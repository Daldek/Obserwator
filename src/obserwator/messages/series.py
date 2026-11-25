"""Messages of ``store/series.py``."""

from obserwator.messages import Text

MESSAGES = {
    "dataset_does_not_build_measurement": Text(
        "The dataset {dataset} does not build measurement series; allowed: {allowed}",
        "Zbiór {dataset} nie tworzy szeregów pomiarowych; dozwolone: {allowed}",
    ),
    "link_file_instead_version_directory": Text(
        "a link or a file instead of the version directory",
        "dowiązanie lub plik zamiast katalogu wersji",
    ),
    "unknown_schema_no_main_file": Text(
        "an unknown schema or no main file",
        "nieznany schemat lub brak pliku głównego",
    ),
    "no_checksum_label_version": Text(
        "no checksum or label of the version",
        "brak sumy lub etykiety wersji",
    ),
    "corrupt_archive_version": Text(
        "A corrupt archive version {version_dir}: {exc}",
        "Uszkodzona wersja archiwum {version_dir}: {exc}",
    ),
    "invalid_pair_content_sha256_content": Text(
        "an invalid pair content_sha256 and content_form",
        "niepoprawna para content_sha256 i content_form",
    ),
    "path_does_not_belong_dataset": Text(
        "the path {server_path} does not belong to the dataset {dataset}",
        "ścieżka {server_path} nie należy do zbioru {dataset}",
    ),
    "request_does_not_match_path": Text(
        "request.{key} does not match the path {server_path}",
        "request.{key} nie odpowiada ścieżce {server_path}",
    ),
    "version_belongs_another_dataset": Text(
        "The version {relative} belongs to another dataset",
        "Wersja {relative} należy do innego zbioru",
    ),
    "version_does_not_match_slot": Text(
        "The version {relative} does not match the slot {slot}",
        "Wersja {relative} nie odpowiada slotowi {slot}",
    ),
    "building_parquet_series_needs_package": Text(
        "Building Parquet series needs the package pyarrow>=15. {install}",
        "Budowa szeregów Parquet wymaga pakietu pyarrow>=15. {install}",
    ),
    "pyarrow_15_required_version_installed": Text(
        "pyarrow>=15 is required (version {version} is installed). {install}",
        "Wymagany pyarrow>=15 (zainstalowano {version}). {install}",
    ),
    "conflicting_values_station": Text(
        "Conflicting {variable} values of the station {code} on {day}",
        "Sprzeczne wartości {variable} stacji {code} z {day}",
    ),
    "conflicting_dates_extremum_station": Text(
        "Conflicting dates of the extremum of {variable} of the station {code}",
        "Sprzeczne daty ekstremum {variable} stacji {code}",
    ),
    "conflicting_number_occurrences_extremum_station": Text(
        "A conflicting number of occurrences of the extremum of {variable} of the "
        "station {code}",
        "Sprzeczna liczba wystąpień ekstremum {variable} stacji {code}",
    ),
    "invalid_station_code": Text(
        "An invalid station code: {code!r}",
        "Nieprawidłowy kod stacji: {code!r}",
    ),
    "unknown_variable_dataset": Text(
        "Unknown variable {variable} in the dataset {key}",
        "Nieznana zmienna {variable} w zbiorze {key}",
    ),
    "inconsistent_flag_variable_station": Text(
        "An inconsistent flag {flag} of the variable {variable} of the station {code}",
        "Niespójna flaga {flag} zmiennej {variable} stacji {code}",
    ),
    "disallowed_quality_source_flag_variable": Text(
        "A disallowed quality {quality!r} or source flag {source_flag!r} of the "
        "variable {variable} of the station {code} on {date}",
        "Niedozwolona jakość {quality!r} lub flaga źródła {source_flag!r} zmiennej "
        "{variable} stacji {code} z {date}",
    ),
    "record_station_file_station": Text(
        "A record of the station {station_code} in the file of the station {code}: "
        "{server_path}",
        "Rekord stacji {station_code} w pliku stacji {code}: {server_path}",
    ),
    "checksum_does_not_match_sidecar": Text(
        "The checksum does not match the sidecar: {relative}",
        "Suma kontrolna nie zgadza się z sidecarem: {relative}",
    ),
    "series_version_directory_collision": Text(
        "A series version directory collision: {parent}",
        "Kolizja katalogu wersji szeregu: {parent}",
    ),
    "input_progress": Text(
        "Series input {relative}",
        "Wejście szeregu {relative}",
    ),
    "series_current": Text(
        "The series {slug} matches the current archives",
        "Szereg {slug} odpowiada bieżącym archiwom",
    ),
    "series_needs_rebuild": Text(
        "The series {slug} needs a rebuild",
        "Szereg {slug} wymaga przebudowy",
    ),
    "series_missing": Text(
        "No series {slug}",
        "Brak szeregu {slug}",
    ),
    "no_archives_of_dataset": Text(
        "No archives of the dataset {dataset} in the store",
        "Brak archiwów zbioru {dataset} w magazynie",
    ),
    "no_input_files": Text(
        "The raw root holds no file of {inputs} that {key} is built from",
        "Katalog surowy nie zawiera plików {inputs}, z których powstaje {key}",
    ),
    "series_inputs_unchanged": Text(
        "The series {slug} has unchanged inputs",
        "Szereg {slug} bez zmian wejść",
    ),
    "archive_read": Text(
        "Read {relative}",
        "Odczytano {relative}",
    ),
    "station_progress": Text(
        "Station {code}",
        "Stacja {code}",
    ),
    "stations_not_list": Text(
        "stations must be a non-empty list of station codes",
        "stations musi być niepustą listą kodów stacji",
    ),
    "stations_outside_grammar": Text(
        "Station codes outside the {provider} grammar of the dataset {key}: {codes}; "
        "expected {pattern}",
        "Kody stacji spoza gramatyki {provider} zbioru {key}: {codes}; oczekiwano "
        "{pattern}",
    ),
    "invalid_subset": Text(
        "an invalid subset: stations and years must be sorted, distinct and not empty",
        "niepoprawny podzbiór: stations i years muszą być posortowane, bez powtórzeń "
        "i niepuste",
    ),
    "subset_beside_full_series": Text(
        "The data root holds the full series of {key} ({version}); a subset of its "
        "stations or years is never built beside it",
        "Katalog danych zawiera pełny szereg {key} ({version}); podzbioru jego stacji "
        "ani lat nie buduje się obok niego",
    ),
    "no_archives_of_subset": Text(
        "The raw root holds no archive of {key} for the chosen stations and years",
        "Katalog surowy nie zawiera archiwów {key} dla wybranych stacji i lat",
    ),
    "subset_holds_nothing": Text(
        "The archives read hold no records of the chosen stations and years of {key}",
        "Odczytane archiwa nie zawierają rekordów wybranych stacji i lat {key}",
    ),
    "stations_missing": Text(
        "The archives of {key} read hold no records of the stations {codes}",
        "Odczytane archiwa {key} nie zawierają rekordów stacji {codes}",
    ),
    # The hourly series built per calendar month (ADR-031).
    "option_needs_monthly": Text(
        "{option} applies only to the hourly series built per calendar month "
        "({allowed}); {key} is built whole or as a subset of stations and years",
        "{option} dotyczy tylko szeregów godzinowych budowanych w miesiącach "
        "kalendarzowych ({allowed}); {key} buduje się w całości albo jako podzbiór "
        "stacji i lat",
    ),
    "monthly_option_refused": Text(
        "{option} does not apply to {key}: an hourly series is built per calendar "
        "month, the months chosen with start and end",
        "{option} nie dotyczy {key}: szereg godzinowy buduje się w miesiącach "
        "kalendarzowych, wybieranych przez start i end",
    ),
    "range_bound_not_date": Text(
        "The range bound {bound} is not a date (YYYY-MM-DD)",
        "Granica zakresu {bound} nie jest datą (RRRR-MM-DD)",
    ),
    "start_later_than_end": Text(
        "The start of the range {start} is later than its end {end}",
        "Początek zakresu {start} jest późniejszy niż koniec {end}",
    ),
    "month_without_value": Text(
        "No input of {key} holds a value of {month}",
        "Żadne wejście {key} nie zawiera wartości z {month}",
    ),
    "no_inputs_of_months": Text(
        "The raw root holds no input of {key} in the chosen months",
        "Katalog surowy nie zawiera wejść {key} w wybranych miesiącach",
    ),
    "inputs_hold_no_value": Text(
        "The inputs of {key} hold no value of any month",
        "Wejścia {key} nie zawierają wartości z żadnego miesiąca",
    ),
    "month_current": Text(
        "The series {slug} of {month} matches its current inputs",
        "Szereg {slug} z {month} odpowiada bieżącym wejściom",
    ),
    "month_needs_rebuild": Text(
        "The series {slug} of {month} needs a rebuild",
        "Szereg {slug} z {month} wymaga przebudowy",
    ),
    "month_missing": Text(
        "No series {slug} of {month}",
        "Brak szeregu {slug} z {month}",
    ),
    "month_inputs_unchanged": Text(
        "The series {slug} of {month} has unchanged inputs",
        "Szereg {slug} z {month} bez zmian wejść",
    ),
    "month_progress": Text(
        "Month {month}",
        "Miesiąc {month}",
    ),
    "input_unreadable": Text(
        "The input {relative} cannot be read: {reason}",
        "Nie można odczytać wejścia {relative}: {reason}",
    ),
}
