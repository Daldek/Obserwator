// „Śnieg” (Nogat plan M10): days with snow cover, the maximum depth of each winter, the first
// and last day with cover, fresh snow (IMGW-PIB `snow_cover`, `fresh_snow`).

import { Chart, fmt, html, useMemo, useState } from "../../lib.js";
import { Figures, Section, Seg, Table, useAnalysis } from "../common.js";
import { DatasetSeg, Option, ROMAN, Source, date, monthDay, num, useOptions, yearAxis } from "./util.js";

const INFO = `Sezon zimowy trwa od 1 VIII do 31 VII i nosi rok swojego końca (sezon 1990/91 to „1991”). Dzień z pokrywą śnieżną to dzień z grubością pokrywy co najmniej 1 cm w porannym pomiarze IMGW-PIB (obok dni z pokrywą ≥ 10 cm). Sezon liczę, gdy w każdym miesiącu X–V brakuje mniej niż 11 dni i mniej niż 5 kolejnych; liczba dni miesiąca to udział dni z pokrywą wśród dni z pomiarem razy liczba dni miesiąca (WMO-No. 1203, 2017, p. 4.4.1 d). Maksimum, pierwszy i ostatni dzień z pokrywą — z dni z pomiarem. Suma śniegu świeżego (stacje opadowe, „fresh_snow”) to suma grubości warstwy świeżego śniegu w sezonie. Terminy średnie to mediany dni sezonu.`;

function season(year) {
  return `${year - 1}/${String(year).slice(2)}`;
}

/** The card „Śnieg”. */
export function Snieg({ station }) {
  const code = station.code;
  const [opt, setOpt] = useOptions({ dataset: undefined }, code);
  const state = useAnalysis("meteo-snow", code, { dataset: opt.dataset });
  const data = state.data;
  const [view, setView] = useState("days");
  const spec = useMemo(() => {
    if (!data) return null;
    const max = view === "max";
    return {
      x: yearAxis(data.seasons, "sezon (rok końca)", "season"),
      y: { label: max ? "maksymalna grubość pokrywy [cm]" : "dni z pokrywą śnieżną", unit: max ? "cm" : "dni" },
      series: max
        ? [{ id: "max", kind: "bars", cls: "s4", label: "maksimum", align: "center", data: data.seasons.map((r) => [r.season, r.max]) }]
        : [
            { id: "days", kind: "bars", cls: "s4", label: "dni ≥ 1 cm", align: "center", data: data.seasons.map((r) => [r.season, r.days]) },
            { id: "days10", kind: "points", label: "dni ≥ 10 cm", data: data.seasons.map((r) => [r.season, r.days10]) },
          ],
      marks: [{ kind: "hline", y: max ? data.summary.max : data.summary.days, label: `średnio ${fmt(max ? data.summary.max : data.summary.days, 0)}` }],
      legend: !max,
      readout: { x: (x) => `sezon ${season(Math.round(x))}`, value: (v) => fmt(v, 0) },
      fit: { ratio: 0.45, minHeight: 170 },
      title: max ? "Maksymalna grubość pokrywy w sezonach" : "Dni z pokrywą śnieżną w sezonach",
    };
  }, [data, view]);
  const s = data && data.summary;
  const columns = data
    ? [
        { key: "season", label: "Sezon", format: (v) => season(v) },
        { key: "days", label: "Dni ≥ 1 cm", format: (v) => num(v, 0) },
        { key: "days10", label: "≥ 10 cm", format: (v) => num(v, 0) },
        { key: "max", label: "Maks. [cm] (data)", format: (v, r) => (v ? `${fmt(v, 0)} (${date(r.max_date)})` : num(v, 0)) },
        { key: "first", label: "Pierwszy", format: (v) => date(v) },
        { key: "last", label: "Ostatni", format: (v) => date(v) },
        ...(data.fresh ? [{ key: "fresh_sum", label: "Świeży [cm]", format: (v, r) => `${num(v, 0)} (${r.fresh_days} d)` }] : []),
      ]
    : [];
  return html`<div class="me-card">
    ${data && data.datasets.length > 1 && html`<div class="me-toolbar"><${DatasetSeg} data=${data} value=${opt.dataset} onChange=${(v) => setOpt({ dataset: v })} /></div>`}
    <${Section} title="Pokrywa śnieżna" info=${INFO} state=${state}>
      ${data &&
      html`
        <${Source} data=${data} />
        <${Figures}
          items=${[
            { label: "Dni z pokrywą ≥ 1 cm", value: num(s.days, 0), note: `średnio w sezonie, ${s.seasons} sezonów` },
            { label: "Dni z pokrywą ≥ 10 cm", value: num(s.days10, 0), note: "średnio w sezonie" },
            { label: "Maksimum sezonu", value: num(s.max, 0, "cm"), note: "średnio" },
            { label: "Największa grubość", value: num(s.record.value, 0, "cm"), note: s.record.date ? date(s.record.date) : "" },
            { label: "Pierwszy · ostatni dzień", value: `${monthDay(s.first_median)} · ${monthDay(s.last_median)}`, note: `mediana; skrajnie ${date(s.earliest)} · ${date(s.latest)}` },
            ...(data.fresh ? [{ label: "Śnieg świeży", value: num(s.fresh_sum, 0, "cm"), note: `${num(s.fresh_days, 0)} dni w sezonie` }] : []),
          ]}
        />
        <${Option} label="Wykres"><${Seg} value=${view} label="Wykres śniegu" options=${[["days", "dni z pokrywą"], ["max", "maksimum"]]} onChange=${setView} /></${Option}>
        <${Chart} spec=${spec} />
        <h4 class="me-sub">Dni z pokrywą średnio w miesiącu</h4>
        <${Table}
          columns=${data.months.map((m) => ({ key: `m${m.month}`, label: ROMAN[m.month - 1], format: (v) => num(v, 1) }))}
          rows=${[Object.fromEntries(data.months.map((m) => [`m${m.month}`, m.days]))]}
          className="tbl me-wide"
        />
        <h4 class="me-sub">Sezony</h4>
        <${Table} columns=${columns} rows=${[...data.seasons].reverse()} max=${10} />
        ${s.no_cover ? html`<p class="muted me-caption">Sezonów bez pokrywy: ${s.no_cover}.</p>` : null}
        ${s.skipped ? html`<p class="muted me-caption">Pominięte sezony bez dość pomiarów pokrywy w miesiącach X–V: ${s.skipped}.</p>` : null}
      `}
    </${Section}>
  </div>`;
}
