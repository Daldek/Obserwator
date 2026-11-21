"""Offline tests for find_stations and fetch_hydro_states (respx-mocked HTTP)."""

import pytest
import respx

from obserwator._version import __version__
from obserwator.datasets import station_source_files
from obserwator.exceptions import (
    ObserwatorDataError,
    ObserwatorStoreError,
    ObserwatorValidationError,
)
from obserwator.stations import (
    HYDRO_MAP_API_URL,
    fetch_hydro_states,
    fetch_hydro_states_async,
    find_stations,
    find_stations_async,
)
from obserwator.store import init_store
from obserwator.testing import build_fixture_store

HYDRO_URL, METEO_URL = (file.url for file in station_source_files())
HYDRO_API_URL = "https://danepubliczne.imgw.pl/api/data/hydro"
METEO_API_URL = "https://danepubliczne.imgw.pl/api/data/meteo"
HYDRO_CSV = (
    '"150190340","ŁÓDŹ ZACHÓD","Ner (18)","1"\n'
    '"149190310","RABA GÓRNA","Raba (2138)","2"\n'
    '"149190300","SAN ESCOBAR","Łódka (2139)",""\n'
)
METEO_CSV = (
    '"251190470","ŁÓDŹ WSCHÓD","LW"\n'
    '"249190310","RABA GÓRNA","GR"\n'
    '"249190310","RABA GÓRNA","GR2"\n'
)
# Current-data API answers: coordinates as texts (as IMGW-PIB publishes them) or
# numbers; SAN ESCOBAR and the meteo RABA GÓRNA are not reported, a row without a
# point and a code off the list are ignored.
HYDRO_API = [
    {"id_stacji": "150190340", "stacja": "ŁÓDŹ", "lat": "51.7592", "lon": "19.4560"},
    {"id_stacji": "149190310", "stacja": "RABA GÓRNA", "lat": 49.61, "lon": 20.05},
    {"id_stacji": "149190399", "stacja": "POZA LISTĄ", "lat": "50.0", "lon": "20.0"},
]
METEO_API = [
    {"kod_stacji": "251190470", "nazwa_stacji": "ŁÓDŹ", "lat": "51.72", "lon": "19.40"},
    {"kod_stacji": "249190310", "nazwa_stacji": "RABA", "lat": None, "lon": None},
]
MAP_PAYLOAD = {
    "stations": [
        {
            "id": 149190310,
            "n": "RABA GÓRNA",
            "rzeka": "Raba",
            "la": 49.61,
            "lo": 20.05,
            "s": "high",
        },
        {"id": "149190311", "n": "SAN ESCOBAR", "la": "brak", "lo": 20.1},
        {"n": "BEZ KODU", "la": 50.0, "lo": 20.0},
        {"id": "149190312", "n": "ŻABIE", "s": "low"},
    ]
}


@pytest.fixture
def lists(respx_mock):
    """Serve both live station lists in CP1250 and the current-data API answers."""
    return (
        respx_mock.get(HYDRO_URL).respond(content=HYDRO_CSV.encode("cp1250")),
        respx_mock.get(METEO_URL).respond(content=METEO_CSV.encode("cp1250")),
        respx_mock.get(HYDRO_API_URL).respond(json=HYDRO_API),
        respx_mock.get(METEO_API_URL).respond(json=METEO_API),
    )


def _rows(stations):
    return [(s.kind, s.station_code, s.name) for s in stations]


# --------------------------------------------------------------------------
# find_stations, live lists
# --------------------------------------------------------------------------


def test_find_stations_without_query_returns_both_lists_in_order(lists):
    stations = find_stations(provider="IMGW-PIB")

    assert _rows(stations) == [
        ("hydro", "150190340", "ŁÓDŹ ZACHÓD"),
        ("hydro", "149190310", "RABA GÓRNA"),
        ("hydro", "149190300", "SAN ESCOBAR"),
        ("meteo", "251190470", "ŁÓDŹ WSCHÓD"),
        ("meteo", "249190310", "RABA GÓRNA"),
        ("meteo", "249190310", "RABA GÓRNA"),
    ]
    assert [s.short_code for s in stations[-2:]] == ["GR", "GR2"]
    assert (stations[1].river, stations[1].hydrographic_code) == ("Raba", "2138")


async def test_live_imgw_stations_carry_the_coordinates_of_the_current_data_api(
    lists,
):
    stations = find_stations(provider="IMGW-PIB")

    assert [(s.station_code, s.latitude, s.longitude) for s in stations] == [
        ("150190340", 51.7592, 19.456),
        ("149190310", 49.61, 20.05),
        # Listed, but not reported by the API: no coordinates.
        ("149190300", None, None),
        ("251190470", 51.72, 19.4),
        ("249190310", None, None),
        ("249190310", None, None),
    ]
    assert await find_stations_async(provider="IMGW-PIB") == stations


