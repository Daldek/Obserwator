// „Reżim i sezonowość” (Nogat plan H10 to H13): Hydrolog's `stats daily` and `stats monthly`,
// Pardé's coefficients with a provisional Dynowska type, the dates of annual extremes.

import { Chart, fmt, html, useMemo } from "../../lib.js";
import { Figures, Section, Seg, Table, useAnalysis } from "../common.js";
import { Block, DOY_TICKS, HYDRO_MONTHS, Notices, Option, ROMAN, VARIABLES, VariableSeg, Years, date, digitsOf, doyLabel, fmtV, useOptions } from "./util.js";

const INFO = `Krzywe reżimu dobowego: dla każdej doby roku hydrologicznego (1 = 1 XI) największa, średnia, mediana i najmniejsza wartość wybranych lat — Hydrolog „stats daily”. Statystyki miesięczne z przedziałem ufności średniej t-Studenta — Hydrolog „stats monthly” (miesiące kalendarzowe, tu w kolejności roku hydrologicznego). Współczynniki Pardégo to średni przepływ miesiąca podzielony przez średni przepływ roczny (prototyp, docelowo Hydrolog H12). Typ reżimu wg kryteriów Dynowskiej (1997, za: Wrzesiński 2018, Badania Fizjograficzne A69): niwalny słabo (przepływ miesiąca wiosennego ≤ 130 % średniego rocznego), średnio (130–180 %) i silnie wykształcony (> 180 %), niwalno-pluwialny (wzrost letni do co najmniej 100 %), pluwialno-niwalny (miesiąc letni wyższy lub prawie równy wiosennemu). Odczyt kryteriów jest roboczy: miesiąc wiosenny = większy z III i IV, letni = największy z VI–VIII, „prawie równy” = co najmniej 95 % wiosennego. Sezonowość: terminy rocznych maksimów i minimów jako kierunki na okręgu roku (Bayliss i Jones 1993, Burn 1997): średni termin i koncentracja r od 0 (rozproszone) do 1 (ten sam dzień); z półroczy IMGW-PIB, gdzie są (data większego z półrocznych maksimów), inaczej z pełnych lat szeregu dobowego (prototyp H13). Wskaźnik sezonowości Walsha i Lawlera (1981) średnich odpływów miesięcznych: 0 – równomierny, 1,83 – cały odpływ w jednym miesiącu.`;

/** Calendar month index (1-12) of the i-th hydrological month (0 = XI). */
const CALENDAR = [11, 12, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10];
const MONTH_TICKS = HYDRO_MONTHS.map((label, at) => ({ value: at + 1, label }));

function dailySpec(daily, variable, unitText) {
  const x = daily.day_of_year;
  return {
    x: { label: "doba roku hydrologicznego", tickList: DOY_TICKS, min: 1, max: 366 },
    y: { label: `${variable} [${unitText}]`, unit: unitText, zero: variable === "Q", digits: digitsOf(variable) },
    series: [
      { id: "range", kind: "band", cls: "s4", label: "min–maks", data: x.map((d, at) => [d, daily.min_values[at], daily.max_values[at]]) },
      { id: "mean", kind: "line", cls: "s1", label: "średnia", data: x.map((d, at) => [d, daily.mean_values[at]]) },
      { id: "median", kind: "line", cls: "s5", label: "mediana", data: x.map((d, at) => [d, daily.median_values[at]]) },
    ],
    legend: true,
    readout: { series: "mean", x: doyLabel },
    fit: { ratio: 0.55, minHeight: 210 },
    title: "Reżim dobowy",
  };
}

function monthlyRows(monthly) {
  return CALENDAR.map((month, at) => {
    const i = month - 1;
    return {
      m: HYDRO_MONTHS[at],
      mean: monthly.mean_values[i],
      median: monthly.median_values[i],
      min: monthly.min_values[i],
      max: monthly.max_values[i],
      std: monthly.std_values[i],
      cv: monthly.cv_values[i],
      skew: monthly.skewness_values[i],
      ci: [monthly.ci_lower[i], monthly.ci_upper[i]],
    };
  });
}

