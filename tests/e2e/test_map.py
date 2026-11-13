"""The map and the station list in the browser (GUI plan D9, D10, S3) on the fixture root.

The map draws on a canvas, so what it shows is read from MapLibre: the codes of the rendered
features of a layer (the map's element keeps the map as ``maplibre``). The fixture server has
no basemap and answers IMGW-PIB's current data from recordings.
"""

import contextlib
import json
import re
from typing import Any
from urllib.request import urlopen

import pytest

from tests.e2e.conftest import FIXTURE_STATIONS, THEMES, WIDTHS

expect = pytest.importorskip("playwright.sync_api").expect
PlaywrightTimeout = pytest.importorskip("playwright.sync_api").TimeoutError

# The codes drawn by layers of the map, each once, sorted
_DRAWN = """(layers) => {
  const map = document.querySelector('.map').maplibre;
  const features = map.queryRenderedFeatures({ layers: layers.filter((id) => map.getLayer(id)) });
  return [...new Set(features.map((feature) => feature.properties.code))].sort();
}"""
_SAME = f"""([layers, codes]) => {{
  const element = document.querySelector('.map');
  if (!element || !element.maplibre || !element.maplibre.getLayer('stations')) return false;
  return JSON.stringify(({_DRAWN})(layers)) === JSON.stringify(codes);
}}"""
# Where a point is on the page: the map's canvas offset plus MapLibre's projection
_PIXEL = """([lon, lat]) => {
  const map = document.querySelector('.map').maplibre;
  const box = map.getCanvas().getBoundingClientRect();
  const point = map.project([lon, lat]);
  return [box.left + point.x, box.top + point.y];
}"""
VIEW = {"pl": ("Stacje", "Pomiary bieżące"), "en": ("Stations", "Current measurements")}
# hydro.imgw.pl's colours of the water states (D9), by the legend's words
STATE_COLOURS = {
    "Powyżej stanu alarmowego": "rgb(255, 0, 0)",
    "Powyżej stanu ostrzegawczego": "rgb(255, 165, 0)",
    "Strefa stanów wysokich": "rgb(255, 235, 9)",
    "Strefa stanów średnich": "rgb(10, 101, 192)",
    "Strefa stanów niskich": "rgb(0, 0, 0)",
    "Poniżej minimum okresowego": "rgb(121, 25, 25)",
    "Brak danych stanu wody": "rgb(206, 206, 255)",
    "Brak stanów charakt. / umownych": "rgb(255, 255, 255)",
}


def drawn(page: Any, *layers: str) -> list[str]:
    return list(page.evaluate(_DRAWN, list(layers)))


def wait_drawn(page: Any, layers: list[str], codes: set[str]) -> None:
    """Wait until the layers draw exactly these stations (MapLibre renders asynchronously)."""
    with contextlib.suppress(PlaywrightTimeout):
        page.wait_for_function(_SAME, arg=[layers, sorted(codes)], timeout=15_000)
    assert drawn(page, *layers) == sorted(codes)


def listed(page: Any) -> set[str]:
    rows = page.locator(".stations .st-item")
    return set(rows.evaluate_all("(items) => items.map((item) => item.dataset.code)"))


def wait_listed(page: Any, codes: set[str]) -> None:
    with contextlib.suppress(PlaywrightTimeout):
        page.wait_for_function(
            "(codes) => JSON.stringify([...document.querySelectorAll('.stations .st-item')]"
            ".map((item) => item.dataset.code).sort()) === JSON.stringify(codes)",
            arg=sorted(codes),
            timeout=10_000,
        )
    assert listed(page) == codes


def row(page: Any, code: str) -> Any:
    return page.locator(f'.st-item[data-code="{code}"]')


def api(base: str, path: str) -> Any:
    with urlopen(base + path) as response:
        return json.load(response)


@pytest.fixture(scope="session")
def catalog(gui_url: str) -> list[dict[str, Any]]:
    stations: list[dict[str, Any]] = api(gui_url, "api/stations")["stations"]
    return stations


