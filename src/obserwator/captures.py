"""
Captures: every answer of a provider's server kept as it came (P14; ADR-030 D3, D5-D7, D9).

A capture dataset (``archive_scope`` ``country_day``, `obserwator.datasets.CAPTURE_SCOPE`)
gathers the answers of one source of current data. Each answer goes, as it came, to the
capture spool ``<state_dir>/obserwator/captures/<dataset>/<YYYY-MM-DD>/`` (the UTC day
of the answer's time): one file per answer, created with ``O_EXCL`` and named by that
time and the SHA-256 of the body, so the GUI, the hourly poll and a CLI run write it
without a lock and never inside a root (D7). ``store sync`` of the dataset seals every
closed UTC day of the spool into one archive version (`obserwator.store.captures`).

- `keep_response` is the hook of the library's requests (``obserwator.fetch``): an
  answer whose address belongs to a capture dataset (`capture_dataset`, the declared
  datasets of ADR-030 D8 included) goes to the provider's adapter
  (`ProviderAdapter.capture`, by default `write_spool`). A failed spool write is one
  warning record (event ``capture_failed``) and a ``config show`` problem
  (`spool_problem`); the answer is still served.
- The address is kept without any credential (`strip_credentials`): no user and
  password, no query parameter that carries a key, no provider key anywhere in it.
- `[obserwator.capture]` of ``nogat.toml`` sets each source (a dataset whose tier is
  not ``verified``) ``public`` or ``private`` (P15, D5); the default follows the
  source's terms (`ProviderAdapter.publication_default`). `capture_report` is the
  section of ``config show``.
- `poll_current` is the hourly poll (D9, P16): one request per source an adapter
  declares (`ProviderAdapter.polled`), written to the spool only; a source polled
  sooner than its declared interval allows is skipped.
- `harvest` is the night's harvest (D9): the paced requests of a dataset an adapter
  harvests (`ProviderAdapter.harvested`, `harvest_requests`) for a range of closed UTC
  days, every answer written to the spool; ``store sync`` with ``pace_until`` runs it
  before sealing.
"""

from __future__ import annotations

import base64
import binascii
import contextlib
import hashlib
import json
import logging
import os
import re
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import ClassVar, Literal, cast
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx

from obserwator import _environment as environment
from obserwator.config import Settings, _provider_secret
from obserwator.datasets import (
    CAPTURE_SCOPE,
    DatasetDescriptor,
    ProviderDescriptor,
    _parse_stations,
    _source_address,
    datasets,
    get_dataset,
    get_provider,
    providers,
)
from obserwator.exceptions import (
    ErrorCode,
    ObserwatorCancelledError,
    ObserwatorError,
    ObserwatorValidationError,
)
from obserwator.fetch import (
    CONNECTION_FAILURES,
    DEFAULT_TIMEOUT,
    Clock,
    PacedOutcome,
    PacedRequest,
    PacedSession,
    _source_error,
)
from obserwator.messages import Message, message, reason
from obserwator.output import FileResult
from obserwator.providers.base import Answer, PolledSource, ProviderAdapter
from obserwator.store.types import (
    Cancel,
    HarvestReport,
    Notice,
    NoticeHook,
    OperationResult,
    PlanAction,
    Progress,
    ProgressHook,
)

__all__ = [
    "CaptureSource",
    "PollReport",
    "PolledAnswer",
    "Spooled",
    "capture_dataset",
    "capture_datasets",
    "capture_report",
    "capture_sources",
    "harvest",
    "keep",
    "keep_response",
    "publication",
    "publication_sources",
    "spool_problem",
    "spool_root",
    "strip_credentials",
    "write_spool",
]

Publication = Literal["public", "private"]
SECTION = "capture"
"""The table of ``[obserwator]`` that sets the publication state of each source (P15)."""
STATES: tuple[Publication, ...] = ("public", "private")
SPOOL = "captures"
"""Directory of the spool in ``<state_dir>/obserwator``."""
FAILURE = "capture-failure.json"
"""The last failed spool write, in ``<state_dir>/obserwator``, until a write succeeds."""
POLLED = ".polled"
"""The time of the last poll of a source, in its directory of the spool."""
EVENT = "capture_failed"
"""The ``event`` of the warning record of a failed spool write."""

_LOG = logging.getLogger(__name__)
_TIME = "%Y-%m-%dT%H:%M:%S.%fZ"
_NAME_TIME = "%Y%m%dT%H%M%S.%fZ"
_SPOOL_NAME = re.compile(r"^([0-9]{8}T[0-9]{6}\.[0-9]{6}Z)_([0-9a-f]{64})\.json$")
_DAY = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
_SHA = re.compile(r"^[0-9a-f]{64}$")
# Query parameters that carry a credential by their name (lower case); a provider's
# own key is also removed by its value wherever it appears.
_CREDENTIAL_PARAMS = frozenset(
    {
        "access_key",
        "access_token",
        "accesskey",
        "api-key",
        "api_key",
        "apikey",
        "auth",
        "authorization",
        "bearer",
        "client_secret",
        "credential",
        "credentials",
        "id_token",
        "key",
        "pass",
        "passwd",
        "password",
        "pwd",
        "refresh_token",
        "secret",
        "sessionid",
        "sig",
        "signature",
        "token",
        "x-api-key",
    }
)
_REDACTED = "REDACTED"
# A poll may come this share of its interval early: the jitter of a timer.
_EARLY = 10


def _now() -> datetime:
    """The current UTC time (tests move it)."""
    return datetime.now(UTC)


def _stamp(moment: datetime) -> str:
    """An instant as the captures write it: UTC with microseconds and ``Z``."""
    return moment.astimezone(UTC).strftime(_TIME)


