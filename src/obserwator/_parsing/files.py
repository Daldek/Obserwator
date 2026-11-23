"""
The files of a provider fed by files (ADR-033): its station file and its series.

A station file is a GeoJSON FeatureCollection of the documented fields (`STATION_FIELDS`;
``station_code``, ``kind`` and ``name`` required), one Point in WGS84 (or null) per
station; a series file holds one station's daily series in the form of ``series export``
(``obserwator-series-csv``: ``date``, ``year``, ``<V> [<unit>]``, ``<V>_flag``, …,
``attribution``, ``terms_notice``) or its Parquet. Both are read strictly: anything
else is an `ObserwatorDataError` naming the file and the place, so ``store import``
refuses the files before it writes and a stored file that cannot be read stops a
build.
"""

from __future__ import annotations

import csv
import io
import json
import math
import re
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Literal

from obserwator.datasets import KINDS, Kind, get_dataset
from obserwator.exceptions import ObserwatorDataError, ObserwatorStoreDependencyError
from obserwator.messages import Message, message
from obserwator.models import Flag, Measurement, NormalizedRecord

__all__ = [
    "FLAGS",
    "STATION_FIELDS",
    "FileStation",
    "parse_series_export",
    "read_station_file",
]

STATION_FIELDS: tuple[str, ...] = (
    "station_code",
    "kind",
    "name",
    "river",
    "hydrographic_code",
    "active",
    "elevation_m",
    "gauge_zero_m",
    "gauge_zero_datum",
    "river_km",
    "catchment_area_km2",
    "established_year",
    "groundwater_kind",
)
"""The properties a station of a station file may have, ``station_code``, ``kind`` and ``name`` required."""
_REQUIRED = ("station_code", "kind", "name")
_TEXTS = ("river", "hydrographic_code", "gauge_zero_datum")
_NUMBERS = ("elevation_m", "gauge_zero_m", "river_km", "catchment_area_km2")
FLAGS: tuple[Flag, ...] = ("value", "missing", "no_phenomenon", "accumulated")
"""The flags of a series file's ``<V>_flag`` columns."""
_WGS84 = frozenset(
    {
        "urn:ogc:def:crs:OGC:1.3:CRS84",
        "urn:ogc:def:crs:OGC::CRS84",
        "urn:ogc:def:crs:EPSG::4326",
        "EPSG:4326",
    }
)
_VALUE_COLUMN = re.compile(r"(?P<name>[A-Za-z][A-Za-z0-9_]*) \[(?P<unit>[^\]]+)\]")
_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
_TRAILING = ("attribution", "terms_notice")
_PARQUET = b"PAR1"
MAX_STATION_BYTES = 20_000_000
"""The largest station file read."""


@dataclass(frozen=True)
class FileStation:
    """
    One station of a station file, its fields checked.

    Attributes
    ----------
    station_code : str
        Its code, ``<id>-<operator's code>``.
    kind : {"hydro", "meteo", "groundwater"}
        Its family.
    name : str
        Its name.
    river, hydrographic_code, gauge_zero_datum : str or None
        Texts of a hydrological station (any station may have them).
    active : bool
        Whether the operator measures there now (true when the file says nothing).
    elevation_m, gauge_zero_m, river_km, catchment_area_km2 : float or None
        Numbers as the file gives them.
    established_year : int or None
        The year it was established.
    groundwater_kind : {"bore", "spring"} or None
        What a groundwater object is; None for the other families.
    longitude, latitude : float or None
        Its point as the file writes it (the catalog checks it against the border of
        the provider's country, ADR-018); None without a geometry.
    """

    station_code: str
    kind: Kind
    name: str
    river: str | None
    hydrographic_code: str | None
    active: bool
    elevation_m: float | None
    gauge_zero_m: float | None
    gauge_zero_datum: str | None
    river_km: float | None
    catchment_area_km2: float | None
    established_year: int | None
    groundwater_kind: Literal["bore", "spring"] | None
    longitude: float | None
    latitude: float | None


def _broken(filename: str, text: Message) -> ObserwatorDataError:
    return ObserwatorDataError(
        message("parsing.provider_file_data", filename=filename, problem=text),
        details={"path": filename},
    )


