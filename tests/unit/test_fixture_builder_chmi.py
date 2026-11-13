"""build_fixture_store(variant="complete_pl_cz"): the IMGW-PIB fixture plus ČHMÚ.

Spec 2026-10-18 §13.3: ČHMÚ archives in versions (first, ``relabeled``,
corrected), a slot with the observation of scenario (8) in the raw root, the
series of both ČHMÚ datasets and the ČHMÚ catalog in the data root (ADR-017),
built offline from ``chmi_builder_recordings.json``. Synthetic files,
fictional station codes.
"""

import hashlib
import json
import socket
from collections import Counter
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

import pytest

from obserwator.store import (
    catalog,
    check_series,
    current_version,
    iter_store,
    read_catalog,
    series,
    writer,
)
from obserwator.testing import build_fixture_store, fixture_files

DAILY = "archives/versions/hydrology/historical/data/daily"
HYDRO, METEO = "cz.chmi.hydro_daily", "cz.chmi.meteo_daily"
RESERIALIZED = "variants/H_0-203-1-900001_DQ_2023_reserialized.json"


def refuse(*args, **kwargs):
    raise AssertionError("połączenie sieciowe w teście offline")


@pytest.fixture(scope="module")
def roots(tmp_path_factory):
    base = tmp_path_factory.mktemp("pl_cz")
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(socket.socket, "connect", refuse)
        patch.setattr(socket, "create_connection", refuse)
        return build_fixture_store(
            base / "store", data_root=base / "data", variant="complete_pl_cz"
        )


@pytest.fixture(scope="module")
def store(roots):
    """The raw root: archives and observations."""
    return roots.raw.root


@pytest.fixture(scope="module")
def data(roots):
    """The data root: series and catalogs."""
    return roots.data.root


def sidecars(root, slot, name):
    return {
        directory.name: json.loads(
            (directory / f"{name}.meta.json").read_text(encoding="utf-8")
        )
        for directory in sorted((root / slot).iterdir())
        if directory.name != "observations"
    }


