"""Daily IMGW meteorological k_d, o_d and s_d (synop) CSV normalization."""

import calendar
import re
from collections.abc import Collection, Iterator
from dataclasses import replace
from datetime import date, timedelta
from typing import Literal

from obserwator._parsing.common import (
    _decode_content,
    _detect_delimiter,
    _is_header_row,
    _iter_rows,
)
from obserwator.exceptions import ObserwatorDataError
from obserwator.messages import message, reason
from obserwator.models import Measurement, NormalizedRecord

_ATTRIBUTE_COLUMNS = {
    "k_d": (("precip_type", 15),),
    "o_d": (("precip_type", 7), ("snow_species", 12), ("snow_cover_type", 14)),
    "s_d": (("precip_type", 15), ("ground_state", 58)),
}
_SYNOP = "pl.imgw.meteo_synop_daily"
DATASET_ATTRIBUTES = {
    "pl.imgw.meteo_climate_daily": tuple(k for k, _ in _ATTRIBUTE_COLUMNS["k_d"]),
    "pl.imgw.meteo_precip_daily": tuple(k for k, _ in _ATTRIBUTE_COLUMNS["o_d"]),
    _SYNOP: tuple(k for k, _ in _ATTRIBUTE_COLUMNS["s_d"]),
}
"""Qualitative ``NormalizedRecord.attributes`` keys of each meteorological dataset."""

# Daily synoptic data (s_d_format.txt, s_d_t_format.txt): the value column of each
# variable, its status (8 no measurement, 9 no phenomenon) in the next one. The
# first columns of s_d are those of k_d. TEMP of s_d_t, the mean daily air
# temperature that STD of s_d gives as Tmean, is not read.
_SYNOP_COLUMNS: dict[str, tuple[tuple[str, int], ...]] = {
    "s_d": (
        ("Tmax", 5),
        ("Tmin", 7),
        ("Tmean", 9),
        ("Tground", 11),
        ("P", 13),
        ("snow_cover", 16),
        ("snow_water_equivalent", 18),
        ("sunshine", 20),
        ("rain_duration", 22),
        ("snowfall_duration", 24),
        ("sleet_duration", 26),
        ("hail_duration", 28),
        ("fog_duration", 30),
        ("mist_duration", 32),
        ("rime_duration", 34),
        ("glaze_duration", 36),
        ("drifting_snow_duration", 38),
        ("blowing_snow_duration", 40),
        ("haze_duration", 42),
        ("wind_10_duration", 44),
        ("wind_15_duration", 46),
        ("thunderstorm_duration", 48),
        ("dew_duration", 50),
        ("hoarfrost_duration", 52),
        ("snow_cover_occurrence", 54),
        ("lightning_occurrence", 56),
        ("isotherm_lower", 59),
        ("isotherm_upper", 61),
        ("actinometry", 63),
    ),
    "s_d_t": (
        ("cloud_cover", 5),
        ("wind_speed", 7),
        ("vapour_pressure", 11),
        ("humidity", 13),
        ("pressure_station", 15),
        ("pressure_sea", 17),
        ("P_day", 19),
        ("P_night", 21),
    ),
}
# Columns of a row of each file.
_SYNOP_WIDTH = {"s_d": 65, "s_d_t": 23}
# A member of a synop package: a station's file named by its number and period
# (``s_d_200_1966_1970.csv``, ``s_d_t_200_2024.csv``) or a month of the whole
# country (``s_d_01_2026.csv``).
_SYNOP_MEMBER = re.compile(
    r"(?:^|/)(s_d(?:_t)?)_(?:([0-9]{3})_([0-9]{4})(?:_([0-9]{4}))?"
    r"|([0-9]{2})_([0-9]{4}))\.csv$"
)


def _measurement(raw: str, status: str, *, filename: str, number: int) -> Measurement:
    status = status.strip()
    if status == "8":
        return Measurement(None, "missing")
    if status == "9":
        return Measurement(0.0, "no_phenomenon")
    if not raw.strip():
        return Measurement(None, "missing")
    try:
        return Measurement(float(raw.strip().replace(",", ".")), "value")
    except ValueError as exc:
        raise ObserwatorDataError(
            message(
                "meteo.invalid_value_row", filename=filename, number=number, raw=raw
            )
        ) from exc


