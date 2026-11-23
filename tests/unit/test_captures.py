"""
Captures (P14-P16, ADR-030 D3, D5-D7, D9): the spool, the request hook, the hourly poll.

Each test has a spool (``OBSERWATOR_STATE_DIR``) and a clock (``obserwator.captures._now``)
of its own and reads no variable, ``.env`` or ``nogat.toml`` of the machine. The sealing
itself is tested in ``test_store_captures.py``; here a sealed day only shows what
reached it.
"""

import base64
import dataclasses
import gzip
import hashlib
import json
import logging
import os
import sys
from datetime import UTC, date, datetime, timedelta, timezone

import httpx
import platformdirs
import pytest
import respx
from typer.testing import CliRunner

import obserwator
from obserwator import captures
from obserwator.captures import (
    Spooled,
    capture_dataset,
    keep_response,
    poll_current,
    poll_plan,
    publication,
    publication_sources,
    read_spooled,
    spool_files,
    spool_root,
    write_spool,
)
from obserwator.cli import main as cli_main
from obserwator.config import environment_report
from obserwator.datasets import ProviderCredential, get_dataset, get_provider, providers
from obserwator.exceptions import ObserwatorError
from obserwator.fetch import _get
from obserwator.providers.base import Answer
from obserwator.store import init_store, sync_store
from obserwator.store.captures import decode
from obserwator.testing import _recorded_http

RUNNER = CliRunner()
FILES = ("recordings.json", "contract_recordings.json")
SOURCES = get_provider("IMGW").adapter.polled
HYDRO = "pl.imgw.hydro_current"
METEO = "pl.imgw.meteo_current"
SYNOP = "pl.imgw.meteo_synop_current"
STATES = "pl.imgw.hydro_states_current"
HYDRO_URL = "https://danepubliczne.imgw.pl/api/data/hydro"
DAY = date(2026, 11, 21)
OUTAGE = b'{"message": "Service Unavailable"}'
KEY = "k3y-of-the-test-provider-0123456789abcdef"
PASSWORD = "pa55word-of-the-reader"
PRIVATE_BY_DEFAULT = {STATES, "pl.imgw.hydro_operational"}
"""hydro.imgw.pl and its backend, whose regulamin allows private use only (D5)."""


def at(hour, minute=0, second=0, *, day=DAY):
    return datetime(day.year, day.month, day.day, hour, minute, second, tzinfo=UTC)


@pytest.fixture(autouse=True)
def user_environment(tmp_path, monkeypatch):
    """No OBSERWATOR_/NOGAT_ variable, ``.env`` or user ``nogat.toml``; a spool of its own."""
    for name in list(os.environ):
        if name.startswith(("OBSERWATOR_", "NOGAT_")):
            monkeypatch.delenv(name)
    home = tmp_path / "home"
    monkeypatch.setattr(
        platformdirs, "user_config_path", lambda *a, **k: home / "config"
    )
    monkeypatch.setattr(platformdirs, "user_data_path", lambda *a, **k: home / "data")
    monkeypatch.setattr(platformdirs, "user_cache_path", lambda *a, **k: home / "cache")
    monkeypatch.setattr(platformdirs, "user_state_path", lambda *a, **k: home / "state")
    monkeypatch.setenv("OBSERWATOR_STATE_DIR", str(tmp_path / "state"))
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)


@pytest.fixture
def clock(monkeypatch):
    """``clock(moment)`` sets the time of the captures (``obserwator.captures._now``)."""

    def move(moment):
        monkeypatch.setattr(captures, "_now", lambda: moment)

    return move


@pytest.fixture
def keyed_imgw(monkeypatch):
    """IMGW-PIB declaring an API key (no provider of 3.2.0 does), the key set."""
    registry = sys.modules["obserwator.datasets"]
    provider = dataclasses.replace(
        get_provider("IMGW"), credential=ProviderCredential("TEST_PROVIDER")
    )
    monkeypatch.setattr(
        registry,
        "_PROVIDERS",
        tuple(provider if item.id == "IMGW" else item for item in providers()),
    )
    monkeypatch.setattr(
        registry,
        "_PROVIDER_BY_NAME",
        {**registry._PROVIDER_BY_NAME, "IMGW": provider, "pl.imgw": provider},
    )
    monkeypatch.setenv("OBSERWATOR_TEST_PROVIDER_API_KEY", KEY)
    return provider


