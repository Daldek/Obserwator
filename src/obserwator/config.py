"""
Settings of the servers and the CLI: environment, ``.env`` and ``nogat.toml`` (DEV-18).

A setting comes from the first of: the environment variable ``OBSERWATOR_<KEY>``, the
same key in a ``.env`` file of the working directory, the shared variable
``NOGAT_<KEY>`` (keys ``data_dir``, ``cache_dir``, ``state_dir``, ``lang``), the section
``[obserwator]`` of ``nogat.toml``, the section ``[nogat]`` of it (shared keys), the
default; a command-line option goes before all of them. The store write token, the
GUI's admin key and a provider's API key (`provider_key`) are credentials: only the
environment (and ``.env``) may give them, or a file the environment names, never
``nogat.toml`` (DEV-18.4). `environment_report` is the document of ``obserwator config
show --json`` (DEV-18.6); `check_config` rejects an unusable ``nogat.toml``;
`credential_problems` and `check_credentials` find a weak key or token and
`check_root_layout` a root of an unknown layout as a server starts (ADR-025).
"""

import codecs
import logging
import os
import stat
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any, Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import (
    BaseSettings,
    DotEnvSettingsSource,
    EnvSettingsSource,
    NoDecode,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

from obserwator import _environment as environment
from obserwator._provider_files import KEY as PROVIDER_FILES
from obserwator._version import __version__
from obserwator.datasets import (
    ProviderCredential,
    ProviderDescriptor,
    get_provider,
    provider_files,
    providers,
)
from obserwator.exceptions import (
    ObserwatorError,
    ObserwatorStoreError,
    ObserwatorValidationError,
)
from obserwator.messages import LANGS, Lang, message
from obserwator.output import DATA_MARKER, STORE_MARKER

if TYPE_CHECKING:
    from obserwator.store.types import RootKind

__all__ = [
    "SECRET_MIN_BYTES",
    "Settings",
    "StoreRoot",
    "check_config",
    "check_credentials",
    "check_root_layout",
    "configured_token",
    "credential_error",
    "credential_keys",
    "credential_problems",
    "credential_providers",
    "environment_report",
    "human_language",
    "provider_key",
    "read_secret_file",
    "settings",
    "store_root",
]

_LOG = logging.getLogger(__name__)


class _NogatEnvSource(PydanticBaseSettingsSource):
    """The shared variables ``NOGAT_<KEY>`` of the keys of `environment.SHARED_KEYS`."""

    def get_field_value(self, field: Any, field_name: str) -> tuple[Any, str, bool]:
        """Not used: `__call__` reads the shared keys at once."""
        return None, field_name, False

    def __call__(self) -> dict[str, Any]:
        """Values of the shared variables that are set (non-empty)."""
        names = {
            key: f"{environment.SHARED_PREFIX}{key.upper()}"
            for key in environment.SHARED_KEYS
        }
        return {
            key: value for key, name in names.items() if (value := os.environ.get(name))
        }


class _FileSource(PydanticBaseSettingsSource):
    """One table of ``nogat.toml``: every setting in ``[obserwator]``, shared keys in ``[nogat]``."""

    def __init__(self, settings_cls: type[BaseSettings], section: str) -> None:
        super().__init__(settings_cls)
        self.section = section

    def get_field_value(self, field: Any, field_name: str) -> tuple[Any, str, bool]:
        """Not used: `__call__` reads the table at once."""
        return None, field_name, False

    def __call__(self) -> dict[str, Any]:
        """Settings of the table; credentials and unknown keys are left out."""
        table = environment.config_file().sections.get(self.section, {})
        known = (
            environment.SHARED_KEYS
            if self.section == environment.APP
            else tuple(self.settings_cls.model_fields)
        )
        return {
            key: value
            for key, value in table.items()
            if key in known and key not in environment.CREDENTIAL_KEYS
        }


def _file_sources(
    settings_cls: type[BaseSettings],
) -> tuple[PydanticBaseSettingsSource, ...]:
    """The sources below ``.env`` in the order of DEV-18.1."""
    return (
        _NogatEnvSource(settings_cls),
        _FileSource(settings_cls, environment.TOOL),
        _FileSource(settings_cls, environment.APP),
    )


class Settings(BaseSettings):
    """Settings loaded from the environment, ``.env`` and ``nogat.toml``."""

    model_config = SettingsConfigDict(
        env_prefix=environment.PREFIX,
        env_file=".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
    )

    # Environment
    env: Literal["development", "production"] = "development"

    # API Server
    host: str = "0.0.0.0"
    port: int = 8000

    # Directories (DEV-18.2): stores live in <data_dir>/obserwator (the data root) and
    # <data_dir>/obserwator-raw (the raw root), caches in <cache_dir>/obserwator and
    # the servers' logs in <state_dir>/obserwator/logs (Nogat DEV-12.6, `log_dir`).
    # None is the working directory. The reference data of
    # IMGW-PIB (hydro_stations_locations.csv, desc/) is fetched again at will,
    # so it lives in the cache, and the state of the REST server (API keys) in
    # the data directory of the tool.
    data_dir: Path = Field(default_factory=environment.default_data_dir)
    cache_dir: Path = Field(default_factory=environment.default_cache_dir)
    state_dir: Path = Field(default_factory=environment.default_state_dir)
    reference_dir: Path = Field(
        default_factory=lambda data: data["cache_dir"] / environment.TOOL / "reference"
    )

    # API Keys
    api_keys_file: Path = Field(
        default_factory=lambda data: (
            data["data_dir"] / environment.TOOL / "api_keys.json"
        )
    )

    # Rate limiting (requests per hour, 0 = unlimited)
    rate_limit: int = 100

    # The data root of the REST server (OBSERWATOR_ROOT, [obserwator] root; DEV-19.2,
    # ADR-017): series, station catalogs and analyses. A server writes only to its
    # configured roots, never to the default <data_dir>/obserwator, and the catalog
    # routes of commands with a root answer 503 store_unavailable without the root
    # of their kind. The CLI, the library and the MCP server use `store_root`.
    # Writes (POST without ?check=true) need both flags below and the X-API-Key
    # header; the token is compared in constant time and is a credential:
    # environment only, the variable or, without it, the text of the file
    # OBSERWATOR_STORE_WRITE_TOKEN_FILE names (a secret file of mode 0600, ADR-025).
    root: Path | None = None
    # The raw root (OBSERWATOR_RAW_ROOT, [obserwator] raw_root; ADR-017): the
    # downloaded archives, station sources and PMAXTP cells; the default of the CLI,
    # the library and the MCP server is <data_dir>/obserwator-raw.
    raw_root: Path | None = None
    store_writes_enabled: bool = False
    store_write_token: SecretStr | None = None
    store_write_token_file: Path | None = None
    # Server directory with user station-location CSVs offered to the catalog
    # route by file name only; unset disables the option (503).
    user_locations_dir: Path | None = None

    # Default and maximum page size of REST list commands (OBSERWATOR_API_MAX_LIMIT).
    api_max_limit: int = Field(default=1000, ge=1)
    # Browser origins allowed to call the REST server cross-origin (CORS;
    # OBSERWATOR_CORS_ORIGINS, [obserwator] cors_origins): comma-separated origins
    # (`https://example.org`, scheme and host with an optional port, no path) or `*`
    # for every origin. Empty (the default): no cross-origin access. Never with
    # credentials: the API authenticates with the X-API-Key header, not cookies.
    cors_origins: Annotated[list[str], NoDecode] = []

    # Language of the human-readable output of the CLI (OBSERWATOR_LANG): the help and the
    # progress and notice lines; "pl" or "en", checked where it is used (`human_language`),
    # so a wrong value fails every obserwator call with validation_error instead of this
    # module's import. Machine output (JSON, the error line) is English whatever it is;
    # REST and MCP ignore it.
    lang: str = "pl"

    # MCP over Streamable HTTP in obserwator server (spec 2026-10-19 §6.2, §6.9): the
    # /mcp endpoint exists only with OBSERWATOR_MCP_ENABLED=true and the mcp extra;
    # it answers only the Host names of OBSERWATOR_MCP_ALLOWED_HOSTS (comma-separated,
    # each with or without a port).
    mcp_enabled: bool = False
    mcp_allowed_hosts: Annotated[list[str], NoDecode] = ["127.0.0.1", "localhost"]
    # `obserwator mcp` starts in the write mode (OBSERWATOR_MCP_ALLOW_WRITES; --allow-writes).
    mcp_allow_writes: bool = False

    # The web GUI (obserwator gui serve, ADR-013). The basemap is a TileJSON address
    # drawn by the GUI's own style (OBSERWATOR_GUI_BASEMAP_URL; empty: no basemap, the
    # borders of Poland and Czechia only) with its credit line. The GUI limits the
    # requests of each client address to request_limit in request_window seconds
    # (Nogat DEV-15.9; static files are not counted).
    gui_basemap_url: str = "https://tiles.openfreemap.org/planet"
    gui_basemap_attribution: str = "OpenFreeMap © OpenMapTiles Data from OpenStreetMap"
    request_limit: int = Field(default=300, ge=1)
    request_window: int = Field(default=60, ge=1)
    # The key of the GUI's admin panel (Nogat DEV-15.13, ADR-020): the header X-Admin-Key
    # of api/admin/... must equal OBSERWATOR_ADMIN_API_KEY or, without it, the text of the
    # file OBSERWATOR_ADMIN_API_KEY_FILE names (a secret file of the service). Credentials:
    # environment only; the GUI reads them on every admin request. Not the REST API keys
    # of `obserwator admin` (api_keys_file).
    admin_api_key: SecretStr | None = None
    admin_api_key_file: Path | None = None

    # Hydrolog's program of the analyses (ADR-016; OBSERWATOR_HYDROLOG_COMMAND,
    # [obserwator] hydrolog_command): a command line, split as a shell splits it
    # (shlex); unset runs `hydrolog` found on PATH. No command option chooses it.
    # `analyses build` stores its results; the GUI runs it for a person's choices.
    hydrolog_command: str | None = None

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """Order the sources: environment, ``.env``, ``NOGAT_*``, ``nogat.toml``."""
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            *_file_sources(settings_cls),
            file_secret_settings,
        )

    @property
    def is_production(self) -> bool:
        """Check if running in production mode."""
        return self.env == "production"

    @property
    def log_dir(self) -> Path:
        """
        The directory of the servers' logs: ``<state_dir>/obserwator/logs``.

        ``obserwator server`` and ``obserwator gui serve`` write their access,
        application and lifecycle records there, one file per kind and UTC day,
        deleted after 14 days (Nogat DEV-12.6); absolute, ``~`` expanded.
        """
        return (self.state_dir / environment.TOOL / "logs").expanduser().absolute()

    @field_validator("mcp_allowed_hosts", "cors_origins", mode="before")
    @classmethod
    def _split_list(cls, value: object) -> object:
        """Split the comma-separated text of a list setting given as one text."""
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("cors_origins", mode="after")
    @classmethod
    def _bare_origins(cls, value: list[str]) -> list[str]:
        """Origins as a browser sends them: no trailing slash (``https://a.example/``)."""
        return [bare for origin in value if (bare := origin.strip().rstrip("/"))]


