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
    "handoff.subject_daily": Text(
        "{station} — {variable}, daily values",
        "{station} — {variable}, wartości dobowe",
    ),
    "handoff.subject_annual": Text(
        "{station} — {variable}, annual maxima",
        "{station} — {variable}, maksima roczne",
    ),
}
