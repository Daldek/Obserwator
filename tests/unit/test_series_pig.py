"""PIG-PIB's readings and hourly series (ADR-035 W7 to W9): values, hours, notices, products.

Plan tests 2 to 4, 11, 12 (the series' parts), 13, 17 and 18 of
``2026-11-24-pig-groundwater.md`` on the rows recorded from cbdgmapa.pgi.gov.pl on
2026-11-24 and 2026-11-25 (``pig_recordings.json``): the fixture variant
``groundwater_pl`` (`groundwater_pl_roots`) read as it is, and roots synchronized here
from `obserwator.testing._PigService` (``store sync``, the night's harvest of
``mwp_auto`` by watermark) and built (``series build``) to see what a build tells.
The run's, the spool's and the writer's clock is a fake one the pacing moves.
"""

import copy
import csv
import io
import json
from datetime import UTC, date, datetime, timedelta
from pathlib import PurePosixPath
from urllib.parse import parse_qsl
from zoneinfo import ZoneInfo

import httpx
import pyarrow.parquet as pq
import pytest
import respx

from obserwator.attribution import attribution
from obserwator.messages import message
from obserwator.store import (
    build_series,
    current_version,
    export_series,
    read_meta,
    read_series,
    summarize_series,
    sync_store,
)
from obserwator.testing import _PigService
from tests.contract.support import trailing_lines
from tests.unit.test_provider_pig import bodies, pace, roots

POINTS = "pl.pig.groundwater_stations"
READINGS = "pl.pig.groundwater_readings"
OPERATIONAL = "pl.pig.groundwater_operational"
SUBDAILY = "pl.pig.groundwater_subdaily"
LAST_ROW = 60938323
"""The newest OBJECTID of the recorded hourly rows."""
LINES = attribution("pig", period="2026", date="2026-11-24")
"""W, WP, P8's notice and RW of data of 2026 captured on 2026-11-24."""
WARSAW = ZoneInfo("Europe/Warsaw")


@pytest.fixture(autouse=True)
def clock(tmp_path, monkeypatch):
    return pace(tmp_path, monkeypatch)


@pytest.fixture
def service():
    return _PigService()


@pytest.fixture
def server(service):
    """PIG-PIB's services answer from the recorded rows; any other request fails."""
    with respx.mock(assert_all_called=False) as mock:
        mock.route(host="cbdgmapa.pgi.gov.pl").mock(side_effect=service)
        yield mock


def hourly_rows(service):
    return service.tables["mwp_auto/MapServer/2"].rows


def row_of(service, objectid):
    """A recorded hourly row by its OBJECTID."""
    return next(
        row for row in hourly_rows(service) if row["attributes"]["OBJECTID"] == objectid
    )


def epoch(stored):
    """The ``TIME`` mwp_auto answers for a stored UTC wall time: read as Warsaw's."""
    return int(stored.replace(tzinfo=WARSAW).timestamp() * 1000)


def harvest(raw, clock):
    """The night's harvest of ``mwp_auto`` into ``raw``: its day's new capture."""
    until = (clock.now() + timedelta(hours=1)).astimezone().strftime("%H:%M")
    (item,) = sync_store(raw, datasets=[OPERATIONAL], pace_until=until).items
    assert item.status == "new"
    return item.version


def hours(data, station, day):
    """A point's hourly depths of a day, by UTC hour (None: no value)."""
    rows = list(
        read_series(root=data, dataset=SUBDAILY, station=station, start=day, end=day)
    )
    assert {(row.time.minute, row.time.second) for row in rows} == {(0, 0)}
    return {row.time.hour: row.measurements["depth_to_water"].value for row in rows}


def reading(data, station, day):
    (row,) = read_series(
        root=data, dataset=READINGS, station=station, start=day, end=day
    )
    return {name: value.value for name, value in row.measurements.items()}


def month(report):
    """The month of a version of the hourly series: ``YYYY-MM``."""
    return report.version.parent.parent.name


# --------------------------------------------------------------------------
# The readings: depth, H_asl and yield at their own dates (tests 2 to 4)
# --------------------------------------------------------------------------


def test_a_depth_above_the_ground_stays_negative_and_lifts_h_asl_above_it(
    groundwater_pl_roots,
):
    rows = list(
        read_series(
            root=groundwater_pl_roots.data.root, dataset=READINGS, station="1934"
        )
    )

    # Jeleniów, an artesian bore whose ground lies at 413.9 m n.p.m.
    assert [
        (
            row.date,
            row.measurements["depth_to_water"].value,
            row.measurements["H_asl"].value,
        )
        for row in rows
    ] == [
        (date(2026, 10, 5), -5.64, 419.54),
        (date(2026, 10, 12), -5.39, 419.29),
        (date(2026, 10, 19), -5.27, 419.17),
        (date(2026, 10, 26), -5.28, 419.18),
    ]


