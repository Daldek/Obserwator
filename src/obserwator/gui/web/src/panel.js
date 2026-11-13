// The right panel „Stacja” (GUI plan D11): the station's header (name, river, code, provider,
// kind, active or not), then its sections as an accordion in the author's order:
// „Informacje o stacji”, „Pomiary bieżące”, „Dane pomiarowo-obserwacyjne”, the
// hydrological (HYDRO_SECTIONS) or meteorological (METEO_SECTIONS) analyses that apply to
// the station, then „Pobierz”. A registry entry is `{id, title, component, available?,
// part?}`: `title` is a key of the catalog, drawn as the card's header; the open card
// draws `component({station, session, analyses})`, where `analyses` is the list of
// api/analyses/{code}, fetched here once; `available(station, ids)`, given the Set of the
// list's ids, leaves out a section no analysis of which applies. A station without series
// shows its catalog data and says the data root holds none. A section that throws shows
// its error in its card; the others go on.
//
// Under each open card the panel draws the provider's lines and terms (Nogat DEV §20):
// those of the station's `attribution_parts` named by the entry's `part` ("catalog",
// "series", by default "results"), joined with the lines of every analysis document the
// card's sections receive (`ResultLines` of sections/common.js; ČHMÚ's line of results
// computed by Hydrolog exists only there). `part: null` means the section draws its own
// („Pomiary bieżące”).

import { Component } from "../vendor/preact/preact.mjs";
import { api } from "./api.js";
import { Attribution, catalogSources, compose, useTexts } from "./attribution.js";
import { fmt, fmtDateTime, html, t, tn, useCallback, useEffect, useMemo, useRef, useState } from "./lib.js";
import { ResultLines, Section } from "./sections/common.js";
import { DANE } from "./sections/dane.js";
import { HYDRO_SECTIONS } from "./sections/hydro/index.js";
import { METEO_SECTIONS } from "./sections/meteo/index.js";
import { Command, Licence, POBIERZ } from "./sections/pobierz.js";
import { STACJA } from "./sections/stacja.js";
import { TERAZ } from "./sections/teraz.js";
import { DATASET_STEPS, datasetTitle, kindName, providerFullName, providerName } from "./words.js";

/** The providers of the catalogs, in the order the panel lists them. */
const PROVIDERS = ["IMGW-PIB", "CHMI"];
/** The names of the formats of a stations file. */
const STATIONS_FORMATS = { geojson: "GeoJSON", csv: "CSV" };

/** The analysis sections of a kind of station. */
function analysisSections(kind) {
  return kind === "hydro" ? HYDRO_SECTIONS : kind === "meteo" ? METEO_SECTIONS : [];
}

/**
 * The sections of a station, in the panel's order.
 *
 * @param {object} station the document of api/stations/{code}
 * @param {Set<string>|null} ids the analysis ids that apply to it; null while unknown,
 *   which leaves the analyses out
 * @returns {object[]} registry entries
 */
export function stationSections(station, ids) {
  const own = station.datasets.length && ids ? analysisSections(station.properties.kind) : [];
  return [STACJA, TERAZ, DANE, ...own.filter((entry) => !entry.available || entry.available(station, ids)), POBIERZ];
}

/**
 * The title of a section of a station of this kind.
 *
 * @param {string|undefined} kind "hydro" or "meteo"
 * @param {string} id the section's id
 * @returns {string|null} its title in the page's language, or null for no such section
 */
export function sectionTitle(kind, id) {
  const entry = [STACJA, TERAZ, DANE, ...analysisSections(kind), POBIERZ].find((item) => item.id === id);
  return entry ? t(entry.title) : null;
}

/** A section's error, in its card: one broken section leaves the panel working. */
class Guard extends Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }

  componentDidCatch(error) {
    this.setState({ error });
  }

  render() {
    const error = this.state.error;
    if (error) return html`<p class="ana-error" role="alert">${t("station.section_failed", { message: String(error.message || error) })}</p>`;
    return this.props.children;
  }
}

