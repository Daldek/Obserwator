"""
The analyses of a station in the GUI: Hydrolog's stored results and a person's choices.

The data root is the fixture root with the analyses ``build_analyses`` stored with the
recorded Hydrolog of ``tests/fixtures/hydrolog`` (read-only); the same recorded program
computes a person's choices and logs every batch it runs. What the store computes and
stores is the store's own tests' (``tests/unit/test_analyses.py``); these check what the
GUI adds: the registry's options, the refusals before Hydrolog runs, the stored result
first, the memory of computed results, the limit of computations and the server paths.
"""

from __future__ import annotations

import asyncio
import json
import sys
import threading
import time
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from starlette.testclient import TestClient

from obserwator import read_analysis
from obserwator.gui import _analyses
from obserwator.gui._analyses import Analyses
from obserwator.gui._app import build_app
from obserwator.gui._config import GuiConfig
from obserwator.gui._root import DataRoot
from tests.contract.support import FAKE_HYDROLOG, command_line

# Stations of the fixture root.
H_AND_T = "149190311"  # IMGW-PIB: H and T, no Q
CZ_HYDRO = "0-203-1-900001"  # ČHMÚ: H, Q and T, thresholds of H and Q
PRECIPITATION = "123750000"  # IMGW-PIB precipitation station with snow


