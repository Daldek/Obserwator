"""Hydrological analyses (Nogat plan H1 to H18), by section of the station panel.

Every number the plan gives Hydrolog comes from Hydrolog's catalog command through
`hydrolog_bridge.call`, the function behind the `hydrolog` CLI, so it equals
`hydrolog <command>` on the same series and options. What Hydrolog has not got yet is a
prototype of `_hydro_proto`, reported as `hydrolog_bridge.prototype(method, target)`.

Sections and their analyses:

- „Stany charakterystyczne”: `hydro_characteristic` (H1, H2), `hydro_levels` (H3)
- „Krzywa natężenia przepływu”: `hydro_rating_curve`, `hydro_rating_periods` (H4)
- „Przepływy maksymalne i minimalne”: `hydro_flood_frequency` (H5, H16), `hydro_low_flow` (H6)
- „Niżówki”: `hydro_low_flow_periods` (H7)
- „Czas trwania i strefy”: `hydro_duration` (H8, H9)
- „Reżim i sezonowość”: `hydro_regime` (H10 to H12), `hydro_seasonality` (H13)
- „Temperatura wody”: `hydro_water_temperature` (H14, H15)
- „Trendy i bilans”: `hydro_trends` (H16), `hydro_runoff` (H17), `hydro_baseflow` (H18)

Year options `from` and `to` are hydrological years (XI–X, named by the year of their end).
"""

from __future__ import annotations

from typing import Any

import numpy as np
from server import hydrolog_bridge as bridge
from server.analyses import Analysis, BadParam, Context, NoData, Params
from server.analyses import _hydro_proto as proto

#: Return periods of the quantile tables: p = 50, 20, 10, 5, 2, 1, 0.5, 0.2, 0.1 %.
TABLE_PERIODS = (2.0, 5.0, 10.0, 20.0, 50.0, 100.0, 200.0, 500.0, 1000.0)
#: Exceedance probabilities [%] of the drawn distribution curves.
CURVE_PERCENTS = (99, 98, 95, 90, 80, 70, 60, 50, 40, 30, 20, 15, 10, 7, 5, 3, 2, 1.5, 1, 0.7, 0.5, 0.3, 0.2, 0.15, 0.1)
#: Hydrolog's keys of `stats characteristic`, in the order of the table rows and columns.
CHARACTERISTIC_KEYS = ("wwx", "swx", "zwx", "nwx", "wsx", "ssx", "zsx", "nsx", "wnx", "snx", "znx", "nnx")
DISTRIBUTIONS = ("all", "log_normal", "gev", "pearson3", "weibull")
FIT_METHODS = ("l_moments", "mle", "moments", "least_squares", "all")


# --- helpers ------------------------------------------------------------------------------


def _years(params: Params) -> tuple[int | None, int | None]:
    start = params.int("from", None, 1800, 2200)
    end = params.int("to", None, 1800, 2200)
    if start is not None and end is not None and start > end:
        raise BadParam("from: później niż to")
    return start, end


def _span(first: int, last: int, start: int, end: int) -> dict[str, int]:
    return {"first": first, "last": last, "from": start, "to": end}


def _valid(daily: proto.Daily, variable: str, first: int, last: int) -> tuple[list[float], list[str]]:
    """The days of hydrological years `first`–`last` with a value: Hydrolog's `values`, `dates`."""
    part = daily.block(first, last)
    values = daily.values[variable][part]
    keep = np.isfinite(values)
    return values[keep].tolist(), np.datetime_as_string(daily.dates[part][keep], unit="D").tolist()


def _daily_or_none(ctx: Context) -> proto.Daily | None:
    try:
        return proto.load_daily(ctx)
    except NoData:
        return None


def _provenance(*items: dict[str, Any]) -> list[dict[str, Any]]:
    """The provenance list: one entry per Hydrolog command (with the number of calls) or prototype."""
    out: list[dict[str, Any]] = []
    for item in items:
        if item["engine"] == "hydrolog":
            same = next((o for o in out if o["engine"] == "hydrolog" and o["command"] == item["command"]), None)
            if same is not None:
                same["calls"] = same.get("calls", 1) + 1
                continue
        elif any(o == item for o in out):
            continue
        out.append(dict(item))
    return out


def _version(*sources: Any) -> str:
    return " · ".join(source.label for source in sources if source is not None)


def _names(variable: str) -> dict[str, str]:
    """Hydrolog's wwx … nnx as the Polish names: WWQ … NNQ for Q, WWW … NNW for H."""
    suffix = "W" if variable == "H" else variable
    return {key: f"{key[0].upper()}{key[1].upper()}{suffix}" for key in CHARACTERISTIC_KEYS}


def _notices(*calls: dict[str, Any]) -> list[dict[str, Any]]:
    return [{"command": call["provenance"]["command"], **notice} for call in calls for notice in call["notices"]]


# --- „Stany charakterystyczne”: H1, H2 ----------------------------------------------------


