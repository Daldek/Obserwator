// „Susze i okresy bezopadowe” (Nogat plan M6, M8): dry and wet spells with the threshold the
// person chooses (`spells.dry`, `spells.wet`), the SPI of 1, 3, 6 and 12 months and the
// relative precipitation of months and years with their classes (`spi`). Every number is a
// field of Hydrolog's result; the page picks, sorts for display, formats and draws (the
// colour of an SPI bar follows McKee's fixed limits).

import { Chart, dayNumber, fmt, html, lang, t, tn, useEffect, useMemo, useState } from "../../lib.js";
import { Figures, Notices, Section, Seg, Table } from "../common.js";
import {
  ClassLegend,
  Option,
  Periods,
  ROMAN,
  classCls,
  dateRange,
  daysText,
  listOf,
  mmLimit,
  monthText,
  newestFirst,
  num,
  takes,
  useMeteo,
  useOptions,
  yearAxis,
  yearAxisLabel,
  yearReadout,
} from "./util.js";

/** The classes of relative precipitation as Hydrolog names them, driest first. */
const RELATIVE = ["extremely_dry", "very_dry", "dry", "normal", "wet", "very_wet", "extremely_wet"];
/** McKee's classes of the SPI, driest first. */
const SPI_CLASSES = ["extremely_dry", "severely_dry", "moderately_dry", "near_normal", "moderately_wet", "very_wet", "extremely_wet"];

/** McKee et al. (1993): the class of an SPI value (0 = extremely dry … 6 = extremely wet). */
function spiClass(value) {
  if (value === null || value === undefined) return null;
  if (value <= -2) return 0;
  if (value <= -1.5) return 1;
  if (value <= -1) return 2;
  if (value < 1) return 3;
  if (value < 1.5) return 4;
  if (value < 2) return 5;
  return 6;
}

/** The first day of a month of a result as a day number (November and December of a
 * hydrological year are in the calendar year before). */
function monthStart(row, yearType) {
  const year = yearType === "hydrological" && row.month >= 11 ? row.year - 1 : row.year;
  return dayNumber(`${String(year).padStart(4, "0")}-${String(row.month).padStart(2, "0")}-01`);
}

// --- dry and wet spells ------------------------------------------------------------------

/** The threshold of the spells: 0,1 or 1 mm at a click, or any the person types. */
function ThresholdChoice({ value, onChange }) {
  const [text, setText] = useState(String(value));
  useEffect(() => setText(String(value)), [value]);
  const number = Number(String(text).replace(",", "."));
  const bad = !(number > 0) || number > 500;
  return html`<div class="me-threshold">
    <${Seg}
      value=${String(value)}
      label=${t("meteo.susze.spells.threshold_label")}
      options=${[
        ["0.1", `${mmLimit(0.1)} mm`],
        ["1", "1 mm"],
      ]}
      onChange=${(v) => onChange(+v)}
    />
    <form class="years" onSubmit=${(e) => (e.preventDefault(), !bad && onChange(number))}>
      <label class="me-number">
        <input type="number" min="0.1" max="500" step="0.1" inputmode="decimal" aria-label=${t("meteo.susze.spells.threshold_input")} value=${text} onInput=${(e) => setText(e.target.value)} />
        <span>mm</span>
      </label>
      <button type="submit" disabled=${bad || number === value}>${t("sections.recompute")}</button>
    </form>
  </div>`;
}

