"""
Sealing the capture spool into archive versions (ADR-030 D3, D7).

``store sync`` of a capture dataset (`obserwator.datasets.CAPTURE_SCOPE`) seals every
closed UTC day of its spool (``<state_dir>/obserwator/captures/<dataset>/<YYYY-MM-DD>/``,
`obserwator.captures`) into one archive version of the slot
``archive:<key>:<YYYY-MM-DD>.jsonl.gz`` (`obserwator.store.writer.write_capture`):

- The file is gzip-compressed JSON Lines (`encode`): one line per answer, in the order
  of time, address, SHA-256 and status, each the answer's ``time``, ``address``,
  ``status``, ``sha256`` and ``body`` (UTF-8 text) or ``body_base64``; an answer equal
  to the one before it from the same address (status and body) is recorded once, as
  ``seen``, without its body. The lines are canonical JSON and the gzip header holds no
  name and the time 0, so the same answers always give the same bytes.
- A day already sealed is sealed again with the answers of its current version: an
  answer that came after (a late spool file) gives a new version holding every answer
  (a correction, nothing lost), and a spool holding nothing new gives ``unchanged``.
- The spool files of a day are removed only after the version that holds them is
  published (or found to hold them already); a file that cannot be read stays, with a
  ``capture_unreadable`` warning.
- The day of today (UTC) is sealed only by a harvest run (``store sync`` with
  ``pace_until``, `check_captures` with ``today``): the run's day version holds every
  answer of the run, and answers that come later the same day give a correction
  version the next night (ADR-030 erratum of 2026-11-23); otherwise today is never
  sealed, answers may still come.
"""

from __future__ import annotations

import contextlib
import gzip
import hashlib
import io
import json
import zlib
from collections.abc import Iterable, Sequence
from datetime import date
from pathlib import Path

from obserwator import captures as _captures
from obserwator.captures import (
    Spooled,
    _canonical,
    from_record,
    read_spooled,
    spool_days,
    spool_files,
    spool_root,
)
from obserwator.datasets import (
    CAPTURE_SCOPE,
    ArchiveFile,
    DatasetDescriptor,
    _capture_file,
    get_dataset,
)
from obserwator.exceptions import (
    ObserwatorCancelledError,
    ObserwatorDataError,
    ObserwatorError,
)
from obserwator.fetch import _archive_slot
from obserwator.messages import message, reason
from obserwator.store.reader import current_version
from obserwator.store.types import (
    Cancel,
    Notice,
    NoticeHook,
    OperationResult,
    PlanItem,
    Progress,
    ProgressHook,
    StoreEntry,
)
from obserwator.store.writer import write_capture

__all__ = [
    "check_captures",
    "closed_days",
    "decode",
    "encode",
    "is_capture",
    "seal_day",
]

_CANCELLED = message("common.cancelled")


def is_capture(descriptor: DatasetDescriptor, /) -> bool:
    """
    Whether a dataset is a capture dataset (``archive_scope`` ``country_day``).

    Parameters
    ----------
    descriptor : DatasetDescriptor
        A dataset.

    Returns
    -------
    bool
        True for a capture dataset.
    """
    return descriptor.archive_scope == CAPTURE_SCOPE


def encode(answers: Iterable[Spooled], /) -> bytes:
    """
    The sealed file of a day's answers: gzip-compressed JSON Lines (ADR-030 D3).

    Parameters
    ----------
    answers : iterable of Spooled
        The answers; one with the identity of another (`Spooled.identity`) is
        kept once.

    Returns
    -------
    bytes
        Deterministic bytes: the lines sorted by time, address, SHA-256 and
        status, canonical JSON each, an answer equal to the one before from its
        address ``seen``; gzip with level 9, no name and the time 0.
    """
    unique = {answer.identity: answer for answer in answers}
    last: dict[str, tuple[str, int]] = {}
    lines = bytearray()
    for identity in sorted(unique):
        answer = unique[identity]
        seen = last.get(answer.address) == (answer.sha256, answer.status)
        lines += _canonical(answer.record(seen=seen))
        last[answer.address] = (answer.sha256, answer.status)
    buffer = io.BytesIO()
    with gzip.GzipFile(
        filename="", mode="wb", fileobj=buffer, compresslevel=9, mtime=0
    ) as stream:
        stream.write(bytes(lines))
    return buffer.getvalue()


