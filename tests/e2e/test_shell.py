"""The page's shell in the browser: themes, the phone, Nogat's shell, language, terms, panels, „Zgłoś uwagę”."""

from typing import Any

import pytest

from tests.e2e.conftest import FIXTURE_STATIONS, THEMES, WIDTHS

expect = pytest.importorskip("playwright.sync_api").expect

STATION = FIXTURE_STATIONS["hydro"]
# Recorded from the page's first script on: the embedding flag at the first frame (the
# first paint follows it) and the display of each top bar the moment it is added
_FIRST_PAINT = """
window.__firstFrame = null;
window.__topBars = [];
const seen = new WeakSet();
requestAnimationFrame(() => {
  window.__firstFrame = document.documentElement.dataset.host || "";
});
new MutationObserver(() => {
  for (const bar of document.querySelectorAll(".topbar")) {
    if (seen.has(bar)) continue;
    seen.add(bar);
    window.__topBars.push(getComputedStyle(bar).display);
  }
}).observe(document, { childList: true, subtree: true });
"""


def _width(page: Any, selector: str) -> int:
    box = page.locator(selector).bounding_box()
    assert box is not None
    return int(round(box["width"]))


@pytest.mark.parametrize("theme", THEMES)
@pytest.mark.parametrize("width", WIDTHS)
def test_the_page_loads_in_each_theme_on_a_desktop_and_a_phone(open_page, theme, width):
    page = open_page(f"?station={STATION}", theme=theme, width=width)
    page.wait_for_load_state("networkidle")
    expect(page.locator("html")).to_have_attribute("data-theme", theme)
    expect(page.locator(".topbar")).to_be_visible()
    expect(page.get_by_role("radiogroup", name="Widok mapy")).to_be_visible()
    # nothing sticks out sideways, the top bar's actions included
    assert page.evaluate("document.documentElement.scrollWidth") <= width


def test_inside_nogat_the_top_bar_is_hidden_from_the_first_paint(open_page):
    page = open_page("?nogat=1")
    page.add_init_script(_FIRST_PAINT)
    page.reload()
    page.locator("#app > *").first.wait_for(state="attached")
    assert page.evaluate("window.__firstFrame") == "nogat"
    assert set(page.evaluate("window.__topBars")) == {"none"}
    expect(page.locator(".topbar")).to_be_hidden()
    # the view takes the whole height: its bar is the first thing on the page
    bar = page.locator(".map-bar").bounding_box()
    assert bar is not None and bar["y"] == 0


def test_the_language_switch_changes_the_texts_and_is_remembered(open_page):
    page = open_page(lang="pl")
    expect(
        page.get_by_role("radiogroup", name="Widok mapy").get_by_role(
            "radio", name="Pomiary bieżące"
        )
    ).to_be_visible()
    page.get_by_role("button", name="EN", exact=True).click()
    views = page.get_by_role("radiogroup", name="Map view")
    expect(views.get_by_role("radio", name="Current measurements")).to_be_visible()
    expect(page.locator("html")).to_have_attribute("lang", "en")
    page.reload()
    expect(
        page.get_by_role("radiogroup", name="Map view").get_by_role(
            "radio", name="Current measurements"
        )
    ).to_be_visible()
    expect(page.get_by_role("button", name="EN", exact=True)).to_have_attribute(
        "aria-pressed", "true"
    )


def test_the_theme_switch_is_remembered(open_page):
    page = open_page(theme="light")
    page.get_by_role("button", name="Ciemny").click()
    expect(page.locator("html")).to_have_attribute("data-theme", "dark")
    page.reload()
    expect(page.locator("html")).to_have_attribute("data-theme", "dark")
    expect(page.get_by_role("button", name="Ciemny")).to_have_attribute(
        "aria-pressed", "true"
    )
    # „Auto” follows the system: no theme of the page's own, also after a reload
    page.get_by_role("button", name="Auto").click()
    page.reload()
    page.locator("#app > *").first.wait_for(state="attached")
    assert page.evaluate("document.documentElement.dataset.theme") is None
    expect(page.get_by_role("button", name="Auto")).to_have_attribute(
        "aria-pressed", "true"
    )


@pytest.mark.parametrize("view", ["", "?view=current", "?view=pmaxtp"])
def test_a_public_deployment_links_its_terms_at_the_bottom_of_the_left_panel(
    open_page, public_url, gui_url, view
):
    page = open_page(view, base=public_url)
    rail = page.locator("#panel-left .panel-foot")
    terms = rail.get_by_role("link", name="Regulamin")
    expect(terms).to_be_visible()
    expect(terms).to_have_attribute("href", "regulamin.html")
    expect(terms).to_have_attribute("target", "_blank")
    expect(terms).to_have_attribute("rel", "noopener")
    # the panel's last item; the view's foot holds only the providers' strip. Measured
    # once the layout settles (the filter's rows and the sheet's slide change the panel).
    gap = None
    for _ in range(50):
        box, panel = rail.bounding_box(), page.locator("#panel-left").bounding_box()
        assert box is not None and panel is not None
        gap = abs(box["y"] + box["height"] - (panel["y"] + panel["height"]))
        if gap <= 1:
            break
        page.wait_for_timeout(100)
    assert gap is not None and gap <= 1
    foot = page.locator(".view-foot")
    expect(foot.get_by_role("link", name="Regulamin", exact=True)).to_have_count(0)
    expect(foot).not_to_contain_text("niekomercyjny")
    # on a phone it ends the left sheet
    phone = open_page(view, base=public_url, width=390)
    phone.locator(".panel-toggle.left").click()
    expect(
        phone.locator("#panel-left .panel-foot").get_by_role("link", name="Regulamin")
    ).to_be_visible()
    # a deployment that is not public has no link
    private = open_page(view, base=gui_url)
    expect(private.get_by_role("radiogroup", name="Widok mapy")).to_be_visible()
    expect(private.locator("#panel-left .panel-foot")).to_have_count(0)


