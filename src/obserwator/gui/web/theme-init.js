// Before the first paint: the stored theme (key "nogat-theme", shared with Nogat's other
// pages; "auto" or nothing follows the system), the stored language (key "obserwator-lang",
// Polish by default) and the embedded flag "?nogat=1", which hides Obserwator's own top bar
// inside Nogat's shell (data-host="nogat", css/app.css); the views stay in the map's bar.
try {
  var t = localStorage.getItem("nogat-theme");
  if (t === "light" || t === "dark") document.documentElement.dataset.theme = t;
  var l = localStorage.getItem("obserwator-lang");
  if (l === "en" || l === "pl") document.documentElement.lang = l;
} catch (e) {}
if (new URLSearchParams(window.location.search).get("nogat") === "1") {
  document.documentElement.dataset.host = "nogat";
}
