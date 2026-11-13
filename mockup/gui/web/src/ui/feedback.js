// „Zgłoś uwagę”, after Hydrolog's GUI (src/ui/feedback.js) and Hydrograf, with the author's
// decision of 2026-11-13: the button of the top bar opens a native modal <dialog> (focus held
// inside, Escape or a click beside it closes it, focus back on the button) with the
// description and its counter (at most 4000 characters), the note against personal data, the
// automatic context shown read-only (what is sent, and the version the server adds), Anuluj
// and Wyślij. No contact fields. A stored report closes the dialog with a toast; a failure
// stays in the dialog as an error toast, with the text kept. The context is taken when the
// dialog opens. The shell mounts the dialog once; the button lives in the top bar.

import { api } from "../api.js";
import { html, useEffect, useRef, useState } from "../lib.js";
import { toast } from "./toast.js";

/** The server's limits (server/feedback.py). */
export const MESSAGE_MAX = 4000;
const ADDRESS_MAX = 500;

/** The note under the description, verbatim (the author, 2026-11-13). */
const NOTE_BEFORE = "Nie wpisuj danych osobowych. Jeśli chcesz odpowiedzi, napisz na ";
const CONTACT = "kontakt@debever.pl";

const TEXTS = {
  open: "Zgłoś uwagę",
  title: "Zgłoś uwagę",
  close: "Zamknij",
  intro: "Opisz błąd lub pomysł. Zgłoszenie trafi do autora Obserwatora.",
  message: "Opis problemu lub sugestii",
  placeholder: "Opisz, co się stało lub co można poprawić…",
  context: "Do zgłoszenia zostanie dołączone",
  cancel: "Anuluj",
  send: "Wyślij",
  sending: "Wysyłam…",
  empty: "Opis nie może być pusty.",
  thanks: "Dziękujemy! Zgłoszenie zostało zapisane.",
  offline: "Nie udało się wysłać zgłoszenia: serwer nie odpowiada.",
  none: "—",
};
const VIEW_NAMES = { stations: "Stacje", current: "Pomiary bieżące", pmaxtp: "PMAXTP" };

/** How long an error stays in the dialog [ms]. */
const ERROR_MS = 6000;
const DIALOG_ID = "feedback-dialog";

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
  return html`<button class="btn ghost feedback-btn" type="button" aria-label=${TEXTS.open} title=${TEXTS.open} aria-haspopup="dialog" aria-controls=${DIALOG_ID} onClick=${openFeedback}>
    ${ICON()}<span class="label">${TEXTS.open}</span>
  </button>`;
}

/**
 * The context sent with a report: the view, its station and section, the page's address.
 *
 * @param {{view: string, station: string|null, section: string|null, sectionTitle: string|null}} state
 *   what the page shows now: the view, the station's code, the section's id and title
 * @returns {{view: string, station?: string, section?: string, section_title?: string, address: string}}
 */
export function feedbackContext({ view, station, section, sectionTitle }) {
  const context = { view };
  if (station) context.station = station;
  if (station && section) {
    context.section = section;
    if (sectionTitle) context.section_title = sectionTitle;
  }
  context.address = `${window.location.pathname}${window.location.search}`.slice(0, ADDRESS_MAX);
  return context;
}

function versionText(meta) {
  const version = meta && meta.version;
  if (!version) return TEXTS.none;
  const parts = [`Obserwator ${version.obserwator}`, `Hydrolog ${version.hydrolog}`];
  if (version.mockup) parts.push(`makieta ${version.mockup}`);
  return parts.join(", ");
}

function failure(error) {
  if (error && error.doc && error.doc.title) return error.doc.title;
  if (error instanceof TypeError) return TEXTS.offline;
  return String((error && error.message) || error);
}

/**
 * The dialog of a report.
 *
 * @param {{capture: () => {context: object, stationName: string|null}, meta: object|null}} props
 *   `capture` gives the context when the dialog opens; `meta` the server's version
 * @returns {object} the <dialog>
 */
export function FeedbackDialog({ capture, meta }) {
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
      setError(null);
      setShown(latest.current());
      element.showModal();
      if (field.current) field.current.focus();
    };
    opener = open;
    return () => {
      if (opener === open) opener = null;
    };
  }, []);
  useEffect(() => {
    if (!error) return undefined;
    const timer = setTimeout(() => setError(null), ERROR_MS);
    return () => clearTimeout(timer);
  }, [error]);

  const close = () => {
    if (dialog.current && dialog.current.open) dialog.current.close();
  };
  const submit = async (event) => {
    event.preventDefault();
    const text = message.trim();
    if (!text) {
      setError({ text: TEXTS.empty, n: Date.now() });
      if (field.current) field.current.focus();
      return;
    }
    setSending(true);
    setError(null);
    try {
      await api.feedback({ message: text, context: shown.context });
      setMessage("");
      close();
      toast(TEXTS.thanks);
    } catch (caught) {
      setError({ text: failure(caught), n: Date.now() });
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
  const context = shown ? shown.context : null;
  const rows = context
    ? [
        ["Widok", VIEW_NAMES[context.view] || context.view],
        ["Stacja", context.station ? [context.station, shown.stationName].filter(Boolean).join(" · ") : TEXTS.none],
        ["Sekcja", context.section ? `${context.section_title || context.section} (${context.section})` : TEXTS.none],
        ["Adres", context.address],
        ["Wersja", versionText(meta)],
      ]
    : [];
  return html`<dialog class="modal feedback" id=${DIALOG_ID} ref=${dialog} aria-labelledby="fb-title" onClick=${onClick} onKeyDown=${onKeyDown}>
    <div class="modal-head">
      <h2 id="fb-title">${TEXTS.title}</h2>
      <button class="btn ghost sm icon" type="button" aria-label=${TEXTS.close} title=${TEXTS.close} onClick=${close}>
        <svg viewBox="0 0 20 20" aria-hidden="true"><path d="M5 5l10 10M15 5L5 15" /></svg>
      </button>
    </div>
    <form novalidate onSubmit=${submit}>
      <div class="modal-body">
        <p class="intro">${TEXTS.intro}</p>
        <div class="field">
          <label for="fb-message">${TEXTS.message}</label>
          <textarea
            id="fb-message"
            ref=${field}
            rows="6"
            maxlength=${MESSAGE_MAX}
            placeholder=${TEXTS.placeholder}
            aria-describedby="fb-note fb-counter"
            value=${message}
            onInput=${(event) => setMessage(event.currentTarget.value)}
          ></textarea>
          <div class="fb-under">
            <p class="fb-note" id="fb-note">${NOTE_BEFORE}<a href=${`mailto:${CONTACT}`}>${CONTACT}</a></p>
            <span class="counter num" id="fb-counter">${message.length}/${MESSAGE_MAX}</span>
          </div>
        </div>
        <section class="fb-context" aria-labelledby="fb-context-title">
          <h3 id="fb-context-title">${TEXTS.context}</h3>
          <dl>
            ${rows.map(([name, value]) => html`<div key=${name}><dt>${name}</dt><dd>${value}</dd></div>`)}
          </dl>
        </section>
      </div>
      <div class="modal-foot">
        <button class="btn" type="button" onClick=${close}>${TEXTS.cancel}</button>
        <button class="btn primary" type="submit" disabled=${sending}>${sending ? TEXTS.sending : TEXTS.send}</button>
      </div>
    </form>
    ${error ? html`<div class="toast bad in-dialog" role="alert" key=${error.n}>${error.text}</div>` : null}
  </dialog>`;
}
