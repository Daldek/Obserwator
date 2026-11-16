/**
 * Scales and ticks of the charts: pure functions without the DOM or Preact (plan D9, D12).
 *
 * A scale maps a domain value to a coordinate of the SVG's viewBox and back
 * (`invert`). Linear and log scales map values; the time scale is linear in
 * minutes with ticks on whole hours; the date scale (Obserwator's mockup) is linear
 * in day numbers (days since 1970-01-01) with ticks on whole years, months or days;
 * the Gumbel scale maps an exceedance
 * probability in percent through the reduced variate u = −ln(−ln(1 − p/100)),
 * so a Gumbel distribution is a straight line (probability paper). Tick labels
 * are numbers and dates of the page's language (`lang()` of i18n.js, through `Intl`):
 * a decimal comma or point, thousands grouped from five digits (so years read
 * "1951"), the minus sign U+2212, month names and day dates as the language writes them.
 */

import { fmtDate, lang } from "../i18n.js";

/** The minus sign of the labels. */
export const MINUS = "\u2212";

/** The `Intl` locale of the page's language. */
function locale() {
  return lang() === "pl" ? "pl-PL" : "en-GB";
}

/**
 * The smallest and the largest of the values a test keeps, in one pass: spreading a long
 * series into `Math.min`/`Math.max` overflows the call stack (a long unit hydrograph).
 *
 * @param {Iterable<number>} values the values
 * @param {(value: number) => boolean} [keep=Number.isFinite] which values count
 * @returns {[number, number] | null} [smallest, largest], null when none counts
 */
export function extent(values, keep = Number.isFinite) {
  let lo = Infinity;
  let hi = -Infinity;
  for (const value of values) {
    if (!keep(value)) continue;
    if (value < lo) lo = value;
    if (value > hi) hi = value;
  }
  return lo <= hi ? [lo, hi] : null;
}

const FORMATTERS = new Map();

/**
 * A cached `Intl` format of the page's language.
 *
 * @param {string} name what it formats (the cache's key, with the language)
 * @param {() => Intl.NumberFormat | Intl.DateTimeFormat} make builds it for `locale()`
 */
function cached(name, make) {
  const key = `${lang()}:${name}`;
  let format = FORMATTERS.get(key);
  if (!format) {
    format = make();
    FORMATTERS.set(key, format);
  }
  return format;
}

/**
 * Format a number in the page's language with a fixed number of decimals.
 *
 * @param {number} value the number
 * @param {number} [digits=0] decimals shown
 * @returns {string} e.g. "1046 213" with a non-breaking space (Polish), "0,25" or "0.25",
 *   "−3"; a value that rounds to zero has no sign; "–" when not finite
 */
export function formatNumber(value, digits = 0) {
  if (!Number.isFinite(value)) return "–";
  const format = cached(`n${digits}`, () =>
    new Intl.NumberFormat(locale(), {
      minimumFractionDigits: digits,
      maximumFractionDigits: digits,
      useGrouping: "min2",
    }),
  );
  const shown = Number(value.toFixed(Math.min(100, digits))) === 0 ? 0 : value;
  return format.format(shown).replace("-", MINUS);
}

/**
 * Format a time in minutes as hours and minutes.
 *
 * @param {number} minutes the time [min]
 * @returns {string} e.g. "6:20" for 380, "0:05" for 5
 */
export function formatTime(minutes) {
  const total = Math.round(minutes);
  const sign = total < 0 ? MINUS : "";
  const abs = Math.abs(total);
  return `${sign}${Math.floor(abs / 60)}:${String(abs % 60).padStart(2, "0")}`;
}

/**
 * Return the decimals that show every multiple of a step exactly.
 *
 * @param {number} step a tick step, e.g. 0.25
 * @returns {number} 2 for 0.25, 1 for 2.5, 0 for 50
 */
export function stepDigits(step) {
  for (let digits = 0; digits < 10; digits += 1) {
    const scaled = step * 10 ** digits;
    if (Math.abs(scaled - Math.round(scaled)) < 1e-9 * Math.max(1, scaled)) return digits;
  }
  return 10;
}

const NICE = [1, 2, 2.5, 5, 10];

/**
 * Return the smallest rounded step (1, 2, 2.5 or 5 times a power of ten) that
 * divides a span into at most `count` intervals.
 *
 * @param {number} span the span of the domain (> 0)
 * @param {number} [count=6] the most intervals
 * @returns {number} the step
 */
