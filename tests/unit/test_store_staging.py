"""store import --staging: PIG-PIB's interim capture (S0) into the raw root (ADR-035).

The runs are written here as S0 writes them (each answer a file, a manifest line with
its time, address, status, size and SHA-256, the events of the run) or as the probe
did (GET addresses, no part, no events), their answers those of the rows recorded on
2026-11-24 (``pig_recordings.json``), served by `obserwator.testing._PigService`. One
cut of the real staging (``tests/fixtures/pig_staging``) checks the import against
answers as S0 kept them.
"""

import gzip
import hashlib
import json
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit
from zoneinfo import ZoneInfo

import pytest

from obserwator.captures import Spooled
from obserwator.commands import check_command, run_command
from obserwator.datasets import _capture_file, get_dataset
from obserwator.exceptions import ObserwatorValidationError
from obserwator.store import check_import, import_files, init_store
from obserwator.store.captures import decode, encode
from obserwator.store.writer import write_capture
from obserwator.testing import _PigService

BASE = "https://cbdgmapa.pgi.gov.pl/arcgis/rest/services/hydrogeologia/"
POINTS = "mwp/MapServer/0"
READINGS = "mwp/MapServer/1"
AUTO_POINTS = "mwp_auto/MapServer/0"
AUTO_ROWS = "mwp_auto/MapServer/2"
OPERATIONAL = "pl.pig.groundwater_operational"
OCTOBER = "mwp/MapServer/1/MWP_2026-10"
POINTS_SLOT = "mwp/MapServer/0/MWP_points"
WARSAW = ZoneInfo("Europe/Warsaw")
DST = "TIME >= TIMESTAMP '{day} 02:00:00' AND TIME < TIMESTAMP '{day} 03:00:00'"
CUT = Path(__file__).parents[1] / "fixtures" / "pig_staging"
LAST_ROW = 60938323
"""The newest OBJECTID of the recorded hourly rows."""


@pytest.fixture(autouse=True)
def state_dir(tmp_path, monkeypatch):
    """The test's state directory (the lock of the captures' sealing) and nogat.toml."""
    monkeypatch.setenv("OBSERWATOR_STATE_DIR", str(tmp_path / "state"))
    config = tmp_path / "nogat.toml"
    config.write_text("", encoding="utf-8")
    monkeypatch.setenv("NOGAT_CONFIG", str(config))


@pytest.fixture
def service():
    return _PigService()


@pytest.fixture
def staging(tmp_path):
    return tmp_path / "staging"


@pytest.fixture
def raw(tmp_path):
    return init_store(tmp_path / "raw").root


