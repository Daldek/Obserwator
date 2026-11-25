"""Provider files (ADR-033): the fields of a provider file and the files of ``nogat.toml``."""

import copy
import hashlib
import json
import re
from pathlib import Path

import pytest

from obserwator._environment import config_file
from obserwator._provider_files import (
    FIELDS,
    LINE_MAX,
    MAX_BYTES,
    NAME_MAX,
    SHORT_NAME_MAX,
    TIERS,
    load_provider_files,
    read_provider_file,
)
from obserwator.datasets import _daily_variables
from obserwator.exceptions import ObserwatorValidationError

FIXTURE = Path(__file__).parents[1] / "fixtures" / "files"
RESERVED = frozenset({"imgw", "chmu"})
VARIABLES = _daily_variables()
LINE = "Źródło danych: Sieć Testowa, licencja CC BY 4.0"
MINIMAL = {
    "id": "SIEC",
    "short_name": "Sieć Testowa",
    "name": "Sieć Testowa Operatora sp. z o.o.",
    "country": "PL",
    "source_class": "other",
    "stations": "siec/stations.geojson",
    "license": {
        "id": "CC-BY-4.0",
        "url": "https://creativecommons.org/licenses/by/4.0/",
    },
    "attribution": {"line": LINE},
    "datasets": {
        "hydro_daily": {
            "directory": "siec/hydro",
            "variables": {"H": "cm", "Q": "m3/s"},
        }
    },
}
DROP = object()
"""A change that removes the field."""


def toml_value(value):
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, list):
        return "[" + ", ".join(toml_value(item) for item in value) + "]"
    raise TypeError(value)


def toml_text(document):
    """A TOML document of strings, integers, lists and tables (tables as sections)."""
    lines = []

    def table(values, header):
        if header:
            lines.append("[" + ".".join(json.dumps(key) for key in header) + "]")
        for key, value in values.items():
            if not isinstance(value, dict):
                lines.append(f"{json.dumps(key)} = {toml_value(value)}")
        for key, value in values.items():
            if isinstance(value, dict):
                table(value, (*header, key))

    table(document, ())
    return "\n".join(lines) + "\n"


def provider_file(directory, changes=None, *, name="siec.toml", base=MINIMAL):
    """Write ``base`` with ``changes`` (a key or a tuple of keys to a value or DROP)."""
    document = copy.deepcopy(base)
    for keys, value in (changes or {}).items():
        *parents, last = keys if isinstance(keys, tuple) else (keys,)
        table = document
        for key in parents:
            table = table.setdefault(key, {})
        if value is DROP:
            del table[last]
        else:
            table[last] = value
    path = directory / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(toml_text(document), encoding="utf-8")
    return path


def read(path, reserved=RESERVED):
    return read_provider_file(path, reserved=reserved, variables=VARIABLES)


def refusal(path, reserved=RESERVED):
    """The details of the refusal of ``path``, whose ``path`` must name the file."""
    with pytest.raises(ObserwatorValidationError) as caught:
        read(path, reserved)
    assert caught.value.details["path"] == str(path)
    return caught.value.details


# --- a valid file ----------------------------------------------------------------------


def test_minimal_file_has_its_fields_and_the_defaults(tmp_path):
    path = provider_file(tmp_path)
    found = read(path)
    assert found.path == path
    assert found.sha256 == hashlib.sha256(path.read_bytes()).hexdigest()
    assert (found.id, found.short_name, found.name, found.country) == (
        "SIEC",
        "Sieć Testowa",
        "Sieć Testowa Operatora sp. z o.o.",
        "PL",
    )
    assert (found.source_class, found.tier, found.publication) == (
        "other",
        "operational",
        "private",
    )
    assert found.stations == "siec/stations.geojson"
    assert found.stations_path == tmp_path / "siec" / "stations.geojson"
    assert (found.license_id, found.license_url, found.terms_url) == (
        "CC-BY-4.0",
        "https://creativecommons.org/licenses/by/4.0/",
        None,
    )
    assert (found.line, found.processed, found.short, found.links) == (
        LINE,
        None,
        None,
        (),
    )
    (dataset,) = found.datasets
    assert (dataset.name, dataset.kind, dataset.directory, dataset.path) == (
        "hydro_daily",
        "hydro",
        "siec/hydro",
        tmp_path / "siec" / "hydro",
    )
    assert dict(dataset.variables) == {"H": "cm", "Q": "m3/s"}
    assert dataset.year_type == "calendar"
    assert (found.acronym, found.key_prefix) == ("siec", "pl.siec")
    assert found.screen_line() == {"text": LINE}