function monthlySpec(monthly, variable, unitText) {
  const rows = monthlyRows(monthly);
  return {
    x: { label: "miesiąc", tickList: MONTH_TICKS, min: 0.5, max: 12.5 },
    y: { label: `${variable} [${unitText}]`, unit: unitText, zero: variable === "Q", digits: digitsOf(variable) },
    series: [
      { id: "ci", kind: "band", cls: "s1", label: `przedział ufności ${fmt(monthly.confidence_level * 100, 0)} %`, data: rows.map((r, at) => [at + 1, r.ci[0], r.ci[1]]) },
      { id: "mean", kind: "line", cls: "s1", label: "średnia", data: rows.map((r, at) => [at + 1, r.mean]) },
      { id: "median", kind: "line", cls: "s5", label: "mediana", data: rows.map((r, at) => [at + 1, r.median]) },
    ],
    legend: true,
    readout: { series: "mean", x: (x) => HYDRO_MONTHS[Math.round(x) - 1] || "" },
    fit: { ratio: 0.45, minHeight: 180 },
    title: "Statystyki miesięczne",
  };
}

function pardeSpec(coefficients) {
  return {
    x: { label: "miesiąc", tickList: MONTH_TICKS, min: 0.5, max: 12.5 },
    y: { label: "współczynnik Pardégo", digits: 2 },
    series: [{ id: "pk", kind: "bars", cls: "s1", align: "center", label: "Qm / Qr", data: CALENDAR.map((month, at) => [at + 1, coefficients[month - 1]]) }],
    marks: [{ kind: "hline", y: 1, label: "1,00" }],
    readout: { x: (x) => HYDRO_MONTHS[Math.round(x) - 1] || "" },
    fit: { ratio: 0.42, minHeight: 170 },
    title: "Współczynniki Pardégo",
  };
}

/** A circle of the year (1 I at the top, clockwise) with the dates of annual extremes. */
function Circle({ entry, label }) {
  const c = 100;
  const R = 78;
  const rows = entry.rows;
  const years = rows.map((r) => r.year);
  const y0 = Math.min(...years);
  const y1 = Math.max(...years);
  const position = (angle, radius) => [c + radius * Math.sin(angle), c - radius * Math.cos(angle)];
  const ticks = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334].map((day, at) => ({ angle: (2 * Math.PI * day) / 365, label: ROMAN[at] }));
  const circle = entry.circular;
  const mean = circle ? position((2 * Math.PI * (circle.mean_day - 0.5)) / 365.25, circle.r * R) : null;
  return html`<figure class="hy-circle">
    <svg viewBox="0 0 200 200" role="img" aria-label=${`${label}: terminy na okręgu roku`}>
      <circle class="hy-circle-ring" cx=${c} cy=${c} r=${R} />
      <circle class="hy-circle-ring inner" cx=${c} cy=${c} r=${R / 2} />
      ${ticks.map(({ angle, label: text }) => {
        const [x1, y1] = position(angle, R - 4);
        const [x2, y2] = position(angle, R + 4);
        const [tx, ty] = position(angle + Math.PI / 12, R + 13);
        return html`<g><line class="hy-circle-tick" x1=${x1} y1=${y1} x2=${x2} y2=${y2} /><text class="hy-circle-label" x=${tx} y=${ty + 3}>${text}</text></g>`;
      })}
      ${rows.map((row, at) => {
        const angle = circle.angles[at];
        const radius = 22 + ((R - 28) * (row.year - y0)) / Math.max(1, y1 - y0);
        const [x, y] = position(angle, radius);
        return html`<circle class=${`hy-circle-dot ${row.half}`} cx=${x} cy=${y} r="3"><title>${row.year}: ${date(row.date)}, ${fmtV(row.value, "Q")}</title></circle>`;
      })}
      ${mean && html`<line class="hy-circle-mean" x1=${c} y1=${c} x2=${mean[0]} y2=${mean[1]} /><circle class="hy-circle-head" cx=${mean[0]} cy=${mean[1]} r="3.5" />`}
    </svg>
    <figcaption>${label}: punkt na okręgu to termin, odległość od środka rok (${y0} w środku, ${y1} na zewnątrz); kolor: półrocze zimowe lub letnie; wektor – średni termin, długość r.</figcaption>
  </figure>`;
}

