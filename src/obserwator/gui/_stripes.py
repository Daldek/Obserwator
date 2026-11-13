"""
Climate stripes (Nogat plan M15): the prototype of their colour scale, until Hydrolog has it.

Ed Hawkins's warming stripes (showyourstripes.info) colour each year of a station by its
annual mean air temperature. Hydrolog gives the annual means, the normal of the reference
period and each year's anomaly from it (the analysis ``temperature.means`` with
``reference_first_year`` and ``reference_last_year``): the normal is the scale's centre.
This module computes only the rest of the scale, which moves to Hydrolog (M15): the
spread, the sample standard deviation of the annual means of a period; the ±k standard
deviations the 16 colours span; and the colour of each year's anomaly.

The two scales are those of the FAQ of showyourstripes.info ("How have these graphics
been made?"): the current page centres the colours on 1961–2010 and spans ±3.0 standard
deviations of the annual means of 1901–2000; its version of June 2019 used 1971–2000 and
±2.6. A period with an annual mean in fewer than 80 % of its years (the rule of a normal,
WMO-No. 1203, 4.4.2) falls back to the station's whole record: Hydrolog's normal of the
whole record for the centre, every annual mean for the spread.
"""

from __future__ import annotations

import math
import statistics
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction
from itertools import pairwise
from typing import TYPE_CHECKING, Any

from anyio import to_thread
from starlette.requests import Request
from starlette.responses import Response

from obserwator.gui import _params as params
from obserwator.gui._http import GuiError, error_body, etag_of, json_response, page_lang
from obserwator.messages import Lang, message

if TYPE_CHECKING:
    from obserwator.gui._state import GuiState

SCHEMA = "obserwator-gui-stripes/1"
"""The document of `stripes`."""
ANALYSIS = "temperature.means"
"""The analysis id that gives the annual means, the normal and the anomalies."""
COLOURS: tuple[str, ...] = (
    "#08306b", "#08519c", "#2171b5", "#4292c6", "#6baed6", "#9ecae1", "#c6dbef", "#deebf7",
    "#fee0d2", "#fcbba1", "#fc9272", "#fb6a4a", "#ef3b2c", "#cb181d", "#a50f15", "#67000d",
)  # fmt: skip
"""
Hawkins's colours, coldest first: the 8 darkest of ColorBrewer's 9-class sequential Blues
(darkest first) and Reds (lightest first), as showyourstripes.info uses them. ColorBrewer
colour schemes: Copyright (c) 2002 Cynthia Brewer, Mark Harrower, and The Pennsylvania
State University, Apache License 2.0. This product includes color specifications and
designs developed by Cynthia Brewer (http://colorbrewer.org/).
"""
NORMAL_SHARE = Fraction(4, 5)
"""The share of a period's years that need an annual mean (WMO-No. 1203, 4.4.2)."""
QUERY = (
    "scale",
    "centre_first_year",
    "centre_last_year",
    "spread_first_year",
    "spread_last_year",
)
"""The parameters of `stripes`."""


@dataclass(frozen=True)
class Variant:
    """
    A scale of showyourstripes.info's FAQ.

    Attributes
    ----------
    centre : tuple of (int, int)
        The years of the normal whose value is the boundary of blue and red.
    spread : tuple of (int, int)
        The years whose annual means give the standard deviation.
    k : float
        How many standard deviations the colours span on each side of the centre.
    """

    centre: tuple[int, int]
    spread: tuple[int, int]
    k: float


SCALES: Mapping[str, Variant] = {
    "2025": Variant((1961, 2010), (1901, 2000), 3.0),
    "2019": Variant((1971, 2000), (1901, 2000), 2.6),
}
"""The scales by the version of the FAQ: the current page first, then June 2019."""
DEFAULT_SCALE = "2025"
"""The scale used when none is chosen."""


@dataclass(frozen=True)
class Spread:
    """
    The spread of the annual means: their sample standard deviation over a period.

    Attributes
    ----------
    sd : float
        The sample standard deviation (n − 1) [°C].
    first_year, last_year : int
        The years it was computed from: the asked ones, else the whole record.
    years : int
        How many annual means it was computed from.
    asked_first_year, asked_last_year : int
        The period asked for.
    asked_years : int
        How many years of the asked period have an annual mean.
    fallback : bool
        Whether the asked period had too few annual means, so the whole record served.
    """

    sd: float
    first_year: int
    last_year: int
    years: int
    asked_first_year: int
    asked_last_year: int
    asked_years: int
    fallback: bool


