// „Krzywa natężenia przepływu” (Nogat plan H4): Hydrolog's `hydrometrics rating-curve` on the
// same-day H and Q of the chosen years, and the curves of successive periods.

import { Chart, fmt, html, useMemo } from "../../lib.js";
import { Figures, Section, Seg, Table, useAnalysis } from "../common.js";
import { Block, Notices, Option, Years, useOptions } from "./util.js";

const INFO = `Krzywa natężenia przepływu Q = a·(H − H₀)^b dopasowana przez Hydrolog („hydrometrics rating-curve”: nieliniowa metoda najmniejszych kwadratów, a ≥ 0, b ≥ 0, H₀ poniżej najniższego stanu; opcjonalnie odrzuca pary o resztach ponad 2 odchylenia standardowe i dopasowuje ponownie) do wszystkich par stan–przepływ z tego samego dnia w wybranych latach; na wykresie punkty są przerzedzone do jednego na komórkę siatki. Domyślnie to ostatnie 10 lat, a nie cały zapis jak w pozostałych analizach: krzywa natężenia zmienia się w czasie, więc jedna krzywa dopasowana do wielu dekad nie opisuje dobrze żadnej z nich; z tego powodu nie dotyczy jej też zalecany minimalny okres 30 lat. Przepływy dobowe są wyznaczane ze stanów krzywymi natężenia samych służb, więc pary z jednego roku leżą na krzywej obowiązującej w tym roku: rozrzut punktów i przesuwanie się krzywych w kolejnych okresach pokazuje zmiany krzywej (np. erozję lub zamulanie koryta, zmianę zera wodowskazu), a nie błąd pomiaru. H₀ jest w centymetrach, a w m³/s na cm^b. Krzywe kolejnych okresów (cały szereg, co najmniej 30 par w okresie) liczy Hydrolog osobno dla każdego okresu; tabela podaje przepływ przy medianie stanów i stan przy medianie przepływów całego szeregu. Opublikowana krzywa ČHMÚ (RC_{WIGOS}.json) nie jest jeszcze w magazynie (D10 planu).`;

const PALETTE = 8;

/** The colour class of the i-th of n periods, oldest to newest along the palette. */
function colour(index, count) {
  return `hy-c${count <= 1 ? PALETTE - 1 : Math.round((index * (PALETTE - 1)) / (count - 1))}`;
}

function formula(fit) {
  return `Q = ${fmt(fit.a, fit.a < 0.01 ? 6 : 4)} · (H − ${fmt(fit.h0, 1)})^${fmt(fit.b, 3)}`;
}

const flowLabel = (x) => `Q = ${fmt(x, x >= 100 ? 0 : x >= 10 ? 1 : 2)} m³/s`;

function Periods({ code, opt, setOpt, axis }) {
  const state = useAnalysis("hydro_rating_periods", code, { period: opt.period, outliers: opt.outliers });
  const data = state.data;
  const spec = useMemo(() => {
    if (!data) return null;
    const fitted = data.periods.filter((p) => p.fit);
    return {
      x: { label: "Q [m³/s]", short: "Q", scale: axis === "log" ? "log" : "linear", zero: true, digits: 2 },
      y: { label: "H [cm]", unit: "cm", zero: false, digits: 0 },
      series: fitted.map((p, at) => ({ id: `p${p.from}`, kind: "line", cls: colour(at, fitted.length), label: `${p.from}–${p.to}`, data: p.fit.curve, unit: "cm" })),
      legend: fitted.map((p, at) => ({ label: `${p.from}–${p.to}`, kind: "stroke", cls: colour(at, fitted.length) })),
      readout: { x: flowLabel },
      fit: { ratio: 0.62, minHeight: 220 },
      title: "Krzywe kolejnych okresów",
    };
  }, [data, axis]);
  const columns = data && [
    { key: "label", label: "Okres", format: (v) => v },
    { key: "n", label: "par", format: (v) => fmt(v, 0) },
    { key: "a", label: "a", format: (v) => (v === undefined ? "–" : fmt(v, v < 0.01 ? 6 : 4)) },
    { key: "b", label: "b", format: (v) => (v === undefined ? "–" : fmt(v, 3)) },
    { key: "h0", label: "H₀ [cm]", format: (v) => (v === undefined ? "–" : fmt(v, 1)) },
    { key: "r2", label: "R²", format: (v) => (v === undefined ? "–" : fmt(v, 3)) },
    { key: "q_at", label: `Q przy H = ${fmt(data.reference.level, 0)} cm`, format: (v, row) => (row.error ? row.error : v === null || v === undefined ? "–" : fmt(v, v >= 100 ? 0 : 2)) },
    { key: "h_at", label: `H przy Q = ${fmt(data.reference.flow, 2)} m³/s`, format: (v) => (v === null || v === undefined ? "–" : fmt(v, 0)) },
  ];
  const rows = data ? data.periods.map((p) => ({ label: `${p.from}–${p.to}`, n: p.n, a: p.fit?.a, b: p.fit?.b, h0: p.fit?.h0, r2: p.fit?.r_squared, q_at: p.q_at, h_at: p.h_at, error: p.error })) : [];
  return html`<${Block} state=${state} title="Kolejne okresy">
    <${Option} label="Okresy"><${Seg} value=${opt.period} label="Długość okresów" options=${[["5", "5 lat"], ["10", "10 lat"], ["20", "20 lat"]]} onChange=${(v) => setOpt({ period: v })} /></${Option}>
    ${data && html`
      <${Chart} spec=${spec} />
      <${Table} columns=${columns} rows=${rows} className="tbl hy-compact" />
      <${Notices} items=${data.notices} />
    `}
  </${Block}>`;
}