function SpellsBody({ r, recordLast }) {
  const p = r.period;
  const dry = r.kind === "dry";
  const what = `P ${dry ? "<" : "≥"} ${mmLimit(r.threshold_mm)} mm`;
  const bars = dry ? "me-bar-dry" : "bar-pe";
  const spells = r.spells || [];
  const sign = (s) => (s.open_start || s.open_end ? "≥ " : "");
  const record = spells.find((s) => s.duration_days === r.max_duration_days) || null;
  const last = spells[spells.length - 1];
  const ongoing = last && last.open_end && last.end_date === recordLast ? last : null;
  const longest = [...spells].sort((a, b) => b.duration_days - a.duration_days || a.start_date.localeCompare(b.start_date)).slice(0, 10);
  const listed = r.min_duration_days > 1;
  const spec = useMemo(
    () => ({
      x: yearAxis(r.years, yearAxisLabel(r.year_type)),
      y: { label: t("meteo.susze.spells.axis"), unit: t("meteo.common.days_unit") },
      series: [
        {
          id: "longest",
          kind: "bars",
          cls: bars,
          label: t("meteo.susze.spells.series"),
          align: "center",
          data: r.years.map((row) => [row.year, row.complete ? row.max_duration_days : null]),
        },
      ],
      marks:
        p.mean_max_duration_days === null || p.mean_max_duration_days === undefined
          ? []
          : [{ kind: "hline", y: p.mean_max_duration_days, label: t("meteo.common.mean_value", { value: daysText(p.mean_max_duration_days, 1) }) }],
      readout: { x: yearReadout, value: (v) => daysText(v, 0) },
      fit: { ratio: 0.45, minHeight: 170 },
      title: t("meteo.susze.spells.chart"),
    }),
    [r, lang()],
  );
  const classSpec = useMemo(() => {
    const labels = p.classes.map((c) => (c.max_days === null ? `≥ ${c.min_days}` : c.min_days === c.max_days ? String(c.min_days) : `${c.min_days}–${c.max_days}`));
    return {
      x: { label: t("meteo.susze.spells.classes_axis"), tickList: labels.map((label, at) => ({ value: at + 1, label })), min: 0.5, max: labels.length + 0.5 },
      y: { label: t("meteo.susze.spells.per_year"), unit: "" },
      series: [{ id: "classes", kind: "bars", cls: bars, label: t("meteo.susze.spells.per_year"), align: "center", data: p.classes.map((c, at) => [at + 1, c.per_year]) }],
      readout: { x: (x) => `${labels[Math.round(x) - 1] || ""} ${t("meteo.common.days_unit")}`, value: (v) => fmt(v, 2) },
      fit: { ratio: 0.4, minHeight: 160 },
      title: t("meteo.susze.spells.classes_chart"),
    };
  }, [r, lang()]);
  return html`<${Figures}
      items=${[
        { label: t("meteo.susze.spells.mean_longest"), value: daysText(p.mean_max_duration_days, 1), note: `${tn("meteo.common.complete_years", p.n_years)}, ${what}` },
        {
          label: t("meteo.susze.spells.record"),
          value: r.max_duration_days === null ? "–" : `${record ? sign(record) : ""}${daysText(r.max_duration_days, 0)}`,
          note: record ? dateRange(record.start_date, record.end_date) : "",
        },
        {
          label: t("meteo.susze.spells.counts"),
          value: `${num(p.mean_spells_10_days, 1)} · ${num(p.mean_spells_15_days, 1)} · ${num(p.mean_spells_20_days, 1)}`,
          note: t("meteo.susze.spells.counts_note"),
        },
        { label: t("meteo.susze.spells.number"), value: num(p.mean_n_spells, 1), note: t("meteo.susze.spells.number_note", { n: fmt(r.n_spells, 0) }) },
        ongoing
          ? { label: t("meteo.susze.spells.ongoing"), value: `${sign(ongoing)}${daysText(ongoing.duration_days, 0)}`, note: t("meteo.susze.spells.since", { start: dateRange(ongoing.start_date), end: dateRange(ongoing.end_date) }) }
          : { label: t("meteo.susze.spells.ongoing"), value: listed ? t("meteo.susze.spells.none_long", { n: r.min_duration_days }) : t("meteo.susze.spells.none") },
      ]}
    />
    <${Chart} spec=${spec} />
    <${Chart} spec=${classSpec} />
    <h4 class="me-sub">${listed ? t("meteo.susze.spells.longest_listed", { n: r.min_duration_days }) : t("meteo.susze.spells.longest")}</h4>
    ${longest.length
      ? html`<${Table}
          columns=${[
            { key: "duration_days", label: t("meteo.susze.spells.days_col"), format: (v, s) => `${sign(s)}${v}` },
            { key: "start_date", label: t("meteo.susze.spells.dates_col"), format: (v, s) => dateRange(v, s.end_date) },
          ]}
          rows=${longest}
        />`
      : html`<p class="muted">${t("meteo.susze.spells.no_long", { n: r.min_duration_days })}</p>`}
    <h4 class="me-sub">${t("meteo.common.years")}</h4>
    <${Table}
      columns=${[
        { key: "year", label: t("meteo.common.year"), format: (v) => String(v) },
        { key: "max_duration_days", label: t("meteo.susze.spells.longest_col"), format: (v) => num(v, 0) },
        { key: "max_start_date", label: t("meteo.susze.spells.dates_col"), format: (v, row) => dateRange(v, row.max_end_date) },
        { key: "spells_10_days", label: "≥ 10", format: (v) => num(v, 0) },
        { key: "spells_15_days", label: "≥ 15", format: (v) => num(v, 0) },
        { key: "spells_20_days", label: "≥ 20", format: (v) => num(v, 0) },
        { key: "n_spells", label: t("meteo.susze.spells.count_col"), format: (v) => num(v, 0) },
      ]}
      rows=${newestFirst(r.years)}
      max=${10}
    />`;
}