def characteristic(ctx: Context, params: Params) -> dict[str, Any]:
    """First degree per year and half-year (H1), second degree over the chosen years (H2)."""
    source = params.choice("source", ("auto", "imgw", "daily"), "auto")
    start, end = _years(params)
    half = proto.load_half_years(ctx)
    daily = _daily_or_none(ctx)
    variables = [v for v in ("H", "Q", "T") if (daily is not None and daily.has(v)) or (half is not None and half.has(v))]
    if not variables:
        raise NoData("Stacja nie ma w magazynie szeregów H, Q ani T.")
    bounds = []
    for variable in variables:
        if daily is not None and daily.has(variable):
            bounds += list(daily.years(variable))
        if half is not None and half.has(variable):
            years = half.years[np.isfinite(half.get(f"{variable}_mean", "annual")) | np.isfinite(half.get(f"{variable}_max", "winter"))]
            if years.size:
                bounds += [int(years[0]), int(years[-1])]
    first, last = min(bounds), max(bounds)
    a, b = proto.year_range((first, last), start, end)

    computed: list[dict[str, Any]] = []
    first_degree: dict[str, list[dict[str, Any]]] = {}
    for variable in variables:
        from_daily = proto.first_degree_daily(daily, variable, a, b) if daily is not None and daily.has(variable) else []
        from_half = proto.first_degree_half_years(half, variable, a, b) if half is not None and half.has(variable) else []
        if source == "imgw":
            rows = from_half
        elif source == "daily":
            rows = from_daily
        else:
            published = {row["year"]: row for row in from_half}
            rows = sorted([*from_half, *(row for row in from_daily if row["year"] not in published)], key=lambda r: r["year"])
        first_degree[variable] = rows
    if any(row["source"] == "imgw" for rows in first_degree.values() for row in rows):
        computed.append(bridge.prototype("Wartości I stopnia: minimum, średnia i maksimum półroczy XI–IV i V–X oraz roku hydrologicznego, opublikowane przez IMGW-PIB (maksimum roczne = większe z półrocznych)", "H1"))
    if any(row["source"] == "daily" for rows in first_degree.values() for row in rows):
        computed.append(bridge.prototype("Wartości I stopnia z szeregu dobowego: minimum, średnia i maksimum dni z wartością w półroczach XI–IV, V–X i w roku hydrologicznym", "H1"))

    second: dict[str, Any] = {}
    calls = []
    for variable in ("H", "Q"):
        if daily is None or not daily.has(variable):
            continue
        da, db = proto.year_range(daily.years(variable), a, b) if daily.years(variable)[0] <= b and daily.years(variable)[1] >= a else (None, None)
        if da is None:
            continue
        values, dates = _valid(daily, variable, da, db)
        call = bridge.call("stats characteristic", {"values": values, "dates": dates, "parameter": variable})
        calls.append(call)
        names = _names(variable)
        complete_set = set(daily.complete_years(variable, da, db))
        entry: dict[str, Any] = {
            "names": [names[key] for key in CHARACTERISTIC_KEYS],
            "hydrolog": {names[key]: call["result"][key] for key in CHARACTERISTIC_KEYS},
            "period_years": call["result"]["period_years"],
            "from": da,
            "to": db,
            "incomplete": [y for y in range(da, db + 1) if y not in complete_set and np.isfinite(daily.values[variable][daily.block(y, y)]).any()],
            "missing": [y for y in range(da, db + 1) if not np.isfinite(daily.values[variable][daily.block(y, y)]).any()],
            "imgw": None,
        }
        if half is not None and half.has(variable):
            rows = half.rows(a, b)
            high, _ = half.annual(variable, "max")
            low, _ = half.annual(variable, "min")
            mean, _ = half.annual(variable, "mean")
            values_half = proto.second_degree(high[rows], mean[rows], low[rows])
            years_used = half.years[rows & np.isfinite(high) & np.isfinite(low)]
            if years_used.size:
                entry["imgw"] = {names[key]: values_half[key] for key in CHARACTERISTIC_KEYS}
                entry["imgw_years"] = int(years_used.size)
                entry["imgw_from"] = int(years_used[0])
                entry["imgw_to"] = int(years_used[-1])
        second[variable] = entry
    if any(entry["imgw"] for entry in second.values()):
        computed.append(bridge.prototype("Wartości II stopnia z półroczy IMGW-PIB (do porównania): największa, średnia, mediana i najmniejsza z rocznych maksimów, średnich i minimów", "H2"))
    units = {v: (daily.units.get(v) if daily is not None and v in daily.units else {"H": "cm", "Q": "m3/s", "T": "degC"}[v]) for v in variables}
    return {
        "series_version": _version(daily, half),
        "computed_by": _provenance(*(call["provenance"] for call in calls), *computed),
        "years": _span(first, last, a, b),
        "source": source,
        "variables": variables,
        "units": units,
        "provider": ctx.station.get("provider"),
        "first_degree": first_degree,
        "second_degree": second,
        "notices": _notices(*calls),
    }


# --- „Stany charakterystyczne”: H3 --------------------------------------------------------

CHMI_LEVELS = (
    ("spa1", "SPA 1 · stan czuwania (bdělost)", True),
    ("spa2", "SPA 2 · stan gotowości (pohotovost)", True),
    ("spa3", "SPA 3 · stan zagrożenia (ohrožení)", True),
    ("q50", "Q50 · woda 50-letnia", True),
    ("drought", "Sucho · próg suszy ČHMÚ", False),
)


def levels(ctx: Context, params: Params) -> dict[str, Any]:
    """Warning levels and the characteristic ones on the daily H (Q) chart, days and events beyond them (H3)."""
    daily = proto.load_daily(ctx)
    default = "H" if daily.has("H") else "Q"
    variable = params.choice("var", ("H", "Q"), default)
    if not daily.has(variable):
        raise NoData(f"Szereg dobowy nie ma {variable} ({proto.VARIABLE_NAMES[variable]}).")
    first, last = daily.years(variable)
    a, b = proto.year_range((first, last), *_years(params))
    computed: list[dict[str, Any]] = []
    found: list[dict[str, Any]] = []
    thresholds = (ctx.station.get("thresholds") or {}).get(variable) or {}
    for key, label, above in CHMI_LEVELS:
        value = thresholds.get(key)
        if value is not None:
            found.append({"id": key, "label": label, "short": label.split(" · ")[0], "value": float(value), "above": above, "source": "ČHMÚ"})
    values, dates = _valid(daily, variable, a, b)
    call = bridge.call("stats characteristic", {"values": values, "dates": dates, "parameter": variable})
    names = _names(variable)
    for key, above in (("swx", True), ("ssx", True), ("snx", False)):
        found.append({"id": key, "label": f"{names[key]} ({a}–{b})", "short": names[key], "value": float(call["result"][key]), "above": above, "source": "Hydrolog"})
    block = daily.block(a, b)
    per_year = {level["id"]: proto.days_beyond_per_year(daily, variable, level["value"], level["above"], a, b) for level in found}
    events = {level["id"]: proto.events_beyond(daily, variable, level["value"], level["above"], a, b) for level in found}
    computed.append(bridge.prototype("Dni w roku hydrologicznym z wartością dobową na poziomie lub powyżej (poniżej) progu i ciągi takich dni (początek, koniec, kulminacja); brak danych przerywa ciąg", "H3"))
    return {
        "series_version": daily.label,
        "computed_by": _provenance(call["provenance"], *computed),
        "years": _span(first, last, a, b),
        "var": variable,
        "unit": daily.units.get(variable),
        "provider": ctx.station.get("provider"),
        "levels": found,
        "imgw_levels": ctx.station.get("provider") == "IMGW-PIB",
        "line": proto.chart_line(daily.dates[block], daily.values[variable][block]),
        "year_list": list(range(a, b + 1)),
        "per_year": per_year,
        "events": events,
        "notices": _notices(call),
    }


# --- „Krzywa natężenia przepływu”: H4 -------------------------------------------------------


def _rating(fit: dict[str, Any], levels_cm: np.ndarray) -> dict[str, Any]:
    result = fit["result"]
    low = max(float(levels_cm.min()), result["h0"] + 0.5)
    grid = np.linspace(low, float(levels_cm.max()), 80)
    flows = result["a"] * np.power(np.maximum(grid - result["h0"], 0.0), result["b"])
    return {
        "a": result["a"],
        "b": result["b"],
        "h0": result["h0"],
        "r_squared": result["r_squared"],
        "std_residuals": result["std_residuals"],
        "n_points": result["n_points"],
        "n_outliers_removed": result["n_outliers_removed"],
        "curve": [[float(q), float(h)] for q, h in zip(flows, grid, strict=True)],
        "notices": fit["notices"],
    }


