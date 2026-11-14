"""
The public GUI's traffic: rate limit and daily statistics (Nogat DEV-15.9, DEV-15.11).

`Traffic` wraps the app as a pure ASGI middleware and `TrafficState` holds what it
counts. A request is an API call (``/api/…``), a page (the start page, the regulamin,
the manual, the admin page) or a static file, by its path relative to the mount.

- Rate limit (DEV-15.9): API calls and pages, not static files, of one client address
  (the one the proxy reports, put in place by uvicorn) are counted in a sliding window
  of ``window`` seconds; above ``limit`` the answer is ``429`` with ``Retry-After``,
  the error document ``rate_limited`` for an API call and a short page for a page. The
  address lives in memory only, for the window only.
- Statistics (DEV-15.11): a visitor is the HMAC-SHA-256 of the address and the
  User-Agent under a random 32-byte salt drawn at start and at each 00:00 UTC; salt and
  hashes stay in memory. Each UTC day is one line of ``<data_dir>/obserwator/stats.jsonl``
  (``date``, ``visitors``, ``page_views``, ``stations_opened``, ``analyses_run``,
  ``downloads``), rewritten atomically every `FLUSH_INTERVAL_S`, at the day's end and at
  shutdown; a restart adds to the day's line. The requests of the admin panel
  (DEV-15.13, `is_admin`) stay under the rate limit but are not counted.

The access log is not this module's: ``obserwator gui serve`` wraps the app in
`obserwator.nogat_logging.AccessLog`, outside `Traffic`, so the answers of the rate
limit are logged too (Nogat DEV-12.4 to DEV-12.8).
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
import secrets
import tempfile
import threading
import time
from collections import deque
from collections.abc import Callable, Mapping
from datetime import UTC, date, datetime
from html import escape
from pathlib import Path
from typing import Literal

from starlette.datastructures import Headers
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
ADMIN_PAGES = frozenset({"/admin", "/admin/", "/admin/index.html"})
"""The paths of the admin page (Nogat DEV-15.13), relative to the mount: pages the rate
limit counts and the statistics do not (`is_admin`)."""
STATS_FILE = "stats.jsonl"
FLUSH_INTERVAL_S = 300.0
"""How often the day's statistics line is rewritten [s] (DEV-15.11: at most 10 min)."""
SWEEP_INTERVAL_S = 1.0
"""How often addresses whose window has passed are forgotten [s]."""
SALT_BYTES = 32

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
        ``api`` below ``/api/``, ``page`` for one of `PAGES` and `ADMIN_PAGES`,
        ``static`` otherwise.
    """
    if path.startswith("/api/"):
        return "api"
    if (path or "/") in PAGES or path in ADMIN_PAGES:
        return "page"
    return "static"


def is_admin(path: str) -> bool:
    """
    Whether a request is the admin panel's (Nogat DEV-15.13), by its path.

    Parameters
    ----------
    path : str
        The path without the mount's prefix (``scope["root_path"]``).

    Returns
    -------
    bool
        True for ``/admin``, ``/api/admin`` and every path below them: the three
        paths a deployment protects, whose answers are never kept (``no-store``) and
        whose requests the statistics do not count (DEV-15.11).
    """
    return path in ("/admin", "/api/admin") or path.startswith(
        ("/admin/", "/api/admin/")
    )


def _utc_day(moment: float) -> str:
    return datetime.fromtimestamp(moment, UTC).date().isoformat()


def _is_day(value: object) -> bool:
    """Whether a value is a UTC day as ``stats.jsonl`` writes it, ``YYYY-MM-DD``."""
    if not isinstance(value, str) or len(value) != 10 or value[4::3] != "--":
        return False
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


def _count(value: object) -> int:
    """A number of a stored line: a whole number from 0, else 0."""
    return value if type(value) is int and value >= 0 else 0


class TrafficState:
    """
    The rate limit and the day's statistics of one GUI app.

    Parameters
    ----------
    limit : int
        At most this many counted requests of one address in ``window`` seconds.
    window : int
        The sliding window of the rate limit [s].
    directory : Path
        The GUI's own directory, ``<data_dir>/obserwator``: ``stats.jsonl`` goes there.
    writes : bool, optional
        Keep ``stats.jsonl`` (default); False keeps it off, so nothing under
        ``directory`` is read or written and the day's numbers stay in memory (GUI plan
        D7: ``directory`` overlaps the data root).
    clock : callable, optional
        Wall-clock time in seconds since the epoch (the UTC day).
    monotonic : callable, optional
        Monotonic time in seconds (the rate limit's window).
    """

    def __init__(
        self,
        *,
        limit: int,
        window: int,
        directory: Path,
        writes: bool = True,
        clock: Callable[[], float] = time.time,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.limit = limit
        self.window = window
        self.directory = directory
        self.stats_path = directory / STATS_FILE
        self.writes = writes
        self.clock = clock
        self.monotonic = monotonic
        self._lock = threading.Lock()  # windows, salt, visitors, counters
        self._io = threading.Lock()  # stats.jsonl; taken before _lock
        self._windows: dict[str, deque[float]] = {}
        self._swept = monotonic()
        self._day = _utc_day(clock())
        self._salt = secrets.token_bytes(SALT_BYTES)
        self._visitors: set[bytes] = set()
        self._counts = dict.fromkeys(COUNTERS, 0)
        self._base = self._read_line(self._day)
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

    def today(self) -> date:
        """The current UTC day, by the state's clock."""
        return datetime.fromtimestamp(self.clock(), UTC).date()

    def days(self, first: date, last: date) -> list[dict[str, str | int]]:
        """
        The days of ``stats.jsonl`` between two UTC days, the current one as counted so far.

        Parameters
        ----------
        first, last : date
            The first and the last UTC day, both included.

        Returns
        -------
        list of dict
            One line per day that has one, in date order: ``date`` and the numbers of
            `COUNTERS` (0 where a stored line lacks one or holds no whole number from
            0). The current day is `snapshot`'s, never its stored line, which lags
            behind; with `writes` off it is the only one.
        """
        self._roll()
        start, end = first.isoformat(), last.isoformat()
        found: dict[str, dict[str, str | int]] = {}
        with self._io:
            for raw in self._stored_lines():
                document = _object(raw)
                day = document.get("date") if document is not None else None
                if document is None or not _is_day(day) or not start <= str(day) <= end:
                    continue
                line: dict[str, str | int] = {"date": str(day)}
                line.update({key: _count(document.get(key)) for key in COUNTERS})
                found[str(day)] = line
            with self._lock:
                current = self._line()
        if start <= str(current["date"]) <= end:
            found[str(current["date"])] = current
        return [found[day] for day in sorted(found)]

    def _stored_lines(self) -> list[str]:
        """The lines of ``stats.jsonl``: none without it, with `writes` off or unreadable."""
        if not self.writes:
            return []
        try:
            return self.stats_path.read_text(encoding="utf-8").splitlines()
        except FileNotFoundError:
            return []
        except OSError as exc:
            self._warn(STATS_FILE, exc)
            return []

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

    def flush(self) -> None:
        """Rewrite the day's line of ``stats.jsonl`` (after a day change, if one is due)."""
        self._roll()
        with self._io:
            with self._lock:
                line = self._line()
            self._write_line(line)

    def _read_line(self, day: str) -> dict[str, int]:
        """The numbers of ``day`` in ``stats.jsonl``, written by an earlier run."""
        for raw in self._stored_lines():
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
        if not self.writes:
            return
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
            self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
            handle, temporary = tempfile.mkstemp(
                dir=self.directory, prefix=".stats-", suffix=".tmp"
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

    # --- lifespan -------------------------------------------------------------------

    async def start(self) -> None:
        """Rewrite the day's line every `FLUSH_INTERVAL_S` from now on."""
        self._task = asyncio.create_task(self._run())

    async def _run(self) -> None:
        while True:
            await asyncio.sleep(FLUSH_INTERVAL_S)
            await asyncio.to_thread(self.flush)

    async def stop(self) -> None:
        """Stop the periodic rewrite and write the day's line."""
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        await asyncio.to_thread(self.flush)

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
    """The ``429`` of a request over the limit, never kept: the error document or a short page."""
    request = Request(scope)
    if kind == "api":
        response = error_response(
            request,
            GuiError(
                "rate_limited",
                message("gui.public.rate_limited", seconds=seconds),
                details={"retry_after": seconds},
                headers={"Retry-After": str(seconds)},
            ),
        )
        response.headers["Cache-Control"] = "no-store"
        return response
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
    ASGI middleware: the rate limit and the statistics of every HTTP request.

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
        """Serve one request: refused over the limit, else counted (not the admin panel's)."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        state = self.state
        path: str = scope["path"]
        root: str = scope.get("root_path", "")
        relative = path[len(root) :] if root and path.startswith(root) else path
        kind = classify(relative)
        counted = not is_admin(relative)
        status = 0

        async def send_counted(event: Message) -> None:
            nonlocal status
            if event["type"] == "http.response.start":
                status = event["status"]
            await send(event)

        try:
            if kind != "static":
                client = scope.get("client")
                address = str(client[0]) if client else ""
                if counted:
                    state.visit(address, Headers(scope=scope).get("user-agent", ""))
                wait = state.admit(address)
                if wait is not None:
                    await _refusal(scope, kind, wait)(scope, receive, send)
                    return
            await self.app(scope, receive, send_counted)
        finally:
            if kind == "page" and counted and status == 200:
                state.page_view()
