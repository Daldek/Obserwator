// „Przepływy maksymalne i minimalne” (Nogat plan H5, H6, H16): Hydrolog's `stats
// flood-frequency` of the annual maxima (`flood_frequency.Q`: IMGW-PIB's half-years where the
// store has them, else the daily series), `stats homogeneity` of the same maxima
// (`homogeneity.Q`) and `stats low-flow` of the annual minima of the daily series
// (`low_flow.Q`). The curves are Hydrolog's quantiles at the registry's return periods.

import { Chart, fmt, html, lang, t, useEffect, useMemo, useState } from "../../lib.js";
import { Figures, Notices, Section, Table, useAnalysis } from "../common.js";
import { HALF_YEARS, Handoff, Option, Select, Years, analysisIds, dailyDataset, fmtV, useOptions, withUnit } from "./util.js";

/** The return periods of the quantile tables by default [years]: p = 50 … 0,1 %. */
const TABLE_PERIODS = [2, 5, 10, 20, 50, 100, 200, 500, 1000];
/** The registry's return periods (`flood_frequency.Q`, `low_flow.Q`): the tables' and 100/p of the curves' points. */
const CURVE_PERIODS = [
  1.0101010101, 1.0204081633, 1.0526315789, 1.1111111111, 1.25, 1.4285714286, 1.6666666667, 2.0, 2.5, 3.3333333333, 5.0, 6.6666666667,
  10.0, 14.2857142857, 20.0, 33.3333333333, 50.0, 66.6666666667, 100.0, 142.8571428571, 200.0, 333.3333333333, 500.0, 666.6666666667,
  1000.0,
];
const MAX_PERIODS = 20;
const DISTRIBUTIONS = ["all", "log_normal", "gev", "pearson3", "weibull"];
const METHODS = ["l_moments", "mle", "moments", "least_squares", "all"];
const DIST_CLASS = { gev: "s1", log_normal: "s2", pearson3: "s3", weibull: "s6" };
const METHOD_CLASS = { l_moments: "fm-lmom", mle: "fm-mle", moments: "fm-mom", least_squares: "fm-lsq" };
/** Names of distributions, the same in every language except the log-normal. */
const NAMES = { gev: "GEV", pearson3: "Pearson III", weibull: "Weibull" };

function distName(name) {
  return name === "log_normal" ? t("hydro.extremes.dist_log_normal") : NAMES[name] || name;
}

function label(item, many) {
  return many ? `${distName(item.distribution_name)} · ${t(`hydro.extremes.method_short.${item.fit_method}`)}` : distName(item.distribution_name);
}

/** The position of a return period in Hydrolog's list. */
function at(periods, period) {
  return periods.findIndex((value) => Math.abs(value - period) <= 1e-6 * period);
}

/** A probability given as a fraction, in percent: „1 %”, „0,1 %”. */
function percent(fraction) {
  const p = fraction * 100;
  return `${fmt(p, p >= 1 ? 0 : 1)} %`;
}

/** The return periods typed by the person: numbers above 1, at most 20; null when not valid. */
function parsePeriods(text) {
  const parts = text
    .split(/[;\s]+|,(?!\d)/)
    .map((part) => part.trim().replace(",", "."))
    .filter(Boolean);
  const values = parts.map(Number);
  if (!values.length || values.length > MAX_PERIODS || values.some((v) => !Number.isFinite(v) || v <= 1)) return null;
  return [...new Set(values)].sort((a, b) => a - b);
}

/** The override of `return_periods` for the tables' periods: none when the registry's list has them all. */
function periodsOverride(periods) {
  if (periods.every((period) => at(CURVE_PERIODS, period) >= 0)) return undefined;
  return [...new Set([...CURVE_PERIODS, ...periods])].sort((a, b) => a - b);
}

function PeriodsForm({ periods, onApply }) {
  const shown = periods.map((p) => fmt(p, Number.isInteger(p) ? 0 : 1)).join("; ");
  const [text, setText] = useState(shown);
  useEffect(() => setText(shown), [shown]);
  const parsed = parsePeriods(text);
  return html`<form class="years hy-periods" onSubmit=${(e) => (e.preventDefault(), parsed && onApply(parsed))}>
    <label>${t("hydro.extremes.periods")} <input type="text" inputmode="decimal" value=${text} onInput=${(e) => setText(e.target.value)} /></label>
    <button type="submit" disabled=${!parsed}>${t("sections.recompute")}</button>
    <small class=${parsed ? "years-note" : "years-note warn"}>${t("hydro.extremes.periods_note", { count: MAX_PERIODS })}</small>
  </form>`;
}

