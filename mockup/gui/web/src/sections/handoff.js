// The hand-off of a station's series to Hydrolog (plan D13, DEV-15.5): „Kopiuj do
// Hydrologa” puts the `nogat-handoff/1` the server builds (api/handoff, around a
// `hydrolog-series/1`) on the clipboard through the kit's nogat-handoff.js, „Plik
// przekazania” saves it as a file. Hydrolog's GUI opens it in „Statystyka przepływów”
// („Wczytaj…”: „Wklej ze schowka” or the file). A section beside an analysis may add the
// analysis' provenance and its numbers: they go to the envelope's `provenance.analysis` and
// `result`, which Hydrolog shows beside its own (for comparison, never as input). The
// envelope keeps the server's `attribution` and `terms_notice` (Nogat DEV-20.6, DEV-20.7);
// with a result, a ČHMÚ series' processed line names the computation too.
//
//   html`<${HandoffButtons} code=${code} variable="Q" computed=${data.computed_by[0]} result=${{…}} />`

import { TEXTS, copyHandoff, downloadHandoff } from "../../nogat/nogat-handoff.js";
import { api } from "../api.js";
import { html, useEffect, useRef, useState } from "../lib.js";

/**
 * The envelope of the server with the analysis' provenance and result added.
 *
 * @param {object} doc the server's `nogat-handoff/1`
 * @param {object|undefined} computed one provenance item of `computed_by`
 * @param {object|undefined} result the analysis' numbers
 * @param {object|null} [texts] api/meta's `attribution` texts
 * @returns {object} the document handed off
 */
export function withAnalysis(doc, computed, result, texts = null) {
  const out = { ...doc, provenance: { ...doc.provenance } };
  if (computed) {
    const hydrolog = computed.engine === "hydrolog";
    const origin = { source: hydrolog ? "hydrolog" : "prototype" };
    for (const key of ["command", "version", "options", "method", "target"]) {
      if (computed[key] !== undefined) origin[key] = computed[key];
    }
    out.provenance.analysis = origin;
  }
  if (result && Object.keys(result).length) {
    const own = { ...result };
    if (computed && computed.engine === "hydrolog") {
      own.command = computed.command;
      own.computed_with = { tool: "hydrolog", version: String(computed.version) };
    } else if (computed) {
      own.command = `prototyp: ${computed.method}`;
    }
    out.result = own;
    if (texts && Array.isArray(out.attribution)) {
      out.attribution = out.attribution.map((line) => (line === texts.lines.CP ? texts.lines.CPR : line));
    }
  }
  return out;
}

/**
 * „Kopiuj do Hydrologa” and „Plik przekazania” for a station's series.
 *
 * @param {{code: string, variable?: "Q"|"H", resolution?: "daily"|"annual", from?: number,
 *   to?: number, computed?: object, result?: object}} props the station; the variable; daily
 *   values or annual maxima (default: daily when the store holds the daily series, else the
 *   annual maxima of the half-year characteristics); the hydrological years; the analysis'
 *   provenance item and numbers
 * @returns {object}
 */
export function HandoffButtons({ code, variable = "Q", resolution, from, to, computed, result }) {
  const field = useRef(null);
  const [meta, setMeta] = useState(null);
  const [state, setState] = useState({ busy: false, message: null, error: null });
  useEffect(() => {
    api.meta().then(setMeta, () => setMeta(null));
  }, []);
  useEffect(() => {
    setState({ busy: false, message: null, error: null });
    if (field.current) field.current.hidden = true;
  }, [code, variable, resolution, from, to]);
  const build = async () => {
    const doc = await api.get("api/handoff", { station: code, variable, resolution, from, to }, { memo: false });
    return withAnalysis(doc, computed, result, meta && meta.attribution);
  };
  const run = (action) => async () => {
    setState({ busy: true, message: null, error: null });
    try {
      const message = await action(await build());
      setState({ busy: false, message, error: null });
    } catch (error) {
      setState({ busy: false, message: null, error });
    }
  };
  const copy = run(async (doc) => ((await copyHandoff(doc, field.current)) === "field" ? TEXTS.copyByHand : TEXTS.copied));
  const save = run(async (doc) => TEXTS.saved(downloadHandoff(doc)));
  const hydrolog = meta && meta.gui && meta.gui.hydrolog;
  return html`<div class="handoff-box">
    <div class="btn-row">
      <button type="button" class="btn sm primary" disabled=${state.busy} onClick=${copy}>
        <img class="btn-mark" src="nogat/marks/hydrolog.svg" alt="" width="16" height="16" />${TEXTS.copyTo("hydrolog")}
      </button>
      <button type="button" class="btn sm" disabled=${state.busy} onClick=${save}>${TEXTS.file}</button>
      ${hydrolog
        ? html`<a class="btn sm ghost" href=${`${hydrolog.replace(/\/?$/, "/")}#statystyka`} target="nogat-hydrolog" rel="noopener">${TEXTS.open("hydrolog")}</a>`
        : null}
    </div>
    ${state.message ? html`<p class="ok-text" role="status">${state.message}</p>` : null}
    ${state.error ? html`<p class="ana-error" role="alert">${state.error.message}</p>` : null}
    <textarea ref=${field} class="handoff-field" hidden aria-label="Tekst przekazania do skopiowania" rows="4"></textarea>
    <p class="note">W Hydrologu: „Statystyka przepływów” → „Wczytaj…” → „Wklej ze schowka” albo „Plik przekazania…”.</p>
  </div>`;
}
