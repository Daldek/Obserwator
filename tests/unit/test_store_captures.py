"""Sealing the capture spool into archive versions and reading them (ADR-030 D3, D6, D7).

``store sync`` of a capture dataset seals every closed UTC day of the spool
(``<state_dir>/obserwator/captures/<dataset>/<YYYY-MM-DD>/``) into one version of the
slot ``archive:<key>:<YYYY-MM-DD>.jsonl.gz``, whose directory may lie in the slot of a
station source (``api/data/hydro``: ``pl.imgw.hydro_now``). Every test has its own
spool (``OBSERWATOR_STATE_DIR``), ``nogat.toml`` and clock (``obserwator.captures._now``,
noon of ``TODAY``); the answers reach the spool by `obserwator.captures.write_spool`,
as the library's requests keep them.
"""

import gzip
import hashlib
import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
import respx

from obserwator import captures
from obserwator.captures import Spooled, spool_root, write_spool
from obserwator.commands import run_command
from obserwator.datasets import _capture_from_path, archive_files, get_dataset
from obserwator.exceptions import ObserwatorValidationError
from obserwator.messages import message
from obserwator.providers.base import Answer
from obserwator.store import (
    build_catalog,
    check_store,
    current_version,
    init_store,
    iter_store,
    sync_store,
    writer,
)
from obserwator.store.captures import decode, encode
from obserwator.testing import _recorded_http, build_fixture_store
from tests.unit.test_store_sync import H2024, V1, store_local

HYDRO = "pl.imgw.hydro_current"
METEO = "pl.imgw.meteo_current"
STATES = "pl.imgw.hydro_states_current"
HYDRO_URL = "https://danepubliczne.imgw.pl/api/data/hydro"
METEO_URL = "https://danepubliczne.imgw.pl/api/data/meteo"
# The source of hydro.imgw.pl's map, and the address the hourly poll asks.
STATES_SOURCE = "https://hydro-back.imgw.pl/map/stations/hydrologic"
ADDRESSES = {
    HYDRO: HYDRO_URL,
    METEO: METEO_URL,
    STATES: f"{STATES_SOURCE}?onlyMainStations=false",
}
HYDRO_NOW = "archive:pl.imgw.hydro_now:hydro"
METEO_NOW = "archive:pl.imgw.meteo_now:meteo"
DAY = date(2026, 11, 21)
TODAY = DAY + timedelta(days=1)


def at(day, clock):
    """The UTC instant of a day's ``clock`` (``HH:MM:SS[.ffffff]``)."""
    return datetime.fromisoformat(f"{day.isoformat()}T{clock}").replace(tzinfo=UTC)


def set_clock(monkeypatch, moment):
    monkeypatch.setattr("obserwator.captures._now", lambda: moment)


def answer(dataset, moment, body, *, status=200):
    """An answer of a capture dataset's source, as it came."""
    return Answer(ADDRESSES[dataset], moment, status, body, dataset)


def spooled(clock, body, *, address=HYDRO_URL, status=200):
    """An answer of ``DAY`` as the spool and the captures hold it."""
    content = body.encode("utf-8") if isinstance(body, str) else body
    return Spooled(
        f"{DAY.isoformat()}T{clock}.000000Z",
        address,
        status,
        hashlib.sha256(content).hexdigest(),
        content,
    )


def records(data):
    """The lines of a sealed capture file, each with its JSON object."""
    text = gzip.decompress(data).decode("utf-8")
    assert text.endswith("\n")
    return [(line, json.loads(line)) for line in text.removesuffix("\n").split("\n")]


def slot(dataset, day):
    return f"archive:{dataset}:{day.isoformat()}.jsonl.gz"


def spool_day(dataset, day):
    return spool_root() / dataset / day.isoformat()


def slot_dir(root, dataset, day):
    server_dir = get_dataset(dataset).server_dir
    return root / "archives" / "versions" / server_dir / day.isoformat()


def versions(root, dataset, day):
    """The version directories of a day's slot."""
    directory = slot_dir(root, dataset, day)
    return sorted(directory.iterdir()) if directory.exists() else []


