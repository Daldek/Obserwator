// Building blocks of the station panel's sections, shared by the hydrological and the
// meteorological views. The shell styles them (css/app.css); their props are fixed.
//
// An analysis is read by its id (one call of Hydrolog's program, the registry of the Nogat
// plan's O2): `useAnalysis(code, "characteristic.Q", overrides)` gives the stored result
// without overrides and one computed on request with them (GUI plan D8). The result is
// `obserwator-analysis/1`: `status` ("ok" | "failed"), `envelope` (Hydrolog's
// `hydrolog-result/1`: `result`, `notices`, `attribution`, `terms_notice`) or `error`
// (`hydrolog-error/1`), `command`, `options`, `inputs` [{dataset, series_version}],
// `hydrolog` {version}, `computed_at`, `source` ("stored" | "computed").

import { api } from "../api.js";
import { has } from "../i18n.js";
import { fmt, fmtDateTime, html, t, tn, useEffect, useState } from "../lib.js";

/**
 * The analysis ids that apply to a station (`api/analyses/{code}`).
 *
 * @param {string} code the station
 * @returns {{data: {analyses: object[], compute: boolean}|null, error: Error|null, loading: boolean,
 *   has: (id: string) => boolean}}
 */
export function useAnalysisList(code) {
  const [state, setState] = useState({ data: null, error: null, loading: true });
  useEffect(() => {
    let live = true;
    setState({ data: null, error: null, loading: true });
    api.analyses(code).then(
      (data) => live && setState({ data, error: null, loading: false }),
      (error) => live && setState({ data: null, error, loading: false }),
    );
    return () => {
      live = false;
    };
  }, [code]);
  const ids = new Set(state.data ? state.data.analyses.map((a) => a.analysis) : []);
  return { ...state, has: (id) => ids.has(id) };
}

function clean(overrides) {
  const out = {};
  for (const [key, value] of Object.entries(overrides || {})) {
    if (value !== undefined && value !== null && value !== "") out[key] = Array.isArray(value) ? value.join(",") : value;
  }
  return out;
}

/**
 * One analysis id of a station: refetched when the id, the station or an override changes.
 * A `null` id fetches nothing (an analysis that does not apply).
 *
 * @param {string} code the station
 * @param {string|null} id the analysis id
 * @param {Record<string, unknown>} [overrides] the person's options; none for the stored result
 * @returns {{data: object|null, error: Error|null, loading: boolean, result: object|null}}
 *   `result` is Hydrolog's own result (`data.envelope.result`) when the call succeeded
 */
export function useAnalysis(code, id, overrides = {}) {
  const chosen = clean(overrides);
  const key = JSON.stringify(chosen);
  const [state, setState] = useState({ data: null, error: null, loading: Boolean(id) });
  useEffect(() => {
    if (!id) {
      setState({ data: null, error: null, loading: false });
      return undefined;
    }
    const control = new AbortController();
    setState((old) => ({ data: old.data, error: null, loading: true }));
    api.analysis(code, id, chosen, { signal: control.signal }).then(
      (data) => setState({ data, error: null, loading: false }),
      (error) => !control.signal.aborted && setState({ data: null, error, loading: false }),
    );
    return () => control.abort();
  }, [code, id, key]);
  const data = state.data;
  const result = data && data.status === "ok" && data.envelope ? data.envelope.result : null;
  return { ...state, result };
}

/** The message of a failed analysis: Hydrolog's error document, else the API's error. */
export function failure(state) {
  if (state.error) return state.error.message;
  if (state.data && state.data.status === "failed" && state.data.error) {
    return state.data.error.message || state.data.error.title || t("sections.failed");
  }
  return null;
}

/**
 * A part of a panel's card: its sub-title, an (i) explanation, the body, and below it where
 * the numbers come from. The card's header already names the section, so `title` names this
 * part only and is left out where the part is the whole card.
 *
 * @param {{title?: string, info?: string|object, states?: object[], children}} props
 *   `states` from useAnalysis: while one loads the body dims, a failure replaces it, and
 *   the provenance of every result is shown under it
 */
export function Section({ title, info, states = [], children }) {
  const [open, setOpen] = useState(false);
  const loading = states.some((s) => s.loading);
  const failed = states.map(failure).filter(Boolean);
  const done = states.filter((s) => s.data);
  const empty = states.length > 0 && done.length === 0;
  return html`<section class="ana">
    ${(title || info) &&
    html`<header class="ana-head">
      ${title && html`<h3>${title}</h3>`}
      ${info &&
      html`<button type="button" class="info-btn" aria-expanded=${open} title=${t("sections.info")} aria-label=${t("sections.info")}
        onClick=${() => setOpen(!open)}>i</button>`}
      ${info && !title && html`<span class="muted small">${t("sections.info_methods")}</span>`}
    </header>`}
    ${open && html`<div class="ana-info">${info}</div>`}
    ${failed.length > 0 && done.every((s) => s.data.status !== "ok")
      ? html`<p class="ana-error">${failed.join(" ")}</p>`
      : html`<div class=${loading ? "ana-body is-loading" : "ana-body"}>
          ${loading && empty ? html`<p class="muted">${t("sections.computing")}</p>` : children}
        </div>`}
    ${done.length > 0 && html`<${Provenance} results=${done.map((s) => s.data)} />`}
  </section>`;
}

