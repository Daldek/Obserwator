"""Exports of ADR-014: the stations as GeoJSON and CSV, a series as CSV, JSON and Parquet."""

import csv
import io
import json
from datetime import date
from pathlib import Path

import jsonschema
import pytest
import respx

from obserwator import (
    ObserwatorCancelledError,
    ObserwatorError,
    ObserwatorStoreError,
    ObserwatorValidationError,
    current_version,
    export_series,
    export_stations,
    get_dataset,
    get_provider,
    init_store,
    read_catalog,
    run_command,
    summarize_series,
    validate_command,
)
from obserwator.attribution import attribution
from obserwator.datasets import archive_files
from obserwator.fetch import DownloadResult
from obserwator.store import build_catalog, build_series, write_archive
from obserwator.store.export import _number
from tests.contract.support import trailing_lines
from tests.unit.test_store_catalog import sync_sources

SCHEMAS = Path(__file__).parents[2] / "schemas"
GOLDEN = Path(__file__).parents[1] / "fixtures" / "export_golden"
ARCHIVES = Path(__file__).parents[1] / "fixtures" / "store" / "archives"
ATTRIBUTION_COLUMNS = (
    "attribution_source",
    "attribution_processed",
    "attribution",
    "terms_notice",
)
DAILY, RABA = "pl.imgw.hydro_daily", "149190310"
# Golden CSV of each shape of a series, saved with the CSV export of develop 9aefb23:
# (store, dataset, station, options).
SERIES = {
    "hydro_daily": ("pl_cz", DAILY, RABA, {}),
    "meteo_precip_daily": ("pl_cz", "pl.imgw.meteo_precip_daily", "123750000", {}),
    "chmi_meteo_daily": ("pl_cz", "cz.chmi.meteo_daily", "0-203-0-90001", {}),
    "chmi_hydro_daily": (
        "pl_cz",
        "cz.chmi.hydro_daily",
        "0-203-1-900002",
        {"year_type": "hydrological"},
    ),
    "hydro_semiannual": ("other", "pl.imgw.hydro_semiannual", RABA, {}),
    "hydro_monthly": ("other", "pl.imgw.hydro_monthly", RABA, {}),
    "meteo_climate_daily": ("other", "pl.imgw.meteo_climate_daily", "123750000", {}),
}


def schema_errors(document, name):
    schema = json.loads((SCHEMAS / f"{name}.schema.json").read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)
    checker = jsonschema.Draft202012Validator(
        schema, format_checker=jsonschema.FormatChecker()
    )
    return [error.message for error in checker.iter_errors(document)]


def rfc7946_problems(document):
    """What breaks RFC 7946 in a FeatureCollection of Points (sections 3.1.2, 3.2, 3.3, 7.1)."""
    if document.get("type") != "FeatureCollection" or not isinstance(
        document.get("features"), list
    ):
        return ["no FeatureCollection with a features array"]
    forbidden = ("coordinates", "geometries", "geometry", "properties")
    problems = [f"collection has {key}" for key in forbidden if key in document]
    for feature in document["features"]:
        code = feature.get("id")
        if feature.get("type") != "Feature" or not {"geometry", "properties"} <= set(
            feature
        ):
            problems.append(f"{code}: no Feature with geometry and properties")
        problems += [
            f"{code}: feature has {key}"
            for key in ("coordinates", "geometries", "features")
            if key in feature
        ]
        if not isinstance(code, str | int) or isinstance(code, bool):
            problems.append(f"{code}: id is neither a string nor a number")
        if not isinstance(feature.get("properties"), dict | None):
            problems.append(f"{code}: properties are no object")
        geometry = feature.get("geometry")
        if geometry is None:
            continue
        position = geometry.get("coordinates")
        if (
            geometry.get("type") != "Point"
            or not isinstance(position, list)
            or not 2 <= len(position) <= 3
            or not all(
                isinstance(item, int | float) and not isinstance(item, bool)
                for item in position
            )
        ):
            problems.append(f"{code}: no Point position")
        elif not (-180 <= position[0] <= 180 and -90 <= position[1] <= 90):
            problems.append(f"{code}: no WGS 84 longitude and latitude")
    return problems


def text(lines):
    return "".join(lines)


def table(lines):
    return list(csv.DictReader(io.StringIO(text(lines), newline="")))


def cell(value):
    """A value as the CSV writes it."""
    if value is None:
        return ""
    if isinstance(value, float):
        return _number(value)
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


