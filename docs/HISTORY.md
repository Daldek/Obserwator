# IMGWTools (now Obserwator) - Release history and closed work

Archive: release history, cross-project analysis, closed backlog items and working notes moved from [PROGRESS.md](PROGRESS.md) with unchanged content (Nogat standard 1.0, DOC-6.1: PROGRESS holds only the current state). Full list of changes: [CHANGELOG.md](CHANGELOG.md).

## Released versions

| Version | Date | Scope |
|--------|------|--------|
| v3.0.0 | 2026-10 | **Versioned data store** (ADR-001): `imgwtools.store`, meteo parsers, Parquet series, `stations.geojson` catalog, PMAXTP per cell, `imgw-project/1` projects; **one catalog of 37 commands** (ADR-002): `imgw-result/1` envelope, pagination, error code registry, CLI and REST generated from the catalog, problem+json; **ČHMÚ provider** (ADR-003): registry of 17 datasets from two providers (`cz.chmi.*`), freshness from the listing, canonical content and observation registry, station catalog with SPA thresholds, quality and flags in series, restoring pins by content; **AI agent support** (ADR-004): `AGENTS.md`/`llms.txt`, English descriptions, side-effect metadata, MCP server (`imgw mcp`, `/mcp`), `GET /llms.txt`; **breaking:** `imgw fetch`/`imgw list` → catalog groups, new REST routes, `station_id` → `station`/`station_code`, `download_*` → `DownloadResult`, removal of the SQLite cache and `core/url_builder`. Details: `docs/CHANGELOG.md` |
| v2.2.0 | 2026-08 | License (year, PEP 639), manual CLA process, IMGW-PIB reference data module (`reference_data.py`), removal of IMGW data from the repo, **removal of legacy `core/imgw_spatial.py`** (breaking: extras `[spatial]` → `[pandas]`, `StationMap` removed) |
| v2.1.1 | 2026-07 | Parsers: auto-detection of delimiter/encoding (UTF-8 BOM)/quotes; meteo URLs consistent with the IMGW server; pyright compatibility; documentation audit |
| v2.1.0 | 2026-01 | Python 3.12+, code modernization (ruff fix), DEVELOPMENT_STANDARDS.md (since removed; see the Nogat standard) |
| v2.0.1 | 2026-01 | Fix import error (lazy load db module) |
| v2.0.0 | 2026-01 | API refactoring, new architecture |
| v1.0.0 | 2025-xx | First stable release |

---

## v3.0.0 — release details (2026-10-19)

Major release implementing ADR-001 (`docs/DECISIONS.md`) according to the plan `docs/superpowers/plans/2026-10-17-versioned-store.md` (tasks T01–T24) and the contract `docs/superpowers/specs/2026-10-17-versioned-store-design.md`. Full list of changes: `docs/CHANGELOG.md`.

- **Wave 0 (T01–T06):** `datasets.py` registry (`pl.imgw.*`, `archive_files`, `station_source_files`), `DownloadResult` in `download_*`, parsers in `_parsing/` (hydro moved from `db/`, new meteo `k_d`/`o_d` with flags), fixes to `stations.py` (`river_order`, `hydrographic_code`, the `rzeka` field), synthetic archives and recordings in `tests/fixtures/store/`, store types and exceptions.
- **Wave 1 (T07–T10):** writer with atomic no-replace publication and the `imgw-meta/1` sidecar, `summarize_coverage`, `imgw fetch` mirroring server paths, REST URLs from the registry.
- **Wave 2 (T11–T14):** `stations.geojson` catalog (Natural Earth outline of Poland, no GIS at runtime), `check_store`/`sync_store` with the `imgw-plan/1` plan, `imgw-series/1` Parquet series, PMAXTP per cell.
- **Wave 3 (T15–T16):** public read API (read-only, problems reported) and `imgwtools.testing.build_fixture_store`.
- **Waves 4–5 (T17–T19):** CSV export with IMGW-PIB attribution, `commands.py` command catalog, `imgw-project/1` projects.
- **Wave 6 (T20–T21):** CLI `imgw store|series|pmaxtp|project` generated from the catalog, store REST behind `IMGW_STORE_ROOT` and a write token.
- **Wave 7 (T22–T24):** removal of the SQLite cache without shims (`db/` package, CLI command, `/api/v1/hydro/data`, settings, extra), a single export list `imgwtools.__all__`, the `[store]` extra, version 3.0.0, `docs/CHANGELOG.md` and documentation update.

**Owner's decision (2026-10-17):** the versioned store goes in now, as 3.0.0; the former "Obserwator 3.0" vision (`docs/OBSERWATOR_SPEC.md`) remains a future extension (renaming, providers) and no longer covers the v2 SQLite cache.

**State after ADR-001 (T25, 2026-10-18):** 998 passed (including the T25 contract in `tests/contract/`), coverage 93% (`pytest --cov=imgwtools`), `ruff check` clean, `pyright` 0 errors.

**ADR-002 — one command catalog and consistent interfaces** (plan `docs/superpowers/plans/2026-10-17-versioned-store.md`, tasks U01–U16; spec §13):

- **Waves 10–11 (U01–U04):** `ERROR_CODES` error code registry (`code`, `details`, `IMGWCancelledError`), `CommandResult`/`Page` envelope types and a single JSON converter; registry of 13 datasets with aliases and `YearsArg`/`MonthsArg`; live functions with `station`/`station_code`, `find_stations`, `fetch_meteo_current`, `fetch_hydro_states`.
- **Waves 12–13 (U05–U08):** one slot grammar, `select_series`, `summarize_series`, `download_archives`, PMAXTP with `method="POT"`, `export_archive`/`export_series` (file or line stream), catalog of 35 commands with `command_schema` and pagination.
- **Waves 14–15 (U09–U12):** CLI and REST generated from the catalog (envelope on stdout, error JSON on stderr, exit codes, problem+json, `?check=true`), project following the ADR-002 conventions, web only on the public API.
- **Wave 16 (U13–U14):** removal of the old URL builders, `core/` and legacy routes; `imgwtools.__all__` consistent with §13.12; cross-interface contract Python = CLI = REST (`tests/contract/test_interface_contract.py`).
- **C01 (ADR-003, before the tag):** open domains of the `/1` contracts (dataset key, country, provider, license, WIGOS code, `location_source`), `content_sha256`/`content_form`, `imgw-observation/1` observation registry.
- **Wave 17 (U15):** release documentation (CHANGELOG with the §13.11 migration tables, README, CLAUDE.md, ARCHITECTURE, standards); README examples run once (Python and CLI live on a fresh store, reading on `build_fixture_store`, REST via `imgw server`); README and CLAUDE.md command tables consistent with `imgw commands schema` (one-off script).
- **Wave 17 (U16) — final gate and live regression:** new `tests/live/test_interfaces_live.py` (skipped without `IMGW_LIVE=1`, JSON report via `IMGW_LIVE_REPORT`). Run 2026-10-18T21:09:34Z (178.4 s, fresh store in tmpfs, `imgw server` on localhost, sequential requests): **42 passed** — each of the 35 commands consistent through Python, the installed `imgw` and REST (status, keys, slots, paths, streams byte for byte, store trees; local commands in REST → 404 `not_found`), 6 live errors consistent (`validation_error` 2/400, `not_found` 3/404, `store_unavailable` 8/503). Fix from the run: relative project pin paths in the envelope JSON no longer depend on the working directory (`_jsonable`). Runs interrupted by a failure on the IMGW side reported it identically (`source_unavailable`, exit 5 / HTTP 502); the test repeats such a run after 20 s and 60 s. Gate: `pytest` 1377 passed, 42 skipped (live); `ruff check` and `ruff format --check` clean; `pyright` 0 errors. 1419 tests in total (`pytest --collect-only`).

