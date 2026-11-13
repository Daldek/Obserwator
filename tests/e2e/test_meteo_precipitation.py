"""
The meteorological sections „Opady” and „Susze i okresy bezopadowe” on a root with long
records, computed by Hydrolog's program (GUI plan S6, D11; Nogat plan M1 to M9).

The page draws the results of the analysis ids of the API (``api/analysis/{code}/{id}``):
the numbers it shows are compared with those documents. Kraków (IMGW-PIB climate station,
1961–2025), Praha-Klementinum (ČHMÚ, precipitation since 1804) and Nowogród Bobrzański
(IMGW-PIB precipitation post with totals of several days after days without a measurement).
"""

from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from typing import Any

import pytest

pytestmark = pytest.mark.hydrolog

KRAKOW = "250190390"
PRAHA = "0-203-0-11514"
POST = "251150030"
"""Nowogród Bobrzański, a station of ``pl.imgw.meteo_precip_daily``."""
STATIONS = [
    pytest.param(KRAKOW, id="krakow"),
    pytest.param(PRAHA, id="praha"),
    pytest.param(POST, id="precipitation_post"),
]
WAIT = 180_000
"""How long a section may take: Hydrolog computes every id on request [ms]."""


def analysis(base: str, code: str, id_: str, **overrides: Any) -> dict[str, Any]:
    """Hydrolog's result of an id as the API serves it to the page."""
    query = urllib.parse.urlencode(overrides)
    url = f"{base}api/analysis/{urllib.parse.quote(code)}/{id_}"
    with urllib.request.urlopen(
        f"{url}?{query}" if query else url, timeout=180
    ) as answer:
        document: dict[str, Any] = json.load(answer)
    assert document["status"] == "ok", document.get("error")
    result: dict[str, Any] = document["envelope"]["result"]
    return result


def number(text: str) -> float:
    """The first number of a text in either language: „1 060,5 mm” → 1060.5."""
    found = re.search(r"[−-]?\d[\d\u00a0\u202f ,]*(?:[.,]\d+)?", text)
    assert found, text
    plain = re.sub(r"[\u00a0\u202f ]", "", found.group(0)).replace("−", "-")
    if "," in plain and "." not in plain and re.search(r",\d{1,2}$", plain):
        plain = plain.replace(",", ".")
    return float(plain.replace(",", ""))


def section(open_page: Any, base: str, code: str, name: str, **options: Any) -> Any:
    """The station's panel with one section open; its card."""
    page = open_page(f"?station={code}&section={name}", base=base, **options)
    return page.locator(f'[data-section="{name}"]')


def part(card: Any, title: str) -> Any:
    """A part of a card by its heading."""
    return card.locator("section.ana").filter(
        has=card.page.locator("h3", has_text=re.compile(f"^{re.escape(title)}$"))
    )


def figure(where: Any, label: str) -> str:
    """The value of a key figure whose label starts with ``label``."""
    tile = where.locator("dl.figures > div").filter(
        has=where.page.locator("dt", has_text=re.compile(f"^{re.escape(label)}"))
    )
    text: str = tile.locator("dd").first.inner_text(timeout=WAIT)
    return text


def note(where: Any, label: str) -> str:
    """The note under a key figure whose label starts with ``label``."""
    tile = where.locator("dl.figures > div").filter(
        has=where.page.locator("dt", has_text=re.compile(f"^{re.escape(label)}"))
    )
    text: str = tile.locator("small").first.inner_text(timeout=WAIT)
    return text


def provenance(where: Any, command: str) -> None:
    """The part names Hydrolog's command that computed its numbers."""
    where.locator(".ana-prov .prov-hydrolog code", has_text=command).first.wait_for(
        timeout=WAIT
    )


