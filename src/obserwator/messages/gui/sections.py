"""The building blocks of the panel's analysis sections: periods, provenance, tables, explanations."""

from obserwator.messages import Text

MESSAGES: dict[str, Text] = {
    "sections.failed": Text("The analysis failed.", "Analiza się nie powiodła."),
    "sections.info": Text("Explanation", "Objaśnienie"),
    "sections.info_methods": Text("How it is computed", "Objaśnienie metod"),
    "sections.guide": Text("More in the guide (in Polish)", "Więcej w instrukcji"),
    "sections.computing": Text("Computing…", "Liczę…"),
    "sections.stored": Text("stored result of {when}", "wynik zapisany {when}"),
    "sections.on_request": Text("computed on request", "policzony na żądanie"),
    "sections.series_version": Text("series {version}", "szereg {version}"),
    "sections.years": Text("Years", "Lata"),
    "sections.to_year": Text("to the year", "do roku"),
    "sections.recompute": Text("Recompute", "Przelicz"),
    "sections.min_years": Text(
        "Recommended minimum period: {years} years.",
        "Zalecany minimalny okres: {years} lat.",
    ),
    "sections.short_period.one": Text(
        "The period {from}–{to} has {n} year: the results are less certain.",
        "Okres {from}–{to} ma {n} rok: wyniki są mniej pewne.",
    ),
    "sections.short_period.few": Text(
        "The period {from}–{to} has {n} years: the results are less certain.",
        "Okres {from}–{to} ma {n} lata: wyniki są mniej pewne.",
    ),
    "sections.short_period.many": Text(
        "The period {from}–{to} has {n} years: the results are less certain.",
        "Okres {from}–{to} ma {n} lat: wyniki są mniej pewne.",
    ),
    "sections.short_period.other": Text(
        "The period {from}–{to} has {n} years: the results are less certain.",
        "Okres {from}–{to} ma {n} roku: wyniki są mniej pewne.",
    ),
    "sections.short_record.one": Text(
        "The period {from}–{to} has {n} year (the station's whole record): the results "
        "are less certain.",
        "Okres {from}–{to} ma {n} rok (cały zapis stacji): wyniki są mniej pewne.",
    ),
    "sections.short_record.few": Text(
        "The period {from}–{to} has {n} years (the station's whole record): the results "
        "are less certain.",
        "Okres {from}–{to} ma {n} lata (cały zapis stacji): wyniki są mniej pewne.",
    ),
    "sections.short_record.many": Text(
        "The period {from}–{to} has {n} years (the station's whole record): the results "
        "are less certain.",
        "Okres {from}–{to} ma {n} lat (cały zapis stacji): wyniki są mniej pewne.",
    ),
    "sections.short_record.other": Text(
        "The period {from}–{to} has {n} years (the station's whole record): the results "
        "are less certain.",
        "Okres {from}–{to} ma {n} roku (cały zapis stacji): wyniki są mniej pewne.",
    ),
    "sections.show_all": Text("Show all ({count})", "Pokaż wszystkie ({count})"),
    "sections.notice.short_reference_period": Text(
        "The period has {years} years, fewer than the recommended {minimum}.",
        "Okres ma {years} lat, mniej niż zalecane {minimum}.",
    ),
    # --- how Hydrolog got a Mann–Kendall p (p_value_method, Hydrolog 0.9.0) -------------
    "sections.p_value_method": Text("p method", "metoda p"),
    "sections.p_value_method.exact": Text("exact distribution", "rozkład dokładny"),
    "sections.p_value_method.normal": Text(
        "normal approximation", "przybliżenie normalne"
    ),
    # --- the versions of Hydrolog's formulas (Nogat CMP-2.8) ----------------------------
    "sections.formulas": Text("formulas: {list}", "wzory: {list}"),
    "sections.formulas_title": Text(
        "The version (formula_version) of each formula of Hydrolog that gave the result: "
        "a result of another version of a formula is computed by a changed formula.",
        "Wersja (formula_version) każdego wzoru Hydrologa, który dał wynik: wynik innej "
        "wersji wzoru policzył zmieniony wzór.",
    ),
    # --- Hydrolog's refusals (hydrolog-error/1, details.reason of Hydrolog 0.9.0) -------
    "sections.refusal.precondition_failed": Text(
        "Hydrolog does not compute it: a condition of its method fails: {condition}.",
        "Hydrolog tego nie liczy: niespełniony warunek stosowalności metody: "
        "{condition}.",
    ),
    "sections.refusal.outside_physical_constraint": Text(
        "Hydrolog does not compute it: the data break a physical condition: {condition}.",
        "Hydrolog tego nie liczy: dane łamią warunek fizyczny: {condition}.",
    ),
    "sections.refusal.outside_physical_range": Text(
        "Hydrolog does not compute it: {name} = {value} lies outside its physical "
        "range {range}.",
        "Hydrolog tego nie liczy: {name} = {value} leży poza zakresem fizycznym "
        "{range}.",
    ),
    "sections.refusal.invalid_type": Text(
        "Hydrolog does not compute it: {name} is not a number.",
        "Hydrolog tego nie liczy: {name} nie jest liczbą.",
    ),
    "sections.refusal.fit": Text(
        "{distribution} by {method}: {text}", "{distribution}, metoda {method}: {text}"
    ),
    # --- the conditions of Hydrolog's formulas the analyses meet (details.constraint) ---
    "sections.constraint.enough_values": Text(
        "too few values for the method", "za mało wartości dla tej metody"
    ),
    "sections.constraint.values_not_all_equal": Text(
        "the values are all equal", "wszystkie wartości są równe"
    ),
    "sections.constraint.positive_values": Text(
        "the log-normal distribution needs values above 0",
        "rozkład log-normalny wymaga wartości większych od 0",
    ),
    "sections.constraint.l_moments_within_distribution": Text(
        "the L-moments of the sample lie outside those the distribution can have",
        "L-momenty próby leżą poza zakresem, jaki ten rozkład może mieć",
    ),
    "sections.constraint.skewness_within_distribution": Text(
        "the skewness of the sample lies outside that the distribution can have",
        "skośność próby leży poza zakresem, jaki ten rozkład może mieć",
    ),
    "sections.constraint.likelihood_has_a_maximum": Text(
        "the likelihood has no maximum the fit can settle on (it grows without bound "
        "at a bound of the distribution)",
        "funkcja wiarygodności nie ma maksimum, na którym dopasowanie może się zatrzymać "
        "(rośnie bez ograniczenia na granicy rozkładu)",
    ),
    "sections.constraint.squares_have_a_minimum": Text(
        "the sum of squares has no minimum the fit can settle on",
        "suma kwadratów nie ma minimum, na którym dopasowanie może się zatrzymać",
    ),
    "sections.constraint.discharges_not_negative": Text(
        "a discharge is below 0", "przepływ jest mniejszy od 0"
    ),
    "sections.constraint.year_covered": Text(
        "the days with a value leave too long a gap in the year for the harmonics",
        "dni z wartością zostawiają w roku zbyt długą lukę dla harmonik",
    ),
    "sections.constraint.has_values": Text(
        "no day has a value", "żaden dzień nie ma wartości"
    ),
    "sections.constraint.recession_segment": Text(
        "no run of falling discharges is long enough",
        "żaden ciąg malejących przepływów nie jest dość długi",
    ),
    "sections.constraint.positive_flow_volume": Text(
        "the period has no flow", "w okresie nie ma przepływu"
    ),
    "sections.constraint.every_month_has_a_value": Text(
        "a calendar month has no value", "któryś miesiąc kalendarzowy nie ma wartości"
    ),
    "sections.constraint.positive_mean": Text(
        "no day has a positive discharge", "żaden dzień nie ma dodatniego przepływu"
    ),
    "sections.constraint.positive_volume": Text(
        "no month has a positive mean", "żaden miesiąc nie ma dodatniej średniej"
    ),
    "sections.constraint.enough_pairs": Text(
        "fewer than 3 stage–discharge pairs", "mniej niż 3 pary stan–przepływ"
    ),
    "sections.constraint.levels_not_all_equal": Text(
        "the water levels are all equal", "wszystkie stany wody są równe"
    ),
    "sections.constraint.discharges_not_all_equal": Text(
        "the discharges are all equal", "wszystkie przepływy są równe"
    ),
    "sections.constraint.least_squares_minimum": Text(
        "the pairs do not follow one curve: their discharge rises like an exponential "
        "of the stage, as with two ratings in the years (a moved gauge zero, a changed "
        "channel), so least squares have no minimum; choose the years of one rating",
        "pary nie układają się w jedną krzywą: przepływ rośnie jak funkcja wykładnicza "
        "stanu, jak przy dwóch krzywych w wybranych latach (przesunięte zero "
        "wodowskazu, zmienione koryto), więc suma kwadratów nie ma minimum; wybierz "
        "lata jednej krzywej",
    ),
    "sections.constraint.enough_gaugings": Text(
        "WMO-No. 1044 recommends at least 12 to 15 gaugings for a rating curve",
        "WMO-No. 1044 zaleca do krzywej natężenia przepływu co najmniej 12–15 pomiarów",
    ),
    "sections.constraint.a_wet_day": Text(
        "no day has precipitation of a wet day", "żaden dzień nie ma opadu dnia mokrego"
    ),
    "sections.constraint.a_positive_total": Text(
        "the precipitation total of the twelve months is 0",
        "suma opadu dwunastu miesięcy wynosi 0",
    ),
    "sections.constraint.three_positive_sums": Text(
        "fewer than three sums are positive", "mniej niż trzy sumy są dodatnie"
    ),
    "sections.constraint.positive_sums_differ": Text(
        "the positive sums are all equal", "wszystkie dodatnie sumy są równe"
    ),
    "sections.constraint.a_positive_temperature_sum": Text(
        "the sum of temperatures is not above 0", "suma temperatur nie jest dodatnia"
    ),
    "sections.constraint.the_same_days": Text(
        "Tmax and Tmin do not hold the same days",
        "Tmax i Tmin nie mają tych samych dni",
    ),
    "sections.constraint.two_times": Text(
        "the values are of one year only", "wartości są tylko z jednego roku"
    ),
    # --- notices of a value outside a range of a formula (Hydrolog 0.9.0) ----------------
    "sections.notice.outside_applicability.range": Text(
        "{method}: {parameter} = {value} lies outside the applicability range of the "
        "method, {minimum} to {maximum}: the result may be unreliable.",
        "{method}: {parameter} = {value} poza zakresem stosowalności metody, od "
        "{minimum} do {maximum}: wynik może być niepewny.",
    ),
    "sections.notice.outside_applicability.below": Text(
        "{method}: {parameter} = {value} lies below the applicability range of the "
        "method, from {minimum}: the result may be unreliable.",
        "{method}: {parameter} = {value} poniżej zakresu stosowalności metody, od "
        "{minimum}: wynik może być niepewny.",
    ),
    "sections.notice.outside_applicability.above": Text(
        "{method}: {parameter} = {value} lies above the applicability range of the "
        "method, up to {maximum}: the result may be unreliable.",
        "{method}: {parameter} = {value} powyżej zakresu stosowalności metody, do "
        "{maximum}: wynik może być niepewny.",
    ),
    "sections.notice.outside_applicability.condition": Text(
        "{method}: {parameter} = {value} breaks a condition of the method's "
        "applicability ({condition}): the result may be unreliable.",
        "{method}: {parameter} = {value} nie spełnia warunku stosowalności metody "
        "({condition}): wynik może być niepewny.",
    ),
    "sections.notice.outside_unverified_range.range": Text(
        "{method}: {parameter} = {value} lies outside the typical range {minimum} to "
        "{maximum}, which no published source gives yet: the result may be unreliable.",
        "{method}: {parameter} = {value} poza typowym zakresem od {minimum} do "
        "{maximum}, którego nie podaje jeszcze żadne opublikowane źródło: wynik może "
        "być niepewny.",
    ),
    "sections.notice.outside_unverified_range.below": Text(
        "{method}: {parameter} = {value} lies below the typical range, from {minimum}, "
        "which no published source gives yet: the result may be unreliable.",
        "{method}: {parameter} = {value} poniżej typowego zakresu, od {minimum}, "
        "którego nie podaje jeszcze żadne opublikowane źródło: wynik może być niepewny.",
    ),
    "sections.notice.outside_unverified_range.above": Text(
        "{method}: {parameter} = {value} lies above the typical range, up to "
        "{maximum}, which no published source gives yet: the result may be unreliable.",
        "{method}: {parameter} = {value} powyżej typowego zakresu, do {maximum}, "
        "którego nie podaje jeszcze żadne opublikowane źródło: wynik może być niepewny.",
    ),
    "sections.notice.outside_unverified_range.condition": Text(
        "{method}: {parameter} = {value} breaks a condition ({condition}) that no "
        "published source gives yet: the result may be unreliable.",
        "{method}: {parameter} = {value} nie spełnia warunku ({condition}), którego nie "
        "podaje jeszcze żadne opublikowane źródło: wynik może być niepewny.",
    ),
    "sections.notice.unreferenced_formula": Text(
        "The formula {formula} (version {formula_version}) has no reference case of a "
        "source and no independent check: its result is not verified against a "
        "source.",
        "Wzór {formula} (wersja {formula_version}) nie ma przypadku wzorcowego ze "
        "źródła ani niezależnego sprawdzenia: jego wyniku nie zweryfikowano względem "
        "źródła.",
    ),
}
