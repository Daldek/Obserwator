"""
Gdańskie Wody, the measurement network of Gdańsk's water company (provider ``GDANSKIEWODY``).

The first provider that is no state service (source class ``other``, Nogat plan
2026-11-20, P11, and 2026-11-27, S1; ADR-034): Gdańskie Wody Sp. z o.o. publishes the
hourly values of its rain gauges, water-level gauges and weather and water-quality
stations of the Gdańsk agglomeration through an API with a key
(``https://pomiary.gdanskiewody.pl/rest/``; the facts in ``docs/providers/
gdanskiewody.md``). Its key is ``OBSERWATOR_GDANSKIE_WODY_API_KEY`` or the file of
``OBSERWATOR_GDANSKIE_WODY_API_KEY_FILE`` (P3), sent as ``Authorization: Bearer`` and
never written anywhere; every error is an HTTP 200 answer whose body says so (P4).

What the store keeps (ADR-034): the station list ``rest/stations``
(``pl.gdanskiewody.station_list``) and, per station, quantity and calendar month, the
answers of the month's days gathered into one file (``pl.gdanskiewody.measurements``,
``rest/measurements/<no>/<symbol>/<YYYY-MM>.json``, plan P6), asked one at a time at
most once a second (P10). Which files a ``store check|sync`` names comes from the station
list the raw root holds; a month stored after it closed is current, one stored while
open is fetched again (`settled`). The hourly series (``*_hourly``, ADR-031) and the
daily series of the provider's day (``*_daily``, P5) are built from those files.

Its terms of use are unknown (the regulamin is shown only after sign-in): its lines are
drafts (`obserwator.attribution.provisional`), its sources ``private`` by default, and
the provider is off in both servers by default and can never be served until its terms
are known (`served_by_default`, `obserwator.instance`). The CLI and the library use it
where it is named.
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Callable, Collection, Iterable, Iterator, Mapping
from datetime import UTC, date, datetime, timedelta
from email.utils import format_datetime
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any, Literal

import httpx

from obserwator import fetch as _fetch
from obserwator._borders import POLAND
from obserwator._parsing.gdanskiewody import (
    PROVIDER,
    GdanskieWodyStation,
    daily_records,
    day_points,
    encode_month,
    parse_gdanskiewody_stations,
    quantity,
    read_stations,
    station_number,
)
from obserwator._parsing.gdanskiewody import (
    hourly_points as month_hours,
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
    ObserwatorCancelledError,
    ObserwatorConnectionError,
    ObserwatorDataError,
    ObserwatorError,
    ObserwatorStoreError,
    ObserwatorValidationError,
)
from obserwator.fetch import (
    _IDENTIFY,
    DownloadResult,
    _get_async,
    _source_error,
)
from obserwator.messages import Message, message
from obserwator.models import NormalizedRecord, StationListEntry
from obserwator.providers.base import CheckScope, Kind, ProviderAdapter, SeriesContext
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
from obserwator.store.writer import _canonical

if TYPE_CHECKING:
    from obserwator.attribution import Origin
    from obserwator.store.catalog import CatalogBuild
    from obserwator.store.types import CatalogReport, PlanAction

__all__ = ["ADAPTER", "GdanskieWodyAdapter"]

STATION_LIST = "pl.gdanskiewody.station_list"
"""The station list ``GET rest/stations`` (a station source, ADR-015)."""
MEASUREMENTS = "pl.gdanskiewody.measurements"
"""The month files of a station's quantity (plan P6)."""
_STATIONS_FILE = "stations"
"""The name of the station list in its server directory ``rest``."""
_SUFFIX = ".json"
_SETTLED = timedelta(hours=6)
"""
How long after its last provider's day a month is fetched again by every sync: late
values may still come in the first hours of the next day (ADR-034 D6).
"""
_DAY_END = timedelta(days=1, hours=6)
"""The end of a provider's day after the start of its date: 06:00 UTC the next day."""
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
)
"""The properties of a station of the catalog, in order (those of a file-fed one)."""


# --- the requests ----------------------------------------------------------------------