def _flow_at(fit: dict[str, Any], level: float) -> float | None:
    if level <= fit["h0"]:
        return None
    return float(fit["a"] * (level - fit["h0"]) ** fit["b"])


def _level_at(fit: dict[str, Any], flow: float) -> float | None:
    if fit["a"] <= 0 or fit["b"] <= 0 or flow <= 0:
        return None
    return float(fit["h0"] + (flow / fit["a"]) ** (1 / fit["b"]))


def _pairs(ctx: Context) -> tuple[proto.Daily, np.ndarray, np.ndarray, np.ndarray, int, int]:
    """The daily series and its days with both H and Q, with the first and last year of them."""
    daily = proto.load_daily(ctx)
    if not (daily.has("H") and daily.has("Q")):
        missing = "Q" if daily.has("H") else "H"
        raise NoData(f"Krzywa natężenia przepływu potrzebuje par H i Q z tego samego dnia; szereg nie ma {missing}.")
    level, flow = daily.values["H"], daily.values["Q"]
    pairs = np.isfinite(level) & np.isfinite(flow)
    pair_years = daily.hy[pairs]
    return daily, level, flow, pairs, int(pair_years[0]), int(pair_years[-1])


def _thin(level: np.ndarray, flow: np.ndarray, bounds: tuple[float, float, float, float], cells: tuple[int, int] = (360, 240)) -> list[list[float]]:
    """The H–Q points of a chart, one per cell of a grid over the chart (`[[Q, H], …]`)."""
    q0, q1, h0, h1 = bounds
    column = np.round((flow - q0) / max(q1 - q0, 1e-9) * cells[0]).astype(int)
    row = np.round((level - h0) / max(h1 - h0, 1e-9) * cells[1]).astype(int)
    _, keep = np.unique(column * (cells[1] + 1) + row, return_index=True)
    keep.sort()
    return [[float(flow[i]), float(level[i])] for i in keep]


def rating_curve(ctx: Context, params: Params) -> dict[str, Any]:
    """Q = a·(H − H₀)^b of same-day H and Q over the chosen years (H4)."""
    daily, level, flow, pairs, first, last = _pairs(ctx)
    start, end = _years(params)
    a, b = proto.year_range((first, last), start if start is not None else max(first, last - 9), end)
    outliers = params.choice("outliers", ("0", "1"), "0") == "1"
    chosen = pairs & (daily.hy >= a) & (daily.hy <= b)
    if chosen.sum() < 3:
        raise NoData(f"W latach {a}–{b} są mniej niż 3 dni z H i Q.")
    options = {"water_levels": level[chosen].tolist(), "discharges": flow[chosen].tolist()}
    if outliers:
        options["remove_outliers"] = True
    fit = bridge.call("hydrometrics rating-curve", options)
    reference_level = float(np.median(level[pairs]))
    reference_flow = float(np.median(flow[pairs]))
    # Points of the chosen years, coloured by up to eight consecutive groups of years and
    # thinned to one per cell of a grid over the chart (all pairs go to Hydrolog).
    bounds = (float(flow[chosen].min()), float(flow[chosen].max()), float(level[chosen].min()), float(level[chosen].max()))
    groups = []
    years = b - a + 1
    count = min(8, years)
    for index in range(count):
        g0 = a + (years * index) // count
        g1 = a + (years * (index + 1)) // count - 1
        rows = chosen & (daily.hy >= g0) & (daily.hy <= g1)
        groups.append({"from": g0, "to": g1, "pairs": int(rows.sum()), "points": _thin(level[rows], flow[rows], bounds) if rows.any() else []})
    return {
        "series_version": daily.label,
        "computed_by": _provenance(fit["provenance"]),
        "years": _span(first, last, a, b),
        "outliers": outliers,
        "fit": _rating(fit, level[chosen]),
        "q_at": _flow_at(fit["result"], reference_level),
        "h_at": _level_at(fit["result"], reference_flow),
        "reference": {"level": reference_level, "flow": reference_flow},
        "groups": groups,
        "notices": _notices(fit),
    }


def rating_periods(ctx: Context, params: Params) -> dict[str, Any]:
    """The rating curves of successive periods of the whole record (H4: how the curve moved)."""
    daily, level, flow, pairs, first, last = _pairs(ctx)
    period = params.int("period", 10, 2, 30)
    outliers = params.choice("outliers", ("0", "1"), "0") == "1"
    reference_level = float(np.median(level[pairs]))
    reference_flow = float(np.median(flow[pairs]))
    periods = []
    calls = []
    p0 = first - ((first - 1) % period)
    while p0 <= last:
        p1 = p0 + period - 1
        rows = pairs & (daily.hy >= p0) & (daily.hy <= p1)
        entry: dict[str, Any] = {"from": max(p0, first), "to": min(p1, last), "n": int(rows.sum())}
        if rows.sum() >= 30:
            options = {"water_levels": level[rows].tolist(), "discharges": flow[rows].tolist()}
            if outliers:
                options["remove_outliers"] = True
            try:
                call = bridge.call("hydrometrics rating-curve", options)
                calls.append(call)
                entry["fit"] = _rating(call, level[rows])
                entry["q_at"] = _flow_at(call["result"], reference_level)
                entry["h_at"] = _level_at(call["result"], reference_flow)
            except bridge.HydrologFailed as exc:
                entry["error"] = exc.text
        else:
            entry["error"] = "mniej niż 30 par H–Q"
        periods.append(entry)
        p0 += period
    if not calls:
        raise NoData("Żaden okres nie ma 30 par H–Q.")
    return {
        "series_version": daily.label,
        "computed_by": _provenance(*(call["provenance"] for call in calls)),
        "years": _span(first, last, first, last),
        "period": period,
        "outliers": outliers,
        "reference": {"level": reference_level, "flow": reference_flow},
        "periods": periods,
        "notices": _notices(*calls),
    }


# --- „Przepływy maksymalne i minimalne”: H5, H6, H16 (homogeneity) ------------------------


def _periods() -> list[float]:
    return sorted(set(TABLE_PERIODS) | {round(100.0 / p, 10) for p in CURVE_PERCENTS})


def _quantile_at(fitted: dict[str, Any], period: float) -> float | None:
    for at, value in enumerate(fitted["return_periods"]):
        if abs(value - period) < 1e-9 * period:
            return fitted["quantiles"][at]
    return None


def _distribution(fitted: dict[str, Any]) -> dict[str, Any]:
    periods = fitted["return_periods"]
    curve = sorted(([100.0 / t, q] for t, q in zip(periods, fitted["quantiles"], strict=True)), key=lambda point: -point[0])
    return {
        "name": fitted["distribution_name"],
        "method": fitted["fit_method"],
        "parameters": fitted["parameters"],
        "aic": fitted.get("aic"),
        "ks_statistic": fitted.get("ks_statistic"),
        "ks_p_value": fitted.get("ks_p_value"),
        "ks_valid": fitted.get("ks_valid"),
        "ad_statistic": fitted.get("ad_statistic"),
        "ad_critical_values": fitted.get("ad_critical_values"),
        "quantiles": [_quantile_at(fitted, period) for period in TABLE_PERIODS],
        "curve": curve,
    }


