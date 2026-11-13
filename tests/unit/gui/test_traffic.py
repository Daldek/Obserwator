"""Rate limit, daily statistics and access log of the public GUI (Nogat DEV-15.9 to DEV-15.11)."""

from __future__ import annotations

import asyncio
import json
import re
import stat
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime, timedelta

import pytest
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.responses import HTMLResponse, JSONResponse, PlainTextResponse
from starlette.routing import Mount, Route
from starlette.testclient import TestClient

from obserwator.gui import _traffic
from obserwator.gui._traffic import Traffic, TrafficState

IP = "203.0.113.77"
NOON = datetime(2026, 11, 13, 12, 0, tzinfo=UTC).timestamp()
KEYS = [
    "date",
    "visitors",
    "page_views",
    "stations_opened",
    "analyses_run",
    "downloads",
]
LOG_KEYS = {
    "time",
    "method",
    "path",
    "status",
    "size",
    "duration_ms",
    "request_id",
    "user_agent",
}


class Clock:
    """Wall-clock and monotonic time that move only when told."""

    def __init__(self, wall: float = NOON) -> None:
        self.wall = wall
        self.mono = 5000.0

    def time(self) -> float:
        return self.wall

    def monotonic(self) -> float:
        return self.mono

    def advance(self, seconds: float) -> None:
        self.wall += seconds
        self.mono += seconds


def make_state(tmp_path, clock, *, limit=300, window=60) -> TrafficState:
    return TrafficState(
        limit=limit,
        window=window,
        state_dir=tmp_path / "state",
        clock=clock.time,
        monotonic=clock.monotonic,
    )


def make_app(state: TrafficState) -> Starlette:
    async def page(request):
        return HTMLResponse("<p>page</p>")

    async def missing_page(request):
        return HTMLResponse("<p>gone</p>", status_code=404)

    async def api(request):
        return JSONResponse({"ok": True})

    async def static(request):
        return PlainTextResponse("console.log(1)")

    async def broken(request):
        raise RuntimeError("boom")

    @asynccontextmanager
    async def lifespan(app):
        await state.start()
        yield
        await state.stop()

    return Starlette(
        routes=[
            Route("/", page),
            Route("/index.html", page),
            Route("/regulamin.html", page),
            Route("/instrukcja/", page),
            Route("/instrukcja/index.html", missing_page),
            Route("/api/broken", broken),
            Route("/api/{rest:path}", api),
            Route("/app.js", static),
        ],
        middleware=[Middleware(Traffic, state=state)],
        lifespan=lifespan,
    )


def client_of(app, address: str = IP, **kwargs) -> TestClient:
    return TestClient(app, client=(address, 4321), **kwargs)


def stats_lines(tmp_path):
    text = (tmp_path / "state" / "stats.jsonl").read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines()]


def log_lines(tmp_path, day: str = "2026-11-13"):
    path = tmp_path / "state" / "logs" / f"access-{day}.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


# --------------------------------------------------------------------------
# Rate limit (DEV-15.9)
# --------------------------------------------------------------------------


def test_the_301st_request_in_60_s_is_refused_with_retry_after(tmp_path):
    clock = Clock()
    client = client_of(make_app(make_state(tmp_path, clock)))

    answers = [client.get("/api/stations").status_code for _ in range(300)]
    clock.advance(15)
    refused = client.get("/api/stations", headers={"Accept-Language": "en"})

    assert set(answers) == {200}
    assert refused.status_code == 429
    assert refused.headers["Retry-After"] == "45"
    document = refused.json()
    assert document["code"] == "rate_limited"
    assert document["details"] == {"retry_after": 45}
    assert document["message"] == "Too many requests. Try again in 45 s."


