"""
Exports of the store: archive records, station series and the station catalogs (ADR-014).

Every export is text lines or one plain file: the archive records of one version as
CSV or JSONL, one station's series as CSV, JSON (``obserwator-series-export/1``) or
Parquet, and the current station catalogs as GeoJSON (``obserwator-stations-export/1``)
or CSV. Every file carries the lines of its providers (ADR-012).
"""

from __future__ import annotations

import csv
import io
import json
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Literal, cast, overload

from obserwator._parsing.meteo import DATASET_ATTRIBUTES
from obserwator.attribution import Attribution
from obserwator.config import store_root
from obserwator.datasets import (
    _CATALOG_DATASETS,
    DatasetDescriptor,
    License,
    ProviderDescriptor,
    get_dataset,
    get_provider,
    providers,
)
from obserwator.exceptions import (
    ObserwatorCancelledError,
    ObserwatorDataError,
    ObserwatorStoreError,
    ObserwatorValidationError,
)
from obserwator.messages import message
from obserwator.models import Measurement, NormalizedRecord
from obserwator.output import OutputReport, Staging, plan_plain, refuse
from obserwator.store.catalog import DETAILS_SOURCE, RootArg, _catalog_lines
from obserwator.store.reader import (
    _archive_main,
    _open,
    _series_datasets,
    _series_path,
    _variables,
    current_version,
    read_archive,
    read_catalog,
    read_meta,
    read_series,
    read_series_index,
)
from obserwator.store.series import _lines, _pyarrow
from obserwator.store.types import (
    Cancel,
    Meta,
    Notice,
    NoticeHook,
    PathArg,
    Progress,
    ProgressHook,
    StationFeature,
    StationSeriesIndex,
)
from obserwator.store.writer import _canonical_text, _fsync_dir

SERIES_EXPORT_SCHEMA = "obserwator-series-export/1"
"""Schema of the JSON export of one station's series (Parquet: ``obserwator_schema``)."""
STATIONS_EXPORT_SCHEMA = "obserwator-stations-export/1"
"""Schema of the GeoJSON export of the station catalogs."""

_SERIES_FORMATS = ("csv", "json", "parquet")
_STATIONS_FORMATS = ("geojson", "csv")
_ARCHIVE_FORMATS = ("csv", "jsonl")
# Formats that are no text lines: one file, so they need output (REST attaches it).
_BINARY_FORMATS = ("parquet",)
_YEAR_TYPES = ("hydrological", "calendar")
_KINDS = ("hydro", "meteo")
_PROGRESS_ROWS = 256
_CANCELLED = message("export.cancelled")
# The trailing columns of the CSV of a series or of the stations (ADR-001 Q10, ADR-012).
_ATTRIBUTION_COLUMNS = (
    "attribution_source",
    "attribution_processed",
    "attribution",
    "terms_notice",
)
# Leading columns of the stations CSV; the other catalog properties follow sorted.
_STATION_COLUMNS = ("station_code", "name", "kind")


def _number(value: float) -> str:
    """Shortest round-trip decimal text with a dot and no exponent."""
    text = repr(float(value))
    return format(Decimal(text), "f") if "e" in text or "E" in text else text


def _timestamp(value: date | datetime | None) -> str:
    return "" if value is None else value.isoformat()


def _check_cancel(cancel: Cancel | None) -> None:
    if cancel is not None and cancel():
        raise ObserwatorCancelledError(_CANCELLED)


def _format(value: object, allowed: tuple[str, ...]) -> None:
    if value not in allowed:
        raise ObserwatorValidationError(
            message(
                "export.unsupported_export_format_available",
                value=value,
                allowed=", ".join(allowed),
            ),
            details={"option": "format", "value": str(value), "allowed": list(allowed)},
        )


def _file(output: PathArg) -> Path:
    """Absolute path of the one output file of an export; a directory is no file."""
    target = Path(output).expanduser().absolute()
    if target.is_dir():
        raise ObserwatorValidationError(
            message("export.output_is_directory", target=target),
            details={"option": "output", "value": str(target)},
        )
    return target


def _target(output: PathArg | None, *, force: bool) -> Path | None:
    """
    Check the output of an export before anything is read for it (DEV-19.6).

    ``None`` streams the lines (and ``force`` then has nothing to replace). A
    file is checked like the target list of any plain write: an existing file
    without ``force`` and a file in a store are a ``conflict`` that lists the
    path; a missing directory is created by the write (DEV-19.8).
    """
    if output is None:
        if force:
            raise ObserwatorValidationError(
                message("export.force_needs_output"), details={"option": "output"}
            )
        return None
    target = _file(output)
    refuse(plan_plain(target.parent, [target.name], force=force), single=True)
    return target


def _needs_output(format: object, output: object) -> None:
    """
    Refuse a binary format without ``output``: it has no text lines to stream.

    One check of every interface: the export functions, the catalog rule of the
    CLI and MCP, and MCP over HTTP; REST writes the file itself and attaches it.
    """
    if output is None and isinstance(format, str) and format.strip() in _BINARY_FORMATS:
        raise ObserwatorValidationError(
            message("export.binary_format_needs_output", format=format.strip()),
            details={"option": "output", "reason": "output_required"},
        )


def _license(descriptor: DatasetDescriptor, on_notice: NoticeHook | None) -> None:
    if on_notice is not None:
        on_notice(
            Notice(
                "info",
                "license_terms",
                get_provider(descriptor.provider).license_notice(_lines(descriptor)),
            )
        )


def _trailing(lines: tuple[str, ...], number: int, last: bool) -> str:
    """
    Cell of a trailing ``attribution`` or ``terms_notice`` column in data row ``number``.

    One line per cell from the first data row down, empty below; the last row
    of a table with fewer rows than lines holds the rest, joined with a line
    feed (Nogat DEV-20.5).
    """
    if number >= len(lines):
        return ""
    return "\n".join(lines[number:]) if last else lines[number]


def _flagged(rows: Iterable[list[str]]) -> Iterator[tuple[int, list[str], bool]]:
    """``(number, row, last)`` of every row, looking one row ahead."""
    iterator = iter(rows)
    current = next(iterator, None)
    number = 0
    while current is not None:
        following = next(iterator, None)
        yield number, current, following is None
        current, number = following, number + 1


def _with_lines(rows: Iterable[list[str]], lines: Attribution) -> Iterator[list[str]]:
    """Rows with the trailing ``attribution`` and ``terms_notice`` cells (DEV-20.5)."""
    for number, row, last in _flagged(rows):
        yield [
            *row,
            _trailing(lines.attribution, number, last),
            _trailing(lines.terms_notice, number, last),
        ]


def _field_names(name: str, descriptor: DatasetDescriptor) -> list[str]:
    """``<V>_quality`` and ``<V>_source_flag`` columns of the dataset's extra fields."""
    return [f"{name}_{field}" for field in descriptor.measurement_fields]


