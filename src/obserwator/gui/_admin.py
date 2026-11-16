"""
The GUI's admin panel (Nogat DEV-15.13, ECO-067, ADR-020): ``admin/`` and ``api/admin/…``.

The page ``admin/`` is the shell ``<nogat-admin>`` of Nogat's kit with „Zgłoszenia”,
„Statystyki” and „Stan” (``gui/web/admin/index.html``); ``admin`` answers ``308`` to
it. Every route under ``api/admin/`` first checks the header ``X-Admin-Key``, in
constant time, against the key read on every request (`configured_key`):
``OBSERWATOR_ADMIN_API_KEY``, else the text of the file ``OBSERWATOR_ADMIN_API_KEY_FILE``
names. A refusal is ``401`` with the error document of ``unauthorized`` and
``details.reason`` ``admin_key_not_configured``, ``admin_key_missing`` or
``admin_key_invalid``; no key is generated and none is logged.

- ``GET api/admin/feedback?limit=&offset=``: the reports of ``feedback.jsonl``, newest
  first, with ``total`` and ``unread_count``.
- ``PATCH api/admin/feedback/{id}`` with ``{"is_read": bool}`` (the report) and
  ``DELETE api/admin/feedback/{id}`` (``{"status": "deleted"}``): the file rewritten
  atomically under its lock (`Feedback.rewrite`); an unknown id is ``404``.
- ``GET api/admin/stats?from=&to=``: the days of ``stats.jsonl`` between two UTC days,
  the last `STATS_DAYS` by default, with the current one as counted so far, and
  ``totals`` of every number but ``visitors``.
- ``GET api/admin/status``: the app, its version, start and uptime, its own directory
  with the free space of its disk, and the checks of `CHECKS`.

Every answer of the panel is ``Cache-Control: no-store`` under the CSP ``'self'``
(`obserwator.gui._app.SecurityHeaders`), and its requests count against the rate limit
but not in the statistics (`obserwator.gui._traffic.is_admin`). The key is not one of
the REST API keys of ``obserwator admin`` (``api_keys.json``), which the GUI never reads.
"""

from __future__ import annotations

import hmac
import json
import logging
import re
import shutil
import time
from collections.abc import Awaitable, Callable
from datetime import timedelta
from pathlib import Path

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import RedirectResponse, Response

from obserwator._hydrolog import open_hydrolog
from obserwator.config import Settings
from obserwator.datasets import get_provider
from obserwator.exceptions import ObserwatorError
from obserwator.gui import _params as params
from obserwator.gui._feedback import read_body
from obserwator.gui._http import GuiError, error_response, json_response, page_lang
from obserwator.gui._root import Snapshot, Version
from obserwator.gui._state import GuiState
from obserwator.gui._traffic import COUNTERS
from obserwator.messages import Lang, message
from obserwator.output import DATA_MARKER

_LOG = logging.getLogger(__name__)

APP = "Obserwator"
"""The app's name in ``api/admin/status``."""
KEY_HEADER = "X-Admin-Key"
"""The header that carries the admin key."""
FEEDBACK_LIMIT = 50
"""The reports of a page of ``api/admin/feedback`` by default."""
FEEDBACK_LIMIT_MAX = 200
"""The most reports of a page of ``api/admin/feedback``."""
STATS_DAYS = 30
"""The days of ``api/admin/stats`` by default, up to today included."""
BODY_MAX_BYTES = 1024
"""The largest body of ``PATCH api/admin/feedback/{id}`` [bytes]."""
CHECKS = ("data_root_marker", "stored_analyses", "hydrolog_command")
"""The checks of ``api/admin/status``, in their order: the data root's marker
(``failed`` without it or when the root cannot be read), Hydrolog's stored analyses
(``warning`` when a provider with a catalog has none) and Hydrolog's program
(``warning`` when the server started without it, ``failed`` when it does not answer)."""

_REPORT_ID = re.compile(r"[0-9]{1,18}")