function Chevron() {
  return html`<svg class="chev" viewBox="0 0 20 20" aria-hidden="true"><path d="M5 8l5 5 5-5" /></svg>`;
}

/**
 * The lines and terms of several sets, each line once, in the order it first appears.
 *
 * @param {({attribution?: string[], terms_notice?: string[]}|null)[]} sets
 * @returns {{attribution: string[], terms_notice: string[]}|null}
 */
function joinLines(sets) {
  const attribution = [];
  const terms = [];
  for (const set of sets) {
    if (!set) continue;
    for (const line of set.attribution || []) if (!attribution.includes(line)) attribution.push(line);
    for (const line of set.terms_notice || []) if (!terms.includes(line)) terms.push(line);
  }
  return attribution.length ? { attribution, terms_notice: terms } : null;
}

/** The header of the station. */
function StationHead({ station }) {
  const p = station.properties;
  return html`<div class="station-head">
    <div class="station-title">
      <h3>${p.name || station.code}</h3>
      ${p.river ? html`<span class="river">${p.river}</span>` : null}
    </div>
    <div class="station-tags">
      <code class="chip">${station.code}</code>
      <span class="chip" title=${providerFullName(station.provider)}>${providerName(station.provider)}</span>
      <span class=${`chip kind-${p.kind}`}>${kindName(p.kind)}</span>
      <span class=${`badge ${p.active ? "ok" : "warn"}`}>${p.active ? t("station.active") : t("station.inactive")}</span>
      ${station.lon === null ? html`<span class="badge warn">${t("station.no_location")}</span>` : null}
    </div>
    ${station.datasets.length ? null : html`<p class="note-box">${t("station.no_series")}</p>`}
  </div>`;
}

/** One card of the accordion: its header, and when open its section and the lines under it. */
function Card({ entry, station, session, analyses, open, onToggle }) {
  const [reported, setReported] = useState([]);
  const seen = useRef(new Set());
  // Stable for the card's life, so the sections' effects that call it run once per document
  const collect = useCallback((doc) => {
    if (!doc || !(doc.attribution || []).length) return;
    const key = JSON.stringify([doc.attribution, doc.terms_notice || []]);
    if (seen.current.has(key)) return;
    seen.current.add(key);
    setReported((old) => [...old, { attribution: doc.attribution, terms_notice: doc.terms_notice || [] }]);
  }, []);
  const Body = entry.component;
  const body = `sec-${entry.id}`;
  const lines = entry.part === null ? null : joinLines([(station.attribution_parts || {})[entry.part || "results"], ...reported]);
  return html`<section class=${`acc-item${open ? " open" : ""}`} data-section=${entry.id}>
    <h3 class="acc-head">
      <button type="button" aria-expanded=${open} aria-controls=${open ? body : undefined} onClick=${() => onToggle(entry.id)}>
        <span class="acc-title">${t(entry.title)}</span>
        <${Chevron} />
      </button>
    </h3>
    ${open
      ? html`<div class="acc-body" id=${body}>
          <${ResultLines.Provider} value=${collect}>
            <${Guard}><${Body} station=${station} session=${session} analyses=${analyses} /></${Guard}>
          </${ResultLines.Provider}>
          <${Attribution} fields=${lines} className="sec-attrib" />
        </div>`
      : null}
  </section>`;
}

/**
 * The panel's body for a selected station.
 *
 * @param {{code: string, session: object|null, open: string[], focus?: string|null,
 *   onToggle: (id: string) => void}} props the station, api/session, the open sections,
 *   the section the address named (scrolled into view once) and the toggle
 * @returns {object}
 */
