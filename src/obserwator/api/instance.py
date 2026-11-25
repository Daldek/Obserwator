"""
The operator's instance on the REST routes (ADR-025).

With ``[obserwator.instance]`` in ``nogat.toml`` the REST server serves only what the
instance serves; without the section nothing changes. `check_start` refuses the start
on a provider file of ``nogat.toml`` that cannot be used (ADR-033), reads the section as
the server starts (`served_instance` keeps it for the process) and stops the start on a
problem of it, on a root of a layout this version does not read (`check_root_layout`)
and, with the section, on a weak write token (`check_credentials`; only a warning
without it). `scope_of` gives each request of a catalog command its `Scope`, or None
without an instance:

- before the root: a route of IMGW-PIB's current data while IMGW-PIB is ``off`` and a
  route of PMAXTP with ``pmaxtp = "off"`` are ``not_found`` before any request;
  `Scope.version` refuses a ``version`` of a provider that is ``off`` by its path alone,
  so a version that exists answers like one that does not;
- after `validate_command` (`Scope.guard`, also for ``?check=true``): a provider, a
  dataset or a station an option names and the instance does not serve is ``not_found``
  (``details.reason`` ``not_served``; a station by `Instance.serves_station`, which
  answers a code that does not exist the same way), and so is the provider file of
  ``store import`` that adds such a provider; a PMAXTP point outside a clipped
  area is ``not_found`` (``outside_area``); a command whose answer would hold stations
  outside a clipped area and cannot be reduced exactly is ``forbidden``
  (``instance_clip``); ``stations find`` and ``stations export`` without a provider name
  the one provider served;
- the run (`Scope.run`): a list keeps the items served before it is paged with the
  catalog's own cursors, and its lines are derived from the page as `run_command`
  derives them; ``store info`` names the providers served, ``stations export`` exports
  the stations `Instance.keeps` and ``pmaxtp read`` refuses a cell outside a clipped area.

The CLI and the MCP server never apply an instance.
"""

from __future__ import annotations

import functools
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any, NoReturn, cast

from obserwator.attribution import Attribution
from obserwator.commands import _ATTRIBUTIONS, _GROUP_PROVIDERS, run_command
from obserwator.config import check_credentials, check_root_layout, settings
from obserwator.datasets import (
    DatasetDescriptor,
    check_provider_files,
    datasets,
    get_dataset,
    get_provider,
    provider_files,
    providers,
)
from obserwator.exceptions import ObserwatorError, ObserwatorValidationError
from obserwator.instance import Instance, load_instance
from obserwator.messages import message
from obserwator.models import PMaXTPResult
from obserwator.store import analysis_definitions, current_version
from obserwator.store.export import _catalogs
from obserwator.store.types import (
    CommandResult,
    DataCommand,
    Page,
    RootKind,
    StoreInfo,
    StorePlan,
    cursor_index,
    page_cursor,
)

__all__ = ["Scope", "check_start", "scope_of", "served_instance"]


@functools.cache
def served_instance() -> Instance | None:
    """
    The instance this process serves: ``[obserwator.instance]``, read once (I7).

    Returns
    -------
    Instance or None
        The section, None without it.

    Raises
    ------
    ObserwatorValidationError
        A problem of the section (`load_instance`); an error is not kept, so the
        next call reads the file again.
    """
    return load_instance()


def check_start(*, warn: bool = True) -> Instance | None:
    """
    Check what the REST server serves as it starts (ADR-025, ADR-033, I7, I10, I12).

    Parameters
    ----------
    warn : bool, optional
        Log a weak write token of a server without an instance; ``obserwator server``
        checks before it starts the server, whose start logs it.

    Returns
    -------
    Instance or None
        The instance the server applies (`served_instance`).

    Raises
    ------
    ObserwatorValidationError
        A provider file of ``nogat.toml`` that cannot be used (its ``details.option``
        ``provider_file.<field>`` and ``details.path``; `check_provider_files`), a
        problem of ``[obserwator.instance]`` (``details.option``
        ``instance.<field>``) or, with the section, a weak write token
        (``details.option`` the variable, ``details.reason`` the problem).
    ObserwatorStoreError
        ``store_unavailable``: ``OBSERWATOR_ROOT`` or ``OBSERWATOR_RAW_ROOT`` holds
        a root of a layout this version does not read.
    """
    check_provider_files()
    instance = served_instance()
    roots: tuple[tuple[RootKind, Path | None], ...] = (
        ("data", settings.root),
        ("raw", settings.raw_root),
    )
    for kind, root in roots:
        # A relative root is refused by every request (503), as without an instance.
        if root is not None and root.is_absolute():
            check_root_layout(root, kind)
    if instance is not None or warn:
        check_credentials("token", strict=instance is not None and instance.declared)
    return instance


