"""
Fixtures of the GUI's browser tests (GUI plan D17): Playwright for Python with Chromium.

Every test of this directory is marked ``e2e`` and is skipped when Chromium cannot start
(``uv run playwright install chromium``). The page is served by the GUI's own app under
uvicorn in a thread, on a free port of 127.0.0.1:

* ``gui_url``: a read-only copy of the fixture data root (``fixture_root`` of
  ``tests/conftest.py``, ``complete_pl_cz``, no stored analyses), no basemap (the
  packaged borders), IMGW-PIB's current data and PMAXTP answered from the library's
  recordings, Hydrolog only when ``OBSERWATOR_HYDROLOG_COMMAND`` is set; not public (no
  ``[nogat.operator]``).
* ``public_url``: the same root as a public deployment: ``[nogat.operator]`` and
  ``[nogat.gui]`` set, so ``regulamin.html`` is served and linked.
* ``stored_url``: a read-only copy of the fixture data root with the analyses that
  ``build_analyses`` stored with the recorded Hydrolog (``tests/fixtures/hydrolog``), the
  rest as ``gui_url``, and no Hydrolog's program at all: only stored results.
* ``analysis_url``: the data root named by ``OBSERWATOR_GUI_E2E_ROOT`` (long records and
  the analyses ``obserwator analyses build`` stored, e.g. a copy of a deployment's root)
  with Hydrolog's program of ``OBSERWATOR_HYDROLOG_COMMAND`` for a person's choices;
  tests using it are skipped when either is unset (mark them ``hydrolog``).
* ``admin_site``: the GUI on the fixture root as ``gui_url`` but its own server, with the
  admin key `ADMIN_KEY` set and its own directory (``feedback.jsonl``, ``stats.jsonl``)
  given to the test, for the admin panel of Nogat DEV-15.13.

A server without ``OBSERWATOR_HYDROLOG_COMMAND`` finds no ``hydrolog`` on ``PATH`` either:
it computes nothing for its whole life.

``open_page`` opens a path of a server in a new browser context with the theme, the
language and the width chosen, and fails the test at its end on any console error, page
error or Content-Security-Policy violation.
"""

from __future__ import annotations

import json
import os
import shlex
import shutil
import socket
import stat
import threading
import time
from collections.abc import Callable, Iterator
from dataclasses import replace
from functools import partial
from pathlib import Path
from typing import Any, Self

import pytest

HERE = Path(__file__).resolve().parent
THEMES = ("light", "dark")
"""The themes of ``localStorage["nogat-theme"]``."""
WIDTHS = (1440, 390)
"""A desktop and a phone (the bottom sheets start at 860 px)."""
PMAXTP_POINT = (52.23, 21.01)
"""The point of the library's PMAXTP recordings."""
FIXTURE_STATIONS = {
    "hydro": "149190310",
    "hydro_chmi": "0-203-1-900001",
    "meteo": "123750000",
    "meteo_chmi": "0-203-0-90001",
}
"""Stations of the fixture root: IMGW-PIB and ČHMÚ, hydrological and meteorological."""
ADMIN_KEY = "klucz-e2e-0123"
"""The admin key of ``admin_site`` (``OBSERWATOR_ADMIN_API_KEY``, read on every request)."""

_CSP_LISTENER = """
document.addEventListener("securitypolicyviolation", (event) => {
  (window.__cspViolations = window.__cspViolations || []).push(
    `${event.violatedDirective} ${event.blockedURI}`);
});
"""


def pytest_collection_modifyitems(config, items):
    for item in items:
        if HERE in Path(str(item.fspath)).resolve().parents:
            item.add_marker(pytest.mark.e2e)


