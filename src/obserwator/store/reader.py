"""Offline, read-only access to the versioned Obserwator store (no network, writes, or locks)."""

from __future__ import annotations

import hashlib
import json
import re
import time
from collections.abc import Callable, Collection, Iterable, Iterator, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from itertools import chain
from pathlib import Path, PurePosixPath
from typing import Any, Final, Literal, cast

from obserwator._parsing import normalize_archive
from obserwator.datasets import (
    _CATALOG_DATASETS,
    CAPTURE_SCOPE,
    DATASET_KEY_PATTERN,
    PROVIDER_ID_ALIASES,
    STATION_CODE_PATTERN,
    ArchiveFile,
    DatasetDescriptor,
    License,
    YearsArg,
    _archive_from_path,
    _station_file,
    builds_series,
    datasets,
    get_dataset,
    get_provider,
    monthly_series,
    parse_years,
    providers,
    resolve_dataset_key,
    station_source_files,
)
from obserwator.exceptions import (
    ObserwatorDataError,
    ObserwatorStoreError,
    ObserwatorValidationError,
    io_error,
)
from obserwator.messages import message, reason
from obserwator.models import Measurement, NormalizedRecord, StationListEntry, Tier
from obserwator.output import DATA_MARKER, STORE_MARKER
from obserwator.store.catalog import (
    _CATALOG_DIRS,
    _NESTED_CATALOGS,
    CATALOG_FILE,
    RootArg,
    _newest_downloaded,
    _signal_time,
    _timestamp,
)
from obserwator.store.content import stored_form
from obserwator.store.pmaxtp import CELL_FILE, CELL_SCHEMA, RESPONSE_FILE
from obserwator.store.series import (
    _FLAGS,
    SERIES_SCHEMA,
    _document_subset,
    _pyarrow,
    _series_descriptor,
)
from obserwator.store.types import (
    Meta,
    Observation,
    PathArg,
    RootKind,
    SeriesIndex,
    SeriesSelection,
    StationCoverage,
    StationFeature,
    StationSeriesIndex,
    StoreEntry,
    StoreHandle,
    StoreInfo,
)
from obserwator.store.writer import (
    _LAYOUT_TREES,
    _MARKERS,
    _OBSERVATIONS,
    _SCHEMAS,
    OBSERVATION_SCHEMA,
    _archive_slot_dir,
    _is_register,
    _is_seen_at,
    _missing_hint,
    _observation_name,
    _safe_root,
    _slot_stem,
    _unmarked_message,
    _validate_slot,
    _wrong_root,
)

STORE_SCHEMA = "obserwator-store/1"
DATA_SCHEMA = "obserwator-data/1"
META_SCHEMA = "obserwator-meta/1"
SERIES_FILE = "series.json"
ANALYSES_SCHEMA: Final = "obserwator-analyses/1"
ANALYSES_FILE: Final = "analyses.json"
# Versions of the analyses of each provider: <ANALYSES_DIR>/<key prefix>/<label>_<sha8>/.
ANALYSES_DIR: Final = "analyses/versions"
CONTRACTS: Mapping[str, str] = {
    "store": STORE_SCHEMA,
    "data": DATA_SCHEMA,
    "meta": META_SCHEMA,
    "series": SERIES_SCHEMA,
    "plan": "obserwator-plan/1",
    "pmaxtp": CELL_SCHEMA,
    "observation": OBSERVATION_SCHEMA,
    "analyses": ANALYSES_SCHEMA,
}

EntryKind = Literal[
    "archive", "series", "catalog", "pmaxtp", "analyses", "observation", "problem"
]
_KINDS: tuple[EntryKind, ...] = (
    "archive",
    "series",
    "catalog",
    "pmaxtp",
    "analyses",
    "observation",
    "problem",
)
# Kind of root a slot lies in, by the kind word of the slot (ADR-017 D2).
_SLOT_ROOTS: Mapping[str, RootKind] = {
    "archive": "raw",
    "pmaxtp": "raw",
    "series": "data",
    "catalog": "data",
    "analyses": "data",
}
_STALE_SECONDS = 24 * 60 * 60
_SIDECAR = ".meta.json"
_SHA = re.compile(r"^[0-9a-f]{64}$")
# Dataset key <country>.<provider>.<name> of any provider (ADR-003 D1, IMGW-20).
_DATASET = re.compile(DATASET_KEY_PATTERN)
_COUNTRY = re.compile(r"^[A-Z]{2}$")
_CODE = re.compile(STATION_CODE_PATTERN)
_VERSION_DIR = re.compile(r"^.+_[0-9a-f]{8}$")
_CELL = re.compile(r"^[0-9]+_[0-9]+$")
_PARQUET = re.compile(
    rf"^stations/{STATION_CODE_PATTERN.removeprefix('^').removesuffix('$')}\.parquet$"
)
_OBSERVATION_FILE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}_[0-9a-f]{8}\.json$")
_SAME_CONTENT = re.compile(r"^[^/]+_[0-9a-f]{8}$")
_LABEL_SOURCES = ("last_modified", "downloaded", "inputs")
_PERIODS = ("winter", "summer", "annual")
_SCALARS = (str, int, float, bool, type(None))
_NESTED = {"thresholds": 2, "hydrogeology": 1}
"""The station properties that are objects, with the depth of their objects."""
# The calendar month of a version of a sub-daily series: the directory of its versions
# and the selector of its slot, ``series:<key>:<YYYY-MM>`` (ADR-031).
_MONTH = re.compile(r"^[0-9]{4}-(0[1-9]|1[0-2])$")
# A time of the index of a sub-daily series: the start of an hour in UTC.
_HOUR_TEXT = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:00:00Z$")
_HOUR = timedelta(hours=1)
# The tiers of the points of a sub-daily series, highest first (ADR-030 D1).
_SERIES_TIERS: tuple[Tier, ...] = ("verified", "telemetry", "operational")
# Versions a caller knows (``iter_store(skip_versions=...)``): the path of a version
# directory relative to the root, with ``/``, and the names of its data files.
_Known = Mapping[str, Collection[str]]


class _Invalid(Exception):
    """A store object that cannot be read as a version; ``code`` is the problem code."""

    def __init__(self, code: str, text: str) -> None:
        super().__init__(text)
        self.code = code


# --------------------------------------------------------------------------
# Store marker
# --------------------------------------------------------------------------


def _marker_files(path: Path) -> list[tuple[RootKind, Path]]:
    """The markers a directory holds as regular files (a link is no marker), by kind."""
    return [
        (kind, path / name)
        for kind, name in _MARKERS.items()
        if not (path / name).is_symlink() and (path / name).is_file()
    ]


def _inspect(path: Path) -> StoreInfo:
    """State of a root of either kind; an unusable one has its one problem and its code."""
    contracts = dict(CONTRACTS)

    def unusable(code: str, text: str, *, schema: str | None = None) -> StoreInfo:
        return StoreInfo(
            path, path.exists(), schema, False, contracts, (text,), providers(), (code,)
        )

    if not path.exists():
        return unusable(
            "missing_store", message("reader.store_directory_does_not_exist", path=path)
        )
    markers = _marker_files(path)
    if len(markers) > 1:
        return unusable(
            "conflicting_markers",
            message(
                "writer.root_holds_both_markers",
                path=path,
                raw=STORE_MARKER,
                data=DATA_MARKER,
            ),
        )
    if not markers:
        layout = next(
            (
                kind
                for kind, trees in _LAYOUT_TREES.items()
                if any((path / name).is_dir() for name in trees)
            ),
            None,
        )
        if layout is not None:
            return unusable("missing_marker", _unmarked_message(path, layout))
        return unusable(
            "missing_marker",
            message(
                "reader.no_marker_not_obserwator_store",
                raw=STORE_MARKER,
                data=DATA_MARKER,
                path=path,
            ),
        )
    ((kind, marker),) = markers
    try:
        payload = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return unusable(
            "invalid_marker",
            message("reader.unreadable_marker", marker=marker, exc=reason(exc)),
        )
    schema = payload.get("schema") if isinstance(payload, dict) else None
    if not isinstance(schema, str):
        return unusable(
            "invalid_marker",
            message("reader.marker_has_no_schema_field", marker=marker),
        )
    if schema != _SCHEMAS[kind]:
        return unusable(
            "unsupported_store",
            message(
                "reader.unsupported_store_version_this_version",
                schema=schema,
                store_schema=_SCHEMAS[kind],
            ),
            schema=schema,
        )
    return StoreInfo(path, True, schema, True, contracts, (), providers())


def store_info(root: PathArg, /) -> StoreInfo:
    """
    Describe a root of either kind without raising for an unknown or missing marker.

    A raw root (marker ``obserwator-store.json``, ``obserwator-store/1``) and a
    data root (``obserwator-data.json``, ``obserwator-data/1``) are both
    supported; ``store_schema`` says which (ADR-017). An unknown schema (e.g.
    ``obserwator-store/2``), a missing or unreadable marker and a directory
    with both markers yield ``supported=False`` with the reason in
    ``problems`` instead of an exception. Of the marker only ``schema`` is
    read, exactly as `open_store` reads it: DEV-19.12 requires ``tool``,
    ``created_at`` and ``producer_version`` of what a writer writes, and
    ``created_by`` is optional, so a marker lacking any of them is a
    supported root (the next write completes the three fields).

    Parameters
    ----------
    root : str or os.PathLike
        Root directory; made absolute before inspection.

    Returns
    -------
    StoreInfo
        Existence of the root, marker schema, support flag, the contract
        versions supported by this library, the detected problems with their
        machine-readable codes (``problem_codes``, one per problem) and the
        data providers the library knows (``providers()``, registry order).

    Raises
    ------
    ObserwatorValidationError
        If the root path contains ``..``.
    ObserwatorStoreError
        If a component of the root path is a symbolic link.
    """
    return _inspect(_safe_root(root))


def _open(root: RootArg, *, kind: RootKind | None = None) -> Path:
    """
    The absolute path of a supported root; every function needing one kind opens it here.

    Parameters
    ----------
    root : str, os.PathLike or StoreHandle
        Root directory or an open handle.
    kind : {"raw", "data"} or None, optional
        Kind of root needed; None accepts either kind.

    Raises
    ------
    ObserwatorStoreError
        Code ``store_unavailable``: the root is no supported root
        (``details.reason`` ``unsupported``; a missing one with the hint that
        creates a root of ``kind``) or one of the other kind than ``kind``
        (``wrong_root``, ``details.kind`` the kind needed; ADR-017 D3).
    """
    info = _inspect(_safe_root(root.root if isinstance(root, StoreHandle) else root))
    if not info.supported:
        missing = info.problem_codes == ("missing_store",)
        raise ObserwatorStoreError(
            "; ".join(info.problems),
            details={"reason": "unsupported"},
            hint=_missing_hint(info.root, kind) if missing else None,
        )
    if kind is not None and info.store_schema != _SCHEMAS[kind]:
        raise _wrong_root(info.root, kind)
    return info.root


# --------------------------------------------------------------------------
# Sidecars
# --------------------------------------------------------------------------


def _text(payload: Mapping[str, Any], key: str, *, const: str | None = None) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise _Invalid(
            "invalid_meta", message("reader.field_must_non_empty_text", key=key)
        )
    if const is not None and value != const:
        raise _Invalid(
            "invalid_meta",
            message("reader.field_must_have_value", key=key, const=const),
        )
    return value


