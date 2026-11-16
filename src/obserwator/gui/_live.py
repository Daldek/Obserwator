"""
Live data through the server only, kept in memory and never stored (GUI plan D8).

- Snapshots of IMGW-PIB's current data (`fetch_hydro_states`, `fetch_hydro_current`,
  `fetch_meteo_current`, `fetch_synop`): each fetched on demand at most once per 10
  minutes, one request at a time (single flight), with the library's timeout. A failed
  refresh keeps the last snapshot, shown with its time, and the next try waits a minute.
- PMAXTP of a point (`fetch_pmaxtp`): per method and point at the four decimals of
  IMGW-PIB's address, 24 hours, at most 1,000 points, one live request at a time.

The page itself never calls a provider: it asks this server.
"""

from __future__ import annotations

import threading
import time
import unicodedata
from collections import OrderedDict
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import Any, Literal

import obserwator
from obserwator.exceptions import ObserwatorError
from obserwator.store.types import StationFeature

CURRENT_TTL_S = 600.0
"""How long a snapshot of IMGW-PIB's current data is served before it is fetched again."""
CURRENT_RETRY_S = 60.0
"""How long a failed fetch keeps further requests from asking IMGW-PIB again."""
PMAXTP_TTL_S = 86400.0
"""How long PMAXTP of a point is served from memory."""
PMAXTP_ENTRIES = 1000
"""How many points of PMAXTP stay in memory."""
PMAXTP_METHODS = ("POT", "AMP")
PmaxtpMethod = Literal["POT", "AMP"]


def utc_now() -> str:
    """The current UTC time, ISO 8601 with ``Z``, to the second."""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass(frozen=True)
class Snapshot:
    """
    The last answer of one IMGW-PIB source of current data, in memory only.

    Attributes
    ----------
    items : Mapping of str to dict, or None
        The records by station code; None before the first answer.
    fetched_at : str or None
        When they were fetched (UTC, ISO 8601 with ``Z``).
    error : ObserwatorError or None
        Why the last attempt failed; None when it answered.
    """

    items: Mapping[str, dict[str, Any]] | None = None
    fetched_at: str | None = None
    error: ObserwatorError | None = None


@dataclass
class _Source:
    """One source: its function, its last snapshot, when it last answered and was asked."""

    fetch: Callable[[], Any]
    snapshot: Snapshot = field(default_factory=Snapshot)
    ok_at: float = -1e18
    tried_at: float = -1e18
    lock: threading.Lock = field(default_factory=threading.Lock)


SOURCES: Mapping[str, Callable[[], Any]] = {
    "states": obserwator.fetch_hydro_states,
    "hydro": obserwator.fetch_hydro_current,
    "meteo": obserwator.fetch_meteo_current,
    "synop": obserwator.fetch_synop,
}
"""The sources of current data by the name the API gives them."""


