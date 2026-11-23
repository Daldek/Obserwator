"""
A provider fed by files in the browser (ADR-033): the test provider SIEC of
``tests/fixtures/files``, imported by ``obserwator store import --provider-file`` and served
by ``obserwator gui serve``, both programs in processes of their own as an operator runs
them (the provider registry reads ``nogat.toml`` as it is imported).

Its stations are on the list and the map; the view's strip (``.view-foot nogat-sources``)
shows the line the provider file declares in its short form, the full line behind
„Źródła i warunki”; a station carries the chip „Inne źródło”, the note that its data do not
come from a national service and the flag of operational, unverified data; and nothing
offers the hand-off to Hydrolog, which stays the national services' (IMGW-PIB, ČHMÚ).
"""

from __future__ import annotations

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

from tests.contract.support import SERVER_FLAGS, STOP_SIGNAL, obserwator_executable
from tests.e2e.conftest import WIDTHS, _free_port

expect = pytest.importorskip("playwright.sync_api").expect

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


@pytest.fixture(scope="module")
def file_provider_site(tmp_path_factory) -> Iterator[str]:
    """
    ``obserwator gui serve`` on a data root of SIEC alone, as ``store import`` builds it from
    a copy of ``tests/fixtures/files`` with SIEC-02 as Parquet; its URL.
    """
    work = tmp_path_factory.mktemp("file-provider")
    config = work / "config"
    shutil.copytree(FILES, config)
    _parquet(config / "siec" / "hydro" / "SIEC-02.csv")
    root = work / "data"
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
    expect(page.locator(".ds-group .ds-provider")).to_have_text(["Sieć Testowa"])
    # the map draws on a canvas: its stations' source holds what it shows
    page.wait_for_function(
        "() => { const map = document.querySelector('.map').maplibre;"
        " return Boolean(map && map.getSource('stations')); }",
        timeout=WAIT,
    )
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
    panel = _station(open_page, file_provider_site, code, "dane")
    expect(panel.locator("[data-part=source-class]")).to_have_text("Inne źródło")
    expect(panel.locator("[data-part=source-note]")).to_have_text(
        "Dane tej stacji nie pochodzą od państwowej służby "
        "hydrologiczno-meteorologicznej."
    )
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
