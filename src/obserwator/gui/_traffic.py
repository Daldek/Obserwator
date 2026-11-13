"""
The public GUI's traffic: rate limit, daily statistics and access log (Nogat DEV-15.9 to DEV-15.11).

`Traffic` wraps the app as a pure ASGI middleware and `TrafficState` holds what it
counts. A request is an API call (``/api/…``), a page (the start page, the regulamin,
the manual) or a static file, by its path relative to the mount.

- Rate limit (DEV-15.9): API calls and pages, not static files, of one client address
  (the one the proxy reports, put in place by uvicorn) are counted in a sliding window
  of ``window`` seconds; above ``limit`` the answer is ``429`` with ``Retry-After``,
  the error document ``rate_limited`` for an API call and a short page for a page. The
  address lives in memory only, for the window only.
- Statistics (DEV-15.11): a visitor is the HMAC-SHA-256 of the address and the
  User-Agent under a random 32-byte salt drawn at start and at each 00:00 UTC; salt and
  hashes stay in memory. Each UTC day is one line of ``<state_dir>/stats.jsonl``
  (``date``, ``visitors``, ``page_views``, ``stations_opened``, ``analyses_run``,
  ``downloads``), rewritten atomically every `FLUSH_INTERVAL_S`, at the day's end and at
  shutdown; a restart adds to the day's line.
- Access log (DEV-15.10): one JSON line per request (time, method, path with query,
  status, size, duration, request id, User-Agent; never the address) in
  ``<state_dir>/logs/access-YYYY-MM-DD.jsonl``, kept `LOG_DAYS` days; every answer
  carries its id in ``X-Request-Id``.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import hmac
import json
import logging
import math
import os
import re
import secrets
import tempfile
import threading
import time
from collections import deque
from collections.abc import Callable, Mapping
from datetime import UTC, date, datetime, timedelta
from html import escape
from pathlib import Path
from typing import IO, Literal

from starlette.datastructures import Headers, MutableHeaders
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from obserwator.gui._http import GuiError, error_response, page_lang
from obserwator.messages import message

_LOG = logging.getLogger(__name__)

Total = Literal["stations_opened", "analyses_run", "downloads"]
TOTALS: tuple[Total, ...] = ("stations_opened", "analyses_run", "downloads")
"""The totals the routes count (`TrafficState.count`)."""
COUNTERS: tuple[str, ...] = ("visitors", "page_views", *TOTALS)
"""The numbers of a day's line of ``stats.jsonl``, after its ``date``."""
PAGES = frozenset(
    {"/", "/index.html", "/regulamin.html", "/instrukcja/", "/instrukcja/index.html"}
)
"""The paths of the GUI's HTML pages, relative to its mount."""
STATS_FILE = "stats.jsonl"
LOG_DIR = "logs"
LOG_DAYS = 14
"""How many UTC days of access logs are kept: today's and the 13 before it."""
FLUSH_INTERVAL_S = 300.0
"""How often the day's statistics line is rewritten [s] (DEV-15.11: at most 10 min)."""
SWEEP_INTERVAL_S = 1.0
"""How often addresses whose window has passed are forgotten [s]."""
SALT_BYTES = 32

_LOG_NAME = re.compile(r"access-(\d{4}-\d{2}-\d{2})\.jsonl")

Kind = Literal["api", "page", "static"]

_PAGE = """<!doctype html>
<html lang="{lang}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<link rel="stylesheet" href="{tokens}">
</head>
<body>
<main>
<h1>{title}</h1>
<p>{text}</p>
</main>
</body>
</html>
"""


def classify(path: str) -> Kind:
    """
    What a request is, by its path relative to the GUI's mount.

    Parameters
    ----------
    path : str
        The path without the mount's prefix (``scope["root_path"]``).

    Returns
    -------
    {"api", "page", "static"}
        ``api`` below ``/api/``, ``page`` for one of `PAGES`, ``static`` otherwise.
    """
    if path.startswith("/api/"):
        return "api"
    if (path or "/") in PAGES:
        return "page"
    return "static"


def _utc_day(moment: float) -> str:
    return datetime.fromtimestamp(moment, UTC).date().isoformat()


