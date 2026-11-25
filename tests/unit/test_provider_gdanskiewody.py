"""The adapter of Gdańskie Wody (ADR-034): requests, errors, month files, catalog, search.

Every request is answered from ``gdanskiewody_recordings.json``
(`obserwator.testing._recorded_http`, recorded on 2026-11-25) or by a fake transport.
Each test has a dummy key, its own working directory (no ``.env``), ``nogat.toml`` and
state directory, a fresh pace and a fake clock (`obserwator.fetch._clock`) that moves
only when the adapter waits, so no test sleeps; today is 2026-11-03 (UTC).
"""

import json
import os
from contextlib import contextmanager
from datetime import UTC, date, datetime, timedelta
from email.utils import parsedate_to_datetime
from itertools import pairwise
from unittest import mock

import httpx
import pydantic
import pytest
import respx

from obserwator import fetch
from obserwator._parsing.gdanskiewody import encode_month, read_month
from obserwator.commands import run_command
from obserwator.config import Settings
from obserwator.datasets import ArchiveFile, archive_files, get_dataset
from obserwator.exceptions import (
    ObserwatorCancelledError,
    ObserwatorDataError,
    ObserwatorError,
    ObserwatorStoreError,
    ObserwatorValidationError,
)
from obserwator.fetch import _IDENTIFY, DownloadResult
from obserwator.messages import message
from obserwator.providers.pl import gdanskiewody
from obserwator.providers.pl.gdanskiewody import ADAPTER
from obserwator.stations import find_stations, find_stations_async
from obserwator.store import (
    build_catalog,
    build_series,
    init_store,
    read_catalog,
    write_archive,
)
from obserwator.store.types import PlanAction
from obserwator.testing import _interactions, _recorded_http
from tests.unit.test_paced import FakeClock
from tests.unit.test_parsing_gdanskiewody import hours
from tests.unit.test_stations_chmu import IMGW_API, IMGW_HYDRO, IMGW_HYDRO_CSV
from tests.unit.test_store_catalog_chmu import serve as serve_chmu

RECORDINGS = ("gdanskiewody_recordings.json",)
CASES = _interactions(RECORDINGS)
KEY = "gw-test-key-0123456789abcdef"
BASE = "https://pomiary.gdanskiewody.pl/rest"
STATIONS = f"{BASE}/stations"
NOW = datetime(2026, 11, 3, 12, tzinfo=UTC)
TODAY = NOW.date()
SETTLED = datetime(2026, 12, 1, 12, tzinfo=UTC)
LIST = get_dataset("pl.gdanskiewody.station_list")
MEASUREMENTS = get_dataset("pl.gdanskiewody.measurements")
SERIES = (
    "pl.gdanskiewody.hydro_hourly",
    "pl.gdanskiewody.meteo_hourly",
    "pl.gdanskiewody.hydro_daily",
    "pl.gdanskiewody.meteo_daily",
)
WATER_QUALITY = ("turbidity", "dissolvedoxygen", "redox", "ph", "conductivity")
MISSING_KEY = (
    "forbidden",
    {"reason": "missing_credentials", "provider": "GDANSKIEWODY"},
)
REFUSED_KEY = (
    "forbidden",
    {"reason": "invalid_credentials", "provider": "GDANSKIEWODY"},
)


