"""The days of ``store check|sync`` of the captures (O3).

``--start``/``--end`` (UTC dates, AGI-3.4) choose the closed spool days a sync seals and
a check plans, and with ``--pace-until`` the days the harvest asks for: by default the
last closed UTC day, at most 40 days back (ADR-030 D9 and its errata of 2026-11-23).

Every test has its own spool (``OBSERWATOR_STATE_DIR``), ``nogat.toml`` and a
fake clock (`obserwator.fetch._clock`, `obserwator.captures._now`) that moves only when a
run waits, so no test sleeps. hydro-back is a fake source that answers any
``hoursInterval`` at the clock's time with the grid of its recorded answers (the full
hours of the interval and the 10-minute points of the last two hours), each value a
function of the station, the series and the hour.
"""

import json
from datetime import UTC, date, datetime, time, timedelta
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
import respx
from typer.testing import CliRunner

from obserwator import captures, fetch
from obserwator.captures import HARVEST_DAYS, spool_files, write_spool
from obserwator.cli.main import app
from obserwator.commands import run_command
from obserwator.error_report import error_hint
from obserwator.exceptions import (
    ObserwatorValidationError,
)
from obserwator.providers.base import Answer
from obserwator.store import check_store, init_store, sync_store
from obserwator.store.captures import decode
from tests.unit.test_paced import FakeClock

OPERATIONAL = "pl.imgw.hydro_operational"
HYDRO = "pl.imgw.hydro_current"
HYDRO_URL = "https://danepubliczne.imgw.pl/api/data/hydro"
SERIES_URL = "https://hydro-back.imgw.pl/station/hydro/"
SERIES = ("status/data", "discharge", "water-temperature")
STATIONS = ("151160060", "150160180")
TODAY = date(2026, 11, 23)
LAST = TODAY - timedelta(days=1)
FIRST = LAST - timedelta(days=HARVEST_DAYS - 1)
NIGHT = time(1, 30)
"""02:30 local in winter: when the night's timer starts (ADR-030 D9)."""
PASSED = "00:00"
"""A ``pace_until`` always passed (the start of the local day): the 5 s spacing."""
RUNNER = CliRunner(env={"TERM": "dumb", "COLUMNS": "80"})


def at(day, moment=NIGHT):
    return datetime.combine(day, moment, UTC)


def days(first, last):
    return [first + timedelta(days=step) for step in range((last - first).days + 1)]


def value(code, series, moment):
    """The fake source's value of a station's series at a time."""
    hour = int(moment.timestamp()) // 3600
    return round(int(code) % 97 + SERIES.index(series) * 100 + (hour % 50) / 4, 2)


def series_answer(code, series, hours, now):
    """hydro-back's answer at ``now``: full hours of ``hours`` back, 10-min tail of 2 h."""
    since = now - timedelta(hours=hours)
    moment = since.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    points = []
    while moment <= now:
        points.append(moment)
        moment += timedelta(hours=1)
    tail = (now - timedelta(hours=2)).replace(second=0, microsecond=0)
    moment = tail + timedelta(minutes=10 - tail.minute % 10)
    while moment <= now:
        if moment.minute:
            points.append(moment)
        moment += timedelta(minutes=10)
    return {
        "operational": [
            {"date": f"{point:%Y-%m-%dT%H:%M:%SZ}", "value": value(code, series, point)}
            for point in sorted(points)
        ]
    }


def stored_hours(root, first, last):
    """``{(station, series, hour): value}`` of the full hours ``first`` to ``last``."""
    found = {}
    directory = root / "archives" / "versions" / "station" / "hydro"
    for path in sorted(directory.glob("*/*/*.jsonl.gz")):
        for answer in decode(path.read_bytes()):
            address = urlsplit(answer.address)
            series = address.path.removeprefix("/station/hydro/")
            (code,) = parse_qs(address.query)["id"]
            for point in json.loads(answer.content)["operational"]:
                moment = datetime.fromisoformat(point["date"])
                if moment.minute == 0 and first <= moment.date() <= last:
                    key = (code, series, moment)
                    assert found.setdefault(key, point["value"]) == point["value"]
    return found


def spool_answer(day, body=b"[1]"):
    """An answer of ``api/data/hydro`` spooled on ``day``."""
    return write_spool(Answer(HYDRO_URL, at(day, time(10, 15)), 200, body, HYDRO))


def spooled_days(key=HYDRO):
    return [
        day for day in days(FIRST - timedelta(days=5), TODAY) if spool_files(key, day)
    ]


def tree(root):
    return sorted(path.relative_to(root).as_posix() for path in root.rglob("*"))


class Clock(FakeClock):
    """The fake clock of the paced runs, noting each wait."""

    def __init__(self, moment):
        super().__init__(moment)
        self.sleeps = []

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        super().sleep(seconds)


