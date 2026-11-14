"""The admin panel in Chromium (Nogat DEV-15.13): the kit's shell on the GUI's own server."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from playwright.sync_api import expect

from tests.e2e.conftest import ADMIN_KEY


def _report(number: int, *, read: bool) -> str:
    document = {
        "id": number,
        "created_at": f"2026-11-1{number}T08:00:00+00:00",
        "message": f"Zgłoszenie testowe {number}",
        "context": {
            "view": "stations",
            "station": None,
            "parameters": {"q": "Wisła"},
            "app_version": "3.0.0",
        },
        "is_read": read,
    }
    return json.dumps(document, ensure_ascii=False, separators=(",", ":"))


def test_the_operator_signs_in_handles_reports_and_reads_stats_and_status(
    admin_site, open_page
):
    url, directory = admin_site
    feedback = directory / "feedback.jsonl"
    feedback.write_text(
        "".join(f"{_report(n, read=n == 1)}\n" for n in (1, 2, 3)), encoding="utf-8"
    )
    yesterday = (datetime.now(UTC).date() - timedelta(days=1)).isoformat()
    day = {
        "date": yesterday,
        "visitors": 4,
        "page_views": 9,
        "stations_opened": 2,
        "analyses_run": 1,
        "downloads": 3,
    }
    (directory / "stats.jsonl").write_text(json.dumps(day) + "\n", encoding="utf-8")

    page = open_page("admin", base=url, ready=False)

    expect(page).to_have_url(f"{url}admin/")
    expect(page.get_by_role("heading", level=1)).to_have_text(
        "Obserwator · Administracja"
    )
    page.get_by_label("Klucz administratora").fill(ADMIN_KEY)
    page.get_by_role("button", name="Zaloguj", exact=True).click()

    # „Zgłoszenia”: the reports of feedback.jsonl, marked and deleted in the file
    reports = page.locator(".nogat-admin-report")
    count = page.locator(".nogat-admin-count")
    expect(reports).to_have_count(3)
    expect(count).to_have_text("Nieprzeczytane: 2 z 3")
    assert (
        page.evaluate("sessionStorage.getItem('obserwator/admin-key/1')") == ADMIN_KEY
    )
    newest = page.locator('.nogat-admin-report[data-id="3"]')
    expect(newest.locator(".nogat-admin-message")).to_have_text("Zgłoszenie testowe 3")
    newest.get_by_role("button", name="Oznacz jako przeczytane").click()
    expect(count).to_have_text("Nieprzeczytane: 1 z 3")
    page.locator('.nogat-admin-report[data-id="2"]').get_by_role(
        "button", name="Usuń"
    ).click()
    question = page.get_by_role("dialog", name="Usunąć zgłoszenie #2?")
    question.get_by_role("button", name="Usuń").click()
    expect(reports).to_have_count(2)
    expect(count).to_have_text("Nieprzeczytane: 0 z 2")
    stored = [json.loads(text) for text in feedback.read_text("utf-8").splitlines()]
    assert [(report["id"], report["is_read"]) for report in stored] == [
        (1, True),
        (3, True),
    ]

    # „Statystyki”: yesterday's line and today as counted so far (the panel is not)
    sections = page.get_by_role("navigation", name="Sekcje panelu")
    sections.get_by_role("link", name="Statystyki").click()
    rows = page.locator(".nogat-admin-table tbody tr")
    expect(rows).to_have_count(2)
    assert rows.first.locator("th").inner_text() == yesterday
    totals = page.locator(".nogat-admin-table tfoot td").all_inner_texts()
    assert totals[0].startswith("4")
    assert totals[1:] == ["9", "2", "1", "3"]

    # „Stan”: the app, its directory and its checks in words
    sections.get_by_role("link", name="Stan").click()
    checks = page.locator(".nogat-admin-check")
    expect(checks).to_have_count(3)
    assert checks.locator(".nogat-admin-check-name").all_inner_texts() == [
        "data_root_marker",
        "stored_analyses",
        "hydrolog_command",
    ]
    assert checks.locator(".nogat-admin-badge").all_inner_texts() == [
        "OK",
        "Ostrzeżenie",
        "Ostrzeżenie",
    ]
    facts = page.locator(".nogat-admin-facts dd").all_inner_texts()
    assert facts[0] == "Obserwator"
    assert facts[4] == str(directory)

    page.get_by_role("button", name="Wyloguj").click()
    expect(page.get_by_label("Klucz administratora")).to_be_visible()
    assert page.evaluate("sessionStorage.length") == 0