def test_station_code_pattern_takes_the_id_and_an_operators_code(tmp_path):
    pattern = read(provider_file(tmp_path)).station_code_pattern
    grammar = re.compile(pattern)
    assert grammar.fullmatch("SIEC-01")
    assert grammar.fullmatch("SIEC-a_b-C")
    assert grammar.fullmatch("SIEC-" + "x" * 32)
    for code in ("SIEC-" + "x" * 33, "SIEC-", "SIEC-_01", "OTHER-01", "siec-01", "01"):
        assert not grammar.fullmatch(code), code


def test_fixture_file_has_its_lines_links_and_datasets():
    found = read(FIXTURE / "siec.toml")
    assert (found.tier, found.publication) == ("operational", "public")
    assert found.processed == "Dane Sieci Testowej Operatora zostały przetworzone"
    assert found.short == "Źródło: Sieć Testowa, CC BY 4.0"
    assert found.links == (
        ("Sieć Testowa", "https://example.org/siec"),
        ("CC BY 4.0", "https://creativecommons.org/licenses/by/4.0/"),
    )
    assert found.screen_line() == {
        "text": found.line,
        "short": "Źródło: Sieć Testowa, CC BY 4.0",
        "links": [
            ["Sieć Testowa", "https://example.org/siec"],
            ["CC BY 4.0", "https://creativecommons.org/licenses/by/4.0/"],
        ],
    }
    assert [
        (item.name, item.kind, dict(item.variables), item.year_type, item.path)
        for item in found.datasets
    ] == [
        (
            "hydro_daily",
            "hydro",
            {"H": "cm", "Q": "m3/s"},
            "hydrological",
            FIXTURE / "siec" / "hydro",
        ),
        (
            "meteo_daily",
            "meteo",
            {"P": "mm", "Tmean": "degC"},
            "calendar",
            FIXTURE / "siec" / "meteo",
        ),
    ]


def test_screen_line_has_short_without_links_and_links_without_short(tmp_path):
    short = read(provider_file(tmp_path, {("attribution", "short"): "Źródło: ST"}))
    assert short.screen_line() == {"text": LINE, "short": "Źródło: ST"}
    linked = read(
        provider_file(
            tmp_path,
            {("attribution", "links"): [["Sieć Testowa", "https://example.org/siec"]]},
        )
    )
    assert linked.screen_line() == {
        "text": LINE,
        "links": [["Sieć Testowa", "https://example.org/siec"]],
    }


def test_datasets_follow_the_kinds_order_and_variables_the_files(tmp_path):
    path = provider_file(
        tmp_path,
        {
            "datasets": {
                "groundwater_daily": {
                    "directory": "siec/gw",
                    "variables": {"H_asl": "m"},
                },
                "meteo_daily": {"directory": "siec/meteo", "variables": {"P": "mm"}},
                "hydro_daily": {
                    "directory": "siec/hydro",
                    "variables": {"Q": "m3/s", "H": "cm"},
                    "year_type": "hydrological",
                },
            }
        },
    )
    found = read(path)
    assert [item.name for item in found.datasets] == [
        "hydro_daily",
        "meteo_daily",
        "groundwater_daily",
    ]
    assert [item.kind for item in found.datasets] == ["hydro", "meteo", "groundwater"]
    assert list(found.datasets[0].variables) == ["Q", "H"]
    assert [item.year_type for item in found.datasets] == [
        "hydrological",
        "calendar",
        "calendar",
    ]


