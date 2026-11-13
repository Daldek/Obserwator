"""The server's texts about analyses computed on request: options, inputs and Hydrolog's program."""

from obserwator.messages import Text

MESSAGES: dict[str, Text] = {
    # --- a person's options -------------------------------------------------------------
    "analyses.option_not_overridable": Text(
        "The option {option} of the analysis {analysis} cannot be changed; allowed: "
        "{allowed}",
        "Opcji {option} analizy {analysis} nie można zmienić; dozwolone: {allowed}",
    ),
    "analyses.option_value_invalid": Text(
        "Invalid value {value} of the option {option}: {reason}",
        "Niepoprawna wartość {value} opcji {option}: {reason}",
    ),
    "analyses.reason_integer": Text(
        "an integer is expected", "oczekiwano liczby całkowitej"
    ),
    "analyses.reason_number": Text("a number is expected", "oczekiwano liczby"),
    "analyses.reason_boolean": Text(
        "true or false is expected", "oczekiwano true albo false"
    ),
    "analyses.reason_enum": Text("allowed: {allowed}", "dozwolone: {allowed}"),
    "analyses.reason_array": Text(
        "a list of numbers is expected", "oczekiwano listy liczb"
    ),
    "analyses.reason_items": Text(
        "from {minimum} to {maximum} items are expected",
        "oczekiwano od {minimum} do {maximum} elementów",
    ),
    "analyses.reason_minimum": Text("at least {limit}", "co najmniej {limit}"),
    "analyses.reason_maximum": Text("at most {limit}", "co najwyżej {limit}"),
    "analyses.reason_exclusive_minimum": Text(
        "more than {limit}", "więcej niż {limit}"
    ),
    "analyses.reason_exclusive_maximum": Text("less than {limit}", "mniej niż {limit}"),
    # --- results ------------------------------------------------------------------------
    "analyses.dependency_without_result": Text(
        "The analysis {analysis} takes a number of another analysis, which gave none: "
        "{reason}",
        "Analiza {analysis} bierze liczbę z innej analizy, która jej nie dała: {reason}",
    ),
    "analyses.no_value": Text("no value", "brak wartości"),
    # --- Hydrolog's program -------------------------------------------------------------
    "analyses.hydrolog_exit": Text(
        "Hydrolog's program ended with the exit code {code}: {reason}",
        "Program Hydrolog zakończył się kodem {code}: {reason}",
    ),
    "analyses.hydrolog_line_count": Text(
        "Hydrolog's program wrote {lines} lines for {calls} calls",
        "Program Hydrolog zapisał {lines} wierszy dla {calls} wywołań",
    ),
}