// --- the SPI -------------------------------------------------------------------------------

function SpiBody({ r, k, onScale }) {
  const scale = r.scales_months[k];
  const name = `SPI-${scale}`;
  const classNames = SPI_CLASSES.map((c) => t(`meteo.susze.spi_class.${c}`));
  const spec = useMemo(
    () => ({
      x: { scale: "date", label: t("meteo.common.month_axis") },
      y: { label: name, zero: true, min: -3.1, max: 3.1 },
      series: [
        {
          id: "spi",
          kind: "bars",
          label: name,
          width: 28,
          digits: 2,
          data: r.months.map((row) => ({ x: monthStart(row, r.year_type), y: row.spi[k], cls: row.spi[k] === null ? "" : `me-spi${spiClass(row.spi[k])}` })),
        },
      ],
      marks: [
        { kind: "hline", y: -1, label: "−1" },
        { kind: "hline", y: 1, label: "1" },
      ],
      readout: {
        x: (x) => {
          const d = new Date(x * 86400000);
          return monthText(d.getUTCFullYear(), d.getUTCMonth() + 1);
        },
      },
      fit: { ratio: 0.45, minHeight: 180 },
      title: name,
    }),
    [r, k, lang()],
  );
  let last = r.months.length - 1;
  while (last >= 0 && r.months[last].spi[k] === null) last -= 1;
  const at = last >= 0 ? r.months[last] : null;
  const fits = (r.period.scales.find((s) => s.scale_months === scale) || { fits: [] }).fits;
  return html`<${Option} label=${t("meteo.susze.spi.scale")}>
      <${Seg} value=${String(k)} label=${t("meteo.susze.spi.scale_label")} options=${r.scales_months.map((n, i) => [String(i), `SPI-${n}`])} onChange=${(v) => onScale(+v)} />
    </${Option}>
    <${Figures}
      items=${[
        { label: t("meteo.susze.spi.calibration"), value: `${r.reference_first_year}–${r.reference_last_year}`, note: t("meteo.susze.spi.gamma") },
        {
          label: t("meteo.susze.spi.last", { name }),
          value: at ? fmt(at.spi[k], 2) : "–",
          note: at ? `${monthText(at.year, at.month)} · ${classNames[spiClass(at.spi[k])]}` : "",
        },
      ]}
    />
    <${Chart} spec=${spec} />
    <${ClassLegend} names=${classNames} palette="spi" />
    <details class="me-details">
      <summary>${t("meteo.susze.spi.fits", { name })}</summary>
      <${Table}
        columns=${[
          { key: "month", label: t("meteo.common.month"), format: (v) => ROMAN[v - 1] },
          { key: "alpha", label: "α", format: (v) => num(v, 3) },
          { key: "beta", label: "β [mm]", format: (v) => num(v, 2) },
          { key: "zero_probability", label: "q", format: (v) => num(v, 3) },
          { key: "n_values", label: "n", format: (v) => num(v, 0) },
        ]}
        rows=${fits}
      />
    </details>`;
}

