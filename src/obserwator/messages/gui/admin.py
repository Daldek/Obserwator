"""The admin panel's texts (Nogat DEV-15.13): its refusals, its errors, the checks of „Stan”."""

from obserwator.messages import Text

MESSAGES: dict[str, Text] = {
    "admin.key_not_configured": Text(
        "The server has no admin key: start it with OBSERWATOR_ADMIN_API_KEY or "
        "OBSERWATOR_ADMIN_API_KEY_FILE.",
        "Serwer nie ma klucza administratora: uruchom go z OBSERWATOR_ADMIN_API_KEY "
        "albo OBSERWATOR_ADMIN_API_KEY_FILE.",
    ),
    "admin.key_missing": Text(
        "Send the admin key in the X-Admin-Key header.",
        "Podaj klucz administratora w nagłówku X-Admin-Key.",
    ),
    "admin.key_invalid": Text(
        "The admin key is not valid.",
        "Nieprawidłowy klucz administratora.",
    ),
    "admin.no_report": Text(
        "There is no report {report}.",
        "Nie ma zgłoszenia {report}.",
    ),
    "admin.report_content_type": Text(
        "A change of a report must be sent as application/json.",
        "Zmianę zgłoszenia trzeba wysłać jako application/json.",
    ),
    "admin.report_bad_body": Text(
        'A change of a report is {{"is_read": true}} or {{"is_read": false}}.',
        'Zmiana zgłoszenia to {{"is_read": true}} albo {{"is_read": false}}.',
    ),
    "admin.reports_io_error": Text(
        "The reports could not be read or written. Try again later.",
        "Nie udało się odczytać ani zapisać zgłoszeń. Spróbuj ponownie później.",
    ),
    "admin.check_marker_ok": Text(
        "{root} holds the marker obserwator-data.json; stations of its current "
        "catalogs: {stations}.",
        "{root} ma znacznik obserwator-data.json; stacje jego bieżących katalogów: "
        "{stations}.",
    ),
    "admin.check_marker_missing": Text(
        "{root} has no marker obserwator-data.json: it is no data root of Obserwator, "
        "so the map shows no station.",
        "{root} nie ma znacznika obserwator-data.json: to nie jest katalog danych "
        "Obserwatora, więc mapa nie pokazuje stacji.",
    ),
    "admin.check_root_unreadable": Text(
        "The data root cannot be read: {error}",
        "Nie można odczytać katalogu danych: {error}",
    ),
    "admin.check_analyses_ok": Text(
        "Stored analyses: {versions}.",
        "Zapisane analizy: {versions}.",
    ),
    "admin.check_analyses_partial": Text(
        "Stored analyses: {versions}; none of {providers}, whose stations show no "
        "analysis.",
        "Zapisane analizy: {versions}; brak analiz {providers}, więc ich stacje nie "
        "pokazują analiz.",
    ),
    "admin.check_analyses_none": Text(
        "No stored analyses: no station shows an analysis (obserwator analyses build).",
        "Brak zapisanych analiz: żadna stacja nie pokazuje analiz (obserwator analyses "
        "build).",
    ),
    "admin.check_hydrolog_ok": Text(
        "Hydrolog {version}: a person's choices are computed on request.",
        "Hydrolog {version}: wybory użytkownika są obliczane na żądanie.",
    ),
    "admin.check_hydrolog_missing": Text(
        "No Hydrolog program was found when the server started "
        "(OBSERWATOR_HYDROLOG_COMMAND, else hydrolog on PATH): only stored results "
        "are shown.",
        "Przy starcie serwera nie znaleziono programu Hydrologa "
        "(OBSERWATOR_HYDROLOG_COMMAND, inaczej hydrolog w PATH): widać tylko zapisane "
        "wyniki.",
    ),
    "admin.check_hydrolog_failed": Text(
        "Hydrolog's program does not answer, so computations on request fail: {error}",
        "Program Hydrologa nie odpowiada, więc obliczenia na żądanie się nie udają: "
        "{error}",
    ),
}
