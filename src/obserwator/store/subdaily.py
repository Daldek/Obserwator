"""
The hourly series of the tiers: one version per calendar month (ADR-031).

A sub-daily series (`obserwator.datasets.monthly_series`: ``pl.imgw.hydro_subdaily``
and ``cz.chmu.hydro_subdaily``) has no files of its own. The version of a month M,
``series/versions/<slug>/<YYYY-MM>/<label>_<sha8>/``, holds the full hours (UTC) of
the datasets of its ``inputs`` (highest tier first) in M, read from the current
versions of the raw root (the plan's D9):

- a capture dataset (``pl.imgw.hydro_operational``, ``cz.chmu.hydro_recent``): every
  capture day from the day after M's first day to 43 days after its last; of each
  answer with status 200 only the full hours of the UTC days before the answer's own
  day (closed days: today's hours, the 10-minute tail and the forecasts never enter),
  the latest answer of an hour winning within the dataset;
- IMGW-PIB's telemetry: the zip of M, its rows at minute 00 (``999`` is no value);
- ČHMÚ's validated hours: the file of every station of the year of M.

Per station, variable and hour the first input of ``inputs`` with a value wins and
the tier of its dataset labels the point, even where the values differ; a lower tier
stays only where every higher one has no value. The input versions holding a record
of M (a value or none) are the inputs of its version (``source_files``): the same
inputs and lines as the month's current version give ``unchanged``, nothing written.
`obserwator.store.series.build_series` and `obserwator.store.series.check_series`
hand a sub-daily series to `build_months` and `check_months`.
"""

from __future__ import annotations

import gzip
import hashlib
import io
import json
import math
import os
import re
import shutil
import socket
import tempfile
import uuid
import zipfile
import zlib
from array import array
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Any, Final, Literal
from urllib.parse import parse_qs

from obserwator._version import __version__
from obserwator.captures import Spooled, _instant, from_record
from obserwator.datasets import (
    CAPTURE_SCOPE,
    ArchiveFile,
    DatasetDescriptor,
    _archive_from_path,
    _license_document,
    _source_address,
    get_dataset,
    get_provider,
    resolve_dataset_key,
)
from obserwator.exceptions import (
    ObserwatorDataError,
    ObserwatorError,
    ObserwatorStoreConflictError,
)
from obserwator.messages import message, reason
from obserwator.models import Tier
from obserwator.providers.pl.imgw import _SERIES as _HYDRO_BACK_SERIES
from obserwator.store.series import (
    _FLAGS,
    SERIES_SCHEMA,
    SeriesState,
    _candidate_labels,
    _content_fields,
    _copy_hashed,
    _current_series,
    _hydro_year,
    _Input,
    _lines,
    _manifest,
    _next_month,
    _parse_time,
    _pick_current,
    _pyarrow,
    _read_versions,
    _report,
    _restore_archive,
    _reusable,
    _series_versions,
    _table_metadata,
)
from obserwator.store.types import (
    Cancel,
    Notice,
    NoticeHook,
    PlanAction,
    PlanItem,
    Progress,
    ProgressHook,
    SeriesReport,
    StorePlan,
)
from obserwator.store.writer import (
    _archive_slot_dir,
    _canonical,
    _cleanup,
    _fsync_dir,
    _publish_dir,
    _tier_fields,
    _utc,
    _validate_slot,
    _write_json,
    prepare_store,
)

_REACH: Final = 43
"""Days before a capture day whose hours its answers may hold (the plan's D9)."""
_TIERS: Final[tuple[Tier, ...]] = ("verified", "telemetry", "operational")
"""The tiers, highest first: the dictionary of the ``<V>_tier`` columns."""
# The tier index of an hour without a value, and the states of an input's hour: no
# record (0), a record without a value, a value.
_NONE: Final = 255
_ABSENT: Final = 1
_VALUE: Final = 2
_VALUE_FLAG: Final = _FLAGS.index("value")
_MISSING_FLAG: Final = _FLAGS.index("missing")
# hydro-back's series of a station below the address of its capture dataset.
_HYDRO_BACK: Final[Mapping[str, str]] = MappingProxyType(
    {path: variable for variable, path in _HYDRO_BACK_SERIES.items()}
)
# The telemetry's parameters: water level, discharge and water temperature.
_TELEMETRY_PARAMS: Final[Mapping[str, str]] = MappingProxyType(
    {"B00020S": "H", "B00050S": "Q", "B00100S": "T"}
)
# A row of a telemetry member at minute 00: code, parameter, month, day, hour, value.
_TELEMETRY_ROW: Final = re.compile(
    r"([^;]*);([^;]*);([0-9]{4}-[0-9]{2})-([0-9]{2}) ([0-9]{2}):00;([^;]*)"
)
_TELEMETRY_NONE: Final = 999.0
# The series of ČHMÚ's ``recent`` day files and of its validated hourly files.
_RECENT_SERIES: Final[Mapping[str, str]] = MappingProxyType(
    {"H": "H", "Q": "Q", "TH": "T"}
)
_RECENT_FILE: Final = re.compile(r"[0-9]{8}_(.+)\.json")
_HOURLY_SERIES: Final[Mapping[str, str]] = MappingProxyType({"HH": "H", "QH": "Q"})
_TIME: Final = "%Y-%m-%dT%H:%M:%SZ"
_ACTION_STATUS: Final[Mapping[SeriesState, Literal["current", "newer", "missing"]]] = (
    MappingProxyType({"current": "current", "outdated": "newer", "missing": "missing"})
)


