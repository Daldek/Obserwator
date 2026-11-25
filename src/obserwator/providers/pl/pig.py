"""
PIG-PIB's groundwater monitoring (provider ``PIG``, ADR-035).

Państwowy Instytut Geologiczny – Państwowy Instytut Badawczy runs Poland's state
geological service, whose Monitoring Wód Podziemnych publishes, through
cbdgmapa.pgi.gov.pl's open ArcGIS REST services (no key; CC BY 4.0 by dane.gov.pl's
dataset 170; the facts in ``docs/providers/pig.md``):

- ``hydrogeologia/mwp``: the points (layer 0) and the MWP database's readings of one
  month (table 1), chemical indicators (table 2) and watch list (table 3), each
  replaced as a whole by the next publication. The readings are verified by PIG-PIB
  before they enter the database: tier ``verified``.
- ``hydrogeologia/mwp_auto``: the automatic points (layer 0) and their hourly depths
  „bez walidacji” (table 2), appended in the order of loading, rows of a day arriving
  for weeks: tier ``operational``.

What the store keeps (W3 to W9 of the plan): every run of an ``mwp`` dataset pages its
layer or table in one run (`obserwator.fetch.arcgis_pages`: the counts before and
after, ``resultOffset``, one request per 2 s, POST) and keeps its answers as they came
in Obserwator's container of answers, one version per run unless its content equals
the current version's (``pig-json/1``: the rows without ``OBJECTID`` and paging); the
readings are one file per calendar month of their rows, ``MWP_<YYYY-MM>.jsonl.gz``
(`published`, check scope ``publication``). The night's harvest of ``mwp_auto``
(``store sync --pace-until``) asks the automatic points, the table's count and every
row appended after the last ``OBJECTID`` the raw root holds (the watermark), page by
page from the last ``OBJECTID`` of the one before, then the stored hour 02 of each
summer-time start day among them; the spool keeps every answer and the run seals them
into its day's capture. The points become the catalog ``pig_stations`` (W6), the
readings the weekly series ``pl.pig.groundwater_readings`` (W7) and the captures the
hourly series ``pl.pig.groundwater_subdaily`` (W8), both with ``H_asl`` derived from
the points' ground elevation.

PIG-PIB is no national hydro-meteorological service: its source class is ``other``
(W2), with P8's notice in its words.
"""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Callable, Collection, Iterable, Iterator, Mapping, Sequence
from datetime import UTC, date, timedelta
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any, Literal

import httpx

from obserwator._borders import POLAND
from obserwator._parsing.pig import (
    DST_CLAUSE,
    PROVIDER,
    AutoHours,
    PigPoint,
    auto_hours,
    automatic_points,
    dst_start,
    level,
    pages,
    parse_pig_readings,
    parse_pig_stations,
    read_points,
    read_readings,
    readings_period,
    stored_hour,
)
from obserwator.datasets import (
    ArchiveFile,
    DatasetDescriptor,
    MonthsArg,
    YearsArg,
    _minimum_year,
    _source_address,
    get_dataset,
    parse_months,
    parse_years,
)
from obserwator.exceptions import (
    ObserwatorConnectionError,
    ObserwatorDataError,
    ObserwatorValidationError,
    io_error,
)
from obserwator.fetch import (
    _IDENTIFY,
    ARCGIS_PAGE,
    DOWNLOAD_TIMEOUT,
    DownloadResult,
    PacedRequest,
    arcgis_pages,
    arcgis_query,
)
from obserwator.messages import Message, message
from obserwator.models import NormalizedRecord, StationListEntry
from obserwator.providers.base import (
    CheckScope,
    Kind,
    ProviderAdapter,
    SeriesContext,
    SourceAction,
)
from obserwator.store.catalog import (
    _Candidate,
    _catalog_lines,
    _catalog_notices,
    _local_source,
    _locate,
    _placement,
    _read_locations,
    _read_sources,
    _series_codes,
)
from obserwator.store.types import Notice
from obserwator.store.writer import _canonical

if TYPE_CHECKING:
    from obserwator.attribution import Origin
    from obserwator.captures import Spooled
    from obserwator.fetch import PacedSession
    from obserwator.store.catalog import CatalogBuild
    from obserwator.store.series import _Version
    from obserwator.store.types import CatalogReport, NoticeHook

__all__ = ["ADAPTER", "PigAdapter"]

STATIONS = "pl.pig.groundwater_stations"
"""The points of ``hydrogeologia/mwp`` layer 0, a station source (ADR-015)."""
READINGS = "pl.pig.groundwater_readings"
"""The readings of the MWP database (table 1), one file per calendar month."""
CHEMISTRY = "pl.pig.groundwater_chemistry"
"""The chemical indicators of the MWP database (table 2), kept as published."""
WATCHLIST = "pl.pig.groundwater_watchlist"
"""The watch-list parameters (table 3), kept as published."""
OPERATIONAL = "pl.pig.groundwater_operational"
"""The night's answers of ``hydrogeologia/mwp_auto``, a capture dataset (ADR-030)."""
SUBDAILY = "pl.pig.groundwater_subdaily"
"""The hourly series of the automatic points (ADR-031), built from the captures."""
_POINTS_FILE = "MWP_points.jsonl.gz"
_FIXED = {CHEMISTRY: "MWP_chemistry.jsonl.gz", WATCHLIST: "MWP_watchlist.jsonl.gz"}
_MONTH_FILE = re.compile(r"MWP_([0-9]{4})-(0[1-9]|1[0-2])\.jsonl\.gz")
_WINDOW_FILE = re.compile(
    r"MWP_([0-9]{4}-[0-9]{2}-[0-9]{2})_([0-9]{4}-[0-9]{2}-[0-9]{2})\.jsonl\.gz"
)
_AUTO_POINTS = "0"
_AUTO_ROWS = "2"
_WATERMARK = re.compile(r"OBJECTID > ([0-9]+)")
_STATION = "mwp_auto"
"""The one „station” of the harvest's requests: a refused page ends the run."""
_PROPERTIES = (
    "station_code",
    "kind",
    "meteo_kind",
    "name",
    "river",
    "hydrographic_code",
    "river_order",
    "location_source",
    "location_uncertainty_m",
    "location_missing_reason",
    "active",
    "established_year",
    "gauge_zero_m",
    "gauge_zero_datum",
    "river_km",
    "catchment_area_km2",
    "elevation_m",
    "groundwater_kind",
    "hydrogeology",
)
"""The properties of a point of the catalog, in order."""


