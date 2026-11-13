"""Stored analyses computed by Hydrolog (ADR-016): build, carry-forward, reading, on the fly.

Hydrolog's program is the recorded fake of ``tests/fixtures/hydrolog``: the answers
of the real Hydrolog on the ``complete_pl_cz`` fixture store. The test marked
``hydrolog`` builds the same store with the real program named by
``OBSERWATOR_HYDROLOG_COMMAND`` and repeats every stored line with one call of
Hydrolog's CLI.
"""

import csv
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from obserwator import (
    AnalysisSource,
    ObserwatorDataError,
    ObserwatorError,
    ObserwatorStoreError,
    ObserwatorValidationError,
    analysis_definitions,
    build_analyses,
    build_series,
    check_analyses,
    compute_analysis,
    current_version,
    export_analyses,
    export_series,
    get_dataset,
    iter_store,
    list_analyses,
    read_analysis,
    read_meta,
    read_series_index,
)
from obserwator._hydrolog import program_words
from obserwator.attribution import Attribution, attribution
from tests.contract.support import (
    BEZ_Q,
    DAILY,
    FAKE_HYDROLOG,
    PRECIP,
    PROCESSED,
    RABA,
    SOURCE,
    command_document,
    command_line,
    load,
    schema_errors,
    sha256,
    snapshot,
    stamps,
    trailing_lines,
    use_fake_hydrolog,
)

# The real Hydrolog of the test marked ``hydrolog``, read before any test changes it.
REAL_HYDROLOG = os.environ.get("OBSERWATOR_HYDROLOG_COMMAND")
# The fake's recorded answers: a command (``#index`` for meteo indices) → result or error.
ANSWERS: dict[str, Any] = json.loads(
    (FAKE_HYDROLOG.parent / "answers.json").read_text(encoding="utf-8")
)
FAILING = {key for key, answer in ANSWERS.items() if "error" in answer}
VERSION = "1.0.0.dev0"  # the fake's version
SLOTS = {"IMGW-PIB": "pl.imgw", "CHMI": "cz.chmi"}
METEO = "123750000"  # an IMGW-PIB precipitation station of the fixture
CHMI_METEO = "0-203-0-90001"  # a ČHMÚ climate station of the fixture
# The options of the series files Hydrolog reads (AnalysisInput.option).
SERIES_FILES = {
    item.option
    for definition in analysis_definitions()
    for variant in definition.variants
    for item in variant.inputs
}
FROZEN_AT = datetime(2026, 10, 20, 9, 0, tzinfo=UTC)


@pytest.fixture(scope="module")
def built(tmp_path_factory, fixture_root):
    """The fixture data root with the analyses of every station; never written."""
    root = tmp_path_factory.mktemp("built") / "store"
    shutil.copytree(fixture_root, root)
    with pytest.MonkeyPatch.context() as patch:
        use_fake_hydrolog(patch)
        assert build_analyses(root).status == "new"
    return root


@pytest.fixture(autouse=True)
def fake_hydrolog(monkeypatch):
    """Hydrolog's program is the fake, answering at once with its own version."""
    for name in (
        "FAKE_HYDROLOG_VERSION",
        "FAKE_HYDROLOG_SLEEP",
        "FAKE_HYDROLOG_FAIL",
        "FAKE_HYDROLOG_LOG",
    ):
        monkeypatch.delenv(name, raising=False)
    use_fake_hydrolog(monkeypatch)


@pytest.fixture(autouse=True)
def temporary(monkeypatch, tmp_path):
    """The temporary directory (``TMPDIR``) of the test: the scratch directories go here."""
    directory = tmp_path / "tmp"
    directory.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(directory))
    return directory


@pytest.fixture
def batches(monkeypatch, tmp_path):
    """The batches the fake ran since the last look: each its arguments and calls."""
    log = tmp_path / "hydrolog.jsonl"
    monkeypatch.setenv("FAKE_HYDROLOG_LOG", str(log))

    def runs():
        found = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
        log.unlink(missing_ok=True)
        return [json.loads(line) for line in found]

    return runs


@pytest.fixture
def frozen(monkeypatch):
    """The clock of the analyses: computed and built at one moment."""

    class Frozen(datetime):
        @classmethod
        def now(cls, tz=None):
            return FROZEN_AT.astimezone(tz)

    monkeypatch.setattr("obserwator.store.analyses.datetime", Frozen)


def copy(root: Path, target: Path) -> Path:
    shutil.copytree(root, target)
    return target


