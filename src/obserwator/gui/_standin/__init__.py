"""
A stand-in for the stored analyses of the Nogat plan's O2, until they land in Obserwator.

It answers like O2's functions (``list_analyses``, ``read_analysis``,
``compute_analysis`` of ``obserwator.store.analyses``; the documents of
``AnalysisSummary`` and ``AnalysisResult``, ``obserwator-analysis/1``) over the GUI's
read-only snapshot of the data root (`Snapshot`), for the ids of O2's registry
(`registry`, a temporary copy). O2's compute path is ported as it is: the analyses an
id takes numbers from (its chain) are planned for the station, the series files are
exported into a private temporary directory, and Hydrolog's program runs one batch per
round of calls (`hydrolog`); a person's options are checked against the registry and
an option of a dependency is passed on to it. Nothing is stored before O2:
``read_analysis`` finds nothing and every result comes from ``compute_analysis``.

When O2 lands, this package goes and the GUI calls ``obserwator.list_analyses``,
``read_analysis`` and ``compute_analysis``.
"""

from __future__ import annotations

import json
import math
import os
import shutil
import tempfile
import threading
from collections import OrderedDict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from obserwator.attribution import Attribution, attribution, dataset_origin
from obserwator.datasets import get_dataset
from obserwator.exceptions import (
    ObserwatorDataError,
    ObserwatorError,
    ObserwatorValidationError,
)
from obserwator.gui._root import Snapshot
from obserwator.gui._standin.hydrolog import Call, Deadline, Hydrolog
from obserwator.gui._standin.registry import (
    BY_ID,
    DEFINITIONS,
    AnalysisDefinition,
    AnalysisOption,
    AnalysisPick,
    AnalysisVariant,
    Kind,
)
from obserwator.messages import message
from obserwator.store import export_series
from obserwator.store.types import SeriesIndex

__all__ = ["ANALYSIS_SCHEMA", "SUMMARY_SCHEMA", "StandIn"]

ANALYSIS_SCHEMA = "obserwator-analysis/1"
SUMMARY_SCHEMA = "obserwator-analysis-summary/1"
EXPORTS_KEPT = 16
"""How many exported series files stay in the private directory."""
_RESULT = "hydrolog-result/1"


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


@dataclass(frozen=True)
class _Planned:
    """An analysis of the registry that applies to a station: its variant and files."""

    definition: AnalysisDefinition
    variant: AnalysisVariant
    files: tuple[tuple[str, str], ...]


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


def _export_name(code: str, key: str) -> str:
    """The name of a series file as O2 gives it to Hydrolog."""
    return f"{code}_{get_dataset(key).slug}.csv"


@dataclass(frozen=True)
class _Station:
    """A station to analyse: its series, catalog entry and applicable analyses."""

    code: str
    provider: str
    kind: Kind
    properties: Mapping[str, Any]
    planned: tuple[_Planned, ...]

    def datasets(self) -> tuple[str, ...]:
        """The datasets the planned analyses read, in order of first use."""
        return tuple(
            dict.fromkeys(key for planned in self.planned for _, key in planned.files)
        )

    def datasets_of(self, planned: _Planned) -> tuple[str, ...]:
        """The datasets an analysis reads, with those of the analyses it depends on."""
        by_id = {item.definition.id: item for item in self.planned}
        found: dict[str, None] = {}
        pending = [planned]
        while pending:
            current = pending.pop()
            for _, key in current.files:
                found.setdefault(key)
            pending += [by_id[name] for name in current.definition.depends_on]
        return tuple(key for key in self.datasets() if key in found)

    def options(self, planned: _Planned) -> dict[str, Any]:
        """The options of an analysis before the picks: the registry's and the files."""
        return {
            **planned.definition.options,
            **planned.variant.options,
            **{option: _export_name(self.code, key) for option, key in planned.files},
        }


@dataclass(frozen=True)
class _Outcome:
    """Hydrolog's answer to the call of one analysis of a station."""

    planned: _Planned
    options: Mapping[str, Any]
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


def _chain(definition: AnalysisDefinition) -> list[AnalysisDefinition]:
    """``definition`` and every analysis it depends on, in registry order."""
    needed = {definition.id}
    pending = [definition]
    while pending:
        for name in pending.pop().depends_on:
            if name not in needed:
                needed.add(name)
                pending.append(BY_ID[name])
    return [item for item in DEFINITIONS if item.id in needed]


def _reachable(
    definition: AnalysisDefinition,
) -> list[tuple[AnalysisDefinition, tuple[str, ...]]]:
    """The chain with the options a change given for ``definition`` does not reach."""
    return [
        (item, () if item.id == definition.id else definition.locked)
        for item in _chain(definition)
    ]


