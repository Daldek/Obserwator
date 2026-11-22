// The results of the view „PMAXTP” (plan D12): the tables of the old page
// (partials/pmaxtp_result.html, removed with the GUI's S8) for every duration and
// probability IMGW-PIB gives: the quantiles (ks), the upper bounds of their confidence
// interval (sg) and the estimation errors (rb). Under the table the rainfall intensity
// curves drawn by the shared chart module (charts/): PMAXTP's maximum intensity q = 166.7·J
// [dm³/(s·ha)], J = h/t [mm/min] of the quantile h [mm] of duration t [min], one curve per
// probability p, as klimat.imgw.pl/opady-maksymalne draws them. Then the monograph, the
// files, packed by the server from the API's answer for the point (api/files/pmaxtp: CSV and
// JSON with PMAXTP's lines and terms), the link to that answer at IMGW-PIB, which is the
// only address IMGW-PIB has for a point (klimat.imgw.pl/opady-maksymalne builds its own
// files in the browser), and the command line that gives the same numbers. PMAXTP's lines
// (PS, PP, the monograph M, N, RK; Nogat DEV-20.2) are in the view's strip (main.js): the
// answer of api/pmaxtp carries them as processed data, PP included, which the curves are.

import { api } from "../api.js";
import { Chart, fmt, fmtDateTime, html, lang, t, useMemo, useState } from "../lib.js";
import { Seg } from "../sections/common.js";
import { Command } from "../sections/pobierz.js";
import { MONOGRAPH_URL, methodName, outside, pmaxtpQuery, pointLabel } from "./state.js";

/** PMAXTP's factor of the intensity: q [dm³/(s·ha)] = 166.7 · J [mm/min]. */
const Q_PER_J = 166.7;

/** The durations labelled on the chart's log axis [min]; the curves span 5 to 4320. */
const DURATION_TICKS = [5, 10, 15, 30, 60, 120, 360, 720, 1440, 4320];

/** The steps of the curves' colour ramp (pmaxtp.css `.pm-p0` … `.pm-p26`). */
const RAMP_STEPS = 26;

/** IMGW-PIB's page of PMAXTP, which builds its files in the browser. */
const PAGE_URL = "https://klimat.imgw.pl/opady-maksymalne";
const PAGE_TEXT = "klimat.imgw.pl/opady-maksymalne";

/** The tables of the answer: the switch's label and the table's title. */
const TABLES = {
  ks: { label: "pmaxtp.table.ks.label", title: "pmaxtp.table.ks.title" },
  sg: { label: "pmaxtp.table.sg.label", title: "pmaxtp.table.sg.title" },
  rb: { label: "pmaxtp.table.rb.label", title: "pmaxtp.table.rb.title" },
};

/** A probability key of IMGW-PIB ("0.01", "99.9") as a number of the page's language. */
function probability(key) {
  const decimals = key.includes(".") ? key.length - key.indexOf(".") - 1 : 0;
  return fmt(Number(key), decimals);
}

/** The file of the point in a format, named as the server names it (Nogat DEV-19.21). */
function file(doc, format) {
  const query = pmaxtpQuery({ lat: doc.latitude, lon: doc.longitude }, doc.method);
  return {
    url: api.pmaxtpFileUrl({ ...query, format }),
    name: `obserwator_pmaxtp_${query.method}_${query.latitude}_${query.longitude}.${format}`,
  };
}

/**
 * The rainfall intensity curves of an answer: q = 166.7 · h / t [dm³/(s·ha)] of the
 * quantiles h (ks) against the duration t, one curve per probability p, from the rarest
 * (the highest, dark red) to the most frequent (blue); both axes logarithmic.
 *
 * @param {{doc: object}} props the answer of api/pmaxtp
 * @returns {object}
 */
function IntensityChart({ doc }) {
  const spec = useMemo(() => {
    const quantiles = doc.data.ks || {};
    const last = Math.max(1, doc.probabilities.length - 1);
    const series = doc.probabilities.map((key, at) => ({
      id: `p${key}`,
      kind: "line",
      cls: `pm-p pm-p${Math.round((at * RAMP_STEPS) / last)}`,
      label: `p = ${probability(key)} %`,
      data: doc.durations
        .map((duration) => {
          const minutes = Number(duration);
          const h = quantiles[duration] ? quantiles[duration][key] : null;
          return [minutes, Number.isFinite(h) ? (Q_PER_J * h) / minutes : null];
        })
        .filter(([, q]) => Number.isFinite(q) && q > 0),
    }));
    return {
      x: {
        scale: "log",
        min: 5,
        max: 4320,
        label: t("pmaxtp.chart.axis_x"),
        tickList: DURATION_TICKS.map((value) => ({ value, label: fmt(value) })),
      },
      y: { scale: "log", label: t("pmaxtp.chart.axis_y"), unit: "dm³/(s·ha)", digits: 1 },
      series,
      legend: true,
      readout: { x: (x) => `t = ${fmt(x)} min` },
      // tall enough for the readout of every curve (27 rows of a full answer) in the plot
      fit: { ratio: 0.75, minHeight: 500 },
      title: t("pmaxtp.chart.title", { method: doc.method, point: pointLabel({ lat: doc.latitude, lon: doc.longitude }) }),
    };
  }, [doc, lang()]);
  return html`<${Chart} class="pm-chart" spec=${spec} />`;
}

