"""Tests of download_archives on recorded IMGW answers (respx-mocked HTTP)."""

from pathlib import Path
from urllib.parse import quote

import httpx
import pytest

from obserwator.datasets import archive_files
from obserwator.exceptions import ObserwatorValidationError
from obserwator.fetch import _download_files, download_archives
from obserwator.store.types import Notice, Progress
from obserwator.urls import IMGW_PUBLIC_DATA_URL

ARCHIVES = Path(__file__).parents[1] / "fixtures" / "store" / "archives"
# Real files and folder indexes of danepubliczne.imgw.pl (recorded 2026-11-14): the
# index of dane_aktynometryczne keeps the rows of Kłodzko and the summary only, the
# index of Kłodzko/Źródłowe/2006 the row of KLO03-06.DAN only.
DOWNLOAD_ONLY = Path(__file__).parents[1] / "fixtures" / "download_only"
ACTINOMETRIC = "pl.imgw.actinometric"
INDEX = f"{IMGW_PUBLIC_DATA_URL}/dane_aktynometryczne/"
SUMMARY = "Promieniowanie słoneczne_zakres danych.xlsx"
SEMIANNUAL = "pl.imgw.hydro_semiannual"
FILES = archive_files(SEMIANNUAL, years=2024)  # polr_H, polr_Q, polr_T


def _record(respx_mock, *, failing: str | None = None) -> None:
    for archive in FILES:
        if archive.server_path.endswith(f"{failing}_2024.zip"):
            respx_mock.get(archive.url).respond(503)
        else:
            body = (ARCHIVES / archive.server_path).read_bytes()
            respx_mock.get(archive.url).respond(content=body)


def _tree(directory: Path) -> list[str]:
    return sorted(p.relative_to(directory).as_posix() for p in directory.rglob("*"))


def test_files_land_under_server_path_with_slots(respx_mock, tmp_path):
    _record(respx_mock)
    report = download_archives(SEMIANNUAL, years="2024", output_dir=tmp_path / "out")
    output = tmp_path / "out"
    assert (report.mode, report.output_dir, report.root) == ("plain", output, None)
    assert not report.cancelled
    assert [item.slot for item in report.items] == [
        f"archive:{SEMIANNUAL}:2024/polr_{param}_2024.zip" for param in "HQT"
    ]
    for item, archive in zip(report.items, FILES, strict=True):
        assert item.status == "downloaded" and item.url == archive.url
        assert item.path == output / archive.server_path
        assert item.path.read_bytes() == (ARCHIVES / archive.server_path).read_bytes()
        assert (item.error, item.error_code) == (None, None)
    assert not [name for name in _tree(output) if name.endswith(".part")]


def test_meteo_monthly_slot_and_path_follow_the_folder(respx_mock, tmp_path):
    (archive,) = archive_files("pl.imgw.meteo_synop_monthly", years=1998)
    respx_mock.get(archive.url).respond(
        content=(ARCHIVES / FILES[0].server_path).read_bytes()
    )
    report = download_archives(
        "meteo/miesieczne/synop", years=1998, output_dir=tmp_path
    )
    (item,) = report.items
    assert item.slot == (
        "archive:pl.imgw.meteo_synop_monthly:1996_2000/1996_2000_m_s.zip"
    )
    assert item.path == (
        tmp_path / "dane_meteorologiczne/miesieczne/synop/1996_2000/1996_2000_m_s.zip"
    )


def test_daily_and_term_archives_of_one_name_never_collide(respx_mock, tmp_path):
    # dobowe/klimat and terminowe/klimat both publish 2001_01_k.zip (other bytes).
    daily, terms = "pl.imgw.meteo_climate_daily", "pl.imgw.meteo_climate_terms"
    climate = ARCHIVES / "dane_meteorologiczne" / "dobowe" / "klimat"
    bodies = {
        daily: (climate / "2001" / "2001_01_k.zip").read_bytes(),
        terms: (climate / "2004" / "2004_02_k.zip").read_bytes(),
    }
    for dataset, body in bodies.items():
        (archive,) = archive_files(dataset, years=2001, months=1)
        respx_mock.get(archive.url).respond(content=body)
    items = [
        item
        for dataset in bodies
        for item in download_archives(
            dataset, years=2001, months=1, output_dir=tmp_path
        ).items
    ]
    assert [item.slot for item in items] == [
        f"archive:{daily}:2001/2001_01_k.zip",
        f"archive:{terms}:2001/2001_01_k.zip",
    ]
    assert [item.path.relative_to(tmp_path).as_posix() for item in items] == [
        "dane_meteorologiczne/dobowe/klimat/2001/2001_01_k.zip",
        "dane_meteorologiczne/terminowe/klimat/2001/2001_01_k.zip",
    ]
    assert [item.path.read_bytes() for item in items] == [bodies[daily], bodies[terms]]
    # both downloads merge their lines into one ATTRIBUTION.txt (ADR-012 D5)
    assert [name for name in _tree(tmp_path) if Path(name).suffix] == [
        "ATTRIBUTION.txt",
        "dane_meteorologiczne/dobowe/klimat/2001/2001_01_k.zip",
        "dane_meteorologiczne/terminowe/klimat/2001/2001_01_k.zip",
    ]


