// Building blocks of the station panel's sections, shared by the hydrological and the
// meteorological views. The shell styles them (css/app.css); their props are fixed.

import { api } from "../api.js";
import { fmt, html, useEffect, useState } from "../lib.js";

/**
 * The state of one analysis of a station: refetched when the name, the station or a
 * parameter changes.
 *
 * @param {string} name the analysis (server/analyses)
 * @param {string} code the station
 * @param {Record<string, string|number|undefined>} params its options
 * @returns {{data: object|null, error: Error|null, loading: boolean}}
 */
export function useAnalysis(name, code, params = {}) {
  const key = JSON.stringify(params);
  const [state, setState] = useState({ data: null, error: null, loading: true });
  useEffect(() => {
    let live = true;
    setState((old) => ({ data: old.data, error: null, loading: true }));
    api.analysis(name, code, params).then(
      (data) => live && setState({ data, error: null, loading: false }),
      (error) => live && setState({ data: null, error, loading: false }),
    );
    return () => {
      live = false;
    };
  }, [name, code, key]);
  return state;
}

/**
 * A section of the panel: its title, an (i) explanation, the body, and below it where
 * the numbers come from.
 *
 * @param {{title: string, info?: string, state?: {data, error, loading}, children}} props
 *   `state` from useAnalysis: while loading the body dims, an error replaces it, and the
 *   provenance of `state.data.computed_by` is shown under it
 */
export function Section({ title, info, state, children }) {
  const [open, setOpen] = useState(false);
  const data = state ? state.data : null;
  return html`<section class="ana">
    <header class="ana-head">
      <h3>${title}</h3>
      ${info && html`<button type="button" class="info-btn" aria-expanded=${open} title="Objaśnienie" onClick=${() => setOpen(!open)}>i</button>`}
    </header>
    ${open && html`<div class="ana-info">${info}</div>`}
    ${state && state.error
      ? html`<p class="ana-error">${state.error.message}</p>`
      : html`<div class=${state && state.loading ? "ana-body is-loading" : "ana-body"}>${state && !data && state.loading ? html`<p class="muted">Liczę…</p>` : children}</div>`}
    ${data && html`<${Provenance} data=${data} />`}
  </section>`;
}

/**
 * Who computed it: Hydrolog's command and version, or a prototype that moves to Hydrolog.
 *
 * @param {{data: {computed_by?: object[], series_version?: string}}} props
 */
export function Provenance({ data }) {
  const items = data.computed_by || [];
  return html`<footer class="ana-prov">
    ${items.map((item) =>
      item.engine === "hydrolog"
        ? html`<span class="prov prov-hydrolog" title=${JSON.stringify(item.options || {})}>Hydrolog ${item.version} · <code>${item.command}</code></span>`
        : html`<span class="prov prov-proto" title=${item.method}>Prototyp obliczeń · docelowo Hydrolog (${item.target})</span>`,
    )}
    ${data.series_version && html`<span class="prov">szereg ${data.series_version}</span>`}
  </footer>`;
}

/**
 * A segmented choice.
 *
 * @param {{value: string, options: [string, string][], onChange: (v: string) => void, label?: string}} props
 *   options as [value, label]
 */
export function Seg({ value, options, onChange, label }) {
  return html`<div class="seg" role="radiogroup" aria-label=${label || ""}>
    ${options.map(
      ([v, text]) =>
        html`<button type="button" role="radio" aria-checked=${v === value} class=${v === value ? "on" : ""} onClick=${() => onChange(v)}>${text}</button>`,
    )}
  </div>`;
}

/**
 * The range of (hydrological) years an analysis uses; applied on „Przelicz”.
 *
 * @param {{first: number, last: number, from: number, to: number, onApply: (from: number, to: number) => void, label?: string}} props
 */
export function YearRange({ first, last, from, to, onApply, label = "Lata" }) {
  const [a, setA] = useState(from);
  const [b, setB] = useState(to);
  useEffect(() => {
    setA(from);
    setB(to);
  }, [from, to]);
  const bad = !(a >= first && b <= last && a <= b);
  return html`<form class="years" onSubmit=${(e) => (e.preventDefault(), !bad && onApply(a, b))}>
    <label>${label} <input type="number" min=${first} max=${last} value=${a} onInput=${(e) => setA(+e.target.value)} /></label>
    <span>–</span>
    <input type="number" aria-label="do roku" min=${first} max=${last} value=${b} onInput=${(e) => setB(+e.target.value)} />
    <button type="submit" disabled=${bad}>Przelicz</button>
  </form>`;
}

/**
 * A plain table.
 *
 * @param {{columns: {key: string, label: string, digits?: number, format?: (v, row) => string}[], rows: object[], className?: string, max?: number}} props
 *   `max` rows shown before „Pokaż wszystkie”
 */
export function Table({ columns, rows, className, max = 0 }) {
  const [all, setAll] = useState(false);
  const shown = max && !all ? rows.slice(0, max) : rows;
  const cell = (c, row) => (c.format ? c.format(row[c.key], row) : typeof row[c.key] === "number" ? fmt(row[c.key], c.digits ?? 2) : row[c.key] ?? "–");
  return html`<div class="table-wrap"><table class=${className || "tbl"}>
      <thead><tr>${columns.map((c) => html`<th scope="col">${c.label}</th>`)}</tr></thead>
      <tbody>${shown.map((row) => html`<tr>${columns.map((c) => html`<td>${cell(c, row)}</td>`)}</tr>`)}</tbody>
    </table>
    ${max && rows.length > max && !all ? html`<button type="button" class="link" onClick=${() => setAll(true)}>Pokaż wszystkie (${rows.length})</button>` : null}
  </div>`;
}

/**
 * Key figures in a row of tiles.
 *
 * @param {{items: {label: string, value: string, note?: string}[]}} props
 */
export function Figures({ items }) {
  return html`<dl class="figures">${items.map((i) => html`<div><dt>${i.label}</dt><dd>${i.value}</dd>${i.note && html`<small>${i.note}</small>`}</div>`)}</dl>`;
}