@pytest.mark.parametrize(
    ("changes", "tier", "publication"),
    [
        ({"tier": "verified"}, "verified", None),
        ({"tier": "telemetry"}, "telemetry", "private"),
        ({"tier": "telemetry", "publication": "public"}, "telemetry", "public"),
        ({"publication": "public"}, "operational", "public"),
        ({"publication": "private"}, "operational", "private"),
    ],
)
def test_tier_and_publication(tmp_path, changes, tier, publication):
    found = read(provider_file(tmp_path, changes))
    assert (found.tier, found.publication) == (tier, publication)


def test_country_cz_gives_its_key_prefix(tmp_path):
    found = read(provider_file(tmp_path, {"country": "CZ", "id": "SIT2"}))
    assert (found.country, found.acronym, found.key_prefix) == ("CZ", "sit2", "cz.sit2")


def test_absolute_and_home_paths_are_kept(tmp_path, monkeypatch):
    # `~` is the user's home: HOME on POSIX, USERPROFILE on Windows (Path.expanduser).
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "home"))
    absolute = tmp_path / "elsewhere" / "stations.geojson"
    found = read(
        provider_file(
            tmp_path / "conf",
            {
                "stations": str(absolute),
                ("datasets", "hydro_daily", "directory"): "~/hydro",
            },
        )
    )
    assert found.stations_path == absolute
    assert found.datasets[0].path == tmp_path / "home" / "hydro"


@pytest.mark.parametrize(
    "identifier", ["SI", "S1", "A" * 16, "SIEC2026", "Z9"], ids=lambda v: v
)
def test_ids_of_the_grammar_are_taken(tmp_path, identifier):
    assert read(provider_file(tmp_path, {"id": identifier})).id == identifier


@pytest.mark.parametrize(
    ("field", "maximum"),
    [
        ("short_name", SHORT_NAME_MAX),
        ("name", NAME_MAX),
        (("attribution", "line"), LINE_MAX),
        (("attribution", "processed"), LINE_MAX),
        (("attribution", "short"), LINE_MAX),
    ],
    ids=str,
)
def test_text_at_its_maximum_is_taken_one_more_refused(tmp_path, field, maximum):
    longest = "Ź" * maximum
    assert read(provider_file(tmp_path, {field: longest}))
    option = "provider_file." + (field if isinstance(field, str) else ".".join(field))
    details = refusal(provider_file(tmp_path, {field: longest + "Ź"}))
    assert details["option"] == option


def test_file_of_max_bytes_is_read_one_byte_more_refused(tmp_path):
    text = toml_text(MINIMAL)
    padding = MAX_BYTES - len(text.encode()) - 2
    path = tmp_path / "siec.toml"
    # newline="": the bytes counted are those written, without Windows' CRLF.
    path.write_text(text + "#" + "x" * padding + "\n", encoding="utf-8", newline="")
    assert path.stat().st_size == MAX_BYTES
    assert read(path).id == "SIEC"
    path.write_text(
        text + "#" + "x" * (padding + 1) + "\n", encoding="utf-8", newline=""
    )
    assert refusal(path)["option"] == "provider_file"


# --- refusals ----------------------------------------------------------------------------


def test_missing_file_is_refused(tmp_path):
    assert refusal(tmp_path / "absent.toml")["option"] == "provider_file"


def test_directory_is_refused(tmp_path):
    directory = tmp_path / "siec.toml"
    directory.mkdir()
    assert refusal(directory)["option"] == "provider_file"


