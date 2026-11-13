"""The view „PMAXTP” in the browser: a point from the map or typed, its tables and files."""

import csv
import io
import json
from typing import Any
from urllib.parse import parse_qs, urljoin, urlparse

import pytest
from playwright.sync_api import expect

from tests.e2e.conftest import PMAXTP_POINT, THEMES, WIDTHS

LAT, LON = PMAXTP_POINT
VIEW = "?view=pmaxtp"


def _answer(page, method="POT"):
    """The API's answer for the fixture point, as the page's server gives it."""
    response = page.request.get(
        urljoin(page.url, f"api/pmaxtp?latitude={LAT}&longitude={LON}&method={method}")
    )
    assert response.ok
    return response.json()


def _pmaxtp_requests(page):
    """Record every request of the page that concerns PMAXTP."""
    seen: list[str] = []
    page.on(
        "request",
        lambda request: "pmaxtp" in request.url.lower() and seen.append(request.url),
    )
    return seen


def _table(page: Any, answer: dict[str, Any]) -> None:
    """The quantiles of the answer are drawn: a row per duration, a column per probability."""
    rows = page.locator(".pm-table tbody tr")
    rows.first.wait_for(timeout=15_000)
    assert rows.count() == len(answer["durations"])
    assert page.locator(".pm-table thead th").count() == 1 + len(
        answer["probabilities"]
    )


def test_a_point_clicked_on_the_map_shows_its_tables_and_no_grid(open_page):
    page = open_page(VIEW)
    seen = _pmaxtp_requests(page)
    canvas = page.locator(".maplibregl-canvas")
    canvas.wait_for()
    box = canvas.bounding_box()
    page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    _table(page, _answer(page))
    # the clicked point fills the form
    assert page.locator(".pmaxtp-form input[name=latitude]").input_value()
    assert page.locator(".pmaxtp-form input[name=longitude]").input_value()
    # the map asks for nothing of PMAXTP but the picked point: no grid of any kind
    asked = [url for url in seen if "/api/pmaxtp?" in url]
    assert asked and len(asked) == len(seen), seen
    points = {
        (query["latitude"][0], query["longitude"][0])
        for query in (parse_qs(urlparse(url).query) for url in asked)
    }
    assert len(points) == 1


@pytest.mark.parametrize("theme", THEMES)
@pytest.mark.parametrize("lang", ["pl", "en"])
def test_typed_coordinates_show_the_tables_with_the_link_to_imgw(
    open_page, theme, lang
):
    page = open_page(VIEW, theme=theme, lang=lang)
    answer = _answer(page)
    comma = "," if lang == "pl" else "."
    page.locator(".pmaxtp-form input[name=latitude]").fill(
        f"{LAT:.2f}".replace(".", comma)
    )
    page.locator(".pmaxtp-form input[name=longitude]").fill(f"{LON:.2f}")
    page.locator(".pmaxtp-form button[type=submit]").click()
    _table(page, answer)
    link = page.locator(f'.pmaxtp-result a[href="{answer["source_url"]}"]')
    assert link.is_visible()
    assert link.get_attribute("target") == "_blank"
    # PMAXTP's lines are the view's strip: PS and PP on screen, every line behind it
    strip = page.locator(".view-foot nogat-sources")
    expect(strip.locator(".nogat-sources-strip")).to_contain_text(
        answer["attribution"][0]
    )
    assert strip.evaluate("(element) => element.attribution") == answer["attribution"]
    assert strip.evaluate("(element) => element.termsNotice") == answer["terms_notice"]


@pytest.mark.parametrize("width", WIDTHS)
def test_a_link_to_a_point_reopens_its_tables(open_page, width):
    page = open_page(f"{VIEW}&lat={LAT:.4f}&lon={LON:.4f}&method=AMP", width=width)
    answer = _answer(page, "AMP")
    _table(page, answer)
    assert page.locator(".pm-table").is_visible()


@pytest.mark.parametrize("latitude", ["60", "abc"])
def test_bad_coordinates_give_the_form_message_and_ask_nothing(open_page, latitude):
    page = open_page(VIEW)
    seen = _pmaxtp_requests(page)
    page.locator(".pmaxtp-form input[name=latitude]").fill(latitude)
    page.locator(".pmaxtp-form input[name=longitude]").fill("21")
    page.locator(".pmaxtp-form button[type=submit]").click()
    alert = page.locator(".pmaxtp-form [role=alert]")
    alert.wait_for()
    assert alert.inner_text().strip()
    assert page.locator(".pm-table").count() == 0
    assert not [url for url in seen if "/api/" in url]


def _download(page: Any, fmt: str) -> bytes:
    with page.expect_download() as event:
        page.locator(".pmaxtp-result .files a", has_text=fmt.upper()).click()
    path = event.value.path()
    with open(path, "rb") as handle:
        return handle.read()


def test_the_files_carry_the_tables_and_the_lines_of_pmaxtp(open_page):
    page = open_page(f"{VIEW}&lat={LAT:.4f}&lon={LON:.4f}")
    answer = _answer(page)
    _table(page, answer)
    lines = [*answer["attribution"], *answer["terms_notice"]]

    rows = list(csv.DictReader(io.StringIO(_download(page, "csv").decode("utf-8"))))
    assert len(rows) == 3 * len(answer["durations"])
    assert {row["table"] for row in rows} == {"ks", "sg", "rb"}
    cells = "\n".join(row["attribution"] + "\n" + row["terms_notice"] for row in rows)
    for line in lines:
        assert line in cells

    document = json.loads(_download(page, "json"))
    assert document["data"] == answer["data"]
    assert [*document["attribution"], *document["terms_notice"]] == lines