def sidecar(version):
    return json.loads(Path(f"{version}.meta.json").read_text(encoding="utf-8"))


def relative(root, path):
    return path.relative_to(root).as_posix()


def tree(root):
    return sorted(relative(root, path) for path in root.rglob("*"))


@pytest.fixture(autouse=True)
def nogat_toml(tmp_path, monkeypatch):
    """The test's own spool and ``nogat.toml``; the clock at noon of TODAY (UTC)."""
    monkeypatch.setenv("OBSERWATOR_STATE_DIR", str(tmp_path / "state"))
    path = tmp_path / "nogat.toml"
    path.write_text("", encoding="utf-8")
    monkeypatch.setenv("NOGAT_CONFIG", str(path))
    set_clock(monkeypatch, at(TODAY, "12:00:00"))
    return path


@pytest.fixture
def server():
    """No request leaves the test: sealing reads the spool and the root only."""
    with respx.mock(assert_all_called=False) as mock:
        yield mock


@pytest.fixture
def raw(tmp_path):
    return init_store(tmp_path / "raw").root


@pytest.fixture
def writer_clock(monkeypatch):
    """The writer stamps ``downloaded_at`` by the test's clock, not the machine's."""

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return captures._now().astimezone(tz)

    monkeypatch.setattr(writer, "datetime", Clock)


# --------------------------------------------------------------------------
# The sealed file
# --------------------------------------------------------------------------


def test_an_answer_equal_to_the_one_before_from_its_address_is_recorded_once():
    other = f"{HYDRO_URL}?format=json"
    answers = [
        spooled("10:15:00", "[1]"),
        spooled("11:15:00", "[1]"),
        spooled("11:15:00", "[1]", address=other),
        spooled("12:15:00", "[2]"),
        spooled("12:15:00", "[1]", address=other),
        spooled("13:15:00", "[1]"),
        spooled("14:15:00", "[1]", status=503),
        spooled("15:15:00", "[1]", status=503),
    ]

    data = encode(reversed(answers))

    lines = records(data)
    for line, record in lines:
        assert line == json.dumps(
            record, sort_keys=True, ensure_ascii=False, separators=(",", ":")
        )
    # In the order of time, address, SHA-256 and status; ``seen``, without a body,
    # only after an equal answer (status and body) from the same address.
    assert [
        (
            record["time"],
            record["address"],
            record["status"],
            record.get("body"),
            record.get("seen"),
        )
        for _, record in lines
    ] == [
        (answers[0].time, HYDRO_URL, 200, "[1]", None),
        (answers[1].time, HYDRO_URL, 200, None, True),
        (answers[2].time, other, 200, "[1]", None),
        (answers[3].time, HYDRO_URL, 200, "[2]", None),
        (answers[4].time, other, 200, None, True),
        (answers[5].time, HYDRO_URL, 200, "[1]", None),
        (answers[6].time, HYDRO_URL, 503, "[1]", None),
        (answers[7].time, HYDRO_URL, 503, None, True),
    ]
    assert all(
        set(record) == {"time", "address", "status", "sha256", "seen"}
        for _, record in lines
        if "seen" in record
    )
    assert [record["sha256"] for _, record in lines] == [a.sha256 for a in answers]
    assert decode(data) == answers


def test_the_same_answers_give_the_same_bytes():
    other = f"{HYDRO_URL}?format=json"
    answers = [
        spooled("10:15:00", "[1]"),
        # Answers of one instant and address are told apart by body, then status.
        spooled("11:15:00", "[2]"),
        spooled("11:15:00", "[2]", status=500),
        spooled("11:15:00", "[3]"),
        spooled("11:15:00", "[2]", address=other),
    ]

    data = encode(answers)

    assert encode(reversed(answers)) == data
    assert [item.identity for item in decode(data)] == sorted(
        item.identity for item in answers
    )
    # An answer kept twice (the GUI and a command at one instant) is sealed once.
    assert encode([*answers, answers[0]]) == data
    # gzip, deflate, no flag (so no file name) and the modification time 0.
    assert data[:4] == b"\x1f\x8b\x08\x00"
    assert data[4:8] == bytes(4)


