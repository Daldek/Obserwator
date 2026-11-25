"""
Gdańskie Wody (pomiary.gdanskiewody.pl/rest) parsers: the station list and the month files.

Formats follow the live answers of 2026-11-20 and 2026-11-25 (ADR-034; the intake note
``docs/providers/gdanskiewody.md``):

- ``GET rest/stations`` — ``{"status": "success", "message": …, "data": [{"no": 1,
  "name": …, "lat": "54.33604", "long": "18.66171", "active": true, "rain": true,
  "water": false, …}]}``: the number of a station (1–999), its name, its point as
  texts in WGS84 (an empty text for none), whether it is active and one boolean per
  quantity it measures;
- ``GET rest/measurements/<no>/<symbol>/<YYYY-MM-DD>`` — ``{"status": "success",
  "message": …, "data": [["YYYY-MM-DD HH:MM:SS", value], …]}``: the 24 hourly values
  of the provider's day D, labelled from 06:00 of D to 05:00 of D+1 in UTC, a missing
  hour ``null``; a date before a station's record or after today gives 24 ``null``;
- an error is HTTP 200 too: ``{"status": "error", "code": N, "message": …}``.

The store keeps one file per station, quantity and calendar month (``archive_scope``
``station_element_month``, plan P6): the answers of the month's days, keyed by date
(``YYYY-MM-DD``), in canonical JSON (`encode_month`, `read_month`). The station code of
the store is ``GDANSKIEWODY-<no>`` (`station_code`): ADR-033's prefixed form, since the
bare numbers belong to PIG-PIB's points.

The daily value of the provider's day (plan P5; `daily_records`) is the sum of the 24
hourly values of ``P`` (precipitation) and the mean of the 24 of every other quantity
with a daily variable, rounded to three decimals; a day without all 24 values has none
(``missing``). Parsing is strict: every content error raises `ObserwatorDataError`
naming the file and the place.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any, Literal

from obserwator.datasets import Kind
from obserwator.exceptions import ObserwatorDataError
from obserwator.messages import message
from obserwator.models import Measurement, NormalizedRecord, StationListEntry

__all__ = [
    "CODE_PREFIX",
    "PROVIDER",
    "QUANTITIES",
    "GdanskieWodyStation",
    "Quantity",
    "daily_records",
    "day_points",
    "encode_month",
    "hour_start",
    "hourly_points",
    "parse_gdanskiewody_month",
    "parse_gdanskiewody_stations",
    "quantity",
    "read_month",
    "read_stations",
    "station_code",
    "station_number",
]

PROVIDER = "GDANSKIEWODY"
"""The provider's identifier (ADR-034)."""
CODE_PREFIX = f"{PROVIDER}-"
"""The prefix of its station codes: ADR-033's ``<ID>-<code>``."""
_STATION_NUMBER = re.compile(r"[1-9][0-9]{0,2}")
_MONTH_FILE = re.compile(r"([0-9]{4})-(0[1-9]|1[0-2])\.json")
_LABEL = re.compile(r"([0-9]{4}-[0-9]{2}-[0-9]{2}) ([0-9]{2}):00:00")
_ROUND = 3
"""Decimals of a daily value: a sum or a mean of hourly values (`daily_records`)."""
_HOURS = 24
"""The hours of the provider's day, 06:00 to 05:00 UTC."""
_DAY_START = 6
"""The UTC hour of the first label of the provider's day."""


@dataclass(frozen=True)
class Quantity:
    """
    A quantity of the API and what Obserwator makes of it (ADR-034 D3).

    Attributes
    ----------
    symbol : str
        The API's name, the ``<symbol>`` of a measurement's address.
    kind : {"hydro", "meteo"}
        The family of the stations that measure it.
    hourly : str or None
        Its variable in the hourly series; None for a quantity stored only (the
        water-quality quantities, ADR-034 D3).
    daily : str or None
        Its variable in the daily series; None for no daily value (a direction, a
        quantity stored only).
    unit : str or None
        Its unit, as the provider's public tables label it (checked 2026-11-25).
    statistic : {"sum", "mean"} or None
        How the 24 hours of the provider's day give its daily value.
    """

    symbol: str
    kind: Kind
    hourly: str | None
    daily: str | None
    unit: str | None
    statistic: Literal["sum", "mean"] | None


