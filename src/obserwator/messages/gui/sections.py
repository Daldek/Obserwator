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
}
