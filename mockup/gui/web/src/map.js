// The map of the stations (plan D9): MapLibre GL JS 6 from vendor/ (its module worker is a
// same-origin file, so the CSP keeps `worker-src 'self'`), set up as Archiwista's map views
// are (Archiwista src/archiwista/web/src/maplibre.js, map/style.js): OpenFreeMap's vector
// tiles drawn in the GUI's own grey style, place names in the packaged glyphs, Polish where
// the tiles have them; when the basemap does not load, the borders of Poland and Czechia
// from Obserwator's package (data/*.geojson) are the background.
//
// Every located station of the catalogs is a symbol: a circle for a hydrological station, a
// square for a meteorological one (shape and colour), a solid outline for IMGW-PIB and a
// dashed one for ČHMÚ, filled when the store holds its series and hollow when it is only in
// the catalog, inactive ones faded; the selected one is ringed. A tooltip names the station;
// a click selects it. The layer „Stan wody (IMGW-PIB)” colours IMGW-PIB's hydro stations by
// the water state of the server's snapshot (api/current), today's /map page of Obserwator.
// Colours come from css/map.css (tokens), read again when the theme changes.

import { api } from "./api.js";
import { html, useEffect, useRef, useState } from "./lib.js";
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
const ICON_PX = 16;
const ICON_RATIO = 2;

/** The water states of IMGW-PIB's map, grouped as the legend names them. */
export const WATER_STATES = [
  ["alarm", "alarmowy"],
  ["warning", "ostrzegawczy"],
  ["high", "wysoki"],
  ["medium", "średni"],
  ["low", "niski"],
  ["unknown", "brak oceny stanu"],
];
const STATE_GROUP = {
  alarm: "alarm",
  warning: "warning",
  high: "high",
  medium: "medium",
  normal: "medium",
  low: "low",
  below: "low",
};

/**
 * The legend's group of an IMGW-PIB water state and whether it is outdated.
 *
 * @param {string|null} state e.g. "lowOutdated", "no-water-state-data"
 * @returns {{group: string, outdated: boolean, label: string}}
 */
export function waterState(state) {
  const raw = String(state || "unknown");
  const outdated = raw.endsWith("Outdated");
  const group = STATE_GROUP[outdated ? raw.slice(0, -8) : raw] || "unknown";
  const label = (WATER_STATES.find(([key]) => key === group) || [null, "brak oceny stanu"])[1];
  return { group, outdated, label: outdated ? `${label} (nieaktualny)` : label };
}

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
  for (const name of ["hydro", "meteo", "ink", "hollow"]) out[`st-${name}`] = cssColor(`--st-${name}`);
  for (const [key] of WATER_STATES) out[`ws-${key}`] = cssColor(`--ws-${key}`);
  out.accent = cssColor("--accent");
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

// --- the station symbols ------------------------------------------------------------------

/** The outline of a symbol in a square of `side`: a circle (hydro) or a square (meteo). */
function shapePath(kind, side, data) {
  const mid = side / 2;
  if (kind === "meteo") {
    const half = side * (data ? 0.3 : 0.25);
    return `M${mid - half} ${mid - half}H${mid + half}V${mid + half}H${mid - half}Z`;
  }
  const r = side * (data ? 0.34 : 0.28);
  return `M${mid - r} ${mid}a${r} ${r} 0 1 0 ${2 * r} 0a${r} ${r} 0 1 0 ${-2 * r} 0`;
}

/** Fill, outline and dashes of a station's symbol. */
function symbolStyle(colors, kind, provider, data) {
  const color = colors[`st-${kind === "meteo" ? "meteo" : "hydro"}`];
  return {
    fill: data ? color : colors["st-hollow"],
    stroke: data ? colors["st-ink"] : color,
    width: data ? 1.4 : 1.8,
    dash: provider === "CHMI" ? [2.2, 1.6] : null,
  };
}

/** The image name of a station. */
function iconName(kind, provider, data) {
  return `${kind === "meteo" ? "meteo" : "hydro"}-${provider === "CHMI" ? "chmi" : "imgw"}-${data ? 1 : 0}`;
}