def _query_url(descriptor: DatasetDescriptor) -> str:
    """The query address of a dataset's layer or table: ``…/MapServer/<n>/query``."""
    return f"{_source_address(descriptor)}/query"


def _auto_url(layer: str) -> str:
    """The query address of a layer or table of ``hydrogeologia/mwp_auto``."""
    return f"{_source_address(get_dataset(OPERATIONAL))}/{layer}/query"


def _month_file(descriptor: DatasetDescriptor, year: int, month: int) -> ArchiveFile:
    """The readings of one calendar month, ``MWP_<YYYY-MM>.jsonl.gz`` (W5)."""
    first = date(year, month, 1)
    following = date(year + month // 12, month % 12 + 1, 1)
    return ArchiveFile(
        descriptor.key,
        f"{descriptor.server_dir}/MWP_{first:%Y-%m}.jsonl.gz",
        _query_url(descriptor),
        year,
        month,
        None,
        "calendar",
        first,
        following - timedelta(days=1),
    )


def _window_file(descriptor: DatasetDescriptor, first: date, last: date) -> ArchiveFile:
    """Readings of other than one calendar month: ``MWP_<first>_<last>.jsonl.gz`` (W5)."""
    return ArchiveFile(
        descriptor.key,
        f"{descriptor.server_dir}/MWP_{first.isoformat()}_{last.isoformat()}.jsonl.gz",
        _query_url(descriptor),
        first.year,
        None,
        None,
        "calendar",
        first,
        last,
    )


def _readings_file(
    descriptor: DatasetDescriptor, first: date, last: date
) -> ArchiveFile:
    """The file of readings from ``first`` to ``last``: their month, or their window."""
    if (first.year, first.month) == (last.year, last.month):
        return _month_file(descriptor, first.year, first.month)
    return _window_file(descriptor, first, last)


def _fixed_file(descriptor: DatasetDescriptor, name: str) -> ArchiveFile:
    """The one file of a table kept as published (or of the points)."""
    return ArchiveFile(
        descriptor.key,
        f"{descriptor.server_dir}/{name}",
        _query_url(descriptor),
        None,
        None,
        None,
        "none",
        None,
        None,
    )


def _spooled(answers: Iterable[Any]) -> bytes:
    """Obserwator's container of the answers of a run (ADR-030 D3 erratum)."""
    # The store imports the adapters, so its encoder is reached at call time.
    import hashlib

    from obserwator.captures import Spooled
    from obserwator.store.captures import encode

    return encode(
        Spooled(
            answer.received_at.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            answer.address,
            answer.status,
            hashlib.sha256(answer.content).hexdigest(),
            answer.content,
        )
        for answer in answers
    )


def _fail_option(descriptor: DatasetDescriptor, option: str, key: str) -> None:
    raise ObserwatorValidationError(
        message(key, option=option, key=descriptor.key),
        details={"option": option, "value": None, "reason": "pig"},
    )


def _first(items: Iterable[str], count: int = 5) -> str:
    """The first codes of a list, for a notice."""
    found = list(items)
    return ", ".join(found[:count]) + (", …" if len(found) > count else "")


# --- the points' capture of mwp_auto and the watermark ------------------------------


def _captures(raw: Path) -> Iterator[_Version]:
    """The current version of each captured day of ``mwp_auto``, newest first."""
    # The store imports the adapters, so its reader is reached at call time.
    from obserwator.store.series import _pick_current, _read_versions

    descriptor = get_dataset(OPERATIONAL)
    assert descriptor.server_dir is not None
    base = raw / "archives" / "versions" / PurePosixPath(descriptor.server_dir)
    if not base.is_dir():
        return
    days = sorted(
        (entry.name for entry in base.iterdir() if entry.is_dir()), reverse=True
    )
    for day in days:
        try:
            date.fromisoformat(day)
        except ValueError:
            continue
        relative = f"archives/versions/{descriptor.server_dir}/{day}"
        current = _pick_current(_read_versions(raw, relative, f"{day}.jsonl.gz"))
        if current is not None:
            yield current


def _capture_sidecars(raw: Path) -> list[dict[str, Any]]:
    """
    The sidecars of the current versions of the captures of ``mwp_auto``, newest first.

    Each holds ``extra.capture`` with the night's ``watermark`` and ``count`` (W9).
    """
    return [dict(version.meta) for version in _captures(raw)]


def _points_capture(raw: Path) -> tuple[_Version, frozenset[str]] | None:
    """
    The newest capture of ``mwp_auto`` that lists its automatic points, and their codes.

    Each night's harvest asks layer 0 first (W9, `PigAdapter.harvest_requests`): the
    current version of each captured day, newest first, until one holds that page
    answered with its rows (`automatic_points`); None for a raw root without one.

    Raises
    ------
    ObserwatorDataError
        If a capture cannot be read.
    """
    for version in _captures(raw):
        try:
            data = version.file.read_bytes()
        except OSError as exc:
            raise io_error(exc) from exc
        codes = automatic_points(pages(data, filename=version.relative))
        if codes is not None:
            return version, codes
    return None


def _harvested_mark(raw: Path) -> tuple[int, int | None, str | None]:
    """
    The watermark of the next harvest, the count of the last one and its day (W9).

    The last ``OBJECTID`` of the pages the newest capture appended; 0 for a raw root
    without one, whose first harvest asks every row (S0's backfill, question 7).
    """
    mark: int | None = None
    count: int | None = None
    day: str | None = None
    for meta in _capture_sidecars(raw):
        capture = meta.get("extra", {}).get("capture", {})
        if mark is None and isinstance(capture.get("watermark"), int):
            mark = capture["watermark"]
        if count is None and isinstance(capture.get("count"), int):
            count = capture["count"]
            day = str(meta.get("extra", {}).get("version", {}).get("label"))
        if mark is not None and count is not None:
            break
    return mark or 0, count, day


class PigAdapter(ProviderAdapter):
    """The adapter of PIG-PIB (ADR-035); `ADAPTER` is its one instance."""

    provider_id = PROVIDER
    origin: Origin = "pig"
    origins: tuple[Origin, ...] = ("pig",)
    border = POLAND
    identifies = True
    harvested = frozenset({OPERATIONAL})
    watermarked = frozenset({OPERATIONAL})
    station_sources = (STATIONS, STATIONS, STATIONS, STATIONS)
    optional_sources = (OPERATIONAL,)
    kinds: tuple[Kind, ...] = ("groundwater",)
    archive_suffixes = (".gz",)
    sidecar_station = False
    source_class: Literal["nmhs", "other"] = "other"
    source_notice: Message | None = message("datasets.source_notice_pig")

    def publication_default(self, key: str, /) -> Literal["public", "private"]:
        """``public``: CC BY 4.0 by dane.gov.pl's dataset 170 (W10)."""
        return "public"

    # --- archives --------------------------------------------------------------------

    def archive_files(
        self,
        descriptor: DatasetDescriptor,
        /,
        *,
        years: YearsArg | None,
        months: MonthsArg | None,
        params: Iterable[Literal["H", "Q", "T"]] | None,
        stations: Iterable[str] | None,
    ) -> tuple[ArchiveFile, ...]:
        """
        The candidate files of a table, offline.

        The readings: one file per calendar month of the selected years (``years``
        required, ``months`` optional), published only while the service holds that
        month; the chemistry and the watch list: their one file (no years).

        Raises
        ------
        ObserwatorValidationError
            For ``params`` or ``stations``, for the readings without ``years`` or
            with a year before 1965, and for ``years`` or ``months`` of a table kept
            as one file.
        """
        if params is not None:
            _fail_option(descriptor, "params", "pig.no_option")
        if stations is not None:
            _fail_option(descriptor, "stations", "pig.no_option")
        if descriptor.key != READINGS:
            for option, given in (("years", years), ("months", months)):
                if given is not None:
                    _fail_option(descriptor, option, "pig.one_file")
            return (_fixed_file(descriptor, _FIXED[descriptor.key]),)
        if years is None:
            raise ObserwatorValidationError(
                message("pig.years_required", key=descriptor.key),
                details={"option": "years", "value": None},
            )
        selected = parse_years(years, option="years")
        _minimum_year(selected, descriptor)
        chosen = parse_months(months, option="months") if months is not None else None
        return tuple(
            _month_file(descriptor, year, month)
            for year in selected
            for month in (chosen or range(1, 13))
        )

    def archive_from_path(
        self, descriptor: DatasetDescriptor, server_path: str, /
    ) -> ArchiveFile | None:
        """``MWP_<YYYY-MM>``, ``MWP_<first>_<last>`` or the one file of a table."""
        directory, _, name = server_path.rpartition("/")
        if directory != descriptor.server_dir:
            return None
        if descriptor.key in _FIXED:
            return (
                _fixed_file(descriptor, name)
                if name == _FIXED[descriptor.key]
                else None
            )
        if descriptor.key != READINGS:
            return None
        if (month := _MONTH_FILE.fullmatch(name)) is not None:
            return _month_file(descriptor, int(month[1]), int(month[2]))
        if (window := _WINDOW_FILE.fullmatch(name)) is not None:
            try:
                first, last = (date.fromisoformat(window[i]) for i in (1, 2))
            except ValueError:
                return None
            archive = _window_file(descriptor, first, last)
            return (
                archive if archive.server_path == server_path and first < last else None
            )
        return None

    def check_scope(self, descriptor: DatasetDescriptor, /) -> CheckScope:
        """``publication``: the one file the service publishes now (W4, W5)."""
        return "publication"

    def published(
        self, descriptor: DatasetDescriptor, /, *, client: httpx.Client
    ) -> tuple[ArchiveFile | None, tuple[Notice, ...]]:
        """
        The file a table is published as now; of the readings, by one query.

        The readings' first and last ``DATA_POMIARU`` (``outStatistics``, one POST)
        name it: their calendar month, or with a warning ``window_unexpected`` their
        first and last day (W5); an empty table is no file (a ``no_readings``
        warning). A table kept as one file needs no request.

        Raises
        ------
        ObserwatorConnectionError
            If the query fails (``source_unavailable``).
        ObserwatorDataError
            If a first or last day the service answers is no date (R1).
        """
        if descriptor.key != READINGS:
            return _fixed_file(descriptor, _FIXED[descriptor.key]), ()
        statistics = json.dumps(
            [
                {
                    "statisticType": kind,
                    "onStatisticField": "DATA_POMIARU",
                    "outStatisticFieldName": name,
                }
                for kind, name in (("min", "first"), ("max", "last"))
            ],
            separators=(",", ":"),
        )
        form = {"where": "1=1", "outStatistics": statistics, "f": "json"}
        _, payload = arcgis_query(
            client, _query_url(descriptor), form, source=self.server_name
        )
        rows = payload.get("features")
        attributes = (
            rows[0].get("attributes", {})
            if isinstance(rows, list) and rows and isinstance(rows[0], dict)
            else {}
        )
        texts = [attributes.get("first"), attributes.get("last")]
        if all(text is None for text in texts):
            notice = Notice(
                "warning",
                "no_readings",
                message("pig.no_readings", url=_query_url(descriptor)),
            )
            return None, (notice,)
        days: list[date] = []
        for text in texts:
            stripped = text.strip() if isinstance(text, str) else ""
            try:
                days.append(date.fromisoformat(stripped))
            except ValueError as exc:
                raise ObserwatorDataError(
                    message(
                        "parsing.pig_invalid",
                        filename=_query_url(descriptor),
                        where="outStatistics",
                        problem=message("parsing.pig_bad_day", value=text),
                    )
                ) from exc
        first, last = days
        archive = _readings_file(descriptor, first, last)
        if archive.month is not None:
            return archive, ()
        notice = Notice(
            "warning",
            "window_unexpected",
            message(
                "pig.window_unexpected",
                first=first.isoformat(),
                last=last.isoformat(),
                name=PurePosixPath(archive.server_path).name,
            ),
        )
        return archive, (notice,)

    def publication_gaps(
        self, descriptor: DatasetDescriptor, raw: Path, /
    ) -> tuple[ArchiveFile, ...]:
        """Every calendar month between the first and last readings stored, without one."""
        if descriptor.key != READINGS:
            return ()
        assert descriptor.server_dir is not None
        base = raw / "archives" / "versions" / PurePosixPath(descriptor.server_dir)
        covered: list[tuple[date, date]] = []
        for slot in sorted(base.iterdir()) if base.is_dir() else ():
            if not any(slot.rglob("*.meta.json")):
                continue
            archive = self.archive_from_path(
                descriptor, f"{descriptor.server_dir}/{slot.name}.jsonl.gz"
            )
            if archive is not None:
                assert archive.period_start is not None
                assert archive.period_end is not None
                covered.append((archive.period_start, archive.period_end))
        if not covered:
            return ()
        first = min(start for start, _ in covered).replace(day=1)
        last = max(end for _, end in covered)
        gaps: list[ArchiveFile] = []
        month = first
        while month <= last:
            candidate = _month_file(descriptor, month.year, month.month)
            assert candidate.period_end is not None
            if not any(
                start <= candidate.period_end and month <= end for start, end in covered
            ):
                gaps.append(candidate)
            month = candidate.period_end + timedelta(days=1)
        return tuple(gaps)

    def replaced(
        self, archive: ArchiveFile, previous: bytes, data: bytes, /
    ) -> tuple[Notice, ...]:
        """``month_republished``: the readings changed, added and removed (W5)."""
        if archive.dataset != READINGS:
            return ()
        name = PurePosixPath(archive.server_path).name
        before = {
            (item.point, item.day): item
            for item in read_readings(previous, filename=name)
        }
        after = {
            (item.point, item.day): item for item in read_readings(data, filename=name)
        }
        changed = sum(
            1 for key, item in after.items() if key in before and before[key] != item
        )
        notice = Notice(
            "warning",
            "month_republished",
            message(
                "pig.month_republished",
                name=name,
                changed=changed,
                added=len(after.keys() - before.keys()),
                removed=len(before.keys() - after.keys()),
            ),
        )
        return (notice,)

    def download(
        self,
        archive: ArchiveFile,
        /,
        *,
        client: httpx.Client | None,
        cancel: Callable[[], bool] | None,
    ) -> DownloadResult:
        """
        One run of a layer or table, as the container of its answers (W4).

        The count before, the pages by ``resultOffset`` and the count after, each a
        paced POST (`obserwator.fetch.arcgis_pages`; the points with their WGS84
        geometry); a run whose counts change is asked again once, then fails. The
        readings name their file by their rows (``archive`` of the result): the
        calendar month they hold, or their first and last day.

        Raises
        ------
        ObserwatorConnectionError
            ``source_unavailable``: a request failed, an answer was no JSON or an
            ArcGIS error, the rows changed during both runs, or the readings table
            holds no rows (``details.reason`` ``nothing_published``).
        ObserwatorDataError
            If the readings' rows cannot be read.
        ObserwatorCancelledError
            If ``cancel`` stops the requests.
        """
        descriptor = get_dataset(archive.dataset)
        if client is None:
            with httpx.Client(
                timeout=DOWNLOAD_TIMEOUT, follow_redirects=True, headers=_IDENTIFY
            ) as own:
                return self.download(archive, client=own, cancel=cancel)
        answers = arcgis_pages(
            client,
            _query_url(descriptor),
            geometry=descriptor.key == STATIONS,
            source=self.server_name,
            cancel=cancel,
        )
        data = _spooled(answers)
        named: ArchiveFile | None = None
        if descriptor.key == READINGS:
            period = readings_period(
                read_readings(data, filename=PurePosixPath(archive.server_path).name)
            )
            if period is None:
                url = _query_url(descriptor)
                raise ObserwatorConnectionError(
                    message("pig.no_readings", url=url),
                    details={"url": url, "reason": "nothing_published"},
                )
            named = _readings_file(descriptor, *period)
        return DownloadResult(
            data=data,
            url=_query_url(descriptor),
            etag=None,
            last_modified=None,
            content_length=None,
            archive=named,
        )

    # --- station sources -------------------------------------------------------------

    def station_file(
        self, descriptor: DatasetDescriptor, name: str, /
    ) -> ArchiveFile | None:
        """``mwp/MapServer/0/MWP_points.jsonl.gz``: the capture of the points."""
        if descriptor.key != STATIONS or name != _POINTS_FILE:
            return None
        return _fixed_file(descriptor, name)

    def parse_station_list(
        self, content: bytes, /, *, kind: Kind, filename: str
    ) -> list[StationListEntry]:
        """The points as groundwater stations (none of another family)."""
        if kind != "groundwater":
            return []
        return parse_pig_stations(content, filename=filename)

    def live_urls(self, kind: Kind, /) -> list[str]:
        """The query address of the points layer (its pages, POSTed)."""
        return [_query_url(get_dataset(STATIONS))] if kind == "groundwater" else []

    def live_stations(self, kind: Kind, /, *, timeout: float) -> list[StationListEntry]:
        """The points asked now: every page of the points layer, in WGS84."""
        if kind != "groundwater":
            return []
        descriptor = get_dataset(STATIONS)
        with httpx.Client(timeout=timeout, headers=_IDENTIFY) as client:
            answers = arcgis_pages(
                client, _query_url(descriptor), geometry=True, source=self.server_name
            )
        return parse_pig_stations(_spooled(answers), filename=_query_url(descriptor))

    async def live_stations_async(
        self, kind: Kind, /, *, timeout: float
    ) -> list[StationListEntry]:
        """Async twin of `live_stations`: the paced pages in a worker thread."""
        return await asyncio.to_thread(self.live_stations, kind, timeout=timeout)

    # --- the station catalog -----------------------------------------------------------

    def catalog_sources(self, raw: Path, /) -> list[tuple[str, ArchiveFile | None]]:
        """The points, the one source of the catalog."""
        return [
            (
                "pig_groundwater_stations",
                self.station_file(get_dataset(STATIONS), _POINTS_FILE),
            )
        ]

    def source_datasets(self) -> list[str]:
        """The points layer."""
        return [STATIONS]

    def optional_action(
        self,
        key: str,
        raw: Path,
        recorded: Mapping[object, object],
        /,
        *,
        catalog: bool,
        cancelled: bool,
    ) -> SourceAction:
        """
        The newest capture of the automatic points of ``mwp_auto`` (`_points_capture`).

        ``current`` when it is the one the catalog recorded, also when neither has
        one; ``newer`` when it appeared or changed, so that a night's new capture
        calls for a new catalog with its ``automatic``; ``missing`` without a catalog.
        """
        if key not in self.optional_sources:
            raise ValueError(f"{key} is no optional source of {self.provider_id}")
        if cancelled:
            return "unverifiable", message("common.cancelled")
        source = get_dataset(OPERATIONAL).slug
        captured = _points_capture(raw)
        digest = None if captured is None else captured[0].sha256
        status: Literal["current", "newer", "missing"]
        if not catalog:
            status = "missing"
        elif recorded.get(source) == digest:
            status = "current"
        else:
            status = "newer"
        if captured is None:
            return status, message(
                "catalog.automatic_not_stored", source=source, dataset=OPERATIONAL
            )
        return status, message(
            "catalog.source_detail", source=source, file=captured[0].relative
        )

    def build_catalog(self, build: CatalogBuild, /) -> CatalogReport:
        """
        The catalog ``pig_stations`` from the stored points (W6).

        Every point is a station of the family ``groundwater`` (``groundwater_kind``
        ``spring`` for „źródło”, ``bore`` for any other type), named by its locality,
        located by the answer's WGS84 point inside Poland's border (ADR-018) or the
        user file, with ``active`` („Tak”/„Nie”), ``elevation_m`` (the ground
        elevation), ``established_year`` and ``hydrogeology``; ``automatic`` tells a
        point that the newest capture of ``mwp_auto`` lists among its automatic points
        (`_points_capture`, recorded among the sources), and is left out while the raw
        root holds none. A code only in a series is a station without a name
        or location (``station_unknown``); a point whose CBDH number or place changed
        since the previous points version is named in ``station_identity_changed``.
        """
        owner, user = build.provider, build.user
        user_rows, user_problems = (
            _read_locations(user[1], static=None, provider=owner)
            if user is not None
            else ({}, [])
        )
        if (report := build.stopped()) is not None:
            return report
        stored = _read_sources(build.raw, owner)
        ((source, _),) = self.catalog_sources(build.raw)
        data, record = stored[source]
        build.progress(
            1, "done", message("catalog.source_read", server_path=record["file"])
        )
        points = {
            point.code: point
            for point in read_points(data, filename=str(record["file"]))
        }
        record["count"] = len(points)
        records: list[dict[str, Any]] = [record]
        problems: list[str] = []
        rejections: list[str] = []
        if user is not None:
            problems.extend(user_problems)
            records.append(
                _local_source(
                    user[1], source="user", file=user[0].name, count=len(user_rows)
                )
                | {"available": True}
            )
        series, series_sources, _ = _series_codes(build.root, problems, provider=owner)
        records.extend(series_sources)
        captured = _points_capture(build.raw)
        automatic = None if captured is None else captured[1]
        if captured is not None:
            version, listed = captured
            records.append(
                {
                    "source": get_dataset(OPERATIONAL).slug,
                    "url": _auto_url(_AUTO_POINTS),
                    "file": version.relative,
                    "fetched_at": version.meta["downloaded_at"],
                    "sha256": version.sha256,
                    "count": len(listed),
                }
            )
            build.progress(
                2, "done", message("catalog.source_read", server_path=version.relative)
            )
        codes = set(points) | set(series.get("groundwater", ()))
        if (report := build.stopped()) is not None:
            return report
        features = []
        used: dict[str, int] = {}
        without = 0
        for code in sorted(codes, key=int):
            point = points.get(code)
            candidates: list[_Candidate] = []
            if point is not None and point.longitude is not None:
                candidates.append((STATIONS, point.longitude, point.latitude))
            if code in user_rows:
                candidates.append(("user", user_rows[code][0], user_rows[code][1]))
            feature, location = _feature(
                code,
                point=point,
                automatic=None if automatic is None else code in automatic,
                candidates=candidates,
                rejections=rejections,
            )
            if location is None:
                without += 1
            else:
                used[location] = used.get(location, 0) + 1
            features.append(feature)
        series_only = sorted(codes - set(points), key=int)
        lines = _catalog_lines(owner, used, sources=records)
        document = {"type": "FeatureCollection", "features": features, **lines.fields()}
        build.progress(6, "done", message("catalog.catalog_built", count=len(features)))
        _catalog_notices(
            build.on_notice,
            problems=problems,
            rejections=rejections,
            used=used,
            user_rows=user_rows if user is not None else None,
            series_only=series_only,
            without=without,
        )
        if build.on_notice is not None:
            if series_only:
                build.on_notice(
                    Notice(
                        "warning",
                        "station_unknown",
                        message(
                            "pig.station_unknown",
                            count=len(series_only),
                            codes=_first(series_only),
                        ),
                    )
                )
            changed = _identity_changes(build.root, points)
            if changed:
                build.on_notice(
                    Notice(
                        "warning",
                        "station_identity_changed",
                        message(
                            "pig.station_identity_changed",
                            count=len(changed),
                            codes=_first(changed),
                        ),
                    )
                )
        if (report := build.stopped()) is not None:
            return report
        problems.extend(rejections)
        return build.publish(
            _canonical(document),
            sources=records,
            count=len(features),
            without=without,
            from_series=len(series_only),
            problems=problems,
            lines=lines,
        )

    # --- parsers and series ------------------------------------------------------------

    def series_sources(self, series: DatasetDescriptor, /) -> tuple[str, ...]:
        """The points, whose ground elevation gives ``H_asl`` (W7, W8)."""
        return (STATIONS,) if series.key in (READINGS, SUBDAILY) else ()

    def normalize(
        self,
        archive: ArchiveFile,
        /,
        *,
        data: bytes,
        carry: dict[str, date] | None,
        stations: Collection[str] | None = None,
        skipped_months: set[date] | None = None,
        context: SeriesContext | None = None,
    ) -> Iterator[NormalizedRecord]:
        """
        The readings at their own dates, with ``H_asl`` of the points read (W7).

        A reading of a point the build's points version lacks stays, without
        ``H_asl``, and is told once the build's files are read (`series_read`,
        ``station_unknown``). With ``stations`` the readings of other points are
        left out, their months noted in ``skipped_months``.

        Raises
        ------
        ObserwatorValidationError
            For a file of another dataset (``no_parser_archive``).
        ObserwatorDataError
            If the capture, or the points version the build read, cannot be read.
        """
        if archive.dataset != READINGS:
            raise ObserwatorValidationError(
                message("parsing.no_parser_archive", dataset=archive.dataset)
            )
        ground = _ground(context)
        known = None if ground is None else ground[0]
        unknown: set[str] = (
            set() if context is None else context.state.setdefault("unknown", set())
        )
        for record in parse_pig_readings(
            data,
            filename=archive.server_path,
            dataset=archive.dataset,
            elevations={} if ground is None else ground[1],
        ):
            code = record.station_code
            if stations is not None and code not in stations:
                if skipped_months is not None:
                    skipped_months.add(record.date.replace(day=1))
                continue
            if known is not None and code not in known:
                unknown.add(code)
            yield record

    def hourly_points(
        self,
        archive: ArchiveFile,
        data: bytes,
        /,
        *,
        context: SeriesContext | None = None,
    ) -> Iterator[tuple[str, str, list[tuple[object, object]]]]:
        """
        The hours of a capture of ``mwp_auto`` (W8, W9): depth and ``H_asl``.

        Read with the captures before it in the build (`SeriesContext.state`), so of
        two rows of one point and hour the later ``OBJECTID`` gives the value; each
        point and hour this capture holds is given with that value.

        Raises
        ------
        ObserwatorDataError
            If the capture cannot be read.
        """
        if archive.dataset != OPERATIONAL:
            raise ValueError(f"{archive.dataset}: {self.provider_id} gives no hours")
        state = _auto_state(context)
        touched = auto_hours(
            pages(data, filename=archive.server_path),
            state,
            filename=archive.server_path,
            month=None if context is None else context.month,
        )
        ground = _ground(context)
        elevations = {} if ground is None else ground[1]
        depths: dict[str, list[tuple[object, object]]] = {}
        levels: dict[str, list[tuple[object, object]]] = {}
        for point, hour in sorted(touched):
            value = state.values[(point, hour)][1]
            stamp = hour.isoformat()
            depths.setdefault(point, []).append((stamp, value))
            elevation = elevations.get(point)
            if elevation is not None:
                levels.setdefault(point, []).append(
                    (stamp, None if value is None else level(elevation, value))
                )
        for point in sorted(depths, key=int):
            yield point, "depth_to_water", depths[point]
            if point in levels:
                yield point, "H_asl", levels[point]

    def series_read(self, context: SeriesContext, label: str, /) -> None:
        """
        What a build's parsers left out or resolved, told once its files are read.

        Of the readings, the points the points version lacks (``station_unknown``);
        of a month ``label`` of the hourly series, the hours whose rows differ, the
        summer-time hours left unresolved and the rows after their answers
        (``hour_revised``, ``hour_unresolved``, ``hour_future``).
        """
        if context.on_notice is None:
            return
        unknown = context.state.get("unknown")
        if unknown:
            codes = sorted(unknown, key=int)
            context.on_notice(
                Notice(
                    "warning",
                    "station_unknown",
                    message(
                        "pig.station_unknown", count=len(codes), codes=_first(codes)
                    ),
                )
            )
        state = context.state.get("auto")
        if not isinstance(state, AutoHours):
            return
        if state.revised:
            point, hour = min(state.revised)
            context.on_notice(
                Notice(
                    "warning",
                    "hour_revised",
                    message(
                        "pig.hour_revised",
                        count=len(state.revised),
                        month=label,
                        point=point,
                        hour=hour.strftime("%Y-%m-%dT%H:%MZ"),
                    ),
                )
            )
        if state.unresolved:
            days = sorted({day.isoformat() for _, day in state.unresolved})
            context.on_notice(
                Notice(
                    "warning",
                    "hour_unresolved",
                    message(
                        "pig.hour_unresolved",
                        count=len(state.unresolved),
                        days=", ".join(days),
                    ),
                )
            )
        if state.future:
            context.on_notice(
                Notice(
                    "warning",
                    "hour_future",
                    message("pig.hour_future", count=state.future),
                )
            )

    # --- captures and the harvest --------------------------------------------------------

    def capture_extra(
        self, key: str, answers: Sequence[Spooled], /
    ) -> Mapping[str, object]:
        """
        Of a capture of ``mwp_auto``: the days of its rows' hours, its watermark, its count.

        ``period`` the first and last UTC day of the stored hours of its rows (the
        rows after their answer's time left out), ``watermark`` the last ``OBJECTID``
        of its pages asked by watermark, ``count`` the table's count it was told.
        """
        if key != OPERATIONAL:
            return {}
        found = [
            page for page in pages_of(answers) if page.layer == f"mwp_auto/{_AUTO_ROWS}"
        ]
        days: list[date] = []
        mark: int | None = None
        count: int | None = None
        for page in found:
            payload = page.payload if page.status == 200 else None
            if not isinstance(payload, dict):
                continue
            if isinstance(payload.get("count"), int) and "returnCountOnly" in page.form:
                count = payload["count"]
            ids: list[int] = []
            for feature in payload.get("features") or ():
                attributes = (
                    feature.get("attributes") if isinstance(feature, dict) else None
                )
                if not isinstance(attributes, dict):
                    continue
                epoch, objectid = attributes.get("TIME"), attributes.get("OBJECTID")
                if isinstance(epoch, int) and not isinstance(epoch, bool):
                    hour = stored_hour(epoch)
                    if hour <= page.received:
                        days.append(hour.date())
                if isinstance(objectid, int):
                    ids.append(objectid)
            if ids and _WATERMARK.fullmatch(page.form.get("where", "")):
                mark = max(ids) if mark is None else max(mark, *ids)
        extra: dict[str, object] = {}
        if days:
            extra["period"] = [min(days).isoformat(), max(days).isoformat()]
        if mark is not None:
            extra["watermark"] = mark
        if count is not None:
            extra["count"] = count
        return extra

    def harvest_requests(
        self,
        descriptor: DatasetDescriptor,
        /,
        *,
        start: date,
        end: date,
        stations: Sequence[str] | None,
        session: PacedSession,
        on_notice: NoticeHook | None,
        raw: Path | None = None,
    ) -> tuple[PacedRequest, ...]:
        """
        The night's requests of ``mwp_auto`` by ``OBJECTID`` watermark (W9).

        The automatic points (layer 0, one page in WGS84), the table's count, then
        every row after the watermark (the last ``OBJECTID`` the raw root's newest
        capture appended; 0 without one), 1,000 a page, the next page from the last
        ``OBJECTID`` of the one before, until a page is short; then the stored hour 02
        of every summer-time start day among the rows by a clause of its own
        (`obserwator._parsing.pig.DST_CLAUSE`). ``start``, ``end`` and ``stations``
        do not apply (refused before the run). A count smaller than the last
        harvest's is a ``rows_removed`` warning.

        Raises
        ------
        ObserwatorValidationError
            Without the raw root.
        """
        if descriptor.key != OPERATIONAL:
            raise ValueError(
                f"{descriptor.key}: {self.provider_id} harvests no answers"
            )
        if raw is None:
            raise ObserwatorValidationError(
                message("pig.watermark_needs_root", dataset=descriptor.key),
                details={"option": "root", "value": None, "reason": "watermark"},
            )
        mark, previous, day = _harvested_mark(raw)
        headers = dict(_IDENTIFY)
        points = PacedRequest(
            _auto_url(_AUTO_POINTS),
            _STATION,
            headers,
            data={
                "where": "1=1",
                "outFields": "*",
                "orderByFields": "OBJECTID",
                "resultOffset": "0",
                "resultRecordCount": str(ARCGIS_PAGE),
                "returnGeometry": "true",
                "f": "json",
                "outSR": "4326",
            },
        )
        days: set[date] = set()

        def dst_page(day_: date, rest: list[date]) -> PacedRequest:
            form = {
                "where": DST_CLAUSE.format(day=day_.isoformat()),
                "outFields": "*",
                "orderByFields": "OBJECTID",
                "resultOffset": "0",
                "resultRecordCount": str(ARCGIS_PAGE),
                "returnGeometry": "false",
                "f": "json",
            }

            def follow(_response: httpx.Response) -> PacedRequest | None:
                return dst_page(rest[0], rest[1:]) if rest else None

            return PacedRequest(_auto_url(_AUTO_ROWS), _STATION, headers, form, follow)

        def page(after: int) -> PacedRequest:
            form = {
                "where": f"OBJECTID > {after}",
                "outFields": "*",
                "orderByFields": "OBJECTID",
                "resultRecordCount": str(ARCGIS_PAGE),
                "returnGeometry": "false",
                "f": "json",
            }

            def follow(response: httpx.Response) -> PacedRequest | None:
                payload = _json(response)
                rows = payload.get("features") if isinstance(payload, dict) else None
                if not isinstance(rows, list):
                    return None
                last = after
                for row in rows:
                    attributes = (
                        row.get("attributes") if isinstance(row, dict) else None
                    )
                    if not isinstance(attributes, dict):
                        continue
                    objectid, epoch = attributes.get("OBJECTID"), attributes.get("TIME")
                    if isinstance(objectid, int) and objectid > last:
                        last = objectid
                    if isinstance(epoch, int) and not isinstance(epoch, bool):
                        # The stored day: the epoch at its Warsaw wall time (W9).
                        stored = stored_hour(epoch).date()
                        if dst_start(stored):
                            days.add(stored)
                full = len(rows) >= ARCGIS_PAGE or bool(
                    payload.get("exceededTransferLimit")
                )
                if full and last > after:
                    return page(last)
                ordered = sorted(days)
                return dst_page(ordered[0], ordered[1:]) if ordered else None

            return PacedRequest(_auto_url(_AUTO_ROWS), _STATION, headers, form, follow)

        def counted(response: httpx.Response) -> PacedRequest | None:
            payload = _json(response)
            count = payload.get("count") if isinstance(payload, dict) else None
            if (
                isinstance(count, int)
                and previous is not None
                and count < previous
                and on_notice is not None
            ):
                on_notice(
                    Notice(
                        "warning",
                        "rows_removed",
                        message(
                            "pig.rows_removed", count=count, previous=previous, day=day
                        ),
                    )
                )
            return page(mark)

        count = PacedRequest(
            _auto_url(_AUTO_ROWS),
            _STATION,
            headers,
            data={"where": "1=1", "returnCountOnly": "true", "f": "json"},
            follow=counted,
        )
        return (points, count)


def _json(response: httpx.Response) -> Any:
    """The JSON of an answer; None for an answer that is no JSON."""
    try:
        return response.json()
    except ValueError:
        return None


def pages_of(answers: Iterable[Spooled]) -> list[Any]:
    """The answers of a capture as pages (`obserwator._parsing.pig.Page`)."""
    from obserwator._parsing.pig import Page

    found = []
    for answer in answers:
        try:
            payload = json.loads(answer.content)
        except ValueError:
            payload = None
        found.append(Page(answer.time, answer.address, answer.status, payload))
    return found


def _ground(
    context: SeriesContext | None,
) -> tuple[frozenset[str], dict[str, float]] | None:
    """
    The points of the points version a build read, and their ground elevations (W7).

    Read once a build (`SeriesContext.state`); None without a points version.
    """
    data = None if context is None else context.sources.get(STATIONS)
    if context is None or data is None:
        return None
    codes, elevations = context.state.get("codes"), context.state.get("elevations")
    if not (isinstance(codes, frozenset) and isinstance(elevations, dict)):
        points = read_points(data, filename=STATIONS)
        codes = frozenset(point.code for point in points)
        elevations = {
            point.code: point.elevation_m
            for point in points
            if point.elevation_m is not None
        }
        context.state["codes"], context.state["elevations"] = codes, elevations
    return codes, elevations


def _auto_state(context: SeriesContext | None) -> AutoHours:
    """The rows of ``mwp_auto`` read so far in a build (one month)."""
    if context is None:
        return AutoHours()
    state = context.state.get("auto")
    if not isinstance(state, AutoHours):
        state = context.state["auto"] = AutoHours()
    return state


def _identity_changes(root: Path, points: Mapping[str, PigPoint]) -> list[str]:
    """
    The points whose CBDH number or place changed since the current catalog (R4).

    A place moved by more than 100 m, or a CBDH number given before and other now.
    """
    from obserwator.store.catalog import _current_catalog

    current = _current_catalog(root, PROVIDER)
    if current is None:
        return []
    path, _ = current
    try:
        document = json.loads(path.read_bytes())
    except (OSError, ValueError):
        return []
    changed: list[str] = []
    for feature in document.get("features") or ():
        code = feature.get("id") if isinstance(feature, dict) else None
        point = points.get(str(code))
        if point is None:
            continue
        properties = feature.get("properties") or {}
        before = (properties.get("hydrogeology") or {}).get("cbdh_number")
        if before and point.cbdh and before != point.cbdh:
            changed.append(point.code)
            continue
        geometry = feature.get("geometry") or {}
        coordinates = (
            geometry.get("coordinates") if isinstance(geometry, dict) else None
        )
        if (
            isinstance(coordinates, list)
            and len(coordinates) == 2
            and point.longitude is not None
            and point.latitude is not None
            and _moved(coordinates, (point.longitude, point.latitude))
        ):
            changed.append(point.code)
    return sorted(changed, key=int)


def _moved(before: Sequence[float], after: tuple[float, float]) -> bool:
    """Whether two WGS84 points lie more than 100 m apart (an equirectangular check)."""
    import math

    lon = math.radians(after[0] - before[0]) * math.cos(math.radians(after[1]))
    lat = math.radians(after[1] - before[1])
    return 6_371_000 * math.hypot(lon, lat) > 100


def _feature(
    code: str,
    *,
    point: PigPoint | None,
    automatic: bool | None,
    candidates: list[_Candidate],
    rejections: list[str],
) -> tuple[dict[str, Any], str | None]:
    """
    A point of the catalog and the source of its location, None without one.

    ``automatic`` None (no capture of the automatic points) leaves it out of the
    point's ``hydrogeology``.
    """
    located = _locate(code, candidates, border=POLAND, rejections=rejections)
    geometry, location_source, uncertainty, reason = _placement(located, candidates)
    hydrogeology: dict[str, object] = dict(point.hydrogeology) if point else {}
    if point is not None and automatic is not None:
        hydrogeology["automatic"] = automatic
    properties: dict[str, Any] = {
        "station_code": code,
        "kind": "groundwater",
        "meteo_kind": None,
        "name": point.name if point else "",
        "river": None,
        "hydrographic_code": None,
        "river_order": None,
        "location_source": location_source,
        "location_uncertainty_m": uncertainty,
        "location_missing_reason": reason,
        # A code known only from a series is no point of the current list.
        "active": bool(point.active) if point else False,
        "established_year": point.established_year if point else None,
        "gauge_zero_m": None,
        "gauge_zero_datum": None,
        "river_km": None,
        "catchment_area_km2": None,
        "elevation_m": point.elevation_m if point else None,
        "groundwater_kind": point.groundwater_kind if point else None,
        "hydrogeology": hydrogeology or None,
    }
    feature = {
        "type": "Feature",
        "id": code,
        "geometry": geometry,
        "properties": {key: properties[key] for key in _PROPERTIES},
    }
    return feature, location_source


ADAPTER = PigAdapter()
"""The adapter of the provider ``PIG``."""
