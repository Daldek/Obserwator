"""Canonical dataset and provider descriptors and offline archive enumeration."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date, timedelta
from types import MappingProxyType
from typing import TYPE_CHECKING, ClassVar, Literal
from urllib.parse import quote

from obserwator._environment import PREFIX, config_file
from obserwator._provider_files import (
    CODE_GRAMMAR,
    STATIONS_FILE,
    FileDataset,
    LoadedFiles,
    ProviderFile,
    load_provider_files,
)
from obserwator.attribution import (
    ORIGINS,
    Attribution,
    attribution,
    declare_origin,
    provider_origin,
)
from obserwator.exceptions import ObserwatorValidationError
from obserwator.messages import Message, localize, message
from obserwator.urls import IMGW_PUBLIC_DATA_URL

if TYPE_CHECKING:
    from obserwator.providers import ProviderAdapter

YearsArg = int | str | Iterable[int | str]
"""Years: ``2024``, ``"2020-2023"``, ``"2020,2022"`` or ``[2020, "2022-2023"]``."""

MonthsArg = int | str | Iterable[int | str]
"""Months 1-12: ``3``, ``"3"``, ``"1,2"`` or ``[1, "2"]``."""

STATION_CODE_PATTERN = (
    rf"^([0-9]{{9}}|0-[0-9]{{1,5}}-[0-9]{{1,5}}-[0-9A-Z]{{1,16}}|[1-9][0-9]{{0,5}}"
    rf"|{CODE_GRAMMAR})$"
)
"""
Station code of any provider: nine IMGW-PIB digits, a WIGOS identifier (ČHMÚ), the
``ID`` of a PIG-PIB point (one to six digits without a leading zero, ADR-035) or
``<id>-<code>``: ``GDANSKIEWODY-<no>`` (ADR-034) or that of a provider fed by files
(ADR-033). The grammars are disjoint, so a code names its provider.
"""

DATASET_KEY_PATTERN = r"^[a-z]{2}\.[a-z][a-z0-9]*\.[a-z][a-z0-9_]*$"
"""Dataset key ``<country>.<key prefix>.<name>[_<variant>]`` of any provider (IMGW-20)."""

CATALOG_DATASET = "pl.imgw.stations"
"""Derived dataset key of the IMGW-PIB station catalog ``stations.geojson`` (no descriptor)."""

DATASET_KEY_ALIASES: Mapping[str, str] = MappingProxyType(
    {
        "cz.chmi.hydro_daily": "cz.chmu.hydro_daily",
        "cz.chmi.meteo_daily": "cz.chmu.meteo_daily",
        "cz.chmi.hydro_stations": "cz.chmu.hydro_stations",
        "cz.chmi.meteo_stations": "cz.chmu.meteo_stations",
        "cz.chmi.hydro_now": "cz.chmu.hydro_now",
        "cz.chmi.meteo_now": "cz.chmu.meteo_now",
    }
)
"""
Renamed dataset keys: published key → current key (ADR-001, IMGW-20; ADR-028).

Sidecars keep their raw ``dataset`` forever; a renamed dataset adds its old key
here, and the entry is recorded in the changelog. The entries are the reading of
stored history, not input: `read_meta` resolves them into ``Meta.dataset_key``,
so a raw root written before a rename is read under the current keys, while
`get_dataset` and every option take the current keys only. Since 3.1.0 the ČHMÚ
archive datasets of 3.0.x (``cz.chmi.*``). Unlike ``legacy_alias`` (pre-3.0 input
words), entries are stored keys.
"""

PROVIDER_ID_ALIASES: Mapping[str, str] = MappingProxyType(
    {"CHMI": "CHMU", "IMGW-PIB": "IMGW"}
)
"""
Renamed provider identifiers: published id → current id (ADR-028).

The reading of stored history, as `DATASET_KEY_ALIASES`: `read_meta` gives the
current id as ``Meta.provider`` for the ``provider`` of a sidecar written before the
rename (3.0.x wrote ``CHMI`` and ``IMGW-PIB``); no input takes an old id.
"""

_YEAR = re.compile(r"([0-9]{1,4})(?:-([0-9]{1,4}))?")
_MONTH = re.compile(r"[0-9]{1,2}")
_PARAMS = ("H", "Q", "T")

# ČHMÚ station code: a WIGOS identifier exactly as in the source (ADR-003 D3).
_WIGOS_CODE = r"0-[0-9]{1,5}-[0-9]{1,5}-[0-9A-Z]{1,16}"
# Site of IMGW-PIB's public data: the current-data API (``IMGW_API_URL``) lies below it.
_IMGW_SITE = "https://danepubliczne.imgw.pl/"
# Root of the published files; the warning archives (``arch/``) lie outside the
# measurement data (``IMGW_PUBLIC_DATA_URL``) below it.
_IMGW_DATA = f"{_IMGW_SITE}data/"
# The datastore of the same site: IMGW-PIB's monthly telemetry (``Arch/Telemetria``).
_IMGW_DATASTORE = f"{_IMGW_SITE}datastore/getfiledown/"
# Backend of IMGW-PIB's hydrological service hydro.imgw.pl (its map and station pages).
_HYDRO_BACK = "https://hydro-back.imgw.pl/"
HYDRO_DETAILS = "pl.imgw.hydro_details"
"""Key of the station details of hydro.imgw.pl, an optional source of the IMGW-PIB catalog (ADR-021)."""
METEO_DETAILS = "pl.imgw.meteo_details"
"""Key of the meteo station details of hydro.imgw.pl, an optional source of the IMGW-PIB catalog (ADR-021 erratum of 2026-11-23)."""
CAPTURE_SCOPE = "country_day"
"""``archive_scope`` of a capture dataset: one version holds the answers of a UTC day (ADR-030 D3)."""
CAPTURE_SUFFIX = ".jsonl.gz"
"""
Ending of the file of a capture version, ``<YYYY-MM-DD>.jsonl.gz`` (ADR-030 D3).

The day's answers as gzip-compressed JSON Lines; the slot directory of the file is
``<server_dir>/<YYYY-MM-DD>`` (the name without the ending).
"""
SERIES_TIME_UNITS = ("day", "week", "month", "half_year", "hour")
"""
Time units of the datasets ``series build`` builds (``DatasetDescriptor.time_unit``).

