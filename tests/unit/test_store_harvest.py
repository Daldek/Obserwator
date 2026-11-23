"""The operational series in the store on recorded answers (ADR-030 D3, D9, O2).

``store sync --pace-until`` harvests one dataset (hydro-back's H, Q and T of
``pl.imgw.hydro_operational``, ČHMÚ's ``recent`` day files of ``cz.chmu.hydro_recent``)
for the last closed UTC day and seals today's spool day with its answers; the other
captures are sealed from the spool; IMGW-PIB's telemetry is checked by the datastore's
listing alone and ČHMÚ's hourly years by their directory listing and a HEAD.

The answers are those recorded on 2026-11-23 (``tests/fixtures/operational``,
``recordings.json``). Every test has its own spool (``OBSERWATOR_STATE_DIR``),
``nogat.toml`` and a fake clock (`obserwator.fetch._clock`, `obserwator.captures._now`)
at the recording's time, so a harvest asks the recorded ``hoursInterval`` and no test
sleeps.
"""

import gzip
import json
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime
from itertools import pairwise
from pathlib import Path
from urllib.parse import parse_qs

import httpx
import pytest
import respx

from obserwator import captures, fetch
from obserwator.captures import spool_root, write_spool
from obserwator.commands import run_command
from obserwator.exceptions import ObserwatorValidationError
from obserwator.fetch import BACKOFF, MIN_SPACING, pace_deadline
from obserwator.providers.base import Answer
from obserwator.providers.cz.chmu import ChmuAdapter
from obserwator.store import check_store, init_store, iter_store, sync_store
from tests.unit.test_paced import CASES, FIXTURES, RECORDINGS, FakeClock

OPERATIONAL = "pl.imgw.hydro_operational"
RECENT = "cz.chmu.hydro_recent"
CURRENT = "cz.chmu.hydro_current"
TELEMETRY = "pl.imgw.hydro_telemetry"
HOURLY = "cz.chmu.hydro_hourly"
RECORDED_AT = datetime.fromisoformat(RECORDINGS["recorded_at"])
TODAY = RECORDED_AT.date()
HARVESTED = TODAY - timedelta(days=1)
HYDRO_BACK = "https://hydro-back.imgw.pl/station/hydro/"
CHMU_RECENT = "https://opendata.chmi.cz/hydrology/recent/data/"
FILES_LIST = "https://danepubliczne.imgw.pl/datastore/getFilesList"
TELEMETRY_ZIP = CASES["telemetry_zip"]["url"]
HOURLY_FILE = CASES["chmu_hourly_2025"]["url"]
CODE = "0-203-1-001000"


def body(case):
    return (FIXTURES / CASES[case]["file"]).read_bytes()


def sidecar(version):
    return json.loads(Path(f"{version}.meta.json").read_text(encoding="utf-8"))


def lines(version):
    """The JSON object of every answer of a sealed capture file."""
    text = gzip.decompress(Path(version).read_bytes()).decode("utf-8")
    return [json.loads(line) for line in text.splitlines()]


def until(minutes):
    """The ``HH:MM`` of local time ``minutes`` after the recording, as pace_deadline reads."""
    return (RECORDED_AT + timedelta(minutes=minutes)).astimezone().strftime("%H:%M")


@pytest.fixture(autouse=True)
def clock(tmp_path, monkeypatch):
    """The test's spool and ``nogat.toml``; the run's clock and the spool's at recorded_at."""
    monkeypatch.setenv("OBSERWATOR_STATE_DIR", str(tmp_path / "state"))
    config = tmp_path / "nogat.toml"
    config.write_text("", encoding="utf-8")
    monkeypatch.setenv("NOGAT_CONFIG", str(config))
    fake = FakeClock(RECORDED_AT)
    monkeypatch.setattr(fetch, "_clock", lambda: fake)
    monkeypatch.setattr(captures, "_now", fake.now)
    return fake


@pytest.fixture
def raw(tmp_path):
    return init_store(tmp_path / "raw").root