# --- servers -----------------------------------------------------------------------------


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _recorded_live() -> tuple[dict[str, Any], Callable[..., Any]]:
    """IMGW-PIB's current data and PMAXTP of the library's recordings, read once."""
    import obserwator
    from obserwator.testing import _recorded_http

    files = ("recordings.json", "contract_recordings.json")
    cases = [
        "hydro_current",
        "hydro_current_station",
        "meteo_current",
        "hydro_states",
        "synop_current",
        "pmaxtp_pot_first",
        "pmaxtp_amp",
    ]
    hydro_station = FIXTURE_STATIONS["hydro"]
    with _recorded_http(cases, recordings=files):
        listing = obserwator.fetch_hydro_current()
        # The listing's values are empty; the station's own answer has them, with times
        one = obserwator.fetch_hydro_current(station=hydro_station)
        records = {
            "hydro": [
                *one,
                *(r for r in listing if str(r.station_code) != hydro_station),
            ],
            "meteo": obserwator.fetch_meteo_current(),
            "states": obserwator.fetch_hydro_states(),
            "synop": obserwator.fetch_synop(),
        }
        latitude, longitude = PMAXTP_POINT
        answers = {
            method: obserwator.fetch_pmaxtp(latitude, longitude, method=method)
            for method in ("POT", "AMP")
        }

    def pmaxtp(
        latitude: float, longitude: float, *, method: str = "POT", **_: Any
    ) -> Any:
        return answers[method]

    return records, pmaxtp


def _read_only(path: Path, *, writable: bool = False) -> None:
    """Make a tree read-only (or writable again, to remove it)."""
    for item in sorted(path.rglob("*"), reverse=True) + [path]:
        mode = item.stat().st_mode
        if item.is_dir():
            wanted = mode | stat.S_IWUSR if writable else mode & ~0o222
        else:
            wanted = mode | stat.S_IWUSR if writable else mode & ~0o222
        item.chmod(wanted)


class _Server:
    """The GUI app under uvicorn in a thread."""

    def __init__(self, app: Any, port: int) -> None:
        import uvicorn

        self.url = f"http://127.0.0.1:{port}/"
        self.app = app
        self.server = uvicorn.Server(
            uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
        )
        self.thread = threading.Thread(target=self.server.run, daemon=True)

    def __enter__(self) -> Self:
        self.thread.start()
        deadline = time.monotonic() + 30
        while not self.server.started:
            if time.monotonic() > deadline or not self.thread.is_alive():
                raise RuntimeError("the GUI server did not start")
            time.sleep(0.05)
        return self

    def __exit__(self, *exc: object) -> None:
        self.server.should_exit = True
        self.thread.join(timeout=30)


def _nogat_toml(path: Path, data_dir: Path, *, public_url: str | None) -> Path:
    lines = ["[nogat]", f"data_dir = {json.dumps(str(data_dir))}", ""]
    if public_url is not None:
        lines += [
            "[nogat.gui]",
            f"obserwator = {json.dumps(public_url)}",
            "",
            "[nogat.operator]",
            'name = "Operator testowy"',
            'email = "operator@example.org"',
            "terms_effective = 2026-11-13",
            'processor = "Example Processor"',
            'processor_transfer = ""',
            'mail_provider = "Example Mail"',
            "",
        ]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _start(
    root: Path,
    work: Path,
    *,
    public: bool = False,
    hydrolog: str | None = None,
    recorded: bool = True,
) -> _Server:
    """A GUI server on ``root``; its own files under ``work``."""
    from obserwator.gui._app import build_app
    from obserwator.gui._config import GuiConfig
    from obserwator.gui._live import CurrentData, Pmaxtp

    port = _free_port()
    url = f"http://127.0.0.1:{port}/"
    work.mkdir(parents=True, exist_ok=True)
    toml = _nogat_toml(
        work / "nogat.toml", work / "data", public_url=url if public else None
    )
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("NOGAT_CONFIG", str(toml))
        # An empty value is ignored by the settings (env_ignore_empty): "none" is no basemap
        patch.setenv("OBSERWATOR_GUI_BASEMAP_URL", "none")
        patch.delenv("OBSERWATOR_ROOT", raising=False)
        if hydrolog:
            patch.setenv("OBSERWATOR_HYDROLOG_COMMAND", hydrolog)
        else:
            patch.delenv("OBSERWATOR_HYDROLOG_COMMAND", raising=False)
            # No program on PATH either while the app looks for it, once (D8)
            patch.setenv(
                "PATH",
                os.pathsep.join(
                    folder
                    for folder in os.environ.get("PATH", "").split(os.pathsep)
                    if shutil.which("hydrolog", path=folder) is None
                ),
            )
        config = GuiConfig.resolve(root=root)
        # The app looks for Hydrolog's program once, as it starts
        app = build_app(replace(config, request_limit=100_000))
    if recorded:
        records, pmaxtp = _recorded_live()
        state = app.state.gui
        state.current = CurrentData(
            sources={name: partial(list, found) for name, found in records.items()}
        )
        state.pmaxtp = Pmaxtp(fetch=pmaxtp)
    return _Server(app, port)


