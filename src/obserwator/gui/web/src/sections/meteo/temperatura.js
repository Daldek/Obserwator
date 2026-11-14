// „Temperatura” (Nogat plan M11, M12, M14, M15): Hydrolog's monthly and annual means, the
// normal of a reference period and the anomalies, the extremes and the daily range
// (`temperature.means`, `temperature.range`), the characteristic days and degree days
// (`temperature.days`, `temperature.degree_days`), the climate stripes (stripes.js: the M15
// prototype's colour scale on Hydrolog's annual means), the harmonics of the annual cycle
// (`harmonics.Tmean`) and Sielianinov's hydrothermal coefficient (`hydrothermal`). Every
// number is a field of Hydrolog's result: the page picks, sorts for display, formats and
// draws; the harmonics Hydrolog fitted are evaluated at the chart's days (drawing).

import { Chart, fmt, html, t, tn, useMemo, useState } from "../../lib.js";
import { Figures, Notices, Section, Seg, Table, YearRange } from "../common.js";
import { Stripes } from "./stripes.js";
import {
  ClassLegend,
  MONTH_TICKS,
  Option,
  Periods,
  ROMAN,
  Source,
  byYear,
  classCls,
  date,
  dayLabel,
  entryOf,
  newestFirst,
  num,
  recordYears,
  takes,
  useMeteo,
  useOptions,
  yearAxis,
  yearAxisLabel,
  yearReadout,
} from "./util.js";

/** A signed number: "+1,3", "−0,4". */
function signed(value, digits = 1) {
  if (value === null || value === undefined || !Number.isFinite(value)) return "–";
  const text = fmt(Math.abs(value), digits);
  return value > 0 ? `+${text}` : value < 0 ? `−${text}` : text;
}

/** A threshold as Hydrolog gave it: whole degrees without decimals. */
function degrees(value) {
  return fmt(value, Number.isInteger(value) ? 0 : 1);
}

/** The rows of Hydrolog's 12 months by month number (a missing month is left out). */
function byMonth(months) {
  const found = new Map();
  for (const row of months || []) found.set(row.month, row);
  return found;
}

// --- means, extremes, the normal --------------------------------------------------------

/** The heat class of a monthly anomaly [°C], for the colour of its cell. */
function anomalyCls(value) {
  if (value === null || value === undefined) return "";
  if (value >= 2) return "me-a3";
  if (value >= 1) return "me-a2";
  if (value >= 0.25) return "me-a1";
  if (value <= -2) return "me-a-3";
  if (value <= -1) return "me-a-2";
  if (value <= -0.25) return "me-a-1";
  return "";
}

function AnomalyTable({ years }) {
  return html`<div class="table-wrap"><table class="tbl me-heat">
    <thead><tr><th scope="col">${t("meteo.common.year")}</th>${ROMAN.map((m) => html`<th scope="col">${m}</th>`)}</tr></thead>
    <tbody>${years.map((year) => {
      const months = byMonth(year.months);
      return html`<tr><th scope="row">${year.year}</th>${ROMAN.map((_, at) => {
        const value = months.has(at + 1) ? months.get(at + 1).anomaly_c : null;
        return html`<td class=${anomalyCls(value)}>${num(value, 1)}</td>`;
      })}</tr>`;
    })}</tbody>
  </table></div>`;
}