@pytest.fixture
def batches(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The recorded program's log of its batches, one test's own."""
    path = tmp_path / "batches.jsonl"
    for name in ("FAKE_HYDROLOG_SLEEP", "FAKE_HYDROLOG_FAIL", "FAKE_HYDROLOG_VERSION"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("FAKE_HYDROLOG_LOG", str(path))
    return path


def gui_app(
    root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *program: str
) -> TestClient:
    """A client of the GUI's API on ``root``, started with Hydrolog's ``program``."""
    toml = tmp_path / "nogat.toml"
    toml.write_text(
        f"[nogat]\ndata_dir = {json.dumps(str(tmp_path / 'data'))}\n", encoding="utf-8"
    )
    monkeypatch.setenv("NOGAT_CONFIG", str(toml))
    monkeypatch.setenv("OBSERWATOR_GUI_BASEMAP_URL", "none")
    monkeypatch.delenv("OBSERWATOR_ROOT", raising=False)
    monkeypatch.setenv("OBSERWATOR_HYDROLOG_COMMAND", command_line(*program))
    config = replace(GuiConfig.resolve(root=root), request_limit=100_000)
    return TestClient(build_app(config))


@pytest.fixture
def client(
    stored_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, batches: Path
) -> Iterator[TestClient]:
    """The GUI's API on the root with stored analyses and the recorded program."""
    program = (sys.executable, str(FAKE_HYDROLOG))
    with gui_app(stored_root, tmp_path, monkeypatch, *program) as found:
        yield found


def ran(log: Path) -> list[list[dict[str, Any]]]:
    """The calls of each batch the recorded program ran."""
    if not log.exists():
        return []
    return [
        json.loads(line)["calls"]
        for line in log.read_text(encoding="utf-8").splitlines()
    ]


def overridable(client: TestClient, station: str, analysis: str) -> dict[str, Any]:
    entries = client.get(f"api/analyses/{station}").json()["analyses"]
    return next(e["overridable"] for e in entries if e["analysis"] == analysis)


# --- the stored results and their options ------------------------------------------------


def test_a_stored_result_is_served_without_running_hydrolog(
    client: TestClient, stored_root: Path, batches: Path
) -> None:
    response = client.get(f"api/analysis/{CZ_HYDRO}/characteristic.Q")

    document = response.json()
    stored = read_analysis(
        root=stored_root, station=CZ_HYDRO, analysis="characteristic.Q"
    )
    assert response.status_code == 200
    assert document["source"] == "stored"
    assert document["stored"] is True
    assert document["analyses_version"] == stored.analyses_version
    assert stored.envelope is not None
    assert document["envelope"]["result"] == stored.envelope["result"]
    assert ran(batches) == []


def test_without_a_program_at_the_start_a_choice_is_refused_even_if_one_is_named_later(
    stored_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, batches: Path
) -> None:
    missing = str(tmp_path / "no-hydrolog")
    with gui_app(stored_root, tmp_path, monkeypatch, missing) as client:
        monkeypatch.setenv(
            "OBSERWATOR_HYDROLOG_COMMAND",
            command_line(sys.executable, str(FAKE_HYDROLOG)),
        )
        stored = client.get(f"api/analysis/{CZ_HYDRO}/characteristic.Q")
        chosen = client.get(f"api/analysis/{CZ_HYDRO}/characteristic.Q?first_year=2024")
        session = client.get("api/session").json()

    assert stored.json()["source"] == "stored"
    assert chosen.status_code == 503
    assert chosen.json()["code"] == "missing_dependency"
    assert session["compute"]["available"] is False
    assert ran(batches) == []


def test_an_id_lists_the_options_it_passes_on_to_what_it_depends_on(
    client: TestClient,
) -> None:
    trend = overridable(client, CZ_HYDRO, "mann_kendall.Q.max")
    own = overridable(client, CZ_HYDRO, "characteristic.Q")

    assert set(trend) == {"alpha", "first_year", "last_year"}
    assert trend["alpha"] == {
        "type": "number",
        "exclusive_minimum": 0.0,
        "exclusive_maximum": 1.0,
    }
    assert own == {
        "first_year": {"type": "integer", "minimum": 1},
        "last_year": {"type": "integer", "minimum": 1},
    }


# --- a person's options ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("station", "analysis", "query", "option"),
    [
        (CZ_HYDRO, "characteristic.Q", "first_year=abc", "first_year"),
        (CZ_HYDRO, "characteristic.Q", "first_year=0", "first_year"),
        (CZ_HYDRO, "characteristic.Q", "parameter=H", "parameter"),
        (CZ_HYDRO, "mann_kendall.Q.max", "alpha=1", "alpha"),
        (CZ_HYDRO, "rating_curve.periods", "years_per_period=31", "years_per_period"),
        (CZ_HYDRO, "rating_curve", "remove_outliers=maybe", "remove_outliers"),
        (CZ_HYDRO, "flood_frequency.Q", "distribution=normal", "distribution"),
        (CZ_HYDRO, "flood_frequency.Q", "return_periods=0.5,10", "return_periods"),
        (CZ_HYDRO, "flood_frequency.Q", "return_periods=", "return_periods"),
        (
            PRECIPITATION,
            "precipitation_quantiles.2d",
            "durations_days=1,2",
            "durations_days",
        ),
        (PRECIPITATION, "spells.dry", "min_duration_days=0", "min_duration_days"),
        (
            PRECIPITATION,
            "precipitation.maxima",
            "reference_first_year=1991",
            "reference_first_year",
        ),
    ],
)
def test_a_wrong_option_is_refused_before_hydrolog_runs(
    client: TestClient,
    batches: Path,
    station: str,
    analysis: str,
    query: str,
    option: str,
) -> None:
    response = client.get(f"api/analysis/{station}/{analysis}?{query}")

    assert response.status_code == 400
    assert response.json()["code"] == "validation_error"
    assert response.json()["details"]["option"] == option
    assert ran(batches) == []


def test_an_unknown_option_names_those_the_id_takes(client: TestClient) -> None:
    response = client.get(f"api/analysis/{CZ_HYDRO}/characteristic.Q?bin_width=5")

    assert response.status_code == 400
    assert response.json()["details"]["allowed"] == ["first_year", "last_year"]


@pytest.mark.parametrize(
    ("station", "analysis"),
    [(H_AND_T, "rating_curve?first_year=2024"), (CZ_HYDRO, "nonsense?first_year=2024")],
)
def test_an_id_the_station_cannot_have_is_not_found(
    client: TestClient, batches: Path, station: str, analysis: str
) -> None:
    response = client.get(f"api/analysis/{station}/{analysis}")

    assert response.status_code == 404
    assert response.json()["code"] == "not_found"
    assert ran(batches) == []


