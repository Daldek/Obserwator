"""Contract of the MCP adapter: tools answer like Python and ``obserwator`` (spec 2026-10-19 §6, §9).

Every contract case of ``test_interface_contract.CASES`` (the commands with a REST
route) runs through the tool of a stdio server in the SDK's in-memory client, with
the root of the command's kind and, for a build, ``raw_root`` (ADR-017): the
structured content is the Python envelope ``to_json(root)``, the text content the
line the CLI prints, a stream the text Python yields with an envelope of
``{schema: obserwator-stream/1, format, bytes, lines}``. Writes run on a server
with writes and ``check: false`` and leave the trees the CLI leaves; a server
without writes answers the plan of
``--check`` and leaves the roots as they were. The local commands without a REST
route follow the same rule, and every error the CLI reports, a root of the other
kind too, is the CLI error line with the registry title.
"""

import json
import shutil
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("mcp")

import anyio
from mcp import Client
from mcp.types import CallToolResult

from obserwator import (
    ERROR_CODES,
    ErrorCode,
    check_command,
    run_command,
)
from obserwator.mcp._tools import Mode
from obserwator.mcp.server import create_server
from tests.contract.support import (
    ANYWHERE,
    H2024,
    NEW,
    V3,
    FakeImgw,
    canonical,
    cli_words,
    envelope_errors,
    input_schema,
    mcp_text,
    schema_errors,
    snapshot,
)
from tests.contract.test_interface_contract import (
    CASES,
    POST_COMMANDS,
    ROUTES,
    SCENARIOS,
    WRITTEN,
    WRONG_ROOTS,
    Roots,
    Scenario,
    Setting,
    fresh_roots,
    recorded,  # noqa: F401 (fixture)
    relative_reference_dir,  # noqa: F401 (fixture)
    resolved,
    rooted,
    stamps_of,
    trees,
    written,
)

# Default page of a list tool (spec 2026-10-19 §6.4 p. 5).
PAGE = 50


def arguments(options: dict[str, object]) -> dict[str, object]:
    """Options in their JSON form: paths as text."""
    return {
        name: str(value) if isinstance(value, Path) else value
        for name, value in options.items()
    }


def call(command: str, options: dict[str, object], *, mode: Mode) -> CallToolResult:
    """The tool of ``command`` on a fresh stdio server in mode ``mode``."""
    name = input_schema(command)["x-obserwator"]["operation_id"]

    async def answer() -> CallToolResult:
        async with Client(create_server(mode=mode, allow_dirs=ANYWHERE)) as client:
            return await client.call_tool(name, arguments(options))

    return anyio.run(answer)


def writing(command: str) -> bool:
    return bool(input_schema(command)["x-obserwator"]["writes"] != "none")


def run(command: str, options: dict[str, object]) -> CallToolResult:
    """Run the command: a writing one on a server with writes and ``check: false``."""
    if writing(command):
        return call(command, {**options, "check": False}, mode="write")
    return call(command, options, mode="read")


def assert_envelope(answered: CallToolResult, python, printed, root) -> None:
    """MCP structured content = Python envelope; MCP text = the CLI stdout line."""
    document = answered.structured_content
    assert answered.is_error is False, mcp_text(answered)
    assert envelope_errors(document) == []
    assert canonical(document) == canonical(python.to_json(root=root))
    assert mcp_text(answered) + "\n" == printed.stdout


def assert_stream(
    answered: CallToolResult, command: str, options, python, root
) -> None:
    """MCP text = the lines Python yields; the envelope sums them up."""
    data = "".join(python.result)
    default = input_schema(command)["properties"]["format"]["default"]
    assert answered.is_error is False, mcp_text(answered)
    assert mcp_text(answered) == data
    assert answered.structured_content == {
        **replace(python, result=None).to_json(root=root),
        "result": {
            "schema": "obserwator-stream/1",
            "format": options.get("format", default),
            "bytes": len(data.encode("utf-8")),
            "lines": data.count("\n"),
        },
    }


