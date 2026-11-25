"""
``store import --staging``: an interim capture into the raw root (ADR-035 W15).

Before the release that captures PIG-PIB's services, its interim capture (S0 of the
Nogat plan 2026-11-24) kept their answers outside any store (`ProviderAdapter.staged`):
a directory of runs ``<YYYY-MM-DDTHHMMSSZ>/`` (the run's UTC start), each with the
answers as they came, one file each, and ``manifest.jsonl``, one line per answer (its
time, address, HTTP status, size and SHA-256). The probe's capture, the first run,
names GET addresses; S0's own runs name the URL POSTed and its form (``params``), the
part of the run each answer belongs to and the events of the run (``part_end`` with
``complete``, ``run_end``).

`import_staging` writes the runs in time order as the store would have written each
that day (W4, W5, W9):

- Before anything is written, every answer's file is checked against its manifest's
  size and SHA-256; a file that is missing or differs refuses the import.
- The answers of one table of a run (the points, the readings, the chemistry, the
  watch list) are one version, Obserwator's container of answers
  (`obserwator.store.captures.encode`), when they are a complete run: every answer
  200 without an ArcGIS error, the pages by ``resultOffset`` up to a short page, the
  counts before and after equal to the rows read, and, in S0's runs, ``complete`` in
  the part's end. The file is named by what the answers hold
  (`ProviderAdapter.run_file`: the readings by the month of their rows); the run's
  time dates the version (``downloaded_at``, the label and the observation of an
  equal run), its content is compared with the version current at that time, and
  ``extra.staging.run`` names the run (`obserwator.store.writer.write_archive`).
- The answers the night's harvest asks (`ProviderAdapter.harvest_answer`: the
  automatic points, the rows after a watermark, the stored hour 02 of a summer-time
  start day) go to the capture of the run's UTC day: the good answers of every run
  of the day and the day's current version are one version (``extra.staging.runs``),
  sealed a line at a time into a file of the root (a night of the backfill holds about
  500 MB of answers), under the lock of the captures' sealing (ADR-030 D10).
- An answer of no such run (the services' and layers' descriptions, other queries)
  and a request without a good answer are left out, counted per run in a notice; so
  is an incomplete table.

A second import of the same runs writes nothing: each table's version holds its run's
bytes, or the run equalled the version current then, and each day's capture holds every
answer already. `check_staging` plans the same without writing. The data root is not
touched: the series and the catalog are built from the raw root as after any night
(``series build``, ``store catalog``).
"""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import re
import shutil
import socket
import uuid
import zlib
from collections import Counter
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path, PurePosixPath
from typing import Literal
from urllib.parse import parse_qsl, urlsplit, urlunsplit

from obserwator.captures import Spooled, _instant, from_record, strip_credentials
from obserwator.datasets import (
    CAPTURE_SCOPE,
    ArchiveFile,
    DatasetDescriptor,
    ProviderDescriptor,
    _capture_file,
    _source_address,
    datasets,
    get_dataset,
    get_provider,
    providers,
)
from obserwator.exceptions import (
    ObserwatorCancelledError,
    ObserwatorDataError,
    ObserwatorValidationError,
)
from obserwator.fetch import ARCGIS_PAGE, DownloadResult, _archive_slot, arcgis_address
from obserwator.messages import Message, message, reason
from obserwator.output import FileResult
from obserwator.providers.base import ProviderAdapter
from obserwator.store.captures import Sealer, encode
from obserwator.store.catalog import _timestamp
from obserwator.store.content import content_sha256, stored_form
from obserwator.store.files import _forward
from obserwator.store.reader import _current, current_version
from obserwator.store.sync import _sync_lock
from obserwator.store.types import (
    Cancel,
    ImportReport,
    Notice,
    NoticeHook,
    OperationResult,
    PathArg,
    PlanAction,
    Progress,
    ProgressHook,
    StoreEntry,
    StoreHandle,
    StorePlan,
)
from obserwator.store.writer import (
    _archive_slot_dir,
    _existing,
    _sha256_file,
    _validate_slot,
    lenient_store,
    prepare_store,
    refuse_root,
    root_conflict_plan,
    version_file,
    write_archive,
    write_capture,
)

__all__ = ["MANIFEST", "check_staging", "import_staging"]

RootArg = PathArg | StoreHandle
MANIFEST = "manifest.jsonl"
"""The manifest of a run of an interim capture: one JSON object per line."""
_RUN = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{6}Z")
_RUN_TIME = "%Y-%m-%dT%H%M%SZ"
_SHA = re.compile(r"[0-9a-f]{64}")
_IMPORT = "store import"
_CANCELLED = message("common.cancelled")

