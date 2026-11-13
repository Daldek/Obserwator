// „Przepływy maksymalne i minimalne” (Nogat plan H5, H6, H16): Hydrolog's
// `stats flood-frequency` and `stats homogeneity` of annual maxima, `stats low-flow` of minima.

import { Chart, fmt, html, useMemo } from "../../lib.js";
import { Figures, Section, Seg, Table, useAnalysis } from "../common.js";
import { Block, Handoff, Notices, Option, Select, Years, date, fmtV, useOptions } from "./util.js";

const INFO = `Kwantyle przepływów maksymalnych rocznych liczy Hydrolog („stats flood-frequency”) dokładnie jak jego CLI: rozkłady log-normalny, GEV, Pearsona III i Weibulla, domyślnie metodą L-momentów (Hosking i Wallis 1997), z miarami zgodności KS, A² Andersona–Darlinga i AIC; rozkłady są ułożone wg AIC. Źródło maksimów: „półrocza IMGW-PIB” to większe z opublikowanych maksimów półrocznych (mogą być chwilowe; decyzja F1 planu), podane Hydrologowi jako gotowe maksima; „szereg dobowy” to wartości dobowe z datami, z których Hydrolog sam wybiera maksima pełnych lat hydrologicznych XI–X (tak, jak z eksportu szeregu z Obserwatora; lata z brakami pomija). Punkty empiryczne mają prawdopodobieństwo przewyższenia m/(n+1). Jednorodność maksimów sprawdza „stats homogeneity” (Manna–Whitneya, Kołmogorowa–Smirnowa i Pettitta). Przepływy minimalne: „stats low-flow” dopasowuje rozkład Fishera–Tippetta minimów (GEV dla minimów) do minimów pełnych lat szeregu dobowego; T = 1/F, F – prawdopodobieństwo nieprzekroczenia. Ten sam szereg i opcje trafiają do Hydrologa przez „Kopiuj do Hydrologa” i „Plik przekazania”.`;

const DIST = { gev: "GEV", log_normal: "log-normalny", pearson3: "Pearson III", weibull: "Weibull" };
const DIST_CLASS = { gev: "s1", log_normal: "s2", pearson3: "s3", weibull: "s6" };
const METHOD = { l_moments: "L-momenty", mle: "NW", moments: "momenty", least_squares: "MNK" };
const METHOD_CLASS = { l_moments: "fm-lmom", mle: "fm-mle", moments: "fm-mom", least_squares: "fm-lsq" };

function label(item, many) {
  return many ? `${DIST[item.name] || item.name} · ${METHOD[item.method] || item.method}` : DIST[item.name] || item.name;
}

function pLabel(period) {
  const p = 100 / period;
  return `${fmt(p, p >= 1 ? 0 : 1)} %`;
}

function QuantileTable({ periods, items, many }) {
  const columns = [
    { key: "p", label: "p", format: (v) => v },
    { key: "T", label: "T [lata]", format: (v) => fmt(v, 0) },
    ...items.map((item, at) => ({ key: `d${at}`, label: label(item, many), format: (v) => fmtV(v, "Q") })),
  ];
  const rows = periods.map((period, row) => {
    const out = { p: pLabel(period), T: period };
    items.forEach((item, at) => (out[`d${at}`] = item.quantiles[row]));
    return out;
  });
  return html`<${Table} columns=${columns} rows=${rows} className="tbl hy-quantiles" />`;
}

