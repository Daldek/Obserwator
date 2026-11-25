"""check_store and sync_store for the month files of Gdańskie Wody (ADR-034).

The station list the raw root holds names the files of ``pl.gdanskiewody.measurements``
(check scope ``months``): a check makes no request, a month is ``current`` once a version
downloaded after it settled is stored, and a sync gathers each day's answer of a month
into one file without a HEAD. The answers are those of ``gdanskiewody_recordings.json``
(served with respx) or synthetic days; the clock of the run (`obserwator.fetch._clock`)
and the writer's ``downloaded_at`` follow a fake clock, which the pacing of the adapter
moves instead of sleeping.
"""

import copy
import json
import re
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import httpx
import pytest
import respx

from obserwator import CommandCall, check_command, command_for_version, fetch
from obserwator._parsing.gdanskiewody import encode_month
from obserwator.exceptions import ObserwatorStoreError, ObserwatorValidationError
from obserwator.fetch import DownloadResult
from obserwator.store import init_store, write_archive, writer
from obserwator.store.sync import CANCELLED, check_store, sync_store
from obserwator.testing import fixture_files
from tests.unit.test_paced import FakeClock

RECORDING = json.loads(
    fixture_files().joinpath("gdanskiewody_recordings.json").read_text(encoding="utf-8")
)
BASE = RECORDING["base_url"]
CASES = {entry["case"]: entry for entry in RECORDING["interactions"]}
STATIONS = "pl.gdanskiewody.station_list"
MEASUREMENTS = "pl.gdanskiewody.measurements"
STATION = "GDANSKIEWODY-1"
RAIN = "rest/measurements/1/rain/2026-11.json"
RAIN_DAYS = ("m_1_rain_20261101", "m_1_rain_20261102", "m_1_rain_20261103")
NOVEMBER_3 = datetime(2026, 11, 3, 9, 30, tzinfo=UTC)
SETTLED = datetime(2026, 12, 1, 12, tzinfo=UTC)
"""When November settles: 06:00 UTC of 1 December, the end of its last day, + 6 h."""
SETTLED_HTTP = "Tue, 01 Dec 2026 12:00:00 GMT"


@pytest.fixture(autouse=True)
def clock(tmp_path, monkeypatch):
    """The test's state and ``nogat.toml``, a key, and the clock on 2026-11-03."""
    monkeypatch.setenv("OBSERWATOR_STATE_DIR", str(tmp_path / "state"))
    config = tmp_path / "nogat.toml"
    config.write_text("", encoding="utf-8")
    monkeypatch.setenv("NOGAT_CONFIG", str(config))
    monkeypatch.setenv("OBSERWATOR_GDANSKIE_WODY_API_KEY", "test-key")
    fake = FakeClock(NOVEMBER_3)
    monkeypatch.setattr(fetch, "_clock", lambda: fake)

    class Clock(datetime):
        """The writer stamps ``downloaded_at`` by the test's clock."""

        @classmethod
        def now(cls, tz=None):
            return fake.now().astimezone(tz)

    monkeypatch.setattr(writer, "datetime", Clock)
    return fake


@pytest.fixture
def raw(tmp_path):
    return init_store(tmp_path / "raw").root


@pytest.fixture
def server():
    """Only the routes a test gives answer; any other request fails the test."""
    with respx.mock(assert_all_called=False) as mock:
        yield mock


def serve(router, *cases):
    """Answer the recorded GET of each case."""
    for case in cases:
        entry = CASES[case]
        router.get(BASE + entry["path"]).mock(
            return_value=httpx.Response(entry["status"], json=entry["json"])
        )


def listed(changes):
    """The recorded station list, the quantities of some stations changed by number."""
    payload = copy.deepcopy(CASES["stations"]["json"])
    for station in payload["data"]:
        station.update(changes.get(station["no"], {}))
    return payload


