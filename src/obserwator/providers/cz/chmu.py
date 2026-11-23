"""
ČHMÚ, Czechia's hydrometeorological institute (provider ``CHMU``).

The CC BY 4.0 open data of opendata.chmi.cz: files of one station (one per station
and year of the daily hydrological data, one per station and element of the daily
meteorological data), the station metadata of ``historical`` and ``now`` and the
station catalog built from them (spec 2026-10-18).
"""

from __future__ import annotations

import math
import re
from collections.abc import Collection, Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Literal

from obserwator._borders import CZECHIA
from obserwator._parsing.chmu import (
    HYDRO_FILE,
    METEO_FILE,
    MetadataTable,
    iter_stations,
    parse_chmu_hydro_daily,
    parse_chmu_meteo_daily,
    parse_listing,
    read_metadata,
    station_coordinates,
    station_rows,
)
from obserwator.datasets import (
    ArchiveFile,
    DatasetDescriptor,
    MonthsArg,
    YearsArg,
    _archive,
    _fixed_station_file,
    _minimum_year,
    _parse_params,
    _parse_stations,
    _station_file,
    _station_files,
    get_dataset,
    get_provider,
    parse_years,
)
from obserwator.exceptions import ObserwatorDataError, ObserwatorValidationError
from obserwator.fetch import _IDENTIFY, _get, _get_async
from obserwator.messages import message
from obserwator.models import NormalizedRecord, StationListEntry
from obserwator.providers.base import CheckScope, Kind, ProviderAdapter
from obserwator.store.catalog import (
    _Candidate,
    _catalog_lines,
    _catalog_notices,
    _catalog_sources,
    _current_archive,
    _distance_m,
    _evaluate,
    _local_source,
    _locate,
    _placement,
    _read_locations,
    _read_sources,
    _series_codes,
)
from obserwator.store.writer import _canonical, _validate_slot

if TYPE_CHECKING:
    from datetime import datetime

    from obserwator.attribution import Origin
    from obserwator.datasets import ProviderDescriptor
    from obserwator.store.catalog import CatalogBuild
    from obserwator.store.types import CatalogReport

__all__ = ["ADAPTER", "ChmuAdapter"]

# Daily elements in file order and the server directory of each.
_ELEMENT_GROUPS: Mapping[str, str] = MappingProxyType(
    {
        "SRA": "precipitation",
        "T": "temperature",
        "TMA": "temperature",
        "TMI": "temperature",
        "SCE": "snow",
        "SNO": "snow",
    }
)
# The daily ``meta1-<YYYYMMDD>.json`` of ``cz.chmu.meteo_now``: the newest of its
# listing is the current one.
METEO_NOW_FILE = re.compile(r"^meta1-[0-9]{8}\.json$")
"""Name of a daily file of the meteo ``now`` metadata."""
# The newest dated file of a listed directory, as plans name it.
_NEWEST = "meta1-<YYYYMMDD>.json"
# The file-name grammar of each kind of per-station file; group 1 is the station code.
_LISTED: Mapping[str, re.Pattern[str]] = MappingProxyType(
    {"station_year": HYDRO_FILE, "station_element": METEO_FILE}
)
# Units of the SPA thresholds (SPAH_UNIT, SPAQ_UNIT) in the catalog.
_THRESHOLD_UNITS: Mapping[str, str] = MappingProxyType({"CM": "cm", "M3_S": "m3/s"})


