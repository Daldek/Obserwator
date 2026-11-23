"""
ČHMÚ, Czechia's hydrometeorological institute (provider ``CHMU``).

The CC BY 4.0 open data of opendata.chmi.cz: files of one station (one per station
and year of the daily hydrological data, of the validated hourly ones and of the
daily and weekly groundwater readings, one per station and element of the daily
meteorological data, one per groundwater object and month of its operational data,
one per object of its characteristics), the station metadata of ``historical`` and
``now``, the operational day files of ``recent`` (the night's harvest) and ``now``
(the live tail, ADR-030) and the station catalog built from them (spec 2026-10-18,
ADR-032).
"""

from __future__ import annotations

import math
import re
from collections.abc import Collection, Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from itertools import combinations
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Literal

import httpx

from obserwator._borders import CZECHIA
from obserwator._parsing.chmu import (
    GROUNDWATER_CHARACTERISTIC_FILE,
    GROUNDWATER_FILE,
    GROUNDWATER_RECENT_FILE,
    HOURLY_FILE,
    HYDRO_FILE,
    METEO_FILE,
    MetadataTable,
    groundwater_kind,
    iter_stations,
    parse_chmu_groundwater,
    parse_chmu_hydro_daily,
    parse_chmu_meteo_daily,
    parse_listing,
    read_metadata,
    require_station_columns,
    station_coordinates,
    station_rows,
)
from obserwator.datasets import (
    KINDS,
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
from obserwator.fetch import (
    _GZIP,
    _IDENTIFY,
    PacedRequest,
    PacedSession,
    _get,
    _get_async,
    _keep,
    _source_error,
)
from obserwator.messages import message
from obserwator.models import NormalizedRecord, StationListEntry
from obserwator.providers.base import (
    Answer,
    CheckScope,
    Kind,
    ProviderAdapter,
    SourceAction,
)
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
    _stored_source,
)
from obserwator.store.types import Notice, NoticeHook
from obserwator.store.writer import _canonical, _validate_slot

if TYPE_CHECKING:
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
# The name of a station's file of a year of each station × year dataset.
_STATION_YEAR_NAMES: Mapping[str, str] = MappingProxyType(
    {
        "cz.chmu.hydro_daily": "H_{code}_DQ_{year}.json",
        "cz.chmu.hydro_hourly": "H_{code}_HQ_{year}.json",
        "cz.chmu.groundwater_daily": "H_{code}_D_{year}.json",
        "cz.chmu.groundwater_weekly": "H_{code}_W_{year}.json",
    }
)
# The letter of each groundwater series of ``historical/data`` in its file names.
_GROUNDWATER_LETTERS: Mapping[str, str] = MappingProxyType(
    {"cz.chmu.groundwater_daily": "D", "cz.chmu.groundwater_weekly": "W"}
)
# The list and the current metadata of the groundwater objects: optional sources of
# the catalog, read when the raw root holds them (ADR-032).
_GROUNDWATER_STATIONS = "cz.chmu.groundwater_stations"
_GROUNDWATER_NOW = "cz.chmu.groundwater_now"
# Units of the SPA thresholds (SPAH_UNIT, SPAQ_UNIT) in the catalog.
_THRESHOLD_UNITS: Mapping[str, str] = MappingProxyType({"CM": "cm", "M3_S": "m3/s"})
# The validated hourly files of a station's year (ADR-030 D2).
_HOURLY = "cz.chmu.hydro_hourly"
# The operational files of ``recent`` (one station and UTC day, the night's harvest)
# and of ``now`` (one station's current UTC day, the live tail), ADR-030.
_RECENT = "cz.chmu.hydro_recent"
_CURRENT = "cz.chmu.hydro_current"


