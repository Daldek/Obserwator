# Obserwator — Testing

Test layout, markers and how to run the tests, moved out of [CLAUDE.md](../CLAUDE.md) (Nogat standard 1.0, DOC-3.2). Test strategy and plan: [TEST_PLAN.md](TEST_PLAN.md).

The project includes unit and contract tests for the public API, CLI, REST, MCP and web GUI; all run offline (`respx` mocks or packaged recordings).

## Running Tests

Run tests and checks through uv (`uv sync --locked` first): the global Python may have an
older non-editable `obserwator` installed, which shadows the local `src/`.

```bash
# The gate (DEV-7.6): ruff format --check, ruff check, mypy, pytest + coverage, commit step
scripts/gate.sh

# Run all offline tests (live tests are deselected by the default marker expression)
uv run pytest

# Run with coverage (the gate enforces fail_under = 80)
uv run pytest --cov=obserwator

# Run specific test file
uv run pytest tests/unit/test_models.py -v

# Lint and types
uv run ruff check . && uv run ruff format --check .
uv run mypy src tests
```

## Markers

`--strict-markers` admits only the markers of `pyproject.toml`; the default expression (`-m 'not live'`) deselects `live`.

|Marker|Tests|Run|
|---|---|---|
|`live`|Real network services (`tests/live/`), outside the gate|`uv run pytest tests/live -m live`|
|`slow`|More than ~10 s or Docker (`test_library_install.py`, in the gate)|with the suite|
|`db`|Needs a database (none at present)|-|
|`hydrolog`|Needs Hydrolog's program: the analyses of `complete_pl_cz` built by the real Hydrolog, every stored line compared byte for byte with its single CLI call; skipped without `OBSERWATOR_HYDROLOG_COMMAND` (about 2 minutes on 4 CPUs)|`OBSERWATOR_HYDROLOG_COMMAND=<hydrolog> uv run pytest tests/unit/test_analyses.py -m hydrolog`|

## Test Structure

|File|Tests|Description|
|---|---|---|
|`tests/conftest.py`|-|Shared fixtures; autouse `isolated_reference_dir` (`settings.reference_dir` in a temporary directory)|
|`tests/fixtures/hydrolog/`|-|Recorded Hydrolog of the stored analyses: `fake_hydrolog.py` answers `config show` and `commands batch` with `answers.json` (the real Hydrolog on `complete_pl_cz`); `FAKE_HYDROLOG_VERSION`, `FAKE_HYDROLOG_SLEEP`, `FAKE_HYDROLOG_FAIL`, `FAKE_HYDROLOG_LOG` steer it|
|`tests/unit/test_public_store_api.py`|209|`__all__` == spec §13.12 + ČHMÚ + `agent_guide` + stored analyses (ADR-016), removed names absent, light imports|
|`tests/unit/test_cli_catalog.py`|176|CLI generated from the catalog: envelope, errors, exit codes, streams, help languages|
|`tests/unit/test_api_commands.py`|171|REST routes from the catalog, problem+json, write guard, refused request options, `Accept-Language`|
|`tests/unit/test_command_schema.py`|115|`command_schema`, `obserwator-commands/1`|
|`tests/unit/test_commands.py`|58|Catalog, validation, `run_command`/`check_command`, paging|
|`tests/unit/test_analyses.py`|26|Stored analyses (ADR-016) with the recorded Hydrolog on `complete_pl_cz`: layout, sidecar, every line verbatim, check plans, carry-forward by hard links, `stations`, `workers`, list/read/export, tampered files, on-the-fly options (passed on, refused, locked), timeout, program failure and absence; one test marked `hydrolog`|
|`tests/unit/test_command_for_version.py`|21|`command_for_version` on `complete_pl_cz` and a PMAXTP cell: the call of each family, its line read back, its offline plan of the same file; refusals `unsupported`, `not_found`, `data_error`, `validation_error`|
|`tests/unit/test_fetch_live.py`|66|Live functions with `respx`|
|`tests/unit/test_datasets.py`|59|Registry, aliases, `archive_files`, `YearsArg`|
|`tests/unit/test_parsers.py`|50|Hydro/meteo/station-list parsers|
|`tests/unit/test_exceptions.py`|49|`ERROR_CODES`, codes and details, file-system errors|
|`tests/unit/test_messages.py`|11|Message catalog: both languages, call sites against entries, Polish literals left|
|`tests/unit/test_store_*.py` (IMGW), `test_series_export.py`|321|Store writer, sync, series, catalog, pmaxtp, reader, incremental scan, export, types, fixtures, marker (`test_store_marker.py`)|
|`tests/unit/test_*_chmi.py`, `test_parsing_chmi.py`, `test_store_content.py`|363|ČHMÚ: parsers, registry, listing sync, catalog, series, export, commands, stations, content form|
|`tests/unit/test_catalog_effects.py`, `test_catalog_i18n.py`, `test_agent_guide.py`, `test_mcp_*.py`|211|Agents: effects = behavior, English texts, guide drift test, MCP tools/calls/stdio/HTTP|
|`tests/unit/test_web_app.py`|58|Web GUI|
|`tests/unit/test_cli_interrupt.py` (with `interrupt_driver.py`)|6|SIGINT and SIGTERM of real plain writes (`datasets download -o`, `store export --output`): exit codes, no staging directory, old target whole|
|`tests/unit/test_output.py`, `test_plain_output.py`|35|Plain output (ADR-007): target list, conflicts, staging and its cleanup, `files[]`, `--check` plan|
|`tests/unit/test_default_root.py`, `test_environment.py`|43|Default root and its source (`OBSERWATOR_ROOT`, `nogat.toml`, `<data_dir>/obserwator`), REST and MCP write refusals, `nogat.toml` settings|
|`tests/unit/test_library_install.py`|3|Wheel built from the checkout, installed without extras into a fresh `uv` venv: `import obserwator` and `list_commands` run (marker `slow`, ~2 s, in the gate)|
|`tests/unit/` other files|287|fetch, models, stations, urls, coverage, download_archives, fixture builder, reference data, CLI admin/main, API main, attribution lines (ADR-012), harmonized exports (ADR-014), station sources (ADR-015), error report|
|`tests/contract/test_interface_contract.py`|92|Python = CLI = REST for all 33 REST commands (analyses on the served store, built by the recorded Hydrolog), error matrix, paging|
|`tests/contract/test_command_lines.py`|200|Every example call of the catalog: `parse_command` reads its line, `validate_command` accepts it, `format_command` writes the same line|
|`tests/contract/test_chmi_contract.py`|68|IMGW-15..19 on `complete_pl_cz`; Python = CLI = REST = MCP for ČHMÚ runs|
|`tests/contract/test_mcp_contract.py`, `test_mcp_http_contract.py`|96|MCP (stdio, `/mcp`) = Python = CLI = REST for every contract case and error code|
|`tests/contract/` other files|142|Store contract (sidecar core of every kind of version), CLI = API parity, `obserwator-commands/1` against Nogat's `commands-1`, the vendored Nogat error registry|
|`tests/live/test_interfaces_live.py`|49|Live IMGW-PIB: 35 commands × Python/`obserwator`/REST (the analyses with the recorded Hydrolog), 6 live errors, MCP leg (`-k obserwator_mcp`, 8 commands); marker `live`|
|`tests/live/test_chmi_live.py`|22|Live ČHMÚ (opendata.chmi.cz) through Python/CLI/REST/MCP with a request log; marker `live`|

