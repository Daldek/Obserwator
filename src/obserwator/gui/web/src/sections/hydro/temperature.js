// „Temperatura wody” (Nogat plan H14, H15): the harmonics of the annual cycle over the period
// and per year (Hydrolog's `stats harmonics`, O2's id `harmonics.T`), the days and runs of
// days beyond 15, 20, 25 °C and below 1 °C (`stats threshold-events`,
// `threshold_events.T.{ge15,ge20,ge25,lt1}`), each year's maximum with its date (`stats
// characteristic`, `characteristic.T`) and the mean of each day of the year (`stats daily`,
// `daily.T`). Every number is Hydrolog's; the curves are its harmonics evaluated at the
// days of the chart.

import { Chart, fmt, html, t, tn, useMemo } from "../../lib.js";
import { Figures, Notices, Section, Seg, Table, useAnalysis } from "../common.js";
import { DOY_TICKS, Option, Years, date, doyLabel, recordYears, useOptions } from "./util.js";

const HARMONICS = "harmonics.T";
const CHARACTERISTIC = "characteristic.T";
const DAILY = "daily.T";
/** The thresholds of O2's ids `threshold_events.T.<key>`. */
const KEYS = ["ge15", "ge20", "ge25", "lt1"];
/** The thresholds the table of the years shows. */
const TABLE_KEYS = ["ge20", "ge25", "lt1"];
const DAYS = Array.from({ length: 366 }, (_, at) => at + 1);

/** The registry entry of an id in the station's list of analyses, or null. */
function entryOf(analyses, id) {
  return (analyses || []).find((item) => item.analysis === id) || null;
}

/** A threshold as „≥ 20 °C” or „< 1 °C”, from the id's options (or Hydrolog's result). */
function thresholdText(options, unitText = "\u00a0°C") {
  if (!options || options.threshold === undefined) return "";
  return `${options.direction === "below" ? "<" : "≥"} ${fmt(options.threshold, 0)}${unitText}`;
}

/**
 * Hydrolog's fit of the annual cycle evaluated at the days of the hydrological year (1 = 1 XI):
 * T(d) = A₀ + Σ Cₖ·cos(2πk(d − dₖ)/P), dₖ the day of the harmonic's first maximum.
 */
function cycle(fit, period, count) {
  return DAYS.map((day) => [
    day,
    fit.harmonics.slice(0, count).reduce((sum, item, at) => sum + item.amplitude * Math.cos((2 * Math.PI * (at + 1) * (day - item.phase_day)) / period), fit.mean),
  ]);
}

/** The annual cycle: the mean of each day over the years, Hydrolog's fit and its first harmonic. */
function cycleSpec(result, daily) {
  const fit = result.period;
  const series = [];
  if (daily) {
    series.push({ id: "mean", kind: "line", cls: "s4", label: t("hydro.temperature.day_mean"), width: 1, data: daily.day_of_year.map((day, at) => [day, daily.mean_values[at]]) });
  }
  series.push(
    { id: "fit", kind: "line", cls: "s1", label: t("hydro.temperature.fit", { n: result.n_harmonics }), data: cycle(fit, result.period_days, result.n_harmonics) },
    { id: "first", kind: "line", cls: "s5", label: t("hydro.temperature.first_harmonic"), data: cycle(fit, result.period_days, 1) },
  );
  return {
    x: { label: t("hydro.axis.hydro_day"), tickList: DOY_TICKS, min: 1, max: 366 },
    y: { label: "T [°C]", unit: "°C", zero: false, digits: 1 },
    series,
    legend: true,
    readout: { series: "fit", x: doyLabel },
    fit: { ratio: 0.55, minHeight: 210 },
    title: t("hydro.temperature.cycle_title"),
  };
}

/** The mean and the amplitude of the first harmonic of each year with a fit of its own. */
function yearlySpec(result) {
  return {
    x: { label: t("hydro.axis.hydro_year"), digits: 0, min: result.first_year - 1, max: result.last_year + 1 },
    y: { label: "°C", unit: "°C", zero: false, digits: 2 },
    series: [
      { id: "a0", kind: "line", cls: "s1", label: t("hydro.temperature.a0"), data: result.years.map((row) => [row.year, row.mean]) },
      { id: "c1", kind: "line", cls: "s2", label: t("hydro.temperature.c1"), data: result.years.map((row) => [row.year, row.harmonics[0].amplitude]) },
    ],
    legend: true,
    readout: { x: (x) => t("hydro.axis.year", { year: Math.round(x) }) },
    fit: { ratio: 0.42, minHeight: 170 },
    title: t("hydro.temperature.yearly_title"),
  };
}

