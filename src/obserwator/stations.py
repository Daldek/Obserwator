"""
Station search and current states of hydrological stations.

`find_stations` searches the station lists of the data providers (IMGW-PIB
and ČHMÚ), live or from a versioned store; `fetch_hydro_states` reads the
locations and current water states of hydrological stations from the
hydro.imgw.pl map API, whose station pages also give the station details
``store sync`` keeps for the catalog (``pl.imgw.hydro_details``, ADR-021).
"""

from __future__ import annotations

import json
import math
import unicodedata
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any, Literal

import httpx
from pydantic import ValidationError

from obserwator._parsing.chmi import iter_stations, parse_listing
from obserwator._parsing.stations import parse_stations_csv
from obserwator._version import __version__
from obserwator.datasets import (
    _CHMI_METEO_NOW_FILE,
    ProviderDescriptor,
    _station_files,
    get_dataset,
    get_provider,
    providers,
    station_source_files,
)
from obserwator.exceptions import (
    ObserwatorCancelledError,
    ObserwatorDataError,
    ObserwatorStoreError,
    ObserwatorValidationError,
)
from obserwator.fetch import (
    _IDENTIFY,
    DEFAULT_TIMEOUT,
    DownloadResult,
    _get,
    _get_async,
    _json_payload,
    _source_error,
)
from obserwator.messages import message
from obserwator.models import HydroState, StationListEntry

if TYPE_CHECKING:
    from obserwator.store.catalog import RootArg
    from obserwator.store.types import StationFeature

HYDRO_MAP_API_URL = "https://hydro-back.imgw.pl/map/stations/hydrologic"
_MAP_HEADERS = {
    "User-Agent": f"Obserwator/{__version__}",
    "Referer": "https://hydro.imgw.pl/",
}
_KINDS: tuple[Literal["hydro", "meteo"], ...] = ("hydro", "meteo")
_SOURCES = ("live", "store")
# The newest dated file of a listed directory, as plans name it.
_NEWEST = "meta1-<YYYYMMDD>.json"
# IMGW-PIB current-data API answer of each family whose ``lon``/``lat`` locate the
# rows of the live list (the first location source of the catalog too), and the
# key of the station code in it.
_IMGW_LOCATIONS: Mapping[str, tuple[str, str]] = {
    "hydro": ("pl.imgw.hydro_now", "id_stacji"),
    "meteo": ("pl.imgw.meteo_now", "kod_stacji"),
}
# Area of a search: west, south, east, north (WGS84 degrees, bounds included).
Area = tuple[float, float, float, float]

# Polish ``ł`` has no decomposition, so ``_normalize`` maps it by hand.
_L_STROKE = unicodedata.lookup("LATIN SMALL LETTER L WITH STROKE")

# ============================================================================
# Station search
# ============================================================================


def _normalize(text: str) -> str:
    """
    Casefolded text without diacritics (``"ŁÓDŹ"`` -> ``"lodz"``).

    Polish ``ł`` becomes ``l`` (it has no decomposition); Czech letters
    decompose, so ``"Špindlerův"`` becomes ``"spindleruv"``.
    """
    folded = unicodedata.normalize("NFKD", text.casefold().replace(_L_STROKE, "l"))
    return "".join(char for char in folded if not unicodedata.combining(char))


def _area(bbox: Sequence[float] | None) -> Area | None:
    """
    Validate the bounding box of a search; return it as ``(w, s, e, n)``.

    Four finite WGS84 degrees in order west, south, east, north: longitudes
    within ±180, latitudes within ±90, west not east of east and south not
    north of north.
    """
    if bbox is None:
        return None
    values = (
        list(bbox) if isinstance(bbox, Sequence) and not isinstance(bbox, str) else []
    )
    shown = ",".join(map(str, values)) if values else repr(bbox)
    if len(values) != 4 or not all(
        isinstance(value, int | float)
        and not isinstance(value, bool)
        and math.isfinite(value)
        for value in values
    ):
        raise ObserwatorValidationError(
            message("stations.bbox_needs_four_numbers", bbox=shown),
            details={"option": "bbox", "value": shown},
        )
    west, south, east, north = (float(value) for value in values)
    if not (
        -180.0 <= west <= 180.0
        and -180.0 <= east <= 180.0
        and -90.0 <= south <= 90.0
        and -90.0 <= north <= 90.0
    ):
        raise ObserwatorValidationError(
            message("stations.bbox_out_of_range", bbox=shown),
            details={"option": "bbox", "value": shown},
        )
    if west > east or south > north:
        raise ObserwatorValidationError(
            message("stations.bbox_inverted", bbox=shown),
            details={"option": "bbox", "value": shown},
        )
    return west, south, east, north


