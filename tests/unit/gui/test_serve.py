"""``obserwator gui serve``, `serve`, the settings and the ``nogat.gui`` entry point (D4, D5)."""

from __future__ import annotations

import json
import queue
import signal
import socket
import subprocess
import sys
import threading
import urllib.request
from importlib.metadata import entry_points
from pathlib import Path

import pytest
from starlette.testclient import TestClient
from typer.testing import CliRunner

from obserwator.exceptions import ERROR_CODES, ObserwatorError
from obserwator.gui import create_app, gui_module, serve
from obserwator.gui._config import Basemap, GuiConfig
from obserwator.gui._serving import url_of
from obserwator.messages import message

DEADLINE_S = 60.0
"""The longest wait for a server to start or to stop [s]."""


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def answer_of(url):
    with urllib.request.urlopen(url, timeout=10) as answer:
        return answer.status, json.loads(answer.read())


@pytest.fixture
def settings(tmp_path, monkeypatch):
    """``nogat.toml`` with ``data_dir`` in the test's directory; no basemap, no Hydrolog."""
    data_dir = tmp_path / "data"
    toml = tmp_path / "nogat.toml"
    toml.write_text(f"[nogat]\ndata_dir = {json.dumps(str(data_dir))}\n", "utf-8")
    monkeypatch.setenv("NOGAT_CONFIG", str(toml))
    monkeypatch.setenv("OBSERWATOR_GUI_BASEMAP_URL", "")
    for name in (
        "OBSERWATOR_ROOT",
        "OBSERWATOR_DATA_DIR",
        "NOGAT_DATA_DIR",
        "OBSERWATOR_HYDROLOG_COMMAND",
        "OBSERWATOR_REQUEST_LIMIT",
    ):
        monkeypatch.delenv(name, raising=False)
    return data_dir


# --- the command and the server ----------------------------------------------------------------


