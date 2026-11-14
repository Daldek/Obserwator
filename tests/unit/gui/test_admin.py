"""The GUI's admin panel (Nogat DEV-15.13, ADR-020): the page, the key and the core API."""

from __future__ import annotations

import json
import os
import re
import shutil
import stat
import sys
import threading
from datetime import UTC, datetime
from pathlib import Path

import pytest
from starlette.applications import Starlette
from starlette.routing import Mount
from starlette.testclient import TestClient

import obserwator
from obserwator.gui._admin import CHECKS, _analyses_check
from obserwator.gui._config import Basemap
from obserwator.gui._feedback import Feedback
from obserwator.gui._root import Snapshot, Version
from obserwator.messages import message
from tests.unit.gui.conftest import HYDROLOG_VERSION, gui_config

KEY = "klucz-0123456789"
ADMIN = {"X-Admin-Key": KEY}
JSON = {"Content-Type": "application/json"}
NOON = datetime(2026, 11, 13, 12, 0, tzinfo=UTC).timestamp()
CONTEXT: dict[str, object] = {
    "view": "stations",
    "station": None,
    "parameters": {},
    "app_version": "3.0.0",
}
ADMIN_CSP = {
    "default-src": ["'self'"],
    "script-src": ["'self'"],
    "style-src": ["'self'"],
    "img-src": ["'self'"],
    "connect-src": ["'self'"],
    "font-src": ["'self'"],
    "object-src": ["'none'"],
    "base-uri": ["'none'"],
    "form-action": ["'self'"],
    "frame-ancestors": ["'none'"],
}
ROUTES = [
    ("GET", "/api/admin/feedback"),
    ("PATCH", "/api/admin/feedback/1"),
    ("DELETE", "/api/admin/feedback/1"),
    ("GET", "/api/admin/stats"),
    ("GET", "/api/admin/status"),
    ("GET", "/api/admin/nothing"),
    ("GET", "/api/admin"),
]


@pytest.fixture(autouse=True)
def no_key(monkeypatch):
    """No admin key of the machine: a test sets its own."""
    monkeypatch.delenv("OBSERWATOR_ADMIN_API_KEY", raising=False)
    monkeypatch.delenv("OBSERWATOR_ADMIN_API_KEY_FILE", raising=False)


@pytest.fixture
def key(monkeypatch):
    monkeypatch.setenv("OBSERWATOR_ADMIN_API_KEY", KEY)
    return KEY


@pytest.fixture
def state_dir(tmp_path):
    """The GUI's own directory, apart from the data root."""
    return tmp_path / "state"


@pytest.fixture
def admin(make_client, key, state_dir):
    """A client of the GUI on the read-only root, its own directory ``state_dir``."""
    return make_client(gui_dir=state_dir)


def line(report: int, *, read: bool = False) -> str:
    """A stored report as ``POST api/feedback`` writes it."""
    document = {
        "id": report,
        "created_at": f"2026-11-{report % 28 + 1:02d}T10:00:00+00:00",
        "message": f"Zgłoszenie {report}",
        "context": CONTEXT,
        "is_read": read,
    }
    return json.dumps(document, ensure_ascii=False, separators=(",", ":"))


def seed(directory: Path, *lines: str) -> Path:
    path = directory / "feedback.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(f"{text}\n" for text in lines), encoding="utf-8")
    return path


def refused(answer, reason, lang="pl"):
    """A ``401`` of the admin API: the error document of ``unauthorized``, never kept."""
    assert answer.status_code == 401, answer.text
    assert answer.headers["cache-control"] == "no-store"
    body = answer.json()
    assert body["schema"] == "obserwator-error/1"
    assert body["code"] == "unauthorized"
    assert body["title"] == message("gui.errors.title_unauthorized", lang=lang)
    assert body["details"] == {"reason": reason}
    assert body["exit_code"] is None


def problem(answer, status, code, option=None):
    assert answer.status_code == status, answer.text
    assert answer.headers["cache-control"] == "no-store"
    body = answer.json()
    assert body["code"] == code
    if option is not None:
        assert body["details"]["option"] == option
    return body


def csp(answer) -> dict[str, list[str]]:
    policy = answer.headers["content-security-policy"]
    return {part.split()[0]: part.split()[1:] for part in policy.split("; ")}


def files_of(root: Path) -> dict[str, bytes]:
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