def test_a_live_api_answer_that_is_no_list_is_a_data_error(respx_mock):
    respx_mock.get(HYDRO_URL).respond(content=HYDRO_CSV.encode("cp1250"))
    respx_mock.get(HYDRO_API_URL).respond(json={"message": "brak"})

    with pytest.raises(ObserwatorDataError) as error:
        find_stations(kind="hydro", provider="IMGW-PIB")
    assert error.value.details == {"url": HYDRO_API_URL}


async def test_bbox_keeps_the_located_stations_inside_it_bounds_included(lists):
    # West and north are exactly ŁÓDŹ ZACHÓD's longitude and latitude; ŁÓDŹ
    # WSCHÓD (19.40 E) lies just west of the area.
    lodz = (19.456, 51.5, 20.0, 51.7592)

    stations = find_stations(provider="IMGW-PIB", bbox=lodz)

    assert _rows(stations) == [("hydro", "150190340", "ŁÓDŹ ZACHÓD")]
    # Stations without coordinates are never inside an area, even all of it.
    world = find_stations(provider="IMGW-PIB", bbox=[-180, -90, 180, 90])
    assert [s.station_code for s in world] == ["150190340", "149190310", "251190470"]
    assert (
        await find_stations_async(provider="IMGW-PIB", query="lodz", bbox=lodz)
        == stations
    )


@pytest.mark.parametrize(
    "query, expected",
    [
        # Name without Polish characters, any case.
        ("lodz", [("hydro", "150190340"), ("meteo", "251190470")]),
        ("  ŁÓDŹ ", [("hydro", "150190340"), ("meteo", "251190470")]),
        # River fragment (Ner) and river with Polish characters (Łódka).
        ("ner", [("hydro", "150190340")]),
        ("lodka", [("hydro", "149190300")]),
        # Code prefix; ordered by name, not by code.
        ("1491903", [("hydro", "149190310"), ("hydro", "149190300")]),
        # A code fragment that is not a prefix does not match.
        ("9190", []),
    ],
)
def test_find_stations_matches_name_river_and_code_prefix(lists, query, expected):
    stations = find_stations(query=query, provider="IMGW-PIB")
    assert [(s.kind, s.station_code) for s in stations] == expected


async def test_find_stations_kind_requests_only_its_list(respx_mock):
    meteo = respx_mock.get(METEO_URL).respond(content=METEO_CSV.encode("cp1250"))
    meteo_api = respx_mock.get(METEO_API_URL).respond(json=METEO_API)

    stations = find_stations(kind="meteo", query="raba", provider="IMGW-PIB")

    assert _rows(stations) == [("meteo", "249190310", "RABA GÓRNA")] * 2
    assert (
        await find_stations_async(kind="meteo", query="raba", provider="IMGW-PIB")
        == stations
    )
    assert (meteo.call_count, meteo_api.call_count) == (2, 2)


@pytest.mark.parametrize(
    "kwargs, option",
    [
        ({"kind": "synop"}, "kind"),
        ({"source": "archive"}, "source"),
        ({"source": "store"}, "root"),
        ({"root": "data/store"}, "root"),
        ({"query": "   "}, "query"),
        # Three numbers, west east of east, south north of north, latitude
        # beyond 90, longitude beyond 180, not a number, a boolean, a text.
        ({"bbox": (16.5, 51.3, 17.9)}, "bbox"),
        ({"bbox": (17.9, 51.3, 16.5, 51.7)}, "bbox"),
        ({"bbox": (16.5, 51.7, 17.9, 51.3)}, "bbox"),
        ({"bbox": (16.5, 51.3, 17.9, 91.0)}, "bbox"),
        ({"bbox": (-181.0, 51.3, 17.9, 51.7)}, "bbox"),
        ({"bbox": (16.5, float("nan"), 17.9, 51.7)}, "bbox"),
        ({"bbox": (16.5, True, 17.9, 51.7)}, "bbox"),
        ({"bbox": "16.5,51.3,17.9,51.7"}, "bbox"),
    ],
)
async def test_find_stations_invalid_options_are_validation_errors(
    respx_mock, kwargs, option
):
    with pytest.raises(ObserwatorValidationError) as error:
        find_stations(**kwargs)
    with pytest.raises(ObserwatorValidationError):
        await find_stations_async(**kwargs)

    assert error.value.code == "validation_error"
    assert error.value.details["option"] == option
    assert not respx_mock.calls


# --------------------------------------------------------------------------
# find_stations, stored catalogs
# --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def fixture_store(tmp_path_factory):
    """The data root of the ``complete`` fixture: an IMGW-PIB catalog only."""
    base = tmp_path_factory.mktemp("fixture")
    return build_fixture_store(base / "raw", data_root=base / "data").data.root


