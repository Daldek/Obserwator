"""
The GUI's hourly series (ADR-031): the months of a series held as one, hours and tiers.

The month versions are written by `plant_month` as the O4 contract lays them out
(``series/versions/<slug>/<YYYY-MM>/<label>_<sha8>/`` with ``series.json``, its sidecar
and one Parquet file per station) on a copy of the fixture root. IMGW-PIB's hourly series
is private by default (its hydro.imgw.pl input, P15, ADR-030 D5): the GUI never serves it.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from datetime import UTC, date, datetime, timedelta

import pytest

from obserwator.attribution import attribution, dataset_origins
from obserwator.datasets import get_dataset
from obserwator.messages import message
from tests.unit.gui.conftest import HYDRO, HYDRO_CHMU

EN = {"Accept-Language": "en"}
CHMU = "cz.chmu.hydro_subdaily"
IMGW = "pl.imgw.hydro_subdaily"
FLAGS = ("value", "missing", "no_phenomenon", "accumulated")
TIERS = ("verified", "telemetry", "operational")


def _time(value: datetime) -> str:
    return value.strftime("%Y-%m-%dT%H:%M:%SZ")


def plant_month(root, dataset, day, points, *, made="2026-11-23T15:00:00Z"):
    """
    One month version of an hourly series holding one day of one station.

    ``points`` maps each variable to 24 ``(value, tier)`` pairs, hour 0 to 23 UTC of
    ``day`` (``(None, None)`` without a value); a variable without any value is
    left out of the coverage's values, as the builder leaves it.
    """
    import pyarrow as pa
    import pyarrow.parquet as pq

    descriptor = get_dataset(dataset)
    code = HYDRO_CHMU if dataset == CHMU else HYDRO
    month = day.strftime("%Y-%m")
    hours = [
        datetime(day.year, day.month, day.day, tzinfo=UTC) + timedelta(hours=h)
        for h in range(24)
    ]
    tiers = [
        tier
        for tier in TIERS
        if any(item[1] == tier for pairs in points.values() for item in pairs)
    ]
    lines = attribution(*dataset_origins(dataset)).fields()
    columns = {
        "time": pa.array(hours, pa.timestamp("us", tz="UTC")),
        "hydro_year": pa.array(
            [day.year + (1 if day.month >= 11 else 0)] * 24, pa.int32()
        ),
    }
    coverage = {}
    for variable, unit in descriptor.variables.items():
        pairs = points.get(variable, [(None, None)] * 24)
        columns[f"{variable}_value"] = pa.array([v for v, _ in pairs], pa.float64())
        columns[f"{variable}_flag"] = pa.DictionaryArray.from_arrays(
            pa.array([0 if v is not None else 1 for v, _ in pairs], pa.int8()),
            pa.array(FLAGS, pa.string()),
        )
        if len(tiers) > 1:
            columns[f"{variable}_tier"] = pa.DictionaryArray.from_arrays(
                pa.array(
                    [None if t is None else TIERS.index(t) for _, t in pairs],
                    pa.int8(),
                ),
                pa.array(TIERS, pa.string()),
            )
        held = [h for h, (v, _) in zip(hours, pairs, strict=True) if v is not None]
        gaps = [
            [_time(h), _time(h)]
            for h, (v, _) in zip(hours, pairs, strict=True)
            if v is None and held and held[0] < h < held[-1]
        ]
        coverage[variable] = {
            "unit": unit,
            "first": _time(held[0]) if held else None,
            "last": _time(held[-1]) if held else None,
            "with_value": len(held),
            "accumulated": 0,
            "gaps": gaps,
        }
    metadata = {
        "obserwator_schema": "obserwator-series/1",
        "dataset": dataset,
        "units": json.dumps(dict(descriptor.variables), sort_keys=True),
        **{name: json.dumps(value) for name, value in lines.items()},
    }
    table = pa.table(columns).replace_schema_metadata(metadata)
    sink = pa.BufferOutputStream()
    pq.write_table(table, sink)
    parquet = sink.getvalue().to_pybytes()
    index = {
        "schema": "obserwator-series/1",
        "dataset": dataset,
        "year_type": "calendar",
        "month": month,
        "tiers": tiers,
        "periods": [[day.isoformat(), day.isoformat()]],
        "stations": {
            code: {
                "file": f"stations/{code}.parquet",
                "sha256": hashlib.sha256(parquet).hexdigest(),
                "rows": 24,
                "variables": coverage,
            }
        },
        **lines,
    }
    data = (
        json.dumps(index, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        + "\n"
    ).encode("utf-8")
    sha = hashlib.sha256(data).hexdigest()
    version = (
        root / "series" / "versions" / descriptor.slug / month / f"2026-11-23_{sha[:8]}"
    )
    (version / "stations").mkdir(parents=True)
    (version / "stations" / f"{code}.parquet").write_bytes(parquet)
    (version / "series.json").write_bytes(data)
    # The provider's fields (producer, country, licence) of its daily series' sidecar
    daily = "chmu_hydro_daily" if dataset == CHMU else "imgw_hydro_daily"
    template = sorted((root / "series/versions" / daily).glob("*/*.meta.json"))[-1]
    sidecar = {
        **json.loads(template.read_text(encoding="utf-8")),
        "dataset": dataset,
        "downloaded_at": made,
        "sha256": sha,
        "size_bytes": len(data),
        "request": {"dataset": dataset, "month": month},
        "tier": "operational",
        "publication": "public" if dataset == CHMU else "private",
        "extra": {
            "derived": "series",
            "version": {"label": "2026-11-23", "label_source": "inputs"},
            "series_schema": "obserwator-series/1",
            "source_files": [],
        },
    }
    (version / "series.json.meta.json").write_text(
        json.dumps(sidecar), encoding="utf-8"
    )
    return f"{month}/{version.name}"


def _hours(*runs):
    """24 ``(value, tier)`` pairs from ``(first, last, value, tier)`` runs of hours."""
    pairs = [(None, None)] * 24
    for first, last, value, tier in runs:
        for hour in range(first, last + 1):
            pairs[hour] = (value + hour, tier)
    return pairs


@pytest.fixture(scope="module")
def hourly_root(fixture_root, tmp_path_factory):
    """
    The fixture root with two months of ČHMÚ's hourly series and one of IMGW-PIB's.

    ČHMÚ, 30 October 2026: H verified at 00–11 UTC (none at 05) and operational at
    12–21, Q verified at 00–05, no T; 2 November 2026: H operational all day (one tier,
    so no tier columns). IMGW-PIB, 30 October 2026: H operational all day.
    """
    root = tmp_path_factory.mktemp("hourly") / "data"
    shutil.copytree(fixture_root, root)
    october = _hours((0, 4, 100.0, "verified"), (6, 11, 100.0, "verified"))
    october[12:22] = _hours((12, 21, 200.0, "operational"))[12:22]
    versions = [
        plant_month(
            root,
            CHMU,
            date(2026, 10, 30),
            {"H": october, "Q": _hours((0, 5, 1.5, "verified"))},
        ),
        plant_month(
            root,
            CHMU,
            date(2026, 11, 2),
            {"H": _hours((0, 23, 300.0, "operational"))},
        ),
    ]
    plant_month(
        root, IMGW, date(2026, 10, 30), {"H": _hours((0, 23, 50.0, "operational"))}
    )
    return root, versions


@pytest.fixture
def client(make_client, hourly_root):
    """A client of the private GUI on the root with the hourly months."""
    return make_client(hourly_root[0])


def test_an_hourly_series_answers_its_hours_and_the_tier_of_each_value(
    client, hourly_root
):
    _, versions = hourly_root
    document = client.get(f"/api/series/{CHMU}/{HYDRO_CHMU}").json()

    assert (document["time_unit"], document["year_type"]) == ("hour", "calendar")
    assert document["versions"] == versions
    assert document["version"] == versions[-1]
    assert len(document["dates"]) == 48
    assert document["dates"][:2] == ["2026-10-30T00:00:00Z", "2026-10-30T01:00:00Z"]
    assert document["dates"][23:25] == ["2026-10-30T23:00:00Z", "2026-11-02T00:00:00Z"]
    assert document["hydro_year"][23:25] == [2026, 2027]
    assert document["values"]["H"][4:7] == [104.0, None, 106.0]
    assert document["values"]["H"][21:25] == [221.0, None, None, 300.0]
    # Each run's rows with a value have its tier; an hour without one has none
    assert document["tiers"] == {
        "H": [[0, 11, "verified"], [12, 47, "operational"]],
        "Q": [[0, 5, "verified"]],
        "T": [],
    }
    assert document["flags"] == {"H": [], "Q": [], "T": []}
    assert document["attribution"] == list(attribution("chmu").attribution)


def test_a_range_of_an_hourly_series_takes_every_hour_of_its_days(client):
    part = client.get(
        f"/api/series/{CHMU}/{HYDRO_CHMU}",
        params={"start": "2026-11-01", "end": "2026-11-02", "variables": "H"},
    ).json()
    october = client.get(
        f"/api/series/{CHMU}/{HYDRO_CHMU}",
        params={"start": "2026-10-30", "end": "2026-10-30"},
    ).json()

    assert part["dates"][0] == "2026-11-02T00:00:00Z"
    assert part["dates"][-1] == "2026-11-02T23:00:00Z"
    assert part["tiers"] == {"H": [[0, 23, "operational"]]}
    assert len(october["dates"]) == 24
    assert october["tiers"]["H"] == [[0, 11, "verified"], [12, 23, "operational"]]


def test_a_station_lists_its_hourly_series_with_the_months_coverage(client):
    station = client.get(f"/api/stations/{HYDRO_CHMU}").json()
    (entry,) = [d for d in station["datasets"] if d["dataset"] == CHMU]

    assert (entry["time_unit"], entry["rows"]) == ("hour", 48)
    assert set(entry["variables"]) == {"H", "Q"}
    assert entry["variables"]["H"] == {
        "unit": "cm",
        "period": None,
        "first": "2026-10-30T00:00:00Z",
        "last": "2026-11-02T23:00:00Z",
        "with_value": 45,
        "accumulated": 0,
        "gaps": 1,
    }
    assert station["attribution_parts"]["series"]["attribution"] == list(
        attribution("chmu").attribution
    )


def test_a_private_hourly_series_is_served_by_no_route(client):
    station = client.get(f"/api/stations/{HYDRO}").json()
    session = client.get("/api/session").json()
    stations = client.get("/api/stations").json()["stations"]
    answers = [
        client.get(f"/api/series/{IMGW}/{HYDRO}", headers=EN),
        client.get(f"/api/files/series/{IMGW}/{HYDRO}", headers=EN),
    ]
    files = client.get(f"/api/downloads/{HYDRO}").json()

    assert IMGW not in [d["dataset"] for d in station["datasets"]]
    assert IMGW not in session["root"]["series"]
    assert CHMU in session["root"]["series"]
    assert IMGW not in next(s for s in stations if s["code"] == HYDRO)["datasets"]
    assert IMGW not in [item["dataset"] for item in files["series"]]
    # Answered as a dataset the root does not hold
    for answer in answers:
        assert answer.status_code == 404, answer.text
        body = answer.json()
        assert body["code"] == "not_found"
        assert body["details"]["value"] == IMGW
        assert IMGW not in body["details"]["allowed"]
        assert body["message"] == message("gui.errors.no_dataset", dataset=IMGW)
