"""Freshness check (listing + HEAD) and plan-driven synchronization of archives."""

from __future__ import annotations

import os
import re
import sys
from collections import defaultdict
from collections.abc import Iterable, Iterator, Mapping
from contextlib import contextmanager, nullcontext
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path, PurePosixPath
from typing import Literal, NamedTuple, cast
from urllib.parse import unquote, urlsplit

import httpx

from obserwator import _environment as environment
from obserwator import captures as _captures
from obserwator import fetch as _fetch
from obserwator._parsing.chmu import ListingEntry, parse_listing
from obserwator.captures import HARVEST_DAYS, _harvest, _harvested
from obserwator.config import Settings
from obserwator.datasets import (
    CAPTURE_SCOPE,
    ArchiveFile,
    DatasetDescriptor,
    MonthsArg,
    YearsArg,
    _archive_from_path,
    _minimum_year,
    _parse_stations,
    _station_file,
    _station_files,
    archive_files,
    get_dataset,
    get_provider,
    keeps_archives,
    parse_months,
    parse_years,
)
from obserwator.datasets import datasets as registered_datasets
from obserwator.exceptions import (
    ErrorCode,
    ObserwatorCancelledError,
    ObserwatorDataError,
    ObserwatorError,
    ObserwatorStoreConflictError,
    ObserwatorValidationError,
    io_error,
)
from obserwator.fetch import (
    _IDENTIFY,
    DEFAULT_TIMEOUT,
    DOWNLOAD_TIMEOUT,
    UNPUBLISHED,
    DownloadResult,
    _archive_slot,
    _download_plain,
    pace_deadline,
)
from obserwator.messages import Message, message, reason
from obserwator.messages.sync import MESSAGES
from obserwator.output import resolve_target
from obserwator.providers.base import CheckScope
from obserwator.store.captures import check_captures, seal_item
from obserwator.store.reader import _Reference, _reference_signal
from obserwator.store.series import (
    _current_version,
    _Version,
)
from obserwator.store.types import (
    Cancel,
    DownloadItem,
    HarvestReport,
    Notice,
    NoticeHook,
    OperationResult,
    PathArg,
    PlanAction,
    PlanItem,
    Progress,
    ProgressHook,
    StoreHandle,
    StorePlan,
    SyncReport,
)
from obserwator.store.writer import (
    lenient_store,
    refuse_root,
    root_conflict_plan,
    version_file,
    write_archive,
)

if sys.platform != "win32":
    import fcntl

CANCELLED = message("common.cancelled")
NO_SIGNAL = message("sync.no_comparable_header")
NO_LISTING_SIGNAL = message("sync.no_comparable_signal")
LOCK_FILE = "store-sync.lock"
"""The lock of capture sealing runs, in ``<state_dir>/obserwator`` (ADR-030 D10)."""
LOCK_WAIT = 600.0
"""How long a sealing ``store sync`` waits for another's lock, in seconds (D10)."""

_HREF = re.compile(r"""href\s*=\s*["']([^"'#?]+)""", re.IGNORECASE)
_DONE = {"new", "relabeled", "unchanged"}
_VersionStatus = Literal["new", "unchanged", "relabeled"]
_SYNC = "store sync"
# How often a waiting ``store sync`` tries the lock again, in seconds.
_LOCK_POLL = 1.0
Status = Literal["current", "newer", "missing", "unverifiable", "check_failed"]


@dataclass(frozen=True)
class _Signal:
    etag: str | None
    last_modified: str | None
    content_length: int | None


def _listing(client: httpx.Client, url: str) -> set[str] | None:
    """File names published in a server directory; ``None`` when the directory is absent."""
    response = client.get(url)
    if response.status_code in (404, 410):
        return None
    response.raise_for_status()
    return {
        PurePosixPath(unquote(urlsplit(href).path)).name
        for href in _HREF.findall(response.text)
    }


def _head(client: httpx.Client, archive: ArchiveFile) -> _Signal | None:
    """Remote HTTP signal of an archive; ``None`` when the file is not published."""
    response = client.head(archive.url)
    if response.status_code in (404, 410):
        return None
    response.raise_for_status()
    length = response.headers.get("Content-Length")
    return _Signal(
        response.headers.get("ETag"),
        response.headers.get("Last-Modified"),
        int(length) if length is not None and length.isdigit() else None,
    )


# Start of the English text of each server error of a check, before its first
# placeholder. A saved plan keeps only the text, so ``_failure_code`` tells a
# server error from any other check_failed reason (an unreadable listing or
# local version, a data error) by these prefixes.
_HTTP_ERRORS = tuple(
    MESSAGES[name].en.partition("{")[0]
    for name in ("timeout_waiting_for_server", "http_error", "connection_error")
)


def _http_error(exc: Exception, *, source: str) -> Message:
    if isinstance(exc, httpx.TimeoutException):
        return message(
            "sync.timeout_waiting_for_server", source=source, reason=reason(exc)
        )
    if isinstance(exc, httpx.HTTPStatusError):
        return message(
            "sync.http_error", status=exc.response.status_code, url=exc.request.url
        )
    return message("sync.connection_error", source=source, reason=reason(exc))


def _failure_code(error: str | None) -> ErrorCode:
    """Error code of a ``check_failed`` reason: provider server or data."""
    return (
        "source_unavailable"
        if error is not None and error.startswith(_HTTP_ERRORS)
        else "data_error"
    )


def _source(archive: ArchiveFile) -> str:
    """Provider's server name in the messages about an archive's server."""
    return get_provider(get_dataset(archive.dataset).provider).adapter.server_name


def _compare(local: dict[str, object], remote: _Signal) -> Status:
    """Compare every header present on both sides; Content-Length never decides."""
    pairs = [
        (local.get("etag"), remote.etag),
        (local.get("last_modified"), remote.last_modified),
    ]
    comparable = [
        (mine, theirs)
        for mine, theirs in pairs
        if mine is not None and theirs is not None
    ]
    if not comparable:
        return "unverifiable"
    return "current" if all(mine == theirs for mine, theirs in comparable) else "newer"


def _item(
    archive: ArchiveFile,
    status: Status,
    *,
    local: _Version | None = None,
    signal: _Signal | None = None,
    error: str | None = None,
) -> PlanItem:
    return PlanItem(
        archive=archive,
        status=status,
        local_path=Path(local.relative) if local is not None else None,
        local_sha256=local.sha256 if local is not None else None,
        remote_etag=signal.etag if signal else None,
        remote_last_modified=signal.last_modified if signal else None,
        content_length=signal.content_length if signal else None,
        error=error,
    )


def _minute(last_modified: str | None) -> datetime | None:
    """UTC time of a ``Last-Modified`` value truncated to the minute, or None."""
    if not last_modified:
        return None
    try:
        moment = parsedate_to_datetime(last_modified)
    except (TypeError, ValueError, OverflowError):
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC).replace(second=0, microsecond=0)


def _listed_at(moment: datetime) -> str:
    """Listing time in the plan form ``YYYY-MM-DDTHH:MMZ``."""
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%MZ")


@dataclass(frozen=True)
class _Listing:
    """Files of a listed server directory by name, or why the listing is unusable."""

    entries: Mapping[str, ListingEntry]
    error: str | None = None


@dataclass(frozen=True)
class _Target:
    """
    Per-station file to check against its slot.

    ``entry`` is the listing row of a published file; without it ``error``
    names the unusable listing of its directory, and neither of them means
    that the source does not publish the file.
    """

    archive: ArchiveFile
    entry: ListingEntry | None = None
    error: str | None = None


def _read_listing(client: httpx.Client, url: str, *, source: str) -> _Listing:
    """GET and parse an nginx listing; any failure is kept as the listing's error."""
    try:
        response = client.get(url)
    except httpx.HTTPError as exc:
        return _Listing({}, _http_error(exc, source=source))
    if response.status_code != 200:
        return _Listing(
            {}, message("sync.http_error", status=response.status_code, url=url)
        )
    try:
        entries = parse_listing(response.content, url=url)
    except ObserwatorDataError as exc:
        return _Listing({}, reason(exc))
    return _Listing({entry.name: entry for entry in entries})


def _directories(
    descriptor: DatasetDescriptor, candidates: tuple[ArchiveFile, ...] | None
) -> list[str]:
    """Server directories whose listings show the requested files of a dataset."""
    assert descriptor.server_dir is not None
    if candidates is None:
        return [descriptor.server_dir]
    return sorted(
        {PurePosixPath(archive.server_path).parent.as_posix() for archive in candidates}
    )


def _no_files(descriptor: DatasetDescriptor, code: str) -> PlanAction:
    return PlanAction(
        _SYNC,
        "unverifiable",
        message("sync.station_no_files", code=code, key=descriptor.key),
    )


def _station_targets(
    descriptor: DatasetDescriptor,
    codes: tuple[str, ...],
    candidates: tuple[ArchiveFile, ...] | None,
    listings: Mapping[str, _Listing],
) -> tuple[list[_Target], list[PlanAction]]:
    """
    Requested files of each station by the listings, or one action per station.

    A requested file absent from a readable listing while the station has
    other files of the dataset there is unpublished; a station without any
    file of the dataset gets one ``unverifiable`` action instead of items
    (spec 2026-10-18 §4.2, steps 5-6). A listing without any name of the
    dataset's grammar is unreadable (a changed server layout, spec §15).
    Candidates in an unreadable listing keep its error; without candidates
    (years taken from the listing) such a station gets a ``check_failed``
    action.

    Parameters
    ----------
    descriptor : DatasetDescriptor
        Per-station dataset.
    codes : tuple of str
        Requested station codes, sorted.
    candidates : tuple of ArchiveFile or None
        Offline candidates of the request, or None to take every listed file
        of the stations.
    listings : Mapping of str to _Listing
        Listing of every directory of `_directories`.

    Returns
    -------
    tuple of (list of _Target, list of PlanAction)
        Files to check (unsorted) and the station actions.
    """
    adapter = get_provider(descriptor.provider).adapter
    provider = get_provider(descriptor.provider)
    wanted = set(codes)
    listed: dict[str, dict[str, tuple[ArchiveFile, ListingEntry]]] = defaultdict(dict)
    failures: dict[str, str] = {}
    for directory in _directories(descriptor, candidates):
        listing = listings[directory]
        if listing.error is not None:
            failures[directory] = listing.error
            continue
        known = False
        for name, entry in listing.entries.items():
            station = adapter.listed_station(descriptor, name)
            if station is None:
                continue
            known = True
            if station not in wanted:
                continue
            archive = _archive_from_path(descriptor.key, f"{directory}/{name}")
            if archive is not None:
                listed[station][archive.server_path] = (archive, entry)
        if not known:
            failures[directory] = message(
                "sync.listing_without_dataset_files",
                base_url=provider.base_url,
                directory=directory,
                key=descriptor.key,
            )
    requested: dict[str, list[ArchiveFile]] = defaultdict(list)
    for archive in candidates or ():
        requested[archive.station_code or ""].append(archive)
    targets: list[_Target] = []
    actions: list[PlanAction] = []
    for code in codes:
        files = listed.get(code, {})
        if candidates is None:
            if failures:
                actions.extend(
                    PlanAction(
                        _SYNC,
                        "check_failed",
                        message("sync.station_error", code=code, error=error),
                    )
                    for error in failures.values()
                )
            elif files:
                targets.extend(
                    _Target(archive, entry) for archive, entry in files.values()
                )
            else:
                actions.append(_no_files(descriptor, code))
            continue
        if not files and not failures:
            actions.append(_no_files(descriptor, code))
            continue
        for archive in requested[code]:
            directory = PurePosixPath(archive.server_path).parent.as_posix()
            if directory in failures:
                targets.append(_Target(archive, error=failures[directory]))
            elif archive.server_path in files:
                targets.append(_Target(archive, files[archive.server_path][1]))
            else:
                targets.append(_Target(archive))
    return targets, actions


