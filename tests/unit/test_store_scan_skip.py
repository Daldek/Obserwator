"""Incremental scan of the store: ``iter_store(skip_versions=...)``, the versions a consumer knows."""

import shutil
from dataclasses import replace
from pathlib import Path

import pytest
import respx

from obserwator.exceptions import ObserwatorValidationError
from obserwator.store import init_store, iter_store, sync_pmaxtp
from obserwator.store import reader as reader_module
from obserwator.testing import build_fixture_store
from tests.unit.test_store_reader import (
    DAILY,
    DAILY_2024,
    observe,
    record_catalog_sources,
    store_archives,
    with_content,
)


def known_versions(root, entries):
    """What a consumer keeps of a scan: the directory of each version and its file names."""
    return {
        entry.version.parent.relative_to(root).as_posix(): (entry.version.name,)
        for entry in entries
        if entry.meta is not None
    }


def skipped(entry):
    """The entry as a scan that knows its version gives it."""
    return replace(entry, meta=None, skipped=True) if entry.meta else entry


@pytest.fixture(scope="module")
def roots(tmp_path_factory):
    """
    Versions of every kind of both providers, an observation register and a PMAXTP
    cell: the raw root and the data root, in that order.
    """
    base = tmp_path_factory.mktemp("skip")
    fixture = build_fixture_store(
        base / "raw", data_root=base / "data", variant="complete_pl_cz"
    )
    with respx.mock(assert_all_called=False) as router:
        record_catalog_sources(router)
        sync_pmaxtp(fixture.raw, method="POT", latitude=52.23, longitude=21.01)
    return fixture.raw.root, fixture.data.root


class Seen:
    """The directories listed and the sidecars read during a scan."""

    def __init__(self):
        self.listed: set[Path] = set()
        self.read: set[Path] = set()

    def clear(self):
        self.listed.clear()
        self.read.clear()


@pytest.fixture
def spy(monkeypatch):
    seen = Seen()
    iterdir, load_meta = Path.iterdir, reader_module._load_meta

    def listing(self):
        seen.listed.add(self)
        return iterdir(self)

    def reading(sidecar):
        seen.read.add(sidecar)
        return load_meta(sidecar)

    monkeypatch.setattr(Path, "iterdir", listing)
    monkeypatch.setattr(reader_module, "_load_meta", reading)
    return seen


def test_a_scan_gives_the_known_versions_back_without_listing_or_reading_them(
    roots, spy
):
    scans = {root: list(iter_store(root)) for root in roots}
    versions = [entry for full in scans.values() for entry in full if entry.meta]
    assert {entry.kind for entry in versions} == {
        "archive",
        "series",
        "catalog",
        "pmaxtp",
    }
    assert {entry.provider for entry in versions} == {"IMGW-PIB", "CHMI"}
    for root, full in scans.items():
        known = known_versions(root, full)
        directories = {root / directory for directory in known}
        spy.clear()
        list(iter_store(root))
        # A scan reads each version: its directory is listed and its sidecar loaded.
        assert directories <= spy.listed and spy.read
        spy.clear()

        incremental = list(iter_store(root, skip_versions=known))

        assert incremental == [skipped(entry) for entry in full]
        assert not directories & spy.listed
        # Only an observation reads the sidecar of the version it names (the content
        # fields); observations are in the raw root.
        observations = [entry for entry in full if entry.kind == "observation"]
        assert bool(observations) is (root == roots[0])
        assert {sidecar.parent for sidecar in spy.read} == {
            entry.version.parent.parent / entry.observation.same_content_as
            for entry in observations
        }


def test_a_known_version_that_broke_since_is_not_seen_but_the_rest_is(tmp_path, roots):
    raw, data = tmp_path / "raw", tmp_path / "data"
    shutil.copytree(roots[0], raw)
    shutil.copytree(roots[1], data)
    known = {root: known_versions(root, iter_store(root)) for root in (raw, data)}
    broken = next(e for e in iter_store(raw, kind="archive") if e.slot == DAILY_2024)
    gone = next(iter_store(data, kind="series", provider="CHMI"))
    Path(f"{broken.version}.meta.json").write_text("{broken", encoding="utf-8")
    shutil.rmtree(gone.version.parent)
    unfinished = data / "stations" / "versions" / "2026-01-01_deadbeef"
    unfinished.mkdir()
    (new,) = store_archives(raw, DAILY, [2023])

    full = [entry for root in (raw, data) for entry in iter_store(root)]
    incremental = [
        entry
        for root in (raw, data)
        for entry in iter_store(root, skip_versions=known[root])
    ]

    by_path = {entry.version: entry for entry in incremental}
    # The scan that knows a version does not look at it; a full scan reports it.
    assert (by_path[broken.version].skipped, by_path[broken.version].problem_code) == (
        True,
        None,
    )
    assert {
        (entry.slot, entry.problem_code)
        for entry in full
        if entry.version == broken.version.parent
    } == {(DAILY_2024, "invalid_json")}
    # What it does not know is read as always: a new version and an unfinished one;
    # a known version that is gone is not reported.
    assert by_path[new.path].meta is not None and not by_path[new.path].skipped
    assert by_path[unfinished].problem_code == "missing_sidecar"
    assert gone.version not in by_path
    assert [entry for entry in incremental if entry.kind == "problem"] == [
        entry
        for entry in full
        if entry.kind == "problem" and entry.version != broken.version.parent
    ]


