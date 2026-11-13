// „Paski klimatyczne” (Nogat plan M15): Ed Hawkins's warming stripes of the annual mean
// temperature (showyourstripes.info). Hydrolog gives the annual means, the normal of the
// centre period and each year's anomaly (`temperature.means`); the GUI server's prototype
// (`api/prototype/stripes/{code}`, src/obserwator/gui/_stripes.py) adds only the colour
// scale and each year's colour, labelled as the prototype that moves to Hydrolog (M15).
// This module draws the stripes as SVG, without axes as the original or with a year axis
// and a readout, and writes them as PNG, SVG and CSV. The images carry the station, the
// period, the method's credit and the provider's lines and terms drawn in (Nogat DEV-20.5);
// the CSV the columns `attribution` and `terms_notice`.

import { api } from "../../api.js";
import { fmt, html, t, tn, useContext, useEffect, useMemo, useRef, useState } from "../../lib.js";
import { Figures, Notices, ResultLines, Section, Seg, YearRange } from "../common.js";
import { Option, Source, useOptions } from "./util.js";

/** Where the method's credit links to. */
const CREDIT_URL = "https://showyourstripes.info";
/** The method's tag, a name: the link of the credit. */
const CREDIT_TAG = "#ShowYourStripes";
/** A year without an annual mean, as showyourstripes.info draws missing years. */
const GREY = "#a3a3a3";
const FONT = "Arial, Helvetica, sans-serif";

let uid = 0;

/** The credit of the method, on the panel and in every file. */
function credit() {
  return `${t("meteo.stripes.credit")} ${CREDIT_TAG}`;
}

/** The colour of a year: Hawkins's palette, grey without an annual mean. */
function colourOf(data, year) {
  return year.colour === null ? GREY : data.palette[year.colour];
}

/** A signed number: "+1,23", "−0,40". */
function signed(value, digits = 2) {
  if (value === null || value === undefined) return "–";
  const text = fmt(Math.abs(value), digits);
  return value > 0 ? `+${text}` : value < 0 ? `−${text}` : text;
}

/** The readout of a year. */
function readout(year) {
  if (year.colour === null) return tn("meteo.stripes.readout_grey", year.months_missing, { year: year.year });
  return t("meteo.stripes.readout", { year: year.year, mean: fmt(year.tmean_c, 2), anomaly: signed(year.anomaly_c) });
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
      aria-label=${axis ? t("meteo.stripes.aria_keys", { label }) : label}
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
    ${axis && html`<p class="stripes-readout" aria-live="polite">${focus === null ? t("meteo.stripes.readout_hint") : readout(years[focus])}</p>`}
  </div>`;
}

/** The colour scale: 16 colours from −kσ to +kσ around the centre, and grey. */
function Legend({ data }) {
  const s = data.scale;
  const k = fmt(s.k, 1);
  return html`<div class="stripes-legend" role="group" aria-label=${t("meteo.stripes.scale_label")}>
    <div class="stripes-bar">${data.palette.map((colour, at) => html`<span style=${{ background: colour }} title=${`${fmt(s.edges_c[at], 2)} – ${fmt(s.edges_c[at + 1], 2)} °C`}></span>`)}</div>
    <div class="stripes-ticks-html">
      <span>${fmt(s.lo_c, 1)} °C<small>−${k}σ</small></span>
      <span>${fmt(s.centre.normal_c, 1)} °C<small>${t("meteo.stripes.legend_centre", { from: s.centre.first_year, to: s.centre.last_year })}</small></span>
      <span>${fmt(s.hi_c, 1)} °C<small>+${k}σ</small></span>
    </div>
    <p class="me-legend"><span><i class="me-sw stripes-grey"></i>${t("meteo.stripes.no_mean")}</span><span>${t("meteo.stripes.step", { value: fmt(s.step_c, 2) })}</span></p>
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
  const whole = ` (${t("meteo.stripes.whole_record")})`;
  return [
    t("meteo.stripes.scale_text", {
      from: c.first_year,
      to: c.last_year,
      value: fmt(c.normal_c, 2),
      whole: c.fallback ? whole : "",
      k: fmt(s.k, 1),
      sd: fmt(d.sd_c, 2),
      sfrom: d.first_year,
      sto: d.last_year,
      swhole: d.fallback ? whole : "",
      lo: fmt(s.lo_c, 2),
      hi: fmt(s.hi_c, 2),
    }),
    data.grey.length ? t("meteo.stripes.grey_text", { years: data.grey.join(", ") }) : "",
  ].filter(Boolean);
}

