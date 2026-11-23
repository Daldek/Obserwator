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
    "server.bad_host": Text(
        "Cannot listen on {host}: {reason}", "Nie można nasłuchiwać na {host}: {reason}"
    ),
    "server.port_in_use": Text(
        "Port {port} of {host} is in use; stop the program that uses it or choose "
        "another with --port.",
        "Port {port} adresu {host} jest zajęty; zatrzymaj program, który go używa, "
        "albo wybierz inny opcją --port.",
    ),
    "server.gui_dir_in_root": Text(
        "The GUI keeps its own files in {gui_dir}, which overlaps the data root "
        "{root}: it writes none of them (no statistics, no reports). "
        "Serve a root outside {gui_dir} or set another data_dir.",
        "GUI trzyma własne pliki w {gui_dir}, który pokrywa się z katalogiem danych "
        "{root}: nie zapisuje żadnego z nich (bez statystyk i zgłoszeń). "
        "Wskaż katalog danych poza {gui_dir} albo ustaw inny data_dir.",
    ),
    "server.upstream_records": Text(
        "IMGW-PIB {source}: answered in {duration_ms} ms, {records} records",
        "IMGW-PIB {source}: odpowiedź w {duration_ms} ms, rekordów: {records}",
    ),
    "server.upstream_ok": Text(
        "IMGW-PIB {source}: answered in {duration_ms} ms",
        "IMGW-PIB {source}: odpowiedź w {duration_ms} ms",
    ),
    "server.upstream_failed": Text(
        "IMGW-PIB {source}: failed after {duration_ms} ms, {code}: {reason}",
        "IMGW-PIB {source}: błąd po {duration_ms} ms, {code}: {reason}",
    ),
    # The live tail of a station's chart in „teraz” (O6), of either provider
    "server.tail_hours": Text(
        "{provider} live tail: answered in {duration_ms} ms, {hours} hours",
        "{provider} ostatnie godziny: odpowiedź w {duration_ms} ms, godzin: {hours}",
    ),
    "server.tail_failed": Text(
        "{provider} live tail: failed after {duration_ms} ms, {code}: {reason}",
        "{provider} ostatnie godziny: błąd po {duration_ms} ms, {code}: {reason}",
    ),
    "errors.bad_parameter": Text(
        "Invalid value of {option}: {value}", "Niepoprawna wartość {option}: {value}"
    ),
    "errors.title_rate_limited": Text("Too many requests", "Zbyt wiele żądań"),
    "errors.title_unauthorized": Text(
        "Authentication required", "Wymagane uwierzytelnienie"
    ),
    "errors.no_analysis": Text(
        "There is no analysis {analysis}.", "Nie ma analizy {analysis}."
    ),
    "errors.no_stored_analyses": Text(
        "The data root holds no analyses of the station {station}.",
        "Katalog danych nie ma zapisanych analiz stacji {station}.",
    ),
    "errors.analysis_not_stored": Text(
        "The data root holds no analysis {analysis} of the station {station}.",
        "Katalog danych nie ma zapisanej analizy {analysis} stacji {station}.",
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
    "errors.no_current_chmu": Text(
        "ČHMÚ's current data are not provided.",
        "Dane bieżące ČHMÚ nie są udostępniane.",
    ),
    "errors.no_current_kind": Text(
        "Current data are given only for hydrological and meteorological stations.",
        "Dane bieżące są podawane tylko dla stacji hydrologicznych i "
        "meteorologicznych.",
    ),
    "errors.no_chart_kind": Text(
        "The chart of current measurements is drawn only for hydrological stations.",
        "Wykres pomiarów bieżących jest rysowany tylko dla stacji hydrologicznych.",
    ),
    "errors.no_chart_provider": Text(
        "{provider} gives no hourly series: there is no chart of current measurements.",
        "{provider} nie podaje szeregu godzinowego: nie ma wykresu pomiarów bieżących.",
    ),
    "errors.chart_private": Text(
        "The chart of the station {station} is not served by this server: its sources "
        "are private ([obserwator.capture]).",
        "Wykres stacji {station} nie jest udostępniany przez ten serwer: jego źródła "
        "są prywatne ([obserwator.capture]).",
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