def codes(stations: list[dict[str, Any]], *, located: bool | None = None) -> set[str]:
    return {
        station["code"]
        for station in stations
        if located is None or (station["lon"] is not None) == located
    }


def test_the_map_draws_the_located_stations_of_both_providers_and_the_list_all(
    open_page, catalog
):
    located = codes(catalog, located=True)
    unlocated = codes(catalog, located=False)
    by_code = {station["code"]: station for station in catalog}
    assert {by_code[code]["provider"] for code in located} == {"IMGW-PIB", "CHMI"}
    assert unlocated
    page = open_page()
    wait_drawn(page, ["stations"], located)
    wait_listed(page, located | unlocated)
    for code in unlocated:
        expect(row(page, code).locator(".no-loc")).to_have_text("bez współrzędnych")
    for code in located:
        expect(row(page, code).locator(".no-loc")).to_have_count(0)
    counts = page.locator(".counts")
    expect(counts).to_contain_text(f"{len(catalog)} stacji")
    expect(counts).to_contain_text(f"na mapie {len(located)}")
    expect(counts).to_contain_text(f"bez współrzędnych {len(unlocated)}")


@pytest.mark.parametrize(
    ("query", "found"),
    [
        # a name without its diacritics and in capitals: Špindlerův Mlýn
        ("SPINDLERUV", {"0-203-1-900001"}),
        # the Polish ó: Raba Górna; a river: the Raba
        ("gorna", {"149190310"}),
        ("RABA", {"149190310", "149190311", "149190312"}),
        # a river with its diacritics folded: Zapadlý potok
        ("zapadly", {"0-203-1-900002"}),
        # a fragment of two names
        ("Lhota", {"0-203-0-90000000002", "0-203-1-900004"}),
        # a prefix of the code, in any case; not the middle of one
        ("0-203-1-cb", {"0-203-1-CB900003"}),
        ("14919031", {"149190310", "149190311", "149190312", "149190313"}),
        ("90001", set()),
    ],
)
def test_the_search_ignores_case_and_diacritics(open_page, query, found):
    page = open_page()
    expect(page.locator(".stations .st-item").first).to_be_visible()
    page.get_by_role(
        "searchbox", name="Szukaj stacji po nazwie, rzece albo kodzie"
    ).fill(query)
    wait_listed(page, found)
    if not found:
        expect(page.get_by_text("Żadna stacja nie pasuje.")).to_be_visible()
        page.get_by_role("button", name="Wyczyść filtry").click()
        expect(page.get_by_role("searchbox")).to_have_value("")
        assert len(listed(page)) > 0


def test_the_filters_choose_the_stations_of_the_list_and_of_the_map(open_page, catalog):
    page = open_page()
    located = codes(catalog, located=True)
    wait_drawn(page, ["stations"], located)

    def check(chosen: list[dict[str, Any]]) -> None:
        wait_listed(page, codes(chosen))
        wait_drawn(page, ["stations"], codes(chosen, located=True))

    page.get_by_role("radiogroup", name="Dostawca").get_by_role(
        "radio", name="ČHMÚ"
    ).click()
    check([s for s in catalog if s["provider"] == "CHMI"])
    page.get_by_role("radiogroup", name="Rodzaj stacji").get_by_role(
        "radio", name="Meteorologiczne"
    ).click()
    check([s for s in catalog if s["provider"] == "CHMI" and s["kind"] == "meteo"])
    # a dataset's chip under another provider is not offered; back to every provider
    expect(
        page.get_by_role("button", name="Dane opadowe dobowe (IMGW-PIB)")
    ).to_have_count(0)
    page.get_by_role("radiogroup", name="Dostawca").get_by_role(
        "radio", name="Wszyscy"
    ).click()
    chip = page.get_by_role("button", name="Dane opadowe dobowe (IMGW-PIB)")
    chip.click()
    expect(chip).to_have_attribute("aria-pressed", "true")
    check([s for s in catalog if "pl.imgw.meteo_precip_daily" in s["datasets"]])
    chip.click()
    page.get_by_role("radiogroup", name="Rodzaj stacji").get_by_role(
        "radio", name="Wszystkie"
    ).click()
    check(catalog)
    page.get_by_role("checkbox", name="tylko czynne").check()
    inactive = codes([s for s in catalog if not s["active"]])
    assert inactive
    check([s for s in catalog if s["active"]])