@pytest.fixture(autouse=True)
def environment(tmp_path, monkeypatch):
    """A dummy key and nothing of the machine: no setting, ``.env`` or spool; a fresh pace."""
    for name in list(os.environ):
        if name.startswith("OBSERWATOR_GDANSKIE_WODY_"):
            monkeypatch.delenv(name)
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)
    config = tmp_path / "nogat.toml"
    config.write_text("", encoding="utf-8")
    monkeypatch.setenv("NOGAT_CONFIG", str(config))
    monkeypatch.setenv("OBSERWATOR_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("OBSERWATOR_GDANSKIE_WODY_API_KEY", KEY)
    monkeypatch.setattr(gdanskiewody, "_PACE", gdanskiewody._Pace())


@pytest.fixture(autouse=True)
def clock(monkeypatch):
    fake = FakeClock(NOW)
    monkeypatch.setattr(fetch, "_clock", lambda: fake)
    return fake


@contextmanager
def recorded(clock, *cases):
    """Answer ``cases`` from the recordings; note each request with the clock's time."""
    sent = []
    with _recorded_http(cases, recordings=RECORDINGS):
        answer = httpx.HTTPTransport.handle_request

        def note(transport, request):
            sent.append((clock.now(), request))
            return answer(transport, request)

        with mock.patch.object(httpx.HTTPTransport, "handle_request", note):
            yield sent


def days(station, symbol):
    """The recorded cases of a station's quantity on 2026-11-01 to 2026-11-03."""
    return [f"m_{station}_{symbol}_2026110{day}" for day in (1, 2, 3)]


def recorded_month(station, symbol):
    """The month file the recorded days of a station's quantity give."""
    return encode_month(
        {
            date(2026, 11, day): CASES[case]["json"]
            for day, case in zip((1, 2, 3), days(station, symbol), strict=True)
        }
    )


def month_file(station, symbol, year=2026, month=11):
    archive = ADAPTER.archive_from_path(
        MEASUREMENTS, f"rest/measurements/{station}/{symbol}/{year}-{month:02d}.json"
    )
    assert archive is not None
    return archive


def list_file():
    archive = ADAPTER.station_file(LIST, "stations")
    assert archive is not None
    return archive


def download(clock, archive, *cases):
    """The adapter's download of ``archive`` from ``cases``, with the requests it made."""
    with recorded(clock, *cases) as sent, httpx.Client(headers=_IDENTIFY) as client:
        result = ADAPTER.download(archive, client=client, cancel=None)
    return result, [request for _, request in sent]


def stored_list(tmp_path, clock):
    """A raw root holding the recorded station list, as the adapter downloads it."""
    raw = init_store(tmp_path / "raw")
    result, _ = download(clock, list_file(), "stations")
    write_archive(raw, archive=list_file(), response=result)
    return raw.root


def month_files(raw, **selection):
    """The server paths and actions of a selection of the stored list's month files."""
    options = {"years": 2026, "months": None, "stations": None, "today": TODAY}
    files, actions = ADAPTER.month_files(MEASUREMENTS, raw, **(options | selection))
    return [file.server_path for file in files], actions


def any_day(asked):
    """A transport answering every day's address with 24 hours of zeros."""

    def answer(request):
        asked.append(str(request.url))
        day = date.fromisoformat(request.url.path.rsplit("/", 1)[1])
        return httpx.Response(200, json=hours(day, [0] * 24))

    return httpx.MockTransport(answer)


# --------------------------------------------------------------------------
# Requests: the key, the pace, the errors of an answer
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("code", "error_code", "reason"),
    [
        (-11, "not_found", "unknown_station"),
        (-12, "no_data", "not_measured"),
        (-13, "no_data", "not_measured"),
        (-2, "validation_error", "bad_request"),
        (-3, "validation_error", "bad_request"),
        (-1, "source_unavailable", "provider_error"),
        (-500, "source_unavailable", "provider_error"),
        (None, "source_unavailable", "provider_error"),
    ],
)
def test_every_code_of_an_error_answer_maps_to_its_error(code, error_code, reason):
    url = f"{BASE}/measurements/1/rain/2026-11-03"
    payload = {"status": "error", "code": code, "message": "Komunikat dostawcy"}

    error = gdanskiewody._answer_error(payload, url)

    assert error.code == error_code
    assert dict(error.details) == {
        "url": url,
        "provider_code": code,
        "provider_text": "Komunikat dostawcy",
        "reason": reason,
    }
    assert url in str(error) and "Komunikat dostawcy" in str(error)


def test_a_refused_key_is_forbidden_with_invalid_credentials():
    payload = {"status": "error", "code": -100, "message": "Błąd uwierzytelniania"}

    error = gdanskiewody._answer_error(payload, STATIONS)

    assert (error.code, dict(error.details)) == REFUSED_KEY
    assert error.hint is not None
    assert "OBSERWATOR_GDANSKIE_WODY_API_KEY" in error.hint


