"""The raw root and the data root (ADR-017): the split of a combined store, wrong roots,
builders that only read the raw root, analyses in the data root."""

import os
import shutil
from pathlib import Path

import pytest

from obserwator.exceptions import ObserwatorStoreError
from obserwator.output import DATA_MARKER, STORE_MARKER
from obserwator.store import (
    build_analyses,
    build_catalog,
    build_series,
    current_version,
    init_store,
    iter_store,
)
from tests.contract.support import use_fake_hydrolog

RAW_TREES = ("archives", "pmaxtp")
DATA_TREES = ("series", "stations", "analyses")
SLOTS = {"analyses:pl.imgw.analyses": "IMGW-PIB", "analyses:cz.chmi.analyses": "CHMI"}


@pytest.fixture(scope="module")
def analysed(tmp_path_factory, fixture_roots):
    """A copy of the fixture data root with the analyses of the recorded Hydrolog."""
    root = tmp_path_factory.mktemp("analysed") / "data"
    shutil.copytree(fixture_roots.data.root, root)
    with pytest.MonkeyPatch.context() as patch:
        use_fake_hydrolog(patch)
        assert build_analyses(root).status == "new"
    return root


@pytest.fixture
def combined(tmp_path, fixture_roots, analysed):
    """A store as before ADR-017: the trees of both kinds under the raw marker."""
    root = tmp_path / "old"
    shutil.copytree(fixture_roots.raw.root, root)
    for tree in DATA_TREES:
        shutil.copytree(analysed / tree, root / tree)
    return root


def problems(root: Path) -> list[tuple[str | None, str | None]]:
    return [(e.problem_code, e.problem) for e in iter_store(root, kind="problem")]


def currents(root: Path) -> dict[str, Path]:
    """The current version of every slot of the root, relative to the root."""
    slots = {
        entry.slot
        for entry in iter_store(root)
        if entry.slot and entry.kind not in ("problem", "observation")
    }
    found = {slot: current_version(root, slot=slot) for slot in slots}
    return {
        slot: entry.version.relative_to(root)
        for slot, entry in found.items()
        if entry is not None and entry.version is not None
    }


def snapshot(root: Path) -> dict[str, tuple[int, int]]:
    """Path, size and modification time of everything in the root."""
    return {
        path.relative_to(root).as_posix(): (
            path.lstat().st_size,
            path.lstat().st_mtime_ns,
        )
        for path in (root, *root.rglob("*"))
    }


def test_the_documented_split_gives_two_clean_roots_with_the_same_current_versions(
    tmp_path, combined, fixture_roots, analysed
):
    raw, data = tmp_path / "raw", tmp_path / "data"
    raw.mkdir()
    data.mkdir()
    for trees, target in ((RAW_TREES, raw), (DATA_TREES, data)):
        for tree in trees:
            if (combined / tree).is_dir():
                shutil.copytree(combined / tree, target / tree, copy_function=os.link)

    assert init_store(raw).kind == "raw"
    assert init_store(data, kind="data").kind == "data"

    assert problems(raw) == []
    assert problems(data) == []
    assert currents(raw) == currents(fixture_roots.raw.root) != {}
    assert currents(data) == currents(analysed) != {}
    archive = next(iter_store(raw, kind="archive")).version
    assert archive is not None
    assert archive.samefile(combined / archive.relative_to(raw))  # hard links


def test_a_store_not_yet_split_is_refused_as_a_data_root_and_scans_as_a_raw_one(
    combined,
):
    for refused in (
        lambda: current_version(combined, slot="series:pl.imgw.hydro_daily"),
        lambda: build_series(
            combined, raw_root=combined, dataset="pl.imgw.hydro_daily"
        ),
        lambda: init_store(combined, kind="data"),
    ):
        with pytest.raises(ObserwatorStoreError) as error:
            refused()
        assert error.value.code == "store_unavailable"
        assert error.value.details == {"reason": "wrong_root", "kind": "data"}
        assert STORE_MARKER in str(error.value)
        assert DATA_MARKER in str(error.value)

    scanned = list(iter_store(combined, kind="problem"))
    assert {entry.version.name for entry in scanned if entry.version} == set(DATA_TREES)
    assert {entry.problem_code for entry in scanned} == {"unknown_entry"}
    assert list(iter_store(combined, kind="series")) == []
    assert list(iter_store(combined, kind="archive")) != []


def test_series_and_catalog_builds_leave_the_raw_root_untouched(
    tmp_path, fixture_roots
):
    raw, data = tmp_path / "raw", tmp_path / "data"
    shutil.copytree(fixture_roots.raw.root, raw)
    before = snapshot(raw)
    tree = [raw, *raw.rglob("*")]
    if os.name == "posix":
        for path in tree:
            path.chmod(0o555 if path.is_dir() else 0o444)
    try:
        series = build_series(data, raw_root=raw, dataset="pl.imgw.hydro_daily")
        catalog = build_catalog(data, raw_root=raw)
    finally:
        if os.name == "posix":
            for path in tree:
                path.chmod(0o755 if path.is_dir() else 0o644)

    assert (series.status, catalog.status) == ("new", "new")
    assert (data / DATA_MARKER).is_file()
    assert not (data / STORE_MARKER).exists()
    assert series.source_files
    assert all(raw in source.parents for source in series.source_files)
    assert snapshot(raw) == before


def test_analyses_are_entries_and_current_versions_of_the_data_root(
    analysed, fixture_roots
):
    entries = list(iter_store(analysed, kind="analyses"))

    assert {entry.slot: entry.provider for entry in entries} == SLOTS
    for entry in entries:
        assert entry.version is not None
        assert entry.version.name == "analyses.json"
        assert entry.meta is not None
        assert entry.meta.extra["derived"] == "analyses"
        assert current_version(analysed, slot=entry.slot) == entry
    assert problems(analysed) == []
    with pytest.raises(ObserwatorStoreError) as error:
        current_version(fixture_roots.raw.root, slot="analyses:pl.imgw.analyses")
    assert error.value.details == {"reason": "wrong_root", "kind": "data"}
    assert list(iter_store(fixture_roots.raw.root, kind="analyses")) == []
