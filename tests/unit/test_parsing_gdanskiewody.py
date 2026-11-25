"""Gdańskie Wody's parsers (ADR-034): the station list, a day's hours, the month files.

The answers are those of ``gdanskiewody_recordings.json`` (recorded on 2026-11-25: eight
stations, the days 2026-11-01 to 2026-11-03 of their quantities, one day asked while
its hour ran); the others are built here in the provider's layout.
"""

import json
import math
import random
from datetime import UTC, date, datetime, timedelta

import pytest

from obserwator._parsing.gdanskiewody import (
    daily_records,
    day_points,
    encode_month,
    hourly_points,
    read_month,
    read_stations,
    station_number,
)
from obserwator.exceptions import ObserwatorDataError
from obserwator.models import Measurement
from obserwator.parsers import parse_gdanskiewody_month, parse_gdanskiewody_stations
from obserwator.testing import _interactions

CASES = _interactions(("gdanskiewody_recordings.json",))
NOVEMBER = (date(2026, 11, 1), date(2026, 11, 2), date(2026, 11, 3))
DAY = date(2026, 11, 2)


def answer(case):
    """The JSON of a recorded answer."""
    return CASES[case]["json"]


def body(case):
    """The bytes of a recorded answer, as the provider sent them."""
    return json.dumps(answer(case), ensure_ascii=False).encode("utf-8")


def month(station, symbol, days=NOVEMBER):
    """The month file of a station's quantity gathered from its recorded days."""
    return encode_month(
        {day: answer(f"m_{station}_{symbol}_{day:%Y%m%d}") for day in days}
    )


def hours(day, values):
    """A successful answer of the provider's ``day``: labels from 06:00 on."""
    start = datetime(day.year, day.month, day.day, 6)
    return {
        "status": "success",
        "message": "Pomiary",
        "data": [
            [f"{start + timedelta(hours=offset):%Y-%m-%d %H:%M:%S}", value]
            for offset, value in enumerate(values)
        ],
    }


def row(no=1, **fields):
    """A station of the list: a rain gauge unless ``fields`` say otherwise."""
    station = {"no": no, "name": "Stacja", "lat": "54.35", "long": "18.65"}
    return station | {"active": True, "rain": True} | fields


def station_list(*rows):
    """A successful answer of ``rest/stations`` with ``rows``."""
    return json.dumps(
        {"status": "success", "message": "Lista stacji", "data": list(rows)}
    ).encode()


def second(**fields):
    """A list whose second station has ``fields``."""
    return station_list(row(1), row(2) | fields)


def daily(day, values, symbol):
    """The measurements of the one record of a file holding ``day``."""
    (record,) = daily_records(
        encode_month({day: hours(day, values)}),
        dataset="pl.gdanskiewody.meteo_daily",
        station="GDANSKIEWODY-1",
        symbol=symbol,
        filename="rest/measurements/1/x/2026-11.json",
    )
    return record.measurements


# --------------------------------------------------------------------------
# The station list
# --------------------------------------------------------------------------


def test_the_recorded_list_gives_each_station_its_family_quantities_and_point():
    stations = read_stations(body("stations"))
    by_number = {station.number: station for station in stations}

    assert [(s.number, s.code, s.kind) for s in stations] == [
        (1, "GDANSKIEWODY-1", "meteo"),
        (2, "GDANSKIEWODY-2", "meteo"),
        (4, "GDANSKIEWODY-4", "hydro"),
        # A rain gauge beside a water-level gauge: a hydrological station.
        (7, "GDANSKIEWODY-7", "hydro"),
        (91, "GDANSKIEWODY-91", "meteo"),
        (504, "GDANSKIEWODY-504", "hydro"),
        (700, "GDANSKIEWODY-700", "hydro"),
        (999, "GDANSKIEWODY-999", "hydro"),
    ]
    assert by_number[7].quantities == ("rain", "water")
    assert by_number[700].quantities == (
        "turbidity",
        "dissolvedoxygen",
        "redox",
        "ph",
        "conductivity",
        "watertemp",
    )
    assert by_number[91].name == "Sopot opad - ul. Mikołaja Reja 25"
    # The point as published (its decimals give its uncertainty); none for "".
    assert (by_number[504].latitude, by_number[504].longitude) == (
        "54.553450",
        "18.442623",
    )
    assert (by_number[700].latitude, by_number[700].longitude) == (None, None)
    assert all(station.active for station in stations)

    entries = parse_gdanskiewody_stations(body("stations"))

    assert [(e.station_code, e.kind) for e in entries] == [
        (s.code, s.kind) for s in stations
    ]
    assert {entry.provider for entry in entries} == {"GDANSKIEWODY"}
    assert (entries[0].name, entries[0].latitude, entries[0].longitude) == (
        "Dolne Miasto",
        54.33604,
        18.66171,
    )
    assert (entries[6].latitude, entries[6].longitude) == (None, None)


