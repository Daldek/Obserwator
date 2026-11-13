"""
Obserwator's web GUI (ADR-013): stations on a map, their data and analyses, PMAXTP.

Every station of the current catalogs is a point on one map; a click opens the station
in the right panel, with a view for a hydrological and another for a meteorological
station: its description, current IMGW-PIB measurements, its series as a chart and a
table, the analyses Hydrolog computed and the data root stores (a person's choices
computed by Hydrolog on request), and downloads. It reads Obserwator's data root and
never writes it; live data (current measurements, PMAXTP) pass through the server only.

* `serve` -- the standalone server (``obserwator gui serve``, ``127.0.0.1:8060`` by
  default); it blocks until Ctrl+C or ``SIGTERM``.
* `create_app` -- the ASGI app; a host mounts it at a prefix of its origin.
* `gui_module` -- the description of the module that Nogat's GUI platform finds through
  the entry point group ``nogat.gui`` (stage 2, B6).

Importing this package imports neither Starlette nor uvicorn: `create_app` and `serve`
raise ``missing_dependency`` without the ``gui`` extra (``pip install "obserwator[gui]"``).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

from obserwator.gui._extra import require_gui_extra
from obserwator.messages import message

if TYPE_CHECKING:
    from starlette.applications import Starlette

__all__ = ["SECTIONS", "WEB_DIR", "GuiModule", "create_app", "gui_module", "serve"]

WEB_DIR: Final = Path(__file__).resolve().parent / "web"
"""The page's directory (package data ``gui/web/**``)."""
SECTIONS: Final[tuple[tuple[str, str], ...]] = (
    ("stations", str(message("gui.shell.view_stations", lang="pl"))),
    ("current", str(message("gui.shell.view_current", lang="pl"))),
    ("pmaxtp", "PMAXTP"),
)
"""The views of the page: their id (the map bar's value) and their Polish title."""


@dataclass(frozen=True)
class GuiModule:
    """
    A GUI module as Nogat's GUI platform hosts it (the fields of Hydrolog's).

    Attributes
    ----------
    name : str
        Id of the module (``"obserwator"``).
    title : str
        Title shown by the host.
    web : Path
        Directory of the page's static files.
    index : str
        The page, relative to ``web``.
    sections : tuple of (str, str)
        The views: the word of the address and the Polish title.
    app : callable
        `create_app`: ``app(root=...)`` returns the ASGI app that serves ``web`` and
        answers ``api/...`` relative to the page, at any prefix.
    """

    name: str
    title: str
    web: Path
    index: str
    sections: tuple[tuple[str, str], ...]
    app: Callable[..., Starlette]


def create_app(*, root: Path | None = None) -> Starlette:
    """
    Create the ASGI app of the GUI: the page and its private API (GUI plan D4 to D8).

    Parameters
    ----------
    root : Path or None, optional
        Obserwator's data root, read only; None takes the CLI's root
        (``OBSERWATOR_ROOT``, ``[obserwator] root``, else ``<data_dir>/obserwator``).

    Returns
    -------
    starlette.applications.Starlette
        The app: the page at its root, the API under ``api/``.

    Raises
    ------
    ObserwatorError
        ``missing_dependency`` without the ``gui`` extra; ``validation_error`` for an
        unusable setting (the basemap's address).
    """
    require_gui_extra()
    from obserwator.gui._app import build_app
    from obserwator.gui._config import GuiConfig

    return build_app(GuiConfig.resolve(root=root))


def serve(
    *,
    host: str = "127.0.0.1",
    port: int = 8060,
    root: Path | None = None,
    open_browser: bool = True,
) -> dict[str, Any]:
    """
    Serve the GUI until Ctrl+C or ``SIGTERM``.

    It has no sign-in: anyone who reaches the address uses it, so a public instance
    follows Nogat's public-GUI rules (rate limit, logs without addresses, daily
    statistics, „Zgłoś uwagę”, the regulamin of ``[nogat.operator]``).

    Parameters
    ----------
    host : str, optional
        Address to listen on (``127.0.0.1``: this computer only).
    port : int, optional
        TCP port (``0`` takes a free one; the line on standard error names it).
    root : Path or None, optional
        The data root (`create_app`).
    open_browser : bool, optional
        Open the page in the default browser once the server listens.

    Returns
    -------
    dict
        ``url`` (the page), ``started_at`` and ``stopped_at`` (UTC, ISO 8601).

    Raises
    ------
    ObserwatorError
        ``missing_dependency`` without the ``gui`` extra, ``conflict`` when the port is
        in use, ``validation_error`` when the host cannot be resolved.
    """
    require_gui_extra()
    from obserwator.gui._serving import run

    return run(create_app(root=root), host=host, port=port, open_browser=open_browser)


def gui_module() -> GuiModule:
    """
    Describe the GUI for Nogat's GUI platform (entry point ``nogat.gui``).

    Returns
    -------
    GuiModule
        ``name="obserwator"``, ``title="Obserwator"``, the page's directory and
        ``index.html``, its three views and `create_app`.
    """
    return GuiModule(
        name="obserwator",
        title="Obserwator",
        web=WEB_DIR,
        index="index.html",
        sections=SECTIONS,
        app=create_app,
    )
