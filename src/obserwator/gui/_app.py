"""
The GUI's Starlette app: the page, its private GET API and ``POST api/feedback``.

Routes are relative to the page, so the app works at ``/`` and mounted under any prefix
(GUI plan D5, D6). They serve this GUI only: no ``/api/v1``, no OpenAPI, no stability
promise (a deviation from AGI-6.1 recorded in ``CLAUDE.md``). Every parameter is checked
before the data root or Hydrolog is touched; an error is ``obserwator-error/1`` with the
registry's status, in the page's language, without server paths.
"""

from __future__ import annotations

import contextlib
import csv
import io
import logging
import shutil
import tempfile
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from datetime import date
from functools import partial
from pathlib import Path
from typing import Any

from anyio import to_thread
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.gzip import GZipMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles
from starlette.types import ASGIApp, Message, Receive, Scope, Send

import obserwator
from obserwator.attribution import (
    ORIGINS,
    Attribution,
    attribution,
    dataset_origin,
    provider_origin,
)
from obserwator.datasets import get_dataset, get_provider, providers
from obserwator.exceptions import ObserwatorError
from obserwator.gui import _params as params
from obserwator.gui._analyses import PROCESSES, TIMEOUT_S, Analyses
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
    json_response,
    page_lang,
)
from obserwator.gui._live import (
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
from obserwator.gui._root import DataRoot, Snapshot
from obserwator.gui._standin import StandIn
from obserwator.gui._state import GuiState
from obserwator.gui._terms import terms_page
from obserwator.gui._traffic import Traffic, TrafficState
from obserwator.messages import LANGS, message
from obserwator.messages.gui import MESSAGES as TEXTS

LOG = logging.getLogger(__name__)
WEB = Path(__file__).resolve().parent / "web"
DATA = Path(obserwator.__file__).resolve().parent / "_data"
BORDERS = {
    "poland_border_wgs84.geojson": DATA / "poland_border_wgs84.geojson",
    "czechia_border_wgs84.geojson": DATA / "czechia_border_wgs84.geojson",
}
"""The packaged borders, the map's background without a basemap (D9)."""
SESSION_SCHEMA = "obserwator-gui-session/1"
HANDOFF_SCHEMA = "nogat-handoff/1"
SERIES_SCHEMA = "hydrolog-series/1"
HYDRO_DAILY = ("pl.imgw.hydro_daily", "cz.chmi.hydro_daily")
PMAXTP_TABLES = ("ks", "sg", "rb")
SEXT = {
    "csv": "text/csv; charset=utf-8",
    "json": "application/json",
    "parquet": "application/vnd.apache.parquet",
}

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


async def _thread[T](function: Callable[[], T]) -> T:
    """Run a blocking read in a worker thread, at most four at a time (D7)."""
    return await to_thread.run_sync(function, limiter=_LIMITER)


_LIMITER: Any = None


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


def _station_origins(
    provider: str, properties: Mapping[str, Any], *, location: bool
) -> Attribution:
    """The lines of what is shown of a station: its provider, hydro.imgw.pl's locations."""
    lines = attribution(provider_origin(provider))
    if (
        location
        and provider == "IMGW-PIB"
        and properties.get("location_source") == "static"
    ):
        lines = lines | attribution("imgw_hydro")
    return lines


# --- the session and the texts ------------------------------------------------------


@_route
async def session(request: Request) -> Response:
    """``obserwator-gui-session/1``: versions, the data root, providers, basemap, menus."""
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
    document = {
        "schema": SESSION_SCHEMA,
        "version": {"obserwator": state.version, "hydrolog": hydrolog},
        "root": {
            "catalogs": {p: v.to_dict() for p, v in snapshot.catalogs.items()},
            "series": {
                key: {
                    **series.version.to_dict(),
                    "year_type": series.index.year_type,
                    "stations": len(series.index.stations),
                }
                for key, series in snapshot.series.items()
            },
            "analyses": None,
            "error": None
            if snapshot.error is None
            else error_body(snapshot.error, lang),
        },
        "providers": {
            provider.id: {
                "short_name": provider.short_name,
                "name": provider.name,
                **attribution(provider_origin(provider.id)).fields(),
            }
            for provider in providers()
        },
        "attribution": {
            "origins": {origin: attribution(origin).fields() for origin in ORIGINS},
            "order": list(attribution(*ORIGINS).attribution),
            "terms_order": list(attribution(*ORIGINS).terms_notice),
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
    }
    return json_response(request, document)


@_route
async def texts(request: Request) -> Response:
    """The area ``gui`` of the message catalog in one language (``lang``: pl or en)."""
    params.only(request.query_params, ("lang",))
    lang = params.choice(request.query_params.get("lang"), "lang", LANGS, "pl")
    document = {
        "lang": lang,
        "texts": {key: getattr(text, lang) for key, text in TEXTS.items()},
    }
    return json_response(
        request, document, etag=etag_of("texts", lang, _gui(request).version)
    )


# --- stations and series --------------------------------------------------------------


@_route
async def stations(request: Request) -> Response:
    """The station layer: every station of the current catalogs and the series holding it."""
    params.only(request.query_params, ())
    snapshot = await _thread(lambda: _snapshot(request))
    lines = Attribution()
    for feature in snapshot.features.values():
        lines = lines | _station_origins(
            feature.provider, feature.properties, location=True
        )
    document = {**snapshot.layer, **lines.fields()}
    return json_response(request, document, etag=snapshot.layer_etag)


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
    catalog = _station_origins(feature.provider, props, location=True)
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
        **catalog.fields(),
        "attribution_parts": {
            "catalog": catalog.fields(),
            "series": series_lines.fields() if held else None,
            "results": series_lines.fields() if held else None,
        },
    }
    _gui(request).traffic.count("stations_opened")
    return json_response(request, document, etag=etag_of("station", snapshot.key, code))


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
    dataset = params.choice(
        request.path_params["dataset"], "dataset", tuple(snapshot.series)
    )
    code = _station(request, snapshot)
    if code not in snapshot.series[dataset].index.stations:
        raise GuiError(
            "not_found",
            message("gui.errors.no_series", station=code, dataset=dataset),
            details={"option": "station", "value": code},
        )
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
    return json_response(request, body, etag=etag_of(base, variables, start, end))


# --- analyses ---------------------------------------------------------------------------


@_route
async def analyses(request: Request) -> Response:
    """The analysis ids of a station: stored summaries, or those that apply (before O2)."""
    params.only(request.query_params, ())
    state = _gui(request)
    snapshot = await _thread(lambda: _snapshot(request))
    code = _station(request, snapshot)
    found = await _thread(lambda: state.analyses.list(snapshot, code))
    document = {
        "station": code,
        "analyses": list(found),
        "compute": state.analyses.can_compute,
    }
    return json_response(
        request,
        document,
        etag=etag_of("analyses", snapshot.key, code, state.analyses.can_compute),
    )


@_route
async def analysis(request: Request) -> Response:
    """One analysis id of a station: the stored result, or one computed with the overrides."""
    state = _gui(request)
    snapshot = await _thread(lambda: _snapshot(request))
    code = _station(request, snapshot)
    name = request.path_params["analysis"]
    overrides = state.analyses.overrides(name, dict(request.query_params))
    result, etag = await state.analyses.get(snapshot, code, name, overrides)
    state.traffic.count("analyses_run")
    return json_response(request, result, etag=etag)


@_route
async def analysis_file(request: Request) -> Response:
    """One analysis id's result as a JSON file: the same document as `analysis`."""
    state = _gui(request)
    snapshot = await _thread(lambda: _snapshot(request))
    code = _station(request, snapshot)
    name = request.path_params["analysis"]
    overrides = state.analyses.overrides(name, dict(request.query_params))
    result, etag = await state.analyses.get(snapshot, code, name, overrides)
    state.traffic.count("downloads")
    return attachment(
        request,
        dumps(result, indent=2),
        filename=f"{code}_{name}.json",
        media_type="application/json",
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
async def current(request: Request) -> Response:
    """The points of „Pomiary bieżące”: IMGW-PIB's hydrological and meteorological stations."""
    params.only(request.query_params, ())
    live = _gui(request).current
    names = ("states", "hydro", "meteo")
    snaps = {name: await _thread(partial(live.get, name)) for name in names}
    if all(snap.items is None for snap in snaps.values()):
        error = next(
            (snap.error for snap in snaps.values() if snap.error is not None), None
        )
        raise error or GuiError("source_unavailable", message("gui.errors.no_current"))
    lang = page_lang(request)
    document = {
        "source": "IMGW-PIB",
        "snapshots": _snapshot_times(snaps, lang),
        "hydro": hydro_points(snaps["states"], snaps["hydro"]),
        "meteo": meteo_points(snaps["meteo"]),
        **attribution("imgw", "imgw_hydro").fields(),
    }
    return json_response(request, document)


@_route
async def current_station(request: Request) -> Response:
    """One station's current values (IMGW-PIB only), with its synoptic report where paired."""
    params.only(request.query_params, ())
    snapshot = await _thread(lambda: _snapshot(request))
    code = _station(request, snapshot)
    feature = snapshot.features[code]
    if feature.provider != "IMGW-PIB":
        raise GuiError(
            "not_found",
            message("gui.errors.no_current_chmi"),
            details={"reason": "provider"},
        )
    live = _gui(request).current
    kind = feature.properties.get("kind")
    indices = synop_indices(snapshot.features)
    names = (
        ("hydro", "states")
        if kind == "hydro"
        else (("meteo", "synop") if code in indices else ("meteo",))
    )
    snaps = {name: await _thread(partial(live.get, name)) for name in names}
    main = snaps[names[0]]
    if main.items is None:
        raise main.error or GuiError(
            "source_unavailable", message("gui.errors.no_current")
        )
    lang = page_lang(request)
    document: dict[str, Any] = {
        "station": code,
        "kind": kind,
        "source": "IMGW-PIB",
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
    return json_response(request, document)


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
async def pmaxtp_file(request: Request) -> Response:
    """PMAXTP of a point as a file packed by the server: CSV or JSON with PMAXTP's lines."""
    query = request.query_params
    params.only(query, ("latitude", "longitude", "method", "format"))
    fmt = params.choice(query.get("format"), "format", ("csv", "json"), "csv")
    method, latitude, longitude = _pmaxtp_query(query)
    document = await _thread(
        lambda: _gui(request).pmaxtp.get(method, latitude, longitude)
    )
    stem = f"pmaxtp_{method}_{latitude:.4f}_{longitude:.4f}"
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
    return attachment(request, body, filename=f"{stem}.{fmt}", media_type=SEXT[fmt])


# --- files and command lines -------------------------------------------------------------


SERIES_FORMATS: tuple[str, ...] = ("csv",)
"""The formats of `export_series`; JSON and Parquet join when S0 (ADR-014) lands."""


def _series_formats() -> tuple[str, ...]:
    """The formats a series file may be downloaded in."""
    return SERIES_FORMATS


def _command_line(dataset: str, code: str, fmt: str) -> str:
    """The equivalent command line: the CLI's default root stands for the server's."""
    name = f"{code}_{get_dataset(dataset).slug}.{fmt}"
    options: dict[str, Any] = {"dataset": dataset, "station": code, "output": name}
    if fmt != "csv":
        options["format"] = fmt
    return obserwator.format_command("series export", options=options)


@_route
async def downloads(request: Request) -> Response:
    """The files of a station: each series in each format, its command line and licence."""
    params.only(request.query_params, ())
    snapshot = await _thread(lambda: _snapshot(request))
    code = _station(request, snapshot)
    formats = _series_formats()
    files = []
    for entry in snapshot.datasets_of(code):
        dataset = entry["dataset"]
        descriptor = get_dataset(dataset)
        files.append(
            {
                "dataset": dataset,
                "version": entry["version"],
                "formats": {
                    fmt: {
                        "file": f"{code}_{descriptor.slug}.{fmt}",
                        "url": f"api/files/series/{dataset}/{code}?format={fmt}",
                        "command": _command_line(dataset, code, fmt),
                    }
                    for fmt in formats
                },
                "licence": {
                    "provider": get_provider(descriptor.provider).short_name,
                    "id": descriptor.license.id,
                    "url": descriptor.license.url,
                    "terms_url": descriptor.license.terms_url,
                },
                **attribution(dataset_origin(dataset)).fields(),
            }
        )
    return json_response(
        request,
        {"station": code, "series": files},
        etag=etag_of("downloads", snapshot.key, code, formats),
    )


@_route
async def series_file(request: Request) -> Response:
    """A station's series as a file, made by `export_series` exactly as the CLI makes it."""
    query = request.query_params
    params.only(query, ("format",))
    snapshot = await _thread(lambda: _snapshot(request))
    dataset = params.choice(
        request.path_params["dataset"], "dataset", tuple(snapshot.series)
    )
    code = _station(request, snapshot)
    if code not in snapshot.series[dataset].index.stations:
        raise GuiError(
            "not_found", message("gui.errors.no_series", station=code, dataset=dataset)
        )
    fmt = params.choice(query.get("format"), "format", _series_formats(), "csv")
    state = _gui(request)
    name = f"{code}_{get_dataset(dataset).slug}.{fmt}"

    def export() -> bytes:
        folder = Path(tempfile.mkdtemp(prefix="obserwator-gui-file-"))
        try:
            options: dict[str, Any] = {
                "root": state.config.root,
                "dataset": dataset,
                "station": code,
                "output": folder / name,
            }
            if fmt != "csv":
                options["format"] = fmt
            obserwator.export_series(**options)
            return (folder / name).read_bytes()
        finally:
            shutil.rmtree(folder, ignore_errors=True)

    body = await _thread(export)
    state.traffic.count("downloads")
    return attachment(
        request,
        body,
        filename=name,
        media_type=SEXT[fmt],
        etag=etag_of("file", snapshot.series[dataset].version.sha256, code, fmt),
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
    query = dict(request.query_params)
    state = _gui(request)
    snapshot = await _thread(lambda: _snapshot(request))
    code = _station(request, snapshot)
    feature = snapshot.features[code]
    props = dict(feature.properties)
    variable = params.choice(query.pop("variable", None), "variable", ("Q", "H"), "Q")
    resolution = params.choice(
        query.pop("resolution", None), "resolution", ("daily", "annual"), "daily"
    )
    name = str(props.get("name") or code)
    river = f" ({props['river']})" if props.get("river") else ""
    producer = {
        "tool": "obserwator",
        "version": state.version,
        "page": _page_address(request, code),
    }
    if resolution == "daily":
        first = params.year(query.pop("first_year", None), "first_year")
        last = params.year(query.pop("last_year", None), "last_year")
        params.years(first, last, first_option="first_year", last_option="last_year")
        params.only(query, ())
        dataset = next(
            (
                key
                for key in HYDRO_DAILY
                if key in snapshot.series
                and code in snapshot.series[key].index.stations
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
        analysis_id = query.pop("analysis", f"flood_frequency.{variable}")
        overrides = state.analyses.overrides(analysis_id, query)
        result_doc, _ = await state.analyses.get(snapshot, code, analysis_id, overrides)
        if result_doc.get("status") != "ok":
            raise GuiError(
                "not_found", message("gui.errors.no_values", variable=variable)
            )
        found = result_doc["envelope"]["result"]
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
            "years": found["hydrological_years"],
            "values": found["annual_maxima"],
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
    """The station's page in this GUI: the deployment's address, else this server's."""
    base = _gui(request).config.gui.get("obserwator") or str(request.base_url)
    return f"{base.rstrip('/')}/?station={code}"


# --- pages ------------------------------------------------------------------------------


@_route
async def regulamin(request: Request) -> Response:
    """``regulamin.html`` (DEV-15.7): the kit's terms filled for the deployment."""
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


class SecurityHeaders:
    """GET and HEAD only (``POST api/feedback`` alone), and the headers of D16 on every answer."""

    def __init__(self, app: ASGIApp, *, policy: str) -> None:
        self.app = app
        self.headers = [
            (b"content-security-policy", policy.encode()),
            (b"x-frame-options", b"DENY"),
            (b"x-content-type-options", b"nosniff"),
            (b"referrer-policy", b"no-referrer"),
            (b"cross-origin-opener-policy", b"same-origin"),
            (b"cross-origin-resource-policy", b"same-origin"),
            (b"permissions-policy", b"camera=(), microphone=(), geolocation=()"),
        ]

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path = (
            scope["path"][len(scope.get("root_path", "")) :]
            if scope["path"].startswith(scope.get("root_path", ""))
            else scope["path"]
        )
        allowed = ("POST",) if path == "/api/feedback" else ("GET", "HEAD")
        headers = self.headers

        async def wrapped(message: Message) -> None:
            if message["type"] == "http.response.start":
                given = list(message.get("headers", []))
                names = {name.lower() for name, _ in given}
                given += [pair for pair in headers if pair[0] not in names]
                if b"cache-control" not in names:
                    given.append((b"cache-control", b"no-cache"))
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


def build_app(config: GuiConfig, *, state: GuiState | None = None) -> Starlette:
    """
    The app for resolved settings: routes, static files, middleware and lifespan.

    Parameters
    ----------
    config : GuiConfig
        The settings.
    state : GuiState or None, optional
        Prepared parts (tests give recorded live sources); built from ``config`` by default.

    Returns
    -------
    Starlette
        The app.
    """
    from anyio import CapacityLimiter

    global _LIMITER
    if _LIMITER is None:
        _LIMITER = CapacityLimiter(4)
    if state is None:
        standin = StandIn(config.root, config.hydrolog_command)
        state = GuiState(
            config=config,
            root=DataRoot(config.root),
            analyses=Analyses(standin),
            current=CurrentData(),
            pmaxtp=Pmaxtp(),
            traffic=TrafficState(
                limit=config.request_limit,
                window=config.request_window,
                state_dir=config.state_dir,
            ),
            feedback=Feedback(config.state_dir / "feedback.jsonl"),
            terms=terms_page(config, WEB),
        )

    @contextlib.asynccontextmanager
    async def lifespan(app: Starlette) -> AsyncIterator[None]:
        await state.traffic.start()
        try:
            yield
        finally:
            await state.traffic.stop()
            state.analyses.backend.close()

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
        Route("/api/downloads/{code}", downloads),
        Route("/api/files/series/{dataset}/{code}", series_file),
        Route("/api/files/analysis/{code}/{analysis}", analysis_file),
        Route("/api/files/pmaxtp", pmaxtp_file),
        Route("/api/handoff/{code}", handoff),
        Route("/api/feedback", post_feedback, methods=["POST"]),
        Route("/api/{rest:path}", api_not_found),
        Route("/regulamin.html", regulamin),
        Route("/data/{name}", border),
        Mount("/", StaticFiles(directory=WEB, html=True)),
    ]
    app = Starlette(
        routes=routes,
        middleware=[
            Middleware(Traffic, state=state.traffic),
            Middleware(SecurityHeaders, policy=csp(config)),
            Middleware(GZipMiddleware, minimum_size=1024),
        ],
        lifespan=lifespan,
    )
    app.state.gui = state
    return app
