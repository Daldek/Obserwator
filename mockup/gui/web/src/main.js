// The mockup of Obserwator's GUI (plan 2026-11-12-obserwator-gui, pending): every station of
// the catalogs on a map, the chosen station in the right panel (Hydrograf's form), in
// Nogat's shell (design/README.md): the top bar, „Stacje” | map | „Stacja”, bottom sheets on
// a phone. The map's bar switches the views: „Stacje” (the catalogs), „Pomiary bieżące”
// (IMGW-PIB's current measurements, current.js) and „PMAXTP” (plan D12: the form takes the
// left panel and the results the right one; no layer of the PMAXTP grid). The address
// keeps the station, its open section, the view and the PMAXTP point (state.js).

import { api } from "./api.js";
import { clock, useCurrent } from "./current.js";
import { html, render, useEffect, useMemo, useState } from "./lib.js";
import { DEFAULT_FILTERS, StationList, onMap, prepareStations } from "./list.js";
import { StationMap } from "./map.js";
import { NoStation, StationPanel } from "./panel.js";
import { PmaxtpForm } from "./pmaxtp/form.js";
import { PmaxtpResult } from "./pmaxtp/result.js";
import { pointLabel, round4, usePmaxtp } from "./pmaxtp/state.js";
import { readAddress, writeAddress } from "./state.js";
import { Seg } from "./ui/seg.js";
import { openPanel } from "./ui/sheet.js";
import { TopBar } from "./ui/top-bar.js";
import { ViewLayout } from "./ui/view-layout.js";

const VIEWS = [
  { value: "stations", label: "Stacje" },
  { value: "current", label: "Pomiary bieżące" },
  { value: "pmaxtp", label: "PMAXTP" },
];
/** The sections open on a first visit: the current measurements and the measurement data. */
const FIRST_OPEN = ["teraz", "dane"];

/** What the bar says in „Pomiary bieżące”: the snapshot's time (plan D9). */
function currentHint(current) {
  if (current.doc) {
    const times = Object.values(current.doc.snapshots)
      .map((snap) => snap.fetched_at)
      .filter(Boolean)
      .sort();
    return `Migawka IMGW-PIB z ${clock(times[times.length - 1])}; kliknij stację, aby zobaczyć jej pomiary`;
  }
  if (current.error) return `Pomiary bieżące niedostępne: ${current.error.message}`;
  return "Pobieram pomiary bieżące z IMGW-PIB…";
}

function App() {
  const [start] = useState(readAddress);
  const [meta, setMeta] = useState(null);
  const [stations, setStations] = useState(null);
  const [failure, setFailure] = useState(null);
  const [selected, setSelected] = useState(start.station);
  const [open, setOpen] = useState(start.section ? [start.section] : FIRST_OPEN);
  const [section, setSection] = useState(start.section);
  const [filters, setFilters] = useState(DEFAULT_FILTERS);
  const [view, setView] = useState(start.view);
  const [fly, setFly] = useState(start.station ? { code: start.station, n: 0 } : null);
  const [pick, setPick] = useState(start.point ? { lat: round4(start.point.lat), lon: round4(start.point.lon) } : null);
  const [pickFly, setPickFly] = useState(start.point && start.view === "pmaxtp" ? { n: 0 } : null);
  const [method, setMethod] = useState(start.method);
  const current = useCurrent(view === "current");
  const pmaxtp = usePmaxtp(pick, method);

  useEffect(() => {
    api.meta().then(setMeta, setFailure);
    api.stations().then((doc) => setStations(prepareStations(doc.stations)), setFailure);
    // A link to a station or to a PMAXTP point opens its panel, on a phone as the sheet
    if (start.view === "pmaxtp" ? start.point : start.station) openPanel("right");
  }, []);
  useEffect(() => writeAddress({ station: selected, section, view, point: pick, method }), [selected, section, view, pick, method]);

  const all = stations || [];
  const byCode = useMemo(() => new Map(all.map((station) => [station.code, station])), [stations]);
  const drawn = useMemo(() => all.filter((station) => onMap(station, filters)), [stations, filters.provider, filters.kind, filters.active]);
  const station = selected ? byCode.get(selected) || null : null;
  const pmaxtpView = view === "pmaxtp";

  const select = (code, { fly: go = false } = {}) => {
    setSelected(code);
    if (go) setFly({ code, n: Date.now() });
    openPanel("right");
  };
  const toggle = (id) => {
    if (open.includes(id)) {
      const rest = open.filter((item) => item !== id);
      setOpen(rest);
      if (section === id) setSection(rest.length ? rest[rest.length - 1] : null);
    } else {
      setOpen([...open, id]);
      setSection(id);
    }
  };
  const choosePoint = (point, { fly: go = false } = {}) => {
    setPick({ lat: round4(point.lat), lon: round4(point.lon) });
    if (go) setPickFly({ n: Date.now() });
    openPanel("right");
  };

  const left = pmaxtpView
    ? { title: "PMAXTP", body: html`<${PmaxtpForm} point=${pick} method=${method} onPoint=${choosePoint} onMethod=${setMethod} />` }
    : {
        title: "Stacje",
        body: failure
          ? html`<p class="ana-error">Serwer makiety nie odpowiada: ${failure.message}</p>`
          : stations
            ? html`<${StationList} stations=${all} filters=${filters} onFilters=${setFilters} selected=${selected} onSelect=${select} />`
            : html`<p class="muted">Wczytuję katalog stacji…</p>`,
      };
  const hints = {
    stations: "Kliknij stację, aby zobaczyć jej dane",
    current: currentHint(current),
    pmaxtp: "Kliknij mapę albo wpisz współrzędne po lewej",
  };
  const center = {
    label: pmaxtpView ? "Mapa: wybór punktu PMAXTP" : "Mapa stacji",
    bar: html`<${Seg} items=${VIEWS} value=${view} onChange=${setView} label="Widok mapy" />
      <span class="hint">${hints[view]}</span>`,
    body: html`<${StationMap}
      stations=${drawn}
      byCode=${byCode}
      selected=${selected}
      fly=${fly}
      view=${view}
      current=${current}
      pick=${pick}
      pickFly=${pickFly}
      onSelect=${(code) => select(code)}
      onPick=${choosePoint}
    />`,
  };
  const right = pmaxtpView
    ? {
        title: "Wyniki PMAXTP",
        sub: pick ? method : null,
        short: "Wyniki PMAXTP",
        body: html`<${PmaxtpResult} point=${pick} method=${method} state=${pmaxtp} />`,
      }
    : {
        title: "Stacja",
        sub: station ? station.code : null,
        short: station ? station.name || station.code : "Stacja",
        body: selected
          ? html`<${StationPanel} key=${selected} code=${selected} meta=${meta} open=${open} focus=${start.station === selected ? start.section : null} onToggle=${toggle} />`
          : html`<${NoStation} meta=${meta} stations=${all} />`,
      };
  return html`
    <${TopBar}
      meta=${meta}
      station=${pmaxtpView ? null : station}
      section=${pmaxtpView ? "PMAXTP" : "Stacje"}
      context=${pmaxtpView && pick ? `${method} · ${pointLabel(pick)}` : null}
    />
    <main class="main">
      <${ViewLayout} left=${left} center=${center} right=${right} />
    </main>
  `;
}

render(html`<${App} />`, document.getElementById("app"));
