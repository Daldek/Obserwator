"""
„Stany charakterystyczne” of a ČHMÚ station on the stored results of the fixture root.

ČHMÚ publishes no half-year characteristics: those of a ČHMÚ station are computed by
Obserwator from its daily series (the author's decision of 2026-11-18), and the card says
so wherever it names IMGW-PIB's half-years for an IMGW-PIB station: the caption of the
second degree, the title of its small numbers, the choice of the source and the source of
each year of the first degree.
"""

from __future__ import annotations

import re
from typing import Any

import pytest

from tests.e2e.conftest import FIXTURE_STATIONS

expect = pytest.importorskip("playwright.sync_api").expect

CHMU = FIXTURE_STATIONS["hydro_chmu"]
WAIT = 20_000
"""How long a section may take to load [ms]."""
TEXTS: dict[str, dict[str, Any]] = {
    "pl": {
        "caption": (
            "Mniejsze: Hydrolog z charakterystyk półrocznych, które Obserwator obliczył "
            "z szeregu dobowego ČHMÚ, bo ČHMÚ ich nie publikuje"
        ),
        "alt": (
            "Z charakterystyk półrocznych obliczonych przez Obserwatora z szeregu "
            "dobowego ČHMÚ"
        ),
        "source": "Źródło",
        "sources": [
            "półrocza obliczone, pozostałe lata dobowe",
            "półrocza obliczone",
            "szereg dobowy",
        ],
        "second": "Wartości II stopnia",
        "first": "Wartości I stopnia w latach",
    },
    "en": {
        "caption": (
            "Small type: Hydrolog from half-year characteristics that Obserwator "
            "computed from ČHMÚ's daily series, as ČHMÚ publishes none"
        ),
        "alt": (
            "From the half-year characteristics Obserwator computed from ČHMÚ's daily "
            "series"
        ),
        "source": "Source",
        "sources": [
            "computed half-years, other years daily",
            "computed half-years",
            "daily series",
        ],
        "second": "Second-degree values",
        "first": "First-degree values by year",
    },
}
"""The card's texts of computed half-years, by the page's language."""


@pytest.mark.parametrize("lang", ["pl", "en"])
def test_a_chmu_station_calls_its_half_years_computed_not_imgws(
    open_page: Any, stored_url: str, lang: str
) -> None:
    texts = TEXTS[lang]
    page = open_page(
        f"?station={CHMU}&section=characteristic", base=stored_url, lang=lang
    )
    card = page.locator('[data-section="characteristic"]')
    stored = page.request.get(
        f"{stored_url}api/analysis/{CHMU}/characteristic.Q.half_years"
    ).json()
    assert (stored["status"], stored["derived"]) == ("ok", "half_years")

    def part(title: str) -> Any:
        """The part of the card under the sub-title ``title``."""
        return card.locator("section.ana").filter(
            has=page.locator("h3", has_text=re.compile(f"^{re.escape(title)}$"))
        )

    caption = part(texts["second"]).locator(".hy-caption")
    expect(caption).to_contain_text(texts["caption"], timeout=WAIT)
    expect(caption).not_to_contain_text("IMGW-PIB")
    expect(card.locator(".hy-matrix small.hy-alt").first).to_have_attribute(
        "title", texts["alt"]
    )
    choice = card.get_by_role("radiogroup", name=texts["source"])
    expect(choice.get_by_role("radio")).to_have_text(texts["sources"])
    # Every year of the first degree here comes from the computed half-years
    cells = part(texts["first"]).locator("table.tbl tbody tr td:last-child")
    expect(cells.first).to_have_text(texts["sources"][1], timeout=WAIT)
    for text in cells.all_inner_texts():
        assert text == texts["sources"][1]
