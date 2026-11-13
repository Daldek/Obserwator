"""
Stored analyses of the stations: Hydrolog's results kept in the data root (ADR-016).

`build_analyses` exports the current series of every station (``series
export``), runs the calls of the registry (`analysis_definitions`) through
Hydrolog's program in batches (`obserwator._hydrolog`) and stores each answer
line verbatim, one slot per provider::

    analyses/versions/<key prefix>/<label>_<sha8>/
        analyses.json              obserwator-analyses/1, the main file
        analyses.json.meta.json    obserwator-meta/1 sidecar, published last
        stations/<code>.json       obserwator-station-analyses/1
        stations/<code>/<id>.json  Hydrolog's answer line, byte for byte

A station whose inputs (the SHA-256 of its station Parquet in each dataset, the
catalog thresholds used, Hydrolog's version and the digest of the registry)
equal its record in the current version is carried forward by hard links,
without a Hydrolog call. `list_analyses`, `read_analysis` and `export_analyses`
read a version; `compute_analysis` computes one analysis with a person's options
on the fly and keeps nothing.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import socket
import tempfile
import threading
import uuid
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, ClassVar, Final, Literal, cast, overload

from obserwator._hydrolog import Call, Deadline, Hydrolog, open_hydrolog, program_words
from obserwator._version import __version__
from obserwator.attribution import Attribution, attribution, dataset_origin
from obserwator.config import store_root
from obserwator.datasets import (
    _CATALOG_DATASETS,
    STATION_CODE_PATTERN,
    ProviderDescriptor,
    _license_document,
    get_dataset,
    providers,
)
from obserwator.exceptions import (
    ObserwatorCancelledError,
    ObserwatorDataError,
    ObserwatorStoreConflictError,
    ObserwatorStoreError,
    ObserwatorValidationError,
    io_error,
)
from obserwator.messages import message, reason
from obserwator.output import FileResult, OutputReport
from obserwator.store.analysis_registry import (
    AnalysisDefinition,
    AnalysisPick,
    AnalysisVariant,
    Kind,
    analysis_definitions,
    definitions_digest,
    get_definition,
)
from obserwator.store.catalog import RootArg, _catalog_license
from obserwator.store.export import (
    _check_cancel,
    _csv_line,
    _csv_lines,
    _deliver,
    _format,
    _Lines,
    _number,
    _target,
    _with_lines,
    export_series,
)
from obserwator.store.reader import (
    _open,
    current_version,
    read_catalog,
    read_meta,
    read_series_index,
)
from obserwator.store.types import (
    Cancel,
    Meta,
    Notice,
    NoticeHook,
    PathArg,
    PlanAction,
    Progress,
    ProgressHook,
    SeriesIndex,
    StoreHandle,
    StorePlan,
)
from obserwator.store.writer import (
    _canonical,
    _cleanup,
    _fsync_dir,
    _link,
    _publish_dir,
    _utc,
    _validate_slot,
    _write_json,
    refuse_root,
    root_conflict_plan,
    version_file,
)

ANALYSES_SCHEMA: Final = "obserwator-analyses/1"
STATION_SCHEMA: Final = "obserwator-station-analyses/1"
EXPORT_SCHEMA: Final = "obserwator-analyses-export/1"
ANALYSES_FILE: Final = "analyses.json"
_SIDECAR = f"{ANALYSES_FILE}.meta.json"
_SLOT = "analyses/versions"
_SCRATCH_PREFIX = "obserwator-analyses-"
_COMMAND = "analyses build"
_RESULT = "hydrolog-result/1"
_FORMATS = ("json", "csv")
# Stations of one Hydrolog process per round: the start of a process (about 1.5 s,
# mostly imports) is paid once for all their calls.
_CHUNK_STATIONS = 16
_DEFAULT_TIMEOUT = 30.0
_CSV_HEADER = (
    "station",
    "analysis",
    "command",
    "series_version",
    "hydrolog_version",
    "path",
    "value",
    "attribution_source",
    "attribution_processed",
    "attribution",
    "terms_notice",
)


# --------------------------------------------------------------------------
# Public results
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class AnalysisSource:
    """
    A series an analysis read and the file Hydrolog got of it.

    Attributes
    ----------
    dataset : str
        Dataset key of the series.
    series_version : str
        The series version directory relative to the data root (POSIX), e.g.
        ``series/versions/hydro_daily/2026-10-19_fc3541d8``.
    series_sha256 : str
        SHA-256 of its ``series.json``.
    station_sha256 : str
        SHA-256 of the station's Parquet file in that version.
    export_sha256 : str
        SHA-256 of the ``series export`` CSV file Hydrolog read.
    """

    dataset: str
    series_version: str
    series_sha256: str
    station_sha256: str
    export_sha256: str


@dataclass(frozen=True)
class AnalysisSummary:
    """
    One analysis of a station without Hydrolog's answer (``analyses list``).

    Attributes
    ----------
    station : str
        Station code.
    provider : str
        ``ProviderDescriptor.id`` of the station.
    kind : {"hydro", "meteo"}
        Kind of the station.
    analysis : str
        Id of the analysis (`analysis_definitions`).
    command : str
        The Hydrolog command.
    options : Mapping of str to object
        The options given to Hydrolog, file names relative to the directory
        of the series files.
    inputs : tuple of AnalysisSource
        The series the analysis read (also those of the analyses whose
        results gave its options).
    hydrolog : Mapping of str to str
        ``{"version": …}`` of the Hydrolog that computed it.
    computed_at : datetime
        When Hydrolog computed it (UTC).
    stored : bool
        True for a stored result, False for one computed on the fly.
    status : {"ok", "failed"}
        ``ok`` with Hydrolog's envelope, ``failed`` with its error document.
    error_code : str or None
        Hydrolog's error code of a failed analysis (e.g.
        ``calculation_error``), None otherwise.
    attribution : tuple of str
        The attribution lines of the data (ADR-012), Hydrolog's included.
    terms_notice : tuple of str
        The terms notice of IMGW-PIB data; empty for other data.
    analyses_version : str or None
        The name of the stored version, ``<label>_<sha8>`` (the label is its
        build date); None for a result computed on the fly.
    """

    SCHEMA: ClassVar[str] = "obserwator-analysis-summary/1"

    station: str
    provider: str
    kind: Literal["hydro", "meteo"]
    analysis: str
    command: str
    options: Mapping[str, Any]
    inputs: tuple[AnalysisSource, ...]
    hydrolog: Mapping[str, str]
    computed_at: datetime
    stored: bool
    status: Literal["ok", "failed"]
    error_code: str | None
    attribution: tuple[str, ...]
    terms_notice: tuple[str, ...]
    analyses_version: str | None


@dataclass(frozen=True)
class AnalysisResult:
    """
    One analysis of a station with Hydrolog's answer (``analyses read``).

    The fields of `AnalysisSummary` and Hydrolog's document: ``envelope`` (its
    ``hydrolog-result/1``, with ``result``, ``notices`` and ``inputs``) of an
    ``ok`` analysis, or ``error`` (its ``hydrolog-error/1``) of a ``failed``
    one. A stored ``envelope`` echoes the absolute paths of the series files
    Hydrolog read, in a scratch directory that no longer exists.
    """

    SCHEMA: ClassVar[str] = "obserwator-analysis/1"

    station: str
    provider: str
    kind: Literal["hydro", "meteo"]
    analysis: str
    command: str
    options: Mapping[str, Any]
    inputs: tuple[AnalysisSource, ...]
    hydrolog: Mapping[str, str]
    computed_at: datetime
    stored: bool
    status: Literal["ok", "failed"]
    error_code: str | None
    envelope: Mapping[str, Any] | None
    error: Mapping[str, Any] | None
    attribution: tuple[str, ...]
    terms_notice: tuple[str, ...]
    analyses_version: str | None


@dataclass(frozen=True)
class ProviderAnalyses:
    """
    The analyses version of one provider in a build.

    Attributes
    ----------
    provider : str
        ``ProviderDescriptor.id``.
    status : {"new", "unchanged", "cancelled", "failed"}
        ``unchanged`` when every station was carried forward and the
        stations are those of the current version: nothing was written.
    version : Path or None
        ``analyses.json`` of the new or unchanged version.
    stations : int
        Stations in the version.
    computed : int
        Stations computed by Hydrolog in this build.
    carried : int
        Stations carried forward from the previous version.
    results_ok : int
        Analyses of the computed stations with Hydrolog's envelope.
    results_failed : int
        Analyses of the computed stations with Hydrolog's error document.
    problems : tuple of str, optional
        Why the build failed.
    """

    provider: str
    status: Literal["new", "unchanged", "cancelled", "failed"]
    version: Path | None
    stations: int
    computed: int
    carried: int
    results_ok: int
    results_failed: int
    problems: tuple[str, ...] = ()


@dataclass(frozen=True)
class AnalysesReport:
    """
    Result of `build_analyses`: one analyses version per provider.

    Attributes
    ----------
    status : {"new", "unchanged", "cancelled", "failed"}
        ``new`` when a provider got a new version, ``unchanged`` when none
        did, ``failed`` without series to analyse.
    hydrolog_version : str or None
        The version of the Hydrolog that computed the results.
    providers : tuple of ProviderAnalyses
        Per provider with analysed stations, in registry order.
    problems : tuple of str, optional
        Why nothing was built.
    files : tuple of FileResult, optional
        The ``analyses.json`` of every new or unchanged version (DEV-19.19).
    """

    SCHEMA: ClassVar[str] = "obserwator-analyses-report/1"

    status: Literal["new", "unchanged", "cancelled", "failed"]
    hydrolog_version: str | None
    providers: tuple[ProviderAnalyses, ...]
    problems: tuple[str, ...] = ()
    files: tuple[FileResult, ...] = ()


# --------------------------------------------------------------------------
# The data root and its inputs
# --------------------------------------------------------------------------


def _data_root(root: RootArg | None) -> Path:
    """
    The data root of the analyses: ``root``, else the default root (DEV-19.2).

    Until the data root has its own marker (Nogat O1) it is an
    ``obserwator-store/1`` store holding the series and catalogs.
    """
    return _open(root if root is not None else store_root().root)


def _write_root(root: RootArg | None) -> PathArg | StoreHandle:
    """The root a build refuses or writes: ``root``, else the default root."""
    return root if root is not None else store_root().root


@dataclass(frozen=True)
class _Series:
    """The current series version of a dataset."""

    key: str
    path: Path
    version: str
    sha256: str
    index: SeriesIndex


@dataclass(frozen=True)
class _Catalog:
    """The current station catalog of a provider."""

    key: str
    version: str
    sha256: str
    properties: Mapping[str, Mapping[str, Any]]


def _relative(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _current_series(root: Path, keys: Iterable[str]) -> dict[str, _Series]:
    found: dict[str, _Series] = {}
    for key in dict.fromkeys(keys):
        entry = current_version(root, slot=f"series:{key}")
        if entry is None or entry.version is None or entry.meta is None:
            continue
        found[key] = _Series(
            key,
            entry.version,
            _relative(root, entry.version.parent),
            entry.meta.sha256,
            read_series_index(entry.version),
        )
    return found


def _current_catalog(root: Path, provider: ProviderDescriptor) -> _Catalog | None:
    key = _CATALOG_DATASETS[provider.id]
    entry = current_version(root, slot=f"catalog:{key}")
    if entry is None or entry.version is None or entry.meta is None:
        return None
    return _Catalog(
        key,
        _relative(root, entry.version.parent),
        entry.meta.sha256,
        {
            feature.station_code: feature.properties
            for feature in read_catalog(entry.version)
        },
    )


# --------------------------------------------------------------------------
# The plan of a station
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class _Planned:
    """An analysis of the registry that applies to a station: its variant and files."""

    definition: AnalysisDefinition
    variant: AnalysisVariant
    files: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class _Station:
    """A station to analyse: its series, catalog entry and applicable analyses."""

    code: str
    provider: ProviderDescriptor
    kind: Kind
    series: Mapping[str, _Series]
    properties: Mapping[str, Any]
    planned: tuple[_Planned, ...]

    def datasets(self) -> tuple[str, ...]:
        """The datasets the planned analyses read, in order of first use."""
        return tuple(
            dict.fromkeys(key for planned in self.planned for _, key in planned.files)
        )

    def thresholds(self) -> object:
        """The catalog thresholds an analysis takes, or None."""
        uses = any(
            pick.analysis is None
            for planned in self.planned
            for pick in planned.definition.picks
        )
        return self.properties.get("thresholds") if uses else None

    def sources(self) -> list[dict[str, str]]:
        """The series of the station's analyses (``inputs`` without the export)."""
        return [
            {
                "dataset": key,
                "series_version": self.series[key].version,
                "series_sha256": self.series[key].sha256,
                "station_sha256": self.series[key].index.stations[self.code].sha256,
            }
            for key in self.datasets()
        ]

    def fingerprint(self, version: str, digest: str) -> tuple[object, ...]:
        """What decides whether the stored record of the station is still current."""
        return _fingerprint(
            ((item["dataset"], item["station_sha256"]) for item in self.sources()),
            self.thresholds(),
            version,
            digest,
        )


