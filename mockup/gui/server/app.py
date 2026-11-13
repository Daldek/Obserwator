"""The mockup's server: the page, a private GET-only API over the demo store, analyses.

Every response with provider data or results carries `attribution` and `terms_notice`
(Nogat DEV §20, ECO-060) from `server/attribution.py`.

Run: `OBSERWATOR_MOCKUP_ROOT=<store> uvicorn server.app:app --port 8060` from `mockup/gui`.
"""

from __future__ import annotations

import asyncio
import csv
import io
import json
import os
import shlex
import shutil
import tempfile
import threading
import time
import unicodedata
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.middleware import Middleware
from starlette.middleware.gzip import GZipMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles
from starlette.types import ASGIApp, Receive, Scope, Send

import obserwator
from obserwator import _environment as environment
from obserwator.messages import localize
from server import attribution, hydrolog_bridge
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
        "location_source": props.get("location_source"),
        "lon": lon,
        "lat": lat,
        "datasets": [d["dataset"] for d in datasets],
        "first": min(first)[:4] if first else None,
        "last": max(last)[:4] if last else None,
    }


STATIONS = [_station_entry(f) for f in store.catalog]
FEATURES = {f.station_code: f for f in store.catalog}
#: The sources of the whole catalog: the lines of the station list and of the map's „Stacje”.
CATALOG_SOURCES = sorted({source for f in store.catalog for source in attribution.station_sources(f.provider, f.properties)})


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
            "attribution": attribution.meta(),
            "mockup": True,
        }
    )


async def stations(request: Request) -> JSONResponse:
    return _json({"count": len(STATIONS), "stations": STATIONS, **attribution.fields(*CATALOG_SOURCES)})


async def station(request: Request) -> JSONResponse:
    """
    A station's catalog entry and coverage, with its lines; `attribution_parts` gives the
    lines of each part of its panel: the catalog, the series and the results computed
    from them (the current values carry theirs in api/current).
    """
    try:
        doc = _station_doc(request.path_params["code"])
    except NoData as exc:
        return _error(404, "not_found", str(exc))
    provider, props = doc["provider"], doc["properties"]
    catalog = attribution.fields(*attribution.station_sources(provider, props))
    held = bool(doc["datasets"])
    doc.update(catalog)
    doc["attribution_parts"] = {
        "catalog": catalog,
        "series": attribution.fields(*attribution.station_sources(provider, props, location=False)) if held else None,
        "results": attribution.fields(*attribution.station_sources(provider, props, location=False, results=True)) if held else None,
    }
    return _json(doc)


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
        **_dataset_fields(dataset),
    }
    if data.period is not None:
        out["period"] = data.period[mask]
        out["extremes"] = {
            k: [None if x is None else str(x)[:10] for x in v[mask]] for k, v in data.extra.items() if k.rsplit("_", 1)[0] in names
        }
    return _json(out)


def _dataset_fields(dataset: str) -> dict[str, list[str]]:
    """The attribution lines and terms of a dataset's series."""
    return attribution.fields(*attribution.dataset_sources(dataset, obserwator.get_dataset(dataset).provider))


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
    # A result is computed from the station's data; a precipitation card adds PMAXTP
    sources = attribution.station_sources(doc["provider"], doc["properties"], location=False, results=True)
    pmaxtp_part = result.get("pmaxtp")
    if isinstance(pmaxtp_part, dict) and pmaxtp_part.get("available"):
        sources.append("pmaxtp")
    result.update(attribution.fields(*sources))
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


# --- the shell: current IMGW-PIB data, PMAXTP, hand-off to Hydrolog, downloads -----------
#
# `api/current` serves snapshots of IMGW-PIB's current data kept in memory only (plan D8):
# without `station`, the points of the view „Pomiary bieżące” (hydrological stations from
# `current hydro-states` and `current hydro`, meteorological ones from `current meteo`);
# with `station`, that station's values for its section „Pomiary bieżące”, with the
# `current synop` report of a synoptic station. `api/pmaxtp` and `api/pmaxtp/file` serve
# PMAXTP of a point from a 24-hour cache (D8, D12). `api/handoff` builds the hand-off of a
# hydrological station's series to Hydrolog's statistics (D13, after Archiwista's
# `services/station_handoff.py`); `api/export` sends a series as Obserwator's own CSV
# (`export_series`) or as a columnar JSON document and `api/export/info` names the
# equivalent command line and the provider's licence (D14).

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
    "synop": obserwator.fetch_synop,
}
_SNAPSHOTS = {name: _Snapshot() for name in _CURRENT_SOURCES}