def _listed_item(
    root: Path,
    archive: ArchiveFile,
    status: Status,
    *,
    reference: _Reference | None = None,
    entry: ListingEntry | None = None,
    error: str | None = None,
) -> PlanItem:
    """Plan item of a per-station file: listing signal and the slot's reference."""
    version = reference.version.version if reference is not None else None
    meta = reference.version.meta if reference is not None else None
    observation = reference.observation if reference is not None else None
    return PlanItem(
        archive=archive,
        status=status,
        local_path=version.relative_to(root) if version is not None else None,
        local_sha256=meta.sha256 if meta is not None else None,
        remote_etag=None,
        remote_last_modified=None,
        content_length=entry.size if entry is not None else None,
        error=error,
        station_code=archive.station_code,
        signal="listing",
        remote_listed_at=_listed_at(entry.modified) if entry is not None else None,
        local_observation=observation.relative_to(root)
        if observation is not None
        else None,
    )


def _check_target(root: Path, target: _Target) -> PlanItem:
    """
    Status of a per-station file by its listing row and the slot's reference signal.

    The reference signal is the newest observation of the current version, or
    the version's own ``extra.http`` and size (ADR-003 D18). The file is
    ``current`` when the reference ``Last-Modified`` truncated to the minute
    and the reference size equal the listing's time and size.
    """
    archive = target.archive
    try:
        reference = _reference_signal(root, slot=_archive_slot(archive))
    except ObserwatorDataError as exc:
        return _listed_item(root, archive, "check_failed", error=reason(exc))
    if target.error is not None:
        return _listed_item(
            root, archive, "check_failed", reference=reference, error=target.error
        )
    entry = target.entry
    if entry is None:
        return _listed_item(
            root, archive, "unverifiable", reference=reference, error=UNPUBLISHED
        )
    if reference is None:
        return _listed_item(root, archive, "missing", entry=entry)
    published = _minute(reference.last_modified)
    if published is None:
        return _listed_item(
            root,
            archive,
            "unverifiable",
            reference=reference,
            entry=entry,
            error=NO_LISTING_SIGNAL,
        )
    same = (published, reference.size_bytes) == (entry.modified, entry.size)
    return _listed_item(
        root,
        archive,
        "current" if same else "newer",
        reference=reference,
        entry=entry,
    )


def _announce(
    item: PlanItem,
    index: int,
    total: int,
    *,
    on_progress: ProgressHook | None,
    on_notice: NoticeHook | None,
) -> None:
    """Notice of an unverifiable or failed item and the progress after it."""
    if item.status == "unverifiable" and on_notice is not None:
        on_notice(
            Notice(
                "warning",
                "source_unverifiable",
                f"{item.archive.server_path}: {item.error}",
            )
        )
    elif item.status == "check_failed" and on_notice is not None:
        on_notice(
            Notice(
                "warning",
                "archive_failed",
                f"{item.archive.server_path}: {item.error}",
            )
        )
    if on_progress is not None:
        on_progress(
            Progress(index, total, "archive", item.status, item.archive.server_path)
        )


def _position(
    order: Mapping[str, int], archive: ArchiveFile
) -> tuple[int, str, int, str, str]:
    """Plan order of per-station files: dataset, station, year, param, path."""
    return (
        order[archive.dataset],
        archive.station_code or "",
        archive.year or 0,
        archive.param or "",
        archive.server_path,
    )


def _check_listed(
    client: httpx.Client,
    root: Path,
    descriptors: list[DatasetDescriptor],
    codes: tuple[str, ...],
    candidates: Mapping[str, tuple[ArchiveFile, ...] | None],
    *,
    on_progress: ProgressHook | None,
    on_notice: NoticeHook | None,
    cancel: Cancel | None,
) -> tuple[list[PlanItem], list[PlanAction], bool]:
    """
    Check per-station files by one listing GET per directory, without HEAD.

    Parameters
    ----------
    client : httpx.Client
        Client of the check.
    root : Path
        Store root.
    descriptors : list of DatasetDescriptor
        Per-station datasets of the request.
    codes : tuple of str
        Requested station codes, sorted.
    candidates : Mapping of str to tuple of ArchiveFile or None
        Offline candidates of each dataset; None takes the listed years.
    on_progress, on_notice : hook or None
        Hooks of `check_store`.
    cancel : Cancel or None
        Polled before every listing and every file.

    Returns
    -------
    tuple of (list of PlanItem, list of PlanAction, bool)
        Items in plan order, station actions and the cancellation flag.
    """
    order = {item.key: index for index, item in enumerate(registered_datasets())}
    ordered = sorted(descriptors, key=lambda descriptor: order[descriptor.key])
    listings: dict[str, _Listing] = {}
    for descriptor in ordered:
        provider = get_provider(descriptor.provider)
        for directory in _directories(descriptor, candidates[descriptor.key]):
            if cancel is not None and cancel():
                known = sorted(
                    (
                        archive
                        for item in ordered
                        for archive in candidates[item.key] or ()
                    ),
                    key=lambda archive: _position(order, archive),
                )
                return (
                    [
                        _listed_item(root, archive, "unverifiable", error=CANCELLED)
                        for archive in known
                    ],
                    [],
                    True,
                )
            listings[directory] = _read_listing(
                client,
                f"{provider.base_url}{directory}/",
                source=provider.short_name,
            )
    targets: list[_Target] = []
    actions: list[PlanAction] = []
    for descriptor in ordered:
        found, stations = _station_targets(
            descriptor, codes, candidates[descriptor.key], listings
        )
        targets.extend(found)
        actions.extend(stations)
    targets.sort(key=lambda target: _position(order, target.archive))
    if on_notice is not None:
        for action in actions:
            on_notice(
                Notice("warning", "source_unverifiable", action.detail)
                if action.status == "unverifiable"
                else Notice("warning", "archive_failed", action.detail)
            )
    items: list[PlanItem] = []
    cancelled = False
    for index, target in enumerate(targets, start=1):
        if not cancelled and cancel is not None and cancel():
            cancelled = True
        if cancelled:
            items.append(
                _listed_item(root, target.archive, "unverifiable", error=CANCELLED)
            )
            continue
        items.append(_check_target(root, target))
        _announce(
            items[-1],
            index,
            len(targets),
            on_progress=on_progress,
            on_notice=on_notice,
        )
    return items, actions, cancelled


def _descriptors(datasets: Iterable[str]) -> list[DatasetDescriptor]:
    """
    Measurement datasets of the request, without repetitions.

    The series datasets and the stored files no series reads (``keeps_archives``:
    ČHMÚ's groundwater ``recent`` and ``characteristic``, ADR-032).
    """
    allowed = [item.key for item in registered_datasets() if keeps_archives(item)]
    found: dict[str, DatasetDescriptor] = {}
    for dataset in dict.fromkeys(datasets):
        descriptor = get_dataset(dataset)
        if descriptor.key not in allowed:
            raise ObserwatorValidationError(
                message(
                    "sync.dataset_keeps_no_archives",
                    dataset=dataset,
                    allowed=", ".join(allowed),
                ),
                details={"option": "datasets", "value": dataset, "allowed": allowed},
            )
        found.setdefault(descriptor.key, descriptor)
    if not found:
        raise ObserwatorValidationError(
            message("sync.choose_least_one_dataset"), details={"option": "datasets"}
        )
    return list(found.values())


def _source_descriptors(datasets: Iterable[str]) -> list[DatasetDescriptor] | None:
    """
    The station-source datasets of a request, or None when it names none of them.

    Station sources are the station lists and the station metadata of the
    catalogs (``time_unit`` ``station_list``, ADR-015); a request holds either
    only them or only measurement datasets.

    Raises
    ------
    ObserwatorValidationError
        If ``datasets`` is a string, names an unknown dataset, or mixes station
        sources with measurement datasets.
    """
    if isinstance(datasets, str):
        raise ObserwatorValidationError(
            message("sync.parameter_datasets_must_list_dataset"),
            details={"option": "datasets", "value": datasets},
        )
    named = [get_dataset(dataset) for dataset in dict.fromkeys(datasets)]
    sources = {d.key: d for d in named if d.time_unit == "station_list"}
    if not sources:
        return None
    if len(sources) != len({d.key for d in named}):
        raise ObserwatorValidationError(
            message("sync.station_sources_alone"),
            details={"option": "datasets", "value": [d.key for d in named]},
        )
    return list(sources.values())


def _capture_descriptors(datasets: Iterable[str]) -> list[DatasetDescriptor] | None:
    """
    The capture datasets of a request, or None when it names none of them.

    A capture dataset (``archive_scope`` ``country_day``, ADR-030 D3) is sealed from
    the spool, not downloaded; a request holds either only capture datasets or none.

    Raises
    ------
    ObserwatorValidationError
        If ``datasets`` is a string, names an unknown dataset, or mixes capture
        datasets with others.
    """
    if isinstance(datasets, str):
        raise ObserwatorValidationError(
            message("sync.parameter_datasets_must_list_dataset"),
            details={"option": "datasets", "value": datasets},
        )
    named = [get_dataset(dataset) for dataset in dict.fromkeys(datasets)]
    captures = {d.key: d for d in named if d.archive_scope == CAPTURE_SCOPE}
    if not captures:
        return None
    if len(captures) != len({d.key for d in named}):
        raise ObserwatorValidationError(
            message("sync.captures_alone"),
            details={"option": "datasets", "value": [d.key for d in named]},
        )
    return list(captures.values())


