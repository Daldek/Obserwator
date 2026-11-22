"""
Half-year characteristics of ČHMÚ computed by Obserwator (the author's decision of 2026-11-18).

ČHMÚ publishes no half-year characteristics, so ``characteristic.{H,Q,T}.half_years``
of a ČHMÚ station read the file Obserwator computes of its daily series with the
definitions of IMGW-PIB's ``pl.imgw.hydro_semiannual`` (``AnalysisInput.derived``
``half_years``), while IMGW-PIB stations keep IMGW-PIB's published file. Hydrolog's
program is the recorded fake of ``tests/fixtures/hydrolog``; the test marked
``hydrolog`` asks the real one named by ``OBSERWATOR_HYDROLOG_COMMAND``.
"""

import csv
import io
import json
import math
import os
import shutil
import tempfile
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pytest

from obserwator import (
    AnalysisSource,
    build_analyses,
    build_series,
    compute_analysis,
    current_version,
    export_analyses,
    export_series,
    list_analyses,
    read_analysis,
    read_series_index,
)
from obserwator.attribution import attribution
from obserwator.datasets import archive_files
from obserwator.fetch import DownloadResult
from obserwator.models import Measurement
from obserwator.store import write_archive
from obserwator.store.export import _export_half_years, _half_year_table
from tests.contract.support import (
    RABA,
    load,
    sha256,
    snapshot,
    stamps,
    trailing_lines,
    use_fake_hydrolog,
)

# The real Hydrolog of the test marked ``hydrolog``, read before any test changes it.
REAL_HYDROLOG = os.environ.get("OBSERWATOR_HYDROLOG_COMMAND")
CHMU_HYDRO = "0-203-1-900001"  # a ČHMÚ hydrological station of the fixture
CHMU_DAILY = "cz.chmu.hydro_daily"
SEMIANNUAL = "pl.imgw.hydro_semiannual"
FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
# IMGW-PIB's half-year file as `series export` writes it.
GOLDEN = FIXTURES / "export_golden" / "series_export_hydro_semiannual.csv"
MISSING = ("", "missing", "", "", "")
"""Value, flag, start, end and occurrences of a statistic without a value."""


@pytest.fixture(autouse=True)
def fake_hydrolog(monkeypatch):
    """Hydrolog's program is the fake, answering at once with its own version."""
    for name in (
        "FAKE_HYDROLOG_VERSION",
        "FAKE_HYDROLOG_SLEEP",
        "FAKE_HYDROLOG_FAIL",
        "FAKE_HYDROLOG_LOG",
    ):
        monkeypatch.delenv(name, raising=False)
    use_fake_hydrolog(monkeypatch)


@pytest.fixture
def temporary(monkeypatch, tmp_path):
    """The temporary directory (``TMPDIR``) of the test: the scratch directories go here."""
    directory = tmp_path / "tmp"
    directory.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(directory))
    return directory


@pytest.fixture
def batches(monkeypatch, tmp_path):
    """The batches the fake ran: each its arguments and calls."""
    log = tmp_path / "hydrolog.jsonl"
    monkeypatch.setenv("FAKE_HYDROLOG_LOG", str(log))

    def runs():
        found = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
        return [json.loads(line) for line in found]

    return runs


@pytest.fixture(scope="module")
def built(tmp_path_factory, fixture_roots):
    """
    The fixture data root with the analyses of every station; never written.

    Its raw root gets IMGW-PIB's half-year archives of 2024 (Raba Górna) and the
    data root their series, so IMGW-PIB has published half-years beside ČHMÚ's.
    """
    base = tmp_path_factory.mktemp("built")
    raw = shutil.copytree(fixture_roots.raw.root, base / "raw")
    root = shutil.copytree(fixture_roots.data.root, base / "data")
    for archive in archive_files(SEMIANNUAL, years=[2024]):
        data = (FIXTURES / "store" / "archives" / archive.server_path).read_bytes()
        response = DownloadResult(data, archive.url, None, None, len(data))
        write_archive(raw, archive=archive, response=response)
    build_series(root, raw_root=raw, dataset=SEMIANNUAL)
    with pytest.MonkeyPatch.context() as patch:
        use_fake_hydrolog(patch)
        assert build_analyses(root).status == "new"
    return root


