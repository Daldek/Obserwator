// „Trendy i bilans” (Nogat plan H16 to H18): the Mann–Kendall test with Sen's slope of the
// annual maxima, means and minima (Hydrolog's `stats mann-kendall`, O2's ids
// `mann_kendall.{Q,H,T}.{max,mean,min}`, on the annual values of `characteristic.{Q,H,T}` that
// O2 passes it and keeps in the result's options), the runoff volumes (`stats runoff-volume`,
// `runoff_volume.Q`) and the baseflow with its index (`stats baseflow`, `baseflow.Q`), over the
// whole record or the years the person chooses. Every number is Hydrolog's; Sen's line is
// its slope and intercept evaluated at the ends of the chart.

import { Chart, dayNumber, fmt, html, t, tn, useMemo } from "../../lib.js";
import { Figures, Notices, Section, Seg, Table, YearRange, useAnalysis } from "../common.js";
import { recordOf } from "./duration.js";
import { DOY_TICKS, HYDRO_MONTHS, Option, Select, UNITS, VariableSeg, dailyDataset, digitsOf, doyLabel, fmtV, useOptions, useSeries } from "./util.js";

const VARIABLES = ["Q", "H", "T"];
const STATISTICS = ["max", "mean", "min"];
const RUNOFF = "runoff_volume.Q";
const BASEFLOW = "baseflow.Q";
const MILLION = 1e6;
/** The symbols of the annual series of the discharge and the water level. */
const SYMBOLS = { Q: { max: "WQ", mean: "SQ", min: "NQ" }, H: { max: "WW", mean: "SW", min: "NW" } };
const MONTH_TICKS = HYDRO_MONTHS.map((label, at) => ({ value: at + 1, label }));

/** The name of an annual series: „WQ”, or the words of the water temperature's. */
function seriesName(variable, statistic) {
  return SYMBOLS[variable] ? SYMBOLS[variable][statistic] : t(`hydro.trends.t_name.${statistic}`);
}

/** A state worth listing: its id applies (it loads, has a result or failed). */
const active = (state) => state.loading || state.data || state.error;

/** A volume in m³ shown in million m³. */
const millions = (m3, digits = 1) => t("hydro.volume.value", { value: fmt(m3 / MILLION, digits) });

/** The annual values the test got (O2 keeps them in the result's options) as chart points. */
function pointsOf(doc) {
  const options = (doc && doc.options) || {};
  return Array.isArray(options.years) && Array.isArray(options.values) ? options.years.map((year, at) => [year, options.values[at]]) : [];
}

/** The annual series with Hydrolog's Sen line over its years. */
function trendSpec(doc, variable, name) {
  const result = doc.envelope.result;
  const points = pointsOf(doc);
  const u = UNITS[variable];
  const series = [{ id: "v", kind: "line", cls: "s1", label: name, unit: u, data: points }];
  if (points.length && result.sen_slope !== null && result.sen_slope !== undefined) {
    const ends = [points[0][0], points[points.length - 1][0]];
    series.push({
      id: "sen",
      kind: "line",
      cls: "s2",
      label: t("hydro.trends.sen_label", { slope: fmtV(result.sen_slope * 10, variable), unit: u }),
      unit: u,
      data: ends.map((year) => [year, result.sen_intercept + result.sen_slope * year]),
    });
  }
  return {
    x: { label: t("hydro.axis.hydro_year"), digits: 0, min: points.length ? points[0][0] - 1 : undefined, max: points.length ? points[points.length - 1][0] + 1 : undefined },
    y: { label: `${name} [${u}]`, unit: u, zero: false, digits: digitsOf(variable) },
    series,
    legend: true,
    readout: { series: "v", x: (x) => t("hydro.axis.year", { year: Math.round(x) }) },
    fit: { ratio: 0.45, minHeight: 180 },
    title: t("hydro.trends.chart_title", { name }),
  };
}

