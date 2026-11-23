"""
A provider fed by files (ADR-033) through Python, the CLI, REST, MCP and the GUI.

The registry reads the provider files of ``nogat.toml`` once, as it is imported, so
every step here runs in a process of its own (test_interface_contract.py runs every
other route in this one). ``NOGAT_CONFIG`` names a copy of ``tests/fixtures/files``
whose station series SIEC-02 is a Parquet file, with a missing day; no ``OBSERWATOR_*``
or ``NOGAT_*`` variable reaches the processes but the temporary state directory of the
session (tests/conftest.py). The servers listen on the loopback, the only address this
test connects to.
"""

from __future__ import annotations

import json
import os
import re
import secrets
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from tests.contract.support import (
    SERVER_FLAGS,
    STOP_SIGNAL,
    canonical,
    envelope_errors,
    in_json,
    load,
    mcp_text,
    obserwator_executable,
    schema_errors,
    snapshot,
)

FILES = Path(__file__).parents[1] / "fixtures" / "files"
PROVIDER_FILE = "siec.toml"
HYDRO, METEO = "pl.siec.hydro_daily", "pl.siec.meteo_daily"
CODES = ["SIEC-01", "SIEC-02", "SIEC-03", "SIEC-M1", "SIEC-X1"]
LINE = (
    "Źródło danych: Sieć Testowa Operatora sp. z o.o., licencja CC BY 4.0 "
    "(https://creativecommons.org/licenses/by/4.0/)"
)
DEADLINE_S = 60.0
"""The longest wait for a server to start or to stop [s]."""
TOKEN = secrets.token_hex(32)
"""A write token strong enough for the REST server's check."""
# The day of a version label (``2026-11-23_6ac7729a``): the day of the run.
DAY = re.compile(r"\d{4}-\d{2}-\d{2}_")
CHECKED_AT = re.compile(r'"checked_at":"[^"]*"')
DEAD_PROXY = "http://127.0.0.1:9"
# Python: the envelope of check_command or run_command as the CLI prints it.
PYTHON = """\
import json, sys
from obserwator import check_command, run_command
check, options = json.loads(sys.argv[1]), json.loads(sys.argv[2])
answer = (check_command if check else run_command)("store import", options=options)
print(json.dumps(answer.to_json(root=options["root"])))
"""
# The line of each provider file as the kit's strip declares it.
SCREEN_LINES = """\
import json
from obserwator.datasets import provider_files
print(json.dumps([item.screen_line() for item in provider_files().files]))
"""
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))
INTERFACES = ("python", "cli", "rest", "mcp")


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Only the loopback: the servers under test run in processes of their own."""
    connect = socket.socket.connect

    def loopback(sock, address, *args, **kwargs):
        if sock.family == socket.AF_INET and address[0] != "127.0.0.1":
            raise AssertionError("połączenie sieciowe w teście kontraktu offline")
        if sock.family == socket.AF_INET6:
            raise AssertionError("połączenie sieciowe w teście kontraktu offline")
        return connect(sock, address, *args, **kwargs)

    monkeypatch.setattr(socket.socket, "connect", loopback)


@dataclass(frozen=True)
class Deployment:
    """A copy of ``tests/fixtures/files`` (``config``) and the roots of its imports."""

    base: Path
    config: Path
    data: Path
    raw: Path

    def environment(self, **variables: str) -> dict[str, str]:
        """The process environment: none of the developer's settings, dead proxies."""
        kept = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith(("OBSERWATOR_", "NOGAT_"))
        }
        return {
            **kept,
            "HTTP_PROXY": DEAD_PROXY,
            "HTTPS_PROXY": DEAD_PROXY,
            "ALL_PROXY": DEAD_PROXY,
            "NO_PROXY": "",
            "OBSERWATOR_STATE_DIR": os.environ["OBSERWATOR_STATE_DIR"],
            "NOGAT_CONFIG": str(self.config / "nogat.toml"),
            **variables,
        }

    def run(
        self, *args: object, code: int = 0, program: list[str] | None = None
    ) -> subprocess.CompletedProcess[str]:
        """``obserwator`` (or ``program``) with ``args`` in a process of its own."""
        result = subprocess.run(
            [*(program or obserwator_executable()), *(str(arg) for arg in args)],
            capture_output=True,
            encoding="utf-8",
            env=self.environment(),
            cwd=self.base,
            timeout=120,
            check=False,
        )
        assert result.returncode == code, result.stderr
        return result

    def answer(self, *args: object) -> dict[str, Any]:
        """The ``obserwator-result/1`` envelope ``--json`` prints."""
        return parsed(self.run(*args, "--json").stdout)

    def refusal(self, *args: object) -> dict[str, Any]:
        """The ``obserwator-error/1`` line of a validation error (exit code 2)."""
        result = self.run(*args, "--json", code=2)
        assert result.stdout == ""
        line = parsed(result.stderr.splitlines()[-1])
        assert schema_errors(line, "obserwator-error/1") == []
        return line

    def import_words(self, provider_file: str = PROVIDER_FILE) -> list[object]:
        """The words of ``store import`` of ``provider_file`` into both roots."""
        roots = ["--root", self.data, "--raw-root", self.raw]
        return ["store", "import", "--provider-file", provider_file, *roots]

    def store_import(self, *args: object) -> dict[str, Any]:
        return self.answer(*self.import_words(), *args)

    def read(self, code: str) -> dict[str, Any]:
        """``series read`` of the station ``code`` of the hydrological series."""
        where = ["--dataset", HYDRO, "--root", self.data]
        return self.answer("series", "read", "--station", code, *where)

    def fresh(self) -> None:
        """Empty roots at the same paths, as the REST server needs them."""
        shutil.rmtree(self.data, ignore_errors=True)
        shutil.rmtree(self.raw, ignore_errors=True)
        self.answer("store", "init", "--root", self.raw)
        self.answer("store", "init", "--root", self.data, "--kind", "data")

    def edit(self, name: str, old: str, new: str) -> None:
        """Replace ``old`` with ``new`` in a file of the copy."""
        path = self.config / name
        text = path.read_text(encoding="utf-8")
        assert old in text
        path.write_text(text.replace(old, new), encoding="utf-8")

    def rest_variables(self) -> dict[str, str]:
        return {
            "OBSERWATOR_ROOT": str(self.data),
            "OBSERWATOR_RAW_ROOT": str(self.raw),
            "OBSERWATOR_STORE_WRITES_ENABLED": "true",
            "OBSERWATOR_STORE_WRITE_TOKEN": TOKEN,
        }


