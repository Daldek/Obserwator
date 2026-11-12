// „Trendy i bilans” (Nogat plan H16 to H18): Hydrolog's `stats mann-kendall` of annual
// series with Sen's slope, runoff volumes and baseflow (prototypes).

import { Chart, fmt, html, useMemo } from "../../lib.js";
import { Figures, Section, Seg, Table, useAnalysis } from "../common.js";
import { Block, DOY_TICKS, HYDRO_MONTHS, Notices, Option, Select, VariableSeg, Years, digitsOf, doyLabel, fmtV, useOptions } from "./util.js";

const INFO = `Trend roczny: test Manna–Kendalla liczy Hydrolog („stats mann-kendall”, dwustronny, α = 0,05) dla rocznych maksimów, średnich i minimów (z półroczy IMGW-PIB, gdzie są, inaczej z pełnych lat szeregu dobowego); nachylenie Sena (mediana nachyleń wszystkich par lat; Sen 1968) z 95 % przedziałem (Gilbert 1987) i wyrazem wolnym Conovera to prototyp (docelowo Hydrolog H16), podane na 10 lat. Objętość odpływu V = Σ Q·86 400 s w mln m³ w latach i miesiącach hydrologicznych, krzywa sumowa roku na tle średniej z lat pełnych (prototyp H17; lata z brakami mają objętość zaniżoną i są oznaczone). Przepływ podziemny: filtr rekurencyjny Lyne’a i Hollicka (1979) z α = 0,925 w trzech przejściach (Nathan i McMahon 1990) na odcinkach co najmniej 60 dni bez braków, z odbiciem 30 dni na końcach (Ladson i in. 2013); wskaźnik BFI = ΣQ_podz/ΣQ; stała recesji k = mediana Q(t+1)/Q(t) w odcinkach opadania co najmniej 5 dni (Tallaksen 1995), czas połowicznego zaniku ln 2/(−ln k) (prototyp H18).`;

const DIRECTION = { increasing: "rosnący", decreasing: "malejący", none: "brak" };

function TrendTable({ data }) {
  const columns = [
    { key: "name", label: "Szereg", format: (v) => v },
    { key: "n", label: "lat", format: (v) => fmt(v, 0) },
    { key: "s", label: "S", format: (v) => fmt(v, 0) },
    { key: "z", label: "Z", format: (v) => fmt(v, 2) },
    { key: "p", label: "p", format: (v) => fmt(v, 3) },
    { key: "trend", label: `trend (α = ${fmt(data.alpha, 2)})`, format: (v) => v },
    { key: "slope", label: "Sen / 10 lat", format: (v, row) => (v === null ? "–" : `${fmtV(v * 10, data.var)} (${fmtV(row.low * 10, data.var)}…${fmtV(row.high * 10, data.var)})`) },
  ];
  const rows = data.series.map((s) => ({
    name: s.name,
    n: s.points.length,
    s: s.mann_kendall ? s.mann_kendall.s_statistic : null,
    z: s.mann_kendall ? s.mann_kendall.z_score : null,
    p: s.mann_kendall ? s.mann_kendall.p_value : null,
    trend: s.mann_kendall ? DIRECTION[s.mann_kendall.trend_direction] || s.mann_kendall.trend_direction : "za mało lat",
    slope: s.sen ? s.sen.slope : null,
    low: s.sen ? s.sen.low : null,
    high: s.sen ? s.sen.high : null,
  }));
  return html`<${Table} columns=${columns} rows=${rows} />`;
}

