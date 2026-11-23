// „Pomiary bieżące” (GUI plan D8, D11): the latest values of an IMGW-PIB station from the
// server's snapshots (api/current/{code}: fetched at most once in ten minutes, every answer
// kept in the server's captures, ADR-030 D7), drawn with the map's symbols (symbols.js):
// - a hydrological station: its water state as hydro.imgw.pl classes and draws it, and the
//   water level, discharge and water temperature of `current hydro` with their times;
// - a meteorological station: the precipitation of the last 10 minutes, classed as on the
//   map, the air temperature, the mean wind and the humidity of `current meteo`; a
//   synoptic station adds the last report of `current synop` (temperature, wind and its
//   direction, humidity, the precipitation total, pressure).
// IMGW-PIB's API gives its times in UTC, shown as such (current.js `measuredAt`).
// Under them, a hydrological station whose chart the server serves (`subdaily` of
// api/stations/{code}: its sources public, O6) has the chart of its hours
// (api/station/{code}/subdaily): the hourly series of the data root, one line per tier in
// the tier's style, and the hours after it that the provider gives now (the live tail,
// green), H with IMGW-PIB's warning and alarm levels, Q or T on a switch, over 3, 7 or 30
// days or every stored hour; a reading that stands alone (a daily water temperature) is a
// point. A ČHMÚ station has no current values: a hydrological one shows its chart where it
// is served, else the section says so in the words of the server's answer
// (`errors.no_current_chmu`) without asking it. The lines and terms of every answer (Nogat
// DEV §20: S, P of danepubliczne.imgw.pl, H of hydro.imgw.pl, C and CP of ČHMÚ, those of
// each tier of the chart) go to the view's strip (`ResultLines`).

import { api } from "../api.js";
import { clock, measuredAt } from "../current.js";
import { Chart, fmt, fmtDate, hourNumber, html, isoOfDay, lang, t, unit, useContext, useEffect, useMemo, useState } from "../lib.js";
import { SymbolIcon, hydroState, meteoClass } from "../symbols.js";
import { variableInfo } from "../words.js";
import { Figures, ResultLines, Section, Seg } from "./common.js";

const COMPASS = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"];
/** The ranges of the chart: days back from now, or every stored hour. */
const RANGES = ["3", "7", "30", "all"];
/** The words of each range: `station.now.chart.range.<key>`. */
const RANGE_WORDS = { 3: "d3", 7: "d7", 30: "d30", all: "all" };
/** The variables of the chart, in the order of its switch. */
const VARIABLES = ["H", "Q", "T"];
/** The tiers of the stored hours, highest first (ADR-031); index + 1 marks a row's tier. */
const TIERS = ["verified", "telemetry", "operational"];
/** An hour in day numbers, the step of the chart's `datetime` scale. */
const HOUR = 1 / 24;
/** A day in milliseconds. */
const DAY_MS = 86400000;
/** IMGW-PIB's levels of a hydrological station drawn over H (ADR-021): catalog key and colour. */
const LEVELS = [
  { key: "warning", value: "warning_level_cm", cls: "hy-lv-1" },
  { key: "alarm", value: "alarm_level_cm", cls: "hy-lv-3" },
];

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
        { label: t("station.now.discharge"), value: amount(r.flow_m3s, r.flow_m3s !== null && r.flow_m3s < 10 ? 2 : 1, "m³/s"), note: at(r.flow_date), stale: r.flow_stale === true ? t("station.now.flow_stale") : null },
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

/** The first UTC day ("YYYY-MM-DD") a range asks for; none for every stored hour. */
function fromDay(range, nowMs) {
  return range === "all" ? undefined : isoOfDay(Math.floor(nowMs / DAY_MS) - Number(range));
}

/** Points with a gap (NaN) where an hour is skipped, where the line breaks. */
function withBreaks(points) {
  const out = [];
  for (const point of points) {
    const before = out.length ? out[out.length - 1] : null;
    if (before && point.x - before.x > 1.5 * HOUR) out.push({ x: before.x + HOUR, y: NaN });
    out.push(point);
  }
  return out;
}

/**
 * A variable's stored hours, each with its tier (index + 1 in TIERS, 0 without a value),
 * and the hours of the live tail after them, as points of the `datetime` scale.
 */
function hoursOf(doc, name) {
  const stored = doc.stored;
  const values = stored.values[name] || [];
  const tiers = new Uint8Array(values.length);
  for (const [first, last, tier] of stored.tiers[name] || []) {
    for (let i = first; i <= last; i += 1) if (values[i] !== null) tiers[i] = TIERS.indexOf(tier) + 1;
  }
  const rows = stored.dates.map((date, i) => ({ x: hourNumber(date), y: values[i] ?? NaN, tier: tiers[i] }));
  const tail = doc.live ? doc.live.values[name] || [] : [];
  const live = doc.live ? doc.live.dates.map((date, i) => ({ x: hourNumber(date), y: tail[i] ?? NaN })) : [];
  return { rows, live };
}