/**
 * Who computed it: Hydrolog's command and version, the series version, and whether the
 * result was stored or computed on request; a prototype names the Hydrolog step it awaits.
 *
 * @param {{results: object[]}} props `obserwator-analysis/1` documents (or a prototype's
 *   `{engine: "prototype", method, target}`)
 */
export function Provenance({ results }) {
  const seen = new Set();
  const items = [];
  for (const doc of results) {
    if (!doc) continue;
    if (doc.engine === "prototype") {
      const key = `p ${doc.target}`;
      if (!seen.has(key)) items.push(html`<span class="prov prov-proto" title=${doc.method}>${t("sections.prototype", { target: doc.target })}</span>`);
      seen.add(key);
      continue;
    }
    const key = `${doc.command} ${doc.source}`;
    if (seen.has(key)) continue;
    seen.add(key);
    const version = doc.hydrolog && doc.hydrolog.version;
    const when = doc.source === "stored" ? t("sections.stored", { when: fmtDateTime(doc.computed_at) }) : t("sections.on_request");
    items.push(
      html`<span class="prov prov-hydrolog" title=${JSON.stringify(doc.options || {})}>Hydrolog ${version || ""} · <code>${doc.command}</code> · ${when}</span>`,
    );
  }
  const versions = new Set();
  for (const doc of results) for (const input of (doc && doc.inputs) || []) versions.add(input.series_version);
  return html`<footer class="ana-prov">
    ${items}
    ${[...versions].map((v) => html`<span class="prov">${t("sections.series_version", { version: v })}</span>`)}
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

/** The shortest period statistics should rest on, in years (the author's answer 5). */
export const MIN_YEARS = 30;

/**
 * The range of (hydrological) years an analysis uses; applied on „Przelicz”. Analyses start
 * from the station's whole record (the author's answer 5). Where the range feeds statistics
 * (`recommend`), it says that 30 years is the recommended minimum and warns, without
 * refusing, of a range shorter than that.
 *
 * @param {{first: number, last: number, from: number, to: number,
 *   onApply: (from: number, to: number) => void, label?: string, recommend?: boolean}} props
 */
export function YearRange({ first, last, from, to, onApply, label, recommend = true }) {
  const [a, setA] = useState(from);
  const [b, setB] = useState(to);
  useEffect(() => {
    setA(from);
    setB(to);
  }, [from, to]);
  const bad = !(a >= first && b <= last && a <= b);
  const years = b - a + 1;
  const record = last - first + 1;
  const short = recommend && !bad && years < MIN_YEARS;
  return html`<form class="years" onSubmit=${(e) => (e.preventDefault(), !bad && onApply(a, b))}>
    <label>${label || t("sections.years")} <input type="number" min=${first} max=${last} value=${a} onInput=${(e) => setA(+e.target.value)} /></label>
    <span>–</span>
    <input type="number" aria-label=${t("sections.to_year")} min=${first} max=${last} value=${b} onInput=${(e) => setB(+e.target.value)} />
    <button type="submit" disabled=${bad}>${t("sections.recompute")}</button>
    ${recommend &&
    html`<small class=${short ? "years-note warn" : "years-note"} role=${short ? "status" : null}>
      ${t("sections.min_years", { years: MIN_YEARS })}
      ${short && ` ${tn(years === record ? "sections.short_record" : "sections.short_period", years, { from: a, to: b })}`}
    </small>`}
  </form>`;
}

/**
 * A plain table.
 *
 * @param {{columns: {key: string, label: string, digits?: number, format?: (v, row) => string}[],
 *   rows: object[], className?: string, max?: number}} props `max` rows shown before „Pokaż wszystkie”
 */
export function Table({ columns, rows, className, max = 0 }) {
  const [all, setAll] = useState(false);
  const shown = max && !all ? rows.slice(0, max) : rows;
  const cell = (c, row) =>
    c.format ? c.format(row[c.key], row) : typeof row[c.key] === "number" ? fmt(row[c.key], c.digits ?? 2) : row[c.key] ?? "–";
  return html`<div class="table-wrap"><table class=${className || "tbl"}>
      <thead><tr>${columns.map((c) => html`<th scope="col">${c.label}</th>`)}</tr></thead>
      <tbody>${shown.map((row) => html`<tr>${columns.map((c) => html`<td>${cell(c, row)}</td>`)}</tr>`)}</tbody>
    </table>
    ${max && rows.length > max && !all
      ? html`<button type="button" class="link" onClick=${() => setAll(true)}>${t("sections.show_all", { count: rows.length })}</button>`
      : null}
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

/**
 * The notices of Hydrolog's results (e.g. `short_reference_period`), each once, in the
 * page's language where the catalog words the code (`sections.notice.<code>`, its
 * placeholders the notice's `details`), else in Hydrolog's English.
 *
 * @param {{states: object[]}} props
 */
export function Notices({ states }) {
  const seen = new Set();
  const items = [];
  for (const state of states) {
    const notices = (state.data && state.data.envelope && state.data.envelope.notices) || [];
    for (const notice of notices) {
      if (seen.has(notice.code)) continue;
      seen.add(notice.code);
      items.push(notice);
    }
  }
  if (!items.length) return null;
  return html`<ul class="ana-notices">${items.map((n) => html`<li class=${`notice notice-${n.level}`}>${has(`sections.notice.${n.code}`) ? t(`sections.notice.${n.code}`, n.details || {}) : n.message}</li>`)}</ul>`;
}
