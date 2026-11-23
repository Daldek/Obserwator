"""The readers of a sub-daily series (ADR-031): month slots, months, reads, summaries, exports, REST."""

import csv
import hashlib
import json
import shutil
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from fastapi.testclient import TestClient

from obserwator._version import __version__
from obserwator.api.instance import served_instance
from obserwator.api.main import app
from obserwator.attribution import attribution, dataset_origins
from obserwator.captures import publication
from obserwator.config import settings
from obserwator.datasets import archive_files, get_dataset, get_provider
from obserwator.exceptions import (
    ObserwatorDataError,
    ObserwatorStoreError,
    ObserwatorValidationError,
)
from obserwator.fetch import DownloadResult
from obserwator.models import Measurement
from obserwator.store import (
    build_series,
    current_version,
    export_series,
    export_stations,
    init_store,
    iter_store,
    read_series,
    read_series_index,
    select_series,
    series_months,
    summarize_series,
    write_archive,
)

IMGW = "pl.imgw.hydro_subdaily"  # private by default: hydro-back's hours
CHMU = "cz.chmu.hydro_subdaily"  # public by default
GLOGOW = "151160060"
KLODZKO = "150160180"
WIGOS = "0-203-1-001000"
FLAGS = ("value", "missing", "no_phenomenon", "accumulated")
TIERS = ("verified", "telemetry", "operational")
HOUR = timedelta(hours=1)
OCTOBER = (date(2026, 10, 30), date(2026, 10, 31))
NOVEMBER = (date(2026, 11, 1), date(2026, 11, 2))
COLUMNS = [
    "time",
    "year",
    "H [cm]",
    "H_flag",
    "H_tier",
    "Q [m3/s]",
    "Q_flag",
    "Q_tier",
    "T [degC]",
    "T_flag",
    "T_tier",
]
# IMGW-PIB's telemetry of October 2026 cut to Głogów and Kłodzko (the recorded harvest).
TELEMETRY = (
    Path(__file__).parents[1]
    / "fixtures/operational/october/danepubliczne.imgw.pl/datastore/getfiledown"
    / "Arch/Telemetria/Hydro/2026/Hydro_2026-10.zip"
)


def hour(month, day, at):
    """The start of an hour of 2026, UTC."""
    return datetime(2026, month, day, at, tzinfo=UTC)


def hours(first, last):
    """Every hour from 00:00 of the day ``first`` to 23:00 of ``last``."""
    moment = datetime(first.year, first.month, first.day, tzinfo=UTC)
    end = datetime(last.year, last.month, last.day, 23, tzinfo=UTC)
    while moment <= end:
        yield moment
        moment += HOUR


