"""
Gdańskie Wody's series built from its stored month files (ADR-034 D8), offline.

Each month file is stored as a sync stores it: `encode_month` of the answers of its days,
``rest/measurements/<no>/<symbol>/<YYYY-MM>.json``, here the recorded answers of
2026-11-01..03 (``gdanskiewody_recordings.json``), so November is a month asked on
2026-11-03, while it runs. The daily series hold the provider's day (06:00 to 05:59
UTC, plan P5), the hourly series each hour at the UTC start of its label (D4).
"""

import json
import math
from datetime import UTC, date, datetime, timedelta
from pathlib import PurePosixPath

import pyarrow.parquet as pq
import pytest

from obserwator._parsing.gdanskiewody import encode_month
from obserwator.datasets import _archive_from_path
from obserwator.fetch import DownloadResult
from obserwator.store import build_series, check_series, init_store, write_archive
from obserwator.testing import fixture_files

RECORDINGS = json.loads(
    fixture_files().joinpath("gdanskiewody_recordings.json").read_text(encoding="utf-8")
)
ANSWERS = {item["case"]: item["json"] for item in RECORDINGS["interactions"]}
MEASUREMENTS = "pl.gdanskiewody.measurements"
HYDRO_DAILY = "pl.gdanskiewody.hydro_daily"
METEO_DAILY = "pl.gdanskiewody.meteo_daily"
HYDRO_HOURLY = "pl.gdanskiewody.hydro_hourly"
METEO_HOURLY = "pl.gdanskiewody.meteo_hourly"
DAYS = (date(2026, 11, 1), date(2026, 11, 2), date(2026, 11, 3))
# The recorded quantities of each station (91's rain and the other stations of the list
# have no recorded day).
RECORDED = {
    1: ("rain",),
    4: ("water",),
    7: ("rain", "water"),
    91: ("temp", "humidity", "pressure", "sun", "winddir", "windlevel"),
    504: ("water", "flow"),
    700: ("watertemp", "conductivity"),
}
# The variable of a quantity in the daily and the hourly series.
DAILY = {
    "rain": "P",
    "water": "H_asl",
    "flow": "Q",
    "watertemp": "T",
    "temp": "Tmean",
    "windlevel": "wind_speed",
    "pressure": "pressure",
    "humidity": "humidity",
    "sun": "irradiance",
}
HOURLY = {**DAILY, "temp": "Tair", "winddir": "wind_direction"}
# The files each series reads: the water quality none, the rain of 7 (a hydrological
# station) the meteorological series, the wind's direction the hourly one only.
HYDRO_FILES = ("4/water", "7/water", "504/water", "504/flow", "700/watertemp")
METEO_DAILY_FILES = (
    "1/rain",
    "7/rain",
    "91/temp",
    "91/humidity",
    "91/pressure",
    "91/sun",
    "91/windlevel",
)
METEO_HOURLY_FILES = (*METEO_DAILY_FILES, "91/winddir")


@pytest.fixture(autouse=True)
def config(tmp_path, monkeypatch):
    """An empty ``nogat.toml``: the provider's sources keep their default publication."""
    path = tmp_path / "nogat.toml"
    path.write_text("", encoding="utf-8")
    monkeypatch.setenv("NOGAT_CONFIG", str(path))


@pytest.fixture
def raw(tmp_path):
    return init_store(tmp_path / "raw").root


@pytest.fixture
def data(tmp_path):
    return tmp_path / "data"


def code(number):
    return f"GDANSKIEWODY-{number}"


def recorded(number, symbol):
    """The recorded answers of 2026-11-01..03 of a station's quantity, by day."""
    return {day: ANSWERS[f"m_{number}_{symbol}_{day:%Y%m%d}"] for day in DAYS}


def answer(day, values):
    """A provider's day answered: its 24 values labelled from 06:00 UTC of ``day``."""
    start = datetime(day.year, day.month, day.day, 6)
    return {
        "status": "success",
        "message": "",
        "data": [
            [f"{start + timedelta(hours=step):%Y-%m-%d %H:%M:%S}", value]
            for step, value in enumerate(values)
        ],
    }


def store(raw, number, symbol, answers):
    """Store the file of one month's answers as a sync stores a month not settled."""
    month = min(answers)
    archive = _archive_from_path(
        MEASUREMENTS, f"rest/measurements/{number}/{symbol}/{month:%Y-%m}.json"
    )
    content = encode_month(answers)
    response = DownloadResult(content, archive.url, None, None, len(content))
    return write_archive(raw, archive=archive, response=response)


def store_recorded(raw):
    for number, symbols in RECORDED.items():
        for symbol in symbols:
            store(raw, number, symbol, recorded(number, symbol))