def _search_options(
    kind: str | None,
    query: str | None,
    source: str,
    root: object,
    bbox: Sequence[float] | None = None,
) -> tuple[tuple[Literal["hydro", "meteo"], ...], str | None, Area | None]:
    """Validate the search options; return the families, stripped query and area."""
    if kind is not None and kind not in _KINDS:
        raise ObserwatorValidationError(
            message("stations.unknown_kind_station_allowed_hydro", kind=kind),
            details={"option": "kind", "allowed": list(_KINDS)},
        )
    if source not in _SOURCES:
        raise ObserwatorValidationError(
            message("stations.unknown_source_station_list_allowed", source=source),
            details={"option": "source", "allowed": list(_SOURCES)},
        )
    if source == "store" and root is None:
        raise ObserwatorValidationError(
            message("stations.search_store_source_store_needs"),
            details={"option": "root"},
        )
    if source == "live" and root is not None:
        raise ObserwatorValidationError(
            message("stations.store_directory_root_allowed_only"),
            details={"option": "root"},
        )
    needle = None
    if query is not None:
        needle = query.strip()
        if not needle:
            raise ObserwatorValidationError(
                message("stations.station_search_phrase_must_not"),
                details={"option": "query"},
            )
    kinds = _KINDS if kind is None else (kind,)
    return kinds, needle, _area(bbox)


def _owners(provider: str | None) -> tuple[ProviderDescriptor, ...]:
    """Providers of a search: every provider for None, else the named one."""
    return providers() if provider is None else (get_provider(provider),)


def _inside(entry: StationListEntry, area: Area) -> bool:
    """Whether a station lies in ``area`` (bounds included); never without coordinates."""
    if entry.latitude is None or entry.longitude is None:
        return False
    west, south, east, north = area
    return west <= entry.longitude <= east and south <= entry.latitude <= north


def _matching(
    entries: Iterable[StationListEntry], query: str | None, area: Area | None
) -> tuple[StationListEntry, ...]:
    """Stations matching ``query`` (normalized name, river, code) and ``area``, ordered."""
    rows = list(entries)
    if query is not None:
        needle = _normalize(query)
        rows = [
            entry
            for entry in rows
            if needle in _normalize(entry.name)
            or (entry.river is not None and needle in _normalize(entry.river))
            or entry.station_code.startswith(query)
        ]
    if area is not None:
        rows = [entry for entry in rows if _inside(entry, area)]
    rank = {owner.id: index for index, owner in enumerate(providers())}
    order = {family: index for index, family in enumerate(_KINDS)}
    return tuple(
        sorted(
            rows,
            key=lambda entry: (
                rank[entry.provider],
                order[entry.kind],
                _normalize(entry.name),
                entry.station_code,
            ),
        )
    )


@dataclass(frozen=True)
class _LiveSource:
    """
    Live station list of one provider and family.

    ``listing`` marks the URL of a directory listing whose newest
    ``meta1-<YYYYMMDD>.json`` is the list (ČHMÚ meteo ``now`` metadata);
    ``locations`` is the URL of the IMGW-PIB current-data API answer of the
    family, read after the list for the coordinates of its stations.
    """

    provider: ProviderDescriptor
    kind: Literal["hydro", "meteo"]
    url: str
    listing: bool = False
    locations: str | None = None


def _live_sources(
    kinds: Sequence[Literal["hydro", "meteo"]],
    owners: Iterable[ProviderDescriptor],
) -> list[_LiveSource]:
    """Live station list of each provider and family, in search order."""
    # The current ČHMÚ metadata, as the first source of its catalog (§7.2).
    sources: list[_LiveSource] = []
    for owner in owners:
        if owner.id == "CHMI":
            hydro = _LiveSource(
                owner, "hydro", _station_files("cz.chmi.hydro_now")[0].url
            )
            meteo_now = get_dataset("cz.chmi.meteo_now")
            meteo = _LiveSource(
                owner, "meteo", f"{owner.base_url}{meteo_now.server_dir}/", listing=True
            )
        else:
            hydro_list, meteo_list = station_source_files(provider=owner.id)
            hydro = _LiveSource(
                owner, "hydro", hydro_list.url, locations=_locations_url("hydro")
            )
            meteo = _LiveSource(
                owner, "meteo", meteo_list.url, locations=_locations_url("meteo")
            )
        sources.extend(hydro if family == "hydro" else meteo for family in kinds)
    return sources


