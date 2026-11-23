"""
ČHMÚ's groundwater objects in the browser (ADR-032) on the fixture variant ``groundwater``.

The map and the list draw them as the GUI's own brown diamond, the kind switch offers
„Podziemne” two by two with the other choices and keeps only them, and the panel of an
object names it a bore („otwór obserwacyjny”) or a spring („źródło”), has no „Pomiary
bieżące” and shows first the bore's level H_asl or the spring's yield; a weekly series
counts its rows as readings. Skipped while the variant does not exist (``groundwater_url``).
"""

from __future__ import annotations

import contextlib
import json
import re
from typing import Any
from urllib.request import urlopen

import pytest

from obserwator.messages import message

expect = pytest.importorskip("playwright.sync_api").expect
PlaywrightTimeout = pytest.importorskip("playwright.sync_api").TimeoutError

BORE = "0-203-1-VP0624"
"""ČHMÚ's bore „Rakousy”: daily 2024, weekly 2012."""
SPRING = "0-203-1-PP0744"
"""ČHMÚ's spring „Želechy”: daily 2024, weekly 2014."""
WAIT = 20_000
"""How long a section may take to load [ms]."""
_ICONS = """() => {
  const map = document.querySelector('.map').maplibre;
  const features = map.queryRenderedFeatures({ layers: ['stations'] });
  return [...new Set(features.map((feature) => feature.properties.icon))].sort();
}"""


def stations(base: str) -> list[dict[str, Any]]:
    with urlopen(base + "api/stations") as response:
        found: list[dict[str, Any]] = json.load(response)["stations"]
    return found


def listed(page: Any) -> list[str]:
    rows = page.locator(".stations .st-item")
    return sorted(
        rows.evaluate_all("(items) => items.map((item) => item.dataset.code)")
    )


def wait_listed(page: Any, codes: list[str]) -> None:
    with contextlib.suppress(PlaywrightTimeout):
        page.wait_for_function(
            "(codes) => JSON.stringify([...document.querySelectorAll('.stations .st-item')]"
            ".map((item) => item.dataset.code).sort()) === JSON.stringify(codes)",
            arg=sorted(codes),
            timeout=10_000,
        )
    assert listed(page) == sorted(codes)


def card(page: Any, section: str) -> Any:
    """A section's card of the station panel, opened."""
    item = page.locator(f'.acc-item[data-section="{section}"]')
    button = item.locator(".acc-head button")
    button.wait_for(timeout=WAIT)
    if button.get_attribute("aria-expanded") != "true":
        button.click()
    item.locator(".acc-body").wait_for(timeout=WAIT)
    return item


def test_podziemne_keeps_the_groundwater_objects_drawn_as_brown_diamonds(
    open_page: Any, groundwater_url: str
) -> None:
    catalog = stations(groundwater_url)
    objects = sorted(s["code"] for s in catalog if s["kind"] == "groundwater")
    assert {BORE, SPRING} <= set(objects)
    page = open_page(base=groundwater_url)
    page.get_by_role("checkbox", name="tylko czynne").uncheck()
    group = page.get_by_role("radiogroup", name="Rodzaj stacji")
    radios = group.get_by_role("radio")
    expect(radios).to_have_text(
        ["Hydrologiczne", "Meteorologiczne", "Podziemne", "Wszystkie"]
    )
    # two by two: Podziemne under Hydrologiczne, Wszystkie beside it
    hydro, meteo, groundwater, every = radios.evaluate_all(
        "(items) => items.map((item) => { const box = item.getBoundingClientRect();"
        " return { x: box.x, y: box.y }; })"
    )
    assert abs(hydro["y"] - meteo["y"]) < 1
    assert abs(groundwater["y"] - every["y"]) < 1
    assert groundwater["y"] > hydro["y"]
    assert abs(groundwater["x"] - hydro["x"]) < 1
    assert abs(every["x"] - meteo["x"]) < 1

    radios.nth(2).click()
    wait_listed(page, objects)
    for code in (BORE, SPRING):
        symbol = page.locator(f'.st-item[data-code="{code}"] svg.sym')
        expect(symbol).to_have_class(re.compile(r"\bgroundwater\b"))
    expect(page.locator(f'.st-item[data-code="{SPRING}"] .st-facts')).to_contain_text(
        "źródło"
    )
    page.wait_for_function(
        "() => { const map = document.querySelector('.map').maplibre;"
        " return map && map.queryRenderedFeatures({ layers: ['stations'] }).length > 0; }",
        timeout=15_000,
    )
    assert set(page.evaluate(_ICONS)) <= {"st-groundwater-0", "st-groundwater-1"}
    legend = page.locator(".map-legend")
    diamond = legend.locator("li", has_text="wód podziemnych").locator("svg.sym")
    expect(diamond).to_have_class(re.compile(r"\bgroundwater\b"))
    fill = diamond.locator(".body").evaluate("(path) => getComputedStyle(path).fill")
    assert fill == "rgb(160, 97, 42)"
    expect(legend).to_contain_text(
        str(message("gui.stations.legend.groundwater_note", "pl"))
    )


@pytest.mark.parametrize(
    ("code", "word", "variable"),
    [(SPRING, "źródło", "spring_yield"), (BORE, "otwór obserwacyjny", "H_asl")],
)
def test_the_panel_names_a_bore_or_a_spring_and_shows_its_level_or_yield(
    open_page: Any, groundwater_url: str, code: str, word: str, variable: str
) -> None:
    page = open_page(f"?station={code}&section=dane", base=groundwater_url)
    head = page.locator(".station-head")
    head.wait_for(timeout=WAIT)

    expect(head.locator(".station-tags")).to_contain_text(word)
    order = page.locator(".acc-item").evaluate_all(
        "items => items.map((item) => item.dataset.section)"
    )
    assert order == ["stacja", "dane", "pobierz"]
    data = card(page, "dane")
    pressed = data.locator('.chips button[aria-pressed="true"]')
    pressed.first.wait_for(timeout=WAIT)
    assert [text.split()[0] for text in pressed.all_inner_texts()] == [variable]
    expect(data.locator(".data-chart svg")).to_have_count(1)
    info = card(page, "stacja")
    row = info.locator("tr", has_text="Rodzaj obiektu")
    expect(row.locator("td")).to_have_text(word)


def test_a_weekly_series_counts_its_readings(
    open_page: Any, groundwater_url: str
) -> None:
    page = open_page(f"?station={BORE}&section=dane", base=groundwater_url)
    data = card(page, "dane")
    data.get_by_role("radio", name="Tygodniowe").click()
    expect(data.locator(".ds-title")).to_have_text(
        "Dane tygodniowe wód podziemnych (ČHMÚ)"
    )
    data.get_by_role("button", name="Tabela").click()

    expect(data.locator(".pager")).to_contain_text(re.compile(r"odczyt"))
    expect(data.locator(".data-foot")).to_contain_text(
        str(message("gui.station.data.weekly_def", "pl"))
    )
