// The left panel of the view „PMAXTP” (plan D12): the method and the point, typed or picked
// on the map, the box `fetch_pmaxtp` accepts, and the examples and the methods'
// description of the old Jinja page (download/pmaxtp.html, removed with the GUI's S8).

import { fmt, html, t, useEffect, useState } from "../lib.js";
import { Seg } from "../ui/seg.js";
import { METHODS, boundsLabel, methodName, outside, round4 } from "./state.js";

/** The examples of the old page: the catalog's name and the point. */
const PLACES = [
  ["pmaxtp.place.warsaw", 52.2297, 21.0122],
  ["pmaxtp.place.krakow", 50.0647, 19.945],
  ["pmaxtp.place.gdansk", 54.352, 18.6466],
  ["pmaxtp.place.wroclaw", 51.1079, 17.0385],
  ["pmaxtp.place.poznan", 52.4064, 16.9252],
];

/** The methods' descriptions of the old page. */
const DESCRIPTIONS = {
  POT: "pmaxtp.method.pot.text",
  AMP: "pmaxtp.method.amp.text",
};

/** A coordinate typed with a decimal comma or dot. */
function parse(text) {
  const value = Number.parseFloat(String(text).trim().replace(",", "."));
  return Number.isFinite(value) ? round4(value) : Number.NaN;
}

/** A coordinate as the field shows it: four decimals in the page's language. */
function shown(value) {
  return fmt(value, 4);
}

/**
 * The form.
 *
 * @param {{point: {lat: number, lon: number}|null, method: "POT"|"AMP",
 *   onPoint: (point: {lat: number, lon: number}, how: {fly: boolean}) => void,
 *   onMethod: (method: string) => void}} props
 * @returns {object}
 */
export function PmaxtpForm({ point, method, onPoint, onMethod }) {
  const [lat, setLat] = useState(point ? shown(point.lat) : "");
  const [lon, setLon] = useState(point ? shown(point.lon) : "");
  const [error, setError] = useState(null);
  // A point picked on the map fills the fields
  useEffect(() => {
    if (!point) return;
    setLat(shown(point.lat));
    setLon(shown(point.lon));
    setError(null);
  }, [point && point.lat, point && point.lon]);
  const submit = (event) => {
    event.preventDefault();
    const typed = { lat: parse(lat), lon: parse(lon) };
    const why = outside(typed);
    setError(why);
    if (!why) onPoint(typed, { fly: true });
  };
  const items = METHODS.map((value) => ({ value, label: value, title: methodName(value) }));
  return html`<form class="pmaxtp-form" onSubmit=${submit}>
    <p class="hint-box">${t("pmaxtp.form.hint")}</p>
    <div class="pm-row">
      <span class="pm-label" aria-hidden="true">${t("pmaxtp.form.method")}</span>
      <${Seg} items=${items} value=${method} onChange=${onMethod} label=${t("pmaxtp.form.method_label")} />
    </div>
    <div class="pm-coords">
      <label>
        <span class="pm-label">${t("pmaxtp.form.latitude")}</span>
        <input
          type="text"
          name="latitude"
          inputmode="decimal"
          autocomplete="off"
          value=${lat}
          placeholder=${t("pmaxtp.form.example", { value: shown(50.0647) })}
          aria-invalid=${error ? "true" : undefined}
          onInput=${(event) => setLat(event.currentTarget.value)}
        />
      </label>
      <label>
        <span class="pm-label">${t("pmaxtp.form.longitude")}</span>
        <input
          type="text"
          name="longitude"
          inputmode="decimal"
          autocomplete="off"
          value=${lon}
          placeholder=${t("pmaxtp.form.example", { value: shown(19.945) })}
          aria-invalid=${error ? "true" : undefined}
          onInput=${(event) => setLon(event.currentTarget.value)}
        />
      </label>
    </div>
    <p class="note">${t("pmaxtp.form.bounds", { bounds: boundsLabel(), function: "fetch_pmaxtp" })}</p>
    ${error ? html`<p class="ana-error" role="alert">${error}</p>` : null}
    <div class="btn-row"><button type="submit" class="btn primary sm">${t("pmaxtp.form.submit")}</button></div>
    <h3 class="group-title">${t("pmaxtp.form.places")}</h3>
    <div class="chips">
      ${PLACES.map(([key, placeLat, placeLon]) => {
        const on = Boolean(point) && point.lat === placeLat && point.lon === placeLon;
        return html`<button
          type="button"
          class=${on ? "chip on" : "chip"}
          aria-pressed=${String(on)}
          onClick=${() => onPoint({ lat: placeLat, lon: placeLon }, { fly: true })}
        >
          ${t(key)}
        </button>`;
      })}
    </div>
    <h3 class="group-title">${t("pmaxtp.form.methods")}</h3>
    ${METHODS.map(
      (value) => html`<details class="pm-method">
        <summary>${value} – ${methodName(value)}</summary>
        <p>${t(DESCRIPTIONS[value])}</p>
      </details>`,
    )}
  </form>`;
}
