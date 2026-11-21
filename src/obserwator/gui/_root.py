"""
Obserwator's data root as the GUI reads it: catalogs, series, stored analyses' versions.

The GUI never writes under the root (GUI plan D7). It reads it only through the public
readers of `obserwator.store` (`read_catalog`, `read_series_index`, `read_series`,
`current_version`, `export_stations`) and asks again at most once a minute whether a
current version changed, so a new ``series build``, catalog or ``analyses build`` shows
without a restart; that read runs in the background, the requests taking the last
snapshot meanwhile. In memory: the station layer of the current versions, what the GUI
shows of each series index (its ranges without a value counted, not kept), the most
recent series documents (at most 32 and 2 million cells) and the 4 most recent files of
the stations.
"""

from __future__ import annotations

import contextlib
import gc
import importlib
import pickle
import threading
import time
from collections import OrderedDict
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from datetime import date, datetime
from pathlib import Path
from typing import Any, Literal, NamedTuple

from obserwator.datasets import datasets, get_dataset
from obserwator.exceptions import ObserwatorError
from obserwator.gui._http import etag_of
from obserwator.instance import Instance
from obserwator.store import (
    StationFeature,
    StationSeriesIndex,
    current_version,
    export_stations,
    read_catalog,
    read_series,
    read_series_index,
)

RELOAD_AFTER_S = 60.0
"""How long the current versions are trusted before the root is asked again [s]."""
SERIES_DOCUMENTS = 32
"""How many station series documents stay in memory at most."""
SERIES_CELLS = 2_000_000
"""How many cells (`series_cells`) the station series documents in memory hold at most,
30 to 60 bytes each: a synoptic station's whole series (37 variables over 60 years) is
1.2 million cells, a hydrological station's 0.1 million. The most recent document stays
even when it alone is larger."""
STATIONS_FILES = 4
"""How many files of the stations stay in memory (one is a few MB on a full root)."""
StationsFormat = Literal["geojson", "csv"]
"""The formats of `export_stations`."""
CATALOG_SLOTS: Mapping[str, str] = {
    "IMGW-PIB": "catalog:pl.imgw.stations",
    "CHMI": "catalog:cz.chmi.stations",
}
"""The catalog of each provider, as `current_version` names it."""
ANALYSES_SLOTS: Mapping[str, str] = {
    "IMGW-PIB": "analyses:pl.imgw.analyses",
    "CHMI": "analyses:cz.chmi.analyses",
}
"""The stored analyses of each provider (ADR-016), as `current_version` names them."""


def in_thread(job: Callable[[], None]) -> None:
    """Run ``job`` in a daemon thread: the re-read of the root behind the requests."""
    threading.Thread(target=job, name="obserwator-gui-root", daemon=True).start()


def series_datasets() -> tuple[str, ...]:
    """The datasets whose station series a data root may hold, in registry order."""
    return tuple(
        descriptor.key
        for descriptor in datasets()
        if descriptor.in_store and descriptor.time_unit in ("day", "month", "half_year")
    )


