"""
PIG-PIB's groundwater monitoring: the points, the readings and the automatic measurements.

Formats follow the answers of cbdgmapa.pgi.gov.pl's ArcGIS services recorded on
2026-11-24 (ADR-035; the intake note ``docs/providers/pig.md``):

- a query page ``{"features": [{"attributes": {…}, "geometry": {"x": …, "y": …}}],
  "exceededTransferLimit": true}``, a count ``{"count": N}``, an error HTTP 200
  ``{"error": {"code": …, "message": …}}``;
- the points ``hydrogeologia/mwp/MapServer/0`` (asked with ``outSR=4326``): one feature
  per point, ``ID`` its only identifier, the type of the point (``RODZAJ_OTWORU``), the
  ground elevation (``RZEDNA_TERENU`` [m n.p.m.], null at 600 points), whether it is
  observed now (``AKTUALNIE_OBSERWOWANY`` „Tak” or „Nie”, or null) and its
  hydrogeological description;
- the readings ``hydrogeologia/mwp/MapServer/1``: ``OTWOR_ID`` (a point's ``ID``),
  ``DATA_POMIARU`` (a text with a leading space, „ 2026-10-01”), the depth to water
  ``GLEBOKOSC_ZWIERCIADLA`` [m p.p.t., negative above the ground] or a spring's yield
  ``WYDAJNOSC`` [l/s]: the reading of 06:00 UTC of one point and day;
- the automatic measurements ``hydrogeologia/mwp_auto/MapServer/2``:
  ``PSH_MONITORING_ID`` (a point's ``ID``), ``TIME``, ``VALUE`` [m, the depth below the
  ground] and ``OBJECTID`` in the order of loading.

A stored version of an ``mwp`` dataset, and every capture of ``mwp_auto``, is
Obserwator's container of answers (gzip-compressed JSON Lines, ADR-030 D3 erratum):
`pages` reads it. The time of ``mwp_auto`` (W9 of the plan): the service stores UTC
wall-clock times, 1 to 6 s past the hour, and answers them as epochs converted as if
they were Europe/Warsaw's; `stored_hour` takes an epoch back to that wall time, reads
it as UTC and floors it to the hour. On the day summer time starts the stored 01:00 and
02:00 come back as one epoch: only a page asking the stored hour 02 by a clause of its
own (`DST_CLAUSE`) tells them apart (`auto_hours`). Parsing is strict: a content error
raises `ObserwatorDataError` naming the file and the place.
"""

from __future__ import annotations

import base64
import binascii
import gzip
import hashlib
import json
import math
import re
import zlib
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any, Literal
from urllib.parse import parse_qsl, urlsplit
from zoneinfo import ZoneInfo

from obserwator.exceptions import ObserwatorDataError
from obserwator.messages import message
from obserwator.models import Measurement, NormalizedRecord, StationListEntry

__all__ = [
    "DST_CLAUSE",
    "PROVIDER",
    "AutoHours",
    "Page",
    "PigPoint",
    "Reading",
    "auto_hours",
    "automatic_points",
    "dst_start",
    "level",
    "pages",
    "parse_pig_readings",
    "parse_pig_stations",
    "read_points",
    "read_readings",
    "readings_period",
    "stored_hour",
    "years",
]

PROVIDER = "PIG"
"""The provider's identifier (ADR-035)."""
WARSAW = ZoneInfo("Europe/Warsaw")
"""The zone by which ``mwp_auto`` converts its stored times to epochs."""
DST_CLAUSE = "TIME >= TIMESTAMP '{day} 02:00:00' AND TIME < TIMESTAMP '{day} 03:00:00'"
"""
The ``where`` of the page of a summer-time start day's stored hour 02 (W9).

A where clause compares the stored times unconverted, so this page holds exactly the
rows stored at 02:00 of the day, whose epochs equal those of the stored 01:00.
"""
_DST_WHERE = re.compile(
    r"TIME >= TIMESTAMP '([0-9]{4}-[0-9]{2}-[0-9]{2}) 02:00:00' AND "
    r"TIME < TIMESTAMP '\1 03:00:00'"
)
_SPRING = "źródło"
_ACTIVE: Mapping[str, bool] = {"Tak": True, "Nie": False}
_BLANK = frozenset({"", "__"})
_DAY = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
_YEAR = re.compile(r"[12][0-9]{3}")
_CENTIMETRE = 2
"""Decimals of a derived level: the depth's centimetre (W7, W8)."""


