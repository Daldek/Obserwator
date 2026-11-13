"""„Zgłoś uwagę”: the reports of the mockup's users, one JSON object per line.

After Hydrolog's GUI (``hydrolog.gui._feedback``) and Hydrograf, with the author's
decision of 2026-11-13: a report is the text (1 to 4000 characters) and the automatic
context the page shows before sending (the view, the station, the section, the address)
plus the app's version, added by the server. No contact fields, no IP address and no
``User-Agent`` are stored; the IP serves only the in-memory rate limit (`RateLimit`).

The file is ``OBSERWATOR_MOCKUP_FEEDBACK``, else ``<data_dir>/obserwator/feedback/reports.jsonl``
(Nogat's ``data_dir``, DEV-18.2); the first report creates it (directory 0700, file 0600).
A line is written with one ``write`` under a thread lock and an exclusive ``flock``, so
concurrent requests and processes never interleave. Reports stay until the operator
removes them.
"""

from __future__ import annotations

import fcntl
import json
import os
import re
import threading
import time
import uuid
from collections import deque
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from obserwator.config import settings

SCHEMA = "obserwator-mockup-feedback/1"
MESSAGE_MAX = 4000
BODY_MAX_BYTES = 8 * 1024
"""The largest body of ``POST api/feedback`` [bytes]."""
ADDRESS_MAX = 500
TITLE_MAX = 120
VIEWS = ("stations", "current", "pmaxtp")
RATE_COUNT = 5
"""Reports per address in `RATE_WINDOW_S`."""
RATE_WINDOW_S = 600.0

_SURROGATE = re.compile("[\ud800-\udfff]")
_CONTROL = re.compile("[\x00-\x1f\x7f]")
_SECTION = re.compile("[a-z0-9_-]{1,40}")
_CONTEXT_KEYS = {"view", "station", "section", "section_title", "address"}
_BODY_KEYS = {"message", "context"}


class Invalid(ValueError):
    """A body that is no report; the text is Polish, for the page."""


def path() -> Path:
    """The file of the reports."""
    chosen = os.environ.get("OBSERWATOR_MOCKUP_FEEDBACK")
    if chosen:
        return Path(chosen).expanduser()
    return settings.data_dir.expanduser() / "obserwator" / "feedback" / "reports.jsonl"


def _clean(text: str) -> str:
    """Lone surrogates, which UTF-8 cannot hold, as U+FFFD."""
    return _SURROGATE.sub("\ufffd", text)


def _line(value: object, name: str, maximum: int) -> str | None:
    """An optional one-line text of the context."""
    if value is None:
        return None
    if not isinstance(value, str) or not value or len(value) > maximum or _CONTROL.search(value):
        raise Invalid(f"Pole kontekstu „{name}” jest niepoprawne.")
    return _clean(value)


def parse(body: object, stations: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Check a report's body: ``{"message": str, "context": {...}}``.

    Parameters
    ----------
    body : object
        The decoded JSON.
    stations : dict
        The catalog's stations by code; a station of the context must be one of them.

    Returns
    -------
    tuple of str and dict
        The text, stripped, and the context with the station's name added.

    Raises
    ------
    Invalid
        On an unknown field, a wrong type, a text out of 1 to 4000 characters, a view
        not in `VIEWS`, an unknown station, a section that is no section id, or an
        address that is no path of this page.
    """
    if not isinstance(body, dict) or set(body) - _BODY_KEYS:
        raise Invalid("Zgłoszenie ma niepoprawną postać.")
    message = body.get("message")
    if not isinstance(message, str) or not message.strip():
        raise Invalid("Opis nie może być pusty.")
    message = _clean(message.strip())
    if len(message) > MESSAGE_MAX:
        raise Invalid(f"Opis może mieć najwyżej {MESSAGE_MAX} znaków.")
    raw = body.get("context")
    if not isinstance(raw, dict) or set(raw) - _CONTEXT_KEYS:
        raise Invalid("Kontekst zgłoszenia ma niepoprawną postać.")
    view = raw.get("view")
    if view not in VIEWS:
        raise Invalid("Pole kontekstu „view” jest niepoprawne.")
    context: dict[str, Any] = {"view": view}
    station = _line(raw.get("station"), "station", 40)
    if station is not None:
        if station not in stations:
            raise Invalid("Nie ma takiej stacji w katalogu.")
        context["station"] = station
        context["station_name"] = stations[station].get("name")
    section = _line(raw.get("section"), "section", 40)
    if section is not None:
        if not _SECTION.fullmatch(section):
            raise Invalid("Pole kontekstu „section” jest niepoprawne.")
        context["section"] = section
        title = _line(raw.get("section_title"), "section_title", TITLE_MAX)
        if title is not None:
            context["section_title"] = title
    address = _line(raw.get("address"), "address", ADDRESS_MAX)
    if address is not None:
        if not address.startswith("/") or address.startswith("//"):
            raise Invalid("Pole kontekstu „address” jest niepoprawne.")
        context["address"] = address
    return message, context


class RateLimit:
    """At most `RATE_COUNT` reports per address in `RATE_WINDOW_S`, in memory only."""

    def __init__(self, count: int = RATE_COUNT, window: float = RATE_WINDOW_S) -> None:
        self.count = count
        self.window = window
        self._lock = threading.Lock()
        self._times: dict[str, deque[float]] = {}

    def take(self, key: str) -> float | None:
        """Count a report of ``key``; when over the limit, the seconds until the next one."""
        now = time.monotonic()
        with self._lock:
            if len(self._times) > 10_000:
                self._times = {k: v for k, v in self._times.items() if v and now - v[-1] < self.window}
            times = self._times.setdefault(key, deque())
            while times and now - times[0] >= self.window:
                times.popleft()
            if len(times) >= self.count:
                return self.window - (now - times[0])
            times.append(now)
            return None


_WRITE = threading.Lock()


def append(message: str, context: dict[str, Any], version: dict[str, Any]) -> dict[str, Any]:
    """Append one report to the file; return it.

    Raises
    ------
    OSError
        If the file cannot be written.
    """
    report = {
        "schema": SCHEMA,
        "id": str(uuid.uuid4()),
        "created_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "version": version,
        "context": context,
        "message": message,
    }
    data = (json.dumps(report, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
    target = path()
    with _WRITE:
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        descriptor = os.open(target, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            written = os.write(descriptor, data)
            if written != len(data):
                raise OSError(f"short write: {written} of {len(data)} bytes")
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    return report