def write_config(tmp_path, monkeypatch, text):
    path = tmp_path / "nogat.toml"
    path.write_text(text, encoding="utf-8")
    monkeypatch.setenv("NOGAT_CONFIG", str(path))
    return path


def body(dataset):
    return json.dumps({"source": dataset}).encode()


def serve(router, answers=None):
    """
    Answer every polled source with ``body(dataset)``, or as ``answers`` says.

    ``answers`` maps a dataset to bytes (an answer 200), an HTTP status (an answer of
    that status with the body ``OUTAGE``) or an exception (no answer).
    """
    routes = {}
    for source in SOURCES:
        answer = (answers or {}).get(source.dataset, body(source.dataset))
        route = router.get(source.url)
        if isinstance(answer, Exception):
            route.mock(side_effect=answer)
        elif isinstance(answer, int):
            route.respond(answer, content=OUTAGE)
        else:
            route.respond(200, content=answer)
        routes[source.dataset] = route
    return routes


def sealed_day(tmp_path, *keys):
    """Seal the closed days of ``keys`` into a new raw root: the items by dataset."""
    report = sync_store(init_store(tmp_path / "raw"), datasets=list(keys))
    return {item.slot.split(":")[1]: item for item in report.items}


# --- the spool --------------------------------------------------------------------------


def test_a_spool_file_is_named_by_its_utc_time_and_body_and_holds_one_record():
    warsaw = timezone(timedelta(hours=2))
    answer = Answer(
        url=HYDRO_URL,
        # 22:30 UTC on the 21st: the spool day is the UTC day, not the local one.
        received_at=datetime(2026, 11, 22, 0, 30, 0, 123456, tzinfo=warsaw),
        status=200,
        content='[{"stacja": "Raba Górna"}]'.encode(),
        dataset=HYDRO,
    )

    path = write_spool(answer)
    again = write_spool(answer)
    binary = write_spool(dataclasses.replace(answer, content=b"\x89PNG\r\n\x00"))
    unknown = write_spool(dataclasses.replace(answer, dataset="pl.imgw.hydro_daily"))

    digest = hashlib.sha256(answer.content).hexdigest()
    stamp = "2026-11-21T22:30:00.123456Z"
    assert path == (
        spool_root() / HYDRO / "2026-11-21" / f"20261121T223000.123456Z_{digest}.json"
    )
    # The same answer at the same instant is kept once; another body is another file.
    assert again == path
    assert spool_files(HYDRO, DAY) == sorted([path, binary])
    assert path.read_bytes().count(b"\n") == 1
    assert json.loads(path.read_bytes()) == {
        "time": stamp,
        "address": HYDRO_URL,
        "status": 200,
        "sha256": digest,
        "body": '[{"stacja": "Raba Górna"}]',
    }
    assert read_spooled(path) == Spooled(stamp, HYDRO_URL, 200, digest, answer.content)
    record = json.loads(binary.read_bytes())
    assert "body" not in record
    assert base64.b64decode(record["body_base64"]) == b"\x89PNG\r\n\x00"
    assert read_spooled(binary).content == b"\x89PNG\r\n\x00"
    assert unknown is None
    assert [entry.name for entry in spool_root().iterdir()] == [HYDRO]


@pytest.mark.parametrize(
    ("url", "dataset"),
    [
        (HYDRO_URL, HYDRO),
        (f"{HYDRO_URL}/id/149190310", HYDRO),
        (
            "HTTPS://DanePubliczne.IMGW.pl/api/data/synop?x=1",
            "pl.imgw.meteo_synop_current",
        ),
        (
            "https://hydro-back.imgw.pl/map/stations/hydrologic?onlyMainStations=true",
            STATES,
        ),
        (
            "https://hydro-back.imgw.pl/station/hydro/status?id=149190310",
            "pl.imgw.hydro_operational",
        ),
        (
            "https://opendata.chmi.cz/hydrology/now/data/0-203-1-001000.json",
            "cz.chmu.hydro_current",
        ),
        # Not below a source's directory: a longer name, the station sources' API.
        ("https://danepubliczne.imgw.pl/api/data/hydrology", None),
        ("https://danepubliczne.imgw.pl/api/data", None),
        # Archives and station lists keep versions of their own.
        (
            "https://danepubliczne.imgw.pl/data/dane_pomiarowo_obserwacyjne/"
            "dane_hydrologiczne/dobowe/2024/codz_2024.zip",
            None,
        ),
        (
            "https://danepubliczne.imgw.pl/data/dane_pomiarowo_obserwacyjne/"
            "dane_hydrologiczne/lista_stacji_hydro.csv",
            None,
        ),
        (
            "https://opendata.chmi.cz/hydrology/historical/data/daily/"
            "H_0-203-1-001000_DQ_2024.json",
            None,
        ),
    ],
)
def test_an_answer_is_kept_in_the_capture_source_its_address_belongs_to(
    clock, url, dataset
):
    clock(at(10, 15))

    found = capture_dataset(url)
    path = keep_response(
        httpx.Response(200, content=b"{}", request=httpx.Request("GET", url))
    )

    assert (None if found is None else found.key) == dataset
    if dataset is None:
        assert path is None
        assert not spool_root().exists()
    else:
        assert path.parent == spool_root() / dataset / "2026-11-21"


