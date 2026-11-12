// „Susze i okresy bezopadowe” (Nogat plan M6, M8): dry and wet spells with the threshold the
// person chooses, SPI of 1, 3, 6 and 12 months and Kaczorowska's relative precipitation classes.

import { Chart, dayNumber, fmt, html, useMemo, useState } from "../../lib.js";
import { Figures, Section, Seg, Table, YearRange, useAnalysis } from "../common.js";
import { ClassLegend, ClassShares, DatasetSeg, Option, ROMAN, Source, classCls, dateRange, monthText, num, part, useOptions, yearAxis, yearReadout } from "./util.js";

const INFO_SPELLS = `Okres bezopadowy to ciąg kolejnych dni z opadem mniejszym od progu (0,1 mm: dni bez opadu; 1 mm: bez opadu istotnego, jak CDD w ETCCDI), okres opadowy — ciąg dni z opadem co najmniej równym progowi. Dzień bez pomiaru przerywa ciąg; ciąg przy braku danych albo na końcu zapisu ma długość co najmniej taką, jaką pokazuję (oznaczony „≥”). Ciąg należy do roku, w którym się zaczął; statystyki roczne (najdłuższy ciąg, liczba ciągów ≥ 10, 15 i 20 dni) liczę dla lat z pomiarem w każdym dniu, rozkład długości — z ciągów pełnych tych lat. Logika serii jest analogiczna do „stats low-flow-sequences” Hydrologa (plan M6).`;

const INFO_SPI = `SPI (Standardized Precipitation Index; McKee, Doesken i Kleist 1993) dla sum 1, 3, 6 i 12 miesięcy: sumy kończące się w danym miesiącu kalendarzowym z lat okresu odniesienia dopasowuję rozkładem gamma metodą największej wiarygodności w przybliżeniu Thoma (1958), z prawdopodobieństwem sumy zerowej q: H(x) = q + (1 − q)·G(x), SPI = Φ⁻¹(H(x)) (Edwards i McKee 1997; WMO-No. 1090, 2012); wartości ograniczam do ±3,09. Sumy miesięczne tylko z miesięcy bez braków (WMO-No. 1203). Dopasowanie wymaga sum w 80 % lat okresu. Klasy McKee: ≤ −2 ekstremalnie suchy, −1,99…−1,5 bardzo suchy, −1,49…−1 umiarkowanie suchy, −0,99…0,99 normalny, dalej symetrycznie wilgotne. Epizod suszy (McKee i in. 1993): ciąg ujemnych SPI, który osiąga −1 lub mniej; jego intensywność to −ΣSPI.`;

const INFO_KACZ = `Opad względny to suma miesiąca (roku) w % normalnej tego miesiąca (roku) z okresu odniesienia. Klasy Kaczorowskiej (1962, Opady w Polsce w przekroju wieloletnim, Prace Geograficzne IG PAN 33; progi za Gąsiorkiem i Musiał 2011): < 50 % skrajnie suchy, 50–74 % bardzo suchy, 75–89 % suchy, 90–110 % normalny, 111–125 % wilgotny, 126–150 % bardzo wilgotny, > 150 % skrajnie wilgotny (procent zaokrąglony do całości). Te same progi stosuję do miesięcy i lat.`;

const KINDS = [
  ["dry", "bezopadowe"],
  ["wet", "opadowe"],
];

