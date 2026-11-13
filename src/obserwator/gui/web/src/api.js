// The private API of Obserwator's GUI server (src/obserwator/gui/_app.py), relative to the
// page, so the page works at "/" and under any prefix. Every request names the page's
// language (Accept-Language), so the server's error texts come in it.

import { lang } from "./i18n.js";

/** An error of the API: its document `obserwator-error/1` and the HTTP status. */
export class ApiError extends Error {
  constructor(status, doc) {
    super(doc && (doc.message || doc.title) ? doc.message || doc.title : `HTTP ${status}`);
    this.status = status;
    this.doc = doc;
  }
}

const cache = new Map();

function query(params) {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params || {})) {
    if (value === undefined || value === null || value === "") continue;
    search.set(key, Array.isArray(value) ? value.join(",") : String(value));
  }
  const text = search.toString();
  return text ? `?${text}` : "";
}

/**
 * GET a route of the API as JSON.
 *
 * @param {string} path relative to the page (`api/stations`)
 * @param {Record<string, unknown>} [params] query parameters; empty ones are left out
 * @param {{memo?: boolean, signal?: AbortSignal}} [options] `memo` keeps the answer for the
 *   page's life (the default), `signal` cancels the request
 * @returns {Promise<any>}
 */
export function get(path, params = {}, { memo = true, signal } = {}) {
  const url = `${path}${query(params)}`;
  const key = `${lang()} ${url}`;
  if (memo && cache.has(key)) return cache.get(key);
  const promise = fetch(url, { headers: { Accept: "application/json", "Accept-Language": lang() }, signal }).then(
    async (response) => {
      const doc = await response.json().catch(() => null);
      if (!response.ok) throw new ApiError(response.status, doc);
      return doc;
    },
  );
  if (memo) {
    cache.set(key, promise);
    promise.catch(() => cache.delete(key));
  }
  return promise;
}

const enc = encodeURIComponent;

export const api = {
  /** `obserwator-gui-session/1`: versions, the data root, providers, basemap, menus. */
  session: () => get("api/session", {}, { memo: false }),
  /** Every station of the catalogs: {count, stations: [{code, name, river, provider, kind, …}]}. */
  stations: () => get("api/stations"),
  /** One station: catalog properties, the series holding it, their lines. */
  station: (code) => get(`api/stations/${enc(code)}`),
  /**
   * A station's series of a dataset: {dates, hydro_year, units, values, flags, period?, extremes?}.
   *
   * @param {string} dataset
   * @param {string} code
   * @param {{variables?: string[], start?: string, end?: string, signal?: AbortSignal}} [options]
   */
  series: (dataset, code, { variables, start, end, signal } = {}) =>
    get(`api/series/${enc(dataset)}/${enc(code)}`, { variables, start, end }, { signal }),
  /** The analysis ids of a station: [{analysis, command, options, overridable, inputs, stored}]. */
  analyses: (code) => get(`api/analyses/${enc(code)}`),
  /**
   * One analysis id of a station (`obserwator-analysis/1`): the stored result without
   * overrides, else computed by Hydrolog with them (`source`: "stored" | "computed").
   *
   * @param {string} code
   * @param {string} id e.g. "characteristic.Q"
   * @param {Record<string, unknown>} [overrides] the person's options (first_year, …)
   * @param {{signal?: AbortSignal}} [options]
   */
  analysis: (code, id, overrides = {}, { signal } = {}) =>
    get(`api/analysis/${enc(code)}/${enc(id)}`, overrides, { signal }),
  /** The address of an analysis id's result as a JSON file. */
  analysisFileUrl: (code, id, overrides = {}) => `api/files/analysis/${enc(code)}/${enc(id)}${query(overrides)}`,
  /** The files of a station: each series in each format, its command line and licence. */
  downloads: (code) => get(`api/downloads/${enc(code)}`),
  /** IMGW-PIB's current data: the points of „Pomiary bieżące” (never memoised). */
  current: () => get("api/current", {}, { memo: false }),
  /** One station's current values (IMGW-PIB only). */
  currentStation: (code) => get(`api/current/${enc(code)}`, {}, { memo: false }),
  /** PMAXTP of a point: {method, latitude, longitude, durations, probabilities, data, …}. */
  pmaxtp: ({ latitude, longitude, method }) => get("api/pmaxtp", { latitude, longitude, method }),
  /** The address of PMAXTP of a point as a CSV or JSON file. */
  pmaxtpFileUrl: ({ latitude, longitude, method, format }) =>
    `api/files/pmaxtp${query({ latitude, longitude, method, format })}`,
  /**
   * The hand-off to Hydrolog (`nogat-handoff/1`): a daily series, or the annual maxima of
   * an analysis id's result.
   *
   * @param {string} code
   * @param {{variable: string, resolution: "daily"|"annual", first_year?: number,
   *   last_year?: number, analysis?: string}} options
   */
  handoff: (code, options) => get(`api/handoff/${enc(code)}`, options, { memo: false }),
  /**
   * „Zgłoś uwagę”: POST api/feedback, the server's only write.
   *
   * @param {{message: string, context: object}} report the text and the automatic context
   * @returns {Promise<{id: number, status: string}>}
   */
  async feedback(report) {
    const response = await fetch("api/feedback", {
      method: "POST",
      headers: { Accept: "application/json", "Content-Type": "application/json", "Accept-Language": lang() },
      body: JSON.stringify(report),
    });
    const doc = await response.json().catch(() => null);
    if (!response.ok) throw new ApiError(response.status, doc);
    return doc;
  },
};
