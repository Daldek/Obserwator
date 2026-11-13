// „Temperatura wody” (Nogat plan H14, H15): harmonics of the annual cycle per year and over
// the period, days beyond thresholds (prototypes).

import { Chart, fmt, html, useMemo } from "../../lib.js";
import { Figures, Section, Seg, Table, useAnalysis } from "../common.js";
import { DOY_TICKS, Option, Years, date, doyLabel, useOptions } from "./util.js";

const INFO = `Analiza harmoniczna cyklu rocznego temperatury wody (prototyp, docelowo Hydrolog H14): metodą najmniejszych kwadratów dopasowane T(t) = A₀ + Σ [a_k·cos(2πkt/P) + b_k·sin(2πkt/P)], P = 365,25 doby, t – doba roku hydrologicznego (0 = 1 XI), dwie harmoniki (Wilks 2011, Statistical Methods in the Atmospheric Sciences, rozdz. 9.4). Dla każdej harmonicznej: amplituda C_k = √(a_k² + b_k²), termin jej maksimum i udział wariancji wyjaśnionej przez harmoniki 1..k. Dopasowanie dla każdego roku z co najmniej 300 dniami pomiaru i dla całego okresu (wszystkie dni naraz). Autor stosował tę analizę do temperatur z boi bałtyckich. Dni z temperaturą ≥ 15, 20, 25 °C i < 1 °C oraz maksimum roczne z datą (prototyp H15).`;

const THRESHOLDS = [
  ["above_15", "≥ 15 °C"],
  ["above_20", "≥ 20 °C"],
  ["above_25", "≥ 25 °C"],
  ["below_1", "< 1 °C"],
];

/** The section „Temperatura wody”. */
export function WaterTemperature({ station }) {
  const code = station.code;
  const [opt, setOpt] = useOptions({ from: undefined, to: undefined, threshold: "above_20" }, code);
  const state = useAnalysis("hydro_water_temperature", code, { from: opt.from, to: opt.to });
  const data = state.data;
  const cycle = useMemo(
    () =>
      data && {
        x: { label: "doba roku hydrologicznego", tickList: DOY_TICKS, min: 1, max: 366 },
        y: { label: "T [°C]", unit: "°C", zero: false, digits: 1 },
        series: [
          { id: "mean", kind: "line", cls: "s4", label: "średnia doby z lat", data: data.cycle.mean, width: 1 },
          { id: "fit", kind: "line", cls: "s1", label: "harmoniki 1 + 2", data: data.cycle.fit },
          { id: "first", kind: "line", cls: "s5", label: "1. harmoniczna", data: data.cycle.first },
        ],
        legend: true,
        readout: { series: "fit", x: doyLabel },
        fit: { ratio: 0.55, minHeight: 210 },
        title: "Cykl roczny temperatury wody",
      },
    [data],
  );
  const fitted = data ? data.rows.filter((r) => r.c1 !== undefined) : [];
  const yearly = useMemo(
    () =>
      data && {
        x: { label: "rok hydrologiczny", digits: 0 },
        y: { label: "°C", unit: "°C", zero: false, digits: 2 },
        series: [
          { id: "a0", kind: "line", cls: "s1", label: "A₀ średnia", data: fitted.map((r) => [r.year, r.a0]) },
          { id: "c1", kind: "line", cls: "s2", label: "C₁ amplituda", data: fitted.map((r) => [r.year, r.c1]) },
        ],
        legend: true,
        readout: { x: (x) => `rok ${Math.round(x)}` },
        fit: { ratio: 0.42, minHeight: 170 },
        title: "Średnia i amplituda w latach",
      },
    [data],
  );
  const days = useMemo(() => {
    if (!data) return null;
    const label = THRESHOLDS.find(([key]) => key === opt.threshold)[1];
    return {
      x: { label: "rok hydrologiczny", digits: 0 },
      y: { label: "dni", digits: 0 },
      series: [{ id: "d", kind: "bars", cls: opt.threshold === "below_1" ? "s3" : "s2", align: "center", label: `dni T ${label}`, data: data.rows.map((r) => [r.year, r[opt.threshold]]) }],
      readout: { x: (x) => `rok ${Math.round(x)}` },
      fit: { ratio: 0.4, minHeight: 160 },
      title: "Dni z temperaturą poza progiem",
    };
  }, [data, opt.threshold]);
  const columns = [
    { key: "year", label: "Rok", format: (v) => String(v) },
    { key: "days", label: "dni", format: (v) => fmt(v, 0) },
    { key: "a0", label: "A₀", format: (v) => fmt(v, 2) },
    { key: "c1", label: "C₁", format: (v) => fmt(v, 2) },
    { key: "date1", label: "maks. 1. harm.", format: (v) => v || "–" },
    { key: "c2", label: "C₂", format: (v) => fmt(v, 2) },
    { key: "r2_2", label: "R² (1+2)", format: (v) => fmt(v, 3) },
    { key: "above_20", label: "≥ 20°", format: (v) => fmt(v, 0) },
    { key: "above_25", label: "≥ 25°", format: (v) => fmt(v, 0) },
    { key: "below_1", label: "< 1°", format: (v) => fmt(v, 0) },
    { key: "max", label: "maks. T", format: (v, row) => `${fmt(v, 1)} (${date(row.max_date)})` },
  ];
  const period = data && data.period;
  const [h1, h2] = period ? period.harmonics : [];
  return html`<${Section} info=${INFO} state=${state}>
    ${data && html`
      <${Years} data=${data} onApply=${(from, to) => setOpt({ from, to })} />
      <${Figures}
        items=${[
          { label: "A₀ średnia", value: `${fmt(period.mean, 2)} °C`, note: `${fmt(period.n, 0)} dni ${data.years.from}–${data.years.to}` },
          { label: "C₁ amplituda", value: `${fmt(h1.amplitude, 2)} °C`, note: `maksimum ${h1.date}` },
          { label: "C₂", value: `${fmt(h2.amplitude, 2)} °C`, note: `maksimum ${h2.date} (i pół roku później)` },
          { label: "Wariancja wyjaśniona", value: `${fmt(h1.explained * 100, 1)} %`, note: `1+2: ${fmt(h2.explained * 100, 1)} %` },
        ]}
      />
      <${Chart} spec=${cycle} />
      ${fitted.length ? html`<${Chart} spec=${yearly} />` : html`<p class="hy-note">Żaden rok nie ma 300 dni pomiaru: harmoniki tylko dla całego okresu.</p>`}
      <${Option} label="Próg"><${Seg} value=${opt.threshold} label="Próg" options=${THRESHOLDS} onChange=${(v) => setOpt({ threshold: v })} /></${Option}>
      <${Chart} spec=${days} />
      <${Table} columns=${columns} rows=${[...data.rows].reverse()} max=${12} className="tbl hy-compact" />
    `}
  </${Section}>`;
}
