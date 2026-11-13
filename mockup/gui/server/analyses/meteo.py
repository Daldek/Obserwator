"""Meteorological analyses (Nogat plan M1 to M14, the warming stripes M15) of a station's daily series.

The daily datasets: IMGW-PIB `pl.imgw.meteo_climate_daily` (P, Tmax, Tmin, Tmean,
snow_cover), `pl.imgw.meteo_precip_daily` (P, snow_cover, fresh_snow) and ČHMÚ
`cz.chmi.meteo_daily` (P, Tmean, Tmax, Tmin). The quantiles of precipitation maxima and the
Mann–Kendall test are Hydrolog's catalog commands (`stats flood-frequency`,
`stats mann-kendall`), run as the CLI runs them; everything else is a prototype of
`_meteo_proto.py` labelled with the plan step that moves it to Hydrolog. Missing data follow
WMO-No. 1203 (see `_meteo_proto`). PMAXTP of the station's point comes from IMGW-PIB through
`obserwator.fetch_pmaxtp`, cached, not stored.
"""

from __future__ import annotations

import math
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any

import numpy as np
from server import attribution, hydrolog_bridge
from server.analyses import Analysis, BadParam, Context, NoData, Params
from server.analyses import _meteo_proto as proto
from server.store import iso

import obserwator

CLIMATE = "pl.imgw.meteo_climate_daily"
PRECIP = "pl.imgw.meteo_precip_daily"
CHMI = "cz.chmi.meteo_daily"
#: Datasets of each kind of data, preferred first when a station is in several.
P_SOURCES = (CLIMATE, CHMI, PRECIP)
T_SOURCES = (CLIMATE, CHMI)
SNOW_SOURCES = (CLIMATE, PRECIP)

YEAR_TYPES = ("calendar", "hydrological")
DURATIONS = (1, 2, 3, 5, 10)
DAY_THRESHOLDS = (0.1, 1.0, 10.0, 20.0)
#: Return periods of the quantile table and the dense list the probability plot draws.
TABLE_PERIODS = (2, 5, 10, 20, 50, 100, 200, 500, 1000)
RETURN_PERIODS = (1.01, 1.05, 1.11, 1.25, 1.43, 1.67, 2, 2.5, 3.33, 5, 10, 20, 50, 100, 200, 500, 1000)
MIN_QUANTILE_YEARS = 10
MIN_TREND_YEARS = 10
#: PMAXTP durations [min] beside the maxima of 1, 2 and 3 days.
PMAXTP_DURATION = {1: 1440, 2: 2880, 3: 4320}
SPI_SCALES = (1, 3, 6, 12)
SIELIANINOV_MONTHS = (4, 5, 6, 7, 8, 9)
SNOW_MONTHS = (10, 11, 12, 1, 2, 3, 4, 5)


# --- the station's prepared series -------------------------------------------------------


@dataclass(frozen=True)
class Prepared:
    """One dataset of a station on a whole-year daily axis, cleaned once."""

    dataset: str
    version: str
    axis: proto.Axis
    first: np.datetime64
    last: np.datetime64
    values: dict[str, np.ndarray]  # NaN where missing; multi-day P totals left out
    p_sum: np.ndarray | None  # P for sums: multi-day totals standing for their days
    p_sum_lost: np.ndarray | None  # (years, 12) months whose sum the totals leave missing


_PREPARED: OrderedDict[tuple[str, str, str], Prepared] = OrderedDict()
_PREPARED_LOCK = threading.Lock()


def _prepared(ctx: Context, dataset: str) -> Prepared:
    version = ctx.store.versions[dataset].name
    key = (dataset, ctx.code, version)
    with _PREPARED_LOCK:
        hit = _PREPARED.get(key)
        if hit is not None:
            _PREPARED.move_to_end(key)
            return hit
    series = ctx.store.series(dataset, ctx.code)
    if len(series.dates) == 0:
        raise NoData("Szereg stacji jest pusty.")
    axis = proto.Axis.spanning(series.dates[0], series.dates[-1])
    values: dict[str, np.ndarray] = {}
    for name, raw in series.values.items():
        clean = np.where(series.flags[name] == "accumulated", np.nan, raw).astype(float)
        values[name] = axis.place(series.dates, clean)
    p_sum = lost = None
    if "P" in values:
        flags = axis.place(series.dates, series.flags["P"], fill="missing")
        raw = axis.place(series.dates, series.values["P"])
        p_sum, lost = proto.precipitation_for_sums(values["P"], flags, raw, axis)
    prepared = Prepared(dataset, series.version, axis, series.dates[0], series.dates[-1], values, p_sum, lost)
    with _PREPARED_LOCK:
        _PREPARED[key] = prepared
        while len(_PREPARED) > 24:
            _PREPARED.popitem(last=False)
    return prepared


def _choose(ctx: Context, params: Params, variables: tuple[str, ...], sources: tuple[str, ...], missing: str) -> str:
    """The dataset of the station holding all `variables`: the one asked for, else the fullest."""
    options = [
        entry
        for entry in ctx.datasets
        if entry["dataset"] in sources and all(v in entry["variables"] for v in variables)
    ]
    if not options:
        raise NoData(missing)
    wanted = params.get("dataset")
    if wanted:
        for entry in options:
            if entry["dataset"] == wanted:
                return wanted
        raise BadParam(f"dataset: one of {', '.join(e['dataset'] for e in options)}")
    best = max(options, key=lambda e: (e["variables"][variables[0]]["with_value"], -sources.index(e["dataset"])))
    return best["dataset"]


def _options(ctx: Context, variables: tuple[str, ...], sources: tuple[str, ...]) -> list[str]:
    return [e["dataset"] for e in ctx.datasets if e["dataset"] in sources and all(v in e["variables"] for v in variables)]


def _year_type(params: Params) -> str:
    return params.choice("year", YEAR_TYPES, "calendar")


def _reference(params: Params, years: np.ndarray) -> dict[str, Any]:
    """The reference period: the one asked for, else the whole record (plan question 5).

    `years` are the years with a value; `min` and `max` bound the years a person may
    choose. A chosen period is clamped to them, so one range serves the analyses of a card
    whose records end in different years. The normal still needs values in 80 % of the
    period's years (WMO-No. 1203, 4.4.2); the GUI recommends at least 30 years.
    """
    first, last = int(years.min()), int(years.max())
    lo = params.int("ref_from", None, 1800, 2200)
    hi = params.int("ref_to", None, 1800, 2200)
    default = lo is None and hi is None
    lo = first if lo is None else min(max(lo, first), last)
    hi = last if hi is None else min(max(hi, first), last)
    if lo > hi:
        raise BadParam("ref_from: after ref_to")
    return {"from": lo, "to": hi, "default": default, "min": first, "max": last}


def _span(st: Prepared, variable: str) -> tuple[np.datetime64, np.datetime64]:
    """The first and last day with a value of a variable (P counts its multi-day totals)."""
    values = st.p_sum if variable == "P" and st.p_sum is not None else st.values.get(variable)
    found = np.flatnonzero(np.isfinite(values)) if values is not None else np.zeros(0, dtype=int)
    if len(found) == 0:
        return st.first, st.last
    return st.axis.dates[found[0]], st.axis.dates[found[-1]]


def _base(st: Prepared, ctx: Context, sources: tuple[str, ...], variables: tuple[str, ...], computed_by: list[dict]) -> dict[str, Any]:
    first, last = _span(st, variables[0])
    return {
        "series_version": st.version,
        "dataset": st.dataset,
        "datasets": _options(ctx, variables, sources),
        "record": {"first": iso(first), "last": iso(last), "variable": variables[0]},
        "computed_by": computed_by,
    }


def _r(value: float, digits: int = 1) -> float | None:
    """A rounded number or None (missing)."""
    if value is None or not math.isfinite(value):
        return None
    return round(float(value), digits)


def _date(st: Prepared, index: int) -> str | None:
    return None if index < 0 else str(st.axis.dates[index])


def _trim(years: np.ndarray, valid: np.ndarray) -> slice:
    """The rows from the first to the last year with a value."""
    where = np.flatnonzero(valid)
    if len(where) == 0:
        return slice(0, 0)
    return slice(int(where[0]), int(where[-1]) + 1)


# --- shared computations ---------------------------------------------------------------------


def _month_sums(st: Prepared) -> np.ndarray:
    """Monthly precipitation sums (calendar years, 12), NaN where a day is missing."""
    quality = proto.month_quality(st.axis, np.isfinite(st.p_sum))
    sums = st.axis.per_month(np.nan_to_num(st.p_sum))
    return np.where(quality.complete & ~st.p_sum_lost, np.round(sums, 1), np.nan)


def _month_counts(axis: proto.Axis, values: np.ndarray, event: np.ndarray) -> np.ndarray:
    """Days with `event` per month, scaled to the month's length (WMO-No. 1203, 4.4.1 d)."""
    known = np.isfinite(values)
    quality = proto.month_quality(axis, known)
    count = axis.per_month((event & known).astype(float))
    with np.errstate(invalid="ignore", divide="ignore"):
        scaled = count / quality.known * quality.days
    return np.where(quality.enough, scaled, np.nan)


def _month_means(axis: proto.Axis, values: np.ndarray) -> np.ndarray:
    """Monthly means where the month has enough days (WMO-No. 1203, 4.4.1 a)."""
    known = np.isfinite(values)
    quality = proto.month_quality(axis, known)
    total = axis.per_month(np.where(known, values, 0.0))
    with np.errstate(invalid="ignore", divide="ignore"):
        mean = total / quality.known
    return np.where(quality.enough, mean, np.nan)


def _month_totals_complete(axis: proto.Axis, values: np.ndarray) -> np.ndarray:
    """Monthly sums of a daily quantity where every day of the month is known."""
    known = np.isfinite(values)
    quality = proto.month_quality(axis, known)
    return np.where(quality.complete, axis.per_month(np.where(known, values, 0.0)), np.nan)


