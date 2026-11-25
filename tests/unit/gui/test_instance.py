"""The GUI on an operator's instance (ADR-025): one filter on the server, every route."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest
from typer.testing import CliRunner

import obserwator
from obserwator.exceptions import ObserwatorValidationError
from obserwator.gui._terms import terms_page
from obserwator.instance import Instance, parse_instance
from tests.unit.gui.conftest import (
    HYDRO,
    HYDRO_CHMU,
    METEO,
    METEO_CHMU,
    PMAXTP_POINT,
    gui_config,
)

WEB = Path(obserwator.__file__).parent / "gui" / "web"
SQUARE = [[14.0, 49.5], [16.0, 49.5], [16.0, 50.6], [14.0, 50.6], [14.0, 49.5]]
"""Bohemia's west of the fixture root: four of its located ČHMÚ stations."""
INSIDE = {"0-203-0-90000000002", METEO_CHMU, HYDRO_CHMU, "0-203-1-CB900003"}
OUTSIDE = "0-203-1-900002"
"""A located ČHMÚ station of the fixture root east of the area."""
NOWHERE = "0-203-1-999999"
"""A code no catalog holds."""
SVG = b'<svg xmlns="http://www.w3.org/2000/svg" width="8" height="8"></svg>'
OPERATOR = {
    "name": "Wody Testowe sp. z o.o.",
    "email": "kontakt@example.org",
    "terms_effective": "2026-11-21",
    "processor": "Example Proxy",
    "processor_transfer": "",
    "processor_cookie": "",
    "mail_provider": "Example Mail",
    "mail_transfer": "",
}
GUI = {"obserwator": "https://wody.example/"}


def operator_terms() -> str:
    """The kit's draft for operators as an operator fills it by hand."""
    draft = (WEB / "nogat" / "nogat-terms-operator.md").read_text(encoding="utf-8")
    text = draft[draft.index("# Regulamin") :]
    return text.replace("{{operator_address}}", "ul. Testowa 1, 00-001 Gdańsk").replace(
        "{{operator_register}}", "KRS 0000000000"
    )


def instance(tmp_path: Path, **table: object) -> Instance:
    """An instance of ``table`` with its area, logo and regulamin beside it."""
    (tmp_path / "area.geojson").write_text(
        json.dumps({"type": "Polygon", "coordinates": [SQUARE]}), encoding="utf-8"
    )
    (tmp_path / "logo.svg").write_bytes(SVG)
    (tmp_path / "terms.md").write_text(operator_terms(), encoding="utf-8")
    return parse_instance(table, base=tmp_path)


def clipped(tmp_path: Path, **more: object) -> Instance:
    """ČHMÚ featured, IMGW-PIB and PIG off, the area clipped, PMAXTP off, title, logo."""
    return instance(
        tmp_path,
        title="Wody Testowe",
        logo="logo.svg",
        featured_provider="CHMU",
        start_view="featured",
        area="area.geojson",
        area_mode="clip",
        pmaxtp="off",
        providers={"IMGW": "off", "PIG": "off"},
        **more,
    )


def codes(client) -> set[str]:
    return {item["code"] for item in client.get("/api/stations").json()["stations"]}


def never(*args, **kwargs):
    raise AssertionError("a request left for a source the instance does not serve")


# --- the session ---------------------------------------------------------------------


def test_without_an_instance_the_session_names_none(client):
    session = client.get("/api/session").json()

    assert session["instance"] is None
    assert list(session["providers"]) == ["IMGW", "CHMU", "PIG"]
    assert set(session["attribution"]["origins"]) == {
        "imgw",
        "imgw_hydro",
        "pmaxtp",
        "chmu",
        "gugik",
        "cuzk",
        "pig",
    }


