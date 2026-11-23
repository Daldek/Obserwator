"""Paced requests of a harvest: spacing, deadline, backoff, stop (ADR-030 D9).

Every test runs on a fake clock (no real sleep): the clock moves only when the session
waits, and each recorded request notes the clock's time, so the spacing is asserted
from the request times. The answers are recorded ones of hydro-back
(``tests/fixtures/operational``); the spool lies in the test's ``state_dir``.
"""

import json
from datetime import UTC, datetime, timedelta, timezone
from itertools import pairwise
from pathlib import Path

import httpx
import pytest
import respx

from obserwator.captures import spool_root
from obserwator.exceptions import ObserwatorValidationError
from obserwator.fetch import (
    BACKOFF,
    MIN_SPACING,
    PacedRequest,
    PacedSession,
    pace_deadline,
)

FIXTURES = Path(__file__).parents[1] / "fixtures" / "operational"
RECORDINGS = json.loads((FIXTURES / "recordings.json").read_text(encoding="utf-8"))
CASES = {item["case"]: item for item in RECORDINGS["interactions"]}
START = datetime(2026, 11, 23, 1, 30, tzinfo=UTC)


class FakeClock:
    """A clock that moves only when the session sleeps."""

    def __init__(self, moment):
        self.moment = moment

    def now(self):
        return self.moment

    def sleep(self, seconds):
        self.moment += timedelta(seconds=seconds)


@pytest.fixture(autouse=True)
def state_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("OBSERWATOR_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("NOGAT_CONFIG", str(tmp_path / "nogat.toml"))


def recorded(case):
    """The body and status of a recorded answer."""
    item = CASES[case]
    return item["status"], (FIXTURES / item["file"]).read_bytes()


def serve(server, clock, answers):
    """Answer each URL from its queue of (status or exception); note request times."""
    times = []

    def answer(request):
        times.append((clock.now(), str(request.url)))
        reply = answers[str(request.url)].pop(0)
        if isinstance(reply, Exception):
            raise reply
        status, body = reply
        return httpx.Response(status, content=body)

    server.route().mock(side_effect=answer)
    return times


def requests_of(*cases):
    return [
        PacedRequest(CASES[case]["url"], CASES[case]["url"].split("id=")[1][:9])
        for case in cases
    ]


@pytest.fixture
def server():
    with respx.mock(assert_all_called=False) as mock:
        yield mock


H, Q, T = "status_data_151160060", "discharge_151160060", "water-temperature_151160060"


def test_without_deadline_every_request_waits_the_minimum_spacing(server):
    clock = FakeClock(START)
    planned = requests_of(H, Q, T)
    times = serve(
        server,
        clock,
        {r.url: [recorded(c)] for r, c in zip(planned, (H, Q, T), strict=True)},
    )

    with PacedSession(clock=clock) as session:
        outcomes = session.run(planned)

    assert [o.status for o in outcomes] == ["answered"] * 3
    gaps = [(b[0] - a[0]).total_seconds() for a, b in pairwise(times)]
    assert gaps == [MIN_SPACING, MIN_SPACING]
    # Each answer of hydro-back's series is kept in the spool of its capture dataset.
    kept = list((spool_root() / "pl.imgw.hydro_operational").rglob("*.json"))
    assert len(kept) == 3


def test_a_deadline_spreads_the_requests_evenly_before_it(server):
    clock = FakeClock(START)
    planned = requests_of(H, Q, T)
    times = serve(
        server,
        clock,
        {r.url: [recorded(c)] for r, c in zip(planned, (H, Q, T), strict=True)},
    )

    with PacedSession(clock=clock, deadline=START + timedelta(seconds=120)) as session:
        session.run(planned)

    # The first at once, the others (120 s) / (left + 1) apart: the last one a
    # spacing before the deadline.
    assert [moment for moment, _ in times] == [
        START,
        START + timedelta(seconds=40),
        START + timedelta(seconds=80),
    ]


def test_a_deadline_passed_gives_the_minimum_spacing(server):
    clock = FakeClock(START)
    planned = requests_of(H, Q)
    times = serve(
        server,
        clock,
        {r.url: [recorded(c)] for r, c in zip(planned, (H, Q), strict=True)},
    )

    with PacedSession(clock=clock, deadline=START - timedelta(hours=1)) as session:
        session.run(planned)

    assert (times[1][0] - times[0][0]).total_seconds() == MIN_SPACING


def test_a_refused_station_is_backed_off_then_skipped_until_the_next_run(server):
    clock = FakeClock(START)
    refused = (503, b"busy")
    planned = [*requests_of(H, Q), *requests_of("status_data_154190080")]
    times = serve(
        server,
        clock,
        {
            planned[0].url: [refused] * 4,
            planned[2].url: [recorded("status_data_154190080")],
        },
    )

    with PacedSession(clock=clock) as session:
        outcomes = session.run(planned)

    assert [o.status for o in outcomes] == ["skipped", "skipped", "answered"]
    assert outcomes[0].attempts == 4
    assert outcomes[0].http_status == 503
    # 60, 120 and 240 s between the attempts; Q of the station is not asked.
    offsets = [(moment - START).total_seconds() for moment, _ in times]
    assert offsets[:4] == [0, BACKOFF[0], BACKOFF[0] + BACKOFF[1], sum(BACKOFF)]
    assert [url for _, url in times].count(planned[1].url) == 0
    assert offsets[4] == sum(BACKOFF) + MIN_SPACING


def test_three_connection_failures_in_a_row_end_the_run(server):
    clock = FakeClock(START)
    planned = requests_of(H, Q, T, "status_data_154190080")
    failure = httpx.ConnectError("refused")
    serve(server, clock, {r.url: [failure] for r in planned})

    with PacedSession(clock=clock) as session:
        outcomes = session.run(planned)

    assert [o.status for o in outcomes] == ["failed", "failed", "failed", "stopped"]
    assert session.requests == 3


def test_any_answer_resets_the_count_of_connection_failures(server):
    clock = FakeClock(START)
    planned = requests_of(H, Q, T, "status_data_154190080")
    failure = httpx.ConnectError("refused")
    serve(
        server,
        clock,
        {
            planned[0].url: [failure],
            planned[1].url: [failure],
            planned[2].url: [recorded(T)],
            planned[3].url: [failure],
        },
    )

    with PacedSession(clock=clock) as session:
        outcomes = session.run(planned)

    assert [o.status for o in outcomes] == ["failed", "failed", "answered", "failed"]


def test_pace_until_is_that_time_of_the_local_day():
    local = timezone(timedelta(hours=1))
    deadline = pace_deadline("06:30", now=START, tz=local)
    assert deadline == datetime(2026, 11, 23, 5, 30, tzinfo=UTC)
    assert pace_deadline(None, now=START) is None
    with pytest.raises(ObserwatorValidationError) as exc:
        pace_deadline("6:30", now=START, tz=local)
    assert exc.value.details["option"] == "pace_until"
