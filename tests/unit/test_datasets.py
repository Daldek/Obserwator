"""Offline checks for source registry and physical archive enumeration."""

import importlib
import json
import re
from datetime import date

import pytest

from obserwator.commands import command_schema, run_command
from obserwator.datasets import (
    CATALOG_DATASET,
    DATASET_KEY_ALIASES,
    DATASET_KEY_PATTERN,
    archive_files,
    datasets,
    get_dataset,
    get_provider,
    parse_months,
    parse_years,
    providers,
    resolve_dataset_key,
    station_source_files,
)
from obserwator.exceptions import ObserwatorValidationError
from obserwator.urls import IMGW_PUBLIC_DATA_URL

# ``obserwator.datasets`` as a module: the package attribute is the ``datasets`` function.
DATASETS_MODULE = importlib.import_module("obserwator.datasets")
_BASE = "https://danepubliczne.imgw.pl/data/dane_pomiarowo_obserwacyjne"

# (key, kind, in_store, time_unit, year_type, first_year, legacy_alias) — spec §13.4.
_REGISTRY = [
    ("pl.imgw.hydro_daily", "hydro", True, "day", "hydrological", 1951, "hydro/dobowe"),
    (
        "pl.imgw.hydro_monthly",
        "hydro",
        True,
        "month",
        "hydrological",
        1951,
        "hydro/miesieczne",
    ),
    (
        "pl.imgw.hydro_semiannual",
        "hydro",
        True,
        "half_year",
        "hydrological",
        1951,
        "hydro/polroczne_i_roczne",
    ),
    (
        "pl.imgw.meteo_climate_daily",
        "meteo",
        True,
        "day",
        "calendar",
        1951,
        "meteo/dobowe/klimat",
    ),
    (
        "pl.imgw.meteo_precip_daily",
        "meteo",
        True,
        "day",
        "calendar",
        1950,
        "meteo/dobowe/opad",
    ),
    (
        "pl.imgw.meteo_synop_daily",
        "meteo",
        True,
        "day",
        "calendar",
        1966,
        "meteo/dobowe/synop",
    ),
    ("pl.imgw.hydro_stations", "hydro", True, "station_list", "none", None, None),
    ("pl.imgw.meteo_stations", "meteo", True, "station_list", "none", None, None),
    ("pl.imgw.hydro_now", "hydro", True, "station_list", "none", None, None),
    ("pl.imgw.meteo_now", "meteo", True, "station_list", "none", None, None),
    ("pl.imgw.hydro_details", "hydro", True, "station_list", "none", None, None),
    ("pl.imgw.pmaxtp", None, True, "cell", "none", None, None),
    # The captures of current data (ADR-030 D2): sealed by store sync from the spool.
    ("pl.imgw.hydro_current", "hydro", True, "snapshot", "calendar", None, None),
    ("pl.imgw.meteo_current", "meteo", True, "snapshot", "calendar", None, None),
    ("pl.imgw.meteo_synop_current", "meteo", True, "snapshot", "calendar", None, None),
    (
        "pl.imgw.warnings_hydro_current",
        "hydro",
        True,
        "snapshot",
        "calendar",
        None,
        None,
    ),
    (
        "pl.imgw.warnings_meteo_current",
        "meteo",
        True,
        "snapshot",
        "calendar",
        None,
        None,
    ),
    ("pl.imgw.hydro_states_current", "hydro", True, "snapshot", "calendar", None, None),
    ("pl.imgw.hydro_phenomena", "hydro", False, "day", "hydrological", 1951, None),
    (
        "pl.imgw.meteo_climate_monthly",
        "meteo",
        False,
        "month",
        "calendar",
        1951,
        "meteo/miesieczne/klimat",
    ),
    (
        "pl.imgw.meteo_precip_monthly",
        "meteo",
        False,
        "month",
        "calendar",
        1950,
        "meteo/miesieczne/opad",
    ),
    (
        "pl.imgw.meteo_synop_monthly",
        "meteo",
        False,
        "month",
        "calendar",
        1960,
        "meteo/miesieczne/synop",
    ),
    (
        "pl.imgw.meteo_climate_terms",
        "meteo",
        False,
        "term",
        "calendar",
        1951,
        "meteo/terminowe/klimat",
    ),
    (
        "pl.imgw.meteo_synop_terms",
        "meteo",
        False,
        "term",
        "calendar",
        1966,
        "meteo/terminowe/synop",
    ),
    ("pl.imgw.warnings_hydro_archive", "hydro", False, "month", "calendar", 2017, None),
    ("pl.imgw.warnings_meteo_archive", "meteo", False, "month", "calendar", 2017, None),
    ("pl.imgw.actinometric", "meteo", False, "term", "calendar", 1990, None),
]
# ČHMÚ datasets after the IMGW-PIB ones (spec 2026-10-18 §2.2).
_CHMU_KEYS = [
    "cz.chmu.hydro_daily",
    "cz.chmu.meteo_daily",
    "cz.chmu.hydro_stations",
    "cz.chmu.meteo_stations",
    "cz.chmu.hydro_now",
    "cz.chmu.meteo_now",
]