export function niceStep(span, count = 6) {
  if (!(span > 0)) return 1;
  const raw = span / Math.max(1, count);
  const power = 10 ** Math.floor(Math.log10(raw));
  for (const factor of NICE) {
    const step = factor * power;
    if (span / step <= count + 1e-9) return step;
  }
  return 10 * power;
}

/** Round away the binary noise of a multiple of a step. */
function clean(value, digits) {
  return Number(value.toFixed(Math.min(12, digits + 2)));
}

/**
 * Return the ticks of a linear domain at multiples of a step.
 *
 * @param {number} min the start of the domain
 * @param {number} max the end of the domain
 * @param {number} step the step
 * @returns {{value: number, label: string}[]} the ticks within [min, max]
 */
export function linearTicks(min, max, step) {
  const digits = stepDigits(step);
  const ticks = [];
  const first = Math.ceil(min / step - 1e-9);
  const last = Math.floor(max / step + 1e-9);
  for (let k = first; k <= last; k += 1) {
    const value = clean(k * step, digits);
    ticks.push({ value, label: formatNumber(value, digits) });
  }
  return ticks;
}

/**
 * Round a linear domain outwards to rounded ticks.
 *
 * The domain covers the values and, with `zero`, zero; `pad` adds a share of
 * the span above the largest value (the headroom of the mockup's charts) and, when
 * the domain reaches below zero, below the smallest one. Negative values are drawn
 * (air temperatures, anomalies, day numbers before 1970); a quantity that is never
 * negative keeps `zero` so its axis starts at 0.
 *
 * @param {number[]} values the values to cover (non-finite ones are skipped)
 * @param {{count?: number, zero?: boolean, pad?: number, min?: number, max?: number}} [options]
 *   `min` and `max` fix an end instead of rounding it
 * @returns {{min: number, max: number, step: number, ticks: {value: number, label: string}[]}}
 */
export function niceDomain(values, options = {}) {
  const { count = 6, zero = true, pad = 0.08 } = options;
  const range = extent(values);
  let lo = options.min ?? (range ? range[0] : 0);
  let hi = options.max ?? (range ? range[1] : 1);
  if (zero && options.min === undefined) lo = Math.min(0, lo);
  if (zero && options.max === undefined) hi = Math.max(0, hi);
  if (hi <= lo) hi = lo + (lo === 0 ? 1 : Math.abs(lo) * 0.1);
  const span = hi - lo;
  if (options.max === undefined) hi += pad * span;
  if (options.min === undefined && lo < 0) lo -= pad * span;
  const step = niceStep(hi - lo, count);
  const digits = stepDigits(step);
  const min = options.min === undefined ? clean(Math.floor(lo / step + 1e-9) * step, digits) : lo;
  const max = options.max ?? clean(Math.ceil(hi / step - 1e-9) * step, digits);
  return { min, max, step, ticks: linearTicks(min, max, step) };
}

/**
 * Return the ticks of a log domain: each power of ten, and 2 and 5 times it
 * when the domain spans at most two decades.
 *
 * @param {number} min the start of the domain (> 0)
 * @param {number} max the end of the domain (> min)
 * @returns {{value: number, label: string}[]} the ticks within [min, max]
 */
export function logTicks(min, max) {
  const first = Math.floor(Math.log10(min) + 1e-9);
  const last = Math.ceil(Math.log10(max) - 1e-9);
  const factors = last - first <= 2 ? [1, 2, 5] : [1];
  const ticks = [];
  for (let power = first; power <= last; power += 1) {
    for (const factor of factors) {
      const value = Number((factor * 10 ** power).toPrecision(12));
      if (value < min * (1 - 1e-9) || value > max * (1 + 1e-9)) continue;
      ticks.push({ value, label: formatNumber(value, Math.max(0, -power)) });
    }
  }
  return ticks;
}

/**
 * Round a log domain outwards to powers of ten.
 *
 * @param {number[]} values the values to cover (values ≤ 0 are skipped)
 * @returns {{min: number, max: number, ticks: {value: number, label: string}[]}}
 */
export function logDomain(values) {
  const range = extent(values, (value) => Number.isFinite(value) && value > 0);
  const lo = range ? range[0] : 1;
  const hi = range ? range[1] : 10;
  const min = 10 ** Math.floor(Math.log10(lo) + 1e-9);
  let max = 10 ** Math.ceil(Math.log10(hi) - 1e-9);
  if (max <= min) max = min * 10;
  return { min, max, ticks: logTicks(min, max) };
}