# Global settings instance
settings = Settings()


def human_language() -> Lang | None:
    """
    Language of the human-readable output of the CLI (``OBSERWATOR_LANG``, ``pl`` by default).

    Returns
    -------
    {"pl", "en"} or None
        The language, or None when the setting is neither ``pl`` nor ``en``
        (the CLI then ends every call with ``validation_error``).
    """
    value = settings.lang.strip()
    return value if value in LANGS else None


# Directory of the default root of each kind below <data_dir> (DEV-19.2, ADR-017 D5).
_DEFAULT_DIRS = {"data": environment.TOOL, "raw": f"{environment.TOOL}-raw"}
# Setting of the root of each kind.
_ROOT_KEYS = {"data": "root", "raw": "raw_root"}
# Marker of each kind of root.
_ROOT_MARKERS = {"data": DATA_MARKER, "raw": STORE_MARKER}


def _root_of(current: Settings, kind: "RootKind" = "data") -> Path:
    """
    The root of ``kind`` of ``current``: the setting, else its directory in ``data_dir``.

    The data root is ``root``, else ``<data_dir>/obserwator``; the raw root is
    ``raw_root``, else ``<data_dir>/obserwator-raw`` (DEV-19.2, ADR-017 D5).
    """
    setting: Path | None = getattr(current, _ROOT_KEYS[kind])
    chosen = setting if setting is not None else current.data_dir / _DEFAULT_DIRS[kind]
    return chosen.expanduser().absolute()