def decode(data: bytes, /) -> list[Spooled]:
    """
    The answers of a sealed capture file, ``seen`` ones with the body they repeat.

    Parameters
    ----------
    data : bytes
        A file written by `encode`.

    Returns
    -------
    list of Spooled
        The answers in file order.

    Raises
    ------
    ValueError
        If the bytes are no gzip-compressed JSON Lines of answers.
    """
    try:
        text = gzip.decompress(data).decode("utf-8")
    except (OSError, EOFError, UnicodeDecodeError, zlib.error) as exc:
        raise ValueError(reason(exc)) from exc
    previous: dict[str, Spooled] = {}
    answers = []
    # A line ends at its line feed only: a body may hold U+2028, U+0085 and the other
    # breaks that `str.splitlines` splits at, which the canonical JSON leaves unescaped.
    for line in text.split("\n"):
        if not line:
            continue
        answer = from_record(json.loads(line), previous=previous)
        previous[answer.address] = answer
        answers.append(answer)
    return answers


def closed_days(
    key: str,
    /,
    *,
    today: bool = False,
    start: date | None = None,
    end: date | None = None,
) -> list[date]:
    """
    The UTC days of a capture dataset in the spool that are over (before today, UTC).

    Parameters
    ----------
    key : str
        A capture dataset.
    today : bool, optional
        Also today's day (a harvest run seals its own answers), whatever
        ``start`` and ``end``.
    start, end : datetime.date or None, optional
        The first and last closed day to give (``store check|sync --start/--end``);
        None for no bound.

    Returns
    -------
    list of datetime.date
        The days in order.
    """
    limit = _captures._now().date()
    return [
        day
        for day in spool_days(key)
        if (
            day < limit
            and (start is None or day >= start)
            and (end is None or day <= end)
        )
        or (today and day == limit)
    ]


def _spooled(
    key: str, day: date, *, on_notice: NoticeHook | None
) -> tuple[list[Spooled], list[Path]]:
    """The readable answers of a spool day and their files; the others are warned of."""
    answers: list[Spooled] = []
    files: list[Path] = []
    for path in spool_files(key, day):
        try:
            answer = read_spooled(path)
            if not answer.time.startswith(day.isoformat()):
                raise ValueError(
                    message("captures.name_does_not_match", name=path.name)
                )
        except (OSError, ValueError) as exc:
            if on_notice is not None:
                on_notice(
                    Notice(
                        "warning",
                        "capture_unreadable",
                        message(
                            "captures.unreadable_spool_file",
                            name=path.relative_to(spool_root()).as_posix(),
                            reason=reason(exc),
                        ),
                    )
                )
            continue
        answers.append(answer)
        files.append(path)
    return answers, files


def _stored(
    root: Path, archive: ArchiveFile
) -> tuple[StoreEntry | None, list[Spooled]]:
    """
    The current version of a day's slot and its answers; none without a version.

    Raises
    ------
    ObserwatorDataError
        If a version of the slot is broken or its file is no sealed capture.
    """
    entry = current_version(root, slot=_archive_slot(archive))
    if entry is None or entry.version is None or entry.meta is None:
        return None, []
    try:
        data = entry.version.read_bytes()
        if hashlib.sha256(data).hexdigest() != entry.meta.sha256:
            raise ValueError(
                message(
                    "reader.checksum_does_not_match_sidecar",
                    name=entry.version.name,
                    path=entry.version,
                )
            )
        return entry, decode(data)
    except (OSError, ValueError) as exc:
        raise ObserwatorDataError(
            message(
                "captures.corrupt_capture",
                version=entry.version.relative_to(root).as_posix(),
                reason=reason(exc),
            )
        ) from exc


