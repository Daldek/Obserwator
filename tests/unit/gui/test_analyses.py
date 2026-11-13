"""
The analyses of a station in the GUI: O2's ids, a person's options, Hydrolog's program.

The ids come from the stand-in of O2's registry over the fixture root (read-only); the
program is a fake (``fake_hydrolog.py``) that answers ``commands batch`` with Hydrolog's
recorded envelopes and logs every process it ran. One test, marked ``hydrolog``, runs
the real program.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import shlex
import shutil
import subprocess
import sys
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from starlette.testclient import TestClient

from obserwator.gui import _analyses
from obserwator.gui._analyses import Analyses
from obserwator.gui._app import build_app
from obserwator.gui._config import GuiConfig
from obserwator.gui._root import DataRoot
from obserwator.gui._standin import StandIn
from obserwator.store import export_series
from obserwator.testing import build_fixture_store

FAKE = Path(__file__).with_name("fake_hydrolog.py")
FAKE_WORDS = (sys.executable, str(FAKE))
RECORDED = json.loads(
    FAKE.with_name("hydrolog_recordings.json").read_text(encoding="utf-8")
)["answers"]
CHARACTERISTIC = RECORDED["stats characteristic|Q"]["result"]

# Stations of the fixture root.
HYDRO = "149190310"  # IMGW-PIB: H, Q and T, no thresholds in the catalog
H_AND_T = "149190311"  # IMGW-PIB: H and T, no Q
CZ_HYDRO = "0-203-1-900001"  # ČHMÚ: H, Q and T, thresholds of H and Q
CZ_Q_LEVELS = "0-203-1-900002"  # ČHMÚ: thresholds of Q only (those of H are null)
PRECIPITATION = "123750000"  # IMGW-PIB precipitation station with snow
CZ_METEO = "0-203-0-90001"  # ČHMÚ: precipitation and air temperature


def _read_only(root: Path, *, writable: bool = False) -> None:
    for path in [root, *root.rglob("*")]:
        if path.is_dir():
            path.chmod(0o755 if writable else 0o555)
        else:
            path.chmod(0o644 if writable else 0o444)


@pytest.fixture(scope="module")
def root(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Path]:
    """The fixture data root of both providers, read-only: the GUI never writes in it."""
    base = tmp_path_factory.mktemp("analyses")
    path = base / "data"
    build_fixture_store(base / "raw", data_root=path, variant="complete_pl_cz")
    _read_only(path)
    yield path
    _read_only(path, writable=True)


@pytest.fixture
def calls_log(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The fake program's log of its processes, one test's own."""
    path = tmp_path / "calls.jsonl"
    monkeypatch.setenv("FAKE_HYDROLOG_LOG", str(path))
    monkeypatch.delenv("FAKE_HYDROLOG_SLEEP", raising=False)
    monkeypatch.delenv("FAKE_HYDROLOG_EXIT", raising=False)
    return path


@pytest.fixture
def client(
    root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, calls_log: Path
) -> Iterator[TestClient]:
    """The GUI's API on the fixture root with the fake program."""
    toml = tmp_path / "nogat.toml"
    toml.write_text(
        f"[nogat]\ndata_dir = {json.dumps(str(tmp_path / 'data'))}\n", encoding="utf-8"
    )
    monkeypatch.setenv("NOGAT_CONFIG", str(toml))
    monkeypatch.setenv("OBSERWATOR_GUI_BASEMAP_URL", "none")
    monkeypatch.delenv("OBSERWATOR_ROOT", raising=False)
    monkeypatch.setenv("OBSERWATOR_HYDROLOG_COMMAND", shlex.join(FAKE_WORDS))
    config = replace(GuiConfig.resolve(root=root), request_limit=100_000)
    with TestClient(build_app(config), client=("203.0.113.9", 4321)) as found:
        yield found


def processes(log: Path) -> list[dict[str, Any]]:
    """The batches the fake program ran, in the order they ended."""
    if not log.exists():
        return []
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]


def ids(client: TestClient, station: str) -> list[str]:
    response = client.get(f"api/analyses/{station}")
    assert response.status_code == 200
    return [entry["analysis"] for entry in response.json()["analyses"]]


