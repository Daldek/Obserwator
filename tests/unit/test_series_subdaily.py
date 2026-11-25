"""The hourly series of the tiers, one version per calendar month (ADR-031), on real data.

IMGW-PIB: hydro-back's answers of a harvest of 2026-10-01..31 for Głogów (151160060) and
Kłodzko (150160180) started on 2026-11-23 (``tests/fixtures/operational/october``),
replayed and sealed as the capture of that day, and the telemetry zip of October cut to
the two stations. ČHMÚ: the ``recent`` day files of 2026-11-22 and the validated hours of
2025 of O2's recordings (``tests/fixtures/operational``). Every test has its own spool
(``OBSERWATOR_STATE_DIR``), roots and fake clock at the recording's time.
"""

import io
import json
import zipfile
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import httpx
import pyarrow.parquet as pq
import pytest
import respx

from obserwator import (
    CommandCall,
    captures,
    check_command,
    command_for_version,
    fetch,
    run_command,
    validate_command,
)
from obserwator.attribution import attribution
from obserwator.captures import write_spool
from obserwator.commands import data_commands
from obserwator.datasets import archive_files, datasets, monthly_series
from obserwator.exceptions import ObserwatorValidationError
from obserwator.fetch import DownloadResult
from obserwator.providers.base import Answer
from obserwator.store import (
    build_series,
    check_series,
    init_store,
    sync_store,
    write_archive,
)
from tests.unit.test_paced import CASES as O2_CASES
from tests.unit.test_paced import FIXTURES as O2_FIXTURES
from tests.unit.test_paced import RECORDINGS as O2_RECORDINGS
from tests.unit.test_paced import FakeClock

OCTOBER = Path(__file__).parents[1] / "fixtures" / "operational" / "october"
RECORDINGS = json.loads((OCTOBER / "recordings.json").read_text(encoding="utf-8"))
CASES = {item["case"]: item for item in RECORDINGS["interactions"]}
RECORDED_AT = datetime.fromisoformat(RECORDINGS["recorded_at"])
ZIP = OCTOBER / CASES["telemetry_zip"]["file"]
IMGW = "pl.imgw.hydro_subdaily"
CHMU = "cz.chmu.hydro_subdaily"
OPERATIONAL = "pl.imgw.hydro_operational"
TELEMETRY = "pl.imgw.hydro_telemetry"
RECENT = "cz.chmu.hydro_recent"
HOURLY = "cz.chmu.hydro_hourly"
GLOGOW, KLODZKO = "151160060", "150160180"
STATIONS = (GLOGOW, KLODZKO)
OCTOBER_DAYS = (date(2026, 10, 1), date(2026, 10, 31))
VERSIONS = Path("series") / "versions"
# The series of hydro-back's answers and the telemetry's parameter of each variable.
SERIES = {"H": "status_data", "Q": "discharge", "T": "water-temperature"}
PARAMS = {"H": "B00020S", "Q": "B00050S", "T": "B00100S"}
CHMU_CODE = "0-203-1-001000"
CHMU_RECENT = "https://opendata.chmi.cz/hydrology/recent/data/"
O2_RECORDED_AT = datetime.fromisoformat(O2_RECORDINGS["recorded_at"])
# The lines of IMGW-PIB's hourly series: of the telemetry and of hydro.imgw.pl, whose
# terms (RH) the telemetry's alone lack.
IMGW_LINES = attribution("imgw", "imgw_hydro")


@pytest.fixture(autouse=True)
def clock(tmp_path, monkeypatch):
    """The test's spool and ``nogat.toml``; the clocks of a run and of the spool."""
    monkeypatch.setenv("OBSERWATOR_STATE_DIR", str(tmp_path / "state"))
    config = tmp_path / "nogat.toml"
    config.write_text("", encoding="utf-8")
    monkeypatch.setenv("NOGAT_CONFIG", str(config))
    fake = FakeClock(RECORDED_AT)
    monkeypatch.setattr(fetch, "_clock", lambda: fake)
    monkeypatch.setattr(captures, "_now", fake.now)
    return fake


