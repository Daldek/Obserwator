"""
The analyses of a station: stored results first, else Hydrolog's program on request.

An analysis id is one call of Hydrolog's program (the registry of the Nogat plan's O2).
Without overrides the GUI serves the stored result over the whole record; with the
person's choices (a period, a distribution, a threshold) it asks Hydrolog to compute the
id on the fly (GUI plan D8): at most two programs at a time, 30 s each, the result held
in this server's memory only (500 results, per series version, id, options and Hydrolog
version) and never written to the data root or to disk.
"""

from __future__ import annotations

import asyncio
import threading
from collections import OrderedDict
from collections.abc import Mapping
from typing import Any

from anyio import to_thread

from obserwator.exceptions import ObserwatorError
from obserwator.gui._http import etag_of
from obserwator.gui._root import Snapshot
from obserwator.gui._standin import StandIn, check_overrides
from obserwator.messages import message

PROCESSES = 2
"""Hydrolog programs running at a time."""
TIMEOUT_S = 30.0
"""The longest computation of one id [s]."""
RESULTS = 500
"""Results computed on request kept in memory."""


class Analyses:
    """
    The analyses of the stations of one data root.

    Parameters
    ----------
    backend : StandIn
        O2's functions (the stand-in until O2 lands).
    """

    def __init__(self, backend: StandIn) -> None:
        self.backend = backend
        self._results: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self._lock = threading.Lock()
        self._running: dict[str, asyncio.Future[dict[str, Any]]] = {}
        self._slots: asyncio.Semaphore | None = None

    @property
    def can_compute(self) -> bool:
        """Whether the server has Hydrolog's program for results computed on request."""
        return self.backend.program is not None

    def hydrolog_version(self) -> str | None:
        """Hydrolog's version, asked of the program once; None without a program."""
        program = self.backend.program
        if program is None:
            return None
        try:
            program.load()
        except Exception:  # noqa: BLE001 - shown as "unknown" in the session
            return None
        return program.version

    def list(self, snapshot: Snapshot, station: str) -> tuple[dict[str, Any], ...]:
        """The ids of a station: stored summaries, or the ids that apply to it."""
        return self.backend.list_analyses(snapshot, station)

    def overrides(self, analysis: str, query: Mapping[str, str]) -> dict[str, Any]:
        """The person's overrides of an id, checked against the registry (D6)."""
        return check_overrides(self.backend.spec(analysis), query)

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
            Checked overrides (`overrides`); empty for the defaults.

        Returns
        -------
        tuple of (dict, str)
            The ``obserwator-analysis/1`` result with ``source`` (``stored`` or
            ``computed``), and its ETag.

        Raises
        ------
        ObserwatorError
            ``not_found`` for an id that does not apply, ``missing_dependency``
            without Hydrolog's program, ``source_unavailable`` when it fails or
            exceeds `TIMEOUT_S`.
        """
        if not overrides:
            stored = await to_thread.run_sync(
                self.backend.read_analysis, snapshot, station, analysis
            )
            if stored is not None:
                return {**stored, "source": "stored"}, etag_of(
                    "stored", stored.get("analyses_version"), station, analysis
                )
        key = etag_of(
            "computed",
            snapshot.key,
            station,
            analysis,
            dict(overrides),
            self.hydrolog_version(),
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
                result = await self._compute(snapshot, station, analysis, overrides)
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
        self,
        snapshot: Snapshot,
        station: str,
        analysis: str,
        overrides: Mapping[str, Any],
    ) -> dict[str, Any]:
        if self._slots is None:
            self._slots = asyncio.Semaphore(PROCESSES)
        async with self._slots:
            try:
                result = await to_thread.run_sync(
                    lambda: self.backend.compute_analysis(
                        snapshot, station, analysis, overrides, timeout=TIMEOUT_S
                    )
                )
            except TimeoutError as exc:
                raise ObserwatorError(
                    message("gui.errors.hydrolog_timeout", seconds=int(TIMEOUT_S)),
                    code="source_unavailable",
                ) from exc
        return {**result, "source": "computed"}