def _harvest_codes(
    captures: list[DatasetDescriptor],
    years: YearsArg | None,
    months: MonthsArg | None,
    stations: Iterable[str] | None,
) -> tuple[str, ...]:
    """
    The station codes of a harvest (``pace_until``, ADR-030 D9); none for every station.

    Raises
    ------
    ObserwatorValidationError
        If the call names more than one dataset or one no adapter harvests
        (``details.reason`` ``not_harvested``), gives ``years`` or ``months``
        (``captures``) or a station code outside the provider's grammar.
    """
    keys = [descriptor.key for descriptor in captures]
    if len(captures) > 1 or not _harvested(captures[0]):
        raise ObserwatorValidationError(
            message("sync.pace_until_not_harvested", keys=", ".join(keys)),
            details={"option": "pace_until", "value": keys, "reason": "not_harvested"},
        )
    for name, given in (("years", years), ("months", months)):
        if given is not None:
            raise ObserwatorValidationError(
                message("sync.option_not_for_captures", option=name),
                details={"option": name, "value": None, "reason": "captures"},
            )
    if stations is None:
        return ()
    return _parse_stations(stations, get_provider(captures[0].provider))


def _day_bound(name: str, value: object, last: date) -> date | None:
    """A bound of the days of capture datasets: a closed UTC day; None for none."""
    if value is None:
        return None
    if not isinstance(value, date) or isinstance(value, datetime):
        raise ObserwatorValidationError(
            message("sync.day_not_date", name=name, value=value),
            details={"option": name, "value": str(value)},
        )
    if value > last:
        raise ObserwatorValidationError(
            message(
                "sync.day_not_closed",
                name=name,
                day=value.isoformat(),
                last=last.isoformat(),
            ),
            details={
                "option": name,
                "value": value.isoformat(),
                "reason": "day_not_closed",
                "last": last.isoformat(),
            },
        )
    return value


def _capture_days(
    start: object, end: object, *, harvest: bool
) -> tuple[date, date] | None:
    """
    Check the days ``start`` and ``end`` of capture datasets; the days a harvest asks.

    Both are closed UTC days (before today, UTC) and ``end`` is not before ``start``.
    With ``harvest`` (``pace_until``), ``end`` defaults to the last closed day and
    ``start`` to ``end``, and ``start`` lies at most `HARVEST_DAYS` days before today
    (ADR-030 D9 and its erratum of 2026-11-23).

    Returns
    -------
    tuple of (datetime.date, datetime.date) or None
        The first and last day of the harvest; None without ``harvest``.

    Raises
    ------
    ObserwatorValidationError
        If a bound is no date, a day not closed yet (``details.reason``
        ``day_not_closed``), ``end`` is before ``start``, or a harvest's ``start``
        lies more than `HARVEST_DAYS` days back (``harvest_reach``, the first day
        allowed in ``details.earliest``).
    """
    today = _captures._now().date()
    last = today - timedelta(days=1)
    first, final = _day_bound("start", start, last), _day_bound("end", end, last)
    if first is not None and final is not None and final < first:
        raise ObserwatorValidationError(
            message(
                "sync.end_before_start", start=first.isoformat(), end=final.isoformat()
            ),
            details={"option": "end", "value": final.isoformat()},
        )
    if not harvest:
        return None
    final = last if final is None else final
    first = final if first is None else first
    earliest = today - timedelta(days=HARVEST_DAYS)
    if first < earliest:
        raise ObserwatorValidationError(
            message(
                "sync.harvest_reach",
                start=first.isoformat(),
                days=HARVEST_DAYS,
                earliest=earliest.isoformat(),
            ),
            details={
                "option": "start",
                "value": first.isoformat(),
                "reason": "harvest_reach",
                "earliest": earliest.isoformat(),
            },
        )
    return first, final


def _harvest_action(
    descriptor: DatasetDescriptor,
    codes: tuple[str, ...],
    pace_until: str,
    days: tuple[date, date],
) -> PlanAction:
    """The plan's ``store sync`` action of a harvest: its source is asked first."""
    return PlanAction(
        _SYNC,
        "missing",
        message(
            "sync.harvest_planned",
            dataset=descriptor.key,
            start=days[0].isoformat(),
            end=days[1].isoformat(),
            stations=", ".join(codes) if codes else message("sync.harvest_every"),
            until=pace_until,
        ),
    )


def _country_archives(
    descriptors: list[DatasetDescriptor],
    years: YearsArg | None,
    months: MonthsArg | None,
    stations: Iterable[str] | None,
) -> list[ArchiveFile]:
    """Country archives (IMGW-PIB) of the request, in the 3.0.0 order."""
    if stations is not None:
        raise ObserwatorValidationError(
            message("sync.imgw_archives_cover_whole"),
            details={"option": "stations", "value": None},
        )
    if years is None:
        raise ObserwatorValidationError(
            message("sync.imgw_datasets_need_option"),
            details={"option": "years", "value": None},
        )
    selected_years = parse_years(years, option="years")
    selected_months = (
        parse_months(months, option="months") if months is not None else None
    )
    result: dict[str, ArchiveFile] = {}
    for descriptor in descriptors:
        for archive in archive_files(
            descriptor.key, years=selected_years, months=selected_months
        ):
            result.setdefault(archive.server_path, archive)
    return list(result.values())


def _station_request(
    descriptors: list[DatasetDescriptor],
    years: YearsArg | None,
    months: MonthsArg | None,
    stations: Iterable[str] | None,
) -> tuple[tuple[str, ...], dict[str, tuple[ArchiveFile, ...] | None]]:
    """
    Station codes and offline candidates of a per-station request (ČHMÚ).

    Returns
    -------
    tuple of (tuple of str, dict)
        Sorted unique station codes and, per dataset key, the candidates of
        `archive_files` or None when the years come from the listing
        (station × year and station × month files without ``years``).
    """
    keys = ", ".join(descriptor.key for descriptor in descriptors)
    if stations is None:
        raise ObserwatorValidationError(
            message("sync.datasets_need_option_stations_station", keys=keys),
            details={"option": "stations", "value": None},
        )
    if months is not None:
        refusal = (
            message("sync.option_months_station_month", keys=keys)
            if any(item.archive_scope == "station_month" for item in descriptors)
            else message("sync.option_months_does_not_apply", keys=keys)
        )
        raise ObserwatorValidationError(
            refusal, details={"option": "months", "value": None}
        )
    codes: tuple[str, ...] = ()
    provided: Iterable[str] = stations
    candidates: dict[str, tuple[ArchiveFile, ...] | None] = {}
    for descriptor in descriptors:
        # Every dataset validates the codes by its provider's grammar.
        codes = provided = _parse_stations(provided, get_provider(descriptor.provider))
        candidates[descriptor.key] = (
            None
            if years is None
            and descriptor.archive_scope in ("station_year", "station_month")
            else archive_files(descriptor.key, years=years, stations=codes)
        )
    return codes, candidates


_Scope = CheckScope


def _scope(descriptor: DatasetDescriptor) -> _Scope:
    """
    How the files of a measurement dataset are found and checked: its adapter's choice.

    ``country``: archives enumerated offline and checked by HEAD (IMGW-PIB's
    archives of the whole country); ``folders``: archives named in the index of
    each folder and checked by HEAD (IMGW-PIB's per-station synop archives);
    ``stations``: station files checked by their listing (ČHMÚ); ``listing``:
    archives enumerated offline and published when the provider's listing names
    them, with no HTTP signal (IMGW-PIB's telemetry, `_check_listing`).
    """
    return get_provider(descriptor.provider).adapter.check_scope(descriptor)


def _folder_request(
    descriptors: list[DatasetDescriptor],
    years: YearsArg | None,
    months: MonthsArg | None,
    stations: Iterable[str] | None,
) -> tuple[tuple[str, ...], dict[str, tuple[ArchiveFile, ...] | None]]:
    """
    Station codes of a request of the per-station synop archives of IMGW-PIB.

    The files come from the folder index (`_check_folders`), so no dataset has
    offline candidates.

    Returns
    -------
    tuple of (tuple of str, dict)
        Sorted unique station codes (none: every station of the folder index)
        and None for every dataset key.
    """
    if years is None:
        raise ObserwatorValidationError(
            message("sync.imgw_datasets_need_option"),
            details={"option": "years", "value": None},
        )
    selected = parse_years(years, option="years")
    if months is not None:
        parse_months(months, option="months")
    codes = (
        _parse_stations(stations, get_provider(descriptors[0].provider))
        if stations is not None
        else ()
    )
    for descriptor in descriptors:
        _minimum_year(selected, descriptor)
    return codes, dict.fromkeys(descriptor.key for descriptor in descriptors)


class _Selection(NamedTuple):
    """The selectors of a check, validated offline (`_selection`)."""

    descriptors: list[DatasetDescriptor]
    codes: tuple[str, ...]
    candidates: dict[str, tuple[ArchiveFile, ...] | None]
    archives: list[ArchiveFile]
    days: tuple[date, date] | None = None
    """The first and last UTC day a harvest asks (``pace_until``); None without one."""