def _parse_daily(
    content: bytes | str,
    *,
    filename: str,
    kind: str,
    year: int | None = None,
    month: int | None = None,
    carry: dict[str, date] | None = None,
    stations: Collection[str] | None = None,
    skipped_months: set[date] | None = None,
) -> Iterator[NormalizedRecord]:
    text = _decode_content(content) if isinstance(content, bytes) else content
    text = text.lstrip("\ufeff")
    fields: dict[str, dict[date, NormalizedRecord]] = {}
    months: set[tuple[int, int]] = set()
    skipped = False
    leading = True
    for number, row in enumerate(_iter_rows(text, _detect_delimiter(text)), 1):
        if not any(cell.strip() for cell in row):
            continue
        if leading:
            leading = False
            if _is_header_row(row):
                continue  # column codes (e.g. o_d_08_2025.csv: kansp,kapost,...)
        if len(row) < (18 if kind == "k_d" else 16):
            raise ObserwatorDataError(
                message("meteo.too_few_columns_row", filename=filename, number=number)
            )
        try:
            station = row[0].strip().strip('"')
            if not re.fullmatch(r"\d{9}", station):
                raise ValueError(message("meteo.invalid_station_code"))
            measured = date(int(row[2]), int(row[3]), int(row[4]))
            if year is not None and (
                measured.year != year or month is not None and measured.month != month
            ):
                raise ValueError(message("meteo.date_outside_period_archive"))
            months.add((measured.year, measured.month))
            if stations is not None and station not in stations:
                # Another station: its values are not read, but every station
                # of the file gets a record of each day of its months.
                skipped = True
                continue
            if kind == "k_d":
                values = {
                    key: _measurement(
                        row[offset], row[offset + 1], filename=filename, number=number
                    )
                    for key, offset in (
                        ("Tmax", 5),
                        ("Tmin", 7),
                        ("Tmean", 9),
                        ("Tground", 11),
                        ("P", 13),
                        ("snow_cover", 16),
                    )
                }
            else:
                values = {
                    key: _measurement(
                        row[offset], row[offset + 1], filename=filename, number=number
                    )
                    for key, offset in (("P", 5), ("snow_cover", 8), ("fresh_snow", 10))
                }
                # Status Z (o_d_format.txt): a collective total of the days without a
                # measurement before it, with no indication of when it fell
                if row[6].strip() == "Z" and values["P"].flag == "value":
                    values["P"] = Measurement(values["P"].value, "accumulated")
            attributes = {
                key: row[column].strip() or None
                for key, column in _ATTRIBUTE_COLUMNS[kind]
            }
            record = NormalizedRecord(
                station,
                "pl.imgw.meteo_climate_daily"
                if kind == "k_d"
                else "pl.imgw.meteo_precip_daily",
                measured,
                measured.year + (measured.month >= 11),
                None,
                values,
                attributes,
            )
            entries = fields.setdefault(station, {})
            if measured in entries:
                raise ValueError(message("meteo.repeated_day_station"))
            entries[measured] = record
        except (ValueError, IndexError) as exc:
            raise ObserwatorDataError(
                message(
                    "meteo.invalid_record_row",
                    filename=filename,
                    number=number,
                    exc=reason(exc),
                )
            ) from exc
    if year is not None:
        months = {(year, month)} if month else {(year, i) for i in range(1, 13)}
    if skipped and skipped_months is not None:
        skipped_months.update(date(y, m, 1) for y, m in months)
    variables = (
        ("Tmax", "Tmin", "Tmean", "Tground", "P", "snow_cover")
        if kind == "k_d"
        else ("P", "snow_cover", "fresh_snow")
    )
    for station, entries in fields.items():
        present_months = {(day.year, day.month) for day in entries}
        previous_missing = None if carry is None else carry.get(station)
        for y, m in sorted(months):
            for day in range(1, calendar.monthrange(y, m)[1] + 1):
                measured = date(y, m, day)
                found = entries.get(measured)
                if found is None:
                    flag: Literal["no_phenomenon", "missing"] = (
                        "no_phenomenon"
                        if kind == "o_d" and (y, m) in present_months
                        else "missing"
                    )
                    values = {
                        name: Measurement(
                            0.0 if name == "P" and flag == "no_phenomenon" else None,
                            flag if name == "P" else "missing",
                        )
                        for name in variables
                    }
                    record = NormalizedRecord(
                        station,
                        "pl.imgw.meteo_climate_daily"
                        if kind == "k_d"
                        else "pl.imgw.meteo_precip_daily",
                        measured,
                        y + (m >= 11),
                        None,
                        values,
                    )
                else:
                    record = found
                precip = record.measurements["P"]
                if (
                    kind == "o_d"
                    and previous_missing == measured - timedelta(days=1)
                    and precip.flag == "value"
                ):
                    values = dict(record.measurements)
                    values["P"] = Measurement(precip.value, "accumulated")
                    record = NormalizedRecord(
                        record.station_code,
                        record.dataset,
                        record.date,
                        record.hydro_year,
                        None,
                        values,
                        record.attributes,
                    )
                previous_missing = (
                    measured
                    if precip.flag == "missing" and measured in entries
                    else None
                )
                yield record
        if carry is not None:
            if previous_missing is None:
                carry.pop(station, None)
            else:
                carry[station] = previous_missing


