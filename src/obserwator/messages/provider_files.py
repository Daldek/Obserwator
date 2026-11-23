"""Messages of the providers fed by files (ADR-033): their files, data and ``store import``."""

from obserwator.messages import Text

MESSAGES = {
    # --- the provider file (obserwator._provider_files) --------------------------------
    "bad_list": Text(
        "{key} of [obserwator] must be a list of paths of provider files",
        "{key} w [obserwator] musi być listą ścieżek plików dostawców",
    ),
    "file_missing": Text(
        "There is no provider file {path}",
        "Nie ma pliku dostawcy {path}",
    ),
    "file_unreadable": Text(
        "Cannot read the provider file {path}: {reason}",
        "Nie można odczytać pliku dostawcy {path}: {reason}",
    ),
    "file_too_large": Text(
        "The provider file {path} has more than {maximum} bytes",
        "Plik dostawcy {path} ma więcej niż {maximum} bajtów",
    ),
    "not_utf8": Text(
        "The provider file {path} is not UTF-8 text",
        "Plik dostawcy {path} nie jest tekstem UTF-8",
    ),
    "not_toml": Text(
        "The provider file {path} is not valid TOML: {reason}",
        "Plik dostawcy {path} nie jest poprawnym plikiem TOML: {reason}",
    ),
    "not_table": Text(
        "{field} of a provider file must be a table",
        "{field} w pliku dostawcy musi być tabelą",
    ),
    "unknown_field": Text(
        "A provider file has no field {field}; the fields there: {allowed}",
        "Plik dostawcy nie ma pola {field}; pola w tym miejscu: {allowed}",
    ),
    "missing_field": Text(
        "{field} is missing from the provider file",
        "W pliku dostawcy brakuje pola {field}",
    ),
    "bad_text": Text(
        "{field} of the provider file is {value}; it must be one line of 1 to "
        "{maximum} characters without spaces at its ends",
        "{field} w pliku dostawcy ma wartość {value}; musi być jednym wierszem o "
        "długości od 1 do {maximum} znaków, bez spacji na początku i na końcu",
    ),
    "bad_url": Text(
        "{field} of the provider file is {value}; it must be an address starting "
        "with https:// or http://",
        "{field} w pliku dostawcy ma wartość {value}; musi być adresem "
        "zaczynającym się od https:// albo http://",
    ),
    "bad_choice": Text(
        "{field} of the provider file is {value}; allowed: {allowed}",
        "{field} w pliku dostawcy ma wartość {value}; dozwolone: {allowed}",
    ),
    "bad_id": Text(
        "id of the provider file is {value}; it must be 2 to 16 capital letters "
        "A-Z and digits, a letter first (it starts the provider's station codes)",
        "id w pliku dostawcy ma wartość {value}; musi mieć od 2 do 16 wielkich "
        "liter A-Z i cyfr, zaczynając od litery (rozpoczyna kody stacji dostawcy)",
    ),
    "reserved_id": Text(
        "id {value} is taken: by a provider of Obserwator, an attribution origin or "
        "another provider file",
        "id {value} jest zajęty: przez dostawcę Obserwatora, źródło atrybucji albo "
        "inny plik dostawcy",
    ),
    "publication_of_verified": Text(
        "publication is set only for the tiers telemetry and operational: verified "
        "data are always served",
        "publication ustawia się tylko dla poziomów telemetry i operational: dane "
        "zweryfikowane są zawsze udostępniane",
    ),
    "bad_license_id": Text(
        "license.id of the provider file is {value}; it must be an identifier of "
        "the licence such as CC-BY-4.0 (letters, digits, '.', '+', '_' and '-')",
        "license.id w pliku dostawcy ma wartość {value}; musi być identyfikatorem "
        "licencji, np. CC-BY-4.0 (litery, cyfry, '.', '+', '_' i '-')",
    ),
    "processed_is_line": Text(
        "attribution.processed repeats attribution.line; leave it out when the "
        "processed data carry the line alone",
        "attribution.processed powtarza attribution.line; pomiń je, gdy dane "
        "przetworzone niosą tylko ten wiersz",
    ),
    "bad_links": Text(
        "attribution.links of the provider file must be a list of pairs "
        '[word, address], e.g. [["CC BY 4.0", "https://…"]]',
        "attribution.links w pliku dostawcy musi być listą par [słowo, adres], "
        'np. [["CC BY 4.0", "https://…"]]',
    ),
    "link_not_shown": Text(
        "attribution.links names {word}, which the shown line does not hold: {line}",
        "attribution.links wskazuje {word}, którego nie ma w pokazywanym wierszu: "
        "{line}",
    ),
    "no_dataset": Text(
        "datasets of the provider file must declare at least one of hydro_daily, "
        "meteo_daily and groundwater_daily",
        "datasets w pliku dostawcy musi deklarować co najmniej jeden ze zbiorów "
        "hydro_daily, meteo_daily i groundwater_daily",
    ),
    "bad_variables": Text(
        "{field} of the provider file must be a table of variables and their units, "
        "of: {allowed}",
        "{field} w pliku dostawcy musi być tabelą zmiennych i ich jednostek, spośród: "
        "{allowed}",
    ),
    "unknown_variable": Text(
        "{variable} is no variable of a daily {kind} series; the variables: {allowed}",
        "{variable} nie jest zmienną dobowej serii rodzaju {kind}; zmienne: {allowed}",
    ),
    "bad_unit": Text(
        "The unit of {variable} is {unit}; Obserwator keeps {variable} in {expected}",
        "Jednostka {variable} to {unit}; Obserwator przechowuje {variable} w "
        "{expected}",
    ),
    # --- the registry entries of a provider fed by files (obserwator.datasets) ----------
    "title_hydro_daily": Text(
        "{provider} — daily hydrological data",
        "{provider} — dane hydrologiczne dobowe",
    ),
    "title_meteo_daily": Text(
        "{provider} — daily meteorological data",
        "{provider} — dane meteorologiczne dobowe",
    ),
    "title_groundwater_daily": Text(
        "{provider} — daily groundwater data",
        "{provider} — dane o wodach podziemnych dobowe",
    ),
    "title_unverified": Text(
        "{title}: operational data, unverified",
        "{title}: dane operacyjne, niezweryfikowane",
    ),
    "title_station_list": Text(
        "{provider} — station file",
        "{provider} — plik stacji",
    ),
    "provider_notice": Text(
        "Licence {license}: {url}",
        "Licencja {license}: {url}",
    ),
    # --- the adapter (obserwator.providers.files) ----------------------------------------
    "dataset_fed_by_files": Text(
        "{key} is fed by files of {provider}: store import reads the files its provider "
        "file names, no server publishes them",
        "{key} jest zasilany plikami dostawcy {provider}: store import czyta pliki "
        "wskazane w jego pliku dostawcy, żaden serwer ich nie publikuje",
    ),
    "stations_unreadable": Text(
        "Cannot read the station file {path} of {provider}: {reason}",
        "Nie można odczytać pliku stacji {path} dostawcy {provider}: {reason}",
    ),
    "series_of_other_kind": Text(
        "Station {code} is a {kind} station of the station file, but its series is in "
        "the {series} dataset",
        "Stacja {code} jest w pliku stacji stacją rodzaju {kind}, a jej seria jest w "
        "zbiorze rodzaju {series}",
    ),
    # --- store import (obserwator.store.files) ------------------------------------------
    "not_listed": Text(
        "{path} is no provider file of nogat.toml: give one of the files [obserwator] "
        "provider_files lists (obserwator config show lists them)",
        "{path} nie jest plikiem dostawcy z nogat.toml: podaj jeden z plików, które "
        "wymienia [obserwator] provider_files (wypisuje je obserwator config show)",
    ),
    "data_file_missing": Text(
        "There is no file {path}",
        "Nie ma pliku {path}",
    ),
    "data_not_file": Text(
        "{path} is a directory, not a file",
        "{path} jest katalogiem, nie plikiem",
    ),
    "data_directory_missing": Text(
        "There is no directory {path}",
        "Nie ma katalogu {path}",
    ),
    "series_file_name": Text(
        "{name} is no series file of the provider: a series file is <station code>.csv "
        "or <station code>.parquet, the code matching {pattern}",
        "{name} nie jest plikiem serii dostawcy: plik serii to <kod stacji>.csv albo "
        "<kod stacji>.parquet, a kod pasuje do {pattern}",
    ),
    "series_twice": Text(
        "Station {code} has two series files in one directory: keep one of the CSV "
        "and the Parquet",
        "Stacja {code} ma dwa pliki serii w jednym katalogu: zostaw jeden, CSV albo "
        "Parquet",
    ),
    "series_other_form": Text(
        "The raw root keeps the series of station {code} as {stored}: deliver it in "
        "that form",
        "Magazyn surowy przechowuje serię stacji {code} jako {stored}: dostarcz ją w "
        "tej postaci",
    ),
    "file_kept": Text(
        "Kept {file} in the raw root",
        "Zachowano {file} w magazynie surowym",
    ),
    "plan_file": Text(
        "{file} as {slot}",
        "{file} jako {slot}",
    ),
    "plan_series": Text(
        "series of {dataset}",
        "seria {dataset}",
    ),
    "plan_catalog": Text(
        "{file} of the catalog of {provider}",
        "{file} katalogu stacji {provider}",
    ),
    "plan_done": Text(
        "Planned the import of {provider}",
        "Zaplanowano import {provider}",
    ),
}
