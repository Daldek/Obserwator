// „Krzywa natężenia przepływu” (Nogat plan H4): Hydrolog's `hydrometrics rating-curve` on the
// same-day H and Q of the chosen years (`rating_curve`: the last ten years by default) and
// the curves of successive periods of the whole record (`rating_curve.periods`). The H–Q
// points come from the daily series (`api.series`), thinned for the chart; the curves are
// Hydrolog's fitted Q = a·(H − H₀)^b drawn at the chart's levels.

import { Chart, fmt, html, lang, t, unit, useMemo } from "../../lib.js";
import { Figures, Notices, Section, Seg, Table, useAnalysis } from "../common.js";
import { Handoff, Option, Years, analysisIds, dailyDataset, useOptions, useSeries } from "./util.js";

const PALETTE = 8;
/** The cells of the grid that thins the H–Q points: one point per cell. */
const CELLS = [360, 240];

/** The colour class of the i-th of n groups of years, oldest to newest along the palette. */
function colour(index, count) {
  return `hy-c${count <= 1 ? PALETTE - 1 : Math.round((index * (PALETTE - 1)) / (count - 1))}`;
}

const fmtA = (a) => fmt(a, a < 0.01 ? 6 : 4);

function formula(fit) {
  const level = fit.h0 < 0 ? `H + ${fmt(-fit.h0, 1)}` : `H − ${fmt(fit.h0, 1)}`;
  return `Q = ${fmtA(fit.a)} · (${level})^${fmt(fit.b, 3)}`;
}

const flowLabel = (x) => `Q = ${fmt(x, x >= 100 ? 0 : x >= 10 ? 1 : 2)} m³/s`;

/**
 * Hydrolog's fitted curve drawn from just above H₀ to `high`: [[Q, H], …] at 80 levels.
 *
 * @param {{a: number, b: number, h0: number}} fit
 * @param {number} low the lowest level drawn [cm]
 * @param {number} high the highest level drawn [cm]
 */
function curve(fit, low, high) {
  const start = Math.max(low, fit.h0 + 0.5);
  if (!(high > start)) return [];
  const out = [];
  for (let i = 0; i < 80; i += 1) {
    const level = start + ((high - start) * i) / 79;
    out.push([fit.a * (level - fit.h0) ** fit.b, level]);
  }
  return out;
}

/**
 * The same-day H–Q pairs of a daily series in up to eight groups of consecutive years, each
 * thinned to one point per cell of a grid over the chart (the x in the axis' scale).
 *
 * @returns {{groups: {from: number, to: number, points: number[][]}[], low: number, high: number}|null}
 *   the groups with points, and the lowest and highest level of the pairs
 */
function pointGroups(series, from, to, log) {
  const level = series.values.H;
  const flow = series.values.Q;
  const pairs = [];
  for (let i = 0; i < series.dates.length; i += 1) {
    const year = series.hydro_year[i];
    if (level[i] !== null && flow[i] !== null && year >= from && year <= to && (!log || flow[i] > 0)) pairs.push(i);
  }
  if (!pairs.length) return null;
  const x = (i) => (log ? Math.log(flow[i]) : flow[i]);
  let x0 = Infinity;
  let x1 = -Infinity;
  let y0 = Infinity;
  let y1 = -Infinity;
  for (const i of pairs) {
    x0 = Math.min(x0, x(i));
    x1 = Math.max(x1, x(i));
    y0 = Math.min(y0, level[i]);
    y1 = Math.max(y1, level[i]);
  }
  const years = to - from + 1;
  const count = Math.min(PALETTE, years);
  const groups = [];
  for (let index = 0; index < count; index += 1) {
    const g0 = from + Math.floor((years * index) / count);
    const g1 = from + Math.floor((years * (index + 1)) / count) - 1;
    const seen = new Set();
    const points = [];
    for (const i of pairs) {
      const year = series.hydro_year[i];
      if (year < g0 || year > g1) continue;
      const column = Math.round(((x(i) - x0) / Math.max(x1 - x0, 1e-9)) * CELLS[0]);
      const row = Math.round(((level[i] - y0) / Math.max(y1 - y0, 1e-9)) * CELLS[1]);
      const cell = column * (CELLS[1] + 1) + row;
      if (seen.has(cell)) continue;
      seen.add(cell);
      points.push([flow[i], level[i]]);
    }
    groups.push({ from: g0, to: g1, points });
  }
  return { groups: groups.filter((group) => group.points.length), low: y0, high: y1 };
}

