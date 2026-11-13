// „Pobierz” (plan D14): each series of the station as Obserwator's CSV (`export_series`,
// api/export) or as one columnar JSON document, with the provider's attribution and licence
// and the equivalent command line (`format_command` of `series export`, api/export/info); for
// a hydrological station the hand-off of Q or H to Hydrolog (D13).

import { copyText } from "../../nogat/nogat-handoff.js";
import { api } from "../api.js";
import { html, useEffect, useRef, useState } from "../lib.js";
import { datasetTitle } from "../words.js";
import { Section } from "./common.js";
import { HandoffButtons } from "./handoff.js";

function exportAddress(code, dataset, format) {
  return `api/export?${new URLSearchParams({ station: code, dataset, format })}`;
}

/** A command line with „Kopiuj” (also the PMAXTP view's, pmaxtp/result.js). */
export function Command({ line }) {
  const field = useRef(null);
  const [said, setSaid] = useState(null);
  const copy = async () => {
    try {
      setSaid((await copyText(line, field.current)) === "field" ? "Zaznaczono: naciśnij Ctrl+C." : "Skopiowano.");
    } catch {
      setSaid("Przeglądarka nie pozwoliła skopiować.");
    }
  };
  return html`<div class="cli">
    <div class="cli-head">
      <span class="label">To samo z wiersza poleceń</span>
      ${said ? html`<span class="muted small" role="status">${said}</span>` : null}
      <button type="button" class="btn sm ghost" onClick=${copy}>Kopiuj</button>
    </div>
    <pre class="code">${line}</pre>
    <textarea ref=${field} hidden aria-label="Polecenie do skopiowania" rows="2"></textarea>
  </div>`;
}

function Licence({ licence }) {
  return html`<div class="licence">
    <p><strong>${licence.attribution}</strong>. ${licence.processed}.</p>
    <p class="muted">
      ${licence.notice}
      ${" "}<a href=${licence.url} target="_blank" rel="noopener noreferrer">Warunki ${licence.licence === "CC-BY-4.0" ? "licencji CC BY 4.0" : licence.provider}</a>
      ${licence.terms_url ? html`${" · "}<a href=${licence.terms_url} target="_blank" rel="noopener noreferrer">wyłączenie odpowiedzialności</a>` : null}
    </p>
  </div>`;
}

function DatasetFiles({ code, entry }) {
  const [state, setState] = useState({ info: null, error: null });
  useEffect(() => {
    let live = true;
    api.get("api/export/info", { station: code, dataset: entry.dataset }).then(
      (info) => live && setState({ info, error: null }),
      (error) => live && setState({ info: null, error }),
    );
    return () => {
      live = false;
    };
  }, [code, entry.dataset]);
  const info = state.info;
  return html`<${Section}
    title=${datasetTitle(entry.dataset)}
    info="CSV to plik polecenia obserwator series export: UTF-8, przecinek, kropka dziesiętna, wartości z flagami, atrybucja dostawcy w pierwszym wierszu danych. JSON to cały szereg w kolumnach z jednostkami, wersją szeregu i atrybucją (układ z planu GUI, D14)."
    state=${{ data: null, error: state.error, loading: !info && !state.error }}
  >
    ${info
      ? html`<div class="btn-row files">
            <a class="btn sm" href=${exportAddress(code, entry.dataset, "csv")} download=${info.files.csv}><span class="fmt">CSV</span>${info.files.csv}</a>
            <a class="btn sm" href=${exportAddress(code, entry.dataset, "json")} download=${info.files.json}><span class="fmt">JSON</span>${info.files.json}</a>
          </div>
          <${Command} line=${info.command} />
          <p class="note">Bez <code>--root</code> polecenie czyta domyślny magazyn Obserwatora; makieta eksportuje wersję szeregu ${entry.version}.</p>
          <${Licence} licence=${info.licence} />`
      : null}
  </${Section}>`;
}

function Pobierz({ station }) {
  if (!station.datasets.length) {
    return html`<p class="note-box">Magazyn nie ma szeregów tej stacji: nie ma czego pobrać. Dane katalogowe są w sekcji „Informacje o stacji”.</p>`;
  }
  const hydro = station.properties.kind === "hydro";
  const has = (variable) =>
    station.datasets.some((entry) => Object.keys(entry.variables).some((name) => name === variable || name.startsWith(`${variable}_max@`)));
  const variables = ["Q", "H"].filter(has);
  const daily = station.datasets.some((entry) => entry.dataset.endsWith(".hydro_daily"));
  return html`
    ${station.datasets.map((entry) => html`<${DatasetFiles} key=${entry.dataset} code=${station.code} entry=${entry} />`)}
    ${hydro && variables.length
      ? html`<${Section}
          title="Przekazanie do Hydrologa"
          info="Dokument nogat-handoff/1 z szeregiem hydrolog-series/1, który Hydrolog otwiera w „Statystyce przepływów”: wartości dobowe (dzień bez wartości jako null), a gdy magazyn ma tylko charakterystyki półroczne IMGW-PIB — maksima roczne, większe z maksimów zimy i lata (rok bez jednego z nich pominięty i wymieniony w pochodzeniu)."
        >
          <p class="note">${daily ? "Szereg dobowy" : "Maksima roczne z charakterystyk półrocznych (szeregu dobowego jeszcze nie ma w magazynie)"} — cały okres.</p>
          ${variables.map(
            (variable) => html`<div class="handoff-var">
              <h4>${variable === "Q" ? "Przepływ Q" : "Stan wody H"}</h4>
              <${HandoffButtons} code=${station.code} variable=${variable} />
            </div>`,
          )}
        </${Section}>`
      : null}
  `;
}

/** The section „Pobierz”. */
export const POBIERZ = { id: "pobierz", title: "Pobierz", component: Pobierz };
