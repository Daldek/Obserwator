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
        "Precipitation totals of a month, a half-year (XI–IV, V–X), a season and a "
        "year, from the station's daily totals. The normal is the mean of such totals "
        "over the years of the reference period, by default the station's whole "
        "record; at least 30 years are recommended.\n\n"
        "Pr = 100 · P / N\n"
        "Cv = σ / P̄\n"
        "where: Pr – relative precipitation [%], P – precipitation total [mm], N – its "
        "normal [mm], P̄, σ – mean and standard deviation of the annual totals of the "
        "years analysed [mm], Cv – coefficient of variation [–]\n\n"
        "A relative precipitation of 100 % is a total equal to the normal; less means "
        "a drier period, more a wetter one than usual. The larger Cv, the more the "
        "annual totals differ from year to year.\n\n"
        "Sources: WMO-No. 1203, 2017",
        "Suma opadów miesiąca, półrocza (XI–IV, V–X), pory roku i roku, liczona z "
        "dobowych sum stacji. Normalna to średnia takich sum z lat okresu odniesienia, "
        "domyślnie całego zapisu stacji; zalecane jest co najmniej 30 lat.\n\n"
        "Pw = 100 · P / N\n"
        "Cv = σ / P̄\n"
        "gdzie: Pw – opad względny [%], P – suma opadów [mm], N – jej normalna [mm], "
        "P̄, σ – średnia i odchylenie standardowe sum rocznych lat analizy [mm], Cv – "
        "współczynnik zmienności [–]\n\n"
        "Opad względny 100 % to suma równa normalnej; mniejszy oznacza okres suchszy, "
        "a większy wilgotniejszy od przeciętnego. Im większy Cv, tym bardziej sumy "
        "roczne różnią się między latami.\n\n"
        "Źródła: WMO-No. 1203, 2017",
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
        "The regime is the share of each month's normal in the sum of the twelve "
        "normals. The indices PCI and SI tell how unevenly precipitation spreads over "
        "the months of the year.\n\n"
        "PCI = 100 · Σpₙ² / (Σpₙ)²\n"
        "SI = Σ|pₙ − R/12| / R\n"
        "kₙ = 12 · pₙ / R\n"
        "where: pₙ – normal of the month n = 1–12 (for a year, its monthly total) "
        "[mm], R – annual total, Σpₙ [mm], kₙ – coefficient of the month [–]\n\n"
        "A bar above the line 1/12 (kₙ > 1) is a month wetter than the average month. "
        "PCI up to 10 and SI up to 0.20 mean an even spread, PCI above 20 a strongly "
        "irregular one, SI above 1.20 almost all precipitation in one or two "
        "months.\n\n"
        "Sources: Oliver 1980 (PCI); Walsh and Lawler 1981 (SI)",
        "Reżim to udział normalnej każdego miesiąca w sumie dwunastu normalnych. "
        "Wskaźniki PCI i SI mówią, jak nierównomiernie opad rozkłada się na miesiące "
        "roku.\n\n"
        "PCI = 100 · Σpₙ² / (Σpₙ)²\n"
        "SI = Σ|pₙ − R/12| / R\n"
        "kₙ = 12 · pₙ / R\n"
        "gdzie: pₙ – normalna miesiąca n = 1–12 (dla roku jego suma miesięczna) [mm], "
        "R – suma roczna, Σpₙ [mm], kₙ – współczynnik miesiąca [–]\n\n"
        "Słupek ponad linią 1/12 (kₙ > 1) to miesiąc wilgotniejszy od przeciętnego. "
        "PCI do 10 i SI do 0,20 oznaczają opad równomierny, PCI powyżej 20 silnie "
        "nieregularny, a SI powyżej 1,20 prawie cały w jednym lub dwóch "
        "miesiącach.\n\n"
        "Źródła: Oliver 1980 (PCI); Walsh i Lawler 1981 (SI)",
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
        "The number of days with daily precipitation of at least 0.1, 1, 10 and 20 mm, "
        "on average in a year and in a month (the counts of days of at least 10 and 20 "
        "mm are the indices R10mm and R20mm). The intensity of a wet day, SDII, is the "
        "mean precipitation of a day with at least 1 mm or, if chosen, 0.1 mm.\n\n"
        "SDII = ΣP / W\n"
        "where: SDII – intensity of a wet day [mm/d], P – precipitation of a wet day "
        "[mm], W – number of wet days [–]\n\n"
        "The larger SDII, the more precipitation an average wet day brings. The count "
        "of a month with a few missing days is scaled to all its days.\n\n"
        "Sources: ETCCDI (Zhang et al. 2011); WMO-No. 1203, 2017",
        "Liczba dni z opadem dobowym co najmniej 0,1, 1, 10 i 20 mm, średnio w roku i "
        "w miesiącu (liczby dni z co najmniej 10 i 20 mm to wskaźniki R10mm i R20mm). "
        "Natężenie dnia mokrego SDII to średni opad dnia z opadem co najmniej 1 mm "
        "albo, do wyboru, 0,1 mm.\n\n"
        "SDII = ΣP / W\n"
        "gdzie: SDII – natężenie dnia mokrego [mm/d], P – opad dnia mokrego [mm], W – "
        "liczba dni mokrych [–]\n\n"
        "Im większe SDII, tym więcej opadu przynosi przeciętny dzień mokry. Liczba dni "
        "miesiąca z nielicznymi brakami pomiaru jest przeliczona na wszystkie jego "
        "dni.\n\n"
        "Źródła: ETCCDI (Zhang i in. 2011); WMO-No. 1203, 2017",
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
        "R95p and R99p are the precipitation of the days of a year with precipitation "
        "above a threshold: the 95th or the 99th percentile of the precipitation of "
        "the wet days (at least 1 mm) of the reference period. R95pTOT and R99pTOT are "
        "the share of that sum in the precipitation of the year's wet days.\n\n"
        "R95pTOT = 100 · R95p / P\n"
        "where: R95p – precipitation of the year's days above the threshold P95 [mm], "
        "P – precipitation of all the year's wet days [mm], R95pTOT – share [%]; R99p "
        "and R99pTOT likewise with the threshold P99\n\n"
        "About one wet day in twenty of the reference period exceeds P95, one in a "
        "hundred P99. The larger R95pTOT, the more of the year's wet-day precipitation "
        "fell on the days above the threshold.\n\n"
        "Sources: ETCCDI (Zhang et al. 2011; Klein Tank et al. 2009); Hyndman and Fan "
        "1996; WMO-No. 1203, 2017",
        "R95p i R99p to suma opadu dni roku z opadem powyżej progu: 95. albo 99. "
        "percentyla opadu dni mokrych (co najmniej 1 mm) okresu odniesienia. R95pTOT i "
        "R99pTOT to udział tej sumy w opadzie dni mokrych roku.\n\n"
        "R95pTOT = 100 · R95p / P\n"
        "gdzie: R95p – opad dni roku powyżej progu P95 [mm], P – opad wszystkich dni "
        "mokrych roku [mm], R95pTOT – udział [%]; R99p i R99pTOT tak samo z progiem "
        "P99\n\n"
        "Próg P95 przekracza około co dwudziesty dzień mokry okresu odniesienia, a P99 "
        "co setny. Im większy R95pTOT, tym większą część opadu dni mokrych roku "
        "przyniosły dni powyżej progu.\n\n"
        "Źródła: ETCCDI (Zhang i in. 2011; Klein Tank i in. 2009); Hyndman i Fan 1996; "
        "WMO-No. 1203, 2017",
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
        "The annual maximum is the largest precipitation total of n consecutive days "
        "of the year (n = 1, 2, 3, 5, 10; for 1 and 5 days the indices Rx1day and "
        "Rx5day). An n-day total belongs to the year of its last day.\n\n"
        "A year with a day without a measurement is left out; the note under the table "
        "names such years. In the table of the months, “Annual maxima” gives in how "
        "many complete years the largest daily total fell in the month.\n\n"
        "Sources: ETCCDI (Zhang et al. 2011); WMO-No. 1203, 2017",
        "Maksimum roczne to największa suma opadu z n kolejnych dni roku (n = 1, 2, 3, "
        "5, 10; dla 1 i 5 dni to wskaźniki Rx1day i Rx5day). Suma n-dniowa należy do "
        "roku swojego ostatniego dnia.\n\n"
        "Rok z dniem bez pomiaru jest pominięty; takie lata wymienia notka pod tabelą. "
        "W tabeli miesięcy „Maks. roczne” podaje, w ilu latach pełnych największa suma "
        "dobowa przypadła na dany miesiąc.\n\n"
        "Źródła: ETCCDI (Zhang i in. 2011); WMO-No. 1203, 2017",
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
        "The precipitation total of the chosen number of days that the annual maximum "
        "exceeds with the probability p, that is once in T years on average. Computed "
        "from distributions fitted to the annual maxima; beside them IMGW-PIB's PMAXTP "
        "for the station's point.\n\n"
        "T = 1 / p\n"
        "pₘ = m / (n + 1)\n"
        "where: p – exceedance probability [–], T – return period [years], pₘ – "
        "exceedance probability of the m-th largest annual maximum [–], n – number of "
        "years\n\n"
        "The distribution with the smallest AIC fits best. A station's daily total "
        "(the day of 06–06 UTC) is smaller than the largest 24-hour total of a moving "
        "window, about 1.13 times on average, and is not converted.\n\n"
        "Sources: Hosking and Wallis 1997; Weiss 1964; PMAXTP: IMGW-PIB",
        "Suma opadu z wybranej liczby dni, którą maksimum roczne przekracza z "
        "prawdopodobieństwem p, czyli średnio raz na T lat. Liczona z rozkładów "
        "dopasowanych do maksimów rocznych; obok PMAXTP IMGW-PIB dla punktu "
        "stacji.\n\n"
        "T = 1 / p\n"
        "pₘ = m / (n + 1)\n"
        "gdzie: p – prawdopodobieństwo przewyższenia [–], T – okres powtarzalności "
        "[lata], pₘ – prawdopodobieństwo przewyższenia m-tego co do wielkości maksimum "
        "rocznego [–], n – liczba lat\n\n"
        "Najlepszy jest rozkład o najmniejszym AIC. Suma dobowa stacji (doba 06–06 "
        "UTC) jest mniejsza od największej sumy 24-godzinnej w przesuwanym oknie, "
        "średnio około 1,13 raza, i nie jest przeliczana.\n\n"
        "Źródła: Hosking i Wallis 1997; Weiss 1964; PMAXTP: IMGW-PIB",
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
        "A dry spell is a run of consecutive days with precipitation below the "
        "threshold, a wet spell a run of days with at least the threshold (1 mm by "
        "default). A spell counts in the year in which it starts.\n\n"
        "At a threshold of 1 mm, the longest spell of a year is the index CDD or CWD. "
        "The mark ≥ is an open spell, cut by a missing measurement: it may have been "
        "longer; the figures of the years take only the years with a measurement on "
        "every day.\n\n"
        "Sources: ETCCDI (Zhang et al. 2011); Tallaksen and van Lanen 2004",
        "Okres bezopadowy to ciąg kolejnych dni z opadem mniejszym od progu, a okres "
        "opadowy ciąg dni z opadem co najmniej równym progowi (domyślnie 1 mm). Ciąg "
        "należy do roku, w którym się zaczął.\n\n"
        "Przy progu 1 mm najdłuższy ciąg roku to wskaźnik CDD albo CWD. Znak ≥ oznacza "
        "ciąg otwarty, przerwany brakiem pomiaru: mógł być dłuższy; wartości lat liczą "
        "się tylko z lat z pomiarem w każdym dniu.\n\n"
        "Źródła: ETCCDI (Zhang i in. 2011); Tallaksen i van Lanen 2004",
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
        "The SPI is the precipitation total of k months (1, 3, 6, 12) ending in a "
        "month, expressed as a value of the standard normal distribution against such "
        "totals of the same month in the reference period.\n\n"
        "SPI = Φ⁻¹(H(x))\n"
        "H(x) = q + (1 − q) · G(x)\n"
        "where: x – total of k months [mm], G – distribution function of the gamma "
        "distribution fitted to the positive totals, q – probability of a zero total "
        "[–], Φ⁻¹ – inverse distribution function of the standard normal "
        "distribution\n\n"
        "A negative SPI is a total below the median of the fitted distribution, a "
        "positive one above it. The colours are McKee's classes; “near normal” lies "
        "between the lines −1 and 1.\n\n"
        "Sources: McKee et al. 1993; Edwards and McKee 1997; Thom 1958; WMO-No. 1090, "
        "2012",
        "SPI to suma opadów z k miesięcy (1, 3, 6, 12) kończących się w danym "
        "miesiącu, wyrażona jako wartość standardowego rozkładu normalnego względem "
        "takich sum tego samego miesiąca w okresie odniesienia.\n\n"
        "SPI = Φ⁻¹(H(x))\n"
        "H(x) = q + (1 − q) · G(x)\n"
        "gdzie: x – suma z k miesięcy [mm], G – dystrybuanta rozkładu gamma "
        "dopasowanego do sum dodatnich, q – prawdopodobieństwo sumy zerowej [–], Φ⁻¹ – "
        "funkcja odwrotna dystrybuanty standardowego rozkładu normalnego\n\n"
        "Ujemny SPI to suma mniejsza od mediany dopasowanego rozkładu, dodatni "
        "większa. Kolory to klasy McKee; klasa „normalny” leży między liniami −1 i "
        "1.\n\n"
        "Źródła: McKee i in. 1993; Edwards i McKee 1997; Thom 1958; WMO-No. 1090, 2012",
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
        "The relative precipitation is the total of a month or a year in % of its "
        "normal, the mean of the reference period. The years are classed after "
        "Kaczorowska, the months by the limits of Polish practice.\n\n"
        "Pr = 100 · P / N\n"
        "where: Pr – relative precipitation [%], P – total of the month or the year "
        "[mm], N – its normal [mm]\n\n"
        "A year is normal at 90–110 %, extremely dry below 50 % and extremely wet "
        "above 150 %. A month is normal at 75–125 %, extremely dry below 25 % and "
        "extremely wet above 200 %.\n\n"
        "Sources: Kaczorowska 1962 (years); Tomaszewska 1994 after Kosiba 1948, as "
        "given by Gąsiorek and Musiał 2011 (months)",
        "Opad względny to suma miesiąca albo roku w procentach jej normalnej, czyli "
        "średniej z okresu odniesienia. Lata są klasyfikowane według Kaczorowskiej, a "
        "miesiące według progów polskiej praktyki.\n\n"
        "Pw = 100 · P / N\n"
        "gdzie: Pw – opad względny [%], P – suma miesiąca albo roku [mm], N – jej "
        "normalna [mm]\n\n"
        "Rok jest normalny przy 90–110 %, skrajnie suchy poniżej 50 %, a skrajnie "
        "wilgotny powyżej 150 %. Miesiąc jest normalny przy 75–125 %, skrajnie suchy "
        "poniżej 25 %, a skrajnie wilgotny powyżej 200 %.\n\n"
        "Źródła: Kaczorowska 1962 (lata); Tomaszewska 1994 za Kosibą 1948, według "
        "Gąsiorka i Musiał 2011 (miesiące)",
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