def _instant(text: str) -> datetime:
    """The instant of a `_stamp` text; ValueError for any other text."""
    return datetime.strptime(text, _TIME).replace(tzinfo=UTC)


# --------------------------------------------------------------------------
# Capture datasets and their sources
# --------------------------------------------------------------------------


def capture_datasets() -> tuple[DatasetDescriptor, ...]:
    """
    Every capture dataset of the registry, the declared ones included (ADR-030 D8).

    Returns
    -------
    tuple of DatasetDescriptor
        The datasets whose ``archive_scope`` is ``country_day``, in registry order.
    """
    return tuple(d for d in datasets(pending=True) if d.archive_scope == CAPTURE_SCOPE)


def publication_sources() -> tuple[DatasetDescriptor, ...]:
    """
    Every source with a publication state: a dataset whose tier is not ``verified`` (D5).

    A sub-daily series (``DatasetDescriptor.inputs``, ADR-031) is no source: its
    state follows its sources' (`publication`).

    Returns
    -------
    tuple of DatasetDescriptor
        The operational and telemetry datasets, the declared ones included, in
        registry order.
    """
    return tuple(
        d for d in datasets(pending=True) if d.tier != "verified" and d.inputs is None
    )


def _capture_descriptor(key: str | None) -> DatasetDescriptor | None:
    return next((d for d in capture_datasets() if d.key == key), None)


def _bare(url: str) -> str:
    """Scheme, host, port and path of an address: what a dataset's address is compared with."""
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    port = f":{parts.port}" if parts.port is not None else ""
    return f"{parts.scheme.lower()}://{host}{port}{parts.path}"


def capture_dataset(url: str, /) -> DatasetDescriptor | None:
    """
    The capture dataset an address belongs to: its source's server directory or below.

    Parameters
    ----------
    url : str
        An address a request asked.

    Returns
    -------
    DatasetDescriptor or None
        The capture dataset whose address (`obserwator.datasets._source_address`) is
        the address or a directory of it, the longest such; None for any other
        address (an archive, a station list).
    """
    bare = _bare(url)
    found: tuple[int, DatasetDescriptor] | None = None
    for descriptor in capture_datasets():
        address = _source_address(descriptor)
        if (bare == address or bare.startswith(f"{address}/")) and (
            found is None or len(address) > found[0]
        ):
            found = (len(address), descriptor)
    return None if found is None else found[1]


def strip_credentials(url: str, provider: ProviderDescriptor | None = None, /) -> str:
    """
    An address without any credential: what a capture keeps of it (P3, ADR-030 D6).

    The user and password of the address, its fragment and every query parameter
    whose name carries a credential (``key``, ``api_key``, ``token``, ``signature``
    and the like) are removed; with a provider that declares a credential (P3), its
    key is removed by its value too: a parameter holding it goes, and the key left
    anywhere else in the address is replaced by ``REDACTED``. An address without
    any of them is returned as it was.

    Parameters
    ----------
    url : str
        The address asked.
    provider : ProviderDescriptor or None, optional
        The provider whose key may be in it.

    Returns
    -------
    str
        The address to keep.
    """
    parts = urlsplit(url)
    secrets: list[str] = []
    if provider is not None and provider.credential is not None:
        key, _ = _provider_secret(provider)
        if key:
            secrets.append(key)
    netloc = parts.netloc.rpartition("@")[2]
    pairs = parse_qsl(parts.query, keep_blank_values=True)
    kept = [
        (name, value)
        for name, value in pairs
        if name.lower() not in _CREDENTIAL_PARAMS
        and not any(secret in name or secret in value for secret in secrets)
    ]
    query = parts.query if len(kept) == len(pairs) else urlencode(kept)
    address = urlunsplit((parts.scheme, netloc, parts.path, query, ""))
    for secret in secrets:
        address = address.replace(secret, _REDACTED)
    return address


# --------------------------------------------------------------------------
# The spool
# --------------------------------------------------------------------------


def spool_root() -> Path:
    """
    The capture spool: ``<state_dir>/obserwator/captures`` (ADR-030 D7).

    Returns
    -------
    pathlib.Path
        Absolute, ``~`` expanded; it need not exist.
    """
    return (Settings().state_dir / environment.TOOL / SPOOL).expanduser().absolute()


def _failure_path() -> Path:
    return (Settings().state_dir / environment.TOOL / FAILURE).expanduser().absolute()


@dataclass(frozen=True)
class Spooled:
    """
    One answer kept in the spool or in a sealed capture.

    Attributes
    ----------
    time : str
        When it arrived: UTC with microseconds and ``Z``
        (``2026-11-22T10:15:03.123456Z``).
    address : str
        The address asked, without any credential.
    status : int
        Its HTTP status.
    sha256 : str
        SHA-256 of the body.
    content : bytes
        The body as it came.
    """

    time: str
    address: str
    status: int
    sha256: str
    content: bytes

    @property
    def identity(self) -> tuple[str, str, str, int]:
        """What tells two answers apart: time, address, body and status."""
        return (self.time, self.address, self.sha256, self.status)

    def record(self, *, seen: bool = False) -> dict[str, object]:
        """
        The JSON object of the answer: its spool file, a line of its capture.

        Parameters
        ----------
        seen : bool, optional
            The answer equals the one before it from the same address: the body is
            left out and ``seen`` is true.

        Returns
        -------
        dict
            ``time``, ``address``, ``status``, ``sha256`` and ``body`` (UTF-8 text)
            or ``body_base64`` (any other bytes), or ``seen``.
        """
        fields: dict[str, object] = {
            "time": self.time,
            "address": self.address,
            "status": self.status,
            "sha256": self.sha256,
        }
        if seen:
            fields["seen"] = True
            return fields
        try:
            fields["body"] = self.content.decode("utf-8")
        except UnicodeDecodeError:
            fields["body_base64"] = base64.b64encode(self.content).decode("ascii")
        return fields