Identity = tuple[str, str, str, int]


@dataclass(frozen=True)
class _Answer:
    """One answer of a run: its manifest's record and its file."""

    run: str
    time: str
    address: str
    status: int
    sha256: str
    size: int
    path: Path

    @property
    def identity(self) -> Identity:
        """What tells it from other answers in a capture (`Spooled.identity`)."""
        return (self.time, self.address, self.sha256, self.status)

    def spooled(self) -> Spooled:
        """The answer with its body, checked against its manifest again."""
        return Spooled(self.time, self.address, self.status, self.sha256, _body(self))


@dataclass
class _Part:
    """The answers of one table in one run: a version when they are a complete run."""

    name: str
    descriptor: DatasetDescriptor
    adapter: ProviderAdapter
    answers: list[_Answer] = field(default_factory=list)


@dataclass
class _Run:
    """One run of the interim capture, its files checked."""

    name: str
    time: datetime
    events: bool = False
    ended: bool = False
    complete: dict[str, bool] = field(default_factory=dict)
    parts: dict[tuple[str, str], _Part] = field(default_factory=dict)
    captures: list[tuple[DatasetDescriptor, _Answer]] = field(default_factory=list)
    answers: int = 0
    failed: int = 0
    left: int = 0
    unlisted: int = 0


@dataclass(frozen=True)
class _Kept:
    """A complete table of a run: its container of answers and the file it names."""

    run: _Run
    part: _Part
    data: bytes
    archive: ArchiveFile


@dataclass(frozen=True)
class _Known:
    """A version of a slot, stored or planned: when, its bytes and its content."""

    at: datetime
    sha256: str
    content: str | None


Source = tuple[str, DatasetDescriptor, ProviderAdapter]


def _refused(path: Path, text: Message) -> ObserwatorValidationError:
    """An interim capture that cannot be imported, refused before anything is written."""
    return ObserwatorValidationError(
        text, details={"option": "staging", "path": str(path)}
    )


def _body(answer: _Answer) -> bytes:
    """The file of an answer, checked against its manifest's size and SHA-256."""
    try:
        data = answer.path.read_bytes()
    except OSError as exc:
        manifest = answer.path.parent / MANIFEST
        raise _refused(
            answer.path,
            message(
                "staging.file_unreadable",
                path=manifest,
                file=answer.path.name,
                reason=reason(exc),
            ),
        ) from exc
    digest = hashlib.sha256(data).hexdigest()
    if len(data) != answer.size or digest != answer.sha256:
        raise _refused(
            answer.path,
            message(
                "staging.file_differs",
                file=answer.path.name,
                run=answer.run,
                size=len(data),
                sha256=digest,
                expected_size=answer.size,
                expected_sha256=answer.sha256,
            ),
        )
    return data


def _good(status: int, data: bytes) -> bool:
    """Whether an answer is a good one: HTTP 200 and a JSON object, no ArcGIS error."""
    if status != 200:
        return False
    try:
        payload = json.loads(data)
    except ValueError:
        return False
    return isinstance(payload, dict) and "error" not in payload


def _bare(address: str) -> str:
    """An address without its query."""
    parts = urlsplit(address)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", "")).rstrip("/")


def _form(address: str) -> dict[str, str]:
    """The parameters of a query (its form or its query string)."""
    return dict(parse_qsl(urlsplit(address).query, keep_blank_values=True))


def _sources() -> list[Source]:
    """The addresses of the datasets of every provider with an interim capture."""
    found: list[Source] = []
    for provider in providers():
        adapter = provider.adapter
        if not adapter.staged:
            continue
        for descriptor in datasets(provider=provider.id):
            if descriptor.server_dir:
                found.append(
                    (_source_address(descriptor).rstrip("/"), descriptor, adapter)
                )
    # The longest address first: a dataset's own table before its service.
    found.sort(key=lambda source: len(source[0]), reverse=True)
    return found


def _match(sources: Sequence[Source], bare: str) -> Source | None:
    """The dataset an address belongs to, by its source address; None for none."""
    for source in sources:
        if bare == source[0] or bare.startswith(f"{source[0]}/"):
            return source
    return None


def _run_time(name: str) -> datetime | None:
    """The UTC start of a run by its directory's name; None for another name."""
    if not _RUN.fullmatch(name):
        return None
    try:
        return datetime.strptime(name, _RUN_TIME).replace(tzinfo=UTC)
    except ValueError:
        return None


