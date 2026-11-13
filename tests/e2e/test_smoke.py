"""
The GUI's smoke test (GUI plan S9): every view opens without a console error, a page
error or a Content-Security-Policy violation, in both themes, on a desktop and a phone,
and the user guide's examples work on the fixture data root.

The views: the start page of both servers, „Pomiary bieżące” and „PMAXTP” with the
recorded point, each station of FIXTURE_STATIONS with its cards opened, the guide
(``instrukcja/``) and ``regulamin.html``. The stations open on ``public_url``, which never
has Hydrolog, so the test does not depend on it: their cards are those that need no
analysis result (the fixture root stores none), taken from the page's registries. The
guide's links into the app open their view, a station's with its panel and the card the
link names; its command lines (``pre.cli-line``) run on the fixture root and write their
files.
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


def open_cards(page: Any, analysis_ids: set[str]) -> list[str]:
    """Open every card of the station panel that needs no analysis result."""
    page.locator(".station-panel .station-head").wait_for(
        state="attached", timeout=WAIT
    )
    ids = page.locator(".acc-item").evaluate_all(
        "(items) => items.map((item) => item.dataset.section)"
    )
    cards = [card for card in ids if card not in analysis_ids]
    for card in cards:
        item = page.locator(f'.acc-item[data-section="{card}"]')
        if not item.evaluate("(node) => node.classList.contains('open')"):
            item.locator(".acc-head button").click()
        item.locator(".acc-body").wait_for(state="attached", timeout=WAIT)
    settle(page)
    for card in cards:
        expect(
            page.locator(f'.acc-item[data-section="{card}"] .acc-body .ana-error')
        ).to_have_count(0)
    return cards


@pytest.mark.parametrize("theme", THEMES)
@pytest.mark.parametrize("width", WIDTHS)
def test_every_view_opens_cleanly(open_page, gui_url, public_url, theme, width):
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
        page = open_page(f"?station={code}", base=public_url, **options)
        if analysis_ids is None:
            analysis_ids = set(page.evaluate(ANALYSIS_IDS))
        assert {"stacja", "teraz", "dane", "pobierz"} <= set(
            open_cards(page, analysis_ids)
        )

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
    gui_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    commands = guide_commands()
    assert commands
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    for words in commands:
        assert words[0] == "obserwator", words
        result = runner.invoke(app, [*words[1:], "--root", str(gui_root)])
        assert result.exit_code == 0, f"{shlex.join(words)}\n{result.output}"
        written = tmp_path / words[words.index("--output") + 1]
        assert written.stat().st_size > 0, shlex.join(words)
