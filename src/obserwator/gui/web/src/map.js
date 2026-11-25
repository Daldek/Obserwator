// The map (plan D9, D12): MapLibre GL JS 6 from vendor/ (its module worker is a same-origin
// file, so the CSP keeps `worker-src 'self'`), set up as Archiwista's map views are
// (Archiwista src/archiwista/web/src/maplibre.js, map/style.js): the deployment's basemap
// (`basemap` of api/session: a TileJSON, OpenFreeMap's by default) drawn in the GUI's own
// grey style, place names in the packaged glyphs, in the page's language where the tiles
// have it (Polish by default, `name:pl`); without a basemap, or when its tiles do not load,
// the state borders of Poland and Czechia from Obserwator's package (data/*.geojson: PRG of
// GUGiK and RÚIAN of ČÚZK, ADR-018) are the background.
//
// The three views of main.js share it, each with only its own layer:
// - „Stacje”: every located station of the catalogs in hydro.imgw.pl's symbols
//   (symbols.js): a triangle for a hydrological station, a circle for a meteorological
//   one, in the colours hydro.imgw.pl gives a station of each kind in its legend, whoever
//   provides it, and the GUI's own brown diamond for ČHMÚ's groundwater objects (bores and
//   springs, ADR-032), which the legend names only where a catalog holds one (`kinds`); a
//   hollow centre when the station is only in the catalog, inactive ones faded; the
//   outline tells the class of the station's source (hydromet P13): solid for a national
//   meteorological and hydrological service, dashed for any other, which the legend names
//   only where a catalog holds a station of another source (`classes`);
// - „Pomiary bieżące”: only IMGW-PIB's current measurements (api/current through
//   current.js), hydrological stations filled by their water state and meteorological ones
//   by their precipitation, as hydro.imgw.pl fills them;
// - „PMAXTP”: no station and no layer of the PMAXTP grid, only the point picked by a click.
// The selected station is its symbol at 32 px, as on hydro.imgw.pl. No text labels: a
// tooltip names the station and its latest values with their times; a click selects it.
// Colours come from css/map.css (tokens), read again when the theme changes.
//
// The basemap's credit goes to the view's one strip under the map and the panels
// (`onCredit`, main.js), with the providers' lines (Nogat DEV-20.5); while the borders are
// the background, the strip carries their lines instead (`onBorders`). It never folds:
// MapLibre's own attribution control, which collapses after the first drag, is left out.
// The zoom buttons are the page's own, so their names follow the page's language. The
// map's element keeps the MapLibre map as `maplibre`, for a test or a console asking what
// is drawn.
//
// On an operator's instance (ADR-025, instance.js) the map starts on the instance's box
// (`startBox`: its featured provider's stations or its area) unless the address names a
// station or a PMAXTP point or the map has moved first; it draws the outline of the area
// (api/area) over the background and under the stations, and in `clip` stays within the
// area's bounds; the featured provider's stations lie on top and, while „Pokaż
// pozostałych dostawców” is off, the class switch on „Wszystkie” and no dataset chip
// chosen (instance.js `fadesOthers`), the other providers' are drawn smaller and at the
// instance's `others_opacity` (`fade`), and the legend names the featured provider's
// stations apart from „Pozostałe źródła”.

import { get } from "./api.js";
import { REFRESH_MS, clock, measuredAt } from "./current.js";
import { has } from "./i18n.js";
import { fmt, html, lang, t, tn, useEffect, useRef, useState } from "./lib.js";
import { boundsLabel } from "./pmaxtp/state.js";
import {
  HEAVY_10_MIN,
  HYDRO_STATES,
  KIND_COLORS,
  METEO_CLASSES,
  SHAPES,
  SYMBOL_PX,
  StationSymbol,
  SymbolIcon,
  drawSymbol,
  hydroState,
  kindShape,
  meteoClass,
} from "./symbols.js";
import { isPhone } from "./ui/sheet.js";
import { useDark } from "./ui/theme.js";
import { SOURCE_CLASSES, groundwaterKindName, kindName, providerName, sourceClass } from "./words.js";

// The vendored libraries' versions the page names (<meta name="obserwator-vendor">, from
// vendor/vendor.json, gui/_page.py): MapLibre's module and the glyphs are asked for at the
// page's own vendor/ with their version (?v=), an address the server lets the browser keep
// for a year; without the element (index.html served as a plain file) without one.
const VERSIONS = (() => {
  try {
    return JSON.parse(document.querySelector('meta[name="obserwator-vendor"]')?.content || "{}");
  } catch {
    return {};
  }
})();

/** The address of a vendored file, relative to the page, with its library's version. */
function vendored(path) {
  const version = VERSIONS[path.split("/")[0]];
  return `${new URL(`vendor/${path}`, document.baseURI).href}${version ? `?v=${encodeURIComponent(version)}` : ""}`;
}

const GLYPHS = vendored(`glyphs/{fontstack}/{range}.pbf`).replace(/%7B/gi, "{").replace(/%7D/gi, "}");
const GLYPH_FONT = "noto-sans-regular";
const BORDERS = ["poland_border_wgs84.geojson", "czechia_border_wgs84.geojson"];
/** Poland and Czechia, the first view. */
const HOME = [
  [12.0, 48.4],
  [24.3, 55.0],
];
const EMPTY = { type: "FeatureCollection", features: [] };
/** The lowest layer above the background (basemap or borders), which goes under it: the
 * instance's area, then the stations. */
const OVERLAY = "area";
/** Room around a box the map fits [px]. */
const FIT_PADDING = 16;
/** The symbols are drawn at four times their size, so the selected one (2×) stays sharp. */
const ICON_RATIO = 4;
/** hydro.imgw.pl's 16 px from zoom 7 (where it opens), smaller over the whole of Poland and Czechia. */
const ICON_SIZE = ["interpolate", ["linear"], ["zoom"], 4, 0.6, 6, 0.8, 7, 1];
const SELECTED_SIZE = ["interpolate", ["linear"], ["zoom"], 4, 1.5, 7, 2];
/** A station of a provider beside the featured one while the list asks for no other
 * provider (instance.js `fadesOthers`, I6): ICON_SIZE times FADED_SIZE, its opacity times
 * the instance's `others_opacity`. */