def test_an_address_belongs_to_the_longest_capture_source_it_lies_in(monkeypatch):
    registry = sys.modules["obserwator.datasets"]
    station = dataclasses.replace(
        get_dataset(HYDRO),
        key="pl.imgw.hydro_station_current",
        slug="imgw_hydro_station_current",
        server_dir="api/data/hydro/id",
    )
    monkeypatch.setattr(registry, "_REGISTRY", (*registry._REGISTRY, station))

    assert capture_dataset(f"{HYDRO_URL}/id/149190310").key == station.key
    assert capture_dataset(HYDRO_URL).key == HYDRO


async def test_the_library_keeps_an_answer_before_it_checks_it_on_both_request_paths(
    clock,
):
    clock(at(10, 15))

    with respx.mock(assert_all_mocked=True) as router:
        router.get(HYDRO_URL).respond(503, content=OUTAGE)
        router.get("https://danepubliczne.imgw.pl/api/data/meteo").respond(
            200, json=[{"kod_stacji": "123750000", "nazwa_stacji": "Warszawa"}]
        )
        with pytest.raises(ObserwatorError) as failed:
            obserwator.fetch_hydro_current()
        records = await obserwator.fetch_meteo_current_async()

    assert failed.value.code == "source_unavailable"
    (outage,) = spool_files(HYDRO, DAY)
    assert (read_spooled(outage).status, read_spooled(outage).content) == (503, OUTAGE)
    (meteo,) = spool_files(METEO, DAY)
    assert read_spooled(meteo).status == 200
    assert [record.station_code for record in records] == ["123750000"]


def test_replayed_answers_reach_the_spool_only_when_a_test_keeps_them(clock):
    clock(at(10, 15))

    with _recorded_http(["hydro_current"], recordings=FILES):
        obserwator.fetch_hydro_current()
    left_alone = list(spool_root().rglob("*"))
    with _recorded_http(["hydro_current"], recordings=FILES, keep=True):
        obserwator.fetch_hydro_current()

    assert left_alone == []
    (kept,) = spool_files(HYDRO, DAY)
    assert read_spooled(kept).address == HYDRO_URL


def test_no_credential_reaches_the_spool_the_sealed_capture_or_its_sidecar(
    tmp_path, clock, keyed_imgw
):
    asked = (
        f"https://reader:{PASSWORD}@danepubliczne.imgw.pl/api/data/hydro/{KEY}/latest"
        f"?station=150190340&api_key={KEY}&token=t0k3n&ref=x{KEY}y&lang=pl#{KEY}"
    )
    clock(at(10, 15))
    with respx.mock(assert_all_mocked=True) as router:
        router.get(host="danepubliczne.imgw.pl").respond(200, json=[{"a": 1}])
        _get(asked, timeout=5)
    (spooled,) = spool_files(HYDRO, DAY)
    spool_bytes = spooled.read_bytes()
    clock(at(0, 30, day=DAY + timedelta(days=1)))

    item = sealed_day(tmp_path, HYDRO)[HYDRO]

    sealed = gzip.decompress(item.version.read_bytes())
    sidecar = item.version.with_name(f"{item.version.name}.meta.json").read_bytes()
    for written in (spool_bytes, sealed, sidecar):
        for secret in (KEY, PASSWORD, "t0k3n"):
            assert secret.encode() not in written
    # The address keeps its other parameters; the key left in its path is redacted.
    (answer,) = decode(item.version.read_bytes())
    assert answer.address == (
        "https://danepubliczne.imgw.pl/api/data/hydro/REDACTED/latest"
        "?station=150190340&lang=pl"
    )