def _complete_years(st: Prepared, values: np.ndarray, year_type: str) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Labels, starts, lengths and completeness (every day known) of the years on the axis."""
    labels, starts, lengths = st.axis.year_blocks(year_type)
    known = np.add.reduceat(np.isfinite(values).astype(int), starts)
    return labels, starts, lengths, (known == lengths) & (lengths >= 365)


def _annual_maxima(st: Prepared, n: int, year_type: str) -> dict[str, np.ndarray]:
    """The largest n-day precipitation of each complete year and its last day."""
    p = st.values["P"]
    labels, starts, lengths, complete = _complete_years(st, p, year_type)
    best, index = proto.block_extreme(proto.rolling_sum(p, n), starts)
    chosen = complete & np.isfinite(best)
    dates = st.axis.dates
    first, last = _span(st, "P")
    in_record = (dates[starts + lengths - 1] >= first) & (dates[starts] <= last)
    return {
        "years": labels[chosen],
        "values": best[chosen],
        "end": index[chosen],
        "incomplete": labels[in_record & ~chosen],
    }


def _annual_sums(st: Prepared, year_type: str) -> tuple[np.ndarray, np.ndarray, np.ndarray, list[int]]:
    """Years, annual sums, the (years, 12) monthly table and its month order."""
    years, table, order = proto.by_year_type(_month_sums(st), st.axis.y0, year_type)
    return years, np.round(table.sum(axis=1), 1), table, order


def _spell_lengths(st: Prepared, threshold: float, dry: bool) -> tuple[proto.Runs, np.ndarray, np.ndarray]:
    """Spells of the daily P and, per calendar year, whether every day is known."""
    p = st.values["P"]
    known = np.isfinite(p)
    condition = (p < threshold) if dry else (p >= threshold)
    found = proto.runs(condition & known, known)
    labels, _, _, complete = _complete_years(st, p, "calendar")
    return found, labels, complete


def _longest_per_year(st: Prepared, found: proto.Runs, labels: np.ndarray, complete: np.ndarray) -> dict[int, tuple[int, int]]:
    """The longest spell starting in each complete calendar year: (length, start index)."""
    out: dict[int, tuple[int, int]] = {int(y): (0, -1) for y, ok in zip(labels, complete, strict=True) if ok}
    for start, length in zip(found.start, found.length, strict=True):
        year = int(st.axis.year[start])
        if year in out and length > out[year][0]:
            out[year] = (int(length), int(start))
    return out


def _proto(method: str, target: str, part: str | None = None) -> dict[str, Any]:
    """
    A prototype's provenance, tagged with the part of the result it computed.

    A section showing one part of a result lists only that part's provenance.
    """
    found = hydrolog_bridge.prototype(method, target)
    return dict(found, part=part) if part else found


# --- M1, M4, M9: sums, normals, anomalies, regime -------------------------------------------------


def precip_sums(ctx: Context, params: Params) -> dict[str, Any]:
    """M1, M4, M9: sums of months, half-years, seasons and years, the normal, % of it, the regime."""
    year_type = _year_type(params)
    dataset = _choose(ctx, params, ("P",), P_SOURCES, "Stacja nie ma pomiarów opadu.")
    st = _prepared(ctx, dataset)
    years, annual, table, order = _annual_sums(st, year_type)
    valid = np.isfinite(annual)
    if not valid.any():
        raise NoData("Żaden rok nie ma pełnych sum miesięcznych opadu.")
    ref = _reference(params, years[valid])
    lo, hi = ref["from"], ref["to"]
    normal_year, ref_years = proto.normal(annual, years, lo, hi)
    normal_months = [proto.normal(table[:, k], years, lo, hi) for k in range(12)]
    month_normals = np.array([m for m, _ in normal_months])
    ref["years"] = ref_years

    rows = _trim(years, np.isfinite(table).any(axis=1))
    with np.errstate(invalid="ignore", divide="ignore"):
        pct_year = 100 * annual / normal_year
        pct_months = 100 * table / month_normals

    calendar_grid = _month_sums(st)
    y0 = st.axis.y0
    cal_years = np.arange(y0, y0 + calendar_grid.shape[0])
    prev_dec = np.r_[np.nan, calendar_grid[:-1, 11]]
    seasons = {
        "DJF": prev_dec + calendar_grid[:, 0] + calendar_grid[:, 1],
        "MAM": calendar_grid[:, 2:5].sum(axis=1),
        "JJA": calendar_grid[:, 5:8].sum(axis=1),
        "SON": calendar_grid[:, 8:11].sum(axis=1),
    }
    hyd_years, hyd_table, _ = proto.by_year_type(calendar_grid, y0, "hydrological")
    halves = {"winter": hyd_table[:, :6].sum(axis=1), "summer": hyd_table[:, 6:].sum(axis=1)}
    season_rows = _trim(cal_years, np.isfinite(np.c_[tuple(seasons.values())]).any(axis=1))
    half_rows = _trim(hyd_years, np.isfinite(np.c_[tuple(halves.values())]).any(axis=1))

    values = annual[valid]
    best = int(np.argmax(values))
    worst = int(np.argmin(values))
    month_stats = []
    for k, month in enumerate(order):
        column = table[:, k]
        have = np.isfinite(column)
        if not have.any():
            month_stats.append({"month": month, "normal": None, "mean": None, "min": None, "max": None, "share": None})
            continue
        i_max = int(np.nanargmax(column))
        i_min = int(np.nanargmin(column))
        month_stats.append(
            {
                "month": month,
                "normal": _r(month_normals[k]),
                "mean": _r(np.nanmean(column)),
                "min": _r(column[i_min]),
                "min_year": int(years[i_min]),
                "max": _r(column[i_max]),
                "max_year": int(years[i_max]),
                "years": int(have.sum()),
            }
        )
    total_normal = float(np.sum(month_normals)) if np.isfinite(month_normals).all() else math.nan
    for item, value in zip(month_stats, month_normals, strict=True):
        item["share"] = _r(100 * value / total_normal) if math.isfinite(total_normal) else None

    # M9: the regime of the reference normal, in calendar order, and per-year indices
    calendar_normals = np.array([month_normals[order.index(m)] for m in range(1, 13)])
    regime: dict[str, Any] | None = None
    if np.isfinite(calendar_normals).all():
        concentration, mean_month = proto.markham(calendar_normals)
        pci = proto.pci(calendar_normals)
        si = proto.seasonality_index(calendar_normals)
        per_year = []
        for year, row in zip(years[valid], table[valid], strict=True):
            per_year.append({"year": int(year), "pci": _r(proto.pci(row), 2), "si": _r(proto.seasonality_index(row), 3)})
        pci_mean = float(np.mean([p["pci"] for p in per_year])) if per_year else math.nan
        si_mean = float(np.mean([p["si"] for p in per_year])) if per_year else math.nan
        regime = {
            "share": [_r(100 * v / total_normal) for v in calendar_normals],
            "coefficient": [_r(v / (total_normal / 12), 2) for v in calendar_normals],
            "pci": _r(pci, 2),
            "pci_class": proto.pci_class(pci),
            "si": _r(si, 3),
            "si_class": proto.si_class(si),
            "pci_years_mean": _r(pci_mean, 2),
            "pci_years_class": proto.pci_class(pci_mean),
            "si_years_mean": _r(si_mean, 3),
            "si_years_class": proto.si_class(si_mean),
            "markham": {"concentration": _r(concentration, 3), "month": _r(mean_month, 2)},
            "years": per_year,
            "pci_classes": list(proto.PCI_CLASSES),
            "si_classes": list(proto.SI_CLASSES),
        }

    notes = []
    if not math.isfinite(normal_year):
        notes.append(
            f"W latach {lo}–{hi} pełne sumy roczne ma tylko {ref_years} lat; normalna wymaga 80 % lat okresu (WMO-No. 1203)."
        )
    computed_by = [
        _proto("Sumy miesięczne, półroczne, sezonowe i roczne opadu; normalna okresu odniesienia i opad w % normalnej; braki wg WMO-No. 1203, 4.4", "M1", "sums"),
        _proto("Średnia roczna suma opadu z lat pełnych", "M4", "sums"),
        _proto("Reżim miesięczny, PCI (Oliver 1980), SI (Walsh i Lawler 1981), wektor Markhama (1970)", "M9", "regime"),
    ]
    out = _base(st, ctx, P_SOURCES, ("P",), computed_by)
    out.update(
        {
            "year_type": year_type,
            "months": order,
            "years": {"first": int(years[valid][0]), "last": int(years[valid][-1]), "complete": int(valid.sum())},
            "reference": ref,
            "normal": {
                "annual": _r(normal_year),
                "months": [_r(v) for v in month_normals],
                "halfyears": {k: _r(proto.normal(v, hyd_years, lo, hi)[0]) for k, v in halves.items()},
                "seasons": {k: _r(proto.normal(v, cal_years, lo, hi)[0]) for k, v in seasons.items()},
            },
            "stats": {
                "mean": _r(values.mean()),
                "std": _r(values.std(ddof=1) if len(values) > 1 else math.nan),
                "cv": _r(values.std(ddof=1) / values.mean() if len(values) > 1 and values.mean() > 0 else math.nan, 3),
                "min": _r(values[worst]),
                "min_year": int(years[valid][worst]),
                "max": _r(values[best]),
                "max_year": int(years[valid][best]),
                "n": int(valid.sum()),
            },
            "annual": [
                {"year": int(y), "sum": _r(s), "pct": _r(p, 0)}
                for y, s, p in zip(years[rows], annual[rows], pct_year[rows], strict=True)
            ],
            "monthly": [
                {"year": int(y), "sums": [_r(v) for v in row], "pct": [_r(v, 0) for v in prow]}
                for y, row, prow in zip(years[rows], table[rows], pct_months[rows], strict=True)
            ],
            "month_stats": month_stats,
            "halfyears": [
                {"year": int(y), "winter": _r(w), "summer": _r(s)}
                for y, w, s in zip(hyd_years[half_rows], halves["winter"][half_rows], halves["summer"][half_rows], strict=True)
            ],
            "seasons": [
                {"year": int(cal_years[i]), **{k: _r(v[i]) for k, v in seasons.items()}}
                for i in range(season_rows.start, season_rows.stop)
            ],
            "regime": regime,
            "notes": notes,
        }
    )
    return out


# --- M4, M5, M7: days with precipitation, intensity, heavy precipitation ---------------------------


def precip_days(ctx: Context, params: Params) -> dict[str, Any]:
    """M4, M5, M7: days with at least 0.1, 1, 10, 20 mm, wet-day intensity, heavy precipitation."""
    year_type = _year_type(params)
    dataset = _choose(ctx, params, ("P",), P_SOURCES, "Stacja nie ma pomiarów opadu.")
    st = _prepared(ctx, dataset)
    axis = st.axis
    p = st.values["P"]
    known = np.isfinite(p)
    grids = {thr: _month_counts(axis, p, p >= thr) for thr in DAY_THRESHOLDS}
    wet_sum = {thr: _month_totals_complete(axis, np.where(known & (p >= thr), p, np.where(known, 0.0, np.nan))) for thr in (0.1, 1.0)}
    tables = {}
    for thr, grid in grids.items():
        years, table, _ = proto.by_year_type(grid, axis.y0, year_type)
        tables[thr] = (years, table)
    years = tables[1.0][0]
    annual = {thr: tables[thr][1].sum(axis=1) for thr in DAY_THRESHOLDS}
    valid = np.isfinite(annual[1.0])
    if not valid.any():
        raise NoData("Żaden rok nie ma dość dni z pomiarem opadu (WMO-No. 1203: mniej niż 11 braków w miesiącu).")

    # intensity: the sum on wet days over the wet days, in years whose every month is complete
    intensity = {}
    for thr in (0.1, 1.0):
        _, sums, _ = proto.by_year_type(wet_sum[thr], axis.y0, year_type)
        _, days, _ = proto.by_year_type(_month_totals_complete(axis, np.where(known, (p >= thr).astype(float), np.nan)), axis.y0, year_type)
        with np.errstate(invalid="ignore", divide="ignore"):
            intensity[thr] = sums.sum(axis=1) / days.sum(axis=1)
    ref = _reference(params, years[valid])
    lo, hi = ref["from"], ref["to"]

    # M7: percentiles of wet days (P ≥ 1 mm) of the reference period, shares per complete year
    labels_day = axis.year if year_type == "calendar" else axis.hydro_year
    wet_ref = p[known & (p >= 1.0) & (labels_day >= lo) & (labels_day <= hi)]
    heavy: dict[str, Any] = {"wet_days": len(wet_ref), "reference": ref}
    labels, starts, _, complete = _complete_years(st, p, year_type)
    heavy_rows: dict[int, dict[str, Any]] = {}
    if len(wet_ref) >= 100:
        p95, p99 = np.percentile(wet_ref, [95, 99], method="median_unbiased")
        heavy.update({"p95": _r(p95, 1), "p99": _r(p99, 1)})
        filled = np.nan_to_num(p)
        total = np.add.reduceat(np.where(filled >= 1.0, filled, 0.0), starts)
        r95 = np.add.reduceat(np.where(filled > p95, filled, 0.0), starts)
        r99 = np.add.reduceat(np.where(filled > p99, filled, 0.0), starts)
        d95 = np.add.reduceat((filled > p95).astype(int), starts)
        d99 = np.add.reduceat((filled > p99).astype(int), starts)
        for i in np.flatnonzero(complete):
            share95 = 100 * r95[i] / total[i] if total[i] > 0 else math.nan
            share99 = 100 * r99[i] / total[i] if total[i] > 0 else math.nan
            heavy_rows[int(labels[i])] = {
                "prcptot": _r(total[i]),
                "r95": _r(r95[i]),
                "r95_share": _r(share95),
                "r95_days": int(d95[i]),
                "r99": _r(r99[i]),
                "r99_share": _r(share99),
                "r99_days": int(d99[i]),
            }
        shares95 = [r["r95_share"] for r in heavy_rows.values() if r["r95_share"] is not None]
        shares99 = [r["r99_share"] for r in heavy_rows.values() if r["r99_share"] is not None]
        heavy["r95_share_mean"] = _r(np.mean(shares95)) if shares95 else None
        heavy["r99_share_mean"] = _r(np.mean(shares99)) if shares99 else None
        heavy["years"] = len(heavy_rows)
    else:
        heavy["note"] = "Za mało dni z opadem ≥ 1 mm w okresie odniesienia (mniej niż 100) na percentyle."

    rows = _trim(years, np.isfinite(np.c_[tuple(annual.values())]).any(axis=1))
    annual_rows = []
    for i in range(rows.start, rows.stop):
        year = int(years[i])
        row = {"year": year, **{f"d{_key(thr)}": _r(annual[thr][i], 1) for thr in DAY_THRESHOLDS}}
        row["sdii"] = _r(intensity[1.0][i], 2)
        row["sdii01"] = _r(intensity[0.1][i], 2)
        row.update(heavy_rows.get(year, {}))
        annual_rows.append(row)

    months = []
    for m in range(12):
        item: dict[str, Any] = {"month": m + 1}
        for thr, grid in grids.items():
            column = grid[:, m]
            item[f"d{_key(thr)}"] = _r(np.nanmean(column), 1) if np.isfinite(column).any() else None
        sums = wet_sum[1.0][:, m]
        days = _month_totals_complete(axis, np.where(known, (p >= 1.0).astype(float), np.nan))[:, m]
        both = np.isfinite(sums) & np.isfinite(days)
        item["sdii"] = _r(sums[both].sum() / days[both].sum(), 2) if both.any() and days[both].sum() > 0 else None
        months.append(item)
    means = {f"d{_key(thr)}": _r(np.nanmean(annual[thr][valid]), 1) for thr in DAY_THRESHOLDS}
    for thr, key in ((1.0, "sdii"), (0.1, "sdii01")):
        ok = np.isfinite(intensity[thr])
        means[key] = _r(np.mean(intensity[thr][ok]), 2) if ok.any() else None
    computed_by = [
        _proto("Dni z opadem ≥ 0,1, 1, 10, 20 mm w miesiącu i roku (liczby dni wg WMO-No. 1203, 4.4.1 d)", "M5", "days"),
        _proto("Natężenie opadu dnia mokrego: suma w dniach ≥ 1 mm (≥ 0,1 mm) przez ich liczbę (SDII, ETCCDI)", "M4", "days"),
        _proto("Udział opadów dużych: suma w dniach powyżej 95. i 99. percentyla dni ≥ 1 mm okresu odniesienia w sumie dni ≥ 1 mm (R95pTOT, R99pTOT, ETCCDI; kwantyl typu 8)", "M7", "heavy"),
    ]
    out = _base(st, ctx, P_SOURCES, ("P",), computed_by)
    out.update(
        {
            "year_type": year_type,
            "thresholds": list(DAY_THRESHOLDS),
            "years": {"first": int(years[valid][0]), "last": int(years[valid][-1]), "complete": int(valid.sum())},
            "reference": ref,
            "annual": annual_rows,
            "months": months,
            "means": means,
            "heavy": heavy,
        }
    )
    return out


def _key(threshold: float) -> str:
    return "01" if threshold == 0.1 else str(int(threshold))


# --- M2: maxima of 1 to 10 days ------------------------------------------------------------------------


def precip_maxima(ctx: Context, params: Params) -> dict[str, Any]:
    """M2: the largest sums of 1, 2, 3, 5 and 10 days of each complete year, monthly maxima."""
    year_type = _year_type(params)
    dataset = _choose(ctx, params, ("P",), P_SOURCES, "Stacja nie ma pomiarów opadu.")
    st = _prepared(ctx, dataset)
    p = st.values["P"]
    found = {n: _annual_maxima(st, n, year_type) for n in DURATIONS}
    if len(found[1]["years"]) == 0:
        raise NoData("Żaden rok nie ma kompletu dni z pomiarem opadu; maksima liczę tylko z lat pełnych.")
    by_year: dict[int, dict[str, Any]] = {}
    summary = {}
    for n, item in found.items():
        for year, value, end in zip(item["years"], item["values"], item["end"], strict=True):
            row = by_year.setdefault(int(year), {"year": int(year)})
            row[f"p{n}"] = _r(value)
            row[f"p{n}_start"] = _date(st, int(end) - n + 1)
            row[f"p{n}_end"] = _date(st, int(end))
        values = item["values"]
        top = int(np.argmax(values))
        summary[str(n)] = {
            "mean": _r(values.mean()),
            "median": _r(np.median(values)),
            "min": _r(values.min()),
            "max": _r(values[top]),
            "max_start": _date(st, int(item["end"][top]) - n + 1),
            "max_end": _date(st, int(item["end"][top])),
            "n": len(values),
        }

    # monthly maxima of daily precipitation (WMO-No. 1203, 4.4.1 b: whatever days there are)
    axis = st.axis
    best, index = proto.block_extreme(p, axis.month_starts)
    best = best.reshape(axis.ny, 12)
    index = index.reshape(axis.ny, 12)
    enough = proto.month_quality(axis, np.isfinite(p)).enough
    annual_month = np.array([int(axis.month[e]) for e in found[1]["end"]])
    months = []
    for m in range(12):
        column = best[:, m]
        if not np.isfinite(column).any():
            months.append({"month": m + 1, "max": None})
            continue
        i = int(np.nanargmax(column))
        usable = column[enough[:, m] & np.isfinite(column)]
        months.append(
            {
                "month": m + 1,
                "max": _r(column[i]),
                "date": _date(st, int(index[i, m])),
                "mean_max": _r(usable.mean()) if len(usable) else None,
                "months": len(usable),
                "annual_max": int((annual_month == m + 1).sum()),
            }
        )
    finite = np.flatnonzero(np.isfinite(p))
    order = finite[np.argsort(-p[finite], kind="stable")[:10]]
    computed_by = [
        _proto("Największe sumy 1, 2, 3, 5 i 10 kolejnych dni w latach pełnych (okno kończące się w roku) i maksima miesięczne opadu dobowego", "M2")
    ]
    out = _base(st, ctx, P_SOURCES, ("P",), computed_by)
    out.update(
        {
            "year_type": year_type,
            "durations": list(DURATIONS),
            "annual": [by_year[y] for y in sorted(by_year)],
            "summary": summary,
            "incomplete": [int(y) for y in found[1]["incomplete"]],
            "months": months,
            "top": [{"date": _date(st, int(i)), "value": _r(p[i])} for i in order],
        }
    )
    return out


# --- M3: quantiles of the maxima (Hydrolog) and PMAXTP ----------------------------------------------


def precip_quantiles(ctx: Context, params: Params) -> dict[str, Any]:
    """M3: quantiles of the annual n-day maxima by Hydrolog's `stats flood-frequency`, PMAXTP."""
    year_type = _year_type(params)
    days = params.int("days", 1)
    if days not in DURATIONS:
        raise BadParam(f"days: one of {', '.join(map(str, DURATIONS))}")
    distribution = params.choice("distribution", ("all", "gev", "pearson3", "log_normal", "weibull"), "all")
    fit_method = params.choice("fit_method", ("l_moments", "mle", "moments", "least_squares"), "l_moments")
    dataset = _choose(ctx, params, ("P",), P_SOURCES, "Stacja nie ma pomiarów opadu.")
    st = _prepared(ctx, dataset)
    found = _annual_maxima(st, days, year_type)
    if len(found["values"]) == 0:
        raise NoData(f"Żaden rok nie ma pełnego maksimum {days}-dniowego.")
    ref = _reference(params, found["years"])
    lo, hi = ref["from"], ref["to"]
    keep = (found["years"] >= lo) & (found["years"] <= hi)
    found = {
        "years": found["years"][keep],
        "values": found["values"][keep],
        "end": found["end"][keep],
        "incomplete": found["incomplete"][(found["incomplete"] >= lo) & (found["incomplete"] <= hi)],
    }
    count = len(found["values"])
    if count < MIN_QUANTILE_YEARS:
        raise NoData(f"W latach {lo}–{hi} pełnych lat z maksimum {days}-dniowym jest {count}; kwantyle liczę od {MIN_QUANTILE_YEARS} lat.")
    maxima = [float(v) for v in found["values"]]
    options = {
        "values": maxima,
        "distribution": distribution,
        "fit_method": fit_method,
        "return_periods": list(RETURN_PERIODS),
    }
    run = hydrolog_bridge.call("stats flood-frequency", options)
    result = run["result"]
    fits = []
    for fit in result.get("distributions", []):
        fits.append(
            {
                key: fit.get(key)
                for key in (
                    "distribution_name",
                    "fit_method",
                    "parameters",
                    "return_periods",
                    "quantiles",
                    "ks_statistic",
                    "ks_p_value",
                    "ks_valid",
                    "ad_statistic",
                    "aic",
                )
            }
        )
    computed_by = [
        _proto("Maksima roczne sum n-dniowych opadu z lat pełnych (wejście kwantyli)", "M2"),
        run["provenance"],
    ]
    out = _base(st, ctx, P_SOURCES, ("P",), computed_by)
    out.update(
        {
            "year_type": year_type,
            "days": days,
            "distribution": distribution,
            "fit_method": fit_method,
            "reference": ref,
            "table_periods": list(TABLE_PERIODS),
            "maxima": [
                {"year": int(y), "value": _r(v), "start": _date(st, int(e) - days + 1), "end": _date(st, int(e))}
                for y, v, e in zip(found["years"], found["values"], found["end"], strict=True)
            ],
            "incomplete": [int(y) for y in found["incomplete"]],
            "hydrolog": {
                "n_years": result.get("n_years"),
                "best_distribution": result.get("best_distribution"),
                "distributions": fits,
                "empirical": result.get("empirical"),
                "notices": run["notices"],
                # the same computation from a shell, for checking
                "cli": "hydrolog stats flood-frequency --values "
                + ",".join(repr(v) for v in maxima)
                + f" --distribution {distribution} --fit-method {fit_method} --return-periods "
                + ",".join(f"{t:g}" for t in RETURN_PERIODS),
            },
            "pmaxtp": _pmaxtp_of(ctx, days),
        }
    )
    return out


