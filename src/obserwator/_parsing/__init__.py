"""Archive parsing for IMGW-PIB ZIP/CSV files and ČHMÚ JSON/CSV files."""

from __future__ import annotations

from collections.abc import Collection, Iterator
from datetime import date
from typing import TYPE_CHECKING

from obserwator.datasets import ArchiveFile, get_dataset, get_provider
from obserwator.exceptions import ObserwatorValidationError
from obserwator.messages import message
from obserwator.models import NormalizedRecord

if TYPE_CHECKING:
    from obserwator.providers.base import SeriesContext

CARRY_DATASETS = frozenset({"pl.imgw.meteo_precip_daily"})
"""Datasets whose archives leave something to the next one (``carry``)."""


def normalize_archive(
    archive: ArchiveFile, /, *, data: bytes
) -> Iterator[NormalizedRecord]:
    """
    Normalize a physical source archive using the parser of its dataset.

    IMGW-PIB hydrological datasets (``pl.imgw.hydro_daily``,
    ``pl.imgw.hydro_monthly``, ``pl.imgw.hydro_semiannual``), IMGW-PIB daily
    meteorological datasets (``pl.imgw.meteo_climate_daily``,
    ``pl.imgw.meteo_precip_daily``, ``pl.imgw.meteo_synop_daily``), the
    ČHMÚ daily datasets (``cz.chmu.hydro_daily``, ``cz.chmu.meteo_daily``) and
    ČHMÚ's groundwater (``cz.chmu.groundwater_daily``,
    ``cz.chmu.groundwater_weekly``) are supported. Parsing is strict: malformed
    rows raise instead of being skipped.

    Parameters
    ----------
    archive : ArchiveFile
        Catalog entry of the archive; its ``dataset`` selects the parser,
        ``server_path`` names it in error messages (for ČHMÚ its file name
        also gives the station code and the year or element) and, for IMGW
        meteorological data, ``year``/``month`` (synop: ``period_start`` and
        ``period_end``) define the expected period.
    data : bytes
        Archive content: a ZIP archive (IMGW-PIB) or the JSON/CSV file
        (ČHMÚ).

    Yields
    ------
    NormalizedRecord
        Normalized measurements with value/flag pairs; see
        ``normalize_hydro_archive``, ``normalize_meteo_archive``,
        ``normalize_synop_archive``, ``parse_chmu_hydro_daily``,
        ``parse_chmu_meteo_daily`` and ``parse_chmu_groundwater`` for the
        per-dataset record layout.

    Raises
    ------
    ObserwatorValidationError
        If no parser is registered for ``archive.dataset``, or a ČHMÚ
        ``server_path`` does not end with a file name of its dataset.
    ObserwatorDataError
        If the archive is unreadable or unsafe, or contains malformed or
        contradictory data.
    """
    yield from normalize_in_sequence(archive, data=data, carry=None)


def normalize_in_sequence(
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
    `normalize_archive` of one of a dataset's archives parsed in date order.

    ``carry`` takes what one archive leaves to the next (the datasets of
    `CARRY_DATASETS`): for IMGW-PIB's daily precipitation
    (``pl.imgw.meteo_precip_daily``), per station, the last day whose ``P``
    was listed missing, so a total on the first day of a monthly archive
    after missing days at the end of the previous one is ``"accumulated"`` as
    one within an archive is. Pass one dictionary, empty at first, to every
    archive of the sequence; ``None`` parses the archive alone, as
    ``normalize_archive``. Other datasets ignore it.

    ``stations`` lets the parsers of IMGW-PIB's daily and monthly archives of
    the whole country skip the rows of other stations before they read their
    values (a series of chosen stations, ADR-026); such rows are not checked
    beyond their station code and date. Other parsers ignore it, so the
    caller still keeps only the records of the stations it wants.
    ``skipped_months`` then receives the first day of every calendar month the
    records of the skipped rows would have covered: the months the archive
    publishes, which the records of the chosen stations alone may not show.
    ``context`` is what a series build gives the parser beside the archive (the
    station sources of `ProviderAdapter.series_sources`: PIG-PIB's points, whose
    ground elevation gives ``H_asl``, ADR-035).
    """
    try:
        descriptor = get_dataset(archive.dataset)
    except ObserwatorValidationError:
        descriptor = None
    if descriptor is None or descriptor.key != archive.dataset:
        raise ObserwatorValidationError(
            message("parsing.no_parser_archive", dataset=archive.dataset)
        )
    # The parser of each dataset is its provider's (ADR-029).
    yield from get_provider(descriptor.provider).adapter.normalize(
        archive,
        data=data,
        carry=carry,
        stations=stations,
        skipped_months=skipped_months,
        context=context,
    )