def _text_field(record: Mapping[str, object], name: str) -> str:
    value = record.get(name)
    if not isinstance(value, str):
        raise ValueError(message("captures.field_not_text", name=name))
    return value


def from_record(
    record: object, *, previous: Mapping[str, Spooled] | None = None
) -> Spooled:
    """
    The answer of a JSON object of the captures (`Spooled.record`).

    Parameters
    ----------
    record : object
        A decoded spool file or line of a capture.
    previous : Mapping of str to Spooled, optional
        The answer before it from each address: the body of a ``seen`` record.

    Returns
    -------
    Spooled
        The answer, its body checked against ``sha256``.

    Raises
    ------
    ValueError
        If the object is not such a record, its body does not match its
        SHA-256, or a ``seen`` record follows no equal answer of its address.
    """
    if not isinstance(record, dict):
        raise ValueError(message("captures.record_not_object"))
    time = _text_field(record, "time")
    address = _text_field(record, "address")
    sha = _text_field(record, "sha256")
    status = record.get("status")
    if isinstance(status, bool) or not isinstance(status, int) or not _SHA.match(sha):
        raise ValueError(message("captures.record_invalid", time=time))
    _instant(time)
    if record.get("seen") is True:
        before = (previous or {}).get(address)
        if before is None or (before.sha256, before.status) != (sha, status):
            raise ValueError(message("captures.seen_without_answer", time=time))
        content = before.content
    elif isinstance(record.get("body"), str):
        content = cast(str, record["body"]).encode("utf-8")
    elif isinstance(record.get("body_base64"), str):
        try:
            content = base64.b64decode(cast(str, record["body_base64"]), validate=True)
        except binascii.Error as exc:
            raise ValueError(message("captures.record_invalid", time=time)) from exc
    else:
        raise ValueError(message("captures.record_invalid", time=time))
    if hashlib.sha256(content).hexdigest() != sha:
        raise ValueError(message("captures.body_sha_mismatch", time=time))
    return Spooled(time, address, status, sha, content)