def test_quantities_follow_the_order_of_the_table_then_unknown_symbols():
    listed = row(rain=False, salinity=True, watertemp=True, temp=True, water=True)

    (station,) = read_stations(station_list(listed | {"alpha": True}))

    assert station.quantities == ("water", "temp", "watertemp", "salinity", "alpha")


@pytest.mark.parametrize(
    ("fields", "kind"),
    [
        ({}, "meteo"),
        ({"rain": False}, "meteo"),
        ({"rain": False, "salinity": True}, "meteo"),
        ({"temp": True, "winddir": True}, "meteo"),
        ({"flow": True}, "hydro"),
        ({"rain": False, "turbidity": True}, "hydro"),
        ({"rain": False, "watertemp": True}, "hydro"),
    ],
)
def test_a_station_is_hydrological_when_it_measures_any_hydrological_quantity(
    fields, kind
):
    (station,) = read_stations(station_list(row(**fields)))

    assert station.kind == kind


def test_a_number_given_twice_keeps_its_first_row_and_both_are_checked():
    stations = read_stations(
        station_list(
            row(1, name="Pierwsza"),
            row(2),
            row(1, name="Druga", rain=False, water=True, lat="", long=""),
        )
    )

    assert [(s.number, s.name, s.kind, s.latitude) for s in stations] == [
        (1, "Pierwsza", "meteo", "54.35"),
        (2, "Stacja", "meteo", "54.35"),
    ]
    with pytest.raises(ObserwatorDataError) as caught:
        read_stations(station_list(row(1), row(1, lat="x")), filename="rest/stations")
    assert "rest/stations cannot be read at $.data[1].lat:" in str(caught.value)


@pytest.mark.parametrize(
    ("content", "where"),
    [
        (b"{", "$"),
        (b"[]", "$"),
        (
            json.dumps({"status": "error", "code": -100, "message": "Błąd"}).encode(),
            "$.status",
        ),
        (json.dumps({"status": "success", "data": {}}).encode(), "$.data"),
        (station_list(row(1), 2), "$.data[1]"),
        (station_list(row(1), {"name": "Bez numeru", "active": True}), "$.data[1].no"),
        (second(no=True), "$.data[1].no"),
        (second(no="2"), "$.data[1].no"),
        (second(no=2.0), "$.data[1].no"),
        (second(no=0), "$.data[1].no"),
        (second(no=1000), "$.data[1].no"),
        (second(name=" "), "$.data[1].name"),
        (second(name=None), "$.data[1].name"),
        (second(active="true"), "$.data[1].active"),
        (second(rain=1), "$.data[1].rain"),
        (second(lat="54,35"), "$.data[1].lat"),
        (second(lat=54.35), "$.data[1].lat"),
        (second(long="nan"), "$.data[1].long"),
        (second(long="inf"), "$.data[1].long"),
    ],
)
def test_every_content_error_of_the_list_names_its_place(content, where):
    with pytest.raises(ObserwatorDataError) as caught:
        read_stations(content, filename="rest/stations")

    assert caught.value.code == "data_error"
    assert f"rest/stations cannot be read at {where}:" in str(caught.value)


# --------------------------------------------------------------------------
# A day's hours
# --------------------------------------------------------------------------


def test_a_recorded_day_runs_from_six_to_five_the_next_morning_in_utc():
    points = day_points(answer("m_1_rain_20261102"), DAY, filename="m.json")

    start = datetime(2026, 11, 2, 6, tzinfo=UTC)
    assert [moment for moment, _ in points] == [
        start + timedelta(hours=offset) for offset in range(24)
    ]
    assert points[-1][0] == datetime(2026, 11, 3, 5, tzinfo=UTC)
    # Integers and decimals both become floats.
    assert [value for _, value in points[4:8]] == [0.0, 0.004, 0.038, 0.087]
    assert all(type(value) is float for _, value in points)