// Steps that are whole tenths of an hour or 15 min multiples, so the labels in hours are exact
const TIME_STEPS = [6, 12, 15, 30, 60, 120, 180, 240, 360, 720, 1440, 2880, 10080];

/**
 * Return the time ticks of a domain in minutes, labelled in hours.
 *
 * @param {number} min the start [min]
 * @param {number} max the end [min]
 * @param {number} [count=13] the most ticks
 * @returns {{step: number, ticks: {value: number, label: string}[]}} `step` in minutes
 */
export function timeTicks(min, max, count = 13) {
  const span = Math.max(max - min, 1);
  // Beyond the steps: whole weeks, still at most `count` ticks (a unit hydrograph of months)
  const week = TIME_STEPS.at(-1);
  const step = TIME_STEPS.find((candidate) => span / candidate <= count - 1) ?? week * Math.ceil(span / (week * (count - 1)));
  const digits = stepDigits(step / 60);
  const ticks = [];
  for (let k = Math.ceil(min / step - 1e-9); k * step <= max + 1e-9; k += 1) {
    ticks.push({ value: k * step, label: formatNumber((k * step) / 60, digits) });
  }
  return { step, ticks };
}

/**
 * Round a time domain in minutes: it starts at the first value (never before 0) and
 * ends at the last one rounded up to the tick step.
 *
 * @param {number[]} values the times [min]
 * @param {{min?: number, max?: number, count?: number}} [options] fixed ends
 * @returns {{min: number, max: number, step: number, ticks: {value: number, label: string}[]}}
 */
export function timeDomain(values, options = {}) {
  const range = extent(values);
  const lo = Math.max(0, options.min ?? (range ? range[0] : 0));
  let hi = options.max ?? (range ? range[1] : 60);
  if (hi <= lo) hi = lo + 60;
  const { step } = timeTicks(lo, hi, options.count);
  const max = options.max ?? Math.ceil(hi / step - 1e-9) * step;
  return { min: lo, max, ...timeTicks(lo, max, options.count) };
}

/** Milliseconds of a day: the `date` scale's x is a day number, days since 1970-01-01. */
const DAY_MS = 86400000;

/** The `Date` of a day number (UTC midnight). */
function dateOfDay(day) {
  return new Date(Math.round(day) * DAY_MS);
}

/**
 * The short name of a month in the page's language.
 *
 * @param {number} month 0 (January) to 11
 * @param {number} [year] given: the name with the year ("sty 1952", "Jan 1952")
 * @returns {string}
 */
export function monthName(month, year) {
  const withYear = year !== undefined;
  const format = cached(withYear ? "my" : "m", () =>
    new Intl.DateTimeFormat(locale(), { month: "short", ...(withYear ? { year: "numeric" } : {}), timeZone: "UTC" }),
  );
  return format.format(new Date(Date.UTC(withYear ? year : 2001, month, 1))).replace(/\.$/, "");
}

/**
 * A day number as the page's language writes a date (the readout of a date axis).
 *
 * @param {number} day days since 1970-01-01 (negative before)
 * @returns {string} e.g. "01.11.1950" (Polish) or "01/11/1950"
 */
export function formatDay(day) {
  return fmtDate(dateOfDay(day).toISOString().slice(0, 10));
}

/**
 * A day number as its day and month, without the year (a tick of a date axis).
 *
 * @param {number} day days since 1970-01-01
 * @returns {string} e.g. "12.03" (Polish) or "12/03"
 */
export function formatDayMonth(day) {
  const format = cached("dm", () => new Intl.DateTimeFormat(locale(), { day: "2-digit", month: "2-digit", timeZone: "UTC" }));
  return format.format(dateOfDay(day));
}

/** The day number of a calendar day (month 0-based, may overflow into the next years). */
function dayOf(year, month, day = 1) {
  return Math.round(Date.UTC(year, month, day) / DAY_MS);
}

// Steps of a date axis, finest first: [unit, multiple]; the average length of each unit
const DATE_STEPS = [
  ["day", 1], ["day", 2], ["day", 7], ["day", 14],
  ["month", 1], ["month", 2], ["month", 3], ["month", 6],
  ["year", 1], ["year", 2], ["year", 5], ["year", 10], ["year", 20], ["year", 25], ["year", 50], ["year", 100],
];
const UNIT_DAYS = { day: 1, month: 30.44, year: 365.25 };