Handler = Callable[[Request], Awaitable[Response]]


def _state(request: Request) -> GuiState:
    state: GuiState = request.app.state.gui
    return state


# --- the key -------------------------------------------------------------------------


def configured_key() -> str | None:
    """
    The admin key now: ``OBSERWATOR_ADMIN_API_KEY``, else the file of ``…_FILE``.

    Read on every request (DEV-15.13), so a new key, or a new key file, applies at
    once; from the environment and ``.env`` only, never from ``nogat.toml`` (DEV-18.4).

    Returns
    -------
    str or None
        The key without surrounding white space; None when neither variable gives
        one: both unset or blank, or the file missing, unreadable, not UTF-8 or
        blank.
    """
    current = Settings()
    if current.admin_api_key is not None:
        key = current.admin_api_key.get_secret_value().strip()
        if key:
            return key
    if current.admin_api_key_file is None:
        return None
    try:
        text = current.admin_api_key_file.expanduser().read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    return text.strip() or None


def refusal(supplied: str | None, expected: str | None) -> GuiError | None:
    """
    The ``401`` of a request without the admin key, None with it.

    Parameters
    ----------
    supplied : str or None
        The header ``X-Admin-Key`` as Starlette decodes it (Latin-1).
    expected : str or None
        The configured key (`configured_key`).

    Returns
    -------
    GuiError or None
        ``unauthorized`` with ``details.reason`` ``admin_key_not_configured``,
        ``admin_key_missing`` or ``admin_key_invalid``; None for the key, compared
        in constant time with the bytes the client sent.
    """
    if expected is None:
        reason, text = (
            "admin_key_not_configured",
            message("gui.admin.key_not_configured"),
        )
    elif not supplied:
        reason, text = "admin_key_missing", message("gui.admin.key_missing")
    elif not hmac.compare_digest(supplied.encode("latin-1"), expected.encode("utf-8")):
        reason, text = "admin_key_invalid", message("gui.admin.key_invalid")
    else:
        return None
    return GuiError("unauthorized", text, details={"reason": reason})


def admin_route(handler: Handler) -> Handler:
    """A route of the admin API: the key checked before anything, every error the error document."""

    async def wrapped(request: Request) -> Response:
        try:
            expected = await run_in_threadpool(configured_key)
            refused = refusal(request.headers.get(KEY_HEADER), expected)
            if refused is not None:
                raise refused
            return await handler(request)
        except (GuiError, ObserwatorError) as exc:
            return error_response(request, exc, _state(request).directories())

    wrapped.__name__ = handler.__name__
    wrapped.__doc__ = handler.__doc__
    return wrapped


# --- the page ------------------------------------------------------------------------


async def admin_page(request: Request) -> Response:
    """``admin``: ``308`` to the admin page ``admin/``, relative, so any prefix holds."""
    query = request.url.query
    return RedirectResponse("admin/" + (f"?{query}" if query else ""), status_code=308)


@admin_route
async def admin_not_found(request: Request) -> Response:
    """Any other address of the admin API: ``404``, once the key is checked."""
    raise GuiError("not_found", message("gui.errors.not_found", path=request.url.path))


# --- reports -------------------------------------------------------------------------


async def _on_file[T](request: Request, call: Callable[[], T]) -> T:
    """``call`` on ``feedback.jsonl`` in a worker thread; a failed read or write is ``io_error``."""
    feedback = _state(request).feedback
    try:
        return await run_in_threadpool(call)
    except OSError as exc:
        _LOG.warning(
            "%s",
            message(
                "gui.public.write_failed",
                file=feedback.path.name,
                reason=exc.strerror or str(exc),
            ),
        )
        raise GuiError("io_error", message("gui.admin.reports_io_error")) from None