@pytest.mark.parametrize(
    ("case", "error_code", "provider_code"),
    [
        ("m_1_foo_20261103", "validation_error", -2),
        ("m_1_rain_bad_date", "validation_error", -3),
        ("m_1_rain_bad_form", "validation_error", -3),
        ("m_1_water_20261103", "no_data", -13),
        ("m_3_rain_20261103", "not_found", -11),
    ],
)
def test_a_recorded_error_answer_names_the_address_but_never_the_key(
    clock, case, error_code, provider_code
):
    url = CASES[case]["url"]

    with (
        recorded(clock, case) as sent,
        httpx.Client(headers=_IDENTIFY) as client,
        pytest.raises(ObserwatorError) as caught,
    ):
        gdanskiewody._ask(client, url, source=ADAPTER.server_name)

    error = caught.value
    assert (error.code, error.details["url"], error.details["provider_code"]) == (
        error_code,
        url,
        provider_code,
    )
    assert error.details["provider_text"] == CASES[case]["json"]["message"]
    assert [request.headers["Authorization"] for _, request in sent] == [
        f"Bearer {KEY}"
    ]
    assert KEY not in f"{error} {json.dumps(dict(error.details))} {error.hint}"


def test_a_key_the_provider_refuses_is_forbidden_wherever_it_is_refused(clock):
    with pytest.raises(ObserwatorError) as listed:
        download(clock, list_file(), "stations_bad_key")
    # The key refused on the third day of a month.
    with pytest.raises(ObserwatorError) as midway:
        download(
            clock,
            month_file(1, "rain"),
            *days(1, "rain")[:2],
            "m_1_rain_20261103_bad_key",
        )

    assert (listed.value.code, dict(listed.value.details)) == REFUSED_KEY
    assert (midway.value.code, dict(midway.value.details)) == REFUSED_KEY


def test_without_a_key_nothing_is_asked_and_nothing_waited(clock, monkeypatch):
    monkeypatch.delenv("OBSERWATOR_GDANSKIE_WODY_API_KEY")

    for archive in (list_file(), month_file(1, "rain"), list_file()):
        with (
            recorded(clock) as sent,
            httpx.Client() as client,
            pytest.raises(ObserwatorError) as caught,
        ):
            ADAPTER.download(archive, client=client, cancel=None)
        assert (caught.value.code, dict(caught.value.details)) == MISSING_KEY
        assert sent == []
    with recorded(clock) as sent, pytest.raises(ObserwatorError) as searched:
        find_stations(provider="GDANSKIEWODY")

    assert (searched.value.code, dict(searched.value.details)) == MISSING_KEY
    assert sent == []
    assert clock.now() == NOW


def test_the_key_travels_only_in_the_authorization_header(tmp_path, clock):
    raw = init_store(tmp_path / "raw")
    archive = month_file(1, "rain")

    listed, asked = download(clock, list_file(), "stations")
    month, asked_month = download(clock, archive, *days(1, "rain"))
    write_archive(raw, archive=list_file(), response=listed)
    write_archive(raw, archive=archive, response=month)

    requests = asked + asked_month
    assert [str(request.url) for request in requests] == [
        STATIONS,
        *(f"{BASE}/measurements/1/rain/2026-11-0{day}" for day in (1, 2, 3)),
    ]
    assert {request.headers["Authorization"] for request in requests} == {
        f"Bearer {KEY}"
    }
    assert KEY not in "".join(str(request.url) for request in requests)
    assert KEY not in listed.url + month.url
    written = [path for path in raw.root.rglob("*") if path.is_file()]
    assert {"stations.meta.json", "2026-11.json.meta.json"} <= {
        path.name for path in written
    }
    assert all(KEY.encode() not in path.read_bytes() for path in written)