class Run:
    """One run of the interim capture, written as S0 writes it, or as the probe did."""

    def __init__(self, staging, name, service, *, probe=False):
        self.dir = staging / name
        self.dir.mkdir(parents=True)
        self.service = service
        self.probe = probe
        self.records = []
        self.clock = datetime.strptime(name, "%Y-%m-%dT%H%M%SZ").replace(tzinfo=UTC)
        self.event(event="run_start")

    def tick(self):
        self.clock += timedelta(seconds=2)
        return self.clock.strftime("%Y-%m-%dT%H:%M:%S.%fZ")

    def event(self, **fields):
        if not self.probe:
            self.records.append({"time": self.tick(), **fields})

    def keep(self, url, file, body, status, **fields):
        (self.dir / file).write_bytes(body)
        self.records.append(
            {
                "time": self.tick(),
                **fields,
                "url": url,
                "file": file,
                "status": status,
                "bytes": len(body),
                "sha256": hashlib.sha256(body).hexdigest(),
            }
        )

    def ask(self, table, params, file, part, *, status=200, body=None):
        """One query: the service's answer (or the one given), kept with its line."""
        if body is None:
            form = {name: str(value) for name, value in params.items()}
            payload = self.service._answer(f"{table}/query", form)
            body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
            body = body.encode("utf-8")
        url = f"{BASE}{table}/query"
        try:
            answer = json.loads(body)
        except ValueError:
            answer = None
        ok = status == 200 and isinstance(answer, dict) and "error" not in answer
        if self.probe:
            self.keep(f"{url}?{urlencode(params)}", file, body, status)
        else:
            self.keep(
                url, file, body, status, part=part, method="POST", params=params, ok=ok
            )
        return answer if ok else None

    def describe(self, path, file):
        """A GET of a service's or layer's description (no query)."""
        body = b'{"currentVersion":11.1,"serviceDescription":"MWP"}'
        self.keep(f"{BASE}{path}?f=json", file, body, 200)

    def offset(
        self, table, part, *, geometry=False, where="1=1", size=1000, between=None
    ):
        """A table by ``resultOffset``, with S0's counts before and after."""
        self.event(event="part_start", part=part)
        count = {"where": where, "returnCountOnly": "true", "f": "json"}
        before = None
        if not self.probe:
            before = self.ask(table, count, f"{part}-count-before.json", part) or {}
            before = before.get("count")
        rows = number = 0
        complete = True
        while True:
            params = {
                "where": where,
                "outFields": "*",
                "orderByFields": "OBJECTID",
                "resultOffset": rows,
                "resultRecordCount": size,
                "returnGeometry": "true" if geometry else "false",
                "f": "json",
            }
            if geometry:
                params["outSR"] = "4326"
            page = self.ask(table, params, f"{part}-page-{number:04d}.json", part)
            number += 1
            if page is None:
                complete = False
                break
            features = page.get("features", [])
            rows += len(features)
            if not features or (
                len(features) < size and not page.get("exceededTransferLimit")
            ):
                break
        if between is not None:
            between()
        if not self.probe:
            after = self.ask(table, count, f"{part}-count-after.json", part) or {}
            after = after.get("count")
            complete = complete and before == after == rows
            self.event(event="part_end", part=part, complete=complete, rows=rows)

    def watermark(self, mark=0, *, size=1000, fail=None):
        """The hourly table by watermark, then the stored hour 02 of each DST start."""
        part = "mwp_auto-2-appended"
        self.event(event="part_start", part=part, watermark=mark)
        number = 0
        days = set()
        while True:
            params = {
                "where": f"OBJECTID > {mark}",
                "outFields": "*",
                "orderByFields": "OBJECTID",
                "resultRecordCount": size,
                "returnGeometry": "false",
                "f": "json",
            }
            file = f"{part}-page-{number:04d}.json"
            number += 1
            if number - 1 == fail:
                self.ask(AUTO_ROWS, params, file, part, status=503, body=b"Busy")
                continue
            page = self.ask(AUTO_ROWS, params, file, part)
            features = page.get("features", [])
            for feature in features:
                wall = datetime.fromtimestamp(
                    feature["attributes"]["TIME"] / 1000, WARSAW
                ).date()
                if wall.month == 3 and wall.weekday() == 6 and wall.day > 24:
                    days.add(wall)
                mark = max(mark, feature["attributes"]["OBJECTID"])
            if len(features) < size and not page.get("exceededTransferLimit"):
                break
        for day in sorted(days):
            self.offset(
                AUTO_ROWS, f"mwp_auto-2-dst-{day}-h02", where=DST.format(day=day)
            )
        self.event(event="part_end", part=part, complete=True, watermark=mark)
        return mark

    def close(self, *, ended=True):
        if ended:
            self.event(event="run_end", complete=True)
        lines = [json.dumps(record, ensure_ascii=False) for record in self.records]
        (self.dir / "manifest.jsonl").write_text("\n".join(lines) + "\n", "utf-8")


def probe_run(staging, service, name="2026-11-24T221607Z"):
    """The probe's capture: GET pages, descriptions and mwp_auto's stored day."""
    run = Run(staging, name, service, probe=True)
    run.describe("mwp/MapServer", "mwp-service.json")
    run.describe(f"{READINGS}", "mwp-1-layer.json")
    run.offset(POINTS, "mwp-0", geometry=True)
    run.offset(READINGS, "mwp-1", size=100)
    run.offset(AUTO_POINTS, "mwp_auto-0", geometry=True)
    day = "TIME >= TIMESTAMP '2026-11-23 00:00:00' AND TIME < TIMESTAMP '2026-11-24 00:00:00'"
    run.offset(AUTO_ROWS, "mwp_auto-2-day-2026-11-23", where=day)
    run.close()
    return run


def normal_run(staging, service, name, *, between=None):
    """S0's daily run: the points, the readings and mwp_auto's points."""
    run = Run(staging, name, service)
    run.offset(POINTS, "mwp-0-points", geometry=True)
    run.offset(READINGS, "mwp-1-readings", between=between)
    run.offset(AUTO_POINTS, "mwp_auto-0-points", geometry=True)
    run.close()
    return run