def annual_spread(
    years: Sequence[int],
    means: Sequence[float | None],
    first_year: int,
    last_year: int,
) -> Spread:
    """
    The sample standard deviation of the annual means of a period, else of the whole record.

    The period counts when at least `NORMAL_SHARE` of its years and at least two have an
    annual mean (the rule of a normal, WMO-No. 1203, 4.4.2); otherwise every annual mean
    of the record serves. showyourstripes.info's FAQ does not name the estimator: the
    sample one (n − 1) differs from the population one by 0.5 % over 100 years.

    Parameters
    ----------
    years : Sequence of int
        The years, strictly increasing.
    means : Sequence of float or None
        Each year's annual mean [°C]; None (or NaN) for a year without one.
    first_year, last_year : int
        The period asked for.

    Returns
    -------
    Spread
        The standard deviation and the years it comes from (0.0 when the means are equal).

    Raises
    ------
    ValueError
        If the sequences differ in length, the years do not increase, the period ends
        before it starts or the whole record has fewer than two annual means.
    """
    if len(years) != len(means):
        raise ValueError("years and means differ in length")
    if any(later <= earlier for earlier, later in pairwise(years)):
        raise ValueError("the years must increase")
    if first_year > last_year:
        raise ValueError("the period ends before it starts")
    known = [
        (year, float(mean))
        for year, mean in zip(years, means, strict=True)
        if mean is not None and math.isfinite(mean)
    ]
    if len(known) < 2:
        raise ValueError("fewer than two annual means")
    inside = [mean for year, mean in known if first_year <= year <= last_year]
    span = last_year - first_year + 1
    if len(inside) >= 2 and len(inside) >= NORMAL_SHARE * span:
        return Spread(
            statistics.stdev(inside),
            first_year,
            last_year,
            len(inside),
            first_year,
            last_year,
            len(inside),
            fallback=False,
        )
    return Spread(
        statistics.stdev(mean for _, mean in known),
        known[0][0],
        known[-1][0],
        len(known),
        first_year,
        last_year,
        len(inside),
        fallback=True,
    )


@dataclass(frozen=True)
class StripeScale:
    """
    The colour scale of the stripes: the centre ± k standard deviations in 16 equal bins.

    Parameters
    ----------
    centre : float
        The normal of the centre period [°C], Hydrolog's.
    sd : float
        The standard deviation of the annual means [°C], positive.
    k : float
        Standard deviations on each side of the centre, positive.

    Raises
    ------
    ValueError
        If a value is not finite, or `sd` or `k` is not positive.
    """

    centre: float
    sd: float
    k: float

    def __post_init__(self) -> None:
        if not all(math.isfinite(value) for value in (self.centre, self.sd, self.k)):
            raise ValueError("the centre, the spread and k must be finite")
        if self.sd <= 0 or self.k <= 0:
            raise ValueError("the spread and k must be positive")

    @property
    def half_width(self) -> float:
        """The distance from the centre to either end of the scale: k standard deviations [°C]."""
        return self.k * self.sd

    @property
    def lo(self) -> float:
        """The cold end of the scale [°C]."""
        return self.centre - self.half_width

    @property
    def hi(self) -> float:
        """The warm end of the scale [°C]."""
        return self.centre + self.half_width

    @property
    def step(self) -> float:
        """The width of one colour [°C]."""
        return 2 * self.half_width / len(COLOURS)

    def edges(self) -> tuple[float, ...]:
        """The 17 bounds of the 16 colours [°C], coldest first."""
        return tuple(self.lo + index * self.step for index in range(len(COLOURS) + 1))

    def colour(self, anomaly: float | None) -> int | None:
        """
        The colour of an anomaly from the centre.

        Parameters
        ----------
        anomaly : float or None
            The annual mean minus the centre [°C]; None (or NaN) for a year without one.

        Returns
        -------
        int or None
            The index in `COLOURS` (0 the darkest blue); beyond the scale its end colour;
            None without an anomaly (a grey stripe).
        """
        if anomaly is None or not math.isfinite(anomaly):
            return None
        index = math.floor((anomaly + self.half_width) / self.step)
        return min(max(index, 0), len(COLOURS) - 1)


def _result(document: Mapping[str, Any]) -> Mapping[str, Any] | None:
    """Hydrolog's result of an analysis document that succeeded."""
    if document.get("status") != "ok":
        return None
    envelope = document.get("envelope")
    result = envelope.get("result") if isinstance(envelope, Mapping) else None
    return result if isinstance(result, Mapping) else None


def _number(value: object) -> float | None:
    """A finite number, else None."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value) if math.isfinite(value) else None


def normal_of(document: Mapping[str, Any]) -> float | None:
    """
    The normal of the reference period in an analysis document of ``temperature.means``.

    Parameters
    ----------
    document : Mapping
        An ``obserwator-analysis/1`` document.

    Returns
    -------
    float or None
        Hydrolog's ``period.normal_c``; None when the analysis failed or Hydrolog gave
        no normal (fewer than 80 % of the reference years with an annual mean).
    """
    result = _result(document)
    period = result.get("period") if result is not None else None
    return _number(period.get("normal_c")) if isinstance(period, Mapping) else None


def _slim(document: Mapping[str, Any]) -> dict[str, Any]:
    """The analysis document without Hydrolog's result: its provenance, notices and lines."""
    slim = dict(document)
    envelope = document.get("envelope")
    if isinstance(envelope, Mapping):
        slim["envelope"] = {
            key: value for key, value in envelope.items() if key != "result"
        }
    return slim


