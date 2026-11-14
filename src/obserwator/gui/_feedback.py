"""
„Zgłoś uwagę” of the public GUI (Nogat DEV-15.12): reports in ``<data_dir>/obserwator/feedback.jsonl``.

``POST api/feedback`` takes ``{"message": text, "context": {"view", "station",
"parameters"}}`` from the GUI's own page only, adds the app's version and stores one
JSON line ``{"id", "created_at", "message", "context", "is_read"}``: never an IP
address or a User-Agent. The address serves only the in-memory limit of `RATE_COUNT`
reports in `RATE_WINDOW_S`. The first report creates the file (directory 0700, file
0600); a line is written in one ``write`` under the file's lock (``flock``), and ids are
never reused: `NEXT_ID_FILE` beside it keeps the next one. The admin panel (DEV-15.13,
``obserwator.gui._admin``) lists the reports and marks or deletes one: the file is then
rewritten atomically, a temporary file renamed over it under the same lock, so a report
is never lost to a rewrite, also of another process.
"""

from __future__ import annotations

import contextlib
import json
import logging
import math
import os
import re
import sys
import tempfile
import threading
import time
from collections import deque
from collections.abc import Callable, Iterable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import Response

from obserwator.gui._http import GuiError, error_response, json_response
from obserwator.messages import message

if sys.platform != "win32":
    import fcntl

_LOG = logging.getLogger(__name__)

BODY_MAX_BYTES = 112 * 1024
"""The largest body of ``POST api/feedback`` [bytes]; above it the answer is ``413``."""
MESSAGE_MAX = 5000
"""The longest description, after stripping [characters]."""
CONTEXT_MAX_BYTES = 100_000
"""The largest stored context, as compact UTF-8 JSON [bytes]."""
PARAMETERS_MAX = 50
"""The most parameters of the view in a context."""
VIEWS = ("stations", "current", "pmaxtp")
"""The GUI's views."""
RATE_COUNT = 5
"""Reports of one address in `RATE_WINDOW_S`."""
RATE_WINDOW_S = 600.0
BODY_KEYS = frozenset({"message", "context"})
CONTEXT_KEYS = frozenset({"view", "station", "parameters"})
NEXT_ID_FILE = "feedback.next_id"
"""Beside ``feedback.jsonl``: the next report's id, written under its lock, so an id stays
given once its report is deleted (DEV-15.12: ascending); without it, the largest id in the
file plus one."""

_SURROGATE = re.compile("[\ud800-\udfff]")