function Seasonality({ state, opt, setOpt }) {
  const data = state.data;
  const stat = opt.extreme;
  const entry = data && data[stat];
  const months = useMemo(() => {
    if (!entry) return null;
    return {
      x: { label: "miesiąc", tickList: MONTH_TICKS, min: 0.5, max: 12.5 },
      y: { label: "lat", digits: 0 },
      series: [{ id: "n", kind: "bars", cls: stat === "max" ? "s2" : "s3", align: "center", label: stat === "max" ? "maksimów" : "minimów", data: CALENDAR.map((month, at) => [at + 1, entry.months[month - 1]]) }],
      readout: { x: (x) => HYDRO_MONTHS[Math.round(x) - 1] || "" },
      fit: { ratio: 0.38, minHeight: 150 },
      title: "Miesiące terminów",
    };
  }, [data, stat]);
  const name = data && (data.var === "H" ? (stat === "max" ? "WW" : "NW") : stat === "max" ? "WQ" : "NQ");
  return html`<${Block} state=${state} title="Sezonowość ekstremów rocznych (H13)">
    ${data && html`
      <div class="hy-options">
        <${Option} label="Ekstrema"><${Seg} value=${stat} label="Ekstrema" options=${[["max", "maksima"], ["min", "minima"]]} onChange=${(v) => setOpt({ extreme: v })} /></${Option}>
        <${Option} label="Zmienna"><${Seg} value=${data.var} label="Zmienna" options=${[["Q", "Q"], ["H", "H"]]} onChange=${(v) => setOpt({ svar: v })} /></${Option}>
      </div>
      ${entry && entry.rows.length
        ? html`
          <${Figures}
            items=${[
              { label: `Średni termin ${name}`, value: entry.circular.mean_date, note: `${entry.circular.n} lat ${data.years.from}–${data.years.to}` },
              { label: "Koncentracja r", value: fmt(entry.circular.r, 2), note: "0 rozproszone, 1 ten sam dzień" },
              { label: "W półroczu zimowym", value: `${fmt(entry.winter_share * 100, 0)} %`, note: "XI–IV" },
              { label: "Źródło", value: data.source === "imgw" ? "półrocza IMGW-PIB" : "szereg dobowy" },
            ]}
          />
          <div class="hy-pair">
            <${Circle} entry=${entry} label=${`Terminy ${name}`} />
            <div class="hy-pair-side"><${Chart} spec=${months} /></div>
          </div>`
        : html`<p class="hy-note">Brak dat ekstremów.</p>`}
    `}
  </${Block}>`;
}

