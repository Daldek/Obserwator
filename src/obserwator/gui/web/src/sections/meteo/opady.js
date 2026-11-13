// „Opady” (Nogat plan M1 to M5, M7, M9): sums and normals, the monthly regime, days with
// precipitation and the intensity, heavy precipitation, the maxima of 1 to 10 days and their
// quantiles beside PMAXTP of the station's point. Every number is a field of Hydrolog's
// result of an analysis id (`precipitation.{sums,seasonality,days,intensity,heavy,maxima}`,
// `precipitation_quantiles[.Nd]`) or of IMGW-PIB's PMAXTP (api/pmaxtp); the page picks,
// sorts for display, formats and draws.

import { Chart, fmt, html, lang, t, tn, useContext, useEffect, useMemo, useState } from "../../lib.js";
import { pmaxtpQuery, usePmaxtp } from "../../pmaxtp/state.js";
import { Figures, Notices, ResultLines, Section, Seg, Table } from "../common.js";
import {
  Option,
  Periods,
  ROMAN,
  Select,
  Source,
  byYear,
  date,
  dateRange,
  entryOf,
  listOf,
  mmLimit as mm,
  newestFirst,
  num,
  takes,
  useMeteo,
  useOptions,
  yearAxis,
  yearAxisLabel,
  yearReadout,
} from "./util.js";

/** The return periods of the quantile tables [years]. */
const TABLE_T = [2, 5, 10, 20, 50, 100, 200, 500, 1000];
/** PMAXTP's durations [min] beside the maxima of 1, 2 and 3 days. */
const PMAXTP_MINUTES = { 1: 1440, 2: 2880, 3: 4320 };
/** The distributions' curves, each in its own style; the best is drawn thicker. */
const DIST_CLASS = { gev: "s1", log_normal: "s2", pearson3: "s3", weibull: "s6" };
const DISTRIBUTIONS = ["log_normal", "gev", "pearson3", "weibull"];
const FIT_METHODS = ["l_moments", "mle", "moments", "least_squares"];

/** A distribution's name: the names read alike in both languages but the log-normal. */
function distName(name) {
  if (name === "log_normal") return t("meteo.dist.log_normal");
  return { gev: "GEV", pearson3: "Pearson III", weibull: "Weibull" }[name] || name;
}

/** The id of the quantiles of the n-day maxima. */
function quantileId(days) {
  return days === 1 ? "precipitation_quantiles" : `precipitation_quantiles.${days}d`;
}

/** The number of days of the maxima an id of quantiles fits (1 for `precipitation_quantiles`). */
function daysOfId(id) {
  const found = /^precipitation_quantiles(?:\.(\d+)d)?$/.exec(id || "");
  return found ? Number(found[1] || 1) : null;
}

/** The index of the row of a return period T in a list of return periods. */
function atPeriod(periods, years) {
  return (periods || []).findIndex((value) => Math.abs(value - years) < 1e-6);
}

/** A month's value of a result's `months` list (by the month 1–12), or null. */
function monthOf(rows, month, key) {
  const row = (rows || []).find((r) => r.month === month);
  return row ? row[key] ?? null : null;
}

// --- sums, normals and the regime ----------------------------------------------------------

function SumsChart({ r, view }) {
  const spec = useMemo(() => {
    const x = yearAxis(r.years, yearAxisLabel(r.year_type));
    if (view === "pct") {
      return {
        x,
        y: { label: t("meteo.opady.sums.axis_pct"), unit: "%", zero: true },
        series: [
          {
            id: "pct",
            kind: "bars",
            label: t("meteo.opady.sums.series_pct"),
            align: "center",
            data: r.years.map((row) => ({
              x: row.year,
              y: row.percent_of_normal === null ? null : row.percent_of_normal - 100,
              cls: row.percent_of_normal === null ? "" : row.percent_of_normal >= 100 ? "me-wet" : "me-dry",
            })),
          },
        ],
        readout: { x: yearReadout, value: (v) => t("meteo.opady.sums.pct_of_normal", { pct: fmt(v + 100, 0) }) },
        fit: { ratio: 0.5, minHeight: 190 },
        title: t("meteo.opady.sums.chart_pct"),
      };
    }
    const normal = r.period.normal_mm;
    return {
      x,
      y: { label: t("meteo.opady.sums.axis_mm"), unit: "mm" },
      series: [{ id: "sum", kind: "bars", cls: "bar-p", label: t("meteo.opady.sums.series_mm"), align: "center", data: byYear(r.years, "total_mm") }],
      marks: normal === null || normal === undefined ? [] : [{ kind: "hline", y: normal, label: t("meteo.opady.sums.normal_mark", { value: fmt(normal, 0) }) }],
      readout: { x: yearReadout },
      fit: { ratio: 0.5, minHeight: 190 },
      title: t("meteo.opady.sums.chart_mm"),
    };
  }, [r, view, lang()]);
  return html`<${Chart} spec=${spec} />`;
}

