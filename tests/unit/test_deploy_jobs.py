"""The deployment's timers (Nogat plan 2026-11-16-operational-series, step A2).

``deploy/obserwator-jobs.sh`` runs the night, the telemetry and the hourly poll of
the units in ``deploy/systemd/``. The jobs run with a stub of the program: the
night's catch-up decides the days each harvest asks for and the hourly series it
builds (ADR-031), and the telemetry builds the months whose zips the stub's
envelope says it stored, and PIG-PIB's catalog and readings series (ADR-035).
"""

import json
import os
import re
import shutil
import subprocess
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from obserwator.datasets import CAPTURE_SCOPE, datasets

DEPLOY = Path(__file__).resolve().parents[2] / "deploy"
JOBS = DEPLOY / "obserwator-jobs.sh"
PROGRAM = Path(sys.executable).with_name("obserwator")

posix_tools = pytest.mark.skipif(
    sys.platform != "linux" or not shutil.which("bash"),
    reason="the deployment scripts need Linux with bash",
)
STUB = """\
#!/bin/sh
printf '%s\\n' "$*" >> "$STUB_LOG"
if [ "$1 $2 $3" = "store sync --datasets" ] && [ -f "$STUB_OUT/$4.json" ]; then
  cat "$STUB_OUT/$4.json"
fi
if [ -n "$STUB_FAIL" ]; then
  case "$*" in *"$STUB_FAIL"*) exit "$STUB_CODE" ;; esac
fi
exit 0
"""


def _utc_today() -> date:
    return datetime.now(UTC).date()


# --- the night ----------------------------------------------------------------


def _night_datasets() -> tuple[list[str], list[str]]:
    text = JOBS.read_text("utf-8")
    watermarked = re.search(r'^WATERMARKED="(\S+) ', text, re.MULTILINE)
    block = re.search(r"^HARVESTS=\((.*?)^\)", text, re.DOTALL | re.MULTILINE)
    sealed = re.search(r"^SEALED=(\S+)$", text, re.MULTILINE)
    assert watermarked and block and sealed
    harvested = [watermarked.group(1)] + [
        line.split()[0].strip('"')
        for line in block.group(1).split("\n")
        if line.strip()
    ]
    return harvested, sealed.group(1).split(",")


def test_the_night_seals_every_served_capture_dataset_once():
    # A capture dataset the night leaves out is never sealed by the timers; a
    # declared one makes the sealing call fail (unknown dataset).
    harvested, sealed = _night_datasets()
    served = {d.key for d in datasets() if d.archive_scope == CAPTURE_SCOPE}
    assert harvested == [
        "pl.pig.groundwater_operational",
        "pl.imgw.hydro_operational",
        "cz.chmu.hydro_recent",
    ]
    assert not set(harvested) & set(sealed)
    assert len(sealed) == len(set(sealed))
    assert set(harvested) | set(sealed) == served