def _object(payload: Mapping[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    if not isinstance(value, dict):
        raise _Invalid("invalid_meta", message("reader.field_must_object", key=key))
    return value


def _registry_origin(dataset: str) -> tuple[str, str] | None:
    """``(country, provider)`` the registry gives ``dataset``; None for an unknown key."""
    key = resolve_dataset_key(dataset)
    if key is None:
        return None
    # Every registry key starts with its provider's key prefix (ADR-003 D1).
    provider = get_provider(key.rsplit(".", 1)[0])
    return provider.country, provider.id


def _content_fields(payload: Mapping[str, Any]) -> tuple[str | None, str | None]:
    """``content_sha256`` and ``content_form``: both absent (None) or both valid."""
    present = [key for key in ("content_sha256", "content_form") if key in payload]
    if not present:
        return None, None
    if len(present) == 1:
        raise _Invalid(
            "invalid_meta",
            message("reader.fields_content_sha256_content_form"),
        )
    digest = payload["content_sha256"]
    if not isinstance(digest, str) or not _SHA.fullmatch(digest):
        raise _Invalid("invalid_meta", message("reader.field_content_sha256_must_have"))
    return digest, stored_form(_text(payload, "content_form"))


def _parse_meta(payload: object) -> Meta:
    """Validate the required ``obserwator-meta/1`` fields; additional fields are tolerated."""
    if not isinstance(payload, dict):
        raise _Invalid("invalid_meta", message("reader.sidecar_not_json_object"))
    schema = payload.get("schema")
    if not isinstance(schema, str):
        raise _Invalid("invalid_meta", message("reader.missing_field_schema"))
    if schema != META_SCHEMA:
        raise _Invalid(
            "unknown_schema",
            message("reader.unsupported_sidecar_schema", schema=schema),
        )
    producer = _text(payload, "producer", const="obserwator")
    producer_version = _text(payload, "producer_version")
    dataset = _text(payload, "dataset")
    if not _DATASET.fullmatch(dataset):
        raise _Invalid(
            "invalid_meta",
            message("reader.field_dataset_must_dataset_key"),
        )
    country = _text(payload, "country")
    if not _COUNTRY.fullmatch(country):
        raise _Invalid(
            "invalid_meta", message("reader.field_country_must_country_code")
        )
    # A sidecar written before a provider was renamed holds its old id (ADR-028).
    provider = _text(payload, "provider")
    provider = PROVIDER_ID_ALIASES.get(provider, provider)
    origin = _registry_origin(dataset)
    if origin is not None and (country, provider) != origin:
        raise _Invalid(
            "invalid_meta",
            message(
                "reader.registry_gives_dataset_country_provider",
                dataset=dataset,
                origin=origin[0],
                origin_2=origin[1],
            ),
        )
    request = _object(payload, "request")
    license_ = _object(payload, "license")
    extra = _object(payload, "extra")
    license_id = _text(license_, "id")
    attribution = _text(license_, "attribution")
    url = _text(license_, "url")
    sha = payload.get("sha256")
    if not isinstance(sha, str) or not _SHA.match(sha):
        raise _Invalid("invalid_meta", message("reader.field_sha256_must_have_64"))
    size = payload.get("size_bytes")
    if isinstance(size, bool) or not isinstance(size, int) or size < 0:
        raise _Invalid("invalid_meta", message("reader.field_size_bytes_must_non"))
    try:
        downloaded_at = _timestamp(_text(payload, "downloaded_at"))
    except ValueError as exc:
        raise _Invalid(
            "invalid_meta", message("reader.field_downloaded_not_iso_date")
        ) from exc
    if downloaded_at.tzinfo is None:
        raise _Invalid(
            "invalid_meta", message("reader.field_downloaded_must_have_time")
        )
    version = _object(extra, "version")
    _text(version, "label")
    if version.get("label_source") not in _LABEL_SOURCES:
        raise _Invalid(
            "invalid_meta",
            message(
                "reader.field_label_source_must_one",
                label_sources=", ".join(_LABEL_SOURCES),
            ),
        )
    content_sha256, content_form = _content_fields(payload)
    tier, publication = _tier_fields(payload)
    terms_url = license_.get("terms_url")
    return Meta(
        schema,
        dataset,
        resolve_dataset_key(dataset),
        sha,
        size,
        downloaded_at,
        License(
            license_id,
            attribution,
            url,
            terms_url if isinstance(terms_url, str) and terms_url else None,
        ),
        request,
        extra,
        content_sha256,
        content_form,
        provider=provider,
        country=country,
        producer=producer,
        producer_version=producer_version,
        tier=tier,
        publication=publication,
    )


_TIERS = ("telemetry", "operational")
_PUBLICATIONS = ("public", "private")


def _tier_fields(
    payload: Mapping[str, Any],
) -> tuple[
    Literal["telemetry", "operational"] | None, Literal["public", "private"] | None
]:
    """
    ``tier`` and ``publication`` (ADR-030 D6): both absent (a verified version) or both valid.

    A sidecar of a verified dataset has neither; one of a dataset of another tier
    has its tier and the publication state of its source when it was written.
    """
    present = [key for key in ("tier", "publication") if key in payload]
    if not present:
        return None, None
    tier, publication = payload.get("tier"), payload.get("publication")
    if tier not in _TIERS or publication not in _PUBLICATIONS:
        raise _Invalid(
            "invalid_meta",
            message(
                "reader.fields_tier_publication",
                tiers=", ".join(_TIERS),
                publications=", ".join(_PUBLICATIONS),
            ),
        )
    return (
        cast(Literal["telemetry", "operational"], tier),
        cast(Literal["public", "private"], publication),
    )


def _load_meta(sidecar: Path) -> Meta:
    if sidecar.is_symlink():
        raise _Invalid(
            "symlink",
            message("reader.symbolic_link_instead_sidecar", name=sidecar.name),
        )
    try:
        text = sidecar.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise _Invalid(
            "missing_sidecar", message("reader.missing_sidecar", name=sidecar.name)
        ) from exc
    except OSError as exc:
        raise _Invalid(
            "unreadable",
            message("reader.unreadable_sidecar", name=sidecar.name, exc=reason(exc)),
        ) from exc
    try:
        payload = json.loads(text)
    except ValueError as exc:
        raise _Invalid(
            "invalid_json",
            message("reader.corrupt_json_sidecar", name=sidecar.name, exc=reason(exc)),
        ) from exc
    return _parse_meta(payload)


def read_meta(path: PathArg, /) -> Meta:
    """
    Read the sidecar of a data file (or the ``*.meta.json`` itself).

    Required ``obserwator-meta/1`` fields are validated; additional fields are
    tolerated.

    Parameters
    ----------
    path : str or os.PathLike
        Main data file of a version or its ``<file>.meta.json`` sidecar.

    Returns
    -------
    Meta
        Parsed sidecar metadata.

    Raises
    ------
    ObserwatorStoreError
        If the sidecar does not exist.
    ObserwatorDataError
        If the sidecar is a symbolic link, not valid JSON or does not satisfy
        ``obserwator-meta/1``; with code ``io_error`` (``details.path``) if the
        system cannot read it.
    """
    given = Path(path)
    sidecar = (
        given
        if given.name.endswith(_SIDECAR)
        else given.with_name(given.name + _SIDECAR)
    )
    try:
        return _load_meta(sidecar)
    except _Invalid as exc:
        if exc.code == "missing_sidecar":
            raise ObserwatorStoreError(
                message("reader.no_sidecar", sidecar=sidecar), code="not_found"
            ) from exc
        if isinstance(exc.__cause__, OSError):
            raise io_error(exc.__cause__) from exc.__cause__
        raise ObserwatorDataError(
            message("reader.invalid_sidecar", sidecar=sidecar, exc=reason(exc))
        ) from exc


# --------------------------------------------------------------------------
# Versions and scan
# --------------------------------------------------------------------------


def _check_version(
    directory: Path,
    name: str,
    *,
    subdirs: tuple[str, ...] = (),
    attachments: tuple[str, ...] = (),
) -> tuple[Path, Meta]:
    """
    Validate one published version directory; ``name`` is the expected main file.

    An attachment (e.g. the raw PMAXTP ``response.json``) has no sidecar of its
    own: it is allowed only when ``extra.response`` of the main sidecar
    describes it (``name``, ``sha256``, ``size_bytes``), and then it must exist
    with that size. Versions without the description and without the file are
    valid (written before attachments existed).
    """
    if directory.is_symlink():
        raise _Invalid(
            "symlink", message("reader.symbolic_link_instead_version_directory")
        )
    files: set[str] = set()
    for child in directory.iterdir():
        if child.is_symlink():
            raise _Invalid(
                "symlink", message("reader.symbolic_link_version", name=child.name)
            )
        if child.is_dir():
            if child.name not in subdirs:
                raise _Invalid(
                    "unknown_entry",
                    message("reader.unknown_directory_version", name=child.name),
                )
        else:
            files.add(child.name)
    if name + _SIDECAR not in files:
        # The sidecar is published last and commits the version (Kartograf D18).
        raise _Invalid(
            "missing_sidecar",
            message(
                "reader.missing_sidecar_unfinished_publication_version",
                name=name,
                sidecar=_SIDECAR,
            ),
        )
    if name not in files:
        raise _Invalid("missing_file", message("reader.missing_main_file", name=name))
    unexpected = sorted(files - {name, name + _SIDECAR, *attachments})
    if unexpected:
        raise _Invalid(
            "unknown_entry",
            message("reader.unknown_files_version", unexpected=", ".join(unexpected)),
        )
    main = directory / name
    meta = _load_meta(directory / (name + _SIDECAR))
    label = cast("Mapping[str, Any]", meta.extra["version"])["label"]
    if directory.name != f"{label}_{meta.sha256[:8]}":
        raise _Invalid(
            "invalid_meta",
            message("reader.name_version_directory_does_not", label=label),
        )
    if main.stat().st_size != meta.size_bytes:
        raise _Invalid(
            "size_mismatch", message("reader.size_differs_from_size_bytes", name=name)
        )
    for attachment in attachments:
        _check_attachment(directory, attachment, meta, present=attachment in files)
    return main, meta


def _check_attachment(directory: Path, name: str, meta: Meta, *, present: bool) -> None:
    """Validate an attachment against ``extra.response`` of the main sidecar (no hashing)."""
    info = meta.extra.get("response")
    if info is None:
        if present:
            raise _Invalid(
                "unknown_entry", message("reader.file_has_no_extra_response", name=name)
            )
        return
    if not isinstance(info, Mapping):
        raise _Invalid(
            "invalid_meta", message("reader.field_extra_response_must_object")
        )
    size = info.get("size_bytes")
    sha = info.get("sha256")
    if (
        info.get("name") != name
        or not isinstance(sha, str)
        or not _SHA.match(sha)
        or isinstance(size, bool)
        or not isinstance(size, int)
        or size < 0
    ):
        raise _Invalid(
            "invalid_meta",
            message("reader.field_extra_response_must_have", name=name),
        )
    if not present:
        raise _Invalid(
            "missing_file", message("reader.missing_file_described_sidecar", name=name)
        )
    if (directory / name).stat().st_size != size:
        raise _Invalid(
            "size_mismatch",
            message("reader.size_differs_from_extra_response", name=name),
        )


def _relative(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _analyses_slots() -> dict[str, str]:
    """Analyses slot of every provider, keyed by its key prefix (its directory)."""
    return {
        owner.key_prefix: f"analyses:{owner.key_prefix}.analyses"
        for owner in providers()
    }


def _slot_provider(slot: str | None) -> str | None:
    """Provider of the dataset named by a slot; None without a slot or a known key."""
    kind, _, rest = (slot or "").partition(":")
    key = rest.partition(":")[0]
    if kind == "analyses":
        return next(
            (
                owner.id
                for owner in providers()
                if f"{owner.key_prefix}.analyses" == key
            ),
            None,
        )
    origin = _registry_origin(key) if key else None
    return None if origin is None else origin[1]


def _problem(slot: str | None, path: Path, code: str, text: str) -> StoreEntry:
    return StoreEntry(
        "problem", slot, path, None, code, text, provider=_slot_provider(slot)
    )


def _unknown(root: Path, path: Path) -> StoreEntry:
    return _problem(
        None,
        path,
        "unknown_entry",
        message("reader.unknown_store_item", relative=_relative(root, path)),
    )


def _entry(
    root: Path,
    kind: EntryKind,
    slot: str,
    directory: Path,
    name: str,
    *,
    server_path: str | None = None,
    strict: bool = False,
    **options: Any,
) -> StoreEntry:
    """
    Entry of one version directory; a broken version becomes a problem entry.

    With ``strict`` a version the system cannot read raises `io_error`
    instead (readers of one slot; a scan reports it as ``unreadable``).
    """
    try:
        main, meta = _check_version(directory, name, **options)
        if (
            server_path is not None
            and meta.request.get("server_path", server_path) != server_path
        ):
            raise _Invalid(
                "invalid_meta",
                message("reader.request_server_path_sidecar_does"),
            )
        if kind == "catalog" and meta.dataset_key != slot.split(":")[1]:
            raise _Invalid(
                "invalid_meta",
                message(
                    "reader.dataset_sidecar_does_not_match",
                    dataset=meta.dataset,
                    slot=slot,
                ),
            )
        if kind == "series":
            series_schema = meta.extra.get("series_schema")
            if not isinstance(series_schema, str):
                raise _Invalid(
                    "invalid_meta", message("reader.field_extra_series_schema_must")
                )
            if series_schema != SERIES_SCHEMA:
                raise _Invalid(
                    "unknown_schema",
                    message(
                        "reader.unsupported_series_schema", series_schema=series_schema
                    ),
                )
        if kind == "analyses":
            if (
                meta.dataset != slot.split(":")[1]
                or meta.provider != _slot_provider(slot)
                or meta.extra.get("derived") != "analyses"
            ):
                raise _Invalid(
                    "invalid_meta",
                    message("reader.sidecar_not_analyses_of_slot", slot=slot),
                )
            analyses_schema = meta.extra.get("analyses_schema")
            if not isinstance(analyses_schema, str):
                raise _Invalid(
                    "invalid_meta",
                    message("reader.field_extra_analyses_schema_must"),
                )
            if analyses_schema != ANALYSES_SCHEMA:
                raise _Invalid(
                    "unknown_schema",
                    message(
                        "reader.unsupported_analyses_schema",
                        analyses_schema=analyses_schema,
                    ),
                )
    except _Invalid as exc:
        if strict and exc.code == "unreadable" and isinstance(exc.__cause__, OSError):
            raise io_error(exc.__cause__) from exc.__cause__
        return _problem(
            slot,
            directory,
            exc.code,
            message(
                "reader.version", relative=_relative(root, directory), exc=reason(exc)
            ),
        )
    except OSError as exc:
        if strict:
            raise io_error(exc) from exc
        return _problem(
            slot,
            directory,
            "unreadable",
            message(
                "reader.version", relative=_relative(root, directory), exc=reason(exc)
            ),
        )
    return StoreEntry(kind, slot, main, meta, None, None, provider=_slot_provider(slot))


def _known_files(root: Path, directory: Path, known: _Known) -> Collection[str] | None:
    """Names of the data files the caller knows in a version directory, else None."""
    if not known or not _VERSION_DIR.match(directory.name):
        return None
    return known.get(_relative(root, directory))


def _skipped(kind: EntryKind, slot: str, main: Path) -> StoreEntry:
    """Entry of a version the caller knows: its place only, nothing of it read."""
    return StoreEntry(
        kind, slot, main, None, None, None, provider=_slot_provider(slot), skipped=True
    )


# --------------------------------------------------------------------------
# Observation register (ADR-003 D18)
# --------------------------------------------------------------------------


def _optional_text(payload: Mapping[str, Any], key: str) -> str | None:
    """A required field holding a non-empty text or null."""
    if key not in payload:
        raise _Invalid("invalid_meta", message("reader.missing_field", key=key))
    value = payload[key]
    if value is not None and (not isinstance(value, str) or not value):
        raise _Invalid(
            "invalid_meta", message("reader.field_must_non_empty_text_2", key=key)
        )
    return value


def _digest(payload: Mapping[str, Any], key: str) -> str:
    """A required SHA-256 hex digest field."""
    value = payload.get(key)
    if not isinstance(value, str) or not _SHA.fullmatch(value):
        raise _Invalid(
            "invalid_meta", message("reader.field_must_have_64_lowercase", key=key)
        )
    return value


def _parse_observation(payload: object) -> Observation:
    """Validate the ``obserwator-observation/1`` fields; additional fields are tolerated."""
    if not isinstance(payload, dict):
        raise _Invalid("invalid_meta", message("reader.observation_not_json_object"))
    schema = payload.get("schema")
    if not isinstance(schema, str):
        raise _Invalid("invalid_meta", message("reader.missing_field_schema"))
    if schema != OBSERVATION_SCHEMA:
        raise _Invalid(
            "unknown_schema",
            message("reader.unsupported_observation_schema", schema=schema),
        )
    _text(payload, "producer")
    _text(payload, "producer_version")
    dataset = _text(payload, "dataset")
    if not _DATASET.fullmatch(dataset):
        raise _Invalid(
            "invalid_meta",
            message("reader.field_dataset_must_dataset_key"),
        )
    seen_at = payload.get("seen_at")
    if not isinstance(seen_at, str) or not _is_seen_at(seen_at):
        raise _Invalid("invalid_meta", message("reader.field_seen_must_utc_time"))
    url = _text(payload, "url")
    last_modified = _optional_text(payload, "last_modified")
    etag = _optional_text(payload, "etag")
    size = payload.get("size_bytes")
    if isinstance(size, bool) or not isinstance(size, int) or size < 0:
        raise _Invalid("invalid_meta", message("reader.field_size_bytes_must_non"))
    sha = _digest(payload, "sha256")
    content_sha256 = _digest(payload, "content_sha256")
    content_form = stored_form(_text(payload, "content_form"))
    same = payload.get("same_content_as")
    if not isinstance(same, str) or not _SAME_CONTENT.fullmatch(same):
        raise _Invalid(
            "invalid_meta",
            message("reader.field_same_content_as_must"),
        )
    return Observation(
        dataset,
        seen_at,
        url,
        last_modified,
        etag,
        size,
        sha,
        content_sha256,
        content_form,
        same,
    )


def _load_observation(path: Path) -> Observation:
    """Read and parse one observation file of a register."""
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise _Invalid(
            "unreadable",
            message("reader.unreadable_observation", name=path.name, exc=reason(exc)),
        ) from exc
    try:
        payload = json.loads(data.decode("utf-8"))
    except ValueError as exc:
        raise _Invalid(
            "invalid_json",
            message("reader.corrupt_json_observation", name=path.name, exc=reason(exc)),
        ) from exc
    return _parse_observation(payload)


def _check_observation(
    path: Path,
    observation: Observation,
    dataset: str,
    version_meta: Callable[[str], Meta | None],
) -> None:
    """
    Check an observation against its file name and its archive slot.

    The name must follow ``seen_at`` and the signal, ``dataset`` must be the
    slot's, and ``same_content_as`` must name a valid version of the slot
    (``version_meta``: directory name → sidecar, None for no valid version)
    with equal content fields.
    """
    expected = _observation_name(observation)
    if not path.name.startswith(f"{observation.seen_at[:10]}_"):
        raise _Invalid(
            "invalid_meta",
            message(
                "reader.name_does_not_match_date",
                name=path.name,
                seen_at=observation.seen_at,
            ),
        )
    if path.name != expected:
        raise _Invalid(
            "invalid_meta",
            message(
                "reader.name_does_not_match_signal", name=path.name, expected=expected
            ),
        )
    if resolve_dataset_key(observation.dataset) != dataset:
        raise _Invalid(
            "invalid_meta",
            message(
                "reader.field_dataset_differs_from_dataset",
                dataset=observation.dataset,
                dataset_2=dataset,
            ),
        )
    meta = version_meta(observation.same_content_as)
    if meta is None:
        raise _Invalid(
            "invalid_meta",
            message(
                "reader.same_content_as_does_not",
                same_content_as=observation.same_content_as,
            ),
        )
    if (meta.content_sha256, meta.content_form) != (
        observation.content_sha256,
        observation.content_form,
    ):
        raise _Invalid(
            "invalid_meta",
            message(
                "reader.content_fields_differ_from_fields",
                same_content_as=observation.same_content_as,
            ),
        )


def _scan_register(
    root: Path,
    register: Path,
    slot: str,
    version_meta: Callable[[str], Meta | None],
) -> Iterator[StoreEntry]:
    """
    Observations and problems of the register ``observations/`` of an archive slot.

    ``version_meta`` gives the sidecar of a valid version of the slot by the
    name of its directory, or None. Files are not hashed.
    """
    dataset = slot.split(":")[1]
    for child in sorted(register.iterdir()):
        relative = _relative(root, child)
        if child.is_symlink():
            yield _problem(
                slot,
                child,
                "symlink",
                message("reader.symbolic_link_observation_register", relative=relative),
            )
        elif not child.is_file() or not _OBSERVATION_FILE.fullmatch(child.name):
            yield _unknown(root, child)
        else:
            try:
                observation = _load_observation(child)
                _check_observation(child, observation, dataset, version_meta)
            except _Invalid as exc:
                yield _problem(
                    slot,
                    child,
                    exc.code,
                    message("reader.observation", relative=relative, exc=reason(exc)),
                )
            else:
                yield StoreEntry(
                    "observation",
                    slot,
                    child,
                    None,
                    None,
                    None,
                    observation,
                    provider=_slot_provider(slot),
                )


# --------------------------------------------------------------------------
# Slots (spec §13.7)
# --------------------------------------------------------------------------

_SLOT_GRAMMAR = message(
    "reader.archive_key_path_series_key",
    monthly=", ".join(item.key for item in datasets() if monthly_series(item)),
    values=", ".join(_CATALOG_DATASETS.values()),
    analyses=", ".join(f"{owner.key_prefix}.analyses" for owner in providers()),
)
_PMAXTP_KEY = "pl.imgw.pmaxtp"


def _archive_descriptors() -> list[DatasetDescriptor]:
    """Stored archive datasets, longest server directory first."""
    return sorted(
        (item for item in datasets() if item.in_store and item.server_dir is not None),
        key=lambda item: -len(item.server_dir or ""),
    )


def _archive_slot(server_path: str) -> str | None:
    """
    Slot ``archive:<key>:<selector>`` of a stored server path.

    The owning dataset is the stored one with the longest matching server
    directory; station-source datasets (lists and station metadata), capture
    datasets (``<YYYY-MM-DD>.jsonl.gz``, ADR-030 D3) and per-station datasets
    accept only their own file names, so one of them may share a directory with
    another dataset (the captures of ``api/data/hydro`` lie below the slot of
    ``pl.imgw.hydro_now``; ČHMÚ's daily and weekly groundwater files, ADR-032),
    other datasets a selector with a folder; any other path has no slot.
    """
    for descriptor in _archive_descriptors():
        if not server_path.startswith(f"{descriptor.server_dir}/"):
            continue
        selector = server_path.removeprefix(f"{descriptor.server_dir}/")
        if descriptor.time_unit == "station_list":
            if _station_file(descriptor, selector) is None:
                continue
            valid = True
        elif descriptor.archive_scope == CAPTURE_SCOPE:
            if _archive_from_path(descriptor.key, server_path) is None:
                continue
            valid = True
        elif descriptor.archive_scope != "country":
            # Per-station files follow the file-name grammar of the dataset.
            if _archive_from_path(descriptor.key, server_path) is None:
                continue
            valid = True
        else:
            # A selector with a folder (IMGW-PIB), or a file its adapter names
            # directly in the directory (PIG-PIB's tables, ADR-035).
            valid = (
                "/" in selector
                or _archive_from_path(descriptor.key, server_path) is not None
            )
        if not valid or ":" in selector:
            return None
        return f"archive:{descriptor.key}:{selector}"
    return None


def _scanned_archive_slot(
    base: Path, directory: Path, files: Collection[str] | None = None
) -> tuple[str, str] | None:
    """
    Slot and server path of a version directory, named after its (possibly orphaned) main file.

    The directory is listed, unless the caller knows its data files (``files``).
    """
    names = sorted(
        files
        if files is not None
        else (
            item.name.removesuffix(_SIDECAR)
            for item in directory.iterdir()
            if not item.is_dir()
        )
    )
    slot_dir = directory.parent
    name = next(
        (item for item in names if _slot_stem(item) == slot_dir.name),
        slot_dir.name,
    )
    server_path = f"{slot_dir.parent.relative_to(base).as_posix()}/{name}"
    slot = _archive_slot(server_path)
    return None if slot is None else (slot, server_path)


def _nested_slot(path: Path) -> bool:
    """
    Whether a directory among an archive slot's versions is another dataset's slot.

    A directory that holds no file and whose name is no version name
    ``<label>_<sha8>``, as the scan tells it apart (`_scan_archives`): the captures
    ``api/data/hydro/<YYYY-MM-DD>/`` below the slot of ``pl.imgw.hydro_now``
    (ADR-030 D3).
    """
    if path.is_symlink() or not path.is_dir() or _VERSION_DIR.match(path.name):
        return False
    try:
        return all(item.is_dir() and not item.is_symlink() for item in path.iterdir())
    except OSError:
        return False


def _directories(root: Path, path: Path) -> Iterator[Path | StoreEntry]:
    """Children of a structural directory; files and links there are problems."""
    for child in sorted(path.iterdir()):
        if child.is_symlink():
            yield _problem(
                _relative(root, child),
                child,
                "symlink",
                message("reader.symbolic_link_store", relative=_relative(root, child)),
            )
        elif not child.is_dir():
            yield _unknown(root, child)
        else:
            yield child


def _versions_dir(root: Path, top: Path) -> Iterator[Path | StoreEntry]:
    """``<top>/versions`` is the only allowed child of a kind directory."""
    for child in _directories(root, top):
        if isinstance(child, StoreEntry):
            yield child
        elif child.name != "versions":
            yield _unknown(root, child)
        else:
            yield child


def _scan_archives(
    root: Path, base: Path, directory: Path, known: _Known
) -> Iterator[StoreEntry]:
    """
    Archive versions, observations and problems below ``directory``.

    A directory ``observations`` is recognized before the version-directory
    rule: beside versions of exactly one slot it is that slot's observation
    register (ADR-003 D18), anywhere else an unknown element. A version the
    caller knows (``known``) is neither listed nor read nor measured; only an
    observation that names it reads its sidecar, for the content fields.
    """
    register: Path | None = None
    slots: set[str] = set()
    versions: dict[str, Meta] = {}
    unread: dict[str, Path] = {}
    for child in _directories(root, directory):
        if isinstance(child, StoreEntry):
            yield child
            continue
        if child.name == _OBSERVATIONS:
            register = child
            continue
        files = _known_files(root, child, known)
        has_files = files is not None or any(
            not item.is_dir() or item.is_symlink() for item in child.iterdir()
        )
        if has_files or _VERSION_DIR.match(child.name):
            deep = len(child.relative_to(base).parts) >= 3
            found = _scanned_archive_slot(base, child, files) if deep else None
            if files is not None and (
                found is None or PurePosixPath(found[1]).name not in files
            ):
                # The names the caller knows lead to no main file: read it as unknown.
                files = None
                found = _scanned_archive_slot(base, child) if deep else None
            if found is None:
                yield _unknown(root, child)
            else:
                slot, server_path = found
                name = PurePosixPath(server_path).name
                if files is not None:
                    unread[child.name] = main = child / name
                    entry = _skipped("archive", slot, main)
                else:
                    entry = _entry(
                        root, "archive", slot, child, name, server_path=server_path
                    )
                slots.add(slot)
                if entry.meta is not None:
                    versions[child.name] = entry.meta
                yield entry
        else:
            yield from _scan_archives(root, base, child, known)
    if register is not None:
        if len(slots) == 1:

            def version_meta(name: str) -> Meta | None:
                if name in unread and name not in versions:
                    try:
                        versions[name] = _load_meta(Path(f"{unread[name]}{_SIDECAR}"))
                    except (_Invalid, OSError):
                        return None
                return versions.get(name)

            yield from _scan_register(root, register, slots.pop(), version_meta)
        else:
            yield _unknown(root, register)


def _series_datasets() -> dict[str, DatasetDescriptor]:
    """Datasets with derived series, keyed by their store directory slug."""
    return {item.slug: item for item in datasets() if builds_series(item)}


def _derived_entry(
    root: Path,
    version: Path | StoreEntry,
    kind: EntryKind,
    slot: str,
    name: str,
    known: _Known,
    **options: Any,
) -> StoreEntry:
    """Entry of a series, catalog or PMAXTP slot child; only archives have a register."""
    if isinstance(version, StoreEntry):
        return version
    if version.name == _OBSERVATIONS:
        return _unknown(root, version)
    files = _known_files(root, version, known)
    if files is not None and name in files:
        return _skipped(kind, slot, version / name)
    return _entry(root, kind, slot, version, name, **options)


def _scan_catalogs(root: Path, versions: Path, known: _Known) -> Iterator[StoreEntry]:
    """
    Station catalog versions and problems below ``stations/versions/``.

    A directory named after a provider's catalog (``imgw_stations``,
    ``chmu_stations``; ADR-003 D5, ADR-028) holds the versions of that
    catalog; any other element is unknown, a catalog version of the 3.0.x
    layout directly in ``stations/versions/`` too.
    """
    for child in _directories(root, versions):
        if isinstance(child, StoreEntry):
            yield child
        elif child.name in _NESTED_CATALOGS:
            slot = f"catalog:{_CATALOG_DATASETS[_NESTED_CATALOGS[child.name]]}"
            for version in _directories(root, child):
                yield _derived_entry(
                    root, version, "catalog", slot, CATALOG_FILE, known
                )
        else:
            yield _unknown(root, child)


def _scan_series(
    root: Path, slug: Path, descriptor: DatasetDescriptor, known: _Known
) -> Iterator[StoreEntry]:
    """
    Series versions and problems of one dataset below ``series/versions/<slug>/``.

    A sub-daily series (`monthly_series`, ADR-031) keeps the versions of each
    calendar month in ``<YYYY-MM>/``, slot ``series:<key>:<YYYY-MM>``; any other
    element beside its months is unknown.
    """
    if not monthly_series(descriptor):
        for version in _directories(root, slug):
            yield _derived_entry(
                root,
                version,
                "series",
                f"series:{descriptor.key}",
                SERIES_FILE,
                known,
                subdirs=("stations",),
            )
        return
    for month in _directories(root, slug):
        if isinstance(month, StoreEntry) or not _MONTH.fullmatch(month.name):
            yield month if isinstance(month, StoreEntry) else _unknown(root, month)
            continue
        for version in _directories(root, month):
            yield _derived_entry(
                root,
                version,
                "series",
                f"series:{descriptor.key}:{month.name}",
                SERIES_FILE,
                known,
                subdirs=("stations",),
            )


def _scan_kind(root: Path, top: Path, known: _Known) -> Iterator[StoreEntry]:
    for versions in _versions_dir(root, top):
        if isinstance(versions, StoreEntry):
            yield versions
        elif top.name == "archives":
            yield from _scan_archives(root, versions, versions, known)
        elif top.name == "stations":
            yield from _scan_catalogs(root, versions, known)
        elif top.name == "series":
            series = _series_datasets()
            for slug in _directories(root, versions):
                if isinstance(slug, StoreEntry) or slug.name not in series:
                    yield slug if isinstance(slug, StoreEntry) else _unknown(root, slug)
                    continue
                yield from _scan_series(root, slug, series[slug.name], known)
        elif top.name == "analyses":
            yield from _scan_analyses(root, versions, known)
        else:
            for method in _directories(root, versions):
                if isinstance(method, StoreEntry) or method.name not in ("POT", "AMP"):
                    yield (
                        method
                        if isinstance(method, StoreEntry)
                        else _unknown(root, method)
                    )
                    continue
                for cell in _directories(root, method):
                    if isinstance(cell, StoreEntry) or not _CELL.match(cell.name):
                        yield (
                            cell
                            if isinstance(cell, StoreEntry)
                            else _unknown(root, cell)
                        )
                        continue
                    for version in _directories(root, cell):
                        yield _derived_entry(
                            root,
                            version,
                            "pmaxtp",
                            f"pmaxtp:{_PMAXTP_KEY}:{method.name}/{cell.name}",
                            CELL_FILE,
                            known,
                            attachments=(RESPONSE_FILE,),
                        )


def _scan_analyses(root: Path, versions: Path, known: _Known) -> Iterator[StoreEntry]:
    """
    Analyses versions and problems below ``analyses/versions/``.

    A directory named after the key prefix of a provider holds the versions
    of that provider's analyses slot (``analyses:<key prefix>.analyses``);
    any other directory is an unknown element.
    """
    slots = _analyses_slots()
    for prefix in _directories(root, versions):
        if isinstance(prefix, StoreEntry) or prefix.name not in slots:
            yield prefix if isinstance(prefix, StoreEntry) else _unknown(root, prefix)
            continue
        for version in _directories(root, prefix):
            yield _derived_entry(
                root,
                version,
                "analyses",
                slots[prefix.name],
                ANALYSES_FILE,
                known,
                subdirs=("stations",),
            )


def _marker_path(root: Path) -> Path:
    """The marker a problem of an unusable root names: the data one if only it is there."""
    data = root / DATA_MARKER
    alone = data.is_file() and not (root / STORE_MARKER).is_file()
    return data if alone else root / STORE_MARKER


def _scan(root: Path, known: _Known) -> Iterator[StoreEntry]:
    """
    Every entry of a root, by the kind its marker gives (ADR-017 D2).

    The trees of the root's kind are scanned; anything else at the top, a
    tree of the other kind included (a store not yet split), is an unknown
    element.
    """
    info = _inspect(root)
    if not info.supported:
        for code, text in zip(info.problem_codes, info.problems, strict=True):
            yield _problem(None, _marker_path(root), code, text)
        return
    kind: RootKind = "raw" if info.store_schema == STORE_SCHEMA else "data"
    cutoff = time.time() - _STALE_SECONDS
    for child in sorted(root.iterdir()):
        if child.name == _MARKERS[kind]:
            continue
        if child.is_symlink():
            yield _problem(
                None,
                child,
                "symlink",
                message("reader.symbolic_link_store", relative=child.name),
            )
        elif child.name == ".incoming" and child.is_dir():
            # Young staging directories are private to a running writer, never versions.
            for staging in sorted(child.iterdir()):
                if staging.lstat().st_mtime < cutoff:
                    relative = _relative(root, staging)
                    yield _problem(
                        None,
                        staging,
                        "stale_incoming",
                        message(
                            "reader.abandoned_staging_older_than_24", relative=relative
                        ),
                    )
        elif child.name in _LAYOUT_TREES[kind] and child.is_dir():
            yield from _scan_kind(root, child, known)
        else:
            yield _unknown(root, child)


def _is_file_name(name: object) -> bool:
    """Whether ``name`` is the plain name of a data file (no path, no sidecar)."""
    return (
        isinstance(name, str)
        and name not in ("", ".", "..")
        and not any(separator in name for separator in ("/", "\\", "\x00"))
        and not name.endswith(_SIDECAR)
    )


def _known_versions(skip_versions: object) -> _Known:
    """The versions the caller knows, checked: directory path to data file names."""
    if skip_versions is None:
        return {}
    if not isinstance(skip_versions, Mapping) or not all(
        isinstance(directory, str)
        and isinstance(names, Collection)
        and not isinstance(names, str)
        and all(_is_file_name(name) for name in names)
        for directory, names in skip_versions.items()
    ):
        raise ObserwatorValidationError(
            message("reader.skip_versions_mapping"),
            details={"option": "skip_versions"},
        )
    return cast(_Known, skip_versions)


def iter_store(
    root: RootArg,
    /,
    *,
    kind: str | None = None,
    provider: str | None = None,
    skip_versions: Mapping[str, Collection[str]] | None = None,
) -> Iterator[StoreEntry]:
    """
    Scan every published version, observation and problem offline, without writing.

    The root is scanned by its marker (ADR-017 D2): a raw root
    (``obserwator-store.json``) yields archive, observation, PMAXTP and
    problem entries, a data root (``obserwator-data.json``) series, catalog,
    analyses and problem entries. A tree of the other kind in a root (e.g.
    ``series/`` in a store not yet split) is an ``unknown_entry`` problem, as
    any unknown directory, and ``kind`` of the other root kind yields
    nothing. Unknown directories, missing sidecars, corrupted JSON, unknown
    schemas (of the sidecar or, for series and analyses, of
    ``extra.series_schema`` and ``extra.analyses_schema``), size mismatches
    and ``.incoming`` stagings older than 24 hours are reported as separate
    ``StoreEntry(kind="problem")`` entries; younger stagings are private and
    are not versions. Files are not hashed during the scan (only their size
    is compared with ``size_bytes``). Each valid file of the observation
    register ``observations/`` of an archive slot is a
    ``StoreEntry(kind="observation")`` (never a version); a broken one is a
    problem with the slot. Every entry names the provider of its slot's
    dataset in ``StoreEntry.provider`` (None for a problem without a slot).
    The versions of a sub-daily series (ADR-031) lie in a directory per
    calendar month, ``series/versions/<slug>/<YYYY-MM>/``, and have its slot
    ``series:<key>:<YYYY-MM>``; any other element beside the months is an
    ``unknown_entry`` problem.

    Every scan reads the sidecar of every version. A consumer that keeps what
    it has read passes the versions it knows in ``skip_versions`` (an
    incremental scan) and gets them back without that cost.

    Parameters
    ----------
    root : str, os.PathLike or StoreHandle
        Root directory of either kind or an open handle.
    kind : {"archive", "series", "catalog", "pmaxtp", "analyses", "observation", "problem"} or None, optional
        Return only entries of this kind; ``None`` returns all entries.
    provider : str or None, optional
        Return only the entries of this provider (``ProviderDescriptor.id`` or
        key prefix) and the problems without a slot; ``None`` returns the
        entries of all providers.
    skip_versions : mapping of str to collection of str or None, optional
        The versions the caller already knows: the path of a version
        directory relative to the root, with ``/`` (``archives/versions/<server
        dir>/<stem>/<label>_<sha8>``, ``series/versions/<slug>/<label>_<sha8>``
        (``series/versions/<slug>/<YYYY-MM>/<label>_<sha8>`` of a sub-daily
        series),
        ``stations/versions/<provider catalog>/<label>_<sha8>``,
        ``pmaxtp/versions/<method>/<cell>/<label>_<sha8>`` or
        ``analyses/versions/<key prefix>/<label>_<sha8>``), mapped to the
        names of its data files: the main file of the version, e.g.
        ``("codz_2024.zip",)``. Such a version comes back as an entry with
        ``skipped=True`` and ``meta=None`` (``kind``, ``slot``, ``version`` and
        ``provider`` as for any entry) without its directory being listed, its
        sidecar read or its file measured. The caller vouches for what it
        names: a known version that has broken since, or a file added to or
        removed from it, is not seen; a scan without the argument sees it.
        Whatever is not named is read as always, so a new version and every
        problem are reported, and a version that is gone is missing. The
        sidecar of a known version is read only when an observation of its
        slot names it, to compare the content fields. A path that is no
        version directory of the store is ignored, and a version whose names
        lack its main file is read as if the caller did not know it. ``None``
        (the default) skips nothing.

    Returns
    -------
    Iterator[StoreEntry]
        Lazily scanned published versions, observations and problems.

    Raises
    ------
    ObserwatorValidationError
        If ``kind`` is not a known entry kind, ``provider`` names no provider,
        ``skip_versions`` is not a mapping of paths to collections of plain
        file names (``details.option`` ``skip_versions``) or the root path
        contains ``..``.
    ObserwatorStoreError
        If a component of the root path is a symbolic link.
    """
    if kind is not None and kind not in _KINDS:
        raise ObserwatorValidationError(
            message(
                "reader.unknown_kind_store_item_allowed",
                kind=kind,
                kinds=", ".join(_KINDS),
            )
        )
    owner = None if provider is None else get_provider(provider).id
    known = _known_versions(skip_versions)
    path = _safe_root(root.root if isinstance(root, StoreHandle) else root)
    return (
        entry
        for entry in _scan(path, known)
        if (kind is None or entry.kind == kind)
        and (owner is None or entry.provider in (owner, None))
    )


def _invalid_slot(slot: object, reason: str) -> ObserwatorValidationError:
    return ObserwatorValidationError(
        message(
            "reader.invalid_slot_expected",
            slot=slot,
            reason=reason,
            slot_grammar=_SLOT_GRAMMAR,
        ),
        details={"option": "slot", "value": slot if isinstance(slot, str) else None},
    )


def _slot_location(
    root: Path, slot: str
) -> tuple[EntryKind, Path, str, dict[str, Any]]:
    """Kind, slot directory, main file name and `_entry` options of a §13.7 slot."""
    if not isinstance(slot, str):
        raise _invalid_slot(slot, message("reader.slot_must_text"))
    kind, _, rest = slot.partition(":")
    key, has_selector, selector = rest.partition(":")
    if kind == "archive":
        descriptor = next(
            (item for item in _archive_descriptors() if item.key == key), None
        )
        if descriptor is None:
            raise _invalid_slot(
                slot, message("reader.not_key_archive_dataset", key=key)
            )
        server_path = f"{descriptor.server_dir}/{selector}"
        if not has_selector or _archive_slot(server_path) != slot:
            raise _invalid_slot(
                slot, message("reader.invalid_file_path_dataset", key=descriptor.key)
            )
        directory = _validate_slot(root, _archive_slot_dir(server_path))
        name = PurePosixPath(server_path).name
        return "archive", directory, name, {"server_path": server_path}
    series = {item.key: item for item in _series_datasets().values()}
    if kind == "series" and key in series and monthly_series(series[key]):
        # A sub-daily series has a slot per calendar month only (ADR-031).
        if not has_selector or not _MONTH.fullmatch(selector):
            raise _invalid_slot(
                slot, message("reader.monthly_slot_needs_month", key=key)
            )
        return (
            "series",
            _validate_slot(root, f"series/versions/{series[key].slug}/{selector}"),
            SERIES_FILE,
            {"subdirs": ("stations",)},
        )
    if has_selector:
        cell = re.fullmatch(r"(POT|AMP)/([0-9]+_[0-9]+)", selector)
        if kind != "pmaxtp" or key != _PMAXTP_KEY or cell is None:
            raise _invalid_slot(slot, message("reader.unexpected_selector"))
        return (
            "pmaxtp",
            _validate_slot(root, f"pmaxtp/versions/{cell[1]}/{cell[2]}"),
            CELL_FILE,
            {"attachments": (RESPONSE_FILE,)},
        )
    if kind == "series" and key in series:
        return (
            "series",
            _validate_slot(root, f"series/versions/{series[key].slug}"),
            SERIES_FILE,
            {"subdirs": ("stations",)},
        )
    owner = next(
        (owner for owner, catalog in _CATALOG_DATASETS.items() if catalog == key),
        None,
    )
    if kind == "catalog" and owner is not None:
        return "catalog", _validate_slot(root, _CATALOG_DIRS[owner]), CATALOG_FILE, {}
    prefix = next(
        (prefix for prefix, name in _analyses_slots().items() if name == slot), None
    )
    if prefix is not None:
        return (
            "analyses",
            _validate_slot(root, f"{ANALYSES_DIR}/{prefix}"),
            ANALYSES_FILE,
            {"subdirs": ("stations",)},
        )
    raise _invalid_slot(slot, message("reader.unknown_kind_key"))


def current_version(root: RootArg, /, *, slot: str) -> StoreEntry | None:
    """
    Current published version of a slot; a broken version in the slot is an error.

    A version directory without the main file's sidecar is an interrupted
    publication, not a version: it is skipped here (``iter_store`` reports it
    as ``missing_sidecar``), and the next write of the same content
    completes it.

    Archive versions are ordered by ``Last-Modified``, then ``downloaded_at``,
    then path; derived versions (series, catalog, PMAXTP, analyses) by
    ``downloaded_at``, then path. Staging directories are never returned, and
    the observation register ``observations/`` of an archive slot is not a
    version. The kind of the slot decides the kind of root (ADR-017 D2):
    archive and PMAXTP slots lie in a raw root, series, catalog and analyses
    slots in a data root.

    Parameters
    ----------
    root : str, os.PathLike or StoreHandle
        Root directory of the slot's kind or an open handle.
    slot : str
        Slot in the §13.7 grammar: ``archive:<key>:<server path without the
        dataset server directory>`` (e.g.
        ``archive:pl.imgw.hydro_daily:2024/codz_2024.zip``),
        ``series:<key>``, of a sub-daily series ``series:<key>:<YYYY-MM>``
        (one slot per calendar month, ADR-031; e.g.
        ``series:pl.imgw.hydro_subdaily:2026-10``), ``catalog:<catalog key>``
        (``catalog:pl.imgw.stations``, ``catalog:cz.chmu.stations``),
        ``pmaxtp:pl.imgw.pmaxtp:<POT|AMP>/<indX>_<indY>`` or
        ``analyses:<provider key prefix>.analyses``
        (``analyses:pl.imgw.analyses``, ``analyses:cz.chmu.analyses``). Station
        selectors of series slots (``series:<key>:<station_code>``) are
        rejected, so is the bare ``series:<key>`` of a sub-daily series (the
        message names its month form).

    Returns
    -------
    StoreEntry or None
        Entry of the current version, or ``None`` if the slot has no
        versions.

    Raises
    ------
    ObserwatorStoreError
        If the root is not a supported root (code ``store_unavailable``), one
        of the other kind than the slot's (``store_unavailable``,
        ``details.reason`` ``wrong_root``, ``details.kind`` the slot's kind of
        root) or a root or slot path component is a symbolic link (code
        ``validation_error``).
    ObserwatorValidationError
        If ``slot`` does not follow the grammar (including the pre-3.0.0
        forms ``archive:<server_path>``, ``series:<slug>``,
        ``catalog:stations`` and ``pmaxtp:<M>:<x>_<y>``); the message
        describes the grammar. Also if the root path contains ``..``.
    ObserwatorDataError
        If any version in the slot is broken (an older version is never
        silently selected instead); with code ``io_error``
        (``details.path``) if the system cannot read one.
    """
    word = slot.partition(":")[0] if isinstance(slot, str) else ""
    return _current(_open(root, kind=_SLOT_ROOTS.get(word)), slot)


def _current(path: Path, slot: str) -> StoreEntry | None:
    """`current_version` of a slot in an opened root."""
    kind, directory, name, options = _slot_location(path, slot)
    if not directory.is_dir():
        return None
    versions: list[tuple[Path, dict[str, Any]]] = []
    entries: dict[Path, StoreEntry] = {}
    for version in sorted(directory.iterdir()):
        if kind == "archive" and (_is_register(version) or _nested_slot(version)):
            continue
        entry = (
            _entry(path, kind, slot, version, name, strict=True, **options)
            if version.is_dir()
            else _unknown(path, version)
        )
        if entry.kind == "problem" and entry.problem_code == "missing_sidecar":
            continue
        if entry.kind == "problem" or entry.meta is None or entry.version is None:
            raise ObserwatorDataError(
                message("reader.corrupt_version_slot", slot=slot, problem=entry.problem)
            )
        meta = entry.meta
        versions.append(
            (
                entry.version,
                {"downloaded_at": meta.downloaded_at.isoformat(), "extra": meta.extra},
            )
        )
        entries[entry.version] = entry
    if kind == "archive":
        current = max(
            versions,
            key=lambda item: (
                _signal_time(item[1]),
                _timestamp(item[1]["downloaded_at"]),
                item[0].as_posix(),
            ),
            default=None,
        )
    else:
        current = _newest_downloaded(versions)
    return entries[current[0]] if current is not None else None


def _month_span(month: str) -> tuple[date, date]:
    """The first and the last day of a calendar month ``YYYY-MM``."""
    year, number = int(month[:4]), int(month[5:7])
    following = date(year + number // 12, number % 12 + 1, 1)
    return date(year, number, 1), following - timedelta(days=1)


def _check_bounds(start: date | None, end: date | None) -> None:
    """A range of days: each bound a ``date`` (no ``datetime``) or None, in order."""
    for bound in (start, end):
        if bound is not None and (
            not isinstance(bound, date) or isinstance(bound, datetime)
        ):
            raise ObserwatorValidationError(
                message("reader.range_bound_must_date", bound=bound)
            )
    if start is not None and end is not None and start > end:
        raise ObserwatorValidationError(
            message("reader.start_range_later_than_end", start=start, end=end)
        )


def series_months(
    root: RootArg,
    /,
    *,
    dataset: str,
    start: date | None = None,
    end: date | None = None,
) -> tuple[StoreEntry, ...]:
    """
    Current version of every month of a sub-daily series, in month order (ADR-031).

    A sub-daily series (``pl.imgw.hydro_subdaily``, ``cz.chmu.hydro_subdaily``)
    has one slot per calendar month, ``series:<key>:<YYYY-MM>``, whose versions lie
    in ``series/versions/<slug>/<YYYY-MM>/``; the current version of a month is
    chosen as `current_version` chooses it (newest ``downloaded_at``, then path).
    A month without a version is left out, and so is any element beside the
    months (`iter_store` reports it). Nothing is written and no Parquet is read.

    Parameters
    ----------
    root : str, os.PathLike or StoreHandle
        Data root directory (ADR-017) or an open handle of one.
    dataset : str
        Sub-daily series dataset (key, slug or legacy alias).
    start : datetime.date or None, optional
        Keep only the months whose last day is ``start`` or later; ``None``
        means no lower bound.
    end : datetime.date or None, optional
        Keep only the months whose first day is ``end`` or earlier; ``None``
        means no upper bound.

    Returns
    -------
    tuple of StoreEntry
        The entry of the current version of each month (``kind`` ``"series"``,
        ``slot`` ``series:<key>:<YYYY-MM>``, ``version`` its ``series.json``,
        ``meta`` its sidecar), months ascending; empty when the root holds no
        month of the series (within the range).

    Raises
    ------
    ObserwatorValidationError
        If the dataset builds no series or its series has no version per month
        (``details.option`` ``dataset``, ``details.reason`` ``not_monthly``), a
        bound is not a ``date`` or ``start`` is later than ``end``; also if the
        root path contains ``..``.
    ObserwatorStoreError
        If the root is not a supported data root (code ``store_unavailable``;
        ``details.reason`` ``wrong_root`` for a raw root) or a path component is
        a symbolic link (code ``validation_error``).
    ObserwatorDataError
        If a version of a month in the range is broken (as in
        `current_version`); with code ``io_error`` (``details.path``) if the
        system cannot read one.
    """
    descriptor = _series_descriptor(dataset)
    if not monthly_series(descriptor):
        raise ObserwatorValidationError(
            message(
                "reader.series_not_monthly",
                key=descriptor.key,
                monthly=", ".join(
                    item.key for item in datasets() if monthly_series(item)
                ),
            ),
            details={"option": "dataset", "value": dataset, "reason": "not_monthly"},
        )
    _check_bounds(start, end)
    path = _open(root, kind="data")
    directory = _validate_slot(path, f"series/versions/{descriptor.slug}")
    if not directory.is_dir():
        return ()
    found: list[StoreEntry] = []
    for month in sorted(child.name for child in directory.iterdir()):
        if not _MONTH.fullmatch(month):
            continue
        first, last = _month_span(month)
        if (start is not None and last < start) or (end is not None and first > end):
            continue
        entry = _current(path, f"series:{descriptor.key}:{month}")
        if entry is not None:
            found.append(entry)
    return tuple(found)


@dataclass(frozen=True)
class _Reference:
    """
    Reference signal of an archive slot (ADR-003 D18).

    Attributes
    ----------
    version : StoreEntry
        Current version of the slot.
    url, etag, last_modified : str or None
        Signal of the newest observation of the current version, or without
        one the version's ``extra.http``.
    size_bytes : int
        Size of the observed bytes, or of the version's main file.
    observation : Path or None
        Observation giving the signal; None when it is the version's own.
    """

    version: StoreEntry
    url: str | None
    etag: str | None
    last_modified: str | None
    size_bytes: int
    observation: Path | None


def _reference_signal(root: RootArg, /, *, slot: str) -> _Reference | None:
    """
    Signal the next download of an archive slot is compared with (ADR-003 D18).

    The newest observation of the current version (by ``seen_at``, then file
    name) gives the signal; observations of older versions are history. Without
    such an observation the signal is the version's ``extra.http`` and
    ``size_bytes``, exactly as in a slot without a register.

    Parameters
    ----------
    root : str, os.PathLike or StoreHandle
        Raw root directory or an open handle of one.
    slot : str
        Archive slot ``archive:<key>:<selector>``.

    Returns
    -------
    _Reference or None
        Reference signal with the current version; None for a slot without
        versions.

    Raises
    ------
    ObserwatorValidationError
        If ``slot`` is not an archive slot of the grammar.
    ObserwatorDataError
        If a version of the slot is broken (as `current_version`), an
        observation of the current version is broken or contradicts it, or a
        register file cannot be told apart from such an observation; with
        code ``io_error`` if the system cannot read one.
    """
    if not slot.startswith("archive:"):
        raise _invalid_slot(
            slot, message("reader.reference_signal_exists_only_archive")
        )
    entry = current_version(root, slot=slot)
    if entry is None or entry.version is None or entry.meta is None:
        return None
    current = entry.version.parent
    register = current.parent / _OBSERVATIONS
    newest: tuple[tuple[str, str], Observation, Path] | None = None
    for child in sorted(register.iterdir()) if _is_register(register) else ():
        if not _OBSERVATION_FILE.fullmatch(child.name) or not (
            child.is_symlink() or child.is_file()
        ):
            continue
        try:
            if child.is_symlink():
                raise _Invalid(
                    "symlink", message("reader.symbolic_link_instead_observation")
                )
            observation = _load_observation(child)
            if observation.same_content_as != current.name:
                continue
            _check_observation(
                child, observation, slot.split(":")[1], {current.name: entry.meta}.get
            )
        except _Invalid as exc:
            if exc.code == "unreadable" and isinstance(exc.__cause__, OSError):
                raise io_error(exc.__cause__) from exc.__cause__
            raise ObserwatorDataError(
                message(
                    "reader.corrupt_observation_slot",
                    slot=slot,
                    name=child.name,
                    exc=reason(exc),
                )
            ) from exc
        order = (observation.seen_at, child.name)
        if newest is None or order > newest[0]:
            newest = (order, observation, child)
    if newest is not None:
        _, observation, path = newest
        return _Reference(
            entry,
            observation.url,
            observation.etag,
            observation.last_modified,
            observation.size_bytes,
            path,
        )
    http = entry.meta.extra.get("http")
    signal: Mapping[str, object] = http if isinstance(http, Mapping) else {}
    texts: list[str | None] = []
    for key in ("url", "etag", "last_modified"):
        value = signal.get(key)
        if value is not None and not isinstance(value, str):
            raise ObserwatorDataError(
                message("reader.corrupt_version_slot_extra_http", slot=slot, key=key)
            )
        texts.append(value)
    url, etag, last_modified = texts
    return _Reference(entry, url, etag, last_modified, entry.meta.size_bytes, None)


# --------------------------------------------------------------------------
# Catalog and series
# --------------------------------------------------------------------------


def _main_file(version: PathArg, name: str) -> Path:
    path = Path(version).expanduser()
    if path.is_dir():
        path = path / name
    elif path.name == name + _SIDECAR:
        path = path.with_name(name)
    if path.name != name:
        raise ObserwatorValidationError(
            message(
                "reader.version_must_point_version_directory",
                name=name,
                version=version,
            ),
            details={"option": "version"},
        )
    return path


def _verified(path: Path) -> bytes:
    """Bytes of a version's main file, verified against its sidecar."""
    if path.is_symlink():
        raise ObserwatorDataError(
            message("reader.symbolic_link_instead_version_file", path=path)
        )
    try:
        data = path.read_bytes()
    except FileNotFoundError as exc:
        raise ObserwatorStoreError(
            message("reader.no_version_file", path=path), code="not_found"
        ) from exc
    except OSError as exc:
        raise io_error(exc) from exc
    meta = read_meta(path)
    if hashlib.sha256(data).hexdigest() != meta.sha256 or len(data) != meta.size_bytes:
        raise ObserwatorDataError(
            message("reader.checksum_does_not_match_sidecar", name=path.name, path=path)
        )
    return data


def _json(path: Path) -> Any:
    try:
        return json.loads(_verified(path))
    except ValueError as exc:
        raise ObserwatorDataError(
            message("reader.corrupt_json", path=path, exc=reason(exc))
        ) from exc


def _number(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(message("reader.coordinate_not_number"))
    return float(value)


def _plain(value: object, *, depth: int = 0) -> bool:
    """Whether a property is a scalar or, ``depth`` levels deep, an object of such values."""
    if isinstance(value, _SCALARS):
        return True
    return (
        depth > 0
        and isinstance(value, dict)
        and all(_plain(item, depth=depth - 1) for item in value.values())
    )


def _catalog_features(path: Path) -> tuple[StationFeature, ...]:
    """Stations of one catalog version, with the provider of its sidecar."""
    document = _json(path)
    provider = read_meta(path).provider
    result: list[StationFeature] = []
    try:
        if (
            not isinstance(document, dict)
            or document.get("type") != "FeatureCollection"
        ):
            raise ValueError(message("reader.featurecollection_was_expected"))
        features = document["features"]
        if not isinstance(features, list):
            raise ValueError(message("reader.features_must_list"))
        for feature in features:
            code = feature["id"]
            if (
                feature["type"] != "Feature"
                or not isinstance(code, str)
                or not _CODE.fullmatch(code)
            ):
                raise ValueError(message("reader.invalid_station_object", code=code))
            properties = feature["properties"]
            # Objects: ČHMÚ hydro stations' SPA thresholds (§7.4), PIG-PIB points'
            # hydrogeological description (ADR-035 W6).
            if not isinstance(properties, dict) or not all(
                _plain(value, depth=_NESTED.get(key, 0))
                for key, value in properties.items()
            ):
                raise ValueError(
                    message("reader.properties_station_must_simple_values", code=code)
                )
            if properties.get("station_code", code) != code:
                raise ValueError(
                    message("reader.station_code_station_differs_from", code=code)
                )
            geometry = feature["geometry"]
            point: tuple[float, float] | None = None
            if geometry is not None:
                coordinates = geometry["coordinates"]
                if (
                    geometry["type"] != "Point"
                    or not isinstance(coordinates, list)
                    or len(coordinates) != 2
                ):
                    raise ValueError(
                        message("reader.geometry_station_must_point_lon", code=code)
                    )
                point = (_number(coordinates[0]), _number(coordinates[1]))
            result.append(StationFeature(code, point, properties, provider))
    except (KeyError, TypeError, ValueError) as exc:
        raise ObserwatorDataError(
            message("reader.invalid_station_catalog", path=path, exc=reason(exc))
        ) from exc
    return tuple(result)


def read_catalog(
    version: PathArg | None = None,
    /,
    *,
    root: RootArg | None = None,
    provider: str | None = None,
) -> tuple[StationFeature, ...]:
    """
    Every station of a catalog version or of the current catalogs of a store.

    Stations without geometry are included. The ``stations.geojson`` bytes are
    verified against the SHA-256 and size recorded in the sidecar, and
    ``StationFeature.provider`` comes from the sidecar. ČHMÚ hydro stations
    carry their SPA thresholds as the object ``properties["thresholds"]``, PIG-PIB's
    points their hydrogeological description as ``properties["hydrogeology"]``.

    Parameters
    ----------
    version : str, os.PathLike or None, optional
        Catalog version directory or its ``stations.geojson`` file.
    root : str, os.PathLike, StoreHandle or None, optional
        Data root whose current catalog of every provider is read, in registry
        order (ADR-017); exactly one of ``version`` and ``root`` is required.
    provider : str or None, optional
        With ``root``: read only the current catalog of this provider
        (``ProviderDescriptor.id`` or key prefix); None reads the catalog of
        every provider and skips providers without one.

    Returns
    -------
    tuple of StationFeature
        With ``version``: stations in file order. With ``root``: the stations
        of each provider's catalog in registry order, each catalog sorted by
        ``station_code``. ``geometry`` is ``None`` for stations without a
        location.

    Raises
    ------
    ObserwatorValidationError
        If not exactly one of ``version`` and ``root`` is given, ``provider``
        is given with ``version`` or names no provider, or ``version`` points
        to neither a version directory nor ``stations.geojson``.
    ObserwatorStoreError
        If the catalog file or its sidecar does not exist, the root is not a
        supported store (code ``store_unavailable``), or the store holds no
        catalog of an explicitly given ``provider`` (code ``not_found``).
    ObserwatorDataError
        If a catalog version is broken, the file is a symbolic link, does not
        match its sidecar, or is not a valid station FeatureCollection; with
        code ``io_error`` (``details.path``) if the system cannot read it.
    """
    if version is not None and root is None:
        if provider is not None:
            raise ObserwatorValidationError(
                message("reader.option_provider_selects_current_store"),
                details={"option": "provider", "value": provider},
            )
        return _catalog_features(_main_file(version, CATALOG_FILE))
    if root is None or version is not None:
        raise ObserwatorValidationError(
            message("reader.give_exactly_one_version_catalog"),
            details={"option": "version" if root is None else "root"},
        )
    owners = providers() if provider is None else (get_provider(provider),)
    result: list[StationFeature] = []
    for owner in owners:
        key = _CATALOG_DATASETS[owner.id]
        entry = current_version(root, slot=f"catalog:{key}")
        if entry is None or entry.version is None:
            if provider is not None:
                raise ObserwatorStoreError(
                    message(
                        "reader.store_has_no_station_catalog",
                        short_name=owner.short_name,
                        key=key,
                        id=owner.id,
                    ),
                    code="not_found",
                    hint=message("errors.hint_store_catalog", provider=owner.id),
                )
            continue
        stations = _catalog_features(entry.version)
        result.extend(sorted(stations, key=lambda station: station.station_code))
    return tuple(result)


# --------------------------------------------------------------------------
# Archives and station lists
# --------------------------------------------------------------------------


def _station_lists(provider: str = "IMGW") -> dict[str, ArchiveFile]:
    """Station list source of each kind of a provider, keyed ``"hydro"`` / ``"meteo"``."""
    return dict(
        zip(("hydro", "meteo"), station_source_files(provider=provider), strict=True)
    )


def read_station_list(
    root: RootArg,
    /,
    *,
    kind: Literal["hydro", "meteo"],
    provider: str = "IMGW",
) -> tuple[StationListEntry, ...]:
    """
    Stations of the current stored station list of one family (offline).

    Reads the current version of the provider's list dataset
    (``pl.imgw.hydro_stations``/``pl.imgw.meteo_stations`` for IMGW-PIB,
    ``cz.chmu.hydro_stations``/``cz.chmu.meteo_stations`` — the historical
    ``meta1.json`` — for ČHMÚ), verifies its bytes against the SHA-256 and
    size of the sidecar and parses it with
    :func:`obserwator.parsers.parse_stations_csv` or
    :func:`obserwator.parsers.parse_chmu_stations`. Lists are stored in the
    raw root by ``obserwator store sync --datasets`` (ADR-015, ADR-017).

    Parameters
    ----------
    root : str, os.PathLike or StoreHandle
        Raw root directory or an open handle of one.
    kind : {"hydro", "meteo"}
        Station family of the list.
    provider : str, optional
        Provider of the list (``ProviderDescriptor.id`` or key prefix),
        ``"IMGW"`` by default.

    Returns
    -------
    tuple of StationListEntry
        Stations in file order, each with ``kind`` and ``provider`` set;
        hydro-only fields are ``None`` for meteorological stations. A code
        listed twice by IMGW (e.g. a meteo station with two short codes) is
        returned twice; `build_catalog` reports such codes in its
        ``problems``. A ČHMÚ list gives one entry per code (meteo: the
        location period with the latest ``BEGIN_DATE``).

    Raises
    ------
    ObserwatorValidationError
        If ``kind`` is neither ``"hydro"`` nor ``"meteo"``, or ``provider``
        names no provider.
    ObserwatorStoreError
        If the root is not a supported raw root (code ``store_unavailable``;
        ``details.reason`` ``wrong_root`` for a data root) or holds no version
        of the list (code ``not_found``, with the ``store sync`` that stores it
        as the hint).
    ObserwatorDataError
        If a version of the list is broken, or the current list does not
        match its sidecar or cannot be parsed.
    """
    owner = get_provider(provider)
    lists = _station_lists(owner.id)
    if kind not in lists:
        raise ObserwatorValidationError(
            message("reader.unknown_kind_station_list_allowed", kind=kind),
            details={"option": "kind", "value": kind, "allowed": list(lists)},
        )
    source = lists[kind]
    base = _open(root, kind="raw")
    entry = current_version(base, slot=str(_archive_slot(source.server_path)))
    if entry is None or entry.version is None or entry.meta is None:
        raise ObserwatorStoreError(
            message("reader.store_has_no_station_list", dataset=source.dataset),
            code="not_found",
            hint=message(
                "catalog.hint_sync_sources",
                root=base,
                datasets=source.dataset,
            ),
        )
    if entry.meta.dataset_key != source.dataset:
        raise ObserwatorDataError(
            message(
                "reader.version_belongs_dataset_not",
                version=entry.version,
                dataset=entry.meta.dataset,
                dataset_2=source.dataset,
            )
        )
    data = _verified(entry.version)
    adapter = get_provider(get_dataset(source.dataset).provider).adapter
    return tuple(
        adapter.parse_station_list(data, kind=kind, filename=str(entry.version))
    )


def _archive_main(version: PathArg) -> Path:
    """Main file of an archive version given as its directory, file or sidecar."""
    path = Path(version).expanduser()
    if path.is_dir():
        sidecars = sorted(
            child.name for child in path.iterdir() if child.name.endswith(_SIDECAR)
        )
        if len(sidecars) != 1:
            raise ObserwatorValidationError(
                message(
                    "reader.directory_not_archive_version_directory", version=version
                )
            )
        return path / sidecars[0].removesuffix(_SIDECAR)
    if path.name.endswith(_SIDECAR):
        return path.with_name(path.name.removesuffix(_SIDECAR))
    return path


def read_archive(version: PathArg, /) -> Iterator[NormalizedRecord]:
    """
    Normalized records of one stored archive version (offline).

    The archive is identified by its sidecar: ``dataset`` and
    ``request.server_path`` are resolved to the registry `ArchiveFile`, the
    stored bytes are verified against the sidecar SHA-256 and size, and the
    dataset parser (:func:`obserwator.parsers.normalize_archive`) is applied.
    Validation and verification happen before the iterator is returned;
    parsing is lazy.

    Parameters
    ----------
    version : str or os.PathLike
        Archive version directory, its main file or its sidecar.

    Returns
    -------
    Iterator of NormalizedRecord
        Records exactly as produced by ``normalize_archive`` for the stored
        bytes.

    Raises
    ------
    ObserwatorValidationError
        If ``version`` is not an archive version (e.g. a series, catalog or
        PMAXTP version, or a directory without exactly one sidecar), or is a
        station list version (read it with :func:`read_station_list`).
    ObserwatorStoreError
        If the archive file or its sidecar does not exist.
    ObserwatorDataError
        If the sidecar is invalid or does not describe a registry archive,
        or the file does not match its sidecar; while iterating, if the
        archive content is malformed.
    """
    main = _archive_main(version)
    meta = read_meta(main)
    server_path = meta.request.get("server_path")
    descriptor = next((d for d in datasets() if d.key == meta.dataset_key), None)
    if not isinstance(server_path, str) or descriptor is None:
        raise ObserwatorValidationError(
            message(
                "reader.not_archive_version_dataset_series",
                main=main,
                dataset=meta.dataset,
            )
        )
    if descriptor.time_unit == "station_list":
        kind = next(
            (
                k
                for k, a in _station_lists(descriptor.provider).items()
                if a.dataset == descriptor.key
            ),
            None,
        )
        if kind is None:
            raise ObserwatorValidationError(
                message(
                    "reader.version_station_metadata",
                    main=main,
                    dataset=meta.dataset,
                )
            )
        # The call needs no ``provider`` for the provider of its default.
        default = (read_station_list.__kwdefaults__ or {}).get("provider")
        option = (
            ""
            if descriptor.provider == default
            else f", provider={descriptor.provider!r}"
        )
        raise ObserwatorValidationError(
            message(
                "reader.version_station_list_station_lists",
                main=main,
                dataset=meta.dataset,
                kind=kind,
                option=option,
            )
        )
    if PurePosixPath(server_path).name != main.name:
        raise ObserwatorDataError(
            message(
                "reader.file_does_not_match_request",
                name=main.name,
                server_path=server_path,
            )
        )
    archive = _archive_from_path(descriptor.key, server_path)
    mismatch = (
        None
        if archive is None
        else next(
            (
                key
                for key in ("year", "month", "station_code", "param")
                if key in meta.request and meta.request[key] != getattr(archive, key)
            ),
            None,
        )
    )
    if archive is None or mismatch is not None:
        reason = (
            message(
                "reader.path_does_not_belong_dataset",
                server_path=server_path,
                key=descriptor.key,
            )
            if archive is None
            else message(
                "reader.request_does_not_match_path",
                mismatch=mismatch,
                server_path=server_path,
            )
        )
        raise ObserwatorDataError(
            message(
                "reader.sidecar_does_not_describe_archive", main=main, reason=reason
            )
        )
    return normalize_archive(archive, data=_verified(main))


def _date(value: object) -> date:
    if not isinstance(value, str):
        raise ValueError(message("reader.date_must_iso_text", value=value))
    return date.fromisoformat(value)


def _span(value: object) -> tuple[date, date]:
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError(message("reader.range_must_pair_dates"))
    start, end = _date(value[0]), _date(value[1])
    if start > end:
        raise ValueError(message("reader.range_reversed", start=start, end=end))
    return start, end


def _hour(value: object) -> datetime:
    """A time of a sub-daily series' index: the start of an hour, UTC, with ``Z``."""
    if not isinstance(value, str) or not _HOUR_TEXT.fullmatch(value):
        raise ValueError(message("reader.time_must_hour_text", value=value))
    return datetime.fromisoformat(value).astimezone(UTC)


def _hour_span(value: object) -> tuple[datetime, datetime]:
    """A gap of a sub-daily series: its first and last hour without a value."""
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError(message("reader.range_must_pair_hours"))
    start, end = _hour(value[0]), _hour(value[1])
    if start > end:
        raise ValueError(message("reader.range_reversed", start=start, end=end))
    return start, end


def _count(value: object, name: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(message("reader.must_integer", name=name, minimum=minimum))
    return value


def _coverage(
    code: str, key: str, value: Any, *, hourly: bool = False
) -> StationCoverage:
    """
    Coverage of one variable of a station's index entry.

    Days of a daily (or coarser) series; ``hourly`` (a sub-daily series, ADR-031)
    gives the times of hours as aware UTC datetimes.
    """
    variable, _, period = key.partition("@")
    if period and period not in _PERIODS:
        raise ValueError(message("reader.unknown_period_variable", key=key))
    unit = value["unit"]
    if not isinstance(unit, str):
        raise ValueError(message("reader.unit_variable_must_text", key=key))
    moment: Callable[[object], date] = _hour if hourly else _date
    span: Callable[[object], tuple[date, date]] = _hour_span if hourly else _span
    first = None if value["first"] is None else moment(value["first"])
    last = None if value["last"] is None else moment(value["last"])
    gaps = value["gaps"]
    if not isinstance(gaps, list):
        raise ValueError(message("reader.gaps_variable_must_list", key=key))
    return StationCoverage(
        code,
        variable,
        unit,
        cast("Literal['winter', 'summer', 'annual'] | None", period or None),
        first,
        last,
        _count(value["with_value"], "with_value"),
        _count(value["accumulated"], "accumulated"),
        tuple(span(gap) for gap in gaps),
    )


def _index_month(value: object, periods: tuple[tuple[date, date], ...]) -> str:
    """The ``month`` of the index of a sub-daily series; its ``periods`` lie in it."""
    if not isinstance(value, str) or not _MONTH.fullmatch(value):
        raise ValueError(message("reader.month_must_text", value=value))
    first, last = _month_span(value)
    for start, end in periods:
        if start < first or end > last:
            raise ValueError(
                message(
                    "reader.period_outside_month", start=start, end=end, month=value
                )
            )
    return value


def _index_tiers(value: object) -> tuple[Tier, ...]:
    """The ``tiers`` of the index of a sub-daily series: distinct, highest first, some."""
    if (
        not isinstance(value, list)
        or not value
        or [tier for tier in _SERIES_TIERS if tier in value] != value
    ):
        raise ValueError(
            message(
                "reader.tiers_must_list", tiers=", ".join(_SERIES_TIERS), value=value
            )
        )
    return tuple(cast("list[Tier]", value))


def _station_periods(code: str, value: object) -> tuple[tuple[date, date], ...] | None:
    """Known periods of one station: ascending, non-overlapping ranges, or None."""
    if value is None:
        return None
    if not isinstance(value, list):
        raise ValueError(message("reader.periods_station_must_list_ranges", code=code))
    spans = tuple(_span(item) for item in value)
    for (_, end), (start, _) in zip(spans, spans[1:], strict=False):
        if start <= end:
            raise ValueError(
                message("reader.periods_station_not_increasing_disjoint", code=code)
            )
    return spans


def read_series_index(version: PathArg, /) -> SeriesIndex:
    """
    Validate ``series.json`` and its Parquet paths without pyarrow or reading Parquet bytes.

    The ``series.json`` bytes are verified against the sidecar; each station
    Parquet file must exist as a regular file, but its contents are not read.
    The known periods of a station (``stations[<code>].periods``, written for
    datasets of per-station files, ADR-003 D10) must be ascending,
    non-overlapping date ranges when present, and the ``subset`` of a version
    built for chosen stations or years (ADR-026) sorted, distinct and not
    empty. A version of a sub-daily series (ADR-031) has its calendar month
    ``month`` (holding every day of ``periods``) and the ``tiers`` of its values
    (distinct, highest first, at least one), and its coverage gives hours
    (``YYYY-MM-DDTHH:00:00Z``) instead of days.

    Parameters
    ----------
    version : str or os.PathLike
        Series version directory or its ``series.json`` file.

    Returns
    -------
    SeriesIndex
        Dataset, year type, periods and per-station Parquet index (with the
        station periods, or None when the index has none), and the subset of
        a version built for chosen stations or years (None for a full series);
        of a version of a sub-daily series also ``month`` and ``tiers``, and
        ``first``, ``last`` and the gaps of its coverage as aware UTC
        datetimes of hours.

    Raises
    ------
    ObserwatorValidationError
        If ``version`` points to neither a version directory nor
        ``series.json``.
    ObserwatorStoreError
        If ``series.json`` or its sidecar does not exist.
    ObserwatorDataError
        If the file is a symbolic link, does not match its sidecar, or is
        not a valid ``obserwator-series/1`` index (including missing Parquet
        files); with code ``io_error`` (``details.path``) if the system
        cannot read it.
    """
    path = _main_file(version, SERIES_FILE)
    document = _json(path)
    try:
        if not isinstance(document, dict):
            raise ValueError(message("reader.series_json_not_object"))
        if document.get("schema") != SERIES_SCHEMA:
            raise ValueError(
                message("reader.unsupported_schema", schema=document.get("schema"))
            )
        dataset = document["dataset"]
        descriptor = get_dataset(dataset) if isinstance(dataset, str) else None
        if descriptor is None or descriptor.slug not in _series_datasets():
            raise ValueError(
                message("reader.dataset_does_not_build_series", dataset=dataset)
            )
        year_type = document["year_type"]
        if year_type not in ("hydrological", "calendar"):
            raise ValueError(message("reader.unknown_year_type", year_type=year_type))
        periods = tuple(_span(item) for item in document["periods"])
        month: str | None = None
        tiers: tuple[Tier, ...] | None = None
        if monthly_series(descriptor):
            month = _index_month(document.get("month"), periods)
            tiers = _index_tiers(document.get("tiers"))
        raw_stations = document["stations"]
        if not isinstance(raw_stations, dict):
            raise ValueError(message("reader.stations_must_object"))
        stations: dict[str, StationSeriesIndex] = {}
        for code, entry in raw_stations.items():
            if not _CODE.fullmatch(code):
                raise ValueError(message("reader.invalid_station_code", code=code))
            file, sha = entry["file"], entry["sha256"]
            if not isinstance(file, str) or not _PARQUET.fullmatch(file):
                raise ValueError(
                    message("reader.invalid_parquet_path_station", code=code, file=file)
                )
            if not isinstance(sha, str) or not _SHA.match(sha):
                raise ValueError(
                    message("reader.invalid_parquet_checksum_station", code=code)
                )
            parquet = path.parent / file
            if parquet.is_symlink() or not parquet.is_file():
                raise ValueError(message("reader.missing_file", file=file))
            variables = entry["variables"]
            if not isinstance(variables, dict):
                raise ValueError(
                    message("reader.variables_station_must_object", code=code)
                )
            stations[code] = StationSeriesIndex(
                Path(file),
                sha,
                _count(entry["rows"], "rows", minimum=1),
                {
                    key: _coverage(code, key, value, hourly=month is not None)
                    for key, value in variables.items()
                },
                _station_periods(code, entry.get("periods")),
            )
        subset = _document_subset(document.get("subset"))
    except (ObserwatorValidationError, KeyError, TypeError, ValueError) as exc:
        raise ObserwatorDataError(
            message("reader.invalid_series_index", path=path, exc=reason(exc))
        ) from exc
    return SeriesIndex(
        SERIES_SCHEMA, dataset, year_type, periods, stations, subset, month, tiers
    )


def _series_path(
    version: PathArg | None, *, root: RootArg | None, dataset: str | None
) -> Path:
    """
    ``series.json`` of a series version given explicitly or as the current one.

    ``version`` is absolute or relative to ``root`` (to the working
    directory without ``root``); ``root`` with ``dataset`` selects the
    current version of the dataset series. Giving ``version`` together with
    ``dataset``, or neither, is a validation error.
    """
    if (version is None) == (dataset is None):
        raise ObserwatorValidationError(
            message("reader.give_series_version_version_store"),
            details={"option": "version"},
        )
    if version is not None:
        if root is None:
            return _main_file(version, SERIES_FILE)
        path = _open(root, kind="data") / Path(version).expanduser()
        return _main_file(path, SERIES_FILE)
    if root is None:
        raise ObserwatorValidationError(
            message("reader.dataset_dataset_selects_current_series"),
            details={"option": "root"},
        )
    descriptor = _series_descriptor(str(dataset))
    entry = current_version(root, slot=f"series:{descriptor.key}")
    if entry is None or entry.version is None:
        raise _no_series(descriptor)
    return entry.version


def _no_series(descriptor: DatasetDescriptor) -> ObserwatorStoreError:
    """The store holds no version of a dataset's series: build it first."""
    return ObserwatorStoreError(
        message("reader.store_has_no_series_run", key=descriptor.key),
        code="not_found",
        hint=message("errors.hint_series_build", dataset=descriptor.key),
    )


def _series_paths(
    version: PathArg | None,
    *,
    root: RootArg | None,
    dataset: str | None,
    start: date | None = None,
    end: date | None = None,
) -> tuple[DatasetDescriptor | None, tuple[Path, ...]]:
    """
    ``series.json`` of every version a series reader reads, in time order.

    The one version of `_series_path` (given, or the current one of the
    dataset), and None; for a sub-daily series (`monthly_series`, ADR-031)
    given by ``root`` and ``dataset``, its descriptor and the current version
    of each of its months touching ``start``–``end`` (`series_months`; every
    month without them), possibly none.

    Raises
    ------
    ObserwatorStoreError
        Code ``not_found`` if the sub-daily series has no month at all, as a
        series without a version.
    """
    if version is None and dataset is not None and root is not None:
        descriptor = _series_descriptor(str(dataset))
        if monthly_series(descriptor):
            _check_bounds(start, end)
            months = series_months(root, dataset=descriptor.key, start=start, end=end)
            if not months and (
                (start is None and end is None)
                or not series_months(root, dataset=descriptor.key)
            ):
                raise _no_series(descriptor)
            return descriptor, tuple(
                entry.version for entry in months if entry.version is not None
            )
    return None, (_series_path(version, root=root, dataset=dataset),)


def _variables(
    variables: Iterable[str] | None, descriptor: DatasetDescriptor
) -> tuple[str, ...]:
    """Validated dataset variables without duplicates; ``None`` means all of them."""
    if variables is None:
        return tuple(descriptor.variables)
    if isinstance(variables, str):
        raise ObserwatorValidationError(
            message("reader.variables_must_list_variable_names"),
            details={"option": "variables", "value": variables},
        )
    names = tuple(dict.fromkeys(variables))
    unknown = [name for name in names if name not in descriptor.variables]
    if not names or unknown:
        raise ObserwatorValidationError(
            message(
                "reader.unknown_variables_available",
                unknown=", ".join(map(str, unknown)) or message("common.none"),
                available=", ".join(descriptor.variables),
            ),
            details={
                "option": "variables",
                "value": unknown,
                "allowed": list(descriptor.variables),
            },
        )
    return names


def _stations(stations: Iterable[str]) -> tuple[str, ...]:
    """Non-empty station codes (``STATION_CODE_PATTERN``) without duplicates, in order."""
    if isinstance(stations, str) or not isinstance(stations, Iterable):
        raise ObserwatorValidationError(
            message("reader.stations_must_list_station_codes"),
            details={"option": "stations", "value": str(stations)},
        )
    codes = tuple(dict.fromkeys(stations))
    invalid = [str(code) for code in codes if not _CODE.fullmatch(str(code))]
    if not codes or invalid:
        raise ObserwatorValidationError(
            message(
                "reader.invalid_station_codes_expected",
                codes=", ".join(invalid) or message("common.none"),
            ),
            details={"option": "stations", "value": invalid},
        )
    return codes


def _outside(codes: Iterable[str], index: SeriesIndex) -> None:
    _absent(codes, index.stations, index.dataset)


def _absent(codes: Iterable[str], held: Collection[str], dataset: str) -> None:
    """Refuse the station codes a series (all its months) does not hold."""
    missing = [code for code in codes if code not in held]
    if missing:
        raise ObserwatorValidationError(
            message(
                "reader.stations_outside_series",
                dataset=dataset,
                missing=", ".join(missing),
            ),
            details={"option": "stations", "value": missing},
        )


def read_series(
    version: PathArg | None = None,
    /,
    *,
    root: RootArg | None = None,
    dataset: str | None = None,
    station: str,
    variables: Iterable[str] | None = None,
    start: date | None = None,
    end: date | None = None,
) -> Iterator[NormalizedRecord]:
    """
    Values and flags of one station between ``start`` and ``end`` (inclusive, period start date).

    Arguments, the series index and the SHA-256 of the station Parquet file
    are validated before the iterator is returned. For monthly and
    half-year series the range filter applies to the period start
    (``date``). Days or months filled in by the builder are returned with
    the ``missing`` flag. Half-year records carry ``extrema_dates`` and, for
    units with IMGW rows, ``extrema_occurrences`` (``<V>_occurrences``).
    Measurements of datasets with measurement fields (ČHMÚ meteo) carry
    ``quality`` and ``source_flag`` from the ``<V>_quality`` and
    ``<V>_source_flag`` columns; elsewhere both are None.

    A sub-daily series (``pl.imgw.hydro_subdaily``, ``cz.chmu.hydro_subdaily``,
    ADR-031) has a version per calendar month: ``root`` with ``dataset`` reads
    the current version of every month (`series_months`) touching
    ``start``–``end`` and joins them in time order, ``version`` reads that
    month. Its records have ``time`` (the start of the hour, an aware UTC
    datetime) and ``date`` its UTC day, and each measurement the ``tier`` of its
    value (the ``<V>_tier`` cell, else the one tier of the version; None
    without a value); ``start`` and ``end`` select the hours from 00:00 of
    ``start`` to 23:00 of ``end`` (UTC). The station must be in a month of the
    series; a month without it is skipped.

    Parameters
    ----------
    version : str, os.PathLike or None, optional
        Series version directory, its ``series.json`` or its sidecar;
        absolute or relative to ``root`` (to the working directory without
        ``root``). Mutually exclusive with ``dataset``.
    root : str, os.PathLike, StoreHandle or None, optional
        Data root (ADR-017): the base of a relative ``version``, or with
        ``dataset`` the root whose current series version is read.
    dataset : str or None, optional
        Series dataset (key, slug or legacy alias) whose current version in
        ``root`` is read.
    station : str
        Station code (``STATION_CODE_PATTERN``) present in the series.
    variables : Iterable[str] or None, optional
        Dataset variable names; duplicates are merged, a single string or an
        empty collection is rejected. ``None`` (default) means every variable
        of the dataset.
    start : datetime.date or None, optional
        First period start date (UTC day of an hour) to include; ``None``
        means no lower bound.
    end : datetime.date or None, optional
        Last period start date (UTC day of an hour) to include; ``None``
        means no upper bound.

    Returns
    -------
    Iterator[NormalizedRecord]
        Records of the station in Parquet row order (of a sub-daily series
        read by ``dataset``: month by month).

    Raises
    ------
    ObserwatorValidationError
        If both or neither of ``version`` and ``dataset`` are given,
        ``dataset`` lacks ``root`` or does not produce series, ``version`` is
        not a series version, the station is not in the series,
        ``variables`` is empty, a string or contains unknown names, a bound
        is not a ``date`` or ``start`` is later than ``end``.
    ObserwatorStoreError
        If ``series.json``, its sidecar or the dataset series does not exist
        (code ``not_found``) or ``root`` is not a supported store (code
        ``store_unavailable``).
    ObserwatorStoreDependencyError
        If ``pyarrow>=15`` is not installed.
    ObserwatorDataError
        If the index or Parquet file is corrupted or does not match its
        checksum or metadata; with code ``io_error`` (``details.path``) if
        the system cannot read it.
    """
    monthly, paths = _series_paths(
        version, root=root, dataset=dataset, start=start, end=end
    )
    if monthly is not None:
        assert root is not None  # the months of a dataset are those of a root
        parts = _month_parts(
            paths,
            root=root,
            descriptor=monthly,
            station=station,
            variables=variables,
            start=start,
            end=end,
        )
        return chain.from_iterable(records for _, records in parts)
    (path,) = paths
    index = read_series_index(path)
    if station not in index.stations:
        raise _station_absent(station, index.dataset)
    descriptor = get_dataset(index.dataset)
    names = _variables(variables, descriptor)
    _check_bounds(start, end)
    return _version_records(
        path, index, descriptor, station=station, names=names, start=start, end=end
    )


def _station_absent(station: str, dataset: str) -> ObserwatorValidationError:
    return ObserwatorValidationError(
        message("reader.station_not_series", station=station, dataset=dataset),
        details={"option": "station", "value": station},
    )


def _month_parts(
    paths: tuple[Path, ...],
    *,
    root: RootArg,
    descriptor: DatasetDescriptor,
    station: str,
    variables: Iterable[str] | None,
    start: date | None,
    end: date | None,
) -> list[tuple[Path, Iterator[NormalizedRecord]]]:
    """
    The records of a station in each month of a sub-daily series it is in.

    ``paths`` are the months within ``start``–``end`` (`_series_paths`), each
    validated with its station file before anything is returned. The station
    must be in one of the series' months: when none of ``paths`` holds it, the
    months outside the range are asked, and a station held only there has no
    records in the range.
    """
    indexes = [(path, read_series_index(path)) for path in paths]
    holding = [(path, index) for path, index in indexes if station in index.stations]
    if not holding and (
        (start is None and end is None)
        or not any(
            station in read_series_index(entry.version).stations
            for entry in series_months(root, dataset=descriptor.key)
            if entry.version is not None and entry.version not in paths
        )
    ):
        raise _station_absent(station, descriptor.key)
    names = _variables(variables, descriptor)
    return [
        (
            path,
            _version_records(
                path,
                index,
                descriptor,
                station=station,
                names=names,
                start=start,
                end=end,
            ),
        )
        for path, index in holding
    ]


def _version_records(
    path: Path,
    index: SeriesIndex,
    descriptor: DatasetDescriptor,
    *,
    station: str,
    names: tuple[str, ...],
    start: date | None,
    end: date | None,
) -> Iterator[NormalizedRecord]:
    """
    The records of a station in one series version, its Parquet file verified.

    The file is read and checked against the index (SHA-256, metadata, rows)
    now; its rows become records while the iterator is consumed. A version of
    a sub-daily series (``index.month``) has ``time`` instead of ``date`` and,
    when its values have several tiers, a ``<V>_tier`` column of every variable.
    """
    pa, pq = _pyarrow()
    entry = index.stations[station]
    parquet = path.parent / entry.file
    try:
        data = parquet.read_bytes()
    except FileNotFoundError as exc:
        raise ObserwatorDataError(
            message(
                "reader.missing_parquet_file_station_from",
                station=station,
                parquet=parquet,
            )
        ) from exc
    except OSError as exc:
        raise io_error(exc) from exc
    if hashlib.sha256(data).hexdigest() != entry.sha256:
        raise ObserwatorDataError(
            message(
                "reader.parquet_checksum_station_does_not",
                station=station,
                parquet=parquet,
            )
        )
    hourly = index.tiers is not None
    half_year = descriptor.time_unit == "half_year"
    columns = [
        "time" if hourly else "date",
        "hydro_year",
        *(["period"] if half_year else []),
    ]
    try:
        # ``<V>_occurrences`` is an additive obserwator-series/1 column; older files lack it.
        present = set(pq.read_schema(pa.BufferReader(data)).names)
        for name in names:
            columns += [f"{name}_value", f"{name}_flag"]
            columns += [f"{name}_{field}" for field in descriptor.measurement_fields]
            # A month of several tiers has the tier of every value (ADR-031).
            if hourly and (len(index.tiers or ()) > 1 or f"{name}_tier" in present):
                columns.append(f"{name}_tier")
            if half_year:
                columns += [f"{name}_start", f"{name}_end"]
                if f"{name}_occurrences" in present:
                    columns.append(f"{name}_occurrences")
        table = pq.read_table(pa.BufferReader(data), columns=columns)
        metadata = table.schema.metadata or {}
        if (
            metadata.get(b"obserwator_schema") != SERIES_SCHEMA.encode()
            or metadata.get(b"dataset") != index.dataset.encode()
        ):
            raise ValueError(message("reader.parquet_metadata_do_not_match"))
        if hourly and getattr(table.schema.field("time").type, "tz", None) is None:
            raise ValueError(message("reader.time_column_without_zone"))
        if table.num_rows != entry.rows:
            raise ValueError(
                message(
                    "reader.number_rows_differs_from_index",
                    num_rows=table.num_rows,
                    rows=entry.rows,
                )
            )
        rows = table.to_pylist()
    except (pa.ArrowException, ValueError) as exc:
        raise ObserwatorDataError(
            message(
                "reader.invalid_parquet_station",
                station=station,
                parquet=parquet,
                exc=reason(exc),
            )
        ) from exc
    return _records(
        rows,
        station=station,
        dataset=index.dataset,
        names=names,
        fields=descriptor.measurement_fields,
        half_year=half_year,
        start=start,
        end=end,
        tiers=index.tiers,
    )


def _records(
    rows: list[dict[str, Any]],
    *,
    station: str,
    dataset: str,
    names: tuple[str, ...],
    fields: tuple[str, ...],
    half_year: bool,
    start: date | None,
    end: date | None,
    tiers: tuple[Tier, ...] | None = None,
) -> Iterator[NormalizedRecord]:
    """
    Records of the rows of a station file, within ``start``–``end``.

    ``tiers`` (of a version of a sub-daily series, ADR-031) reads ``time``: the
    record's ``date`` is its UTC day, and a value's tier is its ``<V>_tier``
    cell, else the one tier of the version; a point without a value has none.
    """
    with_quality, with_source_flag = "quality" in fields, "source_flag" in fields
    for row in rows:
        moment = None if tiers is None else cast(datetime, row["time"]).astimezone(UTC)
        day = row["date"] if moment is None else moment.date()
        if (start is not None and day < start) or (end is not None and day > end):
            continue
        measurements: dict[str, Measurement] = {}
        for name in names:
            value, flag = row[f"{name}_value"], row[f"{name}_flag"]
            if flag not in _FLAGS or (value is None) != (flag == "missing"):
                raise ObserwatorDataError(
                    message(
                        "reader.inconsistent_flag_variable_station",
                        flag=flag,
                        name=name,
                        station=station,
                        day=moment or day,
                    )
                )
            quality = row[f"{name}_quality"] if with_quality else None
            source_flag = row[f"{name}_source_flag"] if with_source_flag else None
            if not (quality is None or type(quality) is int) or not (
                source_flag is None or isinstance(source_flag, str)
            ):
                raise ObserwatorDataError(
                    message(
                        "reader.invalid_quality_source_flag_variable",
                        name=name,
                        station=station,
                        day=moment or day,
                    )
                )
            tier: Tier | None = None
            if tiers is not None:
                tier = row.get(f"{name}_tier", tiers[0] if value is not None else None)
                if (tier is None) != (value is None) or (
                    tier is not None and tier not in tiers
                ):
                    raise ObserwatorDataError(
                        message(
                            "reader.inconsistent_tier_variable_station",
                            tier=tier,
                            name=name,
                            station=station,
                            time=moment,
                        )
                    )
            measurements[name] = Measurement(value, flag, quality, source_flag, tier)
        extrema = (
            {name: (row[f"{name}_start"], row[f"{name}_end"]) for name in names}
            if half_year
            else {}
        )
        occurrences = {
            name: count
            for name in names
            if (count := row.get(f"{name}_occurrences")) is not None
        }
        yield NormalizedRecord(
            station,
            dataset,
            day,
            row["hydro_year"],
            row["period"] if half_year else None,
            measurements,
            extrema_dates=extrema,
            extrema_occurrences=occurrences,
            time=moment,
        )


def summarize_series(
    version: PathArg | None = None,
    /,
    *,
    root: RootArg | None = None,
    dataset: str | None = None,
    stations: Iterable[str] | None = None,
    variables: Iterable[str] | None = None,
) -> tuple[StationCoverage, ...]:
    """
    Coverage of a series version read only from its ``series.json`` (no pyarrow).

    The index bytes are verified against the sidecar and every station
    Parquet file must exist, but Parquet contents are not read.

    A sub-daily series (ADR-031) gives hours (aware UTC datetimes) in
    ``first``, ``last`` and the gaps. With ``root`` and ``dataset`` its months
    (`series_months`) are joined per station and variable: the first and the
    last hour with a value of all months, the sums of ``with_value`` and
    ``accumulated``, and the gaps of every month with the hours between two
    months: those inside the months' ``periods`` (hours outside are unknown,
    never gaps) without a value from the last value of a month to the first of
    the next month with one; gaps that touch are merged. ``version`` summarizes
    that month.

    Parameters
    ----------
    version : str, os.PathLike or None, optional
        Series version directory, its ``series.json`` or its sidecar;
        absolute or relative to ``root`` (to the working directory without
        ``root``). Mutually exclusive with ``dataset``.
    root : str, os.PathLike, StoreHandle or None, optional
        Data root (ADR-017): the base of a relative ``version``, or with
        ``dataset`` the root whose current series version is summarized.
    dataset : str or None, optional
        Series dataset (key, slug or legacy alias) whose current version in
        ``root`` is summarized.
    stations : Iterable[str] or None, optional
        Station codes (``STATION_CODE_PATTERN``) in the series; ``None``
        (default) means every station.
    variables : Iterable[str] or None, optional
        Dataset variable names; ``None`` (default) means every variable.

    Returns
    -------
    tuple of StationCoverage
        One row per station × variable (× half-year period) ordered by
        station code, then variable in dataset order, then period
        (``winter``, ``summer``, ``annual``); of a sub-daily series read by
        ``dataset``, every station of any month.

    Raises
    ------
    ObserwatorValidationError
        If both or neither of ``version`` and ``dataset`` are given,
        ``dataset`` lacks ``root`` or does not produce series, ``version`` is
        not a series version, a station code is malformed or not in the
        series, or a variable is unknown.
    ObserwatorStoreError
        If ``series.json``, its sidecar or the dataset series does not exist
        (code ``not_found``) or ``root`` is not a supported store (code
        ``store_unavailable``).
    ObserwatorDataError
        If the index does not match its sidecar or is not a valid
        ``obserwator-series/1`` index; with code ``io_error`` (``details.path``)
        if the system cannot read it.
    """
    monthly, paths = _series_paths(version, root=root, dataset=dataset)
    held: Mapping[str, Collection[StationCoverage]]
    if monthly is None:
        index = read_series_index(paths[0])
        descriptor, key = get_dataset(index.dataset), index.dataset
        held = {
            code: entry.variables.values() for code, entry in index.stations.items()
        }
    else:
        descriptor, key = monthly, monthly.key
        held = _joined_coverage([read_series_index(path) for path in paths])
    names = set(_variables(variables, descriptor))
    if stations is None:
        codes = tuple(sorted(held))
    else:
        codes = tuple(sorted(_stations(stations)))
        _absent(codes, held, key)
    order = {
        name: number
        for number, name in enumerate(descriptor.variables)
        if name in names
    }
    periods: dict[str | None, int] = {
        None: 0,
        **{period: number for number, period in enumerate(_PERIODS)},
    }
    return tuple(
        coverage
        for code in codes
        for coverage in sorted(
            (item for item in held[code] if item.variable in order),
            key=lambda item: (order[item.variable], periods[item.period]),
        )
    )


def _joined_coverage(
    indexes: Iterable[SeriesIndex],
) -> dict[str, Collection[StationCoverage]]:
    """
    Coverage of a sub-daily series over its months, in month order, per station.

    See `summarize_series`: the hours known between two months are those of the
    days of the months' ``periods``, which a month version gives every station.
    """
    months = list(indexes)
    known = _merged_days(span for index in months for span in index.periods)
    found: dict[str, dict[str, list[StationCoverage]]] = {}
    for index in months:
        for code, entry in index.stations.items():
            for key, coverage in entry.variables.items():
                found.setdefault(code, {}).setdefault(key, []).append(coverage)
    return {
        code: [_joined(items, known) for items in variables.values()]
        for code, variables in found.items()
    }


def _joined(
    months: list[StationCoverage], known: list[tuple[date, date]]
) -> StationCoverage:
    """One variable of a station over its months (`_joined_coverage`)."""
    valued = [item for item in months if item.first is not None]
    gaps = [gap for item in months for gap in item.gaps]
    for previous, following in zip(valued, valued[1:], strict=False):
        lower = cast(datetime, previous.last) + _HOUR
        upper = cast(datetime, following.first) - _HOUR
        for first_day, last_day in known:
            start = max(lower, datetime.combine(first_day, datetime.min.time(), UTC))
            end = min(
                upper, datetime.combine(last_day, datetime.min.time(), UTC) + 23 * _HOUR
            )
            if start <= end:
                gaps.append((start, end))
    merged: list[tuple[date, date]] = []
    for low, high in sorted(gaps):
        if merged and low <= cast(datetime, merged[-1][1]) + _HOUR:
            merged[-1] = (merged[-1][0], max(merged[-1][1], high))
        else:
            merged.append((low, high))
    head = months[0]
    return StationCoverage(
        head.station_code,
        head.variable,
        head.unit,
        head.period,
        min((item.first for item in valued if item.first), default=None),
        max((item.last for item in valued if item.last), default=None),
        sum(item.with_value for item in months),
        sum(item.accumulated for item in months),
        tuple(merged),
    )


def _merged_days(spans: Iterable[tuple[date, date]]) -> list[tuple[date, date]]:
    """Ranges of days, ascending, those that overlap or touch merged."""
    merged: list[tuple[date, date]] = []
    for start, end in sorted(spans):
        if merged and start <= merged[-1][1] + timedelta(days=1):
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def _period_years(periods: Iterable[tuple[date, date]], year_type: str) -> set[int]:
    """Years (hydrological or calendar) touched by the published periods."""

    def year(day: date) -> int:
        return (
            day.year + 1
            if year_type == "hydrological" and day.month >= 11
            else day.year
        )

    return {
        number for start, end in periods for number in range(year(start), year(end) + 1)
    }


def select_series(
    root: RootArg,
    /,
    *,
    dataset: str,
    stations: Iterable[str],
    variables: Iterable[str] | None = None,
    years: YearsArg | None = None,
    year_type: Literal["hydrological", "calendar"] | None = None,
) -> SeriesSelection:
    """
    Validate a selection of stations, variables and years from the current series.

    Nothing is written. The current series version of ``dataset`` in
    ``root`` must contain every selected station and every selected year. A
    selection hands daily series to the analyses, so a sub-daily series
    (ADR-031) is refused.

    Parameters
    ----------
    root : str, os.PathLike or StoreHandle
        Data root directory (ADR-017) or an open handle of one.
    dataset : str
        Series dataset (key, slug or legacy alias).
    stations : Iterable[str]
        Non-empty station codes (``STATION_CODE_PATTERN``); duplicates are
        merged, order is kept.
    variables : Iterable[str] or None, optional
        Dataset variable names; ``None`` (default) means every variable.
    years : YearsArg or None, optional
        Years (``2024``, ``"2020-2023"``, ``"2020,2022"`` or a collection of
        such items); ``None`` (default) means every year of the series.
    year_type : {"hydrological", "calendar"} or None, optional
        Year numbering of ``years``; ``None`` (default) means the numbering of
        the series. Half-year series accept only ``"hydrological"``.

    Returns
    -------
    SeriesSelection
        Full dataset key, ``series.json`` of the current version, stations,
        variables, sorted years and the year type.

    Raises
    ------
    ObserwatorValidationError
        If the dataset does not produce series or is a sub-daily series
        (``details.option`` ``dataset``, ``details.reason`` ``monthly``), a
        station code is malformed or not in the series, a variable is unknown,
        ``years`` is invalid or outside the series, or ``year_type`` is unknown
        or ``"calendar"`` for a half-year series.
    ObserwatorStoreError
        If the dataset has no series in the store (code ``not_found``) or the
        root is not a supported store (code ``store_unavailable``).
    ObserwatorDataError
        If the current series index is broken.
    """
    descriptor = _series_descriptor(dataset)
    if monthly_series(descriptor):
        raise ObserwatorValidationError(
            message("reader.selection_refuses_monthly", key=descriptor.key),
            details={"option": "dataset", "value": dataset, "reason": "monthly"},
        )
    codes = _stations(stations)
    names = _variables(variables, descriptor)
    if year_type is not None and year_type not in ("hydrological", "calendar"):
        raise ObserwatorValidationError(
            message(
                "reader.unknown_kind_year_allowed_hydrological", year_type=year_type
            ),
            details={
                "option": "year_type",
                "value": str(year_type),
                "allowed": ["hydrological", "calendar"],
            },
        )
    if descriptor.time_unit == "half_year" and year_type == "calendar":
        raise ObserwatorValidationError(
            message("reader.semi_annual_series_supports_only"),
            details={"option": "year_type", "value": year_type},
        )
    selected = parse_years(years) if years is not None else None
    path = _series_path(None, root=root, dataset=descriptor.key)
    index = read_series_index(path)
    _outside(codes, index)
    kind = year_type or index.year_type
    available = _period_years(index.periods, kind)
    chosen = selected if selected is not None else tuple(sorted(available))
    outside = [year for year in chosen if year not in available]
    if outside:
        raise ObserwatorValidationError(
            message(
                "reader.years_outside_series",
                key=descriptor.key,
                kind=kind,
                years=", ".join(map(str, outside)),
            ),
            details={"option": "years", "value": outside},
        )
    return SeriesSelection(descriptor.key, path, codes, names, chosen, kind)
