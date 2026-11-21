"""The data root as the GUI reads it (GUI plan D7): current versions, asked again a minute later."""

from __future__ import annotations

import gc
import shutil
from datetime import date

import pytest

import obserwator
from obserwator.gui import _root
from obserwator.gui._root import RELOAD_AFTER_S, DataRoot, series_cells
from obserwator.store import (
    SeriesIndex,
    StationCoverage,
    StationSeriesIndex,
    read_series_index,
)
from obserwator.testing import build_fixture_store
from tests.contract.support import build_served_analyses
from tests.unit.gui.conftest import HYDRO, HYDRO_CHMI


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


def _reachable(root):
    """Every object reachable from ``root``, types, modules and functions aside."""
    seen, stack, found = set(), [root], []
    while stack:
        item = stack.pop()
        if id(item) in seen or isinstance(item, type) or callable(item):
            continue
        seen.add(id(item))
        found.append(item)
        stack.extend(gc.get_referents(item))
    return found


def test_the_snapshot_counts_the_ranges_without_a_value_and_keeps_no_index(
    fixture_root,
):
    snapshot = DataRoot(fixture_root).snapshot()
    series = snapshot.series["pl.imgw.hydro_daily"]
    index = read_series_index(series.version.path)

    (held,) = snapshot.datasets_of(HYDRO)
    gaps = {name: c.gaps for name, c in index.stations[HYDRO].variables.items()}
    assert {name: v["gaps"] for name, v in held["variables"].items()} == {
        name: len(found) for name, found in gaps.items()
    }
    assert held["variables"]["H"]["gaps"] == 2
    # A full root's index lists millions of such ranges (230 MB in memory): the
    # snapshot keeps their number, no range, no date and nothing of the index.
    kept = _reachable(snapshot.series)
    assert not [
        item
        for item in kept
        if isinstance(item, (date, SeriesIndex, StationSeriesIndex, StationCoverage))
    ]


def test_series_documents_in_memory_hold_at_most_the_cells_allowed(
    fixture_root, monkeypatch
):
    sizes = DataRoot(fixture_root)
    chmi, _ = sizes.series_document("cz.chmi.hydro_daily", HYDRO_CHMI)
    imgw, _ = sizes.series_document("pl.imgw.hydro_daily", HYDRO)
    reads = []

    def read(*args, **kwargs):
        reads.append(kwargs["station"])
        return obserwator.read_series(*args, **kwargs)

    monkeypatch.setattr(_root, "read_series", read)
    # Room for either document, not for both: the older goes when the newer comes.
    allowed = series_cells(chmi) + series_cells(imgw) - 1
    monkeypatch.setattr(_root, "SERIES_CELLS", allowed)
    data = DataRoot(fixture_root)

    data.series_document("cz.chmi.hydro_daily", HYDRO_CHMI)
    data.series_document("pl.imgw.hydro_daily", HYDRO)
    data.series_document("pl.imgw.hydro_daily", HYDRO)
    again, _ = data.series_document("cz.chmi.hydro_daily", HYDRO_CHMI)

    assert reads == [HYDRO_CHMI, HYDRO, HYDRO_CHMI]
    assert again == chmi


def test_a_series_document_larger_than_the_cells_allowed_stays_until_the_next(
    fixture_root, monkeypatch
):
    reads = []

    def read(*args, **kwargs):
        reads.append(kwargs["station"])
        return obserwator.read_series(*args, **kwargs)

    monkeypatch.setattr(_root, "read_series", read)
    monkeypatch.setattr(_root, "SERIES_CELLS", 1)
    data = DataRoot(fixture_root)

    first, _ = data.series_document("cz.chmi.hydro_daily", HYDRO_CHMI)
    again, _ = data.series_document("cz.chmi.hydro_daily", HYDRO_CHMI)
    data.series_document("pl.imgw.hydro_daily", HYDRO)
    data.series_document("cz.chmi.hydro_daily", HYDRO_CHMI)

    assert again == first
    assert reads == [HYDRO_CHMI, HYDRO, HYDRO_CHMI]
