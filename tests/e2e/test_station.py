"""
The station panel and its common sections on the fixture root (GUI plan S4, D11).

The header names the station; „Informacje o stacji”, „Pomiary bieżące” and „Dane
pomiarowo-obserwacyjne” come first and „Pobierz” last, in both languages, both themes and
on a phone. An IMGW-PIB hydrological station shows H, Q and T with their flags and both
kinds of year, and its table holds exactly the values and flags of the CSV of
`export_series`; the meteorological stations show precipitation and temperatures; a ČHMÚ
station shows its catalog data and says that ČHMÚ's current data are not provided;
IMGW-PIB's current values come from the server's (recorded) snapshot with their times.
"""

from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Any

import pytest

from obserwator import export_series
from obserwator.messages import message
from tests.e2e.conftest import FIXTURE_STATIONS, THEMES, WIDTHS

expect = pytest.importorskip("playwright.sync_api").expect

HYDRO = FIXTURE_STATIONS["hydro"]
HYDRO_CHMI = FIXTURE_STATIONS["hydro_chmi"]
METEO = FIXTURE_STATIONS["meteo"]
METEO_CHMI = FIXTURE_STATIONS["meteo_chmi"]
WAIT = 20_000
"""How long a section may take to load [ms]."""
TABLE_ROWS = """rows => rows.map((row) => [...row.cells].map((cell) => {
  const flag = cell.querySelector(".flag");
  const text = cell.textContent.replace(flag ? flag.textContent : "", "").trim();
  return [text, flag ? flag.textContent.trim() : null];
}))"""
"""The cells of a table's rows: the text of each without its flag, and the flag."""

Row = list[tuple[str, str | None]]


def card(page: Any, section: str) -> Any:
    """A section's card of the station panel, opened."""
    item = page.locator(f'.acc-item[data-section="{section}"]')
    button = item.locator(".acc-head button")
    button.wait_for(timeout=WAIT)
    if button.get_attribute("aria-expanded") != "true":
        button.click()
    item.locator(".acc-body").wait_for(timeout=WAIT)
    return item


def number(text: str) -> float:
    """A number as the page writes it in Polish: „1 060,5” → 1060.5."""
    plain = re.sub(r"[\u00a0\u202f ]", "", text).replace(",", ".").replace("−", "-")
    return float(plain)


def decimals(text: str) -> int:
    """How many decimals a number of the page shows."""
    return len(text.split(",")[1]) if "," in text else 0


def iso(text: str) -> str:
    """A Polish date of the page as ISO: „01.12.2023” → 2023-12-01."""
    day, month, year = text.split(".")
    return f"{year}-{month}-{day}"


def flag_word(flag: str) -> str:
    """The word of a record's flag that the page shows in Polish."""
    return str(message(f"gui.words.flag.{flag}", "pl"))


def show_every_variable(data: Any) -> list[str]:
    """Turn on every variable of „Dane pomiarowo-obserwacyjne”; their names in order."""
    chips = data.locator(".chips button")
    chips.first.wait_for(timeout=WAIT)
    names = []
    for index in range(chips.count()):
        chip = chips.nth(index)
        if chip.get_attribute("aria-pressed") != "true":
            chip.click()
        expect(chip).to_have_attribute("aria-pressed", "true")
        names.append(chip.inner_text().split()[0])
    return names


def read_table(data: Any) -> tuple[list[str], list[Row]]:
    """Every page of the daily table: its column titles and its rows, newest first."""
    table = data.locator(".data-table")
    titles = table.locator("thead th").all_inner_texts()
    newest = table.locator(".pager button").first
    if newest.is_enabled():
        newest.click()
        expect(newest).to_be_disabled()
    rows: list[Row] = []
    while True:
        rows += [
            [(cell[0], cell[1]) for cell in row]
            for row in table.locator("tbody tr").evaluate_all(TABLE_ROWS)
        ]
        older = table.locator(".pager button").nth(2)
        if older.is_disabled():
            return titles, rows
        first = table.locator("tbody tr").first.inner_text()
        older.click()
        expect(table.locator("tbody tr").first).not_to_have_text(first)


