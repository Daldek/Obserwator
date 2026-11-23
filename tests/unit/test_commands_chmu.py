"""Command catalog for ČHMÚ (spec 2026-10-18 §9.2–§9.3): options, rules, views, parity.

ČHMÚ answers come from the recordings of ``chmu_recordings.json`` and
``chmu_catalog_recordings.json`` only; respx refuses every other request.
"""

import importlib
import json
from datetime import UTC, datetime

import pytest
import respx
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from obserwator import (
    ERROR_CODES,
    STATION_CODE_PATTERN,
    ObserwatorValidationError,
    check_command,
    command_schema,
    data_commands,
    datasets,
    providers,
    run_command,
    validate_command,
)
from obserwator._jsonable import jsonable
from obserwator.api.main import app as rest_app
from obserwator.cli.main import app as cli_app
from obserwator.config import settings
from obserwator.datasets import CAPTURE_SCOPE
from obserwator.store import build_catalog, init_store, sync_store
from tests.contract.support import (
    canonical,
    cli_words,
    input_schema,
    rest_request,
    violations,
)
from tests.unit.test_store_catalog_chmu import SOURCES
from tests.unit.test_store_catalog_chmu import serve as serve_catalog
from tests.unit.test_store_sync_chmu import BASE, FIRST
from tests.unit.test_store_sync_chmu import serve as serve_files