/** Draw (or redraw for a theme) the eight images of the station symbols. */
function drawStationImages(map, colors) {
  const side = ICON_PX * ICON_RATIO;
  const canvas = document.createElement("canvas");
  canvas.width = side;
  canvas.height = side;
  const context = canvas.getContext("2d", { willReadFrequently: true });
  for (const kind of ["hydro", "meteo"]) {
    for (const provider of ["IMGW-PIB", "CHMI"]) {
      for (const data of [true, false]) {
        const style = symbolStyle(colors, kind, provider, data);
        const path = new Path2D(shapePath(kind, side, data));
        context.clearRect(0, 0, side, side);
        context.fillStyle = style.fill;
        context.fill(path);
        context.lineWidth = style.width * ICON_RATIO;
        context.strokeStyle = style.stroke;
        context.setLineDash(style.dash ? style.dash.map((d) => d * ICON_RATIO) : []);
        context.stroke(path);
        const name = iconName(kind, provider, data);
        const image = context.getImageData(0, 0, side, side);
        if (map.hasImage(name)) map.updateImage(name, image);
        else map.addImage(name, image, { pixelRatio: ICON_RATIO });
      }
    }
  }
}

/**
 * A station's symbol as SVG, for the list and the legend: the map's drawing.
 *
 * @param {{kind: string, provider: string, data: boolean, size?: number}} props
 */
export function StationSymbol({ kind, provider, data, size = 14 }) {
  const side = 16;
  const cls = `st-sym ${kind === "meteo" ? "meteo" : "hydro"} ${provider === "CHMI" ? "chmi" : "imgw"} ${data ? "data" : "catalog"}`;
  return html`<svg class=${cls} width=${size} height=${size} viewBox="0 0 16 16" aria-hidden="true">
    <path d=${shapePath(kind, side, data)} />
  </svg>`;
}

function stationFeatures(stations) {
  const features = [];
  for (const station of stations) {
    if (station.lon === null || station.lat === null) continue;
    const data = station.datasets.length > 0;
    features.push({
      type: "Feature",
      geometry: { type: "Point", coordinates: [station.lon, station.lat] },
      properties: {
        code: station.code,
        icon: iconName(station.kind, station.provider, data),
        data: data ? 1 : 0,
        active: station.active ? 1 : 0,
      },
    });
  }
  return { type: "FeatureCollection", features };
}

function stateFeatures(doc) {
  const features = [];
  for (const item of doc.stations) {
    if (item.lon === null || item.lat === null) continue;
    const state = waterState(item.state);
    features.push({
      type: "Feature",
      geometry: { type: "Point", coordinates: [item.lon, item.lat] },
      properties: { code: item.code, group: state.group, outdated: state.outdated, label: state.label, name: item.name, river: item.river || "" },
    });
  }
  return { type: "FeatureCollection", features };
}

function stateColor(colors) {
  const pairs = WATER_STATES.flatMap(([key]) => [key, colors[`ws-${key}`]]);
  return ["match", ["get", "group"], ...pairs.slice(0, -2), colors["ws-unknown"]];
}

function addStationLayers(map, colors) {
  drawStationImages(map, colors);
  map.addSource("stations", { type: "geojson", data: EMPTY });
  map.addSource("states", { type: "geojson", data: EMPTY });
  map.addLayer({
    id: "stations",
    type: "symbol",
    source: "stations",
    layout: {
      "icon-image": ["get", "icon"],
      "icon-allow-overlap": true,
      "icon-ignore-placement": true,
      "icon-size": ["interpolate", ["linear"], ["zoom"], 4, 0.68, 8, 0.95, 12, 1.25],
      "symbol-sort-key": ["+", ["*", 2, ["get", "data"]], ["get", "active"]],
    },
    paint: { "icon-opacity": ["case", ["==", ["get", "active"], 1], 1, 0.55] },
  });
  map.addLayer({
    id: "states",
    type: "circle",
    source: "states",
    layout: { visibility: "none", "circle-sort-key": ["match", ["get", "group"], "alarm", 5, "warning", 4, "high", 3, "medium", 2, "low", 1, 0] },
    paint: {
      "circle-radius": ["interpolate", ["linear"], ["zoom"], 4, 3.6, 8, 5.5, 12, 7.5],
      "circle-color": stateColor(colors),
      "circle-opacity": ["case", ["get", "outdated"], 0.45, 1],
      "circle-stroke-color": colors["st-ink"],
      "circle-stroke-width": 1,
      "circle-stroke-opacity": ["case", ["get", "outdated"], 0.5, 1],
    },
  });
  map.addLayer({
    id: "selected",
    type: "circle",
    source: "stations",
    filter: ["==", ["get", "code"], ""],
    paint: {
      "circle-radius": ["interpolate", ["linear"], ["zoom"], 4, 9, 12, 13],
      "circle-color": "rgba(0, 0, 0, 0)",
      "circle-stroke-color": colors.accent,
      "circle-stroke-width": 3,
    },
  });
}

