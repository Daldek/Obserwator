"""
Shared pytest fixtures for Obserwator tests.
"""

import atexit
import os
import shutil
import tempfile

import pytest

# Keep the servers' logs of the whole session out of the user's state directory.
# ``obserwator.config.settings`` and the log of ``obserwator.api.main``
# (``<state_dir>/obserwator/logs``) are made when first imported, which the conftest
# files below this one do before any hook or fixture runs, so the variable is set when
# this file is imported; the servers that tests start as programs inherit it. A test
# that checks the logs gives its own ``OBSERWATOR_STATE_DIR`` or ``ServerLog``. The
# directory goes when the session's process ends, also after a collection error.
_STATE_ENV = "OBSERWATOR_STATE_DIR"
_SESSION_STATE = tempfile.mkdtemp(prefix="obserwator-tests-state-")
os.environ[_STATE_ENV] = _SESSION_STATE
atexit.register(shutil.rmtree, _SESSION_STATE, ignore_errors=True)


@pytest.fixture(autouse=True)
def isolated_reference_dir(tmp_path_factory, monkeypatch):
    """Point ``settings.data_dir`` at an empty directory for every test.

    Local IMGW-PIB reference data (``python -m obserwator.reference_data``) must not
    leak into tests; a test that needs such a file writes it into this directory.
    """
    from obserwator.config import settings

    data_dir = tmp_path_factory.mktemp("data")
    monkeypatch.setattr(settings, "reference_dir", data_dir)
    return data_dir


@pytest.fixture(scope="session")
def fixture_roots(tmp_path_factory):
    """
    The ``complete_pl_cz`` roots of ``obserwator.testing``, built once per session.

    The raw root and the data root built from it (ADR-017); never written, a
    test copies them to mutate.
    """
    from obserwator.testing import build_fixture_store

    base = tmp_path_factory.mktemp("fixture")
    return build_fixture_store(
        base / "raw", data_root=base / "data", variant="complete_pl_cz"
    )


@pytest.fixture(scope="session")
def fixture_root(fixture_roots):
    """The data root of the fixture roots (series, station catalogs): a ``Path``."""
    return fixture_roots.data.root


@pytest.fixture(scope="session")
def fixture_raw_root(fixture_roots):
    """The raw root of the fixture roots (archives, station sources): a ``Path``."""
    return fixture_roots.raw.root


# Sample PMAXTP API response
@pytest.fixture
def pmaxtp_api_response():
    """Sample response from PMAXTP API."""
    return {
        "data": {
            "ks": {
                "5": {"1": 8.5, "2": 7.2, "5": 5.8, "10": 4.9, "20": 4.0, "50": 2.9},
                "10": {"1": 12.1, "2": 10.3, "5": 8.3, "10": 7.0, "20": 5.7, "50": 4.1},
                "15": {
                    "1": 14.8,
                    "2": 12.6,
                    "5": 10.2,
                    "10": 8.6,
                    "20": 7.0,
                    "50": 5.1,
                },
                "30": {
                    "1": 20.5,
                    "2": 17.5,
                    "5": 14.1,
                    "10": 11.9,
                    "20": 9.7,
                    "50": 7.0,
                },
                "60": {
                    "1": 28.4,
                    "2": 24.2,
                    "5": 19.5,
                    "10": 16.5,
                    "20": 13.4,
                    "50": 9.7,
                },
            },
            "sg": {
                "5": {"1": 9.0, "2": 7.6, "5": 6.1, "10": 5.2, "20": 4.2, "50": 3.1},
                "10": {"1": 12.8, "2": 10.9, "5": 8.8, "10": 7.4, "20": 6.0, "50": 4.4},
                "15": {
                    "1": 15.6,
                    "2": 13.3,
                    "5": 10.8,
                    "10": 9.1,
                    "20": 7.4,
                    "50": 5.4,
                },
            },
            "rb": {
                "5": {"1": 0.5, "2": 0.4, "5": 0.3, "10": 0.3, "20": 0.2, "50": 0.2},
                "10": {"1": 0.7, "2": 0.6, "5": 0.5, "10": 0.4, "20": 0.3, "50": 0.3},
                "15": {"1": 0.8, "2": 0.7, "5": 0.6, "10": 0.5, "20": 0.4, "50": 0.3},
            },
        }
    }
