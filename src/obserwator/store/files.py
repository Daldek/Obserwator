"""
``store import``: a provider fed by files into the raw root and the data root (ADR-033).

An operator's own network enters as data (Nogat plan 2026-11-21, I13): its provider file
beside ``nogat.toml`` names its station file and the directory of each dataset's station
series (`obserwator._provider_files`). One command, `import_files`, keeps every file in
the raw root as it came, each as an archive version with its sidecar (P14: the time,
the address, the provider, the licence and, for an unverified tier, the tier and the
publication state of P15), then builds the provider's series and its catalog into the
data root as ``series build`` and ``store catalog`` do. `check_import` plans the same
offline. Both read and check every file before anything is written: a provider file
with a problem, a missing or unreadable file, a station file or a series file that is
not of the documented form, a series of a station of another kind or a station
delivered once as CSV and once as Parquet are refused with ``validation_error``.
"""

from __future__ import annotations

import hashlib
import os
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Literal

from obserwator._parsing.files import parse_series_export, read_station_file
from obserwator._provider_files import STATIONS_FILE, FileDataset, ProviderFile
from obserwator.datasets import (
    ArchiveFile,
    ProviderDescriptor,
    check_provider_files,
    get_dataset,
    get_provider,
    provider_files,
)
from obserwator.exceptions import (
    ObserwatorCancelledError,
    ObserwatorDataError,
    ObserwatorValidationError,
    io_error,
)
from obserwator.fetch import DownloadResult
from obserwator.messages import Message, message
from obserwator.output import FileResult
from obserwator.store.catalog import (
    CATALOG_FILE,
    _current_archive,
    _current_catalog,
    build_catalog,
)
from obserwator.store.reader import _archive_slot
from obserwator.store.series import (
    _current_series,
    _series_versions,
    build_series,
)
from obserwator.store.types import (
    Cancel,
    CatalogReport,
    ImportReport,
    Notice,
    NoticeHook,
    OperationResult,
    PathArg,
    PlanAction,
    Progress,
    ProgressHook,
    SeriesReport,
    StoreHandle,
    StorePlan,
)
from obserwator.store.writer import (
    _archive_slot_dir,
    _existing,
    _validate_slot,
    lenient_store,
    refuse_root,
    root_conflict_plan,
    version_file,
    write_archive,
)

__all__ = ["check_import", "import_files"]

RootArg = PathArg | StoreHandle
_SUFFIXES = (".csv", ".parquet")
_LICENSE = "license_terms"


@dataclass(frozen=True)
class _File:
    """One file of the provider file, read and checked, and its place in the raw root."""

    archive: ArchiveFile
    source: str
    path: Path
    data: bytes
    dataset: str


def _provider(provider_file: object) -> tuple[ProviderDescriptor, ProviderFile]:
    """
    The provider fed by files of an import; refused before anything is read.

    Every provider file must be valid first (fail closed): a problem of any of them
    is raised as it is, whichever file is named. ``provider_file`` must then be one of
    the files ``[obserwator] provider_files`` lists, a relative path relative to the
    directory of ``nogat.toml`` as there.
    """
    check_provider_files()
    loaded = provider_files()
    found = (
        loaded.find(provider_file)
        if isinstance(provider_file, str | os.PathLike)
        else None
    )
    if found is None:
        shown = (
            str(loaded.resolve(provider_file))
            if isinstance(provider_file, str | os.PathLike)
            else repr(provider_file)
        )
        raise ObserwatorValidationError(
            message("provider_files.not_listed", path=shown),
            details={
                "option": "provider_file",
                "value": shown,
                "reason": "not_listed",
            },
        )
    return get_provider(found.id), found


def _refused(path: Path, option: str, text: Message) -> ObserwatorValidationError:
    """A file of the provider file that cannot be imported."""
    return ObserwatorValidationError(
        text, details={"option": option, "path": str(path)}
    )


