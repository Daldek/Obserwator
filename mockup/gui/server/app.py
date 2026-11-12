"""The mockup's server: the page, a private GET-only API over the demo store, analyses.

Run: `OBSERWATOR_MOCKUP_ROOT=<store> uvicorn server.app:app --port 8060` from `mockup/gui`.
"""

from __future__ import annotations

import json
import os
import shlex
import shutil
import tempfile
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
from starlette.applications import Starlette
from starlette.background import BackgroundTask
from starlette.concurrency import run_in_threadpool
from starlette.middleware import Middleware
from starlette.middleware.gzip import GZipMiddleware
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles
from starlette.types import ASGIApp, Receive, Scope, Send

import obserwator
from obserwator import _environment as environment
from obserwator.messages import message
from server import hydrolog_bridge
from server.analyses import BadParam, Context, NoData, Params, registry
from server.store import Store

WEB = Path(__file__).resolve().parent.parent / "web"
ROOT = Path(os.environ.get("OBSERWATOR_MOCKUP_ROOT", "/home/claude-agent/data/obserwator-demo/store"))
BASEMAP = "https://tiles.openfreemap.org"

store = Store(ROOT)
ANALYSES = registry()


# --- stations ------------------------------------------------------------------------


def _station_entry(feature: Any) -> dict[str, Any]:
    props = dict(feature.properties)
    datasets = store.datasets_of(feature.station_code)
    first = [v["first"] for d in datasets for v in d["variables"].values() if v["first"]]
    last = [v["last"] for d in datasets for v in d["variables"].values() if v["last"]]
    lon, lat = feature.geometry if feature.geometry else (None, None)
    return {
        "code": feature.station_code,
        "name": props.get("name"),
        "river": props.get("river"),
        "provider": feature.provider,
        "kind": props.get("kind"),
        "meteo_kind": props.get("meteo_kind"),
        "active": props.get("active"),
        "lon": lon,
        "lat": lat,
        "datasets": [d["dataset"] for d in datasets],
        "first": min(first)[:4] if first else None,
        "last": max(last)[:4] if last else None,
    }


STATIONS = [_station_entry(f) for f in store.catalog]
FEATURES = {f.station_code: f for f in store.catalog}


def _station_doc(code: str) -> dict[str, Any]:
    feature = FEATURES.get(code)
    if feature is None:
        raise NoData("Nie ma takiej stacji w katalogu.")
    props = dict(feature.properties)
    lon, lat = feature.geometry if feature.geometry else (None, None)
    return {
        "code": code,
        "provider": feature.provider,
        "lon": lon,
        "lat": lat,
        "properties": props,
        "datasets": store.datasets_of(code),
    }


# --- responses -----------------------------------------------------------------------


def _clean(value: Any) -> Any:
    """JSON-ready: NaN and inf as null, numpy scalars and arrays as Python values."""
    if isinstance(value, dict):
        return {str(k): _clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(v) for v in value]
    if isinstance(value, np.ndarray):
        return _clean(value.tolist())
    if isinstance(value, (np.floating, float)):
        number = float(value)
        return number if np.isfinite(number) else None
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.bool_):
        return bool(value)
    if isinstance(value, np.datetime64):
        return str(value.astype("datetime64[D]"))
    return value


def _json(payload: Any, status: int = 200) -> JSONResponse:
    return JSONResponse(_clean(payload), status_code=status, headers={"Cache-Control": "no-cache"})


def _error(status: int, code: str, text: str) -> JSONResponse:
    return _json({"schema": "obserwator-error/1", "code": code, "title": text}, status)


# --- routes --------------------------------------------------------------------------


async def meta(request: Request) -> JSONResponse:
    return _json(
        {
            "obserwator": obserwator.__version__,
            "hydrolog": hydrolog_bridge.VERSION,
            "series": {k: {"version": v.name, "year_type": v.year_type, "stations": len(v.stations)} for k, v in store.versions.items()},
            "analyses": {name: {"kind": a.kind, "title": a.title} for name, a in ANALYSES.items()},
            "gui": environment.gui_addresses() or {},
            "mockup": True,
        }
    )


async def stations(request: Request) -> JSONResponse:
    return _json({"count": len(STATIONS), "stations": STATIONS})


