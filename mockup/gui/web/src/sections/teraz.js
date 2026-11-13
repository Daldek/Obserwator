// „Pomiary bieżące” (plan D8, D11): the latest values of an IMGW-PIB station from the
// server's snapshots (api/current?station=, fetched at most once in ten minutes and never
// stored), drawn with the map's symbols (symbols.js):
// - a hydrological station: its water state as hydro.imgw.pl classes and draws it, and
//   the water level, discharge and water temperature of `current hydro` with their times;
// - a meteorological station: the precipitation of the last 10 minutes, classed as on the
//   map, the air temperature, the mean wind and the humidity of `current meteo`; a
//   synoptic station adds the last report of `current synop` (temperature, wind and its
//   direction, humidity, the precipitation total, pressure).
// IMGW-PIB's API gives its times in UTC (current.js). Obserwator does not serve ČHMÚ's
// current data. Under the values: the lines and terms of the response (Nogat DEV §20): S, P
// for danepubliczne.imgw.pl, and H for the water state of hydro.imgw.pl.

import { api } from "../api.js";
import { Attribution } from "../attribution.js";
import { SOURCES, clock, measuredAt } from "../current.js";
import { fmt, html, useEffect, useState } from "../lib.js";
import { SymbolIcon, hydroState, meteoClass } from "../symbols.js";
import { Figures, Section } from "./common.js";

const INFO_HYDRO =
  "Wartości operacyjne IMGW-PIB (niezweryfikowane) z jego publicznego API (obserwator current hydro): stan wody, przepływ " +
  "i temperatura wody z czasem pomiaru (UTC). Symbol i opis to stan wody względem stanów charakterystycznych z mapy " +
  "hydro.imgw.pl (current hydro-states), w jej kolorach: pełny to stan z pomiarów ostatnich 2 godzin, z pustym środkiem " +
  "z ostatnich 26 godzin. Serwer makiety pyta IMGW-PIB najwyżej raz na 10 minut, pokazuje migawkę z jej czasem i niczego " +
  "nie zapisuje.";
const INFO_METEO =
  "Wartości operacyjne automatycznych stacji meteorologicznych IMGW-PIB (niezweryfikowane) z jego publicznego API " +
  "(obserwator current meteo): opad ostatnich 10 minut, temperatura powietrza z czasem pomiaru (UTC), średnia prędkość " +
  "wiatru i wilgotność względna. Klasa opadu ma kolory mapy hydro.imgw.pl, ale liczona jest z sumy 10-minutowej " +
  "(hydro.imgw.pl liczy z 6 godzin); opad intensywny to co najmniej silny deszcz w skali Chomicza, ≥ √10 ≈ 3,2 mm w 10 " +
  "minut. Stacja synoptyczna ma też ostatnią depeszę SYNOP (current synop). Serwer makiety pyta IMGW-PIB najwyżej raz " +
  "na 10 minut i niczego nie zapisuje.";

const COMPASS = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"];

/** A value with its unit, or a dash. */
function amount(value, digits, unit) {
  return value === null || value === undefined ? "–" : `${fmt(value, digits)} ${unit}`;
}

function HydroNow({ doc }) {
  const r = doc.record;
  const state = hydroState(doc.state);
  return html`
    <p class="now-class">
      <${SymbolIcon} shape="hydro" color=${state.color} hollow=${state.outdated} size=${18} />
      <strong>${state.label}</strong>
      ${doc.state && state.key !== "unknown" && state.key !== "no-water-state-data"
        ? html`<span class="muted small">stan z pomiarów ostatnich ${state.outdated ? "26" : "2"} godzin, mapa hydro.imgw.pl</span>`
        : null}
    </p>
    <${Figures}
      items=${[
        { label: "Stan wody H", value: amount(r.water_level_cm, 0, "cm"), note: measuredAt(r.water_level_date, { year: true }) },
        { label: "Przepływ Q", value: amount(r.flow_m3s, r.flow_m3s !== null && r.flow_m3s < 10 ? 2 : 1, "m³/s"), note: measuredAt(r.flow_date, { year: true }) },
        { label: "Temperatura wody", value: amount(r.water_temp_c, 1, "°C"), note: measuredAt(r.water_temp_date, { year: true }) },
      ]}
    />
  `;
}