def _read(path: Path, option: str) -> bytes:
    """The bytes of a file the provider file names."""
    try:
        return path.read_bytes()
    except FileNotFoundError as exc:
        raise _refused(
            path, option, message("provider_files.data_file_missing", path=path)
        ) from exc
    except IsADirectoryError as exc:
        raise _refused(
            path, option, message("provider_files.data_not_file", path=path)
        ) from exc
    except OSError as exc:
        raise io_error(exc) from exc


def _checked(path: Path, option: str, read: Callable[[], object]) -> None:
    """Run a parser over a file; what it cannot read is the operator's input refused."""
    try:
        read()
    except ObserwatorDataError as exc:
        raise ObserwatorValidationError(
            exc.detail, details={"option": option, "path": str(path)}
        ) from exc


def _other_form(raw: Path | None, archive: ArchiveFile) -> str | None:
    """
    The file name of another form the raw root keeps of a station's series, if any.

    A station delivered as ``<code>.csv`` keeps its versions in the slot of
    ``<code>.parquet`` too (a slot is named by the file without its ending); its
    series would read either, so a station keeps the form it was first imported in.
    """
    if raw is None:
        return None
    slot = _validate_slot(raw, _archive_slot_dir(archive.server_path))
    if not slot.is_dir():
        return None
    name = PurePosixPath(archive.server_path).name
    for version in sorted(slot.iterdir()):
        if not version.is_dir():
            continue
        for sidecar in version.glob("*.meta.json"):
            stored = sidecar.name.removesuffix(".meta.json")
            if stored != name:
                return stored
    return None


def _series_files(
    owner: ProviderDescriptor,
    provider: ProviderFile,
    dataset: FileDataset,
    kinds: dict[str, str],
    raw: Path | None,
) -> list[_File]:
    """The station series files of one dataset, by station code, read and checked."""
    option = f"provider_file.datasets.{dataset.name}.directory"
    key = f"{provider.key_prefix}.{dataset.name}"
    descriptor = get_dataset(key)
    directory = dataset.path
    if not directory.is_dir():
        raise _refused(
            directory,
            option,
            message("provider_files.data_directory_missing", path=directory),
        )
    pattern = re.compile(provider.station_code_pattern)
    found: dict[str, _File] = {}
    for path in sorted(directory.iterdir()):
        if path.name.startswith("."):
            continue
        stem, suffix = path.stem, path.suffix
        if (
            not path.is_file()
            or suffix not in _SUFFIXES
            or pattern.fullmatch(stem) is None
        ):
            raise _refused(
                path,
                option,
                message(
                    "provider_files.series_file_name",
                    name=path.name,
                    pattern=provider.station_code_pattern,
                ),
            )
        if stem in found:
            raise _refused(
                path, option, message("provider_files.series_twice", code=stem)
            )
        kind = kinds.get(stem)
        if kind is not None and kind != dataset.kind:
            raise _refused(
                path,
                option,
                message(
                    "provider_files.series_of_other_kind",
                    code=stem,
                    kind=kind,
                    series=dataset.kind,
                ),
            )
        data = _read(path, option)

        def parse(data: bytes = data, stem: str = stem, path: Path = path) -> object:
            return parse_series_export(
                data, dataset=key, station=stem, filename=str(path)
            )

        _checked(path, option, parse)
        archive = owner.adapter.archive_from_path(
            descriptor, f"{descriptor.server_dir}/{path.name}"
        )
        assert archive is not None  # a code of the provider's grammar, a known suffix
        other = _other_form(raw, archive)
        if other is not None:
            raise _refused(
                path,
                option,
                message("provider_files.series_other_form", code=stem, stored=other),
            )
        found[stem] = _File(archive, archive.url, path, data, key)
    return [found[code] for code in sorted(found)]