# --- the key -----------------------------------------------------------------------------


@pytest.mark.parametrize(("method", "path"), ROUTES)
def test_every_admin_route_refuses_a_missing_wrong_or_unconfigured_key(
    make_client, monkeypatch, state_dir, method, path
):
    stored = seed(state_dir, line(1), line(2))
    before = stored.read_bytes()
    client = make_client(gui_dir=state_dir)
    body = {"json": {"is_read": True}} if method == "PATCH" else {}

    def ask(headers=None):
        return client.request(method, path, headers=headers, **body)

    refused(ask(ADMIN), "admin_key_not_configured")
    monkeypatch.setenv("OBSERWATOR_ADMIN_API_KEY", KEY)
    refused(ask(), "admin_key_missing")
    refused(ask({"X-Admin-Key": ""}), "admin_key_missing")
    for wrong in (KEY.upper(), KEY[:-1], f"{KEY}0", "żółw"):
        # the bytes a client sends: Starlette reads a header as Latin-1
        refused(ask({"X-Admin-Key": wrong.encode()}), "admin_key_invalid")
    refused(
        ask({"X-Admin-Key": "x", "Accept-Language": "en"}), "admin_key_invalid", "en"
    )
    assert ask(ADMIN).status_code != 401
    if method == "GET":
        assert stored.read_bytes() == before


def test_the_key_and_its_file_are_read_on_every_request(
    make_client, monkeypatch, tmp_path, state_dir
):
    path = tmp_path / "admin.key"
    path.write_text("first-key\n", encoding="utf-8")
    monkeypatch.setenv("OBSERWATOR_ADMIN_API_KEY_FILE", str(path))
    client = make_client(gui_dir=state_dir)

    def ask(given: str):
        return client.get("/api/admin/feedback", headers={"X-Admin-Key": given})

    assert ask("first-key").status_code == 200
    path.write_text("second-key", encoding="utf-8")
    refused(ask("first-key"), "admin_key_invalid")
    assert ask("second-key").status_code == 200
    monkeypatch.setenv("OBSERWATOR_ADMIN_API_KEY", "from-the-environment")
    refused(ask("second-key"), "admin_key_invalid")
    assert ask("from-the-environment").status_code == 200
    monkeypatch.delenv("OBSERWATOR_ADMIN_API_KEY")
    path.write_text(" \n", encoding="utf-8")
    refused(ask("second-key"), "admin_key_not_configured")
    path.unlink()
    refused(ask("second-key"), "admin_key_not_configured")


# --- reports -----------------------------------------------------------------------------


def test_reports_are_listed_newest_first_with_their_counts(admin, state_dir):
    seed(
        state_dir,
        line(1, read=True),
        line(2),
        "not json",
        '{"message": "a line without an id"}',
        line(3),
        line(4, read=True),
        line(5),
    )

    every = admin.get("/api/admin/feedback", headers=ADMIN)
    page = admin.get("/api/admin/feedback?limit=2&offset=1", headers=ADMIN)
    beyond = admin.get("/api/admin/feedback?offset=5", headers=ADMIN)

    assert every.status_code == 200
    assert every.headers["cache-control"] == "no-store"
    assert every.json()["items"] == [
        json.loads(line(number, read=number in (1, 4))) for number in (5, 4, 3, 2, 1)
    ]
    assert page.json() == {
        "items": [json.loads(line(4, read=True)), json.loads(line(3))],
        "total": 5,
        "unread_count": 3,
    }
    assert beyond.json() == {"items": [], "total": 5, "unread_count": 3}


def test_a_page_holds_50_reports_by_default_and_200_at_most(admin, state_dir):
    seed(state_dir, *(line(number) for number in range(1, 252)))

    default = admin.get("/api/admin/feedback", headers=ADMIN).json()
    largest = admin.get("/api/admin/feedback?limit=200", headers=ADMIN).json()

    assert [item["id"] for item in default["items"]] == list(range(251, 201, -1))
    assert [item["id"] for item in largest["items"]] == list(range(251, 51, -1))
    assert default["total"] == largest["total"] == 251


