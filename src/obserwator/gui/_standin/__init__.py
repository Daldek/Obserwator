"""
A stand-in for the stored analyses of the Nogat plan's O2, until they land in Obserwator.

It answers like O2's public functions (``list_analyses``, ``read_analysis``,
``compute_analysis``; the dict of ``AnalysisResult``, schema ``obserwator-analysis/1``)
for the analysis ids of the registry that O2 adopts (``local://gui-analysis-calls.md``):
one id is one call of Hydrolog's program, its inputs exported from the data root with
`export_series` into a private temporary directory, its options the registry's defaults
with the person's overrides, its options taken from another id's result where the id
depends on one. Nothing is stored: ``read_analysis`` finds nothing and every result
comes from ``compute_analysis``.

When O2 lands, this package goes and the GUI calls ``obserwator.list_analyses``,
``read_analysis`` and ``compute_analysis``.
"""

from __future__ import annotations

import json
import math
import shutil
import subprocess
import tempfile
import threading
from collections import OrderedDict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import obserwator
from obserwator.attribution import Attribution
from obserwator.exceptions import ObserwatorError, ObserwatorValidationError
from obserwator.gui._root import Snapshot
from obserwator.messages import message

ANALYSIS_SCHEMA = "obserwator-analysis/1"
EXPORTS_KEPT = 16
"""How many exported series files stay in the private directory."""

ParamType = Literal["integer", "number", "string", "boolean", "integers", "numbers"]


@dataclass(frozen=True)
class Param:
    """
    An option the person may change: its type and bounds.

    Attributes
    ----------
    type : {"integer", "number", "string", "boolean", "integers", "numbers"}
        The type; ``integers`` and ``numbers`` are comma-separated lists.
    minimum, maximum : float or None
        Inclusive bounds of a number (of each item of a list).
    allowed : tuple of str or None
        The values of a ``string``.
    """

    type: ParamType
    minimum: float | None = None
    maximum: float | None = None
    allowed: tuple[str, ...] | None = None


YEAR = Param("integer", 1700, 2200)
"""``first_year`` and ``last_year``: hydrological or calendar years."""


@dataclass(frozen=True)
class Dependency:
    """
    Options of an id taken from the result of another id.

    Attributes
    ----------
    analysis : str
        The id whose result feeds the options.
    select : callable
        ``select(result) -> options``: picks values of the other result (its
        ``result`` member, Hydrolog's own document); selection only, no arithmetic.
    shared : tuple of str
        The overrides passed on to the other id (the same period).
    """

    analysis: str
    select: Callable[[Mapping[str, Any]], Mapping[str, Any]]
    shared: tuple[str, ...] = ("first_year", "last_year")


@dataclass(frozen=True)
class Spec:
    """
    One analysis id: one call of Hydrolog's program.

    Attributes
    ----------
    id : str
        The dotted id (``characteristic.Q``).
    command : str
        Hydrolog's catalog command (``stats characteristic``).
    kinds : tuple of str
        The station kinds it applies to (``hydro``, ``meteo``).
    inputs : Mapping of str to tuple of str
        Each file option and the datasets that may fill it, the first the station
        holds being used (``{"input_file": ("pl.imgw.hydro_daily", …)}``).
    variables : Mapping of str to str
        Variables the input of a file option must hold for the station
        (``{"input_file": "Q"}``); without them the id does not apply.
    options : Mapping of str to object
        The other options: columns and defaults.
    overridable : Mapping of str to Param
        The options the person may change, with their types.
    depends : Dependency or None
        Options taken from another id's result.
    providers : tuple of str or None
        Only stations of these providers (``("CHMI",)``); None for every one.
    needs : callable or None
        ``needs(properties) -> bool`` for an id that applies only to stations with
        some catalog property (the ČHMÚ thresholds).
    """

    id: str
    command: str
    kinds: tuple[str, ...]
    inputs: Mapping[str, tuple[str, ...]]
    variables: Mapping[str, str] = field(default_factory=dict)
    options: Mapping[str, Any] = field(default_factory=dict)
    overridable: Mapping[str, Param] = field(default_factory=dict)
    depends: Dependency | None = None
    providers: tuple[str, ...] | None = None
    needs: Callable[[Mapping[str, Any]], bool] | None = None
    catalog_options: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None = None


