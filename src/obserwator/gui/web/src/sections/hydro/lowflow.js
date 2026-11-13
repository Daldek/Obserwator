// „Niżówki” (Nogat plan H7): low-flow periods of the discharge and low-water periods of the
// water level by the threshold level method, Hydrolog's `stats low-flow-sequences` (O2's ids
// `low_flow_sequences.Q` and `low_flow_sequences.H`, chosen by a „Q | H” switch where the
// station has both), stored over the station's whole record and computed on request for the
// years, threshold and limits the person chooses; the periods per year, one year's daily
// series with its periods drawn, and the hand-off of the daily series to Hydrolog beside
// them (plan D13). Every number is Hydrolog's.

import { Chart, dayNumber, fmt, html, t, tn, useEffect, useMemo, useState } from "../../lib.js";
import { Figures, Notices, Section, Seg, Table, useAnalysis } from "../common.js";
import { Handoff, Option, Select, UNITS, VariableSeg, Years, dailyDataset, date, digitsOf, fmtV, recordYears, useOptions, useSeries, withUnit } from "./util.js";

/** The id of each variable, the discharge first. */
const IDS = { Q: "low_flow_sequences.Q", H: "low_flow_sequences.H" };
const MILLION = 1e6;
/** The thresholds read off the duration curve: Hydrolog's exceedance percentage. */
const EXCEEDANCE = { p70: 70, p90: 90 };
/** The mean of the annual minima by variable: SNQ of the discharge, SNW of the water level. */
const MEAN_MINIMUM = { Q: "SNQ", H: "SNW" };
/** The texts of each variable: the (i), the threshold read off the duration curve, the daily series. */
const TEXTS = {
  Q: { info: "hydro.lowflow.info_q", exceedance: "hydro.lowflow.threshold_exceedance_q", daily: "hydro.lowflow.daily_q" },
  H: { info: "hydro.lowflow.info_h", exceedance: "hydro.lowflow.threshold_exceedance_h", daily: "hydro.lowflow.daily_h" },
};
/**
 * Hydrolog's deficits by variable (the fields of a period, a year and the whole): of Q as a
 * volume in m³, shown in million m³; of H in cm·d (the unit of the series times days), as
 * Hydrolog gives them. Digits of a key figure, the whole, the table and the chart.
 */
const DEFICITS = {
  Q: {
    event: "deficit_volume_m3",
    year: "deficit_volume_m3",
    total: "total_deficit_volume_m3",
    divisor: MILLION,
    unit: () => t("hydro.volume.unit"),
    value: (text) => t("hydro.volume.value", { value: text }),
    digits: { figure: 2, total: 1, table: 3, chart: 2 },
  },
  H: {
    event: "deficit_volume",
    year: "deficit",
    total: "total_deficit",
    divisor: null,
    unit: () => "cm·d",
    value: (text) => `${text}\u00a0cm·d`,
    digits: { figure: 0, total: 0, table: 0, chart: 0 },
  },
};

/** The registry entry of an id in the station's list of analyses, or null. */
function entryOf(analyses, id) {
  return (analyses || []).find((item) => item.analysis === id) || null;
}

/** A deficit of Hydrolog's in the unit it is shown in (million m³ of Q, cm·d of H). */
const shown = (value, kind) => (kind.divisor ? value / kind.divisor : value);

/** A deficit with its unit: „1,23 mln m³”, „2 797 cm·d”. */
function deficitText(value, kind, digits) {
  return kind.value(fmt(shown(value, kind), digits));
}

/**
 * The person's choices as the id's overrides; a choice equal to the registry's option is left
 * out, so the stored result serves the defaults.
 */
function overridesOf(opt, defaults) {
  const out = { first_year: opt.from, last_year: opt.to };
  if (opt.min !== undefined && opt.min !== defaults.min_duration_days) out.min_duration_days = opt.min;
  if (opt.gap !== undefined && opt.gap !== defaults.max_gap_days) out.max_gap_days = opt.gap;
  if (opt.threshold in EXCEEDANCE) {
    out.threshold_method = "exceedance";
    out.exceedance_percent = EXCEEDANCE[opt.threshold];
  } else if (opt.threshold === "value" && opt.value > 0) {
    out.threshold_method = "value";
    out.threshold = opt.value;
  } else if (defaults.threshold_method !== "mean_annual_minimum") {
    out.threshold_method = "mean_annual_minimum";
  }
  return out;
}