def versions(raw, slot):
    """The version directories of a slot (not its observation register)."""
    directory = raw / "archives" / "versions" / slot
    if not directory.is_dir():
        return []
    return sorted(path for path in directory.iterdir() if path.name != "observations")


def sidecar(version):
    return json.loads(Path(f"{version}.meta.json").read_text(encoding="utf-8"))


def lines(version):
    text = gzip.decompress(Path(version).read_bytes()).decode("utf-8")
    return [json.loads(line) for line in text.split("\n") if line]


def form(address):
    return dict(parse_qsl(urlsplit(address).query, keep_blank_values=True))


def tree(root):
    """Every file below a root with its bytes' hash (the raw root's state)."""
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file() and ".incoming" not in path.parts
    }


def day_version(raw, day):
    (version,) = versions(raw, f"mwp_auto/MapServer/{day}")
    return version / f"{day}.jsonl.gz"


def stage(staging, service):
    """The probe, a daily run, two backfill runs (one with a 503) and the next day's."""
    probe_run(staging, service)
    normal_run(staging, service, "2026-11-24T231810Z")
    first = Run(staging, "2026-11-24T232212Z", service)
    mark = first.watermark(size=60, fail=1)
    first.close()
    nothing = Run(staging, "2026-11-24T233049Z", service)
    assert nothing.watermark(mark, size=60) == mark
    nothing.close()
    normal_run(staging, service, "2026-11-25T061536Z")


# --------------------------------------------------------------------------
# The import
# --------------------------------------------------------------------------


def test_each_table_of_a_run_is_a_version_dated_by_its_run(raw, staging, service):
    stage(staging, service)
    notices = []

    report = import_files(
        raw.parent / "data", raw_root=raw, staging=staging, on_notice=notices.append
    )

    assert (report.provider, report.cancelled, report.series, report.catalog) == (
        "PIG",
        False,
        (),
        None,
    )
    statuses = [(item.slot, item.status) for item in report.items]
    october = "archive:pl.pig.groundwater_readings:MWP_2026-10.jsonl.gz"
    points = "archive:pl.pig.groundwater_stations:MWP_points.jsonl.gz"
    # The probe's tables are the first versions; the later runs' equal content.
    assert statuses[:6] == [
        (points, "new"),
        (october, "new"),
        (points, "unchanged"),
        (october, "unchanged"),
        (points, "unchanged"),
        (october, "unchanged"),
    ]
    (version,) = versions(raw, OCTOBER)
    meta = sidecar(version / "MWP_2026-10.jsonl.gz")
    # October 2026 dated by the probe's run: its time, its day's label and W.
    assert meta["downloaded_at"] == "2026-11-24T22:16:07Z"
    assert meta["extra"]["version"] == {
        "label": "2026-11-24",
        "label_source": "downloaded",
    }
    assert meta["extra"]["staging"] == {"run": "2026-11-24T221607Z"}
    assert "pozyskano 2026-11-24" in meta["license"]["attribution"]
    assert version.name.startswith("2026-11-24_")
    kept = lines(version / "MWP_2026-10.jsonl.gz")
    # The probe's two GET pages by resultOffset, as they came.
    assert [form(line["address"])["resultOffset"] for line in kept] == ["0", "100"]
    assert sum(len(json.loads(line["body"])["features"]) for line in kept) == 168
    # An equal run whose signal differs (the daily run's container also holds the
    # counts) is recorded as seen at its run's time, not the import's (ADR-003 D18).
    seen = sorted((raw / "archives/versions" / OCTOBER / "observations").iterdir())
    observed = [json.loads(path.read_text()) for path in seen]
    assert [(o["seen_at"], o["same_content_as"]) for o in observed][0] == (
        "2026-11-24T23:18:10Z",
        version.name,
    )
    codes = [notice.code for notice in notices]
    assert codes.count("content_unchanged") == 4
    assert (report.files[0].path, report.files[0].status) == (
        versions(raw, POINTS_SLOT)[0] / "MWP_points.jsonl.gz",
        "new",
    )


