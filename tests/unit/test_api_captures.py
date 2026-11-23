"""REST never serves a private capture (ADR-030 D5, P15): its dataset and versions are not_found."""

import json
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from obserwator.api.instance import served_instance
from obserwator.api.main import app
from obserwator.captures import write_spool
from obserwator.commands import check_command, run_command
from obserwator.config import settings
from obserwator.providers.base import Answer
from obserwator.store import init_store, iter_store, sync_store

PRIVATE = "pl.imgw.hydro_states_current"  # hydro.imgw.pl's map: private by default
PUBLIC = "pl.imgw.hydro_current"  # danepubliczne.imgw.pl's API: public by default
URLS = {
    PRIVATE: "https://hydro-back.imgw.pl/map/stations/hydrologic?onlyMainStations=false",
    PUBLIC: "https://danepubliczne.imgw.pl/api/data/hydro",
}
# A closed UTC day: store sync seals it.
ANSWERED = datetime(2026, 11, 20, 10, 15, tzinfo=UTC)
TOKEN = "s3cret-token"


def spool(day: datetime = ANSWERED) -> None:
    """One answer of each capture dataset in the spool, on the UTC day of ``day``."""
    for key, url in URLS.items():
        write_spool(
            Answer(url=url, received_at=day, status=200, content=b"[]", dataset=key)
        )


@pytest.fixture
def server(monkeypatch, tmp_path):
    """
    A REST server on a raw root holding a sealed day of a private and a public capture.

    Its own spool (``OBSERWATOR_STATE_DIR``) and ``nogat.toml`` (no
    ``[obserwator.capture]``: the defaults), writes enabled with a token.
    """
    monkeypatch.setenv("OBSERWATOR_STATE_DIR", str(tmp_path / "state"))
    config = tmp_path / "nogat.toml"
    config.write_text("", encoding="utf-8")
    monkeypatch.setenv("NOGAT_CONFIG", str(config))
    served_instance.cache_clear()
    raw = init_store(tmp_path / "raw").root
    spool()
    versions = {}
    for key in URLS:
        (item,) = sync_store(raw, datasets=[key]).items
        assert item.status == "new"
        versions[key] = item.version.relative_to(raw).as_posix()
    for name, value in (
        ("root", None),
        ("raw_root", raw),
        ("store_writes_enabled", True),
        ("store_write_token", SecretStr(TOKEN)),
    ):
        monkeypatch.setattr(settings, name, value)
    yield SimpleNamespace(
        raw=raw, versions=versions, config=config, client=TestClient(app)
    )
    served_instance.cache_clear()


def assert_private(answer, key, option):
    assert answer.status_code == 404
    problem = answer.json()
    assert problem["code"] == "not_found"
    assert problem["details"]["reason"] == "private"
    assert problem["details"]["option"] == option
    assert key in problem["detail"]


def test_a_private_capture_dataset_is_not_found_by_store_check_and_sync(server):
    spool(datetime(2026, 11, 21, 9, 0, tzinfo=UTC))  # a day to seal
    client = server.client

    checked = client.get("/api/v1/store/check", params={"datasets": PRIVATE})
    planned = client.post("/api/v1/store/sync?check=true", json={"datasets": [PRIVATE]})
    sealed = client.post(
        "/api/v1/store/sync",
        json={"datasets": [PRIVATE]},
        headers={"X-API-Key": TOKEN},
    )

    for answer in (checked, planned, sealed):
        assert_private(answer, PRIVATE, "datasets")
    # Nothing was sealed: the private day waits in the spool for the command line.
    left = run_command(
        "store check", options={"root": server.raw, "datasets": [PRIVATE]}
    )
    assert [item.status for item in left.result.items] == ["missing"]


def test_a_public_capture_dataset_is_served(server):
    spool(datetime(2026, 11, 21, 9, 0, tzinfo=UTC))

    checked = server.client.get("/api/v1/store/check", params={"datasets": PUBLIC})
    sealed = server.client.post(
        "/api/v1/store/sync",
        json={"datasets": [PUBLIC]},
        headers={"X-API-Key": TOKEN},
    )

    assert checked.status_code == 200
    assert [item["status"] for item in checked.json()["result"]["items"]] == ["missing"]
    assert sealed.status_code == 200
    assert [item["status"] for item in sealed.json()["result"]["items"]] == ["new"]


def test_a_store_sync_plan_holding_a_private_capture_is_not_found(server, tmp_path):
    spool(datetime(2026, 11, 21, 9, 0, tzinfo=UTC))
    path = tmp_path / "plan.json"
    check_command(
        "store check", options={"root": server.raw, "datasets": [PRIVATE]}
    ).result.to_json(path)
    body = json.loads(path.read_text(encoding="utf-8"))

    answer = server.client.post(
        "/api/v1/store/sync", json={"plan": body}, headers={"X-API-Key": TOKEN}
    )

    assert_private(answer, PRIVATE, "plan")


def test_a_version_of_a_private_capture_is_not_found_whether_it_exists_or_not(
    server,
):
    stored = server.versions[PRIVATE]
    absent = stored.replace("2026-11-20", "2026-11-19")

    for version in (stored, absent, stored.rsplit("/", 1)[0]):
        answer = server.client.get(
            "/api/v1/store/export", params={"version": version, "format": "jsonl"}
        )
        assert_private(answer, PRIVATE, "version")
    # The library and the command line read it: the version is in the store.
    assert any(
        entry.slot == f"archive:{PRIVATE}:2026-11-20.jsonl.gz"
        for entry in iter_store(server.raw)
    )


def test_a_version_of_a_public_capture_reaches_the_command(server):
    answer = server.client.get(
        "/api/v1/store/export",
        params={"version": server.versions[PUBLIC], "format": "jsonl"},
    )

    # The version exists: only the guard of private captures would answer 404 here.
    assert answer.status_code != 404


def test_the_operator_decides_per_request_in_nogat_toml(server):
    server.config.write_text(
        f'[obserwator.capture]\n"{PRIVATE}" = "public"\n"{PUBLIC}" = "private"\n',
        encoding="utf-8",
    )

    opened = server.client.get("/api/v1/store/check", params={"datasets": PRIVATE})
    closed = server.client.get("/api/v1/store/check", params={"datasets": PUBLIC})

    assert opened.status_code == 200
    assert_private(closed, PUBLIC, "datasets")