/** The monthly sums (mm or % of the normal) or the seasonal sums of every year. */
function AllYears({ r }) {
  const [view, setView] = useState("mm");
  const year = { key: "year", label: t("meteo.common.year"), format: (v) => String(v) };
  let columns;
  let rows;
  if (view === "seasons") {
    const seasons = [
      ["djf_mm", "XII–II"],
      ["mam_mm", "III–V"],
      ["jja_mm", "VI–VIII"],
      ["son_mm", "IX–XI"],
    ];
    columns = [year, ...seasons.map(([key, label]) => ({ key, label, format: (v) => num(v, 1) }))];
    rows = newestFirst(r.years);
  } else {
    const field = view === "pct" ? "percent_of_normal" : "total_mm";
    const months = (r.years[0] && r.years[0].months.map((m) => m.month)) || [];
    columns = [year, ...months.map((month, at) => ({ key: `m${at}`, label: ROMAN[month - 1], format: (v) => num(v, view === "pct" ? 0 : 1) }))];
    rows = newestFirst(r.years).map((row) => Object.fromEntries([["year", row.year], ...row.months.map((m, at) => [`m${at}`, m[field]])]));
  }
  return html`<${Seg}
      value=${view}
      label=${t("meteo.opady.sums.table_label")}
      options=${[
        ["mm", t("meteo.opady.sums.table.mm")],
        ["pct", t("meteo.opady.sums.table.pct")],
        ["seasons", t("meteo.opady.sums.table.seasons")],
      ]}
      onChange=${setView}
    />
    <${Table} className="tbl me-wide" columns=${columns} rows=${rows} />`;
}

function SumsBody({ station, doc, r, regime }) {
  const [view, setView] = useState("mm");
  const p = r.period;
  const last = [...r.years].reverse().find((row) => row.total_mm !== null);
  const normal = t("meteo.common.normal", { from: r.reference_first_year, to: r.reference_last_year });
  const shares = regime && regime.period ? regime.period.months : [];
  const monthColumns = [
    { key: "month", label: t("meteo.common.month"), format: (v) => ROMAN[v - 1] },
    { key: "normal_mm", label: normal, format: (v) => num(v, 1) },
    { key: "mean_mm", label: t("meteo.opady.sums.mean_col"), format: (v) => num(v, 1) },
    { key: "min_mm", label: t("meteo.opady.sums.min_col"), format: (v, row) => (v === null ? "–" : `${fmt(v, 1)} (${row.min_year})`) },
    { key: "max_mm", label: t("meteo.opady.sums.max_col"), format: (v, row) => (v === null ? "–" : `${fmt(v, 1)} (${row.max_year})`) },
    { key: "month", label: t("meteo.opady.sums.share_col"), format: (v) => num(monthOf(shares, v, "share_percent"), 1) },
  ];
  const yearColumns = [
    { key: "year", label: t("meteo.common.year"), format: (v) => String(v) },
    { key: "total_mm", label: t("meteo.opady.sums.total_col"), format: (v) => num(v, 1) },
    { key: "percent_of_normal", label: t("meteo.opady.sums.pct_col"), format: (v) => num(v, 0) },
    { key: "winter_mm", label: "XI–IV", format: (v) => num(v, 1) },
    { key: "summer_mm", label: "V–X", format: (v) => num(v, 1) },
  ];
  const normals = [
    ["winter_normal_mm", "XI–IV"],
    ["summer_normal_mm", "V–X"],
    ["djf_normal_mm", "XII–II"],
    ["mam_normal_mm", "III–V"],
    ["jja_normal_mm", "VI–VIII"],
    ["son_normal_mm", "IX–XI"],
  ];
  return html`<${Source} station=${station} doc=${doc} variable="P" />
    <${Figures}
      items=${[
        { label: t("meteo.opady.sums.mean"), value: num(p.mean_mm, 0, "mm"), note: `${r.first_year}–${r.last_year}` },
        { label: normal, value: num(p.normal_mm, 0, "mm"), note: tn("meteo.opady.sums.normal_years", p.normal_years) },
        {
          label: t("meteo.opady.sums.year", { year: last ? last.year : "–" }),
          value: last ? num(last.total_mm, 0, "mm") : "–",
          note: last && last.percent_of_normal !== null ? t("meteo.opady.sums.pct_of_normal", { pct: fmt(last.percent_of_normal, 0) }) : "",
        },
        { label: t("meteo.opady.sums.extremes"), value: `${num(p.min_mm, 0)} · ${num(p.max_mm, 0)} mm`, note: `${p.min_year ?? "–"} · ${p.max_year ?? "–"}` },
        { label: t("meteo.opady.sums.cv"), value: num(p.cv, 2), note: `σ = ${num(p.std_mm, 0, "mm")}` },
      ]}
    />
    <${Option} label=${t("meteo.common.chart")}>
      <${Seg}
        value=${view}
        label=${t("meteo.opady.sums.view_label")}
        options=${[
          ["mm", t("meteo.opady.sums.view.mm")],
          ["pct", t("meteo.opady.sums.view.pct")],
        ]}
        onChange=${setView}
      />
    </${Option}>
    <${SumsChart} r=${r} view=${view} />
    <h4 class="me-sub">${t("meteo.opady.sums.months")}</h4>
    <${Table} columns=${monthColumns} rows=${p.months} />
    <h4 class="me-sub">${t("meteo.opady.sums.normals")}</h4>
    <${Table} columns=${normals.map(([key, label]) => ({ key, label, format: (v) => num(v, 1) }))} rows=${[p]} />
    <h4 class="me-sub">${t("meteo.common.years")}</h4>
    <${Table} columns=${yearColumns} rows=${newestFirst(r.years)} max=${10} />
    <details class="me-details">
      <summary>${t("meteo.opady.sums.all_years")}</summary>
      <${AllYears} r=${r} />
    </details>`;
}

