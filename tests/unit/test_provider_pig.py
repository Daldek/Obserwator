"""PIG-PIB's answers as its adapter reads them: readings, points and their search (ADR-035).

Plan tests 1, 5, 6 and 16 of ``2026-11-24-pig-groundwater.md`` on the rows recorded
from cbdgmapa.pgi.gov.pl on 2026-11-24 and 2026-11-25 (``pig_recordings.json``): the
fixture variant ``groundwater_pl`` (`groundwater_pl_roots`), and roots synchronized
here from `obserwator.testing._PigService`, which answers with ArcGIS's semantics. The
run's clock (`obserwator.fetch._clock`), the spool's, the writer's and the envelope's
follow a fake clock, which the pacing moves instead of sleeping.
"""

import gzip
import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
import respx

from obserwator import captures, commands, fetch
from obserwator.attribution import attribution
from obserwator.commands import run_command
from obserwator.store import (
    build_catalog,
    current_version,
    init_store,
    read_catalog,
    read_series,
    sync_store,
    writer,
)
from obserwator.testing import _PigService
from tests.unit.test_paced import FakeClock

POINTS = "pl.pig.groundwater_stations"
READINGS = "pl.pig.groundwater_readings"
NOW = datetime(2026, 11, 24, 22, 16, tzinfo=UTC)
"""When the probe captured the recorded answers, as the fixture variant's clock."""
OLSZYC = (22.108861020498814, 52.02697218383176)
"""The WGS84 point of the bore 6495 the service answers (``outSR=4326``)."""


def pace(tmp_path, monkeypatch):
    """The test's spool and ``nogat.toml``; the run's, spool's, writer's and envelope's clock."""
    monkeypatch.setenv("OBSERWATOR_STATE_DIR", str(tmp_path / "state"))
    config = tmp_path / "nogat.toml"
    config.write_text("", encoding="utf-8")
    monkeypatch.setenv("NOGAT_CONFIG", str(config))
    fake = FakeClock(NOW)
    monkeypatch.setattr(fetch, "_clock", lambda: fake)
    monkeypatch.setattr(fetch, "_ARCGIS", fetch._Spacing())
    monkeypatch.setattr(captures, "_now", fake.now)

    class Clock(datetime):
        """``downloaded_at`` and the day of a search follow the fake clock."""

        @classmethod
        def now(cls, tz=None):
            return fake.now().astimezone(tz)

    monkeypatch.setattr(writer, "datetime", Clock)
    monkeypatch.setattr(commands, "datetime", Clock)
    return fake


@pytest.fixture(autouse=True)
def clock(tmp_path, monkeypatch):
    return pace(tmp_path, monkeypatch)


@pytest.fixture
def service():
    return _PigService()


@pytest.fixture
def server(service):
    """PIG-PIB's services answer from the recorded rows; any other request fails."""
    with respx.mock(assert_all_called=False) as mock:
        mock.route(host="cbdgmapa.pgi.gov.pl").mock(side_effect=service)
        yield mock


def roots(tmp_path):
    """A new raw root and data root."""
    return (
        init_store(tmp_path / "raw").root,
        init_store(tmp_path / "data", kind="data").root,
    )


def bodies(version):
    """The bodies of the answers of a stored container, as JSON (``seen`` lines repeat)."""
    text = gzip.decompress(Path(version).read_bytes()).decode("utf-8")
    lines = [json.loads(line) for line in text.splitlines()]
    return [json.loads(line["body"]) for line in lines if "body" in line]


def catalog(data):
    """The current PIG catalog's points by code."""
    return {
        feature.station_code: feature
        for feature in read_catalog(root=data, provider="PIG")
    }


# --------------------------------------------------------------------------
# The readings' day: a text with a leading space (test 1)
# --------------------------------------------------------------------------


def test_a_reading_is_dated_without_the_leading_space_the_capture_keeps(
    groundwater_pl_roots,
):
    raw, data = groundwater_pl_roots.raw.root, groundwater_pl_roots.data.root
    stored = current_version(
        raw, slot=f"archive:{READINGS}:MWP_2026-10.jsonl.gz"
    ).version
    published = {
        feature["attributes"]["DATA_POMIARU"]
        for body in bodies(stored)
        for feature in body.get("features", ())
    }

    rows = list(read_series(root=data, dataset=READINGS, station="6495"))

    # Kept as PIG-PIB published them: every day of October with a space before it.
    assert published == {f" 2026-10-{day:02d}" for day in range(1, 32)}
    assert [row.date for row in rows] == [date(2026, 10, day) for day in range(1, 32)]
    assert rows[0].measurements["depth_to_water"].value == 3.77