def _selection(
    datasets: Iterable[str],
    years: YearsArg | None,
    months: MonthsArg | None,
    stations: Iterable[str] | None,
    *,
    start: date | None = None,
    end: date | None = None,
    pace_until: str | None = None,
) -> _Selection:
    """
    Validate the selectors of a check offline, before any request.

    Shared by `check_store`, `sync_store` and the command catalog
    (``validate_command`` of ``store check`` and ``store sync``).

    Returns
    -------
    _Selection
        The datasets without repetitions, then for per-station datasets
        (ČHMÚ) the station codes and the candidates of each dataset (see
        `_station_request`) with no archives, for the per-station synop
        archives of IMGW-PIB the station codes and no candidates (see
        `_folder_request`) with no archives, for country datasets (IMGW-PIB,
        its telemetry included) no codes, no candidates and the archives, for
        station sources (lists and station metadata, ADR-015) no codes, no
        candidates and their files with a fixed name, or for capture datasets
        (ADR-030 D3, sealed from the spool) the codes of a harvest
        (``pace_until``, `_harvest_codes`: none for every station), no
        candidates and no files, and the days of the harvest (`_capture_days`).

    Raises
    ------
    ObserwatorValidationError
        If a selector is invalid for the datasets (see the callers),
        ``pace_until`` is no ``HH:MM`` or names no single harvest dataset, or
        ``start`` and ``end`` are invalid (`_capture_days`) or name no capture
        dataset (``details.reason`` ``not_capture``).
    """
    if not isinstance(datasets, str):
        datasets = tuple(datasets)
    if pace_until is not None:
        pace_deadline(pace_until, now=datetime.now(UTC))
    captures = _capture_descriptors(datasets)
    if captures is not None:
        if pace_until is not None:
            codes = _harvest_codes(captures, years, months, stations)
            days = _capture_days(start, end, harvest=True)
            return _Selection(captures, codes, {}, [], days)
        for name, given in (
            ("years", years),
            ("months", months),
            ("stations", stations),
        ):
            if given is not None:
                raise ObserwatorValidationError(
                    message("sync.option_not_for_captures", option=name),
                    details={"option": name, "value": None, "reason": "captures"},
                )
        _capture_days(start, end, harvest=False)
        return _Selection(captures, (), {}, [])
    if pace_until is not None:
        keys = [get_dataset(dataset).key for dataset in dict.fromkeys(datasets)]
        raise ObserwatorValidationError(
            message("sync.pace_until_not_harvested", keys=", ".join(keys)),
            details={"option": "pace_until", "value": keys, "reason": "not_harvested"},
        )
    if start is not None or end is not None:
        keys = [get_dataset(dataset).key for dataset in dict.fromkeys(datasets)]
        raise ObserwatorValidationError(
            message("sync.days_only_for_captures", keys=", ".join(keys)),
            details={
                "option": "start" if start is not None else "end",
                "value": keys,
                "reason": "not_capture",
            },
        )
    sources = _source_descriptors(datasets)
    if sources is not None:
        for name, given in (
            ("years", years),
            ("months", months),
            ("stations", stations),
        ):
            if given is not None:
                raise ObserwatorValidationError(
                    message("sync.option_not_for_station_sources", option=name),
                    details={
                        "option": name,
                        "value": None,
                        "reason": "station_sources",
                    },
                )
        return _Selection(
            sources,
            (),
            {},
            [file for d in sources for file in _station_files(d.key)],
        )
    descriptors = _descriptors(datasets)
    scopes = {_scope(descriptor) for descriptor in descriptors}
    if len(scopes) > 1:
        raise ObserwatorValidationError(
            message(
                "sync.one_call_covers_datasets_one",
                names=", ".join(item.key for item in descriptors),
            ),
            details={"option": "stations", "value": None},
        )
    if scopes == {"stations"}:
        codes, candidates = _station_request(descriptors, years, months, stations)
        return _Selection(descriptors, codes, candidates, [])
    if scopes == {"folders"}:
        codes, candidates = _folder_request(descriptors, years, months, stations)
        return _Selection(descriptors, codes, candidates, [])
    return _Selection(
        descriptors, (), {}, _country_archives(descriptors, years, months, stations)
    )


def _plan_target(root: Path, plan: PathArg) -> Path:
    """Plan file to write: outside the store, in an existing directory."""
    target = Path(plan).expanduser().absolute()
    resolved, store = target.resolve(), root.resolve()
    if resolved == store or store in resolved.parents:
        raise ObserwatorValidationError(
            message("sync.plan_must_written_outside_store", target=target),
            details={"option": "plan", "value": str(target)},
        )
    if not target.parent.is_dir():
        raise ObserwatorValidationError(
            message("sync.directory_plan_file_does_not", parent=target.parent),
            details={"option": "plan", "value": str(target)},
        )
    return target


def check_store(
    root: PathArg | StoreHandle,
    /,
    *,
    datasets: Iterable[str],
    years: YearsArg | None = None,
    months: MonthsArg | None = None,
    stations: Iterable[str] | None = None,
    start: date | None = None,
    end: date | None = None,
    pace_until: str | None = None,
    plan: PathArg | None = None,
    on_progress: ProgressHook | None = None,
    on_notice: NoticeHook | None = None,
    cancel: Cancel | None = None,
) -> StorePlan:
    """
    Plan a synchronization without downloading anything.

    Nothing is written to the store, not even staging files, and no archive is
    fetched. IMGW-PIB country archives are enumerated offline and checked with
    the listing of their parent directory and an HTTP ``HEAD`` request (a file
    is published when its name appears in the listing). The per-station synop
    archives of IMGW-PIB (``pl.imgw.meteo_synop_daily``) are the files the
    index of each folder of the selected years names, checked by ``HEAD`` the
    same way (ADR-022). ČHMÚ per-station files are checked with a single GET
    of each server directory listing, without any ``HEAD``: the listing's time
    (to the minute) and size are compared with the reference signal of the
    slot (the newest observation of its current version, or that version's
    ``Last-Modified`` and size). IMGW-PIB's monthly telemetry, which carries no
    HTTP signal, is checked by one listing of the datastore per year folder: a
    listed month is ``current`` when the store holds it, else ``missing``.
    Per-archive errors are recorded in the plan, never raised. A capture dataset
    (ADR-030 D3) is checked without a request: one item per closed UTC day of its
    spool (`obserwator.store.captures`), those from ``start`` to ``end`` when given;
    with ``pace_until`` also today's spool day, and one ``store sync`` action
    (``missing``) names the harvest the run would ask its source for first.

    Parameters
    ----------
    root : str, os.PathLike or StoreHandle
        Raw root (ADR-017) or an open handle of one.
    datasets : Iterable[str]
        Dataset keys, slugs or legacy aliases of measurement datasets of one
        kind: IMGW-PIB country archives, IMGW-PIB's telemetry, the IMGW-PIB synop
        archives or ČHMÚ station files (also those no series reads: ČHMÚ's
        groundwater ``recent`` and ``characteristic``, ADR-032, and its validated
        hourly files); or station sources; or capture datasets (no ``years``,
        ``months`` or ``stations``, except ``stations`` of a harvest). A bare
        string is rejected.
    years : YearsArg or None, optional
        Years to check (hydrological or calendar, as defined by each dataset):
        ``2024``, ``"2020-2023"``, ``"2020,2022"`` or a collection of such
        items. Required for IMGW-PIB datasets; optional for the ČHMÚ files of
        a station and year or month (``cz.chmu.hydro_daily``,
        ``cz.chmu.hydro_hourly``, ``cz.chmu.groundwater_daily``,
        ``cz.chmu.groundwater_weekly``, ``cz.chmu.groundwater_recent``: None
        checks every year and month the listing shows for the stations);
        rejected for ``cz.chmu.meteo_daily`` and
        ``cz.chmu.groundwater_characteristic``.
    months : MonthsArg or None, optional
        Months (1-12, same forms as ``years``) filtering physically monthly
        IMGW-PIB files only (also the running year's monthly synop files);
        yearly archives are returned once regardless of this filter. Rejected
        for ČHMÚ datasets.
    stations : Iterable[str] or None, optional
        Station codes: ČHMÚ WIGOS identifiers, required for ČHMÚ datasets;
        nine-digit IMGW-PIB codes selecting the synop station archives whose
        number is a code's last three digits (None: every station of the
        folder index); rejected for the other IMGW-PIB datasets; with
        ``pace_until`` the stations of the harvest (None: every station of the
        provider's list).
    start, end : datetime.date or None, optional
        Capture datasets only: the first and last closed UTC day (before today,
        UTC) of the spool days checked, None for no bound (every closed day);
        with ``pace_until`` also the days the harvest asks for: ``end`` by default
        the last closed day, ``start`` by default ``end`` and at most
        `obserwator.captures.HARVEST_DAYS` (40) days before today (ADR-030 D9).
    pace_until : str or None, optional
        ``HH:MM`` (local time) of a ``store sync`` that harvests one capture
        dataset first (`sync_store`): the plan adds today's spool day and the
        harvest's action; only for ``pl.imgw.hydro_operational`` and
        ``cz.chmu.hydro_recent``.
    plan : str, os.PathLike or None, optional
        File to save the plan to (``obserwator-plan/1``, see `StorePlan.to_json`); it
        must lie outside the store in an existing directory.
    on_progress : ProgressHook or None, optional
        Called after each archive with its plan status.
    on_notice : NoticeHook or None, optional
        Receives a ``source_unverifiable`` warning for every ``unverifiable``
        item or action and an ``archive_failed`` error for every
        ``check_failed`` item or action.
    cancel : Cancel or None, optional
        Polled before each listing and archive; once it returns ``True`` the
        remaining archives are listed as ``unverifiable`` with error
        ``"cancelled"``.

    Returns
    -------
    StorePlan
        ``obserwator-plan/1`` plan with one item per archive: ``current``,
        ``newer``, ``missing`` (published but not stored), ``unverifiable``
        (no comparable signal, ``"not published"`` when the file is not
        published, or ``"cancelled"``) or ``check_failed`` (listing or HEAD
        error, unreadable listing, local version or observation). IMGW-PIB
        items compare every header present on both sides (``signal="head"``);
        ČHMÚ items carry ``station_code``, ``signal="listing"``, the listing
        time ``remote_listed_at``, the listing size ``content_length`` and the
        reference observation ``local_observation``, and are ordered by
        dataset, station, year, element. A ČHMÚ station without any file of a
        dataset is one ``store sync`` action (``unverifiable``, or
        ``check_failed`` when the listing of its years cannot be read).
        ``series_state`` is empty: the series lie in the data root, whose
        state ``series build --check`` (`check_series`) reports (ADR-017).
        ``requests`` counts the requests made by the check (``"made"``) and
        the HEAD and GET of every ``newer`` and ``missing`` item
        (``"planned"``).

    Raises
    ------
    ObserwatorStoreError
        If ``root`` is not a supported raw root (code ``store_unavailable``;
        ``details.reason`` ``wrong_root`` for a data root) or a root path
        contains a symbolic link.
    ObserwatorValidationError
        If ``datasets`` is a string or empty, a dataset is unknown or does not
        produce measurement series, IMGW-PIB and ČHMÚ datasets are mixed or
        ``stations`` is missing or given against the datasets (option
        ``stations``), a station code does not follow the provider's grammar,
        the years/months are missing, invalid or rejected for the datasets,
        ``pace_until`` is invalid or names no single harvest dataset
        (``details.reason`` ``not_harvested``), ``start`` or ``end`` is no date, a
        day not closed yet (``day_not_closed``) or given for no capture dataset
        (``not_capture``), ``end`` is before ``start``, a harvest's ``start`` lies
        more than 40 days back (``harvest_reach``), or ``plan`` lies inside the
        store or in a missing directory.
    """
    descriptors, codes, candidates, archives, days = _selection(
        datasets, years, months, stations, start=start, end=end, pace_until=pace_until
    )
    refused = root_conflict_plan("store sync", root, kind="raw")
    if refused is not None:
        if plan is not None:
            refused.to_json(_plan_target(refused.root, plan))
        return refused
    path = lenient_store(root, kind="raw").root
    target = _plan_target(path, plan) if plan is not None else None
    if descriptors[0].archive_scope == CAPTURE_SCOPE:
        items, cancelled = check_captures(
            path,
            descriptors,
            today=pace_until is not None,
            start=start,
            end=end,
            on_progress=on_progress,
            on_notice=on_notice,
            cancel=cancel,
        )
        captured = StorePlan(
            schema="obserwator-plan/1",
            root=path,
            checked_at=datetime.now(UTC),
            items=tuple(items),
            series_state={},
            actions=(
                ()
                if pace_until is None or days is None
                else (_harvest_action(descriptors[0], codes, pace_until, days),)
            ),
            cancelled=cancelled,
            requests={"made": 0, "planned": 0},
        )
        if target is not None:
            captured.to_json(target)
        return captured
    sources = descriptors[0].time_unit == "station_list"
    scope = None if sources else _scope(descriptors[0])
    listed = sources or scope == "stations"
    made = 0

    def count(_request: httpx.Request) -> None:
        nonlocal made
        made += 1

    with httpx.Client(
        timeout=DEFAULT_TIMEOUT,
        follow_redirects=True,
        headers=_IDENTIFY if listed else None,
        event_hooks={"request": [count]},
    ) as client:
        if sources:
            items, actions, cancelled = _check_sources(
                client,
                path,
                descriptors,
                on_progress=on_progress,
                on_notice=on_notice,
                cancel=cancel,
            )
        elif scope == "folders":
            assert years is not None
            items, actions, cancelled = _check_folders(
                client,
                path,
                descriptors,
                years,
                months,
                codes,
                on_progress=on_progress,
                on_notice=on_notice,
                cancel=cancel,
            )
        elif listed:
            items, actions, cancelled = _check_listed(
                client,
                path,
                descriptors,
                codes,
                candidates,
                on_progress=on_progress,
                on_notice=on_notice,
                cancel=cancel,
            )
        elif scope == "listing":
            items, cancelled = _check_listing(
                client,
                path,
                archives,
                on_progress=on_progress,
                on_notice=on_notice,
                cancel=cancel,
            )
            actions = []
        else:
            items, cancelled = _check_country(
                client,
                path,
                archives,
                on_progress=on_progress,
                on_notice=on_notice,
                cancel=cancel,
            )
            actions = []
    # Every newer or missing item is a GET, after a HEAD unless the listing is its
    # only signal (the telemetry).
    requests = 1 if scope == "listing" else 2
    result = StorePlan(
        schema="obserwator-plan/1",
        root=path,
        checked_at=datetime.now(UTC),
        items=tuple(items),
        series_state={},
        actions=tuple(actions),
        cancelled=cancelled,
        requests={
            "made": made,
            "planned": requests
            * sum(item.status in ("newer", "missing") for item in items),
        },
    )
    if target is not None:
        result.to_json(target)
    return result