def test_the_window_slides(tmp_path):
    clock = Clock()
    client = client_of(make_app(make_state(tmp_path, clock, limit=2, window=60)))

    first = client.get("/api/a")
    clock.advance(30)
    second = client.get("/api/a")
    refused = client.get("/api/a")
    clock.advance(30)  # the first request leaves the window
    third = client.get("/api/a")
    refused_again = client.get("/api/a")

    assert [first.status_code, second.status_code, third.status_code] == [200] * 3
    assert refused.status_code == 429 and refused.headers["Retry-After"] == "30"
    assert refused_again.status_code == 429
    assert refused_again.headers["Retry-After"] == "30"


def test_a_refused_request_does_not_extend_the_wait(tmp_path):
    clock = Clock()
    client = client_of(make_app(make_state(tmp_path, clock, limit=1, window=60)))

    client.get("/api/a")
    for _ in range(5):
        clock.advance(10)
        client.get("/api/a")
    clock.advance(10)

    assert client.get("/api/a").status_code == 200


def test_a_page_over_the_limit_is_a_short_page_in_the_readers_language(tmp_path):
    clock = Clock()
    client = client_of(make_app(make_state(tmp_path, clock, limit=1, window=60)))

    client.get("/")
    polish = client.get("/regulamin.html")
    english = client.get("/instrukcja/", headers={"Accept-Language": "en-GB,en;q=0.9"})

    assert polish.status_code == 429 and polish.headers["Retry-After"] == "60"
    assert polish.headers["content-type"].startswith("text/html")
    assert "Zbyt wiele żądań. Spróbuj ponownie za 60 s." in polish.text
    assert '<html lang="pl">' in polish.text
    assert "<script" not in polish.text and "<style" not in polish.text
    assert " style=" not in polish.text
    assert '<link rel="stylesheet" href="/nogat/tokens.css">' in polish.text
    assert "Too many requests. Try again in 60 s." in english.text
    assert re.fullmatch(r"[0-9a-f]{16}", polish.headers["X-Request-Id"])


def test_static_files_are_not_counted_nor_refused(tmp_path):
    clock = Clock()
    state = make_state(tmp_path, clock, limit=1, window=60)
    client = client_of(make_app(state))

    statics = [client.get("/app.js").status_code for _ in range(5)]
    first = client.get("/api/a")
    refused = client.get("/api/a")
    static_after = client.get("/app.js")

    assert statics == [200] * 5
    assert first.status_code == 200 and refused.status_code == 429
    assert static_after.status_code == 200
    assert state.snapshot()["page_views"] == 0


def test_each_address_has_its_own_limit(tmp_path):
    clock = Clock()
    app = make_app(make_state(tmp_path, clock, limit=1, window=60))

    first = client_of(app, "198.51.100.1").get("/api/a")
    other = client_of(app, "198.51.100.2").get("/api/a")
    again = client_of(app, "198.51.100.1").get("/api/a")

    assert (first.status_code, other.status_code, again.status_code) == (200, 200, 429)


def test_the_limit_classifies_paths_relative_to_the_mount(tmp_path):
    clock = Clock()
    state = make_state(tmp_path, clock, limit=1, window=60)
    outer = Starlette(routes=[Mount("/gui", app=make_app(state))])
    client = client_of(outer)

    statics = [client.get("/gui/app.js").status_code for _ in range(3)]
    first = client.get("/gui/")
    refused = client.get("/gui/index.html")

    assert statics == [200] * 3
    assert first.status_code == 200 and refused.status_code == 429
    assert '<link rel="stylesheet" href="/gui/nogat/tokens.css">' in refused.text


# --------------------------------------------------------------------------
# Statistics (DEV-15.11)
# --------------------------------------------------------------------------