def _utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _hide_paths(text: str) -> str:
    """An error text without the server's paths (plan D6)."""
    return text.replace(str(ROOT), "<magazyn>").replace(tempfile.gettempdir(), "<tmp>")


def _polish(exc: obserwator.ObserwatorError) -> str:
    """The library's error in Polish where its catalog has the text, without paths."""
    return _hide_paths(str(localize(exc.detail, "pl")))


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
            snap.error = f"IMGW-PIB nie odpowiada: {_polish(exc)}"
            return snap
        snap.items = {record.station_code: record.model_dump(mode="json") for record in records}
        snap.fetched_at = _utc_now()
        snap.ok_at = now
        snap.error = None
        return snap


async def _snapshots(*names: str) -> dict[str, _Snapshot]:
    """Several sources at once, each through its own single flight."""
    snaps = await asyncio.gather(*(run_in_threadpool(_snapshot, name) for name in names))
    return dict(zip(names, snaps, strict=True))


def _snapshot_times(snaps: dict[str, _Snapshot]) -> dict[str, dict[str, str | None]]:
    return {name: {"fetched_at": snap.fetched_at, "error": snap.error} for name, snap in snaps.items()}


def _fold(text: str) -> str:
    """Upper case without diacritics, for comparing station names."""
    decomposed = unicodedata.normalize("NFKD", text.upper().replace("Ł", "L"))
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def _synop_indices() -> dict[str, str]:
    """
    The WMO index of each synoptic station of IMGW-PIB's catalog, by its nine-digit code.

    `current synop` names stations by their WMO index `12NNN`; in IMGW-PIB's catalog a
    synoptic station's code is `3PPLL0NNN` (Białystok 353230295 is 12295, Kraków-Balice
    350190566 is 12566). A code is paired only when no other meteorological code of the
    catalog ends in the same `0NNN`, and a report is shown only when its station's name
    begins the catalog's name (`_synop_record`). On 2026-11-13 this paired 61 of the 62
    stations of `current synop`; Platforma (12001) is not in the catalog.
    """
    endings: dict[str, list[str]] = {}
    for code, feature in FEATURES.items():
        if feature.provider == "IMGW-PIB" and feature.properties.get("kind") == "meteo":
            if len(code) == 9 and code[0] == "3" and code[5] == "0":
                endings.setdefault(code[6:], []).append(code)
    return {codes[0]: f"12{ending}" for ending, codes in endings.items() if len(codes) == 1}


SYNOP_INDICES = _synop_indices()


def _synop_record(code: str, synop: _Snapshot) -> dict[str, Any] | None:
    index = SYNOP_INDICES.get(code)
    record = (synop.items or {}).get(index) if index else None
    if record is None:
        return None
    first = _fold(record["station_name"]).replace("-", " ").split()[0]
    return record if _fold(FEATURES[code].properties.get("name") or "").startswith(first) else None


def _hydro_points(states: _Snapshot, hydro: _Snapshot) -> list[dict[str, Any]]:
    """Every hydrological station of either snapshot: its water state and its latest values."""
    by_state = states.items or {}
    by_values = hydro.items or {}
    rows = []
    for code in dict.fromkeys([*by_state, *by_values]):
        state = by_state.get(code) or {}
        record = by_values.get(code) or {}
        lat = state.get("latitude") if state.get("latitude") is not None else record.get("latitude")
        lon = state.get("longitude") if state.get("longitude") is not None else record.get("longitude")
        if lat is None or lon is None:
            continue
        rows.append(
            {
                "code": code,
                "name": record.get("station_name") or state.get("name"),
                "river": record.get("river") or state.get("river"),
                "lat": lat,
                "lon": lon,
                "state": state.get("water_state"),
                "h": record.get("water_level_cm"),
                "h_at": record.get("water_level_date"),
                "q": record.get("flow_m3s"),
                "q_at": record.get("flow_date"),
                "t": record.get("water_temp_c"),
                "t_at": record.get("water_temp_date"),
            }
        )
    return rows


