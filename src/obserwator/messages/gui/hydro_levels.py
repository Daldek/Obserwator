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
        "First-degree values are the lowest (N), mean (S) and highest (W) value of a "
        "hydrological year (November–October) or half-year. Second-degree values are "
        "the highest (W), mean (S), median (Z) and lowest (N) of them in the chosen "
        "years.\n\n"
        "The first of the three letters of a name is the statistic over the years, the "
        "second the annual value, the third the variable (Q discharge, W water level, "
        "T water temperature): SNQ is the mean of the annual lowest discharges.\n\n"
        "Sources: IMGW-PIB's method; Byczkowski 1996 (Hydrologia, vol. 1); data: "
        "IMGW-PIB (danepubliczne.imgw.pl), ČHMÚ (opendata.chmi.cz)",
        "Wartości I stopnia to najmniejsza (N), średnia (S) i największa (W) wartość "
        "roku hydrologicznego (XI–X) albo półrocza. Wartości II stopnia to największa "
        "(W), średnia (S), mediana (Z) i najmniejsza (N) z nich w wybranych "
        "latach.\n\n"
        "Pierwsza z trzech liter nazwy to statystyka lat, druga – wartość roczna, "
        "trzecia – zmienna (Q przepływ, W stan wody, T temperatura wody): SNQ to "
        "średnia z rocznych przepływów najmniejszych.\n\n"
        "Źródła: metodyka IMGW-PIB; Byczkowski 1996 (Hydrologia, t. 1); dane: IMGW-PIB "
        "(danepubliczne.imgw.pl), ČHMÚ (opendata.chmi.cz)",
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
        "A day beyond a level has a daily value at or above it (for the drought level, "
        "SNW and SNQ: below it); such days are counted in each hydrological year "
        "(November–October), with their runs. The levels are ČHMÚ's SPA 1–3, Q50 and "
        "drought level and SWW, SSW, SNW (SWQ, SSQ, SNQ) of the chosen years.\n\n"
        "A run ends on a day within the level or without a value. IMGW-PIB's warning "
        "and alarm levels are in the card “Station information”, not here.\n\n"
        "Sources: threshold level method (Tallaksen and van Lanen 2004); ČHMÚ's "
        "levels: ČHMÚ's station catalog (opendata.chmi.cz); data: IMGW-PIB "
        "(danepubliczne.imgw.pl), ČHMÚ (opendata.chmi.cz)",
        "Dzień poza progiem ma wartość dobową równą progowi lub wyższą (przy progu "
        "suszy, SNW i SNQ: niższą); liczone są takie dni w latach hydrologicznych "
        "(XI–X) i ich ciągi. Progi to SPA 1–3, Q50 i próg suszy ČHMÚ oraz SWW, SSW, "
        "SNW (SWQ, SSQ, SNQ) wybranych lat.\n\n"
        "Ciąg kończy dzień w granicach progu albo bez wartości. Stany ostrzegawczy i "
        "alarmowy IMGW-PIB są w karcie „Informacje o stacji”, a nie tutaj.\n\n"
        "Źródła: metoda progowa (Tallaksen i van Lanen 2004); progi ČHMÚ: katalog "
        "stacji ČHMÚ (opendata.chmi.cz); dane: IMGW-PIB (danepubliczne.imgw.pl), ČHMÚ "
        "(opendata.chmi.cz)",
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
        "The relation between discharge and water level at the gauge's cross-section, "
        "fitted by non-linear least squares to the same-day water level–discharge "
        "pairs of the chosen years.\n\n"
        "Q = a·(H − H₀)^b\n"
        "where: Q – discharge [m³/s], H – water level [cm], H₀ – level of zero flow, "
        "below the lowest level [cm], a – coefficient [m³/s·cm⁻ᵇ], b – exponent "
        "[–]\n\n"
        "IMGW-PIB and ČHMÚ compute the daily discharges from the levels with their own "
        "curves, so the scatter of the points and the shift of the curve over time "
        "show changes of the curve (e.g. erosion or silting of the channel, a new "
        "gauge zero), not measurement errors.\n\n"
        "Sources: daily data of IMGW-PIB (danepubliczne.imgw.pl) and ČHMÚ "
        "(opendata.chmi.cz)",
        "Zależność przepływu od stanu wody w przekroju wodowskazowym, dopasowana "
        "nieliniową metodą najmniejszych kwadratów do par stan–przepływ z tego samego "
        "dnia wybranych lat.\n\n"
        "Q = a·(H − H₀)^b\n"
        "gdzie: Q – przepływ [m³/s], H – stan wody [cm], H₀ – stan zerowego przepływu, "
        "niższy od najniższego stanu [cm], a – współczynnik [m³/s·cm⁻ᵇ], b – wykładnik "
        "[–]\n\n"
        "IMGW-PIB i ČHMÚ wyznaczają przepływy dobowe ze stanów własnymi krzywymi, więc "
        "rozrzut punktów i przesuwanie się krzywej w czasie pokazują zmiany krzywej "
        "(np. erozję lub zamulanie koryta, nowe zero wodowskazu), a nie błąd "
        "pomiaru.\n\n"
        "Źródła: dane dobowe IMGW-PIB (danepubliczne.imgw.pl) i ČHMÚ "
        "(opendata.chmi.cz)",
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
        "points of one year lie on the curve the service computed the discharges with. "
        "The hand-off carries the daily discharges of these years with the fitted "
        "curve as Obserwator's result.",
        "Pary dobowe stan–przepływ to nie pomiary hydrometryczne: punkty z jednego "
        "roku leżą na krzywej, z której służba wyliczyła przepływy. Przekazanie niesie "
        "przepływy dobowe tych lat z dopasowaną krzywą jako wynikiem Obserwatora.",
    ),
    "hydro.rating.periods_title": Text("Successive periods", "Kolejne okresy"),
    "hydro.rating.periods_info": Text(
        "Rating curves of successive periods of the station's whole record, each "
        "fitted like the curve of the chosen years, but only to the water "
        "level–discharge pairs of its own period.\n\n"
        "The table gives the discharge of each curve at the median water level and the "
        "water level at the median discharge of all pairs: their change from period to "
        "period is the shift of the curve. A period with fewer than 30 pairs has no "
        "curve.\n\n"
        "Sources: daily data of IMGW-PIB (danepubliczne.imgw.pl) and ČHMÚ "
        "(opendata.chmi.cz)",
        "Krzywe natężenia przepływu kolejnych okresów całego zapisu stacji, każda "
        "dopasowana tak jak krzywa wybranych lat, ale tylko do par stan–przepływ "
        "swojego okresu.\n\n"
        "Tabela podaje przepływ każdej krzywej przy medianie stanów i stan przy "
        "medianie przepływów wszystkich par: ich zmiana z okresu na okres to "
        "przesunięcie krzywej. Okres z mniej niż 30 parami nie ma krzywej.\n\n"
        "Źródła: dane dobowe IMGW-PIB (danepubliczne.imgw.pl) i ČHMÚ "
        "(opendata.chmi.cz)",
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
        "The quantile Q_p is the annual maximum discharge exceeded in any year with "
        "probability p, i.e. on average once in T = 1/p years, estimated from the "
        "log-normal, GEV, Pearson III and Weibull distributions fitted to the annual "
        "maxima.\n\n"
        "Q_p = F⁻¹(1 − p), T = 1/p, pₘ = m/(n + 1)\n"
        "where: Q_p – quantile [m³/s], F – distribution function of the fitted "
        "distribution [–], p – exceedance probability [–], T – return period [years], "
        "pₘ – exceedance probability of an empirical point [–], m – rank of the "
        "maximum in descending order [–], n – number of annual maxima [–]\n\n"
        "Q1% is exceeded on average once in 100 years. The distributions are ranked by "
        "AIC, the lowest first: the first is the best.\n\n"
        "Sources: Hosking and Wallis 1997 (Regional Frequency Analysis); Weibull 1939; "
        "data: IMGW-PIB (danepubliczne.imgw.pl), ČHMÚ (opendata.chmi.cz)",
        "Kwantyl Q_p to przepływ maksymalny roczny przewyższany w każdym roku z "
        "prawdopodobieństwem p, czyli średnio raz na T = 1/p lat, wyznaczany z "
        "rozkładów log-normalnego, GEV, Pearsona III i Weibulla dopasowanych do "
        "maksimów rocznych.\n\n"
        "Q_p = F⁻¹(1 − p), T = 1/p, pₘ = m/(n + 1)\n"
        "gdzie: Q_p – kwantyl [m³/s], F – dystrybuanta dopasowanego rozkładu [–], p – "
        "prawdopodobieństwo przewyższenia [–], T – okres powtarzalności [lata], pₘ – "
        "prawdopodobieństwo przewyższenia punktu empirycznego [–], m – numer maksimum "
        "w szeregu malejącym [–], n – liczba maksimów rocznych [–]\n\n"
        "Q1% jest przewyższany średnio raz na 100 lat. Rozkłady są ułożone według AIC, "
        "od najmniejszego: pierwszy jest najlepszy.\n\n"
        "Źródła: Hosking i Wallis 1997 (Regional Frequency Analysis); Weibull 1939; "
        "dane: IMGW-PIB (danepubliczne.imgw.pl), ČHMÚ (opendata.chmi.cz)",
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
        "A check whether the annual maxima come from one distribution, as the "
        "computation of the quantiles assumes: the Mann–Whitney U and "
        "Kolmogorov–Smirnov tests compare the years before the split year with the "
        "years from it, and Pettitt's test looks for the most probable year of "
        "change.\n\n"
        "A p-value below the significance level α = 0.05 rejects homogeneity (“no” in "
        "the table). A sample that is not homogeneous (e.g. after a reservoir was "
        "built) weakens the quantiles.\n\n"
        "Sources: Mann and Whitney 1947; Smirnov 1939; Pettitt 1979; data: IMGW-PIB "
        "(danepubliczne.imgw.pl), ČHMÚ (opendata.chmi.cz)",
        "Sprawdzenie, czy maksima roczne pochodzą z jednego rozkładu, jak zakłada "
        "obliczenie kwantyli: testy Manna–Whitneya U i Kołmogorowa–Smirnowa porównują "
        "lata przed rokiem podziału z latami od niego, a test Pettitta szuka "
        "najbardziej prawdopodobnego roku zmiany.\n\n"
        "Wartość p mniejsza od poziomu istotności α = 0,05 odrzuca jednorodność (w "
        "tabeli „nie”). Niejednorodna próba (np. po budowie zbiornika) osłabia "
        "kwantyle.\n\n"
        "Źródła: Mann i Whitney 1947; Smirnov 1939; Pettitt 1979; dane: IMGW-PIB "
        "(danepubliczne.imgw.pl), ČHMÚ (opendata.chmi.cz)",
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
        "NQ_T is the annual minimum discharge reached or undercut on average once in T "
        "years, estimated from the Fisher–Tippett distribution of minima (GEV for "
        "minima) fitted to the annual minima of the complete hydrological years of the "
        "daily series.\n\n"
        "T = 1/F, Fₘ = m/(n + 1)\n"
        "where: T – return period [years], F – non-exceedance probability of NQ_T [–], "
        "Fₘ – non-exceedance probability of an empirical point [–], m – rank of the "
        "minimum in ascending order [–], n – number of annual minima [–]\n\n"
        "The annual minimum falls to the 10-year NQ (F = 10 %) or below on average "
        "once in 10 years. Years with a day without a value are left out.\n\n"
        "Sources: Fisher and Tippett 1928; Gumbel 1958 (Statistics of Extremes); "
        "WMO-No. 1029 (2009); data: IMGW-PIB (danepubliczne.imgw.pl), ČHMÚ "
        "(opendata.chmi.cz)",
        "NQ_T to przepływ minimalny roczny osiągany lub niższy średnio raz na T lat, "
        "wyznaczany z rozkładu Fishera–Tippetta minimów (GEV dla minimów) dopasowanego "
        "do minimów rocznych pełnych lat hydrologicznych szeregu dobowego.\n\n"
        "T = 1/F, Fₘ = m/(n + 1)\n"
        "gdzie: T – okres powtarzalności [lata], F – prawdopodobieństwo "
        "nieprzekroczenia NQ_T [–], Fₘ – prawdopodobieństwo nieprzekroczenia punktu "
        "empirycznego [–], m – numer minimum w szeregu rosnącym [–], n – liczba "
        "minimów rocznych [–]\n\n"
        "Minimum roczne spada do NQ 10-letniego (F = 10 %) lub niżej średnio raz na 10 "
        "lat. Lata z dniem bez wartości są pominięte.\n\n"
        "Źródła: Fisher i Tippett 1928; Gumbel 1958 (Statistics of Extremes); WMO-No. "
        "1029 (2009); dane: IMGW-PIB (danepubliczne.imgw.pl), ČHMÚ (opendata.chmi.cz)",
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