def slot(root: Path, provider: str) -> Path:
    """The directory of the analyses versions of a provider."""
    return root / "analyses" / "versions" / SLOTS[provider]


def records(version: Path) -> dict[str, Any]:
    """The station records of a version (``stations/<code>.json``), by code."""
    document = load(version / "analyses.json")
    return {
        code: load(version / entry["file"])
        for code, entry in document["stations"].items()
    }


def answer_key(stored: dict[str, Any]) -> str:
    """The fake's recorded answer of a stored call: its command and meteo index."""
    index = stored["options"].get("index")
    return str(stored["command"]) + ("" if index is None else f"#{index}")


def called(runs: list[dict[str, Any]]) -> set[str]:
    """The stations whose series files the calls of ``runs`` read."""
    return {
        value.split("_", 1)[0]
        for run in runs
        for call in run["calls"]
        for name, value in call["options"].items()
        if name in SERIES_FILES
    }


def source_of(root: Path, dataset: str, station: str) -> AnalysisSource:
    """The current series of a station, as an analysis reading it names it."""
    entry = current_version(root, slot=f"series:{dataset}")
    assert entry is not None and entry.version is not None and entry.meta is not None
    exported = "".join(export_series(entry.version, station=station))
    return AnalysisSource(
        dataset,
        entry.version.parent.relative_to(root).as_posix(),
        entry.meta.sha256,
        read_series_index(entry.version).stations[station].sha256,
        hashlib.sha256(exported.encode("utf-8")).hexdigest(),
    )


def recreate_series(root: Path, version: Path) -> Path:
    """
    The series files of a version's stations, exported again where Hydrolog read them.

    The envelopes name them (``inputs``) in the scratch directory of the build,
    which the build removed; each export gives the bytes the build gave
    Hydrolog (``export_sha256`` of the record).
    """
    stations = records(version)
    named = {
        Path(value)
        for record in stations.values()
        for entry in record["results"]
        for name, value in load(version / entry["file"]).get("inputs", {}).items()
        if name in SERIES_FILES
    }
    (directory,) = {path.parent for path in named}
    assert not directory.exists()
    for code, record in stations.items():
        for item in record["inputs"]:
            exported = export_series(
                root / item["series_version"],
                station=code,
                output=directory / f"{code}_{get_dataset(item['dataset']).slug}.csv",
            )
            assert exported.files[0].sha256 == item["export_sha256"]
    assert all(path.is_file() for path in named)
    return directory


def fake_lines(directory: Path, calls: list[dict[str, Any]]) -> list[bytes]:
    """The lines the fake answers ``calls`` with, run as Obserwator runs a batch."""
    script, output = directory / "replay.jsonl", directory / "replay.out.jsonl"
    with script.open("w", encoding="utf-8", newline="\n") as stream:
        for call in calls:
            stream.write(json.dumps(call, ensure_ascii=False) + "\n")
    finished = subprocess.run(
        [sys.executable, str(FAKE_HYDROLOG), "commands", "batch"]
        + ["--input-file", str(script), "--output", str(output), "--json"],
        capture_output=True,
        check=False,
    )
    assert finished.returncode in (0, 10), finished.stderr
    return output.read_bytes().splitlines(keepends=True)


def call_of(entry: dict[str, Any], line: bytes) -> dict[str, Any]:
    """The call a stored line answered: its options in the order Hydrolog echoed them."""
    echoed = json.loads(line).get("inputs")
    if echoed is None:  # an error document echoes nothing
        return {"command": entry["command"], "options": entry["options"]}
    assert set(echoed) == set(entry["options"])
    options = {name: entry["options"][name] for name in echoed}
    return {"command": entry["command"], "options": options}


def leaves(value: object, pointer: str = "") -> Iterator[tuple[str, object]]:
    """``(JSON Pointer, value)`` of every scalar of ``value`` (RFC 6901)."""
    if isinstance(value, dict):
        for key, item in value.items():
            token = str(key).replace("~", "~0").replace("/", "~1")
            yield from leaves(item, f"{pointer}/{token}")
    elif isinstance(value, list):
        for number, item in enumerate(value):
            yield from leaves(item, f"{pointer}/{number}")
    else:
        yield pointer, value


def holds(cell: str, value: object) -> bool:
    """Whether a CSV cell holds a scalar of Hydrolog's result (numbers as decimals)."""
    if value is None:
        return cell == ""
    if isinstance(value, bool):
        return cell == ("true" if value else "false")
    if isinstance(value, int | float):
        return float(cell) == value
    return cell == value


def declared(command: str) -> list[str]:
    """The error codes the catalog declares for ``command``."""
    return list(command_document(command)["commands"][0]["errors"])


