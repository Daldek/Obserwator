"""The section ``[obserwator.instance]`` (ADR-025): checks, the filter, ``config show``."""

import json
import logging
import os
import stat
from pathlib import Path

import platformdirs
import pytest
from typer.testing import CliRunner

from obserwator.cli import main as cli_main
from obserwator.config import (
    check_credentials,
    check_root_layout,
    configured_token,
    credential_problems,
    environment_report,
)
from obserwator.exceptions import ObserwatorStoreError, ObserwatorValidationError
from obserwator.instance import (
    AREA_MAX_BYTES,
    AREA_MAX_VERTICES,
    LOGO_MAX_BYTES,
    Instance,
    load_instance,
    provider_of_code,
)
from obserwator.store.types import StationFeature

RUNNER = CliRunner()
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + b"\x00" * 17
WEBP = b"RIFF" + (30).to_bytes(4, "little") + b"WEBPVP8 " + b"\x00" * 22
SVG = b'<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"></svg>'
SQUARE = [[14.0, 49.5], [16.0, 49.5], [16.0, 50.6], [14.0, 50.6], [14.0, 49.5]]
HOLE = [[14.5, 49.8], [14.9, 49.8], [14.9, 50.0], [14.5, 50.0], [14.5, 49.8]]
TERMS = "# Regulamin serwisu {{service_name}}\n\nTekst operatora.\n"


@pytest.fixture(autouse=True)
def user_environment(tmp_path, monkeypatch):
    """No OBSERWATOR_/NOGAT_ variable, ``.env`` or user ``nogat.toml`` of the machine."""
    for name in list(os.environ):
        if name.startswith(("OBSERWATOR_", "NOGAT_")):
            monkeypatch.delenv(name)
    home = tmp_path / "home"
    monkeypatch.setattr(
        platformdirs, "user_config_path", lambda *a, **k: home / "config"
    )
    monkeypatch.setattr(platformdirs, "user_data_path", lambda *a, **k: home / "data")
    monkeypatch.setattr(platformdirs, "user_cache_path", lambda *a, **k: home / "cache")
    monkeypatch.setattr(platformdirs, "user_state_path", lambda *a, **k: home / "state")
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)
    return home


def deployment(tmp_path: Path, monkeypatch, section: str, **files: bytes | str) -> Path:
    """A ``nogat.toml`` with ``section`` (an instance table) and files beside it."""
    folder = tmp_path / "config"
    folder.mkdir(exist_ok=True)
    for name, content in files.items():
        target = folder / name.replace("__", ".")
        if isinstance(content, bytes):
            target.write_bytes(content)
        else:
            target.write_text(content, encoding="utf-8")
    path = folder / "nogat.toml"
    path.write_text(section, encoding="utf-8")
    monkeypatch.setenv("NOGAT_CONFIG", str(path))
    return folder


def polygon(*rings) -> str:
    return json.dumps({"type": "Polygon", "coordinates": [list(r) for r in rings]})


def feature(code: str, provider: str, point: tuple[float, float] | None):
    return StationFeature(code, point, {"kind": "hydro"}, provider)


def refused(option: str):
    with pytest.raises(ObserwatorValidationError) as caught:
        load_instance()
    assert caught.value.code == "validation_error"
    assert caught.value.details["option"] == option
    return caught.value


# --- the section -----------------------------------------------------------------------


def test_without_the_section_there_is_no_instance(tmp_path, monkeypatch):
    deployment(tmp_path, monkeypatch, "[obserwator]\nport = 9000\n")

    assert load_instance() is None
    report = environment_report()
    assert report["instance"] is None
    assert report["problems"] == []
    assert report["config_file"]["ignored"] == []


