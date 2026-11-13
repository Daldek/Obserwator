"""Contract between interfaces: Python, ``obserwator`` and REST answer every command alike.

Spec §13 (ADR-002), plan U14. Every catalog command with a REST route runs on the
fixture roots against recorded IMGW answers through ``run_command``, the ``obserwator``
CLI and the REST API. A command works on the root of its kind (ADR-017 D4): the raw
root (``OBSERWATOR_RAW_ROOT``) or the data root (``OBSERWATOR_ROOT``); ``series build``
and ``store catalog`` also read the raw root as ``raw_root``. The CLI prints
``CommandResult.to_json(root)`` and REST answers ``to_json(root, server=True)`` (the
root as ``"."``), so the three documents are equal after a canonical JSON dump;
writes leave identical trees after identical requests. Every registered error code
is reported with the code, exit code and HTTP status of §13.5, a root of the other
kind too; every envelope and error document satisfies the §13.5–§13.6 schemas of
``contract_schemas.json``; the same ``limit``/``cursor`` gives the same page
everywhere; slots and versions taken from answers work in ``current_version`` and as
``obserwator --version`` with ``--root``. No request leaves the recordings.
"""

import functools
import importlib
import json
import os
import shutil
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import pytest

from obserwator import (
    ERROR_CODES,
    ErrorCode,
    ObserwatorCancelledError,
    ObserwatorError,
    check_command,
    current_version,
    init_store,
    run_command,
    store,
    sync_store,
)
from obserwator.api.errors import hide_server_paths
from obserwator.datasets import get_dataset
from obserwator.exceptions import describe_os_error
from obserwator.messages import localize
from obserwator.store.types import page_cursor
from tests.contract.support import (
    BEZ_Q,
    DAILY,
    H2024,
    NEW,
    PRECIP,
    RABA,
    V3,
    FakeImgw,
    canonical,
    cli_words,
    command_document,
    current_analyses,
    current_path,
    envelope_errors,
    in_json,
    input_schemas,
    load,
    rest_request,
    schema_errors,
    slots,
    snapshot,
    stamps,
)

EXIT_CODES = command_document()["exit_codes"]
ROUTES = {
    schema["x-obserwator"]["command"]: schema["x-obserwator"]
    for schema in input_schemas()
    if schema["x-obserwator"]["rest"] is not None
}
POST_COMMANDS = [
    name for name, meta in ROUTES.items() if meta["rest"]["method"] == "POST"
]
INTERFACES = ("python", "cli", "rest")
# Notice labels of the CLI stderr (spec §13.10); its lines are for a person, so they
# are in the language of OBSERWATOR_LANG, Polish by default.
LABELS = {"info": "Informacja", "warning": "Ostrzeżenie"}


def line_of(notice):
    """The stderr line the CLI prints for a notice."""
    return f"{LABELS[notice.level]}: {localize(notice.message, 'pl')}"


# The commands on the raw root (ADR-017 D4); every other command with a root works
# on the data root.
RAW_COMMANDS = frozenset(
    {
        "datasets download",
        "pmaxtp check",
        "pmaxtp sync",
        "pmaxtp read",
        "store check",
        "store sync",
        "store export",
    }
)
# The builds of the data root that read the raw root (option ``raw_root``).
BUILDS = frozenset(
    schema["x-obserwator"]["command"]
    for schema in input_schemas()
    if "raw_root" in schema["properties"]
)
# Kind words of the slots in the raw root (ADR-017 D2); the others are in the data root.
RAW_SLOTS = ("archive", "pmaxtp")


@dataclass(frozen=True)
class Roots:
    """The data root and the raw root a case works on (ADR-017 D1)."""

    data: Path
    raw: Path

    def root(self, command: str) -> Path:
        """The root ``command`` works on: the raw root or the data root."""
        return self.raw if command in RAW_COMMANDS else self.data

    def raw_root(self, command: str) -> Path | None:
        """``raw_root`` of a build that reads the raw root, else None."""
        return self.raw if command in BUILDS else None

    def of_slot(self, slot: str) -> Path:
        """The root holding the versions of ``slot``."""
        return self.raw if slot.partition(":")[0] in RAW_SLOTS else self.data


# Placeholders of versions relative to the command's root, resolved in the served roots.
ARCHIVE, SERIES, ANALYSES = "<archive>", "<series>", "<analyses>"
PLACEHOLDERS = {
    ARCHIVE: f"archive:{PRECIP}:2001/2001_01_o.zip",
    SERIES: f"series:{DAILY}",
}


@dataclass(frozen=True)
class Case:
    """
    Options of one run of a command (JSON form, without ``root`` and ``raw_root``).

    ``store``: ``None`` = no root; ``"served"`` = the shared read-only roots;
    ``"empty"``, ``"sources"`` and ``"fixture"`` = fresh roots for each
    interface (writes).
    """

    options: dict[str, object]
    store: str | None = None


# Kinds of ``Case.store`` that are fresh roots written by the command.
WRITTEN = ("empty", "sources", "fixture")

