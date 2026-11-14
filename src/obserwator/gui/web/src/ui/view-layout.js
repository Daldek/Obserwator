// The layout of the view (Nogat design/README.md, Layout; after Hydrolog's GUI,
// src/ui/view-layout.js): „Stacje” on the left, the map in the centre, „Stacja” on the right.
//   html`<${ViewLayout} left=${{title, sub, body, foot}} center=${{bar, body, label}}
//     right=${{title, sub, body, short, badge}} foot=${foot} />`
// The side panels resize by dragging or by keys (arrows 16 px, Shift 64 px, Home, End,
// Enter or a double click for the default width), left 260-560 px (300) and right
// 340-720 px (400), keeping the centre at least 480 px; the widths are kept in the
// browser. At 860 px and below the panels are bottom sheets, opened from the map's bar.
// The `foot` runs across the whole view under the map and both panels (after Hydrograf's
// #view-foot): the view's one strip of provider lines. On a phone the sheets stop above it
// (`--view-foot-h`), so it stays in sight. A panel's own `foot` sits under its scrolling
// body: „Regulamin” of a public deployment at the bottom of the left panel.

import { useLayoutEffect, useRef, useState } from "../../vendor/preact/hooks.mjs";
import { html, t } from "../lib.js";
import { closePanel, closeSheet, openPanel, usePanels } from "./sheet.js";

/** Bounds of the side panels [px]. */
export const LIMITS = Object.freeze({
  left: Object.freeze({ min: 260, max: 560 }),
  right: Object.freeze({ min: 340, max: 720 }),
});

/** The narrowest centre [px]. */
export const CENTRE_MIN = 480;

const OTHER = { left: "right", right: "left" };
/** The catalog's title of a panel that names none. */
const TITLES = { left: "shell.panel.stations", right: "shell.panel.station" };
const STORAGE_KEY = "obserwator-layout";
const widths = { left: null, right: null };
try {
  const stored = JSON.parse(window.localStorage.getItem(STORAGE_KEY) || "null");
  for (const side of ["left", "right"]) {
    if (stored && typeof stored[side] === "number") widths[side] = clampOwn(side, stored[side]);
  }
} catch {
  // Storage blocked or broken: the default widths.
}

function clampOwn(side, width) {
  return Math.min(LIMITS[side].max, Math.max(LIMITS[side].min, width));
}

/** The default width of a panel: the CSS variable --left-w or --right-w (a media query sets it). */
function cssDefault(side) {
  const value = parseInt(getComputedStyle(document.documentElement).getPropertyValue(`--${side}-w`), 10);
  return Number.isNaN(value) ? LIMITS[side].min : value;
}

/** The widest a panel may be beside the other one and the centre. */
function maxFor(side, total, open) {
  const other = OTHER[side];
  const otherWidth = open[other] ? clampOwn(other, widths[other] ?? cssDefault(other)) : 0;
  return Math.max(LIMITS[side].min, Math.min(LIMITS[side].max, total - otherWidth - CENTRE_MIN));
}

function keep() {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(widths));
  } catch {
    // Storage blocked: the widths last until the page closes.
  }
}

/** The title of a panel as text: its own, else the side's. */
function titleOf(side, panel) {
  return panel && typeof panel.title === "string" && panel.title ? panel.title : t(TITLES[side]);
}

/** A resizer between a panel and the centre. */
function Resizer({ side, title, now, max, onWidth }) {
  const drag = useRef(null);
  const lastDown = useRef(0);
  const sign = side === "right" ? -1 : 1;
  const onPointerDown = (event) => {
    if (event.button !== 0) return;
    event.preventDefault();
    event.currentTarget.focus();
    if (event.timeStamp - lastDown.current < 400) {
      lastDown.current = 0;
      onWidth(null, true);
      return;
    }
    lastDown.current = event.timeStamp;
    drag.current = { x: event.clientX, width: now };
    event.currentTarget.setPointerCapture(event.pointerId);
    event.currentTarget.classList.add("dragging");
    document.body.classList.add("resizing");
  };
  const onPointerMove = (event) => {
    if (!drag.current) return;
    if (Math.abs(event.clientX - drag.current.x) > 3) lastDown.current = 0;
    onWidth(Math.min(max, drag.current.width + sign * (event.clientX - drag.current.x)), false);
  };
  const end = (event) => {
    if (!drag.current) return;
    drag.current = null;
    event.currentTarget.classList.remove("dragging");
    document.body.classList.remove("resizing");
    onWidth(now, true);
  };
  const onKeyDown = (event) => {
    const step = event.shiftKey ? 64 : 16;
    let next;
    if (event.key === "ArrowRight") next = now + sign * step;
    else if (event.key === "ArrowLeft") next = now - sign * step;
    else if (event.key === "Home") next = LIMITS[side].min;
    else if (event.key === "End") next = max;
    else if (event.key === "Enter") next = null;
    else return;
    event.preventDefault();
    onWidth(next === null ? null : Math.min(max, next), true);
  };
  return html`<div
    class=${`resizer r-${side}`}
    role="separator"
    aria-orientation="vertical"
    aria-controls=${`panel-${side}`}
    aria-label=${t("shell.panel.width", { title })}
    aria-valuemin=${LIMITS[side].min}
    aria-valuemax=${max}
    aria-valuenow=${now}
    tabindex="0"
    onPointerDown=${onPointerDown}
    onPointerMove=${onPointerMove}
    onPointerUp=${end}
    onPointerCancel=${end}
    onLostPointerCapture=${end}
    onKeyDown=${onKeyDown}
  ></div>`;
}