@dataclass(frozen=True)
class StoreRoot:
    """
    The default root of one kind, resolved without reading it (DEV-19.2, ADR-017).

    Attributes
    ----------
    root : pathlib.Path
        Absolute root. The data root: ``OBSERWATOR_ROOT``, the same key in
        ``.env``, ``[obserwator] root`` of ``nogat.toml``, else
        ``<data_dir>/obserwator``; the raw root: ``OBSERWATOR_RAW_ROOT``, the
        same key in ``.env``, ``[obserwator] raw_root``, else
        ``<data_dir>/obserwator-raw``; ``~`` expanded. The root need not exist
        yet.
    source : {"default", "env", "dotenv", "file"}
        The layer that gave ``root``.
    name : str or None
        The variable or the table that gave it; ``None`` for the default.
    marker_exists : bool
        Whether the marker of the kind (``obserwator-data.json`` of a data
        root, ``obserwator-store.json`` of a raw root) is a file in the root.
        The directory may be missing; then the marker does not exist either.
    """

    root: Path
    source: str
    name: str | None
    marker_exists: bool


def store_root(*, kind: "RootKind" = "data") -> StoreRoot:
    """
    Return the default root of a kind, its source and whether its marker exists.

    The read-only accessor of the default root that every Nogat producer
    exposes alike (DEV-19.2). The root is the one of a command without
    ``--root`` (``--raw-root`` of a build for the raw root) and of
    ``obserwator config show``, read now so that a later change of the
    environment counts; it looks for one file, the marker, and never creates,
    lists or measures anything, so the cost does not grow with the root
    (``environment_report`` measures the size). A server writes to
    ``Settings.root`` and ``Settings.raw_root`` only.

    Parameters
    ----------
    kind : {"data", "raw"}, optional
        Kind of root (ADR-017): ``"data"`` (series, station catalogs,
        analyses; the default) or ``"raw"`` (archives, station sources,
        PMAXTP cells).

    Returns
    -------
    StoreRoot
        ``root``, ``source`` (``default``, ``env``, ``dotenv`` or ``file``),
        ``name`` (the variable or the table) and ``marker_exists``.
    """
    root = _root_of(Settings(), kind)
    origin = _origin(_ROOT_KEYS[kind], _layers())
    name = origin["name"]
    return StoreRoot(
        root,
        str(origin["source"]),
        None if name is None else str(name),
        (root / _ROOT_MARKERS[kind]).is_file(),
    )


