"""The station panel: its header, „Informacje o stacji”, „Pomiary bieżące”, „Dane pomiarowo-obserwacyjne”, „Pobierz” and the hand-off to Hydrolog."""

from obserwator.messages import Text

MESSAGES: dict[str, Text] = {
    # --- the panel and its header ---------------------------------------------------------
    "station.stacja.title": Text("Station information", "Informacje o stacji"),
    "station.teraz.title": Text("Current measurements", "Pomiary bieżące"),
    "station.dane.title": Text(
        "Measurement and observation data", "Dane pomiarowo-obserwacyjne"
    ),
    "station.pobierz.title": Text("Download", "Pobierz"),
    "station.loading": Text("Loading the station…", "Wczytuję stację…"),
    "station.section_failed": Text(
        "This section does not work: {message}", "Sekcja nie działa: {message}"
    ),
    "station.active": Text("active", "czynna"),
    "station.inactive": Text("inactive", "nieczynna"),
    "station.no_location": Text("no coordinates", "bez współrzędnych"),
    "station.no_series": Text(
        "The data root holds no series of this station: the panel shows its catalog "
        "data.",
        "Katalog danych nie ma szeregów tej stacji: panel pokazuje jej dane z katalogu "
        "stacji.",
    ),
    "station.analyses_loading": Text(
        "Listing the analyses of the station…", "Wczytuję listę analiz stacji…"
    ),
    "station.analyses_failed": Text(
        "The analyses of the station cannot be listed: {message}",
        "Nie można wczytać listy analiz stacji: {message}",
    ),
    "station.version": Text("version {version}", "wersja {version}"),
    "station.variable": Text("Variable", "Zmienna"),
    # --- the panel without a station ------------------------------------------------------
    "station.none.hint": Text(
        "Choose a station on the map or in the list on the left: its information, "
        "current measurements, measurement and observation data, analyses and files to "
        "download will show here.",
        "Wybierz stację na mapie albo z listy po lewej: tu pokażą się informacje o niej, "
        "jej pomiary bieżące, dane pomiarowo-obserwacyjne, analizy i pliki do pobrania.",
    ),
    "station.none.root_error": Text(
        "The data root cannot be read: {message}",
        "Nie można odczytać katalogu danych: {message}",
    ),
    "station.none.catalogs": Text("Station catalogs", "Katalogi stacji"),
    "station.none.provider_kinds": Text(
        "{provider}: hydrological · meteorological",
        "{provider}: hydrologiczne · meteorologiczne",
    ),
    "station.none.catalog_version": Text(
        "catalog {version}, downloaded {when}", "katalog {version}, pobrany {when}"
    ),
    "station.none.with_series": Text(
        "with series in the data root", "z szeregami w katalogu danych"
    ),
    "station.none.without_location": Text(
        "without coordinates (in the list only)", "bez współrzędnych (tylko na liście)"
    ),
    "station.none.series": Text("Series in the data root", "Szeregi w katalogu danych"),
    "station.none.stations.one": Text("{n} station", "{n} stacja"),
    "station.none.stations.few": Text("{n} stations", "{n} stacje"),
    "station.none.stations.many": Text("{n} stations", "{n} stacji"),
    "station.none.stations.other": Text("{n} stations", "{n} stacji"),
    "station.none.no_series": Text(
        "The data root holds no series yet.", "Katalog danych nie ma jeszcze szeregów."
    ),
    "station.none.missing": Text(
        "The data root holds none of: {datasets}.",
        "Katalog danych nie ma zbiorów: {datasets}.",
    ),
    "station.none.no_hydrolog": Text(
        "no Hydrolog: no analyses computed on request",
        "bez Hydrologa: bez analiz liczonych na żądanie",
    ),
    # --- „Informacje o stacji” ------------------------------------------------------------
    "station.info.catalog": Text("Catalog data", "Dane katalogowe"),
    "station.info.code": Text("Station code", "Kod stacji"),
    "station.info.name": Text("Name", "Nazwa"),
    "station.info.river": Text("River", "Rzeka"),
    "station.info.provider": Text("Provider", "Dostawca"),
    "station.info.kind": Text("Kind", "Rodzaj"),
    "station.info.meteo_station": Text("Type of station", "Typ stacji"),
    "station.info.meteo_kind.climate": Text(
        "climatological station", "stacja klimatologiczna"
    ),
    "station.info.meteo_kind.precipitation": Text(
        "precipitation post", "posterunek opadowy"
    ),
    "station.info.active": Text("Active", "Czynna"),
    "station.info.yes": Text("yes", "tak"),
    "station.info.no": Text("no", "nie"),
    "station.info.location": Text("Location (WGS84)", "Położenie (WGS84)"),
    "station.info.no_location": Text("none", "brak"),
    "station.info.uncertainty": Text(
        "{source}, uncertainty ±{metres} m", "{source}, niepewność ±{metres} m"
    ),
    "station.info.source_unknown": Text("source unknown", "źródło nieznane"),
    "station.info.source.api_hydro": Text(
        "IMGW-PIB's current API (danepubliczne.imgw.pl), hydrological stations",
        "bieżące API IMGW-PIB (danepubliczne.imgw.pl), stacje hydrologiczne",
    ),
    "station.info.source.api_meteo": Text(
        "IMGW-PIB's current API (danepubliczne.imgw.pl), meteorological stations",
        "bieżące API IMGW-PIB (danepubliczne.imgw.pl), stacje meteorologiczne",
    ),
    "station.info.source.static": Text(
        "the map of IMGW-PIB's hydrological service (hydro.imgw.pl), the file of "
        "locations in Obserwator's package",
        "mapa serwisu hydrologicznego IMGW-PIB (hydro.imgw.pl), plik położeń w pakiecie "
        "Obserwatora",
    ),
    "station.info.source.user": Text(
        "a file of locations given when the catalog was built",
        "plik położeń podany przy budowie katalogu",
    ),
    "station.info.source.chmi_hydro_now": Text(
        "ČHMÚ's current metadata, hydrology", "bieżące metadane ČHMÚ, hydrologia"
    ),
    "station.info.source.chmi_hydro_meta3": Text(
        "ČHMÚ's metadata (meta3), hydrology", "metadane ČHMÚ (meta3), hydrologia"
    ),
    "station.info.source.chmi_hydro_stations": Text(
        "ČHMÚ's list of stations, hydrology", "wykaz stacji ČHMÚ, hydrologia"
    ),
    "station.info.source.chmi_meteo_now": Text(
        "ČHMÚ's current metadata, meteorology", "bieżące metadane ČHMÚ, meteorologia"
    ),
    "station.info.missing.outside_country": Text(
        "the station lies outside its provider's country", "stacja poza krajem dostawcy"
    ),
    "station.info.missing.none": Text(
        "the sources give no location (a closed station or one outside the current API)",
        "źródła nie podają położenia (stacja zamknięta albo spoza bieżącego API)",
    ),
    "station.info.missing.zero": Text(
        "the source gives zero coordinates", "źródło podaje współrzędne zerowe"
    ),
    "station.info.elevation": Text("Elevation", "Wysokość"),
    "station.info.metres_asl": Text("{value} m a.s.l.", "{value} m n.p.m."),
    "station.info.gauge_zero": Text("Gauge zero", "Zero wodowskazu"),
    "station.info.river_km": Text("River kilometre", "Kilometr rzeki"),
    "station.info.hydrographic_code": Text("Hydrographic code", "Kod hydrograficzny"),
    "station.info.river_order": Text(
        "Number in IMGW-PIB's list", "Liczba z wykazu IMGW-PIB"
    ),
    "station.info.river_order_note": Text(
        "the fourth column of the list of stations, with no meaning given (river_order)",
        "czwarta kolumna wykazu stacji, bez przypisanego znaczenia (river_order)",
    ),
    "station.info.established": Text("Year established", "Rok założenia"),
    "station.info.thresholds": Text("ČHMÚ's thresholds", "Progi ČHMÚ"),
    "station.info.thresholds_info": Text(
        "ČHMÚ's threshold levels and discharges of the station: the flood activity "
        "degrees SPA 1–3 (stupně povodňové aktivity), the drought threshold and q50, "
        "from Obserwator's catalog of stations (source: {source}).",
        "Stany i przepływy progowe ČHMÚ dla stacji: stopnie aktywności powodziowej "
        "SPA 1–3 (stupně povodňové aktivity), próg suszy i q50, z katalogu stacji "
        "Obserwatora (źródło: {source}).",
    ),
    "station.info.threshold": Text("Threshold", "Próg"),
    "station.info.threshold.spa1": Text(
        "1st SPA (bdělost, alertness)", "1. SPA (bdělost, czujność)"
    ),
    "station.info.threshold.spa2": Text(
        "2nd SPA (pohotovost, readiness)", "2. SPA (pohotovost, gotowość)"
    ),
    "station.info.threshold.spa3": Text(
        "3rd SPA (ohrožení, danger)", "3. SPA (ohrožení, zagrożenie)"
    ),
    "station.info.threshold.drought": Text("drought (sucho)", "susza (sucho)"),
    "station.info.coverage": Text(
        "Series in the data root", "Szeregi w katalogu danych"
    ),
    "station.info.coverage_info": Text(
        "The coverage of each variable in the current version of each series: the "
        "first and the last period with a value, the number of periods with a value "
        "(days, months or half-years), of values summed over several days and of gaps, "
        "from the index of the series in Obserwator's data root (series.json).",
        "Pokrycie każdej zmiennej w bieżącej wersji każdego szeregu: pierwszy i ostatni "
        "okres z wartością, liczba okresów z wartością (dni, miesięcy albo półroczy), "
        "wartości sumowanych z kilku dni i luk, według indeksu szeregu w katalogu danych "
        "Obserwatora (series.json).",
    ),
    "station.info.downloaded": Text("downloaded {when}", "pobrany {when}"),
    "station.info.span": Text("From – to", "Od – do"),
    "station.info.with_value": Text("With a value", "Z wartością"),
    "station.info.accumulated": Text("Sums of several days", "Sumy z kilku dni"),
    "station.info.gaps": Text("Gaps", "Luki"),
    "station.info.no_series": Text(
        "The data root holds no series of this station.",
        "Katalog danych nie ma szeregów tej stacji.",
    ),
    # --- „Pomiary bieżące” ----------------------------------------------------------------
    "station.now.info_hydro": Text(
        "IMGW-PIB's operational values (not verified) from its public API (obserwator "
        "current hydro): the water level, the discharge and the water temperature, each "
        "with the time of its measurement (UTC). The symbol and its words are the water "
        "state against the characteristic levels, as the map hydro.imgw.pl shows it "
        "(obserwator current hydro-states), in its colours: filled for a state from the "
        "measurements of the last 2 hours, hollow for one from the last 26 hours. The "
        "GUI's server asks IMGW-PIB at most once in 10 minutes, shows the snapshot with "
        "its time and stores nothing.",
        "Wartości operacyjne IMGW-PIB (niezweryfikowane) z jego publicznego API "
        "(obserwator current hydro): stan wody, przepływ i temperatura wody, każda z "
        "czasem pomiaru (UTC). Symbol i opis to stan wody względem stanów "
        "charakterystycznych, jak pokazuje go mapa hydro.imgw.pl (obserwator current "
        "hydro-states), w jej kolorach: pełny to stan z pomiarów ostatnich 2 godzin, z "
        "pustym środkiem — z ostatnich 26 godzin. Serwer GUI pyta IMGW-PIB najwyżej raz "
        "na 10 minut, pokazuje migawkę z jej czasem i niczego nie zapisuje.",
    ),
    "station.now.info_meteo": Text(
        "Operational values of IMGW-PIB's automatic meteorological stations (not "
        "verified) from its public API (obserwator current meteo): the precipitation of "
        "the last 10 minutes, the air temperature with the time of its measurement "
        "(UTC), the mean wind speed and the relative humidity. The class of "
        "precipitation has the colours of the map hydro.imgw.pl, but it is taken from "
        "the 10-minute total (hydro.imgw.pl takes 6 hours); heavy precipitation is at "
        "least heavy rain on Chomicz's scale, ≥ √10 ≈ 3.2 mm in 10 minutes. A synoptic "
        "station also has its last SYNOP report (obserwator current synop). The GUI's "
        "server asks IMGW-PIB at most once in 10 minutes and stores nothing.",
        "Wartości operacyjne automatycznych stacji meteorologicznych IMGW-PIB "
        "(niezweryfikowane) z jego publicznego API (obserwator current meteo): opad "
        "ostatnich 10 minut, temperatura powietrza z czasem pomiaru (UTC), średnia "
        "prędkość wiatru i wilgotność względna. Klasa opadu ma kolory mapy hydro.imgw.pl, "
        "ale liczona jest z sumy 10-minutowej (hydro.imgw.pl liczy z 6 godzin); opad "
        "intensywny to co najmniej silny deszcz w skali Chomicza, ≥ √10 ≈ 3,2 mm w 10 "
        "minut. Stacja synoptyczna ma też ostatnią depeszę SYNOP (obserwator current "
        "synop). Serwer GUI pyta IMGW-PIB najwyżej raz na 10 minut i niczego nie "
        "zapisuje.",
    ),
    "station.now.chmi_note": Text(
        "Obserwator serves no current data of ČHMÚ (now, recent), only the daily series "
        "of the data root.",
        "Obserwator nie obsługuje bieżących danych ČHMÚ (now, recent), tylko szeregi "
        "dobowe z katalogu danych.",
    ),
    "station.now.loading": Text(
        "Fetching the current measurements…", "Pobieram pomiary bieżące…"
    ),
    "station.now.state_note": Text(
        "state from the measurements of the last {hours} hours, map hydro.imgw.pl",
        "stan z pomiarów ostatnich {hours} godzin, mapa hydro.imgw.pl",
    ),
    "station.now.water_level": Text("Water level H", "Stan wody H"),
    "station.now.discharge": Text("Discharge Q", "Przepływ Q"),
    "station.now.water_temperature": Text("Water temperature", "Temperatura wody"),
    "station.now.precipitation_10min": Text("Precipitation (10 min)", "Opad (10 min)"),
    "station.now.air_temperature": Text("Air temperature", "Temperatura powietrza"),
    "station.now.wind_mean": Text("Wind (mean)", "Wiatr (średni)"),
    "station.now.humidity": Text("Relative humidity", "Wilgotność względna"),
    "station.now.only_precipitation": Text(
        "IMGW-PIB's API now gives only the precipitation of this station.",
        "API IMGW-PIB podaje teraz dla tej stacji tylko opad.",
    ),
    "station.now.no_values": Text(
        "IMGW-PIB's API lists this station but gives none of its values now.",
        "API IMGW-PIB wymienia tę stację, ale nie podaje teraz żadnej jej wartości.",
    ),
    "station.now.synop_title": Text(
        "SYNOP report: {name} ({code})", "Depesza SYNOP: {name} ({code})"
    ),
    "station.now.wind": Text("Wind", "Wiatr"),
    "station.now.wind_from": Text(
        "from {degrees}° ({compass})", "z kierunku {degrees}° ({compass})"
    ),
    "station.now.precipitation_total": Text("Precipitation total", "Suma opadu"),
    "station.now.pressure": Text("Pressure", "Ciśnienie"),
    "station.now.visibility": Text("Visibility", "Widzialność"),
    "station.now.cloud_cover": Text("Cloud cover", "Zachmurzenie"),
    "station.now.synop_term": Text(
        "Observation term: {date}, {hour}:00 UTC.",
        "Termin obserwacji: {date}, {hour}:00 UTC.",
    ),
    "station.now.synop_date": Text(
        "Observation term: {date}.", "Termin obserwacji: {date}."
    ),
    "station.now.no_record_hydro": Text(
        "IMGW-PIB gives no current measurements of this station: it is not in the "
        "API's current hydrological data.",
        "IMGW-PIB nie podaje teraz pomiarów tej stacji: nie ma jej w bieżących danych "
        "hydrologicznych API.",
    ),
    "station.now.no_record_meteo": Text(
        "IMGW-PIB gives no current measurements of this station: it is not in the "
        "API's data of automatic meteorological stations.",
        "IMGW-PIB nie podaje teraz pomiarów tej stacji: nie ma jej w danych "
        "automatycznych stacji meteorologicznych API.",
    ),
    "station.now.inactive": Text("The station is inactive.", "Stacja jest nieczynna."),
    "station.now.snapshots": Text(
        "The server's snapshots: {list}; refreshed at most every 10 minutes, never "
        "stored. Times of measurement in UTC.",
        "Migawki serwera: {list}; odświeżane najwyżej co 10 minut, niezapisywane. Czasy "
        "pomiarów w UTC.",
    ),
    "station.now.source.states": Text(
        "water states (map hydro.imgw.pl)", "stany wody (mapa hydro.imgw.pl)"
    ),
    "station.now.source.hydro": Text(
        "hydrological measurements", "pomiary hydrologiczne"
    ),
    "station.now.source.meteo": Text(
        "meteorological measurements", "pomiary meteorologiczne"
    ),
    "station.now.source.synop": Text("SYNOP reports", "depesze SYNOP"),
    "station.now.snapshot_error": Text(
        "{message} (showing the last successful snapshot)",
        "{message} (pokazuję ostatnią udaną migawkę)",
    ),
    "station.now.refresh": Text("Refresh", "Odśwież"),
    "station.now.operational": Text(
        "IMGW-PIB's operational data: current, not archival",
        "Dane operacyjne IMGW-PIB: bieżące, nie archiwalne",
    ),
    # --- „Dane pomiarowo-obserwacyjne” -----------------------------------------------------
    "station.data.none": Text(
        "No series in the data root: nothing to draw. The catalog data are in “Station "
        "information”.",
        "Brak szeregów w katalogu danych: nie ma czego narysować. Dane katalogowe są w "
        "sekcji „Informacje o stacji”.",
    ),
    "station.data.dataset": Text("Dataset", "Zbiór danych"),
    "station.data.loading": Text("Loading the series…", "Wczytuję szereg…"),
    "station.data.empty": Text(
        "This station's series is empty.", "Szereg tej stacji jest pusty."
    ),
    "station.data.variables": Text("Variables", "Zmienne"),
    "station.data.year_type": Text("Kind of year", "Rodzaj roku"),
    "station.data.hydrological_year": Text("hydrological year", "rok hydrologiczny"),
    "station.data.calendar_year": Text("calendar", "kalendarzowy"),
    "station.data.whole_period": Text("Whole period", "Cały okres"),
    "station.data.choose_variable": Text("Choose a variable.", "Wybierz zmienną."),
    "station.data.flag_def.missing": Text(
        "no value on the day: the line of the chart breaks",
        "dzień bez wartości: linia wykresu się przerywa",
    ),
    "station.data.flag_def.accumulated": Text(
        "precipitation collected over several days, given on the last of them: ticks "
        "under the chart",
        "opad zebrany z kilku dni, podany w ostatnim z nich: kreski pod wykresem",
    ),
    "station.data.flag_def.no_phenomenon": Text(
        "the phenomenon did not occur: 0 in the series, marked in the table",
        "zjawisko nie wystąpiło: 0 w szeregu, oznaczone w tabeli",
    ),
    "station.data.table": Text("Table", "Tabela"),
    "station.data.date": Text("Date", "Data"),
    "station.data.year": Text("Year", "Rok"),
    "station.data.hydro_year": Text("Hydr. year", "Rok hydr."),
    "station.data.year_short": Text("year", "rok"),
    "station.data.newest": Text("Newest", "Najnowsze"),
    "station.data.newer": Text("‹ Newer", "‹ Nowsze"),
    "station.data.older": Text("Older ›", "Starsze ›"),
    "station.data.oldest": Text("Oldest", "Najstarsze"),
    "station.data.page": Text(
        "page {page} of {pages} · {days}", "strona {page} z {pages} · {days}"
    ),
    "station.data.days.one": Text("{n} day", "{n} dzień"),
    "station.data.days.few": Text("{n} days", "{n} dni"),
    "station.data.days.many": Text("{n} days", "{n} dni"),
    "station.data.days.other": Text("{n} days", "{n} dnia"),
    "station.data.no_characteristics": Text(
        "The characteristics of this station have no values.",
        "Charakterystyki tej stacji nie mają wartości.",
    ),
    "station.data.period": Text("Period", "Okres"),
    "station.data.range": Text("lowest–highest", "min–maks"),
    "station.data.mean": Text("mean", "średni"),
    "station.data.mean_column": Text("mean [{unit}]", "średni [{unit}]"),
    "station.data.max_column": Text("max [{unit}]", "maks [{unit}]"),
    "station.data.month": Text("Month", "Miesiąc"),
    "station.data.annual_note": Text(
        "Year: IMGW-PIB's annual mean; its highest and lowest values are the higher "
        "maximum and the lower minimum of its two half-years (a year without one of "
        "them has a gap).",
        "Rok: średnia roczna IMGW-PIB; maksimum i minimum to większe maksimum i "
        "mniejsze minimum z jego dwóch półroczy (rok bez jednego z półroczy ma lukę).",
    ),
    "station.data.half_note": Text(
        "Half-year {period}: IMGW-PIB's values.",
        "Półrocze {period}: wartości IMGW-PIB.",
    ),
    "station.data.dates_note": Text(
        "Under the minimum and the maximum: when they occurred (a range when on several "
        "days), as IMGW-PIB gives it.",
        "Pod minimum i maksimum: kiedy wystąpiły (zakres, gdy w kilku dniach), według "
        "IMGW-PIB.",
    ),
    "station.data.monthly_note": Text(
        "IMGW-PIB's monthly values: the lowest, the mean and the highest of each month.",
        "Wartości miesięczne IMGW-PIB: najniższa, średnia i najwyższa w każdym "
        "miesiącu.",
    ),
    "station.data.units": Text("Units: {units}.", "Jednostki: {units}."),
    "station.data.hydrological_def": Text(
        "A hydrological year runs from 1 November to 31 October and is named by the "
        "year it ends in.",
        "Rok hydrologiczny trwa od 1 listopada do 31 października i nosi numer roku, w "
        "którym się kończy.",
    ),
    "station.data.calendar_def": Text(
        "The series is published by calendar year; the switch above also counts "
        "hydrological years (November to October).",
        "Szereg jest publikowany według roku kalendarzowego; przełącznik wyżej liczy też "
        "lata hydrologiczne (od listopada do października).",
    ),
    "station.data.stored_hydrological": Text(
        "hydrological year XI–X in the data root",
        "rok hydrologiczny XI–X w katalogu danych",
    ),
    "station.data.stored_calendar": Text(
        "calendar year in the data root", "rok kalendarzowy w katalogu danych"
    ),
    # --- „Pobierz” -----------------------------------------------------------------------
    "station.files.none": Text(
        "The data root holds no series of this station: nothing to download. The "
        "catalog data are in “Station information”.",
        "Katalog danych nie ma szeregów tej stacji: nie ma czego pobrać. Dane katalogowe "
        "są w sekcji „Informacje o stacji”.",
    ),
    "station.files.loading": Text(
        "Loading the list of files…", "Wczytuję listę plików…"
    ),
    "station.files.info": Text(
        "Each file is made by the command obserwator series export (export_series) "
        "from the current version of the series in the server's data root. CSV: UTF-8, "
        "comma, decimal point; the date, the year, each variable with its unit and its "
        "flag, and the provider's lines (attribution_source, attribution_processed, "
        "attribution, terms_notice). JSON: one document obserwator-series-export/1 with "
        "the same columns, the units, the series version, the licence and the "
        "provider's lines. Parquet: the same columns, typed, with the same fields in "
        "the file's metadata.",
        "Każdy plik robi polecenie obserwator series export (export_series) z bieżącej "
        "wersji szeregu w katalogu danych serwera. CSV: UTF-8, przecinek, kropka "
        "dziesiętna; data, rok, każda zmienna z jednostką i flagą oraz linie dostawcy "
        "(attribution_source, attribution_processed, attribution, terms_notice). JSON: "
        "jeden dokument obserwator-series-export/1 z tymi samymi kolumnami, jednostkami, "
        "wersją szeregu, licencją i liniami dostawcy. Parquet: te same kolumny, "
        "typowane, z tymi samymi polami w metadanych pliku.",
    ),
    "station.files.command_format": Text(
        "Format of the command line", "Format polecenia"
    ),
    "station.files.cli": Text(
        "The same from the command line", "To samo z wiersza poleceń"
    ),
    "station.files.copy": Text("Copy", "Kopiuj"),
    "station.files.copied": Text("Copied.", "Skopiowano."),
    "station.files.selected": Text(
        "Selected: press Ctrl+C.", "Zaznaczono: naciśnij Ctrl+C."
    ),
    "station.files.copy_failed": Text(
        "The browser did not allow copying.", "Przeglądarka nie pozwoliła skopiować."
    ),
    "station.files.command_field": Text(
        "Command line to copy", "Polecenie do skopiowania"
    ),
    "station.files.version_note": Text(
        "Without --root the command reads Obserwator's default data root; the file "
        "here is version {version} of the series.",
        "Bez --root polecenie czyta domyślny katalog danych Obserwatora; plik stąd to "
        "wersja {version} szeregu.",
    ),
    "station.files.terms": Text("{provider}'s terms", "Regulamin {provider}"),
    "station.files.licence": Text("Licence {licence}", "Licencja {licence}"),
    "station.files.disclaimer": Text("disclaimer", "wyłączenie odpowiedzialności"),
    "station.files.results": Text(
        "Results of the analyses (JSON)", "Wyniki analiz (JSON)"
    ),
    "station.files.results_info": Text(
        "Each analysis of the station as one JSON document obserwator-analysis/1: "
        "Hydrolog's command, options and version, the series it read (version, "
        "SHA-256), the result or the error, and the providers' lines. Without a stored "
        "result the server computes it on request, which may take a few seconds.",
        "Każda analiza stacji jako jeden dokument JSON obserwator-analysis/1: polecenie "
        "Hydrologa, jego opcje i wersja, szereg, który przeczytał (wersja, SHA-256), "
        "wynik albo błąd oraz linie dostawców. Bez zapisanego wyniku serwer liczy go na "
        "żądanie, co może potrwać kilka sekund.",
    ),
    "station.files.results_count.one": Text(
        "{n} analysis applies to this station.", "Stacji dotyczy {n} analiza."
    ),
    "station.files.results_count.few": Text(
        "{n} analyses apply to this station.", "Stacji dotyczą {n} analizy."
    ),
    "station.files.results_count.many": Text(
        "{n} analyses apply to this station.", "Stacji dotyczy {n} analiz."
    ),
    "station.files.results_count.other": Text(
        "{n} analyses apply to this station.", "Stacji dotyczy {n} analizy."
    ),
    "station.files.results_none": Text(
        "No analysis applies to this station.", "Żadna analiza nie dotyczy tej stacji."
    ),
    "station.files.analysis": Text("Analysis", "Analiza"),
    "station.files.file": Text("File", "Plik"),
    "station.files.stored": Text("stored", "zapisany"),
    "station.files.on_request": Text("on request", "na żądanie"),
    "station.files.handoff": Text("Hand-off to Hydrolog", "Przekazanie do Hydrologa"),
    "station.files.handoff_info": Text(
        "A document nogat-handoff/1 with a series hydrolog-series/1, which Hydrolog "
        "opens in “Statystyka przepływów” (flow statistics): the daily values of the "
        "whole period (a day without a value as null); when the data root holds only "
        "IMGW-PIB's half-year characteristics, the annual maxima Hydrolog's flood "
        "frequency analysis used, with its result. The document carries the provider's "
        "lines and terms.",
        "Dokument nogat-handoff/1 z szeregiem hydrolog-series/1, który Hydrolog otwiera "
        "w „Statystyce przepływów”: wartości dobowe z całego okresu (dzień bez wartości "
        "jako null); gdy katalog danych ma tylko charakterystyki półroczne IMGW-PIB — "
        "maksima roczne, których użyła analiza częstości przepływów Hydrologa, z jej "
        "wynikiem. Dokument niesie linie i warunki dostawcy.",
    ),
    "station.files.handoff_daily": Text(
        "Daily series: the whole period.", "Szereg dobowy: cały okres."
    ),
    "station.files.handoff_annual": Text(
        "Annual maxima of the half-year characteristics (the data root has no daily "
        "series): the whole period.",
        "Maksima roczne z charakterystyk półrocznych (katalog danych nie ma szeregu "
        "dobowego): cały okres.",
    ),
    # --- the hand-off to Hydrolog ---------------------------------------------------------
    "station.handoff.copy": Text("Copy to Hydrolog", "Kopiuj do Hydrologa"),
    "station.handoff.file": Text("Hand-off file", "Plik przekazania"),
    "station.handoff.open": Text("Open Hydrolog", "Otwórz Hydrologa"),
    "station.handoff.copied": Text(
        "The hand-off is on the clipboard.", "Skopiowano przekazanie do schowka."
    ),
    "station.handoff.copy_by_hand": Text(
        "The browser did not allow copying: the text of the hand-off is selected, "
        "press Ctrl+C.",
        "Przeglądarka nie pozwoliła skopiować: tekst przekazania jest zaznaczony, "
        "naciśnij Ctrl+C.",
    ),
    "station.handoff.saved": Text(
        "Saved the file “{file}”.", "Zapisano plik „{file}”."
    ),
    "station.handoff.field": Text(
        "Text of the hand-off to copy", "Tekst przekazania do skopiowania"
    ),
    "station.handoff.how": Text(
        "In Hydrolog: “Statystyka przepływów” → “Wczytaj…” → “Wklej ze schowka” or "
        "“Plik przekazania…”.",
        "W Hydrologu: „Statystyka przepływów” → „Wczytaj…” → „Wklej ze schowka” albo "
        "„Plik przekazania…”.",
    ),
}
