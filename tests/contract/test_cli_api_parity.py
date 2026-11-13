"""Contract: ``obserwator`` prints the envelope ``run_command`` returns for every step.

A scenario of the two roots (spec §13.3, ADR-017: raw root, data root, series,
catalog, PMAXTP and flat download commands) runs twice on identical fresh inputs
in the same directory, at a frozen clock and against the same recorded IMGW:
through ``run_command`` and through the ``obserwator`` CLI. Every printed line is
the ``obserwator-result/1`` envelope ``CommandResult.to_json(root)`` of the same
step, the exit code follows its status (§13.6), trees and HTTP traffic are
identical, and every slot of a result names a version ``current_version`` finds
in the root of its kind (§13.7). The installed ``obserwator`` executable reads
offline in its own process like the Python API, and two processes building one
series publish it once and leave the raw root they read as it was.
"""

import json
import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from obserwator import (
    ERROR_CODES,
    command_schema,
    current_version,
    run_command,
)
from obserwator.testing import build_fixture_store
from tests.contract.support import (
    DAILY,
    H2024,
    NEW,
    OLD,
    PRECIP,
    PROCESSED,
    RABA,
    SOURCE,
    V1,
    V2,
    V3,
    canonical,
    cli_words,
    envelope_errors,
    load,
    run_obserwator,
    schema_errors,
    sha256,
    slots,
    snapshot,
    stamps,
)
from tests.contract.test_interface_contract import IMGW_SOURCES, Roots

EXIT_CODES = command_schema()["exit_codes"]


def scenario(work: Path, imgw, run) -> list[dict[str, Any]]:
    """Root, series, catalog, PMAXTP and download steps; ``run`` gives envelopes."""
    raw, data = work / "raw", work / "data"
    selection = {"root": raw, "datasets": [DAILY], "years": [2024]}
    steps = [
        run("store init", {"root": raw}),
        run("store init", {"root": data, "kind": "data"}),
    ]
    imgw.publish(H2024, V1, OLD)
    steps.append(run("store check", {**selection, "plan": work / "plan.json"}))
    imgw.publish(H2024, V2, OLD)  # republished after the check: a stale plan
    steps.append(run("store sync", {"root": raw, "plan": work / "plan.json"}))
    steps.append(run("store check", {**selection, "plan": work / "fresh.json"}))
    steps.append(run("store sync", {"root": raw, "plan": work / "fresh.json"}))
    imgw.publish(H2024, V3, NEW)
    steps.append(run("store sync", selection))
    imgw.publish_catalog_sources()
    steps.append(run("store sync", {"root": raw, "datasets": IMGW_SOURCES}))
    built = {"root": data, "raw_root": raw}
    steps.append(run("series build", {**built, "dataset": DAILY}))
    steps.append(run("store catalog", built))
    steps.append(
        run(
            "series export",
            {
                "root": data,
                "version": steps[-2]["result"]["version"],  # relative to the root
                "station": RABA,
                "output": work / "raba.csv",
                "variables": ["H", "Q"],
            },
        )
    )
    imgw.publish_pmaxtp("pmaxtp_pot_first")
    point = {"latitude": 52.23, "longitude": 21.01, "method": "POT"}
    steps.append(run("pmaxtp sync", {"root": raw, **point}))
    steps.append(run("pmaxtp read", {"root": raw, "ind_x": 751, "ind_y": 317}))
    steps.append(
        run(
            "datasets download", {"dataset": DAILY, "years": [2024], "output_dir": work}
        )
    )
    return steps


