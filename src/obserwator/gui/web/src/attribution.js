// Provider attribution in the GUI (Nogat DEV §20, DEV-20.5, ECO-064, ECO-068, ECO-087). The
// lines come byte for byte from the server's one place for them, obserwator.attribution: in
// the `attribution` and `terms_notice` fields of every response with data or results, and
// for each origin of data in the session's `attribution` (api/session: `origins.{imgw,
// imgw_hydro, pmaxtp, chmu, pig, gugik, cuzk}` and those of the providers fed by files, the
// standard's `order` and `terms_order`). This module merges the lines of what a view shows,
// in the standard's order, each once, as `Attribution.__or__` does on the server, and hands
// them to the kit's <nogat-sources> (`Sources`): a 12 px strip with S, P, PS, PP and the
// short forms of ČHMÚ's, PIG-PIB's, GUGiK's and ČÚZK's lines, after them the lines the
// session declares for it (`screen_lines`: a provider fed by files, its line or its short
// form, shown while the view's lines carry it), then „Źródła i warunki”, a dialog with every
// line, the terms and „Regulamin” where the deployment serves one. A view has one strip,
// across the page under the map and both panels, never one per panel or card. A public
// deployment also links „Regulamin” at the bottom of the left panel (Nogat DEV-15.7):
// `TermsLink`.
//
// PIG-PIB's W names the years and days of each product's data (ADR-035): the session's
// `fillable` are the formulas whose `<period>` and `<date>` each product fills. A filled
// line takes its formula's place in the order, and the W lines of what a view shows merge
// into one naming the first and the last year and day of them all, an unfilled one giving
// way to any filled (the server's `_canonical` and `_merged_w`).
//
// main.js hands the session's `attribution` over with `setTexts` once api/session answers;
// `useTexts` gives it to every component that composes lines (null until then). The origins
// of a provider's catalog are the session's too (words.js `providerOf`).

import "../nogat/nogat-sources.js";
import { html, t, useEffect, useMemo, useState } from "./lib.js";
import { providerOf } from "./words.js";

let known = null;
const listeners = new Set();

/**
 * Hand over the attribution texts of the session (main.js, when api/session answers).
 *
 * @param {{origins: object, order: string[], terms_order: string[], screen_lines:
 *   object[]}|null} texts the session's `attribution`
 */
export function setTexts(texts) {
  known = texts || null;
  for (const listener of [...listeners]) listener(known);
}

/**
 * The session's attribution texts: the lines of each origin of data and their order.
 *
 * @returns {{origins: Record<string, {attribution?: string[], terms_notice?: string[]}>,
 *   order: string[], terms_order: string[], screen_lines: object[]}|null} null until the
 *   session is known
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

/** A fillable formula's pattern: its text byte for byte, `<period>` a year or the first and
 * the last joined by an en dash, `<date>` a day or two joined by a spaced en dash. */
function fillPattern(formula) {
  const source = formula
    .replace(/[.*+?^${}()|[\]\\]/g, "\\$&")
    .replace("<period>", "(?<period>[0-9]{4}(?:–[0-9]{4})?)")
    .replace("<date>", "(?<date>[0-9]{4}-[0-9]{2}-[0-9]{2}(?: – [0-9]{4}-[0-9]{2}-[0-9]{2})?)");
  return new RegExp(`^${source}$`);
}

/** The patterns of the session's fillable formulas, made once per session. */
const PATTERNS = new WeakMap();

function patterns(texts) {
  if (!texts) return [];
  if (!PATTERNS.has(texts)) PATTERNS.set(texts, (texts.fillable || []).map((formula) => ({ formula, pattern: fillPattern(formula) })));
  return PATTERNS.get(texts);
}

/** A line's formula: the fillable one it fills or is, else null. */
function formulaOf(found, line) {
  const item = found.find(({ formula, pattern }) => line === formula || pattern.test(line));
  return item ? item.formula : null;
}

/**
 * One line of a formula's lines: the first and the last year and day of every filled one,
 * the formula itself when none is filled.
 */
function mergedLine(formula, pattern, lines) {
  const years = [];
  const days = [];
  for (const line of lines) {
    const match = pattern.exec(line);
    if (!match) continue;
    years.push(...match.groups.period.split("–").map(Number));
    days.push(...match.groups.date.split(" – "));
  }
  if (!years.length) return formula;
  const first = Math.min(...years);
  const last = Math.max(...years);
  days.sort();
  const period = first === last ? String(first) : `${first}–${last}`;
  const date = days[0] === days[days.length - 1] ? days[0] : `${days[0]} – ${days[days.length - 1]}`;
  return formula.replace("<period>", period).replace("<date>", date);
}

