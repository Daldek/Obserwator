"""Raw-data sync and the station sources of the catalogs (ADR-015, ADR-021).

``store sync`` writes raw data only: measurement archives without series, and
the station sources the catalogs read (station lists checked by HEAD, the
current-data station metadata and hydro.imgw.pl's station details downloaded
and compared). Operational data are never archived (ADR-015 D5): of an IMGW-PIB
current-data answer or station page only the station fields of the dataset are
stored. Replayed with respx from ``recordings.json``,
``builder_recordings.json``, ``chmi_catalog_recordings.json`` and
``hydro_details_recordings.json``; the current-data answers are shaped like the
live API, with fictional stations.
"""

import hashlib
import json
import re
from pathlib import Path

import pytest
import respx

from obserwator._version import __version__
from obserwator.attribution import attribution
from obserwator.datasets import get_provider
from obserwator.exceptions import ObserwatorValidationError
from obserwator.messages import message
from obserwator.store import init_store, iter_store
from obserwator.store.series import build_series, check_series
from obserwator.store.sync import check_store, sync_store
from tests.unit.test_store_sync import H2024, V1, data, get, head, listing

FIXTURES = Path(__file__).parents[1] / "fixtures" / "store"


def _cases(name):
    document = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    base = document["base_url"].rstrip("/")
    return {
        row["case"]: {**row, "url": row.get("url") or f"{base}/{row['path']}"}
        for row in document["interactions"]
    }


IMGW = {**_cases("recordings.json"), **_cases("builder_recordings.json")}
CHMI = _cases("chmi_catalog_recordings.json")
IMGW_SOURCES = [
    "pl.imgw.hydro_stations",
    "pl.imgw.meteo_stations",
    "pl.imgw.hydro_now",
    "pl.imgw.meteo_now",
]
CHMI_SOURCES = [
    "cz.chmi.hydro_stations",
    "cz.chmi.meteo_stations",
    "cz.chmi.hydro_now",
    "cz.chmi.meteo_now",
]
HYDRO_NOW_URL = "https://danepubliczne.imgw.pl/api/data/hydro"
METEO_NOW_URL = "https://danepubliczne.imgw.pl/api/data/meteo"
METEO_NOW_LISTING = CHMI["meteo_now_listing"]["url"]

# Fields of the IMGW-PIB current-data answers never stored: measurements, their
# times and the warning and alarm levels of that answer. The levels the store
# keeps as station reference data are those of hydro.imgw.pl's station pages
# (``pl.imgw.hydro_details``, ADR-021).
HYDRO_MEASUREMENTS = frozenset(
    {
        "stan_wody",
        "stan_wody_data_pomiaru",
        "przeplyw",
        "przeplyw_data",
        "temperatura_wody",
        "temperatura_wody_data_pomiaru",
        "zjawisko_lodowe",
        "zjawisko_lodowe_data_pomiaru",
        "zjawisko_zarastania",
        "zjawisko_zarastania_data_pomiaru",
        "stan_alarmowy",
        "stan_ostrzegawczy",
    }
)
METEO_MEASUREMENTS = frozenset(
    {
        "temperatura_powietrza",
        "temperatura_powietrza_data",
        "temperatura_gruntu",
        "temperatura_gruntu_data",
        "wiatr_kierunek",
        "wiatr_kierunek_data",
        "wiatr_srednia_predkosc",
        "wiatr_srednia_predkosc_data",
        "wiatr_predkosc_maksymalna",
        "wiatr_predkosc_maksymalna_data",
        "wiatr_poryw_10min",
        "wiatr_poryw_10min_data",
        "wilgotnosc_wzgledna",
        "wilgotnosc_wzgledna_data",
        "opad_10min",
        "opad_10min_data",
    }
)
# Fields of ČHMÚ measurement files (_parsing/chmi.py): the JSON series of the
# hydrology files and the CSV columns of the climate files.
CHMI_MEASUREMENTS = frozenset(
    {"tsList", "tsConID", "tsData", "DT", "VAL", "VALUE", "TIMEFUNC", "FLAG", "QUALITY"}
)
HYDRO_KEPT = ("id_stacji", "stacja", "rzeka", "lon", "lat")
METEO_KEPT = ("kod_stacji", "nazwa_stacji", "lon", "lat")


