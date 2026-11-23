"""Per-station Parquet snapshots ``obserwator-series/1`` built from current archive versions."""

from __future__ import annotations

import hashlib
import json
import math
import os
import pickle
import re
import shutil
import socket
import tempfile
import uuid
import zlib
from collections import defaultdict
from collections.abc import Callable, Collection, Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path, PurePosixPath
from typing import Any, Final, Literal

from obserwator._parsing import CARRY_DATASETS, normalize_in_sequence
from obserwator._version import __version__
from obserwator.attribution import Attribution, attribution, dataset_origin
from obserwator.datasets import (
    STATION_CODE_PATTERN,
    ArchiveFile,
    DatasetDescriptor,
    YearsArg,
    _archive_from_path,
    _license_document,
    datasets,
    get_dataset,
    get_provider,
    parse_years,
    resolve_dataset_key,
)
from obserwator.exceptions import (
    ObserwatorDataError,
    ObserwatorError,
    ObserwatorStoreConflictError,
    ObserwatorStoreDependencyError,
    ObserwatorValidationError,
    io_error,
)
from obserwator.messages import message, reason
from obserwator.models import Flag, Measurement, NormalizedRecord
from obserwator.store.content import stored_form
from obserwator.store.types import (
    Cancel,
    Notice,
    NoticeHook,
    PathArg,
    PlanAction,
    PlanItem,
    Progress,
    ProgressHook,
    SeriesReport,
    SeriesSubset,
    StationCoverage,
    StoreHandle,
    StorePlan,
)
from obserwator.store.writer import (
    _archive_slot_dir,
    _canonical,
    _canonical_text,
    _cleanup,
    _fsync_dir,
    _is_register,
    _publish_dir,
    _utc,
    _validate_slot,
    _write_json,
    lenient_store,
    prepare_store,
    refuse_root,
    root_conflict_plan,
    version_file,
)

SERIES_SCHEMA: Final = "obserwator-series/1"
SeriesState = Literal["current", "outdated", "missing"]

_FLAGS = ("value", "missing", "no_phenomenon", "accumulated")
_PERIODS = ("winter", "summer", "annual")
_SHA = re.compile(r"^[0-9a-f]{64}$")
_INT8 = range(-128, 128)
_CANCELLED = message("common.cancelled")
_CHUNK = 1024 * 1024
_STATION_CODE = re.compile(STATION_CODE_PATTERN)
# Closed range of days, both ends included.
_Span = tuple[date, date]


@dataclass(frozen=True)
class _Version:
    """One immutable archive version read from its sidecar (contents not re-hashed)."""

    slot: str
    file: Path
    relative: str
    meta: Mapping[str, Any]

    @property
    def sha256(self) -> str:
        return str(self.meta["sha256"])

    @property
    def label(self) -> str:
        return str(self.meta["extra"]["version"]["label"])

    @property
    def http(self) -> Mapping[str, Any]:
        return self.meta["extra"].get("http") or {}


@dataclass(frozen=True)
class _Input:
    archive: ArchiveFile
    version: _Version


def _raw(raw_root: PathArg | StoreHandle) -> Path:
    """
    The raw root a build reads: opened with the reader's helper, so nothing is written.

    No marker is created or completed and no staging directory is made or
    cleaned there, so a read-only raw root works (ADR-017 D4).

    Raises
    ------
    ObserwatorStoreError
        Code ``store_unavailable``: the raw root is missing (with the hint of
        ``store sync`` and ``store init``), no supported root, or a data root
        (``details.reason`` ``wrong_root``).
    """
    from obserwator.store.reader import _open  # the reader imports this module

    return _open(raw_root, kind="raw")


def _series_descriptor(dataset: str) -> DatasetDescriptor:
    descriptor = get_dataset(dataset)
    allowed = [
        item.key
        for item in datasets()
        if item.in_store and item.time_unit in ("day", "month", "half_year")
    ]
    if descriptor.key not in allowed:
        raise ObserwatorValidationError(
            message(
                "series.dataset_does_not_build_measurement",
                dataset=dataset,
                allowed=", ".join(allowed),
            ),
            details={"option": "dataset", "value": dataset, "allowed": allowed},
        )
    return descriptor


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return parsedate_to_datetime(value).astimezone(UTC)
    except (TypeError, ValueError, OverflowError):
        return None


def _downloaded(meta: Mapping[str, Any]) -> datetime:
    return datetime.fromisoformat(str(meta["downloaded_at"]).replace("Z", "+00:00"))


def _read_versions(root: Path, slot: str, name: str) -> list[_Version]:
    """
    Read every sidecar of an archive slot; a broken version is an explicit error.

    The slot's observation register ``observations/`` is not a version, and
    neither is a version directory without the sidecar (an interrupted
    publication).
    """
    directory = _validate_slot(root, slot)
    if not directory.exists():
        return []
    versions = []
    for version_dir in sorted(directory.iterdir()):
        if _is_register(version_dir):
            continue
        meta_path = version_dir / f"{name}.meta.json"
        main = version_dir / name
        if (
            version_dir.is_dir()
            and not version_dir.is_symlink()
            and not meta_path.exists()
            and not meta_path.is_symlink()
        ):
            continue
        try:
            if (
                version_dir.is_symlink()
                or not version_dir.is_dir()
                or main.is_symlink()
                or meta_path.is_symlink()
            ):
                raise ValueError(message("series.link_file_instead_version_directory"))
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            if meta["schema"] != "obserwator-meta/1" or not main.is_file():
                raise ValueError(message("series.unknown_schema_no_main_file"))
            if not isinstance(meta["sha256"], str) or not isinstance(
                meta["extra"]["version"]["label"], str
            ):
                raise ValueError(message("series.no_checksum_label_version"))
            _content_fields(meta)
            _downloaded(meta)
        except (FileNotFoundError, ValueError, KeyError, TypeError) as exc:
            raise ObserwatorDataError(
                message(
                    "series.corrupt_archive_version",
                    version_dir=version_dir.relative_to(root).as_posix(),
                    exc=reason(exc),
                )
            ) from exc
        except OSError as exc:
            raise io_error(exc) from exc
        versions.append(_Version(slot, main, main.relative_to(root).as_posix(), meta))
    return versions


def _pick_current(versions: Iterable[_Version]) -> _Version | None:
    """Newest Last-Modified (fallback downloaded_at), then downloaded_at, then path."""

    def key(version: _Version) -> tuple[datetime, datetime, str]:
        downloaded = _downloaded(version.meta)
        return (
            _parse_time(version.http.get("last_modified")) or downloaded,
            downloaded,
            version.relative,
        )

    return max(versions, key=key, default=None)


def _current_version(root: Path, archive: ArchiveFile) -> _Version | None:
    return _pick_current(
        _read_versions(
            root,
            _archive_slot_dir(archive.server_path),
            PurePosixPath(archive.server_path).name,
        )
    )


def _content_fields(meta: Mapping[str, Any]) -> dict[str, str]:
    """
    ``content_sha256`` and ``content_form`` of a sidecar: both or none (ADR-003 D17).

    A form renamed since the sidecar was written is given by its current
    identifier (ADR-028).
    """
    fields = {
        key: meta[key] for key in ("content_sha256", "content_form") if key in meta
    }
    if fields and not (
        len(fields) == 2
        and isinstance(fields["content_sha256"], str)
        and _SHA.fullmatch(fields["content_sha256"])
        and isinstance(fields["content_form"], str)
        and fields["content_form"]
    ):
        raise ValueError(message("series.invalid_pair_content_sha256_content"))
    if fields:
        fields["content_form"] = stored_form(fields["content_form"])
    return fields


