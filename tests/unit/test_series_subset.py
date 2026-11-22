"""Series of chosen stations and years (ADR-026): what a subset holds, how a root keeps it."""

import io
import json
import zipfile
from datetime import date
from pathlib import Path

import pyarrow.parquet as pq
import pytest

from obserwator import CommandCall, command_for_version, run_command, validate_command
from obserwator.datasets import _archive_from_path, archive_files
from obserwator.exceptions import (
    ObserwatorStoreConflictError,
    ObserwatorValidationError,
)
from obserwator.fetch import DownloadResult
from obserwator.store import (
    SeriesSubset,
    build_series,
    check_series,
    current_version,
    init_store,
    read_series_index,
    write_archive,
)

FIXTURES = Path(__file__).parents[1] / "fixtures"
HYDRO = "pl.imgw.hydro_daily"
PRECIP = "pl.imgw.meteo_precip_daily"
SYNOP = "pl.imgw.meteo_synop_daily"
CZ_HYDRO = "cz.chmu.hydro_daily"
CZ_METEO = "cz.chmu.meteo_daily"
# The stations of the hydro fixtures: RABA in every archive, NO_Q in November 2021
# and November 2023 only.
RABA, NO_Q = "149190310", "149190311"
BORUCINO = "254170210"
SWINOUJSCIE = "353140200"
SIGNAL = ('"v1"', "Sat, 17 Oct 2026 12:00:00 GMT")
SYNOP_FOLDER = "dane_meteorologiczne/dobowe/synop"


def put(raw, archive, content):
    response = DownloadResult(content, archive.url, SIGNAL[0], SIGNAL[1], len(content))
    return write_archive(raw, archive=archive, response=response)


def store_hydro(raw):
    for archive in archive_files(HYDRO, years=[2022, 2023, 2024], months=[1]):
        path = FIXTURES / "store" / "archives" / archive.server_path
        put(raw, archive, path.read_bytes())


def precip(raw, year, month, rows):
    """Store IMGW-PIB's daily precipitation archive of a month with these rows."""
    (archive,) = archive_files(PRECIP, years=[year], months=[month])
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as package:
        package.writestr(f"o_d_{month:02d}_{year}.csv", "".join(rows).encode("cp1250"))
    return put(raw, archive, buffer.getvalue())


def rain(day, value):
    """A row of BORUCINO: a total, or no measurement (status 8) without a value."""
    when = f'"{day.year}","{day.month:02d}","{day.day:02d}"'
    if value is None:
        return f'"{BORUCINO}","BORUCINO",{when},,"8",,,"8",,"8",,"8",,"8"\n'
    return f'"{BORUCINO}","BORUCINO",{when},{value},,"W",,"9",,"8",,"8",,"9"\n'


def index(report):
    return json.loads(report.version.read_text(encoding="utf-8"))


def sidecar(report):
    meta = report.version.parent / "series.json.meta.json"
    return json.loads(meta.read_text(encoding="utf-8"))


def rows(report, code, since=date.min):
    table = pq.read_table(report.version.parent / "stations" / f"{code}.parquet")
    return [row for row in table.to_pylist() if row["date"] >= since]


def names(report):
    return {path.name for path in report.source_files}


def tree(root):
    return {
        path.relative_to(root).as_posix(): path.stat().st_mtime_ns
        for path in sorted(root.rglob("*"))
    }


@pytest.fixture
def raw(tmp_path):
    return init_store(tmp_path / "raw").root


def test_a_subset_of_stations_holds_the_rows_and_gaps_of_the_full_series(raw, tmp_path):
    store_hydro(raw)

    full = build_series(tmp_path / "full", raw_root=raw, dataset=HYDRO)
    part = build_series(tmp_path / "part", raw_root=raw, dataset=HYDRO, stations=[RABA])

    assert (part.status, part.stations, names(part)) == ("new", 1, names(full))
    whole, subset = index(full), index(part)
    # Only NO_Q has a record of November 2023: the month is published all the
    # same, so RABA has a gap there in the subset too.
    assert ["2023-11-01", "2023-11-30"] in whole["stations"][RABA]["variables"]["H"][
        "gaps"
    ]
    assert subset["stations"] == {RABA: whole["stations"][RABA]}
    assert subset["periods"] == whole["periods"]
    assert (subset["subset"], "subset" in whole) == ({"stations": [RABA]}, False)
    assert sidecar(part)["request"] == {"dataset": HYDRO, "stations": [RABA]}
    assert sidecar(full)["request"] == {"dataset": HYDRO}
    assert read_series_index(part.version).subset == SeriesSubset(stations=(RABA,))
    assert read_series_index(full.version).subset is None


