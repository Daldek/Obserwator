"""Hydrological sections: „Stany charakterystyczne”, „Krzywa natężenia przepływu”, „Przepływy maksymalne i minimalne” (Nogat plan H1 to H6, H16)."""

from obserwator.messages import Text

_COMMON: dict[str, Text] = {
    "hydro.common.years": Text("Hydrological years", "Lata hydrologiczne"),
    "hydro.common.variable": Text("Variable", "Zmienna"),
    "hydro.common.hydro_year": Text("hydrological year", "rok hydrologiczny"),
    "hydro.common.year": Text("Year", "Rok"),
    "hydro.common.year_n": Text("year {year}", "rok {year}"),
    "hydro.common.date": Text("date", "data"),
    "hydro.common.days.one": Text("{n} day", "{n} dzień"),
    "hydro.common.days.few": Text("{n} days", "{n} dni"),
    "hydro.common.days.many": Text("{n} days", "{n} dni"),
    "hydro.common.days.other": Text("{n} days", "{n} dnia"),
    "hydro.section.characteristic": Text(
        "Characteristic levels", "Stany charakterystyczne"
    ),
    "hydro.section.rating": Text("Rating curve", "Krzywa natężenia przepływu"),
    "hydro.section.extremes": Text(
        "Maximum and minimum discharges", "Przepływy maksymalne i minimalne"
    ),
}