/** The chart of the means: the annual mean with the normal, the anomalies or the months. */
function meansChart(data, view) {
  if (!data) return null;
  const tmean = t("meteo.temperature.tmean");
  const period = data.period || {};
  if (view === "anomaly") {
    return {
      x: yearAxis(data.years),
      y: { label: t("meteo.temperature.anomaly_axis", { name: tmean }), unit: "°C", zero: true },
      series: [
        {
          id: "anomaly",
          kind: "bars",
          label: t("meteo.temperature.anomaly"),
          align: "center",
          data: data.years.map((r) => ({ x: r.year, y: r.anomaly_c, cls: r.anomaly_c === null ? "" : r.anomaly_c >= 0 ? "me-warm" : "me-cold" })),
          digits: 2,
        },
      ],
      readout: { x: yearReadout },
      fit: { ratio: 0.45, minHeight: 170 },
      title: t("meteo.temperature.anomaly_title"),
    };
  }
  if (view === "months") {
    const months = period.months || [];
    const series = [];
    if (period.tmax_c !== null && period.tmax_c !== undefined && period.tmin_c !== null && period.tmin_c !== undefined) {
      series.push({ id: "range", kind: "band", cls: "s4", label: t("meteo.temperature.band"), data: months.map((m) => [m.month, m.tmin_c ?? null, m.tmax_c ?? null]) });
    }
    series.push({ id: "mean", kind: "line", cls: "s1", label: t("meteo.temperature.mean_of", { name: tmean }), data: months.map((m) => [m.month, m.tmean_c ?? null]), digits: 1 });
    series.push({
      id: "normal",
      kind: "line",
      cls: "s6",
      label: t("meteo.common.normal", { from: data.reference_first_year, to: data.reference_last_year }),
      data: months.map((m) => [m.month, m.normal_c ?? null]),
      digits: 1,
    });
    return {
      x: { label: t("meteo.common.month_axis"), tickList: ROMAN.map((label, at) => ({ value: at + 1, label })), min: 1, max: 12 },
      y: { label: t("meteo.temperature.temperature_axis"), unit: "°C", zero: false },
      series,
      legend: true,
      readout: { x: (x) => ROMAN[Math.round(x) - 1] || "" },
      fit: { ratio: 0.5, minHeight: 190 },
      title: t("meteo.temperature.months_title"),
    };
  }
  const normal = period.normal_c;
  return {
    x: yearAxis(data.years),
    y: { label: t("meteo.temperature.mean_axis", { name: tmean }), unit: "°C", zero: false },
    series: [{ id: "mean", kind: "line", cls: "s1", label: t("meteo.temperature.annual_mean"), data: byYear(data.years, "tmean_c"), digits: 2 }],
    marks: normal === null || normal === undefined ? [] : [{ kind: "hline", y: normal, label: t("meteo.temperature.normal_value", { value: fmt(normal, 1) }) }],
    readout: { x: yearReadout },
    fit: { ratio: 0.45, minHeight: 170 },
    title: t("meteo.temperature.mean_title"),
  };
}

/** A temperature with the year of its date: "33,5 (1961)". */
function withYear(value, day) {
  return value === null || value === undefined ? "–" : `${fmt(value, 1)} (${day ? day.slice(0, 4) : "–"})`;
}

/** A temperature with its date: "33,5 (27.06.1961)". */
function withDate(value, day) {
  return value === null || value === undefined ? "–" : `${fmt(value, 1)} (${date(day)})`;
}