class _Pace:
    """
    One request of the provider at a time, at least `interval` seconds apart (P10).

    Shared by every download of a process, so the files of one sync are paced as one
    run: the interval holds between the last request of a file and the first of the
    next. Time is the run's clock (`obserwator.fetch._clock`), as
    `obserwator.fetch.PacedSession` keeps it; a clock set back since the last request
    waits the whole interval.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._last: datetime | None = None

    def wait(self, interval: float) -> None:
        """Sleep until ``interval`` seconds after the previous request, then claim it."""
        with self._lock:
            clock = _fetch._clock()
            if self._last is not None:
                elapsed = max((clock.now() - self._last).total_seconds(), 0.0)
                if elapsed < interval:
                    clock.sleep(interval - elapsed)
            self._last = clock.now()


_PACE = _Pace()


def _interval() -> float:
    """The pause between two requests (``OBSERWATOR_GDANSKIE_WODY_REQUEST_INTERVAL``)."""
    from obserwator.config import Settings

    return Settings().gdanskie_wody_request_interval


def _headers() -> dict[str, str]:
    """The key of the provider's requests (P3): read now, never logged or kept."""
    from obserwator.config import provider_key

    return {"Authorization": f"Bearer {provider_key(PROVIDER)}"}


def _answer_error(payload: Mapping[str, Any], url: str) -> ObserwatorError:
    """
    The error of a body ``{"status": "error", "code": N, …}`` (P4, ADR-034 D7).

    ``-100`` (authentication) is `obserwator.config.credential_error`'s ``forbidden``
    (``invalid_credentials``, ``details`` ``reason`` and ``provider``); ``-11`` (no
    such station) ``not_found``; ``-12`` and ``-13`` (the station does not measure the
    quantity) ``no_data``; ``-2`` (unknown symbol) and ``-3`` (bad date)
    ``validation_error``; any other ``source_unavailable``. The ``details`` of these
    hold the address (without the key), the provider's code and its text.
    """
    from obserwator.config import credential_error

    code = payload.get("code")
    text = str(payload.get("message") or "")[:200]
    if code == -100:
        return credential_error(PROVIDER, "invalid_credentials")
    details: dict[str, object] = {
        "url": url,
        "provider_code": code,
        "provider_text": text,
    }
    detail = message("gdanskiewody.answer_error", url=url, code=code, text=text)
    if code == -11:
        return ObserwatorError(
            detail, code="not_found", details={**details, "reason": "unknown_station"}
        )
    if code in (-12, -13):
        return ObserwatorError(
            detail, code="no_data", details={**details, "reason": "not_measured"}
        )
    if code in (-2, -3):
        return ObserwatorValidationError(
            detail, details={**details, "reason": "bad_request"}
        )
    return ObserwatorConnectionError(
        detail, details={**details, "reason": "provider_error"}
    )


def _payload(response: httpx.Response, url: str) -> Any:
    """The JSON of an answer, refused when the body reports an error."""
    try:
        payload = response.json()
    except ValueError as exc:
        raise ObserwatorDataError(
            message("fetch.invalid_json_response_from", url=url)
        ) from exc
    if isinstance(payload, dict) and payload.get("status") == "error":
        raise _answer_error(payload, url)
    return payload


def _ask(client: httpx.Client, url: str, *, source: str) -> Any:
    """One paced request of the provider with its key; the payload of a success."""
    headers = _headers()
    _PACE.wait(_interval())
    try:
        response = client.get(url, headers=headers)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise _source_error(exc, url, source=source) from exc
    return _payload(response, url)


# --- the month files -------------------------------------------------------------------


def _month_days(archive: ArchiveFile, today: date) -> list[date]:
    """The days of a month file to ask: its days up to today (UTC)."""
    assert archive.period_start is not None and archive.period_end is not None
    last = min(archive.period_end, today)
    count = (last - archive.period_start).days + 1
    return [archive.period_start + timedelta(days=offset) for offset in range(count)]