def _job(tmp_path, job, *args, fail="", code=10, weekday=None):
    stub = tmp_path / "obserwator"
    if not stub.exists():
        stub.write_text(STUB, "utf-8")
        stub.chmod(0o755)
    log = tmp_path / "calls.txt"
    log.unlink(missing_ok=True)
    env = {
        **os.environ,
        "OBSERWATOR": str(stub),
        "OBSERWATOR_STATE_DIR": str(tmp_path / "state"),
        "OBSERWATOR_RAW_ROOT": str(tmp_path / "raw"),
        "STUB_LOG": str(log),
        "STUB_FAIL": fail,
        "STUB_CODE": str(code),
        "STUB_OUT": str(tmp_path / "out"),
    }
    if weekday is not None:
        # `date +%u` answers the day of the week asked for; any other call is date's.
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir(exist_ok=True)
        shim = bin_dir / "date"
        shim.write_text(
            f'#!/bin/sh\n[ "$1" = +%u ] && {{ echo {weekday}; exit 0; }}\n'
            f'exec {shutil.which("date")} "$@"\n',
            "utf-8",
        )
        shim.chmod(0o755)
        env["PATH"] = f"{bin_dir}{os.pathsep}{env['PATH']}"
    done = subprocess.run(
        ["bash", str(JOBS), job, *args],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    calls = log.read_text("utf-8").splitlines() if log.exists() else []
    return done, calls


def _answers(tmp_path, datasets, items):
    """The stub's ``store sync --json`` envelope for ``--datasets <datasets>``."""
    envelope = {
        "schema": "obserwator-result/1",
        "status": "ok",
        "result": {
            "schema": "obserwator-sync-report/1",
            "items": [{"slot": slot, "status": status} for slot, status in items],
        },
    }
    out = tmp_path / "out"
    out.mkdir(exist_ok=True)
    (out / f"{datasets}.json").write_text(json.dumps(envelope) + "\n", "utf-8")


def _night(tmp_path, *args, fail="", code=10):
    return _job(tmp_path, "night", *args, fail=fail, code=code)


def _stamp(tmp_path, dataset):
    return tmp_path / "state" / "obserwator" / "timers" / f"{dataset}.harvested"


def _harvest_days(calls, dataset):
    (call,) = [c for c in calls if f"--datasets {dataset} " in c]
    found = re.search(r"--start (\S+) --end (\S+)", call)
    assert found, call
    return found.group(1), found.group(2)


@posix_tools
def test_the_night_harvests_from_the_day_after_the_last_whole_harvest(tmp_path):
    yesterday = _utc_today() - timedelta(days=1)
    done, calls = _night(tmp_path)
    assert done.returncode == 0, done.stdout
    # PIG-PIB's harvest first, from its watermark: no days, no stamp (ADR-035).
    assert calls[0] == (
        "store sync --datasets pl.pig.groundwater_operational --pace-until 02:45 --json"
    )
    assert calls[1].startswith(
        "store sync --datasets pl.imgw.hydro_operational --pace-until 05:00"
    )
    assert calls[2].startswith(
        "store sync --datasets cz.chmu.hydro_recent --pace-until 06:30"
    )
    assert calls[3].startswith("store sync --datasets pl.imgw.hydro_current,")
    assert _harvest_days(calls, "pl.imgw.hydro_operational") == (str(yesterday),) * 2
    assert _stamp(tmp_path, "cz.chmu.hydro_recent").read_text().strip() == str(
        yesterday
    )
    assert not _stamp(tmp_path, "pl.pig.groundwater_operational").exists()
    # After the sealing, the hourly series of the months of each other harvest's days;
    # PIG-PIB's harvest stored no capture, so its series is not built.
    assert calls[4:] == [
        f"series build --dataset {series} --start {yesterday} --end {yesterday}"
        for series in ("pl.imgw.hydro_subdaily", "cz.chmu.hydro_subdaily")
    ]

    # Missed nights: from the day after the stamp; a stamp beyond the source's
    # reach starts at the earliest day it still answers for.
    _stamp(tmp_path, "pl.imgw.hydro_operational").write_text(
        f"{yesterday - timedelta(days=3)}\n"
    )
    _stamp(tmp_path, "cz.chmu.hydro_recent").write_text("2020-01-01\n")
    done, calls = _night(tmp_path)
    assert done.returncode == 0
    assert _harvest_days(calls, "pl.imgw.hydro_operational") == (
        str(yesterday - timedelta(days=2)),
        str(yesterday),
    )
    assert _harvest_days(calls, "cz.chmu.hydro_recent") == (
        str(_utc_today() - timedelta(days=40)),
        str(yesterday),
    )
    assert "beyond the source's reach" in done.stdout
    assert calls[4:] == [
        "series build --dataset pl.imgw.hydro_subdaily"
        f" --start {yesterday - timedelta(days=2)} --end {yesterday}",
        "series build --dataset cz.chmu.hydro_subdaily"
        f" --start {_utc_today() - timedelta(days=40)} --end {yesterday}",
    ]

    # Harvested already (a catch-up after a run by hand): no request and no build of
    # those; PIG-PIB's harvest from its watermark and the sealing run.
    done, calls = _night(tmp_path)
    assert done.returncode == 0
    assert len(calls) == 2 and calls[1].startswith(
        "store sync --datasets pl.imgw.hydro_current,"
    )


@posix_tools
def test_a_failed_harvest_is_asked_again_and_the_night_goes_on(tmp_path):
    yesterday = _utc_today() - timedelta(days=1)
    before = str(yesterday - timedelta(days=2))
    _stamp(tmp_path, "x").parent.mkdir(parents=True)
    for dataset in ("pl.imgw.hydro_operational", "cz.chmu.hydro_recent"):
        _stamp(tmp_path, dataset).write_text(before + "\n")
    done, calls = _night(tmp_path, fail="pl.imgw.hydro_operational", code=10)
    # The partial harvest keeps its stamp, so the next night asks for its days
    # again; the ČHMÚ harvest, the sealing and the hourly series of what it got still
    # run; the exit is the failure's.
    assert done.returncode == 10
    assert len(calls) == 6
    assert calls[4] == (
        "series build --dataset pl.imgw.hydro_subdaily"
        f" --start {yesterday - timedelta(days=1)} --end {yesterday}"
    )
    assert _stamp(tmp_path, "pl.imgw.hydro_operational").read_text().strip() == before
    assert _stamp(tmp_path, "cz.chmu.hydro_recent").read_text().strip() == str(
        yesterday
    )


@posix_tools
def test_a_checked_night_records_no_harvest(tmp_path):
    done, calls = _night(tmp_path, "--check")
    assert done.returncode == 0
    assert all(call.endswith("--check") for call in calls) and len(calls) == 6
    assert not _stamp(tmp_path, "pl.imgw.hydro_operational").exists()
    done, calls = _night(tmp_path, "--start", "2026-13-01")
    assert done.returncode == 64 and not calls


PIG_HARVEST = "pl.pig.groundwater_operational"


def _capture(tmp_path, day, period):
    """
    A capture version of PIG-PIB's harvest whose sidecar names ``period``.

    Its path relative to the raw root, as the envelope of ``store sync --json`` gives it.
    """
    version = f"archives/versions/mwp_auto/MapServer/{day}/{day}_0/{day}.jsonl.gz"
    path = tmp_path / "raw" / version
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"")
    capture = {"answers": 12} if period is None else {"answers": 12, "period": period}
    meta = {"schema": "obserwator-meta/1", "extra": {"capture": capture}}
    Path(f"{path}.meta.json").write_text(json.dumps(meta), "utf-8")
    return version