def cli_options(options: dict[str, Any]) -> list[str]:
    """Hydrolog's CLI words of call options: lists joined by commas, ``--no-`` for false."""
    words: list[str] = []
    for name, value in options.items():
        flag = "--" + name.replace("_", "-")
        if isinstance(value, bool):
            words.append(flag if value else f"--no-{flag[2:]}")
        elif isinstance(value, list):
            words += [flag, ",".join(str(item) for item in value)]
        else:
            words += [flag, str(value)]
    return words


# --------------------------------------------------------------------------
# Building
# --------------------------------------------------------------------------


def test_build_stores_each_line_of_hydrolog_verbatim_with_its_record_and_sidecar(
    tmp_path, fixture_root, temporary
):
    root = copy(fixture_root, tmp_path / "store")

    report = build_analyses(root)

    assert (report.status, report.hydrolog_version) == ("new", VERSION)
    assert [item.provider for item in report.providers] == ["IMGW-PIB", "CHMI"]
    assert [(file.path, file.status) for file in report.files] == [
        (item.version, "new") for item in report.providers
    ]
    assert list(temporary.iterdir()) == []  # the series files of Hydrolog are gone
    for item in report.providers:
        (version,) = slot(root, item.provider).iterdir()
        main, sidecar = version / "analyses.json", version / "analyses.json.meta.json"
        document, stations, meta = load(main), records(version), read_meta(sidecar)
        assert item.version == main
        assert schema_errors(load(sidecar), "obserwator-meta/1") == []
        assert (meta.dataset, meta.provider, meta.sha256, meta.size_bytes) == (
            f"{SLOTS[item.provider]}.analyses",
            item.provider,
            sha256(main),
            main.stat().st_size,
        )
        assert (meta.extra["derived"], meta.extra["hydrolog_version"]) == (
            "analyses",
            VERSION,
        )
        assert meta.request == {"stations": None}
        assert version.name == f"{meta.extra['version']['label']}_{meta.sha256[:8]}"
        assert (item.status, item.stations, item.computed, item.carried) == (
            "new",
            len(stations),
            len(stations),
            0,
        )
        files = {main.name, sidecar.name}
        ok = 0
        for code, record in stations.items():
            entry = document["stations"][code]
            assert entry["sha256"] == sha256(version / entry["file"])
            files.add(entry["file"])
            for result in record["results"]:
                failed = answer_key(result) in FAILING
                assert result["file"] == f"stations/{code}/{result['analysis']}.json"
                assert result["sha256"] == sha256(version / result["file"])
                assert (result["status"], result["error_code"]) == (
                    ("failed", "calculation_error") if failed else ("ok", None)
                )
                files.add(result["file"])
            for source in record["inputs"]:  # the current series of the station
                assert AnalysisSource(**source) == source_of(
                    root, source["dataset"], code
                )
            stored_ok = sum(result["status"] == "ok" for result in record["results"])
            assert (entry["n_ok"], entry["n_failed"]) == (
                stored_ok,
                len(record["results"]) - stored_ok,
            )
            ok += stored_ok
        assert (item.results_ok, item.results_ok + item.results_failed) == (
            ok,
            sum(len(record["results"]) for record in stations.values()),
        )
        assert {
            path.relative_to(version).as_posix()
            for path in version.rglob("*")
            if path.is_file()
        } == files
        # Every stored line is the fake's answer to the stored call, byte for byte.
        directory = recreate_series(root, version)
        entries = [
            (entry, (version / entry["file"]).read_bytes())
            for record in stations.values()
            for entry in record["results"]
        ]
        replayed = fake_lines(
            directory, [call_of(entry, line) for entry, line in entries]
        )
        assert replayed == [line for _, line in entries]


def test_check_plans_a_build_without_computing_or_writing(
    tmp_path, fixture_root, batches
):
    root = copy(fixture_root, tmp_path / "store")
    before = stamps(root)

    planned = check_analyses(root)

    assert [action.status for action in planned.actions] == ["missing", "missing"]
    assert stamps(root) == before
    assert batches() == []  # Hydrolog was asked its version only
    build_analyses(root)
    batches()
    assert [action.status for action in check_analyses(root).actions] == [
        "current",
        "current",
    ]
    assert batches() == []


