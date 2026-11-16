"""
The meteorological sections „Temperatura” (with the climate stripes), „Śnieg” and „Trendy”
on a root with long records and the analyses ``obserwator analyses build`` stored (GUI
plan S6, D11; Nogat plan M10 to M15).

The page draws the results of the analysis ids of the API (``api/analysis/{code}/{id}``)
and the stripes of the M15 prototype (``api/prototype/stripes/{code}``): a section opens
with the stored results, so the numbers it shows are compared with the stored documents
(``source: stored``); the stripes' normal of their reference period is computed by
Hydrolog's program on request and compared with the API's document of the same options
(``source: computed``). Kraków (IMGW-PIB climate station, 1961–2025) and
Praha-Klementinum (ČHMÚ, temperature since 1775, no snow cover).
"""

from __future__ import annotations

import csv
import html
import io
import json
import re
import urllib.parse
import urllib.request
from typing import Any

import pytest

from tests.e2e.conftest import THEMES, WIDTHS

pytestmark = pytest.mark.hydrolog

KRAKOW = "250190390"
PRAHA = "0-203-0-11514"
STATIONS = [pytest.param(KRAKOW, id="krakow"), pytest.param(PRAHA, id="praha")]
WAIT = 180_000
"""How long a section may take: Hydrolog computes the stripes' normal on request [ms]."""
SOURCE = {True: "wynik zapisany", False: "policzony na żądanie"}
"""The provenance chip of a stored result and of one computed on request."""


def get(base: str, path: str, **query: Any) -> dict[str, Any]:
    """A document of the API, as the page gets it."""
    text = urllib.parse.urlencode(query)
    with urllib.request.urlopen(
        f"{base}{path}?{text}" if text else f"{base}{path}", timeout=180
    ) as answer:
        document: dict[str, Any] = json.load(answer)
    return document


def analysis(base: str, code: str, id_: str, **overrides: Any) -> dict[str, Any]:
    """
    Hydrolog's result of an id as the API serves it to the page: the stored one, or with
    a person's ``overrides`` the one computed on request.
    """
    document = get(base, f"api/analysis/{urllib.parse.quote(code)}/{id_}", **overrides)
    assert document["status"] == "ok", document.get("error")
    assert document["source"] == ("computed" if overrides else "stored")
    result: dict[str, Any] = document["envelope"]["result"]
    return result


def stripes(base: str, code: str, **options: Any) -> dict[str, Any]:
    """The stripes document of the prototype."""
    document = get(base, f"api/prototype/stripes/{urllib.parse.quote(code)}", **options)
    assert document["status"] == "ok", document.get("error")
    return document


def number(text: str) -> float:
    """The first number of a text in either language: „−1,23 °C” → -1.23."""
    found = re.search(r"[−+-]?\d[\d\u00a0\u202f ]*(?:[.,]\d+)?", text)
    assert found, text
    plain = re.sub(r"[\u00a0\u202f ]", "", found.group(0)).replace("−", "-")
    return float(plain.replace(",", "."))


def card(open_page: Any, base: str, code: str, name: str, **options: Any) -> Any:
    """The station's panel with one section open; its card."""
    page = open_page(f"?station={code}&section={name}", base=base, **options)
    return page.locator(f'[data-section="{name}"]')


def part(where: Any, title: str) -> Any:
    """A part of a card by its heading."""
    return where.locator("section.ana").filter(
        has=where.page.locator("h3", has_text=re.compile(f"^{re.escape(title)}$"))
    )


def figure(where: Any, label: str) -> str:
    """The value of a key figure whose label starts with ``label``."""
    tile = where.locator("dl.figures > div").filter(
        has=where.page.locator("dt", has_text=re.compile(f"^{re.escape(label)}"))
    )
    text: str = tile.locator("dd").first.inner_text(timeout=WAIT)
    return text


def provenance(where: Any, command: str, *, stored: bool = True) -> None:
    """The part names Hydrolog's command and whether its result is stored or computed."""
    chip = where.locator(".ana-prov .prov-hydrolog", has_text=SOURCE[stored]).filter(
        has=where.page.locator("code", has_text=command)
    )
    chip.first.wait_for(timeout=WAIT)