// --- relative precipitation and its classes ------------------------------------------------

function RelativeTable({ r, classes }) {
  const [all, setAll] = useState(false);
  const byMonth = new Map(r.months.map((row) => [`${row.year} ${row.month}`, row]));
  const order = r.year_type === "hydrological" ? [11, 12, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10] : [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12];
  const rows = newestFirst(r.years);
  const shown = all ? rows : rows.slice(0, 15);
  const cell = (row) => {
    if (!row || row.percent_of_normal === null) return html`<td>–</td>`;
    const index = RELATIVE.indexOf(row.precipitation_class);
    return html`<td class=${classCls("dw", index)} title=${index < 0 ? "" : classes[index]}>${fmt(row.percent_of_normal, 0)}</td>`;
  };
  return html`<div class="table-wrap"><table class="tbl me-heat">
      <thead><tr><th scope="col">${t("meteo.common.year")}</th>${order.map((m) => html`<th scope="col">${ROMAN[m - 1]}</th>`)}<th scope="col">${t("meteo.common.year")}</th></tr></thead>
      <tbody>${shown.map((year) => {
        const index = RELATIVE.indexOf(year.precipitation_class);
        return html`<tr>
          <th scope="row">${year.year}</th>
          ${order.map((m) => cell(byMonth.get(`${year.year} ${m}`)))}
          <td class=${`me-year ${classCls("dw", index)}`} title=${index < 0 ? "" : classes[index]}>${year.percent_of_normal === null ? "–" : fmt(year.percent_of_normal, 0)}</td>
        </tr>`;
      })}</tbody>
    </table>
    ${rows.length > 15 && !all ? html`<button type="button" class="link" onClick=${() => setAll(true)}>${t("sections.show_all", { count: rows.length })}</button>` : null}
    <${ClassLegend} names=${classes} palette="dw" />
  </div>`;
}

function RelativeBody({ r }) {
  const p = r.period;
  const classes = RELATIVE.map((c) => t(`meteo.susze.relative.class.${c}`));
  const name = (cls) => (cls ? classes[RELATIVE.indexOf(cls)] || cls : "");
  const lastYear = [...r.years].reverse().find((row) => row.percent_of_normal !== null);
  const lastMonth = [...r.months].reverse().find((row) => row.percent_of_normal !== null);
  return html`<${Figures}
      items=${[
        {
          label: t("meteo.common.normal", { from: r.reference_first_year, to: r.reference_last_year }),
          value: num(p.normal_mm, 0, "mm"),
          note: tn("meteo.opady.sums.normal_years", p.normal_years),
        },
        ...(lastYear
          ? [{ label: t("meteo.opady.sums.year", { year: lastYear.year }), value: `${fmt(lastYear.percent_of_normal, 0)} %`, note: name(lastYear.precipitation_class) }]
          : []),
        ...(lastMonth
          ? [{ label: monthText(lastMonth.year, lastMonth.month), value: `${fmt(lastMonth.percent_of_normal, 0)} %`, note: name(lastMonth.precipitation_class) }]
          : []),
      ]}
    />
    <h4 class="me-sub">${t("meteo.susze.relative.table")}</h4>
    <${RelativeTable} r=${r} classes=${classes} />`;
}

