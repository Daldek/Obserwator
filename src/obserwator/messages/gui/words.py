"""Words of the store's keys shared by the views: providers, station kinds, datasets, variables."""

from obserwator.messages import Text

MESSAGES: dict[str, Text] = {
    "words.provider.imgw": Text(
        "Institute of Meteorology and Water Management – National Research Institute",
        "Instytut Meteorologii i Gospodarki Wodnej – Państwowy Instytut Badawczy",
    ),
    "words.provider.chmu": Text(
        "Czech Hydrometeorological Institute", "Czeski Instytut Hydrometeorologiczny"
    ),
    "words.kind.hydro": Text("hydrological", "hydrologiczna"),
    "words.kind.meteo": Text("meteorological", "meteorologiczna"),
    "words.dataset.pl_imgw_hydro_daily.title": Text(
        "Daily hydrological data (IMGW-PIB)", "Dane hydrologiczne dobowe (IMGW-PIB)"
    ),
    "words.dataset.pl_imgw_hydro_daily.short": Text("Daily", "Dobowe"),
    "words.dataset.pl_imgw_hydro_monthly.title": Text(
        "Monthly hydrological data (IMGW-PIB)",
        "Dane hydrologiczne miesięczne (IMGW-PIB)",
    ),
    "words.dataset.pl_imgw_hydro_monthly.short": Text("Monthly", "Miesięczne"),
    "words.dataset.pl_imgw_hydro_semiannual.title": Text(
        "Half-year characteristics (IMGW-PIB)", "Charakterystyki półroczne (IMGW-PIB)"
    ),
    "words.dataset.pl_imgw_hydro_semiannual.short": Text("Half-yearly", "Półroczne"),
    "words.dataset.pl_imgw_meteo_climate_daily.title": Text(
        "Daily climate data (IMGW-PIB)", "Dane klimatyczne dobowe (IMGW-PIB)"
    ),
    "words.dataset.pl_imgw_meteo_climate_daily.short": Text("Climate", "Klimatyczne"),
    "words.dataset.pl_imgw_meteo_precip_daily.title": Text(
        "Daily precipitation data (IMGW-PIB)", "Dane opadowe dobowe (IMGW-PIB)"
    ),
    "words.dataset.pl_imgw_meteo_precip_daily.short": Text("Precipitation", "Opadowe"),
    "words.dataset.pl_imgw_meteo_synop_daily.title": Text(
        "Daily synoptic data (IMGW-PIB)", "Dane synoptyczne dobowe (IMGW-PIB)"
    ),
    "words.dataset.pl_imgw_meteo_synop_daily.short": Text("Synoptic", "Synoptyczne"),
    "words.dataset.cz_chmu_hydro_daily.title": Text(
        "Daily hydrological data (ČHMÚ)", "Dane hydrologiczne dobowe (ČHMÚ)"
    ),
    "words.dataset.cz_chmu_hydro_daily.short": Text("Daily", "Dobowe"),
    "words.dataset.cz_chmu_meteo_daily.title": Text(
        "Daily meteorological data (ČHMÚ)", "Dane meteorologiczne dobowe (ČHMÚ)"
    ),
    "words.dataset.cz_chmu_meteo_daily.short": Text("Daily", "Dobowe"),
    "words.variable.h": Text("water level", "stan wody"),
    "words.variable.q": Text("discharge", "przepływ"),
    "words.variable.t": Text("water temperature", "temperatura wody"),
    "words.variable.tmax": Text("maximum temperature", "temperatura maksymalna"),
    "words.variable.tmin": Text("minimum temperature", "temperatura minimalna"),
    "words.variable.tmean": Text("mean temperature", "temperatura średnia"),
    "words.variable.tground": Text("ground temperature", "temperatura przy gruncie"),
    "words.variable.p": Text("precipitation", "opad"),
    "words.variable.snow_cover": Text("snow cover", "pokrywa śnieżna"),
    "words.variable.fresh_snow": Text("fresh snow", "śnieg świeży"),
    "words.variable.snow_water_equivalent": Text(
        "water equivalent of snow", "równoważnik wodny śniegu"
    ),
    "words.variable.sunshine": Text("sunshine duration", "usłonecznienie"),
    "words.variable.rain_duration": Text("duration of rain", "czas trwania deszczu"),
    "words.variable.snowfall_duration": Text(
        "duration of snowfall", "czas trwania opadu śniegu"
    ),
    "words.variable.sleet_duration": Text(
        "duration of rain with snow", "czas trwania deszczu ze śniegiem"
    ),
    "words.variable.hail_duration": Text("duration of hail", "czas trwania gradu"),
    "words.variable.fog_duration": Text("duration of fog", "czas trwania mgły"),
    "words.variable.mist_duration": Text("duration of mist", "czas trwania zamglenia"),
    "words.variable.rime_duration": Text("duration of rime", "czas trwania sadzi"),
    "words.variable.glaze_duration": Text(
        "duration of glaze", "czas trwania gołoledzi"
    ),
    "words.variable.drifting_snow_duration": Text(
        "duration of low drifting snow", "czas trwania zamieci niskiej"
    ),
    "words.variable.blowing_snow_duration": Text(
        "duration of blowing snow", "czas trwania zamieci wysokiej"
    ),
    "words.variable.haze_duration": Text("duration of haze", "czas trwania zmętnienia"),
    "words.variable.wind_10_duration": Text(
        "duration of wind ≥ 10 m/s", "czas trwania wiatru ≥ 10 m/s"
    ),
    "words.variable.wind_15_duration": Text(
        "duration of wind > 15 m/s", "czas trwania wiatru > 15 m/s"
    ),
    "words.variable.thunderstorm_duration": Text(
        "duration of thunderstorm", "czas trwania burzy"
    ),
    "words.variable.dew_duration": Text("duration of dew", "czas trwania rosy"),
    "words.variable.hoarfrost_duration": Text(
        "duration of hoarfrost", "czas trwania szronu"
    ),
    "words.variable.snow_cover_occurrence": Text(
        "snow cover (0/1)", "pokrywa śnieżna (0/1)"
    ),
    "words.variable.lightning_occurrence": Text("lightning (0/1)", "błyskawica (0/1)"),
    "words.variable.isotherm_lower": Text("lower isotherm", "izoterma dolna"),
    "words.variable.isotherm_upper": Text("upper isotherm", "izoterma górna"),
    "words.variable.actinometry": Text("actinometry", "aktynometria"),
    "words.variable.cloud_cover": Text("cloud cover", "zachmurzenie"),
    "words.variable.wind_speed": Text("wind speed", "prędkość wiatru"),
    "words.variable.vapour_pressure": Text(
        "water vapour pressure", "ciśnienie pary wodnej"
    ),
    "words.variable.humidity": Text("relative humidity", "wilgotność względna"),
    "words.variable.pressure_station": Text(
        "pressure at the station", "ciśnienie na poziomie stacji"
    ),
    "words.variable.pressure_sea": Text(
        "pressure at sea level", "ciśnienie na poziomie morza"
    ),
    "words.variable.p_day": Text("precipitation of the day", "opad w dzień"),
    "words.variable.p_night": Text("precipitation of the night", "opad w nocy"),
    "words.flag.value": Text("value", "wartość"),
    "words.flag.missing": Text("missing", "brak"),
    "words.flag.no_phenomenon": Text("no phenomenon", "brak zjawiska"),
    "words.flag.accumulated": Text("sum of several days", "suma z kilku dni"),
    "words.period.winter": Text("winter (XI–IV)", "zima (XI–IV)"),
    "words.period.summer": Text("summer (V–X)", "lato (V–X)"),
    "words.period.annual": Text("year", "rok"),
}
