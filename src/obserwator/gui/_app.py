"""
The GUI's Starlette app: the page, its private API and its admin panel.

The private API answers GET and HEAD and ``POST api/feedback``; the admin panel is
``admin/`` with ``api/admin/…`` (Nogat DEV-15.13, `obserwator.gui._admin`). Routes are
relative to the page, so the app works at ``/`` and mounted under any prefix (GUI plan
D5, D6). They serve this GUI only: no ``/api/v1``, no OpenAPI, no stability promise (a
deviation from AGI-6.1 recorded in ``CLAUDE.md``). Every parameter is checked before
the data root or Hydrolog is touched; an error is ``obserwator-error/1`` with the
registry's status, in the page's language, without server paths.
"""

from __future__ import annotations

import asyncio
import contextlib
import csv
import functools
import io
import logging
import mimetypes
import re
import shlex
import shutil
import tempfile
import weakref
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from datetime import date
from functools import partial
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from anyio import CapacityLimiter, to_thread
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.gzip import GZipMiddleware
from starlette.requests import Request
from starlette.responses import FileResponse, Response
from starlette.routing import Mount, Route
from starlette.types import ASGIApp, Message, Receive, Scope, Send

import obserwator
from obserwator._borders import CZECHIA, POLAND
from obserwator._file_names import (
    analyses_file_name,
    pmaxtp_file_name,
    series_file_name,
    stations_file_name,
)
from obserwator._http_headers import security_headers
from obserwator.attribution import (
    ORIGINS,
    Attribution,
    Origin,
    attribution,
    border_origin,
    dataset_origin,
    provider_origin,
)
from obserwator.config import check_credentials
from obserwator.datasets import KINDS, Kind, get_dataset, get_provider, providers
from obserwator.exceptions import ObserwatorError
from obserwator.gui import _params as params
from obserwator.gui._admin import (
    admin_feedback,
    admin_not_found,
    admin_page,
    admin_report,
    admin_stats,
    admin_status,
)
from obserwator.gui._analyses import PROCESSES, TIMEOUT_S, Analyses, definition_of
from obserwator.gui._config import GuiConfig
from obserwator.gui._feedback import Feedback, post_feedback
from obserwator.gui._http import (
    GuiError,
    attachment,
    clean,
    dumps,
    error_body,
    error_response,
    etag_of,
    hide_paths,
    json_response,
    not_modified,
    page_lang,
    prebuilt_response,
)
from obserwator.gui._live import (
    CURRENT_PROVIDER,
    PMAXTP_METHODS,
    CurrentData,
    Pmaxtp,
    PmaxtpMethod,
    hydro_points,
    meteo_points,
    synop_indices,
    synop_record,
    utc_now,
)
from obserwator.gui._page import Site, WebFiles
from obserwator.gui._root import (
    ANALYSES_SLOTS,
    DataRoot,
    Snapshot,
    StationsFormat,
    record_years,
)
from obserwator.gui._state import GuiState
from obserwator.gui._stripes import stripes as stripes_prototype
from obserwator.gui._terms import terms_page
from obserwator.gui._traffic import Traffic, TrafficState, is_admin
from obserwator.instance import Instance
from obserwator.messages import LANGS, Lang, message
from obserwator.messages.gui import MESSAGES as TEXTS
from obserwator.nogat_logging import AccessLog, ServerLog
from obserwator.store.types import StationFeature

LOG = logging.getLogger(__name__)
WEB = Path(__file__).resolve().parent / "web"
DATA = Path(obserwator.__file__).resolve().parent / "_data"
BORDERS = {name: DATA / name for name in (POLAND, CZECHIA)}
"""The packaged borders, the map's background without a basemap (D9, ADR-018)."""
SESSION_SCHEMA = "obserwator-gui-session/1"
HANDOFF_SCHEMA = "nogat-handoff/1"
SERIES_SCHEMA = "hydrolog-series/1"
HYDRO_DAILY = ("pl.imgw.hydro_daily", "cz.chmu.hydro_daily")
PMAXTP_TABLES = ("ks", "sg", "rb")
SERIES_FORMATS: tuple[str, ...] = ("csv", "json", "parquet")
"""The formats of a station's series file (`export_series`, ADR-014)."""
STATIONS_FORMATS: tuple[str, ...] = ("geojson", "csv")
"""The formats of the stations file (`export_stations`, ADR-014)."""
ANALYSES_FORMATS: tuple[str, ...] = ("json", "csv")
"""The formats of a station's stored analyses (`export_analyses`, ADR-016)."""
READERS = 4
"""Blocking reads of the data root running at a time (D7: the VPS's 4 vCPU)."""
PROVIDER_ORIGINS: Mapping[str, tuple[Origin, ...]] = {
    provider.id: provider.adapter.origins for provider in providers()
}
"""The origins of each provider's data (``obserwator.attribution``), dropped when an
instance turns it ``off`` (ADR-025); PMAXTP's follows ``pmaxtp``, the borders' stay."""
LOGO_CSP = "sandbox; default-src 'none'"
"""The operator's logo's own policy (I14): an SVG opened by itself runs nothing."""
SEXT = {
    "csv": "text/csv; charset=utf-8",
    "json": "application/json",
    "parquet": "application/vnd.apache.parquet",
    "geojson": "application/geo+json",
}
QUIET = (
    r"^/(css|src|vendor|nogat|data|instrukcja|v)/|^/(admin/)?theme-init\.js$"
    r"|^/regulamin\.html$"
    r"|^/(favicon\.ico|robots\.txt|apple-touch-icon(-precomposed)?\.png)$"
)
"""The static content of the access log (Nogat DEV-12.5), paths at the origin's root: the
page's files, the admin page's script, the packaged borders, the guide and the regulamin,
the same for every client, are logged only when answered with 400 or more."""

Handler = Callable[[Request], Awaitable[Response]]


def _gui(request: Request) -> GuiState:
    state: GuiState = request.app.state.gui
    return state


def _route(handler: Handler) -> Handler:
    """A handler whose errors become the error document (D6)."""

    async def wrapped(request: Request) -> Response:
        try:
            return await handler(request)
        except (GuiError, ObserwatorError) as exc:
            return error_response(request, exc, _gui(request).directories())

    wrapped.__name__ = handler.__name__
    wrapped.__doc__ = handler.__doc__
    return wrapped


# --- the instance (ADR-025) ------------------------------------------------------------


def _instance(request: Request) -> Instance | None:
    return _gui(request).config.instance


def served_origins(instance: Instance | None) -> tuple[Origin, ...]:
    """The origins of the data a deployment serves: every one without an instance."""
    if instance is None:
        return ORIGINS
    dropped: set[str] = {
        origin
        for provider, origins in PROVIDER_ORIGINS.items()
        if not instance.serves(provider)
        for origin in origins
    }
    if not instance.pmaxtp:
        dropped.add("pmaxtp")
    return tuple(origin for origin in ORIGINS if origin not in dropped)


def _needs_current(handler: Handler) -> Handler:
    """A route of IMGW-PIB's current data: ``not_found`` before any request when it is off (I8)."""

    async def wrapped(request: Request) -> Response:
        instance = _instance(request)
        if instance is not None and not instance.serves(CURRENT_PROVIDER):
            raise GuiError(
                "not_found",
                message("instance.not_served", provider=CURRENT_PROVIDER),
                details={"reason": "not_served"},
            )
        return await handler(request)

    functools.update_wrapper(wrapped, handler)
    return wrapped