def _record_answer(
    manifest: Path, number: int, record: dict[str, object], run: str
) -> tuple[_Answer, str | None]:
    """The answer of a manifest's line with a file, and its part; refused if malformed."""

    def bad(name: str) -> ObserwatorValidationError:
        return _refused(
            manifest,
            message("staging.bad_record", number=number, path=manifest, field=name),
        )

    time = record.get("time")
    if not isinstance(time, str):
        raise bad("time")
    try:
        _instant(time)
    except ValueError:
        raise bad("time") from None
    url = record.get("url")
    if not isinstance(url, str) or not url.startswith(("https://", "http://")):
        raise bad("url")
    status = record.get("status")
    if isinstance(status, bool) or not isinstance(status, int):
        raise bad("status")
    sha = record.get("sha256")
    if not isinstance(sha, str) or not _SHA.fullmatch(sha):
        raise bad("sha256")
    size = record.get("bytes")
    if isinstance(size, bool) or not isinstance(size, int) or size < 0:
        raise bad("bytes")
    name = record.get("file")
    if (
        not isinstance(name, str)
        or name in ("", ".", "..", MANIFEST)
        or "/" in name
        or "\\" in name
    ):
        raise bad("file")
    params = record.get("params")
    if params is None:
        address = url
    elif isinstance(params, dict):
        # The address of a POST: its URL with its form as the query, as S0 sent it.
        address = arcgis_address(url, {str(k): str(v) for k, v in params.items()})
    else:
        raise bad("params")
    part = record.get("part")
    if part is not None and not isinstance(part, str):
        raise bad("part")
    answer = _Answer(
        run,
        time,
        strip_credentials(address),
        status,
        sha,
        size,
        manifest.parent / name,
    )
    return answer, part