def store_stations(raw, router, payload=None):
    """``store sync`` of the station list, from the recorded answer or ``payload``."""
    router.get(BASE + "rest/stations").mock(
        return_value=httpx.Response(200, json=payload or CASES["stations"]["json"])
    )
    report = sync_store(raw, datasets=[STATIONS])
    assert [item.status for item in report.items] == ["new"]


def quiet_day(day):
    """A day's answer without values: its 24 hours, 06:00 to 05:00 UTC, each null."""
    first = datetime(day.year, day.month, day.day, 6)
    hours = [first + timedelta(hours=offset) for offset in range(24)]
    return {
        "status": "success",
        "message": "synthetic day",
        "data": [[hour.strftime("%Y-%m-%d %H:%M:%S"), None] for hour in hours],
    }


def serve_days(router, number, symbol):
    """Answer every day asked of a station's quantity with `quiet_day`."""

    def answer(request):
        day = date.fromisoformat(request.url.path.rpartition("/")[2])
        return httpx.Response(200, json=quiet_day(day))

    address = re.escape(f"{BASE}rest/measurements/{number}/{symbol}/")
    return router.get(url__regex=rf"^{address}\d{{4}}-\d{{2}}-\d{{2}}$").mock(
        side_effect=answer
    )


def check(raw, **selectors):
    selectors = {"years": 2026, "months": 11, "stations": [STATION], **selectors}
    return check_store(raw, datasets=[MEASUREMENTS], **selectors)


def sync(raw, **selectors):
    selectors = {"years": 2026, "months": 11, "stations": [STATION], **selectors}
    return sync_store(raw, datasets=[MEASUREMENTS], **selectors)


def sidecar(version):
    return json.loads(Path(f"{version}.meta.json").read_text(encoding="utf-8"))


def asked(router, start=0):
    return [
        (call.request.method, str(call.request.url).removeprefix(BASE))
        for call in router.calls[start:]
    ]


# --------------------------------------------------------------------------
# Refusals before any request
# --------------------------------------------------------------------------


def test_month_files_need_the_station_list_of_the_raw_root(raw, server):
    with pytest.raises(ObserwatorStoreError) as error:
        check(raw)

    assert error.value.code == "not_found"
    assert error.value.details == {"reason": "missing_source", "datasets": [STATIONS]}
    assert f"store sync --root {raw} --datasets {STATIONS}" in str(error.value.hint)
    assert not server.calls


@pytest.mark.parametrize(
    ("selectors", "details"),
    [
        ({"years": None}, {"option": "years", "value": None}),
        ({"years": 2004}, {"option": "years", "value": [2004], "minimum": 2005}),
        ({"months": 13}, {"option": "months"}),
        ({"stations": ["0-203-1-001000"]}, {"option": "stations"}),
    ],
    ids=["no_years", "before_first_year", "no_month", "code_of_another_provider"],
)
def test_selectors_are_refused_before_the_station_list_is_read(
    raw, server, selectors, details
):
    # The raw root holds no station list: a refusal after reading it would be
    # not_found instead.
    with pytest.raises(ObserwatorValidationError) as error:
        check(raw, **selectors)

    assert error.value.details.items() >= details.items()
    assert not server.calls


def test_plain_mode_refuses_the_month_files_before_any_request(tmp_path, server):
    target = tmp_path / "plain"

    with pytest.raises(ObserwatorValidationError) as error:
        sync_store(
            output_dir=target,
            datasets=[MEASUREMENTS],
            years=2026,
            months=11,
            stations=[STATION],
        )

    assert error.value.details == {"option": "datasets", "reason": "store_only_dataset"}
    assert not target.exists()
    assert not server.calls


# --------------------------------------------------------------------------
# Check: the stored station list and the clock, no request
# --------------------------------------------------------------------------


