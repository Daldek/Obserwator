// „Zgłoś uwagę” (Nogat DEV-15.12), after Hydrolog's GUI (src/ui/feedback.js) and Hydrograf:
// the button of the top bar opens a native modal <dialog> (focus held inside, Escape or a
// click beside it closes it, focus back on the button) with one text field of 1 to 5,000
// characters and its counter, the note against personal data with the operator's e-mail of
// the session (without one, the note's first sentence only), the context it sends shown
// read-only (the view, the station, the address's parameters; the server adds the app's
// version), Anuluj and Wyślij. No contact fields. A stored report closes the dialog with a
// toast; a refused one (the server's message, e.g. 400 or 429) stays in the dialog with the
// text kept. The context is taken when the dialog opens. The shell mounts the dialog once;
// the button lives in the top bar.

import { ApiError, api } from "../api.js";
import { fmt, html, t, useEffect, useRef, useState } from "../lib.js";
import { addressParameters } from "../state.js";
import { toast } from "./toast.js";

/** The longest description the server accepts (gui/_feedback.py MESSAGE_MAX). */
export const MESSAGE_MAX = 5000;

const DIALOG_ID = "feedback-dialog";
/** A character no text holds: where a link goes into a translated sentence. */
const SLOT = "\u{E000}";

/** A speech bubble, as in Hydrograf's and Hydrolog's top bars. */
const ICON = () => html`<svg class="icon-svg" viewBox="0 0 20 20" aria-hidden="true"><path d="M3 4h14v10H8.5L5 17v-3H3z" /></svg>`;

/** Opens the mounted dialog; null while none is mounted. */
let opener = null;

function openFeedback() {
  if (opener) opener();
}

/**
 * The button of the top bar; below 1100 px only its icon shows.
 *
 * @returns {object} the button
 */
export function FeedbackButton() {
  const label = t("shell.feedback.open");
  return html`<button class="btn ghost feedback-btn" type="button" aria-label=${label} title=${label} aria-haspopup="dialog" aria-controls=${DIALOG_ID} onClick=${openFeedback}>
    ${ICON()}<span class="label">${label}</span>
  </button>`;
}

/**
 * The context sent with a report (Nogat DEV-15.12): the view, its station of the catalog
 * and the address's parameters.
 *
 * @param {{view: string, station: string|null}} state what the page shows now: the view
 *   ("stations", "current" or "pmaxtp") and the station's code
 * @returns {{view: string, station: string|null, parameters: Record<string, string>}}
 */
export function feedbackContext({ view, station }) {
  return { view, station: station || null, parameters: addressParameters() };
}

/** The note under the field: no personal data, and where to write for an answer. */
function Note({ email }) {
  const first = t("shell.feedback.no_personal_data");
  if (!email) return html`<p class="fb-note" id="fb-note">${first}</p>`;
  const [before, after = ""] = t("shell.feedback.reply", { email: SLOT }).split(SLOT);
  return html`<p class="fb-note" id="fb-note">${first} ${before}<a href=${`mailto:${email}`}>${email}</a>${after}</p>`;
}

/** The text of a failed report: the server's message (ApiError), or that it did not answer. */
function failure(error) {
  if (error instanceof ApiError) return error.message;
  return t("shell.feedback.offline");
}

/**
 * The dialog of a report.
 *
 * @param {{capture: () => {view: string, viewName: string, station: string|null,
 *   stationName: string|null, sectionTitle: string|null}, session: object|null}} props
 *   `capture` tells what the page shows when the dialog opens; `session` gives the
 *   operator's e-mail and the version the server adds
 * @returns {object} the <dialog>
 */