@pytest.fixture(scope="session")
def gui_root(fixture_root, tmp_path_factory) -> Iterator[Path]:
    """A read-only copy of the fixture data root of both providers."""
    root = tmp_path_factory.mktemp("gui-root") / "root"
    shutil.copytree(fixture_root, root)
    _read_only(root)
    yield root
    _read_only(root, writable=True)


@pytest.fixture(scope="session")
def stored_root(fixture_root, tmp_path_factory) -> Iterator[Path]:
    """A read-only copy of the fixture data root with its analyses stored (ADR-016)."""
    from tests.contract.support import build_served_analyses

    root = tmp_path_factory.mktemp("gui-root-stored") / "root"
    shutil.copytree(fixture_root, root)
    build_served_analyses(root)
    _read_only(root)
    yield root
    _read_only(root, writable=True)


@pytest.fixture(scope="session")
def stored_url(stored_root, tmp_path_factory) -> Iterator[str]:
    """The GUI on the root with stored analyses and no Hydrolog's program."""
    work = tmp_path_factory.mktemp("gui-stored")
    with _start(stored_root, work) as server:
        yield server.url


@pytest.fixture(scope="session")
def gui_url(gui_root, tmp_path_factory) -> Iterator[str]:
    """The GUI on the fixture root, not public."""
    hydrolog = os.environ.get("OBSERWATOR_HYDROLOG_COMMAND") or None
    work = tmp_path_factory.mktemp("gui-private")
    with _start(gui_root, work, hydrolog=hydrolog) as server:
        yield server.url


@pytest.fixture(scope="session")
def public_url(gui_root, tmp_path_factory) -> Iterator[str]:
    """The GUI on the fixture root as a public deployment (``[nogat.operator]``)."""
    work = tmp_path_factory.mktemp("gui-public")
    with _start(gui_root, work, public=True) as server:
        yield server.url


@pytest.fixture(scope="session")
def analysis_url(tmp_path_factory) -> Iterator[str]:
    """The GUI on a root with long records and Hydrolog (``OBSERWATOR_GUI_E2E_ROOT``)."""
    root = os.environ.get("OBSERWATOR_GUI_E2E_ROOT")
    hydrolog = os.environ.get("OBSERWATOR_HYDROLOG_COMMAND")
    if not root or not hydrolog:
        pytest.skip("OBSERWATOR_GUI_E2E_ROOT and OBSERWATOR_HYDROLOG_COMMAND are unset")
    if not shlex.split(hydrolog) or not Path(root).is_dir():
        pytest.skip(f"no root at {root} or no Hydrolog program")
    work = tmp_path_factory.mktemp("gui-analyses")
    with _start(Path(root), work, hydrolog=hydrolog) as server:
        yield server.url