async def test_find_stations_store_reads_catalog_coordinates_offline(fixture_store):
    with respx.mock(assert_all_called=False) as router:
        stations = find_stations(source="store", root=fixture_store)
        async_stations = await find_stations_async(source="store", root=fixture_store)

    assert not router.calls
    assert async_stations == stations
    located = {
        s.station_code: (s.latitude, s.longitude)
        for s in stations
        if s.latitude is not None
    }
    assert located == {"149190310": (49.7, 20.1), "123750000": (52.23, 21.01)}
    # Catalog features with geometry=null leave the coordinates empty.
    unlocated = {s.station_code for s in stations if s.latitude is None}
    assert {"149190311", "149190312", "123760000"} <= unlocated
    assert [s.kind for s in stations] == sorted(
        (s.kind for s in stations), key=("hydro", "meteo").index
    )
    # The entry carries what the catalog feature knows; a catalog has no short code.
    (raba,) = [s for s in stations if s.station_code == "149190310"]
    assert (
        raba.name,
        raba.river,
        raba.hydrographic_code,
        raba.river_order,
        raba.short_code,
        raba.provider,
    ) == ("Raba Górna", "Raba", "213", 12, None, "IMGW-PIB")


def test_find_stations_store_filters_like_live(fixture_store):
    with respx.mock(assert_all_called=False) as router:
        stations = find_stations(
            kind="hydro", query="bez miejsca", root=fixture_store, source="store"
        )

    assert not router.calls
    assert [(s.station_code, s.latitude) for s in stations] == [("149190312", None)]


def test_find_stations_store_bbox_leaves_out_stations_without_geometry(
    fixture_store,
):
    with respx.mock(assert_all_called=False) as router:
        stations = find_stations(
            source="store", root=fixture_store, bbox=(19.0, 49.0, 21.0, 50.0)
        )

    assert not router.calls
    assert [(s.station_code, s.latitude, s.longitude) for s in stations] == [
        ("149190310", 49.7, 20.1)
    ]


def test_find_stations_store_skips_a_provider_without_a_catalog_unless_named(
    fixture_store,
):
    assert {s.provider for s in find_stations(source="store", root=fixture_store)} == {
        "IMGW-PIB"
    }
    with pytest.raises(ObserwatorStoreError) as error:
        find_stations(source="store", root=fixture_store, provider="CHMI")
    assert error.value.code == "not_found"
    assert "store catalog --provider CHMI" in error.value.hint


def test_find_stations_store_reads_the_catalog_of_every_provider(fixture_root):
    stations = find_stations(source="store", root=fixture_root)
    chmi = find_stations(source="store", root=fixture_root, provider="CHMI")

    assert {s.provider for s in stations} == {"IMGW-PIB", "CHMI"}
    assert chmi == tuple(s for s in stations if s.provider == "CHMI")


def test_find_stations_store_without_catalogs_is_not_found(tmp_path):
    root = init_store(tmp_path / "data", kind="data").root
    with pytest.raises(ObserwatorStoreError) as error:
        find_stations(source="store", root=root)
    assert error.value.code == "not_found"
    assert "store catalog" in error.value.hint


def test_find_stations_store_refuses_a_raw_root(tmp_path):
    root = init_store(tmp_path / "raw").root
    with pytest.raises(ObserwatorStoreError) as error:
        find_stations(source="store", root=root)
    assert error.value.details == {"reason": "wrong_root", "kind": "data"}


# --------------------------------------------------------------------------
# fetch_hydro_states
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "kwargs, only_main", [({}, "false"), ({"main_only": True}, "true")]
)
async def test_fetch_hydro_states_sends_headers_and_main_only(
    respx_mock, kwargs, only_main
):
    route = respx_mock.get(HYDRO_MAP_API_URL).respond(json=MAP_PAYLOAD)

    states = fetch_hydro_states(**kwargs)
    assert await fetch_hydro_states_async(**kwargs) == states

    for call in route.calls:
        request = call.request
        assert request.url.params["onlyMainStations"] == only_main
        assert "Referer" not in request.headers
        assert request.headers["User-Agent"] == (
            f"Obserwator/{__version__} (+https://github.com/Daldek/Obserwator)"
        )


def test_fetch_hydro_states_reads_river_and_skips_invalid_stations(respx_mock):
    respx_mock.get(HYDRO_MAP_API_URL).respond(json=MAP_PAYLOAD)

    states = fetch_hydro_states()

    assert [s.model_dump() for s in states] == [
        {
            "station_code": "149190310",
            "name": "RABA GÓRNA",
            "river": "Raba",
            "latitude": 49.61,
            "longitude": 20.05,
            "water_state": "high",
        },
        {
            "station_code": "149190312",
            "name": "ŻABIE",
            "river": None,
            "latitude": None,
            "longitude": None,
            "water_state": "low",
        },
    ]


@pytest.mark.parametrize(
    "payload, expected",
    [
        (MAP_PAYLOAD["stations"][:1], ["149190310"]),
        ({"numOfAlarmStates": 0}, []),
    ],
)
def test_fetch_hydro_states_accepts_list_and_empty_wrapper(
    respx_mock, payload, expected
):
    respx_mock.get(HYDRO_MAP_API_URL).respond(json=payload)
    assert [s.station_code for s in fetch_hydro_states()] == expected


def test_fetch_hydro_states_rejects_non_list_stations(respx_mock):
    respx_mock.get(HYDRO_MAP_API_URL).respond(json={"stations": "brak"})
    with pytest.raises(ObserwatorDataError, match="a list of stations was expected"):
        fetch_hydro_states()
