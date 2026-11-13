"""Numeric prototypes of the meteorological analyses Hydrolog does not have yet.

The Nogat plan (2026-11-12-station-data-and-analyses, M1 to M14; M15 the warming stripes)
moves each of these computations to Hydrolog; until then `meteo.py` labels every result computed here with
`hydrolog_bridge.prototype(method, target)`. Each function names its method and source.

Missing data follow the WMO Guidelines on the Calculation of Climate Normals (WMO-No. 1203,
2017 edition, section 4.4):

- a monthly mean or count is missing when 11 or more days of the month, or 5 or more
  consecutive days, are missing (4.4.1 a, d); a count is the share of observed days with the
  event times the days of the month;
- a monthly sum needs every day; a multi-day total that follows missing days stands for them
  when the days it covers are fewer than 5 consecutive and fewer than 11 in the month
  (4.4.1 c);
- monthly extremes use whatever days there are (4.4.1 b);
- a normal needs values in at least 80 % of the years of its period (4.4.2).

Annual values need all twelve months. Annual extremes, spells and the annual maxima of a
frequency analysis need every day of the year, as `stats flood-frequency` does with a daily
series („Lata z brakami dni są pomijane”).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from functools import cached_property

import numpy as np
from scipy.special import gammainc, ndtri

#: WMO-No. 1203, 4.4.1: a monthly mean or count is missing from this many missing days …
WMO_MISSING_DAYS = 11
#: … or from this many consecutive missing days.
WMO_MISSING_RUN = 5
#: WMO-No. 1203, 4.4.2: a normal needs values in this share of the years of its period.
WMO_NORMAL_SHARE = 0.8


def calendar(dates: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Calendar year, month (1 to 12) and day of the month of `datetime64[D]` dates."""
    months = dates.astype("datetime64[M]")
    year = dates.astype("datetime64[Y]").astype(int) + 1970
    month = months.astype(int) % 12 + 1
    day = (dates - months.astype("datetime64[D]")).astype(int) + 1
    return year, month, day