def test_every_body_comes_back_from_its_capture_whatever_its_bytes():
    answers = [
        # Text with line breaks that are no line feed: the canonical JSON keeps them.
        spooled("10:15:00", '{"tresc":"Ostrzeżenie\u2028stopnia 2"}'),
        spooled("10:16:00", '{"tresc":"a\u2029b\u0085c"}'),
        spooled("10:17:00", b"\x1f\x8b\x08\x00\xff\xfe"),
        spooled("10:18:00", b"", status=204),
    ]

    data = encode(answers)

    assert decode(data) == answers
    assert [
        sorted(set(record) - {"time", "address", "status", "sha256"})
        for _, record in records(data)
    ] == [["body"], ["body"], ["body_base64"], ["body"]]


# --------------------------------------------------------------------------
# Sealing the closed days of the spool
# --------------------------------------------------------------------------


def test_sealing_the_closed_days_is_idempotent_and_leaves_today_in_the_spool(
    raw, server, tmp_path, monkeypatch
):
    previous = DAY - timedelta(days=1)
    answers = [
        answer(HYDRO, at(DAY, "10:15:00"), b"[1]"),
        answer(HYDRO, at(DAY, "11:15:00"), b"[1]"),
        answer(HYDRO, at(DAY, "12:15:00"), b"[2]"),
    ]
    for item in (answer(HYDRO, at(previous, "23:15:00"), b"[0]"), *answers):
        write_spool(item)
    today = write_spool(answer(HYDRO, at(TODAY, "10:15:00"), b"[3]"))
    saved = tmp_path / "plan.json"

    plan = check_store(raw, datasets=[HYDRO], plan=saved)

    assert [(item.archive.server_path, item.status) for item in plan.items] == [
        (f"api/data/hydro/{previous}.jsonl.gz", "missing"),
        (f"api/data/hydro/{DAY}.jsonl.gz", "missing"),
    ]
    assert plan.requests == {"made": 0, "planned": 0}

    report = sync_store(raw, plan=saved)

    assert [(item.slot, item.status) for item in report.items] == [
        (slot(HYDRO, previous), "new"),
        (slot(HYDRO, DAY), "new"),
    ]
    assert [(file.path, file.status) for file in report.files] == [
        (item.version, "new") for item in report.items
    ]
    sealed = report.items[1]
    sha = hashlib.sha256(sealed.version.read_bytes()).hexdigest()
    assert relative(raw, sealed.version) == (
        f"archives/versions/api/data/hydro/{DAY}/{DAY}_{sha[:8]}/{DAY}.jsonl.gz"
    )
    assert [item.content for item in decode(sealed.version.read_bytes())] == [
        b"[1]",
        b"[1]",
        b"[2]",
    ]
    assert [item.content for item in decode(report.items[0].version.read_bytes())] == [
        b"[0]"
    ]
    assert not spool_day(HYDRO, previous).exists()
    assert not spool_day(HYDRO, DAY).exists()
    assert today.exists()
    assert not slot_dir(raw, HYDRO, TODAY).exists()

    # The same answers once more (a sync stopped before the removal): unchanged.
    again = [write_spool(item) for item in answers]
    current = check_store(raw, datasets=[HYDRO])
    assert [
        (item.status, item.local_path, item.local_sha256) for item in current.items
    ] == [("current", sealed.version.relative_to(raw), sha)]

    repeated = sync_store(raw, datasets=[HYDRO])

    assert [(item.slot, item.status, item.version) for item in repeated.items] == [
        (slot(HYDRO, DAY), "unchanged", sealed.version)
    ]
    assert versions(raw, HYDRO, DAY) == [sealed.version.parent]
    assert not any(path.exists() for path in again)
    assert not spool_day(HYDRO, DAY).exists()
    assert check_store(raw, datasets=[HYDRO]).items == ()

    # From midnight (UTC) on, the day before is closed.
    set_clock(monkeypatch, at(TODAY + timedelta(days=1), "00:00:00"))
    assert [
        (item.archive.server_path, item.status)
        for item in check_store(raw, datasets=[HYDRO]).items
    ] == [(f"api/data/hydro/{TODAY}.jsonl.gz", "missing")]
    assert not server.calls


