"""Messages of ``_parsing/__init__.py``, ``_parsing/common.py``, ``_parsing/stations.py`` and ``_parsing/files.py``."""

from obserwator.messages import Text

MESSAGES = {
    "no_parser_archive": Text(
        "No parser for the archive: {dataset}",
        "Brak parsera archiwum: {dataset}",
    ),
    "archive_too_large": Text(
        "The archive {filename} is too large",
        "Zbyt duże archiwum {filename}",
    ),
    "path_not_allowed": Text(
        "A path not allowed in {filename}: {name}",
        "Niedozwolona ścieżka w {filename}: {name}",
    ),
    "csv_too_large": Text(
        "The CSV is too large in {filename}: {name}",
        "Zbyt duży CSV w {filename}: {name}",
    ),
    "unreadable_archive": Text(
        "Unreadable archive {filename}: {exc}",
        "Nieczytelne archiwum {filename}: {exc}",
    ),
    "unknown_kind_station_list_allowed": Text(
        "Unknown kind of station list: {kind!r}; allowed: hydro, meteo",
        "Nieznany rodzaj listy stacji: {kind!r}; dozwolone hydro, meteo",
    ),
    "zip_archive": Text(
        "ZIP archive",
        "archiwum ZIP",
    ),
    # --- the files of a provider fed by files (_parsing/files.py, ADR-033) -------------
    "provider_file_data": Text(
        "{filename}: {problem}",
        "{filename}: {problem}",
    ),
    "station_file_too_large": Text(
        "the station file has more than {maximum} bytes",
        "plik stacji ma więcej niż {maximum} bajtów",
    ),
    "station_file_not_json": Text(
        "the station file is no UTF-8 JSON: {reason}",
        "plik stacji nie jest JSON-em w UTF-8: {reason}",
    ),
    "station_file_not_collection": Text(
        "the station file is no GeoJSON FeatureCollection with a list of features",
        "plik stacji nie jest kolekcją GeoJSON (FeatureCollection) z listą obiektów",
    ),
    "station_file_crs": Text(
        "the station file names the coordinate system {crs}; only WGS84 longitude "
        "and latitude are read",
        "plik stacji wskazuje układ współrzędnych {crs}; czytane są tylko długość i "
        "szerokość geograficzna WGS84",
    ),
    "station_not_feature": Text(
        "an element of features is no GeoJSON Feature",
        "element features nie jest obiektem GeoJSON (Feature)",
    ),
    "station_without_properties": Text(
        "a station has no properties object",
        "stacja nie ma obiektu properties",
    ),
    "station_bad_code": Text(
        "station_code {code} does not match {pattern}",
        "station_code {code} nie pasuje do {pattern}",
    ),
    "station_unknown_field": Text(
        "station {code} has the property {field}, which a station file has not; the "
        "properties: {allowed}",
        "stacja {code} ma właściwość {field}, której plik stacji nie ma; właściwości: "
        "{allowed}",
    ),
    "station_missing_field": Text(
        "station {code} has no {field}",
        "stacja {code} nie ma {field}",
    ),
    "station_bad_kind": Text(
        "station {code} has the kind {kind}; allowed: {allowed}",
        "stacja {code} ma rodzaj {kind}; dozwolone: {allowed}",
    ),
    "station_bad_field": Text(
        "station {code} has a value of {field} of the wrong type or range",
        "stacja {code} ma wartość {field} złego typu lub spoza zakresu",
    ),
    "station_not_point": Text(
        "the geometry of station {code} is no Point of two coordinates, nor null",
        "geometria stacji {code} nie jest punktem (Point) o dwóch współrzędnych ani "
        "null",
    ),
    "station_bad_point": Text(
        "the point of station {code} is not a longitude from -180 to 180 and a "
        "latitude from -90 to 90",
        "punkt stacji {code} nie jest długością od -180 do 180 i szerokością od -90 "
        "do 90",
    ),
    "station_repeated": Text(
        "station {code} is given twice",
        "stacja {code} występuje dwukrotnie",
    ),
    "series_not_utf8": Text(
        "the series file is not UTF-8 text",
        "plik serii nie jest tekstem UTF-8",
    ),
    "series_not_csv": Text(
        "the series file is no CSV: {reason}",
        "plik serii nie jest plikiem CSV: {reason}",
    ),
    "series_not_parquet": Text(
        "the series file is no readable Parquet: {reason}",
        "plik serii nie jest czytelnym plikiem Parquet: {reason}",
    ),
    "series_no_date": Text(
        "the first column of the series file must be date; found: {found}",
        "pierwszą kolumną pliku serii musi być date; znaleziono: {found}",
    ),
    "series_repeated_column": Text(
        "the series file has the column {column} twice",
        "plik serii ma kolumnę {column} dwukrotnie",
    ),
    "series_unknown_variable": Text(
        "the series file has the variable {variable}, which its dataset has not; the "
        "variables: {allowed}",
        "plik serii ma zmienną {variable}, której jego zbiór nie ma; zmienne: "
        "{allowed}",
    ),
    "series_bad_unit": Text(
        "the series file gives {variable} in {unit}; its dataset keeps it in "
        "{expected}",
        "plik serii podaje {variable} w {unit}; jego zbiór przechowuje ją w {expected}",
    ),
    "series_unknown_column": Text(
        "the series file has the column {column}; the columns: date, year, "
        "<V> [<unit>] and <V>_flag of {allowed}, attribution and terms_notice",
        "plik serii ma kolumnę {column}; kolumny: date, year, <V> [<jednostka>] i "
        "<V>_flag spośród {allowed}, attribution i terms_notice",
    ),
    "series_flag_alone": Text(
        "the series file has {variable}_flag without the values of {variable}",
        "plik serii ma {variable}_flag bez wartości {variable}",
    ),
    "series_no_variable": Text(
        "the series file has no column of values",
        "plik serii nie ma żadnej kolumny wartości",
    ),
    "series_no_rows": Text(
        "the series file has no row",
        "plik serii nie ma żadnego wiersza",
    ),
    "series_bad_row": Text(
        "row {row} of the series file has {found} cells; its header has {expected}",
        "wiersz {row} pliku serii ma {found} komórek; jego nagłówek ma {expected}",
    ),
    "series_bad_date": Text(
        "row {row} of the series file has the date {value}; a date is YYYY-MM-DD",
        "wiersz {row} pliku serii ma datę {value}; data ma postać RRRR-MM-DD",
    ),
    "series_repeated_date": Text(
        "row {row} of the series file repeats the date {day}",
        "wiersz {row} pliku serii powtarza datę {day}",
    ),
    "series_bad_value": Text(
        "row {row} of the series file has {value} as {variable}; a value is a finite "
        "number with a dot",
        "wiersz {row} pliku serii ma {value} jako {variable}; wartość jest skończoną "
        "liczbą z kropką dziesiętną",
    ),
    "series_bad_flag": Text(
        "row {row} of the series file has the flag {flag} of {variable}; allowed: "
        "{allowed}",
        "wiersz {row} pliku serii ma flagę {flag} zmiennej {variable}; dozwolone: "
        "{allowed}",
    ),
    "series_flag_mismatch": Text(
        "row {row} of the series file: the flag {flag} of {variable} does not agree "
        "with its value (missing has none, no_phenomenon 0 or none, the others a "
        "number)",
        "wiersz {row} pliku serii: flaga {flag} zmiennej {variable} nie zgadza się z "
        "wartością (missing nie ma wartości, no_phenomenon ma 0 lub brak, pozostałe "
        "liczbę)",
    ),
    # Gdańskie Wody's answers and month files (ADR-034): where and what is wrong.
    "gdanskiewody_bad_content": Text(
        "Gdańskie Wody's answer {filename} cannot be read at {where}: {problem}",
        "Nie można odczytać odpowiedzi Gdańskich Wód {filename} w miejscu {where}: "
        "{problem}",
    ),
    "gdanskiewody_not_json": Text("it is no JSON", "to nie jest JSON"),
    "gdanskiewody_not_json_object": Text(
        "a JSON object was expected", "oczekiwano obiektu JSON"
    ),
    "gdanskiewody_not_json_list": Text(
        "a JSON list was expected", "oczekiwano listy JSON"
    ),
    "gdanskiewody_not_text": Text("a text was expected", "oczekiwano tekstu"),
    "gdanskiewody_not_number": Text(
        "a finite number was expected", "oczekiwano skończonej liczby"
    ),
    "gdanskiewody_not_integer": Text(
        "an integer was expected", "oczekiwano liczby całkowitej"
    ),
    "gdanskiewody_not_boolean": Text(
        "true or false was expected", "oczekiwano true albo false"
    ),
    "gdanskiewody_not_date": Text(
        "a date YYYY-MM-DD was expected", "oczekiwano daty RRRR-MM-DD"
    ),
    "gdanskiewody_not_success": Text(
        "the status is {status!r}, not success", "status to {status!r}, nie success"
    ),
    "gdanskiewody_bad_number": Text(
        "the station number {number} is not 1 to 999",
        "numer stacji {number} nie mieści się w zakresie 1–999",
    ),
    "gdanskiewody_bad_label": Text(
        "a label YYYY-MM-DD HH:00:00 was expected",
        "oczekiwano etykiety RRRR-MM-DD GG:00:00",
    ),
    "gdanskiewody_bad_pair": Text(
        "a pair [label, value] was expected", "oczekiwano pary [etykieta, wartość]"
    ),
    "gdanskiewody_label_outside_day": Text(
        "the label lies outside the provider's day {day} (06:00 to 05:00 UTC)",
        "etykieta leży poza dobą dostawcy {day} (od 06:00 do 05:00 UTC)",
    ),
    "gdanskiewody_label_twice": Text(
        "the label is given twice in the day's answer",
        "etykieta występuje w odpowiedzi doby dwa razy",
    ),
    "gdanskiewody_day_outside_file": Text(
        "the day lies outside the file's month ({first} to {last})",
        "dzień leży poza miesiącem pliku (od {first} do {last})",
    ),
    "gdanskiewody_bad_name": Text(
        "the name is no rest/measurements/<no>/<symbol>/<YYYY-MM>.json",
        "nazwa nie ma postaci rest/measurements/<no>/<symbol>/<YYYY-MM>.json",
    ),
    # PIG-PIB's captures of ArcGIS pages (ADR-035): where and what is wrong.
    "pig_invalid": Text(
        "PIG-PIB's capture {filename} cannot be read at {where}: {problem}",
        "Nie można odczytać zapisu PIG-PIB {filename} w miejscu {where}: {problem}",
    ),
    "pig_line": Text("line {number}", "wiersz {number}"),
    "pig_row": Text(
        "row {number} of the answer {address}", "wiersz {number} odpowiedzi {address}"
    ),
    "pig_not_object": Text(
        "no answer of a capture (time, address, status, body)",
        "to nie jest odpowiedź zapisu (czas, adres, status, treść)",
    ),
    "pig_seen_alone": Text(
        "a repeated answer follows no answer of its address",
        "powtórzona odpowiedź nie następuje po odpowiedzi z jej adresu",
    ),
    "pig_body_sha": Text(
        "the body does not match its SHA-256", "treść nie zgadza się ze swoim SHA-256"
    ),
    "pig_no_attributes": Text("the row has no attributes", "wiersz nie ma atrybutów"),
    "pig_not_number": Text(
        "a finite number was expected, not {value!r}",
        "oczekiwano skończonej liczby, a nie {value!r}",
    ),
    "pig_no_id": Text(
        "the row names no point (a positive integer) or no time",
        "wiersz nie wskazuje punktu (dodatniej liczby całkowitej) ani czasu",
    ),
    "pig_id_twice": Text(
        "the point's ID is given twice with other attributes",
        "ID punktu występuje dwa razy z innymi atrybutami",
    ),
    "pig_bad_day": Text(
        "DATA_POMIARU {value!r} is no date YYYY-MM-DD",
        "DATA_POMIARU {value!r} nie jest datą RRRR-MM-DD",
    ),
    "pig_two_readings": Text(
        "the point {point} has two different readings of {day}",
        "punkt {point} ma dwa różne pomiary z dnia {day}",
    ),
}