def _meteo_points(meteo: _Snapshot) -> list[dict[str, Any]]:
    """Every automatic meteorological station of the snapshot with its latest values."""
    return [
        {
            "code": code,
            "name": record["station_name"],
            "lat": record["latitude"],
            "lon": record["longitude"],
            "p10": record["precipitation_10min_mm"],
            "t": record["air_temp_c"],
            "t_at": record["air_temp_date"],
            "wind": record["wind_speed_ms"],
            "rh": record["humidity_percent"],
        }
        for code, record in (meteo.items or {}).items()
        if record["latitude"] is not None and record["longitude"] is not None
    ]


async def current(request: Request) -> Response:
    """IMGW-PIB's current data: the points of „Pomiary bieżące”, or one station's values."""
    code = request.query_params.get("station")
    if not code:
        snaps = await _snapshots("states", "hydro", "meteo")
        if all(snap.items is None for snap in snaps.values()):
            errors = "; ".join(dict.fromkeys(snap.error for snap in snaps.values() if snap.error))
            return _error(503, "unavailable", errors or "Brak danych bieżących IMGW-PIB.")
        # Values of danepubliczne.imgw.pl and water states of hydro.imgw.pl
        return _json(
            {
                "source": "IMGW-PIB",
                "snapshots": _snapshot_times(snaps),
                "hydro": _hydro_points(snaps["states"], snaps["hydro"]),
                "meteo": _meteo_points(snaps["meteo"]),
                **attribution.fields("imgw", "imgw-hydro"),
            }
        )
    feature = FEATURES.get(code)
    if feature is None:
        return _error(404, "not_found", "Nie ma takiej stacji w katalogu.")
    if feature.provider != "IMGW-PIB":
        return _error(404, "no_data", "Dane bieżące ČHMÚ nie są udostępniane.")
    kind = feature.properties.get("kind")
    if kind == "hydro":
        snaps = await _snapshots("hydro", "states")
        main = snaps["hydro"]
    else:
        snaps = await _snapshots("meteo", "synop") if code in SYNOP_INDICES else await _snapshots("meteo")
        main = snaps["meteo"]
    if main.items is None:
        return _error(503, "unavailable", main.error or "Brak danych bieżących IMGW-PIB.")
    out: dict[str, Any] = {
        "station": code,
        "kind": kind,
        "source": "IMGW-PIB",
        "snapshots": _snapshot_times(snaps),
        "record": main.items.get(code),
        **attribution.fields(*(("imgw", "imgw-hydro") if kind == "hydro" else ("imgw",))),
    }
    if kind == "hydro":
        state = (snaps["states"].items or {}).get(code)
        out["state"] = state["water_state"] if state else None
    elif "synop" in snaps:
        out["synop"] = _synop_record(code, snaps["synop"])
    return _json(out)


#: How long PMAXTP of a point is served from memory [s] and how many points are kept (D8).
PMAXTP_TTL = 86400.0
PMAXTP_ENTRIES = 1000
PMAXTP_METHODS = ("POT", "AMP")
#: PMAXTP's own terms („Regulamin udostępniania danych projektu PMAXTP” on
#: https://klimat.imgw.pl/opady-maksymalne, read on 2026-11-13) replace IMGW-PIB's lines:
#: PS, PP and the monograph M (server/attribution.py). The page and the monograph's PDF
#: are links of the panel.
PMAXTP_LINKS = {
    "page": "https://klimat.imgw.pl/opady-maksymalne",
    "monograph": "https://www.imgw.pl/sites/default/files/2022-12/imgw-pib-monografia_modele-probabilistyczne-opadow-maksymalnych.pdf",
}
PMAXTP_TABLES = {
    "ks": "kwantyle opadu maksymalnego",
    "sg": "górne granice przedziału ufności kwantyli",
    "rb": "błędy estymacji kwantyli",
}

_PMAXTP: OrderedDict[tuple[str, str, str], tuple[float, dict[str, Any]]] = OrderedDict()
_PMAXTP_CACHE = threading.Lock()
_PMAXTP_LIVE = threading.Lock()  # one live request to IMGW-PIB at a time


def _pmaxtp_query(params: Any) -> tuple[str, float, float]:
    """Method and point of a request, the point at the four decimals of IMGW-PIB's URL."""
    method = params.get("method", "POT")
    if method not in PMAXTP_METHODS:
        raise BadParam("Metoda PMAXTP: POT albo AMP.")
    try:
        lat, lon = float(params.get("lat", "")), float(params.get("lon", ""))
    except ValueError:
        raise BadParam("Podaj szerokość i długość geograficzną w stopniach dziesiętnych.") from None
    if not (np.isfinite(lat) and np.isfinite(lon)):
        raise BadParam("Podaj szerokość i długość geograficzną w stopniach dziesiętnych.")
    return method, round(lat, 4), round(lon, 4)