def _check_folders(
    client: httpx.Client,
    root: Path,
    descriptors: list[DatasetDescriptor],
    years: YearsArg,
    months: MonthsArg | None,
    codes: tuple[str, ...],
    *,
    on_progress: ProgressHook | None,
    on_notice: NoticeHook | None,
    cancel: Cancel | None,
) -> tuple[list[PlanItem], list[PlanAction], bool]:
    """
    Check the per-station synop archives of IMGW-PIB named in the folder index.

    One GET reads the index of every folder of the selected years (a
    five-year folder until 2000, then a year). The station archives it names
    (with ``codes`` only those whose number, the last three digits of a code,
    is requested) and the monthly files of the whole country of the running
    year (with ``months`` only those months) are then checked like country
    archives, by HEAD, in folder order. A folder that is not published is an
    ``unverifiable`` action, one whose index cannot be read a
    ``check_failed`` action; a requested station without an archive in the
    folders read is an ``unverifiable`` action unless a monthly file of the
    whole country was found.
    """
    selected = parse_years(years, option="years")
    chosen = set(parse_months(months, option="months")) if months is not None else None
    listings: dict[str, set[str] | Exception | None] = {}
    archives: list[ArchiveFile] = []
    actions: list[PlanAction] = []
    for descriptor in descriptors:
        adapter = get_provider(descriptor.provider).adapter
        numbers = {adapter.station_key(code) for code in codes}
        found: set[str] = set()
        monthly = False
        for directory in adapter.folders(descriptor, selected):
            if cancel is not None and cancel():
                return (
                    [_item(item, "unverifiable", error=CANCELLED) for item in archives],
                    actions,
                    True,
                )
            try:
                names = _listing(client, f"{adapter.provider.base_url}{directory}/")
            except httpx.HTTPError as exc:
                actions.append(
                    PlanAction(
                        _SYNC,
                        "check_failed",
                        message(
                            "sync.folder_error",
                            directory=directory,
                            error=_http_error(exc, source=adapter.server_name),
                        ),
                    )
                )
                continue
            listings[directory] = names
            if names is None:
                actions.append(
                    PlanAction(
                        _SYNC,
                        "unverifiable",
                        message(
                            "sync.folder_unpublished",
                            directory=directory,
                            key=descriptor.key,
                        ),
                    )
                )
                continue
            for name in sorted(names):
                archive = _archive_from_path(descriptor.key, f"{directory}/{name}")
                if archive is None:
                    continue
                station = adapter.archive_station(archive)
                if station is not None:
                    if numbers and station not in numbers:
                        continue
                    found.add(station)
                elif chosen is not None and archive.month not in chosen:
                    continue
                else:
                    monthly = True
                archives.append(archive)
        if not monthly:
            actions.extend(
                _no_files(descriptor, code)
                for code in codes
                if adapter.station_key(code) not in found
            )
    if on_notice is not None:
        for action in actions:
            on_notice(
                Notice("warning", "source_unverifiable", action.detail)
                if action.status == "unverifiable"
                else Notice("warning", "archive_failed", action.detail)
            )
    items, cancelled = _check_country(
        client,
        root,
        archives,
        on_progress=on_progress,
        on_notice=on_notice,
        cancel=cancel,
        listings=listings,
    )
    return items, actions, cancelled


def _check_country(
    client: httpx.Client,
    root: Path,
    archives: list[ArchiveFile],
    *,
    on_progress: ProgressHook | None,
    on_notice: NoticeHook | None,
    cancel: Cancel | None,
    listings: dict[str, set[str] | Exception | None] | None = None,
) -> tuple[list[PlanItem], bool]:
    """
    Check archives by directory listings and HEAD, in request order.

    ``listings`` holds the names of directories already listed (the folder
    index of the synop archives); the other directories are listed once.
    """
    listings = {} if listings is None else listings
    items: list[PlanItem] = []
    cancelled = False
    for index, archive in enumerate(archives, start=1):
        if not cancelled and cancel is not None and cancel():
            cancelled = True
        if cancelled:
            items.append(_item(archive, "unverifiable", error=CANCELLED))
            continue
        items.append(_check_one(client, root, archive, listings))
        _announce(
            items[-1],
            index,
            len(archives),
            on_progress=on_progress,
            on_notice=on_notice,
        )
    return items, cancelled


def _check_one(
    client: httpx.Client,
    root: Path,
    archive: ArchiveFile,
    listings: dict[str, set[str] | Exception | None],
) -> PlanItem:
    try:
        local = _current_version(root, archive)
    except ObserwatorDataError as exc:
        return _item(archive, "check_failed", error=reason(exc))
    directory = PurePosixPath(archive.server_path).parent.as_posix()
    provider = get_provider(get_dataset(archive.dataset).provider)
    source = provider.adapter.server_name
    if directory not in listings:
        try:
            listings[directory] = _listing(client, f"{provider.base_url}{directory}/")
        except httpx.HTTPError as exc:
            listings[directory] = exc
    listing = listings[directory]
    if isinstance(listing, Exception):
        error = _http_error(listing, source=source)
        return _item(archive, "check_failed", local=local, error=error)
    if listing is None or PurePosixPath(archive.server_path).name not in listing:
        return _item(archive, "unverifiable", local=local, error=UNPUBLISHED)
    try:
        signal = _head(client, archive)
    except httpx.HTTPError as exc:
        error = _http_error(exc, source=source)
        return _item(archive, "check_failed", local=local, error=error)
    if signal is None:
        return _item(archive, "unverifiable", local=local, error=UNPUBLISHED)
    if local is None:
        return _item(archive, "missing", signal=signal)
    status = _compare(dict(local.http), signal)
    return _item(
        archive,
        status,
        local=local,
        signal=signal,
        error=NO_SIGNAL if status == "unverifiable" else None,
    )


def _check_listing(
    client: httpx.Client,
    root: Path,
    archives: list[ArchiveFile],
    *,
    on_progress: ProgressHook | None,
    on_notice: NoticeHook | None,
    cancel: Cancel | None,
) -> tuple[list[PlanItem], bool]:
    """
    Check archives that carry no HTTP signal by their directory's listing, in order.

    One listing per directory (`ProviderAdapter.listing`: IMGW-PIB's telemetry asks
    its datastore, ``POST getFilesList``, once per year folder). A listed file is
    ``current`` when the store holds a version of its slot (published once; ``store
    sync --force`` downloads it again and compares the bytes), else ``missing``; a
    file the listing does not name, or a directory that is not published, is
    ``unverifiable`` (``not published``); an unreadable listing makes its files
    ``check_failed``. Every item has ``signal`` ``listing``.
    """
    listings: dict[str, set[str] | Exception | None] = {}
    items: list[PlanItem] = []
    cancelled = False
    for index, archive in enumerate(archives, start=1):
        if not cancelled and cancel is not None and cancel():
            cancelled = True
        if cancelled:
            items.append(_item(archive, "unverifiable", error=CANCELLED))
            continue
        items.append(
            replace(
                _check_listed_file(client, root, archive, listings), signal="listing"
            )
        )
        _announce(
            items[-1],
            index,
            len(archives),
            on_progress=on_progress,
            on_notice=on_notice,
        )
    return items, cancelled


def _check_listed_file(
    client: httpx.Client,
    root: Path,
    archive: ArchiveFile,
    listings: dict[str, set[str] | Exception | None],
) -> PlanItem:
    """Plan item of one file published by its listing alone (see `_check_listing`)."""
    try:
        local = _current_version(root, archive)
    except ObserwatorDataError as exc:
        return _item(archive, "check_failed", error=reason(exc))
    descriptor = get_dataset(archive.dataset)
    adapter = get_provider(descriptor.provider).adapter
    directory = PurePosixPath(archive.server_path).parent.as_posix()
    if directory not in listings:
        try:
            listings[directory] = adapter.listing(descriptor, directory, client=client)
        except httpx.HTTPError as exc:
            listings[directory] = exc
    listing = listings[directory]
    if isinstance(listing, Exception):
        error = _http_error(listing, source=adapter.server_name)
        return _item(archive, "check_failed", local=local, error=error)
    if listing is None or PurePosixPath(archive.server_path).name not in listing:
        return _item(archive, "unverifiable", local=local, error=UNPUBLISHED)
    return _item(archive, "missing" if local is None else "current", local=local)