def _canonical(record: Mapping[str, object]) -> bytes:
    """A record as one line: sorted keys, no white space, UTF-8, a final line feed."""
    text = json.dumps(record, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return (text + "\n").encode("utf-8")


def write_spool(answer: Answer, /) -> Path | None:
    """
    Write one answer of a capture dataset to the spool (ADR-030 D7).

    The file is ``<spool>/<dataset>/<YYYY-MM-DD>/<YYYYMMDDTHHMMSS.ffffffZ>_<sha256>.json``
    (the UTC day and time of the answer, the SHA-256 of its body), created with
    ``O_EXCL``, written and ``fsync``-ed: one JSON object (`Spooled.record`) with the
    address without any credential (`strip_credentials`). The same answer at the same
    instant is kept once: an existing file of the name is the answer already kept.

    Parameters
    ----------
    answer : Answer
        The answer as it came.

    Returns
    -------
    pathlib.Path or None
        The spool file; None when the answer's dataset is no capture dataset.

    Raises
    ------
    OSError
        If the spool cannot be written (a partial file is removed).
    """
    descriptor = _capture_descriptor(answer.dataset)
    if descriptor is None:
        return None
    moment = answer.received_at.astimezone(UTC)
    digest = hashlib.sha256(answer.content).hexdigest()
    spooled = Spooled(
        _stamp(moment),
        strip_credentials(answer.url, get_provider(descriptor.provider)),
        answer.status,
        digest,
        answer.content,
    )
    directory = spool_root() / descriptor.key / moment.date().isoformat()
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{moment.strftime(_NAME_TIME)}_{digest}.json"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    try:
        handle = os.open(path, flags, 0o666)
    except FileExistsError:
        return path
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(_canonical(spooled.record()))
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        with contextlib.suppress(OSError):
            path.unlink()
        raise
    return path


def read_spooled(path: Path, /) -> Spooled:
    """
    The answer of one spool file, checked against its name.

    Parameters
    ----------
    path : pathlib.Path
        A file of the spool.

    Returns
    -------
    Spooled
        The answer.

    Raises
    ------
    OSError
        If the file cannot be read.
    ValueError
        If the file is no complete spool file (another name, no JSON record, a body
        that does not match its SHA-256 or its name).
    """
    named = _SPOOL_NAME.fullmatch(path.name)
    if named is None:
        raise ValueError(message("captures.not_spool_file", name=path.name))
    spooled = from_record(json.loads(path.read_bytes()))
    if (
        spooled.sha256 != named[2]
        or _instant(spooled.time).strftime(_NAME_TIME) != named[1]
    ):
        raise ValueError(message("captures.name_does_not_match", name=path.name))
    return spooled


def spool_days(key: str, /) -> list[date]:
    """
    The UTC days of a capture dataset that the spool holds a directory of, in order.

    Parameters
    ----------
    key : str
        A capture dataset.

    Returns
    -------
    list of datetime.date
        The days; none when the spool holds nothing of the dataset.
    """
    directory = spool_root() / key
    try:
        names = [entry.name for entry in os.scandir(directory) if entry.is_dir()]
    except (FileNotFoundError, NotADirectoryError):
        return []
    days = []
    for name in names:
        if not _DAY.fullmatch(name):
            continue
        with contextlib.suppress(ValueError):
            days.append(date.fromisoformat(name))
    return sorted(days)


def spool_files(key: str, day: date, /) -> list[Path]:
    """
    The files of one capture dataset and day in the spool, by name (time order).

    Parameters
    ----------
    key : str
        A capture dataset.
    day : datetime.date
        A UTC day.

    Returns
    -------
    list of pathlib.Path
        Every file of the day's directory, complete or not.
    """
    directory = spool_root() / key / day.isoformat()
    try:
        return sorted(
            Path(entry.path)
            for entry in os.scandir(directory)
            if entry.is_file(follow_symlinks=False)
        )
    except (FileNotFoundError, NotADirectoryError):
        return []


# --------------------------------------------------------------------------
# The hook of the requests
# --------------------------------------------------------------------------


def _record_failure(answer: Answer, error: str) -> None:
    """Remember the failed write for ``config show`` (best effort)."""
    record = {
        "time": _stamp(_now()),
        "dataset": answer.dataset,
        "error": error,
    }
    with contextlib.suppress(Exception):
        path = _failure_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(_canonical(record))


def _failed(answer: Answer, exc: BaseException) -> Message:
    """One warning record of a failed spool write, remembered for ``config show``."""
    try:
        spool: object = spool_root()
    except Exception:
        spool = SPOOL
    text = message(
        "captures.spool_failed",
        dataset=answer.dataset,
        spool=spool,
        reason=reason(exc),
    )
    known = isinstance(exc, OSError | ObserwatorError | ValueError)
    _LOG.warning("%s", text, exc_info=None if known else exc, extra={"event": EVENT})
    _record_failure(answer, str(reason(exc)))
    return text


def _recovered() -> None:
    """A write succeeded: the failure ``config show`` reports is past."""
    with contextlib.suppress(Exception):
        _failure_path().unlink(missing_ok=True)


def _adapter(answer: Answer) -> ProviderAdapter | None:
    descriptor = _capture_descriptor(answer.dataset)
    return None if descriptor is None else get_provider(descriptor.provider).adapter


def keep(answer: Answer, /) -> Path | None:
    """
    Hand an answer to its provider's adapter (`ProviderAdapter.capture`); never fail.

    A failure is one warning record (event ``capture_failed``) and a ``config show``
    problem until a write succeeds; the caller serves the answer anyway (D7).

    Parameters
    ----------
    answer : Answer
        The answer as it came, its dataset a capture dataset (others are not kept).

    Returns
    -------
    pathlib.Path or None
        The spool file; None when nothing was kept.
    """
    try:
        adapter = _adapter(answer)
        if adapter is None:
            return None
        path = adapter.capture(answer)
    except Exception as exc:
        _failed(answer, exc)
        return None
    if path is not None:
        _recovered()
    return path


def keep_response(response: httpx.Response, /) -> Path | None:
    """
    Keep a library request's answer whose address belongs to a capture dataset (P14).

    Called by the request paths of ``obserwator.fetch`` with every answer they
    receive (its status included) before it is checked; an answer of an archive or
    a station list is no capture and is left alone. The address of a POST of a form
    (an ArcGIS query of PIG-PIB, ADR-035) is its URL with the form as the query, so
    the pages of one query tell apart.

    Parameters
    ----------
    response : httpx.Response
        A read answer.

    Returns
    -------
    pathlib.Path or None
        The spool file; None when nothing was kept.
    """
    try:
        url = str(response.url)
        descriptor = capture_dataset(url)
        if descriptor is None:
            return None
        request = response.request
        if request.method == "POST" and request.headers.get(
            "content-type", ""
        ).startswith("application/x-www-form-urlencoded"):
            form = request.content.decode("utf-8")
            url = f"{url}{'&' if '?' in url else '?'}{form}"
        answer = Answer(
            url=strip_credentials(url, get_provider(descriptor.provider)),
            received_at=_now(),
            status=response.status_code,
            content=response.content,
            dataset=descriptor.key,
        )
    except Exception as exc:
        _LOG.warning("%s", reason(exc), exc_info=exc, extra={"event": EVENT})
        return None
    return keep(answer)


def _usable(directory: Path) -> bool:
    """Whether a directory could be created or written below its nearest existing part."""
    probe = directory
    while not probe.exists() and probe.parent != probe:
        probe = probe.parent
    return probe.is_dir() and os.access(probe, os.W_OK | os.X_OK)


def spool_problem() -> dict[str, object] | None:
    """
    The spool's problem for ``config show``: it cannot be written, or a write failed.

    Returns
    -------
    dict or None
        ``code`` ``capture_spool``, ``option`` ``state_dir`` and ``message``; None when
        the spool can be written and no write has failed since the last that did not.
    """
    root = spool_root()
    if not _usable(root):
        return {
            "code": "capture_spool",
            "option": "state_dir",
            "message": message("captures.spool_unwritable", spool=root),
        }
    try:
        failure = json.loads(_failure_path().read_bytes())
    except (OSError, ValueError):
        return None
    if not isinstance(failure, dict):
        return None
    return {
        "code": "capture_spool",
        "option": "state_dir",
        "message": message(
            "captures.spool_last_failure",
            time=failure.get("time"),
            dataset=failure.get("dataset"),
            spool=root,
            reason=failure.get("error"),
        ),
    }


# --------------------------------------------------------------------------
# Publication state (P15, ADR-030 D5)
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class CaptureSource:
    """
    The publication state of one source (P15, ADR-030 D5).

    Attributes
    ----------
    dataset : str
        A dataset whose tier is not ``verified``.
    tier : {"telemetry", "operational"}
        Its tier.
    state : {"public", "private"}
        ``public``: shown and downloadable in Obserwator and Archiwista;
        ``private``: stored, read by the CLI, the library and Archiwista's
        signed-in users only.
    source : {"default", "file"}
        Where the state comes from: its terms (`ProviderAdapter.publication_default`)
        or ``[obserwator.capture]`` of ``nogat.toml``.
    """

    dataset: str
    tier: str
    state: Publication
    source: Literal["default", "file"]


def _invalid(option: str, text: Message) -> ObserwatorValidationError:
    return ObserwatorValidationError(
        text, details={"option": option, "reason": "invalid_capture"}
    )


def _flatten(table: Mapping[str, object], prefix: str = "") -> dict[str, object]:
    """
    The keys of a table: a dotted TOML key (``pl.imgw.x = …``) nests tables.

    A source named twice (a quoted key ``"pl.imgw.x"`` beside the dotted one) is
    invalid: which of its states was meant cannot be told.
    """
    flat: dict[str, object] = {}
    for name, value in table.items():
        key = f"{prefix}{name}"
        found = _flatten(value, f"{key}.") if isinstance(value, dict) else {key: value}
        for source, state in found.items():
            if source in flat:
                raise _invalid(
                    f"{SECTION}.{source}",
                    message("captures.source_set_twice", source=source),
                )
            flat[source] = state
    return flat


def _given() -> dict[str, Publication]:
    """The states ``[obserwator.capture]`` sets, checked."""
    table = environment.config_file().sections.get(environment.TOOL, {}).get(SECTION)
    if table is None:
        return {}
    if not isinstance(table, dict):
        raise _invalid(SECTION, message("captures.section_not_table"))
    known = {d.key for d in publication_sources()}
    given: dict[str, Publication] = {}
    for key, value in _flatten(table).items():
        if key not in known:
            raise _invalid(
                f"{SECTION}.{key}",
                message(
                    "captures.unknown_source",
                    source=key,
                    sources=", ".join(sorted(known)),
                ),
            )
        if value not in STATES:
            raise _invalid(
                f"{SECTION}.{key}",
                message(
                    "captures.bad_state",
                    source=key,
                    value=json.dumps(value, default=str)[:80],
                    allowed=", ".join(STATES),
                ),
            )
        given[key] = value
    return given


def _sources(given: Mapping[str, Publication]) -> tuple[CaptureSource, ...]:
    return tuple(
        CaptureSource(
            d.key,
            d.tier,
            given.get(d.key)
            or get_provider(d.provider).adapter.publication_default(d.key),
            "file" if d.key in given else "default",
        )
        for d in publication_sources()
    )


def capture_sources() -> tuple[CaptureSource, ...]:
    """
    Every source's publication state in force and where it comes from (P15, D5).

    Returns
    -------
    tuple of CaptureSource
        One per dataset whose tier is not ``verified``, in registry order.

    Raises
    ------
    ObserwatorValidationError
        If ``[obserwator.capture]`` is no table, names no such source, sets a
        state other than ``public`` and ``private`` or sets a source twice
        (``details.option`` ``capture.<dataset>``, ``details.reason``
        ``invalid_capture``).
    """
    return _sources(_given())


def publication(key: str, /) -> Publication:
    """
    The publication state in force of one source; the defaults while the section is invalid.

    A sub-daily series built from the datasets of its ``inputs`` (ADR-031) is
    ``private`` when one of its sources is (P15: every series built from a private
    capture is left out of the public surfaces), ``public`` otherwise.

    Parameters
    ----------
    key : str
        A dataset whose tier is not ``verified``.

    Returns
    -------
    {"public", "private"}
        The state ``[obserwator.capture]`` sets, else the source's default.
    """
    derived = next((d for d in datasets() if d.key == key and d.inputs), None)
    if derived is not None:
        sources = {d.key for d in publication_sources()}
        states = [publication(item) for item in derived.inputs or () if item in sources]
        return "private" if "private" in states else "public"
    try:
        given = _given()
    except ObserwatorValidationError:
        given = {}
    descriptor = next(d for d in publication_sources() if d.key == key)
    return given.get(key) or get_provider(
        descriptor.provider
    ).adapter.publication_default(key)


def capture_report() -> tuple[dict[str, object], dict[str, object] | None]:
    """
    The captures of ``config show``: the spool and each source's state, and a problem.

    Returns
    -------
    tuple
        The section (``spool``: the spool's directory; ``sources``: per dataset its
        ``state``, ``tier``, ``source`` ``default`` or ``file`` and ``name``, the
        table or null) and the problem of an invalid ``[obserwator.capture]`` (code
        ``invalid_capture``, ``option``, ``message``; the defaults are listed and
        apply) or None.
    """
    problem: dict[str, object] | None = None
    try:
        sources = capture_sources()
    except ObserwatorValidationError as exc:
        sources = _sources({})
        problem = {
            "code": "invalid_capture",
            "option": exc.details.get("option", SECTION),
            "message": exc.detail,
        }
    return {
        "spool": str(spool_root()),
        "sources": {
            item.dataset: {
                "state": item.state,
                "tier": item.tier,
                "source": item.source,
                "name": f"[{environment.TOOL}.{SECTION}]"
                if item.source == "file"
                else None,
            }
            for item in sources
        },
    }, problem


# --------------------------------------------------------------------------
# The hourly poll (P16, ADR-030 D9)
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class PolledAnswer:
    """
    One source of the hourly poll (`poll_current`): its answer in the spool, or why not.

    Attributes
    ----------
    dataset : str
        The capture dataset of the source.
    url : str
        The address asked, without any credential.
    status : {"captured", "skipped", "failed", "cancelled"}
        ``captured``: the answer is in the spool; ``skipped``: the source was polled
        less than its interval ago (P16); ``failed``: no answer came, the server
        answered no success (an HTTP error or a redirect, which the library's
        requests refuse too; kept in the spool all the same) or the spool could not
        be written; ``cancelled``: not asked.
    http_status : int or None, optional
        The HTTP status of the answer; None without one.
    path : pathlib.Path or None, optional
        The spool file of the answer; None when nothing was kept.
    sha256 : str or None, optional
        SHA-256 of the body; None without an answer.
    polled_at : str or None, optional
        When the source was asked, or for ``skipped`` last asked (UTC, ``Z``).
    error : str or None, optional
        Why it failed or was skipped; None otherwise.
    error_code : ErrorCode or None, optional
        ``source_unavailable`` or ``io_error`` of a failure; None otherwise.
    """

    SCHEMA: ClassVar[str] = "obserwator-polled-answer/1"

    dataset: str
    url: str
    status: Literal["captured", "skipped", "failed", "cancelled"]
    http_status: int | None = None
    path: Path | None = None
    sha256: str | None = None
    polled_at: str | None = None
    error: str | None = None
    error_code: ErrorCode | None = None


@dataclass(frozen=True)
class PollReport:
    """
    Report of the hourly poll (``current poll``, P16, ADR-030 D9).

    Attributes
    ----------
    answers : tuple of PolledAnswer
        One per source of every adapter's `ProviderAdapter.polled`, in their order.
    cancelled : bool, optional
        Whether the poll was cancelled.
    files : tuple of FileResult, optional
        The spool files written (``written``), as ``files[]`` (DEV-19.19).
    """

    SCHEMA: ClassVar[str] = "obserwator-poll-report/1"

    answers: tuple[PolledAnswer, ...]
    cancelled: bool = False
    files: tuple[FileResult, ...] = ()


def _polled_sources() -> Iterator[tuple[ProviderAdapter, PolledSource]]:
    for provider in providers():
        for source in provider.adapter.polled:
            yield provider.adapter, source


def _last_poll(key: str) -> datetime | None:
    """When the poll last asked a source; None when never (or unreadable)."""
    try:
        return _instant((spool_root() / key / POLLED).read_text("utf-8").strip())
    except (OSError, ValueError):
        return None


def _mark_poll(key: str, moment: datetime) -> None:
    """Remember the poll of a source (best effort: a failure only loses the ceiling)."""
    directory = spool_root() / key
    with contextlib.suppress(OSError):
        directory.mkdir(parents=True, exist_ok=True)
        temporary = directory / f"{POLLED}.{os.getpid()}"
        temporary.write_text(_stamp(moment) + "\n", encoding="utf-8")
        os.replace(temporary, directory / POLLED)


def _due(source: PolledSource, last: datetime | None) -> datetime | None:
    """When a source may be polled again; None when it may be now (P16)."""
    if last is None:
        return None
    early = source.interval // _EARLY
    due = last + timedelta(seconds=source.interval - early)
    return due if _now() < due else None


def poll_plan() -> list[PlanAction]:
    """
    The plan of ``current poll --check``: per source the request, or why it waits.

    Returns
    -------
    list of PlanAction
        ``unverifiable`` for a source the poll would ask (a live read into the
        spool), ``current`` for one it would skip until its interval passes.
    """
    actions = []
    for _adapter, source in _polled_sources():
        last = _last_poll(source.dataset)
        due = _due(source, last)
        if due is None:
            detail = message(
                "captures.poll_planned",
                url=source.url,
                dataset=source.dataset,
                spool=spool_root() / source.dataset,
                interval=source.interval,
            )
            actions.append(PlanAction("current poll", "unverifiable", detail))
        else:
            assert last is not None
            actions.append(
                PlanAction(
                    "current poll",
                    "current",
                    _too_soon(source, last, due),
                )
            )
    return actions


def _too_soon(source: PolledSource, last: datetime, due: datetime) -> Message:
    return message(
        "captures.poll_too_soon",
        dataset=source.dataset,
        polled_at=_stamp(last),
        interval=source.interval,
        due=_stamp(due),
    )


def _file(path: Path) -> FileResult:
    data = path.read_bytes()
    return FileResult(path, len(data), hashlib.sha256(data).hexdigest(), "written")


def _poll_one(
    adapter: ProviderAdapter,
    source: PolledSource,
    *,
    timeout: float,
    notice: Callable[[Notice], None],
) -> tuple[PolledAnswer, FileResult | None]:
    """Ask one source and keep its answer (see `poll_current`)."""
    provider = adapter.provider
    url = strip_credentials(source.url, provider)
    last = _last_poll(source.dataset)
    due = _due(source, last)
    if due is not None:
        assert last is not None
        text = _too_soon(source, last, due)
        notice(Notice("info", "poll_skipped", text))
        return PolledAnswer(
            source.dataset, url, "skipped", polled_at=_stamp(last), error=text
        ), None
    asked = _now()
    _mark_poll(source.dataset, asked)
    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.get(source.url, headers=dict(source.headers))
    except httpx.HTTPError as exc:
        error = _source_error(exc, url, source=adapter.server_name)
        notice(Notice("warning", "capture_failed", error.detail))
        return PolledAnswer(
            source.dataset,
            url,
            "failed",
            polled_at=_stamp(asked),
            error=error.detail,
            error_code="source_unavailable",
        ), None
    answer = Answer(
        url=strip_credentials(str(response.url), provider),
        received_at=_now(),
        status=response.status_code,
        content=response.content,
        dataset=source.dataset,
    )
    digest = hashlib.sha256(answer.content).hexdigest()
    try:
        path = adapter.capture(answer)
        if path is None:
            raise ValueError(
                message("captures.not_capture_dataset", dataset=source.dataset)
            )
        written = _file(path)
    except Exception as exc:
        text = _failed(answer, exc)
        notice(Notice("warning", "capture_failed", text))
        return PolledAnswer(
            source.dataset,
            answer.url,
            "failed",
            http_status=answer.status,
            sha256=digest,
            polled_at=_stamp(asked),
            error=text,
            error_code="io_error",
        ), None
    _recovered()
    if not response.is_success:
        error = _source_error(
            httpx.HTTPStatusError(
                str(response.status_code), request=response.request, response=response
            ),
            url,
            source=adapter.server_name,
        )
        notice(Notice("warning", "capture_failed", error.detail))
        return PolledAnswer(
            source.dataset,
            answer.url,
            "failed",
            http_status=answer.status,
            path=path,
            sha256=digest,
            polled_at=_stamp(asked),
            error=error.detail,
            error_code="source_unavailable",
        ), written
    return PolledAnswer(
        source.dataset,
        answer.url,
        "captured",
        http_status=answer.status,
        path=path,
        sha256=digest,
        polled_at=_stamp(asked),
    ), written


def poll_current(
    *,
    on_progress: ProgressHook | None = None,
    on_notice: NoticeHook | None = None,
    cancel: Cancel | None = None,
) -> PollReport:
    """
    Ask each polled source of current data once and keep its answer in the spool (D9).

    The hourly poll of ADR-030 D9, which the deployment's timer runs
    (``obserwator-current.timer``, at :15): one GET of each source an adapter
    declares (`ProviderAdapter.polled`; IMGW-PIB's ``api/data/hydro``, ``meteo``,
    ``synop``, ``warningshydro``, ``warningsmeteo`` and hydro.imgw.pl's map of water
    states), one at a time, every answer written to the capture spool through its
    adapter (`ProviderAdapter.capture`) and nothing else: no root is written and no
    record parsed. ``store sync`` of the six capture datasets seals the closed days
    into versions. The declared interval of a source is a ceiling (P16): a source
    asked less than its interval ago (less a tenth, a timer's jitter) is skipped.

    Parameters
    ----------
    on_progress : ProgressHook or None, optional
        Called after each source with its status.
    on_notice : NoticeHook or None, optional
        Receives a ``capture_failed`` warning for each failed source and a
        ``poll_skipped`` notice for each skipped one.
    cancel : Cancel or None, optional
        Polled before each source; once it returns True the rest are
        ``cancelled``.

    Returns
    -------
    PollReport
        One `PolledAnswer` per source and the spool files written.
    """
    sources = list(_polled_sources())
    answers: list[PolledAnswer] = []
    files: list[FileResult] = []
    stopped = False

    def notice(item: Notice) -> None:
        if on_notice is not None:
            on_notice(item)

    for index, (adapter, source) in enumerate(sources, start=1):
        stopped = stopped or (cancel is not None and cancel())
        if stopped:
            answers.append(
                PolledAnswer(
                    source.dataset,
                    strip_credentials(source.url, adapter.provider),
                    "cancelled",
                    error=message("common.cancelled"),
                )
            )
        else:
            answer, written = _poll_one(
                adapter, source, timeout=DEFAULT_TIMEOUT, notice=notice
            )
            answers.append(answer)
            if written is not None:
                files.append(written)
        if on_progress is not None:
            on_progress(
                Progress(
                    index,
                    len(sources),
                    "source",
                    answers[-1].status,
                    message("captures.poll_progress", dataset=source.dataset),
                )
            )
    return PollReport(tuple(answers), stopped, tuple(files))


# --------------------------------------------------------------------------
# The night's harvest (ADR-030 D9)
# --------------------------------------------------------------------------

HARVEST_DAYS = 40
"""
How far back a harvest reaches: its first day at most 40 days before today (UTC).

``store sync --pace-until … --start <D−39>`` asks the 40 closed days D−39 to D, D the
last closed one, inside the six weeks hydro.imgw.pl keeps its operational data („do 6
tygodni wstecz”); ``store check|sync`` refuse an earlier ``start`` of a harvest (ADR-030
D9 and its erratum of 2026-11-23).
"""


def _harvested(descriptor: DatasetDescriptor, /) -> bool:
    """Whether ``store sync`` asks a capture dataset's source before sealing it (D9)."""
    return descriptor.key in get_provider(descriptor.provider).adapter.harvested


def harvest(
    dataset: str,
    start: date,
    end: date,
    /,
    *,
    stations: Sequence[str] | None = None,
    deadline: datetime | None = None,
    clock: Clock | None = None,
    on_progress: ProgressHook | None = None,
    on_notice: NoticeHook | None = None,
    cancel: Cancel | None = None,
) -> HarvestReport:
    """
    Ask a harvest dataset's source for the UTC days ``start`` to ``end``, into the spool.

    The night's harvest of ADR-030 D9: the provider's adapter plans one request per
    station and source (`ProviderAdapter.harvest_requests`, which reads the station
    list it needs through the session), and `obserwator.fetch.PacedSession` asks them
    one at a time, spread evenly up to ``deadline`` and never closer than 5 s, with
    gzip and the backoff of 429 and 5xx (60, 120 and 240 s, then the station is
    skipped until the next run); three connection failures in a row end the run.
    Every answer goes to the capture spool of its dataset, on the UTC day of its time
    (the day of the run, not the days it covers); nothing else is written, and
    ``store sync`` seals the spool (`obserwator.store.sync_store` with ``pace_until``
    runs both).

    Parameters
    ----------
    dataset : str
        Key, slug or legacy alias of a dataset an adapter harvests
        (`ProviderAdapter.harvested`): ``pl.imgw.hydro_operational`` (hydro-back's
        hourly H, Q and T) or ``cz.chmu.hydro_recent`` (ČHMÚ's day files).
    start, end : datetime.date
        The first and last UTC day to cover, closed days.
    stations : sequence of str or None, optional
        Station codes of the dataset's provider, each asked for every source; None
        for every station of the provider's list.
    deadline : datetime.datetime or None, optional
        When the requests should be done (`obserwator.fetch.pace_deadline`); None, or
        a deadline already passed, asks at the minimum spacing of 5 s.
    clock : Clock or None, optional
        The clock of the run (tests give a fake one); None is the system's.
    on_progress : ProgressHook or None, optional
        Called after each planned request (unit ``request``) with its status and a
        line ``<UTC time> <HTTP status> <address>``.
    on_notice : NoticeHook or None, optional
        Receives a ``harvest_failed`` warning for every failed request, skipped
        station, stopped run or unreadable station list, the adapter's warnings
        (``harvest_series_unknown``) and one ``harvest_done`` notice (info) with the
        requests, failures and wall time.
    cancel : Cancel or None, optional
        Polled before each request and during every wait.

    Returns
    -------
    HarvestReport
        The counts and times of the run.

    Raises
    ------
    ObserwatorValidationError
        If no adapter harvests the dataset (``details.reason`` ``not_harvested``),
        ``end`` is before ``start`` or a station code does not follow the
        provider's grammar.
    """
    return _harvest(
        dataset,
        start,
        end,
        stations=stations,
        deadline=deadline,
        clock=clock,
        on_progress=on_progress,
        on_notice=on_notice,
        cancel=cancel,
    )[0]


def _harvest(
    dataset: str,
    start: date,
    end: date,
    /,
    *,
    stations: Sequence[str] | None,
    deadline: datetime | None,
    clock: Clock | None,
    on_progress: ProgressHook | None,
    on_notice: NoticeHook | None,
    cancel: Cancel | None,
    raw: Path | None = None,
) -> tuple[HarvestReport, list[OperationResult]]:
    """
    `harvest`, with its failures as the failed results of a ``store sync`` (no slot).

    One result per failed request, per skipped station, for a run stopped by
    connection failures and for a station list that could not be read. ``raw`` is the
    raw root the run seals into: a harvest by watermark (`ProviderAdapter.watermarked`,
    PIG-PIB's ``mwp_auto``) asks for the rows after the last one it holds.
    """
    descriptor = get_dataset(dataset)
    if not _harvested(descriptor):
        raise ObserwatorValidationError(
            message("captures.not_harvested", dataset=descriptor.key),
            details={
                "option": "dataset",
                "value": descriptor.key,
                "reason": "not_harvested",
            },
        )
    if end < start:
        raise ObserwatorValidationError(
            message(
                "captures.harvest_end_before_start",
                start=start.isoformat(),
                end=end.isoformat(),
            ),
            details={"option": "end", "value": end.isoformat()},
        )
    adapter = get_provider(descriptor.provider).adapter
    codes = None if stations is None else _parse_stations(stations, adapter.provider)
    session = PacedSession(
        deadline=deadline, clock=clock, cancel=cancel, source=adapter.server_name
    )
    started = session.clock.now()
    requests: tuple[PacedRequest, ...] = ()
    outcomes: list[PacedOutcome] = []
    error: ObserwatorError | None = None
    cancelled = False
    with session:
        try:
            requests = adapter.harvest_requests(
                descriptor,
                start=start,
                end=end,
                stations=codes,
                session=session,
                on_notice=on_notice,
                raw=raw,
            )
        except ObserwatorCancelledError:
            cancelled = True
        except ObserwatorError as exc:
            error = exc
        else:
            outcomes = session.run(requests, on_progress=on_progress)
    ended = session.clock.now()
    failures: list[OperationResult] = []

    def fail(text: str, code: ErrorCode) -> None:
        failures.append(OperationResult(None, "failed", None, text, error_code=code))
        if on_notice is not None:
            on_notice(Notice("warning", "harvest_failed", text))

    if error is not None:
        fail(
            message(
                "captures.harvest_unplanned",
                dataset=descriptor.key,
                reason=reason(error),
            ),
            error.code,
        )
    skipped: dict[str, None] = {}
    unasked = 0
    for outcome in outcomes:
        if outcome.status == "failed":
            fail(outcome.error or "", outcome.error_code or "source_unavailable")
        elif outcome.status == "skipped" and outcome.request.station not in skipped:
            skipped[outcome.request.station] = None
            fail(outcome.error or "", "source_unavailable")
        elif outcome.status == "stopped":
            unasked += 1
    if unasked:
        fail(
            message(
                "captures.harvest_stopped",
                dataset=descriptor.key,
                failures=CONNECTION_FAILURES,
                count=unasked,
            ),
            "source_unavailable",
        )
    report = HarvestReport(
        dataset=descriptor.key,
        start=start,
        end=end,
        stations=len({request.station for request in requests}),
        planned=len(requests),
        requests=session.requests,
        answers=session.answers,
        failed=sum(outcome.status == "failed" for outcome in outcomes),
        skipped=tuple(skipped),
        stopped=session.stopped,
        cancelled=cancelled or any(o.status == "cancelled" for o in outcomes),
        deadline=deadline,
        started_at=started,
        ended_at=ended,
        seconds=round((ended - started).total_seconds(), 3),
        error=None if error is None else reason(error),
        error_code=None if error is None else error.code,
    )
    if on_notice is not None:
        on_notice(
            Notice(
                "info",
                "harvest_done",
                message(
                    "captures.harvest_done",
                    dataset=report.dataset,
                    start=start.isoformat(),
                    end=end.isoformat(),
                    stations=report.stations,
                    requests=report.requests,
                    answers=report.answers,
                    failed=report.failed,
                    skipped=len(report.skipped),
                    seconds=f"{report.seconds:.0f}",
                ),
            )
        )
    return report, failures
