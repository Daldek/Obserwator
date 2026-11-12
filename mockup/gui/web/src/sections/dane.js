// „Dane” (plan D11): a station's series as the store holds them. The dataset switch (the
// station's series datasets), the variables, „rok hydrologiczny | kalendarzowy”, the range of
// years, one chart per unit over the whole span (a missing value or a skipped day breaks the
// line; days flagged „suma z kilku dni” are ticks at the bottom), „Tabela” paged, the units,
// the series version and the provider's attribution. A daily series is decimated in the
// browser for drawing (the chart module's `thinPoints`: per pixel column the first, lowest,
// highest and last value and the first gap), so 27,000 days draw at once; the table and the
// downloads keep every value. IMGW-PIB's half-year characteristics (winter, summer, the year)
// are drawn by hydrological year as the min–max band and the mean, with the dates of the
// extremes in the table.

import { thinPoints } from "../charts/series.js";
import { api } from "../api.js";
import { Chart, dayNumber, fmt, fmtDate, html, isoOfDay, unit, useEffect, useMemo, useState } from "../lib.js";
import { FLAGS, PERIODS, datasetTitle, variableInfo } from "../words.js";
import { Seg, Table, YearRange } from "./common.js";

/** Pixel columns a daily series is thinned to before it is handed to the chart. */
const COLUMNS = 1000;
/** Rows of a page of the daily table. */
const PAGE = 50;
const CLASSES = ["s1", "s2", "s3", "s5", "s6", "s4"];
const HALF_YEAR = "pl.imgw.hydro_semiannual";

/** The store's series of a station (api/series), fetched again when the dataset changes. */
function useSeries(code, dataset) {
  const [state, setState] = useState({ data: null, error: null, loading: true });
  useEffect(() => {
    if (!dataset) return undefined;
    let live = true;
    setState({ data: null, error: null, loading: true });
    api.series(code, dataset).then(
      (data) => live && setState({ data, error: null, loading: false }),
      (error) => live && setState({ data: null, error, loading: false }),
    );
    return () => {
      live = false;
    };
  }, [code, dataset]);
  return state;
}

/** The provider's licence of a dataset (api/export/info, shared with „Pobierz”). */
function useLicence(code, dataset) {
  const [licence, setLicence] = useState(null);
  useEffect(() => {
    if (!dataset) return undefined;
    let live = true;
    setLicence(null);
    api.get("api/export/info", { station: code, dataset }).then(
      (info) => live && setLicence(info.licence),
      () => live && setLicence(null),
    );
    return () => {
      live = false;
    };
  }, [code, dataset]);
  return licence;
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

/** The chart of the chosen variables of one unit within a window. */
function dailySpec({ names, units, prepared, window, kind, title }) {
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
      if (i > first && prepared.days[i] - prepared.days[i - 1] > 1) points.push({ x: prepared.days[i - 1] + 1, y: NaN });
      points.push({ x: prepared.days[i], y: values[i] });
    }
    const info = variableInfo(name, kind);
    const drawn = name === "P" ? (shownDays <= 1100 ? "bars" : "area") : name === "snow_cover" || name === "fresh_snow" ? "area" : "line";
    series.push({
      id: name,
      kind: drawn,
      data: drawn === "bars" ? points : thinPoints(points, (x) => x, COLUMNS),
      label: `${name} — ${info.label}`,
      unit: unit(units[name]),
      digits: info.digits,
      cls: CLASSES[order % CLASSES.length],
    });
    const summed = [];
    for (const [index, flag] of prepared.flags[name]) {
      if (flag === "accumulated" && index >= first && index <= last) summed.push(prepared.days[index]);
    }
    if (summed.length) {
      marks.push({ id: `${name}-accumulated`, kind: "rug", data: summed.slice(0, 3000), label: `${name}: ${FLAGS.accumulated}`, cls: "s6", readout: false });
    }
  });
  const shownUnit = unit(units[names[0]]);
  return {
    title,
    fit: { ratio: 0.42, minHeight: 210 },
    size: "small",
    x: { scale: "date", min: lo, max: hi },
    y: { label: `${names.join(", ")} [${shownUnit}]`, unit: shownUnit, zero: names.every(fromZero), digits: variableInfo(names[0], kind).digits },
    series: [...series, ...marks],
    legend: series.length + marks.length > 1,
    readout: true,
  };
}

