// The shell's Polish words for the store's keys: providers, station kinds, datasets,
// variables and flags. Sections may use them too.

/** Providers by their catalog id. */
export const PROVIDERS = {
  "IMGW-PIB": { short: "IMGW-PIB", name: "Instytut Meteorologii i Gospodarki Wodnej – PIB" },
  CHMI: { short: "ČHMÚ", name: "Český hydrometeorologický ústav" },
};

/** The short name of a provider ("ČHMÚ" for "CHMI"). */
export function providerName(id) {
  return (PROVIDERS[id] && PROVIDERS[id].short) || id || "–";
}

/** Station kinds. */
export const KINDS = { hydro: "hydrologiczna", meteo: "meteorologiczna" };

/** The series datasets the store may hold: a title, a short label and the time step. */
export const DATASETS = {
  "pl.imgw.hydro_daily": { title: "Dane hydrologiczne dobowe (IMGW-PIB)", short: "Dobowe", step: "day" },
  "pl.imgw.hydro_semiannual": { title: "Charakterystyki półroczne (IMGW-PIB)", short: "Półroczne", step: "half_year" },
  "pl.imgw.meteo_climate_daily": { title: "Dane klimatyczne dobowe (IMGW-PIB)", short: "Klimatyczne", step: "day" },
  "pl.imgw.meteo_precip_daily": { title: "Dane opadowe dobowe (IMGW-PIB)", short: "Opadowe", step: "day" },
  "cz.chmi.hydro_daily": { title: "Dane hydrologiczne dobowe (ČHMÚ)", short: "Dobowe", step: "day" },
  "cz.chmi.meteo_daily": { title: "Dane meteorologiczne dobowe (ČHMÚ)", short: "Dobowe", step: "day" },
};

/** The title of a dataset, its key when unknown. */
export function datasetTitle(key) {
  return (DATASETS[key] && DATASETS[key].title) || key;
}

/** Variables by their store name: a label, a short symbol and the decimals shown. */
const VARIABLES = {
  hydro: {
    H: { label: "stan wody", digits: 0 },
    Q: { label: "przepływ", digits: 3 },
    T: { label: "temperatura wody", digits: 1 },
  },
  meteo: {
    Tmax: { label: "temperatura maksymalna", digits: 1 },
    Tmin: { label: "temperatura minimalna", digits: 1 },
    Tmean: { label: "temperatura średnia", digits: 1 },
    Tground: { label: "temperatura przy gruncie", digits: 1 },
    P: { label: "opad", digits: 1 },
    snow_cover: { label: "pokrywa śnieżna", digits: 0 },
    fresh_snow: { label: "śnieg świeży", digits: 0 },
  },
};

/**
 * What a variable is, for its station kind.
 *
 * @param {string} name the store's name (H, Q, Tmax, …)
 * @param {string} [kind] "hydro" | "meteo"
 * @returns {{label: string, digits: number}}
 */
export function variableInfo(name, kind) {
  const own = kind && VARIABLES[kind] ? VARIABLES[kind][name] : null;
  return own || VARIABLES.hydro[name] || VARIABLES.meteo[name] || { label: name, digits: 2 };
}

/** The flags of the harmonized records, beside `value`. */
export const FLAGS = {
  value: "wartość",
  missing: "brak",
  no_phenomenon: "brak zjawiska",
  accumulated: "suma z kilku dni",
};

/** The half-years of IMGW-PIB's characteristics. */
export const PERIODS = { winter: "zima (XI–IV)", summer: "lato (V–X)", annual: "rok" };
