// An operator's instance (ADR-025): the deployment's `[obserwator.instance]` of nogat.toml,
// which api/session describes as `instance` (null without one). The server serves only
// what the instance serves: no `off` provider, no station outside a clipped area, no
// current data of an `off` IMGW-PIB, no PMAXTP when it is off. The rest is the page's: the
// providers in the instance's order, the featured one first (I6); the stations of a
// `hidden` provider left out, and those of the providers beside the featured one smaller
// and faded, while „Pokaż inne źródła” is off and the provider switch is on „all” (I2, I6;
// list.js, map.js); only the views served (main.js); the map's start, the area's outline
// and, in `clip`, its bounds (I4, I5; map.js); the operator's logo and title in the top
// bar and the page's title (I14; ui/top-bar.js). Without an instance every provider and
// view is shown, as before.

import { VIEWS } from "./state.js";

/** The providers of the registry in its order: every one without an instance. */
export const PROVIDERS = ["IMGW-PIB", "CHMU"];

/**
 * What a deployment shows.
 *
 * @param {object|null} session api/session; null when it did not answer
 * @returns {{instance: object|null, providers: string[], featured: string|null,
 *   hidden: string[], offersOthers: boolean, views: string[]}} the session's `instance`,
 *   the providers served in its order (the featured one first), the featured one, the
 *   hidden ones, whether „Pokaż inne źródła” changes anything (a hidden provider, or a
 *   featured one beside another) and the views of the map's bar
 */
export function scopeOf(session) {
  const instance = (session && session.instance) || null;
  if (!instance) return { instance: null, providers: PROVIDERS, featured: null, hidden: [], offersOthers: false, views: VIEWS };
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

/** Whether the person asks for no other provider: the switch on „all”, „Pokaż inne źródła” off. */
function featuredOnly(filters) {
  return filters.provider === "all" && !filters.others;
}

/**
 * Whether the list and the map leave a provider's stations out: a hidden one (I2) until it
 * is chosen in the switch or „Pokaż inne źródła” is on.
 *
 * @param {string} provider
 * @param {{provider: string, others: boolean}} filters the list's filters
 * @param {object} scope of scopeOf
 * @returns {boolean}
 */
export function leftOut(provider, filters, scope) {
  return featuredOnly(filters) && scope.hidden.includes(provider);
}

/**
 * Whether the map draws the stations of the providers beside the featured one smaller and
 * faded (I6): until „Pokaż inne źródła” is on or a provider is chosen in the switch.
 *
 * @param {{provider: string, others: boolean}} filters the list's filters
 * @param {object} scope of scopeOf
 * @returns {boolean}
 */
export function fadesOthers(filters, scope) {
  return scope.featured !== null && featuredOnly(filters);
}