function Synop({ report }) {
  const direction = report.wind_direction;
  return html`<${Section} title=${`Depesza SYNOP: ${report.station_name} (${report.station_code})`}>
    <${Figures}
      items=${[
        { label: "Temperatura powietrza", value: amount(report.temperature_c, 1, "°C") },
        {
          label: "Wiatr",
          value: amount(report.wind_speed_ms, 1, "m/s"),
          note: direction === null || direction === undefined ? null : `z kierunku ${direction}° (${COMPASS[Math.round(direction / 22.5) % 16]})`,
        },
        { label: "Wilgotność względna", value: amount(report.humidity_percent, 0, "%") },
        { label: "Suma opadu", value: amount(report.precipitation_mm, 1, "mm") },
        { label: "Ciśnienie", value: amount(report.pressure_hpa, 1, "hPa") },
        ...(report.visibility_m !== null ? [{ label: "Widzialność", value: amount(report.visibility_m, 0, "m") }] : []),
        ...(report.cloud_cover !== null ? [{ label: "Zachmurzenie", value: `${report.cloud_cover}/8` }] : []),
      ]}
    />
    <p class="note">Termin obserwacji: ${report.measurement_date ? `${report.measurement_date.slice(8, 10)}.${report.measurement_date.slice(5, 7)}.${report.measurement_date.slice(0, 4)}` : "–"}${report.measurement_hour !== null ? `, ${String(report.measurement_hour).padStart(2, "0")}:00 UTC` : ""}.</p>
  </${Section}>`;
}

function MeteoNow({ doc }) {
  const r = doc.record;
  const entry = meteoClass(r.precipitation_10min_mm);
  return html`
    <p class="now-class">
      <${SymbolIcon} shape="meteo" color=${entry.color} size=${18} />
      <strong>${entry.label}</strong>
      ${entry.note ? html`<span class="muted small">${entry.note}</span>` : null}
    </p>
    <${Figures}
      items=${[
        { label: "Opad (10 min)", value: amount(r.precipitation_10min_mm, 1, "mm") },
        // A station measuring only precipitation reports nothing else: no empty tiles
        ...(r.air_temp_c !== null ? [{ label: "Temperatura powietrza", value: amount(r.air_temp_c, 1, "°C"), note: measuredAt(r.air_temp_date, { year: true }) }] : []),
        ...(r.wind_speed_ms !== null ? [{ label: "Wiatr (średni)", value: amount(r.wind_speed_ms, 1, "m/s") }] : []),
        ...(r.humidity_percent !== null ? [{ label: "Wilgotność względna", value: amount(r.humidity_percent, 0, "%") }] : []),
      ]}
    />
    ${r.air_temp_c === null && r.wind_speed_ms === null && r.humidity_percent === null
      ? html`<p class="note">API IMGW-PIB podaje teraz dla tej stacji tylko opad.</p>`
      : null}
    ${doc.synop ? html`<${Synop} report=${doc.synop} />` : null}
  `;
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
    return html`<p class="note-box">Dane bieżące ČHMÚ nie są udostępniane: Obserwator nie obsługuje bieżących danych ČHMÚ (now, recent), tylko szeregi dobowe z magazynu.</p>`;
  }
  const doc = state.doc;
  const hydro = station.properties.kind === "hydro";
  const snapshots = doc ? Object.entries(doc.snapshots) : [];
  return html`<${Section} info=${hydro ? INFO_HYDRO : INFO_METEO} state=${{ data: null, error: state.error, loading: state.loading }}>
    ${doc && !doc.record
      ? html`<p class="note-box">IMGW-PIB nie podaje teraz pomiarów tej stacji${station.properties.active ? "" : " (stacja nieczynna)"}: nie ma jej w ${hydro ? "danych bieżących hydrologicznych" : "danych automatycznych stacji meteorologicznych"} API.</p>`
      : null}
    ${doc && doc.record ? (hydro ? html`<${HydroNow} doc=${doc} />` : html`<${MeteoNow} doc=${doc} />`) : null}
    ${doc
      ? html`<p class="note">
          Migawki serwera: ${snapshots.map(([name, snap]) => `${SOURCES[name]} ${clock(snap.fetched_at)}`).join(", ")}; odświeżane najwyżej co 10 minut, niezapisywane. Czasy pomiarów w UTC.
          ${snapshots
            .filter(([, snap]) => snap.error)
            .map(([, snap]) => html`<br /><span class="bad-text">${snap.error} (pokazuję ostatnią udaną migawkę)</span>`)}
        </p>`
      : null}
    <div class="btn-row">
      <button type="button" class="btn sm" disabled=${state.loading} onClick=${() => setRound(round + 1)}>Odśwież</button>
      <span class="muted small">Dane operacyjne IMGW-PIB, bieżące, nie archiwalne</span>
    </div>
    ${doc ? html`<${Attribution} fields=${doc} className="sec-attrib" />` : null}
  </${Section}>`;
}

/** The section „Pomiary bieżące”. */
export const TERAZ = { id: "teraz", title: "Pomiary bieżące", component: Teraz, part: null };
