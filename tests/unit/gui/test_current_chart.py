"""
The chart of „teraz” (O6): the stored hourly series joined with the live tail.

``api/station/{code}/subdaily`` serves the stored hours from ``from`` on and the hours
after the newest stored one that the provider gives now (`LiveTail`, here `FakeTail`
answering as hydro-back and ČHMÚ's ``now`` do), each labelled with its tier; a station
whose sources are ``private`` (P15, ADR-030 D5) is ``not_found`` before any request.
"""

from __future__ import annotations

import shutil
from datetime import UTC, date, datetime, timedelta

import pytest

from obserwator.attribution import attribution
from obserwator.exceptions import ObserwatorConnectionError
from obserwator.gui._live import TAIL_HOURS, LiveTail
from tests.unit.gui.conftest import HYDRO, HYDRO_CHMU, METEO
from tests.unit.gui.hourly import CHMU, IMGW, FakeTail, plant_hours

NOW = datetime(2026, 11, 23, 9, 37, tzinfo=UTC)
"""The tests' current time: the stored hours end at 23:00 UTC of the day before."""
YESTERDAY = date(2026, 11, 22)
FIRST = date(2026, 10, 20)
"""The first stored day: the months of October and November are stored."""
PUBLIC_IMGW = '[obserwator.capture]\n"pl.imgw.hydro_operational" = "public"\n'
PRIVATE_CHMU = '[obserwator.capture]\n"cz.chmu.hydro_current" = "private"\n'


def value(moment: datetime, variable: str) -> float | None:
    """The values of every source: H by the day and hour, Q, and T once a day at 06:00."""
    if variable == "H":
        return 100.0 + moment.day + moment.hour / 100
    if variable == "Q":
        return 1.5
    return 5.0 if moment.hour == 6 and moment.minute == 0 else None


def stored(higher: str):
    """The stored ``(value, tier)`` of an hour: ``higher`` in October, captured after it."""

    def pair(hour: datetime, variable: str):
        found = value(hour, variable)
        tier = higher if hour.month == 10 else "operational"
        return (found, tier) if found is not None else (None, None)

    return pair


@pytest.fixture(scope="module")
def chart_root(fixture_root, tmp_path_factory):
    """The fixture root with the hours of both stations from 20 October to yesterday."""
    root = tmp_path_factory.mktemp("chart") / "data"
    shutil.copytree(fixture_root, root)
    plant_hours(root, CHMU, HYDRO_CHMU, FIRST, YESTERDAY, stored("verified"))
    plant_hours(root, IMGW, HYDRO, FIRST, YESTERDAY, stored("telemetry"))
    return root


class Clock:
    """The tests' UTC time and monotonic seconds, moved by hand."""

    def __init__(self) -> None:
        self.now = NOW
        self.seconds = 1000.0

    def advance(self, minutes: float) -> None:
        self.now += timedelta(minutes=minutes)
        self.seconds += 60 * minutes


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def chart(make_client, chart_root, clock, tmp_path, monkeypatch):
    """``chart(toml="")``: a client on the chart root, its `FakeTail` and ``nogat.toml``."""

    def make(toml: str = "", failure: Exception | None = None):
        config = tmp_path / "nogat.toml"
        config.write_text(toml, encoding="utf-8")
        monkeypatch.setenv("NOGAT_CONFIG", str(config))
        fetch = FakeTail(lambda: clock.now, value, failure)
        tail = LiveTail(fetch, clock=lambda: clock.seconds, now=lambda: clock.now)
        return make_client(chart_root, tail=tail), fetch

    return make