def _station_archives(
    descriptor: DatasetDescriptor,
    *,
    years: YearsArg | None,
    months: MonthsArg | None,
    params: Iterable[Literal["H", "Q", "T"]] | None,
    stations: Iterable[str] | None,
) -> tuple[ArchiveFile, ...]:
    """Per-station files of a dataset (station × year or station × element)."""
    key = descriptor.key
    provider = get_provider(descriptor.provider)
    if months is not None:
        raise ObserwatorValidationError(
            message(
                "datasets.option_months_does_not_apply",
                key=key,
                short_name=provider.short_name,
            ),
            details={"option": "months", "value": key},
        )
    if params is not None:
        _parse_params(params, descriptor)
    if stations is None:
        raise ObserwatorValidationError(
            message(
                "datasets.dataset_needs_option_stations_station",
                key=key,
                short_name=provider.short_name,
            ),
            details={"option": "stations", "value": None},
        )
    codes = _parse_stations(stations, provider)
    directory = descriptor.server_dir
    if descriptor.archive_scope == "station_element":
        if years is not None:
            raise ObserwatorValidationError(
                message(
                    "datasets.files_dataset_cover_whole_history",
                    short_name=provider.short_name,
                    key=key,
                ),
                details={"option": "years", "value": key},
            )
        return tuple(
            _archive(
                descriptor,
                f"{directory}/{group}/dly-{code}-{element}.csv",
                None,
                param=element,
                station_code=code,
            )
            for code in codes
            for element, group in _ELEMENT_GROUPS.items()
        )
    if years is None:
        raise ObserwatorValidationError(
            message("datasets.dataset_needs_option_years_without", key=key),
            details={"option": "years", "value": None},
        )
    selected_years = parse_years(years)
    _minimum_year(selected_years, descriptor)
    return tuple(
        _archive(
            descriptor,
            f"{directory}/H_{code}_DQ_{year}.json",
            year,
            station_code=code,
        )
        for code in codes
        for year in selected_years
    )


def _newest(url: str, content: bytes) -> str:
    """URL of the newest ``meta1-<YYYYMMDD>.json`` in the listing at ``url``."""
    names = sorted(
        entry.name
        for entry in parse_listing(content, url=url)
        if METEO_NOW_FILE.fullmatch(entry.name)
    )
    if not names:
        raise ObserwatorDataError(
            message("stations.unreadable_listing_no_file", url=url, newest=_NEWEST),
            details={"url": url},
        )
    return url + names[-1]


# --------------------------------------------------------------------------
# The station catalog (spec 2026-10-18 §7)
# --------------------------------------------------------------------------


def _chmu_meteo_now(root: Path) -> ArchiveFile | None:
    """The newest stored ``meteorology/climate/now/metadata/meta1-<YYYYMMDD>.json``."""
    descriptor = get_dataset("cz.chmu.meteo_now")
    directory = _validate_slot(root, f"archives/versions/{descriptor.server_dir}")
    names = (
        sorted(
            (
                f"{child.name}.json"
                for child in directory.iterdir()
                if child.is_dir()
                and _station_file(descriptor, f"{child.name}.json") is not None
            ),
            reverse=True,
        )
        if directory.is_dir()
        else []
    )
    for name in names:
        archive = _station_file(descriptor, name)
        if archive is not None and _current_archive(root, archive) is not None:
            return archive
    return None


@dataclass(frozen=True)
class _Metadata:
    """
    One ČHMÚ station metadata source of the catalog.

    Attributes
    ----------
    source : str
        Source name of the file in the sidecar's ``sources`` and in a threshold's
        ``source``, e.g. ``"chmu_hydro_now"``.
    dataset : str
        Key of the file's dataset, the ``location_source`` of a station it
        locates (ADR-028), e.g. ``"cz.chmu.hydro_now"``.
    kind : {"hydro", "meteo"}
        Station family of the file.
    table : MetadataTable
        Rows of the file with columns located by name.
    rows : Mapping of str to int
        Row chosen for every valid station code.
    thresholds : bool
        Whether the SPA thresholds of the file are used (not for ``meta3``).
    """

    source: str
    dataset: str
    kind: Literal["hydro", "meteo"]
    table: MetadataTable
    rows: Mapping[str, int]
    thresholds: bool

    def text(self, code: str, column: str) -> str | None:
        """
        Text of a station's row in a column.

        Parameters
        ----------
        code : str
            Station code.
        column : str
            Column name.

        Returns
        -------
        str or None
            The text; None without the row, the column or a value.
        """
        index = self.rows.get(code)
        if index is None or not self.table.has(column):
            return None
        return self.table.text(index, column)

    def number(self, code: str, column: str) -> int | float | None:
        """
        Number of a station's row in a column, as published.

        Parameters
        ----------
        code : str
            Station code.
        column : str
            Column name.

        Returns
        -------
        int or float or None
            An integer as is and a decimal as the float of its published
            notation; None without the row, the column or a value.

        Raises
        ------
        ObserwatorDataError
            If the cell is not a number or lies beyond the float range.
        """
        index = self.rows.get(code)
        if index is None or not self.table.has(column):
            return None
        value = self.table.number(index, column)
        if value is None or isinstance(value, int):
            return value
        number = float(value)
        if not math.isfinite(number):
            raise self.table.cell_error(
                index, column, message("catalog.number_out_range", value=value)
            )
        return number


