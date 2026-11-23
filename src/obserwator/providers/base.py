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
from dataclasses import dataclass
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
    from obserwator.store.types import CatalogReport, NoticeHook

__all__ = [
    "Answer",
    "CheckScope",
    "Kind",
    "PolledSource",
    "ProviderAdapter",
    "SourceAction",
]

CheckScope = Literal["country", "folders", "stations", "listing"]
"""
How ``store check`` finds and checks the files of a measurement dataset.

``country``: files enumerated offline (`ProviderAdapter.archive_files`), checked by
HEAD; ``folders``: files named in the index of each folder of the selected years
(`ProviderAdapter.folders`), checked by HEAD; ``stations``: one directory listing per
directory of the station files (`ProviderAdapter.listed_station`), which is their
signal; ``listing``: files enumerated offline and published when the provider's
listing of their directory names them (`ProviderAdapter.listing`), without any HTTP
signal: a stored file is current, as published once (IMGW-PIB's telemetry).
"""

SourceAction = tuple[Literal["current", "newer", "missing", "unverifiable"], "Message"]
"""Status and detail of an optional catalog source in a ``store catalog`` plan."""


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
    `polled` (no source of the hourly poll), `harvested` (no harvest), `live_source`
    (no live tail), `credential` (none), `capture` (the capture spool),
    `publication_default` (``private``), `server_name`, `groups`, `identifies`,
    `optional_sources`, `dataset_origin`, `station_origins`, `indexed`, `index_files`,
    `station_key`, `archive_station`, `download`, `folders`, `listed_station`,
    `listing`, `station_file`, `optional_action`, `location_files`, `harvest_requests`
    and `live_tail`.

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
        current metadata of its groundwater objects, ADR-032).
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
    live_source: str | None = None
    station_sources: tuple[str, str, str, str]
    optional_sources: tuple[str, ...] = ()
    kinds: tuple[Kind, ...] = ("hydro", "meteo")
    archive_suffixes: tuple[str, ...]
    sidecar_station: bool
    source_class: Literal["nmhs", "other"] = "nmhs"
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