def flood_frequency(ctx: Context, params: Params) -> dict[str, Any]:
    """`stats flood-frequency` of annual maxima of Q from IMGW-PIB's half-years or the daily series (H5) and `stats homogeneity` (H16)."""
    half = proto.load_half_years(ctx)
    daily = _daily_or_none(ctx)
    has_half = half is not None and half.has("Q")
    has_daily = daily is not None and daily.has("Q")
    if not (has_half or has_daily):
        raise NoData("Stacja nie ma przepływów Q: kwantyle przepływów maksymalnych liczy się z Q.")
    source = params.choice("source", ("semiannual", "daily"), "semiannual" if has_half else "daily")
    if source == "semiannual" and not has_half:
        raise NoData("IMGW-PIB nie publikuje półrocznych charakterystyk tej stacji; wybierz szereg dobowy.")
    if source == "daily" and not has_daily:
        raise NoData("Stacja nie ma szeregu dobowego Q; wybierz półrocza IMGW-PIB.")
    distribution = params.choice("distribution", DISTRIBUTIONS, "all")
    fit_method = params.choice("fit_method", FIT_METHODS, "l_moments")
    start, end = _years(params)
    maxima: list[dict[str, Any]] = []
    if source == "semiannual":
        values, dates = half.annual("Q", "max")  # type: ignore[union-attr]
        present = np.isfinite(values)
        years = half.years  # type: ignore[union-attr]
        first, last = int(years[present][0]), int(years[present][-1])
        a, b = proto.year_range((first, last), start, end)
        rows = present & (years >= a) & (years <= b)
        series = {"values": values[rows].tolist()}
        homogeneity_options = {"values": values[rows].tolist(), "years": years[rows].tolist()}
        maxima = [{"year": int(y), "value": float(v), "date": d} for y, v, d, keep in zip(years, values, dates, rows, strict=True) if keep]
        label = half.label  # type: ignore[union-attr]
    else:
        first, last = daily.years("Q")  # type: ignore[union-attr]
        a, b = proto.year_range((first, last), start, end)
        values_daily, dates_daily = _valid(daily, "Q", a, b)  # type: ignore[arg-type]
        series = {"values": values_daily, "dates": dates_daily}
        homogeneity_options = dict(series)
        label = daily.label  # type: ignore[union-attr]
    fit = bridge.call("stats flood-frequency", {**series, "distribution": distribution, "fit_method": fit_method, "return_periods": _periods()})
    homogeneity = bridge.call("stats homogeneity", homogeneity_options)
    result = fit["result"]
    if source == "daily":
        flows = daily.values["Q"]  # type: ignore[union-attr]
        for year, value in zip(result["hydrological_years"], result["annual_maxima"], strict=True):
            part = daily.block(year, year)  # type: ignore[union-attr]
            at = int(np.nanargmax(flows[part]))
            maxima.append({"year": int(year), "value": float(value), "date": proto.iso(daily.dates[part][at])})  # type: ignore[union-attr]
    empirical = result["empirical"]
    return {
        "series_version": label,
        "computed_by": _provenance(fit["provenance"], homogeneity["provenance"]),
        "years": _span(first, last, a, b),
        "source": source,
        "sources": [s for s, ok in (("semiannual", has_half), ("daily", has_daily)) if ok],
        "distribution": distribution,
        "fit_method": fit_method,
        "table_periods": list(TABLE_PERIODS),
        "n_years": result["n_years"],
        "best": result["best_distribution"],
        "maxima": maxima,
        "incomplete_years": result.get("incomplete_years"),
        "distributions": [_distribution(fitted) for fitted in result["distributions"]],
        "empirical": [[p * 100.0, v] for p, v in zip(empirical["exceedance_prob"], empirical["values_sorted"], strict=True)],
        "homogeneity": homogeneity["result"],
        "notices": _notices(fit, homogeneity),
    }


def low_flow(ctx: Context, params: Params) -> dict[str, Any]:
    """`stats low-flow`: the Fisher–Tippett distribution of annual minima of the daily Q (H6)."""
    daily = proto.load_daily(ctx, need="Q")
    first, last = daily.years("Q")
    a, b = proto.year_range((first, last), *_years(params))
    values, dates = _valid(daily, "Q", a, b)
    call = bridge.call("stats low-flow", {"values": values, "dates": dates, "return_periods": _periods()})
    result = call["result"]
    fitted = result["fisher_tippett"]
    empirical = result["empirical"]
    minima = []
    flows = daily.values["Q"]
    for year, value in zip(result["hydrological_years"], result["annual_minima"], strict=True):
        part = daily.block(year, year)
        at = int(np.nanargmin(flows[part]))
        minima.append({"year": int(year), "value": float(value), "date": proto.iso(daily.dates[part][at])})
    return {
        "series_version": daily.label,
        "computed_by": _provenance(call["provenance"]),
        "years": _span(first, last, a, b),
        "table_periods": list(TABLE_PERIODS),
        "n_years": result["n_years"],
        "minima": minima,
        "incomplete_years": result.get("incomplete_years"),
        "parameters": fitted["parameters"],
        "ks_statistic": fitted.get("ks_statistic"),
        "ks_p_value": fitted.get("ks_p_value"),
        "quantiles": [_quantile_at(fitted, period) for period in TABLE_PERIODS],
        "curve": sorted(([100.0 / t, q] for t, q in zip(fitted["return_periods"], fitted["quantiles"], strict=True)), key=lambda point: -point[0]),
        "empirical": [[p * 100.0, v] for p, v in zip(empirical["non_exceedance_probabilities"], empirical["values_ascending"], strict=True)],
        "notices": _notices(call),
    }


# --- „Niżówki”: H7 ---------------------------------------------------------------------------


