"""
PIG-PIB's points in the browser (ADR-035, test 19 of the plan): ``groundwater_pl_url``.

„Podziemne” draws PIG-PIB's bore 6495 and spring 1247 as the brown diamond with the
dashed outline of another source; the panel of a point shows PIG-PIB's hydrogeology and
opens the bore's level H_asl or the spring's yield; the hourly series of the automatic
bore is labelled „dane operacyjne, niezweryfikowane”; the strip gives PIG-PIB's short form
WK, the dialog its W filled for what the view shows, WP and RW; and the readings file of
„Pobierz” carries them too.
"""

from __future__ import annotations

import contextlib
import csv
import io
import re
from pathlib import Path
from typing import Any

import pytest

from obserwator.attribution import attribution, fill
from obserwator.datasets import get_provider
from obserwator.messages import message

expect = pytest.importorskip("playwright.sync_api").expect
PlaywrightTimeout = pytest.importorskip("playwright.sync_api").TimeoutError

BORE = "6495"
"""PIG-PIB's automatic bore „Olszyc Szlachecki”: October's readings and hours."""
SPRING = "1247"
"""PIG-PIB's spring „Falsztyn”: October's yields."""
WAIT = 20_000
"""How long a section may take to load [ms]."""
LINES = attribution("pig")
W = fill(get_provider("PIG").license.attribution, period="2026", date="2026-11-24")
"""PIG-PIB's W of the fixture: its points, readings and hours of 2026, captured on
2026-11-24."""
WP, NOTICE = LINES.attribution[1:]
(RW,) = LINES.terms_notice
WK = "Źródło: PIG-PIB, CC BY 4.0"
"""PIG-PIB's short form on the strip (Nogat DEV-20.5)."""
# The icon the map draws of each station shown, by code
_ICONS = """() => {
  const map = document.querySelector('.map').maplibre;
  if (!map || !map.getLayer('stations')) return {};
  const features = map.queryRenderedFeatures({ layers: ['stations'] });
  return Object.fromEntries(features.map((f) => [f.properties.code, f.properties.icon]));
}"""


def card(page: Any, section: str) -> Any:
    """A section's card of the station panel, opened."""
    item = page.locator(f'.acc-item[data-section="{section}"]')
    button = item.locator(".acc-head button")
    button.wait_for(timeout=WAIT)
    if button.get_attribute("aria-expanded") != "true":
        button.click()
    item.locator(".acc-body").wait_for(timeout=WAIT)
    return item


def test_podziemne_draws_pig_pibs_bore_and_spring_with_the_dashed_outline(
    open_page: Any, groundwater_pl_url: str
) -> None:
    page = open_page(base=groundwater_pl_url)
    page.get_by_role("radiogroup", name="Rodzaj stacji").get_by_role(
        "radio", name="Podziemne"
    ).click()

    for code in (BORE, SPRING):
        symbol = page.locator(f'.st-item[data-code="{code}"] svg.sym')
        expect(symbol).to_have_class(re.compile(r"\bgroundwater\b.*\bdashed\b"))
    expect(page.locator(f'.st-item[data-code="{SPRING}"] .st-facts')).to_contain_text(
        "źródło"
    )
    # ČHMÚ's objects beside them, of a national service, keep the solid outline
    expect(
        page.locator('.st-item[data-code="0-203-1-VP0624"] svg.sym')
    ).not_to_have_class(re.compile(r"\bdashed\b"))
    with contextlib.suppress(PlaywrightTimeout):
        page.wait_for_function(
            f"(codes) => codes.every((code) => code in ({_ICONS})())",
            arg=[BORE, SPRING],
            timeout=15_000,
        )
    icons = page.evaluate(_ICONS)
    assert (icons.get(BORE), icons.get(SPRING)) == (
        "st-groundwater-1-other",
        "st-groundwater-1-other",
    )
    # The panel without a station counts PIG-PIB's points by the one kind it publishes
    catalogs = page.locator("#panel-right [data-part=catalogs]")
    expect(catalogs.locator("tr.in-class", has_text="PIG-PIB")).to_contain_text(
        "PIG-PIB: podziemne"
    )
    expect(page.locator("#panel-right [data-part=analyses]")).not_to_contain_text(
        "PIG-PIB"
    )