def _harvested(tmp_path, *captures):
    """The stub's envelope of PIG-PIB's harvest: ``(day, status, period)`` each."""
    items = [
        {
            "slot": f"archive:{PIG_HARVEST}:{day}.jsonl.gz",
            "status": status,
            "version": _capture(tmp_path, day, period),
        }
        for day, status, period in captures
    ]
    envelope = {"schema": "obserwator-result/1", "result": {"items": items}}
    out = tmp_path / "out"
    out.mkdir(exist_ok=True)
    (out / f"{PIG_HARVEST}.json").write_text(json.dumps(envelope) + "\n", "utf-8")


def _pig_builds(calls):
    return [c for c in calls if c.startswith("series build --dataset pl.pig.")]


@posix_tools
def test_the_night_builds_pig_pibs_hourly_months_from_its_new_captures(tmp_path):
    # The night's capture and a correction of the day before hold rows from 30
    # October; the imported backfill, unchanged, reaches back to 2000 and is left out:
    # the build starts at the new rows' first day, never at the captures' first month.
    _harvested(
        tmp_path,
        ("2026-11-24", "unchanged", ["2000-01-02", "2026-07-20"]),
        ("2026-11-26", "new", ["2026-10-30", "2026-11-26"]),
        ("2026-11-27", "new", ["2026-11-08", "2026-11-27"]),
    )
    done, calls = _night(tmp_path)
    assert done.returncode == 0, done.stdout
    built = [c for c in calls if c.startswith("series build")]
    assert built[0] == (
        "series build --dataset pl.pig.groundwater_subdaily --start 2026-10-30"
    )
    assert calls.index(built[0]) == 4  # after the sealing, before the other series
    # A capture whose rows have no hour, or a checked night: nothing to build.
    _harvested(tmp_path, ("2026-11-28", "new", None))
    done, calls = _night(tmp_path)
    assert done.returncode == 0 and not _pig_builds(calls)
    _harvested(tmp_path, ("2026-11-27", "new", ["2026-11-08", "2026-11-27"]))
    done, calls = _night(tmp_path, "--check")
    assert done.returncode == 0 and not _pig_builds(calls)


@posix_tools
def test_the_telemetry_builds_the_hourly_series_of_each_month_it_stored(tmp_path):
    # The sync's envelope names the zips it stored: those months are built again, so
    # their telemetry replaces hydro-back's hours; an unchanged zip builds nothing.
    items = [
        ("2026/Hydro_2026-10.zip", "new"),
        ("2026/Hydro_2026-09.zip", "unchanged"),
        ("2026/Hydro_2026-02.zip", "new"),
    ]
    _answers(
        tmp_path,
        "pl.imgw.hydro_telemetry",
        [(f"archive:pl.imgw.hydro_telemetry:{name}", status) for name, status in items],
    )
    done, calls = _job(tmp_path, "telemetry")
    assert done.returncode == 0, done.stdout
    assert calls[0].startswith("store sync --datasets pl.imgw.hydro_telemetry --years")
    assert calls[0].endswith(" --json")
    built = [call for call in calls if call.startswith("series build")]
    assert built == [
        "series build --dataset pl.imgw.hydro_subdaily"
        " --start 2026-10-01 --end 2026-10-31",
        "series build --dataset pl.imgw.hydro_subdaily"
        " --start 2026-02-01 --end 2026-02-28",
    ]
    # A checked run plans the sync only: no zip was stored.
    done, calls = _job(tmp_path, "telemetry", "--check")
    assert done.returncode == 0
    assert not [call for call in calls if call.startswith("series build")]


