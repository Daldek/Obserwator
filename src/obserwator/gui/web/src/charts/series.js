/**
 * Series and marks of a chart: path geometry (pure) and SVG elements.
 *
 * Series kinds: `line`, `step` (a value holds until the next point), `area`
 * (filled down to zero, with its line), `band` (filled between a low and a high value
 * at each x: a min–max envelope; a non-finite end breaks it), `bars` (vertical; on the `y2` panel
 * they hang from its top: the hyetograph), `points` (the empirical points of
 * a probability plot), `rug` (short ticks on the x axis at x values, without
 * a y and without a readout value) and, on a band y axis, horizontal bars (one
 * category per point, `{x: value, y: name, sub, cls, text}`). A series' `cls`
 * (`s1` to `s6`, `bar-p`, `bar-pe`, `best`, …) picks its colour in `css/charts.css`.
 * Marks: `peak` (a dot, a guide to the axis and a boxed label), `hline` (a
 * reference value across the plot), `vline` (a moment, with a note) and
 * `note` (a text at a point).
 */

import { barWidth, points } from "./axes.js";
import { c1, svgEl, textEl } from "./svg.js";

/** The default colour classes, by the series' order. */
export const SERIES_CLASSES = ["s1", "s2", "s3", "s4", "s5", "s6"];

/**
 * A polyline's `d`: "M x,y L x,y …"; a non-finite point starts a new subpath.
 *
 * @param {[number, number][]} xy points in viewBox units
 * @returns {string}
 */
export function linePath(xy) {
  let d = "";
  let pen = false;
  for (const [x, y] of xy) {
    if (!Number.isFinite(x) || !Number.isFinite(y)) {
      pen = false;
      continue;
    }
    d += `${pen ? "L" : "M"}${c1(x)},${c1(y)}`;
    pen = true;
  }
  return d;
}

/**
 * A step line (each value holds until the next point; the last one ends there).
 *
 * @param {[number, number][]} xy points in viewBox units
 * @returns {[number, number][]} the corners
 */
export function stepPoints(xy) {
  const out = [];
  xy.forEach(([x, y], index) => {
    if (index > 0) out.push([x, xy[index - 1][1]]);
    out.push([x, y]);
  });
  return out;
}

/**
 * A filled area between a line and a baseline: "M…Z" for each finite run.
 *
 * @param {[number, number][]} xy points in viewBox units
 * @param {number} base the baseline's y
 * @returns {string}
 */
export function areaPath(xy, base) {
  const runs = [];
  let run = [];
  for (const point of xy) {
    if (Number.isFinite(point[0]) && Number.isFinite(point[1])) run.push(point);
    else if (run.length) {
      runs.push(run);
      run = [];
    }
  }
  if (run.length) runs.push(run);
  return runs
    .map((part) => `${linePath([[part[0][0], base], ...part, [part.at(-1)[0], base]])}Z`)
    .join("");
}

/**
 * A filled band between two lines: "M…Z" for each run where both ends are finite, along
 * the high line forwards and the low line back.
 *
 * @param {number[]} px the x of each point in viewBox units
 * @param {number[]} hi the y of the high ends
 * @param {number[]} lo the y of the low ends
 * @returns {string}
 */
export function bandPath(px, hi, lo) {
  const runs = [];
  let run = [];
  px.forEach((x, at) => {
    if (Number.isFinite(x) && Number.isFinite(hi[at]) && Number.isFinite(lo[at])) run.push(at);
    else if (run.length) {
      runs.push(run);
      run = [];
    }
  });
  if (run.length) runs.push(run);
  return runs
    .map((part) => {
      const top = part.map((at) => [px[at], hi[at]]);
      const bottom = [...part].reverse().map((at) => [px[at], lo[at]]);
      return `${linePath([...top, ...bottom])}Z`;
    })
    .join("");
}

/**
 * Value of a series at an x coordinate of the viewBox: linear between points
 * (lines, areas), the last value before it (steps), the bar that contains it
 * (bars), the nearest point within `snap` (points); a rug has none.
 *
 * @param {{kind: string, px: number[], values: number[], spans?: [number, number][]}} geometry
 *   a series' points in viewBox x (`px`, increasing) and their values
 * @param {number} at an x of the viewBox
 * @param {number} [snap=6] how far a point of a `points` series may be
 * @returns {number | null} the value, or null outside the series
 */