def _restore_archive(dataset: str, meta: Mapping[str, Any]) -> ArchiveFile:
    """Registry `ArchiveFile` of a stored version, consistent with its ``request``."""
    request = meta["request"]
    server_path = request["server_path"]
    archive = (
        _archive_from_path(dataset, server_path)
        if isinstance(server_path, str)
        else None
    )
    if archive is None:
        raise ValueError(
            message(
                "series.path_does_not_belong_dataset",
                server_path=server_path,
                dataset=dataset,
            )
        )
    for key in ("year", "month", "station_code", "param"):
        if key in request and request[key] != getattr(archive, key):
            raise ValueError(
                message(
                    "series.request_does_not_match_path",
                    key=key,
                    server_path=server_path,
                )
            )
    return archive


def _scan_inputs(
    root: Path, descriptor: DatasetDescriptor
) -> tuple[list[_Input], list[str]]:
    """Current version of every archive slot of a dataset, plus unreadable slots."""
    assert descriptor.server_dir is not None
    base = root / "archives" / "versions" / PurePosixPath(descriptor.server_dir)
    if not base.exists():
        return [], []
    slots: dict[Path, str] = {}
    for sidecar in base.rglob("*.meta.json"):
        slots.setdefault(sidecar.parent.parent, sidecar.name.removesuffix(".meta.json"))
    inputs: list[_Input] = []
    problems: list[str] = []
    for slot_dir in sorted(slots):
        slot = slot_dir.relative_to(root).as_posix()
        try:
            current = _pick_current(_read_versions(root, slot, slots[slot_dir]))
            if current is None:
                continue
            # A raw root written before a dataset was renamed holds its old key
            # (ADR-028).
            stored = current.meta.get("dataset")
            if not isinstance(stored, str) or resolve_dataset_key(stored) != (
                descriptor.key
            ):
                raise ObserwatorDataError(
                    message(
                        "series.version_belongs_another_dataset",
                        relative=current.relative,
                    )
                )
            archive = _restore_archive(descriptor.key, current.meta)
            if _archive_slot_dir(archive.server_path) != slot:
                raise ObserwatorDataError(
                    message(
                        "series.version_does_not_match_slot",
                        relative=current.relative,
                        slot=slot,
                    )
                )
        except (ObserwatorError, ValueError, KeyError, TypeError) as exc:
            problems.append(reason(exc))
            continue
        inputs.append(_Input(archive, current))
    inputs.sort(key=lambda item: item.version.slot)
    return inputs, problems


def _manifest(inputs: Iterable[_Input]) -> tuple[tuple[str, str], ...]:
    return tuple(sorted((item.version.slot, item.version.sha256) for item in inputs))


def _subset(
    descriptor: DatasetDescriptor,
    stations: Iterable[str] | None,
    years: YearsArg | None,
) -> SeriesSubset | None:
    """
    The validated subset of a build (ADR-026): sorted codes and years, or None.

    Raises
    ------
    ObserwatorValidationError
        If ``stations`` is a text, no collection or empty, or holds a code
        outside the grammar of the dataset's provider (``details.option``
        ``stations``), or if ``years`` is invalid (``years``).
    """
    if stations is None and years is None:
        return None
    codes: tuple[str, ...] | None = None
    if stations is not None:
        if isinstance(stations, str) or not isinstance(stations, Iterable):
            raise ObserwatorValidationError(
                message("series.stations_not_list"),
                details={"option": "stations", "value": str(stations)},
            )
        given = list(stations)
        if not given:
            raise ObserwatorValidationError(
                message("series.stations_not_list"),
                details={"option": "stations", "value": given},
            )
        provider = get_provider(descriptor.provider)
        pattern = re.compile(provider.station_code_pattern)
        foreign = [
            str(code)
            for code in given
            if not (isinstance(code, str) and pattern.fullmatch(code))
        ]
        if foreign:
            raise ObserwatorValidationError(
                message(
                    "series.stations_outside_grammar",
                    provider=provider.short_name,
                    key=descriptor.key,
                    codes=", ".join(foreign),
                    pattern=provider.station_code_pattern,
                ),
                details={"option": "stations", "value": foreign},
            )
        codes = tuple(sorted(set(given)))
    return SeriesSubset(codes, None if years is None else parse_years(years))


def _subset_document(subset: SeriesSubset | None) -> dict[str, Any]:
    """``subset`` of ``series.json`` and the request of the sidecar: the given keys."""
    if subset is None:
        return {}
    document: dict[str, Any] = {}
    if subset.stations is not None:
        document["stations"] = list(subset.stations)
    if subset.years is not None:
        document["years"] = list(subset.years)
    return document


def _document_subset(value: object) -> SeriesSubset | None:
    """
    The ``subset`` of a ``series.json`` document, or None for a full series.

    Raises
    ------
    ValueError
        If it is no object with ``stations`` (sorted, distinct station codes)
        and/or ``years`` (sorted, distinct years 1-9999), each non-empty.
    """
    if value is None:
        return None
    if not (isinstance(value, dict) and value and set(value) <= {"stations", "years"}):
        raise ValueError(message("series.invalid_subset"))
    stations, years = value.get("stations"), value.get("years")
    if stations is not None and not (
        isinstance(stations, list)
        and stations
        and all(
            isinstance(code, str) and _STATION_CODE.fullmatch(code) for code in stations
        )
        and stations == sorted(set(stations))
    ):
        raise ValueError(message("series.invalid_subset"))
    if years is not None and not (
        isinstance(years, list)
        and years
        and all(type(year) is int and 1 <= year <= 9999 for year in years)
        and years == sorted(set(years))
    ):
        raise ValueError(message("series.invalid_subset"))
    return SeriesSubset(
        None if stations is None else tuple(stations),
        None if years is None else tuple(years),
    )


@dataclass(frozen=True)
class _SeriesVersion:
    path: Path
    meta: Mapping[str, Any]
    manifest: tuple[tuple[str, str], ...]
    lines: Attribution = Attribution()
    subset: SeriesSubset | None = None


def _series_versions(root: Path, descriptor: DatasetDescriptor) -> list[_SeriesVersion]:
    """Readable series versions of a dataset; unverifiable ones are never reused."""
    base = root / "series" / "versions" / descriptor.slug
    if not base.exists():
        return []
    result = []
    for directory in sorted(base.iterdir()):
        main = directory / "series.json"
        try:
            if directory.is_symlink() or main.is_symlink():
                continue
            meta = json.loads(
                (directory / "series.json.meta.json").read_text(encoding="utf-8")
            )
            extra = meta["extra"]
            content = main.read_bytes()
            if (
                meta["schema"] != "obserwator-meta/1"
                or extra.get("series_schema") != SERIES_SCHEMA
                or hashlib.sha256(content).hexdigest() != meta["sha256"]
            ):
                continue
            manifest = tuple(
                sorted(
                    (
                        PurePosixPath(source["file"]).parent.parent.as_posix(),
                        source["sha256"],
                    )
                    for source in extra["source_files"]
                )
            )
            _downloaded(meta)
            document = json.loads(content)
            lines = Attribution(
                tuple(document.get("attribution", ())),
                tuple(document.get("terms_notice", ())),
            )
            subset = _document_subset(document.get("subset"))
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            continue
        result.append(_SeriesVersion(main, meta, manifest, lines, subset))
    return result


