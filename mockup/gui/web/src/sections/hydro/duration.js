// „Czas trwania i strefy” (Nogat plan H8, H9): duration curves of H and Q with the modal
// classes (prototype) and Rybczyński's zones by Hydrolog's `hydrometrics water-level-zones`.

import { Chart, fmt, html, useMemo } from "../../lib.js";
import { Figures, Section, Table, useAnalysis } from "../common.js";
import { HYDRO_MONTHS, Notices, Option, Select, Years, fmtV, useOptions } from "./util.js";

const INFO = `Krzywa czasu trwania (przekroczenia) podaje wartość osiąganą lub przekraczaną przez p % dni wybranych lat (pozycja Weibulla m/(n+1); prototyp, docelowo Hydrolog H8). Strefy stanów wg Rybczyńskiego liczy Hydrolog („hydrometrics water-level-zones”, klasy 10 cm): niskie tło wodne NTW kończy się w środku klasy najczęstszej (modalnej), średnie STW w środku pierwszej klasy, w której krzywa czasu trwania spada poniżej 50 %, wyżej jest wysokie tło WTW. Autor w 2024 r. wyznaczał górną granicę STW ręcznie, styczną do krzywej czasu trwania; Hydrolog robi to regułą 50 %. Klasa modalna przepływów: najczęstsza z 40 klas logarytmicznych (klasy równej szerokości zawsze dają najniższą). Tabela klas w miesiącach hydrologicznych to metoda autora z 2024 r. (liczba dni w klasie, „łącznie z wyższymi” i „łącznie z niższymi”).`;

const MONTHS = [[0, "cały rok"], ...HYDRO_MONTHS.map((m, at) => [at + 1, m])];

function curveSpec(entry, variable, zones) {
  const log = variable === "Q";
  const u = variable === "Q" ? "m³/s" : "cm";
  const series = [];
  if (zones) {
    const low = entry.min;
    const top = Math.max(entry.curve[0][1], zones.stw_upper);
    series.push(
      { id: "ntw", kind: "band", cls: "s3", label: "NTW", data: [[0, low, zones.ntw_upper], [100, low, zones.ntw_upper]], readout: false },
      { id: "stw", kind: "band", cls: "s1", label: "STW", data: [[0, zones.ntw_upper, zones.stw_upper], [100, zones.ntw_upper, zones.stw_upper]], readout: false },
      { id: "wtw", kind: "band", cls: "s2", label: "WTW", data: [[0, zones.stw_upper, top], [100, zones.stw_upper, top]], readout: false },
    );
  }
  series.push({ id: "c", kind: "line", cls: "s1", label: `krzywa czasu trwania ${variable}`, data: entry.curve, unit: u });
  return {
    x: { label: "% dni z wartością równą lub wyższą", short: "p", digits: 1, min: 0, max: 100 },
    y: { label: `${variable} [${u}]`, unit: u, scale: log ? "log" : "linear", zero: false, digits: variable === "H" ? 0 : undefined },
    series,
    legend: true,
    readout: { series: "c", x: (x) => `p = ${fmt(x, x < 1 ? 1 : 0)} % dni` },
    fit: { ratio: 0.58, minHeight: 210 },
    title: `Krzywa czasu trwania ${variable}`,
  };
}

function frequencySpec(entry) {
  const f = entry.frequency;
  const modal = entry.modal;
  return {
    x: { label: "H [cm] (środek klasy 10 cm)", short: "H", digits: 0 },
    y: { label: "% dni", digits: 1 },
    series: [
      {
        id: "f",
        kind: "bars",
        cls: "s4",
        align: "center",
        label: "częstość klasy",
        unit: "%",
        data: f.bin_centers.map((x, at) => ({ x, y: f.frequency_pct[at], cls: modal && f.bin_edges[at] === modal.from ? "hy-modal" : undefined })),
      },
    ],
    readout: { x: (x) => `klasa ${fmt(x - 5, 0)}–${fmt(x + 5, 0)} cm` },
    fit: { ratio: 0.42, minHeight: 170 },
    title: "Częstość klas stanów",
  };
}