QUANTITIES: tuple[Quantity, ...] = (
    Quantity("rain", "meteo", "P", "P", "mm", "sum"),
    Quantity("water", "hydro", "H_asl", "H_asl", "m", "mean"),
    Quantity("flow", "hydro", "Q", "Q", "m3/s", "mean"),
    Quantity("winddir", "meteo", "wind_direction", None, "deg", None),
    Quantity("windlevel", "meteo", "wind_speed", "wind_speed", "m/s", "mean"),
    Quantity("temp", "meteo", "Tair", "Tmean", "degC", "mean"),
    Quantity("pressure", "meteo", "pressure", "pressure", "hPa", "mean"),
    Quantity("humidity", "meteo", "humidity", "humidity", "%", "mean"),
    Quantity("sun", "meteo", "irradiance", "irradiance", "W/m2", "mean"),
    Quantity("turbidity", "hydro", None, None, "FNU", None),
    Quantity("dissolvedoxygen", "hydro", None, None, "mg/l", None),
    Quantity("redox", "hydro", None, None, "mV", None),
    Quantity("ph", "hydro", None, None, None, None),
    Quantity("conductivity", "hydro", None, None, None, None),
    Quantity("watertemp", "hydro", "T", "T", "degC", "mean"),
)
"""Every quantity of the station list, in its order."""
_BY_SYMBOL: Mapping[str, Quantity] = {item.symbol: item for item in QUANTITIES}
_RANK: Mapping[str, int] = {item.symbol: rank for rank, item in enumerate(QUANTITIES)}
"""The place of each symbol in `QUANTITIES`, the order of a station's quantities."""


def quantity(symbol: str, /) -> Quantity | None:
    """
    The quantity of an API symbol.

    Parameters
    ----------
    symbol : str
        A ``<symbol>`` of the API, e.g. ``"rain"``.

    Returns
    -------
    Quantity or None
        None for a symbol the station list of 2026-11-25 does not name.
    """
    return _BY_SYMBOL.get(symbol)


def station_code(number: int, /) -> str:
    """
    The store's code of a station number: ``GDANSKIEWODY-<no>``.

    Parameters
    ----------
    number : int
        The ``no`` of the station list, 1 to 999.

    Returns
    -------
    str
        The code, e.g. ``"GDANSKIEWODY-7"``.
    """
    return f"{CODE_PREFIX}{number}"


def station_number(code: str, /) -> str:
    """
    The API's number of a station code, as the measurement addresses take it.

    Parameters
    ----------
    code : str
        A code ``GDANSKIEWODY-<no>`` of the registry's ``station_code_pattern``.

    Returns
    -------
    str
        The number as text, e.g. ``"7"``.

    Raises
    ------
    ValueError
        If ``code`` is no station code of the provider.
    """
    number = code.removeprefix(CODE_PREFIX)
    if number == code or not _STATION_NUMBER.fullmatch(number):
        raise ValueError(f"{code!r} is no station code of {PROVIDER}")
    return number


@dataclass(frozen=True)
class GdanskieWodyStation:
    """
    A station of the provider's list (``GET rest/stations``).

    Attributes
    ----------
    number : int
        Its ``no``, 1 to 999.
    code : str
        Its code in the store, ``GDANSKIEWODY-<no>``.
    name : str
        Its name as published.
    latitude, longitude : str or None
        Its point as published (WGS84, texts, e.g. ``"54.33604"``); None when the list
        gives an empty text.
    active : bool
        Whether the list says it is active.
    quantities : tuple of str
        The symbols it measures, in the order of `QUANTITIES` (then any unknown
        symbol the list names, in its order).
    kind : {"hydro", "meteo"}
        ``hydro`` when it measures any hydrological quantity (the water level, the
        flow, the water's temperature or quality), else ``meteo``.
    """

    number: int
    code: str
    name: str
    latitude: str | None
    longitude: str | None
    active: bool
    quantities: tuple[str, ...]
    kind: Kind


