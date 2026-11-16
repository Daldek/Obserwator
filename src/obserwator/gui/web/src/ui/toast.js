// A short message at the bottom of the page, after Hydrolog's GUI (src/ui/toast.js):
// toast(t("shell.feedback.sent")) or toast(text, "bad"). The shell renders one ToastHost.

import { html, useEffect, useState } from "../lib.js";

/** How long a message stays [ms]. */
export const TOAST_MS = 4000;

const listeners = new Set();
let counter = 0;

/**
 * Show a short message.
 *
 * @param {string} text the message
 * @param {"ok"|"bad"} [kind="ok"] a success or a failure
 */
export function toast(text, kind = "ok") {
  counter += 1;
  const item = { text, kind, id: counter };
  for (const listener of [...listeners]) listener(item);
}

/**
 * The place of the messages: a live region that stays in the page, so each message is read.
 *
 * @returns {object} the region with the current message, if any
 */
export function ToastHost() {
  const [item, setItem] = useState(null);
  useEffect(() => {
    listeners.add(setItem);
    return () => listeners.delete(setItem);
  }, []);
  useEffect(() => {
    if (!item) return undefined;
    const timer = setTimeout(() => setItem(null), TOAST_MS);
    return () => clearTimeout(timer);
  }, [item]);
  return html`<div class="toast-host" role="status" aria-live="polite">
    ${item ? html`<div class=${`toast ${item.kind}`} key=${item.id}>${item.text}</div>` : null}
  </div>`;
}