@pytest.fixture(scope="module")
def other(tmp_path_factory):
    """Half-year, monthly and climate series of the fixture archives (a data root)."""
    base = tmp_path_factory.mktemp("exports_other")
    raw_root = init_store(base / "raw").root
    root = init_store(base / "data", kind="data").root
    for dataset, years, months in (
        ("pl.imgw.hydro_semiannual", [2024], None),
        ("pl.imgw.hydro_monthly", [2024], None),
        ("pl.imgw.meteo_climate_daily", [2001], [1]),
    ):
        for archive in archive_files(dataset, years=years, months=months):
            source = ARCHIVES / archive.server_path
            if source.exists():
                data = source.read_bytes()
                response = DownloadResult(data, archive.url, None, None, len(data))
                write_archive(raw_root, archive=archive, response=response)
        build_series(root, raw_root=raw_root, dataset=dataset)
    return root


@pytest.fixture
def stores(fixture_root, other):
    return {"pl_cz": fixture_root, "other": other}


# --------------------------------------------------------------------------
# A series as CSV, JSON and Parquet
# --------------------------------------------------------------------------


@pytest.mark.parametrize("name", list(SERIES))
def test_series_csv_stays_byte_for_byte(name, stores):
    store, dataset, station, options = SERIES[name]

    exported = text(
        export_series(root=stores[store], dataset=dataset, station=station, **options)
    )

    golden = (GOLDEN / f"series_export_{name}.csv").read_bytes()
    assert exported.encode("utf-8") == golden


@pytest.mark.parametrize("name", list(SERIES))
def test_series_json_and_parquet_hold_the_values_and_flags_of_the_csv(
    name, stores, tmp_path
):
    import pyarrow.parquet as pq

    store, dataset, station, options = SERIES[name]
    root, descriptor = stores[store], get_dataset(dataset)
    chosen = {"root": root, "dataset": dataset, "station": station, **options}
    rows = table(export_series(**chosen))
    headers = [name for name in rows[0] if name not in ATTRIBUTION_COLUMNS]
    names = [header.split(" [")[0] for header in headers]

    document = json.loads(text(export_series(**chosen, format="json")))
    report = export_series(**chosen, format="parquet", output=tmp_path / "s.parquet")
    parquet = pq.read_table(report.output)

    assert schema_errors(document, "obserwator-series-export-1") == []
    version = current_version(root, slot=f"series:{dataset}").version
    assert document["series_version"] == version.parent.relative_to(root).as_posix()
    assert (document["provider"], document["station"]) == (descriptor.provider, station)
    assert document["variables"] == {
        variable: {"unit": unit, "note": str(descriptor.variable_notes[variable])}
        for variable, unit in descriptor.variables.items()
    }
    lines = trailing_lines(rows)
    assert {key: document[key] for key in lines.fields()} == lines.fields()
    assert list(document["columns"]) == names
    assert parquet.column_names == headers
    for header, column in zip(headers, names, strict=True):
        cells = [row[header] for row in rows]
        assert [cell(value) for value in document["columns"][column]] == cells
        assert [cell(value) for value in parquet.column(header).to_pylist()] == cells
    metadata = {
        key.decode(): value.decode() for key, value in parquet.schema.metadata.items()
    }
    assert metadata["obserwator_schema"] == "obserwator-series-export/1"
    for key in ("dataset", "provider", "station", "series_version", "year_type"):
        assert metadata[key] == document[key]
    variables = document["variables"]
    assert json.loads(metadata["units"]) == {k: v["unit"] for k, v in variables.items()}
    notes = {key: value["note"] for key, value in variables.items()}
    assert json.loads(metadata["variable_notes"]) == notes
    assert json.loads(metadata["license"]) == document["license"]
    assert {key: json.loads(metadata[key]) for key in lines.fields()} == lines.fields()


def test_parquet_needs_output_in_the_function_and_the_catalog(fixture_root, tmp_path):
    options = {
        "root": fixture_root,
        "dataset": DAILY,
        "station": RABA,
        "format": "parquet",
    }

    with pytest.raises(ObserwatorValidationError) as function:
        export_series(**options)
    with pytest.raises(ObserwatorValidationError) as catalog:
        validate_command("series export", options=options)

    expected = {"option": "output", "reason": "output_required"}
    assert function.value.details == catalog.value.details == expected
    assert list(tmp_path.iterdir()) == []


def test_json_lines_equal_the_file_and_follow_the_chosen_variables(
    fixture_root, tmp_path
):
    progress = []
    options = {
        "root": fixture_root,
        "dataset": DAILY,
        "station": RABA,
        "format": "json",
    }
    lines = text(export_series(**options, variables=["Q", "H"]))

    report = export_series(
        **options,
        variables=["Q", "H"],
        output=tmp_path / "raba.json",
        on_progress=progress.append,
    )

    assert report.output.read_bytes() == lines.encode("utf-8")
    document = json.loads(lines)
    assert list(document["variables"]) == ["Q", "H"]
    assert list(document["columns"]) == ["date", "year", "Q", "Q_flag", "H", "H_flag"]
    rows = len(document["columns"]["date"])
    assert [(item.current, item.total) for item in progress] == [(rows, rows)]


