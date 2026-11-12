// Helpers of the meteorological sections: options kept per station, the parts of a result
// with their own provenance, months, classes as coloured cells, dates.

import { fmt, fmtDate, html, useState } from "../../lib.js";
import { Seg } from "../common.js";

/** Calendar months 1–12 as Roman numerals. */
export const ROMAN = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII"];

/** Datasets of a meteorological station, as the switch names them. */
const DATASETS = {
  "pl.imgw.meteo_climate_daily": "klimatyczne IMGW-PIB",
  "pl.imgw.meteo_precip_daily": "opadowe IMGW-PIB",
  "cz.chmi.meteo_daily": "ČHMÚ",
};

/** The datasets with these variables (all of them) that a station has. */
export function datasetsWith(station, variables, keys = Object.keys(DATASETS)) {
  return (station.datasets || []).filter((d) => keys.includes(d.dataset) && variables.every((v) => v in d.variables));
}

/** Whether any of the station's meteorological datasets has a variable with values. */
export function stationHas(station, variable, keys) {
  return datasetsWith(station, [variable], keys).some((d) => (d.variables[variable].with_value || 0) > 0);
}

/**
 * Options of a card kept per station: they start again from `initial` on another station.
 *
 * @param {object} initial the options (undefined is left out of the query)
 * @param {string} code the station
 * @returns {[object, (patch: object) => void]}
 */
export function useOptions(initial, code) {
  const [state, setState] = useState({ code, values: initial });
  const values = state.code === code ? state.values : initial;
  return [values, (patch) => setState({ code, values: { ...values, ...patch } })];
}

/**
 * The state of an analysis with only the provenance of one part of its result: the server
 * tags each prototype with `part` ("sums", "regime", "spi", …); untagged items (Hydrolog's
 * commands, a single prototype) stay.
 */
export function part(state, ...parts) {
  if (!state.data) return state;
  const items = (state.data.computed_by || []).filter((item) => !item.part || parts.includes(item.part));
  return { ...state, data: { ...state.data, computed_by: items } };
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

/** The dataset switch, when the station is in more than one dataset with the variable. */
export function DatasetSeg({ data, value, onChange }) {
  if (!data || !data.datasets || data.datasets.length < 2) return null;
  return html`<${Option} label="Zbiór">
    <${Seg} value=${value || data.dataset} label="Zbiór danych" options=${data.datasets.map((d) => [d, DATASETS[d] || d])} onChange=${onChange} />
  </${Option}>`;
}

const RECORDED = { P: "opad", Tmean: "Tśr", Tmax: "Tmax", Tmin: "Tmin", snow_cover: "pokrywa śnieżna" };

/** Where a result comes from: the dataset and the span of the analysed variable. */
export function Source({ data }) {
  if (!data) return null;
  const what = RECORDED[data.record.variable] || "zapis";
  return html`<p class="me-source muted">Zbiór ${DATASETS[data.dataset] || data.dataset} · ${what}: ${fmtDate(data.record.first)} – ${fmtDate(data.record.last)}</p>`;
}

/** Short notes of a result (Polish texts of the server). */
export function Notes({ items }) {
  if (!items || !items.length) return null;
  return html`<ul class="me-notes">${items.map((text) => html`<li>${text}</li>`)}</ul>`;
}

/** A number with a unit, "–" when missing. */
export function num(value, digits = 1, unitText = "") {
  if (value === null || value === undefined || !Number.isFinite(value)) return "–";
  return unitText ? `${fmt(value, digits)}\u00a0${unitText}` : fmt(value, digits);
}

/** A date "YYYY-MM-DD" as "12.03.1997". */
export const date = fmtDate;

/** A date range "12.03–15.03.1997" (or the dates in full across years). */
export function dateRange(start, end) {
  if (!start) return "–";
  if (!end || end === start) return fmtDate(start);
  if (start.slice(0, 4) === end.slice(0, 4)) return `${start.slice(8, 10)}.${start.slice(5, 7)}–${fmtDate(end)}`;
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

/** Day numbers of the first day of each month (a 365-day year): ticks of a day-of-year axis. */
export const MONTH_TICKS = [1, 32, 60, 91, 121, 152, 182, 213, 244, 274, 305, 335].map((value, at) => ({ value, label: ROMAN[at] }));

/**
 * A class as a coloured cell: `palette` names the CSS family (`dw` dry–wet with 7 classes,
 * `k9` Sielianinov's 9 classes), `index` the class (0 = driest).
 */
export function classCls(palette, index) {
  return index === null || index === undefined ? "" : `me-${palette}${index}`;
}

/** A legend of classes: coloured swatches with their names. */
export function ClassLegend({ names, palette }) {
  return html`<div class="me-legend">${names.map((name, at) => html`<span><i class=${`me-sw ${classCls(palette, at)}`}></i>${name}</span>`)}</div>`;
}

/** The share of each class (%), as a compact table: name, share. */
export function ClassShares({ names, shares, palette, label = "Udział [%]" }) {
  return html`<div class="table-wrap"><table class="tbl me-shares">
    <thead><tr><th scope="col">Klasa</th>${names.map((n, at) => html`<th scope="col" class=${classCls(palette, at)} title=${n}>${n}</th>`)}</tr></thead>
    <tbody>${Object.entries(shares).map(([row, values]) => html`<tr><th scope="row">${row}</th>${values.map((v) => html`<td>${num(v, 1)}</td>`)}</tr>`)}</tbody>
  </table><span class="muted me-caption">${label}</span></div>`;
}

/** Year series of rows: [[year, value], …] (nulls kept as gaps). */
export function byYear(rows, key, yearKey = "year") {
  return rows.map((row) => [row[yearKey], row[key] ?? null]);
}

/** A readout heading for a year axis. */
export const yearReadout = (x) => `rok ${Math.round(x)}`;

/** An x axis over the years of rows, a year of margin each side (bars stand on their year). */
export function yearAxis(rows, label = "rok", key = "year") {
  const years = rows.map((row) => (Array.isArray(row) ? row[0] : row[key])).filter((y) => Number.isFinite(y));
  if (!years.length) return { label };
  return { label, min: Math.min(...years) - 1, max: Math.max(...years) + 1 };
}

/** A month "YYYY-MM" as "V 1983". */
export function monthText(text) {
  if (!text) return "–";
  return `${ROMAN[+text.slice(5, 7) - 1]} ${text.slice(0, 4)}`;
}
