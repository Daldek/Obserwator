"""Hydrological sections: „Niżówki”, „Czas trwania i strefy”, „Reżim i sezonowość”, „Temperatura wody”, „Trendy i bilans” (Nogat plan H7 to H18)."""

from obserwator.messages import Text

MESSAGES: dict[str, Text] = {
    # --- the titles of the sections (hydro/index.js) ----------------------------------
    "hydro.section.lowflow": Text("Low-flow periods", "Niżówki"),
    "hydro.section.duration": Text("Duration and zones", "Czas trwania i strefy"),
    "hydro.section.regime": Text("Regime and seasonality", "Reżim i sezonowość"),
    "hydro.section.temperature": Text("Water temperature", "Temperatura wody"),
    "hydro.section.trends": Text("Trends and water balance", "Trendy i bilans"),
    # --- axes, periods and units the five sections share ------------------------------
    "hydro.axis.hydro_year": Text("hydrological year", "rok hydrologiczny"),
    "hydro.axis.hydro_years": Text("Hydrological years", "Lata hydrologiczne"),
    "hydro.axis.year": Text("year {year}", "rok {year}"),
    "hydro.axis.year_title": Text("Year {year}", "Rok {year}"),
    "hydro.axis.hydro_day": Text(
        "day of the hydrological year", "doba roku hydrologicznego"
    ),
    "hydro.axis.month": Text("month", "miesiąc"),
    "hydro.axis.q_log": Text("Q [m³/s], log scale", "Q [m³/s], skala log."),
    "hydro.axis.days.one": Text("{n} day", "{n} dzień"),
    "hydro.axis.days.few": Text("{n} days", "{n} dni"),
    "hydro.axis.days.many": Text("{n} days", "{n} dni"),
    "hydro.axis.days.other": Text("{n} days", "{n} dnia"),
    "hydro.axis.years.one": Text("{n} year", "{n} rok"),
    "hydro.axis.years.few": Text("{n} years", "{n} lata"),
    "hydro.axis.years.many": Text("{n} years", "{n} lat"),
    "hydro.axis.years.other": Text("{n} years", "{n} roku"),
    "hydro.volume.value": Text("{value} million m³", "{value} mln m³"),
    "hydro.volume.unit": Text("million m³", "mln m³"),
    "hydro.volume.axis": Text("V [million m³]", "V [mln m³]"),
    # --- „Niżówki” ------------------------------------------------------------------------
    "hydro.lowflow.info_q": Text(
        "A low-flow period is a run of days with the daily discharge below the "
        "threshold that lasts at least the chosen number of days (5 by default); runs "
        "parted by a gap shorter than the chosen limit (4 days by default) make one "
        "period.\n\n"
        "V = Σ (Q₀ − Q) · 86,400 s\n"
        "where: V – deficit [m³], Q₀ – threshold [m³/s], Q – daily discharge [m³/s]; "
        "the sum takes the days below the threshold\n\n"
        "The deficit is the volume of water missing up to the threshold, shown in "
        "million m³. A period counts in the hydrological year (November to October) in "
        "which it starts.\n\n"
        "Sources: Tallaksen and van Lanen 2004, Hydrological Drought, ch. 5; daily "
        "data of IMGW-PIB or ČHMÚ",
        "Niżówka to ciąg dni z przepływem dobowym poniżej progu, trwający co najmniej "
        "wybraną liczbę dni (domyślnie 5); ciągi rozdzielone przerwą krótszą niż "
        "wybrany limit (domyślnie 4 dni) tworzą jedną niżówkę.\n\n"
        "V = Σ (Q₀ − Q) · 86 400 s\n"
        "gdzie: V – niedobór [m³], Q₀ – próg [m³/s], Q – przepływ dobowy [m³/s]; suma "
        "obejmuje dni poniżej progu\n\n"
        "Niedobór to objętość wody brakującej do progu, podana w mln m³. Niżówka "
        "należy do roku hydrologicznego (XI–X), w którym się zaczęła.\n\n"
        "Źródła: Tallaksen i van Lanen 2004, Hydrological Drought, rozdz. 5; dane "
        "dobowe IMGW-PIB albo ČHMÚ",
    ),
    "hydro.lowflow.info_h": Text(
        "A low-water period is a run of days with the water level below the threshold "
        "that lasts at least the chosen number of days (5 by default); runs parted by "
        "a gap shorter than the chosen limit (4 days by default) make one period.\n\n"
        "D = Σ (H₀ − H) · 1 d\n"
        "where: D – deficit [cm·d], H₀ – threshold [cm], H – daily water level [cm]; "
        "the sum takes the days below the threshold\n\n"
        "The deficit measures how deep and how long the level stayed low; it is not a "
        "volume of water. The water level depends on the gauge's zero and on the river "
        "bed, so thresholds and deficits compare within one station only.\n\n"
        "Sources: Tallaksen and van Lanen 2004, Hydrological Drought, ch. 5; daily "
        "data of IMGW-PIB or ČHMÚ",
        "Niżówka stanów to ciąg dni ze stanem wody poniżej progu, trwający co najmniej "
        "wybraną liczbę dni (domyślnie 5); ciągi rozdzielone przerwą krótszą niż "
        "wybrany limit (domyślnie 4 dni) tworzą jedną niżówkę.\n\n"
        "D = Σ (H₀ − H) · 1 d\n"
        "gdzie: D – niedobór [cm·d], H₀ – próg [cm], H – dobowy stan wody [cm]; suma "
        "obejmuje dni poniżej progu\n\n"
        "Niedobór mówi, jak głęboko i jak długo stan był niski; nie jest objętością "
        "wody. Stan zależy od zera wodowskazu i koryta, więc progi i niedobory "
        "porównuje się tylko w obrębie jednej stacji.\n\n"
        "Źródła: Tallaksen i van Lanen 2004, Hydrological Drought, rozdz. 5; dane "
        "dobowe IMGW-PIB albo ČHMÚ",
    ),
    "hydro.lowflow.threshold": Text("Threshold", "Próg"),
    "hydro.lowflow.threshold_value": Text("value", "wartość"),
    "hydro.lowflow.min_days": Text("min. days", "min. dni"),
    "hydro.lowflow.max_gap": Text(
        "merge gaps shorter than", "łącz przerwy krótsze niż"
    ),
    "hydro.lowflow.threshold_mean_minimum": Text(
        "{name}, the mean of the annual minima {from}–{to}",
        "{name}, średni z rocznych minimów {from}–{to}",
    ),
    "hydro.lowflow.threshold_exceedance_q": Text(
        "Q{percent}, equalled or exceeded on {percent} % of the days {from}–{to}",
        "Q{percent}, osiągany lub przekraczany przez {percent} % dni {from}–{to}",
    ),
    "hydro.lowflow.threshold_exceedance_h": Text(
        "H{percent}, the water level equalled or exceeded on {percent} % of the days "
        "{from}–{to}",
        "H{percent}, stan wody osiągany lub przekraczany przez {percent} % dni "
        "{from}–{to}",
    ),
    "hydro.lowflow.threshold_given": Text("the threshold given", "próg podany"),
    "hydro.lowflow.events": Text("Low-flow periods", "Niżówek"),
    "hydro.lowflow.longest": Text("Longest", "Najdłuższa"),
    "hydro.lowflow.largest_deficit": Text("Largest deficit", "Największy niedobór"),
    "hydro.lowflow.total_deficit": Text("Total deficit", "Łączny niedobór"),
    "hydro.lowflow.in_years.one": Text("in {n} year", "w {n} roku"),
    "hydro.lowflow.in_years.few": Text("in {n} years", "w {n} latach"),
    "hydro.lowflow.in_years.many": Text("in {n} years", "w {n} latach"),
    "hydro.lowflow.in_years.other": Text("in {n} years", "w {n} roku"),
    "hydro.lowflow.metric": Text("On the chart", "Na wykresie"),
    "hydro.lowflow.metric_name.days": Text("days", "dni"),
    "hydro.lowflow.metric_name.deficit": Text("deficit", "niedobór"),
    "hydro.lowflow.metric_name.n": Text("number", "liczba"),
    "hydro.lowflow.axis.days": Text("low-flow days", "dni niżówki"),
    "hydro.lowflow.axis.deficit": Text("deficit [{unit}]", "niedobór [{unit}]"),
    "hydro.lowflow.axis.n": Text("number of low-flow periods", "liczba niżówek"),
    "hydro.lowflow.per_year_title": Text(
        "Low-flow periods by year", "Niżówki w latach"
    ),
    "hydro.lowflow.year": Text("Year", "Rok"),
    "hydro.lowflow.year_title": Text(
        "Hydrological year {year} with its low-flow periods",
        "Rok hydrologiczny {year} z niżówkami",
    ),
    "hydro.lowflow.year_loading": Text(
        "Loading the year {year}…", "Wczytuję rok {year}…"
    ),
    "hydro.lowflow.deficit_band": Text("deficit", "niedobór"),
    "hydro.lowflow.daily_q": Text("daily discharge", "przepływ dobowy"),
    "hydro.lowflow.daily_h": Text("daily water level", "dobowy stan wody"),
    "hydro.lowflow.threshold_mark": Text("threshold {value}", "próg {value}"),
    "hydro.lowflow.table_title": Text(
        "Low-flow periods (latest first)", "Niżówki (od najnowszej)"
    ),
    "hydro.lowflow.col.from": Text("from", "od"),
    "hydro.lowflow.col.to": Text("to", "do"),
    "hydro.lowflow.col.days": Text("days", "dni"),
    "hydro.lowflow.col.deficit": Text("deficit [{unit}]", "niedobór [{unit}]"),
    "hydro.lowflow.col.min": Text("lowest [{unit}]", "min [{unit}]"),
    "hydro.lowflow.col.mean": Text("mean", "średnio"),
    "hydro.lowflow.col.missing": Text("days missing", "braki"),
    "hydro.lowflow.open_end": Text("{date} (cut off)", "{date} (urwana)"),
    "hydro.lowflow.none": Text(
        "No low-flow period below this threshold in {from}–{to}.",
        "Brak niżówek poniżej tego progu w latach {from}–{to}.",
    ),
    "hydro.lowflow.missing_note": Text(
        "Days without data in {from}–{to}: {n}. A period beside them may have lasted "
        "longer (≥).",
        "Dni bez danych w latach {from}–{to}: {n}. Niżówka przy nich mogła trwać dłużej "
        "(≥).",
    ),
    # --- „Czas trwania i strefy” ------------------------------------------------------
    "hydro.duration.info": Text(
        "The duration curve gives the value equalled or exceeded on p % of the days of "
        "the chosen years, of the whole year or of one month. Rybczyński's zones "
        "divide the water levels of the station's whole record into low, medium and "
        "high background water (NTW, STW, WTW).\n\n"
        "p = m / (n + 1) · 100 % (Weibull plotting position)\n"
        "where: p – duration [% of the days], m – rank of the value from the highest, "
        "n – number of days with a value\n\n"
        "NTW reaches the middle of the modal (most frequent) class, STW the middle of "
        "the first class where the curve falls below 50 %; Q90 is equalled or exceeded "
        "on 90 % of the days.\n\n"
        "Sources: Searcy 1959; Vogel and Fennessey 1994; Byczkowski 1996, Hydrologia, "
        "vol. 1; daily data of IMGW-PIB or ČHMÚ",
        "Krzywa czasu trwania podaje wartość osiąganą lub przekraczaną przez p % dni "
        "wybranych lat, całego roku albo miesiąca. Strefy Rybczyńskiego dzielą stany "
        "wody całego zapisu stacji na niskie, średnie i wysokie tło wodne (NTW, STW, "
        "WTW).\n\n"
        "p = m / (n + 1) · 100 % (pozycja Weibulla)\n"
        "gdzie: p – czas trwania [% dni], m – numer wartości w ciągu uszeregowanym od "
        "największej, n – liczba dni z wartością\n\n"
        "NTW sięga środka klasy modalnej (najczęstszej), STW – środka pierwszej klasy, "
        "w której krzywa spada poniżej 50 %; Q90 jest osiągany lub przekraczany przez "
        "90 % dni.\n\n"
        "Źródła: Searcy 1959; Vogel i Fennessey 1994; Byczkowski 1996, Hydrologia, t. "
        "1; dane dobowe IMGW-PIB albo ČHMÚ",
    ),
    "hydro.duration.month": Text("Month", "Miesiąc"),
    "hydro.duration.whole_year": Text("whole year", "cały rok"),
    "hydro.duration.levels_title": Text(
        "Water levels: Rybczyński's zones and the duration curve",
        "Stany wody: strefy Rybczyńskiego i krzywa czasu trwania",
    ),
    "hydro.duration.flows_title": Text(
        "Discharge: the duration curve", "Przepływy: krzywa czasu trwania"
    ),
    "hydro.duration.table_title": Text(
        "Values of a given duration", "Wartości o danym czasie trwania"
    ),
    "hydro.duration.ntw": Text("low background water", "niskie tło wodne"),
    "hydro.duration.stw": Text("medium background water", "średnie tło wodne"),
    "hydro.duration.wtw": Text("high background water", "wysokie tło wodne"),
    "hydro.duration.modal": Text("Modal class", "Klasa modalna"),
    "hydro.duration.zones_record": Text(
        "The zones come from the station's whole record ({days} with a value).",
        "Strefy pochodzą z całego zapisu stacji ({days} z wartością).",
    ),
    "hydro.duration.basis": Text(
        "{from}–{to}{month}: {days} with a value.",
        "{from}–{to}{month}: {days} z wartością.",
    ),
    "hydro.duration.in_month": Text(", month {month}", ", miesiąc {month}"),
    "hydro.duration.curve_label": Text(
        "duration curve of {variable}", "krzywa czasu trwania {variable}"
    ),
    "hydro.duration.curve_title": Text(
        "Duration curve of {variable}", "Krzywa czasu trwania {variable}"
    ),
    "hydro.duration.x_label": Text(
        "% of the days with a value equal or higher",
        "% dni z wartością równą lub wyższą",
    ),
    "hydro.duration.readout": Text("p = {p} % of the days", "p = {p} % dni"),
    "hydro.duration.level_classes_title": Text(
        "Frequency of the level classes", "Częstość klas stanów"
    ),
    "hydro.duration.level_classes_x": Text(
        "H [cm] (classes of {width} cm)", "H [cm] (klasy co {width} cm)"
    ),
    "hydro.duration.flow_classes_title": Text(
        "Frequency of the discharge classes", "Częstość klas przepływów"
    ),
    "hydro.duration.flow_classes_x": Text(
        "Q [m³/s], logarithmic classes: {count}",
        "Q [m³/s], klasy logarytmiczne: {count}",
    ),
    "hydro.duration.share_axis": Text("% of the days", "% dni"),
    "hydro.duration.class_share": Text("share of the class", "częstość klasy"),
    "hydro.duration.class_readout": Text("class {range}", "klasa {range}"),
    "hydro.duration.months_summary.one": Text(
        "Days of the classes in the months of the hydrological year ({n} class)",
        "Liczebność klas w miesiącach hydrologicznych ({n} klasa)",
    ),
    "hydro.duration.months_summary.few": Text(
        "Days of the classes in the months of the hydrological year ({n} classes)",
        "Liczebność klas w miesiącach hydrologicznych ({n} klasy)",
    ),
    "hydro.duration.months_summary.many": Text(
        "Days of the classes in the months of the hydrological year ({n} classes)",
        "Liczebność klas w miesiącach hydrologicznych ({n} klas)",
    ),
    "hydro.duration.months_summary.other": Text(
        "Days of the classes in the months of the hydrological year ({n} classes)",
        "Liczebność klas w miesiącach hydrologicznych ({n} klasy)",
    ),
    "hydro.duration.col.class": Text("Class [cm]", "Klasa [cm]"),
    "hydro.duration.col.days": Text("days", "dni"),
    "hydro.duration.col.with_higher": Text("with higher", "z wyższymi"),
    "hydro.duration.col.with_lower": Text("with lower", "z niższymi"),
    "hydro.duration.col.p": Text("p [% of the days]", "p [% dni]"),
    "hydro.duration.q50": Text("Q50 (median)", "Q50 (mediana)"),
    "hydro.duration.q90_note": Text(
        "equalled or exceeded on 90 % of the days",
        "osiągany lub przekraczany przez 90 % dni",
    ),
    # --- „Reżim i sezonowość” ---------------------------------------------------------
    "hydro.regime.info": Text(
        "The daily and monthly regime describes the course of the hydrological year "
        "over the station's whole record. Pardé's coefficients give Dynowska's regime "
        "type, and the seasonality shows the dates of the annual extremes on the "
        "circle of the year.\n\n"
        "Kₘ = SQₘ / SQ\n"
        "where: Kₘ – Pardé's coefficient of month m [–], SQₘ – mean discharge of the "
        "month [m³/s], SQ – mean annual discharge [m³/s]\n\n"
        "A coefficient above 1 marks a month with more water than the annual mean; the "
        "seasonality index is 0 for equal months and 1.83 when the whole runoff falls "
        "in one month.\n\n"
        "Sources: Pardé 1933; Dynowska 1997; Wrzesiński 2018; Perz 2019; Walsh and "
        "Lawler 1981; Bayliss and Jones 1993; Burn 1997; daily data of IMGW-PIB or "
        "ČHMÚ, IMGW-PIB's half-years",
        "Reżim dobowy i miesięczny opisuje przebieg roku hydrologicznego z całego "
        "zapisu stacji. Współczynniki Pardégo wyznaczają typ reżimu wg Dynowskiej, a "
        "sezonowość pokazuje terminy rocznych ekstremów na okręgu roku.\n\n"
        "Kₘ = SQₘ / SQ\n"
        "gdzie: Kₘ – współczynnik Pardégo miesiąca m [–], SQₘ – średni przepływ "
        "miesiąca [m³/s], SQ – średni przepływ roczny [m³/s]\n\n"
        "Współczynnik powyżej 1 oznacza miesiąc wodniejszy od średniej rocznej; "
        "wskaźnik sezonowości wynosi 0 przy równych miesiącach i 1,83, gdy cały odpływ "
        "przypada na jeden miesiąc.\n\n"
        "Źródła: Pardé 1933; Dynowska 1997; Wrzesiński 2018; Perz 2019; Walsh i Lawler "
        "1981; Bayliss i Jones 1993; Burn 1997; dane dobowe IMGW-PIB albo ČHMÚ, "
        "półrocza IMGW-PIB",
    ),
    "hydro.regime.daily_monthly_title": Text(
        "Daily and monthly regime", "Reżim dobowy i miesięczny"
    ),
    "hydro.regime.variable": Text("Variable", "Zmienna"),
    "hydro.regime.whole_record": Text(
        "The station's whole record, {from}–{to}.", "Cały zapis stacji, {from}–{to}."
    ),
    "hydro.regime.period_scope": Text(
        "The years chosen apply to Pardé's coefficients and the dates of the extremes; "
        "the daily and monthly regime cover the whole record.",
        "Wybrane lata dotyczą współczynników Pardégo i terminów ekstremów; reżim dobowy i "
        "miesięczny obejmuje cały zapis.",
    ),
    "hydro.regime.daily_title": Text("Daily regime", "Reżim dobowy"),
    "hydro.regime.monthly_title": Text("Monthly statistics", "Statystyki miesięczne"),
    "hydro.regime.range": Text("lowest–highest", "min–maks"),
    "hydro.regime.mean": Text("mean", "średnia"),
    "hydro.regime.median": Text("median", "mediana"),
    "hydro.regime.ci": Text(
        "confidence interval {level} %", "przedział ufności {level} %"
    ),
    "hydro.regime.col.month": Text("Month", "Miesiąc"),
    "hydro.regime.col.mean": Text("mean", "średnia"),
    "hydro.regime.col.median": Text("median", "mediana"),
    "hydro.regime.col.min": Text("lowest", "min"),
    "hydro.regime.col.max": Text("highest", "maks"),
    "hydro.regime.col.std": Text("std. dev.", "odch. std."),
    "hydro.regime.col.skew": Text("skewness", "skośność"),
    "hydro.regime.col.ci": Text("CI {level} %", "PU {level} %"),
    "hydro.regime.parde_title": Text(
        "Pardé's coefficients and the regime type", "Współczynniki Pardégo i typ reżimu"
    ),
    "hydro.regime.parde_axis": Text("Pardé's coefficient", "współczynnik Pardégo"),
    "hydro.regime.type": Text("Regime type", "Typ reżimu"),
    "hydro.regime.type.nival_weak": Text(
        "nival, weakly developed", "niwalny słabo wykształcony"
    ),
    "hydro.regime.type.nival_moderate": Text(
        "nival, moderately developed", "niwalny średnio wykształcony"
    ),
    "hydro.regime.type.nival_strong": Text(
        "nival, strongly developed", "niwalny silnie wykształcony"
    ),
    "hydro.regime.type.nival_pluvial": Text("nival-pluvial", "niwalno-pluwialny"),
    "hydro.regime.type.pluvial_nival": Text("pluvio-nival", "pluwialno-niwalny"),
    "hydro.regime.type_note": Text(
        "Dynowska 1997, type {code}", "Dynowska 1997, typ {code}"
    ),
    "hydro.regime.spring": Text("Spring month", "Miesiąc wiosenny"),
    "hydro.regime.summer": Text("Summer month", "Miesiąc letni"),
    "hydro.regime.spring_share": Text("Runoff of III–IV", "Odpływ III–IV"),
    "hydro.regime.spring_share_note": Text("share of the year's", "udział w rocznym"),
    "hydro.regime.seasonality_index": Text("Seasonality index", "Wskaźnik sezonowości"),
    "hydro.regime.seasonality_index_note": Text(
        "Walsh and Lawler 1981", "Walsh i Lawler 1981"
    ),
    "hydro.regime.criteria": Text(
        "Dynowska's (1997) criteria as Wrzesiński (2018) states them: nival weakly "
        "developed when the spring month (the larger of III and IV) reaches at most "
        "{weak} % of the mean annual flow, moderately at most {strong} %, strongly more; "
        "nival-pluvial when the summer month (the largest of VI–VIII) reaches {rise} %; "
        "pluvio-nival when it reaches at least {equal} % of the spring month. Years "
        "{from}–{to}, with values: {years}.",
        "Kryteria Dynowskiej (1997) wg Wrzesińskiego (2018): niwalny słabo wykształcony, "
        "gdy miesiąc wiosenny (większy z III i IV) osiąga najwyżej {weak} % średniego "
        "przepływu rocznego, średnio – najwyżej {strong} %, silnie – więcej; "
        "niwalno-pluwialny, gdy miesiąc letni (największy z VI–VIII) osiąga {rise} %; "
        "pluwialno-niwalny, gdy osiąga co najmniej {equal} % wiosennego. Lata "
        "{from}–{to}, z danymi: {years}.",
    ),
    "hydro.regime.extremes_title": Text(
        "Seasonality of the annual extremes", "Sezonowość ekstremów rocznych"
    ),
    "hydro.regime.extremes": Text("Extremes", "Ekstrema"),
    "hydro.regime.maxima": Text("highest", "maksima"),
    "hydro.regime.minima": Text("lowest", "minima"),
    "hydro.regime.mean_date": Text("Mean date of {name}", "Średni termin {name}"),
    "hydro.regime.concentration": Text("Concentration r", "Koncentracja r"),
    "hydro.regime.concentration_note": Text(
        "0 spread, 1 the same day", "0 rozproszone, 1 ten sam dzień"
    ),
    "hydro.regime.winter_share": Text("In the winter half-year", "W półroczu zimowym"),
    "hydro.regime.source": Text("Source", "Źródło"),
    "hydro.regime.source.half_years": Text(
        "IMGW-PIB's half-years", "półrocza IMGW-PIB"
    ),
    "hydro.regime.source.daily": Text("the daily series", "szereg dobowy"),
    "hydro.regime.circle_label": Text(
        "{name}: the dates on the circle of the year", "{name}: terminy na okręgu roku"
    ),
    "hydro.regime.circle_caption": Text(
        "Dates of {name}: a dot is the date on the circle of the year (1 January at the "
        "top), its distance from the centre the year ({from} at the centre, {to} "
        "outside); colour: winter or summer half-year; the line points to the mean date "
        "and its length is r.",
        "Terminy {name}: punkt to termin na okręgu roku (1 stycznia u góry), odległość od "
        "środka – rok ({from} w środku, {to} na zewnątrz); kolor: półrocze zimowe lub "
        "letnie; wektor wskazuje średni termin, a jego długość to r.",
    ),
    "hydro.regime.dates_title": Text(
        "Dates of {name} by year", "Terminy {name} w latach"
    ),
    "hydro.regime.no_dates": Text(
        "No dated extreme in these years.", "Brak dat ekstremów w tych latach."
    ),
    # --- „Temperatura wody” -----------------------------------------------------------
    "hydro.temperature.info": Text(
        "The annual cycle of the water temperature is described by its mean A₀ and two "
        "harmonics with a period of a year and of half a year, fitted by least squares "
        "over the whole period and for each year with at least 300 days of "
        "measurements. The days at or above 15, 20 and 25 °C and below 1 °C are "
        "counted too.\n\n"
        "T(t) = A₀ + Σ [aₖ·cos(2πkt/P) + bₖ·sin(2πkt/P)], k = 1, 2\n"
        "Cₖ = √(aₖ² + bₖ²)\n"
        "where: T – water temperature [°C], t – day of the hydrological year counted "
        "from 0 (1 November) [d], P = 365.25 d, A₀ – mean [°C], aₖ, bₖ – coefficients "
        "of harmonic k [°C], Cₖ – its amplitude [°C]\n\n"
        "By the first harmonic the temperature varies from A₀ − C₁ to A₀ + C₁; the "
        "explained variance is the share of the variation that the harmonics "
        "describe.\n\n"
        "Sources: Wilks 2011, Statistical Methods in the Atmospheric Sciences, section "
        "9.4; daily data of IMGW-PIB or ČHMÚ",
        "Cykl roczny temperatury wody opisują średnia A₀ i dwie harmoniki o okresie "
        "roku i pół roku, dopasowane metodą najmniejszych kwadratów dla całego okresu "
        "i każdego roku z co najmniej 300 dniami pomiaru. Liczone są też dni z "
        "temperaturą ≥ 15, 20, 25 °C i < 1 °C.\n\n"
        "T(t) = A₀ + Σ [aₖ·cos(2πkt/P) + bₖ·sin(2πkt/P)], k = 1, 2\n"
        "Cₖ = √(aₖ² + bₖ²)\n"
        "gdzie: T – temperatura wody [°C], t – doba roku hydrologicznego liczona od 0 "
        "(1 XI) [d], P = 365,25 d, A₀ – średnia [°C], aₖ, bₖ – współczynniki k-tej "
        "harmoniki [°C], Cₖ – jej amplituda [°C]\n\n"
        "Według pierwszej harmoniki temperatura waha się od A₀ − C₁ do A₀ + C₁; "
        "wariancja wyjaśniona to udział zmienności opisanej przez harmoniki.\n\n"
        "Źródła: Wilks 2011, Statistical Methods in the Atmospheric Sciences, rozdz. "
        "9.4; dane dobowe IMGW-PIB albo ČHMÚ",
    ),
    "hydro.temperature.cycle_part": Text(
        "Annual cycle and its harmonics", "Cykl roczny i jego harmoniki"
    ),
    "hydro.temperature.a0": Text("A₀ mean", "A₀ średnia"),
    "hydro.temperature.c1": Text("C₁ amplitude", "C₁ amplituda"),
    "hydro.temperature.max_on": Text("maximum {date}", "maksimum {date}"),
    "hydro.temperature.max_on_half": Text(
        "maximum {date} (and half a year later)", "maksimum {date} (i pół roku później)"
    ),
    "hydro.temperature.explained": Text("Explained variance", "Wariancja wyjaśniona"),
    "hydro.temperature.explained_all": Text(
        "harmonics 1–{n}: {value} %", "harmoniki 1–{n}: {value} %"
    ),
    "hydro.temperature.cycle_title": Text(
        "Annual cycle of the water temperature", "Cykl roczny temperatury wody"
    ),
    "hydro.temperature.day_mean": Text(
        "mean of the day over the years", "średnia doby z lat"
    ),
    "hydro.temperature.fit": Text("harmonics 1–{n}", "harmoniki 1–{n}"),
    "hydro.temperature.first_harmonic": Text("1st harmonic", "1. harmoniczna"),
    "hydro.temperature.yearly_title": Text(
        "Mean and amplitude by year", "Średnia i amplituda w latach"
    ),
    "hydro.temperature.no_year_fit": Text(
        "No year has 300 days with a measurement: the harmonics are fitted over the whole "
        "period only.",
        "Żaden rok nie ma 300 dni z pomiarem: harmoniki tylko dla całego okresu.",
    ),
    "hydro.temperature.days_part": Text(
        "Days beyond a threshold", "Dni z temperaturą poza progiem"
    ),
    "hydro.temperature.threshold": Text("Threshold", "Próg"),
    "hydro.temperature.days_axis": Text("days", "dni"),
    "hydro.temperature.days_label": Text(
        "days with T {threshold}", "dni z T {threshold}"
    ),
    "hydro.temperature.days_title": Text(
        "Days with T {threshold} by year", "Dni z T {threshold} w latach"
    ),
    "hydro.temperature.days_beyond": Text(
        "Days with T {threshold}", "Dni z T {threshold}"
    ),
    "hydro.temperature.runs": Text("Runs of such days", "Ciągi takich dni"),
    "hydro.temperature.longest_run": Text("Longest run", "Najdłuższy ciąg"),
    "hydro.temperature.years_part": Text("Years", "Lata"),
    "hydro.temperature.col.year": Text("Year", "Rok"),
    "hydro.temperature.col.days": Text("days", "dni"),
    "hydro.temperature.col.phase1": Text("max. of the 1st harm.", "maks. 1. harm."),
    "hydro.temperature.col.max": Text("max. T", "maks. T"),
    # --- „Trendy i bilans” ------------------------------------------------------------
    "hydro.trends.info": Text(
        "The Mann–Kendall test checks whether the annual maxima, means and minima rise "
        "or fall; Sen's slope gives the change per 10 years. The runoff volume of each "
        "year and month adds up the daily discharges, and Lyne and Hollick's filter "
        "separates the baseflow from the discharge.\n\n"
        "β = median of (xⱼ − xᵢ) / (j − i) over all pairs of years i < j\n"
        "V = Σ Q · 86,400 s\n"
        "BFI = Σ Qb / Σ Q\n"
        "where: xᵢ – annual value of year i, β – Sen's slope [unit per year; shown per "
        "10 years], V – runoff volume [m³], Q – daily discharge [m³/s], Qb – baseflow "
        "[m³/s]\n\n"
        "A trend is increasing or decreasing when p < α = 0.05, otherwise “none”. A "
        "BFI near 1 means that nearly all of the runoff is baseflow.\n\n"
        "Sources: Kendall 1975; Sen 1968; Gilbert 1987; Conover 1980; Lyne and Hollick "
        "1979; Nathan and McMahon 1990; Ladson et al. 2013; Tallaksen 1995; daily data "
        "of IMGW-PIB or ČHMÚ",
        "Test Manna–Kendalla sprawdza, czy roczne maksima, średnie i minima rosną albo "
        "maleją; nachylenie Sena podaje zmianę na 10 lat. Objętość odpływu roku i "
        "miesiąca sumuje przepływy dobowe, a filtr Lyne’a i Hollicka wydziela z "
        "przepływu przepływ podziemny.\n\n"
        "β = mediana (xⱼ − xᵢ) / (j − i) dla wszystkich par lat i < j\n"
        "V = Σ Q · 86 400 s\n"
        "BFI = Σ Qb / Σ Q\n"
        "gdzie: xᵢ – wartość roczna roku i, β – nachylenie Sena [jednostka na rok; na "
        "stronie na 10 lat], V – objętość odpływu [m³], Q – przepływ dobowy [m³/s], Qb "
        "– przepływ podziemny [m³/s]\n\n"
        "Trend jest rosnący albo malejący, gdy p < α = 0,05, inaczej „brak”. BFI "
        "bliski 1 oznacza, że prawie cały odpływ to przepływ podziemny.\n\n"
        "Źródła: Kendall 1975; Sen 1968; Gilbert 1987; Conover 1980; Lyne i Hollick "
        "1979; Nathan i McMahon 1990; Ladson i in. 2013; Tallaksen 1995; dane dobowe "
        "IMGW-PIB albo ČHMÚ",
    ),
    "hydro.trends.annual_trends_title": Text("Annual trends", "Trendy roczne"),
    "hydro.trends.variable": Text("Variable", "Zmienna"),
    "hydro.trends.source_note": Text(
        "Annual values: the highest, mean and lowest daily value of each hydrological "
        "year of the daily series (Hydrolog's “stats characteristic”).",
        "Wartości roczne: największa, średnia i najmniejsza wartość dobowa każdego roku "
        "hydrologicznego szeregu dobowego (Hydrolog „stats characteristic”).",
    ),
    "hydro.trends.col.series": Text("Series", "Szereg"),
    "hydro.trends.col.years": Text("years", "lata"),
    "hydro.trends.col.trend": Text("trend at α = {alpha}", "trend (α = {alpha})"),
    "hydro.trends.col.sen": Text(
        "Sen's slope [{unit}/10 years] (interval)",
        "nachylenie Sena [{unit}/10 lat] (przedział)",
    ),
    "hydro.trends.direction.increasing": Text("increasing", "rosnący"),
    "hydro.trends.direction.decreasing": Text("decreasing", "malejący"),
    "hydro.trends.direction.none": Text("none", "brak"),
    "hydro.trends.t_name.max": Text("highest T", "maks. T"),
    "hydro.trends.t_name.mean": Text("mean T", "śr. T"),
    "hydro.trends.t_name.min": Text("lowest T", "min. T"),
    "hydro.trends.chart": Text("Chart", "Wykres"),
    "hydro.trends.chart_title": Text("Trend of {name}", "Trend {name}"),
    "hydro.trends.sen_label": Text(
        "Sen's slope {slope} {unit}/10 years", "nachylenie Sena {slope} {unit}/10 lat"
    ),
    "hydro.trends.runoff_title": Text("Runoff volume", "Objętość odpływu"),
    "hydro.trends.mean_annual": Text("Mean annual runoff", "Średni odpływ roczny"),
    "hydro.trends.complete_years.one": Text("{n} complete year", "{n} rok pełny"),
    "hydro.trends.complete_years.few": Text("{n} complete years", "{n} lata pełne"),
    "hydro.trends.complete_years.many": Text("{n} complete years", "{n} lat pełnych"),
    "hydro.trends.complete_years.other": Text("{n} complete years", "{n} roku pełnego"),
    "hydro.trends.incomplete_note": Text(
        "incomplete: {present} of {days} days with data",
        "niepełny: {present} z {days} dni z danymi",
    ),
    "hydro.trends.annual_title": Text("Annual runoff", "Odpływ roczny"),
    "hydro.trends.annual_series": Text("annual runoff", "odpływ roczny"),
    "hydro.trends.mean_mark": Text("mean {value}", "średnio {value}"),
    "hydro.trends.monthly_title": Text(
        "Mean runoff of the months", "Średni odpływ miesięcy"
    ),
    "hydro.trends.monthly_series": Text(
        "mean runoff of the month", "średni odpływ miesiąca"
    ),
    "hydro.trends.year": Text("Year", "Rok"),
    "hydro.trends.incomplete_option": Text("{year} (incomplete)", "{year} (niepełny)"),
    "hydro.trends.cumulative_title": Text("Cumulative runoff", "Krzywa sumowa odpływu"),
    "hydro.trends.cumulative_mean": Text("mean of {years}", "średnio ({years})"),
    "hydro.trends.baseflow_title": Text("Baseflow", "Przepływ podziemny"),
    "hydro.trends.recession": Text("Recession constant k", "Stała recesji k"),
    "hydro.trends.segments.one": Text("{n} recession segment", "{n} odcinek opadania"),
    "hydro.trends.segments.few": Text("{n} recession segments", "{n} odcinki opadania"),
    "hydro.trends.segments.many": Text(
        "{n} recession segments", "{n} odcinków opadania"
    ),
    "hydro.trends.segments.other": Text(
        "{n} recession segments", "{n} odcinka opadania"
    ),
    "hydro.trends.half_life": Text("Half-life", "Połowiczny zanik"),
    "hydro.trends.filter": Text("Filter", "Filtr"),
    "hydro.trends.filter_note": Text(
        "Lyne and Hollick, passes: {passes}", "Lyne i Hollick, przejścia: {passes}"
    ),
    "hydro.trends.bfi_title": Text(
        "Baseflow index by year", "Wskaźnik przepływu podziemnego w latach"
    ),
    "hydro.trends.bfi_mark": Text("{value} over the period", "{value} w okresie"),
    "hydro.trends.separation_title": Text(
        "Hydrograph separation, year {year}", "Rozdział hydrogramu, rok {year}"
    ),
    "hydro.trends.flow": Text("discharge", "przepływ"),
    "hydro.trends.baseflow": Text("baseflow", "przepływ podziemny"),
    "hydro.trends.year_loading": Text(
        "Loading the year {year}…", "Wczytuję rok {year}…"
    ),
    # --- Hydrolog's notices these sections meet -----------------------------------------
    "sections.notice.single_value_month": Text(
        "Months {months} hold a single value: their standard deviation, coefficient of "
        "variation, skewness and confidence interval are undefined.",
        "Miesiące {months} mają jedną wartość: ich odchylenie standardowe, współczynnik "
        "zmienności, skośność i przedział ufności są nieokreślone.",
    ),
}