def test_the_session_tells_the_page_the_instance_but_no_path(make_client, tmp_path):
    client = make_client(instance=clipped(tmp_path, others_opacity=0.25))

    response = client.get("/api/session")
    session = response.json()

    assert list(session["providers"]) == ["CHMU"]
    assert set(session["attribution"]["origins"]) == {"chmu", "gugik", "cuzk"}
    chmu = session["attribution"]["origins"]["chmu"]["attribution"]
    assert session["attribution"]["order"][: len(chmu)] == chmu
    assert set(session["root"]["catalogs"]) == {"CHMU"}
    assert set(session["root"]["analyses"]) == {"CHMU"}
    assert all(key.startswith("cz.chmu.") for key in session["root"]["series"])
    found = session["instance"]
    assert found["title"] == "Wody Testowe"
    assert found["logo"] == "api/logo"
    assert found["featured"] == "CHMU"
    assert found["others_opacity"] == 0.25
    assert found["providers"] == {"CHMU": "visible"}
    assert (found["pmaxtp"], found["current"]) == (False, False)
    assert found["start"]["view"] == "featured"
    west, south, east, north = found["start"]["box"]
    assert west < 14.30 < 15.61 < east and south < 49.60 < 50.41 < north
    assert found["area"]["mode"] == "clip"
    assert found["area"]["box"] == [14.0, 49.5, 16.0, 50.6]
    assert found["area"]["bounds"][0] < 14.0 and found["area"]["outline"] == "api/area"
    assert str(tmp_path) not in response.text


def test_an_empty_start_view_falls_back_with_one_warning(make_client, tmp_path, caplog):
    nowhere = instance(
        tmp_path,
        featured_provider="IMGW",
        start_view="featured",
        area="area.geojson",
        area_mode="clip",
    )
    client = make_client(instance=nowhere)

    with caplog.at_level(logging.WARNING):
        first = client.get("/api/session").json()["instance"]["start"]
        again = client.get("/api/session").json()["instance"]["start"]

    assert first == again == {"view": "all", "box": None}
    assert caplog.text.count('start view "featured"') == 1


# --- stations and every route of a station ------------------------------------------------


def test_the_station_layer_holds_only_what_the_instance_serves(
    make_client, client, tmp_path
):
    clipping = make_client(instance=clipped(tmp_path))
    hiding = make_client(
        instance=instance(tmp_path, providers={"IMGW": "hidden", "CHMU": "off"})
    )

    assert codes(clipping) == INSIDE
    assert codes(hiding) >= {HYDRO, METEO}
    assert not any(code.startswith("0-") for code in codes(hiding))
    layer = clipping.get("/api/stations")
    assert layer.headers["etag"] != client.get("/api/stations").headers["etag"]
    assert "IMGW" not in json.dumps(layer.json()["attribution"])


@pytest.mark.parametrize(
    "path",
    [
        "/api/stations/{code}",
        "/api/analyses/{code}",
        "/api/analysis/{code}/flood_frequency.Q",
        "/api/downloads/{code}",
        "/api/handoff/{code}",
        "/api/files/analyses/{code}",
        "/api/files/analysis/{code}/flood_frequency.Q",
        "/api/prototype/stripes/{code}",
        "/api/series/cz.chmu.hydro_daily/{code}",
        "/api/files/series/cz.chmu.hydro_daily/{code}",
        "/api/station/{code}/subdaily",
    ],
)
def test_a_station_outside_answers_as_one_that_does_not_exist(
    make_client, tmp_path, path
):
    client = make_client(instance=clipped(tmp_path))

    outside = client.get(path.format(code=OUTSIDE))
    unknown = client.get(path.format(code=NOWHERE))
    off = client.get(path.format(code=HYDRO))

    assert outside.status_code == unknown.status_code == off.status_code == 404
    assert outside.json()["code"] == unknown.json()["code"] == "not_found"
    assert outside.json()["message"].replace(OUTSIDE, "?") == unknown.json()[
        "message"
    ].replace(NOWHERE, "?")


def test_an_off_provider_has_no_dataset_and_no_stations_file(make_client, tmp_path):
    client = make_client(instance=clipped(tmp_path))

    assert client.get(f"/api/series/pl.imgw.hydro_daily/{HYDRO}").status_code == 404
    assert (
        client.get(f"/api/files/series/pl.imgw.hydro_daily/{HYDRO}").status_code == 404
    )
    assert client.get("/api/downloads/stations?provider=IMGW").status_code == 404
    assert client.get("/api/files/stations?provider=IMGW").status_code == 404
    feedback = client.post(
        "/api/feedback",
        json={"text": "uwaga", "view": "stations", "station": OUTSIDE},
        headers={"Origin": "http://testserver", "Content-Type": "application/json"},
    )
    assert feedback.status_code in (400, 403)