function flagText(flag) {
  return flag && flag !== "value" ? html` <span class="flag">${FLAGS[flag] || flag}</span>` : null;
}

/** The paged table of the window, newest first. */
function DailyTable({ prepared, names, units, window, yearType, kind }) {
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
    { key: "date", label: "Data", format: fmtDate },
    { key: "year", label: yearType === "hydrological" ? "Rok hydr." : "Rok", format: String },
    ...names.map((name) => ({
      key: name,
      label: `${name} [${unit(units[name])}]`,
      format: (value, row) => html`${fmt(value, variableInfo(name, kind).digits)}${flagText(row[`${name}_flag`])}`,
    })),
  ];
  return html`<div class="data-table">
    <${Table} columns=${columns} rows=${rows} />
    <div class="pager">
      <button type="button" class="btn sm" disabled=${page === 0} onClick=${() => setPage(0)} aria-label="Najnowsze">«</button>
      <button type="button" class="btn sm" disabled=${page === 0} onClick=${() => setPage(page - 1)}>‹ Nowsze</button>
      <span class="muted">strona ${fmt(page + 1)} z ${fmt(pages)} · ${fmt(count)} dni</span>
      <button type="button" class="btn sm" disabled=${page >= pages - 1} onClick=${() => setPage(page + 1)}>Starsze ›</button>
      <button type="button" class="btn sm" disabled=${page >= pages - 1} onClick=${() => setPage(pages - 1)} aria-label="Najstarsze">»</button>
    </div>
  </div>`;
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
  if (!days.length) return html`<p class="note-box">Szereg tej stacji jest pusty.</p>`;
  const span = [yearOf(days[0], yearType), yearOf(days[days.length - 1], yearType)];
  const years = range ? [Math.max(span[0], range[0]), Math.min(span[1], range[1])] : span;
  const window = range ? windowOf(years[0], years[1], yearType) : [days[0], days[days.length - 1]];
  const shown = names.filter((name) => chosen.includes(name));
  const groups = [];
  for (const name of shown) {
    const group = groups.find((item) => item.unit === data.units[name]);
    if (group) group.names.push(name);
    else groups.push({ unit: data.units[name], names: [name] });
  }
  const toggle = (name) => setChosen(chosen.includes(name) ? chosen.filter((item) => item !== name) : [...chosen, name]);
  const counts = {};
  for (const name of shown) {
    for (const flag of prepared.flags[name].values()) counts[`${name}:${flag}`] = (counts[`${name}:${flag}`] || 0) + 1;
  }
  const label = station.properties.name || station.code;
  return html`
    <div class="data-controls">
      <div class="chips" role="group" aria-label="Zmienne">
        ${names.map(
          (name) => html`<button type="button" class=${chosen.includes(name) ? "chip on" : "chip"} aria-pressed=${chosen.includes(name)} title=${variableInfo(name, kind).label} onClick=${() => toggle(name)}>
            ${name} <span class="chip-unit">${unit(data.units[name])}</span>
          </button>`,
        )}
      </div>
      <${Seg}
        label="Rodzaj roku"
        value=${yearType}
        onChange=${setYearType}
        options=${[
          ["hydrological", "rok hydrologiczny"],
          ["calendar", "kalendarzowy"],
        ]}
      />
      <div class="years-row">
        <${YearRange} first=${span[0]} last=${span[1]} from=${years[0]} to=${years[1]} onApply=${(a, b) => setRange([a, b])} />
        ${range ? html`<button type="button" class="btn sm ghost" onClick=${() => setRange(null)}>Cały okres</button>` : null}
      </div>
    </div>
    ${shown.length
      ? groups.map(
          (group) => html`<div class="data-chart" key=${group.names.join()}>
            <${Chart} spec=${dailySpec({ names: group.names, units: data.units, prepared, window, kind, title: `${label}: ${group.names.join(", ")}` })} />
          </div>`,
        )
      : html`<p class="muted">Wybierz zmienną.</p>`}
    ${Object.keys(counts).length
      ? html`<p class="note">
          Flagi w szeregu: ${Object.entries(counts)
            .map(([key, count]) => {
              const [name, flag] = key.split(":");
              return `${name} ${FLAGS[flag] || flag}: ${fmt(count)} dni`;
            })
            .join(" · ")}.
        </p>`
      : null}
    <div class="btn-row">
      <button type="button" class=${table ? "btn sm is-on" : "btn sm"} aria-pressed=${table} onClick=${() => setTable(!table)}>Tabela</button>
      <span class="muted small">${fmtDate(isoOfDay(Math.max(window[0], days[0])))} – ${fmtDate(isoOfDay(Math.min(window[1], days[days.length - 1])))}</span>
    </div>
    ${table && shown.length ? html`<${DailyTable} prepared=${prepared} names=${shown} units=${data.units} window=${window} yearType=${yearType} kind=${kind} />` : null}
  `;
}

