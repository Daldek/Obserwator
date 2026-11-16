"""Fetch IMGW-PIB reference data into the reference directory.

After installing the package (``pip install -e .``), run it with no arguments:

    python -m obserwator.reference_data

The module reuses ``obserwator.stations.fetch_hydro_states`` (it does not
duplicate IMGW URLs, parsing, or encoding) and writes only
``hydro_stations_locations.csv``, the format descriptions (``desc/``) and
``ATTRIBUTION.txt``.
Output goes to ``settings.reference_dir``: ``OBSERWATOR_REFERENCE_DIR``, ``[obserwator]
reference_dir`` of ``nogat.toml``, else ``<cache_dir>/obserwator/reference`` (the cache
directory of ``nogat``; ``OBSERWATOR_CACHE_DIR`` moves it). Nothing is written to the
working directory.

All fetched data comes from IMGW-PIB and is subject to IMGW-PIB's terms of use:
the station locations come from the map of the hydrological service hydro.imgw.pl
(reference data, never its operational water states) and the format descriptions
from danepubliczne.imgw.pl. The locations file carries the lines of its data in
the trailing columns ``attribution`` and ``terms_notice`` and ``ATTRIBUTION.txt``
the lines of the whole directory (`obserwator.attribution`, ADR-012).
"""

import csv
import io
import re
import sys
from collections.abc import Iterable, Iterator
from pathlib import Path

import httpx

from obserwator.attribution import attribution
from obserwator.config import human_language, settings
from obserwator.exceptions import ObserwatorError
from obserwator.messages import Lang, message, reason
from obserwator.output import write_attribution
from obserwator.stations import fetch_hydro_states

# Format-description files are not covered by obserwator.stations, so their URLs
# are defined here (new resources, not a duplicate of the station-listing logic).
DESC_BASE = "https://danepubliczne.imgw.pl/data/dane_pomiarowo_obserwacyjne"
HYDRO_DESC = [
    "dane_hydrologiczne/dobowe/CODZ_publiczne_format.txt",
    "dane_hydrologiczne/dobowe/ZJAW_publiczne_format.txt",
    "dane_hydrologiczne/miesieczne/MIES_publiczne_format.txt",
    "dane_hydrologiczne/polroczne_i_roczne/POLR_publiczne_format.txt",
]
METEO_INTERVALS = ["dobowe", "miesieczne", "terminowe"]
METEO_SUBTYPES = ["klimat", "opad", "synop"]

# The lines of the station locations (processed hydro.imgw.pl data) and of the
# whole directory, the verbatim format descriptions included.
LOCATION_LINES = attribution("imgw_hydro")
DIRECTORY_LINES = LOCATION_LINES | attribution("imgw", processed=False)

# Language of the lines this module prints: OBSERWATOR_LANG (Polish by default), Polish
# also for an unusable value (the CLI reports that one).
_LANG: Lang = human_language() or "pl"


def _write_csv(path: Path, header: list[str], rows: Iterable[list[object]]) -> None:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([*header, "attribution", "terms_notice"])
    count = 0
    for row, (attributed, notice) in _with_lines(rows):
        writer.writerow([*row, attributed, notice])
        count += 1
    path.parent.mkdir(parents=True, exist_ok=True)
    # newline="": the csv module already ended each row with \r\n; text mode would
    # turn it into \r\r\n on Windows.
    path.write_text(buf.getvalue(), encoding="utf-8", newline="")
    print(message("reference.rows_written", lang=_LANG, path=path, count=count))


def _with_lines(
    rows: Iterable[list[object]],
) -> Iterator[tuple[list[object], tuple[str, str]]]:
    """
    Rows with the cells of the trailing columns ``attribution`` and ``terms_notice``.

    One line per cell from the first data row down, empty below; the last row
    of a table with fewer rows than lines holds the rest, joined with a line
    feed (Nogat DEV-20.5).
    """
    listed = list(rows)
    columns = (LOCATION_LINES.attribution, LOCATION_LINES.terms_notice)
    for number, row in enumerate(listed):
        last = number == len(listed) - 1
        yield (
            row,
            (
                "\n".join(columns[0][number:]) if last else _line(columns[0], number),
                "\n".join(columns[1][number:]) if last else _line(columns[1], number),
            ),
        )


def _line(lines: tuple[str, ...], number: int) -> str:
    return lines[number] if number < len(lines) else ""


def _write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    print(
        message(
            "reference.bytes_written", lang=_LANG, path=path, size=f"{len(data):,} B"
        )
    )


def fetch_stations(reference_dir: Path) -> None:
    """Fetch hydrological station coordinates via the library (no duplication)."""
    print(message("reference.station_coordinates", lang=_LANG))
    _write_csv(
        reference_dir / "hydro_stations_locations.csv",
        ["station_code", "latitude", "longitude"],
        (
            [s.station_code, s.latitude, s.longitude]
            for s in fetch_hydro_states()
            if s.longitude is not None and s.latitude is not None
        ),
    )


def _meteo_format_files(client: httpx.Client) -> Iterator[tuple[str, str]]:
    """Yield (filename, url) for every meteo *_format.txt found on the server."""
    seen: set[str] = set()
    for interval in METEO_INTERVALS:
        for subtype in METEO_SUBTYPES:
            base = f"{DESC_BASE}/dane_meteorologiczne/{interval}/{subtype}/"
            listing = client.get(base)
            if not listing.is_success:
                continue  # e.g. terminowe/opad does not exist
            for name in re.findall(r'href="([^"/]+_format\.txt)"', listing.text):
                if name not in seen:
                    seen.add(name)
                    yield name, base + name


def fetch_descriptions(reference_dir: Path) -> None:
    """Fetch file-format description files (resources outside the library)."""
    with httpx.Client(timeout=60, follow_redirects=True) as client:
        print(message("reference.format_descriptions_hydro", lang=_LANG))
        for rel in HYDRO_DESC:
            resp = client.get(f"{DESC_BASE}/{rel}")
            if resp.is_success:
                _write_bytes(
                    reference_dir / "desc" / "dane_hydrologiczne" / Path(rel).name,
                    resp.content,
                )
            else:
                print(
                    message(
                        "reference.skipped",
                        lang=_LANG,
                        name=rel,
                        status=resp.status_code,
                    )
                )

        print(message("reference.format_descriptions_meteo", lang=_LANG))
        for name, url in _meteo_format_files(client):
            resp = client.get(url)
            if resp.is_success:
                _write_bytes(
                    reference_dir / "desc" / "dane_meteorologiczne" / name,
                    resp.content,
                )
            else:
                print(
                    message(
                        "reference.skipped",
                        lang=_LANG,
                        name=name,
                        status=resp.status_code,
                    )
                )


def main() -> int:
    """Fetch all reference data into ``settings.reference_dir``."""
    reference_dir = settings.reference_dir
    print(message("reference.fetching_to", lang=_LANG, directory=reference_dir))
    print(message("reference.terms_of_use", lang=_LANG))
    print(
        message(
            "reference.required_attribution",
            lang=_LANG,
            attribution="\n".join(DIRECTORY_LINES.lines),
        )
    )

    try:
        fetch_stations(reference_dir)
        write_attribution(reference_dir, DIRECTORY_LINES)
        fetch_descriptions(reference_dir)
    except (ObserwatorError, httpx.HTTPError) as exc:
        print(
            message("reference.fetch_failed", lang=_LANG, error=reason(exc)),
            file=sys.stderr,
        )
        return 1

    print(message("reference.done", lang=_LANG, directory=reference_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
