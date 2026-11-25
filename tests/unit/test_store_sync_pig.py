"""store check|sync of PIG-PIB's tables and the night's harvest by watermark (ADR-035).

The readings (``pl.pig.groundwater_readings``, check scope ``publication``) are the one
file the service publishes now, named by one statistics query; a sync pages the table
in one run and compares the run's content with the slot's current version
(``pig-json/1``). The automatic measurements (``pl.pig.groundwater_operational``) are
harvested by ``OBJECTID`` watermark and sealed into the run day's capture. The answers
are the rows recorded on 2026-11-24 (``pig_recordings.json``), served with ArcGIS's
semantics by `obserwator.testing._PigService`; the run's clock
(`obserwator.fetch._clock`), the spool's and the writer's follow a fake clock, which the
pacing moves instead of sleeping.
"""

import copy
import gzip
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

import pytest
import respx

from obserwator import captures, fetch
from obserwator.attribution import attribution
from obserwator.commands import run_command
from obserwator.exceptions import ObserwatorValidationError
from obserwator.messages import message
from obserwator.store import check_store, init_store, sync_store, writer
from obserwator.testing import _PigService
from tests.unit.test_paced import FakeClock

READINGS = "pl.pig.groundwater_readings"
CHEMISTRY = "pl.pig.groundwater_chemistry"
OPERATIONAL = "pl.pig.groundwater_operational"
OCTOBER = "mwp/MapServer/1/MWP_2026-10.jsonl.gz"
MONTH = "MWP_2026-10.jsonl.gz"
NOW = datetime(2026, 11, 25, 6, 45, tzinfo=UTC)
TODAY = NOW.date()
LAST_ROW = 60938323
"""The newest OBJECTID of the recorded hourly rows."""


@pytest.fixture(autouse=True)
def clock(tmp_path, monkeypatch):
    """The test's spool and ``nogat.toml``; the run's, spool's and writer's clock."""
    monkeypatch.setenv("OBSERWATOR_STATE_DIR", str(tmp_path / "state"))
    config = tmp_path / "nogat.toml"
    config.write_text("", encoding="utf-8")
    monkeypatch.setenv("NOGAT_CONFIG", str(config))
    fake = FakeClock(NOW)
    monkeypatch.setattr(fetch, "_clock", lambda: fake)
    monkeypatch.setattr(fetch, "_ARCGIS", fetch._Spacing())
    monkeypatch.setattr(captures, "_now", fake.now)

    class Clock(datetime):
        """``downloaded_at`` and the day of a plain write follow the fake clock."""

        @classmethod
        def now(cls, tz=None):
            return fake.now().astimezone(tz)

    monkeypatch.setattr(writer, "datetime", Clock)
    monkeypatch.setattr(fetch, "datetime", Clock)
    return fake


@pytest.fixture
def raw(tmp_path):
    return init_store(tmp_path / "raw").root


@pytest.fixture
def service():
    return _PigService()


@pytest.fixture
def server(service):
    """PIG-PIB's services answer from the recorded rows; any other request fails."""
    with respx.mock(assert_all_called=False) as mock:
        mock.route(host="cbdgmapa.pgi.gov.pl").mock(side_effect=service)
        yield mock


def readings(service):
    return service.tables["mwp/MapServer/1"].rows


def hours(service):
    return service.tables["mwp_auto/MapServer/2"].rows


def reading(service, point, day):
    """The recorded row of a point's reading of a day (``YYYY-MM-DD``)."""
    return next(
        row
        for row in readings(service)
        if row["attributes"]["OTWOR_ID"] == point
        and row["attributes"]["DATA_POMIARU"] == f" {day}"
    )


def answers(version):
    """Every line of a stored container of answers."""
    text = gzip.decompress(Path(version).read_bytes()).decode("utf-8")
    return [json.loads(line) for line in text.splitlines()]


def form(address):
    return dict(parse_qsl(urlsplit(address).query, keep_blank_values=True))


def sidecar(version):
    return json.loads(Path(f"{version}.meta.json").read_text(encoding="utf-8"))