CASES: dict[str, list[Case]] = {
    "datasets list": [Case({"kind": "hydro", "limit": 2, "cursor": page_cursor(1)})],
    "datasets files": [
        Case(
            {
                "dataset": "hydro/dobowe",
                "years": "2021-2023",
                "months": [1, 2],
                "limit": 3,
                "cursor": page_cursor(1),
            }
        )
    ],
    "datasets providers": [Case({"limit": 1, "cursor": page_cursor(1)})],
    "stations find": [
        Case({"kind": "hydro", "query": "raba", "provider": "IMGW-PIB", "limit": 2}),
        Case({"source": "store", "query": "1491", "cursor": page_cursor(1)}, "served"),
    ],
    "current hydro": [Case({"station": RABA})],
    "current meteo": [Case({"limit": 1, "cursor": page_cursor(1)})],
    "current synop": [Case({"station_name": "raba"})],
    "current warnings": [Case({"limit": 5})],
    "current hydro-states": [
        Case({"main_only": True}),
        Case({"cursor": page_cursor(1)}),
    ],
    "pmaxtp fetch": [Case({"latitude": "52.23", "longitude": 21.01})],
    "pmaxtp url": [Case({"latitude": 52.23, "longitude": 21.01, "method": "AMP"})],
    "pmaxtp check": [Case({"latitude": 52.23, "longitude": 21.01}, "served")],
    "pmaxtp sync": [
        Case({"latitude": 52.23, "longitude": 21.01, "method": "POT"}, "empty")
    ],
    "pmaxtp read": [Case({"ind_x": 751, "ind_y": 317}, "served")],
    "store info": [Case({}, "served")],
    "store scan": [
        Case({"kind": "series", "limit": 2, "cursor": page_cursor(2)}, "served")
    ],
    "store check": [Case({"datasets": [DAILY], "years": "2024"}, "served")],
    "store sync": [Case({"datasets": ["hydro/dobowe"], "years": [2024]}, "empty")],
    "store catalog": [Case({}, "sources")],
    "store export": [
        Case({"version": ARCHIVE}, "served"),
        Case({"version": ARCHIVE, "format": "jsonl"}, "served"),
    ],
    "series build": [Case({"dataset": PRECIP}, "fixture")],
    "series select": [
        Case({"dataset": "hydro/dobowe", "stations": [RABA], "years": "2024"}, "served")
    ],
    "series read": [
        Case(
            {
                "dataset": DAILY,
                "station": RABA,
                "variables": ["H", "Q"],
                "start": "2024-01-01",
                "limit": 5,
                "cursor": page_cursor(1),
            },
            "served",
        )
    ],
    "series summary": [Case({"version": SERIES, "stations": [RABA]}, "served")],
    "series export": [
        Case(
            {
                "dataset": DAILY,
                "station": RABA,
                "variables": "H,Q",
                "end": "2024-03-31",
            },
            "served",
        ),
        Case({"dataset": DAILY, "station": RABA, "format": "json"}, "served"),
    ],
    "stations export": [
        Case({"format": "csv", "kind": "hydro"}, "served"),
        Case({"series": False}, "served"),
    ],
    "analyses build": [Case({"stations": [RABA, BEZ_Q], "workers": 2}, "fixture")],
    "analyses list": [
        Case({"station": RABA}, "served"),
        Case(
            {
                "version": ANALYSES,
                "station": BEZ_Q,
                "limit": 5,
                "cursor": page_cursor(1),
            },
            "served",
        ),
    ],
    "analyses read": [
        Case({"station": RABA, "analysis": "characteristic.Q"}, "served"),
        # Hydrolog's error document of a failed analysis (calculation_error).
        Case(
            {"version": ANALYSES, "station": RABA, "analysis": "homogeneity.Q"},
            "served",
        ),
    ],
    "analyses export": [
        Case({"station": RABA}, "served"),
        Case(
            {
                "station": BEZ_Q,
                "analyses": ["daily.H", "characteristic.H"],
                "format": "csv",
            },
            "served",
        ),
    ],
    "commands list": [Case({}), Case({"lang": "en"})],
    "commands schema": [
        Case({"command": "series export"}),
        Case({}),
        Case({"command": "store sync", "lang": "en"}),
    ],
    "commands guide": [Case({}), Case({"format": "llms", "lang": "en"})],
}


@pytest.fixture
def recorded(imgw):
    """Recorded IMGW for every command: archives, station lists, live API, PMAXTP."""
    imgw.publish(H2024, V3, NEW)
    imgw.publish_catalog_sources()
    imgw.publish_live()
    imgw.publish_pmaxtp("pmaxtp_pot_first", "pmaxtp_amp")
    return imgw


@pytest.fixture
def relative_reference_dir(monkeypatch, server):
    """Relative reference-data directory: texts name it alike in every interface."""
    monkeypatch.setattr(server, "reference_dir", Path("brak-danych-referencyjnych"))


def rooted(
    options: dict[str, object], root: Path | None, raw_root: Path | None = None
) -> dict[str, object]:
    """``options`` with ``root`` and, for a build, ``raw_root`` (none: as given)."""
    result = dict(options) if root is None else {"root": root, **options}
    if raw_root is not None:
        result["raw_root"] = raw_root
    return result


def placed(
    command: str, options: dict[str, object], roots: Roots | None
) -> dict[str, object]:
    """``options`` with the root of the command's kind and its ``raw_root``."""
    if roots is None:
        return dict(options)
    return rooted(options, roots.root(command), roots.raw_root(command))


def serve(server, monkeypatch, roots: Roots | None) -> None:
    """The server's ``OBSERWATOR_ROOT`` and ``OBSERWATOR_RAW_ROOT``: ``roots`` or none."""
    monkeypatch.setattr(server, "root", None if roots is None else roots.data)
    monkeypatch.setattr(server, "raw_root", None if roots is None else roots.raw)