function Spells({ state, opt, setOpt }) {
  const data = state.data;
  const kind = opt.kind;
  const block = data && data[kind];
  const spec = useMemo(() => {
    if (!block) return null;
    return {
      x: yearAxis(block.years),
      y: { label: "najdłuższy ciąg [dni]", unit: "dni" },
      series: [{ id: "longest", kind: "bars", cls: kind === "dry" ? "me-bar-dry" : "bar-pe", label: "najdłuższy ciąg", align: "center", data: block.years.map((r) => [r.year, r.longest]) }],
      marks: [{ kind: "hline", y: block.means.longest, label: `średnio ${fmt(block.means.longest, 1)} dni` }],
      readout: { x: yearReadout, value: (v) => `${fmt(v, 0)} dni` },
      fit: { ratio: 0.45, minHeight: 170 },
      title: "Najdłuższy ciąg w roku",
    };
  }, [data, kind]);
  const classSpec = useMemo(() => {
    if (!block) return null;
    const labels = block.classes.map((c) => (c.to === null ? `≥ ${c.from}` : c.from === c.to ? String(c.from) : `${c.from}–${c.to}`));
    return {
      x: { label: "długość ciągu [dni]", tickList: labels.map((label, at) => ({ value: at + 1, label })), min: 0.5, max: labels.length + 0.5 },
      y: { label: "ciągów na rok", unit: "" },
      series: [{ id: "classes", kind: "bars", cls: kind === "dry" ? "me-bar-dry" : "bar-pe", label: "ciągów na rok", align: "center", data: block.classes.map((c, at) => [at + 1, c.per_year]) }],
      readout: { x: (x) => `${labels[Math.round(x) - 1] || ""} dni` },
      fit: { ratio: 0.4, minHeight: 160 },
      title: "Rozkład długości ciągów",
    };
  }, [data, kind]);
  const options = html`<div class="me-options">
    <${Option} label="Próg"><${Seg} value=${opt.threshold} label="Próg opadu" options=${[["0.1", "0,1 mm"], ["1", "1 mm"]]} onChange=${(v) => setOpt({ threshold: v })} /></${Option}>
    <${Option} label="Ciągi"><${Seg} value=${kind} label="Rodzaj ciągów" options=${KINDS} onChange=${(v) => setOpt({ kind: v })} /></${Option}>
  </div>`;
  if (!data) return html`<${Section} title="Okresy bezopadowe i opadowe" info=${INFO_SPELLS} state=${state}>${options}</${Section}>`;
  const record = block.top[0];
  const sign = (r) => (r.censored ? "≥ " : "");
  const what = kind === "dry" ? `P < ${fmt(data.threshold, 1)} mm` : `P ≥ ${fmt(data.threshold, 1)} mm`;
  return html`<${Section} title="Okresy bezopadowe i opadowe" info=${INFO_SPELLS} state=${state}>
    ${options}
    <${Source} data=${data} />
    <${Figures}
      items=${[
        { label: "Najdłuższy w roku, średnio", value: num(block.means.longest, 1, "dni"), note: `${block.complete_years} lat pełnych, ${what}` },
        { label: "Najdłuższy w zapisie", value: record ? `${sign(record)}${record.length} dni` : "–", note: record ? dateRange(record.start, record.end) : "" },
        { label: "Ciągów ≥ 10 · 15 · 20 dni na rok", value: `${num(block.means.n10, 1)} · ${num(block.means.n15, 1)} · ${num(block.means.n20, 1)}` },
        { label: "Trwa na końcu zapisu", value: block.current ? `${block.current.length} dni` : "nie", note: block.current ? `od ${dateRange(block.current.start)} (stan na ${dateRange(block.current.as_of)})` : "" },
      ]}
    />
    <${Chart} spec=${spec} />
    <${Chart} spec=${classSpec} />
    <h4 class="me-sub">Najdłuższe ciągi</h4>
    <${Table}
      columns=${[
        { key: "length", label: "Dni", format: (v, r) => `${sign(r)}${v}` },
        { key: "start", label: "Okres", format: (v, r) => dateRange(v, r.end) },
      ]}
      rows=${block.top}
    />
    <h4 class="me-sub">Lata</h4>
    <${Table}
      columns=${[
        { key: "year", label: "Rok", format: (v) => String(v) },
        { key: "longest", label: "Najdłuższy", format: (v) => String(v) },
        { key: "longest_start", label: "Okres", format: (v, r) => dateRange(v, r.longest_end) },
        { key: "n10", label: "≥ 10", format: (v) => String(v) },
        { key: "n15", label: "≥ 15", format: (v) => String(v) },
        { key: "n20", label: "≥ 20", format: (v) => String(v) },
        { key: "count", label: "Ciągów", format: (v) => String(v) },
      ]}
      rows=${[...block.years].reverse()}
      max=${10}
    />
  </${Section}>`;
}

const SCALES = [
  ["1", "SPI-1"],
  ["3", "SPI-3"],
  ["6", "SPI-6"],
  ["12", "SPI-12"],
];

/** The first day of a month "YYYY-MM" plus k months, as a day number. */
function monthDay(start, k) {
  const y = +start.slice(0, 4);
  const m = +start.slice(5, 7) - 1 + k;
  const year = y + Math.floor(m / 12);
  const month = ((m % 12) + 12) % 12;
  return dayNumber(`${String(year).padStart(4, "0")}-${String(month + 1).padStart(2, "0")}-01`);
}