def test_a_section_resolves_with_its_defaults_and_relative_paths(tmp_path, monkeypatch):
    folder = deployment(
        tmp_path,
        monkeypatch,
        '[obserwator.instance]\ntitle = " Wody Testowe "\nfeatured_provider = "CHMI"\n'
        'start_view = "featured"\narea = "area.geojson"\narea_mode = "clip"\n'
        'pmaxtp = "off"\nlogo = "logo.svg"\nterms = "terms.md"\n\n'
        '[obserwator.instance.providers]\nIMGW-PIB = "hidden"\n',
        area__geojson=polygon(SQUARE),
        logo__svg=SVG,
        terms__md=TERMS,
    )

    instance = load_instance()

    assert instance is not None
    assert instance.title == "Wody Testowe"
    assert dict(instance.providers) == {"IMGW-PIB": "hidden", "CHMI": "visible"}
    assert instance.served == ("CHMI", "IMGW-PIB")
    assert (instance.featured, instance.start_view, instance.pmaxtp) == (
        "CHMI",
        "featured",
        False,
    )
    assert instance.area is not None and instance.area.path == folder / "area.geojson"
    assert instance.clips and instance.area.box == (14.0, 49.5, 16.0, 50.6)
    assert instance.logo is not None and instance.logo.media_type == "image/svg+xml"
    assert instance.terms is not None and instance.terms.text == TERMS
    report = environment_report()["instance"]
    assert report["providers"] == {"IMGW-PIB": "hidden", "CHMI": "visible"}
    assert report["area"]["mode"] == "clip" and report["area"]["vertices"] == 5
    assert report["logo"]["media_type"] == "image/svg+xml"
    assert report["pmaxtp"] == "off"


def test_a_bare_section_serves_everything_from_the_whole_extent(tmp_path, monkeypatch):
    deployment(tmp_path, monkeypatch, "[obserwator.instance]\n")

    instance = load_instance()

    assert instance is not None
    assert dict(instance.providers) == {"IMGW-PIB": "visible", "CHMI": "visible"}
    assert (instance.start_view, instance.area, instance.pmaxtp) == ("all", None, True)
    assert not instance.clips
    assert instance.keeps(feature("149190310", "IMGW-PIB", None))


@pytest.mark.parametrize(
    ("section", "option"),
    [
        ('colour = "red"\n', "instance.colour"),
        ('admin_api_key = "secret"\n', "instance.admin_api_key"),
        ('[obserwator.instance.providers]\nKNMI = "off"\n', "instance.providers.KNMI"),
        (
            '[obserwator.instance.providers]\nCHMI = "invisible"\n',
            "instance.providers.CHMI",
        ),
        ('featured_provider = "KNMI"\n', "instance.featured_provider"),
        (
            'featured_provider = "CHMI"\n[obserwator.instance.providers]\nCHMI = "off"\n',
            "instance.featured_provider",
        ),
        ('start_view = "featured"\n', "instance.start_view"),
        ('start_view = "area"\n', "instance.start_view"),
        ('start_view = "everything"\n', "instance.start_view"),
        ('area_mode = "clip"\n', "instance.area_mode"),
        ("pmaxtp = true\n", "instance.pmaxtp"),
        ("title = 7\n", "instance.title"),
        ('title = "one\\ntwo"\n', "instance.title"),
        (f'title = "{"x" * 81}"\n', "instance.title"),
        (
            'pmaxtp = "off"\n[obserwator.instance.providers]\n'
            'IMGW-PIB = "off"\nCHMI = "off"\n',
            "instance.providers",
        ),
        ('area = "missing.geojson"\n', "instance.area"),
        ('logo = "missing.png"\n', "instance.logo"),
        ('terms = "missing.md"\n', "instance.terms"),
    ],
)
def test_a_wrong_section_is_refused_naming_its_field(
    tmp_path, monkeypatch, section, option
):
    deployment(tmp_path, monkeypatch, "[obserwator.instance]\n" + section)

    refused(option)
    problem = environment_report()["problems"][0]
    assert (problem["code"], problem["option"]) == ("invalid_instance", option)
    assert environment_report()["instance"] is None


def test_the_instance_table_must_be_a_table(tmp_path, monkeypatch):
    deployment(tmp_path, monkeypatch, '[obserwator]\ninstance = "yes"\n')

    refused("instance")