**Total: 3007 tests** (`pytest --collect-only`, 2026-11-13): 2936 offline, 71 live (`uv run pytest tests/live -m live`; JSON report via `OBSERWATOR_LIVE_REPORT=<file>`). The counts of the rows above were recounted the same day with `pytest --collect-only -q`. The contract suite and the analyses tests run the recorded Hydrolog (`OBSERWATOR_HYDROLOG_COMMAND` set by their fixtures); no offline test needs the real program.

## Tests (from README)

Test instructions from the README (moved unchanged).

The project includes unit and contract tests for the public API, CLI, REST, MCP and Web GUI. All run offline: the network is mocked (`respx`) or replayed from recordings in `tests/fixtures/store/`.

### Running the tests

```bash
# Gate: ruff format --check, ruff check, mypy, pytest with coverage (offline), commit check
scripts/gate.sh

# All offline tests (`live` tests are skipped by default)
uv run pytest

# With code coverage
uv run pytest --cov=obserwator
```

### Test structure

```
tests/
├── conftest.py              # Shared fixtures; autouse isolated_reference_dir (settings.reference_dir in tmp)
├── fixtures/store/          # Synthetic archives, listings and recorded HTTP responses of IMGW-PIB and ČHMÚ (fictional stations)
├── fixtures/export_golden/  # Golden files of archive export (CSV with CRLF, JSONL)
├── unit/
│   ├── test_fetch*.py, test_models.py, test_parsers.py, test_stations*.py, test_urls.py
│   ├── test_datasets*.py, test_coverage*.py, test_download_archives*.py, test_parsing_chmi.py
│   ├── test_store_*.py, test_series_export.py          # store: writer, sync, series, catalog, pmaxtp, reader, export, content
│   ├── test_fixture_builder*.py                        # obserwator.testing (complete, complete_pl_cz)
│   ├── test_commands*.py, test_command_schema.py       # command catalog, command_schema
│   ├── test_catalog_effects.py, test_catalog_i18n.py   # command effects, English descriptions
│   ├── test_agent_guide.py                             # AGENTS.md and llms.txt (drift test)
│   ├── test_mcp_*.py                                   # MCP server: tools, calls, stdio, /mcp
│   ├── test_exceptions.py                              # error code registry
│   ├── test_cli_*.py, test_api_*.py, test_web_app.py   # CLI, REST and Web GUI
│   ├── test_reference_data.py                          # python -m obserwator.reference_data
│   └── test_public_store_api.py                        # public exports contract
├── contract/                # store contract, Python = CLI = REST = MCP, ČHMÚ (IMGW-15..19)
└── live/                    # live regression (marker `live`, outside the gate): IMGW-PIB 30 commands × Python/CLI/REST + MCP; ČHMÚ
```

**Total: 2513 tests** (`pytest --collect-only`, 2026-10-31): 2446 offline and 67 live (marker `live`, run explicitly with `-m live`):

```bash
uv run pytest tests/live/test_interfaces_live.py -m live   # IMGW-PIB: 45 tests
uv run pytest tests/live -m live -k obserwator_mcp         # the MCP leg only (obserwator mcp)
uv run pytest tests/live/test_chmi_live.py -m live         # ČHMÚ: 22 tests, approx. 31 MB
```

JSON report of a run: `OBSERWATOR_LIVE_REPORT=<file>`; the ČHMÚ test writes a request log of each interface (Python, CLI, REST, MCP) and reports the number of requests and bytes (`-s`).
