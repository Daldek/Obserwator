"""
The section ``[obserwator.instance]`` of ``nogat.toml``: what one deployment serves (ADR-025).

One table describes an instance of the servers (I1, I2): the state of each provider
(``visible``, ``hidden`` or ``off``), the provider it features, its area (one GeoJSON
Polygon or MultiPolygon in WGS84, ``focus`` or ``clip``), its start view, PMAXTP (``on``
or ``off``) and the operator's title, logo and regulamin. `load_instance` reads and
checks the table once, when a server starts (I7): an unknown field or provider, a
featured provider that is ``off``, an area file that is missing, too large, no polygon
or outside the WGS84 range, a logo that is no PNG, WebP or SVG, a regulamin without its
title, any wrong value is ``validation_error`` naming the field in ``details.option``
(``instance.<field>``), so a server starts only from a valid description. Without the
table there is no instance: the servers serve everything, as before.

`Instance` is the one filter of both servers (I3). `Instance.keeps` says whether a
station of a catalog is served: its provider is not ``off`` and, with ``area_mode =
"clip"``, its location lies inside the area (a station without one does not). The GUI
reduces each read of the data root with `Instance.reduce` (``obserwator.gui._root``), so
its station layer, the layer's ETag and every station route agree; the REST server
(``obserwator.api``) applies the same predicate to its routes. The CLI and the MCP
server, local tools, never apply it. The table holds paths and words only, never a
credential (DEV-18.4); relative paths are relative to the directory of ``nogat.toml``.
"""

from __future__ import annotations

import hashlib
import itertools
import json
import math
import re
import threading
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, TypeVar, cast
from xml.etree import ElementTree

from obserwator import _environment as environment
from obserwator.datasets import _CATALOG_DATASETS, get_dataset, providers
from obserwator.exceptions import ObserwatorValidationError
from obserwator.messages import message, reason

if TYPE_CHECKING:
    from obserwator.store.types import StationFeature

__all__ = [
    "AREA_MAX_BYTES",
    "AREA_MAX_VERTICES",
    "FIELDS",
    "LOGO_MAX_BYTES",
    "TERMS_MAX_BYTES",
    "Area",
    "Instance",
    "Logo",
    "Terms",
    "instance_report",
    "load_instance",
    "parse_instance",
]

ProviderState = Literal["visible", "hidden", "off"]
StartView = Literal["all", "featured", "area"]
AreaMode = Literal["focus", "clip"]
Box = tuple[float, float, float, float]
"""West, south, east, north in degrees."""

SECTION = "instance"
"""The table of ``[obserwator]`` that describes the instance."""
FIELDS: tuple[str, ...] = (
    "title",
    "logo",
    "featured_provider",
    "start_view",
    "area",
    "area_mode",
    "pmaxtp",
    "terms",
    "providers",
)
"""The fields of ``[obserwator.instance]`` (I1)."""
PROVIDER_STATES: tuple[ProviderState, ...] = ("visible", "hidden", "off")
START_VIEWS: tuple[StartView, ...] = ("all", "featured", "area")
AREA_MODES: tuple[AreaMode, ...] = ("focus", "clip")
PMAXTP_STATES: tuple[str, ...] = ("on", "off")
TITLE_MAX = 80
"""The longest title [characters]."""
AREA_MAX_BYTES = 1_000_000
"""The largest area file [bytes] (I4)."""
AREA_MAX_VERTICES = 100_000
"""The most positions of the area's rings (I4)."""
LOGO_MAX_BYTES = 200_000
"""The largest logo [bytes] (I14)."""
TERMS_MAX_BYTES = 200_000
"""The largest regulamin [bytes] (I15)."""
START_MARGIN = 0.05
"""The margin of the featured provider's box: this share of its size on each side (I5)."""
START_MARGIN_MIN = 0.02
"""The least margin of that box [degrees]: one station still gets a box."""
BOUNDS_MARGIN = 0.25
"""The margin of the map's bounds around the area in ``clip``: this share of its size."""
BOUNDS_MARGIN_MIN = 0.5
"""The least margin of the map's bounds [degrees]."""
MERCATOR_LATITUDE = 85.0
"""The highest latitude of the map's bounds (the web map's projection ends near it)."""