_PMAXTP: OrderedDict[tuple[float, float, str], tuple[float, Any]] = OrderedDict()
_PMAXTP_LOCK = threading.Lock()
_PMAXTP_TTL = 24 * 3600.0
_PMAXTP_ERROR_TTL = 600.0
_COORDS: dict[int, dict[str, tuple[float, float]]] = {}


def _coordinates(ctx: Context) -> tuple[float, float] | None:
    table = _COORDS.get(id(ctx.store))
    if table is None:
        table = {f.station_code: f.geometry for f in ctx.store.catalog if f.geometry}
        _COORDS[id(ctx.store)] = table
    return table.get(ctx.code)


def _fetch_pmaxtp(latitude: float, longitude: float, method: str) -> Any:
    """PMAXTP of a point, cached for 24 hours (failures for 10 minutes); one request at a time."""
    key = (round(latitude, 4), round(longitude, 4), method)
    now = time.monotonic()
    hit = _PMAXTP.get(key)
    if hit is not None and now - hit[0] < (_PMAXTP_TTL if not isinstance(hit[1], Exception) else _PMAXTP_ERROR_TTL):
        return hit[1]
    with _PMAXTP_LOCK:
        hit = _PMAXTP.get(key)
        if hit is not None and time.monotonic() - hit[0] < (_PMAXTP_TTL if not isinstance(hit[1], Exception) else _PMAXTP_ERROR_TTL):
            return hit[1]
        try:
            value: Any = obserwator.fetch_pmaxtp(key[0], key[1], method=method, timeout=8.0)
        except obserwator.ObserwatorError as exc:
            value = exc
        _PMAXTP[key] = (time.monotonic(), value)
        while len(_PMAXTP) > 1000:
            _PMAXTP.popitem(last=False)
        return value


