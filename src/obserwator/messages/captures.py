"""Messages of ``captures.py`` and ``store/captures.py`` (ADR-030 D3, D5-D7, D9)."""

from obserwator.messages import Text

MESSAGES = {
    "field_not_text": Text(
        "The field {name} of the record is not text",
        "Pole {name} zapisu nie jest tekstem",
    ),
    "record_not_object": Text(
        "The record is not a JSON object",
        "Zapis nie jest obiektem JSON",
    ),
    "record_invalid": Text(
        "The record of {time} has no valid time, status, SHA-256 or body",
        "Zapis z {time} nie ma poprawnego czasu, statusu, SHA-256 lub treści",
    ),
    "seen_without_answer": Text(
        "The record of {time} is seen, but no equal answer of its address comes before it",
        "Zapis z {time} jest oznaczony jako powtórzony, ale nie poprzedza go równa "
        "odpowiedź z tego samego adresu",
    ),
    "body_sha_mismatch": Text(
        "The body of the record of {time} does not match its SHA-256",
        "Treść zapisu z {time} nie zgadza się z jego SHA-256",
    ),
    "not_spool_file": Text(
        "{name} is no file of the capture spool",
        "{name} nie jest plikiem bufora zapisów",
    ),
    "name_does_not_match": Text(
        "The time or SHA-256 of the answer in {name} does not match its name",
        "Czas lub SHA-256 odpowiedzi w {name} nie zgadza się z nazwą pliku",
    ),
    "spool_failed": Text(
        "An answer of {dataset} could not be kept in the capture spool {spool}: "
        "{reason}; the answer was served without it",
        "Odpowiedź zbioru {dataset} nie trafiła do bufora zapisów {spool}: {reason}; "
        "odpowiedź podano mimo to",
    ),
    "spool_unwritable": Text(
        "The capture spool {spool} cannot be written: the answers of current data are "
        "served, but not kept",
        "Do bufora zapisów {spool} nie można pisać: odpowiedzi z danymi bieżącymi są "
        "podawane, ale nie zachowywane",
    ),
    "spool_last_failure": Text(
        "The last answer of {dataset} could not be kept in the capture spool {spool} "
        "at {time}: {reason}; none has been kept since",
        "Ostatnia odpowiedź zbioru {dataset} nie trafiła do bufora zapisów {spool} "
        "o {time}: {reason}; od tej pory żadna nie została zachowana",
    ),
    "section_not_table": Text(
        "[obserwator.capture] must be a table of sources, each public or private",
        "[obserwator.capture] musi być tabelą źródeł, każde public albo private",
    ),
    "unknown_source": Text(
        "{source} in [obserwator.capture] is no source of operational or telemetry "
        "data; the sources: {sources}",
        "{source} w [obserwator.capture] nie jest źródłem danych operacyjnych ani "
        "telemetrycznych; źródła: {sources}",
    ),
    "bad_state": Text(
        "{source} in [obserwator.capture] is {value}; allowed: {allowed}",
        "{source} w [obserwator.capture] ma wartość {value}; dozwolone: {allowed}",
    ),
    "source_set_twice": Text(
        "{source} is set more than once in [obserwator.capture] (a quoted key and a "
        "dotted one name the same source)",
        "{source} ustawiono w [obserwator.capture] więcej niż raz (klucz w cudzysłowie "
        "i klucz z kropkami wskazują to samo źródło)",
    ),
    "poll_planned": Text(
        "Live read of {url}, its answer kept in the capture spool {spool} ({dataset} "
        "changes at most every {interval} s)",
        "Odczyt na żywo {url}, odpowiedź zachowana w buforze zapisów {spool} "
        "({dataset} zmienia się najwyżej co {interval} s)",
    ),
    "poll_too_soon": Text(
        "{dataset} was polled at {polled_at} and changes at most every {interval} s: "
        "the next poll is due at {due}",
        "{dataset} odpytano o {polled_at}, a zmienia się najwyżej co {interval} s: "
        "następne odpytanie od {due}",
    ),
    "not_capture_dataset": Text(
        "{dataset} is no capture dataset: its answer was not kept",
        "{dataset} nie jest zbiorem zapisów: odpowiedzi nie zachowano",
    ),
    "poll_progress": Text(
        "Polled {dataset}",
        "Odpytano {dataset}",
    ),
    "unreadable_spool_file": Text(
        "The spool file {name} cannot be read and stays in the spool: {reason}",
        "Pliku bufora {name} nie można odczytać i zostaje w buforze: {reason}",
    ),
    "corrupt_capture": Text(
        "The capture version {version} cannot be read: {reason}",
        "Nie można odczytać wersji zapisów {version}: {reason}",
    ),
    "capture_written": Text(
        "Sealed {filename}: {answers} answers of the UTC day {day}",
        "Zamknięto {filename}: {answers} odpowiedzi doby UTC {day}",
    ),
    "day_unreadable": Text(
        "The spool holds no readable answer of {dataset} of {day}",
        "Bufor nie zawiera żadnej czytelnej odpowiedzi zbioru {dataset} z {day}",
    ),
}
