"""
Data fetching functions for IMGW public data.

Provides both synchronous and asynchronous versions of all fetch functions.
Data is fetched directly from IMGW servers and returned; nothing is stored in a
root. Every answer of a source of current data is kept as it came in the capture
spool of ``state_dir`` (`_keep`, ``obserwator.captures``, ADR-030 D7). The paced
requests of a harvest (`PacedSession`: the spacing to a deadline, the backoff and
gzip, ADR-030 D9) are here too.
"""

from __future__ import annotations

import asyncio
import re
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta, tzinfo
from io import BytesIO
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Literal, Protocol, cast
from zipfile import BadZipFile, ZipFile

import httpx
from pydantic import ValidationError

from obserwator._version import __version__
from obserwator.attribution import attribution, dataset_origin
from obserwator.datasets import (
    ArchiveFile,
    MonthsArg,
    ProviderDescriptor,
    YearsArg,
    archive_files,
    get_dataset,
    get_provider,
)
from obserwator.exceptions import (
    ErrorCode,
    ObserwatorCancelledError,
    ObserwatorConnectionError,
    ObserwatorDataError,
    ObserwatorError,
    ObserwatorValidationError,
)
from obserwator.messages import message, reason
from obserwator.models import (
    HydroCurrentData,
    MeteoCurrentData,
    PMaXTPData,
    PMaXTPResult,
    SynopData,
    WarningData,
)
from obserwator.output import (
    FileResult,
    Staging,
    plan_attribution,
    plan_plain,
    refuse,
    refuse_directory,
    resolve_target,
    write_attribution,
)
from obserwator.urls import build_api_url, build_pmaxtp_url

if TYPE_CHECKING:
    from obserwator.store.types import (
        Cancel,
        DownloadItem,
        DownloadReport,
        NoticeHook,
        PathArg,
        ProgressHook,
    )

# Poland coordinate bounds
POLAND_LAT_MIN = 49.0
POLAND_LAT_MAX = 55.0
POLAND_LON_MIN = 14.0
POLAND_LON_MAX = 24.5

DEFAULT_TIMEOUT = 30.0
DOWNLOAD_TIMEOUT = 120.0

UNPUBLISHED = message("common.unpublished")
"""Error text of a candidate file the provider does not publish (HTTP 404/410)."""

# Requests for per-station files (ČHMÚ) identify the library (spec 2026-10-18
# §4.5); IMGW-PIB archive traffic keeps the default headers of 3.0.0.
_IDENTIFY = {"User-Agent": f"obserwator/{__version__}"}
_NOT_PUBLISHED = (404, 410)


@dataclass(frozen=True)
class DownloadResult:
    """Archive bytes and provenance from a single HTTP GET."""

    data: bytes
    url: str
    etag: str | None
    last_modified: str | None
    content_length: int | None


def _download_result(
    response: httpx.Response, *, zipped: bool = True
) -> DownloadResult:
    data = response.content
    if zipped:
        try:
            ZipFile(BytesIO(data)).close()
        except BadZipFile as exc:
            raise ObserwatorDataError(
                message("fetch.invalid_zip_archive_from", url=response.url)
            ) from exc
    length = response.headers.get("Content-Length")
    try:
        content_length = int(length) if length is not None else None
    except ValueError as exc:
        raise ObserwatorDataError(
            message("fetch.invalid_content_length_header", length=length)
        ) from exc
    return DownloadResult(
        data=data,
        url=str(response.url),
        etag=response.headers.get("ETag"),
        last_modified=response.headers.get("Last-Modified"),
        content_length=content_length,
    )


def _json_payload(response: httpx.Response) -> Any:
    try:
        return response.json()
    except ValueError as exc:
        raise ObserwatorDataError(
            message("fetch.invalid_json_response_from", url=response.url)
        ) from exc


def _source_error(
    exc: httpx.HTTPError, url: str, *, source: str = "IMGW"
) -> ObserwatorConnectionError:
    """
    Map a failed request to a provider's server to ``source_unavailable``.

    Parameters
    ----------
    exc : httpx.HTTPError
        Timeout, network error or HTTP 4xx/5xx status of the request.
    url : str
        Requested URL, reported in ``details["url"]``.
    source : str, optional
        Name of the provider in the message, e.g. ``"ČHMÚ"``.

    Returns
    -------
    ObserwatorConnectionError
        Error with ``details`` ``url``, ``reason`` (``timeout``, ``network``
        or ``http_status``) and, for an HTTP status, ``status``.
    """
    if isinstance(exc, httpx.TimeoutException):
        return ObserwatorConnectionError(
            message("fetch.timeout_waiting_server", source=source, url=url),
            details={"url": url, "reason": "timeout"},
        )
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        return ObserwatorConnectionError(
            message(
                "fetch.server_returned_http", source=source, status=status, url=url
            ),
            details={"url": url, "reason": "http_status", "status": status},
        )
    return ObserwatorConnectionError(
        message(
            "fetch.connection_error_server", source=source, exc=reason(exc), url=url
        ),
        details={"url": url, "reason": "network"},
    )


def _keep(response: httpx.Response) -> None:
    """
    Keep an answer in the capture spool when it is one of a capture dataset (P14).

    Every request path of the library hands each read answer here before checking
    it, so an answer of a source of current data is kept whatever its status;
    anything else (an archive, a station list) is left alone. A failure is one
    warning record, never an error of the request (ADR-030 D7).
    """
    from obserwator.captures import keep_response

    keep_response(response)


def _get(
    url: str,
    *,
    timeout: float,
    headers: Mapping[str, str] | None = None,
    source: str = "IMGW",
) -> httpx.Response:
    """GET a URL of the ``source`` provider; failures become ``source_unavailable``."""
    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.get(url, headers=headers)
            _keep(response)
            response.raise_for_status()
    except httpx.HTTPError as exc:
        raise _source_error(exc, url, source=source) from exc
    return response


async def _get_async(
    url: str,
    *,
    timeout: float,
    headers: Mapping[str, str] | None = None,
    source: str = "IMGW",
) -> httpx.Response:
    """Async twin of `_get`."""
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(url, headers=headers)
            await asyncio.to_thread(_keep, response)
            response.raise_for_status()
    except httpx.HTTPError as exc:
        raise _source_error(exc, url, source=source) from exc
    return response


_NO_DATA_KEYS = frozenset({"status", "message"})
"""Keys of the IMGW API answer meaning "no data" (e.g. no meteo warnings)."""


def _records[T](
    payload: object, url: str, parse: Callable[[dict[str, Any]], T]
) -> list[T]:
    """
    Parse the records of an IMGW API answer.

    A single object is one record; ``null`` and an object with only
    ``status``/``message`` (e.g. ``{"message": "Brak ostrzeżeń ..."}``) mean
    no records.

    Parameters
    ----------
    payload : object
        Decoded JSON body.
    url : str
        Requested URL, quoted in error messages.
    parse : callable
        Parser of one record.

    Returns
    -------
    list
        Parsed records in API order.

    Raises
    ------
    ObserwatorDataError
        If the body is not a list of objects or a record cannot be parsed.
    """
    if payload is None or (
        isinstance(payload, dict) and payload.keys() <= _NO_DATA_KEYS
    ):
        return []
    items = [payload] if isinstance(payload, dict) else payload
    if not isinstance(items, list) or not all(isinstance(item, dict) for item in items):
        raise ObserwatorDataError(
            message("fetch.unexpected_response_from_list_objects", url=url)
        )
    try:
        return [parse(cast(dict[str, Any], item)) for item in items]
    except (ValidationError, TypeError, ValueError) as exc:
        raise ObserwatorDataError(
            message("fetch.invalid_record_response_from", url=url, exc=reason(exc))
        ) from exc


def _validate_poland_coords(latitude: float, longitude: float) -> None:
    """Validate that coordinates are numbers within the Poland bounds box."""
    for option, name, value, low, high in (
        (
            "latitude",
            message("fetch.latitude"),
            latitude,
            POLAND_LAT_MIN,
            POLAND_LAT_MAX,
        ),
        (
            "longitude",
            message("fetch.longitude"),
            longitude,
            POLAND_LON_MIN,
            POLAND_LON_MAX,
        ),
    ):
        if (
            isinstance(value, bool)
            or not isinstance(value, int | float)
            or not low <= value <= high
        ):
            details: dict[str, object] = {"option": option}
            if isinstance(value, int | float | str):
                details["value"] = value
            raise ObserwatorValidationError(
                message(
                    "fetch.outside_poland", name=name, value=value, low=low, high=high
                ),
                details=details,
            )