def test_a_subset_of_years_reads_its_archives_and_the_one_that_leaves_it_days(
    raw, tmp_path
):
    precip(raw, 2023, 11, [rain(date(2023, 11, 2), "1.0")])
    december = precip(
        raw,
        2023,
        12,
        [
            rain(date(2023, 12, 29), "2.0"),
            rain(date(2023, 12, 30), None),
            rain(date(2023, 12, 31), None),
        ],
    )
    january = precip(
        raw, 2024, 1, [rain(date(2024, 1, 1), "13.1"), rain(date(2024, 1, 2), "0.4")]
    )

    full = build_series(tmp_path / "full", raw_root=raw, dataset=PRECIP)
    part = build_series(tmp_path / "part", raw_root=raw, dataset=PRECIP, years=[2024])

    # December leaves its missing days to 1 January: read, its own days left out.
    assert set(part.source_files) == {december.path, january.path}
    days = rows(part, BORUCINO)
    assert days[0]["date"] == date(2024, 1, 1)
    assert (days[0]["P_value"], days[0]["P_flag"]) == (13.1, "accumulated")
    assert days == rows(full, BORUCINO, since=date(2024, 1, 1))
    assert index(part)["periods"] == [["2024-01-01", "2024-01-31"]]
    assert index(part)["subset"] == {"years": [2024]}


def test_a_subset_is_never_built_beside_the_full_series(raw, tmp_path):
    store_hydro(raw)
    data = tmp_path / "data"
    full = build_series(data, raw_root=raw, dataset=HYDRO)
    before = tree(data)

    with pytest.raises(ObserwatorStoreConflictError) as refused:
        build_series(data, raw_root=raw, dataset=HYDRO, stations=[RABA])
    plan = check_series(data, raw_root=raw, dataset=HYDRO, years=[2024])

    version = full.version.parent
    assert refused.value.code == "conflict"
    assert refused.value.details == {
        "reason": "full_series",
        "version": version.relative_to(data).as_posix(),
    }
    assert tree(data) == before
    assert plan.items == ()
    assert [(item.action, item.reason, item.path) for item in plan.actions] == [
        ("conflict", "full_series", version)
    ]


def test_a_version_is_reused_only_for_the_same_subset(raw, tmp_path):
    store_hydro(raw)
    data = tmp_path / "data"

    def current():
        return current_version(data, slot=f"series:{HYDRO}").version

    def state(**subset):
        return check_series(data, raw_root=raw, dataset=HYDRO, **subset).series_state

    first = build_series(data, raw_root=raw, dataset=HYDRO, stations=[RABA])
    again = build_series(data, raw_root=raw, dataset=HYDRO, stations=[RABA, RABA])
    assert (first.status, again.status, again.version) == (
        "new",
        "unchanged",
        first.version,
    )
    assert state(stations=[RABA]) == {"imgw_hydro_daily": "current"}
    assert state(stations=[NO_Q, RABA]) == {"imgw_hydro_daily": "outdated"}

    # Every station of the archives is still a subset: no full series.
    every = build_series(data, raw_root=raw, dataset=HYDRO, stations=[NO_Q, RABA])
    assert every.status == "new" and current() == every.version
    assert state() == {"imgw_hydro_daily": "outdated"}

    full = build_series(data, raw_root=raw, dataset=HYDRO)
    assert full.status == "new" and current() == full.version
    assert index(full)["stations"] == index(every)["stations"]
    with pytest.raises(ObserwatorStoreConflictError):
        build_series(data, raw_root=raw, dataset=HYDRO, stations=[RABA])


def test_the_call_of_a_subset_version_builds_the_same_subset(raw, tmp_path):
    store_hydro(raw)
    data = tmp_path / "data"
    built = build_series(
        data, raw_root=raw, dataset=HYDRO, stations=[RABA], years="2023-2024"
    )

    call = command_for_version(built.version, root=data, raw_root=raw)
    again = run_command(call.command, options=call.options).result

    assert call == CommandCall(
        "series build",
        {
            "root": str(data),
            "raw_root": str(raw),
            "dataset": HYDRO,
            "stations": [RABA],
            "years": ["2023,2024"],
        },
        {},
    )
    assert (again.status, again.version) == ("unchanged", built.version)


