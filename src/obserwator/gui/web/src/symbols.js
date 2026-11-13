// The station symbols of hydro.imgw.pl, IMGW-PIB's hydrological service (version 2.1.13.1
// of 2026-11-12, read on 2026-11-13), so that a person who knows IMGW-PIB's map reads this
// one at once (plan D9). Taken from its icon service and its CSS:
// - a hydrological station is a downward triangle with rounded corners, 16 px tall (its
//   viewBox 39 × 34); a meteorological one a circle 16 px across (viewBox 38 × 38); both
//   with a grey outline, #777, 2 units wide (getStrokeStyle()); the selected station is the
//   same symbol at 32 px (its "big" icon);
// - the fill is the station's class: the water state of a hydrological station, the
//   precipitation of a meteorological one, in its colours --<class>-status-color (here
//   --imgw-* in css/map.css, each with its source);
// - a hydrological state „…Outdated” is the same colour with a hollow centre: the state of
//   the last 26 hours instead of the last 2 (PRODUCTS.WATER_STATE.lastStatusInfo);
// - the words are its own (STATUSES.<class>Short of its Polish catalog), entries
//   `gui.stations.state.*` and `gui.stations.precip.*` of the message catalog in both
//   languages, looked up when a class is asked for.
// The outlines are drawn here, the same on the map's canvas and in SVG; no path is copied.
// Where hydro.imgw.pl has no counterpart the shapes stay and this GUI adds its own marks: a
// hollow centre for a station that is only in the catalog and a dashed outline for ČHMÚ.

import { fmt, html, t } from "./lib.js";

/** The water states of a hydrological station, in hydro.imgw.pl's order; `text` is the catalog key of its words. */
export const HYDRO_STATES = Object.freeze([
  { key: "alarm", text: "stations.state.alarm", color: "--imgw-alarm", ageing: true },
  { key: "warning", text: "stations.state.warning", color: "--imgw-warning", ageing: true },
  { key: "high", text: "stations.state.high", color: "--imgw-high", ageing: true },
  { key: "medium", text: "stations.state.medium", color: "--imgw-medium", ageing: true },
  { key: "low", text: "stations.state.low", color: "--imgw-low", ageing: true },
  { key: "below", text: "stations.state.below", color: "--imgw-below", ageing: true },
  { key: "no-water-state-data", text: "stations.state.no_data", color: "--imgw-no-data", ageing: false },
  { key: "unknown", text: "stations.state.unknown", color: "--imgw-unknown", ageing: false },
]);
const HYDRO_BY_KEY = new Map(HYDRO_STATES.map((state) => [state.key, state]));
/** The suffix of a state IMGW-PIB's map draws hollow: measured in the last 26 hours, not 2. */
const OUTDATED = "Outdated";

/**
 * The water state of IMGW-PIB's map as hydro.imgw.pl draws it.
 *
 * @param {string|null} raw e.g. "medium", "lowOutdated", "no-char-states"; none is
 *   „Brak danych stanu wody”, as on hydro.imgw.pl
 * @returns {{key: string, text: string, label: string, color: string, ageing: boolean,
 *   outdated: boolean}} `label` in the page's language
 */
export function hydroState(raw) {
  let key = raw ? String(raw) : "no-water-state-data";
  const outdated = key.endsWith(OUTDATED);
  if (outdated) key = key.slice(0, -OUTDATED.length);
  // hydro.imgw.pl groups "unknown" and "no-char-states" under one colour and one entry
  const state = HYDRO_BY_KEY.get(key === "no-char-states" ? "unknown" : key) || HYDRO_BY_KEY.get("unknown");
  return { ...state, label: t(state.text), outdated: outdated && state.ageing };
}