def test_a_failed_spool_write_never_fails_the_request_and_is_reported_until_one_succeeds(
    tmp_path, caplog, clock
):
    state = tmp_path / "state"
    state.write_text("a file, not a directory\n", encoding="utf-8")
    clock(at(10, 15))
    with (
        caplog.at_level(logging.WARNING, logger="obserwator.captures"),
        _recorded_http(["hydro_current"], recordings=FILES, keep=True),
    ):
        served = obserwator.fetch_hydro_current()
    logged = [r for r in caplog.records if r.name == "obserwator.captures"]
    unwritable = environment_report()["problems"]
    # The state directory is usable again, but the source's directory is blocked: the
    # failure is remembered for config show.
    state.unlink()
    blocked = spool_root() / HYDRO
    blocked.parent.mkdir(parents=True)
    blocked.write_text("in the way\n", encoding="utf-8")
    clock(at(11, 15))
    with _recorded_http(["hydro_current"], recordings=FILES, keep=True):
        obserwator.fetch_hydro_current()
    remembered = environment_report()["problems"]
    failure = state / "obserwator" / "capture-failure.json"
    was_remembered = failure.is_file()
    blocked.unlink()
    clock(at(12, 15))
    with _recorded_http(["hydro_current"], recordings=FILES, keep=True):
        kept = obserwator.fetch_hydro_current()

    assert served and served == kept
    (warning,) = logged
    assert (warning.levelno, warning.event) == (logging.WARNING, "capture_failed")
    assert [(p["code"], p["option"]) for p in unwritable] == [
        ("capture_spool", "state_dir")
    ]
    assert [(p["code"], p["option"]) for p in remembered] == [
        ("capture_spool", "state_dir")
    ]
    assert HYDRO in str(remembered[0]["message"])
    assert was_remembered
    assert not failure.exists()
    assert environment_report()["problems"] == []
    assert len(spool_files(HYDRO, DAY)) == 1


# --- the hourly poll --------------------------------------------------------------------


def test_the_poll_keeps_each_source_answer_in_the_spool_and_writes_no_root(
    tmp_path, monkeypatch, clock
):
    monkeypatch.setenv("OBSERWATOR_ROOT", str(tmp_path / "data"))
    monkeypatch.setenv("OBSERWATOR_RAW_ROOT", str(tmp_path / "raw"))
    clock(at(10, 15))

    with respx.mock(assert_all_mocked=True) as router:
        serve(router)
        report = poll_current()

    assert not report.cancelled
    assert [(a.dataset, a.status, a.http_status) for a in report.answers] == [
        (source.dataset, "captured", 200) for source in SOURCES
    ]
    for answer, source in zip(report.answers, SOURCES, strict=True):
        kept = read_spooled(answer.path)
        assert answer.path.parent == spool_root() / source.dataset / "2026-11-21"
        assert (kept.address, kept.status, kept.content) == (
            source.url,
            200,
            body(source.dataset),
        )
        assert (answer.url, answer.polled_at, answer.error) == (
            source.url,
            "2026-11-21T10:15:00.000000Z",
            None,
        )
        assert answer.sha256 == hashlib.sha256(body(source.dataset)).hexdigest()
    assert [(f.path, f.size_bytes, f.sha256, f.status) for f in report.files] == [
        (
            a.path,
            a.path.stat().st_size,
            hashlib.sha256(a.path.read_bytes()).hexdigest(),
            "written",
        )
        for a in report.answers
    ]
    assert not (tmp_path / "data").exists()
    assert not (tmp_path / "raw").exists()


