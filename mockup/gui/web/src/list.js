// The left panel „Stacje” (plan D10): search by name, river or code ignoring case and
// diacritics (as `obserwator stations find` does: a fragment of the name or the river, a
// prefix of the code), filters by provider, kind, „tylko z danymi” and „tylko czynne”,
// the counts „na mapie N · bez współrzędnych M” and the list; a click selects the station
// and the map flies to it. The provider, kind and active filters choose the map's stations
// too; „tylko z danymi” is the list's: the map keeps catalog-only stations, hollow.

import { fmt, html, useMemo, useState } from "./lib.js";
import { StationSymbol } from "./map.js";
import { Seg } from "./ui/seg.js";
import { providerName } from "./words.js";

/** The filters of a first visit. */
export const DEFAULT_FILTERS = Object.freeze({ query: "", provider: "all", kind: "all", withData: true, active: false });

const PAGE = 150;
const collator = new Intl.Collator("pl", { sensitivity: "base", numeric: true });

/**
 * Text folded for search: lower case without diacritics; Polish ł has no decomposition.
 *
 * @param {string|null|undefined} text
 * @returns {string} e.g. "lodz" for "ŁÓDŹ"
 */
export function fold(text) {
  return String(text ?? "")
    .toLowerCase()
    .replace(/ł/g, "l")
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "");
}

/**
 * The stations of `api/stations` with their folded names, in the list's order: those with
 * series first, then by name.
 *
 * @param {object[]} stations
 * @returns {object[]}
 */
export function prepareStations(stations) {
  return stations
    .map((station) => ({ ...station, foldedName: fold(station.name), foldedRiver: fold(station.river), foldedCode: station.code.toLowerCase() }))
    .sort((a, b) => b.datasets.length - a.datasets.length || collator.compare(a.name || a.code, b.name || b.code));
}

/** Whether the map shows a station under the filters (provider, kind, active). */
export function onMap(station, filters) {
  if (filters.provider !== "all" && station.provider !== filters.provider) return false;
  if (filters.kind !== "all" && station.kind !== filters.kind) return false;
  if (filters.active && !station.active) return false;
  return true;
}

function matches(station, filters, needle) {
  if (!onMap(station, filters)) return false;
  if (filters.withData && !station.datasets.length) return false;
  if (!needle) return true;
  return station.foldedName.includes(needle) || station.foldedRiver.includes(needle) || station.foldedCode.startsWith(needle);
}

/**
 * The panel's body.
 *
 * @param {{stations: object[], filters: object, onFilters: (next: object) => void,
 *   selected: string|null, onSelect: (code: string) => void}} props
 * @returns {object}
 */
export function StationList({ stations, filters, onFilters, selected, onSelect }) {
  const [shown, setShown] = useState(PAGE);
  const needle = fold(filters.query.trim());
  const found = useMemo(() => stations.filter((station) => matches(station, filters, needle)), [stations, filters, needle]);
  const located = found.filter((station) => station.lon !== null).length;
  const set = (key) => (value) => {
    setShown(PAGE);
    onFilters({ ...filters, [key]: value });
  };
  return html`<div class="station-list">
    <label class="search">
      <svg viewBox="0 0 20 20" aria-hidden="true"><circle cx="8.5" cy="8.5" r="5.5" /><path d="M13 13l4 4" /></svg>
      <input
        type="search"
        placeholder="Nazwa, rzeka albo kod"
        aria-label="Szukaj stacji po nazwie, rzece albo kodzie"
        value=${filters.query}
        onInput=${(event) => set("query")(event.target.value)}
      />
    </label>
    <div class="filters">
      <${Seg}
        full
        tiny
        label="Dostawca"
        value=${filters.provider}
        onChange=${set("provider")}
        items=${[
          { value: "all", label: "Wszyscy" },
          { value: "IMGW-PIB", label: "IMGW-PIB" },
          { value: "CHMI", label: "ČHMÚ" },
        ]}
      />
      <${Seg}
        full
        tiny
        label="Rodzaj stacji"
        value=${filters.kind}
        onChange=${set("kind")}
        items=${[
          { value: "all", label: "Wszystkie" },
          { value: "hydro", label: "Hydrologiczne" },
          { value: "meteo", label: "Meteorologiczne" },
        ]}
      />
      <div class="check-row">
        <label class="check"><input type="checkbox" checked=${filters.withData} onChange=${(event) => set("withData")(event.target.checked)} />tylko z danymi</label>
        <label class="check"><input type="checkbox" checked=${filters.active} onChange=${(event) => set("active")(event.target.checked)} />tylko czynne</label>
      </div>
    </div>
    <p class="counts" aria-live="polite">
      <strong>${fmt(found.length)}</strong> ${found.length === 1 ? "stacja" : "stacji"} · na mapie ${fmt(located)} · bez współrzędnych ${fmt(found.length - located)}
    </p>
    ${found.length
      ? html`<ul class="stations" role="list">
          ${found.slice(0, shown).map(
            (station) => html`<li key=${station.code}>
              <button
                type="button"
                class=${station.code === selected ? "st-item sel" : "st-item"}
                aria-current=${station.code === selected ? "true" : undefined}
                onClick=${() => onSelect(station.code, { fly: true })}
              >
                <${StationSymbol} kind=${station.kind} provider=${station.provider} data=${station.datasets.length > 0} />
                <span class="st-name">${station.name || station.code}</span>
                <code class="st-code">${station.code}</code>
                <span class="st-sub">
                  ${[station.river || (station.kind === "meteo" ? "meteorologiczna" : null), providerName(station.provider), station.first ? `${station.first}–${station.last}` : "tylko katalog"]
                    .filter(Boolean)
                    .join(" · ")}
                  ${station.lon === null ? html` · <span class="no-loc">bez współrzędnych</span>` : null}
                </span>
              </button>
            </li>`,
          )}
        </ul>`
      : html`<p class="empty-note">Żadna stacja nie pasuje.${filters.withData ? " Wyłącz „tylko z danymi”, aby szukać też stacji tylko z katalogu." : ""}</p>`}
    ${found.length > shown
      ? html`<button type="button" class="btn sm more" onClick=${() => setShown(shown + PAGE)}>Pokaż kolejne (${fmt(Math.min(PAGE, found.length - shown))} z ${fmt(found.length - shown)})</button>`
      : null}
  </div>`;
}