def check_config() -> None:
    """
    Reject a ``nogat.toml`` that exists but cannot be used.

    Raises
    ------
    ObserwatorValidationError
        If the file is unreadable, not UTF-8, not valid TOML, has a section that is
        not a table, or ``NOGAT_CONFIG`` names a file that does not exist. The
        message names the cause; ``details.reason`` is ``invalid_config`` (the
        same for every cause), ``details.option`` the variable or the file name
        and ``details.path`` the file.
    """
    file = environment.config_file()
    if file.error is not None:
        raise ObserwatorValidationError(
            message(
                "config.cannot_use_settings_file", path=file.path, error=file.error
            ),
            details={
                "option": environment.CONFIG_ENV
                if file.source == environment.CONFIG_ENV
                else environment.CONFIG_FILENAME,
                "path": str(file.path),
                "reason": "invalid_config",
            },
        )


SECRET_MIN_BYTES = 32
"""The shortest key or token in bytes (I10 of ADR-025): ``openssl rand -hex 32`` gives 64."""
_SECRETS: dict[str, tuple[str, str]] = {
    "token": ("store_write_token", "store_write_token_file"),
    "admin": ("admin_api_key", "admin_api_key_file"),
}
"""The credentials by their use: the REST server's write token, the GUI's admin key."""


def _variable(key: str) -> str:
    return f"{environment.PREFIX}{key.upper()}"


_UTF16_BOMS = {codecs.BOM_UTF16_LE: "UTF-16LE", codecs.BOM_UTF16_BE: "UTF-16BE"}
"""The encodings a Windows tool writes a text file in by its BOM (PowerShell 5.1's ``>``)."""


def _read_secret(path: Path) -> tuple[str | None, str | None]:
    """
    A secret file's text, and the encoding it holds instead of UTF-8.

    The text drops a UTF-8 BOM (Windows editors write one) and surrounding white
    space; it is None when the file is missing, unreadable, blank or not UTF-8. The
    encoding is None for UTF-8 text (or no file), ``UTF-16LE`` or ``UTF-16BE`` by
    the BOM, else ``""``: bytes that are no UTF-8.
    """
    try:
        data = path.expanduser().read_bytes()
    except OSError:
        return None, None
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return None, _UTF16_BOMS.get(data[:2], "")
    return text.strip() or None, None


def read_secret_file(path: Path) -> str | None:
    """
    The key or token a secret file holds, read now (ADR-025, I10).

    Parameters
    ----------
    path : Path
        The file a ``*_FILE`` variable names; ``~`` expanded.

    Returns
    -------
    str or None
        Its UTF-8 text without a BOM and surrounding white space; None when the file
        is missing, unreadable, blank or not UTF-8 (`credential_problems` names the
        last).
    """
    return _read_secret(path)[0]