def low_flow_periods(ctx: Context, params: Params) -> dict[str, Any]:
    """Low-flow periods by the threshold level method: Hydrolog per gap-free span, joined across gaps (H7)."""
    daily = proto.load_daily(ctx)
    variable = params.choice("var", ("Q", "H"), "Q" if daily.has("Q") else "H")
    if not daily.has(variable):
        raise NoData(f"Szereg dobowy nie ma {variable} ({proto.VARIABLE_NAMES[variable]}).")
    kind = params.choice("threshold", ("sn", "p70", "p90", "value"), "sn")
    min_duration = params.int("min", 5, 1, 90)
    max_gap = params.int("gap", 4, 0, 30)
    first, last = daily.years(variable)
    a, b = proto.year_range((first, last), *_years(params))
    part = daily.block(a, b)
    values = daily.values[variable][part]
    dates = daily.dates[part]
    computed: list[dict[str, Any]] = []
    calls = []
    unit = daily.units.get(variable)
    names = _names(variable)
    if kind == "sn":
        good, good_dates = _valid(daily, variable, a, b)
        call = bridge.call("stats characteristic", {"values": good, "dates": good_dates, "parameter": variable})
        calls.append(call)
        threshold = float(call["result"]["snx"])
        label = f"{names['snx']} {a}–{b}"
    elif kind in ("p70", "p90"):
        percent = 70 if kind == "p70" else 90
        threshold = float(proto.exceedance_values(values, (percent,))[0])
        label = f"{variable}{percent} (przekraczany przez {percent} % dni {a}–{b})"
        computed.append(bridge.prototype("Krzywa czasu trwania: wartość osiągana lub przekraczana przez p % dni (pozycja Weibulla m/(n+1))", "H8"))
    else:
        threshold = params.float("value", None, -1e6, 1e6)
        if threshold is None:
            raise BadParam("value: podaj próg")
        label = "próg podany"
    if not threshold > 0:
        raise NoData("Hydrolog przyjmuje tylko dodatni próg niżówki.")
    valid = np.isfinite(values)
    starts, ends = proto.runs(valid)
    events: list[dict[str, Any]] = []
    for s, e in zip(starts, ends, strict=True):
        segment = values[s : e + 1]
        if not (segment < threshold).any():
            continue
        call = bridge.call(
            "stats low-flow-sequences",
            {
                "values": segment.tolist(),
                "dates": np.datetime_as_string(dates[s : e + 1], unit="D").tolist(),
                "threshold": threshold,
                "min_duration_days": 1,
                "max_gap_days": max_gap,
            },
        )
        calls.append(call)
        for sequence in call["result"]["sequences"]:
            i0, i1 = int(s + sequence["start_index"]), int(s + sequence["end_index"])
            events.append(
                {
                    "start": i0,
                    "end": i1,
                    "values": sequence["duration_days"],
                    "deficit": sequence["deficit_volume"],
                    "min": sequence["min_flow"],
                    "mean": sequence["mean_flow"],
                    "open_start": bool(i0 == s and s > 0),
                    "open_end": bool(i1 == e and e < len(values) - 1),
                }
            )
    merged = proto.merge_low_flow_events(events, ~valid, max_gap, min_duration)
    computed.append(bridge.prototype("Łączenie ciągów z odcinków bez braków danych przez przerwy krótsze niż próg łączenia (brak danych liczy się jako przerwa), odrzucenie krótszych niż minimum, podsumowanie lat (metoda find_low_sequences autora, 2024)", "H7"))
    volume = variable == "Q"
    out_events = []
    years = daily.hy[part]
    for event in merged:
        start, end_ = int(event["start"]), int(event["end"])
        out_events.append(
            {
                "start": proto.iso(dates[start]),
                "end": proto.iso(dates[end_]),
                "year": int(years[start]),
                "days": event["days"],
                "missing": event["missing"],
                "deficit": event["deficit"],
                "volume": event["deficit"] * proto.DAY_SECONDS / 1e6 if volume else None,
                "min": event["min"],
                "mean": event["mean"],
                "open_start": event["open_start"],
                "open_end": event["open_end"],
            }
        )
    per_year = []
    for year in range(a, b + 1):
        mine = [e for e in out_events if e["year"] == year]
        part_year = daily.values[variable][daily.block(year, year)]
        if not np.isfinite(part_year).any():
            continue
        per_year.append(
            {
                "year": year,
                "n": len(mine),
                "days": sum(e["days"] for e in mine),
                "longest": max((e["days"] for e in mine), default=0),
                "deficit": sum(e["deficit"] for e in mine),
                "volume": sum(e["volume"] for e in mine) if volume else None,
                "missing": int(np.isnan(part_year).sum()),
            }
        )
    longest = max(out_events, key=lambda e: e["days"], default=None)
    largest = max(out_events, key=lambda e: e["deficit"], default=None)
    return {
        "series_version": daily.label,
        "computed_by": _provenance(*(call["provenance"] for call in calls), *computed),
        "years": _span(first, last, a, b),
        "var": variable,
        "unit": unit,
        "dataset": daily.dataset,
        "threshold": {"kind": kind, "value": threshold, "label": label},
        "min_duration": min_duration,
        "max_gap": max_gap,
        "events": out_events,
        "per_year": per_year,
        "longest": longest,
        "largest": largest,
        "spans": int(sum(1 for c in calls if c["provenance"]["command"] == "stats low-flow-sequences")),
        "missing_days": int((~valid).sum()),
    }


# --- „Czas trwania i strefy”: H8, H9 ---------------------------------------------------------


def duration(ctx: Context, params: Params) -> dict[str, Any]:
    """Duration curves of H and Q with the modal classes (H8), Rybczyński's zones by Hydrolog (H9)."""
    daily = proto.load_daily(ctx)
    variables = [v for v in ("H", "Q") if daily.has(v)]
    if not variables:
        raise NoData("Szereg dobowy nie ma H ani Q.")
    years = [y for v in variables for y in daily.years(v)]
    first, last = min(years), max(years)
    a, b = proto.year_range((first, last), *_years(params))
    month = params.int("month", 0, 0, 12)
    part = daily.block(a, b)
    in_month = np.ones(part.stop - part.start, dtype=bool)
    if month:
        in_month = daily.month[part] == proto.HYDRO_MONTHS[month - 1]
    out: dict[str, Any] = {}
    calls = []
    for variable in variables:
        values = daily.values[variable][part][in_month]
        good = proto.finite(values)
        if good.size < 10:
            continue
        entry: dict[str, Any] = {
            "unit": daily.units.get(variable),
            "n": int(good.size),
            "curve": [[float(p), float(v)] for p, v in zip(proto.CURVE_PERCENTS, proto.exceedance_values(good, proto.CURVE_PERCENTS), strict=True)],
            "table": [[p, float(v)] for p, v in zip(proto.TABLE_PERCENTS, proto.exceedance_values(good, proto.TABLE_PERCENTS), strict=True)],
            "min": float(good.min()),
            "max": float(good.max()),
            "mean": float(good.mean()),
            "median": float(np.median(good)),
        }
        if variable == "H":
            call = bridge.call("hydrometrics water-level-zones", {"values": good.tolist(), "bin_width": 10.0})
            calls.append(call)
            result = call["result"]
            frequency = result["frequency"]
            counts = np.asarray(frequency["counts"])
            at = int(np.argmax(counts))
            entry["zones"] = result["zones"]
            entry["frequency"] = frequency
            entry["modal"] = {"from": frequency["bin_edges"][at], "to": frequency["bin_edges"][at + 1], "days": int(counts[at]), "percent": float(frequency["frequency_pct"][at])}
            if not month:
                entry["months"] = proto.class_month_table(daily.values["H"][part], daily.month[part], np.asarray(frequency["bin_edges"]))
        else:
            entry["classes"] = proto.log_classes(good)
            entry["modal"] = entry["classes"]["modal"]
        out[variable] = entry
    if not out:
        raise NoData(f"Za mało wartości w latach {a}–{b}.")
    computed = [bridge.prototype("Krzywa czasu trwania (przekroczenia) z pozycją Weibulla m/(n+1); klasa modalna Q na 40 klasach logarytmicznych; liczebności klas 10 cm w miesiącach hydrologicznych (metoda autora, 2024)", "H8")]
    return {
        "series_version": daily.label,
        "computed_by": _provenance(*(call["provenance"] for call in calls), *computed),
        "years": _span(first, last, a, b),
        "month": month,
        "variables": out,
        "notices": _notices(*calls),
    }