@pytest.mark.parametrize(
    ("query", "option"),
    [
        ("limit=0", "limit"),
        ("limit=201", "limit"),
        ("limit=ten", "limit"),
        ("offset=-1", "offset"),
        ("limit=5&limit=6", "limit"),
        ("page=2", "page"),
    ],
)
def test_a_page_of_reports_is_checked(admin, query, option):
    answer = admin.get(f"/api/admin/feedback?{query}", headers=ADMIN)

    problem(answer, 400, "validation_error", option)


def test_marking_a_report_rewrites_its_line_alone(admin, state_dir):
    by_hand = '{"id": 3, "message": "written by hand", "is_read": false}'
    path = seed(state_dir, line(1), line(2), "not json", by_hand)
    before = path.read_text(encoding="utf-8").splitlines()

    read = admin.patch("/api/admin/feedback/2", json={"is_read": True}, headers=ADMIN)
    after = path.read_text(encoding="utf-8").splitlines()
    by_hand_read = admin.patch(
        "/api/admin/feedback/3", json={"is_read": True}, headers=ADMIN
    )
    inode = path.stat().st_ino
    again = admin.patch("/api/admin/feedback/3", json={"is_read": True}, headers=ADMIN)
    untouched = path.stat().st_ino == inode  # the same value: no rewrite
    unread = admin.patch(
        "/api/admin/feedback/2", json={"is_read": False}, headers=ADMIN
    )

    assert read.status_code == 200
    assert read.headers["cache-control"] == "no-store"
    assert read.json() == json.loads(line(2, read=True))
    assert after == [before[0], line(2, read=True), *before[2:]]
    assert by_hand_read.json() == {**json.loads(by_hand), "is_read": True}
    assert again.json() == by_hand_read.json()
    assert unread.json() == json.loads(line(2))
    assert path.read_text(encoding="utf-8").splitlines() == [
        line(1),
        line(2),
        "not json",
        '{"id":3,"message":"written by hand","is_read":true}',
    ]
    assert untouched
    assert path.stat().st_ino != inode  # a change renames a new file over the old one
    if os.name != "nt":
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert [item.name for item in state_dir.iterdir() if item.suffix == ".tmp"] == []


def test_deleting_a_report_removes_its_line_and_an_unknown_id_is_404(admin, state_dir):
    path = seed(state_dir, line(1), line(2), line(3))

    deleted = admin.delete("/api/admin/feedback/2", headers=ADMIN)
    unknown = [
        admin.delete("/api/admin/feedback/2", headers=ADMIN),
        admin.delete("/api/admin/feedback/0", headers=ADMIN),
        admin.delete("/api/admin/feedback/x1", headers=ADMIN),
        admin.patch("/api/admin/feedback/9", json={"is_read": True}, headers=ADMIN),
    ]
    rest = [admin.delete(f"/api/admin/feedback/{n}", headers=ADMIN) for n in (1, 3)]
    listed = admin.get("/api/admin/feedback", headers=ADMIN)

    assert deleted.status_code == 200
    assert deleted.json() == {"status": "deleted"}
    for answer in unknown:
        body = problem(answer, 404, "not_found")
        assert body["message"] == message(
            "gui.admin.no_report", lang="pl", report=body["details"]["id"]
        )
    assert [answer.json() for answer in rest] == [{"status": "deleted"}] * 2
    assert path.read_bytes() == b""
    assert listed.json() == {"items": [], "total": 0, "unread_count": 0}


@pytest.mark.parametrize(
    ("content", "headers"),
    [
        (b'{"is_read": true}', {"Content-Type": "text/plain"}),
        (b'{"is_read": true}', {}),
        (b"is_read=true", JSON),
        (b'{"is_read": "true"}', JSON),
        (b'{"is_read": 1}', JSON),
        (b'{"is_read": true, "message": "changed"}', JSON),
        (b"[true]", JSON),
        (b"", JSON),
        (b'{"is_read": true}' + b" " * 1024, JSON),
    ],
)
def test_a_change_of_a_report_is_checked_before_the_file(
    admin, state_dir, content, headers
):
    path = seed(state_dir, line(1))
    before = path.read_bytes()

    answer = admin.patch(
        "/api/admin/feedback/1", content=content, headers={**ADMIN, **headers}
    )

    problem(answer, 400, "validation_error")
    assert path.read_bytes() == before