def _reusable(
    version: _SeriesVersion,
    manifest: tuple[tuple[str, str], ...],
    descriptor: DatasetDescriptor,
    subset: SeriesSubset | None,
) -> bool:
    """
    Whether a series version stays current: the same inputs, lines and subset.

    A version written before the series carried the provider's attribution
    lines (ADR-012) is rebuilt once, so the store's products carry them; one whose
    CP names the processing (before ECO-071) stays current, as it holds CP. A
    subset is never the full series, nor another subset (ADR-026).
    """
    return (
        version.manifest == manifest
        and version.lines == _lines(descriptor)
        and version.subset == subset
    )


def _current_series(versions: Iterable[_SeriesVersion]) -> _SeriesVersion | None:
    """Current series version: newest ``downloaded_at`` (build time), then path."""
    return max(
        versions,
        key=lambda item: (_downloaded(item.meta), item.path.as_posix()),
        default=None,
    )


def _full_series(versions: Iterable[_SeriesVersion]) -> _SeriesVersion | None:
    """The newest version of every station and year, which a subset never joins."""
    return _current_series(version for version in versions if version.subset is None)


def _beside_full(
    root: Path, descriptor: DatasetDescriptor, full: _SeriesVersion
) -> ObserwatorStoreConflictError:
    """The refusal of a subset in a data root that holds the full series (ADR-026)."""
    version = full.path.parent.relative_to(root).as_posix()
    return ObserwatorStoreConflictError(
        message(
            "series.subset_beside_full_series", key=descriptor.key, version=version
        ),
        details={"reason": "full_series", "version": version},
    )


def _series_state(
    root: Path,
    descriptor: DatasetDescriptor,
    inputs: list[_Input],
    subset: SeriesSubset | None,
    *,
    reliable: bool = True,
) -> SeriesState:
    current = _current_series(_series_versions(root, descriptor))
    if current is None:
        return "missing"
    return (
        "current"
        if reliable and _reusable(current, _manifest(inputs), descriptor, subset)
        else "outdated"
    )


def _year_span(year: int, descriptor: DatasetDescriptor) -> _Span:
    """The days of a year in the numbering of the dataset (``year_type``)."""
    if descriptor.year_type == "hydrological":
        return date(year - 1, 11, 1) if year > 1 else date.min, date(year, 10, 31)
    return date(year, 1, 1), date(year, 12, 31)


def _windows(
    descriptor: DatasetDescriptor, subset: SeriesSubset | None
) -> tuple[_Span, ...] | None:
    """The days of the chosen years, or None without a choice of years."""
    if subset is None or subset.years is None:
        return None
    return tuple(_year_span(year, descriptor) for year in subset.years)


def _cut(spans: Iterable[_Span], windows: Sequence[_Span] | None) -> list[_Span]:
    """The parts of ``spans`` within ``windows``; every span without windows."""
    if windows is None:
        return list(spans)
    return [
        (max(start, low), min(end, high))
        for start, end in spans
        for low, high in windows
        if start <= high and low <= end
    ]


def _read_inputs(
    inputs: list[_Input], descriptor: DatasetDescriptor, subset: SeriesSubset | None
) -> list[_Input]:
    """
    The inputs a build of ``subset`` reads, in slot order (ADR-026).

    Without a subset every input. Otherwise the archives whose period meets a
    chosen year (a file without a period, a ČHMÚ station's whole record,
    always) and, of the files of one station, those of the chosen stations:
    a ČHMÚ file by its station code, an IMGW-PIB synop file by the station
    number (the last three digits of a code); a file of the whole country
    holds every station. Of a dataset whose archives leave something to the
    next (`CARRY_DATASETS`: the missing days of IMGW-PIB's precipitation,
    `normalize_in_sequence`'s ``carry``) the archive before a chosen one is
    read too; its own records lie outside the chosen years.
    """
    if subset is None:
        return inputs
    windows = _windows(descriptor, subset)
    codes = frozenset(subset.stations or ())
    adapter = get_provider(descriptor.provider).adapter
    numbers = frozenset(adapter.station_key(code) for code in codes)

    def chosen(archive: ArchiveFile) -> bool:
        start, end = archive.period_start, archive.period_end
        if (
            windows is not None
            and start is not None
            and end is not None
            and not any(start <= high and low <= end for low, high in windows)
        ):
            return False
        if subset.stations is None or descriptor.archive_scope == "country":
            return True
        if archive.station_code is not None:
            return archive.station_code in codes
        station = adapter.archive_station(archive)
        return station is None or station in numbers

    picked = {index for index, item in enumerate(inputs) if chosen(item.archive)}
    if descriptor.key in CARRY_DATASETS and windows is not None:
        picked |= {index - 1 for index in picked if index > 0}
    return [inputs[index] for index in sorted(picked)]


