"""
ČHMÚ's groundwater objects in the GUI's private API (ADR-032).

On the data root of the fixture variant ``groundwater`` (`groundwater_root`):
``complete_pl_cz`` with ČHMÚ's bore `BORE` and spring `SPRING`, their daily and weekly
series and the lists of ČHMÚ's groundwater objects. Skipped while the variant does not
exist.
"""

from __future__ import annotations

import csv
import io
import json
from datetime import date
from itertools import pairwise

import pytest

import obserwator
from obserwator.attribution import attribution
from obserwator.messages import message
from tests.unit.gui.conftest import BORE, SPRING

EN = {"Accept-Language": "en"}
WEEKLY = "cz.chmu.groundwater_weekly"


@pytest.fixture
def client(make_client, groundwater_root):
    """A client of the private GUI on the variant's data root."""
    return make_client(groundwater_root)


def test_the_station_layer_names_each_groundwater_object_a_bore_or_a_spring(client):
    stations = client.get("/api/stations").json()["stations"]
    by_code = {station["code"]: station for station in stations}

    assert {
        code: (by_code[code]["kind"], by_code[code]["groundwater_kind"])
        for code in (BORE, SPRING)
    } == {BORE: ("groundwater", "bore"), SPRING: ("groundwater", "spring")}
    assert (by_code[BORE]["name"], by_code[SPRING]["name"]) == ("Rakousy", "Želechy")
    assert (by_code[BORE]["lat"], by_code[BORE]["lon"]) == pytest.approx(
        (50.6259733, 15.1832503)
    )
    assert by_code[BORE]["datasets"] == ["cz.chmu.groundwater_daily", WEEKLY]
    assert (by_code[BORE]["first"], by_code[BORE]["last"]) == ("2012", "2024")
    assert (by_code[SPRING]["first"], by_code[SPRING]["last"]) == ("2014", "2024")
    # What an object is belongs to groundwater objects only
    others = [station for station in stations if station["kind"] != "groundwater"]
    assert {station["kind"] for station in others} == {"hydro", "meteo"}
    assert [
        station["code"] for station in others if "groundwater_kind" in station
    ] == []


def test_a_groundwater_object_answers_its_catalog_data_and_its_series(client):
    bore = client.get(f"/api/stations/{BORE}").json()
    spring = client.get(f"/api/stations/{SPRING}").json()

    for document, what in ((bore, "bore"), (spring, "spring")):
        properties = document["properties"]
        assert (properties["kind"], properties["groundwater_kind"]) == (
            "groundwater",
            what,
        )
        assert properties["location_source"] in {
            "cz.chmu.groundwater_now",
            "cz.chmu.groundwater_stations",
        }
        assert document["attribution_parts"]["series"]["attribution"] == list(
            attribution("chmu").attribution
        )
    assert bore["properties"]["elevation_m"] == pytest.approx(261.22)
    assert spring["properties"]["elevation_m"] == pytest.approx(440)
    steps = {entry["dataset"]: entry["time_unit"] for entry in bore["datasets"]}
    assert steps == {"cz.chmu.groundwater_daily": "day", WEEKLY: "week"}
    level = {
        entry["dataset"]: entry["variables"]["H_asl"] for entry in bore["datasets"]
    }
    flow = {
        entry["dataset"]: entry["variables"]["spring_yield"]
        for entry in spring["datasets"]
    }
    assert {cov["unit"] for cov in level.values()} == {"m"}
    assert {cov["unit"] for cov in flow.values()} == {"l/s"}


@pytest.mark.parametrize(
    ("provider", "stem"),
    [
        (None, "obserwator_stations_groundwater"),
        ("CHMU", "obserwator_stations_chmu_groundwater"),
    ],
)
def test_the_stations_files_of_groundwater_objects_come_from_export_stations(
    client, groundwater_root, provider, stem
):
    query = {"kind": "groundwater", **({"provider": provider} if provider else {})}
    listed = client.get("/api/downloads/stations", params=query).json()
    table = client.get(listed["formats"]["csv"]["url"])
    document = client.get(listed["formats"]["geojson"]["url"])

    chosen = {"kind": "groundwater", "provider": provider}
    assert (
        table.content
        == (
            "".join(
                obserwator.export_stations(groundwater_root, format="csv", **chosen)
            )
        ).encode()
    )
    assert (
        document.content
        == ("".join(obserwator.export_stations(groundwater_root, **chosen))).encode()
    )
    assert table.headers["content-disposition"].startswith(
        f'attachment; filename="{stem}.csv"'
    )
    assert listed["formats"]["csv"]["command"].endswith(
        f"--kind groundwater --format csv --output {stem}.csv"
    )
    features = json.loads(document.content)["features"]
    assert listed["stations"] == len(features)
    kinds = {
        feature["properties"]["station_code"]: (
            feature["properties"]["kind"],
            feature["properties"].get("groundwater_kind"),
        )
        for feature in features
    }
    assert {kind for kind, _ in kinds.values()} == {"groundwater"}
    assert (kinds[BORE], kinds[SPRING]) == (
        ("groundwater", "bore"),
        ("groundwater", "spring"),
    )
    rows = list(csv.DictReader(io.StringIO(table.text, newline="")))
    assert sorted(row["station_code"] for row in rows) == sorted(kinds)


def test_the_weekly_series_has_rows_only_at_its_readings(client):
    weekly = client.get(f"/api/series/{WEEKLY}/{BORE}").json()

    assert weekly["time_unit"] == "week"
    days = [date.fromisoformat(text) for text in weekly["dates"]]
    assert days == sorted(set(days))
    # One row per reading, at its own date, none filled in between: about one a week
    assert {day.year for day in days} == {2012}
    assert 40 <= len(days) <= 53
    assert min((later - earlier).days for earlier, later in pairwise(days)) >= 3
    assert len(weekly["values"]["H_asl"]) == len(days)


@pytest.mark.parametrize("code", [BORE, SPRING])
def test_a_groundwater_object_has_no_current_data(client, code):
    answer = client.get(f"/api/current/{code}", headers=EN)

    assert answer.status_code == 404, answer.text
    body = answer.json()
    assert body["code"] == "not_found"
    assert body["details"] == {"reason": "kind"}
    assert body["message"] == message("gui.errors.no_current_kind")