@pytest.mark.skipif(sys.platform == "win32", reason="flock is POSIX")
def test_a_report_waiting_for_the_lock_goes_to_the_rewritten_file(tmp_path):
    import fcntl

    path = tmp_path / "state" / "feedback.jsonl"
    Feedback(path).append("first", CONTEXT)
    # Another process rewrites the file: it holds the lock until its rename is done
    rewriting = os.open(path, os.O_RDWR)
    fcntl.flock(rewriting, fcntl.LOCK_EX)
    added: list[int] = []
    waiting = threading.Thread(
        target=lambda: added.append(Feedback(path).append("second", CONTEXT))
    )
    waiting.start()
    waiting.join(0.3)
    held = waiting.is_alive()
    new = path.with_name("new.jsonl")
    new.write_text('{"id":1,"message":"first","is_read":true}\n', encoding="utf-8")
    os.replace(new, path)
    os.close(rewriting)
    waiting.join(10)

    assert held  # the report waited for the lock
    assert added == [2]
    lines = [json.loads(text) for text in path.read_text("utf-8").splitlines()]
    assert [(r["id"], r["message"], r["is_read"]) for r in lines] == [
        (1, "first", True),
        (2, "second", False),
    ]


def test_the_panel_reads_and_writes_no_report_under_the_data_root(
    make_client, fixture_root, tmp_path, key
):
    root = tmp_path / "obserwator"
    shutil.copytree(fixture_root, root)
    seed(root, line(1))  # a file of the root, not the GUI's
    before = files_of(tmp_path)

    client = make_client(root, gui_dir=root)
    listed = client.get("/api/admin/feedback", headers=ADMIN)
    marked = client.patch(
        "/api/admin/feedback/1", json={"is_read": True}, headers=ADMIN
    )
    deleted = client.delete("/api/admin/feedback/1", headers=ADMIN)
    client.__exit__(None, None, None)

    assert listed.json() == {"items": [], "total": 0, "unread_count": 0}
    problem(marked, 404, "not_found")
    problem(deleted, 404, "not_found")
    assert files_of(tmp_path) == before


# --- statistics ----------------------------------------------------------------------------


def day(date: str, visitors: int, base: int = 1) -> str:
    """A line of ``stats.jsonl``; the totals from ``base``."""
    document = {
        "date": date,
        "visitors": visitors,
        "page_views": base * 10,
        "stations_opened": base * 3,
        "analyses_run": base * 2,
        "downloads": base,
    }
    return json.dumps(document, separators=(",", ":"))