class Registry:
    """The ids of the stand-in, by id; filled by the modules of this package."""

    def __init__(self, specs: Sequence[Spec]) -> None:
        self.specs: dict[str, Spec] = {}
        for spec in specs:
            if spec.id in self.specs:
                raise ValueError(f"Analysis id twice: {spec.id}")
            self.specs[spec.id] = spec


HYDRO_DAILY = ("pl.imgw.hydro_daily", "cz.chmi.hydro_daily")
"""The daily hydrological series, IMGW-PIB's before ČHMÚ's (a station has one)."""
HALF_YEARS = ("pl.imgw.hydro_semiannual",)
"""IMGW-PIB's half-year and annual characteristics."""
METEO_DAILY = (
    "pl.imgw.meteo_climate_daily",
    "cz.chmi.meteo_daily",
    "pl.imgw.meteo_precip_daily",
)
"""The daily meteorological series: climate stations before precipitation stations."""
PERIOD = {"first_year": YEAR, "last_year": YEAR}
"""The period the person may choose."""


def _registry() -> Registry:
    from obserwator.gui._standin import (
        hydro_levels,
        hydro_regime,
        meteo_precipitation,
        meteo_temperature,
    )

    return Registry(
        [
            *hydro_levels.SPECS,
            *hydro_regime.SPECS,
            *meteo_precipitation.SPECS,
            *meteo_temperature.SPECS,
        ]
    )


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


class HydrologFailed(Exception):
    """Hydrolog's program could not be run or gave no document."""


@dataclass
class _Program:
    command: tuple[str, ...]
    version: str | None = None
    options: dict[str, dict[str, dict[str, Any]]] = field(default_factory=dict)
    lock: threading.Lock = field(default_factory=threading.Lock)

    def run(
        self, args: Sequence[str], timeout: float
    ) -> subprocess.CompletedProcess[str]:
        try:
            return subprocess.run(
                [*self.command, *args],
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
                stdin=subprocess.DEVNULL,
            )
        except subprocess.TimeoutExpired as exc:
            raise TimeoutError(str(exc)) from exc
        except (OSError, subprocess.SubprocessError) as exc:
            raise HydrologFailed(str(exc)) from exc

    def load(self) -> None:
        """Hydrolog's version and the options of its catalog, asked once."""
        with self.lock:
            if self.version is not None:
                return
            done = self.run(["commands", "schema", "--json"], 60.0)
            try:
                envelope = json.loads(done.stdout)
                catalog = envelope["result"]["commands"]
            except (ValueError, KeyError, TypeError) as exc:
                raise HydrologFailed(done.stderr.strip()[-500:] or str(exc)) from exc
            self.options = {
                entry["name"]: {option["name"]: option for option in entry["options"]}
                for entry in catalog
            }
            self.version = str(envelope.get("version"))


def _flag(name: str, value: Any, schema: Mapping[str, Any]) -> list[str]:
    """One option as the CLI's flags: ``--name=value``, lists comma-separated."""
    flag = "--" + name.replace("_", "-")
    if schema.get("type") == "boolean":
        return [flag if value else "--no-" + name.replace("_", "-")]
    if name == "attribution" or (
        schema.get("type") == "array"
        and schema.get("items") not in ("number", "integer", "string")
    ):
        return [f"{flag}={json.dumps(value, ensure_ascii=False)}"]
    if isinstance(value, list | tuple):
        return [f"{flag}=" + ",".join(_plain(item) for item in value)]
    return [f"{flag}={_plain(value)}"]


def _plain(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float) and value.is_integer():
        return repr(value)
    return str(value)