def _files(
    owner: ProviderDescriptor, provider: ProviderFile, raw: Path | None
) -> list[_File]:
    """Every file of the provider file, read and checked: the station file first."""
    option = "provider_file.stations"
    data = _read(provider.stations_path, option)
    holder: list[tuple[str, str]] = []

    def stations() -> None:
        for station in read_station_file(
            data,
            pattern=provider.station_code_pattern,
            filename=str(provider.stations_path),
        ):
            holder.append((station.station_code, station.kind))

    _checked(provider.stations_path, option, stations)
    key = owner.adapter.station_sources[0]
    archive = owner.adapter.station_file(get_dataset(key), STATIONS_FILE)
    assert archive is not None  # the fixed name of the station list
    files = [_File(archive, provider.stations, provider.stations_path, data, key)]
    kinds = dict(holder)
    for dataset in provider.datasets:
        files.extend(_series_files(owner, provider, dataset, kinds, raw))
    return files


def _slot(archive: ArchiveFile) -> str | None:
    return _archive_slot(archive.server_path)


def _cancelled(cancel: Cancel | None) -> bool:
    return cancel is not None and cancel()


def _forward(on_notice: NoticeHook | None) -> NoticeHook | None:
    """The notices of the writes, each text once (one licence notice, not one a file)."""
    if on_notice is None:
        return None
    given: set[tuple[str, str]] = set()

    def forward(notice: Notice) -> None:
        if notice.code == _LICENSE:
            if (notice.code, notice.message) in given:
                return
            given.add((notice.code, notice.message))
        on_notice(notice)

    return forward


def _stored_datasets(raw: Path, provider: ProviderFile) -> list[str]:
    """The datasets of the provider whose files the raw root holds, in file order."""
    found = []
    for dataset in provider.datasets:
        descriptor = get_dataset(f"{provider.key_prefix}.{dataset.name}")
        directory = raw / "archives" / "versions" / (descriptor.server_dir or "")
        if directory.is_dir() and any(directory.rglob("*.meta.json")):
            found.append(descriptor.key)
    return found