def test_a_check_names_the_month_files_of_the_stored_list_without_a_request(
    raw, server
):
    store_stations(raw, server)
    before = len(server.calls)
    notices = []

    plan = check(raw, stations=[STATION, "GDANSKIEWODY-3"], on_notice=notices.append)

    (item,) = plan.items
    assert (item.archive.server_path, item.status, item.station_code) == (
        RAIN,
        "missing",
        STATION,
    )
    assert item.local_path is None
    # The three days of November up to today are the GETs a sync makes.
    assert plan.requests == {"made": 0, "planned": 3}
    assert len(server.calls) == before
    (action,) = plan.actions
    assert (action.command, action.status) == ("store sync", "unverifiable")
    assert "GDANSKIEWODY-3" in action.detail
    assert [(notice.level, notice.code) for notice in notices] == [
        ("warning", "source_unverifiable")
    ]


def test_a_month_not_begun_by_today_is_no_file(raw, server):
    store_stations(raw, server)

    plan = check(raw, years="2026-2027", months=None)

    assert [(item.archive.year, item.archive.month) for item in plan.items] == [
        (2026, month) for month in range(1, 12)
    ]
    # Every day of January to October, and November up to today.
    assert plan.requests == {"made": 0, "planned": 304 + 3}


def test_a_cancelled_check_leaves_the_remaining_month_files_unverifiable(raw, server):
    store_stations(raw, server)
    polls = iter([False])

    plan = check(raw, months=[10, 11], cancel=lambda: next(polls, True))

    assert [(item.archive.month, item.status, item.error) for item in plan.items] == [
        (10, "missing", None),
        (11, "unverifiable", CANCELLED),
    ]
    assert plan.items[1].station_code == STATION
    assert plan.cancelled
    assert plan.requests == {"made": 0, "planned": 31}


@pytest.mark.parametrize(
    ("downloaded", "status"),
    [(SETTLED - timedelta(seconds=1), "newer"), (SETTLED, "current")],
    ids=["before_settled", "settled"],
)
def test_a_version_is_current_once_downloaded_after_its_month_settled(
    raw, server, clock, downloaded, status
):
    store_stations(raw, server)
    (item,) = check(raw).items
    clock.moment = downloaded
    first = date(2026, 11, 1)
    data = encode_month({first: quiet_day(first)})
    response = DownloadResult(data, item.archive.url, None, None, None)
    written = write_archive(raw, archive=item.archive, response=response)

    plan = check(raw)

    (checked,) = plan.items
    assert (checked.status, checked.local_path) == (
        status,
        written.path.relative_to(raw),
    )
    assert plan.requests["planned"] == (30 if status == "newer" else 0)


# --------------------------------------------------------------------------
# Sync: each day's answer into the month's file, no HEAD
# --------------------------------------------------------------------------


def test_a_sync_gathers_the_days_up_to_today_into_one_version(raw, server):
    store_stations(raw, server)
    serve(server, *RAIN_DAYS)
    before = len(server.calls)

    report = sync(raw)

    (result,) = report.items
    assert (result.slot, result.status) == (
        f"archive:{MEASUREMENTS}:1/rain/2026-11.json",
        "new",
    )
    answers = {
        date(2026, 11, day): CASES[case]["json"]
        for day, case in enumerate(RAIN_DAYS, start=1)
    }
    assert result.version.read_bytes() == encode_month(answers)
    assert sidecar(result.version)["extra"]["http"]["last_modified"] is None
    assert asked(server, before) == [
        ("GET", f"rest/measurements/1/rain/2026-11-0{day}") for day in (1, 2, 3)
    ]
    # The month is open: the next check, the same day, wants it again.
    (item,) = check(raw).items
    assert (item.status, item.local_path) == (
        "newer",
        result.version.relative_to(raw),
    )


def test_a_month_synced_once_it_settled_is_current(raw, server, clock):
    store_stations(raw, server)
    days = serve_days(server, 1, "rain")
    clock.moment = SETTLED

    (result,) = sync(raw).items

    assert result.status == "new"
    assert days.call_count == 30
    assert sidecar(result.version)["extra"]["http"]["last_modified"] == SETTLED_HTTP
    plan = check(raw)
    assert [item.status for item in plan.items] == ["current"]
    assert plan.requests == {"made": 0, "planned": 0}