def test_registry_has_the_imgw_descriptors_with_spec_fields():
    descriptors = datasets(provider="IMGW")
    assert [
        (
            d.key,
            d.kind,
            d.in_store,
            d.time_unit,
            d.year_type,
            d.first_year,
            d.legacy_alias,
        )
        for d in descriptors
    ] == _REGISTRY
    # Decision 1a of ADR-028: a slug is the provider's acronym and the key's last part.
    assert all(entry.slug == f"imgw_{entry.key[8:]}" for entry in descriptors)
    for old in ("hydro_daily", "meteo_precip_daily", "pmaxtp"):
        with pytest.raises(ObserwatorValidationError) as exc:
            get_dataset(old)
        assert exc.value.details["value"] == old
    assert all(entry.title and entry.license.id == "IMGW-PIB" for entry in descriptors)
    assert all(
        entry.parser is None and not entry.variables
        for entry in descriptors
        if not entry.in_store
    )


def test_datasets_kind_filter():
    meteo = datasets(kind="meteo")
    assert [d.key for d in meteo] == [
        row[0] for row in _REGISTRY if row[1] == "meteo"
    ] + ["cz.chmu.meteo_daily", "cz.chmu.meteo_stations", "cz.chmu.meteo_now"]
    assert [d.key for d in datasets(kind="hydro")] == [
        row[0] for row in _REGISTRY if row[1] == "hydro"
    ] + ["cz.chmu.hydro_daily", "cz.chmu.hydro_stations", "cz.chmu.hydro_now"]
    with pytest.raises(ObserwatorValidationError) as exc:
        datasets(kind="pmaxtp")
    assert exc.value.code == "validation_error"


@pytest.mark.parametrize("key", [row[0] for row in _REGISTRY if row[-1] is not None])
def test_get_dataset_resolves_key_slug_and_legacy_alias(key):
    descriptor = get_dataset(key)
    assert get_dataset(descriptor.slug) is descriptor
    assert descriptor.legacy_alias is not None
    assert get_dataset(descriptor.legacy_alias) is descriptor
    assert descriptor.key == key


def test_get_dataset_unknown_lists_allowed_keys():
    with pytest.raises(ObserwatorValidationError) as exc:
        get_dataset("hydro/tygodniowe")
    assert exc.value.code == "validation_error"
    assert exc.value.details["allowed"] == [row[0] for row in _REGISTRY] + _CHMU_KEYS


def test_every_dataset_key_follows_the_key_convention():
    # IMGW-20 criterion 1: the consumer's pattern, checked on the whole registry.
    assert DATASET_KEY_PATTERN == r"^[a-z]{2}\.[a-z][a-z0-9]*\.[a-z][a-z0-9_]*$"
    keys = [d.key for d in datasets()] + [CATALOG_DATASET]
    for key in keys:
        assert re.fullmatch(DATASET_KEY_PATTERN, key), key
        assert resolve_dataset_key(key) == key
    for old, current in DATASET_KEY_ALIASES.items():
        assert re.fullmatch(DATASET_KEY_PATTERN, old), old
        assert old not in keys and current in keys, (old, current)


