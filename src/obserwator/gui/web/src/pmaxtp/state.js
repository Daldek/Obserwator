// PMAXTP of a point (plan D12): the box `fetch_pmaxtp` accepts, the point as IMGW-PIB's URL
// rounds it (four decimals, Obserwator `urls.py`), and the result from the server
// (api/pmaxtp: `fetch_pmaxtp`, kept there for 24 hours and asked of IMGW-PIB one point at a
// time, never stored).

import { api } from "../api.js";
import { fmt, lang, t, useEffect, useState } from "../lib.js";

/** The box `fetch_pmaxtp` validates (Obserwator `fetch.py`, POLAND_LAT_MIN to POLAND_LON_MAX). */
export const PMAXTP_BOUNDS = Object.freeze({ lat: [49, 55], lon: [14, 24.5] });

/** The methods of the PMAXTP model; their names and descriptions are the catalog's. */
export const METHODS = ["POT", "AMP"];

/** The catalog's name of a method ("POT" → Peak Over Threshold). */
export function methodName(method) {
  return method === "AMP" ? t("pmaxtp.method.amp.name") : t("pmaxtp.method.pot.name");
}

/** The project's monograph (Open Access, CC BY 4.0), the line M of PMAXTP's attribution. */
export const MONOGRAPH_URL =
  "https://www.imgw.pl/sites/default/files/2022-12/imgw-pib-monografia_modele-probabilistyczne-opadow-maksymalnych.pdf";

/** A coordinate as IMGW-PIB's URL writes it. */
export function round4(value) {
  return Math.round(value * 10000) / 10000;
}

/** "50,0647° N, 19,9450° E" in the page's language. */
export function pointLabel(point) {
  return `${fmt(point.lat, 4)}° N, ${fmt(point.lon, 4)}° E`;
}

/** The box as text: "49–55° N, 14–24,5° E". */
export function boundsLabel() {
  const { lat, lon } = PMAXTP_BOUNDS;
  return `${fmt(lat[0])}–${fmt(lat[1])}° N, ${fmt(lon[0])}–${fmt(lon[1], 1)}° E`;
}

/**
 * Why a point cannot be asked for, or null.
 *
 * @param {{lat: number, lon: number}} point
 * @returns {string|null} the form's message in the page's language
 */
export function outside(point) {
  const { lat, lon } = PMAXTP_BOUNDS;
  if (!Number.isFinite(point.lat) || !Number.isFinite(point.lon)) return t("pmaxtp.form.error_number");
  if (point.lat < lat[0] || point.lat > lat[1] || point.lon < lon[0] || point.lon > lon[1]) {
    return t("pmaxtp.form.error_outside", { point: pointLabel(point), bounds: boundsLabel() });
  }
  return null;
}

/** The query of a point and method on the API's routes (api/pmaxtp, api/files/pmaxtp). */
export function pmaxtpQuery(point, method) {
  return { latitude: point.lat.toFixed(4), longitude: point.lon.toFixed(4), method };
}

/**
 * PMAXTP of the point by the method, while there is a point inside the box; asked again in
 * the other language when the page switches (the server's error texts follow it).
 *
 * @param {{lat: number, lon: number}|null} point
 * @param {"POT"|"AMP"} method
 * @returns {{doc: object|null, error: Error|null, loading: boolean}}
 */
export function usePmaxtp(point, method) {
  const [state, setState] = useState({ doc: null, error: null, loading: false });
  const ask = Boolean(point) && !outside(point);
  useEffect(() => {
    if (!ask) {
      setState({ doc: null, error: null, loading: false });
      return undefined;
    }
    let live = true;
    setState((old) => ({ ...old, error: null, loading: true }));
    api.pmaxtp(pmaxtpQuery(point, method)).then(
      (doc) => live && setState({ doc, error: null, loading: false }),
      (error) => live && setState({ doc: null, error, loading: false }),
    );
    return () => {
      live = false;
    };
  }, [ask, point && point.lat, point && point.lon, method, lang()]);
  return state;
}
