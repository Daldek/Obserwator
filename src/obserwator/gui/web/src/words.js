// Words of the store's keys in the page's language, shared by the views: providers, station
// kinds, datasets, variables, flags and IMGW-PIB's half-years. Every word is an entry of the
// catalog (`gui.words.*`); providers' short names stay as they publish them. Call these at
// render time: the texts change with the language.

import { has, t } from "./i18n.js";

/** Providers' short names by their catalog id: names, the same in every language. */
const SHORT = { "IMGW-PIB": "IMGW-PIB", CHMI: "ČHMÚ" };

/** The catalog's form of a store key: "pl.imgw.hydro_daily" → "pl_imgw_hydro_daily". */
function slug(key) {
  return String(key).replace(/[.-]/g, "_").toLowerCase();
}

/** A text of the catalog, else the fallback (an unknown key of the store). */
function word(key, fallback) {
  return has(key) ? t(key) : fallback;
}

/** The short name of a provider ("ČHMÚ" for "CHMI"), "–" for none. */
export function providerName(id) {
  return SHORT[id] || id || "–";
}

/** The full name of a provider in the page's language. */
export function providerFullName(id) {
  return word(`words.provider.${slug(id)}`, providerName(id));
}

/** A station kind: "hydrological" or "meteorological" in the page's language. */
export function kindName(kind) {
  return word(`words.kind.${kind}`, kind || "–");
}

/** The time step of each dataset the root may hold, in the order of the registry. */
export const DATASET_STEPS = {
  "pl.imgw.hydro_daily": "day",
  "pl.imgw.hydro_monthly": "month",
  "pl.imgw.hydro_semiannual": "half_year",
  "pl.imgw.meteo_climate_daily": "day",
  "pl.imgw.meteo_precip_daily": "day",
  "cz.chmi.hydro_daily": "day",
  "cz.chmi.meteo_daily": "day",
};

/** The title of a dataset ("Daily hydrological data (IMGW-PIB)"), its key when unknown. */
export function datasetTitle(key) {
  return word(`words.dataset.${slug(key)}.title`, key);
}

/** The short label of a dataset ("Daily"), its key when unknown. */
export function datasetShort(key) {
  return word(`words.dataset.${slug(key)}.short`, key);
}

/** The decimals shown of each variable of the store. */
const DIGITS = { H: 0, Q: 3, T: 1, Tmax: 1, Tmin: 1, Tmean: 1, Tground: 1, P: 1, snow_cover: 0, fresh_snow: 0 };

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
    digits: DIGITS[base] ?? 2,
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