def test_consecutive_requests_wait_the_interval_of_the_setting(clock, monkeypatch):
    cases = (*days(1, "rain"), "stations", *days(7, "water"))

    with (
        recorded(clock, *cases) as sent,
        httpx.Client(headers=_IDENTIFY) as client,
    ):
        ADAPTER.download(month_file(1, "rain"), client=client, cancel=None)
        monkeypatch.setenv("OBSERWATOR_GDANSKIE_WODY_REQUEST_INTERVAL", "2.5")
        for archive in (list_file(), month_file(7, "water")):
            ADAPTER.download(archive, client=client, cancel=None)

    times = [moment for moment, _ in sent]
    # The default second between the days of the first file, then 2.5 s before each
    # later request: the pace holds from one file to the next.
    assert times[0] == NOW
    assert [
        (later - earlier).total_seconds() for earlier, later in pairwise(times)
    ] == [
        1.0,
        1.0,
        2.5,
        2.5,
        2.5,
        2.5,
    ]


@pytest.mark.parametrize("value", ["0.999", "0", "-1"])
def test_the_interval_is_never_shorter_than_a_second(clock, monkeypatch, value):
    monkeypatch.setenv("OBSERWATOR_GDANSKIE_WODY_REQUEST_INTERVAL", "1.0")
    assert Settings().gdanskie_wody_request_interval == 1.0
    monkeypatch.setenv("OBSERWATOR_GDANSKIE_WODY_REQUEST_INTERVAL", value)

    with pytest.raises(pydantic.ValidationError):
        Settings()
    with (
        recorded(clock) as sent,
        httpx.Client() as client,
        pytest.raises(pydantic.ValidationError),
    ):
        ADAPTER.download(list_file(), client=client, cancel=None)
    assert sent == []


# --------------------------------------------------------------------------
# Downloads: the station list and the month files
# --------------------------------------------------------------------------