def test_the_harvests_answers_are_the_capture_of_their_runs_day(raw, staging, service):
    stage(staging, service)
    notices = []

    report = import_files(
        raw.parent / "data", raw_root=raw, staging=staging, on_notice=notices.append
    )

    days = [(item.slot, item.status) for item in report.items[-2:]]
    assert days == [
        (f"archive:{OPERATIONAL}:2026-11-24.jsonl.gz", "new"),
        (f"archive:{OPERATIONAL}:2026-11-25.jsonl.gz", "new"),
    ]
    day = day_version(raw, "2026-11-24")
    kept = lines(day)
    wheres = [form(line["address"]).get("where") for line in kept]
    # The probe's points page, the daily run's points (counts and page), the
    # watermark pages and the stored hour 02 of 2026-03-29: not the probe's stored
    # day, its descriptions or the answer 503.
    assert {urlsplit(line["address"]).path.rsplit("/", 2)[-2] for line in kept} == {
        "0",
        "2",
    }
    assert not any("2026-11-23" in (where or "") for where in wheres)
    assert {line["status"] for line in kept} == {200}
    marks = [where for where in wheres if where and where.startswith("OBJECTID")]
    assert marks[0] == "OBJECTID > 0"
    assert DST.format(day="2026-03-29") in wheres
    meta = sidecar(day)
    capture = meta["extra"]["capture"]
    assert capture["watermark"] == LAST_ROW
    # The count of a summer-time hour is no count of the table.
    assert "count" not in capture
    assert capture["period"] == ["2026-03-29", "2026-11-23"]
    assert capture["answers"] == len(kept)
    assert meta["extra"]["staging"] == {
        "runs": [
            "2026-11-24T221607Z",
            "2026-11-24T231810Z",
            "2026-11-24T232212Z",
            "2026-11-24T233049Z",
        ]
    }
    next_day = sidecar(day_version(raw, "2026-11-25"))
    assert next_day["extra"]["staging"] == {"runs": ["2026-11-25T061536Z"]}
    assert next_day["extra"]["capture"] == {"answers": 3}
    texts = {(notice.code, notice.message) for notice in notices}
    assert (
        "staging_left_out",
        "2026-11-24T221607Z: 3 answers of no run of a sync or a harvest left out (the "
        "services' and layers' descriptions, other queries)",
    ) in texts
    assert (
        "staging_failed",
        "2026-11-24T232212Z: 1 requests without a good answer left out (an HTTP "
        "status other than 200, an ArcGIS error or no answer)",
    ) in texts


def test_a_second_import_writes_nothing(raw, staging, service):
    stage(staging, service)
    import_files(raw.parent / "data", raw_root=raw, staging=staging)
    before = tree(raw)

    report = import_files(raw.parent / "data", raw_root=raw, staging=staging)

    assert {item.status for item in report.items} == {"unchanged"}
    assert tree(raw) == before
    assert not (raw.parent / "data").exists()


def test_a_run_is_compared_with_the_version_current_at_its_time(raw, staging, service):
    # Runs A and B hold one content, C another: a second import must not take B
    # for a change against C, the newest (the import of an equal run is dated).
    normal_run(staging, service, "2026-11-24T231810Z")
    normal_run(staging, service, "2026-11-25T061536Z")
    row = service.tables[READINGS].rows[0]["attributes"]
    row["GLEBOKOSC_ZWIERCIADLA"] = round(row["GLEBOKOSC_ZWIERCIADLA"] + 0.5, 2)
    normal_run(staging, service, "2026-11-26T061512Z")
    notices = []

    first = import_files(
        raw.parent / "data", raw_root=raw, staging=staging, on_notice=notices.append
    )
    second = import_files(raw.parent / "data", raw_root=raw, staging=staging)

    readings = [
        item.status for item in first.items if "groundwater_readings" in item.slot
    ]
    assert readings == ["new", "unchanged", "new"]
    assert {item.status for item in second.items} == {"unchanged"}
    dated = sorted(path.name[:10] for path in versions(raw, OCTOBER))
    assert dated == ["2026-11-24", "2026-11-26"]
    (republished,) = [n for n in notices if n.code == "month_republished"]
    assert "MWP_2026-10.jsonl.gz" in republished.message


def test_an_incomplete_table_is_left_out_with_its_reason(raw, staging, service):
    rows = service.tables[READINGS].rows

    def one_more():
        rows.append(json.loads(json.dumps(rows[0])))
        rows[-1]["attributes"]["OBJECTID"] = 99999

    normal_run(staging, service, "2026-11-24T231810Z", between=one_more)
    probe = Run(staging, "2026-11-24T221607Z", service, probe=True)
    probe.offset(READINGS, "mwp-1", size=100)
    probe.records.pop()  # the last page is lost: the run has no short page
    probe.close()
    notices = []

    report = import_files(
        raw.parent / "data", raw_root=raw, staging=staging, on_notice=notices.append
    )

    assert "groundwater_readings" not in " ".join(item.slot for item in report.items)
    assert versions(raw, OCTOBER) == []
    reasons = sorted(n.message for n in notices if n.code == "staging_incomplete")
    assert reasons == [
        "2026-11-24T221607Z: pl.pig.groundwater_readings is no complete run (its "
        "pages do not cover the table up to a short page); left out",
        "2026-11-24T231810Z: mwp-1-readings is no complete run (its manifest marks "
        "it incomplete); left out",
    ]