def _fail(filename: str, where: str, problem: str) -> ObserwatorDataError:
    return ObserwatorDataError(
        message(
            "parsing.gdanskiewody_bad_content",
            filename=filename,
            where=where,
            problem=problem,
        )
    )


def _json(content: bytes | str, filename: str) -> Any:
    try:
        return json.loads(content)
    except (ValueError, RecursionError) as exc:
        raise _fail(filename, "$", message("parsing.gdanskiewody_not_json")) from exc


def _success(payload: Any, filename: str) -> list[Any]:
    """The ``data`` list of a successful answer."""
    if not isinstance(payload, dict):
        raise _fail(filename, "$", message("parsing.gdanskiewody_not_json_object"))
    if payload.get("status") != "success":
        raise _fail(
            filename,
            "$.status",
            message("parsing.gdanskiewody_not_success", status=payload.get("status")),
        )
    data = payload.get("data")
    if not isinstance(data, list):
        raise _fail(filename, "$.data", message("parsing.gdanskiewody_not_json_list"))
    return data


def _point(value: object, filename: str, where: str) -> str | None:
    """A coordinate as published: a decimal text, None for an empty one."""
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise _fail(filename, where, message("parsing.gdanskiewody_not_text"))
    try:
        number = float(value)
    except ValueError as exc:
        raise _fail(
            filename, where, message("parsing.gdanskiewody_not_number")
        ) from exc
    if not math.isfinite(number):
        raise _fail(filename, where, message("parsing.gdanskiewody_not_number"))
    return value.strip()


def read_stations(
    content: bytes | str, /, *, filename: str = "stations"
) -> tuple[GdanskieWodyStation, ...]:
    """
    The stations of the provider's list (``GET rest/stations``), in its order.

    Parameters
    ----------
    content : bytes or str
        The answer as it came.
    filename : str, optional
        Its name or address, for errors.

    Returns
    -------
    tuple of GdanskieWodyStation
        One per station; a number given twice keeps its first row.

    Raises
    ------
    ObserwatorDataError
        If the answer is no successful list of stations: no JSON, an error answer, a
        station without a number of 1 to 999, a name, an ``active`` flag or boolean
        quantities, or a point that is no number.
    """
    rows = _success(_json(content, filename), filename)
    found: dict[int, GdanskieWodyStation] = {}
    for index, row in enumerate(rows):
        where = f"$.data[{index}]"
        if not isinstance(row, dict):
            raise _fail(
                filename, where, message("parsing.gdanskiewody_not_json_object")
            )
        number = row.get("no")
        if isinstance(number, bool) or not isinstance(number, int):
            raise _fail(
                filename, f"{where}.no", message("parsing.gdanskiewody_not_integer")
            )
        if not 1 <= number <= 999:
            raise _fail(
                filename,
                f"{where}.no",
                message("parsing.gdanskiewody_bad_number", number=number),
            )
        name = row.get("name")
        if not isinstance(name, str) or not name.strip():
            raise _fail(
                filename, f"{where}.name", message("parsing.gdanskiewody_not_text")
            )
        active = row.get("active")
        if not isinstance(active, bool):
            raise _fail(
                filename, f"{where}.active", message("parsing.gdanskiewody_not_boolean")
            )
        symbols: list[str] = []
        for key, value in row.items():
            if key in ("no", "name", "lat", "long", "active"):
                continue
            if not isinstance(value, bool):
                raise _fail(
                    filename,
                    f"{where}.{key}",
                    message("parsing.gdanskiewody_not_boolean"),
                )
            if value:
                symbols.append(key)
        symbols.sort(key=lambda symbol: _RANK.get(symbol, len(_RANK)))
        hydro = any(
            item is not None and item.kind == "hydro"
            for item in (quantity(symbol) for symbol in symbols)
        )
        latitude = _point(row.get("lat"), filename, f"{where}.lat")
        longitude = _point(row.get("long"), filename, f"{where}.long")
        if number in found:
            continue
        found[number] = GdanskieWodyStation(
            number=number,
            code=station_code(number),
            name=name.strip(),
            latitude=latitude,
            longitude=longitude,
            active=active,
            quantities=tuple(symbols),
            kind="hydro" if hydro else "meteo",
        )
    return tuple(found.values())