def _number(value: object) -> float | None:
    """A finite JSON number (not a boolean), else None."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _point(
    geometry: object, code: str, filename: str
) -> tuple[float | None, float | None]:
    """The longitude and latitude of a station's Point; (None, None) for a null geometry."""
    if geometry is None:
        return None, None
    coordinates = geometry.get("coordinates") if isinstance(geometry, dict) else None
    if (
        not isinstance(geometry, dict)
        or geometry.get("type") != "Point"
        or not isinstance(coordinates, list)
        or len(coordinates) != 2
    ):
        raise _broken(filename, message("parsing.station_not_point", code=code))
    lon, lat = (_number(value) for value in coordinates)
    if lon is None or lat is None or not (-180 <= lon <= 180 and -90 <= lat <= 90):
        raise _broken(filename, message("parsing.station_bad_point", code=code))
    # The point as published: an integer stays one, so its decimals are counted.
    return coordinates[0], coordinates[1]


def _text_field(
    properties: Mapping[str, Any], name: str, code: str, filename: str
) -> str | None:
    value = properties.get(name)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise _broken(
            filename, message("parsing.station_bad_field", code=code, field=name)
        )
    return " ".join(value.split())


def _station(feature: object, pattern: re.Pattern[str], filename: str) -> FileStation:
    """One feature of a station file."""
    if not isinstance(feature, dict) or feature.get("type") != "Feature":
        raise _broken(filename, message("parsing.station_not_feature"))
    properties = feature.get("properties")
    if not isinstance(properties, dict):
        raise _broken(filename, message("parsing.station_without_properties"))
    code = properties.get("station_code")
    if not isinstance(code, str) or not pattern.fullmatch(code):
        raise _broken(
            filename,
            message(
                "parsing.station_bad_code",
                code=json.dumps(code, ensure_ascii=False)[:80],
                pattern=pattern.pattern,
            ),
        )
    for name in properties:
        if name not in STATION_FIELDS:
            raise _broken(
                filename,
                message(
                    "parsing.station_unknown_field",
                    code=code,
                    field=name,
                    allowed=", ".join(STATION_FIELDS),
                ),
            )
    for name in _REQUIRED:
        if properties.get(name) is None:
            raise _broken(
                filename,
                message("parsing.station_missing_field", code=code, field=name),
            )
    kind = properties["kind"]
    if kind not in KINDS:
        raise _broken(
            filename,
            message(
                "parsing.station_bad_kind",
                code=code,
                kind=json.dumps(kind, ensure_ascii=False)[:40],
                allowed=", ".join(KINDS),
            ),
        )
    name = _text_field(properties, "name", code, filename)
    assert name is not None  # required
    active = properties.get("active", True)
    if not isinstance(active, bool):
        raise _broken(
            filename, message("parsing.station_bad_field", code=code, field="active")
        )
    numbers: dict[str, float | None] = {}
    for field in _NUMBERS:
        value = properties.get(field)
        numbers[field] = None if value is None else _number(value)
        if value is not None and numbers[field] is None:
            raise _broken(
                filename, message("parsing.station_bad_field", code=code, field=field)
            )
    area = numbers["catchment_area_km2"]
    if area is not None and area <= 0:
        raise _broken(
            filename,
            message("parsing.station_bad_field", code=code, field="catchment_area_km2"),
        )
    year = properties.get("established_year")
    if year is not None and (
        isinstance(year, bool) or not isinstance(year, int) or not 1 <= year <= 9999
    ):
        raise _broken(
            filename,
            message("parsing.station_bad_field", code=code, field="established_year"),
        )
    groundwater = properties.get("groundwater_kind")
    if groundwater is not None and (
        kind != "groundwater" or groundwater not in ("bore", "spring")
    ):
        raise _broken(
            filename,
            message("parsing.station_bad_field", code=code, field="groundwater_kind"),
        )
    lon, lat = _point(feature.get("geometry"), code, filename)
    return FileStation(
        station_code=code,
        kind=kind,
        name=name,
        river=_text_field(properties, "river", code, filename),
        hydrographic_code=_text_field(properties, "hydrographic_code", code, filename),
        active=active,
        elevation_m=numbers["elevation_m"],
        gauge_zero_m=numbers["gauge_zero_m"],
        gauge_zero_datum=_text_field(properties, "gauge_zero_datum", code, filename),
        river_km=numbers["river_km"],
        catchment_area_km2=area,
        established_year=year,
        groundwater_kind="bore"
        if groundwater == "bore"
        else "spring"
        if groundwater == "spring"
        else None,
        longitude=lon,
        latitude=lat,
    )