/** The table of the tests of the annual series. */
function TrendTable({ variable, states }) {
  const rows = STATISTICS.filter((statistic) => states[statistic].result).map((statistic) => {
    const doc = states[statistic].data;
    const result = states[statistic].result;
    const points = pointsOf(doc);
    return {
      name: seriesName(variable, statistic),
      period: points.length ? `${points[0][0]}–${points[points.length - 1][0]}` : "–",
      s: result.s_statistic,
      z: result.z_score,
      p: result.p_value,
      trend: t(`hydro.trends.direction.${result.trend_direction}`),
      alpha: result.significance_level,
      slope: result.sen_slope,
      low: result.sen_slope_lower,
      high: result.sen_slope_upper,
    };
  });
  if (!rows.length) return null;
  const columns = [
    { key: "name", label: t("hydro.trends.col.series"), format: (v) => v },
    { key: "period", label: t("hydro.trends.col.years"), format: (v) => v },
    { key: "s", label: "S", format: (v) => fmt(v, 0) },
    { key: "z", label: "Z", format: (v) => fmt(v, 2) },
    { key: "p", label: "p", format: (v) => fmt(v, 3) },
    { key: "trend", label: t("hydro.trends.col.trend", { alpha: fmt(rows[0].alpha, 2) }), format: (v) => v },
    {
      key: "slope",
      label: t("hydro.trends.col.sen", { unit: UNITS[variable] }),
      format: (v, row) => (v === null || v === undefined ? "–" : `${fmtV(v * 10, variable)} (${fmtV(row.low * 10, variable)} … ${fmtV(row.high * 10, variable)})`),
    },
  ];
  return html`<${Table} columns=${columns} rows=${rows} />`;
}

/** The runoff volumes: the years, the months, and one year's cumulative volume against the mean. */
function Runoff({ state, onYear }) {
  const result = state.result;
  const specs = useMemo(() => {
    if (!result) return null;
    const mean = result.mean_annual_volume_m3;
    const days = (values) => values.map((value, at) => [at + 1, value === null ? null : value / MILLION]);
    return {
      annual: {
        x: { label: t("hydro.axis.hydro_year"), digits: 0, min: result.first_year - 1, max: result.last_year + 1 },
        y: { label: t("hydro.volume.axis"), unit: t("hydro.volume.unit"), digits: 1 },
        series: [
          {
            id: "v",
            kind: "bars",
            cls: "s1",
            align: "center",
            label: t("hydro.trends.annual_series"),
            data: result.years.map((row) => ({ x: row.year, y: row.volume_m3 / MILLION, cls: row.complete ? undefined : "hy-incomplete" })),
          },
        ],
        marks: mean === null ? [] : [{ kind: "hline", y: mean / MILLION, label: t("hydro.trends.mean_mark", { value: fmt(mean / MILLION, 0) }) }],
        readout: { x: (x) => t("hydro.axis.year", { year: Math.round(x) }) },
        fit: { ratio: 0.42, minHeight: 170 },
        title: t("hydro.trends.annual_title"),
      },
      monthly: {
        x: { label: t("hydro.axis.month"), tickList: MONTH_TICKS, min: 0.5, max: 12.5 },
        y: { label: t("hydro.volume.axis"), unit: t("hydro.volume.unit"), digits: 1 },
        series: [
          {
            id: "m",
            kind: "bars",
            cls: "s1",
            align: "center",
            label: t("hydro.trends.monthly_series"),
            data: result.monthly_mean_volume_m3.map((value, at) => [at + 1, value === null ? null : value / MILLION]),
          },
        ],
        readout: { x: (x) => HYDRO_MONTHS[Math.round(x) - 1] || "" },
        fit: { ratio: 0.38, minHeight: 150 },
        title: t("hydro.trends.monthly_title"),
      },
      cumulative: {
        x: { label: t("hydro.axis.hydro_day"), tickList: DOY_TICKS, min: 1, max: 366 },
        y: { label: t("hydro.volume.axis"), unit: t("hydro.volume.unit"), digits: 1 },
        series: [
          ...(result.mean_cumulative_volume_m3
            ? [
                {
                  id: "mean",
                  kind: "line",
                  cls: "s4",
                  label: t("hydro.trends.cumulative_mean", { years: tn("hydro.trends.complete_years", result.n_complete_years) }),
                  data: days(result.mean_cumulative_volume_m3),
                },
              ]
            : []),
          { id: "year", kind: "line", cls: "s1", label: t("hydro.axis.year", { year: result.cumulative_year }), data: days(result.cumulative_volume_m3) },
        ],
        legend: true,
        readout: { series: "year", x: doyLabel },
        fit: { ratio: 0.45, minHeight: 180 },
        title: t("hydro.trends.cumulative_title"),
      },
    };
  }, [result]);
  const chosen = result && result.years.find((row) => row.year === result.cumulative_year);
  const incomplete = (row) => t("hydro.trends.incomplete_note", { present: fmt(row.days_with_data, 0), days: fmt(row.days, 0) });
  return html`<${Section} title=${t("hydro.trends.runoff_title")} states=${[state].filter(active)}>
    ${result &&
    html`
      <${Figures}
        items=${[
          {
            label: t("hydro.trends.mean_annual"),
            value: result.mean_annual_volume_m3 === null ? "–" : millions(result.mean_annual_volume_m3),
            note: tn("hydro.trends.complete_years", result.n_complete_years),
          },
          {
            label: t("hydro.axis.year_title", { year: result.cumulative_year }),
            value: chosen ? millions(chosen.volume_m3) : "–",
            note: chosen && !chosen.complete ? incomplete(chosen) : "",
          },
        ]}
      />
      <${Chart} spec=${specs.annual} />
      <${Chart} spec=${specs.monthly} />
      <${Option} label=${t("hydro.trends.year")}>
        <${Select}
          value=${result.cumulative_year}
          label=${t("hydro.axis.hydro_year")}
          options=${[...result.years].reverse().map((row) => [row.year, row.complete ? String(row.year) : t("hydro.trends.incomplete_option", { year: row.year })])}
          onChange=${(v) => onYear(+v)}
        />
      </${Option}>
      <${Chart} spec=${specs.cumulative} />
    `}
  </${Section}>`;
}