def hydro_answer(level="226", at="2026-11-13 13:20:00"):
    """Current hydro answer like the live API: strings, stations not in code order."""
    return [
        {
            "id_stacji": "149190320",
            "stacja": "Fikcyjna Dolna",
            "rzeka": "Wymyślona",
            "wojewodztwo": "małopolskie",
            "lon": "20.4417",
            "lat": "49.8583",
            "rok_zalozenia_stacji": "1951",
            "rzedna_zerawodowskazu": "185.37",
            "kilometr_biegu_rzeki": "41.6",
            "stan_wody": level,
            "stan_wody_data_pomiaru": at,
            "przeplyw": "17.93",
            "przeplyw_data": "2026-11-13 12:10:00",
            "temperatura_wody": "6.4",
            "temperatura_wody_data_pomiaru": "2026-11-13 11:50:00",
            "zjawisko_lodowe": "11",
            "zjawisko_lodowe_data_pomiaru": "2026-11-12 07:00:00",
            "zjawisko_zarastania": "13",
            "zjawisko_zarastania_data_pomiaru": "2026-11-11 07:00:00",
            "stan_alarmowy": "380",
            "stan_ostrzegawczy": "310",
        },
        {
            "id_stacji": "149190318",
            "stacja": "Jezioro Bez Rzeki",
            "wojewodztwo": "pomorskie",
            "lon": "18.3021",
            "lat": "54.1544",
            "rok_zalozenia_stacji": "1972",
            "stan_wody": "147",
            "stan_wody_data_pomiaru": "2026-11-13 13:40:00",
            "przeplyw": None,
            "przeplyw_data": None,
            "temperatura_wody": "8.2",
            "temperatura_wody_data_pomiaru": "2026-11-13 12:30:00",
            "zjawisko_lodowe": None,
            "zjawisko_lodowe_data_pomiaru": None,
            "zjawisko_zarastania": None,
            "zjawisko_zarastania_data_pomiaru": None,
            "stan_alarmowy": "171",
            "stan_ostrzegawczy": "164",
        },
    ]


def meteo_answer(temperature="7.3", at="2026-11-13 13:00:00"):
    """Current meteo answer like the live API: strings, stations not in code order."""
    return [
        {
            "kod_stacji": "253190220",
            "nazwa_stacji": "Fikcyjne Pole",
            "lon": "19.3375",
            "lat": "53.7036",
            "wysokosc_npm": "142",
            "rok_zalozenia_stacji": "1966",
            "temperatura_powietrza": temperature,
            "temperatura_powietrza_data": at,
            "temperatura_gruntu": "5.9",
            "temperatura_gruntu_data": "2026-11-13 12:50:00",
            "wiatr_kierunek": "243",
            "wiatr_kierunek_data": "2026-11-13 12:40:00",
            "wiatr_srednia_predkosc": "3.6",
            "wiatr_srednia_predkosc_data": "2026-11-13 12:40:00",
            "wiatr_predkosc_maksymalna": "9.1",
            "wiatr_predkosc_maksymalna_data": "2026-11-13 12:40:00",
            "wiatr_poryw_10min": "11.8",
            "wiatr_poryw_10min_data": "2026-11-13 12:30:00",
            "wilgotnosc_wzgledna": "87.4",
            "wilgotnosc_wzgledna_data": "2026-11-13 12:20:00",
            "opad_10min": "0.27",
            "opad_10min_data": "2026-11-13 12:10:00",
        },
        {
            "kod_stacji": "250180120",
            "nazwa_stacji": "Wydmowa Góra",
            "lon": "18.0094",
            "lat": "50.4268",
            "wysokosc_npm": "463",
            "temperatura_powietrza": "4.8",
            "temperatura_powietrza_data": "2026-11-13 13:10:00",
            "wilgotnosc_wzgledna": "93.1",
            "wilgotnosc_wzgledna_data": "2026-11-13 13:10:00",
            "opad_10min": "1.06",
            "opad_10min_data": "2026-11-13 13:10:00",
        },
    ]


def operational(answer, fields):
    """Every measurement value and time string of an answer."""
    return {row[name] for row in answer for name in fields if row.get(name)}