/**
 * Return the ticks of a date domain in day numbers: whole days, weeks (Mondays), months
 * or years, the finest step that keeps at most `count` ticks. Years are labelled
 * "1951"; months by their short name in the page's language, with the year at January
 * and on the first tick ("sty 1952", "Jan 1952"); days by day and month ("12.03",
 * "12/03"), with the year on the first tick.
 *
 * @param {number} min the first day number
 * @param {number} max the last day number
 * @param {number} [count=8] the most ticks
 * @returns {{step: [string, number], ticks: {value: number, label: string}[]}}
 */
export function dateTicks(min, max, count = 8) {
  const span = Math.max(max - min, 1);
  const most = Math.max(2, count);
  const step =
    DATE_STEPS.find(([unit, times]) => span / (UNIT_DAYS[unit] * times) <= most - 1) ??
    ["year", 100 * Math.ceil(span / (UNIT_DAYS.year * 100 * (most - 1)))];
  const [unit, times] = step;
  const ticks = [];
  const start = dateOfDay(Math.floor(min));
  if (unit === "year") {
    let year = Math.ceil(start.getUTCFullYear() / times) * times;
    if (dayOf(year, 0) < min) year += times;
    for (; dayOf(year, 0) <= max; year += times) ticks.push({ value: dayOf(year, 0), label: String(year) });
  } else if (unit === "month") {
    let index = start.getUTCFullYear() * 12 + Math.ceil(start.getUTCMonth() / times) * times;
    if (dayOf(Math.floor(index / 12), index % 12) < min) index += times;
    for (; dayOf(Math.floor(index / 12), index % 12) <= max; index += times) {
      const year = Math.floor(index / 12);
      const month = index % 12;
      const label = month === 0 || !ticks.length ? monthName(month, year) : monthName(month);
      ticks.push({ value: dayOf(year, month), label });
    }
  } else {
    // Weeks start on Mondays: day 4 (1970-01-05) is one
    const offset = times % 7 === 0 ? 4 : 0;
    for (let day = Math.ceil((min - offset) / times) * times + offset; day <= max; day += times) {
      ticks.push({ value: day, label: ticks.length ? formatDayMonth(day) : formatDay(day) });
    }
  }
  return { step, ticks };
}

/**
 * A date domain in day numbers: the first and the last value (or the fixed ends), not
 * rounded, with the ticks of `dateTicks`.
 *
 * @param {number[]} values day numbers
 * @param {{min?: number, max?: number, count?: number}} [options] fixed ends and the most ticks
 * @returns {{min: number, max: number, step: [string, number], ticks: {value: number, label: string}[]}}
 */
export function dateDomain(values, options = {}) {
  const range = extent(values);
  const today = Math.floor(Date.now() / DAY_MS);
  const min = options.min ?? (range ? range[0] : today - 365);
  let max = options.max ?? (range ? range[1] : today);
  if (max <= min) max = min + 1;
  return { min, max, ...dateTicks(min, max, options.count) };
}

/**
 * The reduced variate of the Gumbel distribution for an exceedance probability.
 *
 * @param {number} percent the exceedance probability p [%], 0 < p < 100
 * @returns {number} u = −ln(−ln(1 − p/100))
 */
export function reducedVariate(percent) {
  return -Math.log(-Math.log(1 - percent / 100));
}

/**
 * The exceedance probability of a reduced variate (the inverse of `reducedVariate`).
 *
 * @param {number} variate u
 * @returns {number} p [%]
 */
export function exceedanceFromVariate(variate) {
  return 100 * (1 - Math.exp(-Math.exp(-variate)));
}

/** Exceedance probabilities [%] of the probability axis; the first ones win a crowded axis. */
const GUMBEL_MAJOR = [50, 10, 1, 0.1, 0.01, 90, 99];
const GUMBEL_MINOR = [20, 5, 2, 0.5, 0.2, 0.05, 0.02, 80, 95, 98, 99.9];

/**
 * Return the ticks of a Gumbel probability axis.
 *
 * Each tick is an exceedance probability p [%] labelled with p and with the
 * return period T = 100 / p [years]. A tick nearer than `gap` (in the units
 * of the scale's range) to a kept one is dropped, the major ones kept first.
 *
 * @param {(percent: number) => number} scale a Gumbel scale (see `gumbelScale`)
 * @param {number} [gap=30] the least distance between ticks
 * @returns {{value: number, label: string, sub: string}[]} ordered by position
 */
