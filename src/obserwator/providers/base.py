"""
The interface every provider adapter implements (ADR-029).

The registry (`obserwator.datasets`) declares what a provider and its datasets are;
an adapter does what is particular to the provider: it enumerates and downloads its
files, reads its station sources, parses its datasets, names its server and the
attribution origins of its data, and builds its station catalog. The store keeps the
mechanisms (checks by HEAD, by a folder index or by a directory listing; the catalog's
location checks and publication; the series builder) and asks the adapter wherever
providers differ, so no module outside ``obserwator.providers`` and the registry
compares a provider's name.

`ProviderAdapter` is a `typing.Protocol`; the adapters of ``obserwator.providers``
subclass it explicitly to inherit the defaults of the optional members (no live current
data, no credential, no polled source; every answer of a capture dataset written to the
capture spool, ADR-030 D7).
"""

from __future__ import annotations

from collections.abc import Callable, Collection, Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Literal, Protocol

# A station family is the registry's (``groundwater`` since ADR-032).
from obserwator.datasets import Kind

if TYPE_CHECKING:
    import httpx

    from obserwator._provider_files import ProviderFile
    from obserwator.attribution import Origin
    from obserwator.captures import Spooled
    from obserwator.datasets import (
        ArchiveFile,
        DatasetDescriptor,
        MonthsArg,
        ProviderCredential,
        ProviderDescriptor,
        YearsArg,
    )
    from obserwator.fetch import DownloadResult, PacedRequest, PacedSession
    from obserwator.messages import Message
    from obserwator.models import NormalizedRecord, StationListEntry
    from obserwator.store.catalog import CatalogBuild
    from obserwator.store.types import CatalogReport, Notice, NoticeHook, PlanAction

__all__ = [
    "Answer",
    "CheckScope",
    "Kind",
    "PolledSource",
    "ProviderAdapter",
    "SeriesContext",
    "SourceAction",
]

CheckScope = Literal[
    "country", "folders", "stations", "listing", "months", "publication"
]
"""
How ``store check`` finds and checks the files of a measurement dataset.

``country``: files enumerated offline (`ProviderAdapter.archive_files`), checked by
HEAD; ``folders``: files named in the index of each folder of the selected years
(`ProviderAdapter.folders`), checked by HEAD; ``stations``: one directory listing per
directory of the station files (`ProviderAdapter.listed_station`), which is their
signal; ``listing``: files enumerated offline and published when the provider's
listing of their directory names them (`ProviderAdapter.listing`), without any HTTP
signal: a stored file is current, as published once (IMGW-PIB's telemetry);
``months``: a station's month files gathered from an API's answers, named by the
station list the raw root holds (`ProviderAdapter.month_files`) and checked against
the clock without a request: a version downloaded once its month had settled
(`ProviderAdapter.settled`) is current, an earlier one is fetched again (the provider
``GDANSKIEWODY``, ADR-034); ``publication``: the one file a service publishes now,
named by what it holds (`ProviderAdapter.published`: PIG-PIB's readings by the
calendar month of their rows, ADR-035), without an HTTP signal: ``store sync``
downloads it and compares its content with the slot's current version.
"""

SourceAction = tuple[Literal["current", "newer", "missing", "unverifiable"], "Message"]
"""Status and detail of an optional catalog source in a ``store catalog`` plan."""


@dataclass(frozen=True)
class SeriesContext:
    """
    What a series build gives a provider's parsers beside one stored file (ADR-035).

    Attributes
    ----------
    sources : Mapping of str to bytes
        The current version of each of the provider's `ProviderAdapter.series_sources`
        in the raw root, by dataset key (PIG-PIB's points, whose ground elevation
        gives ``H_asl``); a source without a version is left out.
    on_notice : NoticeHook or None
        Receives the parser's warnings about what it leaves out or resolves.
    month : tuple of datetime.date or None
        Of a sub-daily series, the first and last day of the month being built:
        only its hours are wanted; None for every other series.
    state : dict
        A scratch the parser keeps across the files of one build (one month of a
        sub-daily series): PIG-PIB's rows of one point and hour read so far, so the
        later ``OBJECTID`` wins whatever capture holds it.
    """

    sources: Mapping[str, bytes] = MappingProxyType({})
    on_notice: NoticeHook | None = None
    month: tuple[date, date] | None = None
    state: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Answer:
    """
    One answer of a provider's server, as it came (P14, ECO-084).

    What a capture keeps of a request; `ProviderAdapter.capture` receives it.

    Attributes
    ----------
    url : str
        The address asked, without any credential.
    received_at : datetime
        When the answer arrived (UTC).
    status : int
        The HTTP status of the answer.
    content : bytes
        The body as it came.
    dataset : str or None
        Key of the dataset the answer belongs to; None when it belongs to none.
    """

    url: str
    received_at: datetime
    status: int
    content: bytes
    dataset: str | None = None


