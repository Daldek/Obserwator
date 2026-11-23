"""ČHMÚ's groundwater (ADR-032) on real files of a bore and a spring.

The bore ``0-203-1-VP0624`` „Rakousy” and the spring ``0-203-1-PP0744`` „Želechy”,
recorded from opendata.chmi.cz on 2026-11-23 (``chmu_groundwater_recordings.json``,
the object list and ``now`` metadata also in ``chmu_catalog_recordings.json``):
the parser, weekly coverage, ``store sync`` of each archive scope, ``series build``
and ``store catalog --provider CHMU`` through the commands, and the exports of the
fixture variant ``groundwater`` (`groundwater_roots`).
"""

import csv
import io
import json
from datetime import date, timedelta
from itertools import pairwise
from pathlib import Path

import httpx
import pytest
import respx

from obserwator import export_series, export_stations, read_series
from obserwator.commands import run_command
from obserwator.coverage import summarize_coverage
from obserwator.exceptions import ObserwatorDataError, ObserwatorValidationError
from obserwator.messages import message
from obserwator.parsers import parse_chmu_groundwater
from obserwator.store import check_catalog, init_store, sync_store
from tests.contract.support import schema_errors as contract_errors
from tests.unit.test_exports import rfc7946_problems, schema_errors, table, text
from tests.unit.test_store_catalog_chmu import SOURCE_DATASETS, SOURCES
from tests.unit.test_store_catalog_chmu import serve as serve_catalog

FIXTURES = Path(__file__).parents[1] / "fixtures" / "store"
RECORDING = json.loads(
    (FIXTURES / "chmu_groundwater_recordings.json").read_text(encoding="utf-8")
)
CASES = {entry["case"]: entry for entry in RECORDING["interactions"]}
BASE = RECORDING["base_url"]
HISTORICAL = "hydrology/groundwater/historical/data"
BORE, SPRING = "0-203-1-VP0624", "0-203-1-PP0744"
DAILY, WEEKLY = "cz.chmu.groundwater_daily", "cz.chmu.groundwater_weekly"
RECENT = "cz.chmu.groundwater_recent"
CHARACTERISTIC = "cz.chmu.groundwater_characteristic"
LISTS = ("cz.chmu.groundwater_stations", "cz.chmu.groundwater_now")
LIST_CASES = ("groundwater_stations_head", "groundwater_stations_get")
NOW_CASE = "groundwater_now_get"
# The spring's daily file of 2024 as published: its last series' closing brackets
# stand once more after it (one of the files without valid JSON).
SPRING_2024 = f"H_{SPRING}_D_2024.json"
SPRING_WEEKLY = f"H_{SPRING}_W_2014.json"
BORE_WEEKLY = f"H_{BORE}_W_2012.json"


def archive(name):
    return (FIXTURES / "archives" / HISTORICAL / name).read_bytes()


def payload(entry):
    if "listing" in entry:
        return (FIXTURES / entry["listing"]).read_bytes()
    if "archive" in entry:
        return (FIXTURES / "archives" / entry["archive"]).read_bytes()
    return b""


def serve(router, *cases):
    """Answer the recorded groundwater cases (default: all of them)."""
    for case in cases or CASES:
        entry = CASES[case]
        router.route(method=entry["method"], url=BASE + entry["path"]).mock(
            return_value=httpx.Response(
                entry["status"],
                headers=entry["headers"],
                content=payload(entry) if entry["method"] == "GET" else b"",
            )
        )


def traffic(router):
    return [(call.request.method, call.request.url.path[1:]) for call in router.calls]


@pytest.fixture
def server():
    with respx.mock(assert_all_called=False) as router:
        yield router


# --------------------------------------------------------------------------
# The parser: H_<WIGOS>_<D|W>_<YYYY>.json
# --------------------------------------------------------------------------