@pytest.mark.parametrize("code", STATIONS)
def test_temperature_shows_hydrologs_means_days_harmonics_and_coefficient(
    open_page, analysis_url, code
):
    temperature = card(open_page, analysis_url, code, "temperatura")
    means = part(temperature, "Średnie, ekstrema i normalna")
    result = analysis(analysis_url, code, "temperature.means")
    period = result["period"]
    normal = figure(
        means,
        f"Normalna {result['reference_first_year']}–{result['reference_last_year']}",
    )
    assert number(normal) == pytest.approx(period["normal_c"], abs=0.051)
    assert number(figure(means, "Najwyższa Tmax")) == pytest.approx(period["max_c"])
    provenance(means, "meteo temperature")
    # the table of years lists Hydrolog's newest year first
    last = result["years"][-1]
    first_row = means.locator("table").nth(1).locator("tbody tr").first
    assert first_row.locator("td").first.inner_text() == str(last["year"])
    assert number(first_row.locator("td").nth(1).inner_text()) == pytest.approx(
        last["tmean_c"], abs=0.006
    )
    days = analysis(analysis_url, code, "temperature.days")["period"]
    characteristic = part(temperature, "Dni charakterystyczne i stopniodni")
    assert number(figure(characteristic, "z przymrozkiem")) == pytest.approx(
        days["frost_days"], abs=0.051
    )
    harmonics = analysis(analysis_url, code, "harmonics.Tmean")["period"]
    cycle = part(temperature, "Cykl roczny i harmoniki")
    assert number(figure(cycle, "Amplituda C₁")) == pytest.approx(
        harmonics["harmonics"][0]["amplitude"], abs=0.006
    )
    provenance(cycle, "stats harmonics")
    coefficient = analysis(analysis_url, code, "hydrothermal")["period"]
    hydrothermal = part(temperature, "Współczynnik hydrotermiczny")
    assert number(figure(hydrothermal, "k okresu")) == pytest.approx(
        coefficient["mean_season_coefficient"], abs=0.006
    )
    provenance(hydrothermal, "meteo hydrothermal")


@pytest.mark.parametrize("code", STATIONS)
def test_the_stripes_take_hydrologs_normal_and_name_its_computation(
    open_page, analysis_url, code
):
    temperature = card(open_page, analysis_url, code, "temperatura")
    section = part(temperature, "Paski klimatyczne")
    section.locator("svg.stripes").wait_for(timeout=WAIT)
    provenance(section, "meteo temperature", stored=False)
    document = stripes(analysis_url, code)
    centre = document["scale"]["centre"]
    # the centre is Hydrolog's normal of 1961–2010, the scale's reference period
    reference = analysis(
        analysis_url,
        code,
        "temperature.means",
        reference_first_year=1961,
        reference_last_year=2010,
    )
    assert (centre["first_year"], centre["last_year"]) == (1961, 2010)
    assert centre["normal_c"] == pytest.approx(reference["period"]["normal_c"])
    assert number(figure(section, "Średnia 1961–2010")) == pytest.approx(
        centre["normal_c"], abs=0.006
    )
    # one stripe a year, coloured by the server's scale
    rects = section.locator("svg.stripes > rect")
    assert rects.count() == len(document["years"]) + len(document["grey"])
    first = document["years"][0]
    assert rects.first.get_attribute("fill") == document["palette"][first["colour"]]
    # the other scale of the FAQ moves the centre to 1971–2000
    section.locator(".seg button", has_text="FAQ z 2019").click()
    section.locator("dl.figures dt", has_text="Średnia 1971–2000").wait_for(
        timeout=WAIT
    )