@pytest.mark.parametrize("code", STATIONS)
def test_precipitation_shows_hydrologs_numbers_with_their_provenance(
    open_page: Any, analysis_url: str, code: str
) -> None:
    card = section(open_page, analysis_url, code, "opady")

    sums = part(card, "Sumy opadów i normalna")
    found = analysis(analysis_url, code, "precipitation.sums")
    assert number(figure(sums, "Normalna ")) == pytest.approx(
        found["period"]["normal_mm"], abs=0.5
    )
    assert number(figure(sums, "Średnia suma roczna")) == pytest.approx(
        found["period"]["mean_mm"], abs=0.5
    )
    provenance(sums, "meteo precipitation")

    regime = analysis(analysis_url, code, "precipitation.seasonality")
    shown = figure(part(card, "Reżim i sezonowość opadów"), "PCI normalnych")
    assert number(shown) == pytest.approx(regime["period"]["pci"], abs=0.05)

    days = analysis(analysis_url, code, "precipitation.days")
    tens = days["thresholds_mm"].index(10.0)
    shown = figure(part(card, "Dni z opadem i natężenie"), "Dni ≥ 10 mm")
    assert number(shown) == pytest.approx(days["period"]["days"][tens], abs=0.5)

    heavy = analysis(analysis_url, code, "precipitation.heavy")
    shown = figure(part(card, "Opady duże (R95p, R99p)"), "Próg P95")
    assert number(shown) == pytest.approx(heavy["period"]["thresholds_mm"][0], abs=0.05)

    maxima = analysis(analysis_url, code, "precipitation.maxima")
    shown = figure(part(card, "Opady maksymalne 1–10 dni"), "Średnie maksimum")
    one_day = maxima["period"]["durations"][0]
    assert one_day["days"] == 1
    assert number(shown) == pytest.approx(one_day["mean_mm"], abs=0.05)

    quantiles = part(card, "Opad maksymalny o prawdopodobieństwie p")
    fit = analysis(analysis_url, code, "precipitation_quantiles")
    best = fit["distributions"][0]
    hundred = best["quantiles"][best["return_periods"].index(100.0)]
    assert number(figure(quantiles, "p = 1 %")) == pytest.approx(hundred, abs=0.05)
    assert number(figure(quantiles, "Lata (maksimów)")) == fit["n_years"]
    provenance(quantiles, "stats flood-frequency")


@pytest.mark.parametrize("code", STATIONS)
def test_droughts_show_hydrologs_numbers_with_their_provenance(
    open_page: Any, analysis_url: str, code: str
) -> None:
    card = section(open_page, analysis_url, code, "susze")

    spells = part(card, "Okresy bezopadowe i opadowe")
    dry = analysis(analysis_url, code, "spells.dry")
    shown = figure(spells, "Najdłuższy w roku, średnio")
    assert number(shown) == pytest.approx(
        dry["period"]["mean_max_duration_days"], abs=0.05
    )
    assert number(figure(spells, "Najdłuższy w zapisie")) == dry["max_duration_days"]
    assert f"P < {dry['threshold_mm']:g} mm" in note(spells, "Najdłuższy w roku")
    provenance(spells, "meteo spells")

    spi = analysis(analysis_url, code, "spi")
    calibration = figure(
        part(card, "Wskaźnik standaryzowanego opadu SPI"), "Kalibracja"
    )
    assert calibration == f"{spi['reference_first_year']}–{spi['reference_last_year']}"
    relative = part(card, "Opad względny i jego klasy")
    assert number(figure(relative, "Normalna ")) == pytest.approx(
        spi["period"]["normal_mm"], abs=0.5
    )
    newest = spi["years"][-1]
    row = relative.locator("table.me-heat tbody tr").first
    assert number(row.locator("th").inner_text(timeout=WAIT)) == newest["year"]
    assert number(row.locator("td").last.inner_text()) == pytest.approx(
        newest["percent_of_normal"], abs=0.5
    )
    provenance(relative, "meteo spi")


def test_a_dry_spell_threshold_chosen_by_the_person_recomputes(
    open_page: Any, analysis_url: str
) -> None:
    card = section(open_page, analysis_url, KRAKOW, "susze")
    spells = part(card, "Okresy bezopadowe i opadowe")
    stored = figure(spells, "Najdłuższy w roku, średnio")

    spells.locator(".me-threshold input[type=number]").fill("2.5")
    spells.locator(".me-threshold button[type=submit]").click()
    card.page.wait_for_function(
        """() => [...document.querySelectorAll('[data-section="susze"] dl.figures small')]
            .some((note) => note.textContent.includes("P < 2,5 mm"))""",
        timeout=WAIT,
    )

    chosen = analysis(analysis_url, KRAKOW, "spells.dry", threshold_mm=2.5)
    assert chosen["threshold_mm"] == 2.5
    shown = figure(spells, "Najdłuższy w roku, średnio")
    assert shown != stored
    assert number(shown) == pytest.approx(
        chosen["period"]["mean_max_duration_days"], abs=0.05
    )
    spells.locator(
        ".ana-prov .prov-hydrolog", has_text="policzony na żądanie"
    ).wait_for(timeout=WAIT)


def test_precipitation_fits_a_phone_in_english_and_the_dark_theme(
    open_page: Any, analysis_url: str
) -> None:
    card = section(
        open_page, analysis_url, KRAKOW, "opady", theme="dark", width=390, lang="en"
    )
    sums = part(card, "Precipitation totals and the normal")
    found = analysis(analysis_url, KRAKOW, "precipitation.sums")
    assert number(figure(sums, "Normal ")) == pytest.approx(
        found["period"]["normal_mm"], abs=0.5
    )
    chart = sums.locator(".chart svg").first
    chart.wait_for(timeout=WAIT)
    box = chart.bounding_box()
    assert box is not None and box["x"] >= 0 and box["x"] + box["width"] <= 390
    assert card.page.evaluate("document.documentElement.scrollWidth") <= 390
