"""command_for_version: the data command of a stored version, from its metadata (ADR-008, ADR-017)."""

import json
import shutil
from pathlib import Path

import httpx
import pytest
import respx

from obserwator import (
    CommandCall,
    check_command,
    command_for_version,
    format_command,
    init_store,
    iter_store,
    parse_command,
    run_command,
    sync_pmaxtp,
)
from obserwator.exceptions import ObserwatorError
from tests.contract.support import build_served_analyses

RECORDINGS = Path(__file__).parents[1] / "fixtures" / "store" / "recordings.json"
PMAXTP = next(
    item
    for item in json.loads(RECORDINGS.read_text(encoding="utf-8"))["interactions"]
    if item["case"] == "pmaxtp_pot_first"
)
HYDRO = "pl.imgw.hydro_daily"
PRECIP = "pl.imgw.meteo_precip_daily"
CZ_HYDRO = "cz.chmi.hydro_daily"
CZ_METEO = "cz.chmi.meteo_daily"
CZ_FULL, CZ_ELEMENTS = "0-203-1-900001", "0-203-0-90001"

# (dataset, main file of the version) → the options of the rebuilt store sync.
ARCHIVES = {
    "imgw_yearly": (
        HYDRO,
        "codz_2024.zip",
        {"datasets": [HYDRO], "years": ["2024"]},
    ),
    "imgw_monthly": (
        PRECIP,
        "2001_01_o.zip",
        {"datasets": [PRECIP], "years": ["2001"], "months": ["1"]},
    ),
    "chmi_station_year": (
        CZ_HYDRO,
        f"H_{CZ_FULL}_DQ_2023.json",
        {"datasets": [CZ_HYDRO], "years": ["2023"], "stations": [CZ_FULL]},
    ),
    "chmi_station_element": (
        CZ_METEO,
        f"dly-{CZ_ELEMENTS}-T.csv",
        {"datasets": [CZ_METEO], "stations": [CZ_ELEMENTS]},
    ),
}
# Station lists and current-data sources: their own store sync (ADR-015).
STATION_SOURCES = {
    "imgw_station_list": "pl.imgw.hydro_stations",
    "chmi_station_list": "cz.chmi.meteo_stations",
    "imgw_api_answer": "pl.imgw.hydro_now",
    "chmi_meteo_now": "cz.chmi.meteo_now",
}
# Catalogs → the provider of their store catalog.
CATALOGS = {
    "imgw_catalog": ("pl.imgw.stations", "IMGW-PIB"),
    "chmi_catalog": ("cz.chmi.stations", "CHMI"),
}


