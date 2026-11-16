"""The page's shell: the top bar, the views, the panels, the welcome, „Zgłoś uwagę”."""

from obserwator.messages import Text

MESSAGES: dict[str, Text] = {
    # The views of the map's bar and what the bar says beside them
    "shell.view_stations": Text("Stations", "Stacje"),
    "shell.view_current": Text("Current measurements", "Pomiary bieżące"),
    "shell.views": Text("Map view", "Widok mapy"),
    "shell.hint.stations": Text(
        "Click a station to see its data", "Kliknij stację, aby zobaczyć jej dane"
    ),
    "shell.hint.current": Text(
        "IMGW-PIB snapshot of {time}; click a station to see its measurements",
        "Migawka IMGW-PIB z {time}; kliknij stację, aby zobaczyć jej pomiary",
    ),
    "shell.hint.current_loading": Text(
        "Fetching the current measurements from IMGW-PIB…",
        "Pobieram pomiary bieżące z IMGW-PIB…",
    ),
    "shell.hint.current_failed": Text(
        "Current measurements unavailable: {reason}",
        "Pomiary bieżące niedostępne: {reason}",
    ),
    "shell.hint.pmaxtp": Text(
        "Click the map or enter the coordinates on the left",
        "Kliknij mapę albo wpisz współrzędne po lewej",
    ),
    "shell.map": Text("Station map", "Mapa stacji"),
    "shell.map_pmaxtp": Text(
        "Map: choosing the PMAXTP point", "Mapa: wybór punktu PMAXTP"
    ),
    # The side panels: a column on a desktop, a bottom sheet on a phone
    "shell.panel.stations": Text("Stations", "Stacje"),
    "shell.panel.station": Text("Station", "Stacja"),
    "shell.panel.pmaxtp": Text("PMAXTP results", "Wyniki PMAXTP"),
    "shell.panel.close": Text("Close the panel “{title}”", "Zamknij panel „{title}”"),
    "shell.panel.width": Text(
        "Width of the panel “{title}”", "Szerokość panelu „{title}”"
    ),
    "shell.stations_loading": Text(
        "Loading the station catalog…", "Wczytuję katalog stacji…"
    ),
    "shell.stations_failed": Text(
        "The station catalog did not load: {reason}",
        "Nie udało się wczytać katalogu stacji: {reason}",
    ),
    "shell.session_failed": Text(
        "The server's settings did not load: {reason}",
        "Nie udało się wczytać ustawień serwera: {reason}",
    ),
    # The top bar
    "shell.home": Text("Obserwator: start page", "Obserwator: strona główna"),
    "shell.selected_station": Text("Selected station", "Wybrana stacja"),
    "shell.guide": Text("Guide", "Instrukcja"),
    "shell.guide_title": Text(
        "The guide to this application (in Polish)", "Instrukcja obsługi aplikacji"
    ),
    "shell.lang.label": Text("Language", "Język"),
    "shell.lang.pl": Text("Polish", "polski"),
    "shell.lang.en": Text("English", "angielski"),
    "shell.lang_failed": Text(
        "The texts of this language did not load: {reason}",
        "Nie udało się wczytać tekstów w tym języku: {reason}",
    ),
    "shell.theme.label": Text("Theme", "Motyw"),
    "shell.theme.auto": Text("The system's theme", "Motyw systemu"),
    "shell.theme.light": Text("Light", "Jasny"),
    "shell.theme.dark": Text("Dark", "Ciemny"),
    # The welcome window of a first visit, with the kit's full provider lines (Nogat
    # DEV-20.5) and, in a public deployment, the kit's „Regulamin serwisu” (DEV-15.7)
    "shell.welcome.title": Text("Welcome to Obserwator", "Witaj w Obserwatorze"),
    "shell.welcome.intro": Text(
        "Obserwator shows the hydrological and meteorological stations of IMGW-PIB and"
        " ČHMÚ on a map: choose one to see its measurements, analyses and files.",
        "Obserwator pokazuje na mapie stacje hydrologiczne i meteorologiczne IMGW-PIB"
        " i ČHMÚ: wybierz stację, aby zobaczyć jej pomiary, analizy i pliki.",
    ),
    "shell.welcome.start": Text("Got it", "Rozumiem"),
    "shell.welcome.close": Text("Close", "Zamknij"),
    # „Regulamin” of a public deployment at the bottom of the left panel (DEV-15.7)
    "shell.terms": Text("Terms of service", "Regulamin"),
    # „Zgłoś uwagę” (Nogat DEV-15.12)
    "shell.feedback.open": Text("Send feedback", "Zgłoś uwagę"),
    "shell.feedback.close": Text("Close", "Zamknij"),
    "shell.feedback.intro": Text(
        "Describe a bug or an idea. The report goes to the author of Obserwator.",
        "Opisz błąd lub pomysł. Zgłoszenie trafi do autora Obserwatora.",
    ),
    "shell.feedback.message": Text(
        "Description of the problem or suggestion", "Opis problemu lub sugestii"
    ),
    "shell.feedback.placeholder": Text(
        "Describe what happened or what could be better…",
        "Opisz, co się stało lub co można poprawić…",
    ),
    "shell.feedback.no_personal_data": Text(
        "Do not enter personal data.", "Nie wpisuj danych osobowych."
    ),
    "shell.feedback.reply": Text(
        "If you want an answer, write to {email}",
        "Jeśli chcesz odpowiedzi, napisz na {email}",
    ),
    "shell.feedback.counter": Text(
        "{n} of {maximum} characters", "{n} z {maximum} znaków"
    ),
    "shell.feedback.context": Text(
        "Sent with the report", "Do zgłoszenia zostanie dołączone"
    ),
    "shell.feedback.view": Text("View", "Widok"),
    "shell.feedback.station": Text("Station", "Stacja"),
    "shell.feedback.section": Text("Section", "Sekcja"),
    "shell.feedback.parameters": Text("Address", "Adres"),
    "shell.feedback.version": Text("Version", "Wersja"),
    "shell.feedback.cancel": Text("Cancel", "Anuluj"),
    "shell.feedback.send": Text("Send", "Wyślij"),
    "shell.feedback.sending": Text("Sending…", "Wysyłam…"),
    "shell.feedback.sent": Text(
        "Thank you! The report has been saved.",
        "Dziękujemy! Zgłoszenie zostało zapisane.",
    ),
    "shell.feedback.offline": Text(
        "The report was not sent: the server does not answer.",
        "Nie udało się wysłać zgłoszenia: serwer nie odpowiada.",
    ),
}
