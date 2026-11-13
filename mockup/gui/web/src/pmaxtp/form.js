// The left panel of the view „PMAXTP” (plan D12): the method and the point, typed or picked
// on the map, the box `fetch_pmaxtp` accepts, and the examples and the methods'
// description of the old page (src/obserwator/web/templates/download/pmaxtp.html).

import { fmt, html, useEffect, useState } from "../lib.js";
import { Seg } from "../ui/seg.js";
import { METHODS, PMAXTP_BOUNDS, outside, round4 } from "./state.js";

/** The examples of the old page. */
const PLACES = [
  ["Warszawa", 52.2297, 21.0122],
  ["Kraków", 50.0647, 19.945],
  ["Gdańsk", 54.352, 18.6466],
  ["Wrocław", 51.1079, 17.0385],
  ["Poznań", 52.4064, 16.9252],
];

/** A coordinate typed with a decimal comma or dot. */
function parse(text) {
  const value = Number.parseFloat(String(text).trim().replace(",", "."));
  return Number.isFinite(value) ? round4(value) : Number.NaN;
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
  const [lat, setLat] = useState(point ? point.lat.toFixed(4) : "");
  const [lon, setLon] = useState(point ? point.lon.toFixed(4) : "");
  const [error, setError] = useState(null);
  // A point picked on the map fills the fields
  useEffect(() => {
    if (!point) return;
    setLat(point.lat.toFixed(4));
    setLon(point.lon.toFixed(4));
    setError(null);
  }, [point && point.lat, point && point.lon]);
  const submit = (event) => {
    event.preventDefault();
    const typed = { lat: parse(lat), lon: parse(lon) };
    const why = outside(typed);
    setError(why);
    if (!why) onPoint(typed, { fly: true });
  };
  const { lat: latBox, lon: lonBox } = PMAXTP_BOUNDS;
  return html`<form class="pmaxtp-form" onSubmit=${submit}>
    <p class="hint-box">Kliknij punkt na mapie albo wpisz jego współrzędne: panel po prawej pokaże opady maksymalne prawdopodobne PMAXTP IMGW-PIB dla tego miejsca.</p>
    <div class="pm-row">
      <span class="pm-label" aria-hidden="true">Metoda</span>
      <${Seg} items=${METHODS} value=${method} onChange=${onMethod} label="Metoda PMAXTP" />
    </div>
    <div class="pm-coords">
      <label>
        <span class="pm-label">Szerokość [° N]</span>
        <input type="text" inputmode="decimal" autocomplete="off" value=${lat} placeholder="np. 50,0647" onInput=${(event) => setLat(event.currentTarget.value)} />
      </label>
      <label>
        <span class="pm-label">Długość [° E]</span>
        <input type="text" inputmode="decimal" autocomplete="off" value=${lon} placeholder="np. 19,9450" onInput=${(event) => setLon(event.currentTarget.value)} />
      </label>
    </div>
    <p class="note">Zakres: ${fmt(latBox[0])}–${fmt(latBox[1])}° N, ${fmt(lonBox[0])}–${fmt(lonBox[1], 1)}° E (granice <code>fetch_pmaxtp</code>); IMGW-PIB odpowiada dla punktów swojej siatki w Polsce. Punkt jest zaokrąglany do 4 miejsc po przecinku, jak w adresie API IMGW-PIB.</p>
    ${error ? html`<p class="ana-error" role="alert">${error}</p>` : null}
    <div class="btn-row"><button type="submit" class="btn primary sm">Pokaż wyniki</button></div>
    <h3 class="group-title">Przykładowe miejsca</h3>
    <div class="chips">
      ${PLACES.map(
        ([name, placeLat, placeLon]) => html`<button type="button" class="chip" onClick=${() => onPoint({ lat: placeLat, lon: placeLon }, { fly: true })}>${name}</button>`,
      )}
    </div>
    <h3 class="group-title">Metody</h3>
    <details class="pm-method">
      <summary>POT – Peak Over Threshold</summary>
      <p>Metoda wartości szczytowych powyżej progu: wszystkie zdarzenia opadowe przekraczające próg, niezależnie od roku wystąpienia. Zalecana do analiz częstości zdarzeń ekstremalnych.</p>
    </details>
    <details class="pm-method">
      <summary>AMP – Annual Max Precipitation</summary>
      <p>Metoda rocznych wartości maksymalnych: tylko największy opad każdego roku serii pomiarowej. Stosowana w tradycyjnych analizach hydrologicznych.</p>
    </details>
  </form>`;
}