def test_a_rebuild_carries_every_station_until_hydrologs_version_changes(
    tmp_path, built, batches, monkeypatch
):
    root = copy(built, tmp_path / "store")
    before = snapshot(root / "analyses")

    again = build_analyses(root)

    assert again.status == "unchanged"
    assert [(item.status, item.computed, item.carried) for item in again.providers] == [
        ("unchanged", 0, item.stations) for item in again.providers
    ]
    assert [(file.path, file.status) for file in again.files] == [
        (item.version, "unchanged") for item in again.providers
    ]
    assert batches() == []
    assert snapshot(root / "analyses") == before

    monkeypatch.setenv("FAKE_HYDROLOG_VERSION", "1.0.1")
    upgraded = build_analyses(root)

    assert (upgraded.status, upgraded.hydrolog_version) == ("new", "1.0.1")
    assert [
        (item.status, item.computed, item.carried) for item in upgraded.providers
    ] == [("new", item.stations, 0) for item in upgraded.providers]


def test_a_new_series_version_recomputes_its_changed_stations_and_links_the_others(
    tmp_path, built, fixture_raw_root, batches
):
    root = copy(built, tmp_path / "store")
    (old,) = slot(root, "IMGW-PIB").iterdir()
    stored, kept = records(old), snapshot(old)

    def precipitation():
        entry = current_version(root, slot=f"series:{PRECIP}")
        return read_series_index(entry.version).stations

    before = precipitation()
    # The late 1995 archive of the fixture joins the precipitation series.
    assert build_series(root, raw_root=fixture_raw_root, dataset=PRECIP).status == "new"
    after = precipitation()
    changed = {
        code
        for code in stored
        if code in after
        and (code not in before or after[code].sha256 != before[code].sha256)
    }
    assert changed and changed < set(stored)
    assert [action.status for action in check_analyses(root).actions] == [
        "newer",
        "current",
    ]

    report = build_analyses(root)

    imgw, chmi = report.providers
    assert (imgw.status, imgw.computed, imgw.carried) == (
        "new",
        len(changed),
        len(stored) - len(changed),
    )
    assert (chmi.status, chmi.computed) == ("unchanged", 0)
    assert called(batches()) == changed
    new = imgw.version.parent
    for code, record in records(new).items():
        names = [f"stations/{code}.json", *(r["file"] for r in record["results"])]
        linked = [
            (old / name).exists() and os.path.samefile(new / name, old / name)
            for name in names
        ]
        assert linked == [code not in changed] * len(names), code
    assert snapshot(old) == kept  # a published version never changes


def test_stations_computes_only_the_chosen_stations_and_keeps_the_stored_ones(
    tmp_path, fixture_root, batches
):
    root = copy(fixture_root, tmp_path / "store")

    first = build_analyses(root, stations=[RABA])

    (imgw,) = first.providers
    assert (imgw.provider, imgw.status, imgw.stations, imgw.computed) == (
        "IMGW-PIB",
        "new",
        1,
        1,
    )
    runs = batches()
    assert called(runs) == {RABA}
    assert sum(len(run["calls"]) for run in runs) == len(
        list_analyses(root=root, station=RABA)
    )

    second = build_analyses(root, stations=[BEZ_Q])

    (imgw,) = second.providers
    assert (imgw.status, imgw.stations, imgw.computed, imgw.carried) == ("new", 2, 1, 1)
    assert called(batches()) == {BEZ_Q}
    assert list(load(imgw.version)["stations"]) == [RABA, BEZ_Q]
    sidecar = read_meta(imgw.version.parent / "analyses.json.meta.json")
    assert sidecar.request == {"stations": [BEZ_Q]}


def test_two_workers_store_the_same_results_as_one(
    tmp_path, fixture_root, monkeypatch, frozen
):
    # One scratch directory for both builds: the lines echo its paths.
    use_fake_hydrolog(monkeypatch, tmp_path / "scratch")
    trees = []
    for workers in (1, 2):
        root = copy(fixture_root, tmp_path / f"store{workers}")
        assert build_analyses(root, workers=workers).status == "new"
        trees.append(snapshot(root / "analyses"))

    assert trees[0] == trees[1]


def test_a_failing_program_publishes_nothing_and_is_hydrolog_failed(
    tmp_path, fixture_root, monkeypatch, temporary
):
    root = copy(fixture_root, tmp_path / "store")
    monkeypatch.setenv("FAKE_HYDROLOG_FAIL", "1")

    with pytest.raises(ObserwatorError) as error:
        build_analyses(root)

    assert (error.value.code, error.value.details["reason"]) == (
        "source_unavailable",
        "hydrolog_failed",
    )
    assert error.value.code in declared("analyses build")
    assert not (root / "analyses").exists()
    assert not any((root / ".incoming").iterdir())
    assert list(temporary.iterdir()) == []


