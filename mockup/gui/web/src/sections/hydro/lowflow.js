// „Niżówki” (Nogat plan H7): low-flow periods by the threshold level method, Hydrolog's
// `stats low-flow-sequences` on the gap-free spans, joined across gaps by the prototype.

import { api } from "../../api.js";
import { Chart, dayNumber, fmt, html, unit, useEffect, useMemo, useState } from "../../lib.js";
import { Figures, Section, Seg, Table, useAnalysis } from "../common.js";
import { Handoff, Option, Select, VariableSeg, Years, date, digitsOf, fmtV, useOptions } from "./util.js";

const INFO = `Niżówka to ciąg dni z wartością poniżej progu (metoda progowa, Tallaksen i van Lanen 2004), trwający co najmniej 5 dni; ciągi rozdzielone przerwą krótszą niż 4 dni łączy się w jeden (parametry metody find_low_sequences autora, 2024). Próg: SNQ (średni z rocznych minimów; Hydrolog „stats characteristic” z lat wybranego zakresu), Q70 lub Q90 (przepływ osiągany lub przekraczany przez 70 albo 90 % dni; prototyp krzywej czasu trwania H8) albo wartość podana. Ciągi wykrywa Hydrolog („stats low-flow-sequences”), który wymaga szeregu bez braków: dostaje każdy odcinek bez braków danych osobno, a prototyp (docelowo Hydrolog H7) łączy ciągi przez braki krótsze niż próg łączenia (brak danych liczy się jak przerwa), odrzuca krótsze niż minimum i podsumowuje lata (niżówkę przypisuje rokowi hydrologicznemu jej początku). Czas trwania obejmuje dni przerw; niedobór sumuje (próg − Q) tylko dni poniżej progu i dla Q jest podany w mln m³ (× 86 400 s). Ciąg na granicy braku danych mógł trwać dłużej (oznaczony „≥”). Różnica z kodem autora z 2024 r.: Hydrolog najpierw łączy ciągi, potem odrzuca krótkie, i łączy przerwy do 3 dni; kod autora najpierw odrzucał ciągi krótsze niż 5 dni, a łączył tylko przerwy do 2 dni (początek − koniec < 4) — dla Kłodzka w 2022 r. przy progu 4 m³/s daje to tu 2 niżówki, u autora 3.`;

function thresholdOptions(variable) {
  return variable === "H"
    ? [["sn", "SNW"], ["p70", "H70"], ["p90", "H90"], ["value", "wartość"]]
    : [["sn", "SNQ"], ["p70", "Q70"], ["p90", "Q90"], ["value", "wartość"]];
}

function useYearSeries(code, dataset, variable, year) {
  const [state, setState] = useState(null);
  useEffect(() => {
    let live = true;
    setState(null);
    if (!year || !dataset) return undefined;
    api.series(code, dataset, { variables: [variable], from: `${year - 1}-11-01`, to: `${year}-10-31` }).then(
      (doc) => live && setState(doc),
      (error) => live && setState({ error }),
    );
    return () => {
      live = false;
    };
  }, [code, dataset, variable, year]);
  return state;
}

