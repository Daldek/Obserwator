"""
The providers' lines on screen (Nogat DEV-20.5, ECO-064): the kit's <nogat-sources> once
per view, across the page under the map and both panels, never in a panel or card; S, P,
PS, PP and the short ČHMÚ line on screen, every line and the terms behind „Źródła i
warunki”; the welcome window of a first visit with the same full content.
"""

from __future__ import annotations

from typing import Any

import pytest
from playwright.sync_api import expect

from tests.e2e.conftest import FIXTURE_STATIONS, WIDTHS

WAIT = 15_000
CK = "Źródło: ČHMÚ, CC BY 4.0"
"""The short form of ČHMÚ's line C, for the strip only."""


def _session(page: Any, base: str) -> dict[str, Any]:
    session: dict[str, Any] = page.request.get(f"{base}api/session").json()
    return session


@pytest.mark.parametrize("width", WIDTHS)
@pytest.mark.parametrize("kind", ["hydro", "hydro_chmi"])
def test_a_view_has_one_strip_with_the_lines_of_the_map_and_the_panel(
    open_page: Any, stored_url: str, width: int, kind: str
) -> None:
    code = FIXTURE_STATIONS[kind]
    page = open_page(f"?station={code}", base=stored_url, width=width, height=844)
    panel = page.locator("#panel-right")
    expect(panel.locator(".acc-item.open").first).to_be_visible(timeout=WAIT)
    station = page.request.get(f"{stored_url}api/stations/{code}").json()
    catalog = station["attribution_parts"]["catalog"]["attribution"]
    strip = page.locator("nogat-sources")
    expect(strip).to_have_count(1)
    expect(page.locator(".view-foot nogat-sources")).to_have_count(1)
    on_screen = strip.locator(".nogat-sources-strip")
    # the stations of both providers on the map: S, P and CK, once each
    expect(on_screen).to_contain_text(CK)
    expect(on_screen).not_to_contain_text("Český hydrometeorologický ústav")
    shown = strip.evaluate("(element) => element.attribution")
    assert set(catalog) <= set(shown)
    assert len(shown) == len(set(shown))
    if width >= 1440:
        # one IMGW-PIB family with ČHMÚ: at most two lines (DEV-20.5)
        box = on_screen.bounding_box()
        assert box is not None and box["height"] < 3 * 12 * 1.4
    else:
        # the station's sheet stops above the strip, which stays in sight; measured once
        # its 0.25 s slide-in has ended, or its box is still lower by the transform
        expect(panel).to_have_css("transform", "none")
        sheet = panel.bounding_box()
        foot = page.locator(".view-foot").bounding_box()
        assert sheet is not None and foot is not None
        assert sheet["y"] + sheet["height"] <= foot["y"] + 1
    # „Źródła i warunki” opens every line and the terms; Escape closes it
    strip.get_by_role("button", name="Źródła i warunki").click()
    dialog = strip.locator("dialog")
    expect(dialog).to_be_visible()
    for line in shown + strip.evaluate("(element) => element.termsNotice"):
        expect(dialog).to_contain_text(line)
    page.keyboard.press("Escape")
    expect(dialog).to_be_hidden()


def test_the_welcome_window_holds_every_line_once_on_the_first_visit(
    open_page: Any, public_url: str
) -> None:
    page = open_page(base=public_url, welcome=True)
    dialog = page.locator("dialog.welcome")
    expect(dialog).to_be_visible(timeout=WAIT)
    texts = _session(page, public_url)["attribution"]
    content = dialog.locator(".nogat-sources-content")
    for line in texts["order"] + texts["terms_order"]:
        expect(content).to_contain_text(line)
    dialog.get_by_role("button", name="Rozumiem").click()
    expect(dialog).to_be_hidden()
    page.reload()
    expect(page.get_by_role("radiogroup", name="Widok mapy")).to_be_visible()
    expect(page.locator("dialog.welcome")).to_be_hidden()


def test_the_welcome_window_links_the_terms_of_a_public_deployment_once(
    open_page: Any, public_url: str, gui_url: str
) -> None:
    page = open_page(base=public_url, welcome=True)
    dialog = page.locator("dialog.welcome")
    expect(dialog).to_be_visible(timeout=WAIT)
    # the kit's „Regulamin serwisu” is the window's one link to the terms, in a new tab
    expect(dialog.locator('a[href$="regulamin.html"]')).to_have_count(1)
    regulamin = dialog.get_by_role("link", name="Regulamin serwisu", exact=True)
    expect(regulamin).to_have_attribute("href", f"{public_url}regulamin.html")
    expect(regulamin).to_have_attribute("target", "_blank")
    expect(regulamin).to_have_attribute("rel", "noopener")
    # a deployment that is not public has none
    private = open_page(base=gui_url, welcome=True)
    welcome = private.locator("dialog.welcome")
    expect(welcome).to_be_visible(timeout=WAIT)
    expect(welcome.locator('a[href$="regulamin.html"]')).to_have_count(0)
