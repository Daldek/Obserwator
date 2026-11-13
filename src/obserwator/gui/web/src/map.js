// The map (plan D9, D12): MapLibre GL JS 6 from vendor/ (its module worker is a same-origin
// file, so the CSP keeps `worker-src 'self'`), set up as Archiwista's map views are
// (Archiwista src/archiwista/web/src/maplibre.js, map/style.js): the deployment's basemap
// (`basemap` of api/session: a TileJSON, OpenFreeMap's by default) drawn in the GUI's own
// grey style, place names in the packaged glyphs, in the page's language where the tiles
// have it (Polish by default, `name:pl`); without a basemap, or when its tiles do not load,
// the borders of Poland and Czechia from Obserwator's package (data/*.geojson, Natural
// Earth) are the background.
//
// The three views of main.js share it, each with only its own layer:
// - „Stacje”: every located station of the catalogs in hydro.imgw.pl's symbols
//   (symbols.js): a triangle for a hydrological station, a circle for a meteorological
//   one, in the colours hydro.imgw.pl gives a station of each kind in its legend; a hollow
//   centre when the station is only in the catalog, a dashed outline for ČHMÚ, inactive
//   ones faded;
// - „Pomiary bieżące”: only IMGW-PIB's current measurements (api/current through
//   current.js), hydrological stations filled by their water state and meteorological ones
//   by their precipitation, as hydro.imgw.pl fills them;
// - „PMAXTP”: no station and no layer of the PMAXTP grid, only the point picked by a click.
// The selected station is its symbol at 32 px, as on hydro.imgw.pl. No text labels: a
// tooltip names the station and its latest values with their times; a click selects it.
// Colours come from css/map.css (tokens), read again when the theme changes.
//
// The basemap's credit goes to the view's one strip under the map and the panels
// (`onCredit`, main.js), with the providers' lines (Nogat DEV-20.5). It never folds:
// MapLibre's own attribution control, which collapses after the first drag, is left out.
// The zoom buttons are the page's own, so their names follow the page's language. The
// map's element keeps the MapLibre map as `maplibre`, for a test or a console asking what
// is drawn.

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
  meteoClass,
} from "./symbols.js";
import { isPhone } from "./ui/sheet.js";
import { useDark } from "./ui/theme.js";
import { kindName, providerName } from "./words.js";

const VENDOR = new URL("../vendor/", import.meta.url);
const GLYPHS = `${new URL("glyphs/", VENDOR).href}{fontstack}/{range}.pbf`;
const GLYPH_FONT = "noto-sans-regular";
const BORDERS = ["poland_border_wgs84.geojson", "czechia_border_wgs84.geojson"];
/** Poland and Czechia, the first view. */
const HOME = [
  [12.0, 48.4],
  [24.3, 55.0],
];
const EMPTY = { type: "FeatureCollection", features: [] };
/** The lowest layer of the stations: the background (basemap or borders) goes under it. */
const OVERLAY = "stations";
/** The symbols are drawn at four times their size, so the selected one (2×) stays sharp. */
const ICON_RATIO = 4;
/** hydro.imgw.pl's 16 px from zoom 7 (where it opens), smaller over the whole of Poland and Czechia. */
const ICON_SIZE = ["interpolate", ["linear"], ["zoom"], 4, 0.6, 6, 0.8, 7, 1];
const SELECTED_SIZE = ["interpolate", ["linear"], ["zoom"], 4, 1.5, 7, 2];
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
    "halo", "place-1", "place-2", "place-3", "place-4", "border",
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
  const parts = await Promise.all(BORDERS.map((name) => fetch(new URL(`../data/${name}`, import.meta.url)).then((r) => r.json())));
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

/** The image of a station in the view „Stacje”. */
function stationIcon(kind, provider, data) {
  return `st-${kind === "meteo" ? "meteo" : "hydro"}-${provider === "CHMI" ? "chmi" : "imgw"}-${data ? 1 : 0}`;
}