def test_a_poll_sooner_than_the_interval_allows_skips_each_source_without_a_request(
    clock,
):
    first = at(10, 15)
    clock(first)
    planned = poll_plan()
    with respx.mock(assert_all_mocked=True) as router:
        serve(router)
        poll_current()
    waiting = poll_plan()
    # The interval (an hour) less a tenth, a timer's jitter: 54 minutes.
    clock(first + timedelta(seconds=3239))
    notices = []
    with respx.mock(assert_all_mocked=True) as offline:  # any request fails the test
        skipped = poll_current(on_notice=notices.append)
        asked_early = len(offline.calls)
    clock(first + timedelta(seconds=3240))
    due = poll_plan()
    with respx.mock(assert_all_mocked=True) as router:
        routes = serve(router)
        again = poll_current()

    assert {source.interval for source in SOURCES} == {3600}
    assert [action.status for action in planned] == ["unverifiable"] * len(SOURCES)
    assert [action.status for action in waiting] == ["current"] * len(SOURCES)
    assert asked_early == 0
    assert [(a.status, a.polled_at, a.path) for a in skipped.answers] == [
        ("skipped", "2026-11-21T10:15:00.000000Z", None)
    ] * len(SOURCES)
    assert skipped.files == ()
    assert [(n.level, n.code) for n in notices] == [("info", "poll_skipped")] * len(
        SOURCES
    )
    assert [action.status for action in due] == ["unverifiable"] * len(SOURCES)
    assert [a.status for a in again.answers] == ["captured"] * len(SOURCES)
    assert all(route.call_count == 1 for route in routes.values())


def test_a_source_answering_no_success_is_failed_but_kept_one_not_answering_keeps_nothing(
    clock,
):
    clock(at(10, 15))
    notices = []
    # An HTTP error, a redirect (which the library's requests refuse too), no answer.
    failing = {HYDRO: 503, SYNOP: 301, METEO: httpx.ConnectError("connection refused")}

    with respx.mock(assert_all_mocked=True) as router:
        serve(router, failing)
        report = poll_current(on_notice=notices.append)

    answers = {answer.dataset: answer for answer in report.answers}
    for key in (HYDRO, SYNOP):
        answer = answers[key]
        assert (answer.status, answer.error_code, answer.http_status) == (
            "failed",
            "source_unavailable",
            failing[key],
        )
        kept = read_spooled(answer.path)
        assert (kept.status, kept.content) == (failing[key], OUTAGE)
        assert answer.error
    silent = answers[METEO]
    assert (silent.status, silent.error_code, silent.http_status, silent.path) == (
        "failed",
        "source_unavailable",
        None,
        None,
    )
    assert silent.error
    assert spool_files(METEO, DAY) == []
    assert {a.status for key, a in answers.items() if key not in failing} == {
        "captured"
    }
    assert [(n.level, n.code) for n in notices] == [("warning", "capture_failed")] * 3
    assert [f.path for f in report.files] == [a.path for a in report.answers if a.path]


def test_a_cancelled_poll_asks_no_further_source_and_leaves_them_due(clock):
    clock(at(10, 15))

    with respx.mock(assert_all_mocked=True, assert_all_called=False) as router:
        serve(router)
        report = poll_current(cancel=lambda: len(router.calls) >= 2)
        asked = len(router.calls)
    plan = poll_plan()

    assert report.cancelled
    assert [a.status for a in report.answers] == ["captured"] * 2 + ["cancelled"] * 4
    assert asked == 2
    assert all(a.path is None for a in report.answers[2:])
    assert len(report.files) == 2
    assert [action.status for action in plan] == ["current"] * 2 + ["unverifiable"] * 4


def test_an_equal_answer_is_sealed_once_as_seen_and_a_changed_one_again(
    tmp_path, clock
):
    bodies = [b'{"a": 1}', b'{"a": 1}', b'{"a": 2}', b'{"a": 1}']
    for hour, content in zip((10, 11, 12, 13), bodies, strict=True):
        clock(at(hour, 15))
        with respx.mock(assert_all_mocked=True) as router:
            serve(router, {HYDRO: content})
            poll_current()
    clock(at(0, 30, day=DAY + timedelta(days=1)))

    item = sealed_day(tmp_path, HYDRO)[HYDRO]

    assert item.status == "new"
    data = item.version.read_bytes()
    lines = [json.loads(line) for line in gzip.decompress(data).splitlines()]
    assert [(line["time"], line.get("body"), line.get("seen")) for line in lines] == [
        ("2026-11-21T10:15:00.000000Z", '{"a": 1}', None),
        ("2026-11-21T11:15:00.000000Z", None, True),
        ("2026-11-21T12:15:00.000000Z", '{"a": 2}', None),
        ("2026-11-21T13:15:00.000000Z", '{"a": 1}', None),
    ]
    assert set(lines[1]) == {"time", "address", "status", "sha256", "seen"}
    assert [answer.content for answer in decode(data)] == bodies