def _fingerprint(
    inputs: Iterable[tuple[str, str]], thresholds: object, version: str, digest: str
) -> tuple[object, ...]:
    return (
        tuple(sorted(inputs)),
        json.dumps(thresholds, sort_keys=True),
        version,
        digest,
    )


def _record_fingerprint(record: Mapping[str, Any]) -> tuple[object, ...]:
    return _fingerprint(
        ((item["dataset"], item["station_sha256"]) for item in record["inputs"]),
        record.get("thresholds"),
        record["hydrolog"]["version"],
        record["definitions"],
    )


def _pointer(document: object, pointer: str) -> object:
    """The value at a JSON Pointer (RFC 6901), or None when there is none."""
    if pointer == "":
        return document
    current = document
    for raw in pointer.split("/")[1:]:
        token = raw.replace("~1", "/").replace("~0", "~")
        if isinstance(current, Mapping):
            if token not in current:
                return None
            current = current[token]
        elif isinstance(current, list):
            if not token.isdigit() or int(token) >= len(current):
                return None
            current = current[int(token)]
        else:
            return None
    return current


def _is_number(value: object) -> bool:
    return (
        isinstance(value, int | float)
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def _holdings(index: SeriesIndex, code: str) -> frozenset[str]:
    """The variables of the station with a value in a series (half-years without ``@``)."""
    return frozenset(
        name.split("@", 1)[0]
        for name, coverage in index.stations[code].variables.items()
        if coverage.with_value > 0
    )


def _plan(
    kind: Kind,
    holdings: Mapping[str, frozenset[str]],
    properties: Mapping[str, Any],
    definitions: Iterable[AnalysisDefinition],
) -> tuple[_Planned, ...]:
    """The analyses of ``definitions`` the station's series and catalog entry allow."""
    planned: dict[str, _Planned] = {}
    for definition in definitions:
        if definition.kind != kind or any(
            name not in planned for name in definition.depends_on
        ):
            continue
        if any(
            pick.analysis is None and not _is_number(_pointer(properties, pick.pointer))
            for pick in definition.picks
        ):
            continue
        for variant in definition.variants:
            files: list[tuple[str, str]] = []
            for item in variant.inputs:
                key = next(
                    (
                        key
                        for key in item.datasets
                        if set(item.variables) <= holdings.get(key, frozenset())
                    ),
                    None,
                )
                if key is None:
                    break
                files.append((item.option, key))
            else:
                planned[definition.id] = _Planned(definition, variant, tuple(files))
                break
    return tuple(planned.values())


def _provider_stations(
    provider: ProviderDescriptor,
    series: Mapping[str, _Series],
    catalog: _Catalog | None,
    definitions: Sequence[AnalysisDefinition],
) -> dict[str, _Station]:
    """Every station of the provider's series with an analysis to compute, by code."""
    keys = [key for key in series if get_dataset(key).provider == provider.id]
    codes = sorted({code for key in keys for code in series[key].index.stations})
    stations: dict[str, _Station] = {}
    for code in codes:
        held = {
            key: _holdings(series[key].index, code)
            for key in keys
            if code in series[key].index.stations
        }
        kind = cast(Kind, get_dataset(next(iter(held))).kind)
        properties = (catalog.properties.get(code) if catalog else None) or {}
        planned = _plan(kind, held, properties, definitions)
        if planned:
            stations[code] = _Station(
                code,
                provider,
                kind,
                {key: series[key] for key in held},
                properties,
                planned,
            )
    return stations


def _provider_of(code: str) -> ProviderDescriptor:
    """The provider whose station code grammar ``code`` follows (the grammars are disjoint)."""
    if isinstance(code, str):
        for provider in providers():
            if re.fullmatch(provider.station_code_pattern, code):
                return provider
    raise ObserwatorValidationError(
        message("analyses.invalid_station", station=code, pattern=STATION_CODE_PATTERN),
        details={"option": "station", "value": code if isinstance(code, str) else None},
    )


# --------------------------------------------------------------------------
# Computing: series files, rounds of calls, Hydrolog's lines
# --------------------------------------------------------------------------


def _scratch() -> Path:
    """
    A fresh directory of the series files Hydrolog reads, outside the data root.

    ``tempfile.mkdtemp`` (``TMPDIR``): every caller removes it when done.
    """
    return Path(tempfile.mkdtemp(prefix=_SCRATCH_PREFIX))


@dataclass(frozen=True)
class _Outcome:
    """Hydrolog's answer to the call of one analysis of a station."""

    planned: _Planned
    options: Mapping[str, Any]
    line: bytes
    document: Mapping[str, Any]
    datasets: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return self.document.get("schema") == _RESULT

    @property
    def error_code(self) -> str | None:
        code = self.document.get("code")
        return None if self.ok or not isinstance(code, str) else code

    def lines(self) -> Attribution:
        """The attribution lines of Hydrolog's envelope (none for an error)."""
        return Attribution(
            tuple(self.document.get("attribution") or ()),
            tuple(self.document.get("terms_notice") or ()),
        )


@dataclass(frozen=True)
class _Computed:
    """The answers of one station: its series files and the analyses in registry order."""

    station: _Station
    exports: Mapping[str, str]
    outcomes: tuple[_Outcome, ...]
    version: str
    computed_at: datetime


def _picked(
    definition: AnalysisDefinition,
    answers: Mapping[str, _Outcome],
    properties: Mapping[str, Any],
) -> dict[str, Any] | None:
    """
    The options a definition takes from earlier answers or the catalog; None without them.

    A value is copied from Hydrolog's ``result`` (or the catalog entry), never
    computed; ``offset`` moves a year (``last_year`` − 9).
    """
    values: dict[str, Any] = {}
    arrays: dict[tuple[str | None, str, str | None], list[AnalysisPick]] = {}

    def document(pick: AnalysisPick) -> object:
        if pick.analysis is None:
            return properties
        answer = answers.get(pick.analysis)
        return (
            answer.document.get("result") if answer is not None and answer.ok else None
        )

    for pick in definition.picks:
        if pick.each is not None:
            arrays.setdefault((pick.analysis, pick.pointer, pick.where), []).append(
                pick
            )
            continue
        value = _pointer(document(pick), pick.pointer)
        if not _is_number(value):
            return None
        if pick.offset:
            if not isinstance(value, int):
                return None
            value += pick.offset
        values[pick.option] = value
    for (_, pointer, where), picks in arrays.items():
        items = _pointer(document(picks[0]), pointer)
        if not isinstance(items, list):
            return None
        rows = []
        for item in items:
            if where is not None and _pointer(item, where) is not True:
                continue
            row = [_pointer(item, cast(str, pick.each)) for pick in picks]
            if all(_is_number(value) for value in row):
                rows.append(row)
        if not rows:
            return None
        for column, pick in enumerate(picks):
            values[pick.option] = [row[column] for row in rows]
    return values


def _datasets_of(station: _Station, planned: _Planned) -> tuple[str, ...]:
    """The datasets an analysis reads, with those of the analyses it depends on."""
    by_id = {item.definition.id: item for item in station.planned}
    found: dict[str, None] = {}
    pending = [planned]
    while pending:
        current = pending.pop()
        for _, key in current.files:
            found.setdefault(key)
        pending += [by_id[name] for name in current.definition.depends_on]
    return tuple(key for key in station.datasets() if key in found)


def _export_name(code: str, key: str) -> str:
    return f"{code}_{get_dataset(key).slug}.csv"


def _compute(
    hydrolog: Hydrolog,
    scratch: Path,
    name: str,
    stations: Sequence[_Station],
    *,
    overrides: Mapping[str, Mapping[str, Any]] | None = None,
    deadline: Deadline | None = None,
    cancel: Callable[[], bool] | None = None,
) -> tuple[str, list[_Computed]]:
    """
    Every planned analysis of ``stations``: one Hydrolog process per round of calls.

    The series files go to ``scratch`` (``<code>_<dataset slug>.csv``) and are
    removed after the last round; an analysis whose option an earlier answer
    or the catalog does not give is left out.

    Returns
    -------
    tuple of (str, list of _Computed)
        Hydrolog's version (of its last process) and the answers per station.
    """
    exports: dict[str, dict[str, str]] = {}
    for station in stations:
        hashes: dict[str, str] = {}
        for key in station.datasets():
            if cancel is not None and cancel():
                raise ObserwatorCancelledError(message("common.cancelled"))
            report = export_series(
                station.series[key].path,
                station=station.code,
                output=scratch / _export_name(station.code, key),
            )
            hashes[key] = report.files[0].sha256
        exports[station.code] = hashes
    answers: dict[str, dict[str, _Outcome]] = {station.code: {} for station in stations}
    version = hydrolog.version or ""
    levels = sorted({p.definition.level for s in stations for p in s.planned})
    for level in levels:
        calls: list[Call] = []
        owners: list[tuple[_Station, _Planned, dict[str, Any]]] = []
        for station in stations:
            for planned in station.planned:
                definition = planned.definition
                if definition.level != level:
                    continue
                picked = _picked(definition, answers[station.code], station.properties)
                if picked is None:
                    continue
                options: dict[str, Any] = {
                    **definition.options,
                    **planned.variant.options,
                    **{
                        option: _export_name(station.code, key)
                        for option, key in planned.files
                    },
                    **picked,
                    **((overrides or {}).get(definition.id) or {}),
                }
                calls.append(Call(definition.command, options))
                owners.append((station, planned, options))
        if not calls:
            continue
        version, lines = hydrolog.batch(
            scratch, f"{name}-{level}", calls, deadline=deadline, cancel=cancel
        )
        for (station, planned, options), line in zip(owners, lines, strict=True):
            answers[station.code][planned.definition.id] = _Outcome(
                planned,
                options,
                line,
                cast(Mapping[str, Any], json.loads(line)),
                _datasets_of(station, planned),
            )
    for station in stations:
        for key in station.datasets():
            (scratch / _export_name(station.code, key)).unlink(missing_ok=True)
    now = datetime.now(UTC)
    return version, [
        _Computed(
            station,
            exports[station.code],
            tuple(
                answers[station.code][planned.definition.id]
                for planned in station.planned
                if planned.definition.id in answers[station.code]
            ),
            version,
            now,
        )
        for station in stations
    ]


def _dataset_lines(keys: Iterable[str]) -> Attribution:
    """The lines of data of the given datasets: parsed and computed (ADR-012)."""
    return attribution(*dict.fromkeys(dataset_origin(key) for key in keys))


def _station_lines(computed: _Computed) -> Attribution:
    lines = _dataset_lines(computed.station.datasets())
    for outcome in computed.outcomes:
        lines |= outcome.lines()
    return lines


def _sources(computed: _Computed) -> list[dict[str, str]]:
    return [
        {**item, "export_sha256": computed.exports[item["dataset"]]}
        for item in computed.station.sources()
    ]


# --------------------------------------------------------------------------
# Versions of the data root
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class _Version:
    """A published analyses version: its directory, sidecar and main document."""

    directory: Path
    meta: Meta
    document: Mapping[str, Any]

    @property
    def main(self) -> Path:
        return self.directory / ANALYSES_FILE


def _slot(root: Path, provider: ProviderDescriptor) -> Path:
    return _validate_slot(root, f"{_SLOT}/{provider.key_prefix}")


def _broken(path: Path, detail: str) -> ObserwatorDataError:
    return ObserwatorDataError(
        message("analyses.broken_version", path=path, reason=detail),
        details={"path": str(path)},
    )


def _read_bytes(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except FileNotFoundError as exc:
        raise _broken(path, message("analyses.missing_file")) from exc
    except OSError as exc:
        raise io_error(exc) from exc


def _load(directory: Path, meta: Meta) -> _Version:
    """The version of ``directory``: its main file checked against its sidecar."""
    content = _read_bytes(directory / ANALYSES_FILE)
    if hashlib.sha256(content).hexdigest() != meta.sha256:
        raise _broken(
            directory, message("analyses.checksum_mismatch", name=ANALYSES_FILE)
        )
    try:
        document = json.loads(content)
    except ValueError as exc:
        raise _broken(directory, reason(exc)) from exc
    if (
        not isinstance(document, dict)
        or document.get("schema") != ANALYSES_SCHEMA
        or not isinstance(document.get("stations"), dict)
    ):
        raise _broken(directory, message("analyses.unknown_schema"))
    return _Version(directory, meta, document)


def _meta(directory: Path, provider: ProviderDescriptor) -> Meta:
    meta = read_meta(directory / _SIDECAR)
    if meta.extra.get("derived") != "analyses" or meta.provider != provider.id:
        raise _broken(directory, message("analyses.not_analyses_version"))
    return meta


def _current(root: Path, provider: ProviderDescriptor) -> _Version | None:
    """
    The current analyses version of a provider: the newest ``downloaded_at``, then path.

    A directory without the sidecar is an interrupted publication, not a
    version; a broken version is an error (an older one is never chosen
    instead).
    """
    slot = _slot(root, provider)
    if not slot.is_dir():
        return None
    best: tuple[datetime, str, Path, Meta] | None = None
    for directory in sorted(slot.iterdir()):
        if directory.is_symlink() or not directory.is_dir():
            raise _broken(directory, message("analyses.unknown_entry"))
        if not (directory / _SIDECAR).exists():
            continue
        meta = _meta(directory, provider)
        key = (meta.downloaded_at, directory.as_posix(), directory, meta)
        if best is None or key[:2] > best[:2]:
            best = key
    return None if best is None else _load(best[2], best[3])


def _version_at(root: RootArg | None, version: PathArg) -> Path:
    """The directory of a version given as its directory, main file or sidecar."""
    given = Path(version).expanduser()
    if root is not None and not given.is_absolute():
        given = _data_root(root) / given
    if given.name in (ANALYSES_FILE, _SIDECAR):
        given = given.parent
    if not (given / ANALYSES_FILE).is_file():
        raise ObserwatorStoreError(
            message("analyses.version_not_found", version=version),
            code="not_found",
            details={"option": "version"},
        )
    return given.absolute()


def _station_version(
    version: PathArg | None, root: RootArg | None, provider: ProviderDescriptor
) -> _Version:
    """The given or the current analyses version of the station's provider."""
    if version is not None:
        directory = _version_at(root, version)
        return _load(directory, _meta(directory, provider))
    path = _data_root(root)
    found = _current(path, provider)
    if found is None:
        raise ObserwatorStoreError(
            message("analyses.no_version", provider=provider.short_name),
            code="not_found",
            details={"option": "root"},
            hint=message("analyses.hint_build"),
        )
    return found


def _record(version: _Version, code: str) -> dict[str, Any]:
    """The checked record ``stations/<code>.json`` of a station in a version."""
    entry = version.document["stations"].get(code)
    if not isinstance(entry, dict):
        raise ObserwatorStoreError(
            message(
                "analyses.station_not_in_version",
                station=code,
                version=version.directory.name,
            ),
            code="not_found",
            details={"option": "station", "value": code},
        )
    path = version.directory / str(entry["file"])
    content = _read_bytes(path)
    if hashlib.sha256(content).hexdigest() != entry.get("sha256"):
        raise _broken(path, message("analyses.checksum_mismatch", name=path.name))
    try:
        record = json.loads(content)
    except ValueError as exc:
        raise _broken(path, reason(exc)) from exc
    if not isinstance(record, dict) or record.get("schema") != STATION_SCHEMA:
        raise _broken(path, message("analyses.unknown_schema"))
    return record


def _entry(record: Mapping[str, Any], analysis: str) -> Mapping[str, Any]:
    for entry in record["results"]:
        if entry["analysis"] == analysis:
            return cast(Mapping[str, Any], entry)
    raise ObserwatorStoreError(
        message(
            "analyses.analysis_not_stored", station=record["station"], analysis=analysis
        ),
        code="not_found",
        details={
            "option": "analysis",
            "value": analysis,
            "allowed": [entry["analysis"] for entry in record["results"]],
        },
    )


def _line(version: _Version, entry: Mapping[str, Any]) -> bytes:
    path = version.directory / str(entry["file"])
    content = _read_bytes(path)
    if hashlib.sha256(content).hexdigest() != entry.get("sha256"):
        raise _broken(path, message("analyses.checksum_mismatch", name=path.name))
    return content


def _record_lines(record: Mapping[str, Any]) -> Attribution:
    return Attribution(
        tuple(record.get("attribution") or ()), tuple(record.get("terms_notice") or ())
    )


def _summary(
    record: Mapping[str, Any], entry: Mapping[str, Any], version: _Version
) -> AnalysisSummary:
    lines = _record_lines(record)
    return AnalysisSummary(
        record["station"],
        record["provider"],
        record["kind"],
        entry["analysis"],
        entry["command"],
        entry["options"],
        tuple(
            AnalysisSource(**item)
            for item in record["inputs"]
            if item["dataset"] in entry["datasets"]
        ),
        record["hydrolog"],
        datetime.fromisoformat(str(record["computed_at"])),
        True,
        entry["status"],
        entry["error_code"],
        lines.attribution,
        lines.terms_notice,
        version.directory.name,
    )


def _code(station: object) -> tuple[str, ProviderDescriptor]:
    if not isinstance(station, str):
        _provider_of(station)  # type: ignore[arg-type]
    code = cast(str, station)
    return code, _provider_of(code)


# --------------------------------------------------------------------------
# Building
# --------------------------------------------------------------------------


@dataclass
class _ProviderPlan:
    """What a build does with one provider: stations computed, carried, kept."""

    provider: ProviderDescriptor
    current: _Version | None
    stations: list[str]
    compute: list[_Station] = field(default_factory=list)
    carried: dict[str, dict[str, Any]] = field(default_factory=dict)
    catalog: _Catalog | None = None

    @property
    def unchanged(self) -> bool:
        return (
            not self.compute
            and self.current is not None
            and set(self.stations) == set(self.current.document["stations"])
        )


def _selection(stations: Iterable[str] | None) -> tuple[str, ...] | None:
    if stations is None:
        return None
    if isinstance(stations, str) or not isinstance(stations, Iterable):
        raise ObserwatorValidationError(
            message("analyses.stations_not_list"),
            details={"option": "stations", "value": str(stations)},
        )
    codes = tuple(dict.fromkeys(stations))
    invalid = [code for code in codes if not isinstance(code, str)]
    for code in codes:
        if isinstance(code, str):
            try:
                _provider_of(code)
            except ObserwatorValidationError:
                invalid.append(code)
    if not codes or invalid:
        raise ObserwatorValidationError(
            message("analyses.invalid_stations", stations=", ".join(map(str, invalid))),
            details={"option": "stations", "value": [str(code) for code in invalid]},
        )
    return codes


def _workers(workers: object) -> int:
    if isinstance(workers, bool) or not isinstance(workers, int) or workers < 1:
        raise ObserwatorValidationError(
            message("analyses.invalid_workers", workers=workers),
            details={"option": "workers", "value": str(workers)},
        )
    return workers


def _plans(
    root: Path, version: str, selected: tuple[str, ...] | None
) -> list[_ProviderPlan]:
    """The plan of every provider with series to analyse or a current version."""
    definitions = analysis_definitions()
    series = _current_series(root, (key for d in definitions for key in d.datasets()))
    digest = definitions_digest()
    plans: list[_ProviderPlan] = []
    known: set[str] = set()
    for provider in providers():
        uses_catalog = any(
            pick.analysis is None for d in definitions for pick in d.picks
        )
        catalog = _current_catalog(root, provider) if uses_catalog else None
        planned = _provider_stations(provider, series, catalog, definitions)
        known |= set(planned)
        current = _current(root, provider)
        stored = set(current.document["stations"]) if current is not None else set()
        targets = [code for code in planned if selected is None or code in selected]
        kept = (
            sorted(code for code in stored if code not in selected)
            if selected is not None
            else []
        )
        if not targets and not kept:
            continue
        plan = _ProviderPlan(
            provider, current, sorted({*targets, *kept}), catalog=catalog
        )
        for code in targets:
            station = planned[code]
            if current is not None and code in stored:
                record = _record(current, code)
                if _record_fingerprint(record) == station.fingerprint(version, digest):
                    plan.carried[code] = record
                    continue
            plan.compute.append(station)
        for code in kept:
            plan.carried[code] = _record(cast(_Version, current), code)
        plans.append(plan)
    if selected is not None:
        outside = [code for code in selected if code not in known]
        if outside:
            raise ObserwatorValidationError(
                message("analyses.stations_outside", stations=", ".join(outside)),
                details={"option": "stations", "value": outside},
            )
    return plans


def _chunks(stations: Sequence[_Station], workers: int) -> list[list[_Station]]:
    size = max(1, min(_CHUNK_STATIONS, math.ceil(len(stations) / workers)))
    return [
        list(stations[start : start + size]) for start in range(0, len(stations), size)
    ]


def _write(path: Path, data: bytes) -> str:
    """Write a new staged file, flushed and fsynced; its SHA-256."""
    with path.open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    return hashlib.sha256(data).hexdigest()


def _stage(
    staging: Path, computed: _Computed, digest: str
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Write a computed station into ``staging``: its record and its entry of the index."""
    station = computed.station
    directory = staging / "stations" / station.code
    directory.mkdir()
    results = []
    for outcome in computed.outcomes:
        definition = outcome.planned.definition
        relative = f"stations/{station.code}/{definition.id}.json"
        results.append(
            {
                "analysis": definition.id,
                "command": definition.command,
                "options": dict(outcome.options),
                "datasets": list(outcome.datasets),
                "status": "ok" if outcome.ok else "failed",
                "error_code": outcome.error_code,
                "file": relative,
                "sha256": _write(staging / relative, outcome.line),
            }
        )
    _fsync_dir(directory)
    record = {
        "schema": STATION_SCHEMA,
        "station": station.code,
        "provider": station.provider.id,
        "kind": station.kind,
        "computed_at": _utc(computed.computed_at),
        "hydrolog": {"version": computed.version},
        "definitions": digest,
        "inputs": _sources(computed),
        "thresholds": station.thresholds(),
        "results": results,
        **_station_lines(computed).fields(),
    }
    file = f"stations/{station.code}.json"
    ok = sum(1 for item in results if item["status"] == "ok")
    entry = {
        "provider": station.provider.id,
        "kind": station.kind,
        "file": file,
        "sha256": _write(staging / file, _canonical(record)),
        "n_ok": ok,
        "n_failed": len(results) - ok,
    }
    return record, entry


def _carry(
    staging: Path, version: _Version, code: str, record: Mapping[str, Any]
) -> dict[str, Any]:
    """Link a station of the current version into ``staging``; its entry of the index."""
    entry = dict(version.document["stations"][code])
    (staging / "stations" / code).mkdir()
    for name in (entry["file"], *(item["file"] for item in record["results"])):
        _link(version.directory / str(name), staging / str(name))
    _fsync_dir(staging / "stations" / code)
    return entry


def _publish(
    root: Path,
    staging: Path,
    plan: _ProviderPlan,
    records: Mapping[str, Mapping[str, Any]],
    entries: Mapping[str, Mapping[str, Any]],
    version: str,
    selected: tuple[str, ...] | None,
) -> Path:
    """Write ``analyses.json`` and its sidecar, then publish the version (sidecar last)."""
    provider = plan.provider
    lines = Attribution()
    series: dict[tuple[str, str, str], None] = {}
    for code in plan.stations:
        lines |= _record_lines(records[code])
        for item in records[code]["inputs"]:
            series.setdefault(
                (item["dataset"], item["series_version"], item["series_sha256"])
            )
    built_at = datetime.now(UTC)
    catalog = plan.catalog
    document = {
        "schema": ANALYSES_SCHEMA,
        "provider": provider.id,
        "built_at": _utc(built_at),
        "hydrolog": {"version": version},
        "definitions": definitions_digest(),
        "series": [
            {"dataset": key, "series_version": path, "series_sha256": sha}
            for key, path, sha in sorted(series)
        ],
        "catalog": None
        if catalog is None
        else {
            "dataset": catalog.key,
            "version": catalog.version,
            "sha256": catalog.sha256,
        },
        "stations": {code: dict(entries[code]) for code in sorted(plan.stations)},
        **lines.fields(),
    }
    content = _canonical(document)
    sha = hashlib.sha256(content).hexdigest()
    _write_json(staging / ANALYSES_FILE, document)
    label = built_at.date().isoformat()
    meta = {
        "schema": "obserwator-meta/1",
        "producer": "obserwator",
        "producer_version": __version__,
        "dataset": f"{provider.key_prefix}.analyses",
        "country": provider.country,
        "provider": provider.id,
        "request": {"stations": None if selected is None else sorted(selected)},
        "license": _license_document(_catalog_license(provider, lines)),
        "downloaded_at": _utc(built_at),
        "sha256": sha,
        "size_bytes": len(content),
        "extra": {
            "version": {"label": label, "label_source": "downloaded"},
            "derived": "analyses",
            "analyses_schema": ANALYSES_SCHEMA,
            "provider": provider.id,
            "hydrolog_version": version,
            "definitions_digest": document["definitions"],
            "series": document["series"],
            "catalogs": [] if document["catalog"] is None else [document["catalog"]],
        },
    }
    _write_json(staging / _SIDECAR, meta)
    _fsync_dir(staging / "stations")
    _fsync_dir(staging)
    parent = _slot(root, provider)
    parent.mkdir(parents=True, exist_ok=True)
    target = _validate_slot(root, f"{_SLOT}/{provider.key_prefix}/{label}_{sha[:8]}")
    try:
        _publish_dir(staging, target, _SIDECAR)
    except FileExistsError as exc:
        raise ObserwatorStoreConflictError(
            message("analyses.version_collision", path=target)
        ) from exc
    return target / ANALYSES_FILE


def _progress(
    hook: ProgressHook | None, done: int, total: int, status: str, text: str
) -> None:
    if hook is not None:
        hook(Progress(done, total, "station", status, text))


def _build_provider(
    root: Path,
    plan: _ProviderPlan,
    hydrolog: Hydrolog,
    workers: int,
    selected: tuple[str, ...] | None,
    on_progress: ProgressHook | None,
    on_notice: NoticeHook | None,
    cancel: Cancel | None,
) -> ProviderAnalyses:
    provider = plan.provider
    total = len(plan.stations)
    incoming = root / ".incoming"
    incoming.mkdir(exist_ok=True)
    _cleanup(incoming, on_notice=on_notice)
    staging = incoming / f"{socket.gethostname()}_{os.getpid()}_{uuid.uuid4().hex}"
    (staging / "stations").mkdir(parents=True)
    scratch = _scratch()
    stop = threading.Event()

    def stopped() -> bool:
        return stop.is_set() or (cancel is not None and cancel())

    records: dict[str, Mapping[str, Any]] = {}
    entries: dict[str, Mapping[str, Any]] = {}
    ok = failed = done = 0
    try:
        for code, record in plan.carried.items():
            entries[code] = _carry(staging, cast(_Version, plan.current), code, record)
            records[code] = record
            done += 1
            _progress(
                on_progress,
                done,
                total,
                "carried",
                message("analyses.station_carried", station=code),
            )
        digest = definitions_digest()
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures: list[Future[tuple[str, list[_Computed]]]] = [
                pool.submit(
                    _compute, hydrolog, scratch, f"part{number}", chunk, cancel=stopped
                )
                for number, chunk in enumerate(_chunks(plan.compute, workers))
            ]
            try:
                for future in as_completed(futures):
                    for computed in future.result()[1]:
                        record, entry = _stage(staging, computed, digest)
                        code = computed.station.code
                        records[code], entries[code] = record, entry
                        ok += entry["n_ok"]
                        failed += entry["n_failed"]
                        done += 1
                        _progress(
                            on_progress,
                            done,
                            total,
                            "computed",
                            message("analyses.station_computed", station=code),
                        )
            except BaseException:
                stop.set()
                for future in futures:
                    future.cancel()
                raise
        if stopped():
            raise ObserwatorCancelledError(message("common.cancelled"))
        path = _publish(
            root, staging, plan, records, entries, hydrolog.version or "", selected
        )
    except ObserwatorCancelledError:
        return ProviderAnalyses(provider.id, "cancelled", None, total, 0, 0, 0, 0)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
        shutil.rmtree(scratch, ignore_errors=True)
    if on_notice is not None:
        on_notice(
            Notice(
                "info",
                "license_terms",
                provider.license_notice(_record_lines(json.loads(path.read_bytes()))),
            )
        )
    return ProviderAnalyses(
        provider.id,
        "new",
        path,
        total,
        len(plan.compute),
        len(plan.carried),
        ok,
        failed,
    )


def _overall(
    outcomes: Sequence[ProviderAnalyses],
) -> Literal["new", "unchanged", "cancelled", "failed"]:
    statuses = {outcome.status for outcome in outcomes}
    if "cancelled" in statuses:
        return "cancelled"
    if "new" in statuses:
        return "new"
    if statuses == {"failed"}:
        return "failed"
    return "unchanged"


def build_analyses(
    root: RootArg | None = None,
    /,
    *,
    stations: Iterable[str] | None = None,
    workers: int = 1,
    on_progress: ProgressHook | None = None,
    on_notice: NoticeHook | None = None,
    cancel: Cancel | None = None,
) -> AnalysesReport:
    """
    Compute the analyses of every station with Hydrolog and store them as versions.

    Every station of the current series of the registry's datasets gets the
    analyses its series and catalog entry allow (`analysis_definitions`),
    over the whole record. Its series are exported (``series export`` CSV,
    with the attribution columns) into a fresh scratch directory outside the
    data root, which is removed afterwards; Hydrolog's program (the setting
    ``hydrolog_command``, else ``hydrolog`` on ``PATH``) runs the calls of up
    to 16 stations in one process (``commands batch``), one process per
    round (an analysis that takes a number of another's result runs in the
    next round), up to ``workers`` processes at a time. Each answer line is
    stored byte for byte, the station's record names the series versions,
    the file given to Hydrolog, the options and Hydrolog's version.

    Each provider has its own slot, ``analyses/versions/<key prefix>/``. A
    station whose inputs (the SHA-256 of its station Parquet per dataset, the
    catalog thresholds used, Hydrolog's version and the registry digest)
    equal its record in the current version is carried forward by hard links
    without a call; a provider whose stations are all carried forward and
    are the stations of its current version is ``unchanged`` and gets no new
    version.

    Parameters
    ----------
    root : str, os.PathLike, StoreHandle or None, optional
        The data root; None is the default root (``OBSERWATOR_ROOT``, else
        ``<data_dir>/obserwator``).
    stations : iterable of str or None, optional
        Compute only these stations now; the other stations of the current
        versions are carried forward as they are (their records name their
        series versions). None computes every station that needs it.
    workers : int, optional
        Hydrolog processes run at a time (at least 1).
    on_progress : ProgressHook or None, optional
        Called after each station with ``unit="station"`` and the status
        ``computed`` or ``carried``.
    on_notice : NoticeHook or None, optional
        Receives the ``license_terms`` notice of every new version and a
        ``leftover_incoming`` warning for every removed old staging directory.
    cancel : Cancel or None, optional
        Polled while Hydrolog runs; ``True`` stops the build and nothing more
        is published.

    Returns
    -------
    AnalysesReport
        Per provider ``new``, ``unchanged`` or ``cancelled`` with the version,
        the stations computed and carried forward and the analyses that
        Hydrolog answered with its envelope or with an error document;
        ``failed`` when the data root holds no series to analyse.

    Raises
    ------
    ObserwatorValidationError
        If ``stations`` holds an invalid code or a station without series of
        the analyses, or ``workers`` is not a positive integer.
    ObserwatorError
        Code ``missing_dependency`` (``details.reason`` ``hydrolog_missing``)
        without Hydrolog's program; ``source_unavailable``
        (``hydrolog_failed``) when the program fails as a whole.
    ObserwatorStoreError
        If ``root`` is not a supported store.
    ObserwatorStoreConflictError
        If ``root`` nests a store or holds other files, or a version cannot be
        published.
    ObserwatorStoreDependencyError
        If ``pyarrow>=15`` is not installed.
    """
    count = _workers(workers)
    selected = _selection(stations)
    refuse_root(_write_root(root))
    path = _data_root(root)
    hydrolog = open_hydrolog()
    if cancel is not None and cancel():
        return AnalysesReport("cancelled", hydrolog.version, ())
    plans = _plans(path, hydrolog.version or "", selected)
    if not plans:
        return AnalysesReport(
            "failed", hydrolog.version, (), (message("analyses.no_series"),)
        )
    outcomes: list[ProviderAnalyses] = []
    for plan in plans:
        if plan.unchanged:
            current = cast(_Version, plan.current)
            _progress(
                on_progress,
                len(plan.stations),
                len(plan.stations),
                "unchanged",
                message(
                    "analyses.version_unchanged", provider=plan.provider.short_name
                ),
            )
            outcomes.append(
                ProviderAnalyses(
                    plan.provider.id,
                    "unchanged",
                    current.main,
                    len(plan.stations),
                    0,
                    len(plan.carried),
                    0,
                    0,
                )
            )
            continue
        outcome = _build_provider(
            path, plan, hydrolog, count, selected, on_progress, on_notice, cancel
        )
        outcomes.append(outcome)
        if outcome.status == "cancelled":
            break
    files = tuple(
        version_file(outcome.version, outcome.status)
        for outcome in outcomes
        if outcome.version is not None
        and (outcome.status == "new" or outcome.status == "unchanged")
    )
    return AnalysesReport(
        _overall(outcomes), hydrolog.version, tuple(outcomes), (), files
    )


def check_analyses(
    root: RootArg | None = None,
    /,
    *,
    stations: Iterable[str] | None = None,
    workers: int = 1,
    on_progress: ProgressHook | None = None,
    on_notice: NoticeHook | None = None,
    cancel: Cancel | None = None,
) -> StorePlan:
    """
    Plan `build_analyses` without writing and without computing.

    Hydrolog's program is asked only for its version (``config show``),
    which decides with the series and the registry which stations a build
    computes and which it carries forward.

    Parameters
    ----------
    root, stations, workers, on_progress, on_notice, cancel
        As in `build_analyses`; ``workers`` is checked, ``on_progress`` and
        ``on_notice`` are not called, ``cancel`` is not polled.

    Returns
    -------
    StorePlan
        ``obserwator-plan/1`` with one ``analyses build`` action per provider:
        ``current`` (the version stays), ``newer`` (a new version: stations
        to compute and to carry forward) or ``missing`` (no version yet); a
        ``missing`` action without series to analyse; a ``conflict`` action
        for a root that a build refuses.

    Raises
    ------
    ObserwatorValidationError, ObserwatorError, ObserwatorStoreError
        As `build_analyses` before it computes.
    """
    _workers(workers)
    selected = _selection(stations)
    refused = root_conflict_plan(_COMMAND, _write_root(root))
    if refused is not None:
        return refused
    path = _data_root(root)
    hydrolog = open_hydrolog()
    actions: list[PlanAction] = []
    for plan in _plans(path, hydrolog.version or "", selected):
        name = plan.provider.short_name
        if plan.unchanged:
            actions.append(
                PlanAction(
                    _COMMAND,
                    "current",
                    message(
                        "analyses.plan_current",
                        provider=name,
                        stations=len(plan.stations),
                    ),
                )
            )
        else:
            actions.append(
                PlanAction(
                    _COMMAND,
                    "missing" if plan.current is None else "newer",
                    message(
                        "analyses.plan_build",
                        provider=name,
                        computed=len(plan.compute),
                        carried=len(plan.carried),
                        version=hydrolog.version,
                    ),
                )
            )
    if not actions:
        actions.append(PlanAction(_COMMAND, "missing", message("analyses.no_series")))
    return StorePlan(
        "obserwator-plan/1", path, datetime.now(UTC), (), {}, tuple(actions)
    )


# --------------------------------------------------------------------------
# Reading
# --------------------------------------------------------------------------


def list_analyses(
    version: PathArg | None = None,
    /,
    *,
    root: RootArg | None = None,
    station: str,
) -> tuple[AnalysisSummary, ...]:
    """
    List the stored analyses of one station: command, options, status, versions.

    Parameters
    ----------
    version : str, os.PathLike or None, optional
        An analyses version: its directory, ``analyses.json`` or sidecar,
        absolute or relative to ``root`` (to the working directory without
        it). None reads the current version of the station's provider in
        ``root``.
    root : str, os.PathLike, StoreHandle or None, optional
        The data root; None is the default root.
    station : str
        Station code; its grammar names the provider (IMGW-PIB nine digits,
        ČHMÚ WIGOS identifier).

    Returns
    -------
    tuple of AnalysisSummary
        The station's analyses in registry order, without Hydrolog's answers.

    Raises
    ------
    ObserwatorValidationError
        If ``station`` is no station code.
    ObserwatorStoreError
        Code ``not_found``: no analyses version of the provider, no version
        at ``version``, or no station in it.
    ObserwatorDataError
        If the version or the station's record does not match its SHA-256.
    """
    code, provider = _code(station)
    found = _station_version(version, root, provider)
    record = _record(found, code)
    return tuple(_summary(record, entry, found) for entry in record["results"])


def _result(summary: AnalysisSummary, document: Mapping[str, Any]) -> AnalysisResult:
    ok = document.get("schema") == _RESULT
    return AnalysisResult(
        summary.station,
        summary.provider,
        summary.kind,
        summary.analysis,
        summary.command,
        summary.options,
        summary.inputs,
        summary.hydrolog,
        summary.computed_at,
        summary.stored,
        summary.status,
        summary.error_code,
        document if ok else None,
        None if ok else document,
        summary.attribution,
        summary.terms_notice,
        summary.analyses_version,
    )


def read_analysis(
    version: PathArg | None = None,
    /,
    *,
    root: RootArg | None = None,
    station: str,
    analysis: str,
) -> AnalysisResult:
    """
    Read one stored analysis of a station: Hydrolog's answer with its provenance.

    Parameters
    ----------
    version : str, os.PathLike or None, optional
        As in `list_analyses`.
    root : str, os.PathLike, StoreHandle or None, optional
        The data root; None is the default root.
    station : str
        Station code.
    analysis : str
        Id of the analysis (`analysis_definitions`).

    Returns
    -------
    AnalysisResult
        The summary's fields with ``envelope`` (``hydrolog-result/1``) or
        ``error`` (``hydrolog-error/1``) exactly as Hydrolog wrote them.

    Raises
    ------
    ObserwatorValidationError
        If ``station`` is no station code.
    ObserwatorStoreError
        Code ``not_found``: as `list_analyses`, or the station has no stored
        ``analysis`` (``details.allowed`` lists those it has).
    ObserwatorDataError
        If a file of the version does not match its SHA-256.
    """
    code, provider = _code(station)
    found = _station_version(version, root, provider)
    record = _record(found, code)
    entry = _entry(record, analysis)
    return _result(_summary(record, entry, found), json.loads(_line(found, entry)))


# --------------------------------------------------------------------------
# Export
# --------------------------------------------------------------------------


def _cell(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return _number(value) if math.isfinite(value) else ""
    return str(value)


def _leaves(value: object, pointer: str = "") -> Iterator[tuple[str, object]]:
    """``(JSON Pointer, value)`` of every scalar leaf of ``value`` (RFC 6901)."""
    if isinstance(value, Mapping):
        for key, item in value.items():
            token = str(key).replace("~", "~0").replace("/", "~1")
            yield from _leaves(item, f"{pointer}/{token}")
    elif isinstance(value, list):
        for number, item in enumerate(value):
            yield from _leaves(item, f"{pointer}/{number}")
    else:
        yield pointer, value


def _selected(
    record: Mapping[str, Any], analyses: Iterable[str] | None
) -> list[Mapping[str, Any]]:
    if analyses is None:
        return list(record["results"])
    if isinstance(analyses, str) or not isinstance(analyses, Iterable):
        raise ObserwatorValidationError(
            message("analyses.analyses_not_list"),
            details={"option": "analyses", "value": str(analyses)},
        )
    return [_entry(record, name) for name in dict.fromkeys(analyses)]


def _series_versions(record: Mapping[str, Any], entry: Mapping[str, Any]) -> list[str]:
    return [
        item["series_version"]
        for item in record["inputs"]
        if item["dataset"] in entry["datasets"]
    ]


@overload
def export_analyses(
    version: PathArg | None = None,
    /,
    *,
    root: RootArg | None = None,
    station: str,
    analyses: Iterable[str] | None = None,
    format: Literal["json", "csv"] = "json",
    output: None = None,
    force: bool = False,
    on_progress: ProgressHook | None = None,
    on_notice: NoticeHook | None = None,
    cancel: Cancel | None = None,
) -> Iterator[str]: ...


@overload
def export_analyses(
    version: PathArg | None = None,
    /,
    *,
    root: RootArg | None = None,
    station: str,
    analyses: Iterable[str] | None = None,
    format: Literal["json", "csv"] = "json",
    output: PathArg,
    force: bool = False,
    on_progress: ProgressHook | None = None,
    on_notice: NoticeHook | None = None,
    cancel: Cancel | None = None,
) -> OutputReport: ...


def export_analyses(
    version: PathArg | None = None,
    /,
    *,
    root: RootArg | None = None,
    station: str,
    analyses: Iterable[str] | None = None,
    format: Literal["json", "csv"] = "json",
    output: PathArg | None = None,
    force: bool = False,
    on_progress: ProgressHook | None = None,
    on_notice: NoticeHook | None = None,
    cancel: Cancel | None = None,
) -> OutputReport | Iterator[str]:
    """
    Export the stored analyses of one station as JSON or CSV with the attribution.

    ``json`` is one line, the document ``obserwator-analyses-export/1``:
    ``station``, ``provider``, ``kind``, ``analyses_version``,
    ``series_versions`` (dataset, version directory, SHA-256),
    ``hydrolog_version`` and ``results``, each with ``analysis``,
    ``command``, ``options``, ``status``, ``computed_at``, ``series_versions``,
    Hydrolog's ``result`` and ``notices`` (or its ``error`` document),
    ``attribution`` and ``terms_notice``; then the station's ``attribution``
    and ``terms_notice``. ``csv`` (UTF-8, comma, CRLF) is long: one row per
    scalar leaf of Hydrolog's ``result`` of every ``ok`` analysis,
    ``station,analysis,command,series_version,hydrolog_version,path,value``
    with ``path`` a JSON Pointer (RFC 6901) into ``result``, followed by the
    attribution columns of ``series export`` (``attribution_source`` and
    ``attribution_processed`` in the first row, ``attribution`` and
    ``terms_notice`` one line per row from the first).

    Parameters
    ----------
    version : str, os.PathLike or None, optional
        As in `list_analyses`.
    root : str, os.PathLike, StoreHandle or None, optional
        The data root; None is the default root.
    station : str
        Station code.
    analyses : iterable of str or None, optional
        Ids of the analyses to export; None exports every stored one.
    format : {"json", "csv"}, optional
        The format of the lines.
    output : str, os.PathLike or None, optional
        The one plain file to write (DEV-19.1), moved into place when whole;
        None returns the lines.
    force : bool, optional
        Replace an existing ``output``; needs ``output``.
    on_progress : ProgressHook or None, optional
        Called every 256 rows and once at the end (``unit="row"``).
    on_notice : NoticeHook or None, optional
        Receives the ``license_terms`` notice of the provider before the
        first line.
    cancel : Cancel or None, optional
        Polled before the first line, every 256 rows and before the file is
        moved into place.

    Returns
    -------
    OutputReport or Iterator[str]
        With ``output`` the written file; otherwise the lines.

    Raises
    ------
    ObserwatorValidationError
        If ``format`` is not ``json`` or ``csv``, ``output`` is a directory,
        ``force`` lacks ``output`` or ``station`` is no station code.
    ObserwatorError
        Code ``conflict`` when ``output`` exists without ``force`` or lies in
        a store.
    ObserwatorStoreError
        Code ``not_found``: as `read_analysis`.
    ObserwatorDataError
        If a file of the version does not match its SHA-256.
    ObserwatorCancelledError
        If ``cancel`` returns ``True``.
    """
    _format(format, _FORMATS)
    target = _target(output, force=force)
    code, provider = _code(station)
    found = _station_version(version, root, provider)
    record = _record(found, code)
    chosen = _selected(record, analyses)
    _check_cancel(cancel)
    lines = _record_lines(record)
    if on_notice is not None:
        on_notice(Notice("info", "license_terms", provider.license_notice(lines)))
    hydrolog_version = str(record["hydrolog"]["version"])
    documents = [json.loads(_line(found, entry)) for entry in chosen]
    if format == "json":
        results = []
        for entry, document in zip(chosen, documents, strict=True):
            ok = document.get("schema") == _RESULT
            results.append(
                {
                    "analysis": entry["analysis"],
                    "command": entry["command"],
                    "options": entry["options"],
                    "status": entry["status"],
                    "computed_at": record["computed_at"],
                    "series_versions": _series_versions(record, entry),
                    "result": document.get("result") if ok else None,
                    "notices": document.get("notices", []) if ok else [],
                    "error": None if ok else document,
                    "attribution": document.get("attribution", []) if ok else [],
                    "terms_notice": document.get("terms_notice", []) if ok else [],
                }
            )
        export = {
            "schema": EXPORT_SCHEMA,
            "station": code,
            "provider": provider.id,
            "kind": record["kind"],
            "analyses_version": found.directory.name,
            "series_versions": [
                {
                    key: item[key]
                    for key in ("dataset", "series_version", "series_sha256")
                }
                for item in record["inputs"]
            ],
            "hydrolog_version": hydrolog_version,
            "results": results,
            "attribution": list(lines.attribution),
            "terms_notice": list(lines.terms_notice),
        }
        text = json.dumps(export, ensure_ascii=False, separators=(",", ":")) + "\n"
        rows: Iterable[str] = [text]
        head: tuple[str, ...] = ()
    else:
        first = record["inputs"][0]["dataset"] if record["inputs"] else None
        formulas = (
            (get_dataset(first).license.attribution, provider.processed_attribution)
            if first is not None
            else ("", "")
        )

        def table() -> Iterator[list[str]]:
            number = 0
            for entry, document in zip(chosen, documents, strict=True):
                if document.get("schema") != _RESULT:
                    continue
                series = ";".join(_series_versions(record, entry))
                for path, value in _leaves(document.get("result")):
                    yield [
                        code,
                        str(entry["analysis"]),
                        str(entry["command"]),
                        series,
                        hydrolog_version,
                        path,
                        _cell(value),
                        *(formulas if number == 0 else ("", "")),
                    ]
                    number += 1

        head = (_csv_line(list(_CSV_HEADER)),)
        rows = _csv_lines(_with_lines(table(), lines))
    return _deliver(
        _Lines(
            head,
            rows,
            total=None,
            label=message("analyses.export_progress", station=code),
            on_progress=on_progress,
            cancel=cancel,
        ),
        target=target,
        cancel=cancel,
        done=message("analyses.exported", station=code),
    )


def export_lines(
    version: PathArg | None, root: RootArg | None, station: str
) -> Attribution:
    """The attribution lines of a station's stored analyses (the envelope of an export)."""
    code, provider = _code(station)
    return _record_lines(_record(_station_version(version, root, provider), code))


# --------------------------------------------------------------------------
# On the fly
# --------------------------------------------------------------------------


def _chain(definition: AnalysisDefinition) -> list[AnalysisDefinition]:
    """``definition`` and every analysis it depends on, in registry order."""
    needed = {definition.id}
    pending = [definition]
    while pending:
        for name in pending.pop().depends_on:
            if name not in needed:
                needed.add(name)
                pending.append(get_definition(name))
    return [item for item in analysis_definitions() if item.id in needed]


def _overrides(
    definition: AnalysisDefinition, options: Mapping[str, Any] | None
) -> dict[str, dict[str, Any]]:
    """
    The checked options of a person per analysis of the chain.

    An option goes to the analysis and to every analysis it depends on that
    declares it, except those the analysis keeps fixed (``locked``).
    """
    if options is None:
        return {}
    if not isinstance(options, Mapping):
        raise ObserwatorValidationError(
            message("analyses.options_not_mapping"), details={"option": "options"}
        )
    chain = [
        (item, () if item.id == definition.id else definition.locked)
        for item in _chain(definition)
    ]
    allowed = sorted(
        {
            option.name
            for item, locked in chain
            for option in item.overridable
            if option.name not in locked
        }
    )
    result: dict[str, dict[str, Any]] = {}
    for name, value in options.items():
        targets = [
            item
            for item, locked in chain
            if str(name) not in locked and item.option(str(name)) is not None
        ]
        if not targets:
            raise ObserwatorValidationError(
                message(
                    "analyses.option_not_overridable",
                    option=name,
                    analysis=definition.id,
                    allowed=", ".join(allowed) or message("common.none"),
                ),
                details={"option": str(name), "allowed": allowed},
            )
        for target in targets:
            spec = target.option(str(name))
            assert spec is not None
            result.setdefault(target.id, {})[str(name)] = spec.check(value)
    return result


def _timeout(timeout: object) -> float:
    if not _is_number(timeout) or cast(float, timeout) <= 0:
        raise ObserwatorValidationError(
            message("analyses.invalid_timeout", timeout=timeout),
            details={"option": "timeout", "value": str(timeout)},
        )
    return float(cast(float, timeout))


def compute_analysis(
    root: RootArg | None = None,
    /,
    *,
    station: str,
    analysis: str,
    options: Mapping[str, Any] | None = None,
    timeout: float = _DEFAULT_TIMEOUT,
    cancel: Cancel | None = None,
) -> AnalysisResult:
    """
    Compute one analysis of a station on the fly with a person's options; keep nothing.

    The station's current series go to a fresh scratch directory outside the
    data root (removed afterwards) and Hydrolog computes the analysis and the
    analyses it takes numbers from, one process per round, as a build does;
    nothing is written to the data root or to any other lasting file.

    Parameters
    ----------
    root : str, os.PathLike, StoreHandle or None, optional
        The data root; None is the default root.
    station : str
        Station code.
    analysis : str
        Id of the analysis (`analysis_definitions`).
    options : Mapping of str to object or None, optional
        Changes of the registry's options: only the overridable options of
        the analysis or of an analysis it depends on (which gets the change
        too), each checked against its type and bounds; never a file or a
        column.
    timeout : float, optional
        Seconds for the whole computation (30 by default); Hydrolog's
        process is killed past it.
    cancel : Cancel or None, optional
        Polled while Hydrolog runs; ``True`` kills it.

    Returns
    -------
    AnalysisResult
        ``stored`` False and ``analyses_version`` None; ``inputs`` name the
        current series versions and the files Hydrolog read.

    Raises
    ------
    ObserwatorValidationError
        If ``analysis`` is unknown, ``station`` is no station code, an
        option may not be changed or is of the wrong type or outside its
        bounds, or ``timeout`` is not positive.
    ObserwatorStoreError
        Code ``not_found`` (``details.reason`` ``no_series``) when the
        station's series (or its catalog entry) do not allow the analysis.
    ObserwatorDataError
        Code ``data_error`` (``details.reason`` ``dependency_failed``) when an
        analysis it takes a number from gave none.
    ObserwatorError
        Code ``missing_dependency`` (``hydrolog_missing``) without Hydrolog;
        ``source_unavailable`` with ``details.reason`` ``timeout`` past the
        timeout or ``hydrolog_failed``.
    ObserwatorCancelledError
        If ``cancel`` returned ``True``.
    """
    definition = get_definition(analysis)
    code, provider = _code(station)
    overrides = _overrides(definition, options)
    seconds = _timeout(timeout)
    path = _data_root(root)
    chain = _chain(definition)
    series = _current_series(path, (key for item in chain for key in item.datasets()))
    catalog = (
        _current_catalog(path, provider)
        if any(pick.analysis is None for item in chain for pick in item.picks)
        else None
    )
    found = _provider_stations(provider, series, catalog, chain).get(code)
    if found is None or definition.id not in {
        planned.definition.id for planned in found.planned
    }:
        raise ObserwatorStoreError(
            message("analyses.not_applicable", analysis=definition.id, station=code),
            code="not_found",
            details={"reason": "no_series", "option": "station", "value": code},
        )
    hydrolog = Hydrolog(program_words(), None)
    deadline = Deadline.after(seconds)
    scratch = _scratch()
    try:
        version, computed = _compute(
            hydrolog,
            scratch,
            "compute",
            [found],
            overrides=overrides,
            deadline=deadline,
            cancel=cancel,
        )
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    answers = {
        outcome.planned.definition.id: outcome for outcome in computed[0].outcomes
    }
    outcome = answers.get(definition.id)
    if outcome is None:
        failed = next(
            (
                answers[name]
                for name in definition.depends_on
                if name in answers and not answers[name].ok
            ),
            None,
        )
        raise ObserwatorDataError(
            message(
                "analyses.dependency_without_result",
                analysis=definition.id,
                reason=(failed.document.get("message") if failed else None)
                or message("analyses.no_value"),
            ),
            details={"reason": "dependency_failed", "analysis": definition.id},
        )
    sources = {item["dataset"]: item for item in _sources(computed[0])}
    lines = _dataset_lines(outcome.datasets) | outcome.lines()
    summary = AnalysisSummary(
        code,
        provider.id,
        found.kind,
        definition.id,
        definition.command,
        dict(outcome.options),
        tuple(AnalysisSource(**sources[key]) for key in outcome.datasets),
        {"version": version},
        computed[0].computed_at,
        False,
        "ok" if outcome.ok else "failed",
        outcome.error_code,
        lines.attribution,
        lines.terms_notice,
        None,
    )
    return _result(summary, outcome.document)
