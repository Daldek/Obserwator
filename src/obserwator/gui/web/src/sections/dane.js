// „Dane pomiarowo-obserwacyjne” (GUI plan D11): a station's series as the data root holds
// them (api/series). The dataset switch (the station's datasets), the variables,
// „rok hydrologiczny | kalendarzowy”, the range of years, one chart per unit over the
// period chosen (a missing value or a skipped day breaks the line; days flagged „suma z
// kilku dni” are ticks at the bottom), „Tabela” paged with each value's flag, the units and
// the definitions of the flags and years, the series version; the panel draws the
// provider's lines under the card (part "series"). The chart module decimates a long
// series for drawing within the range shown, so a ČHMÚ series since 1775 draws and zooms
// at once; the table and the downloads keep every value. IMGW-PIB's monthly and half-year
// characteristics are drawn as the band of the lowest and the highest value with the mean,
// the half-years' with the dates of their extremes in the table.

import { api } from "../api.js";
import { Chart, dayNumber, fmt, fmtDate, html, isoOfDay, lang, t, tn, unit, useEffect, useMemo, useState } from "../lib.js";
import { FLAGS, datasetShort, datasetTitle, flagName, periodName, variableInfo } from "../words.js";
import { Seg, Table, YearRange } from "./common.js";

/** Rows of a page of the daily table. */
const PAGE = 50;
/** The series' colours of a chart, in order. */
const CLASSES = ["s1", "s2", "s3", "s5", "s6", "s4"];
/** The groups of the monthly and half-year characteristics: their variables' bases. */
const GROUPS = ["H", "Q", "T"];
/** The periods of a half-year series, in the order offered. */
const HALVES = ["annual", "winter", "summer"];

/** The data root's series of a station (api/series), fetched again when the dataset changes. */
function useSeries(code, dataset) {
  const [state, setState] = useState({ data: null, error: null });
  useEffect(() => {
    if (!dataset) return undefined;
    const control = new AbortController();
    setState({ data: null, error: null });
    api.series(dataset, code, { signal: control.signal }).then(
      (data) => setState({ data, error: null }),
      (error) => !control.signal.aborted && setState({ data: null, error }),
    );
    return () => control.abort();
  }, [code, dataset]);
  return state;
}

function dayOf(year, month, day) {
  return Math.round(Date.UTC(year, month, day) / 86400000);
}

/** The year of a day: calendar, or hydrological (November to October, named by its end). */
function yearOf(day, yearType) {
  const date = new Date(day * 86400000);
  const year = date.getUTCFullYear();
  return yearType === "hydrological" && date.getUTCMonth() >= 10 ? year + 1 : year;
}

/** The first and last day of a range of years. */
function windowOf(from, to, yearType) {
  return yearType === "hydrological" ? [dayOf(from - 1, 10, 1), dayOf(to, 9, 31)] : [dayOf(from, 0, 1), dayOf(to, 11, 31)];
}

/** The first index whose day is at least `day` (days ascending). */
function lowerBound(days, day) {
  let lo = 0;
  let hi = days.length;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (days[mid] < day) lo = mid + 1;
    else hi = mid;
  }
  return lo;
}

/** A series document as typed arrays: days, values (NaN missing) and the flags by index. */
function prepare(data) {
  const days = Int32Array.from(data.dates, dayNumber);
  const values = {};
  const flags = {};
  for (const [name, list] of Object.entries(data.values)) {
    values[name] = Float64Array.from(list, (value) => (value === null ? NaN : value));
    flags[name] = new Map((data.flags[name] || []).map(([index, flag]) => [index, flag]));
  }
  return { days, values, flags };
}

/** The variables shown first. */
function defaultVariables(names, kind) {
  const wanted = kind === "hydro" ? ["H", "Q"] : ["Tmean", "P"];
  const chosen = wanted.filter((name) => names.includes(name));
  return chosen.length ? chosen : names.slice(0, 1);
}

/** Whether a variable's axis starts at zero (a quantity that is never negative). */
function fromZero(name) {
  return ["Q", "P", "snow_cover", "fresh_snow"].includes(name);
}

/** "H — water level". */
function variableLabel(name) {
  return `${name} — ${variableInfo(name).label}`;
}

