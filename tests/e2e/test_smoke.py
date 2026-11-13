"""
The GUI's smoke test (GUI plan S9): every view opens without a console error, a page
error or a Content-Security-Policy violation, in both themes, on a desktop and a phone,
and the user guide's examples work on the fixture data root.

The views: the start page of both servers, „Pomiary bieżące” and „PMAXTP” with the
recorded point, each station of FIXTURE_STATIONS with every card opened, the guide
(``instrukcja/``) and ``regulamin.html``. The stations open on ``stored_url``, the fixture
root with its analyses stored and no Hydrolog's program, so the test does not depend on
it: a card opened shows the stored results, so none of its requests of an analysis names
an option (a choice of the person is computed on request, which this server refuses),
and its only errors are those Hydrolog stored. The guide's links into the app open their
view, a station's with its panel and the card the link names; its command lines
(``pre.cli-line``) run on the fixture root with stored analyses and write their files.
"""

from __future__ import annotations

import re
import shlex
from html import unescape
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest
from typer.testing import CliRunner

from obserwator.cli.main import app
from obserwator.gui import WEB_DIR
from tests.e2e.conftest import FIXTURE_STATIONS, PMAXTP_POINT, THEMES, WIDTHS

expect = pytest.importorskip("playwright.sync_api").expect

GUIDE = (WEB_DIR / "instrukcja" / "index.html").read_text(encoding="utf-8")
WAIT = 20_000
"""How long a view may take to draw what it shows [ms]."""
ANALYSIS_IDS = """async () => [
  ...(await import("./src/sections/hydro/index.js")).HYDRO_SECTIONS,
  ...(await import("./src/sections/meteo/index.js")).METEO_SECTIONS,
].map((entry) => entry.id)"""
"""The ids of the analysis cards, from the page's own registries."""
MISSING_ANCHORS = """() => [...document.querySelectorAll('a[href^="#"]')]
  .map((link) => link.getAttribute("href").slice(1))
  .filter((id) => !document.getElementById(id))"""
"""The in-page links of a document whose target is missing."""
OPEN_CARDS = """async () => {
  for (const button of document.querySelectorAll(".acc-item:not(.open) .acc-head button")) {
    button.click();
    await new Promise((resolve) => setTimeout(resolve, 0));
  }
  return [...document.querySelectorAll(".acc-item")].map((item) => item.dataset.section);
}"""
"""Open every closed card of the station panel, one after the other; the ids of all."""


def guide_links() -> list[str]:
    """The guide's links into the app (``../?…``), each once."""
    return sorted(
        {unescape(href) for href in re.findall(r'href="(\.\./\?[^"]*)"', GUIDE)}
    )


def guide_commands() -> list[list[str]]:
    """The command lines the guide shows (``pre.cli-line``), as words."""
    pattern = r'<pre class="[^"]*\bcli-line\b[^"]*"><code>(.*?)</code></pre>'
    return [
        shlex.split(unescape(line)) for line in re.findall(pattern, GUIDE, re.DOTALL)
    ]


def settle(page: Any) -> None:
    """Wait until the page has asked for everything it draws."""
    page.wait_for_load_state("networkidle")


def stored_failures(page: Any, base: str, code: str) -> set[str]:
    """The messages of the analyses of a station that Hydrolog stored as failed."""
    listed = page.request.get(f"{base}api/analyses/{code}").json()["analyses"]
    found = set()
    for entry in listed:
        if entry["status"] == "failed":
            url = f"{base}api/analysis/{code}/{entry['analysis']}"
            error = page.request.get(url).json()["error"]
            found.add(error.get("message") or error["title"])
    return found