def _sorted_keys(table: dict[str, Any]) -> list[str]:
    return sorted(table, key=float)


def _pmaxtp_doc(method: str, lat: float, lon: float) -> dict[str, Any]:
    """
    PMAXTP of a point (`fetch_pmaxtp`), served from memory for PMAXTP_TTL.

    One live request to IMGW-PIB at a time; a request waiting for it finds the point
    cached when an earlier one fetched it. Nothing is written anywhere.
    """
    key = (method, f"{lat:.4f}", f"{lon:.4f}")
    with _PMAXTP_CACHE:
        hit = _PMAXTP.get(key)
        if hit and time.monotonic() - hit[0] < PMAXTP_TTL:
            _PMAXTP.move_to_end(key)
            return hit[1]
    with _PMAXTP_LIVE:
        with _PMAXTP_CACHE:
            hit = _PMAXTP.get(key)
            if hit and time.monotonic() - hit[0] < PMAXTP_TTL:
                return hit[1]
        result = obserwator.fetch_pmaxtp(lat, lon, method=method)
        data = result.data.model_dump(mode="json")
        options = {"latitude": lat, "longitude": lon, "method": method}
        stem = f"pmaxtp_{method}_{key[1]}_{key[2]}"
        doc = {
            "schema": result.SCHEMA,
            "method": method,
            "latitude": lat,
            "longitude": lon,
            "durations": _sorted_keys(data["ks"]),
            "probabilities": _sorted_keys(next(iter(data["ks"].values()))),
            "data": data,
            "unit": "mm",
            "fetched_at": _utc_now(),
            "source_url": obserwator.build_pmaxtp_url(lat, lon, method=method),
            "command": obserwator.format_command("pmaxtp fetch", options=options),
            "files": {"csv": f"{stem}.csv", "json": f"{stem}.json"},
            "tables": PMAXTP_TABLES,
            "links": PMAXTP_LINKS,
            **attribution.fields("pmaxtp"),
        }
    with _PMAXTP_CACHE:
        _PMAXTP[key] = (time.monotonic(), doc)
        _PMAXTP.move_to_end(key)
        while len(_PMAXTP) > PMAXTP_ENTRIES:
            _PMAXTP.popitem(last=False)
    return doc


def _pmaxtp_csv(doc: dict[str, Any]) -> str:
    """
    One header row, then a row per table and duration with a column per probability [%],
    and the columns `attribution` and `terms_notice`: PMAXTP's lines and terms one per
    cell from the first data row down (DEV-20.5). UTF-8, comma, dot decimal, CRLF.
    """
    probabilities = doc["probabilities"]
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\r\n")
    writer.writerow(["method", "latitude", "longitude", "table", "duration [min]", *(f"p={p}% [mm]" for p in probabilities), "attribution", "terms_notice"])
    rows = [(table, duration) for table in ("ks", "sg", "rb") for duration in doc["durations"]]
    lines = attribution.spread(doc["attribution"], len(rows))
    terms = attribution.spread(doc.get("terms_notice", []), len(rows))
    for index, (table, duration) in enumerate(rows):
        row = doc["data"][table].get(duration, {})
        writer.writerow([doc["method"], f"{doc['latitude']:.4f}", f"{doc['longitude']:.4f}", table, duration, *(row.get(p, "") for p in probabilities), lines[index], terms[index]])
    return out.getvalue()


def _pmaxtp_file_document(doc: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": "obserwator-pmaxtp-export/1",
        "note": "Makieta: układ dokumentu z planu GUI Obserwatora (D12, D14); schemat jeszcze nie istnieje.",
        "result": {key: doc[key] for key in ("schema", "method", "latitude", "longitude", "data")},
        "tables": doc["tables"],
        "units": {"ks": "mm", "sg": "mm", "rb": "mm", "duration": "min", "probability": "%"},
        "fetched_at": doc["fetched_at"],
        "source_url": doc["source_url"],
        **attribution.fields("pmaxtp"),
    }


async def _pmaxtp_answer(request: Request) -> dict[str, Any] | Response:
    try:
        method, lat, lon = _pmaxtp_query(request.query_params)
        return await run_in_threadpool(_pmaxtp_doc, method, lat, lon)
    except BadParam as exc:
        return _error(400, "validation_error", str(exc))
    except obserwator.ObserwatorValidationError as exc:
        return _error(400, "validation_error", _polish(exc))
    except obserwator.ObserwatorError as exc:
        return _error(503, "unavailable", f"IMGW-PIB: {_polish(exc)}")


