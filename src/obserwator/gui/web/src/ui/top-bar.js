// The top bar (Nogat design/README.md, Layout; plan D15; after Hydrolog's GUI,
// src/ui/top-bar.js): Obserwator's mark and name, the view and what it shows (the selected
// station, or the PMAXTP point), „Zgłoś uwagę” (feedback.js), „Instrukcja” (the guide,
// instrukcja/), Nogat's app menu „Aplikacje” (the kit's <nogat-app-menu>, the deployment's
// [nogat.gui] of nogat.toml from the session, with „Regulamin” in a public deployment),
// the language switch „PL | EN” (remembered under "obserwator-lang") and the theme switch
// Auto, Jasny, Ciemny. Inside Nogat's shell ("?nogat=1") the shell's own bar replaces it.

import "../../nogat/nogat-app-menu.js";
import { LANGS, lang, loadTexts } from "../i18n.js";
import { html, t, useEffect, useRef } from "../lib.js";
import { FeedbackButton } from "./feedback.js";
import { Seg } from "./seg.js";
import { useTheme } from "./theme.js";
import { toast } from "./toast.js";

const ICONS = {
  auto: () => html`<svg class="icon-svg" viewBox="0 0 20 20" aria-hidden="true"><circle cx="10" cy="10" r="6.5" /><path d="M10 3.5v13a6.5 6.5 0 0 0 0-13z" fill="currentColor" /></svg>`,
  light: () => html`<svg class="icon-svg" viewBox="0 0 20 20" aria-hidden="true"><circle cx="10" cy="10" r="3.5" /><path d="M10 2v2M10 16v2M2 10h2M16 10h2M4.3 4.3l1.4 1.4M14.3 14.3l1.4 1.4M4.3 15.7l1.4-1.4M14.3 5.7l1.4-1.4" /></svg>`,
  dark: () => html`<svg class="icon-svg" viewBox="0 0 20 20" aria-hidden="true"><path d="M16 12.5A6.5 6.5 0 0 1 7.5 4a6.5 6.5 0 1 0 8.5 8.5z" /></svg>`,
};

/** The book of „Instrukcja”, as in Hydrograf's and Hydrolog's top bars. */
const GUIDE_ICON = () => html`<svg class="icon-svg" viewBox="0 0 20 20" aria-hidden="true"><path d="M4 4.5A1.5 1.5 0 0 1 5.5 3H16v12H5.5A1.5 1.5 0 0 0 4 16.5z" /><path d="M4 16.5V4.5M7.5 6.5h5" /></svg>`;

/** The theme switch: Auto (the system's), Jasny, Ciemny; stored as "nogat-theme". */
export function ThemeSwitch() {
  const [choice, setChoice] = useTheme();
  const items = [
    { value: "auto", label: "Auto", title: t("shell.theme.auto"), icon: ICONS.auto() },
    { value: "light", label: t("shell.theme.light"), title: t("shell.theme.light"), icon: ICONS.light() },
    { value: "dark", label: t("shell.theme.dark"), title: t("shell.theme.dark"), icon: ICONS.dark() },
  ];
  return html`<${Seg} items=${items} value=${choice} onChange=${setChoice} label=${t("shell.theme.label")} mode="pressed" className="theme-switch" />`;
}

/**
 * The language switch „PL | EN”: the texts of the other language load and the page draws
 * itself again; the choice is remembered (i18n.js, "obserwator-lang").
 */
export function LangSwitch() {
  const items = LANGS.map((code) => ({ value: code, label: code.toUpperCase(), title: t(`shell.lang.${code}`) }));
  const choose = (next) => {
    if (next === lang()) return;
    loadTexts(next).catch((error) => toast(t("shell.lang_failed", { reason: error.message }), "bad"));
  };
  return html`<${Seg} items=${items} value=${lang()} onChange=${choose} label=${t("shell.lang.label")} mode="pressed" className="lang-switch" />`;
}

/**
 * Nogat's app menu (`<nogat-app-menu>`, a copy of Nogat's kit): the GUIs of the deployment's
 * `[nogat.gui]` table, which the session gives as `gui`, and „Regulamin” (`terms`) in a
 * public deployment. The element draws nothing while the table names no GUI but Obserwator.
 */
export function AppMenu({ apps, terms }) {
  const menu = useRef(null);
  const key = JSON.stringify(apps || null);
  useEffect(() => {
    if (menu.current) menu.current.apps = apps || null;
  }, [key]);
  return html`<nogat-app-menu ref=${menu} current="obserwator" marks="nogat/marks/" terms=${terms || undefined}></nogat-app-menu>`;
}

/**
 * The top bar.
 *
 * @param {{session: object|null, station: {code: string, name?: string, river?: string}|null,
 *   section: string, context?: string|null}} props the session (its `gui` and `terms`), the
 *   selected station, the view's name and, without a station, what the view shows
 * @returns {object} the bar
 */
export function TopBar({ session, station, section, context = null }) {
  const name = station ? station.name || station.code : context;
  useEffect(() => {
    document.title = name ? `${name} — Obserwator` : "Obserwator";
  }, [name]);
  return html`<header class="topbar">
    <a class="brand" href="./" aria-label=${t("shell.home")}>
      <img src="nogat/marks/obserwator.svg" alt="" width="24" height="24" />
      <span class="name">Obserwator</span>
    </a>
    <nav class="crumbs" aria-label=${station ? t("shell.selected_station") : section}>
      <span class="crumb-section">${section}</span>
      ${name
        ? html`<span class="sep" aria-hidden="true">/</span>
            <strong class="crumb-context">${name}${station && station.river ? html`<span class="crumb-river"> · ${station.river}</span>` : null}</strong>`
        : null}
    </nav>
    <div class="top-actions">
      <${FeedbackButton} />
      <a class="btn ghost guide-btn" href="instrukcja/" target="_blank" rel="noopener" aria-label=${t("shell.guide")} title=${t("shell.guide_title")}>
        ${GUIDE_ICON()}<span class="label">${t("shell.guide")}</span>
      </a>
      <${AppMenu} apps=${session ? session.gui : null} terms=${session ? session.terms : null} />
      <${LangSwitch} />
      <${ThemeSwitch} />
    </div>
  </header>`;
}
