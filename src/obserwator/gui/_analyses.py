"""
The analyses of a station: Hydrolog's stored results, and a person's choices on request.

``obserwator analyses build`` stores Hydrolog's result of every analysis of every station
over its whole record in the data root (ADR-016); the GUI lists and shows them
(`list_analyses`, `read_analysis`). With a person's choices (a period, a distribution, a
threshold) it asks Hydrolog to compute the analysis on the fly (`compute_analysis`, GUI
plan D8): at most two computations at a time, 30 s each, the result held in this server's
memory only (500 results, per series versions, id, options and Hydrolog version) and
never written to the data root or to disk; requests for a result being computed wait for
that computation. Hydrolog's program is the one ``analyses build`` runs
(``OBSERWATOR_HYDROLOG_COMMAND``, else ``hydrolog`` on ``PATH``), looked for once when the
app starts: without it only stored results are served. A station without stored results
lists no analyses; an id asked without stored result is computed on request.
"""

from __future__ import annotations

import asyncio
import os
import threading
from collections import OrderedDict
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

from anyio import to_thread

from obserwator import (
    AnalysisDefinition,
    AnalysisOption,
    AnalysisResult,
    AnalysisSummary,
    analysis_definitions,
    compute_analysis,
    list_analyses,
    read_analysis,
)
from obserwator._hydrolog import open_hydrolog, program_words
from obserwator._jsonable import jsonable
from obserwator.exceptions import (
    ObserwatorError,
    ObserwatorStoreError,
    ObserwatorValidationError,
)
from obserwator.gui._http import GuiError, etag_of
from obserwator.gui._root import Snapshot
from obserwator.messages import message

PROCESSES = 2
"""Computations on request running at a time."""
TIMEOUT_S = 30.0
"""The longest computation of one id [s]."""
RESULTS = 500
"""Results computed on request kept in memory."""

DEFINITIONS: Mapping[str, AnalysisDefinition] = {
    definition.id: definition for definition in analysis_definitions()
}
"""The registry of the stored analyses by id, in registry order."""


def definition_of(analysis: str) -> AnalysisDefinition:
    """
    The registry's definition of an id.

    Raises
    ------
    GuiError
        ``not_found`` for an id that is not in the registry.
    """
    found = DEFINITIONS.get(analysis)
    if found is None:
        raise GuiError(
            "not_found",
            message("gui.errors.no_analysis", analysis=analysis[:200]),
            details={"option": "analysis", "value": analysis[:200]},
        )
    return found


def overridable(definition: AnalysisDefinition) -> dict[str, AnalysisOption]:
    """
    The options a person may change for an id, its own before its dependencies'.

    An option of an analysis it depends on is passed on to that analysis, unless the
    id keeps it fixed (``locked``), as `compute_analysis` does.
    """
    needed = {definition.id}
    pending = [definition]
    while pending:
        for name in pending.pop().depends_on:
            if name not in needed:
                needed.add(name)
                pending.append(DEFINITIONS[name])
    chain = [definition] + [
        item
        for item in DEFINITIONS.values()
        if item.id in needed and item.id != definition.id
    ]
    found: dict[str, AnalysisOption] = {}
    for item in chain:
        locked = () if item is definition else definition.locked
        for option in item.overridable:
            if option.name not in locked:
                found.setdefault(option.name, option)
    return found


def option_schema(option: AnalysisOption) -> dict[str, object]:
    """An option as ``api/analyses`` shows it: its type and the bounds it has."""
    found: dict[str, object] = {"type": option.type}
    if option.items is not None:
        found["items"] = option.items
    if option.enum:
        found["enum"] = list(option.enum)
    for name in (
        "minimum",
        "maximum",
        "exclusive_minimum",
        "exclusive_maximum",
        "min_items",
        "max_items",
    ):
        bound = getattr(option, name)
        if bound is not None:
            found[name] = bound
    return found


