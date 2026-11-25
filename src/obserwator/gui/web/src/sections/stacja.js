// „Informacje o stacji” (GUI plan D11): the catalog's properties of the station (its kind
// and, of a groundwater object, whether a bore or a spring, of a PIG-PIB point PSH's number
// and its type as published, its location with the source and the uncertainty, elevation,
// gauge zero with its datum, river kilometre, catchment area, voivodeship and county,
// hydrographic code, year established), IMGW-PIB's warning and alarm levels and absolute
// extremes of a hydrological station (hydro.imgw.pl, ADR-021), ČHMÚ's thresholds of a
// hydrological station, a PIG-PIB point's hydrogeology as published (ADR-035) and the
// coverage of each dataset and variable in the data root. The panel draws the catalog's
// lines under the card (part "catalog").

import { has } from "../i18n.js";
import { fmt, fmtDate, fmtDateTime, html, t, unit } from "../lib.js";
import { datasetTitle, groundwaterKindName, kindName, periodName, providerFullName, providerName, variableInfo } from "../words.js";
import { Section, Table } from "./common.js";

/** ČHMÚ's thresholds of a hydrological station, in their order. */
const THRESHOLDS = ["spa1", "spa2", "spa3", "drought", "q50"];

/** IMGW-PIB's levels and extremes of a hydrological station: catalog keys, in their order. */
const LEVELS = [
  { key: "warning", value: "warning_level_cm", dates: null },
  { key: "alarm", value: "alarm_level_cm", dates: null },
  { key: "minimum", value: "absolute_min_level_cm", dates: "absolute_min_level_dates" },
  { key: "maximum", value: "absolute_max_level_cm", dates: "absolute_max_level_dates" },
];

/**
 * The rows of a PIG-PIB point's hydrogeology (ADR-035 W6), keys of the catalog's
 * `hydrogeology` in the order shown: a text as published, a depth below the ground [m] or
 * a number; the years observed, the administrative units and whether automatic apart.
 */
const HYDROGEOLOGY = [
  { key: "confinement" },
  { key: "stratigraphy" },
  { key: "lithology" },
  { key: "medium" },
  { key: "bore_depth_m", depth: true },
  { key: "final_depth_m", depth: true },
  { key: "water_struck_m", depth: true },
  { key: "water_rest_m", depth: true },
  { key: "screen_top_m", depth: true },
  { key: "screen_bottom_m", depth: true },
];
/** The numbers of a PIG-PIB point in PIG-PIB's databases and monitoring programmes. */
const HYDROGEOLOGY_NUMBERS = ["jcwpd", "cbdh_number", "eu_code", "chemical_number", "research_number", "research_monitoring", "border_number", "pressure_number"];

function Row({ label, value, sub }) {
  return html`<tr><th scope="row">${label}</th><td>${value ?? "–"}${sub ? html`<span class="row-sub">${sub}</span>` : null}</td></tr>`;
}

function given(value) {
  return value !== null && value !== undefined && value !== "";
}

/** Where the catalog took a station's location (or ČHMÚ's thresholds) from. */
function sourceName(source) {
  if (!source) return t("station.info.source_unknown");
  return has(`station.info.source.${source}`) ? t(`station.info.source.${source}`) : source;
}

/** Why a station has no location. */
function missingReason(reason) {
  if (!reason) return t("station.info.no_location");
  return has(`station.info.missing.${reason}`) ? t(`station.info.missing.${reason}`) : reason;
}

/** The kind of an IMGW-PIB meteorological station: climatological or a precipitation post. */
function meteoKind(kind) {
  return has(`station.info.meteo_kind.${kind}`) ? t(`station.info.meteo_kind.${kind}`) : kind;
}

/** A threshold's name: ČHMÚ's flood activity degrees, drought, q50. */
function thresholdName(key) {
  return has(`station.info.threshold.${key}`) ? t(`station.info.threshold.${key}`) : key;
}

/** "H_max@summer" as "H_max [cm]" over "summer (V–X)", "H" as "H [cm]" over "water level". */
function variableCell(name, cov) {
  const [base, period] = name.split("@");
  return html`${base} [${unit(cov.unit)}]<span class="cell-sub">${period ? periodName(period) : variableInfo(base).label}</span>`;
}