export function gumbelTicks(scale, gap = 30) {
  const [left, right] = scale.domain;
  const lo = Math.min(left, right);
  const hi = Math.max(left, right);
  const kept = [];
  for (const percent of [...GUMBEL_MAJOR, ...GUMBEL_MINOR]) {
    if (percent < lo || percent > hi) continue;
    const at = scale(percent);
    if (Math.abs(at - scale.range[0]) < gap / 2) continue; // beside the row labels
    if (kept.some((tick) => Math.abs(scale(tick) - at) < gap)) continue;
    kept.push(percent);
  }
  kept.sort((a, b) => scale(a) - scale(b));
  return kept.map((percent) => {
    const years = 100 / percent;
    const yearsDigits = Math.abs(years - Math.round(years)) < 1e-9 ? 0 : 2;
    return {
      value: percent,
      label: formatNumber(percent, stepDigits(percent)),
      sub: formatNumber(years, yearsDigits),
    };
  });
}

/**
 * Return a Gumbel domain in exceedance probability [%] that covers the values
 * with a margin of `pad` of the reduced variate's span on each side.
 *
 * @param {number[]} values exceedance probabilities [%]
 * @param {{pad?: number}} [options]
 * @returns {[number, number]} [left, right]: the larger probability first
 */
export function gumbelDomain(values, options = {}) {
  const { pad = 0.04 } = options;
  const range = extent(
    values.filter((percent) => Number.isFinite(percent) && percent > 0 && percent < 100).map(reducedVariate),
  );
  let lo = range ? range[0] : reducedVariate(90);
  let hi = range ? range[1] : reducedVariate(1);
  if (hi - lo < 1) {
    lo -= 0.5;
    hi += 0.5;
  }
  const margin = pad * (hi - lo);
  return [exceedanceFromVariate(lo - margin), exceedanceFromVariate(hi + margin)];
}

function attach(map, type, domain, range, invert) {
  map.type = type;
  map.domain = domain;
  map.range = range;
  map.invert = invert;
  return map;
}

/**
 * A linear scale.
 *
 * @param {[number, number]} domain [d0, d1]
 * @param {[number, number]} range [r0, r1]
 * @returns {((value: number) => number) & {type: string, domain: number[], range: number[], invert: (at: number) => number}}
 */
export function linearScale([d0, d1], [r0, r1]) {
  const k = d1 === d0 ? 0 : (r1 - r0) / (d1 - d0);
  return attach(
    (value) => r0 + (value - d0) * k,
    "linear",
    [d0, d1],
    [r0, r1],
    (at) => (k === 0 ? d0 : d0 + (at - r0) / k),
  );
}

/**
 * A log (base 10) scale; values ≤ 0 map to NaN.
 *
 * @param {[number, number]} domain [d0, d1], both > 0
 * @param {[number, number]} range [r0, r1]
 * @returns {((value: number) => number) & {type: string, domain: number[], range: number[], invert: (at: number) => number}}
 */
export function logScale([d0, d1], [r0, r1]) {
  const l0 = Math.log10(d0);
  const k = (r1 - r0) / (Math.log10(d1) - l0 || 1);
  return attach(
    (value) => (value > 0 ? r0 + (Math.log10(value) - l0) * k : NaN),
    "log",
    [d0, d1],
    [r0, r1],
    (at) => 10 ** (l0 + (at - r0) / k),
  );
}

/**
 * A Gumbel probability scale: linear in the reduced variate.
 *
 * @param {[number, number]} domain exceedance probabilities [%], e.g. [99, 0.1]
 * @param {[number, number]} range [r0, r1]
 * @returns {((percent: number) => number) & {type: string, domain: number[], range: number[], invert: (at: number) => number}}
 */
export function gumbelScale([p0, p1], [r0, r1]) {
  const u0 = reducedVariate(p0);
  const k = (r1 - r0) / (reducedVariate(p1) - u0 || 1);
  return attach(
    (percent) => (percent > 0 && percent < 100 ? r0 + (reducedVariate(percent) - u0) * k : NaN),
    "gumbel",
    [p0, p1],
    [r0, r1],
    (at) => exceedanceFromVariate(u0 + (at - r0) / k),
  );
}
