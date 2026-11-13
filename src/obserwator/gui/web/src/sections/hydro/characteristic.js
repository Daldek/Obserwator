// „Stany charakterystyczne” (Nogat plan H1, H2, H3): Hydrolog's `stats characteristic` of the
// daily series (`characteristic.{H,Q,T}`) and of IMGW-PIB's half-year characteristics
// (`characteristic.{H,Q,T}.half_years`): first degree per year and half-year, second degree
// over the chosen years; `stats threshold-events` (`threshold_events.{H,Q}.<level>`) for
// ČHMÚ's thresholds of the station's catalog entry and the characteristic levels SWW, SSW,
// SNW (SWQ, SSQ, SNQ). IMGW-PIB's warning and alarm levels are operational data that are
// not archived (GUI plan D11), so they are not here.

import { Chart, dayNumber, fmt, html, lang, t, tn, unit, useMemo } from "../../lib.js";
import { periodName } from "../../words.js";
import { Figures, Notices, Section, Seg, Table, useAnalysis } from "../common.js";
import {
  HALF_YEARS,
  Handoff,
  Option,
  VariableSeg,
  Years,
  analysisIds,
  dailyDataset,
  date,
  digitsOf,
  fmtV,
  useOptions,
  useSeries,
  withUnit,
} from "./util.js";

const VARIABLES = ["H", "Q", "T"];
const PERIODS = ["annual", "winter", "summer"];
/** Hydrolog's keys of the second degree: rows highest, mean, median, lowest; columns of maxima, means, minima. */
const ROWS = [
  ["row_max", "wwx", "wsx", "wnx"],
  ["row_mean", "swx", "ssx", "snx"],
  ["row_median", "zwx", "zsx", "znx"],
  ["row_min", "nwx", "nsx", "nnx"],
];
/** The levels of `threshold_events.{H,Q}.<key>`: ČHMÚ's from the catalog, then Hydrolog's characteristic ones. */
const CHMI_LEVELS = ["spa1", "spa2", "spa3", "q50", "drought"];
const OWN_LEVELS = ["swx", "ssx", "snx"];
const LEVEL_CLASS = { spa1: "hy-lv-1", spa2: "hy-lv-2", spa3: "hy-lv-3", q50: "hy-lv-4", drought: "hy-lv-dry", swx: "hy-lv-c", ssx: "hy-lv-c", snx: "hy-lv-c" };
const SHORT = { spa1: "SPA 1", spa2: "SPA 2", spa3: "SPA 3", q50: "Q50" };

/** The second-degree values of a result for a period: the annual ones at its top, the half-years' under their names. */
function degree(result, period) {
  if (!result) return null;
  return period === "annual" ? result : result[period] || null;
}

function Matrix({ main, alt, period, variable }) {
  const values = degree(main, period);
  const other = degree(alt, period);
  const cell = (key) => html`<td>
    <span class="hy-name">${main.labels[key]}</span>
    <strong>${fmtV(values[key], variable)}</strong>
    ${other && html`<small class="hy-alt" title=${t("hydro.characteristic.alt_title")}>${fmtV(other[key], variable)}</small>`}
  </td>`;
  return html`<div class="table-wrap"><table class="tbl hy-matrix">
    <thead><tr><th scope="col"></th>${["col_max", "col_mean", "col_min"].map((col) => html`<th scope="col">${t(`hydro.characteristic.${col}`)}</th>`)}</tr></thead>
    <tbody>${ROWS.map(([row, ...keys]) => html`<tr><th scope="row">${t(`hydro.characteristic.${row}`)}</th>${keys.map(cell)}</tr>`)}</tbody>
  </table></div>`;
}

/** The years of `first`–`last` that a result of a daily series has no value in. */
function missingYears(result) {
  const present = new Set(result.years.map((row) => row.year));
  const out = [];
  for (let year = result.first_year; year <= result.last_year; year += 1) if (!present.has(year)) out.push(year);
  return out;
}

function SecondCaption({ main, alt, fromDaily, unitText }) {
  const parts = [];
  if (fromDaily) {
    parts.push(t("hydro.characteristic.caption_daily", { from: main.first_year, to: main.last_year, years: main.period_years, unit: unitText }));
    const missing = missingYears(main);
    if (missing.length) parts.push(t("hydro.characteristic.caption_missing", { years: missing.join(", ") }));
    const partial = main.years.filter((row) => row.annual.days_with_data < row.annual.days).map((row) => row.year);
    if (partial.length) parts.push(t("hydro.characteristic.caption_partial", { years: partial.join(", ") }));
    if (alt) parts.push(t("hydro.characteristic.caption_half", { from: alt.first_year, to: alt.last_year, years: alt.period_years }));
  } else {
    parts.push(t("hydro.characteristic.caption_half_only", { from: main.first_year, to: main.last_year, years: main.period_years, unit: unitText }));
  }
  return html`<p class="muted hy-caption">${parts.join(" ")}</p>`;
}