@pytest.fixture
def server():
    """Only the routes a test gives answer; any other request fails the test."""
    with respx.mock(assert_all_called=False) as mock:
        yield mock


def serve(server, clock, *cases, replies=None):
    """
    Answer the recorded GETs of ``cases``; note each request's time on the clock.

    ``replies`` replaces the answers of an address by a queue of statuses.
    """
    times = []
    for case in cases:
        item = CASES[case]
        queue = list((replies or {}).get(item["url"], ()))

        def answer(request, item=item, queue=queue):
            times.append((clock.now(), str(request.url)))
            status = queue.pop(0) if queue else item["status"]
            content = body(item["case"]) if status == item["status"] else b""
            return httpx.Response(status, content=content)

        server.get(item["url"]).mock(side_effect=answer)
    return times


_HTML = {"Content-Type": "text/html; charset=UTF-8"}


def serve_files_list(server):
    """The datastore's POST getFilesList: the recorded listing of the form's ``path``."""

    def answer(request):
        (path,) = parse_qs(request.content.decode("utf-8"))["path"]
        year = path.rsplit("/", 1)[-1]
        return httpx.Response(
            200, content=body(f"telemetry_listing_{year}"), headers=_HTML
        )

    return server.post(FILES_LIST).mock(side_effect=answer)


_OPERATIONAL_CASES = [
    "map",
    "api_hydro",
    *(
        case
        for case in CASES
        if case.startswith(("status_data_", "discharge_", "water-temperature_"))
    ),
]
_RECENT_CASES = [
    "chmu_meta1",
    *(case for case in CASES if case.startswith("chmu_recent_")),
]


# --------------------------------------------------------------------------
# A harvest, then today's spool day sealed
# --------------------------------------------------------------------------


def test_a_harvest_of_hydro_back_seals_its_answers_into_todays_private_version(
    raw, server, clock
):
    times = serve(server, clock, *_OPERATIONAL_CASES)
    notices = []

    report = sync_store(
        raw, datasets=[OPERATIONAL], pace_until=until(-60), on_notice=notices.append
    )

    (item,) = report.items
    assert (item.slot, item.status) == (
        f"archive:{OPERATIONAL}:{TODAY}.jsonl.gz",
        "new",
    )
    # The map and api/data/hydro name the stations; one request per station and
    # series it measures (154190080 has no discharge), the recorded hoursInterval.
    asked = [url for _, url in times]
    assert asked[:2] == [CASES["map"]["url"], CASES["api_hydro"]["url"]]
    assert sorted(asked[2:]) == sorted(
        CASES[case]["url"] for case in _OPERATIONAL_CASES[2:]
    )
    harvest = report.harvest
    assert (harvest.dataset, harvest.start, harvest.end) == (
        OPERATIONAL,
        HARVESTED,
        HARVESTED,
    )
    assert (harvest.stations, harvest.planned, harvest.requests, harvest.answers) == (
        3,
        8,
        10,
        10,
    )
    assert (harvest.failed, harvest.skipped, harvest.stopped) == (0, (), False)
    # Today's version holds the eight series, its spool day is gone; the station
    # lists went to the spools of their own captures, which this run does not seal.
    meta = sidecar(item.version)
    assert (meta["tier"], meta["publication"]) == ("operational", "private")
    assert meta["extra"]["capture"] == {"answers": 8}
    assert sorted(line["address"] for line in lines(item.version)) == sorted(asked[2:])
    assert {path.parent.parent.name for path in spool_root().rglob("*.json")} == {
        "pl.imgw.hydro_states_current",
        "pl.imgw.hydro_current",
    }
    assert [notice.code for notice in notices if notice.code.startswith("harvest")] == [
        "harvest_done"
    ]