@dataclass(frozen=True)
class Axis:
    """Every day of whole calendar years: the frame all daily arrays of a station share."""

    dates: np.ndarray  # datetime64[D], 1 January of y0 to 31 December of the last year
    year: np.ndarray
    month: np.ndarray
    day: np.ndarray
    hydro_year: np.ndarray  # XI–X, labelled by the year it ends in
    month_key: np.ndarray  # (year - y0) * 12 + month - 1
    y0: int
    ny: int

    @classmethod
    def spanning(cls, first: np.datetime64, last: np.datetime64) -> Axis:
        y0 = int(str(first)[:4])
        y1 = int(str(last)[:4])
        dates = np.arange(np.datetime64(f"{y0:04d}-01-01"), np.datetime64(f"{y1 + 1:04d}-01-01"), dtype="datetime64[D]")
        year, month, day = calendar(dates)
        return cls(dates, year, month, day, year + (month >= 11), (year - y0) * 12 + month - 1, y0, y1 - y0 + 1)

    def place(self, dates: np.ndarray, values: np.ndarray, fill: object = np.nan) -> np.ndarray:
        """The values of a series at their dates on this axis, `fill` on the other days."""
        out = np.full(len(self.dates), fill, dtype=object if values.dtype == object else float)
        out[(dates - self.dates[0]).astype(int)] = values
        return out

    # --- months ------------------------------------------------------------------------

    def per_month(self, weights: np.ndarray) -> np.ndarray:
        """The sum of `weights` in each month, as (years, 12)."""
        return np.bincount(self.month_key, weights=weights, minlength=self.ny * 12).reshape(self.ny, 12)

    @cached_property
    def month_starts(self) -> np.ndarray:
        return np.flatnonzero(np.r_[True, self.month_key[1:] != self.month_key[:-1]])

    @cached_property
    def days_in_month(self) -> np.ndarray:
        return self.per_month(np.ones(len(self.dates)))

    def year_blocks(self, year_type: str) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Labels, first index and length of each (calendar or hydrological) year on the axis.

        The hydrological years at both ends are partial: XI–X years start on 1 November.
        """
        key = self.year if year_type == "calendar" else self.hydro_year
        starts = np.flatnonzero(np.r_[True, key[1:] != key[:-1]])
        lengths = np.diff(np.r_[starts, len(key)])
        return key[starts], starts, lengths


@dataclass(frozen=True)
class MonthQuality:
    """How complete each month of a daily array is (WMO-No. 1203, 4.4.1)."""

    known: np.ndarray  # (years, 12) days with a value
    days: np.ndarray  # (years, 12) days of the month
    run: np.ndarray  # (years, 12) the longest run of missing days in the month

    @property
    def complete(self) -> np.ndarray:
        return self.known == self.days

    @property
    def enough(self) -> np.ndarray:
        """Enough days for a mean or a count: fewer than 11 missing, fewer than 5 in a row."""
        return (self.days - self.known < WMO_MISSING_DAYS) & (self.run < WMO_MISSING_RUN) & (self.known > 0)


def month_quality(axis: Axis, known: np.ndarray) -> MonthQuality:
    """Known days and the longest run of missing days of each month."""
    missing = ~known
    key = axis.month_key
    first = missing & np.r_[True, ~missing[:-1] | (key[1:] != key[:-1])]
    index = np.arange(len(known))
    run_start = np.maximum.accumulate(np.where(first, index, -1))
    here = np.where(missing, index - run_start + 1, 0)
    run = np.maximum.reduceat(here, axis.month_starts).reshape(axis.ny, 12)
    return MonthQuality(axis.per_month(known.astype(float)), axis.days_in_month, run)


def block_extreme(values: np.ndarray, starts: np.ndarray, largest: bool = True) -> tuple[np.ndarray, np.ndarray]:
    """The largest (or smallest) value of each block of days and the index of its first day.

    A block without values gives NaN and -1.
    """
    n = len(values)
    finite = np.isfinite(values)
    filled = np.where(finite, values, -np.inf if largest else np.inf)
    best = (np.maximum if largest else np.minimum).reduceat(filled, starts)
    lengths = np.diff(np.r_[starts, n])
    hit = finite & (filled == np.repeat(best, lengths))
    first = np.minimum.reduceat(np.where(hit, np.arange(n), n), starts)
    found = first < n
    return np.where(found, best, np.nan), np.where(found, first, -1)


def by_year_type(grid: np.ndarray, y0: int, year_type: str) -> tuple[np.ndarray, np.ndarray, list[int]]:
    """A (calendar years, 12) grid of monthly values as rows of the chosen year type.

    Returns the years, the grid (years, 12) in the order of the year and that order of
    months: I–XII for calendar years, XI–X for hydrological years (labelled by the year
    they end in; the first and last are partial and so missing).
    """
    if year_type == "calendar":
        return np.arange(y0, y0 + grid.shape[0]), grid, list(range(1, 13))
    fill = False if grid.dtype == bool else np.nan
    flat = np.r_[np.full(2, fill), grid.reshape(-1), np.full(10, fill)]
    return np.arange(y0, y0 + grid.shape[0] + 1), flat.reshape(-1, 12), [11, 12, *range(1, 11)]


def normal(values: np.ndarray, years: np.ndarray, lo: int, hi: int) -> tuple[float, int]:
    """The mean of `values` over the years lo..hi and how many years have a value.

    NaN when fewer than 80 % of the years of the period have a value (WMO-No. 1203, 4.4.2).
    """
    inside = (years >= lo) & (years <= hi)
    have = inside & np.isfinite(values)
    count = int(have.sum())
    if count == 0 or count < WMO_NORMAL_SHARE * (hi - lo + 1):
        return math.nan, count
    return float(values[have].mean()), count


def rolling_sum(values: np.ndarray, n: int) -> np.ndarray:
    """The sum of the n days ending on each day; NaN unless all n days are known."""
    out = np.full(len(values), np.nan)
    if n > len(values):
        return out
    known = np.isfinite(values)
    total = np.r_[0.0, np.cumsum(np.where(known, values, 0.0))]
    gaps = np.r_[0, np.cumsum(~known)]
    window = total[n:] - total[:-n]
    window[(gaps[n:] - gaps[:-n]) > 0] = np.nan
    out[n - 1 :] = np.round(window, 3)
    return out


# --- precipitation ---------------------------------------------------------------------


def precipitation_for_sums(daily: np.ndarray, flags: np.ndarray, values: np.ndarray, axis: Axis) -> tuple[np.ndarray, np.ndarray]:
    """Daily precipitation for sums: multi-day totals stand for the missing days before them.

    IMGW-PIB marks a total that follows days without a reading as `accumulated`
    (Obserwator's flag); WMO-No. 1203 (4.4.1 c) lets such a total stand for the missing days
    it covers when they are fewer than 5 consecutive days and fewer than 11 days of the
    month. Returns the array (the total on its day, 0 on the days it covers, NaN where
    unknown) and a (years, 12) mask of months whose sum it leaves missing (11 or more
    covered days).
    """
    sums = daily.copy()
    covered = np.zeros(len(daily), dtype=bool)
    for i in np.flatnonzero(flags == "accumulated"):
        j = i
        while j > 0 and flags[j - 1] == "missing":
            j -= 1
        if i - j + 1 < WMO_MISSING_RUN and np.isfinite(values[i]):
            sums[j:i] = 0.0
            sums[i] = values[i]
            covered[j : i + 1] = True
    too_many = axis.per_month(covered.astype(float)) >= WMO_MISSING_DAYS
    return sums, too_many


# --- spells ----------------------------------------------------------------------------


@dataclass(frozen=True)
class Runs:
    """Maximal runs of consecutive known days on which a condition holds."""

    start: np.ndarray  # index of the first day
    length: np.ndarray
    censored: np.ndarray  # next to a missing day or an end of the record: length is a lower bound


def runs(condition: np.ndarray, known: np.ndarray) -> Runs:
    """The runs of `condition` over known days; a missing day ends a run (censored)."""
    state = np.where(known, np.where(condition, 1, 0), 2)
    n = len(state)
    if n == 0:
        empty = np.zeros(0, dtype=int)
        return Runs(empty, empty, empty.astype(bool))
    change = np.flatnonzero(np.diff(state)) + 1
    starts = np.r_[0, change]
    ends = np.r_[change, n]
    chosen = state[starts] == 1
    start = starts[chosen]
    end = ends[chosen]
    before = np.where(start > 0, state[np.maximum(start - 1, 0)], 2)
    after = np.where(end < n, state[np.minimum(end, n - 1)], 2)
    return Runs(start, end - start, (before == 2) | (after == 2))


# --- SPI and relative precipitation ----------------------------------------------------


@dataclass(frozen=True)
class GammaFit:
    """A gamma distribution with a probability of zero (the SPI's mixed distribution)."""

    alpha: float
    beta: float
    q: float  # share of zeros in the calibration sample
    n: int


def fit_gamma_thom(sample: np.ndarray) -> GammaFit | None:
    """Fit the SPI's gamma distribution: Thom's (1958) approximation of maximum likelihood.

    A = ln(mean) - mean(ln x) over the positive values, alpha = (1 + sqrt(1 + 4A/3)) / (4A),
    beta = mean / alpha; q is the share of zeros (McKee et al. 1993; Edwards and McKee 1997;
    WMO-No. 1090, 2012). None when fewer than 3 positive values or all equal.
    """
    x = sample[np.isfinite(sample)]
    positive = x[x > 0]
    if len(positive) < 3:
        return None
    mean = float(positive.mean())
    a = math.log(mean) - float(np.log(positive).mean())
    if a <= 0:
        return None
    alpha = (1 + math.sqrt(1 + 4 * a / 3)) / (4 * a)
    return GammaFit(alpha, mean / alpha, 1 - len(positive) / len(x), len(x))


#: SPI limits as in the `climate_indices` package: beyond them the fit says nothing.
SPI_LIMIT = 3.09


def spi(values: np.ndarray, fit: GammaFit) -> np.ndarray:
    """SPI = Φ⁻¹(H(x)), H(x) = q + (1 - q) G(x; alpha, beta) (McKee et al. 1993), within ±3.09."""
    x = np.where(np.isfinite(values), np.maximum(values, 0.0), np.nan)
    cdf = fit.q + (1 - fit.q) * gammainc(fit.alpha, np.where(x > 0, x, 0.0) / fit.beta)
    cdf = np.where(x > 0, cdf, fit.q)
    with np.errstate(invalid="ignore", divide="ignore"):
        out = np.clip(ndtri(cdf), -SPI_LIMIT, SPI_LIMIT)
    return np.where(np.isfinite(x), out, np.nan)


#: SPI classes (McKee et al. 1993), driest first: upper limits of classes 0 to 5.
SPI_CLASSES = (
    "ekstremalnie suchy",
    "bardzo suchy",
    "umiarkowanie suchy",
    "normalny",
    "umiarkowanie wilgotny",
    "bardzo wilgotny",
    "ekstremalnie wilgotny",
)


def spi_class(value: float) -> int | None:
    """≤ −2, (−2, −1.5], (−1.5, −1], (−1, 1), [1, 1.5), [1.5, 2), ≥ 2 (McKee et al. 1993)."""
    if not math.isfinite(value):
        return None
    if value <= -2:
        return 0
    if value <= -1.5:
        return 1
    if value <= -1:
        return 2
    if value < 1:
        return 3
    if value < 1.5:
        return 4
    if value < 2:
        return 5
    return 6


def drought_events(values: np.ndarray) -> list[tuple[int, int, float, float]]:
    """Drought events of an SPI series (McKee et al. 1993).

    An event is a run of negative SPI that reaches −1 or less; it starts with the first
    negative value and ends with the last one before SPI turns non-negative (a missing value
    ends it too). Returns (first index, last index, minimum, magnitude = −ΣSPI).
    """
    events = []
    i = 0
    n = len(values)
    while i < n:
        if not (np.isfinite(values[i]) and values[i] < 0):
            i += 1
            continue
        j = i
        while j + 1 < n and np.isfinite(values[j + 1]) and values[j + 1] < 0:
            j += 1
        chunk = values[i : j + 1]
        if chunk.min() <= -1:
            events.append((i, j, float(chunk.min()), float(-chunk.sum())))
        i = j + 1
    return events


#: Kaczorowska's (1962) relative precipitation classes, driest first, as % of the normal.
KACZOROWSKA = (
    "skrajnie suchy",
    "bardzo suchy",
    "suchy",
    "normalny",
    "wilgotny",
    "bardzo wilgotny",
    "skrajnie wilgotny",
)


def kaczorowska_class(percent: float) -> int | None:
    """< 50, 50–74, 75–89, 90–110, 111–125, 126–150, > 150 % of the normal (whole percent).

    Kaczorowska Z. (1962) Opady w Polsce w przekroju wieloletnim. Prace Geograficzne IG PAN
    33; limits as given by Gąsiorek and Musiał (2011), Woda-Środowisko-Obszary Wiejskie
    11(4).
    """
    if not math.isfinite(percent):
        return None
    p = round(percent)
    for index, top in enumerate((49, 74, 89, 110, 125, 150)):
        if p <= top:
            return index
    return 6


# --- seasonality -----------------------------------------------------------------------


def pci(months: np.ndarray) -> float:
    """Oliver's (1980) precipitation concentration index: 100 Σp² / (Σp)² of 12 monthly sums."""
    total = float(np.sum(months))
    if not math.isfinite(total) or total <= 0:
        return math.nan
    return 100.0 * float(np.sum(months**2)) / total**2


PCI_CLASSES = ("równomierny", "umiarkowanie skoncentrowany", "nieregularny", "silnie nieregularny")


def pci_class(value: float) -> int | None:
    """≤ 10 uniform, ≤ 15 moderate, ≤ 20 irregular, > 20 strongly irregular (Oliver 1980)."""
    if not math.isfinite(value):
        return None
    for index, top in enumerate((10, 15, 20)):
        if value <= top:
            return index
    return 3


def seasonality_index(months: np.ndarray) -> float:
    """Walsh and Lawler's (1981) seasonality index: Σ|x_n − R/12| / R of 12 monthly sums."""
    total = float(np.sum(months))
    if not math.isfinite(total) or total <= 0:
        return math.nan
    return float(np.sum(np.abs(months - total / 12))) / total


SI_CLASSES = (
    "bardzo równomierny",
    "równomierny z porą wilgotniejszą",
    "raczej sezonowy z krótką porą suchszą",
    "sezonowy",
    "wyraźnie sezonowy z długą porą suchą",
    "większość opadu w 3 miesiącach lub krócej",
    "skrajnie sezonowy",
)


def si_class(value: float) -> int | None:
    """Walsh and Lawler (1981): < 0.20, < 0.40, < 0.60, < 0.80, < 1.00, < 1.20, ≥ 1.20."""
    if not math.isfinite(value):
        return None
    for index, top in enumerate((0.2, 0.4, 0.6, 0.8, 1.0, 1.2)):
        if value < top:
            return index
    return 6


def markham(months: np.ndarray) -> tuple[float, float]:
    """Markham's (1970) vector of 12 monthly sums: concentration (0–1) and mean month.

    Each month is a vector of its sum at the angle of its middle (30° per month); the
    resultant's length over the total is the concentration, its angle the mean timing,
    returned as a month position (1.0 = middle of January, 7.5 = end of July).
    """
    total = float(np.sum(months))
    if not math.isfinite(total) or total <= 0:
        return math.nan, math.nan
    angle = np.deg2rad(np.arange(12) * 30.0 + 15.0)
    x = float(np.sum(months * np.sin(angle)))
    y = float(np.sum(months * np.cos(angle)))
    concentration = math.hypot(x, y) / total
    degrees = math.degrees(math.atan2(x, y)) % 360.0
    return concentration, degrees / 30.0 + 0.5


# --- temperature -----------------------------------------------------------------------


@dataclass(frozen=True)
class Harmonics:
    """A fit of the annual cycle: the mean and the first two harmonics."""

    mean: float
    amplitude: tuple[float, float]
    peak: tuple[float, float]  # day of the year (1 = 1 January) of each harmonic's (first) maximum
    explained: tuple[float, float]  # share of the variance explained by harmonic 1 and by 2
    fitted: np.ndarray = field(repr=False)
    first: np.ndarray = field(repr=False)  # the mean plus the first harmonic only


def harmonic_fit(t: np.ndarray, y: np.ndarray, days: float = 365.0) -> Harmonics | None:
    """Least-squares fit y = A0 + Σ_k a_k cos(2πkt) + b_k sin(2πkt), k = 1, 2.

    `t` is the fraction of the year at the middle of each day ((day of year − 0.5) / length
    of the year). Amplitude C_k = √(a_k² + b_k²), phase φ_k = atan2(b_k, a_k): the k-th
    harmonic peaks at t = φ_k / (2πk), given as a day of the year of `days` days. The shares
    of the variance are those of the sequential least-squares fits (R² with the first
    harmonic, then the gain of the second), which equal C_k²/2 / var(y) for a full year of
    days (harmonic analysis of the annual cycle, e.g. Wilks 2011, Statistical Methods in the
    Atmospheric Sciences, 8.4).
    """
    ok = np.isfinite(y) & np.isfinite(t)
    if ok.sum() < 30:
        return None
    t = t[ok]
    y = y[ok]
    w = 2 * np.pi * t
    columns = [np.ones_like(t), np.cos(w), np.sin(w), np.cos(2 * w), np.sin(2 * w)]
    design = np.column_stack(columns)
    total = float(np.sum((y - y.mean()) ** 2))
    if total <= 0:
        return None
    coef1, *_ = np.linalg.lstsq(design[:, :3], y, rcond=None)
    coef2, *_ = np.linalg.lstsq(design, y, rcond=None)
    r2_1 = 1 - float(np.sum((y - design[:, :3] @ coef1) ** 2)) / total
    r2_2 = 1 - float(np.sum((y - design @ coef2) ** 2)) / total
    a0, a1, b1, a2, b2 = (float(c) for c in coef2)
    c1 = math.hypot(a1, b1)
    c2 = math.hypot(a2, b2)
    t1 = (math.atan2(b1, a1) / (2 * np.pi)) % 1.0
    t2 = (math.atan2(b2, a2) / (4 * np.pi)) % 0.5
    return Harmonics(
        a0,
        (c1, c2),
        (t1 * days + 0.5, t2 * days + 0.5),
        (r2_1, r2_2 - r2_1),
        design @ coef2,
        design[:, :3] @ np.array([a0, a1, b1]),
    )


#: Sielianinov's hydrothermal coefficient classes (Skowera and Puła 2004), driest first.
SIELIANINOV = (
    "skrajnie suchy",
    "bardzo suchy",
    "suchy",
    "dość suchy",
    "optymalny",
    "dość wilgotny",
    "wilgotny",
    "bardzo wilgotny",
    "skrajnie wilgotny",
)


def sielianinov_class(k: float) -> int | None:
    """Class of k: ≤ 0.4, ≤ 0.7, ≤ 1.0, ≤ 1.3, ≤ 1.6, ≤ 2.0, ≤ 2.5, ≤ 3.0, > 3.0 (Skowera and Puła 2004)."""
    if not math.isfinite(k):
        return None
    for index, top in enumerate((0.4, 0.7, 1.0, 1.3, 1.6, 2.0, 2.5, 3.0)):
        if k <= top:
            return index
    return 8


#: De Martonne's (1926) aridity index classes as given by Baltas (2007).
DE_MARTONNE = ("suchy", "półsuchy", "śródziemnomorski", "półwilgotny", "wilgotny", "bardzo wilgotny", "skrajnie wilgotny")


def de_martonne_class(index: float) -> int | None:
    """< 10, < 20, < 24, < 28, < 35, ≤ 55, > 55 (Baltas 2007, Meteorological Applications 14)."""
    if not math.isfinite(index):
        return None
    for position, top in enumerate((10, 20, 24, 28, 35)):
        if index < top:
            return position
    return 5 if index <= 55 else 6


# --- trends ----------------------------------------------------------------------------


def sen_slope(years: np.ndarray, values: np.ndarray, var_s: float, alpha: float = 0.05) -> dict[str, float] | None:
    """Sen's (1968) slope with its confidence interval (Gilbert 1987, section 16.5).

    The slope is the median of (x_j − x_i) / (t_j − t_i) over all pairs i < j; the interval
    takes the order statistics M1 = (N − C)/2 and M2 = (N + C)/2 + 1 of the N sorted pair
    slopes (interpolated between ranks), C = z_{1−α/2} √Var(S) with Var(S) from the
    Mann–Kendall test. The intercept is median(x) − slope · median(t) (Conover 1980).
    """
    ok = np.isfinite(values)
    t = years[ok].astype(float)
    x = values[ok].astype(float)
    if len(x) < 3:
        return None
    i, j = np.triu_indices(len(x), k=1)
    slopes = np.sort((x[j] - x[i]) / (t[j] - t[i]))
    count = len(slopes)
    slope = float(np.median(slopes))
    c = float(ndtri(1 - alpha / 2)) * math.sqrt(max(var_s, 0.0))
    ranks = np.arange(1, count + 1)
    lo_rank = (count - c) / 2
    hi_rank = (count + c) / 2 + 1
    lo = float(np.interp(lo_rank, ranks, slopes)) if 1 <= lo_rank <= count else math.nan
    hi = float(np.interp(hi_rank, ranks, slopes)) if 1 <= hi_rank <= count else math.nan
    return {
        "slope": slope,
        "lower": lo,
        "upper": hi,
        "intercept": float(np.median(x) - slope * np.median(t)),
        "pairs": count,
    }


# --- warming stripes ---------------------------------------------------------------------

#: Hawkins's colours, coldest first: the 8 most saturated of ColorBrewer's 9-class sequential
#: Blues (darkest first) and Reds (lightest first), as the stripes of showyourstripes.info use
#: them. ColorBrewer colour schemes: Copyright (c) 2002 Cynthia Brewer, Mark Harrower, and The
#: Pennsylvania State University, Apache License 2.0 („Apache-Style Software License for
#: ColorBrewer software and ColorBrewer Color Schemes”). This product includes color
#: specifications and designs developed by Cynthia Brewer (http://colorbrewer.org/).
STRIPE_COLOURS = (
    "#08306b", "#08519c", "#2171b5", "#4292c6", "#6baed6", "#9ecae1", "#c6dbef", "#deebf7",
    "#fee0d2", "#fcbba1", "#fc9272", "#fb6a4a", "#ef3b2c", "#cb181d", "#a50f15", "#67000d",
)  # fmt: skip
#: The scales of showyourstripes.info's FAQ „How have these graphics been made?”, by the
#: version of the page: (centre period, spread period, multiple of the standard deviation).
#: 2025 (current page, data to the end of 2025): „the average temperature in 1961-2010 is set as
#: the boundary between blue and red colours, and the colour scale varies from +/- 3.0 standard
#: deviations of the annual average temperatures between 1901-2000”. 2019 (the page of June
#: 2019, web.archive.org 20190617215129): the same with 1971-2000 and +/- 2.6.
STRIPE_SCALES = {
    "2025": ((1961, 2010), (1901, 2000), 3.0),
    "2019": ((1971, 2000), (1901, 2000), 2.6),
}


@dataclass(frozen=True)
class StripeScale:
    """The colour scale of warming stripes: centre ± k standard deviations, in 16 equal bins."""

    centre: float  # mean annual value of the centre period
    sd: float  # standard deviation of the annual values of the spread period
    k: float

    @property
    def lo(self) -> float:
        return self.centre - self.k * self.sd

    @property
    def hi(self) -> float:
        return self.centre + self.k * self.sd

    def edges(self) -> np.ndarray:
        """The 17 bounds of the 16 colours, coldest first."""
        return np.linspace(self.lo, self.hi, len(STRIPE_COLOURS) + 1)

    def colour(self, value: float) -> int | None:
        """The index of a value's colour (0 = darkest blue); beyond the scale, its end colour."""
        if not math.isfinite(value):
            return None
        n = len(STRIPE_COLOURS)
        return min(max(int(math.floor((value - self.lo) / (self.hi - self.lo) * n)), 0), n - 1)


def period_sd(values: np.ndarray, years: np.ndarray, lo: int, hi: int) -> tuple[float, int]:
    """The sample standard deviation (n − 1) of `values` over the years lo..hi and their count.

    NaN under the 80 % rule of a normal (WMO-No. 1203, 4.4.2) or below 2 values. The FAQ of
    showyourstripes.info does not say which estimator it uses; for 100 years the two differ
    by 0.5 %.
    """
    inside = (years >= lo) & (years <= hi)
    have = inside & np.isfinite(values)
    count = int(have.sum())
    if count < 2 or count < WMO_NORMAL_SHARE * (hi - lo + 1):
        return math.nan, count
    return float(np.std(values[have], ddof=1)), count
