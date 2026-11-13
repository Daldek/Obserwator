// The private API of the mockup's server (server/app.py), relative to the page.

/** An error of the API: its document `{code, title}` and the HTTP status. */
export class ApiError extends Error {
  constructor(status, doc) {
    super(doc && doc.title ? doc.title : `HTTP ${status}`);
    this.status = status;
    this.doc = doc;
  }
}

const cache = new Map();

async function get(path, params = {}, { memo = true } = {}) {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") query.set(key, String(value));
  }
  const url = query.toString() ? `${path}?${query}` : path;
  if (memo && cache.has(url)) return cache.get(url);
  const promise = fetch(url, { headers: { Accept: "application/json" } }).then(async (response) => {
    const doc = await response.json().catch(() => null);
    if (!response.ok) throw new ApiError(response.status, doc);
    return doc;
  });
  if (memo) {
    cache.set(url, promise);
    promise.catch(() => cache.delete(url));
  }
  return promise;
}

export const api = {
  /** Versions, the analyses and the deployment's GUIs. */
  meta: () => get("api/meta"),
  /** Every station of the catalogs: {count, stations: [{code, name, river, provider, kind, …}]}. */
  stations: () => get("api/stations"),
  /** One station: catalog properties and the datasets that hold it. */
  station: (code) => get(`api/station/${encodeURIComponent(code)}`),
  /** A station's series: {dates, values: {V: [...]}, units, flags, version, attribution, terms_notice, …}. */
  series: (code, dataset, { variables, from, to } = {}) =>
    get(`api/series/${encodeURIComponent(code)}`, { dataset, variables: variables && variables.join(","), from, to }),
  /** An analysis of a station with its options (strings): the analysis' document. */
  analysis: (name, code, params = {}) => get(`api/analysis/${encodeURIComponent(name)}`, { station: code, ...params }),
  /** A GET of any other route of the server. */
  get,
};