/** The thresholds the person chooses from, named after the variable: SNQ, Q70… or SNW, H70…. */
function thresholdOptions(variable) {
  return [
    ["sn", MEAN_MINIMUM[variable]],
    ["p70", `${variable}70`],
    ["p90", `${variable}90`],
    ["value", t("hydro.lowflow.threshold_value")],
  ];
}

/** Where Hydrolog's threshold came from, named by its method, with its period. */
function thresholdNote(result) {
  const variable = result.parameter;
  const period = { from: result.first_year, to: result.last_year };
  if (result.threshold_method === "mean_annual_minimum") {
    return t("hydro.lowflow.threshold_mean_minimum", { ...period, name: MEAN_MINIMUM[variable] });
  }
  if (result.threshold_method === "exceedance") {
    return t(TEXTS[variable].exceedance, { ...period, percent: fmt(result.exceedance_percent, 0) });
  }
  return t("hydro.lowflow.threshold_given");
}

/** The longest period (the latest of equal ones) and the one with the largest deficit. */
function extremesOf(sequences, kind) {
  let longest = null;
  let largest = null;
  for (const item of sequences) {
    if (!longest || item.duration_days >= longest.duration_days) longest = item;
    if (!largest || item[kind.event] >= largest[kind.event]) largest = item;
  }
  return { longest, largest };
}

const span = (item) => (item ? `${date(item.start_date)}–${date(item.end_date)}` : "");

/** The bars of the periods per hydrological year: days, deficit or number. */
function perYearSpec(result, metric, kind) {
  const pick = { days: (row) => row.duration_days, deficit: (row) => shown(row[kind.year], kind), n: (row) => row.n_events }[metric];
  const label = metric === "deficit" ? t("hydro.lowflow.axis.deficit", { unit: kind.unit() }) : t(`hydro.lowflow.axis.${metric}`);
  return {
    x: { label: t("hydro.axis.hydro_year"), digits: 0, min: result.first_year - 1, max: result.last_year + 1 },
    y: { label, digits: metric === "deficit" ? kind.digits.chart : 0 },
    series: [{ id: "y", kind: "bars", cls: "s2", align: "center", label, data: result.years.map((row) => [row.year, pick(row)]) }],
    readout: { x: (x) => t("hydro.axis.year", { year: Math.round(x) }) },
    fit: { ratio: 0.42, minHeight: 170 },
    title: t("hydro.lowflow.per_year_title"),
  };
}

/**
 * One hydrological year's daily series (Q on a log scale, H on a linear one) with its
 * low-flow periods drawn.
 */
function YearChart({ station, result, year }) {
  const variable = result.parameter;
  const series = useSeries(dailyDataset(station), station.code, [variable], { start: `${year - 1}-11-01`, end: `${year}-10-31` });
  const doc = series.data;
  const spec = useMemo(() => {
    if (!doc || !doc.values || !doc.values[variable]) return null;
    const values = doc.values[variable];
    const days = doc.dates.map(dayNumber);
    const level = result.threshold;
    const inside = new Uint8Array(days.length);
    for (const item of result.sequences) {
      const from = dayNumber(item.start_date);
      const to = dayNumber(item.end_date);
      if (to < days[0] || from > days[days.length - 1]) continue;
      days.forEach((day, at) => {
        if (day >= from && day <= to) inside[at] = 1;
      });
    }
    const below = (at) => inside[at] && values[at] !== null && values[at] < level;
    const u = UNITS[variable];
    const log = variable === "Q";
    return {
      x: { scale: "date" },
      y: { label: log ? t("hydro.axis.q_log") : `${variable} [${u}]`, unit: u, scale: log ? "log" : "linear", zero: false, digits: digitsOf(variable) },
      series: [
        {
          id: "deficit",
          kind: "band",
          cls: "s2",
          label: t("hydro.lowflow.deficit_band"),
          data: days.map((day, at) => (below(at) ? [day, values[at], level] : [day, null, null])),
          readout: false,
        },
        { id: "v", kind: "line", cls: "s1", label: t(TEXTS[variable].daily), unit: u, data: days.map((day, at) => [day, values[at]]) },
      ],
      marks: [{ kind: "hline", y: level, label: t("hydro.lowflow.threshold_mark", { value: fmtV(level, variable) }), cls: "hy-lv-dry" }],
      legend: true,
      readout: { series: "v" },
      fit: { ratio: 0.5, minHeight: 200 },
      title: t("hydro.lowflow.year_title", { year }),
    };
  }, [doc, result, year, variable]);
  if (series.error) return html`<p class="ana-error">${series.error.message}</p>`;
  if (!spec) return html`<p class="muted">${t("hydro.lowflow.year_loading", { year })}</p>`;
  return html`<div class=${series.loading ? "is-loading" : ""}><${Chart} spec=${spec} /></div>`;
}