_PNG = b"\x89PNG\r\n\x1a\n"
_SVG_ROOT = "{http://www.w3.org/2000/svg}svg"
_SVG_FORBIDDEN = re.compile(rb"<!(?:DOCTYPE|ENTITY)", re.IGNORECASE)
_WGS84 = frozenset(
    {
        "urn:ogc:def:crs:OGC:1.3:CRS84",
        "urn:ogc:def:crs:OGC::CRS84",
        "urn:ogc:def:crs:EPSG::4326",
        "EPSG:4326",
    }
)
"""The names of WGS84 longitude and latitude in a ``crs`` member of an older GeoJSON."""
_LINK = re.compile(r"\[[^\]]+\]\((?P<href>[^)\s]+)\)")
"""A link of the regulamin's Markdown subset (Nogat ``scripts/terms.py``)."""
_SAFE_HREF = re.compile(
    r"(?:https?://|mailto:|#|\{\{[a-z][a-z0-9_]*\}\})", re.IGNORECASE
)
_STRIPES = 512
"""The most horizontal stripes of a polygon's edge index."""

_C = TypeVar("_C")
_S = TypeVar("_S")


def _invalid(name: str, text: str, /, **details: object) -> ObserwatorValidationError:
    """``validation_error`` of the field ``name`` (``details.option``: ``instance.<name>``)."""
    return ObserwatorValidationError(
        text, details={"option": f"{SECTION}.{name}", **details}
    )


# --- the area -----------------------------------------------------------------------


