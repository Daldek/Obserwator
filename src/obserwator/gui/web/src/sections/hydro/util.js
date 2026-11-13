// Helpers of the hydrological sections, shared by both halves of the area (HydroA, HydroB):
// the hydrological-year axis, number formats by variable, the station's record of a
// variable, options kept per station, the year range, the daily series and the hand-off.

import { api } from "../../api.js";
import { fmt, fmtDate, html, t, unit, useEffect, useState } from "../../lib.js";
import { variableInfo } from "../../words.js";
import { Seg, YearRange } from "../common.js";
import { HandoffButtons } from "../handoff.js";

/** Months of the hydrological year, November first. */
export const HYDRO_MONTHS = ["XI", "XII", "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X"];
/** Calendar months 1-12 as Roman numerals. */
export const ROMAN = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII"];
/** The first day of each month in the hydrological year (1 = 1 XI, a 365-day year). */
const MONTH_STARTS = [1, 31, 62, 93, 121, 152, 182, 213, 243, 274, 305, 335];
/** Ticks of an x axis over the days of the hydrological year. */
export const DOY_TICKS = HYDRO_MONTHS.map((label, at) => ({ value: MONTH_STARTS[at], label }));

/** A day of the hydrological year (1 = 1 XI) as „12 III”. */
export function doyLabel(day) {
  const whole = Math.min(Math.max(Math.round(day), 1), 366);
  let at = 0;
  while (at < 11 && MONTH_STARTS[at + 1] <= whole) at += 1;
  return `${whole - MONTH_STARTS[at] + 1} ${HYDRO_MONTHS[at]}`;
}

/** The daily hydrological datasets, IMGW-PIB's first (a station has one of them). */
export const HYDRO_DAILY = ["pl.imgw.hydro_daily", "cz.chmi.hydro_daily"];
/** IMGW-PIB's half-year and annual characteristics. */
export const HALF_YEARS = "pl.imgw.hydro_semiannual";

/** Units of the hydrological variables, as shown. */
export const UNITS = { H: "cm", Q: "m³/s", T: "°C" };

/** A variable with its name in the page's language: „Q · przepływ”. */
export function variableLabel(variable) {
  return `${variable} · ${variableInfo(variable).label}`;
}

/** A value of H (cm, whole), T (one decimal) or Q (digits by size). */
export function fmtV(value, variable) {
  if (value === null || value === undefined || !Number.isFinite(value)) return "–";
  if (variable === "H") return fmt(value, 0);
  if (variable === "T") return fmt(value, 1);
  const size = Math.abs(value);
  return fmt(value, size >= 100 ? 0 : size >= 10 ? 1 : size >= 1 ? 2 : 3);
}

/** A value with its unit, "–" when missing. */
export function withUnit(value, variable, u) {
  const text = fmtV(value, variable);
  return text === "–" ? text : `${text}\u00a0${u ? unit(u) : UNITS[variable] || ""}`;
}

/** Digits of a variable's readout on a chart. */
export function digitsOf(variable) {
  return variable === "H" ? 0 : variable === "T" ? 1 : undefined;
}

/** A short date „12.03.1997”, or „–”. */
export const date = fmtDate;

/**
 * Options of a section kept per station: they start again from `initial` on another station.
 *
 * @param {object} initial the options (strings or numbers; undefined is left out of the query)
 * @param {string} code the station
 * @returns {[object, (patch: object) => void]}
 */
export function useOptions(initial, code) {
  const [state, setState] = useState({ code, values: initial });
  const values = state.code === code ? state.values : initial;
  return [values, (patch) => setState({ code, values: { ...values, ...patch } })];
}

/** The hydrological year (XI–X, named after the year it ends in) of an ISO date. */
export function hydroYear(iso) {
  const year = +iso.slice(0, 4);
  return +iso.slice(5, 7) >= 11 ? year + 1 : year;
}

/** The station's daily hydrological dataset (`pl.imgw.hydro_daily` or `cz.chmi.hydro_daily`), or null. */
export function dailyDataset(station) {
  const found = (station.datasets || []).find((item) => HYDRO_DAILY.includes(item.dataset));
  return found ? found.dataset : null;
}

/**
 * The analysis ids that apply to a station, from the panel's `analyses` prop (the list of
 * `api/analyses/{code}`, or its whole answer).
 *
 * @param {object[]|{analyses: object[]}|null|undefined} analyses
 * @returns {Set<string>}
 */
export function analysisIds(analyses) {
  const list = Array.isArray(analyses) ? analyses : (analyses && analyses.analyses) || [];
  return new Set(list.map((item) => item.analysis));
}