_CHARACTERISTIC: dict[str, Text] = {
    "hydro.characteristic.info": Text(
        "First-degree characteristic values are the lowest, mean and highest value of "
        "each hydrological year (November–October) and of its half-years "
        "(November–April, May–October): NW, SW, WW of water levels, NQ, SQ, WQ of "
        "discharges, NT, ST, WT of water temperature. Second-degree values (WWQ…NNQ, "
        "WWW…NNW) are the highest (W), mean (S), median (Z) and lowest (N) of the "
        "annual (half-year) maxima, means and minima of the chosen years, by "
        "IMGW-PIB's method. Hydrolog computes both (“stats characteristic”): in bold "
        "from the daily series (a year without a value on every day from its days "
        "with one), in small type from IMGW-PIB's half-year characteristics "
        "(pl.imgw.hydro_semiannual), whose annual maximum is the larger half-year "
        "one and may be an instantaneous value. The source “IMGW-PIB, other years "
        "daily” takes the published characteristics into the first-degree table "
        "and the years without them from the daily series. By default every year "
        "of the station's record; at least 30 years are recommended. Data: IMGW-PIB "
        "(danepubliczne.imgw.pl), ČHMÚ (opendata.chmi.cz).",
        "Wartości charakterystyczne I stopnia to najmniejsza, średnia i największa "
        "wartość roku hydrologicznego (XI–X) i jego półroczy (XI–IV, V–X): NW, SW, "
        "WW dla stanów, NQ, SQ, WQ dla przepływów, NT, ST, WT dla temperatury wody. "
        "Wartości II stopnia (WWQ…NNQ, WWW…NNW) to największa (W), średnia (S), "
        "mediana (Z) i najmniejsza (N) z rocznych (półrocznych) maksimów, średnich "
        "i minimów wybranych lat, według metodyki IMGW-PIB. Obie liczy Hydrolog "
        "(„stats characteristic”): pogrubione z szeregu dobowego (rok bez wartości "
        "w każdym dniu z dni z wartością), mniejszą czcionką z charakterystyk "
        "półrocznych IMGW-PIB (pl.imgw.hydro_semiannual), w których maksimum roczne "
        "to większe z półrocznych i może być wartością chwilową. Źródło „IMGW-PIB, "
        "pozostałe lata dobowe” bierze do tabeli I stopnia opublikowane "
        "charakterystyki, a lata bez nich z szeregu dobowego. Domyślnie wszystkie "
        "lata zapisu stacji; zalecany okres to co najmniej 30 lat. Dane: IMGW-PIB "
        "(danepubliczne.imgw.pl), ČHMÚ (opendata.chmi.cz).",
    ),
    "hydro.characteristic.second_title": Text(
        "Second-degree values", "Wartości II stopnia"
    ),
    "hydro.characteristic.first_title": Text(
        "First-degree values by year", "Wartości I stopnia w latach"
    ),
    "hydro.characteristic.period": Text("Period", "Okres"),
    "hydro.characteristic.row_max": Text("highest (W)", "największa (W)"),
    "hydro.characteristic.row_mean": Text("mean (S)", "średnia (S)"),
    "hydro.characteristic.row_median": Text("median (Z)", "mediana (Z)"),
    "hydro.characteristic.row_min": Text("lowest (N)", "najmniejsza (N)"),
    "hydro.characteristic.col_max": Text("of maxima", "z maksimów"),
    "hydro.characteristic.col_mean": Text("of means", "ze średnich"),
    "hydro.characteristic.col_min": Text("of minima", "z minimów"),
    "hydro.characteristic.alt_title": Text(
        "From IMGW-PIB's half-year characteristics",
        "Z charakterystyk półrocznych IMGW-PIB",
    ),
    "hydro.characteristic.caption_daily": Text(
        "Bold: Hydrolog from the daily series, hydrological years {from}–{to}, "
        "years with values: {years} [{unit}].",
        "Pogrubione: Hydrolog z szeregu dobowego, lata hydrologiczne {from}–{to}, "
        "lat z wartościami: {years} [{unit}].",
    ),
    "hydro.characteristic.caption_missing": Text(
        "Years without a value: {years}.", "Lata bez wartości: {years}."
    ),
    "hydro.characteristic.caption_partial": Text(
        "Years with days without a value (Hydrolog uses their days with one): {years}.",
        "Lata z dniami bez wartości (Hydrolog liczy je z dni z wartością): {years}.",
    ),
    "hydro.characteristic.caption_half": Text(
        "Small type: Hydrolog from IMGW-PIB's half-year characteristics, {from}–{to}, "
        "years: {years}; their annual maximum is the larger half-year one, which may "
        "be instantaneous, so it can exceed the daily one.",
        "Mniejsze: Hydrolog z charakterystyk półrocznych IMGW-PIB, {from}–{to}, lat: "
        "{years}; maksimum roczne to większe z półrocznych, które może być chwilowe, "
        "więc bywa wyższe od dobowego.",
    ),
    "hydro.characteristic.caption_half_only": Text(
        "Hydrolog from IMGW-PIB's half-year characteristics, hydrological years "
        "{from}–{to}, years: {years} [{unit}].",
        "Hydrolog z charakterystyk półrocznych IMGW-PIB, lata hydrologiczne "
        "{from}–{to}, lat: {years} [{unit}].",
    ),
    "hydro.characteristic.source": Text("Source", "Źródło"),
    "hydro.characteristic.source_auto": Text(
        "IMGW-PIB, other years daily", "IMGW-PIB, pozostałe lata dobowe"
    ),
    "hydro.characteristic.source_half": Text(
        "IMGW-PIB half-years", "półrocza IMGW-PIB"
    ),
    "hydro.characteristic.source_daily": Text("daily series", "szereg dobowy"),
    "hydro.characteristic.chart_title": Text(
        "First-degree values of {variable} by year",
        "Wartości I stopnia {variable} w latach",
    ),
    "hydro.characteristic.col_source": Text("source", "źródło"),
    "hydro.characteristic.from_daily": Text("daily", "dobowe"),
    "hydro.characteristic.from_daily_part": Text(
        "daily, {n} of {days} days", "dobowe, {n} z {days} dni"
    ),
    "hydro.characteristic.none": Text(
        "No values of {variable} from this source in these years.",
        "Brak wartości {variable} z tego źródła w tych latach.",
    ),
}