function Catalog({ station }) {
  const p = station.properties;
  const hydro = p.hydrogeology || {};
  const located = station.lon !== null && station.lat !== null;
  const where = located
    ? p.location_uncertainty_m
      ? t("station.info.uncertainty", { source: sourceName(p.location_source), metres: fmt(p.location_uncertainty_m) })
      : sourceName(p.location_source)
    : null;
  return html`<${Section} title=${t("station.info.catalog")}>
    <table class="params">
      <tbody>
        <${Row} label=${t("station.info.code")} value=${html`<code>${station.code}</code>`} />
        <${Row} label=${t("station.info.name")} value=${p.name || null} />
        ${p.kind === "hydro" ? html`<${Row} label=${t("station.info.river")} value=${p.river || null} />` : null}
        <${Row} label=${t("station.info.provider")} value=${providerName(station.provider)} sub=${providerFullName(station.provider)} />
        <${Row} label=${t("station.info.kind")} value=${kindName(p.kind)} />
        ${p.meteo_kind ? html`<${Row} label=${t("station.info.meteo_station")} value=${meteoKind(p.meteo_kind)} />` : null}
        ${p.groundwater_kind ? html`<${Row} label=${t("station.info.groundwater_kind")} value=${groundwaterKindName(p.groundwater_kind)} />` : null}
        ${hydro.psh_number ? html`<${Row} label=${t("station.info.psh_number")} value=${html`<code>${hydro.psh_number}</code>`} />` : null}
        ${hydro.point_type ? html`<${Row} label=${t("station.info.point_type")} value=${hydro.point_type} />` : null}
        <${Row} label=${t("station.info.active")} value=${p.active ? t("station.info.yes") : t("station.info.no")} />
        <${Row}
          label=${t("station.info.location")}
          value=${located ? `${fmt(station.lat, 5)}° N, ${fmt(station.lon, 5)}° E` : t("station.info.no_location")}
          sub=${located ? where : missingReason(p.location_missing_reason)}
        />
        ${given(p.elevation_m)
          ? html`<${Row}
              label=${t("station.info.elevation")}
              value=${t("station.info.metres_asl", { value: p.kind === "groundwater" ? ownDecimals(p.elevation_m, 2) : fmt(p.elevation_m, 1) })}
            />`
          : null}
        ${given(p.gauge_zero_m)
          ? html`<${Row}
              label=${t("station.info.gauge_zero")}
              value=${p.gauge_zero_datum
                ? t("station.info.metres_asl_datum", { value: fmt(p.gauge_zero_m, 3), datum: p.gauge_zero_datum })
                : t("station.info.metres_asl", { value: fmt(p.gauge_zero_m, 3) })}
            />`
          : null}
        ${given(p.river_km) ? html`<${Row} label=${t("station.info.river_km")} value=${fmt(p.river_km, 2)} />` : null}
        ${p.kind === "hydro" && given(p.catchment_area_km2)
          ? html`<${Row} label=${t("station.info.catchment_area")} value=${`${fmt(p.catchment_area_km2, 2)} km²`} />`
          : null}
        ${p.kind === "hydro" && p.province ? html`<${Row} label=${t("station.info.province")} value=${p.province} />` : null}
        ${p.kind === "hydro" && p.district ? html`<${Row} label=${t("station.info.district")} value=${p.district} />` : null}
        ${p.hydrographic_code ? html`<${Row} label=${t("station.info.hydrographic_code")} value=${html`<code>${p.hydrographic_code}</code>`} />` : null}
        ${given(p.river_order) ? html`<${Row} label=${t("station.info.river_order")} value=${p.river_order} sub=${t("station.info.river_order_note")} />` : null}
        ${p.established_year ? html`<${Row} label=${t("station.info.established")} value=${p.established_year} />` : null}
      </tbody>
    </table>
  </${Section}>`;
}

/** A number to its own decimals, at most `most`. */
function ownDecimals(value, most) {
  const decimals = (String(value).split(".")[1] || "").length;
  return fmt(value, Math.min(decimals, most));
}

/** A threshold as ČHMÚ gives it: its own decimals, at most three. */
function asGiven(value) {
  return given(value) ? ownDecimals(value, 3) : "–";
}

/** IMGW-PIB's warning and alarm levels and absolute extremes; nothing without a value. */
function Levels({ properties }) {
  const rows = LEVELS.map((level) => ({
    label: t(`station.info.level.${level.key}`),
    H: properties[level.value],
    dates: level.dates ? properties[level.dates] : null,
  })).filter((row) => given(row.H) || given(row.dates));
  if (!rows.length) return null;
  return html`<${Section} title=${t("station.info.levels")} info=${t("station.info.levels_info")} guide="hydro-imgw">
    <${Table}
      columns=${[
        { key: "label", label: t("station.info.level") },
        { key: "H", label: "H [cm]", format: asGiven },
        { key: "dates", label: t("station.info.level_date"), format: (dates) => (given(dates) ? dates : "–") },
      ]}
      rows=${rows}
    />
  </${Section}>`;
}