def _period_from_filename(filename: str, kind: str) -> tuple[int | None, int | None]:
    match = re.search(
        rf"(?:^|/){kind}_(\d{{4}})(?:_(\d{{2}}))?\.csv$", filename.lower()
    )
    if match is None:
        return None, None
    return int(match.group(1)), int(match.group(2)) if match.group(2) else None


def _synop_member(name: str) -> tuple[str, date | None, date | None, str | None]:
    """
    Kind, period and station number of a synop member by its name.

    A station's file gives its number and the years of its name, a monthly file
    of the whole country its month; another name gives no period (``s_d``
    unless it names ``s_d_t``).
    """
    match = _SYNOP_MEMBER.search(name.lower())
    if match is None:
        kind = "s_d_t" if re.search(r"(?:^|/)s_d_t_", name.lower()) else "s_d"
        return kind, None, None, None
    if match[2] is not None:
        first, last = int(match[3]), int(match[4] or match[3])
        return match[1], date(first, 1, 1), date(last, 12, 31), match[2]
    year, month = int(match[6]), int(match[5])
    if not 1 <= month <= 12:
        return match[1], None, None, None
    days = calendar.monthrange(year, month)[1]
    return match[1], date(year, month, 1), date(year, month, days), None


def _parse_synop(
    content: bytes | str,
    *,
    filename: str,
    kind: str,
    start: date | None,
    end: date | None,
    number: str | None,
) -> Iterator[NormalizedRecord]:
    """
    Records of one ``s_d`` or ``s_d_t`` CSV, every day of the period for each station.

    Without a period the months present in the file are filled, as for k_d.
    A station's file (``number``) holds only codes ending with its number.
    """
    text = _decode_content(content) if isinstance(content, bytes) else content
    text = text.lstrip("\ufeff")
    columns = _SYNOP_COLUMNS[kind]
    attributes = _ATTRIBUTE_COLUMNS.get(kind, ())
    days: dict[str, dict[date, NormalizedRecord]] = {}
    leading = True
    for line, row in enumerate(_iter_rows(text, _detect_delimiter(text)), 1):
        if not any(cell.strip() for cell in row):
            continue
        if leading:
            leading = False
            if _is_header_row(row):
                continue
        if len(row) < _SYNOP_WIDTH[kind]:
            raise ObserwatorDataError(
                message("meteo.too_few_columns_row", filename=filename, number=line)
            )
        try:
            station = row[0].strip().strip('"')
            if not re.fullmatch(r"\d{9}", station):
                raise ValueError(message("meteo.invalid_station_code"))
            if number is not None and station[-3:] != number:
                raise ValueError(
                    message("meteo.station_of_another_file", number=number)
                )
            measured = date(int(row[2]), int(row[3]), int(row[4]))
            if start is not None and end is not None and not start <= measured <= end:
                raise ValueError(message("meteo.date_outside_period_archive"))
            entries = days.setdefault(station, {})
            if measured in entries:
                raise ValueError(message("meteo.repeated_day_station"))
            entries[measured] = NormalizedRecord(
                station,
                _SYNOP,
                measured,
                measured.year + (measured.month >= 11),
                None,
                {
                    name: _measurement(
                        row[column], row[column + 1], filename=filename, number=line
                    )
                    for name, column in columns
                },
                {name: row[column].strip() or None for name, column in attributes},
            )
        except (ValueError, IndexError) as exc:
            raise ObserwatorDataError(
                message(
                    "meteo.invalid_record_row",
                    filename=filename,
                    number=line,
                    exc=reason(exc),
                )
            ) from exc
    if start is not None and end is not None:
        spans = [(start, end)]
    else:
        months = sorted(
            {(day.year, day.month) for found in days.values() for day in found}
        )
        spans = [
            (date(y, m, 1), date(y, m, calendar.monthrange(y, m)[1])) for y, m in months
        ]
    missing = {name: Measurement(None, "missing") for name, _ in columns}
    for station, entries in days.items():
        for first, last in spans:
            day = first
            while day <= last:
                yield entries.get(day) or NormalizedRecord(
                    station, _SYNOP, day, day.year + (day.month >= 11), None, missing
                )
                day += timedelta(days=1)


