"""The GUI's access log (Nogat DEV-12.4 to DEV-12.8): the app that ``gui serve`` builds.

The app gets a ``ServerLog`` of the test (its own directory, a fixed clock and a stream
in memory), as `obserwator.gui.serve` gives it one in ``<state_dir>/obserwator/logs``;
``test_serve.py`` runs the program itself and reads that directory.
"""

from __future__ import annotations

import io
import json
import re
from datetime import UTC, datetime

from obserwator import __version__
from obserwator.gui._app import BORDERS
from obserwator.nogat_logging import ServerLog
from tests.contract.nogat import validate

IP = "203.0.113.77"
NOON = datetime(2026, 11, 13, 12, 0, tzinfo=UTC)
FIREFOX = "Mozilla/5.0 (X11; Linux x86_64; rv:140.0) Gecko/20100101 Firefox/140.0"


def server_log(tmp_path) -> ServerLog:
    return ServerLog(
        "obserwator",
        __version__,
        tmp_path / "logs",
        stream=io.StringIO(),
        clock=lambda: NOON,
    )


def access_records(tmp_path) -> list[dict[str, object]]:
    path = tmp_path / "logs" / "access-2026-11-13.jsonl"
    return [json.loads(line) for line in path.read_text("utf-8").splitlines()]


def test_each_answered_request_is_one_access_record_without_the_client(
    make_client, tmp_path
):
    log = server_log(tmp_path)
    client = make_client(log=log, address=IP)

    plain = {"User-Agent": FIREFOX, "Accept-Encoding": "identity"}  # bytes as read
    page = client.get("/?view=pmaxtp", headers=plain)
    session = client.get("/api/session", headers={"User-Agent": "curl/8.5.0"})
    missing = client.get("/api/nothing", headers={"User-Agent": "Googlebot/2.1"})
    statics = [
        client.get(path)
        for path in (
            "/css/app.css",
            "/src/main.js",
            "/nogat/tokens.css",
            "/theme-init.js",
            "/admin/theme-init.js",
            "/instrukcja/",
            f"/data/{next(iter(BORDERS))}",
        )
    ]
    static_missing = client.get("/css/nothing.css")
    terms = client.get("/regulamin.html")  # not public: 404

    records = access_records(tmp_path)
    for record in records:
        validate(record, "record-1")
    assert [(r["method"], r["path"], r["status"]) for r in records] == [
        ("GET", "/?view=pmaxtp", 200),
        ("GET", "/api/session", 200),
        ("GET", "/api/nothing", 404),
        ("GET", "/css/nothing.css", 404),
        ("GET", "/regulamin.html", 404),
    ]
    # TestClient names itself ``testclient`` unless told otherwise: a script.
    agents = ["browser", "script", "bot", "script", "script"]
    assert [r["agent"] for r in records] == agents
    assert records[0]["bytes"] == len(page.content)
    assert {r["app"] for r in records} == {"obserwator"}
    assert len({r["request_id"] for r in records}) == len(records)
    assert [s.status_code for s in statics] == [200] * len(statics)
    for answer in (page, session, missing, static_missing, terms, *statics):
        assert "x-request-id" not in answer.headers
    written = b"".join(path.read_bytes() for path in (tmp_path / "logs").iterdir())
    assert IP.encode() not in written
    assert not re.search(rb"Firefox|curl|Googlebot", written)


def test_the_answers_of_the_rate_limit_are_logged(make_client, tmp_path):
    log = server_log(tmp_path)
    client = make_client(log=log, address=IP, request_limit=1)

    first = client.get("/api/session")
    refused = client.get("/api/session")

    assert (first.status_code, refused.status_code) == (200, 429)
    records = access_records(tmp_path)
    assert [(r["path"], r["status"]) for r in records] == [
        ("/api/session", 200),
        ("/api/session", 429),
    ]
    assert records[1]["bytes"] == len(refused.content)
    validate(records[1], "record-1")


def test_no_log_holds_the_admin_key(make_client, tmp_path, monkeypatch):
    key = "klucz-administratora-42"
    monkeypatch.setenv("OBSERWATOR_ADMIN_API_KEY", key)
    log = server_log(tmp_path)
    client = make_client(log=log, gui_dir=tmp_path / "state")

    answers = [
        client.get("/api/admin/status", headers={"X-Admin-Key": key}),
        client.get("/api/admin/feedback", headers={"X-Admin-Key": f"{key}-wrong"}),
        client.delete("/api/admin/feedback/7", headers={"X-Admin-Key": key}),
    ]

    assert [answer.status_code for answer in answers] == [200, 401, 404]
    assert [
        (r["method"], r["path"], r["status"]) for r in access_records(tmp_path)
    ] == [
        ("GET", "/api/admin/status", 200),
        ("GET", "/api/admin/feedback", 401),
        ("DELETE", "/api/admin/feedback/7", 404),
    ]
    written = b"".join(path.read_bytes() for path in (tmp_path / "logs").iterdir())
    assert key.encode() not in written