@pytest.mark.parametrize("setting", ["names a missing program", "is unset"])
def test_without_hydrologs_program_nothing_runs(
    setting, tmp_path, fixture_root, monkeypatch
):
    if setting == "is unset":  # and no hydrolog on PATH, nogat.toml or .env
        monkeypatch.delenv("OBSERWATOR_HYDROLOG_COMMAND")
        monkeypatch.setenv("PATH", str(tmp_path / "pusty"))
        (tmp_path / "nogat.toml").write_text("", encoding="utf-8")
        monkeypatch.setenv("NOGAT_CONFIG", str(tmp_path / "nogat.toml"))
        monkeypatch.chdir(tmp_path)
    else:
        missing = command_line(str(tmp_path / "brak" / "hydrolog"))
        monkeypatch.setenv("OBSERWATOR_HYDROLOG_COMMAND", missing)
    root = copy(fixture_root, tmp_path / "store")
    before = stamps(root)

    for call in (
        lambda: build_analyses(root),
        lambda: check_analyses(root),
        lambda: compute_analysis(root, station=RABA, analysis="characteristic.Q"),
    ):
        with pytest.raises(ObserwatorError) as error:
            call()
        assert (error.value.code, error.value.details["reason"]) == (
            "missing_dependency",
            "hydrolog_missing",
        )

    assert "missing_dependency" in declared("analyses build")
    assert stamps(root) == before


# --------------------------------------------------------------------------
# Reading
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("station", "kind", "dataset", "lines"),
    [
        (RABA, "hydro", DAILY, attribution("imgw")),
        (CHMI_METEO, "meteo", "cz.chmi.meteo_daily", attribution("chmi")),
    ],
    ids=["IMGW-PIB", "CHMI"],
)
def test_list_and_read_give_hydrologs_answers_with_their_provenance(
    station, kind, dataset, lines, built
):
    summaries = list_analyses(root=built, station=station)

    ids = [summary.analysis for summary in summaries]
    assert ids == [d.id for d in analysis_definitions(kind) if d.id in ids]
    (version,) = slot(built, summaries[0].provider).iterdir()
    source = source_of(built, dataset, station)
    for summary in summaries:
        assert (
            summary.station,
            summary.kind,
            summary.stored,
            summary.analyses_version,
            summary.hydrolog,
            summary.inputs,
        ) == (station, kind, True, version.name, {"version": VERSION}, (source,))
        assert Attribution(summary.attribution, summary.terms_notice) == lines
        result = read_analysis(root=built, station=station, analysis=summary.analysis)
        key = answer_key({"command": summary.command, "options": summary.options})
        if key in FAILING:
            assert (result.status, result.error_code, result.envelope) == (
                "failed",
                "calculation_error",
                None,
            )
            assert result.error == {**ANSWERS[key]["error"], "command": summary.command}
        else:
            assert (result.status, result.error_code, result.error) == (
                "ok",
                None,
                None,
            )
            assert result.envelope is not None
            assert result.envelope["result"] == ANSWERS[key]["result"]
            assert result.envelope["notices"] == ANSWERS[key]["notices"]
    # A version given as its directory, main file or sidecar, or relative to the root.
    for given, root in (
        (version, None),
        (version / "analyses.json", None),
        (version / "analyses.json.meta.json", None),
        (version.relative_to(built), built),
    ):
        assert list_analyses(given, root=root, station=station) == summaries


