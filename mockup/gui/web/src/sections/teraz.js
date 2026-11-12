// „Teraz” (plan D8, D11): the current values of an IMGW-PIB station from the server's
// snapshot (api/current: IMGW-PIB's current hydro or meteo data and the hydro map's water
// state, fetched at most once in ten minutes and never stored); ČHMÚ's current data are
// not served by Obserwator.

import { api } from "../api.js";
import { fmt, html, useEffect, useState } from "../lib.js";
import { waterState } from "../map.js";
import { Figures, Section } from "./common.js";

/** "2026-11-12 22:20:00" (IMGW-PIB's local time) as "12.11.2026 22:20". */
function when(text) {
  if (!text) return null;
  const [day, time = ""] = String(text).split(/[ T]/);
  return `${day.slice(8, 10)}.${day.slice(5, 7)}.${day.slice(0, 4)}${time ? ` ${time.slice(0, 5)}` : ""}`;
}

/** A UTC time of the server as the browser's local "22:31". */
function clock(iso) {
  return iso ? new Date(iso).toLocaleTimeString("pl-PL", { hour: "2-digit", minute: "2-digit" }) : "–";
}

const INFO =
  "Wartości operacyjne IMGW-PIB (niezweryfikowane) z jego publicznego API: stan wody, przepływ i " +
  "temperatura wody stacji hydrologicznych albo pomiary automatycznych stacji meteorologicznych, " +
  "oraz stan wody względem stanów charakterystycznych z mapy hydro.imgw.pl. Serwer makiety pyta " +
  "IMGW-PIB najwyżej raz na 10 minut, pokazuje migawkę z jej czasem i niczego nie zapisuje.";

function figuresOf(doc) {
  const r = doc.record;
  if (doc.kind === "hydro") {
    const state = waterState(doc.state);
    return [
      { label: "Stan wody H", value: r.water_level_cm === null ? "–" : `${fmt(r.water_level_cm)} cm`, note: when(r.water_level_date) },
      { label: "Przepływ Q", value: r.flow_m3s === null ? "–" : `${fmt(r.flow_m3s, r.flow_m3s < 10 ? 2 : 1)} m³/s`, note: when(r.flow_date) },
      { label: "Temperatura wody", value: r.water_temp_c === null ? "–" : `${fmt(r.water_temp_c, 1)} °C`, note: when(r.water_temp_date) },
      { label: "Stan wody (mapa IMGW-PIB)", value: doc.state ? state.label : "–", note: doc.state ? doc.state : null },
    ];
  }
  return [
    { label: "Temperatura powietrza", value: r.air_temp_c === null ? "–" : `${fmt(r.air_temp_c, 1)} °C`, note: when(r.air_temp_date) },
    { label: "Wiatr (średni)", value: r.wind_speed_ms === null ? "–" : `${fmt(r.wind_speed_ms, 1)} m/s` },
    { label: "Wilgotność względna", value: r.humidity_percent === null ? "–" : `${fmt(r.humidity_percent, 0)} %` },
    { label: "Opad (10 min)", value: r.precipitation_10min_mm === null ? "–" : `${fmt(r.precipitation_10min_mm, 1)} mm` },
  ];
}

function Teraz({ station }) {
  const imgw = station.provider === "IMGW-PIB";
  const [state, setState] = useState({ doc: null, error: null, loading: imgw });
  const [round, setRound] = useState(0);
  useEffect(() => {
    if (!imgw) return undefined;
    let live = true;
    setState((old) => ({ ...old, loading: true }));
    api.get("api/current", { station: station.code }, { memo: false }).then(
      (doc) => live && setState({ doc, error: null, loading: false }),
      (error) => live && setState({ doc: null, error, loading: false }),
    );
    return () => {
      live = false;
    };
  }, [station.code, round]);
  if (!imgw) {
    return html`<${Section} title="Wartości bieżące">
      <p class="note-box">Dane bieżące ČHMÚ nie są udostępniane: Obserwator nie obsługuje bieżących danych ČHMÚ (now, recent), tylko szeregi dobowe z magazynu.</p>
    </${Section}>`;
  }
  const doc = state.doc;
  return html`<${Section} title="Wartości bieżące IMGW-PIB" info=${INFO} state=${{ data: null, error: state.error, loading: state.loading }}>
    ${doc && !doc.record
      ? html`<p class="note-box">IMGW-PIB nie podaje teraz wartości bieżących tej stacji${station.properties.active ? "" : " (stacja nieczynna)"}.</p>`
      : null}
    ${doc && doc.record ? html`<${Figures} items=${figuresOf(doc)} />` : null}
    ${doc
      ? html`<p class="note">
          Migawka serwera z ${clock(doc.fetched_at)}${doc.state_fetched_at ? `, stan wody z ${clock(doc.state_fetched_at)}` : ""}; odświeżana najwyżej co 10 minut, niezapisywana.
          ${doc.error ? html`<br /><span class="bad-text">${doc.error} (pokazuję ostatnią udaną migawkę)</span>` : null}
        </p>`
      : null}
    <div class="btn-row">
      <button type="button" class="btn sm" disabled=${state.loading} onClick=${() => setRound(round + 1)}>Odśwież</button>
      <span class="muted small">Źródło: IMGW-PIB, dane operacyjne</span>
    </div>
  </${Section}>`;
}

/** The section „Teraz”. */
export const TERAZ = { id: "teraz", title: "Teraz", component: Teraz };
