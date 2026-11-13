// The top bar (Nogat design/README.md, Layout; plan D15; after Hydrolog's GUI,
// src/ui/top-bar.js): Obserwator's mark and name, the badge that says this is a mockup, the
// view and what it shows (the selected station, or the PMAXTP point), Nogat's app menu
// „Aplikacje” (the kit's <nogat-app-menu>, the deployment's [nogat] gui of nogat.toml from
// api/meta) and the theme switch Auto, Jasny, Ciemny. Inside Nogat's shell ("?nogat=1") the
// shell's own bar replaces it.

import "../../nogat/nogat-app-menu.js";
import { html, useEffect, useRef } from "../lib.js";
import { Seg } from "./seg.js";
import { useTheme } from "./theme.js";

const ICONS = {
  auto: () => html`<svg class="icon-svg" viewBox="0 0 20 20" aria-hidden="true"><circle cx="10" cy="10" r="6.5" /><path d="M10 3.5v13a6.5 6.5 0 0 0 0-13z" fill="currentColor" /></svg>`,
  light: () => html`<svg class="icon-svg" viewBox="0 0 20 20" aria-hidden="true"><circle cx="10" cy="10" r="3.5" /><path d="M10 2v2M10 16v2M2 10h2M16 10h2M4.3 4.3l1.4 1.4M14.3 14.3l1.4 1.4M4.3 15.7l1.4-1.4M14.3 5.7l1.4-1.4" /></svg>`,
  dark: () => html`<svg class="icon-svg" viewBox="0 0 20 20" aria-hidden="true"><path d="M16 12.5A6.5 6.5 0 0 1 7.5 4a6.5 6.5 0 1 0 8.5 8.5z" /></svg>`,
};

/** What the badge says, and its longer explanation. */
export const MOCKUP_BADGE = "Makieta — dane prawdziwe, obliczenia Hydrologa i prototypy";
const MOCKUP_TITLE =
  "Makieta GUI Obserwatora do przeglądu: szeregi IMGW-PIB i ČHMÚ z magazynu demonstracyjnego, " +
  "wartości bieżące wprost z IMGW-PIB, analizy liczone poleceniami Hydrologa albo — gdzie Hydrolog " +
  "ich jeszcze nie ma — oznaczonymi prototypami.";

/** The theme switch: Auto (the system's), Jasny, Ciemny; stored as "nogat-theme". */
export function ThemeSwitch() {
  const [choice, setChoice] = useTheme();
  const items = [
    { value: "auto", label: "Auto", title: "Motyw systemu", icon: ICONS.auto() },
    { value: "light", label: "Jasny", title: "Jasny", icon: ICONS.light() },
    { value: "dark", label: "Ciemny", title: "Ciemny", icon: ICONS.dark() },
  ];
  return html`<${Seg} items=${items} value=${choice} onChange=${setChoice} label="Motyw" mode="pressed" />`;
}

/**
 * Nogat's app menu (`<nogat-app-menu>`, a copy of Nogat's kit): the GUIs of the deployment's
 * `[nogat] gui` table, which `api/meta` gives as `gui`. The element draws nothing while the
 * table names no GUI but Obserwator.
 */
export function AppMenu({ apps }) {
  const menu = useRef(null);
  const key = JSON.stringify(apps || null);
  useEffect(() => {
    if (menu.current) menu.current.apps = apps || null;
  }, [key]);
  return html`<nogat-app-menu ref=${menu} current="obserwator" marks="nogat/marks/"></nogat-app-menu>`;
}

/**
 * The top bar.
 *
 * @param {{meta: object|null, station: {code: string, name?: string, river?: string}|null,
 *   section?: string, context?: string|null}} props the server's meta (its `gui`), the
 *   selected station, the view's name and, without a station, what the view shows
 * @returns {object} the bar
 */
export function TopBar({ meta, station, section = "Stacje", context = null }) {
  const name = station ? station.name || station.code : context;
  useEffect(() => {
    document.title = name ? `${name} — Obserwator (makieta)` : "Obserwator — makieta";
  }, [name]);
  return html`<header class="topbar">
    <a class="brand" href="./" aria-label="Obserwator: strona główna">
      <img src="nogat/marks/obserwator.svg" alt="" width="24" height="24" />
      <span class="name">Obserwator</span>
    </a>
    <span class="badge info mockup-badge" title=${MOCKUP_TITLE}><span class="label">${MOCKUP_BADGE}</span></span>
    <nav class="crumbs" aria-label=${station ? "Wybrana stacja" : section}>
      <span class="crumb-section">${section}</span>
      ${name
        ? html`<span class="sep" aria-hidden="true">/</span>
            <strong class="crumb-context">${name}${station && station.river ? html`<span class="crumb-river"> · ${station.river}</span>` : null}</strong>`
        : null}
    </nav>
    <div class="top-actions">
      <${AppMenu} apps=${meta ? meta.gui : null} />
      <${ThemeSwitch} />
    </div>
  </header>`;
}