# --------------------------------------------------------------------------
# The stations of the current catalogs
# --------------------------------------------------------------------------


def test_stations_of_both_providers_are_one_geojson_of_rfc_7946_and_its_schema(
    fixture_root,
):
    document = json.loads(text(export_stations(fixture_root)))

    assert rfc7946_problems(document) == []
    assert schema_errors(document, "obserwator-stations-export-1") == []
    stations = read_catalog(root=fixture_root)
    assert [(f["properties"]["provider"], f["id"]) for f in document["features"]] == [
        (station.provider, station.station_code) for station in stations
    ]
    for feature, station in zip(document["features"], stations, strict=True):
        position = station.geometry
        assert feature["geometry"] == (
            None if position is None else {"type": "Point", "coordinates": [*position]}
        )
        properties = dict(feature["properties"])
        del properties["provider"], properties["series"]
        assert properties == dict(station.properties)
    unlocated = {
        f["properties"]["provider"] for f in document["features"] if not f["geometry"]
    }
    assert unlocated == {"IMGW-PIB", "CHMI"}
    imgw, chmi = attribution("imgw", "gugik"), attribution("chmi", "cuzk")
    assert {key: document[key] for key in ("attribution", "terms_notice")} == (
        imgw | chmi
    ).fields()
    assert [
        (entry["provider"], entry["version"], entry["license"]["id"])
        + (entry.get("terms_notice"),)
        for entry in document["catalogs"]
    ] == [
        (
            provider,
            current_version(fixture_root, slot=f"catalog:{key}")
            .version.parent.relative_to(fixture_root)
            .as_posix(),
            license_id,
            terms,
        )
        for provider, key, license_id, terms in (
            ("IMGW-PIB", "pl.imgw.stations", "IMGW-PIB", list(imgw.terms_notice)),
            ("CHMI", "cz.chmi.stations", "CC-BY-4.0", None),
        )
    ]
    assert [entry["attribution"] for entry in document["catalogs"]] == [
        list(imgw.attribution),
        list(chmi.attribution),
    ]


def test_the_series_of_a_station_are_read_from_the_series_indexes(fixture_root):
    document = json.loads(text(export_stations(fixture_root)))

    expected: dict[str, dict[str, dict[str, object]]] = {}
    for entry in document["series"]:
        version = current_version(
            fixture_root, slot=f"series:{entry['dataset']}"
        ).version
        assert entry["version"] == version.parent.relative_to(fixture_root).as_posix()
        names = list(get_dataset(entry["dataset"]).variables)
        for item in summarize_series(root=fixture_root, dataset=entry["dataset"]):
            held = expected.setdefault(item.station_code, {}).setdefault(
                entry["dataset"], {"first": None, "last": None, "variables": []}
            )
            if item.with_value:
                held["first"] = min(filter(None, (held["first"], item.first)))
                held["last"] = max(filter(None, (held["last"], item.last)))
                held["variables"] = sorted(
                    {*held["variables"], item.variable}, key=names.index
                )
    assert {entry["dataset"] for entry in document["series"]} == {
        DAILY,
        "pl.imgw.meteo_precip_daily",
        "cz.chmi.hydro_daily",
        "cz.chmi.meteo_daily",
    }
    for feature in document["features"]:
        held = {
            dataset: {
                **item,
                "first": item["first"] and item["first"].isoformat(),
                "last": item["last"] and item["last"].isoformat(),
            }
            for dataset, item in expected.get(feature["id"], {}).items()
        }
        assert feature["properties"]["series"] == held
    raba = next(f for f in document["features"] if f["id"] == RABA)
    assert raba["properties"]["series"][DAILY]["variables"] == ["H", "Q", "T"]


def test_the_csv_has_the_rows_of_the_geojson_and_each_provider_its_lines(
    fixture_root,
):
    document = json.loads(text(export_stations(fixture_root)))
    rows = table(export_stations(fixture_root, format="csv"))

    assert list(rows[0])[:4] == ["station_code", "name", "kind", "provider"]
    assert list(rows[0])[-7:] == [
        "latitude",
        "longitude",
        "datasets",
        *ATTRIBUTION_COLUMNS,
    ]
    assert [row["station_code"] for row in rows] == [
        f["id"] for f in document["features"]
    ]
    for row, feature in zip(rows, document["features"], strict=True):
        properties = feature["properties"]
        longitude, latitude = (feature["geometry"] or {"coordinates": [None, None]})[
            "coordinates"
        ]
        assert (row["latitude"], row["longitude"]) == (cell(latitude), cell(longitude))
        assert row["datasets"] == ";".join(properties["series"])
        assert row["active"] == ("true" if properties["active"] else "false")
        assert row["name"] == properties["name"] and row["kind"] == properties["kind"]
        thresholds = properties.get("thresholds")
        assert (json.loads(row["thresholds"]) if row["thresholds"] else None) == (
            thresholds
        )
    for provider, origins in (
        ("IMGW-PIB", ("imgw", "gugik")),
        ("CHMI", ("chmi", "cuzk")),
    ):
        block = [row for row in rows if row["provider"] == provider]
        owner = get_provider(provider)
        assert trailing_lines(block) == attribution(*origins)
        assert (block[0]["attribution_source"], block[0]["attribution_processed"]) == (
            owner.license.attribution,
            owner.processed_attribution,
        )
        assert not any(row["attribution_source"] for row in block[1:])


