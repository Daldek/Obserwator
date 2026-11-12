// The mockup of Obserwator's GUI (plan 2026-11-12-obserwator-gui, pending): every station of
// the catalogs on a map, the chosen station in the right panel (Hydrograf's form), in
// Nogat's shell (design/README.md): the top bar, „Stacje” | map | „Stacja”, bottom sheets on
// a phone. The address keeps the station, its open section and the map's layer (state.js).

import { api } from "./api.js";
import { html, render, useEffect, useMemo, useState } from "./lib.js";
import { DEFAULT_FILTERS, StationList, onMap, prepareStations } from "./list.js";
import { StationMap } from "./map.js";
import { NoStation, StationPanel } from "./panel.js";
import { readAddress, writeAddress } from "./state.js";
import { Seg } from "./ui/seg.js";
import { openPanel } from "./ui/sheet.js";
import { TopBar } from "./ui/top-bar.js";
import { ViewLayout } from "./ui/view-layout.js";

const LAYERS = [
  { value: "stations", label: "Stacje" },
  { value: "states", label: "Stan wody (IMGW-PIB)" },
];

function App() {
  const [start] = useState(readAddress);
  const [meta, setMeta] = useState(null);
  const [stations, setStations] = useState(null);
  const [failure, setFailure] = useState(null);
  const [selected, setSelected] = useState(start.station);
  const [open, setOpen] = useState(start.section ? [start.section] : ["dane"]);
  const [section, setSection] = useState(start.section);
  const [filters, setFilters] = useState(DEFAULT_FILTERS);
  const [layer, setLayer] = useState(start.layer);
  const [fly, setFly] = useState(start.station ? { code: start.station, n: 0 } : null);

  useEffect(() => {
    api.meta().then(setMeta, setFailure);
    api.stations().then((doc) => setStations(prepareStations(doc.stations)), setFailure);
    // A link to a station opens its panel, on a phone as the sheet
    if (start.station) openPanel("right");
  }, []);
  useEffect(() => writeAddress({ station: selected, section, layer }), [selected, section, layer]);

  const all = stations || [];
  const byCode = useMemo(() => new Map(all.map((station) => [station.code, station])), [stations]);
  const drawn = useMemo(() => all.filter((station) => onMap(station, filters)), [stations, filters.provider, filters.kind, filters.active]);
  const station = selected ? byCode.get(selected) || null : null;

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

  const left = {
    title: "Stacje",
    body: failure
      ? html`<p class="ana-error">Serwer makiety nie odpowiada: ${failure.message}</p>`
      : stations
        ? html`<${StationList} stations=${all} filters=${filters} onFilters=${setFilters} selected=${selected} onSelect=${select} />`
        : html`<p class="muted">Wczytuję katalog stacji…</p>`,
  };
  const center = {
    label: "Mapa stacji",
    bar: html`<${Seg} items=${LAYERS} value=${layer} onChange=${setLayer} label="Warstwa mapy" className="layer-seg" />
      <span class="hint">${layer === "states" ? "Stany wody IMGW-PIB z bieżącej migawki serwera" : "Kliknij stację, aby zobaczyć jej dane"}</span>`,
    body: html`<${StationMap} stations=${drawn} byCode=${byCode} selected=${selected} fly=${fly} layer=${layer} onSelect=${(code) => select(code)} />`,
  };
  const right = {
    title: "Stacja",
    sub: station ? station.code : null,
    short: station ? station.name || station.code : "Stacja",
    body: selected
      ? html`<${StationPanel} key=${selected} code=${selected} meta=${meta} open=${open} focus=${start.station === selected ? start.section : null} onToggle=${toggle} />`
      : html`<${NoStation} meta=${meta} stations=${all} />`,
  };
  return html`
    <${TopBar} meta=${meta} station=${station} />
    <main class="main">
      <${ViewLayout} left=${left} center=${center} right=${right} />
    </main>
  `;
}

render(html`<${App} />`, document.getElementById("app"));
