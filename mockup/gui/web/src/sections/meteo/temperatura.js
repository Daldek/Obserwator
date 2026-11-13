// „Temperatura” (Nogat plan M11, M12, M14, M15): means, extremes, the normal and anomalies,
// characteristic days and degree days, the warming stripes, the annual cycle and its
// harmonics, Sielianinov's hydrothermal coefficient and de Martonne's aridity index. A
// station without air temperature (a precipitation post) gets a note of what it lacks.

import { Chart, fmt, html, useMemo, useState } from "../../lib.js";
import { Figures, Section, Seg, Table, YearRange, useAnalysis } from "../common.js";
import { Stripes } from "./stripes.js";
import { ClassLegend, DatasetSeg, MONTH_TICKS, Option, ROMAN, Source, byYear, classCls, datasetsWith, date, dayLabel, num, part, stationHas, useOptions, yearAxis, yearReadout } from "./util.js";

const INFO_T = `Średnie miesięczne Tśr, Tmax i Tmin liczę, gdy w miesiącu brakuje mniej niż 11 dni i mniej niż 5 kolejnych (WMO-No. 1203, 2017, p. 4.4.1 a); średnia roczna to średnia dwunastu takich miesięcy. Normalna to średnia z okresu odniesienia (domyślnie cały zapis stacji; można go zawęzić, zalecany minimalny okres to 30 lat), liczona, gdy wartości ma co najmniej 80 % lat okresu (p. 4.4.2); anomalia to różnica od normalnej. Ekstrema bezwzględne biorą wszystkie dni z pomiarem (p. 4.4.1 b). Amplituda dobowa to średnia Tmax − Tmin dni z oboma pomiarami.`;

const INFO_DAYS = `Dni charakterystyczne wg definicji ETCCDI (Zhang i in. 2011): z przymrozkiem Tmin < 0 °C (FD), mroźne Tmax < 0 °C (ID), gorące Tmax > 25 °C (SU), noce tropikalne Tmin > 20 °C (TR), oraz dni upalne Tmax > 30 °C. Liczba dni miesiąca to udział takich dni wśród dni z pomiarem razy liczba dni miesiąca, gdy brakuje mniej niż 11 dni i mniej niż 5 kolejnych (WMO-No. 1203, p. 4.4.1 d). Stopniodni wzrostu: Σ max(Tśr − 5 °C, 0); stopniodni grzania wg Eurostatu: Σ (18 °C − Tśr) w dniach z Tśr ≤ 15 °C; obie sumy z miesięcy bez braków.`;

const INFO_HARM = `Analiza harmoniczna cyklu rocznego średniej dobowej temperatury: metodą najmniejszych kwadratów dopasowuję T(t) = A₀ + Σₖ Cₖ·cos(2πk(t − tₖ)), k = 1, 2, gdzie t to ułamek roku w środku doby; Cₖ to amplituda, tₖ termin maksimum (dla k = 2 pierwsze z dwóch), udział wariancji — przyrost R² kolejnych harmonik (dla roku bez braków równy Cₖ²/2 przez wariancję). Dla okresu dopasowuję średni cykl (średnia każdego dnia roku z lat okresu; udział wariancji odnosi się do tego cyklu), obok udział wariancji wartości dobowych wyjaśniony przez dwie harmoniki. Lata liczę, gdy każdy miesiąc ma mniej niż 11 braków i mniej niż 5 kolejnych (WMO-No. 1203). Tę samą metodę autor stosował do temperatury wody z boi bałtyckich; w planie to M12, wspólne z H14.`;

const INFO_HTC = `Współczynnik hydrotermiczny Sielianinowa k = P / (0,1·Σt): P to suma opadu miesiąca [mm], Σt suma temperatur dobowych miesiąca, tu średnia miesięczna razy liczba dni (jak Skowera i Puła 2004, Acta Agrophysica 3(1)); liczę go dla miesięcy IV–IX, gdy obie wartości są pełne i średnia temperatura jest dodatnia. Klasy Skowery i Puły (2004): k ≤ 0,4 skrajnie suchy, ≤ 0,7 bardzo suchy, ≤ 1,0 suchy, ≤ 1,3 dość suchy, ≤ 1,6 optymalny, ≤ 2,0 dość wilgotny, ≤ 2,5 wilgotny, ≤ 3,0 bardzo wilgotny, > 3,0 skrajnie wilgotny. „Okres > 10 °C” to wersja pierwotna: opad i suma temperatur dni ze średnią powyżej 10 °C w roku z pełnym pomiarem. Wskaźnik suchości de Martonne’a (1926) I = P / (T + 10) z sumy rocznej i średniej rocznej; klasy wg Baltasa (2007): < 10 suchy, < 20 półsuchy, < 24 śródziemnomorski, < 28 półwilgotny, < 35 wilgotny, ≤ 55 bardzo wilgotny, > 55 skrajnie wilgotny.`;

