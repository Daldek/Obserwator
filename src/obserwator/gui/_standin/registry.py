"""
A temporary copy of O2's registry of analyses, until O2 lands in Obserwator.

Copied from the Nogat plan's O2 (``src/obserwator/store/analysis_registry.py`` of the
branch ``feature/data-root-o2``, not committed yet, as StoreO2 updated it to Hydrolog
14e8f06 on 2026-11-13: ``threshold`` of ``stats threshold-events``, ``bin_*`` and
``exceedance_percents`` of ``stats duration-curve``, the reference period of the
normals, the multi-day quantiles of precipitation and ``locked``). Titles and the digest
of stored versions are left out: the GUI shows its own titles and stores nothing. This
module goes when O2 lands; the GUI then reads ``obserwator.store.analysis_registry``.

An analysis is one call of a Hydrolog command over the whole record of a station: its id
(dotted, e.g. ``characteristic.Q``, ``threshold_events.Q.swx``), the kind of station it
serves (``hydro``, ``meteo``), the command and its options, the series files it gives
Hydrolog (the first variant whose datasets hold the station with the variables), the
options it takes from Hydrolog's result of another analysis of the station or from the
station's catalog entry (picks), and the options a person may change when the analysis
is computed on the fly. An analysis that takes an option from another's result runs in
the next round of calls: every such number is Hydrolog's, copied from its result;
Obserwator computes none (Nogat ECO-059).
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field, replace
from types import MappingProxyType
from typing import Any, Literal

from obserwator.exceptions import ObserwatorValidationError
from obserwator.messages import message

Kind = Literal["hydro", "meteo"]
OptionType = Literal["integer", "number", "boolean", "string", "array"]
_INTEGER = re.compile(r"-?[0-9]+")
# Why a number is outside the bounds of an option, by bound.
_BOUND_REASONS: dict[str, Callable[[float | None], str]] = {
    "minimum": lambda limit: message("gui.analyses.reason_minimum", limit=limit),
    "maximum": lambda limit: message("gui.analyses.reason_maximum", limit=limit),
    "exclusive_minimum": lambda limit: message(
        "gui.analyses.reason_exclusive_minimum", limit=limit
    ),
    "exclusive_maximum": lambda limit: message(
        "gui.analyses.reason_exclusive_maximum", limit=limit
    ),
}


def _frozen(options: Mapping[str, Any]) -> Mapping[str, Any]:
    return MappingProxyType(dict(options))


def _shown(value: object) -> object:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, list | tuple):
        return [_shown(item) for item in value]
    return repr(value)


@dataclass(frozen=True)
class AnalysisOption:
    """
    An option of an analysis that a person may change (computed on the fly).

    Attributes
    ----------
    name : str
        The option of the Hydrolog command.
    type : {"integer", "number", "boolean", "string", "array"}
        Its JSON type, as Hydrolog's schema gives it.
    items : {"integer", "number"} or None, optional
        The type of the items of an array.
    enum : tuple of str, optional
        The allowed values of a string.
    minimum, maximum : float or None, optional
        Inclusive bounds of a number (of every item of an array).
    exclusive_minimum, exclusive_maximum : float or None, optional
        Exclusive bounds of a number (of every item of an array).
    min_items, max_items : int or None, optional
        Bounds of the length of an array.
    """

    name: str
    type: OptionType
    items: Literal["integer", "number"] | None = None
    enum: tuple[str, ...] = ()
    minimum: float | None = None
    maximum: float | None = None
    exclusive_minimum: float | None = None
    exclusive_maximum: float | None = None
    min_items: int | None = None
    max_items: int | None = None

    def _refuse(self, value: object, reason: str) -> ObserwatorValidationError:
        return ObserwatorValidationError(
            message(
                "gui.analyses.option_value_invalid",
                option=self.name,
                value=value,
                reason=reason,
            ),
            details={"option": self.name, "value": _shown(value)},
        )

    def _number(self, value: object, integer: bool) -> int | float:
        number: int | float | None = None
        if isinstance(value, bool):
            number = None
        elif isinstance(value, int):
            number = value
        elif isinstance(value, float) and math.isfinite(value):
            number = int(value) if integer and value.is_integer() else value
        elif isinstance(value, str):
            text = value.strip()
            if _INTEGER.fullmatch(text):
                number = int(text)
            elif not integer:
                try:
                    parsed = float(text)
                except ValueError:
                    parsed = math.nan
                number = parsed if math.isfinite(parsed) else None
        if number is None or (integer and not isinstance(number, int)):
            raise self._refuse(
                value,
                message(
                    "gui.analyses.reason_integer"
                    if integer
                    else "gui.analyses.reason_number"
                ),
            )
        bounds: tuple[tuple[float | None, bool, str], ...] = (
            (self.minimum, self.minimum is None or number >= self.minimum, "minimum"),
            (self.maximum, self.maximum is None or number <= self.maximum, "maximum"),
            (
                self.exclusive_minimum,
                self.exclusive_minimum is None or number > self.exclusive_minimum,
                "exclusive_minimum",
            ),
            (
                self.exclusive_maximum,
                self.exclusive_maximum is None or number < self.exclusive_maximum,
                "exclusive_maximum",
            ),
        )
        for limit, holds, name in bounds:
            if not holds:
                raise self._refuse(value, _BOUND_REASONS[name](limit))
        return number

    def check(self, value: object) -> object:
        """
        The value as Hydrolog takes it, checked against the type and the bounds.

        Numbers may come as text (a query string); an array also as text
        with commas.

        Raises
        ------
        ObserwatorValidationError
            If the value is not of the type or outside the bounds
            (``details.option`` is the option).
        """
        if self.type == "boolean":
            if isinstance(value, str) and value.strip().lower() in ("true", "false"):
                return value.strip().lower() == "true"
            if not isinstance(value, bool):
                raise self._refuse(value, message("gui.analyses.reason_boolean"))
            return value
        if self.type == "string":
            if not isinstance(value, str) or value not in self.enum:
                raise self._refuse(
                    value,
                    message("gui.analyses.reason_enum", allowed=", ".join(self.enum)),
                )
            return value
        if self.type in ("integer", "number"):
            return self._number(value, self.type == "integer")
        items: list[object]
        if isinstance(value, str):
            items = [part for part in value.split(",") if part.strip()]
        elif isinstance(value, list | tuple):
            items = list(value)
        else:
            raise self._refuse(value, message("gui.analyses.reason_array"))
        if (self.min_items is not None and len(items) < self.min_items) or (
            self.max_items is not None and len(items) > self.max_items
        ):
            raise self._refuse(
                value,
                message(
                    "gui.analyses.reason_items",
                    minimum=self.min_items or 0,
                    maximum=self.max_items if self.max_items is not None else "∞",
                ),
            )
        return [self._number(item, self.items == "integer") for item in items]

    def schema(self) -> dict[str, object]:
        """The option as ``api/analyses`` shows it: its type and the bounds it has."""
        found: dict[str, object] = {"type": self.type}
        if self.items is not None:
            found["items"] = self.items
        if self.enum:
            found["enum"] = list(self.enum)
        for name in (
            "minimum",
            "maximum",
            "exclusive_minimum",
            "exclusive_maximum",
            "min_items",
            "max_items",
        ):
            bound = getattr(self, name)
            if bound is not None:
                found[name] = bound
        return found


@dataclass(frozen=True)
class AnalysisInput:
    """
    A series file of the station that Hydrolog reads.

    Attributes
    ----------
    option : str
        The Hydrolog option that takes the file: ``input_file`` (a daily
        series) or ``half_year_file`` (IMGW-PIB's half-year characteristics).
    datasets : tuple of str
        Dataset keys, in order of preference: the first whose current series
        holds the station with every variable is exported (``series export``).
    variables : tuple of str
        The variables that need values at the station.
    """

    option: str
    datasets: tuple[str, ...]
    variables: tuple[str, ...]


@dataclass(frozen=True)
class AnalysisVariant:
    """
    One way of computing an analysis: its series files and their options.

    Attributes
    ----------
    inputs : tuple of AnalysisInput
        The series files.
    options : Mapping of str to object
        The options of these files (columns, ``parameter``), merged over the
        options of the analysis.
    """

    inputs: tuple[AnalysisInput, ...]
    options: Mapping[str, Any] = field(default_factory=lambda: _frozen({}))


@dataclass(frozen=True)
class AnalysisPick:
    """
    An option of an analysis taken from Hydrolog's result of another analysis.

    Attributes
    ----------
    option : str
        The option of the Hydrolog command.
    pointer : str
        JSON Pointer (RFC 6901) into Hydrolog's ``result`` of ``analysis``,
        or into the station's catalog properties without ``analysis``.
    analysis : str or None, optional
        The id of the analysis whose result gives the value; None for the
        station's catalog entry (ČHMÚ's thresholds).
    each : str or None, optional
        A pointer into every item of the array at ``pointer``: the option is
        the array of these values. Picks of one array keep the same items:
        an item without every value (``null``) is left out of all of them.
    where : str or None, optional
        A pointer into every item: only the items where it is ``true``.
    offset : int, optional
        Added to an integer value (``last_year`` − 9: the last ten years).
    """

    option: str
    pointer: str
    analysis: str | None = None
    each: str | None = None
    where: str | None = None
    offset: int = 0


@dataclass(frozen=True)
class AnalysisDefinition:
    """
    One analysis of the registry: a Hydrolog call over the whole record of a station.

    Attributes
    ----------
    id : str
        Dotted id, unique in the registry.
    kind : {"hydro", "meteo"}
        The kind of station it serves.
    command : str
        The Hydrolog command.
    options : Mapping of str to object
        Its options besides the files, the variant's options and the picks.
    variants : tuple of AnalysisVariant
        The ways of computing it, in order: the first whose inputs the
        station has is used.
    picks : tuple of AnalysisPick, optional
        Options taken from Hydrolog's results of other analyses of the
        station or from its catalog entry.
    overridable : tuple of AnalysisOption, optional
        The options a person may change on the fly; a change of an option of
        an analysis it depends on is passed on to that analysis.
    depends_on : tuple of str, optional
        The analyses whose results its picks read.
    level : int, optional
        Its round of Hydrolog calls: 0 without a dependency, else one more
        than its dependencies.
    locked : tuple of str, optional
        Options of the analyses it depends on that a change given for it
        does not reach: its picks read a position of their result that the
        registry's value fixes (the 10 mm count of ``thresholds_mm``).
    """

    id: str
    kind: Kind
    command: str
    options: Mapping[str, Any]
    variants: tuple[AnalysisVariant, ...]
    picks: tuple[AnalysisPick, ...] = ()
    overridable: tuple[AnalysisOption, ...] = ()
    depends_on: tuple[str, ...] = ()
    level: int = 0
    locked: tuple[str, ...] = ()

    def datasets(self) -> tuple[str, ...]:
        """Every dataset any of its variants may read, in order, once each."""
        return tuple(
            dict.fromkeys(
                key
                for variant in self.variants
                for item in variant.inputs
                for key in item.datasets
            )
        )

    def option(self, name: str) -> AnalysisOption | None:
        """The overridable option ``name``, or None."""
        return next((item for item in self.overridable if item.name == name), None)


# --- definitions -------------------------------------------------------------------------

_HYDRO_DAILY = ("pl.imgw.hydro_daily", "cz.chmi.hydro_daily")
_HALF_YEARS = ("pl.imgw.hydro_semiannual",)
_METEO_DAILY = (
    "pl.imgw.meteo_climate_daily",
    "pl.imgw.meteo_precip_daily",
    "cz.chmi.meteo_daily",
)
_DATE = {"date_column": "date"}
_YEARS = (
    AnalysisOption("first_year", "integer", minimum=1),
    AnalysisOption("last_year", "integer", minimum=1),
)
# The reference period of the normals: Hydrolog takes it for precipitation sums,
# heavy and seasonality, temperature means and the SPI only, by default the
# analysed years.
_REFERENCE = (
    AnalysisOption("reference_first_year", "integer", minimum=1),
    AnalysisOption("reference_last_year", "integer", minimum=1),
)
_YEAR_TYPE = AnalysisOption("year_type", "string", enum=("calendar", "hydrological"))
# The return periods of the mockup's tables and probability curves: T = 2…1000
# years and 100/p for the exceedance percentages p of its curves.
_RETURN_PERIODS = (
    1.0101010101,
    1.0204081633,
    1.0526315789,
    1.1111111111,
    1.25,
    1.4285714286,
    1.6666666667,
    2.0,
    2.5,
    3.3333333333,
    5.0,
    6.6666666667,
    10.0,
    14.2857142857,
    20.0,
    33.3333333333,
    50.0,
    66.6666666667,
    100.0,
    142.8571428571,
    200.0,
    333.3333333333,
    500.0,
    666.6666666667,
    1000.0,
)
# The fit of a frequency analysis. Its years choose the hydrological years of a
# series: values without dates (the quantiles of precipitation) have none, so
# there the years go to the analysis that gives the values.
_FIT = (
    AnalysisOption(
        "distribution",
        "string",
        enum=("all", "log_normal", "gev", "pearson3", "weibull"),
    ),
    AnalysisOption(
        "fit_method",
        "string",
        enum=("l_moments", "mle", "moments", "least_squares", "all"),
    ),
    AnalysisOption(
        "return_periods",
        "array",
        items="number",
        exclusive_minimum=1.0,
        min_items=1,
        max_items=50,
    ),
)
_FREQUENCY = (*_FIT, *_YEARS)


def _daily(
    *variables: str, columns: Mapping[str, Any] | None = None
) -> AnalysisVariant:
    """A variant reading a daily hydrological series (IMGW-PIB or ČHMÚ)."""
    return AnalysisVariant(
        (AnalysisInput("input_file", _HYDRO_DAILY, variables),),
        _frozen({**(columns or {"value_column": variables[0]}), **_DATE}),
    )


def _half_years(variable: str) -> AnalysisVariant:
    """A variant reading IMGW-PIB's half-year characteristics of ``variable``."""
    return AnalysisVariant(
        (
            AnalysisInput(
                "half_year_file",
                _HALF_YEARS,
                (f"{variable}_min", f"{variable}_mean", f"{variable}_max"),
            ),
        ),
        _frozen({"parameter": variable}),
    )