def _pmaxtp_of(ctx: Context, days: int) -> dict[str, Any]:
    if ctx.station.get("provider") != "IMGW-PIB":
        return {"available": False, "reason": "PMAXTP obejmuje tylko Polskę (IMGW-PIB)."}
    duration = PMAXTP_DURATION.get(days)
    if duration is None:
        return {"available": False, "reason": "PMAXTP podaje opady do 72 godzin (3 doby)."}
    point = _coordinates(ctx)
    if point is None:
        return {"available": False, "reason": "Stacja nie ma współrzędnych w katalogu."}
    longitude, latitude = point
    out: dict[str, Any] = {
        "available": True,
        "duration_min": duration,
        "latitude": round(latitude, 4),
        "longitude": round(longitude, 4),
        "periods": list(TABLE_PERIODS),
        # PMAXTP's own lines replace IMGW-PIB's (server/attribution.py, DEV-20.2)
        **attribution.fields("pmaxtp"),
    }
    for method in ("POT", "AMP"):
        found = _fetch_pmaxtp(latitude, longitude, method)
        if isinstance(found, Exception):
            out[method] = {"error": str(found)}
            continue
        data = found.data
        out[method] = {
            "quantiles": [_r(data.get_precipitation(duration, 100 / t), 1) for t in TABLE_PERIODS],
            "upper": [_r(data.get_confidence_bound(duration, 100 / t), 1) for t in TABLE_PERIODS],
        }
    if all("error" in out[m] for m in ("POT", "AMP")):
        out["available"] = False
        out["reason"] = f"PMAXTP niedostępne: {out['POT']['error']}"
    return out


# --- M6: dry and wet spells ------------------------------------------------------------------------------

SPELL_CLASSES = ((1, 1), (2, 2), (3, 3), (4, 5), (6, 10), (11, 15), (16, 20), (21, 30), (31, 10**6))


def spells(ctx: Context, params: Params) -> dict[str, Any]:
    """M6: dry and wet spells below or from a threshold of 0.1 or 1 mm."""
    threshold = float(params.choice("threshold", ("0.1", "1"), "0.1"))
    dataset = _choose(ctx, params, ("P",), P_SOURCES, "Stacja nie ma pomiarów opadu.")
    st = _prepared(ctx, dataset)
    p = st.values["P"]
    last_known = int(np.flatnonzero(np.isfinite(p))[-1])
    out_kinds = {}
    for kind, dry in (("dry", True), ("wet", False)):
        found, labels, complete = _spell_lengths(st, threshold, dry)
        years_ok = [int(y) for y, ok in zip(labels, complete, strict=True) if ok]
        if not years_ok:
            raise NoData("Żaden rok nie ma kompletu dni z pomiarem opadu; okresy liczę z lat pełnych.")
        start_year = st.axis.year[found.start]
        in_complete = np.isin(start_year, years_ok)
        longest = _longest_per_year(st, found, labels, complete)
        rows = []
        for year in years_ok:
            chosen = in_complete & (start_year == year)
            lengths = found.length[chosen]
            length, start = longest[year]
            rows.append(
                {
                    "year": year,
                    "longest": length,
                    "longest_start": _date(st, start),
                    "longest_end": _date(st, start + length - 1) if start >= 0 else None,
                    "n10": int((lengths >= 10).sum()),
                    "n15": int((lengths >= 15).sum()),
                    "n20": int((lengths >= 20).sum()),
                    "count": len(lengths),
                }
            )
        full = in_complete & ~found.censored
        classes = []
        for lo, hi in SPELL_CLASSES:
            hit = full & (found.length >= lo) & (found.length <= hi)
            classes.append({"from": lo, "to": hi if hi < 10**6 else None, "count": int(hit.sum()), "per_year": _r(hit.sum() / len(years_ok), 2)})
        order = np.argsort(-found.length, kind="stable")[:10]
        top = [
            {
                "start": _date(st, int(found.start[i])),
                "end": _date(st, int(found.start[i] + found.length[i] - 1)),
                "length": int(found.length[i]),
                "censored": bool(found.censored[i]),
            }
            for i in order
        ]
        current = None
        ending = np.flatnonzero(found.start + found.length - 1 == last_known)
        if len(ending):
            i = int(ending[0])
            current = {"start": _date(st, int(found.start[i])), "length": int(found.length[i]), "as_of": _date(st, last_known)}
        longest_values = np.array([r["longest"] for r in rows], dtype=float)
        out_kinds[kind] = {
            "years": rows,
            "classes": classes,
            "top": top,
            "current": current,
            "means": {
                "longest": _r(longest_values.mean(), 1),
                "n10": _r(np.mean([r["n10"] for r in rows]), 2),
                "n15": _r(np.mean([r["n15"] for r in rows]), 2),
                "n20": _r(np.mean([r["n20"] for r in rows]), 2),
                "count": _r(np.mean([r["count"] for r in rows]), 1),
            },
            "complete_years": len(rows),
        }
    computed_by = [
        _proto(
            f"Ciągi dni bezopadowych (P < {threshold:g} mm) i opadowych (P ≥ {threshold:g} mm): przerwane brakiem danych, przypisane do roku początku; lata pełne",
            "M6",
        )
    ]
    out = _base(st, ctx, P_SOURCES, ("P",), computed_by)
    out.update({"threshold": threshold, "dry": out_kinds["dry"], "wet": out_kinds["wet"]})
    return out


# --- M8: SPI and Kaczorowska's classes -----------------------------------------------------------------


