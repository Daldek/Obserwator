// „Stany charakterystyczne” (Nogat plan H1, H2, H3): first degree per year and half-year,
// second degree by Hydrolog's `stats characteristic`, ČHMÚ thresholds where the catalog has
// them, the characteristic levels of every station and days beyond them. IMGW-PIB's warning
// and alarm levels are operational data, not archived (plan question 3), so they are not here.

import { Chart, fmt, html, unit, useMemo } from "../../lib.js";
import { Section, Seg, Table, useAnalysis } from "../common.js";
import { Block, Handoff, Notices, Option, VARIABLES, VariableSeg, Years, date, digitsOf, fmtV, useOptions, withUnit } from "./util.js";

const INFO = `Wartości charakterystyczne I stopnia to najmniejsza, średnia i największa wartość roku hydrologicznego (XI–X) i jego półroczy (XI–IV, V–X): NW, SW, WW dla stanów, NQ, SQ, WQ dla przepływów. Źródło „auto” bierze opublikowane przez IMGW-PIB charakterystyki półroczne (maksimum roczne to większe z półrocznych; mogą to być wartości chwilowe), a lata bez nich liczy z szeregu dobowego (prototyp, docelowo Hydrolog H1). Wartości II stopnia (WWQ…NNQ, WWW…NNW) liczy Hydrolog („stats characteristic”) z szeregu dobowego wybranych lat: największa (W), średnia (S), mediana (Z) i najmniejsza (N) z rocznych maksimów, średnich i minimów (metodyka IMGW-PIB); obok, mniejszą czcionką, te same wartości z półroczy IMGW-PIB do porównania (prototyp H2). Domyślnie wszystkie lata zapisu stacji. Progi: dla stacji ČHMÚ progi z katalogu stacji (SPA 1–3, sucho, Q50), dla każdej stacji stany (przepływy) charakterystyczne SWW, SSW i SNW (SWQ, SSQ, SNQ) wybranych lat liczone przez Hydrologa. Dni powyżej progu: wartość dobowa równa progowi lub wyższa (dla progu suszy i SNW/SNQ: niższa od progu); ciąg kończy dzień poniżej progu albo brak danych (prototyp H3).`;

const ROWS = [
  ["najw. (W)", 0, 4, 8],
  ["średnia (S)", 1, 5, 9],
  ["mediana (Z)", 2, 6, 10],
  ["najmn. (N)", 3, 7, 11],
];

const FIRST_NAMES = {
  H: ["NW", "SW", "WW"],
  Q: ["NQ", "SQ", "WQ"],
  T: ["min. T", "śr. T", "maks. T"],
};

function Matrix({ entry, variable }) {
  const names = entry.names;
  const cell = (at) => html`<td>
    <span class="hy-name">${names[at]}</span>
    <strong>${fmtV(entry.hydrolog[names[at]], variable)}</strong>
    ${entry.imgw && html`<small class="hy-alt" title="Z półroczy IMGW-PIB (prototyp)">${fmtV(entry.imgw[names[at]], variable)}</small>`}
  </td>`;
  return html`<div class="table-wrap"><table class="tbl hy-matrix">
    <thead><tr><th scope="col"></th><th scope="col" title="z maksimów rocznych">z maksimów</th><th scope="col" title="ze średnich rocznych">ze średnich</th><th scope="col" title="z minimów rocznych">z minimów</th></tr></thead>
    <tbody>${ROWS.map(([label, a, b, c]) => html`<tr><th scope="row">${label}</th>${cell(a)}${cell(b)}${cell(c)}</tr>`)}</tbody>
  </table></div>`;
}

function FirstDegree({ rows, variable, period, unitText }) {
  const [low, mean, high] = FIRST_NAMES[variable];
  const columns = [
    { key: "year", label: "Rok", format: (v) => String(v) },
    { key: "min", label: low, format: (v) => fmtV(v, variable) },
    { key: "min_date", label: "data", format: (v) => (v ? date(v) : "–") },
    { key: "mean", label: mean, format: (v) => fmtV(v, variable) },
    { key: "max", label: high, format: (v) => fmtV(v, variable) },
    { key: "max_date", label: "data", format: (v) => (v ? date(v) : "–") },
    { key: "source", label: "źródło", format: (v, row) => (v === "imgw" ? "IMGW-PIB" : row.missing ? `dobowe, brak ${row.missing} d` : "dobowe") },
  ];
  const shown = rows
    .map((row) => ({ year: row.year, source: row.source, ...row[period] }))
    .reverse();
  const series = [
    ["max", high, "s2"],
    ["mean", mean, "s1"],
    ["min", low, "s3"],
  ].map(([key, label, cls]) => ({
    id: key,
    kind: "line",
    cls,
    label,
    data: rows.map((row) => [row.year, row[period][key] ?? null]),
  }));
  const spec = useMemo(
    () => ({
      x: { label: "rok hydrologiczny", digits: 0 },
      y: { label: `${variable} [${unitText}]`, unit: unitText, scale: variable === "Q" ? "log" : "linear", zero: variable === "Q", digits: digitsOf(variable) },
      series,
      legend: true,
      readout: { x: (x) => `rok ${Math.round(x)}` },
      fit: { ratio: 0.5, minHeight: 190 },
      title: `Wartości I stopnia ${variable} w latach`,
    }),
    [rows, variable, period],
  );
  return html`<${Chart} spec=${spec} />
    <${Table} columns=${columns} rows=${shown} max=${12} />`;
}