def _measurement_cells(
    measurement: Measurement | None, descriptor: DatasetDescriptor
) -> list[str]:
    """Value, flag and extra field cells of one variable; empty without a measurement."""
    if measurement is None:
        return [""] * (2 + len(descriptor.measurement_fields))
    cells = [
        "" if measurement.value is None else _number(measurement.value),
        measurement.flag,
    ]
    for field in descriptor.measurement_fields:
        value = getattr(measurement, field)
        cells.append("" if value is None else str(value))
    return cells


def _csv_lines(rows: Iterable[Sequence[str]]) -> Iterator[str]:
    """CSV text lines (comma, minimal quoting, CRLF) of cell rows."""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    for cells in rows:
        buffer.seek(0)
        buffer.truncate()
        writer.writerow(cells)
        yield buffer.getvalue()


def _csv_line(cells: Sequence[str]) -> str:
    return next(_csv_lines([cells]))


class _Lines:
    """
    Lines of one export: header lines, data rows with cancellation and progress, tail.

    ``count`` is the number of rows the lines carry when they are no rows (the
    columns of a document); progress then reports it instead of the lines.
    """

    def __init__(
        self,
        head: tuple[str, ...],
        rows: Iterable[str],
        *,
        total: int | None,
        label: str,
        on_progress: ProgressHook | None,
        cancel: Cancel | None,
        tail: tuple[str, ...] = (),
        count: int | None = None,
    ) -> None:
        self._head = head
        self._rows = rows
        self._total = total
        self._label = label
        self._on_progress = on_progress
        self._cancel = cancel
        self._tail = tail
        self._count = count
        self.written = 0

    def __iter__(self) -> Iterator[str]:
        yield from self._head
        for text in self._rows:
            yield text
            self.written += 1
            if self.written % _PROGRESS_ROWS == 0:
                _check_cancel(self._cancel)
                if self._total is not None and self._on_progress is not None:
                    self._on_progress(
                        Progress(
                            self.written,
                            self._total,
                            "row",
                            "written",
                            message(
                                "export.rows_written",
                                label=self._label,
                                written=self.written,
                            ),
                        )
                    )
        yield from self._tail

    def finish(self, message: str) -> None:
        if self._on_progress is not None:
            done = self.written if self._count is None else self._count
            total = done if self._total is None else self._total
            self._on_progress(Progress(done, total, "row", "written", message))


def _iterate(lines: _Lines, done: str) -> Iterator[str]:
    yield from lines
    lines.finish(done)


def _write(
    chunks: Iterable[bytes], target: Path, cancel: Cancel | None
) -> OutputReport:
    """
    Write ``chunks`` as the one plain file ``target``.

    The bytes go to a staging directory beside the target
    (``<dir>/.obserwator-incoming/<host>_<pid>_<token>/``), are hashed while they are
    written and fsynced, and the file is moved into place with ``os.replace``
    only when it is whole; cancellation, an error, SIGINT or SIGTERM leave the
    target as it was and remove the staging directory (DEV-19.7).
    """
    with Staging(target.parent) as staging:
        staged, size, sha256 = staging.write(chunks)
        _check_cancel(cancel)
        written = staging.commit(staged, target, size, sha256)
    _fsync_dir(target.parent)
    return OutputReport(target, (written,))


def _deliver(
    lines: _Lines, *, target: Path | None, cancel: Cancel | None, done: str
) -> OutputReport | Iterator[str]:
    """Return the lazy lines, or write them as the one plain file ``target`` (`_write`)."""
    if target is None:
        return _iterate(lines, done)
    report = _write((text.encode("utf-8") for text in lines), target, cancel)
    lines.finish(message("export.exported_to_file", done=done, target=target))
    return report


def _record_json(
    record: NormalizedRecord, descriptor: DatasetDescriptor
) -> dict[str, object]:
    return {
        "station_code": record.station_code,
        "dataset": record.dataset,
        "date": record.date.isoformat(),
        "hydro_year": record.hydro_year,
        "period": record.period,
        "measurements": {
            name: {
                "value": measurement.value,
                "flag": measurement.flag,
                **{
                    field: getattr(measurement, field)
                    for field in descriptor.measurement_fields
                },
            }
            for name, measurement in record.measurements.items()
        },
        "attributes": dict(record.attributes),
        "extrema_dates": {
            name: [None if day is None else day.isoformat() for day in span]
            for name, span in record.extrema_dates.items()
        },
        "extrema_occurrences": dict(record.extrema_occurrences),
    }


def _extrema(record: NormalizedRecord, name: str) -> list[str]:
    """``<V>_start``, ``<V>_end`` and ``<V>_occurrences`` cells of a half-year record."""
    first, last = record.extrema_dates.get(name, (None, None))
    occurrences = record.extrema_occurrences.get(name)
    return [
        _timestamp(first),
        _timestamp(last),
        "" if occurrences is None else str(occurrences),
    ]


def _archive_row(
    record: NormalizedRecord,
    descriptor: DatasetDescriptor,
    attributes: tuple[str, ...],
) -> list[str]:
    unknown = sorted(
        {*record.measurements} - set(descriptor.variables)
        | {*record.attributes} - set(attributes)
    )
    if unknown:
        raise ObserwatorDataError(
            message(
                "export.record_station_from_has_columns",
                station_code=record.station_code,
                date=record.date,
                dataset=record.dataset,
                unknown=", ".join(unknown),
            )
        )
    half_year = descriptor.time_unit == "half_year"
    cells = [
        record.station_code,
        record.dataset,
        record.date.isoformat(),
        str(record.hydro_year),
        record.period or "",
    ]
    for name in descriptor.variables:
        cells += _measurement_cells(record.measurements.get(name), descriptor)
        if half_year:
            cells += _extrema(record, name)
    cells += [record.attributes.get(key) or "" for key in attributes]
    return cells


def _archive_lines(
    records: Iterator[NormalizedRecord], format: str
) -> tuple[tuple[str, ...], Iterator[str]]:
    """
    Header lines and lazy data lines of archive records; no records give no lines.

    The first JSONL object and the trailing CSV columns ``attribution`` and
    ``terms_notice`` carry the lines of the dataset's provider (ADR-012).
    """
    first = next(records, None)
    if first is None:
        return (), iter(())

    def chained() -> Iterator[NormalizedRecord]:
        yield first
        yield from records

    descriptor = get_dataset(first.dataset)
    lines = _lines(descriptor)
    if format == "jsonl":
        return (), (
            json.dumps(
                _record_json(record, descriptor)
                | (lines.fields() if number == 0 else {}),
                ensure_ascii=False,
            )
            + "\n"
            for number, record in enumerate(chained())
        )
    attributes = tuple(DATASET_ATTRIBUTES.get(first.dataset, ()))
    header = ["station_code", "dataset", "date", "hydro_year", "period"]
    for name, unit in descriptor.variables.items():
        header += [f"{name} [{unit}]", f"{name}_flag", *_field_names(name, descriptor)]
        if descriptor.time_unit == "half_year":
            header += [f"{name}_start", f"{name}_end", f"{name}_occurrences"]
    header += [*attributes, "attribution", "terms_notice"]
    rows = (_archive_row(record, descriptor, attributes) for record in chained())
    return (_csv_line(header),), _csv_lines(_with_lines(rows, lines))