def test_the_station_list_is_kept_as_canonical_json_without_signals(clock):
    result, asked = download(clock, list_file(), "stations")

    assert [str(request.url) for request in asked] == [STATIONS]
    canonical = json.dumps(
        CASES["stations"]["json"],
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    assert result.data == (canonical + "\n").encode("utf-8")
    assert (result.url, result.etag, result.last_modified) == (STATIONS, None, None)


def test_a_month_asks_each_of_its_days_up_to_today(clock):
    archive = month_file(1, "rain")

    result, asked = download(clock, archive, *days(1, "rain"))

    assert [str(request.url) for request in asked] == [
        f"{archive.url}/2026-11-0{day}" for day in (1, 2, 3)
    ]
    assert result.data == recorded_month(1, "rain")
    assert (result.url, result.etag, result.last_modified, result.content_length) == (
        archive.url,
        None,
        None,
        None,
    )


def test_a_cancel_stops_the_requests_between_two_days(clock):
    polls = iter([False, True])

    with (
        recorded(clock, "m_1_rain_20261101") as sent,
        httpx.Client() as client,
        pytest.raises(ObserwatorCancelledError) as stopped,
    ):
        ADAPTER.download(
            month_file(1, "rain"), client=client, cancel=lambda: next(polls)
        )
    with (
        recorded(clock) as none,
        httpx.Client() as client,
        pytest.raises(ObserwatorCancelledError),
    ):
        ADAPTER.download(month_file(1, "rain"), client=client, cancel=lambda: True)

    assert stopped.value.code == "cancelled"
    assert [str(request.url) for _, request in sent] == [
        f"{BASE}/measurements/1/rain/2026-11-01"
    ]
    assert none == []


@pytest.mark.parametrize(
    ("now", "last_modified"),
    [
        (SETTLED - timedelta(seconds=1), None),
        (SETTLED, "Tue, 01 Dec 2026 12:00:00 GMT"),
        (datetime(2027, 1, 15, 3, tzinfo=UTC), "Tue, 01 Dec 2026 12:00:00 GMT"),
    ],
)
def test_a_month_asked_once_settled_carries_that_time_as_its_last_modified(
    clock, now, last_modified
):
    clock.moment = now
    archive = month_file(1, "rain")
    asked = []

    with httpx.Client(transport=any_day(asked)) as client:
        result = ADAPTER.download(archive, client=client, cancel=None)

    assert ADAPTER.settled(archive) == SETTLED
    assert result.last_modified == last_modified
    if last_modified is not None:
        assert parsedate_to_datetime(last_modified) == SETTLED
    # Every day of the month is asked, the last one's hours running to 05:00 UTC of
    # 1 December.
    assert len(asked) == 30 and asked[-1] == f"{archive.url}/2026-11-30"
    assert list(read_month(result.data, filename="m.json")) == [
        date(2026, 11, 1) + timedelta(days=offset) for offset in range(30)
    ]


@pytest.mark.parametrize(
    ("year", "month", "settled", "held"),
    [
        (2026, 11, SETTLED, (date(2026, 11, 1), date(2026, 12, 1))),
        (
            2026,
            12,
            datetime(2027, 1, 1, 12, tzinfo=UTC),
            (date(2026, 12, 1), date(2027, 1, 1)),
        ),
        (
            2028,
            2,
            datetime(2028, 3, 1, 12, tzinfo=UTC),
            (date(2028, 2, 1), date(2028, 3, 1)),
        ),
    ],
)
def test_a_month_settles_six_hours_after_its_last_providers_day(
    year, month, settled, held
):
    archive = month_file(7, "water", year, month)

    assert ADAPTER.settled(archive) == settled
    assert ADAPTER.held_period(archive) == held


# --------------------------------------------------------------------------
# The month files a stored station list names
# --------------------------------------------------------------------------


def test_month_files_name_every_quantity_of_the_stored_list_and_read_back(
    tmp_path, clock
):
    raw = stored_list(tmp_path, clock)

    files, actions = ADAPTER.month_files(
        MEASUREMENTS, raw, years=2026, months=None, stations=None, today=TODAY
    )

    assert actions == ()
    # 23 quantities of the eight stations, January to November: December has not
    # begun on 2026-11-03.
    assert len(files) == 23 * 11
    assert {file.month for file in files} == set(range(1, 12))
    assert files[0] == ArchiveFile(
        "pl.gdanskiewody.measurements",
        "rest/measurements/1/rain/2026-01.json",
        f"{BASE}/measurements/1/rain",
        2026,
        1,
        "rain",
        "calendar",
        date(2026, 1, 1),
        date(2026, 1, 31),
        "GDANSKIEWODY-1",
    )
    assert [
        file.param
        for file in files
        if file.station_code == "GDANSKIEWODY-700" and file.month == 11
    ] == [*WATER_QUALITY, "watertemp"]
    assert all(
        ADAPTER.archive_from_path(MEASUREMENTS, file.server_path) == file
        for file in files
    )


def test_month_files_follow_the_selection_and_today(tmp_path, clock):
    raw = stored_list(tmp_path, clock)
    seven = ["GDANSKIEWODY-7"]
    november = [
        "rest/measurements/7/rain/2026-11.json",
        "rest/measurements/7/water/2026-11.json",
    ]

    assert month_files(raw, stations=seven, months=[10, 11]) == (
        [
            "rest/measurements/7/rain/2026-10.json",
            november[0],
            "rest/measurements/7/water/2026-10.json",
            november[1],
        ],
        (),
    )
    # A month that has not begun is no file.
    assert month_files(raw, years="2026-2027", months=[11, 12], stations=seven) == (
        november,
        (),
    )
    assert month_files(
        raw, months=[12], stations=["GDANSKIEWODY-1"], today=date(2026, 12, 1)
    ) == (["rest/measurements/1/rain/2026-12.json"], ())
    # A station the stored list does not hold waits for a sync of the list.
    assert month_files(raw, months=[11], stations=["GDANSKIEWODY-3", *seven]) == (
        november,
        (
            PlanAction(
                "store sync",
                "unverifiable",
                message("gdanskiewody.station_not_listed", code="GDANSKIEWODY-3"),
            ),
        ),
    )
    with pytest.raises(ObserwatorValidationError) as early:
        month_files(raw, years=2004)
    assert early.value.details["minimum"] == 2005


def test_month_files_need_the_station_list_in_the_raw_root(tmp_path):
    raw = init_store(tmp_path / "raw").root

    with pytest.raises(ObserwatorStoreError) as caught:
        month_files(raw)

    assert caught.value.code == "not_found"
    assert dict(caught.value.details) == {
        "reason": "missing_source",
        "datasets": ["pl.gdanskiewody.station_list"],
    }
    assert caught.value.hint is not None
    assert "pl.gdanskiewody.station_list" in caught.value.hint


@pytest.mark.parametrize(
    "server_path",
    [
        "rest/measurements/1/foo/2026-11.json",
        "rest/measurements/0/rain/2026-11.json",
        "rest/measurements/1000/rain/2026-11.json",
        "rest/measurements/07/rain/2026-11.json",
        "rest/measurements/1/rain/2026-13.json",
        "rest/measurements/1/rain/2026-1.json",
        "rest/measurements/1/rain/2026-11-01.json",
        "rest/measurements/1/rain/2026-11.csv",
        "rest/measurements/1/rain/2026-11",
        "rest/measurements/1/rain/x/2026-11.json",
        "rest/1/rain/2026-11.json",
        "rest/stations",
    ],
)
def test_a_path_that_is_no_month_file_names_no_file(server_path):
    assert ADAPTER.archive_from_path(MEASUREMENTS, server_path) is None
    assert (
        ADAPTER.archive_from_path(LIST, "rest/measurements/1/rain/2026-11.json") is None
    )


def test_the_month_files_are_named_only_by_a_stored_station_list():
    with pytest.raises(ObserwatorValidationError) as caught:
        archive_files("pl.gdanskiewody.measurements", years=2026)

    assert dict(caught.value.details) == {
        "option": "dataset",
        "value": "pl.gdanskiewody.measurements",
        "reason": "stored_list",
    }


# --------------------------------------------------------------------------
# The series of a month file
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("symbol", "series"),
    [
        # Station 7 is hydrological, yet its rain is meteorological.
        ("rain", {"pl.gdanskiewody.meteo_hourly", "pl.gdanskiewody.meteo_daily"}),
        ("water", {"pl.gdanskiewody.hydro_hourly", "pl.gdanskiewody.hydro_daily"}),
        ("watertemp", {"pl.gdanskiewody.hydro_hourly", "pl.gdanskiewody.hydro_daily"}),
        ("temp", {"pl.gdanskiewody.meteo_hourly", "pl.gdanskiewody.meteo_daily"}),
        # A day has no direction of the wind.
        ("winddir", {"pl.gdanskiewody.meteo_hourly"}),
        *((symbol, set()) for symbol in WATER_QUALITY),
    ],
)
def test_a_month_file_goes_to_the_series_holding_its_quantitys_variable(symbol, series):
    archive = month_file(7, symbol)

    assert {
        key for key in SERIES if ADAPTER.series_reads(get_dataset(key), archive)
    } == series


