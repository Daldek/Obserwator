"""
The adapter of every provider fed by files (ADR-033; Nogat plan 2026-11-21, I13).

An operator's own network enters as data, not code: a provider file beside
``nogat.toml`` declares it (`obserwator._provider_files`), and ``store import``
(`obserwator.store.import_files`) keeps its station file and its station series in the
raw root as they came and builds its series and its catalog in the data root. One
`FileFedAdapter` per provider file serves it as ADR-029 serves IMGW-PIB and ČHMÚ, so
the store, the servers and the GUI treat it as any provider and no module compares its
id. It has no server: nothing of it is downloaded, checked against a server, polled or
harvested; its live station search reads its station file.

Its files in the raw root lie below ``archives/versions/files/<acronym>/``:
``station_list/stations.geojson`` (the station file, whatever the operator calls it)
and ``<dataset>/<station code>.csv`` or ``.parquet`` (one station's whole series), each
version with its sidecar; the address of a version (``extra.http.url``) is the path of
the operator's file as its provider file names it.
"""

from __future__ import annotations

import re
from collections.abc import Collection, Iterable, Iterator
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from obserwator._borders import CZECHIA, POLAND
from obserwator._parsing.files import (
    FileStation,
    parse_series_export,
    read_station_file,
)
from obserwator._provider_files import STATIONS_FILE, FileDataset, ProviderFile
from obserwator.datasets import (
    KINDS,
    ArchiveFile,
    DatasetDescriptor,
    MonthsArg,
    YearsArg,
)
from obserwator.exceptions import ObserwatorDataError, ObserwatorValidationError
from obserwator.messages import message
from obserwator.models import NormalizedRecord, StationListEntry
from obserwator.providers.base import CheckScope, Kind, ProviderAdapter
from obserwator.store.catalog import (
    _Candidate,
    _catalog_lines,
    _catalog_notices,
    _local_source,
    _locate,
    _placement,
    _read_locations,
    _read_sources,
    _series_codes,
)
from obserwator.store.writer import _canonical

if TYPE_CHECKING:
    from obserwator.attribution import Origin
    from obserwator.store.catalog import CatalogBuild
    from obserwator.store.types import CatalogReport

__all__ = ["FileFedAdapter"]

# The properties of a station of the catalog of a provider fed by files, in order; a
# groundwater object adds ``groundwater_kind`` (as ČHMÚ's, ADR-032).
_PROPERTIES = (
    "station_code",
    "kind",
    "meteo_kind",
    "name",
    "river",
    "hydrographic_code",
    "river_order",
    "location_source",
    "location_uncertainty_m",
    "location_missing_reason",
    "active",
    "established_year",
    "gauge_zero_m",
    "gauge_zero_datum",
    "river_km",
    "catchment_area_km2",
    "elevation_m",
)


def _feature(
    code: str,
    *,
    kind: Kind,
    station: FileStation | None,
    candidates: list[_Candidate],
    border: str,
    rejections: list[str],
) -> tuple[dict[str, Any], str | None]:
    """A station of the catalog and the source of its location, None without one."""
    located = _locate(code, candidates, border=border, rejections=rejections)
    geometry, location_source, uncertainty, reason = _placement(located, candidates)
    properties: dict[str, Any] = {
        "station_code": code,
        "kind": kind,
        "meteo_kind": None,
        "name": station.name if station else "",
        "river": station.river if station else None,
        "hydrographic_code": station.hydrographic_code if station else None,
        "river_order": None,
        "location_source": location_source,
        "location_uncertainty_m": uncertainty,
        "location_missing_reason": reason,
        # A station known only from a series is no station of the operator's file.
        "active": station.active if station else False,
        "established_year": station.established_year if station else None,
        "gauge_zero_m": station.gauge_zero_m if station else None,
        "gauge_zero_datum": station.gauge_zero_datum if station else None,
        "river_km": station.river_km if station else None,
        "catchment_area_km2": station.catchment_area_km2 if station else None,
        "elevation_m": station.elevation_m if station else None,
    }
    if kind == "groundwater":
        properties["groundwater_kind"] = station.groundwater_kind if station else None
    feature = {
        "type": "Feature",
        "id": code,
        "geometry": geometry,
        "properties": properties,
    }
    return feature, location_source


def _entry(station: FileStation, provider: str) -> StationListEntry:
    """A station of the file as a live search gives it."""
    return StationListEntry(
        kind=station.kind,
        station_code=station.station_code,
        name=station.name,
        river=station.river,
        hydrographic_code=station.hydrographic_code,
        latitude=None if station.latitude is None else float(station.latitude),
        longitude=None if station.longitude is None else float(station.longitude),
        provider=provider,
        groundwater_kind=station.groundwater_kind,
    )