@dataclass(frozen=True, order=True)
class _Month:
    """A calendar month, by its first day."""

    first: date

    @property
    def text(self) -> str:
        """``YYYY-MM``: the month's directory and slot selector."""
        return f"{self.first:%Y-%m}"

    @property
    def last(self) -> date:
        return _next_month(self.first) - timedelta(days=1)

    @property
    def hours(self) -> int:
        return 24 * self.last.day

    def hour(self, moment: datetime) -> int | None:
        """The index of a UTC hour in the month; None for an hour of another month."""
        if (moment.year, moment.month) != (self.first.year, self.first.month):
            return None
        return (moment.day - 1) * 24 + moment.hour

    def stamp(self, hour: int) -> str:
        """The start of an hour of the month, ``YYYY-MM-DDTHH:MM:SSZ``."""
        return self.time(hour).strftime(_TIME)

    def time(self, hour: int) -> datetime:
        """The start of an hour of the month (UTC)."""
        start = datetime(self.first.year, self.first.month, 1, tzinfo=UTC)
        return start + timedelta(hours=hour)


def _months(start: date, end: date) -> list[_Month]:
    """Every month from the month of ``start`` to the month of ``end``."""
    months: list[_Month] = []
    first = start.replace(day=1)
    while first <= end:
        months.append(_Month(first))
        first = _next_month(first)
    return months


@dataclass(frozen=True)
class _Slot:
    """An input file of the raw root: its dataset, its place in ``inputs``, its months."""

    source: DatasetDescriptor
    order: int
    archive: ArchiveFile
    months: tuple[_Month, ...]


def _held_months(source: DatasetDescriptor, archive: ArchiveFile) -> tuple[_Month, ...]:
    """The months a file may hold hours of: of its period; of a capture day, its reach."""
    assert archive.period_start is not None and archive.period_end is not None
    start, end = archive.period_start, archive.period_end
    if source.archive_scope == CAPTURE_SCOPE:
        start, end = start - timedelta(days=_REACH), start - timedelta(days=1)
    return tuple(_months(start, end))


def _slots(raw: Path, descriptor: DatasetDescriptor) -> list[_Slot]:
    """Every slot of the inputs of a sub-daily series, in ``inputs`` and slot order."""
    top = raw / "archives" / "versions"
    found: list[_Slot] = []
    for order, key in enumerate(descriptor.inputs or ()):
        source = get_dataset(key)
        assert source.server_dir is not None
        base = top / PurePosixPath(source.server_dir)
        if not base.is_dir():
            continue
        names: dict[Path, str] = {}
        for sidecar in base.rglob("*.meta.json"):
            names.setdefault(
                sidecar.parent.parent, sidecar.name.removesuffix(".meta.json")
            )
        for slot_dir in sorted(names):
            folder = slot_dir.parent.relative_to(top).as_posix()
            archive = _archive_from_path(key, f"{folder}/{names[slot_dir]}")
            # The files of another dataset of the directory are no input of this one.
            if archive is None or (
                _archive_slot_dir(archive.server_path)
                != slot_dir.relative_to(raw).as_posix()
            ):
                continue
            found.append(_Slot(source, order, archive, _held_months(source, archive)))
    return found


def _current(raw: Path, slot: _Slot) -> _Input | None:
    """
    The current version of an input's slot, checked against its dataset and slot.

    Raises
    ------
    ObserwatorError, ValueError, KeyError, TypeError
        If a version of the slot is broken, of another dataset or of another slot.
    """
    archive = slot.archive
    relative = _archive_slot_dir(archive.server_path)
    current = _pick_current(
        _read_versions(raw, relative, PurePosixPath(archive.server_path).name)
    )
    if current is None:
        return None
    # A raw root written before a dataset was renamed holds its old key (ADR-028).
    stored = current.meta.get("dataset")
    if not isinstance(stored, str) or resolve_dataset_key(stored) != slot.source.key:
        raise ObserwatorDataError(
            message("series.version_belongs_another_dataset", relative=current.relative)
        )
    restored = _restore_archive(slot.source.key, current.meta)
    if _archive_slot_dir(restored.server_path) != relative:
        raise ObserwatorDataError(
            message(
                "series.version_does_not_match_slot",
                relative=current.relative,
                slot=relative,
            )
        )
    return _Input(archive, current)