# ============================================================================
# PMAXTP (maximum precipitation of a given duration and probability of exceedance)
# ============================================================================

_PMAXTP_OUTSIDE_GRID = ("poza obszarem", "undefined: lat")
"""Fragments of the PMAXTP API ``error`` texts for a point outside its grid."""


def _check_pmaxtp_payload(payload: object, latitude: float, longitude: float) -> None:
    """
    Reject a PMAXTP response body that reports an error instead of data.

    For points inside the coordinate box but outside its grid (e.g.
    Kaliningrad, Lviv, the Baltic Sea) the API answers HTTP 200 with empty
    ``data`` and ``"error": "Brak pliku, pradopodobnie poza obszarem PL"``
    (earlier ``"undefined: lat …, lon: …, type: KS"``).

    Parameters
    ----------
    payload : object
        Decoded JSON body of the PMAXTP API.
    latitude : float
        Requested latitude, quoted in the message.
    longitude : float
        Requested longitude, quoted in the message.

    Raises
    ------
    ObserwatorValidationError
        If the API reports that the point lies outside the PMAXTP grid.
    ObserwatorDataError
        If the API reports any other error.
    """
    if not isinstance(payload, dict) or not payload.get("error"):
        return
    error = str(payload["error"])
    if any(marker in error.lower() for marker in _PMAXTP_OUTSIDE_GRID):
        raise ObserwatorValidationError(
            message(
                "fetch.point_lies_outside_pmaxtp_grid",
                latitude=latitude,
                longitude=longitude,
                error=error,
            )
        )
    raise ObserwatorDataError(message("fetch.pmaxtp_api_returned_error", error=error))


def _pmaxtp_result(
    raw_data: object,
    method: Literal["POT", "AMP"],
    latitude: float,
    longitude: float,
) -> PMaXTPResult:
    """Validate a PMAXTP response body and build the public result."""
    _check_pmaxtp_payload(raw_data, latitude, longitude)
    try:
        result = PMaXTPResult(
            method=method,
            latitude=latitude,
            longitude=longitude,
            data=PMaXTPData.from_api_response(cast(dict[str, Any], raw_data)),
        )
    except (ValidationError, AttributeError, TypeError, ValueError) as exc:
        raise ObserwatorDataError(
            message("fetch.invalid_pmaxtp_response", exc=reason(exc))
        ) from exc
    if not result.data.ks:
        raise ObserwatorDataError(message("fetch.pmaxtp_response_has_no_data"))
    return result


def fetch_pmaxtp(
    latitude: float,
    longitude: float,
    *,
    method: Literal["POT", "AMP"] = "POT",
    timeout: float = DEFAULT_TIMEOUT,
    validate_coords: bool = True,
) -> PMaXTPResult:
    """
    Fetch PMAXTP data of a point: IMGW-PIB's maximum precipitation.

    PMAXTP („maksymalne opady o określonym czasie trwania i prawdopodobieństwie
    przewyższenia”, the PMAXTP project of IMGW-PIB, ed. B. Ozga-Zieliński, 2022)
    gives precipitation quantiles for 16 durations and 27 probabilities of
    exceedance, for design storms and hydrological modelling. It is not the
    probable maximum precipitation (PMP) of WMO-No. 1045, an upper bound of
    precipitation rather than a quantile. The answer is the cell of IMGW-PIB's
    grid that holds the point, interpolated by kriging from the estimates at
    100 stations (1986-2015); IMGW-PIB's own answer for one of those stations
    may differ at the same place.

    Parameters
    ----------
    latitude : float
        Latitude in decimal degrees (Poland: 49-55).
    longitude : float
        Longitude in decimal degrees (Poland: 14-24.5).
    method : {"POT", "AMP"}, optional
        Sample of the model: "POT" (Peak Over Threshold, the default) or
        "AMP" (Annual Max Precipitation). IMGW-PIB recommends POT for
        probabilities of 50 % and more (e.g. drainage design, where the result
        lies on the safe side) and holds both equivalent below 50 % (the
        monograph, p. 23).
    timeout : float, optional
        Request timeout in seconds.
    validate_coords : bool, optional
        Whether to validate coordinates are within Poland.

    Returns
    -------
    PMaXTPResult
        Precipitation data including ks (quantiles [mm]), sg (upper
        confidence bounds [mm]) and rb (estimation errors [mm]).

    Raises
    ------
    ObserwatorValidationError
        If the method is unknown, coordinates are outside the Poland bounds
        or the API reports the point outside its grid (e.g. Kaliningrad,
        Lviv, the Baltic Sea).
    ObserwatorConnectionError
        If the IMGW server cannot be reached or answers with an HTTP error
        (``details`` ``url``, ``reason`` and, for HTTP errors, ``status``).
    ObserwatorDataError
        If response parsing fails, the API reports another error or the
        response has no quantile table.

    Examples
    --------
    >>> result = fetch_pmaxtp(52.23, 21.01, method="POT")
    >>> precip_15min_p50 = result.data.get_precipitation(15, 50)
    >>> print(f"15-min precipitation, p=50%: {precip_15min_p50} mm")

    Notes
    -----
    Durations [min]: 5, 10, 15, 30, 45, 60, 90, 120, 180, 360, 720, 1080, 1440,
    2160, 2880, 4320. Probabilities [%]: 0.01, 0.02, 0.03, 0.05, 0.1, 0.2, 0.3,
    0.5, 1, 2, 3, 5, 10, 20, 30, 40, 50, 60, 70, 80, 90, 95, 98, 98.5, 99, 99.5,
    99.9. `PMaXTPData.get_precipitation` takes a probability as a number (``0.01``,
    ``50``) and refuses a number that is not in this list.
    """
    if validate_coords:
        _validate_poland_coords(latitude, longitude)
    url = build_pmaxtp_url(latitude, longitude, method=method)
    payload = _json_payload(_get(url, timeout=timeout))
    return _pmaxtp_result(payload, method, latitude, longitude)


async def fetch_pmaxtp_async(
    latitude: float,
    longitude: float,
    *,
    method: Literal["POT", "AMP"] = "POT",
    timeout: float = DEFAULT_TIMEOUT,
    validate_coords: bool = True,
) -> PMaXTPResult:
    """
    Async version of `fetch_pmaxtp`, with identical arguments and result.

    See `fetch_pmaxtp` for full documentation.
    """
    if validate_coords:
        _validate_poland_coords(latitude, longitude)
    url = build_pmaxtp_url(latitude, longitude, method=method)
    payload = _json_payload(await _get_async(url, timeout=timeout))
    return _pmaxtp_result(payload, method, latitude, longitude)


# ============================================================================
# Real-time data (hydro, meteo, synop, warnings)
# ============================================================================


