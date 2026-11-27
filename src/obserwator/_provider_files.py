"""
Provider files: an operator's own network declared as data, not code (ADR-033).

Decision I13 of Nogat's plan ``2026-11-21-obserwator-instance.md``: a provider fed by
files is declared in a TOML file beside ``nogat.toml`` and its stations and series
reach the stores by ``store import`` (`obserwator.store.import_files`); one adapter
of ADR-029 (`obserwator.providers.files.FileFedAdapter`) serves every such provider,
so no module compares a provider's id.

The key ``provider_files`` of ``[obserwator]`` in ``nogat.toml`` lists the files, each
path relative to the directory of ``nogat.toml`` (``~`` expanded). The registry
(`obserwator.datasets`) reads them once, as it is imported: a valid file adds a
provider with its datasets, attribution lines and adapter; a file with a problem adds
nothing and its problem (an `ObserwatorValidationError` whose ``details.option`` names
the field, ``provider_file.<field>``, and ``details.path`` the file) is reported by
``config show``, refuses the start of both servers and every ``store import``.

A provider file (paths in it relative to its own directory)::

    id = "SIEC"                       # A-Z and digits, 2-16, a letter first
    short_name = "Sieć Testowa"       # its name in texts
    name = "Sieć Testowa Operatora"   # its full name
    country = "PL"                    # PL or CZ: the border its stations are checked against
    source_class = "other"            # P11, S1: no state service is fed by files
    tier = "operational"              # verified, telemetry or operational (default)
    publication = "public"            # public or private (default) of an unverified tier
    stations = "siec/stations.geojson"

    [license]
    id = "CC-BY-4.0"
    url = "https://creativecommons.org/licenses/by/4.0/"
    terms_url = "https://example.org/terms"      # optional

    [attribution]
    line = "Źródło danych: …"         # the line every product with its data carries
    processed = "Dane … zostały przetworzone"    # optional: the processed line
    short = "Źródło: …"               # optional: the line as the GUI's strip shows it
    links = [["…", "https://…"]]      # optional: words of the shown line and their links

    [datasets.hydro_daily]            # hydro_daily, meteo_daily or groundwater_daily
    directory = "siec/hydro"          # the station files <code>.csv or <code>.parquet
    variables = { H = "cm", Q = "m3/s" }  # the registry's variables of the kind, its units
    year_type = "hydrological"        # optional: calendar (default) or hydrological

Its station codes are ``<id>-<code>``: the id, a hyphen and the operator's code
(`LOCAL_CODE`), so no code of one provider is a code of another (IMGW-PIB's nine
digits and ČHMÚ's WIGOS identifiers begin with a digit).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tomllib
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Literal

from obserwator._environment import ConfigFile
from obserwator.exceptions import ObserwatorValidationError
from obserwator.messages import Message, message

__all__ = [
    "CODE_GRAMMAR",
    "DATASET_KINDS",
    "KEY",
    "LOCAL_CODE",
    "STATIONS_FILE",
    "FileDataset",
    "LoadedFiles",
    "ProviderFile",
    "load_provider_files",
    "read_provider_file",
]

KEY = "provider_files"
"""The key of ``[obserwator]`` in ``nogat.toml`` that lists the provider files."""
FIELDS: tuple[str, ...] = (
    "id",
    "short_name",
    "name",
    "country",
    "source_class",
    "tier",
    "publication",
    "stations",
    "license",
    "attribution",
    "datasets",
)
"""The fields of a provider file, in the order of its documentation."""
_REQUIRED: tuple[str, ...] = (
    "id",
    "short_name",
    "name",
    "country",
    "source_class",
    "stations",
    "license",
    "attribution",
    "datasets",
)
_LICENSE_FIELDS: tuple[str, ...] = ("id", "url", "terms_url")
_ATTRIBUTION_FIELDS: tuple[str, ...] = ("line", "processed", "short", "links")
_DATASET_FIELDS: tuple[str, ...] = ("directory", "variables", "year_type")
DATASET_KINDS: Mapping[str, Literal["hydro", "meteo", "groundwater"]] = (
    MappingProxyType(
        {
            "hydro_daily": "hydro",
            "meteo_daily": "meteo",
            "groundwater_daily": "groundwater",
        }
    )
)
"""The datasets a provider file may declare, by name, with the kind of each."""
COUNTRIES: tuple[str, ...] = ("PL", "CZ")
"""The countries whose packaged border checks the stations (ADR-018)."""
SOURCE_CLASSES: tuple[str, ...] = ("other",)
"""The source class of a provider fed by files (Nogat plan 2026-11-20, P11)."""
TIERS: tuple[str, ...] = ("verified", "telemetry", "operational")
"""The tiers of ADR-030 D1."""
PUBLICATIONS: tuple[str, ...] = ("public", "private")
"""The publication states of P15 (ADR-030 D5)."""
YEAR_TYPES: tuple[str, ...] = ("calendar", "hydrological")
"""How the years of a dataset's series are counted."""
STATIONS_FILE = "stations.geojson"
"""The name of the station file in the raw root, whatever the operator's file is called."""
LOCAL_CODE = r"[A-Za-z0-9][A-Za-z0-9_-]{0,31}"
"""The operator's part of a station code: 1 to 32 letters, digits, ``_`` or ``-``."""
CODE_GRAMMAR = rf"[A-Z][A-Z0-9]{{1,15}}-{LOCAL_CODE}"
"""A station code of any provider fed by files: ``<id>-<operator's code>``."""
MAX_BYTES = 100_000
"""The largest provider file read."""
SHORT_NAME_MAX = 40
NAME_MAX = 200
LINE_MAX = 500
_ID = re.compile(r"[A-Z][A-Z0-9]{1,15}")
_URL = re.compile(r"https?://[^\s]+")
_LICENSE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9.+_-]{0,63}")


