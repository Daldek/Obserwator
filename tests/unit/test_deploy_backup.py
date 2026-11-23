"""The deployment's backups (Nogat plan 2026-11-16-operational-series, step A4).

``deploy/obserwator-backup.sh`` takes the weekly and monthly snapshots of both
roots, run here with the real program on fixture roots.
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from obserwator.testing import build_fixture_store
from tests.contract.nogat import validate

DEPLOY = Path(__file__).resolve().parents[2] / "deploy"
BACKUP = DEPLOY / "obserwator-backup.sh"
PROGRAM = Path(sys.executable).with_name("obserwator")

posix_tools = pytest.mark.skipif(
    sys.platform != "linux"
    or not all(shutil.which(t) for t in ("bash", "rsync", "flock")),
    reason="the backup script needs Linux with bash, rsync and flock",
)


@pytest.fixture(scope="module")
def fixture_roots(tmp_path_factory):
    base = tmp_path_factory.mktemp("roots")
    build_fixture_store(base / "raw", data_root=base / "data")
    return base


@pytest.fixture
def roots(fixture_roots, tmp_path):
    for name in ("raw", "data"):
        shutil.copytree(fixture_roots / name, tmp_path / name, symlinks=True)
    (tmp_path / "target").mkdir()
    return tmp_path


def _backup(roots, *args):
    env = {
        **os.environ,
        "OBSERWATOR": str(PROGRAM),
        "OBSERWATOR_STATE_DIR": str(roots / "state"),
    }
    command = [
        "bash",
        str(BACKUP),
        "--raw-root",
        str(roots / "raw"),
        "--data-root",
        str(roots / "data"),
        "--target",
        str(roots / "target"),
        "--log-dir",
        str(roots / "logs"),
        *args,
    ]
    return subprocess.run(command, env=env, capture_output=True, text=True, check=False)


def _records(roots):
    lines = []
    for path in sorted((roots / "logs").glob("app-*.jsonl")):
        lines += [json.loads(line) for line in path.read_text("utf-8").splitlines()]
    for record in lines:
        validate(record, "record-1")
    return lines


def _snapshot(roots, kind, day):
    return roots / "target" / "obserwator" / kind / day


def _files(directory):
    return {
        p.relative_to(directory): p.stat() for p in directory.rglob("*") if p.is_file()
    }


@posix_tools
def test_a_weekly_snapshot_holds_only_the_new_files_as_new_inodes(roots):
    staged = roots / "raw" / ".incoming" / "w1"
    staged.mkdir(parents=True)
    (staged / "half-written").write_text("x")
    first = _backup(roots, "--mode", "weekly", "--date", "2026-11-08")
    assert first.returncode == 0, first.stderr
    new = roots / "raw" / "archives" / "new-version"
    new.write_bytes(b"new")
    second = _backup(roots, "--mode", "weekly", "--date", "2026-11-15")
    assert second.returncode == 0, second.stderr

    old, now = (
        _files(_snapshot(roots, "weekly", "2026-11-08")),
        _files(_snapshot(roots, "weekly", "2026-11-15")),
    )
    assert set(now) == set(old) | {Path("raw/archives/new-version")}
    assert not any(".incoming" in path.parts for path in now)
    for path, stat in now.items():
        if path == Path("raw/archives/new-version"):
            assert stat.st_nlink == 1
        else:
            assert stat.st_ino == old[path].st_ino and stat.st_nlink == 2, path
    assert _backup(roots, "--mode", "weekly", "--date", "2026-11-15").returncode == 2


@posix_tools
def test_the_monthly_full_copy_passes_its_restore_test(roots):
    done = _backup(roots, "--date", "2026-11-01")
    assert done.returncode == 0, done.stdout + done.stderr
    monthly = _snapshot(roots, "monthly", "2026-11-01")
    log = (monthly / "restore-test.log").read_text("utf-8")
    assert (
        "data: store scan ok: 4 versions (the source: 4 before the copy, 4 after it), 0 problems"
        in log
    )
    assert "data: SHA-256 ok: 4 version files match their sidecars" in log
    assert "data: series read ok:" in log
    assert "raw: store scan ok: 9 version directories, 9 versions, 0 problems" in log
    assert log.rstrip().endswith("result: passed")
    (record,) = _records(roots)
    assert (record["level"], record["event"]) == ("info", "backup_restore_test")
    assert "passed" in record["message"]
    # A monthly copy is independent; the month's next run is a weekly linked to it.
    source = roots / "raw" / "obserwator-store.json"
    assert (
        monthly / "raw" / "obserwator-store.json"
    ).stat().st_ino != source.stat().st_ino
    assert not list((roots / "target" / "obserwator").glob(".restore-test.*"))
    assert _backup(roots, "--date", "2026-11-08").returncode == 0
    weekly = _snapshot(roots, "weekly", "2026-11-08") / "raw" / "obserwator-store.json"
    assert (
        weekly.stat().st_ino
        == (monthly / "raw" / "obserwator-store.json").stat().st_ino
    )


@posix_tools
def test_a_failed_restore_test_is_recorded_and_prunes_nothing(roots):
    for day in ("2026-08-01", "2026-09-05", "2026-10-03"):
        (_snapshot(roots, "monthly", day) / "data").mkdir(parents=True)
    sidecar = next((roots / "data" / "series").rglob("series.json.meta.json"))
    Path(str(sidecar).removesuffix(".meta.json")).write_text("{}")
    done = _backup(roots, "--date", "2026-11-01", "--keep-monthly", "1")
    assert done.returncode == 1
    log = (_snapshot(roots, "monthly", "2026-11-01") / "restore-test.log").read_text(
        "utf-8"
    )
    assert "data: SHA-256 FAILED" in log and log.rstrip().endswith("result: failed")
    (record,) = _records(roots)
    assert (record["level"], record["event"]) == ("error", "backup_restore_test")
    assert len(list((roots / "target" / "obserwator" / "monthly").iterdir())) == 4


@posix_tools
def test_retention_deletes_only_whole_old_snapshot_directories(roots, tmp_path):
    outside = tmp_path / "outside"
    (outside / "2026-01-04").mkdir(parents=True)
    (outside / "2026-01-04" / "keep").write_text("x")
    weekly = roots / "target" / "obserwator" / "weekly"
    monthly = roots / "target" / "obserwator" / "monthly"
    weekly.mkdir(parents=True)
    (weekly / "2026-01-04").symlink_to(outside / "2026-01-04")
    (weekly / "notes").mkdir()
    for day in ("2026-09-05", "2026-10-03"):
        (monthly / day / "raw").mkdir(parents=True)
        (monthly / day / "data").mkdir()
        (monthly / day / "raw" / "file").write_text("x")
    for day in ("2026-11-08", "2026-11-15", "2026-11-22"):
        done = _backup(
            roots,
            "--mode",
            "weekly",
            "--date",
            day,
            "--keep-weekly",
            "2",
            "--keep-monthly",
            "1",
        )
        assert done.returncode == 0, done.stderr
    assert sorted(p.name for p in weekly.iterdir()) == [
        "2026-01-04",
        "2026-11-15",
        "2026-11-22",
        "notes",
    ]
    assert sorted(p.name for p in monthly.iterdir()) == ["2026-10-03"]
    assert (outside / "2026-01-04" / "keep").exists()
    assert (roots / "raw" / "obserwator-store.json").exists()


@posix_tools
def test_a_full_copy_that_would_fill_the_share_is_refused(roots):
    done = _backup(roots, "--date", "2026-12-06", "--min-free-percent", "100")
    assert done.returncode == 3
    assert not _snapshot(roots, "monthly", "2026-12-06").exists()
    assert not list((roots / "target" / "obserwator" / "monthly").iterdir())
    (record,) = _records(roots)
    assert (record["level"], record["event"]) == ("error", "backup_refused")
    assert "below 100 %" in record["message"]
    # A weekly linked to a snapshot copies no full and is not checked.
    for tree in ("raw", "data"):
        (_snapshot(roots, "monthly", "2026-12-06") / tree).mkdir(parents=True)
    linked = _backup(
        roots, "--mode", "weekly", "--date", "2026-12-13", "--min-free-percent", "100"
    )
    assert linked.returncode == 0, linked.stderr


@posix_tools
def test_a_root_without_its_marker_is_never_backed_up(roots):
    (roots / "raw" / "obserwator-store.json").unlink()
    done = _backup(roots, "--mode", "weekly")
    assert done.returncode == 2
    assert "is it mounted" in done.stderr
    assert not list((roots / "target").iterdir())