def parse_meteo_climate_daily(
    content: bytes | str, /, *, filename: str
) -> Iterator[NormalizedRecord]:
    """
    Parse an IMGW daily climate (``k_d``) CSV into normalized records.

    Variables ``Tmax``, ``Tmin``, ``Tmean``, ``Tground`` [degC], ``P`` [mm]
    and ``snow_cover`` [cm] are read with their status codes: status 8 gives
    ``None`` flagged ``"missing"``, status 9 gives ``0.0`` flagged
    ``"no_phenomenon"``, an empty value is ``"missing"``. The precipitation
    type (``S``, ``W`` or empty) is kept in ``attributes["precip_type"]``.

    The archive period is taken from a ``k_d_<year>[_<month>].csv`` file
    name; without it, the months present in the file are used. For every
    station, every day of that period is yielded and days absent from the
    file get all variables ``"missing"``. A leading row of column codes
    (IMGW header, e.g. ``kansp,kapost,dorok,...``) is skipped; any other
    row must be a data row.

    Parameters
    ----------
    content : bytes or str
        CSV content; bytes are decoded as CP1250 (UTF-8 with BOM detected).
    filename : str
        Member file name, used to infer the period and in error messages.

    Yields
    ------
    NormalizedRecord
        One record per station and calendar day, with dataset
        ``"pl.imgw.meteo_climate_daily"`` and the hydrological year
        (November-October) of the day.

    Raises
    ------
    ObserwatorDataError
        If a row has too few columns, an invalid station code, date or value,
        a date outside the period from ``filename``, or repeats a station day.
    """
    year, month = _period_from_filename(filename, "k_d")
    yield from _parse_daily(
        content, filename=filename, kind="k_d", year=year, month=month
    )


def parse_meteo_precip_daily(
    content: bytes | str, /, *, filename: str
) -> Iterator[NormalizedRecord]:
    """
    Parse an IMGW daily precipitation (``o_d``) CSV into normalized records.

    Variables ``P`` [mm], ``snow_cover`` [cm] and ``fresh_snow`` [cm] are
    read with their status codes: status 8 gives ``None`` flagged
    ``"missing"``, status 9 gives ``0.0`` flagged ``"no_phenomenon"``, an
    empty value is ``"missing"``. Classification codes are kept as text in
    ``attributes`` (``precip_type``, ``snow_species``, ``snow_cover_type``).

    The archive period is taken from an ``o_d_<year>[_<month>].csv`` file
    name; without it, the months present in the file are used. For every
    station, every day of that period is yielded: a day absent from a month
    in which the station has rows gets ``P = 0.0`` flagged
    ``"no_phenomenon"``, a day in a month without any station rows gets
    ``P`` flagged ``"missing"``; other variables of absent days are
    ``"missing"``. A ``P`` value is an IMGW multi-day total, flagged
    ``"accumulated"`` while the preceding days stay ``"missing"``, when its
    status is ``Z`` (o_d_format.txt: a collective total of the days without
    a measurement) or when it directly follows a listed day whose ``P`` is
    missing (status 8). IMGW-PIB's format note gives the second rule for a
    month whose total it computed; it is applied to every month, as a
    reading after days without one (a weekend) is such a total in any month.
    A file knows no day before its first, so a total on the first day of a
    monthly file after missing days at the end of the previous month is
    flagged here only by status ``Z``; the series build of the store carries
    the missing days from one archive of a station to the next. A leading
    row of column codes (IMGW header, e.g. ``kansp,kapost,dorok,...`` in
    ``o_d_08_2025.csv``) is skipped; any other row must be a data row.

    Parameters
    ----------
    content : bytes or str
        CSV content; bytes are decoded as CP1250 (UTF-8 with BOM detected).
    filename : str
        Member file name, used to infer the period and in error messages.

    Yields
    ------
    NormalizedRecord
        One record per station and calendar day, with dataset
        ``"pl.imgw.meteo_precip_daily"`` and the hydrological year
        (November-October) of the day.

    Raises
    ------
    ObserwatorDataError
        If a row has too few columns, an invalid station code, date or value,
        a date outside the period from ``filename``, or repeats a station day.
    """
    year, month = _period_from_filename(filename, "o_d")
    yield from _parse_daily(
        content, filename=filename, kind="o_d", year=year, month=month
    )