def test_a_published_file_with_stray_closings_reads_as_the_file_without_them():
    published = archive(SPRING_2024)
    # The real file is no JSON: the closings ``]}}}`` of the two series ČHMÚ left
    # out stand before the yield series and after it.
    with pytest.raises(json.JSONDecodeError):
        json.loads(published)
    repaired = published.replace(b'"tsList":[]}}}', b'"tsList":[', 1)
    repaired = repaired[: -len(b"]}}}]}}}]}")] + b"]}}}]}"
    json.loads(repaired)

    records = list(parse_chmu_groundwater(published, filename=SPRING_2024))

    assert records == list(parse_chmu_groundwater(repaired, filename=SPRING_2024))
    assert len(records) == 366
    assert {record.dataset for record in records} == {DAILY}
    assert {tuple(record.measurements) for record in records} == {("spring_yield",)}
    last = records[-1]
    assert (last.date, last.hydro_year) == (date(2024, 12, 31), 2025)
    assert last.measurements["spring_yield"].value == 0.635


@pytest.mark.parametrize(
    "where",
    ["before the first series", "between the series", "after the last series"],
)
def test_stray_closings_anywhere_between_the_series_are_skipped(where):
    original = archive(SPRING_WEEKLY)
    head = f'{{"objID":"{SPRING}","tsList":['.encode()
    first, second = original[len(head) : -2].split(b',{"tsConID":"TT"', 1)
    second = b'{"tsConID":"TT"' + second
    stray = b"]}}}"
    body = {
        "before the first series": stray + first + b"," + second,
        "between the series": first + stray + stray + b"," + second,
        "after the last series": first + b"," + second + stray,
    }[where]

    records = list(parse_chmu_groundwater(head + body + b"]}", filename=SPRING_WEEKLY))

    assert records == list(parse_chmu_groundwater(original, filename=SPRING_WEEKLY))
    assert {tuple(record.measurements) for record in records} == {("spring_yield", "T")}


@pytest.mark.parametrize(
    ("old", "new", "path"),
    [
        # Only whole closings, commas and the end of the list may stand there: the
        # file stays the invalid JSON it is.
        (b'"tsList":[]}}}', b'"tsList":[]}}', None),
        (b"]}}}]}}}]}", b"]}}}x]}}}]}", None),
        # A weekly series is not one of a daily file.
        (b'"tsConID":"YD"', b'"tsConID":"YT"', "tsList[0]"),
    ],
)
def test_other_broken_text_or_a_series_of_the_other_kind_is_refused(old, new, path):
    published = archive(SPRING_2024)
    assert published.count(old) == 1

    with pytest.raises(ObserwatorDataError) as error:
        list(parse_chmu_groundwater(published.replace(old, new), filename=SPRING_2024))

    assert SPRING_2024 in str(error.value)
    assert (path or "Invalid JSON") in str(error.value)


def test_a_weekly_file_keeps_each_reading_at_its_own_date():
    records = list(parse_chmu_groundwater(archive(BORE_WEEKLY), filename=BORE_WEEKLY))

    days = [record.date for record in records]
    assert (len(days), days[0], days[-1]) == (52, date(2012, 1, 1), date(2012, 12, 23))
    # Readings a week apart, on the object's own day (Sundays here), never Mondays.
    assert {later - earlier for earlier, later in pairwise(days)} == {timedelta(days=7)}
    assert {record.dataset for record in records} == {WEEKLY}
    assert {tuple(record.measurements) for record in records} == {("H_asl",)}
    assert records[0].measurements["H_asl"].value == 257.91


# --------------------------------------------------------------------------
# Weekly coverage: calendar weeks named by their Mondays
# --------------------------------------------------------------------------


def test_weekly_coverage_counts_calendar_weeks_named_by_their_mondays():
    records = list(parse_chmu_groundwater(archive(BORE_WEEKLY), filename=BORE_WEEKLY))
    # Two readings left out: Sunday 4 and Sunday 11 March 2012.
    lost = (date(2012, 3, 4), date(2012, 3, 11))
    kept = [record for record in records if record.date not in lost]

    full = {c.variable: c for c in summarize_coverage(records, dataset=WEEKLY)}
    gapped = {c.variable: c for c in summarize_coverage(kept, dataset=WEEKLY)}

    level = full["H_asl"]
    assert (level.first, level.last, level.with_value, level.gaps) == (
        date(2012, 1, 1),
        date(2012, 12, 23),
        52,
        (),
    )
    # The two weeks Monday 27 February – Sunday 11 March, named by their Mondays.
    assert gapped["H_asl"].gaps == ((date(2012, 2, 27), date(2012, 3, 5)),)
    assert gapped["H_asl"].with_value == 50
    assert (full["spring_yield"].with_value, full["spring_yield"].gaps) == (0, ())