def test_a_renamed_key_is_read_from_the_store_but_no_input_takes_it():
    # ADR-028: ČHMÚ's keys of 3.0.x resolve, as stored history, to the current ones.
    assert resolve_dataset_key("cz.chmi.hydro_daily") == "cz.chmu.hydro_daily"
    assert resolve_dataset_key("cz.chmu.hydro_daily") == "cz.chmu.hydro_daily"
    with pytest.raises(ObserwatorValidationError) as exc:
        get_dataset("cz.chmi.hydro_daily")
    assert exc.value.details["value"] == "cz.chmi.hydro_daily"
    for old in ("CHMI", "IMGW-PIB"):
        with pytest.raises(ObserwatorValidationError):
            get_provider(old)
    # Unknown keys, slugs and legacy input words are not keys Obserwator knows.
    for value in ("sk.shmu.hydro_daily", "hydro_daily", "hydro/dobowe"):
        assert resolve_dataset_key(value) is None


@pytest.mark.parametrize(
    ("alias", "reason"),
    [("meteo/terminowe/opad", "not_published")],
)
def test_aliases_without_descriptor_explain_reason(alias, reason):
    with pytest.raises(ObserwatorValidationError) as exc:
        archive_files(alias, years=2023, months=1)
    assert exc.value.code == "validation_error"
    assert exc.value.details["reason"] == reason
    assert alias in str(exc.value)


# ADR-030: the captures of current data (H2a), served with their (tier, time_unit,
# archive_scope); every other served dataset is verified.
_CAPTURES = {
    "pl.imgw.hydro_current": ("operational", "snapshot", "country_day"),
    "pl.imgw.meteo_current": ("operational", "snapshot", "country_day"),
    "pl.imgw.meteo_synop_current": ("operational", "snapshot", "country_day"),
    "pl.imgw.warnings_hydro_current": ("operational", "snapshot", "country_day"),
    "pl.imgw.warnings_meteo_current": ("operational", "snapshot", "country_day"),
    "pl.imgw.hydro_states_current": ("operational", "snapshot", "country_day"),
}
# ADR-030: the datasets of the operational series, declared before the steps that
# serve them, with their (tier, time_unit, archive_scope).
_DECLARED = {
    "pl.imgw.hydro_operational": ("operational", "hour", "country_day"),
    "pl.imgw.hydro_telemetry": ("telemetry", "ten_minutes", "country"),
    "cz.chmu.hydro_recent": ("operational", "ten_minutes", "country_day"),
    "cz.chmu.hydro_current": ("operational", "ten_minutes", "country_day"),
    "cz.chmu.hydro_hourly": ("verified", "hour", "station_year"),
}


def test_every_served_dataset_but_the_captures_is_verified_and_its_document_says_so():
    served = datasets()
    assert {
        d.key: (d.tier, d.time_unit, d.archive_scope)
        for d in served
        if d.tier != "verified"
    } == _CAPTURES
    listed = run_command("datasets list", options={"limit": 100}).to_json()
    assert [(item["key"], item["tier"]) for item in listed["result"]] == [
        (d.key, d.tier) for d in served
    ]


def test_declared_datasets_follow_the_served_ones_with_their_tiers():
    served = datasets()
    registry = datasets(pending=True)
    assert registry[: len(served)] == served
    declared = registry[len(served) :]
    assert {d.key: (d.tier, d.time_unit, d.archive_scope) for d in declared} == (
        _DECLARED
    )
    assert [d.key for d in datasets(kind="hydro", provider="CHMU", pending=True)] == [
        "cz.chmu.hydro_daily",
        "cz.chmu.hydro_stations",
        "cz.chmu.hydro_now",
        "cz.chmu.hydro_recent",
        "cz.chmu.hydro_current",
        "cz.chmu.hydro_hourly",
    ]
    # The conventions of the served registry hold before a step serves them.
    names = [name for d in registry for name in (d.key, d.slug)]
    assert len(names) == len(set(names))
    for descriptor in declared:
        prefix, _, name = descriptor.key.rpartition(".")
        assert re.fullmatch(DATASET_KEY_PATTERN, descriptor.key)
        assert prefix == get_provider(descriptor.provider).key_prefix
        assert descriptor.slug == f"{prefix.partition('.')[2]}_{name}"


def test_no_command_offers_or_takes_a_declared_dataset_before_its_step():
    declared = {d.key: d for d in datasets(pending=True) if d.key in _DECLARED}
    for key, descriptor in declared.items():
        for name in (key, descriptor.slug):
            with pytest.raises(ObserwatorValidationError) as exc:
                get_dataset(name)
            assert key not in exc.value.details["allowed"]
        assert resolve_dataset_key(key) is None
    offered = {key for provider in providers() for key in provider.datasets}
    schema = json.dumps(command_schema())
    assert [key for key in declared if key in offered or key in schema] == []