function spiClass(v) {
  if (v === null) return null;
  if (v <= -2) return 0;
  if (v <= -1.5) return 1;
  if (v <= -1) return 2;
  if (v < 1) return 3;
  if (v < 1.5) return 4;
  if (v < 2) return 5;
  return 6;
}

function Spi({ state, scale, onScale }) {
  const data = state.data;
  const spec = useMemo(() => {
    if (!data) return null;
    const values = data.spi[scale];
    return {
      x: { scale: "date", label: "miesiąc" },
      y: { label: `SPI-${scale}`, zero: true, min: -3.1, max: 3.1 },
      series: [
        {
          id: "spi",
          kind: "bars",
          label: `SPI-${scale}`,
          width: 28,
          data: values.map((v, k) => ({ x: monthDay(data.start, k), y: v, cls: v === null ? "" : `me-spi${spiClass(v)}` })),
          digits: 2,
        },
      ],
      marks: [
        { kind: "hline", y: -1, label: "−1" },
        { kind: "hline", y: 1, label: "1" },
      ],
      readout: { x: (x) => { const d = new Date(x * 86400000); return `${ROMAN[d.getUTCMonth()]} ${d.getUTCFullYear()}`; } },
      fit: { ratio: 0.45, minHeight: 180 },
      title: `SPI-${scale}`,
    };
  }, [data, scale]);
  const scaleSeg = html`<${Option} label="Skala"><${Seg} value=${scale} label="Skala SPI" options=${SCALES} onChange=${onScale} /></${Option}>`;
  if (!data) return html`<${Section} title="Wskaźnik SPI" info=${INFO_SPI} state=${part(state, "spi")}>${scaleSeg}</${Section}>`;
  const values = data.spi[scale];
  let last = values.length - 1;
  while (last >= 0 && values[last] === null) last -= 1;
  const lastMonth = last >= 0 ? new Date(monthDay(data.start, last) * 86400000) : null;
  const events = data.events[scale];
  return html`<${Section} title="Wskaźnik SPI" info=${INFO_SPI} state=${part(state, "spi")}>
    ${scaleSeg}
    <${Figures}
      items=${[
        { label: "Kalibracja", value: `${data.reference.from}–${data.reference.to}`, note: "rozkład gamma, Thom" },
        { label: "Ostatnia wartość", value: last >= 0 ? fmt(values[last], 2) : "–", note: lastMonth ? `${ROMAN[lastMonth.getUTCMonth()]} ${lastMonth.getUTCFullYear()} · ${data.spi_classes[spiClass(values[last])]}` : "" },
        { label: "Miesięcy suchych (SPI ≤ −1)", value: num((data.frequency[scale][0] || 0) + (data.frequency[scale][1] || 0) + (data.frequency[scale][2] || 0), 1, "%") },
        { label: "Najsilniejszy epizod", value: events.length ? `${monthText(events[0].start)} – ${monthText(events[0].end)}` : "–", note: events.length ? `${events[0].months} mies., min ${fmt(events[0].min, 2)}` : "" },
      ]}
    />
    <${Chart} spec=${spec} />
    <${ClassLegend} names=${data.spi_classes} palette="dw" />
    <${ClassShares} names=${data.spi_classes} shares=${{ [`SPI-${scale}`]: data.frequency[scale] }} palette="dw" label="Udział miesięcy w klasach [%]" />
    <h4 class="me-sub">Epizody suszy (SPI-${scale})</h4>
    ${events.length
      ? html`<${Table}
          columns=${[
            { key: "start", label: "Od", format: (v) => monthText(v) },
            { key: "end", label: "Do", format: (v) => monthText(v) },
            { key: "months", label: "Mies.", format: (v) => String(v) },
            { key: "min", label: "Min SPI", format: (v) => num(v, 2) },
            { key: "magnitude", label: "−ΣSPI", format: (v) => num(v, 1) },
          ]}
          rows=${events}
        />`
      : html`<p class="muted">Brak epizodów z SPI ≤ −1.</p>`}
    <details class="me-details"><summary>Parametry rozkładu gamma (SPI-${scale})</summary>
      <${Table}
        columns=${[
          { key: "month", label: "Miesiąc", format: (v) => ROMAN[v - 1] },
          { key: "alpha", label: "α", format: (v) => num(v, 3) },
          { key: "beta", label: "β [mm]", format: (v) => num(v, 2) },
          { key: "q", label: "q", format: (v) => num(v, 3) },
          { key: "n", label: "n", format: (v) => String(v) },
        ]}
        rows=${data.fits[scale]}
      />
    </details>
  </${Section}>`;
}