def overridable(client: TestClient, station: str, analysis: str) -> dict[str, Any]:
    entries = client.get(f"api/analyses/{station}").json()["analyses"]
    return next(e["overridable"] for e in entries if e["analysis"] == analysis)


# --- which ids a station has -----------------------------------------------------------


@pytest.mark.parametrize(
    ("station", "present", "absent"),
    [
        (
            H_AND_T,
            ["characteristic.H", "characteristic.T", "threshold_events.T.ge15"],
            [
                "characteristic.Q",
                "rating_curve",
                "flood_frequency.Q",
                "mann_kendall.Q.max",
            ],
        ),
        (
            CZ_Q_LEVELS,
            ["threshold_events.Q.spa1", "threshold_events.Q.drought"],
            ["threshold_events.H.spa1", "threshold_events.H.drought"],
        ),
        (
            HYDRO,
            ["threshold_events.Q.swx", "rating_curve"],
            ["threshold_events.Q.spa1"],
        ),
        (
            PRECIPITATION,
            ["precipitation.sums", "precipitation_quantiles.10d", "spells.dry", "snow"],
            ["temperature.means", "characteristic.Q"],
        ),
        (
            CZ_METEO,
            ["temperature.means", "mann_kendall.temperature.frost_days", "spi"],
            ["snow"],
        ),
    ],
)
def test_a_station_lists_the_ids_its_series_and_catalog_allow(
    client: TestClient, station: str, present: list[str], absent: list[str]
) -> None:
    found = ids(client, station)

    assert set(present) <= set(found)
    assert not set(absent) & set(found)


def test_a_listed_id_names_its_series_and_nothing_stored(client: TestClient) -> None:
    entries = client.get(f"api/analyses/{CZ_HYDRO}").json()["analyses"]
    entry = next(e for e in entries if e["analysis"] == "threshold_events.Q.swx")

    assert entry["command"] == "stats threshold-events"
    assert [i["dataset"] for i in entry["inputs"]] == ["cz.chmi.hydro_daily"]
    assert entry["inputs"][0]["series_version"].startswith("series/versions/")
    assert entry["stored"] is False
    assert entry["attribution"]


def test_an_id_lists_the_options_it_passes_on_to_what_it_depends_on(
    client: TestClient,
) -> None:
    trend = overridable(client, CZ_HYDRO, "mann_kendall.Q.max")
    one_day = overridable(client, PRECIPITATION, "precipitation_quantiles")
    two_days = overridable(client, PRECIPITATION, "precipitation_quantiles.2d")

    assert set(trend) == {"alpha", "first_year", "last_year"}
    assert trend["alpha"] == {
        "type": "number",
        "exclusive_minimum": 0.0,
        "exclusive_maximum": 1.0,
    }
    assert "durations_days" in one_day
    assert set(two_days) == {
        "distribution",
        "fit_method",
        "return_periods",
        "first_year",
        "last_year",
        "year_type",
    }
    assert two_days["return_periods"] == {
        "type": "array",
        "items": "number",
        "exclusive_minimum": 1.0,
        "min_items": 1,
        "max_items": 50,
    }


@pytest.mark.parametrize(
    ("station", "analysis"),
    [
        (H_AND_T, "rating_curve"),
        (HYDRO, "threshold_events.Q.spa1"),
        (HYDRO, "nonsense"),
    ],
)
def test_an_id_the_station_cannot_have_is_not_found(
    client: TestClient, calls_log: Path, station: str, analysis: str
) -> None:
    response = client.get(f"api/analysis/{station}/{analysis}")

    assert response.status_code == 404
    assert response.json()["code"] == "not_found"
    assert processes(calls_log) == []


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
    calls_log: Path,
    station: str,
    analysis: str,
    query: str,
    option: str,
) -> None:
    response = client.get(f"api/analysis/{station}/{analysis}?{query}")

    assert response.status_code == 400
    assert response.json()["code"] == "validation_error"
    assert response.json()["details"]["option"] == option
    assert processes(calls_log) == []


def test_an_unknown_option_names_those_the_id_takes(client: TestClient) -> None:
    response = client.get(f"api/analysis/{CZ_HYDRO}/characteristic.Q?bin_width=5")

    assert response.status_code == 400
    assert response.json()["details"]["allowed"] == ["first_year", "last_year"]