@pytest.fixture(autouse=True)
def no_default_roots(monkeypatch, tmp_path):
    """No root of the machine: the default roots lie in an empty data directory."""
    for name in ("OBSERWATOR_ROOT", "OBSERWATOR_RAW_ROOT"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("OBSERWATOR_DATA_DIR", str(tmp_path / "no-data-dir"))


@pytest.fixture
def raw(fixture_raw_root):
    """The raw root of the ``complete_pl_cz`` fixture: archives, station sources."""
    return fixture_raw_root


@pytest.fixture
def data(fixture_root):
    """The data root of the ``complete_pl_cz`` fixture: series, catalogs."""
    return fixture_root


@pytest.fixture
def raw_copy(raw, tmp_path):
    """A raw root of one test, which it may break."""
    return Path(shutil.copytree(raw, tmp_path / "raw"))


@pytest.fixture
def data_copy(data, tmp_path):
    """A data root of one test, which it may break."""
    return Path(shutil.copytree(data, tmp_path / "data"))


@pytest.fixture
def offline():
    """Every request fails, so a check plans its items without any answer."""
    with respx.mock(assert_all_called=False) as router:
        router.route().mock(side_effect=httpx.ConnectError("offline"))
        yield router


def version(root, kind, dataset, name=None):
    """Store-relative main file of the newest stored version of ``dataset``."""
    found = sorted(
        entry.version
        for entry in iter_store(root, kind=kind)
        if entry.meta is not None
        and entry.meta.dataset_key == dataset
        and (name is None or entry.version.name == name)
    )
    return found[-1].relative_to(root)


def sidecar(root, relative):
    return root / relative.with_name(f"{relative.name}.meta.json")


def rewrite(root, relative, change):
    """Change the sidecar of a version in place."""
    path = sidecar(root, relative)
    document = json.loads(path.read_text(encoding="utf-8"))
    change(document)
    path.write_text(json.dumps(document), encoding="utf-8")


def round_trips(call):
    line = format_command(call.command, options=call.options)
    assert parse_command(line) == call
    return line


def planned(call):
    """Server paths of the items the offline check of ``call`` plans."""
    plan = check_command(call.command, options=call.options).result
    assert plan.root == Path(call.options["root"])
    return {item.archive.server_path for item in plan.items}


def refusal(code, version_, root, **roots):
    with pytest.raises(ObserwatorError) as error:
        command_for_version(version_, root=root, **roots)
    assert error.value.code == code
    return error.value


@pytest.mark.parametrize("case", ARCHIVES, ids=list(ARCHIVES))
def test_archive_version_gives_the_store_sync_of_its_file(case, raw, offline):
    dataset, name, options = ARCHIVES[case]
    relative = version(raw, "archive", dataset, name)
    server_path = sidecar(raw, relative).read_text(encoding="utf-8")
    server_path = json.loads(server_path)["request"]["server_path"]

    call = command_for_version(relative, root=raw)

    assert call == CommandCall("store sync", {"root": str(raw), **options}, {})
    round_trips(call)
    files = planned(call)
    if dataset == CZ_METEO:
        # Every element of the station: the call has no option for one element.
        assert server_path in files and len(files) == 4
    else:
        assert files == {server_path}


@pytest.mark.parametrize("case", STATION_SOURCES, ids=list(STATION_SOURCES))
def test_station_source_version_gives_the_store_sync_of_its_dataset(case, raw, offline):
    dataset = STATION_SOURCES[case]
    relative = version(raw, "archive", dataset)
    server_path = json.loads(sidecar(raw, relative).read_text(encoding="utf-8"))[
        "request"
    ]["server_path"]

    call = command_for_version(relative, root=raw)

    assert call == CommandCall(
        "store sync", {"root": str(raw), "datasets": [dataset]}, {}
    )
    round_trips(call)
    plan = check_command(call.command, options=call.options).result
    if dataset == "cz.chmi.meteo_now":
        # Only the listing names the newest file: offline, the check fails.
        assert plan.items == ()
        assert [action.status for action in plan.actions] == ["check_failed"]
        assert dataset in plan.actions[0].detail
    else:
        assert {item.archive.server_path for item in plan.items} == {server_path}
    if dataset == "pl.imgw.hydro_now":
        # An API answer has no signal: unverifiable without any request.
        assert [item.status for item in plan.items] == ["unverifiable"]
        assert not offline.calls


@pytest.mark.parametrize("case", CATALOGS, ids=list(CATALOGS))
def test_catalog_version_gives_the_offline_store_catalog_of_its_provider(
    case, raw, data, offline
):
    dataset, provider = CATALOGS[case]
    relative = version(data, "catalog", dataset)

    call = command_for_version(relative, root=data, raw_root=raw)

    assert call == CommandCall(
        "store catalog",
        {"root": str(data), "raw_root": str(raw), "provider": provider},
        {},
    )
    round_trips(call)
    stored = {
        entry.version.relative_to(raw).as_posix()
        for entry in iter_store(raw, kind="archive", provider=provider)
        if entry.meta is not None
        and entry.meta.dataset_key.endswith(("_stations", "_now"))
    }
    # The sidecar names the stored file of every station source, API answers too.
    named = {
        source["file"]
        for source in json.loads(sidecar(data, relative).read_text(encoding="utf-8"))[
            "extra"
        ]["catalog"]
        if source["file"].startswith("archives/")
    }
    assert named == stored
    plan = check_command(call.command, options=call.options).result
    assert not offline.calls
    assert plan.items == ()
    sources = plan.actions[: len(stored)]
    assert [action.status for action in sources] == ["current"] * len(stored)
    assert all(any(path in action.detail for action in sources) for path in stored)


@pytest.mark.parametrize("dataset", [HYDRO, CZ_HYDRO])
def test_series_version_and_its_station_file_give_the_series_build(dataset, raw, data):
    relative = version(data, "series", dataset)
    station = next((data / relative.parent / "stations").iterdir())

    call = command_for_version(relative, root=data, raw_root=raw)

    assert call == CommandCall(
        "series build",
        {"root": str(data), "raw_root": str(raw), "dataset": dataset},
        {},
    )
    assert command_for_version(station.relative_to(data), root=data, raw_root=raw) == (
        call
    )
    round_trips(call)
    plan = check_command(call.command, options=call.options).result
    assert {action.command for action in plan.actions} == {"series build"}
    assert list(plan.series_state) == [relative.parts[2]]


@pytest.mark.parametrize(
    ("kind", "dataset", "command"),
    [
        ("series", HYDRO, "series build"),
        ("catalog", "pl.imgw.stations", "store catalog"),
    ],
)
def test_a_build_without_raw_root_reads_the_default_raw_root(
    kind, dataset, command, raw, data, monkeypatch, tmp_path
):
    relative = version(data, kind, dataset)
    default = tmp_path / "no-data-dir" / "obserwator-raw"
    assert command_for_version(relative, root=data).options["raw_root"] == str(default)
    monkeypatch.setenv("OBSERWATOR_RAW_ROOT", str(raw))

    call = command_for_version(relative, root=data)

    assert call.command == command
    assert (call.options["root"], call.options["raw_root"]) == (str(data), str(raw))
    assert command_for_version(relative, root=data, raw_root=raw) == call


def test_analyses_version_and_its_files_give_the_analyses_build(data_copy):
    build_served_analyses(data_copy)
    (directory,) = (data_copy / "analyses" / "versions" / "pl.imgw").iterdir()
    relative = (directory / "analyses.json").relative_to(data_copy)

    call = command_for_version(relative, root=data_copy)

    assert call == CommandCall("analyses build", {"root": str(data_copy)}, {})
    round_trips(call)
    station = next((directory / "stations").iterdir())
    for given in (relative.parent, sidecar(data_copy, relative), station):
        if given.is_absolute():
            given = given.relative_to(data_copy)
        assert command_for_version(given, root=data_copy) == call
    # An absolute path finds its data root by the marker; no raw root is named.
    assert command_for_version(data_copy / relative) == call
    assert command_for_version(relative, root=data_copy, raw_root="/raw") == call


def test_pmaxtp_version_gives_the_sync_of_its_point_and_cell(tmp_path):
    store = init_store(tmp_path / "raw")
    with respx.mock as router:
        route = router.get(PMAXTP["url"]).mock(
            return_value=httpx.Response(PMAXTP["status"], json=PMAXTP["json"])
        )
        stored = sync_pmaxtp(store, method="POT", latitude=52.23, longitude=21.01)
        relative = stored.version.relative_to(store.root)

        call = command_for_version(relative.with_name("response.json"), root=store.root)
        round_trips(call)
        again = run_command(call.command, options=call.options).result

    assert call == CommandCall(
        "pmaxtp sync",
        {
            "root": str(store.root),
            "latitude": "52.23",
            "longitude": "21.01",
            "method": "POT",
            "ind_x": "751",
            "ind_y": "317",
        },
        {},
    )
    assert route.call_count == 2
    assert (again.status, again.version) == ("unchanged", stored.version)


def test_version_is_its_directory_sidecar_or_absolute_path_and_root_defaults(
    raw, data, monkeypatch
):
    relative = version(raw, "archive", HYDRO)
    call = command_for_version(relative, root=raw)

    # A relative archive lies in the default raw root, not in the data root.
    monkeypatch.setenv("OBSERWATOR_ROOT", str(data))
    monkeypatch.setenv("OBSERWATOR_RAW_ROOT", str(raw))
    assert command_for_version(relative.parent) == call
    assert command_for_version(sidecar(raw, relative)) == call
    # An absolute one finds its root by the marker, whatever the defaults.
    monkeypatch.delenv("OBSERWATOR_RAW_ROOT")
    assert command_for_version(raw / relative) == call

    series = version(data, "series", HYDRO)
    monkeypatch.setenv("OBSERWATOR_RAW_ROOT", str(raw))
    built = command_for_version(series, root=data, raw_root=raw)
    assert command_for_version(series) == built
    assert command_for_version(data / series) == built


def test_version_in_a_root_of_the_other_kind_is_refused(raw, data):
    archive = version(raw, "archive", HYDRO)
    series = version(data, "series", HYDRO)

    for given, root, expected in (
        (archive, data, "raw"),
        (series, raw, "data"),
        (Path("stations/versions"), raw, "data"),
        (Path("pmaxtp/versions"), data, "raw"),
    ):
        error = refusal("store_unavailable", given, root)
        assert error.details["reason"] == "wrong_root"
        assert error.details["kind"] == expected


def test_missing_data_file_still_gives_the_command_from_the_sidecar(raw_copy):
    relative = version(raw_copy, "archive", HYDRO)
    expected = command_for_version(relative, root=raw_copy)
    (raw_copy / relative).unlink()

    assert command_for_version(relative, root=raw_copy) == expected


def test_catalog_built_with_user_coordinates_is_refused(data_copy):
    relative = version(data_copy, "catalog", "pl.imgw.stations")
    rewrite(
        data_copy,
        relative,
        lambda meta: meta["request"].update(user_locations="moje_punkty.csv"),
    )

    error = refusal("unsupported", relative, data_copy)

    assert error.details == {
        "reason": "command_not_rebuildable",
        "version": relative.as_posix(),
        "field": "request.user_locations",
    }
    assert "--user-locations" in error.detail


def test_pmaxtp_sidecar_without_its_point_is_refused(tmp_path):
    store = init_store(tmp_path / "raw")
    with respx.mock as router:
        router.get(PMAXTP["url"]).mock(
            return_value=httpx.Response(PMAXTP["status"], json=PMAXTP["json"])
        )
        stored = sync_pmaxtp(store, method="POT", latitude=52.23, longitude=21.01)
    relative = stored.version.relative_to(store.root)
    rewrite(store.root, relative, lambda meta: meta["request"].pop("longitude"))

    error = refusal("unsupported", relative, store.root)

    assert error.details["reason"] == "command_not_rebuildable"
    assert error.details["field"] == "request.longitude"


def test_archive_that_store_sync_does_not_select_is_refused(raw_copy):
    relative = version(raw_copy, "archive", HYDRO)
    slot = raw_copy / relative.parents[1]
    other = slot.with_name("inny_2024") / relative.parent.name
    shutil.copytree(raw_copy / relative.parent, other)
    for path in other.iterdir():
        path.rename(path.with_name(path.name.replace("codz_2024", "inny_2024")))
    moved = (other / "inny_2024.zip").relative_to(raw_copy)
    server_path = "dane_hydrologiczne/dobowe/2024/inny_2024.zip"
    rewrite(
        raw_copy, moved, lambda meta: meta["request"].update(server_path=server_path)
    )

    error = refusal("unsupported", moved, raw_copy)

    assert error.details == {
        "reason": "command_not_rebuildable",
        "version": moved.as_posix(),
        "server_path": server_path,
    }


def test_missing_version_or_unpublished_sidecar_is_not_found(raw_copy):
    relative = version(raw_copy, "archive", HYDRO)
    gone = relative.parent.with_name("2026-01-01_00000000") / relative.name

    assert refusal("not_found", gone, raw_copy).details == {"version": gone.as_posix()}
    sidecar(raw_copy, relative).unlink()
    assert refusal("not_found", relative, raw_copy).details == {
        "version": relative.as_posix()
    }


def test_malformed_or_contradicting_sidecar_is_a_data_error(raw_copy, data_copy):
    relative = version(data_copy, "series", HYDRO)
    rewrite(data_copy, relative, lambda meta: meta.update(dataset=PRECIP))
    assert refusal("data_error", relative, data_copy).details["field"] == "dataset"

    archive = version(raw_copy, "archive", HYDRO)
    rewrite(raw_copy, archive, lambda meta: meta["request"].update(year=2023))
    assert refusal("data_error", archive, raw_copy).details["field"] == "request.year"

    sidecar(raw_copy, archive).write_text("{", encoding="utf-8")
    assert refusal("data_error", archive, raw_copy).details == {
        "version": archive.as_posix()
    }


def test_path_that_is_no_version_is_a_validation_error(raw, tmp_path):
    observation = next(
        entry.version for entry in iter_store(raw, kind="observation")
    ).relative_to(raw)
    for given in (observation, Path("archives/versions"), tmp_path / "elsewhere"):
        error = refusal("validation_error", given, raw)
        assert error.details["option"] == "version"


def test_absolute_version_in_no_root_is_a_validation_error(raw, tmp_path):
    relative = version(raw, "archive", HYDRO)
    unmarked = Path(shutil.copytree(raw, tmp_path / "unmarked"))
    (unmarked / "obserwator-store.json").unlink()

    error = refusal("validation_error", unmarked / relative, None)

    assert error.details == {
        "option": "version",
        "value": str(unmarked / relative),
    }