def parse_gdanskiewody_stations(
    content: bytes | str, /, *, filename: str = "stations"
) -> list[StationListEntry]:
    """
    Parse Gdańskie Wody's station list into station list entries (ADR-034).

    The answer of ``GET https://pomiary.gdanskiewody.pl/rest/stations`` (an API key
    is needed to ask it): the code ``GDANSKIEWODY-<no>``, the name and the point as
    published, the family by what the station measures (``hydro`` with any
    hydrological quantity, else ``meteo``). No river or hydrographic code is
    published.

    Parameters
    ----------
    content : bytes or str
        The answer as it came.
    filename : str, optional
        Its name or address, for errors.

    Returns
    -------
    list of StationListEntry
        One per station, in the list's order.

    Raises
    ------
    ObserwatorDataError
        If the answer is no successful list of stations (`read_stations`).

    Examples
    --------
    >>> from obserwator.parsers import parse_gdanskiewody_stations
    >>> rows = parse_gdanskiewody_stations(content)
    >>> rows[0].station_code
    'GDANSKIEWODY-1'
    """
    return [
        StationListEntry(
            kind=station.kind,
            station_code=station.code,
            name=station.name,
            latitude=None if station.latitude is None else float(station.latitude),
            longitude=None if station.longitude is None else float(station.longitude),
            provider=PROVIDER,
        )
        for station in read_stations(content, filename=filename)
    ]


# --- the month files -------------------------------------------------------------------


def hour_start(label: datetime, /) -> datetime:
    """
    The UTC start of the hour an API label names (plan P5; ADR-034 D4).

    The API labels an hour by its start: the 24 labels of the provider's day D run
    from 06:00 of D to 05:00 of D+1, the daily total of the provider's public
    tables is their sum, and a label of a closed hour is never later than now.

    Parameters
    ----------
    label : datetime
        The label as UTC.

    Returns
    -------
    datetime
        The start of its hour.
    """
    return label


def _label(text: object, filename: str, where: str) -> datetime:
    """An hour's label ``YYYY-MM-DD HH:00:00`` as a UTC time."""
    found = _LABEL.fullmatch(text) if isinstance(text, str) else None
    if found is None:
        raise _fail(filename, where, message("parsing.gdanskiewody_bad_label"))
    try:
        day = date.fromisoformat(found[1])
    except ValueError as exc:
        raise _fail(filename, where, message("parsing.gdanskiewody_bad_label")) from exc
    hour = int(found[2])
    if hour > 23:
        raise _fail(filename, where, message("parsing.gdanskiewody_bad_label"))
    return datetime(day.year, day.month, day.day, hour, tzinfo=UTC)


def _value(raw: object, filename: str, where: str) -> float | None:
    """An hour's value: a finite number, None for ``null``."""
    if raw is None:
        return None
    if isinstance(raw, bool) or not isinstance(raw, int | float):
        raise _fail(filename, where, message("parsing.gdanskiewody_not_number"))
    number = float(raw)
    if not math.isfinite(number):
        raise _fail(filename, where, message("parsing.gdanskiewody_not_number"))
    return number


