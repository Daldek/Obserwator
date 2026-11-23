// Words of the store's keys in the page's language, shared by the views: providers, station
// kinds (and what a groundwater object is), datasets, variables, flags and IMGW-PIB's
// half-years. Every word is an entry of the catalog (`gui.words.*`); providers' short names
// stay as they publish them. Call these at render time: the texts change with the language.

import { has, t } from "./i18n.js";

/** Providers' short names by their catalog id: names, the same in every language. */
const SHORT = { IMGW: "IMGW-PIB", CHMU: "ČHMÚ" };

/** The catalog's form of a store key: "pl.imgw.hydro_daily" → "pl_imgw_hydro_daily". */
function slug(key) {
  return String(key).replace(/[.-]/g, "_").toLowerCase();
}

/** A text of the catalog, else the fallback (an unknown key of the store). */
function word(key, fallback) {
  return has(key) ? t(key) : fallback;
}

/** The short name of a provider ("ČHMÚ" for "CHMU"), "–" for none. */
export function providerName(id) {
  return SHORT[id] || id || "–";
}

/** The full name of a provider in the page's language. */
export function providerFullName(id) {
  return word(`words.provider.${slug(id)}`, providerName(id));
}

/** The station kinds in their order (`obserwator.datasets.KINDS`). */
export const KINDS = Object.freeze(["hydro", "meteo", "groundwater"]);

/**
 * The kinds the views offer and name (the switch „Rodzaj stacji”, the legend, the stations
 * of each catalog): hydrological and meteorological always, groundwater only where the
 * stations hold a groundwater object, so a deployment without one looks as before.
 *
 * @param {object[]} stations stations of api/stations
 * @returns {string[]} kinds, in their order
 */
export function shownKinds(stations) {
  return KINDS.filter((kind) => kind !== "groundwater" || stations.some((station) => station.kind === kind));
}

/** A station kind: "hydrological", "meteorological" or "groundwater" in the page's language. */
export function kindName(kind) {
  return word(`words.kind.${kind}`, kind || "–");
}

/** What a groundwater object is ("borehole", "spring"); null for a station that is none. */
export function groundwaterKindName(kind) {
  return kind ? word(`words.groundwater_kind.${kind}`, kind) : null;
}

/** Each dataset whose station series the root may hold, in the order of the registry: its time step and the kind of its stations. */
export const SERIES_DATASETS = {
  "pl.imgw.hydro_daily": { step: "day", kind: "hydro" },
  "pl.imgw.hydro_monthly": { step: "month", kind: "hydro" },
  "pl.imgw.hydro_semiannual": { step: "half_year", kind: "hydro" },
  "pl.imgw.meteo_climate_daily": { step: "day", kind: "meteo" },
  "pl.imgw.meteo_precip_daily": { step: "day", kind: "meteo" },
  "pl.imgw.meteo_synop_daily": { step: "day", kind: "meteo" },
  "cz.chmu.hydro_daily": { step: "day", kind: "hydro" },
  "cz.chmu.meteo_daily": { step: "day", kind: "meteo" },
  "cz.chmu.groundwater_daily": { step: "day", kind: "groundwater" },
  "cz.chmu.groundwater_weekly": { step: "week", kind: "groundwater" },
};

/** The title of a dataset ("Daily hydrological data (IMGW-PIB)"), its key when unknown. */
export function datasetTitle(key) {
  return word(`words.dataset.${slug(key)}.title`, key);
}

/** The short label of a dataset ("Daily"), its key when unknown. */
export function datasetShort(key) {
  return word(`words.dataset.${slug(key)}.short`, key);
}

/** The decimals shown of each variable of the store; the synoptic durations [h] have one. */
const DIGITS = {
  H: 0,
  Q: 3,
  T: 1,
  Tmax: 1,
  Tmin: 1,
  Tmean: 1,
  Tground: 1,
  P: 1,
  snow_cover: 0,
  fresh_snow: 0,
  snow_water_equivalent: 1,
  sunshine: 1,
  snow_cover_occurrence: 0,
  lightning_occurrence: 0,
  isotherm_lower: 0,
  isotherm_upper: 0,
  actinometry: 0,
  cloud_cover: 1,
  wind_speed: 1,
  vapour_pressure: 1,
  humidity: 1,
  pressure_station: 1,
  pressure_sea: 1,
  P_day: 1,
  P_night: 1,
  H_asl: 2,
  spring_yield: 2,
};

/**
 * What a variable is: its label in the page's language and the decimals shown. A monthly
 * or half-year statistic (`Q_max`) has the label of its variable and `stat` ("max").
 *
 * @param {string} name the store's name (H, Q, Tmax, Q_max, …)
 * @returns {{label: string, digits: number, stat: string|null}}
 */
export function variableInfo(name) {
  const [base, stat] = /^(.+)_(min|mean|max)$/.test(name) ? name.split(/_(?=(?:min|mean|max)$)/) : [name, null];
  return {
    label: word(`words.variable.${slug(base)}`, base),
    digits: DIGITS[base] ?? (base.endsWith("_duration") ? 1 : 2),
    stat: stat || null,
  };
}

/** The flags of the harmonized records, beside `value`, in the order they are explained. */
export const FLAGS = ["value", "missing", "no_phenomenon", "accumulated"];

/** The word of a record's flag ("missing"). */
export function flagName(flag) {
  return word(`words.flag.${flag}`, flag);
}

/** The half-years of IMGW-PIB's characteristics, in their order. */
export const PERIODS = ["winter", "summer", "annual"];

/** The word of a half-year ("winter (XI–IV)"). */
export function periodName(period) {
  return word(`words.period.${period}`, period);
}
