"""
A provider fed by files in the browser (ADR-033): the test provider SIEC of
``tests/fixtures/files``, imported by ``obserwator store import --provider-file`` and served
by ``obserwator gui serve``, both programs in processes of their own as an operator runs
them (the provider registry reads ``nogat.toml`` as it is imported).

Its stations are on the list and the map; the view's strip (``.view-foot nogat-sources``)
shows the line the provider file declares in its short form, the full line behind
„Źródła i warunki”; a station carries the chip „Inne źródło”, P8's notice in the provider's
own words (the session's ``source_notice``) and the flag of operational, unverified data;
and nothing offers the hand-off to Hydrolog, which stays the national services' (IMGW-PIB,
ČHMÚ).

Beside IMGW-PIB's and ČHMÚ's stations (``beside_site``, the fixture data root with SIEC
imported) the page separates the two classes of sources (hydromet P11 to P13): the class
switch „Wszystkie | Służby | Inne źródła” chooses the stations of the list and the map, the
dataset chips stand under the headings of their classes and their providers with their
countries, a station of another source is outlined dashed (on the map's canvas and in the
list, the legend explaining both outlines) and a service's solid, the panel without a
station counts the stations by class, and every chart and table of a station of another
source carries its class.
"""

from __future__ import annotations

import contextlib
import csv
import json
import os
import queue
import shutil
import subprocess
import threading
from collections.abc import Iterable, Iterator
from datetime import date
from pathlib import Path
from typing import Any
from urllib.request import urlopen

import pytest

from obserwator.messages import message
from tests.contract.support import SERVER_FLAGS, STOP_SIGNAL, obserwator_executable
from tests.e2e.conftest import FIXTURE_STATIONS, WIDTHS, _free_port
from tests.e2e.test_map import wait_drawn, wait_listed

expect = pytest.importorskip("playwright.sync_api").expect
PlaywrightTimeout = pytest.importorskip("playwright.sync_api").TimeoutError

WAIT = 15_000
FILES = Path(__file__).resolve().parents[1] / "fixtures" / "files"
DEADLINE_S = 120.0
"""The longest wait for the import, and for the server to start or to stop [s]."""
LINE = (
    "Źródło danych: Sieć Testowa Operatora sp. z o.o., licencja CC BY 4.0 "
    "(https://creativecommons.org/licenses/by/4.0/)"
)
"""The line of ``siec.toml`` (``[attribution] line``)."""
SHORT = "Źródło: Sieć Testowa, CC BY 4.0"
"""Its short form, for the strip (``[attribution] short``)."""
LISTED = {"SIEC-01", "SIEC-02", "SIEC-M1", "SIEC-X1"}
"""The active stations, listed on a first visit („tylko czynne”): not SIEC-03."""
MAPPED = {"SIEC-01", "SIEC-02", "SIEC-M1"}
"""The located ones: SIEC-X1's point lies outside Poland, so the import drops it."""
DASHED = ["5px, 3px", "2.6px"]
"""The outline of a symbol of another source in SVG: its dashes and its width."""
SOLID = ["none", "2px"]
"""The outline of a symbol of a national service: hydro.imgw.pl's solid grey line."""
# The image each station drawn on the map takes, by its code
_ICONS = """() => Object.fromEntries(document.querySelector('.map').maplibre
  .queryRenderedFeatures({ layers: ['stations'] })
  .map((feature) => [feature.properties.code, feature.properties.icon]))"""
# The transparent pixels of the map's images of a triangle in the row 0.8 units under the
# box's top (inside the outline, above the body), between a fifth and four fifths of the
# width, the straight top edge: the gaps of a dashed outline, none of a solid one
_GAPS = """(names) => {
  const map = document.querySelector('.map').maplibre;
  return Object.fromEntries(names.map((name) => {
    const { width, height, data } = map.getImage(name).data;
    const row = Math.floor((0.8 * height) / 34);
    let gaps = 0;
    for (let x = Math.round(width / 5); x < Math.round((4 * width) / 5); x += 1) {
      if (data[(row * width + x) * 4 + 3] < 64) gaps += 1;
    }
    return [name, gaps];
  }));
}"""
# An SVG symbol's outline as drawn: its dashes and its width
_OUTLINE = """(symbol) => {
  const edge = getComputedStyle(symbol.querySelector('.edge'));
  return [edge.strokeDasharray, edge.strokeWidth];
}"""