def test_a_harvest_is_spread_to_its_deadline_and_never_faster_than_one_request_in_5_s(
    raw, server, clock
):
    times = serve(server, clock, *_OPERATIONAL_CASES)
    pace = until(60)
    deadline = pace_deadline(pace, now=RECORDED_AT)

    sync_store(raw, datasets=[OPERATIONAL], pace_until=pace)

    moments = [moment for moment, _ in times]
    assert len(moments) == 10
    assert all(
        (later - earlier).total_seconds() >= MIN_SPACING
        for earlier, later in pairwise(moments)
    )
    if deadline > RECORDED_AT + timedelta(seconds=10 * MIN_SPACING):
        # The planned requests fill the time to the deadline, the last a spacing
        # before it.
        assert moments[-1] < deadline
        assert (moments[-1] - moments[2]).total_seconds() > 30 * 60


def test_a_harvest_of_chmu_recent_seals_its_day_files_and_the_404_into_a_public_version(
    raw, server, clock
):
    times = serve(server, clock, *_RECENT_CASES)

    report = sync_store(raw, datasets=[RECENT], pace_until=until(-60))

    (item,) = report.items
    assert item.status == "new"
    assert [url for _, url in times] == [CASES[case]["url"] for case in _RECENT_CASES]
    assert all(
        request.headers["User-Agent"].startswith("obserwator/")
        for request in (call.request for call in server.calls)
    )
    meta = sidecar(item.version)
    assert (meta["tier"], meta["publication"]) == ("operational", "public")
    assert sorted(
        (line["address"], line["status"]) for line in lines(item.version)
    ) == [
        (f"{CHMU_RECENT}{HARVESTED:%Y%m%d}_0-203-1-001000.json", 200),
        (f"{CHMU_RECENT}{HARVESTED:%Y%m%d}_0-203-1-002000.json", 200),
        (f"{CHMU_RECENT}{HARVESTED:%Y%m%d}_0-203-1-089500.json", 404),
    ]
    assert (report.harvest.planned, report.harvest.answers, report.harvest.failed) == (
        3,
        4,
        0,
    )


def test_a_station_refused_after_the_backoff_leaves_a_partial_sync(raw, server, clock):
    refused = f"{CHMU_RECENT}{HARVESTED:%Y%m%d}_0-203-1-002000.json"
    serve(
        server,
        clock,
        *_RECENT_CASES[1:3],
        replies={refused: [503] * (len(BACKOFF) + 1)},
    )

    envelope = run_command(
        "store sync",
        options={
            "root": raw,
            "datasets": [RECENT],
            "stations": [CODE, "0-203-1-002000"],
            "pace_until": until(-60),
        },
    )

    assert envelope.status == "partial"
    new, failed = envelope.result.items
    assert new.status == "new"
    assert (failed.slot, failed.status, failed.error_code) == (
        None,
        "failed",
        "source_unavailable",
    )
    # Asked once and after each wait of the backoff; skipped, not failed.
    harvest = envelope.result.harvest
    assert (harvest.requests, harvest.answers, harvest.failed, harvest.skipped) == (
        2 + len(BACKOFF),
        2 + len(BACKOFF),
        0,
        ("0-203-1-002000",),
    )


def test_chmu_current_is_spooled_by_its_live_tail_and_sealed_when_the_day_is_closed(
    raw, server, clock
):
    serve(server, clock, "chmu_now")

    (answer,) = ChmuAdapter().live_tail(CODE, hours=1, timeout=5.0)

    assert answer.dataset == CURRENT
    assert sync_store(raw, datasets=[CURRENT]).items == ()
    clock.moment += timedelta(days=1)
    (item,) = sync_store(raw, datasets=[CURRENT]).items
    assert (item.slot, item.status) == (f"archive:{CURRENT}:{TODAY}.jsonl.gz", "new")
    meta = sidecar(item.version)
    assert (meta["tier"], meta["publication"]) == ("operational", "public")
    assert [line["address"] for line in lines(item.version)] == [
        CASES["chmu_now"]["url"]
    ]