const FADED = ["==", ["get", "dim"], 1];
const FADED_SIZE = 0.7;
const SHRINK = ["case", FADED, FADED_SIZE, 1];
const STATION_SIZE = ["interpolate", ["linear"], ["zoom"], 4, ["*", 0.6, SHRINK], 6, ["*", 0.8, SHRINK], 7, SHRINK];
/** Room the tooltip needs right of and around the pointer [px], else it opens on the other side. */
const TIP_WIDTH = 300;
const TIP_HALF_HEIGHT = 90;

// --- colours from css/map.css ----------------------------------------------------------

function cssColor(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || "#888888";
}

function palette() {
  const names = [
    "bg", "land", "landuse", "water", "road", "road-far", "casing", "state", "country", "water-text",
    "halo", "place-1", "place-2", "place-3", "place-4", "border", "area",
  ];
  const out = {};
  for (const name of names) out[name] = cssColor(`--map-${name}`);
  out.accent = cssColor("--accent");
  out.surface = cssColor("--surface");
  return out;
}

// --- the background: the basemap (after Archiwista's map/style.js) or the borders -----------

/**
 * The vector source of a basemap's TileJSON, its tiles checked to stay on its origin (the
 * only one the CSP allows besides the page's own).
 *
 * @param {{url: string}} basemap `basemap` of api/session
 * @returns {Promise<object>} a MapLibre vector source
 */
async function loadBasemapSource(basemap) {
  const response = await fetch(basemap.url);
  if (!response.ok) throw new Error(`TileJSON ${response.status}`);
  const doc = await response.json();
  if (!Array.isArray(doc.tiles) || !doc.tiles.length) throw new Error(`TileJSON ${basemap.url}`);
  const origin = new URL(basemap.url).origin;
  const tiles = doc.tiles.map((tile) => {
    const url = new URL(String(tile), basemap.url);
    if (url.origin !== origin) throw new Error(`TileJSON ${url.origin}`);
    return url.href.replace(/%7B/gi, "{").replace(/%7D/gi, "}");
  });
  const { minzoom, maxzoom, bounds } = doc;
  return { type: "vector", tiles, minzoom, maxzoom, bounds };
}

/** A place's name in the page's language where the tiles have it (Polish by default, plan D9), else its Latin or local name. */
function placeName() {
  return ["coalesce", ["get", `name:${lang()}`], ["get", "name:latin"], ["get", "name"]];
}

const LINES = ["match", ["geometry-type"], ["LineString", "MultiLineString"], true, false];
const POINTS = ["match", ["geometry-type"], ["Point", "MultiPoint"], true, false];
const BUILT_UP = ["residential", "suburb", "quarter", "neighbourhood", "commercial", "industrial", "retail"];
const ROADS = ["motorway", "trunk", "primary", "secondary", "tertiary", "minor"];

/** The grey layers over the OpenMapTiles schema, with the paint keys each takes from the palette. */
function basemapLayers(colors) {
  const zoom = (...stops) => ["interpolate", ["linear"], ["zoom"], ...stops];
  const layer = (id, type, sourceLayer, filter, rest) => ({
    id: `basemap-${id}`,
    type,
    source: "basemap",
    "source-layer": sourceLayer,
    ...(filter ? { filter } : {}),
    ...rest,
  });
  const boundary = (level, disputed) => [
    "all",
    ["==", ["get", "admin_level"], level],
    ["!=", ["get", "maritime"], 1],
    [disputed ? "==" : "!=", ["get", "disputed"], 1],
  ];
  const roads = ["all", ["match", ["get", "class"], ROADS, true, false], ["!=", ["get", "brunnel"], "tunnel"]];
  const roadWidth = (extra) => {
    const of = (motorway, primary, other) => ["match", ["get", "class"], ["motorway", "trunk"], motorway + extra, "primary", primary + extra, other + extra];
    return ["interpolate", ["exponential", 1.5], ["zoom"], 5, of(0.5, 0.35, 0.25), 10, of(1.4, 1, 0.5), 16, of(9, 7, 4)];
  };
  const label = (id, sourceLayer, filter, { size, color, minzoom = 0, maxzoom = 24, line = false, layout = {} }) =>
    layer(id, "symbol", sourceLayer, filter, {
      minzoom,
      maxzoom,
      layout: {
        "text-field": placeName(),
        "text-font": [GLYPH_FONT],
        "text-size": size,
        "text-max-width": 8,
        ...(line ? { "symbol-placement": "line" } : {}),
        ...layout,
      },
      paint: { "text-color": colors[color], "text-halo-color": colors.halo, "text-halo-width": 1.2 },
      metadata: { color },
    });
  const place = (id, classes, options) =>
    label(id, "place", ["match", ["get", "class"], classes, true, false], {
      ...options,
      layout: { "symbol-sort-key": ["coalesce", ["get", "rank"], 99], ...options.layout },
    });
  return [
    layer("landuse", "fill", "landuse", ["match", ["get", "class"], BUILT_UP, true, false], { paint: { "fill-color": colors.landuse }, metadata: { fill: "landuse" } }),
    layer("water", "fill", "water", null, { paint: { "fill-color": colors.water }, metadata: { fill: "water" } }),
    layer("waterway", "line", "waterway", ["match", ["get", "class"], ["river", "canal"], true, false], {
      paint: { "line-color": colors.water, "line-width": zoom(7, 0.6, 14, 3) },
      metadata: { line: "water" },
    }),
    layer("state", "line", "boundary", boundary(4, false), {
      minzoom: 5,
      paint: { "line-color": colors.state, "line-width": zoom(5, 0.6, 12, 1.2), "line-dasharray": [3, 2] },
      metadata: { line: "state" },
    }),
    layer("road", "line", "transportation", roads, {
      minzoom: 6,
      layout: { "line-cap": "round", "line-join": "round" },
      paint: { "line-color": colors["road-far"], "line-width": roadWidth(0) },
      metadata: { line: "road-far" },
    }),
    layer("country", "line", "boundary", boundary(2, false), {
      paint: { "line-color": colors.country, "line-width": zoom(3, 0.8, 10, 1.8) },
      metadata: { line: "country" },
    }),
    layer("country-disputed", "line", "boundary", boundary(2, true), {
      paint: { "line-color": colors.country, "line-width": zoom(3, 0.8, 10, 1.8), "line-dasharray": [2, 2] },
      metadata: { line: "country" },
    }),
    label("waterway-name", "waterway", ["==", ["get", "class"], "river"], { minzoom: 9, line: true, size: zoom(9, 10, 14, 12), color: "water-text" }),
    label("water-name", "water_name", POINTS, { minzoom: 6, size: zoom(6, 10, 10, 12), color: "water-text" }),
    label("water-line-name", "water_name", LINES, { minzoom: 8, line: true, size: 11, color: "water-text" }),
    place("village", ["village"], { minzoom: 10, size: zoom(10, 10, 15, 13), color: "place-1" }),
    place("town", ["town"], { minzoom: 7.5, size: zoom(7, 10, 13, 13), color: "place-2" }),
    place("city", ["city"], { minzoom: 5, size: zoom(5, 10.5, 9, 13, 13, 16), color: "place-3" }),
    place("country-name", ["country"], { maxzoom: 6.5, size: zoom(3, 10, 6, 12), color: "place-4", layout: { "text-transform": "uppercase", "text-letter-spacing": 0.08 } }),
  ];
}