_LEVELS: dict[str, Text] = {
    "hydro.levels.title": Text(
        "Levels and the days beyond them", "Progi i dni poza nimi"
    ),
    "hydro.levels.info": Text(
        "ČHMÚ's thresholds (SPA 1–3, Q50 and the drought level) come from ČHMÚ's "
        "station catalog (opendata.chmi.cz); Hydrolog computes the characteristic "
        "levels SWW, SSW and SNW (SWQ, SSQ, SNQ) of the chosen years (“stats "
        "characteristic”). IMGW-PIB's warning and alarm levels are not in the "
        "archived data, so they are not here. Hydrolog counts the days beyond a "
        "level and the runs of such days (“stats threshold-events”): a day whose "
        "value is at or above the level (for the drought level and SNW/SNQ: below "
        "it) is beyond it; a run ends on a day within the level or without a value. "
        "Hydrological years November–October.",
        "Progi ČHMÚ (SPA 1–3, Q50 i próg suszy) pochodzą z katalogu stacji ČHMÚ "
        "(opendata.chmi.cz); stany (przepływy) charakterystyczne SWW, SSW i SNW "
        "(SWQ, SSQ, SNQ) wybranych lat liczy Hydrolog („stats characteristic”). "
        "Stanów ostrzegawczych i alarmowych IMGW-PIB nie ma w danych archiwalnych, "
        "więc nie ma ich tutaj. Dni poza progiem i ciągi takich dni liczy Hydrolog "
        "(„stats threshold-events”): dzień z wartością równą progowi lub wyższą "
        "(dla progu suszy i SNW/SNQ: niższą od progu) jest poza progiem; ciąg "
        "kończy dzień w granicach progu albo dzień bez wartości. Lata hydrologiczne "
        "XI–X.",
    ),
    "hydro.levels.name.spa1": Text(
        "SPA 1 · alert (bdělost)", "SPA 1 · stan czuwania (bdělost)"
    ),
    "hydro.levels.name.spa2": Text(
        "SPA 2 · readiness (pohotovost)", "SPA 2 · stan gotowości (pohotovost)"
    ),
    "hydro.levels.name.spa3": Text(
        "SPA 3 · danger (ohrožení)", "SPA 3 · stan zagrożenia (ohrožení)"
    ),
    "hydro.levels.name.q50": Text("Q50 · 50-year flood", "Q50 · woda 50-letnia"),
    "hydro.levels.name.drought": Text(
        "Drought · ČHMÚ's drought level", "Sucho · próg suszy ČHMÚ"
    ),
    "hydro.levels.short_drought": Text("drought", "sucho"),
    "hydro.levels.level": Text("Level", "Próg"),
    "hydro.levels.above": Text("days at or above it", "dni równe lub wyższe"),
    "hydro.levels.below": Text("days below it", "dni niższe"),
    "hydro.levels.daily_h": Text("daily water level", "stan dobowy"),
    "hydro.levels.daily_q": Text("daily discharge", "przepływ dobowy"),
    "hydro.levels.chart_title": Text(
        "Daily {variable} with the levels", "{variable} dobowe z progami"
    ),
    "hydro.levels.days": Text("days", "dni"),
    "hydro.levels.days_above": Text("days ≥ {value}", "dni ≥ {value}"),
    "hydro.levels.days_below": Text("days < {value}", "dni < {value}"),
    "hydro.levels.days_title": Text(
        "Days beyond the level by year", "Dni poza progiem w latach"
    ),
    "hydro.levels.fig_days": Text("Days beyond the level", "Dni poza progiem"),
    "hydro.levels.fig_years": Text(
        "hydrological years {from}–{to}", "lata hydrologiczne {from}–{to}"
    ),
    "hydro.levels.fig_events": Text("Runs of days", "Ciągi dni"),
    "hydro.levels.fig_longest": Text("Longest run", "Najdłuższy ciąg"),
    "hydro.levels.col_start": Text("from", "od"),
    "hydro.levels.col_end": Text("to", "do"),
    "hydro.levels.col_peak": Text("peak", "kulminacja"),
    "hydro.levels.col_low": Text("lowest", "minimum"),
    "hydro.levels.col_peak_date": Text("on", "dnia"),
    "hydro.levels.events_above.one": Text(
        "{n} run at or above the level, the highest peak first:",
        "{n} ciąg dni na poziomie progu lub wyżej, od najwyższej kulminacji:",
    ),
    "hydro.levels.events_above.few": Text(
        "{n} runs at or above the level, the highest peak first:",
        "{n} ciągi dni na poziomie progu lub wyżej, od najwyższej kulminacji:",
    ),
    "hydro.levels.events_above.many": Text(
        "{n} runs at or above the level, the highest peak first:",
        "{n} ciągów dni na poziomie progu lub wyżej, od najwyższej kulminacji:",
    ),
    "hydro.levels.events_above.other": Text(
        "{n} runs at or above the level, the highest peak first:",
        "{n} ciągu dni na poziomie progu lub wyżej, od najwyższej kulminacji:",
    ),
    "hydro.levels.events_below.one": Text(
        "{n} run below the level, the lowest value first:",
        "{n} ciąg dni poniżej progu, od najniższej wartości:",
    ),
    "hydro.levels.events_below.few": Text(
        "{n} runs below the level, the lowest value first:",
        "{n} ciągi dni poniżej progu, od najniższej wartości:",
    ),
    "hydro.levels.events_below.many": Text(
        "{n} runs below the level, the lowest value first:",
        "{n} ciągów dni poniżej progu, od najniższej wartości:",
    ),
    "hydro.levels.events_below.other": Text(
        "{n} runs below the level, the lowest value first:",
        "{n} ciągu dni poniżej progu, od najniższej wartości:",
    ),
}