@overload
def export_archive(
    version: PathArg,
    /,
    *,
    root: RootArg | None = None,
    format: Literal["csv", "jsonl"] = "csv",
    output: None = None,
    force: bool = False,
    on_progress: ProgressHook | None = None,
    on_notice: NoticeHook | None = None,
    cancel: Cancel | None = None,
) -> Iterator[str]: ...


@overload
def export_archive(
    version: PathArg,
    /,
    *,
    root: RootArg | None = None,
    format: Literal["csv", "jsonl"] = "csv",
    output: PathArg,
    force: bool = False,
    on_progress: ProgressHook | None = None,
    on_notice: NoticeHook | None = None,
    cancel: Cancel | None = None,
) -> OutputReport: ...


def export_archive(
    version: PathArg,
    /,
    *,
    root: RootArg | None = None,
    format: Literal["csv", "jsonl"] = "csv",
    output: PathArg | None = None,
    force: bool = False,
    on_progress: ProgressHook | None = None,
    on_notice: NoticeHook | None = None,
    cancel: Cancel | None = None,
) -> OutputReport | Iterator[str]:
    """
    Export the normalized records of one stored archive version as CSV or JSONL.

    The stored bytes are verified against the sidecar (see
    :func:`read_archive`) before anything is returned or written. CSV (UTF-8
    without BOM, comma, CRLF rows) starts with the header ``station_code,
    dataset,date,hydro_year,period``, then ``<V> [<unit>],<V>_flag`` for every
    dataset variable (ČHMÚ meteo adds ``<V>_quality,<V>_source_flag``,
    half-year datasets ``<V>_start,<V>_end,<V>_occurrences``), one column
    per qualitative attribute of the dataset (meteo ``precip_type`` etc.) and
    the trailing columns ``attribution`` and ``terms_notice``: the lines of the
    dataset's provider (`obserwator.attribution`, ADR-012), one line per cell
    from the first data row down, the rest joined with a line feed into the
    last row of a shorter table; a variable or attribute absent from a record
    gives empty cells. JSONL writes one object per record with the
    `NormalizedRecord` fields (the ``Measurement`` fields ``quality`` and
    ``source_flag`` only for datasets that fill them) and LF line ends; the
    first object adds ``attribution`` and, with IMGW-PIB data,
    ``terms_notice`` (arrays of the lines). An archive without records gives
    no lines.

    Parameters
    ----------
    version : str or os.PathLike
        Archive version directory, its main file or its sidecar; absolute or
        relative to ``root`` (to the working directory without ``root``).
    root : str, os.PathLike, StoreHandle or None, optional
        Raw root (ADR-017), the base of a relative ``version``.
    format : {"csv", "jsonl"}, optional
        Output format.
    output : str, os.PathLike or None, optional
        The one plain file to write (DEV-19.1): its directory is created when
        missing, the lines go through ``<dir>/.obserwator-incoming/`` and the file is
        moved into place with ``os.replace``, so an interrupted export leaves
        no partial file. ``None`` (default) returns the lines instead,
        byte-identical to the file content.
    force : bool, optional
        Replace an existing ``output`` file; without it an existing file is a
        ``conflict``. Needs ``output``.
    on_progress : ProgressHook or None, optional
        Called once after the export with ``unit="row"`` and the number of
        records.
    on_notice : NoticeHook or None, optional
        Called with the ``license_terms`` notice of the dataset's provider
        (source and processed-data attribution, license note) before the first
        line.
    cancel : Cancel or None, optional
        Polled before the first line, every 256 records and before replacing
        the target; returning ``True`` aborts the export.

    Returns
    -------
    OutputReport or Iterator[str]
        With ``output``: the written file as ``output`` and ``files[]``
        (``written`` or ``replaced``, size and SHA-256 of the bytes written);
        otherwise a lazy iterator of text lines with their line terminators.

    Raises
    ------
    ObserwatorValidationError
        If ``format`` is unsupported, ``version`` is not an archive version
        or is a station list version, ``output`` is a directory, or ``force``
        is given without ``output``.
    ObserwatorError
        Code ``conflict`` before anything is written: ``output`` exists and
        ``force`` is not given (``details.reason="output_exists"``) or lies
        in a store of any tool (``"output_in_store"``); ``details.paths``
        names it.
    ObserwatorStoreError
        If the archive file or its sidecar does not exist (code
        ``not_found``) or ``root`` is not a supported store.
    ObserwatorCancelledError
        If ``cancel`` returns ``True``; the target stays untouched and no
        staging file remains. Without ``output`` it may also be raised while
        iterating.
    ObserwatorDataError
        If the sidecar or the stored bytes are invalid; while iterating (or
        writing), if the archive content is malformed.
    OSError
        If the target cannot be written; the target stays untouched.
    """
    _format(format, _ARCHIVE_FORMATS)
    source = Path(version).expanduser()
    if root is not None:
        source = _open(root, kind="raw") / source
    records = read_archive(source)
    descriptor = get_dataset(read_meta(_archive_main(source)).dataset)
    target = _target(output, force=force)
    head, rows = _archive_lines(records, format)
    _check_cancel(cancel)
    _license(descriptor, on_notice)
    lines = _Lines(
        head,
        rows,
        total=None,
        label=message("export.archive_progress", source=source),
        on_progress=on_progress,
        cancel=cancel,
    )
    return _deliver(
        lines,
        target=target,
        cancel=cancel,
        done=message("export.archive_exported", source=source),
    )


_Kind = Literal["date", "int", "text", "number", "code", "timestamp"]


@dataclass(frozen=True)
class _Column:
    """
    One data column of a series export, the same in CSV, JSON and Parquet.

    ``header`` names it in the CSV and in Parquet, ``name`` in JSON (where the
    unit of a value column is given in ``variables``); ``kind`` gives its CSV
    cell, its JSON value and its Arrow type; ``value`` reads it from a record.
    """

    name: str
    header: str
    kind: _Kind
    value: Callable[[NormalizedRecord], object]

    def cell(self, record: NormalizedRecord) -> str:
        """The CSV cell: empty without a value, a number in its shortest form."""
        value = self.value(record)
        if value is None:
            return ""
        if isinstance(value, float):
            return _number(value)
        if isinstance(value, date):
            return value.isoformat()
        return str(value)

    def json_value(self, record: NormalizedRecord) -> object:
        """The JSON value: a date as ISO text, null without a value."""
        value = self.value(record)
        return value.isoformat() if isinstance(value, date) else value


