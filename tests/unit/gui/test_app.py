"""The GUI's private API, page and headers (GUI plan D4 to D8, D16) on the fixture root."""

from __future__ import annotations

import copy
import csv
import io
import json
import logging
import mimetypes
import re
import shlex
import shutil
from pathlib import Path

import httpx
import pytest
import respx
from starlette.applications import Starlette
from starlette.routing import Mount
from starlette.testclient import TestClient

import obserwator
from obserwator.attribution import attribution
from obserwator.datasets import get_provider
from obserwator.exceptions import ERROR_CODES
from obserwator.gui._config import Basemap
from obserwator.gui._live import CURRENT_TTL_S, CurrentData
from obserwator.messages import message
from obserwator.messages.gui import MESSAGES as TEXTS
from obserwator.testing import _recorded_http
from tests.unit.gui.conftest import (
    ANNUAL_MAXIMA,
    HYDRO,
    HYDRO_CHMU,
    HYDROLOG_VERSION,
    METEO,
    METEO_CHMU,
    PMAXTP_POINT,
    write_program,
)

EN = {"Accept-Language": "en"}
SAME_SITE = {"Sec-Fetch-Site": "same-origin", "Content-Type": "application/json"}
SECURITY = {
    "x-frame-options": "DENY",
    "x-content-type-options": "nosniff",
    "referrer-policy": "no-referrer",
    "cross-origin-opener-policy": "same-origin",
    "cross-origin-resource-policy": "same-origin",
}
UNUSED_FEATURES = {
    "camera",
    "microphone",
    "geolocation",
    "payment",
    "usb",
    "serial",
    "browsing-topics",
    "midi",
    "display-capture",
    "fullscreen",
}


def denied(header: str) -> set[str]:
    """The features a ``Permissions-Policy`` denies to every origin (``name=()``)."""
    entries = [entry.strip().split("=", 1) for entry in header.split(",")]
    return {name for name, allow in entries if allow == "()"}


OWN_ORIGIN_ONLY = {
    "default-src": ["'self'"],
    "script-src": ["'self'"],
    "style-src": ["'self'"],
    "worker-src": ["'self'"],
    "img-src": ["'self'", "data:", "blob:"],
    "connect-src": ["'self'"],
    "font-src": ["'self'"],
    "object-src": ["'none'"],
    "base-uri": ["'none'"],
    "form-action": ["'self'"],
    "frame-ancestors": ["'none'"],
}
OPERATOR = {
    "name": "Operator testowy",
    "email": "operator@example.org",
    "terms_effective": "2026-11-13",
    "processor": "Example Processor",
    "processor_transfer": "",
    "mail_provider": "Example Mail",
}
REPORT = {"message": "The chart is empty.", "context": {"view": "stations"}}
DETAILS_RECORDINGS = (
    Path(__file__).parents[2] / "fixtures" / "store" / "hydro_details_recordings.json"
)
DETAILS = {
    item["case"]: item
    for item in json.loads(DETAILS_RECORDINGS.read_text(encoding="utf-8"))[
        "interactions"
    ]
}
"""The recorded answers of hydro.imgw.pl (``pl.imgw.hydro_details``) by case."""


def problem(answer, status, code, lang="pl"):
    """The error document of an answer, checked: status, schema, code and language."""
    assert answer.status_code == status, answer.text
    assert answer.headers["content-type"] == "application/json"
    assert answer.headers["content-language"] == lang
    body = answer.json()
    assert body["schema"] == "obserwator-error/1"
    assert body["code"] == code
    assert body["title"] == ERROR_CODES[code].title.localized(lang)
    return body


def bad_parameter(answer, option, lang="pl"):
    """The ``400`` of a refused parameter, naming it."""
    body = problem(answer, 400, "validation_error", lang)
    assert body["details"]["option"] == option
    return body


def csp(answer) -> dict[str, list[str]]:
    policy = answer.headers["content-security-policy"]
    return {part.split()[0]: part.split()[1:] for part in policy.split("; ")}