@pytest.fixture
def deployment(tmp_path) -> Deployment:
    """The fixture deployment with SIEC-02 as Parquet: a float H with a null."""
    import pyarrow
    import pyarrow.parquet

    config = tmp_path / "config"
    shutil.copytree(FILES, config)
    hydro = config / "siec" / "hydro"
    days = [date(2026, 10, day) for day in (28, 29, 30, 31)]
    table = pyarrow.table(
        {
            "date": pyarrow.array(days, pyarrow.date32()),
            "H [cm]": pyarrow.array([95.0, 97.0, None, 101.0], pyarrow.float64()),
        }
    )
    pyarrow.parquet.write_table(table, hydro / "SIEC-02.parquet")
    (hydro / "SIEC-02.csv").unlink()
    return Deployment(tmp_path, config, tmp_path / "data", tmp_path / "raw")


@pytest.fixture
def imported(deployment: Deployment) -> Deployment:
    """The deployment after one ``store import`` by the CLI."""
    deployment.store_import()
    return deployment


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@contextmanager
def serving(deployment: Deployment, *args: str, **variables: str) -> Iterator[str]:
    """A server ``obserwator <args> --port P`` until the block ends: its address."""
    port = free_port()
    log = deployment.base / f"server-{port}.log"
    with log.open("w", encoding="utf-8") as errors:
        process = subprocess.Popen(
            [*obserwator_executable(), *args, "--port", str(port)],
            stdout=subprocess.DEVNULL,
            stderr=errors,
            env=deployment.environment(**variables),
            cwd=deployment.base,
            creationflags=SERVER_FLAGS,
        )
    try:
        deadline = time.monotonic() + DEADLINE_S
        while True:
            try:
                socket.create_connection(("127.0.0.1", port), timeout=1).close()
                break
            except OSError:
                assert process.poll() is None, log.read_text(encoding="utf-8")
                assert time.monotonic() < deadline, log.read_text(encoding="utf-8")
                time.sleep(0.05)
        yield f"http://127.0.0.1:{port}"
    finally:
        process.send_signal(STOP_SIGNAL)  # SIGTERM; Ctrl+Break on Windows
        try:
            process.wait(timeout=DEADLINE_S)
        except subprocess.TimeoutExpired:  # pragma: no cover - only when the test fails
            process.kill()
            process.wait()


