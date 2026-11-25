// An operator's instance (ADR-025): the deployment's `[obserwator.instance]` of nogat.toml,
// which api/session describes as `instance` (null without one). The server serves only
// what the instance serves: no `off` provider, no station outside a clipped area, no
// current data of an `off` IMGW-PIB, no PMAXTP when it is off. The rest is the page's: the
// providers in the instance's order, the featured one first (I6); the stations of a
// `hidden` provider left out, while „Pokaż pozostałych dostawców” is off and the class
// switch is on „Wszystkie”, and those of the providers beside the featured one smaller and
// faded while, besides, no dataset is chosen by its chip (I2, I6, hydromet P12; list.js,
// map.js); only the views served (main.js); the map's start, the area's outline and, in
// `clip`, its bounds (I4, I5; map.js); the operator's logo and title in the top bar and the
// page's title (I14; ui/top-bar.js). Without an instance every provider of the session
// (the registry's, a provider fed by files among them) and every view is shown.

import { VIEWS } from "./state.js";

/**
 * What a deployment shows.
 *
 * @param {object|null} session api/session; null when it did not answer
 * @returns {{instance: object|null, providers: string[], featured: string|null,
 *   hidden: string[], offersOthers: boolean, views: string[]}} the session's `instance`,
 *   the providers served in its order (the featured one first; without an instance the
 *   session's providers in the registry's order, none when it did not answer, so the
 *   panels name those of the stations), the featured one, the hidden ones, whether „Pokaż
 *   pozostałych dostawców” changes anything (a hidden provider, or a featured one beside
 *   another) and the views of the map's bar
 */
export function scopeOf(session) {
  const instance = (session && session.instance) || null;
  if (!instance) {
    const providers = session ? Object.keys(session.providers) : [];
    return { instance: null, providers, featured: null, hidden: [], offersOthers: false, views: VIEWS };
  }
  const providers = Object.keys(instance.providers);
  const hidden = providers.filter((id) => instance.providers[id] === "hidden");
  const featured = instance.featured || null;
  const served = { stations: true, current: instance.current, pmaxtp: instance.pmaxtp };
  return {
    instance,
    providers,
    featured,
    hidden,
    offersOthers: hidden.length > 0 || (featured !== null && providers.length > 1),
    views: VIEWS.filter((view) => served[view]),
  };
}

/** Whether the person asks for no other provider: the class switch on „Wszystkie”, „Pokaż pozostałych dostawców” off. */
function featuredOnly(filters) {
  return filters.class === "all" && !filters.others;
}

/**
 * Whether the list and the map leave a provider's stations out: a hidden one (I2) until a
 * class is chosen in the switch or „Pokaż pozostałych dostawców” is on.
 *
 * @param {string} provider
 * @param {{class: string, others: boolean}} filters the list's filters
 * @param {object} scope of scopeOf
 * @returns {boolean}
 */
export function leftOut(provider, filters, scope) {
  return featuredOnly(filters) && scope.hidden.includes(provider);
}

/**
 * Whether the map draws the stations of the providers beside the featured one smaller and
 * faded (I6): until „Pokaż pozostałych dostawców” is on, a class is chosen in the switch or
 * a dataset by its chip, which chooses its provider (hydromet P12).
 *
 * @param {{class: string, others: boolean, datasets: string[]}} filters the list's filters
 * @param {object} scope of scopeOf
 * @returns {boolean}
 */
export function fadesOthers(filters, scope) {
  return scope.featured !== null && featuredOnly(filters) && !(filters.datasets || []).length;
}