const VAR_NAMES = { Tmean: "Tśr", Tmax: "Tmax", Tmin: "Tmin" };

function Temperature({ state }) {
  const data = state.data;
  const [view, setView] = useState("mean");
  const spec = useMemo(() => {
    if (!data) return null;
    if (view === "anomaly") {
      return {
        x: yearAxis(data.annual),
        y: { label: `anomalia ${VAR_NAMES[data.main]} [°C]`, unit: "°C", zero: true },
        series: [{ id: "anom", kind: "bars", label: "anomalia", align: "center", data: data.annual.map((r) => ({ x: r.year, y: r.anomaly, cls: r.anomaly === null ? "" : r.anomaly >= 0 ? "me-warm" : "me-cold" })), digits: 2 }],
        readout: { x: yearReadout },
        fit: { ratio: 0.45, minHeight: 170 },
        title: "Anomalia temperatury rocznej",
      };
    }
    if (view === "months") {
      const series = [];
      if (data.variables.includes("Tmax") && data.variables.includes("Tmin")) {
        series.push({ id: "range", kind: "band", cls: "s4", label: "średnia Tmin–Tmax", data: data.months.map((m) => [m.month, m.tmin ?? null, m.tmax ?? null]) });
      }
      series.push({ id: "mean", kind: "line", cls: "s1", label: `średnia ${VAR_NAMES[data.main]}`, data: data.months.map((m) => [m.month, m.mean]), digits: 1 });
      series.push({ id: "normal", kind: "line", cls: "s6", label: `normalna ${data.reference.from}–${data.reference.to}`, data: data.months.map((m) => [m.month, m.normal]), digits: 1 });
      return {
        x: { label: "miesiąc", tickList: ROMAN.map((label, at) => ({ value: at + 1, label })), min: 1, max: 12 },
        y: { label: "temperatura [°C]", unit: "°C", zero: false },
        series,
        legend: true,
        readout: { x: (x) => ROMAN[Math.round(x) - 1] || "" },
        fit: { ratio: 0.5, minHeight: 190 },
        title: "Przebieg roczny temperatury",
      };
    }
    return {
      x: yearAxis(data.annual),
      y: { label: `średnia roczna ${VAR_NAMES[data.main]} [°C]`, unit: "°C", zero: false },
      series: [{ id: "mean", kind: "line", cls: "s1", label: "średnia roczna", data: byYear(data.annual, "mean"), digits: 2 }],
      marks: data.normal.annual === null ? [] : [{ kind: "hline", y: data.normal.annual, label: `normalna ${fmt(data.normal.annual, 1)} °C` }],
      readout: { x: yearReadout },
      fit: { ratio: 0.45, minHeight: 170 },
      title: "Średnia roczna temperatura",
    };
  }, [data, view]);
  if (!data) return html`<${Section} title="Średnie, ekstrema i normalna" info=${INFO_T} state=${part(state, "means")} />`;
  const last = [...data.annual].reverse().find((r) => r.mean !== null);
  const ref = data.reference;
  const columns = [
    { key: "month", label: "Miesiąc", format: (v) => ROMAN[v - 1] },
    { key: "normal", label: `Normalna`, format: (v) => num(v, 1) },
    { key: "mean", label: VAR_NAMES[data.main], format: (v) => num(v, 1) },
    ...(data.variables.includes("Tmax") ? [{ key: "tmax", label: "Tmax", format: (v) => num(v, 1) }] : []),
    ...(data.variables.includes("Tmin") ? [{ key: "tmin", label: "Tmin", format: (v) => num(v, 1) }] : []),
    ...(data.means.dtr !== undefined ? [{ key: "dtr", label: "Ampl.", format: (v) => num(v, 1) }] : []),
    ...(data.variables.includes("Tmax") ? [{ key: "abs_max", label: "Maks. abs.", format: (v, r) => (v === null || v === undefined ? "–" : `${fmt(v, 1)} (${r.abs_max_date.slice(0, 4)})`) }] : []),
    ...(data.variables.includes("Tmin") ? [{ key: "abs_min", label: "Min. abs.", format: (v, r) => (v === null || v === undefined ? "–" : `${fmt(v, 1)} (${r.abs_min_date.slice(0, 4)})`) }] : []),
  ];
  const yearColumns = [
    { key: "year", label: "Rok", format: (v) => String(v) },
    { key: "mean", label: VAR_NAMES[data.main], format: (v) => num(v, 2) },
    { key: "anomaly", label: "Anomalia", format: (v) => (v === null || v === undefined ? "–" : `${v > 0 ? "+" : ""}${fmt(v, 2)}`) },
    ...(data.variables.includes("Tmax") ? [{ key: "abs_max", label: "Maks. (data)", format: (v, r) => (v === null || v === undefined ? "–" : `${fmt(v, 1)} (${date(r.abs_max_date)})`) }] : []),
    ...(data.variables.includes("Tmin") ? [{ key: "abs_min", label: "Min. (data)", format: (v, r) => (v === null || v === undefined ? "–" : `${fmt(v, 1)} (${date(r.abs_min_date)})`) }] : []),
  ];
  return html`<${Section} title="Średnie, ekstrema i normalna" info=${INFO_T} state=${part(state, "means")}>
    <${Source} data=${data} />
    <${Figures}
      items=${[
        { label: `Normalna ${ref.from}–${ref.to}`, value: num(data.normal.annual, 1, "°C"), note: `${ref.years} lat, ${VAR_NAMES[data.main]}` },
        { label: `Rok ${last ? last.year : "–"}`, value: last ? num(last.mean, 1, "°C") : "–", note: last && last.anomaly !== null ? `anomalia ${last.anomaly > 0 ? "+" : ""}${fmt(last.anomaly, 1)} °C` : "" },
        ...(data.records.max ? [{ label: "Najwyższa Tmax", value: num(data.records.max.value, 1, "°C"), note: date(data.records.max.date) }] : []),
        ...(data.records.min ? [{ label: "Najniższa Tmin", value: num(data.records.min.value, 1, "°C"), note: date(data.records.min.date) }] : []),
        ...(data.means.dtr !== null && data.means.dtr !== undefined ? [{ label: "Amplituda dobowa", value: num(data.means.dtr, 1, "°C"), note: "średnio" }] : []),
      ]}
    />
    <${Option} label="Wykres"><${Seg} value=${view} label="Wykres temperatury" options=${[["mean", "średnia roczna"], ["anomaly", "anomalia"], ["months", "miesiące"]]} onChange=${setView} /></${Option}>
    <${Chart} spec=${spec} />
    <h4 class="me-sub">Miesiące [°C]</h4>
    <${Table} columns=${columns} rows=${data.months} />
    <h4 class="me-sub">Lata [°C]</h4>
    <${Table} columns=${yearColumns} rows=${[...data.annual].reverse()} max=${10} />
    <details class="me-details"><summary>Anomalie miesięcy wszystkich lat [°C]</summary>
      <${AnomalyTable} rows=${[...data.anomalies].reverse()} />
    </details>
  </${Section}>`;
}