def hours(answers):
    """The hours of the answers: {UTC hour its label names: value}."""
    return {
        datetime.fromisoformat(label).replace(tzinfo=UTC): value
        for body in answers.values()
        for label, value in body["data"]
    }


def daily(answers, statistic):
    """The provider's days of answers without a null: the rounded sum or mean."""
    found = {}
    for day, body in answers.items():
        total = math.fsum(value for _, value in body["data"])
        found[day] = round(total if statistic == "sum" else total / 24, 3)
    return found


def document(version):
    return json.loads(version.read_text(encoding="utf-8"))


def sidecar(version):
    meta = version.with_name("series.json.meta.json")
    return json.loads(meta.read_text(encoding="utf-8"))


def table(version, number):
    path = version.parent / "stations" / f"{code(number)}.parquet"
    return pq.read_table(path).to_pylist()


def values(rows, variable, key="date"):
    """The rows of a variable with a value: {date or hour: value}."""
    return {
        row[key]: row[f"{variable}_value"]
        for row in rows
        if row[f"{variable}_flag"] == "value"
    }


def flags(rows, variable):
    return {row["date"]: row[f"{variable}_flag"] for row in rows}


def files(paths):
    """The month files of input versions: ``<no>/<symbol>/<YYYY-MM>``."""
    found = []
    for path in paths:
        number, symbol, name = PurePosixPath(path).parts[-5:-2]
        found.append(f"{number}/{symbol}/{name.removesuffix('.json')}")
    return sorted(found)


def of_november(names):
    """The November files of ``<no>/<symbol>`` names, as `files` gives them."""
    return sorted(f"{name}/2026-11" for name in names)


# --------------------------------------------------------------------------
# The daily series of the provider's day
# --------------------------------------------------------------------------


def test_the_meteo_daily_series_holds_the_provider_days_of_its_quantities(raw, data):
    store_recorded(raw)

    report = build_series(data, raw_root=raw, dataset=METEO_DAILY)

    assert (report.status, report.stations, report.problems) == ("new", 3, ())
    assert files(report.source_files) == of_november(METEO_DAILY_FILES)
    index = document(report.version)
    assert sorted(index["stations"]) == [code(1), code(7), code(91)]
    # The precipitation of 7, a hydrological station, lies in the meteorological series.
    for number in (1, 7):
        rows = table(report.version, number)
        assert values(rows, "P") == daily(recorded(number, "rain"), "sum")
        assert values(rows, "Tmean") == {}
    rows = table(report.version, 91)
    for symbol in ("temp", "windlevel", "pressure", "humidity", "sun"):
        assert values(rows, DAILY[symbol]) == daily(recorded(91, symbol), "mean")
    assert values(rows, "P") == {}
    # A sum and means of the 24 hours from 06:00 UTC, to three decimals.
    assert values(table(report.version, 1), "P")[date(2026, 11, 3)] == 1.007
    assert values(rows, "Tmean")[date(2026, 11, 1)] == 7.242
    assert values(rows, "humidity")[date(2026, 11, 2)] == 92.596


def test_the_hydro_daily_series_claims_only_the_days_a_running_month_holds(raw, data):
    store_recorded(raw)

    report = build_series(data, raw_root=raw, dataset=HYDRO_DAILY)

    assert (report.status, report.stations) == ("new", 4)
    assert files(report.source_files) == of_november(HYDRO_FILES)
    index = document(report.version)
    expected = {
        4: {"H_asl": daily(recorded(4, "water"), "mean")},
        7: {"H_asl": daily(recorded(7, "water"), "mean")},
        504: {
            "H_asl": daily(recorded(504, "water"), "mean"),
            "Q": daily(recorded(504, "flow"), "mean"),
        },
        700: {"T": daily(recorded(700, "watertemp"), "mean")},
    }
    assert sorted(index["stations"]) == sorted(code(number) for number in expected)
    for number, variables in expected.items():
        rows = table(report.version, number)
        assert len(rows) == 3
        for variable in ("H_asl", "Q", "T"):
            assert values(rows, variable) == variables.get(variable, {})
        # The month asked on 2026-11-03 is known to that day, not to its end.
        assert index["stations"][code(number)]["periods"] == [
            ["2026-11-01", "2026-11-03"]
        ]
    assert values(table(report.version, 4), "H_asl")[date(2026, 11, 1)] == 4.893
    assert index["periods"] == [["2026-11-01", "2026-11-03"]]
    meta = sidecar(report.version)
    assert (meta["request"], meta["tier"]) == ({"dataset": HYDRO_DAILY}, "operational")


