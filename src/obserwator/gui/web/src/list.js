// The left panel „Stacje” (plan D10): search by name, river or code ignoring case and
// diacritics (as `obserwator stations find` does: a fragment of the name or the river, a
// prefix of the code), filters by provider, kind, the datasets holding the station (chips,
// any of those chosen) and „tylko czynne”, the counts „na mapie N · bez współrzędnych M”
// and the list, which keeps the stations without coordinates, marked; a click selects the
// station and the map flies to it when it has a location. The filters choose the map's
// stations too (`onMap`); the search is the list's.

import { fmt, html, t, tn, useEffect, useMemo, useRef, useState } from "./lib.js";
import { StationSymbol } from "./symbols.js";
import { Seg } from "./ui/seg.js";
import { DATASET_STEPS, datasetShort, datasetTitle, kindName, providerName } from "./words.js";

/** The filters of a first visit: every station of the catalogs. */
export const DEFAULT_FILTERS = Object.freeze({ query: "", provider: "all", kind: "all", datasets: Object.freeze([]), active: false });

const PAGE = 150;
/** The providers in the order of the registry. */
const PROVIDERS = ["IMGW-PIB", "CHMI"];
/** Station names are Polish and Czech: sorted as Polish, whatever the page's language. */
const collator = new Intl.Collator("pl", { sensitivity: "base", numeric: true });

/**
 * Text folded for search: lower case without diacritics; Polish ł has no decomposition.
 *
 * @param {string|null|undefined} text
 * @returns {string} e.g. "lodz" for "ŁÓDŹ", "spindleruv" for "Špindlerův"
 */
function fold(text) {
  return String(text ?? "")
    .toLowerCase()
    .replace(/\u0142/g, "l")
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "");
}

/**
 * The stations of `api/stations` with their folded names, in the list's order: those with
 * series first; within each group named stations before those without a catalog name
 * (IMGW-PIB rows whose name is their code, e.g. 151160270), then more series first, then by
 * name (code).
 *
 * @param {object[]} stations
 * @returns {object[]}
 */
export function prepareStations(stations) {
  const hasSeries = (station) => (station.datasets.length > 0 ? 1 : 0);
  return stations
    .map((station) => ({
      ...station,
      unnamed: !station.name || station.name === station.code,
      foldedName: fold(station.name),
      foldedRiver: fold(station.river),
      foldedCode: fold(station.code),
    }))
    .sort((a, b) => hasSeries(b) - hasSeries(a) || a.unnamed - b.unnamed || b.datasets.length - a.datasets.length || collator.compare(a.name || a.code, b.name || b.code));
}

/** Whether the map shows a station under the filters (provider, kind, datasets, active); the search is the list's only. */
export function onMap(station, filters) {
  if (filters.provider !== "all" && station.provider !== filters.provider) return false;
  if (filters.kind !== "all" && station.kind !== filters.kind) return false;
  if (filters.active && !station.active) return false;
  const chosen = filters.datasets || [];
  if (chosen.length && !station.datasets.some((key) => chosen.includes(key))) return false;
  return true;
}

function matches(station, filters, needle) {
  if (!onMap(station, filters)) return false;
  if (!needle) return true;
  return station.foldedName.includes(needle) || station.foldedRiver.includes(needle) || station.foldedCode.startsWith(needle);
}

/**
 * The datasets of the stations, each with the provider and kind of the stations it holds,
 * in the order of the registry (words.js), unknown ones last.
 *
 * @param {object[]} stations
 * @returns {Array<{key: string, provider: string, kind: string}>}
 */
function datasetsOf(stations) {
  const found = new Map();
  for (const station of stations) {
    for (const key of station.datasets) {
      if (!found.has(key)) found.set(key, { key, provider: station.provider, kind: station.kind });
    }
  }
  const order = Object.keys(DATASET_STEPS);
  const rank = (key) => (order.includes(key) ? order.indexOf(key) : order.length);
  return [...found.values()].sort((a, b) => rank(a.key) - rank(b.key) || a.key.localeCompare(b.key));
}