def test_a_late_answer_seals_a_correction_that_holds_every_answer(
    raw, monkeypatch, writer_clock
):
    set_clock(monkeypatch, at(TODAY, "01:00:00"))
    for item in (
        answer(HYDRO, at(DAY, "10:15:00"), b"[1]"),
        answer(HYDRO, at(DAY, "11:15:00"), b"[1]"),
    ):
        write_spool(item)
    (first,) = sync_store(raw, datasets=[HYDRO]).items
    # An answer of the day's last instant, kept after the day was sealed.
    set_clock(monkeypatch, at(TODAY, "02:00:00"))
    write_spool(answer(HYDRO, at(DAY, "23:59:59.999999"), b"[2]"))

    plan = check_store(raw, datasets=[HYDRO])

    assert [(item.status, item.local_path) for item in plan.items] == [
        ("newer", first.version.relative_to(raw))
    ]

    (second,) = sync_store(raw, datasets=[HYDRO]).items

    assert (second.slot, second.status) == (slot(HYDRO, DAY), "new")
    assert versions(raw, HYDRO, DAY) == sorted(
        [first.version.parent, second.version.parent]
    )
    assert [
        (item.time, item.content) for item in decode(second.version.read_bytes())
    ] == [
        ("2026-11-21T10:15:00.000000Z", b"[1]"),
        ("2026-11-21T11:15:00.000000Z", b"[1]"),
        ("2026-11-21T23:59:59.999999Z", b"[2]"),
    ]
    assert len(decode(first.version.read_bytes())) == 2
    assert current_version(raw, slot=slot(HYDRO, DAY)).version == second.version
    assert not spool_day(HYDRO, DAY).exists()


def test_a_day_without_a_readable_answer_or_with_a_broken_version_fails(raw):
    kept = answer(HYDRO, at(DAY, "10:15:00"), b"[1]")
    write_spool(kept)
    (sealed,) = sync_store(raw, datasets=[HYDRO]).items
    data = sealed.version.read_bytes()
    # The same size with other bytes: only the SHA-256 tells.
    sealed.version.write_bytes(data[:-1] + bytes([data[-1] ^ 1]))
    again = write_spool(kept)
    lost = DAY - timedelta(days=1)
    truncated = write_spool(answer(HYDRO, at(lost, "10:15:00"), b"[1]"))
    truncated.write_bytes(truncated.read_bytes()[:20])
    notices = []

    plan = check_store(raw, datasets=[HYDRO], on_notice=notices.append)

    assert [(item.archive.server_path, item.status) for item in plan.items] == [
        (f"api/data/hydro/{lost}.jsonl.gz", "check_failed"),
        (f"api/data/hydro/{DAY}.jsonl.gz", "check_failed"),
    ]
    assert plan.items[0].error == message(
        "captures.day_unreadable", dataset=HYDRO, day=lost.isoformat()
    )
    assert plan.items[1].error.key == "captures.corrupt_capture"
    assert plan.requests == {"made": 0, "planned": 0}
    assert [(notice.level, notice.code) for notice in notices] == [
        ("warning", "capture_unreadable"),
        ("warning", "archive_failed"),
        ("warning", "archive_failed"),
    ]

    report = sync_store(raw, datasets=[HYDRO])

    assert [(item.slot, item.status, item.error_code) for item in report.items] == [
        (slot(HYDRO, lost), "failed", "data_error"),
        (slot(HYDRO, DAY), "failed", "data_error"),
    ]
    assert report.files == ()
    assert truncated.exists() and again.exists()
    assert versions(raw, HYDRO, DAY) == [sealed.version.parent]
    assert versions(raw, HYDRO, lost) == []


