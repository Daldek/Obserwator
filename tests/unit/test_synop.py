"""pl.imgw.meteo_synop_daily: the per-station synop archives of IMGW-PIB (ADR-022).

The archives and folder indexes are recorded from danepubliczne.imgw.pl (2026-11):
``1966_1970_230_s.zip`` (Piła, records from 12 October 1970), ``2024_200_s.zip``
(Świnoujście, s_d and a half-year s_d_t), ``2025_200_s.zip`` (s_d only), the monthly
file of January 2026 and the climate archive of 1965 with the rows of Świnoujście only,
and the indexes of three folders with the rows of four stations.
"""

import csv
import io
import json
import zipfile
from datetime import date
from pathlib import Path

import httpx
import pytest
import respx

from obserwator import (
    CommandCall,
    command_for_version,
    normalize_archive,
    parse_meteo_synop_daily,
)
from obserwator.datasets import _archive_from_path, archive_files
from obserwator.exceptions import ObserwatorDataError, ObserwatorValidationError
from obserwator.fetch import DownloadResult
from obserwator.store import build_series, init_store, read_series, write_archive
from obserwator.store.analyses import _plan
from obserwator.store.analysis_registry import analysis_definitions
from obserwator.store.export import _export_joined
from obserwator.store.sync import check_store, sync_store
from obserwator.urls import IMGW_PUBLIC_DATA_URL

FIXTURES = Path(__file__).parents[1] / "fixtures" / "synop"
SYNOP = "pl.imgw.meteo_synop_daily"
CLIMATE = "pl.imgw.meteo_climate_daily"
PRECIP = "pl.imgw.meteo_precip_daily"
SWINOUJSCIE, PILA, BIELSKO = "353140200", "353160230", "349190600"
FOLDER = "dane_meteorologiczne/dobowe/synop"
S1966 = _archive_from_path(SYNOP, f"{FOLDER}/1966_1970/1966_1970_230_s.zip")
S2024 = _archive_from_path(SYNOP, f"{FOLDER}/2024/2024_200_s.zip")
S2025 = _archive_from_path(SYNOP, f"{FOLDER}/2025/2025_200_s.zip")
M2026 = _archive_from_path(SYNOP, f"{FOLDER}/2026/2026_01_s.zip")
SIGNAL = {"ETag": '"s1"', "Last-Modified": "Tue, 07 Jan 2025 13:38:00 GMT"}


def content(archive):
    return (FIXTURES / "archives" / archive.server_path).read_bytes()


def store(root, archive, data=None):
    data = content(archive) if data is None else data
    response = DownloadResult(
        data, archive.url, SIGNAL["ETag"], SIGNAL["Last-Modified"], len(data)
    )
    return write_archive(root, archive=archive, response=response)


def member(archive, name):
    with zipfile.ZipFile(io.BytesIO(content(archive))) as package:
        return package.read(name)


def zipped(name, rows):
    """A ZIP of one CP1250 CSV member made of rows of cells."""
    text = io.StringIO()
    csv.writer(text, quoting=csv.QUOTE_MINIMAL, lineterminator="\r\n").writerows(rows)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as package:
        package.writestr(name, text.getvalue().encode("cp1250"))
    return buffer.getvalue()


def by_day(records):
    return {record.date: record for record in records}


@pytest.fixture
def raw(tmp_path):
    return init_store(tmp_path / "raw").root


@pytest.fixture
def server():
    with respx.mock(assert_all_called=False) as mock:
        yield mock


# --------------------------------------------------------------------------
# Parsing
# --------------------------------------------------------------------------


