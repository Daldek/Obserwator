"""Meteorological sections: „Opady”, „Susze i okresy bezopadowe” (Nogat plan M1 to M9).

Also the titles of every meteorological section (the registry ``meteo/index.js``), the
words both halves of the meteorological sections share (``meteo.common.*``) and the
notices of Hydrolog's ``meteo precipitation``, ``meteo spi`` and ``stats
flood-frequency`` (``sections.notice.<code>``, their placeholders the notices' details).
"""

from obserwator.messages import Text

MESSAGES: dict[str, Text] = {
    # --- the registry's titles -----------------------------------------------------------
    "meteo.title.opady": Text("Precipitation", "Opady"),
    "meteo.title.susze": Text("Droughts and dry spells", "Susze i okresy bezopadowe"),
    "meteo.title.temperatura": Text("Temperature", "Temperatura"),
    "meteo.title.snieg": Text("Snow", "Śnieg"),
    "meteo.title.trendy": Text("Trends", "Trendy"),
    # --- words of both halves ----------------------------------------------------------
    "meteo.common.year": Text("Year", "Rok"),
    "meteo.common.years": Text("Years", "Lata"),
    "meteo.common.month": Text("Month", "Miesiąc"),
    "meteo.common.year_axis": Text("year", "rok"),
    "meteo.common.hydro_year_axis": Text("hydrological year", "rok hydrologiczny"),
    "meteo.common.month_axis": Text("month", "miesiąc"),
    "meteo.common.year_readout": Text("year {year}", "rok {year}"),
    "meteo.common.year_type_label": Text("Kind of year", "Rodzaj roku"),
    "meteo.common.year_type.calendar": Text("calendar", "kalendarzowy"),
    "meteo.common.year_type.hydrological": Text(
        "hydrological XI–X", "hydrologiczny XI–X"
    ),
    "meteo.common.reference": Text("Reference period", "Okres odniesienia"),
    "meteo.common.normal": Text("Normal {from}–{to}", "Normalna {from}–{to}"),
    "meteo.common.chart": Text("Chart", "Wykres"),
    "meteo.common.threshold": Text("Threshold", "Próg"),
    "meteo.common.days_unit": Text("days", "dni"),
    "meteo.common.mean_value": Text("mean {value}", "średnio {value}"),
    "meteo.common.complete_years.one": Text("{n} complete year", "{n} rok pełny"),
    "meteo.common.complete_years.few": Text("{n} complete years", "{n} lata pełne"),
    "meteo.common.complete_years.many": Text("{n} complete years", "{n} lat pełnych"),
    "meteo.common.complete_years.other": Text("{n} complete years", "{n} roku pełnego"),
    # --- distributions and their fits -------------------------------------------------
    "meteo.dist.all": Text("all four", "wszystkie cztery"),
    "meteo.dist.log_normal": Text("log-normal", "log-normalny"),
    "meteo.fit.l_moments": Text("L-moments", "L-momenty"),
    "meteo.fit.mle": Text("maximum likelihood", "największa wiarygodność"),
    "meteo.fit.moments": Text("moments", "momenty"),
    "meteo.fit.least_squares": Text("least squares", "najmniejsze kwadraty"),
    "meteo.fit.param.shape": Text("shape", "kształt"),
    "meteo.fit.param.loc": Text("location", "położenie"),
    "meteo.fit.param.scale": Text("scale", "skala"),
    "meteo.fit.param.skew": Text("skewness", "skośność"),
    # --- „Opady”: sums and normals --------------------------------------------------------
    "meteo.opady.sums.title": Text(
        "Precipitation totals and the normal", "Sumy opadów i normalna"
    ),
    "meteo.opady.sums.info": Text(
        "Hydrolog, `meteo precipitation` (index sums). A monthly total needs every day "
        "of the month; a total of several days that IMGW-PIB gives after days without a "
        "measurement (flag “accumulated”) stands for the days it covers. The half-years "
        "XI–IV and V–X, the meteorological seasons (XII–II with the December of the "
        "year before) and the year need all their months. The normal is the mean of "
        "the years of the reference period that have a value, when they are at least "
        "80 % of its years (WMO-No. 1203, 2017, 4.4.2); the reference period is by "
        "default the years analysed, the station's whole record, and at least 30 years "
        "are recommended (WMO-No. 1203: the standard normal 1991–2020, the reference "
        "normal 1961–1990 for climate change). A total in % of its normal is the "
        "relative precipitation. The mean, the extremes and the coefficient of "
        "variation are those of the years analysed; the share of a month is that of "
        "its normal in the sum of the twelve normals (from the regime below).",
        "Hydrolog, `meteo precipitation` (index sums). Suma miesięczna wymaga każdego "
        "dnia miesiąca; suma z kilku dni, którą IMGW-PIB podaje po dniach bez pomiaru "
        "(flaga „accumulated”), zastępuje dni, które obejmuje. Półrocza XI–IV i V–X, "
        "pory roku meteorologiczne (XII–II z grudniem roku poprzedniego) i rok "
        "wymagają wszystkich swoich miesięcy. Normalna to średnia lat okresu "
        "odniesienia, które mają wartość, gdy jest ich co najmniej 80 % lat okresu "
        "(WMO-No. 1203, 2017, p. 4.4.2); okres odniesienia to domyślnie lata analizy, "
        "czyli cały zapis stacji, a zalecane jest co najmniej 30 lat (WMO-No. 1203: "
        "normalna standardowa 1991–2020, referencyjna 1961–1990 do badania zmian "
        "klimatu). Suma w % normalnej to opad względny. Średnia, skrajne sumy i "
        "współczynnik zmienności dotyczą lat analizy; udział miesiąca to udział jego "
        "normalnej w sumie dwunastu normalnych (z reżimu niżej).",
    ),
    "meteo.opady.sums.mean": Text("Mean annual total", "Średnia suma roczna"),
    "meteo.opady.sums.normal_years.one": Text(
        "{n} year with an annual total", "{n} rok z sumą roczną"
    ),
    "meteo.opady.sums.normal_years.few": Text(
        "{n} years with an annual total", "{n} lata z sumą roczną"
    ),
    "meteo.opady.sums.normal_years.many": Text(
        "{n} years with an annual total", "{n} lat z sumą roczną"
    ),
    "meteo.opady.sums.normal_years.other": Text(
        "{n} years with an annual total", "{n} roku z sumą roczną"
    ),
    "meteo.opady.sums.year": Text("Year {year}", "Rok {year}"),
    "meteo.opady.sums.pct_of_normal": Text(
        "{pct} % of the normal", "{pct} % normalnej"
    ),
    "meteo.opady.sums.extremes": Text("Driest · wettest", "Najsuchszy · najmokrzejszy"),
    "meteo.opady.sums.cv": Text("Coefficient of variation", "Współczynnik zmienności"),
    "meteo.opady.sums.view_label": Text("Chart of the totals", "Wykres sum"),
    "meteo.opady.sums.view.mm": Text("total [mm]", "suma [mm]"),
    "meteo.opady.sums.view.pct": Text("% of the normal", "% normalnej"),
    "meteo.opady.sums.axis_mm": Text("annual total [mm]", "suma roczna [mm]"),
    "meteo.opady.sums.series_mm": Text("annual total", "suma roczna"),
    "meteo.opady.sums.normal_mark": Text("normal {value} mm", "normalna {value} mm"),
    "meteo.opady.sums.chart_mm": Text(
        "Annual precipitation totals", "Sumy roczne opadu"
    ),
    "meteo.opady.sums.axis_pct": Text(
        "relative precipitation − 100 [%]", "opad względny − 100 [%]"
    ),
    "meteo.opady.sums.series_pct": Text(
        "departure from the normal", "odchylenie od normalnej"
    ),
    "meteo.opady.sums.chart_pct": Text(
        "Annual precipitation in % of the normal", "Opad roczny w % normalnej"
    ),
    "meteo.opady.sums.months": Text("Months [mm]", "Miesiące [mm]"),
    "meteo.opady.sums.mean_col": Text("Mean", "Średnia"),
    "meteo.opady.sums.min_col": Text("Min (year)", "Min. (rok)"),
    "meteo.opady.sums.max_col": Text("Max (year)", "Maks. (rok)"),
    "meteo.opady.sums.share_col": Text("Share %", "Udział %"),
    "meteo.opady.sums.normals": Text(
        "Normals of the half-years and seasons [mm]",
        "Normalne półroczy i pór roku [mm]",
    ),
    "meteo.opady.sums.total_col": Text("Total [mm]", "Suma [mm]"),
    "meteo.opady.sums.pct_col": Text("% of the normal", "% normalnej"),
    "meteo.opady.sums.all_years": Text(
        "Months and seasons of every year", "Miesiące i pory roku wszystkich lat"
    ),
    "meteo.opady.sums.table_label": Text("Table of the years", "Tabela lat"),
    "meteo.opady.sums.table.mm": Text("months [mm]", "miesiące [mm]"),
    "meteo.opady.sums.table.pct": Text(
        "months [% of the normal]", "miesiące [% normalnej]"
    ),
    "meteo.opady.sums.table.seasons": Text("seasons [mm]", "pory roku [mm]"),
    # --- „Opady”: the regime ----------------------------------------------------------------
    "meteo.opady.regime.title": Text(
        "Regime and seasonality of precipitation", "Reżim i sezonowość opadów"
    ),
    "meteo.opady.regime.info": Text(
        "Hydrolog, `meteo precipitation` (index seasonality). The regime is the share "
        "of each monthly normal of the reference period in their sum; the coefficient "
        "is a monthly normal over a twelfth of that sum. Oliver's (1980) precipitation "
        "concentration index PCI = 100·Σp²/(Σp)²: up to 10 uniform, up to 15 "
        "moderately concentrated, up to 20 irregular, above 20 strongly irregular. "
        "Walsh and Lawler's (1981) seasonality index SI = Σ|xₙ − R/12|/R: up to 0.20 "
        "very equable, up to 0.40 equable with a wetter season, up to 0.60 rather "
        "seasonal, up to 0.80 seasonal, up to 1.00 markedly seasonal, up to 1.20 most "
        "precipitation in three months or less, above that extreme. Both are given for "
        "the normals and as the mean of the values of the years analysed.",
        "Hydrolog, `meteo precipitation` (index seasonality). Reżim to udział każdej "
        "normalnej miesięcznej okresu odniesienia w ich sumie; współczynnik to "
        "normalna miesiąca przez 1/12 tej sumy. Wskaźnik koncentracji opadu PCI = "
        "100·Σp²/(Σp)² (Oliver 1980): do 10 równomierny, do 15 umiarkowanie "
        "skoncentrowany, do 20 nieregularny, powyżej 20 silnie nieregularny. Wskaźnik "
        "sezonowości SI = Σ|xₙ − R/12|/R (Walsh i Lawler 1981): do 0,20 bardzo "
        "równomierny, do 0,40 równomierny z porą wilgotniejszą, do 0,60 raczej "
        "sezonowy, do 0,80 sezonowy, do 1,00 wyraźnie sezonowy, do 1,20 większość "
        "opadu w trzech miesiącach lub krócej, powyżej skrajny. Oba są podane dla "
        "normalnych i jako średnia wartości lat analizy.",
    ),
    "meteo.opady.regime.axis_x": Text("month", "miesiąc"),
    "meteo.opady.regime.axis_y": Text(
        "share of the annual total [%]", "udział w sumie rocznej [%]"
    ),
    "meteo.opady.regime.series": Text("share", "udział"),
    "meteo.opady.regime.chart": Text("Precipitation regime", "Reżim opadów"),
    "meteo.opady.regime.pci": Text("PCI of the normals", "PCI normalnych"),
    "meteo.opady.regime.pci_years": Text("PCI of the years, mean", "PCI lat, średnio"),
    "meteo.opady.regime.si": Text("SI of the normals", "SI normalnych"),
    "meteo.opady.regime.si_years": Text("SI of the years, mean", "SI lat, średnio"),
    "meteo.opady.regime.coefficient": Text("coefficient", "współczynnik"),
    "meteo.opady.regime.no_normal": Text(
        "A monthly normal of {from}–{to} has values in fewer than 80 % of the years: "
        "choose another reference period.",
        "Normalna któregoś miesiąca lat {from}–{to} ma wartości w mniej niż 80 % lat: "
        "wybierz inny okres odniesienia.",
    ),
    "meteo.opady.regime.years": Text(
        "PCI and SI of each year", "PCI i SI każdego roku"
    ),
    "meteo.opady.regime.class_col": Text("class", "klasa"),
    "meteo.opady.pci.uniform": Text("uniform", "równomierny"),
    "meteo.opady.pci.moderate": Text(
        "moderately concentrated", "umiarkowanie skoncentrowany"
    ),
    "meteo.opady.pci.irregular": Text("irregular", "nieregularny"),
    "meteo.opady.pci.strongly_irregular": Text(
        "strongly irregular", "silnie nieregularny"
    ),
    "meteo.opady.si.very_equable": Text("very equable", "bardzo równomierny"),
    "meteo.opady.si.equable_wetter_season": Text(
        "equable with a wetter season", "równomierny z porą wilgotniejszą"
    ),
    "meteo.opady.si.rather_seasonal": Text(
        "rather seasonal with a short drier season",
        "raczej sezonowy z krótką porą suchszą",
    ),
    "meteo.opady.si.seasonal": Text("seasonal", "sezonowy"),
    "meteo.opady.si.markedly_seasonal": Text(
        "markedly seasonal with a long drier season",
        "wyraźnie sezonowy z długą porą suchszą",
    ),
    "meteo.opady.si.most_in_three_months": Text(
        "most precipitation in three months or less",
        "większość opadu w trzech miesiącach lub krócej",
    ),
    "meteo.opady.si.extreme": Text(
        "extreme, almost all in one or two months",
        "skrajny, prawie cały opad w jednym lub dwóch miesiącach",
    ),
    # --- „Opady”: days with precipitation and the intensity -------------------------------
    "meteo.opady.days.title": Text(
        "Days with precipitation and its intensity", "Dni z opadem i natężenie"
    ),
    "meteo.opady.days.info": Text(
        "Hydrolog, `meteo precipitation` (indices days and intensity). Days with daily "
        "precipitation of at least 0.1, 1, 10 and 20 mm (R10mm and R20mm of the "
        "ETCCDI). A month counts when fewer than 11 days, and fewer than 5 in a row, "
        "are missing; its count is then scaled to all the days of the month "
        "(WMO-No. 1203, 2017, 4.4.1); a year needs its twelve months. A total of "
        "several days after days without a measurement is a missing day here. The "
        "intensity of a wet day (SDII of the ETCCDI; Zhang et al., 2011) is the "
        "precipitation of the wet days (at least 1 mm, or 0.1 mm if chosen) over their "
        "number, in the years whose every day has a value; that of a month pools its "
        "complete months.",
        "Hydrolog, `meteo precipitation` (index days i intensity). Dni z opadem "
        "dobowym co najmniej 0,1, 1, 10 i 20 mm (R10mm i R20mm ETCCDI). Miesiąc liczy "
        "się, gdy brakuje mniej niż 11 dni i mniej niż 5 kolejnych; jego liczba dni "
        "jest wtedy przeliczona na wszystkie dni miesiąca (WMO-No. 1203, 2017, "
        "p. 4.4.1); rok wymaga dwunastu miesięcy. Suma z kilku dni po dniach bez "
        "pomiaru jest tu dniem bez wartości. Natężenie opadu dnia mokrego (SDII wg "
        "ETCCDI; Zhang i in. 2011) to opad dni mokrych (co najmniej 1 mm albo, do "
        "wyboru, 0,1 mm) przez ich liczbę, w latach z pomiarem w każdym dniu; "
        "natężenie miesiąca łączy jego pełne miesiące.",
    ),
    "meteo.opady.days.figure": Text("Days ≥ {threshold} mm", "Dni ≥ {threshold} mm"),
    "meteo.opady.days.per_year": Text("mean in a year", "średnio w roku"),
    "meteo.opady.days.sdii": Text(
        "Intensity of a wet day (≥ {threshold} mm)",
        "Natężenie dnia mokrego (≥ {threshold} mm)",
    ),
    "meteo.opady.days.wet_day": Text("Wet day", "Dzień mokry"),
    "meteo.opady.days.threshold_label": Text(
        "Threshold of daily precipitation", "Próg opadu dobowego"
    ),
    "meteo.opady.days.axis": Text(
        "days with precipitation ≥ {threshold} mm", "dni z opadem ≥ {threshold} mm"
    ),
    "meteo.opady.days.series": Text("days ≥ {threshold} mm", "dni ≥ {threshold} mm"),
    "meteo.opady.days.chart": Text(
        "Days with precipitation in the years", "Dni z opadem w latach"
    ),
    "meteo.opady.days.months": Text("Mean in a month", "Średnio w miesiącu"),
    # --- „Opady”: heavy precipitation -----------------------------------------------------
    "meteo.opady.heavy.title": Text(
        "Heavy precipitation (R95p, R99p)", "Opady duże (R95p, R99p)"
    ),
    "meteo.opady.heavy.info": Text(
        "Hydrolog, `meteo precipitation` (index heavy). The thresholds are the 95th and "
        "99th percentiles of the precipitation of the wet days (at least 1 mm) of the "
        "reference period, quantile type 8 (Hyndman and Fan 1996, as climdex.pcic of "
        "the ETCCDI), from at least 100 wet days. R95p is the precipitation of a "
        "year's days above the 95th percentile, R95pTOT = 100·R95p / the precipitation "
        "of the year's wet days (R99p likewise; Zhang et al., 2011). A year needs every "
        "day. The ETCCDI takes the percentiles of the base period 1961–1990 (Klein "
        "Tank et al., 2009); a period longer than 30 years gives steadier percentiles "
        "(WMO-No. 1203, 2017, 5.2.2).",
        "Hydrolog, `meteo precipitation` (index heavy). Progi to 95. i 99. percentyl "
        "opadu dni mokrych (co najmniej 1 mm) okresu odniesienia, kwantyl typu 8 "
        "(Hyndman i Fan 1996, jak climdex.pcic ETCCDI), liczony z co najmniej 100 dni "
        "mokrych. R95p to opad dni roku powyżej 95. percentyla, R95pTOT = 100·R95p / "
        "opad dni mokrych roku (R99p podobnie; Zhang i in. 2011). Rok wymaga każdego "
        "dnia. ETCCDI bierze percentyle okresu bazowego 1961–1990 (Klein Tank i in. "
        "2009); okres dłuższy niż 30 lat daje stabilniejsze percentyle (WMO-No. 1203, "
        "2017, p. 5.2.2).",
    ),
    "meteo.opady.heavy.threshold": Text("Threshold P{p}", "Próg P{p}"),
    "meteo.opady.heavy.threshold_note": Text(
        "{from}–{to}, days ≥ {wet} mm: {n}", "{from}–{to}, dni ≥ {wet} mm: {n}"
    ),
    "meteo.opady.heavy.share_mean": Text("{index}, mean", "{index} średnio"),
    "meteo.opady.heavy.axis": Text(
        "share in the total of the days ≥ {wet} mm [%]",
        "udział w sumie dni ≥ {wet} mm [%]",
    ),
    "meteo.opady.heavy.chart": Text(
        "Share of heavy precipitation", "Udział opadów dużych"
    ),
    "meteo.opady.heavy.total_col": Text(
        "Total of the days ≥ {wet} mm", "Suma dni ≥ {wet} mm"
    ),
    "meteo.opady.heavy.sum_col": Text("{index} [mm] (days)", "{index} [mm] (dni)"),
    # --- „Opady”: maxima of 1 to 10 days --------------------------------------------------
    "meteo.opady.maxima.title": Text(
        "Maximum precipitation of 1–10 days", "Opady maksymalne 1–10 dni"
    ),
    "meteo.opady.maxima.info": Text(
        "Hydrolog, `meteo precipitation` (index maxima). The n-day sum of a day is the "
        "precipitation of the n days that end on it (n = 1, 2, 3, 5, 10; Rx1day and "
        "Rx5day of the ETCCDI for 1 and 5 days); it belongs to the year of its last day "
        "and needs all n days. An annual maximum needs every day of the year, so a "
        "year with a missing day is left out. The monthly maximum of daily "
        "precipitation takes whatever days the month has; the mean of the monthly "
        "maxima takes the months with enough days (WMO-No. 1203, 2017, 4.4.2), and "
        "“Annual maxima” counts the complete years whose largest daily sum fell in the "
        "month.",
        "Hydrolog, `meteo precipitation` (index maxima). Suma n-dniowa dnia to opad n "
        "dni kończących się tym dniem (n = 1, 2, 3, 5, 10; Rx1day i Rx5day ETCCDI dla 1 "
        "i 5 dni); należy do roku swojego ostatniego dnia i wymaga wszystkich n dni. "
        "Maksimum roczne wymaga każdego dnia roku, więc rok z brakiem dnia jest "
        "pomijany. Maksimum miesięczne opadu dobowego bierze dni, które miesiąc ma; "
        "średnia maksimów miesięcznych — miesiące z dostateczną liczbą dni (WMO-No. "
        "1203, 2017, p. 4.4.2), a „Maks. roczne” liczy lata pełne, w których "
        "największa suma dobowa przypadła na ten miesiąc.",
    ),
    "meteo.opady.days_n.one": Text("{n} day", "{n} doba"),
    "meteo.opady.days_n.few": Text("{n} days", "{n} doby"),
    "meteo.opady.days_n.many": Text("{n} days", "{n} dób"),
    "meteo.opady.days_n.other": Text("{n} days", "{n} doby"),
    "meteo.opady.maxima.duration": Text("Duration", "Czas trwania"),
    "meteo.opady.maxima.duration_label": Text(
        "Number of days of the sums", "Liczba dni sumy"
    ),
    "meteo.opady.maxima.mean": Text("Mean maximum", "Średnie maksimum"),
    "meteo.opady.maxima.median": Text("median {value}", "mediana {value}"),
    "meteo.opady.maxima.largest": Text("Largest", "Największe"),
    "meteo.opady.maxima.smallest": Text("Smallest", "Najmniejsze"),
    "meteo.opady.maxima.complete": Text("Complete years", "Lata pełne"),
    "meteo.opady.maxima.left_out": Text(
        "incomplete left out: {n}", "pominięte niepełne: {n}"
    ),
    "meteo.opady.maxima.axis": Text(
        "maximum, {duration} [mm]", "maksimum, {duration} [mm]"
    ),
    "meteo.opady.maxima.series": Text("annual maximum", "maksimum roczne"),
    "meteo.opady.maxima.chart": Text(
        "Annual maxima, {duration}", "Maksima roczne, {duration}"
    ),
    "meteo.opady.maxima.table": Text("Annual maxima [mm]", "Maksima roczne [mm]"),
    "meteo.opady.maxima.dates_col": Text("Dates ({duration})", "Termin ({duration})"),
    "meteo.opady.maxima.incomplete": Text(
        "Years left out (a day without a value): {years}.",
        "Lata pominięte (dzień bez pomiaru): {years}.",
    ),
    "meteo.opady.maxima.months": Text(
        "Monthly maxima of daily precipitation", "Maksima miesięczne opadu dobowego"
    ),
    "meteo.opady.maxima.highest_col": Text(
        "Highest [mm] (date)", "Najwyższy [mm] (data)"
    ),
    "meteo.opady.maxima.mean_col": Text(
        "Mean of the maxima [mm]", "Średnie maks. [mm]"
    ),
    "meteo.opady.maxima.annual_col": Text("Annual maxima", "Maks. roczne"),
    "meteo.opady.maxima.top": Text(
        "The ten largest annual maxima ({duration})",
        "Dziesięć największych maksimów rocznych ({duration})",
    ),
    "meteo.opady.maxima.value_col": Text("Precipitation [mm]", "Opad [mm]"),
    "meteo.opady.maxima.date_col": Text("Dates", "Termin"),
    # --- „Opady”: quantiles and PMAXTP ----------------------------------------------------
    "meteo.opady.quantiles.title": Text(
        "Maximum precipitation of probability p",
        "Opad maksymalny o prawdopodobieństwie p",
    ),
    "meteo.opady.quantiles.info": Text(
        "Hydrolog, `stats flood-frequency` on the annual maxima of n days of the "
        "complete years (from `meteo precipitation`, index maxima, the same years): "
        "log-normal, GEV, Pearson III and Weibull distributions fitted by L-moments by "
        "default (Hosking and Wallis 1997), with the goodness of fit KS, A² and AIC; "
        "the distribution with the smallest AIC comes first. The points of the annual "
        "maxima are at the exceedance probability m/(n+1). Beside them IMGW-PIB's "
        "PMAXTP for the station's point (precipitation lasting 24, 48 or 72 h, methods "
        "POT and AMP; asked of IMGW-PIB, not computed here). A daily total of a station "
        "(the day of 06–06 UTC) is smaller than the largest 24-hour total of a moving "
        "window, by about 1.13 times on average (Weiss 1964); it is not converted.",
        "Hydrolog, `stats flood-frequency` na maksimach rocznych z n dni lat pełnych "
        "(z `meteo precipitation`, index maxima, te same lata): rozkłady log-normalny, "
        "GEV, Pearsona III i Weibulla, domyślnie metodą L-momentów (Hosking i Wallis "
        "1997), z miarami zgodności KS, A² i AIC; rozkład o najmniejszym AIC jest "
        "pierwszy. Punkty maksimów rocznych mają prawdopodobieństwo przewyższenia "
        "m/(n+1). Obok PMAXTP IMGW-PIB dla punktu stacji (opad o czasie trwania 24, 48 "
        "lub 72 h, metody POT i AMP; dane pobrane z IMGW-PIB, nie liczone tutaj). Suma "
        "dobowa ze stacji (doba 06–06 UTC) jest mniejsza od największej sumy "
        "24-godzinnej w przesuwanym oknie, średnio około 1,13 raza (Weiss 1964); nie "
        "jest przeliczana.",
    ),
    "meteo.opady.quantiles.distribution": Text("Distribution", "Rozkład"),
    "meteo.opady.quantiles.method": Text("Method", "Metoda"),
    "meteo.opady.quantiles.method_label": Text(
        "Method of estimation", "Metoda estymacji"
    ),
    "meteo.opady.quantiles.years": Text("Years (maxima)", "Lata (maksimów)"),
    "meteo.opady.quantiles.best": Text("Best (AIC)", "Najlepszy (AIC)"),
    "meteo.opady.quantiles.best_mark": Text("(best by AIC)", "(najlepszy wg AIC)"),
    "meteo.opady.quantiles.p1": Text(
        "p = 1 % (T = 100 years)", "p = 1 % (T = 100 lat)"
    ),
    "meteo.opady.quantiles.pmaxtp_note": Text(
        "{hours} h, the station's point", "{hours} h, punkt stacji"
    ),
    "meteo.opady.quantiles.axis_x": Text(
        "exceedance probability", "prawdopodobieństwo przewyższenia"
    ),
    "meteo.opady.quantiles.axis_y": Text(
        "maximum precipitation, {duration} [mm]", "opad maksymalny, {duration} [mm]"
    ),
    "meteo.opady.quantiles.empirical": Text(
        "annual maxima (m/(n+1))", "maksima roczne (m/(n+1))"
    ),
    "meteo.opady.quantiles.chart": Text(
        "Distributions of the annual maxima of precipitation on Gumbel paper",
        "Rozkłady maksimów rocznych opadu na siatce Gumbela",
    ),
    "meteo.opady.quantiles.table": Text(
        "Maximum precipitation P_p [mm]", "Opad maksymalny P_p [mm]"
    ),
    "meteo.opady.quantiles.t_col": Text("T [years]", "T [lata]"),
    "meteo.opady.quantiles.pmaxtp_caption": Text(
        "POT and AMP: IMGW-PIB's PMAXTP (precipitation lasting {hours} h) at the point "
        "{point}, asked of IMGW-PIB, not computed here. PMAXTP's data have their own "
        "terms:",
        "POT i AMP: PMAXTP IMGW-PIB (opad o czasie trwania {hours} h) dla punktu "
        "{point}, pobrane z IMGW-PIB, nie liczone tutaj. Dane PMAXTP mają własne "
        "warunki korzystania:",
    ),
    "meteo.opady.quantiles.pmaxtp_link": Text(
        "All PMAXTP tables of this point", "Wszystkie tabele PMAXTP tego punktu"
    ),
    "meteo.opady.quantiles.all": Text(
        "All distributions and the goodness of fit",
        "Wszystkie rozkłady i miary zgodności",
    ),
    "meteo.opady.quantiles.params_col": Text("parameters", "parametry"),
    "meteo.opady.quantiles.ks_note": Text(
        "* The p-value of KS is approximate: the parameters were estimated from the "
        "same sample (Hydrolog ranks by AIC).",
        "* Wartość p testu KS jest orientacyjna: parametry oszacowano z tej samej "
        "próby (Hydrolog porządkuje według AIC).",
    ),
    "meteo.opady.quantiles.cli": Text(
        "The same computation in a terminal", "To samo obliczenie w terminalu"
    ),
    "meteo.opady.pmaxtp.poland_only": Text(
        "PMAXTP covers Poland only (IMGW-PIB's stations).",
        "PMAXTP obejmuje tylko Polskę (stacje IMGW-PIB).",
    ),
    "meteo.opady.pmaxtp.no_point": Text(
        "PMAXTP needs the station's coordinates, which the catalog does not give.",
        "PMAXTP wymaga współrzędnych stacji, których katalog nie podaje.",
    ),
    "meteo.opady.pmaxtp.up_to_3_days": Text(
        "PMAXTP gives precipitation lasting up to 72 hours (3 days).",
        "PMAXTP podaje opady o czasie trwania do 72 godzin (3 dób).",
    ),
    "meteo.opady.pmaxtp.no_duration": Text(
        "PMAXTP's answer for this point has no precipitation lasting {hours} h.",
        "Odpowiedź PMAXTP dla tego punktu nie ma opadu o czasie trwania {hours} h.",
    ),
    "meteo.opady.pmaxtp.loading": Text(
        "PMAXTP: asking IMGW-PIB…", "PMAXTP: pytam IMGW-PIB…"
    ),
    "meteo.opady.pmaxtp.failed": Text(
        "PMAXTP is not available: {error}", "PMAXTP jest niedostępne: {error}"
    ),
    # --- „Susze i okresy bezopadowe”: spells ---------------------------------------------
    "meteo.susze.spells.title": Text(
        "Dry and wet spells", "Okresy bezopadowe i opadowe"
    ),
    "meteo.susze.spells.info": Text(
        "Hydrolog, `meteo spells`. A dry spell is a run of consecutive days with "
        "precipitation below the threshold, a wet spell a run of days with at least it "
        "(1 mm: CDD and CWD of the ETCCDI; Zhang et al., 2011), found by the run logic "
        "of `stats threshold-events` (Tallaksen and van Lanen 2004). A day without a "
        "value ends a spell, which is then open (marked ≥: it may have been longer). A "
        "spell counts in the year in which it starts; the figures of the years take "
        "the years whose every day has a value, the distribution of the durations the "
        "spells of those years that are not open. The list of spells holds those of at "
        "least the duration named; the summaries take every spell.",
        "Hydrolog, `meteo spells`. Okres bezopadowy to ciąg kolejnych dni z opadem "
        "mniejszym od progu, okres opadowy — ciąg dni z opadem co najmniej równym "
        "progowi (1 mm: CDD i CWD wg ETCCDI; Zhang i in. 2011), wyznaczony logiką serii "
        "`stats threshold-events` (Tallaksen i van Lanen 2004). Dzień bez pomiaru "
        "przerywa ciąg, który jest wtedy otwarty (oznaczony ≥: mógł być dłuższy). Ciąg "
        "należy do roku, w którym się zaczął; wartości lat biorą lata z pomiarem w "
        "każdym dniu, rozkład długości — ciągi tych lat, które nie są otwarte. Lista "
        "ciągów obejmuje ciągi nie krótsze od podanej długości; podsumowania biorą "
        "wszystkie ciągi.",
    ),
    "meteo.susze.spells.kind_label": Text("Spells", "Ciągi"),
    "meteo.susze.spells.kind.dry": Text("dry", "bezopadowe"),
    "meteo.susze.spells.kind.wet": Text("wet", "opadowe"),
    "meteo.susze.spells.threshold_label": Text(
        "Threshold of the spells", "Próg ciągów"
    ),
    "meteo.susze.spells.threshold_input": Text(
        "Threshold of the spells [mm]", "Próg ciągów [mm]"
    ),
    "meteo.susze.spells.mean_longest": Text(
        "Longest in a year, mean", "Najdłuższy w roku, średnio"
    ),
    "meteo.susze.spells.record": Text("Longest on record", "Najdłuższy w zapisie"),
    "meteo.susze.spells.counts": Text(
        "Spells ≥ 10 · 15 · 20 days a year", "Ciągów ≥ 10 · 15 · 20 dni na rok"
    ),
    "meteo.susze.spells.counts_note": Text(
        "mean of the complete years", "średnio w latach pełnych"
    ),
    "meteo.susze.spells.number": Text(
        "Spells in a year, mean", "Ciągów w roku, średnio"
    ),
    "meteo.susze.spells.number_note": Text("{n} in the period", "{n} w okresie"),
    "meteo.susze.spells.ongoing": Text(
        "Lasting at the end of the record", "Trwa na końcu zapisu"
    ),
    "meteo.susze.spells.since": Text(
        "from {start} (as of {end})", "od {start} (stan na {end})"
    ),
    "meteo.susze.spells.none": Text("no", "nie"),
    "meteo.susze.spells.none_long": Text("none of ≥ {n} days", "brak ciągu ≥ {n} dni"),
    "meteo.susze.spells.axis": Text("longest spell [days]", "najdłuższy ciąg [dni]"),
    "meteo.susze.spells.series": Text("longest spell", "najdłuższy ciąg"),
    "meteo.susze.spells.chart": Text(
        "The longest spell of each year", "Najdłuższy ciąg w roku"
    ),
    "meteo.susze.spells.classes_axis": Text(
        "duration of a spell [days]", "długość ciągu [dni]"
    ),
    "meteo.susze.spells.per_year": Text("spells a year", "ciągów na rok"),
    "meteo.susze.spells.classes_chart": Text(
        "Distribution of the durations of the spells", "Rozkład długości ciągów"
    ),
    "meteo.susze.spells.longest": Text("The longest spells", "Najdłuższe ciągi"),
    "meteo.susze.spells.longest_listed": Text(
        "The longest spells (of those of at least {n} days)",
        "Najdłuższe ciągi (spośród ciągów co najmniej {n}-dniowych)",
    ),
    "meteo.susze.spells.no_long": Text(
        "No spell of at least {n} days.", "Brak ciągów co najmniej {n}-dniowych."
    ),
    "meteo.susze.spells.days_col": Text("Days", "Dni"),
    "meteo.susze.spells.dates_col": Text("Dates", "Okres"),
    "meteo.susze.spells.longest_col": Text("Longest", "Najdłuższy"),
    "meteo.susze.spells.count_col": Text("Spells", "Ciągów"),
    # --- „Susze i okresy bezopadowe”: the SPI ---------------------------------------------
    "meteo.susze.spi.title": Text(
        "Standardized precipitation index SPI", "Wskaźnik standaryzowanego opadu SPI"
    ),
    "meteo.susze.spi.info": Text(
        "Hydrolog, `meteo spi`. The SPI of a month for k months (1, 3, 6, 12) is the "
        "standard normal quantile of the sum of the k months ending in it under the "
        "distribution of such sums of the same calendar month in the reference period: "
        "a gamma distribution fitted to the positive sums by Thom's (1958) "
        "approximation of maximum likelihood, with the probability of a zero sum q: "
        "H(x) = q + (1 − q)·G(x) (McKee et al., 1993; Edwards and McKee, 1997; "
        "WMO-No. 1090, 2012). A month is fitted when its sums are known in at least "
        "80 % of the years and three or more are positive; the SPI is held within "
        "±3.09. At least 30 years are recommended (WMO-No. 1090: 20–30 years at least, "
        "50–60 preferred). The colours are McKee's classes: −2 and below extremely "
        "dry, to −1.5 severely dry, to −1 moderately dry, below 1 near normal, then "
        "wet likewise.",
        "Hydrolog, `meteo spi`. SPI miesiąca dla k miesięcy (1, 3, 6, 12) to kwantyl "
        "standardowego rozkładu normalnego sumy k miesięcy kończących się w nim, przy "
        "rozkładzie takich sum tego samego miesiąca kalendarzowego w okresie "
        "odniesienia: rozkład gamma dopasowany do sum dodatnich metodą największej "
        "wiarygodności w przybliżeniu Thoma (1958), z prawdopodobieństwem sumy zerowej "
        "q: H(x) = q + (1 − q)·G(x) (McKee i in. 1993; Edwards i McKee 1997; WMO-No. "
        "1090, 2012). Miesiąc jest dopasowany, gdy jego sumy są znane w co najmniej "
        "80 % lat i co najmniej trzy są dodatnie; SPI jest ograniczony do ±3,09. "
        "Zalecane jest co najmniej 30 lat (WMO-No. 1090: co najmniej 20–30 lat, "
        "najlepiej 50–60). Kolory to klasy McKee: −2 i mniej ekstremalnie suchy, do "
        "−1,5 bardzo suchy, do −1 umiarkowanie suchy, poniżej 1 normalny, dalej "
        "symetrycznie wilgotne.",
    ),
    "meteo.susze.spi.scale": Text("Scale", "Skala"),
    "meteo.susze.spi.scale_label": Text("Scale of the SPI", "Skala SPI"),
    "meteo.susze.spi.calibration": Text("Calibration", "Kalibracja"),
    "meteo.susze.spi.gamma": Text("gamma distribution, Thom", "rozkład gamma, Thom"),
    "meteo.susze.spi.last": Text("Last value of {name}", "Ostatnia wartość {name}"),
    "meteo.susze.spi.fits": Text(
        "Parameters of the gamma distribution ({name})",
        "Parametry rozkładu gamma ({name})",
    ),
    "meteo.susze.spi_class.extremely_dry": Text("extremely dry", "ekstremalnie suchy"),
    "meteo.susze.spi_class.severely_dry": Text("severely dry", "bardzo suchy"),
    "meteo.susze.spi_class.moderately_dry": Text(
        "moderately dry", "umiarkowanie suchy"
    ),
    "meteo.susze.spi_class.near_normal": Text("near normal", "normalny"),
    "meteo.susze.spi_class.moderately_wet": Text(
        "moderately wet", "umiarkowanie wilgotny"
    ),
    "meteo.susze.spi_class.very_wet": Text("very wet", "bardzo wilgotny"),
    "meteo.susze.spi_class.extremely_wet": Text(
        "extremely wet", "ekstremalnie wilgotny"
    ),
    # --- „Susze i okresy bezopadowe”: relative precipitation ----------------------------
    "meteo.susze.relative.title": Text(
        "Relative precipitation and its classes", "Opad względny i jego klasy"
    ),
    "meteo.susze.relative.info": Text(
        "Hydrolog, `meteo spi`. The relative precipitation is a total in % of its "
        "normal, the mean of the reference period. A year is classed by Kaczorowska "
        "(1962): below 50 % extremely dry, 50–74 very dry, 75–89 dry, 90–110 normal, "
        "111–125 wet, 126–150 very wet, above 150 extremely wet (the percentage "
        "rounded to a whole number). Kaczorowska gave no classes of months; a month is "
        "classed by the limits of Polish practice: below 25 % extremely dry, from 25 "
        "very dry, from 50 dry, 75–125 normal, above 125 wet, above 150 very wet, "
        "above 200 extremely wet (Tomaszewska 1994, after Kosiba 1948, as given by "
        "Gąsiorek and Musiał 2011).",
        "Hydrolog, `meteo spi`. Opad względny to suma w % jej normalnej, średniej "
        "okresu odniesienia. Rok jest klasyfikowany według Kaczorowskiej (1962): "
        "poniżej 50 % skrajnie suchy, 50–74 bardzo suchy, 75–89 suchy, 90–110 "
        "normalny, 111–125 wilgotny, 126–150 bardzo wilgotny, powyżej 150 skrajnie "
        "wilgotny (procent zaokrąglony do całości). Kaczorowska nie podała klas "
        "miesięcy; miesiąc jest klasyfikowany według progów polskiej praktyki: poniżej "
        "25 % skrajnie suchy, od 25 bardzo suchy, od 50 suchy, 75–125 normalny, "
        "powyżej 125 wilgotny, powyżej 150 bardzo wilgotny, powyżej 200 skrajnie "
        "wilgotny (Tomaszewska 1994, za Kosibą 1948, według Gąsiorka i Musiał 2011).",
    ),
    "meteo.susze.relative.table": Text(
        "Relative precipitation of the months and years [% of the normal]",
        "Opad względny miesięcy i lat [% normalnej]",
    ),
    "meteo.susze.relative.class.extremely_dry": Text("extremely dry", "skrajnie suchy"),
    "meteo.susze.relative.class.very_dry": Text("very dry", "bardzo suchy"),
    "meteo.susze.relative.class.dry": Text("dry", "suchy"),
    "meteo.susze.relative.class.normal": Text("normal", "normalny"),
    "meteo.susze.relative.class.wet": Text("wet", "wilgotny"),
    "meteo.susze.relative.class.very_wet": Text("very wet", "bardzo wilgotny"),
    "meteo.susze.relative.class.extremely_wet": Text(
        "extremely wet", "skrajnie wilgotny"
    ),
    # --- Hydrolog's notices of these commands -------------------------------------------
    "sections.notice.accumulated_totals": Text(
        "{count} values of {column} are totals of several days after days without a "
        "measurement: they stand for those days in the monthly sums and are missing "
        "days in the daily statistics.",
        "{count} wartości {column} to sumy z kilku dni po dniach bez pomiaru: w sumach "
        "miesięcznych zastępują te dni, w statystykach dobowych są brakami.",
    ),
    "sections.notice.normal_not_computed": Text(
        "The normal of {first_year}–{last_year} needs annual values in {required} of "
        "its years and {years} have one (WMO-No. 1203): the normal and the percentages "
        "of it are empty.",
        "Normalna lat {first_year}–{last_year} wymaga wartości rocznych w {required} "
        "latach okresu, a ma je {years} (WMO-No. 1203): normalna i procenty normalnej "
        "są puste.",
    ),
    "sections.notice.spi_not_fitted": Text(
        "SPI-{scale_months}: the sums of the months {months} have no gamma fit (known "
        "in fewer than 80 % of the years or fewer than 3 positive), so their SPI is "
        "empty.",
        "SPI-{scale_months}: sumy miesięcy {months} nie mają dopasowania gamma (znane w "
        "mniej niż 80 % lat albo mniej niż 3 dodatnie), więc ich SPI jest puste.",
    ),
    "sections.notice.ks_test_approximate": Text(
        "The p-values of the Kolmogorov–Smirnov test are approximate: the parameters "
        "were estimated from the same sample. Choose the distribution by A² or AIC.",
        "Wartości p testu Kołmogorowa–Smirnowa są orientacyjne: parametry oszacowano "
        "z tej samej próby. Rozkład wybieraj według A² albo AIC.",
    ),
    "sections.notice.outside_support": Text(
        "The {distribution} distribution fitted by {fit_method} gives no density to the "
        "annual maxima {values}: its AIC is empty and it ranks last.",
        "Rozkład {distribution} dopasowany metodą {fit_method} nie daje gęstości "
        "maksimom rocznym {values}: jego AIC jest puste i rozkład jest ostatni.",
    ),
    "sections.notice.small_sample": Text(
        "The sample has {years} years, fewer than {minimum}: the frequency estimates "
        "may be unreliable.",
        "Liczba lat próby: {years}, mniej niż {minimum}: oszacowania częstości mogą być "
        "niepewne.",
    ),
    "sections.notice.short_record": Text(
        "KZGW (2017) requires at least {minimum} years of data for a frequency "
        "analysis; the sample has {years}.",
        "KZGW (2017) wymaga co najmniej {minimum} lat danych do analizy częstości; "
        "próba ma {years}.",
    ),
    "sections.notice.distribution_left_out": Text(
        "The {fit_method} method gives no parameters of the {distribution} "
        "distribution, which is left out.",
        "Metoda {fit_method} nie daje parametrów rozkładu {distribution}; rozkład "
        "pominięto.",
    ),
}