function RegimeBody({ r }) {
  const p = r.period;
  const spec = useMemo(
    () => ({
      x: { label: t("meteo.opady.regime.axis_x"), tickList: ROMAN.map((label, at) => ({ value: at + 1, label })), min: 0.5, max: 12.5 },
      y: { label: t("meteo.opady.regime.axis_y"), unit: "%" },
      series: [{ id: "share", kind: "bars", cls: "bar-p", label: t("meteo.opady.regime.series"), align: "center", data: p.months.map((m) => [m.month, m.share_percent]) }],
      marks: [{ kind: "hline", y: 100 / 12, label: "1/12" }],
      readout: { x: (x) => ROMAN[Math.round(x) - 1] || "" },
      fit: { ratio: 0.45, minHeight: 170 },
      title: t("meteo.opady.regime.chart"),
    }),
    [r, lang()],
  );
  if (p.pci === null || p.pci === undefined) {
    return html`<p class="muted">${t("meteo.opady.regime.no_normal", { from: r.reference_first_year, to: r.reference_last_year })}</p>`;
  }
  const pci = (cls) => (cls ? t(`meteo.opady.pci.${cls}`) : "");
  const si = (cls) => (cls ? t(`meteo.opady.si.${cls}`) : "");
  return html`<${Chart} spec=${spec} />
    <${Figures}
      items=${[
        { label: t("meteo.opady.regime.pci"), value: num(p.pci, 1), note: pci(p.pci_class) },
        { label: t("meteo.opady.regime.pci_years"), value: num(p.mean_pci, 1), note: pci(p.mean_pci_class) },
        { label: t("meteo.opady.regime.si"), value: num(p.si, 2), note: si(p.si_class) },
        { label: t("meteo.opady.regime.si_years"), value: num(p.mean_si, 2), note: si(p.mean_si_class) },
      ]}
    />
    <${Table}
      columns=${[{ key: "name", label: "", format: (v) => v }, ...p.months.map((m, at) => ({ key: `m${at}`, label: ROMAN[m.month - 1], format: (v) => num(v, 2) }))]}
      rows=${[{ name: t("meteo.opady.regime.coefficient"), ...Object.fromEntries(p.months.map((m, at) => [`m${at}`, m.coefficient])) }]}
      className="tbl me-wide"
    />
    <details class="me-details">
      <summary>${t("meteo.opady.regime.years")}</summary>
      <${Table}
        columns=${[
          { key: "year", label: t("meteo.common.year"), format: (v) => String(v) },
          { key: "pci", label: "PCI", format: (v) => num(v, 1) },
          { key: "pci_class", label: t("meteo.opady.regime.class_col"), format: pci },
          { key: "si", label: "SI", format: (v) => num(v, 2) },
          { key: "si_class", label: t("meteo.opady.regime.class_col"), format: si },
        ]}
        rows=${newestFirst(r.years)}
        max=${10}
      />
    </details>`;
}

// --- days with precipitation, intensity, heavy precipitation -----------------------------

function DaysChart({ r, k }) {
  const spec = useMemo(() => {
    const threshold = mm(r.thresholds_mm[k]);
    const mean = r.period.days[k];
    return {
      x: yearAxis(r.years, yearAxisLabel(r.year_type)),
      y: { label: t("meteo.opady.days.axis", { threshold }), unit: t("meteo.common.days_unit") },
      series: [{ id: `d${k}`, kind: "bars", cls: "bar-pe", label: t("meteo.opady.days.series", { threshold }), align: "center", data: r.years.map((row) => [row.year, row.days[k]]) }],
      marks: mean === null || mean === undefined ? [] : [{ kind: "hline", y: mean, label: t("meteo.common.mean_value", { value: fmt(mean, 1) }) }],
      readout: { x: yearReadout, value: (v) => fmt(v, 0) },
      fit: { ratio: 0.45, minHeight: 170 },
      title: t("meteo.opady.days.chart"),
    };
  }, [r, k, lang()]);
  return html`<${Chart} spec=${spec} />`;
}

function DaysBody({ r, intensity, wet, onWet, wetEntry }) {
  const [k, setK] = useState(Math.min(2, r.thresholds_mm.length - 1));
  const p = r.period;
  const thresholds = r.thresholds_mm;
  const ip = intensity && intensity.period;
  const wetDay = intensity ? intensity.wet_day_mm : 1;
  const sdiiByYear = new Map(((intensity && intensity.years) || []).map((row) => [row.year, row.sdii_mm]));
  const dayColumns = thresholds.map((v, at) => ({ key: `d${at}`, label: `≥ ${mm(v)} mm`, format: (x) => num(x, 1) }));
  const monthRows = p.months.map((m) => ({
    month: m.month,
    ...Object.fromEntries(m.days.map((v, at) => [`d${at}`, v])),
    sdii: monthOf(ip && ip.months, m.month, "sdii_mm"),
  }));
  const yearRows = newestFirst(r.years).map((row) => ({ year: row.year, ...Object.fromEntries(row.days.map((v, at) => [`d${at}`, v])), sdii: sdiiByYear.get(row.year) ?? null }));
  return html`<${Figures}
      items=${[
        ...thresholds.map((v, at) => ({ label: t("meteo.opady.days.figure", { threshold: mm(v) }), value: num(p.days[at], 0), note: t("meteo.opady.days.per_year") })),
        ...(ip ? [{ label: t("meteo.opady.days.sdii", { threshold: mm(wetDay) }), value: num(ip.mean_sdii_mm, 1, "mm/d"), note: tn("meteo.common.complete_years", ip.sdii_years) }] : []),
      ]}
    />
    <div class="me-options">
      <${Option} label=${t("meteo.common.threshold")}>
        <${Seg} value=${String(k)} label=${t("meteo.opady.days.threshold_label")} options=${thresholds.map((v, at) => [String(at), `≥ ${mm(v)} mm`])} onChange=${(v) => setK(+v)} />
      </${Option}>
      ${takes(wetEntry, "wet_day_mm") &&
      html`<${Option} label=${t("meteo.opady.days.wet_day")}>
        <${Seg}
          value=${String(wet)}
          label=${t("meteo.opady.days.wet_day")}
          options=${[
            ["1", "≥ 1 mm"],
            ["0.1", `≥ ${mm(0.1)} mm`],
          ]}
          onChange=${onWet}
        />
      </${Option}>`}
    </div>
    <${DaysChart} r=${r} k=${k} />
    <h4 class="me-sub">${t("meteo.opady.days.months")}</h4>
    <${Table}
      columns=${[{ key: "month", label: t("meteo.common.month"), format: (v) => ROMAN[v - 1] }, ...dayColumns, { key: "sdii", label: "SDII [mm/d]", format: (v) => num(v, 1) }]}
      rows=${monthRows}
    />
    <h4 class="me-sub">${t("meteo.common.years")}</h4>
    <${Table}
      columns=${[
        { key: "year", label: t("meteo.common.year"), format: (v) => String(v) },
        ...dayColumns.map((c) => ({ ...c, format: (x) => num(x, 0) })),
        { key: "sdii", label: "SDII [mm/d]", format: (v) => num(v, 1) },
      ]}
      rows=${yearRows}
      max=${10}
    />`;
}

