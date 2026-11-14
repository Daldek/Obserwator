// „Czas trwania i strefy” (Nogat plan H8, H9): the duration curves of H and Q with their
// classes and modal class, Hydrolog's `stats duration-curve` (O2's ids `duration_curve.H`,
// `duration_curve.Q`) over the whole record or the years and month the person chooses, and
// Rybczyński's zones of the water levels, Hydrolog's `hydrometrics water-level-zones`
// (`water_level_zones.H`, the whole record). Every number is Hydrolog's.

import { Chart, fmt, html, t, tn, useMemo } from "../../lib.js";
import { Figures, Notices, Section, Table, YearRange, useAnalysis } from "../common.js";
import { HYDRO_MONTHS, Option, Select, UNITS, digitsOf, fmtV, recordYears, useOptions, withUnit } from "./util.js";

const IDS = { H: "duration_curve.H", Q: "duration_curve.Q" };
const ZONES = "water_level_zones.H";
/** Calendar months (Hydrolog's `month`, 11 = November) in the order of the hydrological year. */
const CALENDAR = [11, 12, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10];

/** The years of the station's record of any of the variables (each analysis keeps its own). */
export function recordOf(station, variables) {
  const spans = variables.map((variable) => recordYears(station, [variable])).filter(Boolean);
  if (!spans.length) return null;
  return { first: Math.min(...spans.map((s) => s.first)), last: Math.max(...spans.map((s) => s.last)) };
}

/** Hydrolog's value at an exceedance percentage of its table, or null. */
function valueAt(result, percent) {
  const at = result.exceedance_percents.indexOf(percent);
  return at < 0 ? null : result.values[at];
}

/** What a result rests on: its years, its month and the days with a value. */
function basis(result) {
  const month = result.month ? t("hydro.duration.in_month", { month: HYDRO_MONTHS[CALENDAR.indexOf(result.month)] }) : "";
  return t("hydro.duration.basis", { from: result.first_year, to: result.last_year, month, days: tn("hydro.axis.days", result.n_values) });
}

/** The class from the lowest up, as Hydrolog lists them from the highest. */
const ascending = (classes) => [...classes].sort((a, b) => a.lower - b.lower);

/** A class's range with its unit: „90–100 cm”. */
function classRange(item, variable) {
  return `${fmtV(item.lower, variable)}–${fmtV(item.upper, variable)}\u00a0${UNITS[variable]}`;
}

/** The duration curve, on the zones of the water levels where they are given. */
function curveSpec(result, variable, zones) {
  const u = UNITS[variable];
  const series = [];
  if (zones) {
    const low = result.min;
    const top = Math.max(result.curve_values[0], zones.stw_upper);
    const band = (id, cls, from, to) => ({ id, kind: "band", cls, label: id.toUpperCase(), data: [[0, from, to], [100, from, to]], readout: false });
    series.push(band("ntw", "s3", low, zones.ntw_upper), band("stw", "s1", zones.ntw_upper, zones.stw_upper), band("wtw", "s2", zones.stw_upper, top));
  }
  series.push({
    id: "c",
    kind: "line",
    cls: "s1",
    label: t("hydro.duration.curve_label", { variable }),
    unit: u,
    data: result.curve_exceedance_percents.map((p, at) => [p, result.curve_values[at]]),
  });
  return {
    x: { label: t("hydro.duration.x_label"), short: "p", digits: 1, min: 0, max: 100 },
    y: { label: variable === "Q" ? t("hydro.axis.q_log") : `${variable} [${u}]`, unit: u, scale: variable === "Q" ? "log" : "linear", zero: false, digits: digitsOf(variable) },
    series,
    legend: true,
    readout: { series: "c", x: (x) => t("hydro.duration.readout", { p: fmt(x, x < 1 ? 1 : 0) }) },
    fit: { ratio: 0.58, minHeight: 210 },
    title: t("hydro.duration.curve_title", { variable }),
  };
}

/**
 * The share of days of each class of the water levels, the modal class marked; the classes
 * above the level Hydrolog's curve gives for 0.1 % of the days stay in the table only.
 */