def scope_of(spec: DataCommand) -> Scope | None:
    """
    The instance's part in a request of ``spec``; None without an instance.

    Parameters
    ----------
    spec : DataCommand
        The catalog command of the request.

    Returns
    -------
    Scope or None
        What the instance does before, during and after the command.

    Raises
    ------
    ObserwatorError
        ``not_found`` before any request: a route of IMGW-PIB's current data while
        IMGW-PIB is ``off`` (``details.reason`` ``not_served``), a route of PMAXTP with
        ``pmaxtp = "off"`` (``pmaxtp_off``).
    """
    instance = served_instance()
    if instance is None:
        return None
    group = spec.name.split(" ", 1)[0]
    if group == "pmaxtp" and not instance.pmaxtp:
        raise _not_found(message("instance.pmaxtp_off"), "pmaxtp_off")
    if group == "current" and not instance.serves(_GROUP_PROVIDERS[group]):
        raise _not_found(_not_served(_GROUP_PROVIDERS[group]), "not_served")
    return Scope(instance, spec)


class Scope:
    """
    What the instance does to one request of a catalog command (see the module).

    Parameters
    ----------
    instance : Instance
        The instance the server applies.
    spec : DataCommand
        The command of the request.
    """

    def __init__(self, instance: Instance, spec: DataCommand) -> None:
        self.instance = instance
        self.spec = spec
        self._codes: frozenset[str] | None = None

    def version(self, parts: Sequence[str]) -> None:
        """
        Refuse a ``version`` of a provider that is ``off``, by its path alone.

        Parameters
        ----------
        parts : sequence of str
            The segments of the version's path below the root, checked for their
            form (``<tree>/versions/…``) but not for existence: a version that
            exists answers like one that does not.

        Raises
        ------
        ObserwatorError
            ``not_found`` (``details.option`` ``version``, ``reason``
            ``not_served``).
        """
        owner = _version_provider(parts)
        if owner is not None and not self.instance.serves(owner):
            raise _not_found(
                _not_served(owner), "not_served", "version", "/".join(parts)
            )

    def guard(self, options: dict[str, object]) -> None:
        """
        Refuse what the options name and the instance does not serve.

        Called with the options `validate_command` normalized (keys of datasets,
        identifiers of providers), before the command runs or plans, so nothing is
        requested of what is refused. ``stations find`` and ``stations export``
        without ``provider`` get the one provider served.

        Parameters
        ----------
        options : dict of str to object
            The normalized options; changed in place by the narrowing.

        Raises
        ------
        ObserwatorError
            ``not_found`` for a provider, dataset, station or PMAXTP point not
            served (``details.option`` the option, ``details.reason`` ``not_served``
            or ``outside_area``); ``forbidden`` (``instance_clip``) for a command
            whose answer a clipped area cannot reduce exactly, or (``not_served``)
            for ``analyses build`` while the data root holds data of a provider that
            is ``off``.
        ObserwatorValidationError
            Option ``provider``: several providers are served and none is named.
        """
        default = next(
            (o.default for o in self.spec.options if o.name == "provider"), None
        )
        provider = options.get("provider", default)
        if isinstance(provider, str) and not self.instance.serves(provider):
            raise _not_found(_not_served(provider), "not_served", "provider", provider)
        for name in ("dataset", "datasets"):
            for key in _names(options.get(name)):
                self._dataset(get_dataset(key), name)
        if self.spec.name != "current synop":  # a SYNOP index is no station code
            for name in ("station", "stations"):
                for code in _names(options.get(name)):
                    self._station(code, name)
        plan = options.get("plan")
        if isinstance(plan, Path):
            self._plan(StorePlan.from_json(plan))
        rule = _RULES.get(self.spec.name)
        if rule is not None:
            rule(self, options)

    def run(self, options: Mapping[str, object]) -> CommandResult[object]:
        """
        Run the command and keep of its answer what the instance serves.

        Parameters
        ----------
        options : Mapping of str to object
            The guarded options (`guard`); a list's ``limit`` and ``cursor`` page the
            items served.

        Returns
        -------
        CommandResult
            The envelope of `run_command` (``stations export`` with `Instance.keeps`),
            reduced: a list to the items served and their page, with the lines of
            that page; ``store info`` to the providers served; the lines of
            ``stations export`` to those of the catalogs exported.

        Raises
        ------
        ObserwatorError
            As `run_command`; ``not_found`` (``outside_area``) for a PMAXTP cell read
            outside a clipped area.
        """
        name = self.spec.name
        given = dict(options)
        limit = cast("int | None", given.pop("limit", None))
        cursor = cast("str | None", given.pop("cursor", None))
        envelope = run_command(name, options=given, keep=self.instance.keeps)
        if envelope.result is None:
            return envelope
        if self.spec.result == "list":
            return self._page(envelope, given, limit, cursor)
        answer = _ANSWERS.get(name)
        return envelope if answer is None else answer(self, envelope, given)

    def keeps_station(
        self,
        code: str,
        longitude: float | None = None,
        latitude: float | None = None,
        provider: str | None = None,
    ) -> bool:
        """
        Whether a station of an answer is served: its provider, then its place.

        With ``clip`` an item with a location is kept inside the area
        (`Instance.keeps_point`); one without by its code (`serves_station`).
        """
        if provider is not None and not self.instance.serves(provider):
            return False
        if not self.instance.clips:
            return True
        if longitude is not None and latitude is not None:
            return self.instance.keeps_point(longitude, latitude)
        return self.serves_station(code)

    def serves_station(self, code: str) -> bool:
        """
        Whether a station named by its code is served (`Instance.serves_station`).

        With ``clip`` the station is one of `Instance.catalog_codes` of the server's
        data root (none without that root), read once per request: a list asks for
        every item.
        """
        if not self.instance.clips:
            return self.instance.serves_station(code, None)
        if self._codes is None:
            root = _data_root()
            self._codes = (
                frozenset() if root is None else self.instance.catalog_codes(root)
            )
        return code in self._codes

    def serves_dataset(self, descriptor: DatasetDescriptor) -> bool:
        """Whether a dataset is served: its provider is, and PMAXTP's needs ``pmaxtp``."""
        return self.instance.serves(descriptor.provider) and (
            descriptor.time_unit != "cell" or self.instance.pmaxtp
        )

    def clipped(self) -> NoReturn:
        """Refuse the command: its answer would hold stations outside the area."""
        raise ObserwatorError(
            message("instance.clip_refused", command=self.spec.name),
            code="forbidden",
            details={"reason": "instance_clip"},
        )

    def _dataset(self, descriptor: DatasetDescriptor, option: str) -> None:
        if not self.instance.serves(descriptor.provider):
            raise _not_found(
                _not_served(descriptor.provider), "not_served", option, descriptor.key
            )
        if not self.serves_dataset(descriptor):
            raise _not_found(
                message("instance.pmaxtp_off"), "pmaxtp_off", option, descriptor.key
            )

    def _station(self, code: str, option: str) -> None:
        if not self.serves_station(code):
            raise _not_found(
                message("instance.station_not_served", station=code),
                "not_served",
                option,
                code,
            )

    def _plan(self, plan: StorePlan) -> None:
        """A plan of ``store sync``: the dataset and, with ``clip``, the station of each item."""
        for item in plan.items:
            descriptor = get_dataset(item.archive.dataset)
            self._dataset(descriptor, "plan")
            if self.instance.clips and descriptor.archive_scope != "country":
                code = item.station_code or item.archive.station_code
                if code is None:  # a SYNOP archive is named by no station code
                    self.clipped()
                self._station(code, "plan")

    def _page(
        self,
        envelope: CommandResult[object],
        options: Mapping[str, object],
        limit: int | None,
        cursor: str | None,
    ) -> CommandResult[object]:
        """The items served, paged and attributed as `run_command` pages a list."""
        kept = _ITEMS.get(self.spec.name)
        found = tuple(cast("Iterable[object]", envelope.result))
        items = found if kept is None else tuple(i for i in found if kept(self, i))
        start = 0 if cursor is None else cursor_index(cursor)
        end = len(items) if limit is None else min(start + limit, len(items))
        truncated = end < len(items)
        chosen = items[start:end]
        lines = Attribution()
        if self.spec.name in _ATTRIBUTIONS:
            lines = _ATTRIBUTIONS[self.spec.name](dict(options), chosen)
        return replace(
            envelope,
            result=chosen,
            page=Page(len(items), page_cursor(end) if truncated else None, truncated),
            attribution=lines.attribution,
            terms_notice=lines.terms_notice,
        )


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def _not_found(
    detail: str, reason: str, option: str | None = None, value: object = None
) -> ObserwatorError:
    """``not_found`` of something the instance does not serve."""
    details: dict[str, object] = {}
    if option is not None:
        details["option"] = option
    if value is not None:
        details["value"] = value
    details["reason"] = reason
    return ObserwatorError(detail, code="not_found", details=details)