# Golden URLs generated once from the removed build_hydro_url/build_meteo_url.
@pytest.mark.parametrize(
    ("dataset", "years", "months", "urls"),
    [
        (
            "pl.imgw.hydro_phenomena",
            2023,
            None,
            [f"{_BASE}/dane_hydrologiczne/dobowe/2023/zjaw_2023.zip"],
        ),
        (
            "meteo/miesieczne/klimat",
            [1955, 1995, 1991, 2023],
            None,
            [
                f"{_BASE}/dane_meteorologiczne/miesieczne/klimat/1951_1955/1951_1955_m_k.zip",
                f"{_BASE}/dane_meteorologiczne/miesieczne/klimat/1991_1995/1991_1995_m_k.zip",
                f"{_BASE}/dane_meteorologiczne/miesieczne/klimat/2023/2023_m_k.zip",
            ],
        ),
        (
            "meteo/miesieczne/opad",
            [1950, 1955, 1995, 2023],
            [2],
            [
                f"{_BASE}/dane_meteorologiczne/miesieczne/opad/1950_1955/1950_1955_m_o.zip",
                f"{_BASE}/dane_meteorologiczne/miesieczne/opad/1991_1995/1991_1995_m_o.zip",
                f"{_BASE}/dane_meteorologiczne/miesieczne/opad/2023/2023_m_o.zip",
            ],
        ),
        (
            "pl.imgw.meteo_synop_monthly",
            "1960-1966,1995,2023",
            None,
            [
                f"{_BASE}/dane_meteorologiczne/miesieczne/synop/1960_1965/1960_1965_m_s.zip",
                f"{_BASE}/dane_meteorologiczne/miesieczne/synop/1966_1970/1966_1970_m_s.zip",
                f"{_BASE}/dane_meteorologiczne/miesieczne/synop/1991_1995/1991_1995_m_s.zip",
                f"{_BASE}/dane_meteorologiczne/miesieczne/synop/2023/2023_m_s.zip",
            ],
        ),
        (
            "meteo/terminowe/klimat",
            [1995, 2001],
            [1],
            [
                f"{_BASE}/dane_meteorologiczne/terminowe/klimat/1991_1995/1995_k.zip",
                f"{_BASE}/dane_meteorologiczne/terminowe/klimat/2001/2001_01_k.zip",
            ],
        ),
    ],
)
def test_download_only_datasets_match_legacy_urls(dataset, years, months, urls):
    files = archive_files(dataset, years=years, months=months)
    assert [item.url for item in files] == urls
    assert {item.dataset for item in files} == {get_dataset(dataset).key}


def test_meteo_monthly_folder_archive_covers_whole_folder():
    (archive,) = archive_files("pl.imgw.meteo_climate_monthly", years="1996-2000")
    assert (archive.year, archive.month) == (1996, None)
    assert (archive.period_start, archive.period_end) == (
        date(1996, 1, 1),
        date(2000, 12, 31),
    )


def test_synop_monthly_starts_in_1960():
    with pytest.raises(ObserwatorValidationError) as exc:
        archive_files("pl.imgw.meteo_synop_monthly", years=1955)
    assert exc.value.details["minimum"] == 1960


@pytest.mark.parametrize(
    ("years", "expected"),
    [
        (2024, [2024]),
        ("2020-2023", [2020, 2021, 2022, 2023]),
        ("2020,2022", [2020, 2022]),
        ([2020, "2022-2023"], [2020, 2022, 2023]),
        ((2023, "2023", " 2021-2021 "), [2021, 2023]),
    ],
)
def test_years_forms_give_same_files_as_int_lists(years, expected):
    assert parse_years(years) == tuple(expected)
    assert archive_files("pl.imgw.hydro_monthly", years=years) == archive_files(
        "pl.imgw.hydro_monthly", years=expected
    )


@pytest.mark.parametrize(
    "years", [[], "", "2023-2020", "0", "10000", "20x", [True], 2023.0, [None], "2020,"]
)
def test_invalid_years_raise_validation_error(years):
    with pytest.raises(ObserwatorValidationError) as exc:
        parse_years(years)
    assert exc.value.details["option"] == "years"


