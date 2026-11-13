"""The data root as the GUI reads it (GUI plan D7): current versions, asked again a minute later."""

from __future__ import annotations

import shutil

import pytest

import obserwator
from obserwator.gui import _root
from obserwator.gui._root import RELOAD_AFTER_S, DataRoot
from obserwator.testing import build_fixture_store
from tests.contract.support import build_served_analyses
from tests.unit.gui.conftest import HYDRO_CHMI


class Clock:
    """Monotonic time the test moves on."""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock() -> Clock:
    return Clock()


def test_a_new_version_shows_a_minute_later_without_a_restart(
    imgw_root, fixture_root, tmp_path, clock
):
    root = tmp_path / "root"
    shutil.copytree(imgw_root, root)
    data = DataRoot(root, clock=clock)
    before = data.snapshot()

    shutil.rmtree(root)
    shutil.copytree(fixture_root, root)
    clock.now += RELOAD_AFTER_S - 1
    within = data.snapshot()
    clock.now += 2
    after = data.snapshot()

    assert set(before.catalogs) == {"IMGW-PIB"}
    assert within is before
    assert set(after.catalogs) == {"IMGW-PIB", "CHMI"}
    assert HYDRO_CHMI in after.features
    assert after.layer["count"] == 13
    assert after.layer_etag != before.layer_etag
    document, _ = data.series_document("cz.chmi.hydro_daily", HYDRO_CHMI)
    assert document["dates"][0] == "2023-01-01"


def test_new_stored_analyses_show_a_minute_later_and_keep_the_station_layer(
    fixture_root, tmp_path, clock
):
    root = tmp_path / "root"
    shutil.copytree(fixture_root, root)
    data = DataRoot(root, clock=clock)
    before = data.snapshot()

    build_served_analyses(root)
    clock.now += RELOAD_AFTER_S - 1
    within = data.snapshot()
    clock.now += 2
    after = data.snapshot()

    stored = obserwator.read_analysis(
        root=root, station=HYDRO_CHMI, analysis="characteristic.Q"
    )
    (version,) = (root / "analyses" / "versions" / "cz.chmi").iterdir()
    assert before.analyses == {}
    assert within is before
    assert set(after.analyses) == {"IMGW-PIB", "CHMI"}
    assert after.analyses["CHMI"].label == version.name
    assert after.analyses["CHMI"].hydrolog == stored.hydrolog["version"]
    # The catalogs and series are unchanged: so is the station layer's ETag
    assert after.layer_etag == before.layer_etag


def test_unchanged_versions_keep_the_snapshot_already_read(fixture_root, clock):
    data = DataRoot(fixture_root, clock=clock)
    first = data.snapshot()

    clock.now += 10 * RELOAD_AFTER_S

    assert data.snapshot() is first


def test_a_root_that_cannot_be_read_is_an_error_until_it_can(
    fixture_root, tmp_path, clock
):
    root = tmp_path / "root"
    data = DataRoot(root, clock=clock)
    missing = data.snapshot()

    shutil.copytree(fixture_root, root)
    clock.now += RELOAD_AFTER_S
    found = data.snapshot()

    assert missing.error is not None
    assert missing.error.code == "store_unavailable"
    assert missing.features == {}
    assert found.error is None
    assert len(found.features) == 13


def test_a_series_version_of_an_unknown_schema_is_an_error(tmp_path):
    root = tmp_path / "data"
    build_fixture_store(tmp_path / "raw", data_root=root, variant="unknown_schema")

    snapshot = DataRoot(root).snapshot()

    assert snapshot.error is not None
    assert snapshot.series == {}


def test_the_stations_file_is_exported_once_per_versions(
    fixture_root, clock, monkeypatch
):
    calls = []

    def export(*args, **kwargs):
        calls.append(kwargs)
        return obserwator.export_stations(*args, **kwargs)

    monkeypatch.setattr(_root, "export_stations", export)
    data = DataRoot(fixture_root, clock=clock)

    first = data.stations_file("csv", "CHMI", "hydro")
    again = data.stations_file("csv", "CHMI", "hydro")
    other = data.stations_file("geojson", None, None)

    assert again == first
    assert (
        first
        == "".join(
            obserwator.export_stations(
                fixture_root, provider="CHMI", kind="hydro", format="csv"
            )
        ).encode()
    )
    assert other.startswith(b"{")
    assert [(call["format"], call["provider"], call["kind"]) for call in calls] == [
        ("csv", "CHMI", "hydro"),
        ("geojson", None, None),
    ]