def configured_token(current: "Settings | None" = None) -> str | None:
    """
    The REST server's store write token, read now.

    ``OBSERWATOR_STORE_WRITE_TOKEN`` as given, else the text of the file
    ``OBSERWATOR_STORE_WRITE_TOKEN_FILE`` names (`read_secret_file`: UTF-8, a BOM and
    surrounding white space dropped; ADR-025, I10), so a rotated file counts without
    a restart.

    Parameters
    ----------
    current : Settings or None, optional
        The settings; the module's `settings` by default.

    Returns
    -------
    str or None
        The token; None when neither gives one (blank, a missing or unreadable file,
        or one that is not UTF-8).
    """
    chosen = settings if current is None else current
    if chosen.store_write_token is not None:
        token = chosen.store_write_token.get_secret_value()
        if token:
            return token
    if chosen.store_write_token_file is None:
        return None
    return read_secret_file(chosen.store_write_token_file)


def _file_problems(path: Path, option: str) -> tuple[str, list[dict[str, str]]]:
    """The text of a key file and its problems: not UTF-8, open to group or others."""
    found, encoding = _read_secret(path)
    text = found or ""
    problems: list[dict[str, str]] = []
    if encoding is not None:
        problems.append(
            {
                "code": "secret_file_encoding",
                "option": option,
                "message": message(
                    "config.secret_file_encoding", name=option, encoding=encoding
                )
                if encoding
                else message("config.secret_file_not_utf8", name=option),
            }
        )
    try:
        mode = stat.S_IMODE(path.expanduser().stat().st_mode)
    except OSError:
        mode = 0
    if text and os.name != "nt" and mode & 0o077:
        problems.append(
            {
                "code": "secret_file_mode",
                "option": option,
                "message": message(
                    "config.secret_file_mode", name=option, mode=f"{mode:04o}"
                ),
            }
        )
    return text, problems


def credential_problems(
    use: Literal["token", "admin"] | None = None,
) -> list[dict[str, str]]:
    """
    The weak or unusable credentials in force (ADR-025, I10).

    A key or token shorter than `SECRET_MIN_BYTES` bytes, a key file that group or
    others may access (any permission bit but the owner's; not checked on Windows)
    and a key file that is not UTF-8 text (UTF-16 from Windows PowerShell 5.1, say),
    of which no key is read. Only the credential in force counts: the variable when
    it is set, else the file. A missing or unreadable file is no problem here: no key
    is set. A provider's API key (P3) has only the problems of its file: the
    provider, not the operator, chooses its length.

    Parameters
    ----------
    use : {"token", "admin"} or None, optional
        The REST server's write token, the GUI's admin key, or all of them and the
        provider keys (None).

    Returns
    -------
    list of dict
        ``code`` (``short_secret``, ``secret_file_mode`` or ``secret_file_encoding``),
        ``option`` (the variable) and ``message``; the secret itself is never named.
    """
    current = Settings()
    problems: list[dict[str, str]] = []
    for name, (value_key, file_key) in _SECRETS.items():
        if use is not None and name != use:
            continue
        value: SecretStr | None = getattr(current, value_key)
        path: Path | None = getattr(current, file_key)
        text = value.get_secret_value().strip() if value is not None else ""
        option = _variable(value_key)
        if not text and path is not None:
            option = _variable(file_key)
            text, found = _file_problems(path, option)
            problems.extend(found)
        if text and len(text.encode("utf-8")) < SECRET_MIN_BYTES:
            problems.append(
                {
                    "code": "short_secret",
                    "option": option,
                    "message": message(
                        "config.short_secret", name=option, minimum=SECRET_MIN_BYTES
                    ),
                }
            )
    if use is None:
        for provider in credential_providers():
            problems.extend(_provider_secret(provider)[1])
    return problems


def credential_keys() -> tuple[str, ...]:
    """
    The keys only the environment may give: `CREDENTIAL_KEYS` and the providers' (P3).

    Returns
    -------
    tuple of str
        ``environment.CREDENTIAL_KEYS`` followed by ``<stem>_api_key`` and
        ``<stem>_api_key_file`` of every provider declaring a `ProviderCredential`,
        in registry order; a key of ``[obserwator]`` among them is ignored as a
        credential (DEV-18.4).
    """
    return environment.CREDENTIAL_KEYS + tuple(
        variable.removeprefix(environment.PREFIX).lower()
        for provider in credential_providers()
        for variable in _provider_variables(provider)
    )


def credential_providers() -> tuple[ProviderDescriptor, ...]:
    """The providers whose requests need an API key (``credential`` set), in order."""
    return tuple(provider for provider in providers() if provider.credential)


def _provider_variables(provider: ProviderDescriptor) -> tuple[str, str]:
    credential = _credential_of(provider)
    return credential.variable, credential.file_variable


