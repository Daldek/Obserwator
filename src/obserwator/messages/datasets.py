"""Messages of ``datasets.py``."""

from obserwator.messages import Text

MESSAGES = {
    "meteo_terminowe_opad_data_do": Text(
        "The meteo/terminowe/opad data do not exist on the IMGW servers",
        "Dane meteo/terminowe/opad nie istnieją na serwerach IMGW",
    ),
    "unknown_data_provider_allowed": Text(
        "Unknown data provider: {provider!r}; allowed: {allowed}",
        "Nieznany dostawca danych: {provider!r}; dozwolone: {allowed}",
    ),
    "invalid_kind_dataset_allowed_hydro": Text(
        "Invalid kind of dataset: {kind!r}; allowed: hydro, meteo, groundwater",
        "Nieprawidłowy rodzaj zbioru: {kind!r}; dozwolone: hydro, meteo, groundwater",
    ),
    "unknown_imgw_dataset_allowed_keys": Text(
        "Unknown IMGW dataset: {dataset!r}; allowed keys: {allowed}",
        "Nieznany zbiór IMGW: {dataset!r}; dozwolone klucze: {allowed}",
    ),
    "option_must_number_text_list": Text(
        "The option {option} must be a number, a text or a list: {value!r}",
        "Opcja {option} musi być liczbą, tekstem lub listą: {value!r}",
    ),
    "invalid_value_option": Text(
        "Invalid value of the option {option}: {item!r}",
        "Nieprawidłowa wartość opcji {option}: {item!r}",
    ),
    "option_needs_non_empty_list": Text(
        "The option {option} needs a non-empty list of values",
        "Opcja {option} wymaga niepustej listy wartości",
    ),
    "invalid_year_range_years_option": Text(
        "Invalid year or range of years in the option {option}: {item!r}",
        "Nieprawidłowy rok lub zakres lat w opcji {option}: {item!r}",
    ),
    "invalid_range_years_option": Text(
        "Invalid range of years in the option {option}: {item!r}",
        "Nieprawidłowy zakres lat w opcji {option}: {item!r}",
    ),
    "option_must_contain_integers": Text(
        "The option {option} must contain integers: {item!r}",
        "Opcja {option} musi zawierać liczby całkowite: {item!r}",
    ),
    "months_must_range_1_12": Text(
        "Months must be in the range 1–12",
        "Miesiące muszą należeć do zakresu 1–12",
    ),
    "option_params_applies_only_dataset": Text(
        "The option params applies only to the dataset pl.imgw.hydro_semiannual, not "
        "{key}",
        "Opcja params dotyczy wyłącznie zbioru pl.imgw.hydro_semiannual, nie {key}",
    ),
    "invalid_semi_annual_parameters_allowed": Text(
        "Invalid semi-annual parameters: {items!r}; allowed: H, Q, T",
        "Nieprawidłowe parametry półroczne: {items!r}; dozwolone: H, Q, T",
    ),
    "dataset_has_no_annual_archives": Text(
        "The dataset {key} has no annual archives",
        "Zbiór {key} nie udostępnia archiwów rocznych",
    ),
    "dataset_is_capture": Text(
        "The dataset {key} is a capture: no server publishes its files, store sync "
        "seals the answers kept in the spool into one version a UTC day",
        "Zbiór {key} jest zapisem odpowiedzi: żaden serwer nie publikuje jego plików, "
        "store sync zamyka odpowiedzi zebrane w buforze w jedną wersję na dobę UTC",
    ),
    "invalid_years_dataset_first_year": Text(
        "Invalid years of the dataset {key}; the first year is {first_year}",
        "Nieprawidłowe roczniki zbioru {key}; minimalny rok: {first_year}",
    ),
    "archives_dataset_cover_whole_country": Text(
        "The archives of the dataset {key} cover the whole country; the option "
        "stations applies only to datasets with station files (cz.chmu.* and the "
        "per-station synop archives of IMGW-PIB)",
        "Archiwa zbioru {key} obejmują cały kraj; opcja stations dotyczy wyłącznie "
        "zbiorów z plikami stacji (cz.chmu.* i archiwów synop IMGW-PIB "
        "publikowanych osobno dla każdej stacji)",
    ),
    "station_archives_need_stations_or_months": Text(
        "The dataset {key} needs the option stations (9-digit IMGW-PIB station "
        "codes: the archives cover single stations) or months (the monthly files "
        "of the whole country published for the running year)",
        "Zbiór {key} wymaga opcji stations (9-cyfrowych kodów stacji IMGW-PIB: "
        "archiwa obejmują pojedyncze stacje) albo months (miesięcznych plików "
        "całego kraju publikowanych dla bieżącego roku)",
    ),
    "monthly_station_archives_from_2001": Text(
        "The monthly files of the dataset {key} cover years from 2001; earlier "
        "years need the option stations",
        "Miesięczne pliki zbioru {key} obejmują lata od 2001; wcześniejsze roczniki "
        "wymagają opcji stations",
    ),
    "stations_folders_without_codes": Text(
        "The folders of the dataset {key} are named after the stations, without "
        "their codes, so the option stations does not apply: years select the "
        "files of every station",
        "Foldery zbioru {key} noszą nazwy stacji, bez ich kodów, więc opcja "
        "stations go nie dotyczy: roczniki wybierają pliki wszystkich stacji",
    ),
    "files_named_in_folder_index": Text(
        "The files of the dataset {key} are named only in the server's folder "
        "index: datasets download finds them (its --check lists them)",
        "Pliki zbioru {key} są nazwane wyłącznie w indeksie folderów serwera: "
        "znajduje je datasets download (jego --check je wypisuje)",
    ),
    "dataset_needs_option_years_years": Text(
        "The dataset {key} needs the option years (the years of the archives)",
        "Zbiór {key} wymaga opcji years (roczniki archiwów)",
    ),
    "option_stations_must_list_station": Text(
        "The option stations must be a list of station codes, not a single text",
        "Opcja stations musi być listą kodów stacji, nie pojedynczym tekstem",
    ),
    "invalid_station_codes_expected_least": Text(
        "Invalid {short_name} station codes: {codes}; expected at least one code "
        "matching {station_code_pattern}, e.g. 0-203-1-001000",
        "Nieprawidłowe kody stacji {short_name}: {codes}; oczekiwano co najmniej "
        "jednego kodu zgodnego z {station_code_pattern}, np. 0-203-1-001000",
    ),
    "option_months_does_not_apply": Text(
        "The option months does not apply to the dataset {key}: the {short_name} "
        "files are not monthly",
        "Opcja months nie dotyczy zbioru {key}: pliki {short_name} nie są miesięczne",
    ),
    "option_months_station_month": Text(
        "The option months does not apply to the dataset {key}: years chooses its "
        "{short_name} month files, every month of each year",
        "Opcja months nie dotyczy zbioru {key}: years wybiera jego pliki miesięczne "
        "{short_name}, każdy miesiąc każdego roku",
    ),
    "dataset_needs_option_stations_station": Text(
        "The dataset {key} needs the option stations: {short_name} station codes "
        "(the archives cover single stations)",
        "Zbiór {key} wymaga opcji stations: kodów stacji {short_name} (archiwa "
        "obejmują pojedyncze stacje)",
    ),
    "files_dataset_cover_whole_history": Text(
        "The {short_name} files of the dataset {key} cover the whole history of a "
        "station; the option years does not apply to this dataset",
        "Pliki {short_name} zbioru {key} obejmują całą historię stacji; opcja years "
        "nie dotyczy tego zbioru",
    ),
    "dataset_needs_option_years_without": Text(
        "The dataset {key} needs the option years: without a server listing the "
        "published years are not known",
        "Zbiór {key} wymaga opcji years: bez listingu serwera lata opublikowane nie "
        "są znane",
    ),
    # The links to the IMGW-PIB terms only: no summary of them (Nogat DEV-20.7, ECO-065)
    "provider_notice_imgw": Text("{terms}", "{terms}"),
    "provider_notice_chmu": Text(
        "The CC BY 4.0 licence permits copying, changes and commercial use provided "
        "that the author ČHMÚ is credited, the licence is given and the changes are "
        "marked.",
        "Licencja CC BY 4.0 dopuszcza kopiowanie, zmiany i użycie komercyjne pod "
        "warunkiem uznania autorstwa ČHMÚ, podania licencji i oznaczenia zmian.",
    ),
    # Gdańskie Wody's terms are not known yet (ADR-034, the providers plan's question
    # 1): its terms notice says so, and no server serves its data until they are.
    "provider_notice_gdanskiewody": Text(
        "The terms of use of Gdańskie Wody's data are not known yet: they are shown "
        "only to a signed-in user of pomiary.gdanskiewody.pl, so storing, serving and "
        "passing on the data wait for them.",
        "Warunki korzystania z danych Gdańskich Wód nie są jeszcze znane: serwis "
        "pomiary.gdanskiewody.pl pokazuje je tylko zalogowanym użytkownikom, więc "
        "przechowywanie, udostępnianie i przekazywanie danych czeka na nie.",
    ),
    # PIG-PIB's data are under CC BY 4.0 by dane.gov.pl's dataset 170 (ADR-035); its own
    # terms of reuse are linked by RW, never summarized.
    "provider_notice_pig": Text(
        "The CC BY 4.0 licence permits copying, changes and commercial use provided "
        "that the author PIG-PIB is credited, the licence is given and the changes are "
        "marked.",
        "Licencja CC BY 4.0 dopuszcza kopiowanie, zmiany i użycie komercyjne pod "
        "warunkiem uznania autorstwa PIG-PIB, podania licencji i oznaczenia zmian.",
    ),
    # P8 (Nogat plan 2026-11-20): the notice of a provider of the class "other", in the
    # provider's own words where it says more, and PIG-PIB's, a state service but no
    # hydro-meteorological one (Nogat plan 2026-11-27, S5). Every product with its data
    # carries the Polish text after the provider's lines (obserwator.attribution); the GUI
    # shows it in the page's language.
    "source_notice_other": Text(
        "The data do not come from a national hydrological and meteorological service",
        "Dane nie pochodzą od państwowej służby hydrologiczno-meteorologicznej",
    ),
    "source_notice_gdanskiewody": Text(
        "The data do not come from a national hydrological and meteorological "
        "service; Gdańskie Wody publishes them as raw data without verification",
        "Dane nie pochodzą od państwowej służby hydrologiczno-meteorologicznej; "
        "Gdańskie Wody publikują je jako dane surowe bez weryfikacji",
    ),
    "source_notice_pig": Text(
        "The data come from the groundwater monitoring of the state geological "
        "service (PIG-PIB), not from a national hydrological and meteorological "
        "service",
        "Dane pochodzą z monitoringu wód podziemnych państwowej służby geologicznej "
        "(PIG-PIB), nie od państwowej służby hydrologiczno-meteorologicznej",
    ),
    "license_notice": Text(
        "{attribution}. {notice}",
        "{attribution}. {notice}",
    ),
    "title_hydro_daily": Text(
        "Daily hydrological data",
        "Dane hydrologiczne dobowe",
    ),
    "title_hydro_monthly": Text(
        "Monthly hydrological data",
        "Dane hydrologiczne miesięczne",
    ),
    "title_hydro_semiannual": Text(
        "Semi-annual and annual hydrological data",
        "Dane hydrologiczne półroczne i roczne",
    ),
    "title_meteo_climate_daily": Text(
        "Daily meteorological data from climate stations",
        "Dane meteorologiczne dobowe ze stacji klimatycznych",
    ),
    "title_meteo_precip_daily": Text(
        "Daily meteorological data from precipitation stations",
        "Dane meteorologiczne dobowe ze stacji opadowych",
    ),
    "title_meteo_synop_daily": Text(
        "Daily meteorological data from synoptic stations",
        "Dane meteorologiczne dobowe ze stacji synoptycznych",
    ),
    "title_hydro_stations": Text(
        "List of hydrological stations",
        "Lista stacji hydrologicznych",
    ),
    "title_meteo_stations": Text(
        "List of meteorological stations",
        "Lista stacji meteorologicznych",
    ),
    "title_hydro_now": Text(
        "Current hydrological data: station locations",
        "Bieżące dane hydrologiczne: położenie stacji",
    ),
    "title_meteo_now": Text(
        "Current meteorological data: station locations",
        "Bieżące dane meteorologiczne: położenie stacji",
    ),
    "title_hydro_details": Text(
        "Hydrological station details of hydro.imgw.pl: levels, extremes, gauge zero",
        "Szczegóły stacji hydrologicznych z hydro.imgw.pl: stany progowe, ekstrema, "
        "zero wodowskazu",
    ),
    "title_meteo_details": Text(
        "Meteorological station details of hydro.imgw.pl: location and elevation",
        "Szczegóły stacji meteorologicznych z hydro.imgw.pl: położenie i wysokość",
    ),
    "title_pmaxtp": Text(
        "Maximum precipitation of a given duration and probability of exceedance "
        "(PMAXTP)",
        "Maksymalne opady o określonym czasie trwania i prawdopodobieństwie "
        "przewyższenia (PMAXTP)",
    ),
    "title_hydro_phenomena": Text(
        "Daily hydrological phenomena",
        "Zjawiska hydrologiczne dobowe",
    ),
    "title_meteo_climate_monthly": Text(
        "Monthly meteorological data from climate stations",
        "Dane meteorologiczne miesięczne ze stacji klimatycznych",
    ),
    "title_meteo_precip_monthly": Text(
        "Monthly meteorological data from precipitation stations",
        "Dane meteorologiczne miesięczne ze stacji opadowych",
    ),
    "title_meteo_synop_monthly": Text(
        "Monthly meteorological data from synoptic stations",
        "Dane meteorologiczne miesięczne ze stacji synoptycznych",
    ),
    "title_meteo_climate_terms": Text(
        "Meteorological data at observation times from climate stations",
        "Dane meteorologiczne terminowe ze stacji klimatycznych",
    ),
    "title_meteo_synop_terms": Text(
        "Meteorological data at observation times from synoptic stations",
        "Dane meteorologiczne terminowe ze stacji synoptycznych",
    ),
    "title_warnings_hydro_archive": Text(
        "Archive of hydrological warnings (monthly files)",
        "Archiwum ostrzeżeń hydrologicznych (pliki miesięczne)",
    ),
    "title_warnings_meteo_archive": Text(
        "Archive of meteorological warnings (monthly files)",
        "Archiwum ostrzeżeń meteorologicznych (pliki miesięczne)",
    ),
    "title_actinometric": Text(
        "Actinometric data (solar radiation) of the actinometric stations",
        "Dane aktynometryczne (promieniowanie słoneczne) ze stacji aktynometrycznych",
    ),
    # The datasets of the operational series (ADR-030): the words „dane operacyjne,
    # niezweryfikowane” of Nogat DEV-20.8 wherever operational data meet a person.
    "title_hydro_operational": Text(
        "Hourly hydrological data of hydro.imgw.pl (H, Q, T): operational data, "
        "unverified",
        "Godzinowe dane hydrologiczne z hydro.imgw.pl (H, Q, T): dane operacyjne, "
        "niezweryfikowane",
    ),
    "title_meteo_operational": Text(
        "Meteorological station data of hydro.imgw.pl (captured answers): operational "
        "data, unverified",
        "Dane stacji meteorologicznych z hydro.imgw.pl (zapisane odpowiedzi): dane "
        "operacyjne, niezweryfikowane",
    ),
    "title_hydro_telemetry": Text(
        "Hydrological telemetry, monthly files of 10-minute H, Q, T: operational "
        "data, unverified",
        "Telemetria hydrologiczna, pliki miesięczne z H, Q, T co 10 minut: dane "
        "operacyjne, niezweryfikowane",
    ),
    # The hourly series built from the tiers (ADR-031): verified, telemetry and
    # operational hours, each point with its tier.
    "title_hydro_subdaily": Text(
        "Hourly hydrological series (H, Q, T) of the telemetry and of hydro.imgw.pl: "
        "operational data, unverified, each hour with its tier",
        "Godzinowe serie hydrologiczne (H, Q, T) z telemetrii i z hydro.imgw.pl: dane "
        "operacyjne, niezweryfikowane, każda godzina z poziomem danych",
    ),
    "title_hydro_current": Text(
        "Current hydrological data (captured answers): operational data, unverified",
        "Bieżące dane hydrologiczne (zapisane odpowiedzi): dane operacyjne, "
        "niezweryfikowane",
    ),
    "title_meteo_current": Text(
        "Current meteorological data (captured answers): operational data, unverified",
        "Bieżące dane meteorologiczne (zapisane odpowiedzi): dane operacyjne, "
        "niezweryfikowane",
    ),
    "title_meteo_synop_current": Text(
        "Current data of the synoptic stations (captured answers): operational data, "
        "unverified",
        "Bieżące dane ze stacji synoptycznych (zapisane odpowiedzi): dane operacyjne, "
        "niezweryfikowane",
    ),
    "title_warnings_hydro_current": Text(
        "Current hydrological warnings (captured answers): operational data, "
        "unverified",
        "Bieżące ostrzeżenia hydrologiczne (zapisane odpowiedzi): dane operacyjne, "
        "niezweryfikowane",
    ),
    "title_warnings_meteo_current": Text(
        "Current meteorological warnings (captured answers): operational data, "
        "unverified",
        "Bieżące ostrzeżenia meteorologiczne (zapisane odpowiedzi): dane operacyjne, "
        "niezweryfikowane",
    ),
    "title_hydro_states_current": Text(
        "Water states of the map of hydro.imgw.pl (captured answers): operational "
        "data, unverified",
        "Stany wody z mapy hydro.imgw.pl (zapisane odpowiedzi): dane operacyjne, "
        "niezweryfikowane",
    ),
    "title_meteo_states_current": Text(
        "Precipitation states of the meteorological map of hydro.imgw.pl (captured "
        "answers): operational data, unverified",
        "Stany opadów z mapy stacji meteorologicznych hydro.imgw.pl (zapisane "
        "odpowiedzi): dane operacyjne, niezweryfikowane",
    ),
    # The definitions of IMGW-PIB's format descriptions (danepubliczne.imgw.pl:
    # CODZ, MIES and POLR_publiczne_format.txt, k_d_format.txt, o_d_format.txt,
    # s_d_format.txt, s_d_t_format.txt), with the field names of the files and
    # nothing beyond them.
    "note_imgw_hydro_daily_h": Text(
        "Water level of the day (COSTAN); no value where IMGW-PIB's database has no "
        "data (9999 or NULL in the source file)",
        "Stan wody w danym dniu (COSTAN); brak wartości, gdy baza IMGW-PIB nie ma "
        "danych (9999 albo NULL w pliku źródłowym)",
    ),
    "note_imgw_hydro_daily_q": Text(
        "Discharge of the day (COPRZP); no value on a day for which the discharge "
        "was not computed (99999.999 or NULL in the source file)",
        "Przepływ w danym dniu (COPRZP); brak wartości w dniu, dla którego przepływ "
        "nie był opracowywany (99999.999 albo NULL w pliku źródłowym)",
    ),
    "note_imgw_hydro_daily_t": Text(
        "Water temperature of the day (COPTMP); no value where the database has no "
        "data, e.g. without temperature measurements at the station (99.9 or NULL "
        "in the source file)",
        "Temperatura wody w danym dniu (COPTMP); brak wartości, gdy baza nie ma "
        "danych, np. bez pomiarów temperatury na stacji (99.9 albo NULL w pliku "
        "źródłowym)",
    ),
    "note_imgw_hydro_monthly": Text(
        "{statistic} of the month ({field} with the extremum indicator MCWSKEX = "
        "{code}); no value where the database has no data or the observations of "
        "the month were interrupted",
        "{statistic} w miesiącu ({field} przy wskaźniku ekstremum MCWSKEX = {code}); "
        "brak wartości, gdy baza nie ma danych lub obserwacje w miesiącu były "
        "przerwane",
    ),
    "note_imgw_hydro_semiannual": Text(
        "{statistic} of the winter or summer half-year or of the year (PLWLKS with "
        "PLRDZW = {quantity} and PLWSKEX = {code}); _start and _end: the date of "
        "occurrence of the extremum, from and to; no value where the observations "
        "were interrupted",
        "{statistic} w półroczu zimowym albo letnim albo w roku (PLWLKS przy PLRDZW = "
        "{quantity} i PLWSKEX = {code}); _start i _end: data wystąpienia ekstremum, "
        "od i do; brak wartości, gdy obserwacje były przerwane",
    ),
    "stat_imgw_h_min": Text("Minimum water level", "Minimalny stan wody"),
    "stat_imgw_h_mean": Text("Mean water level", "Średni stan wody"),
    "stat_imgw_h_max": Text("Maximum water level", "Maksymalny stan wody"),
    "stat_imgw_q_min": Text("Minimum discharge", "Minimalny przepływ"),
    "stat_imgw_q_mean": Text("Mean discharge", "Średni przepływ"),
    "stat_imgw_q_max": Text("Maximum discharge", "Maksymalny przepływ"),
    "stat_imgw_t_min": Text("Minimum water temperature", "Minimalna temperatura wody"),
    "stat_imgw_t_mean": Text("Mean water temperature", "Średnia temperatura wody"),
    "stat_imgw_t_max": Text("Maximum water temperature", "Maksymalna temperatura wody"),
    "note_imgw_tmax": Text(
        "Maximum daily air temperature (TMAX)",
        "Maksymalna dobowa temperatura powietrza (TMAX)",
    ),
    "note_imgw_tmin": Text(
        "Minimum daily air temperature (TMIN)",
        "Minimalna dobowa temperatura powietrza (TMIN)",
    ),
    "note_imgw_tmean": Text(
        "Mean daily air temperature (STD)",
        "Średnia dobowa temperatura powietrza (STD)",
    ),
    "note_imgw_tground": Text(
        "Minimum daily air temperature at the ground (TMNG)",
        "Minimalna dobowa temperatura powietrza przy gruncie (TMNG)",
    ),
    "note_imgw_p": Text(
        "Daily precipitation sum (SMDB)",
        "Suma dobowa opadów (SMDB)",
    ),
    "note_imgw_precip_p": Text(
        "Daily precipitation sum (SMDB); flag accumulated: a collective sum for the "
        "preceding days without measurement (status 8), with no indication of when it "
        "fell: a sum with status Z or directly after such a day, also one at the end "
        "of the previous monthly archive",
        "Suma dobowa opadów (SMDB); flaga accumulated: opad zbiorczy za poprzedzające "
        "dni z brakiem pomiaru (status 8), bez określenia, kiedy wystąpił: suma o "
        "statusie Z albo bezpośrednio po takim dniu, także na końcu poprzedniego "
        "archiwum miesięcznego",
    ),
    "note_imgw_snow_cover": Text(
        "Snow cover depth (PKSN)",
        "Wysokość pokrywy śnieżnej (PKSN)",
    ),
    "note_imgw_fresh_snow": Text(
        "Depth of freshly fallen snow (HSS)",
        "Wysokość świeżo spadłego śniegu (HSS)",
    ),
    "note_imgw_snow_water": Text(
        "Water equivalent of snow (RWSN)",
        "Równoważnik wodny śniegu (RWSN)",
    ),
    "note_imgw_sunshine": Text("Sunshine duration (USL)", "Usłonecznienie (USL)"),
    "note_imgw_rain_duration": Text(
        "Duration of rain (DESZ)", "Czas trwania opadu deszczu (DESZ)"
    ),
    "note_imgw_snowfall_duration": Text(
        "Duration of snowfall (SNEG)", "Czas trwania opadu śniegu (SNEG)"
    ),
    "note_imgw_sleet_duration": Text(
        "Duration of rain with snow (DISN)",
        "Czas trwania opadu deszczu ze śniegiem (DISN)",
    ),
    "note_imgw_hail_duration": Text(
        "Duration of hail (GRAD)", "Czas trwania gradu (GRAD)"
    ),
    "note_imgw_fog_duration": Text(
        "Duration of fog (MGLA)", "Czas trwania mgły (MGLA)"
    ),
    "note_imgw_mist_duration": Text(
        "Duration of mist (ZMGL)", "Czas trwania zamglenia (ZMGL)"
    ),
    "note_imgw_rime_duration": Text(
        "Duration of rime (SADZ)", "Czas trwania sadzi (SADZ)"
    ),
    "note_imgw_glaze_duration": Text(
        "Duration of glaze (GOLO)", "Czas trwania gołoledzi (GOLO)"
    ),
    "note_imgw_drifting_snow": Text(
        "Duration of low drifting snow (ZMNI)",
        "Czas trwania zamieci śnieżnej niskiej (ZMNI)",
    ),
    "note_imgw_blowing_snow": Text(
        "Duration of high drifting (blowing) snow (ZMWS)",
        "Czas trwania zamieci śnieżnej wysokiej (ZMWS)",
    ),
    "note_imgw_haze_duration": Text(
        "Duration of haze (ZMET)", "Czas trwania zmętnienia (ZMET)"
    ),
    "note_imgw_wind_10_duration": Text(
        "Duration of wind of at least 10 m/s (FF10)",
        "Czas trwania wiatru o prędkości co najmniej 10 m/s (FF10)",
    ),
    "note_imgw_wind_15_duration": Text(
        "Duration of wind above 15 m/s (FF15)",
        "Czas trwania wiatru o prędkości powyżej 15 m/s (FF15)",
    ),
    "note_imgw_thunderstorm": Text(
        "Duration of thunderstorm (BRZA)", "Czas trwania burzy (BRZA)"
    ),
    "note_imgw_dew_duration": Text(
        "Duration of dew (ROSA)", "Czas trwania rosy (ROSA)"
    ),
    "note_imgw_hoarfrost_duration": Text(
        "Duration of hoarfrost (SZRO)", "Czas trwania szronu (SZRO)"
    ),
    "note_imgw_snow_cover_day": Text(
        "Occurrence of snow cover, 0 or 1 (DZPS)",
        "Wystąpienie pokrywy śnieżnej, 0 albo 1 (DZPS)",
    ),
    "note_imgw_lightning_day": Text(
        "Occurrence of lightning, 0 or 1 (DZBL)",
        "Wystąpienie błyskawicy, 0 albo 1 (DZBL)",
    ),
    "note_imgw_isotherm_lower": Text("Lower isotherm (IZD)", "Izoterma dolna (IZD)"),
    "note_imgw_isotherm_upper": Text("Upper isotherm (IZG)", "Izoterma górna (IZG)"),
    "note_imgw_actinometry": Text("Actinometry (AKTN)", "Aktynometria (AKTN)"),
    "note_imgw_cloud_cover": Text(
        "Mean daily total cloud cover (NOS)",
        "Średnie dobowe zachmurzenie ogólne (NOS)",
    ),
    "note_imgw_wind_speed": Text(
        "Mean daily wind speed (FWS)", "Średnia dobowa prędkość wiatru (FWS)"
    ),
    "note_imgw_vapour_pressure": Text(
        "Mean daily water vapour pressure (CPW)",
        "Średnie dobowe ciśnienie pary wodnej (CPW)",
    ),
    "note_imgw_humidity": Text(
        "Mean daily relative humidity (WLGS)",
        "Średnia dobowa wilgotność względna (WLGS)",
    ),
    "note_imgw_pressure_station": Text(
        "Mean daily pressure at the station level (PPPS)",
        "Średnie dobowe ciśnienie na poziomie stacji (PPPS)",
    ),
    "note_imgw_pressure_sea": Text(
        "Mean daily pressure at sea level (PPPM)",
        "Średnie dobowe ciśnienie na poziomie morza (PPPM)",
    ),
    "note_imgw_p_day": Text(
        "Precipitation sum of the day (WODZ)", "Suma opadu dzień (WODZ)"
    ),
    "note_imgw_p_night": Text(
        "Precipitation sum of the night (WONO)", "Suma opadu noc (WONO)"
    ),
    "title_chmu_hydro_daily": Text(
        "ČHMÚ — daily hydrological data (H, Q, T)",
        "ČHMÚ — dane hydrologiczne dobowe (H, Q, T)",
    ),
    "note_chmu_hydro_daily_h": Text(
        "Daily mean water level (HD); date = the day of DT (…T00:00:00Z)",
        "Średni dobowy stan wody (HD); data = dzień z DT (…T00:00:00Z)",
    ),
    "note_chmu_hydro_daily_q": Text(
        "Daily mean discharge (QD), equal to the mean of the 24 hourly discharges "
        "labelled 00–23Z of that date (day by the Z labels; UTC or fixed CET — not "
        "confirmed by ČHMÚ)",
        "Średni dobowy przepływ (QD), równy średniej 24 przepływów godzinowych o "
        "etykietach 00–23Z tej daty (doba według etykiet Z; UTC albo stały SEČ — "
        "niepotwierdzone przez ČHMÚ)",
    ),
    "note_chmu_hydro_daily_t": Text(
        "Daily mean water temperature (TD)",
        "Średnia dobowa temperatura wody (TD)",
    ),
    "title_chmu_meteo_daily": Text(
        "ČHMÚ — daily meteorological data (precipitation, air temperature, snow)",
        "ČHMÚ — dane meteorologiczne dobowe (opad, temperatura powietrza, śnieg)",
    ),
    "note_chmu_meteo_daily_p": Text(
        "Precipitation sum (SRA) from the morning term (06:00Z) of day D to the "
        "morning term of day D+1, assigned to D; in older records the station's "
        "morning term of the time (e.g. 05:00Z or 07:00Z)",
        "Suma opadu (SRA) od terminu porannego (06:00Z) dnia D do terminu porannego "
        "dnia D+1, przypisana do D; w starszych zapisach poranny termin stacji z "
        "tamtego czasu (np. 05:00Z albo 07:00Z)",
    ),
    "note_chmu_meteo_daily_tmean": Text(
        "Daily mean air temperature (T, AVG) = (T06 + T13 + 2·T20)/4 of the UTC "
        "terms of day D; in older records from the station's terms of the time "
        "(e.g. 05:00, 13:00 and 21:00)",
        "Średnia dobowa temperatura powietrza (T, AVG) = (T06 + T13 + 2·T20)/4 z "
        "terminów UTC dnia D; w starszych zapisach z terminów stacji z tamtego "
        "czasu (np. 05:00, 13:00 i 21:00)",
    ),
    "note_chmu_meteo_daily_tmax": Text(
        "Maximum air temperature (TMA) of the period (D−1 20:00, D 20:00] UTC, "
        "assigned to D; in older records the period ends at the station's evening "
        "term of the time (e.g. 19:00 or 21:00)",
        "Maksymalna temperatura powietrza (TMA) okresu (D−1 20:00, D 20:00] UTC, "
        "przypisana do D; w starszych zapisach okres kończy wieczorny termin stacji "
        "z tamtego czasu (np. 19:00 albo 21:00)",
    ),
    "note_chmu_meteo_daily_tmin": Text(
        "Minimum air temperature (TMI) of the period (D−1 20:00, D 20:00] UTC, "
        "assigned to D; in older records the period ends at the station's evening "
        "term of the time (e.g. 19:00 or 21:00)",
        "Minimalna temperatura powietrza (TMI) okresu (D−1 20:00, D 20:00] UTC, "
        "przypisana do D; w starszych zapisach okres kończy wieczorny termin stacji "
        "z tamtego czasu (np. 19:00 albo 21:00)",
    ),
    "note_chmu_meteo_daily_snow_cover": Text(
        "Total snow depth (SCE) at the morning term (06:00Z) of day D",
        "Całkowita wysokość pokrywy śnieżnej (SCE) w terminie porannym (06:00Z) dnia D",
    ),
    "note_chmu_meteo_daily_fresh_snow": Text(
        "Depth of new snow (SNO) fallen from the morning term (06:00Z) of day D to "
        "the morning term of day D+1, assigned to D",
        "Wysokość śniegu świeżo spadłego (SNO) od terminu porannego (06:00Z) dnia D "
        "do terminu porannego dnia D+1, przypisana do D",
    ),
    "title_chmu_hydro_stations": Text(
        "ČHMÚ — list of hydrological stations",
        "ČHMÚ — wykaz stacji hydrologicznych",
    ),
    "title_chmu_meteo_stations": Text(
        "ČHMÚ — list of meteorological stations",
        "ČHMÚ — wykaz stacji meteorologicznych",
    ),
    "title_chmu_hydro_now": Text(
        "ČHMÚ — current metadata of hydrological stations",
        "ČHMÚ — bieżące metadane stacji hydrologicznych",
    ),
    "title_chmu_meteo_now": Text(
        "ČHMÚ — current metadata of meteorological stations",
        "ČHMÚ — bieżące metadane stacji meteorologicznych",
    ),
    "title_chmu_hydro_recent": Text(
        "ČHMÚ — 10-minute hydrological data of the recent days (H, Q, T): "
        "operational data, unverified",
        "ČHMÚ — dane hydrologiczne z ostatnich dni, co 10 minut (H, Q, T): dane "
        "operacyjne, niezweryfikowane",
    ),
    "title_chmu_hydro_current": Text(
        "ČHMÚ — current 10-minute hydrological data of the day (H, Q, T): "
        "operational data, unverified",
        "ČHMÚ — bieżące dane hydrologiczne doby, co 10 minut (H, Q, T): dane "
        "operacyjne, niezweryfikowane",
    ),
    "title_chmu_hydro_hourly": Text(
        "ČHMÚ — hourly hydrological data (H, Q)",
        "ČHMÚ — dane hydrologiczne godzinowe (H, Q)",
    ),
    "title_chmu_hydro_subdaily": Text(
        "ČHMÚ — hourly hydrological series (H, Q, T) of the validated hours and of the "
        "recent days: operational data where unverified, each hour with its tier",
        "ČHMÚ — godzinowe serie hydrologiczne (H, Q, T) z godzin zweryfikowanych i z "
        "ostatnich dni: dane operacyjne tam, gdzie niezweryfikowane, każda godzina z "
        "poziomem danych",
    ),
    "title_chmu_groundwater_daily": Text(
        "ČHMÚ — daily groundwater data (level, spring yield, water temperature)",
        "ČHMÚ — dane o wodach podziemnych dobowe (poziom zwierciadła, wydajność "
        "źródeł, temperatura wody)",
    ),
    "note_chmu_groundwater_daily_h_asl": Text(
        "Groundwater level of a borehole in metres above sea level (HD, „Hladiny – "
        "denní”, MNM), the daily value; date = the day of DT (…T00:00Z, …T06:00Z or "
        "…T07:00Z)",
        "Poziom zwierciadła wody podziemnej w otworze w metrach n.p.m. (HD, „Hladiny "
        "– denní”, MNM), wartość dobowa; data = dzień z DT (…T00:00Z, …T06:00Z albo "
        "…T07:00Z)",
    ),
    "note_chmu_groundwater_daily_yield": Text(
        "Yield of a spring in litres per second (YD, „Vydatnost – denní”, L_S), the "
        "daily value; date = the day of DT",
        "Wydajność źródła w litrach na sekundę (YD, „Vydatnost – denní”, L_S), "
        "wartość dobowa; data = dzień z DT",
    ),
    "note_chmu_groundwater_daily_t": Text(
        "Water temperature (TD, „Teploty vody – denní”, 0C), the daily value; date = "
        "the day of DT",
        "Temperatura wody (TD, „Teploty vody – denní”, 0C), wartość dobowa; data = "
        "dzień z DT",
    ),
    "title_chmu_groundwater_weekly": Text(
        "ČHMÚ — weekly groundwater data (level, spring yield, water temperature)",
        "ČHMÚ — dane o wodach podziemnych tygodniowe (poziom zwierciadła, wydajność "
        "źródeł, temperatura wody)",
    ),
    "note_chmu_groundwater_weekly_h_asl": Text(
        "Groundwater level of a borehole in metres above sea level (HT, „Hladiny – "
        "týdenní”, MNM), one reading a week (mostly on Wednesday) at its date, the "
        "day of DT; no row between two readings",
        "Poziom zwierciadła wody podziemnej w otworze w metrach n.p.m. (HT, „Hladiny "
        "– týdenní”, MNM), jeden odczyt w tygodniu (zwykle w środę) z jego datą, "
        "dniem z DT; bez wierszy między odczytami",
    ),
    "note_chmu_groundwater_weekly_yield": Text(
        "Yield of a spring in litres per second (YT, „Vydatnost – týdenní”, L_S), one "
        "reading a week (mostly on Wednesday) at its date, the day of DT; no row "
        "between two readings",
        "Wydajność źródła w litrach na sekundę (YT, „Vydatnost – týdenní”, L_S), "
        "jeden odczyt w tygodniu (zwykle w środę) z jego datą, dniem z DT; bez "
        "wierszy między odczytami",
    ),
    "note_chmu_groundwater_weekly_t": Text(
        "Water temperature (TT, „Teploty vody – týdenní”, 0C), one reading a week "
        "(mostly on Wednesday) at its date, the day of DT; no row between two readings",
        "Temperatura wody (TT, „Teploty vody – týdenní”, 0C), jeden odczyt w tygodniu "
        "(zwykle w środę) z jego datą, dniem z DT; bez wierszy między odczytami",
    ),
    "title_chmu_groundwater_recent": Text(
        "ČHMÚ — daily groundwater data of the last months (level, spring yield): "
        "operational data, unverified",
        "ČHMÚ — dane o wodach podziemnych dobowe z ostatnich miesięcy (poziom "
        "zwierciadła, wydajność źródeł): dane operacyjne, niezweryfikowane",
    ),
    "title_chmu_groundwater_current": Text(
        "ČHMÚ — current daily groundwater data (level, spring yield): operational "
        "data, unverified",
        "ČHMÚ — bieżące dane o wodach podziemnych, dobowe (poziom zwierciadła, "
        "wydajność źródeł): dane operacyjne, niezweryfikowane",
    ),
    "title_chmu_groundwater_characteristic": Text(
        "ČHMÚ — characteristics of groundwater objects (quantiles of the level or the "
        "yield per week or month of the year)",
        "ČHMÚ — charakterystyki obiektów wód podziemnych (kwantyle poziomu "
        "zwierciadła albo wydajności w tygodniach lub miesiącach roku)",
    ),
    "title_chmu_groundwater_stations": Text(
        "ČHMÚ — list of groundwater objects (boreholes and springs)",
        "ČHMÚ — wykaz obiektów wód podziemnych (otwory obserwacyjne i źródła)",
    ),
    "title_chmu_groundwater_now": Text(
        "ČHMÚ — current metadata of groundwater objects",
        "ČHMÚ — bieżące metadane obiektów wód podziemnych",
    ),
    # Gdańskie Wody (ADR-034): raw data without verification, by the provider's word.
    "title_gdanskiewody_station_list": Text(
        "Gdańskie Wody — station list (rain gauges, water-level gauges, weather and "
        "water-quality stations)",
        "Gdańskie Wody — wykaz stacji (deszczomierze, wodowskazy, stacje "
        "meteorologiczne i jakości wody)",
    ),
    "title_gdanskiewody_measurements": Text(
        "Gdańskie Wody — hourly measurements, one file per station, quantity and "
        "month: raw data without verification",
        "Gdańskie Wody — pomiary godzinowe, jeden plik na stację, wielkość i "
        "miesiąc: dane surowe bez weryfikacji",
    ),
    "title_gdanskiewody_hydro_hourly": Text(
        "Gdańskie Wody — hourly hydrological series (water level in m a.s.l., "
        "discharge, water temperature): raw data without verification",
        "Gdańskie Wody — godzinowe serie hydrologiczne (poziom wody w m n.p.m., "
        "przepływ, temperatura wody): dane surowe bez weryfikacji",
    ),
    "title_gdanskiewody_meteo_hourly": Text(
        "Gdańskie Wody — hourly meteorological series (precipitation, air "
        "temperature, wind, pressure, humidity, irradiance): raw data without "
        "verification",
        "Gdańskie Wody — godzinowe serie meteorologiczne (opad, temperatura "
        "powietrza, wiatr, ciśnienie, wilgotność, natężenie promieniowania): dane "
        "surowe bez weryfikacji",
    ),
    "title_gdanskiewody_hydro_daily": Text(
        "Gdańskie Wody — daily hydrological series of the provider's day (06:00 to "
        "05:59 UTC): raw data without verification",
        "Gdańskie Wody — dobowe serie hydrologiczne doby dostawcy (od 06:00 do "
        "05:59 UTC): dane surowe bez weryfikacji",
    ),
    "title_gdanskiewody_meteo_daily": Text(
        "Gdańskie Wody — daily meteorological series of the provider's day (06:00 to "
        "05:59 UTC): raw data without verification",
        "Gdańskie Wody — dobowe serie meteorologiczne doby dostawcy (od 06:00 do "
        "05:59 UTC): dane surowe bez weryfikacji",
    ),
    "note_gdanskiewody_hourly": Text(
        "The value the provider labels with the start of the hour (UTC); the hour in "
        "progress is a running partial value",
        "Wartość, którą dostawca oznacza początkiem godziny (UTC); trwająca godzina "
        "ma wartość cząstkową, uzupełnianą na bieżąco",
    ),
    "note_gdanskiewody_h_asl": Text(
        "Water level in metres above sea level as published, the vertical datum not "
        "published; never H, the stage above a gauge zero in cm",
        "Poziom wody w metrach n.p.m., jak go opublikowano, bez podanego układu "
        "wysokości; nigdy H, stan nad zerem wodowskazu w cm",
    ),
    "note_gdanskiewody_daily_sum": Text(
        "Sum of the 24 hourly values of the provider's day D (06:00 of D to 05:59 of "
        "D+1, UTC), rounded to three decimals; missing without all 24",
        "Suma 24 wartości godzinowych doby dostawcy D (od 06:00 dnia D do 05:59 dnia "
        "D+1, UTC), zaokrąglona do trzech miejsc; brak bez wszystkich 24",
    ),
    "note_gdanskiewody_daily_mean": Text(
        "Mean of the 24 hourly values of the provider's day D (06:00 of D to 05:59 of "
        "D+1, UTC), rounded to three decimals; missing without all 24",
        "Średnia 24 wartości godzinowych doby dostawcy D (od 06:00 dnia D do 05:59 "
        "dnia D+1, UTC), zaokrąglona do trzech miejsc; brak bez wszystkich 24",
    ),
    # PIG-PIB (ADR-035): the readings of the MWP database are verified by PIG-PIB
    # before they enter it; the automatic measurements of mwp_auto are „bez walidacji”.
    "title_pig_groundwater_stations": Text(
        "PIG-PIB — groundwater monitoring points (MWP): wells, piezometers and springs "
        "with their hydrogeological description",
        "PIG-PIB — punkty monitoringu wód podziemnych (MWP): studnie, piezometry i "
        "źródła z opisem hydrogeologicznym",
    ),
    "title_pig_groundwater_readings": Text(
        "PIG-PIB — groundwater readings of the MWP database (depth to water, spring "
        "yield), one file per month as published",
        "PIG-PIB — pomiary wód podziemnych z bazy MWP (głębokość do zwierciadła, "
        "wydajność źródeł), jeden plik na miesiąc, jak opublikowano",
    ),
    "title_pig_groundwater_chemistry": Text(
        "PIG-PIB — chemical indicators of groundwater (MWP), as published",
        "PIG-PIB — wskaźniki chemiczne wód podziemnych (MWP), jak opublikowano",
    ),
    "title_pig_groundwater_watchlist": Text(
        "PIG-PIB — watch-list parameters of groundwater (DWD 2020/2184), as published",
        "PIG-PIB — parametry wód podziemnych z listy obserwacyjnej (DWD 2020/2184), jak "
        "opublikowano",
    ),
    "title_pig_groundwater_operational": Text(
        "PIG-PIB — automatic hourly groundwater measurements (mwp_auto), the answers "
        "of each night's harvest: operational data, unverified",
        "PIG-PIB — automatyczne godzinowe pomiary wód podziemnych (mwp_auto), "
        "odpowiedzi każdego nocnego pobrania: dane operacyjne, niezweryfikowane",
    ),
    "title_pig_groundwater_subdaily": Text(
        "PIG-PIB — hourly groundwater series of the automatic points (depth to water, "
        "level in m a.s.l.): operational data, unverified",
        "PIG-PIB — godzinowe serie wód podziemnych punktów automatycznych (głębokość "
        "do zwierciadła, poziom w m n.p.m.): dane operacyjne, niezweryfikowane",
    ),
    "note_pig_depth_to_water": Text(
        "Depth from the ground surface to the groundwater table in metres as published "
        "(„m p.p.t.”), positive below the ground and negative above it (artesian); "
        "the reading of 06:00 UTC at its own date, daily at the automatic points and "
        "on Mondays at the others; no row between two readings",
        "Głębokość od powierzchni terenu do zwierciadła wody podziemnej w metrach, "
        "jak opublikowano („m p.p.t.”), dodatnia poniżej terenu, ujemna nad nim "
        "(samowypływ); odczyt z godziny 06:00 UTC z jego datą, codziennie w punktach "
        "automatycznych, w pozostałych w poniedziałki; bez wierszy między odczytami",
    ),
    "note_pig_h_asl": Text(
        "Groundwater level in metres above sea level, derived: the point's ground "
        "elevation (RZEDNA_TERENU of the points the build read) minus the depth to "
        "water, kept to the depth's centimetre; as accurate as the ground elevation "
        "(whole metres at a tenth of the active points, decimetres at three tenths), "
        "and PIG-PIB names no vertical datum",
        "Poziom zwierciadła wody podziemnej w metrach n.p.m., wyliczony: rzędna "
        "terenu punktu (RZEDNA_TERENU z punktów odczytanych przy budowie) minus "
        "głębokość do zwierciadła, z dokładnością głębokości do centymetra; tak "
        "dokładny jak rzędna terenu (w pełnych metrach w co dziesiątym aktywnym "
        "punkcie, w decymetrach w trzech na dziesięć), a PIG-PIB nie podaje układu "
        "wysokości",
    ),
    "note_pig_spring_yield": Text(
        "Yield of a spring in litres per second as published, the reading of 06:00 "
        "UTC at its own date; no row between two readings",
        "Wydajność źródła w litrach na sekundę, jak opublikowano, odczyt z godziny "
        "06:00 UTC z jego datą; bez wierszy między odczytami",
    ),
    "note_pig_hourly_depth": Text(
        "Depth from the ground surface to the groundwater table in metres, positive "
        "below the ground and negative above it: the automatic hourly value without "
        "validation; mwp_auto stores UTC wall-clock times, so an hour is the stored "
        "time read as UTC, its seconds dropped",
        "Głębokość od powierzchni terenu do zwierciadła wody podziemnej w metrach, "
        "dodatnia poniżej terenu, ujemna nad nim: automatyczna wartość godzinowa bez "
        "walidacji; mwp_auto zapisuje czas UTC, więc godzina to zapisany czas "
        "odczytany jako UTC, bez sekund",
    ),
    "note_pig_hourly_h_asl": Text(
        "Groundwater level in metres above sea level, derived from the hourly depth "
        "and the point's ground elevation (as accurate as the ground elevation; no "
        "vertical datum named)",
        "Poziom zwierciadła wody podziemnej w metrach n.p.m., wyliczony z głębokości "
        "godzinowej i rzędnej terenu punktu (tak dokładny jak rzędna terenu; bez "
        "podanego układu wysokości)",
    ),
}
