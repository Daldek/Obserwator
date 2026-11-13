// „Pomiary bieżące” (GUI plan D8, D11): the latest values of an IMGW-PIB station from the
// server's snapshots (api/current/{code}: fetched at most once in ten minutes, never
// stored), drawn with the map's symbols (symbols.js):
// - a hydrological station: its water state as hydro.imgw.pl classes and draws it, and the
//   water level, discharge and water temperature of `current hydro` with their times;
// - a meteorological station: the precipitation of the last 10 minutes, classed as on the
//   map, the air temperature, the mean wind and the humidity of `current meteo`; a
//   synoptic station adds the last report of `current synop` (temperature, wind and its
//   direction, humidity, the precipitation total, pressure).
// IMGW-PIB's API gives its times in UTC, shown as such (current.js `measuredAt`).
// Obserwator serves no current data of ČHMÚ: the section says so in the words of the
// server's answer (`errors.no_current_chmi`) without asking it. The response's lines and
// terms (Nogat DEV §20: S, P of danepubliczne.imgw.pl, and H for the water state of
// hydro.imgw.pl) go to the view's strip (`ResultLines`).

import { api } from "../api.js";
import { clock, measuredAt } from "../current.js";
import { fmt, fmtDate, html, t, useContext, useEffect, useState } from "../lib.js";
import { SymbolIcon, hydroState, meteoClass } from "../symbols.js";
import { Figures, ResultLines, Section } from "./common.js";

const COMPASS = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"];

/** A value with its unit, or a dash. */
function amount(value, digits, unit) {
  return value === null || value === undefined ? "–" : `${fmt(value, digits)} ${unit}`;
}

/** The time of a measurement, or nothing when the API gives none. */
function at(text) {
  return measuredAt(text, { year: true }) || null;
}

function HydroNow({ doc }) {
  const r = doc.record;
  const state = hydroState(doc.state);
  const known = doc.state && state.key !== "unknown" && state.key !== "no-water-state-data";
  return html`
    <p class="now-class">
      <${SymbolIcon} shape="hydro" color=${state.color} hollow=${state.outdated} size=${18} />
      <strong>${state.label}</strong>
      ${known ? html`<span class="muted small">${t("station.now.state_note", { hours: state.outdated ? 26 : 2 })}</span>` : null}
    </p>
    <${Figures}
      items=${[
        { label: t("station.now.water_level"), value: amount(r.water_level_cm, 0, "cm"), note: at(r.water_level_date) },
        { label: t("station.now.discharge"), value: amount(r.flow_m3s, r.flow_m3s !== null && r.flow_m3s < 10 ? 2 : 1, "m³/s"), note: at(r.flow_date) },
        { label: t("station.now.water_temperature"), value: amount(r.water_temp_c, 1, "°C"), note: at(r.water_temp_date) },
      ]}
    />
  `;
}

function Synop({ report }) {
  const direction = report.wind_direction;
  const hour = report.measurement_hour;
  return html`<${Section} title=${t("station.now.synop_title", { name: report.station_name, code: report.station_code })}>
    <${Figures}
      items=${[
        { label: t("station.now.air_temperature"), value: amount(report.temperature_c, 1, "°C") },
        {
          label: t("station.now.wind"),
          value: amount(report.wind_speed_ms, 1, "m/s"),
          note: direction === null || direction === undefined ? null : t("station.now.wind_from", { degrees: fmt(direction), compass: COMPASS[Math.round(direction / 22.5) % 16] }),
        },
        { label: t("station.now.humidity"), value: amount(report.humidity_percent, 0, "%") },
        { label: t("station.now.precipitation_total"), value: amount(report.precipitation_mm, 1, "mm") },
        { label: t("station.now.pressure"), value: amount(report.pressure_hpa, 1, "hPa") },
        ...(report.visibility_m !== null && report.visibility_m !== undefined ? [{ label: t("station.now.visibility"), value: amount(report.visibility_m, 0, "m") }] : []),
        ...(report.cloud_cover !== null && report.cloud_cover !== undefined ? [{ label: t("station.now.cloud_cover"), value: `${report.cloud_cover}/8` }] : []),
      ]}
    />
    <p class="note">
      ${hour === null || hour === undefined
        ? t("station.now.synop_date", { date: fmtDate(report.measurement_date) })
        : t("station.now.synop_term", { date: fmtDate(report.measurement_date), hour: String(hour).padStart(2, "0") })}
    </p>
  </${Section}>`;
}