/** The basemap's layers under the stations; the background takes the basemap's grey. */
function addBasemap(map, source, colors) {
  if (map.getSource("basemap")) return;
  map.addSource("basemap", source);
  for (const layer of basemapLayers(colors)) map.addLayer(layer, OVERLAY);
  map.setPaintProperty("background", "background-color", colors.bg);
}

/** The names of the basemap's places in the page's language. */
function nameBasemap(map) {
  for (const layer of map.getStyle().layers) {
    if (layer.source === "basemap" && layer.type === "symbol") map.setLayoutProperty(layer.id, "text-field", placeName());
  }
}

/** Take a basemap out again (its tiles do not load). */
function removeBasemap(map) {
  for (const layer of map.getStyle().layers) {
    if (layer.source === "basemap") map.removeLayer(layer.id);
  }
  if (map.getSource("basemap")) map.removeSource("basemap");
}

/** The borders of Poland and Czechia from Obserwator's package, on the colour of the sea. */
async function addBorders(map, colors) {
  if (map.getSource("borders")) return;
  const parts = await Promise.all(BORDERS.map((name) => fetch(new URL(`data/${name}`, document.baseURI)).then((r) => r.json())));
  if (map.getSource("borders")) return;
  const data = { type: "FeatureCollection", features: parts.flatMap((part) => part.features || []) };
  map.addSource("borders", { type: "geojson", data });
  map.addLayer({ id: "borders-fill", type: "fill", source: "borders", paint: { "fill-color": colors.land }, metadata: { fill: "land" } }, OVERLAY);
  map.addLayer({ id: "borders-line", type: "line", source: "borders", paint: { "line-color": colors.border, "line-width": 1.4 }, metadata: { line: "border" } }, OVERLAY);
  map.setPaintProperty("background", "background-color", colors.water);
}

/** Repaint the background, the basemap and the borders in the theme's colours. */
function paintBackground(map, colors) {
  map.setPaintProperty("background", "background-color", map.getSource("borders") ? colors.water : colors.bg);
  for (const layer of map.getStyle().layers) {
    const meta = layer.metadata || {};
    if (meta.fill) map.setPaintProperty(layer.id, "fill-color", colors[meta.fill]);
    if (meta.line) map.setPaintProperty(layer.id, "line-color", colors[meta.line]);
    if (meta.color) {
      map.setPaintProperty(layer.id, "text-color", colors[meta.color]);
      map.setPaintProperty(layer.id, "text-halo-color", colors.halo);
    }
  }
}

// --- the symbols (symbols.js) ----------------------------------------------------------------

/**
 * The image of a station in the view „Stacje”: the shape of its kind, whether it has series
 * and the class of its source, whose outline it draws (hydromet P13), never its provider.
 */
function stationIcon(kind, data, source) {
  return `st-${kindShape(kind)}-${data ? 1 : 0}-${source === "other" ? "other" : "nmhs"}`;
}

/** Every image the map draws: its name and look. */
function looks() {
  const out = [];
  for (const kind of Object.keys(SHAPES)) {
    for (const data of [true, false]) {
      for (const source of SOURCE_CLASSES) {
        out.push({ name: stationIcon(kind, data, source), shape: kind, color: KIND_COLORS[kind], hollow: !data, source });
      }
    }
  }
  for (const state of HYDRO_STATES) {
    out.push({ name: `now-hydro-${state.key}-0`, shape: "hydro", color: state.color });
    if (state.ageing) out.push({ name: `now-hydro-${state.key}-1`, shape: "hydro", color: state.color, hollow: true });
  }
  for (const entry of METEO_CLASSES) out.push({ name: `now-meteo-${entry.key}`, shape: "meteo", color: entry.color });
  return out;
}

/** Draw (or redraw for a theme) every image: 16 px tall, at ICON_RATIO pixels per pixel. */
function drawImages(map) {
  const outline = cssColor("--imgw-outline");
  const canvas = document.createElement("canvas");
  const context = canvas.getContext("2d", { willReadFrequently: true });
  for (const look of looks()) {
    const box = SHAPES[look.shape];
    const scale = (SYMBOL_PX / box.height) * ICON_RATIO;
    canvas.width = Math.ceil(box.width * scale);
    canvas.height = Math.ceil(box.height * scale);
    context.clearRect(0, 0, canvas.width, canvas.height);
    drawSymbol(context, { ...look, fill: cssColor(look.color), outline }, scale);
    const image = context.getImageData(0, 0, canvas.width, canvas.height);
    if (map.hasImage(look.name)) map.updateImage(look.name, image);
    else map.addImage(look.name, image, { pixelRatio: ICON_RATIO });
  }
}

function point(lon, lat, properties) {
  return { type: "Feature", geometry: { type: "Point", coordinates: [lon, lat] }, properties };
}

/** A box [west, south, east, north] as MapLibre's bounds: its south-west and north-east corners. */
function corners([west, south, east, north]) {
  return [
    [west, south],
    [east, north],
  ];
}