function AnomalyTable({ rows }) {
  const cls = (v) => (v === null ? "" : v >= 2 ? "me-a3" : v >= 1 ? "me-a2" : v >= 0.25 ? "me-a1" : v <= -2 ? "me-a-3" : v <= -1 ? "me-a-2" : v <= -0.25 ? "me-a-1" : "");
  return html`<div class="table-wrap"><table class="tbl me-heat">
    <thead><tr><th scope="col">Rok</th>${ROMAN.map((m) => html`<th scope="col">${m}</th>`)}</tr></thead>
    <tbody>${rows.map((r) => html`<tr><th scope="row">${r.year}</th>${r.months.map((v) => html`<td class=${cls(v)}>${v === null ? "–" : fmt(v, 1)}</td>`)}</tr>`)}</tbody>
  </table></div>`;
}

const DAY_KEYS = [
  ["fd", "przymrozek", "Tmin < 0 °C"],
  ["id", "mroźne", "Tmax < 0 °C"],
  ["su", "gorące", "Tmax > 25 °C"],
  ["hd", "upalne", "Tmax > 30 °C"],
  ["tr", "noce tropikalne", "Tmin > 20 °C"],
  ["gdd5", "stopniodni wzrostu", "Σ (Tśr − 5)"],
  ["hdd", "stopniodni grzania", "Σ (18 − Tśr), Tśr ≤ 15"],
];