def check_captures(
    root: Path,
    descriptors: Sequence[DatasetDescriptor],
    /,
    *,
    today: bool = False,
    start: date | None = None,
    end: date | None = None,
    on_progress: ProgressHook | None = None,
    on_notice: NoticeHook | None = None,
    cancel: Cancel | None = None,
) -> tuple[list[PlanItem], bool]:
    """
    The plan items of ``store check`` of capture datasets: one per spool day to seal.

    Nothing is written and no request is made: the spool and the raw root are read.

    Parameters
    ----------
    root : pathlib.Path
        The raw root.
    descriptors : sequence of DatasetDescriptor
        Capture datasets.
    today : bool, optional
        Also today's spool day (UTC), which a harvest run seals with the answers
        it asked for; else the closed days only.
    start, end : datetime.date or None, optional
        The first and last closed day checked (`closed_days`); None for no bound.
    on_progress : ProgressHook or None, optional
        Called after each day with its status.
    on_notice : NoticeHook or None, optional
        Receives a ``capture_unreadable`` warning for every spool file that cannot
        be read and an ``archive_failed`` warning for every ``check_failed`` day.
    cancel : Cancel or None, optional
        Polled before each day; the rest are ``unverifiable`` with ``cancelled``.

    Returns
    -------
    tuple of (list of PlanItem, bool)
        Per spool day (each closed day from ``start`` to ``end``, and today with
        ``today``): ``missing`` (no version of the day yet), ``newer`` (the spool
        holds answers its current version does not), ``current`` (every answer is
        in it: left over after a sealing) or ``check_failed`` (no readable answer,
        or a broken version); and whether the check was cancelled.
    """
    days = [
        (d, day)
        for d in descriptors
        for day in closed_days(d.key, today=today, start=start, end=end)
    ]
    items: list[PlanItem] = []
    cancelled = False
    for index, (descriptor, day) in enumerate(days, start=1):
        archive = _capture_file(descriptor, day)
        cancelled = cancelled or (cancel is not None and cancel())
        if cancelled:
            items.append(_item(archive, "unverifiable", error=_CANCELLED))
        else:
            items.append(_check_day(root, descriptor, archive, on_notice=on_notice))
            if items[-1].status == "check_failed" and on_notice is not None:
                on_notice(
                    Notice(
                        "warning",
                        "archive_failed",
                        f"{archive.server_path}: {items[-1].error}",
                    )
                )
        if on_progress is not None:
            on_progress(
                Progress(
                    index, len(days), "archive", items[-1].status, archive.server_path
                )
            )
    return items, cancelled


def _item(
    archive: ArchiveFile,
    status: str,
    *,
    entry: StoreEntry | None = None,
    root: Path | None = None,
    error: str | None = None,
) -> PlanItem:
    local = (
        entry.version.relative_to(root)
        if entry is not None and entry.version is not None and root is not None
        else None
    )
    return PlanItem(
        archive=archive,
        status=status,  # type: ignore[arg-type]
        local_path=local,
        local_sha256=entry.meta.sha256
        if entry is not None and entry.meta is not None
        else None,
        remote_etag=None,
        remote_last_modified=None,
        content_length=None,
        error=error,
    )


def _check_day(
    root: Path,
    descriptor: DatasetDescriptor,
    archive: ArchiveFile,
    *,
    on_notice: NoticeHook | None,
) -> PlanItem:
    assert archive.period_start is not None
    answers, _ = _spooled(descriptor.key, archive.period_start, on_notice=on_notice)
    try:
        entry, stored = _stored(root, archive)
    except ObserwatorError as exc:
        return _item(archive, "check_failed", error=reason(exc))
    if entry is None:
        if not answers:
            text = message(
                "captures.day_unreadable",
                dataset=descriptor.key,
                day=archive.period_start.isoformat(),
            )
            return _item(archive, "check_failed", error=text)
        return _item(archive, "missing")
    known = {answer.identity for answer in stored}
    fresh = any(answer.identity not in known for answer in answers)
    return _item(archive, "newer" if fresh else "current", entry=entry, root=root)