def test_a_missing_hour_is_none():
    points = day_points(answer("m_91_winddir_20261102"), DAY, filename="m.json")
    values = [value for _, value in points]

    assert values[:7] == [None, None, None, 225.0, 225.0, 202.5, None]
    assert values[-2:] == [225.0, 180.0]
    assert values.count(None) == 16


@pytest.mark.parametrize(
    "label", ["2026-11-02 05:00:00", "2026-11-03 06:00:00", "2026-11-01 12:00:00"]
)
def test_a_label_outside_the_providers_day_is_refused(label):
    first, last = "2026-11-02 06:00:00", "2026-11-03 05:00:00"
    accepted = {"status": "success", "data": [[first, 1], [last, 2]]}
    assert len(day_points(accepted, DAY, filename="m.json")) == 2

    with pytest.raises(ObserwatorDataError) as caught:
        day_points(
            {"status": "success", "data": [[first, 1], [label, 1]]},
            DAY,
            filename="m.json",
        )

    text = str(caught.value)
    assert "m.json cannot be read at $.2026-11-02.data[1][0]:" in text
    assert "outside the provider's day 2026-11-02" in text


@pytest.mark.parametrize(
    ("pair", "where"),
    [
        ("2026-11-02 06:00:00", ""),
        (["2026-11-02 06:00:00"], ""),
        (["2026-11-02 06:00:00", 1, 2], ""),
        ({"2026-11-02 06:00:00": 1}, ""),
        (["2026-11-02 06:30:00", 1], "[0]"),
        (["2026-11-02T06:00:00", 1], "[0]"),
        (["2026-11-02 06:00", 1], "[0]"),
        (["2026-11-02 24:00:00", 1], "[0]"),
        (["2026-02-30 06:00:00", 1], "[0]"),
        ([1762063200, 1], "[0]"),
        (["2026-11-02 06:00:00", "1.5"], "[1]"),
        (["2026-11-02 06:00:00", True], "[1]"),
        (["2026-11-02 06:00:00", math.nan], "[1]"),
        (["2026-11-02 06:00:00", math.inf], "[1]"),
    ],
)
def test_a_bad_pair_label_or_value_is_refused_at_its_place(pair, where):
    with pytest.raises(ObserwatorDataError) as caught:
        day_points({"status": "success", "data": [pair]}, DAY, filename="m.json")

    assert f"m.json cannot be read at $.2026-11-02.data[0]{where}:" in str(caught.value)


def test_an_hour_given_twice_in_a_day_is_refused():
    twice = hours(DAY, [1.0] * 24)
    twice["data"][23] = ["2026-11-02 06:00:00", 2.0]

    with pytest.raises(ObserwatorDataError) as caught:
        day_points(twice, DAY, filename="m.json")

    assert "m.json cannot be read at $.2026-11-02.data[23][0]:" in str(caught.value)


def test_an_error_answer_gives_no_hours():
    with pytest.raises(ObserwatorDataError) as caught:
        day_points(answer("m_1_water_20261103"), NOVEMBER[2], filename="m.json")

    assert "m.json cannot be read at $.status:" in str(caught.value)


# --------------------------------------------------------------------------
# The month files
# --------------------------------------------------------------------------


def test_a_month_file_keeps_each_days_answer_in_canonical_bytes():
    answers = {day: answer(f"m_7_water_{day:%Y%m%d}") for day in reversed(NOVEMBER)}

    data = encode_month(answers)

    assert read_month(data, filename="m.json") == answers
    assert list(read_month(data, filename="m.json")) == list(NOVEMBER)
    # Sorted keys, no white space between tokens, UTF-8 and one final line feed:
    # the same answers give the same bytes in any order.
    assert data == encode_month(dict(reversed(answers.items())))
    assert data.endswith(b"}\n") and data.count(b"\n") == 1
    one = {
        "status": "success",
        "message": "Żuławy",
        "data": [["2026-11-02 06:00:00", 1.5]],
    }
    assert (
        encode_month({DAY: one})
        == (
            '{"2026-11-02":{"data":[["2026-11-02 06:00:00",1.5]],'
            '"message":"Żuławy","status":"success"}}\n'
        ).encode()
    )


@pytest.mark.parametrize(
    ("content", "where"),
    [
        (b"{", "$"),
        (b"[{}]", "$"),
        (b'{"2026-11-31": {}}', "$.2026-11-31"),
        (b'{"20261101": {}}', "$.20261101"),
        (b'{"2026-W44-7": {}}', "$.2026-W44-7"),
    ],
)
def test_a_month_file_keyed_by_anything_but_iso_dates_is_refused(content, where):
    with pytest.raises(ObserwatorDataError) as caught:
        read_month(content, filename="m.json")

    assert f"m.json cannot be read at {where}:" in str(caught.value)