def stamps_of(roots: Roots) -> tuple[dict[str, int], dict[str, int]]:
    """`stamps` of both roots, to prove that neither was touched."""
    return stamps(roots.data), stamps(roots.raw)


def resolved(options: dict[str, object], root: Path | None) -> dict[str, object]:
    """Options with version placeholders replaced by versions relative to ``root``."""
    result = dict(options)
    for name, value in options.items():
        if isinstance(value, str) and value in (*PLACEHOLDERS, ANALYSES):
            assert root is not None
            version = (
                current_analyses(root)
                if value == ANALYSES
                else current_path(root, PLACEHOLDERS[value])
            )
            result[name] = version.relative_to(root).as_posix()
    return result


# IMGW-PIB station sources the offline catalog reads from the store (ADR-015).
IMGW_SOURCES = [
    "pl.imgw.hydro_stations",
    "pl.imgw.meteo_stations",
    "pl.imgw.hydro_now",
    "pl.imgw.meteo_now",
]


def written(tmp_path: Path) -> Roots:
    """The place of the fresh roots of a writing case."""
    return Roots(tmp_path / "roots" / "data", tmp_path / "roots" / "raw")


def fresh_roots(kind: str, roots: Roots, fixture: Roots) -> None:
    """
    New roots at ``roots``: copies of the fixture roots, or an empty data root
    beside an empty raw root, or beside one with the IMGW-PIB station sources
    synced from the recorded answers.
    """
    for path in (roots.data, roots.raw):
        if path.exists():
            shutil.rmtree(path)
    if kind == "fixture":
        shutil.copytree(fixture.data, roots.data)
        shutil.copytree(fixture.raw, roots.raw)
        return
    init_store(roots.data, kind="data")
    init_store(roots.raw)
    if kind == "sources":
        sync_store(roots.raw, datasets=IMGW_SOURCES)


def trees(roots: Roots) -> tuple[dict[str, str | None], dict[str, str | None]]:
    """`snapshot` of both roots."""
    return snapshot(roots.data), snapshot(roots.raw)


def answer(
    interface,
    command,
    options,
    root,
    *,
    raw_root=None,
    cli,
    rest,
    headers=None,
    check=False,
):
    """
    The answer of one interface: an envelope, a Click result or an HTTP response.

    Python and the CLI get ``root`` (and ``raw_root``); REST takes them from the
    server's settings.
    """
    if interface == "python":
        dispatch = check_command if check else run_command
        return dispatch(command, options=rooted(options, root, raw_root))
    if interface == "cli":
        flags = ["--check"] if check else []
        return cli(*cli_words(command, rooted(options, root, raw_root)), *flags)
    request = rest_request(command, options)
    if check:
        request["url"] += "?check=true"
    return rest.request(**request, headers=headers)


def compact(document: object) -> str:
    """The one-line JSON the CLI prints and REST sends (spec §13.10)."""
    return json.dumps(document, ensure_ascii=False, separators=(",", ":"))


def assert_alike(command, python, printed, answered, root, *, raw_root=None):
    """Python envelope = CLI stdout = REST body (canonical JSON; streams: bytes)."""
    if ROUTES[command]["result"] == "stream" and not python.check:
        data = "".join(python.result).encode("utf-8")
        assert printed.exit_code == 0, printed.output
        assert printed.stdout_bytes == data
        assert answered.status_code == 200, answered.text
        assert answered.content == data
        assert answered.headers["x-obserwator-status"] == python.status == "ok"
        notices = [
            {"level": n.level, "code": n.code, "message": n.message}
            for n in python.notices
        ]
        assert json.loads(answered.headers["x-obserwator-notices"]) == notices
        # Data exports name the license of their provider; the guide is no data.
        exported = ROUTES[command]["function"].startswith("export_")
        assert ("license_terms" in {notice["code"] for notice in notices}) == exported
        for notice in python.notices:
            assert printed.stderr.count(line_of(notice)) == 1
        return
    local = python.to_json(root=root)
    # REST hides every server directory (T21): the root, and the temporary directory
    # of the series files whose paths Hydrolog's stored envelopes echo.
    served = hide_server_paths(python.to_json(root=root, server=True))
    assert envelope_errors(local) == []
    assert envelope_errors(served) == []
    assert printed.exit_code == EXIT_CODES[python.status], printed.output
    assert printed.stdout == compact(json.loads(printed.stdout)) + "\n"
    assert canonical(json.loads(printed.stdout)) == canonical(local)
    assert answered.status_code == 200, answered.text
    assert answered.headers["content-type"] == "application/json"
    assert canonical(answered.json()) == canonical(served)
    if root is None:  # no root to write as "." in REST: the very same bytes
        assert printed.stdout_bytes == answered.content + b"\n"
    else:  # REST never shows the server's roots (spec §13.1 p. 4)
        assert in_json(str(root)) not in answered.text
        if raw_root is not None:
            assert in_json(str(raw_root)) not in answered.text


# --------------------------------------------------------------------------
# Every command with a REST route: Python = CLI = REST
# --------------------------------------------------------------------------


