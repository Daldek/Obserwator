// Before the admin page's first paint: the theme stored by the app (key "nogat-theme",
// shared with Nogat's other pages; "auto" or nothing follows the system). The panel is
// Polish only, so it leaves out the app's language, which ../theme-init.js also applies.
try {
  var t = localStorage.getItem("nogat-theme");
  if (t === "light" || t === "dark") document.documentElement.dataset.theme = t;
} catch (e) {}
