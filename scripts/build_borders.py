# /// script
# requires-python = ">=3.12"
# dependencies = ["numpy>=1.26", "pyproj>=3.6", "pyshp>=2.3", "shapely>=2.0"]
# ///
"""
Build the packaged state borders of Poland and Czechia from the national registers.

The only way ``src/obserwator/_data/poland_border_wgs84.geojson`` and
``czechia_border_wgs84.geojson`` change (ADR-018). Kartograf downloads the national
files into a temporary store under ``--work-dir``, never a production store::

    kartograf boundaries download --product admin --whole-country --country pl \
        --root <work-dir>/kartograf
    kartograf boundaries download --product admin --whole-country --country cz \
        --root <work-dir>/kartograf

Poland is the state border of PRG (GUGiK): the layer ``A00_Granice_panstwa`` of the
national file, the state territory with the internal sea waters and the territorial
sea. Czechia is the state of RÚIAN (ČÚZK): the layer ``STATY_P`` of the national file.
Each layer is dissolved to one polygon in the CRS of its ``.prj``, simplified by
Douglas-Peucker with its topology kept in a metric CRS (EPSG:2180 for Poland,
EPSG:5514 for Czechia) to `SIMPLIFY_TOLERANCE_M`, transformed to WGS 84, snapped to
`COORDINATE_DECIMALS` and written as one RFC 7946 feature (exterior ring
counter-clockwise). Its properties say what it is: ``name``, ``product``, ``source``,
``created`` (the national file's ``Last-Modified`` day), ``acquired`` (the day of the
download), both read from Kartograf's sidecar ``kartograf-meta/1`` in UTC,
``license`` and ``simplify_tolerance_m``. ``obserwator.attribution`` writes the lines
G and Z of Nogat DEV §20 from them.

The same national files and tolerance give the same bytes. A second run with the
same ``--work-dir`` reuses the files Kartograf stored there; a new directory
downloads them again (about 380 MB from GUGiK and 250 MB from ČÚZK).

Usage::

    uv run scripts/build_borders.py --work-dir <directory outside every store>
"""

from __future__ import annotations

import argparse
import io
import json
import subprocess
import sys
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

import numpy as np
import shapefile
import shapely
from pyproj import CRS, Transformer
from shapely.geometry import MultiPolygon, Polygon, mapping, shape
from shapely.geometry.polygon import orient

SIMPLIFY_TOLERANCE_M = 50
"""Douglas-Peucker tolerance in metres: the outline stays within 50 m of the register's.

A third of the smallest location uncertainty of a station (150 m,
``obserwator.store.catalog.MIN_UNCERTAINTY_M``), so the country check of a catalog
depends on the published coordinates, not on the outline; under two pixels of the map
up to zoom 12; about 6,200 vertices for Poland and 5,100 for Czechia, files of about
120 and 100 KB.
"""
COORDINATE_DECIMALS = 5
"""Decimal places of a coordinate: 1.1 m of latitude, far below the tolerance."""
OUTPUT = Path(__file__).resolve().parent.parent / "src" / "obserwator" / "_data"
"""The package's data directory, where the two files live."""


@dataclass(frozen=True)
class Country:
    """One border: what Kartograf downloads and what the file says of it."""

    code: str
    file: str
    name: str
    provider: str
    product: str
    layer: str
    metric_crs: str
    license: str


COUNTRIES = (
    Country(
        code="pl",
        file="poland_border_wgs84.geojson",
        name="Polska",
        provider="GUGiK",
        product="PRG",
        layer="A00_Granice_panstwa",
        metric_crs="EPSG:2180",
        license=(
            "GUGiK conditions of reuse (https://www.gov.pl/web/gugik/"
            "ponowne-wykorzystanie-informacji-sektora-publicznego)"
        ),
    ),
    Country(
        code="cz",
        file="czechia_border_wgs84.geojson",
        name="Czechy",
        provider="ČÚZK",
        product="RÚIAN",
        layer="STATY_P",
        metric_crs="EPSG:5514",
        license="CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/)",
    ),
)


