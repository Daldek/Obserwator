"""
ČHMÚ, Czechia's hydrometeorological institute (provider ``CHMU``).

The CC BY 4.0 open data of opendata.chmi.cz: files of one station (one per station
and year of the daily hydrological data, one per station and element of the daily
meteorological data), the station metadata of ``historical`` and ``now`` and the
station catalog built from them (spec 2026-10-18).
"""

from __future__ import annotations

import re
from collections.abc import Collection, Iterable, Iterator, Mapping
from datetime import date
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, Literal

from obserwator._borders import CZECHIA
from obserwator._parsing.chmu import (
    HYDRO_FILE,
    METEO_FILE,
    iter_stations,
    parse_chmu_hydro_daily,
    parse_chmu_meteo_daily,
    parse_listing,
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

if TYPE_CHECKING:
    from obserwator.attribution import Origin
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
        from obserwator.store import catalog as store_catalog

        hydro_list, meteo_list, hydro_now, _ = self.station_sources
        meta1, meta3 = _station_files(hydro_now)
        return [
            *(
                (get_dataset(key).slug, _station_files(key)[0])
                for key in (hydro_list, meteo_list)
            ),
            ("chmu_hydro_now", meta1),
            ("chmu_hydro_meta3", meta3),
            ("chmu_meteo_now", store_catalog._chmu_meteo_now(raw)),
        ]

    def source_datasets(self) -> list[str]:
        """The lists, the hydro ``now`` metadata twice (two files), the meteo one."""
        hydro_list, meteo_list, hydro_now, meteo_now = self.station_sources
        return [hydro_list, meteo_list, hydro_now, hydro_now, meteo_now]

    def build_catalog(self, build: CatalogBuild, /) -> CatalogReport:
        """The catalog from the stored ``now`` and ``historical`` metadata and the user file."""
        from obserwator.store import catalog as store_catalog

        return store_catalog._build_chmu(build)

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
