"""The hydrological sections' series access and the computations Hydrolog has not got yet.

The top of the module reads a station's daily series (IMGW-PIB or ČHMÚ: H, Q, T) and
IMGW-PIB's half-year characteristics from the store. The rest are prototypes: each
function names its method and source, and the analysis that uses it reports
`hydrolog_bridge.prototype(method, target)`, where `target` is the step of the Nogat
plan (`docs/plans/2026-11-12-station-data-and-analyses.md`, H1 to H18) that moves the
computation into Hydrolog's catalog. Nothing here repeats a Hydrolog command.
"""

from __future__ import annotations

import math
import threading
from collections import OrderedDict
from dataclasses import dataclass
from datetime import date, datetime

import numpy as np
from server.analyses import Context, NoData

#: Daily series of hydrological stations, by provider.
DAILY_DATASETS = ("pl.imgw.hydro_daily", "cz.chmi.hydro_daily")
#: IMGW-PIB's half-year and annual characteristics.
HALF_YEARS = "pl.imgw.hydro_semiannual"
#: Calendar months of the hydrological year, November first.
HYDRO_MONTHS = (11, 12, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10)
ROMAN = ("I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII")
#: Seconds of a day: m3/s times a day is 86 400 m3.
DAY_SECONDS = 86_400.0
VARIABLE_NAMES = {"H": "stan wody", "Q": "przepływ", "T": "temperatura wody"}


# --- calendar ---------------------------------------------------------------------------


