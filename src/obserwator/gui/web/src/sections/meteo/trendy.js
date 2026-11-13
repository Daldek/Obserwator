// „Trendy” (Nogat plan M13): Hydrolog's Mann–Kendall test with Sen's slope (`stats
// mann-kendall`) of the annual series of other analyses, one id each: the annual
// precipitation total, the highest daily precipitation, the days with precipitation of at
// least 10 mm, the longest dry spell, the annual mean temperature, the frost days and the
// summer days (`mann_kendall.*`). The years and values each test was given come with its
// result (`options`); the page draws them with the trend line Hydrolog fitted.

import { Chart, fmt, html, t } from "../../lib.js";
import { Notices, Section, Table, YearRange } from "../common.js";
import { num, recordYears, useMeteo, useOptions, yearAxis, yearReadout } from "./util.js";

/** The series in the mockup's order: the id, the store's variable and the unit (null = days). */
const SERIES = [
  ["mann_kendall.precipitation.sums", "P", "mm"],
  ["mann_kendall.precipitation.maxima", "P", "mm"],
  ["mann_kendall.precipitation.days", "P", null],
  ["mann_kendall.spells.dry", "P", null],
  ["mann_kendall.temperature.means", "Tmean", "°C"],
  ["mann_kendall.temperature.frost_days", "Tmin", null],
  ["mann_kendall.temperature.summer_days", "Tmax", null],
];
const PREFIX = "mann_kendall.";

/** The catalog name of a series: the id without its prefix, dots as underscores. */
function seriesKey(id) {
  return id.slice(PREFIX.length).replace(/\./g, "_");
}

/** A slope per year as per decade, signed: "+0,42". */
function perDecade(slope, digits) {
  if (slope === null || slope === undefined) return "–";
  const value = slope * 10;
  const text = fmt(Math.abs(value), digits ?? (Math.abs(value) >= 10 ? 1 : 2));
  return value > 0 ? `+${text}` : value < 0 ? `−${text}` : text;
}

/** The direction of a detected trend in words, else "not significant". */
function verdict(result) {
  if (!result.trend_detected) return t("meteo.trends.not_significant");
  return t(result.trend_direction === "decreasing" ? "meteo.trends.decreasing" : result.trend_direction === "increasing" ? "meteo.trends.increasing" : "meteo.trends.none");
}

function SeriesChart({ item }) {
  const { label, unit, result, years, values } = item;
  const points = years.map((year, at) => [year, values[at]]);
  const series = [{ id: "v", kind: "points", label, data: points, unit, digits: unit === "°C" ? 2 : 1 }];
  if (result && years.length) {
    const ends = [years[0], years[years.length - 1]];
    series.push({
      id: "sen",
      kind: "line",
      cls: result.trend_detected ? "s2" : "s4",
      label: t("meteo.trends.sen_line"),
      data: ends.map((year) => [year, result.sen_intercept + result.sen_slope * year]),
      readout: false,
    });
  }
  const spec = {
    x: yearAxis(points),
    y: { label: unit, unit, zero: unit !== "°C" },
    series,
    readout: { series: "v", x: yearReadout },
    fit: { ratio: 0.55, minHeight: 150 },
    title: label,
  };
  return html`<div class="me-trend">
    <h5>${label}</h5>
    <p>
      ${result
        ? html`<span class=${result.trend_detected ? "me-sig" : ""}>${t("meteo.trends.per_decade", { value: perDecade(result.sen_slope), unit })}</span> · p = ${fmt(result.p_value, 3)}`
        : item.failure || ""}
    </p>
    <${Chart} spec=${spec} />
  </div>`;
}

/**
 * The card „Trendy”.
 *
 * @param {{station: object, analyses: object[]}} props
 */
export function Trendy({ station, analyses }) {
  const code = station.code;
  const [opt, setOpt] = useOptions({ first_year: undefined, last_year: undefined }, code);
  const states = SERIES.map(([id]) => useMeteo(code, analyses, id, opt));
  const shown = SERIES.map(([id, variable, unit], at) => ({ id, variable, unit: unit || t("meteo.common.days_unit"), state: states[at] })).filter((item) => item.state.entry);
  const records = shown.map((item) => recordYears(station, item.state.data, item.variable)).filter(Boolean);
  const record = records.length ? { first: Math.min(...records.map((r) => r.first)), last: Math.max(...records.map((r) => r.last)) } : null;
  const onRange = (a, b) =>
    setOpt(record && a === record.first && b === record.last ? { first_year: undefined, last_year: undefined } : { first_year: a, last_year: b });
  const items = shown.map((item) => {
    const doc = item.state.data;
    const options = (doc && doc.options) || {};
    return {
      key: item.id,
      label: t(`meteo.trends.series.${seriesKey(item.id)}`),
      unit: item.unit,
      result: item.state.result,
      years: options.values ? options.years || [] : [],
      values: options.values || [],
      failure: doc && doc.status !== "ok" ? (doc.error && doc.error.message) || t("sections.failed") : item.state.error ? item.state.error.message : "",
    };
  });
  const alpha = items.map((item) => item.result && item.result.significance_level).find((value) => value !== null && value !== undefined);
  const columns = [
    { key: "label", label: t("meteo.trends.col.series"), format: (v) => v },
    { key: "values", label: t("meteo.trends.col.years"), format: (v) => (v.length ? String(v.length) : "–") },
    { key: "result", label: t("meteo.trends.col.sen"), format: (v, r) => (v ? `${perDecade(v.sen_slope)} ${r.unit}` : "–") },
    { key: "result", label: t("meteo.trends.col.interval"), format: (v) => (v ? `${perDecade(v.sen_slope_lower)} … ${perDecade(v.sen_slope_upper)}` : "–") },
    { key: "result", label: "Z", format: (v) => (v ? num(v.z_score, 2) : "–") },
    { key: "result", label: "p", format: (v) => (v ? num(v.p_value, 3) : "–") },
    {
      key: "result",
      label: alpha === undefined ? t("meteo.trends.col.trend") : t("meteo.trends.col.trend_at", { alpha: fmt(alpha, 2) }),
      format: (v, r) => (v ? (v.trend_detected ? html`<strong>${verdict(v)}</strong>` : verdict(v)) : r.failure || "–"),
    },
  ];
  const sectionStates = shown.map((item) => item.state);
  const from = opt.first_year ?? (record && record.first);
  const to = opt.last_year ?? (record && record.last);
  return html`<div class="me-card">
    ${record &&
    html`<div class="me-toolbar">
      <${YearRange} first=${record.first} last=${record.last} from=${from} to=${to} onApply=${onRange} />
    </div>`}
    <${Section} title=${t("meteo.trends.title")} info=${t("meteo.trends.info")} states=${sectionStates}>
      <${Notices} states=${sectionStates} />
      <${Table} columns=${columns} rows=${items} />
      <div class="me-trends">${items.filter((item) => item.values.length > 0).map((item) => html`<${SeriesChart} key=${item.key} item=${item} />`)}</div>
    </${Section}>
  </div>`;
}
