"""Read-only access to the demo store: catalogs, series indexes and station series.

The mockup reads Obserwator's store through its public readers (catalogs, series
indexes, current versions) and the station Parquet files those indexes name. Nothing
is written under the root.
"""

from __future__ import annotations

import threading
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow.parquet as pq

from obserwator import get_dataset
from obserwator.store.reader import current_version, read_catalog, read_series_index

#: Series datasets the GUI shows, in the order of the panel's dataset switch.
SERIES_DATASETS = (
    "pl.imgw.hydro_daily",
    "pl.imgw.hydro_semiannual",
    "pl.imgw.meteo_climate_daily",
    "pl.imgw.meteo_precip_daily",
    "cz.chmi.hydro_daily",
    "cz.chmi.meteo_daily",
)


@dataclass(frozen=True)
class SeriesVersion:
    """The current series version of a dataset."""

    dataset: str
    path: Path  # the version directory
    name: str  # the version's directory name, e.g. 2026-11-12_ab12cd34
    year_type: str
    stations: dict[str, Any]  # code -> StationSeriesIndex


@dataclass(frozen=True)
class Series:
    """One station's series of one dataset: dates and, per variable, values and flags."""

    dataset: str
    station: str
    version: str
    dates: np.ndarray  # datetime64[D]
    hydro_year: np.ndarray  # int
    period: np.ndarray | None  # half-year series: "winter" | "summer" | "annual"
    values: dict[str, np.ndarray]  # float64, NaN where missing
    flags: dict[str, np.ndarray]  # str
    units: dict[str, str]
    extra: dict[str, np.ndarray] = field(default_factory=dict)  # <V>_start/_end of extremes


class Store:
    """The demo store, loaded once; series read on demand and kept in a small LRU."""

    def __init__(self, root: Path, cache_size: int = 48) -> None:
        self.root = root
        self.catalog = read_catalog(root=root)
        self.versions: dict[str, SeriesVersion] = {}
        for key in SERIES_DATASETS:
            entry = current_version(root, slot=f"series:{key}")
            if entry is None or entry.version is None:
                continue
            directory = Path(entry.version)
            if directory.name == "series.json":
                directory = directory.parent
            index = read_series_index(directory)
            self.versions[key] = SeriesVersion(
                key, directory, directory.name, index.year_type, dict(index.stations)
            )
        self._cache: OrderedDict[tuple[str, str], Series] = OrderedDict()
        self._cache_size = cache_size
        self._lock = threading.Lock()

    # --- stations ---------------------------------------------------------------

    def datasets_of(self, code: str) -> list[dict[str, Any]]:
        """The series datasets that hold a station, with per-variable coverage."""
        out = []
        for key, version in self.versions.items():
            entry = version.stations.get(code)
            if entry is None:
                continue
            variables = {}
            for name, cov in entry.variables.items():
                if cov.first is None:
                    continue
                variables[name] = {
                    "unit": cov.unit,
                    "first": cov.first.isoformat(),
                    "last": cov.last.isoformat() if cov.last else None,
                    "with_value": cov.with_value,
                    "gaps": len(cov.gaps),
                }
            if variables:
                out.append({"dataset": key, "version": version.name, "variables": variables})
        return out

    # --- series ------------------------------------------------------------------

    def series(self, dataset: str, code: str) -> Series:
        """A station's whole series of a dataset (KeyError when the store lacks it)."""
        key = (dataset, code)
        with self._lock:
            hit = self._cache.get(key)
            if hit is not None:
                self._cache.move_to_end(key)
                return hit
        version = self.versions[dataset]
        entry = version.stations[code]
        table = pq.read_table(version.path / entry.file)
        descriptor = get_dataset(dataset)
        names = table.column_names
        dates = np.array(table.column("date").to_numpy(zero_copy_only=False), dtype="datetime64[D]")
        hydro_year = table.column("hydro_year").to_numpy(zero_copy_only=False).astype(int)
        period = None
        if "period" in names:
            period = np.array(table.column("period").to_pylist(), dtype=object)
        values: dict[str, np.ndarray] = {}
        flags: dict[str, np.ndarray] = {}
        extra: dict[str, np.ndarray] = {}
        for variable in descriptor.variables:
            column = f"{variable}_value"
            if column not in names:
                continue
            raw = table.column(column).to_numpy(zero_copy_only=False)
            values[variable] = np.where(np.equal(raw, None), np.nan, raw).astype(float)
            flags[variable] = np.array(table.column(f"{variable}_flag").to_pylist(), dtype=object)
            for suffix in ("start", "end"):
                name = f"{variable}_{suffix}"
                if name in names:
                    extra[name] = np.array(table.column(name).to_pylist(), dtype=object)
        series = Series(
            dataset,
            code,
            version.name,
            dates,
            hydro_year,
            period,
            values,
            flags,
            dict(descriptor.variables),
            extra,
        )
        with self._lock:
            self._cache[key] = series
            while len(self._cache) > self._cache_size:
                self._cache.popitem(last=False)
        return series


def iso(day: date | np.datetime64 | None) -> str | None:
    """An ISO date or None."""
    if day is None:
        return None
    return str(np.datetime64(day, "D"))