def _failed(
    station: str, error: Mapping[str, Any], used: Mapping[str, Any]
) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "station": station,
        "status": "failed",
        "error": dict(error),
        "analysis": _slim(used),
        "attribution": list(used.get("attribution") or []),
        "terms_notice": list(used.get("terms_notice") or []),
    }


def _years(result: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Hydrolog's years from the first to the last annual mean, a year missing as grey."""
    rows: dict[int, Mapping[str, Any]] = {}
    for row in result.get("years") or []:
        if isinstance(row, Mapping) and isinstance(row.get("year"), int):
            rows[row["year"]] = row
    known = [
        year for year, row in rows.items() if _number(row.get("tmean_c")) is not None
    ]
    if not known:
        return []
    found = []
    for year in range(min(known), max(known) + 1):
        row = rows.get(year, {})
        mean = _number(row.get("tmean_c"))
        months = [item for item in row.get("months") or [] if isinstance(item, Mapping)]
        found.append(
            {
                "year": year,
                "tmean_c": mean,
                "anomaly_c": _number(row.get("anomaly_c"))
                if mean is not None
                else None,
                "months_missing": 12
                - sum(1 for item in months if _number(item.get("tmean_c")) is not None),
            }
        )
    return found


def stripes_document(
    *,
    station: str,
    variant: str,
    centre: tuple[int, int],
    spread: tuple[int, int],
    asked: Mapping[str, Any],
    used: Mapping[str, Any],
    lang: Lang,
) -> dict[str, Any]:
    """
    The stripes of a station from Hydrolog's ``temperature.means``, with the prototype's scale.

    Parameters
    ----------
    station : str
        The station code.
    variant : str
        The scale's key in `SCALES`.
    centre : tuple of (int, int)
        The reference period asked for (the centre).
    spread : tuple of (int, int)
        The period of the spread asked for.
    asked : Mapping
        The analysis document computed with the asked reference period.
    used : Mapping
        The document whose normal is the centre: `asked` itself, or the one over the
        whole record when `asked` has no normal.
    lang : {"pl", "en"}
        The language of the method and of the errors.

    Returns
    -------
    dict
        ``obserwator-gui-stripes/1``: ``status`` ``ok`` with ``years`` (``year``,
        Hydrolog's ``tmean_c`` and ``anomaly_c``, ``colour``, ``months_missing``),
        ``grey``, ``scale``, ``palette``, ``scales`` (the FAQ's scales to choose
        from), the slim ``analysis`` document, the prototype's ``provenance`` and the
        lines; or ``failed`` with an ``error``.
    """
    result = _result(used)
    if result is None:
        error = used.get("error")
        if isinstance(error, Mapping):
            return _failed(station, error, used)
        return _failed(
            station,
            error_body(
                GuiError(
                    "data_error",
                    message("gui.errors.stripes_no_normal", station=station),
                ),
                lang,
            ),
            used,
        )
    rows = _years(result)
    if sum(1 for row in rows if row["tmean_c"] is not None) < 2:
        return _failed(
            station,
            error_body(
                GuiError(
                    "data_error",
                    message("gui.errors.stripes_no_years", station=station),
                ),
                lang,
            ),
            used,
        )
    normal = normal_of(used)
    if normal is None:
        return _failed(
            station,
            error_body(
                GuiError(
                    "data_error",
                    message("gui.errors.stripes_no_normal", station=station),
                ),
                lang,
            ),
            used,
        )
    deviation = annual_spread(
        [row["year"] for row in rows], [row["tmean_c"] for row in rows], *spread
    )
    if not deviation.sd > 0:
        return _failed(
            station,
            error_body(
                GuiError(
                    "data_error",
                    message("gui.errors.stripes_no_spread", station=station),
                ),
                lang,
            ),
            used,
        )
    k = SCALES[variant].k
    scale = StripeScale(normal, deviation.sd, k)
    for row in rows:
        row["colour"] = scale.colour(row["anomaly_c"])
    asked_result = _result(asked)
    asked_period = asked_result.get("period") if asked_result is not None else None
    asked_years = (
        asked_period.get("normal_years") if isinstance(asked_period, Mapping) else None
    )
    period = result.get("period")
    return {
        "schema": SCHEMA,
        "station": station,
        "status": "ok",
        "variable": "Tmean",
        "first_year": rows[0]["year"],
        "last_year": rows[-1]["year"],
        "years": rows,
        "grey": [row["year"] for row in rows if row["colour"] is None],
        "scale": {
            "variant": variant,
            "k": k,
            "centre": {
                "normal_c": normal,
                "first_year": result.get("reference_first_year"),
                "last_year": result.get("reference_last_year"),
                "years": period.get("normal_years")
                if isinstance(period, Mapping)
                else None,
                "asked_first_year": centre[0],
                "asked_last_year": centre[1],
                "asked_years": asked_years if isinstance(asked_years, int) else 0,
                "fallback": used is not asked,
            },
            "spread": {
                "sd_c": deviation.sd,
                "first_year": deviation.first_year,
                "last_year": deviation.last_year,
                "years": deviation.years,
                "asked_first_year": deviation.asked_first_year,
                "asked_last_year": deviation.asked_last_year,
                "asked_years": deviation.asked_years,
                "fallback": deviation.fallback,
            },
            "lo_c": scale.lo,
            "hi_c": scale.hi,
            "step_c": scale.step,
            "edges_c": list(scale.edges()),
        },
        "palette": list(COLOURS),
        "scales": [
            {
                "name": name,
                "centre": list(item.centre),
                "spread": list(item.spread),
                "k": item.k,
            }
            for name, item in SCALES.items()
        ],
        "analysis": _slim(used),
        "provenance": {
            "engine": "prototype",
            "method": str(message("gui.meteo.stripes.method", lang=lang)),
            "target": "M15",
        },
        "attribution": list(used.get("attribution") or []),
        "terms_notice": list(used.get("terms_notice") or []),
    }


def _period(
    query: Mapping[str, str], name: str, default: tuple[int, int]
) -> tuple[int, int]:
    """A period of the query (``<name>_first_year``, ``<name>_last_year``), else the default."""
    first = params.year(
        query.get(f"{name}_first_year"), f"{name}_first_year", default[0]
    )
    last = params.year(query.get(f"{name}_last_year"), f"{name}_last_year", default[1])
    assert first is not None and last is not None  # the defaults are years
    params.years(
        first, last, first_option=f"{name}_first_year", last_option=f"{name}_last_year"
    )
    return first, last


async def stripes(request: Request) -> Response:
    """
    ``GET api/prototype/stripes/{code}``: the climate stripes of a station (M15 prototype).

    Hydrolog's ``temperature.means`` with the centre as its reference period gives the
    annual means, the normal and the anomalies (over the whole record when the centre
    has too few annual means); the prototype adds the colour scale.

    Parameters
    ----------
    request : Request
        Query ``scale`` (``2025`` or ``2019``), ``centre_first_year``,
        ``centre_last_year``, ``spread_first_year``, ``spread_last_year`` (each by
        default the scale's).

    Returns
    -------
    Response
        ``obserwator-gui-stripes/1`` (see `stripes_document`) with an ETag.

    Raises
    ------
    GuiError
        ``validation_error`` for a wrong parameter, ``not_found`` for an unknown station.
    ObserwatorError
        From the analyses: ``not_found`` when the station has no daily mean temperature,
        ``missing_dependency`` without Hydrolog, ``source_unavailable`` when it fails.
    """
    query = request.query_params
    params.only(query, QUERY)
    variant = params.choice(query.get("scale"), "scale", tuple(SCALES), DEFAULT_SCALE)
    centre = _period(query, "centre", SCALES[variant].centre)
    spread = _period(query, "spread", SCALES[variant].spread)
    state: GuiState = request.app.state.gui
    snapshot = await to_thread.run_sync(state.root.snapshot)
    if snapshot.error is not None:
        raise snapshot.error
    code = params.station(request.path_params["code"])
    if code not in snapshot.features:
        raise GuiError(
            "not_found",
            message("gui.errors.no_station", station=code),
            details={"option": "station", "value": code},
        )
    reference = state.analyses.overrides(
        ANALYSIS,
        {"reference_first_year": str(centre[0]), "reference_last_year": str(centre[1])},
    )
    asked, asked_tag = await state.analyses.get(snapshot, code, ANALYSIS, reference)
    used, used_tag = asked, asked_tag
    if normal_of(asked) is None:
        used, used_tag = await state.analyses.get(snapshot, code, ANALYSIS, {})
    state.traffic.count("analyses_run")
    lang = page_lang(request)
    document = stripes_document(
        station=code,
        variant=variant,
        centre=centre,
        spread=spread,
        asked=asked,
        used=used,
        lang=lang,
    )
    return json_response(
        request,
        document,
        etag=etag_of(
            SCHEMA, state.version, asked_tag, used_tag, variant, centre, spread, lang
        ),
    )