@pytest.fixture(autouse=True)
def clock(tmp_path, monkeypatch):
    """The test's spool, lock and ``nogat.toml``; the clocks at the night of TODAY."""
    monkeypatch.setenv("OBSERWATOR_STATE_DIR", str(tmp_path / "state"))
    config = tmp_path / "nogat.toml"
    config.write_text("", encoding="utf-8")
    monkeypatch.setenv("NOGAT_CONFIG", str(config))
    fake = Clock(at(TODAY))
    monkeypatch.setattr(fetch, "_clock", lambda: fake)
    monkeypatch.setattr(captures, "_now", fake.now)
    return fake


@pytest.fixture
def raw(tmp_path):
    return init_store(tmp_path / "raw").root


@pytest.fixture
def hydro_back(clock):
    """hydro-back's series of any station and ``hoursInterval`` at the clock's time."""
    asked = []
    with respx.mock(assert_all_called=False) as router:

        def answer(request):
            url = urlsplit(str(request.url))
            query = parse_qs(url.query)
            hours = int(query["hoursInterval"][0])
            asked.append((clock.now(), str(request.url)))
            body = series_answer(
                query["id"][0],
                url.path.removeprefix("/station/hydro/"),
                hours,
                clock.now(),
            )
            return httpx.Response(200, json=body)

        router.series = router.route(url__startswith=SERIES_URL).mock(
            side_effect=answer
        )
        router.asked = asked
        yield router


# --------------------------------------------------------------------------
# A backfill against the nights
# --------------------------------------------------------------------------


def test_a_backfill_of_40_days_gives_the_hours_of_the_nights_of_the_same_days(
    tmp_path, monkeypatch, clock, hydro_back
):
    nights = init_store(tmp_path / "nights").root
    for day in days(FIRST, LAST):
        clock.moment = at(day + timedelta(days=1))
        night = sync_store(
            nights, datasets=[OPERATIONAL], stations=list(STATIONS), pace_until=PASSED
        )
        assert (night.harvest.start, night.harvest.end) == (day, day)
        assert [item.status for item in night.items] == ["new"]
    assert len(hydro_back.asked) == HARVEST_DAYS * len(STATIONS) * len(SERIES)

    # The backfill: another raw root and spool, on the night after LAST.
    monkeypatch.setenv("OBSERWATOR_STATE_DIR", str(tmp_path / "backfill-state"))
    backfill = init_store(tmp_path / "backfill").root
    hydro_back.asked.clear()
    clock.moment = at(TODAY)
    report = sync_store(
        backfill,
        datasets=[OPERATIONAL],
        stations=list(STATIONS),
        start=FIRST,
        end=LAST,
        pace_until=PASSED,
    )

    assert (report.harvest.start, report.harvest.end) == (FIRST, LAST)
    assert (report.harvest.planned, report.harvest.answers) == (6, 6)
    # One request per station and series, its hours reaching 00:00 UTC of FIRST.
    asked = {
        parse_qs(urlsplit(url).query)["hoursInterval"][0] for _, url in hydro_back.asked
    }
    assert asked == {str(HARVEST_DAYS * 24 + 3)}
    (sealed,) = report.items
    assert (sealed.slot, sealed.status) == (
        f"archive:{OPERATIONAL}:{TODAY}.jsonl.gz",
        "new",
    )
    by_nights = stored_hours(nights, FIRST, LAST)
    by_backfill = stored_hours(backfill, FIRST, LAST)
    assert len(by_nights) == len(STATIONS) * len(SERIES) * HARVEST_DAYS * 24
    assert by_backfill == by_nights


def test_a_harvest_reaching_more_than_40_days_back_is_refused_before_any_request(
    raw, hydro_back
):
    earliest = TODAY - timedelta(days=HARVEST_DAYS)
    before = tree(raw)

    for call in (check_store, sync_store):
        with pytest.raises(ObserwatorValidationError) as refused:
            call(
                raw,
                datasets=[OPERATIONAL],
                stations=[STATIONS[0]],
                start=earliest - timedelta(days=1),
                pace_until="06:30",
            )
        assert refused.value.details == {
            "option": "start",
            "value": str(earliest - timedelta(days=1)),
            "reason": "harvest_reach",
            "earliest": str(earliest),
        }
    result = RUNNER.invoke(
        app,
        [
            "store",
            "sync",
            "--root",
            str(raw),
            "--datasets",
            OPERATIONAL,
            "--start",
            str(earliest - timedelta(days=1)),
            "--pace-until",
            "06:30",
            "--json",
        ],
    )
    document = json.loads(result.stderr.splitlines()[-1])
    assert (result.exit_code, document["code"]) == (2, "validation_error")
    assert document["hint"] == error_hint("validation_error", document["details"])
    assert "40" in document["hint"]
    assert not hydro_back.calls
    assert tree(raw) == before
    assert spooled_days(OPERATIONAL) == []

    # The 40th day back is the first one a harvest reaches.
    reached = sync_store(
        raw,
        datasets=[OPERATIONAL],
        stations=[STATIONS[0]],
        start=earliest,
        pace_until=PASSED,
    )
    assert (reached.harvest.start, reached.harvest.end) == (earliest, LAST)
    assert len(hydro_back.calls) == len(SERIES)


