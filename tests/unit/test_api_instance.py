"""The REST server serves only what ``[obserwator.instance]`` serves (ADR-025)."""

import json
import os
import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest
import respx
from fastapi.testclient import TestClient
from pydantic import SecretStr
from typer.testing import CliRunner

from obserwator.api.instance import served_instance
from obserwator.api.main import app
from obserwator.cli import main as cli_main
from obserwator.commands import run_command
from obserwator.config import settings
from obserwator.datasets import archive_files
from obserwator.datasets import datasets as registry
from obserwator.exceptions import (
    ObserwatorStoreError,
    ObserwatorValidationError,
)
from obserwator.output import DATA_MARKER
from obserwator.store import analysis_definitions, current_version, init_store
from obserwator.store.types import PlanItem, StorePlan, page_cursor
from obserwator.testing import build_fixture_store
from tests.contract.support import DAILY, RABA, FakeImgw, use_fake_hydrolog

RUNNER = CliRunner()
TOKEN = "s3cret-token"
CHMI_DAILY = "cz.chmi.hydro_daily"
BEZ_Q = "149190311"  # in the IMGW-PIB series, no location in the catalog
NOWHERE = "149199999"  # no such IMGW-PIB station
SPINDLER = "0-203-1-900001"  # ČHMÚ, inside the clipped area
ZAPADLA = "0-203-1-900002"  # ČHMÚ, outside it
NO_CHMI = "0-203-1-999999"  # no such ČHMÚ station
MISSING_LABEL = "2000-01-01_00000000"
POINT = {
    "latitude": "52.23",
    "longitude": "21.01",
}  # Warszawa: the recorded PMAXTP point
CHMI_OFF = '[obserwator.instance.providers]\nCHMI = "off"\n'
IMGW_OFF = '[obserwator.instance.providers]\nIMGW-PIB = "off"\n'
# Every provider off: valid while PMAXTP is served.
NONE_SERVED = '[obserwator.instance.providers]\nIMGW-PIB = "off"\nCHMI = "off"\n'
CURRENT = (
    "current hydro",
    "current meteo",
    "current synop",
    "current warnings",
    "current hydro-states",
)


def square(west, south, east, north):
    return [[west, south], [east, south], [east, north], [west, north], [west, south]]


# Raba Górna (20.1, 49.7) of IMGW-PIB and Špindlerův Mlýn (15.60, 50.40) of ČHMÚ lie
# inside; Warszawa, the other ČHMÚ stations and every station without a location lie
# outside.
CLIPPED = {
    "type": "MultiPolygon",
    "coordinates": [
        [square(19.9, 49.5, 20.3, 49.9)],
        [square(15.5, 50.3, 15.7, 50.5)],
    ],
}
WARSAW = {"type": "Polygon", "coordinates": [square(20.9, 52.1, 21.1, 52.4)]}


def path_of(command):
    group, name = command.split(" ", 1)
    return f"/api/v1/{group}/{name}"


def problem(response, status, code):
    assert response.status_code == status, response.text
    assert response.headers["content-type"] == "application/problem+json"
    body = response.json()
    assert body["code"] == code
    return body


def alike(refused, missing, named, other):
    """Two refusals that differ only by the code or path each request named."""
    assert refused.status_code == missing.status_code == 404
    assert json.loads(json.dumps(missing.json()).replace(other, named)) == (
        refused.json()
    )


def relative(entry, root):
    return entry.version.relative_to(root).as_posix()


def missing_version(version):
    """The path of a version that is not in the store, beside ``version``."""
    parts = version.split("/")
    parts[-2] = MISSING_LABEL
    return "/".join(parts)