@pytest.fixture
def raw(tmp_path):
    return init_store(tmp_path / "raw").root


@pytest.fixture
def data(tmp_path):
    return tmp_path / "data"


def harvest_october(raw, clock):
    """Replay the harvest of October at recorded_at, then seal its day (2026-11-23)."""
    with respx.mock(assert_all_called=True) as server:
        for case, item in CASES.items():
            if case != "telemetry_zip":
                body = (OCTOBER / item["file"]).read_bytes()
                server.get(item["url"]).mock(
                    return_value=httpx.Response(item["status"], content=body)
                )
        report = captures.harvest(OPERATIONAL, *OCTOBER_DAYS, stations=list(STATIONS))
    assert (report.planned, report.answers, report.failed) == (6, 6, 0)
    clock.moment = RECORDED_AT + timedelta(days=1)
    (item,) = sync_store(raw, datasets=[OPERATIONAL]).items
    assert (item.slot, item.status) == (
        f"archive:{OPERATIONAL}:2026-11-23.jsonl.gz",
        "new",
    )


def store_telemetry(raw, content=None, modified="Mon, 16 Nov 2026 10:26:00 GMT"):
    (archive,) = archive_files(TELEMETRY, years=[2026], months=[10])
    content = ZIP.read_bytes() if content is None else content
    response = DownloadResult(content, archive.url, None, modified, len(content))
    return write_archive(raw, archive=archive, response=response)


def edited_zip(edit):
    """The telemetry zip with the rows of every member passed through ``edit``."""
    buffer = io.BytesIO()
    with (
        zipfile.ZipFile(ZIP) as source,
        zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as target,
    ):
        for info in source.infolist():
            rows = source.read(info).decode("utf-8").split("\r\n")
            target.writestr(info.filename, "\r\n".join(edit(rows)))
    return buffer.getvalue()


def answered(variable, code, month="2026-10"):
    """The full hours of a month in hydro-back's recorded answer: {UTC hour: value}."""
    item = CASES[f"{SERIES[variable]}_{code}"]
    body = json.loads((OCTOBER / item["file"]).read_bytes())
    return {
        datetime.fromisoformat(entry["date"]): entry["value"]
        for entry in body["operational"]
        if entry["date"].startswith(month)
        and entry["date"].endswith(":00:00Z")
        and entry["date"][:10] < "2026-11-23"
    }


def telemetry(variable, code):
    """The rows at minute 00 of the telemetry zip: {UTC hour: value}."""
    found = {}
    with zipfile.ZipFile(ZIP) as package:
        for name in package.namelist():
            for row in package.read(name).decode("utf-8").split("\r\n"):
                fields = row.split(";")
                if fields[:2] == [code, PARAMS[variable]] and fields[2].endswith(":00"):
                    moment = datetime.fromisoformat(f"{fields[2]}:00+00:00")
                    found[moment] = float(fields[3])
    return found


def month_report(report, month):
    (found,) = [
        item
        for item in report.months
        if item.version is not None and item.version.parent.parent.name == month
    ]
    return found


def document(version):
    return json.loads(version.read_text(encoding="utf-8"))


def sidecar(version):
    return json.loads(Path(f"{version}.meta.json").read_text(encoding="utf-8"))


def rows(version, code):
    return pq.read_table(version.parent / "stations" / f"{code}.parquet").to_pylist()


def values(table, variable):
    """The hours with a value of a variable of a station file: {UTC hour: value}."""
    return {
        row["time"]: row[f"{variable}_value"]
        for row in table
        if row[f"{variable}_flag"] == "value"
    }


def tiers(table, variable):
    return {
        row["time"]: row[f"{variable}_tier"]
        for row in table
        if row[f"{variable}_flag"] == "value"
    }


def build_october(raw, data):
    return build_series(
        data, raw_root=raw, dataset=IMGW, start=OCTOBER_DAYS[0], end=OCTOBER_DAYS[1]
    )