def _credential_of(provider: ProviderDescriptor) -> ProviderCredential:
    if provider.credential is None:
        raise ValueError(f"The provider {provider.id} declares no credential")
    return provider.credential


def _environment_value(variable: str) -> str | None:
    """
    A variable of the environment, else of ``.env``, as `Settings` reads them.

    Case-insensitive, an empty value unset; never ``nogat.toml`` (DEV-18.4).
    """
    name = variable.lower()
    for source in (EnvSettingsSource(Settings), DotEnvSettingsSource(Settings)):
        value = source.env_vars.get(name)
        if value is not None:
            return value
    return None


def _provider_secret(
    provider: ProviderDescriptor,
) -> tuple[str | None, list[dict[str, str]]]:
    """A provider's key now and the problems of its file, as the admin key's (ADR-020)."""
    variable, file_variable = _provider_variables(provider)
    text = (_environment_value(variable) or "").strip()
    if text:
        return text, []
    path = _environment_value(file_variable)
    if path is None or not path.strip():
        return None, []
    text, problems = _file_problems(Path(path.strip()), file_variable)
    return text or None, problems


def provider_key(provider: str, /) -> str:
    """
    The API key of a provider, read now (Nogat plan 2026-11-20, P3, P4).

    ``OBSERWATOR_<STEM>_API_KEY``, else the text of the file
    ``OBSERWATOR_<STEM>_API_KEY_FILE`` names (`read_secret_file`), from the
    environment or ``.env`` only, never from ``nogat.toml``; a key file group or
    others may access, or one that is not UTF-8, is a warning of the logger
    ``obserwator.config``. The key itself is never logged.

    Parameters
    ----------
    provider : str
        A provider declaring a `ProviderCredential`, by identifier or key prefix.

    Returns
    -------
    str
        The key without surrounding white space.

    Raises
    ------
    ObserwatorError
        ``forbidden`` with ``details.reason`` ``missing_credentials`` when neither
        variable gives a key (`credential_error`).
    ObserwatorValidationError
        If ``provider`` names no provider.
    ValueError
        If the provider declares no credential.
    """
    descriptor = get_provider(provider)
    key, problems = _provider_secret(descriptor)
    for problem in problems:
        _LOG.warning("%s", problem["message"])
    if key is None:
        raise credential_error(descriptor.id, "missing_credentials")
    return key


def credential_error(
    provider: str, reason: Literal["missing_credentials", "invalid_credentials"]
) -> ObserwatorError:
    """
    The error of a missing or rejected provider key (P4), for its caller to raise.

    An adapter raises it with ``invalid_credentials`` when the provider refuses the
    key (HTTP 401 or 403); `provider_key` raises it with ``missing_credentials``.

    Parameters
    ----------
    provider : str
        A provider declaring a `ProviderCredential`, by identifier or key prefix.
    reason : {"missing_credentials", "invalid_credentials"}
        No key is set, or the provider rejected it.

    Returns
    -------
    ObserwatorError
        ``forbidden`` (exit 12, HTTP 403) with ``details.reason`` and
        ``details.provider`` (the identifier) and a hint naming the variables.
    """
    descriptor = get_provider(provider)
    variable, file_variable = _provider_variables(descriptor)
    missing = reason == "missing_credentials"
    return ObserwatorError(
        message(
            "config.provider_key_missing"
            if missing
            else "config.provider_key_rejected",
            provider=descriptor.short_name,
        ),
        code="forbidden",
        details={"reason": reason, "provider": descriptor.id},
        hint=message(
            "config.provider_key_hint" if missing else "config.provider_key_renew",
            variable=variable,
            file_variable=file_variable,
        ),
    )


def check_credentials(use: Literal["token", "admin"], *, strict: bool) -> None:
    """
    Warn of a weak key or token, or refuse it, as a server starts (ADR-025, I10).

    Parameters
    ----------
    use : {"token", "admin"}
        The REST server's write token or the GUI's admin key.
    strict : bool
        Refuse instead of warning: a deployment with ``[obserwator.instance]``.

    Raises
    ------
    ObserwatorValidationError
        With ``strict``, for the first problem of `credential_problems`;
        ``details.option`` names the variable, ``details.reason`` the problem.
    """
    for problem in credential_problems(use):
        if strict:
            raise ObserwatorValidationError(
                message("config.secret_refused", problem=problem["message"]),
                details={"option": problem["option"], "reason": problem["code"]},
            )
        _LOG.warning("%s", problem["message"])