def test_an_option_of_a_dependency_reaches_it_and_not_the_id(
    client: TestClient, calls_log: Path
) -> None:
    response = client.get(
        f"api/analysis/{CZ_HYDRO}/mann_kendall.Q.max?first_year=2024&alpha=0.1"
    )

    assert response.status_code == 200
    first, second = (process["calls"] for process in processes(calls_log))
    assert first[0]["command"] == "stats characteristic"
    assert first[0]["options"]["first_year"] == 2024
    assert second[0]["command"] == "stats mann-kendall"
    assert "first_year" not in second[0]["options"]
    assert second[0]["options"]["alpha"] == 0.1


# --- dependencies and picks ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("analysis", "picked", "rounds"),
    [
        (
            "threshold_events.Q.swx",
            {"threshold": CHARACTERISTIC["swx"], "direction": "above"},
            2,
        ),
        (
            "threshold_events.Q.snx",
            {"threshold": CHARACTERISTIC["snx"], "direction": "below"},
            2,
        ),
        (
            "rating_curve",
            {
                "first_year": CHARACTERISTIC["last_year"] - 9,
                "last_year": CHARACTERISTIC["last_year"],
            },
            2,
        ),
        (
            "mann_kendall.Q.max",
            {
                "values": [year["annual"]["max"] for year in CHARACTERISTIC["years"]],
                "years": [year["year"] for year in CHARACTERISTIC["years"]],
            },
            2,
        ),
        ("threshold_events.Q.spa1", {"threshold": 14.2, "direction": "above"}, 1),
    ],
)
def test_a_number_from_hydrolog_or_the_catalog_goes_into_the_call(
    client: TestClient,
    calls_log: Path,
    analysis: str,
    picked: dict[str, Any],
    rounds: int,
) -> None:
    response = client.get(f"api/analysis/{CZ_HYDRO}/{analysis}")

    assert response.status_code == 200
    document = response.json()
    assert document["status"] == "ok"
    assert {name: document["options"][name] for name in picked} == picked
    ran = processes(calls_log)
    assert len(ran) == rounds
    assert ran[-1]["calls"][0]["options"] == document["options"]
    assert all(all(call["files"].values()) for p in ran for call in p["calls"])


def test_a_dependency_without_the_numbers_gives_no_result(
    client: TestClient, calls_log: Path
) -> None:
    # The recorded maxima of the station's only year are incomplete: no value to fit.
    response = client.get(f"api/analysis/{PRECIPITATION}/precipitation_quantiles")

    assert response.status_code == 500
    assert response.json()["code"] == "data_error"
    assert response.json()["details"]["reason"] == "dependency_failed"
    assert [p["calls"][0]["command"] for p in processes(calls_log)] == [
        "meteo precipitation"
    ]


# --- Hydrolog's answers and failures --------------------------------------------------------


def test_hydrologs_refusal_is_a_failed_result(client: TestClient) -> None:
    response = client.get(f"api/analysis/{CZ_HYDRO}/flood_frequency.Q")

    assert response.status_code == 200
    document = response.json()
    assert document["schema"] == "obserwator-analysis/1"
    assert (document["status"], document["error_code"]) == (
        "failed",
        "calculation_error",
    )
    assert document["error"] == RECORDED["stats flood-frequency"]
    assert document["envelope"] is None
    assert document["hydrolog"] == {"version": "1.0.0.dev0"}
    assert document["source"] == "computed"