function HeavyBody({ r }) {
  const p = r.period;
  const names = r.percentiles.map((pc) => `R${fmt(pc, 0)}p`);
  const wet = mm(r.wet_day_mm);
  const spec = useMemo(
    () => ({
      x: yearAxis(r.years, yearAxisLabel(r.year_type)),
      y: { label: t("meteo.opady.heavy.axis", { wet }), unit: "%" },
      series: [
        { id: "r0", kind: "bars", cls: "bar-pe", label: `${names[0]}TOT`, align: "center", data: r.years.map((row) => [row.year, row.complete ? row.shares_percent[0] : null]) },
        ...names.slice(1).map((name, at) => ({
          id: `r${at + 1}`,
          kind: "points",
          label: `${name}TOT`,
          data: r.years.filter((row) => row.complete && row.shares_percent[at + 1] !== null).map((row) => [row.year, row.shares_percent[at + 1]]),
        })),
      ],
      legend: true,
      readout: { x: yearReadout, value: (v) => `${fmt(v, 1)} %` },
      fit: { ratio: 0.45, minHeight: 170 },
      title: t("meteo.opady.heavy.chart"),
    }),
    [r, lang()],
  );
  return html`<${Figures}
      items=${[
        ...names.map((name, at) => ({
          label: t("meteo.opady.heavy.threshold", { p: fmt(r.percentiles[at], 0) }),
          value: num(p.thresholds_mm[at], 1, "mm"),
          note: at === 0 ? t("meteo.opady.heavy.threshold_note", { from: r.reference_first_year, to: r.reference_last_year, wet, n: fmt(p.wet_days, 0) }) : "",
        })),
        ...names.map((name, at) => ({
          label: t("meteo.opady.heavy.share_mean", { index: `${name}TOT` }),
          value: num(p.mean_shares_percent[at], 1, "%"),
          note: at === 0 ? tn("meteo.common.complete_years", p.n_years) : "",
        })),
      ]}
    />
    <${Chart} spec=${spec} />
    <${Table}
      columns=${[
        { key: "year", label: t("meteo.common.year"), format: (v) => String(v) },
        { key: "wet_day_total_mm", label: t("meteo.opady.heavy.total_col", { wet }), format: (v) => num(v, 1) },
        ...names.flatMap((name, at) => [
          { key: "year", label: t("meteo.opady.heavy.sum_col", { index: name }), format: (v, row) => (row.sums_mm[at] === null ? "–" : `${num(row.sums_mm[at], 1)} (${row.days[at]})`) },
          { key: "year", label: `${name}TOT %`, format: (v, row) => num(row.shares_percent[at], 1) },
        ]),
      ]}
      rows=${newestFirst(r.years).filter((row) => row.complete)}
      max=${8}
    />`;
}

// --- maxima of 1 to 10 days and their quantiles beside PMAXTP --------------------------

function MaximaChart({ r, k, duration }) {
  const spec = useMemo(() => {
    const s = r.period.durations[k];
    return {
      x: yearAxis(r.years, yearAxisLabel(r.year_type)),
      y: { label: t("meteo.opady.maxima.axis", { duration }), unit: "mm" },
      series: [
        {
          id: "max",
          kind: "bars",
          cls: "bar-p",
          label: t("meteo.opady.maxima.series"),
          align: "center",
          data: r.years.map((row) => [row.year, row.complete && row.durations[k] ? row.durations[k].sum_mm : null]),
        },
      ],
      marks: s && s.mean_mm !== null ? [{ kind: "hline", y: s.mean_mm, label: t("meteo.common.mean_value", { value: `${fmt(s.mean_mm, 1)} mm` }) }] : [],
      readout: { x: yearReadout },
      fit: { ratio: 0.45, minHeight: 170 },
      title: t("meteo.opady.maxima.chart", { duration }),
    };
  }, [r, k, duration, lang()]);
  return html`<${Chart} spec=${spec} />`;
}