def check_series(
    root: PathArg | StoreHandle,
    /,
    *,
    raw_root: PathArg | StoreHandle,
    dataset: str,
    stations: Iterable[str] | None = None,
    years: YearsArg | None = None,
    on_progress: ProgressHook | None = None,
    on_notice: NoticeHook | None = None,
    cancel: Cancel | None = None,
) -> StorePlan:
    """
    Report offline what :func:`build_series` would read and the series state.

    Reads only local sidecars of both roots; no network access and no writes.

    Parameters
    ----------
    root : str, os.PathLike or StoreHandle
        Data root the series would be written to (ADR-017); it need not exist.
    raw_root : str, os.PathLike or StoreHandle
        Raw root whose current archive versions the build reads; only read.
    dataset : str
        Full key (``pl.imgw.*`` or ``cz.chmu.*``) of a measurement series
        dataset.
    stations : iterable of str or None, optional
        The stations of a subset, as in :func:`build_series`.
    years : YearsArg or None, optional
        The years of a subset, as in :func:`build_series`.
    on_progress : ProgressHook or None, optional
        Called for each current input archive.
    on_notice : NoticeHook or None, optional
        Receives an ``archive_failed`` error for every unreadable archive slot.
    cancel : Cancel or None, optional
        Polled before each input; once it returns ``True`` the remaining inputs are
        listed as ``unverifiable`` with error ``"cancelled"``.

    Returns
    -------
    StorePlan
        Plan of the data root whose items are the current input archive
        versions the build reads (status ``current``, ``local_path`` relative
        to the raw root, HTTP signals copied from their sidecars, the station
        of a per-station file in ``station_code``), whose ``series_state`` maps
        the dataset slug to ``current``, ``outdated`` or ``missing``, and whose
        ``series build`` actions carry the series status (``current``,
        ``newer`` for an outdated series, or ``missing``), one
        ``check_failed`` action per unreadable slot and a ``missing`` action
        when the raw root holds no archive of the dataset (or of the subset).
        A subset that the data root refuses beside the full series of the
        dataset gives a plan of one ``conflict`` action (``reason``
        ``full_series``, ``path`` that version) and nothing else.

    Raises
    ------
    ObserwatorStoreError
        Code ``store_unavailable`` if ``root`` is no data root that may be
        written or ``raw_root`` is missing or no raw root (``details.reason``
        ``wrong_root`` for a root of the other kind).
    ObserwatorValidationError
        If ``dataset`` is unknown or does not produce measurement series, or
        ``stations`` or ``years`` is invalid.
    """
    descriptor = _series_descriptor(dataset)
    subset = _subset(descriptor, stations, years)
    refused = root_conflict_plan("series build", root, kind="data")
    if refused is not None:
        return refused
    path = lenient_store(root, kind="data").root
    raw = _raw(raw_root)
    if subset is not None:
        full = _full_series(_series_versions(path, descriptor))
        if full is not None:
            action = PlanAction(
                "series build",
                "unverifiable",
                _beside_full(path, descriptor, full).detail,
                action="conflict",
                path=full.path.parent,
                reason="full_series",
            )
            return StorePlan(
                "obserwator-plan/1", path, datetime.now(UTC), (), {}, (action,)
            )
    inputs, problems = _scan_inputs(raw, descriptor)
    read = _read_inputs(inputs, descriptor, subset)
    items: list[PlanItem] = []
    cancelled = False
    for index, item in enumerate(read, start=1):
        if not cancelled and cancel is not None and cancel():
            cancelled = True
        http = item.version.http
        items.append(
            PlanItem(
                archive=item.archive,
                status="unverifiable" if cancelled else "current",
                local_path=Path(item.version.relative),
                local_sha256=item.version.sha256,
                remote_etag=http.get("etag"),
                remote_last_modified=http.get("last_modified"),
                content_length=http.get("content_length"),
                error=_CANCELLED if cancelled else None,
                station_code=item.archive.station_code,
            )
        )
        if on_progress is not None and not cancelled:
            on_progress(
                Progress(
                    index,
                    len(read),
                    "archive",
                    "current",
                    message("series.input_progress", relative=item.version.relative),
                )
            )
    state = _series_state(path, descriptor, read, subset, reliable=not problems)
    detail = {
        "current": message("series.series_current", slug=descriptor.slug),
        "outdated": message("series.series_needs_rebuild", slug=descriptor.slug),
        "missing": message("series.series_missing", slug=descriptor.slug),
    }[state]
    action_status: dict[SeriesState, Literal["current", "newer", "missing"]] = {
        "current": "current",
        "outdated": "newer",
        "missing": "missing",
    }
    actions = [PlanAction("series build", action_status[state], detail)]
    for problem in problems:
        actions.append(PlanAction("series build", "check_failed", problem))
        if on_notice is not None:
            on_notice(Notice("warning", "archive_failed", problem))
    if not read:
        actions.append(
            PlanAction(
                "series build",
                "missing",
                message("series.no_archives_of_dataset", dataset=dataset)
                if not inputs
                else message("series.no_archives_of_subset", key=descriptor.key),
            )
        )
    return StorePlan(
        schema="obserwator-plan/1",
        root=path,
        checked_at=datetime.now(UTC),
        items=tuple(items),
        series_state={descriptor.slug: state},
        actions=tuple(actions),
        cancelled=cancelled,
    )


def _pyarrow() -> tuple[Any, Any]:
    try:
        import pyarrow
        import pyarrow.parquet
    except ImportError as exc:
        raise ObserwatorStoreDependencyError(
            message(
                "series.building_parquet_series_needs_package",
                install=message("errors.store_extra"),
            )
        ) from exc
    if int(pyarrow.__version__.split(".")[0]) < 15:
        raise ObserwatorStoreDependencyError(
            message(
                "series.pyarrow_15_required_version_installed",
                version=pyarrow.__version__,
                install=message("errors.store_extra"),
            )
        )
    return pyarrow, pyarrow.parquet


def _hydro_year(day: date) -> int:
    return day.year + 1 if day.month >= 11 else day.year


def _next_month(day: date) -> date:
    return date(day.year + (day.month == 12), day.month % 12 + 1, 1)


def _period_start(hydro_year: int, period: str) -> date:
    return date(hydro_year, 5, 1) if period == "summer" else date(hydro_year - 1, 11, 1)


_Key = tuple[date, str | None]
# Flag, value, the sign bit (-0.0 == 0.0, but sharing must not change the sign),
# quality and source flag.
_Shared = dict[tuple[str, float | None, bool, int | None, str | None], Measurement]
# One spilled record: date ordinal, hydrological year, period, then the
# (variable, value, flag, quality, source flag), (variable, (start, end)) and
# (variable, occurrences) entries of its measurements, extremum dates and
# extremum occurrence counts.
_Row = tuple[
    int,
    int,
    str | None,
    tuple[tuple[str, float | None, Flag, int | None, str | None], ...],
    tuple[tuple[str, tuple[datetime | None, datetime | None]], ...],
    tuple[tuple[str, int], ...],
]
# Records queued in memory before they are appended to the station files.
_SPILL_ROWS = 200_000


@dataclass
class _Station:
    values: dict[_Key, dict[str, Measurement]]
    extrema: dict[_Key, dict[str, tuple[datetime | None, datetime | None]]]
    occurrences: dict[_Key, dict[str, int]]
    hydro_years: set[int]


def _shared(
    shared: _Shared,
    value: float | None,
    flag: Flag,
    quality: int | None,
    source_flag: str | None,
) -> Measurement:
    """One object per distinct measurement of a station, keeping the sign of zero."""
    key = (
        flag,
        value,
        value is not None and math.copysign(1.0, value) < 0,
        quality,
        source_flag,
    )
    measurement = shared.get(key)
    if measurement is None:
        measurement = Measurement(value, flag, quality, source_flag)
        if value == value:  # NaN never matches its key, caching it would only grow
            shared[key] = measurement
    return measurement


def _collect(
    station: _Station,
    code: str,
    row: _Row,
    descriptor: DatasetDescriptor,
    shared: _Shared,
) -> None:
    """Fold one spilled record into its station; conflicting values raise."""
    ordinal, hydro_year, period, measurements, extrema, occurrences = row
    day = date.fromordinal(ordinal)
    key = (day, period if descriptor.time_unit == "half_year" else None)
    columns = station.values.setdefault(key, {})
    for variable, value, flag, quality, source_flag in measurements:
        measurement = _shared(shared, value, flag, quality, source_flag)
        previous = columns.get(variable)
        if previous is not None and previous != measurement:
            raise ObserwatorDataError(
                message(
                    "series.conflicting_values_station",
                    variable=variable,
                    code=code,
                    day=day,
                )
            )
        columns[variable] = measurement
    for variable, bounds in extrema:
        dates = station.extrema.setdefault(key, {})
        if dates.get(variable, bounds) != bounds:
            raise ObserwatorDataError(
                message(
                    "series.conflicting_dates_extremum_station",
                    variable=variable,
                    code=code,
                )
            )
        dates[variable] = bounds
    for variable, count in occurrences:
        counts = station.occurrences.setdefault(key, {})
        if counts.get(variable, count) != count:
            raise ObserwatorDataError(
                message(
                    "series.conflicting_number_occurrences_extremum_station",
                    variable=variable,
                    code=code,
                )
            )
        counts[variable] = count
    station.hydro_years.add(hydro_year)