def test_station_archive_joins_the_daily_and_term_files_of_its_station():
    days = by_day(normalize_archive(S2024, data=content(S2024)))

    assert len(days) == 366 and {r.station_code for r in days.values()} == {SWINOUJSCIE}
    first = days[date(2024, 1, 1)]
    values = {name: (m.value, m.flag) for name, m in first.measurements.items()}
    # The variables of the climate stations keep their names.
    assert values["Tmax"] == (6.2, "value") and values["P"] == (1.1, "value")
    # Status 9 is no phenomenon, status 8 no measurement.
    assert values["snow_cover"] == (0.0, "no_phenomenon")
    assert values["rain_duration"] == (None, "missing")
    # s_d_t: NOS with status 8, FWS 2.9, PPPS 1003.0, WODZ 0.1, WONO 1.0.
    assert values["cloud_cover"] == (None, "missing")
    assert values["wind_speed"] == (2.9, "value")
    assert values["pressure_station"] == (1003.0, "value")
    assert (values["P_day"], values["P_night"]) == ((0.1, "value"), (1.0, "value"))
    assert first.attributes == {"precip_type": "W", "ground_state": "R"}
    # IMGW-PIB published s_d_t of 2024 until June: the second half is missing.
    assert days[date(2024, 6, 30)].measurements["wind_speed"].flag == "value"
    assert days[date(2024, 12, 31)].measurements["wind_speed"].flag == "missing"
    assert days[date(2024, 12, 31)].measurements["Tmax"].flag == "value"


def test_five_year_archive_covers_its_folder_from_the_first_day():
    records = list(normalize_archive(S1966, data=content(S1966)))
    days = by_day(records)

    assert len(records) == (date(1970, 12, 31) - date(1966, 1, 1)).days + 1
    assert {record.station_code for record in records} == {PILA}
    assert all(
        m.flag == "missing" for m in days[date(1966, 1, 1)].measurements.values()
    )
    assert days[date(1970, 10, 12)].measurements["Tmax"].value == 11.8


def test_archive_without_term_file_has_only_the_daily_variables():
    records = list(normalize_archive(S2025, data=content(S2025)))

    assert len(records) == 365
    assert "cloud_cover" not in records[0].measurements
    assert "Tmax" in records[0].measurements


def test_monthly_file_covers_its_month_for_every_station():
    records = list(normalize_archive(M2026, data=content(M2026)))

    assert {record.station_code for record in records} == {BIELSKO, SWINOUJSCIE}
    assert len(records) == 2 * 31
    assert {record.date.month for record in records} == {1}


def test_station_file_holds_only_codes_of_its_number():
    daily = member(S2024, "s_d_200_2024.csv")

    assert len(list(parse_meteo_synop_daily(daily, filename="s_d_200_2024.csv"))) == 366
    with pytest.raises(ObserwatorDataError, match="201"):
        list(parse_meteo_synop_daily(daily, filename="s_d_201_2024.csv"))
    # The term file is told by its name; a date outside the name's year is refused.
    terms = member(S2024, "s_d_t_200_2024.csv")
    parsed = list(parse_meteo_synop_daily(terms, filename="s_d_t_200_2024.csv"))
    assert set(parsed[0].measurements) == {
        "cloud_cover",
        "wind_speed",
        "vapour_pressure",
        "humidity",
        "pressure_station",
        "pressure_sea",
        "P_day",
        "P_night",
    }
    with pytest.raises(ObserwatorDataError):
        list(parse_meteo_synop_daily(daily, filename="s_d_200_2023.csv"))


# --------------------------------------------------------------------------
# Selection: archive_files and the folder index of store check and store sync
# --------------------------------------------------------------------------


def test_archive_files_name_the_station_files_by_the_last_digits_of_the_code():
    files = archive_files(SYNOP, years="1968,2024", stations=[SWINOUJSCIE, PILA])

    assert [item.server_path.rsplit("/", 1)[1] for item in files] == [
        "1966_1970_200_s.zip",
        "2024_200_s.zip",
        "1966_1970_230_s.zip",
        "2024_230_s.zip",
    ]
    assert (files[0].period_start, files[0].period_end) == (
        date(1966, 1, 1),
        date(1970, 12, 31),
    )
    assert all(item.station_code is None for item in files)
    with pytest.raises(ObserwatorValidationError):
        archive_files(SYNOP, years=1965, stations=[SWINOUJSCIE])