def _read_run(directory: Path, time: datetime, sources: Sequence[Source]) -> _Run:
    """
    A run: its manifest read, each answer's file checked, its answers sorted.

    Raises
    ------
    ObserwatorValidationError
        If the manifest cannot be read, a line is no record of the interim capture,
        or a file is missing or differs from its record.
    """
    manifest = directory / MANIFEST
    run = _Run(directory.name, time)
    try:
        text = manifest.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise _refused(
            manifest,
            message("staging.manifest_unreadable", path=manifest, reason=reason(exc)),
        ) from exc
    listed = {MANIFEST}
    for number, line in enumerate(text.split("\n"), start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except ValueError:
            record = None
        if not isinstance(record, dict):
            raise _refused(
                manifest,
                message("staging.not_object", number=number, path=manifest),
            )
        event = record.get("event")
        if event is not None:
            run.events = True
            if event == "part_end" and isinstance(record.get("part"), str):
                run.complete[str(record["part"])] = record.get("complete") is True
            elif event == "run_end":
                run.ended = True
            continue
        if record.get("file") is None:
            # A request S0 made without an answer to keep (a network failure).
            run.failed += 1
            continue
        answer, part = _record_answer(manifest, number, record, run.name)
        listed.add(answer.path.name)
        data = _body(answer)
        run.answers += 1
        bare = _bare(answer.address)
        source = _match(sources, bare)
        if source is None:
            run.left += 1
            continue
        address, descriptor, adapter = source
        if descriptor.archive_scope == CAPTURE_SCOPE:
            if not adapter.harvest_answer(descriptor.key, answer.address):
                run.left += 1
            elif not _good(answer.status, data):
                run.failed += 1
            else:
                run.captures.append((descriptor, answer))
            continue
        if bare != f"{address}/query":
            run.left += 1
            continue
        name = part if part is not None else descriptor.key
        run.parts.setdefault(
            (descriptor.key, name), _Part(name, descriptor, adapter)
        ).answers.append(answer)
    run.unlisted = sum(1 for entry in directory.iterdir() if entry.name not in listed)
    return run


def _read(
    staging: PathArg,
    *,
    on_progress: ProgressHook | None,
    cancel: Cancel | None,
) -> tuple[ProviderDescriptor, list[_Run] | None]:
    """
    The provider and the runs of an interim capture in time order; None runs if cancelled.

    Raises
    ------
    ObserwatorValidationError
        If ``staging`` is no directory of runs, a run cannot be read or a file differs
        from its record, or the runs hold no answer of one provider's capture.
    """
    directory = Path(staging).expanduser().absolute()
    if not directory.is_dir():
        raise _refused(directory, message("staging.not_directory", path=directory))
    found = sorted(
        (entry.name, time)
        for entry in directory.iterdir()
        if entry.is_dir()
        and (time := _run_time(entry.name)) is not None
        and (entry / MANIFEST).is_file()
    )
    if not found:
        raise _refused(directory, message("staging.no_runs", path=directory))
    sources = _sources()
    staged = sorted({descriptor.provider for _, descriptor, _ in sources})
    runs: list[_Run] = []
    for index, (name, time) in enumerate(found, start=1):
        if cancel is not None and cancel():
            return get_provider(staged[0]), None
        runs.append(_read_run(directory / name, time, sources))
        if on_progress is not None:
            on_progress(
                Progress(
                    index,
                    len(found),
                    "run",
                    "read",
                    message("staging.run_read", run=name, answers=runs[-1].answers),
                )
            )
    owners = sorted(
        {part.descriptor.provider for run in runs for part in run.parts.values()}
        | {descriptor.provider for run in runs for descriptor, _ in run.captures}
    )
    if not owners:
        raise _refused(
            directory,
            message("staging.no_provider", path=directory, providers=", ".join(staged)),
        )
    if len(owners) > 1:
        raise _refused(
            directory,
            message(
                "staging.several_providers", path=directory, providers=", ".join(owners)
            ),
        )
    return get_provider(owners[0]), runs


def _tell(run: _Run, on_notice: NoticeHook | None) -> None:
    """The notices of what a run leaves out."""
    if on_notice is None:
        return
    if run.events and not run.ended:
        on_notice(
            Notice("warning", "staging_open", message("staging.open", run=run.name))
        )
    if run.left:
        on_notice(
            Notice(
                "info",
                "staging_left_out",
                message("staging.left_out", run=run.name, count=run.left),
            )
        )
    if run.unlisted:
        on_notice(
            Notice(
                "warning",
                "staging_left_out",
                message("staging.unlisted", run=run.name, count=run.unlisted),
            )
        )
    if run.failed:
        on_notice(
            Notice(
                "warning",
                "staging_failed",
                message("staging.failed", run=run.name, count=run.failed),
            )
        )


def _incomplete(run: _Run, part: _Part, answers: Sequence[Spooled]) -> Message | None:
    """Why a table's answers are no complete run of `obserwator.fetch.arcgis_pages`."""
    if run.events:
        complete = run.complete.get(part.name)
        if complete is None:
            return message("staging.reason_not_ended")
        if not complete:
            return message("staging.reason_marked")
    rows = 0
    counts: list[object] = []
    short = False
    for answer in answers:
        try:
            payload = json.loads(answer.content)
        except ValueError:
            payload = None
        if answer.status != 200 or not isinstance(payload, dict) or "error" in payload:
            return message("staging.reason_failed")
        form = _form(answer.address)
        if form.get("returnCountOnly") == "true":
            counts.append(payload.get("count"))
            continue
        features = payload.get("features")
        if (
            short
            or not isinstance(features, list)
            or form.get("resultOffset") != str(rows)
        ):
            return message("staging.reason_pages")
        rows += len(features)
        short = len(features) < ARCGIS_PAGE and not payload.get("exceededTransferLimit")
    if not short:
        return message("staging.reason_pages")
    if any(count != rows for count in counts):
        return message(
            "staging.reason_count",
            rows=rows,
            counts=", ".join(str(count) for count in counts),
        )
    return None


def _prepare(run: _Run, part: _Part, on_notice: NoticeHook | None) -> _Kept | None:
    """A table of a run as its version's bytes and file; None, told, when left out."""
    answers = [answer.spooled() for answer in part.answers]
    why = _incomplete(run, part, answers)
    if why is not None:
        if on_notice is not None:
            on_notice(
                Notice(
                    "warning",
                    "staging_incomplete",
                    message(
                        "staging.incomplete", run=run.name, part=part.name, reason=why
                    ),
                )
            )
        return None
    data = encode(answers)
    archive = part.adapter.run_file(
        part.descriptor, data, filename=f"{run.name}/{part.name}"
    )
    if archive is None:
        if on_notice is not None:
            on_notice(
                Notice(
                    "warning",
                    "staging_incomplete",
                    message("staging.empty", run=run.name, part=part.name),
                )
            )
        return None
    return _Kept(run, part, data, archive)


def _days(runs: Sequence[_Run]) -> dict[tuple[str, date], list[_Answer]]:
    """The good answers of the captures of each dataset and UTC day of the runs."""
    days: dict[tuple[str, date], list[_Answer]] = {}
    for run in runs:
        for descriptor, answer in run.captures:
            days.setdefault((descriptor.key, run.time.date()), []).append(answer)
    return dict(sorted(days.items()))


def _identity(record: object) -> Identity:
    """The identity of a line of a sealed capture; ValueError for no such line."""
    if not isinstance(record, dict):
        raise ValueError(message("captures.record_not_object"))
    time, address, sha, status = (
        record.get("time"),
        record.get("address"),
        record.get("sha256"),
        record.get("status"),
    )
    if (
        not isinstance(time, str)
        or not isinstance(address, str)
        or not isinstance(sha, str)
        or isinstance(status, bool)
        or not isinstance(status, int)
    ):
        raise ValueError(message("captures.record_invalid", time=time))
    return (time, address, sha, status)


class _Stored:
    """
    The current version of a day's capture, read a line at a time.

    A day of S0's backfill holds about 500 MB of answers: the version is read for
    its identities first, then again in order with the bodies.

    Raises
    ------
    ObserwatorDataError
        If the version does not match its sidecar or is no sealed capture.
    """

    def __init__(self, root: Path, entry: StoreEntry) -> None:
        assert entry.version is not None and entry.meta is not None
        self.path = entry.version
        self.extra = entry.meta.extra
        self._name = entry.version.relative_to(root).as_posix()
        self.identities: set[Identity] = set()
        self.addresses: Counter[str] = Counter()
        try:
            if _sha256_file(self.path) != entry.meta.sha256:
                raise ValueError(
                    message(
                        "reader.checksum_does_not_match_sidecar",
                        name=self.path.name,
                        path=self.path,
                    )
                )
            for record in self._records():
                identity = _identity(record)
                self.identities.add(identity)
                self.addresses[identity[1]] += 1
        except (OSError, ValueError, EOFError, zlib.error) as exc:
            raise self._corrupt(exc) from exc

    def _corrupt(self, exc: BaseException) -> ObserwatorDataError:
        return ObserwatorDataError(
            message("captures.corrupt_capture", version=self._name, reason=reason(exc))
        )

    def _records(self) -> Iterator[object]:
        with gzip.open(self.path, "rb") as stream:
            for line in stream:
                if line.strip():
                    yield json.loads(line)

    def runs(self) -> list[str]:
        """The runs of an interim capture the version holds (``extra.staging.runs``)."""
        staging = self.extra.get("staging")
        runs = staging.get("runs") if isinstance(staging, dict) else None
        return (
            [run for run in runs if isinstance(run, str)]
            if isinstance(runs, list)
            else []
        )

    def answers(self, repeated: set[str]) -> Iterator[Spooled]:
        """
        The answers in order, each with its body.

        The last body of each address of ``repeated`` is held for the ``seen`` lines
        that repeat it; no other body is.
        """
        previous: dict[str, Spooled] = {}
        last: Identity | None = None
        try:
            for record in self._records():
                answer = from_record(record, previous=previous)
                if last is not None and answer.identity <= last:
                    raise ValueError(
                        message("staging.capture_unordered", version=self._name)
                    )
                last = answer.identity
                if answer.address in repeated:
                    previous[answer.address] = answer
                yield answer
        except (OSError, ValueError, EOFError, zlib.error) as exc:
            raise self._corrupt(exc) from exc


def _merged(stored: Iterator[Spooled], fresh: Sequence[_Answer]) -> Iterator[Spooled]:
    """The stored answers and the fresh ones (sorted, none stored) in identity order."""
    pending = iter(fresh)
    old = next(stored, None)
    new = next(pending, None)
    while old is not None or new is not None:
        if new is None or (old is not None and old.identity < new.identity):
            assert old is not None
            yield old
            old = next(stored, None)
        else:
            yield new.spooled()
            new = next(pending, None)


def _stored_day(raw: Path | None, archive: ArchiveFile) -> _Stored | None:
    """The current version of a capture day's slot, None without one."""
    if raw is None:
        return None
    entry = current_version(raw, slot=_archive_slot(archive))
    if entry is None or entry.version is None or entry.meta is None:
        return None
    return _Stored(raw, entry)


def _keep_day(
    raw: Path,
    descriptor: DatasetDescriptor,
    day: date,
    answers: Sequence[_Answer],
    *,
    on_notice: NoticeHook | None,
    cancel: Cancel | None,
) -> OperationResult:
    """
    The capture of one dataset and day: its current version joined with the answers.

    ``unchanged`` when the current version holds every answer; else one version of
    them all, sealed into a file below the root's ``.incoming`` a line at a time while
    the provider reads them for ``extra.capture`` (`ProviderAdapter.capture_extra`).
    """
    archive = _capture_file(descriptor, day)
    slot = _archive_slot(archive)
    stored = _stored_day(raw, archive)
    known = stored.identities if stored is not None else set()
    fresh = {
        answer.identity: answer for answer in answers if answer.identity not in known
    }
    if stored is not None and not fresh:
        return OperationResult(slot, "unchanged", stored.path, None)
    ordered = [fresh[identity] for identity in sorted(fresh)]
    counted = Counter(stored.addresses) if stored is not None else Counter[str]()
    counted.update(answer.address for answer in ordered)
    repeated = {address for address, count in counted.items() if count > 1}
    runs = sorted(
        set(stored.runs() if stored is not None else ())
        | {answer.run for answer in answers}
    )
    adapter = get_provider(descriptor.provider).adapter
    incoming = raw / ".incoming"
    incoming.mkdir(exist_ok=True)
    scratch = incoming / f"{socket.gethostname()}_{os.getpid()}_{uuid.uuid4().hex}"
    scratch.mkdir()
    try:
        target = scratch / PurePosixPath(archive.server_path).name
        with target.open("xb") as stream:
            sealer = Sealer(stream)
            merged = _merged(
                stored.answers(repeated) if stored is not None else iter(()), ordered
            )

            def sealed() -> Iterator[Spooled]:
                for answer in merged:
                    if cancel is not None and cancel():
                        raise ObserwatorCancelledError(_CANCELLED)
                    sealer.write(answer)
                    yield answer

            through = sealed()
            extra = adapter.capture_extra(descriptor.key, through)
            for _ in through:
                pass
            sealer.close()
            stream.flush()
            os.fsync(stream.fileno())
        written = write_capture(
            raw,
            archive=archive,
            data=target,
            answers=sealer.count,
            extra=extra,
            on_notice=on_notice,
            cancel=cancel,
            provenance={"staging": {"runs": runs}},
        )
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    return OperationResult(slot, written.status, written.path, None)


def _keep(
    raw: Path,
    kept: _Kept,
    *,
    on_notice: NoticeHook | None,
    cancel: Cancel | None,
) -> OperationResult:
    """
    A table of a run as its version, dated by the run (`write_archive`).

    A new version of a slot that held one at the run's time gives the provider's
    notices of the replacement (PIG-PIB's ``month_republished``).
    """
    archive = kept.archive
    slot = _archive_slot(archive)
    prior = _current(raw, slot, kept.run.time)
    written = write_archive(
        raw,
        archive=archive,
        response=DownloadResult(kept.data, archive.url, None, None, None),
        on_notice=on_notice,
        cancel=cancel,
        downloaded_at=kept.run.time,
        provenance={"staging": {"run": kept.run.name}},
    )
    if (
        written.status == "new"
        and prior is not None
        and prior.version is not None
        and on_notice is not None
    ):
        try:
            notices = kept.part.adapter.replaced(
                archive, prior.version.read_bytes(), kept.data
            )
        except (ObserwatorDataError, OSError) as exc:
            notices = (
                Notice(
                    "warning", "archive_failed", f"{archive.server_path}: {reason(exc)}"
                ),
            )
        for notice in notices:
            on_notice(notice)
    return OperationResult(slot, written.status, written.path, None)


def import_staging(
    raw_root: RootArg,
    staging: PathArg,
    /,
    *,
    on_progress: ProgressHook | None = None,
    on_notice: NoticeHook | None = None,
    cancel: Cancel | None = None,
) -> ImportReport:
    """
    Import the runs of an interim capture into the raw root (`store import --staging`).

    The module's rules: every file checked first, the runs in time order, each table
    of a run one version dated by the run, the answers of the night's harvest one
    capture per UTC day joined with the day's version.

    Parameters
    ----------
    raw_root : str, os.PathLike or StoreHandle
        The raw root; created with its marker when new or empty.
    staging : str or os.PathLike
        The directory of the runs (``<YYYY-MM-DDTHHMMSSZ>/manifest.jsonl``).
    on_progress : ProgressHook or None, optional
        Called after each run read (unit ``run``) and each version kept (``archive``).
    on_notice : NoticeHook or None, optional
        Receives what each run leaves out (``staging_left_out``, ``staging_failed``,
        ``staging_incomplete``, ``staging_open``) and the notices of the writes.
    cancel : Cancel or None, optional
        Polled between runs and versions and while a day is sealed; once it returns
        ``True`` the import stops with ``cancelled`` (what was written stays
        complete).

    Returns
    -------
    ImportReport
        The provider, the version of each table and day (``new``, ``relabeled`` or
        ``unchanged``) and every version as ``files[]``; no series and no catalog.

    Raises
    ------
    ObserwatorValidationError
        Before anything is written (``details.option`` ``staging``, ``details.path``
        the file): no directory of runs, a manifest that cannot be read or holds a
        line that is no record, a file missing or not matching its record, or
        answers of no provider's interim capture.
    ObserwatorStoreError
        If the root is one of the other kind or has a layout without its marker.
    ObserwatorStoreConflictError
        If the root nests a store or holds other files, or the sealing of captures
        stayed locked (``sync_locked``).
    ObserwatorDataError
        If a stored version cannot be read or a table's answers cannot be read.
    """
    raw = refuse_root(raw_root, kind="raw")
    lenient_store(raw_root, kind="raw")
    owner, runs = _read(staging, on_progress=on_progress, cancel=cancel)
    items: list[OperationResult] = []
    files: list[FileResult] = []

    def report(*, cancelled: bool) -> ImportReport:
        return ImportReport(owner.id, tuple(items), (), None, cancelled, tuple(files))

    def stopped() -> bool:
        return cancel is not None and cancel()

    if runs is None:
        return report(cancelled=True)
    for run in runs:
        _tell(run, on_notice)
    prepare_store(raw_root, kind="raw")
    forward = _forward(on_notice)
    days = _days(runs)
    total = sum(len(run.parts) for run in runs) + len(days)
    done = 0

    def kept(result: OperationResult, text: Message) -> None:
        nonlocal done
        items.append(result)
        if result.version is not None and result.status != "failed":
            files.append(
                version_file(result.version, result.status)  # type: ignore[arg-type]
            )
        done += 1
        if on_progress is not None:
            on_progress(Progress(done, total, "archive", result.status, text))

    try:
        for run in runs:
            for part in run.parts.values():
                if stopped():
                    return report(cancelled=True)
                prepared = _prepare(run, part, on_notice)
                if prepared is None:
                    done += 1
                    continue
                result = _keep(raw, prepared, on_notice=forward, cancel=cancel)
                text = message(
                    "staging.version_kept",
                    run=run.name,
                    part=part.name,
                    slot=result.slot,
                )
                kept(result, text)
        if days:
            with _sync_lock(cancel=cancel):
                for (key, day), answers in days.items():
                    if stopped():
                        return report(cancelled=True)
                    result = _keep_day(
                        raw,
                        get_dataset(key),
                        day,
                        answers,
                        on_notice=forward,
                        cancel=cancel,
                    )
                    text = message(
                        "staging.day_kept",
                        answers=len({answer.identity for answer in answers}),
                        day=day.isoformat(),
                        slot=result.slot,
                    )
                    kept(result, text)
    except ObserwatorCancelledError:
        return report(cancelled=True)
    return report(cancelled=False)


def _stored_versions(raw: Path | None, kept: _Kept) -> list[_Known]:
    """Every version of a table's slot: its time, its bytes and its content."""
    if raw is None:
        return []
    archive = kept.archive
    slot = _validate_slot(raw, _archive_slot_dir(archive.server_path))
    form = kept.part.descriptor.content_form
    found: list[_Known] = []
    for _, meta in _existing(
        slot, PurePosixPath(archive.server_path).name, archive=True
    ):
        stored = meta.get("content_form")
        content = (
            meta.get("content_sha256")
            if isinstance(stored, str) and stored_form(stored) == form
            else None
        )
        found.append(
            _Known(
                _timestamp(str(meta["downloaded_at"])),
                str(meta["sha256"]),
                content if isinstance(content, str) else None,
            )
        )
    return found


def _plan_version(
    raw: Path | None, planned: dict[str, list[_Known]], kept: _Kept
) -> Literal["current", "newer", "missing"]:
    """
    What the import does with a table of a run, the earlier runs' versions included.

    ``current``: a version holds its bytes, or the version current at the run's time
    holds its content; otherwise ``missing`` (the slot's first version) or ``newer``.
    """
    slot = _archive_slot(kept.archive)
    versions = planned.get(slot)
    if versions is None:
        versions = planned[slot] = _stored_versions(raw, kept)
    sha = hashlib.sha256(kept.data).hexdigest()
    if any(version.sha256 == sha for version in versions):
        return "current"
    form = kept.part.descriptor.content_form
    content = None if form is None else content_sha256(kept.data, form=form)
    prior = max(
        (version for version in versions if version.at <= kept.run.time),
        key=lambda version: version.at,
        default=None,
    )
    if prior is not None and content is not None and prior.content == content:
        return "current"
    status: Literal["newer", "missing"] = "newer" if versions else "missing"
    versions.append(_Known(kept.run.time, sha, content))
    return status


def check_staging(
    raw_root: RootArg,
    staging: PathArg,
    /,
    *,
    on_progress: ProgressHook | None = None,
    on_notice: NoticeHook | None = None,
    cancel: Cancel | None = None,
) -> StorePlan:
    """
    Plan `import_staging` without writing: every file is read and checked as it reads.

    Parameters
    ----------
    raw_root : str, os.PathLike or StoreHandle
        The raw root; it need not exist.
    staging : str or os.PathLike
        The directory of the runs, as `import_staging` takes it.
    on_progress : ProgressHook or None, optional
        Called after each run read and once with the overall status.
    on_notice : NoticeHook or None, optional
        Receives what each run leaves out, as `import_staging` tells it.
    cancel : Cancel or None, optional
        Polled between runs and tables; once it returns ``True`` the plan is
        ``cancelled`` with the actions so far.

    Returns
    -------
    StorePlan
        ``obserwator-plan/1`` of the raw root without items: one ``store import``
        action per complete table of a run (``current`` when a version holds its
        bytes or the version current at the run's time its content, else
        ``missing`` for a slot's first version or ``newer``; the runs before it
        planned too) and one per capture day (``current`` when its current version
        holds every answer, ``newer``, ``missing``). A root that a write turns away
        is planned as one ``conflict`` action.

    Raises
    ------
    ObserwatorValidationError
        As `import_staging`, before anything else.
    ObserwatorStoreError
        If the root is one of the other kind or has a layout without its marker.
    ObserwatorDataError
        If a stored version or a table's answers cannot be read.
    """
    refused = root_conflict_plan(_IMPORT, raw_root, kind="raw")
    if refused is not None:
        return refused
    handle = lenient_store(raw_root, kind="raw")
    raw = handle.root if handle.root.exists() else None
    owner, runs = _read(staging, on_progress=on_progress, cancel=cancel)
    actions: list[PlanAction] = []

    def plan(*, cancelled: bool = False) -> StorePlan:
        return StorePlan(
            "obserwator-plan/1",
            handle.root,
            datetime.now(UTC),
            (),
            {},
            tuple(actions),
            cancelled=cancelled,
        )

    def stopped() -> bool:
        return cancel is not None and cancel()

    if runs is None:
        return plan(cancelled=True)
    for run in runs:
        _tell(run, on_notice)
    planned: dict[str, list[_Known]] = {}
    for run in runs:
        for part in run.parts.values():
            if stopped():
                return plan(cancelled=True)
            prepared = _prepare(run, part, on_notice)
            if prepared is None:
                continue
            actions.append(
                PlanAction(
                    _IMPORT,
                    _plan_version(raw, planned, prepared),
                    message(
                        "staging.plan_version",
                        run=run.name,
                        part=part.name,
                        slot=_archive_slot(prepared.archive),
                    ),
                )
            )
    for (key, day), answers in _days(runs).items():
        if stopped():
            return plan(cancelled=True)
        archive = _capture_file(get_dataset(key), day)
        stored = _stored_day(raw, archive)
        unique = {answer.identity for answer in answers}
        status: Literal["current", "newer", "missing"] = (
            "missing"
            if stored is None
            else "current"
            if unique <= stored.identities
            else "newer"
        )
        actions.append(
            PlanAction(
                _IMPORT,
                status,
                message(
                    "staging.plan_day",
                    answers=len(unique),
                    day=day.isoformat(),
                    slot=_archive_slot(archive),
                ),
            )
        )
    if on_progress is not None:
        overall = (
            "current"
            if all(action.status == "current" for action in actions)
            else "newer"
        )
        on_progress(
            Progress(
                len(actions),
                len(actions),
                "action",
                overall,
                message("staging.plan_done", provider=owner.id),
            )
        )
    return plan()