function MonthTable({ rows }) {
  const columns = [
    { key: "cls", label: "Klasa [cm]", format: (v) => v },
    ...HYDRO_MONTHS.map((m, at) => ({ key: `m${at}`, label: m, format: (v) => (v ? fmt(v, 0) : "") })),
    { key: "days", label: "dni", format: (v) => fmt(v, 0) },
    { key: "percent", label: "%", format: (v) => fmt(v, 2) },
    { key: "with_higher", label: "z wyższymi", format: (v) => fmt(v, 0) },
    { key: "with_lower", label: "z niższymi", format: (v) => fmt(v, 0) },
  ];
  const shown = rows.filter((row) => row.days > 0).map((row) => {
    const out = { cls: `${fmt(row.from, 0)}–${fmt(row.to, 0)}`, days: row.days, percent: row.percent, with_higher: row.with_higher, with_lower: row.with_lower };
    row.months.forEach((count, at) => (out[`m${at}`] = count));
    return out;
  });
  return html`<details class="hy-details"><summary>Liczebność klas w miesiącach hydrologicznych (${rows.length} klas)</summary>
    <${Table} columns=${columns} rows=${shown} className="tbl hy-compact" />
  </details>`;
}

/** The section „Czas trwania i strefy”. */
export function Duration({ station }) {
  const code = station.code;
  const [opt, setOpt] = useOptions({ from: undefined, to: undefined, month: 0 }, code);
  const state = useAnalysis("hydro_duration", code, { from: opt.from, to: opt.to, month: opt.month || undefined });
  const data = state.data;
  const h = data && data.variables.H;
  const q = data && data.variables.Q;
  const hCurve = useMemo(() => h && curveSpec(h, "H", h.zones), [data]);
  const hFrequency = useMemo(() => h && frequencySpec(h), [data]);
  const qCurve = useMemo(() => q && curveSpec(q, "Q", null), [data]);
  const table = data && [
    { key: "p", label: "p [% dni]", format: (v) => fmt(v, 0) },
    ...(h ? [{ key: "h", label: "H_p [cm]", format: (v) => fmtV(v, "H") }] : []),
    ...(q ? [{ key: "q", label: "Q_p [m³/s]", format: (v) => fmtV(v, "Q") }] : []),
  ];
  const tableRows = data ? (h || q).table.map(([p], at) => ({ p, h: h ? h.table[at][1] : null, q: q ? q.table[at][1] : null })) : [];
  return html`<${Section} title="Czas trwania i strefy" info=${INFO} state=${state}>
    ${data && html`
      <${Years} data=${data} onApply=${(from, to) => setOpt({ from, to })} />
      <${Option} label="Miesiąc"><${Select} value=${opt.month} label="Miesiąc hydrologiczny" options=${MONTHS} onChange=${(v) => setOpt({ month: +v })} /></${Option}>
      ${h
        ? html`
          <h4 class="hy-sub">Stany wody: strefy Rybczyńskiego (H9)</h4>
          <${Figures}
            items=${[
              { label: "NTW", value: `≤ ${fmt(h.zones.ntw_upper, 0)} cm`, note: "niskie tło wodne" },
              { label: "STW", value: `${fmt(h.zones.ntw_upper, 0)}–${fmt(h.zones.stw_upper, 0)} cm`, note: "średnie tło wodne" },
              { label: "WTW", value: `> ${fmt(h.zones.stw_upper, 0)} cm`, note: "wysokie tło wodne" },
              { label: "Klasa modalna", value: `${fmt(h.modal.from, 0)}–${fmt(h.modal.to, 0)} cm`, note: `${fmt(h.modal.days, 0)} dni (${fmt(h.modal.percent, 1)} %)` },
            ]}
          />
          <${Chart} spec=${hCurve} />
          <${Chart} spec=${hFrequency} />
          ${h.months && html`<${MonthTable} rows=${h.months} />`}`
        : html`<p class="hy-note">Szereg dobowy nie ma stanów wody H: stref Rybczyńskiego nie ma z czego wyznaczyć.</p>`}
      ${q
        ? html`
          <h4 class="hy-sub">Przepływy: krzywa czasu trwania (H8)</h4>
          <${Figures}
            items=${[
              { label: "Q50 (mediana)", value: `${fmtV(q.median, "Q")} m³/s` },
              { label: "Q90", value: `${fmtV(q.table[6][1], "Q")} m³/s`, note: "osiągany 90 % dni" },
              { label: "Klasa modalna", value: q.modal ? `${fmtV(q.modal.from, "Q")}–${fmtV(q.modal.to, "Q")} m³/s` : "–", note: q.modal ? `${fmt(q.modal.days, 0)} dni (${fmt(q.modal.percent, 1)} %)` : "" },
            ]}
          />
          <${Chart} spec=${qCurve} />`
        : html`<p class="hy-note">Szereg dobowy nie ma przepływów Q.</p>`}
      <h4 class="hy-sub">Wartości o danym czasie trwania</h4>
      <${Table} columns=${table} rows=${tableRows} />
      <${Notices} items=${data.notices} />
    `}
  </${Section}>`;
}