def test_current_measurements_replace_the_station_layer_and_stations_bring_it_back(
    open_page, catalog, gui_url
):
    page = open_page()
    located = codes(catalog, located=True)
    wait_drawn(page, ["stations"], located)
    current = api(gui_url, "api/current")
    (west, south), (east, north) = page.evaluate(
        "() => document.querySelector('.map').maplibre.getBounds().toArray()"
    )

    def shown(rows: list[dict[str, Any]]) -> set[str]:
        return {
            r["code"]
            for r in rows
            if west <= r["lon"] <= east and south <= r["lat"] <= north
        }

    hydro, meteo = shown(current["hydro"]), shown(current["meteo"])
    assert hydro and meteo
    page.get_by_role("radio", name="Pomiary bieżące").click()
    wait_drawn(page, ["current"], hydro | meteo)
    wait_drawn(page, ["stations", "stations-selected"], set())
    # the legend: hydro.imgw.pl's water states in its colours, and what the precipitation
    # class rests on
    legend = page.locator(".map-legend")
    for words, colour in STATE_COLOURS.items():
        symbol = legend.locator("li", has_text=words).locator(".sym .body").first
        assert symbol.evaluate("(path) => getComputedStyle(path).fill") == colour
    expect(legend).to_contain_text("klasa 6-godzinna IMGW-PIB jest tu niedostępna")
    page.get_by_role("radio", name="Stacje").click()
    wait_drawn(page, ["stations"], located)
    wait_drawn(page, ["current", "current-selected"], set())


def test_a_point_names_its_station_and_a_click_selects_it(open_page, catalog):
    page = open_page()
    wait_drawn(page, ["stations"], codes(catalog, located=True))
    # Warszawa: in the middle of the map, clear of the legend (bottom left)
    station = next(s for s in catalog if s["code"] == FIXTURE_STATIONS["meteo"])
    x, y = page.evaluate(_PIXEL, [station["lon"], station["lat"]])
    page.mouse.move(x, y)
    tip = page.get_by_role("tooltip")
    expect(tip).to_contain_text(station["name"])
    expect(tip).to_contain_text(station["code"])
    page.mouse.click(x, y)
    expect(row(page, station["code"])).to_have_attribute("aria-current", "true")
    wait_drawn(page, ["stations-selected"], {station["code"]})


def test_the_legend_explains_the_symbols_of_the_stations(open_page):
    page = open_page()
    legend = page.locator(".map-legend")
    expect(legend.get_by_role("button", name="Legenda")).to_have_attribute(
        "aria-expanded", "true"
    )

    def symbol(words: str) -> Any:
        return legend.locator("li", has_text=words).locator("svg.sym")

    expect(symbol("hydrologiczna")).to_have_class(re.compile(r"\bhydro\b"))
    expect(symbol("meteorologiczna")).to_have_class(re.compile(r"\bmeteo\b"))
    expect(symbol("tylko w katalogu")).to_have_class(re.compile(r"\bhollow\b"))
    expect(symbol("ČHMÚ (obrys przerywany)")).to_have_class(re.compile(r"\bdashed\b"))
    expect(symbol("nieczynna (blado)")).to_have_class(re.compile(r"\bfaded\b"))
    selected = symbol("wybrana").bounding_box()
    usual = symbol("hydrologiczna").bounding_box()
    assert selected is not None and usual is not None
    assert selected["height"] > 1.5 * usual["height"]
    # the fills of „Stacje”: hydro.imgw.pl's icons of a hydrological and a meteorological station
    fills = {
        words: symbol(words)
        .locator(".body")
        .evaluate("(path) => getComputedStyle(path).fill")
        for words in ("hydrologiczna", "meteorologiczna")
    }
    assert fills == {
        "hydrologiczna": "rgb(10, 101, 192)",
        "meteorologiczna": "rgb(40, 150, 19)",
    }