function levelClassesSpec(result) {
  const classes = ascending(result.classes);
  const modal = result.modal_class;
  const top = classes.find((item) => item.upper >= result.curve_values[0]) || classes[classes.length - 1];
  const at = (x) => classes.find((item) => item.lower === x);
  return {
    x: { label: t("hydro.duration.level_classes_x", { width: fmt(result.bin_width, 0) }), short: "H", digits: 0, min: classes[0].lower, max: top.upper },
    y: { label: t("hydro.duration.share_axis"), digits: 1 },
    series: [
      {
        id: "f",
        kind: "bars",
        cls: "s4",
        label: t("hydro.duration.class_share"),
        unit: "%",
        data: classes.map((item) => ({ x: item.lower, y: item.share_percent, cls: modal && item.lower === modal.lower ? "hy-modal" : undefined })),
      },
    ],
    readout: { x: (x) => (at(x) ? t("hydro.duration.class_readout", { range: classRange(at(x), "H") }) : "") },
    zoom: true,
    fit: { ratio: 0.42, minHeight: 170 },
    title: t("hydro.duration.level_classes_title"),
  };
}

/** The share of days of each logarithmic class of the discharge, drawn as steps on a log axis. */
function flowClassesSpec(result) {
  const classes = ascending(result.classes);
  const modal = result.modal_class;
  const steps = (items) => items.flatMap((item) => [[item.lower, item.share_percent], [item.upper, item.share_percent]]);
  return {
    x: { label: t("hydro.duration.flow_classes_x", { count: fmt(result.bin_count, 0) }), short: "Q", scale: "log" },
    y: { label: t("hydro.duration.share_axis"), digits: 1 },
    series: [
      { id: "f", kind: "area", cls: "s1", label: t("hydro.duration.class_share"), unit: "%", data: steps(classes) },
      ...(modal ? [{ id: "m", kind: "area", cls: "s2", label: t("hydro.duration.modal"), unit: "%", data: steps([modal]), readout: false }] : []),
    ],
    legend: true,
    readout: { series: "f", x: (x) => `Q = ${fmtV(x, "Q")} m³/s` },
    fit: { ratio: 0.42, minHeight: 170 },
    title: t("hydro.duration.flow_classes_title"),
  };
}

/** The days of each class of the water levels in the months of the hydrological year (the author's table of 2024). */
function MonthTable({ result }) {
  const rows = result.classes.filter((item) => item.days > 0);
  const columns = [
    { key: "lower", label: t("hydro.duration.col.class"), format: (v, row) => `${fmt(row.lower, 0)}–${fmt(row.upper, 0)}` },
    ...HYDRO_MONTHS.map((month, at) => ({ key: `m${at}`, label: month, format: (v, row) => (row.months[at] ? fmt(row.months[at], 0) : "") })),
    { key: "days", label: t("hydro.duration.col.days"), format: (v) => fmt(v, 0) },
    { key: "share_percent", label: "%", format: (v) => fmt(v, 2) },
    { key: "days_with_higher", label: t("hydro.duration.col.with_higher"), format: (v) => fmt(v, 0) },
    { key: "days_with_lower", label: t("hydro.duration.col.with_lower"), format: (v) => fmt(v, 0) },
  ];
  return html`<details class="hy-details">
    <summary>${tn("hydro.duration.months_summary", rows.length)}</summary>
    <${Table} columns=${columns} rows=${rows} className="tbl hy-compact" />
  </details>`;
}

/** The modal class as a tile. */
function modalFigure(result, variable) {
  const modal = result.modal_class;
  return {
    label: t("hydro.duration.modal"),
    value: modal ? classRange(modal, variable) : "–",
    note: modal ? `${tn("hydro.axis.days", modal.days)} (${fmt(modal.share_percent, 1)} %)` : "",
  };
}

