// The theme of the page (Nogat design/README.md, Theme), after Hydrolog's GUI (src/host.js):
// "auto" follows the system, "light" and "dark" set <html data-theme> and are stored under
// the key "nogat-theme", shared by Nogat's pages on one origin; theme-init.js applies the
// stored choice before the first paint. `useDark` tells a canvas (the map) which theme is
// shown, whether chosen or the system's.

import { useEffect, useState } from "../lib.js";

/** localStorage key of the theme, shared by Nogat's pages on one origin. */
export const THEME_KEY = "nogat-theme";

const root = document.documentElement;
const darkQuery = window.matchMedia("(prefers-color-scheme: dark)");
const listeners = new Set();

/**
 * The stored theme choice.
 *
 * @returns {"auto"|"light"|"dark"} "auto" follows the system
 */
export function storedTheme() {
  try {
    const value = window.localStorage.getItem(THEME_KEY);
    return value === "light" || value === "dark" ? value : "auto";
  } catch {
    return "auto";
  }
}

/** Whether the page shows the dark theme now. */
export function isDark() {
  const chosen = root.dataset.theme;
  if (chosen === "dark") return true;
  if (chosen === "light") return false;
  return darkQuery.matches;
}

function emit() {
  const dark = isDark();
  for (const listener of [...listeners]) listener(dark);
}

darkQuery.addEventListener("change", emit);

function showTheme(choice) {
  if (choice === "light" || choice === "dark") root.dataset.theme = choice;
  else delete root.dataset.theme;
  emit();
}

/**
 * Choose a theme: shown at once and stored for every page of the origin.
 *
 * @param {"auto"|"light"|"dark"} choice the theme
 */
export function setTheme(choice) {
  showTheme(choice);
  try {
    window.localStorage.setItem(THEME_KEY, choice);
  } catch {
    // Storage blocked: the choice lasts until the page closes.
  }
}

/**
 * The theme choice, following changes made in other pages of the origin.
 *
 * @returns {["auto"|"light"|"dark", (choice: string) => void]} the choice and its setter
 */
export function useTheme() {
  const [choice, setChoice] = useState(storedTheme);
  useEffect(() => {
    const onStorage = (event) => {
      if (event.key !== THEME_KEY && event.key !== null) return;
      const next = storedTheme();
      showTheme(next);
      setChoice(next);
    };
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, []);
  return [
    choice,
    (next) => {
      setTheme(next);
      setChoice(next);
    },
  ];
}

/**
 * Whether the dark theme is shown, following the switch and the system.
 *
 * @returns {boolean}
 */
export function useDark() {
  const [dark, setDark] = useState(isDark);
  useEffect(() => {
    listeners.add(setDark);
    return () => listeners.delete(setDark);
  }, []);
  return dark;
}