def drought(ctx: Context, params: Params) -> dict[str, Any]:
    """M8: SPI of 1, 3, 6 and 12 months and Kaczorowska's relative precipitation classes."""
    dataset = _choose(ctx, params, ("P",), P_SOURCES, "Stacja nie ma pomiarów opadu.")
    st = _prepared(ctx, dataset)
    grid = _month_sums(st)
    y0 = st.axis.y0
    cal_years = np.arange(y0, y0 + grid.shape[0])
    annual = np.round(grid.sum(axis=1), 1)
    valid_years = cal_years[np.isfinite(annual)]
    if len(valid_years) == 0:
        raise NoData("Żaden rok nie ma pełnych sum miesięcznych opadu.")
    ref = _reference(params, valid_years)
    lo, hi = ref["from"], ref["to"]
    span = hi - lo + 1

    flat = grid.reshape(-1)
    have = np.flatnonzero(np.isfinite(flat))
    first, last = int(have[0]), int(have[-1])
    month_year = y0 + np.arange(len(flat)) // 12
    month_of = np.arange(len(flat)) % 12
    spi_out: dict[str, list[float | None]] = {}
    fits_out: dict[str, list[dict[str, Any]]] = {}
    freq_out: dict[str, list[float]] = {}
    events_out: dict[str, list[dict[str, Any]]] = {}
    for scale in SPI_SCALES:
        sums = proto.rolling_sum(flat, scale)
        values = np.full(len(flat), np.nan)
        fits = []
        for m in range(12):
            chosen = (month_of == m) & (month_year >= lo) & (month_year <= hi)
            sample = sums[chosen]
            sample = sample[np.isfinite(sample)]
            fit = proto.fit_gamma_thom(sample) if len(sample) >= proto.WMO_NORMAL_SHARE * span else None
            fits.append(
                {"month": m + 1, "alpha": _r(fit.alpha, 4), "beta": _r(fit.beta, 4), "q": _r(fit.q, 3), "n": fit.n}
                if fit
                else {"month": m + 1, "alpha": None, "beta": None, "q": None, "n": len(sample)}
            )
            if fit:
                where = month_of == m
                values[where] = proto.spi(sums[where], fit)
        if not any(f["alpha"] is not None for f in fits):
            raise NoData(
                f"Za mało pełnych miesięcy w latach {lo}–{hi} do dopasowania rozkładu SPI (potrzeba 80 % lat okresu)."
            )
        window = values[first : last + 1]
        classes = [proto.spi_class(v) for v in window]
        counted = [c for c in classes if c is not None]
        freq_out[str(scale)] = [_r(100 * counted.count(c) / len(counted), 1) if counted else None for c in range(7)]
        spi_out[str(scale)] = [_r(v, 2) for v in window]
        fits_out[str(scale)] = fits
        events = sorted(proto.drought_events(window), key=lambda e: -e[3])[:10]
        events_out[str(scale)] = [
            {
                "start": _month_name(y0, first + a),
                "end": _month_name(y0, first + b),
                "months": b - a + 1,
                "min": _r(low, 2),
                "magnitude": _r(mag, 2),
            }
            for a, b, low, mag in events
        ]

    # Kaczorowska: % of the normal of the reference period
    normal_months = np.array([proto.normal(grid[:, m], cal_years, lo, hi)[0] for m in range(12)])
    normal_year, ref_years = proto.normal(annual, cal_years, lo, hi)
    ref["years"] = ref_years
    with np.errstate(invalid="ignore", divide="ignore"):
        pct_months = 100 * grid / normal_months
        pct_year = 100 * annual / normal_year
    rows = _trim(cal_years, np.isfinite(grid).any(axis=1))
    k_rows = []
    month_classes: list[int] = []
    year_classes: list[int] = []
    for i in range(rows.start, rows.stop):
        mc = [proto.kaczorowska_class(v) for v in pct_months[i]]
        yc = proto.kaczorowska_class(pct_year[i])
        month_classes += [c for c in mc if c is not None]
        if yc is not None:
            year_classes.append(yc)
        k_rows.append(
            {
                "year": int(cal_years[i]),
                "pct": _r(pct_year[i], 0),
                "class": yc,
                "months_pct": [_r(v, 0) for v in pct_months[i]],
                "months_class": mc,
            }
        )
    computed_by = [
        _proto(
            "SPI 1, 3, 6, 12 mies.: rozkład gamma z prawdopodobieństwem zera, dopasowany w okresie odniesienia przybliżeniem Thoma (McKee i in. 1993; Edwards i McKee 1997; WMO-No. 1090)",
            "M8",
            "spi",
        ),
        _proto("Opad względny w % normalnej i klasy Kaczorowskiej (1962) miesięcy i lat", "M8", "kaczorowska"),
    ]
    out = _base(st, ctx, P_SOURCES, ("P",), computed_by)
    out.update(
        {
            "reference": ref,
            "years": {"first": int(valid_years[0]), "last": int(valid_years[-1])},
            "start": _month_name(y0, first),
            "spi": spi_out,
            "fits": fits_out,
            "frequency": freq_out,
            "events": events_out,
            "spi_classes": list(proto.SPI_CLASSES),
            "kaczorowska": {
                "classes": list(proto.KACZOROWSKA),
                "normal": {"annual": _r(normal_year), "months": [_r(v) for v in normal_months]},
                "years": k_rows,
                "frequency": {
                    "months": [_r(100 * month_classes.count(c) / len(month_classes), 1) if month_classes else None for c in range(7)],
                    "years": [_r(100 * year_classes.count(c) / len(year_classes), 1) if year_classes else None for c in range(7)],
                },
            },
        }
    )
    return out


def _month_name(y0: int, index: int) -> str:
    return f"{y0 + index // 12:04d}-{index % 12 + 1:02d}"


# --- M11: air temperature ----------------------------------------------------------------------------------

#: Characteristic days: (key, variable, test), definitions of ETCCDI (FD, ID, SU, TR) and of hot days.
CHARACTERISTIC_DAYS = (
    ("fd", "Tmin", lambda v: v < 0.0),
    ("id", "Tmax", lambda v: v < 0.0),
    ("su", "Tmax", lambda v: v > 25.0),
    ("hd", "Tmax", lambda v: v > 30.0),
    ("tr", "Tmin", lambda v: v > 20.0),
)


def _t_dataset(ctx: Context, params: Params) -> str:
    for variable in ("Tmean", "Tmax", "Tmin"):
        if _options(ctx, (variable,), T_SOURCES):
            return _choose(ctx, params, (variable,), T_SOURCES, "")
    raise NoData("Stacja nie ma pomiarów temperatury powietrza.")


def temperature(ctx: Context, params: Params) -> dict[str, Any]:
    """M11: means, extremes, the normal and anomalies, characteristic days, degree days."""
    dataset = _t_dataset(ctx, params)
    st = _prepared(ctx, dataset)
    axis = st.axis
    present = [v for v in ("Tmean", "Tmax", "Tmin") if v in st.values and np.isfinite(st.values[v]).any()]
    if not present:
        raise NoData("Stacja nie ma pomiarów temperatury powietrza.")
    cal_years = np.arange(axis.y0, axis.y0 + axis.ny)
    means = {v: _month_means(axis, st.values[v]) for v in present}
    annual = {v: np.where(np.isfinite(g).all(axis=1), g.mean(axis=1), np.nan) for v, g in means.items()}
    main = "Tmean" if "Tmean" in present else present[0]
    valid = np.isfinite(annual[main])
    if not valid.any():
        raise NoData("Żaden rok nie ma dość dni z pomiarem temperatury (WMO-No. 1203: mniej niż 11 braków w miesiącu).")
    ref = _reference(params, cal_years[valid])
    lo, hi = ref["from"], ref["to"]
    normal_year, ref_years = proto.normal(annual[main], cal_years, lo, hi)
    ref["years"] = ref_years
    normal_months = np.array([proto.normal(means[main][:, m], cal_years, lo, hi)[0] for m in range(12)])

    dtr = None
    if "Tmax" in present and "Tmin" in present:
        daily_range = st.values["Tmax"] - st.values["Tmin"]
        dtr = _month_means(axis, daily_range)
    counts = {}
    for key, variable, test in CHARACTERISTIC_DAYS:
        if variable in present:
            values = st.values[variable]
            with np.errstate(invalid="ignore"):
                counts[key] = _month_counts(axis, values, test(values))
    degree = {}
    if "Tmean" in present:
        t = st.values["Tmean"]
        with np.errstate(invalid="ignore"):
            degree["gdd5"] = _month_totals_complete(axis, np.where(np.isfinite(t), np.maximum(t - 5.0, 0.0), np.nan))
            degree["hdd"] = _month_totals_complete(axis, np.where(np.isfinite(t), np.where(t <= 15.0, 18.0 - t, 0.0), np.nan))

    extremes = {}
    if "Tmax" in present:
        extremes["max"] = proto.block_extreme(st.values["Tmax"], axis.month_starts, largest=True)
    if "Tmin" in present:
        extremes["min"] = proto.block_extreme(st.values["Tmin"], axis.month_starts, largest=False)

    def annual_extreme(kind: str, i: int) -> tuple[float | None, str | None]:
        value, index = extremes[kind]
        row_v = value.reshape(axis.ny, 12)[i]
        row_i = index.reshape(axis.ny, 12)[i]
        if not np.isfinite(row_v).any():
            return None, None
        j = int(np.nanargmax(row_v) if kind == "max" else np.nanargmin(row_v))
        return _r(row_v[j]), _date(st, int(row_i[j]))

    rows = _trim(cal_years, np.isfinite(np.c_[tuple(means[v].reshape(axis.ny, 12) for v in present)]).any(axis=1))
    annual_rows = []
    for i in range(rows.start, rows.stop):
        row: dict[str, Any] = {"year": int(cal_years[i])}
        row["mean"] = _r(annual[main][i], 2)
        row["anomaly"] = _r(annual[main][i] - normal_year, 2) if math.isfinite(normal_year) else None
        if "Tmax" in present:
            row["tmax"] = _r(annual["Tmax"][i], 2)
            row["abs_max"], row["abs_max_date"] = annual_extreme("max", i)
        if "Tmin" in present:
            row["tmin"] = _r(annual["Tmin"][i], 2)
            row["abs_min"], row["abs_min_date"] = annual_extreme("min", i)
        if dtr is not None:
            row["dtr"] = _r(dtr[i].mean() if np.isfinite(dtr[i]).all() else math.nan, 2)
        for key, grid in counts.items():
            row[key] = _r(grid[i].sum() if np.isfinite(grid[i]).all() else math.nan, 0)
        for key, grid in degree.items():
            row[key] = _r(grid[i].sum() if np.isfinite(grid[i]).all() else math.nan, 0)
        annual_rows.append(row)

    months = []
    for m in range(12):
        item: dict[str, Any] = {"month": m + 1, "normal": _r(normal_months[m], 2)}
        column = means[main][:, m]
        item["mean"] = _r(np.nanmean(column), 2) if np.isfinite(column).any() else None
        for variable, key in (("Tmax", "tmax"), ("Tmin", "tmin")):
            if variable in present:
                c = means[variable][:, m]
                item[key] = _r(np.nanmean(c), 2) if np.isfinite(c).any() else None
        if dtr is not None:
            c = dtr[:, m]
            item["dtr"] = _r(np.nanmean(c), 2) if np.isfinite(c).any() else None
        for kind, key in (("max", "abs_max"), ("min", "abs_min")):
            if kind in extremes:
                value, index = extremes[kind]
                v = value.reshape(axis.ny, 12)[:, m]
                if np.isfinite(v).any():
                    j = int(np.nanargmax(v) if kind == "max" else np.nanargmin(v))
                    item[key] = _r(v[j])
                    item[f"{key}_date"] = _date(st, int(index.reshape(axis.ny, 12)[j, m]))
        for key, grid in counts.items():
            c = grid[:, m]
            item[key] = _r(np.nanmean(c), 1) if np.isfinite(c).any() else None
        months.append(item)

    records = {}
    for kind, (value, index) in extremes.items():
        if np.isfinite(value).any():
            j = int(np.nanargmax(value) if kind == "max" else np.nanargmin(value))
            records[kind] = {"value": _r(value[j]), "date": _date(st, int(index[j]))}
    period_means = {}
    for key in ("mean", "tmax", "tmin", "dtr", *counts, *degree):
        values = [r[key] for r in annual_rows if r.get(key) is not None]
        period_means[key] = _r(float(np.mean(values)), 2 if key in ("mean", "tmax", "tmin", "dtr") else 1) if values else None
    with np.errstate(invalid="ignore"):
        anomalies = means[main] - normal_months
    computed_by = [
        _proto("Średnie miesięczne i roczne Tśr, Tmax, Tmin (braki wg WMO-No. 1203, 4.4.1), normalna okresu odniesienia i anomalia, ekstrema bezwzględne, amplituda dobowa", "M11", "means"),
        _proto("Dni charakterystyczne (ETCCDI: FD Tmin < 0, ID Tmax < 0, SU Tmax > 25, TR Tmin > 20; dni upalne Tmax > 30 °C)", "M11", "days"),
        _proto("Stopniodni: wzrostu ponad 5 °C (Σ max(Tśr − 5, 0)) i grzania wg Eurostatu (Σ 18 − Tśr w dniach Tśr ≤ 15 °C)", "M11", "days"),
    ]
    out = _base(st, ctx, T_SOURCES, (main,), computed_by)
    out.update(
        {
            "variables": present,
            "main": main,
            "years": {"first": int(cal_years[valid][0]), "last": int(cal_years[valid][-1]), "complete": int(valid.sum())},
            "reference": ref,
            "normal": {"annual": _r(normal_year, 2), "months": [_r(v, 2) for v in normal_months]},
            "annual": annual_rows,
            "months": months,
            "anomalies": [
                {"year": int(cal_years[i]), "months": [_r(v, 1) for v in anomalies[i]]} for i in range(rows.start, rows.stop)
            ],
            "records": records,
            "means": period_means,
            "counts": list(counts),
            "degree_days": list(degree),
        }
    )
    return out


