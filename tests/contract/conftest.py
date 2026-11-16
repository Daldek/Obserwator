"""Fixtures of the offline contract suite: no network, frozen clock, recorded IMGW.

The three interfaces run in this process: Python through ``run_command``, the
``obserwator`` CLI through Click's runner and REST through the FastAPI test client.
Hydrolog's program is the recorded fake of ``tests/fixtures/hydrolog``.
"""

import importlib
import shutil
import socket
import threading
from collections.abc import Callable
from datetime import UTC, datetime

import pytest
import respx
from fastapi.testclient import TestClient
from pydantic import SecretStr
from typer.testing import CliRunner, Result

from obserwator.api.main import app as rest_app
from obserwator.cli.main import app as cli_app
from obserwator.config import settings
from obserwator.store import open_store, sync_pmaxtp
from obserwator.testing import FixtureRoots
from tests.contract.support import FakeImgw, build_served_analyses, use_fake_hydrolog

FROZEN_AT = datetime(2026, 10, 20, 9, 0, tzinfo=UTC)
WRITE_TOKEN = "kontrakt-token"
# Modules that stamp versions and plans with the current time.
_CLOCKED = (
    "obserwator.store.writer",
    "obserwator.store.series",
    "obserwator.store.catalog",
    "obserwator.store.sync",
    "obserwator.store.pmaxtp",
    "obserwator.store.analyses",
    "obserwator.commands",
)


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """
    Any real connection fails the test; recorded answers come through respx.

    ``socket.socketpair`` stays local by construction: where the system has none
    (Windows), Python connects a socket to its own listener on the loopback, as
    for the self-pipe of every asyncio event loop. Only that connection passes.
    """
    connect = socket.socket.connect
    socketpair = socket.socketpair
    pairing = threading.local()

    def refuse(*args, **kwargs):
        raise AssertionError("połączenie sieciowe w teście kontraktu offline")

    def connect_in_pair(sock, *args, **kwargs):
        if not getattr(pairing, "active", False):
            refuse()
        return connect(sock, *args, **kwargs)

    def pair(*args, **kwargs):
        pairing.active = True
        try:
            return socketpair(*args, **kwargs)
        finally:
            pairing.active = False

    monkeypatch.setattr(socket.socket, "connect", connect_in_pair)
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket, "socketpair", pair)


@pytest.fixture(autouse=True)
def no_obserwator_root(monkeypatch):
    """The developer's OBSERWATOR_ROOT must not reach the commands under test."""
    monkeypatch.delenv("OBSERWATOR_ROOT", raising=False)
    monkeypatch.delenv("OBSERWATOR_RAW_ROOT", raising=False)


@pytest.fixture(autouse=True)
def hydrolog(monkeypatch, tmp_path_factory):
    """
    Hydrolog's program is the recorded fake, for this process and the processes it starts.

    Its series files go to one directory per test, so the stored lines, which
    echo their paths, are the same in Python, the CLI, REST and MCP.
    """
    use_fake_hydrolog(monkeypatch, tmp_path_factory.mktemp("hydrolog") / "scratch")


@pytest.fixture
def frozen(monkeypatch):
    """Freeze the clock of every module that stamps versions and plans."""

    class Frozen(datetime):
        @classmethod
        def now(cls, tz=None):
            return FROZEN_AT.astimezone(tz)

    for name in _CLOCKED:
        monkeypatch.setattr(importlib.import_module(name), "datetime", Frozen)
    return FROZEN_AT


@pytest.fixture
def imgw():
    """Recorded IMGW server; unpublished URLs are refused by respx."""
    with respx.mock(assert_all_called=False) as router:
        yield FakeImgw(router)


@pytest.fixture(scope="session")
def served_roots(tmp_path_factory, fixture_roots):
    """
    Read-only roots of the read commands: copies of the fixture roots with a
    PMAXTP cell in the raw root and the analyses in the data root.
    """
    base = tmp_path_factory.mktemp("served")
    raw, data = base / "raw", base / "data"
    shutil.copytree(fixture_roots.raw.root, raw)
    shutil.copytree(fixture_roots.data.root, data)
    with respx.mock(assert_all_called=False) as router:
        FakeImgw(router).publish_pmaxtp("pmaxtp_pot_first")
        sync_pmaxtp(raw, latitude=52.23, longitude=21.01)
    build_served_analyses(data)
    return FixtureRoots(open_store(raw, kind="raw"), open_store(data, kind="data"))


@pytest.fixture(scope="session")
def served_root(served_roots):
    """The served data root (series, catalogs, analyses): a ``Path``."""
    return served_roots.data.root


@pytest.fixture(scope="session")
def served_raw_root(served_roots):
    """The served raw root (archives, station sources, a PMAXTP cell): a ``Path``."""
    return served_roots.raw.root


@pytest.fixture
def server(monkeypatch):
    """REST server settings: no roots, writes disabled, default page size."""
    for name, value in (
        ("root", None),
        ("raw_root", None),
        ("store_writes_enabled", False),
        ("store_write_token", None),
        ("user_locations_dir", None),
        ("api_max_limit", 1000),
    ):
        monkeypatch.setattr(settings, name, value)
    return settings


@pytest.fixture
def served(server, monkeypatch, served_root, served_raw_root):
    """REST server serving the served roots (``OBSERWATOR_ROOT``, ``OBSERWATOR_RAW_ROOT``)."""
    monkeypatch.setattr(server, "root", served_root)
    monkeypatch.setattr(server, "raw_root", served_raw_root)
    return server


@pytest.fixture
def writable(server, monkeypatch):
    """Store writes enabled on the server; the headers carry the write token."""
    monkeypatch.setattr(server, "store_writes_enabled", True)
    monkeypatch.setattr(server, "store_write_token", SecretStr(WRITE_TOKEN))
    return {"X-API-Key": WRITE_TOKEN}


@pytest.fixture
def rest(server):
    """REST API in process; server errors are answered, not re-raised."""
    return TestClient(rest_app, raise_server_exceptions=False)


@pytest.fixture
def cli() -> Callable[..., Result]:
    """``obserwator`` in process: the Click result of the given arguments."""
    runner = CliRunner()

    def invoke(*args: object) -> Result:
        return runner.invoke(cli_app, [str(arg) for arg in args])

    return invoke
