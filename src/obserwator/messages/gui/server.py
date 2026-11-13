"""The GUI server's own texts: its start, its errors and the notices of its answers."""

from obserwator.messages import Text

MESSAGES: dict[str, Text] = {
    "server.needs_extra": Text(
        "The GUI needs the gui extra (Starlette, uvicorn, pyarrow): cannot import {module}",
        "GUI potrzebuje dodatku gui (Starlette, uvicorn, pyarrow): nie można zaimportować {module}",
    ),
    "server.bad_basemap_url": Text(
        "The basemap address {url} is not an http or https URL; set gui_basemap_url "
        "to a TileJSON address or to none",
        "Adres mapy podkładowej {url} nie jest adresem http ani https; ustaw "
        "gui_basemap_url na adres TileJSON albo none",
    ),
    "server.listening": Text("Obserwator GUI: {url}", "GUI Obserwatora: {url}"),
    "server.bad_host": Text(
        "Cannot listen on {host}: {reason}", "Nie można nasłuchiwać na {host}: {reason}"
    ),
    "server.port_in_use": Text(
        "Port {port} of {host} is in use; stop the program that uses it or choose "
        "another with --port.",
        "Port {port} adresu {host} jest zajęty; zatrzymaj program, który go używa, "
        "albo wybierz inny opcją --port.",
    ),
    "server.state_in_root": Text(
        "The GUI keeps its own files in {state_dir}, which overlaps the data root "
        "{root}: it writes none of them (no statistics, no access log, no reports). "
        "Serve a root outside {state_dir} or set another data_dir.",
        "GUI trzyma własne pliki w {state_dir}, który pokrywa się z katalogiem danych "
        "{root}: nie zapisuje żadnego z nich (bez statystyk, dziennika dostępu i "
        "zgłoszeń). Wskaż katalog danych poza {state_dir} albo ustaw inny data_dir.",
    ),
    "errors.bad_parameter": Text(
        "Invalid value of {option}: {value}", "Niepoprawna wartość {option}: {value}"
    ),
    "errors.title_rate_limited": Text("Too many requests", "Zbyt wiele żądań"),
    "errors.no_analysis": Text(
        "There is no analysis {analysis}.", "Nie ma analizy {analysis}."
    ),
    "errors.analysis_not_for_station": Text(
        "The analysis {analysis} does not apply to the station {station}: it lacks the "
        "series the analysis needs.",
        "Analiza {analysis} nie dotyczy stacji {station}: stacja nie ma szeregu, "
        "którego analiza potrzebuje.",
    ),
    "errors.no_hydrolog": Text(
        "This server computes no analyses on request (no Hydrolog program is set).",
        "Ten serwer nie liczy analiz na żądanie (nie wskazano programu Hydrologa).",
    ),
    "errors.hydrolog_failed": Text(
        "Hydrolog's program could not compute the analysis: {reason}",
        "Program Hydrologa nie policzył analizy: {reason}",
    ),
    "errors.hydrolog_timeout": Text(
        "Hydrolog did not finish within {seconds} s; choose a shorter period.",
        "Hydrolog nie skończył w ciągu {seconds} s; wybierz krótszy okres.",
    ),
    "errors.no_station": Text(
        "There is no station {station} in the catalogs.",
        "W katalogach nie ma stacji {station}.",
    ),
    "errors.no_series": Text(
        "The station {station} has no series of {dataset}.",
        "Stacja {station} nie ma szeregu zbioru {dataset}.",
    ),
    "errors.no_dataset": Text(
        "There is no series of the dataset {dataset} in the data root.",
        "W katalogu danych nie ma szeregów zbioru {dataset}.",
    ),
    "errors.no_stations": Text(
        "The catalogs hold no station of the chosen provider and kind.",
        "Katalogi nie mają stacji wybranego dostawcy i rodzaju.",
    ),
    "errors.feedback_off": Text(
        "Reports are off on this server.",
        "Zgłaszanie uwag jest na tym serwerze wyłączone.",
    ),
    "errors.not_found": Text("Nothing here: {path}", "Nic tu nie ma: {path}"),
    "errors.method_not_allowed": Text(
        "The method {method} is not allowed here; allowed: {allowed}.",
        "Metoda {method} jest tu niedozwolona; dozwolone: {allowed}.",
    ),
    "errors.no_current": Text(
        "IMGW-PIB's current data are not available now.",
        "Dane bieżące IMGW-PIB są teraz niedostępne.",
    ),
    "errors.no_current_chmi": Text(
        "ČHMÚ's current data are not provided.",
        "Dane bieżące ČHMÚ nie są udostępniane.",
    ),
    "errors.no_values": Text(
        "The chosen years hold no values of {variable}.",
        "W wybranych latach nie ma wartości {variable}.",
    ),
    "errors.stripes_no_years": Text(
        "The climate stripes of the station {station} need at least two years with an "
        "annual mean temperature.",
        "Paski klimatyczne stacji {station} potrzebują co najmniej dwóch lat ze średnią "
        "roczną temperatury.",
    ),
    "errors.stripes_no_normal": Text(
        "The normal of the annual mean temperature of the station {station} cannot be "
        "computed, not even over its whole record: the climate stripes have no centre.",
        "Normalnej średniej rocznej temperatury stacji {station} nie da się policzyć "
        "nawet z całego zapisu: paski klimatyczne nie mają środka skali.",
    ),
    "errors.stripes_no_spread": Text(
        "The annual mean temperatures of the station {station} do not vary: the climate "
        "stripes have no colour scale.",
        "Średnie roczne temperatury stacji {station} się nie różnią: paski klimatyczne "
        "nie mają skali kolorów.",
    ),
    "handoff.subject_daily": Text(
        "{station} — {variable}, daily values",
        "{station} — {variable}, wartości dobowe",
    ),
    "handoff.subject_annual": Text(
        "{station} — {variable}, annual maxima",
        "{station} — {variable}, maksima roczne",
    ),
}
