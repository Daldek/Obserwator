// „Reżim i sezonowość” (Nogat plan H10 to H13): the daily regime (Hydrolog's `stats daily`,
// O2's ids `daily.{H,Q,T}`) and the monthly statistics (`stats monthly`, `monthly.{H,Q,T}`) of
// the station's whole record; Pardé's coefficients with Dynowska's regime type (`stats
// regime`, `regime.Q`) and the dates of the annual extremes on the circle of the year
// (`stats seasonality`, `seasonality.Q.{max,min}`) over the whole record or the years the
// person chooses. Every number is Hydrolog's; the page only places the dates on the circle.

import { Chart, fmt, html, t, tn, useMemo } from "../../lib.js";
import { periodName } from "../../words.js";
import { Figures, Notices, Section, Seg, Table, useAnalysis } from "../common.js";
import { DOY_TICKS, HYDRO_MONTHS, Option, ROMAN, UNITS, VariableSeg, Years, date, digitsOf, doyLabel, fmtV, recordYears, useOptions, withUnit } from "./util.js";

const VARIABLES = ["Q", "H", "T"];
const REGIME = "regime.Q";
const SEASONALITY = { max: "seasonality.Q.max", min: "seasonality.Q.min" };
/** Calendar months in the order of the hydrological year. */
const CALENDAR = [11, 12, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10];
const MONTH_TICKS = HYDRO_MONTHS.map((label, at) => ({ value: at + 1, label }));
/** Dynowska's regime types by Hydrolog's code (1 to 5). */
const TYPES = { 1: "nival_weak", 2: "nival_moderate", 3: "nival_strong", 4: "nival_pluvial", 5: "pluvial_nival" };
/** The symbols of the annual extremes of the discharge. */
const EXTREME_NAMES = { max: "WQ", min: "NQ" };

/** A state worth listing: its id applies (it loads, has a result or failed). */
const active = (state) => state.loading || state.data || state.error;

/** The daily regime: the band of the extremes of each day with the mean and the median. */
function dailySpec(result, variable) {
  const u = UNITS[variable];
  const days = result.day_of_year;
  const log = variable === "Q" && result.min_values.every((value) => value === null || value > 0);
  return {
    x: { label: t("hydro.axis.hydro_day"), tickList: DOY_TICKS, min: 1, max: 366 },
    y: { label: log ? t("hydro.axis.q_log") : `${variable} [${u}]`, unit: u, scale: log ? "log" : "linear", zero: false, digits: digitsOf(variable) },
    series: [
      { id: "range", kind: "band", cls: "s4", label: t("hydro.regime.range"), data: days.map((day, at) => [day, result.min_values[at], result.max_values[at]]) },
      { id: "mean", kind: "line", cls: "s1", label: t("hydro.regime.mean"), data: days.map((day, at) => [day, result.mean_values[at]]) },
      { id: "median", kind: "line", cls: "s5", label: t("hydro.regime.median"), data: days.map((day, at) => [day, result.median_values[at]]) },
    ],
    legend: true,
    readout: { series: "mean", x: doyLabel },
    fit: { ratio: 0.55, minHeight: 210 },
    title: t("hydro.regime.daily_title"),
  };
}

/** The rows of the monthly statistics in the order of the hydrological year. */
function monthlyRows(result) {
  return CALENDAR.map((month, at) => {
    const i = result.months.indexOf(month);
    return {
      at: at + 1,
      month: HYDRO_MONTHS[at],
      mean: result.mean_values[i],
      median: result.median_values[i],
      min: result.min_values[i],
      max: result.max_values[i],
      std: result.std_values[i],
      cv: result.cv_values[i],
      skew: result.skewness_values[i],
      low: result.ci_lower[i],
      high: result.ci_upper[i],
    };
  });
}

/** The monthly statistics: the confidence interval of the mean, the mean and the median. */
function monthlySpec(result, variable) {
  const u = UNITS[variable];
  const rows = monthlyRows(result);
  return {
    x: { label: t("hydro.axis.month"), tickList: MONTH_TICKS, min: 0.5, max: 12.5 },
    y: { label: `${variable} [${u}]`, unit: u, zero: variable === "Q", digits: digitsOf(variable) },
    series: [
      { id: "ci", kind: "band", cls: "s1", label: t("hydro.regime.ci", { level: fmt(result.confidence_level * 100, 0) }), data: rows.map((row) => [row.at, row.low, row.high]) },
      { id: "mean", kind: "line", cls: "s1", label: t("hydro.regime.mean"), data: rows.map((row) => [row.at, row.mean]) },
      { id: "median", kind: "line", cls: "s5", label: t("hydro.regime.median"), data: rows.map((row) => [row.at, row.median]) },
    ],
    legend: true,
    readout: { series: "mean", x: (x) => HYDRO_MONTHS[Math.round(x) - 1] || "" },
    fit: { ratio: 0.45, minHeight: 180 },
    title: t("hydro.regime.monthly_title"),
  };
}