/** The days beyond a threshold in each year. */
function daysSpec(result, label, below) {
  return {
    x: { label: t("hydro.axis.hydro_year"), digits: 0, min: result.first_year - 1, max: result.last_year + 1 },
    y: { label: t("hydro.temperature.days_axis"), digits: 0 },
    series: [
      { id: "d", kind: "bars", cls: below ? "s3" : "s2", align: "center", label: t("hydro.temperature.days_label", { threshold: label }), data: result.years.map((row) => [row.year, row.days_beyond]) },
    ],
    readout: { x: (x) => t("hydro.axis.year", { year: Math.round(x) }) },
    fit: { ratio: 0.4, minHeight: 160 },
    title: t("hydro.temperature.days_title", { threshold: label }),
  };
}

/** The longest run of days beyond the threshold (the latest of equal ones), or null. */
function longestRun(events) {
  let found = null;
  for (const item of events) if (!found || item.duration_days >= found.duration_days) found = item;
  return found;
}

/** The years of the results side by side, the latest first. */
function yearRows(harmonics, events, characteristic) {
  const rows = new Map();
  const row = (year) => {
    if (!rows.has(year)) rows.set(year, { year });
    return rows.get(year);
  };
  for (const [key, result] of Object.entries(events)) {
    for (const item of result.years) Object.assign(row(item.year), { days: item.days_with_data, [key]: item.days_beyond });
  }
  if (harmonics) {
    for (const item of harmonics.years) {
      const [first, second] = item.harmonics;
      Object.assign(row(item.year), { a0: item.mean, c1: first.amplitude, phase1: first.phase_day, c2: second ? second.amplitude : null, r2: item.r_squared });
    }
  }
  if (characteristic) {
    for (const item of characteristic.years) {
      if (item.annual && item.annual.max !== null) Object.assign(row(item.year), { max: item.annual.max, max_date: item.annual.max_date });
    }
  }
  return [...rows.values()].sort((a, b) => b.year - a.year);
}