def _meteo(*variables: str, columns: Mapping[str, Any]) -> AnalysisVariant:
    """A variant reading a daily meteorological series (IMGW-PIB or ČHMÚ)."""
    return AnalysisVariant(
        (AnalysisInput("input_file", _METEO_DAILY, variables),),
        _frozen({**columns, **_DATE}),
    )


_PRECIPITATION = {
    "precipitation_column": "P",
    "precipitation_flag_column": "P_flag",
}


def _define(
    id: str,
    kind: Kind,
    command: str,
    variants: Iterable[AnalysisVariant],
    *,
    options: Mapping[str, Any] | None = None,
    picks: Iterable[AnalysisPick] = (),
    overridable: Iterable[AnalysisOption] = (),
    locked: Iterable[str] = (),
) -> AnalysisDefinition:
    chosen = tuple(picks)
    return AnalysisDefinition(
        id,
        kind,
        command,
        _frozen(options or {}),
        tuple(variants),
        chosen,
        tuple(overridable),
        tuple(dict.fromkeys(p.analysis for p in chosen if p.analysis is not None)),
        locked=tuple(locked),
    )


_VARIABLES = ("H", "Q", "T")
# The levels of IMGW-PIB's characteristics and ČHMÚ's thresholds of the catalog
# that the days and events of a variable count from.
_LEVELS = ("swx", "ssx", "snx")
_CHMI_LEVELS = ("spa1", "spa2", "spa3", "q50", "drought")
_EVENT_OPTIONS = (
    *_YEARS,
    AnalysisOption("min_duration_days", "integer", minimum=1),
    AnalysisOption("max_gap_days", "integer", minimum=0),
)
_TRENDS = tuple(
    (variable, statistic)
    for variable in ("Q", "H", "T")
    for statistic in ("max", "mean", "min")
)
_WATER_TEMPERATURE = (
    ("ge15", 15.0, "above"),
    ("ge20", 20.0, "above"),
    ("ge25", 25.0, "above"),
    ("lt1", 1.0, "below"),
)


