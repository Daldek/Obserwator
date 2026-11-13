// The sections of a meteorological station (Nogat plan M1 to M15), in the panel's order.
// Each: {id, title, component, available} where `title` is the catalog key of the card's
// header, component({station, session, analyses}) renders the section and
// available(station, ids) says whether the analysis ids of the station (`api/analyses`, a
// Set) include one the section shows: a station without precipitation has no „Opady”, one
// without temperature no „Temperatura”, a ČHMÚ station no „Śnieg”.

import { Opady } from "./opady.js";
import { Snieg } from "./snieg.js";
import { Susze } from "./susze.js";
import { Temperatura } from "./temperatura.js";
import { Trendy } from "./trendy.js";
import { hasAny } from "./util.js";

const PRECIPITATION = [
  "precipitation.sums",
  "precipitation.seasonality",
  "precipitation.days",
  "precipitation.intensity",
  "precipitation.heavy",
  "precipitation.maxima",
  "precipitation_quantiles",
];
const DROUGHT = ["spells.dry", "spells.wet", "spi"];
const TEMPERATURE = ["temperature.means", "temperature.days", "temperature.degree_days", "temperature.range", "harmonics.Tmean", "hydrothermal"];

/** The trends of meteorological series: Mann–Kendall of precipitation, spells and temperature. */
const meteoTrend = (id) => id.startsWith("mann_kendall.precipitation.") || id === "mann_kendall.spells.dry" || id.startsWith("mann_kendall.temperature.");

export const METEO_SECTIONS = [
  { id: "opady", title: "meteo.title.opady", component: Opady, available: (station, ids) => hasAny(ids, PRECIPITATION) },
  { id: "susze", title: "meteo.title.susze", component: Susze, available: (station, ids) => hasAny(ids, DROUGHT) },
  { id: "temperatura", title: "meteo.title.temperatura", component: Temperatura, available: (station, ids) => hasAny(ids, TEMPERATURE) },
  { id: "snieg", title: "meteo.title.snieg", component: Snieg, available: (station, ids) => ids.has("snow") },
  { id: "trendy", title: "meteo.title.trendy", component: Trendy, available: (station, ids) => [...ids].some(meteoTrend) },
];