# --------------------------------------------------------------------------
# IMGW-PIB: hydro-back's hours, the telemetry over them
# --------------------------------------------------------------------------


def test_october_from_the_capture_alone_holds_every_full_hour_of_hydro_back(
    raw, data, clock
):
    harvest_october(raw, clock)

    report = build_october(raw, data)

    (month,) = report.months
    assert (report.status, month.status, report.stations) == ("new", "new", 2)
    version = month.version
    assert version.parent.parent == data / VERSIONS / "imgw_hydro_subdaily" / "2026-10"
    index = document(version)
    assert (index["month"], index["tiers"], index["periods"]) == (
        "2026-10",
        ["operational"],
        [["2026-10-01", "2026-10-31"]],
    )
    assert (index["attribution"], index["terms_notice"]) == (
        list(IMGW_LINES.attribution),
        list(IMGW_LINES.terms_notice),
    )
    assert sorted(index["stations"]) == sorted(STATIONS)
    hours = [
        datetime(2026, 10, 1, tzinfo=UTC) + timedelta(hours=step) for step in range(744)
    ]
    for code in STATIONS:
        table = rows(version, code)
        assert [row["time"] for row in table] == hours
        assert index["stations"][code]["rows"] == 744
        # One tier: no tier columns in any station file.
        assert not [name for name in table[0] if name.endswith("_tier")]
        for variable in ("H", "Q"):
            got = values(table, variable)
            assert len(got) == 744
            assert got == answered(variable, code) == telemetry(variable, code)
    glogow = values(rows(version, GLOGOW), "T")
    assert len(glogow) == 22
    assert {moment.hour for moment in glogow} == {6}
    assert glogow == answered("T", GLOGOW) == telemetry("T", GLOGOW)
    assert values(rows(version, KLODZKO), "T") == {}
    assert index["stations"][KLODZKO]["variables"]["T"] == {
        "unit": "degC",
        "first": None,
        "last": None,
        "with_value": 0,
        "accumulated": 0,
        "gaps": [],
    }
    meta = sidecar(version)
    assert meta["request"] == {"dataset": IMGW, "month": "2026-10"}
    assert (meta["tier"], meta["publication"]) == ("operational", "private")
    assert [source["name"] for source in meta["extra"]["source_files"]] == [
        "2026-11-23.jsonl.gz"
    ]


def test_the_telemetry_replaces_every_operational_hour_with_its_own_equal_value(
    raw, data, clock
):
    harvest_october(raw, clock)
    operational = build_october(raw, data).months[0].version
    store_telemetry(raw)

    report = build_october(raw, data)

    (month,) = report.months
    assert month.status == "new"
    version = month.version
    assert version != operational
    index = document(version)
    assert index["tiers"] == ["telemetry"]
    for code in STATIONS:
        table, before = rows(version, code), rows(operational, code)
        assert not [name for name in table[0] if name.endswith("_tier")]
        for variable in ("H", "Q", "T"):
            assert values(table, variable) == values(before, variable)
        assert len(values(table, "H")) == len(values(table, "Q")) == 744
    assert len(values(rows(version, GLOGOW), "T")) == 22
    meta = sidecar(version)
    assert sorted(source["name"] for source in meta["extra"]["source_files"]) == [
        "2026-11-23.jsonl.gz",
        "Hydro_2026-10.zip",
    ]
    # The label is the newest Last-Modified of the inputs.
    assert meta["extra"]["version"] == {"label": "2026-11-16", "label_source": "inputs"}
    assert version.parent.name.startswith("2026-11-16_")