def test_non_utf8_is_refused(tmp_path):
    path = tmp_path / "siec.toml"
    path.write_bytes(b"# \xb6ie\xe6\n" + toml_text(MINIMAL).encode())
    assert refusal(path)["option"] == "provider_file"


def test_invalid_toml_is_refused(tmp_path):
    path = tmp_path / "siec.toml"
    path.write_text('id = "AGAIN"\n' + toml_text(MINIMAL), encoding="utf-8")
    assert refusal(path)["option"] == "provider_file"


@pytest.mark.parametrize(
    "missing",
    [
        "id",
        "short_name",
        "name",
        "country",
        "source_class",
        "stations",
        "license",
        "attribution",
        "datasets",
    ],
)
def test_missing_required_field_is_refused(tmp_path, missing):
    details = refusal(provider_file(tmp_path, {missing: DROP}))
    assert details["option"] == f"provider_file.{missing}"


def test_unknown_top_level_field_names_the_fields(tmp_path):
    details = refusal(provider_file(tmp_path, {"operator": "x"}))
    assert details["option"] == "provider_file.operator"
    assert details["allowed"] == list(FIELDS)


@pytest.mark.parametrize(
    "identifier",
    [
        "S",
        "A" * 17,
        "1SIEC",
        "Siec",
        "siec",
        "SI-EC",
        "SI EC",
        "SIĘC",
        "",
        5,
        ["SIEC"],
    ],
    ids=repr,
)
def test_id_outside_the_grammar_is_refused(tmp_path, identifier):
    assert refusal(provider_file(tmp_path, {"id": identifier}))["option"] == (
        "provider_file.id"
    )


@pytest.mark.parametrize("identifier", ["IMGW", "CHMU"])
def test_reserved_id_is_refused_by_its_lower_case(tmp_path, identifier):
    path = provider_file(tmp_path, {"id": identifier})
    assert refusal(path)["option"] == "provider_file.id"
    assert read(path, reserved=frozenset()).id == identifier
    # the names given are lower case: an upper-case entry reserves nothing
    assert read(path, reserved=frozenset({identifier})).id == identifier


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("short_name", ""),
        ("short_name", " Sieć"),
        ("short_name", "Sieć "),
        ("short_name", "Sieć\tTestowa"),
        ("short_name", 5),
        ("name", "Sieć\nTestowa"),
        ("name", ""),
        ("stations", ""),
        ("stations", ["siec/stations.geojson"]),
    ],
    ids=repr,
)
def test_bad_text_is_refused(tmp_path, field, value):
    assert refusal(provider_file(tmp_path, {field: value}))["option"] == (
        f"provider_file.{field}"
    )


@pytest.mark.parametrize(
    ("changes", "option", "allowed"),
    [
        ({"country": "DE"}, "provider_file.country", ["PL", "CZ"]),
        ({"country": "pl"}, "provider_file.country", ["PL", "CZ"]),
        ({"source_class": "national"}, "provider_file.source_class", ["other"]),
        ({"tier": "raw"}, "provider_file.tier", list(TIERS)),
        ({"tier": "Verified"}, "provider_file.tier", list(TIERS)),
        ({"publication": "open"}, "provider_file.publication", ["public", "private"]),
        (
            {"tier": "telemetry", "publication": 1},
            "provider_file.publication",
            ["public", "private"],
        ),
    ],
    ids=repr,
)
def test_value_outside_its_choices_is_refused(tmp_path, changes, option, allowed):
    details = refusal(provider_file(tmp_path, changes))
    assert (details["option"], details["allowed"]) == (option, allowed)


@pytest.mark.parametrize("publication", ["public", "private"])
def test_publication_of_a_verified_tier_is_refused(tmp_path, publication):
    path = provider_file(tmp_path, {"tier": "verified", "publication": publication})
    assert refusal(path)["option"] == "provider_file.publication"


