"""Archive parsing for IMGW-PIB ZIP/CSV files and ČHMÚ JSON/CSV files."""

from collections.abc import Iterator
from datetime import date

from obserwator._parsing.chmi import parse_chmi_hydro_daily, parse_chmi_meteo_daily
from obserwator._parsing.hydro import normalize_hydro_archive
from obserwator._parsing.meteo import normalize_meteo_archive, normalize_synop_archive
from obserwator.datasets import ArchiveFile
from obserwator.exceptions import ObserwatorValidationError
from obserwator.messages import message
from obserwator.models import NormalizedRecord


def normalize_archive(
    archive: ArchiveFile, /, *, data: bytes
) -> Iterator[NormalizedRecord]:
    """
    Normalize a physical source archive using the parser of its dataset.

    IMGW-PIB hydrological datasets (``pl.imgw.hydro_daily``,
    ``pl.imgw.hydro_monthly``, ``pl.imgw.hydro_semiannual``), IMGW-PIB daily
    meteorological datasets (``pl.imgw.meteo_climate_daily``,
    ``pl.imgw.meteo_precip_daily``, ``pl.imgw.meteo_synop_daily``) and the
    ČHMÚ daily datasets (``cz.chmi.hydro_daily``, ``cz.chmi.meteo_daily``)
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
        ``normalize_synop_archive``, ``parse_chmi_hydro_daily`` and
        ``parse_chmi_meteo_daily`` for the per-dataset record layout.

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
    archive: ArchiveFile, /, *, data: bytes, carry: dict[str, date] | None
) -> Iterator[NormalizedRecord]:
    """
    `normalize_archive` of one of a dataset's archives parsed in date order.

    ``carry`` takes what one archive leaves to the next: for IMGW-PIB's daily
    precipitation (``pl.imgw.meteo_precip_daily``), per station, the last day
    whose ``P`` was listed missing, so a total on the first day of a monthly
    archive after missing days at the end of the previous one is
    ``"accumulated"`` as one within an archive is. Pass one dictionary,
    empty at first, to every archive of the sequence; ``None`` parses the
    archive alone, as ``normalize_archive``. Other datasets ignore it.
    """
    if archive.dataset in {
        "pl.imgw.hydro_daily",
        "pl.imgw.hydro_monthly",
        "pl.imgw.hydro_semiannual",
    }:
        yield from normalize_hydro_archive(archive.dataset, archive.server_path, data)
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
            carry=carry,
        )
    elif archive.dataset == "pl.imgw.meteo_synop_daily":
        yield from normalize_synop_archive(
            archive.server_path,
            data,
            start=archive.period_start,
            end=archive.period_end,
        )
    elif archive.dataset == "cz.chmi.hydro_daily":
        yield from parse_chmi_hydro_daily(data, filename=archive.server_path)
    elif archive.dataset == "cz.chmi.meteo_daily":
        yield from parse_chmi_meteo_daily(data, filename=archive.server_path)
    else:
        raise ObserwatorValidationError(
            message("parsing.no_parser_archive", dataset=archive.dataset)
        )
