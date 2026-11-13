/**
 * Drawing a chart into a container with the DOM only (no Preact), so a kit
 * component can wrap it as `Chart` does (plan D9, D12).
 *
 * `drawChart(container, spec)` builds the SVG, the legend and the readout and
 * returns a handle: `update(spec)` redraws in place (the readout keeps its
 * position), `readout.show(index)` and `readout.hide()` move it, `zoom.set(min, max)` and
 * `zoom.reset()` change the x range shown, `destroy()` empties the container. The theme
 * switch needs no redraw: colours are classes; the language switch draws it again (its
 * ticks and words are the page's language).
 *
 * Zoom (a `date` x axis by default, `zoom: true` for a linear, log or time one, `zoom:
 * false` for none): drag over the plot with a mouse to show that range, keys `+` and `−`
 * halve and double it around the readout (or the middle), the readout's arrows move the
 * range when they pass its edge, `0`, a double click or the button under the chart show
 * the whole again.
 */

import { onLangChange } from "../i18n.js";
import { chartLayout, drawAxes, drawGrid } from "./axes.js";
import { keysHint, probabilityHeading, zoomRangeText, zoomResetLabel } from "./labels.js";
import { formatDay, formatNumber, formatTime } from "./scale.js";
import { drawMarks, drawSeries, fitBoxes, seriesGeometry, valueAt } from "./series.js";
import { c1, htmlEl, svgEl, textEl } from "./svg.js";

/**
 * Format a readout value: the axis's `digits`, otherwise by magnitude.
 *
 * @param {number} value
 * @param {number} [digits]
 * @returns {string}
 */
export function readoutNumber(value, digits) {
  if (digits !== undefined) return formatNumber(value, digits);
  const size = Math.abs(value);
  return formatNumber(value, size >= 1000 ? 0 : size >= 100 ? 1 : size >= 1 || size === 0 ? 2 : 3);
}

/**
 * An x value as the readout and the zoom's range show it.
 *
 * @param {object} spec the chart spec
 * @param {string} type the x scale's type
 * @param {number} x the value
 * @returns {string}
 */
function xText(spec, type, x) {
  if (spec.x?.scale === "time") return formatTime(x);
  if (spec.x?.scale === "date") return formatDay(x);
  if (type === "gumbel") return readoutNumber(x, x >= 1 ? 1 : 2);
  return readoutNumber(x, spec.x?.digits);
}

function headingText(layout, x, spec) {
  const custom = spec.readout?.x;
  if (typeof custom === "function") return custom(x);
  const type = layout.x.scale.type;
  if (spec.x?.scale === "time") return `t = ${formatTime(x)}`;
  if (spec.x?.scale === "date") return formatDay(x);
  if (type === "gumbel") {
    const years = 100 / x;
    return probabilityHeading(readoutNumber(x, x >= 1 ? 1 : 2), readoutNumber(years, years >= 10 ? 0 : 1));
  }
  return `${spec.x?.short ?? "x"} = ${xText(spec, type, x)}`;
}

/**
 * The lines of the readout at an index of the master series.
 *
 * @param {object} spec the chart spec
 * @param {ReturnType<typeof chartLayout>} layout
 * @param {object[]} geometries from `seriesGeometry`
 * @param {object} master the geometry the readout steps over
 * @param {number} index an index of the master's points
 * @returns {{heading: string, at: number, rows: {id: string, cls: string, text: string, py: number | null}[]}}
 */
export function readoutAt(spec, layout, geometries, master, index) {
  const at = master.kind === "bars" ? (master.spans[index][0] + master.spans[index][1]) / 2 : master.px[index];
  const x = master.xs[index];
  const rows = [];
  const where = master.kind === "bars" ? master.spans[index][0] : at;
  for (const geometry of geometries) {
    if (geometry.series.readout === false) continue;
    const axisSpec = geometry.axis === "y2" ? layout.y2 : layout.y;
    const format = spec.readout?.value;
    const text = (value) =>
      typeof format === "function"
        ? format(value, geometry.series)
        : readoutNumber(value, geometry.series.digits ?? axisSpec.digits);
    const unit = geometry.series.unit ?? axisSpec.unit;
    const label = geometry.series.label ?? geometry.series.id;
    const suffix = unit ? `\u00a0${unit}` : "";
    if (geometry.kind === "band") {
      // A band reads as its two ends: "min–maks: 12–40 cm"
      const high = geometry === master ? geometry.values[index] : valueAt(geometry, where);
      const low = geometry === master ? geometry.lows[index] : valueAt({ ...geometry, values: geometry.lows }, where);
      if (low === null || high === null || !Number.isFinite(low) || !Number.isFinite(high)) continue;
      rows.push({ id: geometry.series.id, cls: geometry.cls, kind: "band", text: `${label}: ${text(low)}–${text(high)}${suffix}`, py: null });
      continue;
    }
    const value = geometry === master ? master.values[index] : valueAt(geometry, where);
    if (value === null || !Number.isFinite(value)) continue;
    rows.push({
      id: geometry.series.id,
      cls: geometry.cls,
      kind: geometry.kind,
      text: `${label}: ${text(value)}${suffix}`,
      py: geometry.kind === "bars" ? null : axisSpec.scale(value),
    });
  }
  return { heading: headingText(layout, x, spec), at, rows };
}