def _iso(value: date | datetime | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat().replace("+00:00", "Z")
    return value.isoformat()


def _day(value: date | datetime | None) -> str | None:
    """The calendar day of a date or a time, as ``YYYY-MM-DD``."""
    text = _iso(value)
    return text[:10] if text else None


def series_cells(document: Mapping[str, Any]) -> int:
    """
    The size of a series document (`DataRoot.series_document`) in cells.

    Its rows times its columns (the date, the hydrological year, each variable's
    values and, of half-years, the period and each variable's dates of extremes) and
    its flags.
    """
    columns = 2 + len(document["values"]) + len(document.get("extremes", ()))
    if "period" in document:
        columns += 1
    flags = sum(len(rows) for rows in document["flags"].values())
    return len(document["dates"]) * columns + flags


@dataclass(frozen=True)
class Version:
    """
    One current version of the root: a catalog, a dataset's series or stored analyses.

    Attributes
    ----------
    slot : str
        ``catalog:<key>``, ``series:<key>`` or ``analyses:<key>``.
    path : Path
        The version's main file (``stations.geojson``, ``series.json``,
        ``analyses.json``).
    label : str
        The version directory's name, as the panel shows it (``2026-09-21_2a6443c3``).
    sha256 : str
        SHA-256 of the main file, from its sidecar.
    downloaded_at : str or None
        When the version was made, ISO 8601 UTC.
    hydrolog : str or None
        The version of Hydrolog that computed stored analyses, as their sidecar
        records it; None for the other kinds.
    """

    slot: str
    path: Path
    label: str
    sha256: str
    downloaded_at: str | None
    hydrolog: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """The version as the API shows it: label, SHA-256 and date."""
        return {
            "version": self.label,
            "sha256": self.sha256,
            "downloaded_at": self.downloaded_at,
        }


class Coverage(NamedTuple):
    """
    One variable's coverage at a station as the GUI shows it (`StationCoverage`).

    Attributes
    ----------
    unit : str
        The unit of the variable.
    period : str or None
        The half-year period of semi-annual data, None otherwise.
    first, last : str or None
        The first and the last unit with a value, ``YYYY-MM-DD``.
    with_value, accumulated : int
        The units with a value and those flagged ``accumulated``.
    gaps : int
        How many ranges without a value the index lists between ``first`` and ``last``.
    """

    unit: str
    period: str | None
    first: str | None
    last: str | None
    with_value: int
    accumulated: int
    gaps: int


class Held(NamedTuple):
    """
    What the GUI keeps of a station of a series index (`StationSeriesIndex`).

    Attributes
    ----------
    rows : int
        The rows of the station's Parquet file.
    variables : Mapping of str to Coverage
        The coverage of each variable that has a value, by its key (``"Q_min@winter"``).
    """

    rows: int
    variables: Mapping[str, Coverage]


def _held(entry: StationSeriesIndex) -> Held:
    return Held(
        entry.rows,
        {
            name: Coverage(
                coverage.unit,
                coverage.period,
                _iso(coverage.first),
                _iso(coverage.last),
                coverage.with_value,
                coverage.accumulated,
                len(coverage.gaps),
            )
            for name, coverage in entry.variables.items()
            if coverage.first is not None
        },
    )


@dataclass(frozen=True)
class Series:
    """
    The current series version of a dataset and what the GUI keeps of its index.

    Attributes
    ----------
    dataset : str
        The dataset.
    version : Version
        Its current series version.
    year_type : str
        ``hydrological`` or ``calendar``: the year numbering of the index.
    stations : Mapping of str to Held
        Every station of the index, its gap ranges counted (`read_held`).
    """

    dataset: str
    version: Version
    year_type: str
    stations: Mapping[str, Held]


def compact[T](make: Callable[[], T]) -> T:
    """
    What ``make`` returns, made again once everything else it made is gone.

    Python returns an arena (1 MiB) of small objects to the system only when every
    object in it is gone, and its free lists keep some of the objects just freed. What
    a large read keeps (the summary of a 50 MB index, a station's series) is made among
    the read's objects and would keep the arenas of all of them, hundreds of MB that
    then sit unused (in swap, once the system needs the memory). So it is kept as bytes
    while the read's objects go and the free lists are emptied (`gc.collect`), and is
    made again from them, in the memory that is left.

    Parameters
    ----------
    make : callable
        Makes the value: any object `pickle` takes.

    Returns
    -------
    object
        An equal value.
    """
    packed = pickle.dumps(make(), protocol=pickle.HIGHEST_PROTOCOL)
    gc.collect()
    found: T = pickle.loads(packed)
    return found


def read_held(dataset: str, version: Version) -> Series:
    """
    A dataset's current series with what the GUI shows of its index (`Held`).

    The index lists every range without a value of every variable of every station;
    the GUI shows only how many there are. On a full root the ranges are most of the
    index: 1.8 million of the snow variables of the precipitation series, 230 MB in
    memory once read, 600 MB while `read_series_index` reads them; the summary is
    `compact`.

    Parameters
    ----------
    dataset : str
        The dataset.
    version : Version
        Its current series version.

    Returns
    -------
    Series
        The version, the index's year type and its stations.

    Raises
    ------
    ObserwatorError
        When the index cannot be read (`read_series_index`).
    """

    def summary() -> tuple[str, dict[str, Held]]:
        index = read_series_index(version.path)
        return index.year_type, {code: _held(e) for code, e in index.stations.items()}

    year_type, stations = compact(summary)
    return Series(dataset, version, year_type, stations)


@dataclass(frozen=True)
class Snapshot:
    """
    What the root held when it was last read.

    Attributes
    ----------
    catalogs : Mapping of str to Version
        The current catalog of each provider that has one.
    features : Mapping of str to StationFeature
        Every station of those catalogs by its code.
    series : Mapping of str to Series
        The current series of each dataset the root holds.
    error : ObserwatorError or None
        Why the root could not be read; the other fields are then empty.
    analyses : Mapping of str to Version
        The current stored analyses of each provider that has them (ADR-016); not
        part of `key`, since the answers made from them name their version.
    """

    catalogs: Mapping[str, Version] = field(default_factory=dict)
    features: Mapping[str, StationFeature] = field(default_factory=dict)
    series: Mapping[str, Series] = field(default_factory=dict)
    error: ObserwatorError | None = None
    layer: Mapping[str, Any] = field(default_factory=dict)
    layer_etag: str = ""
    analyses: Mapping[str, Version] = field(default_factory=dict)

    @property
    def key(self) -> tuple[str, ...]:
        """The SHA-256 of every catalog and series version in use: the base of the ETags."""
        return tuple(
            sorted(
                [f"{slot}={v.sha256}" for slot, v in self.catalogs.items()]
                + [f"{key}={s.version.sha256}" for key, s in self.series.items()]
            )
        )

    def datasets_of(self, code: str) -> list[dict[str, Any]]:
        """The series that hold a station, each with its version and variables' coverage."""
        found = []
        for key, series in self.series.items():
            held = series.stations.get(code)
            if held is None or not held.variables:
                continue
            found.append(
                {
                    "dataset": key,
                    "provider": get_dataset(key).provider,
                    "time_unit": get_dataset(key).time_unit,
                    "year_type": series.year_type,
                    "rows": held.rows,
                    **series.version.to_dict(),
                    "variables": {
                        name: coverage._asdict()
                        for name, coverage in held.variables.items()
                    },
                }
            )
        return found


def _version(slot: str, root: Path) -> Version | None:
    entry = current_version(root, slot=slot)
    if entry is None or entry.version is None or entry.meta is None:
        return None
    path = Path(entry.version)
    hydrolog = entry.meta.extra.get("hydrolog_version")
    return Version(
        slot,
        path,
        path.parent.name,
        entry.meta.sha256,
        _iso(entry.meta.downloaded_at),
        hydrolog if isinstance(hydrolog, str) else None,
    )


def record_years(held: list[dict[str, Any]]) -> dict[str, str | None]:
    """
    The years of a station's record: from its first to its last value in any series.

    The series of a station are kept per dataset as published; its record spans
    them all, e.g. a synoptic station's climate series before its synoptic one
    (ADR-022).
    """
    firsts = [v["first"] for d in held for v in d["variables"].values() if v["first"]]
    lasts = [v["last"] for d in held for v in d["variables"].values() if v["last"]]
    return {
        "first": min(firsts)[:4] if firsts else None,
        "last": max(lasts)[:4] if lasts else None,
    }


def _layer_entry(feature: StationFeature, snapshot: Snapshot) -> dict[str, Any]:
    """One point of the station layer: what the map, the list and the filters need."""
    props = feature.properties
    held = snapshot.datasets_of(feature.station_code)
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
        "datasets": [d["dataset"] for d in held],
        **record_years(held),
    }