/** The rows of the first degree from the source chosen: IMGW-PIB's half-years, the daily series, or both. */
function firstRows(source, daily, half) {
  const rows = (result, from) => (result ? result.years.map((row) => ({ ...row, from })) : []);
  if (source === "half") return rows(half, "half");
  if (source === "daily") return rows(daily, "daily");
  const published = new Set(half ? half.years.map((row) => row.year) : []);
  return [...rows(half, "half"), ...rows(daily, "daily").filter((row) => !published.has(row.year))].sort((a, b) => a.year - b.year);
}

function FirstDegree({ rows, labels, variable, period, unitText }) {
  const names = [labels.min, labels.mean, labels.max];
  const spec = useMemo(() => {
    const first = rows[0].year;
    const last = rows[rows.length - 1].year;
    const byYear = new Map(rows.map((row) => [row.year, row]));
    const years = Array.from({ length: last - first + 1 }, (_, at) => first + at);
    return {
      x: { label: t("hydro.common.hydro_year"), digits: 0, min: first - 1, max: last + 1 },
      y: { label: `${variable} [${unitText}]`, unit: unitText, scale: variable === "Q" ? "log" : "linear", zero: variable === "Q", digits: digitsOf(variable) },
      series: [
        ["max", labels.max, "s2"],
        ["mean", labels.mean, "s1"],
        ["min", labels.min, "s3"],
      ].map(([key, label, cls]) => ({
        id: key,
        kind: "line",
        cls,
        label,
        data: years.map((year) => [year, byYear.has(year) ? byYear.get(year)[period][key] ?? null : null]),
      })),
      legend: true,
      readout: { x: (x) => t("hydro.common.year_n", { year: Math.round(x) }) },
      fit: { ratio: 0.5, minHeight: 190 },
      title: t("hydro.characteristic.chart_title", { variable }),
    };
  }, [rows, variable, period, lang()]);
  const source = (row) => {
    if (row.from === "half") return "IMGW-PIB";
    const part = row.part;
    return part.days_with_data < part.days
      ? t("hydro.characteristic.from_daily_part", { n: fmt(part.days_with_data, 0), days: fmt(part.days, 0) })
      : t("hydro.characteristic.from_daily");
  };
  const columns = [
    { key: "year", label: t("hydro.common.year"), format: (v) => String(v) },
    { key: "min", label: names[0], format: (v) => fmtV(v, variable) },
    { key: "min_date", label: t("hydro.common.date"), format: (v) => date(v) },
    { key: "mean", label: names[1], format: (v) => fmtV(v, variable) },
    { key: "max", label: names[2], format: (v) => fmtV(v, variable) },
    { key: "max_date", label: t("hydro.common.date"), format: (v) => date(v) },
    { key: "source", label: t("hydro.characteristic.col_source"), format: (v, row) => source(row) },
  ];
  const shown = [...rows].reverse().map((row) => ({ ...row[period], year: row.year, from: row.from, part: row[period] }));
  return html`<${Chart} spec=${spec} />
    <${Table} columns=${columns} rows=${shown} max=${12} />`;
}

/** The value of a level: ČHMÚ's from the station's catalog entry, a characteristic one from Hydrolog. */
function levelValue(key, variable, station, characteristic) {
  if (CHMI_LEVELS.includes(key)) {
    const thresholds = (station.properties && station.properties.thresholds) || {};
    const value = thresholds[variable] && thresholds[variable][key];
    return typeof value === "number" ? value : null;
  }
  return characteristic && typeof characteristic[key] === "number" ? characteristic[key] : null;
}

function levelName(key, characteristic) {
  if (CHMI_LEVELS.includes(key)) return t(`hydro.levels.name.${key}`);
  return `${characteristic.labels[key]} (${characteristic.first_year}–${characteristic.last_year})`;
}

function levelShort(key, characteristic) {
  if (key === "drought") return t("hydro.levels.short_drought");
  return SHORT[key] || (characteristic ? characteristic.labels[key] : key);
}

function Events({ result, variable, unitText }) {
  const above = result.direction !== "below";
  const rows = [...result.events].sort((a, b) => (above ? b.peak - a.peak : a.peak - b.peak));
  const columns = [
    { key: "start_date", label: t("hydro.levels.col_start"), format: date },
    { key: "end_date", label: t("hydro.levels.col_end"), format: date },
    { key: "duration_days", label: t("hydro.levels.days"), format: (v) => fmt(v, 0) },
    { key: "peak", label: t(above ? "hydro.levels.col_peak" : "hydro.levels.col_low"), format: (v) => withUnit(v, variable, unitText) },
    { key: "peak_date", label: t("hydro.levels.col_peak_date"), format: date },
  ];
  return html`<p class="muted hy-caption">${tn(above ? "hydro.levels.events_above" : "hydro.levels.events_below", result.n_events)}</p>
    <${Table} columns=${columns} rows=${rows} className="tbl hy-compact" max=${8} />`;
}