def calendar_parts(dates: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Calendar year and month (1-12) of `datetime64[D]` dates."""
    years = dates.astype("datetime64[Y]").astype(int) + 1970
    months = dates.astype("datetime64[M]").astype(int) % 12 + 1
    return years, months


def hydro_year(dates: np.ndarray) -> np.ndarray:
    """The hydrological year (1 November to 31 October, named by its end) of each date."""
    years, months = calendar_parts(dates)
    return years + (months >= 11)


def hydro_year_start(year: int) -> np.datetime64:
    """1 November of the year before `year`: the first day of hydrological year `year`."""
    return np.datetime64(f"{year - 1:04d}-11-01", "D")


def day_number(dates: np.ndarray) -> np.ndarray:
    """Days since 1970-01-01: the x of the GUI's `date` chart scale (`dayNumber` in lib.js)."""
    return dates.astype("datetime64[D]").astype(np.int64)


def iso(value: object) -> str | None:
    """An ISO date of a numpy date, a datetime, a date or None."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, np.datetime64):
        return None if np.isnat(value) else str(value.astype("datetime64[D]"))
    return str(value)[:10]


def runs(mask: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Starts and inclusive ends of the runs of True in a boolean array."""
    padded = np.concatenate(([False], np.asarray(mask, dtype=bool), [False]))
    edges = np.diff(padded.astype(np.int8))
    return np.flatnonzero(edges == 1), np.flatnonzero(edges == -1) - 1


def finite(values: np.ndarray) -> np.ndarray:
    return values[np.isfinite(values)]


# --- the daily series -------------------------------------------------------------------


@dataclass(frozen=True)
class Daily:
    """A station's daily series on a gap-free calendar: one row per day, NaN where missing."""

    dataset: str
    version: str
    dates: np.ndarray  # datetime64[D], every day from the first to the last of the series
    values: dict[str, np.ndarray]  # H [cm], Q [m3/s], T [degC]
    units: dict[str, str]
    hy: np.ndarray  # hydrological year of each day
    month: np.ndarray  # calendar month 1-12
    doy: np.ndarray  # day of the hydrological year, 1 = 1 November

    @property
    def label(self) -> str:
        return f"{self.dataset} {self.version}"

    def has(self, variable: str) -> bool:
        return variable in self.values and bool(np.isfinite(self.values[variable]).any())

    def years(self, variable: str) -> tuple[int, int]:
        """First and last hydrological year with a value of the variable."""
        present = np.flatnonzero(np.isfinite(self.values[variable]))
        return int(self.hy[present[0]]), int(self.hy[present[-1]])

    def block(self, first: int, last: int) -> slice:
        """The rows of hydrological years `first` to `last` (a contiguous slice)."""
        return slice(int(np.searchsorted(self.hy, first, "left")), int(np.searchsorted(self.hy, last, "right")))

    def complete_years(self, variable: str, first: int, last: int) -> list[int]:
        """Hydrological years with a value on each of their days (365 or 366)."""
        out = []
        values = self.values[variable]
        for year in range(first, last + 1):
            part = self.block(year, year)
            expected = int((hydro_year_start(year + 1) - hydro_year_start(year)).astype(int))
            if part.stop - part.start == expected and np.isfinite(values[part]).all():
                out.append(year)
        return out


_DAILY: OrderedDict[tuple[str, str, str], Daily] = OrderedDict()
_LOCK = threading.Lock()


def daily_dataset(ctx: Context) -> str | None:
    return next((dataset for dataset in DAILY_DATASETS if ctx.has(dataset)), None)


def load_daily(ctx: Context, need: str | None = None) -> Daily:
    """
    The station's daily series laid on a gap-free calendar.

    Raises `NoData` without a daily series or, with `need`, without a value of that
    variable (the text names what is missing).
    """
    dataset = daily_dataset(ctx)
    if dataset is None:
        raise NoData("Stacja nie ma w magazynie szeregu dobowego (H, Q, T).")
    series = ctx.store.series(dataset, ctx.code)
    key = (dataset, ctx.code, series.version)
    with _LOCK:
        hit = _DAILY.get(key)
    if hit is None:
        order = np.argsort(series.dates, kind="stable")
        dates = series.dates[order]
        first = dates[0]
        count = int((dates[-1] - first).astype(int)) + 1
        index = (dates - first).astype(int)
        calendar = first + np.arange(count)
        values = {}
        for variable in ("H", "Q", "T"):
            if variable in series.values:
                column = np.full(count, np.nan)
                column[index] = series.values[variable][order]
                values[variable] = column
        hy = hydro_year(calendar)
        _, month = calendar_parts(calendar)
        starts = np.array([hydro_year_start(int(year)) for year in np.unique(hy)])
        doy = (calendar - starts[np.searchsorted(np.unique(hy), hy)]).astype(int) + 1
        hit = Daily(dataset, series.version, calendar, values, dict(series.units), hy, month, doy)
        with _LOCK:
            _DAILY[key] = hit
            while len(_DAILY) > 16:
                _DAILY.popitem(last=False)
    if need is not None and not hit.has(need):
        raise NoData(f"Szereg dobowy stacji nie ma wartości {need} ({VARIABLE_NAMES.get(need, need)}).")
    return hit


def year_range(available: tuple[int, int], start: int | None, end: int | None) -> tuple[int, int]:
    """The chosen hydrological years clipped to the available ones (`BadParam` if empty)."""
    from server.analyses import BadParam

    first, last = available
    a = first if start is None else max(first, start)
    b = last if end is None else min(last, end)
    if a > b:
        raise BadParam(f"Lata poza zakresem danych {first}–{last}.")
    return a, b


def chart_line(dates: np.ndarray, values: np.ndarray, max_points: int = 1600) -> list[list[float | None]]:
    """
    A daily line for a chart, decimated to the minimum and maximum of buckets of days.

    A daily line for a chart: `[[day number, value], …]`, the minimum and the maximum of
    each bucket of days in their order (the shape survives at any zoom), `None` where a
    whole bucket is missing (the line breaks there).
    """
    count = len(values)
    days = day_number(dates)
    if count <= max_points:
        return [[int(d), (float(v) if np.isfinite(v) else None)] for d, v in zip(days, values, strict=True)]
    size = math.ceil(count / (max_points / 2))
    out: list[list[float | None]] = []
    for start in range(0, count, size):
        part = values[start : start + size]
        good = np.flatnonzero(np.isfinite(part))
        if good.size == 0:
            out.append([int(days[start]), None])
            continue
        low = good[np.argmin(part[good])]
        high = good[np.argmax(part[good])]
        for at in sorted({int(low), int(high)}):
            out.append([int(days[start + at]), float(part[at])])
    return out


# --- IMGW-PIB half-year characteristics ---------------------------------------------------


@dataclass(frozen=True)
class HalfYears:
    """IMGW-PIB's published half-year (XI–IV, V–X) and annual minima, means and maxima."""

    version: str
    years: np.ndarray  # hydrological years, ascending
    table: dict[tuple[str, str], np.ndarray]  # ("Q_max", "winter") -> value per year (NaN)
    when: dict[tuple[str, str], list[str | None]]  # ("Q_max", "winter") -> ISO date of the extreme

    @property
    def label(self) -> str:
        return f"{HALF_YEARS} {self.version}"

    def get(self, column: str, period: str) -> np.ndarray:
        return self.table.get((column, period), np.full(len(self.years), np.nan))

    def dates(self, column: str, period: str) -> list[str | None]:
        return self.when.get((column, period), [None] * len(self.years))

    def has(self, variable: str) -> bool:
        return any(np.isfinite(self.get(f"{variable}_{stat}", period)).any() for stat in ("max", "mean") for period in ("winter", "summer", "annual"))

    def annual(self, variable: str, stat: str) -> tuple[np.ndarray, list[str | None]]:
        """
        Annual maxima, minima or means from the half-year values.

        Annual values: the maximum (minimum) is the larger (smaller) of the two half-year
        ones, NaN when either is missing (F1 of the Nogat plan); the mean is IMGW-PIB's
        annual mean. With the date of the chosen half-year's extreme.
        """
        if stat == "mean":
            return self.get(f"{variable}_mean", "annual"), [None] * len(self.years)
        winter = self.get(f"{variable}_{stat}", "winter")
        summer = self.get(f"{variable}_{stat}", "summer")
        pick_winter = winter >= summer if stat == "max" else winter <= summer
        both = np.isfinite(winter) & np.isfinite(summer)
        values = np.where(both, np.where(pick_winter, winter, summer), np.nan)
        winter_dates = self.dates(f"{variable}_{stat}", "winter")
        summer_dates = self.dates(f"{variable}_{stat}", "summer")
        dates = [
            (w if pick else s) if ok else None
            for w, s, pick, ok in zip(winter_dates, summer_dates, pick_winter, both, strict=True)
        ]
        return values, dates

    def rows(self, first: int, last: int) -> np.ndarray:
        return (self.years >= first) & (self.years <= last)


def load_half_years(ctx: Context) -> HalfYears | None:
    """IMGW-PIB's half-year series of the station, None when the store has none."""
    if not ctx.has(HALF_YEARS):
        return None
    series = ctx.store.series(HALF_YEARS, ctx.code)
    years = np.unique(series.hydro_year)
    position = np.searchsorted(years, series.hydro_year)
    table: dict[tuple[str, str], np.ndarray] = {}
    when: dict[tuple[str, str], list[str | None]] = {}
    for column, values in series.values.items():
        for period in ("winter", "summer", "annual"):
            rows = series.period == period
            column_values = np.full(len(years), np.nan)
            column_values[position[rows]] = values[rows]
            table[(column, period)] = column_values
            start = series.extra.get(f"{column}_start")
            if start is not None:
                found: list[str | None] = [None] * len(years)
                for at, value in zip(position[rows], start[rows], strict=True):
                    found[int(at)] = iso(value)
                when[(column, period)] = found
    return HalfYears(series.version, years, table, when)


# --- H1: characteristic values of the first degree ---------------------------------------


def _part_stats(dates: np.ndarray, values: np.ndarray, expected: int) -> dict[str, object]:
    good = np.flatnonzero(np.isfinite(values))
    if good.size == 0:
        return {"min": None, "mean": None, "max": None, "min_date": None, "max_date": None, "missing": expected}
    low = good[np.argmin(values[good])]
    high = good[np.argmax(values[good])]
    return {
        "min": float(values[low]),
        "mean": float(np.mean(values[good])),
        "max": float(values[high]),
        "min_date": iso(dates[low]),
        "max_date": iso(dates[high]),
        "missing": int(expected - good.size),
    }


def first_degree_daily(daily: Daily, variable: str, first: int, last: int) -> list[dict[str, object]]:
    """
    First-degree values per hydrological year and half-year from the daily series.

    First-degree values (NW, SW, WW; NQ, SQ, WQ; T) of each hydrological year and half-year
    from the daily series: the minimum, mean and maximum of the days with a value, with
    the dates of the extremes and the number of missing days (a year with missing days
    is marked; its extremes may be milder than the true ones).

    Method: IMGW-PIB's definitions of the first-degree characteristic values (minimum,
    mean, maximum of a period), half-years XI–IV and V–X. Target: H1.
    """
    values = daily.values[variable]
    out = []
    for year in range(first, last + 1):
        part = daily.block(year, year)
        start = hydro_year_start(year)
        summer_start = np.datetime64(f"{year:04d}-05-01", "D")
        end = hydro_year_start(year + 1)
        dates = daily.dates[part]
        column = values[part]
        if not np.isfinite(column).any():
            continue
        winter = dates < summer_start
        row = {
            "year": year,
            "source": "daily",
            "winter": _part_stats(dates[winter], column[winter], int((summer_start - start).astype(int))),
            "summer": _part_stats(dates[~winter], column[~winter], int((end - summer_start).astype(int))),
            "annual": _part_stats(dates, column, int((end - start).astype(int))),
        }
        out.append(row)
    return out


def first_degree_half_years(half: HalfYears, variable: str, first: int, last: int) -> list[dict[str, object]]:
    """
    First-degree values per hydrological year and half-year as IMGW-PIB publishes them.

    First-degree values of each hydrological year and half-year as IMGW-PIB publishes
    them (half-year minima, means and maxima with their dates); the annual maximum is the
    larger, the annual minimum the smaller of the half-year ones, the annual mean
    IMGW-PIB's (Nogat plan, F1). Target: H1.
    """
    out = []
    for at, year in enumerate(half.years):
        if not first <= year <= last:
            continue
        row: dict[str, object] = {"year": int(year), "source": "imgw"}
        for period in ("winter", "summer"):
            row[period] = {
                "min": _value(half.get(f"{variable}_min", period)[at]),
                "mean": _value(half.get(f"{variable}_mean", period)[at]),
                "max": _value(half.get(f"{variable}_max", period)[at]),
                "min_date": half.dates(f"{variable}_min", period)[at],
                "max_date": half.dates(f"{variable}_max", period)[at],
            }
        high, high_dates = half.annual(variable, "max")
        low, low_dates = half.annual(variable, "min")
        row["annual"] = {
            "min": _value(low[at]),
            "mean": _value(half.get(f"{variable}_mean", "annual")[at]),
            "max": _value(high[at]),
            "min_date": low_dates[at],
            "max_date": high_dates[at],
        }
        if all(row[p][k] is None for p in ("winter", "summer", "annual") for k in ("min", "mean", "max")):  # type: ignore[index]
            continue
        out.append(row)
    return out


def _value(number: float) -> float | None:
    return float(number) if np.isfinite(number) else None


# --- H2: second degree from IMGW-PIB's half-years (comparison) -----------------------------


def second_degree(maxima: np.ndarray, means: np.ndarray, minima: np.ndarray) -> dict[str, float | None]:
    """
    Second-degree values: W, S, Z and N of the annual maxima, means and minima.

    Second-degree values from annual maxima, means and minima: the highest (W), mean (S),
    median (Z) and lowest (N) of each, keyed as Hydrolog's `stats characteristic`
    (`wwx` … `nnx`). The mean of maxima is the mean of *annual* maxima (Hydrolog's and
    IMGW-PIB's definition), not of pooled half-year maxima as the author's 2024 code did.
    Target: H2 (second degree from the values of H1).
    """
    out: dict[str, float | None] = {}
    for letter, series in (("w", maxima), ("s", means), ("n", minima)):
        good = finite(series)
        for stat, fn in (("w", np.max), ("s", np.mean), ("z", np.median), ("n", np.min)):
            out[f"{stat}{letter}x"] = float(fn(good)) if good.size else None
    return out


# --- H3: days and events beyond a level ---------------------------------------------------


def beyond(values: np.ndarray, level: float, above: bool) -> np.ndarray:
    """Days at or above a level (`above`), or below it; a missing day is neither."""
    with np.errstate(invalid="ignore"):
        return values >= level if above else values < level


def days_beyond_per_year(daily: Daily, variable: str, level: float, above: bool, first: int, last: int) -> list[int | None]:
    """
    Days per hydrological year at or above (below) a level.

    Days per hydrological year at or above (below) a level; None for a year without a
    value. Method: count of daily values beyond a fixed level. Target: H3.
    """
    values = daily.values[variable]
    out: list[int | None] = []
    for year in range(first, last + 1):
        part = values[daily.block(year, year)]
        out.append(int(beyond(part, level, above).sum()) if np.isfinite(part).any() else None)
    return out


def events_beyond(daily: Daily, variable: str, level: float, above: bool, first: int, last: int) -> list[dict[str, object]]:
    """
    Runs of consecutive days at or above (below) a level.

    Runs of consecutive days at or above (below) a level, a missing day ending a run: the
    start, end, duration and the peak (lowest value) with its date. Target: H3.
    """
    part = daily.block(first, last)
    values = daily.values[variable][part]
    dates = daily.dates[part]
    starts, ends = runs(beyond(values, level, above))
    out = []
    for start, end in zip(starts, ends, strict=True):
        window = values[start : end + 1]
        at = int(np.argmax(window) if above else np.argmin(window))
        out.append(
            {
                "start": iso(dates[start]),
                "end": iso(dates[end]),
                "days": int(end - start + 1),
                "peak": float(window[at]),
                "peak_date": iso(dates[start + at]),
            }
        )
    return out


# --- H7: low-flow periods across gaps in the record ---------------------------------------


def merge_low_flow_events(events: list[dict[str, object]], missing: np.ndarray, max_gap: int, min_duration: int) -> list[dict[str, object]]:
    """
    Join Hydrolog's low-flow runs across gaps in the record and keep the long ones.

    Join low-flow runs that Hydrolog found in separate gap-free spans when fewer than
    `max_gap` days part them (missing days count as gap days, as a missing day broke a
    run in the author's `find_low_sequences`), then keep those of at least
    `min_duration` days. Hydrolog's own rule within a span is the same (a gap shorter
    than `max_gap_days` merges, the duration counts the gap days, the deficit only the
    days below the threshold), so a series without gaps gives Hydrolog's events exactly.

    Each event holds global day indexes `start`, `end`, `values` (days with a value),
    `deficit` (unit times day), `min`, `mean`, `open_start`, `open_end`. Target: H7.
    """
    merged: list[dict[str, object]] = []
    for event in sorted(events, key=lambda e: e["start"]):  # type: ignore[arg-type,return-value]
        if merged and int(event["start"]) - int(merged[-1]["end"]) - 1 < max_gap:  # type: ignore[arg-type]
            last = merged[-1]
            total = int(last["values"]) + int(event["values"])  # type: ignore[arg-type]
            last["mean"] = (float(last["mean"]) * int(last["values"]) + float(event["mean"]) * int(event["values"])) / total  # type: ignore[arg-type]
            last["values"] = total
            last["deficit"] = float(last["deficit"]) + float(event["deficit"])  # type: ignore[arg-type]
            last["min"] = min(float(last["min"]), float(event["min"]))  # type: ignore[arg-type]
            last["end"] = event["end"]
            last["open_end"] = event["open_end"]
        else:
            merged.append(dict(event))
    out = []
    for event in merged:
        start, end = int(event["start"]), int(event["end"])  # type: ignore[arg-type]
        if end - start + 1 < min_duration:
            continue
        event["days"] = end - start + 1
        event["missing"] = int(missing[start : end + 1].sum())
        out.append(event)
    return out


# --- H8: duration curves and class frequencies --------------------------------------------

#: Exceedance percentages of a drawn duration curve.
CURVE_PERCENTS = np.unique(np.concatenate(([0.1, 0.2, 0.5], np.arange(1, 100, 1.0), [99.5, 99.8, 99.9])))
#: Percentages of the table of a duration curve (Q10 … Q95: the value exceeded p % of days).
TABLE_PERCENTS = (1, 5, 10, 30, 50, 70, 90, 95, 99)


def exceedance_values(values: np.ndarray, percents: np.ndarray | tuple[float, ...]) -> np.ndarray:
    """
    The empirical duration curve: the value equalled or exceeded on p % of the days.

    The value equalled or exceeded on p % of the days: the empirical duration curve with
    the Weibull plotting position p = m / (n + 1), m the rank from the highest
    (Searcy 1959, USGS Water-Supply Paper 1542-A; Vogel and Fennessey 1994), interpolated
    between ranks. Target: H8.
    """
    ordered = np.sort(finite(values))[::-1]
    count = ordered.size
    positions = np.arange(1, count + 1) / (count + 1) * 100.0
    return np.interp(np.asarray(percents, dtype=float), positions, ordered)


def log_classes(values: np.ndarray, count: int = 40) -> dict[str, object]:
    """
    Class frequencies of discharges on logarithmic classes, with the modal class.

    Class frequencies of discharges on logarithmic classes (`count` classes between the
    smallest positive and the largest value): the counts and the modal class. Equal
    classes would put the mode always in the lowest class of a skewed flow series.
    Target: H8 (the modal class).
    """
    good = finite(values)
    good = good[good > 0]
    if good.size < 2 or good.min() == good.max():
        return {"edges": [], "counts": [], "modal": None}
    edges = np.logspace(math.log10(good.min()), math.log10(good.max()), count + 1)
    counts, _ = np.histogram(good, bins=edges)
    at = int(np.argmax(counts))
    return {
        "edges": edges.tolist(),
        "counts": counts.tolist(),
        "modal": {"from": float(edges[at]), "to": float(edges[at + 1]), "days": int(counts[at]), "percent": float(counts[at] / good.size * 100)},
    }


def class_month_table(values: np.ndarray, months: np.ndarray, edges: np.ndarray) -> list[dict[str, object]]:
    """
    Days of each water-level class in each hydrological month (the author's table).

    Days of each water-level class in each hydrological month, from the highest class
    down, with the total, the share and the cumulative days „including higher” and
    „including lower” (the author's `calculate_water_levels_frequency`, 2024, on the
    classes of Hydrolog's `water-level-zones`; Byczkowski 1996, Hydrologia t. 1). Target: H8.
    """
    keep = np.isfinite(values)
    values = values[keep]
    months = months[keep]
    total = values.size
    index = np.clip(np.searchsorted(edges, values, side="right") - 1, 0, len(edges) - 2)
    table = np.zeros((len(edges) - 1, 12), dtype=int)
    hydro_month = (months - 11) % 12
    np.add.at(table, (index, hydro_month), 1)
    rows = []
    higher = 0
    for at in range(len(edges) - 2, -1, -1):
        count = int(table[at].sum())
        lower = total - higher
        higher += count
        rows.append(
            {
                "from": float(edges[at]),
                "to": float(edges[at + 1]),
                "months": table[at].tolist(),
                "days": count,
                "percent": count / total * 100 if total else None,
                "with_higher": higher,
                "with_lower": lower,
            }
        )
    return rows


# --- H12: Pardé coefficients and the regime type ------------------------------------------

#: The provisional reading of Dynowska's (1997) criteria, as Wrzesiński (2018) states them.
REGIME_RULE = {
    "spring_months": [3, 4],
    "summer_months": [6, 7, 8],
    "weak": 1.30,
    "strong": 1.80,
    "summer_rise": 1.00,
    "nearly_equal": 0.95,
}
REGIME_SOURCE = (
    "Dynowska I. (1997), Reżim odpływu rzecznego, Atlas Rzeczypospolitej Polskiej; kryteria "
    "za: Wrzesiński D. (2018), Typologia reżimu odpływu rzek w Polsce w różnych fazach "
    "oscylacji północnoatlantyckiej, Badania Fizjograficzne R. IX ser. A (A69), 249–261, "
    "doi:10.14746/bfg.2018.9.19"
)


def parde(monthly_means: list[float], annual_mean: float) -> list[float]:
    """
    Pardé's coefficients of the twelve calendar months.

    Pardé's coefficients: the mean flow of each calendar month over the mean annual flow
    (Pardé 1933, Fleuves et rivières). Target: H12.
    """
    return [float(value) / annual_mean for value in monthly_means]


def regime_type(coefficients: list[float]) -> dict[str, object]:
    """
    A regime type after Dynowska's classification, read provisionally.

    A regime type after Dynowska's classification, read provisionally from the Pardé
    coefficients (calendar months 1-12) — the criteria as Wrzesiński (2018) states them:

    1. nival weakly developed: the spring month at most 130 % of the mean annual flow;
    2. nival moderately developed: 130–180 %; 3. nival strongly developed: above 180 %;
    4. nival-pluvial: spring „as a rule” 130–180 % and a summer rise to at least 100 %;
    5. pluvio-nival: the summer month higher than or nearly equal to the spring one.

    The reading (ours, provisional, to be fixed in Hydrolog's plan): the spring month is
    the larger of III and IV, the summer month the largest of VI–VIII, „nearly equal”
    is at least 95 % of the spring value; rule 5 is tested first, then 4, then 1–3 by
    the spring value. Target: H12.
    """
    rule = REGIME_RULE
    spring_month = max(rule["spring_months"], key=lambda m: coefficients[m - 1])  # type: ignore[arg-type,index]
    summer_month = max(rule["summer_months"], key=lambda m: coefficients[m - 1])  # type: ignore[arg-type,index]
    spring = coefficients[spring_month - 1]
    summer = coefficients[summer_month - 1]
    if summer >= rule["nearly_equal"] * spring:  # type: ignore[operator]
        code, label = 5, "pluwialno-niwalny"
    elif summer >= rule["summer_rise"]:  # type: ignore[operator]
        code, label = 4, "niwalno-pluwialny"
    elif spring <= rule["weak"]:  # type: ignore[operator]
        code, label = 1, "niwalny słabo wykształcony"
    elif spring <= rule["strong"]:  # type: ignore[operator]
        code, label = 2, "niwalny średnio wykształcony"
    else:
        code, label = 3, "niwalny silnie wykształcony"
    return {
        "code": code,
        "label": label,
        "spring": {"month": spring_month, "coefficient": spring},
        "summer": {"month": summer_month, "coefficient": summer},
        "rule": rule,
        "source": REGIME_SOURCE,
        "provisional": True,
    }


def seasonality_index(monthly: list[float]) -> float | None:
    """
    Walsh and Lawler's seasonality index of twelve monthly values.

    Walsh and Lawler's (1981, Weather 36: 201–208) seasonality index of twelve monthly
    values, SI = Σ|x_m − R/12| / R with R their sum: 0 for an even year, 1.83 when one
    month holds everything. Applied here to the mean monthly flows. Target: H13.
    """
    values = np.asarray(monthly, dtype=float)
    total = values.sum()
    if not np.isfinite(total) or total <= 0:
        return None
    return float(np.abs(values - total / 12).sum() / total)


# --- H13: circular statistics of the dates of extremes ------------------------------------


def circular_dates(dates: list[str]) -> dict[str, object] | None:
    """
    The circular mean date and the concentration of dates over the year.

    The mean date and the concentration of dates over the year as directional statistics
    (Bayliss and Jones 1993, IH Report 121; Burn 1997, J. Hydrol. 202: 212–230): each date
    an angle θ = 2π·(day − 0.5)/L of its calendar year (L = 365 or 366), the mean
    direction atan2(Σ sin θ, Σ cos θ) is the mean date, the length r of the mean vector
    (0 to 1) the concentration. Target: H13.
    """
    if not dates:
        return None
    days = np.array(dates, dtype="datetime64[D]")
    years, _ = calendar_parts(days)
    starts = np.array([np.datetime64(f"{y:04d}-01-01", "D") for y in years])
    lengths = np.array([366 if (y % 4 == 0 and y % 100 != 0) or y % 400 == 0 else 365 for y in years])
    day = (days - starts).astype(int) + 1
    angle = 2 * np.pi * (day - 0.5) / lengths
    x = float(np.mean(np.cos(angle)))
    y = float(np.mean(np.sin(angle)))
    direction = math.atan2(y, x) % (2 * math.pi)
    mean_day = direction / (2 * math.pi) * 365.25 + 0.5
    return {
        "n": int(days.size),
        "mean_day": mean_day,
        "mean_date": _day_label(mean_day),
        "r": math.hypot(x, y),
        "angles": angle.tolist(),
    }


def _day_label(day: float) -> str:
    """A day of a (non-leap) calendar year as „12 III”."""
    whole = min(max(round(day), 1), 365)
    moment = np.datetime64("2001-01-01", "D") + (whole - 1)
    _, month = calendar_parts(np.array([moment]))
    return f"{int(str(moment)[8:10])} {ROMAN[int(month[0]) - 1]}"


# --- H14: harmonic analysis of the annual cycle --------------------------------------------

PERIOD_DAYS = 365.25


def harmonics(day: np.ndarray, values: np.ndarray, count: int = 2) -> dict[str, object] | None:
    """
    Harmonic analysis of an annual cycle by least squares.

    Harmonic analysis of an annual cycle by least squares: x(t) = A0 + Σ_k [a_k cos(2πkt/P)
    + b_k sin(2πkt/P)], P = 365.25 days, t the day of the hydrological year (0 = 1 XI);
    for each harmonic the amplitude C_k = √(a_k² + b_k²), the phase and the day of its
    first maximum t_k = P·atan2(b_k, a_k)/(2πk), and the share of the variance explained
    by the harmonics 1..k (Wilks 2011, Statistical Methods in the Atmospheric Sciences,
    §9.4; the author used it on Baltic buoy temperatures). Target: H14.
    """
    keep = np.isfinite(values)
    t = day[keep].astype(float)
    y = values[keep]
    if y.size < 4 * count + 2:
        return None
    columns = [np.ones_like(t)]
    for k in range(1, count + 1):
        omega = 2 * np.pi * k * t / PERIOD_DAYS
        columns += [np.cos(omega), np.sin(omega)]
    design = np.column_stack(columns)
    coefficients, *_ = np.linalg.lstsq(design, y, rcond=None)
    total = float(np.sum((y - y.mean()) ** 2))
    out: list[dict[str, float]] = []
    for k in range(1, count + 1):
        a, b = coefficients[2 * k - 1], coefficients[2 * k]
        amplitude = math.hypot(a, b)
        phase = math.atan2(b, a) % (2 * math.pi)
        fitted = design[:, : 2 * k + 1] @ coefficients[: 2 * k + 1]
        explained = 1 - float(np.sum((y - fitted) ** 2)) / total if total > 0 else None
        out.append({"k": k, "amplitude": amplitude, "phase": phase, "day_of_max": phase * PERIOD_DAYS / (2 * np.pi * k) + 1, "explained": explained})
    return {"mean": float(coefficients[0]), "n": int(y.size), "harmonics": out, "coefficients": coefficients.tolist()}


def harmonic_curve(coefficients: list[float], days: np.ndarray) -> np.ndarray:
    """The fitted annual cycle at days of the hydrological year (1 = 1 XI)."""
    t = days.astype(float) - 1
    out = np.full(t.shape, coefficients[0])
    for k in range(1, (len(coefficients) - 1) // 2 + 1):
        omega = 2 * np.pi * k * t / PERIOD_DAYS
        out += coefficients[2 * k - 1] * np.cos(omega) + coefficients[2 * k] * np.sin(omega)
    return out


def hydro_day_label(day: float) -> str:
    """A day of the hydrological year (1 = 1 XI) as „24 VII”."""
    whole = min(max(round(day), 1), 365)
    moment = np.datetime64("2001-11-01", "D") + (whole - 1)
    _, month = calendar_parts(np.array([moment]))
    return f"{int(str(moment)[8:10])} {ROMAN[int(month[0]) - 1]}"


# --- H16: Sen's slope ------------------------------------------------------------------------


def sen_slope(years: np.ndarray, values: np.ndarray) -> dict[str, float] | None:
    """
    Sen's slope with Conover's intercept and Gilbert's confidence interval.

    Sen's (1968, JASA 63: 1379–1389) slope: the median of the slopes of all pairs of
    years, with the intercept after Conover (median of y − slope·t) and the 95 %
    confidence interval of the slope by the normal approximation of Kendall's S
    (Gilbert 1987, Statistical Methods for Environmental Pollution Monitoring, §16.5).
    Target: H16.
    """
    keep = np.isfinite(values)
    t = years[keep].astype(float)
    y = values[keep]
    n = y.size
    if n < 3:
        return None
    i, j = np.triu_indices(n, 1)
    slopes = np.sort((y[j] - y[i]) / (t[j] - t[i]))
    slope = float(np.median(slopes))
    intercept = float(np.median(y - slope * t))
    variance = n * (n - 1) * (2 * n + 5) / 18
    c = 1.959964 * math.sqrt(variance)
    m1 = int((slopes.size - c) / 2)
    m2 = int((slopes.size + c) / 2) + 1
    low = float(slopes[max(m1 - 1, 0)]) if slopes.size else None
    high = float(slopes[min(m2 - 1, slopes.size - 1)]) if slopes.size else None
    return {"slope": slope, "intercept": intercept, "low": low, "high": high, "n": int(n)}  # type: ignore[dict-item]


# --- H18: baseflow ----------------------------------------------------------------------------

BASEFLOW_ALPHA = 0.925
BASEFLOW_PASSES = 3
BASEFLOW_PAD = 30


def lyne_hollick(flows: np.ndarray, alpha: float = BASEFLOW_ALPHA, passes: int = BASEFLOW_PASSES, pad: int = BASEFLOW_PAD) -> np.ndarray:
    """
    Baseflow of a gap-free daily series by the Lyne–Hollick filter.

    Baseflow of a gap-free daily series by the one-parameter recursive digital filter of
    Lyne and Hollick (1979): quickflow q_t = α·q_{t−1} + (1 + α)/2·(Q_t − Q_{t−1}), kept
    within 0..Q_t, baseflow = Q − q; three passes forward, backward, forward with
    α = 0.925 (Nathan and McMahon 1990, WRR 26: 1465–1473) and the series reflected by
    30 days at both ends (Ladson et al. 2013, Aust. J. Water Resour. 17: 25–34).
    Target: H18.
    """
    reach = min(pad, flows.size - 1)
    series = np.concatenate((flows[reach:0:-1], flows, flows[-2 : -reach - 2 : -1])) if reach > 0 else flows.copy()
    base = series.copy()
    for number in range(passes):
        source = base if number % 2 == 0 else base[::-1]
        quick = np.zeros_like(source)
        for t in range(1, source.size):
            value = alpha * quick[t - 1] + (1 + alpha) / 2 * (source[t] - source[t - 1])
            quick[t] = min(max(value, 0.0), source[t])
        result = source - quick
        base = result if number % 2 == 0 else result[::-1]
    return base[reach : reach + flows.size]


def recession_constant(flows: np.ndarray, minimum: int = 5) -> dict[str, float] | None:
    """
    The recession constant k from the recession segments of a daily series.

    The recession constant k = Q_{t+1}/Q_t: the median ratio over the days of recession
    segments, runs of at least `minimum` days of falling flow (Tallaksen 1995, J. Hydrol.
    165: 349–370, a review of the methods); the recession half-time ln 2 / −ln k.
    Target: H18.
    """
    with np.errstate(invalid="ignore", divide="ignore"):
        ratio = flows[1:] / flows[:-1]
        falling = np.isfinite(ratio) & (ratio < 1) & (flows[:-1] > 0)
    starts, ends = runs(falling)
    picked = [ratio[s : e + 1] for s, e in zip(starts, ends, strict=True) if e - s + 1 >= minimum]
    if not picked:
        return None
    k = float(np.median(np.concatenate(picked)))
    return {"k": k, "half_days": math.log(2) / -math.log(k) if 0 < k < 1 else None, "segments": len(picked)}  # type: ignore[dict-item]