def serve_imgw(server, *, hydro=None, meteo=None, list_headers=None):
    """Both station lists (HEAD and GET) and the two current-data answers."""
    for case in ("hydro_stations_get", "meteo_stations_get"):
        row = IMGW[case]
        headers = list_headers or row["headers"]
        content = (FIXTURES / "archives" / row["archive"]).read_bytes()
        server.head(row["url"]).respond(200, headers=headers)
        server.get(row["url"]).respond(200, headers=headers, content=content)
    return (
        server.get(HYDRO_NOW_URL).respond(
            200, json=IMGW["hydro_current"]["json"] if hydro is None else hydro
        ),
        server.get(METEO_NOW_URL).respond(
            200, json=IMGW["meteo_current"]["json"] if meteo is None else meteo
        ),
    )


def serve_chmi(server, *cases):
    for case in cases:
        row = CHMI[case]
        relative = (
            f"archives/{row['archive']}"
            if "archive" in row
            else row.get("variant") or row.get("listing")
        )
        content = (FIXTURES / relative).read_bytes() if relative else b""
        server.route(method=row["method"], url=row["url"]).respond(
            row["status"], headers=row["headers"], content=content
        )


CHMI_ALL = (
    "hydro_stations_head",
    "hydro_stations_get",
    "meteo_stations_head",
    "meteo_stations_get",
    "hydro_now_get",
    "hydro_meta3_get",
    "meteo_now_listing",
    "meteo_now_get",
)


def files(root):
    """Relative paths of every file and directory of the store."""
    return sorted(path.relative_to(root).as_posix() for path in root.rglob("*"))


def urls(server, method=None):
    return [
        str(call.request.url)
        for call in server.calls
        if method is None or call.request.method == method
    ]


def now_versions(root, provider):
    """Every stored version of the provider's ``*_now`` datasets with its sidecar."""
    return [
        entry
        for entry in iter_store(root, kind="archive")
        if entry.meta.dataset.startswith(provider)
        and entry.meta.dataset.endswith("_now")
    ]


@pytest.fixture
def server():
    with respx.mock(assert_all_called=False) as mock:
        yield mock


@pytest.fixture
def root(tmp_path):
    return init_store(tmp_path / "store").root


# --------------------------------------------------------------------------
# A sync writes raw data only
# --------------------------------------------------------------------------


def test_a_sync_writes_no_series_and_build_series_builds_it_afterwards(
    root, server, tmp_path
):
    listing(server, "dane_hydrologiczne/dobowe/2024", "codz_2024.zip")
    head(server, H2024, V1)
    get(server, H2024, V1, data(H2024))
    target = init_store(tmp_path / "data", kind="data").root

    report = sync_store(root, datasets=[H2024.dataset], years=[2024])

    assert [item.status for item in report.items] == ["new"]
    assert [Path(file.path) for file in report.files] == [report.items[0].version]
    assert not (root / "series").exists()
    assert list(iter_store(target)) == []
    series = check_series(target, raw_root=root, dataset=H2024.dataset)
    assert series.series_state == {"hydro_daily": "missing"}

    built = build_series(target, raw_root=root, dataset=H2024.dataset)

    assert built.status == "new"
    assert built.source_files == (report.items[0].version,)
    assert built.version.is_relative_to(target)
    series = check_series(target, raw_root=root, dataset=H2024.dataset)
    assert series.series_state == {"hydro_daily": "current"}


# --------------------------------------------------------------------------
# IMGW-PIB station sources
# --------------------------------------------------------------------------


def test_imgw_lists_are_checked_by_head_and_the_answers_without_a_request(root, server):
    serve_imgw(server)

    plan = check_store(root, datasets=IMGW_SOURCES)

    assert [(item.archive.dataset, item.status) for item in plan.items] == [
        ("pl.imgw.hydro_stations", "missing"),
        ("pl.imgw.meteo_stations", "missing"),
        ("pl.imgw.hydro_now", "unverifiable"),
        ("pl.imgw.meteo_now", "unverifiable"),
    ]
    assert (
        plan.items[2].error
        == plan.items[3].error
        == message("sync.station_source_no_signal")
    )
    assert urls(server) == [
        IMGW["hydro_stations_head"]["url"],
        IMGW["meteo_stations_head"]["url"],
    ]
    assert urls(server, "HEAD") == urls(server)

    sync_store(root, datasets=IMGW_SOURCES)
    current = check_store(root, datasets=IMGW_SOURCES)
    assert [item.status for item in current.items] == [
        "current",
        "current",
        "unverifiable",
        "unverifiable",
    ]

    republished = {
        "ETag": '"list-v2"',
        "Last-Modified": "Fri, 13 Nov 2026 06:00:00 GMT",
    }
    serve_imgw(server, list_headers=republished)
    newer = check_store(root, datasets=IMGW_SOURCES)
    assert [item.status for item in newer.items[:2]] == ["newer", "newer"]
    assert {item.remote_etag for item in newer.items[:2]} == {'"list-v2"'}