def _plain(
    name: str, kind: _Kind, value: Callable[[NormalizedRecord], object]
) -> _Column:
    """A column named alike in every format."""
    return _Column(name, name, kind, value)


def _measured(name: str, field: str) -> Callable[[NormalizedRecord], object]:
    return lambda record: getattr(record.measurements[name], field)


def _extremum(name: str, side: int) -> Callable[[NormalizedRecord], object]:
    return lambda record: record.extrema_dates.get(name, (None, None))[side]


def _occurrences(name: str) -> Callable[[NormalizedRecord], object]:
    return lambda record: record.extrema_occurrences.get(name)


def _series_columns(
    descriptor: DatasetDescriptor, names: Sequence[str], year_type: str
) -> list[_Column]:
    """
    The data columns of a series export, in the order of the CSV header.

    ``date``, ``year`` (of ``year_type``), ``period`` of half-years, then per
    variable the value (``<V> [<unit>]``), ``<V>_flag``, the extra fields of the
    dataset (``<V>_quality``, ``<V>_source_flag``) and the extremum columns of
    half-years (``<V>_start``, ``<V>_end``, ``<V>_occurrences``).
    """
    half_year = descriptor.time_unit == "half_year"

    def year(record: NormalizedRecord) -> int:
        return record.hydro_year if year_type == "hydrological" else record.date.year

    columns = [
        _plain("date", "date", lambda record: record.date),
        _plain("year", "int", year),
    ]
    if half_year:
        columns.append(_plain("period", "text", lambda record: record.period))
    for name in names:
        unit = descriptor.variables[name]
        columns.append(
            _Column(name, f"{name} [{unit}]", "number", _measured(name, "value"))
        )
        columns.append(_plain(f"{name}_flag", "text", _measured(name, "flag")))
        for field in descriptor.measurement_fields:
            kind: _Kind = "code" if field == "quality" else "text"
            columns.append(_plain(f"{name}_{field}", kind, _measured(name, field)))
        if half_year:
            columns += [
                _plain(f"{name}_start", "timestamp", _extremum(name, 0)),
                _plain(f"{name}_end", "timestamp", _extremum(name, 1)),
                _plain(f"{name}_occurrences", "int", _occurrences(name)),
            ]
    return columns


def _compact(value: object) -> str:
    """JSON text of a document part: UTF-8 characters, no spaces."""
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _license_json(license_: License) -> dict[str, str | None]:
    """The licence of provider data: its identifier and the addresses of its terms."""
    return {"id": license_.id, "url": license_.url, "terms_url": license_.terms_url}


def _series_version(series: Path, descriptor: DatasetDescriptor) -> str:
    """A series version as ``--version`` names it: its directory relative to the root."""
    return f"series/versions/{descriptor.slug}/{series.parent.name}"


def _series_head(
    descriptor: DatasetDescriptor,
    station: str,
    version: str,
    year_type: str,
    names: Sequence[str],
) -> dict[str, object]:
    """The fields of a series export before its data (JSON; Parquet metadata)."""
    return {
        "dataset": descriptor.key,
        "provider": descriptor.provider,
        "station": station,
        "series_version": version,
        "year_type": year_type,
        "time_unit": descriptor.time_unit,
        "variables": {
            name: {
                "unit": descriptor.variables[name],
                "note": _note(descriptor, name),
            }
            for name in names
        },
        "license": _license_json(descriptor.license),
        **_lines(descriptor).fields(),
    }


def _note(descriptor: DatasetDescriptor, name: str) -> str | None:
    """The definition of a variable the provider's format description gives, if any."""
    note = descriptor.variable_notes.get(name)
    return None if note is None else str(note)


def _series_json(
    head: Mapping[str, object],
    columns: Sequence[_Column],
    records: Sequence[NormalizedRecord],
) -> tuple[tuple[str, ...], Iterator[str], tuple[str, ...]]:
    """
    Lines of ``obserwator-series-export/1``: the head, one line per column, the end.

    The document is columnar: ``columns`` maps every column name to the array
    of its values in date order (``null`` without a value).
    """
    opening = _compact({"schema": SERIES_EXPORT_SCHEMA, **head})
    last = len(columns) - 1
    lines = (
        f"{_compact(column.name)}:"
        f"{_compact([column.json_value(record) for record in records])}"
        f"{',' if number < last else ''}\n"
        for number, column in enumerate(columns)
    )
    return (opening[:-1] + ',"columns":{\n',), lines, ("}}\n",)


def _series_parquet(
    head: Mapping[str, object],
    columns: Sequence[_Column],
    records: Sequence[NormalizedRecord],
) -> bytes:
    """
    The Parquet file of a series export: the CSV's columns typed, the head as metadata.

    Values ``float64``, flags and other texts ``string``, ``date`` ``date32``,
    ``year`` and ``<V>_occurrences`` ``int32``, ``<V>_quality`` ``int8``,
    ``<V>_start`` and ``<V>_end`` ``timestamp[us]``; the file metadata holds
    ``obserwator_schema`` and the head's fields, objects and arrays as JSON
    (``units`` and ``variable_notes`` from ``variables``).
    """
    pa, pq = _pyarrow()
    types = {
        "date": pa.date32(),
        "int": pa.int32(),
        "text": pa.string(),
        "number": pa.float64(),
        "code": pa.int8(),
        "timestamp": pa.timestamp("us"),
    }
    table = pa.table(
        {
            column.header: pa.array(
                [column.value(record) for record in records], types[column.kind]
            )
            for column in columns
        }
    )
    variables = cast(Mapping[str, Mapping[str, object]], head["variables"])
    fields = {
        "obserwator_schema": SERIES_EXPORT_SCHEMA,
        **{key: value for key, value in head.items() if key != "variables"},
        "units": {name: item["unit"] for name, item in variables.items()},
        "variable_notes": {name: item["note"] for name, item in variables.items()},
    }
    metadata = {
        key: value if isinstance(value, str) else _canonical_text(value)
        for key, value in fields.items()
    }
    sink = pa.BufferOutputStream()
    pq.write_table(table.replace_schema_metadata(metadata), sink)
    return bytes(sink.getvalue().to_pybytes())


@overload
def export_series(
    version: PathArg | None = None,
    /,
    *,
    root: RootArg | None = None,
    dataset: str | None = None,
    station: str,
    variables: Iterable[str] | None = None,
    start: date | None = None,
    end: date | None = None,
    year_type: Literal["hydrological", "calendar"] | None = None,
    format: Literal["csv", "json"] = "csv",
    output: None = None,
    force: bool = False,
    on_progress: ProgressHook | None = None,
    on_notice: NoticeHook | None = None,
    cancel: Cancel | None = None,
) -> Iterator[str]: ...