def _series_document(dataset: str, code: str, series: Series) -> dict[str, Any]:
    """A station's whole series of a dataset as one columnar document (`read_series`)."""
    descriptor = get_dataset(dataset)
    names = tuple(descriptor.variables)
    dates: list[str] = []
    hydro_year: list[int] = []
    period: list[str | None] = []
    values: dict[str, list[float | None]] = {name: [] for name in names}
    flags: dict[str, list[list[Any]]] = {name: [] for name in names}
    extremes: dict[str, list[str | None]] = {}
    half_year = descriptor.time_unit == "half_year"
    if half_year:
        for name in names:
            extremes[f"{name}_start"] = []
            extremes[f"{name}_end"] = []
    for row, record in enumerate(read_series(series.version.path, station=code)):
        dates.append(record.date.isoformat())
        hydro_year.append(record.hydro_year)
        if half_year:
            period.append(record.period)
        for name in names:
            measurement = record.measurements[name]
            values[name].append(
                None if measurement.value is None else float(measurement.value)
            )
            if measurement.flag not in ("value", "missing"):
                flags[name].append([row, measurement.flag])
            if half_year:
                start, end = record.extrema_dates.get(name, (None, None))
                extremes[f"{name}_start"].append(_day(start))
                extremes[f"{name}_end"].append(_day(end))
    document: dict[str, Any] = {
        "dataset": dataset,
        "station": code,
        "version": series.version.label,
        "sha256": series.version.sha256,
        "year_type": series.year_type,
        "time_unit": descriptor.time_unit,
        "dates": dates,
        "hydro_year": hydro_year,
        "units": dict(descriptor.variables),
        "values": values,
        "flags": flags,
    }
    if half_year:
        document["period"] = period
        document["extremes"] = extremes
    return document


READER_MODULES = ("pyarrow.parquet", "pyarrow.dataset")
"""What pyarrow imports on its first read of a Parquet file (`import_readers`)."""