/** "13.08–29.08.1952" for an extreme held from one day to another, "03.02.1951" for one day. */
function extremeDates(start, end) {
  if (!start) return "–";
  if (!end || end === start) return fmtDate(start);
  return start.slice(0, 4) === end.slice(0, 4) ? `${fmtDate(start).slice(0, 5)}–${fmtDate(end)}` : `${fmtDate(start)}–${fmtDate(end)}`;
}

/**
 * The rows of a variable's half-year characteristics by hydrological year: a half-year's
 * own, or the year's: the annual mean, and as the year's extremes the greater maximum and
 * the smaller minimum of the two half-years (a year missing one of them has none).
 */
function halfYearRows(data, group, period) {
  const number = (name, index) => {
    const list = data.values[`${group}_${name}`];
    const value = list && index !== undefined ? list[index] : null;
    return value === null || value === undefined ? NaN : value;
  };
  const when = (name, index, edge) => {
    const list = data.extremes && data.extremes[`${group}_${name}_${edge}`];
    return list && index !== undefined ? list[index] : null;
  };
  const byYear = new Map();
  data.hydro_year.forEach((year, index) => {
    if (!byYear.has(year)) byYear.set(year, {});
    byYear.get(year)[data.period[index]] = index;
  });
  const years = [...byYear.keys()].sort((a, b) => a - b);
  const rows = [];
  for (let year = years[0]; year <= years[years.length - 1]; year += 1) {
    const at = byYear.get(year) || {};
    if (period !== "annual") {
      const i = at[period];
      rows.push({
        year,
        min: number("min", i),
        minDate: extremeDates(when("min", i, "start"), when("min", i, "end")),
        mean: number("mean", i),
        max: number("max", i),
        maxDate: extremeDates(when("max", i, "start"), when("max", i, "end")),
      });
      continue;
    }
    const pick = (name, better) => {
      const winter = number(name, at.winter);
      const summer = number(name, at.summer);
      if (!Number.isFinite(winter) || !Number.isFinite(summer)) return { value: NaN, date: "–" };
      const half = better(summer, winter) ? at.summer : at.winter;
      return { value: number(name, half), date: extremeDates(when(name, half, "start"), when(name, half, "end")) };
    };
    const max = pick("max", (a, b) => a > b);
    const min = pick("min", (a, b) => a < b);
    rows.push({ year, min: min.value, minDate: min.date, mean: number("mean", at.annual), max: max.value, maxDate: max.date });
  }
  return rows;
}