def row_of(rows: list[Row], date: str) -> Row:
    """The row of a day („01.12.2023”)."""
    return next(row for row in rows if row[0][0] == date)


@pytest.mark.parametrize("lang", ["pl", "en"])
@pytest.mark.parametrize("width", WIDTHS)
@pytest.mark.parametrize("theme", THEMES)
def test_the_panel_names_the_station_and_keeps_the_authors_order(
    open_page: Any, theme: str, width: int, lang: str
) -> None:
    page = open_page(f"?station={HYDRO}", theme=theme, width=width, lang=lang)
    head = page.locator(".station-head")
    head.wait_for(timeout=WAIT)

    assert head.locator("h3").inner_text() == "Raba Górna"
    tags = head.locator(".station-tags").inner_text()
    assert HYDRO in tags
    assert "IMGW-PIB" in tags
    assert (
        str(message("gui.words.kind.hydro", lang="pl" if lang == "pl" else "en"))
        in tags
    )
    order = page.locator(".acc-item").evaluate_all(
        "items => items.map((item) => item.dataset.section)"
    )
    assert order[:3] == ["stacja", "teraz", "dane"]
    assert order[-1] == "pobierz"
    for section in ("stacja", "teraz", "dane", "pobierz"):
        body = card(page, section).locator(".acc-body")
        expect(body).to_be_visible()
        expect(body.locator(".ana-error")).to_have_count(0)


def test_the_hydrological_series_shows_h_q_t_with_flags_and_both_kinds_of_year(
    open_page: Any,
) -> None:
    page = open_page(f"?station={HYDRO}&section=dane")
    data = card(page, "dane")

    assert show_every_variable(data) == ["H", "Q", "T"]
    # One chart per unit: cm, m³/s and °C
    expect(data.locator(".data-chart svg")).to_have_count(3)
    assert flag_word("missing") in data.locator(".note .flag").all_inner_texts()
    data.get_by_role("button", name="Tabela").click()
    titles, rows = read_table(data)
    assert titles[:2] == ["Data", "Rok hydr."]
    december = row_of(rows, "01.12.2023")
    assert december[1][0] == "2024"
    assert december[2:] == [("162", None), ("–", flag_word("missing")), ("4,1", None)]

    data.get_by_role("radio", name="kalendarzowy").click()
    expect(data.locator(".data-table thead th").nth(1)).to_have_text("Rok")
    titles, rows = read_table(data)
    assert row_of(rows, "01.12.2023")[1][0] == "2023"
    assert row_of(rows, "29.02.2024")[1][0] == "2024"


@pytest.mark.parametrize(
    ("code", "dataset"),
    [(HYDRO, "pl.imgw.hydro_daily"), (METEO, "pl.imgw.meteo_precip_daily")],
)
def test_the_table_holds_the_values_and_flags_of_the_exported_csv(
    open_page: Any, gui_root: Path, tmp_path: Path, code: str, dataset: str
) -> None:
    exported = tmp_path / "series.csv"
    export_series(root=gui_root, dataset=dataset, station=code, output=exported)
    with exported.open(encoding="utf-8", newline="") as stream:
        expected = list(csv.DictReader(stream))
    page = open_page(f"?station={code}&section=dane")
    data = card(page, "dane")
    names = show_every_variable(data)
    data.get_by_role("button", name="Tabela").click()

    titles, rows = read_table(data)
    assert [title.split(" [")[0] for title in titles[2:]] == names
    assert len(rows) == len(expected)
    shown = {iso(row[0][0]): row for row in rows}
    for record in expected:
        row = shown[record["date"]]
        assert row[1][0] == record["year"]
        for name, (text, flag) in zip(names, row[2:], strict=True):
            where = (record["date"], name)
            value = next(record[key] for key in record if key.startswith(f"{name} ["))
            wanted = record[f"{name}_flag"]
            assert flag == (None if wanted == "value" else flag_word(wanted)), where
            if value == "":
                assert text == "–", where
            else:
                tolerance = 0.5 * 10 ** -decimals(text)
                assert abs(number(text) - float(value)) <= tolerance, where