@dataclass(frozen=True)
class FileDataset:
    """
    One dataset a provider file declares: the daily series of one kind of station.

    Attributes
    ----------
    name : {"hydro_daily", "meteo_daily", "groundwater_daily"}
        Its name, the last part of its key.
    kind : {"hydro", "meteo", "groundwater"}
        The kind of its stations.
    directory : str
        The directory of its station files as the provider file names it.
    path : pathlib.Path
        That directory, absolute.
    variables : Mapping of str to str
        Its variables and their units, in the order of the file.
    year_type : {"calendar", "hydrological"}
        How the years of its series are counted.
    """

    name: str
    kind: Literal["hydro", "meteo", "groundwater"]
    directory: str
    path: Path
    variables: Mapping[str, str]
    year_type: Literal["calendar", "hydrological"]


@dataclass(frozen=True)
class ProviderFile:
    """
    A valid provider file: one provider fed by files (I13).

    Attributes
    ----------
    path : pathlib.Path
        The file, absolute.
    sha256 : str
        SHA-256 of its bytes.
    id : str
        The provider's id (``ProviderDescriptor.id``).
    short_name, name : str
        Its name in texts and its full name.
    country : {"PL", "CZ"}
        Its country: the packaged border its stations are checked against.
    source_class : {"other"}
        Its source class (P11; ``other``, its only value, S2).
    tier : {"verified", "telemetry", "operational"}
        The tier of its data (ADR-030 D1).
    publication : {"public", "private"} or None
        The publication state of its data when ``[obserwator.capture]`` says nothing
        (P15); None for the tier ``verified``, which has none.
    stations : str
        Its station file as the provider file names it.
    stations_path : pathlib.Path
        That file, absolute.
    license_id, license_url : str
        The licence of its data and the address of its text.
    terms_url : str or None
        The address of the provider's terms, if any.
    line : str
        The attribution line every product with its data carries (DEV §20).
    processed : str or None
        The line a processed product carries besides `line`, if any.
    short : str or None
        The line as the strip of a GUI view shows it, if not whole.
    links : tuple of (str, str)
        Words of the shown line and the addresses they link.
    datasets : tuple of FileDataset
        Its datasets, in the order of `DATASET_KINDS`.
    """

    path: Path
    sha256: str
    id: str
    short_name: str
    name: str
    country: Literal["PL", "CZ"]
    source_class: Literal["other"]
    tier: Literal["verified", "telemetry", "operational"]
    publication: Literal["public", "private"] | None
    stations: str
    stations_path: Path
    license_id: str
    license_url: str
    terms_url: str | None
    line: str
    processed: str | None
    short: str | None
    links: tuple[tuple[str, str], ...]
    datasets: tuple[FileDataset, ...]

    @property
    def acronym(self) -> str:
        """The id in lower case: the first part of its slugs and store directories."""
        return self.id.lower()

    @property
    def key_prefix(self) -> str:
        """The prefix of its dataset keys, ``<country>.<acronym>`` (``pl.siec``)."""
        return f"{self.country.lower()}.{self.acronym}"

    @property
    def station_code_pattern(self) -> str:
        """The grammar of its station codes, ``^<id>-<operator's code>$``."""
        return rf"^{self.id}-{LOCAL_CODE}$"

    def dataset_title(self, kind: Literal["hydro", "meteo", "groundwater"]) -> Message:
        """
        The title of its daily dataset of a kind of station, without its tier's words.

        Parameters
        ----------
        kind : {"hydro", "meteo", "groundwater"}
            The kind of the dataset's stations.

        Returns
        -------
        Message
            ``<short name> — daily … data``; the registry adds the words of an
            unverified tier (`obserwator.datasets`), a GUI labels the tier itself.
        """
        if kind == "hydro":
            return message("provider_files.title_hydro_daily", provider=self.short_name)
        if kind == "meteo":
            return message("provider_files.title_meteo_daily", provider=self.short_name)
        return message(
            "provider_files.title_groundwater_daily", provider=self.short_name
        )

    def screen_line(self) -> dict[str, object]:
        """
        The line as Nogat kit's ``<nogat-sources screen-lines>`` declares it (kit 1.2.0).

        Returns
        -------
        dict of str to object
            ``text`` (`line` byte for byte), ``short`` and ``links`` when given.
        """
        item: dict[str, object] = {"text": self.line}
        if self.short is not None:
            item["short"] = self.short
        if self.links:
            item["links"] = [list(pair) for pair in self.links]
        return item


