"""
The packaged state borders of Poland and Czechia (ADR-018).

Two files of ``obserwator/_data``, written only by ``scripts/build_borders.py`` from the
national registers: the state border of Poland from PRG (GUGiK) and the state of Czechia
from RÚIAN (ČÚZK), simplified to the tolerance their properties name. Each is one GeoJSON
feature whose properties say what it is: ``name``, ``product``, ``source``, ``created``,
``acquired``, ``license`` and ``simplify_tolerance_m``. A provider's station catalog
checks its locations against its country's border (`obserwator.store.catalog`), the GUI
draws both as the map's background without a basemap, and `obserwator.attribution`
writes their lines G and Z (Nogat DEV §20) from the properties. Standard library only.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from functools import cache
from importlib.resources import files
from types import MappingProxyType

POLAND = "poland_border_wgs84.geojson"
"""The state border of Poland, from PRG (GUGiK)."""
CZECHIA = "czechia_border_wgs84.geojson"
"""The state border of Czechia, from RÚIAN (ČÚZK)."""
PROVIDERS: Mapping[str, str] = MappingProxyType({"IMGW-PIB": POLAND, "CHMI": CZECHIA})
"""The border each provider's station locations are checked against."""


@dataclass(frozen=True)
class Border:
    """
    One packaged border: what its properties say and its outline.

    Attributes
    ----------
    product : str
        The register it comes from, as Nogat DEV §20 names it: ``PRG`` or ``RÚIAN``.
    created : str
        The day the register's national file was published (its ``Last-Modified``),
        ``YYYY-MM-DD`` in UTC.
    acquired : str
        The day the national file was downloaded, ``YYYY-MM-DD`` in UTC.
    tolerance_m : float
        The simplification tolerance: the outline lies within this many metres of the
        register's border.
    rings : tuple of list
        Every ring of the outline, a list of ``[longitude, latitude]`` pairs in WGS 84;
        read only.
    """

    product: str
    created: str
    acquired: str
    tolerance_m: float
    rings: tuple[list[list[float]], ...]


@cache
def border(resource: str) -> Border:
    """
    Read a packaged border, once per process.

    Parameters
    ----------
    resource : str
        `POLAND` or `CZECHIA`.

    Returns
    -------
    Border
        Its properties and its rings.
    """
    document = json.loads(files("obserwator").joinpath("_data", resource).read_bytes())
    (feature,) = document["features"]
    properties = feature["properties"]
    geometry = feature["geometry"]
    polygons = (
        [geometry["coordinates"]]
        if geometry["type"] == "Polygon"
        else geometry["coordinates"]
    )
    return Border(
        product=properties["product"],
        created=properties["created"],
        acquired=properties["acquired"],
        tolerance_m=float(properties["simplify_tolerance_m"]),
        rings=tuple(ring for polygon in polygons for ring in polygon),
    )