def parse_meteo_synop_daily(
    content: bytes | str, /, *, filename: str
) -> Iterator[NormalizedRecord]:
    """
    Parse an IMGW daily synoptic CSV (``s_d`` or ``s_d_t``) into normalized records.

    An ``s_d`` file gives the variables of the climate stations under their
    names, ``Tmax``, ``Tmin``, ``Tmean``, ``Tground`` [degC], ``P`` [mm] and
    ``snow_cover`` [cm], and the synoptic ones: ``snow_water_equivalent``
    [mm/cm], ``sunshine`` [h], the durations [h] ``rain_duration``,
    ``snowfall_duration``, ``sleet_duration``, ``hail_duration``,
    ``fog_duration``, ``mist_duration``, ``rime_duration``,
    ``glaze_duration``, ``drifting_snow_duration``,
    ``blowing_snow_duration``, ``haze_duration``, ``wind_10_duration``,
    ``wind_15_duration``, ``thunderstorm_duration``, ``dew_duration`` and
    ``hoarfrost_duration``, the occurrences [0/1] ``snow_cover_occurrence``
    and ``lightning_occurrence``, ``isotherm_lower`` and ``isotherm_upper``
    [cm] and ``actinometry`` [J/cm2]; the precipitation type and the state of
    the ground (``Z`` or ``R``) are kept in ``attributes["precip_type"]`` and
    ``attributes["ground_state"]``. An ``s_d_t`` file (named ``s_d_t_*``)
    gives the daily means of the observation times: ``cloud_cover`` [okta],
    ``wind_speed`` [m/s], ``vapour_pressure`` [hPa], ``humidity`` [%],
    ``pressure_station`` and ``pressure_sea`` [hPa], and the day and night
    precipitation sums ``P_day`` and ``P_night`` [mm]; its ``TEMP``, the mean
    temperature that ``Tmean`` gives, is not read. Status 8 gives ``None``
    flagged ``"missing"``, status 9 gives ``0.0`` flagged
    ``"no_phenomenon"``, an empty value is ``"missing"``, as for
    ``parse_meteo_climate_daily``.

    The period is taken from the file name: a station's file
    ``s_d[_t]_<number>_<year>[_<last year>].csv`` holds the years of its name
    and only codes ending with its three-digit number, a monthly file of the
    whole country ``s_d[_t]_<month>_<year>.csv`` its month; without such a
    name, the months present in the file are used. For every station, every
    day of that period is yielded and days absent from the file get all
    variables ``"missing"``.

    Parameters
    ----------
    content : bytes or str
        CSV content; bytes are decoded as CP1250 (UTF-8 with BOM detected).
    filename : str
        Member file name, used to infer the kind, the period and the station
        number and in error messages.

    Yields
    ------
    NormalizedRecord
        One record per station and calendar day, with dataset
        ``"pl.imgw.meteo_synop_daily"`` and the hydrological year
        (November-October) of the day.

    Raises
    ------
    ObserwatorDataError
        If a row has too few columns, an invalid station code (or one of
        another station's file), date or value, a date outside the period from
        ``filename``, or repeats a station day.
    """
    kind, start, end, number = _synop_member(filename)
    yield from _parse_synop(
        content, filename=filename, kind=kind, start=start, end=end, number=number
    )


