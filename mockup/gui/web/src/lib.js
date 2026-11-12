// Preact with htm, the hooks and the chart component, imported from one place.

import htm from "../vendor/htm/htm.mjs";
import { h, render, Fragment } from "../vendor/preact/preact.mjs";
import { useCallback, useEffect, useMemo, useRef, useState } from "../vendor/preact/hooks.mjs";

export const html = htm.bind(h);
export { Fragment, h, render, useCallback, useEffect, useMemo, useRef, useState };
export { Chart } from "./charts/chart.js";

/** Days since 1970-01-01 of an ISO date "YYYY-MM-DD": the x of the chart's `date` scale. */
export function dayNumber(iso) {
  return Math.round(Date.UTC(+iso.slice(0, 4), +iso.slice(5, 7) - 1, +iso.slice(8, 10)) / 86400000);
}

/** The ISO date of a day number. */
export function isoOfDay(day) {
  return new Date(day * 86400000).toISOString().slice(0, 10);
}

const NUMBER = new Map();

/**
 * A number in Polish ("1 234,5"), or "–" when missing.
 *
 * @param {number|null|undefined} value
 * @param {number} [digits] fraction digits (fixed)
 */
export function fmt(value, digits = 0) {
  if (value === null || value === undefined || !Number.isFinite(value)) return "–";
  let format = NUMBER.get(digits);
  if (!format) {
    format = new Intl.NumberFormat("pl-PL", { minimumFractionDigits: digits, maximumFractionDigits: digits });
    NUMBER.set(digits, format);
  }
  return format.format(value);
}

/** A date "YYYY-MM-DD" as "12.11.2026". */
export function fmtDate(iso) {
  if (!iso) return "–";
  return `${iso.slice(8, 10)}.${iso.slice(5, 7)}.${iso.slice(0, 4)}`;
}

/** Units as shown: m3/s → m³/s, degC → °C. */
export function unit(text) {
  return { "m3/s": "m³/s", degC: "°C" }[text] || text || "";
}