def rest_server(deployment: Deployment):
    return serving(
        deployment, "server", "--host", "127.0.0.1", **deployment.rest_variables()
    )


def gui_server(deployment: Deployment):
    return serving(
        deployment, "gui", "serve", "--no-browser", "--root", str(deployment.data)
    )


def parsed(text: str | bytes) -> dict[str, Any]:
    """A JSON object."""
    document = json.loads(text)
    assert isinstance(document, dict), document
    return document


def http(
    url: str,
    path: str,
    query: dict[str, str] | None = None,
    body: object = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, dict[str, Any]]:
    """Status and JSON body of a GET, or of a POST of ``body``."""
    address = url + path + ("?" + urllib.parse.urlencode(query) if query else "")
    request = urllib.request.Request(
        address,
        data=None if body is None else json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", **(headers or {})},
        method="GET" if body is None else "POST",
    )
    try:
        with OPENER.open(request, timeout=DEADLINE_S) as answer:
            return answer.status, parsed(answer.read())
    except urllib.error.HTTPError as error:
        with error:
            return error.code, parsed(error.read())


# --- (a) store import alike in every interface --------------------------------------


Call = Callable[[bool], Awaitable[dict[str, Any]]]


@asynccontextmanager
async def interface(name: str, deployment: Deployment) -> AsyncIterator[Call]:
    """``store import`` of ``siec.toml`` by one interface: check or write, its envelope."""
    roots = {"root": str(deployment.data), "raw_root": str(deployment.raw)}
    options = {**roots, "provider_file": PROVIDER_FILE}
    if name == "python":

        async def call(check: bool) -> dict[str, Any]:
            printed = deployment.run(
                "-c",
                PYTHON,
                json.dumps(check),
                json.dumps(options),
                program=[sys.executable],
            )
            return parsed(printed.stdout)

        yield call
    elif name == "cli":

        async def call(check: bool) -> dict[str, Any]:
            return deployment.store_import(*(["--check"] if check else []))

        yield call
    elif name == "rest":
        with rest_server(deployment) as url:

            async def call(check: bool) -> dict[str, Any]:
                status, body = http(
                    url,
                    "/api/v1/store/import",
                    {"check": "true"} if check else None,
                    {"provider_file": PROVIDER_FILE},
                    {"X-API-Key": TOKEN},
                )
                assert status == 200, body
                return body

            yield call
    else:
        pytest.importorskip("mcp")
        from mcp import Client
        from mcp.client.stdio import StdioServerParameters, stdio_client

        command, *prefix = obserwator_executable()
        server = StdioServerParameters(
            command=command,
            args=[
                *prefix,
                "mcp",
                "--allow-writes",
                "--allow-dir",
                str(deployment.base),
            ],
            env=deployment.environment(),
            cwd=deployment.base,
        )
        with (deployment.base / "mcp.log").open("w+", encoding="utf-8") as log:
            async with Client(stdio_client(server, errlog=log)) as client:

                async def call(check: bool) -> dict[str, Any]:
                    answered = await client.call_tool(
                        "obserwator_store_import", {**options, "check": check}
                    )
                    assert answered.is_error is False, mcp_text(answered)
                    assert isinstance(answered.structured_content, dict)
                    return answered.structured_content

                yield call