def _metadata(
    data: bytes,
    *,
    source: str,
    dataset: str,
    kind: Literal["hydro", "meteo"],
    filename: str,
    problems: list[str],
    thresholds: bool = True,
) -> _Metadata:
    """Parse a ČHMÚ metadata file and choose one row per valid station code."""
    table = read_metadata(data, filename=filename)
    if kind == "hydro":
        table.require("objID", "STATION_NAME", "STREAM_NAME", "GEOGR1", "GEOGR2")
    else:
        table.require("WSI", "FULL_NAME", "GEOGR1", "GEOGR2")
    chosen = station_rows(table, kind=kind)
    pattern = re.compile(
        get_provider(get_dataset(dataset).provider).station_code_pattern
    )
    rows: dict[str, int] = {}
    for code, index in chosen.rows.items():
        if pattern.fullmatch(code):
            rows[code] = index
        else:
            problems.append(
                message("catalog.source_invalid_code", source=source, code=code)
            )
    for code in chosen.duplicates:
        if code in rows:
            problems.append(
                message("catalog.source_repeated_code", source=source, code=code)
            )
    return _Metadata(source, dataset, kind, table, rows, thresholds)


def _thresholds(source: _Metadata, code: str) -> dict[str, Any] | None:
    """
    SPA thresholds of a station's row (spec 2026-10-18 §7.4).

    ``drought`` = ``DRY*``, ``spa1``…``spa3`` = ``SPA1*``…``SPA3*`` and ``q50`` =
    ``SPA4*`` (stage or flow of the 50-year flow, not a fourth degree), numbers
    as published; None when the row has neither ``SPA_TYP`` nor a threshold.
    """
    levels: dict[str, dict[str, Any]] = {}
    present = False
    for variable in ("H", "Q"):
        values = {
            name: source.number(code, column)
            for name, column in (
                ("drought", f"DRY{variable}"),
                ("spa1", f"SPA1{variable}"),
                ("spa2", f"SPA2{variable}"),
                ("spa3", f"SPA3{variable}"),
                ("q50", f"SPA4{variable}"),
            )
        }
        present = present or any(value is not None for value in values.values())
        unit = source.text(code, f"SPA{variable}_UNIT")
        if unit is not None and unit not in _THRESHOLD_UNITS:
            raise source.table.cell_error(
                source.rows[code],
                f"SPA{variable}_UNIT",
                message("catalog.unknown_unit", unit=unit),
            )
        levels[variable] = {
            "unit": None if unit is None else _THRESHOLD_UNITS[unit],
            **values,
        }
    kind = source.text(code, "SPA_TYP")
    if kind is None and not present:
        return None
    return {"source": source.source, "type": kind, **levels}


def _established(source: _Metadata) -> dict[str, int]:
    """Year of the earliest ``BEGIN_DATE`` of each station of a period file."""
    table = source.table
    if not table.has("BEGIN_DATE"):
        return {}
    column = "objID" if source.kind == "hydro" else "WSI"
    first: dict[str, datetime] = {}
    for index in range(len(table.rows)):
        code = table.text(index, column)
        begin = table.timestamp(index, "BEGIN_DATE")
        if (
            code is not None
            and code in source.rows
            and begin is not None
            and (code not in first or begin < first[code])
        ):
            first[code] = begin
    return {code: moment.year for code, moment in first.items()}