function Runoff({ state, opt, setOpt }) {
  const data = state.data;
  const annual = useMemo(
    () =>
      data && {
        x: { label: "rok hydrologiczny", digits: 0 },
        y: { label: "V [mln m³]", unit: "mln m³", digits: 1 },
        series: [{ id: "v", kind: "bars", cls: "s1", align: "center", label: "odpływ roczny", data: data.rows.map((r) => ({ x: r.year, y: r.volume, cls: r.complete ? undefined : "hy-incomplete" })) }],
        marks: data.mean_annual ? [{ kind: "hline", y: data.mean_annual, label: `średnio ${fmt(data.mean_annual, 0)}` }] : [],
        readout: { x: (x) => `rok ${Math.round(x)}` },
        fit: { ratio: 0.42, minHeight: 170 },
        title: "Odpływ roczny",
      },
    [data],
  );
  const monthly = useMemo(
    () =>
      data && {
        x: { label: "miesiąc", tickList: HYDRO_MONTHS.map((label, at) => ({ value: at + 1, label })), min: 0.5, max: 12.5 },
        y: { label: "V [mln m³]", unit: "mln m³", digits: 1 },
        series: [{ id: "m", kind: "bars", cls: "s1", align: "center", label: "średni odpływ miesiąca", data: data.monthly_mean.map((v, at) => [at + 1, v]) }],
        readout: { x: (x) => HYDRO_MONTHS[Math.round(x) - 1] || "" },
        fit: { ratio: 0.38, minHeight: 150 },
        title: "Średni odpływ miesięcy",
      },
    [data],
  );
  const cumulative = useMemo(
    () =>
      data && {
        x: { label: "doba roku hydrologicznego", tickList: DOY_TICKS, min: 1, max: 366 },
        y: { label: "V [mln m³]", unit: "mln m³", digits: 1 },
        series: [
          ...(data.mean_cumulative ? [{ id: "mean", kind: "line", cls: "s4", label: `średnio (${data.complete_years} lat pełnych)`, data: data.mean_cumulative }] : []),
          { id: "year", kind: "line", cls: "s1", label: `rok ${data.year}${data.year_missing ? ` (braki: ${data.year_missing} d)` : ""}`, data: data.cumulative },
        ],
        legend: true,
        readout: { series: "year", x: doyLabel },
        fit: { ratio: 0.45, minHeight: 180 },
        title: "Krzywa sumowa odpływu",
      },
    [data],
  );
  const chosen = data && data.rows.find((r) => r.year === data.year);
  return html`<${Block} state=${state} title="Objętość odpływu (H17)">
    ${data && html`
      <${Figures}
        items=${[
          { label: "Średni odpływ roczny", value: data.mean_annual ? `${fmt(data.mean_annual, 1)} mln m³` : "–", note: `${data.complete_years} lat pełnych` },
          { label: `Rok ${data.year}`, value: chosen ? `${fmt(chosen.volume, 1)} mln m³` : "–", note: chosen && !chosen.complete ? `niepełny (${chosen.missing} d braków)` : "" },
        ]}
      />
      <${Chart} spec=${annual} />
      <${Chart} spec=${monthly} />
      <${Option} label="Rok"><${Select} value=${data.year} label="Rok hydrologiczny" options=${[...data.rows].reverse().map((r) => [r.year, `${r.year}${r.complete ? "" : " (niepełny)"}`])} onChange=${(v) => setOpt({ ryear: +v })} /></${Option}>
      <${Chart} spec=${cumulative} />
    `}
  </${Block}>`;
}

function Baseflow({ state, setOpt }) {
  const data = state.data;
  const yearly = useMemo(
    () =>
      data && {
        x: { label: "rok hydrologiczny", digits: 0 },
        y: { label: "BFI", digits: 2, max: 1 },
        series: [{ id: "bfi", kind: "bars", cls: "s3", align: "center", label: "BFI", data: data.rows.map((r) => [r.year, r.bfi]) }],
        marks: [{ kind: "hline", y: data.bfi, label: `${fmt(data.bfi, 2)} w okresie` }],
        readout: { x: (x) => `rok ${Math.round(x)}` },
        fit: { ratio: 0.4, minHeight: 160 },
        title: "Wskaźnik przepływu podziemnego w latach",
      },
    [data],
  );
  const year = useMemo(
    () =>
      data && {
        x: { scale: "date" },
        y: { label: "Q [m³/s]", unit: "m³/s", scale: "log" },
        series: [
          { id: "q", kind: "line", cls: "s1", label: "przepływ", data: data.flow },
          { id: "b", kind: "line", cls: "s3", label: "przepływ podziemny", data: data.base },
        ],
        legend: true,
        readout: { series: "q" },
        fit: { ratio: 0.5, minHeight: 190 },
        title: `Rozdział hydrogramu, rok ${data.year}`,
      },
    [data],
  );
  return html`<${Block} state=${state} title="Przepływ podziemny (H18)">
    ${data && html`
      <${Figures}
        items=${[
          { label: "BFI", value: fmt(data.bfi, 3), note: `${data.years.from}–${data.years.to}, ${fmt(data.days, 0)} dni` },
          { label: "Stała recesji k", value: data.recession ? fmt(data.recession.k, 4) : "–", note: data.recession ? `${data.recession.segments} odcinków opadania` : "" },
          { label: "Połowiczny zanik", value: data.recession && data.recession.half_days ? `${fmt(data.recession.half_days, 1)} dni` : "–" },
          { label: "Filtr", value: `α = ${fmt(data.alpha, 3)}`, note: "Lyne i Hollick, 3 przejścia" },
        ]}
      />
      <${Chart} spec=${yearly} />
      <${Option} label="Rok"><${Select} value=${data.year} label="Rok hydrologiczny" options=${[...data.rows].reverse().map((r) => [r.year, String(r.year)])} onChange=${(v) => setOpt({ byear: +v })} /></${Option}>
      <${Chart} spec=${year} />
    `}
  </${Block}>`;
}