/**
 * The features of „Stacje”: the featured provider's stations on top and, while `fade`, the
 * other providers' marked to be drawn smaller and fainter (I6).
 *
 * @param {object[]} stations
 * @param {string|null} featured the instance's featured provider
 * @param {boolean} fade whether the other providers' stations are faded
 */
function stationFeatures(stations, featured, fade) {
  const features = [];
  for (const station of stations) {
    if (station.lon === null || station.lat === null) continue;
    const data = station.datasets.length > 0;
    const first = featured !== null && station.provider === featured;
    features.push(
      point(station.lon, station.lat, {
        code: station.code,
        icon: stationIcon(station.kind, data, sourceClass(station.provider)),
        active: station.active ? 1 : 0,
        rank: (first ? 4 : 0) + (data ? 2 : 0) + (station.active ? 1 : 0),
        dim: fade && featured !== null && !first ? 1 : 0,
      }),
    );
  }
  return { type: "FeatureCollection", features };
}

/** The drawing order of the current measurements: meteorological below, the gravest water states on top. */
const HYDRO_RANK = { alarm: 9, warning: 8, high: 7, below: 6, medium: 5, low: 4, unknown: 3, "no-water-state-data": 2 };
const METEO_RANK = { "high-precip": 1.6, precip: 1.4, "no-precip": 1.2, "no-precip-data": 1 };

function currentFeatures(doc) {
  if (!doc) return EMPTY;
  const features = [];
  for (const row of doc.meteo) {
    const entry = meteoClass(row.p10);
    features.push(point(row.lon, row.lat, { code: row.code, icon: `now-meteo-${entry.key}`, rank: METEO_RANK[entry.key] }));
  }
  for (const row of doc.hydro) {
    const state = hydroState(row.state);
    features.push(point(row.lon, row.lat, { code: row.code, icon: `now-hydro-${state.key}-${state.outdated ? 1 : 0}`, rank: HYDRO_RANK[state.key] - (state.outdated ? 0.5 : 0) }));
  }
  return { type: "FeatureCollection", features };
}

const NONE = ["==", ["get", "code"], ""];

/** The opacity of „Stacje”'s symbols: an inactive station half, a faded one `others` times. */
function stationOpacity(others) {
  return ["*", ["case", ["==", ["get", "active"], 1], 1, 0.5], ["case", FADED, others, 1]];
}

/** The instance's `others_opacity` (api/session); 1 without an instance, which fades nothing. */
function othersOpacity(scope) {
  return scope && scope.instance ? scope.instance.others_opacity : 1;
}

/** The layers of each view; every other layer of these is hidden. */
const VIEW_LAYERS = {
  stations: ["stations", "stations-selected"],
  current: ["current", "current-selected"],
  pmaxtp: ["pmaxtp-ring", "pmaxtp-dot"],
};

function addLayers(map, colors) {
  drawImages(map);
  map.addSource("area", { type: "geojson", data: EMPTY });
  map.addSource("stations", { type: "geojson", data: EMPTY });
  map.addSource("current", { type: "geojson", data: EMPTY });
  map.addSource("pmaxtp", { type: "geojson", data: EMPTY });
  // The instance's area (I4) in every view: a faint fill and its outline
  map.addLayer({ id: "area", type: "fill", source: "area", paint: { "fill-color": colors.area, "fill-opacity": 0.06 }, metadata: { fill: "area" } });
  map.addLayer({ id: "area-line", type: "line", source: "area", paint: { "line-color": colors.area, "line-width": 2 }, metadata: { line: "area" } });
  const symbols = (id, source, { size = ICON_SIZE, filter = null, paint = {} } = {}) => ({
    id,
    type: "symbol",
    source,
    ...(filter ? { filter } : {}),
    layout: {
      visibility: "none",
      "icon-image": ["get", "icon"],
      "icon-allow-overlap": true,
      "icon-ignore-placement": true,
      "icon-size": size,
      "symbol-sort-key": ["get", "rank"],
    },
    paint,
  });
  map.addLayer(symbols("stations", "stations", { size: STATION_SIZE, paint: { "icon-opacity": stationOpacity(1) } }));
  map.addLayer(symbols("stations-selected", "stations", { size: SELECTED_SIZE, filter: NONE }));
  map.addLayer(symbols("current", "current"));
  map.addLayer(symbols("current-selected", "current", { size: SELECTED_SIZE, filter: NONE }));
  map.addLayer({
    id: "pmaxtp-ring",
    type: "circle",
    source: "pmaxtp",
    layout: { visibility: "none" },
    paint: { "circle-radius": 11, "circle-color": "rgba(0, 0, 0, 0)", "circle-stroke-color": colors.accent, "circle-stroke-width": 3 },
  });
  map.addLayer({
    id: "pmaxtp-dot",
    type: "circle",
    source: "pmaxtp",
    layout: { visibility: "none" },
    paint: { "circle-radius": 3.5, "circle-color": colors.accent, "circle-stroke-color": colors.surface, "circle-stroke-width": 1.5 },
  });
}

function repaintLayers(map, colors) {
  drawImages(map);
  map.setPaintProperty("pmaxtp-ring", "circle-stroke-color", colors.accent);
  map.setPaintProperty("pmaxtp-dot", "circle-color", colors.accent);
  map.setPaintProperty("pmaxtp-dot", "circle-stroke-color", colors.surface);
}