def deploy(tmp_path, monkeypatch, body="", area=None):
    """A ``nogat.toml`` with ``[obserwator.instance]`` (``area`` clips); read anew."""
    folder = tmp_path / "config"
    folder.mkdir(exist_ok=True)
    if area is not None:
        (folder / "area.geojson").write_text(json.dumps(area), encoding="utf-8")
        body = f'area = "area.geojson"\narea_mode = "clip"\n{body}'
    path = folder / "nogat.toml"
    path.write_text(f"[obserwator.instance]\n{body}", encoding="utf-8")
    monkeypatch.setenv("NOGAT_CONFIG", str(path))
    served_instance.cache_clear()


@pytest.fixture(autouse=True)
def server(monkeypatch, tmp_path):
    """Unconfigured server without an instance; the instance is read anew per test."""
    for name, value in (
        ("root", None),
        ("raw_root", None),
        ("store_writes_enabled", False),
        ("store_write_token", None),
        ("store_write_token_file", None),
        ("user_locations_dir", None),
        ("api_max_limit", 1000),
    ):
        monkeypatch.setattr(settings, name, value)
    for name in ("OBSERWATOR_STORE_WRITE_TOKEN", "OBSERWATOR_STORE_WRITE_TOKEN_FILE"):
        monkeypatch.delenv(name, raising=False)
    empty = tmp_path / "empty.toml"
    empty.write_text("", encoding="utf-8")
    monkeypatch.setenv("NOGAT_CONFIG", str(empty))
    served_instance.cache_clear()
    yield
    served_instance.cache_clear()


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def served(monkeypatch, fixture_root, fixture_raw_root):
    """The fixture roots served: the data root."""
    monkeypatch.setattr(settings, "root", fixture_root)
    monkeypatch.setattr(settings, "raw_root", fixture_raw_root)
    return fixture_root


@pytest.fixture
def empty_raw_root(monkeypatch, tmp_path):
    root = init_store(tmp_path / "raw").root
    monkeypatch.setattr(settings, "raw_root", root)
    return root


@pytest.fixture
def writable(monkeypatch):
    monkeypatch.setattr(settings, "store_writes_enabled", True)
    monkeypatch.setattr(settings, "store_write_token", SecretStr(TOKEN))
    return {"X-API-Key": TOKEN}


@pytest.fixture
def imgw():
    """Recorded sources; ``traffic()`` lists every request that left."""
    with respx.mock(assert_all_called=False) as router:
        yield FakeImgw(router)


@pytest.fixture
def uvicorn_calls(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "uvicorn.run", lambda app, **kwargs: calls.append((app, kwargs))
    )
    monkeypatch.setattr(settings, "host", settings.host)
    monkeypatch.setattr(settings, "port", settings.port)
    return calls


# --------------------------------------------------------------------------
# datasets
# --------------------------------------------------------------------------


def test_datasets_routes_list_and_page_only_the_providers_served(
    client, tmp_path, monkeypatch
):
    deploy(tmp_path, monkeypatch, CHMI_OFF)
    served = [item.key for item in registry() if item.provider == "IMGW-PIB"]

    pages, cursor = [], None
    while True:
        params = {"limit": 5} | ({} if cursor is None else {"cursor": cursor})
        pages.append(client.get(path_of("datasets list"), params=params).json())
        cursor = pages[-1]["page"]["next_cursor"]
        if cursor is None:
            break
    found = client.get(path_of("datasets providers")).json()
    named = client.get(path_of("datasets list"), params={"provider": "cz.chmi"})
    files = client.get(
        path_of("datasets files"),
        params={"dataset": "chmi_hydro_daily", "years": "2023", "stations": SPINDLER},
    )

    assert [item["key"] for page in pages for item in page["result"]] == served
    assert {page["page"]["total"] for page in pages} == {len(served)}
    assert all("attribution" not in page for page in [*pages, found])
    assert [item["id"] for item in found["result"]] == ["IMGW-PIB"]
    assert found["page"]["total"] == 1
    assert problem(named, 404, "not_found")["details"] == {
        "option": "provider",
        "value": "CHMI",
        "reason": "not_served",
    }
    assert problem(files, 404, "not_found")["details"] == {
        "option": "dataset",
        "value": CHMI_DAILY,
        "reason": "not_served",
    }