class _Polygon:
    """
    One polygon's rings with an index of their edges by horizontal stripes.

    A point is inside when a ray from it crosses the edges of the polygon's rings an
    odd number of times (holes included); only the edges of the stripe holding the
    point's latitude are tested, so a station costs a few dozen comparisons even
    against a border of 100,000 vertices.
    """

    __slots__ = ("_bottom", "_height", "_stripes", "box")

    def __init__(self, rings: Sequence[Sequence[tuple[float, float]]]) -> None:
        outer = rings[0]
        longitudes = [x for x, _ in outer]
        latitudes = [y for _, y in outer]
        self.box: Box = (
            min(longitudes),
            min(latitudes),
            max(longitudes),
            max(latitudes),
        )
        edges = [
            (x1, y1, x2, y2)
            for ring in rings
            for (x1, y1), (x2, y2) in itertools.pairwise(ring)
            if y1 != y2
        ]
        count = max(1, min(_STRIPES, len(edges) // 4))
        bottom, top = self.box[1], self.box[3]
        self._bottom = bottom
        self._height = (top - bottom) / count if top > bottom else 1.0
        stripes: list[list[tuple[float, float, float, float]]] = [
            [] for _ in range(count)
        ]
        for edge in edges:
            low, high = sorted((edge[1], edge[3]))
            for index in range(self._stripe(low, count), self._stripe(high, count) + 1):
                stripes[index].append(edge)
        self._stripes = tuple(tuple(stripe) for stripe in stripes)

    def _stripe(self, latitude: float, count: int) -> int:
        return min(count - 1, max(0, int((latitude - self._bottom) / self._height)))

    def contains(self, lon: float, lat: float) -> bool:
        """Whether the point lies inside (a point of the boundary may go either way)."""
        west, south, east, north = self.box
        if not (west <= lon <= east and south <= lat <= north):
            return False
        inside = False
        for x1, y1, x2, y2 in self._stripes[self._stripe(lat, len(self._stripes))]:
            if (y1 > lat) != (y2 > lat) and lon < (x2 - x1) * (lat - y1) / (
                y2 - y1
            ) + x1:
                inside = not inside
        return inside


@dataclass(frozen=True)
class Area:
    """
    The area of an instance: one Polygon or MultiPolygon in WGS84 (I4).

    Attributes
    ----------
    path : Path
        The GeoJSON file it was read from.
    mode : {"focus", "clip"}
        ``focus``: nothing is removed, the map draws the outline and may start on it;
        ``clip``: the stations outside are not served and the map keeps to `bounds`.
    geometry : Mapping
        The polygon as GeoJSON (``type``, ``coordinates`` of ``[lon, lat]``), what the
        GUI draws.
    box : tuple of float
        Its bounding box: west, south, east, north.
    vertices : int
        The positions of its rings.
    sha256 : str
        SHA-256 of the file.
    """

    path: Path
    mode: AreaMode
    geometry: Mapping[str, Any] = field(repr=False)
    box: Box
    vertices: int
    sha256: str
    _polygons: tuple[_Polygon, ...] = field(repr=False, compare=False)

    @property
    def clips(self) -> bool:
        """Whether stations outside the area are not served (``clip``)."""
        return self.mode == "clip"

    def contains(self, lon: float, lat: float) -> bool:
        """Whether a point (degrees) lies inside one of the area's polygons."""
        return any(polygon.contains(lon, lat) for polygon in self._polygons)

    @property
    def bounds(self) -> Box:
        """The map's bounds in ``clip``: the box with a margin (I4)."""
        return _grown(self.box, BOUNDS_MARGIN, BOUNDS_MARGIN_MIN)


def _grown(box: Box, share: float, least: float) -> Box:
    """A box grown on each side by ``share`` of its size, at least ``least`` degrees."""
    west, south, east, north = box
    dx = max((east - west) * share, least)
    dy = max((north - south) * share, least)
    return (
        max(-180.0, west - dx),
        max(-MERCATOR_LATITUDE, south - dy),
        min(180.0, east + dx),
        min(MERCATOR_LATITUDE, north + dy),
    )


def _found(document: object) -> str:
    """What a GeoJSON document holds instead of a polygon, for the message."""
    if not isinstance(document, dict):
        return type(document).__name__
    kind = document.get("type")
    if kind == "FeatureCollection" and isinstance(document.get("features"), list):
        return f"FeatureCollection ({len(document['features'])})"
    return str(kind) if isinstance(kind, str) else "?"


def _check_crs(document: Mapping[str, Any], path: Path) -> None:
    """Refuse a ``crs`` member (GeoJSON 2008) naming anything but WGS84."""
    crs = document.get("crs")
    if crs is None:
        return
    name = crs.get("properties", {}).get("name") if isinstance(crs, dict) else None
    if name not in _WGS84:
        raise _invalid(
            "area",
            message("instance.area_crs", path=path, crs=json.dumps(crs)[:200]),
            path=str(path),
        )


def _geometry(document: object, path: Path) -> Mapping[str, Any]:
    """The one Polygon or MultiPolygon of a geometry, a Feature or a collection of one."""
    found = _found(document)
    current = document
    if isinstance(current, dict) and current.get("type") == "FeatureCollection":
        _check_crs(current, path)
        features = current.get("features")
        current = (
            features[0] if isinstance(features, list) and len(features) == 1 else None
        )
    if isinstance(current, dict) and current.get("type") == "Feature":
        _check_crs(current, path)
        current = current.get("geometry")
        found = _found(current) if current is not None else found
    if not isinstance(current, dict) or current.get("type") not in (
        "Polygon",
        "MultiPolygon",
    ):
        raise _invalid(
            "area",
            message("instance.area_not_polygon", path=path, found=found),
            path=str(path),
        )
    _check_crs(current, path)
    return current


def _position(value: object, path: Path) -> tuple[float, float]:
    """``[lon, lat]`` (an altitude after them is dropped) in the WGS84 range."""
    numbers = (
        value[:2]
        if isinstance(value, list)
        and len(value) in (2, 3)
        and all(
            isinstance(item, int | float) and not isinstance(item, bool)
            for item in value
        )
        else None
    )
    if numbers is None or not all(math.isfinite(float(item)) for item in numbers):
        lon, lat = math.nan, math.nan
    else:
        lon, lat = float(numbers[0]), float(numbers[1])
    if not (-180.0 <= lon <= 180.0 and -90.0 <= lat <= 90.0):
        raise _invalid(
            "area",
            message(
                "instance.area_bad_position", path=path, position=json.dumps(value)[:80]
            ),
            path=str(path),
        )
    return lon, lat


def _polygon_rings(
    coordinates: object, path: Path, counted: list[int]
) -> list[list[tuple[float, float]]]:
    """The rings of one polygon, checked: closed, 4 positions or more, in range."""
    if not isinstance(coordinates, list) or not coordinates:
        raise _invalid(
            "area", message("instance.area_bad_ring", path=path), path=str(path)
        )
    rings = []
    for ring in coordinates:
        if not isinstance(ring, list) or len(ring) < 4:
            raise _invalid(
                "area", message("instance.area_bad_ring", path=path), path=str(path)
            )
        counted[0] += len(ring)
        if counted[0] > AREA_MAX_VERTICES:
            raise _invalid(
                "area",
                message(
                    "instance.area_too_many_vertices",
                    path=path,
                    maximum=AREA_MAX_VERTICES,
                ),
                path=str(path),
                maximum=AREA_MAX_VERTICES,
            )
        positions = [_position(item, path) for item in ring]
        if positions[0] != positions[-1]:
            raise _invalid(
                "area", message("instance.area_bad_ring", path=path), path=str(path)
            )
        rings.append(positions)
    return rings


def _read_bytes(name: str, path: Path, maximum: int) -> bytes:
    """A file of the instance, refused when missing, unreadable or over ``maximum`` bytes."""
    try:
        with path.open("rb") as handle:
            data = handle.read(maximum + 1)
    except FileNotFoundError:
        raise _invalid(
            name,
            message("instance.file_missing", field=name, path=path),
            path=str(path),
        ) from None
    except OSError as exc:
        raise _invalid(
            name,
            message(
                "instance.file_unreadable", field=name, path=path, reason=reason(exc)
            ),
            path=str(path),
        ) from None
    if len(data) > maximum:
        raise _invalid(
            name,
            message("instance.file_too_large", field=name, path=path, maximum=maximum),
            path=str(path),
            maximum=maximum,
        )
    return data


def read_area(path: Path, mode: AreaMode = "focus") -> Area:
    """
    Read the area of an instance from a GeoJSON file (I4).

    Parameters
    ----------
    path : Path
        A GeoJSON file of at most `AREA_MAX_BYTES` holding one Polygon or MultiPolygon:
        the geometry itself, a Feature or a FeatureCollection of one Feature; longitude
        and latitude in WGS84 (RFC 7946; a ``crs`` member may only name WGS84), at most
        `AREA_MAX_VERTICES` positions, every ring closed with 4 positions or more. No
        buffer is added: the polygon is the area.
    mode : {"focus", "clip"}, optional
        What the area does.

    Returns
    -------
    Area
        The area with its box and an index of its edges.

    Raises
    ------
    ObserwatorValidationError
        ``details.option`` ``instance.area`` for any problem of the file.
    """
    data = _read_bytes("area", path, AREA_MAX_BYTES)
    try:
        document = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise _invalid(
            "area",
            message("instance.area_not_json", path=path, reason=reason(exc)),
            path=str(path),
        ) from None
    geometry = _geometry(document, path)
    counted = [0]
    parts = (
        [geometry.get("coordinates")]
        if geometry["type"] == "Polygon"
        else geometry.get("coordinates")
    )
    if not isinstance(parts, list) or not parts:
        raise _invalid(
            "area", message("instance.area_bad_ring", path=path), path=str(path)
        )
    polygons = [_polygon_rings(part, path, counted) for part in parts]
    indexed = tuple(_Polygon(rings) for rings in polygons)
    box = (
        min(polygon.box[0] for polygon in indexed),
        min(polygon.box[1] for polygon in indexed),
        max(polygon.box[2] for polygon in indexed),
        max(polygon.box[3] for polygon in indexed),
    )
    plain = [
        [[list(position) for position in ring] for ring in rings] for rings in polygons
    ]
    return Area(
        path=path,
        mode=mode,
        geometry={
            "type": geometry["type"],
            "coordinates": plain[0] if geometry["type"] == "Polygon" else plain,
        },
        box=box,
        vertices=counted[0],
        sha256=hashlib.sha256(data).hexdigest(),
        _polygons=indexed,
    )


# --- the logo and the regulamin --------------------------------------------------------


@dataclass(frozen=True)
class Logo:
    """
    The operator's logo, shown beside Obserwator's mark (I14).

    Attributes
    ----------
    path : Path
        Its file.
    media_type : {"image/png", "image/webp", "image/svg+xml"}
        Its type, read from the content.
    data : bytes
        Its bytes (at most `LOGO_MAX_BYTES`).
    sha256 : str
        SHA-256 of the bytes.
    """

    path: Path
    media_type: str
    data: bytes = field(repr=False)
    sha256: str


def _svg(data: bytes) -> bool:
    """Whether the bytes are an SVG document: XML whose root is ``<svg>`` of SVG's namespace."""
    try:
        root = ElementTree.fromstring(data)
    except ElementTree.ParseError:
        return False
    return root.tag == _SVG_ROOT


def read_logo(path: Path) -> Logo:
    """
    Read the operator's logo: PNG, WebP or SVG by its content, at most `LOGO_MAX_BYTES`.

    An SVG with a DOCTYPE or an entity is refused before it is parsed; one that holds a
    script is served all the same, since the GUI serves it only from its own origin with
    ``Content-Security-Policy: sandbox`` and as an ``<img>``.

    Raises
    ------
    ObserwatorValidationError
        ``details.option`` ``instance.logo``.
    """
    data = _read_bytes("logo", path, LOGO_MAX_BYTES)
    if data.startswith(_PNG):
        media_type = "image/png"
    elif data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        media_type = "image/webp"
    elif _SVG_FORBIDDEN.search(data):
        raise _invalid(
            "logo", message("instance.logo_svg_doctype", path=path), path=str(path)
        )
    elif _svg(data):
        media_type = "image/svg+xml"
    else:
        raise _invalid("logo", message("instance.logo_type", path=path), path=str(path))
    return Logo(path, media_type, data, hashlib.sha256(data).hexdigest())


@dataclass(frozen=True)
class Terms:
    """
    The operator's regulamin in Markdown, served in place of regulamin 1.0 (I15).

    The GUI builds it with the subset of Nogat's ``scripts/terms.py`` and fills it as
    the kit's page (``obserwator.gui._terms``); a field it cannot fill refuses the start.

    Attributes
    ----------
    path : Path
        Its file.
    text : str
        The Markdown, starting with its ``# `` title.
    sha256 : str
        SHA-256 of the file.
    """

    path: Path
    text: str = field(repr=False)
    sha256: str


def read_terms(path: Path) -> Terms:
    """
    Read the operator's regulamin: UTF-8 Markdown opening with ``# ``, safe links only.

    A link goes to an ``https://``, ``http://``, ``mailto:`` or ``#`` address or to a
    ``{{field}}`` the GUI fills; raw HTML is never passed on (the GUI escapes it).

    Raises
    ------
    ObserwatorValidationError
        ``details.option`` ``instance.terms``.
    """
    data = _read_bytes("terms", path, TERMS_MAX_BYTES)
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        raise _invalid(
            "terms", message("instance.terms_not_text", path=path), path=str(path)
        ) from None
    if not text.startswith("# "):
        raise _invalid(
            "terms", message("instance.terms_no_title", path=path), path=str(path)
        )
    for link in _LINK.finditer(text):
        if not _SAFE_HREF.match(link["href"]):
            raise _invalid(
                "terms",
                message("instance.terms_bad_link", path=path, href=link["href"][:200]),
                path=str(path),
            )
    return Terms(path, text, hashlib.sha256(data).hexdigest())


# --- the instance ---------------------------------------------------------------------


@dataclass(frozen=True)
class Instance:
    """
    A valid ``[obserwator.instance]``: the one filter of both servers (ADR-025).

    Attributes
    ----------
    providers : Mapping of str to {"visible", "hidden", "off"}
        The state of every provider of the registry (``visible`` unless the table
        names another, I2), in registry order.
    featured : str or None
        The featured provider (I6), never ``off``.
    start_view : {"all", "featured", "area"}
        Where the map starts (I5).
    area : Area or None
        The area and its mode (I4).
    pmaxtp : bool
        Whether PMAXTP is served (I8).
    title : str or None
        The operator's name in the page's title and the top bar (I14).
    logo : Logo or None
        The operator's logo (I14).
    terms : Terms or None
        The operator's regulamin (I15).
    """

    providers: Mapping[str, ProviderState]
    featured: str | None = None
    start_view: StartView = "all"
    area: Area | None = None
    pmaxtp: bool = True
    title: str | None = None
    logo: Logo | None = None
    terms: Terms | None = None
    _codes: dict[tuple[object, ...], frozenset[str]] = field(
        default_factory=dict, repr=False, compare=False
    )
    _lock: threading.Lock = field(
        default_factory=threading.Lock, repr=False, compare=False
    )

    def state(self, provider: str) -> ProviderState | None:
        """The state of a provider; None for an id the registry does not know."""
        return self.providers.get(provider)

    def serves(self, provider: str) -> bool:
        """Whether the provider's data are served (``visible`` or ``hidden``)."""
        return self.state(provider) in ("visible", "hidden")

    @property
    def served(self) -> tuple[str, ...]:
        """The providers served, the featured one first, then in registry order."""
        ordered = [p for p in self.providers if self.serves(p)]
        if self.featured in ordered:
            ordered.remove(self.featured)
            ordered.insert(0, self.featured)
        return tuple(ordered)

    @property
    def clips(self) -> bool:
        """Whether stations outside the area are not served (``area_mode = "clip"``)."""
        return self.area is not None and self.area.clips

    def keeps_point(self, lon: float | None, lat: float | None) -> bool:
        """Whether a location is served: anywhere without ``clip``, else inside the area."""
        if not self.clips:
            return True
        if lon is None or lat is None:
            return False
        assert self.area is not None
        return self.area.contains(lon, lat)

    def keeps(self, feature: StationFeature) -> bool:
        """
        Whether a station of a catalog is served (I3).

        Its provider is ``visible`` or ``hidden`` and, with ``clip``, its location lies
        inside the area; a station without a location is then not served.
        """
        if not self.serves(feature.provider):
            return False
        lon, lat = feature.geometry if feature.geometry else (None, None)
        return self.keeps_point(lon, lat)

    def reduce(
        self,
        catalogs: Mapping[str, _C],
        features: Mapping[str, StationFeature],
        series: Mapping[str, _S],
    ) -> tuple[dict[str, _C], dict[str, StationFeature], dict[str, _S]]:
        """
        A read of the data root reduced to what the instance serves (I3).

        Parameters
        ----------
        catalogs : Mapping of str to object
            The current catalog of each provider, by provider id.
        features : Mapping of str to StationFeature
            Their stations by code.
        series : Mapping of str to object
            The current series of each dataset (a dataclass with ``index``, a
            `SeriesIndex`), by dataset key.

        Returns
        -------
        tuple of dict
            The catalogs and series of the providers served and the stations `keeps`;
            with ``clip``, each series index keeps only those stations.
        """
        kept = {code: item for code, item in features.items() if self.keeps(item)}
        reduced: dict[str, _S] = {}
        for key, entry in series.items():
            if not self.serves(get_dataset(key).provider):
                continue
            if self.clips:
                plain: Any = entry
                if hasattr(plain, "index"):  # a series with its whole index
                    index = plain.index
                    held = {c: s for c, s in index.stations.items() if c in kept}
                    plain = replace(plain, index=replace(index, stations=held))
                else:  # a series keeping only its stations' summary
                    held = {c: s for c, s in plain.stations.items() if c in kept}
                    plain = replace(plain, stations=held)
                entry = cast(_S, plain)
            reduced[key] = entry
        return (
            {
                provider: item
                for provider, item in catalogs.items()
                if self.serves(provider)
            },
            kept,
            reduced,
        )

    def start(
        self, features: Mapping[str, StationFeature]
    ) -> tuple[StartView, Box | None]:
        """
        Where the map starts (I5), from the stations served.

        Parameters
        ----------
        features : Mapping of str to StationFeature
            The stations served (a reduced read).

        Returns
        -------
        tuple of (str, tuple or None)
            ``("featured", box)``: the box of the featured provider's located stations
            with a margin; ``("area", box)``: the area's box; ``("all", None)``: the
            whole data set as without an instance, also when the chosen view holds no
            station (the caller logs it).
        """
        if self.start_view == "featured":
            points = [
                item.geometry
                for item in features.values()
                if item.provider == self.featured and item.geometry
            ]
            if points:
                box = (
                    min(lon for lon, _ in points),
                    min(lat for _, lat in points),
                    max(lon for lon, _ in points),
                    max(lat for _, lat in points),
                )
                return "featured", _grown(box, START_MARGIN, START_MARGIN_MIN)
        elif self.start_view == "area" and self.area is not None:
            area = self.area
            if any(
                item.geometry and area.contains(*item.geometry)
                for item in features.values()
            ):
                return "area", area.box
        return "all", None

    @property
    def key(self) -> str:
        """A digest of the resolved section: part of the ETags of what it filters."""
        document = {
            "providers": dict(self.providers),
            "featured": self.featured,
            "start_view": self.start_view,
            "area": None if self.area is None else [self.area.mode, self.area.sha256],
            "pmaxtp": self.pmaxtp,
            "title": self.title,
            "logo": None if self.logo is None else self.logo.sha256,
            "terms": None if self.terms is None else self.terms.sha256,
        }
        text = json.dumps(document, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(text.encode("utf-8")).hexdigest()[:32]

    def catalog_codes(self, root: Path) -> frozenset[str]:
        """
        The codes of the stations of a data root's current catalogs that are served.

        Read again when a catalog's current version changes (the REST server asks on
        every request that names a station; the pointers are a few small files).

        Parameters
        ----------
        root : Path
            A data root.

        Returns
        -------
        frozenset of str
            The codes `keeps`; empty when the root has no catalog.
        """
        from obserwator.store import current_version, read_catalog

        versions: list[tuple[str, Path, str]] = []
        for provider, key in _CATALOG_DATASETS.items():
            if not self.serves(provider):
                continue
            entry = current_version(root, slot=f"catalog:{key}")
            if (
                entry is not None
                and entry.version is not None
                and entry.meta is not None
            ):
                versions.append((provider, Path(entry.version), entry.meta.sha256))
        token = (str(root), *((p, s) for p, _, s in versions))
        with self._lock:
            found = self._codes.get(token)
        if found is not None:
            return found
        codes: set[str] = set()
        for provider, path, _ in versions:
            for feature in read_catalog(path):
                if feature.provider != provider:
                    feature = replace(feature, provider=provider)
                if self.keeps(feature):
                    codes.add(feature.station_code)
        found = frozenset(codes)
        with self._lock:
            self._codes.clear()
            self._codes[token] = found
        return found

    def serves_station(self, code: str, root: Path | None) -> bool:
        """
        Whether a station named by its code is served, as a route that takes one asks.

        With ``clip`` the station must be one of `catalog_codes` of ``root`` (inside
        the area; no root, no station); without it the provider whose code pattern
        the code matches must be served. Either way a refused code answers as one
        that does not exist (``not_found``), so a guessed code tells nothing.

        Parameters
        ----------
        code : str
            A station code (IMGW-PIB's nine digits, ČHMÚ's WIGOS identifier).
        root : Path or None
            The data root whose catalogs locate the stations.
        """
        if self.clips:
            return root is not None and code in self.catalog_codes(root)
        owner = provider_of_code(code)
        return owner is not None and self.serves(owner)

    def report(self) -> dict[str, object]:
        """The resolved section as ``obserwator config show --json`` reports it."""
        area = self.area
        return {
            "title": self.title,
            "featured_provider": self.featured,
            "start_view": self.start_view,
            "pmaxtp": "on" if self.pmaxtp else "off",
            "providers": dict(self.providers),
            "area": None
            if area is None
            else {
                "path": str(area.path),
                "mode": area.mode,
                "box": list(area.box),
                "polygons": len(area._polygons),
                "vertices": area.vertices,
                "sha256": area.sha256,
            },
            "logo": None
            if self.logo is None
            else {
                "path": str(self.logo.path),
                "media_type": self.logo.media_type,
                "bytes": len(self.logo.data),
                "sha256": self.logo.sha256,
            },
            "terms": None
            if self.terms is None
            else {
                "path": str(self.terms.path),
                "bytes": len(self.terms.text.encode("utf-8")),
                "sha256": self.terms.sha256,
            },
        }


def provider_of_code(code: str) -> str | None:
    """The provider whose ``station_code_pattern`` a station code matches, or None."""
    for provider in providers():
        if re.fullmatch(provider.station_code_pattern, code):
            return provider.id
    return None


def _text(table: Mapping[str, Any], name: str) -> str | None:
    """An optional text field."""
    value = table.get(name)
    if value is None:
        return None
    if not isinstance(value, str):
        raise _invalid(
            name, message("instance.not_text", field=name), value=repr(value)[:80]
        )
    return value


def _choice(
    table: Mapping[str, Any], name: str, allowed: Sequence[str], default: str
) -> str:
    """A field with one of ``allowed`` values."""
    value = table.get(name, default)
    if value not in allowed:
        raise _invalid(
            name,
            message(
                "instance.bad_choice",
                field=name,
                value=json.dumps(value, default=str)[:80],
                allowed=", ".join(allowed),
            ),
            value=value
            if isinstance(value, str | int | float | bool)
            else repr(value)[:80],
            allowed=list(allowed),
        )
    return str(value)


def _file(base: Path, value: str) -> Path:
    """A path of the section: ``~`` expanded, relative ones to ``nogat.toml``'s directory."""
    path = Path(value).expanduser()
    return path if path.is_absolute() else base / path


def parse_instance(table: object, *, base: Path) -> Instance:
    """
    Check ``[obserwator.instance]`` and read its files (I1, I2, I4, I7, I14, I15).

    Parameters
    ----------
    table : object
        The table as ``tomllib`` read it.
    base : Path
        The directory of ``nogat.toml``: relative paths start there.

    Returns
    -------
    Instance
        The resolved section.

    Raises
    ------
    ObserwatorValidationError
        The first problem, ``details.option`` naming the field (``instance.<field>``,
        ``instance.providers.<id>`` for a provider's state).
    """
    if not isinstance(table, dict):
        raise ObserwatorValidationError(
            message("instance.not_a_table"), details={"option": SECTION}
        )
    for name in table:
        if name not in FIELDS:
            raise _invalid(
                str(name),
                message(
                    "instance.unknown_field", field=name, allowed=", ".join(FIELDS)
                ),
                allowed=list(FIELDS),
            )
    known = [provider.id for provider in providers()]
    given = table.get("providers", {})
    if not isinstance(given, dict):
        raise _invalid("providers", message("instance.providers_not_table"))
    for provider, state in given.items():
        if provider not in known:
            raise ObserwatorValidationError(
                message(
                    "instance.unknown_provider",
                    provider=provider,
                    known=", ".join(known),
                ),
                details={
                    "option": f"{SECTION}.providers.{provider}",
                    "allowed": known,
                },
            )
        if state not in PROVIDER_STATES:
            raise ObserwatorValidationError(
                message(
                    "instance.bad_choice",
                    field=f"providers.{provider}",
                    value=json.dumps(state, default=str)[:80],
                    allowed=", ".join(PROVIDER_STATES),
                ),
                details={
                    "option": f"{SECTION}.providers.{provider}",
                    "allowed": list(PROVIDER_STATES),
                },
            )
    states: dict[str, ProviderState] = {
        provider: cast(ProviderState, given.get(provider, "visible"))
        for provider in known
    }
    featured = _text(table, "featured_provider")
    if featured is not None:
        if featured not in known:
            raise _invalid(
                "featured_provider",
                message(
                    "instance.unknown_provider",
                    provider=featured,
                    known=", ".join(known),
                ),
                value=featured,
                allowed=known,
            )
        if states[featured] == "off":
            raise _invalid(
                "featured_provider",
                message("instance.featured_off", provider=featured),
                value=featured,
            )
    start_view = cast(StartView, _choice(table, "start_view", START_VIEWS, "all"))
    area_mode = cast(AreaMode, _choice(table, "area_mode", AREA_MODES, "focus"))
    pmaxtp = _choice(table, "pmaxtp", PMAXTP_STATES, "on") == "on"
    if all(state == "off" for state in states.values()) and not pmaxtp:
        raise _invalid("providers", message("instance.nothing_served"))
    title = _text(table, "title")
    if title is not None:
        title = title.strip()
        if not title or len(title) > TITLE_MAX or not title.isprintable():
            raise _invalid(
                "title",
                message("instance.bad_title", maximum=TITLE_MAX),
                maximum=TITLE_MAX,
            )
    area_value = _text(table, "area")
    if area_value is None and "area_mode" in table:
        raise _invalid("area_mode", message("instance.mode_needs_area"))
    if start_view == "featured" and featured is None:
        raise _invalid("start_view", message("instance.start_needs_featured"))
    if start_view == "area" and area_value is None:
        raise _invalid("start_view", message("instance.start_needs_area"))
    area = None if area_value is None else read_area(_file(base, area_value), area_mode)
    logo_value = _text(table, "logo")
    logo = None if logo_value is None else read_logo(_file(base, logo_value))
    terms_value = _text(table, "terms")
    terms = None if terms_value is None else read_terms(_file(base, terms_value))
    return Instance(
        providers=states,
        featured=featured,
        start_view=start_view,
        area=area,
        pmaxtp=pmaxtp,
        title=title,
        logo=logo,
        terms=terms,
    )


def load_instance() -> Instance | None:
    """
    The deployment's ``[obserwator.instance]``, checked (I7); None without the table.

    The file is ``nogat.toml`` of ``NOGAT_CONFIG`` or the user's configuration
    directory; a server calls this once as it starts and refuses to start on an error.

    Raises
    ------
    ObserwatorValidationError
        The first problem of the section (`parse_instance`).
    """
    file = environment.config_file()
    table = file.sections.get(environment.TOOL, {}).get(SECTION)
    if table is None:
        return None
    return parse_instance(table, base=file.path.parent)


def instance_report() -> tuple[dict[str, object] | None, dict[str, object] | None]:
    """
    The section for ``obserwator config show``: its report and its problem.

    Returns
    -------
    tuple
        The resolved section (`Instance.report`) or None, and the problem that keeps
        the servers from starting (``code`` ``invalid_instance``, ``option``,
        ``message``) or None.
    """
    try:
        found = load_instance()
    except ObserwatorValidationError as exc:
        return None, {
            "code": "invalid_instance",
            "option": exc.details.get("option", SECTION),
            "message": exc.detail,
        }
    return (None if found is None else found.report()), None