def test_a_springs_yield_is_spring_yield_with_no_depth_or_level(
    groundwater_pl_roots,
):
    rows = list(
        read_series(
            root=groundwater_pl_roots.data.root, dataset=READINGS, station="1247"
        )
    )

    # Falsztyn, a spring at 637 m n.p.m.: no depth, so no level either.
    assert [
        (row.date, {name: m.value for name, m in row.measurements.items()})
        for row in rows
    ] == [
        (day, {"depth_to_water": None, "H_asl": None, "spring_yield": value})
        for day, value in (
            (date(2026, 10, 5), 0.45),
            (date(2026, 10, 12), 0.42),
            (date(2026, 10, 19), 0.4),
            (date(2026, 10, 26), 0.4),
        )
    ]


def test_a_reading_of_a_point_missing_from_the_points_stays_and_is_told(
    tmp_path, server
):
    raw, data = roots(tmp_path)
    sync_store(raw, datasets=[POINTS])
    sync_store(raw, datasets=[READINGS])
    notices = []

    report = build_series(
        data, raw_root=raw, dataset=READINGS, on_notice=notices.append
    )

    assert report.status == "new"
    # 9390 is in the readings, not in the points: no ground elevation, no H_asl.
    assert reading(data, "9390", date(2026, 10, 7)) == {
        "depth_to_water": None,
        "H_asl": None,
        "spring_yield": 3.63,
    }
    assert [n.message for n in notices if n.code == "station_unknown"] == [
        message("pig.station_unknown", count=1, codes="9390")
    ]


# --------------------------------------------------------------------------
# The time of mwp_auto: stored UTC wall times answered as Warsaw's (test 11)
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("point", "day", "value", "sixth", "other"),
    [
        # CET: the stored 06 is the epoch 05:00:02Z; the stored 07 (06:00:02Z) 1.983.
        ("757", date(2026, 10, 27), 1.97, 1.974, (7, 1.983)),
        # CEST: the stored 06 is 04:00:02Z; the stored 08 (06:00:02Z) 1.628.
        ("757", date(2026, 10, 15), 1.66, 1.658, (8, 1.628)),
        # CEST, the stored 06 at 04:00:04Z; the stored 08 0.876.
        ("6713", date(2026, 10, 18), 0.85, 0.848, (8, 0.876)),
    ],
)
def test_a_reading_of_06_utc_is_the_stored_hour_06_of_its_day(
    point, day, value, sixth, other, groundwater_pl_roots
):
    data = groundwater_pl_roots.data.root

    values = hours(data, point, day)

    assert reading(data, point, day)["depth_to_water"] == value
    assert (values[6], values[other[0]]) == (sixth, other[1])
    # Of the hours 04 to 08 only 06:00 UTC is the reading at its centimetre.
    assert [hour for hour in range(4, 9) if round(values[hour], 2) == value] == [6]


@pytest.mark.parametrize("ids", ["as recorded", "swapped"])
def test_the_two_rows_of_one_epoch_on_the_summer_time_day_are_01_and_02_by_their_page(
    ids, tmp_path, server, service, clock
):
    # 6495 on 2026-03-29: the stored 01:00:01 (3.18) and 02:00:01 (3.181) both come
    # back at 00:00:01Z.
    one, two = row_of(service, 55289214), row_of(service, 55305481)
    if ids == "swapped":
        # The row stored at 02:00 loaded first: the order of loading tells nothing.
        one["attributes"]["OBJECTID"], two["attributes"]["OBJECTID"] = (
            55305481,
            55289214,
        )
    raw, data = roots(tmp_path)
    harvest(raw, clock)

    build_series(data, raw_root=raw, dataset=SUBDAILY)

    values = hours(data, "6495", date(2026, 3, 29))
    assert [values[hour] for hour in range(4)] == [3.182, 3.18, 3.181, 3.181]
    assert None not in values.values() and len(values) == 24