/**
 * The precipitation classes of a meteorological station. hydro.imgw.pl classes by the last
 * 6 hours (STATUSES.*Description): no precipitation, some, or at least heavy rain on
 * Chomicz's scale (number 1, category A0 or higher: a total P ≥ √t mm in t minutes).
 * Obserwator's `current meteo` gives only the latest 10-minute total (`opad_10min`), so
 * the classes here apply the same rule to it: heavy rain is P ≥ √10 ≈ 3.2 mm in 10
 * minutes. hydro.imgw.pl's green ring („Brak opadu godzinowego”) has no counterpart.
 */
export const HEAVY_10_MIN = Math.sqrt(10);
export const METEO_CLASSES = Object.freeze([
  { key: "high-precip", text: "stations.precip.heavy", color: "--imgw-high-precip" },
  { key: "precip", text: "stations.precip.some", color: "--imgw-precip" },
  { key: "no-precip", text: "stations.precip.none", color: "--imgw-no-precip" },
  { key: "no-precip-data", text: "stations.precip.no_data", color: "--imgw-no-data" },
]);
const METEO_BY_KEY = new Map(METEO_CLASSES.map((entry) => [entry.key, entry]));

/** What a precipitation class rests on, in the page's language; nothing without data. */
function precipitationNote(key) {
  if (key === "high-precip") return t("stations.precip.heavy_note", { mm: fmt(HEAVY_10_MIN, 1) });
  return key === "no-precip-data" ? null : t("stations.precip.last_10_min");
}

/**
 * The class of a meteorological station by its latest 10-minute precipitation.
 *
 * @param {number|null} total [mm]
 * @returns {{key: string, text: string, label: string, color: string, note: string|null}}
 *   `label` and `note` in the page's language
 */
export function meteoClass(total) {
  let key = "no-precip-data";
  if (total !== null && total !== undefined && Number.isFinite(total)) {
    key = total >= HEAVY_10_MIN ? "high-precip" : total > 0 ? "precip" : "no-precip";
  }
  const entry = METEO_BY_KEY.get(key);
  return { ...entry, label: t(entry.text), note: precipitationNote(key) };
}

/** The fill of a station in the view „Stacje”: hydro.imgw.pl's icons of a station kind in its own legend (a station in the middle zone, a station without precipitation). */
export const KIND_COLORS = Object.freeze({ hydro: "--imgw-medium", meteo: "--imgw-no-precip" });

// --- the outlines -----------------------------------------------------------------------

/** The box of each shape [units] and the height it takes on the map [px]. */
export const SHAPES = Object.freeze({
  hydro: { width: 39, height: 34 },
  meteo: { width: 38, height: 38 },
});
export const SYMBOL_PX = 16;

/** A polygon with its corners rounded by quadratic curves of `radius` units. */
function roundedPolygon(points, radius) {
  const n = points.length;
  const toward = (from, to, length) => {
    const dx = to[0] - from[0];
    const dy = to[1] - from[1];
    const scale = length / Math.hypot(dx, dy);
    return [from[0] + dx * scale, from[1] + dy * scale];
  };
  const parts = [];
  for (let i = 0; i < n; i += 1) {
    const corner = points[i];
    const before = toward(corner, points[(i + n - 1) % n], radius);
    const after = toward(corner, points[(i + 1) % n], radius);
    parts.push(`${i === 0 ? "M" : "L"}${before[0].toFixed(2)} ${before[1].toFixed(2)}`);
    parts.push(`Q${corner[0]} ${corner[1]} ${after[0].toFixed(2)} ${after[1].toFixed(2)}`);
  }
  return `${parts.join("")}Z`;
}

/** A triangle scaled by `factor` about the centroid of `points`. */
function scaled(points, factor) {
  const cx = points.reduce((sum, p) => sum + p[0], 0) / points.length;
  const cy = points.reduce((sum, p) => sum + p[1], 0) / points.length;
  return points.map(([x, y]) => [cx + (x - cx) * factor, cy + (y - cy) * factor]);
}