def _check_sources(
    client: httpx.Client,
    root: Path,
    descriptors: list[DatasetDescriptor],
    *,
    on_progress: ProgressHook | None,
    on_notice: NoticeHook | None,
    cancel: Cancel | None,
) -> tuple[list[PlanItem], list[PlanAction], bool]:
    """
    Check the station sources of the catalogs (ADR-015) against their slots.

    A station list is checked with ``HEAD`` against the reference signal of its
    slot (the newest observation of the current version, else its own
    ``extra.http``). The station metadata without a stable signal (the current-
    data API answers of IMGW-PIB, the hydro ``now`` metadata of ČHMÚ) are
    ``unverifiable`` without a request, so a sync downloads them and the
    store compares the bytes (or the canonical content). The newest daily
    ČHMÚ meteo ``now`` file is named by its directory listing: ``current``
    when the store holds it, else ``missing``; an unreadable listing is a
    ``check_failed`` action.
    """
    targets: list[ArchiveFile] = []
    actions: list[PlanAction] = []
    for descriptor in descriptors:
        targets.extend(_station_files(descriptor.key))
        if descriptor.update_signal != "listing":
            continue
        listing_url = (
            f"{get_provider(descriptor.provider).base_url}{descriptor.server_dir}/"
        )
        listing = _read_listing(
            client, listing_url, source=get_provider(descriptor.provider).short_name
        )
        newest = sorted(
            name for name in listing.entries if _station_file(descriptor, name)
        )
        if listing.error is not None or not newest:
            actions.append(
                PlanAction(
                    _SYNC,
                    "check_failed",
                    message(
                        "sync.station_source_listing",
                        key=descriptor.key,
                        error=listing.error or message("sync.no_file_in_listing"),
                    ),
                )
            )
            continue
        archive = _station_file(descriptor, newest[-1])
        assert archive is not None
        targets.append(archive)
    items: list[PlanItem] = []
    cancelled = False
    for index, archive in enumerate(targets, start=1):
        cancelled = cancelled or (cancel is not None and cancel())
        if cancelled:
            items.append(_item(archive, "unverifiable", error=CANCELLED))
            continue
        items.append(_check_source(client, root, archive))
        _announce(
            items[-1],
            index,
            len(targets),
            on_progress=on_progress,
            on_notice=on_notice,
        )
    return items, actions, cancelled


def _check_source(client: httpx.Client, root: Path, archive: ArchiveFile) -> PlanItem:
    """Plan item of one station source (see `_check_sources`)."""
    descriptor = get_dataset(archive.dataset)
    try:
        local = _current_version(root, archive)
        reference = (
            _reference_signal(root, slot=_archive_slot(archive))
            if local is not None
            else None
        )
    except ObserwatorDataError as exc:
        return _item(archive, "check_failed", error=reason(exc))
    if descriptor.update_signal == "none":
        return _item(
            archive,
            "unverifiable",
            local=local,
            error=message("sync.station_source_no_signal"),
        )
    if descriptor.update_signal == "listing":
        return _item(archive, "missing" if local is None else "current", local=local)
    try:
        signal = _head(client, archive)
    except httpx.HTTPError as exc:
        source = get_provider(descriptor.provider).short_name
        return _item(
            archive, "check_failed", local=local, error=_http_error(exc, source=source)
        )
    if signal is None:
        return _item(archive, "unverifiable", local=local, error=UNPUBLISHED)
    if local is None:
        return _item(archive, "missing", signal=signal)
    observation = reference.observation if reference is not None else None
    stored: dict[str, object] = (
        {"etag": reference.etag, "last_modified": reference.last_modified}
        if reference is not None and observation is not None
        else dict(local.http)
    )
    status = _compare(stored, signal)
    item = _item(
        archive,
        status,
        local=local,
        signal=signal,
        error=NO_SIGNAL if status == "unverifiable" else None,
    )
    # The observation giving the reference signal, as the ČHMÚ listing items name it.
    return replace(
        item,
        local_observation=observation.relative_to(root)
        if observation is not None
        else None,
    )


def _download(
    archive: ArchiveFile,
    /,
    *,
    client: httpx.Client | None = None,
    cancel: Cancel | None = None,
) -> DownloadResult:
    """
    GET one archive for a store version.

    IMGW-PIB country archives go through the 2.1.1 download functions. A
    per-station file (ČHMÚ, the synop archives of IMGW-PIB) is fetched by its
    URL, through ``client`` when given, and must be a ZIP when its name says
    so. The station details of hydro.imgw.pl are one request per station of
    its map (ADR-021); ``cancel`` is polled between them.

    Raises
    ------
    ObserwatorConnectionError
        If the download fails (``source_unavailable``).
    ObserwatorDataError
        If an IMGW-PIB archive is no ZIP or a header is invalid.
    ObserwatorCancelledError
        If ``cancel`` stops the requests of the station details.
    """
    descriptor = get_dataset(archive.dataset)
    if client is None and (
        descriptor.archive_scope != "country" or descriptor.time_unit == "station_list"
    ):
        with httpx.Client(
            timeout=DOWNLOAD_TIMEOUT, follow_redirects=True, headers=_IDENTIFY
        ) as own:
            return _download(archive, client=own, cancel=cancel)
    return get_provider(descriptor.provider).adapter.download(
        archive, client=client, cancel=cancel
    )


def _result(
    item: PlanItem,
    status: Literal[
        "new",
        "relabeled",
        "unchanged",
        "failed",
        "stale_plan",
        "cancelled",
    ],
    *,
    version: Path | None = None,
    error: str | None = None,
    error_code: ErrorCode | None = None,
) -> OperationResult:
    return OperationResult(
        _archive_slot(item.archive), status, version, error, error_code=error_code
    )


def _stale(item: PlanItem, signal: _Signal | None) -> bool:
    """Whether the HEAD signal differs from the signal the item was planned with."""
    if signal is None:
        return True
    if item.signal == "listing":
        moment = _minute(signal.last_modified)
        return (
            moment is None
            or _listed_at(moment) != item.remote_listed_at
            or signal.content_length != item.content_length
        )
    return (signal.etag, signal.last_modified) != (
        item.remote_etag,
        item.remote_last_modified,
    )