/** Whether a variable has a value among the stored or the live hours. */
function hasValue(doc, name) {
  return (doc.stored.values[name] || []).some((value) => value !== null) || (doc.live ? doc.live.values[name] || [] : []).some((value) => value !== null);
}

/**
 * Whether most values stand alone, without one in the hour before or after: a daily water
 * temperature (one reading at 06:00 UTC, the plan's R7) is drawn as points, not joined.
 */
function standsAlone(points) {
  let valued = 0;
  let joined = 0;
  const near = (a, b) => a && b && Number.isFinite(a.y) && Number.isFinite(b.y) && Math.abs(b.x - a.x) < 1.5 * HOUR;
  points.forEach((point, at) => {
    if (!Number.isFinite(point.y)) return;
    valued += 1;
    if (near(points[at - 1], point) || near(point, points[at + 1])) joined += 1;
  });
  return valued > 0 && 2 * joined < valued;
}

/**
 * The chart of a variable over a range: one line per tier of the stored hours in the
 * tier's style (joined to the next tier's first point), the live tail apart in its own
 * colour (joined to the last stored hour), points where the values stand alone, and over H
 * the station's warning and alarm levels.
 */
function nowSpec({ doc, name, range, station, nowMs }) {
  const { rows, live } = hoursOf(doc, name);
  const end = nowMs / DAY_MS;
  const first = rows.length ? rows[0].x : live.length ? live[0].x : end - 1;
  const start = range === "all" ? Math.min(first, end - HOUR) : end - Number(range);
  const inside = (point) => point.x >= start && point.x <= end;
  const shown = rows.filter(inside);
  const kind = standsAlone([...shown, ...live.filter(inside)]) ? "points" : "line";
  const info = variableInfo(name);
  const unitText = unit(doc.units[name]);
  const series = [];
  const present = [...new Set(shown.filter((row) => row.tier).map((row) => row.tier))].sort((a, b) => a - b);
  for (const level of present) {
    const tier = TIERS[level - 1];
    const data = rows.map((row, at) => {
      const before = at > 0 ? rows[at - 1] : null;
      const own = row.tier === level;
      const joins = kind === "line" && !own && row.tier > 0 && before !== null && before.tier === level && row.x - before.x < 1.5 * HOUR;
      return { x: row.x, y: own || joins ? row.y : NaN };
    });
    series.push({ id: `${name}-${tier}`, kind, data: withBreaks(data), label: `${name} (${t(`station.data.tier.${tier}`)})`, unit: unitText, digits: info.digits, cls: `s1 tier-${tier}` });
  }
  if (live.some((point) => Number.isFinite(point.y))) {
    const last = rows.length ? rows[rows.length - 1] : null;
    const joins = kind === "line" && last !== null && Number.isFinite(last.y) && live[0].x - last.x < 1.5 * HOUR;
    const data = withBreaks([...(joins ? [{ x: last.x, y: last.y }] : []), ...live]);
    series.push({ id: `${name}-live`, kind, data, label: `${name} (${t("station.now.chart.live")})`, unit: unitText, digits: info.digits, cls: "s3 tier-live" });
  }
  const props = station.properties;
  const marks =
    name === "H"
      ? LEVELS.filter((level) => Number.isFinite(props[level.value])).map((level) => ({
          kind: "hline",
          y: props[level.value],
          label: `${t(`station.info.level.${level.key}`)} ${fmt(props[level.value])} ${unitText}`,
          cls: level.cls,
        }))
      : [];
  return {
    title: t("station.now.chart.title", { station: props.name || station.code, variable: `${name} — ${info.label}` }),
    fit: { ratio: 0.5, minHeight: 220 },
    size: "small",
    x: { scale: "datetime", min: start, max: end },
    y: { label: `${name} [${unitText}]`, unit: unitText, zero: name === "Q", digits: info.digits },
    series,
    marks,
    legend: true,
    readout: true,
  };
}

/** When the hours after the stored ones came from the provider, and why the last request failed. */
function LiveNote({ live }) {
  return html`<p class="note">
    ${live.fetched_at ? t("station.now.chart.live_at", { time: clock(live.fetched_at) }) : null}
    ${live.error ? html`${live.fetched_at ? html`<br />` : null}<span class="bad-text">${t("station.now.chart.live_failed", { message: live.error })}</span>` : null}
  </p>`;
}