/** The choice of the number of days of the maxima. */
function DaysSeg({ durations, days, onDays }) {
  return html`<${Option} label=${t("meteo.opady.maxima.duration")}>
    <${Seg}
      value=${String(days)}
      label=${t("meteo.opady.maxima.duration_label")}
      options=${durations.map((n) => [String(n), tn("meteo.opady.days_n", n)])}
      onChange=${(v) => onDays(+v)}
    />
  </${Option}>`;
}

function MaximaBody({ r, days, onDays }) {
  const k = Math.max(0, r.durations_days.indexOf(days));
  const n = r.durations_days[k];
  const s = r.period.durations[k];
  const duration = tn("meteo.opady.days_n", n);
  const skipped = r.period.incomplete_years || [];
  const top = r.years
    .filter((row) => row.complete && row.durations[k] && row.durations[k].sum_mm !== null)
    .sort((a, b) => b.durations[k].sum_mm - a.durations[k].sum_mm)
    .slice(0, 10);
  const columns = [
    { key: "year", label: t("meteo.common.year"), format: (v) => String(v) },
    ...r.durations_days.map((d, at) => ({ key: "year", label: `${d} d`, format: (v, row) => (row.complete ? num(row.durations[at] && row.durations[at].sum_mm, 1) : "–") })),
    {
      key: "year",
      label: t("meteo.opady.maxima.dates_col", { duration }),
      format: (v, row) => (row.complete && row.durations[k] ? dateRange(row.durations[k].start_date, row.durations[k].end_date) : "–"),
    },
  ];
  return html`<${DaysSeg} durations=${r.durations_days} days=${n} onDays=${onDays} />
    <${Figures}
      items=${[
        { label: t("meteo.opady.maxima.mean"), value: num(s.mean_mm, 1, "mm"), note: t("meteo.opady.maxima.median", { value: num(s.median_mm, 1, "mm") }) },
        { label: t("meteo.opady.maxima.largest"), value: num(s.max_mm, 1, "mm"), note: dateRange(s.max_start_date, s.max_end_date) },
        { label: t("meteo.opady.maxima.smallest"), value: num(s.min_mm, 1, "mm") },
        { label: t("meteo.opady.maxima.complete"), value: String(s.n_years), note: skipped.length ? t("meteo.opady.maxima.left_out", { n: skipped.length }) : "" },
      ]}
    />
    <${MaximaChart} r=${r} k=${k} duration=${duration} />
    <h4 class="me-sub">${t("meteo.opady.maxima.table")}</h4>
    <${Table} columns=${columns} rows=${newestFirst(r.years)} max=${10} />
    ${skipped.length ? html`<p class="muted me-caption">${t("meteo.opady.maxima.incomplete", { years: skipped.join(", ") })}</p>` : null}
    <h4 class="me-sub">${t("meteo.opady.maxima.months")}</h4>
    <${Table}
      columns=${[
        { key: "month", label: t("meteo.common.month"), format: (v) => ROMAN[v - 1] },
        { key: "max_mm", label: t("meteo.opady.maxima.highest_col"), format: (v, row) => (v === null ? "–" : `${fmt(v, 1)} (${date(row.date)})`) },
        { key: "mean_max_mm", label: t("meteo.opady.maxima.mean_col"), format: (v) => num(v, 1) },
        { key: "annual_maxima", label: t("meteo.opady.maxima.annual_col"), format: (v) => (v === null || v === undefined ? "–" : `${v}×`) },
      ]}
      rows=${r.period.months}
    />
    <details class="me-details">
      <summary>${t("meteo.opady.maxima.top", { duration })}</summary>
      <${Table}
        columns=${[
          { key: "year", label: t("meteo.common.year"), format: (v) => String(v) },
          { key: "year", label: t("meteo.opady.maxima.value_col"), format: (v, row) => num(row.durations[k].sum_mm, 1) },
          { key: "year", label: t("meteo.opady.maxima.date_col"), format: (v, row) => dateRange(row.durations[k].start_date, row.durations[k].end_date) },
        ]}
        rows=${top}
      />
    </details>`;
}

/**
 * PMAXTP of the station's point beside the maxima of 1, 2 or 3 days: both methods, asked of
 * IMGW-PIB through the server (cached there), only for IMGW-PIB's stations with coordinates.
 */
function usePmaxtpBeside(station, days) {
  const minutes = PMAXTP_MINUTES[days];
  let reason = null;
  if (station.provider !== "IMGW-PIB") reason = t("meteo.opady.pmaxtp.poland_only");
  else if (!Number.isFinite(station.lat) || !Number.isFinite(station.lon)) reason = t("meteo.opady.pmaxtp.no_point");
  else if (!minutes) reason = t("meteo.opady.pmaxtp.up_to_3_days");
  const point = reason ? null : { lat: station.lat, lon: station.lon };
  const pot = usePmaxtp(point, "POT");
  const amp = usePmaxtp(point, "AMP");
  return { point, reason, minutes, hours: minutes ? minutes / 60 : null, methods: [["POT", pot, "s4"], ["AMP", amp, "s5"]] };
}

/** PMAXTP's depths of a duration by the exceedance probability [%], or null. */
function pmaxtpLine(state, minutes) {
  const table = state.doc && state.doc.data && state.doc.data.ks && state.doc.data.ks[String(minutes)];
  if (!table) return null;
  return new Map(Object.entries(table).map(([p, value]) => [Math.round(Number(p) * 1e4) / 1e4, value]));
}

