// Obserwator's GUI (plan 2026-11-12-obserwator-gui): every station of the catalogs on a
// map, the chosen station in the right panel (Hydrograf's form), in Nogat's shell (design/
// README.md): the top bar, „Stacje” | map | „Stacja”, bottom sheets on a phone. The map's
// bar switches the views: „Stacje” (the catalogs), „Pomiary bieżące” (IMGW-PIB's current
// measurements, current.js) and „PMAXTP” (plan D12: the form takes the left panel and the
// results the right one; no layer of the PMAXTP grid). The address keeps the station, its
// open section, the view and the PMAXTP point (state.js). Every view shows the lines of its
// data in one compact strip across the page under the map and both panels (attribution.js
// `Sources`, Nogat DEV-20.5; the layout's `foot`): the union of the lines of what the list
// and the map show and of what the right panel shows (the station's cards, the stations'
// files, PMAXTP's tables), with the lines of the packaged borders while they are the map's
// background (GUGiK's and ČÚZK's, ADR-018) and the basemap's credit after them; never one
// per card. On a phone the sheets stop above it. A first visit opens the welcome window
// with every line (ui/welcome.js). A public deployment adds „Regulamin” and the service's
// statement under the strip. „Zgłoś uwagę” (ui/feedback.js) sends the view, the station and
// the address's parameters.
//
// Every word comes from the message catalog in the page's language (i18n.js): the texts
// load before the first render, and the page renders again when the language changes.

import { api } from "./api.js";
import { BORDER_SOURCES, PublicNotice, Sources, catalogSources, compose, merge, setTexts, useTexts } from "./attribution.js";
import { clock, useCurrent } from "./current.js";
import { lang, loadTexts, onLangChange, storedLang } from "./i18n.js";
import { html, render, t, useEffect, useMemo, useState } from "./lib.js";
import { DEFAULT_FILTERS, StationList, onMap, prepareStations } from "./list.js";
import { StationMap } from "./map.js";
import { NoStation, StationPanel, sectionTitle } from "./panel.js";
import { PmaxtpForm } from "./pmaxtp/form.js";
import { PmaxtpResult } from "./pmaxtp/result.js";
import { pointLabel, round4, usePmaxtp } from "./pmaxtp/state.js";
import { readAddress, writeAddress } from "./state.js";
import { FeedbackDialog } from "./ui/feedback.js";
import { Seg } from "./ui/seg.js";
import { openPanel } from "./ui/sheet.js";
import { ToastHost, toast } from "./ui/toast.js";
import { TopBar } from "./ui/top-bar.js";
import { ViewLayout } from "./ui/view-layout.js";
import { WelcomeDialog } from "./ui/welcome.js";

/** The sections open on a first visit: the current measurements and the measurement data. */
const FIRST_OPEN = ["teraz", "dane"];

/** The views of the map's bar, named in the page's language. */
function views() {
  return [
    { value: "stations", label: t("shell.view_stations") },
    { value: "current", label: t("shell.view_current") },
    { value: "pmaxtp", label: "PMAXTP" },
  ];
}

/** What the bar says in „Pomiary bieżące”: the snapshot's time (plan D9). */
function currentHint(current) {
  if (current.doc) {
    const times = Object.values(current.doc.snapshots)
      .map((snap) => snap.fetched_at)
      .filter(Boolean)
      .sort();
    return t("shell.hint.current", { time: clock(times[times.length - 1]) });
  }
  if (current.error) return t("shell.hint.current_failed", { reason: current.error.message });
  return t("shell.hint.current_loading");
}

