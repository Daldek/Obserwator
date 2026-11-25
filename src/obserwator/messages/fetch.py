"""Messages of ``fetch.py``."""

from obserwator.messages import Text

MESSAGES = {
    "invalid_zip_archive_from": Text(
        "Invalid ZIP archive from {url}",
        "Niepoprawne archiwum ZIP z adresu {url}",
    ),
    "invalid_content_length_header": Text(
        "Invalid Content-Length header: {length}",
        "Niepoprawny nagłówek Content-Length: {length}",
    ),
    "invalid_json_response_from": Text(
        "Invalid JSON response from {url}",
        "Niepoprawna odpowiedź JSON z {url}",
    ),
    "timeout_waiting_server": Text(
        "Timeout waiting for the {source} server: {url}",
        "Przekroczono czas oczekiwania na serwer {source}: {url}",
    ),
    "server_returned_http": Text(
        "The {source} server returned HTTP {status}: {url}",
        "Serwer {source} zwrócił HTTP {status}: {url}",
    ),
    "connection_error_server": Text(
        "Connection error to the {source} server ({exc}): {url}",
        "Błąd połączenia z serwerem {source} ({exc}): {url}",
    ),
    "unexpected_response_from_list_objects": Text(
        "Unexpected response from {url}: a list of objects was expected",
        "Nieoczekiwana odpowiedź z {url}: oczekiwano listy obiektów",
    ),
    "invalid_record_response_from": Text(
        "Invalid record in the response from {url}: {exc}",
        "Niepoprawny rekord w odpowiedzi z {url}: {exc}",
    ),
    "latitude": Text(
        "Latitude",
        "Szerokość",
    ),
    "longitude": Text(
        "Longitude",
        "Długość",
    ),
    "outside_poland": Text(
        "{name} {value!r} is outside Poland ({low}–{high})",
        "{name} geograficzna {value!r} poza zakresem Polski ({low}–{high})",
    ),
    "point_lies_outside_pmaxtp_grid": Text(
        "The point {latitude}, {longitude} lies outside the PMAXTP grid of IMGW-PIB "
        "(no data for this place); API response: {error}",
        "Punkt {latitude}, {longitude} leży poza siatką PMAXTP IMGW-PIB (brak danych "
        "dla tego miejsca); odpowiedź API: {error}",
    ),
    "pmaxtp_api_returned_error": Text(
        "The PMAXTP API returned an error: {error}",
        "API PMAXTP zwróciło błąd: {error}",
    ),
    "invalid_pmaxtp_response": Text(
        "Invalid PMAXTP response: {exc}",
        "Niepoprawna odpowiedź PMAXTP: {exc}",
    ),
    "pmaxtp_response_has_no_data": Text(
        "The PMAXTP response has no data (an empty table ks)",
        "Odpowiedź PMAXTP bez danych (pusta tabela ks)",
    ),
    "unknown_kind_warnings_allowed_hydro": Text(
        "Unknown kind of warnings: {kind!r}; allowed hydro, meteo",
        "Nieznany rodzaj ostrzeżeń: {kind!r}; dozwolone hydro, meteo",
    ),
    "archive_needs_parameter_t_q": Text(
        "The archive {dataset} needs the parameter T, Q or H",
        "Archiwum {dataset} wymaga parametru T, Q albo H",
    ),
    "archive_published_monthly_files_give": Text(
        "The archive {dataset} {year} is published in monthly files; give a month "
        "(1–12)",
        "Archiwum {dataset} {year} jest publikowane w plikach miesięcznych; podaj "
        "miesiąc (1–12)",
    ),
    "year_must_integer": Text(
        "The year must be an integer: {year!r}",
        "Rok musi być liczbą całkowitą: {year!r}",
    ),
    "cannot_save_archive": Text(
        "Cannot save {path}: {exc}",
        "Nie można zapisać {path}: {exc}",
    ),
    "archive_downloaded": Text(
        "Downloaded {server_path}",
        "Pobrano {server_path}",
    ),
    "archive_not_downloaded": Text(
        "Not downloaded {server_path}: {error}",
        "Nie pobrano {server_path}: {error}",
    ),
    "not_in_store": Text(
        "The dataset {dataset} is not kept in the store (download only): use "
        "--output-dir to write plain files",
        "Zbiór {dataset} nie ma miejsca w magazynie (tylko do pobrania): użyj "
        "--output-dir, aby zapisać zwykłe pliki",
    ),
    "pace_until_invalid": Text(
        "Invalid pace_until {value}: expected HH:MM (24-hour local time)",
        "Niepoprawne pace_until {value}: oczekiwano GG:MM (czas lokalny, 24 h)",
    ),
    "paced_request": Text(
        "{time} {status} {url}",
        "{time} {status} {url}",
    ),
    "paced_run_stopped": Text(
        "not asked: the run ended after {failures} connection failures in a row",
        "nie zapytano: przebieg zakończył się po {failures} błędach połączenia z rzędu",
    ),
    "paced_station_skipped": Text(
        "The station {station} is skipped until the next run: HTTP {status} after "
        "{attempts} attempts ({url})",
        "Stacja {station} pominięta do następnego przebiegu: HTTP {status} po "
        "{attempts} próbach ({url})",
    ),
    "paced_not_kept": Text(
        "The capture spool did not keep the answer of {url}",
        "Bufor zapisów nie przyjął odpowiedzi z {url}",
    ),
    # The file a service publishes now (PIG-PIB's tables, ADR-035) is another one.
    "other_file_published": Text(
        "{asked}: the service publishes {published} now, so the file asked is not "
        "published",
        "{asked}: serwis publikuje teraz {published}, więc żądanego pliku nie "
        "opublikowano",
    ),
    # PIG-PIB's ArcGIS queries (ADR-035): an answer that is no query's.
    "arcgis_not_json": Text(
        "The {source} server answered no JSON (an access block page?): {url}",
        "Serwer {source} nie odpowiedział JSON-em (strona blokady dostępu?): {url}",
    ),
    "arcgis_error": Text(
        "The {source} server answered an error {code}: {text} ({url})",
        "Serwer {source} odpowiedział błędem {code}: {text} ({url})",
    ),
    "arcgis_not_page": Text(
        "The {source} server answered no page of rows: {url}",
        "Serwer {source} nie odpowiedział stroną wierszy: {url}",
    ),
    "arcgis_count_changed": Text(
        "The rows of {url} changed during the run, twice: {before} before, {rows} "
        "read, {after} after; nothing was written, the next run asks again",
        "Wiersze {url} zmieniły się w trakcie pobierania, dwukrotnie: {before} przed, "
        "{rows} odczytanych, {after} po; nic nie zapisano, następne uruchomienie "
        "zapyta ponownie",
    ),
}