@pytest.fixture
def admin_site(gui_root, tmp_path, monkeypatch) -> Iterator[tuple[str, Path]]:
    """The GUI with its admin key, and its own directory: ``(url, directory)``."""
    monkeypatch.setenv("OBSERWATOR_ADMIN_API_KEY", ADMIN_KEY)
    monkeypatch.delenv("OBSERWATOR_ADMIN_API_KEY_FILE", raising=False)
    work = tmp_path / "gui-admin"
    directory = work / "data" / "obserwator"  # <data_dir>/obserwator of its nogat.toml
    directory.mkdir(parents=True)
    with _start(gui_root, work, recorded=False) as server:
        yield server.url, directory


# --- the browser -------------------------------------------------------------------------


@pytest.fixture(scope="package")
def browser() -> Iterator[Any]:
    """
    Chromium of Playwright, headless; the tests are skipped without it.

    Package-scoped: Playwright's sync API keeps an event loop running in the main thread,
    so it stops after this directory's tests, before tests that call ``asyncio.run``.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:  # pragma: no cover - the dev group has it
        pytest.skip("Playwright is not installed")
    manager = sync_playwright().start()
    try:
        chromium = manager.chromium.launch()
    except Exception as exc:  # noqa: BLE001 - any launch failure means no browser
        manager.stop()
        pytest.skip(f"Chromium does not start: {exc}")
    yield chromium
    chromium.close()
    manager.stop()


class PageProblems(AssertionError):
    """Console errors, page errors or CSP violations of a page."""


@pytest.fixture
def open_page(browser, gui_url) -> Iterator[Callable[..., Any]]:
    """
    Open a path of a GUI server in a fresh context; fail on console errors at the end.

    ``open_page(path="", *, base=None, theme="light", width=1440, height=900, lang="pl",
    ready=True, welcome=False)`` returns the Playwright ``Page``: ``base`` is a server's
    URL (``gui_url`` by default, or ``public_url``, ``analysis_url``), ``theme`` and
    ``lang`` are stored before the first script runs unless the page stored its own,
    ``ready`` waits until the app has drawn its first element, and without ``welcome`` the
    welcome window of a first visit counts as seen.
    """
    opened: list[tuple[Any, Any, list[str]]] = []

    def opener(
        path: str = "",
        *,
        base: str | None = None,
        theme: str = "light",
        width: int = 1440,
        height: int = 900,
        lang: str = "pl",
        ready: bool = True,
        welcome: bool = False,
    ) -> Any:
        context = browser.new_context(
            viewport={"width": width, "height": height}, accept_downloads=True
        )
        context.add_init_script(
            "if (!localStorage.getItem('nogat-theme')) "
            f"localStorage.setItem('nogat-theme', {json.dumps(theme)});"
            "if (!localStorage.getItem('obserwator-lang')) "
            f"localStorage.setItem('obserwator-lang', {json.dumps(lang)});"
            + ("" if welcome else "localStorage.setItem('obserwator-welcome', '1');")
            + _CSP_LISTENER
        )
        page = context.new_page()
        problems: list[str] = []

        def console(message: Any) -> None:
            if message.type == "error":
                problems.append(f"console error: {message.text} ({message.location})")

        page.on("console", console)
        page.on("pageerror", lambda error: problems.append(f"page error: {error}"))
        opened.append((context, page, problems))
        page.goto((base or gui_url) + path.lstrip("/"))
        if ready:
            # A locator, not wait_for_function: Playwright may evaluate a function string
            # with eval, which the page's CSP refuses (no 'unsafe-eval'). "attached":
            # with ?nogat=1 the first child, the top bar, is hidden.
            page.locator("#app > *").first.wait_for(state="attached", timeout=15_000)
        return page

    yield opener
    found: list[str] = []
    for context, page, problems in opened:
        if not page.is_closed():
            violations = page.evaluate("window.__cspViolations || []")
            found += [f"CSP violation: {item}" for item in violations]
        found += problems
        context.close()
    if found:
        raise PageProblems("\n".join(found))