def _chmu_feature(
    code: str,
    *,
    kind: Literal["hydro", "meteo"],
    sources: Sequence[_Metadata],
    user: Mapping[str, tuple[str, str, str | None]],
    established: Mapping[str, int],
    rejections: list[str],
) -> tuple[dict[str, Any], str | None, bool]:
    """
    GeoJSON feature of a ČHMÚ station, its location source and a location conflict.

    ``sources`` are the metadata files of the family in precedence order (now,
    meta3, archived list): the first that gives a name, river, hydrographic
    code or thresholds wins, and the first valid point of the sources and of
    the user file locates the station. A conflict is another valid point
    farther away than the larger of both uncertainties.
    """
    candidates: list[_Candidate] = []
    owners: list[_Metadata | None] = []
    for source in sources:
        index = source.rows.get(code)
        if index is not None:
            lat, lon = station_coordinates(source.table, index, kind=kind)
            candidates.append((source.dataset, lon, lat))
            owners.append(source)
    if code in user:
        candidates.append(("user", user[code][0], user[code][1]))
        owners.append(None)
    located = _locate(code, candidates, border=CZECHIA, rejections=rejections)
    geometry, location_source, uncertainty, reason = _placement(located, candidates)
    conflict = False
    elevation: int | float | None = None
    if not isinstance(located, str):
        index, point, own = located
        for _, later_lon, later_lat in candidates[index + 1 :]:
            verdict = _evaluate(later_lon, later_lat, border=CZECHIA)
            if not isinstance(verdict, str) and _distance_m(point, verdict[0]) > max(
                own, verdict[1]
            ):
                conflict = True
        owner = owners[index]
        if kind == "meteo" and owner is not None:
            elevation = owner.number(code, "ELEVATION")

    def first(column: str) -> str | None:
        return next(
            (text for source in sources if (text := source.text(code, column))),
            None,
        )

    properties: dict[str, Any] = {
        "station_code": code,
        "kind": kind,
        "meteo_kind": None,
        "name": first("STATION_NAME" if kind == "hydro" else "FULL_NAME") or "",
        "river": first("STREAM_NAME") if kind == "hydro" else None,
        "hydrographic_code": first("HLGP4") if kind == "hydro" else None,
        "river_order": None,
        "location_source": location_source,
        "location_uncertainty_m": uncertainty,
        "location_missing_reason": reason,
        "active": code in sources[0].rows,
        "established_year": established.get(code) if kind == "meteo" else None,
        "gauge_zero_m": None,
        "river_km": None,
        "elevation_m": elevation,
    }
    if kind == "hydro":
        properties["thresholds"] = next(
            (
                found
                for source in sources
                if source.thresholds
                and (found := _thresholds(source, code)) is not None
            ),
            None,
        )
    feature = {
        "type": "Feature",
        "id": code,
        "geometry": geometry,
        "properties": properties,
    }
    return feature, location_source, conflict


def _chmu_catalog_bytes(
    *,
    provider: ProviderDescriptor,
    families: Mapping[str, Sequence[_Metadata]],
    series: Mapping[str, set[str]],
    user: Mapping[str, tuple[str, str, str | None]],
    problems: list[str],
    rejections: list[str],
) -> tuple[bytes, int, int, dict[str, int], list[str], list[str]]:
    """
    Canonical ČHMÚ ``stations.geojson`` and its counts.

    Every code of the metadata files and of the current ČHMÚ series indexes is
    a station (closed and foreign ones too); codes only in the user file are
    problems.

    Returns
    -------
    tuple
        Bytes, station count, stations without location, stations per
        location source, codes known only from series and codes with a
        location conflict.
    """
    listed = {
        kind: {code for source in families[kind] for code in source.rows}
        for kind in ("hydro", "meteo")
    }
    codes = {kind: listed[kind] | series[kind] for kind in ("hydro", "meteo")}
    shared = sorted(codes["hydro"] & codes["meteo"])
    if shared:
        raise ObserwatorDataError(
            message(
                "catalog.station_codes_appear_both_hydro", shared=", ".join(shared[:10])
            )
        )
    known = codes["hydro"] | codes["meteo"]
    series_only = sorted(
        (series["hydro"] | series["meteo"]) - listed["hydro"] - listed["meteo"]
    )
    unknown = sorted(set(user) - known)
    if unknown:
        problems.append(
            message(
                "catalog.user_locations_unknown_codes_chmu",
                count=len(unknown),
                unknown=unknown[0],
            )
        )
    established = _established(families["meteo"][-1])
    features = []
    used: dict[str, int] = {}
    without = 0
    conflicts: list[str] = []
    for code in sorted(known):
        kind: Literal["hydro", "meteo"] = "hydro" if code in codes["hydro"] else "meteo"
        feature, source, conflict = _chmu_feature(
            code,
            kind=kind,
            sources=families[kind],
            user=user,
            established=established,
            rejections=rejections,
        )
        if source is None:
            without += 1
        else:
            used[source] = used.get(source, 0) + 1
        if conflict:
            conflicts.append(code)
        features.append(feature)
    lines = _catalog_lines(provider, used)
    document = {"type": "FeatureCollection", "features": features, **lines.fields()}
    return _canonical(document), len(features), without, used, series_only, conflicts