/** The section „Reżim i sezonowość”. */
export function Regime({ station }) {
  const code = station.code;
  const [opt, setOpt] = useOptions({ var: undefined, from: undefined, to: undefined, extreme: "max", svar: undefined }, code);
  const state = useAnalysis("hydro_regime", code, { var: opt.var, from: opt.from, to: opt.to });
  const seasons = useAnalysis("hydro_seasonality", code, { var: opt.svar, from: opt.from, to: opt.to });
  const data = state.data;
  const variables = (station.datasets || [])
    .filter((d) => d.dataset.endsWith("hydro_daily"))
    .flatMap((d) => Object.keys(d.variables))
    .filter((v) => ["Q", "H", "T"].includes(v));
  const unitText = data ? { "m3/s": "m³/s", degC: "°C" }[data.unit] || data.unit : "";
  const daily = useMemo(() => data && dailySpec(data.daily, data.var, unitText), [data]);
  const monthly = useMemo(() => data && monthlySpec(data.monthly, data.var, unitText), [data]);
  const parde = useMemo(() => data && data.parde && pardeSpec(data.parde.coefficients), [data]);
  const columns = data && [
    { key: "m", label: "Miesiąc", format: (v) => v },
    { key: "mean", label: "średnia", format: (v) => fmtV(v, data.var) },
    { key: "median", label: "mediana", format: (v) => fmtV(v, data.var) },
    { key: "min", label: "min", format: (v) => fmtV(v, data.var) },
    { key: "max", label: "maks", format: (v) => fmtV(v, data.var) },
    { key: "std", label: "odch. std.", format: (v) => fmtV(v, data.var) },
    { key: "cv", label: "CV", format: (v) => fmt(v, 2) },
    { key: "skew", label: "skośność", format: (v) => fmt(v, 2) },
    { key: "ci", label: `PU ${fmt(data.monthly.confidence_level * 100, 0)} %`, format: (v) => `${fmtV(v[0], data.var)}–${fmtV(v[1], data.var)}` },
  ];
  const type = data && data.regime_type;
  return html`<${Section} title="Reżim i sezonowość" info=${INFO} state=${state}>
    ${data && html`
      <${Years} data=${data} onApply=${(from, to) => setOpt({ from, to })} />
      ${variables.length > 1 && html`<${Option} label="Zmienna"><${VariableSeg} value=${data.var} variables=${["Q", "H", "T"].filter((v) => variables.includes(v))} onChange=${(v) => setOpt({ var: v })} /></${Option}>`}
      <h4 class="hy-sub">Reżim dobowy (H10)</h4>
      <${Chart} spec=${daily} />
      <h4 class="hy-sub">Statystyki miesięczne (H11)</h4>
      <${Chart} spec=${monthly} />
      <${Table} columns=${columns} rows=${monthlyRows(data.monthly)} className="tbl hy-compact" />
      ${data.parde
        ? html`
          <h4 class="hy-sub">Współczynniki Pardégo i typ reżimu (H12)</h4>
          <${Figures}
            items=${[
              { label: "Typ reżimu (roboczo)", value: type.label, note: `Dynowska 1997, typ ${type.code}` },
              { label: "Miesiąc wiosenny", value: `${ROMAN[type.spring.month - 1]}: ${fmt(type.spring.coefficient * 100, 0)} %` },
              { label: "Miesiąc letni", value: `${ROMAN[type.summer.month - 1]}: ${fmt(type.summer.coefficient * 100, 0)} %` },
              { label: "Odpływ III–IV", value: `${fmt(data.spring_share * 100, 1)} %`, note: "udział w rocznym" },
              { label: "Wskaźnik sezonowości", value: fmt(data.seasonality_index, 3), note: "Walsh i Lawler 1981" },
            ]}
          />
          <${Chart} spec=${parde} />
          <p class="muted hy-caption">Klasyfikacja robocza (do ustalenia w planie Hydrologa): progi 130 i 180 % oraz 100 % lata wg Dynowskiej (1997) za Wrzesińskim (2018); odczyt „miesiąca wiosennego” (III–IV), „letniego” (VI–VIII) i „prawie równy” (≥ 95 %) jest nasz. ${data.complete_years < 10 ? "Uwaga: mniej niż 10 pełnych lat." : `Pełnych lat: ${data.complete_years}.`}</p>`
        : html`<p class="hy-note">Współczynniki Pardégo i typ reżimu liczy się z przepływów Q${data.var !== "Q" ? `; wybrano ${VARIABLES[data.var]}` : ""}.</p>`}
      <${Notices} items=${data.notices} />
    `}
    <${Seasonality} state=${seasons} opt=${opt} setOpt=${setOpt} />
  </${Section}>`;
}