@dataclass(frozen=True)
class LoadedFiles:
    """
    The provider files of ``nogat.toml``, read once (`load_provider_files`).

    Attributes
    ----------
    paths : tuple of pathlib.Path
        Every file listed, in the order of ``provider_files``.
    files : tuple of ProviderFile
        The valid ones, in the same order.
    problems : tuple of ObserwatorValidationError
        One per file that could not be used (or one for a ``provider_files`` that is
        no list of paths).
    base : pathlib.Path
        The directory of ``nogat.toml``, absolute: a relative path of
        ``provider_files`` lies in it.
    """

    paths: tuple[Path, ...]
    files: tuple[ProviderFile, ...]
    problems: tuple[ObserwatorValidationError, ...]
    base: Path

    def resolve(self, path: str | os.PathLike[str], /) -> Path:
        """
        A path as ``provider_files`` names a file: ``~`` expanded, a relative one to `base`.

        Parameters
        ----------
        path : str or os.PathLike
            The path given, e.g. ``--provider-file`` of ``store import``.

        Returns
        -------
        pathlib.Path
            The path, absolute.
        """
        return _relative(self.base, path)

    def find(self, path: str | os.PathLike[str], /) -> ProviderFile | None:
        """
        The valid file at ``path`` (`resolve`); None when ``provider_files`` lists none.

        Parameters
        ----------
        path : str or os.PathLike
            The path given; it names a file when both lead to the same place (links
            followed, ``..`` removed).

        Returns
        -------
        ProviderFile or None
            The provider file found.
        """
        wanted = self.resolve(path).resolve()
        return next(
            (item for item in self.files if item.path.resolve() == wanted), None
        )


def _invalid(
    path: Path | None, option: str, text: Message, /, **details: object
) -> ObserwatorValidationError:
    """A problem of a provider file: ``details.option`` names its field."""
    found: dict[str, object] = {"option": option}
    if path is not None:
        found["path"] = str(path)
    found.update(details)
    return ObserwatorValidationError(text, details=found)


def _shown(value: object) -> str:
    """A value as a problem names it: JSON, at most 80 characters."""
    return json.dumps(value, default=str, ensure_ascii=False)[:80]