def test_the_daily_precipitation_is_the_sum_of_the_providers_day():
    records = list(
        daily_records(
            month(1, "rain"),
            dataset="pl.gdanskiewody.meteo_daily",
            station="GDANSKIEWODY-1",
            symbol="rain",
            filename="rest/measurements/1/rain/2026-11.json",
        )
    )

    assert [(r.date, r.measurements) for r in records] == [
        (NOVEMBER[0], {"P": Measurement(0.0, "value")}),
        (NOVEMBER[1], {"P": Measurement(0.129, "value")}),
        (NOVEMBER[2], {"P": Measurement(1.007, "value")}),
    ]
    assert {(r.station_code, r.dataset, r.period, r.hydro_year) for r in records} == {
        ("GDANSKIEWODY-1", "pl.gdanskiewody.meteo_daily", None, 2027)
    }


@pytest.mark.parametrize(
    ("station", "symbol", "variable", "means"),
    [
        (4, "water", "H_asl", (4.893, 4.887, 4.887)),
        (504, "flow", "Q", (0.029, 0.029, 0.03)),
        (700, "watertemp", "T", (12.758, 12.662, 12.833)),
        (91, "temp", "Tmean", (7.242, 6.079, 7.125)),
        (91, "windlevel", "wind_speed", (0.0, 0.004, 0.017)),
        (91, "pressure", "pressure", (1024.583, 1023.8, 1025.292)),
        (91, "humidity", "humidity", (91.888, 92.596, 94.562)),
        (91, "sun", "irradiance", (16.137, 14.042, 15.458)),
    ],
)
def test_every_other_daily_value_is_the_mean_of_the_24_hours(
    station, symbol, variable, means
):
    records = daily_records(
        month(station, symbol),
        dataset="pl.gdanskiewody.hydro_daily",
        station=f"GDANSKIEWODY-{station}",
        symbol=symbol,
        filename=f"rest/measurements/{station}/{symbol}/2026-11.json",
    )

    assert [r.measurements for r in records] == [
        {variable: Measurement(mean, "value")} for mean in means
    ]


def test_a_daily_value_has_three_decimals_and_never_a_negative_zero():
    assert daily(DAY, [0.3333] * 24, "rain") == {"P": Measurement(7.999, "value")}
    # 25 / 24 = 1.041666…
    assert daily(DAY, [1] * 23 + [2], "temp") == {"Tmean": Measurement(1.042, "value")}
    zero = daily(DAY, [-0.0001] * 24, "temp")["Tmean"].value

    assert zero == 0.0 and math.copysign(1.0, zero) == 1.0


def test_the_hydrological_year_turns_on_the_first_of_november():
    october, november = date(2026, 10, 31), date(2026, 11, 1)
    content = encode_month(
        {october: hours(october, [1] * 24), november: hours(november, [1] * 24)}
    )

    records = daily_records(
        content, dataset="d", station="GDANSKIEWODY-1", symbol="rain", filename="f"
    )

    assert [(r.date, r.hydro_year) for r in records] == [
        (october, 2026),
        (november, 2027),
    ]


def test_a_day_without_all_24_hours_is_missing():
    day = date(2026, 11, 24)
    missing = {"P": Measurement(None, "missing")}

    assert daily(day, [0.5] * 23 + [None], "rain") == missing
    assert daily(day, [0.5] * 23, "rain") == missing
    assert daily(day, [None] * 24, "rain") == missing
    # The recorded day asked at 03:18 UTC of the next: its last two hours are null.
    (recorded,) = daily_records(
        encode_month({day: answer("m_2_rain_20261124_at_031857")}),
        dataset="pl.gdanskiewody.meteo_daily",
        station="GDANSKIEWODY-2",
        symbol="rain",
        filename="rest/measurements/2/rain/2026-11.json",
    )
    assert recorded.measurements == missing


@pytest.mark.parametrize(
    ("station", "symbol"), [(91, "winddir"), (700, "conductivity"), (91, "foo")]
)
def test_a_quantity_without_a_daily_variable_gives_no_record(station, symbol):
    content = month(station, "winddir" if symbol == "foo" else symbol)

    records = daily_records(
        content,
        dataset="pl.gdanskiewody.meteo_daily",
        station=f"GDANSKIEWODY-{station}",
        symbol=symbol,
        filename="f",
    )

    assert list(records) == []


