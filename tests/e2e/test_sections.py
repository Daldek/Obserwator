"""
The parts of the analysis sections on the stored results of the fixture root (GUI plan D11).

A part that shows several results says when one of them failed, beside the others it
still shows, and it names the series version by its label, as „Dane” does.
"""

from __future__ import annotations

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