/**
 * The map.
 *
 * @param {{stations: object[], byCode: Map<string, object>, kinds: string[], classes: string[],
 *   selected: string|null, fly: {code: string, n: number}|null,
 *   view: "stations"|"current"|"pmaxtp",
 *   current: {doc: object|null, error: Error|null, loading: boolean},
 *   pick: {lat: number, lon: number}|null, pickFly: {n: number}|null,
 *   onBorders: (drawn: boolean) => void, onCredit: (credit: string|null) => void,
 *   session: object|null, scope: object|null, fade: boolean,
 *   startBox: number[]|null, onSelect: (code: string) => void,
 *   onPick: (point: {lat: number, lon: number}) => void}} props
 *   the stations drawn in „Stacje” (already filtered), all stations by code (the tooltip),
 *   the kinds the legend names (words.js `shownKinds`), the classes of the stations' sources
 *   (words.js `shownClasses`: the legend explains the outlines where a station of another
 *   source is held), the selected one, a request to fly to a station, the view, the current
 *   measurements (current.js), the point picked for PMAXTP and a request to fly to it,
 *   whether the packaged borders are the background,
 *   where the basemap's credit goes while the basemap is drawn, api/session (null until it
 *   answers: its `basemap`), what the deployment shows (instance.js `scopeOf`, null until
 *   the session answers: the instance's featured provider and area), whether the other
 *   providers' stations are faded, the instance's start box [west, south, east, north]
 *   (null: none, or the address names a place), the selection's and the pick's handlers
 * @returns {object} the map with its legend and its zoom buttons
 */