def _build_chmu(build: CatalogBuild) -> CatalogReport:
    """ČHMÚ catalog from the stored now and historical metadata files and the user file."""
    owner, user = build.provider, build.user
    # The user file is validated before the sources are read, so a bad header writes nothing.
    user_rows, user_problems = (
        _read_locations(user[1], static=None, provider=owner)
        if user is not None
        else ({}, [])
    )
    if (report := build.stopped()) is not None:
        return report
    stored = _read_sources(build.raw, owner)
    for step, (source, archive) in enumerate(
        _catalog_sources(build.raw, owner), start=1
    ):
        build.progress(
            step,
            "done",
            message(
                "catalog.source_read",
                server_path=archive.server_path if archive else source,
            ),
        )
    hydro_key, meteo_key, hydro_now, meteo_now = owner.adapter.station_sources
    hydro_list, meteo_list = (get_dataset(key).slug for key in (hydro_key, meteo_key))
    if (report := build.stopped()) is not None:
        return report
    problems: list[str] = []
    rejections: list[str] = []
    records: list[dict[str, Any]] = []

    def parse(
        data: bytes,
        record: dict[str, Any],
        *,
        dataset: str,
        kind: Literal["hydro", "meteo"],
        thresholds: bool = True,
    ) -> _Metadata:
        metadata = _metadata(
            data,
            source=record["source"],
            dataset=dataset,
            kind=kind,
            filename=record["file"],
            problems=problems,
            thresholds=thresholds,
        )
        record["count"] = len(metadata.rows)
        records.append(record)
        return metadata

    # Both files of the hydro ``now`` metadata, meta1 and meta3, are of
    # cz.chmu.hydro_now: a station located from either has that location source.
    families = {
        "hydro": (
            parse(*stored["chmu_hydro_now"], dataset=hydro_now, kind="hydro"),
            parse(
                *stored["chmu_hydro_meta3"],
                dataset=hydro_now,
                kind="hydro",
                thresholds=False,
            ),
            parse(*stored[hydro_list], dataset=hydro_key, kind="hydro"),
        ),
        "meteo": (
            parse(*stored["chmu_meteo_now"], dataset=meteo_now, kind="meteo"),
            parse(*stored[meteo_list], dataset=meteo_key, kind="meteo"),
        ),
    }
    if user is not None:
        problems.extend(user_problems)
        records.append(
            _local_source(
                user[1], source="user", file=user[0].name, count=len(user_rows)
            )
            | {"available": True}
        )
    # ČHMÚ publishes no station class: meteo_kind stays null (spec 2026-10-18 §7.3).
    series, series_sources, _ = _series_codes(build.root, problems, provider=owner)
    records.extend(series_sources)
    data, count, without, used, series_only, conflicts = _chmu_catalog_bytes(
        provider=owner,
        families=families,
        series=series,
        user=user_rows,
        problems=problems,
        rejections=rejections,
    )
    build.progress(6, "done", message("catalog.catalog_built", count=count))
    _catalog_notices(
        build.on_notice,
        problems=problems,
        rejections=rejections,
        used=used,
        user_rows=user_rows if user is not None else None,
        series_only=series_only,
        without=without,
        conflicts=conflicts,
    )
    if (report := build.stopped()) is not None:
        return report
    problems.extend(rejections)
    return build.publish(
        data,
        sources=records,
        count=count,
        without=without,
        from_series=len(series_only),
        problems=problems,
        lines=_catalog_lines(owner, used),
    )