def _parquet(csv_file: Path) -> None:
    """Replace a CSV of dates and ``H [cm]`` by its Parquet file, a missing day as null."""
    import pyarrow as pa
    import pyarrow.parquet as pq

    with csv_file.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    table = pa.table(
        {
            "date": pa.array(
                [date.fromisoformat(r["date"]) for r in rows], pa.date32()
            ),
            "H [cm]": pa.array(
                [float(r["H [cm]"]) if r["H [cm]"] else None for r in rows],
                pa.float64(),
            ),
        }
    )
    pq.write_table(table, csv_file.with_suffix(".parquet"))
    csv_file.unlink()


def _environment(config: Path) -> dict[str, str]:
    """
    The programs' environment: ``config`` as ``NOGAT_CONFIG``, no ``OBSERWATOR_*`` setting
    but the tests' state directory, no basemap, no Hydrolog and proxies that lead nowhere.
    """
    dead = "http://127.0.0.1:9"
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("OBSERWATOR_") or key == "OBSERWATOR_STATE_DIR"
    }
    env |= {
        "NOGAT_CONFIG": str(config),
        "OBSERWATOR_GUI_BASEMAP_URL": "none",
        "HTTP_PROXY": dead,
        "HTTPS_PROXY": dead,
        "ALL_PROXY": dead,
        "NO_PROXY": "",
        "PATH": os.pathsep.join(
            folder
            for folder in env.get("PATH", "").split(os.pathsep)
            if shutil.which("hydrolog", path=folder) is None
        ),
    }
    return env


def _drain(stream: Iterable[str] | None, lines: queue.Queue[str]) -> None:
    """Put each line of a stream on a queue until the stream ends."""
    for line in stream or ():
        lines.put(line)


