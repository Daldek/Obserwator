/**
 * The words of the chart module itself, from the catalog (GUI plan D15, `charts.*`).
 *
 * The texts of a particular chart (titles, axis labels, series names) come with its spec
 * from the section; these are the module's own words, read at drawing time so a chart
 * drawn again after the language switch speaks the new language. Compositions without a
 * word ("p [%]", "t = 6:20", "Q = 12,5") stay in the code.
 */

import { t } from "../i18n.js";

/** The first row of the probability axis: the exceedance probability. */
export const PROBABILITY_LABEL = "p [%]";

/** The second row of the probability axis: the return period. */
export function returnPeriodLabel() {
  return t("charts.axis.return_period");
}

/**
 * The readout's heading on a probability axis.
 *
 * @param {string} p the exceedance probability, formatted
 * @param {string} years the return period, formatted
 * @returns {string} e.g. "p = 1,0 % · T = 100 lat"
 */
export function probabilityHeading(p, years) {
  return t("charts.readout.probability", { p, years });
}

/** What the keys and the pointer do, for screen readers (aria-description of the chart). */
export function keysHint(zoom) {
  return zoom ? `${t("charts.keys.readout")} ${t("charts.keys.zoom")}` : t("charts.keys.readout");
}

/** The button that undoes a zoom. */
export function zoomResetLabel() {
  return t("charts.zoom.reset");
}

/**
 * The range a zoomed chart shows.
 *
 * @param {string} from its start, formatted
 * @param {string} to its end, formatted
 * @returns {string}
 */
export function zoomRangeText(from, to) {
  return t("charts.zoom.range", { from, to });
}

/** The error of an image the browser could not draw. */
export function imageFailedText() {
  return t("charts.export.image_failed");
}
