"""The view „PMAXTP” in the browser: a point from the map or typed, its tables and files."""

import contextlib
import csv
import io
import json
from typing import Any
from urllib.parse import parse_qs, urljoin, urlparse

import pytest
from playwright.sync_api import TimeoutError as PlaywrightTimeout
from playwright.sync_api import expect

from obserwator.messages import message
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
    # the map takes clicks once it has loaded: its layers are added and its click
    # handlers bound in one go (map.js, „load”); a click on the bare canvas is lost
    page.wait_for_function(
        "() => { const element = document.querySelector('.map');"
        " return Boolean(element && element.maplibre"
        " && element.maplibre.getLayer('pmaxtp-dot')); }",
        timeout=15_000,
    )
    canvas = page.locator(".maplibregl-canvas")
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
    # without a basemap the map draws the packaged borders, whose lines (GUGiK's PRG,
    # ČÚZK's RÚIAN; attribution.js BORDER_SOURCES) join the strip after PMAXTP's
    session = page.request.get(urljoin(page.url, "api/session")).json()
    origins = session["attribution"]["origins"]
    borders = [
        line
        for name in ("gugik", "cuzk")
        for line in origins[name]["attribution"]
        if line not in answer["attribution"]
    ]
    assert borders
    # the borders join once the map has its background, which may be after the tables
    expected = answer["attribution"] + borders
    with contextlib.suppress(PlaywrightTimeout):
        page.wait_for_function(
            "(want) => JSON.stringify(document.querySelector("
            "'.view-foot nogat-sources')?.attribution) === JSON.stringify(want)",
            arg=expected,
            timeout=15_000,
        )
    assert strip.evaluate("(element) => element.attribution") == expected
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
    link = page.locator(".pmaxtp-result .files a", has_text=fmt.upper())
    with page.expect_download() as event:
        link.click()
    # The page's name and the server's are one (Nogat DEV-19.21).
    name = f"obserwator_pmaxtp_POT_{LAT:.4f}_{LON:.4f}.{fmt}"
    assert link.get_attribute("download") == name
    assert event.value.suggested_filename == name
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


def _intensity(page: Any) -> Any:
    """The chart of the rainfall intensity curves, once drawn."""
    chart = page.locator(".pmaxtp-result .pm-chart")
    chart.locator("svg path.ser").first.wait_for(state="attached", timeout=15_000)
    return chart


def _readout(page: Any, chart: Any, key: str) -> str:
    """The chart's readout after a key on its plot, as a screen reader hears it."""
    chart.locator("svg").focus()
    page.keyboard.press(key)
    return str(chart.locator(".chart-sr").text_content())


def test_the_intensity_curves_give_q_of_the_recorded_quantiles(open_page):
    page = open_page(f"{VIEW}&lat={LAT:.4f}&lon={LON:.4f}", lang="en")
    answer = _answer(page)
    _table(page, answer)
    chart = _intensity(page)
    # one curve per probability of the answer, named by its p in the legend
    probabilities = answer["probabilities"]
    assert chart.locator("path.ser").count() == len(probabilities)
    assert chart.locator(".chart-legend span").all_text_contents() == [
        f"p = {p} %" for p in probabilities
    ]
    # q = 166.7 · h / t of the quantile h of the first duration t and probability p
    duration, p = answer["durations"][0], probabilities[0]
    q = 166.7 * answer["data"]["ks"][duration][p] / float(duration)
    text = _readout(page, chart, "Home")
    assert f"t = {duration} min" in text
    assert f"p = {p} %: {q:.1f}\u00a0dm³/(s·ha)" in text, text
    # the curves are processed data: the view's strip carries PMAXTP's line PP
    processed = str(message("legal.pmaxtp_processed_attribution"))
    assert processed in answer["attribution"]
    page.wait_for_function(
        "(line) => (document.querySelector('.view-foot nogat-sources')?.attribution"
        " || []).includes(line)",
        arg=processed,
        timeout=15_000,
    )


# The durations [min] and probabilities [%] of a full answer of IMGW-PIB (models.py)
_DURATIONS = [
    5,
    10,
    15,
    30,
    45,
    60,
    90,
    120,
    180,
    360,
    720,
    1080,
    1440,
    2160,
    2880,
    4320,
]
_PROBABILITIES = [
    "0.01",
    "0.02",
    "0.03",
    "0.05",
    "0.1",
    "0.2",
    "0.3",
    "0.5",
    "1",
    "2",
    "3",
    "5",
    "10",
    "20",
    "30",
    "40",
    "50",
    "60",
    "70",
    "80",
    "90",
    "95",
    "98",
    "98.5",
    "99",
    "99.5",
    "99.9",
]


def test_a_full_answer_draws_a_curve_per_probability_over_every_duration(open_page):
    page = open_page(VIEW, lang="en")
    answer = _answer(page)
    # a full table of quantiles growing with t and falling with p, in place of the
    # recording's one cell
    ks = {
        str(t): {
            p: round(10 * t**0.3 * (1 + 2 / float(p) ** 0.25), 2)
            for p in _PROBABILITIES
        }
        for t in _DURATIONS
    }
    full = {
        **answer,
        "durations": [str(t) for t in _DURATIONS],
        "probabilities": _PROBABILITIES,
        "data": {"ks": ks, "sg": ks, "rb": ks},
    }
    page.route(
        "**/api/pmaxtp?*",
        lambda route: route.fulfill(
            status=200, content_type="application/json", body=json.dumps(full)
        ),
    )
    page.goto(f"{page.url.split('?')[0]}{VIEW}&lat={LAT:.4f}&lon={LON:.4f}")
    chart = _intensity(page)
    curves = chart.locator("path.ser")
    assert curves.count() == len(_PROBABILITIES)
    # every curve runs over the 16 durations: one move and 15 segments
    for d in curves.evaluate_all("(paths) => paths.map((p) => p.getAttribute('d'))"):
        assert d.count("M") == 1 and d.count("L") == len(_DURATIONS) - 1, d
    # the rarest and the most frequent p are told apart by colour
    strokes = curves.evaluate_all(
        "(paths) => paths.map((p) => getComputedStyle(p).stroke)"
    )
    assert strokes[0] != strokes[-1]
    # the last duration, 72 h, read on the curve of the rarest p
    q = 166.7 * ks["4320"]["0.01"] / 4320
    text = _readout(page, chart, "End")
    assert "t = 4,320 min" in text
    assert f"p = 0.01 %: {q:.1f}\u00a0dm³/(s·ha)" in text, text