_RATING: dict[str, Text] = {
    "hydro.rating.title": Text("Curve of the chosen years", "Krzywa wybranych lat"),
    "hydro.rating.info": Text(
        "Hydrolog fits the rating curve Q = a·(H − H₀)^b (“hydrometrics "
        "rating-curve”: non-linear least squares, H₀ below the lowest level; on "
        "request it drops the pairs whose residual exceeds 2 standard deviations "
        "and fits again) to every same-day water level–discharge pair of the chosen "
        "years; the chart thins the points to one per cell of a grid. By default "
        "the last 10 years, not the whole record as in the other analyses: the "
        "curve changes over time, so one curve fitted to many decades describes "
        "none of them well; for the same reason the recommended minimum of 30 years "
        "does not apply. The services compute daily discharges from the levels "
        "with their own curves (IMGW-PIB, ČHMÚ), so the pairs of one year lie on "
        "the curve valid that year: the scatter and the shift of the curves of "
        "successive periods show changes of the curve (e.g. erosion or silting of "
        "the channel, a new gauge zero), not measurement errors. H₀ is in "
        "centimetres, a in m³/s per cm^b. ČHMÚ's published curve is not in the "
        "store yet.",
        "Krzywą natężenia przepływu Q = a·(H − H₀)^b dopasowuje Hydrolog "
        "(„hydrometrics rating-curve”: nieliniowa metoda najmniejszych kwadratów, "
        "H₀ poniżej najniższego stanu; na życzenie odrzuca pary o resztach ponad 2 "
        "odchylenia standardowe i dopasowuje ponownie) do wszystkich par "
        "stan–przepływ z tego samego dnia w wybranych latach; na wykresie punkty są "
        "przerzedzone do jednego na komórkę siatki. Domyślnie to ostatnie 10 lat, a "
        "nie cały zapis jak w pozostałych analizach: krzywa zmienia się w czasie, "
        "więc jedna krzywa dopasowana do wielu dekad nie opisuje dobrze żadnej z "
        "nich; z tego powodu nie dotyczy jej też zalecany minimalny okres 30 lat. "
        "Przepływy dobowe służby wyznaczają ze stanów własnymi krzywymi (IMGW-PIB, "
        "ČHMÚ), więc pary z jednego roku leżą na krzywej obowiązującej w tym roku: "
        "rozrzut punktów i przesuwanie się krzywych w kolejnych okresach pokazuje "
        "zmiany krzywej (np. erozję lub zamulanie koryta, zmianę zera wodowskazu), a "
        "nie błąd pomiaru. H₀ jest w centymetrach, a w m³/s na cm^b. Opublikowanej "
        "krzywej ČHMÚ nie ma jeszcze w katalogu danych.",
    ),
    "hydro.rating.default_note": Text(
        "By default the last 10 years: the rating curve changes over time (see the "
        "explanation and the successive periods below).",
        "Domyślnie ostatnie 10 lat: krzywa natężenia zmienia się w czasie (zob. "
        "objaśnienie i kolejne okresy poniżej).",
    ),
    "hydro.rating.outliers": Text("Outliers", "Odstające"),
    "hydro.rating.outliers_keep": Text("keep", "zostaw"),
    "hydro.rating.outliers_remove": Text("remove (2σ)", "odrzuć (2σ)"),
    "hydro.rating.axis": Text("Q axis", "Oś Q"),
    "hydro.rating.axis_linear": Text("linear", "liniowa"),
    "hydro.rating.axis_log": Text("logarithmic", "logarytmiczna"),
    "hydro.rating.fig_std": Text("σ of residuals", "σ reszt"),
    "hydro.rating.fig_pairs": Text("Pairs", "Par"),
    "hydro.rating.removed": Text("{n} removed", "odrzucono {n}"),
    "hydro.rating.years_range": Text("years {from}–{to}", "lata {from}–{to}"),
    "hydro.rating.fit_label": Text("curve {from}–{to}", "krzywa {from}–{to}"),
    "hydro.rating.chart_title": Text(
        "H–Q points and the rating curve", "Punkty H–Q i krzywa natężenia przepływu"
    ),
    "hydro.rating.pairs_note": Text(
        "Daily water level–discharge pairs are not hydrometric measurements: the "
        "points of one year lie on the curve the service computed the discharges "
        "with. ČHMÚ's published curve is not in the data root yet. The hand-off carries "
        "the daily discharges of these years with the fitted curve as Obserwator's "
        "result.",
        "Pary dobowe stan–przepływ to nie pomiary hydrometryczne: punkty z jednego "
        "roku leżą na krzywej, z której służba wyliczyła przepływy. Krzywej "
        "opublikowanej przez ČHMÚ nie ma jeszcze w katalogu danych. Przekazanie niesie "
        "przepływy dobowe tych lat z dopasowaną krzywą jako wynikiem Obserwatora.",
    ),
    "hydro.rating.periods_title": Text("Successive periods", "Kolejne okresy"),
    "hydro.rating.periods_info": Text(
        "Hydrolog fits the curve of each period of the whole record separately "
        "(“hydrometrics rating-curve” with “years_per_period”; the periods start in "
        "the years 1951, 1961, … for 10-year periods); a period with fewer than 30 "
        "pairs has no curve. The table gives Q at the median water level and H at "
        "the median discharge of all pairs, both Hydrolog's, to compare the "
        "periods.",
        "Krzywe kolejnych okresów całego zapisu dopasowuje Hydrolog osobno dla "
        "każdego okresu („hydrometrics rating-curve” z „years_per_period”; okresy "
        "10-letnie zaczynają się w latach 1951, 1961, …); okres z mniej niż 30 "
        "parami nie ma krzywej. Tabela podaje przepływ przy medianie stanów i stan "
        "przy medianie przepływów wszystkich par, obie według Hydrologa, żeby "
        "porównać okresy.",
    ),
    "hydro.rating.periods": Text("Periods", "Okresy"),
    "hydro.rating.periods_length": Text("Length of the periods", "Długość okresów"),
    "hydro.rating.years_n": Text("{n} years", "{n} lat"),
    "hydro.rating.periods_chart": Text(
        "Curves of successive periods", "Krzywe kolejnych okresów"
    ),
    "hydro.rating.col_period": Text("Period", "Okres"),
    "hydro.rating.col_pairs": Text("pairs", "par"),
    "hydro.rating.col_q_at": Text("Q at H = {level} cm", "Q przy H = {level} cm"),
    "hydro.rating.col_h_at": Text("H at Q = {flow} m³/s", "H przy Q = {flow} m³/s"),
    "hydro.rating.periods_caption": Text(
        "H = {level} cm and Q = {flow} m³/s are the medians of the pairs of the "
        "whole record (Hydrolog).",
        "H = {level} cm i Q = {flow} m³/s to mediany par całego zapisu (Hydrolog).",
    ),
    "hydro.rating.no_periods": Text(
        "Hydrolog gave no periods: the record is shorter than one period.",
        "Hydrolog nie podał okresów: zapis jest krótszy niż jeden okres.",
    ),
    "hydro.rating.reason.too_few_pairs": Text(
        "fewer than 30 H–Q pairs", "mniej niż 30 par H–Q"
    ),
    "hydro.rating.reason.fit_failed": Text(
        "the fit failed", "dopasowanie się nie powiodło"
    ),
}