def test_without_a_basemap_the_packaged_borders_are_the_background(open_page):
    page = open_page()
    page.wait_for_function(
        "() => { const element = document.querySelector('.map');"
        " const map = element && element.maplibre;"
        " return Boolean(map && map.getSource('borders')"
        " && map.queryRenderedFeatures({ layers: ['borders-fill'] }).length > 0); }"
    )
    assert page.evaluate(
        "() => document.querySelector('.map').maplibre.getSource('basemap') === undefined"
    )
    expect(page.locator(".map-legend")).to_contain_text(
        "Tło: granice Polski i Czech z pakietu Obserwatora"
    )
    expect(page.locator(".map-credits")).not_to_contain_text("Podkład mapy")


def test_the_pmaxtp_view_draws_only_the_point_picked(open_page, catalog):
    page = open_page()
    wait_drawn(page, ["stations"], codes(catalog, located=True))
    page.get_by_role("radio", name="PMAXTP").click()
    # at once, on the place of a station drawn a moment ago: Warszawa
    warszawa = next(s for s in catalog if s["code"] == FIXTURE_STATIONS["meteo"])
    x, y = page.evaluate(_PIXEL, [warszawa["lon"], warszawa["lat"]])
    page.mouse.click(x, y)
    page.wait_for_function(
        "() => document.querySelector('.map').maplibre"
        ".queryRenderedFeatures({ layers: ['pmaxtp-dot'] }).length === 1"
    )
    wait_drawn(
        page, ["stations", "stations-selected", "current", "current-selected"], set()
    )
    # the click picked the point, not the station under it
    page.wait_for_url(re.compile(r"[?&]lat="))
    assert "station=" not in page.url


def test_an_address_with_a_station_opens_the_same_selection(open_page, gui_url):
    code = FIXTURE_STATIONS["hydro_chmi"]
    page = open_page()
    row(page, code).click()
    expect(row(page, code)).to_have_attribute("aria-current", "true")
    page.wait_for_url(re.compile(rf"[?&]station={re.escape(code)}(&|$)"))
    copy = open_page(page.url.removeprefix(gui_url))
    expect(row(copy, code)).to_have_attribute("aria-current", "true")
    wait_drawn(copy, ["stations-selected"], {code})


@pytest.mark.parametrize("lang", ["pl", "en"])
@pytest.mark.parametrize("theme", THEMES)
@pytest.mark.parametrize("width", WIDTHS)
def test_both_views_draw_in_each_theme_language_and_width(
    open_page, catalog, theme, width, lang
):
    page = open_page(theme=theme, width=width, lang=lang)
    wait_drawn(page, ["stations"], codes(catalog, located=True))
    toggle = page.locator(".legend-toggle")
    # on a phone the legend starts folded and opens on demand
    expect(toggle).to_have_attribute(
        "aria-expanded", "false" if width < 860 else "true"
    )
    if width < 860:
        toggle.click()
        expect(page.locator(".map-legend li").first).to_be_visible()
    stations, current = VIEW[lang]
    page.get_by_role("radio", name=current).click()
    page.wait_for_function(
        "() => document.querySelector('.map').maplibre"
        ".queryRenderedFeatures({ layers: ['current'] }).length > 0"
    )
    wait_drawn(page, ["stations"], set())
    page.get_by_role("radio", name=stations).click()
    wait_drawn(page, ["stations"], codes(catalog, located=True))
    # nothing of the map sticks out sideways
    assert page.evaluate("() => document.documentElement.scrollWidth") <= width