const LEVEL_CLASS = { spa1: "hy-lv-1", spa2: "hy-lv-2", spa3: "hy-lv-3", q50: "hy-lv-4", drought: "hy-lv-dry", swx: "hy-lv-c", ssx: "hy-lv-c", snx: "hy-lv-c" };

function Levels({ state, code, variables, choice, setChoice }) {
  const data = state.data;
  const usable = variables.filter((v) => v === "H" || v === "Q");
  const levelId = data && (data.levels.find((l) => l.id === choice.level) ? choice.level : data.levels[0]?.id);
  const level = data && data.levels.find((l) => l.id === levelId);
  const chart = useMemo(() => {
    if (!data) return null;
    const u = unit(data.unit);
    return {
      x: { scale: "date" },
      y: { label: `${data.var} [${u}]`, unit: u, zero: false, digits: digitsOf(data.var) },
      series: [{ id: "v", kind: "line", cls: "s1", label: data.var === "H" ? "stan dobowy" : "przepływ dobowy", data: data.line, width: 1 }],
      marks: data.levels.map((l) => ({ kind: "hline", y: l.value, label: l.short, cls: LEVEL_CLASS[l.id] })),
      readout: true,
      fit: { ratio: 0.55, minHeight: 210 },
      title: `${data.var} dobowe z progami`,
    };
  }, [data]);
  const yearly = useMemo(() => {
    if (!data || !level) return null;
    return {
      x: { label: "rok hydrologiczny", digits: 0 },
      y: { label: "dni", unit: "d", digits: 0 },
      series: [{ id: "d", kind: "bars", cls: level.above ? "s2" : "s3", label: `dni ${level.above ? "≥" : "<"} ${fmtV(level.value, data.var)} ${unit(data.unit)}`, align: "center", data: data.year_list.map((year, at) => [year, data.per_year[level.id][at]]) }],
      readout: { x: (x) => `rok ${Math.round(x)}` },
      fit: { ratio: 0.42, minHeight: 160 },
      title: "Dni powyżej progu w latach",
    };
  }, [data, levelId]);
  return html`<${Block} state=${state} title="Progi i dni powyżej (H3)">
    ${usable.length > 1 && html`<${Option} label="Zmienna"><${VariableSeg} value=${data ? data.var : choice.lv} variables=${usable} onChange=${(v) => setChoice({ lv: v, level: undefined })} /></${Option}>`}
    ${data && html`<ul class="hy-levels">${data.levels.map(
      (l) => html`<li class=${LEVEL_CLASS[l.id]}><i aria-hidden="true"></i>${l.label}: <strong>${withUnit(l.value, data.var, data.unit)}</strong> <small>${l.source}</small></li>`,
    )}</ul>`}
    ${chart && html`<${Chart} spec=${chart} />`}
    ${data && html`<${Option} label="Próg"><${Seg} value=${levelId} label="Próg" options=${data.levels.map((l) => [l.id, l.short])} onChange=${(v) => setChoice({ level: v })} /></${Option}>`}
    ${yearly && html`<${Chart} spec=${yearly} />`}
    ${level && html`<${EventsTable} events=${data.events[level.id]} level=${level} variable=${data.var} />`}
    ${data && html`<${Notices} items=${data.notices} />`}
  </${Block}>`;
}