def test_a_harvest_asks_its_days_and_seals_only_the_spool_days_between_them(
    raw, hydro_back
):
    old = LAST - timedelta(days=5)
    for day in (old, LAST - timedelta(days=2)):
        write_spool(
            Answer(
                f"{SERIES_URL}status/data?id={STATIONS[0]}&hoursInterval=30",
                at(day, time(12)),
                200,
                b"{}",
                OPERATIONAL,
            )
        )

    plan = check_store(
        raw,
        datasets=[OPERATIONAL],
        stations=[STATIONS[0]],
        start=LAST - timedelta(days=3),
        end=LAST - timedelta(days=1),
        pace_until="06:30",
    )
    report = sync_store(
        raw,
        datasets=[OPERATIONAL],
        stations=[STATIONS[0]],
        start=LAST - timedelta(days=3),
        end=LAST - timedelta(days=1),
        pace_until=PASSED,
    )

    assert [item.archive.period_start for item in plan.items] == [
        LAST - timedelta(days=2)
    ]
    (action,) = plan.actions
    assert f"{LAST - timedelta(days=3)} to {LAST - timedelta(days=1)}" in action.detail
    assert (report.harvest.start, report.harvest.end) == (
        LAST - timedelta(days=3),
        LAST - timedelta(days=1),
    )
    # The closed day inside the range and today's, which holds the run's answers.
    assert [(item.slot, item.status) for item in report.items] == [
        (f"archive:{OPERATIONAL}:{LAST - timedelta(days=2)}.jsonl.gz", "new"),
        (f"archive:{OPERATIONAL}:{TODAY}.jsonl.gz", "new"),
    ]
    assert spooled_days(OPERATIONAL) == [old]


# --------------------------------------------------------------------------
# The days of the sealing
# --------------------------------------------------------------------------


def test_start_and_end_choose_the_closed_spool_days_a_check_plans_and_a_sync_seals(
    raw,
):
    spooled = [LAST - timedelta(days=3), LAST - timedelta(days=2), LAST, TODAY]
    for day in spooled:
        spool_answer(day)

    every = check_store(raw, datasets=[HYDRO])
    one = check_store(raw, datasets=[HYDRO], start=spooled[1], end=spooled[1])
    report = sync_store(raw, datasets=[HYDRO], start=spooled[1])
    checked = run_command(
        "store check",
        options={"root": str(raw), "datasets": [HYDRO], "end": str(spooled[0])},
    )

    assert [item.archive.period_start for item in every.items] == spooled[:3]
    assert [item.archive.period_start for item in one.items] == [spooled[1]]
    assert [(item.slot, item.status) for item in report.items] == [
        (f"archive:{HYDRO}:{spooled[1]}.jsonl.gz", "new"),
        (f"archive:{HYDRO}:{LAST}.jsonl.gz", "new"),
    ]
    assert [item.archive.period_start for item in checked.result.items] == [spooled[0]]
    assert spooled_days() == [spooled[0], TODAY]


@pytest.mark.parametrize(
    ("options", "option", "reason"),
    [
        ({"datasets": [HYDRO], "end": TODAY}, "end", "day_not_closed"),
        ({"datasets": [HYDRO], "start": TODAY}, "start", "day_not_closed"),
        ({"datasets": [HYDRO], "start": LAST, "end": FIRST}, "end", None),
        ({"datasets": [HYDRO], "start": "2026-11-20"}, "start", None),
        (
            {"datasets": ["pl.imgw.hydro_daily"], "years": [2024], "start": LAST},
            "start",
            "not_capture",
        ),
        ({"datasets": ["pl.imgw.hydro_now"], "end": LAST}, "end", "not_capture"),
    ],
    ids=["end today", "start today", "end before start", "text", "archives", "source"],
)
def test_invalid_days_are_refused_before_anything_is_read(raw, options, option, reason):
    spool_answer(FIRST)
    before = tree(raw)

    for call in (check_store, sync_store):
        with pytest.raises(ObserwatorValidationError) as refused:
            call(raw, **options)
        assert refused.value.details["option"] == option
        assert refused.value.details.get("reason") == reason

    assert tree(raw) == before
    assert spooled_days() == [FIRST]


def test_start_and_end_are_selectors_of_a_store_only(raw, tmp_path):
    plan = check_store(raw, datasets=[HYDRO])

    with pytest.raises(ObserwatorValidationError):
        sync_store(raw, plan=plan, start=LAST)
    with pytest.raises(ObserwatorValidationError) as plain:
        sync_store(output_dir=tmp_path / "out", datasets=[HYDRO], end=LAST)

    assert plain.value.details == {
        "option": "end",
        "value": str(LAST),
        "reason": "store_only_option",
    }
    assert not (tmp_path / "out").exists()