def versions(raw, server_path):
    """The version directories of a slot (not its observation register)."""
    slot = raw / "archives" / "versions" / server_path.removesuffix(".jsonl.gz")
    if not slot.is_dir():
        return []
    return sorted(path.name for path in slot.iterdir() if path.name != "observations")


def filled_w(period, day):
    (line,) = [
        line
        for line in attribution(
            "pig", processed=False, period=period, date=day
        ).attribution
        if line.startswith("Źródło danych: ")
    ]
    return line


def until(minutes):
    """The ``HH:MM`` of local time ``minutes`` after the fake clock's start."""
    return (NOW + timedelta(minutes=minutes)).astimezone().strftime("%H:%M")


# --------------------------------------------------------------------------
# The readings: the month the service publishes now (W4, W5)
# --------------------------------------------------------------------------


def test_a_check_names_the_month_of_the_rows_by_one_query(raw, server, service):
    plan = check_store(raw, datasets=[READINGS])

    (item,) = plan.items
    assert (item.archive.server_path, item.status) == (OCTOBER, "missing")
    assert plan.requests == {"made": 1, "planned": 3}
    ((path, asked),) = service.requests
    assert path == "mwp/MapServer/1/query"
    assert json.loads(asked["outStatistics"])[0]["onStatisticField"] == "DATA_POMIARU"


def test_a_sync_keeps_the_runs_answers_with_w_filled(raw, server, service):
    notices = []

    report = sync_store(raw, datasets=[READINGS], on_notice=notices.append)

    (result,) = report.items
    assert (result.slot, result.status) == (f"archive:{READINGS}:{MONTH}", "new")
    lines = answers(result.version)
    forms = [form(line["address"]) for line in lines]
    # The count before, one page of 168 rows in OBJECTID order, the count after.
    assert [item.get("returnCountOnly") for item in forms] == ["true", None, "true"]
    assert (forms[1]["resultOffset"], forms[1]["orderByFields"]) == ("0", "OBJECTID")
    assert {line["status"] for line in lines} == {200}
    assert len(json.loads(lines[1]["body"])["features"]) == 168
    meta = sidecar(result.version)
    assert meta["content_form"] == "pig-json/1"
    # W names the year of the readings and the day they were acquired (DEV-20.13).
    assert meta["license"]["attribution"] == filled_w("2026", "2026-11-25")
    (terms,) = [notice for notice in notices if notice.code == "license_terms"]
    assert filled_w("2026", "2026-11-25") in terms.message


def test_a_reload_with_renumbered_ids_and_other_pages_is_unchanged(
    raw, server, service, monkeypatch
):
    sync_store(raw, datasets=[READINGS])
    rows = readings(service)
    for number, row in enumerate(reversed(rows), start=500):
        row["attributes"]["OBJECTID"] = number
    monkeypatch.setattr(fetch, "ARCGIS_PAGE", 50)
    notices = []

    report = sync_store(raw, datasets=[READINGS], on_notice=notices.append)

    (result,) = report.items
    assert result.status == "unchanged"
    assert "content_unchanged" in {notice.code for notice in notices}
    assert len(versions(raw, OCTOBER)) == 1
    # Four pages of 50 were asked this time: the paging is no part of the content.
    pages = [asked for path, asked in service.requests if "resultOffset" in asked]
    assert [asked["resultOffset"] for asked in pages[-4:]] == ["0", "50", "100", "150"]


def test_one_changed_value_is_a_new_version_with_month_republished(
    raw, server, service
):
    sync_store(raw, datasets=[READINGS])
    row = reading(service, 6495, "2026-10-15")
    row["attributes"]["GLEBOKOSC_ZWIERCIADLA"] += 0.01
    notices = []

    report = sync_store(raw, datasets=[READINGS], on_notice=notices.append)

    (result,) = report.items
    assert result.status == "new"
    # The earlier version stays; the notice counts the reading changed.
    assert len(versions(raw, OCTOBER)) == 2
    (republished,) = [n for n in notices if n.code == "month_republished"]
    assert republished.message == message(
        "pig.month_republished",
        name="MWP_2026-10.jsonl.gz",
        changed=1,
        added=0,
        removed=0,
    )