/**
 * The chart of „teraz” (O6): the station's hourly series of the data root and the hours its
 * provider gives after it (api/station/{code}/subdaily), H, Q or T over 3, 7 or 30 days or
 * every stored hour; asked again for another range and by „Odśwież” (`round`).
 */
function NowChart({ station, round }) {
  const [range, setRange] = useState("7");
  const [chosen, setChosen] = useState("H");
  const [state, setState] = useState({ doc: null, range, at: 0, error: null, loading: true });
  const report = useContext(ResultLines);
  useEffect(() => {
    const control = new AbortController();
    setState((old) => ({ ...old, error: null, loading: true }));
    api.subdaily(station.code, { from: fromDay(range, Date.now()), signal: control.signal }).then(
      (doc) => setState({ doc, range, at: Date.now(), error: null, loading: false }),
      (error) => !control.signal.aborted && setState((old) => ({ ...old, error, loading: false })),
    );
    return () => control.abort();
  }, [station.code, range, round]);
  useEffect(() => {
    if (report && state.doc) report(state.doc);
  }, [report, state.doc]);
  const doc = state.doc;
  const offered = doc ? VARIABLES.filter((item) => hasValue(doc, item)) : [];
  const name = offered.includes(chosen) ? chosen : offered[0] || null;
  const spec = useMemo(() => (doc && name ? nowSpec({ doc, name, range: state.range, station, nowMs: state.at }) : null), [doc, name, state.range, state.at, lang()]);
  return html`<${Section} title=${t("station.now.chart.heading")} info=${t("station.now.chart.info")} guide="pomiary-biezace">
    <div class="data-controls now-controls">
      ${offered.length > 1 ? html`<${Seg} label=${t("station.now.chart.variable")} value=${name} onChange=${setChosen} options=${offered.map((item) => [item, item])} />` : null}
      <${Seg} label=${t("station.now.chart.range_label")} value=${range} onChange=${setRange} options=${RANGES.map((item) => [item, t(`station.now.chart.range.${RANGE_WORDS[item]}`)])} />
    </div>
    ${state.error ? html`<p class="ana-error" role="alert">${state.error.message}</p>` : null}
    ${!doc && state.loading ? html`<p class="muted" role="status">${t("station.now.chart.loading")}</p>` : null}
    ${doc && !name ? html`<p class="note-box">${t("station.now.chart.empty")}</p>` : null}
    ${spec
      ? html`<figure class="now-figure">
          <div class="data-chart"><${Chart} spec=${spec} /></div>
          <figcaption class="note">${t("station.now.chart.caption")}</figcaption>
        </figure>`
      : null}
    ${doc && doc.live ? html`<${LiveNote} live=${doc.live} />` : null}
  </${Section}>`;
}

function Teraz({ station }) {
  const imgw = station.provider === "IMGW";
  const chart = station.subdaily === true;
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
  const refresh = html`<button type="button" class="btn sm" disabled=${state.loading} onClick=${() => setRound(round + 1)}>${t("station.now.refresh")}</button>`;
  if (!imgw) {
    return chart
      ? html`<${NowChart} station=${station} round=${round} /><div class="btn-row">${refresh}</div>`
      : html`<p class="note-box">${t("errors.no_current_chmu")} ${t("station.now.chmu_note")}</p>`;
  }
  const doc = state.doc;
  const hydro = station.properties.kind === "hydro";
  const absent = hydro ? t("station.now.no_record_hydro") : t("station.now.no_record_meteo");
  return html`<${Section} info=${hydro ? t("station.now.info_hydro") : t("station.now.info_meteo")} guide="pomiary-biezace">
      ${state.error ? html`<p class="ana-error" role="alert">${state.error.message}</p>` : null}
      ${!doc && state.loading ? html`<p class="muted" role="status">${t("station.now.loading")}</p>` : null}
      ${doc && !doc.record ? html`<p class="note-box">${absent}${station.properties.active ? "" : ` ${t("station.now.inactive")}`}</p>` : null}
      ${doc && doc.record ? (hydro ? html`<${HydroNow} doc=${doc} />` : html`<${MeteoNow} doc=${doc} />`) : null}
      ${doc ? html`<${Snapshots} doc=${doc} />` : null}
      <div class="btn-row">
        ${refresh}
        <span class="muted small">${t("station.now.operational")}</span>
      </div>
    </${Section}>
    ${chart ? html`<${NowChart} station=${station} round=${round} />` : null}`;
}

/** The section „Pomiary bieżące”. */
export const TERAZ = { id: "teraz", title: "station.teraz.title", component: Teraz, part: null };
