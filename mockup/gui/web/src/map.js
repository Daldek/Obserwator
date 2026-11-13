// The map (plan D9, D12): MapLibre GL JS 6 from vendor/ (its module worker is a same-origin
// file, so the CSP keeps `worker-src 'self'`), set up as Archiwista's map views are
// (Archiwista src/archiwista/web/src/maplibre.js, map/style.js): OpenFreeMap's vector tiles
// drawn in the GUI's own grey style, place names in the packaged glyphs, Polish where the
// tiles have them; when the basemap does not load, the borders of Poland and Czechia from
// Obserwator's package (data/*.geojson) are the background.
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
// The selected station is its symbol at 32 px, as on hydro.imgw.pl. A tooltip names the
// station and its latest values; a click selects it. Colours come from css/map.css
// (tokens), read again when the theme changes.
//
// Under the map, a strip carries the providers' lines and terms of the data the view draws
// (Nogat DEV §20, attribution.js). It never folds: MapLibre's compact attribution control,
// which collapses after the first drag, keeps the basemap's credit only.

import { Attribution } from "./attribution.js";
import { REFRESH_MS, clock, measuredAt } from "./current.js";
import { fmt, html, useEffect, useRef, useState } from "./lib.js";
import { PMAXTP_BOUNDS } from "./pmaxtp/state.js";
import { HYDRO_STATES, KIND_COLORS, METEO_CLASSES, SHAPES, SYMBOL_PX, SymbolIcon, drawSymbol, hydroState, meteoClass } from "./symbols.js";
import { isPhone } from "./ui/sheet.js";
import { useDark } from "./ui/theme.js";
import { KINDS, providerName } from "./words.js";

const VENDOR = new URL("../vendor/", import.meta.url);
const GLYPHS = `${new URL("glyphs/", VENDOR).href}{fontstack}/{range}.pbf`;
const GLYPH_FONT = "noto-sans-regular";
const BASEMAP_URL = "https://tiles.openfreemap.org/planet";
const BASEMAP_ATTRIBUTION = "OpenFreeMap © OpenMapTiles Data from OpenStreetMap";
const BORDERS = ["poland_border_wgs84.geojson", "czechia_border_wgs84.geojson"];
/** Poland and Czechia, the first view. */
const HOME = [
  [12.0, 48.4],
  [24.3, 55.0],
];
const EMPTY = { type: "FeatureCollection", features: [] };
/** The symbols are drawn at four times their size, so the selected one (2×) stays sharp. */
const ICON_RATIO = 4;
/** hydro.imgw.pl's 16 px from zoom 7 (where it opens), smaller over the whole of Poland and Czechia. */
const ICON_SIZE = ["interpolate", ["linear"], ["zoom"], 4, 0.6, 6, 0.8, 7, 1];
const SELECTED_SIZE = ["interpolate", ["linear"], ["zoom"], 4, 1.5, 7, 2];

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

// --- the basemap (after Archiwista's map/style.js) -------------------------------------

/**
 * The vector TileJSON of the basemap, its tiles checked to stay on its origin (the only one
 * the CSP allows besides the page's own).
 *
 * @returns {Promise<object>} a MapLibre vector source
 */
async function loadBasemapSource() {
  const response = await fetch(BASEMAP_URL);
  if (!response.ok) throw new Error(`TileJSON ${response.status}`);
  const doc = await response.json();
  if (!Array.isArray(doc.tiles) || !doc.tiles.length) throw new Error("TileJSON bez kafli");
  const origin = new URL(BASEMAP_URL).origin;
  const tiles = doc.tiles.map((tile) => {
    const url = new URL(String(tile), BASEMAP_URL);
    if (url.origin !== origin) throw new Error("kafle spoza adresu TileJSON");
    return url.href.replace(/%7B/gi, "{").replace(/%7D/gi, "}");
  });
  const { minzoom, maxzoom, bounds } = doc;
  return { type: "vector", tiles, minzoom, maxzoom, bounds, attribution: BASEMAP_ATTRIBUTION };
}

const NAME = ["coalesce", ["get", "name:pl"], ["get", "name:latin"], ["get", "name"]];
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
        "text-field": NAME,
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

function mapStyle(source, colors) {
  const style = {
    version: 8,
    glyphs: GLYPHS,
    sources: {},
    layers: [{ id: "background", type: "background", paint: { "background-color": source ? colors.bg : colors.water } }],
  };
  if (source) {
    style.sources.basemap = source;
    style.layers.push(...basemapLayers(colors));
  }
  return style;
}