def _remove(files: Iterable[Path], directory: Path) -> None:
    """Remove the sealed spool files, then their day's directory when it is empty."""
    for path in files:
        with contextlib.suppress(FileNotFoundError):
            path.unlink()
    with contextlib.suppress(OSError):
        directory.rmdir()


def seal_day(
    root: Path,
    descriptor: DatasetDescriptor,
    day: date,
    /,
    *,
    on_progress: ProgressHook | None = None,
    on_notice: NoticeHook | None = None,
    cancel: Cancel | None = None,
) -> OperationResult:
    """
    Seal one UTC day of a capture dataset's spool into its version (D3).

    The day's readable spool files and the answers of the slot's current version
    are joined (each answer once) and written as one version
    (`obserwator.store.writer.write_capture`) unless the current version holds
    every answer already (``unchanged``); then the sealed spool files are removed.

    Parameters
    ----------
    root : pathlib.Path
        The raw root.
    descriptor : DatasetDescriptor
        A capture dataset.
    day : datetime.date
        A closed UTC day, or today in a harvest run.
    on_progress, on_notice, cancel
        As `obserwator.store.writer.write_capture`; ``on_notice`` also receives a
        ``capture_unreadable`` warning for every spool file left in the spool and an
        ``archive_failed`` warning for a day that could not be sealed.

    Returns
    -------
    OperationResult
        ``new``, ``unchanged``, ``failed`` (with its error code) or ``cancelled``
        for the slot ``archive:<key>:<YYYY-MM-DD>.jsonl.gz``.
    """
    archive = _capture_file(descriptor, day)
    slot = _archive_slot(archive)
    answers, files = _spooled(descriptor.key, day, on_notice=on_notice)
    try:
        entry, stored = _stored(root, archive)
        merged = {answer.identity: answer for answer in stored}
        for answer in answers:
            merged.setdefault(answer.identity, answer)
        if not merged:
            text = message(
                "captures.day_unreadable", dataset=descriptor.key, day=day.isoformat()
            )
            return OperationResult(slot, "failed", None, text, error_code="data_error")
        if entry is not None and len(merged) == len(stored):
            assert entry.version is not None
            status, version = "unchanged", entry.version
        else:
            written = write_capture(
                root,
                archive=archive,
                data=encode(merged.values()),
                answers=len(merged),
                on_progress=on_progress,
                on_notice=on_notice,
                cancel=cancel,
            )
            status, version = written.status, written.path
    except ObserwatorCancelledError:
        return OperationResult(slot, "cancelled", None, _CANCELLED)
    except (ObserwatorError, OSError) as exc:
        if on_notice is not None:
            on_notice(
                Notice("warning", "archive_failed", f"{archive.server_path}: {exc}")
            )
        return OperationResult(
            slot,
            "failed",
            None,
            reason(exc),
            error_code=exc.code if isinstance(exc, ObserwatorError) else "io_error",
        )
    # Published (or held already): the spool files of the day may go (D7).
    _remove(files, spool_root() / descriptor.key / day.isoformat())
    return OperationResult(slot, status, version, None)  # type: ignore[arg-type]


def seal_item(
    root: Path,
    item: PlanItem,
    /,
    *,
    on_notice: NoticeHook | None = None,
    cancel: Cancel | None = None,
) -> OperationResult:
    """
    Seal the day of a plan item of a capture dataset (``store sync``, `seal_day`).

    Parameters
    ----------
    root : pathlib.Path
        The raw root.
    item : PlanItem
        An item of `check_captures` (or of a plan file holding one).
    on_notice, cancel
        As `seal_day`.

    Returns
    -------
    OperationResult
        The result of `seal_day`; a cancelled check item is ``cancelled``.
    """
    if item.status == "unverifiable" and item.error == _CANCELLED:
        return OperationResult(
            _archive_slot(item.archive), "cancelled", None, _CANCELLED
        )
    assert item.archive.period_start is not None
    return seal_day(
        root,
        get_dataset(item.archive.dataset),
        item.archive.period_start,
        on_notice=on_notice,
        cancel=cancel,
    )
