// Helpers of the meteorological sections, shared by both halves („Opady”, „Susze” and
// „Temperatura”, „Śnieg”, „Trendy”): the analysis ids a station has and the options each
// accepts, options kept per station, labelled options, where a result comes from, months,
// dates, classes as coloured cells and year axes. Every word is an entry of the catalog.

import { fmt, fmtDate, html, t, useState } from "../../lib.js";
import { datasetTitle, variableInfo } from "../../words.js";
import { YearRange, useAnalysis } from "../common.js";

/** Calendar months 1–12 as Roman numerals. */
export const ROMAN = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII"];

/** The entries of `api/analyses/{code}` the panel passes: the list itself or its document. */
export function listOf(analyses) {
  if (Array.isArray(analyses)) return analyses;
  return (analyses && analyses.analyses) || [];
}

/** The entry of an analysis id in the station's list, or null when the id does not apply. */
export function entryOf(analyses, id) {
  return listOf(analyses).find((entry) => entry.analysis === id) || null;
}

/** Whether the station has any of the ids. */
export function hasAny(ids, names) {
  return names.some((name) => ids.has(name));
}

/**
 * The person's choices an id accepts (its `overridable`), without the unset ones: an id is
 * asked for its stored result until the person changes one of its options.
 *
 * @param {object|null} entry the id's entry of `api/analyses`
 * @param {Record<string, unknown>} choices
 * @returns {Record<string, unknown>}
 */
export function accepted(entry, choices) {
  const allowed = (entry && entry.overridable) || {};
  const out = {};
  for (const [name, value] of Object.entries(choices)) {
    if (name in allowed && value !== undefined && value !== null && value !== "") out[name] = value;
  }
  return out;
}

/** Whether an id takes an option. */
export function takes(entry, name) {
  return Boolean(entry && entry.overridable && name in entry.overridable);
}

/**
 * One analysis id of the station with the choices it accepts; nothing is fetched when the
 * station does not have the id.
 *
 * @param {string} code the station
 * @param {object[]} analyses the station's ids (`api/analyses`)
 * @param {string} id the analysis id
 * @param {Record<string, unknown>} [choices] the person's options (unset: the stored result)
 * @returns {{data: object|null, error: Error|null, loading: boolean, result: object|null,
 *   entry: object|null}}
 */
export function useMeteo(code, analyses, id, choices = {}) {
  const entry = entryOf(analyses, id);
  const state = useAnalysis(code, entry ? id : null, accepted(entry, choices));
  return { ...state, entry };
}

/**
 * Options of a card kept per station: they start again from `initial` on another station.
 *
 * @param {object} initial the options (undefined: the stored result's own)
 * @param {string} code the station
 * @returns {[object, (patch: object) => void]}
 */
export function useOptions(initial, code) {
  const [state, setState] = useState({ code, values: initial });
  const values = state.code === code ? state.values : initial;
  return [values, (patch) => setState({ code, values: { ...values, ...patch } })];
}

/**
 * The years of a variable's record at the station (the bounds of a period the person
 * chooses): calendar years, or hydrological years XI–X named after their end.
 *
 * @param {object} station `api/stations/{code}`
 * @param {object|null} doc an analysis of the variable (its input names the dataset)
 * @param {string} variable the store's variable ("P")
 * @param {string} [yearType] "calendar" or "hydrological"
 * @returns {{first: number, last: number}|null}
 */
export function recordYears(station, doc, variable, yearType = "calendar") {
  const input = doc && (doc.inputs || [])[0];
  const set = input && (station.datasets || []).find((d) => d.dataset === input.dataset);
  const span = set && set.variables[variable];
  if (!span || !span.first || !span.last) return null;
  const year = (iso) => +iso.slice(0, 4) + (yearType === "hydrological" && +iso.slice(5, 7) >= 11 ? 1 : 0);
  return { first: year(span.first), last: year(span.last) };
}

/**
 * The years a card's analyses use: the analysed period (the whole record by default) and,
 * where the ids take it, the reference period of the normals (by default the analysed
 * period); each says that 30 years is the recommended minimum. Choosing the default again
 * goes back to the stored results.
 *
 * @param {{station: object, doc: object|null, variable?: string, yearType?: string,
 *   result: object|null, opt: object, setOpt: (patch: object) => void, reference?: boolean}} props
 *   `doc` and `result`: an analysis of the card and its Hydrolog result (its period fields)
 */
export function Periods({ station, doc, variable = "P", yearType = "calendar", result, opt, setOpt, reference = false }) {
  const record = recordYears(station, doc, variable, yearType);
  if (!record) return null;
  const from = (result && result.first_year) ?? opt.first_year ?? record.first;
  const to = (result && result.last_year) ?? opt.last_year ?? record.last;
  const refFrom = (result && result.reference_first_year) ?? opt.reference_first_year ?? from;
  const refTo = (result && result.reference_last_year) ?? opt.reference_last_year ?? to;
  const period = (a, b) =>
    setOpt(a === record.first && b === record.last ? { first_year: undefined, last_year: undefined } : { first_year: a, last_year: b });
  const normals = (a, b) =>
    setOpt(a === from && b === to ? { reference_first_year: undefined, reference_last_year: undefined } : { reference_first_year: a, reference_last_year: b });
  return html`<${YearRange} first=${record.first} last=${record.last} from=${from} to=${to} onApply=${period} />
    ${reference &&
    html`<${YearRange} label=${t("meteo.common.reference")} first=${record.first} last=${record.last} from=${refFrom} to=${refTo} onApply=${normals} />`}`;
}

