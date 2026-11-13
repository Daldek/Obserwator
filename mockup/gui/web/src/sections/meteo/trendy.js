// „Trendy” (Nogat plan M13): Hydrolog's Mann–Kendall test (`stats mann-kendall`) of the annual
// series of M1, M2, M5, M6 and M11, with Sen's slope (a prototype until Hydrolog has it).

import { Chart, fmt, html } from "../../lib.js";
import { Section, Table, YearRange, useAnalysis } from "../common.js";
import { DatasetSeg, num, useOptions, yearAxis, yearReadout } from "./util.js";

const INFO = `Test Manna–Kendalla liczy Hydrolog („stats mann-kendall”, poziom istotności 0,05; wariancja S bez poprawki na powtórzenia, jak w Hydrologu) dla serii rocznych lat pełnych: suma roczna opadu, maksymalny opad dobowy, dni z opadem ≥ 10 mm, najdłuższy okres bezopadowy (P < 1 mm, ciąg przypisany do roku początku), średnia roczna temperatura, dni z przymrozkiem i dni gorące (gdy stacja mierzy temperaturę). Nachylenie Sena (1968) to mediana nachyleń wszystkich par lat; przedział ufności 95 % wg Gilberta (1987, rozdz. 16.5) z Var(S) testu; linia trendu przechodzi przez medianę lat i wartości (Conover 1980). Test liczę od 10 lat; lata z brakami (wg WMO-No. 1203) pomijam, co nie zmienia porządku pozostałych.`;

const DIRECTION = { increasing: "rosnący", decreasing: "malejący", "no trend": "brak", none: "brak" };

function SeriesChart({ item }) {
  const sen = item.sen;
  const points = item.years.map((y, at) => [y, item.values[at]]);
  const series = [{ id: "v", kind: "points", label: item.label, data: points, unit: item.unit, digits: item.unit === "°C" ? 2 : 1 }];
  if (sen) {
    const first = item.years[0];
    const last = item.years[item.years.length - 1];
    series.push({ id: "sen", kind: "line", cls: item.mann_kendall && item.mann_kendall.trend_detected ? "s2" : "s4", label: "trend Sena", data: [first, last].map((y) => [y, sen.intercept + sen.slope * y]), readout: false });
  }
  const spec = {
    x: yearAxis(points),
    y: { label: item.unit, unit: item.unit, zero: item.unit !== "°C" },
    series,
    readout: { series: "v", x: yearReadout },
    fit: { ratio: 0.55, minHeight: 150 },
    title: item.label,
  };
  const mk = item.mann_kendall;
  return html`<div class="me-trend">
    <h5>${item.label}</h5>
    <p>${sen ? html`<span class=${mk && mk.trend_detected ? "me-sig" : ""}>${sen.per_decade > 0 ? "+" : ""}${fmt(sen.per_decade, Math.abs(sen.per_decade) >= 10 ? 0 : 2)} ${item.unit}/10 lat</span> · p = ${fmt(mk.p_value, 3)}` : item.note || ""}</p>
    <${Chart} spec=${spec} />
  </div>`;
}

/** The card „Trendy”. */
export function Trendy({ station }) {
  const code = station.code;
  const [opt, setOpt] = useOptions({ from: undefined, to: undefined, dataset: undefined }, code);
  const state = useAnalysis("meteo-trends", code, { from: opt.from, to: opt.to, dataset: opt.dataset });
  const data = state.data;
  const columns = [
    { key: "label", label: "Seria", format: (v) => v },
    { key: "n", label: "Lat", format: (v) => String(v) },
    { key: "per_decade", label: "Sen /10 lat", format: (v, r) => (v === null || v === undefined ? "–" : `${v > 0 ? "+" : ""}${fmt(v, Math.abs(v) >= 10 ? 1 : 2)} ${r.unit}`) },
    { key: "ci", label: "95 %", format: (v, r) => (r.lower_decade === undefined ? "–" : `${num(r.lower_decade, 2)} … ${num(r.upper_decade, 2)}`) },
    { key: "z", label: "Z", format: (v) => num(v, 2) },
    { key: "p", label: "p", format: (v) => num(v, 3) },
    { key: "trend", label: "Trend (α = 0,05)", format: (v, r) => (r.detected ? html`<strong>${v}</strong>` : v) },
  ];
  const rows = data
    ? data.series.map((s) => ({
        label: s.label,
        unit: s.unit,
        n: s.n,
        per_decade: s.sen ? s.sen.per_decade : null,
        lower_decade: s.sen ? s.sen.lower_decade : undefined,
        upper_decade: s.sen ? s.sen.upper_decade : undefined,
        z: s.mann_kendall ? s.mann_kendall.z_score : null,
        p: s.mann_kendall ? s.mann_kendall.p_value : null,
        detected: s.mann_kendall ? s.mann_kendall.trend_detected : false,
        trend: s.mann_kendall ? (s.mann_kendall.trend_detected ? DIRECTION[s.mann_kendall.trend_direction] || s.mann_kendall.trend_direction : "nieistotny") : s.note || "–",
      }))
    : [];
  return html`<div class="me-card">
    <div class="me-toolbar">
      <${DatasetSeg} data=${data} value=${opt.dataset} onChange=${(v) => setOpt({ dataset: v })} />
      ${data && html`<${YearRange} first=${data.range.first} last=${data.range.last} from=${data.range.from} to=${data.range.to} label="Lata" onApply=${(a, b) => setOpt({ from: a, to: b })} />`}
    </div>
    <${Section} title="Serie roczne: test Manna–Kendalla i nachylenie Sena" info=${INFO} state=${state}>
      ${data &&
      html`
        <${Table} columns=${columns} rows=${rows} />
        <div class="me-trends">${data.series.filter((s) => s.n > 0).map((s) => html`<${SeriesChart} key=${s.key} item=${s} />`)}</div>
      `}
    </${Section}>
  </div>`;
}