@admin_route
async def admin_feedback(request: Request) -> Response:
    """``GET api/admin/feedback?limit=&offset=``: the reports, newest first, and their counts."""
    query = request.query_params
    params.only(query, ("limit", "offset"))
    limit = (
        params.integer(
            query.get("limit"),
            "limit",
            minimum=1,
            maximum=FEEDBACK_LIMIT_MAX,
            default=FEEDBACK_LIMIT,
        )
        or FEEDBACK_LIMIT
    )
    offset = params.integer(query.get("offset"), "offset", minimum=0, default=0) or 0
    stored = await _on_file(request, _state(request).feedback.reports)
    newest = sorted(stored, key=lambda report: int(report["id"]), reverse=True)
    return json_response(
        request,
        {
            "items": newest[offset : offset + limit],
            "total": len(newest),
            "unread_count": sum(report.get("is_read") is not True for report in newest),
        },
    )


def _is_read(content_type: str, body: bytes | None) -> bool:
    """The ``is_read`` of a report's change, ``{"is_read": bool}`` as JSON, checked."""
    if content_type.split(";")[0].strip().lower() != "application/json":
        raise GuiError(
            "validation_error",
            message("gui.admin.report_content_type"),
            details={"reason": "content_type"},
        )
    try:
        document = json.loads(body) if body is not None else None
    except (ValueError, RecursionError):
        document = None
    if not isinstance(document, dict) or set(document) != {"is_read"}:
        document = None
    value = document.get("is_read") if document is not None else None
    if type(value) is not bool:
        raise GuiError(
            "validation_error",
            message("gui.admin.report_bad_body"),
            details={"option": "is_read", "reason": "shape"},
        )
    return value


@admin_route
async def admin_report(request: Request) -> Response:
    """
    ``PATCH api/admin/feedback/{id}`` with ``{"is_read": bool}``, and ``DELETE``.

    PATCH answers the report as now stored, DELETE ``{"status": "deleted"}``; both
    rewrite ``feedback.jsonl`` (`Feedback.mark`, `Feedback.delete`), and an id no
    report has is ``404 not_found``.
    """
    params.only(request.query_params, ())
    given = str(request.path_params["id"])[: params.MAX_TEXT]
    unknown = GuiError(
        "not_found",
        message("gui.admin.no_report", report=given),
        details={"id": given},
    )
    if not _REPORT_ID.fullmatch(given):
        raise unknown
    number = int(given)
    feedback = _state(request).feedback
    if request.method == "DELETE":
        if not await _on_file(request, lambda: feedback.delete(number)):
            raise unknown
        return json_response(request, {"status": "deleted"})
    body = await read_body(request, BODY_MAX_BYTES)
    is_read = _is_read(request.headers.get("content-type", ""), body)
    marked = await _on_file(request, lambda: feedback.mark(number, is_read))
    if marked is None:
        raise unknown
    return json_response(request, marked)


# --- statistics ----------------------------------------------------------------------


@admin_route
async def admin_stats(request: Request) -> Response:
    """``GET api/admin/stats?from=&to=``: the days of ``stats.jsonl`` and their totals."""
    query = request.query_params
    params.only(query, ("from", "to"))
    traffic = _state(request).traffic
    last = params.iso_date(query.get("to"), "to") or traffic.today()
    first = params.iso_date(query.get("from"), "from") or last - timedelta(
        days=STATS_DAYS - 1
    )
    if first > last:
        raise params.invalid(
            "from",
            query.get("from"),
            "range",
            maximum=last.isoformat(),
            option_after="to",
        )
    days = await run_in_threadpool(traffic.days, first, last)
    totals = {
        key: sum(int(day[key]) for day in days) for key in COUNTERS if key != "visitors"
    }
    return json_response(request, {"days": days, "totals": totals})


# --- status --------------------------------------------------------------------------


def _check(name: str, status: str, detail: str) -> dict[str, str]:
    return {"name": name, "status": status, "detail": str(detail)}


def _unreadable(name: str, error: ObserwatorError, lang: Lang) -> dict[str, str]:
    text = message(
        "gui.admin.check_root_unreadable", lang=lang, error=error.localized(lang)
    )
    return _check(name, "failed", text)