STATIONS = "pl.pig.groundwater_stations"
READINGS = "pl.pig.groundwater_readings"
MONDAYS = "pl.pig.groundwater_chemistry,pl.pig.groundwater_watchlist"
POINTS = f"archive:{STATIONS}:MWP_points.jsonl.gz"
OCTOBER = f"archive:{READINGS}:MWP_2026-10.jsonl.gz"


def _pig_calls(calls):
    return [call for call in calls if "pig" in call or "PIG" in call]


@posix_tools
def test_the_telemetry_asks_pig_pib_every_day_and_its_tables_on_mondays(tmp_path):
    # The readings exist at the source for one month: asked every day, the points
    # in a call of their own (a station source); chemistry and watch list Mondays.
    _answers(tmp_path, STATIONS, [(POINTS, "unchanged")])
    _answers(tmp_path, READINGS, [(OCTOBER, "unchanged")])
    done, calls = _job(tmp_path, "telemetry", weekday=2)
    assert done.returncode == 0, done.stdout
    # The points are held: the catalog takes the night's automatic points; the
    # readings series is not rebuilt without a new version.
    assert _pig_calls(calls) == [
        f"store sync --datasets {STATIONS} --json",
        f"store sync --datasets {READINGS} --json",
        "store catalog --provider PIG",
    ]
    _answers(tmp_path, f"{READINGS},{MONDAYS}", [(OCTOBER, "unchanged")])
    done, calls = _job(tmp_path, "telemetry", weekday=1)
    assert _pig_calls(calls)[1] == f"store sync --datasets {READINGS},{MONDAYS} --json"


@posix_tools
@pytest.mark.parametrize(
    ("points", "readings", "built"),
    [
        # A new month, or the month republished: the series; the points held.
        (
            "unchanged",
            "new",
            ["store catalog --provider PIG", f"series build --dataset {READINGS}"],
        ),
        # New points: the catalog, and the series, whose H_asl reads them.
        (
            "new",
            "unchanged",
            ["store catalog --provider PIG", f"series build --dataset {READINGS}"],
        ),
        # The points' sync failed: no catalog (it would fail without a points
        # version); a new month still builds the series.
        ("failed", "new", [f"series build --dataset {READINGS}"]),
        ("failed", "failed", []),
    ],
)
def test_the_telemetry_builds_pig_pib_on_what_its_syncs_stored(
    tmp_path, points, readings, built
):
    _answers(tmp_path, STATIONS, [(POINTS, points)])
    _answers(tmp_path, READINGS, [(OCTOBER, readings)])
    done, calls = _job(tmp_path, "telemetry", weekday=3)
    assert done.returncode == 0, done.stdout
    assert _pig_calls(calls)[2:] == built
    # A checked run plans the syncs only.
    done, calls = _job(tmp_path, "telemetry", "--check", weekday=3)
    assert _pig_calls(calls) == [
        f"store sync --datasets {STATIONS} --json --check",
        f"store sync --datasets {READINGS} --json --check",
    ]


# --- the units ------------------------------------------------------------------


@pytest.mark.skipif(not shutil.which("systemd-analyze"), reason="needs systemd-analyze")
def test_every_unit_verifies_once_its_paths_are_given(tmp_path):
    values = {
        "@OBSERWATOR@": str(PROGRAM),
        "@DEPLOY_DIR@": str(DEPLOY),
        "@RAW_ROOT@": str(tmp_path / "raw"),
        "@DATA_ROOT@": str(tmp_path / "data"),
        "@STATE_DIR@": str(tmp_path / "state"),
        "@BACKUP_TARGET@": str(tmp_path / "backup"),
    }
    units = sorted((DEPLOY / "systemd").iterdir())
    assert {u.name for u in units} == {
        f"obserwator-{name}.{kind}"
        for name in ("night", "telemetry", "current", "backup")
        for kind in ("service", "timer")
    }
    for unit in units:
        text = unit.read_text("utf-8")
        for placeholder, value in values.items():
            text = text.replace(placeholder, value)
        assert not re.search(r"^[^#].*@[A-Z_]+@", text, re.MULTILINE), unit.name
        (tmp_path / unit.name).write_text(text, "utf-8")
    done = subprocess.run(
        ["systemd-analyze", "verify", *(str(tmp_path / u.name) for u in units)],
        capture_output=True,
        text=True,
        check=False,
    )
    # verify also loads the host's own units (default.target and what it pulls in),
    # and a runner's image may warn about those (`CPUAccounting=` removed in systemd
    # 258); only the lines about the units under test count.
    names = [str(tmp_path), *(u.name for u in units)]
    ours = [
        line
        for line in (done.stdout + done.stderr).splitlines()
        if any(name in line for name in names)
    ]
    assert done.returncode == 0 and not ours, done