def _overrides(
    definition: AnalysisDefinition, options: Mapping[str, object]
) -> dict[str, dict[str, Any]]:
    """
    The checked options of a person per analysis of the chain.

    An option goes to the analysis and to every analysis it depends on that
    declares it, except those the analysis keeps fixed (``locked``).

    Raises
    ------
    ObserwatorValidationError
        For an option no analysis of the chain lets change (``details.allowed``),
        or a value of the wrong type or outside its bounds (``details.option``).
    """
    chain = _reachable(definition)
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
            if name not in locked and item.option(name) is not None
        ]
        if not targets:
            raise ObserwatorValidationError(
                message(
                    "gui.analyses.option_not_overridable",
                    option=name,
                    analysis=definition.id,
                    allowed=", ".join(allowed) or message("common.none"),
                ),
                details={"option": name, "allowed": allowed},
            )
        for target in targets:
            spec = target.option(name)
            assert spec is not None
            result.setdefault(target.id, {})[name] = spec.check(value)
    return result


def _dataset_lines(keys: Iterable[str]) -> Attribution:
    """The lines of data of the given datasets: parsed and computed (ADR-012)."""
    return attribution(*dict.fromkeys(dataset_origin(key) for key in keys))


def _instant(moment: datetime) -> str:
    return moment.isoformat().replace("+00:00", "Z")


