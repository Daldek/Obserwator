"""The settings of one GUI app, resolved once when the app is created (ADR-013)."""

from __future__ import annotations

import shlex
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from obserwator import _environment as environment
from obserwator.config import Settings, store_root
from obserwator.exceptions import ObserwatorValidationError
from obserwator.messages import message

NO_BASEMAP = frozenset({"", "none", "off"})
"""Values of ``gui_basemap_url`` that mean no basemap: the packaged borders only."""


@dataclass(frozen=True)
class Basemap:
    """
    The map's background: a TileJSON drawn by the GUI's own style.

    Attributes
    ----------
    url : str
        Address of the TileJSON (``https://tiles.openfreemap.org/planet``).
    origin : str
        Its origin, the only remote one the page may reach (CSP ``img-src``,
        ``connect-src``): the tiles and glyphs must come from it too.
    attribution : str
        The credit line shown on the map.
    """

    url: str
    origin: str
    attribution: str


@dataclass(frozen=True)
class GuiConfig:
    """
    What one GUI app serves and where it keeps its own files.

    Attributes
    ----------
    root : Path
        Obserwator's data root, read only.
    state_dir : Path
        ``<data_dir>/obserwator``: the GUI's statistics (``stats.jsonl``), reports
        of „Zgłoś uwagę” (``feedback.jsonl``) and access logs (``logs/``),
        Nogat DEV-15.10 to DEV-15.12; never under ``root``.
    basemap : Basemap or None
        The basemap, or None for the offline map (the borders only).
    request_limit, request_window : int
        At most ``request_limit`` counted requests of one client address in
        ``request_window`` seconds (Nogat DEV-15.9).
    hydrolog_command : tuple of str or None
        Hydrolog's program and its leading arguments; None when unset.
    gui : Mapping of str to str
        The deployment's ``[nogat.gui]`` table (DEV-15.4).
    operator : Mapping of str to str or None
        The deployment's ``[nogat.operator]`` table when it is usable: the GUI is
        public and serves ``regulamin.html`` (DEV-15.7); None otherwise.
    operator_problems : tuple of str
        The keys of a ``[nogat.operator]`` table that keep it from being used.
    """

    root: Path
    state_dir: Path
    basemap: Basemap | None
    request_limit: int
    request_window: int
    hydrolog_command: tuple[str, ...] | None
    gui: Mapping[str, str]
    operator: Mapping[str, str] | None
    operator_problems: tuple[str, ...]

    @classmethod
    def resolve(cls, *, root: Path | None = None) -> GuiConfig:
        """
        Read the settings now (DEV-18.1): options, environment, ``nogat.toml``.

        Parameters
        ----------
        root : Path or None, optional
            The data root; None takes the CLI's root (``OBSERWATOR_ROOT``,
            ``[obserwator] root``, else ``<data_dir>/obserwator``).

        Returns
        -------
        GuiConfig
            The resolved settings.
        """
        settings = Settings()
        chosen = (root if root is not None else store_root().root).expanduser()
        url = (settings.gui_basemap_url or "").strip()
        basemap = None
        if url.lower() not in NO_BASEMAP:
            parts = urlsplit(url)
            if parts.scheme not in ("http", "https") or not parts.netloc:
                raise ObserwatorValidationError(
                    message("gui.server.bad_basemap_url", url=url),
                    details={"option": "gui_basemap_url", "value": url},
                )
            basemap = Basemap(
                url,
                f"{parts.scheme}://{parts.netloc}",
                settings.gui_basemap_attribution.strip(),
            )
        command = (settings.hydrolog_command or "").strip()
        operator = environment.operator()
        return cls(
            root=chosen.absolute(),
            state_dir=(settings.data_dir / environment.TOOL).expanduser().absolute(),
            basemap=basemap,
            request_limit=settings.request_limit,
            request_window=settings.request_window,
            hydrolog_command=tuple(shlex.split(command)) if command else None,
            gui=environment.gui_addresses(),
            operator=dict(operator.values) if operator.usable else None,
            operator_problems=operator.problems,
        )
