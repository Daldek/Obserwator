"""
The publication state of the sources on the REST routes (P15, ADR-030 D5).

A source of a tier other than ``verified`` (the captures, IMGW-PIB's telemetry,
ČHMÚ's groundwater months, a provider fed by files of an unverified tier, ADR-033)
whose state in force is ``private`` (`obserwator.captures.publication`:
``[obserwator.capture]`` of ``nogat.toml``, read on every request, else the source's
default, that of its provider file for a provider fed by files) is left out of the REST
API and of MCP over HTTP, which answers through these routes: an option naming it
(``dataset``, ``datasets``, an item of a ``store sync`` plan) and a ``version`` below
one of its slots or below ``series/versions/<its slug>/`` are ``not_found``
(``details.reason`` ``private``) before any request, a version that exists answering
like one that does not, as for a station an instance does not serve (ADR-025 D2). So
is a sub-daily series built from a private source (ADR-031: its state follows its
inputs), by its dataset and by a version below ``series/versions/<its slug>/``. The
CLI, the library and the MCP server on stdio read every source.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import cast

from obserwator.captures import publication, publication_sources
from obserwator.datasets import (
    CAPTURE_SCOPE,
    CAPTURE_SUFFIX,
    DatasetDescriptor,
    _capture_from_path,
    datasets,
    get_provider,
)
from obserwator.exceptions import ObserwatorError
from obserwator.messages import message
from obserwator.store.types import StorePlan

__all__ = ["guard", "refuse_version"]


def _private() -> tuple[DatasetDescriptor, ...]:
    """
    The sources (datasets of a tier other than ``verified``) set ``private``.

    With them the sub-daily series (``DatasetDescriptor.inputs``, ADR-031) whose
    state, that of their inputs, is ``private``.
    """
    candidates = (*publication_sources(), *(d for d in datasets() if d.inputs))
    return tuple(d for d in candidates if publication(d.key) == "private")


def _not_found(
    descriptor: DatasetDescriptor, option: str, value: object
) -> ObserwatorError:
    if descriptor.inputs:
        text = message("api.series_private", dataset=descriptor.key)
    elif get_provider(descriptor.provider).adapter.provider_file is not None:
        text = message("api.files_private", dataset=descriptor.key)
    else:
        text = message("api.capture_private", dataset=descriptor.key)
    return ObserwatorError(
        text,
        code="not_found",
        details={"option": option, "value": value, "reason": "private"},
    )


def _names(value: object) -> tuple[str, ...]:
    """The texts of a normalized option: none, one, or a tuple of them."""
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    return tuple(str(item) for item in cast("Iterable[object]", value))


def guard(options: Mapping[str, object]) -> None:
    """
    Refuse a private source (a dataset not ``verified``) that the options name.

    Called with the options `obserwator.commands.validate_command` normalized (the
    keys of datasets), before the command runs or plans. A sub-daily series of a
    private source (ADR-031) is refused alike.

    Parameters
    ----------
    options : Mapping of str to object
        The normalized options; a ``plan`` is the path of an ``obserwator-plan/1``
        file.

    Raises
    ------
    ObserwatorError
        ``not_found`` (``details.option`` ``dataset``, ``datasets`` or ``plan``,
        ``details.reason`` ``private``).
    """
    private = {descriptor.key: descriptor for descriptor in _private()}
    if not private:
        return
    for name in ("dataset", "datasets"):
        for key in _names(options.get(name)):
            if key in private:
                raise _not_found(private[key], name, key)
    plan = options.get("plan")
    if isinstance(plan, Path):
        for item in StorePlan.from_json(plan).items:
            if item.archive.dataset in private:
                raise _not_found(
                    private[item.archive.dataset], "plan", item.archive.server_path
                )


def _owner(rest: Sequence[str]) -> DatasetDescriptor | None:
    """
    The dataset of the files below ``archives/versions/<rest>``, by its path alone.

    The longest server directory of the registry that ``rest`` lies below (as the
    store's readers find a slot's dataset), captures left out: they share their
    directories and are told apart by the day of their slot (`refuse_version`).
    """
    found: tuple[int, DatasetDescriptor] | None = None
    for descriptor in datasets(pending=True):
        if descriptor.archive_scope == CAPTURE_SCOPE or descriptor.server_dir is None:
            continue
        directory = descriptor.server_dir.split("/")
        if (
            len(rest) > len(directory)
            and list(rest[: len(directory)]) == directory
            and (found is None or len(directory) > found[0])
        ):
            found = (len(directory), descriptor)
    return None if found is None else found[1]


def refuse_version(parts: Sequence[str]) -> None:
    """
    Refuse a version below a slot of a private source, by its path alone.

    Parameters
    ----------
    parts : sequence of str
        The segments of the version's path below the root, checked for their form
        (``archives/versions/…``, ``series/versions/…``) but not for existence: the
        slot directory of a capture's day is ``<server_dir>/<YYYY-MM-DD>`` (ADR-030
        D3), that of any other file a directory below its dataset's server directory
        (IMGW-PIB's telemetry: ``Arch/Telemetria/Hydro/<YYYY>/Hydro_<YYYY-MM>``; a
        provider fed by files: ``files/<acronym>/<dataset>/<station code>``), and the
        versions of a series lie below ``series/versions/<slug>/`` (a sub-daily one
        of ADR-031 and the series of a private source alike).

    Raises
    ------
    ObserwatorError
        ``not_found`` (``details.option`` ``version``, ``details.reason``
        ``private``).
    """
    if list(parts[:2]) == ["series", "versions"]:
        slug = parts[2] if len(parts) > 2 else None
        for descriptor in _private():
            if descriptor.slug == slug:
                raise _not_found(descriptor, "version", "/".join(parts))
        return
    if list(parts[:2]) != ["archives", "versions"]:
        return
    rest = list(parts[2:])
    private = _private()
    for descriptor in private:
        if descriptor.archive_scope != CAPTURE_SCOPE:
            continue
        directory = (descriptor.server_dir or "").split("/")
        size = len(directory)
        if (
            len(rest) > size
            and rest[:size] == directory
            and _capture_from_path(
                descriptor, f"{descriptor.server_dir}/{rest[size]}{CAPTURE_SUFFIX}"
            )
            is not None
        ):
            raise _not_found(descriptor, "version", "/".join(parts))
    owner = _owner(rest)
    if owner is not None and owner in private:
        raise _not_found(owner, "version", "/".join(parts))