def _not_served(provider: str) -> str:
    return message("instance.not_served", provider=get_provider(provider).short_name)


def _outside(latitude: float, longitude: float, option: str) -> ObserwatorError:
    return _not_found(
        message("instance.outside_area", latitude=latitude, longitude=longitude),
        "outside_area",
        option,
    )


def _names(value: object) -> tuple[str, ...]:
    """The texts of a normalized option: none, one, or a tuple of them."""
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    return tuple(str(item) for item in cast("Iterable[object]", value))


def _data_root() -> Path | None:
    """The server's data root, whose catalogs locate the stations of a clipped area."""
    root = settings.root
    return root if root is not None and root.is_absolute() else None


def _version_provider(parts: Sequence[str]) -> str | None:
    """
    The provider a version's path names; None when the path names none.

    ``series/versions/<slug>/`` names its dataset, ``analyses/versions/<key prefix>/``
    its provider, ``archives/versions/<server path>`` the dataset whose server
    directory it lies in; PMAXTP has its own switch (`scope_of`).
    """
    tree, rest = parts[0], parts[2:]
    try:
        if tree == "series":
            return get_dataset(rest[0]).provider
        if tree == "analyses":
            return get_provider(rest[0]).id
    except ObserwatorValidationError:
        return None
    if tree == "archives":
        path = "/".join(rest)
        owners = {
            item.provider
            for item in datasets()
            if item.server_dir is not None and path.startswith(f"{item.server_dir}/")
        }
        return owners.pop() if len(owners) == 1 else None
    return None