/** One side panel: a column on a desktop, a bottom sheet on a phone. */
function Panel({ side, panel, open, sheet, onClose }) {
  const id = `panel-${side}`;
  const title = titleOf(side, panel);
  const close = t("shell.panel.close", { title });
  const classes = ["view-panel", side, open ? "" : "collapsed", sheet ? "open" : ""].filter(Boolean).join(" ");
  return html`<aside class=${classes} aria-labelledby=${`${id}-title`} id=${id}>
    <div class="panel-head">
      <span class="grip" aria-hidden="true" onClick=${onClose}></span>
      <h2 id=${`${id}-title`}>${panel.title || title}</h2>
      ${panel.sub ? html`<span class="sub">${panel.sub}</span>` : null}
      <button class="btn ghost sm icon" type="button" aria-label=${close} title=${close} onClick=${onClose}>
        <svg viewBox="0 0 20 20" aria-hidden="true"><path d="M5 5l10 10M15 5L5 15" /></svg>
      </button>
    </div>
    <div class="view-panel-body">${panel.body}</div>
    ${panel.foot ? html`<div class="panel-foot">${panel.foot}</div>` : null}
  </aside>`;
}

/**
 * The layout: the list, the map and the station, and the foot across them.
 *
 * @param {{left: {title?: any, sub?: any, body: any, foot?: any}, center: {bar?: any, body: any,
 *   label?: string}, right: {title?: any, sub?: any, body: any, short?: string, badge?: any},
 *   foot?: any}} props the panels and the centre; `right.short` and `right.badge` label the
 *   bar's button that opens the station panel (a sheet on a phone); `left.foot` sits at the
 *   bottom of the left panel; `foot` is the view's foot under the map and both panels
 * @returns {object} the layout
 */
export function ViewLayout({ left, center, right, foot }) {
  const panels = usePanels();
  const box = useRef(null);
  const footBox = useRef(null);
  const [, setDragged] = useState(0);
  const [total, setTotal] = useState(0);
  // The foot's height, for the phone's sheets to stop above it
  useLayoutEffect(() => {
    const element = footBox.current;
    if (!element) return undefined;
    const measure = () => box.current && box.current.style.setProperty("--view-foot-h", `${element.offsetHeight}px`);
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => {
      observer.disconnect();
      if (box.current) box.current.style.removeProperty("--view-foot-h");
    };
  }, [Boolean(foot)]);
  useLayoutEffect(() => {
    const measure = () => {
      if (box.current && box.current.clientWidth) setTotal(box.current.clientWidth);
    };
    measure();
    const observer = new ResizeObserver(measure);
    if (box.current) observer.observe(box.current);
    return () => observer.disconnect();
  }, []);
  const open = { left: panels.open.left, right: panels.open.right };
  const sizes = {};
  const style = {};
  if (!panels.phone) {
    for (const side of ["left", "right"]) {
      const max = total ? maxFor(side, total, open) : LIMITS[side].max;
      sizes[side] = { now: Math.min(max, clampOwn(side, widths[side] ?? cssDefault(side))), max };
      style[`--${side}-w`] = open[side] ? `${sizes[side].now}px` : "0px";
    }
  }
  const onWidth = (side) => (next, kept) => {
    widths[side] = next === null ? null : clampOwn(side, next);
    if (kept) keep();
    setDragged((count) => count + 1);
  };
  const sheet = panels.phone ? panels.sheet : null;
  const close = (side) => () => {
    if (panels.phone) closeSheet();
    else closePanel(side);
  };
  const toggle = (side) => {
    if (panels.phone) {
      if (sheet === side) closeSheet();
      else openPanel(side);
    } else if (open[side]) closePanel(side);
    else openPanel(side);
  };
  const button = (side, label, extra) => html`<button
    class=${`btn sm panel-toggle ${side}${open[side] ? " is-open" : ""}`}
    type="button"
    aria-expanded=${String(panels.phone ? sheet === side : open[side])}
    aria-controls=${`panel-${side}`}
    onClick=${() => toggle(side)}
  >
    ${side === "left" ? html`<svg viewBox="0 0 20 20" aria-hidden="true"><path d="M4 5h12M4 10h12M4 15h8" /></svg>` : null}
    <span class="label">${label}</span>${extra || null}
  </button>`;
  return html`<div class="view-layout" ref=${box} style=${style}>
    <${Panel} side="left" panel=${left} open=${open.left} sheet=${sheet === "left"} onClose=${close("left")} />
    ${open.left && !panels.phone ? html`<${Resizer} side="left" title=${titleOf("left", left)} ...${sizes.left} onWidth=${onWidth("left")} />` : null}
    <section class="view-center" aria-label=${center.label || t("shell.map")}>
      <div class="view-bar map-bar">
        ${button("left", titleOf("left", left))}
        ${center.bar || null}
        <div class="end">${button("right", (right && right.short) || titleOf("right", right), right && right.badge)}</div>
      </div>
      <div class="view-body map-body">${center.body}</div>
    </section>
    ${open.right && !panels.phone ? html`<${Resizer} side="right" title=${titleOf("right", right)} ...${sizes.right} onWidth=${onWidth("right")} />` : null}
    <${Panel} side="right" panel=${right} open=${open.right} sheet=${sheet === "right"} onClose=${close("right")} />
    ${foot ? html`<div class="view-foot" ref=${footBox}>${foot}</div>` : null}
  </div>`;
}
