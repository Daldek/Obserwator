// The page's texts and formats in its language (GUI plan D15): every word of the page is
// an entry of Obserwator's message catalog, area `gui`, fetched from `api/texts?lang=`;
// numbers and dates go through `Intl` in the same language. Polish by default, English
// from the switch, remembered under the key "obserwator-lang". A key is the catalog's
// without the area: t("shell.view_stations") is `gui.shell.view_stations`.

const STORAGE = "obserwator-lang";
/** The languages of the page, the default first. */
export const LANGS = ["pl", "en"];

let current = "pl";
let texts = {};
const listeners = new Set();
const numbers = new Map();
let plurals = new Intl.PluralRules("pl");

/** The language the page shows: "pl" or "en". */
export function lang() {
  return current;
}

/** The language chosen before (localStorage), else Polish. */
export function storedLang() {
  try {
    const value = window.localStorage.getItem(STORAGE);
    return LANGS.includes(value) ? value : "pl";
  } catch {
    return "pl";
  }
}

/**
 * Fetch the texts of a language and make it the page's; listeners re-render.
 *
 * @param {string} next "pl" or "en"
 * @returns {Promise<void>}
 */
export async function loadTexts(next) {
  const chosen = LANGS.includes(next) ? next : "pl";
  const response = await fetch(`api/texts?lang=${chosen}`, { headers: { Accept: "application/json" } });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  const doc = await response.json();
  texts = doc.texts || {};
  current = chosen;
  numbers.clear();
  plurals = new Intl.PluralRules(chosen);
  document.documentElement.lang = chosen;
  try {
    window.localStorage.setItem(STORAGE, chosen);
  } catch {
    // a private window: the choice lasts until the page is closed
  }
  for (const listener of listeners) listener(chosen);
}

/**
 * Be told when the language changes.
 *
 * @param {(lang: string) => void} listener
 * @returns {() => void} the function that stops it
 */
export function onLangChange(listener) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function render(template, values) {
  return template.replace(/\{\{|\}\}|\{([A-Za-z_][A-Za-z0-9_]*)\}/g, (match, name) => {
    if (match === "{{") return "{";
    if (match === "}}") return "}";
    const value = values[name];
    return value === undefined || value === null ? "" : String(value);
  });
}

/**
 * A text of the catalog in the page's language, its placeholders filled.
 *
 * @param {string} key the key without the area (`map.legend_title`)
 * @param {Record<string, unknown>} [values] the placeholders' values
 * @returns {string} the text; the key itself when the catalog lacks it
 */
export function t(key, values = {}) {
  const template = texts[key];
  return template === undefined ? key : render(template, values);
}

/**
 * A plural text: the form of `n` by the language's plural rules (`<key>.one`, `.few`,
 * `.many`, `.other`); `n` is a placeholder of every form, formatted as a number.
 *
 * @param {string} key the key without the form
 * @param {number} n the count
 * @param {Record<string, unknown>} [values] other placeholders
 * @returns {string}
 */
export function tn(key, n, values = {}) {
  const form = Number.isInteger(n) ? plurals.select(n) : "other";
  const chosen = texts[`${key}.${form}`] !== undefined ? `${key}.${form}` : `${key}.other`;
  return t(chosen, { ...values, n: fmt(n, Number.isInteger(n) ? 0 : 1) });
}

/** Whether the catalog has a key (for optional texts). */
export function has(key) {
  return texts[key] !== undefined;
}

/**
 * A number in the page's language ("1 234,5" in Polish), or "–" when missing.
 *
 * @param {number|null|undefined} value
 * @param {number} [digits] fraction digits (fixed)
 * @returns {string}
 */
export function fmt(value, digits = 0) {
  if (value === null || value === undefined || !Number.isFinite(value)) return "–";
  let format = numbers.get(digits);
  if (!format) {
    format = new Intl.NumberFormat(current === "pl" ? "pl-PL" : "en-GB", {
      minimumFractionDigits: digits,
      maximumFractionDigits: digits,
    });
    numbers.set(digits, format);
  }
  return format.format(value);
}

/**
 * A date "YYYY-MM-DD" as the language writes it: "12.11.2026" or "12/11/2026".
 *
 * @param {string|null|undefined} iso
 * @returns {string}
 */
export function fmtDate(iso) {
  if (!iso) return "–";
  const day = iso.slice(8, 10);
  const month = iso.slice(5, 7);
  const year = iso.slice(0, 4);
  return current === "pl" ? `${day}.${month}.${year}` : `${day}/${month}/${year}`;
}

/**
 * A UTC time of the API ("2026-11-13T12:20:00Z") in the reader's time zone, "HH:MM".
 *
 * @param {string|null|undefined} iso
 * @returns {string}
 */
export function fmtTime(iso) {
  if (!iso) return "–";
  const when = new Date(iso);
  if (Number.isNaN(when.getTime())) return iso;
  return new Intl.DateTimeFormat(current === "pl" ? "pl-PL" : "en-GB", {
    hour: "2-digit",
    minute: "2-digit",
  }).format(when);
}

/**
 * A UTC time of the API as a date and time in the reader's time zone.
 *
 * @param {string|null|undefined} iso
 * @returns {string}
 */
export function fmtDateTime(iso) {
  if (!iso) return "–";
  const when = new Date(iso);
  if (Number.isNaN(when.getTime())) return iso;
  return new Intl.DateTimeFormat(current === "pl" ? "pl-PL" : "en-GB", {
    dateStyle: "short",
    timeStyle: "short",
  }).format(when);
}