def download(kartograf: str, country: Country, root: Path) -> Path:
    """
    Download the national file of a country into Kartograf's store under ``root``.

    Parameters
    ----------
    kartograf : str
        The ``kartograf`` executable.
    country : Country
        The border to download.
    root : Path
        The temporary store (``--root`` of Kartograf).

    Returns
    -------
    Path
        The ZIP of the national file; its sidecar is ``<path>.meta.json``.
    """
    command = [
        kartograf,
        "boundaries",
        "download",
        "--product",
        "admin",
        "--whole-country",
        "--country",
        country.code,
        "--root",
        str(root),
        "--json",
        "--quiet",
    ]
    done = subprocess.run(command, capture_output=True, text=True, check=False)
    try:
        document = json.loads(done.stdout)
    except json.JSONDecodeError:
        sys.exit(f"{' '.join(command)}: no JSON answer\n{done.stderr}")
    if done.returncode != 0 or document.get("status") != "ok":
        sys.exit(f"{' '.join(command)}: {json.dumps(document, ensure_ascii=False)}")
    files = document["result"]["files"]
    if len(files) != 1:
        sys.exit(f"{' '.join(command)}: expected one national file, got {files}")
    return Path(files[0]["path"])


def provenance(archive: Path) -> tuple[str, str, str]:
    """
    The source address and the days of creation and download of a national file.

    Parameters
    ----------
    archive : Path
        The ZIP Kartograf stored.

    Returns
    -------
    tuple of str
        The address it was downloaded from, the day of its ``Last-Modified``
        header and the day of the download, both ``YYYY-MM-DD`` in UTC.
    """
    sidecar = json.loads(archive.with_name(f"{archive.name}.meta.json").read_text())
    if sidecar.get("schema") != "kartograf-meta/1":
        sys.exit(f"{archive}: not a kartograf-meta/1 sidecar")
    modified = parsedate_to_datetime(sidecar["extra"]["http"]["last_modified"])
    downloaded = datetime.fromisoformat(sidecar["downloaded_at"])
    return (
        sidecar["extra"]["source"]["url"],
        modified.astimezone(UTC).date().isoformat(),
        downloaded.astimezone(UTC).date().isoformat(),
    )


def read_layer(archive: Path, layer: str) -> tuple[shapely.Geometry, CRS]:
    """
    The features of one layer of a zipped shapefile, dissolved, and their CRS.

    Parameters
    ----------
    archive : Path
        The ZIP of the national file.
    layer : str
        The layer's file name without its extension, in any directory of the ZIP.

    Returns
    -------
    tuple
        The union of the layer's geometries and the CRS of its ``.prj``.
    """
    with zipfile.ZipFile(archive) as bundle:
        members = {
            Path(name).suffix.lower(): name
            for name in bundle.namelist()
            if Path(name).stem == layer
        }
        missing = {".shp", ".shx", ".dbf", ".prj"} - members.keys()
        if missing:
            sys.exit(f"{archive}: layer {layer} lacks {sorted(missing)}")
        parts = {suffix: bundle.read(name) for suffix, name in members.items()}
    crs = CRS.from_wkt(parts[".prj"].decode("utf-8"))
    reader = shapefile.Reader(
        shp=io.BytesIO(parts[".shp"]),
        shx=io.BytesIO(parts[".shx"]),
        dbf=io.BytesIO(parts[".dbf"]),
        encodingErrors="replace",
    )
    geometries = [shape(item.__geo_interface__) for item in reader.shapes()]
    if not geometries:
        sys.exit(f"{archive}: layer {layer} has no features")
    return shapely.union_all(geometries), crs


def project(geometry: shapely.Geometry, source: CRS, target: CRS) -> shapely.Geometry:
    """``geometry`` from ``source`` to ``target`` (longitude first), unchanged if equal."""
    if source.equals(target, ignore_axis_order=True):
        return geometry
    transformer = Transformer.from_crs(source, target, always_xy=True)

    def moved(points: np.ndarray) -> np.ndarray:
        x, y = transformer.transform(points[:, 0], points[:, 1])
        return np.column_stack([x, y])

    return shapely.transform(geometry, moved)