@overload
def export_series(
    version: PathArg | None = None,
    /,
    *,
    root: RootArg | None = None,
    dataset: str | None = None,
    station: str,
    variables: Iterable[str] | None = None,
    start: date | None = None,
    end: date | None = None,
    year_type: Literal["hydrological", "calendar"] | None = None,
    format: Literal["csv", "json", "parquet"] = "csv",
    output: PathArg,
    force: bool = False,
    on_progress: ProgressHook | None = None,
    on_notice: NoticeHook | None = None,
    cancel: Cancel | None = None,
) -> OutputReport: ...


def export_series(
    version: PathArg | None = None,
    /,
    *,
    root: RootArg | None = None,
    dataset: str | None = None,
    station: str,
    variables: Iterable[str] | None = None,
    start: date | None = None,
    end: date | None = None,
    year_type: Literal["hydrological", "calendar"] | None = None,
    format: Literal["csv", "json", "parquet"] = "csv",
    output: PathArg | None = None,
    force: bool = False,
    on_progress: ProgressHook | None = None,
    on_notice: NoticeHook | None = None,
    cancel: Cancel | None = None,
) -> OutputReport | Iterator[str]:
    """
    Export the values, flags and provider lines of one station as CSV, JSON or Parquet.

    ``year_type=None`` uses the publication convention of ``series.json`` (IMGW
    hydro ``hydrological``, IMGW meteo and ČHMÚ ``calendar``). Arguments and
    the station data are validated and read before anything is returned or
    written. The three formats hold the same columns (ADR-014).

    The CSV (UTF-8 without BOM, comma, dot decimal, CRLF rows) has a single
    header row ``date,year,<V> [<unit>],<V>_flag,…,attribution_source,
    attribution_processed,attribution,terms_notice``; ČHMÚ meteo series add
    ``<V>_quality`` and ``<V>_source_flag`` after the flag of every variable,
    half-year series add ``period`` and ``<V>_start`` / ``<V>_end`` extremum
    dates with ``<V>_occurrences`` (number of merged IMGW rows). The source
    attribution and the processed-data attribution of the dataset's provider
    appear only in the first data row (ADR-001 Q10); the columns
    ``attribution`` and ``terms_notice`` hold the lines of `obserwator.attribution`
    (ADR-012), one line per cell from the first data row down, the rest
    joined with a line feed into the last row of a shorter series. Missing
    values are empty cells flagged ``missing``.

    JSON is one ``obserwator-series-export/1`` document (UTF-8, LF lines):
    ``schema``, ``dataset``, ``provider``, ``station``, ``series_version`` (the
    version directory relative to the root, ``series/versions/<slug>/<label>_
    <sha8>``), ``year_type`` and ``time_unit``, ``variables`` (per variable its
    ``unit`` and the ``note`` of the provider's format description or null),
    ``license`` (``id``, ``url``, ``terms_url``), ``attribution`` and, with
    IMGW-PIB data, ``terms_notice``, then ``columns``: the CSV's data columns
    by name (a value column by the bare variable name) as arrays in date
    order, null without a value. Parquet holds the CSV's data columns with
    their header names, typed, and the same fields as file metadata
    (``obserwator_schema``, ``units`` and ``variable_notes`` instead of
    ``variables``; objects and arrays as JSON text).

    Parameters
    ----------
    version : str, os.PathLike or None, optional
        Series version directory, its ``series.json`` or its sidecar; absolute
        or relative to ``root`` (to the working directory without ``root``).
        Mutually exclusive with ``dataset``.
    root : str, os.PathLike, StoreHandle or None, optional
        Data root (ADR-017): the base of a relative ``version``, or with
        ``dataset`` the root whose current series version is exported.
    dataset : str or None, optional
        Series dataset (key, slug or legacy alias) whose current version in
        ``root`` is exported.
    station : str
        Station code (nine IMGW-PIB digits or a ČHMÚ WIGOS identifier)
        present in the series.
    variables : Iterable[str] or None, optional
        Dataset variable names; duplicates are merged, column order follows
        this collection, a single string or an empty collection is rejected.
        ``None`` (default) means every variable of the dataset.
    start : datetime.date or None, optional
        First period start date to include (inclusive); ``None`` means no
        lower bound. Monthly and half-year periods are matched by their start.
    end : datetime.date or None, optional
        Last period start date to include (inclusive); ``None`` means no
        upper bound.
    year_type : {"hydrological", "calendar"} or None, optional
        Convention of the ``year`` column: ``hydro_year`` or the calendar year
        of ``date``. ``None`` uses ``series.json`` ``year_type``.
    format : {"csv", "json", "parquet"}, optional
        Output format; ``"parquet"`` is binary and needs ``output``.
    output : str, os.PathLike or None, optional
        The one plain file to write (DEV-19.1): its directory is created when
        missing, the bytes go through ``<dir>/.obserwator-incoming/`` and the
        file is moved into place with ``os.replace``, so an interrupted export
        leaves no partial file. ``None`` (default) returns the lines of CSV or
        JSON instead, byte-identical to the file content.
    force : bool, optional
        Replace an existing ``output`` file; without it an existing file is a
        ``conflict``. Needs ``output``.
    on_progress : ProgressHook or None, optional
        Called every 256 CSV rows and once after the export with ``unit="row"``
        and the number of rows.
    on_notice : NoticeHook or None, optional
        Called with the ``license_terms`` notice of the dataset's provider
        before the first line.
    cancel : Cancel or None, optional
        Polled before the first line, every 256 CSV rows and before replacing
        the target; returning ``True`` aborts the export.

    Returns
    -------
    OutputReport or Iterator[str]
        With ``output``: the written file as ``output`` and ``files[]``
        (``written`` or ``replaced``, size and SHA-256 of the bytes written);
        otherwise a lazy iterator of CSV lines ending with CRLF or of JSON
        lines ending with LF.

    Raises
    ------
    ObserwatorValidationError
        If ``format`` or ``year_type`` is unsupported, ``format="parquet"``
        has no ``output`` (``details.reason="output_required"``),
        ``year_type="calendar"`` is requested for a half-year series,
        ``output`` is a directory, ``force`` is given without ``output``, or
        the arguments are rejected by :func:`read_series` (``version``/
        ``dataset`` choice, station, ``variables``, ``start``/``end``).
    ObserwatorError
        Code ``conflict`` before the station data is read: ``output`` exists
        and ``force`` is not given (``details.reason="output_exists"``) or
        lies in a store of any tool (``"output_in_store"``); ``details.paths``
        names it.
    ObserwatorStoreError
        If ``series.json``, its sidecar or the dataset series does not exist
        (code ``not_found``) or ``root`` is not a supported store.
    ObserwatorCancelledError
        If ``cancel`` returns ``True``; the target stays untouched and no
        staging file remains. Without ``output`` it may also be raised while
        iterating.
    ObserwatorStoreDependencyError
        If ``pyarrow>=15`` is not installed.
    ObserwatorDataError
        If the station series (within ``start``/``end``) is empty or the
        series data is invalid.
    OSError
        If the target cannot be written; the target stays untouched.
    """
    _format(format, _SERIES_FORMATS)
    _needs_output(format, output)
    if year_type is not None and year_type not in _YEAR_TYPES:
        raise ObserwatorValidationError(
            message(
                "export.unknown_year_type_allowed",
                year_type=year_type,
                year_types=", ".join(_YEAR_TYPES),
            ),
            details={
                "option": "year_type",
                "value": str(year_type),
                "allowed": list(_YEAR_TYPES),
            },
        )
    series = _series_path(version, root=root, dataset=dataset)
    index = read_series_index(series)
    descriptor = get_dataset(index.dataset)
    names = _variables(variables, descriptor)
    chosen = year_type or index.year_type
    if descriptor.time_unit == "half_year" and chosen == "calendar":
        raise ObserwatorValidationError(
            message(
                "export.semi_annual_annual_characteristics_have", dataset=index.dataset
            ),
            details={"option": "year_type", "value": "calendar"},
        )
    target = _target(output, force=force)
    records = list(
        read_series(series, station=station, variables=names, start=start, end=end)
    )
    if not records:
        raise ObserwatorDataError(
            message(
                "export.series_station_empty_chosen_range",
                station=station,
                dataset=index.dataset,
            )
        )
    _check_cancel(cancel)
    _license(descriptor, on_notice)
    columns = _series_columns(descriptor, names, chosen)
    done = message("export.series_exported", station=station)
    label = message("export.station_progress", station=station)
    if format == "parquet":
        assert target is not None  # _needs_output refused a Parquet without it
        head = _series_head(
            descriptor, station, _series_version(series, descriptor), chosen, names
        )
        report = _write((_series_parquet(head, columns, records),), target, cancel)
        if on_progress is not None:
            written = message("export.exported_to_file", done=done, target=target)
            on_progress(Progress(len(records), len(records), "row", "written", written))
        return report
    if format == "json":
        head = _series_head(
            descriptor, station, _series_version(series, descriptor), chosen, names
        )
        opening, data, closing = _series_json(head, columns, records)
        return _deliver(
            _Lines(
                opening,
                data,
                total=None,
                label=label,
                on_progress=on_progress,
                cancel=cancel,
                tail=closing,
                count=len(records),
            ),
            target=target,
            cancel=cancel,
            done=done,
        )
    formulas = (
        descriptor.license.attribution,
        get_provider(descriptor.provider).processed_attribution,
    )
    rows = (
        [
            *(column.cell(record) for column in columns),
            *(formulas if number == 0 else ("", "")),
        ]
        for number, record in enumerate(records)
    )
    return _deliver(
        _Lines(
            (
                _csv_line(
                    [*(column.header for column in columns), *_ATTRIBUTION_COLUMNS]
                ),
            ),
            _csv_lines(_with_lines(rows, _lines(descriptor))),
            total=len(records),
            label=label,
            on_progress=on_progress,
            cancel=cancel,
        ),
        target=target,
        cancel=cancel,
        done=done,
    )