function CharacteristicDays({ state }) {
  const data = state.data;
  const keys = data ? DAY_KEYS.filter(([k]) => data.counts.includes(k) || data.degree_days.includes(k)) : [];
  const [key, setKey] = useState("fd");
  const chosen = keys.find(([k]) => k === key) || keys[0];
  const spec = useMemo(() => {
    if (!data || !chosen) return null;
    const [k, name, rule] = chosen;
    const degree = k === "gdd5" || k === "hdd";
    return {
      x: yearAxis(data.annual),
      y: { label: degree ? `${name} [°C·d]` : `dni: ${name} (${rule})`, unit: degree ? "°C·d" : "dni" },
      series: [{ id: k, kind: "bars", cls: k === "fd" || k === "id" || k === "hdd" ? "me-bar-cold" : "me-bar-warm", label: name, align: "center", data: byYear(data.annual, k) }],
      marks: data.means[k] === null || data.means[k] === undefined ? [] : [{ kind: "hline", y: data.means[k], label: `średnio ${fmt(data.means[k], degree ? 0 : 1)}` }],
      readout: { x: yearReadout, value: (v) => fmt(v, 0) },
      fit: { ratio: 0.45, minHeight: 170 },
      title: `${name} w latach`,
    };
  }, [data, chosen && chosen[0]]);
  if (!data) return html`<${Section} title="Dni charakterystyczne i stopniodni" info=${INFO_DAYS} state=${part(state, "days")} />`;
  const countKeys = DAY_KEYS.filter(([k]) => data.counts.includes(k));
  return html`<${Section} title="Dni charakterystyczne i stopniodni" info=${INFO_DAYS} state=${part(state, "days")}>
    <${Figures} items=${keys.map(([k, name, rule]) => ({ label: name, value: num(data.means[k], k === "gdd5" || k === "hdd" ? 0 : 1), note: `${rule}, średnio w roku` }))} />
    <${Option} label="Wskaźnik"><${Seg} value=${chosen ? chosen[0] : key} label="Wskaźnik" options=${keys.map(([k, name]) => [k, name])} onChange=${setKey} /></${Option}>
    <${Chart} spec=${spec} />
    <h4 class="me-sub">Średnio w miesiącu [dni]</h4>
    <${Table}
      columns=${[{ key: "month", label: "Miesiąc", format: (v) => ROMAN[v - 1] }, ...countKeys.map(([k, name]) => ({ key: k, label: name, format: (v) => num(v, 1) }))]}
      rows=${data.months}
    />
  </${Section}>`;
}

function Harmonics({ state, onRange }) {
  const data = state.data;
  const spec = useMemo(() => {
    if (!data) return null;
    const days = data.cycle.mean.map((_, at) => at + 1);
    return {
      x: { label: "dzień roku", tickList: MONTH_TICKS, min: 1, max: 365 },
      y: { label: "Tśr [°C]", unit: "°C", zero: false },
      series: [
        { id: "mean", kind: "line", cls: "s4", label: "średnia dnia roku", data: days.map((d, at) => [d, data.cycle.mean[at]]), digits: 1 },
        { id: "h1", kind: "line", cls: "s2", label: "1. harmonika", data: days.map((d, at) => [d, data.cycle.first[at]]), digits: 1 },
        { id: "fit", kind: "line", cls: "s1", label: "1. + 2. harmonika", data: days.map((d, at) => [d, data.cycle.fit[at]]), digits: 1 },
      ],
      marks: [{ kind: "vline", x: data.period.day1, label: `maks. ${dayLabel(data.period.day1)}` }],
      legend: true,
      readout: { series: "fit", x: (x) => dayLabel(x) },
      fit: { ratio: 0.5, minHeight: 190 },
      title: "Średni cykl roczny temperatury",
    };
  }, [data]);
  const yearSpec = useMemo(() => {
    if (!data) return null;
    return {
      x: yearAxis(data.years),
      y: { label: "dzień roku maksimum 1. harmoniki (200 = 19 VII)", unit: "", zero: false },
      series: [{ id: "day1", kind: "points", label: "termin maksimum", data: data.years.map((r) => [r.year, r.day1]) }],
      readout: { x: yearReadout, value: (v) => dayLabel(v) },
      fit: { ratio: 0.38, minHeight: 150 },
      title: "Termin maksimum w latach",
    };
  }, [data]);
  if (!data) return html`<${Section} title="Cykl roczny i harmoniki" info=${INFO_HARM} state=${state} />`;
  const p = data.period;
  const r = data.years_range;
  return html`<${Section} title="Cykl roczny i harmoniki" info=${INFO_HARM} state=${state}>
    <${YearRange} first=${r.first} last=${r.last} from=${r.from} to=${r.to} label="Lata" onApply=${onRange} />
    <${Figures}
      items=${[
        { label: "Średnia A₀", value: num(p.mean, 2, "°C"), note: `${r.count} lat` },
        { label: "Amplituda C₁", value: num(p.c1, 2, "°C"), note: `maksimum ${dayLabel(p.day1)} (dzień ${fmt(p.day1, 1)})` },
        { label: "Amplituda C₂", value: num(p.c2, 2, "°C"), note: `maksimum ${dayLabel(p.day2)}` },
        { label: "Wariancja cyklu: 1. · 2.", value: `${num(p.ev1, 1)} · ${num(p.ev2, 2)} %` },
        { label: "Wariancja dobowa wyjaśniona", value: num(p.daily_ev, 1, "%"), note: "dwie harmoniki" },
      ]}
    />
    <${Chart} spec=${spec} />
    <${Chart} spec=${yearSpec} />
    <h4 class="me-sub">Lata</h4>
    <${Table}
      columns=${[
        { key: "year", label: "Rok", format: (v) => String(v) },
        { key: "mean", label: "A₀", format: (v) => num(v, 2) },
        { key: "c1", label: "C₁", format: (v) => num(v, 2) },
        { key: "day1", label: "Maks. 1.", format: (v) => dayLabel(v) },
        { key: "c2", label: "C₂", format: (v) => num(v, 2) },
        { key: "day2", label: "Maks. 2.", format: (v) => dayLabel(v) },
        { key: "ev1", label: "War. 1. %", format: (v) => num(v, 1) },
        { key: "ev2", label: "War. 2. %", format: (v) => num(v, 1) },
      ]}
      rows=${[...data.years].reverse()}
      max=${10}
    />
  </${Section}>`;
}