def day_points(
    answer: object, day: date, /, *, filename: str
) -> list[tuple[datetime, float | None]]:
    """
    The hours of one day's answer: each label as UTC and its value.

    Parameters
    ----------
    answer : object
        One successful answer of ``rest/measurements/<no>/<symbol>/<day>``.
    day : datetime.date
        The provider's day it was asked for.
    filename : str
        Its file, for errors.

    Returns
    -------
    list of (datetime, float or None)
        In the answer's order, each hour once.

    Raises
    ------
    ObserwatorDataError
        If the answer is no successful list of ``[label, value]`` pairs, or a label
        lies outside the provider's day (06:00 of ``day`` to 05:00 of the next) or
        comes twice.
    """
    rows = _success(answer, filename)
    first = datetime(day.year, day.month, day.day, _DAY_START, tzinfo=UTC)
    last = first + timedelta(hours=_HOURS - 1)
    points: list[tuple[datetime, float | None]] = []
    seen: set[datetime] = set()
    for index, row in enumerate(rows):
        where = f"$.{day.isoformat()}.data[{index}]"
        if not isinstance(row, list) or len(row) != 2:
            raise _fail(filename, where, message("parsing.gdanskiewody_bad_pair"))
        moment = _label(row[0], filename, f"{where}[0]")
        if not first <= moment <= last:
            raise _fail(
                filename,
                f"{where}[0]",
                message("parsing.gdanskiewody_label_outside_day", day=day),
            )
        if moment in seen:
            raise _fail(
                filename, f"{where}[0]", message("parsing.gdanskiewody_label_twice")
            )
        seen.add(moment)
        points.append((moment, _value(row[1], filename, f"{where}[1]")))
    return points


def encode_month(answers: Mapping[date, object], /) -> bytes:
    """
    The file of a station's quantity and month: its days' answers in canonical JSON.

    Parameters
    ----------
    answers : Mapping of datetime.date to object
        The answer of each day, as JSON values.

    Returns
    -------
    bytes
        ``{"YYYY-MM-DD": <answer>, …}`` with sorted keys, no white space, UTF-8 and a
        final line feed: the same answers always give the same bytes.
    """
    document = {day.isoformat(): answer for day, answer in answers.items()}
    text = json.dumps(
        document, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )
    return (text + "\n").encode("utf-8")


def read_month(
    content: bytes, /, *, filename: str, period: tuple[date, date] | None = None
) -> dict[date, object]:
    """
    The answers of a month file, by day (the reverse of `encode_month`).

    Parameters
    ----------
    content : bytes
        The stored file.
    filename : str
        Its name, for errors.
    period : tuple of datetime.date, optional
        The first and last day the file may hold (its month); None takes any day.

    Returns
    -------
    dict of datetime.date to object
        Each day's answer, in date order.

    Raises
    ------
    ObserwatorDataError
        If the file is no JSON object keyed by ISO dates, or a day lies outside
        ``period``.
    """
    document = _json(content, filename)
    if not isinstance(document, dict):
        raise _fail(filename, "$", message("parsing.gdanskiewody_not_json_object"))
    answers: dict[date, object] = {}
    for key in sorted(document):
        try:
            day = date.fromisoformat(key)
        except ValueError as exc:
            raise _fail(
                filename, f"$.{key}", message("parsing.gdanskiewody_not_date")
            ) from exc
        if day.isoformat() != key:
            raise _fail(filename, f"$.{key}", message("parsing.gdanskiewody_not_date"))
        if period is not None and not period[0] <= day <= period[1]:
            raise _fail(
                filename,
                f"$.{key}",
                message(
                    "parsing.gdanskiewody_day_outside_file",
                    first=period[0],
                    last=period[1],
                ),
            )
        answers[day] = document[key]
    return answers


def hourly_points(
    content: bytes, /, *, filename: str, period: tuple[date, date] | None = None
) -> list[tuple[datetime, float | None]]:
    """
    Every hour of a month file: the UTC start of the hour (`hour_start`) and its value.

    Parameters
    ----------
    content : bytes
        A stored month file (`encode_month`).
    filename : str
        Its name, for errors.
    period : tuple of datetime.date, optional
        The first and last day the file may hold (`read_month`).

    Returns
    -------
    list of (datetime, float or None)
        In time order; the days of a file share no hour (`day_points`).

    Raises
    ------
    ObserwatorDataError
        If the file or an answer cannot be read (`read_month`, `day_points`).
    """
    points = [
        (hour_start(label), value)
        for day, answer in read_month(content, filename=filename, period=period).items()
        for label, value in day_points(answer, day, filename=filename)
    ]
    return sorted(points, key=lambda point: point[0])


def _hydro_year(day: date) -> int:
    """The hydrological year (November to October) of a day."""
    return day.year + 1 if day.month >= 11 else day.year