# --------------------------------------------------------------------------
# Stations: the current catalogs of the providers as GeoJSON or CSV
# --------------------------------------------------------------------------


def _data_root(root: RootArg | None) -> Path:
    """
    The opened data root whose catalogs and series a stations export reads.

    ``None`` is the default data root (`obserwator.store_root`, DEV-19.2,
    ADR-017). The one place where a stations export opens its root.
    """
    return _open(store_root(kind="data").root if root is None else root, kind="data")


@dataclass(frozen=True)
class _Catalog:
    """The current catalog of one provider as an export reads it."""

    owner: ProviderDescriptor
    dataset: str
    version: str
    meta: Meta
    stations: tuple[StationFeature, ...]
    lines: Attribution


def _catalogs(base: Path, provider: str | None, kind: str | None) -> list[_Catalog]:
    """
    The current catalogs of the chosen providers with their stations of ``kind``.

    Stations are sorted by code, those without geometry included. The lines of
    a catalog are those its builder gives it (ADR-012): the provider's processed
    lines, and the lines of hydro.imgw.pl when a station is located by the
    static file of its map or has the station details of its pages (ADR-021).

    Raises
    ------
    ObserwatorStoreError
        Code ``not_found`` when an explicit ``provider`` has no catalog, or
        none of the providers has one.
    """
    owners = providers() if provider is None else (get_provider(provider),)
    found: list[_Catalog] = []
    for owner in owners:
        key = _CATALOG_DATASETS[owner.id]
        entry = current_version(base, slot=f"catalog:{key}")
        if entry is None or entry.version is None or entry.meta is None:
            if provider is not None:
                raise ObserwatorStoreError(
                    message(
                        "reader.store_has_no_station_catalog",
                        short_name=owner.short_name,
                        key=key,
                        id=owner.id,
                    ),
                    code="not_found",
                    hint=message("errors.hint_store_catalog", provider=owner.id),
                )
            continue
        features = read_catalog(entry.version)
        static = sum(
            feature.properties.get("location_source") == "static"
            for feature in features
        )
        detailed = sum(
            feature.properties.get("details_source") == DETAILS_SOURCE
            for feature in features
        )
        chosen = (
            feature
            for feature in features
            if kind is None or feature.properties.get("kind") == kind
        )
        found.append(
            _Catalog(
                owner,
                key,
                entry.version.parent.relative_to(base).as_posix(),
                entry.meta,
                tuple(sorted(chosen, key=lambda feature: feature.station_code)),
                _catalog_lines(owner, {"static": static, DETAILS_SOURCE: detailed}),
            )
        )
    if not found:
        raise ObserwatorStoreError(
            message("export.store_has_no_station_catalog"),
            code="not_found",
            hint=message("errors.hint_store_catalog", provider=owners[0].id),
        )
    return found


def _stations_attribution(
    root: RootArg | None, provider: str | None, kind: str | None
) -> Attribution:
    """The lines of a stations export: those of every catalog it reads."""
    lines = Attribution()
    for catalog in _catalogs(_data_root(root), provider, kind):
        lines |= catalog.lines
    return lines