def test_http_error_fails_one_item_and_others_download(respx_mock, tmp_path):
    _record(respx_mock, failing="Q")
    report = download_archives(SEMIANNUAL, years=2024, output_dir=tmp_path)
    assert [item.status for item in report.items] == [
        "downloaded",
        "failed",
        "downloaded",
    ]
    failed = report.items[1]
    assert failed.error_code == "source_unavailable"
    assert failed.path is None and "HTTP 503" in (failed.error or "")
    assert not (tmp_path / FILES[1].server_path).exists()
    assert report.cancelled is False


def test_corrupt_archive_is_data_error_item(respx_mock, tmp_path):
    for archive in FILES:
        respx_mock.get(archive.url).respond(content=b"<html>to nie zip</html>")
    report = download_archives(
        SEMIANNUAL, years=2024, params=["T"], output_dir=tmp_path
    )
    (item,) = report.items
    assert (item.status, item.error_code) == ("failed", "data_error")
    assert _tree(tmp_path) == []


def test_write_failure_leaves_neither_file_nor_part(respx_mock, tmp_path, monkeypatch):
    _record(respx_mock)

    def refuse(source, target):
        raise PermissionError("brak prawa zapisu")

    monkeypatch.setattr("obserwator.output.os.replace", refuse)
    report = download_archives(
        SEMIANNUAL, years=2024, params=["H"], output_dir=tmp_path
    )
    (item,) = report.items
    assert (item.status, item.error_code, item.path) == ("failed", "io_error", None)
    assert [name for name in _tree(tmp_path) if Path(name).suffix] == []


def test_cancel_between_files_reports_rest_as_cancelled(respx_mock, tmp_path):
    _record(respx_mock)
    answers = iter([False, True])
    report = download_archives(
        SEMIANNUAL, years=2024, output_dir=tmp_path, cancel=lambda: next(answers)
    )
    assert report.cancelled is True
    assert [item.status for item in report.items] == [
        "downloaded",
        "cancelled",
        "cancelled",
    ]
    assert all(item.path is None for item in report.items[1:])
    assert [name for name in _tree(tmp_path) if name.endswith(".zip")] == [
        FILES[0].server_path
    ]
    assert respx_mock.calls.call_count == 1


def test_license_notice_once_after_first_downloaded_file(respx_mock, tmp_path):
    _record(respx_mock, failing="H")
    events: list[object] = []
    download_archives(
        SEMIANNUAL,
        years=2024,
        output_dir=tmp_path,
        on_progress=events.append,
        on_notice=events.append,
    )
    assert [
        event.code if isinstance(event, Notice) else event.status
        for event in events
        if isinstance(event, Notice | Progress)
    ] == ["failed", "downloaded", "license_terms", "downloaded"]


def test_no_license_notice_when_nothing_downloaded(respx_mock, tmp_path):
    for archive in FILES:
        respx_mock.get(archive.url).mock(side_effect=httpx.ConnectError)
    notices: list[Notice] = []
    report = download_archives(
        SEMIANNUAL, years=2024, output_dir=tmp_path, on_notice=notices.append
    )
    assert {item.error_code for item in report.items} == {"source_unavailable"}
    assert notices == []


@pytest.mark.parametrize(
    "dataset, options, option",
    [
        ("pl.imgw.nieznany", {"years": 2024}, "dataset"),
        (SEMIANNUAL, {"years": "2024-x"}, "years"),
        ("pl.imgw.hydro_daily", {"years": 2024, "params": ["Q"]}, "params"),
        (ACTINOMETRIC, {"years": 2006, "stations": ["351160424"]}, "stations"),
        (ACTINOMETRIC, {"years": 1989}, "years"),
        ("pl.imgw.meteo_synop_terms", {"years": 2024}, "stations"),
    ],
)
def test_invalid_options_fail_before_any_request_or_directory(
    respx_mock, tmp_path, dataset, options, option
):
    with pytest.raises(ObserwatorValidationError) as error:
        download_archives(dataset, output_dir=tmp_path / "out", **options)
    assert error.value.details["option"] == option
    assert not respx_mock.calls and not (tmp_path / "out").exists()


