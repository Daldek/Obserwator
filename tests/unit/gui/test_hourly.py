"""
The GUI's hourly series (ADR-031): the months of a series held as one, hours and tiers.

The month versions are written by `plant_month` (`tests.unit.gui.hourly`) as the O4
contract lays them out on a copy of the fixture root. IMGW-PIB's hourly series is
private by default (its hydro.imgw.pl input, P15, ADR-030 D5): the GUI never serves it.
"""

from __future__ import annotations

import shutil
from datetime import date

import pytest

from obserwator.attribution import attribution
from obserwator.messages import message
from tests.unit.gui.conftest import HYDRO, HYDRO_CHMU
from tests.unit.gui.hourly import CHMU, IMGW, plant_month

EN = {"Accept-Language": "en"}


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