def test_the_hours_of_a_month_file_carry_its_station_and_variable():
    conductivity = encode_month(
        {date(2026, 11, 1): CASES["m_700_conductivity_20261101"]["json"]}
    )

    ((station, variable, points),) = ADAPTER.hourly_points(
        month_file(4, "water"), recorded_month(4, "water")
    )

    assert (station, variable, len(points)) == ("GDANSKIEWODY-4", "H_asl", 72)
    assert (points[0], points[-1]) == (
        ("2026-11-01T06:00:00+00:00", 4.9),
        ("2026-11-04T05:00:00+00:00", 4.89),
    )
    assert not list(
        ADAPTER.hourly_points(month_file(700, "conductivity"), conductivity)
    )


def test_a_month_file_holding_a_day_of_another_month_is_read_by_no_series():
    december = date(2026, 12, 1)
    spilled = encode_month({december: hours(december, [1.0] * 24)})
    archive = month_file(4, "water")

    with pytest.raises(ObserwatorDataError):
        list(ADAPTER.hourly_points(archive, spilled))
    with pytest.raises(ObserwatorDataError):
        list(ADAPTER.normalize(archive, data=spilled, carry=None))


# --------------------------------------------------------------------------
# The catalog and the live search
# --------------------------------------------------------------------------


def test_the_catalog_holds_the_stored_list_and_the_codes_only_in_a_series(
    tmp_path, clock
):
    raw = stored_list(tmp_path, clock)
    data = tmp_path / "data"
    # Station 3 is on no list: its month file is read by a series only.
    gone = month_file(3, "rain")
    day = date(2026, 11, 1)
    content = encode_month({day: hours(day, [0.5] * 24)})
    write_archive(
        raw, archive=gone, response=DownloadResult(content, gone.url, None, None, None)
    )
    build_series(data, dataset="pl.gdanskiewody.meteo_daily", raw_root=raw)

    report = build_catalog(data, raw_root=raw, provider="GDANSKIEWODY")

    stations = {
        item.station_code: item
        for item in read_catalog(root=data, provider="GDANSKIEWODY")
    }
    assert (
        report.status,
        report.station_count,
        report.without_location,
        report.from_series,
    ) == ("new", 9, 2, 1)
    assert sorted(stations, key=lambda code: int(code.rpartition("-")[2])) == [
        f"GDANSKIEWODY-{number}" for number in (1, 2, 3, 4, 7, 91, 504, 700, 999)
    ]
    listed, unplaced, only = (
        stations[f"GDANSKIEWODY-{number}"] for number in (1, 700, 3)
    )
    assert listed.geometry == (18.66171, 54.33604)
    assert (listed.properties["location_source"], listed.properties["kind"]) == (
        "pl.gdanskiewody.station_list",
        "meteo",
    )
    assert (unplaced.geometry, unplaced.properties["location_missing_reason"]) == (
        None,
        "none",
    )
    assert (unplaced.properties["kind"], unplaced.properties["active"]) == (
        "hydro",
        True,
    )
    assert (only.geometry, only.properties["kind"]) == (None, "meteo")
    assert (only.properties["name"], only.properties["active"]) == ("", False)