def outline(country: Country, archive: Path) -> Polygon | MultiPolygon:
    """
    The simplified border of a country in WGS 84, ready to be written.

    Parameters
    ----------
    country : Country
        The border.
    archive : Path
        The ZIP of its national file.

    Returns
    -------
    Polygon or MultiPolygon
        Valid, snapped to `COORDINATE_DECIMALS`, exterior rings counter-clockwise.
    """
    geometry, crs = read_layer(archive, country.layer)
    metric = CRS.from_user_input(country.metric_crs)
    simplified = project(geometry, crs, metric).simplify(
        SIMPLIFY_TOLERANCE_M, preserve_topology=True
    )
    wgs84 = project(simplified, metric, CRS.from_epsg(4326))
    snapped = shapely.set_precision(wgs84, 10.0**-COORDINATE_DECIMALS)
    if isinstance(snapped, Polygon):
        result: Polygon | MultiPolygon = orient(snapped, sign=1.0)
    elif isinstance(snapped, MultiPolygon):
        result = MultiPolygon([orient(part, sign=1.0) for part in snapped.geoms])
    else:
        sys.exit(f"{country.name}: the outline is a {snapped.geom_type}")
    if result.is_empty or not result.is_valid:
        sys.exit(f"{country.name}: the simplified outline is not a valid polygon")
    return result


def rounded(value: Any) -> Any:
    """Coordinates of a GeoJSON geometry rounded to `COORDINATE_DECIMALS`."""
    if isinstance(value, float):
        return round(value, COORDINATE_DECIMALS)
    if isinstance(value, list | tuple):
        return [rounded(item) for item in value]
    return value


def document(
    country: Country, geometry: Polygon | MultiPolygon, archive: Path
) -> dict[str, Any]:
    """
    The GeoJSON of a country's border, its properties first.

    Parameters
    ----------
    country : Country
        The border.
    geometry : Polygon or MultiPolygon
        Its outline from `outline`.
    archive : Path
        The ZIP of its national file, beside its sidecar.

    Returns
    -------
    dict
        A FeatureCollection of one feature.
    """
    url, created, acquired = provenance(archive)
    shaped = mapping(geometry)
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "name": country.name,
                    "product": country.product,
                    "source": (
                        f"{country.provider}, {country.product} national file "
                        f"{url} (layer {country.layer})"
                    ),
                    "created": created,
                    "acquired": acquired,
                    "license": country.license,
                    "simplify_tolerance_m": SIMPLIFY_TOLERANCE_M,
                },
                "geometry": {
                    "type": shaped["type"],
                    "coordinates": rounded(shaped["coordinates"]),
                },
            }
        ],
    }


def main(argv: list[str] | None = None) -> int:
    """
    Download, simplify and write both borders.

    Parameters
    ----------
    argv : list of str, optional
        The arguments; ``sys.argv[1:]`` when omitted.

    Returns
    -------
    int
        The exit code: 0 when both files were written.
    """
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument(
        "--work-dir",
        type=Path,
        required=True,
        help="directory of Kartograf's temporary store, outside every store",
    )
    parser.add_argument(
        "--kartograf", default="kartograf", help="the kartograf executable"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=OUTPUT,
        help=f"where the two files are written (default {OUTPUT})",
    )
    args = parser.parse_args(argv)
    root = args.work_dir.expanduser().resolve() / "kartograf"
    root.mkdir(parents=True, exist_ok=True)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for country in COUNTRIES:
        archive = download(args.kartograf, country, root)
        geometry = outline(country, archive)
        text = json.dumps(
            document(country, geometry, archive),
            ensure_ascii=False,
            separators=(",", ":"),
        )
        target = args.output_dir / country.file
        target.write_text(text + "\n", encoding="utf-8")
        vertices = shapely.get_num_coordinates(geometry)
        print(
            f"{target}: {country.product}, {vertices} vertices, "
            f"{target.stat().st_size} B"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