class StandIn:
    """
    The functions of O2 over the GUI's data root, computing every result on request.

    Parameters
    ----------
    root : Path
        The data root.
    command : tuple of str or None
        Hydrolog's program; None when the deployment has none.
    work : Path or None, optional
        The private directory of the exported series; a new temporary one by default.
    """

    def __init__(
        self, root: Path, command: tuple[str, ...] | None, work: Path | None = None
    ) -> None:
        self.root = root
        self.registry = _registry()
        self.program = _Program(command) if command else None
        self._work = work
        self._exports: OrderedDict[tuple[str, str, str], Path] = OrderedDict()
        self._exports_lock = threading.Lock()

    # --- the registry -------------------------------------------------------------

    def spec(self, analysis: str) -> Spec:
        """The id's spec; ``not_found`` for an unknown id."""
        try:
            return self.registry.specs[analysis]
        except KeyError:
            raise ObserwatorError(
                message("gui.errors.no_analysis", analysis=analysis), code="not_found"
            ) from None

    def _inputs(
        self, spec: Spec, snapshot: Snapshot, station: str
    ) -> dict[str, str] | None:
        """The dataset of each file option, or None when the station lacks one."""
        chosen: dict[str, str] = {}
        for option, candidates in spec.inputs.items():
            wanted = spec.variables.get(option)
            for dataset in candidates:
                series = snapshot.series.get(dataset)
                entry = series.index.stations.get(station) if series else None
                if entry is None:
                    continue
                if wanted is not None and not any(
                    (name == wanted or name.startswith(f"{wanted}_"))
                    and coverage.first is not None
                    for name, coverage in entry.variables.items()
                ):
                    continue
                chosen[option] = dataset
                break
            else:
                return None
        return chosen

    def applies(
        self, spec: Spec, snapshot: Snapshot, station: str
    ) -> dict[str, str] | None:
        """The inputs of an id for a station, or None when it does not apply."""
        feature = snapshot.features.get(station)
        if feature is None:
            return None
        props = dict(feature.properties)
        if props.get("kind") not in spec.kinds:
            return None
        if spec.providers is not None and feature.provider not in spec.providers:
            return None
        if spec.needs is not None and not spec.needs(props):
            return None
        inputs = self._inputs(spec, snapshot, station)
        if inputs is None:
            return None
        if (
            spec.depends is not None
            and self.applies(self.spec(spec.depends.analysis), snapshot, station)
            is None
        ):
            return None
        return inputs

    # --- O2's functions -----------------------------------------------------------

    def list_analyses(
        self, snapshot: Snapshot, station: str
    ) -> tuple[dict[str, Any], ...]:
        """The ids that apply to a station, as summaries without results (nothing is stored)."""
        found = []
        for spec in self.registry.specs.values():
            inputs = self.applies(spec, snapshot, station)
            if inputs is None:
                continue
            found.append(
                {
                    "schema": ANALYSIS_SCHEMA,
                    "station": station,
                    "analysis": spec.id,
                    "command": spec.command,
                    "options": self._shown(spec, {}),
                    "overridable": {
                        name: {k: v for k, v in vars(param).items() if v is not None}
                        for name, param in spec.overridable.items()
                    },
                    "inputs": [
                        {
                            "dataset": dataset,
                            "series_version": snapshot.series[dataset].version.label,
                            "sha256": snapshot.series[dataset].version.sha256,
                        }
                        for dataset in inputs.values()
                    ],
                    "stored": False,
                }
            )
        return tuple(found)

    def read_analysis(
        self, snapshot: Snapshot, station: str, analysis: str
    ) -> dict[str, Any] | None:
        """Nothing is stored before O2: always None."""
        self.spec(analysis)
        return None

    def _shown(self, spec: Spec, overrides: Mapping[str, Any]) -> dict[str, Any]:
        options = {**spec.options, **overrides}
        return {
            key: value
            for key, value in options.items()
            if key not in ("values", "years", "dates")
        }

    def _export(self, snapshot: Snapshot, dataset: str, station: str) -> Path:
        """The station's series of a dataset as Obserwator's CSV, kept for a while."""
        version = snapshot.series[dataset].version
        key = (dataset, version.sha256, station)
        with self._exports_lock:
            hit = self._exports.get(key)
            if hit is not None and hit.is_file():
                self._exports.move_to_end(key)
                return hit
            if self._work is None:
                self._work = Path(tempfile.mkdtemp(prefix="obserwator-gui-"))
            work = self._work
        target = work / f"{station}_{dataset}_{version.sha256[:12]}.csv"
        if not target.is_file():
            partial = target.with_suffix(".part.csv")
            obserwator.export_series(
                root=self.root,
                dataset=dataset,
                station=station,
                format="csv",
                output=partial,
                force=True,
            )
            partial.replace(target)
        with self._exports_lock:
            self._exports[key] = target
            while len(self._exports) > EXPORTS_KEPT:
                _, old = self._exports.popitem(last=False)
                old.unlink(missing_ok=True)
        return target

    def compute_analysis(
        self,
        snapshot: Snapshot,
        station: str,
        analysis: str,
        options: Mapping[str, Any] | None = None,
        *,
        timeout: float = 30.0,
    ) -> dict[str, Any]:
        """
        One id for a station, with the person's overrides, computed now and not stored.

        Returns
        -------
        dict
            ``obserwator-analysis/1``: ``status`` ``ok`` with Hydrolog's
            ``envelope``, or ``failed`` with its ``error`` document.

        Raises
        ------
        ObserwatorError
            ``not_found`` for an id that does not apply to the station,
            ``missing_dependency`` without Hydrolog's program, ``source_unavailable``
            when the program cannot be run.
        """
        spec = self.spec(analysis)
        inputs = self.applies(spec, snapshot, station)
        if inputs is None:
            raise ObserwatorError(
                message(
                    "gui.errors.analysis_not_for_station",
                    analysis=analysis,
                    station=station,
                ),
                code="not_found",
            )
        if self.program is None:
            raise ObserwatorError(
                message("gui.errors.no_hydrolog"), code="missing_dependency"
            )
        try:
            self.program.load()
        except HydrologFailed as exc:
            raise ObserwatorError(
                message("gui.errors.hydrolog_failed", reason=str(exc)),
                code="source_unavailable",
            ) from exc
        overrides = dict(options or {})
        call = {**spec.options, **overrides}
        if spec.catalog_options is not None:
            call.update(
                spec.catalog_options(dict(snapshot.features[station].properties))
            )
        attribution = Attribution()
        if spec.depends is not None:
            shared = {
                key: overrides[key] for key in spec.depends.shared if key in overrides
            }
            base = self.compute_analysis(
                snapshot, station, spec.depends.analysis, shared, timeout=timeout
            )
            if base["status"] != "ok":
                return {**base, "analysis": analysis, "command": spec.command}
            call.update(spec.depends.select(base["envelope"]["result"]))
            attribution = Attribution(
                tuple(base["envelope"].get("attribution") or ()),
                tuple(base["envelope"].get("terms_notice") or ()),
            )
            if attribution:
                call["attribution"] = list(attribution.lines)
        files = {
            option: self._export(snapshot, dataset, station)
            for option, dataset in inputs.items()
        }
        call.update({option: str(path) for option, path in files.items()})
        schemas = self.program.options.get(spec.command, {})
        args = [*spec.command.split(), "--json"]
        for name, value in call.items():
            if value is None:
                continue
            args += _flag(name, value, schemas.get(name, {}))
        try:
            done = self.program.run(args, timeout)
        except HydrologFailed as exc:
            raise ObserwatorError(
                message("gui.errors.hydrolog_failed", reason=str(exc)),
                code="source_unavailable",
            ) from exc
        feature = snapshot.features[station]
        result: dict[str, Any] = {
            "schema": ANALYSIS_SCHEMA,
            "station": station,
            "provider": feature.provider,
            "kind": feature.properties.get("kind"),
            "analysis": analysis,
            "command": spec.command,
            "options": self._shown(spec, overrides),
            "inputs": [
                {
                    "dataset": dataset,
                    "series_version": snapshot.series[dataset].version.label,
                    "sha256": snapshot.series[dataset].version.sha256,
                }
                for dataset in inputs.values()
            ],
            "hydrolog": {"version": self.program.version},
            "computed_at": _now(),
            "stored": False,
            "analyses_version": None,
        }
        document = _document(done)
        if document is None:
            raise ObserwatorError(
                message(
                    "gui.errors.hydrolog_failed",
                    reason=done.stderr.strip()[-300:] or f"exit {done.returncode}",
                ),
                code="source_unavailable",
            )
        if document.get("schema") == "hydrolog-result/1":
            result.update(status="ok", envelope=document)
            lines = Attribution(
                tuple(document.get("attribution") or ()),
                tuple(document.get("terms_notice") or ()),
            )
        else:
            result.update(status="failed", error=document)
            lines = attribution
        result.update(lines.fields())
        return result

    def close(self) -> None:
        """Remove the private directory of exported series."""
        with self._exports_lock:
            self._exports.clear()
            if self._work is not None:
                shutil.rmtree(self._work, ignore_errors=True)
                self._work = None