# --- „Reżim i sezonowość”: H10 to H13 ----------------------------------------------------------

_MONTH_DAYS = np.array([31, 28.25, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31])


def regime(ctx: Context, params: Params) -> dict[str, Any]:
    """`stats daily` (H10) and `stats monthly` (H11) of H, Q or T; Pardé's coefficients and the regime type (H12)."""
    daily = proto.load_daily(ctx)
    variable = params.choice("var", ("Q", "H", "T"), "Q" if daily.has("Q") else "H")
    if not daily.has(variable):
        raise NoData(f"Szereg dobowy nie ma {variable} ({proto.VARIABLE_NAMES[variable]}).")
    first, last = daily.years(variable)
    a, b = proto.year_range((first, last), *_years(params))
    values, dates = _valid(daily, variable, a, b)
    day_stats = bridge.call("stats daily", {"values": values, "dates": dates})
    month_stats = bridge.call("stats monthly", {"values": values, "dates": dates})
    computed: list[dict[str, Any]] = []
    out: dict[str, Any] = {
        "series_version": daily.label,
        "years": _span(first, last, a, b),
        "var": variable,
        "unit": daily.units.get(variable),
        "daily": day_stats["result"],
        "monthly": month_stats["result"],
        "complete_years": len(daily.complete_years(variable, a, b)),
        "notices": _notices(day_stats, month_stats),
    }
    if variable == "Q":
        means = month_stats["result"]["mean_values"]
        annual = float(np.mean(values))
        coefficients = proto.parde(means, annual)
        volumes = np.asarray(means) * _MONTH_DAYS
        out["parde"] = {"annual_mean": annual, "coefficients": coefficients}
        out["regime_type"] = proto.regime_type(coefficients)
        out["spring_share"] = float(volumes[2:4].sum() / volumes.sum())
        out["seasonality_index"] = proto.seasonality_index(list(volumes))
        computed.append(bridge.prototype("Współczynniki Pardégo (średni przepływ miesiąca / średni przepływ roczny) ze średnich miesięcznych Hydrologa; typ reżimu wg kryteriów Dynowskiej (1997) w odczycie roboczym; udział odpływu III–IV; wskaźnik sezonowości Walsha i Lawlera (1981)", "H12"))
    out["computed_by"] = _provenance(day_stats["provenance"], month_stats["provenance"], *computed)
    return out


def seasonality(ctx: Context, params: Params) -> dict[str, Any]:
    """Dates of annual maxima and minima: circular mean date, concentration, half-year shares (H13)."""
    half = proto.load_half_years(ctx)
    daily = _daily_or_none(ctx)
    has_q = (half is not None and half.has("Q")) or (daily is not None and daily.has("Q"))
    variable = params.choice("var", ("Q", "H"), "Q" if has_q else "H")
    has_half = half is not None and half.has(variable)
    has_daily = daily is not None and daily.has(variable)
    if not (has_half or has_daily):
        raise NoData(f"Stacja nie ma wartości {variable} ({proto.VARIABLE_NAMES[variable]}).")
    start, end = _years(params)
    out: dict[str, Any] = {"var": variable}
    extremes: dict[str, list[dict[str, Any]]] = {}
    if has_half:
        assert half is not None
        present = np.isfinite(half.annual(variable, "max")[0])
        first, last = int(half.years[present][0]), int(half.years[present][-1])
        a, b = proto.year_range((first, last), start, end)
        rows = half.rows(a, b)
        for stat in ("max", "min"):
            values, dates = half.annual(variable, stat)
            winter = half.get(f"{variable}_{stat}", "winter")
            summer = half.get(f"{variable}_{stat}", "summer")
            extremes[stat] = [
                {"year": int(y), "value": float(v), "date": d, "half": "winter" if (w >= s if stat == "max" else w <= s) else "summer"}
                for y, v, d, w, s, keep in zip(half.years, values, dates, winter, summer, rows, strict=True)
                if keep and np.isfinite(v) and d
            ]
        out["source"] = "imgw"
        label = half.label
    else:
        assert daily is not None
        first, last = daily.years(variable)
        a, b = proto.year_range((first, last), start, end)
        values = daily.values[variable]
        for stat in ("max", "min"):
            rows = []
            for year in daily.complete_years(variable, a, b):
                part = daily.block(year, year)
                at = int(np.argmax(values[part]) if stat == "max" else np.argmin(values[part]))
                day = daily.dates[part][at]
                rows.append({"year": year, "value": float(values[part][at]), "date": proto.iso(day), "half": "winter" if daily.doy[part][at] <= 181 + (1 if (year % 4 == 0 and year % 100 != 0) or year % 400 == 0 else 0) else "summer"})
            extremes[stat] = rows
        out["source"] = "daily"
        label = daily.label
    for stat, rows in extremes.items():
        circle = proto.circular_dates([row["date"] for row in rows])
        months = [0] * 12
        for row in rows:
            months[int(row["date"][5:7]) - 1] += 1
        out[stat] = {
            "rows": rows,
            "circular": circle,
            "months": months,
            "winter_share": (sum(1 for row in rows if row["half"] == "winter") / len(rows)) if rows else None,
        }
    out.update(
        {
            "series_version": label,
            "years": _span(first, last, a, b),
            "unit": "cm" if variable == "H" else "m3/s",
            "computed_by": [bridge.prototype("Statystyka kierunkowa dat ekstremów rocznych: średni termin i koncentracja r (Bayliss i Jones 1993; Burn 1997); udział maksimów półrocza zimowego i letniego", "H13")],
        }
    )
    return out


# --- „Temperatura wody”: H14, H15 -----------------------------------------------------------

ABOVE = (15.0, 20.0, 25.0)
BELOW = 1.0