def normalized(document: dict[str, Any], deployment: Deployment) -> dict[str, Any]:
    """
    The envelope without what differs by interface or by run.

    Python, the CLI and MCP name the raw root's files by absolute paths and the data
    root by its path, REST by relative paths and ``"."`` (it hides its directories); a
    version label begins with the day of the run, a plan has the time of its check.
    """
    text = canonical(document)
    for root in (deployment.raw, deployment.data):
        text = text.replace(in_json(f"{root}{os.sep}"), "")
    text = text.replace(f'"{in_json(str(deployment.data))}"', '"."')
    text = CHECKED_AT.sub('"checked_at":null', text)
    return parsed(DAY.sub("DAY_", text))


def statuses(value: object) -> set[str]:
    """Every ``status`` in a JSON document."""
    if isinstance(value, dict):
        found = {value["status"]} if isinstance(value.get("status"), str) else set()
        return found.union(*(statuses(item) for item in value.values()))
    if isinstance(value, list):
        return set().union(*(statuses(item) for item in value))
    return set()


def tree(deployment: Deployment) -> dict[str, list[str]]:
    """The paths of both roots, the day of each version label replaced."""
    return {
        name: sorted(DAY.sub("DAY_", path) for path in snapshot(root))
        for name, root in (("raw", deployment.raw), ("data", deployment.data))
    }


@pytest.mark.slow
async def test_store_import_answers_alike_in_python_the_cli_rest_and_mcp(
    deployment: Deployment,
) -> None:
    answers: dict[str, list[dict[str, Any]]] = {}
    trees: dict[str, dict[str, list[str]]] = {}
    for name in INTERFACES:
        deployment.fresh()
        async with interface(name, deployment) as call:
            planned = await call(True)
            assert snapshot(deployment.raw).keys() == {"obserwator-store.json"}
            written = await call(False)
            before = {
                root: snapshot(root) for root in (deployment.raw, deployment.data)
            }
            again = await call(False)
            after = {root: snapshot(root) for root in (deployment.raw, deployment.data)}
        assert after == before, name  # a re-run rewrites nothing
        documents = [planned, written, again]
        assert [envelope_errors(document) for document in documents] == [[], [], []]
        answers[name] = [normalized(document, deployment) for document in documents]
        trees[name] = tree(deployment)

    python = answers.pop("python")
    assert answers == dict.fromkeys(answers, python)
    assert trees == dict.fromkeys(trees, trees["python"])
    planned, written, again = python
    assert statuses(planned["result"]["actions"]) == {"missing"}
    assert written["status"] == again["status"] == "ok"
    assert statuses(written["result"]) == {"new"}
    assert statuses(again["result"]) == {"unchanged"}
    assert written["result"]["provider"] == "SIEC"
    assert [item["slot"] for item in written["result"]["items"]] == [
        "archive:pl.siec.station_list:stations.geojson",
        "archive:pl.siec.hydro_daily:SIEC-01.csv",
        "archive:pl.siec.hydro_daily:SIEC-02.parquet",
        "archive:pl.siec.meteo_daily:SIEC-M1.csv",
    ]
    assert LINE in written["attribution"]


# --- (b) an unlisted provider file ---------------------------------------------------


def test_an_unlisted_provider_file_is_refused_and_nothing_is_written(
    deployment: Deployment,
) -> None:
    unlisted = deployment.config / "inna.toml"
    shutil.copy(deployment.config / PROVIDER_FILE, unlisted)

    error = deployment.refusal(*deployment.import_words("inna.toml"))

    assert error["code"] == "validation_error"
    assert error["details"] == {
        "option": "provider_file",
        "value": str(unlisted),
        "reason": "not_listed",
    }
    assert not deployment.data.exists()
    assert not deployment.raw.exists()


# --- (c) the reads of the imported provider and its documents -----------------------