def test_months_forms():
    assert parse_months("3,1,1") == (1, 3)
    assert parse_months([12, "2"]) == (2, 12)
    assert parse_months(5) == (5,)
    for bad in (0, "13", "1-3", [], [True]):
        with pytest.raises(ObserwatorValidationError):
            parse_months(bad)


def test_params_narrow_semiannual_and_are_rejected_elsewhere():
    files = archive_files(
        "hydro/polroczne_i_roczne", years=2020, params=["T", "Q", "Q"]
    )
    assert [item.param for item in files] == ["Q", "T"]
    assert [
        item.param
        for item in archive_files("pl.imgw.hydro_semiannual", years=2020, params="H")
    ] == ["H"]
    with pytest.raises(ObserwatorValidationError) as exc:
        archive_files("pl.imgw.hydro_monthly", years=2020, params=["H"])
    assert exc.value.details["option"] == "params"
    for bad in ([], ["X"]):
        with pytest.raises(ObserwatorValidationError):
            archive_files("pl.imgw.hydro_semiannual", years=2020, params=bad)


def test_hydro_monthly_physical_archive_count_and_calendar_boundaries():
    archives = archive_files(
        "pl.imgw.hydro_daily", years=[2022, 2022, 2024, 2024], months=[1, 3, 3, 12]
    )
    assert [item.server_path.split("/")[-1] for item in archives] == [
        "codz_2022_01.zip",
        "codz_2022_03.zip",
        "codz_2022_12.zip",
        "codz_2024.zip",
    ]
    assert (archives[0].period_start, archives[0].period_end) == (
        date(2021, 11, 1),
        date(2021, 11, 30),
    )
    assert (archives[1].period_start, archives[1].period_end) == (
        date(2022, 1, 1),
        date(2022, 1, 31),
    )
    assert (archives[-1].period_start, archives[-1].period_end) == (
        date(2023, 11, 1),
        date(2024, 10, 31),
    )
    assert len(archive_files("pl.imgw.hydro_daily", years=[2022])) == 12
    assert len(archive_files("pl.imgw.hydro_daily", years=[2024])) == 1


def test_hydro_monthly_and_semiannual_are_distinct_files():
    monthly = archive_files("pl.imgw.hydro_monthly", years=[2024], months=[1, 12])
    semiannual = archive_files("pl.imgw.hydro_semiannual", years=[2024], months=[1, 12])
    assert [item.server_path.split("/")[-1] for item in monthly] == ["mies_2024.zip"]
    assert [item.param for item in semiannual] == ["H", "Q", "T"]
    assert [item.server_path.split("/")[-1] for item in semiannual] == [
        "polr_H_2024.zip",
        "polr_Q_2024.zip",
        "polr_T_2024.zip",
    ]


@pytest.mark.parametrize(
    ("dataset", "year", "filename", "folder"),
    [
        ("meteo_climate_daily", 1951, "1951_k.zip", "1951_1955"),
        ("meteo_climate_daily", 2000, "2000_k.zip", "1996_2000"),
        ("meteo_precip_daily", 1950, "1950_o.zip", "1950_1955"),
        ("meteo_precip_daily", 1955, "1955_o.zip", "1950_1955"),
        ("meteo_precip_daily", 2000, "2000_o.zip", "1996_2000"),
        ("meteo_climate_daily", 2001, "2001_02_k.zip", "2001"),
        ("meteo_precip_daily", 2001, "2001_02_o.zip", "2001"),
    ],
)
def test_meteo_archive_layout(dataset, year, filename, folder):
    files = archive_files(f"pl.imgw.{dataset}", years=[year], months=[2, 2])
    assert len(files) == (1 if year <= 2000 else 1)
    assert files[0].server_path.endswith(f"/{folder}/{filename}")
    assert files[0].year_type == "calendar"


def test_calendar_leap_and_monthly_filter():
    files = archive_files("pl.imgw.meteo_precip_daily", years=[2004], months=[2])
    assert (files[0].period_start, files[0].period_end) == (
        date(2004, 2, 1),
        date(2004, 2, 29),
    )
    assert len(archive_files("pl.imgw.meteo_precip_daily", years=[2001])) == 12


def test_station_lists_are_real_csv_sources():
    hydro, meteo = station_source_files()
    assert hydro.server_path == "dane_hydrologiczne/lista_stacji_hydro.csv"
    assert meteo.server_path == "dane_meteorologiczne/wykaz_stacji.csv"
    for archive in (hydro, meteo):
        assert archive.year is archive.month is archive.param is None
        assert archive.year_type == "none"
        assert archive.period_start is archive.period_end is None
        assert archive.url == f"{IMGW_PUBLIC_DATA_URL}/{archive.server_path}"


