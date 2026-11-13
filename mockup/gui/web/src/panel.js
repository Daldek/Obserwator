// The right panel „Stacja” (plan D11): the station's header (name, river, code, provider,
// kind, active or not), then its sections as an accordion, in the author's order of
// 2026-11-13: „Informacje o stacji” and „Pomiary bieżące” at the top, then „Dane
// pomiarowo-obserwacyjne”, then the hydrological (HYDRO_SECTIONS) or meteorological
// (METEO_SECTIONS) analyses by the station's kind, then „Pobierz”. A registry entry is
// `{id, title, component, available?, part?}`: the panel draws the title as the card's header
// and, when open, `component({station, meta})` inside; `available(station) === false` leaves
// the card out. A station without series shows its catalog data and says the store holds
// none. A section that throws is shown as an error in its card, the others go on.
//
// Under each open section with data the panel draws the provider's lines and terms (Nogat
// DEV §20, attribution.js): those of the station's `attribution_parts` named by the entry's
// `part` ("catalog", "series", or by default "results"); `part: null` means the section
// draws its own from its response („Pomiary bieżące”).

import { Component } from "../vendor/preact/preact.mjs";
import { api } from "./api.js";
import { Attribution, catalogSources, compose, useTexts } from "./attribution.js";
import { fmt, html, useEffect, useState } from "./lib.js";
import { HYDRO_SECTIONS } from "./sections/hydro/index.js";
import { METEO_SECTIONS } from "./sections/meteo/index.js";
import { DANE } from "./sections/dane.js";
import { POBIERZ } from "./sections/pobierz.js";
import { STACJA } from "./sections/stacja.js";
import { TERAZ } from "./sections/teraz.js";
import { DATASETS, KINDS, datasetTitle, providerName } from "./words.js";

/** The sections of a station, in the panel's order. */
export function stationSections(station) {
  const own = station.properties.kind === "hydro" ? HYDRO_SECTIONS : station.properties.kind === "meteo" ? METEO_SECTIONS : [];
  const analyses = station.datasets.length ? own.filter((entry) => !entry.available || entry.available(station) !== false) : [];
  return [STACJA, TERAZ, DANE, ...analyses, POBIERZ];
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
    if (this.state.error) return html`<p class="ana-error">Sekcja nie działa: ${String(this.state.error.message || this.state.error)}</p>`;
    return this.props.children;
  }
}