# --- M12: harmonics of the annual cycle --------------------------------------------------------------------


def harmonics(ctx: Context, params: Params) -> dict[str, Any]:
    """M12: the mean and two harmonics of the annual Tmean cycle, per year and over the period."""
    dataset = _choose(ctx, params, ("Tmean",), T_SOURCES, "Stacja nie ma średniej dobowej temperatury powietrza.")
    st = _prepared(ctx, dataset)
    axis = st.axis
    t_values = st.values["Tmean"]
    enough = proto.month_quality(axis, np.isfinite(t_values)).enough.all(axis=1)
    labels, starts, lengths = axis.year_blocks("calendar")
    good = [int(y) for y, ok in zip(labels, enough, strict=True) if ok]
    if not good:
        raise NoData("Żaden rok nie ma dość dni ze średnią dobową temperatury w każdym miesiącu (WMO-No. 1203).")
    lo = params.int("from", good[0], good[0], good[-1])
    hi = params.int("to", good[-1], good[0], good[-1])
    if lo > hi:
        raise BadParam("from: after to")
    index = np.arange(len(t_values))
    block_of = np.repeat(np.arange(len(starts)), lengths)
    fraction = (index - starts[block_of] + 0.5) / lengths[block_of]
    years = []
    for b, year in enumerate(labels):
        if not enough[b]:
            continue
        sl = slice(int(starts[b]), int(starts[b] + lengths[b]))
        fit = proto.harmonic_fit(fraction[sl], t_values[sl], float(lengths[b]))
        if fit is None:
            continue
        years.append(
            {
                "year": int(year),
                "mean": _r(fit.mean, 2),
                "c1": _r(fit.amplitude[0], 2),
                "day1": _r(fit.peak[0], 1),
                "c2": _r(fit.amplitude[1], 2),
                "day2": _r(fit.peak[1], 1),
                "ev1": _r(100 * fit.explained[0], 1),
                "ev2": _r(100 * fit.explained[1], 1),
            }
        )
    chosen_years = np.isin(axis.year, [y for y in good if lo <= y <= hi]) & np.isfinite(t_values)
    bins = np.minimum((fraction * 365).astype(int), 364)
    sums = np.bincount(bins[chosen_years], weights=t_values[chosen_years], minlength=365)
    counts = np.bincount(bins[chosen_years], minlength=365)
    with np.errstate(invalid="ignore", divide="ignore"):
        cycle = sums / counts
    t_bins = (np.arange(365) + 0.5) / 365
    period = proto.harmonic_fit(t_bins, cycle, 365.0)
    pooled = proto.harmonic_fit(fraction[chosen_years], t_values[chosen_years], 365.0)
    if period is None or pooled is None:
        raise NoData("Za mało dni ze średnią dobową temperatury do analizy cyklu rocznego.")
    computed_by = [
        _proto(
            "Analiza harmoniczna cyklu rocznego Tśr: MNK ze średnią i 2 harmonikami, amplituda, faza (dzień maksimum), udział wariancji; lata z dość dniami w każdym miesiącu",
            "M12",
        )
    ]
    out = _base(st, ctx, T_SOURCES, ("Tmean",), computed_by)
    out.update(
        {
            "years_range": {"first": good[0], "last": good[-1], "from": lo, "to": hi, "count": sum(1 for y in good if lo <= y <= hi)},
            "period": {
                "mean": _r(period.mean, 2),
                "c1": _r(period.amplitude[0], 2),
                "day1": _r(period.peak[0], 1),
                "c2": _r(period.amplitude[1], 2),
                "day2": _r(period.peak[1], 1),
                "ev1": _r(100 * period.explained[0], 2),
                "ev2": _r(100 * period.explained[1], 2),
                "daily_ev": _r(100 * (pooled.explained[0] + pooled.explained[1]), 1),
            },
            "cycle": {
                "mean": [_r(v, 2) for v in cycle],
                "fit": [_r(v, 2) for v in period.fitted],
                "first": [_r(v, 2) for v in period.first],
            },
            "years": years,
        }
    )
    return out


# --- M14: hydrothermal coefficient and the de Martonne index --------------------------------------------------


def hydrothermal(ctx: Context, params: Params) -> dict[str, Any]:
    """M14: Sielianinov's hydrothermal coefficient and de Martonne's aridity index."""
    dataset = _choose(ctx, params, ("P", "Tmean"), T_SOURCES, "Stacja nie ma razem opadu i średniej dobowej temperatury.")
    st = _prepared(ctx, dataset)
    axis = st.axis
    cal_years = np.arange(axis.y0, axis.y0 + axis.ny)
    p_months = _month_sums(st)
    t_months = _month_means(axis, st.values["Tmean"])
    days = axis.days_in_month
    with np.errstate(invalid="ignore", divide="ignore"):
        k = np.where(t_months > 0, 10 * p_months / (t_months * days), np.nan)
    p_daily = st.values["P"]
    t_daily = st.values["Tmean"]
    _, starts, lengths = axis.year_blocks("calendar")
    both = np.isfinite(p_daily) & np.isfinite(t_daily)
    complete = np.add.reduceat(both.astype(int), starts) == lengths
    warm = both & (t_daily > 10.0)
    p_warm = np.add.reduceat(np.where(warm, p_daily, 0.0), starts)
    t_warm = np.add.reduceat(np.where(warm, t_daily, 0.0), starts)
    with np.errstate(invalid="ignore", divide="ignore"):
        season_k = np.where(complete & (t_warm > 0), 10 * p_warm / t_warm, np.nan)
    p_year = np.round(p_months.sum(axis=1), 1)
    t_year = np.where(np.isfinite(t_months).all(axis=1), t_months.mean(axis=1), np.nan)
    with np.errstate(invalid="ignore", divide="ignore"):
        martonne = p_year / (t_year + 10.0)
    columns = [m - 1 for m in SIELIANINOV_MONTHS]
    have = np.isfinite(k[:, columns]).any(axis=1) | np.isfinite(season_k) | np.isfinite(martonne)
    if not have.any():
        raise NoData("Żaden miesiąc nie ma razem pełnej sumy opadu i średniej temperatury.")
    rows = []
    for i in np.flatnonzero(have):
        values = [_r(k[i, c], 2) for c in columns]
        rows.append(
            {
                "year": int(cal_years[i]),
                "k": values,
                "classes": [proto.sielianinov_class(v) if v is not None else None for v in values],
                "season": _r(season_k[i], 2),
                "season_class": proto.sielianinov_class(season_k[i]),
                "de_martonne": _r(martonne[i], 1),
                "de_martonne_class": proto.de_martonne_class(martonne[i]),
            }
        )
    frequency = []
    for c in columns:
        classes = [proto.sielianinov_class(v) for v in k[:, c] if math.isfinite(v)]
        frequency.append(
            {
                "month": c + 1,
                "years": len(classes),
                "mean": _r(np.nanmean(k[:, c]), 2) if classes else None,
                "counts": [classes.count(j) for j in range(len(proto.SIELIANINOV))],
            }
        )
    season_values = season_k[np.isfinite(season_k)]
    martonne_values = martonne[np.isfinite(martonne)]
    computed_by = [
        _proto("Współczynnik hydrotermiczny Sielianinowa k = P / (0,1 Σt) miesięcy IV–IX (Σt = Tśr miesiąca × liczba dni) i okresu Tśr > 10 °C; klasy Skowery i Puły (2004)", "M14"),
        _proto("Wskaźnik suchości de Martonne'a I = P / (T + 10) (1926); klasy wg Baltasa (2007)", "M14"),
    ]
    out = _base(st, ctx, T_SOURCES, ("P", "Tmean"), computed_by)
    out.update(
        {
            "months": list(SIELIANINOV_MONTHS),
            "classes": list(proto.SIELIANINOV),
            "de_martonne_classes": list(proto.DE_MARTONNE),
            "years": rows,
            "frequency": frequency,
            "means": {
                "season": _r(season_values.mean(), 2) if len(season_values) else None,
                "season_class": proto.sielianinov_class(float(season_values.mean())) if len(season_values) else None,
                "de_martonne": _r(martonne_values.mean(), 1) if len(martonne_values) else None,
                "de_martonne_class": proto.de_martonne_class(float(martonne_values.mean())) if len(martonne_values) else None,
            },
        }
    )
    return out


