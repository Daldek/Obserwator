"""
The page on an operator's instance (ADR-025, ``[obserwator.instance]``) in the browser.

The servers of ``tests/e2e/conftest.py``: ``operator_url`` (public, title, logo and
regulamin, ČHMÚ featured, IMGW-PIB off, the area clipped, PMAXTP off, the map starting on
ČHMÚ's stations), ``hidden_url`` (ČHMÚ featured, IMGW-PIB hidden, the area in focus, the
map starting on it) and ``featured_url`` (ČHMÚ featured beside a visible IMGW-PIB); and
``gui_url`` without an instance. The map draws on a canvas, so what it shows is read from
MapLibre (the map's element keeps it as ``maplibre``): its bounds, the stations' source and
the rendered symbols with their evaluated size and opacity.
"""

from __future__ import annotations

import contextlib
import json
import re
from typing import Any
from urllib.request import urlopen

import pytest

from tests.e2e.conftest import (
    FEATURED_OTHERS_OPACITY,
    FIXTURE_STATIONS,
    INSTANCE_AREA,
    INSTANCE_TITLE,
    OPERATOR_ADDRESS,
)

expect = pytest.importorskip("playwright.sync_api").expect
PlaywrightTimeout = pytest.importorskip("playwright.sync_api").TimeoutError

OTHERS = "Pokaż inne źródła"
AREA_BOX = [
    min(x for x, _ in INSTANCE_AREA),
    min(y for _, y in INSTANCE_AREA),
    max(x for x, _ in INSTANCE_AREA),
    max(y for _, y in INSTANCE_AREA),
]
"""The area's box [west, south, east, north]."""
OUTSIDE_STATION = "0-203-1-900004"
"""A located ČHMÚ station south-east of the area (16.60, 49.20), served in focus."""

# The map's state: its bounds, the bounds it keeps to and the features of the area drawn
_CAMERA = """() => {
  const map = document.querySelector('.map').maplibre;
  const box = (b) => (b ? [b.getWest(), b.getSouth(), b.getEast(), b.getNorth()] : null);
  return {
    bounds: box(map.getBounds()),
    max: box(map.getMaxBounds()),
    moving: map.isMoving(),
    area: map.queryRenderedFeatures({ layers: ['area-line'] }).length,
  };
}"""
# Whether the map has its layers and draws stations
_READY = """() => {
  const element = document.querySelector('.map');
  const map = element && element.maplibre;
  return Boolean(map && map.getLayer('stations')
    && map.queryRenderedFeatures({ layers: ['stations'] }).length > 0 && !map.isMoving());
}"""
# The features of the stations' source by code: every station drawn, on screen or not
_SOURCE = """async () => {
  const map = document.querySelector('.map').maplibre;
  const data = await map.getSource('stations').getData();
  return Object.fromEntries(data.features.map((f) => [f.properties.code, f.properties]));
}"""
# The symbols on screen with their evaluated opacity, size and drawing order
_SYMBOLS = """() => {
  const map = document.querySelector('.map').maplibre;
  return Object.fromEntries(map.queryRenderedFeatures({ layers: ['stations'] }).map((f) => [
    f.properties.code,
    { opacity: f.layer.paint['icon-opacity'], size: f.layer.layout['icon-size'],
      order: f.layer.layout['symbol-sort-key'] },
  ]));
}"""
# Show the whole of Poland and Czechia, where the map keeps no bounds
_WHOLE = """() => document.querySelector('.map').maplibre.jumpTo({ center: [18, 51.5], zoom: 4.5 })"""


def api(base: str, path: str) -> Any:
    with urlopen(base + path) as response:
        return json.load(response)


def catalog(base: str) -> dict[str, dict[str, Any]]:
    """The stations a server serves, by code."""
    return {s["code"]: s for s in api(base, "api/stations")["stations"]}


def shown(stations: dict[str, dict[str, Any]], provider: str | None = None) -> set[str]:
    """The codes of the stations of a first visit („tylko czynne” checked) of a provider."""
    return {
        code
        for code, s in stations.items()
        if s["active"] and (provider is None or s["provider"] == provider)
    }


def located(stations: dict[str, dict[str, Any]], codes: set[str]) -> set[str]:
    return {code for code in codes if stations[code]["lon"] is not None}


def ready(page: Any) -> None:
    page.wait_for_function(_READY, timeout=20_000)