def test_unreadable_spool_files_stay_with_a_warning_and_the_readable_are_sealed(raw):
    write_spool(answer(HYDRO, at(DAY, "10:15:00"), b"[1]"))
    write_spool(answer(HYDRO, at(DAY, "11:15:00"), b"[2]"))
    truncated = write_spool(answer(HYDRO, at(DAY, "12:15:00"), b"[3]"))
    truncated.write_bytes(truncated.read_bytes()[:30])
    altered = write_spool(answer(HYDRO, at(DAY, "13:15:00"), b"[4]"))
    record = json.loads(altered.read_bytes())
    altered.write_text(json.dumps({**record, "body": "[5]"}), encoding="utf-8")
    named = write_spool(answer(HYDRO, at(DAY, "14:15:00"), b"[6]"))
    renamed = named.rename(
        named.with_name(
            named.name.replace(
                hashlib.sha256(b"[6]").hexdigest(), hashlib.sha256(b"[7]").hexdigest()
            )
        )
    )
    moved = write_spool(answer(HYDRO, at(TODAY, "09:00:00"), b"[8]"))
    strayed = moved.rename(spool_day(HYDRO, DAY) / moved.name)
    stray = spool_day(HYDRO, DAY) / "notes.txt"
    stray.write_text("no answer", encoding="utf-8")
    unreadable = sorted([truncated, altered, renamed, strayed, stray])
    notices = []

    report = sync_store(raw, datasets=[HYDRO], on_notice=notices.append)

    (sealed,) = report.items
    assert sealed.status == "new"
    assert [item.content for item in decode(sealed.version.read_bytes())] == [
        b"[1]",
        b"[2]",
    ]
    assert sorted(spool_day(HYDRO, DAY).iterdir()) == unreadable
    warned = [notice for notice in notices if notice.code == "capture_unreadable"]
    assert {notice.level for notice in warned} == {"warning"}
    assert {notice.message.params["name"] for notice in warned} == {
        relative(spool_root(), path) for path in unreadable
    }

    # They stay: the next sync finds the day sealed and leaves them alone.
    assert [item.status for item in sync_store(raw, datasets=[HYDRO]).items] == [
        "unchanged"
    ]
    assert sorted(spool_day(HYDRO, DAY).iterdir()) == unreadable


def test_the_store_commands_check_and_seal_a_capture_dataset(raw):
    write_spool(answer(HYDRO, at(DAY, "10:15:00"), b"[1]"))
    options = {"root": str(raw), "datasets": [HYDRO]}

    checked = run_command("store check", options=options)
    synced = run_command("store sync", options=options)

    assert checked.status == "ok"
    assert [item.status for item in checked.result.items] == ["missing"]
    assert synced.status == "ok"
    assert [(item.slot, item.status) for item in synced.result.items] == [
        (slot(HYDRO, DAY), "new")
    ]
    assert not spool_day(HYDRO, DAY).exists()


# --------------------------------------------------------------------------
# Captures beside the station sources
# --------------------------------------------------------------------------