def test_export_gives_the_results_as_one_json_document_or_a_long_csv(built):
    summaries = {s.analysis: s for s in list_analyses(root=built, station=RABA)}
    (summary, *_) = summaries.values()

    (line,) = export_analyses(root=built, station=RABA)

    assert line.endswith("\n") and "\n" not in line[:-1]
    document = json.loads(line)
    assert (
        document["schema"],
        document["station"],
        document["provider"],
        document["analyses_version"],
        document["hydrolog_version"],
    ) == (
        "obserwator-analyses-export/1",
        RABA,
        "IMGW-PIB",
        summary.analyses_version,
        VERSION,
    )
    assert [result["analysis"] for result in document["results"]] == list(summaries)
    for result in document["results"]:
        key = answer_key(result)
        if key in FAILING:  # Hydrolog's error document instead of a result
            assert (result["result"], result["error"]["code"]) == (
                None,
                "calculation_error",
            )
        else:
            assert (result["result"], result["error"]) == (ANSWERS[key]["result"], None)
    assert Attribution(
        tuple(document["attribution"]), tuple(document["terms_notice"])
    ) == attribution("imgw")

    # The chosen analyses, in the given order, each once; CSV rows of the ok ones.
    chosen = ["monthly.Q", "homogeneity.Q", "characteristic.Q"]
    (picked,) = export_analyses(
        root=built, station=RABA, analyses=[*chosen, "monthly.Q"]
    )
    assert [result["analysis"] for result in json.loads(picked)["results"]] == chosen

    text = "".join(
        export_analyses(root=built, station=RABA, analyses=chosen, format="csv")
    )

    rows = text.splitlines(keepends=True)
    assert all(row.endswith("\r\n") for row in rows)
    assert rows[0] == (
        "station,analysis,command,series_version,hydrolog_version,path,value,"
        "attribution_source,attribution_processed,attribution,terms_notice\r\n"
    )
    table = list(csv.DictReader(io.StringIO(text, newline="")))
    keys = {name: answer_key(vars(summaries[name])) for name in chosen}
    expected = [
        (name, path, value)
        for name in chosen
        if keys[name] not in FAILING
        for path, value in leaves(ANSWERS[keys[name]]["result"])
    ]
    assert [(row["station"], row["analysis"], row["path"]) for row in table] == [
        (RABA, name, path) for name, path, _ in expected
    ]
    assert all(
        holds(row["value"], value)
        for row, (_, _, value) in zip(table, expected, strict=True)
    )
    assert {(row["series_version"], row["hydrolog_version"]) for row in table} == {
        (summary.inputs[0].series_version, VERSION)
    }
    assert [
        (row["attribution_source"], row["attribution_processed"]) for row in table
    ] == [(SOURCE, PROCESSED), *[("", "")] * (len(table) - 1)]
    assert trailing_lines(table) == attribution("imgw")


def test_export_writes_one_file_and_replaces_it_only_with_force(tmp_path, built):
    target = tmp_path / "wyniki" / "raba.json"

    written = export_analyses(root=built, station=RABA, output=target)

    assert [(file.path, file.status) for file in written.files] == [(target, "written")]
    assert target.read_bytes() == "".join(
        export_analyses(root=built, station=RABA)
    ).encode("utf-8")
    with pytest.raises(ObserwatorError) as refused:
        export_analyses(root=built, station=RABA, format="csv", output=target)
    assert refused.value.code == "conflict"
    replaced = export_analyses(
        root=built, station=RABA, format="csv", output=target, force=True
    )
    assert [file.status for file in replaced.files] == ["replaced"]
    assert target.read_bytes() == "".join(
        export_analyses(root=built, station=RABA, format="csv")
    ).encode("utf-8")


@pytest.mark.parametrize(
    "tampered",
    [
        "analyses.json",
        f"stations/{RABA}.json",
        f"stations/{RABA}/characteristic.Q.json",
    ],
)
def test_a_tampered_stored_file_is_a_data_error(tampered, tmp_path, built):
    root = copy(built, tmp_path / "store")
    (version,) = slot(root, "IMGW-PIB").iterdir()
    path = version / tampered
    path.write_bytes(path.read_bytes() + b" ")  # still JSON, no longer the stored bytes

    for read in (
        lambda: read_analysis(root=root, station=RABA, analysis="characteristic.Q"),
        lambda: export_analyses(root=root, station=RABA),
    ):
        with pytest.raises(ObserwatorDataError) as error:
            read()
        assert error.value.code == "data_error"


def test_an_unknown_station_or_analysis_is_refused(built, fixture_root):
    with pytest.raises(ObserwatorStoreError) as unknown:
        list_analyses(root=built, station="149999999")
    assert (unknown.value.code, unknown.value.details["option"]) == (
        "not_found",
        "station",
    )
    with pytest.raises(ObserwatorValidationError) as invalid:
        read_analysis(root=built, station="Raba", analysis="characteristic.Q")
    assert invalid.value.details["option"] == "station"
    with pytest.raises(ObserwatorStoreError) as absent:  # no discharge at this station
        read_analysis(root=built, station=BEZ_Q, analysis="characteristic.Q")
    assert (absent.value.code, absent.value.details["option"]) == (
        "not_found",
        "analysis",
    )
    assert absent.value.details["allowed"] == [
        summary.analysis for summary in list_analyses(root=built, station=BEZ_Q)
    ]
    with pytest.raises(ObserwatorValidationError) as unregistered:
        compute_analysis(fixture_root, station=RABA, analysis="mediana.Q")
    assert unregistered.value.details["option"] == "analysis"
    with pytest.raises(ObserwatorStoreError) as inapplicable:
        compute_analysis(fixture_root, station=BEZ_Q, analysis="characteristic.Q")
    assert (inapplicable.value.code, inapplicable.value.details["reason"]) == (
        "not_found",
        "no_series",
    )
    before = stamps(fixture_root)
    with pytest.raises(ObserwatorValidationError) as outside:
        build_analyses(fixture_root, stations=[RABA, "149999999"])
    assert outside.value.details == {"option": "stations", "value": ["149999999"]}
    assert stamps(fixture_root) == before