/** The same computation as a command of Hydrolog's program (its values inline). */
function commandLine(doc) {
  const options = (doc.envelope && doc.envelope.inputs) || doc.options || {};
  const parts = Object.entries(options)
    .filter(([, value]) => value !== null && value !== undefined)
    .map(([name, value]) => `--${name.replace(/_/g, "-")}=${Array.isArray(value) ? value.join(",") : value}`);
  return `hydrolog ${doc.command} ${parts.join(" ")} --json`;
}

function QuantilesChart({ r, pm, duration }) {
  const spec = useMemo(() => {
    const series = r.distributions.map((d, at) => ({
      id: `${d.distribution_name}-${d.fit_method}`,
      kind: "line",
      cls: `${DIST_CLASS[d.distribution_name] || "s4"}${at === 0 ? " best" : ""}`,
      label: distName(d.distribution_name),
      data: d.return_periods.map((value, k) => [100 * d.exceedance_probabilities[k], d.quantiles[k]]).filter(([, q]) => Number.isFinite(q)),
    }));
    const legend = r.distributions.map((d, at) => ({
      label: at === 0 ? `${distName(d.distribution_name)} ${t("meteo.opady.quantiles.best_mark")}` : distName(d.distribution_name),
      kind: "stroke",
      cls: DIST_CLASS[d.distribution_name] || "s4",
    }));
    series.push({
      id: "emp",
      kind: "points",
      label: t("meteo.opady.quantiles.empirical"),
      data: r.empirical.values_sorted.map((v, k) => [100 * r.empirical.exceedance_prob[k], v]),
      readout: false,
    });
    legend.push({ label: t("meteo.opady.quantiles.empirical"), kind: "points" });
    for (const line of pm) {
      series.push({ id: `pmaxtp-${line.method}`, kind: "line", cls: line.cls, label: `PMAXTP ${line.method}`, data: line.points, readout: false });
      legend.push({ label: `PMAXTP ${line.method} (${line.hours} h)`, kind: "stroke", cls: line.cls });
    }
    return {
      x: { scale: "gumbel", domain: [99, 0.1], label: t("meteo.opady.quantiles.axis_x") },
      y: { label: t("meteo.opady.quantiles.axis_y", { duration }), unit: "mm" },
      series,
      legend,
      readout: { series: series[0].id },
      fit: { ratio: 0.66, minHeight: 240 },
      title: t("meteo.opady.quantiles.chart"),
    };
  }, [r, pm, duration, lang()]);
  return html`<${Chart} spec=${spec} />`;
}

