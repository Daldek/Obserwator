// The welcome window (Nogat DEV-20.5, ECO-064): on the first visit in a browser, once the
// session has answered, a native modal <dialog> says in one sentence what the page shows and
// holds the full content of the strips' dialog: every provider line the page may show, the
// terms and „Regulamin” where the deployment serves one, written by the kit's
// `fillSources`. Closing it (the button, ×, Escape or a click beside it) keeps it closed for
// the next visits (localStorage); the strips' „Źródła i warunki” open the same lines later.

import { fillSources } from "../../nogat/nogat-sources.js";
import { allLines, useTexts } from "../attribution.js";
import { html, t, useEffect, useRef } from "../lib.js";

/** localStorage key: set once the welcome window was closed. */
export const WELCOME_KEY = "obserwator-welcome";

function seen() {
  try {
    return window.localStorage.getItem(WELCOME_KEY) === "1";
  } catch {
    return false;
  }
}

function remember() {
  try {
    window.localStorage.setItem(WELCOME_KEY, "1");
  } catch {
    // Storage blocked: the window shows again on the next visit.
  }
}

/**
 * The welcome window, mounted once by the shell.
 *
 * @param {{session: object|null}} props api/session (its `terms`); null until it answers
 * @returns {object} the <dialog>
 */
export function WelcomeDialog({ session }) {
  const texts = useTexts();
  const dialog = useRef(null);
  const sources = useRef(null);
  const start = useRef(null);
  const shown = useRef(false);
  useEffect(() => {
    const element = dialog.current;
    if (!element || !session || !texts || shown.current || seen()) return;
    shown.current = true;
    const lines = allLines(texts);
    fillSources(sources.current, { attribution: lines.attribution, termsNotice: lines.terms_notice, terms: session.terms });
    element.showModal();
    if (start.current) start.current.focus();
  }, [session, texts]);

  const close = () => {
    if (dialog.current && dialog.current.open) dialog.current.close();
  };
  // A click on the dialog itself, not on its content, which fills it, is on the backdrop
  const onClick = (event) => {
    if (event.target === event.currentTarget) close();
  };
  // Escape closes the dialog only, not the phone's sheet under it (ui/sheet.js); Tab wraps
  const onKeyDown = (event) => {
    if (event.key === "Escape") event.stopPropagation();
    if (event.key !== "Tab") return;
    const controls = [...event.currentTarget.querySelectorAll("button, a[href]")];
    const first = controls[0];
    const last = controls[controls.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  };
  return html`<dialog class="modal welcome" ref=${dialog} aria-labelledby="welcome-title" onClick=${onClick} onKeyDown=${onKeyDown} onClose=${remember}>
    <div class="modal-head">
      <h2 id="welcome-title">${t("shell.welcome.title")}</h2>
      <button class="btn ghost sm icon" type="button" aria-label=${t("shell.welcome.close")} title=${t("shell.welcome.close")} onClick=${close}>
        <svg viewBox="0 0 20 20" aria-hidden="true"><path d="M5 5l10 10M15 5L5 15" /></svg>
      </button>
    </div>
    <div class="modal-body">
      <p class="intro">${t("shell.welcome.intro")}</p>
      <div class="welcome-sources" ref=${sources}></div>
    </div>
    <div class="modal-foot">
      <button class="btn primary" type="button" ref=${start} onClick=${close}>${t("shell.welcome.start")}</button>
    </div>
  </dialog>`;
}