def test_the_weekly_series_has_rows_only_at_the_readings(groundwater_roots):
    data = groundwater_roots.data.root
    parsed = list(parse_chmu_groundwater(archive(BORE_WEEKLY), filename=BORE_WEEKLY))

    rows = list(read_series(root=data, dataset=WEEKLY, station=BORE))
    index = json.loads(
        next((data / "series" / "versions" / "chmu_groundwater_weekly").glob("*"))
        .joinpath("series.json")
        .read_text(encoding="utf-8")
    )

    assert [row.date for row in rows] == [record.date for record in parsed]
    assert [row.measurements["H_asl"].value for row in rows] == [
        record.measurements["H_asl"].value for record in parsed
    ]
    level = index["stations"][BORE]["variables"]["H_asl"]
    assert (level["first"], level["last"], level["with_value"], level["gaps"]) == (
        "2012-01-01",
        "2012-12-23",
        52,
        [],
    )
    assert index["stations"][SPRING]["rows"] == 48


# --------------------------------------------------------------------------
# store sync: station × year, station × month and one file per station
# --------------------------------------------------------------------------


def test_sync_of_a_bore_and_a_spring_writes_their_files_with_the_server_signals(
    tmp_path, server
):
    serve(server)
    raw = init_store(tmp_path / "raw")

    synced = run_command(
        "store sync",
        options={
            "root": raw.root,
            "datasets": [DAILY],
            "stations": [BORE, SPRING],
            "years": [2024],
        },
    )

    assert synced.status == "ok"
    assert traffic(server) == [
        ("GET", f"{HISTORICAL}/"),
        ("HEAD", f"{HISTORICAL}/H_{SPRING}_D_2024.json"),
        ("GET", f"{HISTORICAL}/H_{SPRING}_D_2024.json"),
        ("HEAD", f"{HISTORICAL}/H_{BORE}_D_2024.json"),
        ("GET", f"{HISTORICAL}/H_{BORE}_D_2024.json"),
    ]
    items = {item.slot: item for item in synced.result.items}
    assert {slot: item.status for slot, item in items.items()} == {
        f"archive:{DAILY}:H_{SPRING}_D_2024.json": "new",
        f"archive:{DAILY}:H_{BORE}_D_2024.json": "new",
    }
    bore = items[f"archive:{DAILY}:H_{BORE}_D_2024.json"].version
    assert bore.read_bytes() == archive(f"H_{BORE}_D_2024.json")
    meta = json.loads(Path(f"{bore}.meta.json").read_text(encoding="utf-8"))
    assert contract_errors(meta, "obserwator-meta/1") == []
    assert meta["extra"]["http"] == {
        "url": f"{BASE}{HISTORICAL}/H_{BORE}_D_2024.json",
        "etag": '"68ca9e12-2e10"',
        "last_modified": "Wed, 17 Sep 2025 11:40:02 GMT",
        "content_length": 11792,
    }
    assert meta["extra"]["version"] == {
        "label": "2025-09-17",
        "label_source": "last_modified",
    }
    assert meta["request"]["station_code"] == BORE


def test_recent_months_without_years_are_the_months_of_the_listing(tmp_path, server):
    serve(server)
    raw = init_store(tmp_path / "raw")

    listed = sync_store(raw, datasets=[RECENT], stations=[BORE])
    calls = traffic(server)
    every = sync_store(raw, datasets=[RECENT], stations=[BORE], years=[2026])

    month = f"hydrology/groundwater/recent/data/{BORE}_D_202610.json"
    assert calls == [
        ("GET", "hydrology/groundwater/recent/data/"),
        ("HEAD", month),
        ("GET", month),
    ]
    assert [(item.slot, item.status) for item in listed.items] == [
        (f"archive:{RECENT}:{BORE}_D_202610.json", "new")
    ]
    meta = json.loads(
        Path(f"{listed.items[0].version}.meta.json").read_text(encoding="utf-8")
    )
    assert (meta["request"]["year"], meta["request"]["month"]) == (2026, 10)
    # A year asks for its twelve months: the listed one is now stored, the others
    # are not published, and none is requested.
    assert traffic(server)[len(calls) :] == [
        ("GET", "hydrology/groundwater/recent/data/")
    ]
    assert [item.status for item in every.items] == ["unchanged"] * 12
    assert [item.version is not None for item in every.items].count(True) == 1