def _coverage(
    station: StationSeriesIndex, descriptor: DatasetDescriptor
) -> dict[str, object]:
    """
    What a series holds of a station: the first and last date with a value, the variables.

    Read from the index (``series.json``): the variables with a value in the
    dataset's order (half-year periods merged); dates null without any value.
    """
    firsts = [item.first for item in station.variables.values() if item.first]
    lasts = [item.last for item in station.variables.values() if item.last]
    valued = {item.variable for item in station.variables.values() if item.with_value}
    return {
        "first": min(firsts).isoformat() if firsts else None,
        "last": max(lasts).isoformat() if lasts else None,
        "variables": [name for name in descriptor.variables if name in valued],
    }


def _holdings(
    base: Path, catalogs: Sequence[_Catalog], kind: str | None
) -> tuple[list[dict[str, str]], dict[str, dict[str, dict[str, object]]]]:
    """
    The current series of the catalogs' providers and, per station, those holding it.

    Only ``series.json`` indexes are read (no pyarrow): the series of the
    providers' datasets of ``kind``, in registry order; a dataset without a
    series is skipped.
    """
    chosen = {catalog.owner.id for catalog in catalogs}
    versions: list[dict[str, str]] = []
    held: dict[str, dict[str, dict[str, object]]] = {}
    for descriptor in _series_datasets().values():
        if descriptor.provider not in chosen or kind not in (None, descriptor.kind):
            continue
        entry = current_version(base, slot=f"series:{descriptor.key}")
        if entry is None or entry.version is None:
            continue
        index = read_series_index(entry.version)
        versions.append(
            {
                "provider": descriptor.provider,
                "dataset": descriptor.key,
                "version": _series_version(entry.version, descriptor),
            }
        )
        for code, station in index.stations.items():
            held.setdefault(code, {})[descriptor.key] = _coverage(station, descriptor)
    return versions, held


def _utc(moment: datetime) -> str:
    """ISO text of a time in UTC with ``Z``, as every document of Obserwator writes it."""
    aware = moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)
    return aware.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _catalog_json(catalog: _Catalog) -> dict[str, object]:
    """A member of ``catalogs``: the version read, its provider's licence and lines."""
    version = catalog.meta.extra.get("version")
    label = version.get("label") if isinstance(version, Mapping) else None
    return {
        "provider": catalog.owner.id,
        "dataset": catalog.dataset,
        "version": catalog.version,
        "label": label,
        "downloaded_at": _utc(catalog.meta.downloaded_at),
        "stations": len(catalog.stations),
        "license": _license_json(catalog.owner.license),
        **catalog.lines.fields(),
    }


def _feature(
    station: StationFeature, provider: str, held: Mapping[str, object] | None
) -> dict[str, object]:
    """The GeoJSON feature of a station: its catalog properties, provider and series."""
    properties: dict[str, object] = {**station.properties, "provider": provider}
    if held is not None:
        properties["series"] = held
    return {
        "type": "Feature",
        "id": station.station_code,
        "geometry": None
        if station.geometry is None
        else {"type": "Point", "coordinates": list(station.geometry)},
        "properties": properties,
    }


def _stations_geojson(
    catalogs: Sequence[_Catalog],
    versions: Sequence[Mapping[str, str]] | None,
    held: Mapping[str, Mapping[str, object]],
) -> tuple[tuple[str, ...], Iterator[str], tuple[str, ...]]:
    """
    Lines of ``obserwator-stations-export/1``: the head, one line per feature, the end.

    ``versions`` is None without series: then neither the collection nor the
    features name any.
    """
    lines = Attribution()
    for catalog in catalogs:
        lines |= catalog.lines
    head: dict[str, object] = {
        "type": "FeatureCollection",
        "schema": STATIONS_EXPORT_SCHEMA,
        "catalogs": [_catalog_json(catalog) for catalog in catalogs],
    }
    if versions is not None:
        head["series"] = list(versions)
    head.update(lines.fields())
    features = [
        (station, catalog.owner.id)
        for catalog in catalogs
        for station in catalog.stations
    ]
    last = len(features) - 1
    rows = (
        _compact(
            _feature(
                station,
                provider,
                None if versions is None else held.get(station.station_code, {}),
            )
        )
        + ("," if number < last else "")
        + "\n"
        for number, (station, provider) in enumerate(features)
    )
    return (_compact(head)[:-1] + ',"features":[\n',), rows, ("]}\n",)