function Kaczorowska({ state }) {
  const data = state.data;
  if (!data) return html`<${Section} title="Klasy opadów względnych (Kaczorowska)" info=${INFO_KACZ} state=${part(state, "kaczorowska")} />`;
  const k = data.kaczorowska;
  const rows = [...k.years].reverse();
  return html`<${Section} title="Klasy opadów względnych (Kaczorowska)" info=${INFO_KACZ} state=${part(state, "kaczorowska")}>
    <${Figures}
      items=${[
        { label: `Normalna roczna ${data.reference.from}–${data.reference.to}`, value: num(k.normal.annual, 0, "mm") },
        { label: "Lat normalnych", value: num(k.frequency.years[3], 0, "%") },
        { label: "Lat suchych (wszystkie klasy)", value: num((k.frequency.years[0] || 0) + (k.frequency.years[1] || 0) + (k.frequency.years[2] || 0), 0, "%") },
        { label: "Lat wilgotnych (wszystkie klasy)", value: num((k.frequency.years[4] || 0) + (k.frequency.years[5] || 0) + (k.frequency.years[6] || 0), 0, "%") },
      ]}
    />
    <${ClassShares} names=${k.classes} shares=${{ miesiące: k.frequency.months, lata: k.frequency.years }} palette="dw" />
    <h4 class="me-sub">Opad względny miesięcy i lat [% normalnej]</h4>
    <${KaczTable} rows=${rows} classes=${k.classes} />
  </${Section}>`;
}

function KaczTable({ rows, classes }) {
  const [all, setAll] = useState(false);
  const shown = all ? rows : rows.slice(0, 15);
  return html`<div class="table-wrap"><table class="tbl me-heat">
      <thead><tr><th scope="col">Rok</th>${ROMAN.map((m) => html`<th scope="col">${m}</th>`)}<th scope="col">Rok</th></tr></thead>
      <tbody>${shown.map(
        (r) => html`<tr>
          <th scope="row">${r.year}</th>
          ${r.months_pct.map((v, at) => html`<td class=${classCls("dw", r.months_class[at])} title=${r.months_class[at] === null ? "" : classes[r.months_class[at]]}>${v === null ? "–" : fmt(v, 0)}</td>`)}
          <td class=${`me-year ${classCls("dw", r.class)}`} title=${r.class === null ? "" : classes[r.class]}>${r.pct === null ? "–" : fmt(r.pct, 0)}</td>
        </tr>`,
      )}</tbody>
    </table>
    ${rows.length > 15 && !all ? html`<button type="button" class="link" onClick=${() => setAll(true)}>Pokaż wszystkie (${rows.length})</button>` : null}
    <${ClassLegend} names=${classes} palette="dw" />
  </div>`;
}

/** The card „Susze i okresy bezopadowe”. */
export function Susze({ station }) {
  const code = station.code;
  const [opt, setOpt] = useOptions({ threshold: "0.1", kind: "dry", scale: "3", dataset: undefined, ref_from: undefined, ref_to: undefined }, code);
  const spells = useAnalysis("meteo-spells", code, { threshold: opt.threshold, dataset: opt.dataset });
  const drought = useAnalysis("meteo-drought", code, { ref_from: opt.ref_from, ref_to: opt.ref_to, dataset: opt.dataset });
  const ref = drought.data && drought.data.reference;
  return html`<div class="me-card">
    <div class="me-toolbar">
      <${DatasetSeg} data=${spells.data} value=${opt.dataset} onChange=${(v) => setOpt({ dataset: v })} />
      ${ref && html`<${YearRange} first=${ref.min} last=${ref.max} from=${ref.from} to=${ref.to} label="Okres odniesienia" onApply=${(a, b) => setOpt({ ref_from: a, ref_to: b })} />`}
    </div>
    <${Spells} state=${spells} opt=${opt} setOpt=${setOpt} />
    <${Spi} state=${drought} scale=${opt.scale} onScale=${(v) => setOpt({ scale: v })} />
    <${Kaczorowska} state=${drought} />
  </div>`;
}