class _Spill:
    """
    Parsed records grouped by station in temporary files outside the store.

    Records are validated while parsing and appended in compressed chunks to
    one file per station, so memory holds at most ``_SPILL_ROWS`` queued
    records instead of the values of the whole dataset; every station is then
    assembled alone, in the order its records were parsed.
    """

    def __init__(self, directory: Path, descriptor: DatasetDescriptor) -> None:
        self._directory = directory
        self._descriptor = descriptor
        self._code = re.compile(get_provider(descriptor.provider).station_code_pattern)
        self._quality = "quality" in descriptor.measurement_fields
        self._source_flag = "source_flag" in descriptor.measurement_fields
        self._queued: dict[str, list[_Row]] = {}
        self._count = 0
        self.stations: set[str] = set()

    def add(self, record: NormalizedRecord) -> None:
        """Validate one record and queue it for the file of its station."""
        code = record.station_code
        if code not in self.stations and not self._code.fullmatch(code):
            raise ObserwatorDataError(message("series.invalid_station_code", code=code))
        measurements: list[tuple[str, float | None, Flag, int | None, str | None]] = []
        for variable, measurement in record.measurements.items():
            if variable not in self._descriptor.variables:
                raise ObserwatorDataError(
                    message(
                        "series.unknown_variable_dataset",
                        variable=variable,
                        key=self._descriptor.key,
                    )
                )
            if (measurement.value is None) != (
                measurement.flag == "missing"
            ) or measurement.flag not in _FLAGS:
                raise ObserwatorDataError(
                    message(
                        "series.inconsistent_flag_variable_station",
                        flag=measurement.flag,
                        variable=variable,
                        code=code,
                    )
                )
            # Fields the dataset does not declare must stay empty: the Parquet
            # file has no column for them. Quality is stored as int8.
            quality, source_flag = measurement.quality, measurement.source_flag
            if not (
                quality is None
                or (self._quality and type(quality) is int and quality in _INT8)
            ) or not (
                source_flag is None
                or (self._source_flag and isinstance(source_flag, str))
            ):
                raise ObserwatorDataError(
                    message(
                        "series.disallowed_quality_source_flag_variable",
                        quality=quality,
                        source_flag=source_flag,
                        variable=variable,
                        code=code,
                        date=record.date,
                    )
                )
            measurements.append(
                (variable, measurement.value, measurement.flag, quality, source_flag)
            )
        self._queued.setdefault(code, []).append(
            (
                record.date.toordinal(),
                record.hydro_year,
                record.period,
                tuple(measurements),
                tuple(record.extrema_dates.items()),
                tuple(record.extrema_occurrences.items()),
            )
        )
        self.stations.add(code)
        self._count += 1
        if self._count >= _SPILL_ROWS:
            self.flush()

    def flush(self) -> None:
        """Append the queued records to their station files."""
        for code, rows in self._queued.items():
            chunk = zlib.compress(pickle.dumps(rows, pickle.HIGHEST_PROTOCOL), 1)
            with (self._directory / code).open("ab") as stream:
                stream.write(len(chunk).to_bytes(8, "little"))
                stream.write(chunk)
        self._queued.clear()
        self._count = 0

    def station(self, code: str) -> _Station:
        """Assemble one station from its file, then delete the file."""
        station = _Station({}, {}, {}, set())
        shared: _Shared = {}
        path = self._directory / code
        with path.open("rb") as stream:
            while header := stream.read(8):
                chunk = stream.read(int.from_bytes(header, "little"))
                rows: list[_Row] = pickle.loads(zlib.decompress(chunk))
                for row in rows:
                    _collect(station, code, row, self._descriptor, shared)
        path.unlink()
        return station


def _row_keys(station: _Station, time_unit: str) -> list[tuple[_Key, int]]:
    """Every unit of the continuous station calendar, with its hydrological year."""
    if time_unit == "half_year":
        return [
            ((_period_start(year, period), period), year)
            for year in sorted(station.hydro_years)
            for period in _PERIODS
        ]
    days = sorted(day for day, _ in station.values)
    keys: list[tuple[_Key, int]] = []
    current, last = days[0], days[-1]
    while current <= last:
        keys.append(((current, None), _hydro_year(current)))
        current = (
            current + timedelta(days=1) if time_unit == "day" else _next_month(current)
        )
    return keys


def _station_table(pa: Any, station: _Station, descriptor: DatasetDescriptor) -> Any:
    keys = _row_keys(station, descriptor.time_unit)
    flags = pa.array(_FLAGS, pa.string())
    columns: dict[str, Any] = {
        "date": pa.array([key[0] for key, _ in keys], pa.date32()),
        "hydro_year": pa.array([year for _, year in keys], pa.int32()),
    }
    if descriptor.time_unit == "half_year":
        columns["period"] = pa.DictionaryArray.from_arrays(
            pa.array([_PERIODS.index(key[1]) for key, _ in keys], pa.int8()),
            pa.array(_PERIODS, pa.string()),
        )
    missing = Measurement(None, "missing")
    for variable in descriptor.variables:
        measurements = [
            station.values.get(key, {}).get(variable, missing) for key, _ in keys
        ]
        columns[f"{variable}_value"] = pa.array(
            [item.value for item in measurements], pa.float64()
        )
        columns[f"{variable}_flag"] = pa.DictionaryArray.from_arrays(
            pa.array([_FLAGS.index(item.flag) for item in measurements], pa.int8()),
            flags,
        )
        # ČHMÚ meteo: QUALITY as published and FLAG verbatim, both nullable.
        if "quality" in descriptor.measurement_fields:
            columns[f"{variable}_quality"] = pa.array(
                [item.quality for item in measurements], pa.int8()
            )
        if "source_flag" in descriptor.measurement_fields:
            columns[f"{variable}_source_flag"] = pa.array(
                [item.source_flag for item in measurements], pa.string()
            ).dictionary_encode()
        if descriptor.time_unit == "half_year":
            bounds = [
                station.extrema.get(key, {}).get(variable, (None, None))
                for key, _ in keys
            ]
            columns[f"{variable}_start"] = pa.array(
                [start for start, _ in bounds], pa.timestamp("us")
            )
            columns[f"{variable}_end"] = pa.array(
                [end for _, end in bounds], pa.timestamp("us")
            )
            columns[f"{variable}_occurrences"] = pa.array(
                [station.occurrences.get(key, {}).get(variable) for key, _ in keys],
                pa.int32(),
            )
    metadata = {
        "obserwator_schema": SERIES_SCHEMA,
        "dataset": descriptor.key,
        "units": _canonical_text(dict(descriptor.variables)),
    }
    if descriptor.variable_notes:
        metadata["variable_notes"] = _canonical_text(dict(descriptor.variable_notes))
    # The lines of the provider as JSON arrays (ADR-012, Nogat DEV-20.5).
    metadata.update(
        (name, _canonical_text(value))
        for name, value in _lines(descriptor).fields().items()
    )
    return pa.table(columns).replace_schema_metadata(metadata)


def _lines(descriptor: DatasetDescriptor) -> Attribution:
    """The lines of a series: data parsed, harmonised and reformatted (ADR-012)."""
    return attribution(dataset_origin(descriptor.key))


def _archive_span(archive: ArchiveFile) -> tuple[date, date]:
    """Exact publication period of a dated archive."""
    assert archive.period_start is not None and archive.period_end is not None
    return archive.period_start, archive.period_end


def _iso_spans(spans: Iterable[tuple[date, date]]) -> list[list[str]]:
    """``series.json`` form of closed date ranges."""
    return [[start.isoformat(), end.isoformat()] for start, end in spans]