_EXTREMES: dict[str, Text] = {
    "hydro.extremes.max_title": Text(
        "Annual maximum discharges", "Przepływy maksymalne roczne"
    ),
    "hydro.extremes.max_info": Text(
        "Hydrolog computes the quantiles of the annual maximum discharges (“stats "
        "flood-frequency”): the log-normal, GEV, Pearson III and Weibull "
        "distributions, by default by L-moments (Hosking and Wallis 1997), with the "
        "goodness of fit by KS, Anderson–Darling's A² and AIC; the distributions are "
        "ranked by AIC. The maxima: where the data root has IMGW-PIB's half-year "
        "characteristics, the larger of the published half-year maxima (they may "
        "be instantaneous values); at other stations Hydrolog takes the maxima of "
        "the complete hydrological years (November–October) of the daily series "
        "and leaves out incomplete years. The empirical points have the exceedance "
        "probability m/(n+1). The same maxima and options go to Hydrolog through "
        "the hand-off.",
        "Kwantyle przepływów maksymalnych rocznych liczy Hydrolog („stats "
        "flood-frequency”): rozkłady log-normalny, GEV, Pearsona III i Weibulla, "
        "domyślnie metodą L-momentów (Hosking i Wallis 1997), z miarami zgodności "
        "KS, A² Andersona–Darlinga i AIC; rozkłady są ułożone wg AIC. Maksima: tam, "
        "gdzie katalog danych ma charakterystyki półroczne IMGW-PIB, większe z "
        "opublikowanych maksimów półrocznych (mogą być wartościami chwilowymi); na "
        "pozostałych stacjach Hydrolog bierze maksima pełnych lat hydrologicznych "
        "(XI–X) szeregu dobowego i pomija lata niepełne. Punkty empiryczne mają "
        "prawdopodobieństwo przewyższenia m/(n+1). Te same maksima i opcje trafiają "
        "do Hydrologa przez przekazanie.",
    ),
    "hydro.extremes.distribution": Text("Distribution", "Rozkład"),
    "hydro.extremes.dist_all": Text("all four", "wszystkie cztery"),
    "hydro.extremes.dist_log_normal": Text("log-normal", "log-normalny"),
    "hydro.extremes.fit_method": Text("Method", "Metoda"),
    "hydro.extremes.method.l_moments": Text(
        "L-moments (default)", "L-momenty (domyślna)"
    ),
    "hydro.extremes.method.mle": Text("maximum likelihood", "największa wiarygodność"),
    "hydro.extremes.method.moments": Text("moments", "momenty"),
    "hydro.extremes.method.least_squares": Text(
        "least squares", "najmniejsze kwadraty"
    ),
    "hydro.extremes.method.all": Text("all methods", "wszystkie metody"),
    "hydro.extremes.method_short.l_moments": Text("L-moments", "L-momenty"),
    "hydro.extremes.method_short.mle": Text("ML", "NW"),
    "hydro.extremes.method_short.moments": Text("moments", "momenty"),
    "hydro.extremes.method_short.least_squares": Text("LS", "MNK"),
    "hydro.extremes.source_half": Text(
        "Maxima: the half-year maxima IMGW-PIB published (the larger of the two; "
        "they may be instantaneous values).",
        "Maksima: opublikowane przez IMGW-PIB maksima półroczne (większe z dwóch; "
        "mogą być wartościami chwilowymi).",
    ),
    "hydro.extremes.source_daily": Text(
        "Maxima: Hydrolog's maxima of the complete hydrological years (XI–X) of the "
        "daily series (the data root has no half-year characteristics of this station).",
        "Maksima: maksima pełnych lat hydrologicznych (XI–X) szeregu dobowego, "
        "wybrane przez Hydrologa (katalog danych nie ma charakterystyk półrocznych tej "
        "stacji).",
    ),
    "hydro.extremes.fig_years": Text("Years", "Lat"),
    "hydro.extremes.fig_best": Text("Best (AIC)", "Najlepszy (AIC)"),
    "hydro.extremes.max_axis": Text(
        "exceedance probability", "prawdopodobieństwo przewyższenia"
    ),
    "hydro.extremes.max_points": Text("annual maxima", "maksima roczne"),
    "hydro.extremes.max_points_legend": Text(
        "annual maxima (m/(n+1))", "maksima roczne (m/(n+1))"
    ),
    "hydro.extremes.best_label": Text("{name} (best AIC)", "{name} (najlepszy AIC)"),
    "hydro.extremes.max_chart": Text(
        "Distributions of the annual maxima on a Gumbel grid",
        "Rozkłady maksimów rocznych na siatce Gumbela",
    ),
    "hydro.extremes.quantiles_title": Text(
        "Quantiles Q_p [m³/s]", "Kwantyle Q_p [m³/s]"
    ),
    "hydro.extremes.periods": Text(
        "Return periods T [years]", "Okresy powtarzalności T [lata]"
    ),
    "hydro.extremes.periods_note": Text(
        "Numbers greater than 1, separated by semicolons or spaces; at most {count}.",
        "Liczby większe od 1, oddzielone średnikami lub spacjami; najwyżej {count}.",
    ),
    "hydro.extremes.col_t": Text("T [years]", "T [lata]"),
    "hydro.extremes.col_parameters": Text("parameters", "parametry"),
    "hydro.extremes.fit_caption": Text(
        "* The KS p-value is approximate: the parameters were estimated from the "
        "same sample (Hydrolog ranks by AIC). A² is compared with its 5 % critical "
        "value.",
        "* p-value KS orientacyjne: parametry oszacowano z tej samej próby (Hydrolog "
        "porządkuje wg AIC). A² porównano z wartością krytyczną 5 %.",
    ),
    "hydro.extremes.incomplete": Text(
        "Hydrolog left out the incomplete years: {years}.",
        "Hydrolog pominął lata niepełne: {years}.",
    ),
    "hydro.extremes.handoff_note": Text(
        "Hydrolog's GUI (“Statystyka przepływów”, reading the hand-off) computes the "
        "same quantiles from the same maxima and shows Obserwator's numbers beside "
        "its own.",
        "GUI Hydrologa („Statystyka przepływów”, wczytanie przekazania) liczy z tych "
        "samych maksimów te same kwantyle i pokazuje obok liczby Obserwatora.",
    ),
    "hydro.extremes.homogeneity_title": Text(
        "Homogeneity of the maxima", "Jednorodność maksimów"
    ),
    "hydro.extremes.homogeneity_info": Text(
        "Hydrolog tests the annual maxima for homogeneity (“stats homogeneity”): "
        "the Mann–Whitney U and Kolmogorov–Smirnov tests compare the years before "
        "the split year with the years from it (by default the halves of the "
        "sample), Pettitt's test finds the most probable change point; significance "
        "level α = 0.05. A sample that is not homogeneous (e.g. after a reservoir "
        "was built) weakens the quantiles.",
        "Jednorodność maksimów rocznych sprawdza Hydrolog („stats homogeneity”): "
        "testy Manna–Whitneya U i Kołmogorowa–Smirnowa porównują lata przed rokiem "
        "podziału z latami od niego (domyślnie połowy próby), test Pettitta szuka "
        "najbardziej prawdopodobnego punktu zmiany; poziom istotności α = 0,05. "
        "Niejednorodna próba (np. po budowie zbiornika) osłabia kwantyle.",
    ),
    "hydro.extremes.test.mann_whitney": Text("Mann–Whitney U", "Manna–Whitneya U"),
    "hydro.extremes.test.kolmogorov_smirnov": Text(
        "Kolmogorov–Smirnov", "Kołmogorowa–Smirnowa"
    ),
    "hydro.extremes.test.pettitt": Text("Pettitt", "Pettitta"),
    "hydro.extremes.col_statistic": Text("statistic", "statystyka"),
    "hydro.extremes.col_homogeneous": Text("homogeneous", "jednorodny"),
    "hydro.extremes.alpha": Text(
        "Significance level α = {alpha}.", "Poziom istotności α = {alpha}."
    ),
    "hydro.extremes.yes": Text("yes", "tak"),
    "hydro.extremes.no": Text("no", "nie"),
    "hydro.extremes.split_year": Text(
        "Split: the years before {year} and from {year} ({n} maxima).",
        "Podział: lata przed {year} i od {year} ({n} maksimów).",
    ),
    "hydro.extremes.split_index": Text(
        "Split: the first {count} maxima and the rest ({n} in all).",
        "Podział: pierwsze {count} maksimów i pozostałe (razem {n}).",
    ),
    "hydro.extremes.change_point": Text(
        "Pettitt's most probable change point: {year}.",
        "Najbardziej prawdopodobny punkt zmiany wg Pettitta: {year}.",
    ),
    "hydro.extremes.low_title": Text("Minimum discharges", "Przepływy minimalne"),
    "hydro.extremes.low_info": Text(
        "Hydrolog fits the Fisher–Tippett distribution of minima (GEV for minima) to "
        "the annual minima of the complete hydrological years of the daily series "
        "(“stats low-flow”); NQ_T is the discharge reached or undercut once in T "
        "years, T = 1/F, F the non-exceedance probability. The empirical points "
        "have the probability m/(n+1). The hand-off carries the daily discharges of "
        "these years.",
        "Rozkład Fishera–Tippetta minimów (GEV dla minimów) dopasowuje Hydrolog do "
        "minimów rocznych pełnych lat hydrologicznych szeregu dobowego („stats "
        "low-flow”); NQ_T to przepływ osiągany lub niższy raz na T lat, T = 1/F, F – "
        "prawdopodobieństwo nieprzekroczenia. Punkty empiryczne mają "
        "prawdopodobieństwo m/(n+1). Przekazanie niesie przepływy dobowe tych lat.",
    ),
    "hydro.extremes.low_axis": Text(
        "non-exceedance probability of the minima",
        "prawdopodobieństwo nieprzekroczenia minimów",
    ),
    "hydro.extremes.low_curve": Text(
        "Fisher–Tippett (GEV for minima)", "Fisher–Tippett (GEV dla minimów)"
    ),
    "hydro.extremes.low_points": Text("annual minima", "minima roczne"),
    "hydro.extremes.low_chart": Text(
        "Annual minima and the Fisher–Tippett distribution",
        "Minima roczne i rozkład Fishera–Tippetta",
    ),
    "hydro.extremes.fig_low_10": Text("NQ, 10 years", "NQ 10-letni"),
}