@pytest.mark.parametrize(
    ("command", "query"),
    [
        ("datasets list", {"limit": "4"}),
        ("datasets providers", {}),
        ("stations find", {"source": "store"}),
        ("stations export", {}),
        ("store info", {}),
        ("store scan", {}),
        ("series summary", {"dataset": DAILY}),
    ],
)
def test_an_instance_serving_everything_answers_as_none(
    client, served, tmp_path, monkeypatch, command, query
):
    plain = client.get(path_of(command), params=query)
    deploy(tmp_path, monkeypatch, 'title = "Wszystko"\n')

    scoped = client.get(path_of(command), params=query)

    assert plain.status_code == scoped.status_code == 200
    assert scoped.content == plain.content
    assert scoped.headers.get("x-obserwator-attribution") == plain.headers.get(
        "x-obserwator-attribution"
    )


# --------------------------------------------------------------------------
# stations
# --------------------------------------------------------------------------


def test_stations_find_names_the_one_provider_served(
    client, served, tmp_path, monkeypatch, imgw
):
    imgw.publish_catalog_sources()
    deploy(tmp_path, monkeypatch, CHMI_OFF)

    stored = client.get(path_of("stations find"), params={"source": "store"})
    live = client.get(path_of("stations find"), params={"kind": "hydro"})
    named = client.get(
        path_of("stations find"), params={"source": "store", "provider": "CHMI"}
    )
    deploy(tmp_path, monkeypatch, NONE_SERVED)
    nothing = client.get(path_of("stations find"), params={"source": "store"})

    expected = run_command(
        "stations find",
        options={"source": "store", "provider": "IMGW-PIB", "root": served},
    )
    assert stored.json() == expected.to_json(root=served, server=True)
    assert {entry["provider"] for entry in live.json()["result"]} == {"IMGW-PIB"}
    assert imgw.traffic() and all("chmi" not in url for _, url in imgw.traffic())
    assert problem(named, 404, "not_found")["details"] == {
        "option": "provider",
        "value": "CHMI",
        "reason": "not_served",
    }
    assert problem(nothing, 404, "not_found")["details"] == {
        "option": "provider",
        "reason": "not_served",
    }


def test_stations_find_under_clip_pages_only_the_stations_inside(
    client, served, tmp_path, monkeypatch
):
    deploy(tmp_path, monkeypatch, area=CLIPPED)
    query = {"source": "store", "limit": 1}

    first = client.get(path_of("stations find"), params=query).json()
    cursor = first["page"]["next_cursor"]
    second = client.get(
        path_of("stations find"), params=query | {"cursor": cursor}
    ).json()

    assert [e["station_code"] for e in first["result"] + second["result"]] == [
        RABA,
        SPINDLER,
    ]
    assert first["page"] == {
        "total": 2,
        "next_cursor": page_cursor(1),
        "truncated": True,
    }
    assert second["page"] == {"total": 2, "next_cursor": None, "truncated": False}
    # The lines of each page are those of its own stations, as run_command's.
    for page, code, provider in ((first, RABA, "IMGW-PIB"), (second, SPINDLER, "CHMI")):
        alone = run_command(
            "stations find",
            options={
                "source": "store",
                "query": code,
                "provider": provider,
                "root": served,
            },
        )
        assert page["attribution"] == list(alone.attribution)


def test_stations_export_holds_only_the_stations_served_and_their_lines(
    client, served, tmp_path, monkeypatch
):
    deploy(tmp_path, monkeypatch, CHMI_OFF)
    narrowed = client.get(path_of("stations export"))
    deploy(tmp_path, monkeypatch, area=CLIPPED)
    clipped = client.get(path_of("stations export"))

    expected = run_command(
        "stations export", options={"provider": "IMGW-PIB", "root": served}
    )
    assert narrowed.text == "".join(expected.result)
    assert json.loads(narrowed.headers["x-obserwator-attribution"]) == list(
        expected.attribution
    )
    document = json.loads(clipped.text)
    assert [feature["id"] for feature in document["features"]] == [RABA, SPINDLER]
    assert (
        json.loads(clipped.headers["x-obserwator-attribution"])
        == (document["attribution"])
    )


