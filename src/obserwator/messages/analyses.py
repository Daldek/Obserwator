"""Messages of the stored analyses (``store/analyses.py``, ``store/analysis_registry.py``, ``_hydrolog.py``)."""

from obserwator.messages import Text

MESSAGES = {
    # --- Hydrolog's program ---------------------------------------------------------------
    "hydrolog_not_installed": Text(
        "Hydrolog's program was not found: hydrolog is not on PATH",
        "Nie znaleziono programu Hydrolog: hydrolog nie jest na ścieżce PATH",
    ),
    "hydrolog_program_not_found": Text(
        "The program of the setting OBSERWATOR_HYDROLOG_COMMAND was not found",
        "Nie znaleziono programu z ustawienia OBSERWATOR_HYDROLOG_COMMAND",
    ),
    "hint_hydrolog_command": Text(
        "Install Hydrolog or set OBSERWATOR_HYDROLOG_COMMAND ([obserwator] hydrolog_command) to its command line",
        "Zainstaluj Hydrologa albo podaj jego wiersz poleceń w OBSERWATOR_HYDROLOG_COMMAND ([obserwator] hydrolog_command)",
    ),
    "hydrolog_command_invalid": Text(
        "OBSERWATOR_HYDROLOG_COMMAND is no command line: {reason}",
        "OBSERWATOR_HYDROLOG_COMMAND nie jest wierszem poleceń: {reason}",
    ),
    "hydrolog_failed": Text(
        "Hydrolog's program ended with the exit code {code}: {reason}",
        "Program Hydrolog zakończył się kodem {code}: {reason}",
    ),
    "hydrolog_unreadable": Text(
        "Hydrolog's program gave an answer that is not its document: {reason}",
        "Program Hydrolog dał odpowiedź, która nie jest jego dokumentem: {reason}",
    ),
    "hydrolog_line_count": Text(
        "Hydrolog's program wrote {lines} lines for {calls} calls",
        "Program Hydrolog zapisał {lines} wierszy dla {calls} wywołań",
    ),
    "hydrolog_version_changed": Text(
        "Hydrolog's version changed during the computation: {before} → {after}",
        "Wersja Hydrologa zmieniła się w trakcie obliczeń: {before} → {after}",
    ),
    "hydrolog_timeout": Text(
        "Hydrolog did not finish within {seconds} s",
        "Hydrolog nie skończył obliczeń w ciągu {seconds} s",
    ),
    # --- the registry ---------------------------------------------------------------------
    "unknown_analysis": Text(
        "Unknown analysis {analysis}",
        "Nieznana analiza {analysis}",
    ),
    "hint_analysis_definitions": Text(
        "The ids of the analyses: analysis_definitions() or obserwator analyses list",
        "Identyfikatory analiz: analysis_definitions() albo obserwator analyses list",
    ),
    "unknown_kind": Text(
        "Unknown kind of station {kind}; allowed: hydro, meteo",
        "Nieznany rodzaj stacji {kind}; dozwolone: hydro, meteo",
    ),
    "option_value_invalid": Text(
        "Invalid value {value} of the option {option}: {reason}",
        "Niepoprawna wartość {value} opcji {option}: {reason}",
    ),
    "option_not_overridable": Text(
        "The option {option} of the analysis {analysis} cannot be changed; allowed: {allowed}",
        "Opcji {option} analizy {analysis} nie można zmienić; dozwolone: {allowed}",
    ),
    "options_not_mapping": Text(
        "The options must be a mapping of option names to values",
        "Opcje muszą być słownikiem nazw opcji i wartości",
    ),
    "reason_integer": Text("an integer is expected", "oczekiwano liczby całkowitej"),
    "reason_number": Text("a number is expected", "oczekiwano liczby"),
    "reason_boolean": Text("true or false is expected", "oczekiwano true albo false"),
    "reason_enum": Text("allowed: {allowed}", "dozwolone: {allowed}"),
    "reason_array": Text("a list of numbers is expected", "oczekiwano listy liczb"),
    "reason_items": Text(
        "from {minimum} to {maximum} items are expected",
        "oczekiwano od {minimum} do {maximum} elementów",
    ),
    "reason_minimum": Text("at least {limit}", "co najmniej {limit}"),
    "reason_maximum": Text("at most {limit}", "co najwyżej {limit}"),
    "reason_exclusive_minimum": Text("more than {limit}", "więcej niż {limit}"),
    "reason_exclusive_maximum": Text("less than {limit}", "mniej niż {limit}"),
    # --- options of the functions ----------------------------------------------------------
    "invalid_station": Text(
        "Invalid station code {station}; expected {pattern}",
        "Niepoprawny kod stacji {station}; oczekiwano {pattern}",
    ),
    "invalid_stations": Text(
        "Invalid station codes: {stations}",
        "Niepoprawne kody stacji: {stations}",
    ),
    "stations_not_list": Text(
        "stations must be a list of station codes",
        "stations musi być listą kodów stacji",
    ),
    "stations_outside": Text(
        "No series of the analyses holds the stations {stations}",
        "Żaden szereg analiz nie obejmuje stacji {stations}",
    ),
    "invalid_workers": Text(
        "workers must be a positive integer, not {workers}",
        "workers musi być dodatnią liczbą całkowitą, a nie {workers}",
    ),
    "invalid_timeout": Text(
        "timeout must be a positive number of seconds, not {timeout}",
        "timeout musi być dodatnią liczbą sekund, a nie {timeout}",
    ),
    "analyses_not_list": Text(
        "analyses must be a list of analysis ids",
        "analyses musi być listą identyfikatorów analiz",
    ),
    # --- building ------------------------------------------------------------------------
    "no_series": Text(
        "The data root holds no series to analyse",
        "Katalog danych nie zawiera szeregów do analizy",
    ),
    "station_computed": Text(
        "Analyses of the station {station} computed",
        "Obliczono analizy stacji {station}",
    ),
    "station_carried": Text(
        "Analyses of the station {station} carried forward",
        "Przeniesiono analizy stacji {station}",
    ),
    "version_unchanged": Text(
        "The analyses of {provider} are unchanged",
        "Analizy {provider} bez zmian",
    ),
    "version_collision": Text(
        "An analyses version directory collision: {path}",
        "Kolizja katalogu wersji analiz: {path}",
    ),
    "plan_current": Text(
        "The analyses of {provider} are current ({stations} stations)",
        "Analizy {provider} są aktualne ({stations} stacji)",
    ),
    "plan_build": Text(
        "A new analyses version of {provider}: {computed} stations computed by Hydrolog {version}, {carried} carried forward",
        "Nowa wersja analiz {provider}: {computed} stacji do obliczenia Hydrologiem {version}, {carried} do przeniesienia",
    ),
    # --- reading -----------------------------------------------------------------------
    "no_version": Text(
        "The data root holds no analyses of {provider}",
        "Katalog danych nie zawiera analiz {provider}",
    ),
    "hint_build": Text(
        "Compute them: obserwator analyses build",
        "Oblicz je: obserwator analyses build",
    ),
    "version_not_found": Text(
        "No analyses version at {version}",
        "Brak wersji analiz w {version}",
    ),
    "station_not_in_version": Text(
        "The analyses version {version} holds no station {station}",
        "Wersja analiz {version} nie obejmuje stacji {station}",
    ),
    "analysis_not_stored": Text(
        "The station {station} has no stored analysis {analysis}",
        "Stacja {station} nie ma zapisanej analizy {analysis}",
    ),
    "broken_version": Text(
        "A broken analyses version {path}: {reason}",
        "Uszkodzona wersja analiz {path}: {reason}",
    ),
    "missing_file": Text("a missing file", "brak pliku"),
    "checksum_mismatch": Text(
        "{name} does not match its SHA-256",
        "{name} nie zgadza się ze swoją sumą SHA-256",
    ),
    "unknown_schema": Text("an unknown document schema", "nieznany schemat dokumentu"),
    "not_analyses_version": Text(
        "the sidecar names no analyses version of the provider",
        "plik metadanych nie opisuje wersji analiz tego dostawcy",
    ),
    "export_progress": Text(
        "Analyses of the station {station}",
        "Analizy stacji {station}",
    ),
    "exported": Text(
        "Exported the analyses of the station {station}",
        "Wyeksportowano analizy stacji {station}",
    ),
    # --- on the fly ------------------------------------------------------------------------
    "not_applicable": Text(
        "The series of the station {station} do not allow the analysis {analysis}",
        "Szeregi stacji {station} nie pozwalają na analizę {analysis}",
    ),
    "dependency_without_result": Text(
        "The analysis {analysis} takes a number of another analysis, which gave none: {reason}",
        "Analiza {analysis} bierze liczbę z innej analizy, która jej nie dała: {reason}",
    ),
    "no_value": Text("no value", "brak wartości"),
    # --- titles of the analyses ---------------------------------------------------------
    "title_characteristic_h": Text(
        "Characteristic water levels (first and second degree)",
        "Stany charakterystyczne (I i II stopnia)",
    ),
    "title_characteristic_q": Text(
        "Characteristic discharges (first and second degree)",
        "Przepływy charakterystyczne (I i II stopnia)",
    ),
    "title_characteristic_t": Text(
        "Characteristic water temperatures (first and second degree)",
        "Charakterystyczne temperatury wody (I i II stopnia)",
    ),
    "title_half_years_h": Text(
        "Characteristic water levels from IMGW-PIB's half-years",
        "Stany charakterystyczne z półroczy IMGW-PIB",
    ),
    "title_half_years_q": Text(
        "Characteristic discharges from IMGW-PIB's half-years",
        "Przepływy charakterystyczne z półroczy IMGW-PIB",
    ),
    "title_half_years_t": Text(
        "Characteristic water temperatures from IMGW-PIB's half-years",
        "Charakterystyczne temperatury wody z półroczy IMGW-PIB",
    ),
    "title_events_h_swx": Text(
        "Days and events at or above SWW", "Dni i epizody od SWW wzwyż"
    ),
    "title_events_h_ssx": Text(
        "Days and events at or above SSW", "Dni i epizody od SSW wzwyż"
    ),
    "title_events_h_snx": Text(
        "Days and events below SNW", "Dni i epizody poniżej SNW"
    ),
    "title_events_q_swx": Text(
        "Days and events at or above SWQ", "Dni i epizody od SWQ wzwyż"
    ),
    "title_events_q_ssx": Text(
        "Days and events at or above SSQ", "Dni i epizody od SSQ wzwyż"
    ),
    "title_events_q_snx": Text(
        "Days and events below SNQ", "Dni i epizody poniżej SNQ"
    ),
    "title_events_h_spa1": Text(
        "Days and events of H at or above ČHMÚ's SPA 1",
        "Dni i epizody H od SPA 1 ČHMÚ wzwyż",
    ),
    "title_events_h_spa2": Text(
        "Days and events of H at or above ČHMÚ's SPA 2",
        "Dni i epizody H od SPA 2 ČHMÚ wzwyż",
    ),
    "title_events_h_spa3": Text(
        "Days and events of H at or above ČHMÚ's SPA 3",
        "Dni i epizody H od SPA 3 ČHMÚ wzwyż",
    ),
    "title_events_h_q50": Text(
        "Days and events of H at or above ČHMÚ's level of Q50",
        "Dni i epizody H od poziomu Q50 ČHMÚ wzwyż",
    ),
    "title_events_h_drought": Text(
        "Days and events of H below ČHMÚ's drought level",
        "Dni i epizody H poniżej progu suszy ČHMÚ",
    ),
    "title_events_q_spa1": Text(
        "Days and events of Q at or above ČHMÚ's SPA 1",
        "Dni i epizody Q od SPA 1 ČHMÚ wzwyż",
    ),
    "title_events_q_spa2": Text(
        "Days and events of Q at or above ČHMÚ's SPA 2",
        "Dni i epizody Q od SPA 2 ČHMÚ wzwyż",
    ),
    "title_events_q_spa3": Text(
        "Days and events of Q at or above ČHMÚ's SPA 3",
        "Dni i epizody Q od SPA 3 ČHMÚ wzwyż",
    ),
    "title_events_q_q50": Text(
        "Days and events of Q at or above ČHMÚ's Q50",
        "Dni i epizody Q od Q50 ČHMÚ wzwyż",
    ),
    "title_events_q_drought": Text(
        "Days and events of Q below ČHMÚ's drought level",
        "Dni i epizody Q poniżej progu suszy ČHMÚ",
    ),
    "title_rating_curve": Text(
        "Rating curve of the last ten years",
        "Krzywa natężenia przepływu ostatnich dziesięciu lat",
    ),
    "title_rating_periods": Text(
        "Rating curves of ten-year periods",
        "Krzywe natężenia przepływu okresów dziesięcioletnich",
    ),
    "title_flood_frequency": Text(
        "Maximum discharges of a given probability",
        "Przepływy maksymalne o danym prawdopodobieństwie",
    ),
    "title_low_flow": Text(
        "Minimum discharges of a given probability",
        "Przepływy minimalne o danym prawdopodobieństwie",
    ),
    "title_homogeneity": Text(
        "Homogeneity of the annual maxima", "Jednorodność maksimów rocznych"
    ),
    "title_low_flow_sequences": Text(
        "Low-flow periods below SNQ", "Niżówki poniżej SNQ"
    ),
    "title_low_flow_sequences_h": Text(
        "Low-water periods below SNW", "Niżówki stanów poniżej SNW"
    ),
    "title_duration_h": Text(
        "Duration curve and classes of water levels",
        "Krzywa czasu trwania i klasy stanów wody",
    ),
    "title_duration_q": Text(
        "Duration curve and classes of discharges",
        "Krzywa czasu trwania i klasy przepływów",
    ),
    "title_water_level_zones": Text(
        "Water level zones after Rybczyński", "Strefy stanów wody wg Rybczyńskiego"
    ),
    "title_daily_h": Text(
        "Water levels of each day of the year",
        "Stany wody w poszczególnych dniach roku",
    ),
    "title_daily_q": Text(
        "Discharges of each day of the year", "Przepływy w poszczególnych dniach roku"
    ),
    "title_daily_t": Text(
        "Water temperatures of each day of the year",
        "Temperatury wody w poszczególnych dniach roku",
    ),
    "title_monthly_h": Text(
        "Monthly statistics of water levels", "Statystyki miesięczne stanów wody"
    ),
    "title_monthly_q": Text(
        "Monthly statistics of discharges", "Statystyki miesięczne przepływów"
    ),
    "title_monthly_t": Text(
        "Monthly statistics of water temperature",
        "Statystyki miesięczne temperatury wody",
    ),
    "title_regime": Text(
        "River regime: Pardé coefficients and the regime type",
        "Reżim rzeki: współczynniki Pardégo i typ reżimu",
    ),
    "title_seasonality_max": Text(
        "Seasonality of the annual maxima", "Sezonowość maksimów rocznych"
    ),
    "title_seasonality_min": Text(
        "Seasonality of the annual minima", "Sezonowość minimów rocznych"
    ),
    "title_seasonality_h_max": Text(
        "Seasonality of the annual maximum water levels",
        "Sezonowość maksymalnych rocznych stanów wody",
    ),
    "title_seasonality_h_min": Text(
        "Seasonality of the annual minimum water levels",
        "Sezonowość minimalnych rocznych stanów wody",
    ),
    "title_harmonics_t": Text(
        "Annual cycle of water temperature (harmonics)",
        "Cykl roczny temperatury wody (harmoniki)",
    ),
    "title_events_t_ge15": Text(
        "Days with water temperature of 15 °C or more",
        "Dni z temperaturą wody od 15 °C",
    ),
    "title_events_t_ge20": Text(
        "Days with water temperature of 20 °C or more",
        "Dni z temperaturą wody od 20 °C",
    ),
    "title_events_t_ge25": Text(
        "Days with water temperature of 25 °C or more",
        "Dni z temperaturą wody od 25 °C",
    ),
    "title_events_t_lt1": Text(
        "Days with water temperature below 1 °C", "Dni z temperaturą wody poniżej 1 °C"
    ),
    "title_runoff_volume": Text("Runoff volumes", "Objętości odpływu"),
    "title_baseflow": Text(
        "Baseflow and the baseflow index", "Przepływ podziemny i wskaźnik BFI"
    ),
    "title_trend_q_max": Text("Trend of WQ", "Trend WQ"),
    "title_trend_q_mean": Text("Trend of SQ", "Trend SQ"),
    "title_trend_q_min": Text("Trend of NQ", "Trend NQ"),
    "title_trend_h_max": Text("Trend of WW", "Trend WW"),
    "title_trend_h_mean": Text("Trend of SW", "Trend SW"),
    "title_trend_h_min": Text("Trend of NW", "Trend NW"),
    "title_trend_t_max": Text(
        "Trend of the annual maximum water temperature",
        "Trend rocznej maksymalnej temperatury wody",
    ),
    "title_trend_t_mean": Text(
        "Trend of the annual mean water temperature",
        "Trend rocznej średniej temperatury wody",
    ),
    "title_trend_t_min": Text(
        "Trend of the annual minimum water temperature",
        "Trend rocznej minimalnej temperatury wody",
    ),
    "title_precipitation_sums": Text(
        "Precipitation sums, normal and anomaly", "Sumy opadów, normalna i anomalia"
    ),
    "title_precipitation_maxima": Text(
        "Maximum precipitation of 1 to 10 days", "Maksymalne opady 1–10 dni"
    ),
    "title_precipitation_days": Text("Days with precipitation", "Dni z opadem"),
    "title_precipitation_intensity": Text(
        "Mean precipitation and wet-day intensity",
        "Średni opad i natężenie dnia z opadem",
    ),
    "title_precipitation_heavy": Text(
        "Share of heavy precipitation", "Udział opadów dużych"
    ),
    "title_precipitation_seasonality": Text(
        "Seasonality of precipitation", "Sezonowość opadów"
    ),
    "title_precipitation_quantiles": Text(
        "Maximum daily precipitation of a given probability",
        "Maksymalny opad dobowy o danym prawdopodobieństwie",
    ),
    "title_precipitation_quantiles_2d": Text(
        "Maximum 2-day precipitation of a given probability",
        "Maksymalny opad 2-dniowy o danym prawdopodobieństwie",
    ),
    "title_precipitation_quantiles_3d": Text(
        "Maximum 3-day precipitation of a given probability",
        "Maksymalny opad 3-dniowy o danym prawdopodobieństwie",
    ),
    "title_precipitation_quantiles_5d": Text(
        "Maximum 5-day precipitation of a given probability",
        "Maksymalny opad 5-dniowy o danym prawdopodobieństwie",
    ),
    "title_precipitation_quantiles_10d": Text(
        "Maximum 10-day precipitation of a given probability",
        "Maksymalny opad 10-dniowy o danym prawdopodobieństwie",
    ),
    "title_spells_dry": Text("Dry spells", "Okresy bezopadowe"),
    "title_spells_wet": Text("Wet spells", "Okresy z opadem"),
    "title_spi": Text(
        "Standardized precipitation index (SPI) and relative precipitation",
        "Wskaźnik standaryzowanego opadu (SPI) i opad względny",
    ),
    "title_temperature_means": Text(
        "Air temperature: means, extremes, normal and anomaly",
        "Temperatura powietrza: średnie, ekstrema, normalna i anomalia",
    ),
    "title_temperature_days": Text(
        "Characteristic days of air temperature",
        "Dni charakterystyczne temperatury powietrza",
    ),
    "title_temperature_degree_days": Text(
        "Growing and heating degree days", "Stopniodni wegetacji i ogrzewania"
    ),
    "title_temperature_range": Text(
        "Daily range of air temperature", "Dobowa amplituda temperatury powietrza"
    ),
    "title_harmonics_tmean": Text(
        "Annual cycle of air temperature (harmonics)",
        "Cykl roczny temperatury powietrza (harmoniki)",
    ),
    "title_hydrothermal": Text(
        "Sielianinov's hydrothermal coefficient",
        "Współczynnik hydrotermiczny Sielianinowa",
    ),
    "title_snow": Text("Snow cover", "Pokrywa śnieżna"),
    "title_trend_precipitation_sums": Text(
        "Trend of the annual precipitation sums", "Trend rocznych sum opadów"
    ),
    "title_trend_precipitation_maxima": Text(
        "Trend of the annual maximum daily precipitation",
        "Trend rocznych maksimów opadu dobowego",
    ),
    "title_trend_precipitation_days": Text(
        "Trend of the days with precipitation of 10 mm or more",
        "Trend liczby dni z opadem od 10 mm",
    ),
    "title_trend_spells_dry": Text(
        "Trend of the longest dry spell", "Trend najdłuższego okresu bezopadowego"
    ),
    "title_trend_temperature_means": Text(
        "Trend of the annual mean air temperature",
        "Trend rocznej średniej temperatury powietrza",
    ),
    "title_trend_frost_days": Text(
        "Trend of the frost days", "Trend liczby dni przymrozkowych"
    ),
    "title_trend_summer_days": Text(
        "Trend of the summer days", "Trend liczby dni gorących"
    ),
}