def sync_store(
    root: PathArg | StoreHandle | None = None,
    /,
    *,
    output_dir: PathArg | None = None,
    force: bool = False,
    datasets: Iterable[str] | None = None,
    years: YearsArg | None = None,
    months: MonthsArg | None = None,
    stations: Iterable[str] | None = None,
    start: date | None = None,
    end: date | None = None,
    pace_until: str | None = None,
    plan: StorePlan | PathArg | None = None,
    on_progress: ProgressHook | None = None,
    on_notice: NoticeHook | None = None,
    cancel: Cancel | None = None,
) -> SyncReport:
    """
    Download the archives that a plan marks as new or missing, or write them as plain files.

    Downloads write only raw data (ADR-015): the archives, the station lists
    and the station metadata of the catalogs. Series and catalogs are built
    from the store afterwards by ``series build`` and ``store catalog``. A
    capture dataset (ADR-030 D3) downloads nothing: every closed UTC day of its
    spool (those from ``start`` to ``end`` when given) is sealed into one version
    (`obserwator.store.captures.seal_day`), ``new`` or ``unchanged`` when its
    current version holds every answer, and the day's spool files are removed
    once the version holding them is published.

    With ``pace_until`` a harvest dataset (``pl.imgw.hydro_operational``,
    ``cz.chmu.hydro_recent``; ADR-030 D9) is first asked at its source for the UTC
    days ``start`` to ``end``, by default the last closed day
    (`obserwator.captures.harvest`; a backfill reaches at most 40 days back, the
    hours of hydro-back's answer cover every day): one request per station and
    source (ČHMÚ: per station and day), spread evenly until that local time and
    never closer than 5 s, every answer into the spool; then the closed days of its
    spool and today's, which holds the run's answers, are sealed (answers that
    come later today give a correction version the next night). A request that
    fails, a station skipped after the backoff, a run stopped by three connection
    failures in a row and a station list that cannot be read are each one
    ``failed`` result without a slot, so a partial harvest ends ``partial``;
    ``harvest`` reports the counts and times.

    A run that seals captures (a capture dataset, a harvest or a plan holding
    capture days) holds the lock of ADR-030 D10 for its whole run, the harvest
    included: ``flock`` on ``<state_dir>/obserwator/store-sync.lock``. One that
    finds it held tries again every second for `LOCK_WAIT` (10 minutes), then
    fails with ``conflict``. A sync of archives, station sources or catalogs takes
    no lock (the writer's no-replace publication keeps parallel downloads safe),
    nor does a check (`check_store`, ``--check``) or a plain write.

    Without ``plan`` the plan is built by :func:`check_store` from the given
    selectors; ``plan`` and the selectors are mutually exclusive. Before each
    download an HTTP ``HEAD`` re-validates the item: when the ETag or
    Last-Modified (IMGW-PIB), or the Last-Modified minute or Content-Length
    against the listing (ČHMÚ), differs from the plan, or the file is gone,
    the item ends as ``stale_plan`` and is not downloaded; station metadata
    without a signal are downloaded and compared after the download.
    ``check_failed`` items are never downloaded. An ``unverifiable`` item is
    downloaded (then deduplicated by SHA-256) only in a sync without a
    supplied plan; from a supplied plan it stays ``unchanged`` with a
    ``source_unverifiable`` warning. An unpublished item (``"not published"``)
    stays ``unchanged``. Failures of single archives are reported per slot,
    not raised.

    With ``output_dir`` (plain mode, DEV-19.1) the selected archives are
    written as ordinary files ``<output_dir>/<server_path>`` like
    ``datasets download`` does: there is no local version to compare with, so
    every selected file is fetched and an existing target without ``force`` is a
    ``conflict`` that lists every path before the first request (a plan acts on
    versions, DEV-19.17). ČHMÚ station files need ``years`` in plain mode,
    because the years of a store sync come from the server listing; the
    station sources of the catalogs are stored only in a store.

    Parameters
    ----------
    root : str, os.PathLike, StoreHandle or None, optional
        Raw root (ADR-017); None (with no ``output_dir``) is the default raw
        root (``OBSERWATOR_RAW_ROOT``, ``[obserwator] raw_root`` of
        ``nogat.toml`` or ``<data_dir>/obserwator-raw``).
    output_dir : str, os.PathLike or None, optional
        Plain mode: directory of the files, created when missing. Excludes
        ``root``.
    force : bool, optional
        Plain mode: replace existing target files (each atomically; nothing
        else is deleted). Store mode: fetch every selected archive again, also
        the ones the plan calls ``current``; a version is never overwritten.
    datasets : Iterable[str] or None, optional
        Dataset keys, slugs or legacy aliases; required when ``plan`` is not
        given.
    years : YearsArg or None, optional
        Years to synchronize (``2024``, ``"2020-2023"``, ``"2020,2022"`` or a
        collection of such items), as in :func:`check_store`.
    months : MonthsArg or None, optional
        Months (1-12) filtering physically monthly IMGW-PIB files.
    stations : Iterable[str] or None, optional
        Station codes (ČHMÚ WIGOS identifiers, nine-digit codes of the IMGW-PIB
        synop archives), as in :func:`check_store`; with ``pace_until`` the
        stations of the harvest (None: every station of the provider's list).
    start, end : datetime.date or None, optional
        Capture datasets only: the first and last closed UTC day of the spool days
        sealed, None for no bound (every closed day); with ``pace_until`` also the
        days the harvest asks for (``end`` by default the last closed day,
        ``start`` by default ``end``, at most 40 days before today), as in
        :func:`check_store`. Store mode only, without ``plan``.
    pace_until : str or None, optional
        ``HH:MM`` (24 h, local time): harvest one dataset of
        ``pl.imgw.hydro_operational`` and ``cz.chmu.hydro_recent`` before sealing
        it, the requests spread to that time of the local day (one already passed
        means the minimum spacing of 5 s). Store mode only, without ``plan``.
    plan : StorePlan, str, os.PathLike or None, optional
        Plan from :func:`check_store`, or the path of its ``obserwator-plan/1`` JSON file.
        Must refer to the same store root. Store mode only.
    on_progress : ProgressHook or None, optional
        Called after each archive with its operation status; also forwarded to
        :func:`check_store`.
    on_notice : NoticeHook or None, optional
        Receives warnings and errors (``stale_plan``, ``source_unverifiable``,
        ``archive_failed``, a harvest's ``harvest_failed``) and notices of the
        writer (e.g. ``content_unchanged``) and of a harvest (``harvest_done``,
        info).
    cancel : Cancel or None, optional
        Polled while the lock is waited for and before each archive; once it
        returns ``True`` the remaining items end as ``cancelled``.

    Returns
    -------
    SyncReport
        One :class:`OperationResult` per plan item (``new``, ``relabeled``,
        ``unchanged``, ``failed``, ``stale_plan`` or
        ``cancelled``), then one ``failed`` result without a slot for every
        ``check_failed`` action of the plan (a ČHMÚ listing that could
        not be read) and every failure of a harvest, the overall cancellation
        flag, ``files``: the versions with their size, SHA-256 and status (store
        mode) or the files written, ``written`` or ``replaced`` (plain mode), and
        ``harvest`` (`HarvestReport`) with ``pace_until``. A plain file written is
        an item ``new``; an unpublished ČHMÚ candidate is ``unchanged``.

    Raises
    ------
    ObserwatorValidationError
        If both ``plan`` and selectors (``start``, ``end`` and ``pace_until``
        included) are given, ``datasets`` is missing without a plan, the plan
        refers to another store, or the selectors are invalid (see
        :func:`check_store`); if both ``output_dir`` and ``root`` are given
        (``details["reason"]="exclusive_options"``); if ``plan``, ``start``,
        ``end`` or ``pace_until`` is given with ``output_dir``
        (``details["reason"]="store_only_option"``) or station sources or
        captures are synchronized as plain files
        (``details["reason"]="store_only_dataset"``).
    ObserwatorError
        ``conflict`` in plain mode before any request (``output_exists``,
        ``duplicate_output_name``, ``output_in_store``; ``details["paths"]`` is
        the output directory when it is or lies in a store, else every
        offending path); in store mode when ``root`` nests a store
        (``nested_store``) or holds other files and is no store (``not_empty``).
    ObserwatorStoreConflictError
        ``conflict`` with ``details.reason`` ``sync_locked`` (and the lock file in
        ``details.path``) when another run held the lock of the captures for
        `LOCK_WAIT`.
    ObserwatorCancelledError
        If ``cancel`` returned True while the lock was waited for.
    ObserwatorDataError
        If the plan file cannot be read, the marker of ``root`` is unreadable or
        the lock file cannot be opened (``io_error``).
    ObserwatorStoreError
        If ``root`` is not a supported Obserwator store.
    """
    target = resolve_target(
        output_dir=output_dir,
        root=root.root if isinstance(root, StoreHandle) else root,
    )
    if target.mode == "plain":
        return _sync_plain(
            target.path,
            force=force,
            datasets=datasets,
            years=years,
            months=months,
            stations=stations,
            start=start,
            end=end,
            pace_until=pace_until,
            plan=plan,
            on_progress=on_progress,
            on_notice=on_notice,
            cancel=cancel,
        )
    refuse_root(target.path, kind="raw")
    path = lenient_store(target.path, kind="raw").root
    selectors = (datasets, years, months, stations, start, end, pace_until)
    if plan is not None and any(option is not None for option in selectors):
        raise ObserwatorValidationError(
            message("sync.give_plan_selectors_datasets_years")
        )
    selection: _Selection | None = None
    if plan is None:
        if datasets is None:
            raise ObserwatorValidationError(
                message("sync.without_plan_parameter_datasets_required"),
                details={"option": "datasets", "value": None},
            )
        # Every selector is checked before a run waits for the lock.
        selection = _selection(
            datasets,
            years,
            months,
            stations,
            start=start,
            end=end,
            pace_until=pace_until,
        )
    else:
        if not isinstance(plan, StorePlan):
            plan = StorePlan.from_json(plan)
        _same_root(plan, path)
    with _sync_lock(cancel=cancel) if _seals(selection, plan) else nullcontext():
        harvest: HarvestReport | None = None
        harvested: list[OperationResult] = []
        if plan is None:
            assert datasets is not None and selection is not None
            if pace_until is not None:
                harvest, harvested, plan = _harvest_plan(
                    path,
                    selection,
                    pace_until,
                    start=start,
                    end=end,
                    on_progress=on_progress,
                    on_notice=on_notice,
                    cancel=cancel,
                )
            else:
                plan = check_store(
                    path,
                    datasets=datasets,
                    years=years,
                    months=months,
                    stations=stations,
                    start=start,
                    end=end,
                    on_progress=on_progress,
                    on_notice=on_notice,
                    cancel=cancel,
                )
            _same_root(plan, path)
        return _sync_plan(
            path,
            plan,
            explicit=selection is not None,
            force=force,
            harvest=harvest,
            harvested=harvested,
            on_progress=on_progress,
            on_notice=on_notice,
            cancel=cancel,
        )


def _same_root(plan: StorePlan, root: Path) -> None:
    """Refuse a plan of another store than ``root``."""
    if Path(plan.root).expanduser().absolute() != root:
        raise ObserwatorValidationError(
            message("sync.plan_concerns_another_store", root=plan.root)
        )


def sync_lock_path() -> Path:
    """
    The lock file of ``store sync``: ``<state_dir>/obserwator/store-sync.lock``.

    A ``store sync`` that seals captures holds it for its whole run (ADR-030 D10).

    Returns
    -------
    pathlib.Path
        The absolute path; the file need not exist.
    """
    return (Settings().state_dir / environment.TOOL / LOCK_FILE).expanduser().absolute()


def _seals(selection: _Selection | None, plan: StorePlan | None) -> bool:
    """
    Whether a ``store sync`` seals captures, so takes the lock (ADR-030 D10).

    A selection of capture datasets (a harvest's included) or a plan holding a
    capture day does; archives, station sources and catalogs do not.
    """
    if selection is not None:
        return selection.descriptors[0].archive_scope == CAPTURE_SCOPE
    return plan is not None and any(
        get_dataset(item.archive.dataset).archive_scope == CAPTURE_SCOPE
        for item in plan.items
    )


@contextmanager
def _sync_lock(*, cancel: Cancel | None) -> Iterator[None]:
    """
    Hold the lock of the captures' sealing for one ``store sync`` (ADR-030 D10).

    ``flock`` on `sync_lock_path` (created ``0600`` with its directory) for the whole
    run. While another run holds it, the lock is tried again every `_LOCK_POLL`
    seconds for `LOCK_WAIT` seconds on the clock of the paced runs
    (`obserwator.fetch._clock`), polling ``cancel``. The lock goes with the process:
    one that ends, however it ends, releases it. POSIX only, as the GUI's ``flock``
    (ADR-020 erratum of 2026-11-14): on Windows a run takes no lock.

    Raises
    ------
    ObserwatorStoreConflictError
        ``conflict`` (``details.reason`` ``sync_locked``, ``details.path`` the lock
        file, ``details.waited`` the seconds) when the lock stayed held.
    ObserwatorCancelledError
        If ``cancel`` returned True while waiting.
    ObserwatorDataError
        ``io_error`` when the lock file cannot be created or locked.
    """
    # An else block, not code after a return: mypy resolves names only in the
    # branch of the platform it checks, so `fcntl` is no name on Windows.
    if sys.platform == "win32":
        yield
    else:
        path = sync_lock_path()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            handle = os.open(path, os.O_RDWR | os.O_CREAT | os.O_CLOEXEC, 0o600)
        except OSError as exc:
            raise io_error(exc) from exc
        try:
            clock = _fetch._clock()
            started = clock.now()
            while True:
                try:
                    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    pass
                except OSError as exc:
                    raise io_error(exc) from exc
                if cancel is not None and cancel():
                    raise ObserwatorCancelledError(CANCELLED)
                waited = (clock.now() - started).total_seconds()
                if waited >= LOCK_WAIT:
                    raise ObserwatorStoreConflictError(
                        message("sync.sync_locked", path=path, seconds=f"{waited:.0f}"),
                        details={
                            "reason": "sync_locked",
                            "path": str(path),
                            "waited": round(waited, 3),
                        },
                    )
                clock.sleep(min(_LOCK_POLL, LOCK_WAIT - waited))
            yield
        finally:
            os.close(handle)