def water_temperature(ctx: Context, params: Params) -> dict[str, Any]:
    """Harmonics of the annual cycle of water temperature per year and over the period (H14); days beyond thresholds (H15)."""
    daily = proto.load_daily(ctx, need="T")
    first, last = daily.years("T")
    a, b = proto.year_range((first, last), *_years(params))
    temperature = daily.values["T"]
    rows = []
    for year in range(a, b + 1):
        part = daily.block(year, year)
        values = temperature[part]
        count = int(np.isfinite(values).sum())
        if count == 0:
            continue
        row: dict[str, Any] = {"year": year, "days": count}
        good = np.flatnonzero(np.isfinite(values))
        at = good[np.argmax(values[good])]
        row["max"] = float(values[at])
        row["max_date"] = proto.iso(daily.dates[part][at])
        row["mean"] = float(np.nanmean(values)) if count >= 300 else None
        for level in ABOVE:
            row[f"above_{level:g}"] = int(proto.beyond(values, level, True).sum())
        row[f"below_{BELOW:g}"] = int(proto.beyond(values, BELOW, False).sum())
        fit = proto.harmonics(daily.doy[part] - 1, values) if count >= 300 else None
        if fit is not None:
            first_h, second_h = fit["harmonics"]
            row.update(
                {
                    "a0": fit["mean"],
                    "c1": first_h["amplitude"],
                    "day1": first_h["day_of_max"],
                    "date1": proto.hydro_day_label(first_h["day_of_max"]),
                    "c2": second_h["amplitude"],
                    "day2": second_h["day_of_max"],
                    "r2_1": first_h["explained"],
                    "r2_2": second_h["explained"],
                }
            )
        rows.append(row)
    part = daily.block(a, b)
    period_fit = proto.harmonics(daily.doy[part] - 1, temperature[part])
    if period_fit is None:
        raise NoData(f"Za mało pomiarów T w latach {a}–{b}.")
    days = np.arange(1, 367)
    sums = np.bincount(daily.doy[part][np.isfinite(temperature[part])], weights=temperature[part][np.isfinite(temperature[part])], minlength=367)
    counts = np.bincount(daily.doy[part][np.isfinite(temperature[part])], minlength=367)
    with np.errstate(invalid="ignore", divide="ignore"):
        mean_cycle = sums / counts
    fitted = proto.harmonic_curve(period_fit["coefficients"], days)
    first_fit = proto.harmonic_curve(period_fit["coefficients"][:3], days)
    for item in period_fit["harmonics"]:
        item["date"] = proto.hydro_day_label(item["day_of_max"])
    return {
        "series_version": daily.label,
        "computed_by": [
            bridge.prototype("Analiza harmoniczna cyklu rocznego (najmniejsze kwadraty, 2 harmoniki, P = 365,25 d): średnia, amplituda, termin maksimum, wariancja wyjaśniona", "H14"),
            bridge.prototype("Dni z temperaturą wody ≥ 15, 20, 25 °C i < 1 °C, maksimum roczne z datą", "H15"),
        ],
        "years": _span(first, last, a, b),
        "period": period_fit,
        "rows": rows,
        "above": list(ABOVE),
        "below": BELOW,
        "cycle": {
            "mean": [[int(d), float(v) if np.isfinite(v) else None] for d, v in zip(days, mean_cycle[1:], strict=True)],
            "fit": [[int(d), float(v)] for d, v in zip(days, fitted, strict=True)],
            "first": [[int(d), float(v)] for d, v in zip(days, first_fit, strict=True)],
        },
    }


# --- „Trendy i bilans”: H16, H17, H18 --------------------------------------------------------

TREND_SERIES = {
    "Q": (("max", "WQ"), ("mean", "SQ"), ("min", "NQ")),
    "H": (("max", "WW"), ("mean", "SW"), ("min", "NW")),
    "T": (("max", "maks. T"), ("mean", "śr. T"), ("min", "min. T")),
}


def trends(ctx: Context, params: Params) -> dict[str, Any]:
    """`stats mann-kendall` of annual maxima, means and minima with Sen's slope (H16)."""
    half = proto.load_half_years(ctx)
    daily = _daily_or_none(ctx)
    present = [v for v in ("Q", "H", "T") if (half is not None and half.has(v)) or (daily is not None and daily.has(v))]
    variable = params.choice("var", ("Q", "H", "T"), present[0] if present else "Q")
    has_half = half is not None and half.has(variable)
    has_daily = daily is not None and daily.has(variable)
    if not (has_half or has_daily):
        raise NoData(f"Stacja nie ma wartości {variable} ({proto.VARIABLE_NAMES[variable]}).")
    start, end = _years(params)
    annual: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    if has_half:
        assert half is not None
        for stat, _ in TREND_SERIES[variable]:
            values, _ = half.annual(variable, stat)
            annual[stat] = (half.years.astype(int), values)
        source, label = "imgw", half.label
    else:
        assert daily is not None
        first_d, last_d = daily.years(variable)
        years = np.array(daily.complete_years(variable, first_d, last_d), dtype=int)
        for stat, _ in TREND_SERIES[variable]:
            fn = {"max": np.max, "mean": np.mean, "min": np.min}[stat]
            annual[stat] = (years, np.array([fn(daily.values[variable][daily.block(int(y), int(y))]) for y in years], dtype=float))
        source, label = "daily", daily.label
    present = [y for stat in annual for y, v in zip(*annual[stat], strict=True) if np.isfinite(v)]
    if not present:
        raise NoData("Brak rocznych wartości do testu trendu.")
    first, last = min(present), max(present)
    a, b = proto.year_range((first, last), start, end)
    alpha = params.float("alpha", 0.05, 0.001, 0.2)
    calls = []
    series = []
    for stat, name in TREND_SERIES[variable]:
        years, values = annual[stat]
        keep = (years >= a) & (years <= b) & np.isfinite(values)
        entry: dict[str, Any] = {"stat": stat, "name": name, "points": [[int(y), float(v)] for y, v in zip(years[keep], values[keep], strict=True)]}
        if keep.sum() >= 3:
            call = bridge.call("stats mann-kendall", {"values": values[keep].tolist(), "alpha": alpha})
            calls.append(call)
            entry["mann_kendall"] = call["result"]
            entry["sen"] = proto.sen_slope(years[keep], values[keep])
        series.append(entry)
    return {
        "series_version": label,
        "computed_by": _provenance(*(call["provenance"] for call in calls), bridge.prototype("Nachylenie Sena (mediana nachyleń par lat) z wyrazem wolnym Conovera i 95 % przedziałem Gilberta (1987)", "H16")),
        "years": _span(first, last, a, b),
        "var": variable,
        "unit": {"Q": "m3/s", "H": "cm", "T": "degC"}[variable],
        "source": source,
        "alpha": alpha,
        "series": series,
        "notices": _notices(*calls),
    }