def import_readers() -> None:
    """
    Import now what the first read of a station's series would import.

    pyarrow imports its Parquet and dataset modules on its first read of a file, and
    with them pandas when it is installed: about 350 modules, kept for the life of the
    server. Imported during the first request of a series, among the objects of the
    series index it reads (up to 600 MB), they would keep all that memory (`compact`).
    A module pyarrow lacks is left to the read, which manages without it or says so.
    """
    for module in READER_MODULES:
        with contextlib.suppress(ImportError):
            importlib.import_module(module)


class DataRoot:
    """
    The data root, read only, its current versions asked again at most once a minute.

    The first read is made on the first request, which waits for it; every later one
    runs in the background (`snapshot`), so no request waits for the root. Made, it
    imports what a read of a series needs (`import_readers`).

    Parameters
    ----------
    path : Path
        The root.
    reload_after_s : float, optional
        How long a read of the current versions is trusted [s].
    clock : callable, optional
        Monotonic time in seconds.
    background : callable, optional
        Runs a re-read of the root; a daemon thread by default (`in_thread`).
    scope : Instance or None, optional
        The deployment's ``[obserwator.instance]`` (ADR-025): every read is reduced to
        what it serves (`Instance.reduce`), so the station layer, its ETag and every
        route agree; None serves the whole root.
    """

    def __init__(
        self,
        path: Path,
        *,
        reload_after_s: float = RELOAD_AFTER_S,
        clock: Callable[[], float] = time.monotonic,
        background: Callable[[Callable[[], None]], None] = in_thread,
        scope: Instance | None = None,
    ) -> None:
        import_readers()
        self.path = path
        self._reload_after_s = reload_after_s
        self._clock = clock
        self._background = background
        self._scope = scope
        self._lock = threading.Lock()
        self._snapshot: Snapshot | None = None
        self._checked_at = -1e18
        self._refreshing = False
        self._versions: tuple[tuple[str, str], ...] | None = None
        self._series_docs: OrderedDict[tuple[str, ...], tuple[dict[str, Any], int]] = (
            OrderedDict()
        )
        self._series_cells = 0
        self._stations_files: OrderedDict[tuple[str, ...], bytes] = OrderedDict()
        self._docs_lock = threading.Lock()
        self._export_lock = threading.Lock()

    def _current(self) -> tuple[tuple[str, str], ...]:
        """The slot and SHA-256 of every current catalog and series (the pointers only)."""
        found = []
        for slot in (
            *CATALOG_SLOTS.values(),
            *(f"series:{k}" for k in series_datasets()),
        ):
            version = _version(slot, self.path)
            if version is not None:
                found.append((slot, version.sha256))
        return tuple(found)

    def _analyses(self) -> dict[str, Version]:
        """The current stored analyses of each provider that has them (ADR-016)."""
        return {
            provider: version
            for provider, slot in ANALYSES_SLOTS.items()
            if (version := _version(slot, self.path)) is not None
        }

    def snapshot(self) -> Snapshot:
        """
        The current versions, read again in the background after a minute.

        Only the first call reads the root itself (the others wait for it); later, the
        call that finds the read older than a minute starts one re-read (`background`)
        and every call takes the last snapshot until that re-read replaces it.

        Returns
        -------
        Snapshot
            The catalogs, series, station layer and stored analyses' versions;
            ``error`` when the root cannot be read (the GUI then shows the error and
            serves no stations). A new version of stored analyses alone keeps what
            was read of the catalogs and series.
        """
        with self._lock:
            if self._snapshot is None:
                self._checked_at = self._clock()
                self._reread()
                assert self._snapshot is not None
                return self._snapshot
            if (
                self._refreshing
                or self._clock() - self._checked_at < self._reload_after_s
            ):
                return self._snapshot
            self._checked_at = self._clock()
            self._refreshing = True
            last = self._snapshot
        try:
            self._background(self._refresh)
        except BaseException:
            with self._lock:
                self._refreshing = False
            raise
        return self._snapshot or last

    def _refresh(self) -> None:
        """One re-read of the root behind the requests (`snapshot`)."""
        try:
            self._reread()
        finally:
            with self._lock:
                self._refreshing = False

    def _reread(self) -> None:
        """Read the current versions; the catalogs and series again when they changed."""
        try:
            versions = self._current()
            analyses = self._analyses()
        except ObserwatorError as exc:
            self._snapshot, self._versions = Snapshot(error=exc), None
            return
        snapshot, known = self._snapshot, self._versions
        if snapshot is None or versions != known:
            snapshot = self._read()
            known = versions if snapshot.error is None else None
        if snapshot.error is None and snapshot.analyses != analyses:
            snapshot = replace(snapshot, analyses=analyses)
        self._snapshot, self._versions = snapshot, known

    def _read(self) -> Snapshot:
        try:
            catalogs = {
                provider: version
                for provider, slot in CATALOG_SLOTS.items()
                if (version := _version(slot, self.path)) is not None
            }
            features: dict[str, StationFeature] = {}
            for provider, version in catalogs.items():
                for feature in read_catalog(version.path):
                    features[feature.station_code] = (
                        feature
                        if feature.provider == provider
                        else StationFeature(
                            feature.station_code,
                            feature.geometry,
                            feature.properties,
                            provider,
                        )
                    )
            series: dict[str, Series] = {}
            for key in series_datasets():
                version = _version(f"series:{key}", self.path)
                if version is not None:
                    series[key] = read_held(key, version)
        except ObserwatorError as exc:
            return Snapshot(error=exc)
        if self._scope is not None:
            catalogs, features, series = self._scope.reduce(catalogs, features, series)
        snapshot = Snapshot(catalogs, features, series)
        layer = [_layer_entry(feature, snapshot) for feature in features.values()]
        scope = () if self._scope is None else (self._scope.key,)
        return Snapshot(
            catalogs,
            features,
            series,
            None,
            {"count": len(layer), "stations": layer},
            etag_of("stations", snapshot.key, *scope),
        )

    def series_document(self, dataset: str, code: str) -> tuple[dict[str, Any], str]:
        """
        A station's whole series of a dataset as one columnar document.

        Parameters
        ----------
        dataset : str
            A dataset the snapshot holds.
        code : str
            A station of its index.

        Returns
        -------
        tuple of (dict, str)
            ``dates``, ``hydro_year``, ``period`` (half-years), ``units``,
            ``values`` (null = no value), ``flags`` (``[[row, flag], …]`` of the
            flags other than ``value`` and ``missing``), ``extremes`` (half-years:
            ``<V>_start``, ``<V>_end``) and the version; and its ETag base.

        Raises
        ------
        KeyError
            When the snapshot holds no such dataset or station.
        """
        snapshot = self.snapshot()
        series = snapshot.series[dataset]
        if code not in series.stations:
            raise KeyError(code)
        key = (dataset, series.version.sha256, code)
        with self._docs_lock:
            hit = self._series_docs.get(key)
            if hit is not None:
                self._series_docs.move_to_end(key)
                return hit[0], etag_of("series", key)
        document = compact(lambda: _series_document(dataset, code, series))
        size = series_cells(document)
        with self._docs_lock:
            made = self._series_docs.pop(key, None)
            self._series_cells += size - (0 if made is None else made[1])
            self._series_docs[key] = (document, size)
            while len(self._series_docs) > 1 and (
                len(self._series_docs) > SERIES_DOCUMENTS
                or self._series_cells > SERIES_CELLS
            ):
                _, (_, dropped) = self._series_docs.popitem(last=False)
                self._series_cells -= dropped
        return document, etag_of("series", key)

    def stations_file(
        self,
        fmt: StationsFormat,
        provider: str | None,
        kind: Literal["hydro", "meteo"] | None,
    ) -> bytes:
        """
        The stations of the current catalogs as `export_stations` writes them.

        One export runs at a time (it reads every series index: seconds on a full
        root); the `STATIONS_FILES` most recent stay in memory per current versions.

        Parameters
        ----------
        fmt : {"geojson", "csv"}
            The format.
        provider : str or None
            The provider's stations only; None for every one.
        kind : {"hydro", "meteo"} or None
            The stations of this kind only; None for both.

        Returns
        -------
        bytes
            The file, UTF-8.

        Raises
        ------
        ObserwatorError
            When the root holds no catalog of ``provider`` or no station of ``kind``.
        """
        key = (fmt, provider or "", kind or "", *self.snapshot().key)
        with self._docs_lock:
            hit = self._stations_files.get(key)
            if hit is not None:
                self._stations_files.move_to_end(key)
                return hit
        with self._export_lock:
            with self._docs_lock:
                hit = self._stations_files.get(key)
            if hit is None:
                lines = export_stations(
                    self.path,
                    provider=provider,
                    kind=kind,
                    format=fmt,
                    keep=None if self._scope is None else self._scope.keeps,
                )
                hit = "".join(lines).encode("utf-8")
                with self._docs_lock:
                    self._stations_files[key] = hit
                    while len(self._stations_files) > STATIONS_FILES:
                        self._stations_files.popitem(last=False)
        return hit