def test_the_day_counts_visitors_pages_and_totals(tmp_path):
    clock = Clock()
    state = make_state(tmp_path, clock)
    app = make_app(state)
    firefox = {"User-Agent": "Firefox"}
    chrome = {"User-Agent": "Chrome"}

    with client_of(app) as client:
        client.get("/", headers=firefox)
        client.get("/index.html", headers=firefox)
        client.get("/api/a", headers=chrome)
        client.get("/instrukcja/index.html", headers=firefox)  # a page answered 404
        client.get("/app.js", headers={"User-Agent": "Static only"})
        client_of(app, "198.51.100.9").get("/regulamin.html", headers=firefox)
        state.count("stations_opened")
        state.count("analyses_run")
        state.count("downloads")
        state.count("downloads")
        snapshot = state.snapshot()

    assert snapshot == {
        "date": "2026-11-13",
        "visitors": 3,
        "page_views": 3,
        "stations_opened": 1,
        "analyses_run": 1,
        "downloads": 2,
    }
    assert stats_lines(tmp_path) == [snapshot]


def test_the_stats_file_is_private_and_holds_exactly_the_keys(tmp_path):
    clock = Clock()
    with client_of(make_app(make_state(tmp_path, clock))) as client:
        client.get("/")

    path = tmp_path / "state" / "stats.jsonl"
    (line,) = stats_lines(tmp_path)
    assert list(line) == KEYS
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    assert [p.name for p in path.parent.iterdir() if p.name.endswith(".tmp")] == []


def test_a_restart_adds_to_the_days_line_and_keeps_other_days_in_order(tmp_path):
    clock = Clock()
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    earlier = {
        "date": "2026-11-12",
        "visitors": 7,
        "page_views": 9,
        "stations_opened": 1,
        "analyses_run": 0,
        "downloads": 0,
    }
    (state_dir / "stats.jsonl").write_text(json.dumps(earlier) + "\n", encoding="utf-8")

    with client_of(make_app(make_state(tmp_path, clock))) as client:
        client.get("/")
        client.get("/")
    clock.advance(600)
    state = make_state(tmp_path, clock)
    with client_of(make_app(state)) as client:
        client.get("/")  # the same visitor, counted again under the new salt
        state.count("downloads")

    lines = stats_lines(tmp_path)
    assert lines[0] == earlier
    assert lines[1] == {
        "date": "2026-11-13",
        "visitors": 2,
        "page_views": 3,
        "stations_opened": 0,
        "analyses_run": 0,
        "downloads": 1,
    }
    assert len(lines) == 2


def test_the_day_changes_at_midnight_utc_with_a_new_line(tmp_path):
    clock = Clock(datetime(2026, 11, 13, 23, 59, 30, tzinfo=UTC).timestamp())
    state = make_state(tmp_path, clock)

    with client_of(make_app(state)) as client:
        client.get("/")
        state.count("downloads")
        clock.advance(29)  # 23:59:59, still the same day
        client.get("/")
        clock.advance(1)  # 00:00:00 UTC
        client.get("/")
        written_at_midnight = stats_lines(tmp_path)
        snapshot = state.snapshot()

    old = {
        "date": "2026-11-13",
        "visitors": 1,
        "page_views": 2,
        "stations_opened": 0,
        "analyses_run": 0,
        "downloads": 1,
    }
    new = {
        "date": "2026-11-14",
        "visitors": 1,
        "page_views": 1,
        "stations_opened": 0,
        "analyses_run": 0,
        "downloads": 0,
    }
    assert written_at_midnight == [old]
    assert snapshot == new
    assert stats_lines(tmp_path) == [old, new]


def test_the_days_line_is_rewritten_periodically(tmp_path, monkeypatch):
    monkeypatch.setattr(_traffic, "FLUSH_INTERVAL_S", 0.01)
    state = make_state(tmp_path, Clock())

    async def run():
        await state.start()
        state.count("analyses_run")
        for _ in range(200):
            await asyncio.sleep(0.01)
            if (tmp_path / "state" / "stats.jsonl").exists():
                break
        written = stats_lines(tmp_path)
        await state.stop()
        return written

    written = asyncio.run(run())

    assert written[0]["analyses_run"] == 1


def test_an_unknown_total_is_a_program_error(tmp_path):
    with pytest.raises(ValueError, match="pages"):
        make_state(tmp_path, Clock()).count("pages")