def files_of(root: Path) -> dict[str, tuple[int, int]]:
    """Every file under ``root`` with its size and modification time."""
    return {
        str(path.relative_to(root)): (path.stat().st_size, path.stat().st_mtime_ns)
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def parsed_csv(data: bytes) -> list[list[str]]:
    return list(csv.reader(io.StringIO(data.decode("utf-8"), newline="")))


@pytest.fixture(scope="module")
def details_root(fixture_raw_root, fixture_root, tmp_path_factory):
    """
    A copy of the fixture root whose IMGW-PIB catalog has the details of ``HYDRO``.

    The recorded page of Kłodzko (150160180) re-keyed to ``HYDRO`` is synced from a
    map holding ``HYDRO`` alone into a copy of the raw root, and the IMGW-PIB catalog
    is built again from it.
    """
    base = tmp_path_factory.mktemp("gui-root-details")
    raw, data = base / "raw", base / "data"
    shutil.copytree(fixture_raw_root, raw)
    shutil.copytree(fixture_root, data)
    page = copy.deepcopy(DETAILS["status_150160180"]["json"])
    page["id"] = HYDRO
    page["status"]["name"] = HYDRO
    recorded = DETAILS["map"]
    station = {**recorded["json"]["stations"][0], "id": HYDRO}
    with respx.mock(assert_all_mocked=True) as router:
        router.get(recorded["url"]).mock(
            return_value=httpx.Response(
                200, json={**recorded["json"], "stations": [station]}
            )
        )
        router.get(DETAILS["status_unknown"]["url"].replace("999999999", HYDRO)).mock(
            return_value=httpx.Response(200, json=page)
        )
        synced = obserwator.sync_store(raw, datasets=["pl.imgw.hydro_details"])
    assert [item.status for item in synced.items] == ["new"]
    obserwator.build_catalog(data, raw_root=raw)
    return data


# --- the session and the texts ----------------------------------------------------------


def test_the_session_names_the_versions_the_root_and_the_sources(client):
    session = client.get("/api/session").json()

    assert session["schema"] == "obserwator-gui-session/1"
    assert session["version"] == {
        "obserwator": obserwator.__version__,
        "hydrolog": None,
    }
    root = session["root"]
    assert set(root["catalogs"]) == {"IMGW", "CHMU"}
    assert set(root["series"]) == {
        "pl.imgw.hydro_daily",
        "pl.imgw.meteo_precip_daily",
        "cz.chmu.hydro_daily",
        "cz.chmu.meteo_daily",
    }
    hydro = root["series"]["pl.imgw.hydro_daily"]
    assert hydro["year_type"] == "hydrological"
    assert hydro["stations"] == 2
    assert len(hydro["sha256"]) == 64
    assert root["error"] is None
    # The fixture root stores no analyses
    assert root["analyses"] == {"IMGW": None, "CHMU": None}
    assert set(session["providers"]) == {"IMGW", "CHMU"}
    assert session["providers"]["CHMU"]["attribution"] == list(
        attribution("chmu").attribution
    )
    # national services: their countries, and no notice of another source (P8, P11)
    assert {
        provider: (found["country"], found["source_class"], found["source_notice"])
        for provider, found in session["providers"].items()
    } == {"IMGW": ("PL", "nmhs", None), "CHMU": ("CZ", "nmhs", None)}
    origins = session["attribution"]["origins"]
    assert set(origins) == {"imgw", "imgw_hydro", "pmaxtp", "chmu", "gugik", "cuzk"}
    assert session["basemap"] is None
    assert session["terms"] is None
    assert session["operator_email"] is None
    assert session["compute"]["available"] is False


def test_the_session_gives_the_notice_of_another_source_in_the_pages_language(
    client, monkeypatch
):
    # ČHMÚ's adapter made a source of the class "other" with P8's notice of the files'
    # providers: the page shows the notice in its language, beside the class
    adapter = get_provider("CHMU").adapter
    notice = message("datasets.source_notice_other")
    monkeypatch.setattr(adapter, "source_class", "other")
    monkeypatch.setattr(adapter, "source_notice", notice)

    polish = client.get("/api/session").json()["providers"]
    english = client.get("/api/session", headers=EN).json()["providers"]

    assert polish["CHMU"]["source_class"] == english["CHMU"]["source_class"] == "other"
    assert polish["CHMU"]["source_notice"] == notice.localized("pl")
    assert english["CHMU"]["source_notice"] == notice.localized("en")
    assert polish["CHMU"]["source_notice"] != english["CHMU"]["source_notice"]
    assert polish["IMGW"]["source_notice"] is english["IMGW"]["source_notice"] is None


def test_the_session_names_the_stored_analyses_of_each_provider(
    make_client, stored_root
):
    analyses = make_client(stored_root).get("/api/session").json()["root"]["analyses"]

    for provider, folder, station in (
        ("IMGW", "pl.imgw", HYDRO),
        ("CHMU", "cz.chmu", HYDRO_CHMU),
    ):
        (version,) = (stored_root / "analyses" / "versions" / folder).iterdir()
        stored = obserwator.read_analysis(
            root=stored_root, station=station, analysis="characteristic.Q"
        )
        assert analyses[provider]["version"] == version.name
        assert stored.analyses_version == version.name
        assert analyses[provider]["hydrolog"] == stored.hydrolog["version"]
        assert len(analyses[provider]["sha256"]) == 64


def test_a_public_deployment_serves_its_regulamin(make_client):
    private = make_client()
    public = make_client(
        operator=OPERATOR, gui={"obserwator": "https://obserwator.example/"}
    )

    assert private.get("/regulamin.html").status_code == 404
    session = public.get("/api/session").json()
    page = public.get("/regulamin.html")

    assert session["terms"] == "regulamin.html"
    assert session["operator_email"] == "operator@example.org"
    assert session["gui"] == {"obserwator": "https://obserwator.example/"}
    assert page.status_code == 200
    assert page.headers["content-type"] == "text/html; charset=utf-8"
    assert "Operator testowy" in page.text
    assert "{{" not in page.text


def test_the_texts_are_the_gui_area_of_the_catalog_in_either_language(client):
    polish = client.get("/api/texts?lang=pl")
    english = client.get("/api/texts", params={"lang": "en"}).json()
    default = client.get("/api/texts").json()

    assert polish.json() == {
        "lang": "pl",
        "texts": {key: text.pl for key, text in TEXTS.items()},
    }
    assert english == {
        "lang": "en",
        "texts": {key: text.en for key, text in TEXTS.items()},
    }
    assert default == polish.json()
    again = client.get(
        "/api/texts?lang=pl", headers={"If-None-Match": polish.headers["etag"]}
    )
    assert again.status_code == 304
    bad_parameter(client.get("/api/texts?lang=de", headers=EN), "lang", "en")


# --- stations and series ------------------------------------------------------------------


def test_the_station_layer_holds_every_station_of_both_catalogs(client):
    answer = client.get("/api/stations")
    layer = answer.json()

    assert layer["count"] == len(layer["stations"]) == 13
    by_code = {station["code"]: station for station in layer["stations"]}
    assert by_code[HYDRO] == {
        "code": HYDRO,
        "name": "Raba Górna",
        "river": "Raba",
        "provider": "IMGW",
        "kind": "hydro",
        "meteo_kind": None,
        "active": True,
        "location_source": "pl.imgw.hydro_now",
        "lon": 20.1,
        "lat": 49.7,
        "datasets": ["pl.imgw.hydro_daily"],
        "first": "2023",
        "last": "2024",
    }
    assert by_code[METEO_CHMU]["provider"] == "CHMU"
    assert by_code[METEO]["meteo_kind"] == "precipitation"
    # The catalogs' lines: the providers' and those of the packaged borders (ADR-018)
    lines = attribution("imgw", "chmu", "gugik", "cuzk")
    assert layer["attribution"] == list(lines.attribution)
    assert layer["terms_notice"] == list(lines.terms_notice)
    again = client.get(
        "/api/stations", headers={"If-None-Match": answer.headers["etag"]}
    )
    assert again.status_code == 304
    assert again.headers["etag"] == answer.headers["etag"]


def test_the_station_layer_is_built_once_and_a_304_builds_nothing(client, monkeypatch):
    from obserwator.gui import _app

    built = []
    origins = _app._station_origins

    def counted(*args, **kwargs):
        built.append(args[0])
        return origins(*args, **kwargs)

    monkeypatch.setattr(_app, "_station_origins", counted)
    packed = client.get("/api/stations", headers={"Accept-Encoding": "gzip"})
    after_first = len(built)
    plain = client.get("/api/stations", headers={"Accept-Encoding": "identity"})
    unchanged = client.get(
        "/api/stations", headers={"If-None-Match": packed.headers["etag"]}
    )

    assert after_first == 13
    assert len(built) == 13
    assert packed.headers["content-encoding"] == "gzip"
    assert "content-encoding" not in plain.headers
    assert packed.headers["vary"] == plain.headers["vary"] == "Accept-Encoding"
    assert packed.headers["cache-control"] == "no-cache"
    assert packed.json() == plain.json()
    assert packed.headers["etag"] == plain.headers["etag"]
    assert unchanged.status_code == 304


def test_a_station_answers_its_properties_series_and_lines(client):
    hydro = client.get(f"/api/stations/{HYDRO}").json()
    chmu = client.get(f"/api/stations/{HYDRO_CHMU}").json()
    empty = client.get("/api/stations/149190312").json()

    assert (hydro["code"], hydro["provider"], hydro["lon"], hydro["lat"]) == (
        HYDRO,
        "IMGW",
        20.1,
        49.7,
    )
    assert hydro["properties"]["river"] == "Raba"
    (series,) = hydro["datasets"]
    assert series["dataset"] == "pl.imgw.hydro_daily"
    assert series["rows"] == 91
    assert series["variables"]["Q"] == {
        "unit": "m3/s",
        "period": None,
        "first": "2024-02-29",
        "last": "2024-02-29",
        "with_value": 1,
        "accumulated": 0,
        "gaps": 0,
    }
    assert hydro["attribution"] == list(attribution("imgw", "gugik").attribution)
    assert chmu["properties"]["thresholds"]["Q"]["q50"] == 96
    assert chmu["attribution_parts"]["series"]["attribution"] == list(
        attribution("chmu").attribution
    )
    assert "terms_notice" not in chmu["attribution_parts"]["series"]
    assert empty["datasets"] == []
    assert empty["attribution_parts"]["series"] is None


def test_a_station_with_details_names_hydro_imgw_pl_and_carries_them(
    make_client, client, details_root
):
    detailed = make_client(details_root).get(f"/api/stations/{HYDRO}").json()
    plain = client.get(f"/api/stations/{HYDRO}").json()
    lines = attribution("imgw", "gugik", "imgw_hydro")

    assert detailed["attribution"] == list(lines.attribution)
    assert detailed["terms_notice"] == list(lines.terms_notice)
    assert detailed["attribution_parts"]["catalog"] == lines.fields()
    assert {
        key: detailed["properties"][key]
        for key in (
            "established_year",
            "gauge_zero_m",
            "gauge_zero_datum",
            "river_km",
            "catchment_area_km2",
            "province",
            "district",
            "warning_level_cm",
            "alarm_level_cm",
            "absolute_min_level_cm",
            "absolute_min_level_dates",
            "absolute_max_level_cm",
            "absolute_max_level_dates",
            "details_source",
        )
    } == {
        "established_year": 1884,
        "gauge_zero_m": 281.617,
        "gauge_zero_datum": "EVRF2007",
        "river_km": 130.04,
        "catchment_area_km2": 1082.27,
        "province": "dolnośląskie",
        "district": "kłodzki",
        "warning_level_cm": 160,
        "alarm_level_cm": 240,
        "absolute_min_level_cm": 28,
        "absolute_min_level_dates": "1950-08-31",
        "absolute_max_level_cm": 890,
        "absolute_max_level_dates": "1997-07-08",
        "details_source": "hydro_details",
    }
    assert plain["properties"]["details_source"] is None
    assert (
        plain["attribution_parts"]["catalog"] == attribution("imgw", "gugik").fields()
    )


def test_the_lines_of_stations_files_name_hydro_imgw_pl_for_stations_with_details(
    make_client, client, details_root
):
    detailed = make_client(details_root)
    hydro = {"provider": "IMGW", "kind": "hydro"}
    meteo = {"provider": "IMGW", "kind": "meteo"}
    with_details = detailed.get("/api/downloads/stations", params=hydro).json()
    without = detailed.get("/api/downloads/stations", params=meteo).json()
    before = client.get("/api/downloads/stations", params=hydro).json()

    assert "hydro.imgw.pl" in " ".join(with_details["terms_notice"])
    assert with_details["attribution"] == list(
        attribution("imgw", "gugik", "imgw_hydro").attribution
    )
    assert without["attribution"] == list(attribution("imgw", "gugik").attribution)
    assert before["attribution"] == list(attribution("imgw", "gugik").attribution)


def test_an_unknown_station_is_404_and_a_malformed_code_400(client):
    missing = client.get("/api/stations/999999999", headers=EN)
    malformed = client.get("/api/stations/abc")

    body = problem(missing, 404, "not_found", "en")
    assert body["message"] == message("gui.errors.no_station", station="999999999")
    bad_parameter(malformed, "station")


def test_a_series_answers_its_days_values_and_flags(client):
    whole = client.get(f"/api/series/pl.imgw.meteo_precip_daily/{METEO}").json()
    part = client.get(
        f"/api/series/pl.imgw.meteo_precip_daily/{METEO}",
        params={"variables": "P", "start": "2001-01-02", "end": "2001-01-03"},
    ).json()

    assert whole["dates"][0] == "2001-01-01"
    assert len(whole["dates"]) == len(whole["values"]["snow_cover"]) == 31
    assert set(whole["values"]) == {"P", "snow_cover", "fresh_snow"}
    assert part["dates"] == ["2001-01-02", "2001-01-03"]
    assert part["hydro_year"] == [2001, 2001]
    assert part["units"] == {"P": "mm"}
    assert part["values"] == {"P": [9.2, 0.0]}
    assert part["flags"] == {"P": [[0, "accumulated"], [1, "no_phenomenon"]]}
    assert part["year_type"] == "calendar"
    assert part["attribution"] == list(attribution("imgw").attribution)


def test_the_etag_of_a_series_follows_its_query(client):
    path = f"/api/series/cz.chmu.hydro_daily/{HYDRO_CHMU}"
    first = client.get(path, params={"variables": "Q"})
    tag = {"If-None-Match": first.headers["etag"]}

    assert client.get(path, params={"variables": "Q"}, headers=tag).status_code == 304
    other = client.get(path, params={"variables": "H"}, headers=tag)
    assert other.status_code == 200
    assert other.headers["etag"] != first.headers["etag"]


@pytest.mark.parametrize(
    ("query", "option"),
    [
        ({"variables": "Q,X"}, "variables"),
        ({"start": "2024-02-30"}, "start"),
        ({"end": "29.02.2024"}, "end"),
        ({"start": "2024-02-02", "end": "2024-02-01"}, "start"),
        ({"year_type": "calendar"}, "year_type"),
        ([("start", "2024-01-01"), ("start", "2024-01-02")], "start"),
    ],
)
def test_wrong_series_parameters_are_refused_naming_the_option(client, query, option):
    answer = client.get(f"/api/series/pl.imgw.hydro_daily/{HYDRO}", params=query)

    bad_parameter(answer, option)


def test_an_unknown_dataset_or_a_series_the_station_lacks_is_404(client):
    unknown = client.get(f"/api/series/xx.example.daily/{HYDRO}", headers=EN)
    lacking = client.get(f"/api/series/pl.imgw.meteo_precip_daily/{HYDRO}")
    unknown_file = client.get(f"/api/files/series/xx.example.daily/{HYDRO}")

    body = problem(unknown, 404, "not_found", "en")
    assert body["message"] == message(
        "gui.errors.no_dataset", dataset="xx.example.daily"
    )
    body = problem(lacking, 404, "not_found")
    assert body["message"] == message(
        "gui.errors.no_series",
        lang="pl",
        station=HYDRO,
        dataset="pl.imgw.meteo_precip_daily",
    )
    problem(unknown_file, 404, "not_found")


# --- analyses ------------------------------------------------------------------------------


def test_without_stored_results_or_hydrolog_nothing_is_listed_or_computed(client):
    listed = client.get(f"/api/analyses/{HYDRO}").json()
    asked = client.get(f"/api/analysis/{HYDRO}/characteristic.Q", headers=EN)
    files = client.get(f"/api/downloads/{HYDRO}").json()
    export = client.get(f"/api/files/analyses/{HYDRO}?format=csv", headers=EN)

    assert listed == {"station": HYDRO, "analyses": [], "compute": False}
    problem(asked, 503, "missing_dependency", "en")
    assert files["analyses"] is None
    problem(export, 404, "not_found", "en")


def test_stored_results_are_listed_and_read_without_hydrolog(make_client, stored_root):
    client = make_client(stored_root)

    listed = client.get(f"/api/analyses/{HYDRO}").json()
    first = client.get(f"/api/analysis/{HYDRO}/characteristic.Q")
    again = client.get(
        f"/api/analysis/{HYDRO}/characteristic.Q",
        headers={"If-None-Match": first.headers["etag"]},
    )

    summaries = obserwator.list_analyses(root=stored_root, station=HYDRO)
    assert listed["compute"] is False
    assert [entry["analysis"] for entry in listed["analyses"]] == [
        summary.analysis for summary in summaries
    ]
    by_id = {entry["analysis"]: entry for entry in listed["analyses"]}
    assert by_id["characteristic.Q"]["schema"] == "obserwator-analysis-summary/1"
    assert by_id["characteristic.Q"]["stored"] is True
    assert by_id["characteristic.Q"]["overridable"]["first_year"] == {
        "type": "integer",
        "minimum": 1,
    }
    stored = obserwator.read_analysis(
        root=stored_root, station=HYDRO, analysis="characteristic.Q"
    )
    document = first.json()
    assert document["source"] == "stored"
    assert document["analyses_version"] == stored.analyses_version
    assert stored.envelope is not None
    assert document["envelope"]["result"] == stored.envelope["result"]
    # Hydrolog's envelope names the files it read in a scratch directory: names only
    assert (
        document["envelope"]["inputs"]["input_file"]
        == Path(stored.envelope["inputs"]["input_file"]).name
    )
    assert again.status_code == 304


@pytest.mark.parametrize("fmt", ["json", "csv"])
def test_the_stored_results_download_as_analyses_export_makes_them(
    make_client, stored_root, fmt
):
    client = make_client(stored_root)

    files = client.get(f"/api/downloads/{HYDRO}").json()["analyses"]
    whole = client.get(f"/api/files/analyses/{HYDRO}?format={fmt}")
    one = client.get(
        f"/api/files/analyses/{HYDRO}",
        params={"format": fmt, "analysis": "characteristic.Q"},
    )
    unknown = client.get(
        f"/api/files/analyses/{HYDRO}",
        params={"format": fmt, "analysis": "regime.Q.nothing"},
    )

    def exported(**options):
        return "".join(
            obserwator.export_analyses(
                root=stored_root, station=HYDRO, format=fmt, **options
            )
        ).encode("utf-8")

    assert files["formats"][fmt] == {
        "file": f"obserwator_analyses_{HYDRO}.{fmt}",
        "url": f"api/files/analyses/{HYDRO}?format={fmt}",
        "command": (
            f"obserwator analyses export --station {HYDRO} --format {fmt} "
            f"--output obserwator_analyses_{HYDRO}.{fmt}"
        ),
    }
    (version,) = (stored_root / "analyses" / "versions" / "pl.imgw").iterdir()
    assert files["version"] == version.name
    assert whole.content == exported()
    assert whole.headers["content-disposition"].startswith(
        f'attachment; filename="obserwator_analyses_{HYDRO}.{fmt}"'
    )
    assert one.content == exported(analyses=["characteristic.Q"])
    # The page offers one analysis's file under the name the server sends it with.
    assert files["each"]["characteristic.Q"][fmt] == (
        f"obserwator_analyses_{HYDRO}_characteristic.Q.{fmt}"
    )
    assert one.headers["content-disposition"].startswith(
        f'attachment; filename="{files["each"]["characteristic.Q"][fmt]}"'
    )
    problem(unknown, 404, "not_found")


def test_an_analysis_is_computed_by_hydrolog_once_and_served_again(
    make_client, hydrolog
):
    client = make_client(hydrolog=hydrolog)
    path = f"/api/analysis/{HYDRO}/flood_frequency.Q"

    first = client.get(path)
    again = client.get(path, headers={"If-None-Match": first.headers["etag"]})
    file = client.get(f"/api/files/analysis/{HYDRO}/flood_frequency.Q")
    session = client.get("/api/session").json()

    document = first.json()
    assert document["schema"] == "obserwator-analysis/1"
    assert (document["station"], document["analysis"]) == (HYDRO, "flood_frequency.Q")
    assert document["command"] == "stats flood-frequency"
    assert document["status"] == "ok"
    assert document["source"] == "computed"
    assert document["hydrolog"] == {"version": HYDROLOG_VERSION}
    assert document["envelope"]["result"]["annual_maxima"] == ANNUAL_MAXIMA[1]
    assert document["inputs"][0]["dataset"] == "pl.imgw.hydro_daily"
    assert again.status_code == 304
    assert file.headers["content-disposition"].startswith(
        f'attachment; filename="obserwator_analyses_{HYDRO}_flood_frequency.Q.json"'
    )
    assert json.loads(file.content) == document
    assert session["compute"]["available"] is True
    assert session["version"]["hydrolog"] == HYDROLOG_VERSION


@pytest.mark.parametrize(
    ("path", "status", "code"),
    [
        (f"/api/analysis/{HYDRO}/no_such.id", 404, "not_found"),
        (f"/api/analysis/{METEO}/characteristic.Q", 404, "not_found"),
        (
            f"/api/analysis/{HYDRO}/characteristic.Q?no_option=1",
            400,
            "validation_error",
        ),
        (
            f"/api/analysis/{HYDRO}/characteristic.Q?first_year=2000&first_year=2001",
            400,
            "validation_error",
        ),
        (f"/api/files/analysis/{HYDRO}/no_such.id", 404, "not_found"),
    ],
)
def test_an_analysis_outside_the_registry_or_the_station_is_refused(
    make_client, hydrolog, path, status, code
):
    client = make_client(hydrolog=hydrolog)

    problem(client.get(path), status, code)


# --- current data and PMAXTP -----------------------------------------------------------------


def test_the_current_data_of_imgw_are_points_of_the_map(client):
    current = client.get("/api/current").json()

    assert current["source"] == "IMGW"
    for name in ("states", "hydro", "meteo"):
        assert current["snapshots"][name]["fetched_at"].endswith("Z")
        assert current["snapshots"][name]["error"] is None
    hydro = {point["code"]: point for point in current["hydro"]}
    assert hydro[HYDRO]["state"] == "medium"
    assert (hydro[HYDRO]["lat"], hydro[HYDRO]["lon"]) == (49.7, 20.1)
    assert hydro["149190311"]["state"] == "low"
    assert "149190312" not in hydro  # no location in either answer
    assert [point["code"] for point in current["meteo"]] == [METEO]
    assert current["attribution"] == list(attribution("imgw_hydro").attribution)


def test_a_failed_source_keeps_the_others_and_names_its_error(make_client, live):
    client = make_client(sources=live.sources(hydro=live.outage))

    current = client.get("/api/current", headers=EN).json()

    assert current["snapshots"]["hydro"]["fetched_at"] is None
    assert current["snapshots"]["hydro"]["error"] == str(live.outage)
    assert {point["code"] for point in current["hydro"]} == {HYDRO, "149190311"}


def test_no_current_data_at_all_is_an_error(make_client, live):
    failing = dict.fromkeys(("states", "hydro", "meteo", "synop"), live.outage)
    client = make_client(sources=live.sources(**failing))

    problem(client.get("/api/current"), 502, "source_unavailable")
    problem(client.get(f"/api/current/{HYDRO}"), 502, "source_unavailable")


def test_the_current_values_of_one_station(client):
    hydro = client.get(f"/api/current/{HYDRO}").json()
    meteo = client.get(f"/api/current/{METEO}").json()
    chmu = client.get(f"/api/current/{HYDRO_CHMU}", headers=EN)

    assert (hydro["station"], hydro["kind"], hydro["state"]) == (
        HYDRO,
        "hydro",
        "medium",
    )
    assert hydro["record"]["station_name"] == "Raba Górna"
    assert set(hydro["snapshots"]) == {"hydro", "states"}
    assert meteo["record"]["station_name"] == "Warszawa"
    assert "synop" not in meteo  # the code is no synoptic station's
    body = problem(chmu, 404, "not_found", "en")
    assert body["message"] == message("gui.errors.no_current_provider", provider="ČHMÚ")


@pytest.mark.parametrize("path", ["/api/current", f"/api/current/{HYDRO}"])
def test_current_data_answer_304_until_a_snapshot_changes(make_client, live, path):
    now = [1000.0]
    client = make_client()
    client.app.state.gui.current = CurrentData(
        live.sources(), clock=lambda: now[0], start=lambda run: run()
    )
    first = client.get(path)
    etag = first.headers["etag"]

    same = client.get(path, headers={"If-None-Match": etag})
    other_lang = client.get(path, headers={"If-None-Match": etag, **EN})
    now[0] += CURRENT_TTL_S  # a refresh: the same records, a new snapshot
    refreshed = client.get(path, headers={"If-None-Match": etag})

    assert first.status_code == 200
    assert first.headers["cache-control"] == "no-cache"
    assert (same.status_code, same.content) == (304, b"")
    assert same.headers["etag"] == etag
    assert other_lang.status_code == 200
    assert other_lang.headers["etag"] != etag
    assert refreshed.status_code == 200
    assert refreshed.headers["etag"] != etag
    assert refreshed.json()["source"] == "IMGW"


def test_pmaxtp_of_a_point_with_its_tables_its_source_and_command(client):
    latitude, longitude = PMAXTP_POINT
    answer = client.get(
        "/api/pmaxtp", params={"latitude": latitude, "longitude": longitude}
    ).json()
    amp = client.get(
        "/api/pmaxtp",
        params={"latitude": latitude, "longitude": longitude, "method": "AMP"},
    ).json()

    assert (answer["method"], answer["latitude"], answer["longitude"]) == (
        "POT",
        latitude,
        longitude,
    )
    assert answer["durations"] == ["15"]
    assert answer["probabilities"] == ["50"]
    assert answer["data"]["ks"] == {"15": {"50": 13.34}}
    assert answer["unit"] == "mm"
    assert answer["source_url"] == obserwator.build_pmaxtp_url(
        latitude, longitude, method="POT"
    )
    assert obserwator.parse_command(answer["command"]).command == "pmaxtp fetch"
    assert answer["attribution"] == list(attribution("pmaxtp").attribution)
    assert amp["data"]["ks"] == {"15": {"50": 12.8}}


def test_pmaxtp_of_a_point_is_fetched_once_per_method(make_client, live):
    calls = []

    def fetch(latitude, longitude, *, method="POT"):
        calls.append((latitude, longitude, method))
        return live.fetch(latitude, longitude, method=method)

    client = make_client(fetch=fetch)
    for latitude in ("52.23", "52.23001", "52.2300"):
        client.get("/api/pmaxtp", params={"latitude": latitude, "longitude": "21.01"})
    client.get("/api/files/pmaxtp", params={"latitude": "52.23", "longitude": "21.01"})
    client.get(
        "/api/pmaxtp",
        params={"latitude": "52.23", "longitude": "21.01", "method": "AMP"},
    )

    assert calls == [(52.23, 21.01, "POT"), (52.23, 21.01, "AMP")]


@pytest.mark.parametrize(
    ("query", "option"),
    [
        ({"latitude": "52.23"}, "longitude"),
        ({"longitude": "21.01"}, "latitude"),
        ({"latitude": "91", "longitude": "21.01"}, "latitude"),
        ({"latitude": "52,23", "longitude": "21.01"}, "latitude"),
        ({"latitude": "nan", "longitude": "21.01"}, "latitude"),
        ({"latitude": "52.23", "longitude": "21.01", "method": "GEV"}, "method"),
        ({"latitude": "52.23", "longitude": "21.01", "zoom": "3"}, "zoom"),
    ],
)
def test_wrong_pmaxtp_parameters_are_refused(client, query, option):
    bad_parameter(client.get("/api/pmaxtp", params=query), option)


def test_a_point_outside_the_pmaxtp_grid_is_refused_with_imgws_reason(make_client):
    def fetch(latitude, longitude, *, method="POT"):
        with _recorded_http(["pmaxtp_outside_grid"], recordings=("recordings.json",)):
            return obserwator.fetch_pmaxtp(latitude, longitude, method=method)

    client = make_client(fetch=fetch, headers=EN)

    answer = client.get("/api/pmaxtp", params={"latitude": "54.9", "longitude": "23.9"})

    body = problem(answer, 400, "validation_error", "en")
    assert "undefined: lat 54.9000, lon: 23.9000" in body["message"]


def test_pmaxtp_files_hold_the_tables_and_pmaxtp_lines(client):
    query = {"latitude": "52.23", "longitude": "21.01"}
    table = client.get("/api/files/pmaxtp", params=query)
    document = client.get("/api/files/pmaxtp", params={**query, "format": "json"})

    assert table.headers["content-type"] == "text/csv; charset=utf-8"
    assert (
        'filename="obserwator_pmaxtp_POT_52.2300_21.0100.csv"'
        in (table.headers["content-disposition"])
    )
    rows = parsed_csv(table.content)
    assert rows[0] == [
        "method",
        "latitude",
        "longitude",
        "table",
        "duration [min]",
        "p=50% [mm]",
        "attribution",
        "terms_notice",
    ]
    assert [row[:6] for row in rows[1:]] == [
        ["POT", "52.2300", "21.0100", "ks", "15", "13.34"],
        ["POT", "52.2300", "21.0100", "sg", "15", "14.1"],
        ["POT", "52.2300", "21.0100", "rb", "15", "0.3"],
    ]
    lines = attribution("pmaxtp")
    assert [row[6] for row in rows[1:]] == list(lines.attribution)
    assert [row[7] for row in rows[1:]] == [*lines.terms_notice, "", ""]
    exported = json.loads(document.content)
    assert exported["schema"] == "obserwator-pmaxtp-export/1"
    assert exported["data"]["rb"] == {"15": {"50": 0.3}}
    assert exported["terms_notice"] == list(lines.terms_notice)
    bad_parameter(
        client.get("/api/files/pmaxtp", params={**query, "format": "xlsx"}), "format"
    )


# --- files ----------------------------------------------------------------------------------


def test_the_files_of_a_station_come_with_the_readers_command_line(
    client, read_only_root, tmp_path
):
    downloads = client.get(f"/api/downloads/{HYDRO}").json()

    (series,) = downloads["series"]
    assert series["dataset"] == "pl.imgw.hydro_daily"
    assert series["licence"]["provider"] == "IMGW-PIB"
    assert series["attribution"] == list(attribution("imgw").attribution)
    assert set(series["formats"]) == {"csv", "json", "parquet"}
    for fmt, entry in series["formats"].items():
        assert entry["file"] == f"obserwator_series_pl.imgw.hydro_daily_{HYDRO}.{fmt}"
        line = shlex.split(entry["command"])
        assert "--root" not in line
        assert line[line.index("--output") + 1] == entry["file"]
        call = obserwator.parse_command(entry["command"])
        target = tmp_path / entry["file"]
        obserwator.run_command(
            call.command,
            options={**call.options, "root": read_only_root, "output": target},
        )
        download = client.get(entry["url"])
        assert download.status_code == 200
        assert download.content == target.read_bytes()


def test_series_files_are_made_by_export_series_on_the_read_only_root(client):
    path = f"/api/files/series/cz.chmu.hydro_daily/{HYDRO_CHMU}"
    table = client.get(path)
    document = client.get(path, params={"format": "json"})
    parquet = client.get(path, params={"format": "parquet"})

    assert table.headers["content-type"] == "text/csv; charset=utf-8"
    assert table.headers["content-disposition"].startswith(
        f'attachment; filename="obserwator_series_cz.chmu.hydro_daily_{HYDRO_CHMU}.csv"'
    )
    assert parsed_csv(table.content)[1][0] == "2023-01-01"
    assert document.headers["content-type"] == "application/json"
    assert document.json()["schema"] == "obserwator-series-export/1"
    assert parquet.headers["content-type"] == "application/vnd.apache.parquet"
    assert parquet.content[:4] == b"PAR1"
    again = client.get(path, headers={"If-None-Match": table.headers["etag"]})
    assert again.status_code == 304
    bad_parameter(client.get(path, params={"format": "xlsx"}), "format")


def test_the_stations_files_come_from_export_stations(client, read_only_root):
    listed = client.get("/api/downloads/stations").json()
    chosen = client.get(
        "/api/downloads/stations", params={"provider": "CHMU", "kind": "meteo"}
    ).json()
    whole = client.get("/api/files/stations")
    table = client.get(chosen["formats"]["csv"]["url"])

    assert listed["stations"] == 13
    assert [item["provider"] for item in listed["licences"]] == ["IMGW-PIB", "ČHMÚ"]
    assert listed["formats"]["geojson"] == {
        "file": "obserwator_stations.geojson",
        "url": "api/files/stations?format=geojson",
        "command": "obserwator stations export --output obserwator_stations.geojson",
    }
    assert chosen["stations"] == 3
    assert chosen["formats"]["csv"]["command"] == (
        "obserwator stations export --provider CHMU --kind meteo --format csv "
        "--output obserwator_stations_chmu_meteo.csv"
    )
    assert whole.headers["content-type"] == "application/geo+json"
    assert whole.content == "".join(obserwator.export_stations(read_only_root)).encode()
    assert table.headers["content-disposition"].startswith(
        'attachment; filename="obserwator_stations_chmu_meteo.csv"'
    )
    assert (
        table.content
        == "".join(
            obserwator.export_stations(
                read_only_root, provider="CHMU", kind="meteo", format="csv"
            )
        ).encode()
    )
    again = client.get(
        "/api/files/stations", headers={"If-None-Match": whole.headers["etag"]}
    )
    assert again.status_code == 304


@pytest.mark.parametrize(
    ("path", "option"),
    [
        ("/api/files/stations?provider=XX", "provider"),
        ("/api/downloads/stations?kind=climate", "kind"),
        ("/api/files/stations?format=xml", "format"),
        ("/api/downloads/stations?format=csv", "format"),
    ],
)
def test_wrong_stations_parameters_are_refused(client, path, option):
    bad_parameter(client.get(path), option)


def test_stations_of_a_provider_without_a_catalog_are_404(make_client, imgw_root):
    client = make_client(imgw_root, headers=EN)

    for path in (
        "/api/downloads/stations?provider=CHMU",
        "/api/files/stations?provider=CHMU&format=csv",
    ):
        body = problem(client.get(path), 404, "not_found", "en")
        assert body["message"] == message("gui.errors.no_stations")
    assert client.get("/api/downloads/stations").json()["stations"] == 6


# --- the hand-off to Hydrolog --------------------------------------------------------------


def test_the_handoff_of_daily_values_covers_the_years_chosen(client):
    series = client.get(f"/api/series/cz.chmu.hydro_daily/{HYDRO_CHMU}").json()
    answer = client.get(
        f"/api/handoff/{HYDRO_CHMU}",
        params={"variable": "Q", "first_year": "2024", "last_year": "2024"},
        headers=EN,
    ).json()

    rows = [
        (day, value)
        for day, year, value in zip(
            series["dates"], series["hydro_year"], series["values"]["Q"], strict=True
        )
        if year == 2024
    ]
    while rows[-1][1] is None:
        rows.pop()
    while rows[0][1] is None:
        rows.pop(0)
    payload = answer["payload"]
    assert answer["schema"] == "nogat-handoff/1"
    assert payload["schema"] == "hydrolog-series/1"
    assert (payload["variable"], payload["unit"], payload["step"]) == (
        "Q",
        "m3/s",
        "day",
    )
    assert list(zip(payload["dates"], payload["values"], strict=True)) == rows
    assert answer["subject"] == message(
        "gui.handoff.subject_daily",
        lang="en",
        station="Špindlerův Mlýn (Labe)",
        variable="Q",
    )
    assert answer["producer"]["page"] == f"http://testserver/?station={HYDRO_CHMU}"
    assert answer["provenance"]["series"]["dataset"] == "cz.chmu.hydro_daily"
    assert answer["attribution"] == list(attribution("chmu").attribution)
    assert "terms_notice" not in answer


@pytest.mark.parametrize(
    ("query", "status", "code"),
    [
        ({"first_year": "2030"}, 404, "not_found"),
        ({"first_year": "2024", "last_year": "2023"}, 400, "validation_error"),
        ({"variable": "T"}, 400, "validation_error"),
        ({"analysis": "flood_frequency.Q"}, 400, "validation_error"),
        ({"resolution": "monthly"}, 400, "validation_error"),
    ],
)
def test_a_handoff_without_values_or_with_wrong_parameters_is_refused(
    client, query, status, code
):
    problem(client.get(f"/api/handoff/{HYDRO_CHMU}", params=query), status, code)


def test_a_meteorological_station_has_no_hydrological_handoff(client):
    body = problem(client.get(f"/api/handoff/{METEO}"), 404, "not_found")

    assert body["message"] == message(
        "gui.errors.no_series",
        lang="pl",
        station=METEO,
        dataset="pl.imgw.hydro_daily, cz.chmu.hydro_daily",
    )


def test_the_handoff_of_annual_maxima_takes_them_from_hydrologs_result(
    make_client, hydrolog
):
    client = make_client(hydrolog=hydrolog)

    answer = client.get(f"/api/handoff/{HYDRO}", params={"resolution": "annual"}).json()

    payload = answer["payload"]
    assert (payload["step"], payload["statistic"], payload["unit"]) == (
        "year",
        "max",
        "m3/s",
    )
    assert (payload["years"], payload["values"]) == ANNUAL_MAXIMA
    assert answer["result"]["analysis"] == "flood_frequency.Q"
    assert answer["result"]["hydrolog"] == {"version": HYDROLOG_VERSION}
    assert answer["provenance"]["series"]["command"] == "hydrolog stats flood-frequency"
    assert answer["subject"] == message(
        "gui.handoff.subject_annual",
        lang="pl",
        station="Raba Górna (Raba)",
        variable="Q",
    )


def test_a_failed_hydrolog_result_has_no_annual_maxima_to_hand_off(
    make_client, tmp_path
):
    client = make_client(hydrolog=write_program(tmp_path / "failing.py", fail=True))

    problem(
        client.get(f"/api/handoff/{HYDRO}", params={"resolution": "annual"}),
        404,
        "not_found",
    )


# --- the page, the headers and the methods ---------------------------------------------------


def test_the_page_and_its_files_are_revalidated_on_every_load(client):
    page = client.get("/")
    script = client.get("/theme-init.js")
    border = client.get("/data/poland_border_wgs84.geojson")

    assert page.status_code == 200
    assert page.headers["content-type"] == "text/html; charset=utf-8"
    assert 'id="app"' in page.text
    assert script.headers["content-type"].startswith("text/javascript")
    for answer in (page, script, border):
        assert answer.headers["cache-control"] == "no-cache"
    assert border.headers["content-type"] == "application/geo+json"
    assert border.json()["type"] in ("FeatureCollection", "Feature")
    problem(client.get("/data/germany_border_wgs84.geojson"), 404, "not_found")
    assert client.get("/src/no-such-module.js").status_code == 404
    again = client.get("/", headers={"If-None-Match": page.headers["etag"]})
    assert again.status_code == 304


def test_the_page_names_its_files_at_addresses_kept_for_a_year(client):
    page = client.get("/")
    loaded = re.findall(r'(?:src|href)="([^"]+)"', page.text)
    (build,) = {m[1] for m in (re.match(r"v/([0-9a-f]{16})/", a) for a in loaded) if m}
    preloaded = re.findall(r'<link rel="modulepreload" href="([^"]+)"', page.text)
    answers = {address: client.get(f"/{address}") for address in loaded}

    for address, answer in answers.items():
        assert answer.status_code == 200, address
        long = address.startswith(f"v/{build}/") or "?v=" in address
        expected = "public, max-age=31536000, immutable" if long else "no-cache"
        assert answer.headers["cache-control"] == expected, address
    assert f"v/{build}/src/main.js" in loaded
    assert "vendor/maplibre-gl/maplibre-gl.css?v=6.14.0" in loaded
    # Every module of the start is asked for at once: the main module's imports, theirs, …
    assert f"v/{build}/src/lib.js" in preloaded
    assert f"v/{build}/vendor/preact/hooks.mjs" in preloaded
    assert f"v/{build}/src/charts/draw.js" in preloaded
    assert not any("maplibre" in address for address in preloaded)
    assert page.headers["cache-control"] == "no-cache"
    assert client.get("/index.html").content == page.content


def test_an_address_of_another_build_or_version_is_revalidated(client):
    build = re.search(r'src="v/([0-9a-f]{16})/src/main.js"', client.get("/").text)[1]
    current = client.get(f"/v/{build}/src/main.js")
    older = client.get("/v/0123456789abcdef/src/main.js")
    module = client.get("/vendor/maplibre-gl/maplibre-gl.mjs?v=6.14.0")
    other = client.get("/vendor/maplibre-gl/maplibre-gl.mjs?v=6.13.0")
    plain = client.get("/src/main.js")
    again = client.get(
        f"/v/{build}/src/main.js", headers={"If-None-Match": current.headers["etag"]}
    )

    assert current.headers["cache-control"] == "public, max-age=31536000, immutable"
    assert module.headers["cache-control"] == "public, max-age=31536000, immutable"
    assert again.status_code == 304
    # An older build's address (a page cached across a release) gets this build's file
    assert older.content == current.content == plain.content
    for answer in (older, other, plain):
        assert answer.status_code == 200
        assert answer.headers["cache-control"] == "no-cache"
    # Only the page's files are under a build's address
    for path in ("admin/index.html", "instrukcja/index.html", "index.html", "x/y.js"):
        assert client.get(f"/v/{build}/{path}").status_code == 404, path
    assert client.get(f"/v/{build}").status_code == 404


def test_the_icons_and_robots_txt_are_served(client):
    favicon = client.get("/favicon.ico")
    touch = client.get("/apple-touch-icon.png")
    precomposed = client.get("/apple-touch-icon-precomposed.png")
    robots = client.get("/robots.txt")

    assert favicon.status_code == touch.status_code == precomposed.status_code == 200
    assert favicon.content[:4] == b"\x00\x00\x01\x00"  # an ICO directory
    assert touch.content[:8] == b"\x89PNG\r\n\x1a\n"
    assert precomposed.headers["content-type"] == "image/png"
    assert precomposed.content == touch.content
    assert robots.headers["content-type"].startswith("text/plain")
    # Crawlers keep to the page: the API computes on request
    assert robots.text.splitlines() == ["User-agent: *", "Disallow: /api/"]


def test_the_scripts_are_javascript_whatever_types_the_system_registers(
    make_client, monkeypatch
):
    # The types of a Windows registry, which `mimetypes` reads into its table at init.
    mimetypes.init()
    monkeypatch.setitem(mimetypes.types_map, ".js", "application/javascript")
    monkeypatch.setitem(mimetypes.types_map, ".mjs", "text/plain")
    client = make_client()

    for path in ("/theme-init.js", "/vendor/preact/preact.mjs"):
        answer = client.get(path)
        assert answer.status_code == 200
        assert answer.headers["content-type"] == "text/javascript; charset=utf-8"


def test_every_answer_carries_the_security_headers(client):
    answers = [
        client.get("/"),
        client.get("/theme-init.js"),
        client.get("/nothing-here.css"),
        client.get("/api/session"),
        client.get(f"/api/stations/{HYDRO}"),
        client.get("/api/stations/999999999"),
        client.get("/api/pmaxtp?latitude=x"),
        client.get(f"/api/files/series/pl.imgw.hydro_daily/{HYDRO}"),
        client.get("/api/nothing"),
        client.get("/regulamin.html"),
        client.post("/api/session"),
        client.post("/api/feedback", content=b"{}"),
        client.head("/api/session"),
    ]
    tag = client.get("/api/stations").headers["etag"]
    answers.append(client.get("/api/stations", headers={"If-None-Match": tag}))

    assert {answer.status_code for answer in answers} == {
        200,
        304,
        400,
        403,
        404,
        405,
    }
    for answer in answers:
        for name, value in SECURITY.items():
            assert answer.headers[name] == value, (answer.url, name)
        policy = denied(answer.headers["permissions-policy"])
        assert policy >= UNUSED_FEATURES, answer.url
        assert not {"clipboard-write", "clipboard-read"} & policy, answer.url
        assert csp(answer) == OWN_ORIGIN_ONLY, answer.url
        assert answer.headers["cache-control"] in ("no-cache", "no-store")
        assert "x-request-id" not in answer.headers  # the request id stays in the log


def test_the_basemap_origin_is_the_only_remote_one_the_page_may_reach(make_client):
    basemap = Basemap(
        "https://tiles.example/planet", "https://tiles.example", "© Example"
    )
    client = make_client(basemap=basemap)

    answer = client.get("/api/session")

    assert answer.json()["basemap"] == {
        "url": "https://tiles.example/planet",
        "attribution": "© Example",
    }
    policy = csp(answer)
    assert policy["img-src"] == ["'self'", "data:", "blob:", "https://tiles.example"]
    assert policy["connect-src"] == ["'self'", "https://tiles.example"]
    assert policy["script-src"] == ["'self'"]


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
@pytest.mark.parametrize("path", ["/", "/api/session", f"/api/stations/{HYDRO}"])
def test_only_get_and_head_are_allowed(client, method, path):
    answer = client.request(method, path, headers=EN)

    body = problem(answer, 405, "method_not_allowed", "en")
    assert answer.headers["allow"] == "GET, HEAD"
    assert body["message"] == message(
        "gui.errors.method_not_allowed", method=method, allowed="GET, HEAD"
    )


def test_feedback_takes_post_only_and_head_answers_without_a_body(client):
    get = client.get("/api/feedback")
    head = client.head(f"/api/stations/{HYDRO}")

    problem(get, 405, "method_not_allowed")
    assert get.headers["allow"] == "POST"
    assert head.status_code == 200
    assert head.content == b""
    assert head.headers["etag"]


@pytest.mark.parametrize(
    ("accept", "lang"),
    [
        (None, "pl"),
        ("en", "en"),
        ("en-GB,en;q=0.9", "en"),
        ("de-DE,de;q=0.9", "pl"),
        ("fr, pl;q=0.5, en;q=0.4", "pl"),
        ("PL", "pl"),
    ],
)
def test_errors_are_in_the_language_of_the_page(client, accept, lang):
    headers = {"Accept-Language": accept} if accept else {}

    answer = client.get("/api/stations/999999999", headers=headers)

    body = problem(answer, 404, "not_found", lang)
    assert body["message"] == message(
        "gui.errors.no_station", lang=lang, station="999999999"
    )


def test_an_unknown_address_of_the_api_is_404(client):
    body = problem(client.get("/api/v1/stations", headers=EN), 404, "not_found", "en")

    assert body["message"] == message("gui.errors.not_found", path="/api/v1/stations")


def test_a_root_that_cannot_be_read_is_shown_without_the_servers_directories(
    make_client, tmp_path
):
    client = make_client(root=tmp_path / "no-root")

    session = client.get("/api/session")
    answers = [
        client.get("/api/stations"),
        client.get(f"/api/stations/{HYDRO}"),
        client.get(f"/api/series/pl.imgw.hydro_daily/{HYDRO}"),
        client.get("/api/downloads/stations"),
    ]

    assert session.status_code == 200
    error = session.json()["root"]["error"]
    assert error["code"] == "store_unavailable"
    assert str(tmp_path) not in session.text
    for answer in answers:
        problem(answer, 503, "store_unavailable")
        assert str(tmp_path) not in answer.text


# --- the data root and the GUI's own files (D7) ---------------------------------------------


def exercise(client) -> None:
    """Requests of every kind a person makes, a report of „Zgłoś uwagę” included."""
    for path in (
        "/",
        "/api/session",
        "/api/stations",
        f"/api/stations/{HYDRO}",
        f"/api/series/pl.imgw.hydro_daily/{HYDRO}",
        f"/api/downloads/{HYDRO}",
        f"/api/files/series/pl.imgw.hydro_daily/{HYDRO}?format=parquet",
        "/api/files/stations?format=csv",
        f"/api/handoff/{HYDRO_CHMU}",
        f"/api/analysis/{HYDRO}/characteristic.Q",
    ):
        client.get(path)


def test_the_gui_never_writes_under_the_root(
    make_client, fixture_root, hydrolog, tmp_path
):
    before = files_of(fixture_root)
    client = make_client(fixture_root, hydrolog=hydrolog, gui_dir=tmp_path / "state")

    exercise(client)
    client.post("/api/feedback", json=REPORT, headers=SAME_SITE)
    client.__exit__(None, None, None)

    assert files_of(fixture_root) == before
    assert sorted(path.name for path in (tmp_path / "state").iterdir()) == [
        "feedback.jsonl",
        "feedback.next_id",
        "stats.jsonl",
    ]


@pytest.mark.parametrize("layout", ["same", "gui_dir_in_root", "root_in_gui_dir"])
def test_the_gui_writes_none_of_its_files_where_they_would_be_under_the_root(
    make_client, fixture_root, tmp_path, caplog, layout
):
    if layout == "same":
        root = gui_dir = tmp_path / "obserwator"
    elif layout == "gui_dir_in_root":
        root, gui_dir = tmp_path / "obserwator", tmp_path / "obserwator" / "gui"
    else:
        root, gui_dir = tmp_path / "obserwator" / "root", tmp_path / "obserwator"
    shutil.copytree(fixture_root, root)
    before = files_of(tmp_path)
    caplog.set_level(logging.WARNING, logger="obserwator.gui._app")

    client = make_client(root, gui_dir=gui_dir, headers=EN)
    exercise(client)
    report = client.post("/api/feedback", json=REPORT, headers=SAME_SITE)
    client.__exit__(None, None, None)

    body = problem(report, 403, "forbidden", "en")
    assert body["message"] == message("gui.errors.feedback_off")
    assert files_of(tmp_path) == before
    warnings = [
        record.getMessage()
        for record in caplog.records
        if record.name.startswith("obserwator.gui")
    ]
    assert warnings == [
        message("gui.server.gui_dir_in_root", gui_dir=str(gui_dir), root=str(root))
    ]


# --- the app under a prefix (D5) ---------------------------------------------------------------


def test_the_app_mounted_under_a_prefix_serves_the_page_and_the_api(
    read_only_root, live, tmp_path
):
    from obserwator.gui._app import build_app
    from obserwator.gui._live import CurrentData, Pmaxtp
    from tests.unit.gui.conftest import gui_config

    gui = build_app(gui_config(read_only_root, tmp_path / "state"))
    gui.state.gui.current = CurrentData(sources=live.sources())
    gui.state.gui.pmaxtp = Pmaxtp(fetch=live.fetch)
    host = Starlette(routes=[Mount("/m/obserwator", app=gui)])

    with TestClient(host) as client:
        page = client.get("/m/obserwator/")
        station = client.get(f"/m/obserwator/api/stations/{HYDRO}")
        handoff = client.get(f"/m/obserwator/api/handoff/{HYDRO_CHMU}").json()
        missing = client.get("/m/obserwator/api/nothing")
        refused = client.post("/m/obserwator/api/session")
        report = client.post("/m/obserwator/api/feedback", json=REPORT)
        downloads = client.get(f"/m/obserwator/api/downloads/{HYDRO}").json()
        url = downloads["series"][0]["formats"]["csv"]["url"]
        file = client.get(f"/m/obserwator/{url}")
        robots = client.get("/m/obserwator/robots.txt")

    assert page.status_code == 200
    assert 'id="app"' in page.text
    assert station.json()["code"] == HYDRO
    assert handoff["producer"]["page"] == (
        f"http://testserver/m/obserwator/?station={HYDRO_CHMU}"
    )
    problem(missing, 404, "not_found")
    problem(refused, 405, "method_not_allowed")
    problem(report, 403, "forbidden")  # POST reaches the route: only the site is wrong
    assert file.status_code == 200
    assert "Disallow: /m/obserwator/api/" in robots.text.splitlines()
    for answer in (page, station, missing, refused, file):
        assert csp(answer) == OWN_ORIGIN_ONLY