def _spill_station_file(
    spill: _Spill,
    archive: ArchiveFile,
    records: Iterable[NormalizedRecord],
    spans: dict[str, list[tuple[date, date]]],
    superseded: Collection[tuple[str, int]] = (),
    *,
    kept: Callable[[NormalizedRecord], bool] | None = None,
    subset: SeriesSubset | None = None,
    windows: Sequence[_Span] | None = None,
) -> None:
    """
    Spill the records of one per-station file and add its known period.

    A station-year file covers its calendar year (``extra.period``); a
    station-element file the days from its first to its last record, explicit
    missing rows included (ADR-003 D10). A record of another station than
    the file's is a data error. A file without a station code (the synop
    archives of IMGW-PIB, named by the station's number, and the running
    year's monthly files of the whole country) covers its period for every
    station it holds; a record whose station number and year are in
    ``superseded`` is left out. A subset (ADR-026) spills only the records
    ``kept`` takes, and gives its stations the known periods cut to the
    ``windows`` of its years.
    """
    code = archive.station_code
    key = get_provider(get_dataset(archive.dataset).provider).adapter.station_key
    bounds: dict[str, list[date]] = {}
    for record in records:
        if code is not None and record.station_code != code:
            raise ObserwatorDataError(
                message(
                    "series.record_station_file_station",
                    station_code=record.station_code,
                    code=code,
                    server_path=archive.server_path,
                )
            )
        if (key(record.station_code), record.date.year) in superseded:
            continue
        if kept is None or kept(record):
            spill.add(record)
        span = bounds.setdefault(record.station_code, [record.date, record.date])
        span[0], span[1] = min(span[0], record.date), max(span[1], record.date)
    stations: dict[str, list[date] | None] = (
        dict(bounds) if code is None else {code: bounds.get(code)}
    )
    for station, days in stations.items():
        if (
            subset is not None
            and subset.stations is not None
            and station not in subset.stations
        ):
            continue
        if archive.period_start is not None and archive.period_end is not None:
            spans[station].extend(_cut([_archive_span(archive)], windows))
        elif days is not None:
            spans[station].extend(_cut([(days[0], days[1])], windows))


def _superseded(inputs: Iterable[_Input]) -> set[tuple[str, int]]:
    """
    The station numbers and years of the stored synop archives of IMGW-PIB.

    The running year's monthly files of the whole country stand for the
    station archives of that year until IMGW-PIB publishes them; a station's
    archive of a year, once stored, supersedes the station's records of the
    year in those files (ADR-022).
    """
    covered: set[tuple[str, int]] = set()
    for item in inputs:
        archive = item.archive
        adapter = get_provider(get_dataset(archive.dataset).provider).adapter
        station = adapter.archive_station(archive)
        if station is None or archive.station_code is not None:
            continue
        assert archive.period_start is not None and archive.period_end is not None
        covered.update(
            (station, year)
            for year in range(archive.period_start.year, archive.period_end.year + 1)
        )
    return covered


def _coverage_index(coverage: Iterable[StationCoverage]) -> dict[str, dict[str, Any]]:
    """``series.json`` variables of one station, keyed ``<variable>[@<period>]``."""
    return {
        (
            entry.variable
            if entry.period is None
            else f"{entry.variable}@{entry.period}"
        ): {
            "unit": entry.unit,
            "first": entry.first.isoformat() if entry.first else None,
            "last": entry.last.isoformat() if entry.last else None,
            "with_value": entry.with_value,
            "accumulated": entry.accumulated,
            "gaps": [[start.isoformat(), end.isoformat()] for start, end in entry.gaps],
        }
        for entry in coverage
    }


def _candidate_labels(
    label: str, manifest: tuple[tuple[str, str], ...], *, attempts: int
) -> Iterator[str]:
    """Version labels to try in order: ``label``, then stable ``+<8 hex>`` variants."""
    pairs = [list(pair) for pair in manifest]
    yield label
    for attempt in range(1, attempts):
        salt: object = pairs if attempt == 1 else [pairs, attempt]
        yield f"{label}+{hashlib.sha256(_canonical(salt)).hexdigest()[:8]}"


def _copy_hashed(source: Path, target: Path) -> str:
    digest = hashlib.sha256()
    with source.open("rb") as reader, target.open("xb") as writer:
        for chunk in iter(lambda: reader.read(_CHUNK), b""):
            writer.write(chunk)
            digest.update(chunk)
        writer.flush()
        os.fsync(writer.fileno())
    return digest.hexdigest()


def _report(
    status: Literal["new", "unchanged", "cancelled", "failed"],
    *,
    version: Path | None = None,
    stations: int = 0,
    sources: Iterable[Path] = (),
    problems: Iterable[str] = (),
) -> SeriesReport:
    files = (
        (version_file(version, status),)
        if version is not None and status in ("new", "unchanged")
        else ()
    )
    return SeriesReport(
        status, version, stations, tuple(sources), tuple(problems), files
    )


