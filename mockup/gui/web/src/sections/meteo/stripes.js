// „Paski klimatyczne” (M15): Ed Hawkins's warming stripes of the annual mean temperature
// (showyourstripes.info). The server computes each year's colour (server/analyses/meteo.py
// `stripes`); this module draws them as SVG, without axes as the original or with a year axis
// and a readout, and writes them as PNG, SVG and CSV. The images carry the station, the
// period, the method's credit and the provider's lines and terms drawn in (Nogat DEV-20.5);
// the CSV the columns `attribution` and `terms_notice`.

import { fmt, html, useEffect, useMemo, useRef, useState } from "../../lib.js";
import { Figures, Section, Seg, YearRange, useAnalysis } from "../common.js";
import { Notes, Option, Source, useOptions } from "./util.js";

/** The credit of the method, on the panel and in every file. */
export const CREDIT = "Metoda: Ed Hawkins (University of Reading), #ShowYourStripes";
const CREDIT_URL = "https://showyourstripes.info";
/** A year without an annual mean, as showyourstripes.info draws missing years. */
const GREY = "#a3a3a3";
const FONT = "Arial, Helvetica, sans-serif";

const INFO = `Paski klimatyczne (warming stripes) Eda Hawkinsa (University of Reading, 2018; showyourstripes.info, climate-lab-book.ac.uk/2018/warming-stripes): każdy pasek to jeden rok kalendarzowy, a jego kolor to średnia roczna temperatura powietrza (Tśr) stacji. Średnią roczną liczę z dwunastu średnich miesięcznych, gdy w każdym miesiącu brakuje mniej niż 11 dni i mniej niż 5 kolejnych (WMO-No. 1203, p. 4.4.1 a); rok bez takiej średniej jest szary i zakreskowany. Skala jak w FAQ showyourstripes.info („How have these graphics been made?”, stan z 2025 r.): granicą między niebieskim a czerwonym jest średnia z lat 1961–2010, a skala kolorów obejmuje ±3,0 odchylenia standardowego średnich rocznych z lat 1901–2000. Wersja tej strony z czerwca 2019 r. podawała 1971–2000 i ±2,6σ; można ją wybrać. 16 kolorów dzieli przedział na równe części, lata poza nim mają kolor skrajny; odchylenie standardowe liczę z próby (n − 1), bo FAQ go nie określa. Okres, w którym średnią roczną ma mniej niż 80 % lat (WMO-No. 1203, p. 4.4.2), zastępuje cały zapis stacji. Oba okresy można zmienić; zalecany minimalny okres to 30 lat. Kolory to 8 najciemniejszych barw 9-klasowych palet Blues i Reds z ColorBrewer, jak u Hawkinsa. This product includes color specifications and designs developed by Cynthia Brewer (http://colorbrewer.org/). Palety ColorBrewer: © 2002 Cynthia Brewer, Mark Harrower i The Pennsylvania State University, licencja Apache 2.0. Grafiki showyourstripes.info są udostępnione na licencji CC BY 4.0 z obowiązkiem podania autora, prof. Eda Hawkinsa (University of Reading), i odnośnika do showyourstripes.info. Te paski rysuję od nowa z danych stacji jego metodą, więc panel i każdy plik podają „${CREDIT}” z odnośnikiem ${CREDIT_URL}. PNG i SVG mają w obrazie nazwę stacji, okres, tę linię oraz linie dostawcy danych i warunki (DEV-20.5). CSV ma lata, średnie, anomalie od środka skali, kolory oraz kolumny attribution i terms_notice.`;

const SCALES = [
  ["2025", "FAQ 2025: 1961–2010, ±3,0σ"],
  ["2019", "FAQ 2019: 1971–2000, ±2,6σ"],
];

let uid = 0;

/** The colour of a year: Hawkins's palette, grey without an annual mean. */
function colourOf(data, year) {
  return year.colour === null ? GREY : data.palette[year.colour];
}

/** „1 rok”, „3 lata”, „5 lat”. */
function yearsText(n) {
  if (n === 1) return "1 rok";
  return [2, 3, 4].includes(n % 10) && ![12, 13, 14].includes(n % 100) ? `${n} lata` : `${n} lat`;
}