/** The section „Trendy i bilans”. */
export function Trends({ station }) {
  const code = station.code;
  const [opt, setOpt] = useOptions({ var: undefined, from: undefined, to: undefined, pick: "max", ryear: undefined, byear: undefined }, code);
  const state = useAnalysis("hydro_trends", code, { var: opt.var, from: opt.from, to: opt.to });
  const runoff = useAnalysis("hydro_runoff", code, { from: opt.from, to: opt.to, year: opt.ryear });
  const base = useAnalysis("hydro_baseflow", code, { from: opt.from, to: opt.to, year: opt.byear });
  const data = state.data;
  const variables = [
    ...new Set(
      (station.datasets || [])
        .filter((d) => d.dataset.includes("hydro"))
        .flatMap((d) => Object.keys(d.variables).map((v) => v.split("_")[0].split("@")[0]))
        .filter((v) => ["Q", "H", "T"].includes(v)),
    ),
  ];
  const picked = data && (data.series.find((s) => s.stat === opt.pick) || data.series[0]);
  const spec = useMemo(() => {
    if (!picked) return null;
    const unitText = { "m3/s": "m³/s", degC: "°C" }[data.unit] || data.unit;
    const series = [{ id: "v", kind: "line", cls: "s1", label: picked.name, data: picked.points, unit: unitText }];
    if (picked.sen) {
      const years = picked.points.map((p) => p[0]);
      const a = Math.min(...years);
      const b = Math.max(...years);
      series.push({ id: "sen", kind: "line", cls: "s2", label: `nachylenie Sena ${fmtV(picked.sen.slope * 10, data.var)} ${unitText}/10 lat`, data: [a, b].map((y) => [y, picked.sen.intercept + picked.sen.slope * y]), unit: unitText });
    }
    return {
      x: { label: "rok hydrologiczny", digits: 0 },
      y: { label: `${picked.name} [${unitText}]`, unit: unitText, zero: false, digits: digitsOf(data.var) },
      series,
      legend: true,
      readout: { series: "v", x: (x) => `rok ${Math.round(x)}` },
      fit: { ratio: 0.45, minHeight: 180 },
      title: `Trend ${picked.name}`,
    };
  }, [data, opt.pick]);
  const span = data || runoff.data || base.data;
  return html`<${Section} title="Trendy i bilans" info=${INFO}>
    <${Years} data=${span} onApply=${(from, to) => setOpt({ from, to })} />
    <${Block} state=${state} title="Trendy roczne (H16)">
      ${data && html`
        ${variables.length > 1 && html`<${Option} label="Zmienna"><${VariableSeg} value=${data.var} variables=${["Q", "H", "T"].filter((v) => variables.includes(v))} onChange=${(v) => setOpt({ var: v })} /></${Option}>`}
        <p class="muted hy-caption">Wartości roczne: ${data.source === "imgw" ? "półrocza IMGW-PIB (maksimum = większe z półrocznych, minimum = mniejsze)" : "pełne lata szeregu dobowego"}.</p>
        <${TrendTable} data=${data} />
        <${Option} label="Wykres"><${Seg} value=${picked.stat} label="Szereg" options=${data.series.map((s) => [s.stat, s.name])} onChange=${(v) => setOpt({ pick: v })} /></${Option}>
        <${Chart} spec=${spec} />
        <${Notices} items=${data.notices} />
      `}
    </${Block}>
    <${Runoff} state=${runoff} opt=${opt} setOpt=${setOpt} />
    <${Baseflow} state=${base} setOpt=${setOpt} />
  </${Section}>`;
}
