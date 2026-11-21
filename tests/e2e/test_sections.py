"""
The parts of the analysis sections on the stored results of the fixture root (GUI plan D11).

A part that shows several results says when one of them failed, beside the others it
still shows, and it names the series version by its label, as „Dane” does.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tests.e2e.conftest import FIXTURE_STATIONS

expect = pytest.importorskip("playwright.sync_api").expect

HYDRO = FIXTURE_STATIONS["hydro"]
WAIT = 20_000
"""How long a section may take to load [ms]."""
FAILED = "Hydrolog: za mało dni z wartością w wybranym miesiącu"
"""Hydrolog's error of a result computed on request, as the part shows it."""


def test_a_part_names_the_failure_of_one_of_its_results(
    open_page: Any, stored_url: str
) -> None:
    page = open_page(f"?station={HYDRO}&section=duration", base=stored_url)
    card = page.locator('.acc-item[data-section="duration"]')
    # The part's own section: the parent of the header holding its title
    title = card.locator(
        "header.ana-head h3", has_text="Stany wody: strefy Rybczyńskiego"
    )
    levels = title.locator("xpath=../..")
    figures = levels.locator(".figures")
    expect(figures).to_contain_text("NTW", timeout=WAIT)
    expect(levels.locator(".ana-error")).to_have_count(0)
    session = page.request.get(f"{stored_url}api/session").json()
    label = session["root"]["series"]["pl.imgw.hydro_daily"]["version"]
    expect(levels.locator(".ana-prov .prov").filter(has_text="szereg")).to_have_text(
        [f"szereg {label}"]
    )

    # May: Hydrolog fails the duration curves computed on request (its error document),
    # Rybczyński's zones stay stored
    def failed(route: Any) -> None:
        stored = page.request.get(route.request.url.split("?")[0]).json()
        route.fulfill(
            json={
                **stored,
                "status": "failed",
                "envelope": None,
                "error": {"schema": "hydrolog-error/1", "message": FAILED},
                "stored": False,
                "source": "computed",
            }
        )

    page.route("**/api/analysis/*/duration_curve.*?month=5", failed)
    card.get_by_role("combobox", name="Miesiąc").select_option("5")
    expect(levels.locator(".ana-error")).to_have_text(FAILED, timeout=WAIT)
    expect(figures).to_contain_text("NTW")


LOW_FLOW = json.loads(
    (
        Path(__file__).parents[1]
        / "fixtures"
        / "hydrolog"
        / "low_flow_negative_quantiles.json"
    ).read_text(encoding="utf-8")
)
"""Hydrolog's own answers of `stats low-flow` with null quantiles and with an error."""


def _low_flow_part(open_page: Any, base: str, answer: dict[str, Any]) -> Any:
    """The part „Przepływy minimalne” of the station's card, its result ``answer``."""
    page = open_page(f"?station={HYDRO}", base=base)

    def fulfill(route: Any) -> None:
        stored = page.request.get(route.request.url.split("?")[0]).json()
        route.fulfill(json={**stored, **answer})

    page.route(f"**/api/analysis/{HYDRO}/low_flow.Q*", fulfill)
    card = page.locator('.acc-item[data-section="extremes"]')
    card.locator(".acc-head button").click()
    title = card.locator("header.ana-head h3", has_text="Przepływy minimalne")
    return title.locator("xpath=../..")


def test_low_flow_quantiles_below_zero_flow_show_as_missing(
    open_page: Any, stored_url: str
) -> None:
    # Hydrolog with hotfix/ml-fits: a discharge quantile below 0 m³/s is null, with
    # the notice negative_quantiles; here from T = 10 years (0 m³/s at T = 9.3)
    part = _low_flow_part(
        open_page,
        stored_url,
        {"status": "ok", "envelope": LOW_FLOW["ok"], "error": None},
    )
    ten = part.locator(".figures div", has_text="NQ 10-letni")
    expect(ten.locator("dd").first).to_have_text("–", timeout=WAIT)
    expect(ten.locator("small")).to_have_text("F = 10 %: poniżej 0 m³/s")
    rows = part.locator("table tbody tr")
    expect(rows.nth(0)).to_contain_text("0,076")  # T = 2
    expect(rows.nth(1)).to_contain_text("0,037")  # T = 5
    for row in range(2, rows.count()):  # T = 10 … 1000
        expect(rows.nth(row).locator("td").last).to_have_text("–")
    expect(part.locator(".hy-caption").first).to_contain_text("T = 9,3 [lata]")
    expect(part.locator(".ana-notices")).to_contain_text(
        "Dopasowany rozkład Fishera–Tippetta sięga poniżej przepływu zerowego"
    )
    text = part.inner_text()
    assert "NaN" not in text and "null" not in text

    # A fit that fails (minima all equal) is the part's error, without its body
    part = _low_flow_part(
        open_page,
        stored_url,
        {"status": "failed", "envelope": None, "error": LOW_FLOW["error"]},
    )
    expect(part.locator(".ana-error")).to_have_text(
        LOW_FLOW["error"]["message"], timeout=WAIT
    )
    expect(part.locator(".figures")).to_have_count(0)
