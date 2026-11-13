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
// - the texts are its own (STATUSES.<class>Short of its Polish catalog).
// The outlines are drawn here, the same on the map's canvas and in SVG; no path is copied.
// Where hydro.imgw.pl has no counterpart the shapes stay and this GUI adds its own marks: a
// hollow centre for a station that is only in the catalog and a dashed outline for ČHMÚ.

import { html } from "./lib.js";

/** The water states of a hydrological station, in hydro.imgw.pl's order and words. */
export const HYDRO_STATES = [
  { key: "alarm", label: "Powyżej stanu alarmowego", color: "--imgw-alarm", ageing: true },
  { key: "warning", label: "Powyżej stanu ostrzegawczego", color: "--imgw-warning", ageing: true },
  { key: "high", label: "Strefa stanów wysokich", color: "--imgw-high", ageing: true },
  { key: "medium", label: "Strefa stanów średnich", color: "--imgw-medium", ageing: true },
  { key: "low", label: "Strefa stanów niskich", color: "--imgw-low", ageing: true },
  { key: "below", label: "Poniżej minimum okresowego", color: "--imgw-below", ageing: true },
  { key: "no-water-state-data", label: "Brak danych stanu wody", color: "--imgw-no-data", ageing: false },
  { key: "unknown", label: "Brak stanów charakt. / umownych", color: "--imgw-unknown", ageing: false },
];
const HYDRO_BY_KEY = new Map(HYDRO_STATES.map((state) => [state.key, state]));

/**
 * The water state of IMGW-PIB's map as hydro.imgw.pl draws it.
 *
 * @param {string|null} raw e.g. "medium", "lowOutdated", "no-char-states"; none is
 *   „Brak danych stanu wody”, as on hydro.imgw.pl
 * @returns {{key: string, label: string, color: string, outdated: boolean}}
 */
export function hydroState(raw) {
  let key = raw ? String(raw) : "no-water-state-data";
  const outdated = key.endsWith("Outdated");
  if (outdated) key = key.slice(0, -"Outdated".length);
  // hydro.imgw.pl groups "unknown" and "no-char-states" under one colour and one entry
  const state = HYDRO_BY_KEY.get(key === "no-char-states" ? "unknown" : key) || HYDRO_BY_KEY.get("unknown");
  return { ...state, outdated: outdated && state.ageing };
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
export const METEO_CLASSES = [
  { key: "high-precip", label: "Opad intensywny", color: "--imgw-high-precip", note: "co najmniej silny deszcz w skali Chomicza, ≥ 3,2 mm w 10 min" },
  { key: "precip", label: "Opad", color: "--imgw-precip", note: "w ostatnich 10 min" },
  { key: "no-precip", label: "Brak opadu", color: "--imgw-no-precip", note: "w ostatnich 10 min" },
  { key: "no-precip-data", label: "Brak danych opadowych", color: "--imgw-no-data", note: null },
];
const METEO_BY_KEY = new Map(METEO_CLASSES.map((entry) => [entry.key, entry]));

/**
 * The class of a meteorological station by its latest 10-minute precipitation.
 *
 * @param {number|null} total [mm]
 * @returns {{key: string, label: string, color: string, note: string|null}}
 */
export function meteoClass(total) {
  if (total === null || total === undefined || !Number.isFinite(total)) return METEO_BY_KEY.get("no-precip-data");
  if (total >= HEAVY_10_MIN) return METEO_BY_KEY.get("high-precip");
  return METEO_BY_KEY.get(total > 0 ? "precip" : "no-precip");
}

/** The fill of a station in the view „Stacje”: hydro.imgw.pl's icons of a station kind in its own legend (a station in the middle zone, a station without precipitation). */
export const KIND_COLORS = { hydro: "--imgw-medium", meteo: "--imgw-no-precip" };

// --- the outlines -----------------------------------------------------------------------

/** The box of each shape [units] and the height it takes on the map [px]. */
export const SHAPES = {
  hydro: { width: 39, height: 34 },
  meteo: { width: 38, height: 38 },
};
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
  const classes = ["sym", shape, dashed ? "dashed" : "", faded ? "faded" : "", className || ""].filter(Boolean).join(" ");
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