def normalize_meteo_archive(
    dataset: str,
    filename: str,
    data: bytes,
    *,
    year: int | None,
    month: int | None,
    carry: dict[str, date] | None = None,
    stations: Collection[str] | None = None,
    skipped_months: set[date] | None = None,
) -> Iterator[NormalizedRecord]:
    """
    Normalize a daily meteorological IMGW archive.

    Every CSV member named ``k_d_<period>.csv`` (climate) or
    ``o_d_<period>.csv`` (precipitation), where ``<period>`` consists of
    ``_``-separated digit groups (IMGW ``k_d_1995.csv``,
    ``k_d_01_2001.csv``), is parsed like ``parse_meteo_climate_daily`` or
    ``parse_meteo_precip_daily``, except that the period comes from
    ``year`` and ``month`` instead of the member name. Other members of the
    package, e.g. ``k_d_t_*.csv`` (daily means of other elements), are
    ignored.

    Parameters
    ----------
    dataset : str
        Dataset key; ``"pl.imgw.meteo_climate_daily"`` selects ``k_d``
        members, any other value selects ``o_d`` members.
    filename : str
        Archive name used in error messages.
    data : bytes
        ZIP archive content.
    year : int or None
        Calendar year covered by the archive; every row must fall in it and
        missing days are filled for the whole year (or ``month``). ``None``
        disables the check and fills only the months present in the data.
    month : int or None
        Calendar month covered by the archive, or ``None`` for a yearly
        archive.
    carry : dict of str to date or None, optional
        For ``o_d`` archives parsed in date order: per station, the last day
        of the archives before whose ``P`` was listed missing. It is read
        (a total on the next day is ``"accumulated"``) and replaced by the
        state this archive leaves; ``None`` parses the archive alone.
    stations : collection of str or None, optional
        Parse only the rows of these stations; the rows of other stations are
        not checked beyond their station code and date. None parses every
        row.
    skipped_months : set of datetime.date or None, optional
        Receives the first day of every month the records of the stations
        that ``stations`` skipped would have covered (every month of the
        archive's period, see ``year``).

    Yields
    ------
    NormalizedRecord
        One record per station and calendar day.

    Raises
    ------
    ObserwatorDataError
        If the archive is unreadable or unsafe, has no matching CSV member,
        or contains a malformed row.
    """
    from obserwator._parsing.common import archive_csv_members

    kind = "k_d" if dataset == "pl.imgw.meteo_climate_daily" else "o_d"
    matched = False
    for member, content in archive_csv_members(data, filename=filename):
        if not re.search(rf"(?:^|/){kind}(?:_\d+)+\.csv$", member.lower()):
            continue
        matched = True
        yield from _parse_daily(
            content,
            filename=f"{filename}/{member}",
            kind=kind,
            year=year,
            month=month,
            carry=carry if kind == "o_d" else None,
            stations=stations,
            skipped_months=skipped_months,
        )
    if not matched:
        raise ObserwatorDataError(
            message("meteo.no_file", kind=kind, filename=filename)
        )


def normalize_synop_archive(
    filename: str, data: bytes, *, start: date | None, end: date | None
) -> Iterator[NormalizedRecord]:
    """
    Normalize a daily synoptic IMGW archive (``pl.imgw.meteo_synop_daily``).

    The ``s_d`` member and, when the package has it, the ``s_d_t`` member of a
    station's file (``s_d_<number>_<period>.csv``) or of a monthly file of
    the whole country (``s_d_<month>_<year>.csv``) are parsed like
    ``parse_meteo_synop_daily``, except that the period comes from ``start``
    and ``end``; a station's day joins the variables of both members. Other
    members are ignored.

    Parameters
    ----------
    filename : str
        Archive name used in error messages.
    data : bytes
        ZIP archive content.
    start, end : date or None
        First and last day covered by the archive; every row must fall
        between them and missing days are filled for the whole period.
        ``None`` disables the check and fills only the months present in the
        data.

    Yields
    ------
    NormalizedRecord
        One record per station and calendar day.

    Raises
    ------
    ObserwatorDataError
        If the archive is unreadable or unsafe, has no ``s_d`` member, or
        contains a malformed row.
    """
    from obserwator._parsing.common import archive_csv_members

    daily: list[NormalizedRecord] = []
    terms: dict[tuple[str, date], NormalizedRecord] = {}
    matched = False
    for member, content in archive_csv_members(data, filename=filename):
        found = _SYNOP_MEMBER.search(member.lower())
        if found is None:
            continue
        records = _parse_synop(
            content,
            filename=f"{filename}/{member}",
            kind=found[1],
            start=start,
            end=end,
            number=found[2],
        )
        if found[1] == "s_d":
            matched = True
            daily.extend(records)
        else:
            terms.update(
                ((record.station_code, record.date), record) for record in records
            )
    if not matched:
        raise ObserwatorDataError(
            message("meteo.no_file", kind="s_d", filename=filename)
        )
    for record in daily:
        extra = terms.pop((record.station_code, record.date), None)
        yield (
            record
            if extra is None
            else replace(
                record, measurements={**record.measurements, **extra.measurements}
            )
        )
    yield from terms.values()