# --------------------------------------------------------------------------
# current data
# --------------------------------------------------------------------------


def test_current_routes_of_an_off_imgw_pib_are_404_without_a_request(
    client, served, tmp_path, monkeypatch, imgw
):
    imgw.publish_live()
    deploy(tmp_path, monkeypatch, IMGW_OFF)

    answers = [client.get(path_of(command)) for command in CURRENT]
    station = client.get(path_of("current hydro"), params={"station": RABA})
    catalog = client.post(f"{path_of('store catalog')}?check=true", json={})

    for response in [*answers, station]:
        assert problem(response, 404, "not_found")["details"] == {
            "reason": "not_served"
        }
    # store catalog builds IMGW-PIB's catalog unless told otherwise.
    assert problem(catalog, 404, "not_found")["details"] == {
        "option": "provider",
        "value": "IMGW-PIB",
        "reason": "not_served",
    }
    assert imgw.traffic() == []


def test_current_data_under_clip_keep_the_stations_inside(
    client, served, tmp_path, monkeypatch, imgw
):
    imgw.publish_live()
    deploy(tmp_path, monkeypatch, area=CLIPPED)

    hydro = client.get(path_of("current hydro")).json()
    states = client.get(path_of("current hydro-states")).json()
    meteo = client.get(path_of("current meteo")).json()
    warnings = client.get(path_of("current warnings"), params={"kind": "meteo"})
    synop = client.get(path_of("current synop"))
    unlocated = client.get(path_of("current hydro"), params={"station": "149190312"})
    unknown = client.get(path_of("current hydro"), params={"station": NOWHERE})

    assert [item["station_code"] for item in hydro["result"]] == [RABA]
    assert hydro["page"]["total"] == 1
    # The map locates the station without a catalog location inside the area.
    assert [item["station_code"] for item in states["result"]] == [RABA, BEZ_Q]
    assert (meteo["result"], meteo["page"]["total"]) == ([], 0)
    assert warnings.json() == run_command(
        "current warnings", options={"kind": "meteo"}
    ).to_json(server=True)
    assert problem(synop, 403, "forbidden")["details"] == {"reason": "instance_clip"}
    assert problem(unlocated, 404, "not_found")["details"] == {
        "option": "station",
        "value": "149190312",
        "reason": "not_served",
    }
    alike(unlocated, unknown, "149190312", NOWHERE)


# --------------------------------------------------------------------------
# PMAXTP
# --------------------------------------------------------------------------


def test_pmaxtp_off_answers_404_on_every_route_without_a_request(
    client, empty_raw_root, tmp_path, monkeypatch, imgw, writable
):
    imgw.publish_pmaxtp("pmaxtp_pot_first")
    deploy(tmp_path, monkeypatch, 'pmaxtp = "off"\n')

    answers = [
        client.get(path_of("pmaxtp fetch"), params=POINT),
        client.get(path_of("pmaxtp url"), params=POINT),
        client.get(path_of("pmaxtp check"), params=POINT),
        client.get(path_of("pmaxtp read"), params={"ind_x": 751, "ind_y": 317}),
        client.post(f"{path_of('pmaxtp sync')}?check=true", json=POINT),
        client.post(path_of("pmaxtp sync"), json=POINT, headers=writable),
    ]
    keys = [
        item["key"] for item in client.get(path_of("datasets list")).json()["result"]
    ]

    for response in answers:
        assert problem(response, 404, "not_found")["details"] == {
            "reason": "pmaxtp_off"
        }
    assert imgw.traffic() == []
    assert list(empty_raw_root.rglob("cell.json")) == []
    assert keys == [item.key for item in registry() if item.key != "pl.imgw.pmaxtp"]