@pytest.mark.parametrize("command", list(ROUTES))
def test_every_rest_command_answers_alike_in_python_cli_and_rest(
    command,
    cli,
    rest,
    writable,
    server,
    monkeypatch,
    tmp_path,
    fixture_root,
    fixture_raw_root,
    served_root,
    served_raw_root,
    recorded,
    frozen,
    relative_reference_dir,
):
    served = Roots(served_root, served_raw_root)
    fixture = Roots(fixture_root, fixture_raw_root)
    for case in CASES[command]:
        writes = case.store in WRITTEN
        if writes:
            roots = written(tmp_path)
        else:
            roots = served if case.store == "served" else None
        serve(server, monkeypatch, roots)
        root = None if roots is None else roots.root(command)
        raw_root = None if roots is None else roots.raw_root(command)
        options = case.options if writes else resolved(case.options, root)
        local = options
        if ROUTES[command]["result"] == "list" and "limit" not in options:
            # REST pages by OBSERWATOR_API_MAX_LIMIT when no limit is given (spec §13.6).
            local = {"limit": server.api_max_limit, **options}
        given = {"python": local, "cli": local, "rest": options}
        before = stamps_of(served)
        answers, requests, written_trees = {}, {}, {}
        for interface in INTERFACES:
            if writes:
                fresh_roots(case.store, roots, fixture)
            start = len(recorded.router.calls)
            answers[interface] = answer(
                interface,
                command,
                given[interface],
                root,
                raw_root=raw_root,
                cli=cli,
                rest=rest,
                headers=writable,
            )
            requests[interface] = recorded.traffic(start)
            if writes:
                written_trees[interface] = trees(roots)

        python, printed, answered = (answers[i] for i in INTERFACES)
        assert_alike(command, python, printed, answered, root, raw_root=raw_root)
        assert requests["python"] == requests["cli"] == requests["rest"]
        if writes:
            assert (
                written_trees["python"] == written_trees["cli"] == written_trees["rest"]
            )
        assert stamps_of(served) == before
        if roots is not None and ROUTES[command]["result"] != "stream":
            # Every slot of an answer names a version current_version finds in the
            # root of its kind (§13.7, ADR-017 D2).
            for slot in slots(python.to_json(root=root)):
                assert current_version(roots.of_slot(slot), slot=slot).slot == slot


@pytest.mark.parametrize("command", POST_COMMANDS)
def test_every_write_is_planned_alike_by_check_in_python_cli_and_rest(
    command,
    cli,
    rest,
    server,
    monkeypatch,
    tmp_path,
    fixture_root,
    fixture_raw_root,
    recorded,
    frozen,
    relative_reference_dir,
):
    (case,) = CASES[command]
    roots = written(tmp_path)
    fresh_roots(case.store, roots, Roots(fixture_root, fixture_raw_root))
    start = len(recorded.router.calls)  # after the sync of a "sources" raw root
    serve(server, monkeypatch, roots)  # writes stay disabled
    root, raw_root = roots.root(command), roots.raw_root(command)
    before = stamps_of(roots)

    python, printed, answered = (
        answer(
            i,
            command,
            case.options,
            root,
            raw_root=raw_root,
            cli=cli,
            rest=rest,
            check=True,
        )
        for i in INTERFACES
    )

    assert python.check is True
    assert_alike(command, python, printed, answered, root, raw_root=raw_root)
    assert answered.json()["result"]["root"] == "."
    assert stamps_of(roots) == before
    assert recorded.downloads(start) == []


# --------------------------------------------------------------------------
# Paging: the same limit and cursor give the same page (spec §13.6)
# --------------------------------------------------------------------------


PAGED = [
    ("datasets list", {}, False),
    ("current hydro", {}, False),
    ("store scan", {}, True),
    ("series summary", {"dataset": DAILY}, True),
]


def window(limit: int, start: int) -> dict[str, object]:
    """Paging options of the page at item index ``start`` (no cursor for the first)."""
    return {"limit": limit, **({"cursor": page_cursor(start)} if start else {})}


@pytest.mark.parametrize(("command", "options", "stored"), PAGED)
@pytest.mark.parametrize(
    ("limit", "start"), [(4, 0), (4, 4), (3, 9), (1, 3), (5, 20)], ids=str
)
def test_same_limit_and_cursor_give_the_same_page_in_every_interface(
    command,
    options,
    stored,
    limit,
    start,
    cli,
    rest,
    server,
    monkeypatch,
    served_root,
    recorded,
):
    root = served_root if stored else None
    monkeypatch.setattr(server, "root", root)
    paged = {**options, **window(limit, start)}
    whole = run_command(command, options=rooted(options, root))

    python, printed, answered = (
        answer(i, command, paged, root, cli=cli, rest=rest) for i in INTERFACES
    )

    documents = [python.to_json(root=root), json.loads(printed.stdout), answered.json()]
    assert [envelope_errors(document) for document in documents] == [[], [], []]
    assert len({canonical(d["result"]) for d in documents}) == 1
    assert len({canonical(d["page"]) for d in documents}) == 1
    (document, *_) = documents
    everything = whole.to_json(root=root)["result"]
    assert len(everything) > 3
    assert document["result"] == everything[start : start + limit]
    more = start + limit < len(everything)
    assert document["page"] == {
        "total": len(everything),
        "next_cursor": page_cursor(start + limit) if more else None,
        "truncated": more,
    }