def _locations_url(kind: Literal["hydro", "meteo"]) -> str:
    """URL of the IMGW-PIB current-data API answer of a family."""
    return _station_files(_IMGW_LOCATIONS[kind][0])[0].url


def _live_urls(
    kinds: Sequence[Literal["hydro", "meteo"]],
    owners: Iterable[ProviderDescriptor],
) -> list[str]:
    """URLs a live search reads, the newest file of a listing as a pattern (plans)."""
    urls: list[str] = []
    for source in _live_sources(kinds, owners):
        urls.append(source.url)
        if source.listing:
            urls.append(source.url + _NEWEST)
        if source.locations is not None:
            urls.append(source.locations)
    return urls


def _identity(source: _LiveSource) -> tuple[Mapping[str, str] | None, str]:
    """Request headers and the server name of errors (ČHMÚ requests name the library)."""
    if source.provider.id == "CHMI":
        return _IDENTIFY, source.provider.short_name
    return None, "IMGW"


def _newest(source: _LiveSource, content: bytes) -> str:
    """URL of the newest ``meta1-<YYYYMMDD>.json`` in the listing of ``source``."""
    names = sorted(
        entry.name
        for entry in parse_listing(content, url=source.url)
        if _CHMI_METEO_NOW_FILE.fullmatch(entry.name)
    )
    if not names:
        raise ObserwatorDataError(
            message(
                "stations.unreadable_listing_no_file", url=source.url, newest=_NEWEST
            ),
            details={"url": source.url},
        )
    return source.url + names[-1]


def _parsed(source: _LiveSource, content: bytes, url: str) -> list[StationListEntry]:
    """Stations of a live list: an IMGW-PIB CSV or ČHMÚ metadata JSON."""
    if source.provider.id == "CHMI":
        return list(iter_stations(content, kind=source.kind, filename=url))
    return list(parse_stations_csv(content, kind=source.kind))


def _degrees(value: object) -> float | None:
    """A published coordinate (number or numeric text) as a finite float, else None."""
    if isinstance(value, bool) or not isinstance(value, int | float | str):
        return None
    try:
        number = float(value)
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def _located(
    entries: list[StationListEntry], source: _LiveSource, response: httpx.Response
) -> list[StationListEntry]:
    """
    The rows of an IMGW-PIB live list with the coordinates of the current-data API.

    Each row whose code the API answer lists with a numeric ``lat`` and ``lon``
    gets them as published (no border check); other rows keep None.
    """
    url = str(response.url)
    payload = _json_payload(response)
    if not isinstance(payload, list):
        raise ObserwatorDataError(
            message("stations.unexpected_response_from_list_stations", url=url),
            details={"url": url},
        )
    code_key = _IMGW_LOCATIONS[source.kind][1]
    points: dict[str, tuple[float, float]] = {}
    for row in payload:
        if not isinstance(row, dict):
            continue
        code = str(row.get(code_key) or "").strip()
        latitude, longitude = _degrees(row.get("lat")), _degrees(row.get("lon"))
        if code and latitude is not None and longitude is not None:
            points.setdefault(code, (latitude, longitude))
    return [
        replace(entry, latitude=point[0], longitude=point[1])
        if (point := points.get(entry.station_code)) is not None
        else entry
        for entry in entries
    ]


def _read_live(source: _LiveSource, timeout: float) -> list[StationListEntry]:
    """
    Stations of one live list.

    One GET; a listed directory adds its listing, an IMGW-PIB list the
    current-data API answer of its coordinates.
    """
    headers, name = _identity(source)
    url = source.url
    if source.listing:
        listing = _get(url, timeout=timeout, headers=headers, source=name)
        url = _newest(source, listing.content)
    response = _get(url, timeout=timeout, headers=headers, source=name)
    entries = _parsed(source, response.content, url)
    if source.locations is None:
        return entries
    answer = _get(source.locations, timeout=timeout, headers=headers, source=name)
    return _located(entries, source, answer)