/** The station's name, else its code. */
function nameOf(station) {
  return (station.properties && station.properties.name) || station.code;
}

/**
 * The stripes as a standalone SVG document with its title, the scale, the credit and the
 * provider's lines and terms drawn in (DEV-20.5), on white.
 */
export function stripesDocument(data, station, axis) {
  const W = 1200;
  const pad = 32;
  const inner = W - 2 * pad;
  const name = nameOf(station);
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
  text(wrap(t("meteo.stripes.doc_subtitle", { first: data.first_year, last: data.last_year }), 16, inner), 16, "#333333");
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
      const x = pad + (year.year - data.first_year + 0.5) * w;
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
  const legendText = `${fmt(s.lo_c, 1)} °C … ${fmt(s.centre.normal_c, 1)} °C … ${fmt(s.hi_c, 1)} °C (±${fmt(s.k, 1)}σ)`;
  parts.push(`<text x="${(pad + 16 * sw + 10).toFixed(2)}" y="${y + 11}" font-family="${FONT}" font-size="13" fill="#333333">${esc(legendText)}</text>`);
  const greyAt = pad + 16 * sw + 10 + measure(legendText, 13) + 24;
  parts.push(`<rect x="${greyAt.toFixed(2)}" y="${y}" width="${sw.toFixed(2)}" height="12" fill="url(#hatch)"/>`);
  parts.push(`<text x="${(greyAt + sw + 8).toFixed(2)}" y="${y + 11}" font-family="${FONT}" font-size="13" fill="#333333">${esc(t("meteo.stripes.no_mean"))}</text>`);
  y += 22;
  for (const line of scaleText(data)) text(wrap(line, 13, inner), 13, "#333333");
  y += 8;
  text(wrap(`${credit()} · ${CREDIT_URL}`, 14, inner, true), 14, "#1a1a1a", true);
  y += 6;
  for (const line of data.attribution || []) text(wrap(line, 12, inner), 12, "#333333");
  for (const line of data.terms_notice || []) text(wrap(line, 12, inner), 12, "#555555");
  const height = Math.ceil(y + pad - 8);
  const label = esc(t("meteo.stripes.doc_label", { station: name, first: data.first_year, last: data.last_year, credit: credit() }));
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
    return await new Promise((resolve, reject) => canvas.toBlob((blob) => (blob ? resolve(blob) : reject(new Error(t("meteo.stripes.png_failed")))), "image/png"));
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
  const input = (data.analysis && data.analysis.inputs && data.analysis.inputs[0]) || {};
  const method = [
    `${credit()} ${CREDIT_URL}`,
    t("meteo.stripes.csv_station", { name: nameOf(station), code: station.code, dataset: input.dataset || "–", version: input.series_version || "–" }),
    ...scaleText(data),
    t("meteo.stripes.csv_colours"),
  ];
  const rows = data.years;
  const methodCells = spread(method, rows.length);
  const lines = spread(data.attribution || [], rows.length);
  const terms = spread(data.terms_notice || [], rows.length);
  const out = ["year,tmean_C,anomaly_C,colour_index,colour_hex,months_missing,method,attribution,terms_notice"];
  rows.forEach((y, i) => {
    out.push(
      [y.year, y.tmean_c, y.anomaly_c, y.colour, y.colour === null ? "" : data.palette[y.colour], y.months_missing, methodCells[i], lines[i], terms[i]].map(cell).join(","),
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
  const names = { code: station.code, first: data.first_year, last: data.last_year };
  const base = t(axis ? "meteo.stripes.file_axis" : "meteo.stripes.file", names);
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
  const csv = run(() => save(new Blob([stripesCsv(data, station)], { type: "text/csv;charset=utf-8" }), `${t("meteo.stripes.file", names)}.csv`));
  return html`<div class="btn-row files">
    <button type="button" class="btn sm" onClick=${png}><span class="fmt">PNG</span>${base}.png</button>
    <button type="button" class="btn sm" onClick=${svg}><span class="fmt">SVG</span>${base}.svg</button>
    <button type="button" class="btn sm" onClick=${csv}><span class="fmt">CSV</span>${t("meteo.stripes.csv_label")}</button>
    ${error && html`<span class="ana-error" role="alert">${error}</span>`}
  </div>`;
}

// --- the section -------------------------------------------------------------------------

/**
 * The stripes document of a station (`api.stripes`), refetched when the station or an
 * option changes; its lines go to the card like an analysis's. Nothing is asked while
 * `wanted` is false.
 */
function useStripes(code, options, wanted) {
  const chosen = Object.fromEntries(Object.entries(options).filter(([, value]) => value !== undefined && value !== null && value !== ""));
  const key = JSON.stringify(chosen);
  const report = useContext(ResultLines);
  const [state, setState] = useState({ data: null, error: null, loading: true });
  useEffect(() => {
    if (!wanted) return undefined;
    const control = new AbortController();
    setState((old) => ({ data: old.data, error: null, loading: true }));
    api.stripes(code, chosen, { signal: control.signal }).then(
      (data) => setState({ data, error: null, loading: false }),
      (error) => !control.signal.aborted && setState({ data: null, error, loading: false }),
    );
    return () => control.abort();
  }, [code, key, wanted]);
  useEffect(() => {
    if (report && state.data) report(state.data);
  }, [report, state.data]);
  return state;
}

/**
 * The states the section shows: Hydrolog's analysis (its provenance and notices) and the
 * prototype's label; a failure carries the stripes' error on the analysis it came from.
 */
function partsOf(state) {
  const doc = state.data;
  if (!doc) return [state];
  if (doc.status !== "ok") return [{ ...state, data: { ...doc.analysis, status: "failed", error: doc.error } }];
  return [
    { ...state, data: doc.analysis },
    { ...state, data: doc.provenance },
  ];
}

/** The fallback of a period, in words: the asked years lacked annual means. */
function fallbackNote(key, period) {
  return t(key, {
    from: period.asked_first_year,
    to: period.asked_last_year,
    years: period.asked_years,
    span: period.asked_last_year - period.asked_first_year + 1,
    first: period.first_year,
    last: period.last_year,
    count: period.years,
  });
}

/**
 * The stripes of a station with the daily mean temperature, in the card „Temperatura”.
 * Their centre is Hydrolog's normal of a reference period computed on request, so a server
 * without Hydrolog's program (`session.compute.available` false) asks nothing and says so.
 *
 * @param {{station: object, session: object|null}} props `api/stations/{code}`, `api/session`
 */
export function Stripes({ station, session }) {
  const [opt, setOpt] = useOptions({ scale: undefined, centre_first_year: undefined, centre_last_year: undefined, spread_first_year: undefined, spread_last_year: undefined }, station.code);
  const [view, setView] = useState("plain");
  const compute = session ? session.compute.available : null;
  const state = useStripes(station.code, opt, compute === true);
  const doc = state.data;
  const data = doc && doc.status === "ok" ? doc : null;
  const parts = partsOf(state);
  const title = t("meteo.stripes.title");
  const info = t("meteo.stripes.info");
  if (compute === false) {
    return html`<${Section} title=${title} info=${info}><p class="note" data-part="stripes-unavailable">${t("meteo.stripes.no_hydrolog")}</p></${Section}>`;
  }
  if (!data) return html`<${Section} title=${title} info=${info} states=${parts} />`;
  const s = data.scale;
  const c = s.centre;
  const d = s.spread;
  const name = nameOf(station);
  const label = tn("meteo.stripes.aria", data.years.length, { station: name, first: data.first_year, last: data.last_year, from: c.first_year, to: c.last_year });
  const drawn = data.years.filter((y) => y.colour !== null);
  const warm = drawn.reduce((best, y) => (best === null || y.anomaly_c > best.anomaly_c ? y : best), null);
  const cold = drawn.reduce((best, y) => (best === null || y.anomaly_c < best.anomaly_c ? y : best), null);
  const whole = (period) => (period.fallback ? ` (${t("meteo.stripes.whole_record")})` : "");
  const scales = (data.scales || []).map((item) => [
    item.name,
    t("meteo.stripes.scale_option", { version: item.name, from: item.centre[0], to: item.centre[1], k: fmt(item.k, 1) }),
  ]);
  const bounds = (period) => ({ first: Math.min(data.first_year, period.asked_first_year), last: Math.max(data.last_year, period.asked_last_year) });
  const centreBounds = bounds(c);
  const spreadBounds = bounds(d);
  return html`<${Section} title=${title} info=${info} states=${parts}>
    <${Source} station=${station} doc=${data.analysis} variable="Tmean" />
    <${StripesSvg} data=${data} label=${label} axis=${view === "axis"} />
    <p class="stripes-credit">${t("meteo.stripes.credit")} <a href=${CREDIT_URL} target="_blank" rel="noopener noreferrer">${CREDIT_TAG}</a></p>
    <${Option} label=${t("meteo.stripes.view")}>
      <${Seg}
        value=${view}
        label=${t("meteo.stripes.view_label")}
        options=${[
          ["plain", t("meteo.stripes.view_plain")],
          ["axis", t("meteo.stripes.view_axis")],
        ]}
        onChange=${setView}
      />
    </${Option}>
    <${Legend} data=${data} />
    <${Option} label=${t("meteo.stripes.scale")}>
      <${Seg}
        value=${s.variant}
        label=${t("meteo.stripes.scale_label")}
        options=${scales}
        onChange=${(v) => setOpt({ scale: v, centre_first_year: undefined, centre_last_year: undefined, spread_first_year: undefined, spread_last_year: undefined })}
      />
    </${Option}>
    <${YearRange}
      first=${centreBounds.first}
      last=${centreBounds.last}
      from=${c.asked_first_year}
      to=${c.asked_last_year}
      label=${t("meteo.stripes.centre_range")}
      onApply=${(a, b) => setOpt({ centre_first_year: a, centre_last_year: b })}
    />
    <${YearRange}
      first=${spreadBounds.first}
      last=${spreadBounds.last}
      from=${d.asked_first_year}
      to=${d.asked_last_year}
      label=${t("meteo.stripes.spread_range")}
      onApply=${(a, b) => setOpt({ spread_first_year: a, spread_last_year: b })}
    />
    ${c.fallback ? html`<p class="muted me-caption">${fallbackNote("meteo.stripes.centre_fallback", c)}</p>` : null}
    ${d.fallback ? html`<p class="muted me-caption">${fallbackNote("meteo.stripes.spread_fallback", d)}</p>` : null}
    <${Notices} states=${parts} />
    <${Figures}
      items=${[
        {
          label: t("meteo.stripes.centre_figure", { from: c.first_year, to: c.last_year }),
          value: `${fmt(c.normal_c, 2)}\u00a0°C`,
          note: `${t("meteo.stripes.centre_of_scale")}, ${tn("meteo.stripes.years_with_mean", c.years ?? 0)}${whole(c)}`,
        },
        { label: `σ ${d.first_year}–${d.last_year}`, value: `${fmt(d.sd_c, 2)}\u00a0°C`, note: `${tn("meteo.stripes.years_with_mean", d.years)}${whole(d)}` },
        { label: t("meteo.stripes.scale_figure", { k: fmt(s.k, 1) }), value: `${fmt(s.lo_c, 1)} – ${fmt(s.hi_c, 1)}\u00a0°C` },
        ...(warm ? [{ label: t("meteo.stripes.warmest"), value: String(warm.year), note: `${fmt(warm.tmean_c, 2)} °C, ${signed(warm.anomaly_c)} °C` }] : []),
        ...(cold ? [{ label: t("meteo.stripes.coldest"), value: String(cold.year), note: `${fmt(cold.tmean_c, 2)} °C, ${signed(cold.anomaly_c)} °C` }] : []),
      ]}
    />
    ${data.grey.length ? html`<p class="muted me-caption">${t("meteo.stripes.grey", { years: data.grey.join(", ") })}</p>` : null}
    <${Downloads} data=${data} station=${station} axis=${view === "axis"} />
  </${Section}>`;
}