def test_characteristics_are_one_file_per_object_and_take_no_years(tmp_path, server):
    serve(server)
    raw = init_store(tmp_path / "raw")

    with pytest.raises(ObserwatorValidationError) as error:
        sync_store(raw, datasets=[CHARACTERISTIC], stations=[BORE], years=[2024])
    assert not server.calls
    synced = sync_store(raw, datasets=[CHARACTERISTIC], stations=[BORE, SPRING])

    assert error.value.details == {"option": "years", "value": CHARACTERISTIC}
    assert [(item.slot, item.status) for item in synced.items] == [
        (f"archive:{CHARACTERISTIC}:GCHAR_{SPRING}.json", "new"),
        (f"archive:{CHARACTERISTIC}:GCHAR_{BORE}.json", "new"),
    ]
    version = synced.items[1].version
    assert version.parent.parent.relative_to(raw.root).as_posix() == (
        f"archives/versions/hydrology/groundwater/characteristic/data/GCHAR_{BORE}"
    )
    meta = json.loads(Path(f"{version}.meta.json").read_text(encoding="utf-8"))
    assert (meta["request"]["year"], meta["request"]["station_code"]) == (None, BORE)
    assert meta["extra"]["http"]["etag"] == '"67af4d93-166c"'


# --------------------------------------------------------------------------
# series build and store catalog --provider CHMU through the commands
# --------------------------------------------------------------------------


def _synced(tmp_path, *, lists: bool):
    """Raw root with the ČHMÚ station sources and the daily files of both objects."""
    raw = init_store(tmp_path / "raw")
    with respx.mock(assert_all_called=False) as router:
        serve(router)
        serve_catalog(router, *SOURCES, *LIST_CASES, NOW_CASE)
        datasets = [*SOURCE_DATASETS, *(LISTS if lists else ())]
        sources = sync_store(raw, datasets=datasets)
        files = sync_store(raw, datasets=[DAILY], stations=[BORE, SPRING], years=[2024])
    assert {item.status for item in (*sources.items, *files.items)} == {"new"}
    return raw.root, init_store(tmp_path / "data", kind="data").root


def test_series_build_and_catalog_of_a_bore_and_a_spring(tmp_path):
    raw, data = _synced(tmp_path, lists=True)
    roots = {"root": data, "raw_root": raw}

    with respx.mock(assert_all_mocked=True) as offline:
        built = run_command("series build", options={**roots, "dataset": DAILY})
        catalog = run_command("store catalog", options={**roots, "provider": "CHMU"})
        planned = check_catalog(data, raw_root=raw, provider="CHMU")
    assert not offline.calls

    assert (built.status, built.result.status) == ("ok", "new")
    level = list(read_series(root=data, dataset=DAILY, station=BORE))
    flow = list(read_series(root=data, dataset=DAILY, station=SPRING))
    assert (len(level), len(flow)) == (366, 366)
    assert level[0].measurements["H_asl"].value is not None
    assert "H_asl" not in flow[0].measurements or (
        flow[0].measurements["H_asl"].value is None
    )
    assert flow[-1].measurements["spring_yield"].value == 0.635
    assert (catalog.status, catalog.result.status) == ("ok", "new")
    features = {
        feature["id"]: feature
        for feature in json.loads(catalog.result.version.read_text(encoding="utf-8"))[
            "features"
        ]
    }
    for code, kind, name, point, elevation in (
        (BORE, "bore", "Rakousy", [15.1832503, 50.6259733], 261.22),
        (SPRING, "spring", "Želechy", [15.3798331, 50.5518065], 440),
    ):
        properties = features[code]["properties"]
        assert (properties["kind"], properties["groundwater_kind"]) == (
            "groundwater",
            kind,
        )
        assert (properties["name"], properties["elevation_m"]) == (name, elevation)
        assert properties["location_source"] == "cz.chmu.groundwater_now"
        assert properties["active"] is True
        assert features[code]["geometry"]["coordinates"] == point
    others = [f for f in features.values() if f["properties"]["kind"] != "groundwater"]
    assert others
    assert not [f for f in others if "groundwater_kind" in f["properties"]]
    assert [action.status for action in planned.actions] == ["current"] * 9