class Feedback:
    """
    The reports of one GUI app and the limit of reports per address.

    Every read and write of the file takes its lock (``flock``: shared to read,
    exclusive to write), so the GUI's processes, and a person's ``flock``, take turns.

    Parameters
    ----------
    path : Path
        ``<data_dir>/obserwator/feedback.jsonl`` (`GuiConfig.gui_dir`).
    writes : bool, optional
        Take reports (default); False keeps them off: ``POST api/feedback`` answers
        ``forbidden``, the admin panel sees no report, and the file is neither read
        nor written (GUI plan D7: the GUI's own directory overlaps the data root).
    monotonic : callable, optional
        Monotonic time in seconds (the limit's window).
    """

    def __init__(
        self,
        path: Path,
        *,
        writes: bool = True,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.path = path
        self.next_id = path.with_name(NEXT_ID_FILE)
        self.writes = writes
        self.monotonic = monotonic
        self._lock = threading.Lock()  # the limit
        self._io = threading.Lock()  # the file, within this process
        self._times: dict[str, deque[float]] = {}

    def take(self, address: str) -> int | None:
        """
        Count a report of ``address`` against the limit.

        Parameters
        ----------
        address : str
            The client's address, kept in memory for the window only.

        Returns
        -------
        int or None
            None when the report is within the limit (it is then counted); else
            the whole seconds (at least 1) until the next one is accepted.
        """
        now = self.monotonic()
        with self._lock:
            self._times = {
                key: times
                for key, times in self._times.items()
                if times and now - times[-1] < RATE_WINDOW_S
            }
            times = self._times.setdefault(address, deque())
            while times and now - times[0] >= RATE_WINDOW_S:
                times.popleft()
            if len(times) >= RATE_COUNT:
                return max(1, math.ceil(times[0] + RATE_WINDOW_S - now))
            times.append(now)
            return None

    def append(self, text: str, context: Mapping[str, Any]) -> int:
        """
        Store a report as one line, its id never given before (`NEXT_ID_FILE`).

        Parameters
        ----------
        text : str
            The description, checked.
        context : Mapping
            The context, checked, with ``app_version``.

        Returns
        -------
        int
            The report's id.

        Raises
        ------
        OSError
            When the file cannot be read or written.
        """
        with self._io:
            self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            handle = _locked(self.path, os.O_RDWR | os.O_APPEND | os.O_CREAT)
            try:
                with open(handle, "rb", closefd=False) as file:
                    stored = _reports(file)
                largest = max((found["id"] for found in stored), default=0)
                number = max(largest + 1, self._issued())
                report = {
                    "id": number,
                    "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
                    "message": text,
                    "context": dict(context),
                    "is_read": False,
                }
                data = _encoded(report) + b"\n"
                written = os.write(handle, data)
                if written != len(data):
                    raise OSError(f"short write: {written} of {len(data)} bytes")
                os.fsync(handle)
                self._issue(number + 1)
            finally:
                os.close(handle)
        return number

    def reports(self) -> list[dict[str, Any]]:
        """
        The stored reports in the file's order (ascending ids).

        Returns
        -------
        list of dict
            Each line that is a JSON object with a positive whole-number ``id``, as
            stored; empty without the file or when reports are off (`writes`).

        Raises
        ------
        OSError
            When the file cannot be read.
        """
        if not self.writes:
            return []
        with self._io:
            try:
                handle = _locked(self.path, os.O_RDONLY, shared=True)
            except FileNotFoundError:
                return []
            try:
                with open(handle, "rb", closefd=False) as file:
                    lines = file.read().split(b"\n")
            finally:
                os.close(handle)
        return _reports(lines)

    def mark(self, report: int, is_read: bool) -> dict[str, Any] | None:
        """
        Mark a report read or unread, rewriting the file (`rewrite`).

        Parameters
        ----------
        report : int
            The report's id.
        is_read : bool
            Its new ``is_read``.

        Returns
        -------
        dict or None
            The report as now stored; None when no report has the id. A report that
            already has the value leaves the file untouched.

        Raises
        ------
        OSError
            When the file cannot be read or written.
        """
        found: dict[str, Any] | None = None

        def change(lines: list[bytes]) -> list[bytes] | None:
            nonlocal found
            changed = False
            for number, raw in enumerate(lines):
                document = _report(raw)
                if document is None or document["id"] != report:
                    continue
                if document.get("is_read") is not is_read:
                    document["is_read"] = is_read
                    lines[number] = _encoded(document)
                    changed = True
                found = document
            return lines if changed else None

        self.rewrite(change)
        return found

    def delete(self, report: int) -> bool:
        """
        Delete a report, rewriting the file (`rewrite`).

        Its id is never given again: `NEXT_ID_FILE` keeps the next one, also when
        the newest report goes.

        Parameters
        ----------
        report : int
            The report's id.

        Returns
        -------
        bool
            Whether a report had the id.

        Raises
        ------
        OSError
            When the file cannot be read or written.
        """
        deleted = False

        def change(lines: list[bytes]) -> list[bytes] | None:
            nonlocal deleted
            kept = [
                raw
                for raw in lines
                if (document := _report(raw)) is None or document["id"] != report
            ]
            deleted = len(kept) < len(lines)
            return kept if deleted else None

        self.rewrite(change)
        return deleted

    def rewrite(self, change: Callable[[list[bytes]], list[bytes] | None]) -> None:
        """
        Rewrite the file atomically under its lock.

        The new text goes to a temporary file beside it (``0600``), synced, then
        renamed over it while the lock of the old file is held, so a reader sees the
        old file or the new one, never a part, and a report waiting for the lock is
        appended to the new file (`_locked`). Lines nobody changed keep their bytes.

        Parameters
        ----------
        change : callable
            Takes the file's lines without their line ends and returns the new ones,
            or None to leave the file as it is. Not called without the file or when
            reports are off (`writes`).

        Raises
        ------
        OSError
            When the file cannot be read or written; it is then left as it was.
        """
        if not self.writes:
            return
        with self._io:
            try:
                handle = _locked(self.path, os.O_RDWR)
            except FileNotFoundError:
                return
            try:
                with open(handle, "rb", closefd=False) as file:
                    lines = file.read().split(b"\n")
                if lines[-1] == b"":
                    lines.pop()
                largest = max((found["id"] for found in _reports(lines)), default=0)
                if self._issued() <= largest:  # a file of an older GUI: no counter yet
                    self._issue(largest + 1)
                new = change(lines)
                if new is None:
                    return
                data = b"".join(raw + b"\n" for raw in new)
                temporary = _synced(self.path.parent, data)
                try:
                    if sys.platform == "win32":
                        # Windows renames over no open file: this process's lock holds
                        os.close(handle)
                        handle = -1
                    os.replace(temporary, self.path)
                except BaseException:
                    with contextlib.suppress(OSError):
                        os.unlink(temporary)
                    raise
            finally:
                if handle >= 0:
                    os.close(handle)

    def _issued(self) -> int:
        """The next id `NEXT_ID_FILE` holds; 0 without it or when it holds no number."""
        try:
            text = self.next_id.read_text(encoding="utf-8").strip()
        except (FileNotFoundError, UnicodeDecodeError):
            return 0
        return int(text) if text.isascii() and text.isdigit() else 0

    def _issue(self, number: int) -> None:
        """Keep ``number`` as the next id: a temporary file renamed over `NEXT_ID_FILE`."""
        temporary = _synced(self.path.parent, f"{number}\n".encode())
        try:
            os.replace(temporary, self.next_id)
        except BaseException:
            with contextlib.suppress(OSError):
                os.unlink(temporary)
            raise


def _locked(path: Path, flags: int, *, shared: bool = False) -> int:
    """
    ``path`` opened with ``flags`` and locked (POSIX ``flock``), the file the path names.

    A rewrite renames a new file over the path while it holds the lock of the old one,
    so a lock that comes once the path names another file is the old file's: the path
    is then opened and locked again. On Windows, without ``flock``, the instance's lock
    alone orders the reads and writes of one process.

    Parameters
    ----------
    path : Path
        The file.
    flags : int
        The flags of ``os.open`` (a new file gets mode ``0600``).
    shared : bool, optional
        A shared lock (to read) instead of an exclusive one (to write).

    Returns
    -------
    int
        The open, locked file descriptor; the caller closes it, which unlocks it.

    Raises
    ------
    OSError
        ``FileNotFoundError`` when the file does not exist and ``flags`` do not
        create it.
    """
    flags |= getattr(os, "O_BINARY", 0)
    while True:
        handle = os.open(path, flags, 0o600)
        if sys.platform == "win32":
            return handle
        try:
            fcntl.flock(handle, fcntl.LOCK_SH if shared else fcntl.LOCK_EX)
            if os.path.samestat(os.fstat(handle), os.stat(path)):
                return handle
        except FileNotFoundError:
            pass  # removed while this waited: open the path again
        except BaseException:
            os.close(handle)
            raise
        os.close(handle)


def _synced(directory: Path, data: bytes) -> str:
    """``data`` in a new temporary file of ``directory`` (``0600``), synced: its name."""
    handle, name = tempfile.mkstemp(dir=directory, prefix=".feedback-", suffix=".tmp")
    try:
        with os.fdopen(handle, "wb") as file:
            file.write(data)
            file.flush()
            os.fsync(file.fileno())
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(name)
        raise
    return name


def _encoded(report: Mapping[str, Any]) -> bytes:
    """A report as its line, compact UTF-8 JSON without the line end."""
    text = json.dumps(report, ensure_ascii=False, separators=(",", ":"))
    return _clean(text).encode("utf-8")


def _reports(lines: Iterable[bytes]) -> list[dict[str, Any]]:
    """The reports of stored lines, in their order; other lines left out."""
    return [found for found in map(_report, lines) if found is not None]


def _report(raw: bytes) -> dict[str, Any] | None:
    """The report of a stored line: a JSON object with a positive whole-number ``id``."""
    try:
        document = json.loads(raw)
    except ValueError:
        return None
    if not isinstance(document, dict):
        return None
    value = document.get("id")
    return document if type(value) is int and value > 0 else None


def _clean(text: str) -> str:
    """Lone surrogates, which UTF-8 cannot hold, as U+FFFD."""
    return _SURROGATE.sub("\ufffd", text)


def _invalid(text: str, **details: object) -> GuiError:
    return GuiError("validation_error", text, details=details)


def _no_constant(name: str) -> object:
    raise ValueError(name)


def parse(body: bytes) -> tuple[str, str, str | None, dict[str, Any]]:
    """
    Check a report's body.

    Parameters
    ----------
    body : bytes
        The body of ``POST api/feedback``.

    Returns
    -------
    tuple
        The description (stripped), the view, the station code or None, and the
        parameters of the view.

    Raises
    ------
    GuiError
        ``validation_error``: no JSON, another shape, a description out of 1 to
        `MESSAGE_MAX` characters, a context field that is no view, no text or no
        object of at most `PARAMETERS_MAX` text, number, boolean or null values.
    """
    try:
        document = json.loads(body, parse_constant=_no_constant)
    except (ValueError, RecursionError):
        raise _invalid(message("gui.public.feedback_not_json"), reason="json") from None
    if not isinstance(document, dict) or set(document) - BODY_KEYS:
        raise _invalid(message("gui.public.feedback_bad_shape"), reason="shape")
    text = document.get("message")
    if not isinstance(text, str) or not text.strip():
        raise _invalid(
            message("gui.public.feedback_empty"), option="message", reason="empty"
        )
    text = _clean(text.strip())
    if len(text) > MESSAGE_MAX:
        raise _invalid(
            message("gui.public.feedback_too_long", maximum=MESSAGE_MAX),
            option="message",
            reason="too_long",
            maximum=MESSAGE_MAX,
        )
    context = document.get("context")
    if not isinstance(context, dict) or set(context) - CONTEXT_KEYS:
        raise _invalid(message("gui.public.feedback_bad_shape"), reason="shape")
    view = context.get("view")
    if view not in VIEWS:
        raise _invalid(
            message("gui.public.feedback_bad_context", field="view"),
            option="view",
            allowed=list(VIEWS),
        )
    station = context.get("station")
    if station is not None and (not isinstance(station, str) or not station):
        raise _invalid(
            message("gui.public.feedback_bad_context", field="station"),
            option="station",
        )
    parameters = context.get("parameters", {})
    if not isinstance(parameters, dict) or not all(
        value is None or isinstance(value, str | int | float | bool)
        for value in parameters.values()
    ):
        raise _invalid(
            message("gui.public.feedback_bad_context", field="parameters"),
            option="parameters",
        )
    if len(parameters) > PARAMETERS_MAX:
        raise _invalid(
            message("gui.public.feedback_too_many_parameters", maximum=PARAMETERS_MAX),
            option="parameters",
            reason="too_many",
            maximum=PARAMETERS_MAX,
        )
    parameters = {
        _clean(key): _clean(value) if isinstance(value, str) else value
        for key, value in parameters.items()
    }
    return text, str(view), _clean(station) if station else None, parameters


def _same_origin(request: Request) -> bool:
    """Whether this GUI's page sent the request: ``Sec-Fetch-Site``, else ``Origin``."""
    site = request.headers.get("sec-fetch-site")
    if site is not None:
        return site == "same-origin"
    origin = request.headers.get("origin")
    host = request.headers.get("host", "")
    return origin is not None and origin == f"{request.url.scheme}://{host}"


async def read_body(request: Request, limit: int = BODY_MAX_BYTES) -> bytes | None:
    """The body, read in chunks; None when it is larger than ``limit`` bytes."""
    length = request.headers.get("content-length", "")
    if length.isdigit() and int(length) > limit:
        return None
    body = bytearray()
    async for chunk in request.stream():
        body += chunk
        if len(body) > limit:
            return None
    return bytes(body)


async def post_feedback(request: Request) -> Response:
    """
    ``POST api/feedback``: store a report of „Zgłoś uwagę” (DEV-15.12).

    Parameters
    ----------
    request : Request
        ``application/json`` ``{"message": text, "context": {"view", "station",
        "parameters"}}`` from the GUI's own page, at most `BODY_MAX_BYTES`.

    Returns
    -------
    Response
        ``{"id": <id>, "status": "ok"}``; else the error document: ``forbidden``
        (403) from another site or when reports are off (``details.reason``
        ``feedback_off``), ``validation_error`` (400; ``413`` for a body too
        large, ``details.reason`` ``content_type`` for another media type),
        ``rate_limited`` (429 with ``Retry-After``) above `RATE_COUNT` reports of
        one address in `RATE_WINDOW_S`, ``io_error`` (500) when the file cannot be
        written.
    """
    state = request.app.state.gui
    try:
        if not state.feedback.writes:
            raise GuiError(
                "forbidden",
                message("gui.errors.feedback_off"),
                details={"reason": "feedback_off"},
            )
        if not _same_origin(request):
            raise GuiError("forbidden", message("gui.public.feedback_forbidden"))
        media = request.headers.get("content-type", "").split(";")[0].strip().lower()
        if media != "application/json":
            raise _invalid(
                message("gui.public.feedback_content_type"), reason="content_type"
            )
        body = await read_body(request)
        if body is None:
            response = error_response(
                request,
                _invalid(
                    message(
                        "gui.public.feedback_too_large", limit=BODY_MAX_BYTES // 1024
                    ),
                    reason="too_large",
                    maximum=BODY_MAX_BYTES,
                ),
            )
            response.status_code = 413
            return response
        text, view, station, parameters = parse(body)
        if station is not None:
            features = await run_in_threadpool(lambda: state.root.snapshot().features)
            if station not in features:
                raise _invalid(
                    message("gui.public.feedback_unknown_station", station=station),
                    option="station",
                    reason="unknown",
                )
        context = {
            "view": view,
            "station": station,
            "parameters": parameters,
            "app_version": str(state.version),
        }
        if _utf8_size(context) > CONTEXT_MAX_BYTES:
            raise _invalid(
                message(
                    "gui.public.feedback_context_too_large",
                    maximum=CONTEXT_MAX_BYTES // 1000,
                ),
                option="context",
                reason="too_large",
                maximum=CONTEXT_MAX_BYTES,
            )
        wait = state.feedback.take(request.client.host if request.client else "")
        if wait is not None:
            raise GuiError(
                "rate_limited",
                message("gui.public.feedback_rate_limited", seconds=wait),
                details={"retry_after": wait},
                headers={"Retry-After": str(wait)},
            )
        try:
            report = await run_in_threadpool(state.feedback.append, text, context)
        except OSError as exc:
            _LOG.warning(
                "%s",
                message(
                    "gui.public.write_failed",
                    file=state.feedback.path.name,
                    reason=exc.strerror or str(exc),
                ),
            )
            raise GuiError(
                "io_error", message("gui.public.feedback_io_error")
            ) from None
    except GuiError as exc:
        return error_response(request, exc)
    return json_response(request, {"id": report, "status": "ok"})


def _utf8_size(document: object) -> int:
    """The size of a document as compact UTF-8 JSON [bytes]."""
    text = json.dumps(document, ensure_ascii=False, separators=(",", ":"))
    return len(text.encode("utf-8"))