/** The chart of the chosen variables of one unit within a window, every day of it. */
function dailySpec({ names, units, prepared, window, title }) {
  const [lo, hi] = window;
  const first = lowerBound(prepared.days, lo);
  const last = lowerBound(prepared.days, hi + 1) - 1;
  const shownDays = Math.max(0, last - first + 1);
  const series = [];
  const marks = [];
  names.forEach((name, order) => {
    const values = prepared.values[name];
    const points = [];
    for (let i = first; i <= last; i += 1) {
      // A skipped day breaks the line as a missing value does
      if (i > first && prepared.days[i] - prepared.days[i - 1] > 1) points.push({ x: prepared.days[i - 1] + 1, y: NaN });
      points.push({ x: prepared.days[i], y: values[i] });
    }
    const info = variableInfo(name);
    const drawn = name === "P" ? (shownDays <= 1100 ? "bars" : "area") : name === "snow_cover" || name === "fresh_snow" ? "area" : "line";
    series.push({ id: name, kind: drawn, data: points, label: variableLabel(name), unit: unit(units[name]), digits: info.digits, cls: CLASSES[order % CLASSES.length] });
    const summed = [];
    for (const [index, flag] of prepared.flags[name]) {
      if (flag === "accumulated" && index >= first && index <= last) summed.push(prepared.days[index]);
    }
    if (summed.length) {
      marks.push({ id: `${name}-accumulated`, kind: "rug", data: summed, label: `${name}: ${flagName("accumulated")}`, cls: "s6", readout: false });
    }
  });
  const shownUnit = unit(units[names[0]]);
  return {
    title,
    fit: { ratio: 0.42, minHeight: 210 },
    size: "small",
    x: { scale: "date", min: lo, max: hi },
    y: { label: `${names.join(", ")} [${shownUnit}]`, unit: shownUnit, zero: names.every(fromZero), digits: variableInfo(names[0]).digits },
    series: [...series, ...marks],
    legend: series.length + marks.length > 1,
    readout: true,
  };
}

function flagMark(flag) {
  return flag && flag !== "value" ? html` <span class="flag">${flagName(flag)}</span>` : null;
}

/** The paged table of the window, newest first, each value with its flag. */
function DailyTable({ prepared, names, units, window, yearType }) {
  const [page, setPage] = useState(0);
  const first = lowerBound(prepared.days, window[0]);
  const last = lowerBound(prepared.days, window[1] + 1) - 1;
  const count = Math.max(0, last - first + 1);
  const pages = Math.max(1, Math.ceil(count / PAGE));
  useEffect(() => setPage(0), [window[0], window[1], names.join(",")]);
  const rows = [];
  for (let k = 0; k < PAGE; k += 1) {
    const i = last - page * PAGE - k;
    if (i < first) break;
    const row = { date: isoOfDay(prepared.days[i]), year: yearOf(prepared.days[i], yearType) };
    for (const name of names) {
      row[name] = prepared.values[name][i];
      row[`${name}_flag`] = prepared.flags[name].get(i) || (Number.isFinite(prepared.values[name][i]) ? "value" : "missing");
    }
    rows.push(row);
  }
  const columns = [
    { key: "date", label: t("station.data.date"), format: fmtDate },
    { key: "year", label: yearType === "hydrological" ? t("station.data.hydro_year") : t("station.data.year"), format: String },
    ...names.map((name) => ({
      key: name,
      label: `${name} [${unit(units[name])}]`,
      format: (value, row) => html`${fmt(value, variableInfo(name).digits)}${flagMark(row[`${name}_flag`])}`,
    })),
  ];
  return html`<div class="data-table">
    <${Table} columns=${columns} rows=${rows} />
    <div class="pager">
      <button type="button" class="btn sm" disabled=${page === 0} onClick=${() => setPage(0)} aria-label=${t("station.data.newest")} title=${t("station.data.newest")}>«</button>
      <button type="button" class="btn sm" disabled=${page === 0} onClick=${() => setPage(page - 1)}>${t("station.data.newer")}</button>
      <span class="muted">${t("station.data.page", { page: fmt(page + 1), pages: fmt(pages), days: tn("station.data.days", count) })}</span>
      <button type="button" class="btn sm" disabled=${page >= pages - 1} onClick=${() => setPage(page + 1)}>${t("station.data.older")}</button>
      <button type="button" class="btn sm" disabled=${page >= pages - 1} onClick=${() => setPage(pages - 1)} aria-label=${t("station.data.oldest")} title=${t("station.data.oldest")}>»</button>
    </div>
  </div>`;
}

/** The meaning of the flags that the variables shown carry, beside their marks. */
function FlagNotes({ entry, data, prepared, names }) {
  const present = new Set();
  for (const name of names) {
    if (prepared.values[name].some(Number.isNaN)) present.add("missing");
    if ((entry.variables[name] || {}).accumulated > 0) present.add("accumulated");
    if ((data.flags[name] || []).some(([, flag]) => flag === "no_phenomenon")) present.add("no_phenomenon");
  }
  const shown = FLAGS.filter((flag) => present.has(flag));
  if (!shown.length) return null;
  return html`<p class="note">
    ${shown.map((flag, index) => html`${index ? html`<br />` : null}<span class="flag">${flagName(flag)}</span> ${t(`station.data.flag_def.${flag}`)}`)}
  </p>`;
}