def test_synop_station_files_download_and_an_absent_station_is_not_published(
    respx_mock, tmp_path
):
    # The station 230 has a 1966_1970 archive; 999 is no station (codes in order).
    present, absent = archive_files(
        "meteo/terminowe/synop", years=1968, stations=["352150999", "351150230"]
    )
    body = (DOWNLOAD_ONLY / "1966_1970_230_s.zip").read_bytes()
    respx_mock.get(absent.url).respond(404)
    respx_mock.get(present.url).respond(content=body)

    report = download_archives(
        "pl.imgw.meteo_synop_terms",
        years=1968,
        stations=["351150230", "352150999"],
        output_dir=tmp_path,
    )

    assert [(item.slot, item.status) for item in report.items] == [
        (
            "archive:pl.imgw.meteo_synop_terms:1966_1970/1966_1970_230_s.zip",
            "downloaded",
        ),
        (
            "archive:pl.imgw.meteo_synop_terms:1966_1970/1966_1970_999_s.zip",
            "not_published",
        ),
    ]
    assert report.items[1].error_code is None
    assert (tmp_path / present.server_path).read_bytes() == body
    assert not (tmp_path / absent.server_path).exists()


def test_warning_archive_lands_under_its_path_outside_the_measurement_data(
    respx_mock, tmp_path
):
    body = (DOWNLOAD_ONLY / "ost_hydro_2018_12.zip").read_bytes()
    respx_mock.get(
        "https://danepubliczne.imgw.pl/data/arch/ost_hydro/2018/12.zip"
    ).respond(content=body)

    report = download_archives(
        "pl.imgw.warnings_hydro_archive", years=2018, months=12, output_dir=tmp_path
    )

    (item,) = report.items
    assert (item.slot, item.status) == (
        "archive:pl.imgw.warnings_hydro_archive:2018/12.zip",
        "downloaded",
    )
    assert item.path == tmp_path / "arch" / "ost_hydro" / "2018" / "12.zip"
    assert item.path.read_bytes() == body


def _index(respx_mock) -> None:
    """The recorded folder indexes of the actinometric data (Kłodzko and the summary)."""
    pages = {
        "": "akt_root",
        "Kłodzko/": "akt_klodzko",
        "Kłodzko/Zweryfikowane/": "akt_klodzko_zweryfikowane",
        "Kłodzko/Źródłowe/": "akt_klodzko_zrodlowe",
        "Kłodzko/Zweryfikowane/2006/": "akt_klodzko_zweryfikowane_2006",
        "Kłodzko/Źródłowe/2006/": "akt_klodzko_zrodlowe_2006",
        "Kłodzko/Źródłowe/1991-1992/": "akt_klodzko_zrodlowe_1991-1992",
    }
    for relative, name in pages.items():
        respx_mock.get(INDEX + quote(relative)).respond(
            content=(DOWNLOAD_ONLY / f"{name}.html").read_bytes()
        )


def test_actinometric_files_are_found_in_the_index_whatever_the_folder_names(
    respx_mock,
):
    _index(respx_mock)

    files = _download_files(
        ACTINOMETRIC, years=1992, months=None, params=None, stations=None
    )

    # Only the year folder holding 1992 is entered (a range folder), the summary
    # outside the year folders belongs to every selection.
    assert [(item.server_path, item.year) for item in files] == [
        ("dane_aktynometryczne/Kłodzko/Źródłowe/1991-1992/Klodzko1991-1992.xls", 1991),
        (f"dane_aktynometryczne/{SUMMARY}", None),
    ]
    assert files[0].period_end.year == 1992
    entered = {str(call.request.url) for call in respx_mock.calls}
    assert INDEX + quote("Kłodzko/Zweryfikowane/2006/") not in entered


def test_actinometric_download_writes_the_files_as_published(respx_mock, tmp_path):
    _index(respx_mock)
    bodies = {
        "Kłodzko/Zweryfikowane/2006/KLO03-06.DAN": "KLO03-06_zweryfikowane.DAN",
        "Kłodzko/Źródłowe/2006/KLO03-06.DAN": "KLO03-06_zrodlowe.DAN",
        SUMMARY: "zakres_danych.xlsx",
    }
    for relative, name in bodies.items():
        respx_mock.get(INDEX + quote(relative)).respond(
            content=(DOWNLOAD_ONLY / name).read_bytes()
        )

    report = download_archives(ACTINOMETRIC, years=2006, output_dir=tmp_path)

    # One name in two folder kinds gives two files; none of them is a ZIP archive.
    assert [(item.slot, item.status) for item in report.items] == [
        (f"archive:{ACTINOMETRIC}:Kłodzko/Źródłowe/2006/KLO03-06.DAN", "downloaded"),
        (
            f"archive:{ACTINOMETRIC}:Kłodzko/Zweryfikowane/2006/KLO03-06.DAN",
            "downloaded",
        ),
        (f"archive:{ACTINOMETRIC}:{SUMMARY}", "downloaded"),
    ]
    for relative, name in bodies.items():
        written = tmp_path / "dane_aktynometryczne" / relative
        assert written.read_bytes() == (DOWNLOAD_ONLY / name).read_bytes()


def test_actinometric_index_is_not_read_for_a_store_download(respx_mock, tmp_path):
    with pytest.raises(ObserwatorValidationError) as error:
        download_archives(ACTINOMETRIC, years=2006, root=tmp_path / "raw")
    assert error.value.details["reason"] == "not_in_store"
    assert not respx_mock.calls