def test_an_observation_is_checked_against_the_version_it_names_though_it_is_skipped(
    tmp_path,
):
    root = init_store(tmp_path / "store").root
    (written,) = store_archives(root, DAILY, [2024])
    with_content(written.path)
    observe(written.path)
    full = list(iter_store(root))
    known = known_versions(root, full)

    assert [entry.kind for entry in full] == ["archive", "observation"]
    assert list(iter_store(root, skip_versions=known)) == [skipped(e) for e in full]

    # Observed content that differs from that of the version is a problem, as in a full scan.
    other = observe(written.path, etag='"v3"', content_sha256="3" * 64)
    incremental = list(iter_store(root, skip_versions=known))
    assert incremental == [skipped(entry) for entry in iter_store(root)]
    assert [(e.problem_code, e.version) for e in incremental if e.problem_code] == [
        ("invalid_meta", other)
    ]


@pytest.mark.parametrize(
    ("which", "filters"),
    [
        (0, {"kind": "archive"}),
        (0, {"kind": "pmaxtp"}),
        (0, {"provider": "CHMI"}),
        (1, {"kind": "series"}),
        (1, {"kind": "catalog"}),
        (1, {"provider": "CHMI"}),
    ],
)
def test_the_filters_apply_to_the_versions_that_are_skipped(roots, which, filters):
    root = roots[which]
    known = known_versions(root, iter_store(root))
    everything = list(iter_store(root, skip_versions=known))

    wanted = list(iter_store(root, skip_versions=known, **filters))
    assert wanted == [
        entry
        for entry in everything
        if entry.kind == filters.get("kind", entry.kind)
        and entry.provider in (filters.get("provider", entry.provider), None)
    ]
    assert any(entry.skipped for entry in wanted)


def test_what_names_no_version_of_the_store_is_read_as_unknown(roots):
    for root, slot in zip(
        roots, (DAILY_2024, "series:pl.imgw.hydro_daily"), strict=True
    ):
        full = list(iter_store(root))
        version = next(entry for entry in full if entry.slot == slot and entry.meta)
        known = {
            "archives/versions": ("x.zip",),
            "archives/versions/dane_hydrologiczne/dobowe/2024": ("codz_2024.zip",),
            "series/versions/hydro_daily/2026-01-01_deadbeef": ("series.json",),
            "elsewhere/2026-01-01_deadbeef": ("codz_2024.zip",),
            # a version whose names lack its main file: the caller is not sure of it
            version.version.parent.relative_to(root).as_posix(): ("another.zip",),
        }

        assert list(iter_store(root, skip_versions=known)) == full


@pytest.mark.parametrize("known", [None, {}], ids=["none", "empty"])
def test_nothing_known_is_a_full_scan(roots, known):
    for root in roots:
        assert list(iter_store(root, skip_versions=known)) == list(iter_store(root))


@pytest.mark.parametrize(
    "known",
    [
        ["archives/versions/a/2026-01-01_deadbeef"],
        "archives/versions/a/2026-01-01_deadbeef",
        {"archives/versions/a/2026-01-01_deadbeef": "codz_2024.zip"},
        {"archives/versions/a/2026-01-01_deadbeef": None},
        {"archives/versions/a/2026-01-01_deadbeef": [2024]},
        {"archives/versions/a/2026-01-01_deadbeef": ["a/codz_2024.zip"]},
        {"archives/versions/a/2026-01-01_deadbeef": [".."]},
        {"archives/versions/a/2026-01-01_deadbeef": ["codz_2024.zip.meta.json"]},
        {1: ["codz_2024.zip"]},
    ],
)
def test_skip_versions_must_map_directories_to_file_names(tmp_path, known):
    root = init_store(tmp_path / "store").root

    # Refused at the call, not at the first entry.
    with pytest.raises(ObserwatorValidationError) as error:
        iter_store(root, skip_versions=known)

    assert error.value.details == {"option": "skip_versions"}
