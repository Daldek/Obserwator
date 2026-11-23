"""
IMGW-PIB, Poland's hydrological and meteorological service (provider ``IMGW``).

The archives of danepubliczne.imgw.pl (files of the whole country in year or
five-year folders, the per-station synop archives, the actinometric files named only
in the folder index), its station lists and current-data API, hydro.imgw.pl's map
and station details (ADR-021), and the station catalog built from them (ADR-015).
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable, Collection, Iterable, Iterator, Mapping
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

if TYPE_CHECKING:
    from obserwator.attribution import Origin
    from obserwator.store.catalog import CatalogBuild
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
        """The station list CSV of a family."""
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
        from obserwator.store import catalog as store_catalog

        return store_catalog._details_action(
            raw, recorded, catalog=catalog, cancelled=cancelled
        )

    def location_files(self) -> list[tuple[str, bytes | None, Path]]:
        """The static file of hydro.imgw.pl's map, always checked."""
        from obserwator.store import catalog as store_catalog

        static_path, static_bytes = store_catalog._static_file()
        return [("static", static_bytes, static_path)]

    def build_catalog(self, build: CatalogBuild, /) -> CatalogReport:
        """The catalog from the lists, the API answers, the details and the location files."""
        from obserwator.store import catalog as store_catalog

        return store_catalog._build_imgw(build)

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