async def station(request: Request) -> JSONResponse:
    try:
        return _json(_station_doc(request.path_params["code"]))
    except NoData as exc:
        return _error(404, "not_found", str(exc))


async def series(request: Request) -> JSONResponse:
    """A station's series of one dataset: dates, values (null = missing) and flags."""
    code = request.path_params["code"]
    dataset = request.query_params.get("dataset", "")
    if dataset not in store.versions or code not in store.versions[dataset].stations:
        return _error(404, "not_found", "Stacja nie ma szeregu tego zbioru.")
    data = store.series(dataset, code)
    wanted = request.query_params.get("variables")
    names = [v for v in (wanted.split(",") if wanted else data.values) if v in data.values]
    start = request.query_params.get("from")
    end = request.query_params.get("to")
    mask = np.ones(len(data.dates), dtype=bool)
    try:
        if start:
            mask &= data.dates >= np.datetime64(start)
        if end:
            mask &= data.dates <= np.datetime64(end)
    except ValueError:
        return _error(400, "validation_error", "Daty w formacie RRRR-MM-DD.")
    flags: dict[str, list[list[Any]]] = {}
    for name in names:
        marked = data.flags[name][mask]
        flags[name] = [[int(i), str(f)] for i, f in enumerate(marked) if f not in ("value", "missing")]
    out = {
        "dataset": dataset,
        "station": code,
        "version": data.version,
        "year_type": store.versions[dataset].year_type,
        "dates": [str(d) for d in data.dates[mask]],
        "hydro_year": data.hydro_year[mask],
        "units": {n: data.units.get(n) for n in names},
        "values": {n: data.values[n][mask] for n in names},
        "flags": flags,
        "attribution": _attribution(dataset),
    }
    if data.period is not None:
        out["period"] = data.period[mask]
        out["extremes"] = {
            k: [None if x is None else str(x)[:10] for x in v[mask]] for k, v in data.extra.items() if k.rsplit("_", 1)[0] in names
        }
    return _json(out)


def _attribution(dataset: str) -> str:
    return obserwator.get_provider(obserwator.get_dataset(dataset).provider).processed_attribution


_RESULTS: OrderedDict[tuple[str, ...], dict[str, Any]] = OrderedDict()
_RESULTS_LOCK = threading.Lock()


def _run_analysis(name: str, code: str, params: Params) -> dict[str, Any]:
    key = (name, code, *sorted(f"{k}={v}" for k, v in params.items()))
    with _RESULTS_LOCK:
        if key in _RESULTS:
            _RESULTS.move_to_end(key)
            return _RESULTS[key]
    doc = _station_doc(code)
    props = dict(doc["properties"], provider=doc["provider"])
    ctx = Context(store, code, props, doc["datasets"])
    result = ANALYSES[name].function(ctx, params)
    result.setdefault("analysis", name)
    result.setdefault("station", code)
    with _RESULTS_LOCK:
        _RESULTS[key] = result
        while len(_RESULTS) > 500:
            _RESULTS.popitem(last=False)
    return result


async def analysis(request: Request) -> Response:
    from starlette.concurrency import run_in_threadpool

    name = request.path_params["name"]
    if name not in ANALYSES:
        return _error(404, "not_found", "Nie ma takiej analizy.")
    params = Params(request.query_params)
    code = params.pop("station", "")
    try:
        return _json(await run_in_threadpool(_run_analysis, name, code, params))
    except BadParam as exc:
        return _error(400, "validation_error", str(exc))
    except NoData as exc:
        return _error(404, "no_data", str(exc))
    except hydrolog_bridge.HydrologFailed as exc:
        return _error(422, exc.code, f"Hydrolog ({exc.command}): {exc.text}")


# --- the shell: current IMGW-PIB data, hand-off to Hydrolog, downloads ------------------
#
# `api/current` serves snapshots of IMGW-PIB's current data kept in memory only (plan D8);
# `api/handoff` builds the hand-off of a hydrological station's series to Hydrolog's
# statistics (D13, after Archiwista's `services/station_handoff.py`); `api/export` sends a
# series as Obserwator's own CSV (`export_series`) or as a columnar JSON document and
# `api/export/info` names the equivalent command line and the provider's licence (D14).