/** The section „Krzywa natężenia przepływu”. */
export function RatingCurve({ station }) {
  const code = station.code;
  const [opt, setOpt] = useOptions({ from: undefined, to: undefined, period: "10", outliers: "0", axis: "linear" }, code);
  const state = useAnalysis("hydro_rating_curve", code, { from: opt.from, to: opt.to, outliers: opt.outliers });
  const data = state.data;
  const points = useMemo(() => {
    if (!data) return null;
    const groups = data.groups.filter((g) => g.points.length);
    const name = (g) => (g.from === g.to ? String(g.from) : `${g.from}–${g.to}`);
    return {
      x: { label: "Q [m³/s]", short: "Q", scale: opt.axis === "log" ? "log" : "linear", zero: true, digits: 2 },
      y: { label: "H [cm]", unit: "cm", zero: false, digits: 0 },
      series: [
        ...groups.map((g, at) => ({ id: `g${at}`, kind: "points", cls: colour(at, groups.length), label: name(g), data: g.points, readout: false })),
        { id: "fit", kind: "line", cls: "s1 hy-fit", label: `krzywa ${data.years.from}–${data.years.to}`, data: data.fit.curve, unit: "cm" },
      ],
      legend: [
        ...groups.map((g, at) => ({ label: name(g), kind: "stroke", cls: colour(at, groups.length) })),
        { label: `krzywa ${data.years.from}–${data.years.to}`, kind: "stroke", cls: "hy-fit" },
      ],
      readout: { series: "fit", x: flowLabel },
      fit: { ratio: 0.72, minHeight: 240 },
      title: "Punkty H–Q i krzywa natężenia przepływu",
    };
  }, [data, opt.axis]);
  return html`<${Section} title="Krzywa wybranych lat" info=${INFO} state=${state}>
    ${data && html`
      <${Years} data=${data} onApply=${(from, to) => setOpt({ from, to })} recommend=${false} />
      <p class="muted hy-caption">Domyślnie ostatnie 10 lat: krzywa natężenia zmienia się w czasie (zob. objaśnienie i kolejne okresy poniżej).</p>
      <div class="hy-options">
        <${Option} label="Odstające"><${Seg} value=${opt.outliers} label="Odstające" options=${[["0", "zostaw"], ["1", "odrzuć (2σ)"]]} onChange=${(v) => setOpt({ outliers: v })} /></${Option}>
        <${Option} label="Oś Q"><${Seg} value=${opt.axis} label="Oś Q" options=${[["linear", "liniowa"], ["log", "logarytmiczna"]]} onChange=${(v) => setOpt({ axis: v })} /></${Option}>
      </div>
      <p class="hy-formula">${formula(data.fit)}</p>
      <${Figures}
        items=${[
          { label: "a", value: fmt(data.fit.a, data.fit.a < 0.01 ? 6 : 4), note: "m³/s · cm⁻ᵇ" },
          { label: "b", value: fmt(data.fit.b, 3) },
          { label: "H₀", value: `${fmt(data.fit.h0, 1)} cm` },
          { label: "R²", value: fmt(data.fit.r_squared, 4) },
          { label: "σ reszt", value: `${fmt(data.fit.std_residuals, 2)} m³/s` },
          { label: "Par", value: fmt(data.fit.n_points, 0), note: data.fit.n_outliers_removed ? `odrzucono ${data.fit.n_outliers_removed}` : `lata ${data.years.from}–${data.years.to}` },
        ]}
      />
      <${Chart} spec=${points} />
      <p class="muted hy-caption">Pary dobowe stan–przepływ to nie pomiary hydrometryczne: punkty z jednego roku leżą na krzywej, z której służba wyliczyła przepływy. Krzywej opublikowanej przez ČHMÚ nie ma jeszcze w magazynie.</p>
      <${Notices} items=${data.notices} />
      <${Periods} code=${code} opt=${opt} setOpt=${setOpt} axis=${opt.axis} />
    `}
  </${Section}>`;
}