function Means({ station, means, range }) {
  const data = means.result;
  const dtr = range.result;
  const [view, setView] = useState("mean");
  const spec = useMemo(() => meansChart(data, view), [data, view]);
  const states = range.entry ? [means, range] : [means];
  const title = t("meteo.temperature.means.title");
  const info = t("meteo.temperature.means.info");
  if (!data) return html`<${Section} title=${title} info=${info} guide="metody-temperatura-srednie" states=${states} />`;
  const period = data.period || {};
  const tmean = t("meteo.temperature.tmean");
  const hasMax = period.max_c !== null && period.max_c !== undefined;
  const hasMin = period.min_c !== null && period.min_c !== undefined;
  const last = newestFirst(data.years).find((row) => row.tmean_c !== null && row.tmean_c !== undefined);
  const ranges = byMonth(dtr && dtr.period && dtr.period.months);
  const monthRows = (period.months || []).map((m) => ({ ...m, dtr_c: ranges.has(m.month) ? ranges.get(m.month).dtr_c : null }));
  const monthColumns = [
    { key: "month", label: t("meteo.common.month"), format: (v) => ROMAN[v - 1] },
    { key: "normal_c", label: t("meteo.temperature.col.normal"), format: (v) => num(v, 1) },
    { key: "tmean_c", label: tmean, format: (v) => num(v, 1) },
    ...(period.tmax_c !== null && period.tmax_c !== undefined ? [{ key: "tmax_c", label: "Tmax", format: (v) => num(v, 1) }] : []),
    ...(period.tmin_c !== null && period.tmin_c !== undefined ? [{ key: "tmin_c", label: "Tmin", format: (v) => num(v, 1) }] : []),
    ...(dtr ? [{ key: "dtr_c", label: t("meteo.temperature.col.range"), format: (v) => num(v, 1) }] : []),
    ...(hasMax ? [{ key: "max_c", label: t("meteo.temperature.col.abs_max"), format: (v, r) => withYear(v, r.max_date) }] : []),
    ...(hasMin ? [{ key: "min_c", label: t("meteo.temperature.col.abs_min"), format: (v, r) => withYear(v, r.min_date) }] : []),
  ];
  const yearColumns = [
    { key: "year", label: t("meteo.common.year"), format: (v) => String(v) },
    { key: "tmean_c", label: tmean, format: (v) => num(v, 2) },
    { key: "anomaly_c", label: t("meteo.temperature.col.anomaly"), format: (v) => signed(v, 2) },
    ...(hasMax ? [{ key: "max_c", label: t("meteo.temperature.col.max_date"), format: (v, r) => withDate(v, r.max_date) }] : []),
    ...(hasMin ? [{ key: "min_c", label: t("meteo.temperature.col.min_date"), format: (v, r) => withDate(v, r.min_date) }] : []),
  ];
  const figures = [
    {
      label: t("meteo.common.normal", { from: data.reference_first_year, to: data.reference_last_year }),
      value: num(period.normal_c, 1, "°C"),
      note: tn("meteo.temperature.normal_note", period.normal_years ?? 0),
    },
    ...(last
      ? [
          {
            label: t("meteo.temperature.year", { year: last.year }),
            value: num(last.tmean_c, 1, "°C"),
            note: last.anomaly_c === null || last.anomaly_c === undefined ? "" : t("meteo.temperature.anomaly_note", { value: signed(last.anomaly_c, 1) }),
          },
        ]
      : []),
    ...(hasMax ? [{ label: t("meteo.temperature.highest_tmax"), value: num(period.max_c, 1, "°C"), note: date(period.max_date) }] : []),
    ...(hasMin ? [{ label: t("meteo.temperature.lowest_tmin"), value: num(period.min_c, 1, "°C"), note: date(period.min_date) }] : []),
    ...(dtr && dtr.period ? [{ label: t("meteo.temperature.dtr"), value: num(dtr.period.dtr_c, 1, "°C"), note: t("meteo.temperature.on_average") }] : []),
  ];
  return html`<${Section} title=${title} info=${info} guide="metody-temperatura-srednie" states=${states}>
    <${Source} station=${station} doc=${means.data} variable="Tmean" />
    <${Notices} states=${states} />
    <${Figures} items=${figures} />
    <${Option} label=${t("meteo.common.chart")}>
      <${Seg}
        value=${view}
        label=${t("meteo.temperature.chart_label")}
        options=${[
          ["mean", t("meteo.temperature.view.mean")],
          ["anomaly", t("meteo.temperature.view.anomaly")],
          ["months", t("meteo.temperature.view.months")],
        ]}
        onChange=${setView}
      />
    </${Option}>
    <${Chart} spec=${spec} />
    <h4 class="me-sub">${t("meteo.temperature.months_table")}</h4>
    <${Table} columns=${monthColumns} rows=${monthRows} />
    <h4 class="me-sub">${t("meteo.temperature.years_table")}</h4>
    <${Table} columns=${yearColumns} rows=${newestFirst(data.years)} max=${10} />
    <details class="me-details">
      <summary>${t("meteo.temperature.anomalies_all")}</summary>
      <${AnomalyTable} years=${newestFirst(data.years)} />
    </details>
  </${Section}>`;
}