class TrafficState:
    """
    The rate limit, the day's statistics and the access log of one GUI app.

    Parameters
    ----------
    limit : int
        At most this many counted requests of one address in ``window`` seconds.
    window : int
        The sliding window of the rate limit [s].
    state_dir : Path
        The GUI's own directory: ``stats.jsonl`` and ``logs/`` go there.
    clock : callable, optional
        Wall-clock time in seconds since the epoch (the UTC day, the log's time).
    monotonic : callable, optional
        Monotonic time in seconds (the rate limit's window, the durations).
    """

    def __init__(
        self,
        *,
        limit: int,
        window: int,
        state_dir: Path,
        clock: Callable[[], float] = time.time,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.limit = limit
        self.window = window
        self.state_dir = state_dir
        self.stats_path = state_dir / STATS_FILE
        self.log_dir = state_dir / LOG_DIR
        self.clock = clock
        self.monotonic = monotonic
        self._lock = threading.Lock()  # windows, salt, visitors, counters
        self._io = threading.Lock()  # stats.jsonl; taken before _lock
        self._log_lock = threading.Lock()  # the access log file
        self._windows: dict[str, deque[float]] = {}
        self._swept = monotonic()
        self._day = _utc_day(clock())
        self._salt = secrets.token_bytes(SALT_BYTES)
        self._visitors: set[bytes] = set()
        self._counts = dict.fromkeys(COUNTERS, 0)
        self._base = self._read_line(self._day)
        self._log_file: IO[str] | None = None
        self._log_day: str | None = None
        self._task: asyncio.Task[None] | None = None

    # --- rate limit -----------------------------------------------------------------

    def admit(self, address: str) -> int | None:
        """
        Count a request of ``address`` against the limit.

        Parameters
        ----------
        address : str
            The client's address; kept in memory for the window only.

        Returns
        -------
        int or None
            None when the request is within the limit (it is then counted); else
            the whole seconds (at least 1) until the window lets one more in.
        """
        now = self.monotonic()
        with self._lock:
            if now - self._swept >= SWEEP_INTERVAL_S:
                self._sweep(now)
            times = self._windows.setdefault(address, deque())
            while times and now - times[0] >= self.window:
                times.popleft()
            if len(times) >= self.limit:
                return max(1, math.ceil(times[0] + self.window - now))
            times.append(now)
            return None

    def _sweep(self, now: float) -> None:
        self._windows = {
            address: times
            for address, times in self._windows.items()
            if times and now - times[-1] < self.window
        }
        self._swept = now

    # --- statistics -----------------------------------------------------------------

    def visit(self, address: str, user_agent: str) -> None:
        """Count the visitor of a request the limit counts: a keyed hash, never the address."""
        self._roll()
        data = f"{address}\n{user_agent}".encode()
        with self._lock:
            self._visitors.add(hmac.new(self._salt, data, hashlib.sha256).digest())

    def page_view(self) -> None:
        """Count an HTML page served."""
        self._roll()
        with self._lock:
            self._counts["page_views"] += 1

    def count(self, total: Total) -> None:
        """
        Count one of the day's totals.

        Parameters
        ----------
        total : {"stations_opened", "analyses_run", "downloads"}
            The total.
        """
        if total not in TOTALS:
            raise ValueError(f"Unknown total {total!r}; allowed: {TOTALS}")
        self._roll()
        with self._lock:
            self._counts[total] += 1

    def snapshot(self) -> dict[str, str | int]:
        """
        The day's line as it stands: earlier runs of the day plus this one.

        Returns
        -------
        dict
            ``date`` and the numbers of `COUNTERS`.
        """
        self._roll()
        with self._lock:
            return self._line()

    def _line(self) -> dict[str, str | int]:
        line: dict[str, str | int] = {"date": self._day}
        for key in COUNTERS:
            own = len(self._visitors) if key == "visitors" else self._counts[key]
            line[key] = self._base.get(key, 0) + own
        return line

    def _roll(self) -> None:
        """At a new UTC day: write the old day's line, draw a new salt, count anew."""
        day = _utc_day(self.clock())
        if day <= self._day:
            return
        with self._io:
            with self._lock:
                if day <= self._day:
                    return
                old = self._line()
                self._day = day
                self._salt = secrets.token_bytes(SALT_BYTES)
                self._visitors = set()
                self._counts = dict.fromkeys(COUNTERS, 0)
                self._base = {}
            self._write_line(old)
        with self._log_lock:
            self._prune_logs(date.fromisoformat(day))

    def flush(self) -> None:
        """Rewrite the day's line of ``stats.jsonl`` (after a day change, if one is due)."""
        self._roll()
        with self._io:
            with self._lock:
                line = self._line()
            self._write_line(line)

    def _read_line(self, day: str) -> dict[str, int]:
        """The numbers of ``day`` in ``stats.jsonl``, written by an earlier run."""
        try:
            text = self.stats_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return {}
        except OSError as exc:
            self._warn(STATS_FILE, exc)
            return {}
        for raw in text.splitlines():
            document = _object(raw)
            if document is not None and document.get("date") == day:
                return {
                    key: value
                    for key in COUNTERS
                    if type(value := document.get(key)) is int and value >= 0
                }
        return {}

    def _write_line(self, line: Mapping[str, str | int]) -> None:
        """Put ``line`` into ``stats.jsonl`` in date order: temporary file, then rename."""
        try:
            try:
                text = self.stats_path.read_text(encoding="utf-8")
            except FileNotFoundError:
                text = ""
            lines = [(str(line["date"]), json.dumps(line, separators=(",", ":")))]
            for raw in text.splitlines():
                document = _object(raw)
                day = document.get("date") if document is not None else None
                if isinstance(day, str) and day != line["date"]:
                    lines.append((day, raw.strip()))
            lines.sort(key=lambda item: item[0])
            data = "".join(f"{raw}\n" for _, raw in lines)
            self.state_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
            handle, temporary = tempfile.mkstemp(
                dir=self.state_dir, prefix=".stats-", suffix=".tmp"
            )
            try:
                with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as file:
                    file.write(data)
                    file.flush()
                    os.fsync(file.fileno())
                os.chmod(temporary, 0o600)
                os.replace(temporary, self.stats_path)
            except BaseException:
                with contextlib.suppress(OSError):
                    os.unlink(temporary)
                raise
        except OSError as exc:
            self._warn(STATS_FILE, exc)

    # --- access log -----------------------------------------------------------------

    def log(self, entry: Mapping[str, object]) -> None:
        """
        Append one line to the access log of the UTC day of ``entry["time"]``.

        Parameters
        ----------
        entry : Mapping
            The line: ``time`` (UTC, ISO 8601 with ``Z``) first; never an address.
        """
        day = str(entry["time"])[:10]
        line = json.dumps(entry, separators=(",", ":")) + "\n"
        with self._log_lock:
            try:
                file = self._log_file
                if file is None or self._log_day != day:
                    file = self._open_log(day)
                file.write(line)
                file.flush()
            except OSError as exc:
                self._warn(f"{LOG_DIR}/access-{day}.jsonl", exc)

    def _open_log(self, day: str) -> IO[str]:
        self._close_log()
        self.state_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.log_dir.mkdir(mode=0o700, exist_ok=True)
        path = self.log_dir / f"access-{day}.jsonl"
        flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, "O_BINARY", 0)
        handle = os.open(path, flags, 0o600)
        file = os.fdopen(handle, "a", encoding="utf-8", newline="\n")
        self._log_file, self._log_day = file, day
        self._prune_logs(date.fromisoformat(day))
        return file

    def _close_log(self) -> None:
        if self._log_file is not None:
            with contextlib.suppress(OSError):
                self._log_file.close()
        self._log_file = None
        self._log_day = None

    def _prune_logs(self, today: date) -> None:
        """Delete the access logs of days `LOG_DAYS` or more before ``today``."""
        oldest = today - timedelta(days=LOG_DAYS - 1)
        try:
            names = [path for path in self.log_dir.iterdir() if path.is_file()]
        except FileNotFoundError:
            return
        except OSError as exc:
            self._warn(LOG_DIR, exc)
            return
        for path in names:
            found = _LOG_NAME.fullmatch(path.name)
            if found is None:
                continue
            try:
                if date.fromisoformat(found[1]) < oldest:
                    path.unlink(missing_ok=True)
            except ValueError:
                continue
            except OSError as exc:
                self._warn(f"{LOG_DIR}/{path.name}", exc)

    # --- lifespan -------------------------------------------------------------------

    async def start(self) -> None:
        """Delete old access logs and rewrite the day's line every `FLUSH_INTERVAL_S`."""
        today = date.fromisoformat(_utc_day(self.clock()))
        await asyncio.to_thread(self._prune_under_lock, today)
        self._task = asyncio.create_task(self._run())

    def _prune_under_lock(self, today: date) -> None:
        with self._log_lock:
            self._prune_logs(today)

    async def _run(self) -> None:
        while True:
            await asyncio.sleep(FLUSH_INTERVAL_S)
            await asyncio.to_thread(self.flush)

    async def stop(self) -> None:
        """Stop the periodic rewrite, write the day's line and close the access log."""
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        await asyncio.to_thread(self.flush)
        with self._log_lock:
            self._close_log()

    @staticmethod
    def _warn(file: str, exc: OSError) -> None:
        _LOG.warning(
            "%s",
            message("gui.public.write_failed", file=file, reason=exc.strerror),
        )