def _line(
    path: Path,
    table: Mapping[str, Any],
    name: str,
    option: str,
    maximum: int,
    *,
    required: bool,
) -> str | None:
    """A text field of one line, without white space at its ends."""
    value = table.get(name)
    if value is None:
        if required:
            raise _invalid(
                path, option, message("provider_files.missing_field", field=option)
            )
        return None
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or not value.isprintable()
        or len(value) > maximum
    ):
        raise _invalid(
            path,
            option,
            message(
                "provider_files.bad_text",
                field=option,
                value=_shown(value),
                maximum=maximum,
            ),
        )
    return value


def _url(path: Path, value: str | None, option: str) -> str | None:
    """An address of http or https, or None."""
    if value is not None and not _URL.fullmatch(value):
        raise _invalid(
            path,
            option,
            message("provider_files.bad_url", field=option, value=_shown(value)),
        )
    return value


def _choice(
    path: Path,
    table: Mapping[str, Any],
    name: str,
    option: str,
    allowed: tuple[str, ...],
    default: str | None,
) -> str:
    """A field with one of ``allowed`` values; ``default`` when absent (None: required)."""
    value = table.get(name, default)
    if value is None:
        raise _invalid(
            path, option, message("provider_files.missing_field", field=option)
        )
    if value not in allowed:
        raise _invalid(
            path,
            option,
            message(
                "provider_files.bad_choice",
                field=option,
                value=_shown(value),
                allowed=", ".join(allowed),
            ),
            allowed=list(allowed),
        )
    return str(value)


def _fields(
    path: Path, table: object, option: str, allowed: tuple[str, ...]
) -> Mapping[str, Any]:
    """A table of the file with no field outside ``allowed``."""
    if not isinstance(table, dict):
        raise _invalid(path, option, message("provider_files.not_table", field=option))
    for name in table:
        if name not in allowed:
            field = f"{option}.{name}"
            raise _invalid(
                path,
                field,
                message(
                    "provider_files.unknown_field",
                    field=field,
                    allowed=", ".join(allowed),
                ),
                allowed=list(allowed),
            )
    return table


def _relative(base: Path, value: str | os.PathLike[str]) -> Path:
    """A path of the file: ``~`` expanded, a relative one to the file's directory."""
    found = Path(value).expanduser()
    return found if found.is_absolute() else base / found


def _links(
    path: Path, value: object, shown: str, option: str
) -> tuple[tuple[str, str], ...]:
    """``attribution.links``: pairs of a word of the shown line and its address."""
    if value is None:
        return ()
    if not isinstance(value, list):
        raise _invalid(path, option, message("provider_files.bad_links"))
    pairs: list[tuple[str, str]] = []
    for item in value:
        if (
            not isinstance(item, list)
            or len(item) != 2
            or not all(isinstance(part, str) and part for part in item)
        ):
            raise _invalid(path, option, message("provider_files.bad_links"))
        word, address = item
        _url(path, address, option)
        if word not in shown:
            raise _invalid(
                path,
                option,
                message("provider_files.link_not_shown", word=word, line=shown),
            )
        pairs.append((word, address))
    return tuple(pairs)


def _variables(
    path: Path,
    value: object,
    option: str,
    kind: str,
    known: Mapping[str, Mapping[str, str]],
) -> Mapping[str, str]:
    """The variables of a dataset: the registry's of its kind, each with its unit."""
    vocabulary = known.get(kind, {})
    if not isinstance(value, dict) or not value:
        raise _invalid(
            path,
            option,
            message(
                "provider_files.bad_variables",
                field=option,
                allowed=", ".join(
                    f"{name} [{unit}]" for name, unit in vocabulary.items()
                ),
            ),
        )
    found: dict[str, str] = {}
    for name, unit in value.items():
        if name not in vocabulary:
            raise _invalid(
                path,
                f"{option}.{name}",
                message(
                    "provider_files.unknown_variable",
                    variable=name,
                    kind=kind,
                    allowed=", ".join(vocabulary),
                ),
                allowed=list(vocabulary),
            )
        if unit != vocabulary[name]:
            raise _invalid(
                path,
                f"{option}.{name}",
                message(
                    "provider_files.bad_unit",
                    variable=name,
                    unit=_shown(unit),
                    expected=vocabulary[name],
                ),
            )
        found[name] = vocabulary[name]
    return MappingProxyType(found)