export function StationPanel({ code, session, open, focus, onToggle }) {
  const [state, setState] = useState({ station: null, error: null });
  const [list, setList] = useState({ analyses: null, error: null });
  const focused = useRef(false);
  useEffect(() => {
    let live = true;
    setState({ station: null, error: null });
    setList({ analyses: null, error: null });
    focused.current = false;
    api.station(code).then(
      (station) => live && setState({ station, error: null }),
      (error) => live && setState({ station: null, error }),
    );
    api.analyses(code).then(
      (doc) => live && setList({ analyses: doc.analyses, error: null }),
      (error) => live && setList({ analyses: [], error }),
    );
    return () => {
      live = false;
    };
  }, [code]);
  const ids = useMemo(() => (list.analyses ? new Set(list.analyses.map((item) => item.analysis)) : null), [list.analyses]);
  const station = state.station;
  const sections = station ? stationSections(station, ids) : [];
  useEffect(() => {
    // The address' section comes into view once its card is drawn, unless it is the first
    if (!station || !focus || focused.current) return;
    const card = document.querySelector(`.acc-item[data-section="${CSS.escape(focus)}"]`);
    if (card && focus !== sections[0].id) card.scrollIntoView({ block: "start" });
    if (card || ids) focused.current = true;
  }, [station, ids]);
  if (state.error) return html`<p class="ana-error" role="alert">${state.error.message}</p>`;
  if (!station) return html`<p class="muted">${t("station.loading")}</p>`;
  // Where the analyses come once listed: after „Dane pomiarowo-obserwacyjne”
  const waiting = station.datasets.length > 0 && analysisSections(station.properties.kind).length > 0 && !ids;
  const card = (entry) => html`<${Card}
    key=${entry.id}
    entry=${entry}
    station=${station}
    session=${session}
    analyses=${list.analyses}
    open=${open.includes(entry.id)}
    onToggle=${onToggle}
  />`;
  return html`<div class="station-panel">
    <${StationHead} station=${station} />
    <div class="acc">
      ${sections.slice(0, 3).map(card)}
      ${waiting ? html`<p class="note" role="status">${t("station.analyses_loading")}</p>` : null}
      ${list.error ? html`<p class="ana-error" role="alert">${t("station.analyses_failed", { message: list.error.message })}</p>` : null}
      ${sections.slice(3).map(card)}
    </div>
  </div>`;
}

/**
 * „Pobierz listę stacji”: the stations of the list's provider and kind as the files of
 * `export_stations` (api/downloads/stations), each format's command line, the licences and
 * the lines; fetched again when the provider or the kind changes.
 *
 * @param {{provider: string|null, kind: string|null}} props null for every one
 * @returns {object}
 */
function StationsFiles({ provider, kind }) {
  const [state, setState] = useState({ doc: null, error: null });
  useEffect(() => {
    let live = true;
    setState({ doc: null, error: null });
    api.stationsDownloads({ provider, kind }).then(
      (doc) => live && setState({ doc, error: null }),
      (error) => live && setState({ doc: null, error }),
    );
    return () => {
      live = false;
    };
  }, [provider, kind]);
  const { doc, error } = state;
  const formats = doc ? Object.keys(doc.formats) : [];
  return html`<div class="stations-files">
    <${Section} title=${t("station.none.files")} info=${t("station.none.files_info")}>
      <table class="params compact">
        <tbody>
          <tr><th scope="row">${t("stations.list.provider")}</th><td>${provider ? providerName(provider) : t("stations.list.provider_all")}</td></tr>
          <tr><th scope="row">${t("stations.list.kind")}</th><td>${kind ? t(`stations.list.kind_${kind}`) : t("stations.list.kind_all")}</td></tr>
          <tr><th scope="row">${t("station.none.files_stations")}</th><td class="files-count">${doc ? fmt(doc.stations) : "…"}</td></tr>
        </tbody>
      </table>
      <p class="note">${t("station.none.files_note")}</p>
      ${error
        ? html`<p class="ana-error" role="alert">${t("station.none.files_failed", { message: error.message })}</p>`
        : doc
          ? html`<div class="btn-row files">
                ${formats.map(
                  (key) => html`<a class="btn sm" href=${doc.formats[key].url} download=${doc.formats[key].file} data-format=${key}>
                    <span class="fmt">${STATIONS_FORMATS[key] || key}</span>${doc.formats[key].file}
                  </a>`,
                )}
              </div>
              ${formats.map(
                (key) => html`<div data-format=${key}><${Command} line=${doc.formats[key].command} label=${t("station.none.files_cli", { format: STATIONS_FORMATS[key] || key })} /></div>`,
              )}
              ${doc.licences.map((licence) => html`<${Licence} licence=${licence} />`)}
              <${Attribution} fields=${doc} className="sec-attrib" />`
          : html`<p class="muted" role="status">${t("station.files.loading")}</p>`}
    </${Section}>
  </div>`;
}