function QuantilesBody({ station, quantiles, maxima, days, pmaxtp }) {
  const r = quantiles.result;
  const best = r.distributions[0];
  const duration = tn("meteo.opady.days_n", days);
  const lines = [];
  for (const [method, state, cls] of pmaxtp.methods) {
    const byP = pmaxtp.minutes ? pmaxtpLine(state, pmaxtp.minutes) : null;
    if (!byP) continue;
    const points = [...byP.entries()].filter(([p]) => p >= 0.1 && p <= 99).sort((a, b) => b[0] - a[0]);
    lines.push({ method, cls, hours: pmaxtp.hours, byP, points, doc: state.doc });
  }
  const pmKey = lines.map((l) => `${l.method}${l.points.length}`).join(" ");
  const pm = useMemo(() => lines, [pmKey, r]);
  // PMAXTP's lines go to the view's strip while its quantiles are drawn
  const report = useContext(ResultLines);
  const pmaxtpDoc = lines.length ? lines[0].doc : null;
  useEffect(() => {
    if (report && pmaxtpDoc) report(pmaxtpDoc);
  }, [report, pmaxtpDoc]);
  const rowOf = (years) => {
    const at = atPeriod(best.return_periods, years);
    const p = at < 0 ? 100 / years : Math.round(100 * best.exceedance_probabilities[at] * 1e4) / 1e4;
    const row = { p, T: years, best: at < 0 ? null : best.quantiles[at] };
    for (const line of lines) row[line.method] = line.byP.get(Math.round(p * 1e4) / 1e4) ?? null;
    return row;
  };
  const rows = TABLE_T.map(rowOf);
  const complete = maxima && maxima.years ? maxima.years.filter((row) => row.complete) : [];
  const p1 = rowOf(100);
  const columns = [
    { key: "p", label: "p [%]", format: (v) => fmt(v, v >= 1 ? 0 : 1) },
    { key: "T", label: t("meteo.opady.quantiles.t_col"), format: (v) => fmt(v, 0) },
    { key: "best", label: `${distName(best.distribution_name)} [mm]`, format: (v) => num(v, 1) },
    ...lines.map((line) => ({ key: line.method, label: `${line.method} ${line.hours} h`, format: (v) => num(v, 1) })),
  ];
  const allColumns = [
    { key: "T", label: t("meteo.opady.quantiles.t_col"), format: (v) => fmt(v, 0) },
    ...r.distributions.map((d, at) => ({ key: `d${at}`, label: distName(d.distribution_name), format: (v) => num(v, 1) })),
  ];
  const allRows = TABLE_T.map((years) => ({
    T: years,
    ...Object.fromEntries(r.distributions.map((d, at) => [`d${at}`, d.quantiles[atPeriod(d.return_periods, years)] ?? null])),
  }));
  const paramName = (name) => (["shape", "loc", "scale", "skew"].includes(name) ? t(`meteo.fit.param.${name}`) : name);
  const fitRows = r.distributions.map((d) => ({
    name: distName(d.distribution_name),
    method: t(`meteo.fit.${d.fit_method}`),
    aic: d.aic,
    ks: `${num(d.ks_statistic, 3)} (${num(d.ks_p_value, 2)}${d.ks_valid === false ? "*" : ""})`,
    ad: d.ad_statistic,
    params: Object.entries(d.parameters || {})
      .map(([name, value]) => `${paramName(name)} ${fmt(value, Math.abs(value) >= 100 ? 1 : 3)}`)
      .join(", "),
  }));
  const point = pmaxtp.point;
  const pmaxtpError = pmaxtp.methods.map(([, state]) => state.error).find(Boolean);
  const pmaxtpLoading = pmaxtp.methods.some(([, state]) => state.loading);
  return html`<${Figures}
      items=${[
        { label: t("meteo.opady.quantiles.years"), value: String(r.n_years), note: complete.length ? `${complete[0].year}–${complete[complete.length - 1].year}` : "" },
        { label: t("meteo.opady.quantiles.best"), value: distName(best.distribution_name), note: t(`meteo.fit.${best.fit_method}`) },
        { label: t("meteo.opady.quantiles.p1"), value: num(p1.best, 1, "mm") },
        ...lines
          .filter((line) => line.method === "POT" && p1.POT !== null && p1.POT !== undefined)
          .map((line) => ({ label: `PMAXTP ${line.method}, p = 1 %`, value: num(p1.POT, 1, "mm"), note: t("meteo.opady.quantiles.pmaxtp_note", { hours: line.hours }) })),
      ]}
    />
    <${QuantilesChart} r=${r} pm=${pm} duration=${duration} />
    <h4 class="me-sub">${t("meteo.opady.quantiles.table")}</h4>
    <${Table} columns=${columns} rows=${rows} />
    ${pmaxtp.reason ? html`<p class="muted me-caption">${pmaxtp.reason}</p>` : null}
    ${!pmaxtp.reason && pmaxtpLoading ? html`<p class="muted me-caption">${t("meteo.opady.pmaxtp.loading")}</p>` : null}
    ${!pmaxtp.reason && !pmaxtpLoading && pmaxtpError ? html`<p class="muted me-caption">${t("meteo.opady.pmaxtp.failed", { error: pmaxtpError.message })}</p>` : null}
    ${!pmaxtp.reason && !pmaxtpLoading && !pmaxtpError && !lines.length
      ? html`<p class="muted me-caption">${t("meteo.opady.pmaxtp.no_duration", { hours: pmaxtp.hours })}</p>`
      : null}
    ${lines.length
      ? html`<p class="muted me-caption">
            ${t("meteo.opady.quantiles.pmaxtp_caption", { hours: pmaxtp.hours, point: `${fmt(point.lat, 4)}° N, ${fmt(point.lon, 4)}° E` })}
            ${" "}<a href=${`?${new URLSearchParams({ view: "pmaxtp", ...pmaxtpQueryPoint(point) }).toString()}`}>${t("meteo.opady.quantiles.pmaxtp_link")}</a>
          </p>`
      : null}
    <details class="me-details">
      <summary>${t("meteo.opady.quantiles.all")}</summary>
      <${Table} columns=${allColumns} rows=${allRows} />
      <${Table}
        columns=${[
          { key: "name", label: t("meteo.opady.quantiles.distribution"), format: (v) => v },
          { key: "method", label: t("meteo.opady.quantiles.method"), format: (v) => v },
          { key: "aic", label: "AIC", format: (v) => num(v, 1) },
          { key: "ks", label: "KS (p)", format: (v) => v },
          { key: "ad", label: "A²", format: (v) => num(v, 3) },
          { key: "params", label: t("meteo.opady.quantiles.params_col"), format: (v) => v },
        ]}
        rows=${fitRows}
      />
      <p class="muted me-caption">${t("meteo.opady.quantiles.ks_note")}</p>
    </details>
    <details class="me-details">
      <summary>${t("meteo.opady.quantiles.cli")}</summary>
      <pre class="me-cli">${commandLine(quantiles.data)}</pre>
    </details>`;
}

/** The point of the PMAXTP view's address (lat, lon with IMGW-PIB's four decimals). */
function pmaxtpQueryPoint(point) {
  const query = pmaxtpQuery(point, "POT");
  return { lat: query.latitude, lon: query.longitude };
}

function Quantiles({ station, quantiles, maxima, opt, setOpt, durations, entry }) {
  const days = opt.days;
  // the duration of the result shown (the previous one while the chosen one is computed)
  const shown = daysOfId(quantiles.data && quantiles.data.analysis) ?? days;
  const pmaxtp = usePmaxtpBeside(station, shown);
  const defaults = (entry && entry.options) || {};
  const distribution = opt.distribution ?? defaults.distribution ?? "all";
  const method = opt.fit_method ?? defaults.fit_method ?? "l_moments";
  const options = html`<div class="me-options">
    ${durations.length > 1 && html`<${DaysSeg} durations=${durations} days=${days} onDays=${(n) => setOpt({ days: n })} />`}
    ${takes(entry, "distribution") &&
    html`<${Option} label=${t("meteo.opady.quantiles.distribution")}>
      <${Select}
        value=${distribution}
        label=${t("meteo.opady.quantiles.distribution")}
        options=${[["all", t("meteo.dist.all")], ...DISTRIBUTIONS.map((name) => [name, distName(name)])]}
        onChange=${(v) => setOpt({ distribution: v === defaults.distribution ? undefined : v })}
      />
    </${Option}>`}
    ${takes(entry, "fit_method") &&
    html`<${Option} label=${t("meteo.opady.quantiles.method")}>
      <${Select}
        value=${method}
        label=${t("meteo.opady.quantiles.method_label")}
        options=${FIT_METHODS.map((name) => [name, t(`meteo.fit.${name}`)])}
        onChange=${(v) => setOpt({ fit_method: v === defaults.fit_method ? undefined : v })}
      />
    </${Option}>`}
  </div>`;
  return html`<${Section} title=${t("meteo.opady.quantiles.title")} info=${t("meteo.opady.quantiles.info")} states=${[quantiles]}>
    ${options}
    <${Notices} states=${[quantiles]} />
    ${quantiles.result &&
    html`<${QuantilesBody} station=${station} quantiles=${quantiles} maxima=${maxima.result} days=${shown} pmaxtp=${pmaxtp} />`}
  </${Section}>`;
}