function pickMaster(spec, geometries) {
  const wanted = spec.readout?.series;
  const usable = geometries.filter((geometry) => geometry.px.length && geometry.kind !== "hbars");
  if (wanted) return usable.find((geometry) => geometry.series.id === wanted) ?? null;
  return (
    usable.find((geometry) => geometry.kind !== "bars" && geometry.kind !== "band") ??
    usable.find((geometry) => geometry.kind === "band") ??
    usable[0] ??
    null
  );
}

function legendItems(spec, geometries) {
  if (Array.isArray(spec.legend)) return spec.legend;
  return geometries
    .filter((geometry) => geometry.series.label && geometry.series.legend !== false)
    .map((geometry) => ({ label: geometry.series.label, kind: geometry.kind, cls: geometry.kind === "points" ? geometry.series.cls : geometry.cls }));
}

function swatch(item) {
  if (item.kind === "bars" || item.kind === "hbars" || item.kind === "box") return htmlEl("i", { class: `sw ${item.cls ?? ""}`.trim() });
  if (item.kind === "band") return htmlEl("i", { class: `sw band ${item.cls ?? "s1"}` });
  if (item.kind === "points") return htmlEl("i", { class: `sw-dot ${item.cls ?? ""}`.trim() });
  if (item.kind === "rug") return htmlEl("i", { class: "sw-rug" });
  if (item.kind === "stroke") {
    const line = svgEl("line", { x1: 1, y1: 3, x2: 23, y2: 3 });
    return svgEl("svg", { class: `sw-stroke ${item.cls ?? ""}`.trim(), viewBox: "0 0 24 6", "aria-hidden": "true" }, [line]);
  }
  return htmlEl("i", { class: `sw-line ${item.cls ?? "s1"}` });
}

function drawLegend(spec, geometries) {
  const items = legendItems(spec, geometries);
  const legend = htmlEl("div", { class: "chart-legend" });
  for (const item of items) {
    if (item.kind === "text") legend.append(htmlEl("span", { class: "muted" }, [item.label]));
    else if (item.kind === "break") legend.append(htmlEl("span", { class: "legend-break", "aria-hidden": "true" }));
    else legend.append(htmlEl("span", {}, [swatch(item), item.label]));
  }
  return legend;
}

/** The ids of the frames' clip paths: one per chart, unique on the page. */
let clips = 0;

/** How far a series may spill over the frame [viewBox units]: a line or a point on an edge keeps its whole stroke. */
const SPILL = 4;

/**
 * The series of a chart cut at its frame: below an axis that starts at 0 (`niceDomain`),
 * above a fixed maximum, beyond a fixed end of the x axis.
 *
 * @param {string} id the id of the frame's clip path
 * @param {{left: number, right: number, top: number, bottom: number}} plot the frame
 * @param {SVGElement[]} nodes the drawn series
 * @returns {SVGElement[]} the clip path and the series within it
 */
function framed(id, plot, nodes) {
  const rect = svgEl("rect", {
    x: plot.left - SPILL,
    y: plot.top - SPILL,
    width: plot.right - plot.left + 2 * SPILL,
    height: plot.bottom - plot.top + 2 * SPILL,
  });
  return [svgEl("defs", {}, [svgEl("clipPath", { id }, [rect])]), svgEl("g", { class: "framed", "clip-path": `url(#${id})` }, nodes)];
}

/**
 * The first and the last index of the master's points within the frame's width (its points
 * are in the order of x), null when none is: the readout steps over these only.
 *
 * @param {object} master the geometry the readout steps over
 * @param {{left: number, right: number}} plot the frame
 * @returns {{first: number, last: number} | null}
 */
