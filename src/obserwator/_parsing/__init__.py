"""Archive parsing for IMGW-PIB ZIP/CSV files and ČHMÚ JSON/CSV files."""

from collections.abc import Collection, Iterator
from datetime import date

from obserwator._parsing.chmu import parse_chmu_hydro_daily, parse_chmu_meteo_daily
from obserwator._parsing.hydro import normalize_hydro_archive
from obserwator._parsing.meteo import normalize_meteo_archive, normalize_synop_archive
from obserwator.datasets import ArchiveFile
from obserwator.exceptions import ObserwatorValidationError
from obserwator.messages import message
from obserwator.models import NormalizedRecord

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
    ``pl.imgw.meteo_precip_daily``, ``pl.imgw.meteo_synop_daily``) and the
    ČHMÚ daily datasets (``cz.chmu.hydro_daily``, ``cz.chmu.meteo_daily``)
    are supported. Parsing is strict: malformed rows raise instead of being
    skipped.

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
        ``normalize_synop_archive``, ``parse_chmu_hydro_daily`` and
        ``parse_chmu_meteo_daily`` for the per-dataset record layout.

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
    """
    if archive.dataset in {
        "pl.imgw.hydro_daily",
        "pl.imgw.hydro_monthly",
        "pl.imgw.hydro_semiannual",
    }:
        yield from normalize_hydro_archive(
            archive.dataset,
            archive.server_path,
            data,
            stations=stations,
            skipped_months=skipped_months,
        )
    elif archive.dataset in {
        "pl.imgw.meteo_climate_daily",
        "pl.imgw.meteo_precip_daily",
    }:
        yield from normalize_meteo_archive(
            archive.dataset,
            archive.server_path,
            data,
            year=archive.year,
            month=archive.month,
            carry=carry if archive.dataset in CARRY_DATASETS else None,
            stations=stations,
            skipped_months=skipped_months,
        )
    elif archive.dataset == "pl.imgw.meteo_synop_daily":
        yield from normalize_synop_archive(
            archive.server_path,
            data,
            start=archive.period_start,
            end=archive.period_end,
        )
    elif archive.dataset == "cz.chmu.hydro_daily":
        yield from parse_chmu_hydro_daily(data, filename=archive.server_path)
    elif archive.dataset == "cz.chmu.meteo_daily":
        yield from parse_chmu_meteo_daily(data, filename=archive.server_path)
    else:
        raise ObserwatorValidationError(
            message("parsing.no_parser_archive", dataset=archive.dataset)
        )