def test_imgw_sources_sync_into_four_versions_and_repeat_unchanged(root, server):
    hydro, meteo = serve_imgw(server)

    report = sync_store(root, datasets=IMGW_SOURCES)

    assert [(item.slot, item.status) for item in report.items] == [
        ("archive:pl.imgw.hydro_stations:lista_stacji_hydro.csv", "new"),
        ("archive:pl.imgw.meteo_stations:wykaz_stacji.csv", "new"),
        ("archive:pl.imgw.hydro_now:hydro", "new"),
        ("archive:pl.imgw.meteo_now:meteo", "new"),
    ]
    assert [file.status for file in report.files] == ["new"] * 4
    assert report.items[2].version.parent.parent == (
        root / "archives/versions/api/data/hydro"
    )
    assert report.items[3].version.parent.parent == (
        root / "archives/versions/api/data/meteo"
    )
    assert not (root / "series").exists() and not (root / "stations").exists()
    gets = len(urls(server, "GET"))

    again = sync_store(root, datasets=IMGW_SOURCES)

    assert [item.status for item in again.items] == ["unchanged"] * 4
    assert [item.version for item in again.items] == [
        item.version for item in report.items
    ]
    # The lists are current by HEAD; the answers are downloaded and compared.
    assert urls(server, "GET")[gets:] == [HYDRO_NOW_URL, METEO_NOW_URL]
    assert hydro.call_count == meteo.call_count == 2


# --------------------------------------------------------------------------
# ČHMÚ station sources
# --------------------------------------------------------------------------


def test_chmi_sources_check_lists_by_head_and_now_by_the_listing(root, server):
    serve_chmi(server, *CHMI_ALL)

    plan = check_store(root, datasets=CHMI_SOURCES)

    assert [
        (item.archive.dataset, item.archive.server_path, item.status)
        for item in plan.items
    ] == [
        (
            "cz.chmi.hydro_stations",
            "hydrology/historical/metadata/meta1.json",
            "missing",
        ),
        (
            "cz.chmi.meteo_stations",
            "meteorology/climate/historical/metadata/meta1.json",
            "missing",
        ),
        ("cz.chmi.hydro_now", "hydrology/now/metadata/meta1.json", "unverifiable"),
        ("cz.chmi.hydro_now", "hydrology/now/metadata/meta3.json", "unverifiable"),
        # The newest meta1 file of the listing, not meta1-20261017 or meta2-….
        (
            "cz.chmi.meteo_now",
            "meteorology/climate/now/metadata/meta1-20261018.json",
            "missing",
        ),
    ]
    assert sorted(urls(server)) == sorted(
        [
            METEO_NOW_LISTING,
            CHMI["hydro_stations_head"]["url"],
            CHMI["meteo_stations_head"]["url"],
        ]
    )
    assert urls(server, "HEAD") == [
        CHMI["hydro_stations_head"]["url"],
        CHMI["meteo_stations_head"]["url"],
    ]

    report = sync_store(root, datasets=CHMI_SOURCES)

    assert [item.status for item in report.items] == ["new"] * 5
    for item, case in zip(
        report.items,
        (
            "hydro_stations_get",
            "meteo_stations_get",
            "hydro_now_get",
            "hydro_meta3_get",
            "meteo_now_get",
        ),
        strict=True,
    ):
        expected = (FIXTURES / "archives" / CHMI[case]["archive"]).read_bytes()
        assert item.version.read_bytes() == expected  # stored verbatim
    assert [item.status for item in check_store(root, datasets=CHMI_SOURCES).items] == [
        "current",
        "current",
        "unverifiable",
        "unverifiable",
        "current",
    ]
    again = sync_store(root, datasets=CHMI_SOURCES)
    assert [item.status for item in again.items] == ["unchanged"] * 5

    # A newer daily file in the listing is missing although the older one is stored.
    newer = CHMI["meteo_now_listing"]
    body = (FIXTURES / newer["listing"]).read_text(encoding="utf-8")
    added = body.replace(
        "</pre>",
        '<a href="meta1-20261019.json">meta1-20261019.json</a>'
        "                                19-Oct-2026 00:01                 582\n</pre>",
    )
    server.get(METEO_NOW_LISTING).respond(200, headers=newer["headers"], text=added)
    (item,) = check_store(root, datasets=["cz.chmi.meteo_now"]).items
    assert (item.archive.server_path, item.status) == (
        "meteorology/climate/now/metadata/meta1-20261019.json",
        "missing",
    )