def test_rows_of_two_months_name_the_file_by_their_days(raw, server, service):
    late = copy.deepcopy(reading(service, 6495, "2026-10-31"))
    late["attributes"].update(OBJECTID=99_999, DATA_POMIARU=" 2026-11-02")
    readings(service).append(late)
    window = "MWP_2026-10-01_2026-11-02.jsonl.gz"
    notices = []

    report = sync_store(raw, datasets=[READINGS], on_notice=notices.append)

    (result,) = report.items
    assert (result.slot, result.status) == (f"archive:{READINGS}:{window}", "new")
    (unexpected,) = [n for n in notices if n.code == "window_unexpected"]
    assert window in unexpected.message


def test_a_month_the_service_swapped_since_the_check_is_a_stale_plan(
    raw, server, service, tmp_path
):
    plan = check_store(raw, datasets=[READINGS], plan=tmp_path / "plan.json")
    for row in readings(service):
        text = row["attributes"]["DATA_POMIARU"]
        row["attributes"]["DATA_POMIARU"] = text.replace("2026-10-", "2026-12-")

    report = sync_store(raw, plan=plan)

    (result,) = report.items
    assert result.status == "stale_plan"
    assert "MWP_2026-12.jsonl.gz" in result.error
    assert versions(raw, OCTOBER) == []


def test_a_count_that_changes_twice_fails_with_nothing_written(raw, server, service):
    rows = readings(service)
    template = rows[0]

    def growing(request):
        answer = service(request)
        path, asked = service.requests[-1]
        if path == "mwp/MapServer/1/query" and "resultOffset" in asked:
            added = copy.deepcopy(template)
            added["attributes"]["OBJECTID"] = 100_000 + len(rows)
            rows.append(added)
        return answer

    server.routes.clear()
    server.route(host="cbdgmapa.pgi.gov.pl").mock(side_effect=growing)

    report = sync_store(raw, datasets=[READINGS])

    (result,) = report.items
    assert (result.status, result.error_code) == ("failed", "source_unavailable")
    assert versions(raw, OCTOBER) == []
    # The statistics, then two runs of a count, a page and a count.
    assert len(service.requests) == 1 + 2 * 3


def test_a_count_that_changes_once_is_asked_again(raw, server, service):
    rows = readings(service)
    grown = []

    def growing_once(request):
        answer = service(request)
        path, asked = service.requests[-1]
        if path == "mwp/MapServer/1/query" and "resultOffset" in asked and not grown:
            # 853 is read on Mondays only: a Friday reading is a new row.
            added = copy.deepcopy(reading(service, 853, "2026-10-26"))
            added["attributes"].update(OBJECTID=100_000, DATA_POMIARU=" 2026-10-30")
            rows.append(added)
            grown.append(added)
        return answer

    server.routes.clear()
    server.route(host="cbdgmapa.pgi.gov.pl").mock(side_effect=growing_once)

    report = sync_store(raw, datasets=[READINGS])

    (result,) = report.items
    assert result.status == "new"
    # The version holds the second run only: its count, page and the equal count
    # after it (kept once, as seen).
    lines = answers(result.version)
    assert [line.get("seen", False) for line in lines] == [False, False, True]
    assert json.loads(lines[0]["body"]) == {"count": 169}
    assert len(json.loads(lines[1]["body"])["features"]) == 169


@pytest.mark.parametrize(
    ("body", "content_type"),
    [
        (b"<html><body>Request unsuccessful. Incapsula</body></html>", "text/html"),
        (
            b'{"error":{"code":400,"message":"Unable to complete operation."}}',
            "application/json",
        ),
    ],
    ids=["html", "arcgis_error"],
)
def test_an_error_or_html_answer_is_source_unavailable_with_nothing_written(
    raw, server, body, content_type
):
    server.routes.clear()
    server.route(host="cbdgmapa.pgi.gov.pl").respond(
        200, content=body, headers={"Content-Type": content_type}
    )
    notices = []

    report = sync_store(raw, datasets=[READINGS], on_notice=notices.append)

    # The statistics naming the file fail: one failed result without a slot.
    (result,) = report.items
    assert (result.slot, result.status, result.error_code) == (
        None,
        "failed",
        "source_unavailable",
    )
    assert not (raw / "archives" / "versions" / "mwp").exists()
    assert "archive_failed" in {notice.code for notice in notices}