/** Whether a dataset's chip belongs under the provider and kind chosen. */
function offered(entry, filters) {
  return (filters.provider === "all" || entry.provider === filters.provider) && (filters.kind === "all" || entry.kind === filters.kind);
}

/** Bring a station's row into the list's view when its scrolling box shows (not a closed sheet). */
function reveal(item) {
  let box = item.parentElement;
  while (box && box !== document.body) {
    const overflow = getComputedStyle(box).overflowY;
    if ((overflow === "auto" || overflow === "scroll") && box.scrollHeight > box.clientHeight) break;
    box = box.parentElement;
  }
  if (!box || box === document.body || !box.clientHeight) return;
  const top = item.getBoundingClientRect().top - box.getBoundingClientRect().top + box.scrollTop;
  const bottom = top + item.offsetHeight;
  if (top < box.scrollTop) box.scrollTop = top - 8;
  else if (bottom > box.scrollTop + box.clientHeight) box.scrollTop = bottom - box.clientHeight + 8;
}

/** The chips of the datasets that hold stations, grouped by provider. */
function DatasetChips({ entries, filters, onToggle }) {
  const providers = [...new Set([...PROVIDERS, ...entries.map((entry) => entry.provider)])];
  const groups = providers
    .map((provider) => [provider, entries.filter((entry) => entry.provider === provider && offered(entry, filters))])
    .filter(([, shown]) => shown.length);
  if (!groups.length) return null;
  return html`<div class="ds-filter" role="group" aria-label=${t("stations.list.datasets")}>
    <span class="ds-title">${t("stations.list.datasets")}</span>
    ${groups.map(
      ([provider, shown]) => html`<div class="ds-group" key=${provider}>
        <span class="ds-provider">${providerName(provider)}</span>
        <span class="ds-chips">
          ${shown.map((entry) => {
            const on = filters.datasets.includes(entry.key);
            const title = datasetTitle(entry.key);
            return html`<button
              type="button"
              key=${entry.key}
              class=${on ? "chip ds-chip on" : "chip ds-chip"}
              aria-pressed=${String(on)}
              aria-label=${title}
              title=${title}
              onClick=${() => onToggle(entry.key)}
            >
              <${StationSymbol} kind=${entry.kind} provider=${entry.provider} data=${true} size=${11} />${datasetShort(entry.key)}
            </button>`;
          })}
        </span>
      </div>`,
    )}
  </div>`;
}

/**
 * The second line of a station's row: river (or kind), provider and years of its series,
 * shortened when long, then what never is: inactive, no coordinates.
 */
function StationSub({ station }) {
  const facts = [
    station.river || kindName(station.kind),
    providerName(station.provider),
    station.first ? `${station.first}–${station.last}` : t("stations.catalog_only"),
  ];
  return html`<span class="st-sub">
    <span class="st-facts">${facts.join(" · ")}</span>
    ${station.active ? null : html`<span class="st-flag">· ${t("stations.inactive")}</span>`}
    ${station.lon === null ? html`<span class="st-flag">· <span class="no-loc">${t("stations.list.no_location")}</span></span>` : null}
  </span>`;
}

/**
 * The panel's body.
 *
 * @param {{stations: object[], filters: object, onFilters: (next: object) => void,
 *   selected: string|null, onSelect: (code: string, options: {fly: boolean}) => void}} props
 *   the stations of prepareStations, the filters (DEFAULT_FILTERS' fields), their handler,
 *   the selected station and the selection's handler
 * @returns {object}
 */
