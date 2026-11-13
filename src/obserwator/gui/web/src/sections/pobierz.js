// „Pobierz” (GUI plan D14): every file the server offers for the station
// (api/downloads/{code}): each series in each format (`export_series`: CSV, JSON, Parquet)
// with the equivalent command line to copy and the provider's licence; the result of each
// analysis that applies to the station as its JSON document (`obserwator-analysis/1`,
// api/files/analysis); for a hydrological station the hand-off of Q or H to Hydrolog (D13).
// Every file and hand-off carries the provider's lines and terms (Nogat DEV §20), the
// same the panel draws under the card (part "series").

import { copyText } from "../../nogat/nogat-handoff.js";
import { api } from "../api.js";
import { html, t, tn, useEffect, useRef, useState } from "../lib.js";
import { datasetTitle } from "../words.js";
import { Section, Seg, Table } from "./common.js";
import { HandoffButtons } from "./handoff.js";

/** The names of the formats of a series file. */
const FORMATS = { csv: "CSV", json: "JSON", parquet: "Parquet" };
/** The daily hydrological datasets: the hand-off of daily values reads them. */
const HYDRO_DAILY = ["pl.imgw.hydro_daily", "cz.chmi.hydro_daily"];

/**
 * A command line with „Kopiuj” (also the PMAXTP view's, pmaxtp/result.js).
 *
 * @param {{line: string, label?: string}} props the line and what it is (by default „To
 *   samo z wiersza poleceń”)
 * @returns {object}
 */
export function Command({ line, label }) {
  const field = useRef(null);
  const [said, setSaid] = useState(null);
  useEffect(() => {
    setSaid(null);
    if (field.current) field.current.hidden = true;
  }, [line]);
  const copy = async () => {
    try {
      setSaid((await copyText(line, field.current)) === "field" ? t("station.files.selected") : t("station.files.copied"));
    } catch {
      setSaid(t("station.files.copy_failed"));
    }
  };
  return html`<div class="cli">
    <div class="cli-head">
      <span class="label">${label || t("station.files.cli")}</span>
      ${said ? html`<span class="muted small" role="status">${said}</span>` : null}
      <button type="button" class="btn sm ghost" onClick=${copy}>${t("station.files.copy")}</button>
    </div>
    <pre class="code">${line.split(/( +)/).map((part, index) => (index % 2 ? part : part ? html`<span class="arg">${part}</span>` : null))}</pre>
    <textarea ref=${field} hidden aria-label=${t("station.files.command_field")} rows="2"></textarea>
  </div>`;
}

/** The provider's terms or licence of a series, and ČHMÚ's disclaimer. */
function Licence({ licence }) {
  if (!licence || !licence.url) return null;
  const name = licence.id === licence.provider ? t("station.files.terms", { provider: licence.provider }) : t("station.files.licence", { licence: String(licence.id).replace(/-/g, " ") });
  return html`<p class="licence muted">
    <a href=${licence.url} target="_blank" rel="noopener noreferrer">${name}</a>
    ${licence.terms_url ? html`${" · "}<a href=${licence.terms_url} target="_blank" rel="noopener noreferrer">${t("station.files.disclaimer")}</a>` : null}
  </p>`;
}

/** One series of the station: its files, the command line of the format chosen, the licence. */
function SeriesFiles({ entry }) {
  const formats = Object.keys(entry.formats);
  const [chosen, setChosen] = useState(formats[0]);
  const format = entry.formats[chosen] || entry.formats[formats[0]];
  return html`<${Section} title=${datasetTitle(entry.dataset)} info=${t("station.files.info")}>
    <div class="btn-row files">
      ${formats.map(
        (key) => html`<a class="btn sm" href=${entry.formats[key].url} download=${entry.formats[key].file}>
          <span class="fmt">${FORMATS[key] || key}</span>${entry.formats[key].file}
        </a>`,
      )}
    </div>
    ${formats.length > 1
      ? html`<${Seg} label=${t("station.files.command_format")} value=${chosen} onChange=${setChosen} options=${formats.map((key) => [key, FORMATS[key] || key])} />`
      : null}
    <${Command} line=${format.command} />
    <p class="note">${t("station.files.version_note", { version: entry.version })}</p>
    <${Licence} licence=${entry.licence} />
  </${Section}>`;
}