def test_the_stations_files_hold_only_the_stations_inside(make_client, tmp_path):
    client = make_client(instance=clipped(tmp_path))

    geojson = client.get("/api/files/stations?format=geojson")
    csv = client.get("/api/files/stations?format=csv")
    listed = client.get("/api/downloads/stations").json()

    document = geojson.json()
    assert {item["id"] for item in document["features"]} == INSIDE
    assert [item["provider"] for item in document["catalogs"]] == ["CHMU"]
    assert [item["provider"] for item in listed["licences"]] == ["ČHMÚ"]
    assert listed["stations"] == len(INSIDE)
    rows = csv.text.splitlines()
    assert OUTSIDE not in csv.text and HYDRO not in csv.text
    assert sum(code in csv.text for code in INSIDE) == len(INSIDE)
    assert len(rows) == len(INSIDE) + 1


# --- live sources: no request leaves for what is off ----------------------------------------


def test_no_request_leaves_for_an_off_imgw(make_client, tmp_path, live):
    sources = dict.fromkeys(live.records, never)
    client = make_client(instance=clipped(tmp_path), sources=sources)

    assert client.get("/api/current").status_code == 404
    assert client.get(f"/api/current/{HYDRO}").status_code == 404
    assert client.get(f"/api/current/{HYDRO_CHMU}").status_code == 404
    assert client.get("/api/current").json()["details"]["reason"] == "not_served"


def test_no_request_leaves_for_pmaxtp_when_it_is_off(make_client, tmp_path):
    client = make_client(instance=clipped(tmp_path), fetch=never)
    latitude, longitude = PMAXTP_POINT
    query = f"latitude={latitude}&longitude={longitude}"

    point = client.get(f"/api/pmaxtp?{query}")
    file = client.get(f"/api/files/pmaxtp?{query}&format=csv")

    assert point.status_code == file.status_code == 404
    assert point.json()["details"]["reason"] == "pmaxtp_off"


def test_a_clipped_instance_serves_current_and_pmaxtp_of_its_area_only(
    make_client, tmp_path
):
    latitude, longitude = PMAXTP_POINT
    (tmp_path / "warsaw.geojson").write_text(
        json.dumps(
            {
                "type": "Polygon",
                "coordinates": [
                    [
                        [20.5, 51.9],
                        [21.5, 51.9],
                        [21.5, 52.5],
                        [20.5, 52.5],
                        [20.5, 51.9],
                    ]
                ],
            }
        ),
        encoding="utf-8",
    )
    around = parse_instance(
        {"area": "warsaw.geojson", "area_mode": "clip"}, base=tmp_path
    )
    client = make_client(instance=around)

    current = client.get("/api/current").json()
    points = current["hydro"] + current["meteo"]
    assert points
    assert all(20.5 <= p["lon"] <= 21.5 and 51.9 <= p["lat"] <= 52.5 for p in points)
    inside = client.get(f"/api/pmaxtp?latitude={latitude}&longitude={longitude}")
    outside = client.get("/api/pmaxtp?latitude=50.06&longitude=19.94")
    assert inside.status_code == 200
    assert outside.status_code == 404
    assert outside.json()["details"]["reason"] == "outside_area"


# --- the logo, the area and the regulamin ---------------------------------------------------


def test_the_logo_is_served_from_the_own_origin_sandboxed(make_client, tmp_path):
    client = make_client(instance=clipped(tmp_path))

    logo = client.get("/api/logo")
    again = client.get("/api/logo", headers={"If-None-Match": logo.headers["etag"]})

    assert logo.status_code == 200
    assert logo.content == SVG
    assert logo.headers["content-type"].startswith("image/svg+xml")
    assert logo.headers["content-security-policy"] == "sandbox; default-src 'none'"
    assert logo.headers["x-content-type-options"] == "nosniff"
    assert again.status_code == 304


def test_without_a_logo_or_an_area_their_routes_are_not_found(
    client, make_client, tmp_path
):
    bare = make_client(instance=instance(tmp_path))

    for one in (client, bare):
        assert one.get("/api/logo").status_code == 404
        assert one.get("/api/area").status_code == 404


def test_the_area_is_served_as_one_feature(make_client, tmp_path):
    client = make_client(instance=clipped(tmp_path))

    area = client.get("/api/area").json()

    assert area["type"] == "Feature"
    assert area["properties"] == {"mode": "clip"}
    assert area["geometry"] == {"type": "Polygon", "coordinates": [SQUARE]}