def test_a_rebuild_is_unchanged_and_a_month_asked_again_extends_its_days(raw, data):
    store_recorded(raw)
    first = build_series(data, raw_root=raw, dataset=HYDRO_DAILY)
    tree = sorted(data.rglob("*"))

    again = build_series(data, raw_root=raw, dataset=HYDRO_DAILY)

    assert (again.status, again.version) == ("unchanged", first.version)
    assert sorted(data.rglob("*")) == tree
    # Station 4's month asked again on 2026-11-25 at 03:45 UTC (the days between are
    # not recorded): the provider's day of 2026-11-24 still ran, two hours null.
    running = ANSWERS["m_4_water_20261124_at_034500"]
    assert [value for _, value in running["data"][-2:]] == [None, None]
    store(raw, 4, "water", {**recorded(4, "water"), date(2026, 11, 24): running})

    later = build_series(data, raw_root=raw, dataset=HYDRO_DAILY)

    assert later.status == "new" and later.version != first.version
    rows = table(later.version, 4)
    assert flags(rows, "H_asl")[date(2026, 11, 24)] == "missing"
    assert values(rows, "H_asl") == daily(recorded(4, "water"), "mean")
    index = document(later.version)
    assert index["stations"][code(4)]["periods"] == [["2026-11-01", "2026-11-24"]]
    assert index["stations"][code(7)]["periods"] == [["2026-11-01", "2026-11-03"]]
    assert index["periods"] == [["2026-11-01", "2026-11-24"]]


def test_a_subset_holds_its_stations_as_the_full_series_does(raw, tmp_path):
    store_recorded(raw)
    full = build_series(tmp_path / "full", raw_root=raw, dataset=HYDRO_DAILY)

    part = build_series(
        tmp_path / "part", raw_root=raw, dataset=HYDRO_DAILY, stations=[code(504)]
    )
    year = build_series(
        tmp_path / "year", raw_root=raw, dataset=HYDRO_DAILY, years=[2026]
    )
    other = build_series(
        tmp_path / "other", raw_root=raw, dataset=HYDRO_DAILY, years=[2025]
    )

    assert (part.status, part.stations) == ("new", 1)
    assert files(part.source_files) == of_november(["504/water", "504/flow"])
    whole, subset = document(full.version), document(part.version)
    assert subset["stations"] == {code(504): whole["stations"][code(504)]}
    assert subset["subset"] == {"stations": [code(504)]}
    assert table(part.version, 504) == table(full.version, 504)
    assert (year.status, year.stations) == ("new", 4)
    assert document(year.version)["stations"] == whole["stations"]
    assert (other.status, other.version, other.source_files) == ("failed", None, ())


@pytest.mark.parametrize(
    ("dataset", "names", "slot"),
    [
        (HYDRO_DAILY, HYDRO_FILES, "gdanskiewody_hydro_daily"),
        (METEO_DAILY, METEO_DAILY_FILES, "gdanskiewody_meteo_daily"),
        (HYDRO_HOURLY, HYDRO_FILES, "gdanskiewody_hydro_hourly/2026-11"),
        (METEO_HOURLY, METEO_HOURLY_FILES, "gdanskiewody_meteo_hourly/2026-11"),
    ],
)
def test_check_series_plans_a_series_from_the_files_it_reads(
    raw, data, dataset, names, slot
):
    store_recorded(raw)

    plan = check_series(data, raw_root=raw, dataset=dataset)

    assert not data.exists()
    assert plan.series_state == {slot: "missing"}
    assert [action.status for action in plan.actions] == ["missing"]
    assert files(item.local_path for item in plan.items) == of_november(names)
    assert {item.status for item in plan.items} == {"current"}
    report = build_series(data, raw_root=raw, dataset=dataset)
    assert files(report.source_files) == of_november(names)
    plan = check_series(data, raw_root=raw, dataset=dataset)
    assert plan.series_state == {slot: "current"}
    assert [action.status for action in plan.actions] == ["current"]


def test_an_unreadable_month_file_fails_only_the_series_that_read_it(raw, data):
    store_recorded(raw)
    # A later version of station 7's rain that is no month file.
    archive = _archive_from_path(MEASUREMENTS, "rest/measurements/7/rain/2026-11.json")
    response = DownloadResult(b"[]\n", archive.url, None, None, 3)
    write_archive(raw, archive=archive, response=response)

    reports = {
        dataset: build_series(data, raw_root=raw, dataset=dataset)
        for dataset in (HYDRO_DAILY, HYDRO_HOURLY, METEO_DAILY, METEO_HOURLY)
    }

    for dataset in (HYDRO_DAILY, HYDRO_HOURLY):
        assert (reports[dataset].status, reports[dataset].problems) == ("new", ())
    for dataset in (METEO_DAILY, METEO_HOURLY):
        assert reports[dataset].status == "failed"
        assert reports[dataset].problems
        for problem in reports[dataset].problems:
            assert "rest/measurements/7/rain/2026-11.json" in problem