// --- characteristic days and degree days ----------------------------------------------------

/** The day counts of `temperature.days` and the sums of `temperature.degree_days`. */
const DAY_KEYS = ["frost_days", "ice_days", "summer_days", "hot_days", "tropical_nights"];
const DEGREE_KEYS = ["growing_degree_days", "heating_degree_days"];
const COLD = new Set(["frost_days", "ice_days", "heating_degree_days"]);

/** The definition of an index with the thresholds Hydrolog used. */
function ruleOf(key, days, degree) {
  const tmean = t("meteo.temperature.tmean");
  switch (key) {
    case "frost_days":
      return `Tmin < ${degrees(days.frost_tmin_c)} °C`;
    case "ice_days":
      return `Tmax < ${degrees(days.ice_tmax_c)} °C`;
    case "summer_days":
      return `Tmax > ${degrees(days.summer_tmax_c)} °C`;
    case "hot_days":
      return `Tmax > ${degrees(days.hot_tmax_c)} °C`;
    case "tropical_nights":
      return `Tmin > ${degrees(days.tropical_tmin_c)} °C`;
    case "growing_degree_days":
      return `Σ max(${tmean} − ${degrees(degree.growing_base_c)}, 0)`;
    default:
      return `Σ (${degrees(degree.heating_base_c)} − ${tmean}), ${tmean} ≤ ${degrees(degree.heating_limit_c)} °C`;
  }
}

function CharacteristicDays({ days, degree }) {
  const counts = days.result;
  const sums = degree.result;
  const keys = [
    ...(counts ? DAY_KEYS.filter((k) => counts.period && counts.period[k] !== null && counts.period[k] !== undefined) : []),
    ...(sums ? DEGREE_KEYS.filter((k) => sums.period && sums.period[k] !== null && sums.period[k] !== undefined) : []),
  ];
  const [chosen, setChosen] = useState("frost_days");
  const key = keys.includes(chosen) ? chosen : keys[0];
  const spec = useMemo(() => {
    if (!key) return null;
    const degreeKey = DEGREE_KEYS.includes(key);
    const source = degreeKey ? sums : counts;
    const name = t(`meteo.temperature.day.${key}`);
    const mean = source.period[key];
    return {
      x: yearAxis(source.years),
      y: degreeKey
        ? { label: `${name} [°C·d]`, unit: "°C·d" }
        : { label: t("meteo.temperature.days_axis", { name, rule: ruleOf(key, counts, sums) }), unit: t("meteo.common.days_unit") },
      series: [{ id: key, kind: "bars", cls: COLD.has(key) ? "me-bar-cold" : "me-bar-warm", label: name, align: "center", data: byYear(source.years, key) }],
      marks: [{ kind: "hline", y: mean, label: t("meteo.common.mean_value", { value: fmt(mean, degreeKey ? 0 : 1) }) }],
      readout: { x: yearReadout, value: (v) => fmt(v, 0) },
      fit: { ratio: 0.45, minHeight: 170 },
      title: t("meteo.temperature.days_title", { name }),
    };
  }, [counts, sums, key]);
  const states = [days, degree].filter((s) => s.entry);
  const title = t("meteo.temperature.days.title");
  const info = t("meteo.temperature.days.info");
  if (!keys.length) return html`<${Section} title=${title} info=${info} guide="metody-temperatura-dni" states=${states} />`;
  const countKeys = keys.filter((k) => DAY_KEYS.includes(k));
  return html`<${Section} title=${title} info=${info} guide="metody-temperatura-dni" states=${states}>
    <${Notices} states=${states} />
    <${Figures}
      items=${keys.map((k) => {
        const degreeKey = DEGREE_KEYS.includes(k);
        const source = degreeKey ? sums : counts;
        return { label: t(`meteo.temperature.day.${k}`), value: num(source.period[k], degreeKey ? 0 : 1), note: t("meteo.temperature.per_year", { rule: ruleOf(k, counts, sums) }) };
      })}
    />
    <${Option} label=${t("meteo.temperature.index")}>
      <${Seg} value=${key} label=${t("meteo.temperature.index")} options=${keys.map((k) => [k, t(`meteo.temperature.day.${k}`)])} onChange=${setChosen} />
    </${Option}>
    <${Chart} spec=${spec} />
    ${countKeys.length > 0 &&
    html`<h4 class="me-sub">${t("meteo.temperature.days_months")}</h4>
      <${Table}
        columns=${[{ key: "month", label: t("meteo.common.month"), format: (v) => ROMAN[v - 1] }, ...countKeys.map((k) => ({ key: k, label: t(`meteo.temperature.day.${k}`), format: (v) => num(v, 1) }))]}
        rows=${counts.period.months || []}
      />`}
  </${Section}>`;
}