export function StationMap({ stations, byCode, kinds, classes, selected, fly, view, current, pick, pickFly, onBorders, onCredit, session, scope, fade, startBox, onSelect, onPick }) {
  const box = useRef(null);
  const mapRef = useRef(null);
  const handlers = useRef({});
  handlers.current = { onSelect, onPick, view };
  // Whether the map has moved since it started (the person, a fly): an instance's start
  // box no longer applies
  const settled = useRef(false);
  const [ready, setReady] = useState(false);
  const [failure, setFailure] = useState(null);
  // "pending" until the session names the basemap; then "basemap", "borders" (none set) or
  // "failed" (set, but it does not load: the borders instead)
  const [background, setBackground] = useState("pending");
  const [tip, setTip] = useState(null);
  const dark = useDark();
  const rows = current.doc;
  const basemap = session ? session.basemap || null : undefined;
  const basemapUrl = basemap ? basemap.url : basemap;
  const featured = scope ? scope.featured : null;
  const others = othersOpacity(scope);
  const area = scope && scope.instance ? scope.instance.area : null;
  const outline = area ? area.outline : null;
  const bounds = area ? area.bounds : null;

  useEffect(() => {
    let live = true;
    let map = null;
    const element = box.current;
    import(vendored("maplibre-gl/maplibre-gl.mjs"))
      .then((maplibre) => {
        if (!live) return;
        const colors = palette();
        map = new maplibre.Map({
          container: element,
          style: { version: 8, glyphs: GLYPHS, sources: {}, layers: [{ id: "background", type: "background", paint: { "background-color": colors.bg } }] },
          bounds: HOME,
          fitBoundsOptions: { padding: FIT_PADDING },
          attributionControl: false,
          dragRotate: false,
          pitchWithRotate: false,
          touchPitch: false,
          maxPitch: 0,
          renderWorldCopies: false,
          locale: { "Map.Title": t("stations.map.label") },
        });
        map.touchZoomRotate.disableRotation();
        map.keyboard.disableRotation();
        Object.defineProperty(element, "maplibre", { value: map, configurable: true });
        // The person's own move (a drag, the wheel, a key, a pinch, the zoom buttons) settles
        // the map, as a fly does (below); a resize of the page does not
        const settle = (event) => {
          if (event.type === "zoomstart" || event.originalEvent) settled.current = true;
        };
        map.on("movestart", settle);
        map.on("zoomstart", settle);
        // With a listener MapLibre logs nothing itself: a tile or a glyph range that does
        // not load leaves the map as it is (a basemap that never loads gives way to the
        // borders, below); anything else is a fault of this page
        map.on("error", (event) => {
          if (!event.sourceId) console.warn(event.error);
        });
        map.once("load", () => {
          if (!live) return;
          addLayers(map, colors);
          // A point of the view shown; MapLibre answers a hidden layer's symbols for a
          // moment after the view changes, and those are not there to point at
          const pointed = (event) => {
            const feature = event.features && event.features[0];
            if (!feature) return null;
            const layer = feature.layer.id.startsWith("current") ? "current" : "stations";
            return layer === handlers.current.view ? { code: feature.properties.code, layer } : null;
          };
          const show = (event) => {
            const found = pointed(event);
            if (!found) return;
            map.getCanvas().style.cursor = "pointer";
            setTip({ x: event.point.x, y: event.point.y, ...found });
          };
          const hide = () => {
            map.getCanvas().style.cursor = handlers.current.view === "pmaxtp" ? "crosshair" : "";
            setTip(null);
          };
          for (const id of [...VIEW_LAYERS.stations, ...VIEW_LAYERS.current]) {
            map.on("mousemove", id, show);
            map.on("mouseleave", id, hide);
            map.on("click", id, (event) => {
              const found = pointed(event);
              if (found) handlers.current.onSelect(found.code);
            });
          }
          // „PMAXTP”: the stations are hidden, a click anywhere picks the point
          map.on("click", (event) => {
            if (handlers.current.view === "pmaxtp") handlers.current.onPick({ lat: event.lngLat.lat, lon: event.lngLat.lng });
          });
          mapRef.current = map;
          setReady(true);
        });
      })
      .catch((error) => {
        if (live) setFailure(error);
      });
    return () => {
      live = false;
      if (map) map.remove();
      delete element.maplibre;
      mapRef.current = null;
    };
  }, []);

  // The background, once the session names the basemap
  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map || basemapUrl === undefined) return undefined;
    let live = true;
    let loaded = false;
    let failed = false;
    const borders = (state) => {
      setBackground(state);
      addBorders(map, palette()).catch((error) => console.warn(error));
    };
    const onData = (event) => {
      if (event.sourceId === "basemap" && event.tile) loaded = true;
    };
    // A basemap none of whose tiles loads (offline, blocked) gives way to the borders, once
    // every tile of the view has answered (the map is idle); a failing tile, even the first
    // to answer, does not while another of the view loads
    const onError = (event) => {
      if (event.sourceId === "basemap") failed = true;
    };
    const onIdle = () => {
      if (!live || loaded || !failed) return;
      live = false;
      removeBasemap(map);
      borders("failed");
    };
    if (basemapUrl === null) {
      borders("borders");
    } else {
      map.on("data", onData);
      map.on("error", onError);
      map.on("idle", onIdle);
      loadBasemapSource(basemap).then(
        (source) => {
          if (!live) return;
          addBasemap(map, source, palette());
          setBackground("basemap");
        },
        () => {
          if (!live) return;
          live = false;
          borders("failed");
        },
      );
    }
    return () => {
      live = false;
      map.off("data", onData);
      map.off("error", onError);
      map.off("idle", onIdle);
    };
  }, [ready, basemapUrl]);

  // The instance (I4, I5): in `clip` the map stays within the area's bounds; it starts on
  // the instance's box unless it has moved before the session answered
  const startKey = startBox ? startBox.join(",") : "";
  const boundsKey = bounds ? bounds.join(",") : "";
  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map) return;
    if (bounds) map.setMaxBounds(corners(bounds));
    if (startBox && !settled.current) {
      settled.current = true;
      map.fitBounds(corners(startBox), { padding: FIT_PADDING, animate: false });
    }
  }, [ready, startKey, boundsKey]);

  // The outline of the instance's area, asked for once
  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map || !outline) return undefined;
    let live = true;
    get(outline).then(
      (feature) => {
        if (live) map.getSource("area").setData(feature);
      },
      (error) => console.warn(error),
    );
    return () => {
      live = false;
    };
  }, [ready, outline]);

  // The view: only its own layers are shown
  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map) return;
    for (const [name, ids] of Object.entries(VIEW_LAYERS)) {
      for (const id of ids) map.setLayoutProperty(id, "visibility", name === view ? "visible" : "none");
    }
    map.getCanvas().style.cursor = view === "pmaxtp" ? "crosshair" : "";
    // The canvas is a landmark of its own (MapLibre's role="region"): named by what it shows
    map.getCanvas().setAttribute("aria-label", view === "pmaxtp" ? t("shell.map_pmaxtp") : t("stations.map.label"));
    setTip(null);
  }, [ready, view, lang()]);

  // The stations of „Stacje”
  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map) return;
    map.getSource("stations").setData(stationFeatures(stations, featured, fade));
  }, [ready, stations, featured, fade]);

  // The opacity of the stations faded beside the featured provider (the instance's)
  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map) return;
    map.setPaintProperty("stations", "icon-opacity", stationOpacity(others));
  }, [ready, others]);

  // The points of „Pomiary bieżące”
  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map) return;
    map.getSource("current").setData(currentFeatures(rows));
  }, [ready, rows]);

  // The point of „PMAXTP”
  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map) return;
    map.getSource("pmaxtp").setData(pick ? { type: "FeatureCollection", features: [point(pick.lon, pick.lat, {})] } : EMPTY);
  }, [ready, pick && pick.lat, pick && pick.lon]);

  // The selected station, drawn at 32 px
  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map) return;
    const filter = ["==", ["get", "code"], selected || ""];
    map.setFilter("stations-selected", filter);
    map.setFilter("current-selected", filter);
  }, [ready, selected]);

  // Fly to a station chosen from the list or named by the address
  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map || !fly) return;
    const station = byCode.get(fly.code);
    if (!station || station.lon === null) return;
    settled.current = true;
    map.flyTo({ center: [station.lon, station.lat], zoom: Math.max(map.getZoom(), 9), duration: 900 });
  }, [ready, fly, byCode]);

  // Fly to a PMAXTP point typed in the form
  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map || !pickFly || !pick) return;
    settled.current = true;
    map.flyTo({ center: [pick.lon, pick.lat], zoom: Math.max(map.getZoom(), 8), duration: 900 });
  }, [ready, pickFly]);

  // The theme's colours
  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map) return;
    const colors = palette();
    paintBackground(map, colors);
    repaintLayers(map, colors);
  }, [ready, dark]);

  // The canvas's name and the basemap's place names in the page's language
  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map) return;
    map.getCanvas().setAttribute("aria-label", t("stations.map.label"));
    nameBasemap(map);
  }, [ready, lang()]);

  let tipBody = null;
  if (tip && tip.layer === "current" && rows) {
    const hydro = rows.hydro.find((row) => row.code === tip.code);
    const meteo = hydro ? null : rows.meteo.find((row) => row.code === tip.code);
    if (hydro) tipBody = html`<${HydroTip} row=${hydro} station=${byCode.get(tip.code)} />`;
    else if (meteo) tipBody = html`<${MeteoTip} row=${meteo} station=${byCode.get(tip.code)} />`;
  } else if (tip && byCode.get(tip.code)) {
    tipBody = html`<${StationTip} station=${byCode.get(tip.code)} />`;
  }
  const credit = background === "basemap" && basemap && basemap.attribution ? t("stations.map.basemap_credit", { credit: basemap.attribution }) : null;
  useEffect(() => onCredit(credit), [credit]);
  const bordersDrawn = background === "borders" || background === "failed";
  useEffect(() => onBorders(bordersDrawn), [bordersDrawn]);
  return html`<div class="map-wrap">
    <div class="map-stage">
      <div class="map" ref=${box}></div>
      ${failure
        ? html`<div class="map-failure" role="status">
            <strong>${t("stations.map.failure")}</strong>. ${t("stations.map.failure_rest")}
            <span class="map-failure-reason">MapLibre: ${failure.message || String(failure)}</span>
          </div>`
        : null}
      ${tipBody ? html`<${Tip} x=${tip.x} y=${tip.y} stage=${box.current}>${tipBody}</${Tip}>` : null}
      <${Legend} view=${view} background=${background} current=${current} scope=${scope} fade=${fade} area=${area !== null} kinds=${kinds} classes=${classes} />
      ${ready ? html`<${ZoomButtons} map=${mapRef.current} />` : null}
    </div>
  </div>`;
}

/** The tooltip at the pointer, turned to the side with room. */
function Tip({ x, y, stage, children }) {
  const width = stage ? stage.clientWidth : Infinity;
  const height = stage ? stage.clientHeight : Infinity;
  const classes = ["map-tip", x > width - TIP_WIDTH ? "west" : "", y < TIP_HALF_HEIGHT ? "below" : y > height - TIP_HALF_HEIGHT ? "above" : ""].filter(Boolean).join(" ");
  return html`<div class=${classes} style=${{ left: `${x}px`, top: `${y}px` }} role="tooltip">${children}</div>`;
}