def test_pmaxtp_under_clip_serves_only_points_and_cells_inside(
    client, empty_raw_root, tmp_path, monkeypatch, imgw, writable
):
    imgw.publish_pmaxtp("pmaxtp_pot_first")
    synced = client.post(path_of("pmaxtp sync"), json=POINT, headers=writable)
    result = synced.json()["result"]
    cell = {"ind_x": result["ind_x"], "ind_y": result["ind_y"]}
    before = len(imgw.traffic())

    deploy(tmp_path, monkeypatch, area=WARSAW)
    fetched = client.get(path_of("pmaxtp fetch"), params=POINT)
    read = client.get(path_of("pmaxtp read"), params=cell)
    elsewhere = client.get(
        path_of("pmaxtp url"), params={"latitude": "49.7", "longitude": "20.1"}
    )
    deploy(tmp_path, monkeypatch, area=CLIPPED)
    refused = client.get(path_of("pmaxtp fetch"), params=POINT)
    checked = client.post(f"{path_of('pmaxtp sync')}?check=true", json=POINT)
    outside = client.get(path_of("pmaxtp read"), params=cell)

    assert fetched.status_code == 200, fetched.text
    assert fetched.json()["result"]["data"] == result["result"]["data"]
    assert read.status_code == 200, read.text
    for response in (elsewhere, refused, checked):
        assert problem(response, 404, "not_found")["details"] == {
            "option": "latitude",
            "reason": "outside_area",
        }
    assert problem(outside, 404, "not_found")["details"] == {
        "option": "ind_x",
        "reason": "outside_area",
    }
    assert len(imgw.traffic()) == before + 1  # only the point inside was fetched


# --------------------------------------------------------------------------
# series
# --------------------------------------------------------------------------


def test_series_under_clip_answer_only_the_stations_inside(
    client, served, tmp_path, monkeypatch
):
    deploy(tmp_path, monkeypatch, area=CLIPPED)

    summary = client.get(path_of("series summary"), params={"dataset": DAILY})
    clipped = client.get(
        path_of("series read"), params={"dataset": DAILY, "station": BEZ_Q}
    )
    unknown = client.get(
        path_of("series read"), params={"dataset": DAILY, "station": NOWHERE}
    )
    selected = client.get(
        path_of("series select"),
        params={"dataset": DAILY, "stations": [RABA, BEZ_Q]},
    )
    inside = client.get(
        path_of("series export"), params={"dataset": CHMI_DAILY, "station": SPINDLER}
    )
    outside = client.get(
        path_of("series export"), params={"dataset": CHMI_DAILY, "station": ZAPADLA}
    )

    expected = run_command(
        "series summary", options={"dataset": DAILY, "stations": [RABA], "root": served}
    )
    assert (
        summary.json()["result"] == expected.to_json(root=served, server=True)["result"]
    )
    assert summary.json()["page"]["total"] == len(expected.result)
    assert problem(clipped, 404, "not_found")["details"] == {
        "option": "station",
        "value": BEZ_Q,
        "reason": "not_served",
    }
    alike(clipped, unknown, BEZ_Q, NOWHERE)
    assert problem(selected, 404, "not_found")["details"]["value"] == BEZ_Q
    exported = run_command(
        "series export",
        options={"dataset": CHMI_DAILY, "station": SPINDLER, "root": served},
    )
    assert inside.text == "".join(exported.result)
    problem(outside, 404, "not_found")


def test_series_of_an_off_provider_are_404_by_dataset_and_by_version(
    client, served, tmp_path, monkeypatch
):
    deploy(tmp_path, monkeypatch, CHMI_OFF)
    version = relative(current_version(served, slot=f"series:{CHMI_DAILY}"), served)
    missing = missing_version(version)

    by_key = client.get(
        path_of("series read"), params={"dataset": CHMI_DAILY, "station": SPINDLER}
    )
    by_slug = client.get(
        path_of("series summary"), params={"dataset": "chmi_hydro_daily"}
    )
    by_version = client.get(path_of("series summary"), params={"version": version})
    by_missing = client.get(path_of("series summary"), params={"version": missing})

    assert problem(by_key, 404, "not_found")["details"] == {
        "option": "dataset",
        "value": CHMI_DAILY,
        "reason": "not_served",
    }
    assert problem(by_slug, 404, "not_found")["details"]["value"] == CHMI_DAILY
    assert problem(by_version, 404, "not_found")["details"] == {
        "option": "version",
        "value": version,
        "reason": "not_served",
    }
    alike(by_version, by_missing, version, missing)