function YearChart({ code, data, year }) {
  const doc = useYearSeries(code, data.dataset, data.var, year);
  const spec = useMemo(() => {
    if (!doc || doc.error || !doc.values) return null;
    const threshold = data.threshold.value;
    const values = doc.values[data.var];
    const days = doc.dates.map(dayNumber);
    const inEvent = new Uint8Array(days.length);
    for (const event of data.events.filter((e) => e.year === year || (e.start <= `${year}-10-31` && e.end >= `${year - 1}-11-01`))) {
      const a = dayNumber(event.start);
      const b = dayNumber(event.end);
      days.forEach((d, at) => {
        if (d >= a && d <= b) inEvent[at] = 1;
      });
    }
    const u = unit(data.unit);
    return {
      x: { scale: "date" },
      y: { label: `${data.var} [${u}]${data.var === "Q" ? ", skala log." : ""}`, unit: u, scale: data.var === "Q" ? "log" : "linear", zero: false, digits: digitsOf(data.var) },
      series: [
        { id: "deficit", kind: "band", cls: "s2", label: "niedobór", data: days.map((d, at) => (inEvent[at] && values[at] !== null && values[at] < threshold ? [d, values[at], threshold] : [d, null, null])), readout: false },
        { id: "v", kind: "line", cls: "s1", label: data.var === "Q" ? "przepływ dobowy" : "stan dobowy", data: days.map((d, at) => [d, values[at]]) },
      ],
      marks: [{ kind: "hline", y: threshold, label: `próg ${fmtV(threshold, data.var)}`, cls: "hy-lv-dry" }],
      legend: true,
      readout: { series: "v" },
      fit: { ratio: 0.5, minHeight: 200 },
      title: `Rok hydrologiczny ${year} z niżówkami`,
    };
  }, [doc, data, year]);
  if (!doc) return html`<p class="muted">Wczytuję rok ${year}…</p>`;
  if (doc.error) return html`<p class="ana-error">${doc.error.message}</p>`;
  return html`<${Chart} spec=${spec} />`;
}

function LimitsForm({ opt, setOpt }) {
  const [value, setValue] = useState(opt.value ?? "");
  const [min, setMin] = useState(opt.min);
  const [gap, setGap] = useState(opt.gap);
  return html`<form class="years hy-limits" onSubmit=${(e) => (e.preventDefault(), setOpt({ value: opt.threshold === "value" ? value : opt.value, min, gap }))}>
    ${opt.threshold === "value" && html`<label>Próg <input type="number" step="any" min="0" value=${value} onInput=${(e) => setValue(e.target.value)} required /></label>`}
    <label>min. dni <input type="number" min="1" max="90" value=${min} onInput=${(e) => setMin(+e.target.value)} /></label>
    <label>łącz przerwy krótsze niż <input type="number" min="0" max="30" value=${gap} onInput=${(e) => setGap(+e.target.value)} /> d</label>
    <button type="submit">Przelicz</button>
  </form>`;
}