const groupName = (group) => (group.from === group.to ? String(group.from) : `${group.from}–${group.to}`);

function Periods({ code, ids, opt, setOpt, axis }) {
  const per = Number(opt.period);
  const state = useAnalysis(code, "rating_curve.periods", { years_per_period: per === 10 ? undefined : per, remove_outliers: opt.outliers ? true : undefined });
  const levels = useAnalysis(code, ids.has("characteristic.H") ? "characteristic.H" : null);
  const result = state.result;
  const range = levels.result;
  // A record shorter than one period has no periods (`periods` null)
  const periods = (result && result.periods) || [];
  const fitted = periods.filter((p) => p.a !== null && p.a !== undefined);
  const spec = useMemo(() => {
    if (!fitted.length || !range) return null;
    const name = (p) => `${p.first_year}–${p.last_year}`;
    return {
      x: { label: "Q [m³/s]", short: "Q", scale: axis === "log" ? "log" : "linear", zero: true, digits: 2 },
      y: { label: "H [cm]", unit: "cm", zero: false, digits: 0 },
      series: fitted.map((p, at) => ({ id: `p${p.first_year}`, kind: "line", cls: colour(at, fitted.length), label: name(p), data: curve(p, range.nnx, range.wwx), unit: "cm" })),
      legend: fitted.map((p, at) => ({ label: name(p), kind: "stroke", cls: colour(at, fitted.length) })),
      readout: { x: flowLabel },
      fit: { ratio: 0.62, minHeight: 220 },
      title: t("hydro.rating.periods_chart"),
    };
  }, [result, range, axis, lang()]);
  const columns = result && [
    { key: "label", label: t("hydro.rating.col_period"), format: (v) => v },
    { key: "n_pairs", label: t("hydro.rating.col_pairs"), format: (v) => fmt(v, 0) },
    { key: "a", label: "a", format: (v, row) => (row.reason ? t(`hydro.rating.reason.${row.reason}`) : fmtA(v)) },
    { key: "b", label: "b", format: (v) => (v === null || v === undefined ? "–" : fmt(v, 3)) },
    { key: "h0", label: "H₀ [cm]", format: (v) => (v === null || v === undefined ? "–" : fmt(v, 1)) },
    { key: "r_squared", label: "R²", format: (v) => (v === null || v === undefined ? "–" : fmt(v, 3)) },
    { key: "discharge_at_reference_m3s", label: t("hydro.rating.col_q_at", { level: fmt(result.reference_level, 0) }), format: (v) => (v === null || v === undefined ? "–" : fmt(v, v >= 100 ? 0 : 2)) },
    { key: "level_at_reference_discharge", label: t("hydro.rating.col_h_at", { flow: fmt(result.reference_discharge_m3s, 2) }), format: (v) => (v === null || v === undefined ? "–" : fmt(v, 0)) },
  ];
  const rows = periods.map((p) => ({ ...p, label: `${p.first_year}–${p.last_year}` }));
  return html`<${Section} title=${t("hydro.rating.periods_title")} info=${t("hydro.rating.periods_info")} states=${[state]}>
    <${Option} label=${t("hydro.rating.periods")}><${Seg}
      value=${opt.period}
      label=${t("hydro.rating.periods_length")}
      options=${["5", "10", "20"].map((n) => [n, t("hydro.rating.years_n", { n })])}
      onChange=${(v) => setOpt({ period: v })}
    /></${Option}>
    ${result && !periods.length ? html`<p class="muted hy-caption">${t("hydro.rating.no_periods")}</p>` : null}
    ${periods.length > 0 &&
    html`${spec && html`<${Chart} spec=${spec} />`}
      <${Table} columns=${columns} rows=${rows} className="tbl hy-compact" />
      <p class="muted hy-caption">${t("hydro.rating.periods_caption", { level: fmt(result.reference_level, 0), flow: fmt(result.reference_discharge_m3s, 2) })}</p>`}
    <${Notices} states=${[state]} />
  </${Section}>`;
}