function Chevron() {
  return html`<svg class="chev" viewBox="0 0 20 20" aria-hidden="true"><path d="M5 8l5 5 5-5" /></svg>`;
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
      <span class="chip">${providerName(station.provider)}</span>
      <span class=${`chip kind-${p.kind}`}>${KINDS[p.kind] || p.kind || "–"}</span>
      <span class=${`badge ${p.active ? "ok" : "warn"}`}>${p.active ? "czynna" : "nieczynna"}</span>
      ${station.lon === null ? html`<span class="badge warn">bez współrzędnych</span>` : null}
    </div>
    ${station.datasets.length
      ? null
      : html`<p class="note-box">Magazyn nie ma szeregów tej stacji: panel pokazuje jej dane z katalogu.</p>`}
  </div>`;
}

/**
 * The panel's body for a selected station.
 *
 * @param {{code: string, meta: object|null, open: string[], focus?: string|null,
 *   onToggle: (id: string) => void}} props the station, the server's meta, the open
 *   sections, the section the address named (scrolled into view once) and the toggle
 * @returns {object}
 */
export function StationPanel({ code, meta, open, focus, onToggle }) {
  const [state, setState] = useState({ station: null, error: null });
  useEffect(() => {
    let live = true;
    setState({ station: null, error: null });
    api.station(code).then(
      (station) => live && setState({ station, error: null }),
      (error) => live && setState({ station: null, error }),
    );
    return () => {
      live = false;
    };
  }, [code]);
  useEffect(() => {
    // The address' section comes into view, unless it is the first card
    if (!state.station || !focus || focus === stationSections(state.station)[0].id) return;
    const card = document.querySelector(`.acc-item[data-section="${CSS.escape(focus)}"]`);
    if (card) card.scrollIntoView({ block: "start" });
  }, [state.station]);
  if (state.error) return html`<p class="ana-error">${state.error.message}</p>`;
  if (!state.station) return html`<p class="muted">Wczytuję stację…</p>`;
  const station = state.station;
  return html`<div class="station-panel">
    <${StationHead} station=${station} />
    <div class="acc">
      ${stationSections(station).map((entry) => {
        const isOpen = open.includes(entry.id);
        const Body = entry.component;
        return html`<section class=${`acc-item${isOpen ? " open" : ""}`} key=${entry.id} data-section=${entry.id}>
          <h3 class="acc-head">
            <button type="button" aria-expanded=${isOpen} aria-controls=${`sec-${entry.id}`} onClick=${() => onToggle(entry.id)}>
              <span class="acc-title">${entry.title}</span>
              ${entry.meta ? html`<span class="acc-meta">${entry.meta}</span>` : null}
              <${Chevron} />
            </button>
          </h3>
          ${isOpen
            ? html`<div class="acc-body" id=${`sec-${entry.id}`}>
                <${Guard} key=${`${code}:${entry.id}`}><${Body} station=${station} meta=${meta} /></${Guard}>
                ${entry.part === null ? null : html`<${Attribution} fields=${(station.attribution_parts || {})[entry.part || "results"]} className="sec-attrib" />`}
              </div>`
            : null}
        </section>`;
      })}
    </div>
  </div>`;
}

/**
 * The panel without a station: how to choose one and what the store holds.
 *
 * @param {{meta: object|null, stations: object[]}} props
 * @returns {object}
 */
export function NoStation({ meta, stations }) {
  const texts = useTexts();
  const count = (test) => stations.filter(test).length;
  const series = meta ? Object.entries(meta.series || {}) : [];
  return html`<div class="no-station">
    <p class="hint-box">Wybierz stację na mapie albo z listy po lewej: tu pokażą się informacje o niej, jej pomiary bieżące, dane pomiarowo-obserwacyjne, analizy i pliki do pobrania.</p>
    <h3 class="group-title">Katalog</h3>
    <table class="params compact">
      <tbody>
        <tr><th>IMGW-PIB: hydrologiczne · meteorologiczne</th><td>${fmt(count((s) => s.provider === "IMGW-PIB" && s.kind === "hydro"))} · ${fmt(count((s) => s.provider === "IMGW-PIB" && s.kind === "meteo"))}</td></tr>
        <tr><th>ČHMÚ: hydrologiczne · meteorologiczne</th><td>${fmt(count((s) => s.provider === "CHMI" && s.kind === "hydro"))} · ${fmt(count((s) => s.provider === "CHMI" && s.kind === "meteo"))}</td></tr>
        <tr><th>z szeregami w magazynie</th><td>${fmt(count((s) => s.datasets.length > 0))}</td></tr>
        <tr><th>bez współrzędnych (tylko na liście)</th><td>${fmt(count((s) => s.lon === null))}</td></tr>
      </tbody>
    </table>
    <h3 class="group-title">Szeregi w magazynie</h3>
    ${series.length
      ? html`<table class="params compact">
          <tbody>
            ${series.map(
              ([key, value]) => html`<tr>
                <th>${datasetTitle(key)}<span class="row-sub">wersja ${value.version}</span></th>
                <td>${fmt(value.stations)} stacji</td>
              </tr>`,
            )}
          </tbody>
        </table>`
      : html`<p class="muted">Magazyn nie ma jeszcze szeregów.</p>`}
    ${series.length < Object.keys(DATASETS).length
      ? html`<p class="note">Pozostałe zbiory (${Object.keys(DATASETS)
          .filter((key) => !(meta && meta.series && meta.series[key]))
          .map(datasetTitle)
          .join(", ")}) jeszcze się pobierają; pojawią się po ponownym uruchomieniu serwera makiety.</p>`
      : null}
    ${meta ? html`<p class="note">Obserwator ${meta.obserwator} · Hydrolog ${meta.hydrolog}</p>` : null}
    <${Attribution} fields=${compose(texts, catalogSources(stations))} className="sec-attrib" />
  </div>`;
}