def _document(done: subprocess.CompletedProcess[str]) -> dict[str, Any] | None:
    """The envelope on standard output, else the error document of standard error's last line."""
    for text in (done.stdout.strip(), (done.stderr.strip().splitlines() or [""])[-1]):
        if not text:
            continue
        try:
            document = json.loads(text)
        except ValueError:
            continue
        if isinstance(document, dict) and str(document.get("schema", "")).startswith(
            "hydrolog-"
        ):
            return document
    return None


def check_overrides(spec: Spec, query: Mapping[str, str]) -> dict[str, Any]:
    """
    The person's overrides of an id, typed and checked against its spec.

    Raises
    ------
    ObserwatorValidationError
        For an option the id does not let change, or a value of a wrong type or
        out of its bounds (``details.option``).
    """
    found: dict[str, Any] = {}
    for name, text in query.items():
        param = spec.overridable.get(name)
        if param is None:
            raise ObserwatorValidationError(
                message("gui.errors.bad_parameter", option=name, value=text),
                details={
                    "option": name,
                    "value": text,
                    "reason": "unknown",
                    "allowed": sorted(spec.overridable),
                },
            )
        found[name] = _typed(name, text, param)
    first, last = found.get("first_year"), found.get("last_year")
    if isinstance(first, int) and isinstance(last, int) and first > last:
        raise ObserwatorValidationError(
            message("gui.errors.bad_parameter", option="first_year", value=first),
            details={
                "option": "first_year",
                "value": first,
                "reason": "range",
                "maximum": last,
            },
        )
    return found


def _typed(name: str, text: str, param: Param) -> Any:
    def bad(reason: str) -> ObserwatorValidationError:
        return ObserwatorValidationError(
            message("gui.errors.bad_parameter", option=name, value=text[:200]),
            details={"option": name, "value": text[:200], "reason": reason},
        )

    def bounded(value: float) -> None:
        if (param.minimum is not None and value < param.minimum) or (
            param.maximum is not None and value > param.maximum
        ):
            raise bad("range")

    if len(text) > 400:
        raise bad("length")
    if param.type == "string":
        if param.allowed is not None and text not in param.allowed:
            raise bad("allowed")
        return text
    if param.type == "boolean":
        if text not in ("true", "false"):
            raise bad("boolean")
        return text == "true"
    items = text.split(",") if param.type in ("integers", "numbers") else [text]
    values: list[float | int] = []
    for item in items:
        try:
            value: float | int = (
                int(item) if param.type in ("integer", "integers") else float(item)
            )
        except ValueError:
            raise bad("number") from None
        if isinstance(value, float) and not math.isfinite(value):
            raise bad("number")
        bounded(value)
        values.append(value)
    return values if param.type in ("integers", "numbers") else values[0]