export function StationList({ stations, filters, onFilters, selected, onSelect }) {
  const [shown, setShown] = useState(PAGE);
  const list = useRef(null);
  const needle = fold(filters.query.trim());
  const found = useMemo(() => stations.filter((station) => matches(station, filters, needle)), [stations, filters, needle]);
  const datasets = useMemo(() => datasetsOf(stations), [stations]);
  const located = found.filter((station) => station.lon !== null).length;
  const change = (next) => {
    setShown(PAGE);
    // A dataset chosen under another provider or kind is dropped with its chip
    const chosen = (next.datasets || []).filter((key) => {
      const entry = datasets.find((item) => item.key === key);
      return entry && offered(entry, next);
    });
    onFilters({ ...next, datasets: chosen });
  };
  const set = (key) => (value) => change({ ...filters, [key]: value });
  const toggle = (key) => change({ ...filters, datasets: filters.datasets.includes(key) ? filters.datasets.filter((item) => item !== key) : [...filters.datasets, key] });
  const filtered = filters.provider !== "all" || filters.kind !== "all" || filters.active || filters.datasets.length > 0 || filters.query.trim() !== "";
  // „N stacji · na mapie N · bez współrzędnych M”, wrapped only between its parts
  const counts = [
    html`<strong>${fmt(found.length)}</strong> ${tn("stations.list.found", found.length)}`,
    t("stations.list.on_map", { n: fmt(located) }),
    t("stations.list.unlocated", { n: fmt(found.length - located) }),
  ];

  // A station chosen on the map or by the address: its row comes into view when listed
  useEffect(() => {
    if (!selected || !list.current) return;
    const item = [...list.current.querySelectorAll("[data-code]")].find((node) => node.dataset.code === selected);
    if (item) reveal(item);
  }, [selected, stations]);

  return html`<div class="station-list">
    <label class="search">
      <svg viewBox="0 0 20 20" aria-hidden="true"><circle cx="8.5" cy="8.5" r="5.5" /><path d="M13 13l4 4" /></svg>
      <input
        type="search"
        placeholder=${t("stations.list.search_placeholder")}
        aria-label=${t("stations.list.search_label")}
        value=${filters.query}
        onInput=${(event) => set("query")(event.target.value)}
      />
    </label>
    <div class="filters">
      <${Seg}
        full
        tiny
        label=${t("stations.list.provider")}
        value=${filters.provider}
        onChange=${set("provider")}
        items=${[{ value: "all", label: t("stations.list.provider_all") }, ...PROVIDERS.map((id) => ({ value: id, label: providerName(id) }))]}
      />
      <${Seg}
        full
        tiny
        label=${t("stations.list.kind")}
        value=${filters.kind}
        onChange=${set("kind")}
        items=${[
          { value: "all", label: t("stations.list.kind_all") },
          { value: "hydro", label: t("stations.list.kind_hydro") },
          { value: "meteo", label: t("stations.list.kind_meteo") },
        ]}
      />
      <${DatasetChips} entries=${datasets} filters=${filters} onToggle=${toggle} />
      <div class="check-row">
        <label class="check"><input type="checkbox" checked=${filters.active} onChange=${(event) => set("active")(event.target.checked)} />${t("stations.list.active_only")}</label>
      </div>
    </div>
    <p class="counts" aria-live="polite">${counts.map((part, index) => html`${index ? " · " : ""}<span class="count">${part}</span>`)}</p>
    ${found.length
      ? html`<ul class="stations" role="list" ref=${list}>
          ${found.slice(0, shown).map(
            (station) => html`<li key=${station.code}>
              <button
                type="button"
                data-code=${station.code}
                class=${station.code === selected ? "st-item sel" : "st-item"}
                aria-current=${station.code === selected ? "true" : undefined}
                onClick=${() => onSelect(station.code, { fly: true })}
              >
                <${StationSymbol} kind=${station.kind} provider=${station.provider} data=${station.datasets.length > 0} active=${station.active} />
                <span class="st-name">${station.name || station.code}</span>
                <code class="st-code">${station.code}</code>
                <${StationSub} station=${station} />
              </button>
            </li>`,
          )}
        </ul>`
      : html`<div class="empty-note">
          <p>${t("stations.list.none")}</p>
          ${filtered ? html`<button type="button" class="btn sm" onClick=${() => change(DEFAULT_FILTERS)}>${t("stations.list.clear")}</button>` : null}
        </div>`}
    ${found.length > shown
      ? html`<button type="button" class="btn sm more" onClick=${() => setShown(shown + PAGE)}>
          ${t("stations.list.more", { count: fmt(Math.min(PAGE, found.length - shown)), rest: fmt(found.length - shown) })}
        </button>`
      : null}
  </div>`;
}