@pytest.mark.parametrize(("command", "options", "stored"), PAGED)
def test_following_next_cursor_gives_every_item_once_in_order(
    command, options, stored, rest, server, monkeypatch, served_root, recorded
):
    root = served_root if stored else None
    monkeypatch.setattr(server, "root", root)
    everything = run_command(command, options=rooted(options, root)).to_json(
        root=root, server=True
    )["result"]

    collected, paged = [], {**options, "limit": 3}
    while True:
        document = answer("rest", command, paged, root, cli=None, rest=rest).json()
        collected += document["result"]
        if document["page"]["next_cursor"] is None:
            break
        paged = {**options, "limit": 3, "cursor": document["page"]["next_cursor"]}

    assert len(everything) > 3
    assert collected == everything
    assert document["page"] == {
        "total": len(everything),
        "next_cursor": None,
        "truncated": False,
    }


# --------------------------------------------------------------------------
# Scanned versions as obserwator --version with --root
# --------------------------------------------------------------------------

# Kind of a scanned version → command reading it and its other options.
READERS = {
    "archive": ("store export", {}),
    "pmaxtp": ("pmaxtp read", {"ind_x": 751, "ind_y": 317}),
    "series": ("series summary", {"limit": 50}),
    "analyses": ("analyses list", {}),
}


def _station_source(slot: str) -> bool:
    """Station sources are read by stations find and the catalog, not as records."""
    return get_dataset(slot.split(":")[1]).time_unit == "station_list"


def test_scanned_versions_work_as_obserwator_version_with_the_root_of_their_kind(
    cli, rest, server, monkeypatch, served_root, served_raw_root
):
    served = Roots(served_root, served_raw_root)
    serve(server, monkeypatch, served)
    read = []
    for kind, (command, extra) in READERS.items():
        root = served.root(command)
        if root == served.data:  # REST scans the server's data root (ADR-017 D7)
            scanned = rest.get("/api/v1/store/scan", params={"kind": kind}).json()
        else:  # the raw root is scanned by `store scan --root`
            scan = run_command("store scan", options={"root": root, "kind": kind})
            scanned = scan.to_json(root=root)
        for entry in scanned["result"]:
            if kind == "archive" and _station_source(entry["slot"]):
                continue
            options = {"version": entry["version"], **extra}
            if kind == "analyses":  # a station of the version's provider
                options["station"] = min(load(root / entry["version"])["stations"])

            python, printed, answered = (
                answer(i, command, options, root, cli=cli, rest=rest)
                for i in INTERFACES
            )

            assert not Path(entry["version"]).is_absolute()
            assert_alike(command, python, printed, answered, root)
            read.append(kind)
    # The record archives, the PMAXTP cell, the series and the analyses versions of
    # IMGW-PIB and ČHMÚ in the served roots.
    assert Counter(read) == {"archive": 17, "pmaxtp": 1, "series": 6, "analyses": 2}


# --------------------------------------------------------------------------
# Error codes (spec §13.5): the same code, exit code and HTTP status
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Scenario:
    """A command failing with one error code and the interfaces that report it."""

    command: str
    options: dict[str, object]
    roots: Roots | None = None
    interfaces: tuple[str, ...] = INTERFACES
    method: str | None = None  # HTTP method other than the route's

    @property
    def root(self) -> Path | None:
        """The root the command works on."""
        return None if self.roots is None else self.roots.root(self.command)

    def given(self) -> dict[str, object]:
        """The options with the roots, as Python, the CLI and MCP stdio take them."""
        return placed(self.command, self.options, self.roots)


@dataclass(frozen=True)
class Setting:
    """What a scenario may prepare: copies of the roots, recorded answers, patches."""

    tmp_path: Path
    fixture: Roots
    imgw: FakeImgw
    monkeypatch: pytest.MonkeyPatch

    def roots(self) -> Roots:
        roots = written(self.tmp_path)
        shutil.copytree(self.fixture.data, roots.data)
        shutil.copytree(self.fixture.raw, roots.raw)
        return roots

    def raising(self, module: object, name: str, error: BaseException) -> None:
        """Public function ``name`` (signature kept for the dispatcher) raises."""
        original = getattr(module, name)

        @functools.wraps(original)
        def fake(*args, **kwargs):
            raise error

        self.monkeypatch.setattr(module, name, fake)


def _validation_error(setting: Setting) -> Scenario:
    # One validator of the library writes the detail of every interface (§13.1).
    return Scenario("pmaxtp fetch", {"latitude": "1", "longitude": "21.01"})


def _not_found(setting: Setting) -> Scenario:
    return Scenario("pmaxtp read", {"ind_x": 1, "ind_y": 1}, setting.roots())


def _conflict(setting: Setting) -> Scenario:
    roots = setting.roots()
    (roots.data / "notatki").mkdir()
    (roots.data / "notatki" / "kartograf-store.json").write_text(
        json.dumps({"schema": "kartograf-store/1"}), encoding="utf-8"
    )  # a Kartograf store inside the data root
    return Scenario("series build", {"dataset": PRECIP}, roots)


def _source_unavailable(setting: Setting) -> Scenario:
    setting.imgw.answer("hydro_current_outage")
    return Scenario("current hydro", {})


def _missing_dependency(setting: Setting) -> Scenario:
    for name in ("pyarrow", "pyarrow.parquet"):
        setting.monkeypatch.setitem(sys.modules, name, None)
    options: dict[str, object] = {"dataset": DAILY, "station": RABA}
    return Scenario("series read", options, setting.fixture)


def _data_error(setting: Setting) -> Scenario:
    roots = setting.roots()
    series = current_path(roots.data, f"series:{PRECIP}")
    series.write_text("{}", encoding="utf-8")  # no longer the bytes of the sidecar
    return Scenario("series summary", {"dataset": PRECIP}, roots)