function FitTable({ items, many }) {
  const columns = [
    { key: "label", label: "Rozkład", format: (v) => v },
    { key: "aic", label: "AIC", format: (v) => fmt(v, 1) },
    { key: "ks", label: "KS (p)", format: (v, row) => `${fmt(row.ks_statistic, 3)} (${fmt(v, 2)}${row.ks_valid === false ? "*" : ""})` },
    { key: "ad", label: "A²", format: (v, row) => `${fmt(v, 3)}${row.ad5 !== undefined && v > row.ad5 ? " > 5 %" : ""}` },
    { key: "params", label: "parametry", format: (v) => v },
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
    <p class="muted hy-caption">* p-value KS orientacyjne: parametry oszacowano z tej samej próby (Hydrolog: porządkuj wg AIC). A² porównany z wartością krytyczną 5 %.</p>`;
}

function Homogeneity({ result }) {
  if (!result) return null;
  const rows = [
    ["Manna–Whitneya U", result.mann_whitney],
    ["Kołmogorowa–Smirnowa", result.kolmogorov_smirnov],
    ["Pettitta", result.pettitt],
  ].map(([name, test]) => ({ name, statistic: test.statistic, p: test.p_value, ok: test.homogeneous }));
  const columns = [
    { key: "name", label: "Test", format: (v) => v },
    { key: "statistic", label: "statystyka", format: (v) => fmt(v, Math.abs(v) >= 10 ? 0 : 3) },
    { key: "p", label: "p", format: (v) => fmt(v, 3) },
    { key: "ok", label: `jednorodny (α = ${fmt(result.significance_level, 2)})`, format: (v) => (v ? "tak" : "nie") },
  ];
  return html`<h4 class="hy-sub">Jednorodność maksimów (stats homogeneity)</h4>
    <${Table} columns=${columns} rows=${rows} />
    <p class="muted hy-caption">Podział: ${result.split_year ? `lata przed ${result.split_year} i od ${result.split_year}` : `pierwsze ${result.split_index} i pozostałe wartości`}; punkt zmiany wg Pettitta: ${result.pettitt.change_point_year ?? `wartość nr ${result.pettitt.change_point_index}`}.</p>`;
}

function LowFlow({ state, code }) {
  const data = state.data;
  const spec = useMemo(() => {
    if (!data) return null;
    return {
      x: { scale: "gumbel", domain: [99, 0.1], label: "prawdopodobieństwo nieprzekroczenia minimów" },
      y: { label: "NQ [m³/s]", unit: "m³/s" },
      series: [
        { id: "ft", kind: "line", cls: "s3", label: "Fisher–Tippett (GEV minimów)", data: data.curve },
        { id: "emp", kind: "points", label: "minima roczne", data: data.empirical, readout: false },
      ],
      legend: true,
      readout: { series: "ft" },
      fit: { ratio: 0.6, minHeight: 220 },
      title: "Minima roczne i rozkład Fishera–Tippetta",
    };
  }, [data]);
  const columns = [
    { key: "p", label: "F", format: (v) => v },
    { key: "T", label: "T [lata]", format: (v) => fmt(v, 0) },
    { key: "q", label: "NQ_T [m³/s]", format: (v) => fmtV(v, "Q") },
  ];
  const lowest = data && data.minima.reduce((a, b) => (b.value < a.value ? b : a), data.minima[0]);
  return html`<${Block} state=${state} title="Przepływy minimalne (H6)">
    ${data && html`
      <${Figures}
        items=${[
          { label: "Lat pełnych", value: fmt(data.n_years, 0), note: `${data.years.from}–${data.years.to}` },
          { label: "NNQ", value: `${fmtV(lowest.value, "Q")} m³/s`, note: date(lowest.date) },
          { label: "NQ 10 lat", value: `${fmtV(data.quantiles[2], "Q")} m³/s`, note: "F = 10 %" },
          { label: "Parametry", value: Object.entries(data.parameters).map(([k, v]) => `${k} ${fmt(v, 3)}`).join(", ") },
        ]}
      />
      <${Chart} spec=${spec} />
      <${Table} columns=${columns} rows=${data.table_periods.map((period, at) => ({ p: pLabel(period), T: period, q: data.quantiles[at] }))} />
      ${data.incomplete_years && data.incomplete_years.length ? html`<p class="muted hy-caption">Pominięte lata niepełne: ${data.incomplete_years.map((y) => y.year ?? y).join(", ")}.</p>` : null}
      <${Handoff} code=${code} variable="Q" resolution="daily" from=${data.years.from} to=${data.years.to} computed=${data.computed_by[0]} result=${{ quantiles: Object.fromEntries(data.table_periods.map((t, at) => [t, data.quantiles[at]])) }} />
      <${Notices} items=${data.notices} />
    `}
  </${Block}>`;
}

/** The section „Przepływy maksymalne i minimalne”. */
export function Extremes({ station }) {
  const code = station.code;
  const [opt, setOpt] = useOptions({ source: undefined, distribution: "all", fit_method: "l_moments", from: undefined, to: undefined }, code);
  const state = useAnalysis("hydro_flood_frequency", code, { source: opt.source, distribution: opt.distribution, fit_method: opt.fit_method, from: opt.from, to: opt.to });
  const low = useAnalysis("hydro_low_flow", code, { from: opt.from, to: opt.to });
  const data = state.data;
  const many = data && data.fit_method === "all";
  const spec = useMemo(() => {
    if (!data) return null;
    const series = data.distributions.map((item, at) => ({
      id: `${item.name}-${item.method}`,
      kind: "line",
      cls: `${DIST_CLASS[item.name] || "s4"} ${METHOD_CLASS[item.method] || ""}${at === 0 ? " best" : ""}`,
      label: label(item, many),
      data: item.curve,
    }));
    series.push({ id: "emp", kind: "points", label: "maksima roczne", data: data.empirical, readout: false });
    return {
      x: { scale: "gumbel", domain: [99, 0.1], label: "prawdopodobieństwo przewyższenia" },
      y: { label: "WQ [m³/s]", unit: "m³/s" },
      series,
      legend: [
        ...data.distributions.map((item, at) => ({ label: `${label(item, many)}${at === 0 ? " (najlepszy AIC)" : ""}`, kind: "stroke", cls: `${DIST_CLASS[item.name] || "s4"} ${METHOD_CLASS[item.method] || ""}` })),
        { label: "maksima roczne (m/(n+1))", kind: "points" },
      ],
      readout: { series: series[0].id },
      fit: { ratio: 0.66, minHeight: 240 },
      title: "Rozkłady maksimów rocznych na siatce Gumbela",
    };
  }, [data]);
  const sourceOptions = data ? data.sources.map((s) => [s, s === "semiannual" ? "półrocza IMGW-PIB" : "szereg dobowy (jak Hydrolog z eksportu Obserwatora)"]) : [];
  const highest = data && data.maxima.length ? data.maxima.reduce((a, b) => (b.value > a.value ? b : a)) : null;
  const ff = data && data.computed_by.find((p) => p.command === "stats flood-frequency");
  return html`<${Section} title="Przepływy maksymalne roczne (H5)" info=${INFO} state=${state}>
    ${data && html`
      <${Years} data=${data} onApply=${(from, to) => setOpt({ from, to })} />
      <div class="hy-options">
        ${sourceOptions.length > 1 && html`<${Option} label="Maksima"><${Seg} value=${data.source} label="Źródło maksimów" options=${sourceOptions} onChange=${(v) => setOpt({ source: v })} /></${Option}>`}
        <${Option} label="Rozkład"><${Select} value=${data.distribution} label="Rozkład" options=${[["all", "wszystkie cztery"], ["log_normal", "log-normalny"], ["gev", "GEV"], ["pearson3", "Pearson III"], ["weibull", "Weibull"]]} onChange=${(v) => setOpt({ distribution: v })} /></${Option}>
        <${Option} label="Metoda"><${Select} value=${data.fit_method} label="Metoda estymacji" options=${[["l_moments", "L-momenty (domyślna)"], ["mle", "największa wiarygodność"], ["moments", "momenty"], ["least_squares", "najmniejsze kwadraty"], ["all", "wszystkie metody"]]} onChange=${(v) => setOpt({ fit_method: v })} /></${Option}>
      </div>
      ${sourceOptions.length === 1 && html`<p class="muted hy-caption">Źródło maksimów: ${sourceOptions[0][1]}${data.source === "daily" ? " — IMGW-PIB nie publikuje półrocznych charakterystyk tej stacji." : "."}</p>`}
      <${Figures}
        items=${[
          { label: "Lat", value: fmt(data.n_years, 0), note: `${data.years.from}–${data.years.to}` },
          { label: "WWQ", value: highest ? `${fmtV(highest.value, "Q")} m³/s` : "–", note: highest ? (highest.date ? date(highest.date) : String(highest.year)) : "" },
          { label: "Najlepszy (AIC)", value: label(data.distributions[0], many) },
          { label: "Q1% (T = 100)", value: `${fmtV(data.distributions[0].quantiles[5], "Q")} m³/s`, note: label(data.distributions[0], many) },
        ]}
      />
      <${Chart} spec=${spec} />
      <h4 class="hy-sub">Kwantyle Q_p [m³/s]</h4>
      <${QuantileTable} periods=${data.table_periods} items=${data.distributions} many=${many} />
      <${FitTable} items=${data.distributions} many=${many} />
      ${data.incomplete_years && data.incomplete_years.length ? html`<p class="muted hy-caption">Hydrolog pominął lata niepełne: ${data.incomplete_years.map((y) => y.year ?? y).join(", ")}.</p>` : null}
      <${Handoff}
        code=${code}
        variable="Q"
        resolution=${data.source === "semiannual" ? "annual" : "daily"}
        from=${data.years.from}
        to=${data.years.to}
        computed=${ff}
        result=${{ best: data.best, quantiles: Object.fromEntries(data.distributions.map((item) => [`${item.name} ${item.method}`, Object.fromEntries(data.table_periods.map((t, at) => [t, item.quantiles[at]]))])) }}
      />
      <p class="muted hy-caption">GUI Hydrologa („Statystyka przepływów”, wczytanie pliku przekazania) liczy z tego samego szeregu te same kwantyle i pokazuje obok liczby Obserwatora.</p>
      <${Homogeneity} result=${data.homogeneity} />
      <${Notices} items=${data.notices} />
    `}
    <${LowFlow} state=${low} code=${code} />
  </${Section}>`;
}