/**
 * The results panel.
 *
 * @param {{point: {lat: number, lon: number}|null, method: string,
 *   state: {doc: object|null, error: Error|null, loading: boolean}}} props
 * @returns {object}
 */
export function PmaxtpResult({ point, method, state }) {
  const [table, setTable] = useState("ks");
  if (!point) return html`<p class="hint-box">${t("pmaxtp.result.empty")}</p>`;
  const why = outside(point);
  if (why) return html`<p class="ana-error" role="alert">${why}</p>`;
  if (state.error) return html`<p class="ana-error" role="alert">${state.error.message}</p>`;
  const doc = state.doc;
  if (!doc) {
    return html`<p class="muted" role="status">${t("pmaxtp.result.loading", { point: pointLabel(point), method })}</p>`;
  }
  const rows = doc.data[table] || {};
  const files = ["csv", "json"].map((format) => [format, file(doc, format)]);
  return html`<div class=${`pmaxtp-result${state.loading ? " is-loading" : ""}`} aria-busy=${state.loading ? "true" : "false"}>
    <table class="params compact">
      <tbody>
        <tr><th>${t("pmaxtp.result.method")}</th><td>${doc.method} (${methodName(doc.method)})</td></tr>
        <tr><th>${t("pmaxtp.result.point")}</th><td>${pointLabel({ lat: doc.latitude, lon: doc.longitude })}</td></tr>
        <tr>
          <th>${t("pmaxtp.result.fetched")}</th>
          <td>${fmtDateTime(doc.fetched_at)}<span class="row-sub">${t("pmaxtp.result.cache")}</span></td>
        </tr>
      </tbody>
    </table>
    <${Seg}
      label=${t("pmaxtp.result.table_label")}
      value=${table}
      options=${Object.entries(TABLES).map(([key, names]) => [key, t(names.label)])}
      onChange=${setTable}
    />
    <p class="note">${t(TABLES[table].title, { unit: doc.unit })} ${t("pmaxtp.result.axes")}</p>
    <div class="table-wrap pm-table-wrap">
      <table class="tbl pm-table" aria-label=${t(TABLES[table].title, { unit: doc.unit })}>
        <thead>
          <tr>
            <th scope="col">t \\ p</th>
            ${doc.probabilities.map((key) => html`<th scope="col">${probability(key)}</th>`)}
          </tr>
        </thead>
        <tbody>
          ${doc.durations.map(
            (duration) => html`<tr>
              <th scope="row">${duration}</th>
              ${doc.probabilities.map((key) => html`<td>${fmt(rows[duration] ? rows[duration][key] : null, 2)}</td>`)}
            </tr>`,
          )}
        </tbody>
      </table>
    </div>
    <h3 class="group-title">${t("pmaxtp.chart.heading")}</h3>
    <${IntensityChart} doc=${doc} />
    <p class="note">${t("pmaxtp.chart.note")}</p>
    <p class="note">
      ${t("pmaxtp.result.monograph")}${" "}
      <a href=${MONOGRAPH_URL} target="_blank" rel="noopener noreferrer">${t("pmaxtp.result.monograph_link")}</a>
    </p>
    <h3 class="group-title">${t("pmaxtp.result.downloads")}</h3>
    <div class="btn-row files">
      ${files.map(
        ([format, { url, name }]) =>
          html`<a class="btn sm" href=${url} download=${name}><span class="fmt">${format.toUpperCase()}</span>${name}</a>`,
      )}
    </div>
    <p class="note">${t("pmaxtp.result.files", { durations: doc.durations.length, probabilities: doc.probabilities.length })}</p>
    <p class="note">
      <a class="pm-source" href=${doc.source_url} target="_blank" rel="noopener noreferrer">${t("pmaxtp.result.source_link")}</a>
      ${" — "}${t("pmaxtp.result.source_note")}${" "}
      <a href=${PAGE_URL} target="_blank" rel="noopener noreferrer">${PAGE_TEXT}</a>${" "}${t("pmaxtp.result.source_note_end")}
    </p>
    <${Command} line=${doc.command} />
  </div>`;
}