def _store_unavailable(setting: Setting) -> Scenario:
    root = setting.tmp_path / "nie-magazyn"
    root.mkdir()
    return Scenario("series summary", {"dataset": DAILY}, Roots(root, root))


def _io_error(setting: Setting) -> Scenario:
    roots = setting.roots()
    shutil.rmtree(roots.data / ".incoming")
    (roots.data / ".incoming").write_text("plik zamiast katalogu", encoding="utf-8")
    return Scenario("series build", {"dataset": PRECIP}, roots)


def _cancelled(setting: Setting) -> Scenario:
    cancelled = ObserwatorCancelledError("Anulowano budowę szeregu")
    setting.raising(store, "build_series", cancelled)
    return Scenario("series build", {"dataset": PRECIP}, setting.roots())


def _forbidden(setting: Setting) -> Scenario:
    return Scenario("series build", {"dataset": PRECIP}, setting.roots(), ("rest",))


def _unsupported(setting: Setting) -> Scenario:
    # No catalog command refuses a combination itself (command_for_version is
    # Python only); a refusal raised below a command is reported alike.
    refusal = ObserwatorError(
        "Komenda wersji nie do odtworzenia",
        code="unsupported",
        details={"reason": "command_not_rebuildable"},
    )
    setting.raising(store, "store_info", refusal)
    return Scenario("store info", {}, setting.roots())


def _method_not_allowed(setting: Setting) -> Scenario:
    return Scenario("store info", {}, setting.roots(), ("rest",), method="DELETE")


def _internal_error(setting: Setting) -> Scenario:
    registry = importlib.import_module("obserwator.datasets")
    setting.raising(
        registry, "datasets", ObserwatorError("Awaria testowa rejestru zbiorów")
    )
    return Scenario("datasets list", {})


SCENARIOS = {
    "validation_error": _validation_error,
    "not_found": _not_found,
    "conflict": _conflict,
    "source_unavailable": _source_unavailable,
    "missing_dependency": _missing_dependency,
    "data_error": _data_error,
    "store_unavailable": _store_unavailable,
    "io_error": _io_error,
    "cancelled": _cancelled,
    "forbidden": _forbidden,
    "unsupported": _unsupported,
    "method_not_allowed": _method_not_allowed,
    "internal_error": _internal_error,
}


def same_text(local: object, remote: object, temporary: Path) -> None:
    """REST repeats the local text, except that it hides server directories (T21)."""
    local_text, remote_text = canonical(local), canonical(remote)
    directory = in_json(str(temporary))
    if directory in local_text:
        assert directory not in remote_text
    else:
        assert remote_text == local_text


def assert_reported_alike(
    code: ErrorCode,
    scenario: Scenario,
    *,
    cli,
    rest,
    headers,
    temporary: Path,
) -> BaseException | None:
    """
    Python raises, the CLI prints and REST answers one error document of ``code``.

    Returns what Python raised (None for a cancellation or without Python).
    """
    spec = ERROR_CODES[code]
    options = scenario.given()
    raised: BaseException | None = None

    if "python" in scenario.interfaces:
        try:
            envelope = run_command(scenario.command, options=options)
        except (ObserwatorError, OSError) as exc:
            raised = exc
        if code == "cancelled":  # an envelope without a report (spec §13.6)
            assert raised is None
            assert (envelope.status, envelope.result) == ("cancelled", None)
        elif code == "io_error":  # a plain OSError, mapped by every adapter
            assert isinstance(raised, OSError) and not isinstance(
                raised, ObserwatorError
            )
        else:
            assert isinstance(raised, ObserwatorError) and raised.code == code

    if "cli" in scenario.interfaces:
        printed = cli(*cli_words(scenario.command, options))
        assert printed.exit_code == spec.exit_code
        if code == "cancelled":
            assert spec.exit_code == EXIT_CODES["cancelled"]
            document = json.loads(printed.stdout)
            assert envelope_errors(document) == []
            assert document == envelope.to_json(root=scenario.root)
        else:
            assert printed.stdout == ""
            line = json.loads(printed.stderr.splitlines()[-1])
            assert schema_errors(line, "obserwator-error/1") == []
            assert line["code"] == code
            if isinstance(raised, ObserwatorError):
                assert canonical([line["message"], line["details"]]) == canonical(
                    [raised.detail, dict(raised.details)]
                )

    if "rest" in scenario.interfaces:
        request = rest_request(scenario.command, scenario.options)
        if scenario.method is not None:
            request["method"] = scenario.method
        answered = rest.request(**request, headers=headers)
        # REST never cancels: a cancellation reaching it is a program error.
        reported = ERROR_CODES["internal_error" if code == "cancelled" else code]
        body = answered.json()
        assert schema_errors(body, "problem+json") == []
        assert answered.headers["content-type"] == "application/problem+json"
        assert answered.status_code == body["status"] == reported.http_status
        assert (body["code"], body["title"], body["type"], body["instance"]) == (
            reported.code,
            reported.title,
            f"urn:obserwator:error:{reported.code}",
            request["url"],
        )
        if isinstance(raised, ObserwatorError):
            same_text(raised.detail, body["detail"], temporary)
            same_text(dict(raised.details), body["details"], temporary)
    return raised


