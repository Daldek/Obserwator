"""Files of a provider fed by files (ADR-033): the station file and the series files."""

import io
import json
import zipfile
from datetime import date, datetime
from pathlib import Path

import pyarrow
import pyarrow.parquet
import pytest

from obserwator._parsing.files import MAX_STATION_BYTES, read_station_file
from obserwator._provider_files import LOCAL_CODE
from obserwator.datasets import archive_files
from obserwator.exceptions import ObserwatorDataError, ObserwatorValidationError
from obserwator.fetch import DownloadResult
from obserwator.models import Measurement
from obserwator.parsers import parse_series_export
from obserwator.store import (
    build_series,
    export_series,
    init_store,
    read_series,
    write_archive,
)

FIXTURE = Path(__file__).parents[1] / "fixtures" / "files" / "siec"
PATTERN = f"^SIEC-{LOCAL_CODE}$"
NAME = "stations.geojson"
# Packaged daily datasets of the variables and units of the fixture provider's ones.
HYDRO = "cz.chmu.hydro_daily"
METEO = "cz.chmu.meteo_daily"
SERIES = "SIEC-01.csv"


# --- station files -----------------------------------------------------------------------


def feature(code="SIEC-01", geometry=None, **properties):
    return {
        "type": "Feature",
        "geometry": geometry,
        "properties": {"station_code": code, "kind": "hydro", "name": "Most"}
        | properties,
    }


def point(lon, lat):
    return {"type": "Point", "coordinates": [lon, lat]}


def collection(*features, **members):
    return json.dumps(
        {"type": "FeatureCollection", "features": list(features)} | members
    ).encode()


def stations(data):
    return read_station_file(data, pattern=PATTERN, filename=NAME)


def broken(data):
    """The refusal of a station file: a data error naming the file."""
    with pytest.raises(ObserwatorDataError) as caught:
        stations(data)
    assert caught.value.details == {"path": NAME}
    return caught.value


def test_fixture_station_file_gives_every_station_in_file_order():
    found = read_station_file(
        (FIXTURE / "stations.geojson").read_bytes(),
        pattern=PATTERN,
        filename="siec/stations.geojson",
    )
    assert [(item.station_code, item.kind) for item in found] == [
        ("SIEC-01", "hydro"),
        ("SIEC-02", "hydro"),
        ("SIEC-03", "hydro"),
        ("SIEC-X1", "hydro"),
        ("SIEC-M1", "meteo"),
    ]
    first, second, third, _, meteo = found
    assert (first.name, first.river, first.active) == (
        "Wrocław Most Pomorski",
        "Odra",
        True,
    )
    assert (
        first.gauge_zero_m,
        first.gauge_zero_datum,
        first.river_km,
        first.catchment_area_km2,
    ) == (105.02, "PL-EVRF2007-NH", 251.6, 22111.5)
    assert (first.longitude, first.latitude) == (17.0316, 51.1177)
    # absent fields: active by default, no numbers, no texts
    assert (second.active, second.elevation_m, second.gauge_zero_m) == (
        True,
        None,
        None,
    )
    assert (second.hydrographic_code, second.groundwater_kind) == (None, None)
    # a null geometry: a station without a location
    assert (third.active, third.longitude, third.latitude) == (False, None, None)
    assert (meteo.elevation_m, meteo.established_year) == (118, 2019)


def test_geometry_may_be_absent():
    entry = feature()
    del entry["geometry"]
    (found,) = stations(collection(entry))
    assert (found.longitude, found.latitude) == (None, None)


def test_texts_are_collapsed_to_single_spaces():
    (found,) = stations(
        collection(
            feature(
                name="  Wrocław \n Most\tPomorski ",
                river=" Odra ",
                gauge_zero_datum="PL-EVRF2007-NH",
            )
        )
    )
    assert (found.name, found.river, found.gauge_zero_datum) == (
        "Wrocław Most Pomorski",
        "Odra",
        "PL-EVRF2007-NH",
    )