export function valueAt(geometry, at, snap = 6) {
  const { kind, px, values, spans } = geometry;
  if (!px.length || kind === "rug") return null;
  if (kind === "bars") {
    const index = spans.findIndex(([a, b]) => at >= a - 1e-6 && at < b - 1e-6);
    return index < 0 ? null : values[index];
  }
  if (kind === "points") {
    let best = -1;
    for (let i = 0; i < px.length; i += 1) {
      if (Math.abs(px[i] - at) <= snap && (best < 0 || Math.abs(px[i] - at) < Math.abs(px[best] - at))) best = i;
    }
    return best < 0 ? null : values[best];
  }
  if (at < px[0] - 1e-6 || at > px.at(-1) + 1e-6) return null;
  const hi = px.findIndex((x) => x >= at - 1e-6);
  if (Math.abs(px[hi] - at) <= 1e-6) return values[hi];
  const lo = hi - 1;
  if (kind === "step") return values[lo];
  const share = (at - px[lo]) / (px[hi] - px[lo]);
  return values[lo] + share * (values[hi] - values[lo]);
}

/** The value of a point for `thinPoints` by default: its y. */
const yOf = (point) => point.y;

/**
 * The points of a long line, area, step or band drawn (drawing only; the tables and
 * exports keep every value): with more than four points per column of the plot, each
 * column keeps its first, last, lowest and highest point and its first gap, so the drawn
 * line and its peaks look the same with a few thousand points instead of a hundred
 * thousand (a ČHMÚ daily series since 1775 has about 90,000 values).
 *
 * @param {{x: number, y?: number}[]} points the points in increasing x
 * @param {(x: number) => number} place the x scale (to viewBox units)
 * @param {number} columns the plot's width in viewBox units
 * @param {{low?: (point: object) => number, high?: (point: object) => number}} [values]
 *   the low and the high value of a point (both its `y` by default; a band's `lo` and
 *   `hi`); a point either of which is not finite is a gap
 * @returns {object[]} the points kept, in their order
 */
export function thinPoints(points, place, columns, values = {}) {
  if (points.length <= 4 * columns) return points;
  const lowOf = values.low ?? yOf;
  const highOf = values.high ?? yOf;
  const start = place(points[0].x);
  const width = place(points.at(-1).x) - start || 1;
  const out = [];
  let column = -1;
  let first = -1;
  let last = -1;
  let low = -1;
  let high = -1;
  let gap = -1;
  let lowest = 0;
  let highest = 0;
  const kept = [0, 0, 0, 0, 0];
  const flush = () => {
    let count = 0;
    for (const index of [first, low, high, gap, last]) if (index >= 0) kept[count++] = index;
    const row = kept.slice(0, count).sort((a, b) => a - b);
    for (let at = 0; at < count; at += 1) if (at === 0 || row[at] !== row[at - 1]) out.push(points[row[at]]);
  };
  for (let index = 0; index < points.length; index += 1) {
    const point = points[index];
    const at = Math.min(columns - 1, Math.floor(((place(point.x) - start) / width) * columns));
    if (at !== column) {
      if (column >= 0) flush();
      column = at;
      first = index;
      low = -1;
      high = -1;
      gap = -1;
    }
    last = index;
    const lo = lowOf(point);
    const hi = highOf(point);
    if (!Number.isFinite(lo) || !Number.isFinite(hi)) {
      if (gap < 0) gap = index;
      continue;
    }
    if (low < 0 || lo < lowest) {
      low = index;
      lowest = lo;
    }
    if (high < 0 || hi > highest) {
      high = index;
      highest = hi;
    }
  }
  flush();
  return out;
}

/**
 * The points of a series sorted by x (left to right on the plot) and cut to the plot's
 * width: the points within it and the nearest one beyond each edge, so a line leaves the
 * frame towards its next point (a zoomed chart draws and reads out only these).
 *
 * @param {object[]} data the series' points
 * @param {(x: number) => number} place the x scale (to viewBox units)
 * @param {{left: number, right: number}} plot the frame
 * @returns {object[]}
 */
