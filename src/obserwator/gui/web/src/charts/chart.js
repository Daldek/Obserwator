/**
 * `Chart`: the Preact component of a chart (plan, "Interfaces fixed by this plan").
 *
 * ```js
 * html`<${Chart} spec=${{x: {label, scale}, y: {label}, y2, series: [{id, kind, data, axis, cls, label}],
 *                        marks, legend, readout}} svgRef=${ref} />`
 * ```
 *
 * The spec:
 * - `x`: `{label, scale: "linear" | "log" | "time" | "date" | "datetime" | "gumbel", min, max,
 *   domain, digits, short, tickList}`; `time` takes minutes and labels hours; `date`
 *   (Obserwator's mockup) takes day numbers (days since 1970-01-01, `dayNumber` of lib.js) and
 *   labels years, months or days by the plot's width, its readout dd.mm.rrrr; `datetime` takes
 *   fractional day numbers of UTC instants (`hourNumber` of lib.js: the hours of an hourly
 *   series) and labels the reader's local hours or days, or months and years, its readout the
 *   local date and time; `gumbel` takes the exceedance probability [%]
 *   (`domain: [99, 0.1]` fixes its ends) and labels p and T = 100 / p. `tickList: [{value,
 *   label, sub}]` replaces the computed ticks (those within the domain are drawn).
 * - `y`: `{label, unit, scale: "linear" | "log" | "band", min, max, zero, pad, ticks, digits}`;
 *   `band` draws one horizontal bar per point (`{x: value, y: name, sub, cls, text}`). A linear
 *   axis covers negative values (`zero: false` for one that need not include 0).
 * - `y2`: the same as `y` for a panel above the main one, sharing the x axis, whose bars
 *   hang from its top (the hyetograph above the hydrograph); `share` is its part of the height.
 * - `series`: `{id, kind: "line" | "step" | "area" | "band" | "bars" | "points" | "rug", data:
 *   [[x, y], …] (or `{x, y, cls}`; a `rug` takes x values only: short ticks on the x axis; a
 *   `band` takes `[x, lo, hi]` or `{x, lo, hi}`: the fill between, a min–max envelope), axis:
 *   "y" | "y2", cls: "s1"…"s6" | "bar-p" | "bar-pe" | …, label, unit, digits, width, align,
 *   readout, legend}`.
 * - `marks`: `{kind: "peak", x, y, label, cls, guides: "x" | "xy"}`, `{kind: "hline", y, label}`,
 *   `{kind: "vline", x, from, to, extend, label}`, `{kind: "note", x, y, label, dx, dy, anchor}`;
 *   `axis: "y2"` puts a mark on the upper panel.
 * - `legend`: `true` (the labelled series) or items `{label, kind, cls}` (`kind: "text"` a note,
 *   `"stroke"` a line styled as the curves are: its classes' colour and dashes, `"break"` the
 *   start of a new line of the legend).
 * - `readout`: `true` or `{series, x: (x) => text, value: (value, series) => text}`: a cursor
 *   by pointer and by keys (arrows, Shift or Page for ten steps, Home, End, Esc).
 * - `zoom`: whether a range of x can be shown (`true` by default on a `date` axis; a
 *   linear, log or time axis with `true`): a mouse drag over the plot chooses the range,
 *   `+` and `−` halve and double it, the readout's arrows move it past its edge, `0`, a
 *   double click or the button under the chart show the whole again. A long line, step,
 *   area or band is decimated to its first, last, lowest and highest point per column of
 *   the plot (`thinPoints` of series.js) within the range shown.
 * - `size`: "wide" (760 × 432, the default), "small" (360 × 178) or `{width, height}`;
 *   `fit: {ratio, minHeight}` draws the chart at its container's width instead (so its text
 *   keeps its CSS size; below 500 px the small layout), `ratio` times it high, at least
 *   `minHeight`, again when the width changes; `size` stays the fallback without a width.
 *   `title` (the aria-label) or `labelledBy` (an element's id).
 *
 * The drawing itself is `drawChart` (DOM only); this component mounts it and
 * redraws when `spec` changes. `svgRef.current` is the SVG (for `toPng`).
 *
 * `ChartBadge` gives every chart under it a badge above its plot, which the station panel's
 * tables carry too (`BadgeLine`, sections/common.js `Table`): the station panel names the
 * class of a station of another source there (hydromet P11), so a screenshot of any chart or
 * table keeps it.
 */

import htm from "../../vendor/htm/htm.mjs";
import { createContext, h } from "../../vendor/preact/preact.mjs";
import { useContext, useEffect, useRef } from "../../vendor/preact/hooks.mjs";
import { drawChart } from "./draw.js";

const html = htm.bind(h);

/** The text of the badge of every chart and table under it; null (the default) for none. */
export const ChartBadge = createContext(null);

/** The badge above a chart or a table (`ChartBadge`), nothing without one. */
export function BadgeLine() {
  const text = useContext(ChartBadge);
  return text ? html`<p class="data-badge"><span class="chip" data-part="class-badge">${text}</span></p>` : null;
}

/**
 * A chart drawn from a spec, under its badge where `ChartBadge` gives one.
 *
 * @param {{spec: object, svgRef?: {current: SVGSVGElement | null}, class?: string}} props
 * @returns {import("../../vendor/preact/preact.mjs").VNode}
 */
export function Chart({ spec, svgRef, class: extra }) {
  const host = useRef(null);
  const handle = useRef(null);

  useEffect(() => {
    handle.current = drawChart(host.current, spec);
    if (svgRef) svgRef.current = handle.current.svg;
    return () => {
      handle.current.destroy();
      handle.current = null;
      if (svgRef) svgRef.current = null;
    };
  }, []);

  useEffect(() => {
    if (handle.current) handle.current.update(spec);
  }, [spec]);

  // The badge is the chart's sibling, so the element drawChart fills stays the same when
  // the badge comes or goes
  return html`<${BadgeLine} /><div class=${extra ? `chart ${extra}` : "chart"} ref=${host}></div>`;
}