/** The page's zoom buttons, bottom right (Nogat design/README.md). */
function ZoomButtons({ map }) {
  const [zoom, setZoom] = useState(() => map.getZoom());
  useEffect(() => {
    const update = () => setZoom(map.getZoom());
    map.on("zoomend", update);
    return () => map.off("zoomend", update);
  }, [map]);
  return html`<div class="map-zoom" role="group" aria-label=${t("stations.map.zoom")}>
    <button type="button" title=${t("stations.map.zoom_in")} aria-label=${t("stations.map.zoom_in")} disabled=${zoom >= map.getMaxZoom()} onClick=${() => map.zoomIn()}>
      <svg viewBox="0 0 20 20" aria-hidden="true"><path d="M10 4.5v11M4.5 10h11" /></svg>
    </button>
    <button type="button" title=${t("stations.map.zoom_out")} aria-label=${t("stations.map.zoom_out")} disabled=${zoom <= map.getMinZoom()} onClick=${() => map.zoomOut()}>
      <svg viewBox="0 0 20 20" aria-hidden="true"><path d="M4.5 10h11" /></svg>
    </button>
  </div>`;
}

/** A station of „Stacje”: its name, river, code, provider, kind (a groundwater object's also what it is) and the years of its series. */
function StationTip({ station }) {
  const facts = [providerName(station.provider), kindName(station.kind), groundwaterKindName(station.groundwater_kind), station.active ? null : t("stations.inactive")].filter(Boolean);
  return html`
    <strong>${station.name || station.code}</strong>
    ${station.river ? html`<span>${station.river}</span>` : null}
    <span class="muted"><code>${station.code}</code> · ${facts.join(" · ")}</span>
    <span class="muted">${station.first ? t("stations.tip.series", { years: `${station.first}–${station.last}` }) : t("stations.catalog_only")}</span>
  `;
}

/** A value with its unit and the time of its measurement, or nothing without a value; a
 * stale value (`current hydro`'s `flow_stale`) is struck through and says so. */
function Reading({ label, value, digits = 0, unit, at, stale = false }) {
  if (value === null || value === undefined) return null;
  return html`<span class=${stale ? "tip-value stale" : "tip-value"}>${label}: <strong>${fmt(value, digits)} ${unit}</strong>${at ? html` <span class="muted">${measuredAt(at)}</span>` : null}${stale ? html` <span class="stale-note">${t("stations.tip.flow_stale")}</span>` : null}</span>`;
}

function HydroTip({ row, station }) {
  const state = hydroState(row.state);
  return html`
    <strong>${(station && station.name) || row.name || row.code}</strong>
    ${row.river ? html`<span>${row.river}</span>` : null}
    <span class="muted"><code>${row.code}</code> · ${providerName("IMGW")} · ${kindName("hydro")}</span>
    <span class="tip-class"><${SymbolIcon} shape="hydro" color=${state.color} hollow=${state.outdated} size=${13} />${state.label}${state.outdated ? ` ${t("stations.tip.outdated")}` : ""}</span>
    <${Reading} label=${t("stations.tip.water_level")} value=${row.h} unit="cm" at=${row.h_at} />
    <${Reading} label=${t("stations.tip.discharge")} value=${row.q} digits=${row.q !== null && row.q < 10 ? 2 : 1} unit="m³/s" at=${row.q_at} stale=${row.q_stale === true} />
    <${Reading} label=${t("stations.tip.water_temperature")} value=${row.t} digits=${1} unit="°C" at=${row.t_at} />
    ${row.h === null && row.q === null && row.t === null ? html`<span class="muted">${t("stations.tip.no_values")}</span>` : null}
  `;
}

function MeteoTip({ row, station }) {
  const entry = meteoClass(row.p10);
  return html`
    <strong>${(station && station.name) || row.name || row.code}</strong>
    <span class="muted"><code>${row.code}</code> · ${providerName("IMGW")} · ${kindName("meteo")}</span>
    <span class="tip-class"><${SymbolIcon} shape="meteo" color=${entry.color} size=${13} />${entry.label}${entry.note ? ` (${entry.note})` : ""}</span>
    <${Reading} label=${t("stations.tip.precipitation")} value=${row.p10} digits=${1} unit="mm" />
    <${Reading} label=${t("stations.tip.air_temperature")} value=${row.t} digits=${1} unit="°C" at=${row.t_at} />
    <${Reading} label=${t("stations.tip.wind")} value=${row.wind} digits=${1} unit="m/s" />
    <${Reading} label=${t("stations.tip.humidity")} value=${row.rh} unit="%" />
  `;
}

/**
 * A station's symbol of size `size` for each kind named, each with its name; `source` the
 * class of the sources whose outline they draw (null: a service's solid outline).
 */
function KindItems({ kinds, source = null, opacity = null, size = 14 }) {
  return kinds.map(
    (kind) => html`<li key=${kind}><${SymbolIcon} shape=${kind} color=${KIND_COLORS[kind]} source=${source} opacity=${opacity} size=${size} className="st-sym" />${kindName(kind)}</li>`,
  );
}

/** The outline of each class of sources (hydromet P13): a service's solid, another source's dashed. */
function ClassItems() {
  return html`<ul class="legend-list legend-classes">
    <li><${StationSymbol} kind="hydro" data=${true} source="nmhs" />${t("stations.legend.source_nmhs")}</li>
    <li><${StationSymbol} kind="hydro" data=${true} source="other" />${t("stations.legend.source_other")}</li>
  </ul>`;
}

/**
 * The symbols of „Stacje”: one per kind of station named (groundwater only where a catalog
 * holds a groundwater object, with the note that its diamond is the GUI's own), whoever
 * provides it, and where a catalog holds a station of another source the outline of each
 * class of sources (hydromet P13), every symbol drawn with the outline of the one class
 * held, else a service's. While the other providers' stations are faded beside the
 * featured one (`fade`), the featured provider's stations are one group and, while another
 * provider is shown, „Pozostałe źródła” another, drawn as the map draws them (smaller, at
 * the instance's `others_opacity`, dashed where every one of them is another source); no
 * word of a view the instance does not serve.
 *
 * @param {{scope: object|null, fade: boolean, kinds: string[], classes: string[]}} props
 *   what the deployment shows (null until the session answers), whether the other
 *   providers' stations are faded, the kinds named (words.js `shownKinds`) and the classes
 *   of the stations' sources (words.js `shownClasses`)
 */