/** The section „Temperatura wody”. */
export function WaterTemperature({ station, analyses }) {
  const code = station.code;
  const ids = new Set((analyses || []).map((item) => item.analysis));
  const record = recordYears(station, ["T"]);
  const keys = KEYS.filter((key) => ids.has(`threshold_events.T.${key}`));
  const [opt, setOpt] = useOptions({ from: undefined, to: undefined, threshold: "ge20" }, code);
  const chosen = keys.includes(opt.threshold) ? opt.threshold : keys[0];
  const period = { first_year: opt.from, last_year: opt.to };
  const custom = opt.from !== undefined || opt.to !== undefined;
  const harmonics = useAnalysis(code, ids.has(HARMONICS) ? HARMONICS : null, period);
  const daily = useAnalysis(code, ids.has(DAILY) && !custom ? DAILY : null);
  const characteristic = useAnalysis(code, ids.has(CHARACTERISTIC) ? CHARACTERISTIC : null, period);
  const wanted = (key) => keys.includes(key) && (key === chosen || TABLE_KEYS.includes(key));
  const ge15 = useAnalysis(code, wanted("ge15") ? "threshold_events.T.ge15" : null, period);
  const ge20 = useAnalysis(code, wanted("ge20") ? "threshold_events.T.ge20" : null, period);
  const ge25 = useAnalysis(code, wanted("ge25") ? "threshold_events.T.ge25" : null, period);
  const lt1 = useAnalysis(code, wanted("lt1") ? "threshold_events.T.lt1" : null, period);
  const events = { ge15, ge20, ge25, lt1 };
  const hr = harmonics.result;
  const er = chosen ? events[chosen].result : null;
  const labels = Object.fromEntries(keys.map((key) => [key, thresholdText((entryOf(analyses, `threshold_events.T.${key}`) || {}).options)]));
  const cycleChart = useMemo(() => hr && cycleSpec(hr, daily.result), [hr, daily.result]);
  const yearly = useMemo(() => hr && hr.years.length && yearlySpec(hr), [hr]);
  const days = useMemo(() => er && daysSpec(er, labels[chosen], er.direction === "below"), [er, chosen]);
  const longest = er ? longestRun(er.events) : null;
  const loaded = Object.fromEntries(Object.entries(events).filter(([, state]) => state.result).map(([key, state]) => [key, state.result]));
  const rows = yearRows(hr, loaded, characteristic.result);
  const applyYears = (from, to) => setOpt({ from: record && from === record.first ? undefined : from, to: record && to === record.last ? undefined : to });
  const fit = hr && hr.period;
  const [h1, h2] = fit ? fit.harmonics : [];
  const columns = [
    { key: "year", label: t("hydro.temperature.col.year"), format: (v) => String(v) },
    { key: "days", label: t("hydro.temperature.col.days"), format: (v) => fmt(v, 0) },
    { key: "a0", label: "A₀", format: (v) => fmt(v, 2) },
    { key: "c1", label: "C₁", format: (v) => fmt(v, 2) },
    { key: "phase1", label: t("hydro.temperature.col.phase1"), format: (v) => (v === undefined ? "–" : doyLabel(v)) },
    { key: "c2", label: "C₂", format: (v) => fmt(v, 2) },
    { key: "r2", label: "R²", format: (v) => fmt(v, 3) },
    ...TABLE_KEYS.filter((key) => keys.includes(key)).map((key) => ({ key, label: thresholdText((entryOf(analyses, `threshold_events.T.${key}`) || {}).options, "°"), format: (v) => fmt(v, 0) })),
    { key: "max", label: t("hydro.temperature.col.max"), format: (v, row) => (v === undefined ? "–" : `${fmt(v, 1)} (${date(row.max_date)})`) },
  ];
  const active = (state) => state.loading || state.data || state.error;
  return html`<${Section} info=${t("hydro.temperature.info")} guide="metody-temperature"><div class="hy-card">
    <${Years} station=${station} variables=${["T"]} from=${opt.from} to=${opt.to} onApply=${applyYears} label=${t("hydro.axis.hydro_years")} />
    ${ids.has(HARMONICS) &&
    html`<${Section} title=${t("hydro.temperature.cycle_part")} states=${[harmonics, daily].filter(active)}>
      ${hr &&
      html`
        <${Figures}
          items=${[
            { label: t("hydro.temperature.a0"), value: `${fmt(fit.mean, 2)} °C`, note: `${tn("hydro.axis.days", fit.n_values)} ${hr.first_year}–${hr.last_year}` },
            { label: t("hydro.temperature.c1"), value: `${fmt(h1.amplitude, 2)} °C`, note: t("hydro.temperature.max_on", { date: doyLabel(h1.phase_day) }) },
            ...(h2 ? [{ label: "C₂", value: `${fmt(h2.amplitude, 2)} °C`, note: t("hydro.temperature.max_on_half", { date: doyLabel(h2.phase_day) }) }] : []),
            {
              label: t("hydro.temperature.explained"),
              value: `${fmt(h1.explained_variance * 100, 1)} %`,
              note: t("hydro.temperature.explained_all", { n: hr.n_harmonics, value: fmt(fit.r_squared * 100, 1) }),
            },
          ]}
        />
        <${Chart} spec=${cycleChart} />
        ${yearly ? html`<${Chart} spec=${yearly} />` : html`<p class="hy-note">${t("hydro.temperature.no_year_fit")}</p>`}
      `}
    </${Section}>`}
    ${keys.length > 0 &&
    html`<${Section} title=${t("hydro.temperature.days_part")}>
      <${Option} label=${t("hydro.temperature.threshold")}>
        <${Seg} value=${chosen} label=${t("hydro.temperature.threshold")} options=${keys.map((key) => [key, labels[key]])} onChange=${(threshold) => setOpt({ threshold })} />
      </${Option}>
      <${Section} states=${[events[chosen]].filter(active)}>
        ${er &&
        html`
          <${Figures}
            items=${[
              { label: t("hydro.temperature.days_beyond", { threshold: labels[chosen] }), value: fmt(er.days_beyond, 0), note: `${er.first_year}–${er.last_year}` },
              { label: t("hydro.temperature.runs"), value: fmt(er.n_events, 0) },
              {
                label: t("hydro.temperature.longest_run"),
                value: longest ? tn("hydro.axis.days", longest.duration_days) : "–",
                note: longest ? `${date(longest.start_date)}–${date(longest.end_date)}` : "",
              },
            ]}
          />
          <${Chart} spec=${days} />
        `}
      </${Section}>
    </${Section}>`}
    ${rows.length > 0 &&
    html`<${Section} title=${t("hydro.temperature.years_part")} states=${[characteristic].filter(active)}>
      <${Table} columns=${columns} rows=${rows} max=${12} className="tbl hy-compact" />
    </${Section}>`}
    <${Notices} states=${[harmonics, daily, characteristic, ...Object.values(events)]} />
  </div></${Section}>`;
}