export function visiblePoints(data, place, plot) {
  let ordered = data;
  let previous = -Infinity;
  for (const point of data) {
    const at = place(point.x);
    if (!Number.isFinite(at) || at < previous) {
      // Unordered or with points off the scale: placed once, sorted
      ordered = data
        .map((item) => ({ item, at: place(item.x) }))
        .filter((entry) => Number.isFinite(entry.at))
        .sort((a, b) => a.at - b.at)
        .map((entry) => entry.item);
      break;
    }
    previous = at;
  }
  let first = 0;
  while (first < ordered.length && place(ordered[first].x) < plot.left - 1e-6) first += 1;
  let last = ordered.length - 1;
  while (last >= 0 && place(ordered[last].x) > plot.right + 1e-6) last -= 1;
  const from = Math.max(0, first - 1);
  const to = Math.min(ordered.length - 1, last + 1);
  return from === 0 && to === ordered.length - 1 ? ordered : ordered.slice(from, to + 1);
}

/**
 * The geometry of each series of a layout: its viewBox points, values, class.
 *
 * @param {object} spec the chart spec
 * @param {ReturnType<import("./axes.js").chartLayout>} layout
 * @returns {object[]} per series: `{series, kind, cls, axis, px, py, values, spans, xs}`; a
 *   band's `py` and `values` are its high ends, `py2` and `lows` its low ends
 */
export function seriesGeometry(spec, layout) {
  let row = 0;
  return (spec.series ?? []).map((series, index) => {
    const kind = layout.band ? "hbars" : (series.kind ?? "line");
    const cls = series.cls ?? SERIES_CLASSES[index % SERIES_CLASSES.length];
    const data = points(series);
    if (kind === "hbars") {
      row += data.length;
      return { series, kind, cls, axis: "y", data, row: row - data.length, px: [], py: [], values: [], xs: [] };
    }
    const axis = series.axis === "y2" && layout.y2 ? layout.y2 : layout.y;
    const sorted = visiblePoints(data, layout.x.scale, layout.plot);
    const columns = Math.ceil(layout.plot.right - layout.plot.left);
    let order = sorted;
    if (kind === "line" || kind === "area" || kind === "step") order = thinPoints(sorted, layout.x.scale, columns);
    else if (kind === "band") order = thinPoints(sorted, layout.x.scale, columns, { low: (point) => point.lo, high: (point) => point.hi });
    const px = order.map((point) => layout.x.scale(point.x));
    const py = order.map((point) => (Number.isFinite(point.y) ? axis.scale(point.y) : NaN));
    if (kind === "band") {
      const place = (value) => (Number.isFinite(value) ? axis.scale(value) : NaN);
      return {
        series,
        kind,
        cls,
        axis: series.axis === "y2" && layout.y2 ? "y2" : "y",
        data: order,
        xs: order.map((point) => point.x),
        px,
        py: order.map((point) => place(point.hi)),
        py2: order.map((point) => place(point.lo)),
        values: order.map((point) => point.hi),
        lows: order.map((point) => point.lo),
      };
    }
    let spans;
    if (kind === "bars") {
      const width = barWidth(series, order);
      const shift = series.align === "center" ? width / 2 : 0;
      spans = order.map((point) => [
        layout.x.scale(point.x - shift),
        layout.x.scale(point.x - shift + width),
      ]);
    }
    return {
      series,
      kind,
      cls,
      axis: series.axis === "y2" && layout.y2 ? "y2" : "y",
      data: order,
      xs: order.map((point) => point.x),
      px,
      py,
      values: order.map((point) => point.y),
      spans,
    };
  });
}

function drawBars(geometry, layout) {
  const axis = geometry.axis === "y2" ? layout.y2 : layout.y;
  const zero = axis.scale(Math.max(axis.min, Math.min(axis.max, 0)));
  const rects = [];
  geometry.spans.forEach(([a, b], index) => {
    const value = geometry.values[index];
    if (!Number.isFinite(value) || value === 0) return;
    const at = axis.scale(value);
    const gap = b - a > 3 ? 0.5 : 0;
    rects.push(
      svgEl("rect", {
        x: a + gap,
        y: Math.min(at, zero),
        width: Math.max(0.5, b - a - 2 * gap),
        height: Math.abs(at - zero),
        class: geometry.data[index].cls,
      }),
    );
  });
  return svgEl("g", { class: `bars ${geometry.cls}`, "data-series": geometry.series.id }, rects);
}

function drawHorizontalBars(geometry, layout) {
  const { plot, x, y } = layout;
  const zero = x.scale(0);
  const offset = geometry.row;
  const group = svgEl("g", { class: `hbars ${geometry.cls}`, "data-series": geometry.series.id });
  geometry.data.forEach((point, index) => {
    const middle = plot.top + y.step * (offset + index + 0.5);
    const end = x.scale(point.x);
    group.append(
      svgEl("rect", {
        class: ["hbar", point.cls].filter(Boolean).join(" "),
        x: Math.min(zero, end),
        y: middle - y.bar / 2,
        width: Math.max(0.5, Math.abs(end - zero)),
        height: y.bar,
        rx: 3,
      }),
    );
    if (point.text) group.append(textEl("bar-val", Math.max(zero, end) + 8, middle + 4, point.text));
  });
  return group;
}