/** The given threshold and the limits of the method, applied on „Przelicz”. */
function LimitsForm({ given, variable, threshold, min, gap, bounds, onApply }) {
  const [value, setValue] = useState("");
  const [days, setDays] = useState(min);
  const [merge, setMerge] = useState(gap);
  useEffect(() => {
    setDays(min);
    setMerge(gap);
  }, [min, gap]);
  useEffect(() => setValue(""), [variable]);
  const limit = (name, key) => (bounds[name] && bounds[name][key] !== undefined ? bounds[name][key] : null);
  const bad = !(days >= 1) || !(merge >= 0) || (given && !(+value > 0));
  const submit = (event) => {
    event.preventDefault();
    if (!bad) onApply({ value: given ? +value : undefined, min: days, gap: merge });
  };
  return html`<form class="years hy-limits" onSubmit=${submit}>
    ${given &&
    html`<label>${t("hydro.lowflow.threshold")}
      <input type="number" step="any" min="0" value=${value} placeholder=${fmtV(threshold, variable)} onInput=${(e) => setValue(e.target.value)} required /> ${UNITS[variable]}</label>`}
    <label>${t("hydro.lowflow.min_days")}
      <input type="number" min=${limit("min_duration_days", "minimum")} max=${limit("min_duration_days", "maximum")} value=${days} onInput=${(e) => setDays(+e.target.value)} /></label>
    <label>${t("hydro.lowflow.max_gap")}
      <input type="number" min=${limit("max_gap_days", "minimum")} max=${limit("max_gap_days", "maximum")} value=${merge} onInput=${(e) => setMerge(+e.target.value)} /> d</label>
    <button type="submit" disabled=${bad}>${t("sections.recompute")}</button>
  </form>`;
}