def _needs_pmaxtp(handler: Handler) -> Handler:
    """
    A route of PMAXTP: ``not_found`` before any request with ``pmaxtp = "off"`` (I8).

    With ``area_mode = "clip"`` a point outside the area is ``not_found`` too.
    """

    async def wrapped(request: Request) -> Response:
        instance = _instance(request)
        if instance is not None and not instance.pmaxtp:
            raise GuiError(
                "not_found",
                message("instance.pmaxtp_off"),
                details={"reason": "pmaxtp_off"},
            )
        if instance is not None and instance.clips:
            _, latitude, longitude = _pmaxtp_query(request.query_params)
            if not instance.keeps_point(longitude, latitude):
                raise GuiError(
                    "not_found",
                    message(
                        "instance.outside_area", latitude=latitude, longitude=longitude
                    ),
                    details={"option": "latitude", "reason": "outside_area"},
                )
        return await handler(request)

    functools.update_wrapper(wrapped, handler)
    return wrapped


def _inside(request: Request, points: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The current points an instance serves: with ``clip``, those inside its area."""
    instance = _instance(request)
    if instance is None or not instance.clips:
        return points
    return [p for p in points if instance.keeps_point(p.get("lon"), p.get("lat"))]


_STARTS: dict[
    tuple[str, str], tuple[str, tuple[float, float, float, float] | None]
] = {}
"""The start view of each instance and station layer, worked out once (I5)."""


def _start(
    instance: Instance, snapshot: Snapshot
) -> tuple[str, tuple[float, float, float, float] | None]:
    """
    Where the map starts: `Instance.start` of the snapshot's stations, once per layer.

    A start view that holds no station falls back to ``all`` with one warning.
    """
    key = (instance.key, snapshot.layer_etag)
    found = _STARTS.get(key)
    if found is None:
        found = instance.start(snapshot.features)
        if found[0] != instance.start_view:
            LOG.warning("%s", message("instance.empty_start", view=instance.start_view))
        if len(_STARTS) > 16:
            _STARTS.clear()
        _STARTS[key] = found
    return found


def _instance_document(
    instance: Instance | None, snapshot: Snapshot
) -> dict[str, Any] | None:
    """
    What the page needs of the instance (ADR-025, I7): never a path of the server.

    ``title``, ``logo`` (the address of `logo` or null), ``featured`` (a provider or
    null), ``others_opacity`` (the opacity of the other providers' stations while they
    are faded), ``providers`` (the state of each provider served, the featured one first),
    ``start`` (``view`` and ``box`` [west, south, east, north] or null for the whole
    data set), ``area`` (``mode``, ``box``, ``bounds`` of the map in ``clip`` and the
    address of its ``outline``, `area_outline`) and whether ``pmaxtp`` and the
    ``current`` data are served; null without ``[obserwator.instance]``.
    """
    if instance is None:
        return None
    view, box = _start(instance, snapshot) if snapshot.error is None else ("all", None)
    area = instance.area
    return {
        "title": instance.title,
        "logo": None if instance.logo is None else "api/logo",
        "featured": instance.featured,
        "others_opacity": instance.others_opacity,
        "providers": {
            provider: instance.providers[provider] for provider in instance.served
        },
        "start": {"view": view, "box": None if box is None else list(box)},
        "area": None
        if area is None
        else {
            "mode": area.mode,
            "box": list(area.box),
            "bounds": list(area.bounds) if area.clips else None,
            "outline": "api/area",
        },
        "pmaxtp": instance.pmaxtp,
        "current": instance.serves(CURRENT_PROVIDER),
    }


_LIMITERS: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, CapacityLimiter] = (
    weakref.WeakKeyDictionary()
)
"""The limiter of the blocking reads of each event loop (each server)."""


async def _thread[T](function: Callable[[], T]) -> T:
    """Run a blocking read in a worker thread, at most `READERS` at a time (D7)."""
    loop = asyncio.get_running_loop()
    limiter = _LIMITERS.get(loop)
    if limiter is None:
        limiter = _LIMITERS[loop] = CapacityLimiter(READERS)
    return await to_thread.run_sync(function, limiter=limiter)


def _etag(request: Request, *parts: object) -> str:
    """A strong ETag of an answer of this server's run: what it was made from (D7)."""
    return etag_of(_gui(request).boot, *parts)


def _snapshot(request: Request) -> Snapshot:
    snapshot = _gui(request).root.snapshot()
    if snapshot.error is not None:
        raise snapshot.error
    return snapshot


def _station(request: Request, snapshot: Snapshot, value: str | None = None) -> str:
    code = params.station(value if value is not None else request.path_params["code"])
    if code not in snapshot.features:
        raise GuiError(
            "not_found",
            message("gui.errors.no_station", station=code),
            details={"option": "station", "value": code},
        )
    return code


def _dataset(request: Request, snapshot: Snapshot) -> str:
    """The dataset of the address, one whose series the root holds; else ``not_found``."""
    dataset: str = request.path_params["dataset"]
    if dataset not in snapshot.series:
        shown = dataset[: params.MAX_TEXT]
        raise GuiError(
            "not_found",
            message("gui.errors.no_dataset", dataset=shown),
            details={
                "option": "dataset",
                "value": shown,
                "allowed": list(snapshot.series),
            },
        )
    return dataset


def _held(request: Request, snapshot: Snapshot, dataset: str) -> str:
    """The station of the address, held by the dataset's series; else ``not_found``."""
    code = _station(request, snapshot)
    if code not in snapshot.series[dataset].stations:
        raise GuiError(
            "not_found",
            message("gui.errors.no_series", station=code, dataset=dataset),
            details={"option": "station", "value": code},
        )
    return code


def _station_origins(
    provider: str,
    properties: Mapping[str, Any],
    *,
    location: bool,
    details: bool = False,
) -> Attribution:
    """
    The lines of what is shown of a station from its catalog.

    Its provider's; with its location, those of the packaged border the catalog
    checked it against (ADR-018) and hydro.imgw.pl's for a location taken from there;
    with its details, hydro.imgw.pl's for an IMGW-PIB station whose catalog feature
    carries them (``details_source``, ADR-021).
    """
    adapter = get_provider(provider).adapter
    lines = attribution(
        provider_origin(provider),
        *adapter.station_origins(properties, location=False, details=details),
    )
    if not location:
        return lines
    return lines | attribution(
        border_origin(provider),
        *adapter.station_origins(properties, location=True, details=False),
    )


# --- the session and the texts ------------------------------------------------------


@_route
async def session(request: Request) -> Response:
    """
    ``obserwator-gui-session/1``: versions, the data root, providers, basemap, menus.

    On an instance (ADR-025) only what it serves: its providers (the featured one
    first), the origins of their lines (the featured provider's lines first in
    ``order``) and ``instance`` (`_instance_document`); null without one.
    """
    params.only(request.query_params, ())
    state = _gui(request)
    snapshot = await _thread(state.root.snapshot)
    lang = page_lang(request)
    hydrolog = (
        await _thread(state.analyses.hydrolog_version)
        if state.analyses.can_compute
        else None
    )
    config = state.config
    instance = config.instance
    origins = served_origins(instance)
    every = attribution(*origins)
    first = (
        Attribution()
        if instance is None or instance.featured is None
        else attribution(provider_origin(instance.featured))
    )
    shown = (
        providers()
        if instance is None
        else [get_provider(provider) for provider in instance.served]
    )
    document = {
        "schema": SESSION_SCHEMA,
        "version": {"obserwator": state.version, "hydrolog": hydrolog},
        "root": {
            "catalogs": {p: v.to_dict() for p, v in snapshot.catalogs.items()},
            "series": {
                key: {
                    **series.version.to_dict(),
                    "year_type": series.year_type,
                    "stations": len(series.stations),
                }
                for key, series in snapshot.series.items()
            },
            "analyses": {
                provider: None
                if (version := snapshot.analyses.get(provider)) is None
                else {**version.to_dict(), "hydrolog": version.hydrolog}
                for provider in ANALYSES_SLOTS
                if instance is None or instance.serves(provider)
            },
            "error": None
            if snapshot.error is None
            else hide_paths(error_body(snapshot.error, lang), state.directories()),
        },
        "providers": {
            provider.id: {
                "short_name": provider.short_name,
                "name": provider.name,
                **attribution(provider_origin(provider.id)).fields(),
            }
            for provider in shown
        },
        "attribution": {
            "origins": {origin: attribution(origin).fields() for origin in origins},
            "order": list(dict.fromkeys([*first.attribution, *every.attribution])),
            "terms_order": list(
                dict.fromkeys([*first.terms_notice, *every.terms_notice])
            ),
        },
        "basemap": None
        if config.basemap is None
        else {"url": config.basemap.url, "attribution": config.basemap.attribution},
        "gui": dict(config.gui),
        "terms": "regulamin.html" if state.terms is not None else None,
        "operator_email": (config.operator or {}).get("email")
        if state.terms is not None
        else None,
        "compute": {
            "available": state.analyses.can_compute,
            "hydrolog": hydrolog,
            "processes": PROCESSES,
            "timeout_s": TIMEOUT_S,
        },
        "instance": _instance_document(instance, snapshot),
    }
    return json_response(request, document)


@functools.cache
def _texts(lang: Lang) -> dict[str, Any]:
    """The area ``gui`` of the message catalog in ``lang``, made once."""
    return {
        "lang": lang,
        "texts": {key: getattr(text, lang) for key, text in TEXTS.items()},
    }


@_route
async def texts(request: Request) -> Response:
    """The area ``gui`` of the message catalog in one language (``lang``: pl or en)."""
    params.only(request.query_params, ("lang",))
    chosen = params.choice(request.query_params.get("lang"), "lang", LANGS, "pl")
    lang: Lang = "en" if chosen == "en" else "pl"
    return json_response(request, _texts(lang), etag=_etag(request, "texts", lang))


# --- stations and series --------------------------------------------------------------


@_route
async def stations(request: Request) -> Response:
    """
    The station layer: every station of the current catalogs and the series holding it.

    A request holding the layer's ETag gets ``304`` before anything is built; else the
    answer built and gzipped once per layer (`GuiState.layer`).
    """
    params.only(request.query_params, ())
    snapshot = await _thread(lambda: _snapshot(request))
    etag = _etag(request, snapshot.layer_etag)
    unchanged = not_modified(request, etag)
    if unchanged is not None:
        return unchanged

    def build() -> dict[str, Any]:
        lines = Attribution()
        for feature in snapshot.features.values():
            lines = lines | _station_origins(
                feature.provider, feature.properties, location=True
            )
        return {**snapshot.layer, **lines.fields()}

    bodies = await _thread(lambda: _gui(request).layer.bodies(etag, build))
    return prebuilt_response(request, bodies, etag)


@_route
async def station(request: Request) -> Response:
    """One station: its catalog properties, the series holding it and their lines."""
    params.only(request.query_params, ())
    snapshot = await _thread(lambda: _snapshot(request))
    code = _station(request, snapshot)
    feature = snapshot.features[code]
    props = dict(feature.properties)
    held = snapshot.datasets_of(code)
    lon, lat = feature.geometry if feature.geometry else (None, None)
    catalog = _station_origins(feature.provider, props, location=True, details=True)
    series_lines = Attribution()
    for entry in held:
        series_lines = series_lines | attribution(dataset_origin(entry["dataset"]))
    document = {
        "code": code,
        "provider": feature.provider,
        "lon": lon,
        "lat": lat,
        "properties": props,
        "datasets": held,
        **record_years(held),
        **catalog.fields(),
        "attribution_parts": {
            "catalog": catalog.fields(),
            "series": series_lines.fields() if held else None,
            "results": series_lines.fields() if held else None,
        },
    }
    _gui(request).traffic.count("stations_opened")
    return json_response(
        request, document, etag=_etag(request, "station", snapshot.key, code)
    )


def _slice(
    document: Mapping[str, Any],
    variables: tuple[str, ...] | None,
    start: date | None,
    end: date | None,
) -> dict[str, Any]:
    """The rows of a series document between two dates, of some variables."""
    dates: list[str] = document["dates"]
    first = (
        0
        if start is None
        else next(
            (i for i, d in enumerate(dates) if d >= start.isoformat()), len(dates)
        )
    )
    last = (
        len(dates)
        if end is None
        else next((i for i, d in enumerate(dates) if d > end.isoformat()), len(dates))
    )
    names = variables or tuple(document["values"])
    out = {
        key: value
        for key, value in document.items()
        if key not in ("dates", "hydro_year", "values", "flags", "period", "extremes")
    }
    out["dates"] = dates[first:last]
    out["hydro_year"] = document["hydro_year"][first:last]
    out["units"] = {name: document["units"].get(name) for name in names}
    out["values"] = {name: document["values"][name][first:last] for name in names}
    out["flags"] = {
        name: [
            [row - first, flag]
            for row, flag in document["flags"][name]
            if first <= row < last
        ]
        for name in names
    }
    if "period" in document:
        out["period"] = document["period"][first:last]
        out["extremes"] = {
            key: values[first:last]
            for key, values in document["extremes"].items()
            if key.rsplit("_", 1)[0] in names
        }
    return out


@_route
async def series(request: Request) -> Response:
    """A station's series of a dataset: dates, values (null = none) and flags."""
    query = request.query_params
    params.only(query, ("variables", "start", "end"))
    snapshot = await _thread(lambda: _snapshot(request))
    dataset = _dataset(request, snapshot)
    code = _held(request, snapshot, dataset)
    descriptor = get_dataset(dataset)
    variables = params.names(
        query.get("variables"), "variables", tuple(descriptor.variables)
    )
    start = params.iso_date(query.get("start"), "start")
    end = params.iso_date(query.get("end"), "end")
    if start is not None and end is not None and start > end:
        raise params.invalid(
            "start", start.isoformat(), "range", maximum=end.isoformat()
        )
    document, base = await _thread(
        lambda: _gui(request).root.series_document(dataset, code)
    )
    body = {
        **_slice(document, variables, start, end),
        **attribution(dataset_origin(dataset)).fields(),
    }
    return json_response(
        request, body, etag=_etag(request, base, variables, start, end)
    )


# --- analyses ---------------------------------------------------------------------------


@_route
async def analyses(request: Request) -> Response:
    """The stored analyses of a station, each with the options a person may change."""
    params.only(request.query_params, ())
    state = _gui(request)
    snapshot = await _thread(lambda: _snapshot(request))
    code = _station(request, snapshot)
    found = await _thread(lambda: state.analyses.list(code))
    document = {
        "station": code,
        "analyses": list(found),
        "compute": state.analyses.can_compute,
    }
    versions = sorted({str(item.get("analyses_version")) for item in found})
    return json_response(
        request,
        document,
        etag=_etag(
            request,
            "analyses",
            snapshot.key,
            code,
            versions,
            state.analyses.can_compute,
        ),
    )


@_route
async def analysis(request: Request) -> Response:
    """One analysis id of a station: the stored result, or one computed with the overrides."""
    state = _gui(request)
    snapshot = await _thread(lambda: _snapshot(request))
    code = _station(request, snapshot)
    name = request.path_params["analysis"]
    overrides = state.analyses.overrides(name, params.single(request.query_params))
    result, etag = await state.analyses.get(snapshot, code, name, overrides)
    if result["source"] == "computed":
        state.traffic.count("analyses_run")
    return json_response(request, result, etag=_etag(request, etag))


@_route
async def analysis_file(request: Request) -> Response:
    """One analysis id's result as a JSON file: the same document as `analysis`."""
    state = _gui(request)
    snapshot = await _thread(lambda: _snapshot(request))
    code = _station(request, snapshot)
    name = request.path_params["analysis"]
    overrides = state.analyses.overrides(name, params.single(request.query_params))
    result, etag = await state.analyses.get(snapshot, code, name, overrides)
    state.traffic.count("downloads")
    return attachment(
        request,
        dumps(result, indent=2),
        filename=analyses_file_name(code, name, "json"),
        media_type="application/json",
        etag=_etag(request, etag),
    )


@_route
async def analyses_file(request: Request) -> Response:
    """The stored analyses of a station as a file, made by `export_analyses` (CSV or JSON)."""
    query = request.query_params
    params.only(query, ("format", "analysis"))
    fmt = params.choice(query.get("format"), "format", ANALYSES_FORMATS, "json")
    name = query.get("analysis")
    state = _gui(request)
    snapshot = await _thread(lambda: _snapshot(request))
    code = _station(request, snapshot)
    if name is not None:
        definition_of(name)
    stored = await _thread(lambda: state.analyses.list(code))
    if not stored:
        raise GuiError(
            "not_found",
            message("gui.errors.no_stored_analyses", station=code),
            details={"option": "station", "value": code},
        )
    if name is not None and name not in {item["analysis"] for item in stored}:
        raise GuiError(
            "not_found",
            message("gui.errors.analysis_not_stored", analysis=name, station=code),
            details={
                "option": "analysis",
                "value": name,
                "allowed": [item["analysis"] for item in stored],
            },
        )
    version = stored[0].get("analyses_version")
    etag = _etag(request, "analyses-file", version, code, name, fmt)
    unchanged = not_modified(request, etag)
    if unchanged is not None:
        return unchanged
    body = await _thread(
        lambda: "".join(
            obserwator.export_analyses(
                root=state.config.root,
                station=code,
                analyses=None if name is None else [name],
                format="csv" if fmt == "csv" else "json",
            )
        ).encode("utf-8")
    )
    state.traffic.count("downloads")
    return attachment(
        request,
        body,
        filename=analyses_file_name(code, name, fmt),
        media_type="text/csv" if fmt == "csv" else "application/json",
        etag=etag,
    )


# --- current data and PMAXTP -------------------------------------------------------------


def _snapshot_times(snaps: Mapping[str, Any], lang: str) -> dict[str, Any]:
    return {
        name: {
            "fetched_at": snap.fetched_at,
            "error": None
            if snap.error is None
            else error_body(snap.error, lang)["message"],  # type: ignore[arg-type]
        }
        for name, snap in snaps.items()
    }


@_route
@_needs_current
async def current(request: Request) -> Response:
    """The points of „Pomiary bieżące”: IMGW-PIB's hydrological and meteorological stations."""
    params.only(request.query_params, ())
    live = _gui(request).current
    snaps = await _thread(partial(live.get_many, ("states", "hydro", "meteo")))
    if all(snap.items is None for snap in snaps.values()):
        error = next(
            (snap.error for snap in snaps.values() if snap.error is not None), None
        )
        raise error or GuiError("source_unavailable", message("gui.errors.no_current"))
    lang = page_lang(request)
    etag = _etag(request, "current", lang, {k: s.serial for k, s in snaps.items()})
    unchanged = not_modified(request, etag)
    if unchanged is not None:
        return unchanged
    document = {
        "source": CURRENT_PROVIDER,
        "snapshots": _snapshot_times(snaps, lang),
        "hydro": _inside(request, hydro_points(snaps["states"], snaps["hydro"])),
        "meteo": _inside(request, meteo_points(snaps["meteo"])),
        **attribution("imgw", "imgw_hydro").fields(),
    }
    return json_response(request, document, etag=etag)


@_route
@_needs_current
async def current_station(request: Request) -> Response:
    """One station's current values (IMGW-PIB only), with its synoptic report where paired."""
    params.only(request.query_params, ())
    snapshot = await _thread(lambda: _snapshot(request))
    code = _station(request, snapshot)
    feature = snapshot.features[code]
    kind = feature.properties.get("kind")
    if kind not in ("hydro", "meteo"):
        # Current data are of hydrological and meteorological stations only: a groundwater
        # object (ADR-032) is refused as such, whoever provides it, and never taken for a
        # meteorological station
        raise GuiError(
            "not_found",
            message("gui.errors.no_current_kind"),
            details={"reason": "kind"},
        )
    if feature.provider != CURRENT_PROVIDER:
        raise GuiError(
            "not_found",
            message("gui.errors.no_current_chmu"),
            details={"reason": "provider"},
        )
    live = _gui(request).current
    indices = synop_indices(snapshot.features)
    names = (
        ("hydro", "states")
        if kind == "hydro"
        else (("meteo", "synop") if code in indices else ("meteo",))
    )
    snaps = await _thread(partial(live.get_many, names))
    main = snaps[names[0]]
    if main.items is None:
        raise main.error or GuiError(
            "source_unavailable", message("gui.errors.no_current")
        )
    lang = page_lang(request)
    etag = _etag(
        request,
        "current-station",
        snapshot.key,
        code,
        lang,
        {k: s.serial for k, s in snaps.items()},
    )
    unchanged = not_modified(request, etag)
    if unchanged is not None:
        return unchanged
    document: dict[str, Any] = {
        "station": code,
        "kind": kind,
        "source": CURRENT_PROVIDER,
        "snapshots": _snapshot_times(snaps, lang),
        "record": main.items.get(code),
        **(
            attribution("imgw", "imgw_hydro")
            if kind == "hydro"
            else attribution("imgw")
        ).fields(),
    }
    if kind == "hydro":
        state = (snaps["states"].items or {}).get(code)
        document["state"] = state.get("water_state") if state else None
    elif "synop" in snaps:
        document["synop"] = synop_record(code, feature, indices, snaps["synop"])
    return json_response(request, document, etag=etag)


def _pmaxtp_query(query: Mapping[str, str]) -> tuple[PmaxtpMethod, float, float]:
    chosen = params.choice(query.get("method"), "method", PMAXTP_METHODS, "POT")
    method: PmaxtpMethod = "AMP" if chosen == "AMP" else "POT"
    latitude = params.number(query.get("latitude"), "latitude", minimum=-90, maximum=90)
    longitude = params.number(
        query.get("longitude"), "longitude", minimum=-180, maximum=180
    )
    if latitude is None or longitude is None:
        raise params.invalid(
            "latitude" if latitude is None else "longitude", None, "required"
        )
    return method, round(latitude, 4), round(longitude, 4)


@_route
@_needs_pmaxtp
async def pmaxtp(request: Request) -> Response:
    """PMAXTP of a point: the three tables, IMGW-PIB's address of the answer, the lines."""
    params.only(request.query_params, ("latitude", "longitude", "method"))
    method, latitude, longitude = _pmaxtp_query(request.query_params)
    document = await _thread(
        lambda: _gui(request).pmaxtp.get(method, latitude, longitude)
    )
    return json_response(request, {**document, **attribution("pmaxtp").fields()})


def _spread(lines: list[str], rows: int) -> list[str]:
    """One line per cell from the first row down, the rest joined in the last (DEV-20.5)."""
    if rows <= 0:
        return []
    cells = lines[:rows] + [""] * max(0, rows - len(lines))
    if len(lines) > rows:
        cells[rows - 1] = "\n".join(lines[rows - 1 :])
    return cells


def pmaxtp_csv(document: Mapping[str, Any]) -> str:
    """
    PMAXTP of a point as CSV: a row per table and duration, a column per probability.

    The columns ``attribution`` and ``terms_notice`` carry PMAXTP's lines one per cell
    from the first data row down (DEV-20.5). UTF-8, comma, decimal dot, CRLF.
    """
    probabilities = document["probabilities"]
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\r\n")
    writer.writerow(
        [
            "method",
            "latitude",
            "longitude",
            "table",
            "duration [min]",
            *(f"p={p}% [mm]" for p in probabilities),
            "attribution",
            "terms_notice",
        ]
    )
    rows = [
        (table, duration)
        for table in PMAXTP_TABLES
        for duration in document["durations"]
    ]
    lines = attribution("pmaxtp")
    first = _spread(list(lines.attribution), len(rows))
    terms = _spread(list(lines.terms_notice), len(rows))
    for index, (table, duration) in enumerate(rows):
        row = document["data"][table].get(duration, {})
        writer.writerow(
            [
                document["method"],
                f"{document['latitude']:.4f}",
                f"{document['longitude']:.4f}",
                table,
                duration,
                *(row.get(p, "") for p in probabilities),
                first[index],
                terms[index],
            ]
        )
    return out.getvalue()


@_route
@_needs_pmaxtp
async def pmaxtp_file(request: Request) -> Response:
    """PMAXTP of a point as a file packed by the server: CSV or JSON with PMAXTP's lines."""
    query = request.query_params
    params.only(query, ("latitude", "longitude", "method", "format"))
    fmt = params.choice(query.get("format"), "format", ("csv", "json"), "csv")
    method, latitude, longitude = _pmaxtp_query(query)
    document = await _thread(
        lambda: _gui(request).pmaxtp.get(method, latitude, longitude)
    )
    name = pmaxtp_file_name(method, latitude, longitude, fmt)
    if fmt == "json":
        body = dumps(
            {
                "schema": "obserwator-pmaxtp-export/1",
                **{
                    key: document[key]
                    for key in (
                        "method",
                        "latitude",
                        "longitude",
                        "durations",
                        "probabilities",
                        "data",
                        "fetched_at",
                        "source_url",
                    )
                },
                "units": {
                    "ks": "mm",
                    "sg": "mm",
                    "rb": "mm",
                    "duration": "min",
                    "probability": "%",
                },
                **attribution("pmaxtp").fields(),
            },
            indent=2,
        )
    else:
        body = pmaxtp_csv(document).encode("utf-8")
    _gui(request).traffic.count("downloads")
    return attachment(request, body, filename=name, media_type=SEXT[fmt])


# --- files and command lines -------------------------------------------------------------


def _shown_command(command: str, options: Mapping[str, Any]) -> str:
    """
    The command line that makes the same file on the reader's computer.

    It is `format_command`'s canonical line without the server's root (the reader's
    default root stands for it) and with the bare file name as the output (in the
    reader's working directory): no server path (D6).
    """
    words = iter(shlex.split(obserwator.format_command(command, options=options)))
    shown: list[str] = []
    for word in words:
        if word == "--root":
            next(words, None)
        elif word == "--output":
            shown += [word, Path(next(words, "")).name]
        else:
            shown.append(word)
    return shlex.join(shown)


@_route
async def downloads(request: Request) -> Response:
    """The files of a station: its series and stored analyses in each format, with commands."""
    params.only(request.query_params, ())
    state = _gui(request)
    snapshot = await _thread(lambda: _snapshot(request))
    code = _station(request, snapshot)
    files = []
    for entry in snapshot.datasets_of(code):
        dataset = entry["dataset"]
        descriptor = get_dataset(dataset)
        formats = {}
        for fmt in SERIES_FORMATS:
            name = series_file_name(dataset, code, fmt)
            options = {"dataset": dataset, "station": code, "output": name}
            formats[fmt] = {
                "file": name,
                "url": f"api/files/series/{dataset}/{code}?format={fmt}",
                "command": _shown_command(
                    "series export",
                    options if fmt == "csv" else {**options, "format": fmt},
                ),
            }
        files.append(
            {
                "dataset": dataset,
                "version": entry["version"],
                "formats": formats,
                "licence": {
                    "provider": get_provider(descriptor.provider).short_name,
                    "id": descriptor.license.id,
                    "url": descriptor.license.url,
                    "terms_url": descriptor.license.terms_url,
                },
                **attribution(dataset_origin(dataset)).fields(),
            }
        )
    stored = await _thread(lambda: state.analyses.list(code))
    analyses = None
    if stored:
        formats = {}
        for fmt in ANALYSES_FORMATS:
            name = analyses_file_name(code, None, fmt)
            formats[fmt] = {
                "file": name,
                "url": f"api/files/analyses/{code}?format={fmt}",
                "command": _shown_command(
                    "analyses export",
                    {"station": code, "format": fmt, "output": name},
                ),
            }
        analyses = {
            "version": stored[0].get("analyses_version"),
            "hydrolog": stored[0].get("hydrolog"),
            "computed_at": stored[0].get("computed_at"),
            "count": len(stored),
            "formats": formats,
            # The name of each analysis's own files (JSON, CSV), which the page offers.
            "each": {
                item["analysis"]: {
                    fmt: analyses_file_name(code, item["analysis"], fmt)
                    for fmt in ANALYSES_FORMATS
                }
                for item in stored
            },
            "attribution": stored[0].get("attribution", []),
            "terms_notice": stored[0].get("terms_notice", []),
        }
    return json_response(
        request,
        {"station": code, "series": files, "analyses": analyses},
        etag=_etag(
            request,
            "downloads",
            snapshot.key,
            code,
            None if analyses is None else analyses["version"],
        ),
    )


@_route
async def series_file(request: Request) -> Response:
    """A station's series as a file, made by `export_series` exactly as the CLI makes it."""
    query = request.query_params
    params.only(query, ("format",))
    snapshot = await _thread(lambda: _snapshot(request))
    dataset = _dataset(request, snapshot)
    code = _held(request, snapshot, dataset)
    fmt = params.choice(query.get("format"), "format", SERIES_FORMATS, "csv")
    state = _gui(request)
    name = series_file_name(dataset, code, fmt)
    etag = _etag(request, "file", snapshot.series[dataset].version.sha256, code, fmt)
    unchanged = not_modified(request, etag)
    if unchanged is not None:
        return unchanged
    root = state.config.root

    def export() -> bytes:
        if fmt != "parquet":
            lines = obserwator.export_series(
                root=root,
                dataset=dataset,
                station=code,
                format="json" if fmt == "json" else "csv",
            )
            return "".join(lines).encode("utf-8")
        # Parquet is binary and needs a file: a private one, removed at once.
        folder = Path(tempfile.mkdtemp(prefix="obserwator-gui-file-"))
        try:
            obserwator.export_series(
                root=root,
                dataset=dataset,
                station=code,
                format="parquet",
                output=folder / name,
            )
            return (folder / name).read_bytes()
        finally:
            shutil.rmtree(folder, ignore_errors=True)

    body = await _thread(export)
    state.traffic.count("downloads")
    return attachment(request, body, filename=name, media_type=SEXT[fmt], etag=etag)


def _stations_query(
    query: Mapping[str, str],
) -> tuple[str | None, Kind | None]:
    """The provider and the kind of a stations file; None for every one."""
    provider = query.get("provider") or None
    if provider is not None:
        params.choice(provider, "provider", tuple(item.id for item in providers()))
    chosen = query.get("kind") or None
    if chosen is None:
        return provider, None
    params.choice(chosen, "kind", KINDS)
    return provider, next(kind for kind in KINDS if kind == chosen)


def _stations_of(
    snapshot: Snapshot, provider: str | None, kind: str | None
) -> list[StationFeature]:
    """The stations of the current catalogs of a provider and a kind; else ``not_found``."""
    chosen = [
        feature
        for feature in snapshot.features.values()
        if (provider is None or feature.provider == provider)
        and (kind is None or feature.properties.get("kind") == kind)
    ]
    if not chosen:
        raise GuiError(
            "not_found",
            message("gui.errors.no_stations"),
            details={"provider": provider, "kind": kind},
        )
    return chosen


@_route
async def stations_downloads(request: Request) -> Response:
    """The stations of the current catalogs as files: each format, its command line."""
    query = request.query_params
    params.only(query, ("provider", "kind"))
    provider, kind = _stations_query(query)
    snapshot = await _thread(lambda: _snapshot(request))
    chosen = _stations_of(snapshot, provider, kind)
    lines = Attribution()
    for feature in chosen:
        lines = lines | _station_origins(
            feature.provider, feature.properties, location=True, details=True
        )
    selection = {
        key: value for key, value in (("provider", provider), ("kind", kind)) if value
    }
    formats = {}
    for fmt in STATIONS_FORMATS:
        name = stations_file_name(provider, kind, fmt)
        options = {**selection, "output": name}
        formats[fmt] = {
            "file": name,
            "url": f"api/files/stations?{urlencode({'format': fmt, **selection})}",
            "command": _shown_command(
                "stations export",
                options if fmt == "geojson" else {**options, "format": fmt},
            ),
        }
    held = {feature.provider for feature in chosen}
    document = {
        "provider": provider,
        "kind": kind,
        "stations": len(chosen),
        "formats": formats,
        "licences": [
            {
                "provider": item.short_name,
                "id": item.license.id,
                "url": item.license.url,
                "terms_url": item.license.terms_url,
            }
            for item in providers()
            if item.id in held
        ],
        **lines.fields(),
    }
    return json_response(
        request,
        document,
        etag=_etag(request, "stations-downloads", snapshot.key, provider, kind),
    )


@_route
async def stations_file(request: Request) -> Response:
    """The stations of the current catalogs as a file, made by `export_stations`."""
    query = request.query_params
    params.only(query, ("format", "provider", "kind"))
    chosen = params.choice(query.get("format"), "format", STATIONS_FORMATS, "geojson")
    fmt: StationsFormat = "csv" if chosen == "csv" else "geojson"
    provider, kind = _stations_query(query)
    state = _gui(request)
    snapshot = await _thread(lambda: _snapshot(request))
    _stations_of(snapshot, provider, kind)
    etag = _etag(request, "stations-file", snapshot.key, fmt, provider, kind)
    unchanged = not_modified(request, etag)
    if unchanged is not None:
        return unchanged
    body = await _thread(lambda: state.root.stations_file(fmt, provider, kind))
    state.traffic.count("downloads")
    return attachment(
        request,
        body,
        filename=stations_file_name(provider, kind, fmt),
        media_type=SEXT[fmt],
        etag=etag,
    )


# --- the hand-off to Hydrolog -------------------------------------------------------------


@_route
async def handoff(request: Request) -> Response:
    """
    ``nogat-handoff/1`` around ``hydrolog-series/1`` (D13): a daily series or annual maxima.

    ``resolution=daily`` hands the days of the hydrological years chosen (a day without a
    value as null); ``resolution=annual`` hands the annual maxima that Hydrolog's result of
    the id ``analysis`` used (``annual_maxima`` and ``hydrological_years``), with the id's
    command, options and result in the envelope.
    """
    query = params.single(request.query_params)
    state = _gui(request)
    params.station(request.path_params["code"])
    variable = params.choice(query.pop("variable", None), "variable", ("Q", "H"), "Q")
    resolution = params.choice(
        query.pop("resolution", None), "resolution", ("daily", "annual"), "daily"
    )
    first = last = None
    analysis_id = f"flood_frequency.{variable}"
    overrides: dict[str, Any] = {}
    if resolution == "daily":
        first = params.year(query.pop("first_year", None), "first_year")
        last = params.year(query.pop("last_year", None), "last_year")
        params.years(first, last, first_option="first_year", last_option="last_year")
        params.only(query, ())
    else:
        analysis_id = query.pop("analysis", "") or analysis_id
        overrides = state.analyses.overrides(analysis_id, query)
    snapshot = await _thread(lambda: _snapshot(request))
    code = _station(request, snapshot)
    feature = snapshot.features[code]
    props = dict(feature.properties)
    name = str(props.get("name") or code)
    river = f" ({props['river']})" if props.get("river") else ""
    producer = {
        "tool": "obserwator",
        "version": state.version,
        "page": _page_address(request, code),
    }
    if resolution == "daily":
        dataset = next(
            (
                key
                for key in HYDRO_DAILY
                if key in snapshot.series and code in snapshot.series[key].stations
            ),
            None,
        )
        if dataset is None:
            raise GuiError(
                "not_found",
                message(
                    "gui.errors.no_series", station=code, dataset=", ".join(HYDRO_DAILY)
                ),
            )
        document, _ = await _thread(lambda: state.root.series_document(dataset, code))
        keep = [
            i
            for i, (year, value) in enumerate(
                zip(document["hydro_year"], document["values"][variable], strict=True)
            )
            if value is not None
            and (first is None or year >= first)
            and (last is None or year <= last)
        ]
        accumulated = {
            row for row, flag in document["flags"][variable] if flag == "accumulated"
        }
        keep = [i for i in keep if i not in accumulated]
        if not keep:
            raise GuiError(
                "not_found", message("gui.errors.no_values", variable=variable)
            )
        rows = range(keep[0], keep[-1] + 1)
        kept = set(keep)
        payload = {
            "schema": SERIES_SCHEMA,
            "name": f"{name} — {variable}",
            "variable": variable,
            "unit": document["units"][variable],
            "step": "day",
            "dates": [document["dates"][i] for i in rows],
            "values": [
                document["values"][variable][i] if i in kept else None for i in rows
            ],
        }
        lines = attribution(dataset_origin(dataset))
        provenance = {
            "series": {
                "source": feature.provider.lower(),
                "provider": feature.provider,
                "station": code,
                "dataset": dataset,
                "series_version": snapshot.series[dataset].version.label,
            }
        }
        subject = message(
            "gui.handoff.subject_daily",
            lang=page_lang(request),
            station=f"{name}{river}",
            variable=variable,
        )
        result = None
    else:
        result_doc, _ = await state.analyses.get(snapshot, code, analysis_id, overrides)
        found = (result_doc.get("envelope") or {}).get("result") or {}
        years, maxima = found.get("hydrological_years"), found.get("annual_maxima")
        if (
            result_doc.get("status") != "ok"
            or not isinstance(years, list)
            or not isinstance(maxima, list)
        ):
            raise GuiError(
                "not_found", message("gui.errors.no_values", variable=variable)
            )
        payload = {
            "schema": SERIES_SCHEMA,
            "name": f"{name} — {variable}",
            "variable": variable,
            "unit": get_dataset(result_doc["inputs"][0]["dataset"]).variables.get(
                variable
            )
            or get_dataset(result_doc["inputs"][0]["dataset"]).variables.get(
                f"{variable}_max"
            ),
            "step": "year",
            "statistic": "max",
            "year_type": "hydrological",
            "years": years,
            "values": maxima,
        }
        lines = Attribution(
            tuple(result_doc.get("attribution") or ()),
            tuple(result_doc.get("terms_notice") or ()),
        )
        provenance = {
            "series": {
                "source": feature.provider.lower(),
                "provider": feature.provider,
                "station": code,
                "dataset": result_doc["inputs"][0]["dataset"],
                "series_version": result_doc["inputs"][0]["series_version"],
                "command": f"hydrolog {result_doc['command']}",
                "options": result_doc["options"],
            }
        }
        subject = message(
            "gui.handoff.subject_annual",
            lang=page_lang(request),
            station=f"{name}{river}",
            variable=variable,
        )
        result = {
            "analysis": analysis_id,
            "hydrolog": result_doc["hydrolog"],
            "result": found,
        }
    document = {
        "schema": HANDOFF_SCHEMA,
        "created_at": utc_now(),
        "producer": producer,
        "subject": str(subject),
        **lines.fields(),
        "provenance": provenance,
        "payload": payload,
    }
    if result is not None:
        document["result"] = result
    return json_response(request, clean(document))


def _page_address(request: Request, code: str) -> str:
    """The station's page: the deployment's address, else this app's, under its prefix."""
    base = _gui(request).config.gui.get("obserwator") or (
        f"{request.url.scheme}://{request.url.netloc}{request.scope.get('root_path', '')}"
    )
    return f"{base.rstrip('/')}/?station={code}"


# --- pages ------------------------------------------------------------------------------


@_route
async def regulamin(request: Request) -> Response:
    """``regulamin.html`` (DEV-15.7): the kit's terms, or the operator's, filled."""
    terms = _gui(request).terms
    if terms is None:
        raise GuiError(
            "not_found", message("gui.errors.not_found", path="regulamin.html")
        )
    return Response(
        terms,
        media_type="text/html; charset=utf-8",
        headers={"Cache-Control": "no-cache"},
    )


@_route
async def border(request: Request) -> Response:
    """A packaged border of the offline map (D9)."""
    params.only(request.query_params, ())
    path = BORDERS.get(request.path_params["name"])
    if path is None:
        raise GuiError(
            "not_found",
            message("gui.errors.not_found", path=request.path_params["name"]),
        )
    return Response(
        path.read_bytes(),
        media_type="application/geo+json",
        headers={"Cache-Control": "no-cache"},
    )


async def touch_icon(request: Request) -> Response:
    """``apple-touch-icon-precomposed.png``: the same icon as ``apple-touch-icon.png``."""
    return FileResponse(WEB / "apple-touch-icon.png", media_type="image/png")


async def robots(request: Request) -> Response:
    """
    ``robots.txt``: crawlers may read the page but not the API, which computes on request.

    Made here rather than kept as a file of ``web/``: the API's path follows the prefix
    the app is mounted under.
    """
    prefix = request.scope.get("root_path", "").rstrip("/")
    return Response(
        f"User-agent: *\nDisallow: {prefix}/api/\n", media_type="text/plain"
    )


@_route
async def logo(request: Request) -> Response:
    """
    The operator's logo of ``[obserwator.instance]`` (I14), from the GUI's own origin.

    Its type was read from its content at the start (PNG, WebP or SVG); it carries
    `LOGO_CSP` and ``nosniff``, so an SVG opened by itself runs no script.
    """
    params.only(request.query_params, ())
    instance = _instance(request)
    found = None if instance is None else instance.logo
    if found is None:
        raise GuiError("not_found", message("gui.errors.not_found", path="api/logo"))
    etag = _etag(request, "logo", found.sha256)
    headers = {
        "Cache-Control": "no-cache",
        "ETag": f'"{etag}"',
        "Content-Security-Policy": LOGO_CSP,
        "X-Content-Type-Options": "nosniff",
    }
    if not_modified(request, etag) is not None:
        return Response(status_code=304, headers=headers)
    return Response(found.data, media_type=found.media_type, headers=headers)


@_route
async def area_outline(request: Request) -> Response:
    """The area of ``[obserwator.instance]`` (I4) as a GeoJSON Feature, for its outline."""
    params.only(request.query_params, ())
    instance = _instance(request)
    found = None if instance is None else instance.area
    if found is None:
        raise GuiError("not_found", message("gui.errors.not_found", path="api/area"))
    document = {
        "type": "Feature",
        "properties": {"mode": found.mode},
        "geometry": found.geometry,
    }
    return json_response(
        request, document, etag=_etag(request, "area", found.mode, found.sha256)
    )


@_route
async def api_not_found(request: Request) -> Response:
    """Any other address under ``api/``: 404 as the error document."""
    raise GuiError("not_found", message("gui.errors.not_found", path=request.url.path))


# --- headers ------------------------------------------------------------------------------


def csp(config: GuiConfig) -> str:
    """The page's Content-Security-Policy (D16): its own origin and the basemap's only."""
    remote = f" {config.basemap.origin}" if config.basemap is not None else ""
    return "; ".join(
        [
            "default-src 'self'",
            "script-src 'self'",
            "style-src 'self'",
            "worker-src 'self'",
            f"img-src 'self' data: blob:{remote}",
            f"connect-src 'self'{remote}",
            "font-src 'self'",
            "object-src 'none'",
            "base-uri 'none'",
            "form-action 'self'",
            "frame-ancestors 'none'",
        ]
    )


ADMIN_CSP = "; ".join(
    [
        "default-src 'self'",
        "script-src 'self'",
        "style-src 'self'",
        "img-src 'self'",
        "connect-src 'self'",
        "font-src 'self'",
        "object-src 'none'",
        "base-uri 'none'",
        "form-action 'self'",
        "frame-ancestors 'none'",
    ]
)
"""The admin panel's Content-Security-Policy (DEV-15.13): its own origin alone."""
_REPORT_PATH = re.compile(r"/api/admin/feedback/[^/]+")


def methods(path: str) -> tuple[str, ...]:
    """
    The methods a path takes, relative to the mount.

    Parameters
    ----------
    path : str
        The path without the mount's prefix.

    Returns
    -------
    tuple of str
        ``POST`` for ``api/feedback``, ``PATCH`` and ``DELETE`` for a report of the
        admin panel (``api/admin/feedback/{id}``), ``GET`` and ``HEAD`` for the rest.
    """
    if path == "/api/feedback":
        return ("POST",)
    if _REPORT_PATH.fullmatch(path):
        return ("PATCH", "DELETE")
    return ("GET", "HEAD")


def _security(policy: str) -> list[tuple[bytes, bytes]]:
    """The headers of D16 with a Content-Security-Policy and those of both servers."""
    return [
        (b"content-security-policy", policy.encode()),
        (b"x-frame-options", b"DENY"),
        *security_headers(),
        (b"cross-origin-opener-policy", b"same-origin"),
        (b"cross-origin-resource-policy", b"same-origin"),
    ]


class SecurityHeaders:
    """
    The methods of each path (`methods`) and the headers of D16 on every answer.

    An answer of the admin panel (`is_admin`, Nogat DEV-15.13) carries `ADMIN_CSP`
    and ``Cache-Control: no-store`` whatever its route set; any other answer the
    page's policy and ``Cache-Control: no-cache`` unless its route set another.
    """

    def __init__(self, app: ASGIApp, *, policy: str) -> None:
        self.app = app
        self.headers = _security(policy)
        self.admin_headers = _security(ADMIN_CSP)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path = (
            scope["path"][len(scope.get("root_path", "")) :]
            if scope["path"].startswith(scope.get("root_path", ""))
            else scope["path"]
        )
        allowed = methods(path)
        admin = is_admin(path)
        headers = self.admin_headers if admin else self.headers

        async def wrapped(message: Message) -> None:
            if message["type"] == "http.response.start":
                given = list(message.get("headers", []))
                if admin:
                    given = [
                        pair for pair in given if pair[0].lower() != b"cache-control"
                    ]
                names = {name.lower() for name, _ in given}
                given += [pair for pair in headers if pair[0] not in names]
                if b"cache-control" not in names:
                    given.append(
                        (b"cache-control", b"no-store" if admin else b"no-cache")
                    )
                message["headers"] = given
            await send(message)

        if scope["method"] not in allowed:
            request = Request(scope, receive)
            lang = page_lang(request)
            exc = GuiError(
                "method_not_allowed",
                message(
                    "gui.errors.method_not_allowed",
                    method=scope["method"],
                    allowed=", ".join(allowed),
                ),
                headers={"Allow": ", ".join(allowed)},
            )
            body = dumps(error_body(exc, lang))
            response = Response(
                body,
                status_code=405,
                media_type="application/json",
                headers={"Allow": ", ".join(allowed), "Content-Language": lang},
            )
            await response(scope, receive, wrapped)
            return
        await self.app(scope, receive, wrapped)


# --- the app --------------------------------------------------------------------------------


def build_app(
    config: GuiConfig,
    *,
    state: GuiState | None = None,
    log: ServerLog | None = None,
) -> Starlette:
    """
    The app for resolved settings: routes, static files, middleware and lifespan.

    When the GUI's own directory and the data root overlap
    (`GuiConfig.writes_own_files`), the app writes none of its files (D7): no
    statistics, „Zgłoś uwagę” off; one warning says so.

    The static files take their type from `mimetypes`, which on Windows reads the
    registry (``application/javascript`` for a script, or ``text/plain`` after some
    installers), so ``.js`` and ``.mjs`` are registered there as ``text/javascript``
    (RFC 9239), the type of the page's scripts on every system.

    Parameters
    ----------
    config : GuiConfig
        The settings.
    state : GuiState or None, optional
        Prepared parts (tests give recorded live sources); built from ``config`` by default.
    log : ServerLog or None, optional
        Where the access log goes (Nogat DEV-12.4 to DEV-12.9): with it the outermost
        middleware is `AccessLog`, outside the rate limit, one record per request but
        the static content of `QUIET` answered below 400. None (default) logs no
        request, as a host with its own access log mounts the app; ``obserwator gui
        serve`` gives one.

    Returns
    -------
    Starlette
        The app.
    """
    if state is None:
        # A weak admin key: a warning here, an error at the start of an instance
        # (`GuiConfig.resolve`, ADR-025)
        check_credentials("admin", strict=config.instance is not None)
        writes = config.writes_own_files
        if not writes:
            LOG.warning(
                "%s",
                message(
                    "gui.server.gui_dir_in_root",
                    gui_dir=str(config.gui_dir),
                    root=str(config.root),
                ),
            )
        state = GuiState(
            config=config,
            root=DataRoot(config.root, scope=config.instance),
            analyses=Analyses(config.root),
            current=CurrentData(log=log),
            pmaxtp=Pmaxtp(log=log),
            traffic=TrafficState(
                limit=config.request_limit,
                window=config.request_window,
                directory=config.gui_dir,
                writes=writes,
            ),
            feedback=Feedback(config.gui_dir / "feedback.jsonl", writes=writes),
            terms=terms_page(config, WEB),
        )

    @contextlib.asynccontextmanager
    async def lifespan(app: Starlette) -> AsyncIterator[None]:
        await state.traffic.start()
        try:
            yield
        finally:
            await state.traffic.stop()

    for suffix in (".js", ".mjs"):
        mimetypes.add_type("text/javascript", suffix)
    site = Site.load(WEB)

    routes = [
        Route("/api/session", session),
        Route("/api/texts", texts),
        Route("/api/stations", stations),
        Route("/api/stations/{code}", station),
        Route("/api/series/{dataset}/{code}", series),
        Route("/api/analyses/{code}", analyses),
        Route("/api/analysis/{code}/{analysis}", analysis),
        Route("/api/current", current),
        Route("/api/current/{code}", current_station),
        Route("/api/pmaxtp", pmaxtp),
        Route("/api/downloads/stations", stations_downloads),
        Route("/api/downloads/{code}", downloads),
        Route("/api/files/stations", stations_file),
        Route("/api/files/series/{dataset}/{code}", series_file),
        Route("/api/files/analysis/{code}/{analysis}", analysis_file),
        Route("/api/files/analyses/{code}", analyses_file),
        Route("/api/files/pmaxtp", pmaxtp_file),
        Route("/api/handoff/{code}", handoff),
        Route("/api/prototype/stripes/{code}", _route(stripes_prototype)),
        Route("/api/feedback", post_feedback, methods=["POST"]),
        Route("/api/admin/feedback", admin_feedback),
        Route("/api/admin/feedback/{id}", admin_report, methods=["PATCH", "DELETE"]),
        Route("/api/admin/stats", admin_stats),
        Route("/api/admin/status", admin_status),
        Route("/api/admin", admin_not_found),
        Route("/api/admin/{rest:path}", admin_not_found),
        Route("/api/logo", logo),
        Route("/api/area", area_outline),
        Route("/api/{rest:path}", api_not_found),
        Route("/admin", admin_page),
        Route("/regulamin.html", regulamin),
        Route("/data/{name}", border),
        Route("/apple-touch-icon-precomposed.png", touch_icon),
        Route("/robots.txt", robots),
        Route("/", site.index),
        Route("/index.html", site.index),
        Mount("/", WebFiles(site=site, directory=WEB, html=True)),
    ]
    middleware = [
        Middleware(Traffic, state=state.traffic),
        Middleware(SecurityHeaders, policy=csp(config)),
        Middleware(GZipMiddleware, minimum_size=1024),
    ]
    if log is not None:
        middleware.insert(0, Middleware(AccessLog, log=log, quiet=QUIET))
    app = Starlette(routes=routes, middleware=middleware, lifespan=lifespan)
    app.state.gui = state
    return app
