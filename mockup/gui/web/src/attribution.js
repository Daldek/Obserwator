// Provider attribution in the GUI (Nogat DEV §20, ECO-060). The lines come byte for byte
// from the server's one place for them, server/attribution.py: in the `attribution` and
// `terms_notice` fields of every response with data or results, and as texts in
// api/meta. This module merges the sets of a view that shows data of several sources, in
// the standard's order, as `fields` of attribution.py does. It draws them visibly, never
// in a tooltip: the lines, then the notice N and the terms, each URL a link with the same
// text.

import { api } from "./api.js";
import { html, useEffect, useState } from "./lib.js";

let loaded = null;

/**
 * The texts of api/meta's `attribution`: lines by mark, their order and the sets of each
 * data source (server/attribution.py `meta`).
 *
 * @returns {object|null} null until api/meta answers
 */
export function useTexts() {
  const [texts, setTexts] = useState(loaded);
  useEffect(() => {
    if (loaded) return undefined;
    let live = true;
    api.meta().then(
      (meta) => {
        loaded = meta.attribution;
        if (live) setTexts(loaded);
      },
      () => {},
    );
    return () => {
      live = false;
    };
  }, []);
  return texts;
}

/**
 * The lines and terms of data from the given sources, merged and ordered, each once.
 *
 * @param {object|null} texts from useTexts
 * @param {string[]} sources e.g. ["imgw", "imgw-hydro", "chmi"]
 * @returns {{attribution: string[], terms_notice: string[]}|null}
 */
export function compose(texts, sources) {
  if (!texts || !sources.length) return null;
  const lines = new Set();
  const terms = new Set();
  for (const name of sources) {
    const set = texts.sources[name];
    if (!set) continue;
    for (const mark of set.attribution) lines.add(mark);
    for (const mark of set.terms_notice) terms.add(mark);
  }
  for (const [mark, replaced] of Object.entries(texts.replaces)) {
    if (lines.has(mark)) for (const old of replaced) lines.delete(old);
  }
  return {
    attribution: texts.order.filter((mark) => lines.has(mark)).map((mark) => texts.lines[mark]),
    terms_notice: texts.terms_order.filter((mark) => terms.has(mark)).map((mark) => texts.lines[mark]),
  };
}

/**
 * The sources of a set of catalog stations, as `station_sources` of attribution.py counts
 * one: IMGW-PIB's lists and locations of danepubliczne.imgw.pl, the locations of
 * hydro.imgw.pl (`location_source` "static"), ČHMÚ.
 *
 * @param {object[]} stations entries of api/stations
 * @returns {string[]}
 */
export function catalogSources(stations) {
  const out = new Set();
  for (const station of stations) {
    if (station.provider === "IMGW-PIB") {
      out.add("imgw");
      if (station.location_source === "static" && station.lon !== null) out.add("imgw-hydro");
    } else {
      out.add("chmi");
    }
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
 * @param {{fields: {attribution: string[], terms_notice: string[]}|null, inline?: boolean,
 *   className?: string}} props the fields of a response or of compose; `inline` runs the
 *   lines on with a separator (the map's strip), otherwise each line is its own row
 * @returns {object|null}
 */
export function Attribution({ fields, inline = false, className = "" }) {
  if (!fields || !(fields.attribution || []).length) return null;
  const terms = fields.terms_notice || [];
  const classes = ["attrib", inline ? "inline" : "", className].filter(Boolean).join(" ");
  return html`<div class=${classes} role="note" aria-label="Źródło danych i warunki korzystania">
    <p class="attrib-lines">${fields.attribution.map((line) => html`<span class="attrib-line">${linked(line)}</span>`)}</p>
    ${terms.length ? html`<p class="attrib-terms">${terms.map((line) => html`<span class="attrib-line">${linked(line)}</span>`)}</p>` : null}
  </div>`;
}