def source(page: Any) -> dict[str, dict[str, Any]]:
    found: dict[str, dict[str, Any]] = page.evaluate(_SOURCE)
    return found


def wait_source(page: Any, codes: set[str]) -> dict[str, dict[str, Any]]:
    """Wait until the stations' source holds exactly these codes."""
    for _ in range(100):
        found = source(page)
        if set(found) == codes:
            return found
        page.wait_for_timeout(100)
    assert set(source(page)) == codes
    return source(page)


def listed(page: Any) -> list[str]:
    rows = page.locator(".stations .st-item")
    codes: list[str] = rows.evaluate_all("(items) => items.map((i) => i.dataset.code)")
    return codes


def wait_listed(page: Any, codes: set[str]) -> list[str]:
    with contextlib.suppress(PlaywrightTimeout):
        page.wait_for_function(
            "(codes) => JSON.stringify([...document.querySelectorAll('.stations .st-item')]"
            ".map((item) => item.dataset.code).sort()) === JSON.stringify(codes)",
            arg=sorted(codes),
            timeout=10_000,
        )
    rows = listed(page)
    assert set(rows) == codes
    return rows


def settled_camera(page: Any) -> dict[str, Any]:
    """The map's state once it stands still."""
    for _ in range(100):
        state: dict[str, Any] = page.evaluate(_CAMERA)
        if not state["moving"]:
            return state
        page.wait_for_timeout(100)
    raise AssertionError("the map does not stop")


def wait_outline(page: Any) -> None:
    """Wait until the map draws the area's outline (api/area comes after the map loads)."""
    page.wait_for_function(
        "() => document.querySelector('.map').maplibre"
        ".queryRenderedFeatures({ layers: ['area-line'] }).length > 0"
    )


def inside(inner: list[float], outer: list[float], slack: float = 1e-6) -> bool:
    west, south, east, north = inner
    return (
        outer[0] - slack <= west
        and outer[1] - slack <= south
        and east <= outer[2] + slack
        and north <= outer[3] + slack
    )


def providers_switch(page: Any) -> list[str]:
    group = page.get_by_role("radiogroup", name="Dostawca")
    names: list[str] = group.get_by_role("radio").all_inner_texts()
    return names


def chip_groups(page: Any) -> list[str]:
    names: list[str] = page.locator(".ds-group .ds-provider").all_inner_texts()
    return names


# --- without an instance ---------------------------------------------------------------


def test_without_an_instance_the_page_shows_everything_as_before(open_page, gui_url):
    page = open_page()
    session = page.request.get(f"{gui_url}api/session").json()
    assert session["instance"] is None
    ready(page)
    expect(
        page.get_by_role("radiogroup", name="Widok mapy").get_by_role("radio")
    ).to_have_text(["Stacje", "Pomiary bieżące", "PMAXTP"])
    assert providers_switch(page) == ["Wszyscy", "IMGW-PIB", "ČHMÚ"]
    expect(page.locator(".check-row input[type=checkbox]")).to_have_count(1)
    expect(page.get_by_role("checkbox", name=OTHERS)).to_have_count(0)
    expect(page.locator(".topbar .operator")).to_have_count(0)
    expect(page).to_have_title("Obserwator")
    camera = settled_camera(page)
    assert camera["max"] is None and camera["area"] == 0
    legend = page.locator(".map-legend")
    expect(legend).not_to_contain_text("obszar serwisu")
    # one symbol per kind, whoever provides it: no provider in the legend
    expect(legend.locator(".legend-title")).to_have_count(0)
    for words in ("ČHMÚ", "Stacje:", "Pozostałe źródła"):
        expect(legend).not_to_contain_text(words)
    expect(legend.locator("li")).to_have_text(
        [
            "hydrologiczna",
            "meteorologiczna",
            "tylko w katalogu",
            "nieczynna (blado)",
            "wybrana",
        ]
    )


# --- the start, the area and its bounds -----------------------------------------------------