/** IMGW-PIB's half-year characteristics: min, mean and max of H, Q, T by hydrological year. */
function HalfYear({ station, entry, data }) {
  const groups = ["H", "Q", "T"].filter((group) => Object.keys(entry.variables).some((name) => name.startsWith(`${group}_`)));
  const [group, setGroup] = useState(groups[0]);
  const [period, setPeriod] = useState("annual");
  const rows = useMemo(() => (group ? halfYearRows(data, group, period) : []), [data, group, period]);
  if (!group) return html`<p class="note-box">Charakterystyki półroczne tej stacji nie mają wartości.</p>`;
  const kind = station.properties.kind;
  const info = variableInfo(group, kind);
  const shownUnit = unit(data.units[`${group}_mean`]);
  const spec = {
    title: `${station.properties.name || station.code}: ${group}, ${PERIODS[period]}`,
    fit: { ratio: 0.42, minHeight: 210 },
    size: "small",
    x: { label: "rok hydrologiczny", short: "rok", digits: 0, min: rows.length ? rows[0].year : undefined, max: rows.length ? rows[rows.length - 1].year : undefined },
    y: { label: `${group} [${shownUnit}]`, unit: shownUnit, zero: group === "Q", digits: info.digits },
    series: [
      { id: "range", kind: "band", data: rows.map((row) => [row.year, row.min, row.max]), label: "min–maks", cls: "s1" },
      { id: "mean", kind: "line", data: rows.map((row) => [row.year, row.mean]), label: "średni", cls: "s1" },
    ],
    legend: true,
    readout: { series: "mean" },
  };
  // A value with the dates of its extreme below it, so the table fits the panel
  const withDate = (key) => (value, row) => html`${fmt(value, info.digits)}<span class="cell-sub">${row[key]}</span>`;
  const columns = [
    { key: "year", label: "Rok hydr.", format: String },
    { key: "min", label: `min [${shownUnit}]`, format: withDate("minDate") },
    { key: "mean", label: `średni [${shownUnit}]`, digits: info.digits },
    { key: "max", label: `maks [${shownUnit}]`, format: withDate("maxDate") },
  ];
  return html`
    <div class="data-controls">
      ${groups.length > 1
        ? html`<${Seg} label="Zmienna" value=${group} onChange=${setGroup} options=${groups.map((name) => [name, `${name} — ${variableInfo(name, kind).label}`])} />`
        : html`<p class="muted">${group} — ${info.label}</p>`}
      <${Seg} label="Okres" value=${period} onChange=${setPeriod} options=${["annual", "winter", "summer"].map((key) => [key, PERIODS[key]])} />
    </div>
    <div class="data-chart"><${Chart} spec=${spec} /></div>
    <p class="note">
      ${period === "annual"
        ? "Rok: średnia roczna IMGW-PIB; maksimum i minimum to większe i mniejsze z wartości półroczy (rok bez jednego z półroczy — luka)."
        : `Półrocze ${PERIODS[period]}: wartości IMGW-PIB.`}
      ${" "}Pod minimum i maksimum: kiedy wystąpiły (zakres, gdy w kilku dniach), według IMGW-PIB.
    </p>
    <${Table} columns=${columns} rows=${[...rows].reverse().filter((row) => Number.isFinite(row.mean) || Number.isFinite(row.max) || Number.isFinite(row.min))} max=${20} />
  `;
}

function Dane({ station }) {
  const datasets = station.datasets;
  const [dataset, setDataset] = useState(datasets.length ? datasets[0].dataset : null);
  const entry = datasets.find((item) => item.dataset === dataset) || datasets[0] || null;
  const key = entry ? entry.dataset : null;
  const series = useSeries(station.code, key);
  const licence = useLicence(station.code, key);
  if (!entry) {
    return html`<p class="muted">Brak szeregów w magazynie: nie ma czego narysować. Dane katalogowe są w sekcji „Stacja”.</p>`;
  }
  const data = series.data && series.data.dataset === key ? series.data : null;
  // "H_max@summer" and "H" alike as "H [cm]", once per base name
  const units = new Map(Object.entries(entry.variables).map(([name, cov]) => [name.split("@")[0], unit(cov.unit)]));
  return html`<div class="dane">
    ${datasets.length > 1
      ? html`<${Seg} label="Zbiór danych" value=${key} onChange=${setDataset} options=${datasets.map((item) => [item.dataset, datasetTitle(item.dataset)])} />`
      : html`<p class="ds-title">${datasetTitle(key)}</p>`}
    ${series.error ? html`<p class="ana-error">${series.error.message}</p>` : null}
    ${!data && !series.error ? html`<p class="muted">Wczytuję szereg…</p>` : null}
    ${data
      ? key === HALF_YEAR
        ? html`<${HalfYear} key=${`${station.code}:${key}`} station=${station} entry=${entry} data=${data} />`
        : html`<${Daily} key=${`${station.code}:${key}`} station=${station} entry=${entry} data=${data} />`
      : null}
    ${data
      ? html`<footer class="data-foot">
          <p>
            Jednostki: ${[...units].map(([name, text]) => `${name} [${text}]`).join(" · ")}.
            Brak wartości przerywa linię wykresu.
          </p>
          ${licence
            ? html`<p class="attribution">${licence.attribution}. ${licence.processed}.</p>`
            : html`<p class="attribution">${data.attribution}.</p>`}
          <div class="ana-prov">
            <span class="prov">szereg ${data.version}</span>
            <span class="prov">${data.year_type === "hydrological" ? "rok hydrologiczny XI–X" : "rok kalendarzowy"} w magazynie</span>
          </div>
        </footer>`
      : null}
  </div>`;
}

/** The section „Dane”. */
export const DANE = { id: "dane", title: "Dane", component: Dane };