@pytest.mark.parametrize(
    ("dataset", "address"),
    [
        (
            "pl.imgw.meteo_operational",
            "https://hydro-back.imgw.pl/station/meteo/status?id=252200150",
        ),
        (
            "pl.imgw.meteo_states_current",
            "https://hydro-back.imgw.pl/map/stations/meteorologic?onlyMainStations=false",
        ),
    ],
)
def test_the_meteo_captures_of_hydro_back_are_sealed_private(raw, dataset, address):
    write_spool(Answer(address, RECORDED_AT - timedelta(days=1), 200, b"{}", dataset))

    (item,) = sync_store(raw, datasets=[dataset]).items

    assert (item.slot, item.status) == (
        f"archive:{dataset}:{HARVESTED}.jsonl.gz",
        "new",
    )
    meta = sidecar(item.version)
    assert (meta["tier"], meta["publication"]) == ("operational", "private")


# --------------------------------------------------------------------------
# The telemetry by the datastore's listing; ČHMÚ's hourly years
# --------------------------------------------------------------------------


def test_the_telemetry_is_checked_by_its_listing_and_downloaded_without_a_head(
    raw, server, clock
):
    listing = serve_files_list(server)
    serve(server, clock, "telemetry_zip")
    selection = {"datasets": [TELEMETRY], "years": [2026, 2030], "months": [10, 11]}

    plan = check_store(raw, **selection)
    report = sync_store(raw, **selection)

    assert [
        (item.archive.server_path, item.status, item.signal) for item in plan.items
    ] == [
        ("Arch/Telemetria/Hydro/2026/Hydro_2026-10.zip", "missing", "listing"),
        ("Arch/Telemetria/Hydro/2026/Hydro_2026-11.zip", "unverifiable", "listing"),
        ("Arch/Telemetria/Hydro/2030/Hydro_2030-10.zip", "unverifiable", "listing"),
        ("Arch/Telemetria/Hydro/2030/Hydro_2030-11.zip", "unverifiable", "listing"),
    ]
    assert {item.error for item in plan.items[1:]} == {"not published"}
    # One listing per year folder; the GET of the listed file is the plan's request.
    assert plan.requests == {"made": 2, "planned": 1}
    assert [(item.status, item.error) for item in report.items] == [
        ("new", None),
        ("unchanged", "not published"),
        ("unchanged", "not published"),
        ("unchanged", "not published"),
    ]
    # One listing per year folder and run; the zip has no HEAD, only its GET.
    assert listing.call_count == 4
    assert [call.request.method for call in server.calls].count("HEAD") == 0
    zip_gets = [call for call in server.calls if str(call.request.url) == TELEMETRY_ZIP]
    assert len(zip_gets) == 1
    meta = sidecar(report.items[0].version)
    assert (meta["tier"], meta["publication"]) == ("telemetry", "public")
    assert Path(report.items[0].version).read_bytes() == body("telemetry_zip")

    again = sync_store(raw, **selection)
    forced = sync_store(raw, force=True, **selection)

    assert again.items[0].status == "unchanged"
    assert forced.items[0].status == "unchanged"
    zip_gets = [call for call in server.calls if str(call.request.url) == TELEMETRY_ZIP]
    assert len(zip_gets) == 2  # --force asks it again and compares the bytes
    assert [call.request.method for call in server.calls].count("HEAD") == 0


def test_an_unreadable_telemetry_listing_fails_its_files(raw, server):
    server.post(FILES_LIST).mock(side_effect=httpx.ConnectError("refused"))

    plan = check_store(raw, datasets=[TELEMETRY], years=[2026], months=[10])

    (item,) = plan.items
    assert (item.status, item.signal) == ("check_failed", "listing")
    (result,) = sync_store(raw, datasets=[TELEMETRY], years=[2026], months=[10]).items
    assert (result.status, result.error_code) == ("failed", "source_unavailable")


def test_a_cancelled_telemetry_check_asks_no_listing(raw, server):
    plan = check_store(
        raw, datasets=[TELEMETRY], years=[2026], months=[9, 10], cancel=lambda: True
    )

    assert plan.cancelled
    assert [(item.status, item.error) for item in plan.items] == [
        ("unverifiable", "cancelled"),
        ("unverifiable", "cancelled"),
    ]
    assert not server.calls