# --------------------------------------------------------------------------
# Every command with a REST route: MCP = Python = CLI
# --------------------------------------------------------------------------


@pytest.mark.parametrize("command", list(ROUTES))
def test_every_rest_command_answers_alike_in_mcp_python_and_cli(
    command,
    cli,
    tmp_path,
    fixture_root,
    fixture_raw_root,
    served_root,
    served_raw_root,
    recorded,  # noqa: F811
    frozen,
    relative_reference_dir,  # noqa: F811
):
    served = Roots(served_root, served_raw_root)
    fixture = Roots(fixture_root, fixture_raw_root)
    for case in CASES[command]:
        writes = case.store in WRITTEN
        if writes:
            roots = written(tmp_path)
        else:
            roots = served if case.store == "served" else None
        root = None if roots is None else roots.root(command)
        raw_root = None if roots is None else roots.raw_root(command)
        options = case.options if writes else resolved(case.options, root)
        given = rooted(options, root, raw_root)
        local = dict(given)
        if ROUTES[command]["result"] == "list" and "limit" not in options:
            local["limit"] = PAGE  # the page MCP takes without limit
        before = stamps_of(served)
        answers, requests, written_trees = {}, {}, {}
        for interface in ("python", "cli", "mcp"):
            if writes:
                fresh_roots(case.store, roots, fixture)
            start = len(recorded.router.calls)
            if interface == "python":
                answers[interface] = run_command(command, options=local)
            elif interface == "cli":
                answers[interface] = cli(*cli_words(command, local))
            else:
                answers[interface] = run(command, given)
            requests[interface] = recorded.traffic(start)
            if writes:
                written_trees[interface] = trees(roots)

        python, printed, answered = answers["python"], answers["cli"], answers["mcp"]
        if ROUTES[command]["result"] == "stream":
            assert_stream(answered, command, options, python, root)
        else:
            assert_envelope(answered, python, printed, root)
        assert requests["mcp"] == requests["python"] == requests["cli"]
        if writes:
            assert (
                written_trees["mcp"] == written_trees["python"] == written_trees["cli"]
            )
        assert stamps_of(served) == before


@pytest.mark.parametrize("command", POST_COMMANDS)
def test_without_writes_a_write_is_its_plan_of_check_in_python_and_cli(
    command,
    cli,
    tmp_path,
    fixture_root,
    fixture_raw_root,
    recorded,  # noqa: F811
    frozen,
):
    (case,) = CASES[command]
    roots = written(tmp_path)
    fresh_roots(case.store, roots, Roots(fixture_root, fixture_raw_root))
    start = len(recorded.router.calls)  # after the sync of a "sources" raw root
    root = roots.root(command)
    given = rooted(case.options, root, roots.raw_root(command))
    before = stamps_of(roots)

    python = check_command(command, options=given)
    printed = cli(*cli_words(command, given), "--check")
    answered = call(command, given, mode="read")

    assert answered.structured_content["check"] is True
    assert_envelope(answered, python, printed, root)
    assert stamps_of(roots) == before
    assert recorded.downloads(start) == []


# --------------------------------------------------------------------------
# Local commands without a REST route
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Local:
    """A local command, its options, the directory it works in and its reset."""

    command: str
    options: dict[str, object]
    tree: Path
    reset: Callable[[], None]


def _gone(path: Path) -> Callable[[], None]:
    def reset() -> None:
        shutil.rmtree(path, ignore_errors=True)

    return reset


def _store_init(tmp_path: Path, imgw: FakeImgw) -> Local:
    target = tmp_path / "nowy"
    return Local("store init", {"root": target}, target, _gone(target))


def _store_init_data(tmp_path: Path, imgw: FakeImgw) -> Local:
    target = tmp_path / "nowe-dane"
    options = {"root": target, "kind": "data"}
    return Local("store init", options, target, _gone(target))