def test_the_map_starts_on_the_featured_stations_within_the_clipped_area(
    open_page, operator_url
):
    instance = api(operator_url, "api/session")["instance"]
    start, area = instance["start"]["box"], instance["area"]
    assert instance["start"]["view"] == "featured" and area["mode"] == "clip"
    page = open_page(base=operator_url)
    ready(page)
    camera = settled_camera(page)
    # fitted: the whole box in sight with the usual padding, not much more around it
    assert inside(start, camera["bounds"])
    west, south, east, north = camera["bounds"]
    assert east - west < 2 * (start[2] - start[0])
    assert north - south < 2 * (start[3] - start[1])
    # the map keeps to the area's bounds and draws the area's outline under the stations
    assert camera["max"] == pytest.approx(area["bounds"])
    assert inside(AREA_BOX, area["bounds"])
    wait_outline(page)
    layers = page.evaluate(
        "() => document.querySelector('.map').maplibre.getStyle().layers.map((l) => l.id)"
    )
    assert (
        layers.index("borders-line")
        < layers.index("area-line")
        < layers.index("stations")
    )
    expect(page.locator(".map-legend")).to_contain_text("obszar serwisu")


def test_the_map_starts_on_the_area_in_focus_unless_the_address_names_a_station(
    open_page, hidden_url
):
    instance = api(hidden_url, "api/session")["instance"]
    assert instance["start"] == {"view": "area", "box": AREA_BOX}
    assert instance["area"]["bounds"] is None
    page = open_page(base=hidden_url)
    ready(page)
    camera = settled_camera(page)
    assert inside(AREA_BOX, camera["bounds"])
    assert camera["bounds"][2] - camera["bounds"][0] < 1.5 * (AREA_BOX[2] - AREA_BOX[0])
    assert camera["max"] is None
    wait_outline(page)
    # a link to a station outside the area opens on the station, as without an instance
    stations = catalog(hidden_url)
    station = stations[OUTSIDE_STATION]
    linked = open_page(f"?station={OUTSIDE_STATION}", base=hidden_url)
    linked.wait_for_function(
        "([lon, lat]) => { const element = document.querySelector('.map');"
        " const map = element && element.maplibre; if (!map) return false;"
        " const c = map.getCenter(); return !map.isMoving()"
        " && Math.abs(c.lng - lon) < 0.01 && Math.abs(c.lat - lat) < 0.01; }",
        arg=[station["lon"], station["lat"]],
        timeout=20_000,
    )
    west, _, east, _ = settled_camera(linked)["bounds"]
    assert not (west <= AREA_BOX[0] and AREA_BOX[2] <= east)


def test_a_map_moved_before_the_session_answers_keeps_its_place(browser, hidden_url):
    # api/session held back until the person has dragged the map: no start box then (a
    # context of its own, which open_page cannot hold a request of)
    context = browser.new_context(viewport={"width": 1440, "height": 900})
    context.add_init_script("localStorage.setItem('obserwator-welcome', '1');")
    held: list[Any] = []
    context.route("**/api/session", lambda route: held.append(route))
    errors: list[str] = []
    try:
        page = context.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on(
            "console",
            lambda message: (
                errors.append(message.text) if message.type == "error" else None
            ),
        )
        page.goto(hidden_url)
        page.wait_for_function(
            "() => { const element = document.querySelector('.map');"
            " return Boolean(element && element.maplibre"
            " && element.maplibre.getLayer('stations')); }",
            timeout=20_000,
        )
        for _ in range(100):
            if held:
                break
            page.wait_for_timeout(100)
        assert held
        box = page.locator(".map canvas").bounding_box()
        assert box is not None
        x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
        page.mouse.move(x, y)
        page.mouse.down()
        page.mouse.move(x + 150, y + 80, steps=12)
        page.mouse.up()
        moved = settled_camera(page)["bounds"]
        for route in held:
            route.continue_()
        expect(page.locator(".stations .st-item").first).to_be_visible()
        wait_outline(page)
        # the area in sight, its outline drawn, but the map where the person left it
        assert settled_camera(page)["bounds"] == pytest.approx(moved)
        assert moved[2] - moved[0] > 3 * (AREA_BOX[2] - AREA_BOX[0])
    finally:
        context.close()
    assert errors == []


# --- the featured provider and „Pokaż inne źródła” -----------------------------------------


