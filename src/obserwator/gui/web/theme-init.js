// Before the first paint: the stored theme (key "nogat-theme", shared with Nogat's other
// pages; "auto" or nothing follows the system), the stored language (key "obserwator-lang",
// Polish by default) and the embedded flag "?nogat=1", which hides Obserwator's own top bar
// inside Nogat's shell (data-host="nogat", css/app.css); the views stay in the map's bar.
// Then the start's requests, at once rather than after the page's modules: the texts in
// that language, the session and the station layer, with the headers src/api.js sends
// (src/start.js, where i18n.js and api.js take them).
(function () {
  var lang = "pl";
  try {
    var t = localStorage.getItem("nogat-theme");
    if (t === "light" || t === "dark") document.documentElement.dataset.theme = t;
    var l = localStorage.getItem("obserwator-lang");
    if (l === "en" || l === "pl") {
      document.documentElement.lang = l;
      lang = l;
    }
  } catch (e) {}
  if (new URLSearchParams(window.location.search).get("nogat") === "1") {
    document.documentElement.dataset.host = "nogat";
  }
  if (window.fetch) {
    var json = { Accept: "application/json" };
    var asked = { Accept: "application/json", "Accept-Language": lang };
    var started = {};
    started[lang + " api/texts?lang=" + lang] = fetch("api/texts?lang=" + lang, { headers: json });
    started[lang + " api/session"] = fetch("api/session", { headers: asked });
    started[lang + " api/stations"] = fetch("api/stations", { headers: asked });
    for (var key in started) started[key].catch(function () {});
    window.obserwatorStart = started;
  }
})();