def read_station_file(
    data: bytes, /, *, pattern: str, filename: str
) -> tuple[FileStation, ...]:
    """
    Read the station file of a provider fed by files (a GeoJSON FeatureCollection).

    Parameters
    ----------
    data : bytes
        The file.
    pattern : str
        The grammar of the provider's station codes (``^SIEC-…$``).
    filename : str
        Its name or path, for errors.

    Returns
    -------
    tuple of FileStation
        Its stations in file order.

    Raises
    ------
    ObserwatorDataError
        If the file is larger than `MAX_STATION_BYTES`, no UTF-8 JSON, no
        FeatureCollection, names a ``crs`` other than WGS84, or a station has a code
        outside ``pattern``, a property outside `STATION_FIELDS`, lacks one of
        ``station_code``, ``kind`` and ``name``, has a value of the wrong type, a
        geometry other than a Point of two numbers in range, or a code given before.
    """
    if len(data) > MAX_STATION_BYTES:
        raise _broken(
            filename,
            message("parsing.station_file_too_large", maximum=MAX_STATION_BYTES),
        )
    try:
        document = json.loads(data.decode("utf-8-sig"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise _broken(
            filename, message("parsing.station_file_not_json", reason=str(exc))
        ) from exc
    if not isinstance(document, dict) or document.get("type") != "FeatureCollection":
        raise _broken(filename, message("parsing.station_file_not_collection"))
    crs = document.get("crs")
    if crs is not None:
        name = crs.get("properties", {}).get("name") if isinstance(crs, dict) else None
        if name not in _WGS84:
            raise _broken(
                filename,
                message(
                    "parsing.station_file_crs",
                    crs=json.dumps(crs, ensure_ascii=False)[:200],
                ),
            )
    features = document.get("features")
    if not isinstance(features, list):
        raise _broken(filename, message("parsing.station_file_not_collection"))
    grammar = re.compile(pattern)
    stations: list[FileStation] = []
    seen: set[str] = set()
    for feature in features:
        station = _station(feature, grammar, filename)
        if station.station_code in seen:
            raise _broken(
                filename,
                message("parsing.station_repeated", code=station.station_code),
            )
        seen.add(station.station_code)
        stations.append(station)
    return tuple(stations)


# --- series files -----------------------------------------------------------------------


def _hydro_year(day: date) -> int:
    """The hydrological year (November to October) of a day."""
    return day.year + 1 if day.month >= 11 else day.year


@dataclass(frozen=True)
class _Columns:
    """The columns of a series file: the date's and each variable's value and flag."""

    date: int
    values: Mapping[str, int]
    flags: Mapping[str, int]


def _columns(
    header: Sequence[str], variables: Mapping[str, str], filename: str
) -> _Columns:
    """Check the header of a series file against its dataset's variables and units."""
    if not header or header[0] != "date":
        found = ",".join(header) or message("common.none")
        raise _broken(filename, message("parsing.series_no_date", found=found))
    values: dict[str, int] = {}
    flags: dict[str, int] = {}
    seen: set[str] = set()
    for index, column in enumerate(header):
        if column in seen:
            raise _broken(
                filename, message("parsing.series_repeated_column", column=column)
            )
        seen.add(column)
        if index == 0 or column in ("year", *_TRAILING):
            continue
        matched = _VALUE_COLUMN.fullmatch(column)
        if matched is not None:
            name, unit = matched["name"], matched["unit"]
            if name not in variables:
                raise _broken(
                    filename,
                    message(
                        "parsing.series_unknown_variable",
                        variable=name,
                        allowed=", ".join(variables),
                    ),
                )
            if unit != variables[name]:
                raise _broken(
                    filename,
                    message(
                        "parsing.series_bad_unit",
                        variable=name,
                        unit=unit,
                        expected=variables[name],
                    ),
                )
            values[name] = index
            continue
        if column.endswith("_flag") and column.removesuffix("_flag") in variables:
            flags[column.removesuffix("_flag")] = index
            continue
        raise _broken(
            filename,
            message(
                "parsing.series_unknown_column",
                column=column,
                allowed=", ".join(
                    f"{name} [{unit}]" for name, unit in variables.items()
                ),
            ),
        )
    for name in flags:
        if name not in values:
            raise _broken(filename, message("parsing.series_flag_alone", variable=name))
    if not values:
        raise _broken(filename, message("parsing.series_no_variable"))
    return _Columns(0, values, flags)


def _day(value: object, row: int, filename: str) -> date:
    """The date of a row: ``YYYY-MM-DD`` text, a date or a time."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str) and _DATE.fullmatch(value):
        try:
            return date.fromisoformat(value)
        except ValueError:
            pass
    raise _broken(
        filename,
        message(
            "parsing.series_bad_date",
            row=row,
            value=json.dumps(value, default=str, ensure_ascii=False)[:40],
        ),
    )


def _measurement(
    value: object, flag: object, variable: str, row: int, filename: str
) -> Measurement:
    """One value of a row with its flag, which must agree with it."""
    number: float | None
    if value is None or value == "":
        number = None
    elif isinstance(value, str):
        try:
            number = float(value)
        except ValueError:
            number = math.nan
    elif isinstance(value, int | float) and not isinstance(value, bool):
        number = float(value)
    else:
        number = math.nan
    if number is not None and not math.isfinite(number):
        raise _broken(
            filename,
            message(
                "parsing.series_bad_value",
                row=row,
                variable=variable,
                value=json.dumps(value, default=str, ensure_ascii=False)[:40],
            ),
        )
    given = "" if flag is None else flag
    resolved: Flag | None = (
        ("missing" if number is None else "value")
        if given == ""
        else next((item for item in FLAGS if item == given), None)
    )
    if resolved is None:
        raise _broken(
            filename,
            message(
                "parsing.series_bad_flag",
                row=row,
                variable=variable,
                flag=json.dumps(flag, default=str, ensure_ascii=False)[:40],
                allowed=", ".join(FLAGS),
            ),
        )
    if resolved == "no_phenomenon" and number in (None, 0.0):
        return Measurement(0.0, "no_phenomenon")
    if resolved == "no_phenomenon" or (resolved == "missing") != (number is None):
        raise _broken(
            filename,
            message(
                "parsing.series_flag_mismatch",
                row=row,
                variable=variable,
                flag=resolved,
            ),
        )
    return Measurement(number, resolved)


def _records(
    rows: Iterator[tuple[int, Sequence[object]]],
    columns: _Columns,
    *,
    dataset: str,
    station: str,
    filename: str,
) -> list[NormalizedRecord]:
    """The records of a series file's rows, in date order; a repeated date is refused."""
    records: dict[date, NormalizedRecord] = {}
    for number, cells in rows:
        day = _day(cells[columns.date], number, filename)
        if day in records:
            raise _broken(
                filename, message("parsing.series_repeated_date", row=number, day=day)
            )
        measurements = {
            variable: _measurement(
                cells[index],
                cells[columns.flags[variable]] if variable in columns.flags else None,
                variable,
                number,
                filename,
            )
            for variable, index in columns.values.items()
        }
        records[day] = NormalizedRecord(
            station_code=station,
            dataset=dataset,
            date=day,
            hydro_year=_hydro_year(day),
            period=None,
            measurements=measurements,
        )
    if not records:
        raise _broken(filename, message("parsing.series_no_rows"))
    return [records[day] for day in sorted(records)]


def _csv_rows(
    data: bytes, filename: str
) -> tuple[list[str], Iterator[tuple[int, Sequence[object]]]]:
    """The header and the numbered rows of a CSV series file."""
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise _broken(filename, message("parsing.series_not_utf8")) from exc
    reader = csv.reader(io.StringIO(text, newline=""))
    try:
        header = next(reader)
    except StopIteration:
        raise _broken(filename, message("parsing.series_no_rows")) from None
    except csv.Error as exc:
        raise _broken(
            filename, message("parsing.series_not_csv", reason=str(exc))
        ) from exc
    width = len(header)

    def rows() -> Iterator[tuple[int, Sequence[object]]]:
        try:
            for number, cells in enumerate(reader, start=2):
                if len(cells) != width:
                    raise _broken(
                        filename,
                        message(
                            "parsing.series_bad_row",
                            row=number,
                            found=len(cells),
                            expected=width,
                        ),
                    )
                yield number, cells
        except csv.Error as exc:
            raise _broken(
                filename, message("parsing.series_not_csv", reason=str(exc))
            ) from exc

    return [column.strip() for column in header], rows()


def _parquet_rows(
    data: bytes, filename: str
) -> tuple[list[str], Iterator[tuple[int, Sequence[object]]]]:
    """The columns and the numbered rows of a Parquet series file."""
    try:
        import pyarrow
        import pyarrow.parquet
    except ImportError as exc:
        raise ObserwatorStoreDependencyError(
            message(
                "series.building_parquet_series_needs_package",
                install=message("errors.store_extra"),
            )
        ) from exc
    try:
        table = pyarrow.parquet.read_table(pyarrow.BufferReader(data))
    except (pyarrow.ArrowException, OSError, ValueError) as exc:
        raise _broken(
            filename, message("parsing.series_not_parquet", reason=str(exc))
        ) from exc
    header = list(table.column_names)
    columns = [table.column(name).to_pylist() for name in header]

    def rows() -> Iterator[tuple[int, Sequence[object]]]:
        for index in range(table.num_rows):
            yield index + 1, [column[index] for column in columns]

    return header, rows()


def parse_series_export(
    data: bytes, /, *, dataset: str, station: str, filename: str = "<series>"
) -> list[NormalizedRecord]:
    """
    Read one station's daily series in the form of ``series export`` (CSV or Parquet).

    The reader of a provider fed by files (ADR-033): ``obserwator-series-csv`` (UTF-8,
    a BOM allowed, comma, dot decimal; the header ``date``, an optional ``year``, then
    per variable ``<V> [<unit>]`` and an optional ``<V>_flag``, an optional trailing
    ``attribution`` and ``terms_notice``) or the Parquet of ``series export --format
    parquet`` (the same columns; the file metadata is not read). A row's ``year`` and
    lines are not read: the hydrological year follows from the date (November to
    October). Without a flag column an empty cell is ``missing`` and a number a
    ``value``.

    Parameters
    ----------
    data : bytes
        The file; Parquet when it starts with ``PAR1``, else CSV.
    dataset : str
        Key of the dataset whose variables and units the columns must use.
    station : str
        The station of the series, given to every record.
    filename : str, optional
        The file's name or path, for errors.

    Returns
    -------
    list of NormalizedRecord
        One record per row, in date order, each with the values of the columns the
        file has.

    Raises
    ------
    ObserwatorValidationError
        If ``dataset`` names no dataset.
    ObserwatorDataError
        If the file is no such series: a column other than these, a variable or unit
        the dataset does not have, a flag column without its value column, no value
        column, a date other than ``YYYY-MM-DD`` or given twice, a value that is no
        finite number, a flag other than ``value``, ``missing``, ``no_phenomenon`` and
        ``accumulated`` or one that does not agree with the value (``missing`` with a
        value, another without one, ``no_phenomenon`` with a value other than 0), no
        row, or a CSV row of another width.
    ObserwatorStoreDependencyError
        If a Parquet file is read without ``pyarrow``.
    """
    descriptor = get_dataset(dataset)
    header, rows = (
        _parquet_rows(data, filename)
        if data.startswith(_PARQUET)
        else _csv_rows(data, filename)
    )
    columns = _columns(header, descriptor.variables, filename)
    return _records(
        rows, columns, dataset=descriptor.key, station=station, filename=filename
    )