@pytest.mark.parametrize(
    ("changes", "option"),
    [
        ({"license": "CC-BY-4.0"}, "provider_file.license"),
        ({("license", "name"): "CC BY"}, "provider_file.license.name"),
        ({("license", "id"): DROP}, "provider_file.license.id"),
        ({("license", "id"): "CC BY"}, "provider_file.license.id"),
        ({("license", "id"): "-CC"}, "provider_file.license.id"),
        ({("license", "id"): "C" * 65}, "provider_file.license.id"),
        ({("license", "url"): DROP}, "provider_file.license.url"),
        ({("license", "url"): "ftp://example.org/l"}, "provider_file.license.url"),
        ({("license", "url"): "creativecommons.org"}, "provider_file.license.url"),
        ({("license", "url"): "https://"}, "provider_file.license.url"),
        (
            {("license", "terms_url"): "example.org/t"},
            "provider_file.license.terms_url",
        ),
        ({("license", "terms_url"): ""}, "provider_file.license.terms_url"),
    ],
    ids=repr,
)
def test_bad_license_is_refused(tmp_path, changes, option):
    assert refusal(provider_file(tmp_path, changes))["option"] == option


def test_longest_license_id_and_terms_url_are_taken(tmp_path):
    found = read(
        provider_file(
            tmp_path,
            {
                ("license", "id"): "C" * 64,
                ("license", "terms_url"): "http://example.org/terms",
            },
        )
    )
    assert (found.license_id, found.terms_url) == ("C" * 64, "http://example.org/terms")


URL = "https://example.org/siec"


@pytest.mark.parametrize(
    ("changes", "option"),
    [
        ({"attribution": "Źródło"}, "provider_file.attribution"),
        ({("attribution", "logo"): URL}, "provider_file.attribution.logo"),
        ({("attribution", "line"): DROP}, "provider_file.attribution.line"),
        ({("attribution", "line"): "a\nb"}, "provider_file.attribution.line"),
        ({("attribution", "processed"): LINE}, "provider_file.attribution.processed"),
        ({("attribution", "processed"): ""}, "provider_file.attribution.processed"),
        ({("attribution", "short"): " Źródło"}, "provider_file.attribution.short"),
        (
            {("attribution", "links"): [["Nieobecne", URL]]},
            "provider_file.attribution.links",
        ),
        (
            {("attribution", "links"): [["Sieć Testowa", "example.org/siec"]]},
            "provider_file.attribution.links",
        ),
        ({("attribution", "links"): "Sieć Testowa"}, "provider_file.attribution.links"),
        (
            {("attribution", "links"): ["Sieć Testowa", URL]},
            "provider_file.attribution.links",
        ),
        (
            {("attribution", "links"): [["Sieć Testowa"]]},
            "provider_file.attribution.links",
        ),
        (
            {("attribution", "links"): [["Sieć Testowa", URL, URL]]},
            "provider_file.attribution.links",
        ),
        ({("attribution", "links"): [["", URL]]}, "provider_file.attribution.links"),
        (
            # the words must be in the shown line: the short one when given
            {
                ("attribution", "short"): "Źródło: ST",
                ("attribution", "links"): [["Sieć Testowa", URL]],
            },
            "provider_file.attribution.links",
        ),
    ],
    ids=repr,
)
def test_bad_attribution_is_refused(tmp_path, changes, option):
    assert refusal(provider_file(tmp_path, changes))["option"] == option


def test_links_may_name_words_of_the_short_line_only(tmp_path):
    found = read(
        provider_file(
            tmp_path,
            {
                ("attribution", "short"): "Źródło: ST",
                ("attribution", "links"): [["ST", URL]],
            },
        )
    )
    assert found.links == (("ST", URL),)


def test_processed_line_differs_from_the_line(tmp_path):
    found = read(provider_file(tmp_path, {("attribution", "processed"): LINE + "."}))
    assert found.processed == LINE + "."


HYDRO = ("datasets", "hydro_daily")


