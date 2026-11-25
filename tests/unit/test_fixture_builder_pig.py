"""build_fixture_store(variant="groundwater_pl"): the variant groundwater plus PIG-PIB.

PIG-PIB's part (ADR-035) is synchronized from the rows of ``pig_recordings.json`` on a
clock of its own that starts at the probe's capture, so it never sleeps, reaches no
network and no real capture spool, and two builds are byte-identical under a frozen
clock; every file of the variant ``groundwater`` stays as it was.
"""

import hashlib
import re
import socket
from datetime import UTC, datetime

from obserwator.store import catalog, series, subdaily, writer
from obserwator.testing import build_fixture_store

LABEL = re.compile(r"/[0-9]{4}-[0-9]{2}-[0-9]{2}_[0-9a-f]{8}/.*")


def refuse(*args, **kwargs):
    raise AssertionError("a network connection in an offline test")


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


def test_groundwater_pl_adds_pig_pib_alone_and_builds_identically(
    tmp_path, monkeypatch
):
    class Frozen(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 10, 20, 9, 0, tzinfo=UTC).astimezone(tz)

    for module in (writer, series, subdaily, catalog):
        monkeypatch.setattr(module, "datetime", Frozen)
    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    spool = tmp_path / "state" / "obserwator" / "captures"
    monkeypatch.setenv("OBSERWATOR_STATE_DIR", str(tmp_path / "state"))

    groundwater = tree(
        build_fixture_store(
            tmp_path / "a", data_root=tmp_path / "a-data", variant="groundwater"
        )
    )
    first = tree(
        build_fixture_store(
            tmp_path / "b", data_root=tmp_path / "b-data", variant="groundwater_pl"
        )
    )
    second = tree(
        build_fixture_store(
            tmp_path / "c", data_root=tmp_path / "c-data", variant="groundwater_pl"
        )
    )

    assert first == second
    assert {name: first.get(name) for name in groundwater} == groundwater
    # The slots of PIG-PIB's part: its three datasets and what is built of them.
    assert {LABEL.sub("", name) for name in set(first) - set(groundwater)} == {
        "raw/archives/versions/mwp/MapServer/0/MWP_points",
        "raw/archives/versions/mwp/MapServer/1/MWP_2026-10",
        "raw/archives/versions/mwp_auto/MapServer/2026-11-24",
        "data/series/versions/pig_groundwater_readings",
        "data/series/versions/pig_groundwater_subdaily/2026-03",
        "data/series/versions/pig_groundwater_subdaily/2026-10",
        "data/series/versions/pig_groundwater_subdaily/2026-11",
        "data/stations/versions/pig_stations",
    }
    # The raw versions are dated by the part's clock, the probe's capture.
    assert {
        name.split("/")[-2][:10]
        for name in set(first) - set(groundwater)
        if name.startswith("raw/")
    } == {"2026-11-24"}
    assert not spool.exists()