function repaintStations(map, colors) {
  drawStationImages(map, colors);
  map.setPaintProperty("states", "circle-color", stateColor(colors));
  map.setPaintProperty("states", "circle-stroke-color", colors["st-ink"]);
  map.setPaintProperty("selected", "circle-stroke-color", colors.accent);
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
 *   fly: {code: string, n: number}|null, layer: "stations"|"states",
 *   onSelect: (code: string) => void}} props the stations drawn (already filtered), all
 *   stations by code (the tooltip), the selected one, a request to fly to a station, the
 *   layer shown and the selection's handler
 * @returns {object} the map with its legend
 */
export function StationMap({ stations, byCode, selected, fly, layer, onSelect }) {
  const box = useRef(null);
  const mapRef = useRef(null);
  const handlers = useRef({});
  handlers.current = { onSelect, byCode, layer };
  const [ready, setReady] = useState(false);
  const [failure, setFailure] = useState(null);
  const [basemap, setBasemap] = useState(true);
  const [tip, setTip] = useState(null);
  const [states, setStates] = useState({ doc: null, error: null, loading: false, at: 0 });
  const dark = useDark();

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
          addStationLayers(map, colors);
          if (!source) addBorders(map, colors).catch(() => {});
          const show = (event) => {
            const feature = event.features && event.features[0];
            if (!feature) return;
            map.getCanvas().style.cursor = "pointer";
            setTip({ x: event.point.x, y: event.point.y, code: feature.properties.code, label: feature.layer.id === "states" ? feature.properties.label : null });
          };
          const hide = () => {
            map.getCanvas().style.cursor = "";
            setTip(null);
          };
          for (const id of ["stations", "states"]) {
            map.on("mousemove", id, show);
            map.on("mouseleave", id, hide);
            map.on("click", id, (event) => {
              const feature = event.features && event.features[0];
              if (feature) handlers.current.onSelect(feature.properties.code);
            });
          }
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

  // The stations drawn
  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map) return;
    map.getSource("stations").setData(stationFeatures(stations));
  }, [ready, stations]);

  // The selected ring
  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map) return;
    map.setFilter("selected", ["==", ["get", "code"], selected || ""]);
  }, [ready, selected]);

  // Fly to a station chosen from the list
  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map || !fly) return;
    const station = byCode.get(fly.code);
    if (!station || station.lon === null) return;
    map.flyTo({ center: [station.lon, station.lat], zoom: Math.max(map.getZoom(), 9), duration: 900 });
  }, [ready, fly, byCode]);

  // The theme's colours
  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map) return;
    const colors = palette();
    paintBasemap(map, colors, basemap);
    repaintStations(map, colors);
  }, [ready, dark]);

  // The layer of water states: fetched when shown, again after ten minutes
  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map) return;
    const on = layer === "states";
    map.setLayoutProperty("states", "visibility", on ? "visible" : "none");
    map.setPaintProperty("stations", "icon-opacity", on ? 0.3 : ["case", ["==", ["get", "active"], 1], 1, 0.55]);
    if (!on || states.loading || (states.doc && Date.now() - states.at < 600000)) return;
    let live = true;
    setStates((old) => ({ ...old, loading: true }));
    api.get("api/current", { layer: "states" }, { memo: false }).then(
      (doc) => {
        if (!live) return;
        map.getSource("states").setData(stateFeatures(doc));
        setStates({ doc, error: null, loading: false, at: Date.now() });
      },
      (error) => live && setStates((old) => ({ ...old, error, loading: false, at: Date.now() })),
    );
    return () => {
      live = false;
    };
  }, [ready, layer]);

  const tipStation = tip ? byCode.get(tip.code) : null;
  return html`<div class="map-wrap">
    <div class="map" ref=${box} role="region" aria-label="Mapa stacji"></div>
    ${failure
      ? html`<div class="map-failure" role="status">
          <strong>Ta przeglądarka nie rysuje mapy</strong> (MapLibre: ${failure.message || String(failure)}). Lista stacji i panel stacji działają dalej.
        </div>`
      : null}
    ${tip && tipStation ? html`<${Tip} tip=${tip} station=${tipStation} />` : null}
    <${Legend} layer=${layer} basemap=${basemap} states=${states} />
  </div>`;
}