def test_hours_the_telemetry_lacks_stay_operational_in_a_version_of_two_tiers(
    raw, data, clock
):
    harvest_october(raw, clock)
    removed, empty = "2026-10-10 12:00", "2026-10-20 06:00"

    def edit(table):
        for row in table:
            if row.startswith(f"{GLOGOW};B00020S;{removed};"):
                continue
            if row.startswith(f"{GLOGOW};B00020S;{empty};"):
                row = f"{GLOGOW};B00020S;{empty};999"
            yield row

    store_telemetry(raw, edited_zip(edit))

    version = build_october(raw, data).months[0].version

    index = document(version)
    assert index["tiers"] == ["telemetry", "operational"]
    lacking = {
        datetime(2026, 10, 10, 12, tzinfo=UTC),
        datetime(2026, 10, 20, 6, tzinfo=UTC),
    }
    glogow = rows(version, GLOGOW)
    operational = answered("H", GLOGOW)
    assert values(glogow, "H") == operational
    assert {
        moment for moment, tier in tiers(glogow, "H").items() if tier == "operational"
    } == lacking
    assert set(tiers(glogow, "H").values()) == {"telemetry", "operational"}
    assert set(tiers(glogow, "T").values()) == {"telemetry"}
    # Every station file of the version has the tier columns; no value, no tier.
    klodzko = rows(version, KLODZKO)
    assert set(tiers(klodzko, "H").values()) == {"telemetry"}
    assert {row["T_tier"] for row in klodzko} == {None}
    assert index["stations"][GLOGOW]["variables"]["H"]["with_value"] == 744


def test_a_higher_tier_wins_even_where_its_value_differs(raw, data, clock):
    harvest_october(raw, clock)
    hour = datetime(2026, 10, 15, 3, tzinfo=UTC)
    given = answered("H", GLOGOW)[hour] + 7

    def edit(table):
        for row in table:
            if row.startswith(f"{GLOGOW};B00020S;2026-10-15 03:00;"):
                row = f"{GLOGOW};B00020S;2026-10-15 03:00;{given:.1f}".replace(".", ",")
            yield row

    store_telemetry(raw, edited_zip(edit))

    version = build_october(raw, data).months[0].version

    assert document(version)["tiers"] == ["telemetry"]
    got = values(rows(version, GLOGOW), "H")
    assert got[hour] == given
    assert {moment: value for moment, value in got.items() if moment != hour} == {
        moment: value
        for moment, value in answered("H", GLOGOW).items()
        if moment != hour
    }


def test_only_full_hours_of_closed_days_enter_and_each_month_gets_its_version(
    raw, data, clock
):
    harvest_october(raw, clock)

    report = build_series(data, raw_root=raw, dataset=IMGW)

    # 2026-09-30T23:00Z is September's, whose inputs end 43 days after it: the capture
    # of 2026-11-23 holds October and November only.
    assert [month.version.parent.parent.name for month in report.months] == [
        "2026-10",
        "2026-11",
    ]
    assert report.version == report.months[-1].version
    october, november = (month.version for month in report.months)
    assert rows(october, KLODZKO)[0]["time"] == datetime(2026, 10, 1, tzinfo=UTC)
    index = document(november)
    assert index["periods"] == [["2026-11-01", "2026-11-22"]]
    for code in STATIONS:
        table = rows(november, code)
        assert len(table) == index["stations"][code]["rows"] == 22 * 24
        # The answer's day (today then), its 10-minute tail and the forecasts never
        # enter: every hour is a full hour of the days before 2026-11-23.
        assert values(table, "H") == answered("H", code, "2026-11")
        assert max(row["time"] for row in table) == datetime(
            2026, 11, 22, 23, tzinfo=UTC
        )
    # Kłodzko's HBV forecast covers October too; its values are not the series'.
    body = json.loads((OCTOBER / CASES[f"status_data_{KLODZKO}"]["file"]).read_bytes())
    forecast = {
        datetime.fromisoformat(record["date"]): record["value"]
        for record in body["forecasts"][0]["records"]
    }
    got = values(rows(october, KLODZKO), "H")
    differing = [
        moment
        for moment in got
        if moment in forecast and forecast[moment] != got[moment]
    ]
    assert differing
    assert all(got[moment] == answered("H", KLODZKO)[moment] for moment in differing)