export function FeedbackDialog({ capture, session }) {
  const dialog = useRef(null);
  const field = useRef(null);
  const latest = useRef(capture);
  latest.current = capture;
  const [message, setMessage] = useState("");
  const [shown, setShown] = useState(null);
  const [error, setError] = useState(null);
  const [sending, setSending] = useState(false);

  useEffect(() => {
    const open = () => {
      const element = dialog.current;
      if (!element || element.open) return;
      const page = latest.current();
      setError(null);
      setShown({ page, context: feedbackContext(page) });
      element.showModal();
      if (field.current) field.current.focus();
    };
    opener = open;
    return () => {
      if (opener === open) opener = null;
    };
  }, []);

  const close = () => {
    if (dialog.current && dialog.current.open) dialog.current.close();
  };
  const submit = async (event) => {
    event.preventDefault();
    if (sending) return;
    const text = message.trim();
    if (!text) {
      setError(t("public.feedback_empty"));
      if (field.current) field.current.focus();
      return;
    }
    setSending(true);
    setError(null);
    try {
      await api.feedback({ message: text, context: shown.context });
      setMessage("");
      close();
      toast(t("shell.feedback.sent"));
    } catch (caught) {
      setError(failure(caught));
      // The disabled button lost the focus: back to the text, which is kept
      if (field.current) field.current.focus();
    } finally {
      setSending(false);
    }
  };
  // A click on the dialog itself, not on its content, which fills it, is on the backdrop
  const onClick = (event) => {
    if (event.target === event.currentTarget) close();
  };
  // Escape closes the dialog only, not the phone's sheet under it (ui/sheet.js); Tab wraps
  // from the last control to the first and back, never leaving the dialog
  const onKeyDown = (event) => {
    if (event.key === "Escape") event.stopPropagation();
    if (event.key !== "Tab") return;
    const controls = [...event.currentTarget.querySelectorAll("button:not([disabled]), textarea, a[href]")];
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
  const page = shown ? shown.page : null;
  const context = shown ? shown.context : null;
  const parameters = context ? Object.entries(context.parameters) : [];
  const version = session && session.version ? `Obserwator ${session.version.obserwator}` : "—";
  const rows = context
    ? [
        [t("shell.feedback.view"), page.viewName],
        [t("shell.feedback.station"), context.station ? [context.station, page.stationName].filter(Boolean).join(" · ") : "—"],
        ...(context.station && page.sectionTitle ? [[t("shell.feedback.section"), page.sectionTitle]] : []),
        [
          t("shell.feedback.parameters"),
          parameters.length ? html`<code>${parameters.map(([key, value]) => `${key}=${value}`).join("&")}</code>` : "—",
        ],
        [t("shell.feedback.version"), version],
      ]
    : [];
  const title = t("shell.feedback.open");
  return html`<dialog class="modal feedback" id=${DIALOG_ID} ref=${dialog} aria-labelledby="fb-title" onClick=${onClick} onKeyDown=${onKeyDown}>
    <div class="modal-head">
      <h2 id="fb-title">${title}</h2>
      <button class="btn ghost sm icon" type="button" aria-label=${t("shell.feedback.close")} title=${t("shell.feedback.close")} onClick=${close}>
        <svg viewBox="0 0 20 20" aria-hidden="true"><path d="M5 5l10 10M15 5L5 15" /></svg>
      </button>
    </div>
    <form novalidate onSubmit=${submit}>
      <div class="modal-body">
        <p class="intro">${t("shell.feedback.intro")}</p>
        <div class="field">
          <label for="fb-message">${t("shell.feedback.message")}</label>
          <textarea
            id="fb-message"
            ref=${field}
            rows="6"
            maxlength=${MESSAGE_MAX}
            placeholder=${t("shell.feedback.placeholder")}
            aria-describedby="fb-note fb-counter"
            aria-invalid=${error ? "true" : undefined}
            value=${message}
            onInput=${(event) => setMessage(event.currentTarget.value)}
          ></textarea>
          <div class="fb-under">
            <${Note} email=${session ? session.operator_email : null} />
            <span class="counter num" id="fb-counter" aria-label=${t("shell.feedback.counter", { n: fmt(message.length), maximum: fmt(MESSAGE_MAX) })}
              >${fmt(message.length)}/${fmt(MESSAGE_MAX)}</span
            >
          </div>
        </div>
        ${error ? html`<p class="fb-error" role="alert">${error}</p>` : null}
        <section class="fb-context" aria-labelledby="fb-context-title">
          <h3 id="fb-context-title">${t("shell.feedback.context")}</h3>
          <dl>
            ${rows.map(([name, value]) => html`<div key=${name}><dt>${name}</dt><dd>${value}</dd></div>`)}
          </dl>
        </section>
      </div>
      <div class="modal-foot">
        <button class="btn" type="button" onClick=${close}>${t("shell.feedback.cancel")}</button>
        <button class="btn primary" type="submit" disabled=${sending}>${sending ? t("shell.feedback.sending") : t("shell.feedback.send")}</button>
      </div>
    </form>
  </dialog>`;
}