def _property(value: object) -> str:
    """A CSV cell of a catalog property: ``true``/``false``, the shortest number, JSON."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return _number(value)
    if isinstance(value, int | str):
        return str(value)
    return _compact(value)


def _stations_csv(
    catalogs: Sequence[_Catalog], held: Mapping[str, Mapping[str, object]] | None
) -> tuple[tuple[str, ...], Iterator[str]]:
    """
    The header and the lines of the stations CSV, one row per station.

    ``station_code``, ``name``, ``kind``, ``provider``, the other catalog
    properties sorted by name, ``latitude``, ``longitude``, with series
    ``datasets`` (the keys of the series holding the station, joined with
    ``;``) and the attribution columns of the series CSV. Each provider's rows
    form a block that starts with its lines: the formulas in its first row and
    the lines of DEV-20.5 from its first row down.
    """
    names = dict.fromkeys(
        key
        for catalog in catalogs
        for station in catalog.stations
        for key in station.properties
    )
    others = sorted(key for key in names if key not in _STATION_COLUMNS)
    header = [
        *_STATION_COLUMNS,
        "provider",
        *others,
        "latitude",
        "longitude",
        *([] if held is None else ["datasets"]),
        *_ATTRIBUTION_COLUMNS,
    ]

    def rows(catalog: _Catalog) -> Iterator[list[str]]:
        owner = catalog.owner
        formulas = (owner.license.attribution, owner.processed_attribution)
        for number, station in enumerate(catalog.stations):
            longitude, latitude = station.geometry or (None, None)
            cells = [
                *(_property(station.properties.get(key)) for key in _STATION_COLUMNS),
                owner.id,
                *(_property(station.properties.get(key)) for key in others),
                _property(latitude),
                _property(longitude),
            ]
            if held is not None:
                cells.append(";".join(held.get(station.station_code, {})))
            yield [*cells, *(formulas if number == 0 else ("", ""))]

    lines = (
        line
        for catalog in catalogs
        for line in _csv_lines(_with_lines(rows(catalog), catalog.lines))
    )
    return (_csv_line(header),), lines


@overload
def export_stations(
    root: RootArg | None = None,
    /,
    *,
    provider: str | None = None,
    kind: Literal["hydro", "meteo"] | None = None,
    series: bool = True,
    format: Literal["geojson", "csv"] = "geojson",
    output: None = None,
    force: bool = False,
    on_progress: ProgressHook | None = None,
    on_notice: NoticeHook | None = None,
    cancel: Cancel | None = None,
) -> Iterator[str]: ...


@overload
def export_stations(
    root: RootArg | None = None,
    /,
    *,
    provider: str | None = None,
    kind: Literal["hydro", "meteo"] | None = None,
    series: bool = True,
    format: Literal["geojson", "csv"] = "geojson",
    output: PathArg,
    force: bool = False,
    on_progress: ProgressHook | None = None,
    on_notice: NoticeHook | None = None,
    cancel: Cancel | None = None,
) -> OutputReport: ...


def export_stations(
    root: RootArg | None = None,
    /,
    *,
    provider: str | None = None,
    kind: Literal["hydro", "meteo"] | None = None,
    series: bool = True,
    format: Literal["geojson", "csv"] = "geojson",
    output: PathArg | None = None,
    force: bool = False,
    on_progress: ProgressHook | None = None,
    on_notice: NoticeHook | None = None,
    cancel: Cancel | None = None,
) -> OutputReport | Iterator[str]:
    """
    Export the stations of the current catalogs as GeoJSON or CSV, with their series.

    The current station catalog of every chosen provider is read (offline,
    verified against its sidecar), and with ``series`` the ``series.json``
    indexes of the providers' current series (no pyarrow). Stations without a
    location are included. Arguments and data are validated and read before
    anything is returned or written.

    GeoJSON (UTF-8, LF lines) is one ``obserwator-stations-export/1``
    document, an RFC 7946 FeatureCollection with the foreign members
    ``schema``, ``catalogs`` (per catalog read: ``provider``, ``dataset``,
    ``version`` relative to the root, version ``label``, ``downloaded_at``,
    the number of its ``stations`` exported, the provider's ``license``
    ``{id, url, terms_url}`` and its ``attribution`` and ``terms_notice``
    lines: the formula, the processed mark, and the lines of hydro.imgw.pl
    when a location comes from its map), with ``series`` the list of the
    series read (``provider``, ``dataset``, ``version``), and the lines of all
    of them as ``attribution`` and ``terms_notice`` (ADR-012). Each feature
    has the station code as ``id``, a ``Point`` ``[lon, lat]`` or null and the
    catalog's properties with ``provider`` and, with ``series``, ``series``:
    per dataset key holding the station ``{first, last, variables}`` (the
    first and last date with a value, the variables with values).

    CSV (UTF-8, comma, dot decimal, CRLF rows) has one row per station:
    ``station_code,name,kind,provider``, the other catalog properties sorted
    by name (an object such as the ČHMÚ ``thresholds`` as JSON, booleans
    ``true``/``false``), ``latitude,longitude`` (empty without a location),
    with ``series`` ``datasets`` (keys joined with ``;``), then the columns
    ``attribution_source,attribution_processed,attribution,terms_notice`` of
    `export_series`. The rows of each provider form a block that starts
    with the provider's formulas and lines.

    Parameters
    ----------
    root : str, os.PathLike, StoreHandle or None, optional
        Data root whose current catalogs and series are read (ADR-017); None
        is the default data root (`obserwator.store_root`).
    provider : str or None, optional
        Provider identifier or key prefix (``"IMGW-PIB"``, ``"CHMI"``,
        ``"cz.chmi"``); None exports every provider with a catalog.
    kind : {"hydro", "meteo"} or None, optional
        Only the stations of this kind (and the series of its datasets);
        None exports both.
    series : bool, optional
        Name the current series that hold each station (default); False
        reads no series.
    format : {"geojson", "csv"}, optional
        Output format.
    output : str, os.PathLike or None, optional
        The one plain file to write (DEV-19.1), written as `export_series`
        writes it; ``None`` (default) returns the lines instead,
        byte-identical to the file content.
    force : bool, optional
        Replace an existing ``output`` file; without it an existing file is a
        ``conflict``. Needs ``output``.
    on_progress : ProgressHook or None, optional
        Called every 256 stations and once after the export with ``unit="row"``.
    on_notice : NoticeHook or None, optional
        Called with the ``license_terms`` notice of each catalog before the
        first line.
    cancel : Cancel or None, optional
        Polled before the first line, every 256 stations and before replacing
        the target; returning ``True`` aborts the export.

    Returns
    -------
    OutputReport or Iterator[str]
        With ``output``: the written file as ``output`` and ``files[]``;
        otherwise a lazy iterator of GeoJSON lines ending with LF or of CSV
        lines ending with CRLF.

    Raises
    ------
    ObserwatorValidationError
        If ``format``, ``kind`` or ``provider`` is unknown, ``output`` is a
        directory or ``force`` is given without ``output``.
    ObserwatorError
        Code ``conflict`` before the catalogs are read: ``output`` exists and
        ``force`` is not given (``details.reason="output_exists"``) or lies in
        a store of any tool (``"output_in_store"``).
    ObserwatorStoreError
        Code ``not_found`` if the store has no catalog of an explicit
        ``provider`` or no catalog at all; ``store_unavailable`` if ``root``
        is not a supported store.
    ObserwatorCancelledError
        If ``cancel`` returns ``True``; the target stays untouched. Without
        ``output`` it may also be raised while iterating.
    ObserwatorDataError
        If no station is of ``kind``, or a catalog or series index is invalid.
    OSError
        If the target cannot be written; the target stays untouched.
    """
    _format(format, _STATIONS_FORMATS)
    if kind is not None and kind not in _KINDS:
        raise ObserwatorValidationError(
            message("export.unknown_kind_allowed", kind=kind, kinds=", ".join(_KINDS)),
            details={"option": "kind", "value": str(kind), "allowed": list(_KINDS)},
        )
    chosen = None if provider is None else get_provider(provider).id
    base = _data_root(root)
    target = _target(output, force=force)
    catalogs = _catalogs(base, chosen, kind)
    count = sum(len(catalog.stations) for catalog in catalogs)
    if not count:
        raise ObserwatorDataError(
            message(
                "export.no_station_of_kind",
                kind=kind or ", ".join(_KINDS),
                providers=", ".join(catalog.owner.id for catalog in catalogs),
            )
        )
    versions: list[dict[str, str]] | None = None
    held: dict[str, dict[str, dict[str, object]]] = {}
    if series:
        versions, held = _holdings(base, catalogs, kind)
    _check_cancel(cancel)
    if on_notice is not None:
        for catalog in catalogs:
            notice = catalog.owner.license_notice(catalog.lines)
            on_notice(Notice("info", "license_terms", notice))
    closing: tuple[str, ...] = ()
    if format == "geojson":
        opening, rows, closing = _stations_geojson(catalogs, versions, held)
    else:
        opening, rows = _stations_csv(catalogs, held if series else None)
    return _deliver(
        _Lines(
            opening,
            rows,
            total=count,
            label=message("export.stations_progress"),
            on_progress=on_progress,
            cancel=cancel,
            tail=closing,
        ),
        target=target,
        cancel=cancel,
        done=message("export.stations_exported", count=count),
    )