def hours(first: datetime, last: datetime) -> list[str]:
    count = (last - first) // timedelta(hours=1) + 1
    return [
        (first + step * timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        for step in range(count)
    ]


def test_stored_hours_to_yesterday_join_todays_hours_of_the_live_tail(chart):
    client, fetch = chart()

    document = client.get(
        f"/api/station/{HYDRO_CHMU}/subdaily", params={"from": "2026-10-30"}
    ).json()

    stored, live = document["stored"], document["live"]
    end = datetime(2026, 11, 22, 23, tzinfo=UTC)
    assert stored["dates"] == hours(datetime(2026, 10, 30, tzinfo=UTC), end)
    assert stored["last"] == "2026-11-22T23:00:00Z"
    # Each stored hour labelled with its tier: the validated October, then captures
    assert stored["tiers"]["H"] == [
        [0, 47, "verified"],
        [48, len(stored["dates"]) - 1, "operational"],
    ]
    assert stored["values"]["H"][-1] == value(end, "H")
    # Today's full hours to the current one from the live tail, tier operational
    assert (live["dataset"], live["tier"]) == ("cz.chmu.hydro_current", "operational")
    today = datetime(2026, 11, 23, tzinfo=UTC)
    assert live["dates"] == hours(today, datetime(2026, 11, 23, 9, tzinfo=UTC))
    assert live["values"]["H"] == [
        value(moment, "H") for moment in map(datetime.fromisoformat, live["dates"])
    ]
    assert live["values"]["T"][6] == 5.0
    assert (live["fetched_at"], live["error"]) == ("2026-11-23T09:37:00Z", None)
    # One request, back to the newest stored hour: the hours since then and one
    assert fetch.asked == [("CHMU", HYDRO_CHMU, 11)]
    assert live["hours"] == 11
    assert document["attribution"] == list(attribution("chmu").attribution)
    assert client.get(f"/api/stations/{HYDRO_CHMU}").json()["subdaily"] is True


def test_a_second_opening_within_ten_minutes_asks_nothing(chart, clock):
    client, fetch = chart()
    path = f"/api/station/{HYDRO_CHMU}/subdaily"

    first = client.get(path, params={"from": "2026-11-20"}).json()
    clock.advance(9)
    again = client.get(path, params={"from": "2026-11-16"}).json()
    asked_once = list(fetch.asked)
    clock.advance(2)
    later = client.get(path, params={"from": "2026-11-20"}).json()

    assert asked_once == [("CHMU", HYDRO_CHMU, 11)]
    assert again["live"] == first["live"]
    assert len(fetch.asked) == 2
    assert later["live"]["fetched_at"] == "2026-11-23T09:48:00Z"


def test_a_private_source_is_not_served_and_asks_nothing(chart):
    client, fetch = chart()
    imgw = client.get(
        f"/api/station/{HYDRO}/subdaily", headers={"Accept-Language": "en"}
    )
    private, fetch_private = chart(PRIVATE_CHMU)
    chmu = private.get(f"/api/station/{HYDRO_CHMU}/subdaily")
    station = private.get(f"/api/stations/{HYDRO_CHMU}").json()

    for answer in (imgw, chmu):
        assert answer.status_code == 404, answer.text
        assert answer.json()["code"] == "not_found"
        assert answer.json()["details"]["reason"] == "private"
    assert client.get(f"/api/stations/{HYDRO}").json()["subdaily"] is False
    assert station["subdaily"] is False
    assert fetch.asked == fetch_private.asked == []


def test_a_public_imgw_station_has_the_lines_of_each_tier(chart):
    client, fetch = chart(PUBLIC_IMGW)

    document = client.get(f"/api/station/{HYDRO}/subdaily").json()

    tiers = {tier for runs in document["stored"]["tiers"].values() for *_, tier in runs}
    assert tiers == {"telemetry", "operational"}
    assert document["stored"]["dates"][0] == "2026-10-20T00:00:00Z"
    assert document["live"]["dataset"] == "pl.imgw.hydro_operational"
    # The full hours after the stored ones; the 10-minute points stay out
    assert document["live"]["dates"][-1] == "2026-11-23T09:00:00Z"
    lines = attribution("imgw", "imgw_hydro")
    assert document["attribution"] == list(lines.attribution)
    assert document["terms_notice"] == list(lines.terms_notice)
    assert fetch.asked == [("IMGW", HYDRO, 11)]


def test_from_reads_and_serves_only_the_range(chart):
    client, _ = chart()
    path = f"/api/station/{HYDRO_CHMU}/subdaily"

    november = client.get(path, params={"from": "2026-11-21"}).json()["stored"]
    every = client.get(path).json()["stored"]

    assert november["dates"][0] == "2026-11-21T00:00:00Z"
    assert len(november["dates"]) == 48
    assert [label.split("/")[0] for label in november["versions"]] == ["2026-11"]
    assert every["dates"][0] == "2026-10-20T00:00:00Z"
    assert [label.split("/")[0] for label in every["versions"]] == [
        "2026-10",
        "2026-11",
    ]


def test_a_failed_live_tail_serves_the_stored_hours_with_its_error(chart, clock):
    client, fetch = chart(failure=ObserwatorConnectionError("no answer"))

    document = client.get(f"/api/station/{HYDRO_CHMU}/subdaily").json()
    clock.advance(0.5)
    client.get(f"/api/station/{HYDRO_CHMU}/subdaily")

    assert document["stored"]["last"] == "2026-11-22T23:00:00Z"
    assert document["live"]["dates"] == []
    assert document["live"]["error"]
    assert len(fetch.asked) == 1  # a failure waits a minute before the next request


def test_only_a_hydrological_station_has_the_chart(chart):
    client, _ = chart()

    answer = client.get(f"/api/station/{METEO}/subdaily")

    assert answer.status_code == 404
    assert answer.json()["details"]["reason"] == "kind"
    assert client.get(f"/api/stations/{METEO}").json()["subdaily"] is False


def test_without_a_stored_hour_the_tail_asks_the_most_hours(
    make_client, read_only_root, clock, tmp_path, monkeypatch
):
    config = tmp_path / "nogat.toml"
    config.write_text("", encoding="utf-8")
    monkeypatch.setenv("NOGAT_CONFIG", str(config))
    fetch = FakeTail(lambda: clock.now, value)
    tail = LiveTail(fetch, clock=lambda: clock.seconds, now=lambda: clock.now)
    client = make_client(read_only_root, tail=tail)

    document = client.get(f"/api/station/{HYDRO_CHMU}/subdaily").json()

    assert document["stored"]["dates"] == []
    assert document["stored"]["last"] is None
    assert document["live"]["dates"][0] == "2026-11-23T00:00:00Z"
    assert fetch.asked == [("CHMU", HYDRO_CHMU, TAIL_HOURS)]
