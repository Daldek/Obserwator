// The view in the address (plan D10): `?station=<code>&section=<id>`, the view
// (`view=pomiary` for „Pomiary bieżące”, `view=pmaxtp` for „PMAXTP”; none for „Stacje”) and
// the PMAXTP point (`lat`, `lon` at four decimals, `method=AMP` when not POT), written with
// history.replaceState so a copied link reopens the same view. Other parameters (e.g.
// `nogat=1`) are kept.

const VIEW_WORDS = { current: "pomiary", pmaxtp: "pmaxtp" };
const VIEWS = Object.fromEntries(Object.entries(VIEW_WORDS).map(([view, word]) => [word, view]));

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
  return {
    station: params.get("station") || null,
    section: params.get("section") || null,
    view: VIEWS[params.get("view")] || "stations",
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
  put("view", VIEW_WORDS[view] || null);
  put("lat", pmaxtp && point ? point.lat.toFixed(4) : null);
  put("lon", pmaxtp && point ? point.lon.toFixed(4) : null);
  put("method", pmaxtp && method === "AMP" ? "AMP" : null);
  const query = params.toString();
  const next = `${window.location.pathname}${query ? `?${query}` : ""}${window.location.hash}`;
  const now = `${window.location.pathname}${window.location.search}${window.location.hash}`;
  if (next !== now) window.history.replaceState(null, "", next);
}
