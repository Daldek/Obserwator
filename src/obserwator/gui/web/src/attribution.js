// Provider attribution in the GUI (Nogat DEV §20, ECO-060). The lines come byte for byte
// from the server's one place for them, obserwator.attribution: in the `attribution` and
// `terms_notice` fields of every response with data or results, and for each origin of
// data in the session's `attribution` (api/session: `origins.{imgw, imgw_hydro, pmaxtp,
// chmi}`, the standard's `order` and `terms_order`). This module merges the lines of a view
// that shows data of several origins, in the standard's order, each once, as
// `Attribution.__or__` does on the server. It draws them visibly, never in a tooltip: the
// lines, then the notice N and the terms, each URL a link with the same text. A public
// deployment (the session's `terms`) also shows „Regulamin” and the service's statement
// beside them (Nogat DEV-15.7, DEV-15.8): `PublicNotice`.
//
// main.js hands the session's `attribution` over with `setTexts` once api/session answers;
// `useTexts` gives it to every component that composes lines (null until then).

import { html, t, useEffect, useState } from "./lib.js";

let known = null;
const listeners = new Set();

/**
 * Hand over the attribution texts of the session (main.js, when api/session answers).
 *
 * @param {{origins: object, order: string[], terms_order: string[]}|null} texts the
 *   session's `attribution`
 */
export function setTexts(texts) {
  known = texts || null;
  for (const listener of [...listeners]) listener(known);
}

/**
 * The session's attribution texts: the lines of each origin of data and their order.
 *
 * @returns {{origins: Record<string, {attribution?: string[], terms_notice?: string[]}>,
 *   order: string[], terms_order: string[]}|null} null until the session is known
 */
export function useTexts() {
  const [texts, setState] = useState(known);
  useEffect(() => {
    listeners.add(setState);
    setState(known);
    return () => listeners.delete(setState);
  }, []);
  return texts;
}

/** The lines once each: those the standard orders in its order, any other after them. */
function ordered(order, lines) {
  const given = new Set(lines);
  const known = order.filter((line) => given.has(line));
  const listed = new Set(order);
  return [...known, ...[...given].filter((line) => !listed.has(line))];
}

/**
 * The lines and terms of data of the given origins, merged and ordered, each once.
 *
 * @param {object|null} texts from useTexts
 * @param {string[]} sources origins of the data, e.g. ["imgw", "imgw_hydro", "chmi"]
 * @returns {{attribution: string[], terms_notice: string[]}|null} null without texts or
 *   origins
 */
export function compose(texts, sources) {
  if (!texts || !sources.length) return null;
  const lines = [];
  const terms = [];
  for (const name of sources) {
    const origin = texts.origins[name];
    if (!origin) continue;
    lines.push(...(origin.attribution || []));
    terms.push(...(origin.terms_notice || []));
  }
  return { attribution: ordered(texts.order, lines), terms_notice: ordered(texts.terms_order, terms) };
}

/** The origin of a provider's catalog and archives (obserwator.attribution.provider_origin). */
const PROVIDER_ORIGINS = { "IMGW-PIB": "imgw", CHMI: "chmi" };

/**
 * The origins of a set of catalog stations, as the server counts a station's: its
 * provider's, and hydro.imgw.pl's for an IMGW-PIB station located from there
 * (`location_source` "static").
 *
 * @param {object[]} stations entries of api/stations
 * @returns {string[]} e.g. ["imgw", "imgw_hydro", "chmi"]
 */
export function catalogSources(stations) {
  const out = new Set();
  for (const station of stations) {
    const origin = PROVIDER_ORIGINS[station.provider];
    if (!origin) continue;
    out.add(origin);
    if (origin === "imgw" && station.location_source === "static" && station.lon !== null) out.add("imgw_hydro");
  }
  return [...out];
}

const URL_PART = /(https?:\/\/[^\s),”]+)/;

/** A line with each URL a link; the text stays the line's. */
function linked(line) {
  return line.split(URL_PART).map((part, index) =>
    index % 2 ? html`<a href=${part} target="_blank" rel="noopener noreferrer">${part}</a>` : part,
  );
}

/**
 * The lines and the terms, visible.
 *
 * @param {{fields: {attribution: string[], terms_notice?: string[]}|null, inline?: boolean,
 *   className?: string}} props the fields of a response or of compose; `inline` runs the
 *   lines on with a separator (the map's strip), otherwise each line is its own row
 * @returns {object|null}
 */
export function Attribution({ fields, inline = false, className = "" }) {
  if (!fields || !(fields.attribution || []).length) return null;
  const terms = fields.terms_notice || [];
  const classes = ["attrib", inline ? "inline" : "", className].filter(Boolean).join(" ");
  return html`<div class=${classes} role="note" aria-label=${t("shell.attribution")}>
    <p class="attrib-lines">${fields.attribution.map((line) => html`<span class="attrib-line">${linked(line)}</span>`)}</p>
    ${terms.length ? html`<p class="attrib-terms">${terms.map((line) => html`<span class="attrib-line">${linked(line)}</span>`)}</p>` : null}
  </div>`;
}

/**
 * „Regulamin” and the service's statement of a public deployment (Nogat DEV-15.7,
 * DEV-15.8), shown beside the attribution lines of every view; nothing when the deployment
 * is not public (no `terms` in the session).
 *
 * @param {{session: object|null, className?: string}} props the session (its `terms`)
 * @returns {object|null}
 */
export function PublicNotice({ session, className = "" }) {
  if (!session || !session.terms) return null;
  return html`<p class=${["public-notice", className].filter(Boolean).join(" ")}>
    <a class="terms-link" href=${session.terms} target="_blank" rel="noopener">${t("shell.terms")}</a>
    <span class="statement">${t("shell.statement")}</span>
  </p>`;
}