/** Every image the map draws: its name and look. */
function looks() {
  const out = [];
  for (const kind of ["hydro", "meteo"]) {
    for (const provider of ["IMGW-PIB", "CHMI"]) {
      for (const data of [true, false]) {
        out.push({ name: stationIcon(kind, provider, data), shape: kind, color: KIND_COLORS[kind], hollow: !data, dashed: provider === "CHMI" });
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

function stationFeatures(stations) {
  const features = [];
  for (const station of stations) {
    if (station.lon === null || station.lat === null) continue;
    const data = station.datasets.length > 0;
    features.push(
      point(station.lon, station.lat, {
        code: station.code,
        icon: stationIcon(station.kind, station.provider, data),
        active: station.active ? 1 : 0,
        rank: (data ? 2 : 0) + (station.active ? 1 : 0),
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
/** The layers of each view; every other layer of these is hidden. */
const VIEW_LAYERS = {
  stations: ["stations", "stations-selected"],
  current: ["current", "current-selected"],
  pmaxtp: ["pmaxtp-ring", "pmaxtp-dot"],
};

function addLayers(map, colors) {
  drawImages(map);
  map.addSource("stations", { type: "geojson", data: EMPTY });
  map.addSource("current", { type: "geojson", data: EMPTY });
  map.addSource("pmaxtp", { type: "geojson", data: EMPTY });
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
  map.addLayer(symbols("stations", "stations", { paint: { "icon-opacity": ["case", ["==", ["get", "active"], 1], 1, 0.5] } }));
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
 * @param {{stations: object[], byCode: Map<string, object>, selected: string|null,
 *   fly: {code: string, n: number}|null, view: "stations"|"current"|"pmaxtp",
 *   current: {doc: object|null, error: Error|null, loading: boolean},
 *   pick: {lat: number, lon: number}|null, pickFly: {n: number}|null,
 *   onCredit: (credit: string|null) => void, session: object|null,
 *   onSelect: (code: string) => void, onPick: (point: {lat: number, lon: number}) => void}} props
 *   the stations drawn in „Stacje” (already filtered), all stations by code (the tooltip),
 *   the selected one, a request to fly to a station, the view, the current measurements
 *   (current.js), the point picked for PMAXTP and a request to fly to it, where the
 *   basemap's credit goes while the basemap is drawn, api/session (null until it answers:
 *   its `basemap`), the selection's and the pick's handlers
 * @returns {object} the map with its legend and its zoom buttons
 */
export function StationMap({ stations, byCode, selected, fly, view, current, pick, pickFly, onCredit, session, onSelect, onPick }) {
  const box = useRef(null);
  const mapRef = useRef(null);
  const handlers = useRef({});
  handlers.current = { onSelect, onPick, view };
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

  useEffect(() => {
    let live = true;
    let map = null;
    const element = box.current;
    import("../vendor/maplibre-gl/maplibre-gl.mjs")
      .then((maplibre) => {
        if (!live) return;
        const colors = palette();
        map = new maplibre.Map({
          container: element,
          style: { version: 8, glyphs: GLYPHS, sources: {}, layers: [{ id: "background", type: "background", paint: { "background-color": colors.bg } }] },
          bounds: HOME,
          fitBoundsOptions: { padding: 16 },
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
    const borders = (state) => {
      setBackground(state);
      addBorders(map, palette()).catch((error) => console.warn(error));
    };
    const onData = (event) => {
      if (event.sourceId === "basemap" && event.tile) loaded = true;
    };
    // A basemap none of whose tiles loads (offline, blocked) gives way to the borders;
    // a single failing tile of a basemap that loads does not
    const onError = (event) => {
      if (!live || loaded || event.sourceId !== "basemap") return;
      live = false;
      removeBasemap(map);
      borders("failed");
    };
    if (basemapUrl === null) {
      borders("borders");
    } else {
      map.on("data", onData);
      map.on("error", onError);
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
    };
  }, [ready, basemapUrl]);

  // The view: only its own layers are shown
  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map) return;
    for (const [name, ids] of Object.entries(VIEW_LAYERS)) {
      for (const id of ids) map.setLayoutProperty(id, "visibility", name === view ? "visible" : "none");
    }
    map.getCanvas().style.cursor = view === "pmaxtp" ? "crosshair" : "";
    setTip(null);
  }, [ready, view]);

  // The stations of „Stacje”
  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map) return;
    map.getSource("stations").setData(stationFeatures(stations));
  }, [ready, stations]);

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
    map.flyTo({ center: [station.lon, station.lat], zoom: Math.max(map.getZoom(), 9), duration: 900 });
  }, [ready, fly, byCode]);

  // Fly to a PMAXTP point typed in the form
  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map || !pickFly || !pick) return;
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
      <${Legend} view=${view} background=${background} current=${current} />
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

function StationTip({ station }) {
  const facts = [providerName(station.provider), kindName(station.kind), station.active ? null : t("stations.inactive")].filter(Boolean);
  return html`
    <strong>${station.name || station.code}</strong>
    ${station.river ? html`<span>${station.river}</span>` : null}
    <span class="muted"><code>${station.code}</code> · ${facts.join(" · ")}</span>
    <span class="muted">${station.first ? t("stations.tip.series", { years: `${station.first}–${station.last}` }) : t("stations.catalog_only")}</span>
  `;
}

/** A value with its unit and the time of its measurement, or nothing without a value. */
function Reading({ label, value, digits = 0, unit, at }) {
  if (value === null || value === undefined) return null;
  return html`<span class="tip-value">${label}: <strong>${fmt(value, digits)} ${unit}</strong>${at ? html` <span class="muted">${measuredAt(at)}</span>` : null}</span>`;
}

function HydroTip({ row, station }) {
  const state = hydroState(row.state);
  return html`
    <strong>${(station && station.name) || row.name || row.code}</strong>
    ${row.river ? html`<span>${row.river}</span>` : null}
    <span class="muted"><code>${row.code}</code> · ${providerName("IMGW-PIB")} · ${kindName("hydro")}</span>
    <span class="tip-class"><${SymbolIcon} shape="hydro" color=${state.color} hollow=${state.outdated} size=${13} />${state.label}${state.outdated ? ` ${t("stations.tip.outdated")}` : ""}</span>
    <${Reading} label=${t("stations.tip.water_level")} value=${row.h} unit="cm" at=${row.h_at} />
    <${Reading} label=${t("stations.tip.discharge")} value=${row.q} digits=${row.q !== null && row.q < 10 ? 2 : 1} unit="m³/s" at=${row.q_at} />
    <${Reading} label=${t("stations.tip.water_temperature")} value=${row.t} digits=${1} unit="°C" at=${row.t_at} />
    ${row.h === null && row.q === null && row.t === null ? html`<span class="muted">${t("stations.tip.no_values")}</span>` : null}
  `;
}

function MeteoTip({ row, station }) {
  const entry = meteoClass(row.p10);
  return html`
    <strong>${(station && station.name) || row.name || row.code}</strong>
    <span class="muted"><code>${row.code}</code> · ${providerName("IMGW-PIB")} · ${kindName("meteo")}</span>
    <span class="tip-class"><${SymbolIcon} shape="meteo" color=${entry.color} size=${13} />${entry.label}${entry.note ? ` (${entry.note})` : ""}</span>
    <${Reading} label=${t("stations.tip.precipitation")} value=${row.p10} digits=${1} unit="mm" />
    <${Reading} label=${t("stations.tip.air_temperature")} value=${row.t} digits=${1} unit="°C" at=${row.t_at} />
    <${Reading} label=${t("stations.tip.wind")} value=${row.wind} digits=${1} unit="m/s" />
    <${Reading} label=${t("stations.tip.humidity")} value=${row.rh} unit="%" />
  `;
}

function StationsLegend() {
  return html`<ul class="legend-list two">
      <li><${StationSymbol} kind="hydro" provider="IMGW-PIB" data=${true} />${kindName("hydro")}</li>
      <li><${StationSymbol} kind="meteo" provider="IMGW-PIB" data=${true} />${kindName("meteo")}</li>
      <li><${StationSymbol} kind="hydro" provider="IMGW-PIB" data=${false} />${t("stations.catalog_only")}</li>
      <li><${StationSymbol} kind="hydro" provider="CHMI" data=${true} />${t("stations.legend.chmi", { provider: providerName("CHMI") })}</li>
      <li><${StationSymbol} kind="hydro" provider="IMGW-PIB" data=${true} active=${false} />${t("stations.legend.inactive")}</li>
      <li><${StationSymbol} kind="hydro" provider="IMGW-PIB" data=${true} size=${24} />${t("stations.legend.selected")}</li>
    </ul>
    <p class="legend-note">${t("stations.legend.stations_note")}</p>`;
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

function Legend({ view, background, current }) {
  // On a phone the legend starts folded: the map is small
  const [open, setOpen] = useState(() => !isPhone());
  return html`<div class=${`map-legend${open ? "" : " closed"}`}>
    <button type="button" class="legend-toggle" aria-expanded=${String(open)} onClick=${() => setOpen(!open)}>${t("stations.legend.title")}</button>
    ${open
      ? html`<div class="legend-body">
          ${view === "current" ? html`<${CurrentLegend} current=${current} />` : view === "pmaxtp" ? html`<${PmaxtpLegend} />` : html`<${StationsLegend} />`}
          ${background === "borders" ? html`<p class="legend-note">${t("stations.legend.borders")}</p>` : null}
          ${background === "failed" ? html`<p class="legend-note">${t("stations.legend.basemap_failed")}</p>` : null}
        </div>`
      : null}
  </div>`;
}
