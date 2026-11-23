"""
The publication state of the captures on the REST routes (P15, ADR-030 D5).

A capture dataset whose state in force is ``private`` (`obserwator.captures.publication`:
``[obserwator.capture]`` of ``nogat.toml``, read on every request, else the source's
default) is left out of the REST API and of MCP over HTTP, which answers through these
routes: an option naming it (``dataset``, ``datasets``, an item of a ``store sync``
plan) and a ``version`` below one of its slots are ``not_found`` (``details.reason``
``private``) before any request, a version that exists answering like one that does
not, as for a station an instance does not serve (ADR-025 D2). The CLI, the library and
the MCP server on stdio read every capture.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import cast

from obserwator.captures import capture_datasets, publication
from obserwator.datasets import CAPTURE_SUFFIX, DatasetDescriptor, _capture_from_path
from obserwator.exceptions import ObserwatorError
from obserwator.messages import message
from obserwator.store.types import StorePlan

__all__ = ["guard", "refuse_version"]


def _private() -> tuple[DatasetDescriptor, ...]:
    """The capture datasets whose publication state in force is ``private``."""
    return tuple(d for d in capture_datasets() if publication(d.key) == "private")


def _not_found(key: str, option: str, value: object) -> ObserwatorError:
    return ObserwatorError(
        message("api.capture_private", dataset=key),
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
    Refuse a private capture dataset that the options name.

    Called with the options `obserwator.commands.validate_command` normalized (the
    keys of datasets), before the command runs or plans.

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
    private = {descriptor.key for descriptor in _private()}
    if not private:
        return
    for name in ("dataset", "datasets"):
        for key in _names(options.get(name)):
            if key in private:
                raise _not_found(key, name, key)
    plan = options.get("plan")
    if isinstance(plan, Path):
        for item in StorePlan.from_json(plan).items:
            if item.archive.dataset in private:
                raise _not_found(item.archive.dataset, "plan", item.archive.server_path)


def refuse_version(parts: Sequence[str]) -> None:
    """
    Refuse a version below a slot of a private capture dataset, by its path alone.

    Parameters
    ----------
    parts : sequence of str
        The segments of the version's path below the root, checked for their form
        (``archives/versions/…``) but not for existence: the slot directory of a
        capture's day is ``<server_dir>/<YYYY-MM-DD>`` (ADR-030 D3).

    Raises
    ------
    ObserwatorError
        ``not_found`` (``details.option`` ``version``, ``details.reason``
        ``private``).
    """
    if list(parts[:2]) != ["archives", "versions"]:
        return
    rest = list(parts[2:])
    for descriptor in _private():
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
            raise _not_found(descriptor.key, "version", "/".join(parts))