# --- the area --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "document",
    [
        {"type": "Polygon", "coordinates": [SQUARE, HOLE]},
        {
            "type": "Feature",
            "properties": {},
            "geometry": {"type": "Polygon", "coordinates": [SQUARE, HOLE]},
        },
        {
            "type": "FeatureCollection",
            "crs": {
                "type": "name",
                "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"},
            },
            "features": [
                {
                    "type": "Feature",
                    "properties": {},
                    "geometry": {
                        "type": "MultiPolygon",
                        "coordinates": [
                            [SQUARE, HOLE],
                            [[[20, 52], [21, 52], [21, 53], [20, 52]]],
                        ],
                    },
                }
            ],
        },
    ],
)
def test_an_area_is_one_polygon_with_its_holes(tmp_path, monkeypatch, document):
    deployment(
        tmp_path,
        monkeypatch,
        '[obserwator.instance]\narea = "area.json"\narea_mode = "clip"\n',
        area__json=json.dumps(document),
    )

    instance = load_instance()

    assert instance is not None and instance.area is not None
    assert instance.keeps_point(15.5, 50.4)
    assert not instance.keeps_point(14.7, 49.9)  # in the hole
    assert not instance.keeps_point(17.25, 49.85)
    assert not instance.keeps_point(None, None)
    multi = document.get("features", [{}])[0].get("geometry", {}).get("type")
    assert instance.keeps_point(20.2, 52.1) is (multi == "MultiPolygon")


@pytest.mark.parametrize(
    "content",
    [
        "{not json",
        json.dumps({"type": "Point", "coordinates": [15, 50]}),
        json.dumps({"type": "FeatureCollection", "features": []}),
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "geometry": {"type": "Polygon", "coordinates": [SQUARE]},
                    },
                    {
                        "type": "Feature",
                        "geometry": {"type": "Polygon", "coordinates": [SQUARE]},
                    },
                ],
            }
        ),
        polygon(SQUARE[:-1]),  # not closed
        polygon([[0, 0], [1, 1], [0, 0]]),  # three positions
        polygon(
            [[500000, 600000], [500001, 600000], [500001, 600001], [500000, 600000]]
        ),
        polygon([[14, "49"], [15, 49], [15, 50], [14, "49"]]),
        json.dumps(
            {
                "type": "Polygon",
                "crs": {"type": "name", "properties": {"name": "EPSG:2180"}},
                "coordinates": [SQUARE],
            }
        ),
    ],
)
def test_an_area_that_is_no_wgs84_polygon_is_refused(tmp_path, monkeypatch, content):
    deployment(
        tmp_path,
        monkeypatch,
        '[obserwator.instance]\narea = "area.geojson"\n',
        area__geojson=content,
    )

    refused("instance.area")


def test_an_area_has_at_most_its_bytes_and_vertices(tmp_path, monkeypatch):
    ring = [[0, 0]] + [[1, 1]] * (AREA_MAX_VERTICES - 1) + [[0, 0]]
    text = json.dumps({"type": "Polygon", "coordinates": [ring]}, separators=(",", ":"))
    assert len(text) <= AREA_MAX_BYTES
    deployment(
        tmp_path,
        monkeypatch,
        '[obserwator.instance]\narea = "area.geojson"\n',
        area__geojson=text,
    )
    error = refused("instance.area")
    assert error.details["maximum"] == AREA_MAX_VERTICES

    (tmp_path / "config" / "area.geojson").write_text(
        " " * AREA_MAX_BYTES + polygon(SQUARE), encoding="utf-8"
    )
    error = refused("instance.area")
    assert error.details["maximum"] == AREA_MAX_BYTES


# --- the logo and the regulamin ---------------------------------------------------------


@pytest.mark.parametrize(
    ("content", "media_type"),
    [(PNG, "image/png"), (WEBP, "image/webp"), (SVG, "image/svg+xml")],
)
def test_a_logo_is_typed_by_its_content(tmp_path, monkeypatch, content, media_type):
    deployment(
        tmp_path,
        monkeypatch,
        '[obserwator.instance]\nlogo = "logo.bin"\n',
        logo__bin=content,
    )

    instance = load_instance()

    assert instance is not None and instance.logo is not None
    assert (instance.logo.media_type, instance.logo.data) == (media_type, content)


# Short ids: pytest puts the id into PYTEST_CURRENT_TEST, which Windows caps at 32767
# characters, and the bytes of the large logo would be its id.
@pytest.mark.parametrize(
    "content",
    [
        b"GIF89a" + b"\x00" * 10,
        b"<html><body>no image</body></html>",
        b'<!DOCTYPE svg [<!ENTITY a "aaaa">]><svg xmlns="http://www.w3.org/2000/svg">&a;</svg>',
        b"<svg>no namespace</svg>",
        PNG + b"\x00" * LOGO_MAX_BYTES,
    ],
    ids=["gif", "html", "svg-entity", "svg-no-namespace", "png-too-large"],
)
def test_a_logo_that_is_no_small_png_webp_or_svg_is_refused(
    tmp_path, monkeypatch, content
):
    deployment(
        tmp_path,
        monkeypatch,
        '[obserwator.instance]\nlogo = "logo.png"\n',
        logo__png=content,
    )

    refused("instance.logo")