function QuantileTable({ periods, items, many }) {
  const first = items[0];
  const columns = [
    { key: "p", label: "p", format: (v) => v },
    { key: "T", label: t("hydro.extremes.col_t"), format: (v) => fmt(v, Number.isInteger(v) ? 0 : 1) },
    ...items.map((item, column) => ({ key: `d${column}`, label: label(item, many), format: (v) => fmtV(v, "Q") })),
  ];
  const rows = periods
    .map((period) => ({ period, row: at(first.return_periods, period) }))
    .filter((item) => item.row >= 0)
    .map(({ period, row }) => {
      const out = { p: percent(first.exceedance_probabilities[row]), T: period };
      items.forEach((item, column) => (out[`d${column}`] = item.quantiles[at(item.return_periods, period)]));
      return out;
    });
  return html`<${Table} columns=${columns} rows=${rows} className="tbl hy-quantiles" />`;
}

function FitTable({ items, many }) {
  const columns = [
    { key: "label", label: t("hydro.extremes.distribution"), format: (v) => v },
    { key: "aic", label: "AIC", format: (v) => fmt(v, 1) },
    { key: "ks", label: "KS (p)", format: (v, row) => `${fmt(row.ks_statistic, 3)} (${fmt(v, 2)}${row.ks_valid === false ? "*" : ""})` },
    { key: "ad", label: "A²", format: (v, row) => `${fmt(v, 3)}${row.ad5 !== undefined && v > row.ad5 ? " > 5 %" : ""}` },
    { key: "params", label: t("hydro.extremes.col_parameters"), format: (v) => v },
  ];
  const rows = items.map((item) => ({
    label: label(item, many),
    aic: item.aic,
    ks: item.ks_p_value,
    ks_statistic: item.ks_statistic,
    ks_valid: item.ks_valid,
    ad: item.ad_statistic,
    ad5: item.ad_critical_values ? item.ad_critical_values["5%"] : undefined,
    params: Object.entries(item.parameters || {})
      .map(([k, v]) => `${k} ${fmt(v, Math.abs(v) >= 100 ? 1 : 3)}`)
      .join(", "),
  }));
  return html`<${Table} columns=${columns} rows=${rows} />
    <p class="muted hy-caption">${t("hydro.extremes.fit_caption")}</p>`;
}

function Homogeneity({ state }) {
  const result = state.result;
  const rows = result
    ? [
        ["mann_whitney", result.mann_whitney],
        ["kolmogorov_smirnov", result.kolmogorov_smirnov],
        ["pettitt", result.pettitt],
      ].map(([name, test]) => ({ name: t(`hydro.extremes.test.${name}`), statistic: test.statistic, p: test.p_value, ok: test.homogeneous }))
    : [];
  const columns = result && [
    { key: "name", label: "Test", format: (v) => v },
    { key: "statistic", label: t("hydro.extremes.col_statistic"), format: (v) => fmt(v, Math.abs(v) >= 10 ? 0 : 3) },
    { key: "p", label: "p", format: (v) => fmt(v, 3) },
    { key: "ok", label: t("hydro.extremes.col_homogeneous"), format: (v) => t(v ? "hydro.extremes.yes" : "hydro.extremes.no") },
  ];
  return html`<${Section} title=${t("hydro.extremes.homogeneity_title")} info=${t("hydro.extremes.homogeneity_info")} guide="metody-extremes-jednorodnosc" states=${[state]}>
    ${result &&
    html`<${Table} columns=${columns} rows=${rows} className="tbl hy-compact" />
      <p class="muted hy-caption">
        ${t("hydro.extremes.alpha", { alpha: fmt(result.significance_level, 2) })}
        ${" "}${result.split_year
          ? t("hydro.extremes.split_year", { year: result.split_year, n: result.n_years })
          : t("hydro.extremes.split_index", { count: result.split_index, n: result.n_years })}
        ${" "}${result.pettitt.change_point_year ? t("hydro.extremes.change_point", { year: result.pettitt.change_point_year }) : ""}
      </p>`}
    <${Notices} states=${[state]} />
  </${Section}>`;
}