/** The card „Susze i okresy bezopadowe”. */
export function Susze({ station, analyses }) {
  const code = station.code;
  const list = listOf(analyses);
  const [opt, setOpt] = useOptions(
    { kind: "dry", threshold_mm: undefined, scale: null, first_year: undefined, last_year: undefined, reference_first_year: undefined, reference_last_year: undefined },
    code,
  );
  const kinds = [
    ["dry", t("meteo.susze.spells.kind.dry")],
    ["wet", t("meteo.susze.spells.kind.wet")],
  ].filter(([kind]) => list.some((entry) => entry.analysis === `spells.${kind}`));
  const kind = kinds.some(([k]) => k === opt.kind) ? opt.kind : (kinds[0] || ["dry"])[0];
  const period = { first_year: opt.first_year, last_year: opt.last_year };
  const spells = useMeteo(code, list, `spells.${kind}`, { ...period, threshold_mm: opt.threshold_mm });
  const spi = useMeteo(code, list, "spi", { ...period, reference_first_year: opt.reference_first_year, reference_last_year: opt.reference_last_year });
  const defaultThreshold = (spells.entry && spells.entry.options && spells.entry.options.threshold_mm) ?? 1;
  const threshold = opt.threshold_mm ?? defaultThreshold;
  const spiResult = spi.result;
  const k = spiResult ? (opt.scale ?? Math.max(0, spiResult.scales_months.indexOf(3))) : 0;
  const recordLast = (() => {
    const input = spells.data && (spells.data.inputs || [])[0];
    const set = input && (station.datasets || []).find((d) => d.dataset === input.dataset);
    return set && set.variables.P ? set.variables.P.last : null;
  })();
  const first = spells.data ? spells : spi;
  return html`<div class="me-card">
    <div class="me-toolbar">
      <${Periods}
        station=${station}
        doc=${first.data}
        result=${spiResult || spells.result}
        opt=${opt}
        setOpt=${setOpt}
        reference=${takes(spi.entry, "reference_first_year")}
      />
    </div>
    <${Notices} states=${[spells, spi]} />
    ${spells.entry &&
    html`<${Section} title=${t("meteo.susze.spells.title")} info=${t("meteo.susze.spells.info")} guide="metody-susze-ciagi" states=${[spells]}>
      <div class="me-options">
        ${takes(spells.entry, "threshold_mm") &&
        html`<${Option} label=${t("meteo.common.threshold")}>
          <${ThresholdChoice} value=${threshold} onChange=${(v) => setOpt({ threshold_mm: v === defaultThreshold ? undefined : v })} />
        </${Option}>`}
        ${kinds.length > 1 &&
        html`<${Option} label=${t("meteo.susze.spells.kind_label")}>
          <${Seg} value=${kind} label=${t("meteo.susze.spells.kind_label")} options=${kinds} onChange=${(v) => setOpt({ kind: v })} />
        </${Option}>`}
      </div>
      ${spells.result && html`<${SpellsBody} r=${spells.result} recordLast=${recordLast} />`}
    </${Section}>`}
    ${spi.entry &&
    html`<${Section} title=${t("meteo.susze.spi.title")} info=${t("meteo.susze.spi.info")} guide="metody-susze-spi" states=${[spi]}>
      ${spiResult && html`<${SpiBody} r=${spiResult} k=${Math.min(k, spiResult.scales_months.length - 1)} onScale=${(v) => setOpt({ scale: v })} />`}
    </${Section}>`}
    ${spi.entry &&
    html`<${Section} title=${t("meteo.susze.relative.title")} info=${t("meteo.susze.relative.info")} guide="metody-susze-wzgledny" states=${[spi]}>
      ${spiResult && html`<${RelativeBody} r=${spiResult} />`}
    </${Section}>`}
  </div>`;
}