/**
 * The panel without a station: how to choose one, what the data root holds and the
 * stations of the list's provider and kind to download.
 *
 * @param {{session: object|null, stations: object[], provider?: string, kind?: string}}
 *   props api/session, the stations of api/stations and the list's provider and kind
 *   filters ("all" or none for every one)
 * @returns {object}
 */
export function NoStation({ session, stations, provider = "all", kind = "all" }) {
  const texts = useTexts();
  const count = (test) => fmt(stations.filter(test).length);
  const root = session ? session.root : null;
  const held = (root && root.series) || {};
  const catalogs = (root && root.catalogs) || {};
  const series = Object.entries(held);
  const missing = Object.keys(DATASET_STEPS).filter((key) => !held[key]);
  return html`<div class="no-station">
    <p class="hint-box">${t("station.none.hint")}</p>
    ${root && root.error ? html`<p class="ana-error" role="alert">${t("station.none.root_error", { message: root.error.message })}</p>` : null}
    <h3 class="group-title">${t("station.none.catalogs")}</h3>
    <table class="params compact">
      <tbody>
        ${PROVIDERS.map(
          (id) => html`<tr>
            <th scope="row">
              ${t("station.none.provider_kinds", { provider: providerName(id) })}
              ${catalogs[id]
                ? html`<span class="row-sub">${t("station.none.catalog_version", { version: catalogs[id].version, when: fmtDateTime(catalogs[id].downloaded_at) })}</span>`
                : null}
            </th>
            <td>${count((s) => s.provider === id && s.kind === "hydro")} · ${count((s) => s.provider === id && s.kind === "meteo")}</td>
          </tr>`,
        )}
        <tr><th scope="row">${t("station.none.with_series")}</th><td>${count((s) => s.datasets.length > 0)}</td></tr>
        <tr><th scope="row">${t("station.none.without_location")}</th><td>${count((s) => s.lon === null)}</td></tr>
      </tbody>
    </table>
    <${StationsFiles} provider=${provider === "all" ? null : provider} kind=${kind === "all" ? null : kind} />
    <h3 class="group-title">${t("station.none.series")}</h3>
    ${series.length
      ? html`<table class="params compact">
          <tbody>
            ${series.map(
              ([key, value]) => html`<tr>
                <th scope="row">${datasetTitle(key)}<span class="row-sub">${t("station.version", { version: value.version })}</span></th>
                <td>${tn("station.none.stations", value.stations)}</td>
              </tr>`,
            )}
          </tbody>
        </table>`
      : html`<p class="muted">${t("station.none.no_series")}</p>`}
    ${series.length && missing.length ? html`<p class="note">${t("station.none.missing", { datasets: missing.map(datasetTitle).join(", ") })}</p>` : null}
    ${session
      ? html`<p class="note">
          Obserwator ${session.version.obserwator} · ${session.version.hydrolog ? `Hydrolog ${session.version.hydrolog}` : t("station.none.no_hydrolog")}
        </p>`
      : null}
    <${Attribution} fields=${compose(texts, catalogSources(stations))} className="sec-attrib" />
  </div>`;
}