def test_groundwater_kind_of_a_groundwater_object():
    (bore, spring, unknown) = stations(
        collection(
            feature("SIEC-B", kind="groundwater", groundwater_kind="bore"),
            feature("SIEC-S", kind="groundwater", groundwater_kind="spring"),
            feature("SIEC-G", kind="groundwater"),
        )
    )
    assert (
        bore.groundwater_kind,
        spring.groundwater_kind,
        unknown.groundwater_kind,
    ) == (
        "bore",
        "spring",
        None,
    )


@pytest.mark.parametrize(
    "geometry",
    [point(180, 90), point(-180, -90), point(0, 0), point(17.5, 51)],
    ids=repr,
)
def test_points_in_range_are_taken(geometry):
    (found,) = stations(collection(feature(geometry=geometry)))
    assert (found.longitude, found.latitude) == tuple(geometry["coordinates"])


@pytest.mark.parametrize(
    "geometry",
    [
        {"type": "LineString", "coordinates": [[17.0, 51.0], [17.1, 51.1]]},
        {"type": "Point", "coordinates": [17.0, 51.0, 120.0]},
        {"type": "Point", "coordinates": [17.0]},
        {"type": "Point", "coordinates": {"lon": 17.0, "lat": 51.0}},
        {"type": "Point"},
        {"type": "MultiPoint", "coordinates": [[17.0, 51.0]]},
        [17.0, 51.0],
        "POINT (17 51)",
        point("17.0", "51.0"),
        point(True, 51.0),
        point(17.0, None),
        point(180.001, 51.0),
        point(-180.001, 51.0),
        point(17.0, 90.001),
        point(17.0, -90.001),
        point(51.0, 170.0),
    ],
    ids=repr,
)
def test_geometry_other_than_a_point_in_range_is_refused(geometry):
    broken(collection(feature(geometry=geometry)))


def test_non_finite_coordinates_are_refused():
    broken(
        b'{"type": "FeatureCollection", "features": ['
        + json.dumps(feature())
        .encode()
        .replace(
            b'"geometry": null',
            b'"geometry": {"type": "Point", "coordinates": [NaN, 51.0]}',
        )
        + b"]}"
    )


@pytest.mark.parametrize(
    "name",
    [
        "urn:ogc:def:crs:OGC:1.3:CRS84",
        "urn:ogc:def:crs:OGC::CRS84",
        "urn:ogc:def:crs:EPSG::4326",
        "EPSG:4326",
    ],
)
def test_wgs84_crs_is_taken(name):
    crs = {"type": "name", "properties": {"name": name}}
    (found,) = stations(collection(feature(geometry=point(17, 51)), crs=crs))
    assert found.longitude == 17


