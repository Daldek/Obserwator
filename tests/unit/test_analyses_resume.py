"""Resuming an interrupted ``analyses build`` (Nogat ECO-073; ADR-016, erratum of 2026-11-21).

A build that ends before it publishes keeps the stations it computed in its staging
directory ``.incoming/<host>_<pid>_<token>/`` of the data root; the next build takes
them by hard links, without a Hydrolog call, where the record is whole and the
station's inputs are unchanged, and computes the rest. Hydrolog's program is the
recorded fake of ``tests/fixtures/hydrolog``.
"""

import errno
import json
import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

import pytest

from obserwator import build_analyses, build_series, check_analyses, get_provider
from obserwator.messages import message
from obserwator.store import analyses
from tests.contract.support import PRECIP, load, snapshot, stamps, use_fake_hydrolog
from tests.unit.test_analyses import FROZEN_AT, VERSION, called, copy, records

# The installed command in a process of its own, one station per Hydrolog process
# (`_CHUNK_STATIONS`), so that it stages the stations one by one.
KILLED_BUILD = """\
import sys
from obserwator.cli.main import app
from obserwator.store import analyses
analyses._CHUNK_STATIONS = 1
sys.argv = ["obserwator", *sys.argv[1:]]
app()
"""
LIMIT = 60.0


@pytest.fixture(autouse=True)
def fake_hydrolog(monkeypatch):
    """Hydrolog's program is the fake, answering at once with its own version."""
    for name in (
        "FAKE_HYDROLOG_VERSION",
        "FAKE_HYDROLOG_SLEEP",
        "FAKE_HYDROLOG_FAIL",
        "FAKE_HYDROLOG_LOG",
    ):
        monkeypatch.delenv(name, raising=False)
    use_fake_hydrolog(monkeypatch)


@pytest.fixture(autouse=True)
def temporary(monkeypatch, tmp_path):
    """The temporary directory (``TMPDIR``) of the test: the scratch directories go here."""
    directory = tmp_path / "tmp"
    directory.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(directory))
    return directory


@pytest.fixture
def batches(monkeypatch, tmp_path):
    """The batches the fake ran since the last look: each its arguments and calls."""
    log = tmp_path / "hydrolog.jsonl"
    monkeypatch.setenv("FAKE_HYDROLOG_LOG", str(log))

    def runs():
        found = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
        log.unlink(missing_ok=True)
        return [json.loads(line) for line in found]

    return runs


@pytest.fixture
def frozen(monkeypatch):
    """The clock of the analyses: computed and built at one moment."""

    class Frozen(datetime):
        @classmethod
        def now(cls, tz=None):
            return FROZEN_AT.astimezone(tz)

    monkeypatch.setattr("obserwator.store.analyses.datetime", Frozen)


def staged(directory: Path) -> set[str]:
    """The stations whose record a staging directory holds whole (with its line feed)."""
    found = set()
    for path in directory.glob("stations/*.json"):
        content = path.read_bytes()
        try:
            json.loads(content)
        except ValueError:
            continue
        if content.endswith(b"\n"):
            found.add(path.stem)
    return found


def interrupt(root: Path) -> Path:
    """
    Cancel a build of ``root`` once it has staged stations; the directory it keeps.

    IMGW-PIB's stations are one Hydrolog process, so all of them are staged
    before the build sees the cancellation, and ČHMÚ is never reached.
    """
    done: list[str] = []

    def progress(update):
        if update.status == "computed":
            done.append(update.message)

    report = build_analyses(root, on_progress=progress, cancel=lambda: bool(done))

    assert report.status == "cancelled"
    (leftover,) = (root / ".incoming").iterdir()
    assert staged(leftover) and not (root / "analyses").exists()
    return leftover


def linked(version: Path, leftover: Path, code: str) -> bool:
    """Whether every file of a station in ``version`` is the leftover's own file."""
    record = load(leftover / "stations" / f"{code}.json")
    names = [f"stations/{code}.json", *(item["file"] for item in record["results"])]
    return all(os.path.samefile(version / name, leftover / name) for name in names)


