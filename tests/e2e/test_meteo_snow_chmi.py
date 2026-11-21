"""
ČHMÚ's snow in the card „Śnieg” (3.1.0, ADR-003 erratum of 2026-11-21).

`cz.chmi.meteo_daily` carries ČHMÚ's total snow depth (SCE) and new snow (SNO) as
``snow_cover`` and ``fresh_snow``, so a ČHMÚ climate station of the fixture root gets
Hydrolog's ``snow`` analysis (stored by the recorded Hydrolog of ``stored_url``) and the
card IMGW-PIB's stations have, with ČHMÚ named among the data of its information.
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from typing import Any

import pytest

from tests.e2e.conftest import FIXTURE_STATIONS

expect = pytest.importorskip("playwright.sync_api").expect

METEO_CHMI = FIXTURE_STATIONS["meteo_chmi"]
WAIT = 20_000
"""How long a section may take to load [ms]."""


def listed(base: str, code: str) -> set[str]:
    """The ids of the stored analyses of a station, as the page gets them."""
    url = f"{base}api/analyses/{urllib.parse.quote(code)}"
    with urllib.request.urlopen(url, timeout=60) as answer:
        document: dict[str, Any] = json.load(answer)
    return {entry["analysis"] for entry in document["analyses"]}


def test_a_chmi_station_with_snow_measurements_has_the_snow_card(
    open_page: Any, stored_url: str
) -> None:
    assert "snow" in listed(stored_url, METEO_CHMI)

    page = open_page(f"?station={METEO_CHMI}&section=snieg", base=stored_url)
    snow = page.locator('.acc-item[data-section="snieg"]')
    cover = snow.locator("section.ana").filter(
        has=page.locator("h3", has_text="Pokrywa śnieżna")
    )
    expect(cover.locator("dl.figures")).to_be_visible(timeout=WAIT)
    expect(cover.locator(".ana-prov code", has_text="meteo snow").first).to_be_visible()
    cover.locator("button.info-btn").first.click()
    expect(cover.locator(".ana-info")).to_contain_text(
        "ČHMÚ (wysokość pokrywy SCE, śnieg świeży SNO)"
    )
