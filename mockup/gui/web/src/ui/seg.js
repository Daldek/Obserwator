// A segmented control of the shell (Hydrolog's GUI, src/ui/seg.js): a radio group with
// arrow keys and one tab stop (role="radiogroup"), or a group of toggle buttons
// (aria-pressed) such as the theme switch. The sections' simpler `Seg` is in
// sections/common.js; both draw the same `.seg`.

import { html, useRef } from "../lib.js";

/**
 * A segmented control.
 *
 * @param {{items: Array<{value: string|number, label: any, title?: string, icon?: any}>,
 *   value: string|number|null, onChange: (value: any) => void, label: string,
 *   mode?: "radio"|"pressed", full?: boolean, tiny?: boolean, className?: string}} props
 *   the choices, the chosen value, the handler, the group's accessible name, the mode,
 *   full width, the tiny size and more classes
 * @returns {object} the control
 */
export function Seg({ items, value, onChange, label, mode = "radio", full, tiny, className }) {
  const group = useRef(null);
  const radio = mode === "radio";
  const chosen = items.findIndex((item) => item.value === value);
  const onKeyDown = (event) => {
    if (!radio) return;
    const step = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 }[event.key];
    if (!step) return;
    event.preventDefault();
    const index = (Math.max(chosen, 0) + step + items.length) % items.length;
    onChange(items[index].value);
    const buttons = group.current ? group.current.querySelectorAll("button") : [];
    if (buttons[index]) buttons[index].focus();
  };
  const classes = ["seg", full ? "full" : "", tiny ? "tiny" : "", className || ""].filter(Boolean).join(" ");
  return html`
    <div class=${classes} ref=${group} role=${radio ? "radiogroup" : "group"} aria-label=${label} onKeyDown=${onKeyDown}>
      ${items.map((item, index) => {
        const on = index === chosen;
        return html`
          <button
            type="button"
            class=${on ? "on" : ""}
            role=${radio ? "radio" : undefined}
            aria-checked=${radio ? String(on) : undefined}
            aria-pressed=${radio ? undefined : String(on)}
            tabindex=${radio ? (on || (chosen < 0 && index === 0) ? 0 : -1) : undefined}
            title=${item.title}
            onClick=${() => onChange(item.value)}
          >
            ${item.icon || null}${item.icon ? html`<span class="label">${item.label}</span>` : item.label}
          </button>
        `;
      })}
    </div>
  `;
}