#: How long a snapshot of IMGW-PIB's current data is served before it is fetched again [s].
CURRENT_TTL = 600.0
#: How long a failed fetch keeps further requests from asking IMGW-PIB again [s].
CURRENT_RETRY = 60.0


@dataclass
class _Snapshot:
    """The last answer of one IMGW-PIB source of current data, in memory only."""

    items: dict[str, dict[str, Any]] | None = None  # station code -> record
    fetched_at: str | None = None  # UTC time of the last successful fetch
    ok_at: float = -1e9  # time.monotonic() of the last success
    tried_at: float = -1e9  # time.monotonic() of the last attempt
    error: str | None = None  # why the last attempt failed; None after a success
    lock: threading.Lock = field(default_factory=threading.Lock)


_CURRENT_SOURCES = {
    "states": obserwator.fetch_hydro_states,
    "hydro": obserwator.fetch_hydro_current,
    "meteo": obserwator.fetch_meteo_current,
}
_SNAPSHOTS = {name: _Snapshot() for name in _CURRENT_SOURCES}


def _utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _hide_paths(text: str) -> str:
    """An error text without the server's paths (plan D6)."""
    return text.replace(str(ROOT), "<magazyn>").replace(tempfile.gettempdir(), "<tmp>")


def _snapshot(name: str) -> _Snapshot:
    """
    One source of IMGW-PIB's current data, fetched at most once per CURRENT_TTL.

    Single flight: while one request asks IMGW-PIB, the others wait for its answer. A
    failed refresh keeps the last snapshot (shown with its time and the error) and the
    next attempt waits CURRENT_RETRY. Nothing is written anywhere.
    """
    snap = _SNAPSHOTS[name]
    with snap.lock:
        now = time.monotonic()
        if snap.items is not None and now - snap.ok_at < CURRENT_TTL:
            return snap
        if now - snap.tried_at < CURRENT_RETRY:
            return snap
        snap.tried_at = now
        try:
            records = _CURRENT_SOURCES[name]()
        except obserwator.ObserwatorError as exc:
            snap.error = f"IMGW-PIB nie odpowiada: {_hide_paths(str(exc))}"
            return snap
        snap.items = {record.station_code: record.model_dump(mode="json") for record in records}
        snap.fetched_at = _utc_now()
        snap.ok_at = now
        snap.error = None
        return snap


async def current(request: Request) -> Response:
    """IMGW-PIB's current data: the water states of every hydro station, or one station's values."""
    code = request.query_params.get("station")
    if not code:
        if request.query_params.get("layer", "states") != "states":
            return _error(400, "validation_error", "Warstwa danych bieżących: states.")
        snap = await run_in_threadpool(_snapshot, "states")
        if snap.items is None:
            return _error(503, "unavailable", snap.error or "Brak danych bieżących IMGW-PIB.")
        rows = [
            {
                "code": code,
                "name": item["name"],
                "river": item["river"],
                "lat": item["latitude"],
                "lon": item["longitude"],
                "state": item["water_state"],
            }
            for code, item in snap.items.items()
        ]
        return _json({"layer": "states", "source": "IMGW-PIB", "fetched_at": snap.fetched_at, "error": snap.error, "stations": rows})
    feature = FEATURES.get(code)
    if feature is None:
        return _error(404, "not_found", "Nie ma takiej stacji w katalogu.")
    if feature.provider != "IMGW-PIB":
        return _error(404, "no_data", "Dane bieżące ČHMÚ nie są udostępniane.")
    kind = feature.properties.get("kind")
    snap = await run_in_threadpool(_snapshot, "hydro" if kind == "hydro" else "meteo")
    if snap.items is None:
        return _error(503, "unavailable", snap.error or "Brak danych bieżących IMGW-PIB.")
    out: dict[str, Any] = {
        "station": code,
        "kind": kind,
        "source": "IMGW-PIB",
        "fetched_at": snap.fetched_at,
        "error": snap.error,
        "record": snap.items.get(code),
    }
    if kind == "hydro":
        states = await run_in_threadpool(_snapshot, "states")
        state = (states.items or {}).get(code)
        out["state"] = state["water_state"] if state else None
        out["state_fetched_at"] = states.fetched_at
    return _json(out)