def test_an_unreadable_chmi_now_listing_fails_without_an_item(root, server):
    server.get(METEO_NOW_LISTING).respond(503)

    plan = check_store(root, datasets=["cz.chmi.meteo_now"])

    assert plan.items == ()
    assert [action.status for action in plan.actions] == ["check_failed"]
    report = sync_store(root, datasets=["cz.chmi.meteo_now"])
    assert [(item.slot, item.status, item.error_code) for item in report.items] == [
        (None, "failed", "source_unavailable")
    ]
    assert report.files == ()


# --------------------------------------------------------------------------
# Requests that mix or narrow station sources
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "datasets",
    [
        ["pl.imgw.hydro_now", "pl.imgw.hydro_daily"],
        ["cz.chmi.hydro_daily", "cz.chmi.meteo_now"],
        ["pl.imgw.meteo_stations", "cz.chmi.meteo_daily"],
    ],
)
def test_station_sources_are_not_mixed_with_measurement_datasets(
    root, server, datasets
):
    before = files(root)
    for call in (check_store, sync_store):
        with pytest.raises(ObserwatorValidationError) as error:
            call(root, datasets=datasets)
        assert error.value.code == "validation_error"
        assert error.value.localized("en") == message(
            "sync.station_sources_alone"
        ).localized("en")
        assert error.value.details["option"] == "datasets"
    assert not server.calls
    assert files(root) == before


@pytest.mark.parametrize(
    ("option", "value"),
    [("years", [2024]), ("months", [1]), ("stations", ["0-203-1-900001"])],
)
@pytest.mark.parametrize("source", ["pl.imgw.hydro_stations", "cz.chmi.hydro_now"])
def test_selectors_of_files_are_refused_with_station_sources(
    root, server, option, value, source
):
    for call in (check_store, sync_store):
        with pytest.raises(ObserwatorValidationError) as error:
            call(root, datasets=[source], **{option: value})
        assert error.value.details["reason"] == "station_sources"
        assert error.value.details["option"] == option
    assert not server.calls


@pytest.mark.parametrize("source", ["pl.imgw.meteo_now", "cz.chmi.hydro_stations"])
def test_plain_mode_refuses_station_sources(tmp_path, server, source):
    with pytest.raises(ObserwatorValidationError) as error:
        sync_store(output_dir=tmp_path / "out", datasets=[source])

    assert error.value.details["reason"] == "store_only_dataset"
    assert not server.calls
    assert not (tmp_path / "out").exists()


# --------------------------------------------------------------------------
# Operational data are never archived (ADR-015 D5)
# --------------------------------------------------------------------------