def test_the_stripes_files_carry_the_station_the_credit_and_the_lines(
    open_page, analysis_url
):
    temperature = card(open_page, analysis_url, KRAKOW, "temperatura")
    section = part(temperature, "Paski klimatyczne")
    section.locator("svg.stripes").wait_for(timeout=WAIT)
    document = stripes(analysis_url, KRAKOW)
    lines = document["attribution"] + document["terms_notice"]
    assert lines
    page = temperature.page
    files = {}
    for fmt in ("PNG", "SVG", "CSV"):
        with page.expect_download() as download:
            section.locator("button", has=page.locator(".fmt", has_text=fmt)).click()
        files[fmt] = (download.value.suggested_filename, download.value.path())
    png_name, png_path = files["PNG"]
    assert png_name == "paski-klimatyczne-250190390-1961-2025.png"
    assert png_path.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    svg = files["SVG"][1].read_text(encoding="utf-8")
    # the image's texts, its wrapped lines joined again
    drawn = " ".join(
        html.unescape(text) for text in re.findall(r"<text[^>]*>(.*?)</text>", svg)
    )
    assert "KRAKÓW" in drawn.upper()
    assert "#ShowYourStripes" in drawn and "https://showyourstripes.info" in drawn
    for line in lines:
        assert line in drawn
    table = list(csv.DictReader(io.StringIO(files["CSV"][1].read_text("utf-8"))))
    assert [int(row["year"]) for row in table] == [y["year"] for y in document["years"]]
    assert float(table[-1]["anomaly_C"]) == pytest.approx(
        document["years"][-1]["anomaly_c"]
    )
    attribution = "\n".join(row["attribution"] for row in table if row["attribution"])
    terms = "\n".join(row["terms_notice"] for row in table if row["terms_notice"])
    assert attribution.split("\n") == document["attribution"]
    assert terms.split("\n") == document["terms_notice"]
    assert "#ShowYourStripes" in table[0]["method"]


def test_snow_shows_the_winters_hydrolog_counted(open_page, analysis_url):
    snow = card(open_page, analysis_url, KRAKOW, "snieg")
    result = analysis(analysis_url, KRAKOW, "snow")
    period = result["period"]
    cover = part(snow, "Pokrywa śnieżna")
    assert number(figure(cover, "Dni z pokrywą ≥ 1 cm")) == pytest.approx(
        period["mean_cover_days"], abs=0.51
    )
    assert number(figure(cover, "Największa grubość")) == pytest.approx(
        period["max_depth_cm"]
    )
    provenance(cover, "meteo snow")
    newest = result["years"][-1]["year"]
    first_row = cover.locator("table").nth(1).locator("tbody tr").first
    assert first_row.locator("td").first.inner_text() == (
        f"{newest - 1}/{str(newest)[2:]}"
    )


def test_a_czech_station_has_no_snow(open_page, analysis_url):
    page = open_page(f"?station={PRAHA}", base=analysis_url)
    page.locator('[data-section="temperatura"]').wait_for(timeout=WAIT)
    assert page.locator('[data-section="snieg"]').count() == 0


@pytest.mark.parametrize("code", STATIONS)
def test_trends_show_hydrologs_mann_kendall_of_each_annual_series(
    open_page, analysis_url, code
):
    trends = card(open_page, analysis_url, code, "trendy")
    ids = [
        entry["analysis"]
        for entry in get(analysis_url, f"api/analyses/{urllib.parse.quote(code)}")[
            "analyses"
        ]
        if entry["analysis"].startswith("mann_kendall.")
        and entry["analysis"].split(".")[1]
        in ("precipitation", "spells", "temperature")
    ]
    assert "mann_kendall.temperature.means" in ids
    table = trends.locator("section.ana table").first
    table.locator("tbody tr").nth(len(ids) - 1).wait_for(timeout=WAIT)
    assert table.locator("tbody tr").count() == len(ids)
    result = analysis(analysis_url, code, "mann_kendall.temperature.means")
    row = table.locator("tbody tr").filter(has_text="Średnia roczna temperatura")
    cells = row.locator("td")
    cells.nth(5).filter(has_text=re.compile(r"\d")).wait_for(timeout=WAIT)
    assert number(cells.nth(5).inner_text()) == pytest.approx(
        result["p_value"], abs=0.0006
    )
    assert number(cells.nth(2).inner_text()) == pytest.approx(
        10 * result["sen_slope"], abs=0.006
    )
    provenance(trends, "stats mann-kendall")


@pytest.mark.parametrize("theme", THEMES)
@pytest.mark.parametrize("width", WIDTHS)
@pytest.mark.parametrize("lang", ["pl", "en"])
def test_the_stripes_draw_in_both_themes_languages_and_widths(
    open_page, analysis_url, theme, width, lang
):
    temperature = card(
        open_page,
        analysis_url,
        KRAKOW,
        "temperatura",
        theme=theme,
        width=width,
        lang=lang,
    )
    title = "Paski klimatyczne" if lang == "pl" else "Climate stripes"
    section = part(temperature, title)
    section.locator("svg.stripes").wait_for(timeout=WAIT)
    assert section.locator("svg.stripes > rect").count() >= 60
    page = temperature.page
    assert page.evaluate("document.documentElement.scrollWidth") <= width
