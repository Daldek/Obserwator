"""Words of the store's keys shared by the views: providers, station kinds, datasets, variables."""

from obserwator.messages import Text

MESSAGES: dict[str, Text] = {
    "words.provider.imgw_pib": Text(
        "Institute of Meteorology and Water Management – National Research Institute",
        "Instytut Meteorologii i Gospodarki Wodnej – Państwowy Instytut Badawczy",
    ),
    "words.provider.chmi": Text(
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
    "words.dataset.cz_chmi_hydro_daily.title": Text(
        "Daily hydrological data (ČHMÚ)", "Dane hydrologiczne dobowe (ČHMÚ)"
    ),
    "words.dataset.cz_chmi_hydro_daily.short": Text("Daily", "Dobowe"),
    "words.dataset.cz_chmi_meteo_daily.title": Text(
        "Daily meteorological data (ČHMÚ)", "Dane meteorologiczne dobowe (ČHMÚ)"
    ),
    "words.dataset.cz_chmi_meteo_daily.short": Text("Daily", "Dobowe"),
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
    "words.flag.value": Text("value", "wartość"),
    "words.flag.missing": Text("missing", "brak"),
    "words.flag.no_phenomenon": Text("no phenomenon", "brak zjawiska"),
    "words.flag.accumulated": Text("sum of several days", "suma z kilku dni"),
    "words.period.winter": Text("winter (XI–IV)", "zima (XI–IV)"),
    "words.period.summer": Text("summer (V–X)", "lato (V–X)"),
    "words.period.annual": Text("year", "rok"),
}