def listings(server, *, missing=()):
    for name in ("1966_1970", "2024", "2026"):
        server.get(f"{IMGW_PUBLIC_DATA_URL}/{FOLDER}/{name}/").mock(
            return_value=httpx.Response(
                200, text=(FIXTURES / "listings" / f"synop_{name}.html").read_text()
            )
        )
    for name in missing:
        server.get(f"{IMGW_PUBLIC_DATA_URL}/{FOLDER}/{name}/").mock(
            return_value=httpx.Response(404)
        )
    server.head(url__startswith=f"{IMGW_PUBLIC_DATA_URL}/{FOLDER}/").mock(
        return_value=httpx.Response(200, headers=SIGNAL)
    )


def names(plan):
    return [item.archive.server_path.rsplit("/", 1)[1] for item in plan.items]


def test_store_check_takes_the_files_of_the_folder_index(raw, server):
    listings(server, missing=("2027",))
    store(raw, S2024)

    every = check_store(raw, datasets=[SYNOP], years=[1968, 2024, 2026, 2027])
    chosen = check_store(
        raw,
        datasets=["meteo/dobowe/synop"],
        years=[1968, 2024, 2026],
        months=[1],
        stations=[SWINOUJSCIE, "353999230"],
    )
    lonely = check_store(raw, datasets=[SYNOP], years=[2024], stations=["351160424"])

    # Without stations every station of each folder, with the running year's
    # monthly files of the whole country.
    assert names(every) == [
        "1966_1970_200_s.zip",
        "1966_1970_230_s.zip",
        "1966_1970_600_s.zip",
        "1966_1970_625_s.zip",
        "2024_200_s.zip",
        "2024_230_s.zip",
        "2024_600_s.zip",
        "2024_625_s.zip",
        "2026_01_s.zip",
        "2026_02_s.zip",
    ]
    status = {item.archive.server_path: item.status for item in every.items}
    assert status[S2024.server_path] == "current"
    assert status[S1966.server_path] == "missing"
    assert [action.status for action in every.actions] == ["unverifiable"]
    assert "2027" in every.actions[0].detail
    # Stations select by their last three digits; months only the monthly files.
    assert names(chosen) == [
        "1966_1970_200_s.zip",
        "1966_1970_230_s.zip",
        "2024_200_s.zip",
        "2024_230_s.zip",
        "2026_01_s.zip",
    ]
    assert not chosen.actions
    assert lonely.items == () and "351160424" in lonely.actions[0].detail


def test_store_sync_downloads_the_listed_files(raw, server):
    listings(server)
    for archive in (S1966, M2026):
        server.get(archive.url).mock(
            return_value=httpx.Response(200, headers=SIGNAL, content=content(archive))
        )

    report = sync_store(
        raw, datasets=[SYNOP], years=[1970, 2026], months=[1], stations=[PILA]
    )

    assert [(item.slot, item.status) for item in report.items] == [
        (f"archive:{SYNOP}:1966_1970/1966_1970_230_s.zip", "new"),
        (f"archive:{SYNOP}:2026/2026_01_s.zip", "new"),
    ]


def test_version_of_a_synop_archive_gives_the_sync_of_its_folder(raw):
    station = store(raw, S1966)
    monthly = store(raw, M2026)

    for written, options in (
        (station, {"years": ["1966"]}),
        (monthly, {"years": ["2026"], "months": ["1"]}),
    ):
        call = command_for_version(written.path.relative_to(raw), root=raw)
        assert call == CommandCall(
            "store sync", {"root": str(raw), "datasets": [SYNOP], **options}, {}
        )


# --------------------------------------------------------------------------
# Series: per-station periods and the monthly files of the running year
# --------------------------------------------------------------------------


def test_station_archive_of_a_year_supersedes_the_monthly_files_of_its_year(
    raw, tmp_path
):
    # A monthly file of January 2024 as IMGW-PIB publishes it for the running
    # year: Świnoujście's January with another Tmax on the 1st, and a station
    # without an archive of its own.
    rows = list(
        csv.reader(io.StringIO(member(S2024, "s_d_200_2024.csv").decode("cp1250")))
    )
    january = [row for row in rows if row[3] == "01"]
    changed = [[*january[0][:5], "99.9", *january[0][6:]], *january[1:]]
    other = [[BIELSKO, *row[1:]] for row in january]
    (monthly,) = archive_files(SYNOP, years=[2024], months=[1])
    store(raw, monthly, zipped("s_d_01_2024.csv", changed + other))
    store(raw, S2024)
    data = tmp_path / "data"

    report = build_series(data, raw_root=raw, dataset=SYNOP)

    assert report.status == "new", report.problems
    index = json.loads(report.version.read_text(encoding="utf-8"))
    assert index["stations"][SWINOUJSCIE]["periods"] == [["2024-01-01", "2024-12-31"]]
    assert index["stations"][BIELSKO]["periods"] == [["2024-01-01", "2024-01-31"]]
    first = next(read_series(report.version, station=SWINOUJSCIE))
    assert first.measurements["Tmax"].value == 6.2


