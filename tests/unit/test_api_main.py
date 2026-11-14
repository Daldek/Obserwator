"""Application-level behavior of the FastAPI app: system routes, middleware, server."""

import http.client
import json
import runpy
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest
import uvicorn
from fastapi.testclient import TestClient

import obserwator
from obserwator import agent_guide
from obserwator.api.main import app, run_server
from obserwator.config import settings
from tests.contract.nogat import validate

DEADLINE_S = 60.0
"""The longest wait for the server to start or to stop [s]."""


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def uvicorn_calls(monkeypatch):
    calls = []
    monkeypatch.setattr(
        uvicorn, "run", lambda *args, **kwargs: calls.append((args, kwargs))
    )
    return calls


def test_api_main_health_reports_package_version(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": obserwator.__version__}


def test_api_main_info_names_the_api_and_links_the_catalog_schema(client):
    response = client.get("/api/v1")
    assert response.status_code == 200
    body = response.json()
    assert (body["name"], body["version"]) == ("Obserwator API", obserwator.__version__)
    schema = client.get(body["schema"])
    assert schema.json()["result"]["schema"] == "obserwator-commands/1"
    openapi = client.get("/openapi.json").json()
    assert openapi["info"]["version"] == obserwator.__version__


@pytest.mark.parametrize(
    ("header", "lang"),
    [(None, "en"), ("en-GB,en;q=0.9", "en"), ("de, en;q=0.5, pl", "pl")],
)
def test_api_main_llms_txt_is_the_llms_guide_in_the_accepted_language(
    client, header, lang
):
    headers = {} if header is None else {"Accept-Language": header}
    response = client.get("/llms.txt", headers=headers)
    assert response.status_code == 200
    assert response.headers["content-type"] == "text/markdown; charset=utf-8"
    assert response.text == "".join(agent_guide(format="llms", lang=lang))
    assert response.headers["content-language"] == lang
    assert "accept-language" in response.headers["vary"].lower()
    assert "content-disposition" not in response.headers


def test_api_main_cors_preflight_allows_any_origin(client):
    response = client.options(
        "/api/v1/stations/find",
        headers={
            "Origin": "https://raba.example",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "X-API-Key",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://raba.example"
    assert response.headers["access-control-allow-credentials"] == "true"
    assert "x-api-key" in response.headers["access-control-allow-headers"].lower()


def test_api_main_cors_simple_request_echoes_origin(client):
    response = client.get("/health", headers={"Origin": "https://raba.example"})
    assert response.headers["access-control-allow-origin"] == "https://raba.example"
    assert "access-control-allow-origin" not in client.get("/health").headers


def test_api_main_gzip_applies_only_above_threshold(client):
    large = client.get("/openapi.json", headers={"Accept-Encoding": "gzip"})
    small = client.get("/health", headers={"Accept-Encoding": "gzip"})
    assert large.headers["content-encoding"] == "gzip"
    assert "content-encoding" not in small.headers


def test_api_main_root_redirects_to_the_documentation(client):
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"] == "/docs"


@pytest.mark.parametrize("env,reload", [("development", True), ("production", False)])
def test_api_main_run_server_uses_settings(monkeypatch, uvicorn_calls, env, reload):
    monkeypatch.setattr(settings, "env", env)
    monkeypatch.setattr(settings, "host", "127.0.0.5")
    monkeypatch.setattr(settings, "port", 8123)
    run_server()
    ((args, kwargs),) = uvicorn_calls
    assert args == ("obserwator.api.main:app",)
    assert (kwargs["host"], kwargs["port"], kwargs["reload"]) == (
        "127.0.0.5",
        8123,
        reload,
    )


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _answer(
    port: int, path: str, user_agent: str | None = None
) -> tuple[int, dict[str, str]]:
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    try:
        connection.request("GET", path, headers={"User-Agent": user_agent or ""})
        response = connection.getresponse()
        response.read()
        return response.status, {name.lower(): v for name, v in response.getheaders()}
    finally:
        connection.close()


def test_obserwator_server_logs_requests_and_prints_only_its_lifecycle(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("OBSERWATOR_STATE_DIR", str(tmp_path / "state"))
    (tmp_path / "nogat.toml").write_text("", encoding="utf-8")
    monkeypatch.setenv("NOGAT_CONFIG", str(tmp_path / "nogat.toml"))
    port = _free_port()
    process = subprocess.Popen(
        [Path(sys.executable).with_name("obserwator"), "server"]
        + ["--host", "127.0.0.1", "--port", str(port)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        start = json.loads(process.stderr.readline())
        deadline = time.monotonic() + DEADLINE_S
        while True:  # the record comes from the lifespan, just before uvicorn listens
            try:
                health = _answer(port, "/health")
                break
            except ConnectionRefusedError:
                if time.monotonic() > deadline:  # pragma: no cover - a failing test
                    raise
                time.sleep(0.05)
        redirect = _answer(port, "/", "Mozilla/5.0 (X11; Linux x86_64) Firefox/140.0")
        missing = _answer(port, "/nothing?q=Krak%C3%B3w&limit=5", "curl/8.5.0")
        process.send_signal(signal.SIGTERM)
        stdout, stderr = process.communicate(timeout=DEADLINE_S)
    finally:
        if process.poll() is None:  # pragma: no cover - only when the test fails
            process.kill()
            process.wait()
    printed = [start] + [json.loads(line) for line in stderr.splitlines()]

    assert [health[0], redirect[0], missing[0]] == [200, 307, 404]
    assert all("x-request-id" not in headers for _, headers in (health, redirect))
    # Standard output and error: the lifecycle records only (Nogat DEV-12.7).
    assert stdout == ""
    assert [(r["kind"], r["event"]) for r in printed] == [
        ("lifecycle", "start"),
        ("lifecycle", "stop"),
    ]
    assert (start["settings"]["host"], start["settings"]["port"]) == ("127.0.0.1", port)
    # The files: <state_dir>/obserwator/logs/<kind>-YYYY-MM-DD.jsonl (DEV-12.6).
    logs = tmp_path / "state" / "obserwator" / "logs"
    written = {
        path.name.split("-")[0]: [json.loads(x) for x in path.read_text().splitlines()]
        for path in logs.iterdir()
    }
    assert sorted(written) == ["access", "lifecycle"]
    assert written["lifecycle"] == printed
    # /health is the same for every client (DEV-12.5); the search text is dropped.
    assert [(r["path"], r["status"], r["agent"]) for r in written["access"]] == [
        ("/", 307, "browser"),
        ("/nothing?q=&limit=5", 404, "script"),
    ]
    for record in written["access"] + written["lifecycle"]:
        validate(record, "record-1")


def test_api_main_module_entrypoint_starts_server(monkeypatch, uvicorn_calls):
    monkeypatch.setattr(settings, "env", "production")
    monkeypatch.delitem(sys.modules, "obserwator.api.main")
    runpy.run_module("obserwator.api.main", run_name="__main__")
    assert [args for args, _ in uvicorn_calls] == [("obserwator.api.main:app",)]