def test_a_resumed_build_computes_only_the_rest_and_stores_the_uninterrupted_version(
    tmp_path, fixture_root, monkeypatch, frozen, batches
):
    # One scratch directory for every build: the lines echo its paths.
    use_fake_hydrolog(monkeypatch, tmp_path / "scratch")
    whole = copy(fixture_root, tmp_path / "whole")
    expected = build_analyses(whole)
    imgw, chmu = (set(records(item.version.parent)) for item in expected.providers)
    root = copy(fixture_root, tmp_path / "store")
    done = []

    def ctrl_c(update):  # the second Ctrl+C, after two stations were staged
        if update.status == "computed":
            done.append(update.message)
            if len(done) == 2:
                raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        build_analyses(root, on_progress=ctrl_c)
    (leftover,) = (root / ".incoming").iterdir()
    taken, kept = staged(leftover), snapshot(leftover)
    assert len(taken) == 2 and taken < imgw
    batches()

    report = build_analyses(root)

    first, second = report.providers
    assert (first.status, first.resumed, first.computed, first.carried) == (
        "new",
        2,
        len(imgw) - 2,
        0,
    )
    assert (second.resumed, second.computed) == (0, len(chmu))
    assert first.stations == first.computed + first.carried + first.resumed
    assert called(batches()) == (imgw - taken) | chmu  # Hydrolog only for the rest
    assert snapshot(root / "analyses") == snapshot(whole / "analyses")
    assert [(item.results_ok, item.results_failed) for item in report.providers] == [
        (item.results_ok, item.results_failed) for item in expected.providers
    ]
    assert all(linked(first.version.parent, leftover, code) for code in taken)
    # The leftover is another build's: never changed or removed (younger than a day).
    assert snapshot(leftover) == kept
    assert list((root / ".incoming").iterdir()) == [leftover]


@pytest.mark.parametrize("change", ["series version", "registry", "Hydrolog version"])
def test_a_station_whose_inputs_changed_since_the_interruption_is_computed_again(
    change, tmp_path, fixture_root, fixture_raw_root, monkeypatch, batches
):
    root = copy(fixture_root, tmp_path / "store")
    leftover = interrupt(root)
    taken = staged(leftover)
    if change == "series version":
        # The late 1995 archive of the fixture joins the precipitation series: a new
        # version for every station reading it, whether its station file changed or not.
        assert build_series(root, raw_root=fixture_raw_root, dataset=PRECIP).status == (
            "new"
        )
        stale = {
            code
            for code in taken
            if PRECIP
            in {
                item["dataset"]
                for item in load(leftover / "stations" / f"{code}.json")["inputs"]
            }
        }
        assert stale and stale < taken
    elif change == "registry":
        monkeypatch.setattr(analyses, "definitions_digest", lambda: "0" * 64)
        stale = taken
    else:
        monkeypatch.setenv("FAKE_HYDROLOG_VERSION", "1.0.1")
        stale = taken
    batches()

    imgw = build_analyses(root).providers[0]

    assert (imgw.status, imgw.resumed, imgw.computed) == (
        "new",
        len(taken - stale),
        len(stale),
    )
    assert called(batches()) & taken == stale
    assert all(linked(imgw.version.parent, leftover, code) for code in taken - stale)


