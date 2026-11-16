"""
``obserwator gui serve``: the web GUI on this computer until it is stopped (ADR-013).

A command outside the catalog, beside ``obserwator server`` and ``obserwator mcp``: a
server inside a tool is no MCP tool and no REST route (GUI plan D4).
"""

from pathlib import Path

import typer

from obserwator.cli._dispatch import (
    _HELP,
    _LANG,
    ObserwatorCommand,
    ObserwatorSubgroup,
    _error_line,
)
from obserwator.exceptions import ObserwatorError
from obserwator.messages import message

app = typer.Typer(help=message("cli.gui_help", lang=_LANG), cls=ObserwatorSubgroup)


@app.command(
    "serve", cls=ObserwatorCommand, help=message("cli.gui_serve_help", lang=_LANG)
)
def serve(
    host: str = typer.Option(
        "127.0.0.1",
        metavar=message("cli.metavar_address", lang=_LANG),
        help=message("cli.gui_host_help", lang=_LANG),
    ),
    port: int = typer.Option(
        8060,
        metavar=_HELP.metavars["int"],
        help=message("cli.gui_port_help", lang=_LANG),
    ),
    root: Path | None = typer.Option(
        None,
        help=message("cli.gui_root_help", lang=_LANG),
    ),
    no_browser: bool = typer.Option(
        False,
        "--no-browser",
        help=message("cli.gui_no_browser_help", lang=_LANG),
    ),
) -> None:
    """Serve the web GUI until Ctrl+C or SIGTERM; the address goes to standard error."""
    from obserwator.gui import serve as run

    try:
        run(host=host, port=port, root=root, open_browser=not no_browser)
    except ObserwatorError as exc:
        raise typer.Exit(
            _error_line(exc.code, exc.detail, exc.details, hint=exc.hint)
        ) from None
