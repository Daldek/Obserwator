"""Messages of PIG-PIB's adapter (``providers/pl/pig.py``, ADR-035)."""

from obserwator.messages import Text

MESSAGES = {
    "no_option": Text(
        "The option {option} does not apply to the dataset {key}: PIG-PIB publishes "
        "its tables for the whole country, without stations or parameters",
        "Opcja {option} nie dotyczy zbioru {key}: PIG-PIB publikuje swoje tabele dla "
        "całego kraju, bez stacji i parametrów",
    ),
    "years_required": Text(
        "The dataset {key} needs the option years: its files are the calendar months "
        "of the readings, MWP_<YYYY-MM>.jsonl.gz",
        "Zbiór {key} wymaga opcji years: jego pliki to miesiące kalendarzowe "
        "pomiarów, MWP_<RRRR-MM>.jsonl.gz",
    ),
    "one_file": Text(
        "The option {option} does not apply to the dataset {key}: PIG-PIB publishes "
        "it as one table, kept as one file",
        "Opcja {option} nie dotyczy zbioru {key}: PIG-PIB publikuje go jako jedną "
        "tabelę, zapisywaną jako jeden plik",
    ),
    "no_readings": Text(
        "PIG-PIB's readings table holds no rows now ({url}): nothing to name",
        "Tabela pomiarów PIG-PIB nie zawiera teraz wierszy ({url}): nie ma czego "
        "nazwać",
    ),
    "window_unexpected": Text(
        "PIG-PIB's readings span {first} to {last}, not one calendar month: the file "
        "is named by their first and last day ({name})",
        "Pomiary PIG-PIB obejmują okres od {first} do {last}, nie jeden miesiąc "
        "kalendarzowy: plik nazwano pierwszym i ostatnim dniem ({name})",
    ),
    "month_republished": Text(
        "PIG-PIB republished {name}: {changed} readings changed, {added} added, "
        "{removed} removed; the earlier version is kept",
        "PIG-PIB ponownie opublikował {name}: zmieniono {changed} pomiarów, dodano "
        "{added}, usunięto {removed}; wcześniejsza wersja pozostaje",
    ),
    "watermark_needs_root": Text(
        "The harvest of {dataset} asks for the rows after the last OBJECTID the raw "
        "root holds: it needs the raw root of a store sync",
        "Pobranie {dataset} prosi o wiersze po ostatnim OBJECTID zapisanym w "
        "repozytorium surowym: wymaga repozytorium surowego operacji store sync",
    ),
    "rows_removed": Text(
        "PIG-PIB's automatic measurements count {count} rows now, fewer than the "
        "{previous} of the harvest of {day}: rows were removed",
        "Automatyczne pomiary PIG-PIB liczą teraz {count} wierszy, mniej niż {previous} "
        "z pobrania z dnia {day}: wiersze usunięto",
    ),
    "hour_revised": Text(
        "{count} hours of PIG-PIB's automatic measurements had rows with different "
        "values in {month} (the later OBJECTID kept), e.g. point {point} at {hour}",
        "{count} godzin automatycznych pomiarów PIG-PIB miało w {month} wiersze o "
        "różnych wartościach (zachowano późniejszy OBJECTID), np. punkt {point} o "
        "{hour}",
    ),
    "hour_unresolved": Text(
        "{count} points of PIG-PIB's automatic measurements left the hours 01:00 and "
        "02:00 of {days} out: no page of the stored hour 02 tells them apart",
        "{count} punktów automatycznych pomiarów PIG-PIB pominęło godziny 01:00 i "
        "02:00 dnia {days}: żadna strona zapisanej godziny 02 ich nie rozróżnia",
    ),
    "hour_future": Text(
        "{count} rows of PIG-PIB's automatic measurements lie after the answers that "
        "gave them; they stay in the captures and out of the series",
        "{count} wierszy automatycznych pomiarów PIG-PIB leży po czasie odpowiedzi, "
        "które je przyniosły; zostają w zapisach, poza serią",
    ),
    "station_unknown": Text(
        "{count} points of PIG-PIB's readings are missing from its points (e.g. "
        "{codes}): kept in the series without a ground elevation, so without H_asl",
        "{count} punktów pomiarów PIG-PIB nie ma wśród jego punktów (np. {codes}): "
        "zostają w serii bez rzędnej terenu, więc bez H_asl",
    ),
    "station_identity_changed": Text(
        "{count} points of PIG-PIB changed their CBDH number or their place since the "
        "previous points (e.g. {codes}): the ID may name another point",
        "{count} punktów PIG-PIB zmieniło numer CBDH albo położenie od poprzednich "
        "punktów (np. {codes}): ID może oznaczać inny punkt",
    ),
}