@pytest.mark.parametrize(
    "content",
    [
        "<!--\nWZÓR REGULAMINU\n-->\n# Regulamin\n",
        "Regulamin bez tytułu\n",
        "# Regulamin\n\n[kliknij](javascript:alert(1))\n",
        "# Regulamin\n\n[strona](regulamin.html)\n",
        b"# Regulamin \xff\n",
    ],
)
def test_a_regulamin_without_its_title_or_with_an_unsafe_link_is_refused(
    tmp_path, monkeypatch, content
):
    deployment(
        tmp_path,
        monkeypatch,
        '[obserwator.instance]\nterms = "terms.md"\n',
        terms__md=content,
    )

    refused("instance.terms")


def test_a_regulamin_may_link_to_web_mail_anchors_and_fields(tmp_path, monkeypatch):
    text = (
        "# Regulamin\n\n[a](https://example.org) [b](mailto:{{operator_email}}) "
        "[c](#top) [d]({{service_url}}) <https://uodo.gov.pl>\n"
    )
    deployment(
        tmp_path,
        monkeypatch,
        '[obserwator.instance]\nterms = "terms.md"\n',
        terms__md=text,
    )

    instance = load_instance()

    assert instance is not None and instance.terms is not None


def test_a_regulamin_written_on_windows_reads_as_the_same_text(tmp_path, monkeypatch):
    lf = TERMS.encode("utf-8")
    read = []
    for data in (
        lf,
        lf.replace(b"\n", b"\r\n"),
        b"\xef\xbb\xbf" + lf.replace(b"\n", b"\r\n"),
    ):
        deployment(
            tmp_path,
            monkeypatch,
            '[obserwator.instance]\nterms = "terms.md"\n',
            terms__md=data,
        )
        instance = load_instance()
        assert instance is not None and instance.terms is not None
        read.append((instance.terms.text, instance.terms.sha256, instance.key))

    assert read[0][0] == TERMS
    assert read[1] == read[0] and read[2] == read[0]


# --- the filter --------------------------------------------------------------------------


def test_the_filter_keeps_the_served_providers_and_the_stations_inside(
    tmp_path, monkeypatch
):
    deployment(
        tmp_path,
        monkeypatch,
        '[obserwator.instance]\narea = "area.geojson"\narea_mode = "clip"\n'
        '[obserwator.instance.providers]\nIMGW-PIB = "off"\n',
        area__geojson=polygon(SQUARE),
    )
    instance = load_instance()
    assert instance is not None
    stations = {
        "0-203-0-90001": feature("0-203-0-90001", "CHMI", (14.8213, 50.2147)),
        "0-203-1-900002": feature("0-203-1-900002", "CHMI", (17.25, 49.85)),
        "0-20000-0-99903": feature("0-20000-0-99903", "CHMI", None),
        "149190310": feature("149190310", "IMGW-PIB", (15.0, 50.0)),
    }

    assert [code for code, item in stations.items() if instance.keeps(item)] == [
        "0-203-0-90001"
    ]
    assert not instance.serves("IMGW-PIB") and instance.serves("CHMI")
    assert provider_of_code("149190310") == "IMGW-PIB"
    assert provider_of_code("0-203-1-900002") == "CHMI"
    assert provider_of_code("../etc") is None


def test_the_start_view_falls_back_to_the_whole_extent_when_empty():
    instance = Instance(
        providers={"IMGW-PIB": "visible", "CHMI": "visible"},
        featured="CHMI",
        start_view="featured",
    )
    stations = {
        "a": feature("a", "CHMI", (15.0, 50.0)),
        "b": feature("b", "CHMI", (16.0, 49.0)),
        "c": feature("c", "IMGW-PIB", (21.0, 52.0)),
    }

    view, box = instance.start(stations)
    assert view == "featured"
    assert box is not None
    assert box[0] < 15.0 and box[2] > 16.0 and box[1] < 49.0 and box[3] > 50.0
    assert box[2] < 21.0  # the IMGW-PIB station is not in the featured box
    assert instance.start({"c": stations["c"]}) == ("all", None)