_NOTICES: dict[str, Text] = {
    "sections.notice.missing_values_removed": Text(
        "{missing} of {total} values are missing and were left out of the analysis.",
        "Brakuje {missing} z {total} wartości; analiza je pominęła.",
    ),
    "sections.notice.missing_pairs_removed": Text(
        "{missing} of {total} H–Q pairs lack a value and were left out of the fit.",
        "{missing} z {total} par H–Q nie ma jednej z wartości; dopasowanie je "
        "pominęło.",
    ),
    "sections.notice.incomplete_years": Text(
        "Hydrolog left out {skipped} of {total} hydrological years that are "
        "incomplete (a value is needed on every day): {years}.",
        "Hydrolog pominął {skipped} z {total} lat hydrologicznych, które są niepełne "
        "(potrzebna jest wartość w każdym dniu): {years}.",
    ),
    "sections.notice.years_with_missing_days": Text(
        "{count} of {total} hydrological years have days without a value; their "
        "extremes are included and may be milder than the true ones: {years}.",
        "{count} z {total} lat hydrologicznych ma dni bez wartości; ich ekstrema są "
        "uwzględnione i mogą być łagodniejsze od prawdziwych: {years}.",
    ),
    "sections.notice.short_years_left_out": Text(
        "{count} hydrological years have fewer than {minimum} days with a value and "
        "were left out: {years}.",
        "Lata hydrologiczne z mniej niż {minimum} dniami z wartością pominięto "
        "({count}): {years}.",
    ),
    "sections.notice.undated_extremes": Text(
        "{count} annual extremes have no date in IMGW-PIB's half-year file and were "
        "left out: {years}.",
        "Ekstrema roczne bez daty w pliku półrocznym IMGW-PIB pominięto ({count}): "
        "{years}.",
    ),
    "sections.notice.homogeneity_rejected": Text(
        "Homogeneity of the series rejected at α = {alpha} by: {tests}.",
        "Jednorodność szeregu odrzucona przy α = {alpha} przez: {tests}.",
    ),
}

MESSAGES: dict[str, Text] = {
    **_COMMON,
    **_CHARACTERISTIC,
    **_LEVELS,
    **_RATING,
    **_EXTREMES,
    **_NOTICES,
}