const TRIANGLE = [
  [1.5, 1.5],
  [37.5, 1.5],
  [19.5, 32.5],
];
const circle = (r) => `M${19 - r} 19a${r} ${r} 0 1 0 ${2 * r} 0a${r} ${r} 0 1 0 ${-2 * r} 0Z`;
const OUTLINES = {
  hydro: roundedPolygon(TRIANGLE, 3.2),
  meteo: circle(16),
};
const HOLES = {
  hydro: roundedPolygon(scaled(TRIANGLE, 0.55), 1.2),
  meteo: circle(8),
};
/** The dashes of a ČHMÚ outline [units]. */
const DASH = [5, 3];

/**
 * The paths of a symbol: the filled body (even-odd, so a hole stays empty) and the edges.
 *
 * @param {"hydro"|"meteo"} shape
 * @param {boolean} hollow
 */
function symbolPaths(shape, hollow) {
  const outline = OUTLINES[shape];
  return hollow ? { body: `${outline}${HOLES[shape]}`, edges: [outline, HOLES[shape]] } : { body: outline, edges: [outline] };
}

/**
 * Draw a symbol on a canvas at `scale` pixels per unit, the box's top left at the origin.
 *
 * @param {CanvasRenderingContext2D} context
 * @param {{shape: "hydro"|"meteo", fill: string, outline: string, hollow?: boolean, dashed?: boolean}} look
 *   colours as CSS colours
 * @param {number} scale
 */
export function drawSymbol(context, look, scale) {
  const paths = symbolPaths(look.shape, Boolean(look.hollow));
  context.save();
  context.scale(scale, scale);
  context.fillStyle = look.fill;
  context.fill(new Path2D(paths.body), "evenodd");
  context.strokeStyle = look.outline;
  context.lineJoin = "round";
  context.lineWidth = look.dashed ? 2.6 : 2;
  context.setLineDash(look.dashed ? DASH : []);
  for (const edge of paths.edges) context.stroke(new Path2D(edge));
  context.restore();
}

/**
 * A symbol as SVG, for the legend, the list, the tooltip and the panel: the map's drawing.
 *
 * @param {{shape?: "hydro"|"meteo", color: string, hollow?: boolean, dashed?: boolean,
 *   faded?: boolean, size?: number, className?: string, label?: string}} props `color`
 *   names the CSS variable of the fill; `size` is the height [px]; `label` makes it an
 *   image with that name, otherwise it is hidden from assistive technology
 */
export function SymbolIcon({ shape = "hydro", color, hollow = false, dashed = false, faded = false, size = SYMBOL_PX, className, label }) {
  const box = SHAPES[shape];
  const paths = symbolPaths(shape, hollow);
  const classes = ["sym", shape, hollow ? "hollow" : "", dashed ? "dashed" : "", faded ? "faded" : "", className || ""].filter(Boolean).join(" ");
  return html`<svg
    class=${classes}
    width=${((size * box.width) / box.height).toFixed(1)}
    height=${size}
    viewBox=${`0 0 ${box.width} ${box.height}`}
    style=${{ "--sym-fill": `var(${color})` }}
    role=${label ? "img" : null}
    aria-label=${label || null}
    aria-hidden=${label ? null : "true"}
  >
    <path class="body" d=${paths.body} fill-rule="evenodd" />
    ${paths.edges.map((d) => html`<path class="edge" d=${d} />`)}
  </svg>`;
}

/**
 * A station's symbol in the view „Stacje”, as the map draws it: for the list, the dataset
 * filter and the legend.
 *
 * @param {{kind: string, provider: string, data: boolean, active?: boolean, size?: number}} props
 *   `data` whether the store holds a series of the station (else a hollow centre)
 */
export function StationSymbol({ kind, provider, data, active = true, size = 14 }) {
  const shape = kind === "meteo" ? "meteo" : "hydro";
  return html`<${SymbolIcon} shape=${shape} color=${KIND_COLORS[shape]} hollow=${!data} dashed=${provider === "CHMI"} faded=${!active} size=${size} className="st-sym" />`;
}