def test_a_second_build_of_the_same_inputs_is_unchanged_per_month_and_writes_nothing(
    raw, data, clock
):
    harvest_october(raw, clock)
    first = build_series(data, raw_root=raw, dataset=IMGW)
    tree = sorted(data.rglob("*"))

    again = build_series(data, raw_root=raw, dataset=IMGW)

    assert again.status == "unchanged"
    assert [month.status for month in again.months] == ["unchanged", "unchanged"]
    assert [month.version for month in again.months] == [
        month.version for month in first.months
    ]
    assert sorted(data.rglob("*")) == tree
    # The telemetry is an input of October only.
    store_telemetry(raw)
    after = build_series(data, raw_root=raw, dataset=IMGW)
    assert (after.status, [month.status for month in after.months]) == (
        "new",
        ["new", "unchanged"],
    )


def test_a_month_given_without_a_value_fails_and_the_envelope_is_partial(
    raw, data, clock
):
    harvest_october(raw, clock)

    envelope = run_command(
        "series build",
        options={
            "root": data,
            "raw_root": raw,
            "dataset": IMGW,
            "start": "2026-09-15",
            "end": "2026-10-01",
        },
    )

    report = envelope.result
    assert (envelope.status, report.status) == ("partial", "new")
    september, october = report.months
    assert (september.status, september.version, october.status) == (
        "failed",
        None,
        "new",
    )
    assert "2026-09" in september.problems[0]
    assert report.problems == september.problems
    assert (envelope.attribution, envelope.terms_notice) == (
        IMGW_LINES.attribution,
        IMGW_LINES.terms_notice,
    )
    alone = build_series(
        data, raw_root=raw, dataset=IMGW, start=date(2026, 9, 1), end=date(2026, 9, 30)
    )
    assert (alone.status, [month.status for month in alone.months]) == (
        "failed",
        ["failed"],
    )


def test_an_unreadable_input_fails_only_its_month(raw, data, clock):
    harvest_october(raw, clock)
    store_telemetry(raw, b"no zip")
    notices = []

    report = build_series(data, raw_root=raw, dataset=IMGW, on_notice=notices.append)

    october, november = report.months
    assert (october.status, november.status, report.status) == ("failed", "new", "new")
    assert "Hydro_2026-10" in october.problems[0]
    assert [notice.code for notice in notices if notice.code == "archive_failed"] == [
        "archive_failed"
    ]


# --------------------------------------------------------------------------
# ČHMÚ: the recent days' full hours, the validated hours over them
# --------------------------------------------------------------------------


def chmu_answer(hourly):
    """A ``recent`` answer of 2025-01-01: H unlike the validated hours, TH they lack."""
    series = [
        {
            "tsConID": "H",
            "unit": "CM",
            "tsData": [
                {"dt": moment.strftime("%Y-%m-%dT%H:%M:%SZ"), "value": value + 5}
                for moment, value in hourly.items()
                if moment.day == 1
            ],
        },
        {
            "tsConID": "TH",
            "unit": "0C",
            "tsData": [
                *(
                    {"dt": f"2025-01-01T{hour:02d}:00:00Z", "value": 3.5}
                    for hour in range(24)
                ),
                # A 10-minute point and an hour of the answer's own day never enter.
                {"dt": "2025-01-01T00:10:00Z", "value": 99.0},
                {"dt": "2025-01-02T00:00:00Z", "value": 99.0},
            ],
        },
    ]
    return json.dumps({"objList": [{"objID": CHMU_CODE, "tsList": series}]}).encode()