function EventsTable({ events, level, variable }) {
  const rows = [...events].sort((a, b) => (level.above ? b.peak - a.peak : a.peak - b.peak));
  const columns = [
    { key: "start", label: "od", format: date },
    { key: "end", label: "do", format: date },
    { key: "days", label: "dni", format: (v) => fmt(v, 0) },
    { key: "peak", label: level.above ? "kulminacja" : "minimum", format: (v) => fmtV(v, variable) },
    { key: "peak_date", label: "dnia", format: date },
  ];
  return html`<p class="muted hy-caption">${events.length} ${events.length === 1 ? "ciąg" : "ciągów"} ${level.above ? "na poziomie progu lub wyżej" : "poniżej progu"}, od najwyższej kulminacji${level.above ? "" : " (najniższego minimum)"}:</p>
    <${Table} columns=${columns} rows=${rows} max=${8} />`;
}

/** The section „Stany charakterystyczne”. */
export function Characteristic({ station }) {
  const code = station.code;
  const [opt, setOpt] = useOptions({ source: "auto", from: undefined, to: undefined, fv: undefined, sv: undefined, lv: undefined, period: "annual", level: undefined }, code);
  const main = useAnalysis("hydro_characteristic", code, { source: opt.source, from: opt.from, to: opt.to });
  const levels = useAnalysis("hydro_levels", code, { var: opt.lv, from: opt.from, to: opt.to });
  const data = main.data;
  const variables = data ? data.variables : [];
  const firstVar = data && (variables.includes(opt.fv) ? opt.fv : variables.includes("Q") ? "Q" : variables[0]);
  const second = data ? Object.keys(data.second_degree) : [];
  const secondVar = data && (second.includes(opt.sv) ? opt.sv : second.includes("Q") ? "Q" : second[0]);
  const entry = data && secondVar ? data.second_degree[secondVar] : null;
  const hydrolog = data && data.computed_by.find((p) => p.engine === "hydrolog");
  return html`<${Section} info=${INFO} state=${main}>
    ${data && html`
      <${Years} data=${data} onApply=${(from, to) => setOpt({ from, to })} />
      <h4 class="hy-sub">II stopnia (H2)</h4>
      ${second.length === 0 && html`<p class="hy-note">Stacja nie ma szeregu dobowego H ani Q: Hydrolog liczy wartości II stopnia z szeregu dobowego.</p>`}
      ${second.length > 1 && html`<${Option} label="Zmienna"><${VariableSeg} value=${secondVar} variables=${second} onChange=${(v) => setOpt({ sv: v })} /></${Option}>`}
      ${entry && html`
        <${Matrix} entry=${entry} variable=${secondVar} />
        <p class="muted hy-caption">Pogrubione: Hydrolog z szeregu dobowego ${entry.from}–${entry.to}: ${entry.period_years} lat${entry.missing.length ? `, bez danych: ${entry.missing.join(", ")}` : ""}${entry.incomplete.length ? `, niepełne (Hydrolog liczy je z dni z wartością): ${entry.incomplete.join(", ")}` : ""} [${unit(data.units[secondVar])}].
          ${entry.imgw ? ` Małe: z półroczy IMGW-PIB ${entry.imgw_from}–${entry.imgw_to} (${entry.imgw_years} lat, prototyp): maksimum roczne to większe z półrocznych, które mogą być chwilowe, więc bywa wyższe od dobowego.` : ""}</p>
        <${Handoff} code=${code} variable=${secondVar} resolution="daily" from=${entry.from} to=${entry.to} computed=${hydrolog} result=${entry.hydrolog} />`}
      <h4 class="hy-sub">I stopnia w latach (H1)</h4>
      <div class="hy-options">
        <${Option} label="Źródło"><${Seg} value=${opt.source} label="Źródło" options=${[["auto", "auto (F1)"], ["imgw", "półrocza IMGW-PIB"], ["daily", "szereg dobowy"]]} onChange=${(v) => setOpt({ source: v })} /></${Option}>
        <${Option} label="Okres"><${Seg} value=${opt.period} label="Okres" options=${[["annual", "rok"], ["winter", "XI–IV"], ["summer", "V–X"]]} onChange=${(v) => setOpt({ period: v })} /></${Option}>
        ${variables.length > 1 && html`<${Option} label="Zmienna"><${VariableSeg} value=${firstVar} variables=${variables} onChange=${(v) => setOpt({ fv: v })} /></${Option}>`}
      </div>
      ${firstVar && data.first_degree[firstVar].length
        ? html`<${FirstDegree} rows=${data.first_degree[firstVar]} variable=${firstVar} period=${opt.period} unitText=${unit(data.units[firstVar])} />`
        : html`<p class="hy-note">Brak wartości ${firstVar ? VARIABLES[firstVar] : ""} z wybranego źródła w tych latach.</p>`}
      <${Notices} items=${data.notices} />
    `}
    <${Levels} state=${levels} code=${code} variables=${variables} choice=${opt} setChoice=${setOpt} />
  </${Section}>`;
}