@pytest.mark.parametrize(
    "damage",
    [
        "a result file changed",
        "half a record",
        "a record without its final line feed",
        "a result named outside its station",
        "a result without its SHA-256",
    ],
)
def test_a_damaged_staged_station_is_computed_again_and_its_leftover_kept_as_it_is(
    damage, tmp_path, fixture_root, batches
):
    root = copy(fixture_root, tmp_path / "store")
    leftover = interrupt(root)
    taken = staged(leftover)
    code = min(taken)
    path = leftover / "stations" / f"{code}.json"
    content = path.read_bytes()
    record = json.loads(content)
    if damage == "a result file changed":
        result = leftover / record["results"][0]["file"]
        result.write_bytes(result.read_bytes()[:-1] + b" \n")
    elif damage == "half a record":
        path.write_bytes(content[: len(content) // 2])
    elif damage == "a record without its final line feed":  # parses, yet not whole
        path.write_bytes(content[:-1])
    else:
        if damage == "a result without its SHA-256":
            del record["results"][0]["sha256"]
        else:
            record["results"][0]["file"] = "../../outside.json"
        path.write_bytes(json.dumps(record).encode("utf-8") + b"\n")
    kept, before = snapshot(leftover), stamps(root)
    batches()

    planned = check_analyses(root)

    assert stamps(root) == before  # read and hashed, never linked
    assert planned.actions[0].detail == message(
        "analyses.plan_build",
        provider=get_provider("IMGW").short_name,
        computed=1,
        carried=0,
        resumed=len(taken) - 1,
        version=VERSION,
    )
    imgw = build_analyses(root).providers[0]
    assert (imgw.resumed, imgw.computed) == (len(taken) - 1, 1)
    assert called(batches()) & taken == {code}
    assert snapshot(leftover) == kept


def test_a_leftover_older_than_a_day_is_taken_before_the_cleanup_removes_it(
    tmp_path, fixture_root, batches
):
    root = copy(fixture_root, tmp_path / "store")
    leftover = interrupt(root)
    taken, kept = staged(leftover), snapshot(leftover)
    old = time.time() - 25 * 60 * 60
    os.utime(leftover, (old, old))
    batches()
    notices = []

    imgw = build_analyses(root, on_notice=notices.append).providers[0]

    assert (imgw.resumed, imgw.computed) == (len(taken), 0)
    assert not called(batches()) & taken
    assert not leftover.exists()
    assert [
        notice.message for notice in notices if notice.code == "leftover_incoming"
    ] == [message("writer.abandoned_staging_removed", name=leftover.name)]
    # The linked files outlive the leftover: the version holds its stations as staged.
    version = snapshot(imgw.version.parent)
    assert {
        name: sha for name, sha in version.items() if name.startswith("stations")
    } == (kept)


def test_a_build_ended_by_an_error_keeps_its_stations_and_never_its_scratch(
    tmp_path, fixture_root, monkeypatch, temporary, batches
):
    root = copy(fixture_root, tmp_path / "store")

    def full(*args, **kwargs):
        raise OSError(errno.ENOSPC, "No space left on device")

    with monkeypatch.context() as patch:
        patch.setattr(analyses, "_publish", full)
        with pytest.raises(OSError):
            build_analyses(root)
    assert list(temporary.iterdir()) == []
    (leftover,) = (root / ".incoming").iterdir()
    taken = staged(leftover)
    batches()

    imgw = build_analyses(root).providers[0]

    assert taken and (imgw.resumed, imgw.computed) == (len(taken), 0)
    assert not called(batches()) & taken


def test_the_stations_of_a_killed_build_are_resumed(
    tmp_path, fixture_root, temporary, batches
):
    root = copy(fixture_root, tmp_path / "store")
    (tmp_path / "nogat.toml").write_text("", encoding="utf-8")
    environment = {
        **os.environ,
        "FAKE_HYDROLOG_SLEEP": "1",
        "NOGAT_CONFIG": str(tmp_path / "nogat.toml"),
        "TMPDIR": str(temporary),
    }
    errors = tmp_path / "stderr"
    with errors.open("wb") as stream:
        process = subprocess.Popen(
            [sys.executable, "-c", KILLED_BUILD, "analyses", "build", "--root", root],
            stdout=subprocess.DEVNULL,
            stderr=stream,
            env=environment,
            cwd=tmp_path,
        )
    try:
        deadline = time.monotonic() + LIMIT
        while not any(staged(path) for path in root.glob(".incoming/*")):
            assert process.poll() is None and time.monotonic() < deadline, (
                errors.read_text(encoding="utf-8")
            )
            time.sleep(0.02)
    finally:
        process.kill()  # SIGKILL: no finally of the build runs
        process.wait()
    (leftover,) = (root / ".incoming").iterdir()
    taken, kept = staged(leftover), snapshot(leftover)
    batches()

    imgw = build_analyses(root).providers[0]

    assert imgw.resumed == len(taken) >= 1
    assert imgw.computed == imgw.stations - len(taken)
    assert not called(batches()) & taken
    assert snapshot(leftover) == kept