def test_chmu_recent_full_hours_and_the_validated_hours_over_them(raw, data, clock):
    clock.moment = O2_RECORDED_AT
    cases = [case for case in O2_CASES if case.startswith("chmu_recent_")]
    with respx.mock(assert_all_called=True) as server:
        for case in cases:
            item = O2_CASES[case]
            body = (O2_FIXTURES / item["file"]).read_bytes()
            server.get(item["url"]).mock(
                return_value=httpx.Response(item["status"], content=body)
            )
        captures.harvest(
            RECENT,
            date(2026, 11, 22),
            date(2026, 11, 22),
            stations=[case.removeprefix("chmu_recent_") for case in cases],
        )
    item = O2_CASES["chmu_hourly_2025"]
    content = (O2_FIXTURES / item["file"]).read_bytes()
    validated = json.loads(content)["tsList"]
    hourly = {
        name: {
            datetime.fromisoformat(dt): value
            for dt, value in series["tsData"]["data"]["values"]
        }
        for series in validated
        for name in [{"HH": "H", "QH": "Q"}[series["tsConID"]]]
    }
    write_spool(
        Answer(
            f"{CHMU_RECENT}20250101_{CHMU_CODE}.json",
            datetime(2025, 1, 2, 1, tzinfo=UTC),
            200,
            chmu_answer(hourly["H"]),
            RECENT,
        )
    )
    clock.moment = O2_RECORDED_AT + timedelta(days=1)
    assert {result.status for result in sync_store(raw, datasets=[RECENT]).items} == {
        "new"
    }
    (archive,) = archive_files(HOURLY, stations=[CHMU_CODE], years=[2025])
    headers = item["headers"]
    write_archive(
        raw,
        archive=archive,
        response=DownloadResult(
            content,
            archive.url,
            headers["ETag"],
            headers["Last-Modified"],
            len(content),
        ),
    )

    report = build_series(data, raw_root=raw, dataset=CHMU)

    assert [month.status for month in report.months] == ["new", "new"]
    january, november = (month.version for month in report.months)
    assert november.parent.parent == data / VERSIONS / "chmu_hydro_subdaily" / "2026-11"
    index = document(november)
    assert (index["tiers"], index["periods"]) == (
        ["operational"],
        [["2026-11-22", "2026-11-22"]],
    )
    # The station answered 404 has no file of the day: two stations.
    assert sorted(index["stations"]) == ["0-203-1-001000", "0-203-1-002000"]
    for code in index["stations"]:
        recent = json.loads(
            (O2_FIXTURES / O2_CASES[f"chmu_recent_{code}"]["file"]).read_bytes()
        )
        table = rows(november, code)
        assert len(table) == 24
        for series in recent["objList"][0]["tsList"]:
            assert values(table, series["tsConID"]) == {
                datetime.fromisoformat(point["dt"]): point["value"]
                for point in series["tsData"]
                if point["dt"].endswith(":00:00Z")
            }
    index = document(january)
    assert (index["month"], index["tiers"], index["periods"]) == (
        "2025-01",
        ["verified", "operational"],
        [["2025-01-01", "2025-01-02"]],
    )
    table = rows(january, CHMU_CODE)
    assert len(table) == 48
    # The validated hours win where the recent answer differs; TH stays operational.
    for variable in ("H", "Q"):
        assert values(table, variable) == hourly[variable]
        assert set(tiers(table, variable).values()) == {"verified"}
    temperature = values(table, "T")
    assert temperature == {
        datetime(2025, 1, 1, hour, tzinfo=UTC): 3.5 for hour in range(24)
    }
    assert set(tiers(table, "T").values()) == {"operational"}
    assert index["stations"][CHMU_CODE]["variables"]["T"]["gaps"] == []
    meta = sidecar(january)
    assert (meta["tier"], meta["publication"]) == ("operational", "public")
    assert meta["extra"]["version"]["label"] == "2026-05-21"


# --------------------------------------------------------------------------
# The command: its options, its plan, the call of a month
# --------------------------------------------------------------------------


def test_command_for_version_of_a_month_builds_its_days_again(raw, data, clock):
    harvest_october(raw, clock)
    version = build_october(raw, data).months[0].version
    relative = version.parent.relative_to(data)

    call = command_for_version(relative, root=data, raw_root=raw)

    assert call == CommandCall(
        "series build",
        {
            "root": str(data),
            "raw_root": str(raw),
            "dataset": IMGW,
            "start": "2026-10-01",
            "end": "2026-10-31",
        },
        {},
    )
    station = version.parent / "stations" / f"{GLOGOW}.parquet"
    assert command_for_version(station, raw_root=raw) == call
    plan = check_command(call.command, options=call.options).result
    assert plan.series_state == {"imgw_hydro_subdaily/2026-10": "current"}