function LowFlow({ state, code, session, periods }) {
  const result = state.result;
  const fitted = result && result.fisher_tippett;
  const spec = useMemo(() => {
    if (!fitted) return null;
    return {
      x: { scale: "gumbel", domain: [99, 0.1], label: t("hydro.extremes.low_axis") },
      y: { label: "NQ [m³/s]", unit: "m³/s" },
      series: [
        { id: "ft", kind: "line", cls: "s3", label: t("hydro.extremes.low_curve"), data: fitted.non_exceedance_probabilities.map((p, i) => [p * 100, fitted.quantiles[i]]).sort((a, b) => b[0] - a[0]) },
        { id: "emp", kind: "points", label: t("hydro.extremes.low_points"), data: result.empirical.non_exceedance_probabilities.map((p, i) => [p * 100, result.empirical.values_ascending[i]]), readout: false },
      ],
      legend: true,
      readout: { series: "ft" },
      fit: { ratio: 0.6, minHeight: 220 },
      title: t("hydro.extremes.low_chart"),
    };
  }, [result, lang()]);
  const lowest = result && result.empirical.values_ascending[0];
  const lowestYear = result && result.hydrological_years[result.annual_minima.indexOf(lowest)];
  const ten = fitted ? at(fitted.return_periods, 10) : -1;
  const columns = [
    { key: "f", label: "F", format: (v) => v },
    { key: "T", label: t("hydro.extremes.col_t"), format: (v) => fmt(v, Number.isInteger(v) ? 0 : 1) },
    { key: "q", label: "NQ_T [m³/s]", format: (v) => fmtV(v, "Q") },
  ];
  const rows = fitted
    ? periods
        .map((period) => at(fitted.return_periods, period))
        .filter((row) => row >= 0)
        .map((row) => ({ f: percent(fitted.non_exceedance_probabilities[row]), T: fitted.return_periods[row], q: fitted.quantiles[row] }))
    : [];
  const years = result ? result.hydrological_years : [];
  return html`<${Section} title=${t("hydro.extremes.low_title")} info=${t("hydro.extremes.low_info")} guide="metody-extremes-minima" states=${[state]}>
    ${result &&
    html`<${Figures}
        items=${[
          { label: t("hydro.extremes.fig_years"), value: fmt(result.n_years, 0), note: years.length ? `${years[0]}–${years[years.length - 1]}` : "" },
          { label: "NNQ", value: withUnit(lowest, "Q"), note: lowestYear ? t("hydro.common.year_n", { year: lowestYear }) : "" },
          { label: t("hydro.extremes.fig_low_10"), value: ten >= 0 ? withUnit(fitted.quantiles[ten], "Q") : "–", note: "F = 10 %" },
          { label: t("hydro.extremes.col_parameters"), value: Object.entries(fitted.parameters).map(([k, v]) => `${k} ${fmt(v, 3)}`).join(", ") },
        ]}
      />
      <${Chart} spec=${spec} />
      <${Table} columns=${columns} rows=${rows} />
      ${result.incomplete_years && result.incomplete_years.length
        ? html`<p class="muted hy-caption">${t("hydro.extremes.incomplete", { years: result.incomplete_years.join(", ") })}</p>`
        : null}
      ${years.length > 0 &&
      html`<${Handoff} code=${code} session=${session} variable="Q" resolution="daily" from=${years[0]} to=${years[years.length - 1]} doc=${state.data} />`}`}
    <${Notices} states=${[state]} />
  </${Section}>`;
}

