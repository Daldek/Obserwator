"""
„Pobierz” on the fixture root (GUI plan D13, D14).

Every series file the panel offers, in each format, is byte for byte the file of
`export_series` with the same options; the command line it shows for a format, run on the
fixture root (`obserwator.run_command`), makes that very file; and the hand-off of the daily
series to Hydrolog, saved or copied, is a `nogat-handoff/1` valid against Nogat's schema
that holds the series' days with values.
"""

from __future__ import annotations

import csv
import json
import urllib.parse
from pathlib import Path
from typing import Any

import jsonschema
import pytest

from obserwator import export_series, parse_command, run_command
from tests.e2e.conftest import FIXTURE_STATIONS

expect = pytest.importorskip("playwright.sync_api").expect

STATIONS = [
    FIXTURE_STATIONS["hydro"],
    FIXTURE_STATIONS["hydro_chmi"],
    FIXTURE_STATIONS["meteo"],
    FIXTURE_STATIONS["meteo_chmi"],
]
HYDRO_DAILY = {
    FIXTURE_STATIONS["hydro"]: "pl.imgw.hydro_daily",
    FIXTURE_STATIONS["hydro_chmi"]: "cz.chmi.hydro_daily",
}
WAIT = 20_000
"""How long the list of files may take to load [ms]."""
HANDOFF_SCHEMA = (
    Path(__file__).resolve().parents[2] / "schemas" / "nogat" / "handoff-1.schema.json"
)


def files_card(open_page: Any, code: str) -> Any:
    """„Pobierz” of a station, open, with its files listed."""
    page = open_page(f"?station={code}&section=pobierz")
    item = page.locator('.acc-item[data-section="pobierz"]')
    item.locator(".files a").first.wait_for(timeout=WAIT)
    return item


def address(href: str) -> tuple[str, str, str]:
    """The dataset, the station and the format of a file's address."""
    parsed = urllib.parse.urlsplit(href)
    *_, dataset, code = parsed.path.split("/")
    query = urllib.parse.parse_qs(parsed.query)
    return urllib.parse.unquote(dataset), urllib.parse.unquote(code), query["format"][0]


def download(link: Any) -> tuple[str, bytes]:
    """The file a link gives: its name and its bytes."""
    with link.page.expect_download(timeout=WAIT) as started:
        link.click()
    got = started.value
    return got.suggested_filename, Path(got.path()).read_bytes()


@pytest.mark.parametrize("code", STATIONS)
def test_every_series_file_is_the_export_of_the_same_options(
    open_page: Any, gui_root: Path, tmp_path: Path, code: str
) -> None:
    item = files_card(open_page, code)
    links = item.locator(".files a")
    formats = set()
    for index in range(links.count()):
        link = links.nth(index)
        dataset, station, fmt = address(link.get_attribute("href"))
        assert station == code
        name, body = download(link)
        expected = tmp_path / f"expected.{fmt}"
        export_series(
            root=gui_root,
            dataset=dataset,
            station=code,
            format="parquet"
            if fmt == "parquet"
            else "json"
            if fmt == "json"
            else "csv",
            output=expected,
        )
        assert name == link.get_attribute("download")
        assert body == expected.read_bytes(), (dataset, fmt)
        formats.add(fmt)
    assert formats == {"csv", "json", "parquet"}


@pytest.mark.parametrize("code", STATIONS)
def test_the_command_line_shown_makes_the_same_file(
    open_page: Any, gui_root: Path, tmp_path: Path, code: str
) -> None:
    item = files_card(open_page, code)
    series = item.locator("section.ana", has=item.page.locator(".files"))
    for index in range(series.count()):
        part = series.nth(index)
        links = part.locator(".files a")
        for number in range(links.count()):
            link = links.nth(number)
            _, _, fmt = address(link.get_attribute("href"))
            name, body = download(link)
            choice = part.locator(".seg button").nth(number)
            choice.click()
            expect(choice).to_have_attribute("aria-checked", "true")
            line = part.locator("pre.code").inner_text()

            call = parse_command(line)
            assert call.command == "series export"
            assert "root" not in call.options, line
            assert call.options["output"] == name
            assert call.options.get("format", "csv") == fmt
            made = tmp_path / f"{index}-{name}"
            run_command(
                call.command,
                options={**call.options, "root": gui_root, "output": made},
            )
            assert made.read_bytes() == body, line


@pytest.mark.parametrize("code", sorted(HYDRO_DAILY))
@pytest.mark.parametrize("how", ["file", "clipboard"])
def test_the_hand_off_is_a_valid_nogat_hand_off_of_the_daily_series(
    open_page: Any, gui_root: Path, tmp_path: Path, code: str, how: str
) -> None:
    exported = tmp_path / "series.csv"
    export_series(
        root=gui_root, dataset=HYDRO_DAILY[code], station=code, output=exported
    )
    with exported.open(encoding="utf-8", newline="") as stream:
        records = list(csv.DictReader(stream))
    column = next(key for key in records[0] if key.startswith("Q ["))
    days = [
        (record["date"], float(record[column]))
        for record in records
        if record[column] != "" and record["Q_flag"] != "accumulated"
    ]
    item = files_card(open_page, code)
    page = item.page
    box = item.locator(".handoff-var").first
    buttons = box.locator(".btn-row button")
    if how == "file":
        with page.expect_download(timeout=WAIT) as started:
            buttons.nth(1).click()
        text = Path(started.value.path()).read_text(encoding="utf-8")
    else:
        page.context.grant_permissions(["clipboard-read", "clipboard-write"])
        buttons.nth(0).click()
        expect(box.locator('[role="status"]')).to_be_visible()
        field = box.locator("textarea")
        text = (
            field.input_value()
            if field.is_visible()
            else page.evaluate("navigator.clipboard.readText()")
        )
    document = json.loads(text)

    schema = json.loads(HANDOFF_SCHEMA.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator(schema).validate(document)
    payload = document["payload"]
    assert (payload["schema"], payload["variable"], payload["step"]) == (
        "hydrolog-series/1",
        "Q",
        "day",
    )
    held = [
        (day, value)
        for day, value in zip(payload["dates"], payload["values"], strict=True)
        if value is not None
    ]
    assert held == days
    assert document["provenance"]["series"]["station"] == code
    assert document["attribution"]
