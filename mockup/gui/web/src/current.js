// The view „Pomiary bieżące” (plan D8, D9): IMGW-PIB's current measurements from the
// server's snapshots (api/current), asked for when the view opens and again every ten
// minutes while it stays open; the server asks IMGW-PIB at most once in ten minutes and
// keeps nothing. Also the words of their times: IMGW-PIB's API gives them in UTC
// (hydro.imgw.pl labels the same measurements „UTC”; at 08:14 UTC on 2026-11-13 the
// newest water level of the API was stamped 08:00).

import { api } from "./api.js";
import { useEffect, useState } from "./lib.js";

/** How often the open view asks the server again [ms]: the server's snapshot lifetime. */
export const REFRESH_MS = 600000;

/**
 * A time of IMGW-PIB's API as shown.
 *
 * @param {string|null} text "2026-11-12 22:20:00" (UTC)
 * @param {{year?: boolean}} [options] with the year: "12.11.2026 22:20 UTC"
 * @returns {string|null} "12.11 22:20 UTC"
 */
export function measuredAt(text, { year = false } = {}) {
  if (!text) return null;
  const [day, time = ""] = String(text).split(/[ T]/);
  const date = `${day.slice(8, 10)}.${day.slice(5, 7)}${year ? `.${day.slice(0, 4)}` : ""}`;
  return `${date}${time ? ` ${time.slice(0, 5)}` : ""} UTC`;
}

/**
 * A UTC time of the server as the browser's local clock.
 *
 * @param {string|null} iso "2026-11-13T08:11:52Z"
 * @returns {string} "09:11"
 */
export function clock(iso) {
  return iso ? new Date(iso).toLocaleTimeString("pl-PL", { hour: "2-digit", minute: "2-digit" }) : "–";
}

/** The words of a snapshot source. */
export const SOURCES = {
  states: "stany wody (mapa hydro.imgw.pl)",
  hydro: "pomiary hydrologiczne",
  meteo: "pomiary meteorologiczne",
  synop: "depesze SYNOP",
};

/**
 * The points of „Pomiary bieżące” while `active`.
 *
 * @param {boolean} active whether the view is shown
 * @returns {{doc: object|null, error: Error|null, loading: boolean}} the last answer of
 *   api/current, kept when a later request fails
 */
export function useCurrent(active) {
  const [state, setState] = useState({ doc: null, error: null, loading: false, at: 0 });
  const [round, setRound] = useState(0);
  useEffect(() => {
    if (!active) return undefined;
    const timer = setInterval(() => setRound((n) => n + 1), REFRESH_MS);
    return () => clearInterval(timer);
  }, [active]);
  useEffect(() => {
    if (!active || (state.doc && Date.now() - state.at < REFRESH_MS - 5000)) return undefined;
    let live = true;
    setState((old) => ({ ...old, loading: true }));
    api.get("api/current", {}, { memo: false }).then(
      (doc) => live && setState({ doc, error: null, loading: false, at: Date.now() }),
      (error) => live && setState((old) => ({ ...old, error, loading: false })),
    );
    return () => {
      if (live) setState((old) => ({ ...old, loading: false }));
      live = false;
    };
  }, [active, round]);
  return state;
}