def test_the_featured_providers_stations_lie_on_top_and_the_others_fade_until_shown(
    open_page, featured_url
):
    stations = catalog(featured_url)
    chmi = located(stations, shown(stations, "CHMI"))
    imgw = located(stations, shown(stations, "IMGW-PIB"))
    assert chmi and imgw
    page = open_page(base=featured_url)
    ready(page)
    assert providers_switch(page) == ["Wszyscy", "ČHMÚ", "IMGW-PIB"]
    assert chip_groups(page) == ["ČHMÚ", "IMGW-PIB"]
    rows = wait_listed(page, shown(stations))
    assert {
        stations[code]["provider"] for code in rows[: len(shown(stations, "CHMI"))]
    } == {"CHMI"}
    others = page.get_by_role("checkbox", name=OTHERS)
    expect(others).not_to_be_checked()
    legend = page.locator(".map-legend")

    def symbols() -> dict[str, dict[str, float]]:
        wait_source(page, chmi | imgw)
        page.wait_for_timeout(300)  # the next frame draws the new source
        found: dict[str, dict[str, float]] = page.evaluate(_SYMBOLS)
        assert set(found) == chmi | imgw
        return found

    faded = symbols()
    full = {faded[code]["size"] for code in chmi}
    assert len(full) == 1 and {faded[code]["opacity"] for code in chmi} == {1}
    for code in imgw:
        assert faded[code]["opacity"] == pytest.approx(FEATURED_OTHERS_OPACITY)
        assert faded[code]["size"] < 0.8 * min(full)
    assert min(faded[code]["order"] for code in chmi) > max(
        faded[code]["order"] for code in imgw
    )
    # the legend: ČHMÚ's stations, then the other sources drawn as the map draws them
    expect(legend.locator(".legend-title")).to_have_text(
        ["Stacje: ČHMÚ", "Pozostałe źródła"]
    )
    groups = legend.locator(".legend-title + .legend-list")
    expect(groups).to_have_count(2)
    for group in (groups.nth(0), groups.nth(1)):
        expect(group.locator("svg.sym")).to_have_count(2)
    strengths = [
        groups.nth(n)
        .locator("svg.sym")
        .evaluate_all("(all) => all.map((s) => Number(getComputedStyle(s).opacity))")
        for n in (0, 1)
    ]
    assert strengths[0] == [1, 1]
    assert strengths[1] == [pytest.approx(FEATURED_OTHERS_OPACITY)] * 2
    heights = [
        groups.nth(n).locator("svg.sym").first.bounding_box()["height"] for n in (0, 1)
    ]
    assert heights[1] < 0.8 * heights[0]
    # „Pokaż inne źródła”: every station at full strength, ČHMÚ's still on top
    others.check()
    page.wait_for_function(
        "() => document.querySelector('.map').maplibre"
        ".queryRenderedFeatures({ layers: ['stations'] })"
        ".every((f) => f.layer.paint['icon-opacity'] === 1)"
    )
    strong = symbols()
    assert {strong[code]["size"] for code in imgw} == full
    assert min(strong[code]["order"] for code in chmi) > max(
        strong[code]["order"] for code in imgw
    )
    expect(legend.locator(".legend-title")).to_have_count(0)
    expect(legend).not_to_contain_text("Pozostałe źródła")
    # IMGW-PIB chosen in the switch: its stations alone, at full strength
    others.uncheck()
    page.get_by_role("radiogroup", name="Dostawca").get_by_role(
        "radio", name="IMGW-PIB"
    ).click()
    wait_source(page, imgw)
    page.wait_for_function(
        "(n) => { const found = document.querySelector('.map').maplibre"
        ".queryRenderedFeatures({ layers: ['stations'] });"
        " return found.length === n && found.every((f) => f.layer.paint['icon-opacity'] === 1); }",
        arg=len(imgw),
    )
    # not remembered: the next visit starts with it off
    again = open_page(base=featured_url)
    expect(again.get_by_role("checkbox", name=OTHERS)).not_to_be_checked()