function MeteoNow({ doc }) {
  const r = doc.record;
  const entry = meteoClass(r.precipitation_10min_mm);
  // A station measuring only precipitation reports nothing else: no empty tiles
  const others = [
    r.air_temp_c !== null ? { label: t("station.now.air_temperature"), value: amount(r.air_temp_c, 1, "°C"), note: at(r.air_temp_date) } : null,
    r.wind_speed_ms !== null ? { label: t("station.now.wind_mean"), value: amount(r.wind_speed_ms, 1, "m/s") } : null,
    r.humidity_percent !== null ? { label: t("station.now.humidity"), value: amount(r.humidity_percent, 0, "%") } : null,
  ].filter(Boolean);
  return html`
    <p class="now-class">
      <${SymbolIcon} shape="meteo" color=${entry.color} size=${18} />
      <strong>${entry.label}</strong>
      ${entry.note ? html`<span class="muted small">${entry.note}</span>` : null}
    </p>
    ${r.precipitation_10min_mm === null && !others.length
      ? html`<p class="note-box">${t("station.now.no_values")}</p>`
      : html`<${Figures} items=${[{ label: t("station.now.precipitation_10min"), value: amount(r.precipitation_10min_mm, 1, "mm") }, ...others]} />
          ${others.length ? null : html`<p class="note">${t("station.now.only_precipitation")}</p>`}`}
    ${doc.synop ? html`<${Synop} report=${doc.synop} />` : null}
  `;
}

/** The server's snapshots behind the values, with their times and any failed refresh. */
function Snapshots({ doc }) {
  const snapshots = Object.entries(doc.snapshots || {});
  if (!snapshots.length) return null;
  const list = snapshots.map(([name, snap]) => `${t(`station.now.source.${name}`)} ${clock(snap.fetched_at)}`).join(", ");
  return html`<p class="note">
    ${t("station.now.snapshots", { list })}
    ${snapshots
      .filter(([, snap]) => snap.error)
      .map(([, snap]) => html`<br /><span class="bad-text">${t("station.now.snapshot_error", { message: snap.error })}</span>`)}
  </p>`;
}

function Teraz({ station }) {
  const imgw = station.provider === "IMGW-PIB";
  const [state, setState] = useState({ doc: null, error: null, loading: imgw });
  const [round, setRound] = useState(0);
  useEffect(() => {
    if (!imgw) return undefined;
    let live = true;
    setState((old) => ({ ...old, loading: true }));
    api.currentStation(station.code).then(
      (doc) => live && setState({ doc, error: null, loading: false }),
      (error) => live && setState((old) => ({ doc: old.doc, error, loading: false })),
    );
    return () => {
      live = false;
    };
  }, [station.code, round]);
  const report = useContext(ResultLines);
  useEffect(() => {
    if (report && state.doc) report(state.doc);
  }, [report, state.doc]);
  if (!imgw) {
    return html`<p class="note-box">${t("errors.no_current_chmi")} ${t("station.now.chmi_note")}</p>`;
  }
  const doc = state.doc;
  const hydro = station.properties.kind === "hydro";
  const absent = hydro ? t("station.now.no_record_hydro") : t("station.now.no_record_meteo");
  return html`<${Section} info=${hydro ? t("station.now.info_hydro") : t("station.now.info_meteo")}>
    ${state.error ? html`<p class="ana-error" role="alert">${state.error.message}</p>` : null}
    ${!doc && state.loading ? html`<p class="muted" role="status">${t("station.now.loading")}</p>` : null}
    ${doc && !doc.record ? html`<p class="note-box">${absent}${station.properties.active ? "" : ` ${t("station.now.inactive")}`}</p>` : null}
    ${doc && doc.record ? (hydro ? html`<${HydroNow} doc=${doc} />` : html`<${MeteoNow} doc=${doc} />`) : null}
    ${doc ? html`<${Snapshots} doc=${doc} />` : null}
    <div class="btn-row">
      <button type="button" class="btn sm" disabled=${state.loading} onClick=${() => setRound(round + 1)}>${t("station.now.refresh")}</button>
      <span class="muted small">${t("station.now.operational")}</span>
    </div>
  </${Section}>`;
}

/** The section „Pomiary bieżące”. */
export const TERAZ = { id: "teraz", title: "station.teraz.title", component: Teraz, part: null };
