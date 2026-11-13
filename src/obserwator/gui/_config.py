"""The settings of one GUI app, resolved once when the app is created (ADR-013)."""

from __future__ import annotations

import os
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
BASEMAP_ENV = f"{environment.PREFIX}GUI_BASEMAP_URL"
"""The variable of the basemap's address; set and empty, it means no basemap (the
settings ignore an empty variable, which would bring the default basemap back)."""


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
        Nogat DEV-15.10 to DEV-15.12; never under ``root`` (`writes_state`).
    basemap : Basemap or None
        The basemap, or None for the offline map (the borders only).
    request_limit, request_window : int
        At most ``request_limit`` counted requests of one client address in
        ``request_window`` seconds (Nogat DEV-15.9).
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
    gui: Mapping[str, str]
    operator: Mapping[str, str] | None
    operator_problems: tuple[str, ...]

    @property
    def writes_state(self) -> bool:
        """
        Whether the GUI may write its own files: ``state_dir`` and ``root`` are apart.

        ``<data_dir>/obserwator`` is both the GUI's directory and the default data root
        (ADR-017; the default raw root, ``<data_dir>/obserwator-raw``, lies beside it and
        the GUI never reads it), and the server never writes under the root it serves
        (GUI plan D7): when one of the two directories is the other or holds it, the GUI
        writes none of its files.
        """
        return not _overlap(self.state_dir, self.root)

    @classmethod
    def resolve(cls, *, root: Path | None = None) -> GuiConfig:
        """
        Read the settings now (DEV-18.1): options, environment, ``nogat.toml``.

        Parameters
        ----------
        root : Path or None, optional
            The data root; None takes the default data root of the CLI
            (`store_root`: ``OBSERWATOR_ROOT``, ``[obserwator] root``, else
            ``<data_dir>/obserwator``; ADR-017).

        Returns
        -------
        GuiConfig
            The resolved settings.
        """
        settings = Settings()
        chosen = (
            root if root is not None else store_root(kind="data").root
        ).expanduser()
        given = os.environ.get(BASEMAP_ENV)
        url = (settings.gui_basemap_url if given is None else given).strip()
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
        operator = environment.operator()
        return cls(
            root=chosen.absolute(),
            state_dir=(settings.data_dir / environment.TOOL).expanduser().absolute(),
            basemap=basemap,
            request_limit=settings.request_limit,
            request_window=settings.request_window,
            gui=environment.gui_addresses(),
            operator=dict(operator.values) if operator.usable else None,
            operator_problems=operator.problems,
        )


def _overlap(first: Path, second: Path) -> bool:
    """Whether two directories are one or one holds the other, also through symbolic links."""
    return any(
        one == other or one in other.parents or other in one.parents
        for one, other in ((first, second), (first.resolve(), second.resolve()))
    )
