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
    "station.analyses_none": Text(
        "The data root holds no stored analyses of this station "
        "(obserwator analyses build stores them).",
        "Katalog danych nie ma zapisanych analiz tej stacji "
        "(zapisuje je obserwator analyses build).",
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
    "station.none.analyses": Text(
        "Stored analyses in the data root", "Zapisane analizy w katalogu danych"
    ),
    "station.none.analyses_version": Text(
        "version {version}, computed {when}", "wersja {version}, policzona {when}"
    ),
    "station.none.no_analyses": Text("none stored", "brak zapisanych"),
    "station.none.no_hydrolog": Text(
        "no Hydrolog: no analyses computed on request",
        "bez Hydrologa: bez analiz liczonych na żądanie",
    ),
    "station.none.files": Text("Download the station list", "Pobierz listę stacji"),
    "station.none.files_info": Text(
        "The stations of the current catalogs as GeoJSON or CSV, stations without "
        "coordinates included: each station's catalog data, its location and the "
        "datasets it has series in.\n\n"
        "The CSV has one row per station (UTF-8, comma as separator, decimal point). "
        "Every file carries the providers' lines: keep them when you use the data "
        "further.\n\n"
        "Sources: IMGW-PIB and ČHMÚ (stations), GUGiK and ČÚZK (the state borders the "
        "locations are checked against)",
        "Stacje bieżących katalogów jako GeoJSON albo CSV, razem ze stacjami bez "
        "współrzędnych: dane katalogowe każdej stacji, jej położenie i zbiory danych, "
        "w których ma szeregi.\n\n"
        "CSV ma wiersz na stację (UTF-8, przecinek jako separator, kropka dziesiętna). "
        "Każdy plik niesie wiersze dostawców: zachowaj je przy dalszym wykorzystaniu "
        "danych.\n\n"
        "Źródła: IMGW-PIB i ČHMÚ (stacje), GUGiK i ČÚZK (granice państw, którymi "
        "sprawdzane są położenia)",
    ),
    "station.none.files_stations": Text("Stations in the file", "Stacje w pliku"),
    "station.none.files_note": Text(
        "The file takes only the list's provider and kind: the dataset chips and "
        "“active only” do not narrow it.",
        "Plik uwzględnia tylko dostawcę i rodzaj wybrane na liście: chipy zbiorów i "
        "„tylko czynne” go nie zawężają.",
    ),
    "station.none.files_cli": Text(
        "{format} from the command line", "{format} z wiersza poleceń"
    ),
    "station.none.files_failed": Text(
        "The station list cannot be offered: {message}",
        "Nie można udostępnić listy stacji: {message}",
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
    "station.info.metres_asl_datum": Text(
        "{value} m a.s.l. ({datum})", "{value} m n.p.m. ({datum})"
    ),
    "station.info.gauge_zero": Text("Gauge zero", "Zero wodowskazu"),
    "station.info.catchment_area": Text("Catchment area", "Powierzchnia zlewni"),
    "station.info.province": Text("Voivodeship", "Województwo"),
    "station.info.district": Text("County (powiat)", "Powiat"),
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
    "station.info.levels": Text(
        "IMGW-PIB's levels and extremes", "Progi i stany ekstremalne IMGW-PIB"
    ),
    "station.info.levels_info": Text(
        "IMGW-PIB's warning and alarm levels of the station and the absolute minimum "
        "and maximum water levels of its gauge, with the dates they occurred.\n\n"
        "H in cm above the gauge zero; the warning and alarm levels as the station's "
        "page gave them on the day of their download.\n\n"
        "Sources: IMGW-PIB, the station's page on hydro.imgw.pl",
        "Stany ostrzegawczy i alarmowy IMGW-PIB dla stacji oraz absolutne minimum i "
        "maksimum stanu wody na jej wodowskazie, z datami ich wystąpienia.\n\n"
        "H w cm nad zerem wodowskazu; stany ostrzegawczy i alarmowy według strony "
        "stacji z dnia ich pobrania.\n\n"
        "Źródła: IMGW-PIB, strona stacji w serwisie hydro.imgw.pl",
    ),
    "station.info.level": Text("Level", "Stan"),
    "station.info.level.warning": Text("Warning level", "Stan ostrzegawczy"),
    "station.info.level.alarm": Text("Alarm level", "Stan alarmowy"),
    "station.info.level.minimum": Text("Absolute minimum", "Absolutne minimum"),
    "station.info.level.maximum": Text("Absolute maximum", "Absolutne maksimum"),
    "station.info.level_date": Text("Date", "Data"),
    "station.info.thresholds": Text("ČHMÚ's thresholds", "Progi ČHMÚ"),
    "station.info.thresholds_info": Text(
        "ČHMÚ's threshold levels and discharges of the station: the flood activity "
        "degrees SPA 1–3 (stupně povodňové aktivity), the drought threshold and "
        "q50.\n\n"
        "The SPA degrees in turn are alertness, readiness and danger; q50 is the level "
        "and discharge of the 50-year flood.\n\n"
        "Sources: {source}",
        "Stany i przepływy progowe ČHMÚ dla stacji: stopnie aktywności powodziowej SPA "
        "1–3 (stupně povodňové aktivity), próg suszy i q50.\n\n"
        "Kolejne stopnie SPA to czujność, gotowość i zagrożenie; q50 to stan i "
        "przepływ wody 50-letniej.\n\n"
        "Źródła: {source}",
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
        "The coverage of each variable in the current version of each series of the "
        "station: the first and the last period with a value and the number of periods "
        "with a value (days, months or half-years), of sums of several days and of "
        "gaps.\n\n"
        "A gap is an unbroken run of periods without a value between the first and the "
        "last; “Gaps” gives the number of such runs. A sum of several days is "
        "precipitation collected over several days and given on the last of them.",
        "Pokrycie każdej zmiennej w bieżącej wersji każdego szeregu stacji: pierwszy i "
        "ostatni okres z wartością oraz liczba okresów z wartością (dni, miesięcy albo "
        "półroczy), sum z kilku dni i luk.\n\n"
        "Luka to nieprzerwany ciąg okresów bez wartości między pierwszym a ostatnim; "
        "„Luki” podaje liczbę takich ciągów. Suma z kilku dni to opad zebrany z kilku "
        "dni i podany w ostatnim z nich.",
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
        "IMGW-PIB's unverified operational values: the water level H, the discharge Q "
        "and the water temperature, each with the time of its measurement (UTC).\n\n"
        "The symbol and its words are the water state against the characteristic "
        "levels, in the colours of the map hydro.imgw.pl: a filled symbol is the state "
        "from the measurements of the last 2 hours, a hollow one the state from the "
        "last 26 hours. The values are refreshed at most every 10 minutes.\n\n"
        "Sources: IMGW-PIB, its public API (danepubliczne.imgw.pl) and the map "
        "hydro.imgw.pl",
        "Niezweryfikowane wartości operacyjne IMGW-PIB: stan wody H, przepływ Q i "
        "temperatura wody, każda z czasem pomiaru (UTC).\n\n"
        "Znak i opis to stan wody względem stanów charakterystycznych, w kolorach mapy "
        "hydro.imgw.pl: znak pełny to stan z pomiarów ostatnich 2 godzin, a z pustym "
        "środkiem stan z ostatnich 26 godzin. Wartości odświeżają się najwyżej co 10 "
        "minut.\n\n"
        "Źródła: IMGW-PIB, publiczne API (danepubliczne.imgw.pl) i mapa hydro.imgw.pl",
    ),
    "station.now.info_meteo": Text(
        "Unverified operational values of an IMGW-PIB automatic station: the "
        "precipitation of the last 10 minutes, the air temperature with the time of "
        "its measurement (UTC), the mean wind and the relative humidity; a synoptic "
        "station also has its last SYNOP report.\n\n"
        "Heavy precipitation (at least heavy rain on Chomicz's scale): P ≥ √t\n"
        "where: P – precipitation total [mm], t – its duration [min]\n\n"
        "The precipitation class, in the colours of the map hydro.imgw.pl, comes from "
        "the 10-minute total, not the 6-hour one: heavy precipitation is here P ≥ √10 "
        "≈ 3.2 mm. The values are refreshed at most every 10 minutes.\n\n"
        "Sources: IMGW-PIB, its public API (danepubliczne.imgw.pl); Chomicz's scale of "
        "rain intensity",
        "Niezweryfikowane wartości operacyjne automatycznej stacji IMGW-PIB: opad "
        "ostatnich 10 minut, temperatura powietrza z czasem pomiaru (UTC), średni "
        "wiatr i wilgotność względna; stacja synoptyczna ma też ostatnią depeszę "
        "SYNOP.\n\n"
        "Opad intensywny (co najmniej silny deszcz w skali Chomicza): P ≥ √t\n"
        "gdzie: P – suma opadu [mm], t – czas trwania opadu [min]\n\n"
        "Klasę opadu, w kolorach mapy hydro.imgw.pl, daje suma 10-minutowa, nie "
        "6-godzinna: opad intensywny to tu P ≥ √10 ≈ 3,2 mm. Wartości odświeżają się "
        "najwyżej co 10 minut.\n\n"
        "Źródła: IMGW-PIB, publiczne API (danepubliczne.imgw.pl); skala natężenia "
        "deszczu Chomicza",
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
        "The station's series of the whole period, in its current version, as CSV, "
        "JSON or Parquet: the date, the year and each variable with its unit and "
        "flag.\n\n"
        "The CSV is text for a spreadsheet (UTF-8, comma as separator, decimal point); "
        "JSON and Parquet have the same columns, Parquet also their types. Every file "
        "carries the provider's lines and terms: keep them when you use the data "
        "further.\n\n"
        "Sources: IMGW-PIB (danepubliczne.imgw.pl) or ČHMÚ (opendata.chmi.cz)",
        "Szereg stacji z całego okresu, w bieżącej wersji, jako CSV, JSON albo "
        "Parquet: data, rok i każda zmienna z jednostką i flagą.\n\n"
        "CSV to tekst do arkusza kalkulacyjnego (UTF-8, przecinek jako separator, "
        "kropka dziesiętna); JSON i Parquet mają te same kolumny, a Parquet także ich "
        "typy. Każdy plik niesie wiersze i warunki dostawcy: zachowaj je przy dalszym "
        "wykorzystaniu danych.\n\n"
        "Źródła: IMGW-PIB (danepubliczne.imgw.pl) albo ČHMÚ (opendata.chmi.cz)",
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
        "Results of the analyses (JSON, CSV)", "Wyniki analiz (JSON, CSV)"
    ),
    "station.files.results_info": Text(
        "The stored results of the station's analyses, computed with the default "
        "options: all of them in one file (JSON or CSV) or each analysis on its "
        "own.\n\n"
        "The CSV is a long table, one value of a result per row; the JSON also gives "
        "the computation's options and the versions of the program and of the series, "
        "needed to cite a result. Results computed on request, with other years or "
        "options, are not in the files.\n\n"
        "Sources: IMGW-PIB or ČHMÚ (the station's series); the explanations of the "
        "analysis cards give the methods and their literature",
        "Zapisane wyniki analiz stacji, policzone z domyślnymi opcjami: wszystkie w "
        "jednym pliku (JSON albo CSV) albo każda analiza osobno.\n\n"
        "CSV to długa tabela, wiersz na jedną wartość wyniku; JSON podaje też opcje "
        "obliczenia oraz wersje programu i szeregu, potrzebne do cytowania wyniku. "
        "Wyniki policzone na żądanie, z innymi latami albo opcjami, nie trafiają do "
        "plików.\n\n"
        "Źródła: IMGW-PIB albo ČHMÚ (szeregi stacji); metody i ich literaturę podają "
        "objaśnienia kart analiz",
    ),
    "station.files.results_count.one": Text(
        "{n} analysis of this station is stored.",
        "Zapisano {n} analizę tej stacji.",
    ),
    "station.files.results_count.few": Text(
        "{n} analyses of this station are stored.",
        "Zapisano {n} analizy tej stacji.",
    ),
    "station.files.results_count.many": Text(
        "{n} analyses of this station are stored.",
        "Zapisano {n} analiz tej stacji.",
    ),
    "station.files.results_count.other": Text(
        "{n} analyses of this station are stored.",
        "Zapisano {n} analizy tej stacji.",
    ),
    "station.files.results_none": Text(
        "The data root holds no analyses of this station.",
        "Katalog danych nie ma zapisanych analiz tej stacji.",
    ),
    "station.files.results_version": Text(
        "Analyses version {version}, computed by Hydrolog {hydrolog} on {when}.",
        "Wersja analiz {version}, policzona Hydrologiem {hydrolog} {when}.",
    ),
    "station.files.analysis": Text("Analysis", "Analiza"),
    "station.files.file": Text("Files", "Pliki"),
    "station.files.handoff": Text("Hand-off to Hydrolog", "Przekazanie do Hydrologa"),
    "station.files.handoff_info": Text(
        "The station's series for Hydrolog, the application for hydrological "
        "computations: the daily values of the whole period or, when the station has "
        "only IMGW-PIB's half-year characteristics, the annual maxima the flood "
        "frequency analysis used, with its result.\n\n"
        "Hydrolog opens the hand-off in “Statystyka przepływów” (flow statistics) and "
        "shows an included result beside its own, for comparison. The hand-off carries "
        "the provider's lines and terms.\n\n"
        "Sources: IMGW-PIB or ČHMÚ (the station's series)",
        "Szereg stacji dla Hydrologa, aplikacji do obliczeń hydrologicznych: wartości "
        "dobowe z całego okresu albo, gdy stacja ma tylko charakterystyki półroczne "
        "IMGW-PIB, maksima roczne, których użyła analiza częstości przepływów, z jej "
        "wynikiem.\n\n"
        "Hydrolog otwiera przekazanie w „Statystyce przepływów”, a dołączony wynik "
        "pokazuje obok własnego, do porównania. Przekazanie niesie wiersze i warunki "
        "dostawcy.\n\n"
        "Źródła: IMGW-PIB albo ČHMÚ (szeregi stacji)",
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