@pytest.mark.parametrize(
    "dataset, years, months",
    [
        ("pl.imgw.meteo_stations", [2024], None),
        ("pl.imgw.pmaxtp", [2024], None),
        ("pl.imgw.hydro_daily", [1950], None),
        ("pl.imgw.meteo_climate_daily", [1950], None),
        ("pl.imgw.hydro_daily", [2022], [13]),
        ("pl.imgw.meteo_precip_daily", [2024], []),
        ("pl.imgw.hydro_phenomena", [1950], None),
    ],
)
def test_invalid_choices_raise_validation_error(dataset, years, months):
    with pytest.raises(ObserwatorValidationError):
        archive_files(dataset, years=years, months=months)


_SYNOP_TERMS = "pl.imgw.meteo_synop_terms"
_SYNOP_DIR = f"{_BASE}/dane_meteorologiczne/terminowe/synop"


def test_synop_terms_station_files_follow_the_folders_and_the_station_number():
    # ŚWINOUJŚCIE 353140200 and ŁEBA 354170120: the files carry the last 3 digits.
    files = archive_files(
        "meteo/terminowe/synop",
        years="1966-1971,2000,2001",
        stations=["354170120", "353140200"],
    )
    assert [item.url for item in files] == [
        f"{_SYNOP_DIR}/1966_1970/1966_1970_200_s.zip",
        f"{_SYNOP_DIR}/1971_1975/1971_1975_200_s.zip",
        f"{_SYNOP_DIR}/1996_2000/1996_2000_200_s.zip",
        f"{_SYNOP_DIR}/2001/2001_200_s.zip",
        f"{_SYNOP_DIR}/1966_1970/1966_1970_120_s.zip",
        f"{_SYNOP_DIR}/1971_1975/1971_1975_120_s.zip",
        f"{_SYNOP_DIR}/1996_2000/1996_2000_120_s.zip",
        f"{_SYNOP_DIR}/2001/2001_120_s.zip",
    ]
    folder, year = files[0], files[3]
    assert (folder.year, folder.period_start, folder.period_end) == (
        1966,
        date(1966, 1, 1),
        date(1970, 12, 31),
    )
    assert (year.year, year.month, year.period_end) == (2001, None, date(2001, 12, 31))
    # The name has only the station number, so the file carries no station code.
    assert {item.station_code for item in files} == {None}


def test_synop_terms_codes_of_one_station_number_name_one_file():
    files = archive_files(_SYNOP_TERMS, years=2024, stations=["353140200", "253140200"])
    assert [item.server_path.rsplit("/", 1)[1] for item in files] == ["2024_200_s.zip"]


def test_synop_terms_months_select_the_monthly_country_files_from_2001():
    files = archive_files(_SYNOP_TERMS, years="2000-2026", months="10,1")
    assert [item.url for item in files][-2:] == [
        f"{_SYNOP_DIR}/2026/2026_01_s.zip",
        f"{_SYNOP_DIR}/2026/2026_10_s.zip",
    ]
    assert len(files) == 2 * 26 and files[0].server_path.endswith("/2001/2001_01_s.zip")
    assert (files[-1].period_start, files[-1].period_end) == (
        date(2026, 10, 1),
        date(2026, 10, 31),
    )
    with pytest.raises(ObserwatorValidationError) as exc:
        archive_files(_SYNOP_TERMS, years="1990-2000", months=1)
    assert exc.value.details["option"] == "months"


@pytest.mark.parametrize(
    ("options", "option"),
    [
        ({"years": 2024}, "stations"),
        ({"stations": ["353140200"]}, "years"),
        ({"years": 1965, "stations": ["353140200"]}, "years"),
        ({"years": 2024, "stations": ["200"]}, "stations"),
        ({"years": 2024, "stations": ["0-203-1-001000"]}, "stations"),
    ],
)
def test_synop_terms_selection_errors(options, option):
    with pytest.raises(ObserwatorValidationError) as exc:
        archive_files(_SYNOP_TERMS, **options)
    assert exc.value.details["option"] == option


