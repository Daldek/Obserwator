"""The attribution lines and the terms lines of provider data (ADR-012, Nogat DEV §20).

The texts are a legal contract: the IMGW-PIB terms, the PMAXTP terms and CC BY 4.0
of ČHMÚ prescribe them, so one test pins them byte for byte against the table of
Nogat DEV §20; every other test takes them from `obserwator.attribution`. One test
per surface family proves that a product with provider data carries them: CSV,
JSONL, Parquet, the JSON documents of the store, the envelope, REST, MCP, the
``ATTRIBUTION.txt`` of a plain write and the human CLI output. Offline: the
fixture store and recorded answers only.
"""

import csv
import io
import json
import shutil
from pathlib import Path

import pyarrow.parquet as pq
import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from obserwator import current_version, run_command
from obserwator.api.main import app
from obserwator.attribution import ORIGINS, Attribution, attribution, carried
from obserwator.cli.main import app as cli_app
from obserwator.config import settings
from obserwator.datasets import archive_files
from obserwator.messages import message
from obserwator.store import (
    export_archive,
    export_series,
    init_store,
    read_series,
    sync_pmaxtp,
)
from tests.contract.support import (
    ANYWHERE,
    DAILY,
    RABA,
    FakeImgw,
    load,
    trailing_lines,
)

CHMI_HYDRO = "cz.chmi.hydro_daily"
CHMI_STATION = "0-203-1-900001"
SEMIANNUAL = "pl.imgw.hydro_semiannual"
ARCHIVES = Path(__file__).parents[1] / "fixtures" / "store" / "archives"
POINT = {"latitude": 52.23, "longitude": 21.01}
IMGW = attribution("imgw")
CHMI = attribution("chmi")


def series_of(root: Path, dataset: str) -> Path:
    """The ``series.json`` of the current series version of a dataset."""
    entry = current_version(root, slot=f"series:{dataset}")
    assert entry is not None and entry.version is not None, dataset
    return Path(entry.version)


def table_of(lines) -> list[dict[str, str]]:
    """The rows of exported CSV lines (a cell may hold line feeds)."""
    return list(csv.DictReader(io.StringIO("".join(lines), newline="")))


# --------------------------------------------------------------------------
# The lines and their composition
# --------------------------------------------------------------------------


def test_the_ten_lines_are_the_table_of_nogat_dev_20_byte_for_byte():
    imgw = "Instytut Meteorologii i Gospodarki Wodnej – Państwowy Instytut Badawczy"
    imgw_of = (
        "Dane Instytutu Meteorologii i Gospodarki Wodnej – Państwowego Instytutu "
        "Badawczego"
    )
    pmaxtp = "https://klimat.imgw.pl/opady-maksymalne"
    table = {
        "S": f"Źródłem pochodzenia danych jest {imgw}",
        "P": f"{imgw_of} zostały przetworzone",
        "PS": f"Źródłem pochodzenia danych jest {imgw}, dane pochodzą ze strony {pmaxtp}",
        "PP": f"{imgw_of} pochodzące ze strony {pmaxtp} zostały przetworzone",
        "M": (
            "„Modele probabilistyczne opadów maksymalnych o określonym czasie trwania "
            "i prawdopodobieństwie przewyższenia – Projekt PMAXTP”, red. Bogdan "
            f"Ozga-Zieliński, {imgw}, Warszawa 2022"
        ),
        "C": (
            "Źródło danych: Český hydrometeorologický ústav (ČHMÚ), "
            "https://opendata.chmi.cz, licencja CC BY 4.0 "
            "(https://creativecommons.org/licenses/by/4.0/)"
        ),
        "CP": "Dane ČHMÚ zostały przetworzone (normalizacja i zmiana formatu)",
        "RD": "Regulamin danych IMGW-PIB: https://danepubliczne.imgw.pl/regulations",
        "RH": (
            "Regulamin serwisu hydrologicznego IMGW-PIB: https://hydro.imgw.pl/#/regulamin"
        ),
        "RK": f"Regulamin danych PMAXTP: {pmaxtp}",
    }

    every = attribution(*ORIGINS)

    marks = ("S", "P", "PS", "PP", "M", "C", "CP")
    assert every.attribution == tuple(table[mark] for mark in marks)
    assert every.terms_notice == tuple(table[mark] for mark in ("RD", "RH", "RK"))