def test_the_catalog_needs_the_stored_station_list(tmp_path):
    raw = init_store(tmp_path / "raw")

    with pytest.raises(ObserwatorStoreError) as caught:
        build_catalog(tmp_path / "data", raw_root=raw, provider="GDANSKIEWODY")

    assert caught.value.code == "not_found"
    assert caught.value.details["reason"] == "missing_source"


async def test_a_live_search_naming_the_provider_reads_its_recorded_list(clock):
    with recorded(clock, "stations", "stations") as both:
        found = find_stations(provider="GDANSKIEWODY")
    with recorded(clock, "stations") as meteo:
        sopot = run_command(
            "stations find",
            options={"provider": "GDANSKIEWODY", "kind": "meteo", "query": "sopot"},
        )
    with respx.mock(assert_all_called=True) as router:
        route = router.get(STATIONS).respond(json=CASES["stations"]["json"])
        hydro = await find_stations_async(provider="GDANSKIEWODY", kind="hydro")

    # One list holds both families: a search of both asks it once per family.
    assert (len(both), len(meteo)) == (2, 1)
    assert [(entry.kind, entry.station_code) for entry in found] == [
        ("hydro", "GDANSKIEWODY-504"),
        ("hydro", "GDANSKIEWODY-700"),
        ("hydro", "GDANSKIEWODY-4"),
        ("hydro", "GDANSKIEWODY-7"),
        ("hydro", "GDANSKIEWODY-999"),
        ("meteo", "GDANSKIEWODY-1"),
        ("meteo", "GDANSKIEWODY-2"),
        ("meteo", "GDANSKIEWODY-91"),
    ]
    assert {entry.provider for entry in found} == {"GDANSKIEWODY"}
    assert [entry.station_code for entry in sopot.result] == ["GDANSKIEWODY-91"]
    assert hydro == tuple(entry for entry in found if entry.kind == "hydro")
    assert route.calls.last.request.headers["Authorization"] == f"Bearer {KEY}"


async def test_a_search_without_a_provider_never_asks_gdanskie_wody(clock):
    with respx.mock(assert_all_called=False) as router:
        serve_chmu(router, "hydro_now_get")
        router.get(IMGW_HYDRO).respond(content=IMGW_HYDRO_CSV.encode("cp1250"))
        router.get(IMGW_API + "hydro").respond(json=[])
        gdansk = router.get(STATIONS).respond(json=CASES["stations"]["json"])
        found = find_stations(kind="hydro")
        found_async = await find_stations_async(kind="hydro")

    assert not gdansk.called
    assert found == found_async
    assert {entry.provider for entry in found} == {"IMGW", "CHMU"}