@pytest.mark.parametrize(
    "name",
    [
        "1966_1970/1966_1970_200_s.zip",
        "1996_2000/1996_2000_120_s.zip",
        "2024/2024_200_s.zip",
        "2026/2026_03_s.zip",
    ],
)
def test_synop_terms_paths_map_back_to_their_files(name):
    archive = DATASETS_MODULE._archive_from_path(
        _SYNOP_TERMS, f"dane_meteorologiczne/terminowe/synop/{name}"
    )
    assert archive is not None and archive.url == f"{_SYNOP_DIR}/{name}"
    selection = (
        {"months": archive.month}
        if archive.month is not None
        else {"stations": ["353140200", "354170120"]}
    )
    assert archive in archive_files(_SYNOP_TERMS, years=archive.year, **selection)


@pytest.mark.parametrize(
    "name",
    [
        "1966_1970/1971_1975_200_s.zip",  # the name's period is not the folder's
        "1999/1999_200_s.zip",  # a year until 2000 lies in a five-year folder
        "1961_1965/1961_1965_200_s.zip",  # before the first year
        "1996_2000/1996_2000_03_s.zip",  # monthly files only from 2001
        "2026/2026_13_s.zip",
        "2024/2024_200_k.zip",
    ],
)
def test_synop_terms_foreign_paths_are_no_files(name):
    assert (
        DATASETS_MODULE._archive_from_path(
            _SYNOP_TERMS, f"dane_meteorologiczne/terminowe/synop/{name}"
        )
        is None
    )


def test_warning_archives_are_monthly_files_outside_the_measurement_data():
    files = archive_files(
        "pl.imgw.warnings_hydro_archive", years="2017-2018", months=12
    )
    assert [item.url for item in files] == [
        "https://danepubliczne.imgw.pl/data/arch/ost_hydro/2017/12.zip",
        "https://danepubliczne.imgw.pl/data/arch/ost_hydro/2018/12.zip",
    ]
    assert [item.server_path for item in files][0] == "arch/ost_hydro/2017/12.zip"
    assert (files[1].month, files[1].period_start, files[1].period_end) == (
        12,
        date(2018, 12, 1),
        date(2018, 12, 31),
    )
    meteo = archive_files("pl.imgw.warnings_meteo_archive", years=2024)
    assert [item.server_path for item in meteo] == [
        f"arch/ost_meteo/2024/{month:02d}.zip" for month in range(1, 13)
    ]
    assert (
        DATASETS_MODULE._archive_from_path(
            "pl.imgw.warnings_meteo_archive", "arch/ost_meteo/2024/05.zip"
        )
        == meteo[4]
    )
    for options in ({"years": 2016}, {"years": 2024, "stations": ["353140200"]}):
        with pytest.raises(ObserwatorValidationError):
            archive_files("pl.imgw.warnings_hydro_archive", **options)


def test_actinometric_files_are_named_only_in_the_folder_index():
    with pytest.raises(ObserwatorValidationError) as exc:
        archive_files("pl.imgw.actinometric", years=2015)
    assert exc.value.details["reason"] == "listed"
    # The selection is checked first: its folders carry station names, no codes.
    for options, option in (
        ({"years": 2015, "stations": ["351160424"]}, "stations"),
        ({}, "years"),
        ({"years": 1989}, "years"),
    ):
        with pytest.raises(ObserwatorValidationError) as exc:
            archive_files("pl.imgw.actinometric", **options)
        assert exc.value.details["option"] == option


def test_actinometric_paths_take_the_years_of_their_year_folder():
    def path(relative):
        return DATASETS_MODULE._archive_from_path(
            "pl.imgw.actinometric", f"dane_aktynometryczne/{relative}"
        )

    ranged = path("Kłodzko/Źródłowe/1991-1992/Klodzko1991-1992.xls")
    assert (ranged.year, ranged.period_start, ranged.period_end) == (
        1991,
        date(1991, 1, 1),
        date(1992, 12, 31),
    )
    assert ranged.url == (
        f"{_BASE}/dane_aktynometryczne/K%C5%82odzko/%C5%B9r%C3%B3d%C5%82owe/"
        "1991-1992/Klodzko1991-1992.xls"
    )
    summary = path("Promieniowanie słoneczne_zakres danych.xlsx")
    assert (summary.year, summary.year_type, summary.period_start) == (
        None,
        "none",
        None,
    )
    assert path("Kłodzko/") is None
