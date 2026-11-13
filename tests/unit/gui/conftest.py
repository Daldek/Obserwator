"""
Fixtures of the GUI server's tests: the fixture root, recorded live data, the app.

The data root is the session's ``fixture_root`` (``tests/conftest.py``: the data root of
``build_fixture_store(raw, data_root=data, variant="complete_pl_cz")``, IMGW-PIB and
ČHMÚ) and a read-only copy of it, also with the analyses that ``build_analyses`` stores
with the recorded Hydrolog of ``tests/fixtures/hydrolog``; IMGW-PIB's current data and
PMAXTP are the library's recorded answers, put into the app's `GuiState`; Hydrolog's
program of the app (``OBSERWATOR_HYDROLOG_COMMAND``) is a small recorded program that
answers ``config show`` and ``commands batch`` as Hydrolog does, or none.
"""

from __future__ import annotations

import shutil
import stat
import sys
import textwrap
from collections.abc import Callable, Iterator
from dataclasses import dataclass, replace
from functools import partial
from pathlib import Path
from typing import Any

import pytest
from starlette.testclient import TestClient

from tests.contract.support import build_served_analyses, command_line

HYDRO = "149190310"
"""IMGW-PIB's hydrological station of the fixture root (daily H, Q, T of 2024)."""
HYDRO_CHMI = "0-203-1-900001"
"""ČHMÚ's hydrological station of the fixture root."""
METEO = "123750000"
"""IMGW-PIB's precipitation station of the fixture root (January 2001)."""
METEO_CHMI = "0-203-0-90001"
"""ČHMÚ's meteorological station of the fixture root."""
PMAXTP_POINT = (52.23, 21.01)
"""The point of the library's PMAXTP recordings."""
HYDROLOG_VERSION = "0.0.0-test"
"""The version the recorded Hydrolog program names."""
ANNUAL_MAXIMA = ([2023, 2024], [12.5, 30.25])
"""The hydrological years and annual maxima of every recorded Hydrolog result."""

_PROGRAM = textwrap.dedent(
    """
    import json
    import sys

    def envelope(command, result, **extra):
        return {
            "schema": "hydrolog-result/1", "tool": "hydrolog", "version": VERSION,
            "command": command, "status": "ok", "result": result, "notices": [],
            **extra,
        }

    args = sys.argv[1:]
    if args[:2] == ["config", "show"]:
        print(json.dumps(envelope("config show", {})))
        sys.exit(0)
    if args[:2] == ["commands", "batch"]:
        source = args[args.index("--input-file") + 1]
        target = args[args.index("--output") + 1]
        with open(source, encoding="utf-8") as calls, open(
            target, "w", encoding="utf-8", newline="\\n"
        ) as out:
            for line in calls:
                call = json.loads(line)
                if FAIL:
                    out.write(json.dumps({
                        "schema": "hydrolog-error/1", "tool": "hydrolog",
                        "code": "invalid_input", "message": "the series is too short",
                    }) + "\\n")
                    continue
                result = {
                    "options": call["options"],
                    "hydrological_years": YEARS,
                    "annual_maxima": MAXIMA,
                }
                out.write(json.dumps(envelope(call["command"], result)) + "\\n")
        print(json.dumps(envelope("commands batch", {})))
        sys.exit(11 if FAIL else 0)
    sys.exit(2)
    """
)


@dataclass(frozen=True)
class Live:
    """The recorded answers of IMGW-PIB: current data by source and PMAXTP by method."""

    records: dict[str, list[Any]]
    pmaxtp: dict[str, Any]
    outage: Exception

    def sources(self, **failing: Exception) -> dict[str, Callable[[], Any]]:
        """The sources of `CurrentData`; a source named in ``failing`` raises its error."""

        def fail(exc: Exception) -> Any:
            raise exc

        return {
            name: partial(fail, failing[name])
            if name in failing
            else partial(list, found)
            for name, found in self.records.items()
        }

    def fetch(self, latitude: float, longitude: float, *, method: str = "POT") -> Any:
        """`fetch_pmaxtp` answering the recorded point."""
        return self.pmaxtp[method]


def read_only(path: Path, *, writable: bool = False) -> None:
    """Make a tree read-only, or writable again so that it can be removed."""
    for item in [*sorted(path.rglob("*"), reverse=True), path]:
        mode = item.stat().st_mode
        item.chmod(mode | stat.S_IWUSR if writable else mode & ~0o222)


@pytest.fixture(scope="session")
def imgw_root(tmp_path_factory):
    """The data root of IMGW-PIB alone (variant ``complete``: no ČHMÚ catalog)."""
    from obserwator.testing import build_fixture_store

    base = tmp_path_factory.mktemp("gui-root-imgw")
    roots = build_fixture_store(
        base / "raw", data_root=base / "data", variant="complete"
    )
    return roots.data.root


