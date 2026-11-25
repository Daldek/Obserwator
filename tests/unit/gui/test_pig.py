"""
PIG-PIB's points in the GUI's private API (ADR-035).

On the data root of the fixture variant ``groundwater_pl`` (`groundwater_pl_roots`):
``groundwater`` and PIG-PIB's recorded points, October 2026's readings, a night's
capture of ``mwp_auto``, both series and the PIG catalog, all of them captured on
2026-11-24.
"""

from __future__ import annotations

import json

import pytest

from obserwator.attribution import attribution, fill, filled
from obserwator.datasets import get_provider
from obserwator.store import current_version

BORE = "6495"
"""PIG-PIB's automatic bore „Olszyc Szlachecki”: readings and hours."""
FORMULA = get_provider("PIG").license.attribution
"""PIG-PIB's W with its placeholders, as the table of provider lines writes it."""
CATALOG_W = fill(FORMULA, period="2026", date="2026-11-24")
"""The W of the fixture's PIG catalog: its points and automatic points of 2026-11-24."""


@pytest.fixture
def root(groundwater_pl_roots):
    return groundwater_pl_roots.data.root


@pytest.fixture
def client(make_client, root):
    """A client of the private GUI on the variant's data root."""
    return make_client(root)


def catalog_w(root):
    """The filled W the current PIG catalog was written with."""
    entry = current_version(root, slot="catalog:pl.pig.stations")
    document = json.loads(entry.version.read_text(encoding="utf-8"))
    return list(filled(document["attribution"]))


def test_the_session_fills_pig_pibs_w_as_its_catalog_and_names_no_analyses_of_it(
    client, root
):
    session = client.get("/api/session").json()

    texts = session["attribution"]
    assert catalog_w(root) == [CATALOG_W]
    lines = attribution("pig")
    expected = [CATALOG_W, *lines.attribution[1:]]
    assert texts["origins"]["pig"]["attribution"] == expected
    assert session["providers"]["PIG"]["attribution"] == expected
    assert texts["origins"]["pig"]["terms_notice"] == list(lines.terms_notice)
    # The page places a filled W where the order has the formula
    assert texts["fillable"] == [FORMULA]
    assert FORMULA in texts["order"]
    # Every other origin keeps its lines
    assert texts["origins"]["chmu"] == attribution("chmu").fields()
    # No analysis applies to a groundwater object: PIG-PIB stores none
    assert session["root"]["analyses"] == {"IMGW": None, "CHMU": None}
    assert {
        provider: found["kinds"] for provider, found in session["providers"].items()
    } == {
        "IMGW": ["hydro", "meteo"],
        "CHMU": ["hydro", "meteo", "groundwater"],
        "PIG": ["groundwater"],
    }


def test_pig_pibs_hours_are_unverified_as_a_whole_unlike_the_tiers_of_chmus(client):
    datasets = client.get("/api/session").json()["datasets"]

    # PIG-PIB's hours are its automatic measurements alone; ČHMÚ's hourly series joins
    # verified hours to captured ones, each hour naming its tier
    assert {
        key: (datasets[key]["tier"], datasets[key]["unverified"])
        for key in (
            "pl.pig.groundwater_readings",
            "pl.pig.groundwater_subdaily",
            "cz.chmu.hydro_subdaily",
        )
    } == {
        "pl.pig.groundwater_readings": ("verified", False),
        "pl.pig.groundwater_subdaily": ("operational", True),
        "cz.chmu.hydro_subdaily": ("operational", False),
    }


def test_the_lines_of_pig_pibs_points_fill_w_as_the_stations_file_does(client):
    station = client.get(f"/api/stations/{BORE}").json()
    layer = client.get("/api/stations").json()
    listed = client.get(
        "/api/downloads/stations", params={"provider": "PIG", "kind": "groundwater"}
    ).json()
    exported = client.get(listed["formats"]["geojson"]["url"]).json()

    assert filled(station["attribution_parts"]["catalog"]["attribution"]) == (
        CATALOG_W,
    )
    assert FORMULA not in station["attribution"]
    assert filled(layer["attribution"]) == (CATALOG_W,)
    assert FORMULA not in layer["attribution"]
    # The file the page offers carries the lines the page names beside it
    assert listed["attribution"] == exported["attribution"]
    assert listed["terms_notice"] == exported["terms_notice"]
    assert filled(listed["attribution"]) == (CATALOG_W,)
