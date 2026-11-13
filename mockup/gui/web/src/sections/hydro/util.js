// Helpers of the hydrological sections: options kept per station, a sub-block with its own
// provenance, the hydrological-year axis, number formats by variable, the hand-off slot.

import { fmt, fmtDate, html, unit, useEffect, useState } from "../../lib.js";
import { Provenance, Seg, YearRange } from "../common.js";

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

export const VARIABLES = { H: "H · stan wody", Q: "Q · przepływ", T: "T · temperatura wody" };
export const UNITS = { H: "cm", Q: "m³/s", T: "°C" };

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

/**
 * The year range of an analysis: shown once its result names the available years.
 *
 * @param {{data: object|null, onApply: (from: number, to: number) => void, label?: string, recommend?: boolean}} props
 *   `recommend` as YearRange: the 30-year note, on unless the range is not a statistical period
 */
export function Years({ data, onApply, label = "Lata hydrologiczne", recommend = true }) {
  if (!data || !data.years) return null;
  const { first, last, from, to } = data.years;
  return html`<${YearRange} first=${first} last=${last} from=${from} to=${to} onApply=${onApply} label=${label} recommend=${recommend} />`;
}

/**
 * A part of a section computed by another analysis: its own loading state, error and
 * provenance (the section's footer names only its main analysis).
 *
 * @param {{state: {data, error, loading}, title?: string, children}} props
 */
export function Block({ state, title, children }) {
  const head = title && html`<h4 class="hy-sub">${title}</h4>`;
  if (state.error) return html`<div class="hy-block">${head}<p class="ana-error">${state.error.message}</p></div>`;
  if (!state.data) return html`<div class="hy-block">${head}<p class="muted">Liczę…</p></div>`;
  return html`<div class=${state.loading ? "hy-block is-loading" : "hy-block"}>
    ${head}${children}
    <${Provenance} data=${state.data} />
  </div>`;
}

/** A row of options with a label. */
export function Option({ label, children }) {
  return html`<div class="hy-option"><span class="hy-label">${label}</span>${children}</div>`;
}

/** A segmented choice of the variables a station has. */
export function VariableSeg({ value, variables, onChange }) {
  return html`<${Seg} value=${value} label="Zmienna" options=${variables.map((v) => [v, VARIABLES[v] || v])} onChange=${onChange} />`;
}

/** A native select. */
export function Select({ value, options, onChange, label }) {
  return html`<select class="hy-select" aria-label=${label || ""} value=${value} onChange=${(e) => onChange(e.target.value)}>
    ${options.map(([v, text]) => html`<option value=${v} selected=${String(v) === String(value)}>${text}</option>`)}
  </select>`;
}

/** Hydrolog's notices of a result, plainly. */
export function Notices({ items }) {
  if (!items || !items.length) return null;
  const shown = items.filter((item) => item.level !== "info").slice(0, 6);
  if (!shown.length) return null;
  return html`<details class="hy-notices"><summary>Komunikaty Hydrologa (${shown.length})</summary>
    <ul>${shown.map((item) => html`<li><code>${item.code}</code> ${item.message}</li>`)}</ul>
  </details>`;
}

let handoff = null;
const handoffModule = import("../handoff.js").then(
  (module) => (handoff = module.HandoffButtons || null),
  () => null,
);

/**
 * The hand-off to Hydrolog (shell slice, `sections/handoff.js`), once that module is there.
 *
 * @param {object} props `HandoffButtons` props: {code, variable, resolution, from, to, computed, result}
 */
export function Handoff(props) {
  const [ready, setReady] = useState(Boolean(handoff));
  useEffect(() => {
    if (!handoff) handoffModule.then(() => setReady(Boolean(handoff)));
  }, []);
  if (!ready || !handoff) return null;
  return html`<div class="hy-handoff"><${handoff} ...${props} /></div>`;
}