function withinFrame(master, plot) {
  let first = -1;
  let last = -1;
  master.px.forEach((x, at) => {
    const middle = master.kind === "bars" ? (master.spans[at][0] + master.spans[at][1]) / 2 : x;
    if (middle < plot.left - 0.5 || middle > plot.right + 0.5) return;
    if (first < 0) first = at;
    last = at;
  });
  return first < 0 ? null : { first, last };
}

/** The x scales a range of which can be shown (zoom); a probability axis keeps its own. */
const ZOOM_SCALES = new Set(["date", "linear", "log", "time"]);

/** Whether a chart zooms: a `date` x axis unless `zoom: false`, the other x scales with `zoom: true`. */
function zoomable(spec) {
  const kind = spec.x?.scale ?? "linear";
  if (spec.y?.scale === "band" || !ZOOM_SCALES.has(kind)) return false;
  return spec.zoom ?? kind === "date";
}

/** Whether two specs draw the same data on the same x axis (a zoom outlives a redraw of the same data). */
function sameData(a, b) {
  if (a.x?.scale !== b.x?.scale || a.x?.min !== b.x?.min || a.x?.max !== b.x?.max) return false;
  const left = a.series ?? [];
  const right = b.series ?? [];
  return left.length === right.length && left.every((series, at) => series.data === right[at].data);
}

/** The least distance a drag must cover to choose a range [viewBox units]. */
const DRAG = 6;

/**
 * Draw a chart into a container.
 *
 * @param {HTMLElement} container it gets the class `chart` (and `wide` for a wide chart)
 * @param {object} spec the chart spec (see `chart.js`)
 * @returns {{
 *   svg: SVGSVGElement, update: (spec: object) => void, destroy: () => void,
 *   readout: {show: (index: number) => void, hide: () => void, index: () => number | null},
 *   zoom: {set: (min: number, max: number) => void, reset: () => void, range: () => {min: number, max: number} | null}
 * }}
 */