def test_a_verbatim_copy_carries_the_source_lines_and_processed_data_add_theirs():
    s, p, ps, pp, m, c, cp = attribution(*ORIGINS).attribution
    rd, rh, rk = attribution(*ORIGINS).terms_notice

    assert [
        (attribution(origin, processed=False), attribution(origin))
        for origin in ORIGINS
    ] == [
        (Attribution((s,), (rd,)), Attribution((s, p), (rd,))),
        (Attribution((s,), (rh,)), Attribution((s, p), (rh,))),
        (Attribution((ps, m), (rk,)), Attribution((ps, pp, m), (rk,))),
        (Attribution((c,)), Attribution((c, cp))),
    ]
    assert attribution() == Attribution() and not attribution()


def test_lines_merge_once_in_the_order_of_the_standard_and_round_trip():
    every = attribution(*ORIGINS)
    reversed_merge = (
        attribution("chmi")
        | attribution("pmaxtp")
        | attribution("imgw_hydro")
        | attribution("imgw")
    )

    assert reversed_merge == every
    assert every | every == every
    # A line of another tool follows the known ones, each once.
    foreign = Attribution(("Dane przetworzone w programie X",))
    assert (foreign | IMGW).attribution == (*IMGW.attribution, *foreign.attribution)
    # JSON fields: no empty terms_notice (ČHMÚ data), nothing without lines.
    assert CHMI.fields() == {"attribution": list(CHMI.attribution)}
    assert IMGW.fields() == {
        "attribution": list(IMGW.attribution),
        "terms_notice": list(IMGW.terms_notice),
    }
    assert Attribution().fields() == {}
    # The lines of a file read back, empty lines skipped.
    for lines in (every, IMGW, CHMI, foreign | IMGW, Attribution()):
        assert Attribution.from_lines([*lines.lines, ""]) == lines
        assert Attribution.from_lines(reversed(lines.lines)) == lines
    # Another tool's terms line, of the form of DEV §20, is read back as one
    theirs = "Regulamin danych X: https://example.org/terms"
    assert Attribution.from_lines([*IMGW.lines, theirs]).terms_notice == (
        *IMGW.terms_notice,
        theirs,
    )


# The lines of IMGW-PIB data of hydro.imgw.pl as products stored before ECO-065 hold
# them: H, N and the terms lines that did not name their terms
H = "Dane pochodzą z serwisu hydrologicznego IMGW-PIB https://hydro.imgw.pl"
N = (
    "Dane IMGW-PIB można wykorzystywać nieodpłatnie do celów prywatnych "
    "(niezarobkowych). Wykorzystanie w działalności gospodarczej, na stronach "
    "z reklamami lub do celów wymienionych w regulaminie (m.in. planowanie w "
    "gospodarowaniu wodami, art. 317 Prawa wodnego) wymaga umowy z IMGW-PIB."
)
OLD = Attribution(
    (*IMGW.attribution, H),
    (
        N,
        "Regulamin: https://danepubliczne.imgw.pl/regulations",
        "Regulamin: https://hydro.imgw.pl/#/regulamin",
    ),
)


def test_a_stored_product_carries_the_derived_lines_and_its_producers_own_only():
    hydrolog = "Dane ČHMÚ zostały przetworzone (obliczenia w programie Hydrolog)"
    stored = Attribution((*OLD.attribution, hydrolog), OLD.terms_notice)

    assert carried(OLD, "imgw", "imgw_hydro") == attribution("imgw", "imgw_hydro")
    assert carried(stored, "chmi") == attribution("chmi") | Attribution((hydrolog,))
    # An ATTRIBUTION.txt written before ECO-065 is read back without its retired lines
    assert Attribution.from_lines(OLD.lines) == Attribution(IMGW.attribution)


# --------------------------------------------------------------------------
# Surfaces
# --------------------------------------------------------------------------


