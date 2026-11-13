// The view „Pomiary bieżące” (plan D8, D9): IMGW-PIB's current measurements from the
// server's snapshots (api/current), asked for when the view opens and again every ten
// minutes while it stays open; the server asks IMGW-PIB at most once in ten minutes and
// keeps nothing. Also the times of these measurements as the page's language writes them:
// IMGW-PIB's API gives them in UTC and hydro.imgw.pl labels the same measurements „UTC”
// (at 08:14 UTC on 2026-11-13 the newest water level of the API was stamped 08:00), so
// they stay in UTC; the server's own times (a snapshot's) are the reader's clock.

import { api } from "./api.js";
import { fmtTime, lang, useEffect, useState } from "./lib.js";

/** How often the open view asks the server again [ms]: the server's snapshot lifetime. */
export const REFRESH_MS = 600000;

const stamps = new Map();

/** The format of a measurement's time in the page's language, in UTC, with or without the year. */
function stampFormat(year) {
  const key = `${lang()} ${year}`;
  let format = stamps.get(key);
  if (!format) {
    format = new Intl.DateTimeFormat(lang() === "pl" ? "pl-PL" : "en-GB", {
      day: "2-digit",
      month: "2-digit",
      ...(year ? { year: "numeric" } : {}),
      hour: "2-digit",
      minute: "2-digit",
      hourCycle: "h23",
      timeZone: "UTC",
      timeZoneName: "short",
    });
    stamps.set(key, format);
  }
  return format;
}

/**
 * A time of IMGW-PIB's API as shown, in UTC as the API gives it.
 *
 * @param {string|null} text "2026-11-12 22:20:00" (UTC)
 * @param {{year?: boolean}} [options] with the year: "12.11.2026, 22:20 UTC"
 * @returns {string|null} "12.11, 22:20 UTC" in Polish, "12/11, 22:20 UTC" in English; the
 *   text itself when it is no time
 */
export function measuredAt(text, { year = false } = {}) {
  if (!text) return null;
  const when = new Date(`${String(text).trim().replace(" ", "T")}Z`);
  if (Number.isNaN(when.getTime())) return String(text);
  return stampFormat(year).format(when);
}

/**
 * A UTC time of the server (a snapshot's, a PMAXTP answer's) on the reader's clock.
 *
 * @param {string|null} iso "2026-11-13T08:11:52Z"
 * @returns {string} "09:11" in Warsaw, "–" for none
 */
export function clock(iso) {
  return fmtTime(iso);
}

/**
 * The points of „Pomiary bieżące” while `active`.
 *
 * @param {boolean} active whether the view is shown
 * @returns {{doc: object|null, error: Error|null, loading: boolean}} the last answer of
 *   api/current (`{snapshots, hydro, meteo, attribution, terms_notice}`), kept when a later
 *   request fails
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
    // Back in the view within the snapshot's lifetime: the server would answer the same
    if (!active || (state.doc && Date.now() - state.at < REFRESH_MS - 5000)) return undefined;
    let live = true;
    setState((old) => ({ ...old, loading: true }));
    api.current().then(
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