def _month_file(
    descriptor: DatasetDescriptor, station: str, symbol: str, year: int, month: int
) -> ArchiveFile:
    """The file of one station's quantity and calendar month."""
    first = date(year, month, 1)
    following = date(year + month // 12, month % 12 + 1, 1)
    number = station_number(station)
    directory = f"{descriptor.server_dir}/{number}/{symbol}"
    return ArchiveFile(
        descriptor.key,
        f"{directory}/{first:%Y-%m}{_SUFFIX}",
        f"{_source_address(descriptor)}/{number}/{symbol}",
        year,
        month,
        symbol,
        "calendar",
        first,
        following - timedelta(days=1),
        station,
    )


def _stored_stations(raw: Path) -> tuple[GdanskieWodyStation, ...]:
    """
    The stations of the station list the raw root holds (its current version).

    Raises
    ------
    ObserwatorStoreError
        ``not_found`` (``details.reason`` ``missing_source``) without a stored list,
        with the ``store sync`` that stores it.
    ObserwatorDataError
        If the stored list cannot be read.
    """
    # The store imports the adapters, so its readers are reached at call time.
    from obserwator.store.series import _current_version

    descriptor = get_dataset(STATION_LIST)
    archive = ADAPTER.station_file(descriptor, _STATIONS_FILE)
    assert archive is not None
    version = _current_version(raw, archive)
    if version is None:
        raise ObserwatorStoreError(
            message("gdanskiewody.no_station_list", root=raw, dataset=STATION_LIST),
            code="not_found",
            details={"reason": "missing_source", "datasets": [STATION_LIST]},
            hint=message("catalog.hint_sync_sources", root=raw, datasets=STATION_LIST),
        )
    return read_stations(version.file.read_bytes(), filename=version.relative)


class GdanskieWodyAdapter(ProviderAdapter):
    """The adapter of Gdańskie Wody (ADR-034); `ADAPTER` is its one instance."""

    provider_id = PROVIDER
    origin: Origin = "gdanskiewody"
    origins: tuple[Origin, ...] = ("gdanskiewody",)
    border = POLAND
    identifies = True
    station_sources = (STATION_LIST, STATION_LIST, STATION_LIST, STATION_LIST)
    archive_suffixes = (_SUFFIX,)
    sidecar_station = True
    source_class: Literal["state", "other"] = "other"
    source_notice: Message | None = message("datasets.source_notice_gdanskiewody")
    # The author, 2026-11-25: off until he names the range to download (ADR-034 D1).
    served_by_default = False

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
        Refuse: a month file is named by the station list the raw root holds.

        Raises
        ------
        ObserwatorValidationError
            Always (``details.reason`` ``stored_list``): ``store check|sync`` names
            the files of the stations and quantities of the stored station list.
        """
        raise ObserwatorValidationError(
            message("gdanskiewody.files_from_station_list", key=descriptor.key),
            details={
                "option": "dataset",
                "value": descriptor.key,
                "reason": "stored_list",
            },
        )

    def archive_from_path(
        self, descriptor: DatasetDescriptor, server_path: str, /
    ) -> ArchiveFile | None:
        """``rest/measurements/<no>/<symbol>/<YYYY-MM>.json``: a month file."""
        parts = PurePosixPath(server_path).parts
        prefix = PurePosixPath(descriptor.server_dir or "").parts
        if (
            descriptor.key != MEASUREMENTS
            or len(parts) != len(prefix) + 3
            or parts[: len(prefix)] != prefix
        ):
            return None
        number, symbol, name = parts[len(prefix) :]
        stem = name.removesuffix(_SUFFIX)
        if stem == name or quantity(symbol) is None:
            return None
        try:
            station = f"{PROVIDER}-{number}"
            station_number(station)
            year, month = (int(part) for part in stem.split("-"))
            archive = _month_file(descriptor, station, symbol, year, month)
        except ValueError:
            return None
        return archive if archive.server_path == server_path else None

    def check_scope(self, descriptor: DatasetDescriptor, /) -> CheckScope:
        """``months``: named by the stored station list, checked against the clock."""
        return "months"

    def month_files(
        self,
        descriptor: DatasetDescriptor,
        raw: Path,
        /,
        *,
        years: YearsArg,
        months: MonthsArg | None,
        stations: Iterable[str] | None,
        today: date,
    ) -> tuple[tuple[ArchiveFile, ...], tuple[PlanAction, ...]]:
        """
        The month files of a selection, named by the station list the raw root holds.

        Every quantity a station of the stored list measures, for each selected month
        that has begun by ``today``; a station named but not listed is one ``store
        sync`` action (``unverifiable``).

        Raises
        ------
        ObserwatorStoreError
            ``not_found`` (``missing_source``) without a stored station list.
        ObserwatorValidationError
            If a year lies before the dataset's first.
        """
        from obserwator.store.types import PlanAction

        selected = parse_years(years, option="years")
        _minimum_year(selected, descriptor)
        chosen = parse_months(months, option="months") if months is not None else None
        listed = {station.code: station for station in _stored_stations(raw)}
        actions: list[PlanAction] = []
        codes = list(listed) if stations is None else list(stations)
        files: list[ArchiveFile] = []
        for code in codes:
            station = listed.get(code)
            if station is None:
                actions.append(
                    PlanAction(
                        "store sync",
                        "unverifiable",
                        message("gdanskiewody.station_not_listed", code=code),
                    )
                )
                continue
            for symbol in station.quantities:
                if quantity(symbol) is None:
                    continue
                for year in selected:
                    for month in chosen or range(1, 13):
                        if date(year, month, 1) > today:
                            continue
                        files.append(_month_file(descriptor, code, symbol, year, month))
        return tuple(files), tuple(actions)

    def settled(self, archive: ArchiveFile, /) -> datetime:
        """
        When a version of a month file is final: six hours after the month.

        The provider's day of the month's last date ends at 06:00 UTC of the next
        month's first day; a version downloaded six hours later is current, an
        earlier one is fetched again by the next sync (``store sync --force`` fetches
        a final one again). A download from that time on carries it as its
        ``Last-Modified`` (`download`), so the same bytes downloaded earlier become a
        new version of that time (``relabeled``) and the month is current from then
        on.
        """
        assert archive.period_end is not None
        end = archive.period_end
        return datetime(end.year, end.month, end.day, tzinfo=UTC) + _DAY_END + _SETTLED

    def held_period(self, archive: ArchiveFile, /) -> tuple[date, date]:
        """A month's hours run to 05:00 UTC of the next month's first day."""
        assert archive.period_start is not None and archive.period_end is not None
        return archive.period_start, archive.period_end + timedelta(days=1)

    def download(
        self,
        archive: ArchiveFile,
        /,
        *,
        client: httpx.Client | None,
        cancel: Callable[[], bool] | None,
    ) -> DownloadResult:
        """
        The station list, or a month file gathered from its days' answers.

        Each request carries the key and waits for the request interval (P10); a
        month asks each of its days up to today (UTC), ``cancel`` polled before each.
        A month asked once it settled (`settled`) gives that time as its
        ``last_modified``: the provider sends no such header, and a settled month no
        longer changes; no other file has one.

        Raises
        ------
        ObserwatorError
            ``forbidden`` without a key or with one the provider refuses, or the error
            an answer reports (`_answer_error`).
        ObserwatorConnectionError
            If a request fails (``source_unavailable``).
        ObserwatorDataError
            If an answer is no JSON or a day's answer no list of hours.
        ObserwatorCancelledError
            If ``cancel`` stops the requests.
        """
        assert client is not None
        source = self.server_name
        last_modified: str | None = None
        if archive.dataset == STATION_LIST:
            data = _canonical(_ask(client, archive.url, source=source))
            # A list that cannot be read is no version.
            read_stations(data, filename=archive.url)
        else:
            now = _fetch._clock().now().astimezone(UTC)
            answers: dict[date, object] = {}
            for day in _month_days(archive, now.date()):
                if cancel is not None and cancel():
                    raise ObserwatorCancelledError(message("gdanskiewody.cancelled"))
                url = f"{archive.url}/{day.isoformat()}"
                payload = _ask(client, url, source=source)
                day_points(payload, day, filename=url)
                answers[day] = payload
            data = encode_month(answers)
            settled = self.settled(archive)
            if now >= settled:
                last_modified = format_datetime(settled, usegmt=True)
        return DownloadResult(
            data=data,
            url=archive.url,
            etag=None,
            last_modified=last_modified,
            content_length=None,
        )

    # --- station sources -------------------------------------------------------------

    def station_file(
        self, descriptor: DatasetDescriptor, name: str, /
    ) -> ArchiveFile | None:
        """``rest/stations``, the one file of the station list."""
        if descriptor.key != STATION_LIST or name != _STATIONS_FILE:
            return None
        return ArchiveFile(
            descriptor.key,
            f"{descriptor.server_dir}/{name}",
            f"{_source_address(descriptor)}/{name}",
            None,
            None,
            None,
            "none",
            None,
            None,
        )

    def _list_url(self) -> str:
        archive = self.station_file(get_dataset(STATION_LIST), _STATIONS_FILE)
        assert archive is not None
        return archive.url

    def parse_station_list(
        self, content: bytes, /, *, kind: Kind, filename: str
    ) -> list[StationListEntry]:
        """The stations of one family of the list (``hydro`` or ``meteo``)."""
        return [
            entry
            for entry in parse_gdanskiewody_stations(content, filename=filename)
            if entry.kind == kind
        ]

    def live_urls(self, kind: Kind, /) -> list[str]:
        """The station list (the key in a header, never in the address)."""
        return [self._list_url()]

    def live_stations(self, kind: Kind, /, *, timeout: float) -> list[StationListEntry]:
        """The list's stations of one family, asked now with the key (one GET)."""
        url = self._list_url()
        with httpx.Client(timeout=timeout, headers=_IDENTIFY) as client:
            payload = _ask(client, url, source=self.server_name)
        return self.parse_station_list(_canonical(payload), kind=kind, filename=url)

    async def live_stations_async(
        self, kind: Kind, /, *, timeout: float
    ) -> list[StationListEntry]:
        """
        Async twin of `live_stations`, paced as every request of the provider.

        The pause runs in a worker thread, so the event loop goes on meanwhile.
        """
        url = self._list_url()
        headers = {**_IDENTIFY, **_headers()}
        await asyncio.to_thread(_PACE.wait, _interval())
        response = await _get_async(
            url, timeout=timeout, headers=headers, source=self.server_name
        )
        payload = _payload(response, url)
        return self.parse_station_list(_canonical(payload), kind=kind, filename=url)

    # --- the station catalog -----------------------------------------------------------

    def catalog_sources(self, raw: Path, /) -> list[tuple[str, ArchiveFile | None]]:
        """The station list, the one source of the catalog."""
        return [
            (
                "gdanskiewody_station_list",
                self.station_file(get_dataset(STATION_LIST), _STATIONS_FILE),
            )
        ]

    def source_datasets(self) -> list[str]:
        """The provider's station list."""
        return [STATION_LIST]

    def build_catalog(self, build: CatalogBuild, /) -> CatalogReport:
        """
        The catalog from the stored station list, the series indexes and the user file.

        Every station of the list and every code of the provider's current series is a
        station; a code only in a series is a station of the series' family without a
        name, located only by the user file. A station's family is the list's
        (``hydro`` when it measures any hydrological quantity), so its precipitation
        may lie in a meteorological series. A point lies in Poland (its packaged
        border, ADR-018) or the station has no location; ``location_source`` is the
        key of the station list (ADR-028 D2) or ``user``.
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
        stations = read_stations(data, filename=str(record["file"]))
        record["count"] = len(stations)
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
        listed = {station.code: station for station in stations}
        families: dict[str, Kind] = {code: item.kind for code, item in listed.items()}
        for kind in ("hydro", "meteo"):
            for code in sorted(series.get(kind, ())):
                families.setdefault(code, kind)
        if (report := build.stopped()) is not None:
            return report
        features = []
        used: dict[str, int] = {}
        without = 0
        for code in sorted(families, key=_code_order):
            station = listed.get(code)
            candidates: list[_Candidate] = []
            if station is not None and station.longitude is not None:
                candidates.append((STATION_LIST, station.longitude, station.latitude))
            if code in user_rows:
                candidates.append(("user", user_rows[code][0], user_rows[code][1]))
            feature, location = _feature(
                code,
                kind=families[code],
                station=station,
                candidates=candidates,
                rejections=rejections,
            )
            if location is None:
                without += 1
            else:
                used[location] = used.get(location, 0) + 1
            features.append(feature)
        series_only = sorted(set(families) - set(listed), key=_code_order)
        lines = _catalog_lines(owner, used)
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
        The daily values of a month file by the provider's day (P5, ADR-034 D5).

        Raises
        ------
        ObserwatorValidationError
            For a file of another dataset (``no_parser_archive``).
        ObserwatorDataError
            If the file cannot be read or holds a day of another month
            (`obserwator._parsing.gdanskiewody`).
        """
        if (
            archive.dataset != MEASUREMENTS
            or archive.station_code is None
            or archive.param is None
        ):
            raise ObserwatorValidationError(
                message("parsing.no_parser_archive", dataset=archive.dataset)
            )
        assert archive.period_start is not None and archive.period_end is not None
        yield from daily_records(
            data,
            dataset=archive.dataset,
            station=archive.station_code,
            symbol=archive.param,
            filename=archive.server_path,
            period=(archive.period_start, archive.period_end),
        )

    def series_reads(self, series: DatasetDescriptor, archive: ArchiveFile, /) -> bool:
        """Whether a series holds the variable of a month file's quantity."""
        found = quantity(archive.param or "")
        if found is None:
            return False
        variable = found.daily if series.time_unit == "day" else found.hourly
        return variable is not None and variable in series.variables

    def hourly_points(
        self,
        archive: ArchiveFile,
        data: bytes,
        /,
        *,
        context: SeriesContext | None = None,
    ) -> Iterator[tuple[str, str, list[tuple[object, object]]]]:
        """
        Every hour of a month file: its station, its variable and the hours' points.

        Each point is the UTC start of its hour (ISO 8601) and its value; an hour
        without a value is ``None``.

        Raises
        ------
        ObserwatorDataError
            If the file cannot be read or holds a day of another month.
        """
        found = quantity(archive.param or "")
        if found is None or found.hourly is None or archive.station_code is None:
            return
        assert archive.period_start is not None and archive.period_end is not None
        points = month_hours(
            data,
            filename=archive.server_path,
            period=(archive.period_start, archive.period_end),
        )
        yield (
            archive.station_code,
            found.hourly,
            [(moment.isoformat(), value) for moment, value in points],
        )


def _code_order(code: str) -> tuple[int, str]:
    """Station codes in the order of their numbers (``…-7`` before ``…-15``)."""
    number = code.rpartition("-")[2]
    return (int(number), code) if number.isdigit() else (0, code)


def _feature(
    code: str,
    *,
    kind: Kind,
    station: GdanskieWodyStation | None,
    candidates: list[_Candidate],
    rejections: list[str],
) -> tuple[dict[str, Any], str | None]:
    """A station of the catalog and the source of its location, None without one."""
    located = _locate(code, candidates, border=POLAND, rejections=rejections)
    geometry, location_source, uncertainty, reason = _placement(located, candidates)
    properties: dict[str, Any] = {
        "station_code": code,
        "kind": kind,
        "meteo_kind": None,
        "name": station.name if station else "",
        "river": None,
        "hydrographic_code": None,
        "river_order": None,
        "location_source": location_source,
        "location_uncertainty_m": uncertainty,
        "location_missing_reason": reason,
        # A station known only from a series is no station of the current list.
        "active": station.active if station else False,
        "established_year": None,
        "gauge_zero_m": None,
        "gauge_zero_datum": None,
        "river_km": None,
        "catchment_area_km2": None,
        "elevation_m": None,
    }
    feature = {
        "type": "Feature",
        "id": code,
        "geometry": geometry,
        "properties": {key: properties[key] for key in _PROPERTIES},
    }
    return feature, location_source


ADAPTER = GdanskieWodyAdapter()
"""The adapter of the provider ``GDANSKIEWODY``."""