_UNKNOWN_LAYOUT = frozenset(
    {"unsupported_store", "invalid_marker", "conflicting_markers"}
)
"""The problems of `store_info` that mean a root this version cannot read."""


def check_root_layout(root: Path, kind: "RootKind" = "data") -> None:
    """
    Refuse a root whose layout this version does not read, as a server starts (I12).

    The marker's schema (``obserwator-data/1`` of a data root, ``obserwator-store/1``
    of a raw root) names the layout; an unknown schema, an unreadable marker or both
    markers stop the start with a hint. A missing root or marker does not: the GUI
    then shows its error, as before, and a later ``store init`` makes it.

    Parameters
    ----------
    root : Path
        The root a server serves.
    kind : {"data", "raw"}, optional
        Its kind, for the hint's schema.

    Raises
    ------
    ObserwatorStoreError
        Code ``store_unavailable``, ``details.reason`` ``unsupported_layout``.
    """
    from obserwator.store import store_info

    try:
        info = store_info(root)
    except ObserwatorError:
        return  # an unsafe path: every read refuses it, as before
    found = _UNKNOWN_LAYOUT.intersection(info.problem_codes)
    if info.supported or not found:
        return
    schema = "obserwator-data/1" if kind == "data" else "obserwator-store/1"
    raise ObserwatorStoreError(
        message(
            "config.unknown_layout",
            root=root,
            version=__version__,
            problems="; ".join(info.problems),
        ),
        code="store_unavailable",
        details={
            "reason": "unsupported_layout",
            "problem_codes": sorted(found),
            "schema": info.store_schema,
            "supported": dict(info.contracts),
        },
        hint=message("config.unknown_layout_hint", schema=schema),
    )


def _plain(value: object) -> object:
    """A setting value as JSON (paths as text)."""
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, list | tuple):
        return [_plain(item) for item in value]
    return value


def _layers() -> list[tuple[str, Callable[[str], str], PydanticBaseSettingsSource]]:
    """The sources of `Settings` with the label of their kind and the name of a key in it."""

    def variable(prefix: str) -> Callable[[str], str]:
        return lambda key: f"{prefix}{key.upper()}"

    nogat_env, obserwator_file, nogat_file = _file_sources(Settings)
    return [
        ("env", variable(environment.PREFIX), EnvSettingsSource(Settings)),
        ("dotenv", variable(environment.PREFIX), DotEnvSettingsSource(Settings)),
        ("env", variable(environment.SHARED_PREFIX), nogat_env),
        ("file", lambda key: f"[{environment.TOOL}]", obserwator_file),
        ("file", lambda key: f"[{environment.APP}]", nogat_file),
    ]


def _origin(
    key: str, layers: list[tuple[str, Callable[[str], str], PydanticBaseSettingsSource]]
) -> dict[str, object]:
    for source, name, layer in layers:
        if key in layer():
            return {"source": source, "name": name(key)}
    return {"source": "default", "name": None}


def _tree_size(root: Path) -> int:
    """Bytes of the files below ``root``; a hard-linked file counts once."""
    total = 0
    seen: set[tuple[int, int]] = set()
    pending = [root]
    while pending:
        try:
            with os.scandir(pending.pop()) as entries:
                for entry in entries:
                    if entry.is_dir(follow_symlinks=False):
                        pending.append(Path(entry.path))
                    elif entry.is_file(follow_symlinks=False):
                        # On Windows DirEntry.stat() leaves st_nlink, st_ino and
                        # st_dev at 0; only os.stat() reads them there.
                        info = (
                            os.stat(entry.path, follow_symlinks=False)
                            if os.name == "nt"
                            else entry.stat(follow_symlinks=False)
                        )
                        if info.st_nlink > 1:
                            identity = (info.st_dev, info.st_ino)
                            if identity in seen:
                                continue
                            seen.add(identity)
                        total += info.st_size
        except OSError:
            continue  # a directory that vanished or cannot be listed
    return total


def _provider_files_report() -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """
    The provider files of ``config show`` and their problems (ADR-033).

    Returns
    -------
    tuple of (list, list)
        Each file ``[obserwator] provider_files`` lists, in its order: its ``path``
        and the ``provider`` it adds, null when the file cannot be used; and one
        problem per file that cannot (code ``invalid_provider_file``, ``option`` the
        field, ``path`` the file, ``message``), which keeps both servers from starting.
    """
    loaded = provider_files()
    added = {item.path: item.id for item in loaded.files}
    files: list[dict[str, object]] = [
        {"path": str(path), "provider": added.get(path)} for path in loaded.paths
    ]
    problems: list[dict[str, object]] = [
        {
            "code": "invalid_provider_file",
            "option": problem.details.get("option", PROVIDER_FILES),
            "path": problem.details.get("path"),
            "message": problem.detail,
        }
        for problem in loaded.problems
    ]
    return files, problems