def test_a_month_file_name_gives_the_station_and_the_quantity():
    rain = list(
        parse_gdanskiewody_month(
            month(7, "rain"), filename="rest/measurements/7/rain/2026-11.json"
        )
    )
    water = parse_gdanskiewody_month(
        month(7, "water"),
        filename="rest/measurements/7/water/2026-11.json",
        dataset="pl.gdanskiewody.hydro_daily",
    )

    assert [(r.station_code, r.dataset, r.date) for r in rain] == [
        ("GDANSKIEWODY-7", "pl.gdanskiewody.measurements", day) for day in NOVEMBER
    ]
    assert [r.measurements for r in rain] == [
        {"P": Measurement(value, "value")} for value in (0.0, 0.096, 0.5)
    ]
    assert [(r.station_code, r.dataset, r.measurements) for r in water] == [
        (
            "GDANSKIEWODY-7",
            "pl.gdanskiewody.hydro_daily",
            {"H_asl": Measurement(v, "value")},
        )
        for v in (2.971, 2.97, 2.974)
    ]


@pytest.mark.parametrize(
    "filename",
    [
        "2026-11.json",
        "rain/2026-11.json",
        "rest/measurements/0/rain/2026-11.json",
        "rest/measurements/1000/rain/2026-11.json",
        "rest/measurements/07/rain/2026-11.json",
        "rest/measurements/x/rain/2026-11.json",
        "rest/measurements/7/rain/2026-13.json",
        "rest/measurements/7/rain/2026-1.json",
        "rest/measurements/7/rain/2026-11.csv",
        "rest/measurements/7/rain/2026-11-01.json",
    ],
)
def test_a_name_that_is_no_month_file_of_a_station_is_refused(filename):
    with pytest.raises(ObserwatorDataError) as caught:
        list(parse_gdanskiewody_month(month(7, "rain"), filename=filename))

    assert f"{filename} cannot be read at $:" in str(caught.value)


def test_a_day_outside_the_files_month_is_refused():
    first, last, december = date(2026, 11, 1), date(2026, 11, 30), date(2026, 12, 1)
    edges = encode_month({day: hours(day, [0.5] * 24) for day in (first, last)})
    spilled = encode_month(
        {first: hours(first, [0.5] * 24), december: hours(december, [0.5] * 24)}
    )

    assert list(read_month(edges, filename="m.json", period=(first, last))) == [
        first,
        last,
    ]
    assert list(read_month(spilled, filename="m.json")) == [first, december]
    with pytest.raises(ObserwatorDataError) as caught:
        read_month(spilled, filename="m.json", period=(first, last))
    assert "m.json cannot be read at $.2026-12-01:" in str(caught.value)
    with pytest.raises(ObserwatorDataError):
        hourly_points(spilled, filename="m.json", period=(first, last))
    with pytest.raises(ObserwatorDataError) as named:
        list(
            parse_gdanskiewody_month(
                spilled, filename="rest/measurements/7/rain/2026-11.json"
            )
        )
    assert "at $.2026-12-01:" in str(named.value)


def test_the_hours_of_a_month_file_come_once_each_in_time_order():
    shuffled = {day: answer(f"m_4_water_{day:%Y%m%d}") for day in NOVEMBER}
    shuffled[NOVEMBER[1]] = shuffled[NOVEMBER[1]] | {
        "data": random.Random(7).sample(shuffled[NOVEMBER[1]]["data"], 24)
    }

    points = hourly_points(encode_month(shuffled), filename="m.json")

    start = datetime(2026, 11, 1, 6, tzinfo=UTC)
    assert [moment for moment, _ in points] == [
        start + timedelta(hours=offset) for offset in range(72)
    ]
    assert points == hourly_points(month(4, "water"), filename="m.json")
    assert (points[0], points[-1]) == (
        (start, 4.9),
        (datetime(2026, 11, 4, 5, tzinfo=UTC), 4.89),
    )


@pytest.mark.parametrize(
    "code",
    [
        "GDANSKIEWODY-0",
        "GDANSKIEWODY-1000",
        "GDANSKIEWODY-07",
        "GDANSKIEWODY-",
        "7",
        "CHMU-7",
    ],
)
def test_only_a_code_of_the_provider_gives_a_station_number(code):
    assert station_number("GDANSKIEWODY-999") == "999"
    with pytest.raises(ValueError):
        station_number(code)