HYDRO, METEO = "cz.chmu.hydro_daily", "cz.chmu.meteo_daily"
S1, S2 = "0-203-1-900001", "0-203-1-900002"
FULL = "0-203-0-90001"
ROOT = "/data/obserwator"
HYDRO_NOW = BASE + "hydrology/now/metadata/meta1.json"
GROUNDWATER_NOW = BASE + "hydrology/groundwater/now/metadata/meta1.json"
# The station sources of the ČHMÚ catalog, synced before a catalog (ADR-015).
STATION_SOURCES = [
    "cz.chmu.hydro_stations",
    "cz.chmu.meteo_stations",
    "cz.chmu.hydro_now",
    "cz.chmu.meteo_now",
]
# ČHMÚ's groundwater datasets (ADR-032), after the station sources.
GROUNDWATER = [
    "cz.chmu.groundwater_daily",
    "cz.chmu.groundwater_weekly",
    "cz.chmu.groundwater_recent",
    "cz.chmu.groundwater_characteristic",
    "cz.chmu.groundwater_stations",
    "cz.chmu.groundwater_now",
]
METEO_LISTING = BASE + "meteorology/climate/now/metadata/"
FROZEN_AT = datetime(2026, 10, 20, 9, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def no_obserwator_root(monkeypatch):
    """The developer's OBSERWATOR_ROOT and OBSERWATOR_RAW_ROOT must not reach the CLI."""
    monkeypatch.delenv("OBSERWATOR_ROOT", raising=False)
    monkeypatch.delenv("OBSERWATOR_RAW_ROOT", raising=False)


@pytest.fixture
def server(monkeypatch):
    """REST server without roots, writes disabled, default page size."""
    for name, value in (
        ("root", None),
        ("raw_root", None),
        ("store_writes_enabled", False),
        ("store_write_token", None),
        ("user_locations_dir", None),
        ("api_max_limit", 1000),
    ):
        monkeypatch.setattr(settings, name, value)
    return settings


@pytest.fixture
def frozen(monkeypatch):
    class Frozen(datetime):
        @classmethod
        def now(cls, tz=None):
            return FROZEN_AT.astimezone(tz)

    for name in (
        "obserwator.commands",
        "obserwator.store.sync",
        "obserwator.store.catalog",
    ):
        monkeypatch.setattr(importlib.import_module(name), "datetime", Frozen)


@pytest.fixture
def chmu():
    """Recorded ČHMÚ: current metadata, station lists and the daily-file listings."""
    with respx.mock(assert_all_called=False) as router:
        serve_catalog(router, *SOURCES, "groundwater_now_get")
        serve_files(
            router,
            "hydro_listing",
            "precipitation_listing",
            "temperature_listing",
            "snow_listing",
        )
        yield router


# --------------------------------------------------------------------------
# Catalog and registry
# --------------------------------------------------------------------------


def test_catalog_has_36_commands_and_datasets_providers_lists_both_providers():
    assert len(data_commands()) == 36

    listed = run_command("datasets providers", options={})
    planned = check_command("datasets providers", options={})

    assert listed.status == "ok"
    assert [provider.id for provider in listed.result] == ["IMGW", "CHMU"]
    assert (listed.result, listed.page.total) == (providers(), 2)
    assert [action.status for action in planned.result.actions] == ["current"]
    chmu = run_command("datasets list", options={"provider": "CHMU"}).result
    assert [descriptor.key for descriptor in chmu] == [
        HYDRO,
        METEO,
        *STATION_SOURCES,
        *GROUNDWATER,
    ]
    assert run_command("datasets list", options={}).page.total == len(datasets())


def _entry(name):
    (entry,) = command_schema(name)["commands"]
    return entry


def _options(name):
    return {option["name"]: option for option in _entry(name)["options"]}


def _values(option):
    return [value["value"] for value in option["enum"]]


def test_command_schema_publishes_provider_stations_and_their_rules():
    for name in ("datasets list", "stations find", "store scan"):
        provider = _options(name)["provider"]
        assert _values(provider) == ["IMGW", "CHMU"]
        assert "default" not in provider
    catalog = _options("store catalog")["provider"]
    assert (_values(catalog), catalog["default"]) == (["IMGW", "CHMU"], "IMGW")
    for name in ("datasets files", "datasets download", "store check", "store sync"):
        entry = _entry(name)
        stations = _options(name)["stations"]
        assert stations["items"]["pattern"] == STATION_CODE_PATTERN
        assert stations["flags"] == ["--stations", "-s"]
        # Years depend on the dataset, so the schema leaves them to the rules.
        assert _options(name)["years"]["required"] is False
        rules = entry["rules"]
        assert any("stations" in rule and "cz.chmu" in rule for rule in rules)
        assert any("years" in rule and METEO in rule for rule in rules)
    # No server publishes a capture's files: store sync seals them (ADR-030 D3).
    archive = _values(_options("datasets files")["dataset"])
    assert archive == [
        item.key
        for item in datasets()
        if item.server_dir is not None
        and item.time_unit != "station_list"
        and item.archive_scope != CAPTURE_SCOPE
    ]
    assert {HYDRO, METEO} <= set(archive)
    entry = _entry("datasets providers")
    assert (
        entry["function"],
        entry["result"]["cardinality"],
        entry["result_type"],
    ) == (
        "providers",
        "bounded",
        "ProviderDescriptor",
    )
    assert entry["rest"]["path"] == "/api/v1/datasets/providers"


def test_chmu_view_of_the_catalog_drops_imgw_only_commands_and_narrows_choices():
    view = data_commands(provider="CHMU")

    groups = {command.name.split()[0] for command in view}
    assert not groups & {"current", "pmaxtp"}
    assert len(view) == 25  # 36 without six current and five pmaxtp commands
    for command in view:
        for option in command.options:
            if option.name in ("dataset", "datasets"):
                assert option.choices
                assert all(key.startswith("cz.chmu.") for key in option.choices)
            elif option.name == "provider":
                assert (option.choices, option.required, option.default) == (
                    ("CHMU",),
                    True,
                    None,
                )
    assert data_commands(provider="cz.chmu") == view
    imgw = data_commands(provider="IMGW")
    assert [command.name for command in imgw] == [c.name for c in data_commands()]
    assert all(
        key.startswith("pl.imgw.")
        for command in imgw
        for option in command.options
        if option.name in ("dataset", "datasets")
        for key in option.choices
    )
    # The whole catalog still validates: provider stays optional there.
    assert validate_command("stations find", options={}) == {}
    with pytest.raises(ObserwatorValidationError) as error:
        data_commands(provider="SHMU")
    assert error.value.details["option"] == "provider"


# --------------------------------------------------------------------------
# validate_command
# --------------------------------------------------------------------------


REJECTED = [
    ("datasets files", {"dataset": HYDRO, "years": 2024}, "stations"),
    (
        "datasets files",
        {"dataset": "pl.imgw.hydro_daily", "years": 2024, "stations": [S1]},
        "stations",
    ),
    ("datasets files", {"dataset": HYDRO, "stations": [S1]}, "years"),
    ("datasets files", {"dataset": METEO, "stations": [FULL], "years": 2024}, "years"),
    (
        "datasets files",
        {"dataset": HYDRO, "stations": ["149190310"], "years": 2024},
        "stations",
    ),
    ("datasets files", {"dataset": HYDRO, "stations": [S1], "years": 1886}, "years"),
    (
        "datasets download",
        {"dataset": HYDRO, "stations": [S1], "years": 2024, "months": 1},
        "months",
    ),
    (
        "datasets download",
        {"dataset": METEO, "stations": [FULL], "params": "H"},
        "params",
    ),
    ("datasets list", {"provider": "SHMU"}, "provider"),
    ("stations find", {"provider": "chmu"}, "provider"),
    ("store scan", {"root": ROOT, "provider": "CZ"}, "provider"),
    ("store catalog", {"root": ROOT, "provider": "SHMU"}, "provider"),
    (
        "store check",
        {
            "root": ROOT,
            "datasets": [HYDRO, "pl.imgw.hydro_daily"],
            "stations": [S1],
            "years": 2024,
        },
        "stations",
    ),
    ("store check", {"root": ROOT, "datasets": [HYDRO]}, "stations"),
    (
        "store check",
        {
            "root": ROOT,
            "datasets": ["pl.imgw.hydro_daily"],
            "years": 2024,
            "stations": [S1],
        },
        "stations",
    ),
    (
        "store check",
        {"root": ROOT, "datasets": [METEO], "stations": [FULL], "years": 2024},
        "years",
    ),
    (
        "store check",
        {"root": ROOT, "datasets": [HYDRO], "stations": [S1], "months": 1},
        "months",
    ),
    (
        "store check",
        {"root": ROOT, "datasets": [METEO], "stations": ["0-203-0-ab"]},
        "stations",
    ),
    (
        "store sync",
        {"root": ROOT, "plan": "/tmp/plan.json", "stations": [S1]},
        "stations",
    ),
    ("store sync", {"root": ROOT, "datasets": [HYDRO]}, "stations"),
]


@pytest.mark.parametrize(("command", "options", "option"), REJECTED)
def test_validate_command_applies_the_rules_of_the_dataset_provider(
    command, options, option
):
    with pytest.raises(ObserwatorValidationError) as error:
        validate_command(command, options=options)

    assert error.value.code == "validation_error"
    assert error.value.details["option"] == option


VALID = [
    ("datasets list", {"provider": "CHMU", "kind": "hydro"}),
    (
        "datasets files",
        {"dataset": HYDRO, "stations": [S2, S1, S2], "years": "2004-2006"},
    ),
    ("datasets files", {"dataset": "chmu_meteo_daily", "stations": FULL}),
    (
        "datasets download",
        {"dataset": METEO, "stations": [FULL], "output_dir": "/tmp/pobrane dane"},
    ),
    ("datasets providers", {"limit": 1}),
    ("stations find", {"provider": "cz.chmu", "kind": "hydro", "query": "spindleruv"}),
    ("stations find", {"provider": "CHMU", "source": "store", "root": ROOT}),
    ("store scan", {"root": ROOT, "provider": "CHMU", "kind": "archive"}),
    ("store check", {"root": ROOT, "datasets": HYDRO, "stations": [S1, S2]}),
    (
        "store check",
        {
            "root": ROOT,
            "datasets": [HYDRO],
            "stations": S1,
            "years": [2023, 2024],
            "plan": "/tmp/plan.json",
        },
    ),
    ("store check", {"root": ROOT, "datasets": METEO, "stations": FULL}),
    ("store check", {"root": ROOT, "datasets": ["cz.chmu.hydro_now"]}),
    (
        "store sync",
        {
            "root": ROOT,
            "datasets": [HYDRO],
            "stations": [S1],
            "years": "2023-2024",
            "force": True,
        },
    ),
    ("store sync", {"root": ROOT, "datasets": STATION_SOURCES}),
    ("store catalog", {"root": ROOT, "provider": "CHMU"}),
]


@pytest.mark.parametrize(("command", "options"), VALID)
def test_chmu_examples_normalize_to_options_of_the_command_schema(command, options):
    normalized = validate_command(command, options=options)

    assert violations(jsonable(normalized), input_schema(command)) == []


def test_validate_command_normalizes_chmu_selectors():
    files = validate_command(
        "datasets files",
        options={
            "dataset": "chmu_hydro_daily",
            "stations": f"{S2},{S1},{S2}",
            "years": "2024",
        },
    )
    assert files == {"dataset": HYDRO, "years": (2024,), "stations": (S2, S1)}
    check = validate_command(
        "store check", options={"root": ROOT, "datasets": HYDRO, "stations": S1}
    )
    assert (check["datasets"], check["stations"], "years" in check) == (
        (HYDRO,),
        (S1,),
        False,
    )
    assert validate_command("datasets list", options={"provider": "cz.chmu"}) == {
        "provider": "CHMU"
    }


# --------------------------------------------------------------------------
# Dispatch: stations reach the functions, statuses, checks
# --------------------------------------------------------------------------


def test_store_check_and_sync_pass_stations_through_the_catalog(tmp_path):
    root = init_store(tmp_path / "store").root
    options = {"root": root, "datasets": [HYDRO], "stations": [S1]}

    with respx.mock(assert_all_called=False) as router:
        serve_files(router, "hydro_listing", *FIRST)
        planned = check_command("store sync", options=options)
        synced = run_command("store sync", options=options)

    assert planned.status == synced.status == "ok"
    assert [(item.station_code, item.status) for item in planned.result.items] == [
        (S1, "missing"),
        (S1, "missing"),
    ]
    assert [item.status for item in synced.result.items] == ["new", "new"]


def test_unpublished_files_count_as_successful_items_of_a_download(tmp_path):
    options = {
        "dataset": HYDRO,
        "stations": [S2],
        "years": "2004-2005",
        "output_dir": tmp_path / "pobrane",
    }
    with respx.mock(assert_all_called=False) as router:
        serve_files(router, "h900002_2005_get")
        failing = f"hydrology/historical/data/daily/H_{S2}_DQ_2004.json"
        router.get(BASE + failing).respond(500)
        planned = check_command("datasets download", options=options)
        result = run_command("datasets download", options=options)
        printed = CliRunner().invoke(cli_app, cli_words("datasets download", options))

    # two files and the ATTRIBUTION.txt of the directory (ADR-012 D5)
    assert [action.status for action in planned.result.actions] == ["missing"] * 3
    assert planned.result.actions[-1].path.name == "ATTRIBUTION.txt"
    assert [item.status for item in result.result.items] == ["failed", "not_published"]
    # A failure beside an unpublished candidate is partial, not failed (§13.6).
    assert result.status == "partial"
    assert printed.exit_code == 10, printed.output
    assert canonical(json.loads(printed.stdout)) == canonical(result.to_json())


def test_check_of_a_live_chmu_search_names_its_sources_without_requests():
    with respx.mock(assert_all_called=False) as router:
        plan = check_command("stations find", options={"provider": "CHMU"}).result

    assert not router.calls
    assert [action.status for action in plan.actions] == ["unverifiable"] * 4
    details = " ".join(action.detail for action in plan.actions)
    assert HYDRO_NOW in details and METEO_LISTING in details
    assert GROUNDWATER_NOW in details


def test_source_unavailable_title_is_neutral_and_the_detail_names_chmu(server):
    assert ERROR_CODES["source_unavailable"].title == "Data source unavailable"
    with respx.mock(assert_all_called=False) as router:
        serve_catalog(router, "hydro_now_outage")
        response = TestClient(rest_app).get(
            "/api/v1/stations/find", params={"provider": "CHMU", "kind": "hydro"}
        )

    problem = response.json()
    assert response.status_code == 502
    assert (problem["code"], problem["title"]) == (
        "source_unavailable",
        "Data source unavailable",
    )
    assert "ČHMÚ" in problem["detail"]
    assert problem["details"]["url"] == HYDRO_NOW


# --------------------------------------------------------------------------
# Python = obserwator = REST for the new and changed commands
# --------------------------------------------------------------------------


# The third column: the kind of root the command works on (ADR-017), or None.
PARITY = [
    ("datasets providers", {"limit": 5}, None),
    ("datasets list", {"provider": "CHMU", "limit": 10}, None),
    (
        "datasets files",
        {"dataset": HYDRO, "stations": [S1, S2], "years": "2023-2024", "limit": 10},
        None,
    ),
    ("stations find", {"provider": "CHMU", "query": "spindleruv", "limit": 10}, None),
    ("stations find", {"provider": "CHMU", "source": "store", "limit": 10}, "data"),
    ("store scan", {"provider": "CHMU", "kind": "catalog", "limit": 10}, "data"),
    ("store check", {"datasets": [HYDRO], "stations": [S1, S2]}, "raw"),
    ("store check", {"datasets": [METEO], "stations": [FULL]}, "raw"),
]


@pytest.mark.parametrize(("command", "options", "kind"), PARITY)
def test_chmu_commands_answer_alike_in_python_cli_and_rest(
    tmp_path, monkeypatch, server, frozen, chmu, command, options, kind
):
    root = None
    if kind is not None:
        raw = init_store(tmp_path / "raw")
        data = tmp_path / "data"
        # The catalog reads the synced station sources offline (ADR-015, ADR-017).
        sync_store(raw, datasets=STATION_SOURCES)
        build_catalog(data, raw_root=raw, provider="CHMU")
        root = raw.root if kind == "raw" else data
        monkeypatch.setattr(server, "root", data)
        monkeypatch.setattr(server, "raw_root", raw.root)
    local = options if root is None else {"root": root, **options}

    start = len(chmu.calls)
    python = run_command(command, options=local)
    middle = len(chmu.calls)
    printed = CliRunner().invoke(cli_app, cli_words(command, local))
    end = len(chmu.calls)
    answered = TestClient(rest_app).request(**rest_request(command, options))

    assert python.status == "ok"
    assert printed.exit_code == 0, printed.output
    assert canonical(json.loads(printed.stdout)) == canonical(python.to_json(root=root))
    assert answered.status_code == 200, answered.text
    assert canonical(answered.json()) == canonical(
        python.to_json(root=root, server=True)
    )
    requests = [
        [(c.request.method, str(c.request.url)) for c in chmu.calls[a:b]]
        for a, b in ((start, middle), (middle, end), (end, len(chmu.calls)))
    ]
    assert requests[0] == requests[1] == requests[2]


def test_store_catalog_of_chmu_is_planned_alike_offline_in_python_cli_and_rest(
    tmp_path, monkeypatch, server, frozen, chmu
):
    raw = init_store(tmp_path / "raw").root
    root = init_store(tmp_path / "data", kind="data").root
    synced = sync_store(raw, datasets=STATION_SOURCES)
    monkeypatch.setattr(server, "root", root)
    monkeypatch.setattr(server, "raw_root", raw)
    options = {"provider": "CHMU"}
    local = {"root": root, "raw_root": raw, **options}

    start = len(chmu.calls)
    python = check_command("store catalog", options=local)
    printed = CliRunner().invoke(
        cli_app, [*cli_words("store catalog", local), "--check"]
    )
    request = rest_request("store catalog", options)
    request["url"] += "?check=true"
    answered = TestClient(rest_app).request(**request)

    assert len(chmu.calls) == start  # the plan reads the stored sources only
    assert python.result.items == ()
    # Five stored source files (hydro now has meta1 and meta3), the two optional
    # groundwater lists (not stored, ADR-032), the series indexes and the catalog: no
    # catalog yet, so nothing is current.
    assert len(synced.items) == 5
    assert [action.status for action in python.result.actions] == ["missing"] * 9
    stored = [item.version.relative_to(raw).as_posix() for item in synced.items]
    assert all(
        path in action.detail
        for path, action in zip(stored, python.result.actions[:5], strict=True)
    )
    assert canonical(json.loads(printed.stdout)) == canonical(python.to_json(root=root))
    assert answered.status_code == 200, answered.text
    assert canonical(answered.json()) == canonical(
        python.to_json(root=root, server=True)
    )
    assert not list((root / "stations").glob("**/*.geojson"))