function Tip({ tip, station }) {
  const years = station.first ? `${station.first}–${station.last}` : null;
  return html`<div class="map-tip" style=${{ left: `${tip.x}px`, top: `${tip.y}px` }} role="tooltip">
    <strong>${station.name || station.code}</strong>
    ${station.river ? html`<span>${station.river}</span>` : null}
    <span class="muted"><code>${station.code}</code> · ${providerName(station.provider)} · ${KINDS[station.kind] || station.kind}</span>
    ${tip.label ? html`<span class="tip-state">Stan wody: ${tip.label}</span>` : null}
    <span class="muted">${years ? `szeregi ${years}` : "tylko w katalogu"}</span>
  </div>`;
}

function Legend({ layer, basemap, states }) {
  // On a phone the legend starts folded: the map is small
  const [open, setOpen] = useState(() => !isPhone());
  const time = states.doc && states.doc.fetched_at ? new Date(states.doc.fetched_at) : null;
  return html`<div class=${`map-legend${open ? "" : " closed"}`}>
    <button type="button" class="legend-toggle" aria-expanded=${open} onClick=${() => setOpen(!open)}>Legenda</button>
    ${open
      ? html`<div class="legend-body">
          ${layer === "states"
            ? html`<ul class="legend-list">
                  ${WATER_STATES.map(([key, label]) => html`<li><i class=${`ws-dot ${key}`}></i>${label}</li>`)}
                  <li><i class="ws-dot medium old"></i>blado: pomiar nieaktualny</li>
                </ul>
                <p class="legend-note">
                  ${states.loading ? "Pobieram stany wody z IMGW-PIB…" : null}
                  ${time ? `Stany wody IMGW-PIB z ${time.toLocaleTimeString("pl-PL", { hour: "2-digit", minute: "2-digit" })}` : null}
                  ${states.doc && states.doc.error ? html`<br /><span class="bad-text">${states.doc.error}</span>` : null}
                  ${states.error ? html`<span class="bad-text">${states.error.message}</span>` : null}
                </p>`
            : html`<ul class="legend-list two">
                <li><${StationSymbol} kind="hydro" provider="IMGW-PIB" data=${true} />hydrologiczna</li>
                <li><${StationSymbol} kind="meteo" provider="IMGW-PIB" data=${true} />meteorologiczna</li>
                <li><${StationSymbol} kind="hydro" provider="IMGW-PIB" data=${true} />z szeregami</li>
                <li><${StationSymbol} kind="hydro" provider="IMGW-PIB" data=${false} />tylko katalog</li>
                <li><${StationSymbol} kind="hydro" provider="IMGW-PIB" data=${true} />IMGW-PIB: obrys ciągły</li>
                <li><${StationSymbol} kind="hydro" provider="CHMI" data=${true} />ČHMÚ: obrys przerywany</li>
                <li><i class="sel-ring"></i>wybrana</li>
                <li><i class="faded-dot"></i>blado: nieczynna</li>
              </ul>`}
          ${basemap ? null : html`<p class="legend-note">Podkład OpenFreeMap niedostępny: tło to granice Polski i Czech z pakietu Obserwatora.</p>`}
        </div>`
      : null}
  </div>`;
}