def test_without_the_page_of_the_stored_hour_02_both_rows_leave_the_series_and_are_told(
    tmp_path, service, clock
):
    def refused(request):
        """The page of the stored hour 02 fails with ArcGIS's error object."""
        if dict(parse_qsl(request.read().decode())).get("where", "").startswith("TIME"):
            return httpx.Response(
                200, json={"error": {"code": 400, "message": "Unable to complete."}}
            )
        return service(request)

    raw, data = roots(tmp_path)
    with respx.mock(assert_all_called=False) as mock:
        mock.route(host="cbdgmapa.pgi.gov.pl").mock(side_effect=refused)
        harvest(raw, clock)
    notices = []

    build_series(data, raw_root=raw, dataset=SUBDAILY, on_notice=notices.append)

    values = hours(data, "6495", date(2026, 3, 29))
    assert (values[1], values[2]) == (None, None)
    assert None not in (values[hour] for hour in (0, *range(3, 24)))
    assert [n.message for n in notices if n.code == "hour_unresolved"] == [
        message("pig.hour_unresolved", count=1, days="2026-03-29")
    ]


def test_the_day_summer_time_ends_has_24_hours_each_with_its_value(
    groundwater_pl_roots,
):
    values = hours(groundwater_pl_roots.data.root, "757", date(2026, 10, 25))

    # The stored 02:00 comes back once, in the hour Warsaw's clocks repeat.
    assert sorted(values) == list(range(24))
    assert (values[1], values[2], values[3]) == (1.808, 1.807, 1.806)
    assert None not in values.values()


# --------------------------------------------------------------------------
# The harvest's rows in the hourly series (tests 12 and 13)
# --------------------------------------------------------------------------


def test_a_late_row_of_an_earlier_month_rebuilds_that_months_version_alone(
    tmp_path, server, service, clock
):
    raw, data = roots(tmp_path)
    harvest(raw, clock)
    build_series(data, raw_root=raw, dataset=SUBDAILY)
    # The next night brings 6495's row stored at 2026-03-30 00:00:01 (CEST): loaded
    # after the last harvest, eight months after its hour.
    late = copy.deepcopy(row_of(service, 55289213))
    late["attributes"].update(
        OBJECTID=LAST_ROW + 1, TIME=epoch(datetime(2026, 3, 30, 0, 0, 1)), VALUE=3.2
    )
    del late["attributes"]["_stored"]
    hourly_rows(service).append(late)
    clock.moment += timedelta(days=1)
    harvest(raw, clock)

    rebuilt = build_series(data, raw_root=raw, dataset=SUBDAILY)

    assert {month(item): item.status for item in rebuilt.months} == {
        "2026-03": "new",
        "2026-10": "unchanged",
        "2026-11": "unchanged",
    }
    assert hours(data, "6495", date(2026, 3, 30))[0] == 3.2


def test_rows_of_one_hour_count_once_when_equal_else_the_later_one_with_a_notice(
    tmp_path, server, clock
):
    raw, data = roots(tmp_path)
    harvest(raw, clock)
    notices = []

    build_series(data, raw_root=raw, dataset=SUBDAILY, on_notice=notices.append)

    day = date(2026, 11, 23)
    valued = {
        point: {
            hour: value
            for hour, value in hours(data, point, day).items()
            if value is not None
        }
        for point in ("9830", "9312")
    }
    # 9830: 60910332 and 60923482, 3.543 both, stored at 00:00:00. 9312: 4.81
    # (60920525, stored 22:00:01) and 4.809 (60920526, stored 22:21:22).
    assert valued == {"9830": {0: 3.543}, "9312": {22: 4.809}}
    assert [n.message for n in notices if n.code == "hour_revised"] == [
        message(
            "pig.hour_revised",
            count=1,
            month="2026-11",
            point="9312",
            hour="2026-11-23T22:00Z",
        )
    ]


def test_a_row_after_its_answer_stays_in_the_capture_and_leaves_the_series_told_once(
    tmp_path, server, clock
):
    raw, data = roots(tmp_path)
    capture = harvest(raw, clock)
    notices = []

    report = build_series(
        data, raw_root=raw, dataset=SUBDAILY, on_notice=notices.append
    )

    # 2405's row stored at 2136-02-07 07:28:15.
    kept = [
        (feature["attributes"]["OBJECTID"], feature["attributes"]["VALUE"])
        for body in bodies(capture)
        for feature in body.get("features", ())
        if feature["attributes"].get("PSH_MONITORING_ID") == 2405
    ]
    assert kept == [(58035369, 2.172)]
    assert sorted(month(item) for item in report.months) == [
        "2026-03",
        "2026-10",
        "2026-11",
    ]
    assert not [
        item
        for item in report.months
        if "2405" in json.loads(item.version.read_text(encoding="utf-8"))["stations"]
    ]
    assert [n.message for n in notices if n.code == "hour_future"] == [
        message("pig.hour_future", count=1)
    ]


