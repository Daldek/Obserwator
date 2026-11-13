"""Live data through the server only (GUI plan D8): IMGW-PIB's snapshots and PMAXTP."""

from __future__ import annotations

import threading
import time
from types import SimpleNamespace

from obserwator.gui._live import (
    CURRENT_RETRY_S,
    CURRENT_TTL_S,
    PMAXTP_TTL_S,
    CurrentData,
    Pmaxtp,
    synop_indices,
    synop_record,
)
from obserwator.store.types import StationFeature


class Clock:
    """Monotonic time the test moves on."""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


class Source:
    """A source of current data that answers the records, or raises the error, it holds."""

    def __init__(self, records) -> None:
        self.records = records
        self.error: Exception | None = None
        self.calls = 0

    def __call__(self):
        self.calls += 1
        if self.error is not None:
            raise self.error
        return list(self.records)


def meteo(code: str, name: str) -> StationFeature:
    return StationFeature(code, (19.8, 50.1), {"kind": "meteo", "name": name})


def report(index: str, name: str) -> SimpleNamespace:
    return SimpleNamespace(
        station_code=index,
        model_dump=lambda mode: {"station_code": index, "station_name": name},
    )


def test_a_snapshot_is_asked_of_imgw_pib_at_most_once_in_ten_minutes(live):
    clock = Clock()
    source = Source(live.records["states"])
    current = CurrentData({"states": source}, clock=clock)

    first = current.get("states")
    clock.now += CURRENT_TTL_S - 1
    current.get("states")
    clock.now += 2
    refreshed = current.get("states")

    assert source.calls == 2
    assert first.items is not None
    assert first.items["149190310"]["water_state"] == "medium"
    assert refreshed.error is None


def test_a_failed_refresh_keeps_the_last_snapshot_and_waits_a_minute(live):
    clock = Clock()
    source = Source(live.records["states"])
    current = CurrentData({"states": source}, clock=clock)
    good = current.get("states")
    fetched_at, items = good.fetched_at, dict(good.items or {})

    source.error = live.outage
    clock.now += CURRENT_TTL_S
    failed = current.get("states")
    clock.now += CURRENT_RETRY_S - 1
    current.get("states")
    calls_while_waiting = source.calls
    source.error = None
    clock.now += 1
    recovered = current.get("states")

    assert failed.items == items
    assert failed.fetched_at == fetched_at
    assert failed.error is live.outage
    assert calls_while_waiting == 2
    assert source.calls == 3
    assert recovered.error is None


def test_a_source_that_never_answered_has_no_items_and_its_error(live):
    source = Source(live.records["hydro"])
    source.error = live.outage
    current = CurrentData({"hydro": source}, clock=Clock())

    snapshot = current.get("hydro")

    assert (snapshot.items, snapshot.fetched_at) == (None, None)
    assert snapshot.error is live.outage


def test_requests_at_the_same_time_ask_imgw_pib_once(live):
    release = threading.Event()
    source = Source(live.records["meteo"])

    def slow():
        release.wait(5)
        return source()

    current = CurrentData({"meteo": slow})
    found = []
    threads = [
        threading.Thread(target=lambda: found.append(current.get("meteo")))
        for _ in range(4)
    ]
    for thread in threads:
        thread.start()
    time.sleep(0.05)
    release.set()
    for thread in threads:
        thread.join(5)

    assert source.calls == 1
    assert len(found) == 4
    assert all(snapshot.items == found[0].items for snapshot in found)


def test_a_synoptic_report_is_paired_by_wmo_index_and_name():
    features = {
        "350190566": meteo("350190566", "KRAKÓW-BALICE"),
        "351190465": meteo("351190465", "ŁÓDŹ-LUBLINEK"),
        "352200375": meteo("352200375", "WARSZAWA-OKĘCIE"),
        "353200375": meteo("353200375", "WARSZAWA-BIELANY"),
        "350190599": StationFeature(
            "350190599", None, {"kind": "hydro", "name": "KRAKÓW"}
        ),
    }
    synop = SimpleNamespace(
        items={
            "12566": {"station_name": "Kraków-Balice"},
            "12465": {"station_name": "Kalisz"},
            "12375": {"station_name": "Warszawa"},
        }
    )

    indices = synop_indices(features)

    assert indices == {"350190566": "12566", "351190465": "12465"}
    assert synop_record("350190566", features["350190566"], indices, synop) == {
        "station_name": "Kraków-Balice"
    }
    assert synop_record("351190465", features["351190465"], indices, synop) is None
    assert synop_record("352200375", features["352200375"], indices, synop) is None


def test_a_letter_l_with_a_stroke_pairs_like_its_plain_letter():
    features = {"351190465": meteo("351190465", "ŁÓDŹ-LUBLINEK")}
    synop = SimpleNamespace(items={"12465": {"station_name": "Lodz-Lublinek"}})

    indices = synop_indices(features)

    assert synop_record("351190465", features["351190465"], indices, synop) == {
        "station_name": "Lodz-Lublinek"
    }


def test_pmaxtp_of_a_point_is_kept_a_day(live):
    clock = Clock()
    calls = []

    def fetch(latitude, longitude, *, method="POT"):
        calls.append((latitude, longitude, method))
        return live.fetch(latitude, longitude, method=method)

    pmaxtp = Pmaxtp(fetch, clock=clock)

    first = pmaxtp.get("POT", 52.23, 21.01)
    clock.now += PMAXTP_TTL_S - 1
    kept = pmaxtp.get("POT", 52.23, 21.01)
    clock.now += 2
    pmaxtp.get("POT", 52.23, 21.01)

    assert kept is first
    assert calls == [(52.23, 21.01, "POT")] * 2


def test_pmaxtp_tables_are_ordered_by_duration_and_probability():
    tables = {
        "5": {"50": 4.0, "10": 6.0, "1": 9.0, "0.1": 12.0},
        "1440": {"50": 40.0, "10": 60.0, "1": 90.0, "0.1": 120.0},
        "60": {"50": 14.0, "10": 16.0, "1": 19.0, "0.1": 22.0},
    }
    answer = SimpleNamespace(
        data=SimpleNamespace(
            model_dump=lambda mode: {"ks": tables, "sg": tables, "rb": tables}
        )
    )

    document = Pmaxtp(lambda latitude, longitude, *, method: answer).get(
        "AMP", 50.0, 20.0
    )

    assert document["durations"] == ["5", "60", "1440"]
    assert document["probabilities"] == ["0.1", "1", "10", "50"]
    assert document["method"] == "AMP"
    assert document["command"].startswith("obserwator pmaxtp fetch")