export function drawChart(container, spec) {
  container.classList.add("chart");
  const svg = svgEl("svg", { class: "chart-svg", role: "img", focusable: "false" });
  const zoomText = htmlEl("span", { class: "chart-zoom-range" });
  const zoomButton = htmlEl("button", { type: "button", class: "btn sm chart-zoom-reset" });
  const zoomBar = htmlEl("div", { class: "chart-zoom", hidden: "" }, [zoomText, zoomButton]);
  const legendSlot = htmlEl("div", { class: "chart-legend-slot" });
  const live = htmlEl("div", { class: "chart-sr", "aria-live": "polite" });
  container.append(svg, zoomBar, legendSlot, live);
  clips += 1;
  const clipId = `chart-frame-${clips}`;

  let current = spec;
  let layout;
  let geometries;
  let master = null;
  let shown = null;
  let index = null;
  let layer = null;
  // The container's width a fitted chart is drawn for [CSS px]; 0 before it has one
  let width = 0;
  // The x range shown (null: the whole), the whole x domain, the selection being dragged
  let view = null;
  let whole = null;
  let drag = null;
  const selection = svgEl("rect", { class: "zoom-selection", visibility: "hidden" });

  /**
   * The spec as drawn: a fitted one (`fit`) takes the container's width as its viewBox's,
   * so its text keeps its CSS size at every width, and `ratio` times it, at least
   * `minHeight`, as its height; without a width it keeps its `size`. A zoomed one shows
   * its range of x.
   */
  function drawn(next) {
    let out = next;
    if (next.fit && width) {
      out = { ...out, size: { width, height: Math.max(next.fit.minHeight ?? 0, Math.round(width * next.fit.ratio)) } };
    }
    if (view) out = { ...out, x: { ...out.x, min: view.min, max: view.max } };
    return out;
  }

  function hide() {
    layer?.replaceChildren();
    layer?.setAttribute("visibility", "hidden");
    live.textContent = "";
  }

  function show(next) {
    if (!master || !layer) return;
    index = Math.max(shown.first, Math.min(shown.last, next));
    const reading = readoutAt(current, layout, geometries, master, index);
    const { plot } = layout;
    const top = layout.upper ? layout.upper.top : layout.main.top;
    layer.replaceChildren();
    layer.removeAttribute("visibility");
    layer.append(svgEl("line", { class: "readout-line", x1: reading.at, x2: reading.at, y1: top, y2: plot.bottom }));
    for (const row of reading.rows) {
      if (row.py === null) continue;
      layer.append(svgEl("circle", { class: `readout-dot ${row.cls}`, cx: reading.at, cy: row.py, r: 3.5 }));
    }
    const lines = [reading.heading, ...reading.rows.map((row) => row.text)];
    const size = layout.small ? 10 : 11;
    const lineHeight = size + 4;
    const width = Math.max(...lines.map((line) => line.length)) * size * 0.56 + 16;
    const height = lines.length * lineHeight + 8;
    // Right of the cursor when it fits, else left of it, never past the chart's left edge
    const right = reading.at + 10 + width <= plot.right;
    const left = right ? reading.at + 10 : Math.max(0, reading.at - 10 - width);
    const boxTop = top + 4;
    layer.append(svgEl("rect", { class: "readout-box", x: left, y: boxTop, width, height, rx: 4 }));
    lines.forEach((line, row) => {
      layer.append(textEl(row === 0 ? "readout-head" : "readout-text", left + 8, boxTop + 4 + lineHeight * (row + 1) - 4, line));
    });
    if (svg.isConnected) {
      const texts = [...layer.querySelectorAll("text")];
      try {
        const measured = Math.max(...texts.map((text) => text.getComputedTextLength())) + 16;
        if (measured > 16) {
          const box = layer.querySelector(".readout-box");
          const fitLeft = right ? reading.at + 10 : Math.max(0, reading.at - 10 - measured);
          box.setAttribute("width", String(c1(measured)));
          box.setAttribute("x", String(c1(fitLeft)));
          for (const text of texts) text.setAttribute("x", String(c1(fitLeft + 8)));
        }
      } catch {
        // an SVG without layout (display: none) keeps the estimate
      }
    }
    live.textContent = lines.join(" · ");
  }

  /** The marks within the x range shown (a zoomed chart leaves out those beyond it). */
  function marksShown() {
    const marks = current.marks ?? [];
    if (!view) return marks;
    const { left, right } = layout.plot;
    return marks.filter((mark) => {
      if (mark.kind === "hline" || !Number.isFinite(mark.x)) return true;
      const at = layout.x.scale(mark.x);
      return at >= left - 0.5 && at <= right + 0.5;
    });
  }

  function render(nextSpec) {
    current = nextSpec;
    const zoom = zoomable(current);
    if (!zoom) view = null;
    if (current.fit && !width) width = Math.floor(container.clientWidth);
    layout = chartLayout(drawn(current));
    if (!view) whole = { min: layout.x.min, max: layout.x.max };
    geometries = seriesGeometry(current, layout);
    master = current.readout && !layout.band ? pickMaster(current, geometries) : null;
    shown = master ? withinFrame(master, layout.plot) : null;
    if (!shown) master = null;
    container.classList.toggle("wide", !layout.small);
    container.classList.toggle("fit", Boolean(current.fit));
    container.classList.toggle("zoomable", zoom);
    svg.setAttribute("viewBox", `0 0 ${layout.width} ${layout.height}`);
    if (current.title) svg.setAttribute("aria-label", current.title);
    else svg.removeAttribute("aria-label");
    if (current.labelledBy) svg.setAttribute("aria-labelledby", current.labelledBy);
    else svg.removeAttribute("aria-labelledby");
    if (master || zoom) {
      svg.setAttribute("tabindex", "0");
      svg.setAttribute("aria-description", keysHint(zoom));
    } else {
      svg.removeAttribute("tabindex");
      svg.removeAttribute("aria-description");
    }
    layer = master ? svgEl("g", { class: "readout", visibility: "hidden" }) : null;
    svg.replaceChildren(
      ...drawGrid(layout),
      ...(layout.band ? drawSeries(geometries, layout) : framed(clipId, layout.plot, drawSeries(geometries, layout))),
      ...drawMarks(marksShown(), layout),
      ...drawAxes(layout),
      ...(zoom ? [selection] : []),
      ...(layer ? [layer] : []),
    );
    fitBoxes(svg, layout.plot);
    zoomBar.hidden = !view;
    if (view) {
      const type = layout.x.scale.type;
      zoomText.textContent = zoomRangeText(xText(current, type, view.min), xText(current, type, view.max));
    }
    zoomButton.textContent = zoomResetLabel();
    legendSlot.replaceChildren(...(current.legend ? [drawLegend(current, geometries)] : []));
    if (master && index !== null && document.activeElement === svg) show(index);
    else {
      if (!master || index === null || index < shown.first || index > shown.last) index = null;
      live.textContent = "";
    }
  }

  /** The index of the master's point within the frame nearest to an x value. */
  function indexOfX(value) {
    let best = shown.first;
    for (let at = shown.first; at <= shown.last; at += 1) {
      if (Math.abs(master.xs[at] - value) < Math.abs(master.xs[best] - value)) best = at;
    }
    return best;
  }

  /**
   * Show a range of x (clamped to the whole; the whole shows no range) and keep the
   * readout at the x it read.
   */
  function setView(min, max) {
    if (!whole || !(max > min)) return;
    const kept = master && index !== null ? master.xs[index] : null;
    const lo = Math.max(whole.min, min);
    const hi = Math.min(whole.max, max);
    view = lo <= whole.min && hi >= whole.max ? null : { min: lo, max: hi };
    index = null;
    render(current);
    if (master && kept !== null && document.activeElement === svg) show(indexOfX(kept));
    if (!master || index === null) live.textContent = zoomBar.hidden ? "" : zoomText.textContent;
  }

  /** Show the x range between two x coordinates of the viewBox. */
  function viewBetween(a, b) {
    const { scale } = layout.x;
    setView(scale.invert(Math.min(a, b)), scale.invert(Math.max(a, b)));
  }

  /** Zoom by a factor of the range's width (½ in, 2 out) around the readout or the middle. */
  function zoomBy(factor) {
    const { left, right } = layout.plot;
    if (factor < 1 && master && shown.last - shown.first < 4) return;
    const centre = master && index !== null ? master.px[index] : (left + right) / 2;
    const half = ((right - left) * factor) / 2;
    let a = centre - half;
    let b = centre + half;
    // Within the plot when zooming in, so the range stays where the reader looks
    if (factor < 1 && a < left) [a, b] = [left, left + 2 * half];
    if (factor < 1 && b > right) [a, b] = [right - 2 * half, right];
    // Within the whole when zooming out, so the range grows on the side that has room
    if (factor > 1) {
      const start = layout.x.scale(whole.min);
      const end = layout.x.scale(whole.max);
      if (b > end) [a, b] = [a - (b - end), end];
      if (a < start) [a, b] = [start, Math.min(end, b + (start - a))];
    }
    viewBetween(a, b);
  }

  /** Move the range shown by a share of its width (negative: left); false at the whole's end. */
  function pan(share) {
    if (!view) return false;
    const { scale } = layout.x;
    const { left, right } = layout.plot;
    let shift = (right - left) * share;
    const start = scale(whole.min);
    const end = scale(whole.max);
    if (left + shift < start) shift = start - left;
    if (right + shift > end) shift = end - right;
    if (Math.abs(shift) < 0.5) return false;
    const kept = view;
    setView(scale.invert(left + shift), scale.invert(right + shift));
    return view !== kept;
  }

  function svgX(clientX, clientY) {
    const matrix = svg.getScreenCTM();
    if (!matrix) return null;
    return new DOMPoint(clientX, clientY).matrixTransform(matrix.inverse()).x;
  }

  function nearest(clientX, clientY) {
    const x = svgX(clientX, clientY);
    if (x === null) return null;
    let best = shown.first;
    for (let at = shown.first; at <= shown.last; at += 1) {
      const middle = master.kind === "bars" ? (master.spans[at][0] + master.spans[at][1]) / 2 : master.px[at];
      const bestMiddle = master.kind === "bars" ? (master.spans[best][0] + master.spans[best][1]) / 2 : master.px[best];
      if (Math.abs(middle - x) < Math.abs(bestMiddle - x)) best = at;
    }
    return { index: best, x };
  }

  function onPointerMove(event) {
    if (drag) {
      const x = svgX(event.clientX, event.clientY);
      if (x === null) return;
      drag.to = Math.max(layout.plot.left, Math.min(layout.plot.right, x));
      if (Math.abs(drag.to - drag.from) < DRAG) return;
      hide();
      const { top, bottom } = layout.plot;
      selection.setAttribute("x", String(c1(Math.min(drag.from, drag.to))));
      selection.setAttribute("width", String(c1(Math.abs(drag.to - drag.from))));
      selection.setAttribute("y", String(c1(top)));
      selection.setAttribute("height", String(c1(bottom - top)));
      selection.removeAttribute("visibility");
      return;
    }
    if (!master) return;
    const found = nearest(event.clientX, event.clientY);
    if (!found || found.x < layout.plot.left - 8 || found.x > layout.plot.right + 8) {
      hide();
      return;
    }
    show(found.index);
  }

  function onPointerDown(event) {
    if (event.pointerType !== "mouse") {
      // A touch reads out where it lands; dragging scrolls the page
      onPointerMove(event);
      return;
    }
    if (event.button !== 0 || !zoomable(current)) return;
    const x = svgX(event.clientX, event.clientY);
    if (x === null || x < layout.plot.left || x > layout.plot.right) return;
    drag = { from: x, to: x, pointer: event.pointerId };
    svg.setPointerCapture(event.pointerId);
    event.preventDefault();
  }

  function endDrag(event, apply) {
    if (!drag || event.pointerId !== drag.pointer) return;
    const { from, to } = drag;
    drag = null;
    selection.setAttribute("visibility", "hidden");
    if (svg.hasPointerCapture(event.pointerId)) svg.releasePointerCapture(event.pointerId);
    if (apply && Math.abs(to - from) >= DRAG) viewBetween(from, to);
  }

  const onPointerUp = (event) => endDrag(event, true);
  const onPointerCancel = (event) => endDrag(event, false);

  function onPointerLeave() {
    if (document.activeElement !== svg && !drag) hide();
  }

  function onDoubleClick() {
    if (view) setView(-Infinity, Infinity);
  }

  /** Step the readout past the edge of a zoomed range: the range moves a quarter on. */
  function stepBeyond(direction, step) {
    const kept = master.xs[index];
    if (!pan(direction * 0.25)) return false;
    if (!master) return true;
    let next = indexOfX(kept);
    next += direction * step;
    show(next);
    return true;
  }

  function onKeyDown(event) {
    const zoom = zoomable(current);
    if (zoom && (event.key === "+" || event.key === "=")) {
      event.preventDefault();
      zoomBy(0.5);
      return;
    }
    if (zoom && (event.key === "-" || event.key === "_")) {
      event.preventDefault();
      zoomBy(2);
      return;
    }
    if (zoom && event.key === "0") {
      event.preventDefault();
      setView(-Infinity, Infinity);
      return;
    }
    if (!master) return;
    const { first, last } = shown;
    const step = event.shiftKey || event.key === "PageUp" || event.key === "PageDown" ? 10 : 1;
    const from = index ?? first;
    let next = null;
    if (event.key === "ArrowRight" || event.key === "ArrowUp" || event.key === "PageUp") next = index === null ? first : from + step;
    else if (event.key === "ArrowLeft" || event.key === "ArrowDown" || event.key === "PageDown") next = index === null ? last : from - step;
    else if (event.key === "Home") next = first;
    else if (event.key === "End") next = last;
    else if (event.key === "Escape") {
      index = null;
      hide();
      return;
    } else return;
    event.preventDefault();
    if (index !== null && view && (next > last || next < first) && stepBeyond(next > last ? 1 : -1, step)) return;
    show(next);
  }

  function onFocus() {
    if (master && index !== null) show(index);
  }

  function onBlur() {
    hide();
  }

  function onReset() {
    setView(-Infinity, Infinity);
    svg.focus({ preventScroll: true });
  }

  const listeners = [
    ["pointermove", onPointerMove],
    ["pointerdown", onPointerDown],
    ["pointerup", onPointerUp],
    ["pointercancel", onPointerCancel],
    ["pointerleave", onPointerLeave],
    ["dblclick", onDoubleClick],
    ["keydown", onKeyDown],
    ["focus", onFocus],
    ["blur", onBlur],
  ];
  for (const [name, listener] of listeners) svg.addEventListener(name, listener);
  zoomButton.addEventListener("click", onReset);
  // A fitted chart is drawn again when its container's width changes
  const resized = new ResizeObserver(() => {
    const next = Math.floor(container.clientWidth);
    if (!current.fit || !next || next === width) return;
    width = next;
    render(current);
  });
  resized.observe(container);
  // Its ticks, readout and buttons speak the page's language
  const stopLang = onLangChange(() => render(current));
  render(spec);

  return {
    svg,
    update(next) {
      if (view && !sameData(current, next)) view = null;
      render(next);
    },
    destroy() {
      for (const [name, listener] of listeners) svg.removeEventListener(name, listener);
      zoomButton.removeEventListener("click", onReset);
      resized.disconnect();
      stopLang();
      container.replaceChildren();
      container.classList.remove("chart", "wide", "fit", "zoomable");
    },
    readout: {
      show,
      hide() {
        index = null;
        hide();
      },
      index: () => index,
    },
    zoom: {
      set: setView,
      reset: () => setView(-Infinity, Infinity),
      range: () => (view ? { ...view } : null),
    },
  };
}