function Hydrothermal({ state }) {
  const data = state.data;
  const spec = useMemo(() => {
    if (!data) return null;
    return {
      x: yearAxis(data.years),
      y: { label: "k okresu Tśr > 10 °C", unit: "" },
      series: [{ id: "k", kind: "bars", label: "k", align: "center", data: data.years.map((r) => ({ x: r.year, y: r.season, cls: r.season_class === null ? "" : `me-k9${r.season_class}` })), digits: 2 }],
      marks: [
        { kind: "hline", y: 1.3, label: "1,3" },
        { kind: "hline", y: 1.6, label: "1,6" },
      ],
      readout: { x: yearReadout, value: (v) => fmt(v, 2) },
      fit: { ratio: 0.42, minHeight: 160 },
      title: "Współczynnik Sielianinowa w latach",
    };
  }, [data]);
  if (!data) return html`<${Section} title="Współczynnik hydrotermiczny" info=${INFO_HTC} state=${state} />`;
  const m = data.means;
  const rows = [...data.years].reverse();
  return html`<${Section} title="Współczynnik hydrotermiczny" info=${INFO_HTC} state=${state}>
    <${Figures}
      items=${[
        { label: "k okresu Tśr > 10 °C", value: num(m.season, 2), note: m.season_class === null ? "" : `średnio: ${data.classes[m.season_class]}` },
        { label: "Wskaźnik de Martonne’a", value: num(m.de_martonne, 1), note: m.de_martonne_class === null ? "" : data.de_martonne_classes[m.de_martonne_class] },
        ...data.frequency.map((f) => ({ label: `k ${ROMAN[f.month - 1]} średnio`, value: num(f.mean, 2), note: `${f.years} lat` })),
      ]}
    />
    <${Chart} spec=${spec} />
    <h4 class="me-sub">Klasy miesięcy IV–IX</h4>
    <div class="table-wrap"><table class="tbl me-heat">
      <thead><tr><th scope="col">Rok</th>${data.months.map((mo) => html`<th scope="col">${ROMAN[mo - 1]}</th>`)}<th scope="col">Tśr > 10</th><th scope="col">de Martonne</th></tr></thead>
      <tbody>${rows.slice(0, 20).map(
        (r) => html`<tr><th scope="row">${r.year}</th>
          ${r.k.map((v, at) => html`<td class=${classCls("k9", r.classes[at])} title=${r.classes[at] === null ? "" : data.classes[r.classes[at]]}>${v === null ? "–" : fmt(v, 2)}</td>`)}
          <td class=${classCls("k9", r.season_class)}>${r.season === null ? "–" : fmt(r.season, 2)}</td>
          <td title=${r.de_martonne_class === null ? "" : data.de_martonne_classes[r.de_martonne_class]}>${r.de_martonne === null ? "–" : fmt(r.de_martonne, 1)}</td>
        </tr>`,
      )}</tbody>
    </table></div>
    ${rows.length > 20 ? html`<p class="muted me-caption">Ostatnie 20 lat z ${rows.length}; częstości klas niżej liczę ze wszystkich.</p>` : null}
    <${ClassLegend} names=${data.classes} palette="k9" />
    <h4 class="me-sub">Częstość klas [lata]</h4>
    <div class="table-wrap"><table class="tbl me-heat">
      <thead><tr><th scope="col">Miesiąc</th>${data.classes.map((c, at) => html`<th scope="col" class=${classCls("k9", at)} title=${c}>${at + 1}</th>`)}</tr></thead>
      <tbody>${data.frequency.map((f) => html`<tr><th scope="row">${ROMAN[f.month - 1]}</th>${f.counts.map((c) => html`<td>${c}</td>`)}</tr>`)}</tbody>
    </table></div>
  </${Section}>`;
}

