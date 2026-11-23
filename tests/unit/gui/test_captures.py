"""The GUI's live answers in the capture spool and the next sealed version (ADR-030 D7)."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from obserwator import captures
from obserwator.datasets import get_provider
from obserwator.store import init_store, sync_store
from obserwator.store.captures import decode
from obserwator.testing import _interactions, _recorded_http
from tests.unit.gui.conftest import HYDRO

FILES = ("recordings.json", "contract_recordings.json")
CASES = {
    "pl.imgw.hydro_current": "hydro_current",
    "pl.imgw.meteo_current": "meteo_current",
    "pl.imgw.meteo_synop_current": "synop_current",
    "pl.imgw.warnings_hydro_current": "warnings_hydro",
    "pl.imgw.warnings_meteo_current": "warnings_meteo",
    "pl.imgw.hydro_states_current": "hydro_states",
}
"""The recorded answer of each source of the hourly poll."""
GUI_CASES = ("hydro_current", "hydro_states")
"""What a hydrological station's card fetches: ``current hydro`` and the water states."""
OPENED = datetime(2026, 11, 21, 10, 5, tzinfo=UTC)
POLLED = datetime(2026, 11, 21, 11, 15, tzinfo=UTC)
NEXT_DAY = datetime(2026, 11, 22, 0, 30, tzinfo=UTC)


def test_a_card_opened_in_the_gui_and_the_hourly_poll_are_in_the_next_sealed_version(
    make_client, tmp_path, monkeypatch
):
    monkeypatch.setenv("OBSERWATOR_STATE_DIR", str(tmp_path / "state"))
    (tmp_path / "nogat.toml").write_text("", encoding="utf-8")
    monkeypatch.setenv("NOGAT_CONFIG", str(tmp_path / "nogat.toml"))
    imgw = get_provider("IMGW").adapter
    client = make_client(sources=imgw.current)  # the library's fetchers
    recorded = _interactions(FILES)

    monkeypatch.setattr(captures, "_now", lambda: OPENED)
    with _recorded_http(GUI_CASES, recordings=FILES, keep=True):
        card = client.get(f"/api/current/{HYDRO}")
    monkeypatch.setattr(captures, "_now", lambda: POLLED)
    with _recorded_http(list(CASES.values()), recordings=FILES, keep=True):
        polled = captures.poll_current()
    monkeypatch.setattr(captures, "_now", lambda: NEXT_DAY)
    keys = [source.dataset for source in imgw.polled]
    synced = sync_store(init_store(tmp_path / "raw"), datasets=keys)

    # The card is answered as without the spool.
    assert card.status_code == 200
    document = card.json()
    assert (document["station"], document["kind"], document["state"]) == (
        HYDRO,
        "hydro",
        "medium",
    )
    assert document["record"]["station_name"] == "Raba Górna"
    assert [answer.status for answer in polled.answers] == ["captured"] * len(keys)
    # One version of the day per source holds every answer, the GUI's and the poll's.
    assert sorted(CASES) == sorted(keys)
    assert [item.status for item in synced.items] == ["new"] * len(keys)
    sealed = {
        item.slot.split(":")[1]: decode(item.version.read_bytes())
        for item in synced.items
    }
    for key, case in CASES.items():
        opened = ["2026-11-21T10:05:00.000000Z"] if case in GUI_CASES else []
        assert [(a.time, a.address, a.status) for a in sealed[key]] == [
            (time, recorded[case]["url"], 200)
            for time in [*opened, "2026-11-21T11:15:00.000000Z"]
        ]
        assert all(json.loads(a.content) == recorded[case]["json"] for a in sealed[key])