def test_the_operator_serves_its_own_regulamin_of_the_sources_served(
    make_client, tmp_path
):
    client = make_client(
        instance=clipped(tmp_path, terms="terms.md"), operator=OPERATOR, gui=GUI
    )

    session = client.get("/api/session").json()
    page = client.get("/regulamin.html").text

    assert session["terms"] == "regulamin.html"
    assert "<h1>Regulamin serwisu Obserwator</h1>" in page
    assert "ul. Testowa 1, 00-001 Gdańsk" in page
    assert "<h3>ČHMÚ</h3>" in page
    assert "IMGW-PIB: dane publiczne" not in page
    assert "opady maksymalne PMAXTP" not in page
    assert "niekomercyjn" not in page
    assert "{{" not in page and "<!--" not in page.split("</head>", 1)[1]


def test_the_kit_regulamin_of_an_instance_keeps_the_served_blocks_only(
    make_client, tmp_path
):
    client = make_client(instance=clipped(tmp_path), operator=OPERATOR, gui=GUI)

    page = client.get("/regulamin.html").text

    assert "<h3>ČHMÚ</h3>" in page
    assert "IMGW-PIB: dane publiczne" not in page
    assert "IMGW-PIB: serwis hydrologiczny" not in page
    assert "opady maksymalne PMAXTP" not in page


def test_an_operator_regulamin_the_deployment_cannot_fill_is_refused(tmp_path):
    config = gui_config(
        tmp_path / "root",
        tmp_path / "state",
        instance=clipped(tmp_path, terms="terms.md"),
    )

    with pytest.raises(ObserwatorValidationError) as caught:
        terms_page(config, WEB)

    assert caught.value.details["option"] == "instance.terms"
    (tmp_path / "hand.md").write_text(
        operator_terms().replace("KRS 0000000000", "{{operator_register}}"),
        encoding="utf-8",
    )
    filled = gui_config(
        tmp_path / "root",
        tmp_path / "state",
        operator=OPERATOR,
        gui=GUI,
        instance=clipped(tmp_path, terms="hand.md"),
    )
    with pytest.raises(ObserwatorValidationError):
        terms_page(filled, WEB)


# --- the start of the server ------------------------------------------------------------


def test_the_gui_does_not_start_from_a_wrong_section(tmp_path, monkeypatch):
    toml = tmp_path / "nogat.toml"
    toml.write_text(
        '[obserwator.instance]\nfeatured_provider = "CHMU"\n'
        '[obserwator.instance.providers]\nCHMU = "off"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("NOGAT_CONFIG", str(toml))
    monkeypatch.setenv("OBSERWATOR_GUI_BASEMAP_URL", "none")
    from obserwator.cli import main as cli_main

    result = CliRunner().invoke(
        cli_main.app,
        ["gui", "serve", "--no-browser", "--port", "0", "--root", str(tmp_path)],
    )

    assert result.exit_code == 2
    error = json.loads(result.stderr.strip().splitlines()[-1])
    assert error["code"] == "validation_error"
    assert error["details"]["option"] == "instance.featured_provider"


def test_an_instance_refuses_a_weak_admin_key(tmp_path, monkeypatch):
    from obserwator.gui._config import GuiConfig

    toml = tmp_path / "nogat.toml"
    toml.write_text("[obserwator.instance]\n", encoding="utf-8")
    monkeypatch.setenv("NOGAT_CONFIG", str(toml))
    monkeypatch.setenv("OBSERWATOR_GUI_BASEMAP_URL", "none")
    monkeypatch.delenv("OBSERWATOR_ADMIN_API_KEY_FILE", raising=False)
    monkeypatch.setenv("OBSERWATOR_ADMIN_API_KEY", "too-short")

    with pytest.raises(ObserwatorValidationError) as caught:
        GuiConfig.resolve(root=tmp_path)
    assert caught.value.details == {
        "option": "OBSERWATOR_ADMIN_API_KEY",
        "reason": "short_secret",
    }

    monkeypatch.setenv("OBSERWATOR_ADMIN_API_KEY", "k" * 32)
    assert GuiConfig.resolve(root=tmp_path).instance is not None
