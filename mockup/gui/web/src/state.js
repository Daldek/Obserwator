// The view in the address (plan D10): `?station=<code>&section=<id>` and the map's layer
// (`layer=stan`), written with history.replaceState so a copied link reopens the same view.
// Other parameters (e.g. `nogat=1`) are kept.

/**
 * The view the address names.
 *
 * @returns {{station: string|null, section: string|null, layer: "stations"|"states"}}
 */
export function readAddress() {
  const params = new URLSearchParams(window.location.search);
  return {
    station: params.get("station") || null,
    section: params.get("section") || null,
    layer: params.get("layer") === "stan" ? "states" : "stations",
  };
}

/**
 * Write the view into the address without a new history entry.
 *
 * @param {{station: string|null, section: string|null, layer: string}} view
 */
export function writeAddress({ station, section, layer }) {
  const params = new URLSearchParams(window.location.search);
  const put = (key, value) => (value ? params.set(key, value) : params.delete(key));
  put("station", station);
  put("section", station ? section : null);
  put("layer", layer === "states" ? "stan" : null);
  const query = params.toString();
  const next = `${window.location.pathname}${query ? `?${query}` : ""}${window.location.hash}`;
  const now = `${window.location.pathname}${window.location.search}${window.location.hash}`;
  if (next !== now) window.history.replaceState(null, "", next);
}