@pytest.mark.parametrize(
    ("code", "variable", "rows"),
    [
        (
            BORE,
            "H_asl",
            {
                "Numer PSH": "II_963_1",
                "Typ według dostawcy": "st. wiercona",
                "Charakter punktu": "Zwierciadło napięte",
                "Zwierciadło ustalone": "2,7 m p.p.t.",
                "Pomiar automatyczny": "tak",
            },
        ),
        (
            SPRING,
            "spring_yield",
            {
                "Numer PSH": "II_344_1",
                "Typ według dostawcy": "źródło",
                "Charakter punktu": "Pomiar wydajności",
                "Pomiar automatyczny": "nie",
            },
        ),
    ],
)
def test_a_points_panel_shows_its_hydrogeology_and_opens_its_level_or_yield(
    open_page: Any,
    groundwater_pl_url: str,
    code: str,
    variable: str,
    rows: dict[str, str],
) -> None:
    page = open_page(f"?station={code}&section=dane", base=groundwater_pl_url)
    data = card(page, "dane")
    pressed = data.locator('.chips button[aria-pressed="true"]')
    pressed.first.wait_for(timeout=WAIT)
    assert [text.split()[0] for text in pressed.all_inner_texts()] == [variable]
    expect(data.locator(".data-chart svg")).to_have_count(1)
    expect(data.locator(".ds-title")).to_have_text("Odczyty wód podziemnych (PIG-PIB)")
    expect(data.locator("[data-part=dataset-note]")).to_have_text(
        str(message("gui.words.dataset.pl_pig_groundwater_readings.note", "pl"))
    )

    info = card(page, "stacja")
    expect(info.locator("tr", has_text="Położenie (WGS84)")).to_contain_text(
        "punkty monitoringu PIG-PIB, wody podziemne"
    )
    for label, value in rows.items():
        row = info.locator("tr", has=page.locator("th", has_text=label))
        expect(row.locator("td")).to_have_text(value)
    section = info.locator("section.ana", has=page.locator("[data-part=hydrogeology]"))
    expect(section.locator(".ana-head h3")).to_have_text("Hydrogeologia")
    section.locator(".info-btn").click()
    expect(section.get_by_role("link", name="Więcej w instrukcji")).to_have_attribute(
        "href", "instrukcja/#pig"
    )


def test_the_hours_of_the_automatic_bore_are_labelled_operational_unverified(
    open_page: Any, groundwater_pl_url: str
) -> None:
    page = open_page(f"?station={BORE}&section=dane", base=groundwater_pl_url)
    data = card(page, "dane")
    title = data.locator(".ds-title")
    expect(title.locator("[data-part=unverified]")).to_have_count(0)

    data.get_by_role("radio", name="Godzinowe").click()

    expect(title).to_have_text(
        "Dane godzinowe wód podziemnych (PIG-PIB) dane operacyjne, niezweryfikowane"
    )
    expect(title.locator("[data-part=unverified]")).to_have_text(
        "dane operacyjne, niezweryfikowane"
    )
    expect(data.locator(".data-chart")).to_contain_text(
        "H_asl — rzędna zwierciadła wody (zapisane odpowiedzi: dane operacyjne,"
        " niezweryfikowane)"
    )
    # one tier: no word on how the tiers of several are chosen
    expect(data).not_to_contain_text(str(message("gui.station.data.tiers_def", "pl")))
    record = page.locator(".station-head .station-record")
    expect(record.locator("[data-part=unverified]")).to_have_count(1)


def test_the_strip_gives_wk_and_the_dialog_w_wp_and_rw_of_what_is_shown(
    open_page: Any, groundwater_pl_url: str
) -> None:
    welcome = open_page(base=groundwater_pl_url, welcome=True).locator("dialog.welcome")
    expect(welcome).to_be_visible(timeout=WAIT)
    for line in (W, WP, NOTICE, RW):
        expect(welcome).to_contain_text(line)
    expect(welcome).not_to_contain_text("<period>")

    page = open_page(f"?station={BORE}&section=dane", base=groundwater_pl_url)
    card(page, "dane").locator(".data-chart svg").wait_for(timeout=WAIT)
    strip = page.locator(".view-foot nogat-sources")
    expect(strip.locator(".nogat-sources-strip")).to_contain_text(WK)
    expect(strip.locator(".nogat-sources-strip")).not_to_contain_text(
        "Monitoring Wód Podziemnych"
    )
    strip.get_by_role("button", name="Źródła i warunki").click()
    dialog = strip.locator("dialog")
    expect(dialog).to_be_visible()
    # the catalog's W and the readings' merge into one line
    shown = dialog.locator("li", has_text="Państwowy Instytut Geologiczny")
    expect(shown).to_have_text([W])
    for line in (WP, NOTICE, RW):
        expect(dialog).to_contain_text(line)
    expect(dialog).not_to_contain_text("<period>")


def test_the_readings_file_carries_w_wp_and_rw_in_its_last_two_columns(
    open_page: Any, groundwater_pl_url: str
) -> None:
    page = open_page(f"?station={BORE}&section=pobierz", base=groundwater_pl_url)
    files = card(page, "pobierz")
    name = f"obserwator_series_pl.pig.groundwater_readings_{BORE}.csv"
    link = files.locator(f'.files a[download="{name}"]')
    link.wait_for(timeout=WAIT)
    terms = files.get_by_role("link", name="Regulamin PIG-PIB").first
    expect(terms).to_have_attribute("href", get_provider("PIG").license.terms_url or "")

    with page.expect_download(timeout=WAIT) as started:
        link.click()
    assert started.value.suggested_filename == name
    text = Path(started.value.path()).read_text(encoding="utf-8")
    header, *rows = list(csv.reader(io.StringIO(text, newline="")))

    assert header[-2:] == ["attribution", "terms_notice"]
    assert [row[-2] for row in rows if row[-2]] == [W, WP, NOTICE]
    assert [row[-1] for row in rows if row[-1]] == [RW]