@pytest.mark.parametrize("code", list(ERROR_CODES))
def test_every_error_code_is_reported_alike_by_every_interface(
    code,
    cli,
    rest,
    writable,
    server,
    monkeypatch,
    tmp_path,
    tmp_path_factory,
    fixture_root,
    fixture_raw_root,
    imgw,
):
    fixture = Roots(fixture_root, fixture_raw_root)
    scenario = SCENARIOS[code](Setting(tmp_path, fixture, imgw, monkeypatch))
    serve(server, monkeypatch, scenario.roots)
    if code == "forbidden":
        monkeypatch.setattr(server, "store_writes_enabled", False)

    assert_reported_alike(
        code,
        scenario,
        cli=cli,
        rest=rest,
        headers=writable,
        temporary=tmp_path_factory.getbasetemp(),
    )


def _data_command_on_the_raw_root(setting: Setting) -> Scenario:
    raw = setting.fixture.raw  # also a store not yet split (obserwator-store.json)
    return Scenario("series summary", {"dataset": DAILY}, Roots(raw, raw))


def _raw_command_on_the_data_root(setting: Setting) -> Scenario:
    data = setting.fixture.data
    return Scenario("pmaxtp read", {"ind_x": 751, "ind_y": 317}, Roots(data, data))


def _build_reading_a_data_root(setting: Setting) -> Scenario:
    roots = setting.roots()
    return Scenario("series build", {"dataset": PRECIP}, Roots(roots.data, roots.data))


# A root of the other kind (ADR-017 D3) → the kind the command expected there.
WRONG_ROOTS = {
    "data-command-on-the-raw-root": (_data_command_on_the_raw_root, "data"),
    "raw-command-on-the-data-root": (_raw_command_on_the_data_root, "raw"),
    "build-reading-a-data-root": (_build_reading_a_data_root, "raw"),
}


@pytest.mark.parametrize("wrong", list(WRONG_ROOTS))
def test_a_root_of_the_other_kind_is_store_unavailable_in_every_interface(
    wrong,
    cli,
    rest,
    writable,
    server,
    monkeypatch,
    tmp_path,
    tmp_path_factory,
    fixture_root,
    fixture_raw_root,
    imgw,
):
    prepare, kind = WRONG_ROOTS[wrong]
    fixture = Roots(fixture_root, fixture_raw_root)
    scenario = prepare(Setting(tmp_path, fixture, imgw, monkeypatch))
    assert scenario.roots is not None
    serve(server, monkeypatch, scenario.roots)
    before = stamps_of(scenario.roots)

    raised = assert_reported_alike(
        "store_unavailable",
        scenario,
        cli=cli,
        rest=rest,
        headers=writable,
        temporary=tmp_path_factory.getbasetemp(),
    )

    assert isinstance(raised, ObserwatorError)
    assert dict(raised.details) == {"reason": "wrong_root", "kind": kind}
    assert stamps_of(scenario.roots) == before


# --------------------------------------------------------------------------
# File-system errors (spec §13.5): io_error, a Polish reason and details.path
# --------------------------------------------------------------------------


def _series_index(roots: Roots) -> Path:
    return current_path(roots.data, f"series:{DAILY}")


def _archive_file(roots: Roots) -> tuple[Scenario, Path]:
    archive = current_path(roots.raw, PLACEHOLDERS[ARCHIVE])
    version = archive.relative_to(roots.raw).as_posix()
    return Scenario("store export", {"version": version}, roots), archive


def _series_file(roots: Roots) -> tuple[Scenario, Path]:
    index = _series_index(roots)
    version = index.relative_to(roots.data).as_posix()
    return Scenario("series summary", {"version": version}, roots), index


def _series_sidecar(roots: Roots) -> tuple[Scenario, Path]:
    # Found by current_version, which never takes the version for a broken one.
    index = _series_index(roots)
    return (
        Scenario("series summary", {"dataset": DAILY}, roots),
        index.with_name(f"{index.name}.meta.json"),
    )


def _station_parquet(roots: Roots) -> tuple[Scenario, Path]:
    index = _series_index(roots)
    station = json.loads(index.read_text(encoding="utf-8"))["stations"][RABA]
    return (
        Scenario("series read", {"dataset": DAILY, "station": RABA}, roots),
        index.parent / station["file"],
    )


def _pmaxtp_cell(roots: Roots) -> tuple[Scenario, Path]:
    cell = current_path(roots.raw, "pmaxtp:pl.imgw.pmaxtp:POT/751_317")
    return Scenario("pmaxtp read", {"ind_x": 751, "ind_y": 317}, roots), cell


UNREADABLE = {
    "archive-file": _archive_file,
    "series-file": _series_file,
    "series-sidecar": _series_sidecar,
    "station-parquet": _station_parquet,
    "pmaxtp-cell": _pmaxtp_cell,
}