def test_a_subset_names_the_stations_it_lacks_and_publishes_nothing_without_any(
    raw, tmp_path
):
    store_hydro(raw)
    notices = []

    part = build_series(
        tmp_path / "part",
        raw_root=raw,
        dataset=HYDRO,
        stations=[RABA, "149199999"],
        on_notice=notices.append,
    )
    nobody = build_series(
        tmp_path / "none", raw_root=raw, dataset=HYDRO, stations=["149199999"]
    )
    no_year = build_series(tmp_path / "none", raw_root=raw, dataset=HYDRO, years=[1990])

    assert part.status == "new" and list(index(part)["stations"]) == [RABA]
    assert index(part)["subset"] == {"stations": [RABA, "149199999"]}
    (missing,) = [notice for notice in notices if notice.level == "warning"]
    assert missing.code == "stations_missing" and "149199999" in missing.message
    assert (nobody.status, no_year.status) == ("failed", "failed")
    assert nobody.problems and no_year.problems
    assert not (tmp_path / "none").exists()


@pytest.mark.parametrize(
    ("dataset", "station", "years", "year_file"),
    [
        (CZ_HYDRO, "0-203-1-900002", None, None),
        (CZ_HYDRO, "0-203-1-900001", [2024], "H_0-203-1-900001_DQ_2024.json"),
        (CZ_METEO, "0-203-0-90001", None, None),
    ],
)
def test_a_subset_of_station_files_reads_only_the_files_of_its_stations(
    fixture_raw_root, tmp_path, dataset, station, years, year_file
):
    full = build_series(tmp_path / "full", raw_root=fixture_raw_root, dataset=dataset)
    part = build_series(
        tmp_path / "part",
        raw_root=fixture_raw_root,
        dataset=dataset,
        stations=[station],
        years=years,
    )

    files = {
        name for name in names(full) if f"{station}-" in name or f"{station}_" in name
    }
    assert len(files) < len(names(full))
    assert names(part) == (files if year_file is None else {year_file})
    assert list(index(part)["stations"]) == [station]
    if years is None:
        assert index(part)["stations"][station] == index(full)["stations"][station]
    else:
        periods = [["2024-01-01", "2024-12-31"]]
        assert index(part)["stations"][station]["periods"] == periods
        assert rows(part, station) == rows(full, station, since=date(2024, 1, 1))


def test_a_synop_subset_reads_the_files_of_its_station_and_the_monthly_files(
    raw, tmp_path
):
    for path in (
        "1966_1970/1966_1970_230_s.zip",  # Piła
        "2024/2024_200_s.zip",  # Świnoujście
        "2025/2025_200_s.zip",
        "2026/2026_01_s.zip",  # the whole country in January 2026
    ):
        archive = _archive_from_path(SYNOP, f"{SYNOP_FOLDER}/{path}")
        content = FIXTURES / "synop" / "archives" / archive.server_path
        put(raw, archive, content.read_bytes())

    full = build_series(tmp_path / "full", raw_root=raw, dataset=SYNOP)
    part = build_series(
        tmp_path / "part", raw_root=raw, dataset=SYNOP, stations=[SWINOUJSCIE]
    )
    year = build_series(
        tmp_path / "year",
        raw_root=raw,
        dataset=SYNOP,
        stations=[SWINOUJSCIE],
        years=[2025],
    )

    assert names(part) == {"2024_200_s.zip", "2025_200_s.zip", "2026_01_s.zip"}
    assert index(part)["stations"] == {
        SWINOUJSCIE: index(full)["stations"][SWINOUJSCIE]
    }
    assert names(year) == {"2025_200_s.zip"}
    assert index(year)["stations"][SWINOUJSCIE]["periods"] == [
        ["2025-01-01", "2025-12-31"]
    ]


@pytest.mark.parametrize(
    ("subset", "option"),
    [
        ({"stations": ["0-203-1-001000"]}, "stations"),  # a ČHMÚ code
        ({"stations": RABA}, "stations"),  # a text, not a list
        ({"stations": []}, "stations"),
        ({"years": "2024-2020"}, "years"),
    ],
)
def test_a_subset_outside_the_grammar_is_refused_before_anything_is_read(
    raw, tmp_path, subset, option
):
    for check in (check_series, build_series):
        with pytest.raises(ObserwatorValidationError) as refused:
            check(tmp_path / "data", raw_root=raw, dataset=HYDRO, **subset)
        assert refused.value.details["option"] == option
    assert not (tmp_path / "data").exists()


def test_the_catalog_refuses_a_code_of_another_provider_as_the_library_does(tmp_path):
    # The schema of the option takes every code of either provider; the rule of the
    # command keeps CLI, REST and MCP to the dataset's provider.
    with pytest.raises(ObserwatorValidationError) as refused:
        validate_command(
            "series build",
            options={
                "root": str(tmp_path / "data"),
                "dataset": HYDRO,
                "stations": [RABA, "0-203-1-001000"],
            },
        )
    assert refused.value.details == {"option": "stations", "value": ["0-203-1-001000"]}