async def pmaxtp(request: Request) -> Response:
    """PMAXTP of a point: the three tables, their files and IMGW-PIB's own address of the answer."""
    doc = await _pmaxtp_answer(request)
    return doc if isinstance(doc, Response) else _json(doc)


async def pmaxtp_file(request: Request) -> Response:
    """PMAXTP of a point as a file packed by the server: CSV or JSON with PMAXTP's terms."""
    fmt = request.query_params.get("format", "csv")
    if fmt not in ("csv", "json"):
        return _error(400, "validation_error", "Format: csv albo json.")
    doc = await _pmaxtp_answer(request)
    if isinstance(doc, Response):
        return doc
    if fmt == "json":
        body = json.dumps(_clean(_pmaxtp_file_document(doc)), ensure_ascii=False, indent=1).encode()
        media = "application/json"
    else:
        body = _pmaxtp_csv(doc).encode()
        media = "text/csv; charset=utf-8"
    name = doc["files"][fmt]
    return Response(body, media_type=media, headers={"Content-Disposition": f'attachment; filename="{name}"', "Cache-Control": "no-cache"})


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
        # The provider's lines and terms travel with the series (DEV-20.6, DEV-20.7)
        **_dataset_fields(origin["dataset"]),
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


def _licence(dataset: str) -> dict[str, Any]:
    """The provider's licence of a dataset and its terms page; the lines are `attribution`."""
    descriptor = obserwator.get_dataset(dataset)
    provider = obserwator.get_provider(descriptor.provider)
    return {
        "provider": provider.short_name,
        "licence": descriptor.license.id,
        "url": descriptor.license.url,
        "terms_url": descriptor.license.terms_url,
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
        "licence": _licence(dataset),
        **_dataset_fields(dataset),
    }


async def export(request: Request) -> Response:
    """
    A station's series as a file: Obserwator's CSV (`export_series`) or the JSON document.

    The CSV keeps every row and column of `export_series`, whose first data row has the
    columns `attribution_source` and `attribution_processed`, and adds the columns
    `attribution` and `terms_notice` of DEV-20.5, which the library does not write yet.
    """
    params = request.query_params
    code = params.get("station", "")
    dataset = params.get("dataset", "")
    fmt = params.get("format", "csv")
    if fmt not in ("csv", "json"):
        return _error(400, "validation_error", "Format: csv albo json.")
    if not _holds(dataset, code):
        return _error(404, "not_found", "Stacja nie ma szeregu tego zbioru.")
    name = _export_name(code, dataset, fmt)
    headers = {"Content-Disposition": f'attachment; filename="{name}"', "Cache-Control": "no-cache"}
    if fmt == "json":
        doc = await run_in_threadpool(_export_document, dataset, code)
        body = json.dumps(_clean(doc), ensure_ascii=False).encode()
        return Response(body, media_type="application/json", headers=headers)
    folder = Path(tempfile.mkdtemp(prefix="obserwator-mockup-"))
    try:
        await run_in_threadpool(obserwator.export_series, root=ROOT, dataset=dataset, station=code, format="csv", output=folder / name)
        text = (folder / name).read_bytes().decode("utf-8")  # CRLF rows kept as written
    except (obserwator.ObserwatorError, OSError) as exc:
        return _error(422, str(getattr(exc, "code", "io_error")), _hide_paths(str(exc)))
    finally:
        shutil.rmtree(folder, ignore_errors=True)
    sources = attribution.dataset_sources(dataset, obserwator.get_dataset(dataset).provider)
    body = attribution.with_columns(text, *sources).encode()
    return Response(body, media_type="text/csv; charset=utf-8", headers=headers)


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
    return _json({"station": code, "dataset": dataset, "files": names, "command": line, "licence": _licence(dataset), **_dataset_fields(dataset)})


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
        Route("/api/pmaxtp", pmaxtp),
        Route("/api/pmaxtp/file", pmaxtp_file),
        Route("/api/handoff", handoff),
        Route("/api/export", export),
        Route("/api/export/info", export_info),
        Mount("/", StaticFiles(directory=WEB, html=True)),
    ],
    middleware=[Middleware(SecurityHeaders), Middleware(GZipMiddleware, minimum_size=1024)],
)