def test_an_archived_now_version_holds_no_measurement(root, server):
    hydro, meteo = hydro_answer(), meteo_answer()
    serve_imgw(server, hydro=hydro, meteo=meteo)
    serve_chmi(server, "hydro_now_get", "hydro_meta3_get", "meteo_now_listing")
    serve_chmi(server, "meteo_now_get")

    imgw = sync_store(root, datasets=["pl.imgw.hydro_now", "pl.imgw.meteo_now"])
    chmi = sync_store(root, datasets=["cz.chmi.hydro_now", "cz.chmi.meteo_now"])

    assert [item.status for item in (*imgw.items, *chmi.items)] == ["new"] * 5
    answers = {
        "pl.imgw.hydro_now": (hydro, HYDRO_KEPT, HYDRO_MEASUREMENTS),
        "pl.imgw.meteo_now": (meteo, METEO_KEPT, METEO_MEASUREMENTS),
    }
    stored = now_versions(root, "pl.imgw.")
    assert sorted(entry.meta.dataset for entry in stored) == sorted(answers)
    for entry in stored:
        answer, kept, measurements = answers[entry.meta.dataset]
        content = entry.version.read_bytes()
        rows = json.loads(content)
        assert content == (
            json.dumps(rows, ensure_ascii=False, separators=(",", ":")) + "\n"
        ).encode("utf-8")
        assert all(not set(row) & measurements for row in rows)
        for value in operational(answer, measurements):
            assert json.dumps(value, ensure_ascii=False).encode("utf-8") not in content
        codes = [row[kept[0]] for row in rows]
        assert codes == sorted(row[kept[0]] for row in answer)
        by_code = {station[kept[0]]: station for station in answer}
        assert rows == [
            {name: by_code[code][name] for name in kept if name in by_code[code]}
            for code in codes
        ]
        assert entry.meta.extra["kept_fields"] == list(kept)

    stored = now_versions(root, "cz.chmi.")
    assert sorted(entry.version.name for entry in stored) == [
        "meta1-20261018.json",
        "meta1.json",
        "meta3.json",
    ]
    for entry in stored:
        document = json.loads(entry.version.read_bytes())
        assert not set(document) & CHMI_MEASUREMENTS
        columns = document["data"]["data"]["header"].split(",")
        assert not set(columns) & CHMI_MEASUREMENTS
        assert "kept_fields" not in entry.meta.extra  # station metadata, verbatim


def test_an_answer_whose_measurements_changed_is_unchanged(root, server):
    serve_imgw(server, hydro=hydro_answer(), meteo=meteo_answer())
    first = sync_store(root, datasets=["pl.imgw.hydro_now", "pl.imgw.meteo_now"])
    slots = [item.version.parent.parent for item in first.items]

    serve_imgw(
        server,
        hydro=hydro_answer(level="231", at="2026-11-13 13:30:00"),
        meteo=meteo_answer(temperature="7.9", at="2026-11-13 13:10:00"),
    )
    again = sync_store(root, datasets=["pl.imgw.hydro_now", "pl.imgw.meteo_now"])

    assert [item.status for item in again.items] == ["unchanged", "unchanged"]
    assert [item.version for item in again.items] == [
        item.version for item in first.items
    ]
    assert [len(list(slot.iterdir())) for slot in slots] == [1, 1]

    # A station field that the store keeps is new station metadata.
    renamed = hydro_answer()
    renamed[0]["stacja"] = "Fikcyjna Dolna II"
    serve_imgw(server, hydro=renamed, meteo=meteo_answer())
    changed = sync_store(root, datasets=["pl.imgw.hydro_now"])
    assert [item.status for item in changed.items] == ["new"]
    assert "Fikcyjna Dolna II" in changed.items[0].version.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "answer",
    [
        {"json": {"status": "error", "message": "brak danych"}},
        {"json": ["149190320", "149190318"]},
        {"text": "<html>Przerwa techniczna</html>"},
    ],
    ids=["object", "list_of_codes", "html"],
)
def test_an_answer_that_is_no_list_of_stations_fails_and_writes_nothing(
    root, server, answer
):
    server.get(HYDRO_NOW_URL).respond(200, **answer)
    before = files(root)

    report = sync_store(root, datasets=["pl.imgw.hydro_now"])

    assert [(item.status, item.error_code) for item in report.items] == [
        ("failed", "data_error")
    ]
    assert report.items[0].version is None and report.files == ()
    assert files(root) == before


# --------------------------------------------------------------------------
# hydro.imgw.pl's station details (ADR-021)
# --------------------------------------------------------------------------

DETAILS_KEY = "pl.imgw.hydro_details"
DETAILS = _cases("hydro_details_recordings.json")
DETAILS_MAP = DETAILS["map"]["json"]
DETAILS_MAP_URL = DETAILS["map"]["url"]
DETAILS_URL = "https://hydro-back.imgw.pl/station/hydro/status"
# The recorded station pages by code; the backend answers null for a code it
# does not know.
DETAILS_PAGES = {
    row["url"].rpartition("=")[2]: row["json"]
    for case, row in DETAILS.items()
    if case.startswith("status_")
}
DETAILS_CODES = [station["id"] for station in DETAILS_MAP["stations"]]
# The station reference data the store keeps of a page, nested as in the answer.
DETAILS_KEPT = (
    "id",
    "properties.maximumStateValue",
    "properties.maximumStateDate",
    "properties.minimumStateValue",
    "properties.minimumStateDate",
    "properties.district",
    "properties.waterGaugeZeroOrdinate",
    "properties.waterGaugeZeroOrdinateReferrenceSystem",
    "properties.yearOfEstablishment",
    "status.riverCourseKm",
    "status.catchmentArea",
    "status.province",
    "status.alarmValue",
    "status.warningValue",
)
DETAILS_SLOT = "archives/versions/station/hydro/status"