def open_cards(page: Any) -> tuple[list[str], list[str]]:
    """
    Open every card of the station panel and wait until they asked for all they draw.

    Returns the ids of the cards and the addresses of the API asked meanwhile. The page's
    load state "networkidle" is reached once per page, so the requests are followed here.
    """
    page.locator(".station-panel .station-head").wait_for(
        state="attached", timeout=WAIT
    )
    # The analysis cards come once api/analyses answered
    settle(page)
    asked: list[str] = []
    running: set[Any] = set()

    def started(request: Any) -> None:
        if "/api/" in request.url:
            asked.append(request.url)
        running.add(request)

    def ended(request: Any) -> None:
        running.discard(request)

    page.on("request", started)
    page.on("requestfinished", ended)
    page.on("requestfailed", ended)
    cards = page.evaluate(OPEN_CARDS)
    expect(page.locator(".acc-item.open .acc-body")).to_have_count(len(cards))
    quiet = 0
    for _ in range(WAIT // 50):
        quiet = 0 if running else quiet + 1
        if quiet == 10:
            break
        page.wait_for_timeout(50)
    assert not running, [request.url for request in running]
    return cards, asked


@pytest.mark.parametrize("theme", THEMES)
@pytest.mark.parametrize("width", WIDTHS)
def test_every_view_opens_cleanly(
    open_page, gui_url, public_url, stored_url, theme, width
):
    options = {"theme": theme, "width": width, "height": 900 if width > 860 else 844}
    for base in (gui_url, public_url):
        page = open_page(base=base, **options)
        page.locator(".station-list .stations li").first.wait_for(
            state="attached", timeout=WAIT
        )
        settle(page)

    page = open_page("?view=current", **options)
    expect(page.locator(".view-bar .hint")).to_contain_text(
        "Migawka IMGW-PIB z", timeout=WAIT
    )
    settle(page)

    latitude, longitude = PMAXTP_POINT
    page = open_page(f"?view=pmaxtp&lat={latitude:.4f}&lon={longitude:.4f}", **options)
    page.locator(".pm-table").wait_for(state="attached", timeout=WAIT)
    settle(page)

    analysis_ids: set[str] | None = None
    for code in FIXTURE_STATIONS.values():
        page = open_page(f"?station={code}", base=stored_url, **options)
        if analysis_ids is None:
            analysis_ids = set(page.evaluate(ANALYSIS_IDS))
        cards, asked = open_cards(page)
        assert {"stacja", "teraz", "dane", "pobierz"} <= set(cards)
        assert set(cards) & analysis_ids, code
        # A card opened shows the stored results: no request names an option
        results = [url for url in asked if "/api/analysis/" in url]
        assert results, code
        assert [url for url in results if urlsplit(url).query] == []
        stored = stored_failures(page, stored_url, code)
        for text in page.locator(".acc-item .ana-error").all_inner_texts():
            rest = text
            for failure in stored:
                rest = rest.replace(failure, "")
            assert text.strip() and not rest.strip(), (code, text)

    page = open_page("instrukcja/", ready=False, **options)
    page.locator(".guide-toc").wait_for(timeout=WAIT)
    settle(page)
    assert page.evaluate("document.documentElement.lang") == "pl"
    assert page.evaluate("document.documentElement.dataset.theme") == theme
    expect(page.locator(f'[data-theme-choice="{theme}"]')).to_have_attribute(
        "aria-pressed", "true"
    )
    assert page.evaluate(MISSING_ANCHORS) == []
    assert page.evaluate("document.documentElement.scrollWidth") <= width

    page = open_page("regulamin.html", base=public_url, ready=False, **options)
    page.locator("main.nogat-terms h1").wait_for(timeout=WAIT)
    settle(page)


def test_the_guides_links_open_their_views(open_page, public_url):
    links = guide_links()
    assert any("station=" in link for link in links)
    for link in links:
        query = {
            key: values[0] for key, values in parse_qs(urlsplit(link).query).items()
        }
        page = open_page(link.removeprefix("../"), base=public_url)
        if "station" in query:
            head = page.locator(".station-panel .station-head")
            expect(head.locator("code.chip")).to_have_text(
                query["station"], timeout=WAIT
            )
            if "section" in query:
                card = page.locator(
                    f'.acc-item.open[data-section="{query["section"]}"]'
                )
                card.locator(".acc-body").wait_for(state="attached", timeout=WAIT)
        elif query.get("view") == "pmaxtp":
            page.locator(".pm-table").wait_for(state="attached", timeout=WAIT)
        else:
            expect(page.locator(".view-bar .hint")).to_contain_text(
                "Migawka IMGW-PIB z", timeout=WAIT
            )
        settle(page)
    # Every picture of the guide is served
    page = open_page("instrukcja/", base=public_url, ready=False)
    sources = page.locator("img").evaluate_all(
        "(images) => images.map((image) => image.src)"
    )
    assert sources
    assert [src for src in sources if not page.request.get(src).ok] == []


def test_the_guides_command_lines_write_their_files_on_the_fixture_root(
    stored_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    commands = guide_commands()
    assert commands
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    for words in commands:
        assert words[0] == "obserwator", words
        result = runner.invoke(app, [*words[1:], "--root", str(stored_root)])
        assert result.exit_code == 0, f"{shlex.join(words)}\n{result.output}"
        written = tmp_path / words[words.index("--output") + 1]
        assert written.stat().st_size > 0, shlex.join(words)