// --- harmonics of the annual cycle ---------------------------------------------------------

/** The calendar day (1 = 1 January, a 365-day year) of a day of the hydrological year (1 = 1 November). */
function calendarDay(day) {
  return day > 61 ? day - 61 : day + 304;
}

/** The day of the hydrological year (1 = 1 November) of a calendar day (1 = 1 January). */
function hydrologicalDay(day) {
  return day > 304 ? day - 304 : day + 61;
}

/**
 * Hydrolog's fitted cycle at a day of the hydrological year: A₀ + Σ Cₖ cos(2πk(d − dₖ)/P)
 * over the first `count` harmonics (dₖ the day of the k-th harmonic's first maximum).
 */
function cycleAt(fit, periodDays, day, count) {
  let value = fit.mean;
  fit.harmonics.slice(0, count).forEach((harmonic, at) => {
    value += harmonic.amplitude * Math.cos((2 * Math.PI * (at + 1) * (day - harmonic.phase_day)) / periodDays);
  });
  return value;
}

/** A day of the hydrological year as its calendar date: "17 VII". */
function peakLabel(day) {
  return day === null || day === undefined ? "–" : dayLabel(calendarDay(day));
}

/** A share of the variance (a fraction) in percent. */
function percent(share, digits = 1) {
  return share === null || share === undefined ? "–" : fmt(share * 100, digits);
}

