"""
Checks of the private API's parameters, before the data root or Hydrolog is touched.

Every parameter of a route is checked against the registries (station code patterns,
dataset keys, variables, ISO dates, the analyses and their options) and an unknown one
is refused (GUI plan D6, DEV-13.3): `GuiError` ``validation_error`` (400) naming the
option, its value and what is allowed.
"""

from __future__ import annotations

import math
import re
from collections.abc import Collection, Iterable, Mapping
from datetime import date

from obserwator.datasets import STATION_CODE_PATTERN
from obserwator.gui._http import GuiError
from obserwator.messages import message

_STATION = re.compile(STATION_CODE_PATTERN)
_YEAR = re.compile(r"-?[0-9]{1,4}")
_INTEGER = re.compile(r"-?[0-9]{1,9}")
_NUMBER = re.compile(r"-?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][-+]?[0-9]+)?")
_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
MAX_TEXT = 200
"""The longest value of a parameter, in characters."""


def invalid(option: str, value: object, reason: str, **details: object) -> GuiError:
    """The error of a parameter: its option, its value and why it is refused."""
    shown = value if not isinstance(value, str) else value[:MAX_TEXT]
    return GuiError(
        "validation_error",
        message("gui.errors.bad_parameter", option=option, value=shown),
        details={"option": option, "value": shown, "reason": reason, **details},
    )


def only(query: Mapping[str, str], allowed: Iterable[str]) -> None:
    """
    Refuse a parameter the route does not take, and a repeated one.

    Parameters
    ----------
    query : Mapping of str to str
        The query parameters (Starlette's ``QueryParams``).
    allowed : iterable of str
        The parameters of the route.

    Raises
    ------
    GuiError
        ``validation_error`` with ``reason`` ``unknown`` or ``repeated``.
    """
    names = set(allowed)
    keys = list(query.keys()) if hasattr(query, "keys") else list(query)
    multi = getattr(query, "multi_items", None)
    items = multi() if callable(multi) else [(key, query[key]) for key in keys]
    seen: set[str] = set()
    for key, value in items:
        if key not in names:
            raise invalid(key, value, "unknown", allowed=sorted(names))
        if key in seen:
            raise invalid(key, value, "repeated")
        seen.add(key)


def single(query: Mapping[str, str]) -> dict[str, str]:
    """
    The parameters as a dictionary, each given once.

    Parameters
    ----------
    query : Mapping of str to str
        The query parameters (Starlette's ``QueryParams``).

    Returns
    -------
    dict of str to str
        Every parameter with its value.

    Raises
    ------
    GuiError
        ``validation_error`` with ``reason`` ``repeated`` for a parameter given twice.
    """
    only(query, query.keys())
    return dict(query)


def station(value: str, option: str = "station") -> str:
    """A station code of either provider (``STATION_CODE_PATTERN``)."""
    if not _STATION.fullmatch(value):
        raise invalid(option, value, "pattern", pattern=STATION_CODE_PATTERN)
    return value


def choice(
    value: str | None, option: str, allowed: Collection[str], default: str | None = None
) -> str:
    """One of ``allowed``; ``default`` when the parameter is missing or empty."""
    if value is None or value == "":
        if default is None:
            raise invalid(option, value, "required", allowed=sorted(allowed))
        return default
    if value not in allowed:
        raise invalid(option, value, "allowed", allowed=list(allowed))
    return value


def integer(
    value: str | None,
    option: str,
    *,
    minimum: int | None = None,
    maximum: int | None = None,
    default: int | None = None,
) -> int | None:
    """An integer within the bounds; ``default`` when missing or empty."""
    if value is None or value == "":
        return default
    if not _INTEGER.fullmatch(value):
        raise invalid(option, value, "integer")
    number = int(value)
    if (minimum is not None and number < minimum) or (
        maximum is not None and number > maximum
    ):
        raise invalid(option, value, "range", minimum=minimum, maximum=maximum)
    return number


def year(value: str | None, option: str, default: int | None = None) -> int | None:
    """A year between 1700 and 2200; ``default`` when missing or empty."""
    if value is not None and value != "" and not _YEAR.fullmatch(value):
        raise invalid(option, value, "integer")
    return integer(value, option, minimum=1700, maximum=2200, default=default)


def number(
    value: str | None,
    option: str,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
    default: float | None = None,
) -> float | None:
    """A finite decimal number (a dot as the separator) within the bounds."""
    if value is None or value == "":
        return default
    if len(value) > 40 or not _NUMBER.fullmatch(value):
        raise invalid(option, value, "number")
    result = float(value)
    if not math.isfinite(result):
        raise invalid(option, value, "number")
    if (minimum is not None and result < minimum) or (
        maximum is not None and result > maximum
    ):
        raise invalid(option, value, "range", minimum=minimum, maximum=maximum)
    return result


def iso_date(value: str | None, option: str) -> date | None:
    """An ISO date ``YYYY-MM-DD``; None when missing or empty."""
    if value is None or value == "":
        return None
    if not _DATE.fullmatch(value):
        raise invalid(option, value, "date")
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise invalid(option, value, "date") from None


def names(
    value: str | None, option: str, allowed: Collection[str]
) -> tuple[str, ...] | None:
    """A comma-separated subset of ``allowed``, each once; None when missing or empty."""
    if value is None or value == "":
        return None
    chosen = tuple(dict.fromkeys(part.strip() for part in value.split(",")))
    wrong = [name for name in chosen if name not in allowed]
    if wrong or not all(chosen):
        raise invalid(option, value, "allowed", allowed=sorted(allowed))
    return chosen


def years(
    first: int | None, last: int | None, *, first_option: str, last_option: str
) -> None:
    """Refuse a range whose first year comes after its last."""
    if first is not None and last is not None and first > last:
        raise invalid(
            first_option, first, "range", maximum=last, option_after=last_option
        )