/** Pardé's coefficients of the months, November first, against the annual mean (1). */
function pardeSpec(result) {
  const ticks = result.months.map((month, at) => ({ value: at + 1, label: ROMAN[month - 1] }));
  return {
    x: { label: t("hydro.axis.month"), tickList: ticks, min: 0.5, max: 12.5 },
    y: { label: t("hydro.regime.parde_axis"), digits: 2 },
    series: [{ id: "pk", kind: "bars", cls: "s1", align: "center", label: "Qm / Qr", data: result.parde.map((value, at) => [at + 1, value]) }],
    marks: [{ kind: "hline", y: 1, label: fmt(1, 2) }],
    readout: { x: (x) => (ticks[Math.round(x) - 1] || {}).label || "" },
    fit: { ratio: 0.42, minHeight: 170 },
    title: t("hydro.regime.parde_title"),
  };
}

/** The day of the calendar year (1 = 1 January) of an ISO date and the year's length. */
function calendarDay(iso) {
  const year = +iso.slice(0, 4);
  const day = (Date.UTC(year, +iso.slice(5, 7) - 1, +iso.slice(8, 10)) - Date.UTC(year, 0, 1)) / 86400000 + 1;
  const leap = (year % 4 === 0 && year % 100 !== 0) || year % 400 === 0;
  return [day, leap ? 366 : 365];
}

/** The day of the hydrological year (1 = 1 November) of an ISO date. */
function hydroDay(iso) {
  const year = +iso.slice(0, 4);
  const month = +iso.slice(5, 7);
  const start = Date.UTC(month >= 11 ? year : year - 1, 10, 1);
  return Math.round((Date.UTC(year, month - 1, +iso.slice(8, 10)) - start) / 86400000) + 1;
}

/** Whether a date falls in the winter half-year (XI–IV). */
const inWinter = (iso) => {
  const month = +iso.slice(5, 7);
  return month >= 11 || month <= 4;
};

/** „06-08” (Hydrolog's mean date) as „8 VI”. */
const dayMonth = (text) => `${+text.slice(3, 5)} ${ROMAN[+text.slice(0, 2) - 1]}`;

/**
 * The circle of the year (1 I at the top, clockwise) with each year's date of the extreme
 * at Hydrolog's angle of it, the years outwards, and Hydrolog's mean date as a vector of
 * the length r.
 */
function Circle({ result, name }) {
  const c = 100;
  const R = 78;
  const y0 = result.first_year;
  const y1 = result.last_year;
  const position = (angle, radius) => [c + radius * Math.sin(angle), c - radius * Math.cos(angle)];
  const ticks = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334].map((day, at) => ({ angle: (2 * Math.PI * day) / 365, label: ROMAN[at] }));
  const mean = position((2 * Math.PI * (result.mean_day - 0.5)) / 365.25, result.concentration * R);
  return html`<figure class="hy-circle">
    <svg viewBox="0 0 200 200" role="img" aria-label=${t("hydro.regime.circle_label", { name })}>
      <circle class="hy-circle-ring" cx=${c} cy=${c} r=${R} />
      <circle class="hy-circle-ring inner" cx=${c} cy=${c} r=${R / 2} />
      ${ticks.map(({ angle, label }) => {
        const [x1, y1t] = position(angle, R - 4);
        const [x2, y2] = position(angle, R + 4);
        const [tx, ty] = position(angle + Math.PI / 12, R + 13);
        return html`<g><line class="hy-circle-tick" x1=${x1} y1=${y1t} x2=${x2} y2=${y2} /><text class="hy-circle-label" x=${tx} y=${ty + 3}>${label}</text></g>`;
      })}
      ${result.years.map((row) => {
        const [day, length] = calendarDay(row.date);
        const radius = 22 + ((R - 28) * (row.year - y0)) / Math.max(1, y1 - y0);
        const [x, y] = position((2 * Math.PI * (day - 0.5)) / length, radius);
        return html`<circle class=${`hy-circle-dot ${inWinter(row.date) ? "winter" : "summer"}`} cx=${x} cy=${y} r="3">
          <title>${row.year}: ${date(row.date)}, ${withUnit(row.value, "Q")}</title>
        </circle>`;
      })}
      <line class="hy-circle-mean" x1=${c} y1=${c} x2=${mean[0]} y2=${mean[1]} />
      <circle class="hy-circle-head" cx=${mean[0]} cy=${mean[1]} r="3.5" />
    </svg>
    <figcaption>${t("hydro.regime.circle_caption", { name, from: y0, to: y1 })}</figcaption>
  </figure>`;
}