def _trend(
    id: str,
    kind: Kind,
    source: str,
    value: str,
    where: str | None = None,
    locked: tuple[str, ...] = (),
) -> AnalysisDefinition:
    """Mann–Kendall with Sen's slope of an annual series of another analysis."""
    return _define(
        id,
        kind,
        "stats mann-kendall",
        (AnalysisVariant(()),),
        options={"alpha": 0.05},
        picks=(
            AnalysisPick("values", "/years", source, each=value, where=where),
            AnalysisPick("years", "/years", source, each="/year", where=where),
        ),
        overridable=(
            AnalysisOption(
                "alpha", "number", exclusive_minimum=0.0, exclusive_maximum=1.0
            ),
        ),
        locked=locked,
    )


def _hydro() -> list[AnalysisDefinition]:
    found: list[AnalysisDefinition] = []
    for variable in _VARIABLES:
        found.append(
            _define(
                f"characteristic.{variable}",
                "hydro",
                "stats characteristic",
                (_daily(variable),),
                options={"parameter": variable},
                overridable=_YEARS,
            )
        )
        found.append(
            _define(
                f"characteristic.{variable}.half_years",
                "hydro",
                "stats characteristic",
                (_half_years(variable),),
                overridable=_YEARS,
            )
        )
    for variable in ("H", "Q"):
        for key in _LEVELS:
            found.append(
                _define(
                    f"threshold_events.{variable}.{key}",
                    "hydro",
                    "stats threshold-events",
                    (_daily(variable),),
                    options={"direction": "below" if key == "snx" else "above"},
                    picks=(
                        AnalysisPick(
                            "threshold", f"/{key}", f"characteristic.{variable}"
                        ),
                    ),
                    overridable=_EVENT_OPTIONS,
                )
            )
    for variable in ("H", "Q"):
        for key in _CHMI_LEVELS:
            found.append(
                _define(
                    f"threshold_events.{variable}.{key}",
                    "hydro",
                    "stats threshold-events",
                    (_daily(variable),),
                    options={"direction": "below" if key == "drought" else "above"},
                    picks=(AnalysisPick("threshold", f"/thresholds/{variable}/{key}"),),
                    overridable=_EVENT_OPTIONS,
                )
            )
    rating = {"level_column": "H", "discharge_column": "Q"}
    found += [
        _define(
            "rating_curve",
            "hydro",
            "hydrometrics rating-curve",
            (_daily("H", "Q", columns=rating),),
            picks=(
                AnalysisPick("first_year", "/last_year", "characteristic.Q", offset=-9),
                AnalysisPick("last_year", "/last_year", "characteristic.Q"),
            ),
            overridable=(
                *_YEARS,
                AnalysisOption("remove_outliers", "boolean"),
                AnalysisOption("outlier_std", "number", exclusive_minimum=0.0),
            ),
        ),
        _define(
            "rating_curve.periods",
            "hydro",
            "hydrometrics rating-curve",
            (_daily("H", "Q", columns=rating),),
            options={"years_per_period": 10},
            overridable=(
                *_YEARS,
                AnalysisOption("years_per_period", "integer", minimum=2, maximum=30),
                AnalysisOption("remove_outliers", "boolean"),
            ),
        ),
        _define(
            "flood_frequency.Q",
            "hydro",
            "stats flood-frequency",
            (_half_years("Q"), _daily("Q")),
            options={
                "distribution": "all",
                "fit_method": "l_moments",
                "return_periods": list(_RETURN_PERIODS),
            },
            overridable=_FREQUENCY,
        ),
        _define(
            "low_flow.Q",
            "hydro",
            "stats low-flow",
            (_daily("Q"),),
            options={"return_periods": list(_RETURN_PERIODS)},
            overridable=(_FIT[2], *_YEARS),
        ),
        _define(
            "homogeneity.Q",
            "hydro",
            "stats homogeneity",
            (_half_years("Q"), _daily("Q")),
            options={"alpha": 0.05},
            overridable=(
                AnalysisOption(
                    "alpha", "number", exclusive_minimum=0.0, exclusive_maximum=1.0
                ),
                AnalysisOption("split_year", "integer", minimum=1),
                *_YEARS,
            ),
        ),
        _define(
            "low_flow_sequences.Q",
            "hydro",
            "stats low-flow-sequences",
            (_daily("Q"),),
            options={
                "parameter": "Q",
                "threshold_method": "mean_annual_minimum",
                "min_duration_days": 5,
                "max_gap_days": 4,
            },
            overridable=(
                AnalysisOption(
                    "threshold_method",
                    "string",
                    enum=("mean_annual_minimum", "exceedance", "value"),
                ),
                AnalysisOption("threshold", "number", exclusive_minimum=0.0),
                AnalysisOption(
                    "exceedance_percent",
                    "number",
                    exclusive_minimum=0.0,
                    exclusive_maximum=100.0,
                ),
                AnalysisOption("min_duration_days", "integer", minimum=1, maximum=90),
                AnalysisOption("max_gap_days", "integer", minimum=0, maximum=30),
                *_YEARS,
            ),
        ),
    ]
    for variable, bins in (
        ("H", {"bin_method": "width", "bin_width": 10}),
        ("Q", {"bin_method": "log", "bin_count": 40}),
    ):
        found.append(
            _define(
                f"duration_curve.{variable}",
                "hydro",
                "stats duration-curve",
                (_daily(variable),),
                options=bins,
                overridable=(
                    *_YEARS,
                    AnalysisOption("month", "integer", minimum=1, maximum=12),
                    AnalysisOption(
                        "exceedance_percents",
                        "array",
                        items="number",
                        exclusive_minimum=0.0,
                        exclusive_maximum=100.0,
                        min_items=1,
                        max_items=50,
                    ),
                    AnalysisOption("bin_width", "number", exclusive_minimum=0.0)
                    if variable == "H"
                    else AnalysisOption("bin_count", "integer", minimum=2),
                ),
            )
        )
    found.append(
        _define(
            "water_level_zones.H",
            "hydro",
            "hydrometrics water-level-zones",
            (
                AnalysisVariant(
                    (AnalysisInput("input_file", _HYDRO_DAILY, ("H",)),),
                    _frozen({"value_column": "H"}),
                ),
            ),
            options={"bin_width": 10},
            overridable=(AnalysisOption("bin_width", "number", exclusive_minimum=0.0),),
        )
    )
    for variable in _VARIABLES:
        found += [
            _define(
                f"daily.{variable}",
                "hydro",
                "stats daily",
                (_daily(variable),),
            ),
            _define(
                f"monthly.{variable}",
                "hydro",
                "stats monthly",
                (_daily(variable),),
                options={"confidence_level": 0.95},
                overridable=(
                    AnalysisOption(
                        "confidence_level",
                        "number",
                        exclusive_minimum=0.0,
                        exclusive_maximum=1.0,
                    ),
                ),
            ),
        ]
    found.append(
        _define(
            "regime.Q",
            "hydro",
            "stats regime",
            (_daily("Q"),),
            overridable=_YEARS,
        )
    )
    for statistic in ("max", "min"):
        found.append(
            _define(
                f"seasonality.Q.{statistic}",
                "hydro",
                "stats seasonality",
                (
                    _half_years("Q"),
                    _daily("Q", columns={"value_column": "Q", "parameter": "Q"}),
                ),
                options={"statistic": statistic},
                overridable=_YEARS,
            )
        )
    found.append(
        _define(
            "harmonics.T",
            "hydro",
            "stats harmonics",
            (_daily("T"),),
            options={"harmonics": 2},
            overridable=(
                AnalysisOption("harmonics", "integer", minimum=1, maximum=4),
                *_YEARS,
            ),
        )
    )
    for key, threshold, direction in _WATER_TEMPERATURE:
        found.append(
            _define(
                f"threshold_events.T.{key}",
                "hydro",
                "stats threshold-events",
                (_daily("T"),),
                options={"threshold": threshold, "direction": direction},
                overridable=_EVENT_OPTIONS,
            )
        )
    found += [
        _define(
            "runoff_volume.Q",
            "hydro",
            "stats runoff-volume",
            (_daily("Q"),),
            overridable=(
                *_YEARS,
                AnalysisOption("cumulative_year", "integer", minimum=1),
            ),
        ),
        _define(
            "baseflow.Q",
            "hydro",
            "stats baseflow",
            (_daily("Q"),),
            options={"alpha": 0.925, "passes": 3},
            overridable=(
                AnalysisOption("alpha", "number", exclusive_minimum=0.0, maximum=1.0),
                AnalysisOption("passes", "integer", minimum=3),
                AnalysisOption("series_year", "integer", minimum=1),
                *_YEARS,
            ),
        ),
    ]
    for variable, statistic in _TRENDS:
        found.append(
            _trend(
                f"mann_kendall.{variable}.{statistic}",
                "hydro",
                f"characteristic.{variable}",
                f"/annual/{statistic}",
            )
        )
    return found