function Thresholds({ thresholds }) {
  const levels = thresholds.H || null;
  const flows = thresholds.Q || null;
  const rows = THRESHOLDS.map((key) => ({
    label: key === "q50" ? "q50" : thresholdName(key),
    H: levels ? levels[key] : null,
    Q: flows ? flows[key] : null,
  })).filter((row) => given(row.H) || given(row.Q));
  if (!rows.length) return null;
  return html`<${Section} title=${t("station.info.thresholds")} info=${t("station.info.thresholds_info", { source: sourceName(thresholds.source) })} guide="chmu">
    <${Table}
      columns=${[
        { key: "label", label: t("station.info.threshold") },
        { key: "H", label: `H [${unit((levels && levels.unit) || "cm")}]`, format: asGiven },
        { key: "Q", label: `Q [${unit((flows && flows.unit) || "m3/s")}]`, format: asGiven },
      ]}
      rows=${rows}
    />
  </${Section}>`;
}

/** The years a point was observed: from – to, or since its first. */
function observedYears(first, last) {
  if (given(first) && given(last)) return `${first}–${last}`;
  return given(first) ? t("station.info.since", { year: first }) : `–${last}`;
}

/**
 * A PIG-PIB point's hydrogeology as PIG-PIB publishes it (ADR-035 W6): the character of
 * the point and its aquifer, its depths below the ground, the years observed, its numbers,
 * the administrative units, the chemical analyses and whether it measures automatically
 * (as the night's capture of the automatic points lists it; no row without one). Only the
 * rows the point has.
 */
function Hydrogeology({ hydro }) {
  const rows = [];
  const row = (label, value) => rows.push(html`<${Row} label=${label} value=${value} />`);
  for (const { key, depth } of HYDROGEOLOGY) {
    if (given(hydro[key])) row(t(`station.info.hydro.${key}`), depth ? t("station.info.metres_below", { value: ownDecimals(hydro[key], 2) }) : hydro[key]);
  }
  if (given(hydro.observed_from) || given(hydro.observed_to)) row(t("station.info.hydro.observed"), observedYears(hydro.observed_from, hydro.observed_to));
  for (const key of HYDROGEOLOGY_NUMBERS) if (given(hydro[key])) row(t(`station.info.hydro.${key}`), String(hydro[key]));
  if (given(hydro.voivodeship)) row(t("station.info.province"), hydro.voivodeship);
  if (given(hydro.county)) row(t("station.info.district"), hydro.county);
  if (given(hydro.commune)) row(t("station.info.commune"), hydro.commune);
  if (given(hydro.chemical_analyses)) row(t("station.info.hydro.chemical_analyses"), hydro.chemical_analyses);
  if (typeof hydro.automatic === "boolean") row(t("station.info.hydro.automatic"), hydro.automatic ? t("station.info.yes") : t("station.info.no"));
  if (!rows.length) return null;
  return html`<${Section} title=${t("station.info.hydrogeology")} info=${t("station.info.hydrogeology_info")} guide="pig">
    <table class="params" data-part="hydrogeology">
      <tbody>
        ${rows}
      </tbody>
    </table>
  </${Section}>`;
}

function Coverage({ station }) {
  if (!station.datasets.length) {
    return html`<${Section} title=${t("station.info.coverage")}><p class="muted">${t("station.info.no_series")}</p></${Section}>`;
  }
  return html`<${Section} title=${t("station.info.coverage")} info=${t("station.info.coverage_info")} guide="karty">
    ${station.datasets.map((entry) => {
      const covered = Object.entries(entry.variables);
      const summed = covered.some(([, cov]) => cov.accumulated > 0);
      return html`<div class="coverage" key=${entry.dataset}>
        <h4>
          ${datasetTitle(entry.dataset)}
          <span class="muted"> · ${t("station.version", { version: entry.version })} · ${t("station.info.downloaded", { when: fmtDateTime(entry.downloaded_at) })}</span>
        </h4>
        <${Table}
          columns=${[
            { key: "name", label: t("station.variable"), format: (name, row) => variableCell(name, row) },
            { key: "first", label: t("station.info.span"), format: (first, row) => html`${fmtDate(first)} –<br />${fmtDate(row.last)}` },
            { key: "with_value", label: t("station.info.with_value"), digits: 0 },
            ...(summed ? [{ key: "accumulated", label: t("station.info.accumulated"), digits: 0 }] : []),
            { key: "gaps", label: t("station.info.gaps"), digits: 0 },
          ]}
          rows=${covered.map(([name, cov]) => ({ ...cov, name }))}
        />
      </div>`;
    })}
  </${Section}>`;
}

function Stacja({ station }) {
  const { thresholds, hydrogeology } = station.properties;
  return html`
    <${Catalog} station=${station} />
    ${station.properties.kind === "hydro" ? html`<${Levels} properties=${station.properties} />` : null}
    ${thresholds && typeof thresholds === "object" ? html`<${Thresholds} thresholds=${thresholds} />` : null}
    ${hydrogeology && typeof hydrogeology === "object" ? html`<${Hydrogeology} hydro=${hydrogeology} />` : null}
    <${Coverage} station=${station} />
  `;
}

/** The section „Informacje o stacji”. */
export const STACJA = { id: "stacja", title: "station.stacja.title", component: Stacja, part: "catalog" };