class _Tier:
    """
    The records of one input in a month: per station and variable, an hour's state.

    A series holds the values of the month's hours and their states: no record, a
    record without a value, or a value. A record put later replaces the one of its
    hour, so an input read in time order keeps the latest record of every hour.
    """

    def __init__(self, hours: int) -> None:
        self.hours = hours
        self.series: dict[tuple[str, str], tuple[array[float], bytearray]] = {}
        self.days = bytearray(hours // 24)

    def put(self, station: str, variable: str, hour: int, value: float | None) -> None:
        """Record the value of an hour, or that it has none."""
        entry = self.series.get((station, variable))
        if entry is None:
            entry = (array("d", bytes(8 * self.hours)), bytearray(self.hours))
            self.series[(station, variable)] = entry
        if value is None:
            entry[1][hour] = _ABSENT
        else:
            entry[0][hour] = value
            entry[1][hour] = _VALUE
        self.days[hour // 24] = 1

    def valued(self) -> bool:
        """Whether an hour of the month has a value."""
        return any(_VALUE in states for _, states in self.series.values())


@dataclass(frozen=True)
class _Reading:
    """What the parsers of an input need: the month, the station grammar, its address."""

    month: _Month
    code: re.Pattern[str]
    address: str


def _full_hour(text: object) -> datetime | None:
    """The UTC start of a full hour given as ISO 8601 with a zone; None for others."""
    if not isinstance(text, str):
        return None
    try:
        moment = datetime.fromisoformat(text)
    except ValueError:
        return None
    if moment.tzinfo is None:
        return None
    moment = moment.astimezone(UTC)
    return None if moment.minute or moment.second or moment.microsecond else moment


def _value(raw: object) -> float | None | Literal[False]:
    """The value of a point: a finite number, None for null (no value), else False."""
    if raw is None:
        return None
    if isinstance(raw, bool) or not isinstance(raw, int | float):
        return False
    try:
        number = float(raw)
    except OverflowError:
        return False
    return number if math.isfinite(number) else False


def _json(content: bytes) -> object:
    """The JSON of an answer's body; None for a body that is no JSON."""
    try:
        return json.loads(content)
    except (ValueError, RecursionError):
        return None


def _put_points(
    tier: _Tier,
    station: str,
    variable: str,
    points: Iterable[tuple[object, object]],
    reading: _Reading,
    *,
    before: date | None,
) -> bool:
    """
    Put the ``(time, value)`` points at full hours of the month; whether any was.

    ``before`` keeps only the hours of the days before it: the closed days of an
    answer (the plan's D9).
    """
    held = False
    for when, raw in points:
        moment = _full_hour(when)
        if moment is None or (before is not None and moment.date() >= before):
            continue
        hour = reading.month.hour(moment)
        value = _value(raw)
        if hour is None or value is False:
            continue
        tier.put(station, variable, hour, value)
        held = True
    return held


def _hydro_back(answer: Spooled, reading: _Reading, tier: _Tier) -> bool:
    """
    hydro-back's H, Q or T of one station (``status/data``, ``discharge``, ``water-temperature``).

    The station is the ``id`` of the address; of the body only ``operational``:
    its entries at full hours of the days before the answer's UTC day.
    """
    base, _, query = answer.address.partition("?")
    prefix = f"{reading.address}/"
    variable = _HYDRO_BACK.get(base[len(prefix) :]) if base.startswith(prefix) else None
    codes = parse_qs(query).get("id", [])
    if variable is None or len(codes) != 1 or not reading.code.fullmatch(codes[0]):
        return False
    body = _json(answer.content)
    entries = body.get("operational") if isinstance(body, dict) else None
    if not isinstance(entries, list):
        return False
    return _put_points(
        tier,
        codes[0],
        variable,
        (
            (entry.get("date"), entry.get("value"))
            for entry in entries
            if isinstance(entry, dict)
        ),
        reading,
        before=_instant(answer.time).date(),
    )


def _chmu_recent(answer: Spooled, reading: _Reading, tier: _Tier) -> bool:
    """
    ČHMÚ's ``recent`` day file of one station, ``<YYYYMMDD>_<WIGOS>.json``.

    The series ``H``, ``Q`` and ``TH`` of the station's object: their points at full
    hours of the days before the answer's UTC day.
    """
    head, _, name = answer.address.partition("?")[0].rpartition("/")
    match = _RECENT_FILE.fullmatch(name)
    if head != reading.address or match is None or not reading.code.fullmatch(match[1]):
        return False
    station = match[1]
    body = _json(answer.content)
    objects = body.get("objList") if isinstance(body, dict) else None
    before = _instant(answer.time).date()
    held = False
    for item in objects if isinstance(objects, list) else ():
        if not isinstance(item, dict) or item.get("objID") != station:
            continue
        series = item.get("tsList")
        for entry in series if isinstance(series, list) else ():
            if not isinstance(entry, dict):
                continue
            con, points = entry.get("tsConID"), entry.get("tsData")
            variable = _RECENT_SERIES.get(con) if isinstance(con, str) else None
            if variable is None or not isinstance(points, list):
                continue
            pairs = (
                (point.get("dt"), point.get("value"))
                for point in points
                if isinstance(point, dict)
            )
            if _put_points(tier, station, variable, pairs, reading, before=before):
                held = True
    return held


def _telemetry(item: _Input, data: bytes, reading: _Reading, tier: _Tier) -> bool:
    """
    IMGW-PIB's telemetry of a month: the rows at minute 00 of every ``.csv`` member.

    Rows ``code;param;YYYY-MM-DD HH:MM;value`` of ``B00020S`` (H), ``B00050S`` (Q)
    and ``B00100S`` (T); ``999`` is no value and a decimal comma is read as a point.

    Raises
    ------
    ObserwatorDataError
        If the zip cannot be read.
    """
    month, days = reading.month.text, reading.month.last.day
    codes: dict[str, bool] = {}
    held = False
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as package:
            for info in sorted(package.infolist(), key=lambda entry: entry.filename):
                if info.is_dir() or not info.filename.lower().endswith(".csv"):
                    continue
                with (
                    package.open(info) as member,
                    io.TextIOWrapper(
                        member, encoding="utf-8", errors="replace"
                    ) as rows,
                ):
                    for line in rows:
                        row = _TELEMETRY_ROW.fullmatch(line.strip())
                        if row is None or row[3] != month:
                            continue
                        variable = _TELEMETRY_PARAMS.get(row[2].strip())
                        day, hour, code = int(row[4]), int(row[5]), row[1].strip()
                        if variable is None or not 1 <= day <= days or hour > 23:
                            continue
                        if code not in codes:
                            codes[code] = reading.code.fullmatch(code) is not None
                        try:
                            number = float(row[6].strip().replace(",", "."))
                        except ValueError:
                            continue
                        if not codes[code] or not math.isfinite(number):
                            continue
                        value = None if number == _TELEMETRY_NONE else number
                        tier.put(code, variable, (day - 1) * 24 + hour, value)
                        held = True
    except (
        zipfile.BadZipFile,
        zlib.error,
        EOFError,
        OSError,
        NotImplementedError,
        RuntimeError,
        ValueError,
    ) as exc:
        raise ObserwatorDataError(
            message(
                "series.input_unreadable",
                relative=item.version.relative,
                reason=reason(exc),
            )
        ) from exc
    return held


def _chmu_hourly(item: _Input, data: bytes, reading: _Reading, tier: _Tier) -> bool:
    """
    ČHMÚ's validated hours of a station's year, ``H_<WIGOS>_HQ_<YYYY>.json``.

    The ``DT,VAL`` rows of ``HH`` (H) and ``QH`` (Q) at full hours of the month;
    null is no value.

    Raises
    ------
    ObserwatorDataError
        If the file is no JSON object of the station of its name.
    """
    filename = item.version.relative
    station = item.archive.station_code
    try:
        body = json.loads(data)
    except (ValueError, RecursionError) as exc:
        raise ObserwatorDataError(
            message(
                "chmu.invalid_hm_file",
                filename=filename,
                location="$",
                reason=reason(exc),
            )
        ) from exc
    if not isinstance(body, dict):
        raise ObserwatorDataError(
            message(
                "chmu.invalid_hm_file",
                filename=filename,
                location="$",
                reason=message("chmu.root_value_not_object"),
            )
        )
    if station is None or body.get("objID") != station:
        raise ObserwatorDataError(
            message(
                "chmu.invalid_hm_file",
                filename=filename,
                location="objID",
                reason=message(
                    "chmu.code_does_not_match_file",
                    obj_id=body.get("objID"),
                    code=station,
                ),
            )
        )
    held = False
    series = body.get("tsList")
    for entry in series if isinstance(series, list) else ():
        if not isinstance(entry, dict):
            continue
        name, collection = entry.get("tsConID"), entry.get("tsData")
        variable = _HOURLY_SERIES.get(name) if isinstance(name, str) else None
        table = collection.get("data") if isinstance(collection, dict) else None
        rows = table.get("values") if isinstance(table, dict) else None
        if variable is None or not isinstance(rows, list):
            continue
        pairs = (
            (row[0], row[1]) for row in rows if isinstance(row, list) and len(row) == 2
        )
        if _put_points(tier, station, variable, pairs, reading, before=None):
            held = True
    return held


# The parsers of the answers of a capture dataset and of the files of the others.
_ANSWER_PARSERS: Final[Mapping[str, Callable[[Spooled, _Reading, _Tier], bool]]] = (
    MappingProxyType(
        {"pl.imgw.hydro_operational": _hydro_back, "cz.chmu.hydro_recent": _chmu_recent}
    )
)
_FILE_PARSERS: Final[Mapping[str, Callable[[_Input, bytes, _Reading, _Tier], bool]]] = (
    MappingProxyType(
        {"pl.imgw.hydro_telemetry": _telemetry, "cz.chmu.hydro_hourly": _chmu_hourly}
    )
)


def _answers(item: _Input, data: bytes) -> Iterator[Spooled]:
    """
    The answers of a sealed capture in file order, each with its body.

    The file is sorted by time, address and SHA-256 (`obserwator.store.captures.encode`),
    so a later answer of an hour comes later. A ``seen`` line repeats the answer before
    it from its address and is skipped: no record of its own.

    Raises
    ------
    ObserwatorDataError
        If the file is no gzip-compressed JSON Lines of answers.
    """
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(data), mode="rb") as stream:
            for line in stream:
                if not line.strip():
                    continue
                record = json.loads(line)
                if not (isinstance(record, dict) and record.get("seen") is True):
                    yield from_record(record)
    except (OSError, EOFError, zlib.error, ValueError) as exc:
        raise ObserwatorDataError(
            message(
                "captures.corrupt_capture",
                version=item.version.relative,
                reason=reason(exc),
            )
        ) from exc


def _parse(item: _Input, slot: _Slot, tier: _Tier, reading: _Reading) -> bool:
    """
    Put the records of the month of one input version into its tier.

    Returns
    -------
    bool
        Whether the version holds a record of the month: an input of the version.

    Raises
    ------
    ObserwatorDataError
        If the file does not match its sidecar's checksum or cannot be read.
    OSError
        If the file cannot be read.
    """
    data = item.version.file.read_bytes()
    if hashlib.sha256(data).hexdigest() != item.version.sha256:
        raise ObserwatorDataError(
            message(
                "series.checksum_does_not_match_sidecar", relative=item.version.relative
            )
        )
    if slot.source.archive_scope != CAPTURE_SCOPE:
        return _FILE_PARSERS[slot.source.key](item, data, reading, tier)
    parse = _ANSWER_PARSERS[slot.source.key]
    held = False
    for answer in _answers(item, data):
        if answer.status == 200 and parse(answer, reading, tier):
            held = True
    return held


@dataclass
class _MonthInputs:
    """What the inputs of a month hold: one tier per input, the versions read, failures."""

    tiers: list[_Tier]
    read: list[_Input] = field(default_factory=list)
    contributors: list[_Input] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)
    cancelled: bool = False