/** A signed number: "+1,23", "−0,40". */
function signed(value, digits = 2) {
  if (value === null || value === undefined) return "–";
  const text = fmt(Math.abs(value), digits);
  return value > 0 ? `+${text}` : value < 0 ? `−${text}` : text;
}

/** The readout of a year. */
function readout(year) {
  if (year.colour === null) {
    return `${year.year}: brak średniej rocznej (${year.missing_months} ${year.missing_months === 1 ? "miesiąc" : "mies."} z 11 lub więcej brakami dni albo 5 kolejnymi)`;
  }
  return `${year.year}: średnia ${fmt(year.mean, 2)} °C, anomalia ${signed(year.anomaly)} °C`;
}

/** The years between labels of a year axis: at least `gap` pixels apart. */
function tickStep(count, width, gap = 52) {
  for (const step of [1, 2, 5, 10, 20, 25, 50, 100]) if ((width / count) * step >= gap) return step;
  return 200;
}

/** The width of a container, again when it changes. */
function useWidth(ref) {
  const [width, setWidth] = useState(0);
  useEffect(() => {
    const element = ref.current;
    if (!element) return undefined;
    const measure = () => setWidth(Math.round(element.getBoundingClientRect().width));
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  return width;
}

/**
 * The stripes as SVG at the container's width: `axis` adds the year axis, the readout and
 * a cursor by pointer and by keys (arrows, Shift or Page for ten years, Home, End, Esc).
 */
function StripesSvg({ data, label, axis }) {
  const host = useRef(null);
  const width = useWidth(host);
  const [focus, setFocus] = useState(null);
  const ids = useMemo(() => `stripes-hatch-${++uid}`, []);
  useEffect(() => setFocus(null), [data, axis]);
  const years = data.years;
  const n = years.length;
  const height = Math.max(90, Math.min(220, Math.round(width * 0.22)));
  const below = axis ? 26 : 0;
  const w = width / n;
  const at = (x) => Math.min(n - 1, Math.max(0, Math.floor(x / w)));
  const move = (index) => setFocus(Math.min(n - 1, Math.max(0, index)));
  const onKey = (event) => {
    const step = event.shiftKey || event.key.startsWith("Page") ? 10 : 1;
    const current = focus === null ? n - 1 : focus;
    const keys = {
      ArrowLeft: () => move(current - step),
      ArrowDown: () => move(current - step),
      PageDown: () => move(current - step),
      ArrowRight: () => move(current + step),
      ArrowUp: () => move(current + step),
      PageUp: () => move(current + step),
      Home: () => move(0),
      End: () => move(n - 1),
      Escape: () => setFocus(null),
    };
    if (!keys[event.key]) return;
    event.preventDefault();
    keys[event.key]();
  };
  const step = tickStep(n, width);
  const ticks = axis ? years.filter((y) => y.year % step === 0) : [];
  const grey = years.map((y, i) => [y, i]).filter(([y]) => y.colour === null);
  return html`<div class="stripes-host" ref=${host}>
    ${width > 0 &&
    html`<svg
      class=${axis ? "stripes stripes-axis" : "stripes"}
      width=${width}
      height=${height + below}
      viewBox=${`0 0 ${width} ${height + below}`}
      role="img"
      aria-label=${axis ? `${label}; strzałki wybierają rok` : label}
      tabindex=${axis ? 0 : null}
      onKeyDown=${axis ? onKey : null}
      onPointerMove=${axis ? (e) => setFocus(at(e.clientX - e.currentTarget.getBoundingClientRect().left)) : null}
      onPointerLeave=${axis ? () => setFocus(null) : null}
    >
      <defs>
        <pattern id=${ids} patternUnits="userSpaceOnUse" width="6" height="6" patternTransform="rotate(45)">
          <rect width="6" height="6" fill=${GREY} />
          <line x1="0" y1="0" x2="0" y2="6" stroke="#ffffff" stroke-width="2.5" stroke-opacity="0.7" />
        </pattern>
      </defs>
      ${years.map((y, i) => html`<rect x=${i * w} y="0" width=${i === n - 1 ? w : w + 0.6} height=${height} fill=${colourOf(data, y)} />`)}
      ${grey.map(([, i]) => html`<rect x=${i * w} y="0" width=${w} height=${height} fill=${`url(#${ids})`} />`)}
      ${axis &&
      html`<g class="stripes-ticks">
        <line class="stripes-base" x1="0" x2=${width} y1=${height + 0.5} y2=${height + 0.5} />
        ${ticks.map((y) => {
          const x = (y.year - years[0].year + 0.5) * w;
          const anchor = x < 20 ? "start" : x > width - 20 ? "end" : "middle";
          return html`<g><line x1=${x} x2=${x} y1=${height} y2=${height + 5} /><text x=${x} y=${height + 18} text-anchor=${anchor}>${y.year}</text></g>`;
        })}
      </g>`}
      ${axis && focus !== null && html`<rect class="stripes-focus" x=${focus * w} y="0.75" width=${Math.max(w, 2)} height=${height - 1.5} />`}
    </svg>`}
    ${axis && html`<p class="stripes-readout" aria-live="polite">${focus === null ? "Wskaż rok kursorem albo strzałkami (po wybraniu wykresu klawiszem Tab)." : readout(years[focus])}</p>`}
  </div>`;
}

/** The colour scale: 16 colours from −kσ to +kσ around the centre, and grey. */
function Legend({ data }) {
  const s = data.scale;
  return html`<div class="stripes-legend" role="group" aria-label="Skala kolorów">
    <div class="stripes-bar">${data.palette.map((colour, at) => html`<span style=${{ background: colour }} title=${`${fmt(s.edges[at], 2)} – ${fmt(s.edges[at + 1], 2)} °C`}></span>`)}</div>
    <div class="stripes-ticks-html">
      <span>${fmt(s.lo, 1)} °C<small>−${fmt(s.k, 1)}σ</small></span>
      <span>${fmt(s.centre.value, 1)} °C<small>średnia ${s.centre.from}–${s.centre.to}</small></span>
      <span>${fmt(s.hi, 1)} °C<small>+${fmt(s.k, 1)}σ</small></span>
    </div>
    <p class="me-legend"><span><i class="me-sw stripes-grey"></i>brak średniej rocznej</span><span>1 kolor = ${fmt((2 * s.k * s.spread.sd) / 16, 2)} °C</span></p>
  </div>`;
}

// --- files -------------------------------------------------------------------------------

/** XML-escaped text. */
function esc(text) {
  return String(text).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&apos;" })[c]);
}

let measurer = null;

/** The width of a text in pixels at a font size. */
function measure(text, size, bold = false) {
  measurer = measurer || document.createElement("canvas").getContext("2d");
  measurer.font = `${bold ? "bold " : ""}${size}px ${FONT}`;
  return measurer.measureText(text).width;
}

/** Lines of `text` no wider than `width` pixels in the given font size. */
function wrap(text, size, width, bold = false) {
  const out = [];
  let line = "";
  for (const word of String(text).split(" ")) {
    const next = line ? `${line} ${word}` : word;
    if (line && measure(next, size, bold) > width) {
      out.push(line);
      line = word;
    } else {
      line = next;
    }
  }
  if (line) out.push(line);
  return out;
}

/** The scale in words, for the image and the CSV. */
function scaleText(data) {
  const s = data.scale;
  const c = s.centre;
  const d = s.spread;
  return [
    `Środek skali: średnia ${c.from}–${c.to} = ${fmt(c.value, 2)} °C${c.fallback ? " (cały zapis stacji)" : ""}; skala ±${fmt(s.k, 1)}σ, σ = ${fmt(d.sd, 2)} °C ze średnich rocznych ${d.from}–${d.to}${d.fallback ? " (cały zapis stacji)" : ""}: od ${fmt(s.lo, 2)} °C do ${fmt(s.hi, 2)} °C w 16 kolorach.`,
    data.grey.length ? `Lata szare (brak średniej rocznej wg WMO-No. 1203): ${data.grey.join(", ")}.` : "",
  ].filter(Boolean);
}

/**
 * The stripes as a standalone SVG document with its title, the scale, the credit and the
 * provider's lines and terms drawn in (DEV-20.5), on white.
 */
export function stripesDocument(data, station, axis) {
  const W = 1200;
  const pad = 32;
  const inner = W - 2 * pad;
  const name = station.properties.name || station.code;
  const parts = [];
  let y = pad;
  const text = (lines, size, colour, bold = false, gap = 1.35) => {
    for (const line of lines) {
      y += size;
      parts.push(`<text x="${pad}" y="${y}" font-family="${FONT}" font-size="${size}"${bold ? ' font-weight="bold"' : ""} fill="${colour}">${esc(line)}</text>`);
      y += size * (gap - 1);
    }
  };
  text(wrap(`${name} (${station.code})`, 24, inner, true), 24, "#1a1a1a", true);
  y += 4;
  text(wrap(`Paski klimatyczne ${data.first}–${data.last} · średnia roczna temperatura powietrza (Tśr)`, 16, inner), 16, "#333333");
  y += 12;
  const n = data.years.length;
  const w = inner / n;
  const H = 300;
  const top = y;
  parts.push(
    `<defs><pattern id="hatch" patternUnits="userSpaceOnUse" width="6" height="6" patternTransform="rotate(45)"><rect width="6" height="6" fill="${GREY}"/><line x1="0" y1="0" x2="0" y2="6" stroke="#ffffff" stroke-width="2.5" stroke-opacity="0.7"/></pattern></defs>`,
  );
  data.years.forEach((year, i) => {
    const width = i === n - 1 ? w : w + 0.6;
    parts.push(`<rect x="${(pad + i * w).toFixed(2)}" y="${top}" width="${width.toFixed(2)}" height="${H}" fill="${colourOf(data, year)}"/>`);
    if (year.colour === null) parts.push(`<rect x="${(pad + i * w).toFixed(2)}" y="${top}" width="${w.toFixed(2)}" height="${H}" fill="url(#hatch)"/>`);
  });
  y = top + H;
  if (axis) {
    const step = tickStep(n, inner);
    parts.push(`<line x1="${pad}" x2="${pad + inner}" y1="${y + 0.5}" y2="${y + 0.5}" stroke="#555555"/>`);
    for (const year of data.years.filter((item) => item.year % step === 0)) {
      const x = pad + (year.year - data.first + 0.5) * w;
      parts.push(`<line x1="${x.toFixed(2)}" x2="${x.toFixed(2)}" y1="${y}" y2="${y + 6}" stroke="#555555"/>`);
      parts.push(`<text x="${x.toFixed(2)}" y="${y + 21}" text-anchor="middle" font-family="${FONT}" font-size="13" fill="#333333">${year.year}</text>`);
    }
    y += 26;
  }
  y += 14;
  // the colour scale
  const sw = Math.min(28, inner / 2 / 16);
  data.palette.forEach((colour, at) => parts.push(`<rect x="${(pad + at * sw).toFixed(2)}" y="${y}" width="${(sw + 0.4).toFixed(2)}" height="12" fill="${colour}"/>`));
  const s = data.scale;
  const legendText = `${fmt(s.lo, 1)} °C … ${fmt(s.centre.value, 1)} °C … ${fmt(s.hi, 1)} °C (±${fmt(s.k, 1)}σ)`;
  parts.push(`<text x="${(pad + 16 * sw + 10).toFixed(2)}" y="${y + 11}" font-family="${FONT}" font-size="13" fill="#333333">${esc(legendText)}</text>`);
  const greyAt = pad + 16 * sw + 10 + measure(legendText, 13) + 24;
  parts.push(`<rect x="${greyAt.toFixed(2)}" y="${y}" width="${sw.toFixed(2)}" height="12" fill="url(#hatch)"/>`);
  parts.push(`<text x="${(greyAt + sw + 8).toFixed(2)}" y="${y + 11}" font-family="${FONT}" font-size="13" fill="#333333">brak średniej rocznej</text>`);
  y += 22;
  for (const line of scaleText(data)) text(wrap(line, 13, inner), 13, "#333333");
  y += 8;
  text(wrap(`${CREDIT} · ${CREDIT_URL}`, 14, inner, true), 14, "#1a1a1a", true);
  y += 6;
  for (const line of data.attribution || []) text(wrap(line, 12, inner), 12, "#333333");
  for (const line of data.terms_notice || []) text(wrap(line, 12, inner), 12, "#555555");
  const height = Math.ceil(y + pad - 8);
  const label = esc(`${name}: paski klimatyczne ${data.first}–${data.last}. ${CREDIT}`);
  const body = `<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${height}" viewBox="0 0 ${W} ${height}" role="img" aria-label="${label}"><title>${label}</title><rect width="${W}" height="${height}" fill="#ffffff"/>${parts.join("")}</svg>`;
  return { text: `<?xml version="1.0" encoding="UTF-8"?>\n${body}\n`, svg: body, width: W, height };
}

/** The SVG document drawn on a canvas, twice its size, as PNG. */
async function pngOf(doc) {
  const url = URL.createObjectURL(new Blob([doc.svg], { type: "image/svg+xml" }));
  try {
    const image = new Image();
    image.src = url;
    await image.decode();
    const canvas = document.createElement("canvas");
    canvas.width = doc.width * 2;
    canvas.height = doc.height * 2;
    canvas.getContext("2d").drawImage(image, 0, 0, canvas.width, canvas.height);
    return await new Promise((resolve, reject) => canvas.toBlob((blob) => (blob ? resolve(blob) : reject(new Error("PNG: brak obrazu"))), "image/png"));
  } finally {
    URL.revokeObjectURL(url);
  }
}

/** One line per cell from the first row down, the rest joined into the last (DEV-20.5). */
function spread(items, rows) {
  if (rows <= 0) return [];
  const cells = items.slice(0, rows).concat(Array(Math.max(0, rows - items.length)).fill(""));
  if (items.length > rows) cells[rows - 1] = items.slice(rows - 1).join("\n");
  return cells;
}

function cell(value) {
  const text = value === null || value === undefined ? "" : String(value);
  return /[",\r\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

/** The years as CSV: UTF-8, comma, dot decimal, CRLF; the method and the provider's lines in columns. */
export function stripesCsv(data, station) {
  const name = station.properties.name || station.code;
  const method = [`${CREDIT} ${CREDIT_URL}`, `Stacja: ${name} (${station.code}); zbiór ${data.dataset}, szereg ${data.series_version}`, ...scaleText(data), "colour_index: 0 = najciemniejszy niebieski, 15 = najciemniejszy czerwony; pusty = brak średniej rocznej"];
  const rows = data.years;
  const methodCells = spread(method, rows.length);
  const lines = spread(data.attribution || [], rows.length);
  const terms = spread(data.terms_notice || [], rows.length);
  const out = ["year,tmean_C,anomaly_C,colour_index,colour_hex,missing_months,method,attribution,terms_notice"];
  rows.forEach((y, i) => {
    out.push(
      [y.year, y.mean, y.anomaly, y.colour, y.colour === null ? "" : data.palette[y.colour], y.missing_months, methodCells[i], lines[i], terms[i]].map(cell).join(","),
    );
  });
  return `${out.join("\r\n")}\r\n`;
}

function save(blob, name) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  link.hidden = true;
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 0);
}

function Downloads({ data, station, axis }) {
  const [error, setError] = useState(null);
  const base = `paski-klimatyczne-${station.code}-${data.first}-${data.last}${axis ? "-os" : ""}`;
  const run = (fn) => async () => {
    setError(null);
    try {
      await fn();
    } catch (e) {
      setError(String(e.message || e));
    }
  };
  const png = run(async () => save(await pngOf(stripesDocument(data, station, axis)), `${base}.png`));
  const svg = run(() => save(new Blob([stripesDocument(data, station, axis).text], { type: "image/svg+xml" }), `${base}.svg`));
  const csv = run(() => save(new Blob([stripesCsv(data, station)], { type: "text/csv;charset=utf-8" }), `paski-klimatyczne-${station.code}-${data.first}-${data.last}.csv`));
  return html`<div class="btn-row files">
    <button type="button" class="btn sm" onClick=${png}><span class="fmt">PNG</span>${base}.png</button>
    <button type="button" class="btn sm" onClick=${svg}><span class="fmt">SVG</span>${base}.svg</button>
    <button type="button" class="btn sm" onClick=${csv}><span class="fmt">CSV</span>lata, średnie, anomalie</button>
    ${error && html`<span class="ana-error" role="alert">${error}</span>`}
  </div>`;
}

// --- the section -------------------------------------------------------------------------

/**
 * The stripes of a station with the daily mean temperature, in the card „Temperatura”.
 *
 * @param {{station: object, dataset?: string}} props
 */
export function Stripes({ station, dataset }) {
  const [opt, setOpt] = useOptions({ scale: "2025", centre_from: undefined, centre_to: undefined, spread_from: undefined, spread_to: undefined }, station.code);
  const [view, setView] = useState("plain");
  const state = useAnalysis("meteo-stripes", station.code, { dataset, ...opt });
  const data = state.data;
  if (!data) return html`<${Section} title="Paski klimatyczne" info=${INFO} state=${state} />`;
  const s = data.scale;
  const rec = data.record;
  const name = station.properties.name || station.code;
  const label = `Paski klimatyczne stacji ${name}, ${data.first}–${data.last}: ${data.years.length} lat, od niebieskiego (chłodniej) do czerwonego (cieplej) wobec średniej ${s.centre.from}–${s.centre.to}`;
  const warm = data.warmest[0];
  const cold = data.coldest[0];
  return html`<${Section} title="Paski klimatyczne" info=${INFO} state=${state}>
    <${Source} data=${data} />
    <${StripesSvg} data=${data} label=${label} axis=${view === "axis"} />
    <p class="stripes-credit">${CREDIT.replace("#ShowYourStripes", "")}<a href=${CREDIT_URL} target="_blank" rel="noopener noreferrer">#ShowYourStripes</a></p>
    <${Option} label="Widok"><${Seg} value=${view} label="Widok pasków" options=${[["plain", "paski"], ["axis", "z osią lat i odczytem"]]} onChange=${setView} /></${Option}>
    <${Legend} data=${data} />
    <${Option} label="Skala"><${Seg} value=${opt.scale} label="Skala kolorów" options=${SCALES} onChange=${(v) => setOpt({ scale: v, centre_from: undefined, centre_to: undefined, spread_from: undefined, spread_to: undefined })} /></${Option}>
    <${YearRange} first=${Math.min(rec.min, s.centre.from)} last=${Math.max(rec.max, s.centre.to)} from=${s.centre.from} to=${s.centre.to} label="Środek skali (okres odniesienia)" onApply=${(a, b) => setOpt({ centre_from: a, centre_to: b })} />
    <${YearRange} first=${Math.min(rec.min, s.spread.from)} last=${Math.max(rec.max, s.spread.to)} from=${s.spread.from} to=${s.spread.to} label="Rozrzut σ z lat" onApply=${(a, b) => setOpt({ spread_from: a, spread_to: b })} />
    <${Notes} items=${data.notes} />
    <${Figures}
      items=${[
        { label: `Średnia ${s.centre.from}–${s.centre.to}`, value: `${fmt(s.centre.value, 2)}\u00a0°C`, note: `środek skali, ${yearsText(s.centre.years)} ze średnią${s.centre.fallback ? " (cały zapis)" : ""}` },
        { label: `σ ${s.spread.from}–${s.spread.to}`, value: `${fmt(s.spread.sd, 2)}\u00a0°C`, note: `${yearsText(s.spread.years)} ze średnią${s.spread.fallback ? " (cały zapis)" : ""}` },
        { label: `Skala ±${fmt(s.k, 1)}σ`, value: `${fmt(s.lo, 1)} – ${fmt(s.hi, 1)}\u00a0°C` },
        ...(warm ? [{ label: "Najcieplejszy rok", value: String(warm.year), note: `${fmt(warm.mean, 2)} °C, ${signed(warm.anomaly)} °C` }] : []),
        ...(cold ? [{ label: "Najchłodniejszy rok", value: String(cold.year), note: `${fmt(cold.mean, 2)} °C, ${signed(cold.anomaly)} °C` }] : []),
      ]}
    />
    ${data.grey.length ? html`<p class="muted me-caption">Lata szare: ${data.grey.join(", ")}.</p>` : null}
    <${Downloads} data=${data} station=${station} axis=${view === "axis"} />
  </${Section}>`;
}