# --------------------------------------------------------------------------
# Series read and export (tests 17 and 18)
# --------------------------------------------------------------------------


def test_the_readings_have_rows_at_their_dates_only(groundwater_pl_roots):
    data = groundwater_pl_roots.data.root
    mondays = [date(2026, 10, day) for day in (5, 12, 19, 26)]

    found = {
        station: [
            row.date
            for row in read_series(root=data, dataset=READINGS, station=station)
        ]
        for station in ("6495", "853", "1247")
    }

    assert found == {
        "6495": [date(2026, 10, day) for day in range(1, 32)],  # automatic bore
        "853": mondays,  # a bore read on Mondays
        "1247": mondays,  # a spring
    }


def test_a_calendar_week_without_a_reading_is_a_gap_and_a_day_without_one_is_not(
    tmp_path, server, service
):
    service.tables["mwp/MapServer/1"].rows[:] = [
        row
        for row in service.tables["mwp/MapServer/1"].rows
        if (row["attributes"]["OTWOR_ID"], row["attributes"]["DATA_POMIARU"])
        not in {(853, " 2026-10-12"), (6495, " 2026-10-14")}
    ]
    raw, data = roots(tmp_path)
    sync_store(raw, datasets=[READINGS])

    build_series(data, raw_root=raw, dataset=READINGS)

    coverage = {
        item.station_code: item
        for item in summarize_series(
            root=data, dataset=READINGS, stations=["853", "6495"]
        )
        if item.variable == "depth_to_water"
    }
    weekly, daily = coverage["853"], coverage["6495"]
    # The week of Monday 12 October has no reading of the bore read on Mondays.
    assert (weekly.first, weekly.last, weekly.gaps) == (
        date(2026, 10, 5),
        date(2026, 10, 26),
        ((date(2026, 10, 12), date(2026, 10, 12)),),
    )
    # Wednesday 14 October is missing, but its week has six readings.
    assert (daily.first, daily.last, daily.gaps) == (
        date(2026, 10, 1),
        date(2026, 10, 31),
        (),
    )


def test_a_readings_export_carries_w_wp_and_rw_in_the_csv_and_parquet(
    groundwater_pl_roots, tmp_path
):
    options = {
        "root": groundwater_pl_roots.data.root,
        "dataset": READINGS,
        "station": "853",
    }

    table = list(csv.DictReader(io.StringIO("".join(export_series(**options)))))
    report = export_series(**options, format="parquet", output=tmp_path / "853.parquet")

    assert list(table[0])[-2:] == ["attribution", "terms_notice"]
    assert trailing_lines(table) == LINES
    metadata = {
        key.decode(): value.decode()
        for key, value in pq.read_schema(report.output).metadata.items()
    }
    assert {
        key: json.loads(metadata[key]) for key in ("attribution", "terms_notice")
    } == LINES.fields()


def test_the_hourly_series_of_an_automatic_bore_is_operational_and_apart_from_readings(
    groundwater_pl_roots,
):
    data = groundwater_pl_roots.data.root
    november = {"start": date(2026, 11, 1), "end": date(2026, 11, 30)}

    hourly = list(read_series(root=data, dataset=SUBDAILY, station="6495", **november))
    table = list(
        csv.DictReader(
            io.StringIO(
                "".join(
                    export_series(
                        root=data, dataset=SUBDAILY, station="6495", **november
                    )
                )
            )
        )
    )
    readings = current_version(data, slot=f"series:{READINGS}").version

    # Every hour of 23 November, the stored day of the night's capture.
    assert [row.time for row in hourly] == [
        datetime(2026, 11, 23, hour, tzinfo=UTC) for hour in range(24)
    ]
    assert {value.tier for row in hourly for value in row.measurements.values()} == {
        "operational"
    }
    assert {name: m.value for name, m in hourly[6].measurements.items()} == {
        "depth_to_water": 3.618,
        "H_asl": 166.88,
    }
    assert trailing_lines(table) == LINES
    # The readings series reads the points and the readings, never the captures.
    assert [
        PurePosixPath(source["file"]).parent.parent.as_posix()
        for source in read_meta(readings).extra["source_files"]
    ] == [
        "archives/versions/mwp/MapServer/0/MWP_points",
        "archives/versions/mwp/MapServer/1/MWP_2026-10",
    ]