def _marker_check(root: Path, snapshot: Snapshot, lang: Lang) -> dict[str, str]:
    """``data_root_marker``: the data root has its marker and can be read."""
    name = CHECKS[0]
    if not (root / DATA_MARKER).is_file():
        text = message("gui.admin.check_marker_missing", lang=lang, root=str(root))
        return _check(name, "failed", text)
    if snapshot.error is not None:
        return _unreadable(name, snapshot.error, lang)
    text = message(
        "gui.admin.check_marker_ok",
        lang=lang,
        root=str(root),
        stations=len(snapshot.features),
    )
    return _check(name, "ok", text)


def _stored(provider: str, version: Version) -> str:
    """A provider's stored analyses: its name, the version and Hydrolog's version."""
    shown = f"{get_provider(provider).short_name} {version.label}"
    return f"{shown} (Hydrolog {version.hydrolog})" if version.hydrolog else shown


def _analyses_check(snapshot: Snapshot, lang: Lang) -> dict[str, str]:
    """``stored_analyses``: every provider with a catalog has analyses stored (ADR-016)."""
    name = CHECKS[1]
    if snapshot.error is not None:
        return _unreadable(name, snapshot.error, lang)
    stored = snapshot.analyses
    if not stored:
        return _check(
            name, "warning", message("gui.admin.check_analyses_none", lang=lang)
        )
    versions = ", ".join(_stored(provider, stored[provider]) for provider in stored)
    missing = [provider for provider in snapshot.catalogs if provider not in stored]
    if missing:
        text = message(
            "gui.admin.check_analyses_partial",
            lang=lang,
            versions=versions,
            providers=", ".join(get_provider(p).short_name for p in missing),
        )
        return _check(name, "warning", text)
    text = message("gui.admin.check_analyses_ok", lang=lang, versions=versions)
    return _check(name, "ok", text)


def _hydrolog_check(state: GuiState, lang: Lang) -> dict[str, str]:
    """``hydrolog_command``: Hydrolog's program, found at the start, answers now."""
    name = CHECKS[2]
    if not state.analyses.can_compute:
        text = message("gui.admin.check_hydrolog_missing", lang=lang)
        return _check(name, "warning", text)
    try:
        version = open_hydrolog().version
    except ObserwatorError as exc:
        text = message(
            "gui.admin.check_hydrolog_failed", lang=lang, error=exc.localized(lang)
        )
        return _check(name, "failed", text)
    text = message("gui.admin.check_hydrolog_ok", lang=lang, version=str(version))
    return _check(name, "ok", text)


def _checks(state: GuiState, lang: Lang) -> list[dict[str, str]]:
    """The checks of `CHECKS`, their details in ``lang``."""
    snapshot = state.root.snapshot()
    return [
        _marker_check(state.config.root, snapshot, lang),
        _analyses_check(snapshot, lang),
        _hydrolog_check(state, lang),
    ]


def _disk(directory: Path) -> dict[str, int | None]:
    """The free and the total bytes of the disk of ``directory`` or its nearest parent."""
    for candidate in (directory, *directory.parents):
        try:
            usage = shutil.disk_usage(candidate)
        except FileNotFoundError:
            continue
        except OSError:
            break
        return {"free_bytes": usage.free, "total_bytes": usage.total}
    return {"free_bytes": None, "total_bytes": None}


@admin_route
async def admin_status(request: Request) -> Response:
    """``GET api/admin/status``: the app, its start, its directory and disk, the checks."""
    params.only(request.query_params, ())
    state = _state(request)
    checks = await run_in_threadpool(_checks, state, page_lang(request))
    directory = state.config.gui_dir
    return json_response(
        request,
        {
            "app": APP,
            "version": state.version,
            "started_at": state.started_at.isoformat(timespec="seconds"),
            "uptime_s": int(time.monotonic() - state.started),
            "data_dir": str(directory),
            "disk": await run_in_threadpool(_disk, directory),
            "checks": checks,
        },
    )