class StandIn:
    """
    O2's functions over the GUI's data root, computing every result on request.

    Parameters
    ----------
    root : Path
        The data root (read only).
    command : tuple of str or None
        Hydrolog's program and its leading arguments; None when the deployment has
        none (nothing is computed).
    work : Path or None, optional
        The private directory of the exported series and of Hydrolog's batches; a
        new temporary one by default.
    """

    def __init__(
        self, root: Path, command: tuple[str, ...] | None, work: Path | None = None
    ) -> None:
        self.root = root
        self.program = Hydrolog(command) if command else None
        self._work = work
        self._exports: OrderedDict[tuple[str, str, str], tuple[Path, str]] = (
            OrderedDict()
        )
        self._lock = threading.Lock()

    # --- the registry ---------------------------------------------------------------

    def definition(self, analysis: str) -> AnalysisDefinition:
        """
        The definition of an id.

        Raises
        ------
        ObserwatorError
            ``not_found`` for an id that is not in the registry.
        """
        found = BY_ID.get(analysis)
        if found is None:
            raise ObserwatorError(
                message("gui.errors.no_analysis", analysis=analysis),
                code="not_found",
                details={"option": "analysis", "value": analysis[:200]},
            )
        return found

    def overridable(self, analysis: str) -> dict[str, AnalysisOption]:
        """
        The options a person may change for an id, its own before its dependencies'.

        An option of an analysis it depends on is passed on to that analysis,
        unless the id keeps it fixed (``locked``).
        """
        found: dict[str, AnalysisOption] = {}
        definition = self.definition(analysis)
        reachable = _reachable(definition)
        reachable.sort(key=lambda entry: entry[0].id != definition.id)
        for item, locked in reachable:
            for option in item.overridable:
                if option.name not in locked:
                    found.setdefault(option.name, option)
        return found

    def check_options(
        self, analysis: str, options: Mapping[str, object]
    ) -> dict[str, Any]:
        """
        A person's options of an id, typed and checked as O2's ``compute_analysis`` does.

        Parameters
        ----------
        analysis : str
            The id.
        options : Mapping
            Option names and values; numbers may come as text, an array as text
            with commas (a query string).

        Returns
        -------
        dict
            The options with their values as Hydrolog takes them.

        Raises
        ------
        ObserwatorError
            ``not_found`` for an unknown id.
        ObserwatorValidationError
            For an option the id does not let change, or a value of the wrong type or
            outside its bounds.
        """
        definition = self.definition(analysis)
        checked = _overrides(definition, options)
        return {
            name: next(values[name] for values in checked.values() if name in values)
            for name in options
        }

    # --- the station ----------------------------------------------------------------

    def _station(
        self,
        snapshot: Snapshot,
        code: str,
        definitions: Iterable[AnalysisDefinition],
    ) -> _Station | None:
        """The station's plan for ``definitions`` over the snapshot's current series."""
        chosen = tuple(definitions)
        keys = dict.fromkeys(key for item in chosen for key in item.datasets())
        held = {
            key: _holdings(snapshot.series[key].index, code)
            for key in keys
            if key in snapshot.series and code in snapshot.series[key].index.stations
        }
        if not held:
            return None
        first = get_dataset(next(iter(held)))
        feature = snapshot.features.get(code)
        properties = dict(feature.properties) if feature is not None else {}
        planned = _plan(cast(Kind, first.kind), held, properties, chosen)
        if not planned:
            return None
        return _Station(
            code, first.provider, cast(Kind, first.kind), properties, planned
        )

    def _version_dir(self, snapshot: Snapshot, key: str) -> str:
        """The series version directory, relative to the root (POSIX) as O2 names it."""
        directory = snapshot.series[key].version.path.parent
        for base in (self.root, self.root.resolve()):
            if directory.is_relative_to(base):
                return directory.relative_to(base).as_posix()
        return directory.as_posix()

    def _source(self, snapshot: Snapshot, code: str, key: str) -> dict[str, Any]:
        series = snapshot.series[key]
        return {
            "dataset": key,
            "series_version": self._version_dir(snapshot, key),
            "series_sha256": series.version.sha256,
            "station_sha256": series.index.stations[code].sha256,
        }

    # --- O2's functions -------------------------------------------------------------

    def list_analyses(
        self, snapshot: Snapshot, station: str
    ) -> tuple[dict[str, Any], ...]:
        """
        The ids that apply to a station, in registry order, as summaries.

        Nothing is stored before O2: a summary has the command, the options known
        before Hydrolog runs (without the picks), the series it reads, the lines of
        their data and the options a person may change (``overridable``); no
        ``hydrolog``, ``computed_at`` or ``status``.
        """
        found = self._station(snapshot, station, DEFINITIONS)
        if found is None:
            return ()
        sources = {
            key: self._source(snapshot, station, key) for key in found.datasets()
        }
        summaries = []
        for planned in found.planned:
            datasets = found.datasets_of(planned)
            lines = _dataset_lines(datasets)
            definition = planned.definition
            summaries.append(
                {
                    "schema": SUMMARY_SCHEMA,
                    "station": station,
                    "provider": found.provider,
                    "kind": found.kind,
                    "analysis": definition.id,
                    "command": definition.command,
                    "options": found.options(planned),
                    "inputs": [
                        {**sources[key], "export_sha256": None} for key in datasets
                    ],
                    "hydrolog": None,
                    "computed_at": None,
                    "stored": False,
                    "status": None,
                    "error_code": None,
                    "attribution": list(lines.attribution),
                    "terms_notice": list(lines.terms_notice),
                    "analyses_version": None,
                    "overridable": {
                        name: option.schema()
                        for name, option in self.overridable(definition.id).items()
                    },
                }
            )
        return tuple(summaries)

    def read_analysis(
        self, snapshot: Snapshot, station: str, analysis: str
    ) -> dict[str, Any] | None:
        """Nothing is stored before O2: None for every id of the registry."""
        self.definition(analysis)
        return None

    def compute_analysis(
        self,
        snapshot: Snapshot,
        station: str,
        analysis: str,
        options: Mapping[str, object] | None = None,
        *,
        timeout: float = 30.0,
    ) -> dict[str, Any]:
        """
        Compute one id of a station on the fly with a person's options; keep nothing.

        Hydrolog computes the id and the analyses it takes numbers from, one
        process per round, on the station's series of the snapshot.

        Parameters
        ----------
        snapshot : Snapshot
            The data root's current versions.
        station : str
            The station.
        analysis : str
            The id.
        options : Mapping or None, optional
            Changes of the registry's options (`check_options`).
        timeout : float, optional
            Seconds for the whole computation; Hydrolog's process is killed past it.

        Returns
        -------
        dict
            ``obserwator-analysis/1`` with ``stored`` false: ``status`` ``ok`` with
            Hydrolog's ``envelope``, or ``failed`` with its ``error`` document.

        Raises
        ------
        ObserwatorError
            ``not_found`` for an unknown id or one the station's series (or its
            catalog entry) do not allow (``details.reason`` ``no_series``);
            ``missing_dependency`` without Hydrolog's program; ``source_unavailable``
            past the timeout (``details.reason`` ``timeout``) or when the program
            fails (``hydrolog_failed``).
        ObserwatorValidationError
            For an option that may not be changed or a wrong value.
        ObserwatorDataError
            ``data_error`` (``details.reason`` ``dependency_failed``) when an analysis
            the id takes a number from gave none.
        """
        definition = self.definition(analysis)
        overrides = _overrides(definition, options or {})
        found = self._station(snapshot, station, _chain(definition))
        if found is None or definition.id not in {
            planned.definition.id for planned in found.planned
        }:
            raise ObserwatorError(
                message(
                    "gui.errors.analysis_not_for_station",
                    analysis=definition.id,
                    station=station,
                ),
                code="not_found",
                details={"reason": "no_series", "option": "station", "value": station},
            )
        if self.program is None:
            raise ObserwatorError(
                message("gui.errors.no_hydrolog"),
                code="missing_dependency",
                details={"reason": "hydrolog_missing"},
            )
        deadline = Deadline.after(timeout)
        scratch = Path(tempfile.mkdtemp(prefix="compute-", dir=self._directory()))
        try:
            exports = {
                key: self._export(snapshot, key, station, scratch)
                for key in found.datasets()
            }
            version, answers = self._rounds(found, scratch, overrides, deadline)
        finally:
            shutil.rmtree(scratch, ignore_errors=True)
        computed_at = _instant(datetime.now(UTC))
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
                    "gui.analyses.dependency_without_result",
                    analysis=definition.id,
                    reason=(failed.document.get("message") if failed else None)
                    or message("gui.analyses.no_value"),
                ),
                details={"reason": "dependency_failed", "analysis": definition.id},
            )
        lines = _dataset_lines(outcome.datasets) | outcome.lines()
        return {
            "schema": ANALYSIS_SCHEMA,
            "station": station,
            "provider": found.provider,
            "kind": found.kind,
            "analysis": definition.id,
            "command": definition.command,
            "options": dict(outcome.options),
            "inputs": [
                {
                    **self._source(snapshot, station, key),
                    "export_sha256": exports[key],
                }
                for key in outcome.datasets
            ],
            "hydrolog": {"version": version},
            "computed_at": computed_at,
            "stored": False,
            "status": "ok" if outcome.ok else "failed",
            "error_code": outcome.error_code,
            "envelope": dict(outcome.document) if outcome.ok else None,
            "error": None if outcome.ok else dict(outcome.document),
            "attribution": list(lines.attribution),
            "terms_notice": list(lines.terms_notice),
            "analyses_version": None,
        }

    def _rounds(
        self,
        station: _Station,
        scratch: Path,
        overrides: Mapping[str, Mapping[str, Any]],
        deadline: Deadline,
    ) -> tuple[str, dict[str, _Outcome]]:
        """Every planned analysis of the station: one Hydrolog process per round."""
        program = cast(Hydrolog, self.program)
        answers: dict[str, _Outcome] = {}
        version = ""
        for level in sorted({planned.definition.level for planned in station.planned}):
            calls: list[Call] = []
            owners: list[tuple[_Planned, dict[str, Any]]] = []
            for planned in station.planned:
                definition = planned.definition
                if definition.level != level:
                    continue
                picked = _picked(definition, answers, station.properties)
                if picked is None:
                    continue
                options = {
                    **station.options(planned),
                    **picked,
                    **overrides.get(definition.id, {}),
                }
                calls.append(Call(definition.command, options))
                owners.append((planned, options))
            if not calls:
                continue
            version, lines = program.batch(
                scratch, f"compute-{level}", calls, deadline=deadline
            )
            for (planned, options), line in zip(owners, lines, strict=True):
                answers[planned.definition.id] = _Outcome(
                    planned,
                    options,
                    cast(Mapping[str, Any], json.loads(line)),
                    station.datasets_of(planned),
                )
        return version, answers

    # --- the series files -----------------------------------------------------------

    def _directory(self) -> Path:
        with self._lock:
            if self._work is None:
                self._work = Path(tempfile.mkdtemp(prefix="obserwator-gui-"))
            self._work.mkdir(parents=True, exist_ok=True)
            return self._work

    def _export(self, snapshot: Snapshot, key: str, code: str, scratch: Path) -> str:
        """
        Put the station's series of a dataset into ``scratch`` under O2's file name.

        The file is exported once per series version (`export_series` of the
        snapshot's version) and kept for the next computations (`EXPORTS_KEPT`);
        ``scratch`` gets a hard link to it (a copy where links do not work).

        Returns
        -------
        str
            SHA-256 of the file.
        """
        version = snapshot.series[key].version
        cached = (key, version.sha256, code)
        exports = self._directory() / "exports"
        with self._lock:
            hit = self._exports.get(cached)
            if hit is None or not hit[0].is_file():
                target = (
                    exports
                    / f"{code}_{get_dataset(key).slug}_{version.sha256[:16]}.csv"
                )
                report = export_series(
                    version.path, station=code, output=target, force=True
                )
                hit = (target, report.files[0].sha256)
                self._exports[cached] = hit
                while len(self._exports) > EXPORTS_KEPT:
                    _, (old, _) = self._exports.popitem(last=False)
                    old.unlink(missing_ok=True)
            self._exports.move_to_end(cached)
            name = scratch / _export_name(code, key)
            try:
                os.link(hit[0], name)
            except OSError:
                shutil.copyfile(hit[0], name)
            return hit[1]

    def close(self) -> None:
        """Remove the private directory of exported series."""
        with self._lock:
            self._exports.clear()
            if self._work is not None:
                shutil.rmtree(self._work, ignore_errors=True)
                self._work = None