# --- publication state (P15) ------------------------------------------------------------


def test_config_show_lists_every_source_with_its_state_and_where_it_comes_from(
    tmp_path, monkeypatch
):
    defaults = environment_report()["capture"]
    write_config(
        tmp_path,
        monkeypatch,
        "[obserwator.capture]\n"
        '"pl.imgw.hydro_current" = "private"\n'
        'pl.imgw.hydro_states_current = "public"\n'  # dotted keys are tables in TOML
        'cz.chmu.hydro_recent = "private"\n',
    )
    changed = {
        HYDRO: "private",
        STATES: "public",
        "cz.chmu.hydro_recent": "private",
    }

    report = environment_report()
    text = RUNNER.invoke(cli_main.app, ["config", "show"])
    shown = RUNNER.invoke(cli_main.app, ["config", "show", "--json"])

    keys = [descriptor.key for descriptor in publication_sources()]
    assert {HYDRO, "cz.chmu.hydro_current", *changed, *PRIVATE_BY_DEFAULT} <= set(keys)
    assert "pl.imgw.hydro_daily" not in keys  # a verified dataset has no state
    assert defaults["spool"] == str(spool_root())
    assert list(defaults["sources"]) == keys
    for descriptor in publication_sources():
        assert defaults["sources"][descriptor.key] == {
            "state": "private" if descriptor.key in PRIVATE_BY_DEFAULT else "public",
            "tier": descriptor.tier,
            "source": "default",
            "name": None,
        }
    for key, entry in report["capture"]["sources"].items():
        if key in changed:
            assert entry == {
                **defaults["sources"][key],
                "state": changed[key],
                "source": "file",
                "name": "[obserwator.capture]",
            }
        else:
            assert entry == defaults["sources"][key]
    assert [publication(key) for key in changed] == list(changed.values())
    assert report["problems"] == []
    assert report["config_file"]["ignored"] == []
    assert text.exit_code == 0, text.output
    lines = text.stdout.splitlines()
    for key, entry in report["capture"]["sources"].items():
        (line,) = [line for line in lines if line.startswith(f"  {key} = ")]
        assert line.startswith(f"  {key} = {entry['state']}  [")
        assert line.endswith("[file [obserwator.capture]]") == (key in changed)
    assert shown.exit_code == 0, shown.output
    assert json.loads(shown.stdout)["capture"] == report["capture"]


@pytest.mark.parametrize(
    ("text", "option"),
    [
        # A verified dataset has no publication state.
        (
            '"pl.imgw.hydro_daily" = "private"\n',
            "capture.pl.imgw.hydro_daily",
        ),
        ('pl.imgw.hydro_current = "hidden"\n', "capture.pl.imgw.hydro_current"),
        ("pl.imgw.hydro_current = true\n", "capture.pl.imgw.hydro_current"),
        # A quoted key and dotted keys naming one source: which state was meant?
        (
            '"pl.imgw.hydro_current" = "private"\npl.imgw.hydro_current = "public"\n',
            "capture.pl.imgw.hydro_current",
        ),
    ],
)
def test_an_invalid_capture_section_is_a_problem_and_every_default_applies(
    tmp_path, monkeypatch, text, option
):
    # A valid line beside the invalid one: the whole section is set aside.
    write_config(
        tmp_path,
        monkeypatch,
        f'[obserwator.capture]\npl.imgw.hydro_states_current = "public"\n{text}',
    )

    report = environment_report()

    (problem,) = report["problems"]
    assert (problem["code"], problem["option"]) == ("invalid_capture", option)
    assert {entry["source"] for entry in report["capture"]["sources"].values()} == {
        "default"
    }
    assert (publication(STATES), publication(HYDRO)) == ("private", "public")


def test_a_capture_setting_that_is_no_table_is_a_problem_and_every_default_applies(
    tmp_path, monkeypatch
):
    write_config(tmp_path, monkeypatch, '[obserwator]\ncapture = "public"\n')

    report = environment_report()
    text = RUNNER.invoke(cli_main.app, ["config", "show"])

    (problem,) = report["problems"]
    assert (problem["code"], problem["option"]) == ("invalid_capture", "capture")
    assert publication(STATES) == "private"
    assert [line for line in text.stdout.splitlines() if "[invalid_capture]" in line]