def test_a_program_that_fails_is_unavailable_and_not_kept(
    client: TestClient, calls_log: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FAKE_HYDROLOG_EXIT", "3")
    failed = client.get(f"api/analysis/{CZ_HYDRO}/characteristic.Q")
    monkeypatch.delenv("FAKE_HYDROLOG_EXIT")
    again = client.get(f"api/analysis/{CZ_HYDRO}/characteristic.Q")

    assert failed.status_code == 502
    assert failed.json()["code"] == "source_unavailable"
    assert failed.json()["details"] == {"reason": "hydrolog_failed", "exit_code": 3}
    assert again.status_code == 200
    assert len(processes(calls_log)) == 1


def test_a_computation_past_the_time_limit_is_stopped(
    client: TestClient, calls_log: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(_analyses, "TIMEOUT_S", 0.5)
    monkeypatch.setenv("FAKE_HYDROLOG_SLEEP", "30")

    response = client.get(f"api/analysis/{CZ_HYDRO}/characteristic.Q")

    assert response.status_code == 502
    assert response.json()["details"]["reason"] == "timeout"
    assert processes(calls_log) == []  # killed before it answered


# --- the cache and the program limit ---------------------------------------------------------


def test_a_result_is_computed_once_per_options(
    client: TestClient, calls_log: Path
) -> None:
    first = client.get(f"api/analysis/{CZ_HYDRO}/characteristic.Q")
    second = client.get(f"api/analysis/{CZ_HYDRO}/characteristic.Q")
    other = client.get(f"api/analysis/{CZ_HYDRO}/characteristic.Q?first_year=2024")

    assert first.json() == second.json()
    assert first.headers["etag"] == second.headers["etag"]
    assert other.json()["options"]["first_year"] == 2024
    assert len(processes(calls_log)) == 2


def _most_at_once(spans: list[tuple[float, float]]) -> int:
    events = sorted(
        [(end, -1) for _, end in spans] + [(start, 1) for start, _ in spans]
    )
    running = most = 0
    for _, step in events:
        running += step
        most = max(most, running)
    return most


def test_at_most_two_programs_run_at_once_and_one_per_result(
    root: Path, tmp_path: Path, calls_log: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FAKE_HYDROLOG_SLEEP", "0.4")
    standin = StandIn(root, FAKE_WORDS, work=tmp_path / "work")
    analyses = Analyses(standin)
    snapshot = DataRoot(root).snapshot()
    different = ["characteristic.H", "characteristic.Q", "daily.Q", "monthly.Q"]
    different += ["regime.Q", "daily.H"]

    async def run() -> list[tuple[dict[str, Any], str]]:
        requests = [analyses.get(snapshot, CZ_HYDRO, i, {}) for i in different]
        requests += [analyses.get(snapshot, CZ_HYDRO, "daily.T", {}) for _ in range(3)]
        return await asyncio.gather(*requests)

    try:
        results = asyncio.run(run())
    finally:
        standin.close()

    assert [result["status"] for result, _ in results] == ["ok"] * 9
    assert results[-1] == results[-2] == results[-3]
    ran = processes(calls_log)
    assert len(ran) == len(different) + 1
    assert _most_at_once([(p["start"], p["end"]) for p in ran]) == 2


# --- the real program ------------------------------------------------------------------------


def _hydrolog() -> tuple[str, ...]:
    configured = os.environ.get("OBSERWATOR_HYDROLOG_COMMAND", "").strip()
    words = tuple(shlex.split(configured)) if configured else ("hydrolog",)
    if shutil.which(words[0]) is None:
        pytest.skip("no Hydrolog program (OBSERWATOR_HYDROLOG_COMMAND or PATH)")
    return words


@pytest.mark.hydrolog
def test_flood_frequency_is_hydrologs_own_call_on_the_same_export(
    root: Path, tmp_path: Path
) -> None:
    words = _hydrolog()
    snapshot = DataRoot(root).snapshot()
    standin = StandIn(root, words, work=tmp_path / "work")
    try:
        computed = standin.compute_analysis(snapshot, CZ_HYDRO, "flood_frequency.Q")
    finally:
        standin.close()
    export = tmp_path / "export.csv"
    export_series(
        snapshot.series["cz.chmi.hydro_daily"].version.path,
        station=CZ_HYDRO,
        output=export,
    )
    args = [*words, *computed["command"].split(), "--json"]
    for name, value in {**computed["options"], "input_file": str(export)}.items():
        text = ",".join(map(str, value)) if isinstance(value, list) else str(value)
        args += ["--" + name.replace("_", "-"), text]
    done = subprocess.run(
        args, capture_output=True, text=True, timeout=300, check=False
    )
    own = json.loads(done.stdout.strip() or done.stderr.strip().splitlines()[-1])

    assert (
        computed["inputs"][0]["export_sha256"]
        == hashlib.sha256(export.read_bytes()).hexdigest()
    )
    if computed["status"] == "ok":
        assert computed["envelope"]["result"] == own["result"]
    else:
        assert computed["error"] == own