# --------------------------------------------------------------------------
# The analyses in the data root (ADR-017)
# --------------------------------------------------------------------------


def test_analyses_versions_are_entries_of_their_slot_and_the_newest_is_current(
    tmp_path, built, monkeypatch
):
    root = copy(built, tmp_path / "store")
    slots = {
        provider: f"analyses:{prefix}.analyses" for provider, prefix in SLOTS.items()
    }

    def entries():
        return {
            (entry.slot, entry.provider, entry.version, entry.meta.dataset)
            for entry in iter_store(root, kind="analyses")
        }

    first = {
        (slots[provider], provider, version / "analyses.json", f"{prefix}.analyses")
        for provider, prefix in SLOTS.items()
        for version in slot(root, provider).iterdir()
    }
    assert entries() == first and len(first) == 2
    for name, _, version, _ in first:
        assert current_version(root, slot=name).version == version

    monkeypatch.setenv("FAKE_HYDROLOG_VERSION", "1.0.1")
    upgraded = build_analyses(root)

    newer = {
        (
            slots[item.provider],
            item.provider,
            item.version,
            f"{SLOTS[item.provider]}.analyses",
        )
        for item in upgraded.providers
    }
    assert entries() == first | newer and len(newer) == 2
    for name, _, version, _ in newer:
        assert current_version(root, slot=name).version == version
    assert list(iter_store(root, kind="problem")) == []


def test_a_broken_analyses_version_is_refused_not_passed_over(
    tmp_path, built, monkeypatch
):
    root = copy(built, tmp_path / "store")
    (older,) = slot(root, "IMGW-PIB").iterdir()
    monkeypatch.setenv("FAKE_HYDROLOG_VERSION", "1.0.1")
    assert build_analyses(root).status == "new"
    (newer,) = set(slot(root, "IMGW-PIB").iterdir()) - {older}
    (newer / "analyses.json.meta.json").write_text("{", encoding="utf-8")
    before = snapshot(root / "analyses")

    for call in (
        lambda: current_version(root, slot="analyses:pl.imgw.analyses"),
        lambda: list_analyses(root=root, station=RABA),
        lambda: read_analysis(root=root, station=RABA, analysis="characteristic.Q"),
        lambda: check_analyses(root),
        lambda: build_analyses(root),
    ):
        with pytest.raises(ObserwatorDataError) as error:
            call()
        assert error.value.code == "data_error"
    assert snapshot(root / "analyses") == before


def test_a_raw_root_is_the_wrong_root_of_the_analyses(fixture_raw_root):
    before = stamps(fixture_raw_root)

    for call in (
        lambda: build_analyses(fixture_raw_root),
        lambda: list_analyses(root=fixture_raw_root, station=RABA),
        lambda: current_version(fixture_raw_root, slot="analyses:pl.imgw.analyses"),
    ):
        with pytest.raises(ObserwatorStoreError) as error:
            call()
        details = error.value.details
        assert (error.value.code, details["reason"], details["kind"]) == (
            "store_unavailable",
            "wrong_root",
            "data",
        )
    assert list(iter_store(fixture_raw_root, kind="analyses")) == []
    assert stamps(fixture_raw_root) == before


# --------------------------------------------------------------------------
# On the fly
# --------------------------------------------------------------------------


def test_compute_answers_on_the_fly_and_keeps_nothing(fixture_root, temporary):
    before = (snapshot(fixture_root), stamps(fixture_root))

    result = compute_analysis(
        fixture_root, station=RABA, analysis="threshold_events.H.swx"
    )

    assert (result.stored, result.analyses_version, result.status, result.error) == (
        False,
        None,
        "ok",
        None,
    )
    assert result.envelope is not None
    assert result.envelope["result"] == ANSWERS["stats threshold-events"]["result"]
    # The threshold is copied from Hydrolog's answer of characteristic.H.
    assert (
        result.options["threshold"] == ANSWERS["stats characteristic"]["result"]["swx"]
    )
    assert result.inputs == (source_of(fixture_root, DAILY, RABA),)
    assert Attribution(result.attribution, result.terms_notice) == attribution("imgw")
    assert (snapshot(fixture_root), stamps(fixture_root)) == before
    assert list(temporary.iterdir()) == []