def test_a_run_that_has_not_ended_keeps_its_good_answers(raw, staging, service):
    run = Run(staging, "2026-11-24T232212Z", service)
    run.watermark(size=60)
    run.records = [r for r in run.records if r.get("event") != "part_end"]
    run.close(ended=False)
    notices = []

    report = import_files(
        raw.parent / "data", raw_root=raw, staging=staging, on_notice=notices.append
    )

    (item,) = report.items
    assert item.status == "new"
    assert sidecar(item.version)["extra"]["capture"]["watermark"] == LAST_ROW
    assert ("staging_open", "warning") in {(n.code, n.level) for n in notices}


def test_a_file_unlike_its_manifest_refuses_the_import_before_any_write(
    raw, staging, service
):
    stage(staging, service)
    page = staging / "2026-11-24T232212Z" / "mwp_auto-2-appended-page-0002.json"
    page.write_bytes(page.read_bytes().replace(b'"VALUE":', b'"VALUE": ', 1))
    before = tree(raw)

    with pytest.raises(ObserwatorValidationError) as refused:
        import_files(raw.parent / "data", raw_root=raw, staging=staging)

    assert refused.value.details == {"option": "staging", "path": str(page)}
    assert "does not match its manifest" in str(refused.value)
    assert tree(raw) == before
    page.unlink()
    with pytest.raises(ObserwatorValidationError) as missing:
        check_import(raw.parent / "data", raw_root=raw, staging=staging)
    assert missing.value.details["path"] == str(page)


def test_no_runs_or_both_forms_are_refused(raw, staging, tmp_path):
    staging.mkdir()
    with pytest.raises(ObserwatorValidationError) as empty:
        import_files(raw.parent / "data", raw_root=raw, staging=staging)
    assert empty.value.details == {"option": "staging", "path": str(staging)}
    with pytest.raises(ObserwatorValidationError) as both:
        import_files(
            raw.parent / "data",
            raw_root=raw,
            staging=staging,
            provider_file=tmp_path / "siec.toml",
        )
    assert both.value.details == {"option": "staging"}
    with pytest.raises(ObserwatorValidationError) as neither:
        check_import(raw.parent / "data", raw_root=raw)
    assert neither.value.details == {"option": "provider_file"}


# --------------------------------------------------------------------------
# The capture of a day joined with its current version
# --------------------------------------------------------------------------


def test_a_day_with_a_version_gets_one_holding_both(raw, staging, service):
    # A harvest sealed the day before the import, its second count a ``seen`` line;
    # a run between its two answers asks the same address with another count, so
    # the joined version must give that line its body again. The version streamed
    # is the bytes the sealing of all the answers gives.
    descriptor = get_dataset(OPERATIONAL)
    archive = _capture_file(descriptor, datetime(2026, 11, 24).date())
    body = b'{"count":626}'
    count = f"{BASE}{AUTO_POINTS}/query?where=1%3D1&returnCountOnly=true&f=json"
    harvested = [
        Spooled("2026-11-24T02:31:00.000000Z", count, 200, sha(body), body),
        Spooled("2026-11-24T02:40:00.000000Z", count, 200, sha(body), body),
    ]
    write_capture(raw, archive=archive, data=encode(harvested), answers=2)
    assert [
        line.get("seen", False) for line in lines(day_version(raw, "2026-11-24"))
    ] == [
        False,
        True,
    ]
    run = Run(staging, "2026-11-24T023500Z", service)
    run.offset(AUTO_POINTS, "mwp_auto-0-points", geometry=True)
    run.close()

    report = import_files(raw.parent / "data", raw_root=raw, staging=staging)

    (item,) = report.items
    assert item.status == "new"
    stored = decode(item.version.read_bytes())
    assert [answer.time[11:19] for answer in stored] == [
        "02:31:00",
        "02:35:06",
        "02:35:08",
        "02:35:10",
        "02:40:00",
    ]
    assert stored[-1].content == body
    assert item.version.read_bytes() == encode([*harvested, *stored[1:4]])
    assert [line.get("seen", False) for line in lines(item.version)] == [
        False,
        False,
        False,
        True,
        False,
    ]
    assert sidecar(item.version)["extra"]["staging"] == {"runs": ["2026-11-24T023500Z"]}
    again = import_files(raw.parent / "data", raw_root=raw, staging=staging)
    assert [i.status for i in again.items] == ["unchanged"]