/**
 * Draw the series: areas and bands first, then bars, lines and points on top.
 *
 * @param {object[]} geometries from `seriesGeometry`
 * @param {ReturnType<import("./axes.js").chartLayout>} layout
 * @returns {SVGElement[]}
 */
export function drawSeries(geometries, layout) {
  const rank = { area: 0, band: 0, bars: 1, hbars: 1, step: 2, line: 2, points: 3, rug: 3 };
  const ordered = [...geometries].sort((a, b) => (rank[a.kind] ?? 2) - (rank[b.kind] ?? 2));
  const out = [];
  for (const geometry of ordered) {
    const { kind, cls, series } = geometry;
    const xy = geometry.px.map((x, i) => [x, geometry.py[i]]);
    if (kind === "bars") out.push(drawBars(geometry, layout));
    else if (kind === "band") {
      const d = bandPath(geometry.px, geometry.py, geometry.py2);
      out.push(svgEl("path", { class: `band ${cls}`, d, "data-series": series.id }));
    } else if (kind === "hbars") out.push(drawHorizontalBars(geometry, layout));
    else if (kind === "points") {
      const dots = xy
        .filter(([x, y]) => Number.isFinite(x) && Number.isFinite(y))
        .map(([x, y]) => svgEl("circle", { cx: x, cy: y, r: layout.small ? 3 : 3.6 }));
      // Points take a colour only from their own `cls` (plain dots otherwise: the empirical points)
      out.push(svgEl("g", { class: `emp ${series.cls ?? ""}`.trim(), "data-series": series.id }, dots));
    } else if (kind === "rug") {
      const { bottom } = geometry.axis === "y2" ? layout.upper : layout.main;
      const length = layout.small ? 6 : 8;
      const ticks = geometry.px
        .filter((x) => Number.isFinite(x))
        .map((x) => svgEl("line", { x1: x, x2: x, y1: bottom, y2: bottom - length }));
      out.push(svgEl("g", { class: `rug ${cls}`, "data-series": series.id }, ticks));
    } else {
      const path = kind === "step" ? stepPoints(xy) : xy;
      if (kind === "area") {
        const axis = geometry.axis === "y2" ? layout.y2 : layout.y;
        const base = axis.scale(Math.max(axis.min, Math.min(axis.max, 0)));
        out.push(svgEl("path", { class: `q-area ${cls}`, d: areaPath(path, base), "data-series": series.id }));
      }
      out.push(svgEl("path", { class: `ser ${cls}`, d: linePath(path), "data-series": series.id }));
    }
  }
  return out;
}

/** An estimate of a text's width in viewBox units, corrected after drawing (`fitBoxes`). */
function textWidth(text, size = 12) {
  return String(text).length * size * 0.56;
}

/**
 * Baselines of the labels of reference lines at the plot's right edge, kept apart: from the
 * top down each label sits just above its line, else just below it, else `gap` under the
 * label before (the lines stay at their values; only their labels move).
 *
 * @param {number[]} lines the lines' y in viewBox units
 * @param {number} [gap=12] the least distance between two baselines
 * @returns {number[]} the baseline of each line's label, in the order of `lines`
 */
export function spreadLabels(lines, gap = 12) {
  const order = lines.map((py, at) => ({ py, at })).sort((a, b) => a.py - b.py);
  const out = new Array(lines.length);
  let previous = -Infinity;
  for (const { py, at } of order) {
    const above = py - 4;
    const below = py + gap - 1;
    let place = above;
    if (above - previous < gap) place = below - previous >= gap ? below : previous + gap;
    out[at] = place;
    previous = place;
  }
  return out;
}

/**
 * Draw the marks.
 *
 * @param {object[]} marks the spec's `marks`
 * @param {ReturnType<import("./axes.js").chartLayout>} layout
 * @returns {SVGElement[]}
 */