def _file_parts(
    descriptor: DatasetDescriptor, name: str
) -> tuple[str, int | None, int | None, str | None] | None:
    """
    The station, year, month and element a per-station file name of a dataset gives.

    By the grammar of the dataset's files (spec 2026-10-18 §2.3, ADR-032); None for
    a name of another dataset or of none.
    """
    key = descriptor.key
    if key == "cz.chmu.hydro_daily":
        hydro = HYDRO_FILE.fullmatch(name)
        return None if hydro is None else (hydro[1], int(hydro[2]), None, None)
    if key == _HOURLY:
        hourly = HOURLY_FILE.fullmatch(name)
        return None if hourly is None else (hourly[1], int(hourly[2]), None, None)
    if key == "cz.chmu.meteo_daily":
        meteo = METEO_FILE.fullmatch(name)
        return None if meteo is None else (meteo[1], None, None, meteo[2])
    if key in _GROUNDWATER_LETTERS:
        series = GROUNDWATER_FILE.fullmatch(name)
        if series is None or series[2] != _GROUNDWATER_LETTERS[key]:
            return None
        return series[1], int(series[3]), None, None
    if descriptor.archive_scope == "station_month":
        month = GROUNDWATER_RECENT_FILE.fullmatch(name)
        return None if month is None else (month[1], int(month[2]), int(month[3]), None)
    if descriptor.archive_scope == "station":
        own = GROUNDWATER_CHARACTERISTIC_FILE.fullmatch(name)
        return None if own is None else (own[1], None, None, None)
    return None