/** The section „Czas trwania i strefy”. */
export function Duration({ station, analyses }) {
  const code = station.code;
  const ids = new Set((analyses || []).map((item) => item.analysis));
  const variables = ["H", "Q"].filter((variable) => ids.has(IDS[variable]));
  const record = recordOf(station, variables);
  const [opt, setOpt] = useOptions({ from: undefined, to: undefined, month: 0 }, code);
  const overrides = { first_year: opt.from, last_year: opt.to, month: opt.month || undefined };
  const h = useAnalysis(code, ids.has(IDS.H) ? IDS.H : null, overrides);
  const q = useAnalysis(code, ids.has(IDS.Q) ? IDS.Q : null, overrides);
  const zones = useAnalysis(code, ids.has(ZONES) ? ZONES : null);
  const hr = h.result;
  const qr = q.result;
  const zr = zones.result;
  const chosen = opt.from !== undefined || opt.to !== undefined || opt.month > 0;
  const hCurve = useMemo(() => hr && curveSpec(hr, "H", zr && zr.zones), [hr, zr]);
  const hClasses = useMemo(() => hr && hr.classes.length && levelClassesSpec(hr), [hr]);
  const qCurve = useMemo(() => qr && curveSpec(qr, "Q", null), [qr]);
  const qClasses = useMemo(() => qr && qr.classes.length && flowClassesSpec(qr), [qr]);
  const apply = (from, to) => setOpt({ from: record && from === record.first ? undefined : from, to: record && to === record.last ? undefined : to });
  const table = hr || qr;
  const states = [h, q, zones].filter((state) => state.data || state.loading || state.error);
  return html`<${Section} info=${t("hydro.duration.info")} guide="metody-duration"><div class="hy-card">
    ${record &&
    html`<${YearRange}
      first=${record.first}
      last=${record.last}
      from=${opt.from ?? record.first}
      to=${opt.to ?? record.last}
      onApply=${apply}
      label=${t("hydro.axis.hydro_years")}
    />`}
    <div class="hy-options">
      <${Option} label=${t("hydro.duration.month")}>
        <${Select}
          value=${opt.month}
          label=${t("hydro.duration.month")}
          options=${[[0, t("hydro.duration.whole_year")], ...CALENDAR.map((month, at) => [month, HYDRO_MONTHS[at]])]}
          onChange=${(v) => setOpt({ month: +v })}
        />
      </${Option}>
    </div>
    ${(ids.has(IDS.H) || ids.has(ZONES)) &&
    html`<${Section} title=${t("hydro.duration.levels_title")} states=${[h, zones].filter((state) => state.data || state.loading || state.error)}>
      ${zr &&
      html`<${Figures}
        items=${[
          { label: "NTW", value: `≤ ${withUnit(zr.zones.ntw_upper, "H")}`, note: t("hydro.duration.ntw") },
          { label: "STW", value: `${fmtV(zr.zones.ntw_upper, "H")}–${withUnit(zr.zones.stw_upper, "H")}`, note: t("hydro.duration.stw") },
          { label: "WTW", value: `> ${withUnit(zr.zones.stw_upper, "H")}`, note: t("hydro.duration.wtw") },
          ...(hr ? [modalFigure(hr, "H")] : []),
        ]}
      />`}
      ${hr &&
      html`
        <${Chart} spec=${hCurve} />
        <p class="muted hy-caption">
          ${basis(hr)}${zr && chosen ? ` ${t("hydro.duration.zones_record", { days: tn("hydro.axis.days", zr.n_observations) })}` : ""}
        </p>
        ${hClasses && html`<${Chart} spec=${hClasses} />`}
        ${!hr.month && html`<${MonthTable} result=${hr} />`}
      `}
      ${!hr && zr && html`<p class="muted hy-caption">${t("hydro.duration.zones_record", { days: tn("hydro.axis.days", zr.n_observations) })}</p>`}
    </${Section}>`}
    ${ids.has(IDS.Q) &&
    html`<${Section} title=${t("hydro.duration.flows_title")} states=${[q]}>
      ${qr &&
      html`
        <${Figures}
          items=${[
            { label: t("hydro.duration.q50"), value: withUnit(qr.median, "Q") },
            { label: "Q90", value: withUnit(valueAt(qr, 90), "Q"), note: t("hydro.duration.q90_note") },
            modalFigure(qr, "Q"),
          ]}
        />
        <${Chart} spec=${qCurve} />
        <p class="muted hy-caption">${basis(qr)}</p>
        ${qClasses && html`<${Chart} spec=${qClasses} />`}
      `}
    </${Section}>`}
    ${table &&
    html`<${Section} title=${t("hydro.duration.table_title")}>
      <${Table}
        columns=${[
          { key: "p", label: t("hydro.duration.col.p"), format: (v) => fmt(v, v < 1 ? 1 : 0) },
          ...(hr ? [{ key: "h", label: "H_p [cm]", format: (v) => fmtV(v, "H") }] : []),
          ...(qr ? [{ key: "q", label: "Q_p [m³/s]", format: (v) => fmtV(v, "Q") }] : []),
        ]}
        rows=${table.exceedance_percents.map((p) => ({ p, h: hr ? valueAt(hr, p) : null, q: qr ? valueAt(qr, p) : null }))}
      />
    </${Section}>`}
    <${Notices} states=${states} />
  </div></${Section}>`;
}