class CurrentData:
    """
    The snapshots of IMGW-PIB's current data.

    Parameters
    ----------
    sources : Mapping of str to callable, optional
        A function per source returning its records (each with ``station_code`` and
        ``model_dump``); the library's fetchers by default, recorded answers in tests.
    clock : callable, optional
        Monotonic time in seconds.
    """

    def __init__(
        self,
        sources: Mapping[str, Callable[[], Any]] | None = None,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._sources = {
            name: _Source(fetch) for name, fetch in (sources or SOURCES).items()
        }
        self._clock = clock

    def get(self, name: str) -> Snapshot:
        """
        One source, fetched at most once per `CURRENT_TTL_S` (single flight).

        Parameters
        ----------
        name : str
            ``states``, ``hydro``, ``meteo`` or ``synop``.

        Returns
        -------
        Snapshot
            The last successful answer (``items`` None before the first one) and
            the error of the last attempt.
        """
        source = self._sources[name]
        with source.lock:
            now = self._clock()
            last = source.snapshot
            if last.items is not None and now - source.ok_at < CURRENT_TTL_S:
                return last
            if now - source.tried_at < CURRENT_RETRY_S:
                return last
            source.tried_at = now
            try:
                records = source.fetch()
            except ObserwatorError as exc:
                source.snapshot = replace(last, error=exc)
                return source.snapshot
            source.snapshot = Snapshot(
                {
                    str(record.station_code): record.model_dump(mode="json")
                    for record in records
                },
                utc_now(),
            )
            source.ok_at = now
            return source.snapshot


_STROKES = str.maketrans({0x141: "L"})
"""The letter L with a stroke, which Unicode does not decompose, as a plain L."""


def fold(text: str) -> str:
    """Upper case without diacritics, for comparing station names."""
    decomposed = unicodedata.normalize("NFKD", text.upper().translate(_STROKES))
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def synop_indices(features: Mapping[str, StationFeature]) -> dict[str, str]:
    """
    The WMO index of each synoptic station of IMGW-PIB's catalog, by its code.

    ``current synop`` names stations by their WMO index ``12NNN``; in IMGW-PIB's
    catalog a synoptic station's code is ``3PPLL0NNN`` (Kraków-Balice 350190566 is
    12566). A code is paired only when no other meteorological code of the catalog ends
    in the same ``0NNN``, and a report is shown only when its station's name begins the
    catalog's name (`synop_record`).
    """
    endings: dict[str, list[str]] = {}
    for code, feature in features.items():
        meteo = (
            feature.provider == "IMGW-PIB" and feature.properties.get("kind") == "meteo"
        )
        if meteo and len(code) == 9 and code[0] == "3" and code[5] == "0":
            endings.setdefault(code[6:], []).append(code)
    return {
        codes[0]: f"12{ending}" for ending, codes in endings.items() if len(codes) == 1
    }


def synop_record(
    code: str,
    feature: StationFeature,
    indices: Mapping[str, str],
    synop: Snapshot,
) -> dict[str, Any] | None:
    """The synoptic report of a catalog station, when its pairing holds by name."""
    index = indices.get(code)
    record = (synop.items or {}).get(index) if index else None
    if record is None:
        return None
    first = fold(str(record.get("station_name") or "")).replace("-", " ").split()
    name = fold(str(feature.properties.get("name") or ""))
    return record if first and name.startswith(first[0]) else None


def hydro_points(states: Snapshot, hydro: Snapshot) -> list[dict[str, Any]]:
    """Every hydrological station of either snapshot: its water state and latest values."""
    by_state = states.items or {}
    by_values = hydro.items or {}
    rows = []
    for code in dict.fromkeys([*by_state, *by_values]):
        state = by_state.get(code) or {}
        record = by_values.get(code) or {}
        lat = (
            state.get("latitude")
            if state.get("latitude") is not None
            else record.get("latitude")
        )
        lon = (
            state.get("longitude")
            if state.get("longitude") is not None
            else record.get("longitude")
        )
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


def meteo_points(meteo: Snapshot) -> list[dict[str, Any]]:
    """Every automatic meteorological station of the snapshot with its latest values."""
    return [
        {
            "code": code,
            "name": record.get("station_name"),
            "lat": record.get("latitude"),
            "lon": record.get("longitude"),
            "p10": record.get("precipitation_10min_mm"),
            "t": record.get("air_temp_c"),
            "t_at": record.get("air_temp_date"),
            "wind": record.get("wind_speed_ms"),
            "rh": record.get("humidity_percent"),
        }
        for code, record in (meteo.items or {}).items()
        if record.get("latitude") is not None and record.get("longitude") is not None
    ]


class Pmaxtp:
    """
    PMAXTP of points, kept in memory for a day.

    Parameters
    ----------
    fetch : callable, optional
        ``fetch(latitude, longitude, method=…)`` returning a `PMaxTPResult`;
        `obserwator.fetch_pmaxtp` by default, a recorded answer in tests.
    clock : callable, optional
        Monotonic time in seconds.
    """

    def __init__(
        self,
        fetch: Callable[..., Any] | None = None,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._fetch = fetch or obserwator.fetch_pmaxtp
        self._clock = clock
        self._points: OrderedDict[
            tuple[str, str, str], tuple[float, dict[str, Any]]
        ] = OrderedDict()
        self._cache = threading.Lock()
        self._live = threading.Lock()

    def _hit(self, key: tuple[str, str, str]) -> dict[str, Any] | None:
        with self._cache:
            hit = self._points.get(key)
            if hit and self._clock() - hit[0] < PMAXTP_TTL_S:
                self._points.move_to_end(key)
                return hit[1]
        return None

    def get(
        self, method: PmaxtpMethod, latitude: float, longitude: float
    ) -> dict[str, Any]:
        """
        PMAXTP of a point: the three tables (``ks``, ``sg``, ``rb``) and their axes.

        Parameters
        ----------
        method : {"POT", "AMP"}
            The method of the PMAXTP model.
        latitude, longitude : float
            The point, rounded to the four decimals of IMGW-PIB's address.

        Returns
        -------
        dict
            ``method``, ``latitude``, ``longitude``, ``durations`` [min],
            ``probabilities`` [%], ``data`` (the tables of the answer),
            ``fetched_at``, ``source_url`` (IMGW-PIB's own answer) and the
            equivalent ``command`` line.

        Raises
        ------
        ObserwatorError
            When IMGW-PIB refuses the point or does not answer.
        """
        key = (method, f"{latitude:.4f}", f"{longitude:.4f}")
        found = self._hit(key)
        if found is not None:
            return found
        with self._live:
            found = self._hit(key)
            if found is not None:
                return found
            result = self._fetch(latitude, longitude, method=method)
            data = result.data.model_dump(mode="json")
            first: dict[str, Any] = next(iter(data["ks"].values()), {})
            document = {
                "method": method,
                "latitude": latitude,
                "longitude": longitude,
                "durations": sorted(data["ks"], key=float),
                "probabilities": sorted(first, key=float),
                "data": {name: data[name] for name in ("ks", "sg", "rb")},
                "unit": "mm",
                "fetched_at": utc_now(),
                "source_url": obserwator.build_pmaxtp_url(
                    latitude, longitude, method=method
                ),
                "command": obserwator.format_command(
                    "pmaxtp fetch",
                    options={
                        "latitude": latitude,
                        "longitude": longitude,
                        "method": method,
                    },
                ),
            }
        with self._cache:
            self._points[key] = (self._clock(), document)
            self._points.move_to_end(key)
            while len(self._points) > PMAXTP_ENTRIES:
                self._points.popitem(last=False)
        return document
