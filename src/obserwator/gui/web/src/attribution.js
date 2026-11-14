// Provider attribution in the GUI (Nogat DEV §20, DEV-20.5, ECO-064, ECO-068). The lines
// come byte for byte from the server's one place for them, obserwator.attribution: in the
// `attribution` and `terms_notice` fields of every response with data or results, and for
// each origin of data in the session's `attribution` (api/session: `origins.{imgw,
// imgw_hydro, pmaxtp, chmi, gugik, cuzk}`, the standard's `order` and `terms_order`). This
// module merges the lines of what a view shows, in the standard's order, each once, as
// `Attribution.__or__` does on the server, and hands them to the kit's <nogat-sources>
// (`Sources`): a 12 px strip with S, P, PS, PP and the short forms of ČHMÚ's, GUGiK's and
// ČÚZK's lines, then „Źródła i warunki”, a dialog with every line, the terms and „Regulamin”
// where the deployment serves one. A view has one strip, across the page under the map and
// both panels, never one per panel or card. A public deployment also shows „Regulamin” and
// the service's statement under it (Nogat DEV-15.7, DEV-15.8): `PublicNotice`.
//
// main.js hands the session's `attribution` over with `setTexts` once api/session answers;
// `useTexts` gives it to every component that composes lines (null until then).

import "../nogat/nogat-sources.js";
import { html, t, useEffect, useMemo, useState } from "./lib.js";

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

/**
 * Every line of a session: what the page may show, for the welcome window.
 *
 * @param {object|null} texts from useTexts
 * @returns {{attribution: string[], terms_notice: string[]}|null} null without texts
 */
export function allLines(texts) {
  return texts ? compose(texts, Object.keys(texts.origins)) : null;
}

/**
 * The lines and terms of several sets, each line once: those the standard orders in its
 * order, any other after them in the order it first appears.
 *
 * @param {object|null} texts from useTexts; without them the order the lines come in
 * @param {({attribution?: string[], terms_notice?: string[]}|null)[]} sets
 * @returns {{attribution: string[], terms_notice: string[]}|null} null without a line
 */
export function merge(texts, sets) {
  const lines = [];
  const terms = [];
  for (const set of sets) {
    if (!set) continue;
    lines.push(...(set.attribution || []));
    terms.push(...(set.terms_notice || []));
  }
  if (!lines.length && !terms.length) return null;
  return {
    attribution: ordered(texts ? texts.order : [], lines),
    terms_notice: ordered(texts ? texts.terms_order : [], terms),
  };
}

/** The origin of a provider's catalog and archives (obserwator.attribution.provider_origin). */
const PROVIDER_ORIGINS = { "IMGW-PIB": "imgw", CHMI: "chmi" };
/** The origin of the packaged border a provider's catalog was checked against
 * (obserwator.attribution.border_origin, ADR-018). */
const BORDER_ORIGINS = { "IMGW-PIB": "gugik", CHMI: "cuzk" };
/** The origins of the packaged borders, PRG of GUGiK and RÚIAN of ČÚZK, while the map draws
 * them as its background. */
export const BORDER_SOURCES = ["gugik", "cuzk"];

/**
 * The origins of a set of catalog stations, as the server counts a station's: its
 * provider's, the border's its location was checked against, and hydro.imgw.pl's for an
 * IMGW-PIB station located from there (`location_source` "static").
 *
 * @param {object[]} stations entries of api/stations
 * @returns {string[]} e.g. ["imgw", "gugik", "imgw_hydro", "chmi", "cuzk"]
 */
export function catalogSources(stations) {
  const out = new Set();
  for (const station of stations) {
    const origin = PROVIDER_ORIGINS[station.provider];
    if (!origin) continue;
    out.add(origin);
    out.add(BORDER_ORIGINS[station.provider]);
    if (origin === "imgw" && station.location_source === "static" && station.lon !== null) out.add("imgw_hydro");
  }
  return [...out];
}

/** The arrays of a set, the same objects while their lines stay: <nogat-sources> redraws, and
 * closes its dialog, whenever it is handed a new array. */
function useStable(lines) {
  const key = JSON.stringify(lines);
  return useMemo(() => lines, [key]);
}

/**
 * The kit's strip of the lines (`<nogat-sources>`, Nogat DEV-20.5): S, P, PS, PP and the
 * short forms of ČHMÚ's, GUGiK's and ČÚZK's lines on screen (CK, GK, ZK), every line and
 * the terms in its dialog; nothing without lines.
 *
 * @param {{fields: {attribution?: string[], terms_notice?: string[]}|null, session:
 *   object|null}} props the fields of a response, of compose or of merge; the session
 *   (its `terms`, the regulamin of a public deployment, linked from the dialog)
 * @returns {object}
 */
export function Sources({ fields, session }) {
  const attribution = useStable((fields && fields.attribution) || []);
  const termsNotice = useStable((fields && fields.terms_notice) || []);
  const terms = session && session.terms ? session.terms : undefined;
  return html`<nogat-sources attribution=${attribution} termsNotice=${termsNotice} terms=${terms}></nogat-sources>`;
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