# --------------------------------------------------------------------------
# The joined daily record of a station (ADR-022)
# --------------------------------------------------------------------------


def climate_row(code, day, tmax, p):
    return [code, "STACJA", day.year, f"{day.month:02d}", f"{day.day:02d}",
            tmax, "", -1.0, "", 0.5, "", -2.0, "", p, "", "W", 0, "9"]  # fmt: skip


def test_joined_record_takes_synop_then_climate_by_day_and_variable(raw, tmp_path):
    store(raw, S1966)
    store(raw, S2024)
    store(raw, archive_files(CLIMATE, years=[1965])[0])
    # Piła in the climate archive of 1970: a day the synoptic file fills as
    # missing and a day both hold.
    (k1970,) = archive_files(CLIMATE, years=[1970])
    store(
        raw,
        k1970,
        zipped(
            "k_d_1970.csv",
            [
                climate_row(PILA, date(1970, 1, 1), 1.0, 2.5),
                climate_row(PILA, date(1970, 10, 12), 99.0, 9.9),
            ],
        ),
    )
    data = tmp_path / "data"
    synop = build_series(data, raw_root=raw, dataset=SYNOP).version
    climate = build_series(data, raw_root=raw, dataset=CLIMATE).version

    def joined(station):
        target = tmp_path / f"{station}.csv"
        _export_joined([synop, climate], station=station, output=target)
        with target.open(encoding="utf-8", newline="") as stream:
            return {row["date"]: row for row in csv.DictReader(stream)}

    pila = joined(PILA)
    swinoujscie = joined(SWINOUJSCIE)

    # Synop first; the climate value fills a day the synoptic file lacks.
    assert pila["1970-01-01"]["Tmax [degC]"] == "1.0"
    assert pila["1970-10-12"]["Tmax [degC]"] == "11.8"
    assert pila["1970-10-12"]["sunshine [h]"] == ""
    # One row per day from the first to the last record of any series.
    assert (
        list(swinoujscie)[0] == "1965-01-01" and list(swinoujscie)[-1] == "2024-12-31"
    )
    assert len(swinoujscie) == (date(2024, 12, 31) - date(1965, 1, 1)).days + 1
    assert swinoujscie["1965-01-01"]["Tmax [degC]"] == "5.9"
    assert swinoujscie["2024-01-01"]["Tmax [degC]"] == "6.2"
    assert swinoujscie["1990-06-01"]["Tmax_flag"] == "missing"


def test_meteo_analyses_read_the_joined_record_of_the_station():
    held = {
        SYNOP: frozenset({"P", "Tmax", "Tmin", "Tmean", "snow_cover"}),
        CLIMATE: frozenset({"P", "Tmax", "Tmin", "Tmean", "snow_cover"}),
        PRECIP: frozenset({"P", "snow_cover"}),
    }
    planned = _plan("meteo", held, {}, analysis_definitions(kind="meteo"))

    files = {
        (planned_.variant.inputs[0].variables, keys)
        for planned_ in planned
        for _, keys in planned_.files
    }
    assert ((("P",), (SYNOP, CLIMATE, PRECIP))) in files
    assert any(
        "Tmax" in variables and keys == (SYNOP, CLIMATE) for variables, keys in files
    )
    # A station with a climate series only reads it alone.
    alone = _plan("meteo", {CLIMATE: held[CLIMATE]}, {}, analysis_definitions())
    assert {keys for item in alone for _, keys in item.files} == {(CLIMATE,)}