class _Inputs:
    """The input slots of a sub-daily series and their current versions, each read once."""

    def __init__(self, raw: Path, descriptor: DatasetDescriptor) -> None:
        self.raw = raw
        self.descriptor = descriptor
        self.ranks = [
            _TIERS.index(get_dataset(key).tier) for key in descriptor.inputs or ()
        ]
        self._code = re.compile(get_provider(descriptor.provider).station_code_pattern)
        self._by_month: dict[_Month, list[_Slot]] = {}
        for slot in _slots(raw, descriptor):
            for month in slot.months:
                self._by_month.setdefault(month, []).append(slot)
        self._versions: dict[tuple[str, str], _Input | str | None] = {}

    def months(self, start: date | None, end: date | None) -> tuple[list[_Month], bool]:
        """
        The months to build and whether they were given.

        Both bounds give every month they touch; otherwise the months an input may
        hold, within the bound given.
        """
        if start is not None and end is not None:
            return _months(start, end), True
        return [
            month
            for month in sorted(self._by_month)
            if (start is None or month.last >= start)
            and (end is None or month.first <= end)
        ], False

    def _version(self, slot: _Slot) -> _Input | str | None:
        """The current version of a slot, or why it cannot be read."""
        key = (slot.source.key, slot.archive.server_path)
        if key not in self._versions:
            try:
                self._versions[key] = _current(self.raw, slot)
            except (ObserwatorError, ValueError, KeyError, TypeError) as exc:
                self._versions[key] = reason(exc)
        return self._versions[key]

    def read(
        self,
        month: _Month,
        *,
        cancel: Cancel | None,
        on_progress: ProgressHook | None,
    ) -> _MonthInputs:
        """Read every input of a month; the first unreadable one ends the reading."""
        result = _MonthInputs([_Tier(month.hours) for _ in self.ranks])
        picked: list[tuple[_Slot, _Input]] = []
        for slot in self._by_month.get(month, ()):
            version = self._version(slot)
            if isinstance(version, str):
                result.problems.append(version)
            elif version is not None:
                picked.append((slot, version))
                result.read.append(version)
        if result.problems:
            return result
        for index, (slot, item) in enumerate(picked, start=1):
            if cancel is not None and cancel():
                result.cancelled = True
                return result
            reading = _Reading(month, self._code, _source_address(slot.source))
            try:
                if _parse(item, slot, result.tiers[slot.order], reading):
                    result.contributors.append(item)
            except (ObserwatorDataError, OSError) as exc:
                result.problems.append(reason(exc))
                return result
            if on_progress is not None:
                on_progress(
                    Progress(
                        index,
                        len(picked),
                        "archive",
                        "parsed",
                        message("series.archive_read", relative=item.version.relative),
                    )
                )
        return result


