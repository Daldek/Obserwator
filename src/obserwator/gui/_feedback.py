"""
„Zgłoś uwagę” of the public GUI (Nogat DEV-15.12): reports in ``<data_dir>/obserwator/feedback.jsonl``.

``POST api/feedback`` takes ``{"message": text, "context": {"view", "station",
"parameters"}}`` from the GUI's own page only, adds the app's version and stores one
JSON line ``{"id", "created_at", "message", "context", "is_read"}``: never an IP
address or a User-Agent. The address serves only the in-memory limit of `RATE_COUNT`
reports in `RATE_WINDOW_S`. The first report creates the file (directory 0700, file
0600); a line is written in one ``write`` under a lock. There are no admin routes: the
operator reads the file with ``jq``.
"""

from __future__ import annotations

import json
import logging
import math
import os
import re
import sys
import threading
import time
from collections import deque
from collections.abc import Callable, Mapping
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

_SURROGATE = re.compile("[\ud800-\udfff]")


class Feedback:
    """
    The reports of one GUI app and the limit of reports per address.

    Parameters
    ----------
    path : Path
        ``<data_dir>/obserwator/feedback.jsonl`` (`GuiConfig.gui_dir`).
    writes : bool, optional
        Take reports (default); False keeps them off: ``POST api/feedback`` answers
        ``forbidden`` and nothing is written (GUI plan D7: the GUI's own directory
        overlaps the data root).
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
        self.writes = writes
        self.monotonic = monotonic
        self._lock = threading.Lock()
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
        Store a report as one line: its id is one more than the largest in the file.

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
        with self._lock:
            self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            flags = os.O_RDWR | os.O_APPEND | os.O_CREAT | getattr(os, "O_BINARY", 0)
            handle = os.open(self.path, flags, 0o600)
            try:
                if sys.platform != "win32":
                    fcntl.flock(handle, fcntl.LOCK_EX)
                with open(handle, "rb", closefd=False) as file:
                    largest = max(map(_id_of, file), default=0)
                report = {
                    "id": largest + 1,
                    "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
                    "message": text,
                    "context": dict(context),
                    "is_read": False,
                }
                line = json.dumps(report, ensure_ascii=False, separators=(",", ":"))
                data = (line + "\n").encode("utf-8")
                written = os.write(handle, data)
                if written != len(data):
                    raise OSError(f"short write: {written} of {len(data)} bytes")
                os.fsync(handle)
            finally:
                os.close(handle)
        return largest + 1


def _id_of(raw: bytes) -> int:
    """The id of a stored line, 0 for a line that has none."""
    try:
        document = json.loads(raw)
    except ValueError:
        return 0
    value = document.get("id") if isinstance(document, dict) else None
    return value if type(value) is int else 0


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


async def _body(request: Request) -> bytes | None:
    """The body, read in chunks; None when it is larger than `BODY_MAX_BYTES`."""
    length = request.headers.get("content-length", "")
    if length.isdigit() and int(length) > BODY_MAX_BYTES:
        return None
    body = bytearray()
    async for chunk in request.stream():
        body += chunk
        if len(body) > BODY_MAX_BYTES:
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
        body = await _body(request)
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