@dataclass(frozen=True)
class PolledSource:
    """
    A source of current data the hourly poll asks (``current poll``, P16, ADR-030 D9).

    Attributes
    ----------
    dataset : str
        Key of the capture dataset its answers belong to.
    url : str
        The address of its answer for every station, without any credential.
    interval : int
        How often the source changes, in seconds: the shortest spacing of two polls
        of it. The rate is a ceiling (P16): the deployment's timer runs at it or
        slower, and a poll asked sooner skips the source.
    headers : Mapping of str to str, optional
        Request headers the source needs (hydro.imgw.pl's backend refuses the
        default user agents of HTTP libraries).
    """

    dataset: str
    url: str
    interval: int
    headers: Mapping[str, str] = MappingProxyType({})


class ProviderAdapter(Protocol):
    """
    What Obserwator does with one data provider beyond its registry entry (ADR-029).

    One adapter per provider, in ``obserwator.providers.<country>.<acronym>``;
    `ProviderDescriptor.adapter` gives it. The attributes are the provider's facts the
    code acts on; the methods are its behaviour. Adapters subclass this protocol to
    inherit the defaults of the optional members: `current` (no live current data),
    `polled` (no source of the hourly poll), `harvested` and `watermarked` (no
    harvest), `live_source` (no live tail), `credential` (none), `capture` (the
    capture spool),
    `publication_default` (``private``), `server_name`, `groups`, `identifies`,
    `optional_sources`, `dataset_origin`, `station_origins`, `indexed`, `index_files`,
    `station_key`, `archive_station`, `download`, `folders`, `listed_station`,
    `listing`, `month_files`, `settled`, `held_period`, `station_file`,
    `optional_action`, `location_files`, `harvest_requests`, `live_tail`,
    `series_reads`, `hourly_points`, `series_read`, `published`, `publication_gaps`,
    `replaced`, `series_sources` and `capture_extra`.

    Attributes
    ----------
    provider_id : str
        ``ProviderDescriptor.id`` of the provider.
    origin : Origin
        Attribution origin of its archives and station lists (`obserwator.attribution`).
    origins : tuple of Origin
        Every origin of its data that an instance turning the provider ``off`` drops
        (ADR-025); PMAXTP's follows the instance's ``pmaxtp`` switch instead.
    border : str
        The packaged border (`obserwator._borders`) its station locations are checked
        against (ADR-018).
    server_name : str
        Its server's name in the texts of a failed request: the short name by default
        (IMGW-PIB's is ``IMGW``, as the texts of 3.0.0 named it).
    identifies : bool
        Whether its requests name the library (``User-Agent: obserwator/<version>``,
        spec 2026-10-18 §4.5) whatever the files asked.
    groups : frozenset of str
        Command groups that read its sources only (``current``, ``pmaxtp``): the
        catalog narrowed to another provider leaves them out.
    current : Mapping of str to callable
        Its live current data by source name, the sources of the GUI's view of the
        current measurements (``states``, ``hydro``, ``meteo``, ``synop``); empty
        without any.
    polled : tuple of PolledSource
        The sources of current data the hourly poll asks (P16, ADR-030 D9), each with
        the ceiling of its rate; empty without any.
    harvested : frozenset of str
        Capture datasets whose answers ``store sync`` asks for before it seals them:
        the night's harvest (ADR-030 D9, `harvest_requests`); empty without any.
    watermarked : frozenset of str
        Those of `harvested` asked by watermark: every row the source appended after
        the last one the raw root holds, whatever days they cover (PIG-PIB's
        ``mwp_auto``, ADR-035 W9), so a harvest of one takes no days and no stations;
        empty without any.
    live_source : str or None
        The capture dataset of the answers of `live_tail` (the GUI's live tail of a
        station's chart in „teraz”, O6), whose publication state
        (`obserwator.captures.publication`) the GUI honours before it asks; None
        without a live tail.
    station_sources : tuple of str
        Keys of its station-source datasets (ADR-015): the hydro and meteo station
        lists, then the hydro and meteo station metadata.
    optional_sources : tuple of str
        Keys of station sources its catalog reads when the raw root holds them
        (IMGW-PIB: hydro.imgw.pl's station details, ADR-021; ČHMÚ: the list and the
        current metadata of its groundwater objects, ADR-032; PIG-PIB: the night's
        capture of ``mwp_auto``, whose layer 0 lists the automatic points, ADR-035).
    kinds : tuple of str
        The station families it publishes, in `obserwator.datasets.KINDS` order: a
        live search of another family asks it nothing (``hydro`` and ``meteo`` by
        default; ČHMÚ also ``groundwater``).
    archive_suffixes : tuple of str
        File types it publishes as archives (lower case, with the dot).
    sidecar_station : bool
        Whether the sidecars of its archives name the station and the parameter
        (``request.station_code``, ``request.param``, ``extra.period.station_code``);
        IMGW-PIB's keep the layout of 3.0.0 without them.
    source_class : {"nmhs", "other"}
        Who operates its network (Nogat plan 2026-11-20, P11): ``nmhs``, a national
        meteorological and hydrological service of a WMO member (the default:
        IMGW-PIB, ČHMÚ), or ``other`` (an office, a company, a university, an
        operator's own network). A label of the operator, never a claim of WMO
        compliance.
    source_notice : Message or None
        P8's notice of a provider of the class ``other``: a catalog message saying
        that its data do not come from a national hydro-meteorological service and,
        where the provider says so, that they are unverified, in the provider's own
        words. Every product with its data carries it after the provider's lines
        (`obserwator.attribution`), and the GUI's station panel shows it beside the
        class badge; None for an ``nmhs`` provider (the default).
    served_by_default : bool
        Whether the servers serve the provider when ``[obserwator.instance.providers]``
        names no state for it, and a search that names no provider asks it: True by
        default; False for a provider the author keeps ``off`` until he decides what
        it serves (Gdańskie Wody, ADR-034), which is then used only where named.
    provider_file : ProviderFile or None
        The provider file of a provider fed by files (ADR-033): its data come from the
        files it names, imported by ``store import``, never from a server; None for a
        provider with a server (the default).
    """

    provider_id: str
    origin: Origin
    origins: tuple[Origin, ...]
    border: str
    identifies: bool = False
    groups: frozenset[str] = frozenset()
    current: Mapping[str, Callable[[], Any]] = MappingProxyType({})
    polled: tuple[PolledSource, ...] = ()
    harvested: frozenset[str] = frozenset()
    watermarked: frozenset[str] = frozenset()
    live_source: str | None = None
    station_sources: tuple[str, str, str, str]
    optional_sources: tuple[str, ...] = ()
    kinds: tuple[Kind, ...] = ("hydro", "meteo")
    archive_suffixes: tuple[str, ...]
    sidecar_station: bool
    source_class: Literal["nmhs", "other"] = "nmhs"
    source_notice: Message | None = None
    served_by_default: bool = True
    provider_file: ProviderFile | None = None

    @property
    def provider(self) -> ProviderDescriptor:
        """
        The provider's registry entry.

        Returns
        -------
        ProviderDescriptor
            The descriptor of `provider_id`.
        """
        from obserwator.datasets import get_provider

        return get_provider(self.provider_id)

    @property
    def server_name(self) -> str:
        """
        The provider's server in the texts of a failed request.

        Returns
        -------
        str
            The provider's short name by default.
        """
        return self.provider.short_name

    @property
    def credential(self) -> ProviderCredential | None:
        """
        The credential the provider's requests need (P3); None without one.

        The registry declares it (``ProviderDescriptor.credential``, step H3); a
        request of the adapter reads the key with ``config.provider_key`` and a
        rejected key is ``config.credential_error`` (``forbidden``).

        Returns
        -------
        ProviderCredential or None
            The registry's declaration; None for IMGW-PIB and ČHMÚ.
        """
        return self.provider.credential

    # --- attribution ---------------------------------------------------------------

    def dataset_origin(self, key: str) -> Origin:
        """
        The origin of the data of one of the provider's datasets or derived keys.

        Parameters
        ----------
        key : str
            Full key with the provider's prefix (a dataset, ``<prefix>.stations``).

        Returns
        -------
        Origin
            `origin` by default.
        """
        return self.origin

    def station_origins(
        self,
        properties: Mapping[str, object],
        *,
        location: bool = True,
        details: bool = True,
    ) -> tuple[Origin, ...]:
        """
        The origins of what a station of the provider's catalog holds beyond its data.

        The provider's origin and its border's are not included: these are the
        origins of a location or details taken from another of its services.

        Parameters
        ----------
        properties : Mapping of str to object
            The station's catalog properties.
        location : bool, optional
            Whether the station's location is shown or written.
        details : bool, optional
            Whether the station's details are shown or written.

        Returns
        -------
        tuple of Origin
            None by default.
        """
        return ()

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
        The files of an archive dataset of the provider, offline (`archive_files`).

        Parameters
        ----------
        descriptor : DatasetDescriptor
            A dataset of the provider with archives (not a station source).
        years, months, params, stations
            The selection of `obserwator.datasets.archive_files`.

        Returns
        -------
        tuple of ArchiveFile
            The candidates, in the provider's order.

        Raises
        ------
        ObserwatorValidationError
            If the selection does not fit the dataset.
        """
        ...

    def archive_from_path(
        self, descriptor: DatasetDescriptor, server_path: str, /
    ) -> ArchiveFile | None:
        """
        The archive of a server path of an archive dataset, offline.

        The reverse of `archive_files`: the descriptor equals the one it gives.

        Parameters
        ----------
        descriptor : DatasetDescriptor
            A dataset of the provider with archives (not a station source).
        server_path : str
            File path relative to the provider's ``base_url``.

        Returns
        -------
        ArchiveFile or None
            None when the path is no file of the dataset.
        """
        ...

    def indexed(self, descriptor: DatasetDescriptor, /) -> bool:
        """
        Whether a dataset's files are named only in the server's index (ADR-023).

        Parameters
        ----------
        descriptor : DatasetDescriptor
            A dataset of the provider.

        Returns
        -------
        bool
            False by default: `archive_files` names every file.
        """
        return False

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
        """
        The files the server's index names for a selection of an `indexed` dataset.

        Parameters
        ----------
        descriptor : DatasetDescriptor
            A dataset for which `indexed` is True.
        years, params, stations
            The selection of `obserwator.datasets.archive_files`.
        index : bool
            Whether the index may be read; without it the selection is only checked
            and no file is returned.
        timeout : float
            Request timeout in seconds.

        Returns
        -------
        tuple of ArchiveFile
            The files in the index's order.

        Raises
        ------
        ValueError
            For a dataset the server does not name (the default: every one).
        """
        raise ValueError(
            f"{descriptor.key}: {self.provider_id} names its files offline"
        )

    def station_key(self, code: str, /) -> str:
        """
        What the provider's per-station archives name a station by.

        Parameters
        ----------
        code : str
            A station code of the provider.

        Returns
        -------
        str
            The code itself by default.
        """
        return code

    def archive_station(self, archive: ArchiveFile, /) -> str | None:
        """
        The station one archive holds, as `station_key` gives it; None for many.

        Parameters
        ----------
        archive : ArchiveFile
            A file of one of the provider's datasets.

        Returns
        -------
        str or None
            ``archive.station_code`` by default.
        """
        return archive.station_code

    def download(
        self,
        archive: ArchiveFile,
        /,
        *,
        client: httpx.Client | None,
        cancel: Callable[[], bool] | None,
    ) -> DownloadResult:
        """
        GET one file for a store version (``store sync``).

        By default one GET of the file's address through ``client``, whose bytes
        must form a ZIP archive when the name says so.

        Parameters
        ----------
        archive : ArchiveFile
            A file of one of the provider's datasets.
        client : httpx.Client or None
            The client of the sync; None only for a file of the whole country.
        cancel : callable or None
            Polled between the requests of a file gathered from many answers.

        Returns
        -------
        DownloadResult
            The bytes with the HTTP signals of the answer.

        Raises
        ------
        ObserwatorConnectionError
            If the download fails (``source_unavailable``).
        ObserwatorDataError
            If the bytes are not what the file's name promises.
        ObserwatorCancelledError
            If ``cancel`` stops the requests.
        """
        from obserwator.fetch import _archive_response, _zipped

        assert client is not None
        return _archive_response(
            client,
            archive.url,
            source=self.provider.short_name,
            zipped=_zipped(archive),
        )

    # --- the store's checks ------------------------------------------------------

    def check_scope(self, descriptor: DatasetDescriptor, /) -> CheckScope:
        """
        How ``store check`` finds and checks the files of a measurement dataset.

        Parameters
        ----------
        descriptor : DatasetDescriptor
            A dataset of the provider with archives.

        Returns
        -------
        CheckScope
            ``country``, ``folders`` or ``stations``.
        """
        ...

    def folders(
        self, descriptor: DatasetDescriptor, years: Iterable[int], /
    ) -> list[str]:
        """
        Server directories of the selected years of a dataset in folders, by year.

        Parameters
        ----------
        descriptor : DatasetDescriptor
            A dataset whose `check_scope` is ``folders``.
        years : iterable of int
            The selected years.

        Returns
        -------
        list of str
            The folders, each once, in the order of the years.

        Raises
        ------
        ValueError
            For a dataset that is not in folders (the default: every one).
        """
        raise ValueError(
            f"{descriptor.key}: no dataset of {self.provider_id} in folders"
        )

    def listed_station(self, descriptor: DatasetDescriptor, name: str, /) -> str | None:
        """
        The station a name of a directory listing is a file of, by the dataset's grammar.

        Parameters
        ----------
        descriptor : DatasetDescriptor
            A dataset whose `check_scope` is ``stations``.
        name : str
            A file name of the listing.

        Returns
        -------
        str or None
            The station code; None for a name of no file of the dataset.

        Raises
        ------
        ValueError
            For a dataset without per-station listings (the default: every one).
        """
        raise ValueError(f"{descriptor.key}: no per-station listing of {name}")

    def listing(
        self, descriptor: DatasetDescriptor, directory: str, /, *, client: httpx.Client
    ) -> set[str] | None:
        """
        The file names the provider's listing publishes in a directory of a dataset.

        Parameters
        ----------
        descriptor : DatasetDescriptor
            A dataset whose `check_scope` is ``listing``.
        directory : str
            A directory of its files, relative to the dataset's base URL.
        client : httpx.Client
            The client of the check.

        Returns
        -------
        set of str or None
            The names; None when the directory is not published.

        Raises
        ------
        httpx.HTTPError
            If the listing cannot be read.
        ValueError
            For a dataset without such a listing (the default: every one).
        """
        raise ValueError(f"{descriptor.key}: no listing of {directory}")

    def month_files(
        self,
        descriptor: DatasetDescriptor,
        raw: Path,
        /,
        *,
        years: YearsArg,
        months: MonthsArg | None,
        stations: Iterable[str] | None,
        today: date,
    ) -> tuple[tuple[ArchiveFile, ...], tuple[PlanAction, ...]]:
        """
        The month files of a selection of a dataset checked by ``months``.

        Parameters
        ----------
        descriptor : DatasetDescriptor
            A dataset whose `check_scope` is ``months``.
        raw : pathlib.Path
            The raw root, whose station list names the stations and what they measure.
        years : YearsArg
            The selected years.
        months : MonthsArg or None
            The selected months of each year; None for every one.
        stations : iterable of str or None
            The selected stations; None for every one of the stored list.
        today : datetime.date
            Today (UTC): a month that has not begun is no file.

        Returns
        -------
        tuple
            The files, and the ``store sync`` actions of what cannot be named (a
            station the stored list does not hold).

        Raises
        ------
        ObserwatorStoreError
            ``not_found`` (``missing_source``) without the station list in the raw
            root.
        ValueError
            For a dataset not checked by months (the default: every one).
        """
        raise ValueError(f"{descriptor.key}: {self.provider_id} has no month files")

    def settled(self, archive: ArchiveFile, /) -> datetime:
        """
        When a version of a month file stops changing: a later download is current.

        Parameters
        ----------
        archive : ArchiveFile
            A file of `month_files`.

        Returns
        -------
        datetime.datetime
            The time (UTC) from which a stored version is final.

        Raises
        ------
        ValueError
            For a file not checked by months (the default: every one).
        """
        raise ValueError(f"{archive.dataset}: {self.provider_id} has no month files")

    def held_period(self, archive: ArchiveFile, /) -> tuple[date, date]:
        """
        The first and last UTC day whose hours a file of the provider may hold.

        A sub-daily series reads a file for each month of these days (ADR-031).

        Parameters
        ----------
        archive : ArchiveFile
            A dated file of one of the provider's datasets.

        Returns
        -------
        tuple of datetime.date
            Its period by default (Gdańskie Wody's provider days end at 05:00 UTC of
            the next day).
        """
        assert archive.period_start is not None and archive.period_end is not None
        return archive.period_start, archive.period_end

    def published(
        self, descriptor: DatasetDescriptor, /, *, client: httpx.Client
    ) -> tuple[ArchiveFile | None, tuple[Notice, ...]]:
        """
        The file a dataset checked by ``publication`` is published as now.

        Parameters
        ----------
        descriptor : DatasetDescriptor
            A dataset whose `check_scope` is ``publication``.
        client : httpx.Client
            The client of the check, for a request that names the file (PIG-PIB's
            readings: the first and last day of their rows, one query).

        Returns
        -------
        tuple of (ArchiveFile or None, tuple of Notice)
            The file, None when the service publishes nothing now, and the warnings
            of its naming (PIG-PIB's ``window_unexpected``: rows of more or less than
            one calendar month; ``no_readings``: an empty table).

        Raises
        ------
        ObserwatorConnectionError
            If the request naming the file fails (``source_unavailable``).
        ObserwatorDataError
            If the answer naming the file cannot be read.
        ValueError
            For a dataset not checked by ``publication`` (the default: every one).
        """
        raise ValueError(f"{descriptor.key}: {self.provider_id} names no publication")

    def publication_gaps(
        self, descriptor: DatasetDescriptor, raw: Path, /
    ) -> tuple[ArchiveFile, ...]:
        """
        The files of a dataset checked by ``publication`` that no capture can fill now.

        Parameters
        ----------
        descriptor : DatasetDescriptor
            A dataset whose `check_scope` is ``publication``.
        raw : pathlib.Path
            The raw root.

        Returns
        -------
        tuple of ArchiveFile
            None by default; PIG-PIB's readings: every calendar month between the
            first and the last stored that has no version (``not_captured``: the
            service holds the current month only, ADR-035 W5).
        """
        return ()

    def replaced(
        self, archive: ArchiveFile, previous: bytes, data: bytes, /
    ) -> tuple[Notice, ...]:
        """
        The notices of a new version that replaces the current version of its slot.

        Parameters
        ----------
        archive : ArchiveFile
            The file of both versions.
        previous : bytes
            The slot's current version before the new one.
        data : bytes
            The new version.

        Returns
        -------
        tuple of Notice
            None by default; PIG-PIB's ``month_republished`` with the readings
            changed, added and removed (ADR-035 W5).
        """
        return ()

    # --- station sources ---------------------------------------------------------

    def station_file(
        self, descriptor: DatasetDescriptor, name: str, /
    ) -> ArchiveFile | None:
        """
        A file of a station-source dataset by its name (ADR-015).

        Parameters
        ----------
        descriptor : DatasetDescriptor
            A station-source dataset of the provider.
        name : str
            A file name in the dataset's ``server_dir``.

        Returns
        -------
        ArchiveFile or None
            A file with a fixed name of the registry by default; None for another name.
        """
        from obserwator.datasets import _fixed_station_file

        return _fixed_station_file(descriptor, name)

    def parse_station_list(
        self, content: bytes, /, *, kind: Kind, filename: str
    ) -> list[StationListEntry]:
        """
        Stations of one of the provider's station lists.

        Parameters
        ----------
        content : bytes
            The list as published (or stored).
        kind : {"hydro", "meteo"}
            Its family.
        filename : str
            Its name or address, for errors.

        Returns
        -------
        list of StationListEntry
            One entry per station of the list, in its order.

        Raises
        ------
        ObserwatorDataError
            If the list cannot be read.
        """
        ...

    def live_urls(self, kind: Kind, /) -> list[str]:
        """
        The addresses a live station search of one family reads (its plans).

        Parameters
        ----------
        kind : {"hydro", "meteo"}
            The family.

        Returns
        -------
        list of str
            The addresses in request order; a file named by a listing as a pattern.
        """
        ...

    def live_stations(self, kind: Kind, /, *, timeout: float) -> list[StationListEntry]:
        """
        Stations of the provider's live station list of one family.

        Parameters
        ----------
        kind : {"hydro", "meteo"}
            The family.
        timeout : float
            Request timeout in seconds.

        Returns
        -------
        list of StationListEntry
            The stations with the coordinates the provider publishes.

        Raises
        ------
        ObserwatorConnectionError
            If the server cannot be reached or answers with an HTTP error.
        ObserwatorDataError
            If an answer cannot be read.
        """
        ...

    async def live_stations_async(
        self, kind: Kind, /, *, timeout: float
    ) -> list[StationListEntry]:
        """
        Async twin of `live_stations`.

        Parameters
        ----------
        kind : {"hydro", "meteo"}
            The family.
        timeout : float
            Request timeout in seconds.

        Returns
        -------
        list of StationListEntry
            As `live_stations`.
        """
        ...

    # --- the station catalog -----------------------------------------------------

    def catalog_sources(self, raw: Path, /) -> list[tuple[str, ArchiveFile | None]]:
        """
        The station sources of the provider's catalog in build order, by source name.

        Parameters
        ----------
        raw : pathlib.Path
            The raw root (a source named by its stored versions is looked up there).

        Returns
        -------
        list of (str, ArchiveFile or None)
            Each source's name and file; None for a source of which none is stored.
        """
        ...

    def source_datasets(self) -> list[str]:
        """
        Dataset of each source of `catalog_sources`, in the same order.

        Returns
        -------
        list of str
            Dataset keys, one per source.
        """
        ...

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
        Status and detail of an optional source in a ``store catalog`` plan.

        Parameters
        ----------
        key : str
            One of `optional_sources`.
        raw : pathlib.Path
            The raw root.
        recorded : Mapping
            SHA-256 of each source the current catalog was built from, by source name.
        catalog : bool
            Whether the data root holds a catalog of the provider.
        cancelled : bool
            Whether the check was cancelled.

        Returns
        -------
        SourceAction
            The status and the detail of the action.

        Raises
        ------
        ValueError
            For a key that is none of `optional_sources` (the default: every one).
        """
        raise ValueError(f"{key} is no optional source of {self.provider_id}")

    def location_files(self) -> list[tuple[str, bytes | None, Path]]:
        """
        Location files of the provider's catalog outside any dataset, but the user's.

        Returns
        -------
        list of (str, bytes or None, pathlib.Path)
            Source name, content (None when the file is absent) and path of each;
            none by default.
        """
        return []

    def build_catalog(self, build: CatalogBuild, /) -> CatalogReport:
        """
        Build the provider's catalog from its stored sources (`build_catalog`).

        Parameters
        ----------
        build : CatalogBuild
            The roots, the user file and the hooks of the build, with its
            publication.

        Returns
        -------
        CatalogReport
            The report of `obserwator.store.build_catalog`.
        """
        ...

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
        context: SeriesContext | None = None,
    ) -> Iterator[NormalizedRecord]:
        """
        Normalized records of one stored file of the provider's datasets.

        Parameters
        ----------
        archive : ArchiveFile
            The file (its ``dataset`` selects the parser).
        data : bytes
            The file's content.
        carry, stations, skipped_months
            As `obserwator._parsing.normalize_in_sequence`.
        context : SeriesContext or None, optional
            What the series build gives beside the file (its `series_sources`); None
            outside a build.

        Returns
        -------
        Iterator of NormalizedRecord
            The records in file order.

        Raises
        ------
        ObserwatorValidationError
            If the dataset has no parser (``no_parser_archive``).
        ObserwatorDataError
            If the file cannot be parsed.
        """
        ...

    def series_reads(self, series: DatasetDescriptor, archive: ArchiveFile, /) -> bool:
        """
        Whether a series built from ``inputs`` reads one of their files (ADR-034).

        Parameters
        ----------
        series : DatasetDescriptor
            A series dataset with ``inputs``.
        archive : ArchiveFile
            A stored file of one of its inputs.

        Returns
        -------
        bool
            True by default (every file); Gdańskie Wody's month file only for a series
            holding the variable of its quantity.
        """
        return True

    def series_sources(self, series: DatasetDescriptor, /) -> tuple[str, ...]:
        """
        Station sources whose current versions a series of the provider reads (ADR-035).

        A series build reads them beside its inputs and hands them to the parsers
        (`SeriesContext.sources`), and each is an input of every version it builds
        (``source_files``), so a new version of one rebuilds the series.

        Parameters
        ----------
        series : DatasetDescriptor
            A series dataset of the provider.

        Returns
        -------
        tuple of str
            None by default; PIG-PIB's points (``pl.pig.groundwater_stations``) for
            its two series, whose ground elevation gives ``H_asl``.
        """
        return ()

    def hourly_points(
        self,
        archive: ArchiveFile,
        data: bytes,
        /,
        *,
        context: SeriesContext | None = None,
    ) -> Iterator[tuple[str, str, list[tuple[object, object]]]]:
        """
        The hours of a stored input file of a sub-daily series (ADR-031, ADR-034).

        Parameters
        ----------
        archive : ArchiveFile
            A file of an input dataset: no capture of IMGW-PIB or ČHMÚ (the store
            reads those itself), or a capture of a provider that reads its own
            (PIG-PIB's ``mwp_auto``, ADR-035).
        data : bytes
            Its content.
        context : SeriesContext or None, optional
            The build's sources, the month built and the scratch kept across its
            files; None outside a build.

        Returns
        -------
        Iterator of (str, str, list)
            Per station and variable, the ``(time, value)`` points (ISO 8601 times
            with a zone).

        Raises
        ------
        ValueError
            For a dataset the adapter reads no hours of (the default: every one; the
            store reads IMGW-PIB's and ČHMÚ's inputs itself).
        """
        raise ValueError(f"{archive.dataset}: {self.provider_id} gives no hours")

    def series_read(self, context: SeriesContext, label: str, /) -> None:
        """
        Tell what a build's parsers left out or resolved, once its files are read.

        A series build reads the files of one build with one context (ADR-035): every
        input of a series, or the inputs of one month of a sub-daily series; then it
        calls this hook, so the parsers' findings kept in ``context.state`` reach
        ``context.on_notice`` once per build, not once per file.

        Parameters
        ----------
        context : SeriesContext
            The context the build's files were read with.
        label : str
            What was read: a month ``YYYY-MM`` of a sub-daily series, else the
            series' dataset key.

        Returns
        -------
        None
            Nothing by default. PIG-PIB's adapter tells the readings of points its
            points lack (``station_unknown``) and, of a month of its hourly series, the
            hours whose rows differ, the summer-time hours left unresolved and the rows
            after their answers (``hour_revised``, ``hour_unresolved``,
            ``hour_future``).
        """
        return None

    # --- captures ------------------------------------------------------------------

    def capture(self, answer: Answer, /) -> Path | None:
        """
        Keep an answer of the provider's servers as a capture (P14, ECO-084).

        The hook of the captures: every answer a request path of the provider
        receives goes here (through `obserwator.captures.keep`, which turns a failure
        into one warning record), so no provider can skip it. By default an answer
        of a capture dataset is written to the capture spool
        (``<state_dir>/obserwator/captures/<dataset>/<YYYY-MM-DD>/``, one file per
        answer, ADR-030 D7), which ``store sync`` seals into one version a UTC day;
        an answer of another dataset, or of none, is not kept here (an archive
        download keeps its own version).

        Parameters
        ----------
        answer : Answer
            The answer as it came.

        Returns
        -------
        pathlib.Path or None
            The spool file of the answer; None when its dataset is no capture
            dataset.

        Raises
        ------
        OSError
            If the spool cannot be written.
        """
        from obserwator.captures import write_spool

        return write_spool(answer)

    def capture_extra(
        self, key: str, answers: Sequence[Spooled], /
    ) -> Mapping[str, object]:
        """
        What the provider adds to ``extra.capture`` of a capture version's sidecar.

        Read again from the sidecar alone, without the capture: the ``period`` (the
        first and last UTC day, ISO, whose hours the answers hold) lets a sub-daily
        series read a capture for the months of those days instead of the 43 days
        before its day (ADR-031 D3), and names the years of the version's lines
        (PIG-PIB's W); a harvest by watermark keeps its ``watermark`` (the last
        ``OBJECTID`` of the pages it appended) and the ``count`` of rows it was told.

        Parameters
        ----------
        key : str
            A capture dataset of the provider.
        answers : sequence of Spooled
            The answers of the version.

        Returns
        -------
        Mapping of str to object
            Empty by default (the days follow from the capture's day, so the
            sidecars of IMGW-PIB and ČHMÚ keep their bytes); PIG-PIB's ``mwp_auto``:
            ``period``, ``watermark`` and ``count`` where its answers give them
            (ADR-035 W9).
        """
        return {}

    def publication_default(self, key: str, /) -> Literal["public", "private"]:
        """
        Whether a source of the provider is served when the operator says nothing (P15).

        The default follows the source's terms as the provider's intake records them
        (ADR-030 D5); ``[obserwator.capture]`` of ``nogat.toml`` overrides it.

        Parameters
        ----------
        key : str
            A dataset of the provider whose tier is not ``verified``.

        Returns
        -------
        {"public", "private"}
            ``private`` by default: a source whose terms nobody recorded is stored,
            never served.
        """
        return "private"

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
        raw: Path | None = None,
    ) -> tuple[PacedRequest, ...]:
        """
        The requests of the night's harvest of a capture dataset (ADR-030 D9).

        The adapter reads the station list it needs through ``session`` (paced, its
        answer kept in the spool when it is a capture source's) and returns one
        request per station and source of the closed UTC days ``start`` to ``end``,
        those of one station together; `obserwator.captures.harvest` asks them and the
        spool keeps every answer.

        Parameters
        ----------
        descriptor : DatasetDescriptor
            One of `harvested`.
        start, end : datetime.date
            The first and last UTC day to cover, closed days.
        stations : sequence of str or None
            Station codes to ask (each for every source); None for every station of
            the provider's list.
        session : PacedSession
            The paced requests of the run.
        on_notice : NoticeHook or None
            Receives the warnings of the planning (a station list read only in part).
        raw : pathlib.Path or None, optional
            The raw root the run seals into: of a harvest by watermark (PIG-PIB's
            ``mwp_auto``, ADR-035 W9) where the last ``OBJECTID`` captured comes from;
            None outside a ``store sync``.

        Returns
        -------
        tuple of PacedRequest
            The requests in order.

        Raises
        ------
        ObserwatorConnectionError
            If the station list cannot be read (``source_unavailable``).
        ObserwatorDataError
            If the station list cannot be parsed.
        ObserwatorCancelledError
            If the session's ``cancel`` returned True.
        ValueError
            For a dataset it does not harvest (the default: every one).
        """
        raise ValueError(f"{descriptor.key}: {self.provider_id} harvests no answers")

    def live_tail(
        self, code: str, /, *, hours: int, timeout: float
    ) -> tuple[Answer, ...]:
        """
        The operational answers of one station asked live (the GUI's live tail, O6).

        Every answer belongs to `live_source` and goes to the capture spool as the
        library's requests keep them (P14); the answers are returned whatever their
        status. `obserwator.store.subdaily.tail_hours` reads their full hours.

        Parameters
        ----------
        code : str
            A station code of the provider.
        hours : int
            How many hours back the answers should reach, where the source takes it.
        timeout : float
            Timeout of each request in seconds.

        Returns
        -------
        tuple of Answer
            One per request, in order; none by default (no live tail).

        Raises
        ------
        ObserwatorConnectionError
            If a request gets no answer (``source_unavailable``).
        """
        return ()