def text(moment):
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def canonical(document):
    return (
        json.dumps(document, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def coverage(unit, points, rows):
    """A variable's coverage as ``series.json`` gives it; gaps never span a missing row."""
    valued = sorted(points)
    gaps = []
    run = None
    for moment in rows:
        if not valued or not valued[0] <= moment <= valued[-1]:
            continue
        if moment in points:
            run = None
        elif run is not None and moment - run[1] == HOUR:
            run[1] = moment
        else:
            run = [moment, moment]
            gaps.append(run)
    return {
        "unit": unit,
        "first": text(valued[0]) if valued else None,
        "last": text(valued[-1]) if valued else None,
        "with_value": len(valued),
        "accumulated": 0,
        "gaps": [[text(first), text(last)] for first, last in gaps],
    }


def write_month(
    root,
    dataset,
    month,
    stations,
    *,
    periods,
    label="2026-11-23",
    downloaded="2026-11-23T03:00:00Z",
):
    """
    Publish a version of a month of a sub-daily series in the builder's layout.

    ``stations`` maps a station code to ``{variable: {hour: (value, tier)}}``; a
    station file has a row for every hour of ``periods`` and a ``<V>_tier`` column
    only when the values have several tiers. Returns the ``series.json``.
    """
    descriptor = get_dataset(dataset)
    found = {
        tier
        for points in stations.values()
        for values in points.values()
        for _, tier in values.values()
    }
    tiers = [tier for tier in TIERS if tier in found]
    rows = [moment for first, last in periods for moment in hours(first, last)]
    lines = attribution(*dataset_origins(dataset))
    files, index = {}, {}
    for code, points in stations.items():
        columns = {
            "time": pa.array(rows, pa.timestamp("us", tz="UTC")),
            "hydro_year": pa.array(
                [moment.year + (moment.month >= 11) for moment in rows], pa.int32()
            ),
        }
        for name in descriptor.variables:
            cells = [points.get(name, {}).get(moment) for moment in rows]
            columns[f"{name}_value"] = pa.array(
                [None if cell is None else cell[0] for cell in cells], pa.float64()
            )
            columns[f"{name}_flag"] = pa.DictionaryArray.from_arrays(
                pa.array([1 if cell is None else 0 for cell in cells], pa.int8()),
                pa.array(FLAGS),
            )
            if len(tiers) > 1:
                columns[f"{name}_tier"] = pa.DictionaryArray.from_arrays(
                    pa.array(
                        [
                            None if cell is None else TIERS.index(cell[1])
                            for cell in cells
                        ],
                        pa.int8(),
                    ),
                    pa.array(TIERS),
                )
        metadata = {
            "obserwator_schema": "obserwator-series/1",
            "dataset": dataset,
            "units": json.dumps(dict(descriptor.variables)),
            **{key: json.dumps(value) for key, value in lines.fields().items()},
        }
        sink = pa.BufferOutputStream()
        pq.write_table(pa.table(columns).replace_schema_metadata(metadata), sink)
        files[code] = sink.getvalue().to_pybytes()
        index[code] = {
            "file": f"stations/{code}.parquet",
            "sha256": hashlib.sha256(files[code]).hexdigest(),
            "rows": len(rows),
            "variables": {
                name: coverage(unit, points.get(name, {}), rows)
                for name, unit in descriptor.variables.items()
            },
        }
    content = canonical(
        {
            "schema": "obserwator-series/1",
            "dataset": dataset,
            "year_type": "calendar",
            "month": month,
            "tiers": tiers,
            "periods": [
                [first.isoformat(), last.isoformat()] for first, last in periods
            ],
            "stations": index,
            **lines.fields(),
        }
    )
    sha = hashlib.sha256(content).hexdigest()
    provider = get_provider(descriptor.provider)
    version = (
        root / "series" / "versions" / descriptor.slug / month / f"{label}_{sha[:8]}"
    )
    (version / "stations").mkdir(parents=True)
    for code, data in files.items():
        (version / "stations" / f"{code}.parquet").write_bytes(data)
    (version / "series.json").write_bytes(content)
    sidecar = {
        "schema": "obserwator-meta/1",
        "producer": "obserwator",
        "producer_version": __version__,
        "dataset": dataset,
        "country": provider.country,
        "provider": provider.id,
        "request": {"dataset": dataset, "month": month},
        "license": {
            "id": descriptor.license.id,
            "attribution": ". ".join(lines.attribution),
            "url": descriptor.license.url,
        },
        "downloaded_at": downloaded,
        "sha256": sha,
        "size_bytes": len(content),
        "tier": "operational",
        "publication": publication(dataset),
        "extra": {
            "version": {"label": label, "label_source": "inputs"},
            "derived": "series",
            "series_schema": "obserwator-series/1",
            "source_files": [],
        },
    }
    (version / "series.json.meta.json").write_bytes(canonical(sidecar))
    return version / "series.json"


def rewrite(series, change):
    """Change the ``series.json`` of a version and give its sidecar the new bytes."""
    document = json.loads(series.read_text(encoding="utf-8"))
    change(document)
    content = canonical(document)
    series.write_bytes(content)
    sidecar = series.with_name("series.json.meta.json")
    meta = json.loads(sidecar.read_text(encoding="utf-8"))
    meta.update(sha256=hashlib.sha256(content).hexdigest(), size_bytes=len(content))
    sidecar.write_bytes(canonical(meta))


def every(first, last, tier, value, *, skip=()):
    """The points of the hours of ``first``–``last`` but ``skip``, one value and tier."""
    return {
        moment: (value, tier) for moment in hours(first, last) if moment not in skip
    }


def version_dir(series):
    """A month version as ``--version`` names it: relative to the data root."""
    return series.parent.relative_to(series.parents[5]).as_posix()


@pytest.fixture
def data(tmp_path):
    return init_store(tmp_path / "data", kind="data").root


@pytest.fixture
def months(data):
    """
    IMGW-PIB's sub-daily series of 2026-10 (one tier) and 2026-11 (two tiers).

    Głogów's H stops at 21:00 of 31 October and resumes at 01:00 of 1 November (a gap
    across the months' boundary) and misses 05:00–06:00 of 30 October; its T is read
    once a day at 06:00. Kłodzko has values in November only.
    """
    october_h = {
        moment: (200.0 + number, "operational")
        for number, moment in enumerate(hours(*OCTOBER))
        if moment
        not in (hour(10, 30, 5), hour(10, 30, 6), hour(10, 31, 22), hour(10, 31, 23))
    }
    october = write_month(
        data,
        IMGW,
        "2026-10",
        {
            GLOGOW: {
                "H": october_h,
                "Q": every(*OCTOBER, "operational", 50.5),
                "T": {
                    hour(10, 30, 6): (8.5, "operational"),
                    hour(10, 31, 6): (8.0, "operational"),
                },
            }
        },
        periods=[OCTOBER],
    )
    november = write_month(
        data,
        IMGW,
        "2026-11",
        {
            GLOGOW: {
                "H": {
                    **every(
                        NOVEMBER[0],
                        NOVEMBER[0],
                        "telemetry",
                        300.0,
                        skip=[hour(11, 1, 0)],
                    ),
                    **every(NOVEMBER[1], NOVEMBER[1], "operational", 400.0),
                },
                "Q": every(*NOVEMBER, "telemetry", 60.25),
                "T": {
                    hour(11, 1, 6): (7.5, "operational"),
                    hour(11, 2, 6): (7.0, "operational"),
                },
            },
            KLODZKO: {
                "H": every(*NOVEMBER, "telemetry", 120.0),
                "Q": every(*NOVEMBER, "telemetry", 3.5),
            },
        },
        periods=[NOVEMBER],
    )
    return SimpleNamespace(root=data, october=october, november=november)


# --------------------------------------------------------------------------
# Slots, scan, months
# --------------------------------------------------------------------------


def test_a_month_has_its_slot_and_the_bare_slot_names_the_month_form(months):
    entry = current_version(months.root, slot=f"series:{IMGW}:2026-10")

    assert (entry.kind, entry.slot, entry.version, entry.provider) == (
        "series",
        f"series:{IMGW}:2026-10",
        months.october,
        "IMGW",
    )
    assert current_version(months.root, slot=f"series:{IMGW}:2026-09") is None
    for slot in (
        f"series:{IMGW}",
        f"series:{IMGW}:2026-13",
        f"series:{IMGW}:{GLOGOW}",
        f"series:{IMGW}:2026-10/x",
    ):
        with pytest.raises(ObserwatorValidationError) as error:
            current_version(months.root, slot=slot)
        assert f"series:{IMGW}:<YYYY-MM>" in str(error.value)
        assert error.value.details == {"option": "slot", "value": slot}
    # Any other series keeps refusing a selector.
    with pytest.raises(ObserwatorValidationError, match="unexpected selector"):
        current_version(months.root, slot="series:pl.imgw.hydro_daily:2026-10")


def test_the_newest_build_of_a_month_is_its_current_version(months):
    newer = write_month(
        months.root,
        IMGW,
        "2026-11",
        {KLODZKO: {"H": every(*NOVEMBER, "operational", 121.0)}},
        periods=[NOVEMBER],
        label="2026-11-22",
        downloaded="2026-11-24T03:00:00Z",
    )

    assert current_version(months.root, slot=f"series:{IMGW}:2026-11").version == newer
    assert [entry.version for entry in series_months(months.root, dataset=IMGW)] == [
        months.october,
        newer,
    ]


def test_the_scan_lists_month_versions_under_their_slots_and_strays_as_unknown(
    months,
):
    slug = months.root / "series" / "versions" / "imgw_hydro_subdaily"
    (slug / "stray").mkdir()
    misplaced = slug / months.october.parent.name  # a version beside the months
    shutil.copytree(months.october.parent, misplaced)

    entries = list(iter_store(months.root))

    assert {(e.slot, e.version) for e in entries if e.kind == "series"} == {
        (f"series:{IMGW}:2026-10", months.october),
        (f"series:{IMGW}:2026-11", months.november),
    }
    assert {(e.problem_code, e.version) for e in entries if e.kind == "problem"} == {
        ("unknown_entry", slug / "stray"),
        ("unknown_entry", misplaced),
    }
    # A caller that knows a month's version gets it back unread.
    known = {version_dir(months.october): ["series.json"]}
    skipped = [
        entry
        for entry in iter_store(months.root, kind="series", skip_versions=known)
        if entry.skipped
    ]
    assert [(entry.slot, entry.version) for entry in skipped] == [
        (f"series:{IMGW}:2026-10", months.october)
    ]


@pytest.mark.parametrize(
    ("bounds", "expected"),
    [
        ({}, ["2026-10", "2026-11"]),
        ({"start": date(2026, 10, 31)}, ["2026-10", "2026-11"]),
        ({"start": date(2026, 11, 1)}, ["2026-11"]),
        ({"end": date(2026, 10, 31)}, ["2026-10"]),
        ({"start": date(2026, 10, 15), "end": date(2026, 10, 15)}, ["2026-10"]),
        ({"end": date(2026, 9, 30)}, []),
    ],
)
def test_series_months_gives_the_months_touching_the_range_in_order(
    months, bounds, expected
):
    entries = series_months(months.root, dataset=IMGW, **bounds)

    assert [entry.slot for entry in entries] == [
        f"series:{IMGW}:{month}" for month in expected
    ]


def test_series_months_refuses_a_series_without_months_and_bad_bounds(months):
    with pytest.raises(ObserwatorValidationError) as error:
        series_months(months.root, dataset="pl.imgw.hydro_daily")
    assert error.value.details == {
        "option": "dataset",
        "value": "pl.imgw.hydro_daily",
        "reason": "not_monthly",
    }
    for bounds in (
        {"start": datetime(2026, 10, 1, tzinfo=UTC)},
        {"start": date(2026, 11, 2), "end": date(2026, 11, 1)},
    ):
        with pytest.raises(ObserwatorValidationError):
            series_months(months.root, dataset=IMGW, **bounds)
    assert series_months(months.root, dataset=CHMU) == ()


# --------------------------------------------------------------------------
# Index and records
# --------------------------------------------------------------------------


def test_the_index_of_a_month_has_its_month_tiers_and_hours(months):
    index = read_series_index(months.november)
    h = index.stations[GLOGOW].variables["H"]

    assert (index.month, index.tiers) == ("2026-11", ("telemetry", "operational"))
    assert (h.first, h.last, h.with_value, h.gaps) == (
        hour(11, 1, 1),
        hour(11, 2, 23),
        47,
        (),
    )
    assert h.first.tzinfo is UTC
    october = read_series_index(months.october)
    assert october.tiers == ("operational",)
    assert october.stations[GLOGOW].variables["H"].gaps == (
        (hour(10, 30, 5), hour(10, 30, 6)),
    )


@pytest.mark.parametrize(
    "change",
    [
        lambda document: document.update(month="2026-13"),
        lambda document: document.pop("month"),
        lambda document: document.update(month="2026-09"),  # periods outside it
        lambda document: document.update(tiers=[]),
        lambda document: document.pop("tiers"),
        lambda document: document.update(tiers=["operational", "telemetry"]),
        lambda document: document.update(tiers=["telemetry", "telemetry"]),
        lambda document: document.update(tiers=["daily"]),
        lambda document: document["stations"][GLOGOW]["variables"]["H"].update(
            first="2026-11-01T01:30:00Z"
        ),
        lambda document: document["stations"][GLOGOW]["variables"]["T"].update(
            gaps=[["2026-11-01", "2026-11-02"]]
        ),
    ],
)
def test_a_bad_month_tiers_or_time_is_an_invalid_index(months, change):
    rewrite(months.november, change)

    with pytest.raises(ObserwatorDataError, match="invalid series index"):
        read_series_index(months.november)


def test_reading_the_dataset_joins_the_months_with_the_tier_of_each_point(months):
    records = list(read_series(root=months.root, dataset=IMGW, station=GLOGOW))
    at = {record.time: record for record in records}

    assert [record.time for record in records] == [
        *hours(*OCTOBER),
        *hours(*NOVEMBER),
    ]
    assert all(
        record.date == record.time.date() and record.time.tzinfo is UTC
        for record in records
    )
    # October has one tier and no tier column: every value has it.
    assert at[hour(10, 30, 0)].measurements["H"] == Measurement(
        200.0, "value", tier="operational"
    )
    assert at[hour(10, 30, 5)].measurements["H"] == Measurement(None, "missing")
    # November has two: each value its own, none without a value.
    assert at[hour(11, 1, 0)].measurements["H"] == Measurement(None, "missing")
    assert at[hour(11, 1, 1)].measurements["H"] == Measurement(
        300.0, "value", tier="telemetry"
    )
    assert at[hour(11, 2, 0)].measurements["H"].tier == "operational"
    assert at[hour(11, 1, 6)].measurements["T"] == Measurement(
        7.5, "value", tier="operational"
    )


def test_start_and_end_take_the_hours_of_their_utc_days(months):
    records = list(
        read_series(
            root=months.root,
            dataset=IMGW,
            station=GLOGOW,
            variables=["Q"],
            start=date(2026, 10, 31),
            end=date(2026, 11, 1),
        )
    )

    assert [record.time for record in records] == list(
        hours(date(2026, 10, 31), date(2026, 11, 1))
    )
    assert {name for record in records for name in record.measurements} == {"Q"}


def test_a_version_reads_its_month_and_the_station_must_be_in_a_month(months):
    month = list(read_series(months.november.parent, station=KLODZKO))

    assert [record.time for record in month] == list(hours(*NOVEMBER))
    assert {record.measurements["H"].tier for record in month} == {"telemetry"}
    # Kłodzko is in November only: October has no records of it, no error.
    assert (
        list(
            read_series(
                root=months.root, dataset=IMGW, station=KLODZKO, end=date(2026, 10, 31)
            )
        )
        == []
    )
    with pytest.raises(ObserwatorValidationError) as error:
        read_series(root=months.root, dataset=IMGW, station="149190310")
    assert error.value.details == {"option": "station", "value": "149190310"}
    with pytest.raises(ObserwatorValidationError):
        read_series(months.october, station=KLODZKO)


def test_a_root_without_a_month_of_the_series_has_none_to_read(data):
    calls = (
        lambda: read_series(root=data, dataset=IMGW, station=GLOGOW),
        lambda: summarize_series(root=data, dataset=IMGW),
        lambda: export_series(root=data, dataset=IMGW, station=GLOGOW),
    )
    for call in calls:
        with pytest.raises(ObserwatorStoreError) as error:
            call()
        assert error.value.code == "not_found"


def test_a_value_of_a_month_of_several_tiers_without_its_tier_is_invalid(months):
    parquet = months.november.parent / "stations" / f"{GLOGOW}.parquet"
    table = pq.read_table(parquet)
    tiers = table.column("H_tier").to_pylist()
    tiers[1] = None  # 01:00 of 1 November has a value
    table = table.set_column(
        table.schema.get_field_index("H_tier"),
        "H_tier",
        pa.array(tiers).dictionary_encode(),
    )
    pq.write_table(table, parquet)
    digest = hashlib.sha256(parquet.read_bytes()).hexdigest()
    rewrite(
        months.november,
        lambda document: document["stations"][GLOGOW].update(sha256=digest),
    )

    with pytest.raises(ObserwatorDataError, match="inconsistent tier"):
        list(read_series(months.november, station=GLOGOW))


# --------------------------------------------------------------------------
# Summary
# --------------------------------------------------------------------------


def test_the_summary_joins_the_months_with_the_gap_across_their_boundary(months):
    rows = summarize_series(root=months.root, dataset=IMGW)
    at = {(row.station_code, row.variable): row for row in rows}

    assert [(row.station_code, row.variable) for row in rows] == [
        (KLODZKO, "H"),
        (KLODZKO, "Q"),
        (KLODZKO, "T"),
        (GLOGOW, "H"),
        (GLOGOW, "Q"),
        (GLOGOW, "T"),
    ]
    h = at[GLOGOW, "H"]
    assert (h.first, h.last, h.with_value) == (hour(10, 30, 0), hour(11, 2, 23), 91)
    assert h.gaps == (
        (hour(10, 30, 5), hour(10, 30, 6)),
        (hour(10, 31, 22), hour(11, 1, 0)),
    )
    assert at[GLOGOW, "T"].gaps == (
        (hour(10, 30, 7), hour(10, 31, 5)),
        (hour(10, 31, 7), hour(11, 1, 5)),
        (hour(11, 1, 7), hour(11, 2, 5)),
    )
    # The last value of October and the first of November are adjacent hours.
    assert (at[GLOGOW, "Q"].with_value, at[GLOGOW, "Q"].gaps) == (96, ())
    assert at[KLODZKO, "H"].first == hour(11, 1, 0)
    assert (at[KLODZKO, "T"].first, at[KLODZKO, "T"].with_value) == (None, 0)
    # A version summarizes its month only.
    (november,) = summarize_series(months.november, stations=[GLOGOW], variables=["H"])
    assert (november.first, november.with_value) == (hour(11, 1, 1), 47)
    with pytest.raises(ObserwatorValidationError):
        summarize_series(root=months.root, dataset=IMGW, stations=["149190310"])


def test_hours_outside_the_months_periods_are_never_gaps(data):
    # 31 October has no record of any station: its hours are unknown, not missing.
    first, last = date(2026, 10, 30), date(2026, 11, 1)
    write_month(
        data,
        IMGW,
        "2026-10",
        {
            GLOGOW: {
                "H": every(
                    first,
                    first,
                    "telemetry",
                    1.0,
                    skip=[hour(10, 30, 22), hour(10, 30, 23)],
                )
            }
        },
        periods=[(first, first)],
    )
    write_month(
        data,
        IMGW,
        "2026-11",
        {GLOGOW: {"H": every(last, last, "telemetry", 2.0, skip=[hour(11, 1, 0)])}},
        periods=[(last, last)],
    )

    (h,) = summarize_series(root=data, dataset=IMGW, variables=["H"])

    assert h.gaps == (
        (hour(10, 30, 22), hour(10, 30, 23)),
        (hour(11, 1, 0), hour(11, 1, 0)),
    )


def test_a_month_the_builder_made_of_the_telemetry_reads_back(tmp_path):
    raw = init_store(tmp_path / "raw").root
    data = init_store(tmp_path / "data", kind="data").root
    content = TELEMETRY.read_bytes()
    (archive,) = archive_files("pl.imgw.hydro_telemetry", years=[2026], months=[10])
    write_archive(
        raw,
        archive=archive,
        response=DownloadResult(content, archive.url, None, None, len(content)),
    )
    build_series(data, raw_root=raw, dataset=IMGW)

    (month,) = series_months(data, dataset=IMGW)
    records = list(read_series(root=data, dataset=IMGW, station=GLOGOW))
    rows = {
        (row.station_code, row.variable): row
        for row in summarize_series(root=data, dataset=IMGW)
    }

    assert month.slot == f"series:{IMGW}:2026-10"
    assert [record.time for record in records] == list(
        hours(date(2026, 10, 1), date(2026, 10, 31))
    )
    assert {
        measurement.tier
        for record in records
        for measurement in record.measurements.values()
        if measurement.value is not None
    } == {"telemetry"}
    # Every full hour of H and Q at both stations, Głogów's T once a day.
    assert [
        rows[code, name].with_value for code in (KLODZKO, GLOGOW) for name in "HQ"
    ] == [744] * 4
    assert (rows[GLOGOW, "T"].with_value, rows[KLODZKO, "T"].with_value) == (22, 0)


# --------------------------------------------------------------------------
# Exports
# --------------------------------------------------------------------------


def test_the_three_export_formats_hold_the_same_hourly_columns(months, tmp_path):
    options = {"root": months.root, "dataset": IMGW, "station": GLOGOW}
    export_series(**options, output=tmp_path / "glogow.csv")
    export_series(**options, format="json", output=tmp_path / "glogow.json")
    export_series(**options, format="parquet", output=tmp_path / "glogow.parquet")
    with (tmp_path / "glogow.csv").open(encoding="utf-8", newline="") as stream:
        header, *data = list(csv.reader(stream))
    document = json.loads((tmp_path / "glogow.json").read_text(encoding="utf-8"))
    table = pq.read_table(tmp_path / "glogow.parquet")
    lines = attribution(*dataset_origins(IMGW))
    versions = [version_dir(months.october), version_dir(months.november)]

    assert header == [*COLUMNS, "attribution", "terms_notice"]
    assert list(document["columns"]) == [column.split(" ")[0] for column in COLUMNS]
    assert table.column_names == COLUMNS
    assert table.schema.field("time").type == pa.timestamp("us", tz="UTC")
    assert len(data) == len(document["columns"]["time"]) == table.num_rows == 96
    # 00:00 of 30 October, 00:00 and 01:00 of 1 November: one tier, none, another.
    assert [row[:5] for row in (data[0], data[48], data[49])] == [
        ["2026-10-30T00:00:00Z", "2026", "200.0", "value", "operational"],
        ["2026-11-01T00:00:00Z", "2026", "", "missing", ""],
        ["2026-11-01T01:00:00Z", "2026", "300.0", "value", "telemetry"],
    ]
    columns = document["columns"]
    assert [columns[name][48:50] for name in ("time", "H", "H_tier")] == [
        ["2026-11-01T00:00:00Z", "2026-11-01T01:00:00Z"],
        [None, 300.0],
        [None, "telemetry"],
    ]
    assert table.slice(48, 2).select(["time", "H [cm]", "H_tier"]).to_pylist() == [
        {"time": hour(11, 1, 0), "H [cm]": None, "H_tier": None},
        {"time": hour(11, 1, 1), "H [cm]": 300.0, "H_tier": "telemetry"},
    ]
    assert (
        document["time_unit"],
        document["series_version"],
        document["series_versions"],
    ) == ("hour", versions[0], versions)
    assert (document["attribution"], document["terms_notice"]) == (
        list(lines.attribution),
        list(lines.terms_notice),
    )
    metadata = table.schema.metadata
    assert json.loads(metadata[b"series_versions"]) == versions
    assert json.loads(metadata[b"attribution"]) == list(lines.attribution)
    assert [row[-2] for row in data[: len(lines.attribution)]] == list(
        lines.attribution
    )


def test_an_export_names_only_the_months_it_holds(months):
    def head(*args, **options):
        return json.loads("".join(export_series(*args, format="json", **options)))

    november = head(root=months.root, dataset=IMGW, station=KLODZKO)
    october = head(months.october, station=GLOGOW, variables=["Q"])

    assert november["series_versions"] == [version_dir(months.november)]
    assert len(november["columns"]["time"]) == 48
    assert (october["series_version"], october["series_versions"]) == (
        version_dir(months.october),
        [version_dir(months.october)],
    )
    assert list(october["columns"]) == ["time", "year", "Q", "Q_flag", "Q_tier"]
    with pytest.raises(ObserwatorDataError, match="is empty"):
        export_series(
            root=months.root, dataset=IMGW, station=KLODZKO, end=date(2026, 10, 31)
        )


def test_the_stations_export_lists_the_daily_series_beside_a_sub_daily_one(
    fixture_root, tmp_path
):
    root = tmp_path / "data"
    shutil.copytree(fixture_root, root)
    write_month(
        root,
        IMGW,
        "2026-10",
        {GLOGOW: {"Q": every(*OCTOBER, "telemetry", 1.0)}},
        periods=[OCTOBER],
    )

    document = json.loads("".join(export_stations(root, format="geojson")))

    datasets = {item["dataset"] for item in document["series"]}
    assert "pl.imgw.hydro_daily" in datasets and IMGW not in datasets


def test_series_select_refuses_a_sub_daily_series(months):
    with pytest.raises(ObserwatorValidationError) as error:
        select_series(months.root, dataset=IMGW, stations=[GLOGOW])

    assert error.value.details == {
        "option": "dataset",
        "value": IMGW,
        "reason": "monthly",
    }


# --------------------------------------------------------------------------
# REST
# --------------------------------------------------------------------------


@pytest.fixture
def rest(months, monkeypatch, tmp_path):
    """A REST server on the data root of ``months`` and a public ČHMÚ month, no nogat.toml section."""
    config = tmp_path / "nogat.toml"
    config.write_text("", encoding="utf-8")
    monkeypatch.setenv("NOGAT_CONFIG", str(config))
    served_instance.cache_clear()
    write_month(
        months.root,
        CHMU,
        "2026-11",
        {WIGOS: {"H": every(NOVEMBER[0], NOVEMBER[0], "verified", 55.0)}},
        periods=[(NOVEMBER[0], NOVEMBER[0])],
    )
    monkeypatch.setattr(settings, "root", months.root)
    yield SimpleNamespace(months=months, client=TestClient(app))
    served_instance.cache_clear()


def assert_private(answer, key, option):
    assert answer.status_code == 404, answer.text
    problem = answer.json()
    assert problem["code"] == "not_found"
    assert problem["details"]["reason"] == "private"
    assert problem["details"]["option"] == option
    assert key in problem["detail"]


def test_rest_does_not_serve_the_private_imgw_series_by_dataset_or_version(rest):
    for route, params in (
        ("read", {"station": GLOGOW}),
        ("export", {"station": GLOGOW}),
        ("summary", {}),
    ):
        answer = rest.client.get(
            f"/api/v1/series/{route}", params={"dataset": IMGW, **params}
        )
        assert_private(answer, IMGW, "dataset")
    stored = version_dir(rest.months.october)
    for version in (
        stored,
        stored.replace("2026-10", "2026-09"),
        "series/versions/imgw_hydro_subdaily/2026-10",
    ):
        answer = rest.client.get(
            "/api/v1/series/read", params={"version": version, "station": GLOGOW}
        )
        assert_private(answer, IMGW, "version")


def test_rest_serves_the_public_chmu_series(rest):
    answer = rest.client.get(
        "/api/v1/series/read", params={"dataset": CHMU, "station": WIGOS}
    )

    assert answer.status_code == 200, answer.text
    first = answer.json()["result"][0]
    assert first["time"] == "2026-11-01T00:00:00Z"
    assert first["measurements"]["H"] == {
        "value": 55.0,
        "flag": "value",
        "quality": None,
        "source_flag": None,
        "tier": "verified",
    }