def test_a_table_kept_as_one_file_fails_its_run_on_an_error_answer(raw, server):
    # The recordings hold no chemistry: the service answers its error object.
    report = sync_store(raw, datasets=[CHEMISTRY])

    (result,) = report.items
    assert result.slot == f"archive:{CHEMISTRY}:MWP_chemistry.jsonl.gz"
    assert (result.status, result.error_code) == ("failed", "source_unavailable")
    assert not (raw / "archives" / "versions" / "mwp").exists()


def test_a_month_between_two_captured_ones_is_not_captured(raw, server, service):
    for row in readings(service):
        text = row["attributes"]["DATA_POMIARU"]
        row["attributes"]["DATA_POMIARU"] = text.replace("2026-10-", "2026-08-")
    sync_store(raw, datasets=[READINGS])
    service.tables["mwp/MapServer/1"] = _PigService().tables["mwp/MapServer/1"]
    sync_store(raw, datasets=[READINGS])
    notices = []

    plan = check_store(raw, datasets=[READINGS], on_notice=notices.append)

    (gap,) = [action for action in plan.actions if "MWP_2026-09" in action.detail]
    assert (gap.command, gap.status) == ("store sync", "unverifiable")
    (warning,) = [n for n in notices if n.code == "not_captured"]
    assert "mwp/MapServer/1/MWP_2026-09.jsonl.gz" in warning.message
    # The stored October is checked by its content, the gap fails nothing.
    (item,) = plan.items
    assert (item.archive.server_path, item.status) == (OCTOBER, "unverifiable")
    assert all(result.status != "failed" for result in sync_store(raw, plan=plan).items)


def test_selectors_that_do_not_apply_are_refused_before_any_request(
    raw, tmp_path, server, service
):
    for options in ({"years": 2026}, {"months": 10}, {"stations": ["6495"]}):
        with pytest.raises(ObserwatorValidationError) as caught:
            check_store(raw, datasets=[READINGS], **options)
        assert caught.value.details["reason"] == "publication"
    with pytest.raises(ObserwatorValidationError) as plain:
        sync_store(output_dir=tmp_path / "out", datasets=[READINGS])
    assert plain.value.details["reason"] == "store_only_dataset"
    assert service.requests == []


# --------------------------------------------------------------------------
# Plain files: datasets download (W13)
# --------------------------------------------------------------------------


def test_a_download_writes_the_month_published_with_w_in_attribution_txt(
    tmp_path, server, service
):
    out = tmp_path / "out"

    report = fetch.download_archives(
        READINGS, years=2026, months=[9, 10], output_dir=out
    )

    september, october = report.items
    assert (september.status, october.status) == ("not_published", "downloaded")
    assert september.error == message(
        "fetch.other_file_published",
        asked="mwp/MapServer/1/MWP_2026-09.jsonl.gz",
        published=OCTOBER,
    )
    # One run serves both candidates: a count, a page and a count.
    assert len(service.requests) == 3
    assert answers(out / OCTOBER)[0]["status"] == 200
    lines = (out / "ATTRIBUTION.txt").read_text(encoding="utf-8").splitlines()
    assert filled_w("2026", "2026-11-25") in lines
    assert str(message("legal.pig_terms")) in lines


# --------------------------------------------------------------------------
# The harvest of mwp_auto by OBJECTID watermark (W9)
# --------------------------------------------------------------------------