def _object(raw: str) -> dict[str, object] | None:
    """A line of a JSON Lines file as an object, or None."""
    try:
        document = json.loads(raw)
    except ValueError:
        return None
    return document if isinstance(document, dict) else None


def _refusal(scope: Scope, kind: Kind, seconds: int) -> Response:
    """The ``429`` of a request over the limit: the error document or a short page."""
    request = Request(scope)
    if kind == "api":
        return error_response(
            request,
            GuiError(
                "rate_limited",
                message("gui.public.rate_limited", seconds=seconds),
                details={"retry_after": seconds},
                headers={"Retry-After": str(seconds)},
            ),
        )
    lang = page_lang(request)
    title = message("gui.errors.title_rate_limited", lang=lang)
    text = message("gui.public.rate_limited", lang=lang, seconds=seconds)
    page = _PAGE.format(
        lang=lang,
        title=escape(title),
        text=escape(text),
        tokens=escape(f"{scope.get('root_path', '')}/nogat/tokens.css"),
    )
    return Response(
        page,
        status_code=429,
        media_type="text/html",
        headers={
            "Retry-After": str(seconds),
            "Cache-Control": "no-store",
            "Content-Language": lang,
        },
    )


class Traffic:
    """
    ASGI middleware: rate limit, statistics and access log of every HTTP request.

    Parameters
    ----------
    app : ASGIApp
        The wrapped app.
    state : TrafficState
        What it counts and where it writes.
    """

    def __init__(self, app: ASGIApp, *, state: TrafficState) -> None:
        self.app = app
        self.state = state

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Serve one request: refused over the limit, counted and logged."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        state = self.state
        started = state.monotonic()
        moment = state.clock()
        path: str = scope["path"]
        root: str = scope.get("root_path", "")
        kind = classify(path[len(root) :] if root and path.startswith(root) else path)
        request_id = secrets.token_hex(8)
        user_agent = Headers(scope=scope).get("user-agent")
        status = 0
        size = 0

        async def send_with_id(event: Message) -> None:
            nonlocal status, size
            if event["type"] == "http.response.start":
                status = event["status"]
                MutableHeaders(scope=event)["X-Request-Id"] = request_id
            elif event["type"] == "http.response.body":
                size += len(event.get("body", b""))
            elif event["type"] == "http.response.pathsend":
                with contextlib.suppress(OSError):
                    size += os.path.getsize(event["path"])
            await send(event)

        try:
            if kind != "static":
                client = scope.get("client")
                address = str(client[0]) if client else ""
                state.visit(address, user_agent or "")
                wait = state.admit(address)
                if wait is not None:
                    await _refusal(scope, kind, wait)(scope, receive, send_with_id)
                    return
            await self.app(scope, receive, send_with_id)
        except BaseException:
            if status == 0:
                status = 500
            raise
        finally:
            if kind == "page" and status == 200:
                state.page_view()
            query = scope.get("query_string", b"").decode("latin-1")
            state.log(
                {
                    "time": datetime.fromtimestamp(moment, UTC)
                    .isoformat(timespec="milliseconds")
                    .replace("+00:00", "Z"),
                    "method": scope.get("method", ""),
                    "path": f"{path}?{query}" if query else path,
                    "status": status,
                    "size": size,
                    "duration_ms": round((state.monotonic() - started) * 1000, 3),
                    "request_id": request_id,
                    "user_agent": user_agent,
                }
            )