def _fail(filename: str, where: str, problem: str) -> ObserwatorDataError:
    return ObserwatorDataError(
        message("parsing.pig_invalid", filename=filename, where=where, problem=problem)
    )


# --- the container of answers ------------------------------------------------------


@dataclass(frozen=True)
class Page:
    """
    One answer of a capture of PIG-PIB's services.

    Attributes
    ----------
    time : str
        When it came (UTC, ``YYYY-MM-DDTHH:MM:SS.ffffffZ``).
    address : str
        The address asked; of a POST, its URL with the form as the query.
    status : int
        Its HTTP status.
    payload : Any
        Its body as JSON; None when the body is no JSON.
    """

    time: str
    address: str
    status: int
    payload: Any

    @property
    def layer(self) -> str:
        """``<service>/<layer>`` of the address: ``mwp/0``, ``mwp/1``, ``mwp_auto/2``."""
        parts = urlsplit(self.address).path.rstrip("/").split("/")
        return f"{parts[-4]}/{parts[-2]}" if len(parts) >= 4 else ""

    @property
    def form(self) -> dict[str, str]:
        """The parameters of the query (its form or query string)."""
        return dict(parse_qsl(urlsplit(self.address).query, keep_blank_values=True))

    @property
    def received(self) -> datetime:
        """`time` as an aware UTC instant."""
        return datetime.strptime(self.time, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=UTC)

    @property
    def features(self) -> list[Any] | None:
        """The rows of a page answered 200; None for any other answer."""
        if self.status != 200 or not isinstance(self.payload, dict):
            return None
        found = self.payload.get("features")
        return found if isinstance(found, list) else None


def pages(data: bytes, /, *, filename: str) -> list[Page]:
    """
    The answers of a capture (gzip-compressed JSON Lines, ADR-030 D3), in file order.

    A ``seen`` line repeats the answer before it from its address.

    Parameters
    ----------
    data : bytes
        The stored file.
    filename : str
        Its name, for errors.

    Returns
    -------
    list of Page
        Every answer with its body read as JSON (None for no JSON).

    Raises
    ------
    ObserwatorDataError
        If the file is no such container or a body does not match its SHA-256.
    """
    try:
        text = gzip.decompress(data).decode("utf-8")
    except (OSError, EOFError, UnicodeDecodeError, zlib.error) as exc:
        raise _fail(filename, "gzip", str(exc)) from exc
    found: list[Page] = []
    previous: dict[str, bytes] = {}
    for number, line in enumerate(text.split("\n"), start=1):
        if not line:
            continue
        where = message("parsing.pig_line", number=number)
        try:
            record = json.loads(line)
        except ValueError as exc:
            raise _fail(filename, where, str(exc)) from exc
        if not isinstance(record, dict):
            raise _fail(filename, where, message("parsing.pig_not_object"))
        address, status, sha = (
            record.get("address"),
            record.get("status"),
            record.get("sha256"),
        )
        if (
            not isinstance(address, str)
            or not isinstance(status, int)
            or not isinstance(record.get("time"), str)
        ):
            raise _fail(filename, where, message("parsing.pig_not_object"))
        if record.get("seen") is True:
            body = previous.get(address)
            if body is None:
                raise _fail(filename, where, message("parsing.pig_seen_alone"))
        elif isinstance(record.get("body"), str):
            body = record["body"].encode("utf-8")
        elif isinstance(record.get("body_base64"), str):
            try:
                body = base64.b64decode(record["body_base64"], validate=True)
            except binascii.Error as exc:
                raise _fail(filename, where, str(exc)) from exc
        else:
            raise _fail(filename, where, message("parsing.pig_not_object"))
        if hashlib.sha256(body).hexdigest() != sha:
            raise _fail(filename, where, message("parsing.pig_body_sha"))
        previous[address] = body
        try:
            payload = json.loads(body)
        except ValueError:
            payload = None
        found.append(Page(record["time"], address, status, payload))
    return found


def _attributes(feature: object, filename: str, where: str) -> Mapping[str, Any]:
    attributes = feature.get("attributes") if isinstance(feature, dict) else None
    if not isinstance(attributes, dict):
        raise _fail(filename, where, message("parsing.pig_no_attributes"))
    return attributes