/** A labelled row of options. */
export function Option({ label, children }) {
  return html`<div class="me-option"><span class="me-label">${label}</span>${children}</div>`;
}

/** A native select of options [[value, label], …]. */
export function Select({ value, options, onChange, label }) {
  return html`<select class="me-select" aria-label=${label || ""} value=${value} onChange=${(e) => onChange(e.target.value)}>
    ${options.map(([v, text]) => html`<option value=${v} selected=${String(v) === String(value)}>${text}</option>`)}
  </select>`;
}

/**
 * Where a result comes from: the dataset of the analysis's input and the span of the
 * variable in it ("Daily climate data (IMGW-PIB) · precipitation: 01.01.1961 – 31.12.2025").
 *
 * @param {{station: object, doc: object|null, variable: string}} props `doc` is an
 *   `obserwator-analysis/1` document
 */
export function Source({ station, doc, variable }) {
  const input = doc && (doc.inputs || [])[0];
  if (!input) return null;
  const set = (station.datasets || []).find((d) => d.dataset === input.dataset);
  const span = set && set.variables[variable];
  const what = variableInfo(variable).label;
  return html`<p class="me-source muted">${datasetTitle(input.dataset)} · ${what}${span ? `: ${fmtDate(span.first)} – ${fmtDate(span.last)}` : ""}</p>`;
}

/** A number with a unit, "–" when missing. */
export function num(value, digits = 1, unitText = "") {
  if (value === null || value === undefined || !Number.isFinite(value)) return "–";
  return unitText ? `${fmt(value, digits)}\u00a0${unitText}` : fmt(value, digits);
}

/** A number of days with its unit ("23,0 dni"). */
export function daysText(value, digits = 0) {
  return num(value, digits, t("meteo.common.days_unit"));
}

/** A threshold of precipitation [mm] with no more decimals than it has: "0,1", "1", "2,5". */
export function mmLimit(value) {
  if (value === null || value === undefined || !Number.isFinite(value)) return "–";
  const digits = Number.isInteger(value) ? 0 : Number.isInteger(Math.round(value * 1e6) / 1e5) ? 1 : 2;
  return fmt(value, digits);
}

/** A date "YYYY-MM-DD" in the page's language. */
export const date = fmtDate;

/** A date range "12.03–15.03.1997" (the dates in full across years), "–" without a start. */
export function dateRange(start, end) {
  if (!start) return "–";
  if (!end || end === start) return fmtDate(start);
  if (start.slice(0, 4) === end.slice(0, 4)) return `${fmtDate(start).slice(0, 5)}–${fmtDate(end)}`;
  return `${fmtDate(start)}–${fmtDate(end)}`;
}

/** A day of the year (1 = 1 January, a 365-day year) as "17 VII". */
export function dayLabel(day) {
  if (day === null || day === undefined || !Number.isFinite(day)) return "–";
  const d = new Date(Date.UTC(2001, 0, 1) + (Math.round(day) - 1) * 86400000);
  return `${d.getUTCDate()} ${ROMAN[d.getUTCMonth()]}`;
}

/** A "MM-DD" as "28 XI". */
export function monthDay(text) {
  if (!text) return "–";
  return `${+text.slice(3, 5)} ${ROMAN[+text.slice(0, 2) - 1]}`;
}

/** A month of a year as "V 1983". */
export function monthText(year, month) {
  if (!year || !month) return "–";
  return `${ROMAN[month - 1]} ${year}`;
}

/** Day numbers of the first day of each month (a 365-day year): ticks of a day-of-year axis. */
export const MONTH_TICKS = [1, 32, 60, 91, 121, 152, 182, 213, 244, 274, 305, 335].map((value, at) => ({ value, label: ROMAN[at] }));

/**
 * A class as a coloured cell: `palette` names the CSS family (`dw` dry–wet with 7 classes,
 * `k9` Sielianinov's 9 classes), `index` the class (0 = driest).
 */
export function classCls(palette, index) {
  return index === null || index === undefined || index < 0 ? "" : `me-${palette}${index}`;
}

/** A legend of classes: coloured swatches with their names. */
export function ClassLegend({ names, palette }) {
  return html`<div class="me-legend">${names.map((name, at) => html`<span><i class=${`me-sw ${classCls(palette, at)}`}></i>${name}</span>`)}</div>`;
}

/** Year series of rows: [[year, value], …] (nulls kept as gaps). */
export function byYear(rows, key, yearKey = "year") {
  return rows.map((row) => [row[yearKey], row[key] ?? null]);
}

/** The x axis label of a year type. */
export function yearAxisLabel(yearType) {
  return yearType === "hydrological" ? t("meteo.common.hydro_year_axis") : t("meteo.common.year_axis");
}

/** A readout heading for a year axis. */
export const yearReadout = (x) => t("meteo.common.year_readout", { year: Math.round(x) });

/** An x axis over the years of rows, a year of margin each side (bars stand on their year). */
export function yearAxis(rows, label = t("meteo.common.year_axis"), key = "year") {
  const years = rows.map((row) => (Array.isArray(row) ? row[0] : row[key])).filter((y) => Number.isFinite(y));
  if (!years.length) return { label };
  return { label, min: Math.min(...years) - 1, max: Math.max(...years) + 1 };
}

/** Rows newest first, for tables of years. */
export function newestFirst(rows) {
  return [...(rows || [])].reverse();
}