/** A daily series: variables, years, charts and the table. */
function Daily({ station, entry, data }) {
  const kind = station.properties.kind;
  const prepared = useMemo(() => prepare(data), [data]);
  const names = Object.keys(data.units).filter((name) => entry.variables[name] && prepared.values[name]);
  const [chosen, setChosen] = useState(() => defaultVariables(names, kind));
  const [yearType, setYearType] = useState(data.year_type === "calendar" ? "calendar" : "hydrological");
  const [range, setRange] = useState(null);
  const [table, setTable] = useState(false);
  const days = prepared.days;
  const span = days.length ? [yearOf(days[0], yearType), yearOf(days[days.length - 1], yearType)] : [0, 0];
  const years = range ? [Math.max(span[0], range[0]), Math.min(span[1], range[1])] : span;
  const window = range && days.length ? windowOf(years[0], years[1], yearType) : [days[0], days[days.length - 1]];
  const shown = names.filter((name) => chosen.includes(name));
  const label = station.properties.name || station.code;
  const specs = useMemo(() => {
    if (!days.length) return [];
    const groups = [];
    for (const name of shown) {
      const group = groups.find((item) => item.unit === data.units[name]);
      if (group) group.names.push(name);
      else groups.push({ unit: data.units[name], names: [name] });
    }
    return groups.map((group) => ({
      key: group.names.join(),
      spec: dailySpec({ names: group.names, units: data.units, prepared, window, title: `${label}: ${group.names.join(", ")}` }),
    }));
  }, [prepared, shown.join(), window[0], window[1], lang()]);
  if (!days.length) return html`<p class="note-box">${t("station.data.empty")}</p>`;
  const toggle = (name) => setChosen(chosen.includes(name) ? chosen.filter((item) => item !== name) : [...chosen, name]);
  return html`
    <div class="data-controls">
      <div class="chips" role="group" aria-label=${t("station.data.variables")}>
        ${names.map(
          (name) => html`<button type="button" class=${chosen.includes(name) ? "chip on" : "chip"} aria-pressed=${chosen.includes(name)} title=${variableInfo(name).label} onClick=${() => toggle(name)}>
            ${name} <span class="chip-unit">${unit(data.units[name])}</span>
          </button>`,
        )}
      </div>
      <${Seg}
        label=${t("station.data.year_type")}
        value=${yearType}
        onChange=${setYearType}
        options=${[
          ["hydrological", t("station.data.hydrological_year")],
          ["calendar", t("station.data.calendar_year")],
        ]}
      />
      <div class="years-row">
        <${YearRange} first=${span[0]} last=${span[1]} from=${years[0]} to=${years[1]} onApply=${(a, b) => setRange([a, b])} recommend=${false} />
        ${range ? html`<button type="button" class="btn sm ghost" onClick=${() => setRange(null)}>${t("station.data.whole_period")}</button>` : null}
      </div>
    </div>
    ${specs.length
      ? specs.map((item) => html`<div class="data-chart" key=${item.key}><${Chart} spec=${item.spec} /></div>`)
      : html`<p class="muted">${t("station.data.choose_variable")}</p>`}
    <${FlagNotes} entry=${entry} data=${data} prepared=${prepared} names=${shown} />
    <div class="btn-row">
      <button type="button" class=${table ? "btn sm is-on" : "btn sm"} aria-pressed=${table} onClick=${() => setTable(!table)}>${t("station.data.table")}</button>
      <span class="muted small">${fmtDate(isoOfDay(Math.max(window[0], days[0])))} – ${fmtDate(isoOfDay(Math.min(window[1], days[days.length - 1])))}</span>
    </div>
    ${table && shown.length ? html`<${DailyTable} prepared=${prepared} names=${shown} units=${data.units} window=${window} yearType=${yearType} />` : null}
  `;
}

/** "13.08–29.08.1952" for an extreme held from one day to another, "03.02.1951" for one day. */
function extremeDates(start, end) {
  if (!start) return "–";
  if (!end || end === start) return fmtDate(start);
  return start.slice(0, 4) === end.slice(0, 4) ? `${fmtDate(start).slice(0, 5)}–${fmtDate(end)}` : `${fmtDate(start)}–${fmtDate(end)}`;
}