def test_a_hidden_provider_shows_only_when_chosen_or_asked_for(open_page, hidden_url):
    stations = catalog(hidden_url)
    chmi = shown(stations, "CHMI")
    imgw = shown(stations, "IMGW-PIB")
    assert located(stations, imgw)
    page = open_page(base=hidden_url)
    ready(page)
    # left out of the list, the map and the chips; the switch names it after ČHMÚ
    wait_listed(page, chmi)
    wait_source(page, located(stations, chmi))
    assert providers_switch(page) == ["Wszyscy", "ČHMÚ", "IMGW-PIB"]
    assert chip_groups(page) == ["ČHMÚ"]
    expect(
        page.get_by_role("radiogroup", name="Widok mapy").get_by_role("radio")
    ).to_have_count(3)
    # „Pokaż inne źródła”: back in the list after ČHMÚ's and on the map at full strength
    page.get_by_role("checkbox", name=OTHERS).check()
    rows = wait_listed(page, chmi | imgw)
    assert set(rows[: len(chmi)]) == chmi
    assert chip_groups(page) == ["ČHMÚ", "IMGW-PIB"]
    found = wait_source(page, located(stations, chmi | imgw))
    assert {found[code]["dim"] for code in found} == {0}
    page.evaluate(_WHOLE)
    page.wait_for_function(
        "(codes) => { const drawn = document.querySelector('.map').maplibre"
        ".queryRenderedFeatures({ layers: ['stations'] }).map((f) => f.properties.code);"
        " return codes.every((code) => drawn.includes(code)); }",
        arg=sorted(located(stations, imgw)),
    )
    # off again, then IMGW-PIB chosen in the switch: its stations alone
    page.get_by_role("checkbox", name=OTHERS).uncheck()
    wait_listed(page, chmi)
    page.get_by_role("radiogroup", name="Dostawca").get_by_role(
        "radio", name="IMGW-PIB"
    ).click()
    wait_listed(page, imgw)
    wait_source(page, located(stations, imgw))
    assert chip_groups(page) == ["IMGW-PIB"]
    # a link to a station of the hidden provider shows the other providers' stations
    code = min(located(stations, imgw))
    linked = open_page(f"?station={code}", base=hidden_url)
    expect(linked.get_by_role("checkbox", name=OTHERS)).to_be_checked()
    expect(linked.locator(f'.st-item[data-code="{code}"]')).to_have_attribute(
        "aria-current", "true"
    )


# --- the views, the top bar, the lines and the regulamin -------------------------------------


@pytest.mark.parametrize(
    "address", ["", "?view=current", "?view=pmaxtp&lat=50.0000&lon=15.0000"]
)
def test_the_views_bar_offers_only_the_views_served(open_page, operator_url, address):
    page = open_page(address, base=operator_url)
    views = page.get_by_role("radiogroup", name="Widok mapy").get_by_role("radio")
    expect(views).to_have_text(["Stacje"])
    expect(views).to_have_attribute("aria-checked", "true")
    page.wait_for_url(re.compile(r"^[^?]*$"))
    wait_listed(page, shown(catalog(operator_url)))


def test_with_pmaxtp_off_the_precipitation_card_never_asks_for_it(
    open_page, stored_url, no_pmaxtp_url
):
    # An IMGW-PIB station's „Opady” asks for PMAXTP of its point beside the quantiles;
    # an instance with PMAXTP off serves no api/pmaxtp (a 404 and a console error, which
    # open_page fails on), so the card does not ask. The fixture's one year has no
    # quantiles: the station's list gains them, their result failed as Hydrolog's would
    def quantiles_listed(route: Any) -> None:
        document = route.fetch().json()
        (maxima,) = [
            entry
            for entry in document["analyses"]
            if entry["analysis"] == "precipitation.maxima"
        ]
        document["analyses"].append({**maxima, "analysis": "precipitation_quantiles"})
        route.fulfill(json=document)

    def quantiles_failed(route: Any) -> None:
        maxima = route.request.url.split("?")[0].replace(
            "precipitation_quantiles", "precipitation.maxima"
        )
        stored = route.fetch(url=maxima).json()
        route.fulfill(
            json={
                **stored,
                "analysis": "precipitation_quantiles",
                "status": "failed",
                "envelope": None,
                "error": {"schema": "hydrolog-error/1", "message": "za mało lat"},
                "stored": False,
                "source": "computed",
            }
        )

    code = FIXTURE_STATIONS["meteo"]
    asked: dict[str, list[str]] = {}
    for name, base in (("served", stored_url), ("off", no_pmaxtp_url)):
        page = open_page(base=base)
        seen = asked[name] = []
        page.on(
            "request",
            lambda request, seen=seen: (
                seen.append(request.url) if "/api/pmaxtp?" in request.url else None
            ),
        )
        page.route(f"**/api/analyses/{code}", quantiles_listed)
        page.route(f"**/api/analysis/{code}/precipitation_quantiles*", quantiles_failed)
        if name == "served":
            page.route("**/api/pmaxtp?*", lambda route: route.fulfill(json={}))
        page.goto(f"{base}?station={code}&section=opady")
        card = page.locator('[data-section="opady"]')
        expect(
            card.get_by_text("Opad maksymalny o prawdopodobieństwie p")
        ).to_be_visible(timeout=15_000)
        expect(card).to_contain_text("za mało lat")
        page.wait_for_load_state("networkidle")
    assert len(asked["served"]) == 2
    assert asked["off"] == []