# --------------------------------------------------------------------------
# analyses
# --------------------------------------------------------------------------


def test_analyses_of_an_off_provider_are_404_and_its_data_stop_a_build(
    client, served, tmp_path, monkeypatch
):
    deploy(tmp_path, monkeypatch, CHMI_OFF)
    analysis = analysis_definitions()[0].id

    listed = client.get(path_of("analyses list"), params={"station": SPINDLER})
    unknown = client.get(path_of("analyses list"), params={"station": NO_CHMI})
    read = client.get(
        path_of("analyses read"), params={"station": SPINDLER, "analysis": analysis}
    )
    exported = client.get(path_of("analyses export"), params={"station": SPINDLER})
    pinned = client.get(
        path_of("analyses list"),
        params={
            "station": RABA,
            "version": f"analyses/versions/cz.chmi/{MISSING_LABEL}",
        },
    )
    build = client.post(f"{path_of('analyses build')}?check=true", json={})

    for response in (listed, read, exported):
        assert problem(response, 404, "not_found")["details"] == {
            "option": "station",
            "value": SPINDLER,
            "reason": "not_served",
        }
    alike(listed, unknown, SPINDLER, NO_CHMI)
    assert problem(pinned, 404, "not_found")["details"]["option"] == "version"
    # The fixture's data root holds ČHMÚ series: a build would name ČHMÚ.
    assert problem(build, 403, "forbidden")["details"] == {"reason": "not_served"}


def test_analyses_build_of_a_root_without_the_off_provider_is_served(
    client, monkeypatch, tmp_path
):
    use_fake_hydrolog(monkeypatch, tmp_path / "scratch")
    roots = build_fixture_store(tmp_path / "raw", data_root=tmp_path / "data")
    monkeypatch.setattr(settings, "root", roots.data.root)
    deploy(tmp_path, monkeypatch, CHMI_OFF)

    planned = client.post(f"{path_of('analyses build')}?check=true", json={})

    assert planned.status_code == 200, planned.text
    assert planned.json()["status"] == "ok"


def test_analyses_under_clip_read_only_the_stations_inside(
    client, monkeypatch, tmp_path, fixture_root
):
    use_fake_hydrolog(monkeypatch, tmp_path / "scratch")
    root = Path(shutil.copytree(fixture_root, tmp_path / "data"))
    run_command("analyses build", options={"root": root})
    monkeypatch.setattr(settings, "root", root)
    deploy(tmp_path, monkeypatch, area=CLIPPED)

    inside = client.get(path_of("analyses list"), params={"station": RABA})
    outside = client.get(path_of("analyses list"), params={"station": ZAPADLA})
    unknown = client.get(path_of("analyses list"), params={"station": NO_CHMI})
    planned = client.post(f"{path_of('analyses build')}?check=true", json={})

    assert inside.status_code == 200, inside.text
    assert inside.json() == run_command(
        "analyses list", options={"station": RABA, "root": root}
    ).to_json(root=root, server=True)
    alike(outside, unknown, ZAPADLA, NO_CHMI)
    assert planned.status_code == 200, planned.text


# --------------------------------------------------------------------------
# store
# --------------------------------------------------------------------------