def test_obserwator_scenario_prints_the_envelopes_of_run_command_and_writes_alike(
    tmp_path, cli, imgw, frozen
):
    work = tmp_path / "work"

    def python(command, options):
        envelope = run_command(command, options=options)
        return envelope.to_json(root=options.get("root"))

    def printed(command, options):
        result = cli(*cli_words(command, options))
        document = json.loads(result.stdout)
        assert result.exit_code == EXIT_CODES[document["status"]], result.output
        return document

    runs = []
    for run in (python, printed):
        if work.exists():
            shutil.rmtree(work)
        work.mkdir()
        start = len(imgw.router.calls)
        steps = scenario(work, imgw, run)
        runs.append((steps, snapshot(work), imgw.traffic(start)))
    (returned, tree, traffic), (shown, cli_tree, cli_traffic) = runs

    assert [canonical(step) for step in shown] == [canonical(s) for s in returned]
    assert cli_tree == tree
    assert cli_traffic == traffic
    roots = Roots(work / "data", work / "raw")
    for step in returned:
        assert envelope_errors(step) == [], step["command"]
        for slot in slots(step["result"]):
            assert current_version(roots.of_slot(slot), slot=slot).slot == slot

    def statuses(step):
        return [item["status"] for item in step["result"]["items"]]

    raw, data = returned[0:2]
    assert raw["result"]["schema"] == "obserwator-store/1"
    assert data["result"]["schema"] == "obserwator-data/1"
    check, stale, fresh, synced, newer, sources = returned[2:8]
    assert statuses(check) == statuses(fresh) == ["missing"]
    # The plan file is the plan of the envelope (one obserwator-plan/1 document).
    assert load(work / "fresh.json") == fresh["result"]
    assert schema_errors(fresh["result"], "obserwator-plan/1") == []
    assert statuses(stale) == ["stale_plan"]
    assert stale["status"] == "failed"  # no item done: exit code 11
    assert stale["result"]["files"] == []
    # A sync writes raw data only: the report lists the archive versions, no series.
    for step in (synced, newer, sources):
        assert step["result"]["schema"] == "obserwator-sync-report/2"
        assert "series" not in step["result"]
        assert [file["path"] for file in step["result"]["files"]] == [
            item["version"] for item in step["result"]["items"]
        ]
    assert statuses(synced) == statuses(newer) == ["new"]
    assert statuses(sources) == ["new"] * 4
    # The stored current-data answers are processed: the line P joins the line S.
    assert synced["attribution"] == [SOURCE]
    assert sources["attribution"] == [SOURCE, PROCESSED]
    series, catalog, exported, cell = returned[8:12]
    assert [step["result"]["status"] for step in (series, catalog, cell)] == ["new"] * 3
    # The series is built in the data root from the archives of the raw root.
    assert not Path(series["result"]["version"]).is_absolute()
    assert all(
        Path(source).is_relative_to(work / "raw")
        for source in series["result"]["source_files"]
    )
    assert exported["result"] == {
        "schema": "obserwator-output/1",
        "output": str(work / "raba.csv"),
        "files": [
            {
                "path": str(work / "raba.csv"),
                "size_bytes": (work / "raba.csv").stat().st_size,
                "sha256": sha256(work / "raba.csv"),
                "status": "written",
            }
        ],
    }
    downloaded = returned[13]
    assert statuses(downloaded) == ["downloaded"]
    assert (
        downloaded["result"]["items"][0]["slot"]
        == f"archive:{DAILY}:2024/codz_2024.zip"
    )
    # The raw root: 6 archive versions (2 × codz_2024, 2 station lists, 2 current-data
    # answers) and the PMAXTP cell; the data root: the series built once, the catalog.
    metas = [path for path in tree if path.endswith(".meta.json")]
    assert sum(path.startswith("raw/") for path in metas) == 7
    assert sum(path.startswith("data/") for path in metas) == 2
    assert len(metas) == 9


def test_installed_obserwator_prints_the_envelopes_of_run_command_offline(
    tmp_path, fixture_root, fixture_raw_root, imgw
):
    corrupt = build_fixture_store(
        tmp_path / "corrupt-raw", data_root=tmp_path / "corrupt-data", variant="corrupt"
    )
    raw, root = tmp_path / "raw", tmp_path / "data"
    shutil.copytree(fixture_raw_root, raw)
    shutil.copytree(fixture_root, root)
    target = tmp_path / "raba.csv"
    before = stamps(raw), stamps(root)

    for command, options in (
        ("store info", {"root": root}),
        ("store info", {"root": raw}),
        ("store info", {"root": tmp_path / "brak"}),
        ("store scan", {"root": corrupt.raw.root, "kind": "problem"}),
        ("store scan", {"root": corrupt.data.root, "kind": "problem"}),
        (
            "series export",
            {"root": root, "dataset": DAILY, "station": RABA, "output": target},
        ),
    ):
        printed = run_obserwator(*cli_words(command, options))
        exported = target.read_bytes() if target.exists() else None
        target.unlink(missing_ok=True)

        expected = run_command(command, options=options).to_json(
            root=options.get("root")
        )

        document = json.loads(printed.stdout)
        assert printed.stdout.count("\n") == 1
        assert envelope_errors(document) == []
        assert canonical(document) == canonical(expected)
        assert exported == (target.read_bytes() if target.exists() else None)
        target.unlink(missing_ok=True)
    assert (stamps(raw), stamps(root)) == before

    refused = run_obserwator(
        "store", "check", "--root", raw, "--datasets", DAILY, check=False
    )
    line = json.loads(refused.stderr.splitlines()[-1])
    assert (refused.returncode, refused.stdout) == (
        ERROR_CODES["validation_error"].exit_code,
        "",
    )
    assert schema_errors(line, "obserwator-error/1") == []
    assert (line["code"], line["details"]["option"]) == ("validation_error", "years")


def test_two_obserwator_processes_building_one_series_publish_it_once(
    tmp_path, fixture_root, fixture_raw_root
):
    raw, root = tmp_path / "raw", tmp_path / "data"
    shutil.copytree(fixture_raw_root, raw)
    shutil.copytree(fixture_root, root)
    slot = root / "series" / "versions" / "meteo_precip_daily"
    before = {path.name for path in slot.iterdir()}
    read = stamps(raw)

    def build(_):
        return run_obserwator(
            "series",
            "build",
            "--root",
            root,
            "--raw-root",
            raw,
            "--dataset",
            PRECIP,
            "--json",
        )

    with ThreadPoolExecutor(2) as pool:
        envelopes = [json.loads(result.stdout) for result in pool.map(build, range(2))]

    assert [envelope_errors(envelope) for envelope in envelopes] == [[], []]
    assert [envelope["status"] for envelope in envelopes] == ["ok", "ok"]
    reports = [envelope["result"] for envelope in envelopes]
    assert sorted(report["status"] for report in reports) == ["new", "unchanged"]
    assert len({report["version"] for report in reports}) == 1
    (new,) = {path.name for path in slot.iterdir()} - before
    assert Path(reports[0]["version"]).parent.name == new
    assert not any((root / ".incoming").iterdir())
    assert stamps(raw) == read  # a build never writes into the raw root it reads
