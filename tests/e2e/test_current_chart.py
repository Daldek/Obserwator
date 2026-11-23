"""
The chart of „teraz” in Chromium (O6): stored hours, the live tail, ranges, a phone.

``chart_url`` serves a copy of the fixture roots whose IMGW-PIB station has hydro.imgw.pl's
details (warning level 160 cm, alarm level 240 cm) and whose two hydrological stations
have hourly series from 35 days ago to yesterday (UTC): IMGW-PIB's telemetry before the
last 4 days and captured answers after, ČHMÚ's validated hours and ``recent`` likewise.
The live tails answer as the providers do (`tail_value` of the conftest). IMGW-PIB's
sources are private by default; a test sets hydro-back ``public`` in ``nogat.toml``.
"""

from __future__ import annotations

import shutil
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from playwright.sync_api import expect

from tests.e2e.conftest import FIXTURE_STATIONS, _read_only, _start, tail_value
from tests.unit.gui.hourly import CHMU, IMGW, add_details, plant_hours

HYDRO = FIXTURE_STATIONS["hydro"]
HYDRO_CHMU = FIXTURE_STATIONS["hydro_chmu"]
WAIT = 15_000
PUBLIC = '[obserwator.capture]\n"pl.imgw.hydro_operational" = "public"\n'


def _stored(higher: str, recent: date):
    """A stored hour: the tail's values, ``higher`` before ``recent``, captured after."""

    def pair(hour: datetime, variable: str):
        found = tail_value(hour, variable)
        tier = higher if hour.date() < recent else "operational"
        return (found, tier) if found is not None else (None, None)

    return pair


@pytest.fixture(scope="module")
def chart_url(fixture_raw_root, fixture_root, tmp_path_factory) -> Iterator[str]:
    """The GUI on the roots with the stations' hourly series up to yesterday."""
    base = tmp_path_factory.mktemp("gui-chart")
    raw, data = base / "raw", base / "data"
    shutil.copytree(fixture_raw_root, raw)
    shutil.copytree(fixture_root, data)
    add_details(raw, data, HYDRO)
    today = datetime.now(UTC).date()
    first, last = today - timedelta(days=35), today - timedelta(days=1)
    recent = today - timedelta(days=4)
    plant_hours(data, IMGW, HYDRO, first, last, _stored("telemetry", recent))
    plant_hours(data, CHMU, HYDRO_CHMU, first, last, _stored("verified", recent))
    _read_only(data)
    with _start(data, base / "work") as server:
        yield server.url
    _read_only(data, writable=True)


@pytest.fixture
def public(tmp_path, monkeypatch) -> None:
    """hydro-back ``public`` in the ``nogat.toml`` every request reads (P15)."""
    config = tmp_path / "nogat.toml"
    config.write_text(PUBLIC, encoding="utf-8")
    monkeypatch.setenv("NOGAT_CONFIG", str(config))


def _chart(page: Any) -> Any:
    card = page.locator('.acc-item[data-section="teraz"]')
    figure = card.locator(".now-figure")
    figure.locator("svg.chart-svg").wait_for(timeout=WAIT)
    return card, figure


@pytest.mark.parametrize("width", [1440, 390])
def test_an_imgw_station_draws_its_tiers_the_live_tail_and_its_levels(
    open_page: Any, chart_url: str, public: None, width: int, tmp_path: Path
) -> None:
    asked: list[str] = []
    page = open_page(f"?station={HYDRO}&section=teraz", base=chart_url, width=width)
    page.on("request", lambda request: asked.append(request.url))
    card, figure = _chart(page)

    legend = figure.locator(".chart-legend")
    for words in ("telemetria", "zapisane odpowiedzi", "pobrane teraz"):
        expect(legend).to_contain_text(words)
    marks = figure.locator("g.mark.hline")
    expect(marks).to_have_count(2)
    assert sorted(marks.all_text_contents()) == [
        "Stan alarmowy 240 cm",
        "Stan ostrzegawczy 160 cm",
    ]
    expect(figure.locator("figcaption")).to_contain_text(
        "Dane operacyjne, niezweryfikowane"
    )
    # The tiles of the current values stay above the chart
    expect(card.locator(".figures > div").first).to_be_visible()
    figure.scroll_into_view_if_needed()
    figure.screenshot(path=str(tmp_path / f"teraz-{width}.png"))
    assert figure.bounding_box()["width"] <= width
    if width == 390:
        assert page.evaluate("document.documentElement.scrollWidth") <= 390

    # Another range asks the route with its first day; T's daily readings are points
    with page.expect_request(lambda request: "/subdaily?from=" in request.url) as sent:
        card.get_by_role("radio", name="30 dni").click()
    first = (datetime.now(UTC).date() - timedelta(days=30)).isoformat()
    assert sent.value.url.endswith(f"from={first}")
    card.get_by_role("radio", name="T", exact=True).click()
    expect(figure.locator("g.emp circle").first).to_be_visible()
    expect(figure.locator("g.mark.hline")).to_have_count(0)


def test_a_private_source_draws_no_chart_and_asks_nothing(
    open_page: Any, chart_url: str
) -> None:
    asked: list[str] = []
    page = open_page(f"?station={HYDRO}", base=chart_url, ready=False)
    page.on("request", lambda request: asked.append(request.url))
    page.locator("#app > *").first.wait_for(state="attached", timeout=WAIT)
    card = page.locator('.acc-item[data-section="teraz"]')
    expect(card.locator(".figures > div").first).to_be_visible(timeout=WAIT)

    expect(card.locator(".now-figure")).to_have_count(0)
    assert not [url for url in asked if "/subdaily" in url]


def test_a_chmu_station_draws_its_stored_and_live_hours(
    open_page: Any, chart_url: str
) -> None:
    page = open_page(f"?station={HYDRO_CHMU}&section=teraz", base=chart_url, width=390)
    _, figure = _chart(page)

    legend = figure.locator(".chart-legend")
    for words in ("zapisane odpowiedzi", "pobrane teraz"):
        expect(legend).to_contain_text(words)
    expect(figure.locator("g.mark.hline")).to_have_count(0)