@contextlib.contextmanager
def _served(work: Path, root: Path) -> Iterator[str]:
    """
    SIEC imported by ``store import`` into the data root ``root`` from a copy of
    ``tests/fixtures/files`` (SIEC-02 as Parquet) under ``work``, and ``obserwator gui
    serve`` on that root: its URL while it runs.
    """
    config = work / "config"
    shutil.copytree(FILES, config)
    _parquet(config / "siec" / "hydro" / "SIEC-02.csv")
    env = _environment(config / "nogat.toml")
    imported = subprocess.run(
        [*obserwator_executable(), "store", "import", "--root", str(root)]
        + ["--raw-root", str(work / "raw"), "--provider-file", "siec.toml", "--json"],
        capture_output=True,
        encoding="utf-8",
        env=env,
        timeout=DEADLINE_S,
        check=False,
    )
    assert imported.returncode == 0, imported.stderr
    assert json.loads(imported.stdout)["status"] == "ok"
    port = _free_port()
    process = subprocess.Popen(
        [*obserwator_executable(), "gui", "serve", "--no-browser", "--port", str(port)]
        + ["--root", str(root)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        encoding="utf-8",
        env=env,
        creationflags=SERVER_FLAGS,
    )
    # The lifecycle records on standard error, read to the end so the pipe never fills
    lines: queue.Queue[str] = queue.Queue()
    threading.Thread(target=_drain, args=(process.stderr, lines), daemon=True).start()
    try:
        start = json.loads(lines.get(timeout=DEADLINE_S))
        assert start["event"] == "start", start
        yield start["settings"]["url"]
    finally:
        process.send_signal(STOP_SIGNAL)
        try:
            process.wait(timeout=DEADLINE_S)
        except subprocess.TimeoutExpired:  # pragma: no cover - only when it hangs
            process.kill()
            process.wait()


@pytest.fixture(scope="module")
def file_provider_site(tmp_path_factory) -> Iterator[str]:
    """``obserwator gui serve`` on a data root of SIEC alone; its URL."""
    work = tmp_path_factory.mktemp("file-provider")
    with _served(work, work / "data") as url:
        yield url


@pytest.fixture(scope="module")
def beside_site(fixture_root, tmp_path_factory) -> Iterator[str]:
    """
    ``obserwator gui serve`` on a copy of the fixture data root (IMGW-PIB's and ČHMÚ's
    stations and series) with SIEC imported beside them; its URL. Its server answers no
    current data (its requests lead nowhere), so a test opens no card of them.
    """
    work = tmp_path_factory.mktemp("file-provider-beside")
    shutil.copytree(fixture_root, work / "data")
    with _served(work, work / "data") as url:
        yield url


def _api(base: str, path: str) -> Any:
    with urlopen(base + path, timeout=10) as answer:
        return json.load(answer)


def _station(open_page: Any, base: str, code: str, section: str, **options: Any) -> Any:
    """A station's page with a section open: its panel."""
    page = open_page(f"?station={code}&section={section}", base=base, **options)
    panel = page.locator("#panel-right")
    expect(panel.locator(f'.acc-item.open[data-section="{section}"]')).to_be_visible(
        timeout=WAIT
    )
    return panel


def test_the_stations_of_a_provider_fed_by_files_are_on_the_list_and_the_map(
    open_page: Any, file_provider_site: str
) -> None:
    stations = _api(file_provider_site, "api/stations")["stations"]
    assert {s["provider"] for s in stations} == {"SIEC"}
    page = open_page(base=file_provider_site)
    page.wait_for_function(
        "(codes) => JSON.stringify([...document.querySelectorAll('.stations .st-item')]"
        ".map((item) => item.dataset.code).sort()) === JSON.stringify(codes)",
        arg=sorted(LISTED),
        timeout=WAIT,
    )
    # its chips under its name and country; one class of sources: no class switch, no
    # class heading, but the legend explains the dashed outline of its stations
    expect(page.locator(".ds-group .ds-provider")).to_have_text(["Sieć Testowa · PL"])
    expect(page.locator(".ds-class-title")).to_have_count(0)
    expect(page.get_by_role("radiogroup", name="Rodzaj źródła")).to_have_count(0)
    expect(page.locator(".map-legend .legend-classes li")).to_have_text(
        ["Służba hydrologiczno-meteorologiczna", "Inne źródło"]
    )
    # the map draws on a canvas, a while after the list: once it draws the stations, its
    # stations' source holds where it shows them
    wait_drawn(page, ["stations"], MAPPED)
    drawn = page.evaluate(
        """async () => {
          const map = document.querySelector('.map').maplibre;
          const data = await map.getSource('stations').getData();
          return data.features.map((f) => [f.properties.code, f.geometry.coordinates]);
        }"""
    )
    located = {
        s["code"]: [s["lon"], s["lat"]] for s in stations if s["lon"] is not None
    }
    assert dict(drawn) == {code: located[code] for code in MAPPED}


@pytest.mark.parametrize("width", WIDTHS)
def test_the_strip_shows_the_declared_line_in_its_short_form(
    open_page: Any, file_provider_site: str, width: int, tmp_path: Path
) -> None:
    panel = _station(
        open_page, file_provider_site, "SIEC-01", "dane", width=width, height=844
    )
    page = panel.page
    strip = page.locator(".view-foot nogat-sources")
    expect(page.locator("nogat-sources")).to_have_count(1)
    expect(strip).to_have_count(1)
    # the strip is redrawn whenever its lines change: the station's arrive with its page,
    # the borders' (GUGiK's PRG, ČÚZK's RÚIAN) once the map has them as its background, so
    # the strip is measured only after both
    origins = _api(file_provider_site, "api/session")["attribution"]["origins"]
    lines = [
        line for name in ("gugik", "cuzk") for line in origins[name]["attribution"]
    ]
    lines.append(LINE)
    with contextlib.suppress(PlaywrightTimeout):
        page.wait_for_function(
            "(want) => { const got = document.querySelector('.view-foot nogat-sources')"
            "?.attribution || []; return want.every((line) => got.includes(line)); }",
            arg=lines,
            timeout=WAIT,
        )
    assert set(lines) <= set(strip.evaluate("(element) => element.attribution"))
    on_screen = strip.locator(".nogat-sources-strip")
    expect(on_screen).to_contain_text(SHORT)
    expect(on_screen).not_to_contain_text("Operatora sp. z o.o.")
    # its words link where the provider file says
    expect(on_screen.get_by_role("link", name="Sieć Testowa")).to_have_attribute(
        "href", "https://example.org/siec"
    )
    assert LINE in strip.evaluate("(element) => element.attribution")
    foot = page.locator(".view-foot")
    # one line is less than twice the font size high, two lines more
    size = float(on_screen.evaluate("(e) => parseFloat(getComputedStyle(e).fontSize)"))
    box = on_screen.bounding_box()
    assert box is not None and box["height"] < 2 * size
    if width < 1440:
        # the station's sheet stops above the strip, cut to one line on a phone, which
        # „więcej” unfolds in place
        expect(panel).to_have_css("transform", "none")
        sheet = panel.bounding_box()
        bottom = foot.bounding_box()
        assert sheet is not None and bottom is not None
        assert sheet["y"] + sheet["height"] <= bottom["y"] + 1
        strip.get_by_role("button", name="więcej").click()
        box = on_screen.bounding_box()
        assert box is not None and box["height"] > 2 * size
    expect(on_screen.get_by_text(SHORT)).to_be_in_viewport()
    foot.screenshot(path=str(tmp_path / f"strip-{width}.png"))
    # the full line behind „Źródła i warunki”
    strip.get_by_role("button", name="Źródła i warunki").click()
    dialog = strip.locator("dialog")
    expect(dialog).to_be_visible()
    expect(dialog).to_contain_text(LINE)
    page.keyboard.press("Escape")
    expect(dialog).to_be_hidden()


@pytest.mark.parametrize("code", ["SIEC-01", "SIEC-M1"])
def test_a_station_shows_another_source_and_its_unverified_data(
    open_page: Any, file_provider_site: str, code: str
) -> None:
    # P8's notice of a provider fed by files, in its own words, as the session gives it
    notice = str(message("datasets.source_notice_other", "pl"))
    provider = _api(file_provider_site, "api/session")["providers"]["SIEC"]
    assert (provider["country"], provider["source_notice"]) == ("PL", notice)
    panel = _station(open_page, file_provider_site, code, "dane")
    # the header opens with the class of the source, its notice under the tags
    expect(panel.locator(".station-tags > *").first).to_have_text("Inne źródło")
    expect(panel.locator("[data-part=source-class]")).to_have_text("Inne źródło")
    expect(panel.locator("[data-part=source-note]")).to_have_text(notice)
    expect(panel.locator("[data-part=unverified]").first).to_have_text(
        "dane operacyjne, niezweryfikowane"
    )


def test_a_hydrological_station_offers_no_handoff_to_hydrolog(
    open_page: Any, file_provider_site: str
) -> None:
    panel = _station(open_page, file_provider_site, "SIEC-01", "pobierz")
    page = panel.page
    item = panel.locator('.acc-item[data-section="pobierz"]')
    expect(item.locator(".files a").first).to_be_visible(timeout=WAIT)
    # its series file is offered, the hand-off of „Pobierz” and of the analyses is not
    expect(item).to_contain_text("obserwator_series_pl.siec.hydro_daily_SIEC-01.csv")
    expect(panel.locator(".handoff-box")).to_have_count(0)
    expect(panel).not_to_contain_text("Przekazanie do Hydrologa")
    expect(panel.locator('img[src$="hydrolog.svg"]')).to_have_count(0)
    asked = page.evaluate("performance.getEntriesByType('resource').map((e) => e.name)")
    assert any(url.endswith("/api/session") for url in asked)
    assert not [url for url in asked if "/api/handoff/" in url]


# --- beside IMGW-PIB and ČHMÚ: the classes of sources (hydromet P11 to P13) -------------


def _classes(base: str) -> dict[str, str]:
    """The class of the source of each station a server serves, by its code."""
    providers = _api(base, "api/session")["providers"]
    return {
        s["code"]: providers[s["provider"]]["source_class"]
        for s in _api(base, "api/stations")["stations"]
    }


def test_the_class_switch_and_the_chips_separate_the_classes_of_sources(
    open_page: Any, beside_site: str
) -> None:
    stations = {s["code"]: s for s in _api(beside_site, "api/stations")["stations"]}
    session = _api(beside_site, "api/session")
    sources = _classes(beside_site)
    assert {s["provider"]: sources[c] for c, s in stations.items()} == {
        "IMGW": "nmhs",
        "CHMU": "nmhs",
        "SIEC": "other",
    }

    def shown(source: str | None = None, *, located: bool = False) -> set[str]:
        """The stations of a first visit („tylko czynne”) of a class, or of both."""
        return {
            code
            for code, s in stations.items()
            if s["active"]
            and source in (None, sources[code])
            and (s["lon"] is not None or not located)
        }

    page = open_page(base=beside_site)
    radios = page.get_by_role("radiogroup", name="Rodzaj źródła").get_by_role("radio")
    expect(radios).to_have_text(["Wszystkie", "Służby", "Inne źródła"])
    expect(radios.nth(0)).to_have_attribute("aria-checked", "true")
    wait_listed(page, shown())
    wait_drawn(page, ["stations"], shown(located=True))
    # the chips under the headings of the classes, each provider with its country, the
    # providers of a class by country
    chips = page.locator(".ds-filter")
    expect(chips.locator(".ds-class-title")).to_have_text(
        ["Służby hydrologiczno-meteorologiczne", "Inne źródła"]
    )
    groups = chips.locator(".ds-class")
    expect(groups.nth(0).locator(".ds-provider")).to_have_text(
        ["ČHMÚ · CZ", "IMGW-PIB · PL"]
    )
    expect(groups.nth(1).locator(".ds-provider")).to_have_text(["Sieć Testowa · PL"])
    # the panel without a station counts every station of each class above its providers
    rows = page.locator("#panel-right [data-part=catalogs] tr.class-row")
    expect(rows.locator("th")).to_have_text(
        [
            "Służby hydrologiczno-meteorologiczne: hydrologiczne · meteorologiczne",
            "Inne źródła: hydrologiczne · meteorologiczne",
        ]
    )
    expect(rows.locator("td")).to_have_text(
        [
            " · ".join(
                str(
                    sum(
                        sources[c] == source and s["kind"] == kind
                        for c, s in stations.items()
                    )
                )
                for kind in ("hydro", "meteo")
            )
            for source in ("nmhs", "other")
        ]
    )
    files = page.locator("#panel-right .stations-files")
    expect(files.locator("tr").first).to_contain_text("Wszyscy")
    # „Inne źródła”: its stations alone, its chips without a heading, and the stations
    # file of the one provider left
    radios.nth(2).click()
    wait_listed(page, shown("other"))
    wait_drawn(page, ["stations"], shown("other", located=True))
    expect(chips.locator(".ds-class-title")).to_have_count(0)
    expect(chips.locator(".ds-provider")).to_have_text(["Sieć Testowa · PL"])
    expect(files.locator("tr").first).to_contain_text("Sieć Testowa")
    offered = _api(beside_site, "api/downloads/stations?provider=SIEC")["stations"]
    expect(files.locator(".files-count")).to_have_text(str(offered), timeout=WAIT)
    # „Służby”: the national services' stations, of two providers
    radios.nth(1).click()
    wait_listed(page, shown("nmhs"))
    wait_drawn(page, ["stations"], shown("nmhs", located=True))
    expect(files.locator("tr").first).to_contain_text("Wszyscy")
    # one provider chosen by its chips, under both classes again
    radios.nth(0).click()
    title = session["datasets"]["pl.siec.hydro_daily"]["title"]
    page.get_by_role("button", name=title).click()
    wait_listed(
        page, {c for c in shown() if "pl.siec.hydro_daily" in stations[c]["datasets"]}
    )
    expect(files.locator("tr").first).to_contain_text("Sieć Testowa")


def test_a_station_of_another_source_is_outlined_dashed_and_a_service_solid(
    open_page: Any, beside_site: str
) -> None:
    sources = _classes(beside_site)
    stations = _api(beside_site, "api/stations")["stations"]
    located = {s["code"] for s in stations if s["active"] and s["lon"] is not None}
    page = open_page(base=beside_site)
    wait_drawn(page, ["stations"], located)
    # the map: each station's image is of the class of its source, never of its provider
    icons = page.evaluate(_ICONS)
    assert {code: icon.rsplit("-", 1)[1] for code, icon in icons.items()} == {
        code: sources[code] for code in located
    }
    assert {sources[code] for code in icons} == {"nmhs", "other"}
    # whose outline the canvas draws dashed for another source, solid for a service
    gaps = page.evaluate(_GAPS, ["st-hydro-1-other", "st-hydro-1-nmhs"])
    assert gaps["st-hydro-1-nmhs"] == 0
    assert gaps["st-hydro-1-other"] > 5
    # the list draws the same outlines
    service = min(code for code in located if sources[code] == "nmhs")
    for code, outline in (("SIEC-01", DASHED), (service, SOLID)):
        symbol = page.locator(f'.st-item[data-code="{code}"] svg.sym')
        assert symbol.evaluate(_OUTLINE) == outline, code
    # and the legend explains both, under the marks of every station
    legend = page.locator(".map-legend")
    entries = legend.locator(".legend-classes li")
    expect(entries).to_have_text(
        ["Służba hydrologiczno-meteorologiczna", "Inne źródło"]
    )
    assert entries.nth(0).locator("svg.sym").evaluate(_OUTLINE) == SOLID
    assert entries.nth(1).locator("svg.sym").evaluate(_OUTLINE) == DASHED
    expect(legend.locator("li").first).to_have_text("hydrologiczna")
    assert legend.locator("li").first.locator("svg.sym").evaluate(_OUTLINE) == SOLID
    # the tooltip names the provider of a station of another source
    station = next(s for s in stations if s["code"] == "SIEC-01")
    x, y = page.evaluate(
        """([lon, lat]) => {
          const map = document.querySelector('.map').maplibre;
          const box = map.getCanvas().getBoundingClientRect();
          const point = map.project([lon, lat]);
          return [box.left + point.x, box.top + point.y];
        }""",
        [station["lon"], station["lat"]],
    )
    page.mouse.move(x, y)
    expect(page.get_by_role("tooltip")).to_contain_text("Sieć Testowa")


def test_every_chart_and_table_of_another_source_carries_its_class(
    open_page: Any, beside_site: str
) -> None:
    panel = _station(open_page, beside_site, "SIEC-01", "dane")
    card = panel.locator('.acc-item[data-section="dane"]')
    charts = card.locator(".chart")
    expect(charts.first).to_be_visible(timeout=WAIT)
    # a badge right above each chart, then above the table
    expect(card.locator(".data-badge + .chart")).to_have_count(charts.count())
    card.get_by_role("button", name="Tabela").click()
    table = card.locator(".data-table")
    expect(table.locator(".data-badge + .table-wrap")).to_have_count(1)
    expect(table.locator("[data-part=class-badge]")).to_have_text("Inne źródło")
    expect(card.locator("[data-part=class-badge]")).to_have_text(
        ["Inne źródło"] * (charts.count() + 1)
    )
    # a national service's station of the same page: no class, no notice, no badge (its
    # „Pomiary bieżące” stays closed: this server answers no current data)
    panel = _station(open_page, beside_site, FIXTURE_STATIONS["hydro"], "dane")
    card = panel.locator('.acc-item[data-section="dane"]')
    expect(card.locator(".chart").first).to_be_visible(timeout=WAIT)
    card.get_by_role("button", name="Tabela").click()
    expect(card.locator(".data-table .table-wrap")).to_have_count(1)
    for part in ("source-class", "source-note", "class-badge"):
        expect(panel.locator(f"[data-part={part}]")).to_have_count(0)