/** A value of a series document, NaN for none. */
function valueOf(data, name, index) {
  const list = data.values[name];
  const value = list && index !== undefined ? list[index] : null;
  return value === null || value === undefined ? NaN : value;
}

/** The dates of a half-year's extreme. */
function datesOf(data, name, index) {
  const starts = data.extremes && data.extremes[`${name}_start`];
  const ends = data.extremes && data.extremes[`${name}_end`];
  if (!starts || index === undefined) return "–";
  return extremeDates(starts[index], ends ? ends[index] : null);
}

/**
 * The rows of a group's half-year characteristics by hydrological year: a half-year's own,
 * or the year's: IMGW-PIB's annual mean, and as the year's extremes the higher maximum and
 * the lower minimum of its two half-years, picked with their dates (a year missing one of
 * them has none).
 */
function halfYearRows(data, group, period) {
  const byYear = new Map();
  data.hydro_year.forEach((year, index) => {
    if (!byYear.has(year)) byYear.set(year, {});
    byYear.get(year)[data.period[index]] = index;
  });
  const years = [...byYear.keys()].sort((a, b) => a - b);
  const rows = [];
  if (!years.length) return rows;
  for (let year = years[0]; year <= years[years.length - 1]; year += 1) {
    const at = byYear.get(year) || {};
    if (period !== "annual") {
      const i = at[period];
      rows.push({
        x: year,
        min: valueOf(data, `${group}_min`, i),
        minDate: datesOf(data, `${group}_min`, i),
        mean: valueOf(data, `${group}_mean`, i),
        max: valueOf(data, `${group}_max`, i),
        maxDate: datesOf(data, `${group}_max`, i),
      });
      continue;
    }
    const pick = (name, higher) => {
      const winter = valueOf(data, name, at.winter);
      const summer = valueOf(data, name, at.summer);
      if (!Number.isFinite(winter) || !Number.isFinite(summer)) return { value: NaN, date: "–" };
      const half = (higher ? summer > winter : summer < winter) ? at.summer : at.winter;
      return { value: valueOf(data, name, half), date: datesOf(data, name, half) };
    };
    const max = pick(`${group}_max`, true);
    const min = pick(`${group}_min`, false);
    rows.push({ x: year, min: min.value, minDate: min.date, mean: valueOf(data, `${group}_mean`, at.annual), max: max.value, maxDate: max.date });
  }
  return rows;
}

/** The rows of a group's monthly characteristics, one per month of the series. */
function monthRows(data, group) {
  return data.dates.map((date, index) => ({
    x: dayNumber(date),
    month: date,
    min: valueOf(data, `${group}_min`, index),
    mean: valueOf(data, `${group}_mean`, index),
    max: valueOf(data, `${group}_max`, index),
  }));
}

/** "11.1950" of the first day of a month, as the language writes dates. */
function monthText(iso) {
  return fmtDate(iso).slice(3);
}

/**
 * IMGW-PIB's monthly or half-year characteristics: the lowest, mean and highest value of
 * H, Q or T by month, or by hydrological year and half-year with the extremes' dates.
 */