def environment_report() -> dict[str, object]:
    """
    Report the settings in force and where each comes from (DEV-18.6).

    Returns
    -------
    dict of {str : object}
        Document ``obserwator-config/1`` with ``config_file`` (``path``, ``source``,
        ``exists``, ``error``, ``ignored`` keys of ``[obserwator]`` that no setting
        uses and credentials found in the file), ``keys`` (every setting but
        the credentials: ``value``, ``source`` ``default``, ``env``, ``dotenv``
        or ``file`` and ``name``, the variable or the table), ``credentials``
        (each credential variable ``present`` or ``missing``, those of every
        provider key after the servers'; the value is never given), ``store``
        (the data root, its source, whether it exists and
        its size in bytes; hard-linked files counted once), ``raw_store``
        (the same of the raw root, ADR-017), ``instance`` (the resolved
        ``[obserwator.instance]``, ADR-025, or null), ``capture`` (the capture
        spool's directory and each source's publication state, ``public`` or
        ``private``, with where it comes from, ``default`` or ``file``
        ``[obserwator.capture]``; ADR-030 D5, D7), ``provider_files`` (each
        provider file of ``[obserwator] provider_files``: its ``path`` and the
        ``provider`` it adds, null when it cannot be used; ADR-033) and
        ``problems`` (each ``code``, ``option`` and ``message``: an invalid
        instance section, which keeps the servers from starting, an invalid capture
        section, whose defaults apply, a provider file that cannot be used
        (``invalid_provider_file`` with its ``path``), which keeps the servers from
        starting, a capture spool that cannot be written or whose last write
        failed, a weak key or token, a leftover ``api_keys.json`` of the
        deprecated ``obserwator admin``).
    """
    from obserwator.captures import SECTION as CAPTURE_SECTION
    from obserwator.captures import capture_report, spool_problem
    from obserwator.instance import SECTION, instance_report

    current = Settings()
    file = environment.config_file()
    layers = _layers()
    keys: dict[str, object] = {}
    credentials: dict[str, str] = {}
    for name in Settings.model_fields:
        value = getattr(current, name)
        if name in environment.CREDENTIAL_KEYS:
            variable = f"{environment.PREFIX}{name.upper()}"
            credentials[variable] = "present" if value is not None else "missing"
            continue
        keys[name] = {"value": _plain(value), **_origin(name, layers)}
    for provider in credential_providers():
        for variable in _provider_variables(provider):
            present = (_environment_value(variable) or "").strip()
            credentials[variable] = "present" if present else "missing"
    secret_keys = credential_keys()
    ignored = [
        {
            "key": key,
            "reason": "credential" if key in secret_keys else "unknown",
        }
        for key in file.sections.get(environment.TOOL, {})
        if key not in (SECTION, CAPTURE_SECTION, PROVIDER_FILES)
        and (key not in Settings.model_fields or key in secret_keys)
    ]
    instance, invalid = instance_report()
    problems: list[dict[str, object]] = [] if invalid is None else [invalid]
    capture, invalid_capture = capture_report()
    problems.extend(
        problem for problem in (invalid_capture, spool_problem()) if problem is not None
    )
    files, invalid_files = _provider_files_report()
    problems.extend(invalid_files)
    problems.extend(dict(problem) for problem in credential_problems())
    if current.api_keys_file.expanduser().is_file():
        problems.append(
            {
                "code": "deprecated_api_keys",
                "option": "api_keys_file",
                "message": message(
                    "config.api_keys_deprecated", path=current.api_keys_file
                ),
            }
        )

    def described(kind: "RootKind") -> dict[str, object]:
        root = _root_of(current, kind)
        return {
            "root": str(root),
            **_origin(_ROOT_KEYS[kind], layers),
            "exists": root.is_dir(),
            "size_bytes": _tree_size(root) if root.is_dir() else None,
        }

    return {
        "schema": "obserwator-config/1",
        "tool": "obserwator",
        "version": __version__,
        "config_file": {
            "path": str(file.path),
            "source": file.source,
            "exists": file.exists,
            "error": file.error,
            "ignored": ignored,
        },
        "keys": keys,
        "credentials": credentials,
        "store": described("data"),
        "raw_store": described("raw"),
        "instance": instance,
        "capture": capture,
        "provider_files": files,
        "problems": problems,
    }