def fill(values: dict[date, float], first: date, last: date, value: float) -> None:
    """``value`` on every day from ``first`` to ``last``."""
    day = first
    while day <= last:
        values[day] = value
        day += timedelta(days=1)


def cells(row: dict[str, str], column: str) -> tuple[str, ...]:
    """Value, flag, start, end and occurrences of a statistic (``H_min``) of a row."""
    (value,) = (name for name in row if name.startswith(f"{column} ["))
    return tuple(
        row[name]
        for name in (
            value,
            f"{column}_flag",
            f"{column}_start",
            f"{column}_end",
            f"{column}_occurrences",
        )
    )


def version_of(root: Path, prefix: str) -> Path:
    """The one analyses version of a provider (``pl.imgw``, ``cz.chmu``)."""
    (version,) = (root / "analyses" / "versions" / prefix).iterdir()
    return version


def records(version: Path) -> dict[str, Any]:
    """The station records of a version (``stations/<code>.json``), by code."""
    document = load(version / "analyses.json")
    return {
        code: load(version / entry["file"])
        for code, entry in document["stations"].items()
    }


def half_years(stations: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    """The stored ``characteristic.*.half_years`` entries, by station and id."""
    return {
        (code, entry["analysis"]): entry
        for code, record in stations.items()
        for entry in record["results"]
        if entry["analysis"].endswith(".half_years")
    }


# --------------------------------------------------------------------------
# The computed file
# --------------------------------------------------------------------------


def test_half_years_of_daily_values_have_the_statistics_of_imgws_file():
    level: dict[date, float] = {}
    fill(level, date(2022, 10, 15), date(2023, 4, 30), 100.0)
    # Two separate runs at the winter minimum, one day at its maximum: mean 100
    fill(level, date(2022, 12, 1), date(2022, 12, 3), 90.0)
    level[date(2023, 3, 10)] = 90.0
    level[date(2023, 4, 30)] = 140.0
    fill(level, date(2023, 5, 1), date(2023, 10, 31), 120.0)
    # Two runs at the summer maximum, the first and the last days: mean 120
    fill(level, date(2023, 5, 1), date(2023, 5, 2), 200.0)
    level[date(2023, 10, 31)] = 200.0
    fill(level, date(2023, 7, 1), date(2023, 7, 4), 60.0)
    fill(level, date(2023, 11, 1), date(2024, 10, 31), 50.0)
    level[date(2024, 5, 10)] = level[date(2024, 5, 12)] = 40.0
    fill(level, date(2024, 6, 1), date(2024, 6, 2), 60.0)
    discharge: dict[date, float] = {}
    fill(discharge, date(2022, 10, 15), date(2023, 4, 30), 2.5)
    fill(discharge, date(2023, 5, 1), date(2023, 10, 31), 4.0)
    del discharge[date(2023, 8, 15)]  # a day without a row of Q
    fill(discharge, date(2023, 11, 1), date(2024, 4, 30), 3.0)
    fill(discharge, date(2024, 5, 1), date(2024, 10, 31), 1.0)
    days: dict[date, dict[str, Measurement]] = {
        day: {"H": Measurement(value, "value")} for day, value in level.items()
    }
    days[date(2024, 2, 29)]["H"] = Measurement(None, "missing")
    for day, value in discharge.items():
        days[day]["Q"] = Measurement(value, "value")

    header, rows = _half_year_table(days, {"H": "cm", "Q": "m3/s"})

    assert header == [
        "date",
        "year",
        "period",
        *(
            column
            for name, unit in (("H", "cm"), ("Q", "m3/s"))
            for statistic in ("min", "mean", "max")
            for column in (
                f"{name}_{statistic} [{unit}]",
                f"{name}_{statistic}_flag",
                f"{name}_{statistic}_start",
                f"{name}_{statistic}_end",
                f"{name}_{statistic}_occurrences",
            )
        ),
    ]
    # Every hydrological year of the days: winter dated November 1, summer May 1
    assert [row[:3] for row in rows] == [
        [start, str(year), period]
        for year in (2022, 2023, 2024)
        for start, period in (
            (f"{year - 1}-11-01", "winter"),
            (f"{year}-05-01", "summer"),
            (f"{year - 1}-11-01", "annual"),
        )
    ]
    table = {(int(row[1]), row[2]): dict(zip(header, row, strict=True)) for row in rows}
    statistics = [f"{name}_{s}" for name in ("H", "Q") for s in ("min", "mean", "max")]
    # 2022: only its last days, no complete half-year
    for period in ("winter", "summer", "annual"):
        assert {cells(table[2022, period], c) for c in statistics} == {MISSING}
    winter, summer, annual = (table[2023, p] for p in ("winter", "summer", "annual"))
    assert [cells(winter, c) for c in statistics] == [
        ("90.0", "value", "2022-12-01", "2023-03-10", "2"),
        ("100.0", "value", "", "", "1"),
        ("140.0", "value", "2023-04-30", "2023-04-30", "1"),
        ("2.5", "value", "2022-11-01", "2023-04-30", "1"),
        ("2.5", "value", "", "", "1"),
        ("2.5", "value", "2022-11-01", "2023-04-30", "1"),
    ]
    # A day without Q: the summer has no Q, and the year no mean of Q
    assert [cells(summer, c) for c in statistics] == [
        ("60.0", "value", "2023-07-01", "2023-07-04", "1"),
        ("120.0", "value", "", "", "1"),
        ("200.0", "value", "2023-05-01", "2023-10-31", "2"),
        MISSING,
        MISSING,
        MISSING,
    ]
    # The year: the mean of both half-years only, as IMGW-PIB publishes it
    assert [cells(annual, c) for c in statistics] == [
        MISSING,
        (annual["H_mean [cm]"], "value", "", "", "1"),
        MISSING,
        MISSING,
        MISSING,
        MISSING,
    ]
    assert float(annual["H_mean [cm]"]) == (181 * 100 + 184 * 120) / 365
    # A day without a value of H (29 February 2024): no winter of H
    winter, summer, annual = (table[2024, p] for p in ("winter", "summer", "annual"))
    assert [cells(winter, c) for c in statistics] == [
        MISSING,
        MISSING,
        MISSING,
        ("3.0", "value", "2023-11-01", "2024-04-30", "1"),
        ("3.0", "value", "", "", "1"),
        ("3.0", "value", "2023-11-01", "2024-04-30", "1"),
    ]
    assert [cells(summer, c) for c in statistics] == [
        ("40.0", "value", "2024-05-10", "2024-05-12", "2"),
        ("50.0", "value", "", "", "1"),
        ("60.0", "value", "2024-06-01", "2024-06-02", "1"),
        ("1.0", "value", "2024-05-01", "2024-10-31", "1"),
        ("1.0", "value", "", "", "1"),
        ("1.0", "value", "2024-05-01", "2024-10-31", "1"),
    ]
    assert [cells(annual, c) for c in statistics] == [
        MISSING,
        MISSING,
        MISSING,
        MISSING,
        (annual["Q_mean [m3/s]"], "value", "", "", "1"),
        MISSING,
    ]
    assert float(annual["Q_mean [m3/s]"]) == (182 * 3.0 + 184 * 1.0) / 366


def test_the_file_of_a_chmu_station_is_imgws_export_of_its_daily_values(
    fixture_root, tmp_path
):
    entry = current_version(fixture_root, slot=f"series:{CHMU_DAILY}")
    assert entry is not None and entry.version is not None
    target = tmp_path / "half_years.csv"

    report = _export_half_years(entry.version, station=CHMU_HYDRO, output=target)

    text = target.read_text(encoding="utf-8")
    assert report.files[0].sha256 == sha256(target)
    # The columns and units of IMGW-PIB's half-year export
    first_line = GOLDEN.read_text(encoding="utf-8").splitlines(keepends=True)[0]
    assert text.splitlines(keepends=True)[0] == first_line
    table = list(csv.DictReader(io.StringIO(text, newline="")))
    exported = "".join(export_series(entry.version, station=CHMU_HYDRO))
    daily = list(csv.DictReader(io.StringIO(exported, newline="")))
    # ČHMÚ's lines, as the export of the daily series has them
    assert trailing_lines(table) == trailing_lines(daily) == attribution("chmu")
    # Each half-year from the daily values: only one with a value every day
    values = {
        (variable, date.fromisoformat(row["date"])): row[f"{variable} [{unit}]"]
        for row in daily
        for variable, unit in (("H", "cm"), ("Q", "m3/s"), ("T", "degC"))
    }
    spans = {"winter": ((11, 1), (4, 30)), "summer": ((5, 1), (10, 31))}
    complete = 0
    for row in table:
        year = int(row["year"])
        for variable in ("H", "Q", "T"):
            if row["period"] == "annual":
                assert cells(row, f"{variable}_min") == MISSING
                assert cells(row, f"{variable}_max") == MISSING
                continue
            (month, day), (last_month, last_day) = spans[row["period"]]
            first = date(year - 1 if month == 11 else year, month, day)
            found = []
            while first <= date(year, last_month, last_day):
                found.append(values.get((variable, first), ""))
                first += timedelta(days=1)
            if "" in found:
                assert {
                    cells(row, f"{variable}_{s}") for s in ("min", "mean", "max")
                } == {MISSING}
                continue
            complete += 1
            numbers = [float(cell) for cell in found]
            low, mean, high = (
                cells(row, f"{variable}_{s}") for s in ("min", "mean", "max")
            )
            assert (float(low[0]), low[1]) == (min(numbers), "value")
            assert (float(high[0]), high[1]) == (max(numbers), "value")
            assert float(mean[0]) == pytest.approx(math.fsum(numbers) / len(numbers))
    assert complete > 0


# --------------------------------------------------------------------------
# Building, reading, exporting
# --------------------------------------------------------------------------


def test_a_build_stores_chmus_computed_half_years_beside_imgws_published(built):
    chmu_version = version_of(built, "cz.chmu")
    chmu = records(chmu_version)
    imgw = records(version_of(built, "pl.imgw"))

    computed = half_years(chmu)

    assert {analysis for code, analysis in computed if code == CHMU_HYDRO} == {
        f"characteristic.{variable}.half_years" for variable in ("H", "Q", "T")
    }
    for (code, analysis), entry in computed.items():
        assert (entry["derived"], entry["datasets"], entry["status"]) == (
            "half_years",
            [CHMU_DAILY],
            "ok",
        )
        assert entry["options"] == {
            "half_year_file": f"{code}_chmu_hydro_daily_half_years.csv",
            "parameter": analysis.split(".")[1],
        }
        # The fake answers with the lines of the file it read: ČHMÚ's
        line = load(chmu_version / entry["file"])
        assert tuple(line["attribution"]) == attribution("chmu").attribution
    # The other analyses of ČHMÚ read the daily series, the flood frequency too
    for code, record in chmu.items():
        for entry in record["results"]:
            if (code, entry["analysis"]) not in computed:
                assert entry["derived"] is None
                assert "half_year_file" not in entry["options"]
    # The station's record names its daily series once, with its series export
    entry = current_version(built, slot=f"series:{CHMU_DAILY}")
    assert entry is not None and entry.version is not None
    exported = "".join(export_series(entry.version, station=CHMU_HYDRO))
    (source,) = chmu[CHMU_HYDRO]["inputs"]
    assert (source["dataset"], source["export_sha256"]) == (
        CHMU_DAILY,
        sha256(exported.encode("utf-8")),
    )
    # IMGW-PIB keeps the half-year file it publishes
    published = half_years(imgw)
    assert set(published) == {
        (RABA, f"characteristic.{variable}.half_years") for variable in ("H", "Q", "T")
    }
    for (code, analysis), entry in published.items():
        assert (entry["derived"], entry["datasets"]) == (None, [SEMIANNUAL])
        assert entry["options"] == {
            "half_year_file": f"{code}_imgw_hydro_semiannual.csv",
            "parameter": analysis.split(".")[1],
        }


def test_reading_and_exporting_say_which_half_years_were_computed(built):
    summaries = list_analyses(root=built, station=CHMU_HYDRO)

    derived = {summary.analysis: summary.derived for summary in summaries}
    assert derived == {
        name: "half_years" if name.endswith(".half_years") else None for name in derived
    }
    assert derived["characteristic.Q.half_years"] == "half_years"
    result = read_analysis(
        root=built, station=CHMU_HYDRO, analysis="characteristic.Q.half_years"
    )
    assert (result.status, result.derived) == ("ok", "half_years")
    daily = read_analysis(root=built, station=CHMU_HYDRO, analysis="characteristic.Q")
    assert daily.derived is None
    published = read_analysis(
        root=built, station=RABA, analysis="characteristic.Q.half_years"
    )
    assert (published.derived, published.inputs[0].dataset) == (None, SEMIANNUAL)

    (line,) = export_analyses(root=built, station=CHMU_HYDRO)
    document = json.loads(line)
    assert {item["analysis"]: item["derived"] for item in document["results"]} == (
        derived
    )

    chosen = ["characteristic.Q", "characteristic.Q.half_years"]
    text = "".join(
        export_analyses(root=built, station=CHMU_HYDRO, analyses=chosen, format="csv")
    )
    head = text.splitlines()[0].split(",")
    assert head[head.index("value") + 1 :] == [
        "derived",
        "attribution",
        "terms_notice",
    ]
    table = list(csv.DictReader(io.StringIO(text, newline="")))
    assert {(row["analysis"], row["derived"]) for row in table} == {
        ("characteristic.Q", ""),
        ("characteristic.Q.half_years", "half_years"),
    }


def test_on_the_fly_the_half_years_are_computed_of_the_current_daily_series(
    fixture_root, temporary, batches, tmp_path
):
    before = (snapshot(fixture_root), stamps(fixture_root))

    result = compute_analysis(
        fixture_root,
        station=CHMU_HYDRO,
        analysis="characteristic.Q.half_years",
        options={"first_year": 2023},
    )

    assert (result.stored, result.status, result.derived) == (False, "ok", "half_years")
    assert result.options == {
        "half_year_file": f"{CHMU_HYDRO}_chmu_hydro_daily_half_years.csv",
        "parameter": "Q",
        "first_year": 2023,
    }
    # Hydrolog read the computed file alone; its SHA-256 names it
    assert [call["options"] for run in batches() for call in run["calls"]] == [
        dict(result.options)
    ]
    entry = current_version(fixture_root, slot=f"series:{CHMU_DAILY}")
    assert entry is not None and entry.version is not None and entry.meta is not None
    computed = _export_half_years(
        entry.version, station=CHMU_HYDRO, output=tmp_path / "computed.csv"
    )
    assert result.inputs == (
        AnalysisSource(
            CHMU_DAILY,
            entry.version.parent.relative_to(fixture_root).as_posix(),
            entry.meta.sha256,
            read_series_index(entry.version).stations[CHMU_HYDRO].sha256,
            computed.files[0].sha256,
        ),
    )
    assert (snapshot(fixture_root), stamps(fixture_root)) == before
    assert list(temporary.iterdir()) == []


@pytest.mark.hydrolog
@pytest.mark.skipif(
    REAL_HYDROLOG is None,
    reason="needs Hydrolog's program: OBSERWATOR_HYDROLOG_COMMAND",
)
def test_the_real_hydrolog_takes_the_half_years_of_the_computed_file(
    fixture_root, monkeypatch, temporary, tmp_path
):
    monkeypatch.setenv("OBSERWATOR_HYDROLOG_COMMAND", str(REAL_HYDROLOG))

    result = compute_analysis(
        fixture_root, station=CHMU_HYDRO, analysis="characteristic.Q.half_years"
    )

    assert (result.status, result.derived) == ("ok", "half_years"), result.error
    assert result.envelope is not None
    found = result.envelope["result"]
    entry = current_version(fixture_root, slot=f"series:{CHMU_DAILY}")
    assert entry is not None and entry.version is not None
    target = tmp_path / "half_years.csv"
    _export_half_years(entry.version, station=CHMU_HYDRO, output=target)
    with target.open(encoding="utf-8", newline="") as stream:
        table = [row for row in csv.DictReader(stream) if row["Q_min_flag"] == "value"]
    # Hydrolog's first degree is the file's: each half-year with its extremes' days
    assert found["source"] == "half_years"
    assert {
        (item["year"], period): tuple(
            item[period][key] for key in ("min", "min_date", "mean", "max", "max_date")
        )
        for item in found["years"]
        for period in ("winter", "summer")
        if item[period]["mean"] is not None
    } == {
        (int(row["year"]), row["period"]): (
            float(row["Q_min [m3/s]"]),
            row["Q_min_start"],
            float(row["Q_mean [m3/s]"]),
            float(row["Q_max [m3/s]"]),
            row["Q_max_start"],
        )
        for row in table
        if row["period"] != "annual"
    }
    assert list(temporary.iterdir()) == []
