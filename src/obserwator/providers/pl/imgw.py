"""
IMGW-PIB, Poland's hydrological and meteorological service (provider ``IMGW``).

The archives of danepubliczne.imgw.pl (files of the whole country in year or
five-year folders, the per-station synop archives, the actinometric files named only
in the folder index), its station lists and current-data API, hydro.imgw.pl's map
and station details (ADR-021), and the station catalog built from them (ADR-015).
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Callable, Collection, Iterable, Iterator, Mapping, Sequence
from dataclasses import replace
from datetime import date
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Literal, cast
from urllib.parse import quote, unquote, urlsplit

import httpx

from obserwator._borders import POLAND
from obserwator._parsing import CARRY_DATASETS
from obserwator._parsing.hydro import normalize_hydro_archive
from obserwator._parsing.meteo import normalize_meteo_archive, normalize_synop_archive
from obserwator._parsing.stations import parse_stations_csv
from obserwator.datasets import (
    _PARAMS,
    HYDRO_DETAILS,
    ArchiveFile,
    DatasetDescriptor,
    MonthsArg,
    YearsArg,
    _archive,
    _minimum_year,
    _parse_params,
    _parse_stations,
    _station_files,
    get_dataset,
    get_provider,
    parse_months,
    parse_years,
)
from obserwator.exceptions import ObserwatorDataError, ObserwatorValidationError
from obserwator.fetch import (
    DownloadResult,
    _get,
    _get_async,
    _json_payload,
    _source_error,
    download_hydro_data,
    download_meteo_data,
    fetch_hydro_current,
    fetch_meteo_current,
    fetch_synop,
)
from obserwator.messages import message
from obserwator.models import NormalizedRecord, StationListEntry
from obserwator.providers.base import CheckScope, Kind, ProviderAdapter, SourceAction
from obserwator.stations import _hydro_details, fetch_hydro_states
from obserwator.store.catalog import (
    _catalog_lines,
    _catalog_notices,
    _catalog_sources,
    _current_archive,
    _feature,
    _list_rows,
    _local_source,
    _optional_float,
    _optional_int,
    _read_locations,
    _read_sources,
    _series_codes,
    _stored_source,
    _text,
)
from obserwator.store.types import Notice
from obserwator.store.writer import _canonical

if TYPE_CHECKING:
    from obserwator.attribution import Origin
    from obserwator.datasets import ProviderDescriptor
    from obserwator.messages import Message
    from obserwator.store.catalog import CatalogBuild, MeteoKind
    from obserwator.store.types import CatalogReport

__all__ = ["ADAPTER", "ImgwAdapter"]

# Folder of a country archive: a year or a five-year range.
_FOLDER = re.compile(r"([0-9]{4})(?:_([0-9]{4}))?")
# Per-station synop archives (``meteo/dobowe|terminowe/synop``): the folder's period
# and the station number (the last three digits of its code); the running year is
# published as monthly files of the whole country instead.
_STATION_FILE = re.compile(r"^(?:([0-9]{4})_)?([0-9]{4})_([0-9]{3})_s\.zip$")
_MONTH_FILE = re.compile(r"^([0-9]{4})_([0-9]{2})_s\.zip$")
# Monthly archives of the warnings, ``<year>/<MM>.zip`` from September 2017.
_WARNING_ARCHIVES = ("pl.imgw.warnings_hydro_archive", "pl.imgw.warnings_meteo_archive")
# Year folder of the actinometric index: a year or a range of years.
_INDEX_YEARS = re.compile(r"([0-9]{4})(?:-([0-9]{4}))?")
# Links of the server's folder index (Apache autoindex).
_HREF = re.compile(r"""href\s*=\s*["']([^"'#?]+)""", re.IGNORECASE)
# Suffix of the file name and the last year of the first folder of the
# meteorological five-year grid (klimat 1951_1955, opad 1950_1955, synop
# 1960_1965, the per-station synop archives 1966_1970); from 1966 all subtypes
# share the 1966_1970, ... grid.
_METEO_LAYOUT = {
    "pl.imgw.meteo_climate_daily": ("k", 1955),
    "pl.imgw.meteo_precip_daily": ("o", 1955),
    "pl.imgw.meteo_synop_daily": ("s", 1970),
    "pl.imgw.meteo_climate_monthly": ("k", 1955),
    "pl.imgw.meteo_precip_monthly": ("o", 1955),
    "pl.imgw.meteo_synop_monthly": ("s", 1965),
    "pl.imgw.meteo_climate_terms": ("k", 1955),
    "pl.imgw.meteo_synop_terms": ("s", 1970),
}
# Datasets of an origin other than danepubliczne.imgw.pl: PMAXTP's own pages and
# hydro.imgw.pl's station details (ADR-021).
_DATASET_ORIGINS: Mapping[str, Origin] = MappingProxyType(
    {"pl.imgw.pmaxtp": "pmaxtp", HYDRO_DETAILS: "imgw_hydro"}
)
# The current-data API answer of each family whose ``lon``/``lat`` locate the rows of
# the live list (the first location source of the catalog too), and the key of the
# station code in it.
_LOCATIONS: Mapping[str, tuple[str, str]] = MappingProxyType(
    {
        "hydro": ("pl.imgw.hydro_now", "id_stacji"),
        "meteo": ("pl.imgw.meteo_now", "kod_stacji"),
    }
)
# The parser of each dataset's archives.
_HYDRO_PARSED = frozenset(
    {"pl.imgw.hydro_daily", "pl.imgw.hydro_monthly", "pl.imgw.hydro_semiannual"}
)
_METEO_PARSED = frozenset({"pl.imgw.meteo_climate_daily", "pl.imgw.meteo_precip_daily"})
_SYNOP_PARSED = "pl.imgw.meteo_synop_daily"
_HYDRO_INTERVALS: Mapping[
    str, Literal["dobowe", "miesieczne", "polroczne_i_roczne"]
] = MappingProxyType(
    {
        "pl.imgw.hydro_daily": "dobowe",
        "pl.imgw.hydro_monthly": "miesieczne",
        "pl.imgw.hydro_semiannual": "polroczne_i_roczne",
    }
)
# The local file of the coordinates of hydro.imgw.pl's map, a location file of the
# catalog outside any dataset (``static``), written by ``python -m
# obserwator.reference_data``.
STATIC_LOCATIONS = "hydro_stations_locations.csv"
# Source name of hydro.imgw.pl's station details (``pl.imgw.hydro_details``), an
# optional source of the IMGW-PIB catalog: its sidecar entry and ``details_source``.
DETAILS_SOURCE = "hydro_details"
# Properties of an IMGW-PIB hydrological station taken from those details (ADR-021).
_DETAILS_PROPERTIES = (
    "established_year",
    "gauge_zero_m",
    "gauge_zero_datum",
    "river_km",
    "catchment_area_km2",
    "province",
    "district",
    "warning_level_cm",
    "alarm_level_cm",
    "absolute_min_level_cm",
    "absolute_min_level_dates",
    "absolute_max_level_cm",
    "absolute_max_level_dates",
)
# ``meteo_kind`` of an IMGW-PIB station measured in the current series of a dataset,
# in order of precedence: a station in several series has the first kind (the
# programme of a synoptic station includes the climate one, which includes
# precipitation).
_METEO_KINDS: Mapping[str, MeteoKind] = MappingProxyType(
    {
        "pl.imgw.meteo_synop_daily": "synop",
        "pl.imgw.meteo_climate_daily": "climate",
        "pl.imgw.meteo_precip_daily": "precipitation",
    }
)
_KIND_RANKS: Mapping[MeteoKind, int] = MappingProxyType(
    {kind: rank for rank, kind in enumerate(_METEO_KINDS.values())}
)


# --------------------------------------------------------------------------
# Archives
# --------------------------------------------------------------------------


def _meteo_folder(year: int, *, first_year: int, first_folder_end: int) -> str:
    if year > 2000:
        return str(year)
    if year <= first_folder_end:
        return f"{first_year}_{first_folder_end}"
    start = 1951 + (year - 1951) // 5 * 5
    return f"{start}_{start + 4}"


def _country_archives(
    descriptor: DatasetDescriptor,
    *,
    years: YearsArg | None,
    months: MonthsArg | None,
    params: Iterable[Literal["H", "Q", "T"]] | None,
    stations: Iterable[str] | None,
) -> tuple[ArchiveFile, ...]:
    """Archives of a dataset covering the whole country."""
    key = descriptor.key
    if stations is not None:
        raise ObserwatorValidationError(
            message("datasets.archives_dataset_cover_whole_country", key=key),
            details={"option": "stations", "value": key},
        )
    if years is None:
        raise ObserwatorValidationError(
            message("datasets.dataset_needs_option_years_years", key=key),
            details={"option": "years", "value": None},
        )
    selected_years = parse_years(years)
    selected_months = (
        parse_months(months) if months is not None else tuple(range(1, 13))
    )
    selected_params = (
        _parse_params(params, descriptor) if params is not None else _PARAMS
    )
    _minimum_year(selected_years, descriptor)
    first_year = descriptor.first_year or selected_years[0]

    directory = descriptor.server_dir
    result: list[ArchiveFile] = []
    folders: set[str] = set()
    for year in selected_years:
        if key == "pl.imgw.hydro_daily":
            if year < 2023:
                for month in selected_months:
                    result.append(
                        _archive(
                            descriptor,
                            f"{directory}/{year}/codz_{year}_{month:02d}.zip",
                            year,
                            month,
                        )
                    )
            else:
                result.append(
                    _archive(descriptor, f"{directory}/{year}/codz_{year}.zip", year)
                )
        elif key == "pl.imgw.hydro_phenomena":
            result.append(
                _archive(descriptor, f"{directory}/{year}/zjaw_{year}.zip", year)
            )
        elif key == "pl.imgw.hydro_monthly":
            result.append(
                _archive(descriptor, f"{directory}/{year}/mies_{year}.zip", year)
            )
        elif key in _WARNING_ARCHIVES:
            for month in selected_months:
                result.append(
                    _archive(
                        descriptor,
                        f"{directory}/{year}/{month:02d}.zip",
                        year,
                        month,
                    )
                )
        elif key == "pl.imgw.hydro_semiannual":
            for param in selected_params:
                result.append(
                    _archive(
                        descriptor,
                        f"{directory}/{year}/polr_{param}_{year}.zip",
                        year,
                        param=param,
                    )
                )
        else:
            suffix, first_folder_end = _METEO_LAYOUT[key]
            folder = _meteo_folder(
                year, first_year=first_year, first_folder_end=first_folder_end
            )
            if descriptor.time_unit == "month":
                if folder in folders:
                    continue
                folders.add(folder)
                first, _, last = folder.partition("_")
                result.append(
                    _archive(
                        descriptor,
                        f"{directory}/{folder}/{folder}_m_{suffix}.zip",
                        int(first),
                        last_year=int(last or first),
                    )
                )
            elif year <= 2000:
                result.append(
                    _archive(
                        descriptor, f"{directory}/{folder}/{year}_{suffix}.zip", year
                    )
                )
            else:
                for month in selected_months:
                    result.append(
                        _archive(
                            descriptor,
                            f"{directory}/{folder}/{year}_{month:02d}_{suffix}.zip",
                            year,
                            month,
                        )
                    )
    return tuple(result)


def _station_file(
    descriptor: DatasetDescriptor, folder: str, number: str
) -> ArchiveFile:
    """
    Per-station synop archive: one station in one folder.

    The file carries no station code (its name has only the station number),
    so the archive equals the one `_archive_from_path` gives for its path; it
    covers the whole folder (a five-year range or a year).
    """
    suffix = _METEO_LAYOUT[descriptor.key][0]
    first, _, last = folder.partition("_")
    return _archive(
        descriptor,
        f"{descriptor.server_dir}/{folder}/{folder}_{number}_{suffix}.zip",
        int(first),
        last_year=int(last or first),
    )


def _month_file(descriptor: DatasetDescriptor, year: int, month: int) -> ArchiveFile:
    """Monthly file of the whole country that stands for the running year's station files."""
    suffix = _METEO_LAYOUT[descriptor.key][0]
    return _archive(
        descriptor,
        f"{descriptor.server_dir}/{year}/{year}_{month:02d}_{suffix}.zip",
        year,
        month,
    )


def _station_archives(
    descriptor: DatasetDescriptor,
    *,
    years: YearsArg | None,
    months: MonthsArg | None,
    params: Iterable[Literal["H", "Q", "T"]] | None,
    stations: Iterable[str] | None,
) -> tuple[ArchiveFile, ...]:
    """
    Per-station synop archives and the monthly files of the running year.

    Stations give one file per station and folder (the station number is the
    last three digits of the code; two codes of one number name one file);
    months give the monthly files of the whole country of the years from 2001.
    """
    key = descriptor.key
    if params is not None:
        _parse_params(params, descriptor)
    if years is None:
        raise ObserwatorValidationError(
            message("datasets.dataset_needs_option_years_years", key=key),
            details={"option": "years", "value": None},
        )
    if stations is None and months is None:
        raise ObserwatorValidationError(
            message("datasets.station_archives_need_stations_or_months", key=key),
            details={"option": "stations", "value": None},
        )
    selected_years = parse_years(years)
    _minimum_year(selected_years, descriptor)
    first_year = descriptor.first_year or selected_years[0]
    first_folder_end = _METEO_LAYOUT[key][1]
    result: dict[str, ArchiveFile] = {}
    if stations is not None:
        for code in _parse_stations(stations, get_provider(descriptor.provider)):
            for year in selected_years:
                folder = _meteo_folder(
                    year, first_year=first_year, first_folder_end=first_folder_end
                )
                archive = _station_file(descriptor, folder, code[-3:])
                result.setdefault(archive.server_path, archive)
    if months is not None:
        selected_months = parse_months(months)
        recent = [year for year in selected_years if year > 2000]
        if not recent:
            raise ObserwatorValidationError(
                message("datasets.monthly_station_archives_from_2001", key=key),
                details={"option": "months", "value": list(selected_months)},
            )
        for year in recent:
            for month in selected_months:
                archive = _month_file(descriptor, year, month)
                result.setdefault(archive.server_path, archive)
    return tuple(result.values())


def _station_path(
    descriptor: DatasetDescriptor, directory: str, name: str
) -> ArchiveFile | None:
    """The archive of a per-station synop path, None when it is no file of the dataset."""
    parent, _, folder = directory.rpartition("/")
    period = _FOLDER.fullmatch(folder)
    if parent != descriptor.server_dir or period is None:
        return None
    first = int(period[1])
    first_year = descriptor.first_year or first
    if first < first_year or folder != _meteo_folder(
        first, first_year=first_year, first_folder_end=_METEO_LAYOUT[descriptor.key][1]
    ):
        return None
    if (station := _STATION_FILE.fullmatch(name)) is not None:
        archive = _station_file(descriptor, folder, station[3])
    elif (monthly := _MONTH_FILE.fullmatch(name)) is not None and (
        first > 2000 and 1 <= int(monthly[2]) <= 12
    ):
        archive = _month_file(descriptor, first, int(monthly[2]))
    else:
        return None
    return archive if archive.server_path == f"{directory}/{name}" else None


def _indexed_years(
    descriptor: DatasetDescriptor,
    *,
    years: YearsArg | None,
    params: Iterable[Literal["H", "Q", "T"]] | None,
    stations: Iterable[str] | None,
) -> tuple[int, ...]:
    """
    Years of a dataset named in the folder index, checked offline.

    Its folders are named after the stations, without their codes, so a
    selection takes every station; months select nothing (the file names
    follow no rule), as for the yearly archives.
    """
    key = descriptor.key
    if stations is not None:
        raise ObserwatorValidationError(
            message("datasets.stations_folders_without_codes", key=key),
            details={"option": "stations", "value": key},
        )
    if params is not None:
        _parse_params(params, descriptor)
    if years is None:
        raise ObserwatorValidationError(
            message("datasets.dataset_needs_option_years_years", key=key),
            details={"option": "years", "value": None},
        )
    selected = parse_years(years)
    _minimum_year(selected, descriptor)
    return selected


def _year_folder(name: str) -> tuple[int, int] | None:
    """First and last year of a year folder of the folder index (``2015``, ``1991-1992``)."""
    span = _INDEX_YEARS.fullmatch(name)
    if span is None:
        return None
    return int(span[1]), int(span[2] or span[1])


def _indexed_file(descriptor: DatasetDescriptor, relative: str) -> ArchiveFile:
    """
    The archive of a file found in the folder index, by its path below ``server_dir``.

    A file in a year folder covers that folder's years; any other file (the
    summary of the dataset, a station's documents) has no year.
    """
    path = f"{descriptor.server_dir}/{relative}"
    for part in relative.split("/")[:-1]:
        if (span := _year_folder(part)) is not None:
            return _archive(descriptor, path, span[0], last_year=span[1])
    return _archive(descriptor, path, None)


def _index_names(client: httpx.Client, url: str) -> list[str]:
    """
    Names of a folder index: files, and sub-folders with a trailing ``/``.

    The links are percent-decoded (UTF-8); the parent folder, absolute links and
    the sorting links of the index are no entries.

    Raises
    ------
    ObserwatorConnectionError
        If the index cannot be read (``source_unavailable``).
    """
    try:
        response = client.get(url)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise _source_error(exc, url) from exc
    names = (
        unquote(href)
        for href in _HREF.findall(response.text)
        if not href.startswith("/") and not urlsplit(href).scheme
    )
    return list(dict.fromkeys(name for name in names if name.strip("/")))


def _indexed_archives(
    descriptor: DatasetDescriptor, years: Iterable[int], *, timeout: float
) -> tuple[ArchiveFile, ...]:
    """
    Files of a dataset named only in the folder index (ADR-023), in index order.

    The tree below ``server_dir`` is walked folder by folder, whatever the
    names and spelling of the folders; a year folder (``2015``, ``1991-1992``)
    is entered only when it holds a selected year, and every file outside the
    year folders (the summary of the dataset, a station's documents) belongs
    to every selection.
    """
    assert descriptor.server_dir is not None
    selected = set(years)
    base = f"{get_provider(descriptor.provider).base_url}{descriptor.server_dir}/"
    found: list[ArchiveFile] = []
    with httpx.Client(timeout=timeout, follow_redirects=True) as client:

        def walk(relative: str) -> None:
            for name in _index_names(client, base + quote(relative)):
                if not name.endswith("/"):
                    found.append(_indexed_file(descriptor, relative + name))
                    continue
                span = _year_folder(name[:-1])
                if span is None or selected.intersection(range(span[0], span[1] + 1)):
                    walk(relative + name)

        walk("")
    return tuple(found)


# --------------------------------------------------------------------------
# Live station lists
# --------------------------------------------------------------------------


def _degrees(value: object) -> float | None:
    """A published coordinate (number or numeric text) as a finite float, else None."""
    if isinstance(value, bool) or not isinstance(value, int | float | str):
        return None
    try:
        number = float(value)
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def _located(
    entries: list[StationListEntry], kind: Kind, response: httpx.Response
) -> list[StationListEntry]:
    """
    The rows of a live list with the coordinates of the current-data API.

    Each row whose code the API answer lists with a numeric ``lat`` and ``lon``
    gets them as published (no border check); other rows keep None.
    """
    url = str(response.url)
    payload = _json_payload(response)
    if not isinstance(payload, list):
        raise ObserwatorDataError(
            message("stations.unexpected_response_from_list_stations", url=url),
            details={"url": url},
        )
    code_key = _LOCATIONS[kind][1]
    points: dict[str, tuple[float, float]] = {}
    for row in payload:
        if not isinstance(row, dict):
            continue
        code = str(row.get(code_key) or "").strip()
        latitude, longitude = _degrees(row.get("lat")), _degrees(row.get("lon"))
        if code and latitude is not None and longitude is not None:
            points.setdefault(code, (latitude, longitude))
    return [
        replace(entry, latitude=point[0], longitude=point[1])
        if (point := points.get(entry.station_code)) is not None
        else entry
        for entry in entries
    ]


# --------------------------------------------------------------------------
# The station catalog
# --------------------------------------------------------------------------


def _stored_details(root: Path) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    """
    hydro.imgw.pl's station details by code and their sidecar entry, from the raw root.

    The optional source of the IMGW-PIB catalog (ADR-021): the current version
    of ``pl.imgw.hydro_details`` when the raw root holds one, else no details
    and an entry with ``available`` false, as for a missing static file.
    """
    stored = _stored_source(root, _station_files(HYDRO_DETAILS)[0], DETAILS_SOURCE)
    if stored is None:
        return {}, {
            "source": DETAILS_SOURCE,
            "url": None,
            "file": None,
            "fetched_at": None,
            "count": 0,
            "sha256": None,
            "available": False,
        }
    data, record = stored
    rows = _api_rows(data, record, "id")
    return rows, {**record, "count": len(rows), "available": True}


def _api_rows(
    data: bytes, record: Mapping[str, Any], code_key: str
) -> dict[str, dict[str, Any]]:
    """Station rows by code of a stored answer: IMGW-PIB's current data or hydro.imgw.pl's details."""
    url = record["url"]
    try:
        payload = json.loads(data)
    except ValueError as exc:
        raise ObserwatorDataError(
            message("catalog.invalid_json_response_from", url=url)
        ) from exc
    if not isinstance(payload, list) or not all(
        isinstance(row, dict) for row in payload
    ):
        raise ObserwatorDataError(
            message("catalog.unexpected_format_response_from", url=url)
        )
    rows: dict[str, dict[str, Any]] = {}
    for row in payload:
        code = str(row.get(code_key) or "").strip()
        if code:
            rows[code] = row
    return rows


def _details(row: Mapping[str, Any] | None) -> dict[str, Any]:
    """
    The catalog properties of a station's details of hydro.imgw.pl (ADR-021).

    Numbers and texts as the station page publishes them: levels in cm above
    the gauge zero, the gauge zero in metres in its datum, the river kilometre,
    the catchment area in km², the dates of the absolute extremes as text (one
    or more days, ranges or months, sometimes a word). A gauge zero of 0 is
    none: the page writes 0 where the list of hydro.imgw.pl (``list/hydro``)
    has no gauge zero, and no gauge of IMGW-PIB has its zero at 0 m. A
    catchment area of 0 is none too: the page writes 0 for the gauges on the
    sea and its lagoons. Without details every property is null.
    """
    if row is None:
        return {**dict.fromkeys(_DETAILS_PROPERTIES), "details_source": None}
    page = row.get("properties")
    page = page if isinstance(page, dict) else {}
    status = row.get("status")
    status = status if isinstance(status, dict) else {}
    zero = _optional_float(page.get("waterGaugeZeroOrdinate")) or None
    return {
        "established_year": _optional_int(page.get("yearOfEstablishment")),
        "gauge_zero_m": zero,
        "gauge_zero_datum": None
        if zero is None
        else _text(page.get("waterGaugeZeroOrdinateReferrenceSystem")),
        "river_km": _optional_float(status.get("riverCourseKm")),
        "catchment_area_km2": _optional_float(status.get("catchmentArea")) or None,
        "province": _text(status.get("province")),
        "district": _text(page.get("district")),
        "warning_level_cm": _optional_float(status.get("warningValue")),
        "alarm_level_cm": _optional_float(status.get("alarmValue")),
        "absolute_min_level_cm": _optional_float(page.get("minimumStateValue")),
        "absolute_min_level_dates": _text(page.get("minimumStateDate")),
        "absolute_max_level_cm": _optional_float(page.get("maximumStateValue")),
        "absolute_max_level_dates": _text(page.get("maximumStateDate")),
        "details_source": DETAILS_SOURCE,
    }


def _catalog_bytes(
    *,
    provider: ProviderDescriptor,
    lists: Mapping[str, Mapping[str, StationListEntry]],
    apis: Mapping[str, Mapping[str, Mapping[str, Any]]],
    details: Mapping[str, Mapping[str, Any]],
    series: Mapping[str, set[str]],
    meteo_kinds: Mapping[str, MeteoKind],
    static: Mapping[str, tuple[str, str, str | None]],
    user: Mapping[str, tuple[str, str, str | None]],
    problems: list[str],
    rejections: list[str],
) -> tuple[bytes, int, list[str], dict[str, int], list[str], int]:
    """
    The canonical IMGW-PIB catalog and its counts.

    Returns the bytes, the number of stations, the codes of those without a
    location (in code order), the stations located by each source, the codes
    known only from series indexes and the number of hydrological stations with
    details of hydro.imgw.pl (``details`` by code; it adds no station).
    """
    # A point of the current-data answer of a family has that answer's dataset as its
    # location source.
    api_sources = dict(
        zip(("hydro", "meteo"), provider.adapter.station_sources[2:], strict=True)
    )
    for api_kind, api_rows in apis.items():
        for code in api_rows:
            if not (len(code) == 9 and code.isdecimal()):
                problems.append(
                    message("catalog.api_invalid_code", api_kind=api_kind, code=code)
                )
    listed = {
        kind: {
            code
            for code in (*lists[kind], *apis[kind])
            if len(code) == 9 and code.isdecimal()
        }
        for kind in ("hydro", "meteo")
    }
    codes = {kind: listed[kind] | series[kind] for kind in ("hydro", "meteo")}
    shared = sorted(codes["hydro"] & codes["meteo"])
    if shared:
        raise ObserwatorDataError(
            message(
                "catalog.station_codes_appear_both_hydro",
                first="hydro",
                second="meteo",
                shared=", ".join(shared[:10]),
            )
        )
    # The static file holds IMGW-PIB hydrological gauge coordinates, so a code known
    # only from it is still a (historical) hydro station: no code may disappear. The
    # user file only fills locations and names no station family.
    codes["hydro"] |= set(static) - codes["meteo"]
    known = codes["hydro"] | codes["meteo"]
    # Codes measured in a stored series but absent from every list, API and the
    # static file (e.g. stations closed long ago) stay as historical stations.
    series_only = sorted(
        (series["hydro"] | series["meteo"])
        - listed["hydro"]
        - listed["meteo"]
        - set(static)
    )
    unknown = sorted(set(user) - known)
    if unknown:
        problems.append(
            message(
                "catalog.user_locations_unknown_codes",
                count=len(unknown),
                unknown=unknown[0],
            )
        )
    features = []
    used: dict[str, int] = {}
    unlocated: list[str] = []
    detailed = 0
    for code in sorted(known):
        kind: Literal["hydro", "meteo"] = "hydro" if code in codes["hydro"] else "meteo"
        api = apis[kind].get(code)
        candidates: list[tuple[str, object, object]] = []
        if api is not None:
            candidates.append((api_sources[kind], api.get("lon"), api.get("lat")))
        if code in static:
            candidates.append(("static", static[code][0], static[code][1]))
        if code in user:
            candidates.append(("user", user[code][0], user[code][1]))
        page = details.get(code) if kind == "hydro" else None
        feature, source = _feature(
            code,
            kind=kind,
            meteo_kind=meteo_kinds.get(code) if kind == "meteo" else None,
            listed=lists[kind].get(code),
            api=api,
            details=_details(page),
            candidates=candidates,
            rejections=rejections,
        )
        if source is None:
            unlocated.append(code)
        else:
            used[source] = used.get(source, 0) + 1
        if page is not None:
            detailed += 1
        features.append(feature)
    lines = _catalog_lines(provider, {**used, DETAILS_SOURCE: detailed})
    document = {"type": "FeatureCollection", "features": features, **lines.fields()}
    return _canonical(document), len(features), unlocated, used, series_only, detailed


def _static_file() -> tuple[Path, bytes | None]:
    """Local IMGW-PIB coordinates ``station_code,latitude,longitude``; ``None`` when absent.

    IMGW data is not shipped with the package: ``python -m obserwator.reference_data`` writes
    the file into the reference directory (``OBSERWATOR_REFERENCE_DIR``, ``[obserwator] reference_dir``
    of ``nogat.toml``, else ``<cache_dir>/obserwator/reference``).
    """
    from obserwator.config import settings

    path = settings.reference_dir / STATIC_LOCATIONS
    try:
        return path, path.read_bytes()
    except FileNotFoundError:
        return path, None
    except OSError as exc:
        raise ObserwatorValidationError(
            message("catalog.cannot_read_local_location_file", path=path)
        ) from exc


def _details_action(
    raw: Path, recorded: Mapping[object, object], *, catalog: bool, cancelled: bool
) -> tuple[Literal["current", "newer", "missing", "unverifiable"], Message]:
    """
    Status and detail of the optional station details of hydro.imgw.pl in a catalog plan.

    ``current`` when the raw root holds the version the catalog was built from,
    or holds none and the catalog was built without (a catalog written before
    ADR-021 records none); ``newer`` when they appeared, changed or are gone;
    ``missing`` without a catalog.
    """
    if cancelled:
        return "unverifiable", message("common.cancelled")
    stored = _current_archive(raw, _station_files(HYDRO_DETAILS)[0])
    digest = None if stored is None else stored[1]["sha256"]
    status: Literal["current", "newer", "missing"]
    if not catalog:
        status = "missing"
    elif recorded.get(DETAILS_SOURCE) == digest:
        status = "current"
    else:
        status = "newer"
    if stored is None:
        return status, message(
            "catalog.details_not_stored", source=DETAILS_SOURCE, dataset=HYDRO_DETAILS
        )
    return status, message(
        "catalog.source_detail",
        source=DETAILS_SOURCE,
        file=stored[0].relative_to(raw).as_posix(),
    )


def _static_missing(
    path: Path, unlocated: Sequence[str], details: Mapping[str, Any]
) -> Message:
    """
    The problem of a missing static file, with what it costs when the raw root tells.

    The file holds the coordinates of the stations of hydro.imgw.pl's map, whose
    pages are the station details (``pl.imgw.hydro_details``, ADR-021): with the
    details stored, the stations the file would locate are those with details and
    without a location, so they are counted; without the details the cost is
    unknown. IMGW-PIB's data are not shipped with Obserwator, so the message names
    the command that downloads the file.
    """
    gap = [code for code in unlocated if code in details]
    if not gap:
        return message("catalog.static_missing", static_path=path.as_posix())
    return message(
        "catalog.static_missing_stations",
        static_path=path.as_posix(),
        count=len(gap),
        example=gap[0],
    )


def _meteo_kind_gap(
    root: Path, raw: Path, series_sources: Sequence[Mapping[str, Any]]
) -> Notice | None:
    """
    The ``series_missing`` notice of the meteo series a data root lacks, or None.

    ``meteo_kind`` of an IMGW-PIB station comes only from the current series of
    `_METEO_KINDS` in the data root (the station lists publish no kind): without
    any of them every meteorological station has none (a warning); without some, a
    station measured only in a missing one has a lower kind or none (information).
    Both name the ``series build`` of the first missing dataset.
    """
    held = {entry["dataset"] for entry in series_sources}
    absent = [key for key in _METEO_KINDS if key not in held]
    if not absent:
        return None
    if len(absent) == len(_METEO_KINDS):
        return Notice(
            "warning",
            "series_missing",
            message(
                "catalog.meteo_kind_without_series",
                datasets=", ".join(absent),
                root=root,
                raw=raw,
                dataset=absent[0],
            ),
        )
    return Notice(
        "info",
        "series_missing",
        message(
            "catalog.meteo_kind_partial_series",
            sources=", ".join(_METEO_KINDS),
            root=root,
            datasets=", ".join(absent),
            raw=raw,
            dataset=absent[0],
        ),
    )


def _build_imgw(build: CatalogBuild) -> CatalogReport:
    """IMGW-PIB catalog from the station lists, public APIs, station details and location files."""
    owner, user = build.provider, build.user
    # Location files are validated before any download, so a bad header writes nothing.
    static_path, static_bytes = _static_file()
    static, static_problems = (
        _read_locations(static_bytes, static=STATIC_LOCATIONS, provider=owner)
        if static_bytes is not None
        else ({}, [])
    )
    user_rows, user_problems = (
        _read_locations(user[1], static=None, provider=owner)
        if user is not None
        else ({}, [])
    )
    if (report := build.stopped()) is not None:
        return report
    stored = _read_sources(build.raw, owner)
    sources: list[dict[str, Any]] = []
    lists: list[bytes] = []
    apis: list[dict[str, dict[str, Any]]] = []
    for step, (source, archive) in enumerate(
        _catalog_sources(build.raw, owner), start=1
    ):
        data, record = stored[source]
        if source in ("api_hydro", "api_meteo"):
            rows = _api_rows(
                data, record, "id_stacji" if source == "api_hydro" else "kod_stacji"
            )
            record["count"] = len(rows)
            apis.append(rows)
        else:
            lists.append(data)
        sources.append(record)
        build.progress(
            step,
            "done",
            message(
                "catalog.source_read",
                server_path=archive.server_path if archive else source,
            ),
        )
    details, details_record = _stored_details(build.raw)
    sources.append(details_record)
    server_path = _station_files(HYDRO_DETAILS)[0].server_path
    if details_record["available"]:
        build.progress(
            5, "done", message("catalog.source_read", server_path=server_path)
        )
    else:
        build.progress(
            5, "missing", message("catalog.details_absent", server_path=server_path)
        )
    if (report := build.stopped()) is not None:
        return report
    problems: list[str] = []
    rejections: list[str] = []
    parsed_lists = {
        "hydro": _list_rows(lists[0], kind="hydro", problems=problems),
        "meteo": _list_rows(lists[1], kind="meteo", problems=problems),
    }
    sources[0]["count"] = len(parsed_lists["hydro"])
    sources[1]["count"] = len(parsed_lists["meteo"])
    if static_bytes is None:
        sources.append(
            {
                "source": "static",
                "url": None,
                "file": STATIC_LOCATIONS,
                "fetched_at": None,
                "count": 0,
                "sha256": None,
                "available": False,
            }
        )
    else:
        problems.extend(static_problems)
        sources.append(
            _local_source(
                static_bytes, source="static", file=STATIC_LOCATIONS, count=len(static)
            )
            | {"available": True}
        )
    if user is not None:
        problems.extend(user_problems)
        sources.append(
            _local_source(
                user[1], source="user", file=user[0].name, count=len(user_rows)
            )
        )
    series, series_sources, meteo_kinds = _series_codes(
        build.root, problems, provider=owner
    )
    sources.extend(series_sources)
    data, count, unlocated, used, series_only, detailed = _catalog_bytes(
        provider=owner,
        lists=parsed_lists,
        apis={"hydro": apis[0], "meteo": apis[1]},
        details=details,
        series=series,
        meteo_kinds=meteo_kinds,
        static=static,
        user=user_rows,
        problems=problems,
        rejections=rejections,
    )
    build.progress(6, "done", message("catalog.catalog_built", count=count))
    if not details_record["available"] and build.on_notice is not None:
        build.on_notice(
            Notice(
                "info",
                "source_missing",
                message(
                    "catalog.details_missing", root=build.raw, dataset=HYDRO_DETAILS
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
        without=len(unlocated),
    )
    # What the person can fill, after the summary of the locations: the static file
    # (also a problem of the report, though no catalog_problem notice) and the meteo
    # series of meteo_kind.
    gaps: list[Notice] = []
    if static_bytes is None:
        missing = _static_missing(static_path, unlocated, details)
        problems.append(missing)
        gaps.append(Notice("warning", "source_missing", missing))
    if (meteo := _meteo_kind_gap(build.root, build.raw, series_sources)) is not None:
        gaps.append(meteo)
    if build.on_notice is not None:
        for notice in gaps:
            build.on_notice(notice)
    if (report := build.stopped()) is not None:
        return report
    problems.extend(rejections)
    return build.publish(
        data,
        sources=sources,
        count=count,
        without=len(unlocated),
        from_series=len(series_only),
        problems=problems,
        lines=_catalog_lines(owner, {**used, DETAILS_SOURCE: detailed}),
    )


# --------------------------------------------------------------------------
# The adapter
# --------------------------------------------------------------------------


class ImgwAdapter(ProviderAdapter):
    """The adapter of IMGW-PIB (ADR-029); `ADAPTER` is its one instance."""

    provider_id = "IMGW"
    origin: Origin = "imgw"
    origins: tuple[Origin, ...] = ("imgw", "imgw_hydro")
    border = POLAND
    groups = frozenset({"current", "pmaxtp"})
    current: Mapping[str, Callable[[], Any]] = MappingProxyType(
        {
            "states": fetch_hydro_states,
            "hydro": fetch_hydro_current,
            "meteo": fetch_meteo_current,
            "synop": fetch_synop,
        }
    )
    station_sources = (
        "pl.imgw.hydro_stations",
        "pl.imgw.meteo_stations",
        "pl.imgw.hydro_now",
        "pl.imgw.meteo_now",
    )
    optional_sources = (HYDRO_DETAILS,)
    archive_suffixes = (".zip", ".csv")
    sidecar_station = False

    @property
    def server_name(self) -> str:
        """``IMGW``: the server's name in the texts of 3.0.0's failed requests."""
        return "IMGW"

    def dataset_origin(self, key: str) -> Origin:
        """PMAXTP's and hydro.imgw.pl's station details' own; danepubliczne's otherwise."""
        return _DATASET_ORIGINS.get(key, self.origin)

    def station_origins(
        self,
        properties: Mapping[str, object],
        *,
        location: bool = True,
        details: bool = True,
    ) -> tuple[Origin, ...]:
        """hydro.imgw.pl's for a location from its map (``static``) or its station details."""
        if (details and properties.get("details_source") is not None) or (
            location and properties.get("location_source") == "static"
        ):
            return ("imgw_hydro",)
        return ()

    # --- archives --------------------------------------------------------------

    def indexed(self, descriptor: DatasetDescriptor, /) -> bool:
        """Whether the dataset's files are named only in the server's folder index."""
        return descriptor.update_signal == "listing"

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
        """Country archives, the per-station synop archives; a dataset in the index refused."""
        if self.indexed(descriptor):
            _indexed_years(descriptor, years=years, params=params, stations=stations)
            raise ObserwatorValidationError(
                message("datasets.files_named_in_folder_index", key=descriptor.key),
                details={
                    "option": "dataset",
                    "value": descriptor.key,
                    "reason": "listed",
                },
            )
        if descriptor.archive_scope == "country":
            return _country_archives(
                descriptor, years=years, months=months, params=params, stations=stations
            )
        return _station_archives(
            descriptor, years=years, months=months, params=params, stations=stations
        )

    def archive_from_path(
        self, descriptor: DatasetDescriptor, server_path: str, /
    ) -> ArchiveFile | None:
        """A file of the index, a per-station synop archive or a country archive."""
        directory, _, name = server_path.rpartition("/")
        if self.indexed(descriptor):
            prefix = f"{descriptor.server_dir}/"
            if not server_path.startswith(prefix) or server_path.endswith("/"):
                return None
            return _indexed_file(descriptor, server_path.removeprefix(prefix))
        if descriptor.archive_scope == "station_year":
            return _station_path(descriptor, directory, name)
        parent, _, folder = directory.rpartition("/")
        years = _FOLDER.fullmatch(folder)
        if years is None or parent != descriptor.server_dir:
            return None
        first = max(int(years[1]), descriptor.first_year or 1)
        for year in range(first, int(years[2] or years[1]) + 1):
            for item in self.archive_files(
                descriptor, years=(year,), months=None, params=None, stations=None
            ):
                if item.server_path == server_path:
                    return item
        return None

    def index_files(
        self,
        descriptor: DatasetDescriptor,
        /,
        *,
        years: YearsArg | None,
        params: Iterable[Literal["H", "Q", "T"]] | None,
        stations: Iterable[str] | None,
        index: bool,
        timeout: float,
    ) -> tuple[ArchiveFile, ...]:
        """The files the folder index names in the selected years (ADR-023)."""
        selected = _indexed_years(
            descriptor, years=years, params=params, stations=stations
        )
        if not index:
            return ()
        return _indexed_archives(descriptor, selected, timeout=timeout)

    def station_key(self, code: str, /) -> str:
        """The station number of the synop archives: the code's last three digits."""
        return code[-3:]

    def archive_station(self, archive: ArchiveFile, /) -> str | None:
        """The number of a per-station synop archive's station; None for another file."""
        station = _STATION_FILE.fullmatch(PurePosixPath(archive.server_path).name)
        return None if station is None else station[3]

    def download(
        self,
        archive: ArchiveFile,
        /,
        *,
        client: httpx.Client | None,
        cancel: Callable[[], bool] | None,
    ) -> DownloadResult:
        """
        One file: a country archive through the 2.1.1 functions, the station details.

        hydro.imgw.pl's station details are one request per station of its map
        (ADR-021); a per-station synop archive or a station list is one GET.
        """
        descriptor = get_dataset(archive.dataset)
        if descriptor.key == HYDRO_DETAILS:
            assert client is not None
            return _hydro_details(client, archive.url, cancel=cancel)
        if (
            descriptor.archive_scope != "country"
            or descriptor.time_unit == "station_list"
        ):
            return super().download(archive, client=client, cancel=cancel)
        assert archive.year is not None
        if descriptor.kind == "hydro":
            return download_hydro_data(
                _HYDRO_INTERVALS[descriptor.key],
                archive.year,
                archive.month,
                cast(Literal["T", "Q", "H"] | None, archive.param),
            )
        subtype: Literal["klimat", "opad"] = (
            "klimat" if descriptor.key == "pl.imgw.meteo_climate_daily" else "opad"
        )
        return download_meteo_data("dobowe", subtype, archive.year, archive.month)

    # --- the store's checks ----------------------------------------------------

    def check_scope(self, descriptor: DatasetDescriptor, /) -> CheckScope:
        """Country archives offline and by HEAD; the synop archives by the folder index."""
        return "country" if descriptor.archive_scope == "country" else "folders"

    def folders(
        self, descriptor: DatasetDescriptor, years: Iterable[int], /
    ) -> list[str]:
        """The folder of each selected year: a five-year folder until 2000, then a year."""
        assert descriptor.server_dir is not None and descriptor.first_year is not None
        _, first_folder_end = _METEO_LAYOUT[descriptor.key]
        return list(
            dict.fromkeys(
                f"{descriptor.server_dir}/"
                + _meteo_folder(
                    year,
                    first_year=descriptor.first_year,
                    first_folder_end=first_folder_end,
                )
                for year in years
            )
        )

    # --- station sources -------------------------------------------------------

    def parse_station_list(
        self, content: bytes, /, *, kind: Kind, filename: str
    ) -> list[StationListEntry]:
        """The station list CSV of a family (IMGW-PIB publishes no groundwater list)."""
        if kind == "groundwater":
            raise ValueError(f"{self.provider_id} publishes no {kind} station list")
        return list(parse_stations_csv(content, kind=kind))

    def _live(self, kind: Kind) -> tuple[str, str]:
        """The station list of a family and the current-data API answer locating it."""
        lists = dict(zip(("hydro", "meteo"), self.station_sources[:2], strict=True))
        return (
            _station_files(lists[kind])[0].url,
            _station_files(_LOCATIONS[kind][0])[0].url,
        )

    def live_urls(self, kind: Kind, /) -> list[str]:
        """The list, then the current-data API answer of its coordinates."""
        return list(self._live(kind))

    def live_stations(self, kind: Kind, /, *, timeout: float) -> list[StationListEntry]:
        """The list's rows with the coordinates of the current-data API (two GETs)."""
        url, locations = self._live(kind)
        response = _get(url, timeout=timeout, source=self.server_name)
        entries = self.parse_station_list(response.content, kind=kind, filename=url)
        answer = _get(locations, timeout=timeout, source=self.server_name)
        return _located(entries, kind, answer)

    async def live_stations_async(
        self, kind: Kind, /, *, timeout: float
    ) -> list[StationListEntry]:
        """Async twin of `live_stations`."""
        url, locations = self._live(kind)
        response = await _get_async(url, timeout=timeout, source=self.server_name)
        entries = self.parse_station_list(response.content, kind=kind, filename=url)
        answer = await _get_async(locations, timeout=timeout, source=self.server_name)
        return _located(entries, kind, answer)

    # --- the station catalog ---------------------------------------------------

    def catalog_sources(self, raw: Path, /) -> list[tuple[str, ArchiveFile | None]]:
        """The two lists, then the current-data API answers ``api_hydro``, ``api_meteo``."""
        hydro_list, meteo_list, hydro_now, meteo_now = self.station_sources
        return [
            *(
                (get_dataset(key).slug, _station_files(key)[0])
                for key in (hydro_list, meteo_list)
            ),
            ("api_hydro", _station_files(hydro_now)[0]),
            ("api_meteo", _station_files(meteo_now)[0]),
        ]

    def source_datasets(self) -> list[str]:
        """The four station sources, one file each."""
        return list(self.station_sources)

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
        """The station details of hydro.imgw.pl (ADR-021)."""
        return _details_action(raw, recorded, catalog=catalog, cancelled=cancelled)

    def location_files(self) -> list[tuple[str, bytes | None, Path]]:
        """The static file of hydro.imgw.pl's map, always checked."""
        static_path, static_bytes = _static_file()
        return [("static", static_bytes, static_path)]

    def build_catalog(self, build: CatalogBuild, /) -> CatalogReport:
        """The catalog from the lists, the API answers, the details and the location files."""
        return _build_imgw(build)

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
        """The hydrological, daily meteorological and synop archives."""
        if archive.dataset in _HYDRO_PARSED:
            yield from normalize_hydro_archive(
                archive.dataset,
                archive.server_path,
                data,
                stations=stations,
                skipped_months=skipped_months,
            )
        elif archive.dataset in _METEO_PARSED:
            yield from normalize_meteo_archive(
                archive.dataset,
                archive.server_path,
                data,
                year=archive.year,
                month=archive.month,
                carry=carry if archive.dataset in CARRY_DATASETS else None,
                stations=stations,
                skipped_months=skipped_months,
            )
        elif archive.dataset == _SYNOP_PARSED:
            yield from normalize_synop_archive(
                archive.server_path,
                data,
                start=archive.period_start,
                end=archive.period_end,
            )
        else:
            raise ObserwatorValidationError(
                message("parsing.no_parser_archive", dataset=archive.dataset)
            )


ADAPTER = ImgwAdapter()
"""The adapter of IMGW-PIB."""
