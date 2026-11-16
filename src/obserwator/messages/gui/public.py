"""The public GUI's rules (Nogat DEV-15.7 to DEV-15.12): the rate limit, the regulamin, „Zgłoś uwagę”."""

from obserwator.messages import Text

MESSAGES: dict[str, Text] = {
    "public.rate_limited": Text(
        "Too many requests. Try again in {seconds} s.",
        "Zbyt wiele żądań. Spróbuj ponownie za {seconds} s.",
    ),
    "public.write_failed": Text(
        "The GUI could not read or write its file {file}: {reason}",
        "GUI nie mogło odczytać ani zapisać pliku {file}: {reason}",
    ),
    "public.terms_not_served": Text(
        "The GUI serves no regulamin.html and links none: {reason}",
        "GUI nie udostępnia regulamin.html ani odnośnika do niego: {reason}",
    ),
    "public.terms_bad_values": Text(
        "values of the terms: missing or empty {missing}; unknown {unknown}",
        "wartości regulaminu: brak albo puste {missing}; nieznane {unknown}",
    ),
    "public.terms_unknown_blocks": Text(
        "not a block of the terms: {blocks}",
        "nie ma takiego bloku regulaminu: {blocks}",
    ),
    "public.terms_field_left": Text(
        "the filled terms still hold {{{{",
        "wypełniony regulamin wciąż zawiera {{{{",
    ),
    "public.feedback_forbidden": Text(
        "Reports are accepted only from this site's own page.",
        "Zgłoszenia przyjmuje tylko strona tego serwisu.",
    ),
    "public.feedback_content_type": Text(
        "A report must be sent as application/json.",
        "Zgłoszenie musi być wysłane jako application/json.",
    ),
    "public.feedback_too_large": Text(
        "The report is too large (at most {limit} KiB).",
        "Zgłoszenie jest za duże (najwyżej {limit} KiB).",
    ),
    "public.feedback_not_json": Text(
        "The report is not valid JSON.",
        "Zgłoszenie nie jest poprawnym JSON-em.",
    ),
    "public.feedback_bad_shape": Text(
        'A report is {{"message": text, "context": object}} without other fields.',
        'Zgłoszenie to {{"message": tekst, "context": obiekt}} bez innych pól.',
    ),
    "public.feedback_empty": Text(
        "The description must not be empty.",
        "Opis nie może być pusty.",
    ),
    "public.feedback_too_long": Text(
        "The description may have at most {maximum} characters.",
        "Opis może mieć najwyżej {maximum} znaków.",
    ),
    "public.feedback_bad_context": Text(
        "The context field {field} is not valid.",
        "Pole kontekstu {field} jest niepoprawne.",
    ),
    "public.feedback_unknown_station": Text(
        "There is no station {station} in the catalog.",
        "W katalogu nie ma stacji {station}.",
    ),
    "public.feedback_too_many_parameters": Text(
        "The context may hold at most {maximum} parameters.",
        "Kontekst może mieć najwyżej {maximum} parametrów.",
    ),
    "public.feedback_context_too_large": Text(
        "The context of the report is too large (at most {maximum} KB).",
        "Kontekst zgłoszenia jest za duży (najwyżej {maximum} KB).",
    ),
    "public.feedback_rate_limited": Text(
        "Too many reports from this address. Try again in {seconds} s.",
        "Za dużo zgłoszeń z tego adresu. Spróbuj ponownie za {seconds} s.",
    ),
    "public.feedback_io_error": Text(
        "The report could not be stored. Try again later.",
        "Nie udało się zapisać zgłoszenia. Spróbuj ponownie później.",
    ),
}