/** Repaint the basemap and the borders in the theme's colours. */
function paintBasemap(map, colors, basemap) {
  map.setPaintProperty("background", "background-color", basemap ? colors.bg : colors.water);
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

/** The borders of Poland and Czechia from Obserwator's package: the background without a basemap. */
async function addBorders(map, colors) {
  if (map.getSource("borders")) return;
  const parts = await Promise.all(BORDERS.map((name) => fetch(new URL(`../data/${name}`, import.meta.url)).then((r) => r.json())));
  if (map.getSource("borders")) return;
  const data = { type: "FeatureCollection", features: parts.flatMap((part) => part.features || []) };
  map.addSource("borders", { type: "geojson", data, attribution: "Granice: pakiet Obserwatora" });
  const before = map.getLayer("stations") ? "stations" : undefined;
  map.addLayer({ id: "borders-fill", type: "fill", source: "borders", paint: { "fill-color": colors.land }, metadata: { fill: "land" } }, before);
  map.addLayer({ id: "borders-line", type: "line", source: "borders", paint: { "line-color": colors.border, "line-width": 1.4 }, metadata: { line: "border" } }, before);
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

/**
 * A station's symbol in the view „Stacje” as SVG, for the list and the legend: the map's drawing.
 *
 * @param {{kind: string, provider: string, data: boolean, active?: boolean, size?: number}} props
 */
export function StationSymbol({ kind, provider, data, active = true, size = 14 }) {
  const shape = kind === "meteo" ? "meteo" : "hydro";
  return html`<${SymbolIcon} shape=${shape} color=${KIND_COLORS[shape]} hollow=${!data} dashed=${provider === "CHMI"} faded=${!active} size=${size} className="st-sym" />`;
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

const LOCALE = {
  "Map.Title": "Mapa stacji",
  "NavigationControl.ZoomIn": "Przybliż",
  "NavigationControl.ZoomOut": "Oddal",
  "NavigationControl.ResetBearing": "Północ u góry",
  "AttributionControl.ToggleAttribution": "Pokaż lub ukryj źródła mapy",
};

/**
 * The map.
 *
 * @param {{stations: object[], byCode: Map<string, object>, selected: string|null,
 *   fly: {code: string, n: number}|null, view: "stations"|"current"|"pmaxtp",
 *   current: {doc: object|null, error: Error|null, loading: boolean},
 *   pick: {lat: number, lon: number}|null, pickFly: {n: number}|null,
 *   credits: {attribution: string[], terms_notice: string[]}|null,
 *   onSelect: (code: string) => void, onPick: (point: {lat: number, lon: number}) => void}} props
 *   the stations drawn in „Stacje” (already filtered), all stations by code (the tooltip),
 *   the selected one, a request to fly to a station, the view, the current measurements
 *   (current.js), the point picked for PMAXTP and a request to fly to it, the lines and
 *   terms of the data drawn, the selection's and the pick's handlers
 * @returns {object} the map with its legend and the providers' strip
 */
export function StationMap({ stations, byCode, selected, fly, view, current, pick, pickFly, credits, onSelect, onPick }) {
  const box = useRef(null);
  const mapRef = useRef(null);
  const handlers = useRef({});
  handlers.current = { onSelect, onPick, view };
  const [ready, setReady] = useState(false);
  const [failure, setFailure] = useState(null);
  const [basemap, setBasemap] = useState(true);
  const [tip, setTip] = useState(null);
  const dark = useDark();
  const rows = current.doc;

  useEffect(() => {
    let live = true;
    let map = null;
    Promise.all([
      import("../vendor/maplibre-gl/maplibre-gl.mjs"),
      loadBasemapSource().catch(() => null),
    ])
      .then(([maplibre, source]) => {
        if (!live) return;
        const colors = palette();
        if (!source) setBasemap(false);
        map = new maplibre.Map({
          container: box.current,
          style: mapStyle(source, colors),
          bounds: HOME,
          fitBoundsOptions: { padding: 16 },
          attributionControl: false,
          dragRotate: false,
          pitchWithRotate: false,
          touchPitch: false,
          maxPitch: 0,
          renderWorldCopies: false,
          locale: LOCALE,
        });
        map.touchZoomRotate.disableRotation();
        map.keyboard.disableRotation();
        map.addControl(new maplibre.AttributionControl({ compact: true }), "bottom-right");
        map.addControl(new maplibre.NavigationControl({ showCompass: false }), "bottom-right");
        map.on("error", (event) => {
          // Without a listener MapLibre logs to the console; a basemap that does not
          // answer gives way to the borders, said in the legend. Other errors (a glyph
          // range the package lacks) leave the map as it is.
          if (event.sourceId !== "basemap") return;
          setBasemap(false);
          if (map.isStyleLoaded()) addBorders(map, palette()).catch(() => {});
        });
        map.once("load", () => {
          if (!live) return;
          addLayers(map, colors);
          if (!source) addBorders(map, colors).catch(() => {});
          const show = (event) => {
            const feature = event.features && event.features[0];
            if (!feature) return;
            map.getCanvas().style.cursor = "pointer";
            setTip({ x: event.point.x, y: event.point.y, code: feature.properties.code, layer: feature.layer.id.startsWith("current") ? "current" : "stations" });
          };
          const hide = () => {
            map.getCanvas().style.cursor = handlers.current.view === "pmaxtp" ? "crosshair" : "";
            setTip(null);
          };
          for (const id of [...VIEW_LAYERS.stations, ...VIEW_LAYERS.current]) {
            map.on("mousemove", id, show);
            map.on("mouseleave", id, hide);
            map.on("click", id, (event) => {
              const feature = event.features && event.features[0];
              if (feature) handlers.current.onSelect(feature.properties.code);
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
      mapRef.current = null;
    };
  }, []);

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

  // Fly to a station chosen from the list
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
    paintBasemap(map, colors, basemap);
    repaintLayers(map, colors);
  }, [ready, dark]);

  let tipBody = null;
  if (tip && tip.layer === "current" && rows) {
    const hydro = rows.hydro.find((row) => row.code === tip.code);
    const meteo = hydro ? null : rows.meteo.find((row) => row.code === tip.code);
    if (hydro) tipBody = html`<${HydroTip} row=${hydro} station=${byCode.get(tip.code)} />`;
    else if (meteo) tipBody = html`<${MeteoTip} row=${meteo} station=${byCode.get(tip.code)} />`;
  } else if (tip && byCode.get(tip.code)) {
    tipBody = html`<${StationTip} station=${byCode.get(tip.code)} />`;
  }
  return html`<div class="map-wrap">
    <div class="map-stage">
      <div class="map" ref=${box} role="region" aria-label="Mapa stacji"></div>
      ${failure
        ? html`<div class="map-failure" role="status">
            <strong>Ta przeglądarka nie rysuje mapy</strong> (MapLibre: ${failure.message || String(failure)}). Lista stacji, panel stacji i formularz PMAXTP działają dalej.
          </div>`
        : null}
      ${tipBody ? html`<div class="map-tip" style=${{ left: `${tip.x}px`, top: `${tip.y}px` }} role="tooltip">${tipBody}</div>` : null}
      <${Legend} view=${view} basemap=${basemap} current=${current} />
    </div>
    ${credits ? html`<footer class="map-credits" aria-label="Źródła danych mapy"><${Attribution} fields=${credits} inline=${true} /></footer>` : null}
  </div>`;
}

function StationTip({ station }) {
  const years = station.first ? `${station.first}–${station.last}` : null;
  return html`
    <strong>${station.name || station.code}</strong>
    ${station.river ? html`<span>${station.river}</span>` : null}
    <span class="muted"><code>${station.code}</code> · ${providerName(station.provider)} · ${KINDS[station.kind] || station.kind}${station.active ? "" : " · nieczynna"}</span>
    <span class="muted">${years ? `szeregi ${years}` : "tylko w katalogu"}</span>
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
    <strong>${(station && station.name) || row.name}</strong>
    ${row.river ? html`<span>${row.river}</span>` : null}
    <span class="muted"><code>${row.code}</code> · IMGW-PIB · hydrologiczna</span>
    <span class="tip-class"><${SymbolIcon} shape="hydro" color=${state.color} hollow=${state.outdated} size=${13} />${state.label}${state.outdated ? " (stan z ostatnich 26 h)" : ""}</span>
    <${Reading} label="Stan wody H" value=${row.h} unit="cm" at=${row.h_at} />
    <${Reading} label="Przepływ Q" value=${row.q} digits=${row.q !== null && row.q < 10 ? 2 : 1} unit="m³/s" at=${row.q_at} />
    <${Reading} label="Temperatura wody" value=${row.t} digits=${1} unit="°C" at=${row.t_at} />
    ${row.h === null && row.q === null && row.t === null ? html`<span class="muted">IMGW-PIB nie podaje teraz pomiarów tej stacji.</span>` : null}
  `;
}

function MeteoTip({ row, station }) {
  const entry = meteoClass(row.p10);
  return html`
    <strong>${(station && station.name) || row.name}</strong>
    <span class="muted"><code>${row.code}</code> · IMGW-PIB · meteorologiczna</span>
    <span class="tip-class"><${SymbolIcon} shape="meteo" color=${entry.color} size=${13} />${entry.label}${entry.note ? ` (${entry.note})` : ""}</span>
    <${Reading} label="Opad w 10 min" value=${row.p10} digits=${1} unit="mm" />
    <${Reading} label="Temperatura powietrza" value=${row.t} digits=${1} unit="°C" at=${row.t_at} />
    <${Reading} label="Wiatr (średni)" value=${row.wind} digits=${1} unit="m/s" />
    <${Reading} label="Wilgotność względna" value=${row.rh} unit="%" />
  `;
}

function StationsLegend() {
  return html`<ul class="legend-list two">
      <li><${StationSymbol} kind="hydro" provider="IMGW-PIB" data=${true} />hydrologiczna</li>
      <li><${StationSymbol} kind="meteo" provider="IMGW-PIB" data=${true} />meteorologiczna</li>
      <li><${StationSymbol} kind="hydro" provider="IMGW-PIB" data=${false} />tylko w katalogu</li>
      <li><${StationSymbol} kind="hydro" provider="CHMI" data=${true} />ČHMÚ (obrys przerywany)</li>
      <li><${StationSymbol} kind="hydro" provider="IMGW-PIB" data=${true} active=${false} />nieczynna (blado)</li>
      <li><${StationSymbol} kind="hydro" provider="IMGW-PIB" data=${true} size=${24} />wybrana</li>
    </ul>
    <p class="legend-note">Kształty i kolory stacji jak na mapie hydro.imgw.pl (IMGW-PIB); stan wody i opad pokazuje widok „Pomiary bieżące”.</p>`;
}

function CurrentLegend({ current }) {
  const doc = current.doc;
  const snapshots = doc ? Object.values(doc.snapshots) : [];
  const times = snapshots.map((snap) => snap.fetched_at).filter(Boolean).sort();
  const errors = [...new Set(snapshots.map((snap) => snap.error).filter(Boolean))];
  return html`
    <p class="legend-title">Stacje hydrologiczne: stan wody</p>
    <ul class="legend-list">
      ${HYDRO_STATES.map(
        (state) => html`<li>
          <${SymbolIcon} shape="hydro" color=${state.color} size=${13} />
          ${state.ageing ? html`<${SymbolIcon} shape="hydro" color=${state.color} hollow=${true} size=${13} />` : html`<i class="legend-gap"></i>`}
          ${state.label}
        </li>`,
      )}
    </ul>
    <p class="legend-note">Pełny: stan z pomiarów ostatnich 2 godzin; pusty środek: z ostatnich 26 godzin.</p>
    <p class="legend-title">Stacje meteorologiczne: opad w 10 min</p>
    <ul class="legend-list">
      ${METEO_CLASSES.map((entry) => html`<li><${SymbolIcon} shape="meteo" color=${entry.color} size=${13} />${entry.label}${entry.key === "high-precip" ? " (≥ 3,2 mm)" : ""}</li>`)}
    </ul>
    <p class="legend-note">Symbole i kolory jak na hydro.imgw.pl, które klasyfikuje opad z 6 godzin; Obserwator ma tylko ostatnią sumę 10-minutową. Intensywny: co najmniej silny deszcz w skali Chomicza.</p>
    <p class="legend-note">
      ${current.loading && !doc ? "Pobieram pomiary bieżące z IMGW-PIB…" : null}
      ${doc && times.length
        ? `Migawka IMGW-PIB z ${clock(times[times.length - 1])}: ${fmt(doc.hydro.length)} stacji hydrologicznych, ${fmt(doc.meteo.length)} meteorologicznych; odświeżana co ${REFRESH_MS / 60000} min, niezapisywana.`
        : null}
      ${errors.map((error) => html`<br /><span class="bad-text">${error}</span>`)}
      ${current.error ? html`<br /><span class="bad-text">${current.error.message}${doc ? " (pokazuję ostatnią migawkę)" : ""}</span>` : null}
    </p>`;
}

function PmaxtpLegend() {
  return html`<ul class="legend-list"><li><i class="pick-ring"></i>punkt PMAXTP</li></ul>
    <p class="legend-note">Kliknij mapę w granicach PMAXTP (${fmt(PMAXTP_BOUNDS.lat[0])}–${fmt(PMAXTP_BOUNDS.lat[1])}° N, ${fmt(PMAXTP_BOUNDS.lon[0])}–${fmt(PMAXTP_BOUNDS.lon[1], 1)}° E). Mapa nie rysuje siatki PMAXTP.</p>`;
}

function Legend({ view, basemap, current }) {
  // On a phone the legend starts folded: the map is small
  const [open, setOpen] = useState(() => !isPhone());
  return html`<div class=${`map-legend${open ? "" : " closed"}`}>
    <button type="button" class="legend-toggle" aria-expanded=${open} onClick=${() => setOpen(!open)}>Legenda</button>
    ${open
      ? html`<div class="legend-body">
          ${view === "current" ? html`<${CurrentLegend} current=${current} />` : view === "pmaxtp" ? html`<${PmaxtpLegend} />` : html`<${StationsLegend} />`}
          ${basemap ? null : html`<p class="legend-note">Podkład OpenFreeMap niedostępny: tło to granice Polski i Czech z pakietu Obserwatora.</p>`}
        </div>`
      : null}
  </div>`;
}