# --------------------------------------------------------------------------
# Rules of single commands
# --------------------------------------------------------------------------


def _narrow(scope: Scope, options: dict[str, object]) -> None:
    """
    Without ``provider`` and with a provider ``off``: the one provider served.

    Only the providers a search without a provider asks count: one off by default
    (ADR-034) is asked only where named, so it narrows nothing.
    """
    instance = scope.instance
    if "provider" in options or instance.complete:
        return
    served = instance.served
    if len(served) == 1:
        options["provider"] = served[0]
        return
    if not served:
        raise _not_found(message("api.no_provider_served"), "not_served", "provider")
    off = [
        get_provider(p).short_name for p in instance.providers if not instance.serves(p)
    ]
    raise ObserwatorValidationError(
        message("instance.provider_needed", option="provider", off=", ".join(off)),
        details={"option": "provider", "allowed": list(served)},
    )


def _unclipped(scope: Scope, options: dict[str, object]) -> None:
    """A command whose answer a clipped area cannot reduce exactly."""
    if scope.instance.clips:
        scope.clipped()


def _selection(scope: Scope, options: dict[str, object]) -> None:
    """Per-station files with ``clip``: only of the stations named (served)."""
    if not scope.instance.clips or "stations" in options or "plan" in options:
        return
    if any(
        get_dataset(key).archive_scope != "country"
        for key in _names(options.get("datasets"))
    ):
        scope.clipped()


def _point(scope: Scope, options: dict[str, object]) -> None:
    """A PMAXTP point outside a clipped area, before any request."""
    latitude = cast(float, options["latitude"])
    longitude = cast(float, options["longitude"])
    if not scope.instance.keeps_point(longitude, latitude):
        raise _outside(latitude, longitude, "latitude")


def _analyses_build(scope: Scope, options: dict[str, object]) -> None:
    """
    ``analyses build`` while the data root holds data of a provider that is ``off``.

    A build (and its plan) names every provider with series to analyse or an
    analyses version, which no option narrows: it is refused then.
    """
    root = cast(Path, options["root"])
    keys = sorted({key for d in analysis_definitions() for key in d.datasets()})
    for owner in providers():
        if scope.instance.serves(owner.id):
            continue
        slots = [f"series:{k}" for k in keys if get_dataset(k).provider == owner.id]
        slots.append(f"analyses:{owner.key_prefix}.analyses")
        if any(current_version(root, slot=slot) is not None for slot in slots):
            raise ObserwatorError(
                message(
                    "api.command_touches_off_provider",
                    command=scope.spec.name,
                    provider=owner.short_name,
                ),
                code="forbidden",
                details={"reason": "not_served"},
            )