def sha(body):
    return hashlib.sha256(body).hexdigest()


# --------------------------------------------------------------------------
# The plan
# --------------------------------------------------------------------------


def test_check_plans_what_the_import_does(raw, staging, service):
    stage(staging, service)
    before = tree(raw)

    plan = check_import(raw.parent / "data", raw_root=raw, staging=staging)

    assert plan.root == raw
    assert [action.status for action in plan.actions] == [
        "missing",
        "missing",
        "current",
        "current",
        "current",
        "current",
        "missing",
        "missing",
    ]
    assert plan.actions[1].detail == (
        "2026-11-24T221607Z: pl.pig.groundwater_readings as "
        "archive:pl.pig.groundwater_readings:MWP_2026-10.jsonl.gz"
    )
    assert plan.actions[-1].detail.startswith("3 answers of the runs of 2026-11-25 as")
    assert tree(raw) == before
    import_files(raw.parent / "data", raw_root=raw, staging=staging)
    after = check_import(raw.parent / "data", raw_root=raw, staging=staging)
    assert {action.status for action in after.actions} == {"current"}
    late = Run(staging, "2026-11-25T231500Z", service)
    late.offset(AUTO_POINTS, "mwp_auto-0-points", geometry=True)
    late.close()
    newer = check_import(raw.parent / "data", raw_root=raw, staging=staging)
    assert [action.status for action in newer.actions][-2:] == ["current", "newer"]


def test_the_command_takes_staging_instead_of_a_provider_file(raw, staging, service):
    probe_run(staging, service)
    options = {"root": raw.parent / "data", "raw_root": raw, "staging": staging}

    planned = check_command("store import", options=options)
    result = run_command("store import", options=options)

    assert planned.status == "ok"
    assert [action.status for action in planned.result.actions] == [
        "missing",
        "missing",
        "missing",
    ]
    assert result.status == "ok"
    assert [item.status for item in result.result.items] == ["new"] * 3
    # W names the years of the versions' data and the day of their run (DEV-20.13).
    (w,) = [line for line in result.attribution if "PIG-PIB" in line][:1]
    assert "(wytworzono 2026, pozyskano 2026-11-24)" in w


# --------------------------------------------------------------------------
# A cut of the real staging
# --------------------------------------------------------------------------


def test_a_cut_of_the_real_staging_imports_as_kept(raw, tmp_path):
    staging = tmp_path / "staging"
    shutil.copytree(CUT, staging)
    notices = []

    report = import_files(
        raw.parent / "data", raw_root=raw, staging=staging, on_notice=notices.append
    )

    statuses = [(item.slot, item.status) for item in report.items]
    watchlist = "archive:pl.pig.groundwater_watchlist:MWP_watchlist.jsonl.gz"
    day = f"archive:{OPERATIONAL}:2026-11-24.jsonl.gz"
    # The probe's watch list and S0's equal run of it; one capture of the day.
    assert statuses == [(watchlist, "new"), (watchlist, "unchanged"), (day, "new")]
    meta = sidecar(report.items[0].version)
    assert meta["downloaded_at"] == "2026-11-24T22:16:07Z"
    assert meta["extra"]["staging"] == {"run": "2026-11-24T221607Z"}
    capture = sidecar(report.items[2].version)["extra"]["capture"]
    # The last OBJECTID of S0's page 0009 of 2026-11-24T232301Z (as its manifest
    # says), the 503 and the timed-out request left out.
    assert capture["watermark"] == 53586301
    assert "count" not in capture
    failed = sorted(n.message for n in notices if n.code == "staging_failed")
    assert failed == [
        "2026-11-24T232301Z: 1 requests without a good answer left out (an HTTP "
        "status other than 200, an ArcGIS error or no answer)",
        "2026-11-24T233049Z: 1 requests without a good answer left out (an HTTP "
        "status other than 200, an ArcGIS error or no answer)",
    ]
    again = import_files(raw.parent / "data", raw_root=raw, staging=staging)
    assert {item.status for item in again.items} == {"unchanged"}