# --------------------------------------------------------------------------
# The points: place, kind and activity (tests 5 and 6)
# --------------------------------------------------------------------------


def test_a_point_is_placed_by_the_answers_wgs84_point_not_its_pl_1992_attributes(
    tmp_path, server, service
):
    layer = service.tables["mwp/MapServer/0"].rows
    for row in layer:
        # PL-1992 metres naming another place: a location taken from them moves.
        found = row["attributes"]
        found["WSP_X_1992"], found["WSP_Y_1992"] = (
            found["WSP_Y_1992"],
            found["WSP_X_1992"],
        )
    raw, data = roots(tmp_path)
    sync_store(raw, datasets=[POINTS])

    build_catalog(data, raw_root=raw, provider="PIG")

    points = catalog(data)
    assert {code: point.geometry for code, point in points.items()} == {
        str(row["attributes"]["ID"]): (row["geometry"]["x"], row["geometry"]["y"])
        for row in layer
    }
    assert points["6495"].geometry == OLSZYC
    assert {point.properties["location_source"] for point in points.values()} == {
        POINTS
    }


def test_a_spring_is_the_type_zrodlo_every_other_type_a_bore_and_tak_alone_active(
    groundwater_pl_roots,
):
    points = catalog(groundwater_pl_roots.data.root)

    # (groundwater_kind, the type as published, active) of each point of the layer;
    # the published flag in the comments.
    assert {
        code: (
            point.properties["groundwater_kind"],
            point.properties["hydrogeology"].get("point_type"),
            point.properties["active"],
        )
        for code, point in points.items()
        if point.properties["hydrogeology"] is not None
    } == {
        "3": ("bore", None, False),  # type " " (blank), „Nie”
        "11": ("bore", "st. wiercona", False),  # „Nie”
        "757": ("bore", "st. wiercona", True),  # „Tak”, and so on
        "853": ("bore", "st. wiercona", True),
        "1247": ("spring", "źródło", True),
        "1934": ("bore", "st. wiercona", True),
        "6495": ("bore", "st. wiercona", True),
        "6713": ("bore", "piezometr", True),
        "8269": ("bore", "st. wiercona", False),  # null
        "9312": ("bore", "piezometr", True),
        "9830": ("bore", "piezometr", True),
    }


# --------------------------------------------------------------------------
# stations find (test 16)
# --------------------------------------------------------------------------


@pytest.mark.parametrize("source", ["live", "store"])
def test_stations_find_gives_a_point_with_its_hydrogeology_and_a_filled_w(
    source, groundwater_pl_roots, server
):
    options = {"provider": "PIG", "kind": "groundwater", "source": source}
    if source == "store":
        options["root"] = groundwater_pl_roots.data.root

    envelope = run_command("stations find", options=options)

    found = {entry.station_code: entry for entry in envelope.result}
    point = found["6495"]
    assert (point.provider, point.kind, point.groundwater_kind, point.name) == (
        "PIG",
        "groundwater",
        "bore",
        "Olszyc Szlachecki",
    )
    assert (point.longitude, point.latitude) == OLSZYC
    assert {
        key: point.hydrogeology[key]
        for key in (
            "point_type",
            "confinement",
            "psh_number",
            "cbdh_number",
            "eu_code",
            "screen_top_m",
            "screen_bottom_m",
            "observed_from",
            "jcwpd",
        )
    } == {
        "point_type": "st. wiercona",
        "confinement": "Zwierciadło napięte",
        "psh_number": "II_963_1",
        "cbdh_number": "5640022",
        "eu_code": "PLGW200055_021",
        "screen_top_m": 19.9,
        "screen_bottom_m": 26.5,
        "observed_from": 2013,
        "jcwpd": 55,
    }
    # The catalog knows the points of the hourly series; the live layer does not.
    assert point.hydrogeology.get("automatic") is (True if source == "store" else None)
    # W names the year and the day the points were captured: by the variant's
    # sync, or by this search.
    lines = attribution("pig", period="2026", date="2026-11-24")
    assert lines.attribution[0] in envelope.attribution
    assert envelope.terms_notice == lines.terms_notice