class ChmuAdapter(ProviderAdapter):
    """The adapter of ČHMÚ (ADR-029); `ADAPTER` is its one instance."""

    provider_id = "CHMU"
    origin: Origin = "chmu"
    origins: tuple[Origin, ...] = ("chmu",)
    border = CZECHIA
    identifies = True
    station_sources = (
        "cz.chmu.hydro_stations",
        "cz.chmu.meteo_stations",
        "cz.chmu.hydro_now",
        "cz.chmu.meteo_now",
    )
    archive_suffixes = (".json", ".csv")
    sidecar_station = True

    # --- archives --------------------------------------------------------------

    def archive_files(
        self,
        descriptor: DatasetDescriptor,
        /,
        *,
        years: YearsArg | None,
        months: MonthsArg | None,
        params: Iterable[Literal["H", "Q", "T"]] | None,
        stations: Iterable[str] | None,
    ) -> tuple[ArchiveFile, ...]:
        """One file per station and year, or per station and element."""
        return _station_archives(
            descriptor, years=years, months=months, params=params, stations=stations
        )

    def archive_from_path(
        self, descriptor: DatasetDescriptor, server_path: str, /
    ) -> ArchiveFile | None:
        """A station's file by the grammar of its dataset."""
        directory, _, name = server_path.rpartition("/")
        if descriptor.archive_scope == "station_year":
            hydro = HYDRO_FILE.fullmatch(name)
            if hydro is None or directory != descriptor.server_dir:
                return None
            year = int(hydro[2])
            if descriptor.first_year is not None and year < descriptor.first_year:
                return None
            return self.archive_files(
                descriptor, years=[year], months=None, params=None, stations=[hydro[1]]
            )[0]
        if descriptor.archive_scope == "station_element":
            meteo = METEO_FILE.fullmatch(name)
            if meteo is None or directory != (
                f"{descriptor.server_dir}/{_ELEMENT_GROUPS[meteo[2]]}"
            ):
                return None
            return next(
                item
                for item in self.archive_files(
                    descriptor,
                    years=None,
                    months=None,
                    params=None,
                    stations=[meteo[1]],
                )
                if item.param == meteo[2]
            )
        return None

    # --- the store's checks ----------------------------------------------------

    def check_scope(self, descriptor: DatasetDescriptor, /) -> CheckScope:
        """A station's files by the listing of their directory (spec 2026-10-18 §4)."""
        return "country" if descriptor.archive_scope == "country" else "stations"

    def listed_station(self, descriptor: DatasetDescriptor, name: str, /) -> str | None:
        """The station of a listed file by the grammar of the dataset's files (§2.3)."""
        match = _LISTED[descriptor.archive_scope].fullmatch(name)
        return None if match is None else match[1]

    # --- station sources -------------------------------------------------------

    def station_file(
        self, descriptor: DatasetDescriptor, name: str, /
    ) -> ArchiveFile | None:
        """A fixed name, or a daily ``meta1-<YYYYMMDD>.json`` of the meteo ``now`` metadata."""
        if descriptor.key == self.station_sources[3] and METEO_NOW_FILE.fullmatch(name):
            return _archive(descriptor, f"{descriptor.server_dir}/{name}", None)
        return _fixed_station_file(descriptor, name)

    def parse_station_list(
        self, content: bytes, /, *, kind: Kind, filename: str
    ) -> list[StationListEntry]:
        """The station metadata JSON (``meta1.json``) of a family."""
        return list(iter_stations(content, kind=kind, filename=filename))

    def _live(self, kind: Kind) -> tuple[str, bool]:
        """
        The current metadata of a family, the first source of the catalog (§7.2).

        The hydro ``now`` file has a fixed name; the meteo one is the newest
        ``meta1-<YYYYMMDD>.json`` of its directory's listing (True).
        """
        if kind == "hydro":
            return _station_files(self.station_sources[2])[0].url, False
        meteo_now = get_dataset(self.station_sources[3])
        return f"{self.provider.base_url}{meteo_now.server_dir}/", True

    def live_urls(self, kind: Kind, /) -> list[str]:
        """The hydro metadata; the meteo listing and its newest file as a pattern."""
        url, listing = self._live(kind)
        return [url, url + _NEWEST] if listing else [url]

    def live_stations(self, kind: Kind, /, *, timeout: float) -> list[StationListEntry]:
        """The stations of the current metadata (its listing first for meteo)."""
        url, listing = self._live(kind)
        if listing:
            index = _get(
                url, timeout=timeout, headers=_IDENTIFY, source=self.server_name
            )
            url = _newest(url, index.content)
        response = _get(
            url, timeout=timeout, headers=_IDENTIFY, source=self.server_name
        )
        return self.parse_station_list(response.content, kind=kind, filename=url)

    async def live_stations_async(
        self, kind: Kind, /, *, timeout: float
    ) -> list[StationListEntry]:
        """Async twin of `live_stations`."""
        url, listing = self._live(kind)
        if listing:
            index = await _get_async(
                url, timeout=timeout, headers=_IDENTIFY, source=self.server_name
            )
            url = _newest(url, index.content)
        response = await _get_async(
            url, timeout=timeout, headers=_IDENTIFY, source=self.server_name
        )
        return self.parse_station_list(response.content, kind=kind, filename=url)

    # --- the station catalog ---------------------------------------------------

    def catalog_sources(self, raw: Path, /) -> list[tuple[str, ArchiveFile | None]]:
        """
        The two ``historical`` lists, the hydro ``now`` metadata, the newest meteo one.

        The hydro ``now`` metadata are ``meta1.json`` and ``meta3.json``; the
        newest daily meteo ``now`` file is None when none is stored.
        """
        hydro_list, meteo_list, hydro_now, _ = self.station_sources
        meta1, meta3 = _station_files(hydro_now)
        return [
            *(
                (get_dataset(key).slug, _station_files(key)[0])
                for key in (hydro_list, meteo_list)
            ),
            ("chmu_hydro_now", meta1),
            ("chmu_hydro_meta3", meta3),
            ("chmu_meteo_now", _chmu_meteo_now(raw)),
        ]

    def source_datasets(self) -> list[str]:
        """The lists, the hydro ``now`` metadata twice (two files), the meteo one."""
        hydro_list, meteo_list, hydro_now, meteo_now = self.station_sources
        return [hydro_list, meteo_list, hydro_now, hydro_now, meteo_now]

    def build_catalog(self, build: CatalogBuild, /) -> CatalogReport:
        """The catalog from the stored ``now`` and ``historical`` metadata and the user file."""
        return _build_chmu(build)

    # --- parsers ---------------------------------------------------------------

    def normalize(
        self,
        archive: ArchiveFile,
        /,
        *,
        data: bytes,
        carry: dict[str, date] | None,
        stations: Collection[str] | None = None,
        skipped_months: set[date] | None = None,
    ) -> Iterator[NormalizedRecord]:
        """The daily hydro JSON and the daily meteo CSV of one station."""
        if archive.dataset == "cz.chmu.hydro_daily":
            yield from parse_chmu_hydro_daily(data, filename=archive.server_path)
        elif archive.dataset == "cz.chmu.meteo_daily":
            yield from parse_chmu_meteo_daily(data, filename=archive.server_path)
        else:
            raise ObserwatorValidationError(
                message("parsing.no_parser_archive", dataset=archive.dataset)
            )


ADAPTER = ChmuAdapter()
"""The adapter of ČHMÚ."""