/** The JSON document of each analysis that applies to the station. */
function ResultFiles({ code, analyses }) {
  const rows = (analyses || []).map((item) => ({ id: item.analysis, title: item.title || null, command: item.command, stored: item.stored }));
  return html`<${Section} title=${t("station.files.results")} info=${t("station.files.results_info")}>
    ${analyses === null ? html`<p class="muted" role="status">${t("station.analyses_loading")}</p>` : null}
    ${analyses && !rows.length ? html`<p class="muted">${t("station.files.results_none")}</p>` : null}
    ${rows.length
      ? html`<p class="note">${tn("station.files.results_count", rows.length)}</p>
          <${Table}
            max=${8}
            columns=${[
              {
                key: "id",
                label: t("station.files.analysis"),
                format: (id, row) => html`<code>${id}</code><span class="cell-sub">${row.title ? `${row.title} · ` : ""}hydrolog ${row.command} · ${row.stored ? t("station.files.stored") : t("station.files.on_request")}</span>`,
              },
              { key: "file", label: t("station.files.file"), format: (_, row) => html`<a href=${api.analysisFileUrl(code, row.id)} download=${`${code}_${row.id}.json`}>JSON</a>` },
            ]}
            rows=${rows}
          />`
      : null}
  </${Section}>`;
}

/** „Przekazanie do Hydrologa”: daily Q and H, else the annual maxima of the flood frequency. */
function Handoff({ station, session, analyses }) {
  const daily = station.datasets.find((entry) => HYDRO_DAILY.includes(entry.dataset));
  const ids = new Set((analyses || []).map((item) => item.analysis));
  const variables = daily ? ["Q", "H"].filter((name) => daily.variables[name]) : ids.has("flood_frequency.Q") ? ["Q"] : [];
  if (!variables.length) return null;
  return html`<${Section} title=${t("station.files.handoff")} info=${t("station.files.handoff_info")}>
    <p class="note">${daily ? t("station.files.handoff_daily") : t("station.files.handoff_annual")}</p>
    ${variables.map(
      (variable) => html`<div class="handoff-var" key=${variable}>
        <h4>${variable === "Q" ? t("station.now.discharge") : t("station.now.water_level")}</h4>
        <${HandoffButtons}
          code=${station.code}
          session=${session}
          variable=${variable}
          resolution=${daily ? "daily" : "annual"}
          analysis=${daily ? undefined : "flood_frequency.Q"}
        />
      </div>`,
    )}
  </${Section}>`;
}

function Pobierz({ station, session, analyses }) {
  const [state, setState] = useState({ doc: null, error: null });
  const has = station.datasets.length > 0;
  useEffect(() => {
    if (!has) return undefined;
    let live = true;
    api.downloads(station.code).then(
      (doc) => live && setState({ doc, error: null }),
      (error) => live && setState({ doc: null, error }),
    );
    return () => {
      live = false;
    };
  }, [station.code]);
  if (!has) return html`<p class="note-box">${t("station.files.none")}</p>`;
  const doc = state.doc;
  return html`
    ${state.error ? html`<p class="ana-error" role="alert">${state.error.message}</p>` : null}
    ${!doc && !state.error ? html`<p class="muted" role="status">${t("station.files.loading")}</p>` : null}
    ${doc ? doc.series.map((entry) => html`<${SeriesFiles} key=${entry.dataset} entry=${entry} />`) : null}
    <${ResultFiles} code=${station.code} analyses=${analyses} />
    ${station.properties.kind === "hydro" ? html`<${Handoff} station=${station} session=${session} analyses=${analyses} />` : null}
  `;
}

/** The section „Pobierz”. */
export const POBIERZ = { id: "pobierz", title: "station.pobierz.title", component: Pobierz, part: "series" };