def test_compute_passes_a_changed_option_on_to_the_analyses_it_depends_on(
    fixture_root, batches
):
    result = compute_analysis(
        fixture_root,
        station=RABA,
        analysis="threshold_events.H.swx",
        options={"first_year": "2024", "min_duration_days": 3},
    )

    assert (result.options["first_year"], result.options["min_duration_days"]) == (
        2024,
        3,
    )
    calls = {
        call["command"]: call["options"] for run in batches() for call in run["calls"]
    }
    assert calls["stats threshold-events"] == result.options
    # characteristic.H declares first_year, not min_duration_days.
    assert calls["stats characteristic"]["first_year"] == 2024
    assert "min_duration_days" not in calls["stats characteristic"]
    # thresholds_mm is locked for mann_kendall.precipitation.days, not for its source.
    days = compute_analysis(
        fixture_root,
        station=METEO,
        analysis="precipitation.days",
        options={"thresholds_mm": "5,10"},
    )
    assert days.options["thresholds_mm"] == [5, 10]


@pytest.mark.parametrize(
    ("station", "analysis", "options", "option"),
    [
        pytest.param(
            RABA,
            "characteristic.Q",
            {"input_file": "inny.csv"},
            "input_file",
            id="file",
        ),
        pytest.param(
            RABA,
            "characteristic.Q",
            {"first_year": "dwa tysiące"},
            "first_year",
            id="type",
        ),
        pytest.param(RABA, "homogeneity.Q", {"alpha": 1}, "alpha", id="bound"),
        pytest.param(
            RABA,
            "flood_frequency.Q",
            {"distribution": "gumbel"},
            "distribution",
            id="choice",
        ),
        pytest.param(
            METEO,
            "mann_kendall.precipitation.days",
            {"thresholds_mm": [5]},
            "thresholds_mm",
            id="locked",
        ),
    ],
)
def test_compute_refuses_an_option_it_may_not_change(
    station, analysis, options, option, fixture_root, batches
):
    with pytest.raises(ObserwatorValidationError) as error:
        compute_analysis(
            fixture_root, station=station, analysis=analysis, options=options
        )

    assert error.value.details["option"] == option
    assert batches() == []


def test_compute_past_its_timeout_is_source_unavailable(
    fixture_root, monkeypatch, temporary
):
    monkeypatch.setenv("FAKE_HYDROLOG_SLEEP", "60")
    started = time.monotonic()

    with pytest.raises(ObserwatorError) as error:
        compute_analysis(
            fixture_root, station=RABA, analysis="characteristic.Q", timeout=0.5
        )

    assert (error.value.code, error.value.details["reason"]) == (
        "source_unavailable",
        "timeout",
    )
    assert time.monotonic() - started < 30  # Hydrolog was stopped, not awaited
    assert list(temporary.iterdir()) == []


# --------------------------------------------------------------------------
# The real Hydrolog
# --------------------------------------------------------------------------


@pytest.mark.hydrolog
@pytest.mark.skipif(
    REAL_HYDROLOG is None,
    reason="needs Hydrolog's program: OBSERWATOR_HYDROLOG_COMMAND",
)
def test_every_line_stored_by_the_real_hydrolog_is_the_answer_of_its_single_call(
    tmp_path, fixture_root, monkeypatch
):
    monkeypatch.setenv("OBSERWATOR_HYDROLOG_COMMAND", str(REAL_HYDROLOG))
    root = copy(fixture_root, tmp_path / "store")

    report = build_analyses(root, workers=2)

    assert report.status == "new", report.problems
    program = program_words()
    calls = []
    for item in report.providers:
        assert item.version is not None
        version = item.version.parent
        directory = recreate_series(root, version)
        calls += [
            (directory, entry, (version / entry["file"]).read_bytes())
            for record in records(version).values()
            for entry in record["results"]
            if entry["status"] == "ok"
        ]

    def single(call):
        directory, entry, line = call
        answered = subprocess.run(
            [*program, *entry["command"].split(), *cli_options(entry["options"])]
            + ["--json"],
            cwd=directory,
            capture_output=True,
            timeout=600,
            check=False,
        )
        if answered.stdout == line:
            return None
        return entry["file"], answered.returncode, answered.stderr[-300:]

    with ThreadPoolExecutor(max_workers=os.cpu_count() or 1) as pool:
        differing = [found for found in pool.map(single, calls) if found is not None]

    assert calls
    assert differing == []
