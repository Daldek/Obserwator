// „Informacje o stacji” (plan D11): the catalog's properties of the station (location and
// its source and uncertainty, elevation, gauge zero, river km, hydrographic code, year
// established; ČHMÚ's SPA levels of a hydro station) and the coverage of each dataset and
// variable in the store.

import { fmt, fmtDate, html, unit } from "../lib.js";
import { KINDS, PERIODS, PROVIDERS, datasetTitle, variableInfo } from "../words.js";
import { Section, Table } from "./common.js";

const LOCATION_SOURCES = {
  api_hydro: "bieżące API IMGW-PIB, stacje hydrologiczne",
  api_meteo: "bieżące API IMGW-PIB, stacje meteorologiczne",
  static: "plik położeń stacji hydrologicznych w pakiecie Obserwatora",
  chmi_hydro_now: "bieżące metadane ČHMÚ, hydrologia",
  chmi_hydro_meta3: "metadane ČHMÚ (meta3), hydrologia",
  chmi_hydro_stations: "wykaz stacji ČHMÚ, hydrologia",
  chmi_meteo_now: "bieżące metadane ČHMÚ, meteorologia",
  chmi_meteo_stations: "wykaz stacji ČHMÚ, meteorologia",
};
const MISSING_REASONS = {
  outside_country: "stacja poza krajem dostawcy",
  none: "źródła nie podają położenia (stacja zamknięta albo spoza bieżącego API)",
  zero: "źródło podaje współrzędne zerowe",
};
const THRESHOLDS = [
  ["spa1", "1. SPA (bdělost, czujność)"],
  ["spa2", "2. SPA (pohotovost, gotowość)"],
  ["spa3", "3. SPA (ohrožení, zagrożenie)"],
  ["drought", "susza (sucho)"],
  ["q50", "q50"],
];

function Row({ label, value, sub }) {
  return html`<tr><th>${label}</th><td>${value ?? "–"}${sub ? html`<span class="row-sub">${sub}</span>` : null}</td></tr>`;
}

/** "H_max@summer" as "H_max · lato (V–X)". */
function variableName(name, kind) {
  const [base, period] = name.split("@");
  if (period) return `${base} · ${PERIODS[period] || period}`;
  return `${base} — ${variableInfo(base, kind).label}`;
}

function Stacja({ station }) {
  const p = station.properties;
  const located = station.lon !== null && station.lat !== null;
  const provider = PROVIDERS[station.provider];
  const thresholds = p.thresholds && typeof p.thresholds === "object" ? p.thresholds : null;
  return html`
    <${Section} title="Dane katalogowe">
      <table class="params">
        <tbody>
          <${Row} label="Kod stacji" value=${html`<code>${station.code}</code>`} />
          <${Row} label="Nazwa" value=${p.name} />
          ${p.kind === "hydro" ? html`<${Row} label="Rzeka" value=${p.river} />` : null}
          <${Row} label="Dostawca" value=${provider ? provider.short : station.provider} sub=${provider ? provider.name : null} />
          <${Row} label="Rodzaj" value=${KINDS[p.kind] || p.kind} />
          <${Row} label="Czynna" value=${p.active ? "tak" : "nie"} />
          <${Row}
            label="Położenie (WGS84)"
            value=${located ? `${fmt(station.lat, 5)}° N, ${fmt(station.lon, 5)}° E` : "brak"}
            sub=${located
              ? `${LOCATION_SOURCES[p.location_source] || p.location_source || "źródło nieznane"}${p.location_uncertainty_m ? `, niepewność ±${fmt(p.location_uncertainty_m)} m` : ""}`
              : MISSING_REASONS[p.location_missing_reason] || p.location_missing_reason}
          />
          ${p.elevation_m !== null && p.elevation_m !== undefined ? html`<${Row} label="Wysokość" value=${`${fmt(p.elevation_m, 1)} m n.p.m.`} />` : null}
          ${p.gauge_zero_m !== null && p.gauge_zero_m !== undefined ? html`<${Row} label="Zero wodowskazu" value=${`${fmt(p.gauge_zero_m, 3)} m n.p.m.`} />` : null}
          ${p.river_km !== null && p.river_km !== undefined ? html`<${Row} label="Kilometr rzeki" value=${fmt(p.river_km, 2)} />` : null}
          ${p.hydrographic_code ? html`<${Row} label="Kod hydrograficzny" value=${html`<code>${p.hydrographic_code}</code>`} />` : null}
          ${p.river_order !== null && p.river_order !== undefined ? html`<${Row} label="Liczba z wykazu IMGW-PIB" value=${p.river_order} sub="czwarta kolumna wykazu stacji, bez przypisanego znaczenia (river_order)" />` : null}
          ${p.established_year ? html`<${Row} label="Rok założenia" value=${p.established_year} />` : null}
        </tbody>
      </table>
    </${Section}>
    ${thresholds
      ? html`<${Section} title="Progi ČHMÚ" info="Stany i przepływy progowe ČHMÚ: stopnie powodziowe SPA 1–3, próg suszy i q50, z katalogu Obserwatora (źródło: bieżące dane hydrologiczne ČHMÚ).">
          <${Table}
            columns=${[
              { key: "label", label: "Próg" },
              { key: "H", label: `H [${unit((thresholds.H && thresholds.H.unit) || "cm")}]`, digits: 0 },
              { key: "Q", label: `Q [${unit((thresholds.Q && thresholds.Q.unit) || "m3/s")}]`, digits: 3 },
            ]}
            rows=${THRESHOLDS.map(([key, label]) => ({
              label,
              H: thresholds.H ? thresholds.H[key] : null,
              Q: thresholds.Q ? thresholds.Q[key] : null,
            }))}
          />
        </${Section}>`
      : null}
    <${Section} title="Szeregi w magazynie" info="Pokrycie każdej zmiennej w bieżącej wersji szeregu: pierwszy i ostatni okres z wartością, liczba okresów z wartością (dni albo półrocza) i liczba luk, według indeksu series.json Obserwatora.">
      ${station.datasets.length
        ? station.datasets.map(
            (entry) => html`<div class="coverage">
              <h4>${datasetTitle(entry.dataset)} <span class="muted">· wersja ${entry.version}</span></h4>
              <${Table}
                columns=${[
                  { key: "name", label: "Zmienna" },
                  { key: "first", label: "Od", format: fmtDate },
                  { key: "last", label: "Do", format: fmtDate },
                  { key: "with_value", label: "Z wartością", digits: 0 },
                  { key: "gaps", label: "Luki", digits: 0 },
                ]}
                rows=${Object.entries(entry.variables).map(([name, cov]) => ({ name: `${variableName(name, p.kind)} [${unit(cov.unit)}]`, ...cov }))}
              />
            </div>`,
          )
        : html`<p class="muted">Magazyn nie ma szeregów tej stacji.</p>`}
    </${Section}>
  `;
}

/** The section „Informacje o stacji”. */
export const STACJA = { id: "stacja", title: "Informacje o stacji", component: Stacja };