@pytest.fixture(scope="session")
def read_only_root(fixture_root, tmp_path_factory) -> Iterator[Path]:
    """A read-only copy of the fixture root (GUI plan D7)."""
    root = tmp_path_factory.mktemp("gui-root-ro") / "root"
    shutil.copytree(fixture_root, root)
    read_only(root)
    yield root
    read_only(root, writable=True)


@pytest.fixture(scope="session")
def stored_root(fixture_root, tmp_path_factory) -> Iterator[Path]:
    """A read-only copy of the fixture root with its stored analyses (ADR-016)."""
    root = tmp_path_factory.mktemp("gui-root-stored") / "root"
    shutil.copytree(fixture_root, root)
    build_served_analyses(root)
    read_only(root)
    yield root
    read_only(root, writable=True)


@pytest.fixture(scope="session")
def live() -> Live:
    """IMGW-PIB's current data and PMAXTP from the library's recordings, read once."""
    import obserwator
    from obserwator.exceptions import ObserwatorError
    from obserwator.testing import _recorded_http

    files = ("recordings.json", "contract_recordings.json")
    cases = [
        "hydro_current",
        "meteo_current",
        "hydro_states",
        "synop_current",
        "pmaxtp_pot_first",
        "pmaxtp_amp",
    ]
    latitude, longitude = PMAXTP_POINT
    with _recorded_http(cases, recordings=files):
        records: dict[str, list[object]] = {
            "hydro": list(obserwator.fetch_hydro_current()),
            "meteo": list(obserwator.fetch_meteo_current()),
            "states": list(obserwator.fetch_hydro_states()),
            "synop": list(obserwator.fetch_synop()),
        }
        answers = {
            method: obserwator.fetch_pmaxtp(latitude, longitude, method=method)
            for method in ("POT", "AMP")
        }
    with _recorded_http(["hydro_current_outage"], recordings=files):
        try:
            obserwator.fetch_hydro_current()
        except ObserwatorError as exc:
            outage: Exception = exc
        else:  # pragma: no cover - the recording is an outage
            raise AssertionError("the outage recording answered")
    return Live(records, answers, outage)


def write_program(path: Path, *, fail: bool = False) -> tuple[str, ...]:
    """A recorded Hydrolog program at ``path``; ``fail`` makes every call fail."""
    years, maxima = ANNUAL_MAXIMA
    head = (
        f"VERSION = {HYDROLOG_VERSION!r}\nFAIL = {fail!r}\n"
        f"YEARS = {years!r}\nMAXIMA = {maxima!r}\n"
    )
    path.write_text(head + _PROGRAM, encoding="utf-8")
    return (sys.executable, str(path))


@pytest.fixture(scope="session")
def hydrolog(tmp_path_factory) -> tuple[str, ...]:
    """The command line of the recorded Hydrolog program."""
    return write_program(tmp_path_factory.mktemp("hydrolog") / "hydrolog.py")


def gui_config(root: Path, state_dir: Path, **changes: Any) -> Any:
    """Settings of a private GUI on ``root`` without basemap and Hydrolog."""
    from obserwator.gui._config import GuiConfig

    config = GuiConfig(
        root=root,
        state_dir=state_dir,
        basemap=None,
        request_limit=100_000,
        request_window=60,
        gui={},
        operator=None,
        operator_problems=(),
    )
    return replace(config, **changes)


@pytest.fixture
def make_client(
    tmp_path, read_only_root, live, monkeypatch
) -> Iterator[Callable[..., TestClient]]:
    """
    Open a client of the app, its lifespan running, until the test ends.

    ``make_client(root=None, *, hydrolog=None, live=…, headers=…, **config)``: the app
    on ``root`` (the read-only root by default) with Hydrolog's program ``hydrolog`` (a
    command line's words; none by default), the settings changed by ``config`` and the
    live sources of ``live`` (`Live.sources` names; recorded by default).
    """
    from obserwator.gui._app import build_app
    from obserwator.gui._live import CurrentData, Pmaxtp

    opened: list[TestClient] = []

    def make(
        root: Path | None = None,
        *,
        hydrolog: tuple[str, ...] | None = None,
        sources: dict[str, Callable[[], Any]] | None = None,
        fetch: Callable[..., Any] | None = None,
        headers: dict[str, str] | None = None,
        **changes: Any,
    ) -> TestClient:
        monkeypatch.setenv(
            "OBSERWATOR_HYDROLOG_COMMAND",
            command_line(*(hydrolog or (str(tmp_path / "no-hydrolog"),))),
        )
        state_dir = changes.pop("state_dir", tmp_path / f"state-{len(opened)}")
        config = gui_config(root or read_only_root, state_dir, **changes)
        app = build_app(config)
        app.state.gui.current = CurrentData(sources=sources or live.sources())
        app.state.gui.pmaxtp = Pmaxtp(fetch=fetch or live.fetch)
        client = TestClient(app, headers=headers)
        client.__enter__()
        opened.append(client)
        return client

    yield make
    for client in reversed(opened):
        client.__exit__(None, None, None)


@pytest.fixture
def client(make_client):
    """A client of the private GUI on the read-only root, in Polish (the default)."""
    return make_client()
