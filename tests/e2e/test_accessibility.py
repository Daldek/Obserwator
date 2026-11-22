"""
The page under axe-core: the start page and a station's panel, on a desktop and a phone.

axe-core is a file of the tests (``tests/e2e/vendor/``, MPL-2.0), never served by the GUI;
it runs through Playwright's evaluation, outside the page's CSP. A violation of impact
``serious`` or ``critical`` fails; so does any of the rules the page once broke (the
level-one heading, the names of its landmarks, the key figures' ``<dl>``).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from tests.e2e.conftest import FIXTURE_STATIONS, WIDTHS

expect = pytest.importorskip("playwright.sync_api").expect

VENDOR = Path(__file__).resolve().parent / "vendor"
WAIT = 20_000
FIXED = ("page-has-heading-one", "landmark-unique", "definition-list", "dlitem")
"""Rules the page broke before 3.1.0 (axe-core 4.13 on the deployment, 2026-11-20)."""


def _axe() -> str:
    manifest = json.loads((VENDOR / "vendor.json").read_text(encoding="utf-8"))
    entry = manifest["libraries"][0]["files"]["axe-core/axe.min.js"]
    source = (VENDOR / "axe-core" / "axe.min.js").read_bytes()
    assert hashlib.sha256(source).hexdigest() == entry["sha256"]
    return source.decode("utf-8")


def _violations(page: Any) -> list[dict[str, Any]]:
    page.evaluate(_axe())
    result: dict[str, Any] = page.evaluate("axe.run(document)")
    return [
        {
            "id": v["id"],
            "impact": v["impact"],
            "nodes": [node["target"] for node in v["nodes"]],
        }
        for v in result["violations"]
    ]


def _assert_accessible(page: Any) -> None:
    found = _violations(page)
    bad = [v for v in found if v["impact"] in ("serious", "critical")]
    bad += [v for v in found if v["id"] in FIXED and v not in bad]
    assert bad == []


@pytest.mark.parametrize("width", WIDTHS)
def test_the_start_page_has_no_serious_accessibility_violation(open_page, width):
    page = open_page(width=width, height=900)
    page.locator("ul.stations li").first.wait_for(state="attached", timeout=WAIT)
    expect(page.locator("h1")).to_have_count(1)
    _assert_accessible(page)


@pytest.mark.parametrize("width", WIDTHS)
def test_a_station_panel_has_no_serious_accessibility_violation(open_page, width):
    station = FIXTURE_STATIONS["hydro"]
    page = open_page(f"?station={station}&section=teraz", width=width, height=900)
    # „Pomiary bieżące” with its key figures, whose notes are `dd`s of their tiles
    tiles = page.locator('.acc-item[data-section="teraz"] dl.figures > div')
    tiles.first.wait_for(timeout=WAIT)
    expect(tiles.locator("dd.figure-note small").first).to_be_attached()
    _assert_accessible(page)
    # The view's region and the map's canvas are two landmarks with names of their own
    page.locator('canvas[role="region"]').wait_for(state="attached", timeout=WAIT)
    names = page.locator('.view-center, canvas[role="region"]').evaluate_all(
        "(nodes) => nodes.map((node) => node.getAttribute('aria-label'))"
    )
    assert len(names) == 2 and len(set(names)) == 2