def test_the_imported_provider_is_read_back_and_its_documents_meet_the_contracts(
    imported: Deployment,
) -> None:
    siec = ["stations", "find", "--provider", "SIEC"]
    store = imported.answer(*siec, "--source", "store", "--root", imported.data)
    live = imported.answer(*siec, "--source", "live")
    reads = {code: imported.read(code) for code in ("SIEC-01", "SIEC-02")}
    scan = imported.answer("store", "scan", "--root", imported.data)
    config = parsed(imported.run("config", "show", "--json").stdout)

    for found in (store, live):
        assert envelope_errors(found) == []
        assert sorted(row["station_code"] for row in found["result"]) == CODES
        assert {row["provider"] for row in found["result"]} == {"SIEC"}
        assert LINE in found["attribution"]
    # The catalog rejected the point outside the country; the live list keeps it.
    located = {
        found: {row["station_code"]: row["latitude"] for row in answer["result"]}
        for found, answer in (("store", store), ("live", live))
    }
    assert located["store"]["SIEC-X1"] is None
    assert located["live"]["SIEC-X1"] == 50.0
    assert located["store"]["SIEC-01"] == located["live"]["SIEC-01"] == 51.1177

    def h(answer: dict[str, Any]) -> list[tuple[str, object, str]]:
        return [
            (
                row["date"],
                row["measurements"]["H"]["value"],
                row["measurements"]["H"]["flag"],
            )
            for row in answer["result"]
        ]

    for answer in reads.values():
        assert envelope_errors(answer) == []
        assert answer["attribution"][0] == LINE
    assert h(reads["SIEC-01"]) == [  # the CSV
        ("2026-10-28", 212.0, "value"),
        ("2026-10-29", 215.0, "value"),
        ("2026-10-30", None, "missing"),
        ("2026-10-31", 220.0, "value"),
        ("2026-11-01", 224.0, "value"),
        ("2026-11-02", 226.0, "value"),
    ]
    assert h(reads["SIEC-02"]) == [  # the Parquet, its null a missing day
        ("2026-10-28", 95.0, "value"),
        ("2026-10-29", 97.0, "value"),
        ("2026-10-30", None, "missing"),
        ("2026-10-31", 101.0, "value"),
    ]

    assert envelope_errors(scan) == []
    assert [(entry["slot"], entry["provider"]) for entry in scan["result"]] == [
        ("series:pl.siec.hydro_daily", "SIEC"),
        ("series:pl.siec.meteo_daily", "SIEC"),
        ("catalog:pl.siec.stations", "SIEC"),
    ]
    assert config["provider_files"] == [
        {"path": str(imported.config / PROVIDER_FILE), "provider": "SIEC"}
    ]
    assert config["problems"] == []

    # The station codes of a provider fed by files meet the contract schemas.
    contracts = {
        "series.json": "obserwator-series/1",
        "stations.geojson": "stations.geojson",
    }
    sidecars = sorted(imported.raw.rglob("*.meta.json")) + sorted(
        imported.data.rglob("*.meta.json")
    )
    assert len(sidecars) == 4 + 3  # 4 files as they came; 2 series and the catalog
    mains = 0
    for sidecar in sidecars:
        assert schema_errors(load(sidecar), "obserwator-meta/1") == [], sidecar
        main = sidecar.with_name(sidecar.name.removesuffix(".meta.json"))
        if imported.data in main.parents and main.name in contracts:
            assert schema_errors(load(main), contracts[main.name]) == [], main
            mains += 1
    assert mains == 3


# --- (d) the GUI ---------------------------------------------------------------------


def test_the_gui_names_the_provider_its_datasets_its_line_and_its_stations(
    imported: Deployment,
) -> None:
    screen_lines = json.loads(
        imported.run("-c", SCREEN_LINES, program=[sys.executable]).stdout
    )

    with gui_server(imported) as url:
        session = http(url, "/api/session")
        stations = http(url, "/api/stations")

    assert session[0] == stations[0] == 200
    document = session[1]
    provider = document["providers"]["SIEC"]
    assert {
        key: provider[key] for key in ("key_prefix", "origin", "border", "source_class")
    } == {
        "key_prefix": "pl.siec",
        "origin": "siec",
        "border": "gugik",
        "source_class": "other",
    }
    assert provider["attribution"][0] == LINE
    siec = {key: value for key, value in document["datasets"].items() if "siec" in key}
    assert list(siec) == [HYDRO, METEO]
    assert {(value["provider"], value["tier"]) for value in siec.values()} == {
        ("SIEC", "operational")
    }
    assert document["attribution"]["screen_lines"] == screen_lines
    assert screen_lines[0]["text"] == LINE
    rows = [row for row in stations[1]["stations"] if row["provider"] == "SIEC"]
    assert sorted(row["code"] for row in rows) == CODES


