// The hand-off of a station's series to Hydrolog (GUI plan D13, Nogat DEV-15.5): „Kopiuj do
// Hydrologa” puts the `nogat-handoff/1` the server builds (api/handoff/{code}, around a
// `hydrolog-series/1`) on the clipboard through the kit's nogat-handoff.js, „Plik
// przekazania” saves it as a file. Hydrolog's GUI opens it in „Statystyka przepływów”
// („Wczytaj…”: „Wklej ze schowka” or the file). Two kinds:
// - daily values of the hydrological years chosen; a section beside an analysis may give
//   the analysis' document (`doc`), whose command, options, version and result go into
//   the envelope's `provenance.analysis` and `result` (shown by Hydrolog beside its own,
//   for comparison, never as input) with the result's lines (ČHMÚ's line of results
//   computed by Hydrolog);
// - annual maxima: those Hydrolog's result of an analysis id used (`analysis` and its
//   `overrides`), the envelope filled by the server.
// The envelope keeps the server's `attribution` and `terms_notice` (Nogat DEV-20.6, 20.7).
//
//   html`<${HandoffButtons} code=${code} session=${session} variable="Q" from=${1991} to=${2020} doc=${data} />`

import { copyHandoff, downloadHandoff } from "../../nogat/nogat-handoff.js";
import { api } from "../api.js";
import { html, t, useEffect, useRef, useState } from "../lib.js";

/** The lines of two lists, each once, in the order they first appear. */
function union(first, second) {
  return [...new Set([...(first || []), ...(second || [])])];
}

/**
 * The server's daily hand-off with an analysis' result added for comparison.
 *
 * @param {object} doc the server's `nogat-handoff/1`
 * @param {object|undefined} analysis an `obserwator-analysis/1`; used when its status is "ok"
 * @returns {object} the document handed off
 */
export function withResult(doc, analysis) {
  if (!analysis || analysis.status !== "ok" || !analysis.envelope) return doc;
  const attribution = union(doc.attribution, analysis.attribution);
  const terms = union(doc.terms_notice, analysis.terms_notice);
  const version = analysis.hydrolog ? analysis.hydrolog.version : undefined;
  return {
    ...doc,
    ...(attribution.length ? { attribution } : {}),
    ...(terms.length ? { terms_notice: terms } : {}),
    provenance: {
      ...doc.provenance,
      analysis: { source: "hydrolog", analysis: analysis.analysis, command: `hydrolog ${analysis.command}`, version, options: analysis.options },
    },
    result: { analysis: analysis.analysis, hydrolog: analysis.hydrolog, result: analysis.envelope.result },
  };
}

/**
 * „Kopiuj do Hydrologa” and „Plik przekazania” for a station's series.
 *
 * @param {{code: string, session?: object|null, variable?: "Q"|"H", resolution?: "daily"|"annual",
 *   from?: number, to?: number, analysis?: string, overrides?: object, doc?: object}} props
 *   the station; api/session (its `gui.hydrolog` gives „Otwórz Hydrologa”); the variable;
 *   daily values of the hydrological years `from`–`to` (all by default), with the result
 *   of `doc` beside them, or the annual maxima of the analysis id `analysis` computed with
 *   `overrides`
 * @returns {object}
 */
export function HandoffButtons({ code, session, variable = "Q", resolution = "daily", from, to, analysis, overrides, doc }) {
  const field = useRef(null);
  const [state, setState] = useState({ busy: false, message: null, error: null });
  const chosen = JSON.stringify(overrides || {});
  useEffect(() => {
    setState({ busy: false, message: null, error: null });
    if (field.current) field.current.hidden = true;
  }, [code, variable, resolution, from, to, analysis, chosen]);
  const build = async () => {
    if (resolution === "annual") return api.handoff(code, { variable, resolution, analysis, ...(overrides || {}) });
    return withResult(await api.handoff(code, { variable, resolution, first_year: from, last_year: to }), doc);
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
  const copy = run(async (handed) => ((await copyHandoff(handed, field.current)) === "field" ? t("station.handoff.copy_by_hand") : t("station.handoff.copied")));
  const save = run(async (handed) => t("station.handoff.saved", { file: downloadHandoff(handed) }));
  const hydrolog = session && session.gui ? session.gui.hydrolog : null;
  return html`<div class="handoff-box">
    <div class="btn-row">
      <button type="button" class="btn sm primary" disabled=${state.busy} onClick=${copy}>
        <img class="btn-mark" src="nogat/marks/hydrolog.svg" alt="" width="16" height="16" />${t("station.handoff.copy")}
      </button>
      <button type="button" class="btn sm" disabled=${state.busy} onClick=${save}>${t("station.handoff.file")}</button>
      ${hydrolog
        ? html`<a class="btn sm ghost" href=${`${hydrolog.replace(/\/?$/, "/")}#statystyka`} target="nogat-hydrolog" rel="noopener">${t("station.handoff.open")}</a>`
        : null}
    </div>
    ${state.message ? html`<p class="ok-text" role="status">${state.message}</p>` : null}
    ${state.error ? html`<p class="ana-error" role="alert">${state.error.message}</p>` : null}
    <textarea ref=${field} class="handoff-field" hidden aria-label=${t("station.handoff.field")} rows="4"></textarea>
    <p class="note">${t("station.handoff.how")}</p>
  </div>`;
}
