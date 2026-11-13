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
    "hydro.lowflow.info": Text(
        "A low-flow period is a run of days with the discharge below a threshold (the "
        "threshold level method; Tallaksen and van Lanen 2004) that lasts at least the "
        "given number of days (5 by default); runs parted by a gap shorter than the "
        "merging limit (4 days by default; a day without data counts as a gap) make one "
        "period. The threshold: SNQ, the mean of the annual minima of the period; Q70 or "
        "Q90, the discharge equalled or exceeded on 70 or 90 % of the days of the period "
        "(the duration curve); or a value given. The duration includes the days of the "
        "gaps; the deficit sums (threshold − Q) over the days below the threshold, times "
        "86,400 s, shown in million m³. A period belongs to the hydrological year "
        "(November to October) in which it starts; one beside missing data may have "
        "lasted longer (≥). Computed by Hydrolog (“stats low-flow-sequences”); the chart "
        "of a year draws the daily series with these periods.",
        "Niżówka to ciąg dni z przepływem poniżej progu (metoda progowa; Tallaksen i van "
        "Lanen 2004), trwający co najmniej podaną liczbę dni (domyślnie 5); ciągi "
        "rozdzielone przerwą krótszą niż próg łączenia (domyślnie 4 dni; dzień bez danych "
        "liczy się jak przerwa) tworzą jedną niżówkę. Próg: SNQ – średni z rocznych "
        "minimów okresu; Q70 lub Q90 – przepływ osiągany lub przekraczany przez 70 albo "
        "90 % dni okresu (krzywa czasu trwania); albo wartość podana. Czas trwania "
        "obejmuje dni przerw; niedobór sumuje (próg − Q) dni poniżej progu, razy 86 400 s, "
        "podany w mln m³. Niżówkę przypisuje się rokowi hydrologicznemu (XI–X) jej "
        "początku; ciąg przy braku danych mógł trwać dłużej (≥). Liczy Hydrolog („stats "
        "low-flow-sequences”); wykres roku rysuje szereg dobowy z tymi niżówkami.",
    ),
    "hydro.lowflow.threshold": Text("Threshold", "Próg"),
    "hydro.lowflow.threshold_value": Text("value", "wartość"),
    "hydro.lowflow.min_days": Text("min. days", "min. dni"),
    "hydro.lowflow.max_gap": Text(
        "merge gaps shorter than", "łącz przerwy krótsze niż"
    ),
    "hydro.lowflow.threshold_snq": Text(
        "SNQ, the mean of the annual minima {from}–{to}",
        "SNQ, średni z rocznych minimów {from}–{to}",
    ),
    "hydro.lowflow.threshold_exceedance": Text(
        "Q{percent}, equalled or exceeded on {percent} % of the days {from}–{to}",
        "Q{percent}, osiągany lub przekraczany przez {percent} % dni {from}–{to}",
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
    "hydro.lowflow.axis.deficit": Text("deficit [million m³]", "niedobór [mln m³]"),
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
    "hydro.lowflow.daily_flow": Text("daily discharge", "przepływ dobowy"),
    "hydro.lowflow.threshold_mark": Text("threshold {value}", "próg {value}"),
    "hydro.lowflow.table_title": Text(
        "Low-flow periods (latest first)", "Niżówki (od najnowszej)"
    ),
    "hydro.lowflow.col.from": Text("from", "od"),
    "hydro.lowflow.col.to": Text("to", "do"),
    "hydro.lowflow.col.days": Text("days", "dni"),
    "hydro.lowflow.col.deficit": Text("deficit [million m³]", "niedobór [mln m³]"),
    "hydro.lowflow.col.min": Text("lowest [m³/s]", "min [m³/s]"),
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
        "the chosen years (Weibull plotting positions m/(n+1)), over the whole year or one "
        "month; Hydrolog (“stats duration-curve”) also divides the values into classes "
        "(levels: 10 cm wide; discharges: 40 logarithmic classes, as with classes of equal "
        "width the lowest is always the most frequent) and gives the most frequent "
        "(modal) class and the days of each class in the months of the hydrological year "
        "with the totals “with higher” and “with lower” (the author's method of 2024). "
        "Rybczyński's zones of the water levels come from Hydrolog (“hydrometrics "
        "water-level-zones”, classes of 10 cm, the station's whole record): low "
        "background water NTW ends at the middle of the modal class, medium background "
        "water STW at the middle of the first class where the duration curve falls below "
        "50 %, above it is high background water WTW. In 2024 the author set the upper "
        "limit of STW by hand, at the tangent to the duration curve; Hydrolog applies the "
        "50 % rule.",
        "Krzywa czasu trwania (przekroczenia) podaje wartość osiąganą lub przekraczaną "
        "przez p % dni wybranych lat (pozycje Weibulla m/(n+1)), w całym roku albo jednym "
        "miesiącu; Hydrolog („stats duration-curve”) dzieli też wartości na klasy (stany: "
        "co 10 cm; przepływy: 40 klas logarytmicznych, bo przy klasach równej szerokości "
        "najczęstsza jest zawsze najniższa) i podaje klasę najczęstszą (modalną) oraz "
        "liczebności klas w miesiącach hydrologicznych z sumami „łącznie z wyższymi” i "
        "„łącznie z niższymi” (metoda autora z 2024 r.). Strefy stanów wg Rybczyńskiego "
        "liczy Hydrolog („hydrometrics water-level-zones”, klasy 10 cm, cały zapis "
        "stacji): niskie tło wodne NTW kończy się w środku klasy modalnej, średnie STW w "
        "środku pierwszej klasy, w której krzywa czasu trwania spada poniżej 50 %, wyżej "
        "jest wysokie tło WTW. Autor w 2024 r. wyznaczał górną granicę STW ręcznie, "
        "styczną do krzywej czasu trwania; Hydrolog stosuje regułę 50 %.",
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
        "Daily regime: for each day of the hydrological year (1 = 1 November) the "
        "highest, mean, median and lowest value of all years (Hydrolog's “stats daily”). "
        "Monthly statistics of the calendar months, here in the order of the "
        "hydrological year, with the Student-t confidence interval of the mean "
        "(Hydrolog's “stats monthly”). Both cover the station's whole record. Pardé's "
        "(1933) coefficients: the mean flow of each month over the mean annual flow; "
        "Dynowska's (1997) regime type by Wrzesiński's (2018) criteria (the spring month "
        "is the larger of III and IV, Perz 2019; the summer month the largest of VI–VIII); "
        "the share of March and April in the annual volume and Walsh and Lawler's (1981) "
        "seasonality index of the monthly volumes, 0 for equal months, 1.83 when one "
        "month holds all (Hydrolog's “stats regime”). Seasonality: the dates of the "
        "annual maxima and minima as directions on the circle of the year (Bayliss and "
        "Jones 1993, Burn 1997), their mean date and concentration r from 0 (spread) to "
        "1 (the same day), the shares of the winter (XI–IV) and summer half-years; from "
        "IMGW-PIB's half-years where they exist, else from the complete years of the "
        "daily series (Hydrolog's “stats seasonality”).",
        "Reżim dobowy: dla każdej doby roku hydrologicznego (1 = 1 XI) największa, "
        "średnia, mediana i najmniejsza wartość wszystkich lat (Hydrolog „stats daily”). "
        "Statystyki miesięczne miesięcy kalendarzowych, tu w kolejności roku "
        "hydrologicznego, z przedziałem ufności średniej t-Studenta (Hydrolog „stats "
        "monthly”). Obie obejmują cały zapis stacji. Współczynniki Pardégo (1933): średni "
        "przepływ miesiąca podzielony przez średni przepływ roczny; typ reżimu wg "
        "Dynowskiej (1997) według kryteriów Wrzesińskiego (2018) (miesiąc wiosenny to "
        "większy z III i IV, Perz 2019; letni – największy z VI–VIII); udział marca i "
        "kwietnia w odpływie rocznym i wskaźnik sezonowości Walsha i Lawlera (1981) "
        "objętości miesięcznych: 0 – równomierny, 1,83 – cały odpływ w jednym miesiącu "
        "(Hydrolog „stats regime”). Sezonowość: terminy rocznych maksimów i minimów jako "
        "kierunki na okręgu roku (Bayliss i Jones 1993, Burn 1997), ich średni termin i "
        "koncentracja r od 0 (rozproszone) do 1 (ten sam dzień), udział półrocza "
        "zimowego (XI–IV) i letniego; z półroczy IMGW-PIB, gdzie są, inaczej z pełnych lat "
        "szeregu dobowego (Hydrolog „stats seasonality”).",
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
        "Harmonic analysis of the annual cycle of the water temperature (Wilks 2011, "
        "Statistical Methods in the Atmospheric Sciences, section 9.4): a least-squares "
        "fit of T(t) = A₀ + Σ [aₖ·cos(2πkt/P) + bₖ·sin(2πkt/P)], P = 365.25 days, t the "
        "day of the hydrological year from 0 (1 November), with two harmonics; for each "
        "the amplitude Cₖ = √(aₖ² + bₖ²), the day of its first maximum and what it adds "
        "to the explained variance (R²); over the period and for each year with at least "
        "300 days of measurements (Hydrolog's “stats harmonics”). The curves of the chart "
        "are this fit evaluated at each day; the mean of each day over the years comes "
        "from Hydrolog's “stats daily” (drawn for the whole record). Days with the "
        "temperature at or above 15, 20, 25 °C and below 1 °C in each year, and the runs "
        "of such days (Hydrolog's “stats threshold-events”); each year's maximum with its "
        "date (Hydrolog's “stats characteristic”). The author applied this analysis to "
        "the temperatures of Baltic buoys.",
        "Analiza harmoniczna cyklu rocznego temperatury wody (Wilks 2011, Statistical "
        "Methods in the Atmospheric Sciences, rozdz. 9.4): metodą najmniejszych kwadratów "
        "dopasowane T(t) = A₀ + Σ [aₖ·cos(2πkt/P) + bₖ·sin(2πkt/P)], P = 365,25 doby, t – "
        "doba roku hydrologicznego liczona od 0 (1 XI), dwie harmoniki; dla każdej "
        "amplituda Cₖ = √(aₖ² + bₖ²), termin jej pierwszego maksimum i to, co dodaje do "
        "wariancji wyjaśnionej (R²); dla całego okresu i każdego roku z co najmniej 300 "
        "dniami pomiaru (Hydrolog „stats harmonics”). Krzywe wykresu to to dopasowanie "
        "policzone w każdej dobie; średnia doby z lat pochodzi z Hydrologa „stats daily” "
        "(rysowana dla całego zapisu). Dni z temperaturą co najmniej 15, 20, 25 °C i "
        "poniżej 1 °C w latach oraz ciągi takich dni (Hydrolog „stats threshold-events”); "
        "maksimum roczne z datą (Hydrolog „stats characteristic”). Autor stosował tę "
        "analizę do temperatur z boi bałtyckich.",
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
        "Annual trends: the two-sided Mann–Kendall test (α = 0.05, Var(S) corrected for "
        "tied values; Kendall 1975) with Sen's slope (the median of the slopes of all "
        "pairs of years; Sen 1968), Conover's intercept and the 1 − α confidence interval "
        "of the slope (Gilbert 1987), shown per 10 years (Hydrolog's “stats "
        "mann-kendall”), of the annual maxima, means and minima of the daily series "
        "that Hydrolog's “stats characteristic” gives. Runoff volume V = ΣQ·86,400 s of "
        "each hydrological year and month, the means of the complete years and months, "
        "and the cumulative volume of one year beside the mean one of the complete years "
        "(Hydrolog's “stats runoff-volume”); a year with missing days has a smaller "
        "volume and is marked. Baseflow: Lyne and Hollick's (1979) recursive filter with "
        "α = 0.925 in three passes (Nathan and McMahon 1990) on the gapless spans of at "
        "least 60 days, 30 days reflected at both ends (Ladson et al. 2013); the "
        "baseflow index BFI = ΣQb/ΣQ of the period and of each year with 300 days; the "
        "recession constant k, the median Q(t+1)/Q(t) of falls lasting 5 days or more "
        "(Tallaksen 1995), and the half-life ln 2/(−ln k) (Hydrolog's “stats "
        "baseflow”).",
        "Trendy roczne: dwustronny test Manna–Kendalla (α = 0,05, wariancja S z poprawką "
        "na powtórzenia wartości; Kendall 1975) z nachyleniem Sena (mediana nachyleń "
        "wszystkich par lat; Sen 1968), wyrazem wolnym Conovera i przedziałem ufności "
        "nachylenia 1 − α (Gilbert 1987), podanym na 10 lat (Hydrolog „stats "
        "mann-kendall”), dla rocznych maksimów, średnich i minimów szeregu dobowego, które "
        "daje Hydrolog „stats characteristic”. Objętość odpływu V = ΣQ·86 400 s każdego "
        "roku i miesiąca hydrologicznego, średnie z lat i miesięcy pełnych oraz krzywa "
        "sumowa jednego roku na tle średniej z lat pełnych (Hydrolog „stats "
        "runoff-volume”); rok z brakami ma objętość zaniżoną i jest oznaczony. Przepływ "
        "podziemny: filtr rekurencyjny Lyne'a i Hollicka (1979) z α = 0,925 w trzech "
        "przejściach (Nathan i McMahon 1990) na ciągłych odcinkach co najmniej 60 dni, z "
        "odbiciem 30 dni na obu końcach (Ladson i in. 2013); wskaźnik BFI = ΣQb/ΣQ okresu "
        "i lat z 300 dniami; stała recesji k – mediana Q(t+1)/Q(t) spadków trwających co "
        "najmniej 5 dni (Tallaksen 1995) – i czas połowicznego zaniku ln 2/(−ln k) "
        "(Hydrolog „stats baseflow”).",
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