def _names(value: object) -> object:
    """Hydrolog's ``inputs`` with each absolute path written as its file name (D6)."""
    if isinstance(value, Mapping):
        return {key: _names(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_names(item) for item in value]
    if isinstance(value, str) and os.path.isabs(value):
        return Path(value).name
    return value


def document(result: AnalysisResult | AnalysisSummary) -> dict[str, Any]:
    """
    The JSON document of a stored or computed analysis (``obserwator-analysis/1``).

    Hydrolog's envelope echoes the absolute paths of the series files it read, in a
    scratch directory of the server: only their file names are shown (D6).
    """
    found = cast(dict[str, Any], jsonable(result))
    envelope = found.get("envelope")
    if isinstance(envelope, dict) and "inputs" in envelope:
        found["envelope"] = {**envelope, "inputs": _names(envelope["inputs"])}
    return found


def _absent(exc: ObserwatorStoreError) -> bool:
    """Whether a store error says that nothing is stored (no version, no station, no id)."""
    return exc.code == "not_found"


class Analyses:
    """
    The analyses of the stations of one data root.

    Hydrolog's program is looked for once, when the app starts (`program_words`):
    without it the app computes nothing, as its session says, even if the setting
    names a program later.

    Parameters
    ----------
    root : Path
        The data root, read only.
    """

    def __init__(self, root: Path) -> None:
        self.root = root
        self._missing: ObserwatorError | None = None
        try:
            program_words()
        except ObserwatorError as exc:
            self._missing = exc
        self._version: str | None = None
        self._asked = False
        self._results: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self._lock = threading.Lock()
        self._running: dict[str, asyncio.Future[dict[str, Any]]] = {}
        self._slots: asyncio.Semaphore | None = None

    @property
    def can_compute(self) -> bool:
        """Whether Hydrolog's program was found when the app started."""
        return self._missing is None

    def hydrolog_version(self) -> str | None:
        """Hydrolog's version, asked of the program once; None without a program."""
        with self._lock:
            if self._asked:
                return self._version
        version: str | None = None
        if self.can_compute:
            try:
                version = open_hydrolog().version
            except ObserwatorError:  # shown as "unknown" in the session
                version = None
        with self._lock:
            self._version, self._asked = version, True
        return version

    def list(self, station: str) -> tuple[dict[str, Any], ...]:
        """
        The stored analyses of a station, each with the options a person may change.

        Returns
        -------
        tuple of dict
            ``obserwator-analysis-summary/1`` in registry order; empty when the data
            root has no analyses of the station's provider or none of the station.
        """
        try:
            summaries = list_analyses(root=self.root, station=station)
        except ObserwatorStoreError as exc:
            if _absent(exc):
                return ()
            raise
        return tuple(
            {
                **document(summary),
                "overridable": {
                    name: option_schema(option)
                    for name, option in overridable(
                        definition_of(summary.analysis)
                    ).items()
                },
            }
            for summary in summaries
        )

    def overrides(self, analysis: str, query: Mapping[str, str]) -> dict[str, Any]:
        """
        A person's options of an id, typed and checked against the registry (D6).

        Raises
        ------
        GuiError
            ``not_found`` for an unknown id.
        ObserwatorValidationError
            For an option the id (or an analysis it depends on) does not let change
            (``details.allowed``), or a value of the wrong type or outside its bounds.
        """
        definition = definition_of(analysis)
        allowed = overridable(definition)
        checked: dict[str, Any] = {}
        for name, value in query.items():
            option = allowed.get(name)
            if option is None:
                names = sorted(allowed)
                raise ObserwatorValidationError(
                    message(
                        "analyses.option_not_overridable",
                        option=name,
                        analysis=definition.id,
                        allowed=", ".join(names) or message("common.none"),
                    ),
                    details={"option": name, "allowed": names},
                )
            checked[name] = option.check(value)
        return checked

    def stored(self, station: str, analysis: str) -> dict[str, Any] | None:
        """The stored result of an id, or None when the data root has none."""
        try:
            return document(
                read_analysis(root=self.root, station=station, analysis=analysis)
            )
        except ObserwatorStoreError as exc:
            if _absent(exc):
                return None
            raise

    async def get(
        self,
        snapshot: Snapshot,
        station: str,
        analysis: str,
        overrides: Mapping[str, Any],
    ) -> tuple[dict[str, Any], str]:
        """
        One id of a station: the stored result, else one computed now.

        Parameters
        ----------
        snapshot : Snapshot
            The data root's current versions.
        station : str
            The station.
        analysis : str
            The id.
        overrides : Mapping
            Checked overrides (`overrides`); empty for the stored result.

        Returns
        -------
        tuple of (dict, str)
            The ``obserwator-analysis/1`` result with ``source`` (``stored`` or
            ``computed``), and its ETag.

        Raises
        ------
        ObserwatorError
            ``not_found`` for an id that does not apply, ``missing_dependency``
            without Hydrolog's program when the app started, ``source_unavailable``
            when it fails or exceeds `TIMEOUT_S`, ``data_error`` when an analysis
            the id takes a number from gave none.
        """
        definition_of(analysis)
        if not overrides:
            stored = await to_thread.run_sync(self.stored, station, analysis)
            if stored is not None:
                return {**stored, "source": "stored"}, etag_of(
                    "stored", stored.get("analyses_version"), station, analysis
                )
        missing = self._missing
        if missing is not None:
            raise ObserwatorError(
                missing.detail,
                code=missing.code,
                details=missing.details,
                hint=missing.hint,
            )
        version = await to_thread.run_sync(self.hydrolog_version)
        key = etag_of(
            "computed", snapshot.key, station, analysis, dict(overrides), version
        )
        with self._lock:
            hit = self._results.get(key)
            if hit is not None:
                self._results.move_to_end(key)
                return hit, key
        running = self._running.get(key)
        if running is None:
            running = asyncio.get_running_loop().create_future()
            self._running[key] = running
            try:
                result = await self._compute(station, analysis, overrides)
            except BaseException as exc:
                running.set_exception(exc)
                running.exception()  # retrieved: no warning when nobody else waits
                raise
            finally:
                self._running.pop(key, None)
            running.set_result(result)
            with self._lock:
                self._results[key] = result
                while len(self._results) > RESULTS:
                    self._results.popitem(last=False)
            return result, key
        return await asyncio.shield(running), key

    async def _compute(
        self, station: str, analysis: str, overrides: Mapping[str, Any]
    ) -> dict[str, Any]:
        if self._slots is None:
            self._slots = asyncio.Semaphore(PROCESSES)
        async with self._slots:
            result = await to_thread.run_sync(
                lambda: compute_analysis(
                    self.root,
                    station=station,
                    analysis=analysis,
                    options=dict(overrides) or None,
                    timeout=TIMEOUT_S,
                )
            )
        return {**document(result), "source": "computed"}