async def _read_live_async(
    source: _LiveSource, timeout: float
) -> list[StationListEntry]:
    """Async twin of `_read_live`."""
    headers, name = _identity(source)
    url = source.url
    if source.listing:
        listing = await _get_async(url, timeout=timeout, headers=headers, source=name)
        url = _newest(source, listing.content)
    response = await _get_async(url, timeout=timeout, headers=headers, source=name)
    entries = _parsed(source, response.content, url)
    if source.locations is None:
        return entries
    answer = await _get_async(
        source.locations, timeout=timeout, headers=headers, source=name
    )
    return _located(entries, source, answer)


def _text(value: object) -> str | None:
    """A catalog property that is a non-empty text, else None."""
    return value if isinstance(value, str) and value else None


def _catalog_entry(feature: StationFeature) -> StationListEntry | None:
    """The search entry of a catalog station; None for a station of no family."""
    properties = feature.properties
    kind = properties.get("kind")
    if kind not in _KINDS:
        return None
    order = properties.get("river_order")
    return StationListEntry(
        kind=kind,
        station_code=feature.station_code,
        name=_text(properties.get("name")) or "",
        river=_text(properties.get("river")),
        hydrographic_code=_text(properties.get("hydrographic_code")),
        river_order=order
        if isinstance(order, int) and not isinstance(order, bool)
        else None,
        latitude=None if feature.geometry is None else feature.geometry[1],
        longitude=None if feature.geometry is None else feature.geometry[0],
        provider=feature.provider,
    )


def _stored(
    root: RootArg,
    kinds: Sequence[Literal["hydro", "meteo"]],
    owners: Sequence[ProviderDescriptor],
    *,
    explicit: bool,
) -> list[StationListEntry]:
    """
    Stations of the current station catalogs of the providers in a data root (ADR-017).

    A provider without a catalog is skipped unless it was named (``explicit``:
    ``not_found`` of `read_catalog`); a data root without the catalog of any
    searched provider is ``not_found`` with the ``store catalog`` hint.
    """
    from obserwator.store import read_catalog

    found: list[StationListEntry] = []
    read = False
    for owner in owners:
        try:
            features = read_catalog(root=root, provider=owner.id)
        except ObserwatorStoreError as exc:
            if exc.code != "not_found" or explicit:
                raise
            continue
        read = True
        for feature in features:
            entry = _catalog_entry(feature)
            if entry is not None and entry.kind in kinds:
                found.append(entry)
    if not read:
        raise ObserwatorStoreError(
            message(
                "stations.no_station_catalog",
                providers=", ".join(owner.short_name for owner in owners),
            ),
            code="not_found",
            details={"option": "root"},
            hint=message("errors.hint_store_catalog", provider=owners[0].id),
        )
    return found


