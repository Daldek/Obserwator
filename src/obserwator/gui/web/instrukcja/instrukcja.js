// The guide's page (instrukcja/index.html): the theme switch of the app's top bar (Auto,
// Jasny, Ciemny), drawn by the page's own markup because the guide is Polish only and loads
// none of the app's texts. The choice is the app's: ../src/ui/theme.js keeps it under
// "nogat-theme" for every page of the origin, theme-init.js applied it before the first
// paint, and a choice made in the app's tab shows here too. The rest is static HTML.

import { THEME_KEY, setTheme, storedTheme } from "../src/ui/theme.js";

const buttons = [...document.querySelectorAll("[data-theme-choice]")];

/** Mark the button of the choice pressed. */
function show(choice) {
  for (const button of buttons) {
    const on = button.dataset.themeChoice === choice;
    button.classList.toggle("on", on);
    button.setAttribute("aria-pressed", String(on));
  }
}

for (const button of buttons) {
  button.addEventListener("click", () => {
    setTheme(button.dataset.themeChoice);
    show(button.dataset.themeChoice);
  });
}

window.addEventListener("storage", (event) => {
  if (event.key !== THEME_KEY && event.key !== null) return;
  const choice = storedTheme();
  setTheme(choice);
  show(choice);
});

show(storedTheme());