def test_csv_of_series_export_has_one_line_per_cell_and_joins_the_rest_into_one_row(
    fixture_root,
):
    imgw_rows = table_of(export_series(root=fixture_root, dataset=DAILY, station=RABA))
    chmi_rows = table_of(
        export_series(root=fixture_root, dataset=CHMI_HYDRO, station=CHMI_STATION)
    )
    day = next(iter(read_series(root=fixture_root, dataset=DAILY, station=RABA))).date
    (single,) = table_of(
        export_series(
            root=fixture_root, dataset=DAILY, station=RABA, start=day, end=day
        )
    )

    assert len(imgw_rows) > 2 and trailing_lines(imgw_rows) == IMGW
    assert [(row["attribution"], row["terms_notice"]) for row in imgw_rows[:3]] == [
        (IMGW.attribution[0], IMGW.terms_notice[0]),
        (IMGW.attribution[1], ""),
        ("", ""),
    ]
    # CC BY 4.0 data: C and CP, no IMGW-PIB terms lines.
    assert trailing_lines(chmi_rows) == CHMI
    assert not any(row["terms_notice"] for row in chmi_rows)
    # A table of one row holds every line of a column in its one cell.
    assert (single["attribution"], single["terms_notice"]) == (
        "\n".join(IMGW.attribution),
        "\n".join(IMGW.terms_notice),
    )


def test_store_export_carries_the_lines_in_csv_columns_and_the_first_jsonl_object(
    fixture_raw_root,
):
    (archive,) = archive_files(DAILY, years=2024)
    version = current_version(
        fixture_raw_root,
        slot=f"archive:{DAILY}:{archive.server_path.split('/', 2)[-1]}",
    ).version

    rows = table_of(export_archive(version))
    objects = [json.loads(line) for line in export_archive(version, format="jsonl")]

    assert list(rows[0])[-2:] == ["attribution", "terms_notice"]
    assert trailing_lines(rows) == IMGW
    first, *others = objects
    assert {key: first[key] for key in IMGW.fields()} == IMGW.fields()
    assert not any("attribution" in item or "terms_notice" in item for item in others)


def test_parquet_files_of_a_series_hold_the_lines_as_json_arrays(fixture_root):
    for dataset, station, lines in (
        (DAILY, RABA, IMGW),
        (CHMI_HYDRO, CHMI_STATION, CHMI),
    ):
        version = series_of(fixture_root, dataset).parent
        metadata = pq.read_schema(version / "stations" / f"{station}.parquet").metadata

        assert json.loads(metadata[b"attribution"]) == list(lines.attribution)
        # Without IMGW-PIB data there is no terms notice, as in JSON.
        terms = metadata.get(b"terms_notice")
        assert (terms and json.loads(terms)) == (list(lines.terms_notice) or None)


def test_json_documents_of_the_store_carry_the_lines_at_the_top(
    fixture_root, tmp_path, respx_mock
):
    FakeImgw(respx_mock).publish_pmaxtp("pmaxtp_pot_first")
    cell = sync_pmaxtp(init_store(tmp_path / "store"), **POINT).version
    catalogs = fixture_root / "stations" / "versions"

    documents = {
        "series.json IMGW-PIB": (load(series_of(fixture_root, DAILY)), IMGW),
        "series.json ČHMÚ": (load(series_of(fixture_root, CHMI_HYDRO)), CHMI),
        # Built without the static locations: no hydro.imgw.pl lines.
        "stations.geojson IMGW-PIB": (
            load(next(catalogs.glob("*_*/stations.geojson"))),
            IMGW,
        ),
        "stations.geojson ČHMÚ": (
            load(next(catalogs.glob("chmi_stations/*/stations.geojson"))),
            CHMI,
        ),
        "cell.json": (load(cell), attribution("pmaxtp")),
    }

    for name, (document, lines) in documents.items():
        assert {key: document.get(key) for key in ("attribution", "terms_notice")} == {
            "attribution": list(lines.attribution),
            "terms_notice": list(lines.terms_notice) or None,
        }, name


def test_the_envelope_has_the_lines_of_data_commands_only(fixture_root):
    read = run_command(
        "series read",
        options={"root": fixture_root, "dataset": DAILY, "station": RABA, "limit": 1},
    )
    listed = run_command("datasets list", options={})

    assert (read.attribution, read.terms_notice) == (
        IMGW.attribution,
        IMGW.terms_notice,
    )
    document = read.to_json()
    keys = list(document)
    assert keys[keys.index("result") + 1 : keys.index("notices")] == [
        "attribution",
        "terms_notice",
    ]
    assert {key: document[key] for key in IMGW.fields()} == IMGW.fields()
    # The registry is no provider data: no lines, no empty fields.
    assert (listed.attribution, listed.terms_notice) == ((), ())
    assert not {"attribution", "terms_notice"} & set(listed.to_json())