function Harmonics({ station, state, onRange }) {
  const data = state.result;
  const spec = useMemo(() => {
    if (!data) return null;
    const fit = data.period;
    const days = Array.from({ length: 365 }, (_, at) => at + 1);
    const peak = fit.harmonics[0] ? calendarDay(fit.harmonics[0].phase_day) : null;
    return {
      x: { label: t("meteo.harmonics.day_axis"), tickList: MONTH_TICKS, min: 1, max: 365 },
      y: { label: `${t("meteo.temperature.tmean")} [°C]`, unit: "°C", zero: false },
      series: [
        { id: "first", kind: "line", cls: "s2", label: t("meteo.harmonics.first"), data: days.map((d) => [d, cycleAt(fit, data.period_days, hydrologicalDay(d), 1)]), digits: 1 },
        { id: "fit", kind: "line", cls: "s1", label: tn("meteo.harmonics.fit", data.n_harmonics), data: days.map((d) => [d, cycleAt(fit, data.period_days, hydrologicalDay(d), data.n_harmonics)]), digits: 1 },
      ],
      marks: peak === null ? [] : [{ kind: "vline", x: peak, label: t("meteo.harmonics.max_mark", { date: dayLabel(peak) }) }],
      legend: true,
      readout: { series: "fit", x: (x) => dayLabel(x) },
      fit: { ratio: 0.5, minHeight: 190 },
      title: t("meteo.harmonics.cycle_title"),
    };
  }, [data]);
  const yearSpec = useMemo(() => {
    if (!data) return null;
    const points = data.years.filter((r) => r.harmonics[0]).map((r) => [r.year, calendarDay(r.harmonics[0].phase_day)]);
    return {
      x: yearAxis(points, yearAxisLabel("hydrological")),
      y: { label: t("meteo.harmonics.peak_axis"), unit: "", zero: false },
      series: [{ id: "peak", kind: "points", label: t("meteo.harmonics.peak_series"), data: points }],
      readout: { x: yearReadout, value: (v) => dayLabel(v) },
      fit: { ratio: 0.38, minHeight: 150 },
      title: t("meteo.harmonics.peak_title"),
    };
  }, [data]);
  const title = t("meteo.harmonics.title");
  const info = t("meteo.harmonics.info");
  const record = recordYears(station, state.data, "Tmean", "hydrological");
  const range = record && data ? html`<${YearRange} first=${record.first} last=${record.last} from=${data.first_year} to=${data.last_year} label=${t("meteo.harmonics.years")} onApply=${onRange(record)} />` : null;
  if (!data) return html`<${Section} title=${title} info=${info} guide="metody-temperatura-harmoniki" states=${[state]} />`;
  const fit = data.period;
  const [one, two] = fit.harmonics;
  const rows = newestFirst(data.years).map((r) => ({ ...r, c1: r.harmonics[0] || {}, c2: r.harmonics[1] || {} }));
  return html`<${Section} title=${title} info=${info} guide="metody-temperatura-harmoniki" states=${[state]}>
    ${range}
    <${Notices} states=${[state]} />
    <${Figures}
      items=${[
        { label: t("meteo.harmonics.mean"), value: num(fit.mean, 2, "°C"), note: tn("meteo.harmonics.years_note", data.period_years, { from: data.first_year, to: data.last_year }) },
        ...(one ? [{ label: t("meteo.harmonics.amplitude", { name: "C₁" }), value: num(one.amplitude, 2, "°C"), note: t("meteo.harmonics.peak", { date: peakLabel(one.phase_day) }) }] : []),
        ...(two ? [{ label: t("meteo.harmonics.amplitude", { name: "C₂" }), value: num(two.amplitude, 2, "°C"), note: t("meteo.harmonics.peak", { date: peakLabel(two.phase_day) }) }] : []),
        ...(one && two ? [{ label: t("meteo.harmonics.shares"), value: `${percent(one.explained_variance)} · ${percent(two.explained_variance, 2)} %` }] : []),
        { label: t("meteo.harmonics.r2"), value: `${percent(fit.r_squared)} %`, note: tn("meteo.harmonics.daily_values", fit.n_values) },
      ]}
    />
    <${Chart} spec=${spec} />
    <${Chart} spec=${yearSpec} />
    <h4 class="me-sub">${t("meteo.harmonics.years_table")}</h4>
    <${Table}
      columns=${[
        { key: "year", label: t("meteo.common.year"), format: (v) => String(v) },
        { key: "mean", label: "A₀", format: (v) => num(v, 2) },
        { key: "c1", label: "C₁", format: (v) => num(v.amplitude, 2) },
        { key: "c1", label: t("meteo.harmonics.col.max", { k: 1 }), format: (v) => peakLabel(v.phase_day) },
        ...(two
          ? [
              { key: "c2", label: "C₂", format: (v) => num(v.amplitude, 2) },
              { key: "c2", label: t("meteo.harmonics.col.max", { k: 2 }), format: (v) => peakLabel(v.phase_day) },
            ]
          : []),
        { key: "c1", label: t("meteo.harmonics.col.share", { k: 1 }), format: (v) => percent(v.explained_variance) },
        ...(two ? [{ key: "c2", label: t("meteo.harmonics.col.share", { k: 2 }), format: (v) => percent(v.explained_variance, 2) }] : []),
      ]}
      rows=${rows}
      max=${10}
    />
  </${Section}>`;
}