class FileFedAdapter(ProviderAdapter):
    """
    The adapter of one provider fed by files (ADR-033).

    Parameters
    ----------
    provider_file : ProviderFile
        The provider file that declares the provider.
    """

    identifies = False
    kinds = KINDS
    archive_suffixes = (".csv", ".parquet")
    sidecar_station = True
    source_class: Literal["nmhs", "other"] = "other"

    def __init__(self, provider_file: ProviderFile) -> None:
        self.provider_file = provider_file
        self.provider_id = provider_file.id
        self.origin: Origin = provider_file.acronym
        self.origins: tuple[Origin, ...] = (provider_file.acronym,)
        self.border = CZECHIA if provider_file.country == "CZ" else POLAND
        stations = f"{provider_file.key_prefix}.station_list"
        self.station_sources = (stations, stations, stations, stations)

    @property
    def _file(self) -> ProviderFile:
        """The provider file, never None for this adapter."""
        assert self.provider_file is not None
        return self.provider_file

    def _dataset(self, key: str) -> FileDataset | None:
        """The dataset of the provider file that a key names; None for another key."""
        prefix = f"{self._file.key_prefix}."
        name = key.removeprefix(prefix)
        return next(
            (
                item
                for item in self._file.datasets
                if key.startswith(prefix) and item.name == name
            ),
            None,
        )

    # --- the publication state (P15) ----------------------------------------------

    def publication_default(self, key: str, /) -> Literal["public", "private"]:
        """The ``publication`` of the provider file; ``private`` when it says none."""
        return self._file.publication or "private"

    # --- archives --------------------------------------------------------------------

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
        """
        Refuse: the files of a provider fed by files are its operator's, not a server's.

        Raises
        ------
        ObserwatorValidationError
            Always (``details.reason`` ``fed_by_files``): ``store import`` reads the
            files the provider file names.
        """
        raise ObserwatorValidationError(
            message(
                "provider_files.dataset_fed_by_files",
                key=descriptor.key,
                provider=self.provider_id,
            ),
            details={
                "option": "dataset",
                "value": descriptor.key,
                "reason": "fed_by_files",
            },
        )

    def archive_from_path(
        self, descriptor: DatasetDescriptor, server_path: str, /
    ) -> ArchiveFile | None:
        """A station's series file ``<server_dir>/<station code>.csv`` (or ``.parquet``)."""
        directory, _, name = server_path.rpartition("/")
        dataset = self._dataset(descriptor.key)
        stem, dot, suffix = name.rpartition(".")
        if (
            dataset is None
            or directory != descriptor.server_dir
            or not dot
            or f".{suffix}" not in self.archive_suffixes
            or not re.fullmatch(self._file.station_code_pattern, stem)
        ):
            return None
        return ArchiveFile(
            descriptor.key,
            server_path,
            f"{dataset.directory}/{name}",
            None,
            None,
            None,
            "none",
            None,
            None,
            stem,
        )

    def check_scope(self, descriptor: DatasetDescriptor, /) -> CheckScope:
        """
        No check: no server publishes the files (``store check`` does not offer them).

        Raises
        ------
        ValueError
            Always.
        """
        raise ValueError(f"{descriptor.key}: {self.provider_id} is fed by files")

    # --- station sources ---------------------------------------------------------

    def station_file(
        self, descriptor: DatasetDescriptor, name: str, /
    ) -> ArchiveFile | None:
        """The station file ``stations.geojson`` of the provider's station list."""
        if descriptor.key != self.station_sources[0] or name != STATIONS_FILE:
            return None
        return ArchiveFile(
            descriptor.key,
            f"{descriptor.server_dir}/{name}",
            self._file.stations,
            None,
            None,
            None,
            "none",
            None,
            None,
        )

    def _stations(self, content: bytes, filename: str) -> tuple[FileStation, ...]:
        return read_station_file(
            content, pattern=self._file.station_code_pattern, filename=filename
        )

    def parse_station_list(
        self, content: bytes, /, *, kind: Kind, filename: str
    ) -> list[StationListEntry]:
        """The stations of one family of the provider's station file."""
        return [
            _entry(station, self.provider_id)
            for station in self._stations(content, filename)
            if station.kind == kind
        ]

    def live_urls(self, kind: Kind, /) -> list[str]:
        """The station file as the provider file names it."""
        return [self._file.stations]

    def live_stations(self, kind: Kind, /, *, timeout: float) -> list[StationListEntry]:
        """
        The stations of one family of the operator's station file, read from disk.

        Raises
        ------
        ObserwatorDataError
            If the file cannot be read or is no valid station file.
        """
        path = self._file.stations_path
        try:
            content = path.read_bytes()
        except OSError as exc:
            raise ObserwatorDataError(
                message(
                    "provider_files.stations_unreadable",
                    provider=self.provider_id,
                    path=self._file.stations,
                    reason=exc.strerror or str(exc),
                ),
                details={"path": self._file.stations},
            ) from exc
        return self.parse_station_list(content, kind=kind, filename=self._file.stations)

    async def live_stations_async(
        self, kind: Kind, /, *, timeout: float
    ) -> list[StationListEntry]:
        """`live_stations`: a file on disk asks no server."""
        return self.live_stations(kind, timeout=timeout)

    # --- the station catalog -----------------------------------------------------

    def catalog_sources(self, raw: Path, /) -> list[tuple[str, ArchiveFile | None]]:
        """The station file, the one source of the catalog."""
        key = self.station_sources[0]
        source = f"{self._file.acronym}_station_list"
        return [(source, self.station_file(_descriptor(key), STATIONS_FILE))]

    def source_datasets(self) -> list[str]:
        """The provider's station list."""
        return [self.station_sources[0]]

    def build_catalog(self, build: CatalogBuild, /) -> CatalogReport:
        """
        The catalog from the stored station file, the series indexes and the user file.

        Every station of the station file and every code of the provider's current
        series is a station; a code only in a series is a station of the series'
        family without a name, located only by the user file. A point lies in the
        provider's country (its packaged border, ADR-018) or the station has no
        location (``outside_country``); ``location_source`` is the key of the station
        list (ADR-028 D2) or ``user``.
        """
        owner, user = build.provider, build.user
        user_rows, user_problems = (
            _read_locations(user[1], static=None, provider=owner)
            if user is not None
            else ({}, [])
        )
        if (report := build.stopped()) is not None:
            return report
        stored = _read_sources(build.raw, owner)
        ((source, _),) = self.catalog_sources(build.raw)
        data, record = stored[source]
        build.progress(
            1, "done", message("catalog.source_read", server_path=record["file"])
        )
        # A stored station file that cannot be read stops the build (data_error).
        stations = self._stations(data, str(record["file"]))
        record["count"] = len(stations)
        records: list[dict[str, Any]] = [record]
        problems: list[str] = []
        rejections: list[str] = []
        if user is not None:
            problems.extend(user_problems)
            records.append(
                _local_source(
                    user[1], source="user", file=user[0].name, count=len(user_rows)
                )
                | {"available": True}
            )
        series, series_sources, _ = _series_codes(build.root, problems, provider=owner)
        records.extend(series_sources)
        listed = {station.station_code: station for station in stations}
        families: dict[str, Kind] = {code: item.kind for code, item in listed.items()}
        for kind in KINDS:
            for code in sorted(series.get(kind, ())):
                if code not in families:
                    families[code] = kind
                elif families[code] != kind:
                    problems.append(
                        message(
                            "provider_files.series_of_other_kind",
                            code=code,
                            kind=families[code],
                            series=kind,
                        )
                    )
        if (report := build.stopped()) is not None:
            return report
        key = self.station_sources[0]
        features = []
        used: dict[str, int] = {}
        without = 0
        for code in sorted(families):
            station = listed.get(code)
            candidates: list[_Candidate] = []
            if station is not None and station.longitude is not None:
                candidates.append((key, station.longitude, station.latitude))
            if code in user_rows:
                candidates.append(("user", user_rows[code][0], user_rows[code][1]))
            feature, location = _feature(
                code,
                kind=families[code],
                station=station,
                candidates=candidates,
                border=self.border,
                rejections=rejections,
            )
            if location is None:
                without += 1
            else:
                used[location] = used.get(location, 0) + 1
            features.append(feature)
        series_only = sorted(set(families) - set(listed))
        lines = _catalog_lines(owner, used)
        document = {"type": "FeatureCollection", "features": features, **lines.fields()}
        build.progress(6, "done", message("catalog.catalog_built", count=len(features)))
        _catalog_notices(
            build.on_notice,
            problems=problems,
            rejections=rejections,
            used=used,
            user_rows=user_rows if user is not None else None,
            series_only=series_only,
            without=without,
        )
        if (report := build.stopped()) is not None:
            return report
        problems.extend(rejections)
        return build.publish(
            _canonical(document),
            sources=records,
            count=len(features),
            without=without,
            from_series=len(series_only),
            problems=problems,
            lines=lines,
        )

    # --- parsers -------------------------------------------------------------------

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
        """
        One station's series file (``obserwator-series-csv`` or its Parquet).

        Raises
        ------
        ObserwatorValidationError
            For a file of no series dataset of the provider (``no_parser_archive``).
        ObserwatorDataError
            If the file is no such series (`obserwator.parsers.parse_series_export`).
        """
        if self._dataset(archive.dataset) is None or archive.station_code is None:
            raise ObserwatorValidationError(
                message("parsing.no_parser_archive", dataset=archive.dataset)
            )
        yield from parse_series_export(
            data,
            dataset=archive.dataset,
            station=archive.station_code,
            filename=archive.server_path,
        )


def _descriptor(key: str) -> DatasetDescriptor:
    """The registry entry of a key (the registry imports no adapter, so at call time)."""
    from obserwator.datasets import get_dataset

    return get_dataset(key)


def adapters(files: Iterable[ProviderFile]) -> tuple[FileFedAdapter, ...]:
    """
    The adapter of each provider file the registry read.

    Parameters
    ----------
    files : iterable of ProviderFile
        The valid provider files (`obserwator.datasets.provider_files`).

    Returns
    -------
    tuple of FileFedAdapter
        One adapter per file, in order.
    """
    return tuple(FileFedAdapter(item) for item in files)
