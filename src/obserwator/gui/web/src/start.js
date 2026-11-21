// The start's requests made before the modules load (theme-init.js): the texts in the
// stored language, the session and the station layer, each under "<lang> <address>". The
// page would otherwise ask for them only after all its modules, one after another; i18n.js
// and api.js take each answer once, and ask again themselves when it is missing or failed.

/**
 * The early answer of an address in a language, taken once.
 *
 * @param {string} lang "pl" or "en"
 * @param {string} url the address relative to the page (`api/session`)
 * @returns {Promise<Response>|null} the request made at the start, else null
 */
export function takeStart(lang, url) {
  const started = window.obserwatorStart;
  const key = `${lang} ${url}`;
  if (!started || !(key in started)) return null;
  const response = started[key];
  delete started[key];
  return response;
}
