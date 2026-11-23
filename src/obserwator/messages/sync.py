"""Messages of ``store/sync.py``."""

from obserwator.messages import Text

MESSAGES = {
    "parameter_datasets_must_list_dataset": Text(
        "The parameter datasets must be a list of dataset keys",
        "Parametr datasets musi być listą kluczy zbiorów",
    ),
    "choose_least_one_dataset": Text(
        "Choose at least one dataset",
        "Wybierz co najmniej jeden zbiór",
    ),
    "dataset_keeps_no_archives": Text(
        "store sync keeps no source files of the dataset {dataset}; allowed: {allowed}",
        "store sync nie zapisuje plików źródłowych zbioru {dataset}; dozwolone: "
        "{allowed}",
    ),
    "imgw_archives_cover_whole": Text(
        "The IMGW-PIB archives cover the whole country; the option stations applies "
        "only to station datasets (ČHMÚ, the IMGW-PIB synop archives)",
        "Archiwa IMGW-PIB obejmują cały kraj; opcja stations dotyczy wyłącznie "
        "zbiorów stacji (ČHMÚ, archiwa synop IMGW-PIB)",
    ),
    "imgw_datasets_need_option": Text(
        "The IMGW-PIB datasets need the option years",
        "Zbiory IMGW-PIB wymagają opcji years",
    ),
    "datasets_need_option_stations_station": Text(
        "The datasets {keys} need the option stations: station codes (the source "
        "files cover single stations)",
        "Zbiory {keys} wymagają opcji stations: kodów stacji (pliki źródła obejmują "
        "pojedyncze stacje)",
    ),
    "option_months_does_not_apply": Text(
        "The option months does not apply to the datasets {keys}: the station files "
        "are not monthly",
        "Opcja months nie dotyczy zbiorów {keys}: pliki stacji nie są miesięczne",
    ),
    "option_months_station_month": Text(
        "The option months does not apply to the datasets {keys}: years chooses the "
        "month files, every published month of each year",
        "Opcja months nie dotyczy zbiorów {keys}: years wybiera pliki miesięczne, "
        "każdy opublikowany miesiąc każdego roku",
    ),
    "one_call_covers_datasets_one": Text(
        "One call covers datasets of one kind: national IMGW-PIB archives (without "
        "the option stations), IMGW-PIB's telemetry (without stations), the IMGW-PIB "
        "synop station archives (stations optional) or ČHMÚ station files (with the "
        "option stations); given {names}",
        "Jedno wywołanie obejmuje zbiory jednego rodzaju: archiwa krajowe IMGW-PIB "
        "(bez opcji stations), telemetrię IMGW-PIB (bez stations), archiwa stacji "
        "synoptycznych IMGW-PIB (stations opcjonalne) albo pliki stacji ČHMÚ (z "
        "opcją stations); podano {names}",
    ),
    "plan_must_written_outside_store": Text(
        "The plan must be written outside the store: {target}",
        "Plan musi być zapisany poza magazynem: {target}",
    ),
    "directory_plan_file_does_not": Text(
        "The directory of the plan file does not exist: {parent}",
        "Katalog pliku planu nie istnieje: {parent}",
    ),
    "give_plan_selectors_datasets_years": Text(
        "Give a plan or the selectors datasets/years/months/stations/pace_until, not "
        "both",
        "Podaj plan albo selektory datasets/years/months/stations/pace_until, nie oba "
        "naraz",
    ),
    "without_plan_parameter_datasets_required": Text(
        "Without a plan the parameter datasets is required",
        "Bez planu wymagany jest parametr datasets",
    ),
    "plan_concerns_another_store": Text(
        "The plan concerns another store: {root}",
        "Plan dotyczy innego magazynu: {root}",
    ),
    "no_comparable_header": Text(
        "no comparable ETag/Last-Modified header",
        "brak porównywalnego nagłówka ETag/Last-Modified",
    ),
    "no_comparable_signal": Text(
        "no comparable signal",
        "brak porównywalnego sygnału",
    ),
    "station_no_files": Text(
        "station {code}: no files of the dataset {key} at the source",
        "stacja {code}: brak plików zbioru {key} u źródła",
    ),
    "listing_without_dataset_files": Text(
        "Unreadable listing {base_url}{directory}/: no files of the dataset {key}",
        "Nieczytelny listing {base_url}{directory}/: brak plików zbioru {key}",
    ),
    "folder_unpublished": Text(
        "folder {directory}: not published, no files of the dataset {key}",
        "folder {directory}: nieopublikowany, brak plików zbioru {key}",
    ),
    "folder_error": Text(
        "folder {directory} of the server: {error}",
        "folder {directory} serwera: {error}",
    ),
    "station_error": Text(
        "station {code}: {error}",
        "stacja {code}: {error}",
    ),
    "skipped_sync_from_plan": Text(
        "{server_path}: {error}; skipped while syncing from the plan",
        "{server_path}: {error}; pominięto przy synchronizacji z planu",
    ),
    "download_and_compare": Text(
        "{server_path}: {error}; the file is downloaded and its SHA-256 compared",
        "{server_path}: {error}; pobieranie i porównanie sumy SHA-256",
    ),
    "stale_plan": Text(
        "{server_path}: the server headers changed since the plan was checked",
        "{server_path}: nagłówki serwera zmieniły się od sprawdzenia planu",
    ),
    "timeout_waiting_for_server": Text(
        "Timed out waiting for the {source} server: {reason}",
        "Przekroczono czas odpowiedzi serwera {source}: {reason}",
    ),
    "http_error": Text(
        "HTTP error {status}: {url}",
        "Błąd HTTP {status}: {url}",
    ),
    "connection_error": Text(
        "Connection error to {source}: {reason}",
        "Błąd połączenia z {source}: {reason}",
    ),
    "plain_needs_years": Text(
        "The datasets {keys} need the option years in plain mode: the store reads "
        "the years from the server listing, a plain write does not",
        "Zbiory {keys} wymagają w trybie plain opcji years: magazyn czyta lata z "
        "listingu serwera, zwykły zapis go nie używa",
    ),
    "store_only_option": Text(
        "The option {name} acts on versions of a store: it is valid only with "
        "root, not with output_dir",
        "Opcja {name} działa na wersjach magazynu: jest ważna tylko z root, nie z "
        "output_dir",
    ),
    "station_sources_alone": Text(
        "Station sources (station lists and station metadata, *_stations, *_now and "
        "pl.imgw.*_details) are synchronized in a call of their own, without "
        "measurement datasets",
        "Źródła stacji (listy i metadane stacji, *_stations, *_now i "
        "pl.imgw.*_details) synchronizuje osobne wywołanie, bez zbiorów "
        "pomiarowych",
    ),
    "option_not_for_station_sources": Text(
        "The option {option} does not apply to station sources: each is one file of "
        "the whole country",
        "Opcja {option} nie dotyczy źródeł stacji: każde jest jednym plikiem całego "
        "kraju",
    ),
    "station_sources_store_only": Text(
        "Station sources are stored only in a store, where store catalog reads them; "
        "give root, not output_dir",
        "Źródła stacji zapisuje się tylko w magazynie, gdzie czyta je store catalog; "
        "podaj root, nie output_dir",
    ),
    "captures_alone": Text(
        "Capture datasets (*_current, *_operational, cz.chmu.hydro_recent) are sealed "
        "from the capture spool in a call of their own, without other datasets",
        "Zbiory zapisów (*_current, *_operational, cz.chmu.hydro_recent) zamyka z "
        "bufora zapisów osobne wywołanie, bez innych zbiorów",
    ),
    "option_not_for_captures": Text(
        "The option {option} does not apply to capture datasets: every closed UTC day "
        "of the spool is sealed",
        "Opcja {option} nie dotyczy zbiorów zapisów: zamykana jest każda zakończona "
        "doba UTC bufora",
    ),
    "captures_store_only": Text(
        "Capture datasets are sealed only into a store; give root, not output_dir",
        "Zbiory zapisów zamyka się tylko w magazynie; podaj root, nie output_dir",
    ),
    "pace_until_not_harvested": Text(
        "pace_until harvests one dataset of pl.imgw.hydro_operational and "
        "cz.chmu.hydro_recent in a call; given {keys}",
        "pace_until pobiera jeden zbiór spośród pl.imgw.hydro_operational i "
        "cz.chmu.hydro_recent na wywołanie; podano {keys}",
    ),
    "harvest_planned": Text(
        "{dataset}: its source is asked for the UTC day {day} ({stations}), spread "
        "until {until}, before its spool is sealed with today's day",
        "{dataset}: źródło jest pytane o dobę UTC {day} ({stations}) z odstępami do "
        "{until}, zanim bufor zostanie zamknięty razem z dobą dzisiejszą",
    ),
    "harvest_every": Text(
        "every station of its list",
        "każda stacja z jego listy",
    ),
    "station_source_no_signal": Text(
        "no stable freshness signal: the answer or its envelope is regenerated, so "
        "store sync downloads it and compares the content",
        "brak stabilnego sygnału aktualności: odpowiedź lub jej koperta jest "
        "generowana na nowo, więc store sync ją pobiera i porównuje treść",
    ),
    "station_source_listing": Text(
        "{key}: {error} (the listing does not name the newest file)",
        "{key}: {error} (listing nie wskazuje najnowszego pliku)",
    ),
    "no_file_in_listing": Text(
        "no file of the dataset in the listing",
        "brak pliku zbioru w listingu",
    ),
}