/** The card „Opady”. */
export function Opady({ station, analyses }) {
  const code = station.code;
  const list = listOf(analyses);
  const [opt, setOpt] = useOptions(
    {
      year_type: undefined,
      first_year: undefined,
      last_year: undefined,
      reference_first_year: undefined,
      reference_last_year: undefined,
      wet_day_mm: undefined,
      days: 1,
      distribution: undefined,
      fit_method: undefined,
    },
    code,
  );
  const period = { year_type: opt.year_type, first_year: opt.first_year, last_year: opt.last_year };
  const reference = { reference_first_year: opt.reference_first_year, reference_last_year: opt.reference_last_year };
  const sums = useMeteo(code, list, "precipitation.sums", { ...period, ...reference });
  const regime = useMeteo(code, list, "precipitation.seasonality", { ...period, ...reference });
  const days = useMeteo(code, list, "precipitation.days", period);
  const intensity = useMeteo(code, list, "precipitation.intensity", { ...period, wet_day_mm: opt.wet_day_mm });
  const heavy = useMeteo(code, list, "precipitation.heavy", { ...period, ...reference });
  const maxima = useMeteo(code, list, "precipitation.maxima", period);
  const durations = [1, 2, 3, 5, 10].filter((n) => entryOf(list, quantileId(n)));
  const qDays = durations.includes(opt.days) ? opt.days : 1;
  const quantiles = useMeteo(code, list, quantileId(qDays), { ...period, distribution: opt.distribution, fit_method: opt.fit_method });
  const yearType = opt.year_type || "calendar";
  const first = [sums, regime, days, heavy, maxima, intensity].find((s) => s.data);
  const wetDefault = String((intensity.result && intensity.result.wet_day_mm) ?? 1);
  return html`<div class="me-card">
    <div class="me-toolbar">
      <${Option} label=${t("meteo.common.year")}>
        <${Seg}
          value=${yearType}
          label=${t("meteo.common.year_type_label")}
          options=${[
            ["calendar", t("meteo.common.year_type.calendar")],
            ["hydrological", t("meteo.common.year_type.hydrological")],
          ]}
          onChange=${(v) => setOpt({ year_type: v === "calendar" ? undefined : v })}
        />
      </${Option}>
      <${Periods}
        station=${station}
        doc=${first && first.data}
        yearType=${yearType}
        result=${sums.result || (first && first.result)}
        opt=${opt}
        setOpt=${setOpt}
        reference=${takes(sums.entry, "reference_first_year")}
      />
    </div>
    <${Notices} states=${[sums, regime, days, intensity, heavy, maxima]} />
    ${sums.entry &&
    html`<${Section} title=${t("meteo.opady.sums.title")} info=${t("meteo.opady.sums.info")} states=${[sums]}>
      ${sums.result && html`<${SumsBody} station=${station} doc=${sums.data} r=${sums.result} regime=${regime.result} />`}
    </${Section}>`}
    ${regime.entry &&
    html`<${Section} title=${t("meteo.opady.regime.title")} info=${t("meteo.opady.regime.info")} states=${[regime]}>
      ${regime.result && html`<${RegimeBody} r=${regime.result} />`}
    </${Section}>`}
    ${days.entry &&
    html`<${Section} title=${t("meteo.opady.days.title")} info=${t("meteo.opady.days.info")} states=${[days, intensity]}>
      ${days.result &&
      html`<${DaysBody}
        r=${days.result}
        intensity=${intensity.result}
        wet=${opt.wet_day_mm ?? wetDefault}
        wetEntry=${intensity.entry}
        onWet=${(v) => setOpt({ wet_day_mm: v === "1" ? undefined : +v })}
      />`}
    </${Section}>`}
    ${heavy.entry &&
    html`<${Section} title=${t("meteo.opady.heavy.title")} info=${t("meteo.opady.heavy.info")} states=${[heavy]}>
      ${heavy.result && html`<${HeavyBody} r=${heavy.result} />`}
    </${Section}>`}
    ${maxima.entry &&
    html`<${Section} title=${t("meteo.opady.maxima.title")} info=${t("meteo.opady.maxima.info")} states=${[maxima]}>
      ${maxima.result && html`<${MaximaBody} r=${maxima.result} days=${opt.days} onDays=${(n) => setOpt({ days: n })} />`}
    </${Section}>`}
    ${quantiles.entry &&
    html`<${Quantiles}
      station=${station}
      quantiles=${quantiles}
      maxima=${maxima}
      opt=${{ ...opt, days: qDays }}
      setOpt=${setOpt}
      durations=${durations}
      entry=${quantiles.entry}
    />`}
  </div>`;
}