def tree(roots):
    """Files of both fixture roots, by kind of root and relative path."""
    return {
        f"{kind}/{path.relative_to(root).as_posix()}": hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
        for kind, root in (("raw", roots.raw.root), ("data", roots.data.root))
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_chmi_archives_keep_the_versions_of_each_scenario(store):
    republished = sidecars(
        store, f"{DAILY}/H_0-203-1-900002_DQ_2004", "H_0-203-1-900002_DQ_2004.json"
    )
    first, relabeled = republished.values()
    assert first["sha256"] == relabeled["sha256"]
    assert [meta["extra"]["version"]["label"] for meta in republished.values()] == [
        "2025-07-01",
        "2026-02-06",
    ]
    corrected = sidecars(
        store, f"{DAILY}/H_0-203-1-900001_DQ_2024", "H_0-203-1-900001_DQ_2024.json"
    )
    old, new = corrected.values()
    assert old["content_sha256"] != new["content_sha256"]
    assert new["extra"]["http"]["etag"] == '"6a0eea27-554e"'
    assert {meta["content_form"] for meta in (*republished.values(), old, new)} == {
        "chmi-json/1"
    }
    (rain,) = sidecars(
        store,
        "archives/versions/meteorology/climate/historical_csv/data/daily/precipitation/"
        "dly-0-203-0-90000000002-SRA",
        "dly-0-203-0-90000000002-SRA.csv",
    ).values()
    assert "content_sha256" not in rain and rain["provider"] == "CHMI"


def test_reserialized_file_is_one_observation_beside_its_only_version(store):
    slot = f"{DAILY}/H_0-203-1-900001_DQ_2023"
    ((version, meta),) = sidecars(store, slot, "H_0-203-1-900001_DQ_2023.json").items()
    (observation,) = (store / slot / "observations").iterdir()
    seen = json.loads(observation.read_text(encoding="utf-8"))
    reserialized = fixture_files().joinpath(*RESERIALIZED.split("/")).read_bytes()

    assert seen["same_content_as"] == version
    assert seen["sha256"] == hashlib.sha256(reserialized).hexdigest() != meta["sha256"]
    assert (seen["content_sha256"], seen["content_form"]) == (
        meta["content_sha256"],
        meta["content_form"],
    )
    assert seen["last_modified"] == "Mon, 19 Oct 2026 03:12:44 GMT"
    entry = current_version(
        store, slot=f"archive:{HYDRO}:H_0-203-1-900001_DQ_2023.json"
    )
    assert entry is not None and entry.version is not None
    assert entry.version.parent.name == version


def test_chmi_series_and_catalog_are_current_and_the_scan_is_clean(store, data):
    assert check_series(data, raw_root=store, dataset=HYDRO).series_state == {
        "chmi_hydro_daily": "current"
    }
    assert check_series(data, raw_root=store, dataset=METEO).series_state == {
        "chmi_meteo_daily": "current"
    }
    hydro_series = sidecars(data, "series/versions/chmi_hydro_daily", "series.json")
    assert len(hydro_series) == 2  # before and after the correction of 900001 2024
    current = max(hydro_series.values(), key=lambda meta: meta["downloaded_at"])
    inputs = {source["name"]: source for source in current["extra"]["source_files"]}
    corrected = inputs["H_0-203-1-900001_DQ_2024.json"]["file"]
    assert corrected.split("/")[-2].startswith("2026-05-21_")
    assert (store / corrected).is_file()  # source files name the raw root
    assert all("content_sha256" in source for source in inputs.values())

    stations = {
        feature.station_code for feature in read_catalog(root=data, provider="CHMI")
    }
    assert {"0-203-1-900001", "0-203-1-900002", "0-203-0-90001"} <= stations
    assert {feature.provider for feature in read_catalog(root=data)} == {
        "IMGW-PIB",
        "CHMI",
    }
    entries = [*iter_store(store), *iter_store(data)]
    assert [entry.problem for entry in entries if entry.kind == "problem"] == []
    assert Counter(
        (entry.kind, entry.provider) for entry in entries if entry.provider == "CHMI"
    ) == {
        # 12 measurement files, 2 station lists, 3 station metadata (``now``).
        ("archive", "CHMI"): 17,
        ("observation", "CHMI"): 1,
        ("series", "CHMI"): 3,
        ("catalog", "CHMI"): 1,
    }


def test_imgw_part_equals_the_complete_fixture_and_builds_are_identical(
    tmp_path, monkeypatch
):
    class Frozen(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 10, 20, 9, 0, tzinfo=UTC).astimezone(tz)

    for module in (writer, series, catalog):
        monkeypatch.setattr(module, "datetime", Frozen)
    complete = tree(
        build_fixture_store(tmp_path / "complete", data_root=tmp_path / "complete-data")
    )
    first = tree(
        build_fixture_store(
            tmp_path / "a", data_root=tmp_path / "a-data", variant="complete_pl_cz"
        )
    )
    second = tree(
        build_fixture_store(
            tmp_path / "b", data_root=tmp_path / "b-data", variant="complete_pl_cz"
        )
    )

    assert first == second
    assert {name: first[name] for name in complete} == complete
    chmi = (
        "raw/archives/versions/hydrology/",
        "raw/archives/versions/meteorology/",
        "data/series/versions/chmi_",
        "data/stations/versions/chmi_stations/",
    )
    assert all(name.startswith(chmi) for name in set(first) - set(complete))


def test_builder_recordings_follow_the_nginx_signals_of_the_source():
    """ETag = "<hex mtime>-<hex size>" of Last-Modified and Content-Length (§13.1)."""
    document = json.loads(
        fixture_files().joinpath("chmi_builder_recordings.json").read_text("utf-8")
    )
    signals = [
        entry for entry in document["interactions"] if "ETag" in entry["headers"]
    ]
    assert signals
    for entry in signals:
        headers = entry["headers"]
        moment = int(parsedate_to_datetime(headers["Last-Modified"]).timestamp())
        size = int(headers["Content-Length"])
        assert headers["ETag"] == f'"{moment:x}-{size:x}"', entry["case"]
        if entry["method"] == "GET":
            relative = entry.get("variant") or f"archives/{entry['archive']}"
            assert len(fixture_files().joinpath(*relative.split("/")).read_bytes()) == (
                size
            ), entry["case"]