def fetch_hydro_current(
    *,
    station: str | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> list[HydroCurrentData]:
    """
    Fetch current hydrological data from IMGW API.

    Data includes water level, flow, water temperature and the station
    location for monitoring stations.

    Parameters
    ----------
    station : str or None, optional
        Station code; None returns data for all stations.
    timeout : float, optional
        Request timeout in seconds.

    Returns
    -------
    list of HydroCurrentData
        Current measurements for the requested stations.

    Raises
    ------
    ObserwatorConnectionError
        If the IMGW server cannot be reached or answers with an HTTP error,
        including 404 for an unknown station (``details`` ``url``,
        ``reason`` and, for HTTP errors, ``status``).
    ObserwatorDataError
        If the response is not a list of valid records.

    Examples
    --------
    >>> stations = fetch_hydro_current()
    >>> klodzko = fetch_hydro_current(station="150160180")
    >>> print(f"Water level: {klodzko[0].water_level_cm} cm")
    """
    url = build_api_url("hydro", station=station)
    payload = _json_payload(_get(url, timeout=timeout))
    return _records(payload, url, HydroCurrentData.from_api_response)


async def fetch_hydro_current_async(
    *,
    station: str | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> list[HydroCurrentData]:
    """
    Async version of `fetch_hydro_current`, with identical arguments and result.

    See `fetch_hydro_current` for full documentation.
    """
    url = build_api_url("hydro", station=station)
    payload = _json_payload(await _get_async(url, timeout=timeout))
    return _records(payload, url, HydroCurrentData.from_api_response)


def fetch_meteo_current(
    *,
    station: str | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> list[MeteoCurrentData]:
    """
    Fetch current data of automatic meteorological stations from IMGW API.

    Data includes air temperature, mean wind speed, relative humidity,
    10-minute precipitation and the station location.

    Parameters
    ----------
    station : str or None, optional
        Station code; None returns data for all stations.
    timeout : float, optional
        Request timeout in seconds.

    Returns
    -------
    list of MeteoCurrentData
        Current measurements; a value the station does not report is None.

    Raises
    ------
    ObserwatorConnectionError
        If the IMGW server cannot be reached or answers with an HTTP error,
        including 404 for an unknown station (``details`` ``url``,
        ``reason`` and, for HTTP errors, ``status``).
    ObserwatorDataError
        If the response is not a list of valid records.

    Examples
    --------
    >>> [pszczyna] = fetch_meteo_current(station="249180010")
    >>> print(f"Air temperature: {pszczyna.air_temp_c} C")
    """
    url = build_api_url("meteo", station=station)
    payload = _json_payload(_get(url, timeout=timeout))
    return _records(payload, url, MeteoCurrentData.from_api_response)


async def fetch_meteo_current_async(
    *,
    station: str | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> list[MeteoCurrentData]:
    """
    Async version of `fetch_meteo_current`, with identical arguments and result.

    See `fetch_meteo_current` for full documentation.
    """
    url = build_api_url("meteo", station=station)
    payload = _json_payload(await _get_async(url, timeout=timeout))
    return _records(payload, url, MeteoCurrentData.from_api_response)


def _filter_synop(
    records: list[SynopData], station_name: str | None
) -> list[SynopData]:
    """Records whose station name contains ``station_name`` (case-insensitive)."""
    if not station_name:
        return records
    wanted = station_name.casefold()
    return [record for record in records if wanted in record.station_name.casefold()]


def fetch_synop(
    *,
    station: str | None = None,
    station_name: str | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> list[SynopData]:
    """
    Fetch current synoptic data from IMGW API.

    Synoptic data includes temperature, wind, humidity, precipitation, etc.

    Parameters
    ----------
    station : str or None, optional
        Synoptic station code (e.g. ``"12375"``); requests only that station.
    station_name : str or None, optional
        Case-insensitive fragment of the station name, filtered locally.
    timeout : float, optional
        Request timeout in seconds.

    Returns
    -------
    list of SynopData
        Current synoptic measurements for the requested stations.

    Raises
    ------
    ObserwatorConnectionError
        If the IMGW server cannot be reached or answers with an HTTP error,
        including 404 for an unknown station (``details`` ``url``,
        ``reason`` and, for HTTP errors, ``status``).
    ObserwatorDataError
        If the response is not a list of valid records.

    Examples
    --------
    >>> stations = fetch_synop()
    >>> warszawa = fetch_synop(station_name="Warszawa")
    """
    url = build_api_url("synop", station=station)
    payload = _json_payload(_get(url, timeout=timeout))
    return _filter_synop(
        _records(payload, url, SynopData.from_api_response), station_name
    )


async def fetch_synop_async(
    *,
    station: str | None = None,
    station_name: str | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> list[SynopData]:
    """
    Async version of `fetch_synop`, with identical arguments and result.

    See `fetch_synop` for full documentation.
    """
    url = build_api_url("synop", station=station)
    payload = _json_payload(await _get_async(url, timeout=timeout))
    return _filter_synop(
        _records(payload, url, SynopData.from_api_response), station_name
    )


_WARNING_KINDS: tuple[Literal["hydro", "meteo"], ...] = ("hydro", "meteo")


def _warning_sources(
    kind: Literal["hydro", "meteo"] | None,
) -> list[tuple[Literal["hydro", "meteo"], str]]:
    """Warning families to fetch with their endpoint URLs, hydro first."""
    if kind is not None and kind not in _WARNING_KINDS:
        raise ObserwatorValidationError(
            message("fetch.unknown_kind_warnings_allowed_hydro", kind=kind),
            details={"option": "kind", "allowed": list(_WARNING_KINDS)},
        )
    kinds = _WARNING_KINDS if kind is None else (kind,)
    return [(family, build_api_url(f"warnings{family}")) for family in kinds]


def _warning_parser(
    kind: Literal["hydro", "meteo"],
) -> Callable[[dict[str, Any]], WarningData]:
    return lambda record: WarningData.from_api_response(record, kind=kind)


def fetch_warnings(
    *,
    kind: Literal["hydro", "meteo"] | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> list[WarningData]:
    """
    Fetch current hydrological and/or meteorological warnings from IMGW.

    Parameters
    ----------
    kind : {"hydro", "meteo"} or None, optional
        Warning family; None fetches both (hydro warnings first).
    timeout : float, optional
        Request timeout in seconds.

    Returns
    -------
    list of WarningData
        Active warnings, each with its family in ``kind``. Empty list if
        there are none.

    Raises
    ------
    ObserwatorValidationError
        If ``kind`` is not ``"hydro"``, ``"meteo"`` or None.
    ObserwatorConnectionError
        If an IMGW server cannot be reached or answers with an HTTP error
        (``details`` ``url``, ``reason`` and, for HTTP errors, ``status``).
    ObserwatorDataError
        If a response is not a list of valid records.

    Examples
    --------
    >>> for warning in fetch_warnings():
    ...     print(f"{warning.kind} {warning.level}: {warning.event}")
    """
    result: list[WarningData] = []
    for family, url in _warning_sources(kind):
        payload = _json_payload(_get(url, timeout=timeout))
        result.extend(_records(payload, url, _warning_parser(family)))
    return result


async def fetch_warnings_async(
    *,
    kind: Literal["hydro", "meteo"] | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> list[WarningData]:
    """
    Async version of `fetch_warnings`, with identical arguments and result.

    See `fetch_warnings` for full documentation.
    """
    result: list[WarningData] = []
    for family, url in _warning_sources(kind):
        payload = _json_payload(await _get_async(url, timeout=timeout))
        result.extend(_records(payload, url, _warning_parser(family)))
    return result


# ============================================================================
# Archive data download
# ============================================================================


def _archive_slot(archive: ArchiveFile) -> str:
    """
    Return the slot of an IMGW archive or station list file (spec §13.7).

    Parameters
    ----------
    archive : ArchiveFile
        File from the dataset registry.

    Returns
    -------
    str
        ``archive:<dataset key>:<server_path without the dataset server_dir>``,
        e.g. ``archive:pl.imgw.hydro_daily:2024/codz_2024.zip``.
    """
    server_dir = get_dataset(archive.dataset).server_dir
    selector = archive.server_path.removeprefix(f"{server_dir}/")
    return f"archive:{archive.dataset}:{selector}"


def _single_archive(
    files: tuple[ArchiveFile, ...], *, option: Literal["month", "param"]
) -> ArchiveFile:
    """Return the only archive selected by 2.1.1 download arguments."""
    if len(files) == 1:
        return files[0]
    if option == "param":
        text = message("fetch.archive_needs_parameter_t_q", dataset=files[0].dataset)
    else:
        text = message(
            "fetch.archive_published_monthly_files_give",
            dataset=files[0].dataset,
            year=files[0].year,
        )
    raise ObserwatorValidationError(text, details={"option": option})


def _legacy_year(year: object) -> int:
    if isinstance(year, bool) or not isinstance(year, int):
        raise ObserwatorValidationError(
            message("fetch.year_must_integer", year=year),
            details={"option": "year", "value": str(year)},
        )
    return year


def _hydro_archive(
    interval: str, year: int, month: int | None, param: str | None
) -> ArchiveFile:
    """Registry archive of the 2.1.1 `download_hydro_data` arguments."""
    year = _legacy_year(year)
    if interval == "dobowe" and month == 13:
        return archive_files("pl.imgw.hydro_phenomena", years=year)[0]
    descriptor = get_dataset(f"hydro/{interval}")
    semiannual = descriptor.key == "pl.imgw.hydro_semiannual"
    files = archive_files(
        descriptor.key,
        years=year,
        months=month,
        params=[cast(Literal["H", "Q", "T"], param)] if semiannual and param else None,
    )
    return _single_archive(files, option="param" if semiannual else "month")


def _meteo_archive(
    interval: str, subtype: str, year: int, month: int | None
) -> ArchiveFile:
    """Registry archive of the 2.1.1 `download_meteo_data` arguments."""
    year = _legacy_year(year)
    descriptor = get_dataset(f"meteo/{interval}/{subtype}")
    files = archive_files(descriptor.key, years=year, months=month)
    return _single_archive(files, option="month")


def _archive_response(
    client: httpx.Client, url: str, *, source: str = "IMGW", zipped: bool = True
) -> DownloadResult:
    """
    GET one source file; HTTP failures become ``source_unavailable``.

    Parameters
    ----------
    client : httpx.Client
        Client of the download.
    url : str
        URL of the file.
    source : str, optional
        Name of the provider in error messages.
    zipped : bool, optional
        Whether the bytes must form a ZIP archive (IMGW-PIB); per-station
        ČHMÚ files (JSON, CSV) are taken as they are.

    Returns
    -------
    DownloadResult
        Original bytes and response headers.

    Raises
    ------
    ObserwatorConnectionError
        If the request fails (``details`` ``url``, ``reason`` and, for an
        HTTP error, ``status``).
    ObserwatorDataError
        If ``zipped`` bytes are no ZIP archive or ``Content-Length`` is
        invalid.
    """
    try:
        response = client.get(url)
        _keep(response)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise _source_error(exc, url, source=source) from exc
    return _download_result(response, zipped=zipped)


async def _archive_response_async(
    client: httpx.AsyncClient, url: str
) -> DownloadResult:
    """Async twin of `_archive_response`."""
    try:
        response = await client.get(url)
        await asyncio.to_thread(_keep, response)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise _source_error(exc, url) from exc
    return _download_result(response)


def download_hydro_data(
    interval: Literal["dobowe", "miesieczne", "polroczne_i_roczne"],
    year: int,
    month: int | None = None,
    param: Literal["T", "Q", "H"] | None = None,
    *,
    timeout: float = DOWNLOAD_TIMEOUT,
) -> DownloadResult:
    """
    Download one hydrological archive as ZIP bytes.

    The file is resolved through the dataset registry (`archive_files`): the
    interval is the legacy alias ``hydro/<interval>`` and ``dobowe`` with
    ``month=13`` selects ``pl.imgw.hydro_phenomena`` (``zjaw_<year>.zip``).
    Use `parse_zip_file` to extract and parse the data.

    Parameters
    ----------
    interval : {"dobowe", "miesieczne", "polroczne_i_roczne"}
        Data interval: daily, monthly or semi-annual/annual.
    year : int
        Hydrological year (from 1951).
    month : int or None, optional
        Hydrological month 1-12 (1 = November), required for daily data
        before 2023; 13 selects the daily phenomena archive.
    param : {"T", "Q", "H"} or None, optional
        Parameter of semi-annual data, required there: "T" (temperature),
        "Q" (flow) or "H" (water level).
    timeout : float, optional
        Request timeout in seconds.

    Returns
    -------
    DownloadResult
        Original ZIP bytes and response headers.

    Raises
    ------
    ObserwatorValidationError
        If the interval is unknown, the year or month is invalid, or a
        required month or parameter is missing (``details["option"]``).
    ObserwatorConnectionError
        If the download fails (``source_unavailable``; ``details`` ``url``,
        ``reason`` and, for HTTP errors, ``status``).
    ObserwatorDataError
        If the downloaded data is not a ZIP archive.

    Examples
    --------
    >>> response = download_hydro_data("dobowe", 2023)
    >>> from obserwator import parse_zip_file
    >>> for station, record in parse_zip_file(response.data, "dobowe"):
    ...     print(f"{station.station_name}: {record.water_level_cm} cm")
    """
    archive = _hydro_archive(interval, year, month, param)
    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        return _archive_response(client, archive.url)


async def download_hydro_data_async(
    interval: Literal["dobowe", "miesieczne", "polroczne_i_roczne"],
    year: int,
    month: int | None = None,
    param: Literal["T", "Q", "H"] | None = None,
    *,
    timeout: float = DOWNLOAD_TIMEOUT,
) -> DownloadResult:
    """
    Async version of `download_hydro_data`, with identical arguments and result.

    See `download_hydro_data` for full documentation.
    """
    archive = _hydro_archive(interval, year, month, param)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        return await _archive_response_async(client, archive.url)


def download_meteo_data(
    interval: Literal["dobowe", "miesieczne", "terminowe"],
    subtype: Literal["klimat", "opad", "synop"],
    year: int,
    month: int | None = None,
    *,
    timeout: float = DOWNLOAD_TIMEOUT,
) -> DownloadResult:
    """
    Download one meteorological archive as ZIP bytes.

    The file is resolved through the dataset registry (`archive_files`) from
    the legacy alias ``meteo/<interval>/<subtype>``; a monthly archive covers
    the whole folder (five years until 2000) containing ``year``.

    Parameters
    ----------
    interval : {"dobowe", "miesieczne", "terminowe"}
        Data interval: daily, monthly or hourly.
    subtype : {"klimat", "opad", "synop"}
        Data subtype: climate, precipitation or synoptic.
    year : int
        Calendar year.
    month : int or None, optional
        Month 1-12, required for daily and hourly data from 2001; for synop it
        names the monthly file of the whole country that IMGW-PIB publishes
        for the running year (the closed years are per-station archives, see
        `download_archives`).
    timeout : float, optional
        Request timeout in seconds.

    Returns
    -------
    DownloadResult
        Original ZIP bytes and response headers.

    Raises
    ------
    ObserwatorValidationError
        If the combination is not published as a single archive (hourly
        precipitation; ``details["reason"]``), synop is asked for without a
        month, the year or month is invalid, or a required month is missing.
    ObserwatorConnectionError
        If the download fails (``source_unavailable``; ``details`` ``url``,
        ``reason`` and, for HTTP errors, ``status``).
    ObserwatorDataError
        If the downloaded data is not a ZIP archive.

    Examples
    --------
    >>> response = download_meteo_data("miesieczne", "opad", 2023)
    >>> response.data[:2]
    b'PK'
    """
    archive = _meteo_archive(interval, subtype, year, month)
    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        return _archive_response(client, archive.url)


async def download_meteo_data_async(
    interval: Literal["dobowe", "miesieczne", "terminowe"],
    subtype: Literal["klimat", "opad", "synop"],
    year: int,
    month: int | None = None,
    *,
    timeout: float = DOWNLOAD_TIMEOUT,
) -> DownloadResult:
    """
    Async version of `download_meteo_data`, with identical arguments and result.

    See `download_meteo_data` for full documentation.
    """
    archive = _meteo_archive(interval, subtype, year, month)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        return await _archive_response_async(client, archive.url)


_STREAM_CHUNK = 1 << 16
"""Size of the pieces a plain download is read, hashed and written in."""


def _origin(archive: ArchiveFile) -> tuple[ProviderDescriptor, bool]:
    """Provider of an archive and whether its files are per station (ČHMÚ)."""
    descriptor = get_dataset(archive.dataset)
    return get_provider(descriptor.provider), descriptor.archive_scope != "country"


def _server(archive: ArchiveFile) -> str:
    """
    The server's name in the texts of a failed download of an archive.

    The provider's short name for a file of one station, its adapter's
    ``server_name`` for a file of the whole country (``IMGW``, as 3.0.0 wrote).
    """
    provider, per_station = _origin(archive)
    return provider.short_name if per_station else provider.adapter.server_name


def _zipped(archive: ArchiveFile) -> bool:
    """Whether the bytes of an archive must form a ZIP archive (by its name)."""
    return archive.server_path.lower().endswith(".zip")


def _download_files(
    dataset: str,
    /,
    *,
    years: YearsArg | None,
    months: MonthsArg | None,
    params: Iterable[Literal["H", "Q", "T"]] | None,
    stations: Iterable[str] | None,
    index: bool = True,
    timeout: float = DEFAULT_TIMEOUT,
) -> tuple[ArchiveFile, ...]:
    """
    Files of a download: `archive_files`, or the server's index of a dataset named there.

    With ``index=False`` the selection of an indexed dataset is only checked
    (offline) and no file is returned.
    """
    descriptor = get_dataset(dataset)
    adapter = get_provider(descriptor.provider).adapter
    if not adapter.indexed(descriptor):
        return archive_files(
            dataset, years=years, months=months, params=params, stations=stations
        )
    return adapter.index_files(
        descriptor,
        years=years,
        params=params,
        stations=stations,
        index=index,
        timeout=timeout,
    )


def _stage(
    client: httpx.Client,
    archive: ArchiveFile,
    staging: Staging,
    *,
    source: str,
    zipped: bool,
) -> tuple[Path, int, str]:
    """
    GET one source file straight into the staging directory (DEV-19.7).

    The bytes are hashed while they stream to the staged file; an archive that
    must be a ZIP is verified there, before it is moved into place.

    Returns
    -------
    tuple of (pathlib.Path, int, str)
        The staged file, its size and its SHA-256.

    Raises
    ------
    ObserwatorConnectionError
        If the request fails (``source_unavailable``).
    ObserwatorDataError
        If ``zipped`` bytes are no ZIP archive.
    """
    try:
        with client.stream("GET", archive.url) as response:
            response.raise_for_status()
            staged, size, sha256 = staging.write(response.iter_bytes(_STREAM_CHUNK))
    except httpx.HTTPError as exc:
        raise _source_error(exc, archive.url, source=source) from exc
    if zipped:
        try:
            ZipFile(staged).close()
        except BadZipFile as exc:
            staged.unlink(missing_ok=True)
            raise ObserwatorDataError(
                message("fetch.invalid_zip_archive_from", url=archive.url)
            ) from exc
    return staged, size, sha256


def _download_loop(
    files: Sequence[ArchiveFile],
    save: Callable[[httpx.Client, ArchiveFile], FileResult],
    *,
    timeout: float,
    on_progress: ProgressHook | None,
    on_notice: NoticeHook | None,
    cancel: Cancel | None,
) -> tuple[list[DownloadItem], list[FileResult]]:
    """
    Download every archive with ``save`` and report each file as an item.

    A failed file becomes a ``failed`` item and the others are still
    downloaded; a ČHMÚ candidate the server answers with HTTP 404 or 410 is a
    successful ``not_published`` item; ``cancel`` is polled before every file.
    """
    # store.types is imported lazily: the obserwator.store package imports this module.
    from obserwator.store.types import DownloadItem, Notice, Progress

    items: list[DownloadItem] = []
    written: list[FileResult] = []
    licensed: set[str] = set()
    listed = any(_origin(archive)[1] for archive in files)
    with httpx.Client(
        timeout=timeout,
        follow_redirects=True,
        headers=_IDENTIFY if listed else None,
    ) as client:
        for index, archive in enumerate(files):
            if cancel is not None and cancel():
                items.extend(
                    DownloadItem(
                        _archive_slot(rest), rest.url, "cancelled", None, None, None
                    )
                    for rest in files[index:]
                )
                break
            provider, per_station = _origin(archive)
            slot = _archive_slot(archive)
            try:
                result = save(client, archive)
            except ObserwatorCancelledError:
                items.extend(
                    DownloadItem(
                        _archive_slot(rest), rest.url, "cancelled", None, None, None
                    )
                    for rest in files[index:]
                )
                break
            except ObserwatorError as exc:
                if per_station and exc.details.get("status") in _NOT_PUBLISHED:
                    item = DownloadItem(
                        slot, archive.url, "not_published", None, UNPUBLISHED, None
                    )
                else:
                    item = DownloadItem(
                        slot, archive.url, "failed", None, exc.detail, exc.code
                    )
            except OSError as exc:
                item = DownloadItem(
                    slot,
                    archive.url,
                    "failed",
                    None,
                    message(
                        "fetch.cannot_save_archive",
                        path=archive.server_path,
                        exc=reason(exc),
                    ),
                    "io_error",
                )
            else:
                written.append(result)
                item = DownloadItem(
                    slot, archive.url, "downloaded", result.path, None, None
                )
            items.append(item)
            if on_progress is not None:
                on_progress(
                    Progress(
                        index + 1,
                        len(files),
                        "archive",
                        item.status,
                        message(
                            "fetch.archive_downloaded", server_path=archive.server_path
                        )
                        if item.path is not None
                        else message(
                            "fetch.archive_not_downloaded",
                            server_path=archive.server_path,
                            error=item.error,
                        ),
                    )
                )
            if item.path is not None and provider.id not in licensed:
                licensed.add(provider.id)
                if on_notice is not None:
                    on_notice(
                        Notice("info", "license_terms", provider.license_notice())
                    )
    return items, written


def _download_plain(
    files: Sequence[ArchiveFile],
    directory: Path,
    *,
    force: bool,
    timeout: float,
    on_progress: ProgressHook | None,
    on_notice: NoticeHook | None,
    cancel: Cancel | None,
) -> tuple[list[DownloadItem], list[FileResult]]:
    """
    Write the archives as ordinary files below ``directory`` (DEV-19.5 to DEV-19.9).

    The names are the server paths. The output directory is checked first
    (`refuse_directory`), then the full target list with the directory's
    ``ATTRIBUTION.txt``, both before the first request (`plan_plain`,
    `plan_attribution`, `refuse`); each file is streamed to the staging
    directory, verified and moved into place with ``os.replace``. Once a file
    is written, the attribution file gets the lines of the verbatim files
    (ADR-012) and is the last entry of the returned files.

    Raises
    ------
    ObserwatorError
        ``conflict`` (``output_in_store`` with the directory as the path for a
        directory that is or lies in a store; ``duplicate_output_name``,
        ``output_in_store`` for a target that would enter a store below the
        directory, ``output_exists``) before anything is requested or written.
    OSError
        If the output directory cannot be created.
    """
    refuse_directory(directory)
    lines = attribution(
        *dict.fromkeys(dataset_origin(archive.dataset) for archive in files),
        processed=False,
    )
    attribution_entry = plan_attribution(directory, lines)
    refuse(
        [
            *plan_plain(
                directory, [archive.server_path for archive in files], force=force
            ),
            *([] if attribution_entry is None else [attribution_entry]),
        ]
    )
    with Staging(directory) as staging:

        def save(client: httpx.Client, archive: ArchiveFile) -> FileResult:
            staged, size, sha256 = _stage(
                client,
                archive,
                staging,
                source=_server(archive),
                zipped=_zipped(archive),
            )
            target = directory.joinpath(*archive.server_path.split("/"))
            return staging.commit(staged, target, size, sha256)

        items, written = _download_loop(
            files,
            save,
            timeout=timeout,
            on_progress=on_progress,
            on_notice=on_notice,
            cancel=cancel,
        )
    if written and (noted := write_attribution(directory, lines)) is not None:
        written = [*written, noted]
    return items, written


def _download_store(
    files: Sequence[ArchiveFile],
    root: Path,
    *,
    timeout: float,
    on_progress: ProgressHook | None,
    on_notice: NoticeHook | None,
    cancel: Cancel | None,
) -> tuple[list[DownloadItem], list[FileResult]]:
    """
    Publish the archives as versions in the store at ``root`` (``write_archive``).

    Every file is fetched (there is no freshness check) and gets the status of
    its version: ``new``, ``unchanged`` or ``relabeled``.

    Raises
    ------
    ObserwatorStoreError
        If ``root`` is no usable store (the layout has no marker).
    ObserwatorStoreConflictError
        If the root nests a store or holds foreign files.
    """
    # The writer imports this module, so it is imported lazily.
    from obserwator.store.types import Notice
    from obserwator.store.writer import prepare_store, write_archive

    handle = prepare_store(root)

    def forward(notice: Notice) -> None:
        # The license notice is sent once per provider by the loop.
        if on_notice is not None and notice.code != "license_terms":
            on_notice(notice)

    def save(client: httpx.Client, archive: ArchiveFile) -> FileResult:
        response = _archive_response(
            client,
            archive.url,
            source=_server(archive),
            zipped=_zipped(archive),
        )
        version = write_archive(
            handle, archive=archive, response=response, on_notice=forward, cancel=cancel
        )
        return FileResult(
            version.path, version.path.stat().st_size, version.sha256, version.status
        )

    return _download_loop(
        files,
        save,
        timeout=timeout,
        on_progress=on_progress,
        on_notice=on_notice,
        cancel=cancel,
    )


def download_archives(
    dataset: str,
    /,
    *,
    years: YearsArg | None = None,
    months: MonthsArg | None = None,
    params: Iterable[Literal["H", "Q", "T"]] | None = None,
    stations: Iterable[str] | None = None,
    output_dir: PathArg | None = None,
    root: PathArg | None = None,
    force: bool = False,
    timeout: float = DOWNLOAD_TIMEOUT,
    on_progress: ProgressHook | None = None,
    on_notice: NoticeHook | None = None,
    cancel: Cancel | None = None,
) -> DownloadReport:
    """
    Download the source files of a dataset as plain files or into the raw root.

    With ``output_dir`` (plain mode, DEV-19.1) every file of `archive_files`
    is written as ``<output_dir>/<server_path>``: before the first request the
    full list of targets is checked and an existing target without ``force``,
    a duplicate name or a directory that is, or lies in, a store is a
    ``conflict`` that lists every path; each file is streamed to
    ``<output_dir>/.obserwator-incoming/<host>_<pid>_<token>/``, hashed while it
    streams, verified and moved into place with ``os.replace``, so an
    interrupted download leaves no partial file. Without ``output_dir`` the
    files are published as versions in the raw root at ``root`` (ADR-017; the
    default raw root when ``root`` is not given: ``OBSERWATOR_RAW_ROOT``,
    ``[obserwator] raw_root`` of ``nogat.toml`` or ``<data_dir>/obserwator-raw``);
    only the datasets of the store are accepted. A failed file becomes a
    ``failed`` item and the remaining files are still downloaded. Per-station
    files (ČHMÚ, the per-station synop archives of IMGW-PIB) are candidates
    that are fetched without a listing (spec 2026-10-18 §4.4): a candidate the
    server answers with HTTP 404 or 410 is a successful ``not_published``
    item. The files of ``pl.imgw.actinometric`` are found in the server's
    folder index before the first file is fetched (ADR-023): every station,
    the year folders of the selected years and the files outside the year
    folders. Only names ending with ``.zip`` must be ZIP archives.

    Parameters
    ----------
    dataset : str
        Key, slug or legacy alias of an archive dataset.
    years : YearsArg or None, optional
        Archive years: a number, a range ``"a-b"``, a list ``"a,b"`` or an
        iterable of these. Required except for ``cz.chmu.meteo_daily``, which
        rejects it.
    months : MonthsArg or None, optional
        Months 1-12 of physically monthly files; None selects all months.
        Rejected for ČHMÚ datasets; for the per-station synop archives of
        IMGW-PIB the monthly files of the whole country (see `archive_files`).
    params : iterable of {"H", "Q", "T"} or None, optional
        Parameters of ``pl.imgw.hydro_semiannual``; None selects all three.
    stations : iterable of str or None, optional
        Station codes: ČHMÚ WIGOS identifiers, required for ČHMÚ datasets;
        9-digit IMGW-PIB codes for the per-station synop archives; rejected for
        other IMGW-PIB datasets.
    output_dir : str or os.PathLike or None, optional
        Plain mode: directory of the files, created when missing. Excludes
        ``root``.
    root : str or os.PathLike or None, optional
        Store mode: the raw root; None (with no ``output_dir``) is the
        default raw root.
    force : bool, optional
        Plain mode: replace existing target files (each atomically, nothing
        else is deleted). Store mode: the files are fetched again anyway and
        a version is never overwritten, so it changes nothing.
    timeout : float, optional
        Request timeout in seconds, per file.
    on_progress : ProgressHook or None, optional
        Called after every file with status ``downloaded``,
        ``not_published`` or ``failed``.
    on_notice : NoticeHook or None, optional
        Receives the ``license_terms`` notice of the provider once, after the
        first downloaded file.
    cancel : Cancel or None, optional
        Polled before every file; returning ``True`` stops the download and
        reports the remaining files as ``cancelled``.

    Returns
    -------
    DownloadReport
        The mode, the absolute ``output_dir`` or ``root``, one item per file
        in download order (the §13.7 slot, URL, status, written path and, for
        a failed file, the error text and code: ``source_unavailable``,
        ``data_error`` or ``io_error``; a ``not_published`` item has no path,
        the error ``"not published"`` and no code) and ``files``: the files
        written with their size, SHA-256 and status (``written`` or
        ``replaced`` in plain mode, ``new``, ``unchanged`` or ``relabeled``
        in store mode).

    Raises
    ------
    ObserwatorValidationError
        If the dataset, years, months, params or stations are invalid
        (``details["option"]``); if both ``output_dir`` and ``root`` are
        given (``details["reason"]="exclusive_options"``); or if a store
        download names a dataset outside the store
        (``details["reason"]="not_in_store"``).
    ObserwatorError
        ``conflict`` in plain mode before any request: an output directory that
        is or lies in a store (``output_in_store``, ``details["paths"]`` is the
        directory), then an existing target without ``force``
        (``output_exists``), duplicate names (``duplicate_output_name``) or a
        target that would enter a store below the directory
        (``output_in_store``); ``details["paths"]`` lists every such path. In
        store mode ``store_unavailable`` (a layout without a marker, or a data
        root: ``details["reason"]="wrong_root"``) or ``conflict`` (a nested
        store, ``nested_store``, or a root with other files, ``not_empty``).
    OSError
        If the output directory cannot be created.

    Examples
    --------
    >>> report = download_archives(
    ...     "meteo/miesieczne/synop", years=1998, output_dir="data/synop"
    ... )
    >>> [item.status for item in report.items]
    ['downloaded']
    >>> [file.status for file in report.files]
    ['written']
    """
    # The selection is checked offline first; the folder index is read only for
    # a download that can take place.
    files = _download_files(
        dataset,
        years=years,
        months=months,
        params=params,
        stations=stations,
        index=False,
    )
    descriptor = get_dataset(dataset)
    target = resolve_target(output_dir=output_dir, root=root)
    # store.types is imported lazily: the obserwator.store package imports this module.
    from obserwator.store.types import DownloadReport

    if target.mode != "plain" and not descriptor.in_store:
        raise ObserwatorValidationError(
            message("fetch.not_in_store", dataset=descriptor.key),
            details={
                "option": "dataset",
                "value": descriptor.key,
                "reason": "not_in_store",
            },
        )
    if get_provider(descriptor.provider).adapter.indexed(descriptor):
        files = _download_files(
            dataset, years=years, months=months, params=params, stations=stations
        )
    if target.mode == "plain":
        items, written = _download_plain(
            files,
            target.path,
            force=force,
            timeout=timeout,
            on_progress=on_progress,
            on_notice=on_notice,
            cancel=cancel,
        )
        directory, store = target.path, None
    else:
        items, written = _download_store(
            files,
            target.path,
            timeout=timeout,
            on_progress=on_progress,
            on_notice=on_notice,
            cancel=cancel,
        )
        directory, store = None, target.path
    cancelled = any(item.status == "cancelled" for item in items)
    return DownloadReport(
        target.mode, directory, store, tuple(items), tuple(written), cancelled
    )


# ============================================================================
# Paced requests of a harvest (ADR-030 D9)
# ============================================================================

MIN_SPACING = 5.0
"""
The shortest spacing of two requests of a paced run, in seconds (ADR-030 D9).

A run without a deadline, or whose deadline has passed (a missed night caught up
later), asks at this spacing; a run with a deadline never asks closer.
"""
BACKOFF: tuple[float, ...] = (60.0, 120.0, 240.0)
"""
Seconds waited after an answer 429 or 5xx before the request is asked again.

A request still refused after the last wait skips its station until the next run.
"""
CONNECTION_FAILURES = 3
"""Requests in a row without any answer (timeouts, network errors) that end a paced run."""
_GZIP: Mapping[str, str] = MappingProxyType({"Accept-Encoding": "gzip"})
_PACE_UNTIL = re.compile(r"^([01][0-9]|2[0-3]):([0-5][0-9])$")
_TICK = 1.0
"""The longest single sleep of a paced run: a cancel is noticed within it."""
_UNAVAILABLE: ErrorCode = "source_unavailable"


class Clock(Protocol):
    """The time of a paced run: a test gives a fake one, so that no test sleeps."""

    def now(self) -> datetime:
        """The current time, UTC."""
        ...

    def sleep(self, seconds: float, /) -> None:
        """Wait ``seconds``."""
        ...


class SystemClock:
    """The real clock of a paced run: `datetime.now` in UTC and `time.sleep`."""

    def now(self) -> datetime:
        """The current time, UTC."""
        return datetime.now(UTC)

    def sleep(self, seconds: float, /) -> None:
        """Wait ``seconds``."""
        time.sleep(seconds)


def _clock() -> Clock:
    """The clock of a paced run (tests replace it)."""
    return SystemClock()


def pace_deadline(
    until: str | None, /, *, now: datetime, tz: tzinfo | None = None
) -> datetime | None:
    """
    The deadline of ``--pace-until HH:MM``: that time of the local day of ``now``.

    A deadline that has already passed is kept as it is: the run asks at the
    minimum spacing (`MIN_SPACING`), as a missed night caught up later does.

    Parameters
    ----------
    until : str or None
        ``HH:MM`` (24 h), local time; None for no deadline.
    now : datetime.datetime
        The current time (aware).
    tz : datetime.tzinfo or None, optional
        The local time zone; None is the system's.

    Returns
    -------
    datetime.datetime or None
        The deadline in UTC; None without ``until``.

    Raises
    ------
    ObserwatorValidationError
        If ``until`` is no ``HH:MM`` (``details.option`` ``pace_until``).
    """
    if until is None:
        return None
    match = _PACE_UNTIL.fullmatch(until) if isinstance(until, str) else None
    if match is None:
        raise ObserwatorValidationError(
            message("fetch.pace_until_invalid", value=until),
            details={"option": "pace_until", "value": str(until)},
        )
    local = now.astimezone(tz).replace(
        hour=int(match[1]), minute=int(match[2]), second=0, microsecond=0
    )
    return local.astimezone(UTC)


@dataclass(frozen=True)
class PacedRequest:
    """
    One planned request of a paced run (`PacedSession.run`).

    Attributes
    ----------
    url : str
        The address to ask.
    station : str
        The station it belongs to: a request refused after the backoff skips the
        station's other requests of the run.
    headers : Mapping of str to str, optional
        Request headers (the user agent a source needs).
    """

    url: str
    station: str
    headers: Mapping[str, str] = MappingProxyType({})


@dataclass(frozen=True)
class PacedOutcome:
    """
    What came of one planned request of a paced run.

    Attributes
    ----------
    request : PacedRequest
        The request.
    status : {"answered", "failed", "skipped", "stopped", "cancelled"}
        ``answered``: an answer 2xx, or 404 or 410 (nothing published for the
        station), kept in the spool; ``failed``: no answer (a connection failure),
        another refusal (kept in the spool) or an answer the spool could not keep;
        ``skipped``: the station was refused (429 or 5xx) after the backoff, by this
        request or an earlier one of the station; ``stopped``: not asked, the run
        ended after `CONNECTION_FAILURES` connection failures in a row;
        ``cancelled``: not asked, the run was cancelled.
    http_status : int or None, optional
        The status of the last answer; None without one.
    attempts : int, optional
        Requests made for it, the retries of the backoff included.
    asked_at : datetime.datetime or None, optional
        When it was last asked (UTC); None when it was not.
    error : str or None, optional
        Why it failed, was skipped or not asked; None when answered.
    error_code : ErrorCode or None, optional
        The code of that error: ``source_unavailable`` (no answer, a refusal, a
        skipped station, a stopped run), ``io_error`` (the spool did not keep the
        answer) or ``cancelled``; None when answered.
    """

    request: PacedRequest
    status: Literal["answered", "failed", "skipped", "stopped", "cancelled"]
    http_status: int | None = None
    attempts: int = 0
    asked_at: datetime | None = None
    error: str | None = None
    error_code: ErrorCode | None = None


class _Refused(Exception):
    """A request still answered 429 or 5xx after the backoff."""

    def __init__(self, response: httpx.Response) -> None:
        super().__init__(response.status_code)
        self.response = response


class _Stopped(Exception):
    """`CONNECTION_FAILURES` requests in a row without any answer."""

    def __init__(self, failure: httpx.RequestError) -> None:
        super().__init__(str(failure))
        self.failure = failure


def _backs_off(status: int) -> bool:
    """Whether an answer is retried after a wait: 429 Too Many Requests and 5xx."""
    return status == 429 or status >= 500


class PacedSession:
    """
    The requests of one run, one at a time, spread evenly to a deadline (ADR-030 D9).

    The one place of the pacing, the backoff and gzip of Obserwator's harvests:

    - **Pacing:** each request waits until a spacing has passed since the one
      before: with a deadline the time left divided by the requests left plus one
      (`run` spreads its requests so that the last one comes a spacing before the
      deadline), never less than `MIN_SPACING`; without a deadline, or with one
      already passed, `MIN_SPACING`.
    - **Backoff:** an answer 429 or 5xx is asked again after each wait of
      `BACKOFF` (60, 120 and 240 s); still refused, the request is refused.
    - **Connection failures:** `CONNECTION_FAILURES` requests in a row without any
      answer end the run; any answer resets the count.
    - **gzip:** every request asks for a gzip-compressed answer, which httpx
      decompresses.
    - **Captures:** every answer (each attempt's, refusals included) goes to the
      capture spool when its address belongs to a capture dataset (P14).

    Parameters
    ----------
    deadline : datetime.datetime or None, optional
        When the requests should be done (`pace_deadline`); None for none.
    clock : Clock or None, optional
        The clock (tests give a fake one); None is the system's.
    timeout : float, optional
        Timeout of each request in seconds.
    cancel : Cancel or None, optional
        Polled before each request and during every wait.
    source : str, optional
        The server's name in the texts of a failed request.
    """

    def __init__(
        self,
        *,
        deadline: datetime | None = None,
        clock: Clock | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        cancel: Cancel | None = None,
        source: str = "IMGW",
    ) -> None:
        self.deadline = deadline
        self.clock = _clock() if clock is None else clock
        self.source = source
        self._timeout = timeout
        self._cancel = cancel
        self._client: httpx.Client | None = None
        self._last: datetime | None = None
        self._failures = 0
        self.requests = 0
        """Requests made: the retries of the backoff included."""
        self.answers = 0
        """Answers received, whatever their status."""
        self.stopped = False
        """Whether `run` ended after `CONNECTION_FAILURES` connection failures in a row."""

    def __enter__(self) -> PacedSession:
        """Open the client of the run (gzip-compressed answers)."""
        self._client = httpx.Client(timeout=self._timeout, headers=dict(_GZIP))
        return self

    def __exit__(self, *exc: object) -> None:
        """Close the client of the run."""
        if self._client is not None:
            self._client.close()
            self._client = None

    def _check_cancel(self) -> None:
        if self._cancel is not None and self._cancel():
            raise ObserwatorCancelledError(message("common.cancelled"))

    def _wait_until(self, moment: datetime) -> None:
        """Sleep until ``moment`` in steps of at most `_TICK`, polling ``cancel``."""
        while True:
            self._check_cancel()
            left = (moment - self.clock.now()).total_seconds()
            if left <= 0:
                return
            self.clock.sleep(min(left, _TICK))

    def spacing(self, left: int | None) -> float:
        """
        The spacing of the next request after the one before, in seconds.

        Parameters
        ----------
        left : int or None
            The requests left to the deadline, the next one included; None for a
            request outside the spread (a station list): `MIN_SPACING`.

        Returns
        -------
        float
            The time left to the deadline divided by ``left + 1``, at least
            `MIN_SPACING`; `MIN_SPACING` without a deadline or a request before.
        """
        if left is None or self.deadline is None or self._last is None:
            return MIN_SPACING
        remaining = (self.deadline - self._last).total_seconds()
        return max(MIN_SPACING, remaining / (left + 1))

    def _ask(self, url: str, headers: Mapping[str, str]) -> tuple[httpx.Response, bool]:
        """
        One attempt: the GET, counted, its answer to the spool.

        Returns the answer and whether the spool kept it (always True for an
        address of no capture dataset). A request without an answer raises the
        `httpx.RequestError`, or `_Stopped` when it is the last one of
        `CONNECTION_FAILURES` in a row.
        """
        # The captures import this module, so they are reached at call time.
        from obserwator.captures import capture_dataset, keep_response

        assert self._client is not None, "PacedSession is used outside its with"
        self._check_cancel()
        self._last = self.clock.now()
        self.requests += 1
        try:
            response = self._client.get(url, headers=dict(headers))
        except httpx.RequestError as exc:
            self._failures += 1
            if self._failures >= CONNECTION_FAILURES:
                raise _Stopped(exc) from exc
            raise
        self._failures = 0
        self.answers += 1
        kept = (
            capture_dataset(str(response.url)) is None
            or keep_response(response) is not None
        )
        return response, kept

    def get(
        self,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        left: int | None = None,
    ) -> tuple[httpx.Response, bool, int]:
        """
        One request of the run: paced, asked again after 429 or 5xx.

        Parameters
        ----------
        url : str
            The address.
        headers : Mapping of str to str or None, optional
            Request headers besides gzip's.
        left : int or None, optional
            The requests left to the deadline, this one included (`spacing`).

        Returns
        -------
        tuple of (httpx.Response, bool, int)
            The last answer, whether the spool kept every answer of a capture
            source, and the attempts made.

        Raises
        ------
        httpx.RequestError
            If no answer came (a connection failure).
        ObserwatorCancelledError
            If ``cancel`` returned True.
        """
        if self._last is not None:
            self._wait_until(self._last + timedelta(seconds=self.spacing(left)))
        sent = dict(headers or {})
        response, kept = self._ask(url, sent)
        attempts = 1
        for pause in BACKOFF:
            if not _backs_off(response.status_code):
                break
            self._wait_until(self.clock.now() + timedelta(seconds=pause))
            response, again = self._ask(url, sent)
            kept, attempts = kept and again, attempts + 1
        return response, kept, attempts

    def fetch(
        self, url: str, *, headers: Mapping[str, str] | None = None
    ) -> httpx.Response:
        """
        One request that the run cannot do without (a station list): a success or an error.

        Paced at `MIN_SPACING` and asked again after 429 or 5xx as `get`.

        Parameters
        ----------
        url : str
            The address.
        headers : Mapping of str to str or None, optional
            Request headers besides gzip's.

        Returns
        -------
        httpx.Response
            An answer 2xx.

        Raises
        ------
        ObserwatorConnectionError
            If no answer came or the last answer was no success
            (``source_unavailable``).
        ObserwatorCancelledError
            If ``cancel`` returned True.
        """
        try:
            response, _, _ = self.get(url, headers=headers)
            response.raise_for_status()
        except _Stopped as exc:
            raise _source_error(exc.failure, url, source=self.source) from exc
        except httpx.HTTPError as exc:
            raise _source_error(exc, url, source=self.source) from exc
        return response

    def run(
        self,
        requests: Sequence[PacedRequest],
        *,
        on_progress: ProgressHook | None = None,
    ) -> list[PacedOutcome]:
        """
        Ask every request in order, spread to the deadline (see the class).

        A station refused after the backoff is skipped: its later requests are not
        asked and the spread is computed without them. After `CONNECTION_FAILURES`
        connection failures in a row the rest is ``stopped``; after a cancel,
        ``cancelled``.

        Parameters
        ----------
        requests : sequence of PacedRequest
            The requests, those of one station together.
        on_progress : ProgressHook or None, optional
            Called after each request (unit ``request``) with its status and a line
            naming its time, HTTP status and address.

        Returns
        -------
        list of PacedOutcome
            One per request, in order.
        """
        # store.types is imported lazily: the obserwator.store package imports this module.
        from obserwator.store.types import Progress

        positions: dict[str, list[int]] = {}
        for index, request in enumerate(requests):
            positions.setdefault(request.station, []).append(index)
        outcomes: list[PacedOutcome] = []
        skipped: dict[str, PacedOutcome] = {}
        left = len(requests)
        ended: Literal["stopped", "cancelled"] | None = None
        for index, request in enumerate(requests):
            if ended is not None:
                outcome = PacedOutcome(
                    request,
                    ended,
                    error=self._ended_text(ended),
                    error_code="cancelled" if ended == "cancelled" else _UNAVAILABLE,
                )
            elif request.station in skipped:
                before = skipped[request.station]
                outcome = PacedOutcome(
                    request,
                    "skipped",
                    before.http_status,
                    error=before.error,
                    error_code=_UNAVAILABLE,
                )
            else:
                outcome = self._one(request, left)
                left -= 1
                if outcome.status == "skipped":
                    skipped[request.station] = outcome
                    left -= sum(
                        1 for later in positions[request.station] if later > index
                    )
                elif outcome.status == "cancelled":
                    ended = "cancelled"
                elif outcome.status == "stopped":
                    ended, self.stopped = "stopped", True
                    # The third failure itself is a failed request.
                    outcome = replace(outcome, status="failed")
            outcomes.append(outcome)
            if on_progress is not None:
                on_progress(
                    Progress(
                        index + 1,
                        len(requests),
                        "request",
                        outcome.status,
                        message(
                            "fetch.paced_request",
                            time=_stamp(outcome.asked_at),
                            status=outcome.http_status or "—",
                            url=request.url,
                        ),
                    )
                )
        return outcomes

    def _ended_text(self, ended: Literal["stopped", "cancelled"]) -> str:
        if ended == "cancelled":
            return message("common.cancelled")
        return message("fetch.paced_run_stopped", failures=CONNECTION_FAILURES)

    def _one(self, request: PacedRequest, left: int) -> PacedOutcome:
        """Ask one planned request (see `run`)."""
        try:
            response, kept, attempts = self.get(
                request.url, headers=request.headers, left=left
            )
        except ObserwatorCancelledError:
            return PacedOutcome(
                request,
                "cancelled",
                error=message("common.cancelled"),
                error_code="cancelled",
            )
        except _Stopped as exc:
            error = _source_error(exc.failure, request.url, source=self.source)
            return PacedOutcome(
                request,
                "stopped",
                attempts=1,
                asked_at=self._last,
                error=error.detail,
                error_code=_UNAVAILABLE,
            )
        except httpx.RequestError as exc:
            error = _source_error(exc, request.url, source=self.source)
            return PacedOutcome(
                request,
                "failed",
                attempts=1,
                asked_at=self._last,
                error=error.detail,
                error_code=_UNAVAILABLE,
            )
        status = response.status_code
        if _backs_off(status):
            text = message(
                "fetch.paced_station_skipped",
                station=request.station,
                status=status,
                url=request.url,
                attempts=attempts,
            )
            return PacedOutcome(
                request, "skipped", status, attempts, self._last, text, _UNAVAILABLE
            )
        if not kept:
            text = message("fetch.paced_not_kept", url=request.url)
            return PacedOutcome(
                request, "failed", status, attempts, self._last, text, "io_error"
            )
        if response.is_success or status in _NOT_PUBLISHED:
            return PacedOutcome(request, "answered", status, attempts, self._last)
        text = message(
            "fetch.server_returned_http",
            source=self.source,
            status=status,
            url=request.url,
        )
        return PacedOutcome(
            request, "failed", status, attempts, self._last, text, _UNAVAILABLE
        )


def _stamp(moment: datetime | None) -> str:
    """An instant of a paced run in its progress lines: UTC to the second, ``Z``."""
    if moment is None:
        return "—"
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