/** The section „Przepływy maksymalne i minimalne”. */
export function Extremes({ station, session, analyses }) {
  const code = station.code;
  const ids = analysisIds(analyses);
  const list = Array.isArray(analyses) ? analyses : (analyses && analyses.analyses) || [];
  const entry = list.find((item) => item.analysis === "flood_frequency.Q");
  const maximaDataset = entry && entry.inputs && entry.inputs[0] ? entry.inputs[0].dataset : dailyDataset(station);
  const [opt, setOpt] = useOptions({ distribution: "all", fit_method: "l_moments", from: undefined, to: undefined, periods: TABLE_PERIODS }, code);
  const returnPeriods = periodsOverride(opt.periods);
  const years = { first_year: opt.from, last_year: opt.to };
  const overrides = {
    distribution: opt.distribution === "all" ? undefined : opt.distribution,
    fit_method: opt.fit_method === "l_moments" ? undefined : opt.fit_method,
    return_periods: returnPeriods,
    ...years,
  };
  const state = useAnalysis(code, ids.has("flood_frequency.Q") ? "flood_frequency.Q" : null, overrides);
  const homogeneity = useAnalysis(code, ids.has("homogeneity.Q") ? "homogeneity.Q" : null, years);
  const low = useAnalysis(code, ids.has("low_flow.Q") ? "low_flow.Q" : null, { return_periods: returnPeriods, ...years });
  const result = state.result;
  const many = result && result.fit_method === "all";
  const spec = useMemo(() => {
    if (!result) return null;
    const series = result.distributions.map((item, row) => ({
      id: `${item.distribution_name}-${item.fit_method}`,
      kind: "line",
      cls: `${DIST_CLASS[item.distribution_name] || "s4"} ${METHOD_CLASS[item.fit_method] || ""}${row === 0 ? " best" : ""}`,
      label: label(item, many),
      data: item.exceedance_probabilities.map((p, i) => [p * 100, item.quantiles[i]]).sort((a, b) => b[0] - a[0]),
    }));
    series.push({ id: "emp", kind: "points", label: t("hydro.extremes.max_points"), data: result.empirical.exceedance_prob.map((p, i) => [p * 100, result.empirical.values_sorted[i]]), readout: false });
    return {
      x: { scale: "gumbel", domain: [99, 0.1], label: t("hydro.extremes.max_axis") },
      y: { label: "WQ [m³/s]", unit: "m³/s" },
      series,
      legend: [
        ...result.distributions.map((item, row) => ({
          label: row === 0 ? t("hydro.extremes.best_label", { name: label(item, many) }) : label(item, many),
          kind: "stroke",
          cls: `${DIST_CLASS[item.distribution_name] || "s4"} ${METHOD_CLASS[item.fit_method] || ""}`,
        })),
        { label: t("hydro.extremes.max_points_legend"), kind: "points" },
      ],
      readout: { series: series[0].id },
      fit: { ratio: 0.66, minHeight: 240 },
      title: t("hydro.extremes.max_chart"),
    };
  }, [result, lang()]);
  const best = result && result.distributions[0];
  const hundred = best ? at(best.return_periods, 100) : -1;
  const highest = result && result.empirical.values_sorted[0];
  const highestYear = result && result.hydrological_years[result.annual_maxima.indexOf(highest)];
  const fromHalfYears = result ? result.source === "half_years" : maximaDataset === HALF_YEARS;
  return html`<div class="hy-card">
    <${Years}
      station=${station}
      variables=${["Q"]}
      dataset=${maximaDataset}
      from=${opt.from}
      to=${opt.to}
      onApply=${(from, to) => setOpt({ from, to })}
    />
    <${Section} title=${t("hydro.extremes.max_title")} info=${t("hydro.extremes.max_info")} guide="metody-extremes-maksima" states=${[state]}>
      <div class="hy-options">
        <${Option} label=${t("hydro.extremes.distribution")}><${Select}
          value=${opt.distribution}
          label=${t("hydro.extremes.distribution")}
          options=${DISTRIBUTIONS.map((d) => [d, d === "all" ? t("hydro.extremes.dist_all") : distName(d)])}
          onChange=${(v) => setOpt({ distribution: v })}
        /></${Option}>
        <${Option} label=${t("hydro.extremes.fit_method")}><${Select}
          value=${opt.fit_method}
          label=${t("hydro.extremes.fit_method")}
          options=${METHODS.map((m) => [m, t(`hydro.extremes.method.${m}`)])}
          onChange=${(v) => setOpt({ fit_method: v })}
        /></${Option}>
      </div>
      <p class="muted hy-caption">${t(fromHalfYears ? "hydro.extremes.source_half" : "hydro.extremes.source_daily")}</p>
      ${result &&
      html`<${Figures}
          items=${[
            { label: t("hydro.extremes.fig_years"), value: fmt(result.n_years, 0), note: `${result.hydrological_years[0]}–${result.hydrological_years[result.hydrological_years.length - 1]}` },
            { label: "WWQ", value: withUnit(highest, "Q"), note: highestYear ? t("hydro.common.year_n", { year: highestYear }) : "" },
            { label: t("hydro.extremes.fig_best"), value: label(best, many) },
            { label: "Q1% (T = 100)", value: hundred >= 0 ? withUnit(best.quantiles[hundred], "Q") : "–", note: label(best, many) },
          ]}
        />
        <${Chart} spec=${spec} />
        <h4 class="hy-sub">${t("hydro.extremes.quantiles_title")}</h4>
        <${PeriodsForm} periods=${opt.periods} onApply=${(periods) => setOpt({ periods })} />
        <${QuantileTable} periods=${opt.periods} items=${result.distributions} many=${many} />
        <${FitTable} items=${result.distributions} many=${many} />
        ${result.incomplete_years && result.incomplete_years.length
          ? html`<p class="muted hy-caption">${t("hydro.extremes.incomplete", { years: result.incomplete_years.join(", ") })}</p>`
          : null}
        <${Handoff} code=${code} session=${session} variable="Q" resolution="annual" analysis="flood_frequency.Q" overrides=${overrides} />
        <p class="muted hy-caption">${t("hydro.extremes.handoff_note")}</p>`}
      <${Notices} states=${[state]} />
    </${Section}>
    ${ids.has("homogeneity.Q") && html`<${Homogeneity} state=${homogeneity} />`}
    ${ids.has("low_flow.Q") && html`<${LowFlow} state=${low} code=${code} session=${session} periods=${opt.periods} />`}
  </div>`;
}