def _meteo_definitions() -> list[AnalysisDefinition]:
    precipitation = (_meteo("P", columns=_PRECIPITATION),)
    found: list[AnalysisDefinition] = []
    indices: tuple[tuple[str, Mapping[str, Any], tuple[AnalysisOption, ...]], ...] = (
        ("sums", {}, _REFERENCE),
        (
            "maxima",
            # Hydrolog gives the 1-day maximum first (/durations/0) and these after it.
            {"durations_days": [2, 3, 5, 10]},
            (
                AnalysisOption(
                    "durations_days",
                    "array",
                    items="integer",
                    minimum=1,
                    maximum=30,
                    min_items=1,
                    max_items=10,
                ),
            ),
        ),
        (
            "days",
            # The trend of the days reads the count of the third, 10 mm (/days/2).
            {"thresholds_mm": [0.1, 1.0, 10.0, 20.0]},
            (
                AnalysisOption(
                    "thresholds_mm",
                    "array",
                    items="number",
                    exclusive_minimum=0.0,
                    min_items=1,
                    max_items=10,
                ),
            ),
        ),
        (
            "intensity",
            {},
            (AnalysisOption("wet_day_mm", "number", exclusive_minimum=0.0),),
        ),
        (
            "heavy",
            {},
            (
                AnalysisOption(
                    "percentiles",
                    "array",
                    items="number",
                    exclusive_minimum=0.0,
                    maximum=100.0,
                    min_items=1,
                    max_items=5,
                ),
                *_REFERENCE,
            ),
        ),
        ("seasonality", {}, _REFERENCE),
    )
    for index, options, extra in indices:
        found.append(
            _define(
                f"precipitation.{index}",
                "meteo",
                "meteo precipitation",
                precipitation,
                options={"index": index, **options},
                overridable=(*_YEARS, _YEAR_TYPE, *extra),
            )
        )
    # Quantiles of the annual maxima of 1, 2, 3, 5 and 10 days: position k of
    # ``durations`` follows the registry's ``durations_days``, so a change of that
    # list may not reach the maxima of a multi-day quantile.
    for suffix, position in (("", 0), (".2d", 1), (".3d", 2), (".5d", 3), (".10d", 4)):
        found.append(
            _define(
                f"precipitation_quantiles{suffix}",
                "meteo",
                "stats flood-frequency",
                (AnalysisVariant(()),),
                options={
                    "distribution": "all",
                    "fit_method": "l_moments",
                    "return_periods": list(_RETURN_PERIODS),
                },
                picks=(
                    AnalysisPick(
                        "values",
                        "/years",
                        "precipitation.maxima",
                        each=f"/durations/{position}/sum_mm",
                        where="/complete",
                    ),
                ),
                overridable=_FIT,
                locked=("durations_days",) if position else (),
            )
        )
    for kind in ("dry", "wet"):
        found.append(
            _define(
                f"spells.{kind}",
                "meteo",
                "meteo spells",
                precipitation,
                # The list of spells keeps those of 10 days or more (Kraków's whole
                # list was about 510 KB); the summaries count every spell.
                options={"kind": kind, "threshold_mm": 1.0, "min_duration_days": 10},
                overridable=(
                    AnalysisOption("threshold_mm", "number", exclusive_minimum=0.0),
                    AnalysisOption("min_duration_days", "integer", minimum=1),
                    _YEAR_TYPE,
                    *_YEARS,
                ),
            )
        )
    found.append(
        _define(
            "spi",
            "meteo",
            "meteo spi",
            precipitation,
            overridable=(
                AnalysisOption(
                    "scales_months",
                    "array",
                    items="integer",
                    minimum=1,
                    maximum=48,
                    min_items=1,
                    max_items=8,
                ),
                _YEAR_TYPE,
                *_YEARS,
                *_REFERENCE,
            ),
        )
    )
    mean = (_meteo("Tmean", columns={"tmean_column": "Tmean"}),)
    extremes = (
        _meteo("Tmax", "Tmin", columns={"tmax_column": "Tmax", "tmin_column": "Tmin"}),
    )
    days = tuple(
        AnalysisOption(name, "number")
        for name in (
            "frost_tmin_c",
            "ice_tmax_c",
            "summer_tmax_c",
            "hot_tmax_c",
            "tropical_tmin_c",
        )
    )
    degree_days = tuple(
        AnalysisOption(name, "number")
        for name in ("growing_base_c", "heating_base_c", "heating_limit_c")
    )
    temperature: tuple[
        tuple[str, tuple[AnalysisVariant, ...], tuple[AnalysisOption, ...]], ...
    ] = (
        ("means", mean, _REFERENCE),
        ("days", extremes, days),
        ("degree_days", mean, degree_days),
        ("range", extremes, ()),
    )
    for index, variants, extra in temperature:
        found.append(
            _define(
                f"temperature.{index}",
                "meteo",
                "meteo temperature",
                variants,
                options={"index": index},
                overridable=(*_YEARS, _YEAR_TYPE, *extra),
            )
        )
    found += [
        _define(
            "harmonics.Tmean",
            "meteo",
            "stats harmonics",
            (_meteo("Tmean", columns={"value_column": "Tmean"}),),
            options={"harmonics": 2},
            overridable=(
                AnalysisOption("harmonics", "integer", minimum=1, maximum=4),
                *_YEARS,
            ),
        ),
        _define(
            "hydrothermal",
            "meteo",
            "meteo hydrothermal",
            (
                _meteo(
                    "P", "Tmean", columns={**_PRECIPITATION, "tmean_column": "Tmean"}
                ),
            ),
            overridable=_YEARS,
        ),
        _define(
            "snow",
            "meteo",
            "meteo snow",
            (
                _meteo(
                    "snow_cover",
                    "fresh_snow",
                    columns={
                        "snow_cover_column": "snow_cover",
                        "fresh_snow_column": "fresh_snow",
                    },
                ),
                _meteo("snow_cover", columns={"snow_cover_column": "snow_cover"}),
            ),
            overridable=_YEARS,
        ),
    ]
    trends: tuple[tuple[str, str, str, str | None, tuple[str, ...]], ...] = (
        (
            "mann_kendall.precipitation.sums",
            "precipitation.sums",
            "/total_mm",
            None,
            (),
        ),
        (
            "mann_kendall.precipitation.maxima",
            "precipitation.maxima",
            "/durations/0/sum_mm",
            "/complete",
            (),
        ),
        (
            "mann_kendall.precipitation.days",
            "precipitation.days",
            "/days/2",
            None,
            ("thresholds_mm",),
        ),
        (
            "mann_kendall.spells.dry",
            "spells.dry",
            "/max_duration_days",
            "/complete",
            (),
        ),
        ("mann_kendall.temperature.means", "temperature.means", "/tmean_c", None, ()),
        (
            "mann_kendall.temperature.frost_days",
            "temperature.days",
            "/frost_days",
            None,
            (),
        ),
        (
            "mann_kendall.temperature.summer_days",
            "temperature.days",
            "/summer_days",
            None,
            (),
        ),
    )
    for id, source, value, where, locked in trends:
        found.append(_trend(id, "meteo", source, value, where, locked))
    return found


def _with_levels(
    definitions: list[AnalysisDefinition],
) -> tuple[AnalysisDefinition, ...]:
    """The definitions with their rounds; a dependency must come earlier."""
    levels: dict[str, int] = {}
    result = []
    for definition in definitions:
        if definition.id in levels:
            raise ValueError(f"Duplicate analysis id {definition.id!r}")
        missing = [name for name in definition.depends_on if name not in levels]
        if missing:
            raise ValueError(f"{definition.id} depends on later or unknown {missing}")
        level = max((levels[name] + 1 for name in definition.depends_on), default=0)
        levels[definition.id] = level
        result.append(replace(definition, level=level))
    return tuple(result)


DEFINITIONS: tuple[AnalysisDefinition, ...] = _with_levels(
    [*_hydro(), *_meteo_definitions()]
)
"""The registry, in order: an analysis after those it depends on."""
BY_ID: Mapping[str, AnalysisDefinition] = MappingProxyType(
    {definition.id: definition for definition in DEFINITIONS}
)
"""The registry by id."""