/** The section „Niżówki”. */
export function LowFlowPeriods({ station, session, analyses }) {
  const code = station.code;
  const variables = Object.keys(IDS).filter((v) => entryOf(analyses, IDS[v]));
  const [opt, setOpt] = useOptions(
    { var: undefined, from: undefined, to: undefined, choice: "sn", threshold: "sn", value: undefined, min: undefined, gap: undefined, metric: "days", year: undefined },
    code,
  );
  const variable = variables.includes(opt.var) ? opt.var : variables[0];
  const id = IDS[variable];
  const kind = DEFICITS[variable];
  const entry = entryOf(analyses, id);
  const defaults = (entry && entry.options) || {};
  const record = recordYears(station, [variable]);
  const fetched = useAnalysis(code, id, overridesOf(opt, defaults));
  // The other variable's document stays in the state while the switch loads: it is not shown.
  const state = fetched.data && fetched.data.analysis !== id ? { ...fetched, data: null, result: null } : fetched;
  const result = state.result;
  const { longest, largest } = useMemo(() => extremesOf(result ? result.sequences : [], kind), [result, kind]);
  const perYear = useMemo(() => result && perYearSpec(result, opt.metric, kind), [result, opt.metric, kind]);
  const withEvents = result ? [...new Set(result.sequences.map((item) => item.hydrological_year))].sort((a, b) => b - a) : [];
  const year = withEvents.includes(opt.year) ? opt.year : largest ? largest.hydrological_year : withEvents[0];
  const applyYears = (from, to) =>
    setOpt({ from: record && from === record.first ? undefined : from, to: record && to === record.last ? undefined : to, year: undefined });
  const choose = (choice) => setOpt(choice === "value" ? { choice } : { choice, threshold: choice, year: undefined });
  // A typed threshold is in the unit of its variable: another variable starts from its mean minimum.
  const switchTo = (v) =>
    setOpt({ var: v, year: undefined, value: undefined, ...(opt.choice === "value" || opt.threshold === "value" ? { choice: "sn", threshold: "sn" } : {}) });
  if (!variable) return null;
  const unit = UNITS[variable];
  const columns = [
    { key: "start_date", label: t("hydro.lowflow.col.from"), format: (v, row) => `${row.open_start ? "≤ " : ""}${date(v)}` },
    { key: "end_date", label: t("hydro.lowflow.col.to"), format: (v, row) => (row.open_end ? t("hydro.lowflow.open_end", { date: date(v) }) : date(v)) },
    { key: "duration_days", label: t("hydro.lowflow.col.days"), format: (v, row) => `${row.open_start || row.open_end ? "≥ " : ""}${fmt(v, 0)}` },
    { key: kind.event, label: t("hydro.lowflow.col.deficit", { unit: kind.unit() }), format: (v) => fmt(shown(v, kind), kind.digits.table) },
    { key: "min_flow", label: t("hydro.lowflow.col.min", { unit }), format: (v) => fmtV(v, variable) },
    { key: "mean_flow", label: t("hydro.lowflow.col.mean"), format: (v) => fmtV(v, variable) },
    { key: "missing_days", label: t("hydro.lowflow.col.missing"), format: (v) => (v ? fmt(v, 0) : "") },
  ];
  return html`<${Section} info=${t(TEXTS[variable].info)}><div class="hy-card">
    <${Years} station=${station} variables=${[variable]} from=${opt.from} to=${opt.to} onApply=${applyYears} label=${t("hydro.axis.hydro_years")} />
    <div class="hy-options">
      ${variables.length > 1 &&
      html`<${Option} label=${t("hydro.common.variable")}><${VariableSeg} value=${variable} variables=${variables} onChange=${switchTo} /></${Option}>`}
      <${Option} label=${t("hydro.lowflow.threshold")}>
        <${Seg} value=${opt.choice} label=${t("hydro.lowflow.threshold")} options=${thresholdOptions(variable)} onChange=${choose} />
      </${Option}>
    </div>
    <${LimitsForm}
      given=${opt.choice === "value"}
      variable=${variable}
      threshold=${result ? result.threshold : null}
      min=${result ? result.min_duration_days : defaults.min_duration_days}
      gap=${result ? result.max_gap_days : defaults.max_gap_days}
      bounds=${(entry && entry.overridable) || {}}
      onApply=${({ value, min, gap }) => setOpt({ threshold: opt.choice === "value" ? "value" : opt.threshold, value: value ?? opt.value, min, gap, year: undefined })}
    />
    <${Section} states=${[state]}>
      ${result &&
      html`
        <${Figures}
          items=${[
            { label: t("hydro.lowflow.threshold"), value: withUnit(result.threshold, variable), note: thresholdNote(result) },
            { label: t("hydro.lowflow.events"), value: fmt(result.n_events, 0), note: `${result.first_year}–${result.last_year}` },
            { label: t("hydro.lowflow.longest"), value: longest ? tn("hydro.axis.days", longest.duration_days) : "–", note: span(longest) },
            {
              label: t("hydro.lowflow.largest_deficit"),
              value: largest ? deficitText(largest[kind.event], kind, kind.digits.figure) : "–",
              note: span(largest),
            },
            {
              label: t("hydro.lowflow.total_deficit"),
              value: deficitText(result[kind.total], kind, kind.digits.total),
              note: tn("hydro.lowflow.in_years", result.period_years),
            },
          ]}
        />
        <${Option} label=${t("hydro.lowflow.metric")}>
          <${Seg}
            value=${opt.metric}
            label=${t("hydro.lowflow.metric")}
            options=${["days", "deficit", "n"].map((metric) => [metric, t(`hydro.lowflow.metric_name.${metric}`)])}
            onChange=${(metric) => setOpt({ metric })}
          />
        </${Option}>
        <${Chart} spec=${perYear} />
        ${year
          ? html`
              <${Option} label=${t("hydro.lowflow.year")}>
                <${Select} value=${year} label=${t("hydro.axis.hydro_year")} options=${withEvents.map((y) => [y, String(y)])} onChange=${(v) => setOpt({ year: +v })} />
              </${Option}>
              <${YearChart} station=${station} result=${result} year=${year} />
              <h4 class="hy-sub">${t("hydro.lowflow.table_title")}</h4>
              <${Table} columns=${columns} rows=${[...result.sequences].reverse()} max=${10} className="tbl hy-compact" />`
          : html`<p class="hy-note">${t("hydro.lowflow.none", { from: result.first_year, to: result.last_year })}</p>`}
        ${result.n_missing_days > 0 &&
        html`<p class="muted hy-caption">${t("hydro.lowflow.missing_note", { from: result.first_year, to: result.last_year, n: fmt(result.n_missing_days, 0) })}</p>`}
        <${Handoff} code=${code} session=${session} variable=${variable} resolution="daily" from=${result.first_year} to=${result.last_year} doc=${state.data} />
      `}
      <${Notices} states=${[state]} />
    </${Section}>
  </div></${Section}>`;
}