def test_gui_serve_answers_until_sigterm_and_ends_with_exit_code_0(
    fixture_root, settings
):
    program = Path(sys.executable).with_name("obserwator")
    port = free_port()
    url = f"http://127.0.0.1:{port}/"
    process = subprocess.Popen(
        [program, "gui", "serve", "--no-browser", "--port", str(port)]
        + ["--root", str(fixture_root)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    lines: queue.Queue[str] = queue.Queue()
    threading.Thread(
        target=lambda: [lines.put(line) for line in process.stderr], daemon=True
    ).start()
    try:
        announced = lines.get(timeout=DEADLINE_S)
        status, session = answer_of(url + "api/session")
        process.send_signal(signal.SIGTERM)
        code = process.wait(timeout=DEADLINE_S)
    finally:
        if process.poll() is None:  # pragma: no cover - only when the test fails
            process.kill()
            process.wait()

    assert announced.strip() == message("gui.server.listening", url=url)
    assert status == 200
    assert set(session["root"]["catalogs"]) == {"IMGW-PIB", "CHMI"}
    assert code == 0


def test_a_port_in_use_is_a_conflict(fixture_root, settings):
    with socket.socket() as taken:
        taken.bind(("127.0.0.1", 0))
        taken.listen()
        port = taken.getsockname()[1]

        with pytest.raises(ObserwatorError) as raised:
            serve(port=port, root=fixture_root, open_browser=False)
        from obserwator.cli.main import app

        result = CliRunner().invoke(
            app,
            ["gui", "serve", "--no-browser", "--port", str(port)]
            + ["--root", str(fixture_root)],
        )

    assert raised.value.code == "conflict"
    assert raised.value.details == {
        "reason": "port_in_use",
        "host": "127.0.0.1",
        "port": port,
    }
    assert result.exit_code == ERROR_CODES["conflict"].exit_code


def test_an_address_that_cannot_be_resolved_is_refused(fixture_root, settings):
    with pytest.raises(ObserwatorError) as raised:
        serve(host="bad host!", port=0, root=fixture_root, open_browser=False)

    assert raised.value.code == "validation_error"
    assert raised.value.details["option"] == "host"


def test_the_address_of_an_ipv6_host_is_in_brackets():
    assert url_of("::1", 8060) == "http://[::1]:8060/"
    assert url_of("127.0.0.1", 8060) == "http://127.0.0.1:8060/"


# --- the settings ---------------------------------------------------------------------------------


def test_the_settings_come_from_the_environment_and_nogat_toml(
    fixture_root, settings, tmp_path, monkeypatch
):
    toml = tmp_path / "nogat.toml"
    toml.write_text(
        "\n".join(
            [
                "[nogat]",
                f"data_dir = {json.dumps(str(tmp_path / 'data'))}",
                "[nogat.gui]",
                'obserwator = "https://obserwator.example/"',
                "[nogat.operator]",
                'name = "Operator testowy"',
                'email = "operator@example.org"',
                "terms_effective = 2026-11-13",
                'processor = "Example Processor"',
                'processor_transfer = ""',
                "",
            ]
        ),
        "utf-8",
    )
    monkeypatch.setenv("NOGAT_CONFIG", str(toml))
    monkeypatch.setenv("OBSERWATOR_GUI_BASEMAP_URL", "https://tiles.example/planet")
    monkeypatch.setenv("OBSERWATOR_GUI_BASEMAP_ATTRIBUTION", "© Example")
    monkeypatch.setenv(
        "OBSERWATOR_HYDROLOG_COMMAND", "'/opt/hydro log/bin/hydrolog' --quiet"
    )
    monkeypatch.setenv("OBSERWATOR_REQUEST_LIMIT", "5")

    config = GuiConfig.resolve(root=fixture_root)

    assert config.root == fixture_root
    assert config.state_dir == tmp_path / "data" / "obserwator"
    assert config.writes_state is True
    assert config.basemap == Basemap(
        "https://tiles.example/planet", "https://tiles.example", "© Example"
    )
    assert config.hydrolog_command == ("/opt/hydro log/bin/hydrolog", "--quiet")
    assert config.request_limit == 5
    assert config.gui == {"obserwator": "https://obserwator.example/"}
    assert config.operator is not None
    assert config.operator["email"] == "operator@example.org"


def test_the_default_root_is_the_guis_own_directory_so_it_writes_nothing(settings):
    config = GuiConfig.resolve()

    assert config.root == config.state_dir == settings / "obserwator"
    assert config.writes_state is False
    assert config.basemap is None
    assert config.hydrolog_command is None


@pytest.mark.parametrize("value", ["", "none", "OFF"])
def test_an_empty_basemap_address_is_the_offline_map(settings, monkeypatch, value):
    monkeypatch.setenv("OBSERWATOR_GUI_BASEMAP_URL", value)

    assert GuiConfig.resolve().basemap is None


@pytest.mark.parametrize("value", ["ftp://tiles.example/planet", "tiles.example"])
def test_a_basemap_address_that_is_no_web_address_is_refused(
    settings, monkeypatch, value
):
    monkeypatch.setenv("OBSERWATOR_GUI_BASEMAP_URL", value)

    with pytest.raises(ObserwatorError) as raised:
        create_app()

    assert raised.value.code == "validation_error"
    assert raised.value.details == {"option": "gui_basemap_url", "value": value}


def test_without_the_gui_extra_the_app_names_what_to_install(monkeypatch):
    from obserwator.gui import _extra

    real = _extra.importlib.import_module

    def without_uvicorn(name, *args):
        if name == "uvicorn":
            raise ImportError(name)
        return real(name, *args)

    monkeypatch.setattr(_extra.importlib, "import_module", without_uvicorn)

    with pytest.raises(ObserwatorError) as raised:
        create_app()

    assert raised.value.code == "missing_dependency"
    assert raised.value.hint == 'pip install "obserwator[gui]"'


# --- the module of Nogat's GUI platform ------------------------------------------------------------


def test_the_nogat_gui_entry_point_loads_the_module(fixture_root, settings):
    (entry,) = [
        entry for entry in entry_points(group="nogat.gui") if entry.name == "obserwator"
    ]

    module = entry.load()()

    assert module == gui_module()
    assert (module.name, module.title) == ("obserwator", "Obserwator")
    assert (module.web / module.index).is_file()
    assert [section for section, _ in module.sections] == [
        "stations",
        "current",
        "pmaxtp",
    ]
    with TestClient(module.app(root=fixture_root)) as client:
        assert client.get("/").status_code == 200
        assert client.get("/api/session").json()["root"]["error"] is None