def import_files(
    root: RootArg,
    /,
    *,
    raw_root: RootArg,
    provider_file: PathArg,
    on_progress: ProgressHook | None = None,
    on_notice: NoticeHook | None = None,
    cancel: Cancel | None = None,
) -> ImportReport:
    """
    Import the files of a provider fed by files into the raw root and the data root.

    The provider file (one of ``[obserwator] provider_files`` of ``nogat.toml``,
    ADR-033) names the station file and, per dataset, a directory of one file per
    station, ``<station code>.csv`` (``obserwator-series-csv``, the CSV of ``series
    export``) or ``<station code>.parquet`` (its Parquet). Every file is read and
    checked first; then each is kept in the raw root as it came (`write_archive`: an
    archive version with its sidecar, ``unchanged`` when the same bytes are stored),
    below ``archives/versions/files/<acronym>/``: the station file as
    ``station_list/stations.geojson``, a series as ``<dataset>/<file name>``. Then
    each dataset whose files the raw root holds is built (`build_series`) and the
    provider's catalog (`build_catalog`), into the data root. A version is never
    replaced, so a station's last delivered series stays when the directory no longer
    holds its file.

    Parameters
    ----------
    root : str, os.PathLike or StoreHandle
        The data root of the series and the catalog (ADR-017); created with its marker
        when new or empty.
    raw_root : str, os.PathLike or StoreHandle
        The raw root the files are kept in; created with its marker when new or empty.
    provider_file : str or os.PathLike
        The provider file of the provider fed by files: one of the files
        ``[obserwator] provider_files`` lists, ``~`` expanded and a relative path
        relative to the directory of ``nogat.toml``, as there.
    on_progress : ProgressHook or None, optional
        Called after each file kept (``unit`` ``file``) and by the builds.
    on_notice : NoticeHook or None, optional
        Receives the notices of the writes (the provider's ``license_terms`` once) and
        of the builds.
    cancel : Cancel or None, optional
        Polled before each file and before each build; once it returns ``True`` the
        import stops with ``cancelled`` (what was written stays complete).

    Returns
    -------
    ImportReport
        The raw version of every file, the builds and every version as ``files[]``.

    Raises
    ------
    ObserwatorValidationError
        Before anything is written: a provider file of ``nogat.toml`` with a problem
        (its own ``details.option`` and ``details.path``); ``provider_file`` naming no
        file ``provider_files`` lists (``details.option`` ``provider_file``,
        ``details.reason`` ``not_listed``); a missing
        station file or dataset directory, a file in such a directory that is not
        ``<station code>.csv`` or ``.parquet`` of the provider's codes, a station given
        twice, a station file or series file that cannot be read as documented, a
        series of a station of another kind, or a station whose raw root keeps the
        other form of its series (``details.option`` the field of the provider file,
        ``details.path`` the file).
    ObserwatorStoreError
        If a root is one of the other kind (``store_unavailable``, ``wrong_root``) or
        has a layout without its marker.
    ObserwatorStoreConflictError
        If a root nests a store or holds other files (``conflict``).
    ObserwatorDataError
        If a build cannot read what the raw root holds; ``io_error`` if a file cannot
        be read.
    """
    owner, found = _provider(provider_file)
    refuse_root(root, kind="data")
    lenient_store(root, kind="data")
    raw = refuse_root(raw_root, kind="raw")
    lenient_store(raw_root, kind="raw")
    files = _files(owner, found, raw if raw.exists() else None)
    items: list[OperationResult] = []
    written: list[FileResult] = []
    forward = _forward(on_notice)
    total = len(files)

    def report(
        series: tuple[SeriesReport, ...] = (),
        catalog: CatalogReport | None = None,
        *,
        cancelled: bool,
    ) -> ImportReport:
        files_ = [*written]
        for item in series:
            files_.extend(item.files)
        if catalog is not None:
            files_.extend(catalog.files)
        return ImportReport(
            owner.id, tuple(items), series, catalog, cancelled, tuple(files_)
        )

    for number, item in enumerate(files, start=1):
        if _cancelled(cancel):
            return report(cancelled=True)
        try:
            result = write_archive(
                raw_root,
                archive=item.archive,
                response=DownloadResult(
                    item.data, item.source, None, None, len(item.data)
                ),
                on_notice=forward,
                cancel=cancel,
            )
        except ObserwatorCancelledError:
            return report(cancelled=True)
        items.append(
            OperationResult(_slot(item.archive), result.status, result.path, None)
        )
        written.append(version_file(result.path, result.status))
        if on_progress is not None:
            on_progress(
                Progress(
                    number,
                    total,
                    "file",
                    result.status,
                    message("provider_files.file_kept", file=item.source),
                )
            )
    series: list[SeriesReport] = []
    for key in _stored_datasets(raw, found):
        if _cancelled(cancel):
            return report(tuple(series), cancelled=True)
        series.append(
            build_series(
                root,
                raw_root=raw_root,
                dataset=key,
                on_progress=on_progress,
                on_notice=on_notice,
                cancel=cancel,
            )
        )
        if series[-1].status == "cancelled":
            return report(tuple(series), cancelled=True)
    if _cancelled(cancel):
        return report(tuple(series), cancelled=True)
    catalog = build_catalog(
        root,
        raw_root=raw_root,
        provider=owner.id,
        on_progress=on_progress,
        on_notice=on_notice,
        cancel=cancel,
    )
    return report(tuple(series), catalog, cancelled=catalog.status == "cancelled")


def _file_status(
    raw: Path | None, item: _File
) -> Literal["current", "newer", "missing"]:
    """Whether the raw root's current version of a file has its bytes."""
    if raw is None:
        return "missing"
    slot = _validate_slot(raw, _archive_slot_dir(item.archive.server_path))
    if not slot.is_dir() or not any(
        _existing(slot, PurePosixPath(item.archive.server_path).name, archive=True)
    ):
        return "missing"
    current = _current_archive(raw, item.archive)
    if current is None:
        return "missing"
    digest = hashlib.sha256(item.data).hexdigest()
    return "current" if current[1]["sha256"] == digest else "newer"