**ADR-003 — ČHMÚ provider** (spec `docs/superpowers/specs/2026-10-18-chmi-provider-design.md`, plan C01–C10 in §16; by the owner's decision of 2026-10-19 in release 3.0.0, ADR-003 erratum D16):

- **Wave C1 (C02–C03):** provider registry (`ProviderDescriptor`, `providers`, `get_provider`) and 4 `cz.chmi.*` descriptors, `archive_files(stations=)`, §9.4 types, `write_archive` with provider fields from the registry, the canonical form `chmi-json/1` (`content_sha256`), a `content_unchanged` row and observation recording; ČHMÚ parsers (hydro JSON, meteo CSV, metadata, nginx listing) and synthetic files with fictitious WIGOS codes.
- **Wave C2 (C04, C06):** freshness from the directory listing (`check_store`/`sync_store` with `stations`, plan fields `station_code`, `signal`, `remote_listed_at`, `local_observation`, `requests`), `download_archives` with `not_published`, `chmi_recordings.json` recordings; ČHMÚ station catalog (`stations/versions/chmi_stations/`, SPA thresholds, outline of Czechia), per-provider readers (`iter_store`, `read_catalog`, `read_station_list`, `store_info().providers`).
- **Wave C3 (C05, C07):** ČHMÚ series with periods known per station (`stations[<code>].periods`, `summarize_coverage(station_periods=)`), quality and flag columns in Parquet, CSV and JSONL, provider attribution in exports; catalog of 36 commands (`datasets providers`, the `provider` and `stations` options, `data_commands(provider=)`), `find_stations` for ČHMÚ, the title "Źródło danych niedostępne" ("Data source unavailable"), web IMGW-PIB only.
- **Wave C4 (C08):** projects with ČHMÚ tasks and restoring by content (`restored_by_content`, `content_match`, `pin_restored_by_content`, `get_project_status(on_notice=)`), test store `build_fixture_store(variant="complete_pl_cz")`.
- **Wave C5 (C09):** IMGW-15..19 contract `tests/contract/test_chmi_contract.py` (68 tests, Python/CLI/REST/MCP parity) and live test `tests/live/test_chmi_live.py` — run 2026-10-19: 26 passed in 77 s, 124 requests, 31.5 MB (stations `0-203-1-001000`, 2024–2026 with an unpublished 2026, and `0-203-0-11799`); fix from the run: `details.value` in `series select` as a list. Full gate (covers A01–A05): `pytest` 2129 passed, 79 skipped (live); `ruff check` and `ruff format --check` clean; `pyright` 0 errors. Live IMGW-PIB regression (`tests/live/test_interfaces_live.py`, 37 commands and the MCP leg): 53 passed in 103 s.

**ADR-004 — AI agent support** (spec `docs/superpowers/specs/2026-10-19-agent-support-design.md`, plan A01–A06 in §11):

- **Wave C4 + A1 (A01):** English descriptions of the catalog, groups, errors and datasets (`help_en`, `description_en`, `rules_en`, `title_en`), `command_schema(lang=)`, `IMGW_LANG` in the CLI (also Typer/Click elements), `Accept-Language` in REST, side-effect metadata (`writes`, `network`, `operation_id`, `env_root_when`).
- **Wave A2 (A02, A03):** `agent_guide`, the `commands guide` command (the 37th), derived files `AGENTS.md` and `llms.txt` with a drift test; MCP adapter `src/imgwtools/mcp/` (extra `imgwtools[mcp]`, modes `read`/`write`/`http`).
- **Wave A3 (A04, A05):** cleanup of legacy messages (help of `imgw admin`, `version`, `server`, OpenAPI field descriptions, `reference_data`, HTML pages outside OpenAPI; a repeated scan added items 34–37 of spec §7.2 and additions to §7.3 — erratum A04); `imgw mcp`, `/mcp` (`IMGW_MCP_ENABLED`, `IMGW_MCP_ALLOWED_HOSTS`), `GET /llms.txt`, Docker image on Python 3.12 with `.[api,mcp]` and `location = /mcp` in nginx (image built and checked 2026-10-19: `/health`, `/llms.txt`, `initialize` on `/mcp`).
- **Wave A4 (A06) and C10:** release documentation (CHANGELOG, README with ČHMÚ and agent sections, CLAUDE.md, ARCHITECTURE, standards, PRD, RULES), errata to ADR-001 and ADR-002 according to the "Impact" sections of ADR-003 and ADR-004, ADR-003 erratum D13, ADR-004 status in the index, `[ADR-003]`/`[ADR-004]` notes in spec 2026-10-17 §13 and `[ADR-004]` in spec 2026-10-18 §9.3, "3.1.0" → 3.0.0 in the ČHMÚ spec (with historical context); README and CLAUDE.md command tables consistent with `imgw commands schema` (one-off script); ČHMÚ examples run once offline on `complete_pl_cz` and live (opendata.chmi.cz), MCP examples — stdio configuration (also `--allow-writes`, `--lang en`, the `uvx` variant) and `/mcp` over HTTP — via the SDK client, Docker example on an image built with `docker compose build`. `AGENTS.md` and `llms.txt` not regenerated (catalog texts unchanged); drift test and full `pytest`: 2129 passed, 79 skipped (live).

**Compatibility fixes for Archiwista before the tag** (compatibility audit of 3.0.0 against Archiwista's requirements and review of `cb6af4f`, owner's decision 2026-10-19; branch `fix/archiwista-compat-2` from `develop` (then `slave`)):

- **Publication rollback:** after an error or Ctrl+C, `_publish_dir` no longer removes the hard-linked data files — a concurrent write of the same bytes could have taken them over and committed them with its own sidecar, and removing them left a committed version without its main file (`missing_file`, `IMGWDataError` for the slot); the interrupted publication stays, and only empty directories created by the write are removed. Regression `test_failed_commit_keeps_files_a_concurrent_writer_committed` (EIO, Ctrl+C). ADR-001 erratum 2026-10-19.
- **Hard-link requirement:** the `imgw-store.json` marker stays on `os.link`; README, ARCHITECTURE, CHANGELOG and the errata describe the requirement (FAT/exFAT, some NAS and FUSE, the macOS SMB client → `not_atomic`; the same requirement as Kartograf's store, its ADR-036) and the manual removal of an interrupted publication that a retry under the same label will not complete (station catalog, PMAXTP, an archive without `Last-Modified` retried on another day). CHANGELOG: the `[Unreleased]` section merged into `[3.0.0]`.
- **B — `meteo_kind`:** the IMGW-PIB catalog gives `climate`/`precipitation` from the current series `pl.imgw.meteo_climate_daily`/`pl.imgw.meteo_precip_daily`, `check_catalog` detects the change (cherry-pick `e77a6f9` from `fix/archiwista-compat`). ADR-001 erratum 2026-10-19.
- **D — flat download regression:** daily and sub-daily `2001_01_k.zip` in separate server paths and slots (cherry-pick `c280088`).
- Gate (offline, network blocked by a proxy): `pytest` 2134 passed, 79 skipped (live); `ruff check` and `ruff format --check src/ tests/` clean; `pyright` 0 errors.

## v2.2.0 — release details (2026-08-22)

Minor release — 20 commits on the `develop` branch on top of v2.1.1, including breaking changes (removal of the legacy spatial, api and datastore modules).

- **License:** corrected year in `LICENSE`; license metadata compliant with PEP 639 in `pyproject.toml` (`license = "MIT"`, `license-files`).
- **CLA process:** manual CLA process — `docs/CLA.md`, `CONTRIBUTING.md`, `CONTRIBUTORS.md`, PR template.
- **IMGW-PIB reference data:** IMGW data removed from the repository (`36ea672`); new module `src/imgwtools/reference_data.py` for downloading it on demand (`python -m imgwtools.reference_data`); `data/shp` untracked and ignored.
- **README:** new section on data sources and attribution.
- **Parsers:** documentation notes on extreme-value processing in `parse_semi_annual_csv`.
- **Tests:** fictitious test station "San Escobar" (123456789) instead of real IMGW data in fixtures.
- **Breaking: removal of `core/imgw_spatial.py`** — the legacy module (dead imports, pyright errors) removed; extras `[spatial]` renamed to `[pandas]` (`pyproj`/`pyshp` dependencies dropped). Anyone installing `imgwtools[spatial]` or importing `StationMap` must update their code — the functionality has no direct replacement in this release.
- **Breaking: removal of `core/imgw_api.py` and `core/imgw_datastore.py`** — classes marked DEPRECATED since 2.0.0 (`HYDRO`, `SYNOP`, `METEO`, `WARNINGS`, `PMAXTPAPI`, `DataDownloader`) removed; replacements in the public API: `fetch_hydro_current`, `fetch_synop`, `fetch_warnings`, `fetch_pmaxtp`, `download_hydro_data`, `download_meteo_data`. Only `url_builder.py` remained in `core/`.
- **Documentation and code style (2026-08-22):** `ruff format` ran over the whole repository (19 files); all docstrings in `src/` rewritten to the NumPy convention, and the `D` rules (pydocstyle, `convention = "numpy"`, without `D401`) enabled in `pyproject.toml` as a permanent lint gate (`tests/**` exempt). `docs/DEVELOPMENT_STANDARDS.md`, `docs/PRD.md`, `docs/ARCHITECTURE.md`, `docs/RULES.md`, `CLAUDE.md` and `README.md` corrected to the actual state of the code. Verification: **109 passed**, `ruff check` clean, `ruff format --check` clean, `pyright` 0 errors, coverage **23%** (`pytest --cov=imgwtools`).

**Final state of v2.2.0:** 109 passed, `ruff check` clean, `pyright` 0 errors (verification as for v2.1.1 below).

**Status:** prepared on the `develop` branch, commit `release: v2.2.0`; awaiting merge into `main` (then `master`) (no tagging/publishing at this stage).

## v2.1.1 — release details (2026-07-06)

### 🐛 Bugfix: handling inconsistent IMGW archive formats in the parsers (2026-07-05)

IMGW archival CSV files (`dane_hydrologiczne`) differ in format between years in **three** respects. The parsers in `src/imgwtools/db/parsers.py` assumed a single format (semicolon + CP1250), so most years did not parse at all. All three problems fixed:

1. **Delimiter** — most years use a comma with quotes, some (e.g. 2023) a semicolon; some files have an extra header row with column codes. The hardcoded `delimiter=";"` caused `parse_zip_file` to **silently return 0 records** for comma years. → helper `_detect_delimiter()` (per file, from the first non-empty line; tie → semicolon).
2. **Encoding** — CP1250 is the standard, but `codz_2023.zip` (daily, annual file) is in **UTF-8 with BOM**; the parser raised `UnicodeDecodeError`. → helper `_decode_content()` (BOM → `utf-8-sig`; then the requested encoding is tried with a UTF-8 fallback).
3. **Quotes** — in the **2024** daily and monthly files every line is wrapped in an outer quote with doubled quotes inside (`"149180020,CHAŁUPKI,...,""2024"",..."`), so `csv.reader` saw a single field and the parser silently returned 0 records. → helper `_iter_rows()` (a single-field row containing the delimiter is parsed again).

A leading space in the station code and the header row are handled by the existing safeguards (`_safe_int`, `.strip().strip('"')`).

**Tests:** `tests/unit/test_parsers.py` — 28 tests (delimiter, encoding, quotes, end-to-end via `parse_zip_file`). After this fix the suite had 103 tests; the final count for the whole v2.1.1 release is **109** (see the meteo URL fix below). `ruff check src/ tests/` and `ruff format --check` (then only for changed files — since 2026-08-22 formatting covers the whole repository) — clean; along the way 13 pre-existing lint errors in old test files were fixed (unused imports, import sorting).

**Verification on real data (2026-07-05, record counts):**

| File | Format | Before (2.1.0) | After the fix |
|------|--------|---------------|-------------|
| polr_Q_2020 | comma, CP1250 | 0 | 6007 |
| polr_Q_2023 | semicolon, CP1250 | 6014 | 6014 |
| polr_Q_2024 | comma, CP1250, header | 0 | 6198 |
| mies_2019–2022 | comma, CP1250 | 0 | 29,802 – 30,171/year |
| mies_2023 | semicolon, CP1250 | 29,805 | 29,805 |
| mies_2024 | comma, CP1250, **quoted lines** | 0 | 32,408 |
| codz_2020_01, codz_2022_06 | comma, CP1250 | 0 | 24,913 / 24,881 |
| codz_2023 | semicolon, **UTF-8 with BOM** | `UnicodeDecodeError` | 301,994 |
| codz_2024 | comma, CP1250, **quoted lines** | 0 | 326,845 |

**Other changes as part of the release preparation:**
- version bumped to **2.1.1** (`_version.py`, `pyproject.toml`); updated `CLAUDE.md` (version, tests, notes on the CSV format) and `README.md` (format note, test counts, `db/parsers.py` coverage 78%),
- `.gitignore`: added `.coverage`, `dist/`, `.python-version`, SQLite database files,
- fixed pre-existing lint errors in `tests/` (ruff --fix).

**Status:** released in **v2.1.1** (patch — bug fixes, no public API changes).

### 🔧 Typing: Pylance/pyright compatibility (2026-07-05)

Pylance in VSC reported errors in `db/parsers.py` (and more broadly). A `pyright` check (the Pylance engine) on the project venv confirmed: **136 errors** in `src/`. After the fixes: **0 errors**.

- **`Field(None, ...)` → `Field(default=None, ...)`** in 46 pydantic model fields (`models.py`, `db/models.py`, `api/schemas.py`, `stations.py`). Pyright does not recognize a positional default with the `Field` overloads in pydantic 2.12 — optional fields looked required (errors "Arguments missing for parameters latitude, longitude"). Change with no runtime impact.
- **`db/parsers.py`**: explicit type narrowing — `not isinstance(content, str)` (also handles bytearray/memoryview better than the old variant), `or` conditions instead of `all([...])` (pyright does not narrow through `all`). Removed the `int | None` and `memoryview.lstrip` errors.
- **`db/__init__.py`**: imports under `TYPE_CHECKING` for names loaded lazily via `__getattr__` — Pylance sees the symbols and offers completions, runtime unchanged (lazy loading preserved).
- **`cli/db.py`**: `isinstance` narrowing in the record display branches; **`api/routes/hydro.py`**: annotation `list[HydroDailyDataPoint | HydroMonthlyDataPoint]` for `data_points` (list invariance).
- **`pyproject.toml`**: new `[tool.pyright]` section (venvPath/venv + ignore for the legacy core); **`.vscode/settings.json`** (local configuration, not tracked in the repo) pointing to the `.venv` interpreter (without it Pylance analyzes the package from the old global pyenv 2.0.1).

**Done 2026-08-22 (v2.2.0):** the legacy modules `core/imgw_spatial.py`, `core/imgw_api.py` (DEPRECATED since 2.0.0) and `core/imgw_datastore.py` (dead `wget` import) were removed; `[tool.pyright].ignore` is no longer needed. Only `url_builder.py` remained in `core/`.

### 🐛 Bugfix: meteo URLs inconsistent with the actual IMGW server structure (2026-07-05)

Functional GUI verification (server run locally, all routes + forms + static files) showed that the pages, map, station list and PMAXTP work, but **`build_meteo_url` generated dead links (404)** — the structure of meteo files on the IMGW server differs from the one described in the documentation. Directory listings were verified live:

| Interval | Subtype | Actual files | Previously generated |
|---|---|---|---|
| miesieczne (k/o/s) | ≤2000 | **one file per 5-year folder** `{folder}_m_{x}.zip` | `{year}_{x}.zip` → 404 |
| dobowe/terminowe | climate, precipitation | `{year}_{x}.zip` (≤2000), `{year}_{mm}_{x}.zip` (2001+) | ✓ correct |
| dobowe/terminowe | synop | **per-station files** `{folder}_{code}_s.zip` | `{year}_{mm}_s.zip` → 404 |
| terminowe | precipitation | **dataset does not exist** | `{year}_{mm}_o.zip` → 404 |

Additionally, the 5-year folder grids start differently per subtype: climate `1951_1955`, precipitation `1950_1955`, synop `1960_1965` (a 6-year folder).

**Fix (`core/url_builder.py`):**
- `_get_meteo_folder(year, subtype)` — folder grid dependent on the subtype,
- miesieczne: file name `{folder}_m_{x}.zip` (covers both periods),
- synop dobowe/terminowe, terminowe precipitation, synop <1960 → a readable `ValueError` instead of a dead link (the GUI shows the message in the error list),
- GUI (`web/app.py`): link deduplication (years ≤2000 map to a shared 5-year file).

**Verification:** 6 new URL patterns checked with HEAD on the IMGW servers — all **200 OK** (incl. `1996_2000_m_s.zip`, `1950_1955_m_o.zip`, `1960_1965_m_s.zip`). GUI form: correct links + error message for daily synop. Tests: `test_urls.py` 22→28 (**full suite: 109 passed**). Updated the meteo structure descriptions in README.md and CLAUDE.md.

### 📚 Pre-release documentation audit (2026-07-05)

Full review of the documentation against the code (subagent + manual verification). Unified for v2.1.1:
- version 2.1.1 everywhere (removed the leftover 2.0.0 in `ARCHITECTURE.md`, 1.0.0 in `PRD.md`),
- test count **109** and test status consistent across README/CLAUDE/PRD/DEVELOPMENT_STANDARDS,
- `ARCHITECTURE.md` — updated CSV parsing section (auto-detection of delimiter/encoding/quotes),
- `README.md` — corrected map data source (`hydro-back.imgw.pl/map/stations/hydrologic`, previously wrongly `danepubliczne.imgw.pl/api/data/hydro`),
- type checker `mypy` → `pyright` in `DEVELOPMENT_STANDARDS.md` and in the "Commands" section; coverage threshold unified at 80% (`RULES.md`/`PRD.md`/`DEVELOPMENT_STANDARDS.md`); added `test_parsers.py` and the `develop` branch to the relevant lists.

**Final state of v2.1.1:** 109 passed, `ruff check` clean, `pyright` 0 errors.

### 🚀 Release finalization (2026-07-06)

- Removed the `[tool.mypy]` section and the `mypy>=1.6` dependency from `pyproject.toml` — the project uses **pyright** only (`[tool.pyright]`).
- Built fresh `dist/` artifacts for **2.1.1** (`python -m build`, hatchling backend); removed the old 2.0.1 wheels.
- Changes merged from the `develop` branch into `main`.

---

## Cross-Project Analysis (2026-01-21)

An integration analysis of 4 repositories was carried out: **Hydrograf**, **Hydrolog**, **Kartograf**, **IMGWTools**.

### Dependency map

```
HYDROGRAF (main application)
    ├── IMGWTools (IMGW data) ← THIS PROJECT
    ├── Kartograf (GIS data)
    └── Hydrolog (hydrological calculations)
            ├── IMGWTools (required) ← THIS PROJECT
            └── Kartograf (optional)
```

### Role of IMGWTools

IMGWTools is a **base library** used by:
- **Hydrograf** - directly (IMGW data, PMAXTP)
- **Hydrolog** - as a required dependency (precipitation data for hydrological calculations)

### Problems found in IMGWTools

| Problem | Status | Priority |
|---------|--------|-----------|
| Python `>=3.11` (other projects `>=3.12`) | ✅ Fixed (v2.1.0) | - |
| Uses `ruff` (others use `black+flake8`) | 🟡 Informational | LOW |
| Uses `hatchling` (others use `setuptools`) | 🟡 Informational | LOW |
| No DEVELOPMENT_STANDARDS.md | ✅ Fixed (v2.1.0) | - |

### Code standards - comparison

| Aspect | IMGWTools | Hydrolog | Kartograf | Compatibility |
|--------|-----------|----------|-----------|----------|
| Python | >=3.12 | >=3.12 | >=3.12 | ✅ |
| Line length | 88 | 88 | 88 | ✅ |
| Formatter | ruff | black | black | ⚠️ |
| Build | hatchling | setuptools | setuptools | ⚠️ |

### Recommendations

1. ~~**[CONSIDER]** Raise Python to `>=3.12` for consistency with other projects~~ ✅ Done (v2.1.0)
2. ~~**[BACKLOG]** Create DEVELOPMENT_STANDARDS.md (copy the format from Hydrolog)~~ ✅ Done (v2.1.0)
3. **[INFO]** Using `ruff` instead of `black+flake8` is OK (modern approach)

### Full documentation

Detailed cross-project analysis: `Hydrograf/docs/CROSS_PROJECT_ANALYSIS.md`

---

## Backlog — closed items

_Open backlog items are in [PROGRESS.md](PROGRESS.md), section "Next". Closed items moved without changes are below._

### Versioned store (after 3.0.0)

- [x] T25 — final contract suite (`tests/contract/`): offline state machine HEAD→plan→sync→series→catalog→CSV→project→verify/restore, CLI = API path/SHA parity (done 2026-10-18).
- [x] **C01 before the v3.0.0 tag:** opening the domains of the `/1` contracts to further providers (`dataset`, `country`, `provider`, `license.id`, WIGOS station code, `location_source` values), optional canonical-content fields `content_sha256` and `content_form` in `imgw-meta/1` and in `files[]` of `imgw-project/1`, and the `imgw-observation/1` observation registry (`observations/` directory in the archive slot, `kind="observation"` entries in the scan, internal publication of observations) — with no change to IMGW behavior or bytes (done 2026-10-18, commit `549795c`; calling observation recording in `write_archive` belongs to C02).
- [x] **ČHMÚ provider (Czechia, opendata.chmi.cz)** — ADR-003 and spec `docs/superpowers/specs/2026-10-18-chmi-provider-design.md` (plan C02–C10), in release 3.0.0 (erratum D16): `cz.chmi.hydro_daily`, `cz.chmi.meteo_daily`, station lists and the `cz.chmi.stations` catalog with SPA thresholds, freshness from the listing, canonical content `chmi-json/1` with the observation registry, ČHMÚ quality and flags in series, restoring pins by content; IMGW-15..19 contract and live test (done 2026-10-19, C02–C10). Meets Archiwista's requirements IMGW-15..19 (v0.6 "PL + CZ").
- [x] **Writing to the store on macOS and Windows** — version publication following Kartograf's model (hard links, the sidecar commits the version; ADR-001, erratum 2026-10-19) instead of `renameat2`, which is available only on Linux; directory `fsync` skipped on Windows (done 2026-10-19; checked on Linux, Windows simulated by refusing `os.open` on a directory).

### AI agent support (after 3.0.0)

- [x] **Agent surfaces in English (AGI-9.2, ECO-042, DEV-2.3, AGI-9.1, ADR-006)** — message catalog `imgwtools.messages` (`Text(en, pl)` under the key `<area>.<name>`, `message()`, `Message`, `localize()`, `reason()`; guard test `tests/unit/test_messages.py`), `detail` of all exceptions and item errors, notices, progress and plan lines, CLI (last stderr line in English, help and lines per `IMGW_LANG`), MCP server in English only (`imgw mcp --lang` removed), `command_schema`/`list_commands`/`agent_guide` in English by default, `AGENTS.md` and `llms.txt` in English, REST without `Accept-Language` in English (`Content-Language`, `Vary`), OpenAPI in English (model field descriptions too), dataset titles and descriptions of commands, options, rules and groups as catalog entries with English main text (`help_en`, `description_en`, `rules_en`, `title_en` removed), web GUI pages in the `web` area (the GUI stays in Polish). Done 2026-10-24 in nine commits on the `chore/nogat-2.1` branch; after the last one no Polish literal remained outside the catalog.

### Data output (after 3.0.0)

- [x] **Data output convention (ECO-051, DEV §19, ADR-007)** — branch `feature/data-output` (commits from `1dc2b61`; no push, tag or merge): three output targets with one name across the library, CLI, MCP and guide (`output_dir`/`--output-dir`/`-o` plain files, `root`/`--root` store, `output`/`--output` a single export file, `--force`), default store `<data_dir>/imgw` and `IMGW_ROOT` instead of `IMGW_STORE_ROOT`, plain mode of `datasets download`, `store sync`, `pmaxtp sync` and exports (preflight with `details.paths`, staging `.imgw-incoming/`, `os.replace`, `--force`, `--check` with `write|replace|conflict`, `files[]` with streaming SHA-256), the `imgw-store.json` marker with `tool`, `created_at` and `producer_version` created by the first write, nested stores by marker names, statuses `new`/`unchanged`, `imgw mcp --allow-dir`; tests: REST and MCP refusals (DEV-19.3), sidecar core (DEV-19.16), marker contract (DEV-19.12), SIGINT and SIGTERM through real commands (DEV-19.7); smoke `store sync` in the default root without a prior store (done 2026-10-25).

### Infrastructure and code quality

- [x] ~~Fallback station lists hardcoded in the code (`api/routes/hydro.py`, `api/routes/meteo.py`)~~ — routes removed in 3.0.0 (ADR-002); station lists come from `find_stations` using the IMGW CSV.

### Done (archive)

- [x] CLI (`imgw` command)
- [x] REST API (FastAPI)
- [x] Web GUI (HTMX + Jinja2)
- [x] PMAXTP data
- [x] Current hydro/meteo/synop data
- [x] Archive data download
- [x] Warnings
- [x] ~~SQLite cache (optional)~~ — removed in 3.0.0 (ADR-001 D5), replaced by the versioned store
- [x] Versioned data store: 1:1 archives with sidecars, freshness plan, Parquet series, `stations.geojson` catalog, PMAXTP per cell, CSV export, projects, CLI and REST (v3.0.0)
- [x] One command catalog for Python, CLI and REST: `imgw-result/1` envelope, pagination, error code registry, `command_schema`, CLI and REST generated from the catalog, cross-interface contract (ADR-002, v3.0.0)
- [x] ČHMÚ provider in the registry, store, command catalog and projects (ADR-003, v3.0.0)
- [x] AI agent support: `AGENTS.md`/`llms.txt`, English catalog descriptions, side-effect metadata, MCP server `imgw mcp` and `/mcp`, cleanup of legacy messages (ADR-004, v3.0.0)
- [x] Daily meteo parsers `k_d`/`o_d` with missing-value flags (v3.0.0)
- [x] Public test store builder `imgwtools.testing` for Archiwista and Retman (v3.0.0)
- [x] Raising Python to `>=3.12` for consistency with other projects (cross-project recommendation, v2.1.0)
- [x] DEVELOPMENT_STANDARDS.md in the Hydrolog format (cross-project recommendation, v2.1.0)

### Nogat standard 1.0 compliance (`chore/nogat-2.1`, moved from PROGRESS on 2026-11-16)

- **Done:** pyright → mypy `strict` (ECO-010; tests without annotations are a DEV-7.3 deviation in `CLAUDE.md`), `scripts/gate.sh` + `check-commits.sh`, `uv.lock`, the `live` marker instead of `IMGW_LIVE=1`, coverage ≥ 80% (DEV-7.5), CI/Dependabot from the Nogat templates (they work after the branch rename), `forbidden` with exit code 12 (ERR §4), erratum to ADR-001 D1 (hard links), MCP prefix `obserwator_` = the catalog `operation_id` = the OpenAPI `operationId`, the full set of MCP annotations with `idempotentHint`, the `commands list` command (ECO-018, AGI-5.2, AGI-5.4, AGI-5.9, AGI-6.2; ADR-004 erratum of 2026-10-24); user environment DEV-18: `nogat.toml` via `tomllib`, `NOGAT_*`, `cache_dir`, `IMGW_DATA_DIR` → `OBSERWATOR_REFERENCE_DIR` (breaking change), `obserwator config show --json`, 18 variables in README and `.env.example` (ADR-005).
- **Done (document budgets, DOC-1.7), as of 2026-10-31:** `CLAUDE.md` 96 lines (budget 200), `README.md` 221 (400), `docs/PROGRESS.md` 191 (300), `AGENTS.md` 174 lines and 16.0 KiB in both languages (200 lines and 16 KiB), `llms.txt` 2,810 characters before the first list of links (8,000); the `AGENTS.md` and `llms.txt` budgets are guarded by `tests/unit/test_agent_guide.py`, the rest are limits for review. Content moved out of `CLAUDE.md` and `README.md` lives in `docs/CODEBASE.md`, `docs/TESTING.md` and `docs/USAGE.md`. The "unusable `nogat.toml`" error has `details.reason = "invalid_config"` (the cause text in the message), and a file not in UTF-8 ends with `validation_error` (test `test_environment.py`).
- **README by DOC-2.1 (2026-11-16):** the sections, their order and the summary of 337 characters follow DOC-2.1 to DOC-2.5; the reference material it held (store details, GUI, server logs, configuration) is in `docs/USAGE.md`.

### Releases 3.0.0 to 3.1.0 (moved from PROGRESS on 2026-11-22)

Moved without changes, but the status of the narrow-screen item: the steps of release 3.0.0, the deployment of 2026-11-15, the items of release 3.1.0 and the defects fixed in 3.0.1 and 3.1.0.

#### Release 3.0.0 (PROGRESS "Next" item 1 until 2026-11-22)

1. **Release 3.0.0 (frozen by the author on 2026-11-16):** a member of the first joint release of the Nogat ecosystem (Nogat release set candidate-6; ECO-074), the first release under the name Obserwator (ADR-009, ECO-057); the last tag is IMGWTools `v2.1.1` (2026-07-06). What it ships, with the migration from 2.1.1: [CHANGELOG "Unreleased"](CHANGELOG.md). Until the tag the only further change is the release commit: Obserwator pins no producer of the ecosystem, so it gets no pin commit, and every other change, a defect included, waits for 3.0.1 or 3.1.0 ("Release 3.0.1" and "Known defects" below). Steps (Nogat REL-2.1, REL-6.6), run by Nogat's coordinator and the author:
   1. The coordinator re-pins the consumers, builds Nogat's release set candidate-6 and verifies it (REL §6).
   2. The release commit on `develop`: `__version__` `3.0.0` in `src/obserwator/_version.py`, `[Unreleased]` → `[3.0.0] - <date>` in the CHANGELOG, `uv.lock`.
   3. Merge `develop` → `main` (DEV-3.6) and the author's annotated tag `v3.0.0` on the merge commit, after Kartograf `v0.8.0` and before Hydrolog, Hydrograf and Archiwista (producers first).
   4. The consumers of Obserwator in the set replace their commit pins with the tag `v3.0.0` and narrow their ranges in their own release commits (REL-5.3, REL-5.6): Hydrolog (extras `pmaxtp`, `gui`) and Hydrograf (a dependency of its backend), both through `[tool.uv.sources]`, and Archiwista (extra `obserwator`) pin `f4f6a8d` today, the commit of Nogat's release set candidate-5. Retman, no member of the set, pins `3816b3c`.

#### Deployment of synop data (PROGRESS "Next" item 6 until 2026-11-22)

6. **Deployment of synop data (ADR-022; session 2026-11-15):** `obserwator-public.service` deployed at commit 3816b3c with its raw root on a NAS share (2825 archives moved there and verified); synop sync 1966–2026 complete (1882 new archives merged into store); analyses built: `pl.imgw` version 2026-11-15_2c0ccedb (3240 stations, 82362 ok, 2093 failed vs 2061 before), `cz.chmi` version 2026-11-15_b3178c6e (23 stations). First analyses build as background job was interrupted at 2332/3240 stations when agent session ended; resume plan in "Release 3.0.1", last item (carry-forward matched stations, recompute the rest). The failures, checked on 2026-11-15 from the stored lines: 984 are `calculation_error` (a record too short for the method, e.g. Mann-Kendall, flood frequency), 1 `data_error`, 1108 `internal_error` of Hydrolog 0.8.0.dev0, 1102 of them an `IndexError` of its daily meteorological commands on a station file that starts or ends with days without a value (`meteo snow` on 249180050, whose snow cover starts in 2011 in a record from 1961; `meteo precipitation` on 249180030, whose last 365 days have no precipitation; the same file without those days computes); the 32 more than on 2026-11-13 are 17 of the 9 new synop stations and 15 of 9 stations whose joined record changed, all such `internal_error`. A Hydrolog bug, reported to Hydrolog; Obserwator's export is unchanged. Once Hydrolog is fixed, `analyses build` recomputes those stations only if Hydrolog reports another version (the carry-forward compares it; open question below).

#### Release 3.1.0 (the author's decisions of 2026-11-14, 2026-11-17 and 2026-11-18)

Planned on 2026-11-14 as 3.0.1; on 2026-11-17 the author made 3.0.1 a release of defect fixes only, beside the patches of the other members, and moved these changes to 3.1.0. On 2026-11-18 the author added the last two items: the data of every provider should be consistent, so ČHMÚ gets the snow and the half-year characteristics that IMGW-PIB already has. The first five were found on 2026-11-14 while checking how the GUI serves „Pomiary bieżące”: the browser asks only this server (`api/current`, CSP `connect-src 'self'` and the tile host), which fetches IMGW-PIB and keeps each source in process memory for `CURRENT_TTL_S` (600 s), shared by all users (`gui/_live.py`). That stays: direct requests from browsers would multiply the load on IMGW-PIB (its answers are `no-store`), send every user's address to it and duplicate the parsers in JS.

- [x] Honest request headers to hydro-back.imgw.pl: `_MAP_HEADERS` (`stations.py`) drop the `Referer: https://hydro.imgw.pl/` that passes this program off as IMGW-PIB's own page, and the `User-Agent` names the program and its project address (`Obserwator/<version> (+<URL>)`, no personal data); the docstrings that say the backend requires both headers are corrected. Checked on 2026-11-14: the map (`map/stations/hydrologic`) and a station's card (`station/hydro/status`) answer 200 to `Obserwator/<version>` without a `Referer`, and 403 only to the default user agents of curl and httpx. Done (`feat/current-data-3.1.0`, merged into `develop` 2026-11-21, `19e578b`; ADR-021 erratum of 2026-11-21; both answered 200 again on 2026-11-21).
- [x] Refresh in the background: when an entry of `_live.py` expires, the requests get the last good data while one refresh runs, instead of all waiting on the lock for the upstream call (up to 30 s per source). Done (`feat/current-data-3.1.0`, merged into `develop`; ADR-013 erratum of 2026-11-21): only a source that never answered is waited for.
- [x] Fetch the sources of `/api/current` in parallel: today `states`, `hydro` and `meteo` are fetched one after another, so a cold first request can take up to about 90 s. Done (`feat/current-data-3.1.0`, merged into `develop`): on 2026-11-21 (local instance on the deployment's data root, load about 14 on 4 CPUs) the cold first `api/current` took 1.96–2.93 s before (two more runs 8.4 and 9.2 s) and 0.94–1.62 s after, the slowest source alone (`hydro` or `meteo`, 0.8–1.6 s).
- [x] `ETag` and `304 Not Modified` on `/api/current` and `/api/current/{code}`: today every poll of every open tab (each 10 minutes) downloads the whole answer (about 287 KB). Done (`feat/current-data-3.1.0`, merged into `develop`): a revalidation is `304` with 0 bytes in 5–16 ms against 301 KB (47 KB gzipped) in 35–45 ms.
- [x] Log every upstream fetch of `_live.py` (source, duration, outcome, error code) in the app log (`nogat-log/1`), so that failures of IMGW-PIB and the number of requests to it can be seen. Done (`feat/current-data-3.1.0`, merged into `develop`): app records `upstream_fetch`, PMAXTP included (USAGE "Server logs").
- [x] Rainfall intensity curves in the view „PMAXTP”, as on klimat.imgw.pl/opady-maksymalne: a chart of the maximum rainfall intensity q [dm³/(s·ha)] against the duration t, one curve per probability of exceedance p, for the point and method of the result, beside its tables (`gui/web/src/pmaxtp/result.js`, drawn by the shared chart module `gui/web/src/charts/`). PMAXTP's own definition: q = 166.7·J, where J = h/t [mm/min] is the intensity of the quantile h [mm] of duration t [min]; q is computed from the quantiles (ks) of the answer, so the chart is processed data and carries PMAXTP's line PP („…zostały przetworzone”) with PS, as the view's strip already does. The user guide (part 05) describes the chart. Done 2026-11-21 (`feat/gui-pmaxtp-chart`, merged into `develop` with `feat/gui-quick-3.1.0`, `11c52b7`): both axes logarithmic, the curves a colour ramp from the rarest p to the most frequent, no image export (no chart of the module has one).
- [x] Resume an interrupted `analyses build` (Nogat ECO-073; the author's decision of 2026-11-15): `_build_provider` (`store/analyses.py`) stages every finished station in `analyses/.incoming/<host>_<pid>_<uuid>/`, but the next start's `_cleanup` removes that directory as a leftover, so on 2026-11-15 a deployment build lost 2332 of 3240 stations (about 2 hours) when the agent's session ended. The next build takes from a leftover staging directory, without computing them again, the stations whose input series version, `definitions_digest()` and Hydrolog version equal the current ones (the same test as `carried` from the published version), computes the rest and publishes as today; a staging directory that matches nothing is removed as today. Tests: an interrupted build resumed gives the same version as an uninterrupted one; a changed input, definition or Hydrolog version computes the station again. Done (`feat/analyses-resume-3.1.0`, merged into `develop` with `feat/chmi-snow-halfyears`, `8990056`; ADR-016 erratum of 2026-11-21).
- [x] ČHMÚ snow (the author's decision of 2026-11-18): `cz.chmi.meteo_daily` reads only the elements `SRA`, `T`, `TMA` and `TMI` (`_CHMI_METEO_FILE`, `datasets.py`; `_parsing/chmi.py`), so ČHMÚ stations have no snow, while IMGW-PIB's daily series have `snow_cover` and `fresh_snow` [cm] and its analyses use them. Add ČHMÚ's daily snow elements of the same `daily` folder (to check against the published files: total snow depth `SCE`, new snow `SNO`, water equivalent `SVH`) under the variable names of IMGW-PIB's series where the quantity is the same (`snow_cover`, `fresh_snow`, `snow_water_equivalent`), with their terms and units in `variable_notes`; then rebuild the series and the analyses, so the snow analyses cover ČHMÚ stations as IMGW-PIB's. Done (`feat/chmi-snow-halfyears`, merged into `develop` 2026-11-21, `8990056`; ADR-003 erratum of 2026-11-21): `SCE` → `snow_cover`, `SNO` → `fresh_snow`; `SVH` is the water equivalent in mm, not IMGW-PIB's `snow_water_equivalent` in mm/cm, so it is not read ("Open questions"). Open: the deployment's sync of the snow files and the rebuild.
- [x] Half-year characteristics of ČHMÚ (the author's decision of 2026-11-18): `characteristic.{H,Q,T}.half_years` read IMGW-PIB's own half-year file (`pl.imgw.hydro_semiannual`, `half_year_file`; `store/analysis_registry.py`), and ČHMÚ publishes none, so its stations lack them. Compute them from ČHMÚ's daily series with the definitions of IMGW-PIB's file (hydrological half-years: winter November–April, summer May–October; the same statistics), and say in the analysis that they are computed, not published. IMGW-PIB keeps its published file. Check after the rebuild that every kind of analysis exists for both providers, or name in `docs/` why a kind is provider-specific (ČHMÚ's SPA 1–3 and its drought and q50 thresholds, today ČHMÚ only). Done (`feat/chmi-half-years-3.1.0`, merged into `develop` with `feat/chmi-snow-halfyears`, `8990056`): a derived input `AnalysisInput.derived="half_years"`, result field `derived`; the provider-specific kinds are named in docs/USAGE.md (the check after the rebuild remains).

Not taken (2026-11-14): a request to IMGW-PIB for permission to use hydro-back.imgw.pl, which is the undocumented backend of hydro.imgw.pl and not a public API, and a move of the water states to danepubliczne.imgw.pl.

#### Release 3.1.0: responsiveness and accessibility of the public GUI (the author's decision of 2026-11-20)

Found on 2026-11-20 from the access logs of 2026-11-14 to 2026-11-20 (about 4,300 requests; 2,664 on 2026-11-19, the day of the presentation, at about 500 an hour, with no `429` and no `5xx`), `curl` against `127.0.0.1:8060` and through the Cloudflare tunnel (about 130–150 ms of round trip per request), and a headless browser emulating an iPhone 13 on `fast3g` with a 4× slower CPU, with axe-core 4.13 on the start page and on a station. The start today is a chain: the HTML and 71 files (63 modules of `src/`, MapLibre, CSS) end at 1.23 s, `api/texts` only then (to 1.99 s), then `api/session`, `api/downloads/stations` and `api/stations` (to 3.5 s), then the basemap's tiles. The first four items touch every visit and change no interface.

Quick fixes:

- [x] `api/stations` answers `304` without building its answer: today the layer (1.63 MB of JSON, 141 KB gzipped) is assembled on every request, about 220 ms, and a `304` still takes about 100 ms. Check `If-None-Match` against the layer's ETag first and keep the built, compressed answer in memory until the snapshot changes.
- [x] The start does not wait in a chain: `index.html` preloads `api/texts?lang=…`, `api/session` and `api/stations` (`<link rel="preload" as="fetch" crossorigin>`) and the entry modules (`modulepreload`), or `main.js` asks for them together; two to three round trips less.
- [x] `favicon.ico`, `robots.txt` and `apple-touch-icon.png` (with `apple-touch-icon-precomposed.png`) are served: 43 answers `404` in the logs.
- [x] The data root's snapshot is read again in the background: `DataRoot.snapshot` reads it on a request when the last read is older than a minute, so at low traffic nearly every visit pays for it (`api/session` cold about 190 ms against 1 ms warm, median 314 ms in the logs). The requests take the last snapshot while one read runs, as the refresh of `/api/current` in the section above, which today takes about 1 s cold against 36 ms.
- [x] Long cache of static files: everything is `Cache-Control: no-cache`, so each visit asks again for 71 files and MapLibre's module (286 KB gzipped) goes through the tunnel every time (`cf-cache-status: DYNAMIC`). Files of `vendor/` get the version in their address (the worker already has `?v=6.14.0`, the module and its CSS do not) and `src/`, `css/` a digest of the build, all with `max-age=31536000, immutable`; `index.html` and `api/` stay `no-cache`.
- [x] Narrow screens: the attribution strip takes 127 of 844 px (15 %) at all times, over an open station's panel too; one line with „Źródła i warunki” opening the full text instead. The station button of the top bar overflows the screen by 5 px and cuts the name (ANNOPOL); a maximum width with an ellipsis. On 2026-11-21 the station button got its ellipsis (it shrinks to what the bar leaves); the one-line strip came with Nogat's kit (ECO-080, `feat/phone-sources-strip`, merged into `develop` `64f6abb`), in 3.1.0.
- [x] Accessibility (axe-core): no `<h1>` on the page (a visually hidden one); two landmarks named „Mapa stacji” (`.view-center`), each gets its own name; serious: `<dl class="figures">` of the station's „Pomiary bieżące” holds children other than `dt`/`dd` groups or `div`.

#### Release 3.1.0: findings of the release round (the coordinator's list of 2026-11-21)

Both merged into `develop` with `fix/3.1.0-findings` (`e68df87`, 2026-11-21), as were GEO-03, GEO-04, E3-01 and E7-11 below.

- [x] REST CORS: `allow_origins=["*"]` with `allow_credentials=True` replaced by `OBSERWATOR_CORS_ORIGINS` (`cors_origins` in `[obserwator]`; default no cross-origin access, never credentials; `config show` lists it).
- [x] Security headers: `obserwator server` sends `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer` and the GUI's `Permissions-Policy`, which now denies every unused browser feature (`_http_headers.py`); the GUI's start page and admin panel checked in Chromium without a console warning.

#### Release 3.1.1: its first item, taken into 3.1.0

- [x] `.env` in `.gitignore` (taken into 3.1.0 on 2026-11-21): `.env`, `.env.*` (but `.env.example`), `api_keys.json`, `*.key`, `*.pem` and `*.secret` are ignored; `tests/unit/test_environment.py` checks it with `git check-ignore`. Step 0 of Nogat's plan `docs/plans/2026-11-20-hydromet-providers.md` (branch `plan/hydromet-providers`).

#### Known defects fixed in 3.0.1 and 3.1.0

Found by Nogat's integration run of candidate-5 and by the scenario test of 2026-11-15 and 2026-11-16 (PROGRESS "Known defects"):

- C4: a plain plan (`--check` with `--output-dir`) into another tool's store lists `ATTRIBUTION.txt` as `write` while the run refuses every target (DEV-19.10, DEV-19.11) — fixed on `fix/3.0.1`: the plan lists it as a `conflict` (`output_in_store`) like every target.
- C5: the hint of `store_unavailable` `no_marker` does not name the path (DEV-19.13; Kartograf's half of C5 is Kartograf's) — fixed on `fix/3.0.1`: the hint is `obserwator store init --root <path>` (`--kind data` for a data root).
- C7: `test_instructions_are_english_and_hold_the_rules_and_the_mode_below_2_kib[read]` fails under a long `TMPDIR` (2,050 bytes), as it puts `tmp_path` paths into the instructions — fixed on `fix/3.0.1`: the test names fixed paths.
- GEO-03: in the IMGW-PIB catalog 2,143 of 3,811 stations have no location and meteo stations no `meteo_kind` or `established_year`, partly for a reference file not downloaded, which only `problems` hints — fixed for 3.1.0 as far as it was a defect (merged into `develop`): `store catalog` warns of a missing reference file (`source_missing`, 34 hydro.imgw.pl map stations left unlocated on the 2026-11 roots) and of the meteo series missing for `meteo_kind` (`series_missing`); the catalogs did not change. Not published by any stored source: 2,109 locations (495 hydro, 1,614 meteo), the `established_year` of meteo stations and 533 meteo kinds (no daily data). Q1 for the author ("Open questions"); Q2 decided by the author on 2026-11-21 ("Release 3.2.0").
- GEO-04: `stations find --source live` gives no coordinates and no area filter — fixed for 3.1.0 (ADR-024; merged into `develop`): live IMGW-PIB stations carry the coordinates of the current-data API (807 of 1,301 hydro, 570 of 2,185 meteo on 2026-11-21; the rest are not reported by it), and `stations find --bbox west,south,east,north` filters both sources by area.
- E3-01: `series build` has no station or year filter (for 12 stations it built the national sets, 2 × 763 s, 479 MB) — fixed for 3.1.0 (ADR-026; merged into `develop`): `series build --stations/--years` builds a subset version recorded as such (`subset`, `request`); a data root holding the full series refuses a subset (`full_series`), and a new subset replaces the one before (ADR-026 D5, confirmed by the author on 2026-11-21).
- E3-06: `obserwator server` without the extra `api` ends with a `ModuleNotFoundError` traceback (exit 1) instead of `missing_dependency` (exit 6) — fixed on `fix/3.0.1`: without FastAPI or uvicorn it ends with `missing_dependency` (`details.extra="api"`, hint `pip install "obserwator[api]"`).
- E7-11: an idle `obserwator gui serve` holds about 1 GB in swap (test and production instance) — fixed for 3.1.0 (ADR-027; merged into `develop`): the snapshot keeps a summary of each series index, large reads are compacted, series documents are limited to 2 million cells; idle RSS 1,490 → 722 MB, peak 2,258 → 1,127 MB on the deployed root (554 requests). Left: about 190 MB of free pymalloc pools and 140 MB of free glibc memory after the file exports and computations on request (not compacted); the 50 MB `series.json` of `pl.imgw.meteo_precip_daily` is parsed whole on every `read_series` ("Open questions").
- ČHMÚ daily meteo at older observation terms (found on the deployment's raw root, 2026-11-17): `series build --dataset cz.chmi.meteo_daily` failed as a whole (exit 11) on the rows of 85 of 3,351 files stamped at a station's term of the time (`SRA` 05:00 or 07:00, `TMA`/`TMI` 18:00 to 21:00, `T` terms 05:00 to 21:00) — fixed on `fix/3.0.1` (ADR-003 erratum of 2026-11-17).

#### Formula audit of 2026-11-18 (branch `fix/presentation`)

Defects found by Nogat's formula audit of 2026-11-18 (its `TRIAGE.md`: T24, T25, T26 and the follow-up of Hydrolog's `hotfix/ml-fits`), fixed on `fix/presentation` before the public presentation of 2026-11-19, merged into `develop` (`04c017f`) and deployed on :8060:

- T25: two values a few ulps apart on a chart's axis without `zero` (H, Q, T, regime, trends, temperature, rating curve) hung the browser's tab in `linearTicks` — fixed: such a span is one value, and `linearTicks` ends for every domain.
- T24: a precipitation total on the 1st of a monthly `o_d` archive after missing days at the end of the previous one stayed `value` (BORUCINO 2024-07-01, 13.1 mm), and status `Z` was never read — fixed: `series build` carries the missing days across archives and `Z` is `accumulated`; the stored `pl.imgw.meteo_precip_daily` series takes it in its next version (not rebuilt).
- T26: PMAXTP was called „probable maximum precipitation” / „opady maksymalne prawdopodobne” (that is PMP) and POT „recommended for most applications” without a source — fixed: the monograph's name, its advice (POT for p ≥ 50 %, AMP and POT equivalent below) and the grid product (kriged from 100 stations, may differ from a station's own estimate) in the messages, USAGE, the GUI and its guide, docstrings and the agent guide.
- Hydrolog's `hotfix/ml-fits` (T28): `low_flow.Q` may hold `null` quantiles (notice `negative_quantiles`) or end in `calculation_error` — the GUI's „Przepływy minimalne” leaves the points out of the curve and shows „–” with a note; exports, REST, CLI and the analyses build take `null` as it is. The stored analyses change when rebuilt with that Hydrolog.
- T32: `precipitation.heavy` took `percentiles` up to 100 inclusive, which Hydrolog refuses — fixed: `exclusive_maximum` 100.

### Release 3.2.0 (moved from PROGRESS on 2026-11-23)

Moved without changes: the branches of release 3.1.0 of PROGRESS „Working branch” and the items of release 3.2.0.

#### Release 3.1.0 on `develop` (PROGRESS „Working branch” until 2026-11-23)

`develop` held release 3.1.0: the fixes of the formula audit of 2026-11-18 (`fix/presentation`, merged `04c017f`; `fix/frost-days-title`, merged `c3587ae`), `fix/stale-current-flow` (`6599e65`) and the work of the release round of 2026-11-21: `feat/current-data-3.1.0` (`19e578b`), `feat/hydrolog-0.9.0` (`d05b45a`), `feat/gui-quick-3.1.0` (`11c52b7`, with the PMAXTP chart), `feat/chmi-snow-halfyears` (`8990056`, with the resumed analyses build and ČHMÚ's half-years), `feat/operator-instance` (`9b920f8`), `fix/3.1.0-findings` (`e68df87`: CORS, security headers, GEO-03, GEO-04, E3-01, E7-11), `fix/windows-instance` (`047aeda`), `feat/phone-sources-strip` (`64f6abb`), `feat/unified-symbols` (`50c7749`), `feat/national-provider-names` (`a4f98e0`), `chore/round-integration` (`135b443`) and `chore/copies-round` (`4bf0ce3`).

#### Release 3.2.0 (the author's decisions of 2026-11-20 and 2026-11-22)

The operational series and the providers' interface, by Nogat's plans `docs/plans/2026-11-16-operational-series.md` (O1–O4, O6, A2, A4 and `cz.chmu.hydro_hourly`; its step table holds every 3.2.0 step with its dependency and check) and `docs/plans/2026-11-20-hydromet-providers.md` (steps 2, 2a, 3, 4 and 5a), approved on 2026-11-23 by Fable for the author, after Nogat's step N0 (ECO-084, ECO-085, DEV-20.8 amended). Gdańskie Wody and the provider fed by files are 3.3.0 (the author, 2026-11-22). Archiwista's minor (A1) is deployed before the first hourly series reaches a shared data root (ECO-085).

- [x] `pl.imgw.meteo_details` (GEO-03 Q2, decided by the author on 2026-11-21: into v3.2.0) — done on `feature/meteo-details-3.2.0` (ADR-021, ADR-028 and ADR-030 errata of 2026-11-23): the meteorological map of hydro.imgw.pl (877 stations) and each station's page (`hydro-back.imgw.pl/station/meteo/status`) kept as a derived file of `id`, `coordinates` and `properties.altitude`; the IMGW-PIB catalog gives a meteo station `elevation_m` and, where the current-data API does not locate it, the page's point with `location_source` `pl.imgw.meteo_details`; RH with them. Its answers spool to the declared `pl.imgw.meteo_operational` and `pl.imgw.meteo_states_current` (`private`), served with O2. Operator, once merged: `obserwator store sync --root "$RAW" --datasets pl.imgw.meteo_details` (about 880 requests, a few minutes), then `store catalog`.
- [x] Provider adapters (plan P1, P2, step 2): `obserwator.providers`, one module per provider behind one `Protocol`; IMGW-PIB and ČHMÚ move onto it with the same bytes of archives, sidecars, series, catalogs, envelopes and AGENTS.md — done on `feature/provider-adapters-3.2.0` (ADR-029); each provider's catalog builder lives in its adapter's module (`feature/provider-catalogs-3.2.0`); the GUI's page still names IMGW-PIB for its current-data and PMAXTP views (P11–P13, `v3.3.0`).
- [x] Provider credentials and errors (P3, P4, step 3; step table row H3): `OBSERWATOR_<PROVIDER>_API_KEY` or `…_API_KEY_FILE` in `CREDENTIAL_KEYS`; a missing or rejected key is `forbidden` with `details.reason` `missing_credentials` or `invalid_credentials`. Done on `feature/provider-credentials-3.2.0`: `ProviderDescriptor.credential` (`ProviderCredential`), `config.provider_key`, `config.credential_error`, `config.credential_keys`, `config show`, `.env.example`; tested with a test-only provider (no provider of 3.2.0 needs a key). Nogat's copy `schemas/nogat/error_registry.json` still lacks the two reasons in `forbidden`'s meaning: the next copies round.
- [x] Hourly series (O4 with P5, step 4; ADR-031) — on `feature/hourly-series-3.2.0`: `pl.imgw.hydro_subdaily` and `cz.chmu.hydro_subdaily` (`time_unit` `hour`, `inputs`, tier `operational`), one version per month `series:<key>:<YYYY-MM>` with `time` and `<var>_tier` (only in a month of several tiers), the full hours of the closed UTC days of each capture (D9), the highest tier per station, variable and hour, `series build --start/--end`, `series read|summary|export` across months, `series_months`, `series select` refusing them, REST and the GUI hiding a private series, the GUI's series chart with hours and tiers, the night's and the telemetry's timers building the months they touched; tested on October 2026 recorded on 2026-11-23 (744 of 744). No series of 3.2.0 is aggregated by day; ČHMÚ groundwater's `recent` stays without a series (ADR-032 erratum). Archiwista's A1 accepts the new values before the first hourly series reaches a shared data root (ADR-031, Consequences).
- [x] ČHMÚ groundwater (H5a, plan P7, step 5a; ADR-032) — on `feature/chmu-groundwater-3.2.0`: `cz.chmu.groundwater_{daily,weekly}` (series; `time_unit` `week`, rows at reading dates), `_recent` (operational, stored without a series), `_characteristic` (statistics), `_stations` and `_now` (optional catalog sources), `_current` declared; kind `groundwater` with `groundwater_kind`, `H_asl`, `spring_yield`, `parse_chmu_groundwater`, the GUI's symbol, filter and panel; the fixture variant `groundwater` of ADR-032 D9 (a real bore and spring) and its tests (`test_groundwater_chmu.py`, `test_fixture_builder_chmu.py`, the GUI's `test_groundwater.py` in `tests/unit/gui` and `tests/e2e`). `recent` stays without a series in 3.2.0: O4's precedence of the tiers builds the hourly series only (ADR-031, ADR-032 erratum of 2026-11-23), and no current chart is drawn for a groundwater object. `recent`'s sidecars get `tier`/`publication` from H2a's writer on merge; Archiwista's A1 accepts the new values listed in ADR-032's consequences.
- [x] Captures and the operational tier (O1, ADR-030): `DatasetDescriptor.tier` (`verified`, `telemetry`, `operational`; every `datasets list` document carries it), the eleven datasets of the plans declared in the registry and offered by no surface until their step serves them (`datasets(pending=True)`), the publication defaults, the spool, the sidecar fields and the lock decided for the steps below; ADR-003 D4, ADR-013 D5 and D6 and ADR-015 D5 amended; ADR-025's step 6 moved to 3.3.0 (erratum).
- [x] Captures (H2a; P14–P16, step 2a; ADR-030 D3, D5–D7, D9 and its errata of 2026-11-23) — done on `feature/captures-3.2.0`: `ProviderAdapter.capture` writes every answer of a capture source to the spool `<state_dir>/obserwator/captures/<dataset>/<YYYY-MM-DD>/` (`obserwator.captures`; every request path goes through `fetch._keep`, so the `current` commands, the GUI's snapshots, the live station search and `store sync` of the station sources spool too); the six `pl.imgw.*_current` datasets are served and `store check|sync --datasets` of them seals each closed UTC day into one version `archive:<key>:<YYYY-MM-DD>.jsonl.gz` (`store/captures.py`); `current poll` (the 36th command, `[local]`) with each source's declared interval as a ceiling; `[obserwator.capture]` and `config show` `capture`; the sidecar fields `tier` and `publication`; REST and MCP over HTTP answer `not_found` for a `private` capture (`api/publication.py`). Built on it: O2's fetchers through `fetch._get`/`_archive_response` spool by themselves, and O2 moves `pl.imgw.hydro_operational`, `cz.chmu.hydro_recent` and `cz.chmu.hydro_current` into `_DATASETS` (sealing works for any `country_day` dataset); O3's `--start`/`--end` filter the closed days of `check_captures`, and the lock `store-sync.lock` is not built yet; O6 honours `captures.publication` in the GUI; A2's `obserwator-current.timer` runs `obserwator current poll` at :15.
- [x] Fetchers (O2; ADR-030 errata of 2026-11-23) — done on `feature/operational-fetchers-3.2.0`: `PacedSession` in `fetch.py` (spread to `--pace-until`, at least 5 s apart, backoff 60/120/240 s, three connection failures end the run, gzip); `store sync --pace-until HH:MM` harvests one of `pl.imgw.hydro_operational` (hydro-back's H, Q and T, 3.1.0's `User-Agent`, no `Referer`) and `cz.chmu.hydro_recent` for the last closed UTC day (`captures.harvest`, `HarvestReport`) and seals today's spool day with it; the telemetry checked by the datastore's listing (no HEAD), ČHMÚ's hourly years by listing and HEAD; seven datasets served (47; only `cz.chmu.groundwater_current` declared); REST guards every private source. Tested on answers recorded in `tests/fixtures/operational`; a live run of three stations (9 requests, 21 s apart) on 2026-11-23. The step's check of one live night on the test instance (at most one request per 5 s) is still to run.
- [x] `cz.chmu.hydro_hourly` (E10): ČHMÚ's validated hourly set, the verified tier of `cz.chmu.hydro_subdaily` (O2 serves it, O4 builds it over `recent`). R6 checked on the data at hand (ADR-031): HH of 2025 whole centimetres, QH two decimals; sample or rounded mean stays undecided without the 10-minute values of the same year, so R6 stays open.
- [x] `store check|sync --start/--end` and the lock (O3; ADR-030 D9, D10 and its errata of 2026-11-23) — done on `feature/store-sync-window-3.2.0`: UTC dates (AGI-3.4) narrowing the closed spool days, or with `--pace-until` the harvest's days (`--end` the last closed UTC day by default, `--start` at most `HARVEST_DAYS` = 40 days back; refusals `day_not_closed`, `harvest_reach`, `not_capture`, `store_only_option`); a `store sync` that seals captures holds `flock` on `<state_dir>/obserwator/store-sync.lock` for the whole run, waits 600 s, then `conflict` (`sync_locked`); archive syncs, checks and Windows take none. Tested in `test_store_sync_window.py` (a 40-day backfill on the recorded grid, the lock on a fake clock and across processes).
- [x] The chart of the current readings (O6; ADR-013, ADR-029, ADR-030 and ADR-031 errata of 2026-11-23) — on `feature/current-chart-3.2.0`: „Wykres godzinowy” in „teraz” of a hydrological station (H, Q, T over 3, 7, 30 days or the whole record; each tier in its line style, the live tail green, points for lone readings, IMGW-PIB's warning and alarm levels); the route `api/station/{code}/subdaily?from=` reading only the months of its range (`DataRoot.series_document(since=)`) and joining the live tail (`gui._live.LiveTail`: 10 min per station, 60 s after a failure, 500 stations, one live request of the server; answers to the spool, read by `store.subdaily.tail_hours`); `ProviderAdapter.live_source`; a station whose hourly series or live source is `private` answers `404` before any request and its document has `subdaily` false, so with the defaults ČHMÚ's hydrological stations have the chart and IMGW-PIB's once hydro-back is set `public`. Tested in `tests/unit/gui/test_current_chart.py` (fake clock and `FakeTail`) and `tests/e2e/test_current_chart.py` (Chromium at 1440 and 390 px).
- [x] Timers (A2; ADR-030 erratum of 2026-11-23) — done on `feature/timers-backups-3.2.0`: `deploy/systemd/` templates of `obserwator-night` (02:30: the harvests until 05:00 and 06:30 from the day after each one's last whole harvest, then the sealing of the other captures), `obserwator-telemetry` (06:45) and `obserwator-current` (hourly at :15), `Persistent=true`, confined by the install contract's unit rule, run through `deploy/obserwator-jobs.sh`; the compose service `jobs`; USAGE.md „Timers”. Checked: `systemd-analyze verify`, the night, telemetry and poll `--check` and one real poll under the user manager and in Docker. The real night is D1's.
- [x] Backups (A4) — done on `feature/timers-backups-3.2.0`: `deploy/obserwator-backup.sh` and `obserwator-backup.timer` (Sundays 07:00): weekly `--link-dest` snapshots, the month's first a full copy with its restore test (`restore-test.log`, a `backup_restore_test` record), 8 and 6 kept, the 15 % guard; USAGE.md „Backups”, README (DEV-18.5). Checked on the author's NAS (CIFS) with fixture roots: the second weekly holds only the new file as a new inode. The first run belongs before the first night (D1).

### Decided questions

- **`/mcp` on the public server (the author's decision of 2026-11-09).** Off by default: `OBSERWATOR_MCP_ENABLED=false` stays in `Settings`, `.env.example` and `docker/docker-compose.yml`, and an operator enables `/mcp` explicitly (ADR-004, open question 2).


---

## Commands

```bash
# Tests (always via the project venv)
.venv/bin/python -m pytest
.venv/bin/python -m pytest --cov=imgwtools

# Linting and formatting
.venv/bin/ruff check src/ tests/
.venv/bin/ruff format --check src/ tests/

# Type checking (config: [tool.pyright] in pyproject.toml)
npx -y pyright src/imgwtools/

# Agent guide (derived files; after every change to the catalog, registries or templates)
imgw commands guide --format agents --lang pl --path AGENTS.md
imgw commands guide --format llms --lang pl --path llms.txt
```

---

## Git workflow

- **main** - default branch (stable)
- **develop** - development branch (v2.2.0)
- **feature/versioned-store** - versioned store and consistent interfaces, release 3.0.0
- **feature/chmi-agents** - ČHMÚ provider and AI agent support, release 3.0.0
