"""The deployment's timers (Nogat plan 2026-11-16-operational-series, step A2).

``deploy/obserwator-jobs.sh`` runs the night, the telemetry and the hourly poll of
the units in ``deploy/systemd/``. The jobs run with a stub of the program: the
night's catch-up decides the days each harvest asks for and the hourly series it
builds (ADR-031), and the telemetry builds the months whose zips the stub's
envelope says it stored.
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
if [ -n "$STUB_OUT" ]; then
  case "$*" in "store sync --datasets pl.imgw.hydro_telemetry"*) cat "$STUB_OUT" ;; esac
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


def _job(tmp_path, job, *args, fail="", code=10, out=""):
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
        "STUB_LOG": str(log),
        "STUB_FAIL": fail,
        "STUB_CODE": str(code),
        "STUB_OUT": out,
    }
    done = subprocess.run(
        ["bash", str(JOBS), job, *args],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    calls = log.read_text("utf-8").splitlines() if log.exists() else []
    return done, calls


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
        "store sync --datasets pl.pig.groundwater_operational --pace-until 02:45"
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
    # After the sealing, the hourly series: every month of PIG-PIB's captures, then
    # the months of each other harvest's days.
    assert calls[4] == "series build --dataset pl.pig.groundwater_subdaily"
    assert calls[5:] == [
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
    assert calls[5:] == [
        "series build --dataset pl.imgw.hydro_subdaily"
        f" --start {yesterday - timedelta(days=2)} --end {yesterday}",
        "series build --dataset cz.chmu.hydro_subdaily"
        f" --start {_utc_today() - timedelta(days=40)} --end {yesterday}",
    ]

    # Harvested already (a catch-up after a run by hand): no request and no build of
    # those, PIG-PIB's harvest from its watermark, the sealing and its series run.
    done, calls = _night(tmp_path)
    assert done.returncode == 0
    assert len(calls) == 3 and calls[1].startswith(
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
    assert len(calls) == 7
    assert calls[5] == (
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
    assert all(call.endswith("--check") for call in calls) and len(calls) == 7
    assert not _stamp(tmp_path, "pl.imgw.hydro_operational").exists()
    done, calls = _night(tmp_path, "--start", "2026-13-01")
    assert done.returncode == 64 and not calls


@posix_tools
def test_the_telemetry_builds_the_hourly_series_of_each_month_it_stored(tmp_path):
    # The sync's envelope names the zips it stored: those months are built again, so
    # their telemetry replaces hydro-back's hours; an unchanged zip builds nothing.
    items = [
        ("2026/Hydro_2026-10.zip", "new"),
        ("2026/Hydro_2026-09.zip", "unchanged"),
        ("2026/Hydro_2026-02.zip", "new"),
    ]
    envelope = {
        "schema": "obserwator-result/1",
        "status": "ok",
        "result": {
            "schema": "obserwator-sync-report/1",
            "items": [
                {"slot": f"archive:pl.imgw.hydro_telemetry:{name}", "status": status}
                for name, status in items
            ],
        },
    }
    out = tmp_path / "sync.json"
    out.write_text(json.dumps(envelope) + "\n", "utf-8")
    done, calls = _job(tmp_path, "telemetry", out=str(out))
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
    done, calls = _job(tmp_path, "telemetry", "--check", out=str(out))
    assert done.returncode == 0
    assert not [call for call in calls if call.startswith("series build")]


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