def test_captures_below_the_slot_of_hydro_now_leave_its_versions_and_catalog_alone(
    tmp_path,
):
    roots = build_fixture_store(tmp_path / "raw", data_root=tmp_path / "data")
    raw = roots.raw.root
    hydro_now = current_version(raw, slot=HYDRO_NOW)
    meteo_now = current_version(raw, slot=METEO_NOW)
    write_spool(answer(HYDRO, at(DAY, "10:15:00"), b"[]"))
    write_spool(answer(METEO, at(DAY, "10:15:00"), b"[]"))

    hydro, meteo = sync_store(raw, datasets=[HYDRO, METEO]).items
    # The station sources are synchronized again beside the captures.
    with _recorded_http(["hydro_current", "meteo_current"]):
        resynced = sync_store(raw, datasets=["pl.imgw.hydro_now", "pl.imgw.meteo_now"])

    assert [(item.slot, item.status) for item in (hydro, meteo)] == [
        (slot(HYDRO, DAY), "new"),
        (slot(METEO, DAY), "new"),
    ]
    # The day's slot directory lies in the slot directory of pl.imgw.hydro_now.
    assert slot_dir(raw, HYDRO, DAY).parent == hydro_now.version.parent.parent
    assert [(item.slot, item.status, item.version) for item in resynced.items] == [
        (HYDRO_NOW, "unchanged", hydro_now.version),
        (METEO_NOW, "unchanged", meteo_now.version),
    ]
    entries = list(iter_store(raw))
    assert [entry for entry in entries if entry.kind == "problem"] == []
    assert sorted(
        (entry.slot, relative(raw, entry.version))
        for entry in entries
        if relative(raw, entry.version).startswith("archives/versions/api/data/")
    ) == sorted(
        [
            (HYDRO_NOW, relative(raw, hydro_now.version)),
            (METEO_NOW, relative(raw, meteo_now.version)),
            (slot(HYDRO, DAY), relative(raw, hydro.version)),
            (slot(METEO, DAY), relative(raw, meteo.version)),
        ]
    )
    assert current_version(raw, slot=HYDRO_NOW).version == hydro_now.version
    assert current_version(raw, slot=METEO_NOW).version == meteo_now.version
    assert current_version(raw, slot=slot(HYDRO, DAY)).version == hydro.version
    assert current_version(raw, slot=slot(METEO, DAY)).version == meteo.version
    # The catalog reads the same station metadata: the very catalog of the fixture.
    assert build_catalog(roots.data, raw_root=raw).status == "unchanged"


# --------------------------------------------------------------------------
# Tier and publication of the sidecar (ADR-030 D6)
# --------------------------------------------------------------------------


def test_a_capture_sidecar_holds_its_tier_and_the_publication_in_force_when_written(
    raw, nogat_toml
):
    for item in (
        answer(HYDRO, at(DAY, "10:15:00"), b"[1]"),
        answer(HYDRO, at(DAY, "11:15:00"), b"[1]"),
        answer(HYDRO, at(DAY, "12:15:00"), b"[2]"),
        answer(STATES, at(DAY, "10:15:00"), b"{}"),
    ):
        write_spool(item)

    hydro, states = sync_store(raw, datasets=[HYDRO, STATES]).items

    meta = sidecar(hydro.version)
    assert (meta["tier"], meta["publication"]) == ("operational", "public")
    assert meta["extra"]["capture"] == {"answers": 3}
    assert meta["extra"]["http"]["url"] == HYDRO_URL
    assert meta["extra"]["version"] == {
        "label": DAY.isoformat(),
        "label_source": "downloaded",
    }
    meta = sidecar(states.version)
    assert (meta["tier"], meta["publication"]) == ("operational", "private")
    assert meta["extra"]["capture"] == {"answers": 1}
    assert meta["extra"]["http"]["url"] == STATES_SOURCE

    # [obserwator.capture] turns both round for the versions written after it.
    nogat_toml.write_text(
        "[obserwator.capture]\n"
        '"pl.imgw.hydro_current" = "private"\n'
        'pl.imgw.hydro_states_current = "public"\n',
        encoding="utf-8",
    )
    write_spool(answer(HYDRO, at(DAY, "23:15:00"), b"[3]"))
    write_spool(answer(STATES, at(DAY, "23:15:00"), b"{}"))
    hydro_late, states_late = sync_store(raw, datasets=[HYDRO, STATES]).items

    assert {
        entry.version: (entry.meta.tier, entry.meta.publication)
        for entry in iter_store(raw, kind="archive")
    } == {
        hydro.version: ("operational", "public"),
        states.version: ("operational", "private"),
        hydro_late.version: ("operational", "private"),
        states_late.version: ("operational", "public"),
    }
    assert sidecar(states_late.version)["extra"]["capture"] == {"answers": 2}


