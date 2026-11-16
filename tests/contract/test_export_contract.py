"""Contract of the binary export (ADR-014): Parquet is one file in Python, CLI, MCP and REST.

Python, ``obserwator`` and the stdio MCP server write the same bytes with ``output``,
REST answers them as an attachment; without ``output`` the call is the same
``validation_error`` in every interface, MCP over HTTP included.
"""

import importlib.util
import json
from typing import Any, Literal

import anyio
import pytest

from obserwator import ObserwatorValidationError, run_command
from tests.contract.support import ANYWHERE

MCP = importlib.util.find_spec("mcp") is not None
METEO, STATION = "cz.chmi.meteo_daily", "0-203-0-90001"
REFUSAL = {"option": "output", "reason": "output_required"}


def options(root, **extra) -> dict[str, Any]:
    return {
        "root": str(root),
        "dataset": METEO,
        "station": STATION,
        "format": "parquet",
        **extra,
    }


def mcp_call(
    arguments: dict[str, Any], *, mode: Literal["read", "write", "http"] = "write"
) -> Any:
    """``obserwator_series_export`` of a fresh MCP server (stdio modes or ``http``)."""
    if mode == "http":
        from obserwator.mcp._calls import call_tool
        from obserwator.mcp._tools import catalog_tools

        tool = catalog_tools(mode="http")["obserwator_series_export"]

        async def report(*_: object) -> None:
            return None

        return anyio.run(lambda: call_tool(tool, arguments, report=report))
    from mcp import Client

    from obserwator.mcp.server import create_server

    async def ask() -> Any:
        async with Client(create_server(mode=mode, allow_dirs=ANYWHERE)) as client:
            return await client.call_tool("obserwator_series_export", arguments)

    return anyio.run(ask)


def test_parquet_is_one_file_in_python_cli_mcp_and_a_rest_attachment(
    fixture_root, tmp_path, cli, rest, server, monkeypatch
):
    python = run_command(
        "series export", options=options(fixture_root, output=tmp_path / "p")
    )
    data = (tmp_path / "p").read_bytes()
    printed = cli(
        "series",
        "export",
        *[
            word
            for name, value in options(fixture_root, output=tmp_path / "c").items()
            for word in (f"--{name}", str(value))
        ],
        "--json",
    )
    monkeypatch.setattr(server, "root", fixture_root)
    answered = rest.get(
        "/api/v1/series/export",
        params={"dataset": METEO, "station": STATION, "format": "parquet"},
    )

    assert printed.exit_code == 0, printed.output
    assert (tmp_path / "c").read_bytes() == data
    if MCP:
        result = mcp_call(
            {**options(fixture_root, output=str(tmp_path / "m")), "check": False}
        )
        assert result.is_error is False, result.content[0].text
        assert (tmp_path / "m").read_bytes() == data
    assert answered.status_code == 200, answered.text
    assert answered.content == data
    assert answered.headers["content-type"] == "application/vnd.apache.parquet"
    assert answered.headers["content-disposition"] == (
        f'attachment; filename="{STATION}.parquet"'
    )
    assert answered.headers["x-obserwator-status"] == python.status == "ok"
    assert json.loads(answered.headers["x-obserwator-attribution"]) == list(
        python.attribution
    )
    assert not list(tmp_path.glob("**/.obserwator-incoming"))


def test_parquet_without_output_is_one_validation_error_everywhere(fixture_root, cli):
    with pytest.raises(ObserwatorValidationError) as python:
        run_command("series export", options=options(fixture_root))
    printed = cli(
        "series",
        "export",
        *[
            word
            for name, value in options(fixture_root).items()
            for word in (f"--{name}", value)
        ],
        "--json",
    )

    assert python.value.details == REFUSAL
    line = json.loads(printed.stderr.splitlines()[-1])
    assert (printed.exit_code, line["code"], line["details"]) == (
        2,
        "validation_error",
        REFUSAL,
    )
    if MCP:
        for mode, given in (
            ("read", options(fixture_root)),
            ("http", options(fixture_root)),
        ):
            if mode == "http":
                del given["root"]  # the server's root over HTTP
            result = mcp_call(given, mode=mode)
            assert result.is_error is True
            document = result.structured_content
            assert (document["code"], document["details"]) == (
                "validation_error",
                REFUSAL,
            )