/** The daily discharge of the year Hydrolog separated (the series) with its baseflow. */
function Separation({ station, result }) {
  const year = result.series_year;
  const series = useSeries(dailyDataset(station), station.code, ["Q"], { start: `${year - 1}-11-01`, end: `${year}-10-31` });
  const doc = series.data;
  const spec = useMemo(() => {
    if (!doc || !doc.values || !doc.values.Q) return null;
    return {
      x: { scale: "date" },
      y: { label: t("hydro.axis.q_log"), unit: "m³/s", scale: "log", zero: false },
      series: [
        { id: "q", kind: "line", cls: "s1", label: t("hydro.trends.flow"), unit: "m³/s", data: doc.dates.map((day, at) => [dayNumber(day), doc.values.Q[at]]) },
        { id: "b", kind: "line", cls: "s3", label: t("hydro.trends.baseflow"), unit: "m³/s", data: result.series_dates.map((day, at) => [dayNumber(day), result.series_baseflow[at]]) },
      ],
      legend: true,
      readout: { series: "q" },
      fit: { ratio: 0.5, minHeight: 190 },
      title: t("hydro.trends.separation_title", { year }),
    };
  }, [doc, result]);
  if (series.error) return html`<p class="ana-error">${series.error.message}</p>`;
  if (!spec) return html`<p class="muted">${t("hydro.trends.year_loading", { year })}</p>`;
  return html`<div class=${series.loading ? "is-loading" : ""}><${Chart} spec=${spec} /></div>`;
}

/** The baseflow: its index over the period and per year, the recession, one year separated. */
function Baseflow({ station, state, onYear }) {
  const result = state.result;
  const yearly = useMemo(
    () =>
      result && {
        x: { label: t("hydro.axis.hydro_year"), digits: 0, min: result.first_year - 1, max: result.last_year + 1 },
        y: { label: "BFI", digits: 2, min: 0, max: 1 },
        series: [{ id: "bfi", kind: "bars", cls: "s3", align: "center", label: "BFI", data: result.years.map((row) => [row.year, row.bfi]) }],
        marks: [{ kind: "hline", y: result.bfi, label: t("hydro.trends.bfi_mark", { value: fmt(result.bfi, 2) }) }],
        readout: { x: (x) => t("hydro.axis.year", { year: Math.round(x) }) },
        fit: { ratio: 0.4, minHeight: 160 },
        title: t("hydro.trends.bfi_title"),
      },
    [result],
  );
  const recession = result && result.recession;
  return html`<${Section} title=${t("hydro.trends.baseflow_title")} states=${[state].filter(active)}>
    ${result &&
    html`
      <${Figures}
        items=${[
          { label: "BFI", value: fmt(result.bfi, 3), note: `${result.first_year}–${result.last_year}, ${tn("hydro.axis.days", result.n_values)}` },
          {
            label: t("hydro.trends.recession"),
            value: recession && recession.k !== null ? fmt(recession.k, 4) : "–",
            note: recession ? tn("hydro.trends.segments", recession.n_segments) : "",
          },
          { label: t("hydro.trends.half_life"), value: recession && recession.half_life_days !== null ? tn("hydro.axis.days", recession.half_life_days) : "–" },
          { label: t("hydro.trends.filter"), value: `α = ${fmt(result.alpha, 3)}`, note: t("hydro.trends.filter_note", { passes: fmt(result.passes, 0) }) },
        ]}
      />
      <${Chart} spec=${yearly} />
      <${Option} label=${t("hydro.trends.year")}>
        <${Select}
          value=${result.series_year}
          label=${t("hydro.axis.hydro_year")}
          options=${[...result.years].reverse().map((row) => [row.year, String(row.year)])}
          onChange=${(v) => onYear(+v)}
        />
      </${Option}>
      <${Separation} station=${station} result=${result} />
    `}
  </${Section}>`;
}

