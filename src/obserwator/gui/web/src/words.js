// Words of the store's keys in the page's language, shared by the views: providers, station
// kinds (and what a groundwater object is), datasets, variables, flags and IMGW-PIB's
// half-years. Every word is an entry of the catalog (`gui.words.*`); providers' short names
// stay as they publish them. Call these at render time: the texts change with the language.
// The providers and their series datasets are the session's (api/session `providers` and
// `datasets`, in the order of the registry), which main.js hands over with `setRegistry`
// once it answers: a provider's names, the class of its source and the origins of its
// lines; a dataset's provider, kind, time step, tier and, where the catalog has no words of
// its own (a provider fed by files), its title and short label in the page's language.

import { has, t } from "./i18n.js";

/** The session's providers by id and series datasets by key; none until it answers. */
let registry = { providers: {}, datasets: {} };

/**
 * Hand over the providers and the series datasets of the session (main.js, when api/session
 * answers, before the page draws with them).
 *
 * @param {{providers: object, datasets: object}} session api/session
 */
export function setRegistry(session) {
  registry = { providers: session.providers || {}, datasets: session.datasets || {} };
}

/**
 * A provider as the session describes it.
 *
 * @param {string} id e.g. "IMGW"
 * @returns {{short_name: string, name: string, key_prefix: string, origin: string, border:
 *   string, source_class: string}|null} its short and full name, the prefix of its dataset
 *   keys, the origin of its lines, the origin of the border its stations were checked
 *   against and the class of its source; null while the session does not name it
 */
export function providerOf(id) {
  return Object.hasOwn(registry.providers, id) ? registry.providers[id] : null;
}

/** The catalog's form of a store key: "pl.imgw.hydro_daily" → "pl_imgw_hydro_daily". */
function slug(key) {
  return String(key).replace(/[.-]/g, "_").toLowerCase();
}

/** A text of the catalog, else the fallback (an unknown key of the store). */
function word(key, fallback) {
  return has(key) ? t(key) : fallback;
}

/** The short name of a provider ("ČHMÚ" for "CHMU"), its id until the session names it, "–" for none. */
export function providerName(id) {
  const provider = providerOf(id);
  return provider ? provider.short_name : id || "–";
}

/** The full name of a provider in the page's language: the catalog's, else the one it publishes. */
export function providerFullName(id) {
  const provider = providerOf(id);
  return word(`words.provider.${slug(id)}`, provider ? provider.name : providerName(id));
}

/**
 * The class of a provider's source (hydromet P11): "nmhs", a national meteorological and
 * hydrological service (IMGW-PIB, ČHMÚ), or "other" (a provider fed by files among them).
 *
 * @param {string} id
 * @returns {string|null} null until the session names the provider
 */
export function sourceClass(id) {
  const provider = providerOf(id);
  return provider ? provider.source_class : null;
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

/**
 * Each dataset whose station series the root may hold, of the providers served, in the
 * order of the registry; none until the session answers.
 *
 * @returns {Record<string, {provider: string, kind: string, step: string, tier: string,
 *   title: string, short: string}>} by key: its provider, the kind of its stations, its time
 *   step ("day", "week", "month", "half_year", "hour"), its tier ("verified", "telemetry",
 *   "operational") and its title and short label in the page's language
 */
export function seriesDatasets() {
  return registry.datasets;
}

/** A series dataset of the session, null while it names none of this key. */
function datasetOf(key) {
  return Object.hasOwn(registry.datasets, key) ? registry.datasets[key] : null;
}

/** The title of a dataset ("Daily hydrological data (IMGW-PIB)"): the catalog's, else the session's, else its key. */
export function datasetTitle(key) {
  const dataset = datasetOf(key);
  return word(`words.dataset.${slug(key)}.title`, dataset ? dataset.title : key);
}

/** The short label of a dataset ("Daily"): the catalog's, else the session's, else its key. */
export function datasetShort(key) {
  const dataset = datasetOf(key);
  return word(`words.dataset.${slug(key)}.short`, dataset ? dataset.short : key);
}

/**
 * Whether a dataset's series are operational data, unverified, as a whole (hydromet P11,
 * Nogat DEV-20.8): its tier is not "verified". An hourly series is not: each of its hours
 * carries its own tier, which its chart and table name (ADR-031).
 */
export function unverified(key) {
  const dataset = datasetOf(key);
  return dataset !== null && dataset.tier !== "verified" && dataset.step !== "hour";
}

/** Whether a dataset holds daily hydrological series: a provider's `<key prefix>.hydro_daily`. */
export function hydroDaily(key) {
  const dataset = datasetOf(key);
  return dataset !== null && dataset.kind === "hydro" && dataset.step === "day";
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