def check_import(
    root: RootArg,
    /,
    *,
    raw_root: RootArg,
    provider_file: PathArg,
    on_progress: ProgressHook | None = None,
    on_notice: NoticeHook | None = None,
    cancel: Cancel | None = None,
) -> StorePlan:
    """
    Plan `import_files` offline: nothing is written.

    Every file is read and checked as the import reads it, so a plan refuses what the
    import refuses.

    Parameters
    ----------
    root : str, os.PathLike or StoreHandle
        The data root; it need not exist.
    raw_root : str, os.PathLike or StoreHandle
        The raw root; it need not exist.
    provider_file : str or os.PathLike
        The provider file, as `import_files` takes it.
    on_progress : ProgressHook or None, optional
        Called once with the overall status.
    on_notice : NoticeHook or None, optional
        Not called: a plan has no notices of its own.
    cancel : Cancel or None, optional
        Polled before the files are compared; once it returns ``True`` the plan is
        ``cancelled`` without actions.

    Returns
    -------
    StorePlan
        ``obserwator-plan/1`` without items: one ``store import`` action per file
        (``missing`` without a version in the raw root, ``current`` when its current
        version has the same bytes, ``newer`` otherwise), one ``series build`` action
        per dataset (``missing`` without a series, ``newer`` when a file of it is new
        or changed, ``current`` otherwise) and one ``store catalog`` action
        (``missing`` without a catalog, ``newer`` when the station file or a series
        changes, ``current`` otherwise). A root that a write turns away is planned as
        one ``conflict`` action.

    Raises
    ------
    ObserwatorValidationError
        As `import_files`, before anything else.
    ObserwatorStoreError
        If a root is one of the other kind or has a layout without its marker.
    """
    owner, found = _provider(provider_file)
    for value, kind in ((root, "data"), (raw_root, "raw")):
        refused = root_conflict_plan(
            "store import", value, kind="data" if kind == "data" else "raw"
        )
        if refused is not None:
            return refused
    data = lenient_store(root, kind="data").root
    raw_handle = lenient_store(raw_root, kind="raw")
    raw = raw_handle.root if raw_handle.root.exists() else None
    files = _files(owner, found, raw)
    if _cancelled(cancel):
        return StorePlan(
            "obserwator-plan/1", data, datetime.now(UTC), (), {}, (), cancelled=True
        )
    actions: list[PlanAction] = []
    changed: dict[str, bool] = {}
    for item in files:
        status = _file_status(raw, item)
        changed[item.dataset] = changed.get(item.dataset, False) or status != "current"
        actions.append(
            PlanAction(
                "store import",
                status,
                message(
                    "provider_files.plan_file",
                    file=item.source,
                    slot=str(_slot(item.archive)),
                ),
            )
        )
    any_change = any(changed.values())
    for dataset in found.datasets:
        descriptor = get_dataset(f"{found.key_prefix}.{dataset.name}")
        current = _current_series(_series_versions(data, descriptor))
        series_status: Literal["current", "newer", "missing"]
        if current is None:
            series_status = "missing"
        elif changed.get(descriptor.key, False):
            series_status = "newer"
        else:
            series_status = "current"
        any_change = any_change or series_status != "current"
        actions.append(
            PlanAction(
                "series build",
                series_status,
                message("provider_files.plan_series", dataset=descriptor.key),
            )
        )
    catalog = _current_catalog(data, owner.id) if data.exists() else None
    catalog_status: Literal["current", "newer", "missing"] = (
        "missing" if catalog is None else "newer" if any_change else "current"
    )
    actions.append(
        PlanAction(
            "store catalog",
            catalog_status,
            message(
                "provider_files.plan_catalog",
                provider=owner.id,
                file=CATALOG_FILE,
            ),
        )
    )
    if on_progress is not None:
        on_progress(
            Progress(
                len(actions),
                len(actions),
                "action",
                catalog_status,
                message("provider_files.plan_done", provider=owner.id),
            )
        )
    return StorePlan(
        "obserwator-plan/1", data, datetime.now(UTC), (), {}, tuple(actions)
    )