@pytest.fixture
def stats_client(read_only_root, live, state_dir, key):
    """The GUI at noon UTC of 2026-11-13 with lines in ``stats.jsonl``."""
    from obserwator.gui._analyses import Analyses
    from obserwator.gui._app import build_app
    from obserwator.gui._live import CurrentData, Pmaxtp
    from obserwator.gui._root import DataRoot
    from obserwator.gui._state import GuiState
    from obserwator.gui._traffic import TrafficState

    state_dir.mkdir()
    (state_dir / "stats.jsonl").write_text(
        "\n".join(
            [
                day("2026-10-14", 7),
                day("2026-10-15", 5, base=2),
                "not json",
                '{"date": "2026-11-02", "visitors": -1, "page_views": "many"}',
                '{"date": "2.11.2026", "visitors": 3}',
                day("2026-11-12", 4, base=3),
                day("2026-11-13", 6),
                day("2026-11-20", 9),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    config = gui_config(read_only_root, state_dir)
    state = GuiState(
        config=config,
        root=DataRoot(read_only_root),
        analyses=Analyses(read_only_root),
        current=CurrentData(sources=live.sources()),
        pmaxtp=Pmaxtp(fetch=live.fetch),
        traffic=TrafficState(
            limit=1000, window=60, directory=state_dir, clock=lambda: NOON
        ),
        feedback=Feedback(state_dir / "feedback.jsonl"),
        terms=None,
    )
    with TestClient(build_app(config, state=state)) as client:
        yield client


def test_stats_are_the_stored_days_and_today_as_counted_so_far(stats_client):
    stats_client.get("/")  # a visitor and a page view of today
    stats_client.get("/admin/")  # the panel is not counted

    answer = stats_client.get("/api/admin/stats", headers=ADMIN)

    assert answer.status_code == 200
    assert answer.headers["cache-control"] == "no-store"
    zero = dict.fromkeys(
        ["visitors", "page_views", "stations_opened", "analyses_run", "downloads"], 0
    )
    assert answer.json() == {
        "days": [
            json.loads(day("2026-10-15", 5, base=2)),
            {"date": "2026-11-02", **zero},
            json.loads(day("2026-11-12", 4, base=3)),
            {**json.loads(day("2026-11-13", 6)), "visitors": 7, "page_views": 11},
        ],
        "totals": {
            "page_views": 20 + 30 + 11,
            "stations_opened": 6 + 9 + 3,
            "analyses_run": 4 + 6 + 2,
            "downloads": 2 + 3 + 1,
        },
    }


def test_stats_take_two_days_both_included(stats_client):
    def dates(query: str) -> list[str]:
        answer = stats_client.get(f"/api/admin/stats?{query}", headers=ADMIN)
        assert answer.status_code == 200, answer.text
        return [line["date"] for line in answer.json()["days"]]

    assert dates("from=2026-11-12&to=2026-11-20") == [
        "2026-11-12",
        "2026-11-13",
        "2026-11-20",
    ]
    assert dates("from=1970-01-01") == [
        "2026-10-14",
        "2026-10-15",
        "2026-11-02",
        "2026-11-12",
        "2026-11-13",
    ]
    assert dates("to=2026-11-12") == [
        "2026-10-14",
        "2026-10-15",
        "2026-11-02",
        "2026-11-12",
    ]
    assert dates("from=2026-11-14&to=2026-11-19") == []


@pytest.mark.parametrize(
    ("query", "option"),
    [
        ("from=2026-11-14&to=2026-11-13", "from"),
        ("from=2026-11-14", "from"),
        ("to=13.11.2026", "to"),
        ("from=2026-02-30", "from"),
        ("days=7", "days"),
    ],
)
def test_the_days_of_the_stats_are_checked(stats_client, query, option):
    answer = stats_client.get(f"/api/admin/stats?{query}", headers=ADMIN)

    problem(answer, 400, "validation_error", option)


# --- status --------------------------------------------------------------------------------


def statuses(client) -> dict[str, str]:
    answer = client.get("/api/admin/status", headers={**ADMIN, "Accept-Language": "en"})
    assert answer.status_code == 200, answer.text
    return {check["name"]: check["status"] for check in answer.json()["checks"]}


def test_status_names_the_app_its_directory_its_disk_and_its_checks(
    make_client, stored_root, hydrolog, key, state_dir
):
    before = datetime.now(UTC).replace(microsecond=0)
    client = make_client(stored_root, hydrolog=hydrolog, gui_dir=state_dir)

    answer = client.get("/api/admin/status", headers={**ADMIN, "Accept-Language": "en"})

    assert answer.status_code == 200
    assert answer.headers["cache-control"] == "no-store"
    document = answer.json()
    assert list(document) == [
        "app",
        "version",
        "started_at",
        "uptime_s",
        "data_dir",
        "disk",
        "checks",
    ]
    assert document["app"] == "Obserwator"
    assert document["version"] == obserwator.__version__
    assert before <= datetime.fromisoformat(document["started_at"]) <= datetime.now(UTC)
    assert type(document["uptime_s"]) is int and document["uptime_s"] >= 0
    assert document["data_dir"] == str(state_dir)
    disk = document["disk"]
    assert 0 <= disk["free_bytes"] <= disk["total_bytes"]
    checks = document["checks"]
    assert [(check["name"], check["status"]) for check in checks] == [
        (name, "ok") for name in CHECKS
    ]
    assert str(stored_root) in checks[0]["detail"]
    assert "IMGW-PIB" in checks[1]["detail"] and "ČHMÚ" in checks[1]["detail"]
    assert checks[2]["detail"] == message(
        "gui.admin.check_hydrolog_ok", version=HYDROLOG_VERSION
    )


def test_status_warns_of_what_is_missing_and_fails_what_is_broken(
    make_client, read_only_root, tmp_path, key
):
    broken = tmp_path / "broken.py"
    broken.write_text("import sys\nsys.exit(3)\n", encoding="utf-8")

    # The setting of Hydrolog's program is read when each client is made: ask at once
    plain = statuses(make_client(read_only_root))
    failing = statuses(make_client(hydrolog=(sys.executable, str(broken))))
    no_root = statuses(make_client(tmp_path / "no-root"))

    assert plain == {
        "data_root_marker": "ok",
        "stored_analyses": "warning",
        "hydrolog_command": "warning",
    }
    assert failing["hydrolog_command"] == "failed"
    assert no_root == {
        "data_root_marker": "failed",
        "stored_analyses": "failed",
        "hydrolog_command": "warning",
    }


def test_stored_analyses_name_the_providers_that_lack_them():
    version = Version(
        "analyses:pl.imgw.analyses",
        Path("analyses.json"),
        "2026-11-13_ab12cd34",
        "0" * 64,
        None,
        "1.2.0",
    )
    both = {"IMGW-PIB": version, "CHMI": version}

    partial = _analyses_check(
        Snapshot(catalogs=both, analyses={"IMGW-PIB": version}), "en"
    )
    complete = _analyses_check(Snapshot(catalogs=both, analyses=both), "en")

    assert partial == {
        "name": "stored_analyses",
        "status": "warning",
        "detail": message(
            "gui.admin.check_analyses_partial",
            versions="IMGW-PIB 2026-11-13_ab12cd34 (Hydrolog 1.2.0)",
            providers="ČHMÚ",
        ),
    }
    assert complete["status"] == "ok"
    assert complete["detail"] == message(
        "gui.admin.check_analyses_ok",
        versions=(
            "IMGW-PIB 2026-11-13_ab12cd34 (Hydrolog 1.2.0), "
            "ČHMÚ 2026-11-13_ab12cd34 (Hydrolog 1.2.0)"
        ),
    )


# --- the page ------------------------------------------------------------------------------


def test_the_admin_page_is_the_kit_shell_never_kept_under_its_own_origin_only(
    make_client,
):
    basemap = Basemap("https://tiles.example/planet", "https://tiles.example", "©")
    client = make_client(basemap=basemap)

    moved = client.get("/admin?from=bookmark", follow_redirects=False)
    page = client.get("/admin/")
    script = client.get("/admin/theme-init.js")

    assert moved.status_code == 308
    assert moved.headers["location"] == "admin/?from=bookmark"
    assert page.status_code == 200
    assert page.headers["content-type"] == "text/html; charset=utf-8"
    html = page.text
    assert re.search(
        r'<nogat-admin app="Obserwator" project="obserwator" back="\.\./"'
        r' marks="\.\./nogat/marks/"></nogat-admin>',
        html,
    )
    assert '<meta name="robots" content="noindex">' in html
    loaded = re.findall(r'(?:src|href)="([^"]+)"', html)
    assert loaded == [
        "../nogat/marks/obserwator.svg",
        "theme-init.js",
        "../nogat/tokens.css",
        "../nogat/nogat-admin.css",
        "../nogat/nogat-admin.js",
    ]
    for answer in (moved, page, script):
        assert answer.headers["cache-control"] == "no-store", answer.url
        assert csp(answer) == ADMIN_CSP, answer.url
    assert "https://tiles.example" in client.get("/").headers["content-security-policy"]


def test_the_admin_page_and_api_follow_the_apps_prefix(read_only_root, tmp_path, key):
    from obserwator.gui._app import build_app

    host = Starlette(
        routes=[
            Mount(
                "/m/obserwator",
                app=build_app(gui_config(read_only_root, tmp_path / "state")),
            )
        ]
    )

    with TestClient(host) as client:
        page = client.get("/m/obserwator/admin")
        listed = client.get("/m/obserwator/api/admin/feedback", headers=ADMIN)

    assert page.status_code == 200
    assert page.url.path == "/m/obserwator/admin/"
    assert "<nogat-admin " in page.text
    assert listed.json() == {"items": [], "total": 0, "unread_count": 0}


@pytest.mark.parametrize(
    ("method", "path", "allowed"),
    [
        ("GET", "/api/admin/feedback/1", "PATCH, DELETE"),
        ("POST", "/api/admin/feedback/1", "PATCH, DELETE"),
        ("PATCH", "/api/admin/feedback", "GET, HEAD"),
        ("DELETE", "/api/admin/feedback/1/2", "GET, HEAD"),
        ("PUT", "/api/admin/status", "GET, HEAD"),
        ("POST", "/admin/", "GET, HEAD"),
    ],
)
def test_each_admin_address_takes_its_own_methods(admin, method, path, allowed):
    answer = admin.request(method, path, headers=ADMIN)

    problem(answer, 405, "method_not_allowed")
    assert answer.headers["allow"] == allowed