def test_check_series_plans_each_month_from_the_local_inputs(raw, data, clock):
    harvest_october(raw, clock)

    plan = check_series(data, raw_root=raw, dataset=IMGW)

    assert not data.exists()
    assert plan.series_state == {
        "imgw_hydro_subdaily/2026-10": "missing",
        "imgw_hydro_subdaily/2026-11": "missing",
    }
    assert [(action.command, action.status) for action in plan.actions] == [
        ("series build", "missing")
    ] * 2
    (item,) = plan.items
    assert (item.archive.dataset, item.status) == (OPERATIONAL, "current")
    assert (
        item.local_path.parent.parent.as_posix()
        == "archives/versions/station/hydro/2026-11-23"
    )
    build_series(data, raw_root=raw, dataset=IMGW)
    store_telemetry(raw)

    plan = check_series(data, raw_root=raw, dataset=IMGW)

    assert plan.series_state == {
        "imgw_hydro_subdaily/2026-10": "outdated",
        "imgw_hydro_subdaily/2026-11": "current",
    }
    assert [action.status for action in plan.actions] == ["newer", "current"]
    assert sorted(item.archive.dataset for item in plan.items) == [
        OPERATIONAL,
        TELEMETRY,
    ]
    given = check_series(
        data, raw_root=raw, dataset=IMGW, start=date(2026, 9, 1), end=date(2026, 9, 30)
    )
    assert given.series_state == {"imgw_hydro_subdaily/2026-09": "missing"}
    (action,) = given.actions
    assert action.status == "missing" and "2026-09" in action.detail


@pytest.mark.parametrize(
    ("dataset", "options", "option", "reason"),
    [
        (IMGW, {"stations": [GLOGOW]}, "stations", "monthly"),
        (CHMU, {"years": [2025]}, "years", "monthly"),
        ("pl.imgw.hydro_daily", {"start": date(2026, 10, 1)}, "start", "not_monthly"),
        ("cz.chmu.hydro_daily", {"end": date(2026, 10, 31)}, "end", "not_monthly"),
    ],
)
def test_series_build_refuses_the_options_of_the_other_kind_of_series(
    raw, data, dataset, options, option, reason
):
    calls = (
        lambda: build_series(data, raw_root=raw, dataset=dataset, **options),
        lambda: check_series(data, raw_root=raw, dataset=dataset, **options),
        lambda: validate_command(
            "series build",
            options={"root": data, "raw_root": raw, "dataset": dataset, **options},
        ),
    )
    for call in calls:
        with pytest.raises(ObserwatorValidationError) as exc:
            call()
        assert (exc.value.details["option"], exc.value.details["reason"]) == (
            option,
            reason,
        )
    assert not data.exists()


def test_the_months_of_series_build_run_forwards(raw, data):
    with pytest.raises(ObserwatorValidationError) as exc:
        build_series(
            data,
            raw_root=raw,
            dataset=IMGW,
            start=date(2026, 11, 1),
            end=date(2026, 10, 31),
        )

    assert exc.value.details["option"] == "end"


def test_the_hourly_series_are_built_by_series_build_never_synced_or_downloaded():
    hourly = {descriptor.key for descriptor in datasets() if monthly_series(descriptor)}
    choices = {
        command.name: set(option.choices or ())
        for command in data_commands()
        for option in command.options
        if option.name in ("dataset", "datasets")
    }

    assert hourly == {
        IMGW,
        CHMU,
        "pl.gdanskiewody.hydro_hourly",
        "pl.gdanskiewody.meteo_hourly",
    }
    assert hourly <= choices["series build"]
    for name in ("datasets files", "datasets download", "store check", "store sync"):
        assert not hourly & choices[name]
