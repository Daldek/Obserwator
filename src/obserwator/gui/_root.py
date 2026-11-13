"""
Obserwator's data root as the GUI reads it: catalogs, series indexes and station series.

The GUI never writes under the root (GUI plan D7). It reads it only through the public
readers (`read_catalog`, `read_series_index`, `read_series`, `current_version`) and asks
again at most once a minute whether a current version changed, so a new ``series build``
or catalog shows without a restart. In memory: the station layer of the current versions
and the 32 most recent series documents.
"""

from __future__ import annotations

import threading
import time
from collections import OrderedDict
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

from obserwator.datasets import datasets, get_dataset
from obserwator.exceptions import ObserwatorError
from obserwator.gui._http import etag_of
from obserwator.store.reader import (
    current_version,
    read_catalog,
    read_series,
    read_series_index,
)
from obserwator.store.types import SeriesIndex, StationFeature

RELOAD_AFTER_S = 60.0
"""How long the current versions are trusted before the root is asked again [s]."""
SERIES_DOCUMENTS = 32
"""How many station series documents stay in memory."""
CATALOG_SLOTS: Mapping[str, str] = {
    "IMGW-PIB": "catalog:pl.imgw.stations",
    "CHMI": "catalog:cz.chmi.stations",
}
"""The catalog of each provider, as `current_version` names it."""


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


@dataclass(frozen=True)
class Version:
    """
    One current version of the root: a catalog or a dataset's series.

    Attributes
    ----------
    slot : str
        ``catalog:<key>`` or ``series:<key>``.
    path : Path
        The version's main file (``stations.geojson``, ``series.json``).
    label : str
        The version directory's name, as the panel shows it (``2026-09-21_2a6443c3``).
    sha256 : str
        SHA-256 of the main file, from its sidecar.
    downloaded_at : str or None
        When the version was made, ISO 8601 UTC.
    """

    slot: str
    path: Path
    label: str
    sha256: str
    downloaded_at: str | None

    def to_dict(self) -> dict[str, Any]:
        """The version as the API shows it: label, SHA-256 and date."""
        return {
            "version": self.label,
            "sha256": self.sha256,
            "downloaded_at": self.downloaded_at,
        }


@dataclass(frozen=True)
class Series:
    """The current series version of a dataset and its index."""

    dataset: str
    version: Version
    index: SeriesIndex


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
    """

    catalogs: Mapping[str, Version] = field(default_factory=dict)
    features: Mapping[str, StationFeature] = field(default_factory=dict)
    series: Mapping[str, Series] = field(default_factory=dict)
    error: ObserwatorError | None = None
    layer: Mapping[str, Any] = field(default_factory=dict)
    layer_etag: str = ""

    @property
    def key(self) -> tuple[str, ...]:
        """The SHA-256 of every version in use: the base of the ETags."""
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
            entry = series.index.stations.get(code)
            if entry is None:
                continue
            variables = {
                name: {
                    "unit": coverage.unit,
                    "period": coverage.period,
                    "first": _iso(coverage.first),
                    "last": _iso(coverage.last),
                    "with_value": coverage.with_value,
                    "accumulated": coverage.accumulated,
                    "gaps": len(coverage.gaps),
                }
                for name, coverage in entry.variables.items()
                if coverage.first is not None
            }
            if variables:
                found.append(
                    {
                        "dataset": key,
                        "provider": get_dataset(key).provider,
                        "time_unit": get_dataset(key).time_unit,
                        "year_type": series.index.year_type,
                        "rows": entry.rows,
                        **series.version.to_dict(),
                        "variables": variables,
                    }
                )
        return found


def _version(slot: str, root: Path) -> Version | None:
    entry = current_version(root, slot=slot)
    if entry is None or entry.version is None or entry.meta is None:
        return None
    path = Path(entry.version)
    return Version(
        slot,
        path,
        path.parent.name,
        entry.meta.sha256,
        _iso(entry.meta.downloaded_at),
    )


def _layer_entry(feature: StationFeature, snapshot: Snapshot) -> dict[str, Any]:
    """One point of the station layer: what the map, the list and the filters need."""
    props = feature.properties
    held = snapshot.datasets_of(feature.station_code)
    firsts = [v["first"] for d in held for v in d["variables"].values() if v["first"]]
    lasts = [v["last"] for d in held for v in d["variables"].values() if v["last"]]
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
        "first": min(firsts)[:4] if firsts else None,
        "last": max(lasts)[:4] if lasts else None,
    }


class DataRoot:
    """
    The data root, read only, its current versions asked again at most once a minute.

    Parameters
    ----------
    path : Path
        The root.
    reload_after_s : float, optional
        How long a read of the current versions is trusted [s].
    """

    def __init__(self, path: Path, *, reload_after_s: float = RELOAD_AFTER_S) -> None:
        self.path = path
        self._reload_after_s = reload_after_s
        self._lock = threading.Lock()
        self._snapshot: Snapshot | None = None
        self._checked_at = -1e18
        self._versions: tuple[tuple[str, str], ...] | None = None
        self._series_docs: OrderedDict[tuple[str, ...], dict[str, Any]] = OrderedDict()
        self._docs_lock = threading.Lock()

    def _current(self) -> tuple[tuple[str, str], ...]:
        """The slot and SHA-256 of every current version (cheap: the pointers only)."""
        found = []
        for slot in (
            *CATALOG_SLOTS.values(),
            *(f"series:{k}" for k in series_datasets()),
        ):
            version = _version(slot, self.path)
            if version is not None:
                found.append((slot, version.sha256))
        return tuple(found)

    def snapshot(self) -> Snapshot:
        """
        The current versions, read again when the last read is older than a minute.

        Returns
        -------
        Snapshot
            The catalogs, series and station layer; ``error`` when the root cannot
            be read (the GUI then shows the error and serves no stations).
        """
        with self._lock:
            now = time.monotonic()
            if (
                self._snapshot is not None
                and now - self._checked_at < self._reload_after_s
            ):
                return self._snapshot
            self._checked_at = now
            try:
                versions = self._current()
            except ObserwatorError as exc:
                self._snapshot, self._versions = Snapshot(error=exc), None
                return self._snapshot
            if self._snapshot is None or versions != self._versions:
                self._snapshot = self._read()
                self._versions = versions if self._snapshot.error is None else None
            return self._snapshot

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
                    series[key] = Series(key, version, read_series_index(version.path))
        except ObserwatorError as exc:
            return Snapshot(error=exc)
        snapshot = Snapshot(catalogs, features, series)
        layer = [_layer_entry(feature, snapshot) for feature in features.values()]
        return Snapshot(
            catalogs,
            features,
            series,
            None,
            {"count": len(layer), "stations": layer},
            etag_of("stations", snapshot.key),
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
        if code not in series.index.stations:
            raise KeyError(code)
        key = (dataset, series.version.sha256, code)
        with self._docs_lock:
            hit = self._series_docs.get(key)
            if hit is not None:
                self._series_docs.move_to_end(key)
                return hit, etag_of("series", key)
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
            "year_type": series.index.year_type,
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
        with self._docs_lock:
            self._series_docs[key] = document
            while len(self._series_docs) > SERIES_DOCUMENTS:
                self._series_docs.popitem(last=False)
        return document, etag_of("series", key)