/** The harmonics of the annual cycle with their own hydrological years. */
function HarmonicsPart({ station, analyses }) {
  const [opt, setOpt] = useOptions({ first_year: undefined, last_year: undefined }, station.code);
  const state = useMeteo(station.code, analyses, "harmonics.Tmean", opt);
  const onRange = (record) => (a, b) => setOpt(a === record.first && b === record.last ? { first_year: undefined, last_year: undefined } : { first_year: a, last_year: b });
  return html`<${Harmonics} station=${station} state=${state} onRange=${onRange} />`;
}

// --- hydrothermal coefficient -------------------------------------------------------------

/** Skowera and Puła's classes of the coefficient as Hydrolog names them, driest first. */
const K_CLASSES = ["extremely_dry", "very_dry", "dry", "fairly_dry", "optimal", "fairly_wet", "wet", "very_wet", "extremely_wet"];
/** The bounds of the optimal class (Skowera and Puła 2004), marked on the chart. */
const OPTIMAL = [1.3, 1.6];
/** The years of the table of the months, newest first. */
const RECENT = 20;

function kClass(name) {
  const at = K_CLASSES.indexOf(name);
  return at < 0 ? null : at;
}

function className(name) {
  return name ? t(`meteo.hydrothermal.class.${name}`) : "";
}

function Hydrothermal({ state }) {
  const data = state.result;
  const spec = useMemo(() => {
    if (!data) return null;
    return {
      x: yearAxis(data.years),
      y: { label: t("meteo.hydrothermal.season"), unit: "" },
      series: [
        {
          id: "k",
          kind: "bars",
          label: "k",
          align: "center",
          data: data.years.map((r) => ({ x: r.year, y: r.season_coefficient, cls: classCls("k9", kClass(r.season_class)) })),
          digits: 2,
        },
      ],
      marks: OPTIMAL.map((y) => ({ kind: "hline", y, label: fmt(y, 1) })),
      readout: { x: yearReadout, value: (v) => fmt(v, 2) },
      fit: { ratio: 0.42, minHeight: 160 },
      title: t("meteo.hydrothermal.chart_title"),
    };
  }, [data]);
  const title = t("meteo.hydrothermal.title");
  const info = t("meteo.hydrothermal.info");
  if (!data) return html`<${Section} title=${title} info=${info} guide="metody-temperatura-hydrotermiczny" states=${[state]} />`;
  const period = data.period;
  const months = (period.months || []).map((m) => m.month);
  const rows = newestFirst(data.years);
  return html`<${Section} title=${title} info=${info} guide="metody-temperatura-hydrotermiczny" states=${[state]}>
    <${Notices} states=${[state]} />
    <${Figures}
      items=${[
        {
          label: t("meteo.hydrothermal.season"),
          value: num(period.mean_season_coefficient, 2),
          note: period.mean_season_class ? t("meteo.hydrothermal.mean_class", { name: className(period.mean_season_class) }) : "",
        },
        ...(period.months || []).map((m) => ({
          label: t("meteo.hydrothermal.month_mean", { month: ROMAN[m.month - 1] }),
          value: num(m.mean_coefficient, 2),
          note: tn("meteo.temperature.years_count", m.n_years),
        })),
      ]}
    />
    <${Chart} spec=${spec} />
    <h4 class="me-sub">${t("meteo.hydrothermal.months_table", { first: ROMAN[months[0] - 1] || "", last: ROMAN[months[months.length - 1] - 1] || "" })}</h4>
    <div class="table-wrap"><table class="tbl me-heat">
      <thead><tr>
        <th scope="col">${t("meteo.common.year")}</th>
        ${months.map((m) => html`<th scope="col">${ROMAN[m - 1]}</th>`)}
        <th scope="col">${t("meteo.hydrothermal.col.season")}</th>
      </tr></thead>
      <tbody>${rows.slice(0, RECENT).map((r) => {
        const cells = byMonth(r.months);
        return html`<tr><th scope="row">${r.year}</th>
          ${months.map((m) => {
            const cell = cells.get(m) || {};
            return html`<td class=${classCls("k9", kClass(cell.sielianinov_class))} title=${className(cell.sielianinov_class)}>${num(cell.coefficient, 2)}</td>`;
          })}
          <td class=${classCls("k9", kClass(r.season_class))} title=${className(r.season_class)}>${num(r.season_coefficient, 2)}</td>
        </tr>`;
      })}</tbody>
    </table></div>
    ${rows.length > RECENT ? html`<p class="muted me-caption">${t("meteo.hydrothermal.last_years", { shown: RECENT, count: rows.length })}</p>` : null}
    <${ClassLegend} names=${K_CLASSES.map(className)} palette="k9" />
    <h4 class="me-sub">${t("meteo.hydrothermal.frequency")}</h4>
    <div class="table-wrap"><table class="tbl me-heat">
      <thead><tr>
        <th scope="col">${t("meteo.common.month")}</th>
        ${K_CLASSES.map((name, at) => html`<th scope="col" class=${classCls("k9", at)} title=${className(name)}>${at + 1}</th>`)}
      </tr></thead>
      <tbody>${(period.months || []).map(
        (m) => html`<tr><th scope="row">${ROMAN[m.month - 1]}</th>${K_CLASSES.map((name) => html`<td>${(m.class_counts || {})[name] ?? "–"}</td>`)}</tr>`,
      )}</tbody>
    </table></div>
  </${Section}>`;
}