export function drawMarks(marks, layout) {
  const { plot, main, upper, x } = layout;
  const out = [];
  // The labels of the reference lines of each panel, spread apart
  const tags = new Map();
  for (const panelAxis of ["y", "y2"]) {
    const labelled = (marks ?? []).filter(
      (mark) => mark.kind === "hline" && mark.label && (mark.axis === "y2" && layout.y2 ? "y2" : "y") === panelAxis,
    );
    const axis = panelAxis === "y2" ? layout.y2 : layout.y;
    // A bold label of the small text with its halo: 13 viewBox units (11 on a small chart)
    const places = spreadLabels(labelled.map((mark) => axis.scale(mark.y)), layout.small ? 11 : 13);
    labelled.forEach((mark, at) => tags.set(mark, places[at]));
  }
  for (const mark of marks ?? []) {
    const axis = mark.axis === "y2" && layout.y2 ? layout.y2 : layout.y;
    const panel = mark.axis === "y2" && upper ? upper : main;
    const cls = mark.cls ?? "s1";
    if (mark.kind === "peak") {
      const px = x.scale(mark.x);
      const py = axis.scale(mark.y);
      const group = svgEl("g", { class: "mark peak", "data-mark": mark.id });
      group.append(svgEl("line", { class: "peak-line", x1: px, x2: px, y1: py, y2: panel.bottom }));
      if (mark.guides === "xy") group.append(svgEl("line", { class: "peak-line", x1: plot.left, x2: px, y1: py, y2: py }));
      group.append(svgEl("circle", { class: `peak-dot ${cls}`, cx: px, cy: py, r: layout.small ? 3.5 : 4.5 }));
      if (mark.label) {
        if (layout.small) {
          const right = px > plot.left + (plot.right - plot.left) * 0.66;
          group.append(textEl("peak-tag", right ? px - 7 : px + 7, py - 5, mark.label, right ? "end" : undefined));
        } else {
          const width = textWidth(mark.label) + 16;
          const left = px + 12 + width > plot.right ? px - 12 - width : px + 12;
          const box = svgEl("rect", { class: "peak-box", x: left, y: py - 15, width, height: 22, rx: 4 });
          const text = textEl("peak-label", left + 8, py, mark.label);
          group.append(box, text);
        }
      }
      out.push(group);
    } else if (mark.kind === "hline") {
      const py = axis.scale(mark.y);
      const group = svgEl("g", { class: `mark hline ${mark.cls ?? ""}`.trim(), "data-mark": mark.id });
      group.append(svgEl("line", { class: "peak-line ref", x1: plot.left, x2: plot.right, y1: py, y2: py }));
      if (mark.label) group.append(textEl("peak-tag", plot.right - 2, tags.get(mark) ?? py - 4, mark.label, "end"));
      out.push(group);
    } else if (mark.kind === "vline") {
      const px = x.scale(mark.x);
      const from = Number.isFinite(mark.from) ? axis.scale(mark.from) : panel.top;
      const to = Number.isFinite(mark.to) ? axis.scale(mark.to) : panel.bottom;
      const group = svgEl("g", { class: "mark vline", "data-mark": mark.id });
      group.append(svgEl("line", { class: "mark-line", x1: px, x2: px, y1: from, y2: to + (mark.extend ?? 0) }));
      if (mark.label) group.append(textEl("note", px + 5, to + (mark.extend ?? 0) - 2, mark.label));
      out.push(group);
    } else if (mark.kind === "note") {
      const px = x.scale(mark.x);
      const py = axis.scale(mark.y);
      out.push(textEl(mark.cls ?? "note", px + (mark.dx ?? 0), py + (mark.dy ?? 0), mark.label, mark.anchor));
    }
  }
  return out;
}

/**
 * Fit the boxes of the peak labels to their measured texts (an attached SVG only).
 *
 * @param {SVGSVGElement} svg the drawn chart
 * @param {{right: number}} plot the plot area
 */
export function fitBoxes(svg, plot) {
  if (!svg.isConnected) return;
  for (const group of svg.querySelectorAll("g.mark.peak")) {
    const box = group.querySelector(".peak-box");
    const text = group.querySelector(".peak-label");
    const dot = group.querySelector(".peak-dot");
    if (!box || !text || !dot) continue;
    let width;
    try {
      width = text.getComputedTextLength() + 16;
    } catch {
      continue;
    }
    if (!(width > 16)) continue;
    const px = Number(dot.getAttribute("cx"));
    const left = px + 12 + width > plot.right ? px - 12 - width : px + 12;
    box.setAttribute("x", String(c1(left)));
    box.setAttribute("width", String(c1(width)));
    text.setAttribute("x", String(c1(left + 8)));
  }
}
