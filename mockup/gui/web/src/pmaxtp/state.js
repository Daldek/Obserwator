// PMAXTP of a point (plan D12): the box `fetch_pmaxtp` accepts, the point as IMGW-PIB's URL
// rounds it (four decimals, Obserwator `urls.py`), and the result from the server
// (api/pmaxtp: `fetch_pmaxtp`, kept there for 24 hours and asked of IMGW-PIB one point at a
// time, never stored).

import { api } from "../api.js";
import { fmt, useEffect, useState } from "../lib.js";

/** The box `fetch_pmaxtp` validates (Obserwator `fetch.py`, POLAND_LAT_MIN to POLAND_LON_MAX). */
export const PMAXTP_BOUNDS = Object.freeze({ lat: [49, 55], lon: [14, 24.5] });

/** The methods, described as on the old page (templates/download/pmaxtp.html). */
export const METHODS = [
  { value: "POT", label: "POT", title: "Peak Over Threshold: wartości szczytowe powyżej progu" },
  { value: "AMP", label: "AMP", title: "Annual Max Precipitation: maksima roczne" },
];
export const METHOD_NAMES = { POT: "Peak Over Threshold", AMP: "Annual Max Precipitation" };

/** A coordinate as IMGW-PIB's URL writes it. */
export function round4(value) {
  return Math.round(value * 10000) / 10000;
}

/** "50,0647° N, 19,9450° E". */
export function pointLabel(point) {
  return `${fmt(point.lat, 4)}° N, ${fmt(point.lon, 4)}° E`;
}

/**
 * Why a point cannot be asked for, or null.
 *
 * @param {{lat: number, lon: number}} point
 * @returns {string|null}
 */
export function outside(point) {
  const { lat, lon } = PMAXTP_BOUNDS;
  if (!Number.isFinite(point.lat) || !Number.isFinite(point.lon)) return "Podaj szerokość i długość geograficzną w stopniach dziesiętnych.";
  if (point.lat < lat[0] || point.lat > lat[1] || point.lon < lon[0] || point.lon > lon[1]) {
    return `Punkt ${pointLabel(point)} leży poza zakresem PMAXTP: ${fmt(lat[0])}–${fmt(lat[1])}° N, ${fmt(lon[0])}–${fmt(lon[1], 1)}° E.`;
  }
  return null;
}

/** The query of a point and method on the server's routes. */
export function pmaxtpQuery(point, method) {
  return { lat: point.lat.toFixed(4), lon: point.lon.toFixed(4), method };
}

/**
 * PMAXTP of the point by the method, while there is a point inside the box.
 *
 * @param {{lat: number, lon: number}|null} point
 * @param {"POT"|"AMP"} method
 * @returns {{doc: object|null, error: Error|null, loading: boolean}}
 */
export function usePmaxtp(point, method) {
  const [state, setState] = useState({ doc: null, error: null, loading: false });
  const ask = point && !outside(point);
  useEffect(() => {
    if (!ask) {
      setState({ doc: null, error: null, loading: false });
      return undefined;
    }
    let live = true;
    setState((old) => ({ ...old, error: null, loading: true }));
    api.get("api/pmaxtp", pmaxtpQuery(point, method)).then(
      (doc) => live && setState({ doc, error: null, loading: false }),
      (error) => live && setState({ doc: null, error, loading: false }),
    );
    return () => {
      live = false;
    };
  }, [ask, point && point.lat, point && point.lon, method]);
  return state;
}