def test_a_catalog_without_the_object_lists_keeps_the_series_and_says_so(tmp_path):
    raw, data = _synced(tmp_path, lists=False)
    run_command(
        "series build", options={"root": data, "raw_root": raw, "dataset": DAILY}
    )
    notices = []

    with respx.mock(assert_all_mocked=True):
        first = run_command(
            "store catalog",
            options={"root": data, "raw_root": raw, "provider": "CHMU"},
            on_notice=notices.append,
        )
    features = {
        f["id"]: f
        for f in json.loads(first.result.version.read_text(encoding="utf-8"))[
            "features"
        ]
    }

    assert first.result.status == "new"
    assert message(
        "catalog.groundwater_sources_missing", raw=raw, datasets=",".join(LISTS)
    ) in [notice.message for notice in notices if notice.code == "source_missing"]
    # The objects of the series stay, as groundwater objects without a name, a
    # kind of object or a location from the lists.
    for code in (BORE, SPRING):
        properties = features[code]["properties"]
        assert properties["kind"] == "groundwater"
        assert properties["groundwater_kind"] is None
        assert (properties["name"], properties["active"]) == ("", False)
        assert features[code]["geometry"] is None

    # The lists appear in the raw root: the check names them newer, and the next
    # build takes the names, kinds and locations from them.
    with respx.mock(assert_all_called=False) as router:
        serve_catalog(router, *LIST_CASES, NOW_CASE)
        sync_store(raw, datasets=list(LISTS))
    planned = check_catalog(data, raw_root=raw, provider="CHMU")
    with respx.mock(assert_all_mocked=True):
        second = run_command(
            "store catalog", options={"root": data, "raw_root": raw, "provider": "CHMU"}
        )
    assert [action.status for action in planned.actions[5:7]] == ["newer", "newer"]
    assert second.result.status == "new"
    located = {
        f["id"]: f["properties"]
        for f in json.loads(second.result.version.read_text(encoding="utf-8"))[
            "features"
        ]
    }
    assert (located[BORE]["groundwater_kind"], located[SPRING]["groundwater_kind"]) == (
        "bore",
        "spring",
    )


# --------------------------------------------------------------------------
# Exports of the fixture variant
# --------------------------------------------------------------------------


def test_stations_export_of_the_groundwater_kind_names_bores_and_springs(
    groundwater_roots,
):
    data = groundwater_roots.data.root

    document = json.loads(text(export_stations(data, kind="groundwater")))
    rows = table(export_stations(data, kind="groundwater", format="csv"))
    hydro = next(
        csv.reader(io.StringIO(text(export_stations(data, kind="hydro", format="csv"))))
    )

    assert rfc7946_problems(document) == []
    assert schema_errors(document, "obserwator-stations-export-1") == []
    kinds = {
        f["id"]: (f["properties"]["kind"], f["properties"]["groundwater_kind"])
        for f in document["features"]
    }
    assert kinds == {BORE: ("groundwater", "bore"), SPRING: ("groundwater", "spring")}
    assert {(row["station_code"], row["groundwater_kind"]) for row in rows} == {
        (BORE, "bore"),
        (SPRING, "spring"),
    }
    assert {row["kind"] for row in rows} == {"groundwater"}
    # The column belongs to an export with a groundwater object only.
    assert "groundwater_kind" not in hydro
    series = {item["dataset"] for item in document["series"]}
    assert series == {DAILY, WEEKLY}


def test_series_export_json_of_a_weekly_series_says_week_and_meets_its_schema(
    groundwater_roots,
):
    data = groundwater_roots.data.root

    document = json.loads(
        text(export_series(root=data, dataset=WEEKLY, station=SPRING, format="json"))
    )

    assert schema_errors(document, "obserwator-series-export-1") == []
    assert (document["dataset"], document["time_unit"]) == (WEEKLY, "week")
    days = [date.fromisoformat(day) for day in document["columns"]["date"]]
    assert (len(days), days[0], days[-1]) == (48, date(2014, 2, 7), date(2014, 12, 31))
    assert document["variables"]["spring_yield"]["unit"] == "l/s"
    assert len(document["columns"]["spring_yield"]) == len(days)