def test_a_persons_choice_is_computed_once_and_shows_no_server_path(
    client: TestClient, stored_root: Path, batches: Path
) -> None:
    path = f"api/analysis/{CZ_HYDRO}/characteristic.Q?first_year=2024"

    first = client.get(path)
    again = client.get(path)

    document = first.json()
    assert document["source"] == "computed"
    assert document["stored"] is False
    assert document["analyses_version"] is None
    assert document["options"]["first_year"] == 2024
    assert again.json() == document
    assert len(ran(batches)) == 1
    # Hydrolog read the series in a scratch directory of the server: names only
    assert "/" not in document["envelope"]["inputs"]["input_file"]
    assert str(stored_root) not in first.text


def test_an_option_of_a_dependency_reaches_it_and_not_the_id(
    client: TestClient, batches: Path
) -> None:
    response = client.get(
        f"api/analysis/{CZ_HYDRO}/mann_kendall.Q.max?first_year=2024&alpha=0.1"
    )

    assert response.status_code == 200
    first, second = ran(batches)
    assert first[0]["command"] == "stats characteristic"
    assert first[0]["options"]["first_year"] == 2024
    assert second[0]["command"] == "stats mann-kendall"
    assert "first_year" not in second[0]["options"]
    assert second[0]["options"]["alpha"] == 0.1


# --- Hydrolog's answers and failures --------------------------------------------------------


def test_hydrologs_refusal_is_a_failed_result(client: TestClient) -> None:
    response = client.get(f"api/analysis/{CZ_HYDRO}/flood_frequency.Q?first_year=2024")

    document = response.json()
    assert response.status_code == 200
    assert (document["status"], document["error_code"]) == (
        "failed",
        "calculation_error",
    )
    assert document["envelope"] is None
    assert document["source"] == "computed"


def test_a_program_that_fails_is_unavailable_and_not_kept(
    client: TestClient, batches: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = f"api/analysis/{CZ_HYDRO}/characteristic.Q?first_year=2024"
    monkeypatch.setenv("FAKE_HYDROLOG_FAIL", "1")
    failed = client.get(path)
    monkeypatch.delenv("FAKE_HYDROLOG_FAIL")
    again = client.get(path)

    assert failed.status_code == 502
    assert failed.json()["code"] == "source_unavailable"
    assert failed.json()["details"]["reason"] == "hydrolog_failed"
    assert again.status_code == 200
    assert len(ran(batches)) == 2


def test_a_computation_past_the_time_limit_is_stopped(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(_analyses, "TIMEOUT_S", 0.5)
    monkeypatch.setenv("FAKE_HYDROLOG_SLEEP", "30")
    started = time.monotonic()

    response = client.get(f"api/analysis/{CZ_HYDRO}/characteristic.Q?first_year=2024")

    assert response.status_code == 502
    assert response.json()["details"]["reason"] == "timeout"
    assert time.monotonic() - started < 15


# --- the memory and the limit of computations -----------------------------------------------


def test_at_most_two_computations_run_at_once_and_one_per_result(
    stored_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lock = threading.Lock()
    running = most = calls = 0

    def compute(root: Path, /, **asked: Any) -> Any:
        nonlocal running, most, calls
        with lock:
            running += 1
            calls += 1
            most = max(most, running)
        time.sleep(0.2)
        with lock:
            running -= 1
        return read_analysis(
            root=stored_root, station=asked["station"], analysis=asked["analysis"]
        )

    monkeypatch.setattr(_analyses, "compute_analysis", compute)
    monkeypatch.setenv(
        "OBSERWATOR_HYDROLOG_COMMAND", command_line(sys.executable, str(FAKE_HYDROLOG))
    )
    analyses = Analyses(stored_root)
    snapshot = DataRoot(stored_root).snapshot()
    different = ["characteristic.H", "characteristic.Q", "daily.Q", "monthly.Q"]
    choice = {"first_year": 2024}

    async def run() -> list[tuple[dict[str, Any], str]]:
        requests = [analyses.get(snapshot, CZ_HYDRO, i, choice) for i in different]
        requests += [
            analyses.get(snapshot, CZ_HYDRO, "daily.T", choice) for _ in range(3)
        ]
        return await asyncio.gather(*requests)

    results = asyncio.run(run())

    assert [result["source"] for result, _ in results] == ["computed"] * 7
    assert results[-1] == results[-2] == results[-3]
    assert calls == len(different) + 1
    assert most == _analyses.PROCESSES == 2