def assert_io_error_alike(scenario: Scenario, *, cli, rest, headers=None):
    """The library error, the CLI line and the REST problem report one io_error."""
    command, options, root = scenario.command, scenario.given(), scenario.root
    assert scenario.roots is not None and root is not None
    with pytest.raises((ObserwatorError, OSError)) as caught:
        run_command(command, options=options)
    raised = caught.value
    if isinstance(raised, ObserwatorError):
        assert raised.code == "io_error"
        expected = [raised.detail, dict(raised.details)]
    else:  # a plain OSError of a write, described by every adapter
        assert isinstance(raised, OSError)
        expected = list(describe_os_error(raised))
    spec = ERROR_CODES["io_error"]

    printed = cli(*cli_words(command, options))
    line = json.loads(printed.stderr.splitlines()[-1])
    assert (printed.exit_code, printed.stdout, line["code"]) == (
        spec.exit_code,
        "",
        "io_error",
    )
    assert canonical([line["message"], line["details"]]) == canonical(expected)

    answered = rest.request(**rest_request(command, scenario.options), headers=headers)
    body = answered.json()
    assert schema_errors(body, "problem+json") == []
    assert (answered.status_code, body["code"], body["title"]) == (
        spec.http_status,
        "io_error",
        spec.title,
    )
    # The CLI text with the server root hidden (paths relative to it, T21); the
    # root and its separator as they stand in JSON text (backslashes on Windows).
    hidden = in_json(f"{root}{os.sep}")
    assert canonical([body["detail"], body["details"]]) == canonical(expected).replace(
        hidden, ""
    )
    for server_root in (scenario.roots.data, scenario.roots.raw):
        assert in_json(str(server_root)) not in answered.text
    return raised


@pytest.mark.skipif(
    sys.platform == "win32", reason="chmod only sets the read-only attribute on Windows"
)
@pytest.mark.parametrize("unreadable", list(UNREADABLE))
def test_an_unreadable_version_is_an_io_error_in_every_interface(
    unreadable, cli, rest, server, monkeypatch, tmp_path, served_root, served_raw_root
):
    roots = written(tmp_path)
    shutil.copytree(served_root, roots.data)
    shutil.copytree(served_raw_root, roots.raw)
    scenario, target = UNREADABLE[unreadable](roots)
    serve(server, monkeypatch, roots)
    target.chmod(0)
    try:
        raised = assert_io_error_alike(scenario, cli=cli, rest=rest)
    finally:
        target.chmod(0o644)

    assert isinstance(raised, ObserwatorError)
    assert (raised.detail, dict(raised.details)) == (
        f"File system error: permission denied: {target}",
        {"path": str(target)},
    )


def test_a_failed_write_is_the_same_io_error_in_obserwator_and_rest(
    cli,
    rest,
    writable,
    server,
    monkeypatch,
    tmp_path,
    fixture_root,
    fixture_raw_root,
    imgw,
):
    fixture = Roots(fixture_root, fixture_raw_root)
    scenario = _io_error(Setting(tmp_path, fixture, imgw, monkeypatch))
    serve(server, monkeypatch, scenario.roots)

    raised = assert_io_error_alike(scenario, cli=cli, rest=rest, headers=writable)

    assert isinstance(raised, OSError) and not isinstance(raised, ObserwatorError)
    assert raised.filename is not None


# --------------------------------------------------------------------------
# Error documents of the adapters' own paths (spec §13.5)
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("method", "url", "body", "code"),
    [
        ("GET", "/api/v1/nie/ma", None, "not_found"),
        (
            "POST",
            "/api/v1/pmaxtp/sync?check=true",
            {"latitude": True, "longitude": 21.01},
            "validation_error",
        ),
        ("GET", "/api/v1/datasets/list?kolor=czerwony", None, "validation_error"),
        ("GET", "/api/v1/datasets/list?limit=1001", None, "validation_error"),
        ("GET", "/api/v1/store/info", None, "store_unavailable"),
    ],
    ids=["unknown-route", "body-type", "unknown-option", "above-maximum", "no-root"],
)
def test_rest_answers_every_refused_request_with_a_problem_document(
    method, url, body, code, rest
):
    answered = rest.request(method, url, json=body)

    document = answered.json()
    spec = ERROR_CODES[code]
    assert schema_errors(document, "problem+json") == []
    assert answered.status_code == document["status"] == spec.http_status
    assert (document["code"], document["title"]) == (code, spec.title)


@pytest.mark.parametrize(
    "args",
    [
        ("datasets", "list", "--kolor", "czerwony"),
        ("datasets", "files", "--dataset", DAILY, "--years"),
        ("magazyn",),
        (),
    ],
    ids=["unknown-flag", "missing-value", "unknown-group", "no-command"],
)
def test_obserwator_ends_every_syntax_error_with_a_validation_error_line(args, cli):
    printed = cli(*args)

    line = json.loads(printed.stderr.splitlines()[-1])
    assert schema_errors(line, "obserwator-error/1") == []
    assert (printed.stdout, line["code"]) == ("", "validation_error")
    assert printed.exit_code == ERROR_CODES["validation_error"].exit_code


def test_program_errors_are_internal_errors_in_obserwator_and_rest(
    cli, rest, monkeypatch
):
    registry = importlib.import_module("obserwator.datasets")
    original = registry.datasets

    @functools.wraps(original)
    def broken(*args, **kwargs):
        raise RuntimeError("błąd programu w rejestrze")

    monkeypatch.setattr(registry, "datasets", broken)

    printed = cli("datasets", "list")
    answered = rest.get("/api/v1/datasets/list")

    spec = ERROR_CODES["internal_error"]
    line = json.loads(printed.stderr.splitlines()[-1])
    assert schema_errors(line, "obserwator-error/1") == []
    assert (printed.exit_code, line["code"]) == (spec.exit_code, "internal_error")
    body = answered.json()
    assert schema_errors(body, "problem+json") == []
    assert (answered.status_code, body["code"]) == (spec.http_status, "internal_error")
    assert "błąd programu" not in body["detail"]  # REST keeps program internals in logs