/** Each year's date of the extreme in its hydrological year, by half-year. */
function datesSpec(result, name) {
  const point = (row) => ({ x: hydroDay(row.date), y: row.year });
  return {
    x: { label: t("hydro.axis.hydro_day"), tickList: DOY_TICKS, min: 1, max: 366 },
    y: { label: t("hydro.axis.hydro_year"), digits: 0, zero: false, min: result.first_year - 1, max: result.last_year + 1 },
    series: [
      { id: "winter", kind: "points", cls: "s1", label: periodName("winter"), data: result.years.filter((row) => inWinter(row.date)).map(point) },
      { id: "summer", kind: "points", cls: "s2", label: periodName("summer"), data: result.years.filter((row) => !inWinter(row.date)).map(point) },
    ],
    legend: true,
    readout: { x: doyLabel, value: (value) => String(Math.round(value)) },
    fit: { ratio: 0.8, minHeight: 220 },
    title: t("hydro.regime.dates_title", { name }),
  };
}

/** The section „Reżim i sezonowość”. */
export function Regime({ station, analyses }) {
  const code = station.code;
  const ids = new Set((analyses || []).map((item) => item.analysis));
  const variables = VARIABLES.filter((v) => ids.has(`daily.${v}`) || ids.has(`monthly.${v}`));
  const [opt, setOpt] = useOptions({ var: undefined, from: undefined, to: undefined, extreme: "max" }, code);
  const variable = variables.includes(opt.var) ? opt.var : variables[0];
  const daily = useAnalysis(code, variable && ids.has(`daily.${variable}`) ? `daily.${variable}` : null);
  const monthly = useAnalysis(code, variable && ids.has(`monthly.${variable}`) ? `monthly.${variable}` : null);
  const period = { first_year: opt.from, last_year: opt.to };
  const regime = useAnalysis(code, ids.has(REGIME) ? REGIME : null, period);
  const seasons = useAnalysis(code, ids.has(SEASONALITY[opt.extreme]) ? SEASONALITY[opt.extreme] : null, period);
  const dr = daily.result;
  const mr = monthly.result;
  const rr = regime.result;
  const sr = seasons.result;
  const name = EXTREME_NAMES[opt.extreme];
  const dailyChart = useMemo(() => dr && dailySpec(dr, variable), [dr, variable]);
  const monthlyChart = useMemo(() => mr && monthlySpec(mr, variable), [mr, variable]);
  const parde = useMemo(() => rr && pardeSpec(rr), [rr]);
  const dates = useMemo(() => sr && sr.years.length && datesSpec(sr, name), [sr, name]);
  const record = variable ? recordYears(station, [variable]) : null;
  const flows = recordYears(station, ["Q"]);
  const chosen = opt.from !== undefined || opt.to !== undefined;
  const applyYears = (from, to) => setOpt({ from: flows && from === flows.first ? undefined : from, to: flows && to === flows.last ? undefined : to });
  const extremes = ids.has(SEASONALITY.max) || ids.has(SEASONALITY.min);
  const columns = variable && [
    { key: "month", label: t("hydro.regime.col.month"), format: (v) => v },
    { key: "mean", label: t("hydro.regime.col.mean"), format: (v) => fmtV(v, variable) },
    { key: "median", label: t("hydro.regime.col.median"), format: (v) => fmtV(v, variable) },
    { key: "min", label: t("hydro.regime.col.min"), format: (v) => fmtV(v, variable) },
    { key: "max", label: t("hydro.regime.col.max"), format: (v) => fmtV(v, variable) },
    { key: "std", label: t("hydro.regime.col.std"), format: (v) => fmtV(v, variable) },
    { key: "cv", label: "CV", format: (v) => fmt(v, 2) },
    { key: "skew", label: t("hydro.regime.col.skew"), format: (v) => fmt(v, 2) },
    {
      key: "low",
      label: t("hydro.regime.col.ci", { level: mr ? fmt(mr.confidence_level * 100, 0) : "" }),
      format: (v, row) => `${fmtV(row.low, variable)}–${fmtV(row.high, variable)}`,
    },
  ];
  const type = rr && rr.regime_type;
  const criteria = type && type.criteria;
  return html`<${Section} info=${t("hydro.regime.info")}><div class="hy-card">
    ${variables.length > 0 &&
    html`<${Section} title=${t("hydro.regime.daily_monthly_title")}>
      ${variables.length > 1 &&
      html`<${Option} label=${t("hydro.regime.variable")}><${VariableSeg} value=${variable} variables=${variables} onChange=${(v) => setOpt({ var: v })} /></${Option}>`}
      ${record && html`<p class="muted hy-caption">${t("hydro.regime.whole_record", { from: record.first, to: record.last })}</p>`}
      <${Section} states=${[daily, monthly].filter(active)}>
        ${dr && html`<h4 class="hy-sub">${t("hydro.regime.daily_title")}</h4><${Chart} spec=${dailyChart} />`}
        ${mr &&
        html`<h4 class="hy-sub">${t("hydro.regime.monthly_title")}</h4>
          <${Chart} spec=${monthlyChart} />
          <${Table} columns=${columns} rows=${monthlyRows(mr)} className="tbl hy-compact" />`}
      </${Section}>
    </${Section}>`}
    ${(ids.has(REGIME) || extremes) &&
    html`<${Section}><div class="hy-card">
      <${Years} station=${station} variables=${["Q"]} from=${opt.from} to=${opt.to} onApply=${applyYears} label=${t("hydro.axis.hydro_years")} />
      ${chosen && variables.length > 0 && html`<p class="muted hy-caption">${t("hydro.regime.period_scope")}</p>`}
    ${ids.has(REGIME) &&
    html`<${Section} title=${t("hydro.regime.parde_title")} states=${[regime]}>
      ${rr &&
      html`
        <${Figures}
          items=${[
            { label: t("hydro.regime.type"), value: t(`hydro.regime.type.${TYPES[type.code]}`), note: t("hydro.regime.type_note", { code: type.code }) },
            { label: t("hydro.regime.spring"), value: `${ROMAN[criteria.spring_month - 1]}: ${fmt(criteria.spring_coefficient * 100, 0)} %` },
            { label: t("hydro.regime.summer"), value: `${ROMAN[criteria.summer_month - 1]}: ${fmt(criteria.summer_coefficient * 100, 0)} %` },
            { label: t("hydro.regime.spring_share"), value: `${fmt(rr.spring_share * 100, 1)} %`, note: t("hydro.regime.spring_share_note") },
            { label: t("hydro.regime.seasonality_index"), value: fmt(rr.seasonality_index, 3), note: t("hydro.regime.seasonality_index_note") },
          ]}
        />
        <${Chart} spec=${parde} />
        <p class="muted hy-caption">
          ${t("hydro.regime.criteria", {
            weak: fmt(criteria.nival_limits[0] * 100, 0),
            strong: fmt(criteria.nival_limits[1] * 100, 0),
            rise: fmt(criteria.summer_rise * 100, 0),
            equal: fmt(criteria.nearly_equal * 100, 0),
            from: rr.first_year,
            to: rr.last_year,
            years: tn("hydro.axis.years", rr.period_years),
          })}
        </p>
      `}
    </${Section}>`}
    ${extremes &&
    html`<${Section} title=${t("hydro.regime.extremes_title")}>
      <${Option} label=${t("hydro.regime.extremes")}>
        <${Seg}
          value=${opt.extreme}
          label=${t("hydro.regime.extremes")}
          options=${[["max", t("hydro.regime.maxima")], ["min", t("hydro.regime.minima")]]}
          onChange=${(extreme) => setOpt({ extreme })}
        />
      </${Option}>
      <${Section} states=${[seasons].filter(active)}>
        ${sr &&
        (sr.years.length
          ? html`
              <${Figures}
                items=${[
                  {
                    label: t("hydro.regime.mean_date", { name }),
                    value: dayMonth(sr.mean_date),
                    note: `${tn("hydro.axis.years", sr.period_years)} ${sr.first_year}–${sr.last_year}`,
                  },
                  { label: t("hydro.regime.concentration"), value: fmt(sr.concentration, 2), note: t("hydro.regime.concentration_note") },
                  { label: t("hydro.regime.winter_share"), value: `${fmt(sr.winter_share * 100, 0)} %`, note: "XI–IV" },
                  { label: t("hydro.regime.source"), value: t(`hydro.regime.source.${sr.source}`) },
                ]}
              />
              <div class="hy-pair">
                <${Circle} result=${sr} name=${name} />
                <div class="hy-pair-side"><${Chart} spec=${dates} /></div>
              </div>
            `
          : html`<p class="hy-note">${t("hydro.regime.no_dates")}</p>`)}
      </${Section}>
    </${Section}>`}
    </div></${Section}>`}
    <${Notices} states=${[daily, monthly, regime, seasons]} />
  </div></${Section}>`;
}