def _provider_file(scope: Scope, options: dict[str, object]) -> None:
    """
    ``store import`` of a provider that is ``off``, by the provider its file adds.

    A path that names no provider file is left to the import, which refuses it.
    """
    path = options.get("provider_file")
    found = provider_files().find(path) if isinstance(path, Path) else None
    if found is not None and not scope.instance.serves(found.id):
        raise _not_found(
            _not_served(found.id), "not_served", "provider_file", str(path)
        )


_RULES: dict[str, Callable[[Scope, dict[str, object]], None]] = {
    "stations find": _narrow,
    "stations export": _narrow,
    "current synop": _unclipped,
    "store export": _unclipped,
    "store check": _selection,
    "store sync": _selection,
    "store import": _provider_file,
    "pmaxtp fetch": _point,
    "pmaxtp url": _point,
    "pmaxtp check": _point,
    "pmaxtp sync": _point,
    "analyses build": _analyses_build,
}
"""What a command refuses or narrows beyond the options every command guards."""


def _located(scope: Scope, item: Any) -> bool:
    """A live reading or water state: by the location it carries, else by its code."""
    return scope.keeps_station(item.station_code, item.longitude, item.latitude)


def _found(scope: Scope, item: Any) -> bool:
    """
    A station of ``stations find``: by its provider and its code.

    As every route naming a station (`Scope.serves_station`): with ``clip`` the data
    root's catalogs decide, not the coordinates of a live list.
    """
    return scope.keeps_station(item.station_code, provider=item.provider)


def _scanned(scope: Scope, item: Any) -> bool:
    """
    A version or problem of ``store scan``: by its provider.

    A problem that names no slot (an unknown directory, a stale staging directory)
    names no provider either: kept only while every provider served by default is
    served (`Instance.complete`).
    """
    instance = scope.instance
    if item.provider is None:
        return instance.complete
    return instance.serves(item.provider)


_ITEMS: dict[str, Callable[[Scope, Any], bool]] = {
    "datasets list": lambda scope, item: scope.serves_dataset(item),
    "datasets providers": lambda scope, item: scope.instance.serves(item.id),
    "stations find": _found,
    "current hydro": _located,
    "current meteo": _located,
    "current hydro-states": _located,
    "store scan": _scanned,
    "series summary": lambda scope, item: scope.keeps_station(item.station_code),
}
"""The items a list keeps; the other lists are already narrowed by their options."""


def _store_info(
    scope: Scope, envelope: CommandResult[object], options: Mapping[str, object]
) -> CommandResult[object]:
    info = cast(StoreInfo, envelope.result)
    served = tuple(p for p in info.providers if scope.instance.serves(p.id))
    return replace(envelope, result=replace(info, providers=served))


def _pmaxtp_read(
    scope: Scope, envelope: CommandResult[object], options: Mapping[str, object]
) -> CommandResult[object]:
    cell = cast(PMaXTPResult, envelope.result)
    if not scope.instance.keeps_point(cell.longitude, cell.latitude):
        raise _outside(cell.latitude, cell.longitude, "ind_x")
    return envelope


def _stations_export(
    scope: Scope, envelope: CommandResult[object], options: Mapping[str, object]
) -> CommandResult[object]:
    """The lines of the catalogs exported: those holding a station the instance keeps."""
    lines = Attribution()
    for catalog in _catalogs(
        cast(Path, options["root"]),
        cast("str | None", options.get("provider")),
        cast("str | None", options.get("kind")),
        scope.instance.keeps,
    ):
        lines |= catalog.lines
    return replace(
        envelope, attribution=lines.attribution, terms_notice=lines.terms_notice
    )


_ANSWERS: dict[
    str,
    Callable[
        [Scope, CommandResult[object], Mapping[str, object]], CommandResult[object]
    ],
] = {
    "store info": _store_info,
    "pmaxtp read": _pmaxtp_read,
    "stations export": _stations_export,
}
"""How an answer that is no list is reduced to what the instance serves."""