/** The section „Niżówki”. */
export function LowFlowPeriods({ station }) {
  const code = station.code;
  const [opt, setOpt] = useOptions({ var: undefined, threshold: "sn", value: undefined, min: 5, gap: 4, from: undefined, to: undefined, metric: "days", year: undefined }, code);
  const params = { var: opt.var, threshold: opt.threshold, value: opt.threshold === "value" ? opt.value : undefined, min: opt.min, gap: opt.gap, from: opt.from, to: opt.to };
  const state = useAnalysis("hydro_low_flow_periods", code, opt.threshold === "value" && !opt.value ? { ...params, threshold: "sn" } : params);
  const data = state.data;
  const variables = (station.datasets || [])
    .filter((d) => d.dataset.endsWith("hydro_daily"))
    .flatMap((d) => Object.keys(d.variables))
    .filter((v) => v === "Q" || v === "H");
  const volume = data && data.var === "Q";
  const perYear = useMemo(() => {
    if (!data) return null;
    const metric = opt.metric;
    const pick = { days: (r) => r.days, deficit: (r) => (volume ? r.volume : r.deficit), n: (r) => r.n }[metric];
    const label = { days: "dni niżówki", deficit: volume ? "niedobór [mln m³]" : `niedobór [${unit(data.unit)}·d]`, n: "liczba niżówek" }[metric];
    return {
      x: { label: "rok hydrologiczny", digits: 0 },
      y: { label, digits: metric === "deficit" ? 2 : 0 },
      series: [{ id: "y", kind: "bars", cls: "s2", align: "center", label, data: data.per_year.map((r) => [r.year, pick(r)]) }],
      readout: { x: (x) => `rok ${Math.round(x)}` },
      fit: { ratio: 0.42, minHeight: 170 },
      title: "Niżówki w latach",
    };
  }, [data, opt.metric]);
  const columns = data && [
    { key: "start", label: "od", format: (v, row) => `${row.open_start ? "≤ " : ""}${date(v)}` },
    { key: "end", label: "do", format: (v, row) => `${date(v)}${row.open_end ? " (urwana)" : ""}` },
    { key: "days", label: "dni", format: (v, row) => `${row.open_start || row.open_end ? "≥ " : ""}${fmt(v, 0)}` },
    volume
      ? { key: "volume", label: "niedobór [mln m³]", format: (v) => fmt(v, 3) }
      : { key: "deficit", label: `niedobór [${unit(data.unit)}·d]`, format: (v) => fmt(v, 0) },
    { key: "min", label: `min [${unit(data.unit)}]`, format: (v) => fmtV(v, data.var) },
    { key: "mean", label: "średnio", format: (v) => fmtV(v, data.var) },
    { key: "missing", label: "braki", format: (v) => (v ? `${v} d` : "") },
  ];
  const yearsWithEvents = data ? [...new Set(data.events.map((e) => e.year))].sort((a, b) => b - a) : [];
  const year = data && (yearsWithEvents.includes(opt.year) ? opt.year : data.largest ? data.largest.year : yearsWithEvents[0]);
  const sequences = data && data.computed_by.find((p) => p.command === "stats low-flow-sequences");
  return html`<${Section} info=${INFO} state=${state}>
    ${data && html`
      <${Years} data=${data} onApply=${(from, to) => setOpt({ from, to })} />
      <div class="hy-options">
        ${variables.length > 1 && html`<${Option} label="Zmienna"><${VariableSeg} value=${data.var} variables=${["Q", "H"].filter((v) => variables.includes(v))} onChange=${(v) => setOpt({ var: v, year: undefined })} /></${Option}>`}
        <${Option} label="Próg"><${Seg} value=${opt.threshold} label="Próg" options=${thresholdOptions(data.var)} onChange=${(v) => setOpt({ threshold: v, year: undefined })} /></${Option}>
      </div>
      <${LimitsForm} opt=${opt} setOpt=${setOpt} />
      <${Figures}
        items=${[
          { label: "Próg", value: `${fmtV(data.threshold.value, data.var)} ${unit(data.unit)}`, note: data.threshold.label },
          { label: "Niżówek", value: fmt(data.events.length, 0), note: `${data.years.from}–${data.years.to}` },
          { label: "Najdłuższa", value: data.longest ? `${fmt(data.longest.days, 0)} dni` : "–", note: data.longest ? `${date(data.longest.start)}–${date(data.longest.end)}` : "" },
          { label: "Największy niedobór", value: data.largest ? (volume ? `${fmt(data.largest.volume, 2)} mln m³` : `${fmt(data.largest.deficit, 0)} ${unit(data.unit)}·d`) : "–", note: data.largest ? `${date(data.largest.start)}–${date(data.largest.end)}` : "" },
        ]}
      />
      <${Option} label="Na wykresie"><${Seg} value=${opt.metric} label="Miara" options=${[["days", "dni"], ["deficit", "niedobór"], ["n", "liczba"]]} onChange=${(v) => setOpt({ metric: v })} /></${Option}>
      <${Chart} spec=${perYear} />
      ${year && html`
        <${Option} label="Rok"><${Select} value=${year} label="Rok hydrologiczny" options=${yearsWithEvents.map((y) => [y, String(y)])} onChange=${(v) => setOpt({ year: +v })} /></${Option}>
        <${YearChart} code=${code} data=${data} year=${year} />`}
      <h4 class="hy-sub">Niżówki (od najnowszej)</h4>
      <${Table} columns=${columns} rows=${[...data.events].reverse()} max=${10} />
      <p class="muted hy-caption">Hydrolog dostał ${data.spans} ${data.spans === 1 ? "odcinek" : "odcinków"} bez braków danych${data.missing_days ? `; braków w zakresie: ${data.missing_days} dni` : ""}.</p>
      <${Handoff} code=${code} variable=${data.var} resolution="daily" from=${data.years.from} to=${data.years.to} computed=${sequences} result=${{ threshold: data.threshold.value, n_events: data.events.length, longest_days: data.longest ? data.longest.days : 0 }} />
    `}
  </${Section}>`;
}