def find_stations(
    *,
    kind: Literal["hydro", "meteo"] | None = None,
    query: str | None = None,
    source: Literal["live", "store"] = "live",
    root: RootArg | None = None,
    provider: str | None = None,
    bbox: Sequence[float] | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> tuple[StationListEntry, ...]:
    """
    Find stations of IMGW-PIB and ČHMÚ by name, river, code prefix or area.

    Parameters
    ----------
    kind : {"hydro", "meteo"} or None, optional
        Station family; None searches both lists.
    query : str or None, optional
        Text matched case- and diacritic-insensitively (``"lodz"`` finds
        ``"ŁÓDŹ"``, ``"spindleruv"`` finds ``"Špindlerův Mlýn"``) as a
        fragment of the station name or river, or as a prefix of the
        station code. None returns every station.
    source : {"live", "store"}, optional
        ``"live"`` downloads the current lists of each provider: the
        IMGW-PIB station list CSV of each family and its current-data API
        answer (``api/data/hydro``, ``api/data/meteo``: two GETs per family)
        and the ČHMÚ metadata ``hydrology/now/metadata/meta1.json`` and the
        newest ``meteorology/climate/now/metadata/meta1-<YYYYMMDD>.json``
        (its directory listing, then the file). ``"store"`` reads the
        current station catalogs of a data root offline (ADR-017), which
        ``store catalog`` builds from the stored lists.
    root : str, os.PathLike or StoreHandle, optional
        Data root; required with ``source="store"`` and not allowed with
        ``source="live"``.
    provider : str or None, optional
        Provider identifier or key prefix (``"IMGW-PIB"``, ``"CHMI"``,
        ``"cz.chmi"``); None searches every provider and, with
        ``source="store"``, skips providers without a station catalog.
    bbox : sequence of four floats or None, optional
        Area of the search: ``(west, south, east, north)`` in WGS84 degrees,
        bounds included; only stations with coordinates inside it are
        returned, so a station without coordinates is left out. None
        searches everywhere.
    timeout : float, optional
        Request timeout in seconds (live source).

    Returns
    -------
    tuple of StationListEntry
        Matching stations ordered by provider (registry order), family
        (hydro, meteo), normalized name and code, each with its
        ``provider``; a code listed twice on the live IMGW-PIB meteo list is
        returned for each row. Live entries carry the coordinates as their
        provider publishes them, without validation against the country
        border: ČHMÚ those of the metadata, IMGW-PIB the ``lat``/``lon`` of
        the current-data API answer of the family; a station of the IMGW-PIB
        list the API does not report (closed or not reporting now) has None.
        The hydrographic code is the one of the list as published (IMGW-PIB:
        a short number in parentheses, e.g. ``"14"`` for the Barycz).
        With ``source="store"`` every station of a catalog is one entry with
        its code, family, name, river, hydrographic code and river order, the
        coordinates of its geometry (None for stations with ``geometry:
        null``, validated by ``store catalog``) and ``short_code`` None.

    Raises
    ------
    ObserwatorValidationError
        If ``kind``, ``source`` or ``provider`` is unknown, ``query`` is
        blank, ``root`` is missing with ``source="store"`` or given with
        ``source="live"``, or ``bbox`` is not four finite numbers with
        longitudes within ±180, latitudes within ±90, west ≤ east and
        south ≤ north (``details.option`` ``"bbox"``).
    ObserwatorConnectionError
        If a provider's server cannot be reached or answers with an HTTP
        error (``details`` ``url``, ``reason`` and, for HTTP errors,
        ``status``).
    ObserwatorStoreError
        If the root is not a supported data root (code
        ``store_unavailable``; ``details.reason`` ``wrong_root`` for a raw
        root), holds no station catalog of any searched provider, or lacks
        the catalog of a named ``provider`` (code ``not_found``, with the
        ``store catalog`` hint).
    ObserwatorDataError
        If a live list, listing or current-data API answer, or a stored list
        or catalog, is malformed or does not match its sidecar.

    Examples
    --------
    >>> [s.name for s in find_stations(kind="hydro", query="lodz")]
    >>> find_stations(provider="CHMI", query="spindleruv")
    >>> find_stations(query="1491", source="store", root="data/store")
    >>> find_stations(kind="hydro", bbox=(16.5, 51.3, 17.9, 51.7))  # Barycz
    """
    kinds, needle, area = _search_options(kind, query, source, root, bbox)
    owners = _owners(provider)
    if root is not None:  # validated: root is given exactly with source="store"
        stored = _stored(root, kinds, owners, explicit=provider is not None)
        return _matching(stored, needle, area)
    entries = [
        entry
        for live in _live_sources(kinds, owners)
        for entry in _read_live(live, timeout)
    ]
    return _matching(entries, needle, area)


async def find_stations_async(
    *,
    kind: Literal["hydro", "meteo"] | None = None,
    query: str | None = None,
    source: Literal["live", "store"] = "live",
    root: RootArg | None = None,
    provider: str | None = None,
    bbox: Sequence[float] | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> tuple[StationListEntry, ...]:
    """
    Async version of `find_stations`, with identical arguments and result.

    See `find_stations` for full documentation.
    """
    kinds, needle, area = _search_options(kind, query, source, root, bbox)
    owners = _owners(provider)
    if root is not None:  # validated: root is given exactly with source="store"
        stored = _stored(root, kinds, owners, explicit=provider is not None)
        return _matching(stored, needle, area)
    entries: list[StationListEntry] = []
    for live in _live_sources(kinds, owners):
        entries.extend(await _read_live_async(live, timeout))
    return _matching(entries, needle, area)


# ============================================================================
# Hydrological station states (hydro.imgw.pl map)
# ============================================================================


def _map_url(main_only: bool) -> str:
    return f"{HYDRO_MAP_API_URL}?onlyMainStations={'true' if main_only else 'false'}"


def _hydro_states(payload: Any, url: str) -> list[HydroState]:
    """
    Parse the map API answer; stations without a code or with invalid values are skipped.

    The API uses short keys: ``id`` code, ``n`` name, ``la``/``lo``
    coordinates, ``s`` water state; ``rzeka`` is the river name.
    """
    items = payload.get("stations", []) if isinstance(payload, dict) else payload
    if not isinstance(items, list):
        raise ObserwatorDataError(
            message("stations.unexpected_response_from_list_stations", url=url)
        )
    states: list[HydroState] = []
    for item in items:
        if not isinstance(item, dict) or not item.get("id"):
            continue
        try:
            states.append(
                HydroState(
                    station_code=str(item["id"]),
                    name=item.get("n", item.get("name", "")),
                    river=item.get("rzeka"),
                    latitude=item.get("la", item.get("lat")),
                    longitude=item.get("lo", item.get("lon")),
                    water_state=item.get("s", item.get("waterStateStatus")),
                )
            )
        except ValidationError:
            continue
    return states


def fetch_hydro_states(
    *,
    main_only: bool = False,
    timeout: float = DEFAULT_TIMEOUT,
) -> list[HydroState]:
    """
    Fetch locations and current water states of hydrological stations.

    Reads the map API of https://hydro.imgw.pl (``hydro-back.imgw.pl``),
    which requires the ``Referer`` and ``User-Agent`` headers sent here.

    Parameters
    ----------
    main_only : bool, optional
        If True, only main stations; by default all stations.
    timeout : float, optional
        Request timeout in seconds.

    Returns
    -------
    list of HydroState
        Stations in API order; a station without a code or with invalid
        values is skipped, missing coordinates or state are None.

    Raises
    ------
    ObserwatorConnectionError
        If the server cannot be reached or answers with an HTTP error
        (``details`` ``url``, ``reason`` and, for HTTP errors, ``status``).
    ObserwatorDataError
        If the response is not JSON or holds no station list.

    Examples
    --------
    >>> alarmed = [s for s in fetch_hydro_states() if s.water_state == "alarm"]
    """
    url = _map_url(main_only)
    response = _get(url, timeout=timeout, headers=_MAP_HEADERS)
    return _hydro_states(_json_payload(response), url)


async def fetch_hydro_states_async(
    *,
    main_only: bool = False,
    timeout: float = DEFAULT_TIMEOUT,
) -> list[HydroState]:
    """
    Async version of `fetch_hydro_states`, with identical arguments and result.

    See `fetch_hydro_states` for full documentation.
    """
    url = _map_url(main_only)
    response = await _get_async(url, timeout=timeout, headers=_MAP_HEADERS)
    return _hydro_states(_json_payload(response), url)


def _hydro_details(
    client: httpx.Client, url: str, *, cancel: Callable[[], bool] | None = None
) -> DownloadResult:
    """
    hydro.imgw.pl's details of every station of its map, gathered into one JSON list.

    The map (``onlyMainStations=false``) names the stations; then ``url``, the
    endpoint of a station page (``station/hydro/status``), is asked once per
    station (``?id=<code>``), in map order, one request at a time and with the
    headers hydro-back.imgw.pl requires. An answer that is no object (``null``
    for a code the backend does not know) is left out. The list holds the
    whole answers: `write_archive` keeps only the fields of
    ``pl.imgw.hydro_details`` (ADR-015 D5, ADR-021).

    Parameters
    ----------
    client : httpx.Client
        Client of the requests.
    url : str
        The endpoint of the station pages, the URL of the dataset's file.
    cancel : callable or None, optional
        Polled before each request; once it returns True the download stops.

    Returns
    -------
    DownloadResult
        The JSON list with ``url`` and without HTTP signals (one file of many
        answers has none).

    Raises
    ------
    ObserwatorConnectionError
        If any request fails (``source_unavailable``, ``details`` ``url`` of
        that request); nothing is returned of the other answers.
    ObserwatorDataError
        If the map or an answer is no JSON, or the map holds no station list.
    ObserwatorCancelledError
        If ``cancel`` returns True.
    """
    asked = _map_url(False)
    answers: list[Any] = []
    try:
        response = client.get(asked, headers=_MAP_HEADERS)
        response.raise_for_status()
        for state in _hydro_states(_json_payload(response), asked):
            if cancel is not None and cancel():
                raise ObserwatorCancelledError(message("stations.details_cancelled"))
            asked = f"{url}?id={state.station_code}"
            response = client.get(asked, headers=_MAP_HEADERS)
            response.raise_for_status()
            answer = _json_payload(response)
            if isinstance(answer, dict):
                answers.append(answer)
    except httpx.HTTPError as exc:
        raise _source_error(exc, asked) from exc
    data = json.dumps(answers, ensure_ascii=False).encode("utf-8")
    return DownloadResult(
        data=data, url=url, etag=None, last_modified=None, content_length=None
    )