A day, a weekly reading (ČHMÚ's groundwater, at its own date, ADR-032), a month or a
half-year; a dataset of one of them with a parser is a series dataset. An hour is the
unit of the sub-daily series built from the datasets of their ``inputs`` (ADR-031),
one version per calendar month (`monthly_series`).
"""
Kind = Literal["hydro", "meteo", "groundwater"]
"""A station family, the ``kind`` of a dataset, a station list and a catalog station."""
KINDS: tuple[Kind, ...] = ("hydro", "meteo", "groundwater")
"""
The station families in their order: hydrological, meteorological and groundwater.

ČHMÚ's bores and springs are ``groundwater`` (ADR-032); searches, lists and catalogs
give the families in this order.
"""


@dataclass(frozen=True)
class License:
    """
    License and attribution terms of a dataset.

    Attributes
    ----------
    id : str
        License identifier, e.g. ``"IMGW-PIB"`` (IMGW-PIB terms of use) or
        ``"CC-BY-4.0"``.
    attribution : str
        Required attribution formula of the source files (IMGW-PIB ``S``,
        PMAXTP ``PS``, ČHMÚ ``C`` of `obserwator.attribution`); it keeps its
        (Polish) wording in every language, because sidecars and exports
        persist it.
    url : str
        URL of the license or terms of use.
    terms_url : str or None, optional
        URL of the provider's own page on licensing and liability; None when
        the provider has none (sidecars write the field only when set).
    """

    id: str
    attribution: str
    url: str
    terms_url: str | None = None


_CREDENTIAL_STEM = re.compile(r"^[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)*$")


@dataclass(frozen=True)
class ProviderCredential:
    """
    The API key a provider's requests need (Nogat plan 2026-11-20, P3).

    The key comes from ``OBSERWATOR_<STEM>_API_KEY`` or the file named by
    ``OBSERWATOR_<STEM>_API_KEY_FILE``, from the environment or ``.env`` only, never
    from ``nogat.toml``, as the GUI's admin key (ADR-020); `obserwator.config.provider_key`
    reads it. No provider of 3.2.0 needs one.

    Attributes
    ----------
    stem : str
        Upper-case name between ``OBSERWATOR_`` and ``_API_KEY``, e.g.
        ``"GDANSKIE_WODY"``.
    variable : str
        The variable of the key, ``OBSERWATOR_<STEM>_API_KEY`` (derived).
    file_variable : str
        The variable naming the key's file, ``OBSERWATOR_<STEM>_API_KEY_FILE``
        (derived).

    Raises
    ------
    ValueError
        If ``stem`` is not upper-case letters, digits and single underscores.
    """

    stem: str
    variable: str = field(init=False)
    file_variable: str = field(init=False)

    def __post_init__(self) -> None:
        """Check the stem and derive the two variables."""
        if not _CREDENTIAL_STEM.fullmatch(self.stem):
            raise ValueError(f"Invalid credential stem {self.stem!r}")
        object.__setattr__(self, "variable", f"{PREFIX}{self.stem}_API_KEY")
        object.__setattr__(self, "file_variable", f"{self.variable}_FILE")


@dataclass(frozen=True)
class ProviderDescriptor:
    """
    Registry entry describing a data provider (ADR-003 D1).

    Attributes
    ----------
    id : str
        Value of the ``provider`` fields, ``"IMGW"`` or ``"CHMU"``.
    short_name : str
        Name shown in texts, ``"IMGW-PIB"`` or ``"ČHMÚ"``.
    name : str
        Full name of the institution.
    country : str
        ISO 3166-1 alpha-2 country code, ``"PL"`` or ``"CZ"``.
    key_prefix : str
        Prefix of the provider's dataset keys, ``"pl.imgw"`` or ``"cz.chmu"``.
    base_url : str
        Base URL of the ``server_path`` of the provider's files (with the
        trailing slash).
    license : License
        License and attribution of the provider's data.
    processed_attribution : str
        Formula marking processed forms (series, catalog, exports), without
        a final full stop (IMGW-PIB ``P``, ČHMÚ ``CP``).
    notice : str
        Text of the ``license_terms`` notice that follows the attribution (a
        catalog message): the IMGW-PIB terms notice with its terms, or the
        CC BY 4.0 note of ČHMÚ.
    station_code_pattern : str
        Regular expression of the provider's station codes.
    datasets : tuple of str
        Keys of the provider's datasets in registry order.
    credential : ProviderCredential or None, optional
        The API key the provider's requests need (P3); None for a provider of open
        data (IMGW-PIB, ČHMÚ). Written to the ``obserwator-provider/1`` document only
        when set (an optional field, ECO-085).
    """

    SCHEMA: ClassVar[str] = "obserwator-provider/1"

    id: str
    short_name: str
    name: str
    country: str
    key_prefix: str
    base_url: str
    license: License
    processed_attribution: str
    notice: str
    station_code_pattern: str
    datasets: tuple[str, ...]
    credential: ProviderCredential | None = field(
        default=None, metadata={"omit_none": True}
    )

    def license_notice(self, lines: Attribution | None = None) -> Message:
        """
        Text of the ``license_terms`` notice of data of this provider.

        Parameters
        ----------
        lines : Attribution or None, optional
            The lines the written or returned data carry (`obserwator.attribution`):
            the processed lines of a derived form, the PMAXTP lines of a cell;
            the provider's lines of a verbatim copy by default.

        Returns
        -------
        Message
            The attribution lines followed by the terms notice of IMGW-PIB
            data or the provider's notice.
        """
        if lines is None:
            lines = attribution(provider_origin(self.id), processed=False)
        notice = (
            message("datasets.provider_notice_imgw", terms=" ".join(lines.terms_notice))
            if lines.terms_notice
            else self.notice
        )
        return message(
            "datasets.license_notice",
            attribution=". ".join(lines.attribution),
            notice=notice,
        )

    @property
    def adapter(self) -> ProviderAdapter:
        """
        The provider's adapter: what Obserwator does with it beyond this entry (ADR-029).

        Returns
        -------
        ProviderAdapter
            The adapter of ``obserwator.providers`` for `id`.
        """
        # The adapters import this registry, so they are reached at call time.
        from obserwator.providers import adapter

        return adapter(self.id)

    @property
    def acronym(self) -> str:
        """
        The provider's acronym in identifiers and file names (ECO-082, ADR-028).

        Returns
        -------
        str
            `id` in lower case: the first part of its slugs and of its store
            directories (``imgw``, ``chmu``).
        """
        return self.id.lower()

    @property
    def source_class(self) -> Literal["nmhs", "other"]:
        """
        Who operates the provider's network (Nogat plan 2026-11-20, P11).

        Returns
        -------
        {"nmhs", "other"}
            ``nmhs`` for a national meteorological and hydrological service
            (IMGW-PIB, ČHMÚ), ``other`` for every other operator, a provider fed by
            files among them (ADR-033); its adapter's ``source_class``. A property,
            so the ``obserwator-provider/1`` document is unchanged.
        """
        return self.adapter.source_class


@dataclass(frozen=True)
class DatasetDescriptor:
    """
    Registry entry describing a dataset of a provider.

    Attributes
    ----------
    key : str
        Full namespaced dataset key, e.g. ``"pl.imgw.hydro_daily"``.
    slug : str
        Short name used only in store directory names: the provider's acronym and
        the last part of the key, e.g. ``"imgw_hydro_daily"`` (ADR-028).
    kind : {"hydro", "meteo", "groundwater"} or None
        Data family (``groundwater``: ČHMÚ's bores and springs, ADR-032); None for
        PMAXTP.
    title : str
        English title of the dataset (a catalog message), e.g. ``"Daily
        hydrological data"``; ``localize(title, "pl")`` is the Polish title.
    server_dir : str or None
        Directory on the provider's server, relative to its ``base_url``,
        e.g. ``"dane_hydrologiczne/dobowe"``; None for PMAXTP.
    parser : str or None
        Name of the registered public parser function; None for PMAXTP and
        download-only datasets.
    variables : Mapping of str to str
        Variable codes mapped to their units, e.g. ``{"H": "cm"}``; empty for
        station lists and download-only datasets.
    time_unit : str
        Time resolution of a record: ``"day"``, ``"week"`` (a weekly reading at its
        own date, ADR-032), ``"month"``, ``"half_year"``, ``"term"`` (the
        observation times), ``"hour"`` or ``"ten_minutes"``; or the auxiliary
        source type: ``"station_list"``, ``"cell"`` (PMAXTP), ``"snapshot"`` (an
        answer of current data that gives every station's latest values at their
        own times, ADR-030) or ``"statistics"`` (a station's published statistics
        by period of the year, ADR-032).
    year_type : {"hydrological", "calendar", "none"}
        Year numbering of the archives.
    first_year : int or None
        Lowest year accepted by the offline generator (there is no upper
        bound); None for station lists, PMAXTP and files without a year.
    update_signal : {"http", "listing", "none"}
        Freshness signal: HTTP headers of the file, the server listing of its
        directory, or none.
    license : License
        License and attribution of the data.
    legacy_alias : str or None
        Pre-3.0 interval path accepted as input, e.g. ``"hydro/dobowe"``.
    in_store : bool
        Whether the dataset can be stored in the versioned store; False for
        datasets that can only be downloaded.
    provider : str, optional
        ``ProviderDescriptor.id`` of the dataset's provider.
    archive_scope : str, optional
        What one source file covers: ``"country"`` the whole country,
        ``"station_year"`` one station and year, ``"station_month"`` one station and
        calendar month, ``"station"`` one station (ADR-032), ``"station_element"``
        the whole history of one station and element, ``"station_element_month"`` one
        station, element and calendar month (Gdańskie Wody's answers of the month's
        days gathered into one file, ADR-034), ``"country_day"`` the answers of one
        UTC day for the whole network (a capture version, ADR-030); of a series built
        from ``inputs``, the scope of their files.
    variable_notes : Mapping of str to str, optional
        Convention of each variable (English catalog messages), e.g. the day of
        a sum; the series metadata keeps the English text.
    measurement_fields : tuple of {"quality", "source_flag"}, optional
        Additional ``Measurement`` fields the dataset fills.
    content_form : str or None, optional
        Key of ``CONTENT_FORMS`` (``obserwator.store.content``) of the
        dataset's files; None when only the bytes identify the content.
    volatile_fields : tuple of str, optional
        Volatile fields of ``content_form``; empty without a form.
    base_url : str or None, optional
        Base URL of the dataset's server paths when it is not the provider's
        ``base_url`` (the current-data API of IMGW-PIB, archived as the station
        locations of its catalog, and hydro.imgw.pl's backend); None for the
        provider's.
    kept_fields : tuple of str, optional
        Fields of each station that the store keeps of an answer that also
        carries operational data (IMGW-PIB's current-data API: measurements and
        their times; hydro.imgw.pl's station details: water states): the stored
        file holds the stations with these fields only, never the rest
        (ADR-015 D5, ADR-021). A dotted name reaches into an object of the
        answer (``"status.alarmValue"``), the first field is the station code;
        empty keeps the provider's bytes verbatim.
    tier : {"verified", "telemetry", "operational"}, optional
        What the data are, set here and never inferred from their values
        (ADR-030, Nogat ECO-084): ``"verified"`` a published archive or a
        validated set (the default, every dataset of 3.1.0), ``"telemetry"``
        IMGW-PIB's monthly telemetry, ``"operational"`` what a source gives as
        current or unverified data. A sub-daily series has the lowest tier of its
        ``inputs`` (ADR-031): it may hold operational hours, and each of its
        points carries its own tier.
    inputs : tuple of str or None, optional
        The datasets a series is built from, when it has no files of its own: of a
        sub-daily series (ADR-031), highest tier first, a point of one replacing that
        of a later one; of Gdańskie Wody's daily series (ADR-034), its month files,
        whose daily values its parser gives. The provider's adapter says which of
        their files a series reads (`ProviderAdapter.series_reads`). None for every
        other dataset (an optional field of ``obserwator-dataset/1``, written only
        when set).
    """

    SCHEMA: ClassVar[str] = "obserwator-dataset/1"

    key: str
    slug: str
    kind: Kind | None
    title: str
    server_dir: str | None
    parser: str | None
    variables: Mapping[str, str]
    time_unit: Literal[
        "day",
        "week",
        "month",
        "half_year",
        "term",
        "hour",
        "ten_minutes",
        "station_list",
        "cell",
        "snapshot",
        "statistics",
    ]
    year_type: Literal["hydrological", "calendar", "none"]
    first_year: int | None
    update_signal: Literal["http", "listing", "none"]
    license: License
    legacy_alias: str | None
    in_store: bool
    provider: str = "IMGW"
    archive_scope: Literal[
        "country",
        "station_year",
        "station_month",
        "station",
        "station_element",
        "station_element_month",
        "country_day",
    ] = "country"
    variable_notes: Mapping[str, str] = field(default_factory=dict)
    measurement_fields: tuple[Literal["quality", "source_flag"], ...] = ()
    content_form: str | None = None
    volatile_fields: tuple[str, ...] = ()
    base_url: str | None = None
    kept_fields: tuple[str, ...] = ()
    tier: Literal["verified", "telemetry", "operational"] = "verified"
    inputs: tuple[str, ...] | None = field(default=None, metadata={"omit_none": True})


@dataclass(frozen=True)
class ArchiveFile:
    """
    Single physical source file (ZIP archive, CSV or JSON file).

    Attributes
    ----------
    dataset : str
        Full key of the dataset the file belongs to.
    server_path : str
        File path relative to the provider's ``base_url``.
    url : str
        Full download URL.
    year : int or None
        Archive year (hydrological or calendar per ``year_type``); for a
        meteorological monthly archive covering a multi-year folder, the
        first year of the folder; None for station lists and files without
        a year (ČHMÚ meteorological files cover the station's history).
    month : int or None
        Month of a monthly file (for hydrological data 1 = November of the
        previous year, 12 = October); None for yearly files.
    param : str or None
        Parameter of a semi-annual archive (``"H"``, ``"Q"`` or ``"T"``) or
        the element of a ČHMÚ meteorological file (``"SRA"``, ``"T"``,
        ``"TMA"``, ``"TMI"``, ``"SCE"``, ``"SNO"``), None otherwise.
    year_type : {"hydrological", "calendar", "none"}
        Year numbering of ``year``.
    period_start : date or None
        First calendar day covered by the file; None for station lists and
        files without a year.
    period_end : date or None
        Last calendar day covered by the file; None for station lists and
        files without a year.
    station_code : str or None, optional
        Station of a per-station file (WIGOS identifier), None for files
        covering the whole country.
    """

    SCHEMA: ClassVar[str] = "obserwator-archive-file/1"

    dataset: str
    server_path: str
    url: str
    year: int | None
    month: int | None
    param: str | None
    year_type: Literal["hydrological", "calendar", "none"]
    period_start: date | None
    period_end: date | None
    station_code: str | None = None


_LICENSE = License(
    "IMGW-PIB",
    message("legal.imgw_attribution"),
    "https://danepubliczne.imgw.pl/regulations",
)
# The data of hydro.imgw.pl are under the terms of that service (Nogat DEV-20.7, RH).
_HYDRO_LICENSE = License(
    "IMGW-PIB",
    message("legal.imgw_attribution"),
    "https://hydro.imgw.pl/#/regulamin",
)
# PMAXTP has terms of its own (the project page), with its own formulas.
_PMAXTP_LICENSE = License(
    "IMGW-PIB",
    message("legal.pmaxtp_attribution"),
    "https://klimat.imgw.pl/opady-maksymalne",
)
_CHMU_LICENSE = License(
    "CC-BY-4.0",
    message("legal.chmu_attribution"),
    "https://creativecommons.org/licenses/by/4.0/",
    "https://www.chmi.cz/vylou%C4%8Den%C3%AD-odpov%C4%9Bdnosti",
)
# Canonical form of the ČHMÚ JSON files (envelope fields regenerated on every
# publication); equal to obserwator.store.content.CONTENT_FORMS["chmu-json/1"].
_CHMU_JSON = "chmu-json/1"
_CHMU_VOLATILE = ("zaznamID", "datumVytvoreni")
# Variables of ČHMÚ's groundwater series (ADR-032): the level of a bore in metres above
# sea level (plan P7: never H, the stage above a gauge zero in cm), the yield of a
# spring and the water temperature.
_GROUNDWATER_VARIABLES = {"H_asl": "m", "spring_yield": "l/s", "T": "degC"}

_HYDRO_STATS = {
    f"{v}_{stat}": unit
    for v, unit in (("H", "cm"), ("Q", "m3/s"), ("T", "degC"))
    for stat in ("min", "mean", "max")
}
# Variable definitions of IMGW-PIB's format descriptions (danepubliczne.imgw.pl,
# CODZ, MIES and POLR_publiczne_format.txt, k_d_format.txt, o_d_format.txt): the
# fields of the files, the extremum indicators and what a missing value means.
_IMGW_STATISTICS = {
    "H_min": message("datasets.stat_imgw_h_min"),
    "H_mean": message("datasets.stat_imgw_h_mean"),
    "H_max": message("datasets.stat_imgw_h_max"),
    "Q_min": message("datasets.stat_imgw_q_min"),
    "Q_mean": message("datasets.stat_imgw_q_mean"),
    "Q_max": message("datasets.stat_imgw_q_max"),
    "T_min": message("datasets.stat_imgw_t_min"),
    "T_mean": message("datasets.stat_imgw_t_mean"),
    "T_max": message("datasets.stat_imgw_t_max"),
}
# MCWSKEX and PLWSKEX: 1 minimum, 2 mean, 3 maximum; the monthly value fields.
_IMGW_EXTREMA = {"min": 1, "mean": 2, "max": 3}
_IMGW_MONTHLY_FIELDS = {"H": "MCSTAN", "Q": "MCPRZP", "T": "MCPTMP"}
_IMGW_MONTHLY_NOTES = {
    name: message(
        "datasets.note_imgw_hydro_monthly",
        statistic=statistic,
        field=_IMGW_MONTHLY_FIELDS[name[0]],
        code=_IMGW_EXTREMA[name[2:]],
    )
    for name, statistic in _IMGW_STATISTICS.items()
}
_IMGW_SEMIANNUAL_NOTES = {
    name: message(
        "datasets.note_imgw_hydro_semiannual",
        statistic=statistic,
        quantity=name[0],
        code=_IMGW_EXTREMA[name[2:]],
    )
    for name, statistic in _IMGW_STATISTICS.items()
}
_IMGW_SNOW_COVER = message("datasets.note_imgw_snow_cover")
# Gdańskie Wody (ADR-034): the variables of its quantities (`obserwator._parsing.
# gdanskiewody.QUANTITIES`), with the units of the provider's public tables (checked
# 2026-11-25); the water level in m a.s.l. is H_asl (plan P7). A day has no direction of
# the wind, and its air temperature is the mean of the provider's day.
_GDANSKIEWODY = "GDANSKIEWODY"
_GDANSKIEWODY_STATIONS = "pl.gdanskiewody.station_list"
_GDANSKIEWODY_MEASUREMENTS = "pl.gdanskiewody.measurements"
_GDANSKIEWODY_FIRST_YEAR = 2005
_GDANSKIEWODY_CODE = r"GDANSKIEWODY-[1-9][0-9]{0,2}"
_GDANSKIEWODY_LICENSE = License(
    "gdanskiewody-terms-unknown",
    message("legal.gdanskiewody_attribution"),
    "https://pomiary.gdanskiewody.pl/account/signup",
)
_GDANSKIEWODY_HYDRO = {"H_asl": "m", "Q": "m3/s", "T": "degC"}
_GDANSKIEWODY_METEO_HOURLY = {
    "P": "mm",
    "Tair": "degC",
    "wind_speed": "m/s",
    "wind_direction": "deg",
    "pressure": "hPa",
    "humidity": "%",
    "irradiance": "W/m2",
}
_GDANSKIEWODY_METEO_DAILY = {
    "P": "mm",
    "Tmean": "degC",
    "wind_speed": "m/s",
    "pressure": "hPa",
    "humidity": "%",
    "irradiance": "W/m2",
}
# PIG-PIB (ADR-035): the groundwater monitoring of the state geological service
# (Monitoring Wód Podziemnych) of cbdgmapa.pgi.gov.pl's ArcGIS services
# ``hydrogeologia/mwp`` (the points and the MWP database) and ``hydrogeologia/mwp_auto``
# (the automatic measurements), CC BY 4.0 by dane.gov.pl's dataset 170. Its W line has
# a period and a date filled per product (`obserwator.attribution`); the license's
# formula keeps the placeholders of the standard's table.
_PIG = "PIG"
_PIG_STATIONS = "pl.pig.groundwater_stations"
_PIG_READINGS = "pl.pig.groundwater_readings"
_PIG_OPERATIONAL = "pl.pig.groundwater_operational"
_PIG_CODE = r"[1-9][0-9]{0,5}"
# The canonical form of a capture of ArcGIS pages: the rows without OBJECTID and paging
# (`obserwator.store.content.CONTENT_FORMS["pig-json/1"]`).
_PIG_JSON = "pig-json/1"
_PIG_VOLATILE = ("OBJECTID",)
_PIG_LICENSE = License(
    "CC-BY-4.0",
    message("legal.pig_attribution", period="<period>", date="<date>"),
    "https://creativecommons.org/licenses/by/4.0/",
    "https://www.pgi.gov.pl/rejestry-i-bazy-danych-geologicznych/zasady-korzystania-z-isp.html",
)
_PIG_READING_NOTES = {
    "depth_to_water": message("datasets.note_pig_depth_to_water"),
    "H_asl": message("datasets.note_pig_h_asl"),
    "spring_yield": message("datasets.note_pig_spring_yield"),
}
_PIG_HOURLY_NOTES = {
    "depth_to_water": message("datasets.note_pig_hourly_depth"),
    "H_asl": message("datasets.note_pig_hourly_h_asl"),
}


def _gdanskiewody_series(
    kind: Kind,
    time_unit: Literal["hour", "day"],
    variables: Mapping[str, str],
    title: Message,
) -> DatasetDescriptor:
    """
    A series of Gdańskie Wody, built from the stored month files (ADR-034).

    The hourly series (ADR-031) holds each hour the provider labels with its start;
    the daily one the sum (``P``) or the mean of the 24 hours of the provider's day,
    06:00 to 05:59 UTC (P5, `obserwator._parsing.gdanskiewody.daily_records`).
    """
    daily = time_unit == "day"
    notes = {
        name: message(
            (
                "datasets.note_gdanskiewody_daily_sum"
                if name == "P"
                else "datasets.note_gdanskiewody_daily_mean"
            )
            if daily
            else (
                "datasets.note_gdanskiewody_h_asl"
                if name == "H_asl"
                else "datasets.note_gdanskiewody_hourly"
            )
        )
        for name in variables
    }
    return DatasetDescriptor(
        key=f"pl.gdanskiewody.{kind}_{'daily' if daily else 'hourly'}",
        slug=f"gdanskiewody_{kind}_{'daily' if daily else 'hourly'}",
        kind=kind,
        title=title,
        server_dir=None,
        parser="parse_gdanskiewody_month" if daily else None,
        variables=dict(variables),
        time_unit=time_unit,
        year_type="calendar",
        first_year=_GDANSKIEWODY_FIRST_YEAR,
        update_signal="none",
        license=_GDANSKIEWODY_LICENSE,
        legacy_alias=None,
        in_store=True,
        provider=_GDANSKIEWODY,
        archive_scope="station_element_month",
        variable_notes=notes,
        tier="operational",
        inputs=(_GDANSKIEWODY_MEASUREMENTS,),
    )


_DATASETS: tuple[DatasetDescriptor, ...] = (
    DatasetDescriptor(
        key="pl.imgw.hydro_daily",
        slug="imgw_hydro_daily",
        kind="hydro",
        title=message("datasets.title_hydro_daily"),
        server_dir="dane_hydrologiczne/dobowe",
        parser="parse_daily_csv",
        variables={"H": "cm", "Q": "m3/s", "T": "degC"},
        time_unit="day",
        year_type="hydrological",
        first_year=1951,
        update_signal="http",
        license=_LICENSE,
        legacy_alias="hydro/dobowe",
        in_store=True,
        variable_notes={
            "H": message("datasets.note_imgw_hydro_daily_h"),
            "Q": message("datasets.note_imgw_hydro_daily_q"),
            "T": message("datasets.note_imgw_hydro_daily_t"),
        },
    ),
    DatasetDescriptor(
        key="pl.imgw.hydro_monthly",
        slug="imgw_hydro_monthly",
        kind="hydro",
        title=message("datasets.title_hydro_monthly"),
        server_dir="dane_hydrologiczne/miesieczne",
        parser="parse_monthly_csv",
        variables=_HYDRO_STATS,
        time_unit="month",
        year_type="hydrological",
        first_year=1951,
        update_signal="http",
        license=_LICENSE,
        legacy_alias="hydro/miesieczne",
        in_store=True,
        variable_notes=_IMGW_MONTHLY_NOTES,
    ),
    DatasetDescriptor(
        key="pl.imgw.hydro_semiannual",
        slug="imgw_hydro_semiannual",
        kind="hydro",
        title=message("datasets.title_hydro_semiannual"),
        server_dir="dane_hydrologiczne/polroczne_i_roczne",
        parser="parse_semi_annual_csv",
        variables=_HYDRO_STATS,
        time_unit="half_year",
        year_type="hydrological",
        first_year=1951,
        update_signal="http",
        license=_LICENSE,
        legacy_alias="hydro/polroczne_i_roczne",
        in_store=True,
        variable_notes=_IMGW_SEMIANNUAL_NOTES,
    ),
    DatasetDescriptor(
        key="pl.imgw.meteo_climate_daily",
        slug="imgw_meteo_climate_daily",
        kind="meteo",
        title=message("datasets.title_meteo_climate_daily"),
        server_dir="dane_meteorologiczne/dobowe/klimat",
        parser="parse_meteo_climate_daily",
        variables={
            "Tmax": "degC",
            "Tmin": "degC",
            "Tmean": "degC",
            "Tground": "degC",
            "P": "mm",
            "snow_cover": "cm",
        },
        time_unit="day",
        year_type="calendar",
        first_year=1951,
        update_signal="http",
        license=_LICENSE,
        legacy_alias="meteo/dobowe/klimat",
        in_store=True,
        variable_notes={
            "Tmax": message("datasets.note_imgw_tmax"),
            "Tmin": message("datasets.note_imgw_tmin"),
            "Tmean": message("datasets.note_imgw_tmean"),
            "Tground": message("datasets.note_imgw_tground"),
            "P": message("datasets.note_imgw_p"),
            "snow_cover": _IMGW_SNOW_COVER,
        },
    ),
    DatasetDescriptor(
        key="pl.imgw.meteo_precip_daily",
        slug="imgw_meteo_precip_daily",
        kind="meteo",
        title=message("datasets.title_meteo_precip_daily"),
        server_dir="dane_meteorologiczne/dobowe/opad",
        parser="parse_meteo_precip_daily",
        variables={"P": "mm", "snow_cover": "cm", "fresh_snow": "cm"},
        time_unit="day",
        year_type="calendar",
        first_year=1950,
        update_signal="http",
        license=_LICENSE,
        legacy_alias="meteo/dobowe/opad",
        in_store=True,
        variable_notes={
            "P": message("datasets.note_imgw_precip_p"),
            "snow_cover": _IMGW_SNOW_COVER,
            "fresh_snow": message("datasets.note_imgw_fresh_snow"),
        },
    ),
    # One archive per station and folder (five years until 2000, then a year),
    # named by the station's number; the running year is published as monthly
    # files of the whole country (the store finds both in the folder index).
    DatasetDescriptor(
        key="pl.imgw.meteo_synop_daily",
        slug="imgw_meteo_synop_daily",
        kind="meteo",
        title=message("datasets.title_meteo_synop_daily"),
        server_dir="dane_meteorologiczne/dobowe/synop",
        parser="parse_meteo_synop_daily",
        variables={
            "Tmax": "degC",
            "Tmin": "degC",
            "Tmean": "degC",
            "Tground": "degC",
            "P": "mm",
            "snow_cover": "cm",
            "snow_water_equivalent": "mm/cm",
            "sunshine": "h",
            "rain_duration": "h",
            "snowfall_duration": "h",
            "sleet_duration": "h",
            "hail_duration": "h",
            "fog_duration": "h",
            "mist_duration": "h",
            "rime_duration": "h",
            "glaze_duration": "h",
            "drifting_snow_duration": "h",
            "blowing_snow_duration": "h",
            "haze_duration": "h",
            "wind_10_duration": "h",
            "wind_15_duration": "h",
            "thunderstorm_duration": "h",
            "dew_duration": "h",
            "hoarfrost_duration": "h",
            "snow_cover_occurrence": "0/1",
            "lightning_occurrence": "0/1",
            "isotherm_lower": "cm",
            "isotherm_upper": "cm",
            "actinometry": "J/cm2",
            "cloud_cover": "okta",
            "wind_speed": "m/s",
            "vapour_pressure": "hPa",
            "humidity": "%",
            "pressure_station": "hPa",
            "pressure_sea": "hPa",
            "P_day": "mm",
            "P_night": "mm",
        },
        time_unit="day",
        year_type="calendar",
        first_year=1966,
        update_signal="http",
        license=_LICENSE,
        legacy_alias="meteo/dobowe/synop",
        in_store=True,
        archive_scope="station_year",
        variable_notes={
            "Tmax": message("datasets.note_imgw_tmax"),
            "Tmin": message("datasets.note_imgw_tmin"),
            "Tmean": message("datasets.note_imgw_tmean"),
            "Tground": message("datasets.note_imgw_tground"),
            "P": message("datasets.note_imgw_p"),
            "snow_cover": _IMGW_SNOW_COVER,
            "snow_water_equivalent": message("datasets.note_imgw_snow_water"),
            "sunshine": message("datasets.note_imgw_sunshine"),
            "rain_duration": message("datasets.note_imgw_rain_duration"),
            "snowfall_duration": message("datasets.note_imgw_snowfall_duration"),
            "sleet_duration": message("datasets.note_imgw_sleet_duration"),
            "hail_duration": message("datasets.note_imgw_hail_duration"),
            "fog_duration": message("datasets.note_imgw_fog_duration"),
            "mist_duration": message("datasets.note_imgw_mist_duration"),
            "rime_duration": message("datasets.note_imgw_rime_duration"),
            "glaze_duration": message("datasets.note_imgw_glaze_duration"),
            "drifting_snow_duration": message("datasets.note_imgw_drifting_snow"),
            "blowing_snow_duration": message("datasets.note_imgw_blowing_snow"),
            "haze_duration": message("datasets.note_imgw_haze_duration"),
            "wind_10_duration": message("datasets.note_imgw_wind_10_duration"),
            "wind_15_duration": message("datasets.note_imgw_wind_15_duration"),
            "thunderstorm_duration": message("datasets.note_imgw_thunderstorm"),
            "dew_duration": message("datasets.note_imgw_dew_duration"),
            "hoarfrost_duration": message("datasets.note_imgw_hoarfrost_duration"),
            "snow_cover_occurrence": message("datasets.note_imgw_snow_cover_day"),
            "lightning_occurrence": message("datasets.note_imgw_lightning_day"),
            "isotherm_lower": message("datasets.note_imgw_isotherm_lower"),
            "isotherm_upper": message("datasets.note_imgw_isotherm_upper"),
            "actinometry": message("datasets.note_imgw_actinometry"),
            "cloud_cover": message("datasets.note_imgw_cloud_cover"),
            "wind_speed": message("datasets.note_imgw_wind_speed"),
            "vapour_pressure": message("datasets.note_imgw_vapour_pressure"),
            "humidity": message("datasets.note_imgw_humidity"),
            "pressure_station": message("datasets.note_imgw_pressure_station"),
            "pressure_sea": message("datasets.note_imgw_pressure_sea"),
            "P_day": message("datasets.note_imgw_p_day"),
            "P_night": message("datasets.note_imgw_p_night"),
        },
    ),
    DatasetDescriptor(
        key="pl.imgw.hydro_stations",
        slug="imgw_hydro_stations",
        kind="hydro",
        title=message("datasets.title_hydro_stations"),
        server_dir="dane_hydrologiczne",
        parser="parse_stations_csv",
        variables={},
        time_unit="station_list",
        year_type="none",
        first_year=None,
        update_signal="http",
        license=_LICENSE,
        legacy_alias=None,
        in_store=True,
    ),
    DatasetDescriptor(
        key="pl.imgw.meteo_stations",
        slug="imgw_meteo_stations",
        kind="meteo",
        title=message("datasets.title_meteo_stations"),
        server_dir="dane_meteorologiczne",
        parser="parse_stations_csv",
        variables={},
        time_unit="station_list",
        year_type="none",
        first_year=None,
        update_signal="http",
        license=_LICENSE,
        legacy_alias=None,
        in_store=True,
    ),
    # The current-data API answers, archived as the station locations of the
    # IMGW-PIB catalog (ADR-015 D2): no file name of their own and no HTTP signal.
    # They also carry operational data, which are never archived: the store keeps
    # each station's code, name, river and coordinates only (ADR-015 D5).
    DatasetDescriptor(
        key="pl.imgw.hydro_now",
        slug="imgw_hydro_now",
        kind="hydro",
        title=message("datasets.title_hydro_now"),
        server_dir="api/data",
        parser=None,
        variables={},
        time_unit="station_list",
        year_type="none",
        first_year=None,
        update_signal="none",
        license=_LICENSE,
        legacy_alias=None,
        in_store=True,
        base_url=_IMGW_SITE,
        kept_fields=("id_stacji", "stacja", "rzeka", "lon", "lat"),
    ),
    DatasetDescriptor(
        key="pl.imgw.meteo_now",
        slug="imgw_meteo_now",
        kind="meteo",
        title=message("datasets.title_meteo_now"),
        server_dir="api/data",
        parser=None,
        variables={},
        time_unit="station_list",
        year_type="none",
        first_year=None,
        update_signal="none",
        license=_LICENSE,
        legacy_alias=None,
        in_store=True,
        base_url=_IMGW_SITE,
        kept_fields=("kod_stacji", "nazwa_stacji", "lon", "lat"),
    ),
    # The station details of hydro.imgw.pl (ADR-021): its backend's answer for each
    # station of its map, one request per station, gathered into one file. The store
    # keeps each station's reference data only (warning and alarm levels, absolute
    # extremes, gauge zero, river kilometre, catchment area, year of establishment,
    # province and district), never its water states (ADR-015 D5, Nogat DEV-20.8).
    DatasetDescriptor(
        key=HYDRO_DETAILS,
        slug="imgw_hydro_details",
        kind="hydro",
        title=message("datasets.title_hydro_details"),
        server_dir="station/hydro",
        parser=None,
        variables={},
        time_unit="station_list",
        year_type="none",
        first_year=None,
        update_signal="none",
        license=_HYDRO_LICENSE,
        legacy_alias=None,
        in_store=True,
        base_url=_HYDRO_BACK,
        kept_fields=(
            "id",
            "properties.maximumStateValue",
            "properties.maximumStateDate",
            "properties.minimumStateValue",
            "properties.minimumStateDate",
            "properties.district",
            "properties.waterGaugeZeroOrdinate",
            "properties.waterGaugeZeroOrdinateReferrenceSystem",
            "properties.yearOfEstablishment",
            "status.riverCourseKm",
            "status.catchmentArea",
            "status.province",
            "status.alarmValue",
            "status.warningValue",
        ),
    ),
    # The meteorological station pages of hydro.imgw.pl, gathered as the hydrological
    # ones above: of each station only its code, coordinates and elevation, never its
    # precipitation, sums or records (ADR-015 D5, ADR-021 erratum of 2026-11-23).
    DatasetDescriptor(
        key=METEO_DETAILS,
        slug="imgw_meteo_details",
        kind="meteo",
        title=message("datasets.title_meteo_details"),
        server_dir="station/meteo",
        parser=None,
        variables={},
        time_unit="station_list",
        year_type="none",
        first_year=None,
        update_signal="none",
        license=_HYDRO_LICENSE,
        legacy_alias=None,
        in_store=True,
        base_url=_HYDRO_BACK,
        kept_fields=("id", "coordinates.x", "coordinates.y", "properties.altitude"),
    ),
    DatasetDescriptor(
        key="pl.imgw.pmaxtp",
        slug="imgw_pmaxtp",
        kind=None,
        title=message("datasets.title_pmaxtp"),
        server_dir=None,
        parser=None,
        variables={"ks": "mm", "sg": "mm", "rb": "mm"},
        time_unit="cell",
        year_type="none",
        first_year=None,
        update_signal="none",
        license=_PMAXTP_LICENSE,
        legacy_alias=None,
        in_store=True,
    ),
    # The captures of the sources of current data that answer for every station in
    # one request (ADR-030 D3, D4): every answer the hourly poll (``current poll``),
    # the GUI and the ``current`` commands receive, spooled per UTC day and sealed by
    # ``store sync`` into one version a day (``archive:<key>:<YYYY-MM-DD>.jsonl.gz``).
    DatasetDescriptor(
        key="pl.imgw.hydro_current",
        slug="imgw_hydro_current",
        kind="hydro",
        title=message("datasets.title_hydro_current"),
        server_dir="api/data/hydro",
        parser=None,
        variables={},
        time_unit="snapshot",
        year_type="calendar",
        first_year=None,
        update_signal="none",
        license=_LICENSE,
        legacy_alias=None,
        in_store=True,
        archive_scope="country_day",
        base_url=_IMGW_SITE,
        tier="operational",
    ),
    DatasetDescriptor(
        key="pl.imgw.meteo_current",
        slug="imgw_meteo_current",
        kind="meteo",
        title=message("datasets.title_meteo_current"),
        server_dir="api/data/meteo",
        parser=None,
        variables={},
        time_unit="snapshot",
        year_type="calendar",
        first_year=None,
        update_signal="none",
        license=_LICENSE,
        legacy_alias=None,
        in_store=True,
        archive_scope="country_day",
        base_url=_IMGW_SITE,
        tier="operational",
    ),
    DatasetDescriptor(
        key="pl.imgw.meteo_synop_current",
        slug="imgw_meteo_synop_current",
        kind="meteo",
        title=message("datasets.title_meteo_synop_current"),
        server_dir="api/data/synop",
        parser=None,
        variables={},
        time_unit="snapshot",
        year_type="calendar",
        first_year=None,
        update_signal="none",
        license=_LICENSE,
        legacy_alias=None,
        in_store=True,
        archive_scope="country_day",
        base_url=_IMGW_SITE,
        tier="operational",
    ),
    DatasetDescriptor(
        key="pl.imgw.warnings_hydro_current",
        slug="imgw_warnings_hydro_current",
        kind="hydro",
        title=message("datasets.title_warnings_hydro_current"),
        server_dir="api/data/warningshydro",
        parser=None,
        variables={},
        time_unit="snapshot",
        year_type="calendar",
        first_year=None,
        update_signal="none",
        license=_LICENSE,
        legacy_alias=None,
        in_store=True,
        archive_scope="country_day",
        base_url=_IMGW_SITE,
        tier="operational",
    ),
    DatasetDescriptor(
        key="pl.imgw.warnings_meteo_current",
        slug="imgw_warnings_meteo_current",
        kind="meteo",
        title=message("datasets.title_warnings_meteo_current"),
        server_dir="api/data/warningsmeteo",
        parser=None,
        variables={},
        time_unit="snapshot",
        year_type="calendar",
        first_year=None,
        update_signal="none",
        license=_LICENSE,
        legacy_alias=None,
        in_store=True,
        archive_scope="country_day",
        base_url=_IMGW_SITE,
        tier="operational",
    ),
    # The map of hydro.imgw.pl: every station's water state and its class.
    DatasetDescriptor(
        key="pl.imgw.hydro_states_current",
        slug="imgw_hydro_states_current",
        kind="hydro",
        title=message("datasets.title_hydro_states_current"),
        server_dir="map/stations/hydrologic",
        parser=None,
        variables={},
        time_unit="snapshot",
        year_type="calendar",
        first_year=None,
        update_signal="none",
        license=_HYDRO_LICENSE,
        legacy_alias=None,
        in_store=True,
        archive_scope="country_day",
        base_url=_HYDRO_BACK,
        tier="operational",
    ),
    # Every answer of hydro-back's station endpoints ``station/hydro/…`` (the night's
    # ``status/data``, ``discharge`` and ``water-temperature``, the GUI's live tail,
    # the station pages of `pl.imgw.hydro_details`), one capture version per UTC day.
    DatasetDescriptor(
        key="pl.imgw.hydro_operational",
        slug="imgw_hydro_operational",
        kind="hydro",
        title=message("datasets.title_hydro_operational"),
        server_dir="station/hydro",
        parser=None,
        variables={"H": "cm", "Q": "m3/s", "T": "degC"},
        time_unit="hour",
        year_type="calendar",
        first_year=None,
        update_signal="none",
        license=_HYDRO_LICENSE,
        legacy_alias=None,
        in_store=True,
        archive_scope="country_day",
        base_url=_HYDRO_BACK,
        tier="operational",
    ),
    # Every answer of hydro-back's meteorological station endpoints ``station/meteo/…``
    # (the station pages of `pl.imgw.meteo_details`), as `pl.imgw.hydro_operational`.
    DatasetDescriptor(
        key="pl.imgw.meteo_operational",
        slug="imgw_meteo_operational",
        kind="meteo",
        title=message("datasets.title_meteo_operational"),
        server_dir="station/meteo",
        parser=None,
        variables={},
        time_unit="hour",
        year_type="calendar",
        first_year=None,
        update_signal="none",
        license=_HYDRO_LICENSE,
        legacy_alias=None,
        in_store=True,
        archive_scope="country_day",
        base_url=_HYDRO_BACK,
        tier="operational",
    ),
    # The map of hydro.imgw.pl's meteorological stations: each station's precipitation
    # state, asked for the codes of `pl.imgw.meteo_details`.
    DatasetDescriptor(
        key="pl.imgw.meteo_states_current",
        slug="imgw_meteo_states_current",
        kind="meteo",
        title=message("datasets.title_meteo_states_current"),
        server_dir="map/stations/meteorologic",
        parser=None,
        variables={},
        time_unit="snapshot",
        year_type="calendar",
        first_year=None,
        update_signal="none",
        license=_HYDRO_LICENSE,
        legacy_alias=None,
        in_store=True,
        archive_scope="country_day",
        base_url=_HYDRO_BACK,
        tier="operational",
    ),
    # The monthly zips of every station's 10-minute H, Q and T (B00020S, B00050S,
    # B00100S), year folders from 2008; the signal is the datastore's listing
    # (``POST datastore/getFilesList``), not a folder index.
    DatasetDescriptor(
        key="pl.imgw.hydro_telemetry",
        slug="imgw_hydro_telemetry",
        kind="hydro",
        title=message("datasets.title_hydro_telemetry"),
        server_dir="Arch/Telemetria/Hydro",
        parser=None,
        variables={"H": "cm", "Q": "m3/s", "T": "degC"},
        time_unit="ten_minutes",
        year_type="calendar",
        first_year=2008,
        update_signal="listing",
        license=_LICENSE,
        legacy_alias=None,
        in_store=True,
        base_url=_IMGW_DATASTORE,
        tier="telemetry",
    ),
    # The hourly series of the tiers (ADR-031): the telemetry's full-hour records over
    # the full hours hydro-back gave for each closed UTC day (the plan's D9), one
    # version per calendar month; no files of its own.
    DatasetDescriptor(
        key="pl.imgw.hydro_subdaily",
        slug="imgw_hydro_subdaily",
        kind="hydro",
        title=message("datasets.title_hydro_subdaily"),
        server_dir=None,
        parser=None,
        variables={"H": "cm", "Q": "m3/s", "T": "degC"},
        time_unit="hour",
        year_type="calendar",
        first_year=2008,
        update_signal="none",
        license=_LICENSE,
        legacy_alias=None,
        in_store=True,
        tier="operational",
        inputs=("pl.imgw.hydro_telemetry", "pl.imgw.hydro_operational"),
    ),
    DatasetDescriptor(
        key="pl.imgw.hydro_phenomena",
        slug="imgw_hydro_phenomena",
        kind="hydro",
        title=message("datasets.title_hydro_phenomena"),
        server_dir="dane_hydrologiczne/dobowe",
        parser=None,
        variables={},
        time_unit="day",
        year_type="hydrological",
        first_year=1951,
        update_signal="http",
        license=_LICENSE,
        legacy_alias=None,
        in_store=False,
    ),
    DatasetDescriptor(
        key="pl.imgw.meteo_climate_monthly",
        slug="imgw_meteo_climate_monthly",
        kind="meteo",
        title=message("datasets.title_meteo_climate_monthly"),
        server_dir="dane_meteorologiczne/miesieczne/klimat",
        parser=None,
        variables={},
        time_unit="month",
        year_type="calendar",
        first_year=1951,
        update_signal="http",
        license=_LICENSE,
        legacy_alias="meteo/miesieczne/klimat",
        in_store=False,
    ),
    DatasetDescriptor(
        key="pl.imgw.meteo_precip_monthly",
        slug="imgw_meteo_precip_monthly",
        kind="meteo",
        title=message("datasets.title_meteo_precip_monthly"),
        server_dir="dane_meteorologiczne/miesieczne/opad",
        parser=None,
        variables={},
        time_unit="month",
        year_type="calendar",
        first_year=1950,
        update_signal="http",
        license=_LICENSE,
        legacy_alias="meteo/miesieczne/opad",
        in_store=False,
    ),
    DatasetDescriptor(
        key="pl.imgw.meteo_synop_monthly",
        slug="imgw_meteo_synop_monthly",
        kind="meteo",
        title=message("datasets.title_meteo_synop_monthly"),
        server_dir="dane_meteorologiczne/miesieczne/synop",
        parser=None,
        variables={},
        time_unit="month",
        year_type="calendar",
        first_year=1960,
        update_signal="http",
        license=_LICENSE,
        legacy_alias="meteo/miesieczne/synop",
        in_store=False,
    ),
    DatasetDescriptor(
        key="pl.imgw.meteo_climate_terms",
        slug="imgw_meteo_climate_terms",
        kind="meteo",
        title=message("datasets.title_meteo_climate_terms"),
        server_dir="dane_meteorologiczne/terminowe/klimat",
        parser=None,
        variables={},
        time_unit="term",
        year_type="calendar",
        first_year=1951,
        update_signal="http",
        license=_LICENSE,
        legacy_alias="meteo/terminowe/klimat",
        in_store=False,
    ),
    DatasetDescriptor(
        key="pl.imgw.meteo_synop_terms",
        slug="imgw_meteo_synop_terms",
        kind="meteo",
        title=message("datasets.title_meteo_synop_terms"),
        server_dir="dane_meteorologiczne/terminowe/synop",
        parser=None,
        variables={},
        time_unit="term",
        year_type="calendar",
        first_year=1966,
        update_signal="http",
        license=_LICENSE,
        legacy_alias="meteo/terminowe/synop",
        in_store=False,
        archive_scope="station_year",
    ),
    # The monthly archives of the warnings, outside the measurement data (ADR-023).
    DatasetDescriptor(
        key="pl.imgw.warnings_hydro_archive",
        slug="imgw_warnings_hydro_archive",
        kind="hydro",
        title=message("datasets.title_warnings_hydro_archive"),
        server_dir="arch/ost_hydro",
        parser=None,
        variables={},
        time_unit="month",
        year_type="calendar",
        first_year=2017,
        update_signal="http",
        license=_LICENSE,
        legacy_alias=None,
        in_store=False,
        base_url=_IMGW_DATA,
    ),
    DatasetDescriptor(
        key="pl.imgw.warnings_meteo_archive",
        slug="imgw_warnings_meteo_archive",
        kind="meteo",
        title=message("datasets.title_warnings_meteo_archive"),
        server_dir="arch/ost_meteo",
        parser=None,
        variables={},
        time_unit="month",
        year_type="calendar",
        first_year=2017,
        update_signal="http",
        license=_LICENSE,
        legacy_alias=None,
        in_store=False,
        base_url=_IMGW_DATA,
    ),
    # Solar radiation of the actinometric stations: folders named after the stations
    # (no codes), their files found in the server's folder index (ADR-023).
    DatasetDescriptor(
        key="pl.imgw.actinometric",
        slug="imgw_actinometric",
        kind="meteo",
        title=message("datasets.title_actinometric"),
        server_dir="dane_aktynometryczne",
        parser=None,
        variables={},
        time_unit="term",
        year_type="calendar",
        first_year=1990,
        update_signal="listing",
        license=_LICENSE,
        legacy_alias=None,
        in_store=False,
    ),
    DatasetDescriptor(
        key="cz.chmu.hydro_daily",
        slug="chmu_hydro_daily",
        kind="hydro",
        title=message("datasets.title_chmu_hydro_daily"),
        server_dir="hydrology/historical/data/daily",
        parser="parse_chmu_hydro_daily",
        variables={"H": "cm", "Q": "m3/s", "T": "degC"},
        time_unit="day",
        year_type="calendar",
        first_year=1887,
        update_signal="listing",
        license=_CHMU_LICENSE,
        legacy_alias=None,
        in_store=True,
        provider="CHMU",
        archive_scope="station_year",
        variable_notes={
            "H": message("datasets.note_chmu_hydro_daily_h"),
            "Q": message("datasets.note_chmu_hydro_daily_q"),
            "T": message("datasets.note_chmu_hydro_daily_t"),
        },
        content_form=_CHMU_JSON,
        volatile_fields=_CHMU_VOLATILE,
    ),
    DatasetDescriptor(
        key="cz.chmu.meteo_daily",
        slug="chmu_meteo_daily",
        kind="meteo",
        title=message("datasets.title_chmu_meteo_daily"),
        server_dir="meteorology/climate/historical_csv/data/daily",
        parser="parse_chmu_meteo_daily",
        variables={
            "P": "mm",
            "Tmean": "degC",
            "Tmax": "degC",
            "Tmin": "degC",
            "snow_cover": "cm",
            "fresh_snow": "cm",
        },
        time_unit="day",
        year_type="calendar",
        first_year=None,
        update_signal="listing",
        license=_CHMU_LICENSE,
        legacy_alias=None,
        in_store=True,
        provider="CHMU",
        archive_scope="station_element",
        variable_notes={
            "P": message("datasets.note_chmu_meteo_daily_p"),
            "Tmean": message("datasets.note_chmu_meteo_daily_tmean"),
            "Tmax": message("datasets.note_chmu_meteo_daily_tmax"),
            "Tmin": message("datasets.note_chmu_meteo_daily_tmin"),
            "snow_cover": message("datasets.note_chmu_meteo_daily_snow_cover"),
            "fresh_snow": message("datasets.note_chmu_meteo_daily_fresh_snow"),
        },
        measurement_fields=("quality", "source_flag"),
    ),
    DatasetDescriptor(
        key="cz.chmu.hydro_stations",
        slug="chmu_hydro_stations",
        kind="hydro",
        title=message("datasets.title_chmu_hydro_stations"),
        server_dir="hydrology/historical/metadata",
        parser="parse_chmu_stations",
        variables={},
        time_unit="station_list",
        year_type="none",
        first_year=None,
        update_signal="http",
        license=_CHMU_LICENSE,
        legacy_alias=None,
        in_store=True,
        provider="CHMU",
        content_form=_CHMU_JSON,
        volatile_fields=_CHMU_VOLATILE,
    ),
    DatasetDescriptor(
        key="cz.chmu.meteo_stations",
        slug="chmu_meteo_stations",
        kind="meteo",
        title=message("datasets.title_chmu_meteo_stations"),
        server_dir="meteorology/climate/historical/metadata",
        parser="parse_chmu_stations",
        variables={},
        time_unit="station_list",
        year_type="none",
        first_year=None,
        update_signal="http",
        license=_CHMU_LICENSE,
        legacy_alias=None,
        in_store=True,
        provider="CHMU",
        content_form=_CHMU_JSON,
        volatile_fields=_CHMU_VOLATILE,
    ),
    # The ``now`` metadata of the stations (spec 2026-10-18 §7.2), archived for the
    # ČHMÚ catalog (ADR-015 D2): their envelopes are regenerated hourly or daily, so
    # they have no stable HTTP signal; the daily meteo file is found in its listing.
    DatasetDescriptor(
        key="cz.chmu.hydro_now",
        slug="chmu_hydro_now",
        kind="hydro",
        title=message("datasets.title_chmu_hydro_now"),
        server_dir="hydrology/now/metadata",
        parser=None,
        variables={},
        time_unit="station_list",
        year_type="none",
        first_year=None,
        update_signal="none",
        license=_CHMU_LICENSE,
        legacy_alias=None,
        in_store=True,
        provider="CHMU",
        content_form=_CHMU_JSON,
        volatile_fields=_CHMU_VOLATILE,
    ),
    DatasetDescriptor(
        key="cz.chmu.meteo_now",
        slug="chmu_meteo_now",
        kind="meteo",
        title=message("datasets.title_chmu_meteo_now"),
        server_dir="meteorology/climate/now/metadata",
        parser=None,
        variables={},
        time_unit="station_list",
        year_type="none",
        first_year=None,
        update_signal="listing",
        license=_CHMU_LICENSE,
        legacy_alias=None,
        in_store=True,
        provider="CHMU",
        content_form=_CHMU_JSON,
        volatile_fields=_CHMU_VOLATILE,
    ),
    # ČHMÚ's groundwater (ADR-032): the bores and springs of ``hydrology/groundwater/``,
    # one file per object and year of its daily and of its weekly readings (the two
    # series of ``historical/data``), its operational month files (``recent``), its
    # published statistics (``characteristic``) and the lists of the objects.
    DatasetDescriptor(
        key="cz.chmu.groundwater_daily",
        slug="chmu_groundwater_daily",
        kind="groundwater",
        title=message("datasets.title_chmu_groundwater_daily"),
        server_dir="hydrology/groundwater/historical/data",
        parser="parse_chmu_groundwater",
        variables=_GROUNDWATER_VARIABLES,
        time_unit="day",
        year_type="calendar",
        first_year=1960,
        update_signal="listing",
        license=_CHMU_LICENSE,
        legacy_alias=None,
        in_store=True,
        provider="CHMU",
        archive_scope="station_year",
        variable_notes={
            "H_asl": message("datasets.note_chmu_groundwater_daily_h_asl"),
            "spring_yield": message("datasets.note_chmu_groundwater_daily_yield"),
            "T": message("datasets.note_chmu_groundwater_daily_t"),
        },
    ),
    DatasetDescriptor(
        key="cz.chmu.groundwater_weekly",
        slug="chmu_groundwater_weekly",
        kind="groundwater",
        title=message("datasets.title_chmu_groundwater_weekly"),
        server_dir="hydrology/groundwater/historical/data",
        parser="parse_chmu_groundwater",
        variables=_GROUNDWATER_VARIABLES,
        time_unit="week",
        year_type="calendar",
        first_year=1933,
        update_signal="listing",
        license=_CHMU_LICENSE,
        legacy_alias=None,
        in_store=True,
        provider="CHMU",
        archive_scope="station_year",
        variable_notes={
            "H_asl": message("datasets.note_chmu_groundwater_weekly_h_asl"),
            "spring_yield": message("datasets.note_chmu_groundwater_weekly_yield"),
            "T": message("datasets.note_chmu_groundwater_weekly_t"),
        },
    ),
    # One file per object and calendar month from 2025-01, rewritten every night until
    # the end of the next month: operational data (ADR-030 D1), stored as archive
    # versions and built into no series.
    DatasetDescriptor(
        key="cz.chmu.groundwater_recent",
        slug="chmu_groundwater_recent",
        kind="groundwater",
        title=message("datasets.title_chmu_groundwater_recent"),
        server_dir="hydrology/groundwater/recent/data",
        parser=None,
        variables={"H_asl": "m", "spring_yield": "l/s"},
        time_unit="day",
        year_type="calendar",
        first_year=2025,
        update_signal="listing",
        license=_CHMU_LICENSE,
        legacy_alias=None,
        in_store=True,
        provider="CHMU",
        archive_scope="station_month",
        tier="operational",
    ),
    # The quantiles 5-95 % of an object's level or yield per week or month of the year.
    DatasetDescriptor(
        key="cz.chmu.groundwater_characteristic",
        slug="chmu_groundwater_characteristic",
        kind="groundwater",
        title=message("datasets.title_chmu_groundwater_characteristic"),
        server_dir="hydrology/groundwater/characteristic/data",
        parser=None,
        variables={},
        time_unit="statistics",
        year_type="none",
        first_year=None,
        update_signal="listing",
        license=_CHMU_LICENSE,
        legacy_alias=None,
        in_store=True,
        provider="CHMU",
        archive_scope="station",
    ),
    DatasetDescriptor(
        key="cz.chmu.groundwater_stations",
        slug="chmu_groundwater_stations",
        kind="groundwater",
        title=message("datasets.title_chmu_groundwater_stations"),
        server_dir="hydrology/groundwater/historical/metadata",
        parser="parse_chmu_stations",
        variables={},
        time_unit="station_list",
        year_type="none",
        first_year=None,
        update_signal="http",
        license=_CHMU_LICENSE,
        legacy_alias=None,
        in_store=True,
        provider="CHMU",
        content_form=_CHMU_JSON,
        volatile_fields=_CHMU_VOLATILE,
    ),
    # The objects of the operational network, regenerated every hour like the hydro
    # ``now`` metadata (no stable HTTP signal).
    DatasetDescriptor(
        key="cz.chmu.groundwater_now",
        slug="chmu_groundwater_now",
        kind="groundwater",
        title=message("datasets.title_chmu_groundwater_now"),
        server_dir="hydrology/groundwater/now/metadata",
        parser=None,
        variables={},
        time_unit="station_list",
        year_type="none",
        first_year=None,
        update_signal="none",
        license=_CHMU_LICENSE,
        legacy_alias=None,
        in_store=True,
        provider="CHMU",
        content_form=_CHMU_JSON,
        volatile_fields=_CHMU_VOLATILE,
    ),
    # ČHMÚ's day files of 10-minute H, Q and TH (never rewritten, published about
    # 00:20 UTC the next day), the 548 stations of a day in one capture version.
    DatasetDescriptor(
        key="cz.chmu.hydro_recent",
        slug="chmu_hydro_recent",
        kind="hydro",
        title=message("datasets.title_chmu_hydro_recent"),
        server_dir="hydrology/recent/data",
        parser=None,
        variables={"H": "cm", "Q": "m3/s", "T": "degC"},
        time_unit="ten_minutes",
        year_type="calendar",
        first_year=None,
        update_signal="listing",
        license=_CHMU_LICENSE,
        legacy_alias=None,
        in_store=True,
        provider="CHMU",
        archive_scope="country_day",
        tier="operational",
    ),
    # ČHMÚ's ``now`` files of a station's current UTC day, rewritten every 20
    # minutes, captured when they are asked for (the GUI's live tail).
    DatasetDescriptor(
        key="cz.chmu.hydro_current",
        slug="chmu_hydro_current",
        kind="hydro",
        title=message("datasets.title_chmu_hydro_current"),
        server_dir="hydrology/now/data",
        parser=None,
        variables={"H": "cm", "Q": "m3/s", "T": "degC"},
        time_unit="ten_minutes",
        year_type="calendar",
        first_year=None,
        update_signal="none",
        license=_CHMU_LICENSE,
        legacy_alias=None,
        in_store=True,
        provider="CHMU",
        archive_scope="country_day",
        tier="operational",
    ),
    # ČHMÚ's validated hourly HH and QH, one file per station and year (from 1905
    # in the listing of 2026-11-16), published once a year like the daily DQ.
    DatasetDescriptor(
        key="cz.chmu.hydro_hourly",
        slug="chmu_hydro_hourly",
        kind="hydro",
        title=message("datasets.title_chmu_hydro_hourly"),
        server_dir="hydrology/historical/data/hourly",
        parser=None,
        variables={"H": "cm", "Q": "m3/s"},
        time_unit="hour",
        year_type="calendar",
        first_year=1905,
        update_signal="listing",
        license=_CHMU_LICENSE,
        legacy_alias=None,
        in_store=True,
        provider="CHMU",
        archive_scope="station_year",
        content_form=_CHMU_JSON,
        volatile_fields=_CHMU_VOLATILE,
        tier="verified",
    ),
    # The hourly series of the tiers (ADR-031): the validated hours over the full
    # hours of the ``recent`` day files, one version per calendar month.
    DatasetDescriptor(
        key="cz.chmu.hydro_subdaily",
        slug="chmu_hydro_subdaily",
        kind="hydro",
        title=message("datasets.title_chmu_hydro_subdaily"),
        server_dir=None,
        parser=None,
        variables={"H": "cm", "Q": "m3/s", "T": "degC"},
        time_unit="hour",
        year_type="calendar",
        first_year=1905,
        update_signal="none",
        license=_CHMU_LICENSE,
        legacy_alias=None,
        in_store=True,
        provider="CHMU",
        tier="operational",
        inputs=("cz.chmu.hydro_hourly", "cz.chmu.hydro_recent"),
    ),
    # Gdańskie Wody (ADR-034): the provider's station list, the month files of each
    # station's quantity gathered from its answers of a day (plan P6) and the series
    # built from them, hourly (ADR-031) and of the provider's day (P5). Raw data
    # without verification by the provider's word (tier ``operational``).
    DatasetDescriptor(
        key=_GDANSKIEWODY_STATIONS,
        slug="gdanskiewody_station_list",
        kind=None,
        title=message("datasets.title_gdanskiewody_station_list"),
        server_dir="rest",
        parser="parse_gdanskiewody_stations",
        variables={},
        time_unit="station_list",
        year_type="none",
        first_year=None,
        update_signal="none",
        license=_GDANSKIEWODY_LICENSE,
        legacy_alias=None,
        in_store=True,
        provider=_GDANSKIEWODY,
    ),
    DatasetDescriptor(
        key=_GDANSKIEWODY_MEASUREMENTS,
        slug="gdanskiewody_measurements",
        kind=None,
        title=message("datasets.title_gdanskiewody_measurements"),
        server_dir="rest/measurements",
        parser=None,
        variables={**_GDANSKIEWODY_HYDRO, **_GDANSKIEWODY_METEO_HOURLY},
        time_unit="hour",
        year_type="calendar",
        first_year=_GDANSKIEWODY_FIRST_YEAR,
        update_signal="none",
        license=_GDANSKIEWODY_LICENSE,
        legacy_alias=None,
        in_store=True,
        provider=_GDANSKIEWODY,
        archive_scope="station_element_month",
        tier="operational",
    ),
    _gdanskiewody_series(
        "hydro",
        "hour",
        _GDANSKIEWODY_HYDRO,
        message("datasets.title_gdanskiewody_hydro_hourly"),
    ),
    _gdanskiewody_series(
        "meteo",
        "hour",
        _GDANSKIEWODY_METEO_HOURLY,
        message("datasets.title_gdanskiewody_meteo_hourly"),
    ),
    _gdanskiewody_series(
        "hydro",
        "day",
        _GDANSKIEWODY_HYDRO,
        message("datasets.title_gdanskiewody_hydro_daily"),
    ),
    _gdanskiewody_series(
        "meteo",
        "day",
        _GDANSKIEWODY_METEO_DAILY,
        message("datasets.title_gdanskiewody_meteo_daily"),
    ),
    # PIG-PIB (ADR-035): the points, the readings and the two tables of the MWP
    # database (verified: PIG-PIB checks them before they enter it), each version the
    # capture of one run's pages, compared by content (``pig-json/1``), the readings
    # one file per calendar month of their rows; the automatic hourly measurements of
    # ``mwp_auto`` (operational, „bez walidacji”), harvested each night by ``OBJECTID``
    # watermark into the night's capture, and the hourly series built from them.
    DatasetDescriptor(
        key=_PIG_STATIONS,
        slug="pig_groundwater_stations",
        kind="groundwater",
        title=message("datasets.title_pig_groundwater_stations"),
        server_dir="mwp/MapServer/0",
        parser="parse_pig_stations",
        variables={},
        time_unit="station_list",
        year_type="none",
        first_year=None,
        update_signal="none",
        license=_PIG_LICENSE,
        legacy_alias=None,
        in_store=True,
        provider=_PIG,
        content_form=_PIG_JSON,
        volatile_fields=_PIG_VOLATILE,
    ),
    DatasetDescriptor(
        key=_PIG_READINGS,
        slug="pig_groundwater_readings",
        kind="groundwater",
        title=message("datasets.title_pig_groundwater_readings"),
        server_dir="mwp/MapServer/1",
        parser="parse_pig_readings",
        variables={"depth_to_water": "m", "H_asl": "m", "spring_yield": "l/s"},
        time_unit="week",
        year_type="hydrological",
        first_year=1965,
        update_signal="none",
        license=_PIG_LICENSE,
        legacy_alias=None,
        in_store=True,
        provider=_PIG,
        variable_notes=_PIG_READING_NOTES,
        content_form=_PIG_JSON,
        volatile_fields=_PIG_VOLATILE,
    ),
    DatasetDescriptor(
        key="pl.pig.groundwater_chemistry",
        slug="pig_groundwater_chemistry",
        kind="groundwater",
        title=message("datasets.title_pig_groundwater_chemistry"),
        server_dir="mwp/MapServer/2",
        parser=None,
        variables={},
        time_unit="snapshot",
        year_type="none",
        first_year=None,
        update_signal="none",
        license=_PIG_LICENSE,
        legacy_alias=None,
        in_store=True,
        provider=_PIG,
        content_form=_PIG_JSON,
        volatile_fields=_PIG_VOLATILE,
    ),
    DatasetDescriptor(
        key="pl.pig.groundwater_watchlist",
        slug="pig_groundwater_watchlist",
        kind="groundwater",
        title=message("datasets.title_pig_groundwater_watchlist"),
        server_dir="mwp/MapServer/3",
        parser=None,
        variables={},
        time_unit="snapshot",
        year_type="none",
        first_year=None,
        update_signal="none",
        license=_PIG_LICENSE,
        legacy_alias=None,
        in_store=True,
        provider=_PIG,
        content_form=_PIG_JSON,
        volatile_fields=_PIG_VOLATILE,
    ),
    DatasetDescriptor(
        key=_PIG_OPERATIONAL,
        slug="pig_groundwater_operational",
        kind="groundwater",
        title=message("datasets.title_pig_groundwater_operational"),
        server_dir="mwp_auto/MapServer",
        parser=None,
        variables={"depth_to_water": "m"},
        time_unit="hour",
        year_type="calendar",
        first_year=None,
        update_signal="none",
        license=_PIG_LICENSE,
        legacy_alias=None,
        in_store=True,
        provider=_PIG,
        archive_scope="country_day",
        tier="operational",
    ),
    DatasetDescriptor(
        key="pl.pig.groundwater_subdaily",
        slug="pig_groundwater_subdaily",
        kind="groundwater",
        title=message("datasets.title_pig_groundwater_subdaily"),
        server_dir=None,
        parser=None,
        variables={"depth_to_water": "m", "H_asl": "m"},
        time_unit="hour",
        year_type="calendar",
        first_year=2015,
        update_signal="none",
        license=_PIG_LICENSE,
        legacy_alias=None,
        in_store=True,
        provider=_PIG,
        variable_notes=_PIG_HOURLY_NOTES,
        tier="operational",
        inputs=(_PIG_OPERATIONAL,),
    ),
)
# Datasets declared ahead of the step that serves them (ADR-030 D8): in the registry
# with their tier, listed by ``datasets(pending=True)`` only. No command, MCP tool,
# REST route or GUI view lists or accepts them (`get_dataset`, the providers'
# ``datasets`` and the choices of the catalog read `_DATASETS`) until their step
# moves them there (H2a moved the six captures of current data, O2 the datasets of
# the operational series, beside each provider's stored datasets).
_PENDING = (
    # ČHMÚ's groundwater ``now`` files, an object's latest daily value rewritten every
    # hour (ADR-032): captured when they are asked for, like the hydro ``now`` files;
    # the same values come in `cz.chmu.groundwater_recent` the next night.
    DatasetDescriptor(
        key="cz.chmu.groundwater_current",
        slug="chmu_groundwater_current",
        kind="groundwater",
        title=message("datasets.title_chmu_groundwater_current"),
        server_dir="hydrology/groundwater/now/data",
        parser=None,
        variables={"H_asl": "m", "spring_yield": "l/s"},
        time_unit="day",
        year_type="calendar",
        first_year=None,
        update_signal="none",
        license=_CHMU_LICENSE,
        legacy_alias=None,
        in_store=True,
        provider="CHMU",
        archive_scope="country_day",
        tier="operational",
    ),
)

# Providers fed by files (ADR-033; Nogat plan 2026-11-21, I13): an operator's own
# network declared in the provider files ``nogat.toml`` lists, read once as the
# registry is imported (`obserwator._provider_files`). A valid file adds a provider
# after the packaged ones, with its station file and its daily datasets after theirs,
# and declares the origin of its lines (`obserwator.attribution.declare_origin`); a
# file with a problem adds nothing (`provider_file_problems`).
_FILES_DIRECTORY = "files"
"""The directory of the raw root below ``archives/versions`` of every provider fed by files."""


def _daily_variables() -> dict[str, dict[str, str]]:
    """The variables of the daily series of each kind of station, with their units."""
    found: dict[str, dict[str, str]] = {}
    for descriptor in _DATASETS:
        if (
            descriptor.time_unit == "day"
            and descriptor.kind is not None
            and descriptor.parser is not None
        ):
            for name, unit in descriptor.variables.items():
                found.setdefault(descriptor.kind, {}).setdefault(name, unit)
    return found


def _file_title(provider: ProviderFile, dataset: FileDataset) -> Message:
    """The title of a dataset of a provider fed by files, with its tier when unverified."""
    title = provider.dataset_title(dataset.kind)
    if provider.tier == "verified":
        return title
    return message("provider_files.title_unverified", title=title)


def _file_datasets(provider: ProviderFile) -> tuple[DatasetDescriptor, ...]:
    """
    The datasets of a provider fed by files: its station file, then its daily series.

    Their files lie in the raw root below ``files/<acronym>/`` (`_FILES_DIRECTORY`):
    ``station_list/stations.geojson`` and ``<name>/<station code>.csv`` (or
    ``.parquet``), one file per station with its whole record.
    """
    licence = License(
        provider.license_id, provider.line, provider.license_url, provider.terms_url
    )
    base = f"{_FILES_DIRECTORY}/{provider.acronym}"
    stations = DatasetDescriptor(
        key=f"{provider.key_prefix}.station_list",
        slug=f"{provider.acronym}_station_list",
        kind=None,
        title=message(
            "provider_files.title_station_list", provider=provider.short_name
        ),
        server_dir=f"{base}/station_list",
        parser=None,
        variables={},
        time_unit="station_list",
        year_type="none",
        first_year=None,
        update_signal="none",
        license=licence,
        legacy_alias=None,
        in_store=True,
        provider=provider.id,
    )
    return (
        stations,
        *(
            DatasetDescriptor(
                key=f"{provider.key_prefix}.{dataset.name}",
                slug=f"{provider.acronym}_{dataset.name}",
                kind=dataset.kind,
                title=_file_title(provider, dataset),
                server_dir=f"{base}/{dataset.name}",
                parser="parse_series_export",
                variables=dict(dataset.variables),
                time_unit="day",
                year_type=dataset.year_type,
                first_year=None,
                update_signal="none",
                license=licence,
                legacy_alias=None,
                in_store=True,
                provider=provider.id,
                archive_scope="station",
                tier=provider.tier,
            )
            for dataset in provider.datasets
        ),
    )


def _file_provider(provider: ProviderFile) -> ProviderDescriptor:
    """The registry entry of a provider fed by files."""
    return ProviderDescriptor(
        id=provider.id,
        short_name=provider.short_name,
        name=provider.name,
        country=provider.country,
        key_prefix=provider.key_prefix,
        base_url="",
        license=License(
            provider.license_id, provider.line, provider.license_url, provider.terms_url
        ),
        processed_attribution=provider.processed or "",
        notice=message(
            "provider_files.provider_notice",
            license=provider.license_id,
            url=provider.license_url,
        ),
        station_code_pattern=provider.station_code_pattern,
        datasets=tuple(item.key for item in _file_datasets(provider)),
    )


def _load_files() -> LoadedFiles:
    """
    Read the provider files of ``nogat.toml`` and declare the origins of their lines.

    A provider file may take no id of a packaged provider (nor its old ids) and no
    name of an attribution origin.
    """
    loaded = load_provider_files(
        config_file(),
        reserved=frozenset(
            (
                *ORIGINS,
                "imgw",
                "chmu",
                *(alias.lower() for alias in PROVIDER_ID_ALIASES),
            )
        ),
        variables=_daily_variables(),
    )
    # P8: every provider fed by files is of the class "other" (no national service),
    # and its notice follows its lines in every product (the Polish text, as the lines).
    notice = localize(message("datasets.source_notice_other"), "pl")
    for provider in loaded.files:
        declare_origin(provider.acronym, provider.line, provider.processed, notice)
    return loaded


_FILES = _load_files()
_DATASETS = _DATASETS + tuple(
    descriptor for item in _FILES.files for descriptor in _file_datasets(item)
)
_REGISTRY = _DATASETS + _PENDING
_PROVIDERS: tuple[ProviderDescriptor, ...] = (
    ProviderDescriptor(
        id="IMGW",
        short_name="IMGW-PIB",
        name=message("legal.imgw_name"),
        country="PL",
        key_prefix="pl.imgw",
        base_url=f"{IMGW_PUBLIC_DATA_URL}/",
        license=_LICENSE,
        processed_attribution=message("legal.imgw_processed_attribution"),
        notice=message(
            "datasets.provider_notice_imgw",
            terms=" ".join(attribution("imgw").terms_notice),
        ),
        station_code_pattern=r"^[0-9]{9}$",
        datasets=tuple(item.key for item in _DATASETS if item.provider == "IMGW"),
    ),
    ProviderDescriptor(
        id="CHMU",
        short_name="ČHMÚ",
        name="Český hydrometeorologický ústav",
        country="CZ",
        key_prefix="cz.chmu",
        base_url="https://opendata.chmi.cz/",
        license=_CHMU_LICENSE,
        processed_attribution=message("legal.chmu_processed_attribution"),
        notice=message("datasets.provider_notice_chmu"),
        station_code_pattern=rf"^{_WIGOS_CODE}$",
        datasets=tuple(item.key for item in _DATASETS if item.provider == "CHMU"),
    ),
    # Gdańskie Wody (ADR-034): an API with a key (P3), terms not known yet, so its
    # lines are drafts (`obserwator.attribution.provisional`) and no server serves it.
    ProviderDescriptor(
        id=_GDANSKIEWODY,
        short_name=message("legal.gdanskiewody_short_name"),
        name=message("legal.gdanskiewody_name"),
        country="PL",
        key_prefix="pl.gdanskiewody",
        base_url="https://pomiary.gdanskiewody.pl/",
        license=_GDANSKIEWODY_LICENSE,
        processed_attribution=message("legal.gdanskiewody_processed_attribution"),
        notice=message("datasets.provider_notice_gdanskiewody"),
        station_code_pattern=rf"^{_GDANSKIEWODY_CODE}$",
        datasets=tuple(
            item.key for item in _DATASETS if item.provider == _GDANSKIEWODY
        ),
        credential=ProviderCredential("GDANSKIE_WODY"),
    ),
    # PIG-PIB (ADR-035): the state geological service's groundwater monitoring, open
    # ArcGIS REST without a key, CC BY 4.0 by dane.gov.pl's dataset 170.
    ProviderDescriptor(
        id=_PIG,
        short_name=message("legal.pig_short_name"),
        name=message("legal.pig_name"),
        country="PL",
        key_prefix="pl.pig",
        base_url="https://cbdgmapa.pgi.gov.pl/arcgis/rest/services/hydrogeologia/",
        license=_PIG_LICENSE,
        processed_attribution=message("legal.pig_processed_attribution"),
        notice=message("datasets.provider_notice_pig"),
        station_code_pattern=rf"^{_PIG_CODE}$",
        datasets=tuple(item.key for item in _DATASETS if item.provider == _PIG),
    ),
)
_PROVIDERS = _PROVIDERS + tuple(_file_provider(item) for item in _FILES.files)
# Lookup by id and by key prefix.
_PROVIDER_BY_NAME = {
    name: provider
    for provider in _PROVIDERS
    for name in (provider.key_prefix, provider.id)
}
# Derived dataset key of each provider's station catalog, ``<key prefix>.stations``, by
# provider id (ADR-003 D5).
_CATALOG_DATASETS: Mapping[str, str] = MappingProxyType(
    {provider.id: f"{provider.key_prefix}.stations" for provider in _PROVIDERS}
)
# Lookup order key → slug → legacy alias: later entries of the inner tuple win.
_BY_NAME = {
    name: descriptor
    for descriptor in _DATASETS
    for name in (descriptor.legacy_alias, descriptor.slug, descriptor.key)
    if name is not None
}
_ALLOWED = [descriptor.key for descriptor in _DATASETS]
_UNSUPPORTED = {
    "meteo/terminowe/opad": (
        "not_published",
        message("datasets.meteo_terminowe_opad_data_do"),
    ),
}


def providers() -> tuple[ProviderDescriptor, ...]:
    """
    Return the provider registry.

    Returns
    -------
    tuple of ProviderDescriptor
        ``IMGW``, then ``CHMU`` (a fixed order), then the providers fed by files of
        ``nogat.toml`` in the order of its ``provider_files`` (ADR-033).
    """
    return _PROVIDERS


def provider_files() -> LoadedFiles:
    """
    The provider files ``nogat.toml`` lists, as the registry read them (ADR-033).

    Read once, when this module was imported: a change of a file is seen by the next
    process.

    Returns
    -------
    LoadedFiles
        The files listed, the valid ones (each a provider of `providers`) and the
        problem of each other (an `ObserwatorValidationError` naming the field in
        ``details.option`` and the file in ``details.path``), which ``config show``
        reports and which refuses the start of both servers and every ``store
        import``.
    """
    return _FILES


def check_provider_files() -> None:
    """
    Refuse a deployment whose provider files cannot all be used (fail closed, ADR-033).

    Raises
    ------
    ObserwatorValidationError
        The first problem of `provider_files`.
    """
    if _FILES.problems:
        problem = _FILES.problems[0]
        raise ObserwatorValidationError(
            problem.detail, details=problem.details, hint=problem.hint
        )


def get_provider(provider: str, /) -> ProviderDescriptor:
    """
    Find a provider by its identifier or dataset key prefix.

    Parameters
    ----------
    provider : str
        Identifier (``"IMGW"``, ``"CHMU"``) or key prefix
        (``"pl.imgw"``, ``"cz.chmu"``).

    Returns
    -------
    ProviderDescriptor
        Descriptor of the provider.

    Raises
    ------
    ObserwatorValidationError
        If the value names no provider (``details.allowed`` lists the
        identifiers).
    """
    if isinstance(provider, str) and provider in _PROVIDER_BY_NAME:
        return _PROVIDER_BY_NAME[provider]
    allowed = [item.id for item in _PROVIDERS]
    raise ObserwatorValidationError(
        message(
            "datasets.unknown_data_provider_allowed",
            provider=provider,
            allowed=", ".join(allowed),
        ),
        details={
            "option": "provider",
            "value": provider if isinstance(provider, str) else repr(provider),
            "allowed": allowed,
        },
    )


def datasets(
    *,
    kind: Kind | None = None,
    provider: str | None = None,
    pending: bool = False,
) -> tuple[DatasetDescriptor, ...]:
    """
    Return the dataset registry, optionally limited to a family and a provider.

    Parameters
    ----------
    kind : {"hydro", "meteo", "groundwater"} or None, optional
        Data family to keep; None keeps every family (PMAXTP has no family
        and is returned only then).
    provider : str or None, optional
        Provider identifier or key prefix to keep (see `get_provider`); None
        keeps all providers.
    pending : bool, optional
        Also the datasets declared ahead of the step that serves them (ADR-030):
        no command, MCP tool, REST route or GUI view lists or accepts these, and
        `get_dataset` refuses their keys, until that step serves them.

    Returns
    -------
    tuple of DatasetDescriptor
        Descriptors in registry order: the IMGW-PIB datasets (those of the
        store, then the download-only ones), then the ČHMÚ datasets; with
        ``pending``, then the declared ones.

    Raises
    ------
    ObserwatorValidationError
        If ``kind`` is not one of `KINDS` or None, or ``provider`` names no
        provider.
    """
    if kind is not None and kind not in KINDS:
        raise ObserwatorValidationError(
            message("datasets.invalid_kind_dataset_allowed_hydro", kind=kind),
            details={"option": "kind", "value": kind, "allowed": list(KINDS)},
        )
    owner = None if provider is None else get_provider(provider).id
    registry = _REGISTRY if pending else _DATASETS
    if kind is None and owner is None:
        return registry
    return tuple(
        descriptor
        for descriptor in registry
        if (kind is None or descriptor.kind == kind)
        and (owner is None or descriptor.provider == owner)
    )


def builds_series(descriptor: DatasetDescriptor, /) -> bool:
    """
    Whether ``series build`` builds a series of a dataset.

    Parameters
    ----------
    descriptor : DatasetDescriptor
        A registry entry.

    Returns
    -------
    bool
        True for a dataset of the store with a parser and a time unit of
        `SERIES_TIME_UNITS`, and for a sub-daily series built from its ``inputs``
        (ADR-031); False for station sources, download-only datasets and the
        stored files no series of their own reads (``cz.chmu.groundwater_recent``,
        the operational data and the telemetry, ADR-030 D1, and the statistics of
        ``cz.chmu.groundwater_characteristic``, ADR-032).
    """
    return (
        descriptor.in_store
        and descriptor.time_unit in SERIES_TIME_UNITS
        and (descriptor.parser is not None or descriptor.inputs is not None)
    )


def monthly_series(descriptor: DatasetDescriptor, /) -> bool:
    """
    Whether a series dataset is built as one version per calendar month (ADR-031).

    Parameters
    ----------
    descriptor : DatasetDescriptor
        A registry entry.

    Returns
    -------
    bool
        True for the sub-daily series (``time_unit`` ``hour``, built from their
        ``inputs``): their slots are ``series:<key>:<YYYY-MM>`` and their versions lie
        in ``series/versions/<slug>/<YYYY-MM>/``; False for every other dataset.
    """
    return builds_series(descriptor) and descriptor.time_unit == "hour"


def keeps_archives(descriptor: DatasetDescriptor, /) -> bool:
    """
    Whether ``store sync`` keeps a dataset's source files as archive versions.

    Parameters
    ----------
    descriptor : DatasetDescriptor
        A registry entry.

    Returns
    -------
    bool
        True for a dataset of the store with files on its provider's server
        other than the station sources: every series dataset (`builds_series`)
        and the stored files no series reads (``cz.chmu.groundwater_recent``,
        ``cz.chmu.groundwater_characteristic``, ADR-032); False for station
        lists and metadata, the captures of current data (sealed from the
        spool, ADR-030 D3), PMAXTP and the download-only datasets.
    """
    return (
        descriptor.in_store
        and descriptor.server_dir is not None
        and descriptor.time_unit != "station_list"
        and descriptor.archive_scope != CAPTURE_SCOPE
    )


def get_dataset(dataset: str, /) -> DatasetDescriptor:
    """
    Find a dataset by its key, slug or legacy alias.

    Parameters
    ----------
    dataset : str
        Full key (``"pl.imgw.hydro_daily"``), slug (``"imgw_hydro_daily"``) or
        legacy alias (``"hydro/dobowe"``), tried in this order. A renamed key
        of ``DATASET_KEY_ALIASES`` and a slug of 3.0.x without its provider's
        acronym (``"hydro_daily"``) are no input (ADR-028).

    Returns
    -------
    DatasetDescriptor
        Descriptor of the dataset; results always carry its full ``key``.

    Raises
    ------
    ObserwatorValidationError
        If the value names no dataset (``details.allowed`` lists the keys; a
        key or slug declared ahead of its step, ADR-030, names none either), or
        it is a legacy alias of an archive without a descriptor (nonexistent
        hourly precipitation; ``details.reason`` says why).
    """
    if isinstance(dataset, str):
        if (descriptor := _BY_NAME.get(dataset)) is not None:
            return descriptor
        if dataset in _UNSUPPORTED:
            reason, text = _UNSUPPORTED[dataset]
            raise ObserwatorValidationError(
                text,
                details={
                    "option": "dataset",
                    "value": dataset,
                    "reason": reason,
                    "allowed": _ALLOWED,
                },
            )
    raise ObserwatorValidationError(
        message(
            "datasets.unknown_imgw_dataset_allowed_keys",
            dataset=dataset,
            allowed=", ".join(_ALLOWED),
        ),
        details={
            "option": "dataset",
            "value": dataset if isinstance(dataset, str) else repr(dataset),
            "allowed": _ALLOWED,
        },
    )


def resolve_dataset_key(dataset: str, /) -> str | None:
    """
    Resolve a stored dataset key to its current key.

    Parameters
    ----------
    dataset : str
        Dataset key as written, e.g. the ``dataset`` field of a sidecar.

    Returns
    -------
    str or None
        The key itself if it is current (a registry key or the station
        catalog key of a provider, e.g. ``CATALOG_DATASET`` or
        ``"cz.chmu.stations"``), the current key of a renamed key from
        ``DATASET_KEY_ALIASES``, None for a key Obserwator does not know
        (slugs and legacy aliases are not keys and give None too).
    """
    key = DATASET_KEY_ALIASES.get(dataset, dataset)
    if key in _CATALOG_DATASETS.values() or any(item.key == key for item in _DATASETS):
        return key
    return None


def _license_document(license_: License, /) -> dict[str, str]:
    """
    The ``license`` object of a sidecar.

    ``terms_url`` is written only when set, so IMGW-PIB sidecars keep the
    bytes they had before the field existed.

    Parameters
    ----------
    license_ : License
        License of a provider or dataset.

    Returns
    -------
    dict of str to str
        ``id``, ``attribution``, ``url`` and, when set, ``terms_url``.
    """
    document = {
        "id": license_.id,
        "attribution": license_.attribution,
        "url": license_.url,
    }
    if license_.terms_url is not None:
        document["terms_url"] = license_.terms_url
    return document


def _items(value: object, option: str) -> list[int | str]:
    """Flatten a scalar, comma-separated text or iterable into list items."""
    if isinstance(value, int | str):
        raw: list[object] = [value]
    elif isinstance(value, Iterable) and not isinstance(value, bytes | Mapping):
        raw = list(value)
    else:
        raise ObserwatorValidationError(
            message(
                "datasets.option_must_number_text_list", option=option, value=value
            ),
            details={"option": option, "value": repr(value)},
        )
    items: list[int | str] = []
    for item in raw:
        if isinstance(item, str):
            items.extend(part.strip() for part in item.split(","))
        elif isinstance(item, int) and not isinstance(item, bool):
            items.append(item)
        else:
            raise ObserwatorValidationError(
                message("datasets.invalid_value_option", option=option, item=item),
                details={"option": option, "value": repr(item)},
            )
    if not items or "" in items:
        raise ObserwatorValidationError(
            message("datasets.option_needs_non_empty_list", option=option),
            details={"option": option, "value": repr(value)},
        )
    return items


def parse_years(value: YearsArg, /, *, option: str = "years") -> tuple[int, ...]:
    """
    Expand a years argument into sorted, unique years.

    Parameters
    ----------
    value : YearsArg
        A year (``2024``), a range (``"2020-2023"``), comma-separated text
        (``"2020,2022"``) or an iterable mixing years and ranges
        (``[2020, "2022-2023"]``).
    option : str, optional
        Option name used in error messages and ``details.option``.

    Returns
    -------
    tuple of int
        Expanded years in ascending order, without duplicates.

    Raises
    ------
    ObserwatorValidationError
        If the value is empty, not a year or range, a range is reversed, or a
        year is outside 1-9999.
    """
    years: set[int] = set()
    for item in _items(value, option):
        if isinstance(item, int):
            start = end = item
        elif match := _YEAR.fullmatch(item):
            start = int(match.group(1))
            end = int(match.group(2) or start)
        else:
            raise ObserwatorValidationError(
                message(
                    "datasets.invalid_year_range_years_option", option=option, item=item
                ),
                details={"option": option, "value": item},
            )
        if not 1 <= start <= end <= 9999:
            raise ObserwatorValidationError(
                message(
                    "datasets.invalid_range_years_option", option=option, item=item
                ),
                details={"option": option, "value": item},
            )
        years.update(range(start, end + 1))
    return tuple(sorted(years))


def parse_months(value: MonthsArg, /, *, option: str = "months") -> tuple[int, ...]:
    """
    Normalize a months argument into sorted, unique months.

    Parameters
    ----------
    value : MonthsArg
        A month (``3``), comma-separated text (``"1,2"``) or an iterable of
        months as numbers or text.
    option : str, optional
        Option name used in error messages and ``details.option``.

    Returns
    -------
    tuple of int
        Months 1-12 in ascending order, without duplicates.

    Raises
    ------
    ObserwatorValidationError
        If the value is empty, not an integer, or a month is outside 1-12.
    """
    months: set[int] = set()
    for item in _items(value, option):
        if isinstance(item, str):
            if not _MONTH.fullmatch(item):
                raise ObserwatorValidationError(
                    message(
                        "datasets.option_must_contain_integers",
                        option=option,
                        item=item,
                    ),
                    details={"option": option, "value": item},
                )
            item = int(item)
        if not 1 <= item <= 12:
            raise ObserwatorValidationError(
                message("datasets.months_must_range_1_12"),
                details={"option": option, "value": item},
            )
        months.add(item)
    return tuple(sorted(months))


def _parse_params(
    params: Iterable[Literal["H", "Q", "T"]], dataset: DatasetDescriptor
) -> tuple[str, ...]:
    if dataset.key != "pl.imgw.hydro_semiannual":
        raise ObserwatorValidationError(
            message("datasets.option_params_applies_only_dataset", key=dataset.key),
            details={"option": "params", "value": dataset.key},
        )
    items = [
        part.strip()
        for item in ([params] if isinstance(params, str) else params)
        for part in (item.split(",") if isinstance(item, str) else [item])
    ]
    if not items or any(item not in _PARAMS for item in items):
        raise ObserwatorValidationError(
            message("datasets.invalid_semi_annual_parameters_allowed", items=items),
            details={"option": "params", "value": items, "allowed": list(_PARAMS)},
        )
    return tuple(param for param in _PARAMS if param in items)


def _period(year: int, month: int | None, *, hydrological: bool) -> tuple[date, date]:
    if month is None:
        start = date(year - 1, 11, 1) if hydrological else date(year, 1, 1)
        end = date(year, 10, 31) if hydrological else date(year, 12, 31)
    else:
        actual_year = year - 1 if hydrological and month <= 2 else year
        actual_month = ((month + 9) % 12) + 1 if hydrological else month
        start = date(actual_year, actual_month, 1)
        next_month = (
            date(actual_year + 1, 1, 1)
            if actual_month == 12
            else date(actual_year, actual_month + 1, 1)
        )
        end = next_month - timedelta(days=1)
    return start, end


def _archive(
    descriptor: DatasetDescriptor,
    path: str,
    year: int | None,
    month: int | None = None,
    param: str | None = None,
    *,
    last_year: int | None = None,
    station_code: str | None = None,
) -> ArchiveFile:
    if year is None:
        start, end = None, None
    else:
        start, end = _period(
            year, month, hydrological=descriptor.year_type == "hydrological"
        )
        if last_year is not None:
            end = date(last_year, 12, 31)
    return ArchiveFile(
        descriptor.key,
        path,
        (descriptor.base_url or get_provider(descriptor.provider).base_url)
        + quote(path),
        year,
        month,
        param,
        descriptor.year_type if year is not None else "none",
        start,
        end,
        station_code,
    )


def archive_files(
    dataset: str,
    /,
    *,
    years: YearsArg | None = None,
    months: MonthsArg | None = None,
    params: Iterable[Literal["H", "Q", "T"]] | None = None,
    stations: Iterable[str] | None = None,
) -> tuple[ArchiveFile, ...]:
    """
    Enumerate distinct physical source files without accessing the network.

    IMGW-PIB archives cover the whole country: months select only physically
    monthly files (daily hydro before 2023, daily and hourly meteo from
    2001); for yearly archives one file per year is returned, and a
    meteorological monthly archive is returned once per folder (five-year
    folders until 2000). The per-station synop archives of IMGW-PIB
    (``pl.imgw.meteo_synop_daily``, ``pl.imgw.meteo_synop_terms``) hold one
    station per file: one file per station and folder (five-year folders
    until 2000), named by the station number (the last three digits of its
    code); the running year is published as monthly files of the whole
    country, selected by months. ČHMÚ files cover one station: one file per
    station and calendar year (``cz.chmu.hydro_daily``) or six files per
    station with its whole history, one per element SRA, T, TMA, TMI, SCE,
    SNO (``cz.chmu.meteo_daily``). Years are not limited by the current year;
    the result lists candidates, and whether a file is published is decided
    by the server (its listing or a 404 answer).

    The warning archives (``pl.imgw.warnings_hydro_archive``,
    ``pl.imgw.warnings_meteo_archive``) are monthly files, one per month.
    The files of ``pl.imgw.actinometric`` follow no name rule: they are
    found in the server's folder index by `download_archives`, so they are
    refused here.

    Parameters
    ----------
    dataset : str
        Key, slug or legacy alias of an archive dataset (all but the station
        lists, PMAXTP and the captures).
    years : YearsArg or None, optional
        Archive years (hydrological or calendar per the dataset), also as
        ranges ``"a-b"``; at least ``first_year`` of the dataset. Required
        except for ``cz.chmu.meteo_daily``, which rejects it.
    months : MonthsArg or None, optional
        Months 1-12 (for hydrological data 1 = November of the previous
        year); None selects all months. Rejected for ČHMÚ datasets. For the
        per-station synop archives of IMGW-PIB they select the monthly files
        of the whole country (years from 2001), and either they or
        ``stations`` are required.
    params : iterable of {"H", "Q", "T"} or None, optional
        Parameters of ``pl.imgw.hydro_semiannual`` to keep; None keeps all
        three. Rejected for other datasets.
    stations : iterable of str or None, optional
        Station codes of the dataset's provider (duplicates are dropped).
        Required for ČHMÚ datasets, accepted by the per-station synop archives
        of IMGW-PIB, rejected for other IMGW-PIB datasets.

    Returns
    -------
    tuple of ArchiveFile
        IMGW-PIB archives ordered by year, then by month or parameter (the
        per-station synop archives by station, then by folder, then the
        monthly files); ČHMÚ files ordered by station code, then by year or
        element.

    Raises
    ------
    ObserwatorValidationError
        If the dataset is unknown or has no archives (station lists,
        PMAXTP), is a capture dataset (``details.reason="capture"``: its
        versions are sealed from the spool, ADR-030 D3) or its files are named
        only in the server's folder index (``details.reason="listed"``), a
        required option is missing or a
        rejected one is given, the years or months are empty, malformed or out
        of range, a station code does not follow the provider's grammar, or
        ``params`` is invalid; ``details.option`` names the option.
    """
    descriptor = get_dataset(dataset)
    if descriptor.server_dir is None or descriptor.time_unit == "station_list":
        raise ObserwatorValidationError(
            message("datasets.dataset_has_no_annual_archives", key=descriptor.key),
            details={"option": "dataset", "value": descriptor.key},
        )
    if descriptor.archive_scope == CAPTURE_SCOPE:
        # A capture is written from the spool, not downloaded (ADR-030 D3).
        raise ObserwatorValidationError(
            message("datasets.dataset_is_capture", key=descriptor.key),
            details={"option": "dataset", "value": descriptor.key, "reason": "capture"},
        )
    return get_provider(descriptor.provider).adapter.archive_files(
        descriptor, years=years, months=months, params=params, stations=stations
    )


def _minimum_year(years: tuple[int, ...], descriptor: DatasetDescriptor) -> None:
    """Reject years before ``first_year`` of the dataset (``details.minimum``)."""
    if descriptor.first_year is not None and years[0] < descriptor.first_year:
        raise ObserwatorValidationError(
            message(
                "datasets.invalid_years_dataset_first_year",
                key=descriptor.key,
                first_year=descriptor.first_year,
            ),
            details={
                "option": "years",
                "value": list(years),
                "minimum": descriptor.first_year,
            },
        )


def _parse_stations(
    stations: Iterable[str], provider: ProviderDescriptor
) -> tuple[str, ...]:
    """Station codes of the provider's grammar, sorted, without duplicates."""
    if isinstance(stations, str) or not isinstance(stations, Iterable):
        raise ObserwatorValidationError(
            message("datasets.option_stations_must_list_station"),
            details={"option": "stations", "value": str(stations)},
        )
    items = list(stations)
    pattern = re.compile(provider.station_code_pattern)
    invalid = [
        str(item)
        for item in items
        if not isinstance(item, str) or not pattern.fullmatch(item)
    ]
    if not items or invalid:
        raise ObserwatorValidationError(
            message(
                "datasets.invalid_station_codes_expected_least",
                short_name=provider.short_name,
                codes=", ".join(invalid) or message("common.none"),
                station_code_pattern=provider.station_code_pattern,
            ),
            details={"option": "stations", "value": invalid},
        )
    return tuple(sorted(set(items)))


# Files of each station-source dataset (ADR-015): the provider's station lists and
# the station metadata its catalog is built from, with their fixed names; the
# daily ``meta1-<YYYYMMDD>.json`` of ``cz.chmu.meteo_now``, the newest of its listing,
# is a file of its adapter's. Each file of hydro.imgw.pl's station details (hydro and
# meteo) gathers one answer per station (ADR-021).
_STATION_FILES: Mapping[str, tuple[str, ...]] = MappingProxyType(
    {
        "pl.imgw.hydro_stations": ("lista_stacji_hydro.csv",),
        "pl.imgw.meteo_stations": ("wykaz_stacji.csv",),
        "pl.imgw.hydro_now": ("hydro",),
        "pl.imgw.meteo_now": ("meteo",),
        HYDRO_DETAILS: ("status",),
        METEO_DETAILS: ("status",),
        "cz.chmu.hydro_stations": ("meta1.json",),
        "cz.chmu.meteo_stations": ("meta1.json",),
        "cz.chmu.hydro_now": ("meta1.json", "meta3.json"),
        "cz.chmu.meteo_now": (),
        "cz.chmu.groundwater_stations": ("meta1.json",),
        "cz.chmu.groundwater_now": ("meta1.json",),
        _GDANSKIEWODY_STATIONS: ("stations",),
        # The capture of the pages of PIG-PIB's points layer (ADR-035).
        _PIG_STATIONS: ("MWP_points.jsonl.gz",),
        # The station file of each provider fed by files (ADR-033).
        **{
            f"{provider.key_prefix}.station_list": (STATIONS_FILE,)
            for provider in _FILES.files
        },
    }
)


def _fixed_station_file(descriptor: DatasetDescriptor, name: str) -> ArchiveFile | None:
    """A file with a fixed name of a station-source dataset; None for another name."""
    if name in _STATION_FILES.get(descriptor.key, ()):
        return _archive(descriptor, f"{descriptor.server_dir}/{name}", None)
    return None


def _station_file(descriptor: DatasetDescriptor, name: str) -> ArchiveFile | None:
    """A file of a station-source dataset by its name; None when it is no file of it."""
    return get_provider(descriptor.provider).adapter.station_file(descriptor, name)


def _station_files(dataset: str, /) -> tuple[ArchiveFile, ...]:
    """The files with a fixed name of a station-source dataset (none for ``cz.chmu.meteo_now``)."""
    descriptor = get_dataset(dataset)
    found: list[ArchiveFile] = []
    for name in _STATION_FILES[descriptor.key]:
        # Each provider's adapter names its files (a provider fed by files, the path
        # of the operator's file).
        archive = _station_file(descriptor, name)
        assert archive is not None  # a fixed name is a file of the dataset
        found.append(archive)
    return tuple(found)


def station_source_files(*, provider: str = "IMGW") -> tuple[ArchiveFile, ArchiveFile]:
    """
    Return the two station list sources of a provider as archive descriptors.

    Parameters
    ----------
    provider : str, optional
        Provider identifier or key prefix (see `get_provider`).

    Returns
    -------
    tuple of (ArchiveFile, ArchiveFile)
        Hydrological and meteorological station lists, with ``year=None``
        and ``year_type="none"``: for IMGW-PIB ``lista_stacji_hydro.csv``
        and ``wykaz_stacji.csv``, for ČHMÚ the two ``historical`` metadata
        files ``meta1.json``.

    Raises
    ------
    ObserwatorValidationError
        If ``provider`` names no provider.
    """
    hydro, meteo, _, _ = get_provider(provider).adapter.station_sources
    return _station_files(hydro)[0], _station_files(meteo)[0]


def _archive_from_path(dataset: str, server_path: str, /) -> ArchiveFile | None:
    """
    Recreate the `ArchiveFile` of a server path offline (reverse of `archive_files`).

    Used for stored versions, plans and server listings: the descriptor equals
    the one `archive_files` (or `station_source_files`) gives for the path; a
    capture dataset's path is ``<server_dir>/<YYYY-MM-DD>.jsonl.gz`` (`_capture_file`).

    Parameters
    ----------
    dataset : str
        Key, slug or legacy alias of the dataset the path should belong to.
    server_path : str
        File path relative to the provider's ``base_url``.

    Returns
    -------
    ArchiveFile or None
        Descriptor of the file, or None if the path is no file of the
        dataset (e.g. another name in a listing).

    Raises
    ------
    ObserwatorValidationError
        If ``dataset`` names no dataset.
    """
    descriptor = get_dataset(dataset)
    if descriptor.archive_scope == CAPTURE_SCOPE:
        return _capture_from_path(descriptor, server_path)
    directory, _, name = server_path.rpartition("/")
    if descriptor.time_unit == "station_list":
        if directory != descriptor.server_dir:
            return None
        return _station_file(descriptor, name)
    if descriptor.server_dir is None:
        return None
    return get_provider(descriptor.provider).adapter.archive_from_path(
        descriptor, server_path
    )


def _source_address(descriptor: DatasetDescriptor, /) -> str:
    """The address of a dataset's server directory: its base URL and ``server_dir``."""
    base = descriptor.base_url or get_provider(descriptor.provider).base_url
    return base + (descriptor.server_dir or "")


def _capture_file(descriptor: DatasetDescriptor, day: date, /) -> ArchiveFile:
    """
    The file of a capture dataset's version of one UTC day (ADR-030 D3).

    Its server path is ``<server_dir>/<YYYY-MM-DD>.jsonl.gz`` (the slot
    ``archive:<key>:<YYYY-MM-DD>.jsonl.gz``) and its URL the address of the source
    whose answers it holds: no server publishes the file, the store seals it from
    the spool.
    """
    return ArchiveFile(
        descriptor.key,
        f"{descriptor.server_dir}/{day.isoformat()}{CAPTURE_SUFFIX}",
        _source_address(descriptor),
        day.year,
        day.month,
        None,
        "calendar",
        day,
        day,
    )


def _capture_from_path(
    descriptor: DatasetDescriptor, server_path: str, /
) -> ArchiveFile | None:
    """The file of a capture dataset's server path; None for any other path."""
    directory, _, name = server_path.rpartition("/")
    stem = name.removesuffix(CAPTURE_SUFFIX)
    if directory != descriptor.server_dir or stem == name:
        return None
    try:
        day = date.fromisoformat(stem)
    except ValueError:
        return None
    # Only the canonical form of the day names a file (not ``20261122``, say).
    return _capture_file(descriptor, day) if day.isoformat() == stem else None