# --------------------------------------------------------------------------
# Access log (DEV-15.10)
# --------------------------------------------------------------------------


def test_every_request_is_one_log_line_without_the_address(tmp_path):
    clock = Clock()
    app = make_app(make_state(tmp_path, clock, limit=2))

    with client_of(app, raise_server_exceptions=False) as client:
        page = client.get("/?a=1&b=%C5%BC", headers={"User-Agent": "Firefox/140"})
        static = client.get("/app.js")
        client.get("/api/broken")
        refused = client.get("/api/x")

    lines = log_lines(tmp_path)
    assert [line["path"] for line in lines] == [
        "/?a=1&b=%C5%BC",
        "/app.js",
        "/api/broken",
        "/api/x",
    ]
    assert [line["status"] for line in lines] == [200, 200, 500, 429]
    assert all(set(line) == LOG_KEYS for line in lines)
    first = lines[0]
    assert first["time"] == "2026-11-13T12:00:00.000Z"
    assert first["method"] == "GET"
    assert first["size"] == len(page.content)
    assert first["user_agent"] == "Firefox/140"
    assert first["request_id"] == page.headers["X-Request-Id"]
    assert lines[1]["request_id"] == static.headers["X-Request-Id"]
    assert lines[3]["request_id"] == refused.headers["X-Request-Id"]
    assert lines[3]["size"] == len(refused.content)
    assert len({line["request_id"] for line in lines}) == 4
    assert all(re.fullmatch(r"[0-9a-f]{16}", line["request_id"]) for line in lines)
    log = tmp_path / "state" / "logs" / "access-2026-11-13.jsonl"
    assert stat.S_IMODE(log.stat().st_mode) == 0o600
    assert stat.S_IMODE(log.parent.stat().st_mode) == 0o700


def test_no_written_file_holds_the_client_address(tmp_path):
    clock = Clock()
    state = make_state(tmp_path, clock, limit=1)

    with client_of(make_app(state), raise_server_exceptions=False) as client:
        client.get("/", headers={"User-Agent": "Firefox"})
        client.get("/")  # refused
        client.get("/api/broken")
        client.get("/app.js")
        clock.advance(86400)  # a new day: the old line and a new log
        client.get("/api/a")

    files = [path for path in (tmp_path / "state").rglob("*") if path.is_file()]
    assert len(files) == 3  # stats.jsonl and two access logs
    for path in files:
        assert IP.encode() not in path.read_bytes(), path.name


def _touch_logs(tmp_path, *days: date) -> None:
    logs = tmp_path / "state" / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    for day in days:
        (logs / f"access-{day.isoformat()}.jsonl").write_text("{}\n", encoding="utf-8")
    (logs / "notes.txt").write_text("kept", encoding="utf-8")


def _log_days(tmp_path) -> set[str]:
    return {path.name for path in (tmp_path / "state" / "logs").iterdir()}


def test_logs_older_than_14_days_are_deleted_at_start(tmp_path):
    today = date(2026, 11, 13)
    _touch_logs(tmp_path, today - timedelta(days=14), today - timedelta(days=13))

    with client_of(make_app(make_state(tmp_path, Clock()))):
        remaining = _log_days(tmp_path)

    assert remaining == {"access-2026-10-31.jsonl", "notes.txt"}


def test_logs_older_than_14_days_are_deleted_at_the_day_change(tmp_path):
    clock = Clock()
    today = date(2026, 11, 13)
    _touch_logs(tmp_path, today - timedelta(days=13))
    state = make_state(tmp_path, clock)

    with client_of(make_app(state)) as client:
        client.get("/app.js")
        kept_today = _log_days(tmp_path)
        clock.advance(86400)
        client.get("/app.js")
        after = _log_days(tmp_path)

    assert "access-2026-10-31.jsonl" in kept_today
    assert after == {
        "access-2026-11-13.jsonl",
        "access-2026-11-14.jsonl",
        "notes.txt",
    }