def test_without_a_file_it_reads_a_daily_series_names_the_dataset_to_sync(raw, data):
    # Only water quality: a file no series reads.
    store(raw, 700, "conductivity", recorded(700, "conductivity"))

    report = build_series(data, raw_root=raw, dataset=HYDRO_DAILY)
    plan = check_series(data, raw_root=raw, dataset=HYDRO_DAILY)

    assert (report.status, report.version, report.source_files) == ("failed", None, ())
    (problem,) = report.problems
    assert MEASUREMENTS in problem
    assert (plan.series_state, plan.items) == (
        {"gdanskiewody_hydro_daily": "missing"},
        (),
    )
    state, missing = plan.actions
    assert (state.status, missing.status, missing.detail) == (
        "missing",
        "missing",
        problem,
    )


# --------------------------------------------------------------------------
# The hourly series, one version per month
# --------------------------------------------------------------------------


def test_the_hourly_series_holds_every_hour_at_the_start_of_its_label(raw, data):
    store_recorded(raw)

    report = build_series(data, raw_root=raw, dataset=HYDRO_HOURLY)

    # The hours from 2026-11-01 06:00 to 2026-11-04 05:00 UTC: November alone.
    (month,) = report.months
    assert (report.status, month.status, report.stations) == ("new", "new", 4)
    version = month.version
    assert version.parent.parent == (
        data / "series" / "versions" / "gdanskiewody_hydro_hourly" / "2026-11"
    )
    index = document(version)
    assert (index["month"], index["tiers"], index["periods"]) == (
        "2026-11",
        ["operational"],
        [["2026-11-01", "2026-11-04"]],
    )
    start = datetime(2026, 11, 1, tzinfo=UTC)
    for number, symbols in (
        (4, ("water",)),
        (7, ("water",)),
        (504, ("water", "flow")),
        (700, ("watertemp",)),
    ):
        rows = table(version, number)
        assert [row["time"] for row in rows] == [
            start + timedelta(hours=step) for step in range(96)
        ]
        for symbol in symbols:
            given = hours(recorded(number, symbol))
            assert len(given) == 72
            assert values(rows, HOURLY[symbol], "time") == given
    meta = sidecar(version)
    assert (meta["request"], meta["tier"]) == (
        {"dataset": HYDRO_HOURLY, "month": "2026-11"},
        "operational",
    )
    meteo = build_series(data, raw_root=raw, dataset=METEO_HOURLY)
    (month,) = meteo.months
    assert sorted(document(month.version)["stations"]) == [code(1), code(7), code(91)]
    assert values(table(month.version, 7), "P", "time") == hours(recorded(7, "rain"))
    # An hour answered null has no value.
    directions = hours(recorded(91, "winddir"))
    assert values(table(month.version, 91), "wind_direction", "time") == {
        moment: value for moment, value in directions.items() if value is not None
    }


def test_the_last_provider_day_of_a_month_ends_in_the_next_months_version(raw, data):
    # October's file holding its last provider day (the days before not given), which
    # runs to 05:00 UTC of November's first day, and November's.
    last = answer(date(2026, 10, 31), [4.8 + step / 100 for step in range(24)])
    store(raw, 4, "water", {date(2026, 10, 31): last})
    store(raw, 4, "water", recorded(4, "water"))

    report = build_series(data, raw_root=raw, dataset=HYDRO_HOURLY)
    days = build_series(data, raw_root=raw, dataset=HYDRO_DAILY)

    october, november = report.months
    assert [month.version.parent.parent.name for month in report.months] == [
        "2026-10",
        "2026-11",
    ]
    given = hours({date(2026, 10, 31): last})
    late = {moment: value for moment, value in given.items() if moment.month == 11}
    assert sorted(late) == [
        datetime(2026, 11, 1, hour, tzinfo=UTC) for hour in range(6)
    ]
    assert values(table(october.version, 4), "H_asl", "time") == {
        moment: value for moment, value in given.items() if moment.month == 10
    }
    assert values(table(november.version, 4), "H_asl", "time") == {
        **late,
        **hours(recorded(4, "water")),
    }
    assert files(october.source_files) == ["4/water/2026-10"]
    assert files(november.source_files) == ["4/water/2026-10", "4/water/2026-11"]
    # In the daily series the provider's day is October's last.
    rows = table(days.version, 4)
    assert values(rows, "H_asl") == {
        date(2026, 10, 31): round(math.fsum(given.values()) / 24, 3),
        **daily(recorded(4, "water"), "mean"),
    }
    assert document(days.version)["stations"][code(4)]["periods"] == [
        ["2026-10-31", "2026-11-03"]
    ]