function Levels({ station, code, session, ids, years, choice, setChoice }) {
  const usable = ["H", "Q"].filter((v) => [...CHMI_LEVELS, ...OWN_LEVELS].some((key) => ids.has(`threshold_events.${v}.${key}`)));
  const variable = usable.includes(choice.lv) ? choice.lv : usable[0];
  const keys = [...CHMI_LEVELS, ...OWN_LEVELS].filter((key) => ids.has(`threshold_events.${variable}.${key}`));
  const characteristic = useAnalysis(code, ids.has(`characteristic.${variable}`) ? `characteristic.${variable}` : null, years);
  const level = keys.includes(choice.level) ? choice.level : keys.find((key) => key.startsWith("spa")) || keys[0];
  const events = useAnalysis(code, level ? `threshold_events.${variable}.${level}` : null, years);
  const own = characteristic.result;
  const levels = keys
    .map((key) => ({ key, value: levelValue(key, variable, station, own) }))
    .filter((item) => item.value !== null && (CHMI_LEVELS.includes(item.key) || own));
  const dataset = dailyDataset(station);
  const from = own ? own.first_year : years.first_year;
  const to = own ? own.last_year : years.last_year;
  const series = useSeries(dataset, code, variable ? [variable] : [], from && to ? { start: `${from - 1}-11-01`, end: `${to}-10-31` } : {});
  const unitText = unit(series.data ? series.data.units[variable] : variable === "H" ? "cm" : "m3/s");
  const daily = useMemo(() => {
    if (!series.data) return null;
    const values = series.data.values[variable];
    return {
      x: { scale: "date" },
      y: { label: `${variable} [${unitText}]`, unit: unitText, zero: false, digits: digitsOf(variable) },
      series: [{ id: "v", kind: "line", cls: "s1", label: t(variable === "H" ? "hydro.levels.daily_h" : "hydro.levels.daily_q"), data: series.data.dates.map((d, at) => [dayNumber(d), values[at]]), width: 1 }],
      marks: levels.map((item) => ({ kind: "hline", y: item.value, label: levelShort(item.key, own), cls: LEVEL_CLASS[item.key] })),
      readout: true,
      fit: { ratio: 0.55, minHeight: 210 },
      title: t("hydro.levels.chart_title", { variable }),
    };
  }, [series.data, levels.map((item) => `${item.key}${item.value}`).join(), lang()]);
  const result = events.result;
  const yearly = useMemo(() => {
    if (!result) return null;
    const above = result.direction !== "below";
    const label = t(above ? "hydro.levels.days_above" : "hydro.levels.days_below", { value: withUnit(result.threshold, variable, unitText) });
    return {
      x: { label: t("hydro.common.hydro_year"), digits: 0, min: result.first_year - 1, max: result.last_year + 1 },
      y: { label: t("hydro.levels.days"), unit: "d", digits: 0 },
      series: [{ id: "d", kind: "bars", cls: above ? "s2" : "s3", label, align: "center", data: result.years.map((row) => [row.year, row.days_beyond]) }],
      readout: { x: (x) => t("hydro.common.year_n", { year: Math.round(x) }) },
      fit: { ratio: 0.42, minHeight: 160 },
      title: t("hydro.levels.days_title"),
    };
  }, [result, lang()]);
  if (!variable) return null;
  return html`<${Section} title=${t("hydro.levels.title")} info=${t("hydro.levels.info")} states=${[events]}>
    ${usable.length > 1 && html`<${Option} label=${t("hydro.common.variable")}><${VariableSeg} value=${variable} variables=${usable} onChange=${(v) => setChoice({ lv: v, level: undefined })} /></${Option}>`}
    <ul class="hy-levels">${levels.map(
      (item) => html`<li class=${LEVEL_CLASS[item.key]}><i aria-hidden="true"></i>${levelName(item.key, own)}: <strong>${withUnit(item.value, variable, unitText)}</strong> <small>${CHMI_LEVELS.includes(item.key) ? "ČHMÚ" : "Hydrolog"}</small></li>`,
    )}</ul>
    ${series.error ? html`<p class="ana-error">${series.error.message}</p>` : daily && html`<${Chart} spec=${daily} />`}
    ${levels.length > 0 &&
    html`<${Option} label=${t("hydro.levels.level")}><${Seg} value=${level} label=${t("hydro.levels.level")} options=${levels.map((item) => [item.key, levelShort(item.key, own)])} onChange=${(v) => setChoice({ level: v })} /></${Option}>`}
    ${result &&
    html`<${Figures}
        items=${[
          { label: t("hydro.levels.level"), value: withUnit(result.threshold, variable, unitText), note: t(result.direction === "below" ? "hydro.levels.below" : "hydro.levels.above") },
          { label: t("hydro.levels.fig_days"), value: fmt(result.days_beyond, 0), note: t("hydro.levels.fig_years", { from: result.first_year, to: result.last_year }) },
          { label: t("hydro.levels.fig_events"), value: fmt(result.n_events, 0) },
          { label: t("hydro.levels.fig_longest"), value: tn("hydro.common.days", result.max_duration_days ?? 0) },
        ]}
      />
      <${Chart} spec=${yearly} />
      <${Events} result=${result} variable=${variable} unitText=${unitText} />`}
    <${Notices} states=${[events]} />
  </${Section}>`;
}