def test_a_verified_version_has_neither_tier_nor_publication(raw):
    written = store_local(raw, H2024, V1)

    assert {"tier", "publication"}.isdisjoint(sidecar(written.path))
    (entry,) = iter_store(raw)
    assert (entry.meta.tier, entry.meta.publication) == (None, None)


@pytest.mark.parametrize(
    ("dropped", "changed"),
    [
        ("publication", {}),
        ("tier", {}),
        (None, {"tier": "verified"}),
        (None, {"publication": "secret"}),
    ],
    ids=["tier alone", "publication alone", "verified tier", "unknown publication"],
)
def test_a_sidecar_with_a_partial_or_invalid_tier_is_invalid_meta(
    raw, dropped, changed
):
    write_spool(answer(HYDRO, at(DAY, "10:15:00"), b"[1]"))
    (sealed,) = sync_store(raw, datasets=[HYDRO]).items
    path = Path(f"{sealed.version}.meta.json")
    meta = {**json.loads(path.read_text(encoding="utf-8")), **changed}
    meta.pop(dropped, None)
    path.write_text(json.dumps(meta), encoding="utf-8")

    (entry,) = iter_store(raw)

    assert (entry.kind, entry.slot, entry.problem_code) == (
        "problem",
        slot(HYDRO, DAY),
        "invalid_meta",
    )


# --------------------------------------------------------------------------
# What a capture dataset is not given
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "other", ["pl.imgw.hydro_now", "pl.imgw.hydro_daily", "cz.chmu.hydro_daily"]
)
def test_a_capture_dataset_is_never_mixed_with_another_dataset(raw, server, other):
    write_spool(answer(HYDRO, at(DAY, "10:15:00"), b"[1]"))
    before = tree(raw)

    for call in (check_store, sync_store):
        with pytest.raises(ObserwatorValidationError) as error:
            call(raw, datasets=[other, HYDRO])
        assert error.value.localized("en") == message("sync.captures_alone")
        assert error.value.details["option"] == "datasets"

    assert tree(raw) == before
    assert spool_day(HYDRO, DAY).exists()
    assert not server.calls


@pytest.mark.parametrize(
    ("option", "value"),
    [("years", [2026]), ("months", [11]), ("stations", ["149190320"])],
)
def test_file_selectors_are_refused_with_a_capture_dataset(raw, server, option, value):
    for call in (check_store, sync_store):
        with pytest.raises(ObserwatorValidationError) as error:
            call(raw, datasets=[HYDRO], **{option: value})
        assert error.value.details["reason"] == "captures"
        assert error.value.details["option"] == option
    assert not server.calls


def test_a_capture_dataset_is_never_written_as_a_plain_file(tmp_path, server):
    write_spool(answer(HYDRO, at(DAY, "10:15:00"), b"[1]"))

    with pytest.raises(ObserwatorValidationError) as plain:
        sync_store(output_dir=tmp_path / "out", datasets=[HYDRO])
    with pytest.raises(ObserwatorValidationError) as files:
        archive_files(HYDRO)

    assert plain.value.details["reason"] == "store_only_dataset"
    assert not (tmp_path / "out").exists()
    assert spool_day(HYDRO, DAY).exists()
    assert (files.value.details["reason"], files.value.details["value"]) == (
        "capture",
        HYDRO,
    )
    assert not server.calls


@pytest.mark.parametrize(
    "server_path",
    [
        "api/data/hydro/20261121.jsonl.gz",
        "api/data/hydro/2026-W47-6.jsonl.gz",
        "api/data/hydro/2026-02-30.jsonl.gz",
        "api/data/hydro/2026-11-21.json.gz",
        "api/data/hydro/2026-11-21.jsonl",
        "api/data/hydro/.jsonl.gz",
        "api/data/hydro/2026-11-21/2026-11-21.jsonl.gz",
        "api/data/2026-11-21.jsonl.gz",
        "api/data/meteo/2026-11-21.jsonl.gz",
    ],
)
def test_only_its_directory_and_the_canonical_day_name_a_capture_file(server_path):
    assert _capture_from_path(get_dataset(HYDRO), server_path) is None