def _number(value: object, filename: str, where: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise _fail(filename, where, message("parsing.pig_not_number", value=value))
    number = float(value)
    if not math.isfinite(number):
        raise _fail(filename, where, message("parsing.pig_not_number", value=value))
    return number


def _text(value: object) -> str | None:
    """A text as published, None for a blank one (PSH's empty number is „__”)."""
    if value is None:
        return None
    text = str(value).strip()
    return None if text in _BLANK else text


def _year(value: object) -> int | None:
    text = _text(value)
    return int(text) if text is not None and _YEAR.fullmatch(text) else None


# --- the points --------------------------------------------------------------------


@dataclass(frozen=True)
class PigPoint:
    """
    One point of PIG-PIB's monitoring (the points layer, W6).

    Attributes
    ----------
    code : str
        ``ID`` as text, the station code (``^[1-9][0-9]{0,5}$``).
    name : str
        The locality (``MIEJSCOWOSC``); empty when none is published.
    groundwater_kind : {"bore", "spring"}
        ``spring`` for the type „źródło”, ``bore`` for every other type, a blank one
        included.
    active : bool or None
        Whether it is observed now: „Tak” True, „Nie” False, null None.
    elevation_m : float or None
        The ground elevation (``RZEDNA_TERENU``, m n.p.m.; no datum named).
    longitude, latitude : float or None
        The point of the answer's geometry (``outSR=4326``), never the PL-1992
        coordinates of the attributes.
    established_year : int or None
        The year the point was built (``ROK_BUDOWY``).
    cbdh : str or None
        CBDH's number of the point (``NUMER_CBDH``).
    hydrogeology : Mapping of str to object
        The hydrogeological description as published, without nulls.
    """

    code: str
    name: str
    groundwater_kind: Literal["bore", "spring"]
    active: bool | None
    elevation_m: float | None
    longitude: float | None
    latitude: float | None
    established_year: int | None
    cbdh: str | None
    hydrogeology: Mapping[str, object] = field(default_factory=dict)


# The attributes of the hydrogeological description (W6), by their key in it: texts,
# depths in metres and years, as published.
_HYDRO_TEXTS = (
    ("point_type", "RODZAJ_OTWORU"),
    ("confinement", "CHARAKTER_PUNKTU"),
    ("stratigraphy", "CHRONO"),
    ("lithology", "LITOLOGIA"),
    ("medium", "TYP_OSRODKA"),
    ("psh_number", "NR_PKT_MONIT_ILOSC"),
    ("cbdh_number", "NUMER_CBDH"),
    ("eu_code", "IDENT_EU"),
    ("research_number", "NR_MONIT_BAD"),
    ("research_monitoring", "TYP_MONITORINGU_BAD"),
    ("border_number", "NR_PKT_MON_GRAN"),
    ("pressure_number", "NR_PKT_MON_BAD"),
    ("chemical_analyses", "ANALIZY_CHEMICZNE"),
    ("voivodeship", "WOJEWODZTWO"),
    ("county", "POWIAT"),
    ("commune", "GMINA"),
)
_HYDRO_DEPTHS = (
    ("bore_depth_m", "GLEBOKOSC_OTWORU"),
    ("final_depth_m", "GLEB_OST_OTWORU"),
    ("water_struck_m", "ZWIERCIADLO_NAW"),
    ("water_rest_m", "ZWIERCIADLO_SWOBODNE"),
    ("screen_top_m", "GLEBOKOSC_W_OD"),
    ("screen_bottom_m", "GLEBOKOSC_W_DO"),
)
_HYDRO_YEARS = (
    ("observed_from", "ROK_ROZP_OBSERWACJI"),
    ("observed_to", "ROK_ZAK_OBSERWACJI"),
)


def _point(feature: object, filename: str, where: str) -> PigPoint:
    attributes = _attributes(feature, filename, where)
    code = attributes.get("ID")
    if isinstance(code, bool) or not isinstance(code, int) or code < 1:
        raise _fail(filename, where, message("parsing.pig_no_id"))
    point_type = _text(attributes.get("RODZAJ_OTWORU"))
    observed = _text(attributes.get("AKTUALNIE_OBSERWOWANY"))
    geometry = feature.get("geometry") if isinstance(feature, dict) else None
    longitude = latitude = None
    if isinstance(geometry, dict):
        longitude = _number(geometry.get("x"), filename, where)
        latitude = _number(geometry.get("y"), filename, where)
    hydrogeology: dict[str, object] = {}
    for key, name in _HYDRO_TEXTS:
        if (text := _text(attributes.get(name))) is not None:
            hydrogeology[key] = text
    chemical = _number(attributes.get("NR_MONIT_STANU_CHEM"), filename, where)
    if chemical is not None:
        hydrogeology["chemical_number"] = (
            int(chemical) if chemical.is_integer() else chemical
        )
    for key, name in _HYDRO_DEPTHS:
        if (depth := _number(attributes.get(name), filename, where)) is not None:
            hydrogeology[key] = depth
    for key, name in _HYDRO_YEARS:
        if (year := _year(attributes.get(name))) is not None:
            hydrogeology[key] = year
    body = attributes.get("JCWPD_174")
    if isinstance(body, int) and not isinstance(body, bool):
        hydrogeology["jcwpd"] = body
    return PigPoint(
        code=str(code),
        name=_text(attributes.get("MIEJSCOWOSC")) or "",
        groundwater_kind="spring" if point_type == _SPRING else "bore",
        active=None if observed is None else _ACTIVE.get(observed),
        elevation_m=_number(attributes.get("RZEDNA_TERENU"), filename, where),
        longitude=longitude,
        latitude=latitude,
        established_year=_year(attributes.get("ROK_BUDOWY")),
        cbdh=_text(attributes.get("NUMER_CBDH")),
        hydrogeology=hydrogeology,
    )


def read_points(data: bytes, /, *, filename: str) -> tuple[PigPoint, ...]:
    """
    The points of a stored version of ``pl.pig.groundwater_stations``, by ``ID``.

    Parameters
    ----------
    data : bytes
        The capture of the points layer's pages.
    filename : str
        Its name, for errors.

    Returns
    -------
    tuple of PigPoint
        Every point once, in the order of their codes' numbers.

    Raises
    ------
    ObserwatorDataError
        If the capture or a row cannot be read, or an ``ID`` repeats with other
        attributes.
    """
    found: dict[str, PigPoint] = {}
    for page in pages(data, filename=filename):
        for index, feature in enumerate(page.features or (), start=1):
            where = message("parsing.pig_row", address=page.address, number=index)
            point = _point(feature, filename, where)
            known = found.get(point.code)
            if known is not None and known != point:
                raise _fail(filename, where, message("parsing.pig_id_twice"))
            found[point.code] = point
    return tuple(found[code] for code in sorted(found, key=int))


def parse_pig_stations(content: bytes, /, *, filename: str) -> list[StationListEntry]:
    """
    The points of PIG-PIB's monitoring as station-list entries (``groundwater``).

    Parameters
    ----------
    content : bytes
        A stored version of ``pl.pig.groundwater_stations``: the capture of the pages
        of ``hydrogeologia/mwp/MapServer/0`` asked with ``outSR=4326``.
    filename : str
        Its name or address, for errors.

    Returns
    -------
    list of StationListEntry
        One entry per point (``provider`` ``PIG``, ``groundwater_kind`` ``spring``
        for „źródło”, ``bore`` otherwise, ``hydrogeology`` the description), in the
        order of the codes' numbers.

    Raises
    ------
    ObserwatorDataError
        If the capture or a row cannot be read.
    """
    return [
        StationListEntry(
            kind="groundwater",
            station_code=point.code,
            name=point.name,
            latitude=point.latitude,
            longitude=point.longitude,
            provider=PROVIDER,
            groundwater_kind=point.groundwater_kind,
            hydrogeology=dict(point.hydrogeology),
        )
        for point in read_points(content, filename=filename)
    ]


def automatic_points(found: Iterable[Page], /) -> frozenset[str] | None:
    """
    The automatic points a capture of ``mwp_auto`` lists: the codes of its layer 0.

    A night's harvest asks ``hydrogeologia/mwp_auto/MapServer/0`` first (W9): the
    points measured automatically, ``ID_PKT_MWP`` a point's ``ID`` of the points layer.

    Parameters
    ----------
    found : iterable of Page
        The answers of a capture (`pages`).

    Returns
    -------
    frozenset of str or None
        The codes of the last page of layer 0 answered with its rows (a value that is
        no code left out); None for a capture without such a page.
    """
    codes: frozenset[str] | None = None
    for page in found:
        rows = page.features
        if page.layer != "mwp_auto/0" or rows is None:
            continue
        listed: set[str] = set()
        for row in rows:
            attributes = row.get("attributes") if isinstance(row, dict) else None
            code = (
                attributes.get("ID_PKT_MWP") if isinstance(attributes, dict) else None
            )
            if isinstance(code, int) and not isinstance(code, bool) and code >= 1:
                listed.add(str(code))
        codes = frozenset(listed)
    return codes


# --- the readings ------------------------------------------------------------------


@dataclass(frozen=True)
class Reading:
    """
    One row of the readings table: a point's reading of 06:00 UTC of a day.

    Attributes
    ----------
    point : str
        The point's ``ID`` as text (``OTWOR_ID``).
    day : datetime.date
        ``DATA_POMIARU`` without its leading space.
    depth : float or None
        The depth to water [m p.p.t.]: positive below the ground, negative above it.
    spring_yield : float or None
        A spring's yield [l/s].
    """

    point: str
    day: date
    depth: float | None
    spring_yield: float | None


def read_readings(data: bytes, /, *, filename: str) -> tuple[Reading, ...]:
    """
    The rows of a stored version of ``pl.pig.groundwater_readings``.

    Parameters
    ----------
    data : bytes
        The capture of the readings table's pages.
    filename : str
        Its name, for errors.

    Returns
    -------
    tuple of Reading
        One reading per point and day, in the order of points and days; an identical
        row repeated is kept once.

    Raises
    ------
    ObserwatorDataError
        If the capture or a row cannot be read, or a point has two different
        readings of one day.
    """
    found: dict[tuple[str, date], Reading] = {}
    for page in pages(data, filename=filename):
        for index, feature in enumerate(page.features or (), start=1):
            where = message("parsing.pig_row", address=page.address, number=index)
            attributes = _attributes(feature, filename, where)
            point = attributes.get("OTWOR_ID")
            if isinstance(point, bool) or not isinstance(point, int) or point < 1:
                raise _fail(filename, where, message("parsing.pig_no_id"))
            text = attributes.get("DATA_POMIARU")
            stripped = text.strip() if isinstance(text, str) else ""
            if not _DAY.fullmatch(stripped):
                raise _fail(filename, where, message("parsing.pig_bad_day", value=text))
            try:
                day = date.fromisoformat(stripped)
            except ValueError as exc:
                raise _fail(filename, where, str(exc)) from exc
            reading = Reading(
                str(point),
                day,
                _number(attributes.get("GLEBOKOSC_ZWIERCIADLA"), filename, where),
                _number(attributes.get("WYDAJNOSC"), filename, where),
            )
            known = found.get((reading.point, day))
            if known is not None and known != reading:
                raise _fail(
                    filename,
                    where,
                    message("parsing.pig_two_readings", point=reading.point, day=day),
                )
            found[(reading.point, day)] = reading
    return tuple(
        found[key] for key in sorted(found, key=lambda key: (int(key[0]), key[1]))
    )


def readings_period(readings: Iterable[Reading], /) -> tuple[date, date] | None:
    """
    The first and last day of a set of readings; None for none.

    Parameters
    ----------
    readings : iterable of Reading
        Rows of the readings table.

    Returns
    -------
    tuple of datetime.date or None
        Their first and last ``DATA_POMIARU``.
    """
    days = [reading.day for reading in readings]
    return (min(days), max(days)) if days else None


def _hydro_year(day: date) -> int:
    """The hydrological year (November–October) of a day."""
    return day.year + 1 if day.month >= 11 else day.year


def level(elevation: float, depth: float, /) -> float:
    """
    ``H_asl`` = ground elevation − depth to water, to the centimetre (W7, W8).

    Parameters
    ----------
    elevation : float
        The point's ground elevation (``RZEDNA_TERENU``).
    depth : float
        The depth to water, negative above the ground.

    Returns
    -------
    float
        The level rounded to the centimetre.
    """
    return round(elevation - depth, _CENTIMETRE)


def parse_pig_readings(
    content: bytes,
    /,
    *,
    filename: str,
    dataset: str = "pl.pig.groundwater_readings",
    elevations: Mapping[str, float] | None = None,
) -> Iterator[NormalizedRecord]:
    """
    The records of the readings of PIG-PIB's MWP database (W7).

    Each row is the reading of 06:00 UTC of one point and day, a record at its own
    date: ``depth_to_water`` [m] as published (negative above the ground) and,
    with the point's ground elevation, ``H_asl`` [m] = elevation − depth to the
    depth's centimetre; or ``spring_yield`` [l/s]. A row without either value has
    ``depth_to_water`` missing.

    Parameters
    ----------
    content : bytes
        A stored version of ``pl.pig.groundwater_readings``.
    filename : str
        Its name, for errors.
    dataset : str, optional
        The dataset key of the records.
    elevations : Mapping of str to float or None, optional
        The ground elevation of each point (``RZEDNA_TERENU`` of the points the build
        read); a point without one gets no ``H_asl``.

    Returns
    -------
    Iterator of NormalizedRecord
        One record per point and day, in the order of points and days.

    Raises
    ------
    ObserwatorDataError
        If the capture or a row cannot be read.
    """
    known = elevations or {}
    for reading in read_readings(content, filename=filename):
        measurements: dict[str, Measurement] = {}
        if reading.depth is not None:
            measurements["depth_to_water"] = Measurement(reading.depth, "value")
            elevation = known.get(reading.point)
            if elevation is not None:
                measurements["H_asl"] = Measurement(
                    level(elevation, reading.depth), "value"
                )
        if reading.spring_yield is not None:
            measurements["spring_yield"] = Measurement(reading.spring_yield, "value")
        if not measurements:
            measurements["depth_to_water"] = Measurement(None, "missing")
        yield NormalizedRecord(
            station_code=reading.point,
            dataset=dataset,
            date=reading.day,
            hydro_year=_hydro_year(reading.day),
            period=None,
            measurements=measurements,
        )


# --- the automatic measurements -----------------------------------------------------


def stored_hour(epoch_ms: int, /) -> datetime:
    """
    The stored hour of an epoch of ``mwp_auto`` (W9): its Warsaw wall time read as UTC.

    The service stores UTC wall-clock times and answers them converted as if they
    were Europe/Warsaw's, so the epoch's Warsaw wall time is the stored time; its
    seconds (1 to 6 past the hour, by point) are floored away.

    Parameters
    ----------
    epoch_ms : int
        ``TIME`` of a row, milliseconds since the epoch.

    Returns
    -------
    datetime.datetime
        The start of the stored hour, UTC.
    """
    wall = datetime.fromtimestamp(epoch_ms / 1000, tz=WARSAW)
    return datetime(wall.year, wall.month, wall.day, wall.hour, tzinfo=UTC)


def dst_start(day: date, /) -> bool:
    """Whether summer time starts on a day: the last Sunday of March (EU rule)."""
    return day.month == 3 and day.weekday() == 6 and day.day > 24


def _collision(epoch_ms: int) -> date | None:
    """The summer-time start day whose stored 01:00 and 02:00 share an epoch's hour."""
    wall = datetime.fromtimestamp(epoch_ms / 1000, tz=WARSAW)
    return wall.date() if dst_start(wall.date()) and wall.hour == 1 else None


@dataclass
class AutoHours:
    """
    The hours of ``mwp_auto``'s rows read so far in one build (W8, W9).

    Shared by the captures of one month of the hourly series, read in time order, so
    that two rows of one point and stored hour keep the later ``OBJECTID`` whatever
    capture holds it.

    Attributes
    ----------
    values : dict
        Per (point, hour) the ``OBJECTID`` and value kept.
    revised : set of tuple
        The (point, hour) whose rows disagreed (the later ``OBJECTID`` kept).
    unresolved : set of tuple
        The (point, day) of a summer-time start day whose stored 01:00 and 02:00
        rows could not be told apart (no page of the stored hour 02), left out.
    future : int
        Rows whose hour lies after the answer that gave them, left out.
    """

    values: dict[tuple[str, datetime], tuple[int, float | None]] = field(
        default_factory=dict
    )
    revised: set[tuple[str, datetime]] = field(default_factory=set)
    unresolved: set[tuple[str, date]] = field(default_factory=set)
    future: int = 0


def _dst_pages(found: Iterable[Page]) -> dict[date, set[int]]:
    """The ``OBJECTID`` of every row of each page of a stored hour 02 (`DST_CLAUSE`)."""
    hours: dict[date, set[int]] = {}
    for page in found:
        rows = page.features
        clause = _DST_WHERE.fullmatch(page.form.get("where", ""))
        if rows is None or clause is None or page.layer != "mwp_auto/2":
            continue
        ids = hours.setdefault(date.fromisoformat(clause[1]), set())
        for row in rows:
            objectid = row.get("attributes", {}).get("OBJECTID")
            if isinstance(objectid, int):
                ids.add(objectid)
    return hours


def auto_hours(
    found: Iterable[Page],
    state: AutoHours,
    /,
    *,
    filename: str,
    month: tuple[date, date] | None = None,
) -> set[tuple[str, datetime]]:
    """
    Fold the rows of one capture of ``mwp_auto`` into ``state`` (W8, W9).

    Each row of a page 200 of table 2 gives its point's stored hour (`stored_hour`)
    and value (null: no value). A row whose hour lies after the time of its answer
    stays in the capture and out of the series, and belongs to no month a build
    reads: the build of the month of the capture's last hour (the end of the
    capture's period, `ProviderAdapter.capture_extra`; without one, the day before
    its answers) counts it in ``state.future``, every build when ``month`` is None.
    Of two rows of one point and hour the later ``OBJECTID`` is kept, and rows that
    differ are noted in ``state.revised``. A row of a summer-time start day at the
    shared stored hour 01 is hour 02 when the capture's page of that day's stored
    hour 02 holds its ``OBJECTID``, else hour 01; without such a page it is left out
    and its point and day noted in ``state.unresolved``.

    Parameters
    ----------
    found : iterable of Page
        The answers of one capture (`pages`).
    state : AutoHours
        The hours read so far; updated.
    filename : str
        The capture's name, for errors.
    month : tuple of datetime.date or None, optional
        Only the hours of these days (the first and the last), when given.

    Returns
    -------
    set of tuple
        The (point, hour) this capture gave, whose kept values ``state`` holds.

    Raises
    ------
    ObserwatorDataError
        If a row of table 2 cannot be read.
    """
    answers = list(found)
    second = _dst_pages(answers)
    touched: set[tuple[str, datetime]] = set()
    rows: list[tuple[int, str, datetime, float | None]] = []
    future = 0
    last: date | None = None
    reach: date | None = None
    for page in answers:
        features = page.features
        if features is None or page.layer != "mwp_auto/2":
            continue
        limit = page.received
        for index, feature in enumerate(features, start=1):
            where = message("parsing.pig_row", address=page.address, number=index)
            attributes = _attributes(feature, filename, where)
            point, epoch, objectid = (
                attributes.get("PSH_MONITORING_ID"),
                attributes.get("TIME"),
                attributes.get("OBJECTID"),
            )
            if (
                isinstance(point, bool)
                or not isinstance(point, int)
                or not isinstance(epoch, int)
                or not isinstance(objectid, int)
            ):
                raise _fail(filename, where, message("parsing.pig_no_id"))
            value = _number(attributes.get("VALUE"), filename, where)
            hour = stored_hour(epoch)
            if hour > limit:
                future += 1
                reach = reach or (limit - timedelta(days=1)).date()
                continue
            last = hour.date() if last is None else max(last, hour.date())
            day = _collision(epoch)
            if day is not None:
                # A pair of another month is no business of this one's build.
                if month is not None and not month[0] <= day <= month[1]:
                    continue
                if day not in second:
                    state.unresolved.add((str(point), day))
                    continue
                if objectid in second[day]:
                    hour += timedelta(hours=1)
            if month is not None and not month[0] <= hour.date() <= month[1]:
                continue
            rows.append((objectid, str(point), hour, value))
    told = last or reach
    if future and (month is None or (told and month[0] <= told <= month[1])):
        state.future += future
    rows.sort(key=lambda row: row[0])
    for objectid, point, hour, value in rows:
        key = (point, hour)
        touched.add(key)
        kept = state.values.get(key)
        if kept is not None:
            if kept[0] == objectid:
                continue
            if kept[1] != value:
                state.revised.add(key)
            if kept[0] > objectid:
                continue
        state.values[key] = (objectid, value)
    return touched


def years(found: Iterable[Page], /) -> set[int]:
    """The years of the stored hours of a capture's rows of ``mwp_auto``'s table 2."""
    seen: set[int] = set()
    for page in found:
        features = page.features
        if features is None or page.layer != "mwp_auto/2":
            continue
        for feature in features:
            attributes = (
                feature.get("attributes") if isinstance(feature, dict) else None
            )
            epoch = attributes.get("TIME") if isinstance(attributes, dict) else None
            if isinstance(epoch, int) and not isinstance(epoch, bool):
                hour = stored_hour(epoch)
                if hour <= page.received:
                    seen.add(hour.year)
    return seen