def _station_archives(
    descriptor: DatasetDescriptor,
    *,
    years: YearsArg | None,
    months: MonthsArg | None,
    params: Iterable[Literal["H", "Q", "T"]] | None,
    stations: Iterable[str] | None,
) -> tuple[ArchiveFile, ...]:
    """
    Per-station files of a dataset.

    Station × year, station × month (every month of each year), station ×
    element or one file per station.
    """
    key = descriptor.key
    provider = get_provider(descriptor.provider)
    if months is not None:
        refusal = (
            message(
                "datasets.option_months_station_month",
                key=key,
                short_name=provider.short_name,
            )
            if descriptor.archive_scope == "station_month"
            else message(
                "datasets.option_months_does_not_apply",
                key=key,
                short_name=provider.short_name,
            )
        )
        raise ObserwatorValidationError(
            refusal, details={"option": "months", "value": key}
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
    if descriptor.archive_scope in ("station_element", "station"):
        if years is not None:
            raise ObserwatorValidationError(
                message(
                    "datasets.files_dataset_cover_whole_history",
                    short_name=provider.short_name,
                    key=key,
                ),
                details={"option": "years", "value": key},
            )
        if descriptor.archive_scope == "station":
            return tuple(
                _archive(
                    descriptor,
                    f"{directory}/GCHAR_{code}.json",
                    None,
                    station_code=code,
                )
                for code in codes
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
    if descriptor.archive_scope == "station_month":
        return tuple(
            _archive(
                descriptor,
                f"{directory}/{code}_D_{year}{month:02d}.json",
                year,
                month,
                station_code=code,
            )
            for code in codes
            for year in selected_years
            for month in range(1, 13)
        )
    name = _STATION_YEAR_NAMES[key]
    return tuple(
        _archive(
            descriptor,
            f"{directory}/{name.format(code=code, year=year)}",
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
    kind : {"hydro", "meteo", "groundwater"}
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
    kind: Kind
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
    kind: Kind,
    filename: str,
    problems: list[str],
    thresholds: bool = True,
) -> _Metadata:
    """Parse a ČHMÚ metadata file and choose one row per valid station code."""
    table = read_metadata(data, filename=filename)
    require_station_columns(table, kind=kind)
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
            continue
        if kind == "groundwater" and groundwater_kind(table, index) is None:
            problems.append(
                message(
                    "catalog.source_unknown_object_type",
                    source=source,
                    code=code,
                    value=table.text(index, "OBJECT_TYPE"),
                )
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


# The name column and the elevation column of each family's metadata files.
_NAME_COLUMNS: Mapping[str, str] = MappingProxyType(
    {"hydro": "STATION_NAME", "meteo": "FULL_NAME", "groundwater": "OBJECT_NAME"}
)
_ELEVATION_COLUMNS: Mapping[str, str] = MappingProxyType(
    {"meteo": "ELEVATION", "groundwater": "ALTITUDE"}
)


def _chmu_feature(
    code: str,
    *,
    kind: Kind,
    sources: Sequence[_Metadata],
    active: Collection[str],
    user: Mapping[str, tuple[str, str, str | None]],
    established: Mapping[str, int],
    rejections: list[str],
) -> tuple[dict[str, Any], str | None, bool]:
    """
    GeoJSON feature of a ČHMÚ station, its location source and a location conflict.

    ``sources`` are the metadata files of the family in precedence order (now,
    meta3, archived list; the stored ones of a groundwater object): the first
    that gives a name, river, hydrographic code, thresholds or the kind of a
    groundwater object wins, and the first valid point of the sources and of
    the user file locates the station; ``active`` are the codes of the
    family's ``now`` metadata. A conflict is another valid point farther away
    than the larger of both uncertainties.
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
        if kind in _ELEVATION_COLUMNS and owner is not None:
            elevation = owner.number(code, _ELEVATION_COLUMNS[kind])

    def first(column: str) -> str | None:
        return next(
            (text for source in sources if (text := source.text(code, column))),
            None,
        )

    properties: dict[str, Any] = {
        "station_code": code,
        "kind": kind,
        "meteo_kind": None,
        "name": first(_NAME_COLUMNS[kind]) or "",
        "river": first("STREAM_NAME") if kind == "hydro" else None,
        "hydrographic_code": first("HLGP4") if kind == "hydro" else None,
        "river_order": None,
        "location_source": location_source,
        "location_uncertainty_m": uncertainty,
        "location_missing_reason": reason,
        "active": code in active,
        "established_year": established.get(code) if kind == "meteo" else None,
        "gauge_zero_m": None,
        "river_km": None,
        "elevation_m": elevation,
    }
    if kind == "groundwater":
        # Only the features of groundwater objects carry it (ADR-032).
        properties["groundwater_kind"] = next(
            (
                object_type
                for source in sources
                if code in source.rows
                and (object_type := groundwater_kind(source.table, source.rows[code]))
            ),
            None,
        )
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
    active: Mapping[str, Collection[str]],
    series: Mapping[str, set[str]],
    user: Mapping[str, tuple[str, str, str | None]],
    problems: list[str],
    rejections: list[str],
) -> tuple[bytes, int, int, dict[str, int], list[str], list[str]]:
    """
    Canonical ČHMÚ ``stations.geojson`` and its counts.

    Every code of the metadata files and of the current ČHMÚ series indexes is
    a station (closed and foreign ones too) of the family whose files or series
    hold it; codes only in the user file are problems. ``families`` holds the
    metadata files of each family the raw root has, ``active`` the codes of
    each family's ``now`` metadata.

    Returns
    -------
    tuple
        Bytes, station count, stations without location, stations per
        location source, codes known only from series and codes with a
        location conflict.
    """
    listed = {
        kind: {code for source in families.get(kind, ()) for code in source.rows}
        for kind in KINDS
    }
    codes = {kind: listed[kind] | series.get(kind, set()) for kind in KINDS}
    for first, second in combinations(KINDS, 2):
        shared = sorted(codes[first] & codes[second])
        if shared:
            raise ObserwatorDataError(
                message(
                    "catalog.station_codes_appear_both_hydro",
                    first=first,
                    second=second,
                    shared=", ".join(shared[:10]),
                )
            )
    known = {code for family in codes.values() for code in family}
    series_only = sorted(
        {code for kind in KINDS for code in series.get(kind, ())}
        - {code for family in listed.values() for code in family}
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
        kind = next(family for family in KINDS if code in codes[family])
        feature, source, conflict = _chmu_feature(
            code,
            kind=kind,
            sources=families.get(kind, ()),
            active=active.get(kind, ()),
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
        kind: Kind,
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
    families: dict[str, Sequence[_Metadata]] = {
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
    # The list and the current metadata of the groundwater objects, when the raw root
    # holds them (ADR-032): the current metadata first, as in the other families.
    groundwater: list[_Metadata] = []
    active: dict[str, Collection[str]] = {
        kind: families[kind][0].rows for kind in ("hydro", "meteo")
    }
    for key in (_GROUNDWATER_NOW, _GROUNDWATER_STATIONS):
        archive = _station_files(key)[0]
        found = _stored_source(build.raw, archive, get_dataset(key).slug)
        if found is None:
            continue
        build.progress(
            5, "done", message("catalog.source_read", server_path=archive.server_path)
        )
        metadata = parse(*found, dataset=key, kind="groundwater")
        groundwater.append(metadata)
        if key == _GROUNDWATER_NOW:
            active["groundwater"] = metadata.rows
    if groundwater:
        families["groundwater"] = tuple(groundwater)
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
        active=active,
        series=series,
        user=user_rows,
        problems=problems,
        rejections=rejections,
    )
    build.progress(6, "done", message("catalog.catalog_built", count=count))
    if series["groundwater"] and not groundwater and build.on_notice is not None:
        build.on_notice(
            Notice(
                "info",
                "source_missing",
                message(
                    "catalog.groundwater_sources_missing",
                    raw=build.raw,
                    datasets=f"{_GROUNDWATER_STATIONS},{_GROUNDWATER_NOW}",
                ),
            )
        )
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
    harvested = frozenset({_RECENT})
    live_source = _CURRENT
    station_sources = (
        "cz.chmu.hydro_stations",
        "cz.chmu.meteo_stations",
        "cz.chmu.hydro_now",
        "cz.chmu.meteo_now",
    )
    optional_sources = (_GROUNDWATER_STATIONS, _GROUNDWATER_NOW)
    kinds = KINDS
    archive_suffixes = (".json", ".csv")
    sidecar_station = True

    def publication_default(self, key: str, /) -> Literal["public", "private"]:
        """``public``: ČHMÚ's open data are CC BY 4.0 (ADR-030 D5)."""
        return "public"

    # --- the night's harvest and the live tail (ADR-030 D9) ---------------------

    def harvest_requests(
        self,
        descriptor: DatasetDescriptor,
        /,
        *,
        start: date,
        end: date,
        stations: Sequence[str] | None,
        session: PacedSession,
        on_notice: NoticeHook | None,
    ) -> tuple[PacedRequest, ...]:
        """
        The ``recent`` day file of every station and day, ``start`` to ``end``.

        The stations are those of the ``now`` metadata (``hydrology/now/metadata/
        meta1.json``, 548 on 2026-11-23), in its order, or ``stations``; one request
        per station and day, ``<YYYYMMDD>_<WIGOS>.json``, the days of a station
        together. A station without the file of a day answers 404 (not published).
        """
        if descriptor.key not in self.harvested:
            return super().harvest_requests(
                descriptor,
                start=start,
                end=end,
                stations=stations,
                session=session,
                on_notice=on_notice,
            )
        if stations is not None:
            codes = list(stations)
        else:
            url = _station_files(self.station_sources[2])[0].url
            content = session.fetch(url, headers=_IDENTIFY).content
            codes = [
                entry.station_code
                for entry in self.parse_station_list(
                    content, kind="hydro", filename=url
                )
            ]
        directory = f"{self.provider.base_url}{descriptor.server_dir}"
        days = [start + timedelta(days=step) for step in range((end - start).days + 1)]
        return tuple(
            PacedRequest(f"{directory}/{day:%Y%m%d}_{code}.json", code, _IDENTIFY)
            for code in dict.fromkeys(codes)
            for day in days
        )

    def live_tail(
        self, code: str, /, *, hours: int, timeout: float
    ) -> tuple[Answer, ...]:
        """The ``now`` file of one station: its current UTC day (``hours`` unused)."""
        descriptor = get_dataset(_CURRENT)
        url = f"{self.provider.base_url}{descriptor.server_dir}/{code}.json"
        try:
            with httpx.Client(
                timeout=timeout, headers={**_GZIP, **_IDENTIFY}
            ) as client:
                response = client.get(url)
        except httpx.HTTPError as exc:
            raise _source_error(exc, url, source=self.server_name) from exc
        _keep(response)
        return (
            Answer(
                url,
                datetime.now(UTC),
                response.status_code,
                response.content,
                descriptor.key,
            ),
        )

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
        """One file per station and year, month or element, or one per station."""
        return _station_archives(
            descriptor, years=years, months=months, params=params, stations=stations
        )

    def archive_from_path(
        self, descriptor: DatasetDescriptor, server_path: str, /
    ) -> ArchiveFile | None:
        """A station's file by the grammar of its dataset."""
        directory, _, name = server_path.rpartition("/")
        parts = _file_parts(descriptor, name)
        if parts is None:
            return None
        code, year, month, element = parts
        if element is not None:
            if directory != f"{descriptor.server_dir}/{_ELEMENT_GROUPS[element]}":
                return None
            return next(
                item
                for item in self.archive_files(
                    descriptor, years=None, months=None, params=None, stations=[code]
                )
                if item.param == element
            )
        if directory != descriptor.server_dir:
            return None
        if year is None:
            return self.archive_files(
                descriptor, years=None, months=None, params=None, stations=[code]
            )[0]
        if descriptor.first_year is not None and year < descriptor.first_year:
            return None
        files = self.archive_files(
            descriptor, years=[year], months=None, params=None, stations=[code]
        )
        return files[0] if month is None else files[month - 1]

    # --- the store's checks ----------------------------------------------------

    def check_scope(self, descriptor: DatasetDescriptor, /) -> CheckScope:
        """A station's files by the listing of their directory (spec 2026-10-18 §4)."""
        return "country" if descriptor.archive_scope == "country" else "stations"

    def listed_station(self, descriptor: DatasetDescriptor, name: str, /) -> str | None:
        """The station of a listed file by the grammar of the dataset's files (§2.3)."""
        parts = _file_parts(descriptor, name)
        return None if parts is None else parts[0]

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

        The hydro and groundwater ``now`` files have a fixed name; the meteo one
        is the newest ``meta1-<YYYYMMDD>.json`` of its directory's listing (True).
        """
        if kind == "hydro":
            return _station_files(self.station_sources[2])[0].url, False
        if kind == "groundwater":
            return _station_files(_GROUNDWATER_NOW)[0].url, False
        meteo_now = get_dataset(self.station_sources[3])
        return f"{self.provider.base_url}{meteo_now.server_dir}/", True

    def live_urls(self, kind: Kind, /) -> list[str]:
        """The hydro and groundwater metadata; the meteo listing and its newest file."""
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

    def optional_action(
        self,
        key: str,
        raw: Path,
        recorded: Mapping[object, object],
        /,
        *,
        catalog: bool,
        cancelled: bool,
    ) -> SourceAction:
        """
        The stored list or current metadata of the groundwater objects (ADR-032).

        ``current`` when the current version equals the one the catalog recorded,
        also when neither has one; ``newer`` when it appeared, changed or is
        gone; ``missing`` without a catalog.
        """
        if key not in self.optional_sources:
            raise ValueError(f"{key} is no optional source of {self.provider_id}")
        if cancelled:
            return "unverifiable", message("common.cancelled")
        source = get_dataset(key).slug
        stored = _current_archive(raw, _station_files(key)[0])
        digest = None if stored is None else stored[1]["sha256"]
        status: Literal["current", "newer", "missing"]
        if not catalog:
            status = "missing"
        elif recorded.get(source) == digest:
            status = "current"
        else:
            status = "newer"
        if stored is None:
            return status, message(
                "catalog.groundwater_not_stored", source=source, dataset=key
            )
        return status, message(
            "catalog.source_detail",
            source=source,
            file=stored[0].relative_to(raw).as_posix(),
        )

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
        """The daily hydro JSON, the groundwater JSON and the daily meteo CSV of one station."""
        if archive.dataset == "cz.chmu.hydro_daily":
            yield from parse_chmu_hydro_daily(data, filename=archive.server_path)
        elif archive.dataset == "cz.chmu.meteo_daily":
            yield from parse_chmu_meteo_daily(data, filename=archive.server_path)
        elif archive.dataset in _GROUNDWATER_LETTERS:
            yield from parse_chmu_groundwater(data, filename=archive.server_path)
        else:
            raise ObserwatorValidationError(
                message("parsing.no_parser_archive", dataset=archive.dataset)
            )


ADAPTER = ChmuAdapter()
"""The adapter of ČHMÚ."""