@pytest.mark.parametrize("width", [1440, 390])
def test_the_top_bar_shows_the_operators_logo_and_title(open_page, operator_url, width):
    page = open_page(base=operator_url, width=width, height=844)
    bar = page.locator(".topbar")
    expect(bar.locator(":scope > *").first).to_have_class("brand")
    expect(bar.locator(".brand .name")).to_have_text("Obserwator")
    operator = bar.locator(".brand + .operator")
    logo = operator.get_by_role("img", name=INSTANCE_TITLE)
    expect(logo).to_have_attribute("src", "api/logo")
    page.wait_for_function(
        "() => { const img = document.querySelector('.operator img');"
        " return img && img.complete && img.naturalWidth > 0; }"
    )
    box = logo.bounding_box()
    assert box is not None and 0 < box["height"] <= 24
    assert operator.evaluate("(e) => getComputedStyle(e).borderLeftWidth") == "1px"
    title = operator.locator(".operator-name")
    if width >= 860:
        expect(title).to_have_text(INSTANCE_TITLE)
        expect(title).to_be_visible()
    else:
        expect(title).to_be_hidden()
    assert page.evaluate("() => document.documentElement.scrollWidth") <= width
    expect(page).to_have_title(f"Obserwator · {INSTANCE_TITLE}")
    assert re.fullmatch(
        r"v/[0-9a-f]{16}/nogat/marks/obserwator\.svg",
        page.locator("link[rel=icon]").get_attribute("href") or "",
    )
    if width >= 860:
        code = "0-203-1-900001"
        name = catalog(operator_url)[code]["name"]
        page.locator(f'.st-item[data-code="{code}"]').click()
        expect(page).to_have_title(f"{name} — Obserwator · {INSTANCE_TITLE}")


def test_the_lines_and_the_panel_name_only_the_providers_served(
    open_page, operator_url, gui_url
):
    every = api(gui_url, "api/session")["attribution"]["origins"]
    imgw = every["imgw"]["attribution"] + every["imgw_hydro"]["attribution"]
    chmi = every["chmi"]["attribution"]
    page = open_page(base=operator_url, welcome=True)
    welcome = page.locator("dialog.welcome")
    expect(welcome).to_be_visible(timeout=15_000)
    expect(welcome.locator(".intro")).to_have_text(
        "Obserwator pokazuje na mapie stacje hydrologiczne i meteorologiczne: wybierz"
        " stację, aby zobaczyć jej pomiary, analizy i pliki."
    )
    for line in chmi:
        expect(welcome).to_contain_text(line)
    expect(welcome).not_to_contain_text("IMGW")
    welcome.get_by_role("button", name="Rozumiem").click()
    strip = page.locator(".view-foot nogat-sources")
    expect(strip.locator(".nogat-sources-strip")).to_contain_text("Źródło: ČHMÚ")
    shown_lines = strip.evaluate("(element) => element.attribution")
    assert not set(imgw) & set(shown_lines)
    strip.get_by_role("button", name="Źródła i warunki").click()
    dialog = strip.locator("dialog")
    expect(dialog).to_be_visible()
    expect(dialog).not_to_contain_text("IMGW")
    page.keyboard.press("Escape")
    # the panel without a station counts and lists the catalogs of ČHMÚ alone
    panel = page.locator("#panel-right")
    expect(panel.locator("[data-part=analyses] tr[data-provider]")).to_have_count(1)
    expect(panel.locator("[data-part=analyses] tr[data-provider]")).to_have_attribute(
        "data-provider", "CHMI"
    )
    expect(panel.locator(".no-station")).not_to_contain_text("IMGW")


def test_the_regulamin_link_opens_the_operators_regulamin(open_page, operator_url):
    page = open_page(base=operator_url)
    link = page.locator("#panel-left .panel-foot").get_by_role("link", name="Regulamin")
    expect(link).to_have_attribute("href", "regulamin.html")
    with page.expect_popup() as opened:
        link.click()
    terms = opened.value
    terms.wait_for_load_state()
    expect(terms.locator("h1")).to_have_text("Regulamin serwisu Obserwator")
    expect(terms.locator("body")).to_contain_text(OPERATOR_ADDRESS)
    expect(terms.locator("body")).to_contain_text("ČHMÚ")
    expect(terms.locator("body")).not_to_contain_text("IMGW-PIB: dane publiczne")
    expect(terms.locator("body")).not_to_contain_text("opady maksymalne PMAXTP")