def chmi_plan(tmp_path):
    """An ``obserwator-plan/1`` document of one ČHMÚ archive, for the served raw root."""
    archive = archive_files(CHMI_DAILY, years=[2023], stations=[SPINDLER])[0]
    item = PlanItem(
        archive, "missing", None, None, None, None, None, None, SPINDLER, "listing"
    )
    plan = StorePlan("obserwator-plan/1", tmp_path, datetime.now(UTC), (item,), {})
    document = json.loads(plan.to_json(tmp_path / "plan.json").read_text("utf-8"))
    return document | {"root": "."}


def test_store_routes_hide_and_refuse_an_off_provider_before_any_request(
    client, served, fixture_raw_root, tmp_path, monkeypatch, imgw, writable
):
    deploy(tmp_path, monkeypatch, CHMI_OFF)
    slot = f"archive:{CHMI_DAILY}:H_{SPINDLER}_DQ_2023.json"
    archive = relative(current_version(fixture_raw_root, slot=slot), fixture_raw_root)
    missing = missing_version(archive)
    selection = {"datasets": [CHMI_DAILY], "stations": [SPINDLER]}

    info = client.get(path_of("store info")).json()["result"]
    scan = client.get(path_of("store scan")).json()
    refused = {
        "scan": client.get(path_of("store scan"), params={"provider": "CHMI"}),
        "check": client.get(path_of("store check"), params=selection),
        "sync check": client.post(
            f"{path_of('store sync')}?check=true", json=selection
        ),
        "sync": client.post(path_of("store sync"), json=selection, headers=writable),
        "plan": client.post(
            path_of("store sync"), json={"plan": chmi_plan(tmp_path)}, headers=writable
        ),
        "catalog": client.post(
            path_of("store catalog"), json={"provider": "CHMI"}, headers=writable
        ),
        "build": client.post(
            path_of("series build"), json={"dataset": CHMI_DAILY}, headers=writable
        ),
        "export": client.get(path_of("store export"), params={"version": archive}),
    }
    exported_missing = client.get(path_of("store export"), params={"version": missing})

    assert [provider["id"] for provider in info["providers"]] == ["IMGW-PIB"]
    assert {entry["provider"] for entry in scan["result"]} == {"IMGW-PIB"}
    assert scan["page"]["total"] == len(scan["result"])
    options = {
        name: problem(r, 404, "not_found")["details"] for name, r in refused.items()
    }
    assert {name: details["option"] for name, details in options.items()} == {
        "scan": "provider",
        "check": "datasets",
        "sync check": "datasets",
        "sync": "datasets",
        "plan": "plan",
        "catalog": "provider",
        "build": "dataset",
        "export": "version",
    }
    assert {details["reason"] for details in options.values()} == {"not_served"}
    alike(refused["export"], exported_missing, archive, missing)
    assert imgw.traffic() == []


def test_store_under_clip_refuses_what_it_cannot_reduce(
    client, served, fixture_raw_root, tmp_path, monkeypatch, imgw
):
    deploy(tmp_path, monkeypatch, area=CLIPPED)
    slot = f"archive:{DAILY}:2024/codz_2024.zip"
    archive = relative(current_version(fixture_raw_root, slot=slot), fixture_raw_root)
    synop = {"datasets": "pl.imgw.meteo_synop_daily", "years": "2023"}

    exported = client.get(path_of("store export"), params={"version": archive})
    every_station = client.get(path_of("store check"), params=synop)
    clipped = client.get(path_of("store check"), params=synop | {"stations": BEZ_Q})
    planned = client.post(
        f"{path_of('store sync')}?check=true",
        json={"datasets": ["pl.imgw.meteo_synop_daily"], "years": [2023]},
    )

    for response in (exported, every_station, planned):
        assert problem(response, 403, "forbidden")["details"] == {
            "reason": "instance_clip"
        }
    assert problem(clipped, 404, "not_found")["details"] == {
        "option": "stations",
        "value": BEZ_Q,
        "reason": "not_served",
    }
    assert imgw.traffic() == []


# --------------------------------------------------------------------------
# The start of the server and the write token
# --------------------------------------------------------------------------


def started():
    """Run the app's lifespan once (the start of the server)."""
    with TestClient(app):
        pass