def test_feedback_sends_a_report_of_the_view_shown(open_page, public_url):
    page = open_page(f"?station={STATION}&section=dane", base=public_url)
    page.get_by_role("button", name="Zgłoś uwagę").click()
    dialog = page.get_by_role("dialog", name="Zgłoś uwagę")
    expect(dialog).to_be_visible()
    # the note names the operator's address; the context shows the station it sends
    expect(dialog.get_by_role("link", name="operator@example.org")).to_have_attribute(
        "href", "mailto:operator@example.org"
    )
    expect(dialog.locator(".fb-context")).to_contain_text(STATION)
    field = dialog.get_by_label("Opis problemu lub sugestii")
    expect(field).to_be_focused()
    # an empty description is not sent
    dialog.get_by_role("button", name="Wyślij").click()
    expect(dialog.get_by_role("alert")).to_be_visible()
    field.fill("Wykres przepływów nie mieści się na telefonie.")
    with page.expect_request("**/api/feedback") as sent:
        dialog.get_by_role("button", name="Wyślij").click()
    assert sent.value.post_data_json == {
        "message": "Wykres przepływów nie mieści się na telefonie.",
        "context": {
            "view": "stations",
            "station": STATION,
            "parameters": {"station": STATION, "section": "dane"},
        },
    }
    expect(dialog).to_be_hidden()
    expect(page.locator(".toast")).to_contain_text("Dziękujemy!")


def test_feedback_shows_the_servers_refusal_and_keeps_the_text(browser, gui_url):
    # A refused request is a console error of Chromium's own: this page is checked for
    # errors of its scripts only
    context = browser.new_context(viewport={"width": 1440, "height": 900})
    # the welcome window of a first visit counts as seen
    context.add_init_script("localStorage.setItem('obserwator-welcome', '1');")
    errors: list[str] = []
    try:
        page = context.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(gui_url)
        page.get_by_role("button", name="Zgłoś uwagę").click()
        dialog = page.get_by_role("dialog", name="Zgłoś uwagę")
        # without the operator's e-mail the note is its first sentence only
        expect(dialog.locator("#fb-note")).to_have_text("Nie wpisuj danych osobowych.")
        field = dialog.get_by_label("Opis problemu lub sugestii")
        text = "Jeszcze jedna uwaga."
        # one address may send only a few reports at a time
        for _ in range(10):
            if not dialog.is_visible():
                page.get_by_role("button", name="Zgłoś uwagę").click()
            field.fill(text)
            with page.expect_response("**/api/feedback") as answer:
                dialog.get_by_role("button", name="Wyślij").click()
            if answer.value.status != 200:
                break
            expect(dialog).to_be_hidden()
        assert answer.value.status == 429
        expect(dialog.get_by_role("alert")).to_have_text(answer.value.json()["message"])
        expect(field).to_have_value(text)
    finally:
        context.close()
    assert errors == []


def test_a_side_panel_resizes_by_keys_and_keeps_its_width(open_page):
    page = open_page()
    resizer = page.get_by_role("separator", name="Szerokość panelu „Stacje”")
    assert _width(page, "#panel-left") == 300
    resizer.focus()
    page.keyboard.press("ArrowRight")
    expect(resizer).to_have_attribute("aria-valuenow", "316")
    page.keyboard.press("Shift+ArrowRight")
    expect(resizer).to_have_attribute("aria-valuenow", "380")
    assert _width(page, "#panel-left") == 380
    page.keyboard.press("Home")
    expect(resizer).to_have_attribute("aria-valuenow", "260")
    page.keyboard.press("End")
    expect(resizer).to_have_attribute("aria-valuenow", "560")
    page.reload()
    expect(resizer).to_have_attribute("aria-valuenow", "560")
    assert _width(page, "#panel-left") == 560
    resizer.focus()
    page.keyboard.press("Enter")
    expect(resizer).to_have_attribute("aria-valuenow", "300")


def test_on_a_phone_the_panels_are_bottom_sheets(open_page):
    page = open_page(width=390, height=844)
    sheet = page.locator("#panel-left")
    expect(sheet).to_be_hidden()
    expect(page.locator(".resizer")).to_have_count(0)
    page.locator(".map-bar").get_by_role("button", name="Stacje", exact=True).click()
    expect(sheet).to_be_visible()
    expect(sheet).to_have_css("transform", "none")
    box = sheet.bounding_box()
    # the sheet stops above the view's foot, the strip of provider lines
    foot = page.locator(".view-foot").bounding_box()
    assert box is not None and foot is not None
    assert round(box["width"]) == 390
    assert round(box["y"] + box["height"]) == round(foot["y"])
    assert round(foot["y"] + foot["height"]) == 844
    page.keyboard.press("Escape")
    expect(sheet).to_be_hidden()