def runoff(ctx: Context, params: Params) -> dict[str, Any]:
    """Annual and monthly runoff volumes, the cumulative volume of a year against the mean (H17)."""
    daily = proto.load_daily(ctx, need="Q")
    first, last = daily.years("Q")
    a, b = proto.year_range((first, last), *_years(params))
    flows = daily.values["Q"]
    complete = set(daily.complete_years("Q", a, b))
    years = []
    cumulative = {}
    for year in range(a, b + 1):
        part = daily.block(year, year)
        values = flows[part]
        if not np.isfinite(values).any():
            continue
        months = []
        for month in proto.HYDRO_MONTHS:
            rows = daily.month[part] == month
            month_values = values[rows]
            missing = int(np.isnan(month_values).sum())
            months.append({"volume": float(np.nansum(month_values) * proto.DAY_SECONDS / 1e6) if missing < rows.sum() else None, "missing": missing})
        years.append({"year": year, "volume": float(np.nansum(values) * proto.DAY_SECONDS / 1e6), "missing": int(np.isnan(values).sum()), "complete": year in complete, "months": months})
        if year in complete:
            cumulative[year] = np.cumsum(values) * proto.DAY_SECONDS / 1e6
    if not years:
        raise NoData(f"Brak przepływów w latach {a}–{b}.")
    full = [row for row in years if row["complete"]]
    monthly_mean = [
        float(np.mean([row["months"][m]["volume"] for row in years if row["months"][m]["missing"] == 0 and row["months"][m]["volume"] is not None]))
        if any(row["months"][m]["missing"] == 0 and row["months"][m]["volume"] is not None for row in years)
        else None
        for m in range(12)
    ]
    chosen = params.int("year", max(complete) if complete else years[-1]["year"], a, b)
    part = daily.block(chosen, chosen)
    year_cumulative = np.nancumsum(flows[part]) * proto.DAY_SECONDS / 1e6
    mean_cumulative = None
    if cumulative:
        length = 365
        mean_cumulative = np.mean([curve[:length] for curve in cumulative.values()], axis=0)
    return {
        "series_version": daily.label,
        "computed_by": [bridge.prototype("Objętość odpływu V = Σ Q·86 400 s (mln m³) w latach i miesiącach hydrologicznych, krzywa sumowa roku na tle średniej z lat pełnych (pomysł autora, 95ec3ea, 2025)", "H17")],
        "years": _span(first, last, a, b),
        "rows": years,
        "mean_annual": float(np.mean([row["volume"] for row in full])) if full else None,
        "complete_years": len(full),
        "monthly_mean": monthly_mean,
        "year": chosen,
        "year_missing": int(np.isnan(flows[part]).sum()),
        "cumulative": [[int(d), float(v)] for d, v in zip(daily.doy[part], year_cumulative, strict=True)],
        "mean_cumulative": [[int(d) + 1, float(v)] for d, v in enumerate(mean_cumulative)] if mean_cumulative is not None else None,
    }


def baseflow(ctx: Context, params: Params) -> dict[str, Any]:
    """Baseflow by the Lyne–Hollick filter, the baseflow index per year and the recession constant (H18)."""
    daily = proto.load_daily(ctx, need="Q")
    first, last = daily.years("Q")
    a, b = proto.year_range((first, last), *_years(params))
    part = daily.block(a, b)
    flows = daily.values["Q"][part]
    base = np.full(flows.shape, np.nan)
    starts, ends = proto.runs(np.isfinite(flows))
    used = 0
    for s, e in zip(starts, ends, strict=True):
        if e - s + 1 < 60:
            continue
        base[s : e + 1] = proto.lyne_hollick(flows[s : e + 1])
        used += 1
    if used == 0:
        raise NoData(f"W latach {a}–{b} nie ma odcinka co najmniej 60 dni bez braków Q.")
    filtered = np.isfinite(base)
    years = daily.hy[part]
    rows = []
    for year in range(a, b + 1):
        rows_year = (years == year) & filtered
        if rows_year.sum() < 300:
            continue
        rows.append({"year": year, "bfi": float(base[rows_year].sum() / flows[rows_year].sum()), "days": int(rows_year.sum()), "base_mean": float(base[rows_year].mean()), "q_mean": float(flows[rows_year].mean())})
    recession = proto.recession_constant(flows)
    chosen = params.int("year", rows[-1]["year"] if rows else b, a, b)
    year_rows = years == chosen
    dates = daily.dates[part][year_rows]
    return {
        "series_version": daily.label,
        "computed_by": [bridge.prototype("Przepływ podziemny filtrem rekurencyjnym Lyne'a i Hollicka (α = 0,925, 3 przejścia, odbicie 30 dni; Nathan i McMahon 1990; Ladson i in. 2013), BFI = ΣQb/ΣQ, stała recesji k = mediana Q(t+1)/Q(t) w odcinkach opadania ≥ 5 dni (Tallaksen 1995)", "H18")],
        "years": _span(first, last, a, b),
        "bfi": float(base[filtered].sum() / flows[filtered].sum()),
        "days": int(filtered.sum()),
        "spans": used,
        "rows": rows,
        "recession": recession,
        "year": chosen,
        "flow": [[int(d), float(v) if np.isfinite(v) else None] for d, v in zip(proto.day_number(dates), flows[year_rows], strict=True)],
        "base": [[int(d), float(v) if np.isfinite(v) else None] for d, v in zip(proto.day_number(dates), base[year_rows], strict=True)],
        "alpha": proto.BASEFLOW_ALPHA,
    }


ANALYSES: dict[str, Analysis] = {
    "hydro_characteristic": Analysis(characteristic, "hydro", "Stany i przepływy charakterystyczne"),
    "hydro_levels": Analysis(levels, "hydro", "Stany ostrzegawcze, progi i dni powyżej"),
    "hydro_rating_curve": Analysis(rating_curve, "hydro", "Krzywa natężenia przepływu"),
    "hydro_rating_periods": Analysis(rating_periods, "hydro", "Krzywe natężenia przepływu kolejnych okresów"),
    "hydro_flood_frequency": Analysis(flood_frequency, "hydro", "Przepływy maksymalne o danym prawdopodobieństwie"),
    "hydro_low_flow": Analysis(low_flow, "hydro", "Przepływy minimalne o danym prawdopodobieństwie"),
    "hydro_low_flow_periods": Analysis(low_flow_periods, "hydro", "Niżówki"),
    "hydro_duration": Analysis(duration, "hydro", "Czas trwania i strefy stanów"),
    "hydro_regime": Analysis(regime, "hydro", "Reżim: statystyki dobowe i miesięczne, współczynniki Pardégo"),
    "hydro_seasonality": Analysis(seasonality, "hydro", "Sezonowość ekstremów"),
    "hydro_water_temperature": Analysis(water_temperature, "hydro", "Temperatura wody"),
    "hydro_trends": Analysis(trends, "hydro", "Trendy roczne"),
    "hydro_runoff": Analysis(runoff, "hydro", "Objętości odpływu"),
    "hydro_baseflow": Analysis(baseflow, "hydro", "Przepływ podziemny"),
}
