"""
Live data through the server only, kept in memory, never in a root (GUI plan D8).

Every answer of a provider's current data the server fetches also goes, as it came, to
the capture spool of ``state_dir`` (``<state_dir>/obserwator/captures``, ADR-030 D7):
the library's fetchers and the providers' adapters hand it on (`obserwator.captures`),
so ``store sync`` of the capture datasets seals it into the raw root later; the GUI
writes no root. A spool that cannot be written is one warning record, and the answer
is served all the same.

- Snapshots of IMGW-PIB's current data (`fetch_hydro_states`, `fetch_hydro_current`,
  `fetch_meteo_current`, `fetch_synop`): each fetched on demand at most once per 10
  minutes, one request per source at a time (single flight), with the library's
  timeout, the sources of one request at the same time. An expired snapshot is served
  while its refresh runs in the background; only a source that never answered makes a
  request wait. A failed refresh keeps the last snapshot, shown with its time, and the
  next try waits a minute.
- PMAXTP of a point (`fetch_pmaxtp`): per method and point at the four decimals of
  IMGW-PIB's address, 24 hours, at most 1,000 points, one live request at a time.
- The live tail of a station's chart in „teraz” (O6, `LiveTail`): the hours after its
  newest stored hour, asked of its provider's adapter (`ProviderAdapter.live_tail`:
  hydro-back with ``hoursInterval`` the hours since then and one, at most 1,000;
  ČHMÚ's ``now`` file) when that hour is older than the current one, kept 10 minutes
  for at most 500 stations, one request per station at a time and one live request
  for the whole server.

Every request to a provider is one app record ``upstream_fetch`` (`log_fetch`,
`log_tail`): its source, duration, outcome and error code, never a client's address.

The page itself never calls a provider: it asks this server.
"""

from __future__ import annotations

import itertools
import logging
import math
import threading
import time
import unicodedata
from array import array
from collections import OrderedDict
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from functools import partial
from typing import TYPE_CHECKING, Any, Literal

import obserwator
from obserwator.datasets import get_provider, providers
from obserwator.exceptions import ObserwatorError
from obserwator.fetch import DEFAULT_TIMEOUT
from obserwator.messages import Message, message
from obserwator.store.subdaily import tail_hours
from obserwator.store.types import StationFeature

if TYPE_CHECKING:
    from obserwator.nogat_logging import ServerLog
    from obserwator.providers.base import Answer

_LOG = logging.getLogger(__name__)


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
FETCH_EVENT = "upstream_fetch"
"""The ``event`` of the app record of a request to a provider (`log_fetch`, `log_tail`)."""
TAIL_TTL_S = CURRENT_TTL_S
"""How long a station's live tail is served before it is asked again (O6)."""
TAIL_RETRY_S = CURRENT_RETRY_S
"""How long a failed live tail keeps its station from being asked again."""
TAIL_STATIONS = 500
"""How many stations' live tails stay in memory at most."""
TAIL_HOURS = 1000
"""The most hours a live tail asks back (hydro-back's ``hoursInterval``)."""
_HOUR = timedelta(hours=1)

_SERIALS = itertools.count(1)
"""The serial numbers of the snapshots of the process, each new one the next."""


def utc_now() -> str:
    """The current UTC time, ISO 8601 with ``Z``, to the second."""
    return iso_utc(datetime.now(UTC))


def iso_utc(moment: datetime) -> str:
    """An instant in UTC, ISO 8601 with ``Z``, to the second."""
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def log_fetch(
    log: ServerLog | None,
    source: str,
    seconds: float,
    *,
    records: int | None = None,
    error: BaseException | None = None,
) -> None:
    """
    One app record of a request to IMGW-PIB: its source, duration, outcome, error code.

    ``info`` for an answer, ``warning`` for an `ObserwatorError` (IMGW-PIB failed or
    refused; its code), ``error`` with the trace for any other exception (a defect of
    this program, code ``internal_error``). Never a client's address or a point.

    Parameters
    ----------
    log : ServerLog or None
        The server's logs (``nogat-log/1``); None logs through `logging`, for a host
        that mounts the app with its own logs.
    source : str
        ``states``, ``hydro``, ``meteo``, ``synop`` or ``pmaxtp``.
    seconds : float
        How long the request took.
    records : int or None, optional
        The records of an answer of current data; None for PMAXTP.
    error : BaseException or None, optional
        Why the request failed; None when it answered.
    """
    duration_ms = round(seconds * 1000)
    if error is not None:
        text = message(
            "gui.server.upstream_failed",
            source=source,
            duration_ms=duration_ms,
            code=error.code if isinstance(error, ObserwatorError) else "internal_error",
            reason=str(error),
        )
    elif records is None:
        text = message("gui.server.upstream_ok", source=source, duration_ms=duration_ms)
    else:
        text = message(
            "gui.server.upstream_records",
            source=source,
            duration_ms=duration_ms,
            records=records,
        )
    _record(log, text, error)