def error_line(result):
    return json.loads(result.stderr.splitlines()[-1])


def test_a_problem_of_the_section_stops_the_start(tmp_path, monkeypatch, uvicorn_calls):
    deploy(tmp_path, monkeypatch, 'pmaxtp = "maybe"\n')

    with pytest.raises(ObserwatorValidationError) as caught:
        started()
    result = RUNNER.invoke(cli_main.app, ["server"])

    assert caught.value.details["option"] == "instance.pmaxtp"
    assert result.exit_code == 2
    assert result.stdout == ""
    error = error_line(result)
    assert (error["code"], error["details"]["option"]) == (
        "validation_error",
        "instance.pmaxtp",
    )
    assert uvicorn_calls == []


def test_an_instance_refuses_to_start_on_a_weak_write_token(
    tmp_path, monkeypatch, uvicorn_calls
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OBSERWATOR_STORE_WRITE_TOKEN", "short")
    started()  # without an instance a weak token is only logged
    deploy(tmp_path, monkeypatch)

    with pytest.raises(ObserwatorValidationError) as short:
        started()
    result = RUNNER.invoke(cli_main.app, ["server"])
    monkeypatch.delenv("OBSERWATOR_STORE_WRITE_TOKEN")
    shared = tmp_path / "token"
    shared.write_text("t" * 64, encoding="utf-8")
    shared.chmod(0o644)
    monkeypatch.setenv("OBSERWATOR_STORE_WRITE_TOKEN_FILE", str(shared))
    if os.name == "nt":  # no permission bits: only the length is checked
        started()
    else:
        with pytest.raises(ObserwatorValidationError) as readable:
            started()
        assert readable.value.details == {
            "option": "OBSERWATOR_STORE_WRITE_TOKEN_FILE",
            "reason": "secret_file_mode",
        }
    shared.chmod(0o600)
    started()

    assert short.value.details == {
        "option": "OBSERWATOR_STORE_WRITE_TOKEN",
        "reason": "short_secret",
    }
    assert result.exit_code == 2
    assert error_line(result)["details"] == short.value.details
    assert uvicorn_calls == []


def test_a_root_of_an_unknown_layout_stops_the_start(
    tmp_path, monkeypatch, uvicorn_calls
):
    root = tmp_path / "data"
    root.mkdir()
    (root / DATA_MARKER).write_text('{"schema": "obserwator-data/9"}', "utf-8")
    monkeypatch.setattr(settings, "root", root)

    with pytest.raises(ObserwatorStoreError) as caught:
        started()
    result = RUNNER.invoke(cli_main.app, ["server"])

    assert (caught.value.code, caught.value.details["reason"]) == (
        "store_unavailable",
        "unsupported_layout",
    )
    assert error_line(result)["code"] == "store_unavailable"
    assert uvicorn_calls == []


def test_writes_take_the_token_of_the_file_read_on_each_write(
    client, empty_raw_root, tmp_path, monkeypatch, imgw
):
    imgw.publish_pmaxtp("pmaxtp_pot_first")
    secret = tmp_path / "token"
    secret.write_text("a" * 64 + "\n", encoding="utf-8")
    monkeypatch.setattr(settings, "store_writes_enabled", True)
    monkeypatch.setattr(settings, "store_write_token_file", secret)

    first = client.post(
        path_of("pmaxtp sync"), json=POINT, headers={"X-API-Key": "a" * 64}
    )
    secret.write_text("b" * 64, encoding="utf-8")
    stale = client.post(
        path_of("pmaxtp sync"), json=POINT, headers={"X-API-Key": "a" * 64}
    )
    rotated = client.post(
        path_of("pmaxtp sync"), json=POINT, headers={"X-API-Key": "b" * 64}
    )

    assert first.status_code == 200, first.text
    assert problem(stale, 403, "forbidden")["details"] == {"reason": "invalid_api_key"}
    assert rotated.status_code == 200, rotated.text