function App({ lang: language }) {
  const [start] = useState(readAddress);
  const [session, setSession] = useState(null);
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
  // The lines of what the station panel shows (panel.js `onLines`), whether the packaged
  // borders are the map's background and the basemap's credit (map.js `onBorders`,
  // `onCredit`)
  const [panelLines, setPanelLines] = useState(null);
  const [borders, setBorders] = useState(false);
  const [credit, setCredit] = useState(null);

  useEffect(() => {
    api.stations().then((doc) => setStations(prepareStations(doc.stations)), setFailure);
    // A link to a station or to a PMAXTP point opens its panel, on a phone as the sheet
    if (start.view === "pmaxtp" ? start.point : start.station) openPanel("right");
  }, []);
  // The session again in each language: its error texts follow the page's language
  useEffect(() => {
    let live = true;
    api.session().then(
      (doc) => {
        if (!live) return;
        setTexts(doc.attribution);
        setSession(doc);
      },
      (error) => {
        if (live) toast(t("shell.session_failed", { reason: error.message }), "bad");
      },
    );
    return () => {
      live = false;
    };
  }, [language]);
  useEffect(() => writeAddress({ station: selected, section, view, point: pick, method }), [selected, section, view, pick, method]);

  const all = stations || [];
  const byCode = useMemo(() => new Map(all.map((station) => [station.code, station])), [stations]);
  const drawn = useMemo(
    () => all.filter((station) => onMap(station, filters)),
    [stations, filters.provider, filters.kind, filters.datasets, filters.active],
  );
  const station = selected ? byCode.get(selected) || null : null;
  const texts = useTexts();
  const listed = useMemo(() => compose(texts, catalogSources(drawn)), [texts, drawn]);
  const background = useMemo(() => (borders ? compose(texts, BORDER_SOURCES) : null), [texts, borders]);
  const pmaxtpView = view === "pmaxtp";
  // The view's lines: what the list and the map show, the map's background and what the
  // right panel shows
  const shown = pmaxtpView ? [pmaxtp.doc, background] : [listed, view === "current" ? current.doc : null, background, panelLines];
  const lines = merge(texts, shown);
  const viewItems = views();
  const viewName = viewItems.find((item) => item.value === view).label;
  // What „Zgłoś uwagę” shows and sends: the view and, outside PMAXTP, the station of the
  // catalog with its open section, read when the dialog opens
  const captureFeedback = () => {
    const shown = pmaxtpView ? null : station;
    return {
      view,
      viewName,
      station: shown ? shown.code : null,
      stationName: shown ? shown.name || null : null,
      sectionTitle: shown && section ? sectionTitle(shown.kind, section) : null,
    };
  };

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
        title: t("shell.panel.stations"),
        body: failure
          ? html`<p class="ana-error" role="alert">${t("shell.stations_failed", { reason: failure.message })}</p>`
          : stations
            ? html`<${StationList} stations=${all} filters=${filters} onFilters=${setFilters} selected=${selected} onSelect=${select} />`
            : html`<p class="muted" role="status">${t("shell.stations_loading")}</p>`,
      };
  const hints = {
    stations: t("shell.hint.stations"),
    current: currentHint(current),
    pmaxtp: t("shell.hint.pmaxtp"),
  };
  const center = {
    label: pmaxtpView ? t("shell.map_pmaxtp") : t("shell.map"),
    bar: html`<${Seg} items=${viewItems} value=${view} onChange=${setView} label=${t("shell.views")} />
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
      onBorders=${setBorders}
      onCredit=${setCredit}
      session=${session}
      onSelect=${(code) => select(code)}
      onPick=${choosePoint}
    />`,
  };
  const foot =
    lines || credit || (session && session.terms)
      ? html`${lines || credit
            ? html`<div class="view-sources">
                <${Sources} fields=${lines} session=${session} />
                ${credit ? html`<span class="map-basemap">${credit}</span>` : null}
              </div>`
            : null}
          <${PublicNotice} session=${session} />`
      : null;
  const right = pmaxtpView
    ? {
        title: t("shell.panel.pmaxtp"),
        sub: pick ? method : null,
        short: t("shell.panel.pmaxtp"),
        body: html`<${PmaxtpResult} point=${pick} method=${method} state=${pmaxtp} />`,
      }
    : {
        title: t("shell.panel.station"),
        sub: station ? station.code : null,
        short: station ? station.name || station.code : t("shell.panel.station"),
        body: selected
          ? html`<${StationPanel} key=${selected} code=${selected} session=${session} open=${open} focus=${start.station === selected ? start.section : null} onToggle=${toggle} onLines=${setPanelLines} />`
          : html`<${NoStation} session=${session} stations=${all} provider=${filters.provider} kind=${filters.kind} onLines=${setPanelLines} />`,
      };
  return html`
    <${TopBar}
      session=${session}
      station=${pmaxtpView ? null : station}
      section=${viewName}
      context=${pmaxtpView && pick ? `${method} · ${pointLabel(pick)}` : null}
    />
    <main class="main">
      <${ViewLayout} left=${left} center=${center} right=${right} foot=${foot} />
    </main>
    <${FeedbackDialog} capture=${captureFeedback} session=${session} />
    <${WelcomeDialog} session=${session} />
    <${ToastHost} />
  `;
}

const root = document.getElementById("app");

/** Draw the page in the language of the texts now loaded. */
function draw() {
  render(html`<${App} lang=${lang()} />`, root);
}

loadTexts(storedLang()).then(
  () => {
    draw();
    onLangChange(draw);
  },
  () => {
    // Without its texts the page cannot speak: index.html's own message, in both languages
    const message = document.getElementById("boot-error");
    if (message) message.hidden = false;
  },
);
