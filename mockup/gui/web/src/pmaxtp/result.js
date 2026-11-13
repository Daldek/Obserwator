// The results of the view „PMAXTP” (plan D12): the tables of the old page
// (src/obserwator/web/templates/partials/pmaxtp_result.html) for every duration and
// probability IMGW-PIB gives: the quantiles (ks), the upper bounds of their confidence
// interval (sg) and the estimation errors (rb). Then the files, packed by the server from
// the API's answer for the point (api/pmaxtp/file: CSV and JSON with PMAXTP's own terms),
// the link to that answer at IMGW-PIB, which is the only address IMGW-PIB has for a point
// (klimat.imgw.pl/opady-maksymalne builds its own files in the browser), the command line
// that gives the same numbers, and PMAXTP's source line, processed mark and monograph.

import { fmt, html, useState } from "../lib.js";
import { Command } from "../sections/pobierz.js";
import { clock } from "../current.js";
import { Seg } from "../sections/common.js";
import { METHOD_NAMES, outside, pmaxtpQuery, pointLabel } from "./state.js";

const TABLES = [
  ["ks", "Kwantyle"],
  ["sg", "Górna granica"],
  ["rb", "Błąd estymacji"],
];
const TITLES = {
  ks: "Kwantyle opadu maksymalnego [mm]",
  sg: "Górne granice przedziału ufności kwantyli [mm]",
  rb: "Błędy estymacji kwantyli [mm]",
};

/** A probability key of IMGW-PIB ("0.01", "99.9") as shown. */
function probability(key) {
  return key.replace(".", ",");
}

function fileAddress(doc, format) {
  return `api/pmaxtp/file?${new URLSearchParams({ ...pmaxtpQuery({ lat: doc.latitude, lon: doc.longitude }, doc.method), format })}`;
}

function Terms({ doc }) {
  const terms = doc.terms;
  return html`<div class="licence">
    <p><strong>${terms.source}</strong>.</p>
    <p>${terms.processed}.</p>
    <p>Monografia projektu: <a href=${terms.monograph_url} target="_blank" rel="noopener noreferrer">${terms.monograph}</a>.</p>
    <p class="muted">
      ${doc.notice}
      ${" "}<a href=${terms.page} target="_blank" rel="noopener noreferrer">Regulamin udostępniania danych projektu PMAXTP</a>
    </p>
  </div>`;
}

/**
 * The results panel.
 *
 * @param {{point: {lat: number, lon: number}|null, method: string,
 *   state: {doc: object|null, error: Error|null, loading: boolean}}} props
 * @returns {object}
 */
export function PmaxtpResult({ point, method, state }) {
  const [table, setTable] = useState("ks");
  if (!point) {
    return html`<p class="hint-box">Kliknij punkt na mapie albo wpisz współrzędne po lewej: tu pojawią się tabele PMAXTP tego miejsca i pliki do pobrania. Mapa nie rysuje siatki PMAXTP.</p>`;
  }
  const why = outside(point);
  if (why) return html`<p class="ana-error">${why}</p>`;
  if (state.error) return html`<p class="ana-error">${state.error.message}</p>`;
  const doc = state.doc;
  if (!doc) return html`<p class="muted">Pobieram PMAXTP z IMGW-PIB dla ${pointLabel(point)} (${method})…</p>`;
  const rows = doc.data[table];
  return html`<div class=${`pmaxtp-result${state.loading ? " is-loading" : ""}`}>
    <table class="params compact">
      <tbody>
        <tr><th>Metoda</th><td>${doc.method} (${METHOD_NAMES[doc.method]})</td></tr>
        <tr><th>Punkt</th><td>${pointLabel({ lat: doc.latitude, lon: doc.longitude })}</td></tr>
        <tr><th>Odpowiedź IMGW-PIB</th><td>${clock(doc.fetched_at)}<span class="row-sub">w pamięci serwera do 24 h, niezapisywana</span></td></tr>
      </tbody>
    </table>
    <${Seg} label="Tabela PMAXTP" value=${table} options=${TABLES} onChange=${setTable} />
    <p class="note">${TITLES[table]}. Wiersze: czas trwania opadu t [min]; kolumny: prawdopodobieństwo przewyższenia p [%].</p>
    <div class="table-wrap pm-table-wrap">
      <table class="tbl pm-table">
        <thead>
          <tr>
            <th scope="col">t \\ p</th>
            ${doc.probabilities.map((key) => html`<th scope="col">${probability(key)}</th>`)}
          </tr>
        </thead>
        <tbody>
          ${doc.durations.map(
            (duration) => html`<tr>
              <th scope="row">${duration}</th>
              ${doc.probabilities.map((key) => html`<td>${fmt(rows[duration] ? rows[duration][key] : null, 2)}</td>`)}
            </tr>`,
          )}
        </tbody>
      </table>
    </div>
    <h3 class="group-title">Pobierz</h3>
    <div class="btn-row files">
      <a class="btn sm" href=${fileAddress(doc, "csv")} download=${doc.files.csv}><span class="fmt">CSV</span>${doc.files.csv}</a>
      <a class="btn sm" href=${fileAddress(doc, "json")} download=${doc.files.json}><span class="fmt">JSON</span>${doc.files.json}</a>
    </div>
    <p class="note">Pliki składa serwer z odpowiedzi API IMGW-PIB dla tego punktu: trzy tabele (ks, sg, rb) dla ${doc.durations.length} czasów trwania i ${doc.probabilities.length} prawdopodobieństw. CSV: UTF-8, przecinek, kropka dziesiętna, formuły PMAXTP w pierwszym wierszu danych; JSON: wynik <code>${doc.schema}</code> z jednostkami i formułami.</p>
    <p class="note">
      <a href=${doc.source_url} target="_blank" rel="noopener noreferrer">Odpowiedź API IMGW-PIB (JSON)</a> — ten punkt wprost z serwisu IMGW-PIB. IMGW-PIB nie publikuje plików PMAXTP pod adresem punktu: jego strona
      ${" "}<a href=${doc.terms.page} target="_blank" rel="noopener noreferrer">klimat.imgw.pl/opady-maksymalne</a> składa pliki w przeglądarce z tej samej odpowiedzi.
    </p>
    <${Command} line=${doc.command} />
    <${Terms} doc=${doc} />
  </div>`;
}