def test_the_same_bytes_asked_once_the_month_settled_are_relabeled(raw, server, clock):
    store_stations(raw, server)
    serve_days(server, 1, "rain")
    # The month is over, its last day not settled yet: every day asked, no time.
    clock.moment = datetime(2026, 12, 1, 8, tzinfo=UTC)
    (early,) = sync(raw).items
    assert early.status == "new"
    assert [item.status for item in check(raw).items] == ["newer"]
    clock.moment = SETTLED

    (late,) = sync(raw).items

    assert late.status == "relabeled"
    assert late.version != early.version
    assert late.version.read_bytes() == early.version.read_bytes()
    assert sidecar(late.version)["extra"]["http"]["last_modified"] == SETTLED_HTTP
    (item,) = check(raw).items
    assert (item.status, item.local_path) == ("current", late.version.relative_to(raw))


def test_force_asks_a_settled_month_again_and_keeps_equal_bytes(raw, server, clock):
    store_stations(raw, server)
    days = serve_days(server, 1, "rain")
    clock.moment = SETTLED
    (first,) = sync(raw).items
    clock.moment = SETTLED + timedelta(days=3)

    (kept,) = sync(raw).items
    assert (kept.status, kept.version, days.call_count) == (
        "unchanged",
        first.version,
        30,
    )

    (forced,) = sync(raw, force=True).items

    assert (forced.status, forced.version) == ("unchanged", first.version)
    assert days.call_count == 60


def test_a_day_the_provider_refuses_fails_only_its_month_file(raw, server):
    # The list says station 1 also measures the water level; the API refuses it (-13).
    store_stations(raw, server, listed({1: {"water": True}}))
    serve(server, *RAIN_DAYS, *(f"m_4_water_2026110{day}" for day in (1, 2, 3)))
    refused = server.get(
        url__regex=rf"^{re.escape(BASE)}rest/measurements/1/water/.*$"
    ).mock(return_value=httpx.Response(200, json=CASES["m_1_water_20261103"]["json"]))

    report = sync(raw, stations=[STATION, "GDANSKIEWODY-4"])

    assert [
        (result.slot.rpartition(":")[2], result.status, result.error_code)
        for result in report.items
    ] == [
        ("1/rain/2026-11.json", "new", None),
        ("1/water/2026-11.json", "failed", "no_data"),
        ("4/water/2026-11.json", "new", None),
    ]
    # The month stops at its first refused day.
    assert refused.call_count == 1


def test_a_saved_plan_of_month_files_is_carried_out_without_a_head(
    raw, server, tmp_path
):
    store_stations(raw, server)
    serve(server, *RAIN_DAYS)
    saved = tmp_path / "plan.json"
    check(raw, plan=saved)
    before = len(server.calls)

    report = sync_store(raw, plan=saved)

    assert [result.status for result in report.items] == ["new"]
    assert asked(server, before) == [
        ("GET", f"rest/measurements/1/rain/2026-11-0{day}") for day in (1, 2, 3)
    ]


def test_the_version_command_of_a_month_file_plans_it_again(raw, server):
    store_stations(raw, server)
    serve(server, *RAIN_DAYS)
    (result,) = sync(raw).items

    call = command_for_version(result.version.relative_to(raw), root=raw)

    assert call == CommandCall(
        "store sync",
        {
            "root": str(raw),
            "datasets": [MEASUREMENTS],
            "stations": [STATION],
            "years": ["2026"],
            "months": ["11"],
        },
        {},
    )
    plan = check_command(call.command, options=call.options).result
    assert [(item.archive.server_path, item.status) for item in plan.items] == [
        (RAIN, "newer")
    ]