def _datasets(
    path: Path, value: object, known: Mapping[str, Mapping[str, str]], prefix: str
) -> tuple[FileDataset, ...]:
    """The datasets of the file, in the order of `DATASET_KINDS`."""
    table = _fields(path, value, f"{prefix}.datasets", tuple(DATASET_KINDS))
    if not table:
        raise _invalid(path, f"{prefix}.datasets", message("provider_files.no_dataset"))
    found: list[FileDataset] = []
    for name, kind in DATASET_KINDS.items():
        if name not in table:
            continue
        option = f"{prefix}.datasets.{name}"
        entry = _fields(path, table[name], option, _DATASET_FIELDS)
        directory = _line(
            path, entry, "directory", f"{option}.directory", 1000, required=True
        )
        assert directory is not None
        variables = _variables(
            path, entry.get("variables"), f"{option}.variables", kind, known
        )
        year_type = _choice(
            path, entry, "year_type", f"{option}.year_type", YEAR_TYPES, "calendar"
        )
        found.append(
            FileDataset(
                name,
                kind,
                directory,
                _relative(path.parent, directory),
                variables,
                "hydrological" if year_type == "hydrological" else "calendar",
            )
        )
    return tuple(found)


def read_provider_file(
    path: Path,
    /,
    *,
    reserved: Collection[str],
    variables: Mapping[str, Mapping[str, str]],
) -> ProviderFile:
    """
    Read and check one provider file; nothing else is read (its data files neither).

    Parameters
    ----------
    path : pathlib.Path
        The file, absolute.
    reserved : Collection of str
        Names a provider fed by files may not take, in lower case: the ids and
        acronyms of the packaged providers and the names of the attribution origins.
    variables : Mapping of str to Mapping of str to str
        The registry's variables of a daily series of each kind of station with their
        units: those a dataset of the file may declare.

    Returns
    -------
    ProviderFile
        The provider.

    Raises
    ------
    ObserwatorValidationError
        The first problem: ``details.option`` names the field (``provider_file`` for
        the file itself, ``provider_file.<field>``, ``provider_file.datasets.<name>
        .<field>``) and ``details.path`` the file.
    """
    option = "provider_file"
    try:
        data = path.read_bytes()
    except FileNotFoundError as exc:
        raise _invalid(
            path, option, message("provider_files.file_missing", path=path)
        ) from exc
    except OSError as exc:
        raise _invalid(
            path,
            option,
            message(
                "provider_files.file_unreadable",
                path=path,
                reason=exc.strerror or str(exc),
            ),
        ) from exc
    if len(data) > MAX_BYTES:
        raise _invalid(
            path,
            option,
            message("provider_files.file_too_large", path=path, maximum=MAX_BYTES),
        )
    try:
        document = tomllib.loads(data.decode("utf-8"))
    except UnicodeDecodeError as exc:
        raise _invalid(
            path, option, message("provider_files.not_utf8", path=path)
        ) from exc
    except tomllib.TOMLDecodeError as exc:
        raise _invalid(
            path, option, message("provider_files.not_toml", path=path, reason=str(exc))
        ) from exc

    def invalid(field: str, text: Message, /, **details: object) -> Exception:
        return _invalid(path, f"{option}.{field}", text, **details)

    def text(table: Mapping[str, Any], field: str, maximum: int) -> str:
        found = _line(
            path,
            table,
            field.rpartition(".")[2],
            f"{option}.{field}",
            maximum,
            required=True,
        )
        assert found is not None  # required: _line raised without it
        return found

    def optional(table: Mapping[str, Any], field: str, maximum: int) -> str | None:
        name = field.rpartition(".")[2]
        return _line(path, table, name, f"{option}.{field}", maximum, required=False)

    table = _fields(path, document, option, FIELDS)
    for name in _REQUIRED:
        if name not in table:
            raise invalid(
                name, message("provider_files.missing_field", field=f"{option}.{name}")
            )
    identifier = table["id"]
    if not isinstance(identifier, str) or not _ID.fullmatch(identifier):
        raise invalid("id", message("provider_files.bad_id", value=_shown(identifier)))
    if identifier.lower() in reserved:
        raise invalid("id", message("provider_files.reserved_id", value=identifier))
    short_name = text(table, "short_name", SHORT_NAME_MAX)
    name = text(table, "name", NAME_MAX)
    country = _choice(path, table, "country", f"{option}.country", COUNTRIES, None)
    _choice(path, table, "source_class", f"{option}.source_class", SOURCE_CLASSES, None)
    tier = _choice(path, table, "tier", f"{option}.tier", TIERS, "operational")
    publication: str | None = None
    if tier == "verified":
        if "publication" in table:
            raise invalid(
                "publication", message("provider_files.publication_of_verified")
            )
    else:
        publication = _choice(
            path, table, "publication", f"{option}.publication", PUBLICATIONS, "private"
        )
    stations = text(table, "stations", 1000)
    licence = _fields(path, table["license"], f"{option}.license", _LICENSE_FIELDS)
    license_id = text(licence, "license.id", 64)
    if not _LICENSE_ID.fullmatch(license_id):
        raise invalid(
            "license.id", message("provider_files.bad_license_id", value=license_id)
        )
    license_url = text(licence, "license.url", 1000)
    _url(path, license_url, f"{option}.license.url")
    terms_url = optional(licence, "license.terms_url", 1000)
    _url(path, terms_url, f"{option}.license.terms_url")
    lines = _fields(
        path, table["attribution"], f"{option}.attribution", _ATTRIBUTION_FIELDS
    )
    line = text(lines, "attribution.line", LINE_MAX)
    processed = optional(lines, "attribution.processed", LINE_MAX)
    if processed is not None and processed == line:
        raise invalid(
            "attribution.processed", message("provider_files.processed_is_line")
        )
    short = optional(lines, "attribution.short", LINE_MAX)
    links = _links(
        path, lines.get("links"), short or line, f"{option}.attribution.links"
    )
    datasets = _datasets(path, table["datasets"], variables, option)
    return ProviderFile(
        path=path,
        sha256=hashlib.sha256(data).hexdigest(),
        id=identifier,
        short_name=short_name,
        name=name,
        country="CZ" if country == "CZ" else "PL",
        source_class="other",
        tier="verified"
        if tier == "verified"
        else "telemetry"
        if tier == "telemetry"
        else "operational",
        publication=None
        if publication is None
        else "public"
        if publication == "public"
        else "private",
        stations=stations,
        stations_path=_relative(path.parent, stations),
        license_id=license_id,
        license_url=license_url,
        terms_url=terms_url,
        line=line,
        processed=processed,
        short=short,
        links=links,
        datasets=datasets,
    )