# --- (e) the provider off on an instance -------------------------------------------


def test_a_provider_off_is_gone_from_the_gui_and_rest(imported: Deployment) -> None:
    with (imported.config / "nogat.toml").open("a", encoding="utf-8") as toml:
        toml.write('\n[obserwator.instance.providers]\nSIEC = "off"\n')

    with gui_server(imported) as url:
        session = http(url, "/api/session")[1]
        stations = http(url, "/api/stations")[1]
    with rest_server(imported) as url:
        providers = http(url, "/api/v1/datasets/providers")
        datasets = http(url, "/api/v1/datasets/list")
        found = http(url, "/api/v1/stations/find", {"provider": "SIEC"})
        written = http(
            url,
            "/api/v1/store/import",
            body={"provider_file": PROVIDER_FILE},
            headers={"X-API-Key": TOKEN},
        )

    assert "SIEC" not in session["providers"]
    assert not [key for key in session["datasets"] if key.startswith("pl.siec.")]
    assert session["attribution"]["screen_lines"] == []
    assert [row for row in stations["stations"] if row["provider"] == "SIEC"] == []
    assert providers[0] == datasets[0] == 200
    assert "SIEC" not in {provider["id"] for provider in providers[1]["result"]}
    assert not [
        item for item in datasets[1]["result"] if item["key"].startswith("pl.siec.")
    ]
    for status, body in (found, written):
        assert status == 404
        assert schema_errors(body, "problem+json") == []
        assert (body["code"], body["details"]["reason"]) == ("not_found", "not_served")


# --- (f) a private provider ----------------------------------------------------------


def test_a_private_provider_is_left_out_of_the_gui_and_rest(
    deployment: Deployment,
) -> None:
    deployment.edit(PROVIDER_FILE, 'publication = "public"', 'publication = "private"')
    deployment.fresh()
    report = deployment.store_import()["result"]
    (version,) = [
        series["version"]
        for series in report["series"]
        if "siec_hydro_daily" in series["version"]
    ]
    # The command line reads what no server serves.
    assert deployment.read("SIEC-01")["status"] == "ok"

    with gui_server(deployment) as url:
        session = http(url, "/api/session")[1]
    with rest_server(deployment) as url:
        reads = [
            http(url, "/api/v1/series/read", {"dataset": HYDRO, "station": "SIEC-01"}),
            http(
                url, "/api/v1/series/read", {"version": version, "station": "SIEC-01"}
            ),
        ]

    assert version.startswith("series/versions/siec_hydro_daily/")
    assert not [key for key in session["datasets"] if key.startswith("pl.siec.")]
    for status, body in reads:
        assert status == 404
        assert schema_errors(body, "problem+json") == []
        assert (body["code"], body["details"]["reason"]) == ("not_found", "private")


# --- (g) a provider file that cannot be used -----------------------------------------


def test_an_unusable_provider_file_refuses_the_import_and_both_servers(
    deployment: Deployment,
) -> None:
    deployment.edit(PROVIDER_FILE, 'id = "SIEC"', 'id = "siec"')
    provider_file = str(deployment.config / PROVIDER_FILE)

    error = deployment.refusal(*deployment.import_words())
    gui = ["gui", "serve", "--no-browser", "--root", deployment.base]
    servers = [
        deployment.run("server", "--host", "127.0.0.1", "--port", free_port(), code=2),
        deployment.run(*gui, "--port", free_port(), code=2),
    ]

    assert error["code"] == "validation_error"
    assert error["details"] == {"option": "provider_file.id", "path": provider_file}
    assert not deployment.data.exists()
    assert not deployment.raw.exists()
    for started in servers:
        assert started.stdout == ""
        line = parsed(started.stderr.splitlines()[-1])
        assert schema_errors(line, "obserwator-error/1") == []
        assert line["code"] == "validation_error"
        assert line["details"] == {"option": "provider_file.id", "path": provider_file}