/** The section „Krzywa natężenia przepływu”. */
export function RatingCurve({ station, session, analyses }) {
  const code = station.code;
  const ids = analysisIds(analyses);
  const [opt, setOpt] = useOptions({ from: undefined, to: undefined, period: "10", outliers: false, axis: "linear" }, code);
  const state = useAnalysis(code, ids.has("rating_curve") ? "rating_curve" : null, {
    first_year: opt.from,
    last_year: opt.to,
    remove_outliers: opt.outliers ? true : undefined,
  });
  const fit = state.result;
  const dataset = dailyDataset(station);
  const series = useSeries(fit ? dataset : null, code, ["H", "Q"], fit ? { start: `${fit.first_year - 1}-11-01`, end: `${fit.last_year}-10-31` } : {});
  const spec = useMemo(() => {
    if (!fit || !series.data) return null;
    const drawn = pointGroups(series.data, fit.first_year, fit.last_year, opt.axis === "log");
    const groups = drawn ? drawn.groups : [];
    const fitted = t("hydro.rating.fit_label", { from: fit.first_year, to: fit.last_year });
    return {
      x: { label: "Q [m³/s]", short: "Q", scale: opt.axis === "log" ? "log" : "linear", zero: true, digits: 2 },
      y: { label: "H [cm]", unit: "cm", zero: false, digits: 0 },
      series: [
        ...groups.map((group, at) => ({ id: `g${at}`, kind: "points", cls: colour(at, groups.length), label: groupName(group), data: group.points, readout: false })),
        { id: "fit", kind: "line", cls: "s1 hy-fit", label: fitted, data: drawn ? curve(fit, drawn.low, drawn.high) : [], unit: "cm" },
      ],
      legend: [
        ...groups.map((group, at) => ({ label: groupName(group), kind: "stroke", cls: colour(at, groups.length) })),
        { label: fitted, kind: "stroke", cls: "hy-fit" },
      ],
      readout: { series: "fit", x: flowLabel },
      fit: { ratio: 0.72, minHeight: 240 },
      title: t("hydro.rating.chart_title"),
    };
  }, [fit, series.data, opt.axis, lang()]);
  const flowUnit = unit("m3/s");
  return html`<div class="hy-card">
    <${Section} title=${t("hydro.rating.title")} info=${t("hydro.rating.info")} states=${[state]}>
      ${fit &&
      html`<${Years}
          station=${station}
          variables=${["H", "Q"]}
          from=${opt.from ?? fit.first_year}
          to=${opt.to ?? fit.last_year}
          onApply=${(from, to) => setOpt({ from, to })}
          recommend=${false}
        />
        <p class="muted hy-caption">${t("hydro.rating.default_note")}</p>
        <div class="hy-options">
          <${Option} label=${t("hydro.rating.outliers")}><${Seg}
            value=${opt.outliers ? "remove" : "keep"}
            label=${t("hydro.rating.outliers")}
            options=${[
              ["keep", t("hydro.rating.outliers_keep")],
              ["remove", t("hydro.rating.outliers_remove")],
            ]}
            onChange=${(v) => setOpt({ outliers: v === "remove" })}
          /></${Option}>
          <${Option} label=${t("hydro.rating.axis")}><${Seg}
            value=${opt.axis}
            label=${t("hydro.rating.axis")}
            options=${[
              ["linear", t("hydro.rating.axis_linear")],
              ["log", t("hydro.rating.axis_log")],
            ]}
            onChange=${(v) => setOpt({ axis: v })}
          /></${Option}>
        </div>
        <p class="hy-formula">${formula(fit)}</p>
        <${Figures}
          items=${[
            { label: "a", value: fmtA(fit.a), note: "m³/s · cm⁻ᵇ" },
            { label: "b", value: fmt(fit.b, 3) },
            { label: "H₀", value: `${fmt(fit.h0, 1)} cm` },
            { label: "R²", value: fmt(fit.r_squared, 4) },
            { label: t("hydro.rating.fig_std"), value: `${fmt(fit.std_residuals, 2)} ${flowUnit}` },
            {
              label: t("hydro.rating.fig_pairs"),
              value: fmt(fit.n_points, 0),
              note: fit.n_outliers_removed ? t("hydro.rating.removed", { n: fmt(fit.n_outliers_removed, 0) }) : t("hydro.rating.years_range", { from: fit.first_year, to: fit.last_year }),
            },
          ]}
        />
        ${series.error ? html`<p class="ana-error">${series.error.message}</p>` : spec && html`<${Chart} spec=${spec} />`}
        <p class="muted hy-caption">${t("hydro.rating.pairs_note")}</p>
        <${Handoff} code=${code} session=${session} variable="Q" resolution="daily" from=${fit.first_year} to=${fit.last_year} doc=${state.data} />`}
      <${Notices} states=${[state]} />
    </${Section}>
    ${ids.has("rating_curve.periods") && html`<${Periods} code=${code} ids=${ids} opt=${opt} setOpt=${setOpt} axis=${opt.axis} />`}
  </div>`;
}