@pytest.mark.parametrize(
    ("changes", "option"),
    [
        ({"datasets": {}}, "provider_file.datasets"),
        ({"datasets": "hydro_daily"}, "provider_file.datasets"),
        (
            {("datasets", "rain_daily"): {"directory": "x", "variables": {"P": "mm"}}},
            "provider_file.datasets.rain_daily",
        ),
        ({HYDRO: "siec/hydro"}, "provider_file.datasets.hydro_daily"),
        (
            {(*HYDRO, "station_file"): "x.geojson"},
            "provider_file.datasets.hydro_daily.station_file",
        ),
        ({(*HYDRO, "directory"): DROP}, "provider_file.datasets.hydro_daily.directory"),
        ({(*HYDRO, "directory"): ""}, "provider_file.datasets.hydro_daily.directory"),
        ({(*HYDRO, "variables"): DROP}, "provider_file.datasets.hydro_daily.variables"),
        ({(*HYDRO, "variables"): {}}, "provider_file.datasets.hydro_daily.variables"),
        (
            {(*HYDRO, "variables"): ["H", "Q"]},
            "provider_file.datasets.hydro_daily.variables",
        ),
        (
            {(*HYDRO, "variables"): {"H": "cm", "P": "mm"}},
            "provider_file.datasets.hydro_daily.variables.P",
        ),
        (
            {(*HYDRO, "variables"): {"H": "m"}},
            "provider_file.datasets.hydro_daily.variables.H",
        ),
        (
            {(*HYDRO, "variables"): {"Q": "m3/s", "H": 1}},
            "provider_file.datasets.hydro_daily.variables.H",
        ),
        (
            {(*HYDRO, "year_type"): "water"},
            "provider_file.datasets.hydro_daily.year_type",
        ),
    ],
    ids=repr,
)
def test_bad_dataset_is_refused(tmp_path, changes, option):
    assert refusal(provider_file(tmp_path, changes))["option"] == option


def test_unknown_variable_names_the_kinds_variables(tmp_path):
    path = provider_file(tmp_path, {(*HYDRO, "variables"): {"Tmean": "degC"}})
    details = refusal(path)
    assert details["option"] == "provider_file.datasets.hydro_daily.variables.Tmean"
    assert details["allowed"] == list(VARIABLES["hydro"])


def test_year_type_refusal_names_its_choices(tmp_path):
    details = refusal(provider_file(tmp_path, {(*HYDRO, "year_type"): "water"}))
    assert details["allowed"] == ["calendar", "hydrological"]


# --- the files of nogat.toml -----------------------------------------------------------


def loaded(tmp_path, monkeypatch, lines, reserved=RESERVED):
    """``load_provider_files`` of a ``nogat.toml`` in ``tmp_path/conf`` of ``lines``."""
    config = tmp_path / "conf" / "nogat.toml"
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text("\n".join(lines) + "\n", encoding="utf-8")
    monkeypatch.setenv("NOGAT_CONFIG", str(config))
    return load_provider_files(config_file(), reserved=reserved, variables=VARIABLES)


def listed(*paths):
    return ["[obserwator]", f"provider_files = {toml_value(list(paths))}"]


def test_no_key_lists_nothing(tmp_path, monkeypatch):
    found = loaded(tmp_path, monkeypatch, ["[obserwator]", 'raw_root = "/raw"'])
    assert (found.paths, found.files, found.problems) == ((), (), ())


def test_empty_list_lists_nothing(tmp_path, monkeypatch):
    found = loaded(tmp_path, monkeypatch, listed())
    assert (found.paths, found.files, found.problems) == ((), (), ())