def daily_records(
    content: bytes,
    /,
    *,
    dataset: str,
    station: str,
    symbol: str,
    filename: str,
    period: tuple[date, date] | None = None,
) -> Iterator[NormalizedRecord]:
    """
    The daily value of each provider's day of a month file (plan P5; ADR-034 D5).

    The provider's day D holds the 24 hours labelled 06:00 of D to 05:00 of D+1
    (UTC): its daily value is the sum of the 24 values of a quantity summed
    (``P``), the mean of the 24 of any other with a daily variable, rounded to three
    decimals. A day without all 24 values has no value (``missing``); a quantity
    without a daily variable gives no record.

    Parameters
    ----------
    content : bytes
        A stored month file (`encode_month`).
    dataset : str
        The key of the records (the file's dataset).
    station : str
        The file's station code, ``GDANSKIEWODY-<no>``.
    symbol : str
        The file's quantity.
    filename : str
        Its name, for errors.
    period : tuple of datetime.date, optional
        The first and last day the file may hold (`read_month`).

    Yields
    ------
    NormalizedRecord
        One per day of the file, in date order, with the daily variable of the
        quantity.

    Raises
    ------
    ObserwatorDataError
        If the file or an answer cannot be read (`read_month`, `day_points`).
    """
    found = quantity(symbol)
    if found is None or found.daily is None or found.statistic is None:
        return
    for day, answer in read_month(content, filename=filename, period=period).items():
        values = [value for _, value in day_points(answer, day, filename=filename)]
        complete = len(values) == _HOURS and all(value is not None for value in values)
        measurement = Measurement(None, "missing")
        if complete:
            numbers = [value for value in values if value is not None]
            total = math.fsum(numbers)
            result = total if found.statistic == "sum" else total / len(numbers)
            measurement = Measurement(round(result, _ROUND) + 0.0, "value")
        yield NormalizedRecord(
            station_code=station,
            dataset=dataset,
            date=day,
            hydro_year=_hydro_year(day),
            period=None,
            measurements={found.daily: measurement},
        )


def parse_gdanskiewody_month(
    content: bytes, /, *, filename: str, dataset: str = "pl.gdanskiewody.measurements"
) -> Iterator[NormalizedRecord]:
    """
    Parse a stored month file of Gdańskie Wody into daily records (ADR-034).

    The file of one station, quantity and calendar month,
    ``rest/measurements/<no>/<symbol>/<YYYY-MM>.json`` of the raw root: the answers
    of the month's days. Each provider's day (06:00 to 05:59 UTC) gives its daily
    value (`daily_records`): the sum of the 24 hours of precipitation, the mean of the
    24 of the other quantities, ``missing`` without all 24.

    Parameters
    ----------
    content : bytes
        The stored file.
    filename : str
        Its server path ``rest/measurements/<no>/<symbol>/<YYYY-MM>.json``: the
        station, the quantity and the month come from it.
    dataset : str, optional
        The dataset key of the records.

    Yields
    ------
    NormalizedRecord
        One per day, in date order.

    Raises
    ------
    ObserwatorDataError
        If the name or the content is no month file of the provider, or the file
        holds a day of another month.

    Examples
    --------
    >>> from obserwator.parsers import parse_gdanskiewody_month
    >>> name = "rest/measurements/1/rain/2026-11.json"
    >>> [r.measurements["P"].value for r in parse_gdanskiewody_month(data, filename=name)]
    """
    parts = filename.split("/")
    month = _MONTH_FILE.fullmatch(parts[-1])
    if len(parts) < 3 or month is None or not _STATION_NUMBER.fullmatch(parts[-3]):
        raise _fail(filename, "$", message("parsing.gdanskiewody_bad_name"))
    year, number = int(month[1]), int(month[2])
    following = date(year + number // 12, number % 12 + 1, 1)
    yield from daily_records(
        content,
        dataset=dataset,
        station=station_code(int(parts[-3])),
        symbol=parts[-2],
        filename=filename,
        period=(date(year, number, 1), following - timedelta(days=1)),
    )
