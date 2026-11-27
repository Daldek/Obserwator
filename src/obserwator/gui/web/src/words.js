// Words of the store's keys in the page's language, shared by the views: providers, the
// classes of their sources, countries, station kinds (and what a groundwater object is),
// datasets, variables, flags and IMGW-PIB's half-years. Every word is an entry of the
// catalog (`gui.words.*`); providers' short names stay as they publish them. Call these at
// render time: the texts change with the language. The providers and their series datasets
// are the session's (api/session `providers` and `datasets`, in the order of the registry),
// which main.js hands over with `setRegistry` once it answers: a provider's names, its
// country, the families of its stations, the class of its source with P8's notice of
// another source, and the origins of its lines; a dataset's provider, kind, time step,
// tier, whether its series are unverified as a whole and, where the catalog has no words
// of its own (a provider fed by files), its title and short label in the page's language.
// The page groups the providers by the class of their source, never by their ids
// (hydromet P1, P11, P12: `classGroups`).

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
 * @returns {{short_name: string, name: string, country: string, key_prefix: string, origin:
 *   string, border: string, source_class: string, source_notice: string|null}|null} its
 *   short and full name, its country (ISO 3166-1 alpha-2), the prefix of its dataset keys,
 *   the origin of its lines, the origin of the border its stations were checked against,
 *   the class of its source and P8's notice in the page's language (the class "other" and
 *   PIG-PIB; null for IMGW-PIB and ČHMÚ); null while the session does not name it
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
 * The class of a provider's source (hydromet P11, state services S1): "state", a state
 * service set up by statute and run by a state body or state research institute (IMGW-PIB,
 * ČHMÚ, PIG-PIB), or "other", every other operator (Gdańskie Wody, a provider fed by files).
 *
 * @param {string} id
 * @returns {string|null} null until the session names the provider
 */
export function sourceClass(id) {
  const provider = providerOf(id);
  return provider ? provider.source_class : null;
}

/** The classes of the providers' sources (hydromet P11, state services S1) in the page's order: state services, then other sources. */
export const SOURCE_CLASSES = Object.freeze(["state", "other"]);

/**
 * The classes the stations' sources hold, in their order: the class switch of „Stacje”
 * and the legend's outlines name them only where both are held, since one class alone
 * separates nothing.
 *
 * @param {object[]} stations stations of api/stations
 * @returns {string[]} classes, in their order
 */
export function shownClasses(stations) {
  const held = new Set(stations.map((station) => sourceClass(station.provider)));
  return SOURCE_CLASSES.filter((cls) => held.has(cls));
}

/** A class of sources as a heading: "State services" or "Other sources". */
export function sourceClassName(cls) {
  return word(`words.source_class.${cls}`, cls || "–");
}

/** A country by its ISO 3166-1 alpha-2 code ("Poland" for "PL"): the catalog's word, else the code. */
export function countryName(code) {
  return code ? word(`words.country.${String(code).toLowerCase()}`, code) : "–";
}

/** Providers' short names are sorted as Polish, whatever the page's language. */
const nameOrder = new Intl.Collator("pl", { sensitivity: "base", numeric: true });

/**
 * Providers grouped by the class of their source (hydromet P12), as the station list's
 * dataset chips and the panel without a station show them: one group per class holding a
 * provider, the featured provider's class first, else state services before other
 * sources; within a class the featured provider first (ADR-025, I6), then by country and
 * short name. A provider the session does not name has no class: its group comes last.
 *
 * @param {string[]} providers ids
 * @param {string|null} [featured] the instance's featured provider
 * @returns {{cls: string|null, providers: string[]}[]} the groups in order
 */
export function classGroups(providers, featured = null) {
  const first = featured ? sourceClass(featured) : null;
  const rank = (cls) => (cls !== null && cls === first ? -1 : SOURCE_CLASSES.includes(cls) ? SOURCE_CLASSES.indexOf(cls) : SOURCE_CLASSES.length);
  const country = (id) => (providerOf(id) || {}).country || "";
  const sorted = [...providers].sort(
    (a, b) => Number(b === featured) - Number(a === featured) || country(a).localeCompare(country(b)) || nameOrder.compare(providerName(a), providerName(b)),
  );
  const groups = [];
  for (const id of sorted) {
    const cls = sourceClass(id);
    const group = groups.find((item) => item.cls === cls);
    if (group) group.providers.push(id);
    else groups.push({ cls, providers: [id] });
  }
  return groups.sort((a, b) => rank(a.cls) - rank(b.cls));
}

/** The station kinds in their order (`obserwator.datasets.KINDS`). */
export const KINDS = Object.freeze(["hydro", "meteo", "groundwater"]);

/**
 * The families of a provider's stations (the session's `kinds`, its adapter's), in their
 * order: PIG-PIB's points are groundwater objects alone; every kind until the session
 * names the provider.
 *
 * @param {string} id
 * @returns {string[]} kinds, in their order
 */
export function providerKinds(id) {
  const provider = providerOf(id);
  return provider && Array.isArray(provider.kinds) ? KINDS.filter((kind) => provider.kinds.includes(kind)) : [...KINDS];
}

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
 *   unverified: boolean, title: string, short: string}>} by key: its provider, the kind of
 *   its stations, its time step ("day", "week", "month", "half_year", "hour"), its tier
 *   ("verified", "telemetry", "operational"), whether its series are unverified as a whole
 *   (`unverified`) and its title and short label in the page's language
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
 * The note of a dataset under its series, what its provider says of its values (when
 * ČHMÚ reads, PIG-PIB's quantities, its 06:00 UTC reading and its hours); null for a
 * dataset without one.
 */
export function datasetNote(key) {
  const name = `words.dataset.${slug(key)}.note`;
  return has(name) ? t(name) : null;
}

/**
 * Whether a dataset's series are operational data, unverified, as a whole (hydromet P11,
 * Nogat DEV-20.8): the session's `unverified`, a tier other than "verified" and, of an
 * hourly series, every input of that one tier (PIG-PIB's automatic hours). An hourly
 * series of several tiers is not: each of its hours carries its own tier, which its chart
 * and table name (ADR-031).
 */
export function unverified(key) {
  const dataset = datasetOf(key);
  return dataset !== null && dataset.unverified === true;
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
  depth_to_water: 2,
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