/**
 * The lines once each: those the standard orders in its order, a filled line in its
 * formula's place, any other after them; the lines of each fillable formula merged into
 * one in the place of the first (`mergedLine`).
 */
function ordered(texts, order, lines) {
  const found = patterns(texts);
  const given = [...new Set(lines)];
  const merged = [];
  const done = new Set();
  for (const line of given) {
    const formula = found.length ? formulaOf(found, line) : null;
    if (formula === null) merged.push(line);
    else if (!done.has(formula)) {
      done.add(formula);
      const { pattern } = found.find((item) => item.formula === formula);
      merged.push(mergedLine(formula, pattern, given.filter((other) => formulaOf(found, other) === formula)));
    }
  }
  const place = new Map(order.map((line, index) => [line, index]));
  const key = (line) => (found.length ? formulaOf(found, line) || line : line);
  const known = merged.filter((line) => place.has(key(line))).sort((a, b) => place.get(key(a)) - place.get(key(b)));
  return [...known, ...merged.filter((line) => !place.has(key(line)))];
}

/**
 * The lines and terms of data of the given origins, merged and ordered, each once.
 *
 * @param {object|null} texts from useTexts
 * @param {string[]} sources origins of the data, e.g. ["imgw", "imgw_hydro", "chmu"]
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
  return { attribution: ordered(texts, texts.order, lines), terms_notice: ordered(texts, texts.terms_order, terms) };
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
 * order, any other after them in the order it first appears; the W lines of PIG-PIB merged
 * into one (`ordered`).
 *
 * @param {object|null} texts from useTexts; without them the order the lines come in, no
 *   line merged
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
    attribution: ordered(texts, texts ? texts.order : [], lines),
    terms_notice: ordered(texts, texts ? texts.terms_order : [], terms),
  };
}

/** The origins of the packaged borders, PRG of GUGiK and RÚIAN of ČÚZK, while the map draws
 * them as its background. */
export const BORDER_SOURCES = ["gugik", "cuzk"];
/** The location sources of hydro.imgw.pl: its map's file and its meteorological station pages. */
const HYDRO_BACK_LOCATIONS = new Set(["static", "pl.imgw.meteo_details"]);

/**
 * The origins of a set of catalog stations, as the server counts a station's: its
 * provider's (the session's `origin`, obserwator.attribution.provider_origin), that of the
 * border its location was checked against (`border`, border_origin, ADR-018), and
 * hydro.imgw.pl's for an IMGW-PIB station located from there (`location_source` "static"
 * or "pl.imgw.meteo_details"). A provider the session does not name counts none.
 *
 * @param {object[]} stations entries of api/stations
 * @returns {string[]} e.g. ["imgw", "gugik", "imgw_hydro", "chmu", "cuzk"]
 */
export function catalogSources(stations) {
  const out = new Set();
  for (const station of stations) {
    const provider = providerOf(station.provider);
    if (!provider) continue;
    out.add(provider.origin);
    out.add(provider.border);
    if (provider.origin === "imgw" && HYDRO_BACK_LOCATIONS.has(station.location_source) && station.lon !== null) out.add("imgw_hydro");
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
 * short forms of ČHMÚ's, GUGiK's and ČÚZK's lines on screen (CK, GK, ZK), then the lines the
 * session declares for it (its `attribution.screen_lines`: those of the providers fed by
 * files, each shown while the fields carry it), every line and the terms in its dialog;
 * nothing without lines.
 *
 * @param {{fields: {attribution?: string[], terms_notice?: string[]}|null, session:
 *   object|null}} props the fields of a response, of compose or of merge; the session
 *   (its `terms`, the regulamin of a public deployment, linked from the dialog, and the
 *   lines declared for the strip)
 * @returns {object}
 */
export function Sources({ fields, session }) {
  const attribution = useStable((fields && fields.attribution) || []);
  const termsNotice = useStable((fields && fields.terms_notice) || []);
  const screenLines = useStable((session && session.attribution.screen_lines) || []);
  const terms = session && session.terms ? session.terms : undefined;
  return html`<nogat-sources attribution=${attribution} termsNotice=${termsNotice} screenLines=${screenLines} terms=${terms}></nogat-sources>`;
}

/**
 * „Regulamin” of a public deployment (Nogat DEV-15.7), a small quiet link at the bottom of
 * the left panel, opening the terms in a new tab; nothing when the deployment is not public
 * (no `terms` in the session).
 *
 * @param {{session: object|null}} props the session (its `terms`)
 * @returns {object|null}
 */
export function TermsLink({ session }) {
  if (!session || !session.terms) return null;
  return html`<a class="terms-link" href=${session.terms} target="_blank" rel="noopener">${t("shell.terms")}</a>`;
}
