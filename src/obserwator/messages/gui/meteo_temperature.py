"""Meteorological sections: „Temperatura” with the climate stripes, „Śnieg”, „Trendy” (Nogat plan M10 to M15)."""

from obserwator.messages import Text

MESSAGES: dict[str, Text] = {
    # --- „Temperatura”: means, extremes, the normal ------------------------------------
    "meteo.temperature.tmean": Text("Tmean", "Tśr"),
    "meteo.temperature.means.title": Text(
        "Means, extremes and the normal", "Średnie, ekstrema i normalna"
    ),
    "meteo.temperature.means.info": Text(
        "Hydrolog computes the monthly means of Tmean, Tmax and Tmin of a month with fewer "
        "than 11 missing days and fewer than 5 in a row, and the annual mean of the twelve "
        "monthly means (WMO-No. 1203, 2017, 4.4.1 a; Hydrolog „meteo temperature”, index "
        "means). The normal is the mean of the reference period (by default the analysed "
        "years: the station's whole record; it can be narrowed, 30 years are the "
        "recommended minimum), computed when at least 80 % of its years have a value "
        "(4.4.2); the anomaly is the difference from the normal. The absolute extremes take "
        "every day with a measurement (4.4.1 b). The daily range is the mean of Tmax − Tmin "
        "of the days with both (index range; DTR of the ETCCDI, Zhang et al. 2011).",
        "Średnie miesięczne Tśr, Tmax i Tmin liczy Hydrolog, gdy w miesiącu brakuje mniej "
        "niż 11 dni i mniej niż 5 kolejnych, a średnią roczną z dwunastu średnich "
        "miesięcznych (WMO-No. 1203, 2017, 4.4.1 a; Hydrolog „meteo temperature”, wskaźnik "
        "means). Normalna to średnia z okresu odniesienia (domyślnie z lat analizy: całego "
        "zapisu stacji; można go zawęzić, zalecany minimalny okres to 30 lat), liczona, gdy "
        "wartość ma co najmniej 80 % lat okresu (4.4.2); anomalia to różnica od normalnej. "
        "Ekstrema bezwzględne biorą wszystkie dni z pomiarem (4.4.1 b). Amplituda dobowa to "
        "średnia Tmax − Tmin dni z oboma pomiarami (wskaźnik range; DTR wg ETCCDI, Zhang i "
        "in. 2011).",
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
        "Characteristic days as the ETCCDI defines them (Zhang et al. 2011): frost days "
        "Tmin < 0 °C (FD), ice days Tmax < 0 °C (ID), summer days Tmax > 25 °C (SU), "
        "tropical nights Tmin > 20 °C (TR), and the hot days Tmax > 30 °C of Polish "
        "practice. The days of a month are the share of such days among the days with a "
        "measurement times the days of the month, when fewer than 11 days and fewer than 5 "
        "in a row are missing (WMO-No. 1203, 4.4.1 d); a year needs its twelve months. "
        "Growing degree days: Σ max(Tmean − 5 °C, 0); heating degree days after Eurostat: "
        "Σ (18 °C − Tmean) over the days with Tmean ≤ 15 °C; both from months without a "
        "missing day. Hydrolog „meteo temperature”, indices days and degree_days.",
        "Dni charakterystyczne wg definicji ETCCDI (Zhang i in. 2011): z przymrozkiem "
        "Tmin < 0 °C (FD), mroźne Tmax < 0 °C (ID), gorące Tmax > 25 °C (SU), noce "
        "tropikalne Tmin > 20 °C (TR) oraz dni upalne Tmax > 30 °C, jak w praktyce "
        "polskiej. Liczba dni miesiąca to udział takich dni wśród dni z pomiarem razy "
        "liczba dni miesiąca, gdy brakuje mniej niż 11 dni i mniej niż 5 kolejnych "
        "(WMO-No. 1203, 4.4.1 d); rok wymaga dwunastu miesięcy. Stopniodni wzrostu: "
        "Σ max(Tśr − 5 °C, 0); stopniodni grzania wg Eurostatu: Σ (18 °C − Tśr) w dniach "
        "z Tśr ≤ 15 °C; obie sumy z miesięcy bez braków. Hydrolog „meteo temperature”, "
        "wskaźniki days i degree_days.",
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
        "Harmonic analysis of the annual cycle of the daily mean temperature (Hydrolog "
        "„stats harmonics”; Wilks 2011, 9.4): least squares fit T(d) = A₀ + Σₖ Cₖ·cos(2πk"
        "(d − dₖ)/365.25) on the day d of the hydrological year (1 = 1 November), over "
        "the whole period and in each hydrological year with at least 300 days with a "
        "value; Cₖ is the amplitude, dₖ the day of the first maximum (shown as a calendar "
        "date), the share of the variance what each harmonic adds to R² of the daily "
        "values. The author used the same method for the water temperature of Baltic "
        "buoys; in the plan it is M12, shared with H14.",
        "Analiza harmoniczna cyklu rocznego średniej dobowej temperatury (Hydrolog „stats "
        "harmonics”; Wilks 2011, 9.4): metodą najmniejszych kwadratów T(d) = A₀ + Σₖ Cₖ·"
        "cos(2πk(d − dₖ)/365,25) na dniu d roku hydrologicznego (1 = 1 listopada), dla "
        "całego okresu i każdego roku hydrologicznego z co najmniej 300 dniami z wartością; "
        "Cₖ to amplituda, dₖ dzień pierwszego maksimum (podany jako data kalendarzowa), "
        "udział w wariancji — przyrost R² wartości dobowych kolejnych harmonik. Tę samą "
        "metodę autor stosował do temperatury wody z boi bałtyckich; w planie to M12, "
        "wspólne z H14.",
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
        "Sielianinov's hydrothermal coefficient k = P / (0.1·Σt) (Hydrolog „meteo "
        "hydrothermal”): P is the precipitation total of a month [mm], Σt the sum of the "
        "daily temperatures, here the monthly mean times the days of the month (Skowera "
        "and Puła 2004, Acta Agrophysica 3(1)), for the months IV–IX with a positive mean "
        "temperature and both values complete (WMO-No. 1203, 4.4.1 a, c). Classes of "
        "Skowera and Puła (2004): k ≤ 0.4 extremely dry, ≤ 0.7 very dry, ≤ 1.0 dry, ≤ 1.3 "
        "fairly dry, ≤ 1.6 optimal, ≤ 2.0 fairly wet, ≤ 2.5 wet, ≤ 3.0 very wet, > 3.0 "
        "extremely wet. „Season Tmean > 10 °C” is the original version (Selyaninov 1928): "
        "the precipitation and the temperature sum of the days with a mean above 10 °C in "
        "a year with both values on every day.",
        "Współczynnik hydrotermiczny Sielianinowa k = P / (0,1·Σt) (Hydrolog „meteo "
        "hydrothermal”): P to suma opadu miesiąca [mm], Σt suma temperatur dobowych "
        "miesiąca, tu średnia miesięczna razy liczba dni (jak Skowera i Puła 2004, Acta "
        "Agrophysica 3(1)), dla miesięcy IV–IX z dodatnią średnią temperaturą i pełnymi "
        "obiema wartościami (WMO-No. 1203, 4.4.1 a, c). Klasy Skowery i Puły (2004): "
        "k ≤ 0,4 skrajnie suchy, ≤ 0,7 bardzo suchy, ≤ 1,0 suchy, ≤ 1,3 dość suchy, "
        "≤ 1,6 optymalny, ≤ 2,0 dość wilgotny, ≤ 2,5 wilgotny, ≤ 3,0 bardzo wilgotny, "
        "> 3,0 skrajnie wilgotny. „Okres Tśr > 10 °C” to wersja pierwotna (Sielianinow "
        "1928): opad i suma temperatur dni ze średnią powyżej 10 °C w roku z obiema "
        "wartościami w każdym dniu.",
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
        "Ed Hawkins's warming stripes (University of Reading, 2018; showyourstripes.info, "
        "climate-lab-book.ac.uk/2018/warming-stripes): each stripe is a calendar year and "
        "its colour the station's annual mean air temperature (Tmean). Hydrolog computes "
        "the annual means from twelve monthly means of months with fewer than 11 missing "
        "days and fewer than 5 in a row (WMO-No. 1203, 4.4.1 a), the normal of the centre "
        "period and each year's anomaly from it (temperature.means); a year without an "
        "annual mean is grey and hatched. The colour scale is a prototype of this server "
        "until Hydrolog has it (M15), as in the FAQ of showyourstripes.info („How have "
        "these graphics been made?”, 2025): the boundary between blue and red is the mean "
        "of 1961–2010 and the colours span ±3.0 standard deviations of the annual means of "
        "1901–2000. The page's version of June 2019 gave 1971–2000 and ±2.6σ; it can be "
        "chosen. 16 colours divide the range into equal parts, years beyond it take the "
        "end colour; the standard deviation is the sample one (n − 1), which the FAQ does "
        "not specify. A period with an annual mean in fewer than 80 % of its years "
        "(WMO-No. 1203, 4.4.2) gives way to the station's whole record. Both periods can "
        "be changed; 30 years are the recommended minimum. The colours are the 8 darkest "
        "of ColorBrewer's 9-class Blues and Reds, as Hawkins uses them. This product "
        "includes color specifications and designs developed by Cynthia Brewer "
        "(http://colorbrewer.org/). ColorBrewer schemes: © 2002 Cynthia Brewer, Mark "
        "Harrower and The Pennsylvania State University, Apache License 2.0. The graphics "
        "of showyourstripes.info are licensed CC BY 4.0, crediting Prof. Ed Hawkins "
        "(University of Reading) and linking to showyourstripes.info; these stripes are "
        "drawn anew from the station's data by his method, so the panel and every file "
        "give „Method: Ed Hawkins (University of Reading), #ShowYourStripes” with the link "
        "https://showyourstripes.info. The PNG and SVG carry the station's name, the "
        "period, this line and the data provider's lines and terms (DEV-20.5); the CSV the "
        "years, means, anomalies, colours and the columns attribution and terms_notice.",
        "Paski klimatyczne (warming stripes) Eda Hawkinsa (University of Reading, 2018; "
        "showyourstripes.info, climate-lab-book.ac.uk/2018/warming-stripes): każdy pasek "
        "to jeden rok kalendarzowy, a jego kolor to średnia roczna temperatura powietrza "
        "(Tśr) stacji. Średnie roczne liczy Hydrolog z dwunastu średnich miesięcznych "
        "miesięcy, w których brakuje mniej niż 11 dni i mniej niż 5 kolejnych "
        "(WMO-No. 1203, 4.4.1 a), a także normalną okresu środka skali i anomalię każdego "
        "roku od niej (temperature.means); rok bez średniej rocznej jest szary i "
        "zakreskowany. Skala kolorów to prototyp tego serwera, dopóki nie ma jej "
        "Hydrolog (M15), jak w FAQ showyourstripes.info („How have these graphics been "
        "made?”, 2025): granicą między niebieskim a czerwonym jest średnia z lat "
        "1961–2010, a kolory obejmują ±3,0 odchylenia standardowego średnich rocznych z "
        "lat 1901–2000. Wersja tej strony z czerwca 2019 r. podawała 1971–2000 i ±2,6σ; "
        "można ją wybrać. 16 kolorów dzieli przedział na równe części, lata poza nim mają "
        "kolor skrajny; odchylenie standardowe jest z próby (n − 1), bo FAQ go nie "
        "określa. Okres, w którym średnią roczną ma mniej niż 80 % lat (WMO-No. 1203, "
        "4.4.2), zastępuje cały zapis stacji. Oba okresy można zmienić; zalecany "
        "minimalny okres to 30 lat. Kolory to 8 najciemniejszych barw 9-klasowych palet "
        "Blues i Reds z ColorBrewer, jak u Hawkinsa. This product includes color "
        "specifications and designs developed by Cynthia Brewer (http://colorbrewer.org/). "
        "Palety ColorBrewer: © 2002 Cynthia Brewer, Mark Harrower i The Pennsylvania State "
        "University, licencja Apache 2.0. Grafiki showyourstripes.info są udostępnione na "
        "licencji CC BY 4.0 z obowiązkiem podania autora, prof. Eda Hawkinsa (University "
        "of Reading), i odnośnika do showyourstripes.info; te paski są rysowane od nowa z "
        "danych stacji jego metodą, więc panel i każdy plik podają „Metoda: Ed Hawkins "
        "(University of Reading), #ShowYourStripes” z odnośnikiem "
        "https://showyourstripes.info. PNG i SVG mają w obrazie nazwę stacji, okres, tę "
        "linię oraz linie dostawcy danych i warunki (DEV-20.5); CSV ma lata, średnie, "
        "anomalie, kolory oraz kolumny attribution i terms_notice.",
    ),
    "meteo.stripes.credit": Text(
        "Method: Ed Hawkins (University of Reading),",
        "Metoda: Ed Hawkins (University of Reading),",
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
        "Środek skali: normalna Hydrologu z lat {from}–{to} = {value} °C{whole}; skala "
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
        "80 %, WMO-No. 1203, 4.4.2); służy normalna Hydrologu z całego zapisu "
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
    "meteo.stripes.method": Text(
        "Colour scale of Ed Hawkins's climate stripes (showyourstripes.info): ±k sample "
        "standard deviations of the annual means of the spread period around Hydrolog's "
        "normal of the reference period, in 16 equal steps of ColorBrewer's 8 Blues and "
        "8 Reds; a period with an annual mean in fewer than 80 % of its years "
        "(WMO-No. 1203, 4.4.2) gives way to the whole record.",
        "Skala kolorów pasków klimatycznych Eda Hawkinsa (showyourstripes.info): ±k "
        "odchyleń standardowych z próby średnich rocznych okresu rozrzutu wokół "
        "normalnej Hydrologu z okresu odniesienia, w 16 równych przedziałach 8 barw "
        "Blues i 8 Reds palety ColorBrewer; okres ze średnią roczną w mniej niż 80 % "
        "lat (WMO-No. 1203, 4.4.2) zastępuje cały zapis.",
    ),
    # --- „Śnieg” -------------------------------------------------------------------------
    "meteo.snow.title": Text("Snow cover", "Pokrywa śnieżna"),
    "meteo.snow.info": Text(
        "A winter is the season from 1 August to 31 July named after the year it ends in "
        "(the winter 1990/91 is „1991”; Hydrolog „meteo snow”). A day with snow cover has "
        "a depth of at least 1 cm in IMGW-PIB's morning observation. The days of a month "
        "are the share of days with cover among the days with an observation times the "
        "days of the month when fewer than 11 days and fewer than 5 in a row are missing "
        "(WMO-No. 1203, 2017, 4.3 and 4.4.1 d), else the days observed; a winter is "
        "counted when every month October–May has enough days. The largest depth, the "
        "first and the last day with cover and the sum of fresh snow (precipitation "
        "posts, „fresh_snow”) take the days the winter has. The typical dates are the "
        "medians of the days of the season.",
        "Sezon zimowy trwa od 1 VIII do 31 VII i nosi rok swojego końca (sezon 1990/91 to "
        "„1991”; Hydrolog „meteo snow”). Dzień z pokrywą śnieżną to dzień z grubością "
        "pokrywy co najmniej 1 cm w porannym pomiarze IMGW-PIB. Liczba dni miesiąca to "
        "udział dni z pokrywą wśród dni z pomiarem razy liczba dni miesiąca, gdy brakuje "
        "mniej niż 11 dni i mniej niż 5 kolejnych (WMO-No. 1203, 2017, 4.3 i 4.4.1 d), "
        "inaczej liczba dni zaobserwowanych; sezon liczy się, gdy każdy miesiąc X–V ma "
        "dość dni. Maksimum, pierwszy i ostatni dzień z pokrywą oraz suma śniegu świeżego "
        "(stacje opadowe, „fresh_snow”) biorą dni, które sezon ma. Terminy typowe to "
        "mediany dni sezonu.",
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
        "Hydrolog's Mann–Kendall test („stats mann-kendall”, two-sided, significance "
        "level 0.05, Var(S) corrected for ties after Kendall 1975) with Sen's slope (1968: "
        "the median of the slopes of all pairs of years), its 1 − α confidence interval "
        "after Gilbert (1987, 16.5) and Conover's intercept (1980) of the annual series "
        "Hydrolog gives: the annual precipitation total, the highest daily precipitation, "
        "the days with precipitation ≥ 10 mm, the longest dry spell (P < 1 mm, the spell "
        "counted in the year it starts), the annual mean temperature, the frost days and "
        "the summer days (when the station measures temperature). Years without a complete "
        "value (WMO-No. 1203) are left out, which keeps the order of the others. The "
        "slope is shown per 10 years.",
        "Test Manna–Kendalla liczy Hydrolog („stats mann-kendall”, dwustronny, poziom "
        "istotności 0,05, wariancja S z poprawką na powtórzenia wg Kendalla 1975) z "
        "nachyleniem Sena (1968: mediana nachyleń wszystkich par lat), jego przedziałem "
        "ufności 1 − α wg Gilberta (1987, 16.5) i wyrazem wolnym Conovera (1980) dla serii "
        "rocznych, które daje Hydrolog: suma roczna opadu, maksymalny opad dobowy, dni z "
        "opadem ≥ 10 mm, najdłuższy okres bezopadowy (P < 1 mm, ciąg przypisany do roku "
        "początku), średnia roczna temperatura, dni z przymrozkiem i dni gorące (gdy "
        "stacja mierzy temperaturę). Lata bez pełnej wartości (wg WMO-No. 1203) są "
        "pomijane, co nie zmienia porządku pozostałych. Nachylenie podano na 10 lat.",
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