def test_a_chmu_hourly_year_is_found_by_its_listing_and_checked_by_head(
    raw, server, clock
):
    serve(server, clock, "chmu_hourly_listing", "chmu_hourly_2025")
    modified = datetime(2026, 5, 21, 11, 30, 2, tzinfo=UTC)
    server.head(HOURLY_FILE).mock(
        return_value=httpx.Response(
            200,
            headers={
                "Last-Modified": format_datetime(modified, usegmt=True),
                "Content-Length": "513517",
                "ETag": '"6a0eecba-7d5ed"',
            },
        )
    )

    report = sync_store(raw, datasets=[HOURLY], stations=[CODE], years=[2025])

    (item,) = report.items
    assert (item.slot, item.status) == (
        f"archive:{HOURLY}:H_{CODE}_HQ_2025.json",
        "new",
    )
    assert [call.request.method for call in server.calls] == ["GET", "HEAD", "GET"]
    meta = sidecar(item.version)
    assert {"tier", "publication"}.isdisjoint(meta)
    assert meta["content_form"] == "chmu-json/1"


# --------------------------------------------------------------------------
# What pace_until refuses, and the plan of a harvest
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("options", "option", "reason"),
    [
        ({"datasets": ["pl.imgw.hydro_current"]}, "pace_until", "not_harvested"),
        ({"datasets": [OPERATIONAL, RECENT]}, "pace_until", "not_harvested"),
        ({"datasets": [TELEMETRY], "years": [2026]}, "pace_until", "not_harvested"),
        ({"datasets": [OPERATIONAL], "years": [2026]}, "years", "captures"),
        ({"datasets": [RECENT], "months": [11]}, "months", "captures"),
    ],
    ids=["no harvest", "two datasets", "not a capture", "years", "months"],
)
def test_pace_until_names_exactly_one_harvest_dataset(
    raw, server, options, option, reason
):
    with pytest.raises(ObserwatorValidationError) as exc:
        sync_store(raw, pace_until="06:00", **options)

    assert (exc.value.details["option"], exc.value.details["reason"]) == (
        option,
        reason,
    )
    assert not server.calls


def test_pace_until_is_refused_with_a_plan_and_in_plain_mode(raw, tmp_path, server):
    plan = check_store(raw, datasets=[OPERATIONAL])

    with pytest.raises(ObserwatorValidationError):
        sync_store(raw, plan=plan, pace_until="06:00")
    with pytest.raises(ObserwatorValidationError) as plain:
        sync_store(output_dir=tmp_path, datasets=[OPERATIONAL], pace_until="06:00")

    assert plain.value.details == {
        "option": "pace_until",
        "value": "06:00",
        "reason": "store_only_option",
    }
    assert not server.calls


def test_store_check_with_pace_until_plans_the_harvest_and_todays_spool_day(
    raw, server
):
    address = CASES["status_data_151160060"]["url"]
    write_spool(Answer(address, RECORDED_AT, 200, b"{}", OPERATIONAL))

    plain = check_store(raw, datasets=[OPERATIONAL])
    plan = check_store(
        raw, datasets=[OPERATIONAL], pace_until="06:00", stations=["151160060"]
    )

    assert (plain.items, plain.actions) == ((), ())
    (item,) = plan.items
    assert (item.archive.dataset, item.status) == (OPERATIONAL, "missing")
    assert item.archive.server_path.endswith(f"/{TODAY}.jsonl.gz")
    (action,) = plan.actions
    assert (action.command, action.status) == ("store sync", "missing")
    assert OPERATIONAL in action.detail
    assert str(HARVESTED) in action.detail
    assert "151160060" in action.detail
    assert "06:00" in action.detail
    assert not server.calls
    assert [entry.slot for entry in iter_store(raw)] == []