/**
 * The hydrological years of a station's record of variables in a dataset, from the station's
 * document (the first and last day with a value of each variable): the years all of them
 * cover. A half-year dataset's variables (`Q_max@winter`) count for their variable.
 *
 * @param {object} station `api.station(code)`
 * @param {string[]} variables e.g. ["Q"], ["H", "Q"]
 * @param {string} [dataset] the dataset; the station's daily one by default
 * @returns {{first: number, last: number}|null}
 */
export function recordYears(station, variables, dataset) {
  const key = dataset || dailyDataset(station);
  const found = (station.datasets || []).find((item) => item.dataset === key);
  if (!found) return null;
  let first = -Infinity;
  let last = Infinity;
  for (const variable of variables) {
    const spans = Object.entries(found.variables || {})
      .filter(([name, info]) => (name === variable || name.startsWith(`${variable}_`)) && info.first && info.last)
      .map(([, info]) => [hydroYear(info.first), hydroYear(info.last)]);
    if (!spans.length) return null;
    first = Math.max(first, Math.min(...spans.map((span) => span[0])));
    last = Math.min(last, Math.max(...spans.map((span) => span[1])));
  }
  return first <= last ? { first, last } : null;
}

/**
 * The hydrological years an analysis uses, over the station's record of its variables
 * (YearRange of common.js: applied on „Przelicz”, with the 30-year note unless the range is
 * not a statistical period).
 *
 * @param {{station: object, variables: string[], dataset?: string, from?: number, to?: number,
 *   onApply: (from: number, to: number) => void, label?: string, recommend?: boolean}} props
 *   `from`, `to` the years chosen (the whole record by default)
 */
export function Years({ station, variables, dataset, from, to, onApply, label, recommend = true }) {
  const record = recordYears(station, variables, dataset);
  if (!record) return null;
  return html`<${YearRange}
    first=${record.first}
    last=${record.last}
    from=${from ?? record.first}
    to=${to ?? record.last}
    onApply=${onApply}
    label=${label || t("hydro.common.years")}
    recommend=${recommend}
  />`;
}

/**
 * A station's series of a dataset (`api.series`), refetched when a choice changes; null
 * arguments fetch nothing.
 *
 * @param {string|null} dataset
 * @param {string|null} code
 * @param {string[]} variables
 * @param {{start?: string, end?: string}} [range] ISO days
 * @returns {{data: object|null, error: Error|null, loading: boolean}}
 */
export function useSeries(dataset, code, variables, { start, end } = {}) {
  const wanted = dataset && code && variables.length ? variables.join(",") : null;
  const [state, setState] = useState({ data: null, error: null, loading: Boolean(wanted) });
  useEffect(() => {
    if (!wanted) {
      setState({ data: null, error: null, loading: false });
      return undefined;
    }
    const control = new AbortController();
    setState((old) => ({ data: old.data, error: null, loading: true }));
    api.series(dataset, code, { variables: wanted, start, end, signal: control.signal }).then(
      (data) => setState({ data, error: null, loading: false }),
      (error) => !control.signal.aborted && setState({ data: null, error, loading: false }),
    );
    return () => control.abort();
  }, [dataset, code, wanted, start, end]);
  return state;
}

/** A row of options with a label. */
export function Option({ label, children }) {
  return html`<div class="hy-option"><span class="hy-label">${label}</span>${children}</div>`;
}

/** A segmented choice of the variables a station has. */
export function VariableSeg({ value, variables, onChange }) {
  return html`<${Seg} value=${value} label=${t("hydro.common.variable")} options=${variables.map((v) => [v, variableLabel(v)])} onChange=${onChange} />`;
}

/** A native select. */
export function Select({ value, options, onChange, label }) {
  return html`<select class="hy-select" aria-label=${label || ""} value=${value} onChange=${(e) => onChange(e.target.value)}>
    ${options.map(([v, text]) => html`<option value=${v} selected=${String(v) === String(value)}>${text}</option>`)}
  </select>`;
}

/**
 * The hand-off to Hydrolog beside an analysis (plan D13): Panel's `HandoffButtons`.
 *
 * @param {object} props `{code, session, variable, resolution, from, to, analysis, overrides, doc}`:
 *   a daily series of the years `from`–`to` with the analysis' document `doc` beside it, or
 *   (`resolution: "annual"`) the annual maxima of the id `analysis` with its `overrides`
 */
export function Handoff(props) {
  return html`<div class="hy-handoff"><${HandoffButtons} ...${props} /></div>`;
}