/** The section „Stany charakterystyczne”. */
export function Characteristic({ station, session, analyses }) {
  const code = station.code;
  const ids = analysisIds(analyses);
  const [opt, setOpt] = useOptions({ from: undefined, to: undefined, variable: undefined, period: "annual", source: "auto", lv: undefined, level: undefined }, code);
  const variables = VARIABLES.filter((v) => ids.has(`characteristic.${v}`) || ids.has(`characteristic.${v}.half_years`));
  const variable = variables.includes(opt.variable) ? opt.variable : variables.includes("Q") ? "Q" : variables[0];
  const years = { first_year: opt.from, last_year: opt.to };
  const daily = useAnalysis(code, ids.has(`characteristic.${variable}`) ? `characteristic.${variable}` : null, years);
  const half = useAnalysis(code, ids.has(`characteristic.${variable}.half_years`) ? `characteristic.${variable}.half_years` : null, years);
  const fromDaily = Boolean(daily.result);
  const main = daily.result || half.result;
  const alt = fromDaily ? half.result : null;
  const both = ids.has(`characteristic.${variable}`) && ids.has(`characteristic.${variable}.half_years`);
  const source = both ? opt.source : ids.has(`characteristic.${variable}`) ? "daily" : "half";
  const rows = firstRows(source, daily.result, half.result);
  const dataset = ids.has(`characteristic.${variable}`) ? dailyDataset(station) : HALF_YEARS;
  const unitText = unit(variable === "H" ? "cm" : variable === "Q" ? "m3/s" : "degC");
  const states = [daily, half].filter((state) => state.loading || state.data || state.error);
  return html`<div class="hy-card">
    <${Years} station=${station} variables=${[variable]} dataset=${dataset} from=${opt.from} to=${opt.to} onApply=${(from, to) => setOpt({ from, to })} />
    <div class="hy-options">
      ${variables.length > 1 && html`<${Option} label=${t("hydro.common.variable")}><${VariableSeg} value=${variable} variables=${variables} onChange=${(v) => setOpt({ variable: v })} /></${Option}>`}
      <${Option} label=${t("hydro.characteristic.period")}><${Seg} value=${opt.period} label=${t("hydro.characteristic.period")} options=${PERIODS.map((p) => [p, periodName(p)])} onChange=${(v) => setOpt({ period: v })} /></${Option}>
    </div>
    <${Section} title=${t("hydro.characteristic.second_title")} info=${t("hydro.characteristic.info")} states=${states}>
      ${main &&
      html`<${Matrix} main=${main} alt=${alt} period=${opt.period} variable=${variable} />
        <${SecondCaption} main=${main} alt=${alt} fromDaily=${fromDaily} unitText=${unitText} />
        ${fromDaily && variable !== "T" && html`<${Handoff} code=${code} session=${session} variable=${variable} resolution="daily" from=${main.first_year} to=${main.last_year} doc=${daily.data} />`}`}
      <${Notices} states=${states} />
    </${Section}>
    <${Section} title=${t("hydro.characteristic.first_title")} states=${states}>
      ${both &&
      html`<${Option} label=${t("hydro.characteristic.source")}><${Seg}
          value=${source}
          label=${t("hydro.characteristic.source")}
          options=${[
            ["auto", t("hydro.characteristic.source_auto")],
            ["half", t("hydro.characteristic.source_half")],
            ["daily", t("hydro.characteristic.source_daily")],
          ]}
          onChange=${(v) => setOpt({ source: v })}
        /></${Option}>`}
      ${main &&
      (rows.length
        ? html`<${FirstDegree} rows=${rows} labels=${main.first_degree_labels} variable=${variable} period=${opt.period} unitText=${unitText} />`
        : html`<p class="hy-note">${t("hydro.characteristic.none", { variable })}</p>`)}
    </${Section}>
    <${Levels} station=${station} code=${code} session=${session} ids=${ids} years=${years} choice=${opt} setChoice=${setOpt} />
  </div>`;
}