HANDOFF_SCHEMA = "nogat-handoff/1"
SERIES_SCHEMA = "hydrolog-series/1"
DAILY_HYDRO = ("pl.imgw.hydro_daily", "cz.chmi.hydro_daily")
HALF_YEAR = "pl.imgw.hydro_semiannual"
#: How an annual maximum comes from the half-year characteristics: Archiwista's rule (A-ADR-051).
ANNUAL_RULE = "greater of the winter and summer maxima of the half-year characteristics"


def _holds(dataset: str, code: str) -> bool:
    version = store.versions.get(dataset)
    return version is not None and code in version.stations


def _year(text: str | None, name: str) -> int | None:
    if not text:
        return None
    try:
        return int(text)
    except ValueError:
        raise BadParam(f"{name}: rok, liczba całkowita.") from None


def _handoff_doc(code: str, variable: str, resolution: str | None, first: int | None, last: int | None, page: str) -> dict[str, Any]:
    """
    The `nogat-handoff/1` of a hydrological station's series around a `hydrolog-series/1`.

    `daily`: every day from the first to the last value of the variable within the
    hydrological years first..last, a day without a value (no row, missing, accumulated)
    as null. `annual`: the annual maxima of the half-year characteristics, the greater of
    the winter and summer maxima; a year missing one of them is null and named in
    `left_out`. Without `resolution` the daily series when the store has it.
    """
    feature = FEATURES.get(code)
    if feature is None:
        raise NoData("Nie ma takiej stacji w katalogu.")
    props = dict(feature.properties)
    if props.get("kind") != "hydro":
        raise NoData("Do Hydrologa przekazuje się szeregi stacji hydrologicznych.")
    daily = next((key for key in DAILY_HYDRO if _holds(key, code)), None)
    resolution = resolution or ("daily" if daily else "annual")
    station_name = props.get("name") or code
    origin: dict[str, Any] = {"source": feature.provider.lower(), "provider": feature.provider, "station": code}
    if resolution == "daily":
        if daily is None:
            raise NoData("Magazyn nie ma (jeszcze) dobowego szeregu tej stacji.")
        data = store.series(daily, code)
        if variable not in data.values:
            raise NoData(f"Szereg dobowy tej stacji nie ma zmiennej {variable}.")
        values = data.values[variable]
        keep = np.isfinite(values) & (data.flags[variable] != "accumulated")
        if first is not None:
            keep &= data.hydro_year >= first
        if last is not None:
            keep &= data.hydro_year <= last
        found = np.flatnonzero(keep)
        if not found.size:
            raise NoData(f"W wybranych latach nie ma wartości {variable}.")
        start, end = data.dates[found[0]], data.dates[found[-1]]
        days = np.arange(start, end + np.timedelta64(1, "D"), dtype="datetime64[D]")
        by_day = np.full(days.size, np.nan)
        by_day[(data.dates[found] - start).astype(int)] = values[found]
        payload: dict[str, Any] = {
            "schema": SERIES_SCHEMA,
            "name": f"{station_name} — {variable}",
            "variable": variable,
            "unit": data.units[variable],
            "step": "day",
            "dates": [str(day) for day in days],
            "values": by_day,
        }
        origin.update(dataset=daily, series_version=data.version)
        what = "wartości dobowe"
    elif resolution == "annual":
        if not _holds(HALF_YEAR, code):
            raise NoData("Magazyn nie ma półrocznych charakterystyk tej stacji.")
        data = store.series(HALF_YEAR, code)
        column = f"{variable}_max"
        halves: dict[int, dict[str, float]] = {}
        for year, period, value in zip(data.hydro_year, data.period, data.values[column]):
            if period in ("winter", "summer"):
                halves.setdefault(int(year), {})[period] = float(value)
        years = sorted(y for y in halves if (first is None or y >= first) and (last is None or y <= last))
        maxima: list[float | None] = []
        left_out: list[int] = []
        for year in years:
            winter = halves[year].get("winter", np.nan)
            summer = halves[year].get("summer", np.nan)
            if np.isfinite(winter) and np.isfinite(summer):
                maxima.append(max(winter, summer))
            else:
                maxima.append(None)
                left_out.append(year)
        if all(value is None for value in maxima):
            raise NoData(f"W wybranych latach nie ma maksimów rocznych {variable}.")
        payload = {
            "schema": SERIES_SCHEMA,
            "name": f"{station_name} — {variable}",
            "variable": variable,
            "unit": data.units[column],
            "step": "year",
            "statistic": "max",
            "year_type": "hydrological",
            "years": years,
            "values": maxima,
        }
        origin.update(dataset=HALF_YEAR, series_version=data.version, rule=ANNUAL_RULE, left_out=left_out)
        what = "maksima roczne"
    else:
        raise BadParam("resolution: daily albo annual.")
    river = f" ({props['river']})" if props.get("river") else ""
    return {
        "schema": HANDOFF_SCHEMA,
        "created_at": _utc_now(),
        "producer": {"tool": "obserwator", "version": obserwator.__version__, "page": page},
        "subject": f"{station_name}{river} — {variable}, {what}",
        "provenance": {"series": origin},
        "payload": payload,
    }


