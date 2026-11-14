// „Śnieg” (Nogat plan M10): Hydrolog's snow cover of each winter (`meteo snow`, the id
// `snow`): days with snow cover, the largest depth, the first and the last day with cover
// and fresh snow, of the winters August–July named after the year they end in. Every number
// is a field of Hydrolog's result; the page picks, formats and draws.

import { Chart, fmt, html, t, tn, useMemo, useState } from "../../lib.js";
import { Figures, Notices, Section, Seg, Table, YearRange } from "../common.js";
import { Option, ROMAN, Source, date, monthDay, newestFirst, num, recordYears, useMeteo, useOptions, yearAxis } from "./util.js";

/** The months of the table of days with snow cover: October to May, as the winter runs. */
const WINTER_MONTHS = [10, 11, 12, 1, 2, 3, 4, 5];

/** A winter as "1990/91": the season August–July that ends in `year`. */
function season(year) {
  return `${year - 1}/${String(year).slice(2)}`;
}

/** Whether Hydrolog gave a value (not null). */
function present(value) {
  return value !== null && value !== undefined;
}

/**
 * The card „Śnieg”.
 *
 * @param {{station: object, analyses: object[]}} props
 */
export function Snieg({ station, analyses }) {
  const code = station.code;
  const [opt, setOpt] = useOptions({ first_year: undefined, last_year: undefined }, code);
  const state = useMeteo(code, analyses, "snow", opt);
  const data = state.result;
  const [view, setView] = useState("days");
  const spec = useMemo(() => {
    if (!data) return null;
    const max = view === "max";
    const counted = data.years.filter((r) => r.complete);
    const mean = max ? data.period.mean_max_depth_cm : data.period.mean_cover_days;
    return {
      x: yearAxis(data.years, t("meteo.snow.season_axis")),
      y: { label: max ? t("meteo.snow.max_axis") : t("meteo.snow.days_axis"), unit: max ? "cm" : t("meteo.common.days_unit") },
      series: max
        ? [{ id: "max", kind: "bars", cls: "s4", label: t("meteo.snow.max_series"), align: "center", data: data.years.map((r) => [r.year, r.max_depth_cm ?? null]) }]
        : [{ id: "days", kind: "bars", cls: "s4", label: t("meteo.snow.days_series"), align: "center", data: counted.map((r) => [r.year, r.cover_days ?? null]) }],
      marks: present(mean) ? [{ kind: "hline", y: mean, label: t("meteo.common.mean_value", { value: fmt(mean, 0) }) }] : [],
      readout: { x: (x) => t("meteo.snow.readout", { season: season(Math.round(x)) }), value: (v) => fmt(v, 0) },
      fit: { ratio: 0.45, minHeight: 170 },
      title: max ? t("meteo.snow.max_title") : t("meteo.snow.days_title"),
    };
  }, [data, view]);
  const record = recordYears(station, state.data, "snow_cover", "hydrological");
  const title = t("meteo.snow.title");
  const info = t("meteo.snow.info");
  const onRange = (a, b) =>
    setOpt(record && a === record.first && b === record.last ? { first_year: undefined, last_year: undefined } : { first_year: a, last_year: b });
  if (!data) return html`<div class="me-card"><${Section} title=${title} info=${info} guide="metody-snieg" states=${[state]} /></div>`;
  const p = data.period;
  const fresh = present(p.mean_fresh_snow_cm);
  const months = new Map((p.months || []).map((m) => [m.month, m.cover_days]));
  const columns = [
    { key: "year", label: t("meteo.snow.col.season"), format: (v) => season(v) },
    { key: "cover_days", label: t("meteo.snow.col.days"), format: (v) => num(v, 0) },
    { key: "max_depth_cm", label: t("meteo.snow.col.max"), format: (v, r) => (v ? `${fmt(v, 0)} (${date(r.max_date)})` : num(v, 0)) },
    { key: "first_date", label: t("meteo.snow.col.first"), format: (v) => date(v) },
    { key: "last_date", label: t("meteo.snow.col.last"), format: (v) => date(v) },
    ...(fresh ? [{ key: "fresh_snow_cm", label: t("meteo.snow.col.fresh"), format: (v, r) => (present(v) ? `${fmt(v, 0)} (${num(r.fresh_snow_days, 0)} d)` : "–") }] : []),
  ];
  const incomplete = p.incomplete_years || [];
  return html`<div class="me-card">
    ${record &&
    html`<div class="me-toolbar">
      <${YearRange} first=${record.first} last=${record.last} from=${data.first_year} to=${data.last_year} label=${t("meteo.snow.winters")} onApply=${onRange} />
    </div>`}
    <${Section} title=${title} info=${info} guide="metody-snieg" states=${[state]}>
      <${Source} station=${station} doc=${state.data} variable="snow_cover" />
      <${Notices} states=${[state]} />
      <${Figures}
        items=${[
          { label: t("meteo.snow.cover_days"), value: num(p.mean_cover_days, 0), note: tn("meteo.snow.per_winter", p.n_years) },
          { label: t("meteo.snow.mean_max"), value: num(p.mean_max_depth_cm, 0, "cm"), note: t("meteo.temperature.on_average") },
          { label: t("meteo.snow.record"), value: num(p.max_depth_cm, 0, "cm"), note: p.max_date ? date(p.max_date) : "" },
          {
            label: t("meteo.snow.first_last"),
            value: `${monthDay(p.median_first_day)} · ${monthDay(p.median_last_day)}`,
            note: t("meteo.snow.first_last_note", { earliest: date(p.earliest_first_date), latest: date(p.latest_last_date) }),
          },
          ...(fresh ? [{ label: t("meteo.snow.fresh"), value: num(p.mean_fresh_snow_cm, 0, "cm"), note: t("meteo.snow.fresh_note", { days: num(p.mean_fresh_snow_days, 0) }) }] : []),
        ]}
      />
      <${Option} label=${t("meteo.common.chart")}>
        <${Seg}
          value=${view}
          label=${t("meteo.snow.chart_label")}
          options=${[
            ["days", t("meteo.snow.view_days")],
            ["max", t("meteo.snow.view_max")],
          ]}
          onChange=${setView}
        />
      </${Option}>
      <${Chart} spec=${spec} />
      <h4 class="me-sub">${t("meteo.snow.months_table")}</h4>
      <${Table}
        columns=${WINTER_MONTHS.map((m) => ({ key: `m${m}`, label: ROMAN[m - 1], format: (v) => num(v, 1) }))}
        rows=${[Object.fromEntries(WINTER_MONTHS.map((m) => [`m${m}`, months.has(m) ? months.get(m) : null]))]}
        className="tbl me-wide"
      />
      <h4 class="me-sub">${t("meteo.snow.seasons_table")}</h4>
      <${Table} columns=${columns} rows=${newestFirst(data.years)} max=${10} />
      ${p.years_without_cover ? html`<p class="muted me-caption">${t("meteo.snow.no_cover", { count: p.years_without_cover })}</p>` : null}
      ${incomplete.length ? html`<p class="muted me-caption">${t("meteo.snow.incomplete", { seasons: incomplete.map(season).join(", ") })}</p>` : null}
    </${Section}>
  </div>`;
}