def test_the_meteorological_stations_show_precipitation_and_temperatures(
    open_page: Any,
) -> None:
    page = open_page(f"?station={METEO}&section=dane")
    data = card(page, "dane")
    chips = data.locator(".chips button")
    chips.first.wait_for(timeout=WAIT)
    assert [text.split()[0] for text in chips.all_inner_texts()] == [
        "P",
        "snow_cover",
        "fresh_snow",
    ]
    pressed = data.locator('.chips button[aria-pressed="true"]')
    assert [text.split()[0] for text in pressed.all_inner_texts()] == ["P"]
    expect(data.locator(".data-chart svg")).to_have_count(1)
    marks = data.locator(".note .flag").all_inner_texts()
    assert flag_word("accumulated") in marks
    assert flag_word("no_phenomenon") in marks

    page = open_page(f"?station={METEO_CHMI}&section=dane")
    data = card(page, "dane")
    chips = data.locator(".chips button")
    chips.first.wait_for(timeout=WAIT)
    assert sorted(text.split()[0] for text in chips.all_inner_texts()) == [
        "P",
        "Tmax",
        "Tmean",
        "Tmin",
    ]
    pressed = data.locator('.chips button[aria-pressed="true"]')
    assert sorted(text.split()[0] for text in pressed.all_inner_texts()) == [
        "P",
        "Tmean",
    ]
    charts = data.locator(".data-chart svg")
    expect(charts).to_have_count(2)
    titles = charts.evaluate_all(
        "charts => charts.map((chart) => chart.getAttribute('aria-label'))"
    )
    assert sorted(title.rsplit(": ", 1)[1] for title in titles) == ["P", "Tmean"]


def test_a_chmi_station_shows_its_catalog_data_and_no_current_data(
    open_page: Any,
) -> None:
    page = open_page(f"?station={HYDRO_CHMI}&section=stacja")
    asked: list[str] = []
    page.on("request", lambda request: asked.append(request.url))
    info = card(page, "stacja")

    text = info.inner_text()
    assert "1-05-03-0110" in text
    assert "Labe" in text
    spa = info.locator("tr", has_text="1. SPA").first.locator("td").all_inner_texts()
    assert spa[1:] == ["120", "14,2"]
    covered = info.locator(".coverage tbody tr").all_inner_texts()
    assert [row.split()[0] for row in covered] == ["H", "Q", "T"]

    now = card(page, "teraz")
    expect(now.locator(".acc-body")).to_contain_text(
        str(message("gui.errors.no_current_chmi", "pl"))
    )
    assert not [url for url in asked if "api/current" in url]


def test_current_values_of_an_imgw_station_come_with_their_times(
    open_page: Any,
) -> None:
    page = open_page(f"?station={HYDRO}&section=teraz")
    now = card(page, "teraz")
    tiles = now.locator(".figures > div")
    tiles.first.wait_for(timeout=WAIT)

    shown = {
        tile.locator("dt").inner_text(): (
            tile.locator("dd").inner_text(),
            tile.locator("small").inner_text() if tile.locator("small").count() else "",
        )
        for tile in tiles.all()
    }
    level, flow, temperature = (
        shown[str(message(f"gui.station.now.{key}", "pl"))]
        for key in ("water_level", "discharge", "water_temperature")
    )
    assert (level[0], flow[0], temperature[0]) == ("182 cm", "3,41 m³/s", "9,8 °C")
    times = (level[1], flow[1], temperature[1])
    for when, hour in zip(times, ("11:00", "11:00", "06:00"), strict=True):
        assert "17.10.2026" in when
        assert hour in when
        assert "UTC" in when
    expect(now.locator(".now-class svg")).to_have_count(1)
    assert now.locator(".now-class strong").inner_text().strip()
