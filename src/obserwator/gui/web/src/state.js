// The view in the address (plan D10): `?station=<code>&section=<id>`, the view
// (`view=current` for „Pomiary bieżące”, `view=pmaxtp` for „PMAXTP”; none for „Stacje”) and
// the PMAXTP point (`lat`, `lon` at four decimals, `method=AMP` when not POT), written with
// history.replaceState so a copied link reopens the same view. Other parameters (e.g.
// `nogat=1`) are kept.

/** The views of the map's bar; the first is the default, which the address leaves out. */
export const VIEWS = ["stations", "current", "pmaxtp"];

/**
 * The view the address names.
 *
 * @returns {{station: string|null, section: string|null, view: "stations"|"current"|"pmaxtp",
 *   point: {lat: number, lon: number}|null, method: "POT"|"AMP"}}
 */
export function readAddress() {
  const params = new URLSearchParams(window.location.search);
  const lat = Number.parseFloat(params.get("lat") || "");
  const lon = Number.parseFloat(params.get("lon") || "");
  const view = params.get("view");
  return {
    station: params.get("station") || null,
    section: params.get("section") || null,
    view: VIEWS.includes(view) ? view : VIEWS[0],
    point: Number.isFinite(lat) && Number.isFinite(lon) ? { lat, lon } : null,
    method: params.get("method") === "AMP" ? "AMP" : "POT",
  };
}

/**
 * Write the view into the address without a new history entry.
 *
 * @param {{station: string|null, section: string|null, view: string,
 *   point: {lat: number, lon: number}|null, method: string}} state
 */
export function writeAddress({ station, section, view, point, method }) {
  const params = new URLSearchParams(window.location.search);
  const put = (key, value) => (value ? params.set(key, value) : params.delete(key));
  const pmaxtp = view === "pmaxtp";
  put("station", station);
  put("section", station ? section : null);
  put("view", view === VIEWS[0] ? null : view);
  put("lat", pmaxtp && point ? point.lat.toFixed(4) : null);
  put("lon", pmaxtp && point ? point.lon.toFixed(4) : null);
  put("method", pmaxtp && method === "AMP" ? "AMP" : null);
  const query = params.toString();
  const next = `${window.location.pathname}${query ? `?${query}` : ""}${window.location.hash}`;
  const now = `${window.location.pathname}${window.location.search}${window.location.hash}`;
  if (next !== now) window.history.replaceState(null, "", next);
}

/**
 * The address's parameters as an object: what „Zgłoś uwagę” sends as the view's
 * parameters (Nogat DEV-15.12), at most `limit` of them.
 *
 * @param {number} [limit] the most parameters kept (the server's PARAMETERS_MAX)
 * @returns {Record<string, string>}
 */
export function addressParameters(limit = 50) {
  return Object.fromEntries([...new URLSearchParams(window.location.search)].slice(0, limit));
}