/** The section „Trendy i bilans”. */
export function Trends({ station, analyses }) {
  const code = station.code;
  const ids = new Set((analyses || []).map((item) => item.analysis));
  const variables = VARIABLES.filter((v) => STATISTICS.some((statistic) => ids.has(`mann_kendall.${v}.${statistic}`)));
  const [opt, setOpt] = useOptions({ var: undefined, from: undefined, to: undefined, pick: "max", ryear: undefined, byear: undefined }, code);
  const variable = variables.includes(opt.var) ? opt.var : variables[0];
  const period = { first_year: opt.from, last_year: opt.to };
  const id = (statistic) => (variable && ids.has(`mann_kendall.${variable}.${statistic}`) ? `mann_kendall.${variable}.${statistic}` : null);
  const trends = { max: useAnalysis(code, id("max"), period), mean: useAnalysis(code, id("mean"), period), min: useAnalysis(code, id("min"), period) };
  const runoff = useAnalysis(code, ids.has(RUNOFF) ? RUNOFF : null, { ...period, cumulative_year: opt.ryear });
  const base = useAnalysis(code, ids.has(BASEFLOW) ? BASEFLOW : null, { ...period, series_year: opt.byear });
  const record = recordOf(station, [...new Set([variable, ids.has(RUNOFF) || ids.has(BASEFLOW) ? "Q" : null].filter(Boolean))]);
  const picks = STATISTICS.filter((statistic) => id(statistic));
  const pick = picks.includes(opt.pick) ? opt.pick : picks[0];
  const shown = pick && trends[pick].data && trends[pick].result ? trends[pick].data : null;
  const name = pick ? seriesName(variable, pick) : "";
  const spec = useMemo(() => shown && trendSpec(shown, variable, name), [shown, variable, name]);
  const apply = (from, to) =>
    setOpt({ from: record && from === record.first ? undefined : from, to: record && to === record.last ? undefined : to, ryear: undefined, byear: undefined });
  return html`<${Section} info=${t("hydro.trends.info")} guide="metody-trends"><div class="hy-card">
    ${record &&
    html`<${YearRange}
      first=${record.first}
      last=${record.last}
      from=${opt.from ?? record.first}
      to=${opt.to ?? record.last}
      onApply=${apply}
      label=${t("hydro.axis.hydro_years")}
    />`}
    ${variables.length > 0 &&
    html`<${Section} title=${t("hydro.trends.annual_trends_title")}>
      ${variables.length > 1 &&
      html`<${Option} label=${t("hydro.trends.variable")}><${VariableSeg} value=${variable} variables=${variables} onChange=${(v) => setOpt({ var: v })} /></${Option}>`}
      <p class="muted hy-caption">${t("hydro.trends.source_note")}</p>
      <${Section} states=${Object.values(trends).filter(active)}>
        <${TrendTable} variable=${variable} states=${trends} />
        ${picks.length > 1 &&
        html`<${Option} label=${t("hydro.trends.chart")}>
          <${Seg} value=${pick} label=${t("hydro.trends.chart")} options=${picks.map((statistic) => [statistic, seriesName(variable, statistic)])} onChange=${(v) => setOpt({ pick: v })} />
        </${Option}>`}
        ${spec && html`<${Chart} spec=${spec} />`}
      </${Section}>
    </${Section}>`}
    ${ids.has(RUNOFF) && html`<${Runoff} state=${runoff} onYear=${(year) => setOpt({ ryear: year })} />`}
    ${ids.has(BASEFLOW) && html`<${Baseflow} station=${station} state=${base} onYear=${(year) => setOpt({ byear: year })} />`}
    <${Notices} states=${[...Object.values(trends), runoff, base]} />
  </div></${Section}>`;
}