def test_kind_provider_and_series_narrow_what_is_read(fixture_root):
    hydro = json.loads(text(export_stations(fixture_root, kind="hydro")))
    chmi = json.loads(
        text(export_stations(fixture_root, provider="cz.chmi", series=False))
    )
    header = next(
        csv.reader(
            io.StringIO(text(export_stations(fixture_root, series=False, format="csv")))
        )
    )

    assert {f["properties"]["kind"] for f in hydro["features"]} == {"hydro"}
    assert {get_dataset(item["dataset"]).kind for item in hydro["series"]} == {"hydro"}
    assert [entry["stations"] for entry in hydro["catalogs"]] == [
        len([f for f in hydro["features"] if f["properties"]["provider"] == provider])
        for provider in ("IMGW-PIB", "CHMI")
    ]
    assert {f["properties"]["provider"] for f in chmi["features"]} == {"CHMI"}
    assert "series" not in chmi and "terms_notice" not in chmi
    assert not any("series" in f["properties"] for f in chmi["features"])
    assert "datasets" not in header


def test_a_location_of_the_hydro_imgw_pl_map_adds_its_lines(
    tmp_path, isolated_reference_dir
):
    raw_root = init_store(tmp_path / "raw")
    store = init_store(tmp_path / "data", kind="data")
    (isolated_reference_dir / "hydro_stations_locations.csv").write_text(
        "station_code,latitude,longitude\n149190312,50.0512,19.9512\n", encoding="utf-8"
    )
    with respx.mock(assert_all_called=False) as router:
        sync_sources(raw_root, router)
        build_catalog(store, raw_root=raw_root.root)

    document = json.loads(text(export_stations(store, series=False)))
    envelope = run_command("stations export", options={"root": store.root})
    text(envelope.result)

    lines = attribution("imgw", "gugik") | attribution("imgw_hydro")
    assert {key: document[key] for key in lines.fields()} == lines.fields()
    assert document["catalogs"][0]["attribution"] == list(lines.attribution)
    assert (envelope.attribution, envelope.terms_notice) == (
        lines.attribution,
        lines.terms_notice,
    )


def test_the_file_equals_the_lines_and_the_default_root_is_the_store_root(
    fixture_root, tmp_path, monkeypatch
):
    monkeypatch.setenv("OBSERWATOR_ROOT", str(fixture_root))
    progress, notices = [], []
    lines = text(export_stations(format="csv"))

    report = export_stations(
        output=tmp_path / "stations.csv",
        format="csv",
        on_progress=progress.append,
        on_notice=notices.append,
    )

    assert report.output.read_bytes() == lines.encode("utf-8")
    stations = len(read_catalog(root=fixture_root))
    assert (progress[-1].current, progress[-1].total) == (stations, stations)
    assert [notice.code for notice in notices] == ["license_terms", "license_terms"]
    with pytest.raises(ObserwatorError) as conflict:
        export_stations(fixture_root, output=report.output)
    assert conflict.value.code == "conflict"
    with pytest.raises(ObserwatorCancelledError):
        export_stations(
            fixture_root, output=report.output, force=True, cancel=lambda: True
        )
    assert report.output.read_bytes() == lines.encode("utf-8")


@pytest.mark.parametrize(
    ("options", "option"),
    [
        ({"format": "shapefile"}, "format"),
        ({"kind": "air"}, "kind"),
        ({"provider": "DWD"}, "provider"),
        ({"force": True}, "output"),
    ],
)
def test_wrong_options_are_refused_before_reading(fixture_root, options, option):
    with pytest.raises(ObserwatorValidationError) as error:
        export_stations(fixture_root, **options)
    assert error.value.details["option"] == option


def test_a_store_without_a_catalog_is_not_found(tmp_path):
    root = init_store(tmp_path / "store", kind="data").root

    for provider in (None, "CHMI"):
        with pytest.raises(ObserwatorStoreError) as error:
            export_stations(root, provider=provider)
        assert error.value.code == "not_found" and error.value.hint