def _sync_plan(
    path: Path,
    plan: StorePlan,
    *,
    explicit: bool,
    force: bool,
    harvest: HarvestReport | None,
    harvested: list[OperationResult],
    on_progress: ProgressHook | None,
    on_notice: NoticeHook | None,
    cancel: Cancel | None,
) -> SyncReport:
    """Carry out a plan in the raw root ``path`` (`sync_store`, under its lock)."""

    def cancelled() -> bool:
        return cancel is not None and cancel()

    results: list[OperationResult] = []
    stop = False
    # ČHMÚ requests name obserwator/<version> (spec 2026-10-18 §4.5), also those
    # of its station sources, which have no listing signal.
    identify = any(
        item.signal == "listing"
        or get_provider(get_dataset(item.archive.dataset).provider).adapter.identifies
        for item in plan.items
    )
    with httpx.Client(
        timeout=DEFAULT_TIMEOUT,
        follow_redirects=True,
        headers=_IDENTIFY if identify else None,
    ) as client:
        for index, item in enumerate(plan.items, start=1):
            stop = stop or cancelled()
            if stop:
                results.append(_result(item, "cancelled", error=CANCELLED))
                continue
            if get_dataset(item.archive.dataset).archive_scope == CAPTURE_SCOPE:
                sealed = seal_item(path, item, on_notice=on_notice, cancel=cancel)
                results.append(sealed)
            else:
                results.append(
                    _sync_one(
                        client,
                        path,
                        item,
                        explicit=explicit,
                        force=force,
                        cancel=cancel,
                        on_notice=on_notice,
                    )
                )
            if on_progress is not None:
                on_progress(
                    Progress(
                        index,
                        len(plan.items),
                        "archive",
                        results[-1].status,
                        item.archive.server_path,
                    )
                )
    unchecked = [
        OperationResult(
            None,
            "failed",
            None,
            action.detail,
            error_code=_failure_code(action.detail.partition(": ")[2]),
        )
        for action in plan.actions
        if action.command == _SYNC and action.status == "check_failed"
    ]

    was_cancelled = (
        stop
        or any(result.status == "cancelled" for result in results)
        or (harvest is not None and harvest.cancelled)
    )
    files = tuple(
        version_file(result.version, cast(_VersionStatus, result.status))
        for result in results
        if result.version is not None and result.status in _DONE
    )
    return SyncReport(
        items=(*results, *unchecked, *harvested),
        cancelled=was_cancelled,
        files=files,
        harvest=harvest,
    )


def _harvest_plan(
    root: Path,
    selection: _Selection,
    pace_until: str,
    *,
    start: date | None,
    end: date | None,
    on_progress: ProgressHook | None,
    on_notice: NoticeHook | None,
    cancel: Cancel | None,
) -> tuple[HarvestReport, list[OperationResult], StorePlan]:
    """
    The harvest of ``store sync --pace-until``, then the plan sealing its spool days.

    ``selection`` is validated before any request (`_selection`); the harvest asks
    its days (``selection.days``: ``start`` to ``end``, by default the last closed
    UTC day; `obserwator.captures.harvest`, the deadline from ``pace_until`` on the
    run's clock), and the plan holds the closed spool days of the dataset (from
    ``start`` to ``end`` when given) and today's, which the harvest's answers went
    to (ADR-030 errata of 2026-11-23). Returns the harvest's report, its failures
    and the plan.
    """
    assert selection.days is not None
    descriptors = selection.descriptors
    clock = _fetch._clock()
    report, failures = _harvest(
        descriptors[0].key,
        selection.days[0],
        selection.days[1],
        stations=selection.codes or None,
        deadline=pace_deadline(pace_until, now=clock.now()),
        clock=clock,
        on_progress=on_progress,
        on_notice=on_notice,
        cancel=cancel,
    )
    items, cancelled = check_captures(
        root,
        descriptors,
        today=True,
        start=start,
        end=end,
        on_progress=on_progress,
        on_notice=on_notice,
        cancel=cancel,
    )
    plan = StorePlan(
        schema="obserwator-plan/1",
        root=root,
        checked_at=datetime.now(UTC),
        items=tuple(items),
        series_state={},
        cancelled=cancelled,
        requests={"made": report.requests, "planned": 0},
    )
    return report, failures, plan


def _plain_archives(
    datasets: Iterable[str],
    years: YearsArg | None,
    months: MonthsArg | None,
    stations: Iterable[str] | None,
) -> list[ArchiveFile]:
    """
    The archives a plain sync writes: the selection of the store, resolved offline.

    The per-station synop archives of IMGW-PIB are the candidates of
    `archive_files`: the stations' archives and the monthly files of
    ``months`` (the store reads the folder index instead).

    Raises
    ------
    ObserwatorValidationError
        If the selectors are invalid (see `_selection`), name station sources
        (stored only, ``details.reason`` ``store_only_dataset``), a ČHMÚ
        dataset of station-year or station-month files has no ``years`` (the
        store reads them from the server listing, which a plain write does not
        use), or the synop archives have neither ``stations`` nor ``months``.
    """
    descriptors, _, candidates, archives, _ = _selection(
        datasets, years, months, stations
    )
    if descriptors[0].time_unit == "station_list":
        raise ObserwatorValidationError(
            message("sync.station_sources_store_only"),
            details={"option": "datasets", "reason": "store_only_dataset"},
        )
    if descriptors[0].archive_scope == CAPTURE_SCOPE:
        raise ObserwatorValidationError(
            message("sync.captures_store_only"),
            details={"option": "datasets", "reason": "store_only_dataset"},
        )
    if not candidates:
        return archives
    if _scope(descriptors[0]) == "folders":
        candidates = {
            descriptor.key: archive_files(
                descriptor.key, years=years, months=months, stations=stations
            )
            for descriptor in descriptors
        }
    unnamed = [d.key for d in descriptors if candidates[d.key] is None]
    if unnamed:
        raise ObserwatorValidationError(
            message("sync.plain_needs_years", keys=", ".join(unnamed)),
            details={
                "option": "years",
                "value": None,
                "reason": "years_required_in_plain_mode",
            },
        )
    chosen: dict[str, ArchiveFile] = {}
    for descriptor in descriptors:
        for archive in candidates[descriptor.key] or ():
            chosen.setdefault(archive.server_path, archive)
    return list(chosen.values())


def _plain_result(item: DownloadItem) -> OperationResult:
    """Per-file outcome of a plain download as the operation of a sync."""
    if item.status == "downloaded":
        return OperationResult(item.slot, "new", item.path, None)
    if item.status == "not_published":
        return OperationResult(item.slot, "unchanged", None, item.error)
    if item.status == "cancelled":
        return OperationResult(item.slot, "cancelled", None, CANCELLED)
    return OperationResult(
        item.slot, "failed", None, item.error, error_code=item.error_code
    )


def _sync_plain(
    directory: Path,
    *,
    force: bool,
    datasets: Iterable[str] | None,
    years: YearsArg | None,
    months: MonthsArg | None,
    stations: Iterable[str] | None,
    start: date | None,
    end: date | None,
    pace_until: str | None,
    plan: StorePlan | PathArg | None,
    on_progress: ProgressHook | None,
    on_notice: NoticeHook | None,
    cancel: Cancel | None,
) -> SyncReport:
    """
    Write the selected archives as plain files below ``directory`` (DEV-19.9, DEV-19.17).

    Raises
    ------
    ObserwatorValidationError
        If ``plan``, ``start``, ``end`` or ``pace_until`` is given (they act on
        versions and the spool), ``datasets`` is missing, the selectors are invalid
        or name station sources or captures (stored only).
    ObserwatorError
        ``conflict`` before the first request (see ``download_archives``).
    """
    for name, given in (
        ("plan", plan),
        ("start", start),
        ("end", end),
        ("pace_until", pace_until),
    ):
        if given is not None:
            raise ObserwatorValidationError(
                message("sync.store_only_option", name=name),
                details={
                    "option": name,
                    "value": str(given),
                    "reason": "store_only_option",
                },
            )
    if datasets is None:
        raise ObserwatorValidationError(
            message("sync.without_plan_parameter_datasets_required"),
            details={"option": "datasets", "value": None},
        )
    archives = _plain_archives(datasets, years, months, stations)
    items, written = _download_plain(
        archives,
        directory,
        force=force,
        timeout=DOWNLOAD_TIMEOUT,
        on_progress=on_progress,
        on_notice=on_notice,
        cancel=cancel,
    )
    return SyncReport(
        items=tuple(_plain_result(item) for item in items),
        cancelled=any(item.status == "cancelled" for item in items),
        files=tuple(written),
    )


def _sync_one(
    client: httpx.Client,
    root: Path,
    item: PlanItem,
    *,
    explicit: bool,
    force: bool,
    cancel: Cancel | None,
    on_notice: NoticeHook | None,
) -> OperationResult:
    local = root / item.local_path if item.local_path is not None else None
    descriptor = get_dataset(item.archive.dataset)
    # Station metadata without an HTTP signal are compared after the download, and
    # a file published by its listing alone (the telemetry) has no HEAD to compare.
    unsigned = (
        descriptor.time_unit == "station_list" and descriptor.update_signal != "http"
    ) or _scope(descriptor) == "listing"
    if item.status == "current" and not force:
        return _result(item, "unchanged", version=local)
    if item.status == "check_failed":
        return _result(
            item, "failed", error=item.error, error_code=_failure_code(item.error)
        )
    if item.status == "unverifiable":
        if item.error == CANCELLED:
            return _result(item, "cancelled", error=CANCELLED)
        if item.error == UNPUBLISHED:
            return _result(item, "unchanged", version=local, error=UNPUBLISHED)
        if not explicit:
            if on_notice is not None:
                on_notice(
                    Notice(
                        "warning",
                        "source_unverifiable",
                        message(
                            "sync.skipped_sync_from_plan",
                            server_path=item.archive.server_path,
                            error=item.error,
                        ),
                    )
                )
            return _result(item, "unchanged", version=local, error=item.error)
        if on_notice is not None and descriptor.update_signal != "none":
            on_notice(
                Notice(
                    "warning",
                    "source_unverifiable",
                    message(
                        "sync.download_and_compare",
                        server_path=item.archive.server_path,
                        error=item.error,
                    ),
                )
            )
    if not unsigned:
        try:
            signal = _head(client, item.archive)
        except httpx.HTTPError as exc:
            return _result(
                item,
                "failed",
                error=_http_error(exc, source=_source(item.archive)),
                error_code="source_unavailable",
            )
        if _stale(item, signal):
            text = message("sync.stale_plan", server_path=item.archive.server_path)
            if on_notice is not None:
                on_notice(Notice("warning", "stale_plan", text))
            return _result(item, "stale_plan", version=local, error=text)
    try:
        response = _download(item.archive, client=client, cancel=cancel)
        written = write_archive(
            root,
            archive=item.archive,
            response=response,
            on_notice=on_notice,
            cancel=cancel,
        )
    except (ObserwatorError, OSError) as exc:
        if isinstance(exc, ObserwatorCancelledError) or (
            cancel is not None and cancel()
        ):
            return _result(item, "cancelled", error=CANCELLED)
        if on_notice is not None:
            on_notice(
                Notice(
                    "warning", "archive_failed", f"{item.archive.server_path}: {exc}"
                )
            )
        return _result(
            item,
            "failed",
            error=reason(exc),
            error_code=exc.code if isinstance(exc, ObserwatorError) else "io_error",
        )
    return _result(item, written.status, version=written.path)
