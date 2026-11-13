"""command_for_version: the data command of a stored version, from its metadata (ADR-008)."""

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
from obserwator.testing import build_fixture_store

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


@pytest.fixture(scope="module")
def root(tmp_path_factory):
    path = tmp_path_factory.mktemp("command_for_version") / "store"
    return build_fixture_store(path, variant="complete_pl_cz").root


@pytest.fixture
def copy(root, tmp_path):
    """A store of one test, which it may break."""
    return Path(shutil.copytree(root, tmp_path / "store"))


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


def refusal(code, version_, root):
    with pytest.raises(ObserwatorError) as error:
        command_for_version(version_, root=root)
    assert error.value.code == code
    return error.value


@pytest.mark.parametrize("case", ARCHIVES, ids=list(ARCHIVES))
def test_archive_version_gives_the_store_sync_of_its_file(case, root, offline):
    dataset, name, options = ARCHIVES[case]
    relative = version(root, "archive", dataset, name)
    server_path = sidecar(root, relative).read_text(encoding="utf-8")
    server_path = json.loads(server_path)["request"]["server_path"]

    call = command_for_version(relative, root=root)

    assert call == CommandCall("store sync", {"root": str(root), **options}, {})
    round_trips(call)
    files = planned(call)
    if dataset == CZ_METEO:
        # Every element of the station: the call has no option for one element.
        assert server_path in files and len(files) == 4
    else:
        assert files == {server_path}


@pytest.mark.parametrize("case", STATION_SOURCES, ids=list(STATION_SOURCES))
def test_station_source_version_gives_the_store_sync_of_its_dataset(
    case, root, offline
):
    dataset = STATION_SOURCES[case]
    relative = version(root, "archive", dataset)
    server_path = json.loads(sidecar(root, relative).read_text(encoding="utf-8"))[
        "request"
    ]["server_path"]

    call = command_for_version(relative, root=root)

    assert call == CommandCall(
        "store sync", {"root": str(root), "datasets": [dataset]}, {}
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
    case, root, offline
):
    dataset, provider = CATALOGS[case]
    relative = version(root, "catalog", dataset)

    call = command_for_version(relative, root=root)

    assert call == CommandCall(
        "store catalog", {"root": str(root), "provider": provider}, {}
    )
    round_trips(call)
    stored = {
        entry.version.relative_to(root).as_posix()
        for entry in iter_store(root, kind="archive", provider=provider)
        if entry.meta is not None
        and entry.meta.dataset_key.endswith(("_stations", "_now"))
    }
    # The sidecar names the stored file of every station source, API answers too.
    named = {
        source["file"]
        for source in json.loads(sidecar(root, relative).read_text(encoding="utf-8"))[
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
def test_series_version_and_its_station_file_give_the_series_build(dataset, root):
    relative = version(root, "series", dataset)
    station = next((root / relative.parent / "stations").iterdir())

    call = command_for_version(relative, root=root)

    assert call == CommandCall(
        "series build", {"root": str(root), "dataset": dataset}, {}
    )
    assert command_for_version(station.relative_to(root), root=root) == call
    round_trips(call)
    plan = check_command(call.command, options=call.options).result
    assert {action.command for action in plan.actions} == {"series build"}
    assert list(plan.series_state) == [relative.parts[2]]


def test_pmaxtp_version_gives_the_sync_of_its_point_and_cell(tmp_path):
    store = init_store(tmp_path / "store")
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
    root, monkeypatch
):
    relative = version(root, "archive", HYDRO)
    call = command_for_version(relative, root=root)

    monkeypatch.setenv("OBSERWATOR_ROOT", str(root))
    assert command_for_version(relative.parent) == call
    assert command_for_version(sidecar(root, relative)) == call
    assert command_for_version(root / relative) == call


def test_missing_data_file_still_gives_the_command_from_the_sidecar(copy):
    relative = version(copy, "archive", HYDRO)
    expected = command_for_version(relative, root=copy)
    (copy / relative).unlink()

    assert command_for_version(relative, root=copy) == expected


def test_catalog_built_with_user_coordinates_is_refused(copy):
    relative = version(copy, "catalog", "pl.imgw.stations")
    rewrite(
        copy,
        relative,
        lambda meta: meta["request"].update(user_locations="moje_punkty.csv"),
    )

    error = refusal("unsupported", relative, copy)

    assert error.details == {
        "reason": "command_not_rebuildable",
        "version": relative.as_posix(),
        "field": "request.user_locations",
    }
    assert "--user-locations" in error.detail


def test_pmaxtp_sidecar_without_its_point_is_refused(tmp_path):
    store = init_store(tmp_path / "store")
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


def test_archive_that_store_sync_does_not_select_is_refused(copy):
    relative = version(copy, "archive", HYDRO)
    slot = copy / relative.parents[1]
    other = slot.with_name("inny_2024") / relative.parent.name
    shutil.copytree(copy / relative.parent, other)
    for path in other.iterdir():
        path.rename(path.with_name(path.name.replace("codz_2024", "inny_2024")))
    moved = (other / "inny_2024.zip").relative_to(copy)
    server_path = "dane_hydrologiczne/dobowe/2024/inny_2024.zip"
    rewrite(copy, moved, lambda meta: meta["request"].update(server_path=server_path))

    error = refusal("unsupported", moved, copy)

    assert error.details == {
        "reason": "command_not_rebuildable",
        "version": moved.as_posix(),
        "server_path": server_path,
    }


def test_missing_version_or_unpublished_sidecar_is_not_found(copy):
    relative = version(copy, "archive", HYDRO)
    gone = relative.parent.with_name("2026-01-01_00000000") / relative.name

    assert refusal("not_found", gone, copy).details == {"version": gone.as_posix()}
    sidecar(copy, relative).unlink()
    assert refusal("not_found", relative, copy).details == {
        "version": relative.as_posix()
    }


def test_malformed_or_contradicting_sidecar_is_a_data_error(copy):
    relative = version(copy, "series", HYDRO)
    rewrite(copy, relative, lambda meta: meta.update(dataset=PRECIP))
    assert refusal("data_error", relative, copy).details["field"] == "dataset"

    archive = version(copy, "archive", HYDRO)
    rewrite(copy, archive, lambda meta: meta["request"].update(year=2023))
    assert refusal("data_error", archive, copy).details["field"] == "request.year"

    sidecar(copy, archive).write_text("{", encoding="utf-8")
    assert refusal("data_error", archive, copy).details == {
        "version": archive.as_posix()
    }


def test_path_that_is_no_version_is_a_validation_error(root, tmp_path):
    observation = next(
        entry.version for entry in iter_store(root, kind="observation")
    ).relative_to(root)
    for given in (observation, Path("archives/versions"), tmp_path / "elsewhere"):
        error = refusal("validation_error", given, root)
        assert error.details["option"] == "version"
