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

The fixtures of `tests/e2e/conftest.py`: `gui_url` (the fixture root of both providers as a read-only copy, no basemap, IMGW-PIB's current data and PMAXTP from the library's recordings), `public_url` (the same as a public deployment with `[nogat.operator]`), `operator_url`, `hidden_url` and `featured_url` (the same as operators' instances of `[obserwator.instance]`, ADR-025: public with title, logo, regulamin, IMGW-PIB off, a clipped area and PMAXTP off; IMGW-PIB hidden with the area in focus; ČHMÚ featured beside a visible IMGW-PIB), `stored_url` (the fixture root with the analyses that the recorded Hydrolog of `tests/fixtures/hydrolog` stored, without any Hydrolog's program), `no_pmaxtp_url` (`stored_url`'s root as an instance without PMAXTP), `analysis_url` (the root of `OBSERWATOR_GUI_E2E_ROOT` with its stored analyses and Hydrolog's program for a person's choices), `admin_site` (the GUI with its admin key `OBSERWATOR_ADMIN_API_KEY` and a directory of its own for the reports and daily totals) and `open_page` (a page in a chosen theme, language and width that fails its test on any console error, page error or Content-Security-Policy violation). Every server's live tail of the chart of „teraz” (O6) answers through `FakeTail` of `tests/unit/gui/hourly.py` with values made at the time asked, so no request of a test leaves the machine.

## Test Structure

|File|Tests|Description|
|---|---|---|
|`tests/conftest.py`|-|Shared fixtures; autouse `isolated_reference_dir` (`settings.reference_dir` in a temporary directory)|
|`tests/fixtures/hydrolog/`|-|Recorded Hydrolog of the stored analyses: `fake_hydrolog.py` answers `config show` and `commands batch` with `answers.json` (the real Hydrolog on `complete_pl_cz`); `FAKE_HYDROLOG_VERSION`, `FAKE_HYDROLOG_SLEEP`, `FAKE_HYDROLOG_FAIL`, `FAKE_HYDROLOG_LOG` steer it|
|`tests/unit/test_public_store_api.py`|233|`__all__` == spec §13.12 + ČHMÚ + `agent_guide` + stored analyses (ADR-016), removed names absent, light imports|
|`tests/unit/test_cli_catalog.py`|196|CLI generated from the catalog: envelope, errors, exit codes, streams, help languages, the default root of each kind|
|`tests/unit/test_api_commands.py`|193|REST routes from the catalog, problem+json, write guard, refused request options, `Accept-Language`, the server's two roots (`OBSERWATOR_ROOT`, `OBSERWATOR_RAW_ROOT`)|
|`tests/unit/test_command_schema.py`|120|`command_schema`, `obserwator-commands/1`|
|`tests/unit/test_commands.py`|65|Catalog, validation, `run_command`/`check_command`, paging|
|`tests/unit/test_analyses.py`|29|Stored analyses (ADR-016) with the recorded Hydrolog on `complete_pl_cz`: layout, sidecar, every line verbatim, check plans, carry-forward by hard links, `stations`, `workers`, list/read/export, tampered files, on-the-fly options (passed on, refused, locked), timeout, program failure and absence, analyses entries and slots of the data root, a raw root refused; one test marked `hydrolog`|
|`tests/unit/test_command_for_version.py`|26|`command_for_version` on `complete_pl_cz` and a PMAXTP cell: the call of each family (archives, station sources and PMAXTP of the raw root; series and catalogs with `--raw-root`, analyses of the data root), its line read back, its offline plan of the same file; refusals `unsupported`, `not_found`, `data_error`, `validation_error`, `wrong_root`|
|`tests/unit/test_fetch_live.py`|66|Live functions with `respx`|
|`tests/unit/test_datasets.py`|83|Registry, aliases, `archive_files`, `YearsArg`, the download-only datasets (ADR-023), the tiers and the datasets declared ahead of their steps (ADR-030)|
|`tests/unit/test_parsers.py`|51|Hydro/meteo/station-list parsers|
|`tests/unit/test_exceptions.py`|49|`ERROR_CODES`, codes and details, file-system errors|
|`tests/unit/test_messages.py`|13|Message catalog: both languages, call sites against entries, Polish literals left|
|`tests/unit/test_store_*.py` (IMGW), `test_series_export.py`, `test_series_subdaily.py`|472|Store writer, sync, series, catalog, pmaxtp, reader, incremental scan, export, types, fixtures, markers of both roots (`test_store_marker.py`), the split of a combined store and a data root built from a read-only raw root (`test_store_split.py`), the sealing of the capture spool (`test_store_captures.py`, ADR-030); on the answers recorded in `tests/fixtures/operational` (`test_store_harvest.py`): `store sync --pace-until` of hydro-back's series and ČHMÚ's `recent` files on a fake clock (the recorded `hoursInterval`, every gap at least 5 s, spread to the deadline, today's version sealed), a station refused after the backoff (`partial`), ČHMÚ's `now` file by `live_tail`, the meteo captures' tiers, the telemetry by the datastore's listing (no HEAD, `--force` compares the bytes), ČHMÚ's hourly year, what `pace_until` refuses and the plan of a harvest; `store check|sync --start/--end` and the lock (`test_store_sync_window.py`, ADR-030 D10): a 40-day backfill on the recorded grid (5760 hours), the reach of 40 days and the other refusals, a second capture sync waiting 600 s on a fake clock then `conflict` (`sync_locked`), checks and archive syncs while locked, a holder in another process; the hourly series (ADR-031) on October 2026 recorded in `tests/fixtures/operational/october` (`test_series_subdaily.py`: 744 of 744 operational hours equal to the telemetry's, the telemetry replacing them, a gap staying operational, precedence, the D9 trim, months and `unchanged`, ČHMÚ's validated hours over `recent`, `command_for_version`, the plan) and its readers (`test_store_reader_subdaily.py`: month slots, `series_months`, reads, summaries and exports across months, REST hiding a private series)|
|`tests/unit/test_*_chmu.py`, `test_parsing_chmu.py`, `test_store_content.py`|399|ČHMÚ: parsers, registry, listing sync, catalog, series, export, commands, stations, content form; groundwater (`test_groundwater_chmu.py`, ADR-032): a published file with stray closings, weekly readings and coverage by calendar weeks, `store sync` of station × year, station × month and per-station files, `series build` and `store catalog --provider CHMU` of a bore and a spring with and without the object lists, `stations export --kind groundwater`, the series export of a weekly series|
|`tests/unit/test_parsing_gdanskiewody.py`, `test_provider_gdanskiewody.py`, `test_store_sync_gdanskiewody.py`, `test_series_gdanskiewody.py`|182|Gdańskie Wody (ADR-034) on the answers recorded on 2026-11-25 (`gdanskiewody_recordings.json`: the station list cut to eight stations, 2026-11-01 to 03 of their quantities, the error answers `-2`, `-3`, `-11`, `-13`, `-100`, one day asked twice while its hour ran), a dummy key and a fake clock (`obserwator.fetch._clock`): the parsers (families and quantities of the list, the provider's day from 06:00 to 05:00 UTC, an hour given twice or a label outside the day refused, canonical month files, the daily sum and means with three decimals, `missing` without all 24 hours, the hydrological year, the month file's name and a day outside its month), the adapter (every error code to its error, the key only in `Authorization`, nothing asked or waited without a key, the request interval and its minimum, a month's days up to today, a cancel between two days, `settled` and the `Last-Modified` of a settled month, `month_files` from the stored list, `series_reads`, `hourly_points`, the catalog, a live search naming the provider and one without it), `store check\|sync` of the month files (the stored list required, selectors refused first, plain mode refused, no request in a check, `missing`, `newer` and `current` on the clock, the days gathered into one version, the same bytes `relabeled` once settled, `--force`, a refused day failing only its file, a saved plan, `command_for_version`) and the series (the daily series of the provider's days, a running month's days, `unchanged`, subsets, `series build --check`, an unreadable file, the hourly series at the start of each label, the last provider day in the next month's version)|
|`tests/unit/test_catalog_effects.py`, `test_catalog_i18n.py`, `test_agent_guide.py`, `test_mcp_*.py`|214|Agents: effects = behavior, English texts, guide drift test, MCP tools/calls/stdio/HTTP|
|`tests/unit/gui/`|359|The GUI's server through Starlette's `TestClient` on the fixture root and its read-only copy: routes, headers, refused methods and parameters, error statuses and cache rules, the app under a prefix, `gui serve` until `SIGTERM` (Ctrl+Break on Windows) and the `nogat.gui` entry point; the rate limit, daily totals, access log (`nogat_logging`, no client addresses, no admin key), „Zgłoś uwagę” and regulamin; the admin panel (`test_admin.py`: the key and its file read on every request, reports, stats, status; ADR-020); an operator's instance on every route (`test_instance.py`, ADR-025); IMGW-PIB snapshots and PMAXTP from recorded answers; a hydrological station's card opened in the GUI and the hourly poll in the next sealed version (`test_captures.py`, 1 test, ADR-030); the climate stripes' colour scale on Hydrolog's annual means (`test_stripes.py`); ČHMÚ's groundwater objects on the variant `groundwater` (`test_groundwater.py`, 7 tests: bore or spring, catalog data and series, stations files, weekly rows at the readings, no current data); hourly series (`test_hourly.py`, 4 tests, ADR-031: hours and the tier of each value, a range of whole days, the months' coverage, a private series served by no route); the chart of „teraz” (`test_current_chart.py`, 8 tests, O6, on months planted by `hourly.py` and a `FakeTail` on a fake clock: the stored hours to yesterday 23:00 UTC with their tiers joined by today's hours of the live tail, asked once with `hoursInterval` 11; no second request within 10 minutes and one after; a private source answering `404` `private` without a request and `subdaily` false; a public IMGW-PIB station with the lines of each tier; `from` reading only the months of its range; a failed live tail serving the stored hours with its error and waiting 60 s; only a hydrological station charted; 1,000 hours asked without a stored hour); the analyses that the recorded Hydrolog of `tests/fixtures/hydrolog` stored (listed with the options a person may change, read without running a program, named by the session, shown by `DataRoot` a minute after a build, exported as JSON and CSV) and a person's choices computed by recorded programs (refused options, the memory of results, two computations at a time, timeout and failure, no program found at the start)|
|`tests/contract/test_gui_web.py`|9|The page's files: the SHA-256 of the copied Nogat files and the vendored libraries, no remote URL, no inline script or style in `index.html`, `admin/index.html` and the guide `instrukcja/index.html`, every text the scripts name a key of the area `gui`, no Polish literal in the scripts, every link of a section's explanation into the guide an id of the guide (Nogat DEV-15.14)|
|`tests/e2e/` (Playwright, Chromium)|199|The GUI in Chromium on a live server (marker `e2e`): `test_shell.py`, `test_map.py`, `test_station.py`, `test_charts.py`, `test_files.py`, `test_pmaxtp.py`, `test_sections.py` (103 tests on the fixture root; `test_shell.py`: „Regulamin” of a public deployment at the bottom of the left panel; `test_station.py`: a ČHMÚ hydrological station's „Pomiary bieżące” with its chart; `test_sections.py`: a part names the failure of one of its results and the series version by its label; `test_files.py` and `test_pmaxtp.py`: every download under the name of Nogat DEV-19.21 the server gives it); `test_current_chart.py` (4 tests, O6: „Wykres godzinowy” of an IMGW-PIB station with hydro-back set `public` at 1440 and 390 px, its legend of telemetry, stored answers and the hours fetched now, the warning and alarm levels, the caption, „30 dni” asking from 30 days back, T as points, nothing wider than a phone; a private IMGW-PIB station without the chart and without asking; a ČHMÚ station's stored hours and live tail); `test_sources.py` (6 tests: the providers' lines once per view and in the welcome window of a first visit, the welcome's one link to the terms); `test_admin.py` (1 test: the admin panel's sign-in, reports, stats and status on `admin_site`); `test_instance.py` (14 tests: the page on operators' instances, ADR-025, and `gui_url` without one); `test_accessibility.py` (4 tests: axe-core on the start page and a station's panel, on a desktop and a phone); `test_groundwater.py` (4 tests on `groundwater_url`, the variant `groundwater`: „Podziemne” and the brown diamonds, the panel of a bore and of a spring, a weekly series counted in readings); `test_hydro_half_years.py` (2 tests) and `test_meteo_snow_chmu.py` (1 test) on `stored_url`: a ČHMÚ station's half-years named as computed by Obserwator, and its card „Śnieg”; `test_smoke.py` (6 tests) opens every view in both themes and on a phone's width, every card of the fixture stations on their stored analyses without Hydrolog's program (no request of an analysis names an option, no error but those Hydrolog stored), and runs the guide's command lines; `test_file_provider.py` (9 tests, ADR-033: the test provider SIEC imported and served by the programs in processes of their own, its stations, its line in the strip, the chip „Inne źródło”, its notice and the flag of unverified data, no hand-off to Hydrolog; beside IMGW-PIB and ČHMÚ the class switch, the dataset chips under their class headings, the dashed outline, the stations counted by class and the class on every chart and table, hydromet P11 to P13); the analysis sections `test_hydro_levels.py`, `test_hydro_regime.py`, `test_meteo_precipitation.py`, `test_meteo_temperature.py` (45 tests, marker `hydrolog`, on `OBSERWATOR_GUI_E2E_ROOT` with Hydrolog's program): the default view against the stored result, a person's change against the result computed on request|
|`tests/unit/test_cli_interrupt.py` (with `interrupt_driver.py`)|6|SIGINT and SIGTERM of real plain writes (`datasets download -o`, `store export --output`): exit codes, no staging directory, old target whole|
|`tests/unit/test_output.py`, `test_plain_output.py`|40|Plain output (ADR-007): target list, conflicts, staging and its cleanup, `files[]`, `--check` plan|
|`tests/unit/test_default_root.py`, `test_environment.py`|63|Default roots and their sources (`OBSERWATOR_ROOT`, `OBSERWATOR_RAW_ROOT`, `nogat.toml`, `<data_dir>/obserwator`, `<data_dir>/obserwator-raw`), REST and MCP write refusals, `nogat.toml` settings|
|`tests/unit/test_library_install.py`|3|Wheel built from the checkout, installed without extras into a fresh `uv` venv: `import obserwator` and `list_commands` run (marker `slow`, ~2 s, in the gate)|
|`tests/unit/test_deploy_*.py`|12|The deployment (Nogat plan 2026-11-16 A2, A4): the night's catch-up with a stub of the program (the days of each harvest, the hourly series of their months, a failed harvest asked again, `--check` records nothing, the night's datasets equal to the served capture datasets), the telemetry building the months whose zips it stored, `systemd-analyze verify` of every unit with its paths given (skipped without systemd), and `obserwator-backup.sh` on fixture roots: a weekly snapshot holding only the new files as new inodes, a monthly full copy and its restore test, a failed restore test that prunes nothing, the retention, the free-space refusal, a root without its marker (Linux with `rsync` and `flock`)|
|`tests/unit/` other files|821|fetch, models, stations, urls, coverage, download_archives, fixture builder, reference data, CLI admin/main, API main, attribution lines (ADR-012), harmonized exports (ADR-014), station sources (ADR-015), daily synop data (ADR-022, `test_synop.py`), error report; an operator's instance (ADR-025: `test_instance.py` with `config show`, `test_api_instance.py` on the REST routes), series subsets (ADR-026, `test_series_subset.py`), the resume of an interrupted `analyses build` (`test_analyses_resume.py`), ČHMÚ's computed half-years (`test_analyses_half_years.py`, one test marked `hydrolog`), the providers' credentials (`test_provider_credentials.py`), the capture spool and the hourly poll (`test_captures.py`, ADR-030), the provider files and the station and series files of a provider fed by files (ADR-033, `test_provider_files.py`, `test_parsing_files.py`), REST refusing private sources (`test_api_captures.py`) and the paced requests of a harvest on a fake clock (`test_paced.py`)|
|`tests/contract/test_interface_contract.py`|96|Python = CLI = REST for all 33 REST commands, each on the root of its kind (analyses on the served data root, built by the recorded Hydrolog), error matrix, paging|
|`tests/contract/test_command_lines.py`|216|Every example call of the catalog: `parse_command` reads its line, `validate_command` accepts it, `format_command` writes the same line|
|`tests/contract/test_chmu_contract.py`|69|IMGW-15..19 on `complete_pl_cz`; Python = CLI = REST = MCP for ČHMÚ runs|
|`tests/contract/test_mcp_contract.py`, `test_mcp_http_contract.py`|102|MCP (stdio, `/mcp`) = Python = CLI = REST for every contract case and error code|
|`tests/contract/` other files|169|Store contract (sidecar core of every kind of version), CLI = API parity, `obserwator-commands/1` against Nogat's `commands-1`, the vendored Nogat error registry, REST's attachment names (Nogat DEV-19.21)|
|`tests/live/test_interfaces_live.py`|51|Live IMGW-PIB: 36 commands × Python/`obserwator`/REST (the analyses with the recorded Hydrolog; `current poll` compared by status and keys only), 6 live errors, MCP leg (`-k obserwator_mcp`, 8 commands); marker `live`|
|`tests/live/test_chmu_live.py`|22|Live ČHMÚ (opendata.chmi.cz) through Python/CLI/REST/MCP with a request log; marker `live`|
|`tests/live/test_gdanskiewody_live.py`|3|Live Gdańskie Wody (pomiary.gdanskiewody.pl, ADR-034): the station list parses, a past day of rain gives its 24 hours, an unknown symbol is `validation_error`; at most four paced requests, current and recent days only, never a backfill; skipped without `OBSERWATOR_GDANSKIE_WODY_API_KEY` or `OBSERWATOR_GDANSKIE_WODY_API_KEY_FILE`; marker `live`|

**Total: 4631 tests** (`pytest --collect-only -q -m ''`, 2026-11-25): 4555 offline (199 of them in `tests/e2e`, skipped without Chromium), 76 live (`uv run pytest tests/live -m live`; JSON report via `OBSERWATOR_LIVE_REPORT=<file>`). The counts of the rows above were recounted the same day with `pytest --collect-only -q` and add up to that total, the GUI's rows included. The contract suite and the analyses tests run the recorded Hydrolog (`OBSERWATOR_HYDROLOG_COMMAND` set by their fixtures); no offline test needs the real program. Fixtures: `fixture_roots` (`FixtureRoots`), `fixture_root` (the data root), `fixture_raw_root` (the raw root) and `groundwater_roots` (the variant `groundwater`) in `tests/conftest.py`; `served_root`, `served_raw_root` and `served` (both server settings) in `tests/contract/conftest.py`.

Fixture variants of `obserwator.testing.build_fixture_store` (CODEBASE „Offline fixture roots”): `complete` (IMGW-PIB), `complete_pl_cz` (with ČHMÚ's hydro and meteo stations), `corrupt`, `unknown_schema` and `groundwater` (ADR-032 D9): `complete_pl_cz` plus real files and server headers recorded on 2026-11-23 (`chmu_groundwater_recordings.json`): the bore `0-203-1-VP0624` „Rakousy” and the spring `0-203-1-PP0744` „Želechy”, their daily files of 2024, the weekly files of 2012 (bore) and 2014 (spring), the bore's `recent` month 2026-10, the characteristics of both, the object list and the `now` metadata cut to the rows of the two objects, the series `chmu_groundwater_daily` and `chmu_groundwater_weekly` and one ČHMÚ catalog with hydro, meteo and groundwater stations; `complete` and `complete_pl_cz` stay byte-identical. Its tests: `tests/unit/test_groundwater_chmu.py`, `tests/unit/test_fixture_builder_chmu.py` (the variant and its recordings), `tests/unit/gui/test_groundwater.py` and `tests/e2e/test_groundwater.py`.

The variant `groundwater_pl` (ADR-035) is `groundwater` plus PIG-PIB's real rows recorded on 2026-11-24 and 2026-11-25 (`pig_recordings.json`, eleven points), answered with ArcGIS's semantics by `obserwator.testing._PigService` and synchronized on a clock that starts at the probe's capture and moves only when a paced request waits: the points, October 2026's readings, the night's capture of `mwp_auto` of 2026-11-24 (with the stored hour 02 of 2026-03-29), the series `pig_groundwater_readings` and `pig_groundwater_subdaily` (2026-03, 2026-10, 2026-11) and the PIG catalog; `complete`, `complete_pl_cz` and `groundwater` stay byte-identical. Its tests: `tests/unit/test_provider_pig.py`, `tests/unit/test_series_pig.py` (on the session fixture `groundwater_pl_roots` and roots of their own) and `tests/unit/test_fixture_builder_pig.py`.

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
├── fixtures/store/          # Synthetic archives, listings and recorded HTTP responses of IMGW-PIB and ČHMÚ (fictional stations; real files of two ČHMÚ groundwater objects)
├── fixtures/operational/    # Answers recorded on 2026-11-23 for ADR-030's harvests (recordings.json: address, status, headers, file, SHA-256): hydro-back's series, the telemetry's listings and a cut zip, ČHMÚ's now metadata, recent, now and hourly files; october/: a harvest of October 2026 for 151160060 and 150160180 and the October telemetry cut to them (ADR-031)
├── fixtures/hydrolog/       # Recorded Hydrolog of the stored analyses (fake_hydrolog.py, answers.json)
├── fixtures/export_golden/  # Golden files of archive export (CSV with CRLF, JSONL)
├── fixtures/pig_staging/    # A cut of PIG-PIB's interim capture S0 as kept (ADR-035): the probe's watch-list page and a description, S0's equal run of it, a watermark page with the answer 503 after it, a summer-time hour 02 and a timed-out request; manifest lines verbatim
├── unit/
│   ├── test_fetch*.py, test_models.py, test_parsers.py, test_stations*.py, test_urls.py
│   ├── test_datasets*.py, test_coverage*.py, test_download_archives*.py, test_parsing_chmu.py
│   ├── test_groundwater_chmu.py                        # ČHMÚ groundwater: parser, weekly coverage, sync, series, catalog, exports
│   ├── test_parsing_gdanskiewody.py, test_provider_gdanskiewody.py   # Gdańskie Wody (ADR-034): parsers and adapter on its recorded answers
│   ├── test_store_sync_gdanskiewody.py, test_series_gdanskiewody.py  # Gdańskie Wody: month files of store check|sync on a fake clock, its hourly and daily series
│   ├── test_store_sync_pig.py, test_provider_pig.py, test_series_pig.py   # PIG-PIB (ADR-035): store check|sync and the harvest by watermark on a fake clock; the readings' days, the points and their search; the readings and hourly series
│   ├── test_store_staging.py                           # PIG-PIB's interim capture S0 (ADR-035): store import --staging of runs written as S0 and the probe wrote them, and of a cut of the real staging (fixtures/pig_staging)
│   ├── test_store_*.py, test_series_export.py          # store: writer, sync, series, catalog, pmaxtp, reader, export, content, captures, harvests
│   ├── test_series_subdaily.py, test_store_reader_subdaily.py   # hourly series (ADR-031): builder on October 2026, months, precedence; readers, exports, REST
│   ├── test_captures.py, test_paced.py, test_provider_credentials.py   # capture spool and hourly poll (ADR-030), paced harvests, providers' credentials
│   ├── test_deploy_*.py                                # the deployment: the night's jobs, systemd units, obserwator-backup.sh
│   ├── test_fixture_builder*.py                        # obserwator.testing (complete, complete_pl_cz, groundwater, groundwater_pl)
│   ├── test_commands*.py, test_command_schema.py       # command catalog, command_schema
│   ├── test_catalog_effects.py, test_catalog_i18n.py   # command effects, English descriptions
│   ├── test_agent_guide.py                             # AGENTS.md and llms.txt (drift test)
│   ├── test_mcp_*.py                                   # MCP server: tools, calls, stdio, /mcp
│   ├── test_exceptions.py                              # error code registry
│   ├── test_cli_*.py, test_api_*.py                    # CLI and REST
│   ├── test_analyses*.py, test_series_subset.py        # stored analyses (recorded Hydrolog), series subsets
│   ├── test_instance.py                                # [obserwator.instance] (ADR-025)
│   ├── gui/                                            # the GUI's server (TestClient), stored analyses, recorded Hydrolog programs; hourly.py: planted months and live tails of the chart of „teraz”
│   ├── test_reference_data.py                          # python -m obserwator.reference_data
│   └── test_public_store_api.py                        # public exports contract
├── contract/                # store contract, Python = CLI = REST = MCP, ČHMÚ (IMGW-15..19), the GUI's page files
├── e2e/                     # the GUI in Chromium (Playwright; markers e2e and hydrolog)
└── live/                    # live regression (marker `live`, outside the gate): IMGW-PIB 36 commands × Python/CLI/REST + MCP; ČHMÚ; Gdańskie Wody (its key, a few requests)
```

**Total: 4631 tests** (`pytest --collect-only -q -m ''`, 2026-11-25): 4555 offline and 76 live (marker `live`, run explicitly with `-m live`):

```bash
uv run pytest tests/live/test_interfaces_live.py -m live   # IMGW-PIB: 51 tests
uv run pytest tests/live -m live -k obserwator_mcp         # the MCP leg only (obserwator mcp)
uv run pytest tests/live/test_chmu_live.py -m live         # ČHMÚ: 22 tests, approx. 31 MB
uv run pytest tests/live/test_gdanskiewody_live.py -m live # Gdańskie Wody: 3 tests, at most 4 paced requests; skipped without OBSERWATOR_GDANSKIE_WODY_API_KEY[_FILE]
```

JSON report of a run: `OBSERWATOR_LIVE_REPORT=<file>`; the ČHMÚ test writes a request log of each interface (Python, CLI, REST, MCP) and reports the number of requests and bytes (`-s`).