@pytest.mark.parametrize(
    "crs",
    [
        {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::2180"}},
        {"type": "name", "properties": {"name": "EPSG:2180"}},
        {"type": "name", "properties": {"name": "epsg:4326"}},
        {"type": "name", "properties": {}},
        {"type": "name"},
        "EPSG:4326",
        ["EPSG:4326"],
    ],
    ids=repr,
)
def test_other_crs_is_refused(crs):
    broken(collection(feature(geometry=point(17, 51)), crs=crs))


@pytest.mark.parametrize("properties", ["EPSG:4326", None, ["EPSG:4326"]], ids=repr)
def test_crs_whose_properties_are_no_object_is_refused(properties):
    broken(collection(feature(), crs={"type": "name", "properties": properties}))


@pytest.mark.parametrize(
    "code",
    [
        "SIEC-01",
        "SIEC-a_b-C",
        "SIEC-" + "x" * 32,
    ],
)
def test_codes_of_the_pattern_are_taken(code):
    (found,) = stations(collection(feature(code)))
    assert found.station_code == code


@pytest.mark.parametrize(
    "code",
    ["OTHER-01", "siec-01", "SIEC-", "SIEC-_1", "SIEC-" + "x" * 33, "SIEC 01", 1, None],
    ids=repr,
)
def test_code_outside_the_pattern_is_refused(code):
    broken(collection(feature(code)))


def test_repeated_code_is_refused():
    broken(collection(feature("SIEC-01"), feature("SIEC-02"), feature("SIEC-01")))


@pytest.mark.parametrize("missing", ["kind", "name"])
def test_missing_required_property_is_refused(missing):
    entry = feature()
    del entry["properties"][missing]
    broken(collection(entry))


@pytest.mark.parametrize(
    "properties",
    [
        {"kind": None},
        {"name": None},
        {"kind": "rain"},
        {"kind": "Hydro"},
        {"kind": ["hydro"]},
        {"name": ""},
        {"name": "   "},
        {"name": 5},
        {"river": ""},
        {"river": 5},
        {"hydrographic_code": " "},
        {"gauge_zero_datum": ["PL-EVRF2007-NH"]},
        {"active": "yes"},
        {"active": 1},
        {"elevation_m": "118"},
        {"elevation_m": True},
        {"gauge_zero_m": [105.0]},
        {"river_km": {"km": 1}},
        {"catchment_area_km2": 0},
        {"catchment_area_km2": -1.5},
        {"established_year": 0},
        {"established_year": 10000},
        {"established_year": 2019.0},
        {"established_year": "2019"},
        {"established_year": True},
        {"groundwater_kind": "bore"},
        {"kind": "groundwater", "groundwater_kind": "well"},
        {"operator": "x"},
    ],
    ids=repr,
)
def test_bad_property_is_refused(properties):
    broken(collection(feature(**properties)))


def test_boundaries_of_numbers_are_taken():
    (found,) = stations(
        collection(
            feature(
                established_year=1,
                catchment_area_km2=0.01,
                elevation_m=-10,
                river_km=0,
            ),
        )
    )
    assert (
        found.established_year,
        found.catchment_area_km2,
        found.elevation_m,
        found.river_km,
    ) == (1, 0.01, -10.0, 0.0)
    (found,) = stations(collection(feature(established_year=9999)))
    assert found.established_year == 9999


@pytest.mark.parametrize(
    "data",
    [
        b"",
        b"not json",
        b'{"type": "FeatureCollection", "features": [}',
        '{"type": "FeatureCollection", "features": [], "name": "Sieć"}'.encode(
            "cp1250"
        ),
        b"[]",
        json.dumps(feature()).encode(),
        b'{"type": "FeatureCollection"}',
        b'{"type": "FeatureCollection", "features": {}}',
        b'{"type": "featurecollection", "features": []}',
        collection({"type": "feature", "properties": feature()["properties"]}),
        collection({"type": "Feature", "geometry": None}),
        collection({"type": "Feature", "geometry": None, "properties": None}),
        collection("SIEC-01"),
    ],
    ids=repr,
)
def test_file_other_than_a_feature_collection_is_refused(data):
    broken(data)


def test_bom_and_an_empty_collection_are_taken():
    assert stations(b"\xef\xbb\xbf" + collection(feature())) != ()
    assert stations(collection()) == ()


def test_file_of_max_bytes_is_read_one_byte_more_refused():
    data = collection(feature())
    padded = data + b" " * (MAX_STATION_BYTES - len(data))
    assert len(padded) == MAX_STATION_BYTES
    assert len(stations(padded)) == 1
    broken(padded + b" ")


# --- series files ------------------------------------------------------------------------


def csv_file(*lines):
    return ("\n".join(lines) + "\n").encode()


def series(data, dataset=HYDRO, station="SIEC-01"):
    return parse_series_export(data, dataset=dataset, station=station, filename=SERIES)


def refused(data, dataset=HYDRO):
    """The refusal of a series file: a data error naming the file."""
    with pytest.raises(ObserwatorDataError) as caught:
        series(data, dataset)
    assert caught.value.details == {"path": SERIES}
    return caught.value


def values(records):
    return {
        record.date: {
            name: (item.value, item.flag) for name, item in record.measurements.items()
        }
        for record in records
    }


def test_fixture_hydro_file_with_flags_and_trailing_lines():
    records = series((FIXTURE / "hydro" / "SIEC-01.csv").read_bytes())
    assert values(records) == {
        date(2026, 10, 28): {"H": (212.0, "value"), "Q": (145.3, "value")},
        date(2026, 10, 29): {"H": (215.0, "value"), "Q": (149.8, "value")},
        date(2026, 10, 30): {"H": (None, "missing"), "Q": (None, "missing")},
        date(2026, 10, 31): {"H": (220.0, "value"), "Q": (156.1, "value")},
        date(2026, 11, 1): {"H": (224.0, "value"), "Q": (160.4, "value")},
        date(2026, 11, 2): {"H": (226.0, "value"), "Q": (162.0, "value")},
    }
    assert {(record.station_code, record.dataset) for record in records} == {
        ("SIEC-01", HYDRO)
    }
    # the year of a row is not read: the hydrological year follows from the date
    assert [record.hydro_year for record in records] == [2026] * 4 + [2027] * 2
    assert {record.period for record in records} == {None}


def test_fixture_file_without_flag_columns():
    records = series(
        (FIXTURE / "hydro" / "SIEC-02.csv").read_bytes(), station="SIEC-02"
    )
    assert values(records) == {
        date(2026, 10, 28): {"H": (95.0, "value")},
        date(2026, 10, 29): {"H": (97.0, "value")},
        date(2026, 10, 30): {"H": (None, "missing")},
        date(2026, 10, 31): {"H": (101.0, "value")},
    }


def test_fixture_meteo_file_keeps_every_flag():
    records = series((FIXTURE / "meteo" / "SIEC-M1.csv").read_bytes(), METEO, "SIEC-M1")
    assert [record.measurements["P"] for record in records] == [
        Measurement(0.0, "no_phenomenon"),
        Measurement(2.3, "value"),
        Measurement(None, "missing"),
        Measurement(5.8, "accumulated"),
    ]
    assert [record.measurements["Tmean"].value for record in records] == [
        9.4,
        8.1,
        7.6,
        6.9,
    ]


@pytest.mark.parametrize(
    ("value", "flag", "expected"),
    [
        ("1.5", "value", Measurement(1.5, "value")),
        ("-3", "value", Measurement(-3.0, "value")),
        ("", "missing", Measurement(None, "missing")),
        ("2.5", "accumulated", Measurement(2.5, "accumulated")),
        ("0", "no_phenomenon", Measurement(0.0, "no_phenomenon")),
        ("0.0", "no_phenomenon", Measurement(0.0, "no_phenomenon")),
        ("", "no_phenomenon", Measurement(0.0, "no_phenomenon")),
        ("1.5", "", Measurement(1.5, "value")),
        ("", "", Measurement(None, "missing")),
    ],
    ids=repr,
)
def test_flag_agrees_with_the_value(value, flag, expected):
    (record,) = series(
        csv_file("date,P [mm],P_flag", f"2026-01-01,{value},{flag}"), METEO
    )
    assert record.measurements["P"] == expected


@pytest.mark.parametrize(
    ("value", "flag"),
    [
        ("", "value"),
        ("1.5", "missing"),
        ("0", "missing"),
        ("", "accumulated"),
        ("0.5", "no_phenomenon"),
        ("1.5", "Value"),
        ("1.5", "estimated"),
        ("1.5", " value"),
        ("nan", "value"),
        ("inf", "value"),
        ("-inf", "value"),
        ("1e400", "value"),
        ("1,5", "value"),
        ("abc", "value"),
    ],
    ids=repr,
)
def test_value_or_flag_that_does_not_agree_is_refused(value, flag):
    cell = f'"{value}"' if "," in value else value
    refused(csv_file("date,P [mm],P_flag", f"2026-01-01,{cell},{flag}"), METEO)


def test_unsorted_rows_come_in_date_order():
    records = series(
        csv_file("date,H [cm]", "2026-03-01,3", "2025-12-31,1", "2026-01-15,2")
    )
    assert [(record.date, record.measurements["H"].value) for record in records] == [
        (date(2025, 12, 31), 1.0),
        (date(2026, 1, 15), 2.0),
        (date(2026, 3, 1), 3.0),
    ]


def test_repeated_date_is_refused():
    refused(csv_file("date,H [cm]", "2026-01-01,3", "2026-01-02,1", "2026-01-01,3"))


@pytest.mark.parametrize(
    "day", ["2026-02-30", "2026-1-01", "01.01.2026", "2026-01-01T00:00", "", "20260101"]
)
def test_date_other_than_an_iso_day_is_refused(day):
    refused(csv_file("date,H [cm]", f"{day},3"))


def test_columns_hold_only_those_the_file_has():
    (record,) = series(csv_file("date,Q [m3/s],Q_flag", "2026-01-01,1.5,value"))
    assert set(record.measurements) == {"Q"}


def test_year_and_trailing_lines_are_not_read_anywhere_in_the_header():
    (record,) = series(
        csv_file(
            "date,attribution,H [cm],year,terms_notice",
            '2026-11-05,"Źródło: Sieć, CC BY",42,1999,"Warunki"',
        )
    )
    assert (record.hydro_year, record.measurements["H"]) == (
        2027,
        Measurement(42.0, "value"),
    )


@pytest.mark.parametrize(
    "header",
    [
        "year,date,H [cm]",
        "Date,H [cm]",
        "date,H [m]",
        "date,H [cm ]",
        "date,H",
        "date,X [cm]",
        "date,P [mm]",
        "date,H [cm],comment",
        "date,H [cm],Q_flag",
        "date,H [cm],H [cm]",
        "date,H [cm],year,year",
        "date,year",
        "date,H_flag",
    ],
)
def test_header_outside_the_datasets_columns_is_refused(header):
    width = header.count(",")
    refused(csv_file(header, "2026-01-01" + ",1" * width))


@pytest.mark.parametrize(
    "data",
    [
        b"",
        b"date,H [cm]\n",
        b"date,H [cm]\n2026-01-01,1,2\n",
        b"date,H [cm]\n2026-01-01\n",
        b'date,H [cm]\n2026-01-01,"1\n',
        "date,H [cm],attribution\n2026-01-01,1,Źródło\n".encode("cp1250"),
    ],
    ids=repr,
)
def test_file_other_than_a_series_csv_is_refused(data):
    refused(data)


def test_bom_crlf_and_spaces_in_the_header_are_taken():
    (record,) = series(b"\xef\xbb\xbfdate, H [cm] \r\n2026-01-01,7\r\n")
    assert record.measurements["H"] == Measurement(7.0, "value")


def test_unknown_dataset_is_a_validation_error():
    with pytest.raises(ObserwatorValidationError):
        series(csv_file("date,H [cm]", "2026-01-01,1"), "pl.siec.hydro_daily_unknown")


def parquet(table):
    sink = io.BytesIO()
    pyarrow.parquet.write_table(table, sink)
    return sink.getvalue()


def test_parquet_gives_the_records_of_the_csv():
    csv_data = (FIXTURE / "hydro" / "SIEC-01.csv").read_bytes()
    days = [date(2026, 10, d) for d in (28, 29, 30, 31)] + [
        date(2026, 11, 1),
        date(2026, 11, 2),
    ]
    table = pyarrow.table(
        {
            "date": pyarrow.array(days, pyarrow.date32()),
            "year": [2026] * 4 + [2027] * 2,
            "H [cm]": [212.0, 215.0, None, 220.0, 224.0, 226.0],
            "H_flag": ["value", "value", "missing", "value", "value", "value"],
            "Q [m3/s]": [145.3, 149.8, None, 156.1, 160.4, 162.0],
            "Q_flag": ["value", "value", "missing", "value", "value", "value"],
            "attribution": [""] * 6,
            "terms_notice": [""] * 6,
        }
    )
    data = parquet(table)
    assert series(data) == series(csv_data)
    # the name does not decide the format: the bytes do
    assert parse_series_export(
        data, dataset=HYDRO, station="SIEC-01", filename="a.csv"
    ) == series(csv_data)


@pytest.mark.parametrize(
    "days",
    [
        ["2026-01-02", "2026-01-01"],
        [datetime(2026, 1, 2, 0, 0), datetime(2026, 1, 1, 0, 0)],
        [date(2026, 1, 2), date(2026, 1, 1)],
    ],
    ids=["text", "timestamp", "date"],
)
def test_parquet_dates_as_text_time_or_date(days):
    records = series(parquet(pyarrow.table({"date": days, "H [cm]": [2.0, None]})))
    assert values(records) == {
        date(2026, 1, 1): {"H": (None, "missing")},
        date(2026, 1, 2): {"H": (2.0, "value")},
    }


def test_parquet_nan_value_is_refused():
    refused(parquet(pyarrow.table({"date": ["2026-01-01"], "H [cm]": [float("nan")]})))


def test_parquet_of_another_column_is_refused():
    refused(parquet(pyarrow.table({"date": ["2026-01-01"], "H [m]": [1.0]})))


@pytest.mark.parametrize(
    "data", [b"PAR1", b"PAR1 not parquet at all", b"\x00\x01PARQUET?"], ids=repr
)
def test_file_named_parquet_that_is_none_is_refused(data):
    with pytest.raises(ObserwatorDataError) as caught:
        parse_series_export(
            data, dataset=HYDRO, station="SIEC-01", filename="SIEC-01.parquet"
        )
    assert caught.value.details == {"path": "SIEC-01.parquet"}


# --- round trip of series export ---------------------------------------------------------


STATION = "149190310"


@pytest.fixture
def exported(tmp_path):
    """A hydrological year of one IMGW-PIB station built in a store, and its records."""
    raw = init_store(tmp_path / "raw").root
    root = init_store(tmp_path / "data", kind="data").root
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(
            "codz_2024.csv",
            "\n".join(
                [
                    f"{STATION},Raba Górna,Raba,2024,1,1,150,2.5,4.0,11",
                    f"{STATION},Raba Górna,Raba,2024,6,15,155,3.75,12.5,10",
                    f"{STATION},Raba Górna,Raba,2024,12,31,160,99999.999,99.9,10",
                ]
            ).encode("cp1250"),
        )
    data = buffer.getvalue()
    (wanted,) = [
        item
        for item in archive_files("pl.imgw.hydro_daily", years=[2024])
        if item.server_path == "dane_hydrologiczne/dobowe/2024/codz_2024.zip"
    ]
    write_archive(
        raw,
        archive=wanted,
        response=DownloadResult(data, wanted.url, None, None, len(data)),
    )
    version = build_series(root, raw_root=raw, dataset="pl.imgw.hydro_daily").version
    return version, list(read_series(version, station=STATION))


@pytest.mark.parametrize("form", ["csv", "parquet"])
def test_series_export_reads_back_as_the_stored_series(exported, tmp_path, form):
    version, stored = exported
    target = tmp_path / f"{STATION}.{form}"
    export_series(version, station=STATION, output=target, format=form)
    found = parse_series_export(
        target.read_bytes(),
        dataset="pl.imgw.hydro_daily",
        station=STATION,
        filename=target.name,
    )
    assert len(found) == len(stored) == 366
    assert values(found) == values(stored)
    assert [record.hydro_year for record in found] == [
        record.hydro_year for record in stored
    ]
    assert [
        (record.measurements["H"].value, record.measurements["Q"].value)
        for record in found
        if record.measurements["H"].flag == "value"
    ] == [(150.0, 2.5), (155.0, 3.75), (160.0, None)]