const T_SETS = ["pl.imgw.meteo_climate_daily", "cz.chmi.meteo_daily"];

/** The harmonics of the annual cycle, for a station with the daily mean temperature. */
function HarmonicsPart({ code, opt, setOpt }) {
  const state = useAnalysis("meteo-harmonics", code, { dataset: opt.dataset, from: opt.from, to: opt.to });
  return html`<${Harmonics} state=${state} onRange=${(a, b) => setOpt({ from: a, to: b })} />`;
}

/** The hydrothermal coefficient, for a station with precipitation and the mean temperature. */
function HydrothermalPart({ code, opt }) {
  const state = useAnalysis("meteo-hydrothermal", code, { dataset: opt.dataset });
  return html`<${Hydrothermal} state=${state} />`;
}

/** The card „Temperatura”: the stripes and the harmonics need Tśr, the coefficient also P in the same dataset. */
export function Temperatura({ station }) {
  const hasT = ["Tmean", "Tmax", "Tmin"].some((v) => stationHas(station, v, T_SETS));
  if (!hasT) {
    return html`<div class="me-card">
      <p class="note-box">Stacja nie mierzy temperatury powietrza (posterunek opadowy). Analizy tej sekcji, w tym paski klimatyczne, potrzebują pomiarów temperatury powietrza, a paski — średniej dobowej temperatury (Tśr).</p>
    </div>`;
  }
  return html`<${TemperatureCard} station=${station} />`;
}

function TemperatureCard({ station }) {
  const code = station.code;
  const [opt, setOpt] = useOptions({ dataset: undefined, ref_from: undefined, ref_to: undefined, from: undefined, to: undefined }, code);
  const temp = useAnalysis("meteo-temperature", code, { dataset: opt.dataset, ref_from: opt.ref_from, ref_to: opt.ref_to });
  const ref = temp.data && temp.data.reference;
  const hasMean = stationHas(station, "Tmean", T_SETS);
  const hasBoth = datasetsWith(station, ["P", "Tmean"], T_SETS).length > 0;
  return html`<div class="me-card">
    <div class="me-toolbar">
      <${DatasetSeg} data=${temp.data} value=${opt.dataset} onChange=${(v) => setOpt({ dataset: v })} />
      ${ref && html`<${YearRange} first=${ref.min} last=${ref.max} from=${ref.from} to=${ref.to} label="Okres odniesienia" onApply=${(a, b) => setOpt({ ref_from: a, ref_to: b })} />`}
    </div>
    <${Temperature} state=${temp} />
    ${hasMean && html`<${Stripes} station=${station} dataset=${opt.dataset} />`}
    <${CharacteristicDays} state=${temp} />
    ${hasMean && html`<${HarmonicsPart} code=${code} opt=${opt} setOpt=${setOpt} />`}
    ${hasBoth && html`<${HydrothermalPart} code=${code} opt=${opt} />`}
    ${!hasMean && html`<p class="muted me-caption">Stacja nie ma średniej dobowej temperatury: bez pasków klimatycznych, analizy harmonicznej i współczynnika hydrotermicznego.</p>`}
    ${hasMean && !hasBoth && html`<p class="muted me-caption">Stacja nie mierzy opadu: bez współczynnika hydrotermicznego.</p>`}
  </div>`;
}