def _page_address(request: Request, code: str) -> str:
    """The page of a station in this GUI: the deployment's address from nogat.toml, else this server's."""
    base = (environment.gui_addresses() or {}).get("obserwator") or str(request.base_url)
    return f"{base.rstrip('/')}/?station={code}"


async def handoff(request: Request) -> Response:
    """A station's series handed to Hydrolog: `nogat-handoff/1` around `hydrolog-series/1`."""
    params = request.query_params
    code = params.get("station", "")
    variable = params.get("variable", "Q")
    resolution = params.get("resolution") or None
    if variable not in ("Q", "H"):
        return _error(400, "validation_error", "Zmienna: Q albo H.")
    try:
        first = _year(params.get("from"), "from")
        last = _year(params.get("to"), "to")
        doc = await run_in_threadpool(_handoff_doc, code, variable, resolution, first, last, _page_address(request, code))
    except BadParam as exc:
        return _error(400, "validation_error", str(exc))
    except NoData as exc:
        return _error(404, "no_data", str(exc))
    return _json(doc)


_NOTICES = {"IMGW-PIB": "datasets.provider_notice_imgw", "CHMI": "datasets.provider_notice_chmi"}


def _licence(dataset: str) -> dict[str, Any]:
    """The provider's attribution formulas, licence and notice of a dataset (Polish)."""
    descriptor = obserwator.get_dataset(dataset)
    provider = obserwator.get_provider(descriptor.provider)
    return {
        "provider": provider.short_name,
        "attribution": descriptor.license.attribution,
        "processed": provider.processed_attribution,
        "licence": descriptor.license.id,
        "url": descriptor.license.url,
        "terms_url": descriptor.license.terms_url,
        "notice": str(message(_NOTICES[provider.id], lang="pl")),
    }


def _export_name(code: str, dataset: str, extension: str) -> str:
    return f"{code}_{dataset}.{extension}"


def _export_document(dataset: str, code: str) -> dict[str, Any]:
    """A station's whole series as one columnar JSON document with units and attribution."""
    data = store.series(dataset, code)
    feature = FEATURES[code]
    columns: dict[str, Any] = {"date": [str(day) for day in data.dates], "hydro_year": data.hydro_year}
    if data.period is not None:
        columns["period"] = data.period
    for name, values in data.values.items():
        columns[name] = values
        columns[f"{name}_flag"] = data.flags[name]
        for suffix in ("start", "end"):
            extra = data.extra.get(f"{name}_{suffix}")
            if extra is not None:
                columns[f"{name}_{suffix}"] = [None if day is None else str(day)[:10] for day in extra]
    return {
        "schema": "obserwator-series-export/1",
        "note": "Makieta: układ dokumentu z planu GUI Obserwatora (D14); schemat jeszcze nie istnieje.",
        "dataset": dataset,
        "station": code,
        "name": feature.properties.get("name"),
        "river": feature.properties.get("river"),
        "provider": feature.provider,
        "series_version": data.version,
        "year_type": store.versions[dataset].year_type,
        "units": data.units,
        "rows": int(data.dates.size),
        "columns": columns,
        "attribution": _licence(dataset),
    }