def _datasets_download(tmp_path: Path, imgw: FakeImgw) -> Local:
    imgw.publish(H2024, V3, NEW)
    output = tmp_path / "pobrane"
    options = {"dataset": "hydro/dobowe", "years": [2024], "output_dir": output}
    return Local("datasets download", options, output, _gone(output))


LOCAL = {
    "store init": _store_init,
    "store init --kind data": _store_init_data,
    "datasets download": _datasets_download,
}


@pytest.mark.parametrize("call_id", list(LOCAL))
def test_every_local_command_answers_alike_in_mcp_python_and_cli(
    call_id, cli, tmp_path, imgw, frozen
):
    local = LOCAL[call_id](tmp_path, imgw)
    command = local.command
    local.reset()
    before = snapshot(local.tree)
    root = local.options.get("root")
    answers, local_trees = {}, {}
    for interface in ("python", "cli", "mcp"):
        local.reset()
        if interface == "python":
            answers[interface] = run_command(command, options=local.options)
        elif interface == "cli":
            answers[interface] = cli(*cli_words(command, arguments(local.options)))
        else:
            answers[interface] = run(command, local.options)
        local_trees[interface] = snapshot(local.tree)

    assert_envelope(answers["mcp"], answers["python"], answers["cli"], root)
    assert local_trees["mcp"] == local_trees["python"] == local_trees["cli"]
    assert (local_trees["mcp"] == before) is not writing(command)


# --------------------------------------------------------------------------
# Error codes: the CLI error line with the registry title
# --------------------------------------------------------------------------


# The CLI reports every code with an exit code (the others are REST's own), except
# `forbidden`: no CLI command refuses a write, so there is no scenario that makes the CLI
# and MCP answer alike; the MCP refusal is checked in tests/unit/test_mcp_calls.py.
@pytest.mark.parametrize(
    "code",
    [
        code
        for code, spec in ERROR_CODES.items()
        if spec.exit_code is not None and code != "forbidden"
    ],
)
def test_every_error_of_the_cli_is_the_same_document_in_mcp(
    code, cli, tmp_path, fixture_root, fixture_raw_root, imgw, monkeypatch
):
    fixture = Roots(fixture_root, fixture_raw_root)
    scenario = SCENARIOS[code](Setting(tmp_path, fixture, imgw, monkeypatch))

    assert_same_error(code, scenario, cli)


@pytest.mark.parametrize("wrong", list(WRONG_ROOTS))
def test_a_root_of_the_other_kind_is_the_same_error_in_mcp(
    wrong, cli, tmp_path, fixture_root, fixture_raw_root, imgw, monkeypatch
):
    prepare, kind = WRONG_ROOTS[wrong]
    fixture = Roots(fixture_root, fixture_raw_root)
    scenario = prepare(Setting(tmp_path, fixture, imgw, monkeypatch))

    document = assert_same_error("store_unavailable", scenario, cli)

    assert document["details"] == {"reason": "wrong_root", "kind": kind}


def assert_same_error(code: ErrorCode, scenario: Scenario, cli) -> dict[str, Any]:
    """The CLI error line of ``scenario`` is the error document of its MCP tool."""
    options = scenario.given()

    printed = cli(*cli_words(scenario.command, options))
    answered = run(scenario.command, options)

    document: dict[str, Any] = answered.structured_content or {}
    if code == "cancelled":  # an envelope without a report, as on CLI stdout
        assert answered.is_error is False
        assert document["status"] == "cancelled"
        assert mcp_text(answered) + "\n" == printed.stdout
        return document
    line = json.loads(printed.stderr.splitlines()[-1])
    assert answered.is_error is True
    assert mcp_text(answered) == json.dumps(
        document, ensure_ascii=False, separators=(",", ":")
    )
    assert document["code"] == code
    assert document["title"] == ERROR_CODES[code].title
    assert schema_errors(document, "obserwator-error/1") == []
    assert canonical(document) == canonical(line)
    return document
