"""Hydrolog's catalog commands, run in this process.

The plan (Nogat 2026-11-12-station-data-and-analyses, D6) runs Hydrolog as a program
from Obserwator; the mockup imports Hydrolog's catalog and calls `run_command`, the
function behind every Hydrolog CLI, REST and MCP call, so a number here equals the one
`hydrolog <group> <verb>` gives for the same options.
"""

from __future__ import annotations

from typing import Any

import hydrolog
from hydrolog.catalog.dispatch import run_command

VERSION = str(hydrolog.__version__)

#: Options too long to show in a provenance line.
_BULKY = frozenset({"values", "dates", "water_levels", "discharges", "input_file"})


class HydrologFailed(Exception):
    """A Hydrolog command refused its input or failed: its code and message."""

    def __init__(self, command: str, code: str, text: str) -> None:
        super().__init__(f"{command}: {text}")
        self.command = command
        self.code = code
        self.text = text


def call(command: str, options: dict[str, Any]) -> dict[str, Any]:
    """
    Run one Hydrolog catalog command and return its result and provenance.

    Returns ``{"result": <the command's result>, "notices": [...], "provenance": {...}}``
    where ``provenance`` is ``{"engine": "hydrolog", "version", "command", "options"}``
    with the bulky inputs (values, dates) left out and their count given instead.
    """
    try:
        envelope = run_command(command, options).to_dict()
    except hydrolog.HydrologError as exc:  # every error of Hydrolog's catalog
        code = getattr(exc, "code", type(exc).__name__)
        raise HydrologFailed(command, str(code), str(exc)) from exc
    shown = {key: value for key, value in options.items() if key not in _BULKY}
    for key in ("values", "water_levels"):
        if key in options:
            shown[f"{key}_count"] = len(options[key])
    return {
        "result": envelope["result"],
        "notices": envelope.get("notices", []),
        "provenance": {
            "engine": "hydrolog",
            "version": VERSION,
            "command": command,
            "options": shown,
        },
    }


def prototype(method: str, target: str) -> dict[str, Any]:
    """
    The provenance of a computation Hydrolog does not have yet.

    ``method`` names the method and its source; ``target`` the step of the Nogat plan
    that moves it to Hydrolog (e.g. "H12").
    """
    return {"engine": "prototype", "method": method, "target": target}
