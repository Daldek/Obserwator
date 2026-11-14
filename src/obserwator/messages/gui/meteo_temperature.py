"""Meteorological sections: „Temperatura” with the climate stripes, „Śnieg”, „Trendy” (Nogat plan M10 to M15)."""

from obserwator.messages import Text

MESSAGES: dict[str, Text] = {
    # --- „Temperatura”: means, extremes, the normal ------------------------------------
    "meteo.temperature.tmean": Text("Tmean", "Tśr"),
    "meteo.temperature.means.title": Text(
        "Means, extremes and the normal", "Średnie, ekstrema i normalna"
    ),
    "meteo.temperature.means.info": Text(
        "The monthly means of Tmean, Tmax and Tmin are computed from the daily "
        "temperatures, and the annual mean from the twelve monthly means. The normal "
        "is the mean Tmean of the years of the reference period, and the anomaly a "
        "year's or a month's mean minus the normal.\n\n"
        "ΔT = T − Tₙ\n"
        "A = Σ (Tmax − Tmin) / m\n"
        "where: ΔT – the anomaly [°C], T – the mean Tmean of a year or a month [°C], "
        "Tₙ – its normal [°C], A – the daily range [°C], Tmax, Tmin – a day's maximum "
        "and minimum temperature [°C], m – the days with both measurements [–]\n\n"
        "A positive anomaly marks a period warmer than the normal, a negative one a "
        "cooler period. A dash „–” marks a month with too many days without a "
        "measurement, or a year with such a month.\n\n"
        "Sources: WMO-No. 1203 (2017), 4.4.1 a, b and 4.4.2; Zhang et al. 2011 "
        "(ETCCDI, index DTR); data: IMGW-PIB or ČHMÚ",
        "Średnie miesięczne Tśr, Tmax i Tmin liczone są z temperatur dobowych, a "
        "średnia roczna z dwunastu średnich miesięcznych. Normalna to średnia Tśr z "
        "lat okresu odniesienia, a anomalia – różnica średniej roku albo miesiąca od "
        "normalnej.\n\n"
        "ΔT = T − Tₙ\n"
        "A = Σ (Tmax − Tmin) / m\n"
        "gdzie: ΔT – anomalia [°C], T – średnia Tśr roku albo miesiąca [°C], Tₙ – jej "
        "normalna [°C], A – amplituda dobowa [°C], Tmax, Tmin – temperatura "
        "maksymalna i minimalna dnia [°C], m – liczba dni z oboma pomiarami [–]\n\n"
        "Anomalia dodatnia oznacza okres cieplejszy od normalnej, ujemna – "
        "chłodniejszy. Kreska „–” to miesiąc z za dużą liczbą dni bez pomiaru albo "
        "rok z takim miesiącem.\n\n"
        "Źródła: WMO-No. 1203 (2017), 4.4.1 a, b i 4.4.2; Zhang i in. 2011 (ETCCDI, "
        "wskaźnik DTR); dane: IMGW-PIB albo ČHMÚ",
    ),
    "meteo.temperature.normal_note.one": Text(
        "{n} year with an annual mean", "{n} rok ze średnią roczną"
    ),
    "meteo.temperature.normal_note.few": Text(
        "{n} years with an annual mean", "{n} lata ze średnią roczną"
    ),
    "meteo.temperature.normal_note.many": Text(
        "{n} years with an annual mean", "{n} lat ze średnią roczną"
    ),
    "meteo.temperature.normal_note.other": Text(
        "{n} years with an annual mean", "{n} roku ze średnią roczną"
    ),
    "meteo.temperature.year": Text("Year {year}", "Rok {year}"),
    "meteo.temperature.anomaly_note": Text("anomaly {value} °C", "anomalia {value} °C"),
    "meteo.temperature.highest_tmax": Text("Highest Tmax", "Najwyższa Tmax"),
    "meteo.temperature.lowest_tmin": Text("Lowest Tmin", "Najniższa Tmin"),
    "meteo.temperature.dtr": Text("Daily range", "Amplituda dobowa"),
    "meteo.temperature.on_average": Text("on average", "średnio"),
    "meteo.temperature.chart_label": Text("Temperature chart", "Wykres temperatury"),
    "meteo.temperature.view.mean": Text("annual mean", "średnia roczna"),
    "meteo.temperature.view.anomaly": Text("anomaly", "anomalia"),
    "meteo.temperature.view.months": Text("months", "miesiące"),
    "meteo.temperature.anomaly_axis": Text(
        "anomaly of {name} [°C]", "anomalia {name} [°C]"
    ),
    "meteo.temperature.anomaly": Text("anomaly", "anomalia"),
    "meteo.temperature.anomaly_title": Text(
        "Anomaly of the annual mean temperature",
        "Anomalia średniej rocznej temperatury",
    ),
    "meteo.temperature.band": Text("mean Tmin–Tmax", "średnia Tmin–Tmax"),
    "meteo.temperature.mean_of": Text("mean {name}", "średnia {name}"),
    "meteo.temperature.temperature_axis": Text("temperature [°C]", "temperatura [°C]"),
    "meteo.temperature.months_title": Text(
        "Annual course of the temperature", "Przebieg roczny temperatury"
    ),
    "meteo.temperature.mean_axis": Text(
        "annual mean {name} [°C]", "średnia roczna {name} [°C]"
    ),
    "meteo.temperature.annual_mean": Text("annual mean", "średnia roczna"),
    "meteo.temperature.normal_value": Text("normal {value} °C", "normalna {value} °C"),
    "meteo.temperature.mean_title": Text(
        "Annual mean temperature", "Średnia roczna temperatura"
    ),
    "meteo.temperature.months_table": Text("Months [°C]", "Miesiące [°C]"),
    "meteo.temperature.col.normal": Text("Normal", "Normalna"),
    "meteo.temperature.col.range": Text("Range", "Ampl."),
    "meteo.temperature.col.abs_max": Text("Abs. max.", "Maks. abs."),
    "meteo.temperature.col.abs_min": Text("Abs. min.", "Min. abs."),
    "meteo.temperature.years_table": Text("Years [°C]", "Lata [°C]"),
    "meteo.temperature.col.anomaly": Text("Anomaly", "Anomalia"),
    "meteo.temperature.col.max_date": Text("Max. (date)", "Maks. (data)"),
    "meteo.temperature.col.min_date": Text("Min. (date)", "Min. (data)"),
    "meteo.temperature.anomalies_all": Text(
        "Monthly anomalies of every year [°C]", "Anomalie miesięcy wszystkich lat [°C]"
    ),
    "meteo.temperature.years_count.one": Text("{n} year", "{n} rok"),
    "meteo.temperature.years_count.few": Text("{n} years", "{n} lata"),
    "meteo.temperature.years_count.many": Text("{n} years", "{n} lat"),
    "meteo.temperature.years_count.other": Text("{n} years", "{n} roku"),
    # --- characteristic days and degree days ---------------------------------------------
    "meteo.temperature.days.title": Text(
        "Characteristic days and degree days", "Dni charakterystyczne i stopniodni"
    ),
    "meteo.temperature.days.info": Text(
        "Characteristic days are set by a temperature threshold: frost days (Tmin < 0 "
        "°C), ice days (Tmax < 0 °C), summer days (Tmax > 25 °C), hot days (Tmax > 30 "
        "°C) and tropical nights (Tmin > 20 °C). Degree days sum the daily departures "
        "of Tmean from a threshold.\n\n"
        "GDD = Σ max(Tmean − 5 °C, 0)\n"
        "HDD = Σ (18 °C − Tmean), over the days with Tmean ≤ 15 °C\n"
        "where: GDD – growing degree days [°C·d], HDD – heating degree days [°C·d], "
        "Tmean – a day's mean temperature [°C]\n\n"
        "The tiles give the mean per year of the period. A year without a bar on the "
        "chart has a month with too many missing days, for degree days a month with "
        "any missing day.\n\n"
        "Sources: Zhang et al. 2011 (ETCCDI: FD, ID, SU, TR); Eurostat 2024 (heating "
        "degree days); WMO-No. 1203 (2017), 4.4.1 d; data: IMGW-PIB or ČHMÚ",
        "Dni charakterystyczne wyznacza próg temperatury: dni z przymrozkiem (Tmin < "
        "0 °C), mroźne (Tmax < 0 °C), gorące (Tmax > 25 °C), upalne (Tmax > 30 °C) i "
        "noce tropikalne (Tmin > 20 °C). Stopniodni sumują dobowe odchylenia Tśr od "
        "progu.\n\n"
        "GDD = Σ max(Tśr − 5 °C, 0)\n"
        "HDD = Σ (18 °C − Tśr), w dniach z Tśr ≤ 15 °C\n"
        "gdzie: GDD – stopniodni wzrostu [°C·d], HDD – stopniodni grzania [°C·d], Tśr "
        "– średnia temperatura dnia [°C]\n\n"
        "Kafelki podają średnią na rok okresu. Rok bez słupka na wykresie ma miesiąc "
        "z za dużą liczbą braków, a przy stopniodniach – miesiąc z jakimkolwiek "
        "brakiem.\n\n"
        "Źródła: Zhang i in. 2011 (ETCCDI: FD, ID, SU, TR); Eurostat 2024 (stopniodni "
        "grzania); WMO-No. 1203 (2017), 4.4.1 d; dane: IMGW-PIB albo ČHMÚ",
    ),
    "meteo.temperature.day.frost_days": Text("frost days", "z przymrozkiem"),
    "meteo.temperature.day.ice_days": Text("ice days", "mroźne"),
    "meteo.temperature.day.summer_days": Text("summer days", "gorące"),
    "meteo.temperature.day.hot_days": Text("hot days", "upalne"),
    "meteo.temperature.day.tropical_nights": Text("tropical nights", "noce tropikalne"),
    "meteo.temperature.day.growing_degree_days": Text(
        "growing degree days", "stopniodni wzrostu"
    ),
    "meteo.temperature.day.heating_degree_days": Text(
        "heating degree days", "stopniodni grzania"
    ),
    "meteo.temperature.per_year": Text(
        "{rule}, mean per year", "{rule}, średnio w roku"
    ),
    "meteo.temperature.index": Text("Index", "Wskaźnik"),
    "meteo.temperature.days_axis": Text(
        "days: {name} ({rule})", "dni: {name} ({rule})"
    ),
    "meteo.temperature.days_title": Text("{name} by year", "{name} w latach"),
    "meteo.temperature.days_months": Text(
        "Mean per month [days]", "Średnio w miesiącu [dni]"
    ),
    # --- harmonics of the annual cycle ----------------------------------------------------
    "meteo.harmonics.title": Text(
        "Annual cycle and harmonics", "Cykl roczny i harmoniki"
    ),
    "meteo.harmonics.info": Text(
        "The mean and two harmonics: cosine waves with a period of a year and of half "
        "a year, fitted by least squares to the daily mean temperatures of the whole "
        "period and of each hydrological year.\n\n"
        "T(d) = A₀ + Σₖ Cₖ·cos(2πk·(d − dₖ) / 365.25)\n"
        "where: T – the daily mean temperature [°C], d – the day of the hydrological "
        "year, 1 = 1 November [–], A₀ – the mean of the cycle [°C], Cₖ – the "
        "amplitude of the harmonic k = 1, 2 [°C], dₖ – the day of its first maximum "
        "[–]\n\n"
        "C₁ is half the range of the first harmonic, and the date beside it the day "
        "of its maximum. The share of the variance is what a harmonic adds to R²; an "
        "R² near 100 % means a cycle that describes the daily values well.\n\n"
        "Sources: Wilks 2011, Statistical Methods in the Atmospheric Sciences, 3rd "
        "ed., section 9.4; data: IMGW-PIB or ČHMÚ",
        "Średnia i dwie harmoniki: fale kosinusoidalne o okresie roku i pół roku, "
        "dopasowane metodą najmniejszych kwadratów do średnich dobowych temperatury "
        "całego okresu i każdego roku hydrologicznego.\n\n"
        "T(d) = A₀ + Σₖ Cₖ·cos(2πk·(d − dₖ) / 365,25)\n"
        "gdzie: T – średnia dobowa temperatura [°C], d – dzień roku hydrologicznego, "
        "1 = 1 listopada [–], A₀ – średnia cyklu [°C], Cₖ – amplituda harmoniki k = "
        "1, 2 [°C], dₖ – dzień jej pierwszego maksimum [–]\n\n"
        "C₁ to połowa rozpiętości pierwszej harmoniki, a data przy niej – termin jej "
        "maksimum. Udział w wariancji to przyrost R² po dodaniu harmoniki; R² bliskie "
        "100 % oznacza cykl dobrze opisujący wartości dobowe.\n\n"
        "Źródła: Wilks 2011, Statistical Methods in the Atmospheric Sciences, 3. "
        "wyd., rozdz. 9.4; dane: IMGW-PIB albo ČHMÚ",
    ),
    "meteo.harmonics.years": Text("Hydrological years", "Lata hydrologiczne"),
    "meteo.harmonics.mean": Text("Mean A₀", "Średnia A₀"),
    "meteo.harmonics.years_note.one": Text(
        "{n} hydrological year, {from}–{to}", "{n} rok hydrologiczny, {from}–{to}"
    ),
    "meteo.harmonics.years_note.few": Text(
        "{n} hydrological years, {from}–{to}", "{n} lata hydrologiczne, {from}–{to}"
    ),
    "meteo.harmonics.years_note.many": Text(
        "{n} hydrological years, {from}–{to}",
        "{n} lat hydrologicznych, {from}–{to}",
    ),
    "meteo.harmonics.years_note.other": Text(
        "{n} hydrological years, {from}–{to}",
        "{n} roku hydrologicznego, {from}–{to}",
    ),
    "meteo.harmonics.amplitude": Text("Amplitude {name}", "Amplituda {name}"),
    "meteo.harmonics.peak": Text("maximum {date}", "maksimum {date}"),
    "meteo.harmonics.shares": Text(
        "Share of the variance: 1st · 2nd", "Udział w wariancji: 1. · 2."
    ),
    "meteo.harmonics.r2": Text("Variance explained (R²)", "Wyjaśniona wariancja (R²)"),
    "meteo.harmonics.daily_values.one": Text("{n} daily value", "{n} wartość dobowa"),
    "meteo.harmonics.daily_values.few": Text("{n} daily values", "{n} wartości dobowe"),
    "meteo.harmonics.daily_values.many": Text(
        "{n} daily values", "{n} wartości dobowych"
    ),
    "meteo.harmonics.daily_values.other": Text(
        "{n} daily values", "{n} wartości dobowej"
    ),
    "meteo.harmonics.day_axis": Text("day of the year", "dzień roku"),
    "meteo.harmonics.first": Text("1st harmonic", "1. harmonika"),
    "meteo.harmonics.fit.one": Text("{n} harmonic", "{n} harmonika"),
    "meteo.harmonics.fit.few": Text("sum of {n} harmonics", "suma {n} harmonik"),
    "meteo.harmonics.fit.many": Text("sum of {n} harmonics", "suma {n} harmonik"),
    "meteo.harmonics.fit.other": Text("sum of {n} harmonics", "suma {n} harmonik"),
    "meteo.harmonics.max_mark": Text("max. {date}", "maks. {date}"),
    "meteo.harmonics.cycle_title": Text(
        "Fitted annual cycle of the temperature", "Dopasowany cykl roczny temperatury"
    ),
    "meteo.harmonics.peak_axis": Text(
        "day of the year of the 1st harmonic's maximum (200 = 19 VII)",
        "dzień roku maksimum 1. harmoniki (200 = 19 VII)",
    ),
    "meteo.harmonics.peak_series": Text("day of the maximum", "termin maksimum"),
    "meteo.harmonics.peak_title": Text(
        "Day of the maximum by year", "Termin maksimum w latach"
    ),
    "meteo.harmonics.years_table": Text("Hydrological years", "Lata hydrologiczne"),
    "meteo.harmonics.col.max": Text("Max. of C{k}", "Maks. C{k}"),
    "meteo.harmonics.col.share": Text("Share of C{k} %", "Udział C{k} %"),
    # --- hydrothermal coefficient ----------------------------------------------------------
    "meteo.hydrothermal.title": Text(
        "Hydrothermal coefficient", "Współczynnik hydrotermiczny"
    ),
    "meteo.hydrothermal.info": Text(
        "Sielianinov's coefficient compares the precipitation with the sum of "
        "temperatures, a measure of the evaporation. It is computed for the months "
        "IV–IX and for the period of the days with a mean daily temperature above 10 "
        "°C.\n\n"
        "k = P / (0.1·Σt)\n"
        "where: k – the hydrothermal coefficient [–], P – the precipitation total of "
        "the month or the period [mm], Σt – the sum of the daily mean temperatures of "
        "its days [°C], for a month its mean times its days\n\n"
        "The optimal class is 1.3 < k ≤ 1.6; a lower k marks ever drier conditions, "
        "extremely dry at k ≤ 0.4, and a higher k ever wetter ones, extremely wet at "
        "k > 3.0.\n\n"
        "Sources: Selyaninov 1928; Skowera and Puła 2004, Acta Agrophysica 3(1) "
        "(classes); WMO-No. 1203 (2017), 4.4.1 a, c; data: IMGW-PIB or ČHMÚ",
        "Współczynnik Sielianinowa porównuje opad z sumą temperatur, która jest miarą "
        "parowania. Liczony dla miesięcy IV–IX i dla okresu dni ze średnią dobową "
        "temperaturą powyżej 10 °C.\n\n"
        "k = P / (0,1·Σt)\n"
        "gdzie: k – współczynnik hydrotermiczny [–], P – suma opadu miesiąca albo "
        "okresu [mm], Σt – suma średnich dobowych temperatur jego dni [°C], w "
        "miesiącu średnia miesięczna razy liczba dni\n\n"
        "Klasa optymalna to 1,3 < k ≤ 1,6; niższy k oznacza warunki coraz suchsze, do "
        "skrajnie suchych przy k ≤ 0,4, a wyższy – coraz wilgotniejsze, do skrajnie "
        "wilgotnych przy k > 3,0.\n\n"
        "Źródła: Sielianinow 1928; Skowera i Puła 2004, Acta Agrophysica 3(1) "
        "(klasy); WMO-No. 1203 (2017), 4.4.1 a, c; dane: IMGW-PIB albo ČHMÚ",
    ),
    "meteo.hydrothermal.season": Text(
        "k of the season Tmean > 10 °C", "k okresu Tśr > 10 °C"
    ),
    "meteo.hydrothermal.mean_class": Text("on average: {name}", "średnio: {name}"),
    "meteo.hydrothermal.month_mean": Text(
        "k of {month} on average", "k {month} średnio"
    ),
    "meteo.hydrothermal.chart_title": Text(
        "Sielianinov's coefficient by year", "Współczynnik Sielianinowa w latach"
    ),
    "meteo.hydrothermal.months_table": Text(
        "Classes of the months {first}–{last}", "Klasy miesięcy {first}–{last}"
    ),
    "meteo.hydrothermal.col.season": Text("Tmean > 10", "Tśr > 10"),
    "meteo.hydrothermal.last_years": Text(
        "The last {shown} years of {count}; the class frequencies below cover them all.",
        "Ostatnie {shown} lat z {count}; częstości klas niżej obejmują wszystkie.",
    ),
    "meteo.hydrothermal.frequency": Text(
        "Frequency of the classes [years]", "Częstość klas [lata]"
    ),
    "meteo.hydrothermal.class.extremely_dry": Text("extremely dry", "skrajnie suchy"),
    "meteo.hydrothermal.class.very_dry": Text("very dry", "bardzo suchy"),
    "meteo.hydrothermal.class.dry": Text("dry", "suchy"),
    "meteo.hydrothermal.class.fairly_dry": Text("fairly dry", "dość suchy"),
    "meteo.hydrothermal.class.optimal": Text("optimal", "optymalny"),
    "meteo.hydrothermal.class.fairly_wet": Text("fairly wet", "dość wilgotny"),
    "meteo.hydrothermal.class.wet": Text("wet", "wilgotny"),
    "meteo.hydrothermal.class.very_wet": Text("very wet", "bardzo wilgotny"),
    "meteo.hydrothermal.class.extremely_wet": Text(
        "extremely wet", "skrajnie wilgotny"
    ),
    # --- climate stripes (M15) -------------------------------------------------------------
    "meteo.stripes.title": Text("Climate stripes", "Paski klimatyczne"),
    "meteo.stripes.info": Text(
        "Each stripe is a calendar year, and its colour the station's annual mean air "
        "temperature (Tmean) against the mean of the years of the scale's centre. A "
        "year without an annual mean is grey and hatched.\n\n"
        "scale from Tₙ − k·σ to Tₙ + k·σ\n"
        "1 colour = 2·k·σ / 16\n"
        "where: Tₙ – the mean of the years of the scale's centre [°C], σ – the "
        "standard deviation of the annual means of the spread's years [°C], k – the "
        "number of standard deviations, 3.0 or 2.6 [–]\n\n"
        "A red stripe is a year warmer than the scale's centre, a blue one a cooler "
        "year; the darker the colour, the larger the difference, and a year beyond "
        "the scale takes the end colour.\n\n"
        "Sources: Hawkins 2018, climate-lab-book.ac.uk/2018/warming-stripes; the FAQ "
        "of showyourstripes.info „How have these graphics been made?” (2025); WMO-No. "
        "1203 (2017), 4.4.1 a and 4.4.2; data: IMGW-PIB or ČHMÚ\n"
        "Climate stripes: the method of Prof. Ed Hawkins (University of Reading), "
        "#ShowYourStripes, showyourstripes.info; the graphics of showyourstripes.info "
        "are licensed CC BY 4.0, and these stripes are drawn by his method from the "
        "station's data\n"
        "ColorBrewer schemes: © 2002 Cynthia Brewer, Mark Harrower and The "
        "Pennsylvania State University, Apache License 2.0. This product includes "
        "color specifications and designs developed by Cynthia Brewer "
        "(http://colorbrewer.org/).",
        "Każdy pasek to jeden rok kalendarzowy, a jego kolor – średnia roczna "
        "temperatura powietrza stacji (Tśr) wobec średniej z lat środka skali. Rok "
        "bez średniej rocznej jest szary i zakreskowany.\n\n"
        "skala od Tₙ − k·σ do Tₙ + k·σ\n"
        "1 kolor = 2·k·σ / 16\n"
        "gdzie: Tₙ – średnia z lat środka skali [°C], σ – odchylenie standardowe "
        "średnich rocznych z lat rozrzutu [°C], k – liczba odchyleń standardowych, "
        "3,0 albo 2,6 [–]\n\n"
        "Czerwony pasek to rok cieplejszy od środka skali, niebieski – chłodniejszy; "
        "im ciemniejszy kolor, tym większa różnica, a rok poza skalą ma kolor "
        "skrajny.\n\n"
        "Źródła: Hawkins 2018, climate-lab-book.ac.uk/2018/warming-stripes; FAQ "
        "showyourstripes.info „How have these graphics been made?” (2025); WMO-No. "
        "1203 (2017), 4.4.1 a i 4.4.2; dane: IMGW-PIB albo ČHMÚ\n"
        "Paski klimatyczne: metoda prof. Eda Hawkinsa (University of Reading), "
        "#ShowYourStripes, showyourstripes.info; grafiki showyourstripes.info są na "
        "licencji CC BY 4.0, a te paski są rysowane jego metodą z danych stacji\n"
        "Palety ColorBrewer: © 2002 Cynthia Brewer, Mark Harrower i The Pennsylvania "
        "State University, licencja Apache 2.0. This product includes color "
        "specifications and designs developed by Cynthia Brewer "
        "(http://colorbrewer.org/).",
    ),
    "meteo.stripes.credit": Text(
        "Method: Ed Hawkins (University of Reading),",
        "Metoda: Ed Hawkins (University of Reading),",
    ),
    "meteo.stripes.no_hydrolog": Text(
        "The stripes are centred on Hydrolog's normal of their reference period, "
        "computed on request, and this server has no Hydrolog program.",
        "Środkiem pasków jest normalna Hydrologa z ich okresu odniesienia, liczona na "
        "żądanie, a ten serwer nie ma programu Hydrolog.",
    ),
    "meteo.stripes.aria.one": Text(
        "Climate stripes of {station}, {first}–{last}: {n} year, from blue (cooler) to "
        "red (warmer) than the mean of {from}–{to}",
        "Paski klimatyczne stacji {station}, {first}–{last}: {n} rok, od niebieskiego "
        "(chłodniej) do czerwonego (cieplej) wobec średniej {from}–{to}",
    ),
    "meteo.stripes.aria.few": Text(
        "Climate stripes of {station}, {first}–{last}: {n} years, from blue (cooler) to "
        "red (warmer) than the mean of {from}–{to}",
        "Paski klimatyczne stacji {station}, {first}–{last}: {n} lata, od niebieskiego "
        "(chłodniej) do czerwonego (cieplej) wobec średniej {from}–{to}",
    ),
    "meteo.stripes.aria.many": Text(
        "Climate stripes of {station}, {first}–{last}: {n} years, from blue (cooler) to "
        "red (warmer) than the mean of {from}–{to}",
        "Paski klimatyczne stacji {station}, {first}–{last}: {n} lat, od niebieskiego "
        "(chłodniej) do czerwonego (cieplej) wobec średniej {from}–{to}",
    ),
    "meteo.stripes.aria.other": Text(
        "Climate stripes of {station}, {first}–{last}: {n} years, from blue (cooler) to "
        "red (warmer) than the mean of {from}–{to}",
        "Paski klimatyczne stacji {station}, {first}–{last}: {n} roku, od niebieskiego "
        "(chłodniej) do czerwonego (cieplej) wobec średniej {from}–{to}",
    ),
    "meteo.stripes.aria_keys": Text(
        "{label}; the arrow keys pick a year", "{label}; strzałki wybierają rok"
    ),
    "meteo.stripes.readout_hint": Text(
        "Point at a year with the cursor or the arrow keys (after selecting the chart "
        "with Tab).",
        "Wskaż rok kursorem albo strzałkami (po wybraniu wykresu klawiszem Tab).",
    ),
    "meteo.stripes.readout": Text(
        "{year}: mean {mean} °C, anomaly {anomaly} °C",
        "{year}: średnia {mean} °C, anomalia {anomaly} °C",
    ),
    "meteo.stripes.readout_grey.one": Text(
        "{year}: no annual mean ({n} month without a monthly mean by WMO-No. 1203)",
        "{year}: brak średniej rocznej ({n} miesiąc bez średniej miesięcznej wg "
        "WMO-No. 1203)",
    ),
    "meteo.stripes.readout_grey.few": Text(
        "{year}: no annual mean ({n} months without a monthly mean by WMO-No. 1203)",
        "{year}: brak średniej rocznej ({n} miesiące bez średniej miesięcznej wg "
        "WMO-No. 1203)",
    ),
    "meteo.stripes.readout_grey.many": Text(
        "{year}: no annual mean ({n} months without a monthly mean by WMO-No. 1203)",
        "{year}: brak średniej rocznej ({n} miesięcy bez średniej miesięcznej wg "
        "WMO-No. 1203)",
    ),
    "meteo.stripes.readout_grey.other": Text(
        "{year}: no annual mean ({n} months without a monthly mean by WMO-No. 1203)",
        "{year}: brak średniej rocznej ({n} miesiąca bez średniej miesięcznej wg "
        "WMO-No. 1203)",
    ),
    "meteo.stripes.scale_label": Text("Colour scale", "Skala kolorów"),
    "meteo.stripes.legend_centre": Text("mean {from}–{to}", "średnia {from}–{to}"),
    "meteo.stripes.no_mean": Text("no annual mean", "brak średniej rocznej"),
    "meteo.stripes.step": Text("1 colour = {value} °C", "1 kolor = {value} °C"),
    "meteo.stripes.whole_record": Text("whole record", "cały zapis"),
    "meteo.stripes.scale_text": Text(
        "Centre of the scale: Hydrolog's normal of {from}–{to} = {value} °C{whole}; "
        "scale ±{k}σ, σ = {sd} °C of the annual means of {sfrom}–{sto}{swhole}: from "
        "{lo} °C to {hi} °C in 16 colours.",
        "Środek skali: normalna Hydrologa z lat {from}–{to} = {value} °C{whole}; skala "
        "±{k}σ, σ = {sd} °C ze średnich rocznych z lat {sfrom}–{sto}{swhole}: od {lo} °C "
        "do {hi} °C w 16 kolorach.",
    ),
    "meteo.stripes.grey_text": Text(
        "Grey years (no annual mean by WMO-No. 1203): {years}.",
        "Lata szare (brak średniej rocznej wg WMO-No. 1203): {years}.",
    ),
    "meteo.stripes.doc_subtitle": Text(
        "Climate stripes {first}–{last} · annual mean air temperature (Tmean)",
        "Paski klimatyczne {first}–{last} · średnia roczna temperatura powietrza (Tśr)",
    ),
    "meteo.stripes.doc_label": Text(
        "{station}: climate stripes {first}–{last}. {credit}",
        "{station}: paski klimatyczne {first}–{last}. {credit}",
    ),
    "meteo.stripes.png_failed": Text(
        "The PNG image could not be drawn.", "Nie udało się narysować obrazu PNG."
    ),
    "meteo.stripes.csv_station": Text(
        "Station: {name} ({code}); dataset {dataset}, series {version}",
        "Stacja: {name} ({code}); zbiór {dataset}, szereg {version}",
    ),
    "meteo.stripes.csv_colours": Text(
        "colour_index: 0 = the darkest blue, 15 = the darkest red; empty = no annual mean",
        "colour_index: 0 = najciemniejszy niebieski, 15 = najciemniejszy czerwony; "
        "pusty = brak średniej rocznej",
    ),
    "meteo.stripes.file": Text(
        "climate-stripes-{code}-{first}-{last}",
        "paski-klimatyczne-{code}-{first}-{last}",
    ),
    "meteo.stripes.file_axis": Text(
        "climate-stripes-{code}-{first}-{last}-axis",
        "paski-klimatyczne-{code}-{first}-{last}-os",
    ),
    "meteo.stripes.csv_label": Text(
        "years, means, anomalies", "lata, średnie, anomalie"
    ),
    "meteo.stripes.view": Text("View", "Widok"),
    "meteo.stripes.view_label": Text("View of the stripes", "Widok pasków"),
    "meteo.stripes.view_plain": Text("stripes", "paski"),
    "meteo.stripes.view_axis": Text(
        "with a year axis and readout", "z osią lat i odczytem"
    ),
    "meteo.stripes.scale": Text("Scale", "Skala"),
    "meteo.stripes.scale_option": Text(
        "FAQ of {version}: {from}–{to}, ±{k}σ", "FAQ z {version}: {from}–{to}, ±{k}σ"
    ),
    "meteo.stripes.centre_range": Text(
        "Centre of the scale (reference period)", "Środek skali (okres odniesienia)"
    ),
    "meteo.stripes.spread_range": Text("Spread σ of the years", "Rozrzut σ z lat"),
    "meteo.stripes.centre_fallback": Text(
        "Centre of the scale: the years {from}–{to} have an annual mean in {years} of "
        "{span} (fewer than 80 %, WMO-No. 1203, 4.4.2); Hydrolog's normal of the whole "
        "record {first}–{last} serves ({count} years with a mean).",
        "Środek skali: lata {from}–{to} mają średnią roczną w {years} z {span} (mniej niż "
        "80 %, WMO-No. 1203, 4.4.2); służy normalna Hydrologa z całego zapisu "
        "{first}–{last} ({count} lat ze średnią).",
    ),
    "meteo.stripes.spread_fallback": Text(
        "Spread σ: the years {from}–{to} have an annual mean in {years} of {span} (fewer "
        "than 80 %, WMO-No. 1203, 4.4.2); the whole record {first}–{last} serves "
        "({count} years with a mean).",
        "Rozrzut σ: lata {from}–{to} mają średnią roczną w {years} z {span} (mniej niż "
        "80 %, WMO-No. 1203, 4.4.2); służy cały zapis {first}–{last} ({count} lat ze "
        "średnią).",
    ),
    "meteo.stripes.centre_figure": Text("Mean {from}–{to}", "Średnia {from}–{to}"),
    "meteo.stripes.centre_of_scale": Text("centre of the scale", "środek skali"),
    "meteo.stripes.years_with_mean.one": Text(
        "{n} year with a mean", "{n} rok ze średnią"
    ),
    "meteo.stripes.years_with_mean.few": Text(
        "{n} years with a mean", "{n} lata ze średnią"
    ),
    "meteo.stripes.years_with_mean.many": Text(
        "{n} years with a mean", "{n} lat ze średnią"
    ),
    "meteo.stripes.years_with_mean.other": Text(
        "{n} years with a mean", "{n} roku ze średnią"
    ),
    "meteo.stripes.scale_figure": Text("Scale ±{k}σ", "Skala ±{k}σ"),
    "meteo.stripes.warmest": Text("Warmest year", "Najcieplejszy rok"),
    "meteo.stripes.coldest": Text("Coldest year", "Najchłodniejszy rok"),
    "meteo.stripes.grey": Text("Grey years: {years}.", "Lata szare: {years}."),
    # --- „Śnieg” -------------------------------------------------------------------------
    "meteo.snow.title": Text("Snow cover", "Pokrywa śnieżna"),
    "meteo.snow.info": Text(
        "A day with snow cover has a cover at least 1 cm deep in IMGW-PIB's morning "
        "observation. A winter runs from 1 August to 31 July and bears on the chart's "
        "axis the year it ends in (1990/91 is 1991).\n\n"
        "The tiles give the means, the largest depth with its date and the medians of "
        "the first and the last day with snow cover over the winters with enough "
        "observations in every month October–May; a note under the tables lists the "
        "others.\n\n"
        "Sources: WMO-No. 1203 (2017), 4.3 and 4.4.1 d; data: IMGW-PIB (fresh snow "
        "from the precipitation posts)",
        "Dzień z pokrywą śnieżną ma pokrywę o grubości co najmniej 1 cm w porannym "
        "pomiarze IMGW-PIB. Sezon zimowy trwa od 1 VIII do 31 VII, a na osi wykresu "
        "nosi rok swojego końca (1990/91 to 1991).\n\n"
        "Kafelki podają średnie, największą grubość z datą i mediany pierwszego i "
        "ostatniego dnia z pokrywą z sezonów, które mają dość pomiarów w każdym "
        "miesiącu X–V; pozostałe sezony wymienia notka pod tabelami.\n\n"
        "Źródła: WMO-No. 1203 (2017), 4.3 i 4.4.1 d; dane: IMGW-PIB (śnieg świeży z "
        "posterunków opadowych)",
    ),
    "meteo.snow.winters": Text("Winters", "Sezony"),
    "meteo.snow.cover_days": Text(
        "Days with snow cover ≥ 1 cm", "Dni z pokrywą ≥ 1 cm"
    ),
    "meteo.snow.per_winter.one": Text(
        "mean per winter, {n} winter", "średnio w sezonie, {n} sezon"
    ),
    "meteo.snow.per_winter.few": Text(
        "mean per winter, {n} winters", "średnio w sezonie, {n} sezony"
    ),
    "meteo.snow.per_winter.many": Text(
        "mean per winter, {n} winters", "średnio w sezonie, {n} sezonów"
    ),
    "meteo.snow.per_winter.other": Text(
        "mean per winter, {n} winters", "średnio w sezonie, {n} sezonu"
    ),
    "meteo.snow.mean_max": Text("Maximum of the winter", "Maksimum sezonu"),
    "meteo.snow.record": Text("Largest depth", "Największa grubość"),
    "meteo.snow.first_last": Text("First · last day", "Pierwszy · ostatni dzień"),
    "meteo.snow.first_last_note": Text(
        "median; extremes {earliest} · {latest}",
        "mediana; skrajnie {earliest} · {latest}",
    ),
    "meteo.snow.fresh": Text("Fresh snow", "Śnieg świeży"),
    "meteo.snow.fresh_note": Text("{days} days per winter", "{days} dni w sezonie"),
    "meteo.snow.chart_label": Text("Snow chart", "Wykres śniegu"),
    "meteo.snow.view_days": Text("days with cover", "dni z pokrywą"),
    "meteo.snow.view_max": Text("maximum", "maksimum"),
    "meteo.snow.season_axis": Text("winter (year of its end)", "sezon (rok końca)"),
    "meteo.snow.max_axis": Text(
        "largest depth of the snow cover [cm]", "maksymalna grubość pokrywy [cm]"
    ),
    "meteo.snow.days_axis": Text("days with snow cover", "dni z pokrywą śnieżną"),
    "meteo.snow.max_series": Text("maximum", "maksimum"),
    "meteo.snow.days_series": Text("days ≥ 1 cm", "dni ≥ 1 cm"),
    "meteo.snow.readout": Text("winter {season}", "sezon {season}"),
    "meteo.snow.max_title": Text(
        "Largest depth of the snow cover by winter",
        "Maksymalna grubość pokrywy w sezonach",
    ),
    "meteo.snow.days_title": Text(
        "Days with snow cover by winter", "Dni z pokrywą śnieżną w sezonach"
    ),
    "meteo.snow.months_table": Text(
        "Days with snow cover per month on average", "Dni z pokrywą średnio w miesiącu"
    ),
    "meteo.snow.seasons_table": Text("Winters", "Sezony"),
    "meteo.snow.col.season": Text("Winter", "Sezon"),
    "meteo.snow.col.days": Text("Days ≥ 1 cm", "Dni ≥ 1 cm"),
    "meteo.snow.col.max": Text("Max. [cm] (date)", "Maks. [cm] (data)"),
    "meteo.snow.col.first": Text("First", "Pierwszy"),
    "meteo.snow.col.last": Text("Last", "Ostatni"),
    "meteo.snow.col.fresh": Text("Fresh [cm]", "Świeży [cm]"),
    "meteo.snow.no_cover": Text(
        "Winters without snow cover: {count}.", "Sezonów bez pokrywy: {count}."
    ),
    "meteo.snow.incomplete": Text(
        "Winters left out for too few observations of the snow cover in October–May: "
        "{seasons}.",
        "Pominięte sezony bez dość pomiarów pokrywy w miesiącach X–V: {seasons}.",
    ),
    # --- „Trendy” ------------------------------------------------------------------------
    "meteo.trends.title": Text(
        "Annual series: the Mann–Kendall test and Sen's slope",
        "Serie roczne: test Manna–Kendalla i nachylenie Sena",
    ),
    "meteo.trends.info": Text(
        "The Mann–Kendall test checks whether an annual series has a monotonic trend, "
        "and Sen's slope is the median of the slopes of the lines joining every pair "
        "of years.\n\n"
        "S = Σ sgn(xⱼ − xᵢ) over all pairs of years tᵢ < tⱼ\n"
        "b = median[(xⱼ − xᵢ) / (tⱼ − tᵢ)]\n"
        "where: xᵢ – the value of the series in the year tᵢ [mm, days or °C], S – the "
        "test statistic [–], b – Sen's slope [mm, days or °C per year]\n\n"
        "A trend is significant when p < α = 0.05 (two-sided test), and the sign of S "
        "tells whether the series rises or falls. The slope and its confidence "
        "interval are given per 10 years, and the line on the chart is Sen's "
        "trend.\n\n"
        "Sources: Mann 1945; Kendall 1975 (variance of S corrected for ties); Sen "
        "1968; Gilbert 1987, 16.5 (confidence interval); Conover 1980 (intercept); "
        "WMO-No. 1203 (2017), years with a complete value; data: IMGW-PIB or ČHMÚ",
        "Test Manna–Kendalla sprawdza, czy seria roczna ma trend monotoniczny, a "
        "nachylenie Sena to mediana nachyleń odcinków łączących wszystkie pary "
        "lat.\n\n"
        "S = Σ sgn(xⱼ − xᵢ) po wszystkich parach lat tᵢ < tⱼ\n"
        "b = mediana[(xⱼ − xᵢ) / (tⱼ − tᵢ)]\n"
        "gdzie: xᵢ – wartość serii w roku tᵢ [mm, dni albo °C], S – statystyka testu "
        "[–], b – nachylenie Sena [mm, dni albo °C na rok]\n\n"
        "Trend jest istotny, gdy p < α = 0,05 (test dwustronny), a znak S mówi, czy "
        "seria rośnie, czy maleje. Nachylenie i jego przedział ufności podano na 10 "
        "lat, a linia na wykresie to trend Sena.\n\n"
        "Źródła: Mann 1945; Kendall 1975 (wariancja S z poprawką na powtórzenia); Sen "
        "1968; Gilbert 1987, 16.5 (przedział ufności); Conover 1980 (wyraz wolny); "
        "WMO-No. 1203 (2017), lata z pełną wartością; dane: IMGW-PIB albo ČHMÚ",
    ),
    "meteo.trends.series.precipitation_sums": Text(
        "Annual precipitation total", "Suma roczna opadu"
    ),
    "meteo.trends.series.precipitation_maxima": Text(
        "Highest daily precipitation", "Maksymalny opad dobowy"
    ),
    "meteo.trends.series.precipitation_days": Text(
        "Days with precipitation ≥ 10 mm", "Dni z opadem ≥ 10 mm"
    ),
    "meteo.trends.series.spells_dry": Text(
        "Longest dry spell (P < 1 mm)", "Najdłuższy okres bezopadowy (P < 1 mm)"
    ),
    "meteo.trends.series.temperature_means": Text(
        "Annual mean temperature", "Średnia roczna temperatura"
    ),
    "meteo.trends.series.temperature_frost_days": Text(
        "Frost days (Tmin < 0 °C)", "Dni z przymrozkiem (Tmin < 0 °C)"
    ),
    "meteo.trends.series.temperature_summer_days": Text(
        "Summer days (Tmax > 25 °C)", "Dni gorące (Tmax > 25 °C)"
    ),
    "meteo.trends.col.series": Text("Series", "Seria"),
    "meteo.trends.col.years": Text("Years", "Lat"),
    "meteo.trends.col.sen": Text("Sen per 10 years", "Sen na 10 lat"),
    "meteo.trends.col.interval": Text("Confidence interval", "Przedział ufności"),
    "meteo.trends.col.trend": Text("Trend", "Trend istotny"),
    "meteo.trends.col.trend_at": Text("Trend at α = {alpha}", "Trend przy α = {alpha}"),
    "meteo.trends.increasing": Text("increasing", "rosnący"),
    "meteo.trends.decreasing": Text("decreasing", "malejący"),
    "meteo.trends.none": Text("none", "brak"),
    "meteo.trends.not_significant": Text("not significant", "nieistotny"),
    "meteo.trends.per_decade": Text(
        "{value} {unit} per 10 years", "{value} {unit}/10 lat"
    ),
    "meteo.trends.sen_line": Text("Sen's trend", "trend Sena"),
}