@pytest.mark.parametrize(
    "value", ['"siec.toml"', '["siec.toml", 1]', '[""]', "true", '{ a = "b" }']
)
def test_value_other_than_a_list_of_paths_is_one_problem(tmp_path, monkeypatch, value):
    provider_file(tmp_path / "conf")
    found = loaded(tmp_path, monkeypatch, ["[obserwator]", f"provider_files = {value}"])
    assert (found.paths, found.files) == ((), ())
    (problem,) = found.problems
    assert isinstance(problem, ObserwatorValidationError)
    assert problem.details == {
        "option": "provider_files",
        "path": str(tmp_path / "conf" / "nogat.toml"),
    }


def test_paths_are_relative_to_the_directory_of_nogat_toml(tmp_path, monkeypatch):
    path = provider_file(tmp_path / "conf" / "providers")
    monkeypatch.chdir(tmp_path)
    found = loaded(tmp_path, monkeypatch, listed("providers/siec.toml"))
    assert found.paths == (path,)
    assert [item.path for item in found.files] == [path]
    assert found.files[0].stations_path == path.parent / "siec" / "stations.geojson"
    assert found.problems == ()


def test_a_path_listed_twice_is_read_once(tmp_path, monkeypatch):
    path = provider_file(tmp_path / "conf")
    found = loaded(tmp_path, monkeypatch, listed("siec.toml", "./siec.toml", str(path)))
    assert found.paths == (path,)
    assert [item.id for item in found.files] == ["SIEC"]
    assert found.problems == ()


def test_a_second_file_of_a_taken_id_is_its_own_problem(tmp_path, monkeypatch):
    first = provider_file(tmp_path / "conf", name="a.toml")
    second = provider_file(tmp_path / "conf", {"name": "Inna"}, name="b.toml")
    found = loaded(tmp_path, monkeypatch, listed("a.toml", "b.toml"))
    assert found.paths == (first, second)
    assert [item.path for item in found.files] == [first]
    (problem,) = found.problems
    assert problem.details["option"] == "provider_file.id"
    assert problem.details["path"] == str(second)


def test_reserved_ids_are_refused_by_the_list(tmp_path, monkeypatch):
    provider_file(tmp_path / "conf", {"id": "IMGW"})
    found = loaded(tmp_path, monkeypatch, listed("siec.toml"))
    assert found.files == ()
    assert [problem.details["option"] for problem in found.problems] == [
        "provider_file.id"
    ]


def test_a_bad_file_leaves_the_good_ones(tmp_path, monkeypatch):
    conf = tmp_path / "conf"
    good = provider_file(conf, {"id": "AA"}, name="a.toml")
    bad = provider_file(conf, {"id": "BB", "name": DROP}, name="b.toml")
    other = provider_file(conf, {"id": "CC"}, name="c.toml")
    found = loaded(
        tmp_path, monkeypatch, listed("a.toml", "b.toml", "missing.toml", "c.toml")
    )
    assert found.paths == (good, bad, conf / "missing.toml", other)
    assert [item.id for item in found.files] == ["AA", "CC"]
    assert [
        (problem.details["option"], problem.details["path"])
        for problem in found.problems
    ] == [
        ("provider_file.name", str(bad)),
        ("provider_file", str(conf / "missing.toml")),
    ]


def test_a_failed_file_does_not_take_its_id(tmp_path, monkeypatch):
    conf = tmp_path / "conf"
    provider_file(conf, {"country": "DE"}, name="a.toml")
    second = provider_file(conf, name="b.toml")
    found = loaded(tmp_path, monkeypatch, listed("a.toml", "b.toml"))
    assert [item.path for item in found.files] == [second]
    assert [problem.details["option"] for problem in found.problems] == [
        "provider_file.country"
    ]


def test_fixture_nogat_toml_gives_its_provider(monkeypatch):
    monkeypatch.setenv("NOGAT_CONFIG", str(FIXTURE / "nogat.toml"))
    found = load_provider_files(config_file(), reserved=RESERVED, variables=VARIABLES)
    assert found.paths == (FIXTURE / "siec.toml",)
    assert [item.id for item in found.files] == ["SIEC"]
    assert found.problems == ()