@dataclass(frozen=True)
class _Merged:
    """The points of a month: per station the value and tier of each variable's hours."""

    stations: dict[str, dict[str, tuple[array[float], bytearray]]]
    days: list[int]

    @property
    def rows(self) -> list[int]:
        """The hours of every station file: every hour of each day with a record."""
        return [day * 24 + hour for day in self.days for hour in range(24)]

    @property
    def tiers(self) -> list[int]:
        """The indices in `_TIERS` of the points with a value, highest first."""
        found = {
            label
            for columns in self.stations.values()
            for _, labels in columns.values()
            for label in set(labels)
        }
        return sorted(found - {_NONE})


def _merge(read: _MonthInputs, ranks: Sequence[int], hours: int) -> _Merged:
    """
    The winning value of every station, variable and hour, and the days with a record.

    The first input (in ``inputs`` order) with a value of an hour gives it and its tier;
    a station without any value is left out.
    """
    known = bytearray(hours // 24)
    for tier in read.tiers:
        known = bytearray(a | b for a, b in zip(known, tier.days, strict=True))
    stations: dict[str, dict[str, tuple[array[float], bytearray]]] = {}
    keys = sorted({key for tier in read.tiers for key in tier.series})
    for station, variable in keys:
        entries = [
            (rank, tier.series[(station, variable)])
            for rank, tier in zip(ranks, read.tiers, strict=True)
            if (station, variable) in tier.series
        ]
        values = array("d", bytes(8 * hours))
        labels = bytearray([_NONE]) * hours
        for hour in range(hours):
            for rank, (found, states) in entries:
                if states[hour] == _VALUE:
                    values[hour], labels[hour] = found[hour], rank
                    break
        if labels.count(_NONE) < hours:
            stations.setdefault(station, {})[variable] = (values, labels)
    return _Merged(stations, [day for day, flag in enumerate(known) if flag])


def _station_table(
    pa: Any,
    descriptor: DatasetDescriptor,
    month: _Month,
    rows: Sequence[int],
    columns: Mapping[str, tuple[array[float], bytearray]],
    *,
    tiered: bool,
) -> Any:
    """
    The Parquet table of one station of a month version.

    ``time`` (``timestamp[us, tz=UTC]``), ``hydro_year`` and per variable
    ``<V>_value`` and ``<V>_flag``, with ``<V>_tier`` when the version has more than
    one tier (null without a value).
    """
    data: dict[str, Any] = {
        "time": pa.array(
            [month.time(hour) for hour in rows], pa.timestamp("us", tz="UTC")
        ),
        "hydro_year": pa.array([_hydro_year(month.first)] * len(rows), pa.int32()),
    }
    flags, tiers = pa.array(_FLAGS, pa.string()), pa.array(_TIERS, pa.string())
    for variable in descriptor.variables:
        series = columns.get(variable)
        labels = [_NONE] * len(rows) if series is None else [series[1][h] for h in rows]
        values = [
            None if series is None or label == _NONE else series[0][hour]
            for hour, label in zip(rows, labels, strict=True)
        ]
        data[f"{variable}_value"] = pa.array(values, pa.float64())
        data[f"{variable}_flag"] = pa.DictionaryArray.from_arrays(
            pa.array(
                [_MISSING_FLAG if label == _NONE else _VALUE_FLAG for label in labels],
                pa.int8(),
            ),
            flags,
        )
        if tiered:
            data[f"{variable}_tier"] = pa.DictionaryArray.from_arrays(
                pa.array(
                    [None if label == _NONE else label for label in labels], pa.int8()
                ),
                tiers,
            )
    return pa.table(data).replace_schema_metadata(_table_metadata(descriptor))


def _coverage(
    unit: str,
    rows: Sequence[int],
    series: tuple[array[float], bytearray] | None,
    month: _Month,
) -> dict[str, Any]:
    """
    ``series.json`` coverage of one variable of a station of a month.

    Gaps are the runs of hours without a value between the first and the last hour
    with one; the hours of days without any record are unknown, never gaps.
    """
    labels = series[1] if series is not None else None
    valued = [hour for hour in rows if labels is not None and labels[hour] != _NONE]
    runs: list[list[int]] = []
    if labels is not None and valued:
        for hour in rows:
            if not valued[0] < hour < valued[-1] or labels[hour] != _NONE:
                continue
            if runs and runs[-1][1] == hour - 1:
                runs[-1][1] = hour
            else:
                runs.append([hour, hour])
    return {
        "unit": unit,
        "first": month.stamp(valued[0]) if valued else None,
        "last": month.stamp(valued[-1]) if valued else None,
        "with_value": len(valued),
        "accumulated": 0,
        "gaps": [[month.stamp(start), month.stamp(end)] for start, end in runs],
    }


def _periods(month: _Month, days: Sequence[int]) -> list[list[str]]:
    """The days with a record as closed ranges of ISO dates."""
    spans: list[list[int]] = []
    for day in days:
        if spans and spans[-1][1] == day - 1:
            spans[-1][1] = day
        else:
            spans.append([day, day])
    return [
        [
            (month.first + timedelta(days=start)).isoformat(),
            (month.first + timedelta(days=end)).isoformat(),
        ]
        for start, end in spans
    ]


# One month built: its report and its stations.
_Built = tuple[SeriesReport, frozenset[str]]


def _write_month(
    path: Path,
    inputs: _Inputs,
    month: _Month,
    read: _MonthInputs,
    merged: _Merged,
    *,
    pa: Any,
    pq: Any,
    on_progress: ProgressHook | None,
    on_notice: NoticeHook | None,
    cancelled: Callable[[], bool],
    published: Callable[[], None],
) -> _Built:
    """
    Write the version of a month into the data root and publish it atomically.

    As a daily version (`obserwator.store.series.build_series`): the station files and
    ``series.json`` staged in ``.incoming``, then published by hard links with the
    sidecar last, into ``series/versions/<slug>/<YYYY-MM>/<label>_<sha8>/``.
    """
    descriptor = inputs.descriptor
    manifest = _manifest(read.contributors)
    sources = [item.version.file for item in read.contributors]
    rows, present = merged.rows, merged.tiers
    # The first write of a new data root creates its marker (DEV-19.13).
    prepare_store(path, kind="data")
    incoming = path / ".incoming"
    incoming.mkdir(exist_ok=True)
    _cleanup(incoming, on_notice=on_notice)
    staging = incoming / f"{socket.gethostname()}_{os.getpid()}_{uuid.uuid4().hex}"
    (staging / "stations").mkdir(parents=True)
    try:
        index_stations: dict[str, dict[str, Any]] = {}
        with tempfile.TemporaryDirectory(prefix="obserwator-series-") as local:
            codes = sorted(merged.stations)
            for number, code in enumerate(codes, start=1):
                if cancelled():
                    return _report("cancelled", sources=sources), frozenset()
                columns = merged.stations[code]
                table = _station_table(
                    pa, descriptor, month, rows, columns, tiered=len(present) > 1
                )
                built = Path(local) / f"{code}.parquet"
                pq.write_table(table, built)
                digest = _copy_hashed(built, staging / "stations" / f"{code}.parquet")
                built.unlink()
                index_stations[code] = {
                    "file": f"stations/{code}.parquet",
                    "sha256": digest,
                    "rows": len(rows),
                    "variables": {
                        variable: _coverage(unit, rows, columns.get(variable), month)
                        for variable, unit in descriptor.variables.items()
                    },
                }
                if on_progress is not None:
                    on_progress(
                        Progress(
                            number,
                            len(codes),
                            "station",
                            "written",
                            message("series.station_progress", code=code),
                        )
                    )
        _fsync_dir(staging / "stations")
        lines = _lines(descriptor)
        series = {
            "schema": SERIES_SCHEMA,
            "dataset": descriptor.key,
            "year_type": descriptor.year_type,
            "month": month.text,
            "tiers": [_TIERS[index] for index in present],
            "periods": _periods(month, merged.days),
            "stations": index_stations,
            **lines.fields(),
        }
        content = _canonical(series)
        sha = hashlib.sha256(content).hexdigest()
        _write_json(staging / "series.json", series)
        modified = [
            moment
            for item in read.contributors
            if (moment := _parse_time(item.version.http.get("last_modified")))
        ]
        now = datetime.now(UTC)
        label = (max(modified) if modified else now).date().isoformat()
        provider = get_provider(descriptor.provider)
        license_info = _license_document(descriptor.license)
        license_info["attribution"] = ". ".join(lines.attribution)
        source_files = [
            {
                "name": item.version.file.name,
                "file": item.version.relative,
                "sha256": item.version.sha256,
                "label": item.version.label,
                **_content_fields(item.version.meta),
            }
            for item in sorted(
                read.contributors, key=lambda entry: entry.version.relative
            )
        ]

        def sidecar(version_label: str) -> dict[str, Any]:
            return {
                "schema": "obserwator-meta/1",
                "producer": "obserwator",
                "producer_version": __version__,
                "dataset": descriptor.key,
                "country": provider.country,
                "provider": provider.id,
                # The call of the version (command_for_version): its month.
                "request": {"dataset": descriptor.key, "month": month.text},
                "license": license_info,
                "downloaded_at": _utc(now),
                "sha256": sha,
                "size_bytes": len(content),
                # Its tier and publication state (ADR-030 D6): of its lowest input.
                **_tier_fields(descriptor),
                "extra": {
                    "version": {"label": version_label, "label_source": "inputs"},
                    "derived": "series",
                    "series_schema": SERIES_SCHEMA,
                    "source_files": source_files,
                },
            }

        if cancelled():
            return _report("cancelled", sources=sources), frozenset()
        slot = f"series/versions/{descriptor.slug}/{month.text}"
        parent = _validate_slot(path, slot)
        parent.mkdir(parents=True, exist_ok=True)
        # As a daily version: identical series.json of other inputs gets a stable
        # manifest suffix; an older version of the same inputs is not current, so this
        # build takes the next free label and becomes current.
        attempts = sum(1 for _ in parent.iterdir()) + 2
        for candidate in _candidate_labels(label, manifest, attempts=attempts):
            target = _validate_slot(path, f"{slot}/{candidate}_{sha[:8]}")
            meta_path = staging / "series.json.meta.json"
            meta_path.unlink(missing_ok=True)
            _write_json(meta_path, sidecar(candidate))
            _fsync_dir(staging)
            try:
                _publish_dir(staging, target, "series.json.meta.json")
            except FileExistsError:
                winner = _current_series(_series_versions(path, descriptor, month.text))
                if (
                    winner is not None
                    and winner.path.parent == target
                    and winner.manifest == manifest
                ):
                    # A concurrent build of the same inputs published first.
                    return _report(
                        "unchanged",
                        version=target / "series.json",
                        stations=len(index_stations),
                        sources=sources,
                    ), frozenset(index_stations)
                continue
            published()
            return _report(
                "new",
                version=target / "series.json",
                stations=len(index_stations),
                sources=sources,
            ), frozenset(index_stations)
        raise ObserwatorStoreConflictError(
            message("series.series_version_directory_collision", parent=parent)
        )
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def _build_month(
    path: Path,
    inputs: _Inputs,
    month: _Month,
    *,
    explicit: bool,
    pa: Any,
    pq: Any,
    on_progress: ProgressHook | None,
    on_notice: NoticeHook | None,
    cancel: Cancel | None,
    published: Callable[[], None],
) -> _Built | None:
    """The version of one month; None for a month not given whose inputs hold no value."""
    descriptor = inputs.descriptor
    read = inputs.read(month, cancel=cancel, on_progress=on_progress)
    sources = [item.version.file for item in read.read]
    if read.cancelled:
        return _report("cancelled", sources=sources), frozenset()
    if read.problems:
        for problem in read.problems:
            if on_notice is not None:
                on_notice(Notice("warning", "archive_failed", problem))
        return _report("failed", sources=sources, problems=read.problems), frozenset()
    merged = _merge(read, inputs.ranks, month.hours)
    if not merged.stations:
        if not explicit:
            return None
        problem = message(
            "series.month_without_value", key=descriptor.key, month=month.text
        )
        return _report("failed", sources=sources, problems=[problem]), frozenset()
    current = _current_series(_series_versions(path, descriptor, month.text))
    if current is not None and _reusable(
        current, _manifest(read.contributors), descriptor, None
    ):
        series = json.loads(current.path.read_text(encoding="utf-8"))
        recorded = [
            inputs.raw / PurePosixPath(source["file"])
            for source in current.meta["extra"]["source_files"]
        ]
        if on_progress is not None:
            on_progress(
                Progress(
                    1,
                    1,
                    "series",
                    "unchanged",
                    message(
                        "series.month_inputs_unchanged",
                        slug=descriptor.slug,
                        month=month.text,
                    ),
                )
            )
        return _report(
            "unchanged",
            version=current.path,
            stations=len(series["stations"]),
            sources=recorded,
        ), frozenset(series["stations"])

    def cancelled() -> bool:
        return cancel is not None and cancel()

    return _write_month(
        path,
        inputs,
        month,
        read,
        merged,
        pa=pa,
        pq=pq,
        on_progress=on_progress,
        on_notice=on_notice,
        cancelled=cancelled,
        published=published,
    )


def _summary(descriptor: DatasetDescriptor, built: Sequence[_Built]) -> SeriesReport:
    """The report of a build of months: the months' reports and their sums."""
    reports = [report for report, _ in built]
    statuses = {report.status for report in reports}
    status: Literal["new", "unchanged", "cancelled", "failed"]
    if "cancelled" in statuses:
        status = "cancelled"
    elif statuses <= {"failed"}:
        status = "failed"
    elif "new" in statuses:
        status = "new"
    else:
        status = "unchanged"
    problems = [problem for report in reports for problem in report.problems]
    if not reports:
        problems.append(message("series.inputs_hold_no_value", key=descriptor.key))
    return SeriesReport(
        status,
        next((r.version for r in reversed(reports) if r.version is not None), None),
        len(frozenset().union(*(codes for _, codes in built))),
        tuple(
            dict.fromkeys(path for report in reports for path in report.source_files)
        ),
        tuple(dict.fromkeys(problems)),
        tuple(file for report in reports for file in report.files),
        months=tuple(reports),
    )


def build_months(
    path: Path,
    raw: Path,
    descriptor: DatasetDescriptor,
    /,
    *,
    start: date | None,
    end: date | None,
    on_progress: ProgressHook | None = None,
    on_notice: NoticeHook | None = None,
    cancel: Cancel | None = None,
) -> SeriesReport:
    """
    Build the version of every month of a sub-daily series (``series build``).

    One month at a time, from the current input versions of the raw root (the
    module's rules); a month whose inputs and lines are those of its current version
    is ``unchanged``.

    Parameters
    ----------
    path : pathlib.Path
        The data root (checked by the caller); its marker is written with its
        first version.
    raw : pathlib.Path
        The raw root, only read.
    descriptor : DatasetDescriptor
        A sub-daily series (`obserwator.datasets.monthly_series`).
    start, end : datetime.date or None
        Both: every month from the month of ``start`` to that of ``end``, each
        reported (a month whose inputs hold no value fails, its problem naming
        it). Otherwise the months an input may hold (the 43 days before a capture
        day, the month of a telemetry zip, the year of a ČHMÚ file), within the
        bound given; a month whose inputs hold no value is skipped.
    on_progress : ProgressHook or None, optional
        Called after each input read and each station file written, once for an
        unchanged month and after each month (unit ``month``).
    on_notice : NoticeHook or None, optional
        Receives an ``archive_failed`` warning for every unreadable input, a
        ``leftover_incoming`` warning for every removed staging directory and the
        ``license_terms`` notice once a month version is new.
    cancel : Cancel or None, optional
        Polled between steps; once it returns ``True`` the build stops and the
        month being built is ``cancelled``, nothing of it published.

    Returns
    -------
    SeriesReport
        The months' reports in ``months`` (month order); ``cancelled`` when the
        build was, ``failed`` when every month failed or none had a value,
        ``new`` when a month is new, else ``unchanged``. ``version`` is that of
        the last month with a version, ``stations`` the distinct stations of the
        months, ``source_files``, ``files`` and ``problems`` those of every month.

    Raises
    ------
    ObserwatorStoreDependencyError
        If ``pyarrow>=15`` is not installed.
    ObserwatorStoreConflictError
        If a version cannot be published atomically or its directory collides
        with a different version.
    """
    pa, pq = _pyarrow()
    if cancel is not None and cancel():
        return SeriesReport("cancelled", None, 0, (), (), months=())
    inputs = _Inputs(raw, descriptor)
    months, explicit = inputs.months(start, end)
    if not months:
        problem = message("series.no_inputs_of_months", key=descriptor.key)
        return SeriesReport("failed", None, 0, (), (problem,), months=())
    noticed = False

    def published() -> None:
        nonlocal noticed
        if not noticed and on_notice is not None:
            provider = get_provider(descriptor.provider)
            on_notice(
                Notice(
                    "info", "license_terms", provider.license_notice(_lines(descriptor))
                )
            )
        noticed = True

    built: list[_Built] = []
    for index, month in enumerate(months, start=1):
        if cancel is not None and cancel():
            built.append((_report("cancelled"), frozenset()))
            break
        outcome = _build_month(
            path,
            inputs,
            month,
            explicit=explicit,
            pa=pa,
            pq=pq,
            on_progress=on_progress,
            on_notice=on_notice,
            cancel=cancel,
            published=published,
        )
        if outcome is not None:
            built.append(outcome)
        if on_progress is not None:
            on_progress(
                Progress(
                    index,
                    len(months),
                    "month",
                    "skipped" if outcome is None else outcome[0].status,
                    message("series.month_progress", month=month.text),
                )
            )
        if outcome is not None and outcome[0].status == "cancelled":
            break
    return _summary(descriptor, built)


def _plan_item(item: _Input) -> PlanItem:
    """The plan item of an input version: current, its path in the raw root, signals."""
    http = item.version.http
    return PlanItem(
        archive=item.archive,
        status="current",
        local_path=Path(item.version.relative),
        local_sha256=item.version.sha256,
        remote_etag=http.get("etag"),
        remote_last_modified=http.get("last_modified"),
        content_length=http.get("content_length"),
        error=None,
        station_code=item.archive.station_code,
    )


def check_months(
    path: Path,
    raw: Path,
    descriptor: DatasetDescriptor,
    /,
    *,
    start: date | None,
    end: date | None,
    on_progress: ProgressHook | None = None,
    on_notice: NoticeHook | None = None,
    cancel: Cancel | None = None,
) -> StorePlan:
    """
    Plan the months of a sub-daily series offline (``series build --check``).

    The local input files are read, as `build_months` reads them, to tell which of
    them hold records of a month; nothing is written and no request is made.

    Parameters
    ----------
    path : pathlib.Path
        The data root (it need not exist).
    raw : pathlib.Path
        The raw root.
    descriptor : DatasetDescriptor
        A sub-daily series.
    start, end : datetime.date or None
        The months, as `build_months` chooses them.
    on_progress : ProgressHook or None, optional
        Called after each month checked (unit ``month``, its state).
    on_notice : NoticeHook or None, optional
        Receives an ``archive_failed`` warning for every unreadable input.
    cancel : Cancel or None, optional
        Polled before each month and each input; once it returns ``True`` the
        months left are not checked and the plan is ``cancelled``.

    Returns
    -------
    StorePlan
        ``series_state`` maps ``<slug>/<YYYY-MM>`` of every month the build would
        report to ``current``, ``outdated`` or ``missing``; one ``series build``
        action per such month (``current``, ``newer`` or ``missing``; a month given
        by both bounds whose inputs hold no value has that detail), one
        ``check_failed`` action per unreadable input and a ``missing`` action when
        no input lies in the chosen months. The items are the input versions that
        hold records of the months, each once: the ``source_files`` of the build.
    """
    inputs = _Inputs(raw, descriptor)
    months, explicit = inputs.months(start, end)
    items: dict[str, PlanItem] = {}
    actions: list[PlanAction] = []
    states: dict[str, SeriesState] = {}
    cancelled = False
    for index, month in enumerate(months, start=1):
        read = (
            None
            if cancel is not None and cancel()
            else inputs.read(month, cancel=cancel, on_progress=None)
        )
        if read is None or read.cancelled:
            cancelled = True
            break
        for problem in read.problems:
            actions.append(PlanAction("series build", "check_failed", problem))
            if on_notice is not None:
                on_notice(Notice("warning", "archive_failed", problem))
        valued = not read.problems and any(tier.valued() for tier in read.tiers)
        if not (read.problems or valued or explicit):
            continue
        current = _current_series(_series_versions(path, descriptor, month.text))
        state: SeriesState = "missing"
        if current is not None:
            reusable = _reusable(
                current, _manifest(read.contributors), descriptor, None
            )
            state = "current" if valued and reusable else "outdated"
        if read.problems or valued:
            detail = {
                "current": message(
                    "series.month_current", slug=descriptor.slug, month=month.text
                ),
                "outdated": message(
                    "series.month_needs_rebuild", slug=descriptor.slug, month=month.text
                ),
                "missing": message(
                    "series.month_missing", slug=descriptor.slug, month=month.text
                ),
            }[state]
        else:
            detail = message(
                "series.month_without_value", key=descriptor.key, month=month.text
            )
        actions.append(PlanAction("series build", _ACTION_STATUS[state], detail))
        states[f"{descriptor.slug}/{month.text}"] = state
        for item in read.contributors:
            items.setdefault(item.version.relative, _plan_item(item))
        if on_progress is not None:
            on_progress(
                Progress(
                    index,
                    len(months),
                    "month",
                    state,
                    message("series.month_progress", month=month.text),
                )
            )
    if not months:
        actions.append(
            PlanAction(
                "series build",
                "missing",
                message("series.no_inputs_of_months", key=descriptor.key),
            )
        )
    return StorePlan(
        schema="obserwator-plan/1",
        root=path,
        checked_at=datetime.now(UTC),
        items=tuple(items.values()),
        series_state=states,
        actions=tuple(actions),
        cancelled=cancelled,
    )
