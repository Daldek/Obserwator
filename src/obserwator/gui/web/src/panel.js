// The right panel „Stacja” (GUI plan D11): the station's header (name, river, code, provider,
// kind and, of a groundwater object, whether a bore or a spring, active or not; of a
// provider that is no national meteorological and hydrological service, hydromet P11, the
// chip „Inne źródło” first among its tags and under them P8's notice in the provider's own
// words, the session's `source_notice`; the record of its series, a dataset's unverified data
// labelled), then its sections as an accordion in the author's order: „Informacje o
// stacji”, „Pomiary bieżące” (not of a groundwater object: no current data are served for
// one, ADR-032), „Dane pomiarowo-obserwacyjne”, the hydrological (HYDRO_SECTIONS) or
// meteorological (METEO_SECTIONS) analyses that apply to the station, then „Pobierz”; every
// chart and table of a station of another source carries the chip „Inne źródło” too
// (`ChartBadge` of charts/chart.js). A registry entry is `{id, title, component,
// available?, part?}`: `title` is a key of the catalog, drawn as the card's header; the
// open card draws `component({station, session, analyses})`, where `analyses` is the list
// of api/analyses/{code}, fetched here once; `available(station, ids)`, given the Set of the
// list's ids, leaves out a section no analysis of which applies. A station without series
// shows its catalog data and says the data root holds none. A section that throws shows its
// error in its card; the others go on.
//
// The panel hands the lines and terms of what it shows (Nogat DEV §20, DEV-20.5) to the
// view's one strip (`onLines`, main.js): the station's catalog lines of its header,
// and for each open card the station's `attribution_parts` named by the entry's `part`
// ("catalog", "series", by default "results"; `null` for none) joined with the lines of
// every document the card's sections receive (`ResultLines` of sections/common.js; ČHMÚ's
// line of results computed by Hydrolog exists only there). No card draws lines of its own.

import { Component } from "../vendor/preact/preact.mjs";
import { api } from "./api.js";
import { catalogSources, compose, merge, useTexts } from "./attribution.js";
import { scopeOf } from "./instance.js";
import { ChartBadge, fmt, fmtDateTime, html, t, tn, useCallback, useEffect, useMemo, useRef, useState } from "./lib.js";
import { ResultLines, Section, UnverifiedFlag } from "./sections/common.js";
import { DANE } from "./sections/dane.js";
import { HYDRO_SECTIONS } from "./sections/hydro/index.js";
import { METEO_SECTIONS } from "./sections/meteo/index.js";
import { Command, Licence, POBIERZ } from "./sections/pobierz.js";
import { STACJA } from "./sections/stacja.js";
import { TERAZ } from "./sections/teraz.js";
import {
  classGroups,
  datasetShort,
  datasetTitle,
  groundwaterKindName,
  kindName,
  providerFullName,
  providerName,
  providerOf,
  seriesDatasets,
  shownKinds,
  sourceClass,
  sourceClassName,
} from "./words.js";

/** The names of the formats of a stations file. */
const STATIONS_FORMATS = { geojson: "GeoJSON", csv: "CSV" };

/** The analysis sections of a kind of station. */
function analysisSections(kind) {
  return kind === "hydro" ? HYDRO_SECTIONS : kind === "meteo" ? METEO_SECTIONS : [];
}

/** The sections before the analyses: „Pomiary bieżące” only of a station with current data, none of a groundwater object. */
function leadSections(kind) {
  return kind === "groundwater" ? [STACJA, DANE] : [STACJA, TERAZ, DANE];
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
  const kind = station.properties.kind;
  const own = station.datasets.length && ids ? analysisSections(kind) : [];
  return [...leadSections(kind), ...own.filter((entry) => !entry.available || entry.available(station, ids)), POBIERZ];
}

/**
 * The title of a section of a station of this kind.
 *
 * @param {string|undefined} kind "hydro", "meteo" or "groundwater"
 * @param {string} id the section's id
 * @returns {string|null} its title in the page's language, or null for no such section
 */