function StationsLegend({ scope, fade, kinds, classes = [] }) {
  const featured = fade && scope ? scope.featured : null;
  const rest = featured ? scope.providers.filter((id) => id !== featured && !scope.hidden.includes(id)) : [];
  const only = classes.length === 1 ? classes[0] : null;
  const marks = html`<li><${StationSymbol} kind="hydro" data=${false} source=${only} />${t("stations.catalog_only")}</li>
    <li><${StationSymbol} kind="hydro" data=${true} active=${false} source=${only} />${t("stations.legend.inactive")}</li>
    <li><${StationSymbol} kind="hydro" data=${true} source=${only} size=${24} />${t("stations.legend.selected")}</li>`;
  const outlines = classes.includes("other") ? html`<${ClassItems} />` : null;
  const note = html`<p class="legend-note">${t(!scope || scope.views.includes("current") ? "stations.legend.stations_note" : "stations.legend.symbols_note")}</p>
    ${kinds.includes("groundwater") ? html`<p class="legend-note">${t("stations.legend.groundwater_note")}</p>` : null}`;
  if (!featured) {
    return html`<ul class="legend-list two"><${KindItems} kinds=${kinds} source=${only} />${marks}</ul>${outlines}${note}`;
  }
  const restSource = rest.length && rest.every((id) => sourceClass(id) === "other") ? "other" : null;
  return html`<p class="legend-title">${t("stations.legend.featured", { provider: providerName(featured) })}</p>
    <ul class="legend-list two"><${KindItems} kinds=${kinds} source=${sourceClass(featured)} /></ul>
    ${rest.length
      ? html`<p class="legend-title">${t("stations.legend.others")}</p>
          <ul class="legend-list two"><${KindItems} kinds=${kinds} source=${restSource} opacity=${othersOpacity(scope)} size=${Number((14 * FADED_SIZE).toFixed(1))} /></ul>`
      : null}
    <ul class="legend-list two legend-marks">${marks}</ul>
    ${outlines}
    ${note}`;
}

/** The words of a snapshot of api/current ("states", "hydro", "meteo"), its name when unknown. */
function sourceName(name) {
  return has(`stations.source.${name}`) ? t(`stations.source.${name}`) : name;
}

function CurrentLegend({ current }) {
  const doc = current.doc;
  const snapshots = doc ? Object.entries(doc.snapshots) : [];
  const times = snapshots.map(([, snap]) => snap.fetched_at).filter(Boolean).sort();
  return html`
    <p class="legend-title">${t("stations.legend.hydro_title")}</p>
    <ul class="legend-list">
      ${HYDRO_STATES.map(
        (state) => html`<li key=${state.key}>
          <${SymbolIcon} shape="hydro" color=${state.color} size=${13} />
          ${state.ageing ? html`<${SymbolIcon} shape="hydro" color=${state.color} hollow=${true} size=${13} />` : html`<i class="legend-gap"></i>`}
          ${t(state.text)}
        </li>`,
      )}
    </ul>
    <p class="legend-note">${t("stations.legend.hydro_note")}</p>
    <p class="legend-title">${t("stations.legend.meteo_title")}</p>
    <ul class="legend-list">
      ${METEO_CLASSES.map(
        (entry) => html`<li key=${entry.key}>
          <${SymbolIcon} shape="meteo" color=${entry.color} size=${13} />${t(entry.text)}${entry.key === "high-precip" ? ` (≥ ${fmt(HEAVY_10_MIN, 1)} mm)` : ""}
        </li>`,
      )}
    </ul>
    <p class="legend-note">${t("stations.legend.meteo_note")}</p>
    <div class="legend-status" aria-live="polite">
      ${current.loading && !doc ? html`<p class="legend-note">${t("stations.legend.loading")}</p>` : null}
      ${doc && times.length
        ? html`<p class="legend-note">
            ${t("stations.legend.snapshot", {
              time: clock(times[times.length - 1]),
              hydro: tn("stations.legend.hydro_count", doc.hydro.length),
              meteo: tn("stations.legend.meteo_count", doc.meteo.length),
              minutes: fmt(REFRESH_MS / 60000),
            })}
          </p>`
        : null}
      ${snapshots
        .filter(([, snap]) => snap.error)
        .map(([name, snap]) => html`<p class="legend-note bad-text" key=${name}>${sourceName(name)}: ${snap.error}</p>`)}
      ${current.error
        ? html`<p class="legend-note bad-text">${current.error.message}${doc ? ` ${t("stations.legend.last_snapshot")}` : ""}</p>`
        : null}
    </div>`;
}

function PmaxtpLegend() {
  return html`<ul class="legend-list"><li><i class="pick-ring"></i>${t("stations.legend.pick")}</li></ul>
    <p class="legend-note">${t("stations.legend.pmaxtp_note", { bounds: boundsLabel() })}</p>`;
}

function Legend({ view, background, current, scope, fade, area, kinds, classes }) {
  // On a phone the legend starts folded: the map is small
  const [open, setOpen] = useState(() => !isPhone());
  return html`<div class=${`map-legend${open ? "" : " closed"}`}>
    <button type="button" class="legend-toggle" aria-expanded=${String(open)} onClick=${() => setOpen(!open)}>${t("stations.legend.title")}</button>
    ${open
      ? html`<div class="legend-body">
          ${view === "current" ? html`<${CurrentLegend} current=${current} />` : view === "pmaxtp" ? html`<${PmaxtpLegend} />` : html`<${StationsLegend} scope=${scope} fade=${fade} kinds=${kinds} classes=${classes} />`}
          ${area ? html`<ul class="legend-list legend-more"><li><i class="legend-area"></i>${t("stations.legend.area")}</li></ul>` : null}
          ${background === "borders" ? html`<p class="legend-note">${t("stations.legend.borders")}</p>` : null}
          ${background === "failed" ? html`<p class="legend-note">${t("stations.legend.basemap_failed")}</p>` : null}
        </div>`
      : null}
  </div>`;
}