// --- the card ---------------------------------------------------------------------------------

/**
 * The card „Temperatura”: the period of every calendar-year analysis and the reference
 * period of the normal in its toolbar; the stripes and the harmonics need the daily mean
 * temperature, the coefficient also precipitation.
 *
 * @param {{station: object, session: object|null, analyses: object[]}} props
 */
export function Temperatura({ station, session, analyses }) {
  const code = station.code;
  const [opt, setOpt] = useOptions({ first_year: undefined, last_year: undefined, reference_first_year: undefined, reference_last_year: undefined }, code);
  const period = { first_year: opt.first_year, last_year: opt.last_year };
  const means = useMeteo(code, analyses, "temperature.means", opt);
  const range = useMeteo(code, analyses, "temperature.range", period);
  const days = useMeteo(code, analyses, "temperature.days", period);
  const degree = useMeteo(code, analyses, "temperature.degree_days", period);
  const hydrothermal = useMeteo(code, analyses, "hydrothermal", period);
  const anchor = [means, days, degree, range, hydrothermal].find((s) => s.data && s.result);
  const variable = means.entry || degree.entry || hydrothermal.entry ? "Tmean" : "Tmax";
  return html`<div class="me-card">
    <div class="me-toolbar">
      <${Periods}
        station=${station}
        doc=${anchor ? anchor.data : null}
        variable=${variable}
        result=${anchor ? anchor.result : null}
        opt=${opt}
        setOpt=${setOpt}
        reference=${takes(means.entry, "reference_first_year")}
      />
    </div>
    ${means.entry && html`<${Means} station=${station} means=${means} range=${range} />`}
    ${means.entry && html`<${Stripes} station=${station} session=${session} />`}
    ${(days.entry || degree.entry) && html`<${CharacteristicDays} days=${days} degree=${degree} />`}
    ${entryOf(analyses, "harmonics.Tmean") && html`<${HarmonicsPart} station=${station} analyses=${analyses} />`}
    ${hydrothermal.entry && html`<${Hydrothermal} state=${hydrothermal} />`}
  </div>`;
}