def test_the_first_harvest_asks_every_row_and_records_its_watermark(
    raw, server, service, clock
):
    notices = []

    report = sync_store(
        raw, datasets=[OPERATIONAL], pace_until=until(60), on_notice=notices.append
    )

    (item,) = report.items
    assert (item.slot, item.status) == (
        f"archive:{OPERATIONAL}:{TODAY}.jsonl.gz",
        "new",
    )
    asked = [(path, asked.get("where")) for path, asked in service.requests]
    assert asked == [
        ("mwp_auto/MapServer/0/query", "1=1"),
        ("mwp_auto/MapServer/2/query", "1=1"),
        ("mwp_auto/MapServer/2/query", "OBJECTID > 0"),
        # The stored hour 02 of the summer-time start day among the rows.
        (
            "mwp_auto/MapServer/2/query",
            "TIME >= TIMESTAMP '2026-03-29 02:00:00' AND "
            "TIME < TIMESTAMP '2026-03-29 03:00:00'",
        ),
    ]
    meta = sidecar(item.version)
    # The 2136 row lies after its answer: no day of the period.
    assert meta["extra"]["capture"] == {
        "answers": 4,
        "period": ["2026-03-29", "2026-11-23"],
        "watermark": LAST_ROW,
        "count": 149,
    }
    assert (meta["tier"], meta["publication"]) == ("operational", "public")
    assert meta["license"]["attribution"] == filled_w("2026", "2026-11-25")
    assert [line["address"] for line in answers(item.version)][2].endswith(
        "where=OBJECTID+%3E+0&outFields=%2A&orderByFields=OBJECTID"
        "&resultRecordCount=1000&returnGeometry=false&f=json"
    )
    assert report.harvest.failed == 0


def test_the_next_harvest_asks_only_the_rows_beyond_the_watermark(
    raw, server, service, clock
):
    sync_store(raw, datasets=[OPERATIONAL], pace_until=until(60))
    clock.moment = NOW + timedelta(days=1)
    late = copy.deepcopy(hours(service)[-1])
    late["attributes"].update(OBJECTID=LAST_ROW + 7)
    hours(service).append(late)
    service.requests.clear()

    report = sync_store(raw, datasets=[OPERATIONAL], pace_until=until(24 * 60 + 60))

    assert [asked.get("where") for _, asked in service.requests] == [
        "1=1",
        "1=1",
        f"OBJECTID > {LAST_ROW}",
    ]
    (item,) = report.items
    assert item.slot == f"archive:{OPERATIONAL}:{TODAY + timedelta(days=1)}.jsonl.gz"
    assert sidecar(item.version)["extra"]["capture"]["watermark"] == LAST_ROW + 7


def test_a_count_below_the_last_harvests_warns_of_rows_removed(
    raw, server, service, clock
):
    sync_store(raw, datasets=[OPERATIONAL], pace_until=until(60))
    clock.moment = NOW + timedelta(days=1)
    del hours(service)[:9]
    notices = []

    sync_store(
        raw,
        datasets=[OPERATIONAL],
        pace_until=until(24 * 60 + 60),
        on_notice=notices.append,
    )

    (removed,) = [n for n in notices if n.code == "rows_removed"]
    assert removed.message == message(
        "pig.rows_removed", count=140, previous=149, day=str(TODAY)
    )


def test_a_harvest_by_watermark_takes_no_days_or_stations(raw, server, service):
    for options in (
        {"start": TODAY - timedelta(days=2)},
        {"end": TODAY - timedelta(days=1)},
        {"stations": ["6495"]},
    ):
        with pytest.raises(ObserwatorValidationError) as caught:
            sync_store(raw, datasets=[OPERATIONAL], pace_until=until(60), **options)
        assert caught.value.details["reason"] == "watermark"
    assert service.requests == []


def test_datasets_list_names_the_six_datasets_with_their_tiers():
    envelope = run_command("datasets list", options={"provider": "PIG"})

    assert [
        (item.key, item.tier, item.time_unit, item.archive_scope)
        for item in envelope.result
    ] == [
        ("pl.pig.groundwater_stations", "verified", "station_list", "country"),
        ("pl.pig.groundwater_readings", "verified", "week", "country"),
        ("pl.pig.groundwater_chemistry", "verified", "snapshot", "country"),
        ("pl.pig.groundwater_watchlist", "verified", "snapshot", "country"),
        ("pl.pig.groundwater_operational", "operational", "hour", "country_day"),
        ("pl.pig.groundwater_subdaily", "operational", "hour", "country"),
    ]