def serve_details(server, *, pages=None, stations=None):
    """The recorded map and station pages; ``pages`` replaces answers by code."""
    stations = DETAILS_MAP["stations"] if stations is None else stations
    server.get(DETAILS_MAP_URL).respond(200, json={**DETAILS_MAP, "stations": stations})
    answers = {**DETAILS_PAGES, **(pages or {})}
    # The bytes of the answer: ``json=None`` would give an empty body, not ``null``.
    return {
        station["id"]: server.get(f"{DETAILS_URL}?id={station['id']}").respond(
            200,
            content=json.dumps(answers[station["id"]]).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        for station in stations
    }


def kept(page):
    """The kept fields of a station page, nested as in the answer."""
    row = {"id": page["id"]}
    for name in DETAILS_KEPT[1:]:
        group, _, field = name.partition(".")
        row.setdefault(group, {})[field] = page[group][field]
    return row


def other_water_states(page):
    """A later page: other water states and notices, the same reference data."""
    status = {
        **page["status"],
        "currentState": {"date": "2026-11-14T12:00:00Z", "value": 777.0},
        "previousState": {"date": "2026-11-14T11:50:00Z", "value": 776.0},
        "trend": 1,
        "status": 160,
        "notes": [{"content": "Stacja automatyczna zdewastowana", "severity": 1}],
    }
    return {**page, "stateCode": "high", "status": status}


def test_details_sync_keeps_the_reference_data_of_each_station(root, server):
    serve_details(server)
    notices = []

    report = sync_store(root, datasets=[DETAILS_KEY], on_notice=notices.append)

    assert [(item.slot, item.status) for item in report.items] == [
        (f"archive:{DETAILS_KEY}:status", "new")
    ]
    version = report.items[0].version
    content = version.read_bytes()
    assert version.name == "status"
    assert version.parent.parent == root / DETAILS_SLOT
    assert re.fullmatch(
        rf"\d{{4}}-\d{{2}}-\d{{2}}_{hashlib.sha256(content).hexdigest()[:8]}",
        version.parent.name,
    )
    rows = json.loads(content)
    assert content == (
        json.dumps(rows, ensure_ascii=False, separators=(",", ":")) + "\n"
    ).encode("utf-8")
    # Sorted by code; the map lists Kłodzko, Warszawa-Bulwary, Świnoujście.
    assert rows == [kept(DETAILS_PAGES[code]) for code in sorted(DETAILS_CODES)]
    assert rows[0] == {
        "id": "150160180",
        "properties": {
            "maximumStateValue": 890,
            "maximumStateDate": "1997-07-08",
            "minimumStateValue": 28,
            "minimumStateDate": "1950-08-31",
            "district": "kłodzki",
            "waterGaugeZeroOrdinate": 281.617,
            "waterGaugeZeroOrdinateReferrenceSystem": "EVRF2007",
            "yearOfEstablishment": "1884",
        },
        "status": {
            "riverCourseKm": 130.04,
            "catchmentArea": 1082.27,
            "province": "dolnośląskie",
            "alarmValue": 240.0,
            "warningValue": 160.0,
        },
    }
    # Water states, notices, the clause on operational data, coordinates and the
    # backend's own id never reach the store.
    for name in (
        "currentState",
        "previousState",
        "lastState",
        "notes",
        "stateCode",
        "trend",
        "coordinates",
        "dataClause",
    ):
        assert f'"{name}"'.encode() not in content, name
    assert all("id" not in row["status"] for row in rows)
    assert all(set(row) == {"id", "properties", "status"} for row in rows)

    sidecar = json.loads(version.with_name("status.meta.json").read_text("utf-8"))
    assert sidecar["license"]["url"] == "https://hydro.imgw.pl/#/regulamin"
    assert sidecar["extra"]["kept_fields"] == list(DETAILS_KEPT)

    # The map, then one page per station in map order, each with the headers
    # hydro-back.imgw.pl requires.
    assert urls(server) == [
        DETAILS_MAP_URL,
        *(f"{DETAILS_URL}?id={code}" for code in DETAILS_CODES),
    ]
    for call in server.calls:
        assert call.request.headers["Referer"] == "https://hydro.imgw.pl/"
        assert call.request.headers["User-Agent"] == f"Obserwator/{__version__}"

    # The terms of hydro.imgw.pl (RH), with the processed mark: the store keeps
    # some fields of each answer.
    (terms,) = [notice for notice in notices if notice.code == "license_terms"]
    lines = attribution("imgw_hydro", processed=True)
    assert terms.message == get_provider("IMGW-PIB").license_notice(lines)
    assert str(message("legal.imgw_terms_hydro")) in terms.message
    assert str(message("legal.imgw_processed_attribution")) in terms.message
    assert str(message("legal.imgw_terms_danepubliczne")) not in terms.message


def test_details_leave_out_a_map_station_the_backend_does_not_know(root, server):
    stations = [*DETAILS_MAP["stations"]]
    stations.insert(1, {**stations[0], "id": "999999999", "n": "NIEZNANA"})
    pages = serve_details(server, stations=stations)

    report = sync_store(root, datasets=[DETAILS_KEY])

    assert [item.status for item in report.items] == ["new"]
    assert pages["999999999"].called
    rows = json.loads(report.items[0].version.read_bytes())
    assert [row["id"] for row in rows] == sorted(DETAILS_CODES)


@pytest.mark.parametrize("failing", ["map", "152210170"])
def test_an_http_error_of_any_details_request_fails_and_writes_nothing(
    root, server, failing
):
    pages = serve_details(server)
    if failing == "map":
        server.get(DETAILS_MAP_URL).respond(503)
    else:
        server.get(f"{DETAILS_URL}?id={failing}").respond(503)
    before = files(root)

    report = sync_store(root, datasets=[DETAILS_KEY])

    assert [(item.status, item.error_code) for item in report.items] == [
        ("failed", "source_unavailable")
    ]
    assert report.items[0].version is None and report.files == ()
    assert files(root) == before
    # No request after the failed one.
    assert not pages["153140010"].called


def test_a_cancel_between_station_pages_stores_nothing(root, server):
    pages = serve_details(server)
    before = files(root)

    report = sync_store(
        root, datasets=[DETAILS_KEY], cancel=lambda: pages["150160180"].called
    )

    assert report.cancelled
    assert [item.status for item in report.items] == ["cancelled"]
    assert report.files == () and files(root) == before
    assert not pages["152210170"].called and not pages["153140010"].called


def test_details_are_unverifiable_and_unchanged_when_only_water_states_moved(
    root, server
):
    serve_details(server)

    plan = check_store(root, datasets=[DETAILS_KEY])

    assert [(item.archive.dataset, item.status) for item in plan.items] == [
        (DETAILS_KEY, "unverifiable")
    ]
    assert plan.items[0].error == message("sync.station_source_no_signal")
    assert not server.calls
    first = sync_store(root, datasets=[DETAILS_KEY])
    recheck = check_store(root, datasets=[DETAILS_KEY])
    assert [item.status for item in recheck.items] == ["unverifiable"]

    serve_details(
        server,
        pages={code: other_water_states(DETAILS_PAGES[code]) for code in DETAILS_CODES},
    )
    again = sync_store(root, datasets=[DETAILS_KEY])

    assert [item.status for item in again.items] == ["unchanged"]
    assert again.items[0].version == first.items[0].version
    assert len(list((root / DETAILS_SLOT).iterdir())) == 1

    # A changed warning level is new station reference data.
    raised = DETAILS_PAGES["152210170"]
    raised = {**raised, "status": {**raised["status"], "warningValue": 710.0}}
    serve_details(server, pages={"152210170": raised})
    changed = sync_store(root, datasets=[DETAILS_KEY])
    assert [item.status for item in changed.items] == ["new"]
    rows = json.loads(changed.items[0].version.read_bytes())
    assert rows[1]["status"]["warningValue"] == 710.0