def test_rest_answers_carry_the_lines_in_the_body_and_the_stream_headers(
    fixture_root, monkeypatch
):
    monkeypatch.setattr(settings, "root", fixture_root)
    client = TestClient(app)
    query = {"dataset": DAILY, "station": RABA}

    body = client.get("/api/v1/series/read", params={**query, "limit": "1"}).json()
    stream = client.get("/api/v1/series/export", params=query)

    assert {key: body.get(key) for key in IMGW.fields()} == IMGW.fields()
    assert stream.status_code == 200, stream.text
    for header, lines in (
        ("x-obserwator-attribution", IMGW.attribution),
        ("x-obserwator-terms-notice", IMGW.terms_notice),
    ):
        assert stream.headers[header].isascii()  # HTTP headers are Latin-1
        assert json.loads(stream.headers[header]) == list(lines)


async def test_an_mcp_tool_result_has_the_lines_in_its_structured_content(
    fixture_root, tmp_path, monkeypatch
):
    pytest.importorskip("mcp")
    from mcp import Client

    from obserwator.mcp.server import create_server

    monkeypatch.delenv("OBSERWATOR_ROOT", raising=False)
    root = tmp_path / "store"
    shutil.copytree(fixture_root, root)
    arguments = {"root": str(root), "dataset": DAILY, "station": RABA, "limit": 1}

    async with Client(create_server(mode="read", allow_dirs=ANYWHERE)) as client:
        result = await client.call_tool("obserwator_series_read", arguments)

    assert result.is_error is False
    document = result.structured_content
    assert {key: document[key] for key in IMGW.fields()} == IMGW.fields()


def test_a_plain_write_merges_its_lines_into_the_attribution_file(respx_mock, tmp_path):
    # Every file of the half-year archives answers with the fixture archive.
    files = archive_files(SEMIANNUAL, years=2024)
    body = (ARCHIVES / files[0].server_path).read_bytes()
    for archive in files:
        respx_mock.get(archive.url).respond(content=body)
    FakeImgw(respx_mock).publish_pmaxtp("pmaxtp_pot_first")
    out = tmp_path / "out"
    target = out / "ATTRIBUTION.txt"
    verbatim = attribution("imgw", processed=False)

    downloaded = run_command(
        "datasets download",
        options={"dataset": SEMIANNUAL, "years": 2024, "output_dir": out},
    )
    first = target.read_bytes()
    cell = sync_pmaxtp(output_dir=out, **POINT)

    # A verbatim copy of archives: S, then N and RD; UTF-8, LF after each line.
    assert (downloaded.attribution, downloaded.terms_notice) == (
        verbatim.attribution,
        verbatim.terms_notice,
    )
    assert downloaded.result.files[-1].path == target
    assert first == "".join(f"{line}\n" for line in verbatim.lines).encode("utf-8")
    # A later write into the same directory merges its lines in, no conflict.
    merged = verbatim | attribution("pmaxtp")
    assert target.read_text(encoding="utf-8") == "".join(
        f"{line}\n" for line in merged.lines
    )
    assert (cell.files[-1].path, cell.files[-1].status) == (target, "replaced")


def test_the_human_cli_output_prints_the_lines_after_the_result(fixture_root):
    printed = CliRunner().invoke(
        cli_app,
        [
            *("series", "read", "--root", str(fixture_root)),
            *("--dataset", DAILY, "--station", RABA, "--limit", "1"),
            *("--lang", "en"),
        ],
    )

    assert printed.exit_code == 0, printed.output
    lines = printed.stdout.splitlines()
    start = lines.index(str(message("cli.human_attribution", lang="en"))) + 1
    assert [line.strip() for line in lines[start : start + len(IMGW.lines)]] == list(
        IMGW.lines
    )
    assert all(line != line.lstrip() for line in lines[start : start + len(IMGW.lines)])