# --- M10: snow ------------------------------------------------------------------------------------------------------


def snow(ctx: Context, params: Params) -> dict[str, Any]:
    """M10: days with snow cover, the maximum depth, first and last day, fresh snow per winter."""
    dataset = _choose(ctx, params, ("snow_cover",), SNOW_SOURCES, "Stacja nie ma pomiarów pokrywy śnieżnej.")
    st = _prepared(ctx, dataset)
    axis = st.axis
    depth = st.values["snow_cover"]
    fresh = st.values.get("fresh_snow")
    has_fresh = fresh is not None and np.isfinite(fresh).any()
    known = np.isfinite(depth)
    enough = proto.month_quality(axis, known).enough
    cover = _month_counts(axis, depth, depth >= 1.0)
    cover10 = _month_counts(axis, depth, depth >= 10.0)
    raw_cover = axis.per_month((known & (depth >= 1.0)).astype(float))
    raw_cover10 = axis.per_month((known & (depth >= 10.0)).astype(float))
    # winter seasons VIII–VII, labelled by the year they end in
    season_key = axis.year + (axis.month >= 8)
    starts = np.flatnonzero(np.r_[True, season_key[1:] != season_key[:-1]])
    seasons = season_key[starts]
    ends = np.r_[starts[1:], len(season_key)]
    rows = []
    skipped = 0
    for s, a, b in zip(seasons, starts, ends, strict=True):
        months = [(int(s) - 1, m) if m >= 8 else (int(s), m) for m in (8, 9, 10, 11, 12, 1, 2, 3, 4, 5, 6, 7)]
        cells = [(y - axis.y0, m - 1) for y, m in months if 0 <= y - axis.y0 < axis.ny]
        if len(cells) < 12:
            continue
        winter_ok = all(enough[r, c] for r, c in cells if c + 1 in SNOW_MONTHS)
        if not winter_ok:
            skipped += 1
            continue
        days = sum(cover[r, c] if enough[r, c] else raw_cover[r, c] for r, c in cells)
        days10 = sum(cover10[r, c] if enough[r, c] else raw_cover10[r, c] for r, c in cells)
        block = depth[a:b]
        with np.errstate(invalid="ignore"):
            on = np.flatnonzero(np.isfinite(block) & (block >= 1.0))
        top, where = proto.block_extreme(block, np.array([0]))
        row: dict[str, Any] = {
            "season": int(s),
            "days": _r(days, 0),
            "days10": _r(days10, 0),
            "max": _r(top[0], 0),
            "max_date": _date(st, int(a + where[0])) if where[0] >= 0 and top[0] > 0 else None,
            "first": _date(st, int(a + on[0])) if len(on) else None,
            "last": _date(st, int(a + on[-1])) if len(on) else None,
            "first_day": int(on[0]) if len(on) else None,
            "last_day": int(on[-1]) if len(on) else None,
        }
        if has_fresh:
            f = fresh[a:b]
            row["fresh_sum"] = _r(np.nansum(f), 0) if np.isfinite(f).any() else None
            row["fresh_days"] = int((np.isfinite(f) & (f > 0)).sum())
        rows.append(row)
    if not rows:
        raise NoData(
            "Żadna zima nie ma dość dni z pomiarem pokrywy śnieżnej w miesiącach X–V (WMO-No. 1203: mniej niż 11 braków w miesiącu)."
        )
    month_means = []
    for m in SNOW_MONTHS:
        c = cover[:, m - 1]
        month_means.append({"month": m, "days": _r(np.nanmean(c), 1) if np.isfinite(c).any() else None})

    def mean_of(key: str, digits: int = 1) -> float | None:
        values = [r[key] for r in rows if r.get(key) is not None]
        return _r(float(np.mean(values)), digits) if values else None

    firsts = [r["first_day"] for r in rows if r["first_day"] is not None]
    lasts = [r["last_day"] for r in rows if r["last_day"] is not None]
    record = max(rows, key=lambda r: r["max"] or 0)
    summary = {
        "seasons": len(rows),
        "days": mean_of("days"),
        "days10": mean_of("days10"),
        "max": mean_of("max"),
        "record": {"value": record["max"], "date": record["max_date"], "season": record["season"]},
        "first_median": _season_day(float(np.median(firsts))) if firsts else None,
        "last_median": _season_day(float(np.median(lasts))) if lasts else None,
        "earliest": min((r for r in rows if r["first_day"] is not None), key=lambda r: r["first_day"], default={}).get("first"),
        "latest": max((r for r in rows if r["last_day"] is not None), key=lambda r: r["last_day"], default={}).get("last"),
        "no_cover": sum(1 for r in rows if not r["days"]),
        "skipped": skipped,
    }
    if has_fresh:
        summary["fresh_sum"] = mean_of("fresh_sum")
        summary["fresh_days"] = mean_of("fresh_days")
    computed_by = [
        _proto("Pokrywa śnieżna sezonów VIII–VII: dni z pokrywą ≥ 1 i ≥ 10 cm (liczby dni wg WMO-No. 1203), maksimum, pierwszy i ostatni dzień, suma śniegu świeżego; zimy z dość dniami w X–V", "M10")
    ]
    out = _base(st, ctx, SNOW_SOURCES, ("snow_cover",), computed_by)
    out.update({"seasons": rows, "summary": summary, "months": month_means, "fresh": has_fresh})
    return out


def _season_day(offset: float) -> str:
    """A day of a VIII–VII season (0 = 1 August) as "MM-DD" of a season without 29 February."""
    day = np.datetime64("2001-08-01") + round(offset)
    return str(day)[5:]


# --- M13: trends -------------------------------------------------------------------------------------------------------------


def trends(ctx: Context, params: Params) -> dict[str, Any]:
    """M13: Hydrolog's Mann–Kendall test and Sen's slope of the annual series of M1 to M11."""
    has_p = bool(_options(ctx, ("P",), P_SOURCES))
    has_t = any(_options(ctx, (v,), T_SOURCES) for v in ("Tmean", "Tmax", "Tmin"))
    if not (has_p or has_t):
        raise NoData("Stacja nie ma pomiarów opadu ani temperatury.")
    candidates: list[tuple[str, str, str, np.ndarray, np.ndarray]] = []
    st = None
    if has_p:
        st = _prepared(ctx, _choose(ctx, params, ("P",), P_SOURCES, ""))
        axis = st.axis
        cal_years = np.arange(axis.y0, axis.y0 + axis.ny)
        years, sums, _, _ = _annual_sums(st, "calendar")
        candidates.append(("p_sum", "Suma roczna opadu", "mm", years, sums))
        maxima = _annual_maxima(st, 1, "calendar")
        candidates.append(("p_max1", "Maksymalny opad dobowy", "mm", maxima["years"], maxima["values"]))
        p = st.values["P"]
        r10 = _month_counts(axis, p, p >= 10.0)
        candidates.append(("r10", "Dni z opadem ≥ 10 mm", "dni", cal_years, np.where(np.isfinite(r10).all(axis=1), r10.sum(axis=1), np.nan)))
        found, labels, complete = _spell_lengths(st, 1.0, dry=True)
        longest = _longest_per_year(st, found, labels, complete)
        candidates.append(("cdd", "Najdłuższy okres bezopadowy (P < 1 mm)", "dni", np.array(list(longest), dtype=int), np.array([v[0] for v in longest.values()], dtype=float)))
    t_dataset = None
    tt = None
    if has_t:
        # the temperature dataset is chosen on its own: `dataset` names the precipitation one
        t_dataset = _t_dataset(ctx, Params({k: v for k, v in params.items() if k != "dataset"}))
        tt = _prepared(ctx, t_dataset)
        t_years = np.arange(tt.axis.y0, tt.axis.y0 + tt.axis.ny)
        if "Tmean" in tt.values and np.isfinite(tt.values["Tmean"]).any():
            grid = _month_means(tt.axis, tt.values["Tmean"])
            candidates.append(("t_mean", "Średnia roczna temperatura", "°C", t_years, np.where(np.isfinite(grid).all(axis=1), grid.mean(axis=1), np.nan)))
        for key, variable, test, label in (
            ("fd", "Tmin", lambda v: v < 0.0, "Dni z przymrozkiem (Tmin < 0 °C)"),
            ("su", "Tmax", lambda v: v > 25.0, "Dni gorące (Tmax > 25 °C)"),
        ):
            if variable in tt.values and np.isfinite(tt.values[variable]).any():
                values = tt.values[variable]
                with np.errstate(invalid="ignore"):
                    g = _month_counts(tt.axis, values, test(values))
                candidates.append((key, label, "dni", t_years, np.where(np.isfinite(g).all(axis=1), g.sum(axis=1), np.nan)))

    all_years = np.concatenate([c[3][np.isfinite(c[4])] for c in candidates if np.isfinite(c[4]).any()])
    if len(all_years) == 0:
        raise NoData("Brak serii rocznych z pełnymi latami.")
    first, last = int(all_years.min()), int(all_years.max())
    lo = params.int("from", first, first, last)
    hi = params.int("to", last, first, last)
    if lo > hi:
        raise BadParam("from: after to")
    alpha = 0.05
    series = []
    mk_provenance = None
    for key, label, unit, years_c, values_c in candidates:
        inside = (years_c >= lo) & (years_c <= hi) & np.isfinite(values_c)
        ys = years_c[inside]
        vs = values_c[inside]
        item: dict[str, Any] = {
            "key": key,
            "label": label,
            "unit": unit,
            "years": [int(y) for y in ys],
            "values": [_r(v, 2) for v in vs],
            "n": len(vs),
        }
        if len(vs) >= MIN_TREND_YEARS:
            run = hydrolog_bridge.call("stats mann-kendall", {"values": [float(v) for v in vs], "alpha": alpha})
            mk = run["result"]
            mk_provenance = mk_provenance or run["provenance"]
            item["mann_kendall"] = {k: mk.get(k) for k in ("s_statistic", "var_s", "z_score", "p_value", "trend_detected", "trend_direction", "significance_level")}
            sen = proto.sen_slope(ys, vs, float(mk.get("var_s") or 0.0), alpha)
            if sen:
                item["sen"] = {
                    "slope": _r(sen["slope"], 4),
                    "per_decade": _r(10 * sen["slope"], 3),
                    "lower_decade": _r(10 * sen["lower"], 3),
                    "upper_decade": _r(10 * sen["upper"], 3),
                    "intercept": _r(sen["intercept"], 4),
                }
        else:
            item["note"] = f"Za mało lat ({len(vs)}); test liczę od {MIN_TREND_YEARS}."
        series.append(item)
    computed_by = []
    if mk_provenance:
        computed_by.append(dict(mk_provenance, options={"alpha": alpha, "values": "seria roczna"}))
    computed_by.append(_proto("Nachylenie Sena (1968) z przedziałem ufności Gilberta (1987, rozdz. 16.5) z Var(S) testu Manna–Kendalla", "M13"))
    computed_by.append(_proto("Serie roczne M1, M2, M5, M6, M11 z lat pełnych (braki wg WMO-No. 1203)", "M13"))
    out = _base(st, ctx, P_SOURCES, ("P",), computed_by) if st is not None else _base(tt, ctx, T_SOURCES, (next(v for v in ("Tmean", "Tmax", "Tmin") if v in tt.values),), computed_by)
    out.update(
        {
            "range": {"first": first, "last": last, "from": lo, "to": hi},
            "alpha": alpha,
            "t_dataset": t_dataset,
            "series": series,
        }
    )
    return out