export function sectionTitle(kind, id) {
  const entry = [...leadSections(kind), ...analysisSections(kind), POBIERZ].find((item) => item.id === id);
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
 * Hand the lines of a component to the panel's foot while it is drawn, and none once it is
 * gone.
 *
 * @param {(lines: object|null) => void} onLines where the lines go
 * @param {{attribution: string[], terms_notice: string[]}|null} lines
 */
function useLines(onLines, lines) {
  const key = JSON.stringify(lines);
  useEffect(() => onLines(lines), [key]);
  useEffect(() => () => onLines(null), []);
}

/** The years of a dataset's values at the station, null without any. */
function datasetYears(entry) {
  const spans = Object.values(entry.variables).filter((v) => v.first && v.last);
  if (!spans.length) return null;
  return { first: +spans.map((v) => v.first).sort()[0].slice(0, 4), last: +spans.map((v) => v.last).sort().at(-1).slice(0, 4) };
}

/**
 * The station's record (ADR-022): its years over every series, and the dataset of each
 * part, labelled where its series are unverified.
 */
function Record({ station }) {
  const parts = station.datasets.map((entry) => ({ key: entry.dataset, years: datasetYears(entry) })).filter((part) => part.years);
  if (!station.first || !parts.length) return null;
  parts.sort((a, b) => a.years.first - b.years.first);
  return html`<p class="station-record small">
    ${t("station.record", { years: `${station.first}–${station.last}` })}${" "}
    ${parts.map(
      (part, at) => html`${at ? " · " : ""}<span title=${datasetTitle(part.key)}>${datasetShort(part.key)} ${part.years.first}–${part.years.last}<${UnverifiedFlag} dataset=${part.key} /></span>`,
    )}
  </p>`;
}

/**
 * The header of the station; of a provider of the class "other" (hydromet P11) opening with
 * the chip of its class and, under the tags, P8's notice in the provider's own words (the
 * session's `source_notice`, else the page's own note).
 */
function StationHead({ station }) {
  const p = station.properties;
  const other = sourceClass(station.provider) === "other";
  const provider = providerOf(station.provider);
  return html`<div class="station-head">
    <div class="station-title">
      <h3>${p.name || station.code}</h3>
      ${p.river ? html`<span class="river">${p.river}</span>` : null}
    </div>
    <div class="station-tags">
      ${other ? html`<span class="chip" data-part="source-class">${t("station.source_other")}</span>` : null}
      <code class="chip">${station.code}</code>
      <span class="chip" title=${providerFullName(station.provider)}>${providerName(station.provider)}</span>
      <span class=${`chip kind-${p.kind}`}>${kindName(p.kind)}</span>
      ${p.groundwater_kind ? html`<span class="chip">${groundwaterKindName(p.groundwater_kind)}</span>` : null}
      <span class=${`badge ${p.active ? "ok" : "warn"}`}>${p.active ? t("station.active") : t("station.inactive")}</span>
      ${station.lon === null ? html`<span class="badge warn">${t("station.no_location")}</span>` : null}
    </div>
    ${other ? html`<p class="note-box" data-part="source-note">${(provider && provider.source_notice) || t("station.source_other_note")}</p>` : null}
    <${Record} station=${station} />
    ${station.datasets.length ? null : html`<p class="note-box">${t("station.no_series")}</p>`}
  </div>`;
}

/** One card of the accordion: its header, and when open its section; its lines go to `onLines`. */
function Card({ entry, station, session, analyses, open, onToggle, onLines }) {
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
  const own = entry.part === null ? null : (station.attribution_parts || {})[entry.part || "results"];
  const lines = open ? merge(null, [own, ...reported]) : null;
  const key = JSON.stringify(lines);
  useEffect(() => onLines(entry.id, lines), [key]);
  useEffect(() => () => onLines(entry.id, null), []);
  const Body = entry.component;
  const body = `sec-${entry.id}`;
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
        </div>`
      : null}
  </section>`;
}

/**
 * The panel's body for a selected station.
 *
 * @param {{code: string, session: object|null, open: string[], focus?: string|null,
 *   onToggle: (id: string) => void, onLines: (lines: object|null) => void}} props the
 *   station, api/session, the open sections, the section the address named (scrolled into
 *   view once), the toggle and where the lines of what the panel shows go
 * @returns {object}
 */
export function StationPanel({ code, session, open, focus, onToggle, onLines }) {
  const texts = useTexts();
  const [state, setState] = useState({ station: null, error: null });
  const [list, setList] = useState({ analyses: null, error: null });
  const [cards, setCards] = useState({});
  const focused = useRef(false);
  const cardLines = useCallback((id, lines) => setCards((old) => (old[id] === lines ? old : { ...old, [id]: lines })), []);
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
  const parts = (station && station.attribution_parts) || {};
  useLines(onLines, station ? merge(texts, [parts.catalog, ...sections.map((entry) => cards[entry.id])]) : null);
  if (state.error) return html`<p class="ana-error" role="alert">${state.error.message}</p>`;
  if (!station) return html`<p class="muted">${t("station.loading")}</p>`;
  // Where the analyses come once listed: after „Dane pomiarowo-obserwacyjne”
  const lead = leadSections(station.properties.kind).length;
  const analysed = station.datasets.length > 0 && analysisSections(station.properties.kind).length > 0;
  const waiting = analysed && !ids;
  const card = (entry) => html`<${Card}
    key=${entry.id}
    entry=${entry}
    station=${station}
    session=${session}
    analyses=${list.analyses}
    open=${open.includes(entry.id)}
    onToggle=${onToggle}
    onLines=${cardLines}
  />`;
  // Every chart and table of a station of another source carries its class (hydromet P11)
  const badge = sourceClass(station.provider) === "other" ? t("station.source_other") : null;
  return html`<div class="station-panel">
    <${StationHead} station=${station} />
    <${ChartBadge.Provider} value=${badge}>
      <div class="acc">
        ${sections.slice(0, lead).map(card)}
        ${waiting ? html`<p class="note" role="status">${t("station.analyses_loading")}</p>` : null}
        ${list.error ? html`<p class="ana-error" role="alert">${t("station.analyses_failed", { message: list.error.message })}</p>` : null}
        ${analysed && ids && ids.size === 0 && !list.error ? html`<p class="note" data-part="no-analyses">${t("station.analyses_none")}</p>` : null}
        ${sections.slice(lead).map(card)}
      </div>
    </${ChartBadge.Provider}>
  </div>`;
}

/**
 * „Pobierz listę stacji”: the stations of the list's provider and kind as the files of
 * `export_stations` (api/downloads/stations), each format's command line and the licences;
 * fetched again when the provider or the kind changes. Its answer, with its lines, goes to
 * `onDoc`.
 *
 * @param {{provider: string|null, kind: string|null, onDoc: (doc: object|null) => void}}
 *   props the one provider the list's class switch and chips leave, and the list's kind;
 *   null for every one
 * @returns {object}
 */
function StationsFiles({ provider, kind, onDoc }) {
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
  useEffect(() => onDoc(doc), [doc]);
  const formats = doc ? Object.keys(doc.formats) : [];
  return html`<div class="stations-files">
    <${Section} title=${t("station.none.files")} info=${t("station.none.files_info")} guide="lista-stacji">
      <table class="params compact">
        <tbody>
          <tr><th scope="row">${t("station.none.files_provider")}</th><td>${provider ? providerName(provider) : t("station.none.files_provider_all")}</td></tr>
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
              ${doc.licences.map((licence) => html`<${Licence} licence=${licence} />`)}`
          : html`<p class="muted" role="status">${t("station.files.loading")}</p>`}
    </${Section}>
  </div>`;
}

/**
 * The panel without a station: how to choose one, what the data root holds and the
 * stations of the list's provider and kind to download; on an operator's instance only of
 * the providers it serves (ADR-025). The catalogs' stations are counted by provider, in the
 * order of the list's chips (words.js `classGroups`), and where the providers are of both
 * classes of sources, by class with its providers under it (hydromet P12).
 *
 * @param {{session: object|null, stations: object[], provider?: string|null, kind?: string,
 *   onLines: (lines: object|null) => void}} props api/session, the stations of
 *   api/stations, the one provider the list's class switch and chips leave (list.js
 *   `chosenProvider`; null for more) and the list's kind ("all" for every one), and where
 *   the lines of the catalogs and of the stations files go
 * @returns {object}
 */
export function NoStation({ session, stations, provider = null, kind = "all", onLines }) {
  const texts = useTexts();
  const [files, setFiles] = useState(null);
  useLines(onLines, merge(texts, [compose(texts, catalogSources(stations)), files]));
  const count = (test) => fmt(stations.filter(test).length);
  const root = session ? session.root : null;
  const held = (root && root.series) || {};
  const catalogs = (root && root.catalogs) || {};
  const analyses = (root && root.analyses) || {};
  const series = Object.entries(held);
  const scope = scopeOf(session);
  const providers = [...new Set([...scope.providers, ...stations.map((s) => s.provider)])];
  // A dataset the root may hold but does not, of a served provider and of a kind offered
  // for its stations: a groundwater dataset only where its catalog has a groundwater object;
  // never an hourly series (ADR-031), built from the captures and not served while private
  const offered = Object.fromEntries(providers.map((id) => [id, shownKinds(stations.filter((s) => s.provider === id))]));
  const missing = Object.entries(seriesDatasets())
    .filter(([key, dataset]) => !held[key] && dataset.step !== "hour" && (offered[dataset.provider] || []).includes(dataset.kind))
    .map(([key]) => key);
  const groups = classGroups(providers, scope.featured);
  const byClass = groups.length > 1;
  // „IMGW-PIB: hydrologiczne · meteorologiczne” and its counts, of a provider or a class
  const named = (name, kinds) => t(kinds.includes("groundwater") ? "station.none.catalog_kinds_groundwater" : "station.none.catalog_kinds", { name });
  const counted = (own, kinds) => kinds.map((which) => fmt(own.filter((s) => s.kind === which).length)).join(" · ");
  const rows = groups.flatMap((group) => {
    const members = group.providers.map(
      (id) => html`<tr class=${byClass ? "in-class" : null}>
        <th scope="row">
          ${named(providerName(id), offered[id])}
          ${catalogs[id]
            ? html`<span class="row-sub">${t("station.none.catalog_version", { version: catalogs[id].version, when: fmtDateTime(catalogs[id].downloaded_at) })}</span>`
            : null}
        </th>
        <td>${counted(stations.filter((s) => s.provider === id), offered[id])}</td>
      </tr>`,
    );
    if (!byClass) return members;
    const own = stations.filter((s) => group.providers.includes(s.provider));
    const kinds = shownKinds(own);
    return [
      html`<tr class="class-row" data-class=${group.cls}><th scope="row">${named(sourceClassName(group.cls), kinds)}</th><td>${counted(own, kinds)}</td></tr>`,
      ...members,
    ];
  });
  return html`<div class="no-station">
    <p class="hint-box">${t("station.none.hint")}</p>
    ${root && root.error ? html`<p class="ana-error" role="alert">${t("station.none.root_error", { message: root.error.message })}</p>` : null}
    <h3 class="group-title">${t("station.none.catalogs")}</h3>
    <table class="params compact" data-part="catalogs">
      <tbody>
        ${rows}
        <tr><th scope="row">${t("station.none.with_series")}</th><td>${count((s) => s.datasets.length > 0)}</td></tr>
        <tr><th scope="row">${t("station.none.without_location")}</th><td>${count((s) => s.lon === null)}</td></tr>
      </tbody>
    </table>
    <${StationsFiles} provider=${provider} kind=${kind === "all" ? null : kind} onDoc=${setFiles} />
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
    <h3 class="group-title">${t("station.none.analyses")}</h3>
    <table class="params compact" data-part="analyses">
      <tbody>
        ${providers.map(
          (id) => html`<tr data-provider=${id}>
            <th scope="row">
              ${providerName(id)}
              ${analyses[id]
                ? html`<span class="row-sub">${t("station.none.analyses_version", { version: analyses[id].version, when: fmtDateTime(analyses[id].downloaded_at) })}</span>`
                : null}
            </th>
            <td>${analyses[id] ? (analyses[id].hydrolog ? `Hydrolog ${analyses[id].hydrolog}` : "–") : t("station.none.no_analyses")}</td>
          </tr>`,
        )}
      </tbody>
    </table>
    ${session
      ? html`<p class="note">
          Obserwator ${session.version.obserwator} · ${session.version.hydrolog ? `Hydrolog ${session.version.hydrolog}` : t("station.none.no_hydrolog")}
        </p>`
      : null}
  </div>`;
}