# --- secrets, the deprecated keys, the layout ----------------------------------------------


def test_a_short_key_or_a_shared_key_file_is_a_problem(tmp_path, monkeypatch, caplog):
    monkeypatch.setenv("OBSERWATOR_STORE_WRITE_TOKEN", "tiny-secret-7")
    key = tmp_path / "admin.key"
    key.write_text("k" * 40 + "\n", encoding="utf-8")
    key.chmod(0o644)
    monkeypatch.setenv("OBSERWATOR_ADMIN_API_KEY_FILE", str(key))

    problems = credential_problems()

    assert [(p["code"], p["option"]) for p in problems] == [
        ("short_secret", "OBSERWATOR_STORE_WRITE_TOKEN"),
        ("secret_file_mode", "OBSERWATOR_ADMIN_API_KEY_FILE"),
    ]
    text = json.dumps(environment_report())
    assert "tiny-secret-7" not in text and "k" * 40 not in text
    assert str(key) not in text
    with caplog.at_level(logging.WARNING):
        check_credentials("admin", strict=False)
    assert "OBSERWATOR_ADMIN_API_KEY_FILE" in caplog.text
    with pytest.raises(ObserwatorValidationError) as caught:
        check_credentials("token", strict=True)
    assert caught.value.details == {
        "option": "OBSERWATOR_STORE_WRITE_TOKEN",
        "reason": "short_secret",
    }

    key.chmod(0o600)
    monkeypatch.setenv("OBSERWATOR_STORE_WRITE_TOKEN", "t" * 32)
    assert credential_problems() == []


def test_the_write_token_may_come_from_a_file(tmp_path, monkeypatch):
    token = tmp_path / "token"
    token.write_text("x" * 48 + "\n", encoding="utf-8")
    token.chmod(stat.S_IRUSR | stat.S_IWUSR)
    monkeypatch.setenv("OBSERWATOR_STORE_WRITE_TOKEN_FILE", str(token))

    from obserwator.config import Settings

    assert configured_token(Settings()) == "x" * 48
    monkeypatch.setenv("OBSERWATOR_STORE_WRITE_TOKEN", "y" * 40)
    assert configured_token(Settings()) == "y" * 40
    report = environment_report()
    assert report["credentials"]["OBSERWATOR_STORE_WRITE_TOKEN_FILE"] == "present"
    assert "x" * 48 not in json.dumps(report)


def test_the_deprecated_api_keys_say_so(tmp_path, monkeypatch):
    keys = tmp_path / "home" / "data" / "obserwator" / "api_keys.json"
    keys.parent.mkdir(parents=True)
    keys.write_text('{"keys": []}', encoding="utf-8")

    result = RUNNER.invoke(cli_main.app, ["admin", "keys"])
    report = environment_report()

    assert result.exit_code == 0
    assert "v4.0.0" in result.stderr
    assert [p["code"] for p in report["problems"]] == ["deprecated_api_keys"]
    shown = RUNNER.invoke(cli_main.app, ["config", "show"])
    assert "deprecated_api_keys" in shown.stdout


def test_config_show_names_a_wrong_section_as_a_problem(tmp_path, monkeypatch):
    deployment(
        tmp_path, monkeypatch, '[obserwator.instance]\nfeatured_provider = "KNMI"\n'
    )

    result = RUNNER.invoke(cli_main.app, ["config", "show", "--json"])

    report = json.loads(result.stdout)
    assert result.exit_code == 0
    assert report["instance"] is None
    assert report["problems"][0]["option"] == "instance.featured_provider"


def test_a_root_of_an_unknown_layout_is_refused(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    check_root_layout(root)  # no marker: the page shows its error, as before
    (root / "obserwator-data.json").write_text(
        '{"schema": "obserwator-data/9", "tool": "obserwator"}', encoding="utf-8"
    )

    with pytest.raises(ObserwatorStoreError) as caught:
        check_root_layout(root)

    assert caught.value.code == "store_unavailable"
    assert caught.value.details["reason"] == "unsupported_layout"
    assert caught.value.hint is not None and "obserwator-data/1" in caught.value.hint
    (root / "obserwator-data.json").write_text(
        '{"schema": "obserwator-data/1", "tool": "obserwator"}', encoding="utf-8"
    )
    check_root_layout(root)