# --- M15: warming stripes (Hawkins) -----------------------------------------------------------------------------

STRIPES_METHOD = (
    "Hawkins warming stripes, showyourstripes.info (FAQ „How have these graphics been made?”) i "
    "climate-lab-book.ac.uk/2018/warming-stripes: średnia roczna Tśr (12 miesięcy wg WMO-No. 1203, 4.4.1), "
    "kolor wg różnicy od średniej okresu odniesienia, skala ±kσ średnich rocznych okresu rozrzutu w 16 kolorach "
    "(8 Blues i 8 Reds ColorBrewer)"
)


def _years(n: int) -> str:
    """„1 rok”, „3 lata”, „5 lat”."""
    if n == 1:
        return "1 rok"
    return f"{n} lata" if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14) else f"{n} lat"


def _stripe_period(
    params: Params, key: str, default: tuple[int, int], annual: np.ndarray, years: np.ndarray, stat: Any
) -> tuple[dict[str, Any], float]:
    """
    The period asked for (by default the FAQ's), else the whole record.

    `stat(values, years, lo, hi)` gives the period's value and count, NaN under the 80 % rule
    of WMO-No. 1203, 4.4.2. The whole record takes every year with a value.
    """
    lo = params.int(f"{key}_from", None, 1700, 2200)
    hi = params.int(f"{key}_to", None, 1700, 2200)
    lo = default[0] if lo is None else lo
    hi = default[1] if hi is None else hi
    if lo > hi:
        raise BadParam(f"{key}_from: after {key}_to")
    value, count = stat(annual, years, lo, hi)
    out: dict[str, Any] = {"asked_from": lo, "asked_to": hi, "asked_years": count, "default": [lo, hi] == list(default)}
    if math.isfinite(value):
        out.update({"from": lo, "to": hi, "years": count, "fallback": False})
        return out, value
    valid = np.isfinite(annual)
    first, last = int(years[valid][0]), int(years[valid][-1])
    sample = annual[valid]
    whole = float(sample.mean()) if key == "centre" else (float(np.std(sample, ddof=1)) if len(sample) > 1 else math.nan)
    out.update({"from": first, "to": last, "years": int(valid.sum()), "fallback": True})
    return out, whole


def stripes(ctx: Context, params: Params) -> dict[str, Any]:
    """M15: Ed Hawkins's warming stripes of the annual mean temperature (showyourstripes.info)."""
    dataset = _choose(ctx, params, ("Tmean",), T_SOURCES, "Paski klimatyczne potrzebują średniej dobowej temperatury powietrza (Tśr); stacja jej nie ma.")
    st = _prepared(ctx, dataset)
    axis = st.axis
    t = st.values["Tmean"]
    variant = params.choice("scale", tuple(proto.STRIPE_SCALES), "2025")
    centre_default, spread_default, k = proto.STRIPE_SCALES[variant]
    years = np.arange(axis.y0, axis.y0 + axis.ny)
    monthly = _month_means(axis, t).reshape(axis.ny, 12)
    annual = np.where(np.isfinite(monthly).all(axis=1), monthly.mean(axis=1), np.nan)
    valid = np.isfinite(annual)
    if valid.sum() < 2:
        raise NoData("Paski klimatyczne potrzebują co najmniej dwóch lat z pełnymi miesiącami (WMO-No. 1203: mniej niż 11 braków w miesiącu i mniej niż 5 kolejnych).")
    centre, centre_value = _stripe_period(params, "centre", centre_default, annual, years, proto.normal)
    spread, sd = _stripe_period(params, "spread", spread_default, annual, years, proto.period_sd)
    if not (math.isfinite(sd) and sd > 0):
        raise NoData("Średnie roczne nie mają rozrzutu: skali kolorów nie da się wyznaczyć.")
    scale = proto.StripeScale(centre_value, sd, k)
    quality = proto.month_quality(axis, np.isfinite(t))
    bad_months = (~quality.enough).reshape(axis.ny, 12).sum(axis=1)

    rows = _trim(years, valid)
    out_years = []
    for i in range(rows.start, rows.stop):
        value = float(annual[i])
        out_years.append(
            {
                "year": int(years[i]),
                "mean": _r(value, 2),
                "anomaly": _r(value - scale.centre, 2),
                "colour": scale.colour(value),
                "missing_months": int(bad_months[i]),
            }
        )
    drawn = [y for y in out_years if y["colour"] is not None]
    by_anomaly = sorted(drawn, key=lambda y: y["anomaly"])
    grey = [y["year"] for y in out_years if y["colour"] is None]
    notes = []
    for period, word in ((centre, "Środek skali"), (spread, "Rozrzut σ")):
        if period["fallback"]:
            notes.append(
                f"{word}: lata {period['asked_from']}–{period['asked_to']} mają średnią roczną w {period['asked_years']} z "
                f"{period['asked_to'] - period['asked_from'] + 1} lat (mniej niż 80 %, WMO-No. 1203, 4.4.2); "
                f"biorę cały zapis {period['from']}–{period['to']} ({_years(period['years'])} ze średnią)."
            )
        span = period["to"] - period["from"] + 1
        if span < 30:
            notes.append(f"{word}: okres {period['from']}–{period['to']} ma {_years(span)}, mniej niż zalecane 30 lat; skala jest mniej pewna.")
    if grey:
        notes.append(f"Lata szare (brak średniej rocznej: miesiąc z 11 lub więcej brakami dni albo 5 kolejnymi): {len(grey)}.")
    edges = scale.edges()
    computed_by = [_proto(STRIPES_METHOD, "M15")]
    out = _base(st, ctx, T_SOURCES, ("Tmean",), computed_by)
    out.update(
        {
            "variable": "Tmean",
            "first": out_years[0]["year"],
            "last": out_years[-1]["year"],
            "record": dict(out["record"], min=int(years[valid][0]), max=int(years[valid][-1])),
            "years": out_years,
            "grey": grey,
            "scale": {
                "variant": variant,
                "k": k,
                "centre": dict(centre, value=_r(scale.centre, 3)),
                "spread": dict(spread, sd=_r(scale.sd, 3)),
                "lo": _r(scale.lo, 2),
                "hi": _r(scale.hi, 2),
                "edges": [_r(e, 3) for e in edges],
                "anomaly_edges": [_r(e - scale.centre, 3) for e in edges],
            },
            "palette": list(proto.STRIPE_COLOURS),
            "coldest": by_anomaly[:5],
            "warmest": by_anomaly[::-1][:5],
            "darkest": {
                "blue": [y["year"] for y in drawn if y["colour"] == 0],
                "red": [y["year"] for y in drawn if y["colour"] == len(proto.STRIPE_COLOURS) - 1],
            },
            "notes": notes,
        }
    )
    return out



ANALYSES: dict[str, Analysis] = {
    "meteo-precip-sums": Analysis(precip_sums, "meteo", "Sumy opadów, normalna i sezonowość"),
    "meteo-precip-days": Analysis(precip_days, "meteo", "Dni z opadem, natężenie i opady duże"),
    "meteo-precip-maxima": Analysis(precip_maxima, "meteo", "Maksymalne opady 1–10 dni"),
    "meteo-precip-quantiles": Analysis(precip_quantiles, "meteo", "Opady maksymalne o zadanym prawdopodobieństwie"),
    "meteo-spells": Analysis(spells, "meteo", "Okresy bezopadowe i opadowe"),
    "meteo-drought": Analysis(drought, "meteo", "SPI i klasy opadów względnych"),
    "meteo-temperature": Analysis(temperature, "meteo", "Temperatura powietrza"),
    "meteo-harmonics": Analysis(harmonics, "meteo", "Cykl roczny temperatury"),
    "meteo-hydrothermal": Analysis(hydrothermal, "meteo", "Współczynnik hydrotermiczny"),
    "meteo-snow": Analysis(snow, "meteo", "Pokrywa śnieżna"),
    "meteo-trends": Analysis(trends, "meteo", "Trendy serii rocznych"),
    "meteo-stripes": Analysis(stripes, "meteo", "Paski klimatyczne"),
}