def build_series(
    root: PathArg | StoreHandle,
    /,
    *,
    raw_root: PathArg | StoreHandle,
    dataset: str,
    stations: Iterable[str] | None = None,
    years: YearsArg | None = None,
    on_progress: ProgressHook | None = None,
    on_notice: NoticeHook | None = None,
    cancel: Cancel | None = None,
) -> SeriesReport:
    """
    Snapshot every station of the current archive versions as one series version.

    Reads exactly the current version of every archive slot of the dataset in
    the raw root and writes one Parquet file per station plus ``series.json``
    (``obserwator-series/1``) into the data root, published atomically as a new
    version (ADR-017). The raw root is only read: no marker, staging directory
    or cleanup there, so a read-only raw root works; the data root gets its
    marker with its first version. When the current series version (the
    newest build) was built from the same input manifest (slot and full SHA-256
    of every input) it is returned as ``unchanged`` without invoking the Parquet
    writer. An older version with that manifest (inputs reverted to earlier
    content) is never reused: a new version is built and becomes current. Parsed
    records are validated and spilled per station to compressed temporary files
    outside the roots (``tempfile``), then every station is assembled, written
    and covered alone, so memory stays bounded by one station and a queue of
    parsed records, not by the dataset. An unreadable input or conflicting
    values fail the whole build; an incomplete snapshot is never published.

    Datasets of per-station files (``cz.chmu.*``, ADR-003 D10) also record the
    known periods of every station in ``stations[<code>].periods``: the
    calendar years of its station-year files, or the first to last row of
    each station-element file, merged. Gaps are counted only on those days, so
    a year whose file is not published is unknown, not a gap; the dataset
    ``periods`` are the union of the station periods. Meteorological stations
    get the ``<V>_quality`` and ``<V>_source_flag`` Parquet columns, inputs of
    a dataset with a canonical form carry ``content_sha256`` and
    ``content_form`` in ``extra.source_files`` (whose ``file`` is relative to
    the raw root), and the sidecar names the provider of the dataset with its
    processed-data attribution.

    ``stations`` or ``years`` build a subset (ADR-026): only the archives that
    hold them are read (``source_files``; of IMGW-PIB's daily precipitation
    also the archive before a chosen one, for the missing days it leaves to
    the next), only their records are kept, the known periods are cut to the
    chosen years, and the rows of other stations in the daily and monthly
    archives of the whole country are skipped before their values are read.
    A station holds in a subset exactly the rows and coverage it has in the
    full series of the same inputs, within the chosen years. ``series.json``
    records the request as ``subset`` and the sidecar as ``request.stations``
    and ``request.years``; a version is reused only for the same subset, so a
    subset never stands for the full series nor the full series for a subset.
    A data root that holds a full version of the dataset refuses a subset
    (``conflict``, ``full_series``), so the current version of a dataset is
    never a subset beside its full series; a full build after a subset
    becomes current as any newer build.

    Parameters
    ----------
    root : str, os.PathLike or StoreHandle
        Data root the series version is written to; created with its marker
        when it is new or empty.
    raw_root : str, os.PathLike or StoreHandle
        Raw root whose current archive versions are read; never written.
    dataset : str
        Full key (``pl.imgw.*`` or ``cz.chmu.*``) of a measurement series
        dataset.
    stations : iterable of str or None, optional
        Build only these stations (codes of the dataset's provider; duplicates
        are merged). A station the archives read do not hold is named in a
        ``stations_missing`` warning. None builds every station.
    years : YearsArg or None, optional
        Build only these years: numbers or ranges in the numbering of the
        dataset (hydrological years, November to October, for the
        hydrological datasets of IMGW-PIB; calendar years otherwise). None
        builds every year.
    on_progress : ProgressHook or None, optional
        Called after each parsed archive and each written station file, or once
        for an unchanged version.
    on_notice : NoticeHook or None, optional
        Receives ``archive_failed`` errors for unreadable inputs, a
        ``leftover_incoming`` warning for every removed staging directory older
        than 24 hours, a ``stations_missing`` warning for chosen stations the
        archives read do not hold and the ``license_terms`` notice when a new
        version is created.
    cancel : Cancel or None, optional
        Polled between steps; once it returns ``True`` the build stops with a
        ``cancelled`` report and nothing is published.

    Returns
    -------
    SeriesReport
        Status ``new``, ``unchanged``, ``cancelled`` or ``failed``; ``version`` is
        the path of ``series.json``, ``source_files`` the absolute paths of the input
        archive versions in the raw root (for ``unchanged``, the inputs recorded
        in the existing current version's sidecar) and ``problems`` the reasons
        of a failure, also of a subset whose archives hold none of its
        stations and years.

    Raises
    ------
    ObserwatorStoreError
        Code ``store_unavailable`` if ``root`` is no supported data root or
        ``raw_root`` is missing or no raw root (``details.reason``
        ``wrong_root`` for a root of the other kind, e.g. a store not yet
        split used as the data root).
    ObserwatorValidationError
        If ``dataset`` is unknown or does not produce measurement series, or
        ``stations`` (``details.option`` ``stations``: no list, empty, or a
        code outside the grammar of the dataset's provider) or ``years`` is
        invalid.
    ObserwatorStoreDependencyError
        If ``pyarrow>=15`` is not installed.
    ObserwatorStoreConflictError
        If ``root`` nests a store (``details.reason`` ``nested_store``) or holds
        other files and is no store (``not_empty``), the version cannot be
        published atomically or its directory collides with a different
        version, or a subset is asked of a root that holds a full version of
        the dataset (``full_series``, ``details.version`` that version).
    """
    refuse_root(root, kind="data")
    path = lenient_store(root, kind="data").root
    raw = _raw(raw_root)
    descriptor = _series_descriptor(dataset)
    subset = _subset(descriptor, stations, years)
    pa, pq = _pyarrow()

    def cancelled() -> bool:
        return cancel is not None and cancel()

    if cancelled():
        return _report("cancelled")
    if subset is not None:
        full = _full_series(_series_versions(path, descriptor))
        if full is not None:
            raise _beside_full(path, descriptor, full)
    inputs, problems = _scan_inputs(raw, descriptor)
    if problems:
        for problem in problems:
            if on_notice is not None:
                on_notice(Notice("warning", "archive_failed", problem))
        return _report(
            "failed", sources=[item.version.file for item in inputs], problems=problems
        )
    if not inputs:
        return _report(
            "failed",
            problems=[message("series.no_archives_of_dataset", dataset=dataset)],
        )
    read = _read_inputs(inputs, descriptor, subset)
    if not read:
        return _report(
            "failed",
            problems=[message("series.no_archives_of_subset", key=descriptor.key)],
        )
    sources = [item.version.file for item in read]
    manifest = _manifest(read)
    current = _current_series(_series_versions(path, descriptor))
    if current is not None and _reusable(current, manifest, descriptor, subset):
        series = json.loads(current.path.read_text(encoding="utf-8"))
        recorded = [
            raw / PurePosixPath(source["file"])
            for source in current.meta["extra"]["source_files"]
        ]
        if on_progress is not None:
            on_progress(
                Progress(
                    1,
                    1,
                    "series",
                    "unchanged",
                    message("series.series_inputs_unchanged", slug=descriptor.slug),
                )
            )
        return _report(
            "unchanged",
            version=current.path,
            stations=len(series["stations"]),
            sources=recorded,
        )

    # Lazy import: obserwator.coverage imports store.types, which loads this package.
    from obserwator.coverage import (
        _KnownSpans,
        _KnownUnits,
        _merge_spans,
        _station_coverage,
    )

    known = _KnownUnits(descriptor.time_unit)
    # Per-station files (ČHMÚ, ADR-003 D10; the synop archives of IMGW-PIB,
    # ADR-022): known periods of every station.
    per_station = descriptor.archive_scope != "country"
    spans: dict[str, list[tuple[date, date]]] = defaultdict(list)
    superseded = _superseded(inputs) if per_station else set()
    # What an archive leaves to the next of the same dataset (missing days of IMGW-PIB
    # precipitation before a multi-day total): the inputs are in slot order, which is
    # date order for every IMGW-PIB folder (`1991_1995/1995_o`, `2024/2024_07_o`).
    carry: dict[str, date] = {}
    # A subset (ADR-026): the records it keeps, the days of its years, the rows the
    # parsers may skip and the months of the rows they skipped.
    windows = _windows(descriptor, subset)
    chosen = (
        None
        if subset is None or subset.stations is None
        else frozenset(subset.stations)
    )
    chosen_years = (
        None if subset is None or subset.years is None else frozenset(subset.years)
    )
    hydrological = descriptor.year_type == "hydrological"

    def wanted(record: NormalizedRecord) -> bool:
        year = record.hydro_year if hydrological else record.date.year
        return (chosen is None or record.station_code in chosen) and (
            chosen_years is None or year in chosen_years
        )

    kept = None if subset is None else wanted
    skipped: set[date] = set()
    with tempfile.TemporaryDirectory(prefix="obserwator-series-") as local:
        spill = _Spill(Path(local), descriptor)
        try:
            for index, item in enumerate(read, start=1):
                if cancelled():
                    return _report("cancelled", sources=sources)
                data = item.version.file.read_bytes()
                if hashlib.sha256(data).hexdigest() != item.version.sha256:
                    raise ObserwatorDataError(
                        message(
                            "series.checksum_does_not_match_sidecar",
                            relative=item.version.relative,
                        )
                    )
                # Records go to their station files and are dropped: neither the
                # parsed records nor the values of all stations stay in memory.
                records = normalize_in_sequence(
                    item.archive,
                    data=data,
                    carry=carry,
                    stations=chosen,
                    skipped_months=skipped,
                )
                if per_station:
                    monthly = item.archive.month is not None
                    _spill_station_file(
                        spill,
                        item.archive,
                        records,
                        spans,
                        superseded if monthly else (),
                        kept=kept,
                        subset=subset,
                        windows=windows,
                    )
                else:
                    for record in records:
                        known.add(record)
                        if kept is None or kept(record):
                            spill.add(record)
                if on_progress is not None:
                    on_progress(
                        Progress(
                            index,
                            len(read),
                            "archive",
                            "parsed",
                            message(
                                "series.archive_read", relative=item.version.relative
                            ),
                        )
                    )
            spill.flush()
        except (ObserwatorDataError, ObserwatorValidationError, OSError) as exc:
            if on_notice is not None:
                on_notice(Notice("warning", "archive_failed", reason(exc)))
            return _report("failed", sources=sources, problems=[reason(exc)])
        # The months the rows of other stations publish (a subset of stations).
        known.add_months(skipped)
        if subset is not None:
            if not spill.stations:
                return _report(
                    "failed",
                    sources=sources,
                    problems=[
                        message("series.subset_holds_nothing", key=descriptor.key)
                    ],
                )
            missing = sorted((chosen or frozenset()) - spill.stations)
            if missing and on_notice is not None:
                on_notice(
                    Notice(
                        "warning",
                        "stations_missing",
                        message(
                            "series.stations_missing",
                            key=descriptor.key,
                            codes=", ".join(missing),
                        ),
                    )
                )
        station_periods = {code: _merge_spans(items) for code, items in spans.items()}

        # The first write of a new data root creates its marker (DEV-19.13).
        prepare_store(path, kind="data")
        incoming = path / ".incoming"
        incoming.mkdir(exist_ok=True)
        _cleanup(incoming, on_notice=on_notice)
        staging = incoming / f"{socket.gethostname()}_{os.getpid()}_{uuid.uuid4().hex}"
        (staging / "stations").mkdir(parents=True)
        try:
            index_stations: dict[str, dict[str, Any]] = {}
            total = len(spill.stations)
            for number, code in enumerate(sorted(spill.stations), start=1):
                if cancelled():
                    return _report("cancelled", sources=sources)
                try:
                    station = spill.station(code)
                except ObserwatorDataError as exc:
                    if on_notice is not None:
                        on_notice(Notice("warning", "archive_failed", reason(exc)))
                    return _report("failed", sources=sources, problems=[reason(exc)])
                table = _station_table(pa, station, descriptor)
                periods = station_periods[code] if per_station else None
                coverage = _station_coverage(
                    code,
                    station.values,
                    descriptor=descriptor,
                    known=known if periods is None else _KnownSpans(periods),
                )
                built = Path(local) / f"{code}.parquet"
                pq.write_table(table, built)
                digest = _copy_hashed(built, staging / "stations" / f"{code}.parquet")
                built.unlink()
                entry: dict[str, Any] = {
                    "file": f"stations/{code}.parquet",
                    "sha256": digest,
                    "rows": table.num_rows,
                    "variables": _coverage_index(coverage),
                }
                if periods is not None:
                    entry["periods"] = _iso_spans(periods)
                index_stations[code] = entry
                if on_progress is not None:
                    on_progress(
                        Progress(
                            number,
                            total,
                            "station",
                            "written",
                            message("series.station_progress", code=code),
                        )
                    )
            _fsync_dir(staging / "stations")
            lines = _lines(descriptor)
            series = {
                "schema": SERIES_SCHEMA,
                "dataset": descriptor.key,
                "year_type": descriptor.year_type,
                "periods": _iso_spans(
                    _merge_spans(
                        span
                        for code in index_stations
                        for span in station_periods[code]
                    )
                    if per_station
                    else _merge_spans(
                        _cut((_archive_span(item.archive) for item in read), windows)
                    )
                ),
                "stations": index_stations,
                **lines.fields(),
            }
            if subset is not None:
                series["subset"] = _subset_document(subset)
            content = _canonical(series)
            sha = hashlib.sha256(content).hexdigest()
            _write_json(staging / "series.json", series)
            published = [
                moment
                for item in read
                if (moment := _parse_time(item.version.http.get("last_modified")))
            ]
            now = datetime.now(UTC)
            label = (
                max(published).date().isoformat()
                if published
                else now.date().isoformat()
            )
            provider = get_provider(descriptor.provider)
            license_info = _license_document(descriptor.license)
            license_info["attribution"] = ". ".join(lines.attribution)
            # Inputs of a dataset with a canonical form carry its content sum (pins
            # ``input`` restorable by content, ADR-003 D17); others keep 3.0.0 bytes.
            source_files = [
                {
                    "name": item.version.file.name,
                    "file": item.version.relative,
                    "sha256": item.version.sha256,
                    "label": item.version.label,
                    **_content_fields(item.version.meta),
                }
                for item in sorted(read, key=lambda entry: entry.version.relative)
            ]

            def sidecar(version_label: str) -> dict[str, Any]:
                return {
                    "schema": "obserwator-meta/1",
                    "producer": "obserwator",
                    "producer_version": __version__,
                    "dataset": descriptor.key,
                    "country": provider.country,
                    "provider": provider.id,
                    # The call of the version (command_for_version): a subset
                    # adds its stations and years.
                    "request": {"dataset": descriptor.key, **_subset_document(subset)},
                    "license": license_info,
                    "downloaded_at": _utc(now),
                    "sha256": sha,
                    "size_bytes": len(content),
                    "extra": {
                        "version": {"label": version_label, "label_source": "inputs"},
                        "derived": "series",
                        "series_schema": SERIES_SCHEMA,
                        "source_files": source_files,
                    },
                }

            if cancelled():
                return _report("cancelled", sources=sources)
            if subset is not None:
                # A full build may have published since the check above.
                full = _full_series(_series_versions(path, descriptor))
                if full is not None:
                    raise _beside_full(path, descriptor, full)
            parent = _validate_slot(path, f"series/versions/{descriptor.slug}")
            parent.mkdir(parents=True, exist_ok=True)
            # Identical series.json from a different input manifest (e.g. re-zipped
            # archive) gets a stable manifest suffix instead of replacing the existing
            # version. An older version of the same manifest (inputs reverted to
            # earlier content) is not current, so this build takes the next free
            # label and becomes current.
            attempts = sum(1 for _ in parent.iterdir()) + 2
            for candidate in _candidate_labels(label, manifest, attempts=attempts):
                target = _validate_slot(
                    path, f"series/versions/{descriptor.slug}/{candidate}_{sha[:8]}"
                )
                meta_path = staging / "series.json.meta.json"
                meta_path.unlink(missing_ok=True)
                _write_json(meta_path, sidecar(candidate))
                _fsync_dir(staging)
                try:
                    _publish_dir(staging, target, "series.json.meta.json")
                except FileExistsError:
                    winner = _current_series(_series_versions(path, descriptor))
                    if (
                        winner is not None
                        and winner.path.parent == target
                        and winner.manifest == manifest
                        and winner.subset == subset
                    ):
                        # A concurrent build of the same inputs published first.
                        return _report(
                            "unchanged",
                            version=target / "series.json",
                            stations=len(index_stations),
                            sources=sources,
                        )
                    continue
                if on_notice is not None:
                    on_notice(
                        Notice(
                            "info",
                            "license_terms",
                            provider.license_notice(lines),
                        )
                    )
                return _report(
                    "new",
                    version=target / "series.json",
                    stations=len(index_stations),
                    sources=sources,
                )
            raise ObserwatorStoreConflictError(
                message("series.series_version_directory_collision", parent=parent)
            )
        finally:
            if staging.exists():
                shutil.rmtree(staging)