function Characteristics({ station, entry, data }) {
  const half = data.time_unit === "half_year";
  const groups = GROUPS.filter((group) => Object.keys(entry.variables).some((name) => name.startsWith(`${group}_`)));
  const [group, setGroup] = useState(groups[0]);
  const [period, setPeriod] = useState("annual");
  const rows = useMemo(() => (group ? (half ? halfYearRows(data, group, period) : monthRows(data, group)) : []), [data, group, period]);
  if (!group) return html`<p class="note-box">${t("station.data.no_characteristics")}</p>`;
  const info = variableInfo(group);
  const shownUnit = unit(data.units[`${group}_mean`]);
  const label = station.properties.name || station.code;
  const spec = {
    title: half ? `${label}: ${group}, ${periodName(period)}` : `${label}: ${group}`,
    fit: { ratio: 0.42, minHeight: 210 },
    size: "small",
    x: half
      ? { label: t("station.data.hydrological_year"), short: t("station.data.year_short"), digits: 0, min: rows.length ? rows[0].x : undefined, max: rows.length ? rows[rows.length - 1].x : undefined }
      : { scale: "date" },
    y: { label: `${group} [${shownUnit}]`, unit: shownUnit, zero: group === "Q", digits: info.digits },
    series: [
      { id: "range", kind: "band", data: rows.map((row) => [row.x, row.min, row.max]), label: t("station.data.range"), cls: "s1" },
      { id: "mean", kind: "line", data: rows.map((row) => [row.x, row.mean]), label: t("station.data.mean"), cls: "s1" },
    ],
    legend: true,
    readout: { series: "mean" },
    zoom: true,
  };
  // A value with the dates of its extreme under it, so the table fits the panel
  const withDate = (key) => (value, row) => html`${fmt(value, info.digits)}<span class="cell-sub">${row[key]}</span>`;
  const columns = half
    ? [
        { key: "x", label: t("station.data.hydro_year"), format: String },
        { key: "min", label: `min [${shownUnit}]`, format: withDate("minDate") },
        { key: "mean", label: t("station.data.mean_column", { unit: shownUnit }), digits: info.digits },
        { key: "max", label: t("station.data.max_column", { unit: shownUnit }), format: withDate("maxDate") },
      ]
    : [
        { key: "month", label: t("station.data.month"), format: monthText },
        { key: "min", label: `min [${shownUnit}]`, digits: info.digits },
        { key: "mean", label: t("station.data.mean_column", { unit: shownUnit }), digits: info.digits },
        { key: "max", label: t("station.data.max_column", { unit: shownUnit }), digits: info.digits },
      ];
  const filled = [...rows].reverse().filter((row) => Number.isFinite(row.mean) || Number.isFinite(row.max) || Number.isFinite(row.min));
  return html`
    <div class="data-controls">
      ${groups.length > 1
        ? html`<${Seg} label=${t("station.variable")} value=${group} onChange=${setGroup} options=${groups.map((name) => [name, variableLabel(name)])} />`
        : html`<p class="muted">${variableLabel(group)}</p>`}
      ${half ? html`<${Seg} label=${t("station.data.period")} value=${period} onChange=${setPeriod} options=${HALVES.map((key) => [key, periodName(key)])} />` : null}
    </div>
    <div class="data-chart"><${Chart} spec=${spec} /></div>
    <p class="note">
      ${half ? (period === "annual" ? t("station.data.annual_note") : t("station.data.half_note", { period: periodName(period) })) : t("station.data.monthly_note")}
      ${half ? ` ${t("station.data.dates_note")}` : ""}
    </p>
    <${Table} columns=${columns} rows=${filled} max=${half ? 20 : 24} />
  `;
}

/** The units of a dataset's variables, once per base name: "H [cm] · Q [m³/s]". */
function unitsText(entry) {
  const base = (name) => name.split("@")[0].replace(/_(min|mean|max)$/, "");
  const units = new Map(Object.entries(entry.variables).map(([name, cov]) => [base(name), unit(cov.unit)]));
  return [...units].map(([name, text]) => `${name} [${text}]`).join(" · ");
}

function Dane({ station }) {
  const datasets = station.datasets;
  const [dataset, setDataset] = useState(datasets.length ? datasets[0].dataset : null);
  const entry = datasets.find((item) => item.dataset === dataset) || datasets[0] || null;
  const key = entry ? entry.dataset : null;
  const series = useSeries(station.code, key);
  if (!entry) return html`<p class="muted">${t("station.data.none")}</p>`;
  const data = series.data && series.data.dataset === key ? series.data : null;
  const daily = entry.time_unit === "day";
  return html`<div>
    <div class="data-controls">
      ${datasets.length > 1
        ? html`<${Seg} label=${t("station.data.dataset")} value=${key} onChange=${setDataset} options=${datasets.map((item) => [item.dataset, datasetShort(item.dataset)])} />`
        : null}
      <p class="ds-title">${datasetTitle(key)}</p>
    </div>
    ${series.error ? html`<p class="ana-error" role="alert">${series.error.message}</p>` : null}
    ${!data && !series.error ? html`<p class="muted" role="status">${t("station.data.loading")}</p>` : null}
    ${data
      ? daily
        ? html`<${Daily} key=${`${station.code}:${key}`} station=${station} entry=${entry} data=${data} />`
        : html`<${Characteristics} key=${`${station.code}:${key}`} station=${station} entry=${entry} data=${data} />`
      : null}
    ${data
      ? html`<footer class="data-foot">
          <p>${t("station.data.units", { units: unitsText(entry) })}</p>
          ${data.year_type === "hydrological" ? html`<p>${t("station.data.hydrological_def")}</p>` : daily ? html`<p>${t("station.data.calendar_def")}</p>` : null}
          <div class="ana-prov">
            <span class="prov">${t("sections.series_version", { version: data.version })}</span>
            <span class="prov">${data.year_type === "hydrological" ? t("station.data.stored_hydrological") : t("station.data.stored_calendar")}</span>
          </div>
        </footer>`
      : null}
  </div>`;
}

/** The section „Dane pomiarowo-obserwacyjne”. */
export const DANE = { id: "dane", title: "station.dane.title", component: Dane, part: "series" };
