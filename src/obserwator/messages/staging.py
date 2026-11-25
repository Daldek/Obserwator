"""Messages of ``store import --staging``: an interim capture into the raw root (ADR-035)."""

from obserwator.messages import Text

MESSAGES = {
    # --- refusals before anything is written ------------------------------------------
    "not_directory": Text(
        "There is no directory {path} of an interim capture",
        "Nie ma katalogu przechwytywania tymczasowego {path}",
    ),
    "no_runs": Text(
        "{path} holds no run of an interim capture "
        "(<YYYY-MM-DDTHHMMSSZ>/manifest.jsonl)",
        "{path} nie zawiera żadnego przebiegu przechwytywania tymczasowego "
        "(<YYYY-MM-DDTHHMMSSZ>/manifest.jsonl)",
    ),
    "manifest_unreadable": Text(
        "Cannot read {path}: {reason}",
        "Nie można odczytać {path}: {reason}",
    ),
    "bad_record": Text(
        "Line {number} of {path} is no record of the interim capture: {field} is "
        "missing or not valid",
        "Wiersz {number} pliku {path} nie jest zapisem przechwytywania "
        "tymczasowego: brak pola {field} albo jest niepoprawne",
    ),
    "not_object": Text(
        "Line {number} of {path} is no JSON object",
        "Wiersz {number} pliku {path} nie jest obiektem JSON",
    ),
    "file_unreadable": Text(
        "{path} names {file}, which cannot be read: {reason}",
        "{path} wskazuje plik {file}, którego nie można odczytać: {reason}",
    ),
    "file_differs": Text(
        "{file} of the run {run} does not match its manifest: {size} bytes, "
        "SHA-256 {sha256}; the manifest says {expected_size} bytes, "
        "{expected_sha256}",
        "{file} przebiegu {run} nie zgadza się z manifestem: {size} B, "
        "SHA-256 {sha256}; manifest podaje {expected_size} B, {expected_sha256}",
    ),
    "no_provider": Text(
        "{path} holds no answer of the interim capture of a provider ({providers})",
        "{path} nie zawiera żadnej odpowiedzi przechwytywania tymczasowego "
        "dostawcy ({providers})",
    ),
    "several_providers": Text(
        "{path} holds answers of several providers: {providers}",
        "{path} zawiera odpowiedzi kilku dostawców: {providers}",
    ),
    "capture_unordered": Text(
        "The capture {version} does not hold its answers in their order",
        "Przechwycenie {version} nie zawiera odpowiedzi w ich kolejności",
    ),
    # --- what a run leaves out (warnings) ---------------------------------------------
    "left_out": Text(
        "{run}: {count} answers of no run of a sync or a harvest left out (the "
        "services' and layers' descriptions, other queries)",
        "{run}: pominięto odpowiedzi spoza przebiegów synchronizacji i zbioru "
        "({count}: opisy usług i warstw, inne zapytania)",
    ),
    "unlisted": Text(
        "{run}: {count} files its manifest does not list left out",
        "{run}: pominięto pliki, których manifest nie wymienia ({count})",
    ),
    "failed": Text(
        "{run}: {count} requests without a good answer left out (an HTTP status "
        "other than 200, an ArcGIS error or no answer)",
        "{run}: pominięto zapytania bez poprawnej odpowiedzi ({count}: status HTTP "
        "inny niż 200, błąd ArcGIS albo brak odpowiedzi)",
    ),
    "incomplete": Text(
        "{run}: {part} is no complete run ({reason}); left out",
        "{run}: {part} nie jest pełnym przebiegiem ({reason}); pominięto",
    ),
    "reason_not_ended": Text(
        "its run stopped before it ended",
        "jego przebieg zatrzymał się przed końcem",
    ),
    "reason_marked": Text(
        "its manifest marks it incomplete",
        "manifest oznacza go jako niepełny",
    ),
    "reason_failed": Text(
        "an answer failed",
        "jedna z odpowiedzi jest błędna",
    ),
    "reason_pages": Text(
        "its pages do not cover the table up to a short page",
        "jego strony nie obejmują tabeli aż do niepełnej strony",
    ),
    "reason_count": Text(
        "{rows} rows read, the counts before and after {counts}",
        "odczytano {rows} wierszy, liczby przed i po {counts}",
    ),
    "empty": Text(
        "{run}: {part} holds no row; left out",
        "{run}: {part} nie zawiera żadnego wiersza; pominięto",
    ),
    "open": Text(
        "{run} has not ended: its complete parts and good answers are imported, "
        "the rest by the next import",
        "{run} się nie zakończył: zaimportowano jego pełne części i poprawne "
        "odpowiedzi, resztę zaimportuje następny import",
    ),
    # --- progress and plan ------------------------------------------------------------
    "run_read": Text(
        "Read the run {run}: {answers} answers match its manifest",
        "Odczytano przebieg {run}: {answers} odpowiedzi zgadza się z manifestem",
    ),
    "version_kept": Text(
        "{run}: {part} kept as {slot}",
        "{run}: {part} zachowano jako {slot}",
    ),
    "day_kept": Text(
        "{answers} answers of the runs of {day} kept as {slot}",
        "{answers} odpowiedzi przebiegów z {day} zachowano jako {slot}",
    ),
    "plan_version": Text(
        "{run}: {part} as {slot}",
        "{run}: {part} jako {slot}",
    ),
    "plan_day": Text(
        "{answers} answers of the runs of {day} as {slot}",
        "{answers} odpowiedzi przebiegów z {day} jako {slot}",
    ),
    "plan_done": Text(
        "Planned the import of the interim capture of {provider}",
        "Zaplanowano import przechwytywania tymczasowego {provider}",
    ),
}
