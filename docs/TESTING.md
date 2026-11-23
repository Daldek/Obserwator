# Obserwator — Testing

Test layout, markers and how to run the tests, moved out of [CLAUDE.md](../CLAUDE.md) (Nogat standard 1.1, DOC-3.2). Test strategy and plan: [TEST_PLAN.md](TEST_PLAN.md).

The project includes unit and contract tests for the public API, CLI, REST, MCP and the GUI, and browser tests of the GUI (Playwright with Chromium); all run offline (`respx` mocks or packaged recordings).

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

# The GUI in Chromium (tests/e2e, marker e2e; skipped while Chromium does not start)
uv run playwright install chromium
uv run pytest tests/e2e

# The GUI's analysis sections with Hydrolog's program on a root with long records (marker hydrolog)
OBSERWATOR_GUI_E2E_ROOT=<data root> OBSERWATOR_HYDROLOG_COMMAND=<hydrolog> uv run pytest tests/e2e -m hydrolog

# Lint and types
uv run ruff check . && uv run ruff format --check .
uv run mypy src tests
```

## Markers

`--strict-markers` admits only the markers of `pyproject.toml`; the default expression (`-m 'not live'`) deselects `live`.

|Marker|Tests|Run|
|---|---|---|
|`live`|Real network services (`tests/live/`), outside the gate|`uv run pytest tests/live -m live`|
|`e2e`|The GUI in Chromium: every test of `tests/e2e/`, given the marker by its `conftest.py` and skipped while Chromium does not start (CI installs none)|`uv run pytest tests/e2e`|
|`slow`|More than ~10 s or Docker (`test_library_install.py`, in the gate)|with the suite|
|`db`|Needs a database (none at present)|-|
|`hydrolog`|Needs Hydrolog's program: the analyses of `complete_pl_cz` built by the real Hydrolog, every stored line compared byte for byte with its single CLI call (about 2 minutes on 4 CPUs), the half-year characteristics Obserwator computes for a ČHMÚ station read by the real Hydrolog (`test_analyses_half_years.py`), and the GUI's analysis sections in Chromium on a root with stored analyses (`OBSERWATOR_GUI_E2E_ROOT`), where the program computes a person's choices; skipped without `OBSERWATOR_HYDROLOG_COMMAND`|`OBSERWATOR_HYDROLOG_COMMAND=<hydrolog> uv run pytest tests/unit/test_analyses.py tests/unit/test_analyses_half_years.py -m hydrolog`, `OBSERWATOR_GUI_E2E_ROOT=<data root> OBSERWATOR_HYDROLOG_COMMAND=<hydrolog> uv run pytest tests/e2e -m hydrolog`|

The fixtures of `tests/e2e/conftest.py`: `gui_url` (the fixture root of both providers as a read-only copy, no basemap, IMGW-PIB's current data and PMAXTP from the library's recordings), `public_url` (the same as a public deployment with `[nogat.operator]`), `operator_url`, `hidden_url` and `featured_url` (the same as operators' instances of `[obserwator.instance]`, ADR-025: public with title, logo, regulamin, IMGW-PIB off, a clipped area and PMAXTP off; IMGW-PIB hidden with the area in focus; ČHMÚ featured beside a visible IMGW-PIB), `stored_url` (the fixture root with the analyses that the recorded Hydrolog of `tests/fixtures/hydrolog` stored, without any Hydrolog's program), `no_pmaxtp_url` (`stored_url`'s root as an instance without PMAXTP), `analysis_url` (the root of `OBSERWATOR_GUI_E2E_ROOT` with its stored analyses and Hydrolog's program for a person's choices), `admin_site` (the GUI with its admin key `OBSERWATOR_ADMIN_API_KEY` and a directory of its own for the reports and daily totals) and `open_page` (a page in a chosen theme, language and width that fails its test on any console error, page error or Content-Security-Policy violation).

## Test Structure

|File|Tests|Description|
|---|---|---|
|`tests/conftest.py`|-|Shared fixtures; autouse `isolated_reference_dir` (`settings.reference_dir` in a temporary directory)|
|`tests/fixtures/hydrolog/`|-|Recorded Hydrolog of the stored analyses: `fake_hydrolog.py` answers `config show` and `commands batch` with `answers.json` (the real Hydrolog on `complete_pl_cz`); `FAKE_HYDROLOG_VERSION`, `FAKE_HYDROLOG_SLEEP`, `FAKE_HYDROLOG_FAIL`, `FAKE_HYDROLOG_LOG` steer it|
|`tests/unit/test_public_store_api.py`|213|`__all__` == spec §13.12 + ČHMÚ + `agent_guide` + stored analyses (ADR-016), removed names absent, light imports|
|`tests/unit/test_cli_catalog.py`|189|CLI generated from the catalog: envelope, errors, exit codes, streams, help languages, the default root of each kind|
|`tests/unit/test_api_commands.py`|190|REST routes from the catalog, problem+json, write guard, refused request options, `Accept-Language`, the server's two roots (`OBSERWATOR_ROOT`, `OBSERWATOR_RAW_ROOT`)|
|`tests/unit/test_command_schema.py`|118|`command_schema`, `obserwator-commands/1`|
|`tests/unit/test_commands.py`|63|Catalog, validation, `run_command`/`check_command`, paging|
|`tests/unit/test_analyses.py`|29|Stored analyses (ADR-016) with the recorded Hydrolog on `complete_pl_cz`: layout, sidecar, every line verbatim, check plans, carry-forward by hard links, `stations`, `workers`, list/read/export, tampered files, on-the-fly options (passed on, refused, locked), timeout, program failure and absence, analyses entries and slots of the data root, a raw root refused; one test marked `hydrolog`|
|`tests/unit/test_command_for_version.py`|26|`command_for_version` on `complete_pl_cz` and a PMAXTP cell: the call of each family (archives, station sources and PMAXTP of the raw root; series and catalogs with `--raw-root`, analyses of the data root), its line read back, its offline plan of the same file; refusals `unsupported`, `not_found`, `data_error`, `validation_error`, `wrong_root`|
|`tests/unit/test_fetch_live.py`|66|Live functions with `respx`|
|`tests/unit/test_datasets.py`|83|Registry, aliases, `archive_files`, `YearsArg`, the download-only datasets (ADR-023), the tiers and the datasets declared ahead of their steps (ADR-030)|
|`tests/unit/test_parsers.py`|51|Hydro/meteo/station-list parsers|
|`tests/unit/test_exceptions.py`|49|`ERROR_CODES`, codes and details, file-system errors|
|`tests/unit/test_messages.py`|13|Message catalog: both languages, call sites against entries, Polish literals left|
|`tests/unit/test_store_*.py` (IMGW), `test_series_export.py`|350|Store writer, sync, series, catalog, pmaxtp, reader, incremental scan, export, types, fixtures, markers of both roots (`test_store_marker.py`), the split of a combined store and a data root built from a read-only raw root (`test_store_split.py`)|
|`tests/unit/test_*_chmu.py`, `test_parsing_chmu.py`, `test_store_content.py`|373|ČHMÚ: parsers, registry, listing sync, catalog, series, export, commands, stations, content form|
|`tests/unit/test_catalog_effects.py`, `test_catalog_i18n.py`, `test_agent_guide.py`, `test_mcp_*.py`|214|Agents: effects = behavior, English texts, guide drift test, MCP tools/calls/stdio/HTTP|
|`tests/unit/gui/`|337|The GUI's server through Starlette's `TestClient` on the fixture root and its read-only copy: routes, headers, refused methods and parameters, error statuses and cache rules, the app under a prefix, `gui serve` until `SIGTERM` (Ctrl+Break on Windows) and the `nogat.gui` entry point; the rate limit, daily totals, access log (`nogat_logging`, no client addresses, no admin key), „Zgłoś uwagę” and regulamin; the admin panel (`test_admin.py`: the key and its file read on every request, reports, stats, status; ADR-020); an operator's instance on every route (`test_instance.py`, ADR-025); IMGW-PIB snapshots and PMAXTP from recorded answers; the climate stripes' colour scale on Hydrolog's annual means (`test_stripes.py`); the analyses that the recorded Hydrolog of `tests/fixtures/hydrolog` stored (listed with the options a person may change, read without running a program, named by the session, shown by `DataRoot` a minute after a build, exported as JSON and CSV) and a person's choices computed by recorded programs (refused options, the memory of results, two computations at a time, timeout and failure, no program found at the start)|
|`tests/contract/test_gui_web.py`|9|The page's files: the SHA-256 of the copied Nogat files and the vendored libraries, no remote URL, no inline script or style in `index.html`, `admin/index.html` and the guide `instrukcja/index.html`, every text the scripts name a key of the area `gui`, no Polish literal in the scripts, every link of a section's explanation into the guide an id of the guide (Nogat DEV-15.14)|
|`tests/e2e/` (Playwright, Chromium)|181|The GUI in Chromium on a live server (marker `e2e`): `test_shell.py`, `test_map.py`, `test_station.py`, `test_charts.py`, `test_files.py`, `test_pmaxtp.py`, `test_sections.py` (103 tests on the fixture root; `test_shell.py`: „Regulamin” of a public deployment at the bottom of the left panel; `test_sections.py`: a part names the failure of one of its results and the series version by its label; `test_files.py` and `test_pmaxtp.py`: every download under the name of Nogat DEV-19.21 the server gives it); `test_sources.py` (6 tests: the providers' lines once per view and in the welcome window of a first visit, the welcome's one link to the terms); `test_admin.py` (1 test: the admin panel's sign-in, reports, stats and status on `admin_site`); `test_instance.py` (14 tests: the page on operators' instances, ADR-025, and `gui_url` without one); `test_accessibility.py` (4 tests: axe-core on the start page and a station's panel, on a desktop and a phone); `test_hydro_half_years.py` (2 tests) and `test_meteo_snow_chmu.py` (1 test) on `stored_url`: a ČHMÚ station's half-years named as computed by Obserwator, and its card „Śnieg”; `test_smoke.py` (6 tests) opens every view in both themes and on a phone's width, every card of the fixture stations on their stored analyses without Hydrolog's program (no request of an analysis names an option, no error but those Hydrolog stored), and runs the guide's command lines; the analysis sections `test_hydro_levels.py`, `test_hydro_regime.py`, `test_meteo_precipitation.py`, `test_meteo_temperature.py` (44 tests, marker `hydrolog`, on `OBSERWATOR_GUI_E2E_ROOT` with Hydrolog's program): the default view against the stored result, a person's change against the result computed on request|
|`tests/unit/test_cli_interrupt.py` (with `interrupt_driver.py`)|6|SIGINT and SIGTERM of real plain writes (`datasets download -o`, `store export --output`): exit codes, no staging directory, old target whole|
|`tests/unit/test_output.py`, `test_plain_output.py`|40|Plain output (ADR-007): target list, conflicts, staging and its cleanup, `files[]`, `--check` plan|
|`tests/unit/test_default_root.py`, `test_environment.py`|63|Default roots and their sources (`OBSERWATOR_ROOT`, `OBSERWATOR_RAW_ROOT`, `nogat.toml`, `<data_dir>/obserwator`, `<data_dir>/obserwator-raw`), REST and MCP write refusals, `nogat.toml` settings|
|`tests/unit/test_library_install.py`|3|Wheel built from the checkout, installed without extras into a fresh `uv` venv: `import obserwator` and `list_commands` run (marker `slow`, ~2 s, in the gate)|
|`tests/unit/` other files|479|fetch, models, stations, urls, coverage, download_archives, fixture builder, reference data, CLI admin/main, API main, attribution lines (ADR-012), harmonized exports (ADR-014), station sources (ADR-015), daily synop data (ADR-022, `test_synop.py`), error report; an operator's instance (ADR-025: `test_instance.py` with `config show`, `test_api_instance.py` on the REST routes), series subsets (ADR-026, `test_series_subset.py`), the resume of an interrupted `analyses build` (`test_analyses_resume.py`), ČHMÚ's computed half-years (`test_analyses_half_years.py`, one test marked `hydrolog`) and the providers' credentials (`test_provider_credentials.py`)|
|`tests/contract/test_interface_contract.py`|95|Python = CLI = REST for all 33 REST commands, each on the root of its kind (analyses on the served data root, built by the recorded Hydrolog), error matrix, paging|
|`tests/contract/test_command_lines.py`|204|Every example call of the catalog: `parse_command` reads its line, `validate_command` accepts it, `format_command` writes the same line|
|`tests/contract/test_chmu_contract.py`|69|IMGW-15..19 on `complete_pl_cz`; Python = CLI = REST = MCP for ČHMÚ runs|
|`tests/contract/test_mcp_contract.py`, `test_mcp_http_contract.py`|100|MCP (stdio, `/mcp`) = Python = CLI = REST for every contract case and error code|
|`tests/contract/` other files|155|Store contract (sidecar core of every kind of version), CLI = API parity, `obserwator-commands/1` against Nogat's `commands-1`, the vendored Nogat error registry, REST's attachment names (Nogat DEV-19.21)|
|`tests/live/test_interfaces_live.py`|50|Live IMGW-PIB: 35 commands × Python/`obserwator`/REST (the analyses with the recorded Hydrolog), 6 live errors, MCP leg (`-k obserwator_mcp`, 8 commands); marker `live`|
|`tests/live/test_chmu_live.py`|22|Live ČHMÚ (opendata.chmi.cz) through Python/CLI/REST/MCP with a request log; marker `live`|

**Total: 3840 tests** (`pytest --collect-only -q -m ''`, 2026-11-23): 3768 offline (181 of them in `tests/e2e`, skipped without Chromium), 72 live (`uv run pytest tests/live -m live`; JSON report via `OBSERWATOR_LIVE_REPORT=<file>`). The counts of the rows above were recounted the same day with `pytest --collect-only -q` and add up to that total, the GUI's rows included. The contract suite and the analyses tests run the recorded Hydrolog (`OBSERWATOR_HYDROLOG_COMMAND` set by their fixtures); no offline test needs the real program. Fixtures: `fixture_roots` (`FixtureRoots`), `fixture_root` (the data root) and `fixture_raw_root` (the raw root) in `tests/conftest.py`; `served_root`, `served_raw_root` and `served` (both server settings) in `tests/contract/conftest.py`.

Fixture variants of `obserwator.testing.build_fixture_store` (CODEBASE „Offline fixture roots”): `complete` (IMGW-PIB), `complete_pl_cz` (with ČHMÚ's hydro and meteo stations), `corrupt` and `unknown_schema`. Planned for ČHMÚ's groundwater (ADR-032 D9), not yet written: the variant `groundwater` (`complete_pl_cz` plus real files recorded on 2026-11-23: the bore `0-203-1-VP0624` „Rakousy” and the spring `0-203-1-PP0744` „Želechy”, their daily files of 2024, the weekly files of 2012 (bore) and 2014 (spring), the bore's `recent` month 2026-10, the characteristics of both, the object list and the `now` metadata cut to a few real rows, the series `chmu_groundwater_daily` and `chmu_groundwater_weekly` and the ČHMÚ catalog with hydro, meteo and groundwater stations; `complete` and `complete_pl_cz` byte-identical) and its tests `tests/unit/test_parsing_chmu_groundwater.py`, `tests/unit/test_series_weekly.py`, `tests/unit/test_fixture_builder_groundwater.py`, `tests/unit/gui/test_groundwater.py` and `tests/e2e/test_groundwater.py`.

## Tests (from README)

Test instructions from the README (moved unchanged).

The project includes unit and contract tests for the public API, CLI, REST, MCP and the GUI, and browser tests of the GUI. All run offline: the network is mocked (`respx`) or replayed from recordings in `tests/fixtures/store/`.

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
├── fixtures/hydrolog/       # Recorded Hydrolog of the stored analyses (fake_hydrolog.py, answers.json)
├── fixtures/export_golden/  # Golden files of archive export (CSV with CRLF, JSONL)
├── unit/
│   ├── test_fetch*.py, test_models.py, test_parsers.py, test_stations*.py, test_urls.py
│   ├── test_datasets*.py, test_coverage*.py, test_download_archives*.py, test_parsing_chmu.py
│   ├── test_store_*.py, test_series_export.py          # store: writer, sync, series, catalog, pmaxtp, reader, export, content
│   ├── test_fixture_builder*.py                        # obserwator.testing (complete, complete_pl_cz)
│   ├── test_commands*.py, test_command_schema.py       # command catalog, command_schema
│   ├── test_catalog_effects.py, test_catalog_i18n.py   # command effects, English descriptions
│   ├── test_agent_guide.py                             # AGENTS.md and llms.txt (drift test)
│   ├── test_mcp_*.py                                   # MCP server: tools, calls, stdio, /mcp
│   ├── test_exceptions.py                              # error code registry
│   ├── test_cli_*.py, test_api_*.py                    # CLI and REST
│   ├── test_analyses*.py, test_series_subset.py        # stored analyses (recorded Hydrolog), series subsets
│   ├── test_instance.py                                # [obserwator.instance] (ADR-025)
│   ├── gui/                                            # the GUI's server (TestClient), stored analyses, recorded Hydrolog programs
│   ├── test_reference_data.py                          # python -m obserwator.reference_data
│   └── test_public_store_api.py                        # public exports contract
├── contract/                # store contract, Python = CLI = REST = MCP, ČHMÚ (IMGW-15..19), the GUI's page files
├── e2e/                     # the GUI in Chromium (Playwright; markers e2e and hydrolog)
└── live/                    # live regression (marker `live`, outside the gate): IMGW-PIB 35 commands × Python/CLI/REST + MCP; ČHMÚ
```

**Total: 3840 tests** (`pytest --collect-only`, 2026-11-23): 3768 offline and 72 live (marker `live`, run explicitly with `-m live`):

```bash
uv run pytest tests/live/test_interfaces_live.py -m live   # IMGW-PIB: 50 tests
uv run pytest tests/live -m live -k obserwator_mcp         # the MCP leg only (obserwator mcp)
uv run pytest tests/live/test_chmu_live.py -m live         # ČHMÚ: 22 tests, approx. 31 MB
```

JSON report of a run: `OBSERWATOR_LIVE_REPORT=<file>`; the ČHMÚ test writes a request log of each interface (Python, CLI, REST, MCP) and reports the number of requests and bytes (`-s`).