def _record(log: ServerLog | None, text: Message, error: BaseException | None) -> None:
    """
    One app record ``upstream_fetch``, its level by the request's outcome.

    ``info`` for an answer, ``warning`` for an `ObserwatorError`, ``error`` with the
    trace for any other exception (a defect of this program).
    """
    level = logging.INFO
    info = None
    if isinstance(error, ObserwatorError):
        level = logging.WARNING
    elif error is not None:
        level = logging.ERROR
        info = (type(error), error, error.__traceback__)
    if log is not None:
        log.application(level, FETCH_EVENT, str(text), info)
    else:
        _LOG.log(level, "%s", text, exc_info=info, extra={"event": FETCH_EVENT})


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
    serial : int
        Unique in the process for each answer or failure of a source (0 before the
        first): an answer made from the same serials is the same (its ETag).
    """

    items: Mapping[str, dict[str, Any]] | None = None
    fetched_at: str | None = None
    error: ObserwatorError | None = None
    serial: int = 0


@dataclass
class _Source:
    """One source: its function, its last snapshot, when it answered and was asked."""

    fetch: Callable[[], Any]
    snapshot: Snapshot = field(default_factory=Snapshot)
    ok_at: float = -1e18
    tried_at: float = -1e18
    running: threading.Event | None = None
    """Set when the refresh that runs ends; None while none runs."""


def _in_thread(run: Callable[[], None]) -> None:
    """Run ``run`` in a daemon thread, which a stop of the server does not wait for."""
    threading.Thread(target=run, name="obserwator-current", daemon=True).start()


CURRENT_PROVIDER = next(item.id for item in providers() if item.adapter.current)
"""The provider of the current measurements view: the only live data the GUI serves."""
SOURCES: Mapping[str, Callable[[], Any]] = get_provider(
    CURRENT_PROVIDER
).adapter.current
"""The sources of current data by the name the API gives them (its adapter's, ADR-029)."""


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
    log : ServerLog or None, optional
        Where each request to IMGW-PIB is logged (`log_fetch`).
    start : callable, optional
        Runs a refresh in the background: a daemon thread by default.
    """

    def __init__(
        self,
        sources: Mapping[str, Callable[[], Any]] | None = None,
        *,
        clock: Callable[[], float] = time.monotonic,
        log: ServerLog | None = None,
        start: Callable[[Callable[[], None]], None] = _in_thread,
    ) -> None:
        self._sources = {
            name: _Source(fetch) for name, fetch in (sources or SOURCES).items()
        }
        self._clock = clock
        self._log = log
        self._start = start
        self._lock = threading.Lock()

    def get(self, name: str) -> Snapshot:
        """
        One source, as `get_many` gives it.

        Parameters
        ----------
        name : str
            ``states``, ``hydro``, ``meteo`` or ``synop``.

        Returns
        -------
        Snapshot
            The last successful answer and the error of the last attempt.
        """
        return self.get_many((name,))[name]

    def get_many(self, names: Iterable[str]) -> dict[str, Snapshot]:
        """
        Sources, each fetched at most once per `CURRENT_TTL_S`, all at the same time.

        A source whose snapshot expired starts its refresh in the background (one at a
        time, the next try a `CURRENT_RETRY_S` after a failure) and gives its last
        snapshot at once; only a source without any answer yet is waited for.

        Parameters
        ----------
        names : iterable of str
            Of ``states``, ``hydro``, ``meteo`` and ``synop``.

        Returns
        -------
        dict of str to Snapshot
            Per name the last successful answer (``items`` None before the first one)
            and the error of the last attempt.
        """
        names = tuple(names)
        started: list[Callable[[], None]] = []
        waits: list[threading.Event] = []
        with self._lock:
            now = self._clock()
            for name in names:
                source = self._sources[name]
                if source.running is None and self._due(source, now):
                    source.tried_at = now
                    source.running = threading.Event()
                    started.append(
                        partial(self._refresh, name, source, source.running, now)
                    )
                if source.running is not None and source.snapshot.items is None:
                    waits.append(source.running)
        for run in started:
            self._start(run)
        for done in waits:
            done.wait()
        with self._lock:
            return {name: self._sources[name].snapshot for name in names}

    @staticmethod
    def _due(source: _Source, now: float) -> bool:
        fresh = source.snapshot.items is not None and now - source.ok_at < CURRENT_TTL_S
        return not fresh and now - source.tried_at >= CURRENT_RETRY_S

    def _refresh(
        self, name: str, source: _Source, done: threading.Event, asked_at: float
    ) -> None:
        """Fetch one source and keep its answer, or its error beside the last one."""
        began = time.perf_counter()
        try:
            records = source.fetch()
            items = {
                str(record.station_code): record.model_dump(mode="json")
                for record in records
            }
        except Exception as exc:
            # IMGW-PIB failed (an ObserwatorError, kept beside the last answer) or this
            # program did (logged with its trace): the last answer stays.
            log_fetch(self._log, name, time.perf_counter() - began, error=exc)
            if isinstance(exc, ObserwatorError):
                with self._lock:
                    source.snapshot = replace(
                        source.snapshot, error=exc, serial=next(_SERIALS)
                    )
        else:
            log_fetch(self._log, name, time.perf_counter() - began, records=len(items))
            with self._lock:
                source.snapshot = Snapshot(items, utc_now(), serial=next(_SERIALS))
                source.ok_at = asked_at
        finally:
            with self._lock:
                source.running = None
            done.set()


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
            feature.provider == CURRENT_PROVIDER
            and feature.properties.get("kind") == "meteo"
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
                "q_stale": record.get("flow_stale"),
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
    log : ServerLog or None, optional
        Where each request to IMGW-PIB is logged (`log_fetch`), without the point.
    """

    def __init__(
        self,
        fetch: Callable[..., Any] | None = None,
        *,
        clock: Callable[[], float] = time.monotonic,
        log: ServerLog | None = None,
    ) -> None:
        self._fetch = fetch or obserwator.fetch_pmaxtp
        self._clock = clock
        self._log = log
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
            began = time.perf_counter()
            try:
                result = self._fetch(latitude, longitude, method=method)
            except ObserwatorError as exc:
                log_fetch(self._log, "pmaxtp", time.perf_counter() - began, error=exc)
                raise
            log_fetch(self._log, "pmaxtp", time.perf_counter() - began)
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


# --- the live tail of a station's chart in „teraz” (O6) -----------------------------------


def _utc() -> datetime:
    """The current UTC time."""
    return datetime.now(UTC)


def utc_hour(moment: datetime) -> datetime:
    """The start of the UTC hour of an instant."""
    return moment.astimezone(UTC).replace(minute=0, second=0, microsecond=0)


def tail_asked(since: datetime | None, now: datetime) -> int:
    """
    The hours a live tail asks back (``hoursInterval``): those since ``since``, and one.

    Parameters
    ----------
    since : datetime or None
        The newest stored hour of the station (UTC); None when none is stored.
    now : datetime
        The current time.

    Returns
    -------
    int
        The whole hours from ``since`` to the current hour and one more, at least 1
        and at most `TAIL_HOURS`; `TAIL_HOURS` without a stored hour.
    """
    if since is None:
        return TAIL_HOURS
    return max(1, min(TAIL_HOURS, (utc_hour(now) - since) // _HOUR + 1))


def log_tail(
    log: ServerLog | None,
    provider: str,
    seconds: float,
    *,
    hours: int = 0,
    error: BaseException | None = None,
) -> None:
    """
    One app record ``upstream_fetch`` of a live tail's request (`_record`).

    Its provider, duration, the hours it gave or its error code; never a client's
    address or the station asked.

    Parameters
    ----------
    log : ServerLog or None
        The server's logs; None logs through `logging`.
    provider : str
        The provider asked.
    seconds : float
        How long the request took.
    hours : int, optional
        The hours with a value it gave.
    error : BaseException or None, optional
        Why the request failed; None when it answered.
    """
    name = get_provider(provider).short_name
    duration_ms = round(seconds * 1000)
    if error is not None:
        text = message(
            "gui.server.tail_failed",
            provider=name,
            duration_ms=duration_ms,
            code=error.code if isinstance(error, ObserwatorError) else "internal_error",
            reason=str(error),
        )
    else:
        text = message(
            "gui.server.tail_hours", provider=name, duration_ms=duration_ms, hours=hours
        )
    _record(log, text, error)


@dataclass(frozen=True)
class Tail:
    """
    The live tail of one station: the full hours of its provider's answers, in memory.

    Attributes
    ----------
    start : datetime or None
        The first hour of ``values`` (UTC); None without any hour.
    values : Mapping of str to array of float
        Per variable the value of every hour from ``start`` (NaN without one), each
        column as long as the others: the hours after the stored ones when it was asked.
    asked_at : datetime or None
        When it was asked (UTC).
    hours : int
        The hours it asked back (``hoursInterval``).
    fetched_at : str or None
        When the answers came (UTC, ISO 8601 with ``Z``); None before any came.
    error : ObserwatorError or None
        Why the last request failed (its values are then those of the request before
        it, if any); None when it was answered.
    serial : int
        Unique in the process for each answer or failure (the ETags).
    """

    start: datetime | None = None
    values: Mapping[str, array[float]] = field(default_factory=dict)
    asked_at: datetime | None = None
    hours: int = 0
    fetched_at: str | None = None
    error: ObserwatorError | None = None
    serial: int = 0

    def covers(self, since: datetime | None) -> bool:
        """Whether its answers reach back to the newest stored hour ``since``."""
        if self.hours >= TAIL_HOURS:
            return True
        return (
            since is not None
            and self.asked_at is not None
            and self.asked_at - self.hours * _HOUR <= since
        )

    def hours_after(
        self, since: datetime | None, first: datetime | None = None
    ) -> tuple[list[datetime], dict[str, list[float | None]]]:
        """
        Its hours after the newest stored one ``since`` and from ``first`` on.

        Returns
        -------
        tuple of (list of datetime, dict)
            Every hour from the first to the last with a value (UTC) and each
            variable's value of each (None without one); empty without any.
        """
        if self.start is None or not self.values:
            return [], {}
        count = max(len(column) for column in self.values.values())
        low = 0
        if since is not None:
            low = max(low, (since - self.start) // _HOUR + 1)
        if first is not None:
            low = max(low, (first - self.start) // _HOUR)
        rows = [
            row
            for row in range(low, count)
            if any(not math.isnan(column[row]) for column in self.values.values())
        ]
        if not rows:
            return [], {}
        lo, hi = rows[0], rows[-1]
        times = [self.start + row * _HOUR for row in range(lo, hi + 1)]
        values = {
            name: [
                None if math.isnan(value) else value for value in column[lo : hi + 1]
            ]
            for name, column in self.values.items()
        }
        return times, values


def _columns(
    found: Mapping[str, Mapping[datetime, float]], since: datetime | None
) -> tuple[datetime | None, dict[str, array[float]]]:
    """The hours after ``since`` of a live tail (`tail_hours`): one column per variable."""
    kept = {
        name: [
            (moment, value)
            for moment, value in hours.items()
            if since is None or moment > since
        ]
        for name, hours in found.items()
    }
    kept = {name: pairs for name, pairs in kept.items() if pairs}
    if not kept:
        return None, {}
    start = min(pairs[0][0] for pairs in kept.values())
    end = max(pairs[-1][0] for pairs in kept.values())
    count = (end - start) // _HOUR + 1
    columns: dict[str, array[float]] = {}
    for name, pairs in kept.items():
        column = array("d", [math.nan]) * count
        for moment, value in pairs:
            column[(moment - start) // _HOUR] = value
        columns[name] = column
    return start, columns


TailFetch = Callable[[str, str, int], Sequence["Answer"]]
"""``fetch(provider, code, hours)``: the answers of a station's live tail."""


def _adapter_tail(provider: str, code: str, hours: int) -> tuple[Answer, ...]:
    """A station's live tail from its provider's adapter, every answer spooled (ADR-030 D7)."""
    return get_provider(provider).adapter.live_tail(
        code, hours=hours, timeout=DEFAULT_TIMEOUT
    )


class LiveTail:
    """
    The live tails of stations for the chart of „teraz” (O6), kept in memory.

    A station's tail is asked when the newest stored hour of its series is older than
    the current hour, at most once per `TAIL_TTL_S` while it reaches that hour (a
    failure keeps the station from being asked for `TAIL_RETRY_S`), for at most
    `TAIL_STATIONS` stations (the least recently served goes first), one request per
    station at a time and one live request for the whole server. Its provider's adapter
    writes every answer to the capture spool (ADR-030 D7); only the hours after the
    stored ones are kept here.

    Parameters
    ----------
    fetch : callable, optional
        ``fetch(provider, code, hours)`` returning the answers of a station's tail;
        `ProviderAdapter.live_tail` of its provider by default, recorded answers in
        tests.
    clock : callable, optional
        Monotonic time in seconds.
    now : callable, optional
        The current UTC time.
    log : ServerLog or None, optional
        Where each request is logged (`log_tail`).
    stations : int, optional
        How many stations' tails stay in memory at most.
    """

    def __init__(
        self,
        fetch: TailFetch | None = None,
        *,
        clock: Callable[[], float] = time.monotonic,
        now: Callable[[], datetime] = _utc,
        log: ServerLog | None = None,
        stations: int = TAIL_STATIONS,
    ) -> None:
        self._fetch = fetch or _adapter_tail
        self._clock = clock
        self._now = now
        self._log = log
        self._stations = stations
        self._tails: OrderedDict[tuple[str, str], tuple[float, Tail]] = OrderedDict()
        self._state = threading.Condition()
        self._asking: set[tuple[str, str]] = set()
        self._live = threading.Lock()

    def now(self) -> datetime:
        """The current UTC time, as the tails count it."""
        return self._now()

    def cached(self, provider: str, code: str, since: datetime | None) -> Tail | None:
        """
        A station's tail in memory that may be served, without asking (`get`).

        Parameters
        ----------
        provider, code : str
            The station's provider and code.
        since : datetime or None
            The newest stored hour of the station; None when none is stored.

        Returns
        -------
        Tail or None
            The tail asked less than `TAIL_TTL_S` ago that reaches ``since`` (a failed
            one for `TAIL_RETRY_S`); None when it must be asked.
        """
        with self._state:
            return self._fresh((provider, code), since)

    def get(self, provider: str, code: str, since: datetime | None) -> Tail:
        """
        A station's tail: from memory (`cached`), else asked of its provider.

        A request of a station that is being asked waits for that request's answer;
        any other request waits for the one live request of the server.

        Parameters
        ----------
        provider, code : str
            The station's provider and code.
        since : datetime or None
            The newest stored hour of the station; None when none is stored, which
            asks `TAIL_HOURS` back.

        Returns
        -------
        Tail
            Its hours after ``since``, or the error of its request beside the hours
            of the one before.
        """
        key = (provider, code)
        with self._state:
            while (found := self._fresh(key, since)) is None and key in self._asking:
                self._state.wait()
            if found is not None:
                return found
            self._asking.add(key)
            known = self._tails.get(key)
        try:
            tail = self._ask(provider, code, since, None if known is None else known[1])
            with self._state:
                self._tails[key] = (self._clock(), tail)
                self._tails.move_to_end(key)
                while len(self._tails) > self._stations:
                    self._tails.popitem(last=False)
            return tail
        finally:
            with self._state:
                self._asking.discard(key)
                self._state.notify_all()

    def _fresh(self, key: tuple[str, str], since: datetime | None) -> Tail | None:
        """The station's tail in memory that may be served; the caller holds the lock."""
        hit = self._tails.get(key)
        if hit is None:
            return None
        asked, tail = hit
        age = self._clock() - asked
        if tail.error is not None:
            fresh = age < TAIL_RETRY_S
        else:
            fresh = age < TAIL_TTL_S and tail.covers(since)
        if not fresh:
            return None
        self._tails.move_to_end(key)
        return tail

    def _ask(
        self, provider: str, code: str, since: datetime | None, known: Tail | None
    ) -> Tail:
        """Ask the provider for the station's tail, one request of the server at a time."""
        with self._live:
            now = self._now()
            hours = tail_asked(since, now)
            began = time.perf_counter()
            try:
                answers = self._fetch(provider, code, hours)
            except Exception as exc:
                log_tail(self._log, provider, time.perf_counter() - began, error=exc)
                if not isinstance(exc, ObserwatorError):
                    raise
                serial = next(_SERIALS)
                if known is not None and known.start is not None:
                    return replace(known, error=exc, serial=serial)
                return Tail(asked_at=now, hours=hours, error=exc, serial=serial)
            seconds = time.perf_counter() - began
        start, values = _columns(tail_hours(answers, code), since)
        given = sum(
            not math.isnan(value) for column in values.values() for value in column
        )
        log_tail(self._log, provider, seconds, hours=given)
        fetched = iso_utc(self._now())
        return Tail(start, values, now, hours, fetched, None, next(_SERIALS))