def load_provider_files(
    config: ConfigFile,
    /,
    *,
    reserved: Collection[str],
    variables: Mapping[str, Mapping[str, str]],
) -> LoadedFiles:
    """
    Read the provider files ``nogat.toml`` lists (``[obserwator] provider_files``).

    Parameters
    ----------
    config : ConfigFile
        ``nogat.toml`` as `obserwator._environment.config_file` read it.
    reserved : Collection of str
        As `read_provider_file`.
    variables : Mapping of str to Mapping of str to str
        As `read_provider_file`.

    Returns
    -------
    LoadedFiles
        The files listed, the valid ones and the problem of each other; a second
        file declaring an id already declared is a problem of its own.
    """
    base = config.path.parent.absolute()
    value = config.sections.get("obserwator", {}).get(KEY)
    if value is None:
        return LoadedFiles((), (), (), base)
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item for item in value
    ):
        problem = _invalid(
            config.path, KEY, message("provider_files.bad_list", key=KEY)
        )
        return LoadedFiles((), (), (problem,), base)
    paths = tuple(dict.fromkeys(_relative(base, item) for item in value))
    files: list[ProviderFile] = []
    problems: list[ObserwatorValidationError] = []
    taken = set(reserved)
    for path in paths:
        try:
            found = read_provider_file(path, reserved=taken, variables=variables)
        except ObserwatorValidationError as exc:
            problems.append(exc)
            continue
        taken.add(found.acronym)
        files.append(found)
    return LoadedFiles(paths, tuple(files), tuple(problems), base)