async def export(request: Request) -> Response:
    """A station's series as a file: Obserwator's CSV (`export_series`) or the JSON document."""
    params = request.query_params
    code = params.get("station", "")
    dataset = params.get("dataset", "")
    fmt = params.get("format", "csv")
    if fmt not in ("csv", "json"):
        return _error(400, "validation_error", "Format: csv albo json.")
    if not _holds(dataset, code):
        return _error(404, "not_found", "Stacja nie ma szeregu tego zbioru.")
    name = _export_name(code, dataset, fmt)
    if fmt == "json":
        doc = await run_in_threadpool(_export_document, dataset, code)
        body = json.dumps(_clean(doc), ensure_ascii=False).encode()
        return Response(body, media_type="application/json", headers={"Content-Disposition": f'attachment; filename="{name}"', "Cache-Control": "no-cache"})
    folder = Path(tempfile.mkdtemp(prefix="obserwator-mockup-"))
    try:
        await run_in_threadpool(obserwator.export_series, root=ROOT, dataset=dataset, station=code, format="csv", output=folder / name)
    except (obserwator.ObserwatorError, OSError) as exc:
        shutil.rmtree(folder, ignore_errors=True)
        return _error(422, str(getattr(exc, "code", "io_error")), _hide_paths(str(exc)))
    return FileResponse(
        folder / name,
        media_type="text/csv; charset=utf-8",
        filename=name,
        headers={"Cache-Control": "no-cache"},
        background=BackgroundTask(shutil.rmtree, folder, True),
    )


async def export_info(request: Request) -> Response:
    """The files of a station's series, the equivalent command line and the licence."""
    params = request.query_params
    code = params.get("station", "")
    dataset = params.get("dataset", "")
    if not _holds(dataset, code):
        return _error(404, "not_found", "Stacja nie ma szeregu tego zbioru.")
    names = {fmt: _export_name(code, dataset, fmt) for fmt in ("csv", "json")}
    # Obserwator's canonical line; the server's root left out (the CLI's default root
    # stands in for it) and the output a bare file name
    target = Path(tempfile.gettempdir()) / names["csv"]
    line = obserwator.format_command(
        "series export",
        options={"root": str(ROOT), "dataset": dataset, "station": code, "format": "csv", "output": str(target)},
    )
    line = line.replace(f" --root {shlex.quote(str(ROOT))}", "").replace(shlex.quote(str(target)), shlex.quote(names["csv"]))
    return _json({"station": code, "dataset": dataset, "files": names, "command": line, "licence": _licence(dataset)})


# --- security headers ----------------------------------------------------------------

CSP = "; ".join(
    [
        "default-src 'self'",
        "script-src 'self'",
        "style-src 'self' 'unsafe-inline'",
        # MapLibre's module worker is a same-origin file (vendor/maplibre-gl), no blob: (D16)
        "worker-src 'self'",
        f"img-src 'self' data: blob: {BASEMAP}",
        f"connect-src 'self' {BASEMAP}",
        "font-src 'self'",
        "object-src 'none'",
        "base-uri 'none'",
        "form-action 'self'",
        "frame-ancestors 'none'",
    ]
)
HEADERS = [
    (b"content-security-policy", CSP.encode()),
    (b"x-frame-options", b"DENY"),
    (b"x-content-type-options", b"nosniff"),
    (b"referrer-policy", b"no-referrer"),
    (b"permissions-policy", b"camera=(), microphone=(), geolocation=()"),
]


class SecurityHeaders:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        if scope["method"] not in ("GET", "HEAD"):
            await Response("Method Not Allowed", 405, headers={"Allow": "GET, HEAD"})(scope, receive, send)
            return

        async def wrapped(message: dict[str, Any]) -> None:
            if message["type"] == "http.response.start":
                message.setdefault("headers", [])
                message["headers"] = list(message["headers"]) + HEADERS
                if not scope["path"].startswith("/api/"):
                    message["headers"].append((b"cache-control", b"no-cache"))
            await send(message)

        await self.app(scope, receive, wrapped)


app = Starlette(
    routes=[
        Route("/api/meta", meta),
        Route("/api/stations", stations),
        Route("/api/station/{code}", station),
        Route("/api/series/{code}", series),
        Route("/api/analysis/{name}", analysis),
        Route("/api/current", current),
        Route("/api/handoff", handoff),
        Route("/api/export", export),
        Route("/api/export/info", export_info),
        Mount("/", StaticFiles(directory=WEB, html=True)),
    ],
    middleware=[Middleware(SecurityHeaders), Middleware(GZipMiddleware, minimum_size=1024)],
)
