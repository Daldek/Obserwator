"""
The names of the files Obserwator names for a user (Nogat DEV-19.21, ECO-083).

A GUI's download and a REST attachment are named
``obserwator_<content>_<qualifiers>.<extension>``: the content in English (``stations``,
``series``, ``analyses``, ``pmaxtp``), the qualifiers each after ``_`` with identifiers
as they are (a dataset key, a station code, an analysis id, a method) and a provider by
its national acronym in lower case (``imgw``, ``chmu``). Both servers, ``obserwator
server`` and ``obserwator gui serve``, take their names from here, so one file has one
name wherever it is downloaded. A unit of the raw root keeps its name in the store
(DEV-19.5), the guides theirs (``AGENTS.md``, ``llms.txt``).
"""

from obserwator.datasets import get_dataset, get_provider

__all__ = [
    "analyses_file_name",
    "pmaxtp_file_name",
    "series_file_name",
    "stations_file_name",
]

_TOOL = "obserwator"


def _name(content: str, *qualifiers: str, extension: str) -> str:
    """``obserwator_<content>[_<qualifier>…].<extension>``."""
    return f"{'_'.join((_TOOL, content, *qualifiers))}.{extension}"


def series_file_name(dataset: str, station: str, extension: str) -> str:
    """
    A station's series: ``obserwator_series_<dataset key>_<station>.<extension>``.

    Parameters
    ----------
    dataset : str
        The dataset's key, slug or alias; the name holds its key.
    station : str
        The station's code.
    extension : str
        ``csv``, ``json`` or ``parquet``.

    Returns
    -------
    str
        For example ``obserwator_series_pl.imgw.meteo_precip_daily_252170380.csv``.
    """
    return _name("series", get_dataset(dataset).key, station, extension=extension)


def stations_file_name(provider: str | None, kind: str | None, extension: str) -> str:
    """
    The stations: ``obserwator_stations[_<provider>][_<kind>].<extension>``.

    Parameters
    ----------
    provider : str or None
        The provider's id; the name holds its national acronym in lower case, the one
        of its dataset keys (``imgw``, ``chmu``). None for every provider.
    kind : str or None
        ``hydro`` or ``meteo``; None for both.
    extension : str
        ``geojson`` or ``csv``.

    Returns
    -------
    str
        For example ``obserwator_stations_imgw_meteo.csv`` or ``obserwator_stations.geojson``.
    """
    acronym = None
    if provider is not None:
        acronym = get_provider(provider).key_prefix.rpartition(".")[2]
    parts = (part for part in (acronym, kind) if part)
    return _name("stations", *parts, extension=extension)


def analyses_file_name(station: str, analysis: str | None, extension: str) -> str:
    """
    A station's stored analyses: ``obserwator_analyses_<station>[_<analysis>].<extension>``.

    Parameters
    ----------
    station : str
        The station's code.
    analysis : str or None
        One analysis id (``flood_frequency.Q``); None for all of them.
    extension : str
        ``json`` or ``csv``.

    Returns
    -------
    str
        For example ``obserwator_analyses_149190310_flood_frequency.Q.json``.
    """
    parts = (station,) if analysis is None else (station, analysis)
    return _name("analyses", *parts, extension=extension)


def pmaxtp_file_name(
    method: str, latitude: float, longitude: float, extension: str
) -> str:
    """
    PMAXTP of a point: ``obserwator_pmaxtp_<method>_<latitude>_<longitude>.<extension>``.

    Parameters
    ----------
    method : str
        ``POT`` or ``AMP``, as it is.
    latitude, longitude : float
        The point, each with four decimals in the name.
    extension : str
        ``csv`` or ``json``.

    Returns
    -------
    str
        For example ``obserwator_pmaxtp_POT_52.4142_17.4586.csv``.
    """
    return _name(
        "pmaxtp", method, f"{latitude:.4f}", f"{longitude:.4f}", extension=extension
    )
