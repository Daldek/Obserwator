# Obserwator — Codebase Reference

Code and module reference moved out of [CLAUDE.md](../CLAUDE.md) (Nogat standard 1.0, DOC-3.2): package tree, public library API, command catalog, data sources and formats, deployment, versioned store. Architecture and component diagrams: [ARCHITECTURE.md](ARCHITECTURE.md); tests: [TESTING.md](TESTING.md); task-oriented usage: [USAGE.md](USAGE.md).

## Package Tree

```
src/obserwator/
├── __init__.py           # PUBLIC API - single __all__ (spec §13.12, ČHMÚ spec §9.1, agent_guide)
├── _version.py           # Version, single source (`[tool.hatch.version]` in pyproject.toml)
├── fetch.py              # PUBLIC: live data (fetch_*), PMAXTP, download_archives, download_*_data
├── models.py             # PUBLIC: Data models (PMaXTPData, HydroCurrentData, NormalizedRecord, Measurement, ...)
├── stations.py           # PUBLIC: find_stations (live lists of IMGW-PIB and ČHMÚ, or the current catalogs of a data root)
├── datasets.py           # PUBLIC: Provider registry (providers, get_provider) + 22 dataset descriptors, archive_files
├── commands.py           # PUBLIC: Command catalog (35 commands, PL + EN texts, effects), run_command, command_schema, list_commands
├── agent_guide.py        # PUBLIC: agent_guide (AGENTS.md / llms.txt), MCP server instructions
├── coverage.py           # PUBLIC: summarize_coverage (per-station periods for ČHMÚ)
├── exceptions.py         # PUBLIC: ObserwatorError hierarchy + ERROR_CODES registry (title as a catalog message)
├── error_report.py       # PUBLIC: obserwator-error/1 document (ErrorReport, error_document, error_report, error_hint)
├── messages/             # Message catalog: message(), Message, localize(), one module of Text(en, pl) per area (ADR-006; analyses.py: titles and errors of the analyses)
│   └── gui/              # The GUI's texts (area gui, one module per part of the page), served by api/texts
├── urls.py               # PUBLIC: IMGW URL constants, build_pmaxtp_url, build_api_url
├── parsers.py            # PUBLIC: Parser re-exports (IMGW-PIB hydro/meteo, ČHMÚ, station lists)
├── testing.py            # PUBLIC: build_fixture_store (complete, complete_pl_cz, ...) → FixtureRoots(raw, data), fixture_files
├── _jsonable.py          # Single JSON converter (envelope, relative store paths)
├── _environment.py       # nogat.toml, NOGAT_* variables, user directories (DEV-18.1); [nogat.gui] (gui_addresses), [nogat.operator] (operator); credential keys
├── _borders.py           # The packaged state borders (border, PROVIDERS): PRG (GUGiK) and RÚIAN (ČÚZK), written only by scripts/build_borders.py (ADR-018); standard library only
├── attribution.py        # Provider attribution and terms lines of every product (ADR-012): attribution, carried, origins imgw, imgw_hydro, pmaxtp, chmi, gugik (G), cuzk (Z)
├── _examples.py          # Example calls of the catalog (examples of command_schema): canonical line + result excerpt
├── output.py             # Plain output (ADR-007): resolve_target, plan_plain, refuse, Staging, FileResult, OutputReport, STORE_MARKERS, DATA_MARKER
├── reference_data.py     # python -m obserwator.reference_data (reference files in OBSERWATOR_REFERENCE_DIR)
├── config.py             # Settings (pydantic-settings, OBSERWATOR_*), log_dir = <state_dir>/obserwator/logs, store_root, check_config, environment_report (config show)
├── nogat_logging.py      # Nogat's reference module, copied byte for byte (DEV-12.9): ServerLog, AccessLog of both servers; never edited
├── _hydrolog.py          # Hydrolog's program (setting hydrolog_command): open_hydrolog, Hydrolog.batch (`commands batch` in a separate process; ADR-016)
├── _data/                # Poland/Czechia borders (PRG, RÚIAN; ADR-018), agents/ guide templates, packaged fixtures
├── _parsing/             # common.py, hydro.py, meteo.py, stations.py, chmi.py (ČHMÚ files, listings, metadata)
├── store/                # Versioned store in two roots, raw and data (ADR-017) [Parquet: obserwator[store]]
│   ├── types.py          # Dataclasses: StorePlan, CommandResult, Page, StoreEntry, StoreHandle, ...; RootKind
│   ├── writer.py         # init_store (raw or data root), open_store, write_archive (atomic, append-only, content_unchanged + observations)
│   ├── content.py        # Canonical content forms (chmi-json/1), content_sha256
│   ├── sync.py           # check_store, sync_store (IMGW-PIB: listing + HEAD; ČHMÚ: directory listing)
│   ├── series.py         # check_series, build_series (Parquet in the data root, from the archives of the raw root)
│   ├── catalog.py        # check_catalog, build_catalog (stations.geojson per provider in the data root, from the station sources of the raw root)
│   ├── pmaxtp.py         # check_pmaxtp, sync_pmaxtp, read_pmaxtp
│   ├── reader.py         # store_info, iter_store, current_version, read_*, select/summarize_series
│   ├── export.py         # export_archive, export_series (CSV/JSON/Parquet), export_stations (GeoJSON/CSV); ADR-014
│   ├── analyses.py       # build_analyses, check_analyses, list/read/export_analyses, compute_analysis (Hydrolog's answers, ADR-016)
│   ├── analysis_registry.py # The 87 analyses: AnalysisDefinition (variants, picks, overridable, locked, rounds), definitions_digest
│   └── plain.py          # plain_actions: the obserwator-plan/1 actions of a plain write
├── api/                  # FastAPI REST API [optional: obserwator[api]]
│   ├── main.py           # App entry point (/health, /api/v1, /llms.txt, /docs, /mcp; GET / redirects to /docs)
│   ├── routes/commands.py# Routes generated from the catalog (commands._input_schemas, x-obserwator.rest), Accept-Language (English by default)
│   ├── errors.py         # application/problem+json handlers, hide_server_paths, accept_language
│   └── schemas.py        # HealthCheck
├── cli/                  # Typer/Click CLI [optional: obserwator[cli]]
│   ├── main.py           # Entry point (obserwator command): version, server, mcp, gui, admin, config + catalog groups
│   ├── gui_cmd.py        # obserwator gui serve (outside the catalog, ADR-013)
│   ├── config_cmd.py     # obserwator config show (outside the catalog, DEV-18.6)
│   ├── _dispatch.py      # ObserwatorGroup + register_catalog: the only CLI adapter of the catalog (OBSERWATOR_LANG)
│   ├── _render.py        # Summary for a person of the envelope (without --json): one renderer, key-field hints
│   └── admin.py          # REST API key management (api_keys.json; not the GUI's admin key)
├── mcp/                  # MCP adapter [optional: obserwator[mcp]]; not in obserwator.__all__
│   ├── _tools.py         # Tools from the catalog (modes read/write/http, schemas, annotations)
│   ├── _calls.py         # Calls: stdio (check_command/run_command), http (REST routes in process)
│   └── server.py         # create_server, run_stdio, http_app
└── gui/                  # Web GUI [optional: obserwator[gui]]: obserwator gui serve, entry point nogat.gui (ADR-013); not in obserwator.__all__
    ├── __init__.py       # create_app, serve, gui_module, GuiModule, WEB_DIR, SECTIONS (imports neither Starlette nor uvicorn)
    ├── _extra.py         # require_gui_extra: missing_dependency without Starlette, uvicorn or pyarrow
    ├── _config.py        # GuiConfig.resolve: root, own directory (gui_dir), basemap, rate limit, [nogat.gui], [nogat.operator]
    ├── _serving.py       # uvicorn: binds, starts the ServerLog (record start with the address), stops on Ctrl+C or SIGTERM; no uvicorn log
    ├── _app.py           # Starlette app: the private API's routes (the files of export_series, export_stations and export_analyses at api/files/series, stations, analyses; POST api/feedback), the admin panel (admin/, api/admin/…), SecurityHeaders (headers, CSP, methods), QUIET, build_app (AccessLog outermost when given a ServerLog)
    ├── _http.py          # JSON answers with strong ETags, attachments, obserwator-error/1 in the page's language without server paths
    ├── _params.py        # Checks of every query and path parameter before the root or Hydrolog is touched
    ├── _state.py         # GuiState: the parts of a running app
    ├── _root.py          # DataRoot: the data root read-only, current versions asked again at most once a minute
    ├── _live.py          # IMGW-PIB snapshots (10 min) and PMAXTP points (24 h), in memory only
    ├── _analyses.py      # Analyses: Hydrolog's stored results (list_analyses, read_analysis); a person's choices by compute_analysis (program looked for once at the start, 2 processes, 30 s, 500 results)
    ├── _stripes.py       # Climate stripes (M15): the prototype of their colour scale
    ├── _traffic.py       # Traffic: rate limit and daily totals (stats.jsonl; Nogat DEV-15.9, DEV-15.11)
    ├── _feedback.py      # POST api/feedback: „Zgłoś uwagę” reports in feedback.jsonl, next id in feedback.next_id (DEV-15.12), rewritten atomically under flock
    ├── _admin.py         # The admin panel's API (DEV-15.13): X-Admin-Key, api/admin/feedback|stats|status
    ├── _terms.py         # regulamin.html: the terms of Nogat's kit (web/nogat/nogat-terms.html, kit 0.7.0) filled for the deployment (DEV-15.7)
    └── web/              # The page (package data): index.html, theme-init.js, src/ (Preact + htm modules: map, list, panel, sections/, charts/, pmaxtp/, ui/), css/, vendor/ (Preact, htm, MapLibre GL JS, glyphs), nogat/ (tokens, marks, kit 0.7.0), admin/ (the admin panel, <nogat-admin>), instrukcja/ (the guide in Polish)

AGENTS.md, llms.txt       # Agent guide — DERIVED files: regenerate with `obserwator commands guide` (drift test)
```

## CLI Examples

```bash
# CLI examples (stdout: a summary for a person; with --json the one-line envelope obserwator-result/1)
obserwator version                                   # Show version
obserwator server --host 0.0.0.0 --port 8000         # Run API server
obserwator gui serve --root /dane/obserwator --no-browser  # Web GUI on 127.0.0.1:8060 (obserwator[cli,gui])
obserwator datasets list -k hydro                    # Dataset registry
obserwator datasets files -d hydro/dobowe -y 2023 -m 1  # Archive URLs (no download)
obserwator datasets download -d hydro/dobowe -y 2023 -m 1 -o dane  # Download archives
obserwator stations find -k hydro -q wisla --limit 20  # Search station lists
obserwator current hydro -s 150160180                # Current hydro data
obserwator current warnings -k meteo                 # Warnings
obserwator pmaxtp fetch --lat 52.23 --lon 21.01      # PMAXTP data (method POT)
obserwator store init --root /dane/obserwator-raw    # Raw root (archives, station sources, PMAXTP)
obserwator store init --kind data --root /dane/obserwator  # Data root (series, catalogs, analyses)
obserwator store sync --root /dane/obserwator-raw -d pl.imgw.hydro_daily -y 2024 --check  # Plan only
obserwator series build --root /dane/obserwator --raw-root /dane/obserwator-raw -d hydro/dobowe
obserwator series summary --root /dane/obserwator -d hydro/dobowe -s 149180020
obserwator datasets providers                        # IMGW-PIB and CHMI
obserwator stations find -k hydro -q spindleruv --provider CHMI  # ČHMÚ station (WIGOS id)
obserwator store check --root /dane/obserwator-raw -d cz.chmi.hydro_daily -s 0-203-1-001000 -y 2024-2025  # ČHMÚ listing check
obserwator store catalog --root /dane/obserwator --raw-root /dane/obserwator-raw --provider CHMI  # ČHMÚ station catalog
obserwator commands schema --command "store sync" --json  # obserwator-commands/1 of a command
obserwator commands schema --command "store sync" --lang pl  # Readable, Polish texts
obserwator store sync --schema                       # Same, via the command itself
obserwator commands guide --format agents --output AGENTS.md --force  # Regenerate AGENTS.md (English)
obserwator mcp [--allow-writes --allow-dir DIR]      # MCP server on stdio, English; writes only inside --allow-dir (obserwator[mcp])
obserwator admin keys                                # List REST API keys
obserwator admin create --name "User1"               # Create a REST API key
obserwator admin revoke <key_id>                     # Revoke a REST API key
obserwator admin delete <key_id>                     # Delete a REST API key
obserwator admin stats                               # Show REST API key statistics
```

## Public Library API

The public API is exposed via `from obserwator import ...` (one `__all__`, also re-exported from the defining modules). The first object argument may be positional; every further argument is keyword-only. Station codes are always `str` (`station_code`): 9 digits for IMGW-PIB, a WIGOS id for ČHMÚ (`STATION_CODE_PATTERN`).

**Live Data and Downloads:**
|Function|Description|
|---|---|
|`fetch_pmaxtp(latitude, longitude, *, method="POT")`|Get PMAXTP precipitation data (`PMaXTPResult`)|
|`fetch_hydro_current(*, station=None)`|Current hydro data (`HydroCurrentData`)|
|`fetch_meteo_current(*, station=None)`|Current meteo data (`MeteoCurrentData`)|
|`fetch_synop(*, station=None, station_name=None)`|Current synop data (`SynopData`)|
|`fetch_warnings(*, kind=None)`|Hydro/meteo warnings (`WarningData`; `None` = both)|
|`fetch_hydro_states(*, main_only=False)`|Hydro stations with coordinates and water state (`HydroState`)|
|`find_stations(*, kind=None, query=None, source="live", root=None, provider=None)`|Search IMGW-PIB and/or ČHMÚ station lists live, or with `source="store"` the current catalogs of the data root `root` (offline; `short_code` None; no catalog → `not_found` with the `store catalog` hint) (`StationListEntry`)|
|`download_archives(dataset, /, *, years, months, params, stations, output_dir, root, force)`|Download archives as plain files named by the provider's server path (`output_dir`) or into the raw root (`root`; neither = the default raw root) (`DownloadReport`: `mode`, `output_dir`, `root`, `files[]`; ČHMÚ 404 → `not_published`)|
|`download_hydro_data(interval, year, month, param)`|One hydro archive as `DownloadResult` (bytes in `.data`)|
|`download_meteo_data(interval, subtype, year, month)`|One meteo archive as `DownloadResult`|

Every live function but `download_archives` has an `*_async` twin with identical arguments (`find_stations_async`, `fetch_hydro_states_async`, `download_hydro_data_async`, ...).

**Registry and URLs:**
|Function|Description|
|---|---|
|`providers()`, `get_provider(id or key_prefix)`|Provider registry (`ProviderDescriptor`: `IMGW-PIB`, `CHMI`)|
|`datasets(*, kind=None, provider=None)`|Dataset descriptors (`DatasetDescriptor`; 22)|
|`get_dataset(dataset)`|Descriptor by key, slug or legacy alias|
|`archive_files(dataset, /, *, years=None, months=None, params=None, stations=None)`|Archive files with URLs (`ArchiveFile`; `stations` required for `cz.chmi.*`)|
|`station_source_files(*, provider="IMGW-PIB")`|The two station lists of a provider as `ArchiveFile`s (hydro, meteo): IMGW-PIB `lista_stacji_hydro.csv`, `wykaz_stacji.csv`; ČHMÚ the two `historical` `meta1.json`|
|`build_pmaxtp_url(latitude, longitude, *, method="POT")`|PMAXTP API URL|
|`build_api_url(endpoint, /, *, station, station_name)`|IMGW real-time API URL|

**Versioned Store** (also in `obserwator.store`):
|Function|Description|
|---|---|
|`init_store(root, /, *, kind="raw", created_at=None)`, `open_store(root, /, *, kind=None)`, `store_info(root, /)`|Create, open or describe a root (ADR-017): `kind="raw"` writes `obserwator-store.json`, `kind="data"` `obserwator-data.json`; `open_store` without `kind` opens either and `StoreHandle.kind` tells which; `store_info` takes either (`store_schema` `obserwator-store/1` or `obserwator-data/1`) and does not raise for a root that is no store: `StoreInfo.problems` has a code in `problem_codes` for each problem (`missing_store`, `missing_marker`, `invalid_marker`, `unsupported_store`, `conflicting_markers`); `StoreInfo.contracts` has the keys `store`, `data`, `meta`, `series`, `plan`, `pmaxtp`, `observation`, `analyses`|
|`RootKind`, `StoreHandle(root, schema)`|`RootKind = Literal["raw", "data"]` (also in `obserwator`); `StoreHandle.kind` is `"raw"` for `obserwator-store/1`, `"data"` for `obserwator-data/1`. A function given a root of the other kind than it needs raises `ObserwatorStoreError` (`store_unavailable`, `details.reason="wrong_root"`, `details.kind` the kind needed)|
|`iter_store(root, /, *, kind=None, provider=None, skip_versions=None)`|Scan every version (`StoreEntry.meta` is a `Meta`, with `producer` and `producer_version`), observation and problem of a root, by its marker: a raw root gives `archive`, `observation`, `pmaxtp` and `problem` entries, a data root `series`, `catalog`, `analyses` and `problem` entries; a tree of the other kind is an `unknown_entry` problem and `kind=` of the other kind gives nothing; `skip_versions` (Python only) maps the version directory of each version a consumer knows, relative to the root, to its data file names: it comes back `skipped=True` without `meta`, neither listed nor read (incremental scan)|
|`store_root(*, kind="data")`|The default root of a kind without reading it: `StoreRoot(root, source, name, marker_exists)`; the data root is `OBSERWATOR_ROOT`, `[obserwator] root` or `<data_dir>/obserwator`, the raw root `OBSERWATOR_RAW_ROOT`, `[obserwator] raw_root` or `<data_dir>/obserwator-raw` (DEV-19.2, ADR-017; Kartograf has the same function)|
|`check_store`, `sync_store`|Raw root: freshness plan (IMGW-PIB: listing + HEAD; ČHMÚ: one directory listing, `stations`; `series_state` `{}`) and download of new/missing archives; `sync_store(root=None, *, output_dir=None, force=False, ...)` writes plain files with `output_dir` (no `plan`, no series)|
|`write_archive(root, /, *, archive, response, on_progress=None, on_notice=None, cancel=None)`|Commit one downloaded file (`DownloadResult`) and its `*.meta.json` sidecar as a version `<label>_<sha8>` of the raw root, published by hard links, the sidecar last, never replacing a version (`VersionResult`; equal canonical content → `unchanged` + an observation, ADR-003)|
|`build_series(root, /, *, raw_root, dataset, on_progress=None, on_notice=None, cancel=None)`, `check_series(...)`|Parquet station series in the data root `root`, built from the current archive versions of the raw root `raw_root` (keyword-only, required; only read: no marker, staging or clean-up there); `SeriesReport.source_files` and the plan items name files of the raw root|
|`build_catalog(root, /, *, raw_root, provider="IMGW-PIB", user_locations=None, ...)`, `check_catalog(...)`|`stations.geojson` catalog of one provider (`"IMGW-PIB"` default, `"CHMI"`) in the data root `root`, built offline from the station sources of the raw root `raw_root` and the series indexes of the data root|
|`check_pmaxtp`, `sync_pmaxtp`, `read_pmaxtp`|PMAXTP grid cells of the raw root|
|`current_version(root, /, *, slot)`|Current version of a slot; the slot decides the kind of root: `archive:<key>:<file>`, `pmaxtp:…` raw; `series:<key>`, `catalog:<prefix>.stations`, `analyses:<prefix>.analyses` (`analyses:pl.imgw.analyses`, `analyses:cz.chmi.analyses`) data|
|`read_meta`, `read_archive`, `read_station_list(root, /, *, kind, provider="IMGW-PIB")`, `read_catalog(version=None, /, *, root=None, provider=None)`, `read_series_index`, `read_series`|Offline readers (`read_archive` and `read_station_list` of the raw root, `read_catalog` and the series readers of the data root)|
|`select_series`, `summarize_series`|Series selection and coverage (data root)|
|`export_archive`, `export_series`|CSV/JSONL export of an archive version; one station's series as CSV, JSON (`obserwator-series-export/1`) or Parquet (needs `output`); a line iterator, or with `output` (+ `force`) one plain file and its `OutputReport`|
|`export_stations`|The stations of the current catalogs as GeoJSON (`obserwator-stations-export/1`, RFC 7946) or CSV, with the series that hold them (ADR-014; schemas in `schemas/`)|

**Offline fixture roots** (`obserwator.testing`, outside `obserwator.__all__`; ADR-017 D9): `build_fixture_store(root, *, data_root, variant="complete") -> FixtureRoots` builds a raw root at `root` (archives, station sources) and the data root built from it at `data_root` (series, catalogs) with the public writers and recorded answers, without the network; `FixtureRoots(raw, data)` is a frozen dataclass of the two `StoreHandle`s. Variants: `complete`, `complete_pl_cz` (ČHMÚ too), `corrupt` (a sidecar of the raw root truncated) and `unknown_schema` (a series version of `/2` in the data root).

**Stored Analyses** (ADR-016; also in `obserwator.store`; every number is Hydrolog's, run through the setting `hydrolog_command`, else `hydrolog` on `PATH`):
|Function|Description|
|---|---|
|`analysis_definitions(kind=None)`|The registry: 87 `AnalysisDefinition` (59 `hydro`, 28 `meteo`) with `id`, `kind`, title key, Hydrolog `command`, `options`, `variants` (`AnalysisVariant`, `AnalysisInput`), `picks` (`AnalysisPick`), `overridable` (`AnalysisOption` with type and bounds), `depends_on`, `level` (round), `locked`; `kind` other than `hydro`/`meteo` → `validation_error`|
|`build_analyses(root=None, /, *, stations=None, workers=1, on_progress, on_notice, cancel)`, `check_analyses(...)`|Compute every station of the data root with Hydrolog and store one version per provider there (no raw root is read; `AnalysesReport` `obserwator-analyses-report/1`: `status`, `hydrolog_version`, `providers[]` = `ProviderAnalyses` with `new`/`unchanged`/`cancelled`/`failed`, `computed`, `carried`, `results_ok`, `results_failed`); carry-forward by hard links on an equal fingerprint; the check is an `obserwator-plan/1` of the stations to compute and carry|
|`list_analyses(version=None, /, *, root=None, station)`|`AnalysisSummary` (`obserwator-analysis-summary/1`) per stored analysis of a station: command, options, `inputs` (`AnalysisSource`: dataset, series version, SHA-256s), status, `error_code`, versions, attribution|
|`read_analysis(version=None, /, *, root=None, station, analysis)`|`AnalysisResult` (`obserwator-analysis/1`): the summary with Hydrolog's `envelope` (`hydrolog-result/1`) or `error` (`hydrolog-error/1`) as stored|
|`export_analyses(version=None, /, *, root=None, station, analyses=None, format="json", output=None, force=False, ...)`|`json`: one `obserwator-analyses-export/1` line; `csv`: one row per scalar leaf of `result` (`path` a JSON Pointer) with the attribution columns; a line iterator, or with `output` one plain file and its `OutputReport`|
|`compute_analysis(root=None, /, *, station, analysis, options=None, timeout=30.0, cancel=None)`|One analysis on the fly with a person's overridable options (of it or of its dependencies, minus `locked`); `stored=False`, nothing written; not a catalog command|

**Command Catalog:**
|Function|Description|
|---|---|
|`command_schema(command=None, /, *, lang="en")`|`obserwator-commands/1` (Nogat `commands-1`) of one command or the whole catalog: `name`, `operation_id`, `function`, `summary`, `description`, `options` (type, `enum` with meanings, bounds, `path_role`, `flags`), `result`, `effects`, `check`, `rules`, `examples`, `errors`, `i18n.pl`, plus `group`, `result_type`, `rest`; `lang="pl"` = Polish texts|
|`list_commands(*, lang="en")`|Catalog summary `obserwator-command-list/1` (`tool`, `version`, `groups`, `commands`): per command the `name`, `operation_id`, group, one-sentence summary, `read_only`, `check`, effects, result and REST route (`obserwator commands list`, MCP `obserwator_commands_list`)|
|`data_commands(*, provider=None)`|Catalog entries (`DataCommand`; `provider` = view of one provider)|
|`validate_command(command, /, *, options)`|Normalized options or `ObserwatorValidationError` with `details.option`|
|`format_command(command, /, *, options, run=None)`|Canonical CLI command line of a call; `run={"check": True}` adds `--check`|
|`parse_command(line, /)`|An `obserwator` line (text or words) → `CommandCall(command, options, run)` with the texts the CLI passes (`run`: `check`); a mistake of the line is `validation_error`, `details.reason="usage"`|
|`command_for_version(version, *, root=None, raw_root=None)`|Offline, read-only: the `CommandCall` that fetches or builds a stored version again, from its sidecar and the layout. The first directory of `version` gives the kind of its root (`archives/`, `pmaxtp/` raw; `series/`, `stations/`, `analyses/` data); a relative `version` lies in `root`, else in the default root of its kind, an absolute one in `root` or its nearest ancestor with a marker (directory, main file, sidecar, PMAXTP `response.json`, a series or analyses station file); the shape `parse_command` gives, with the absolute `root`. Archives → `store sync` (IMGW-PIB `--datasets --years [--months]`, ČHMÚ `--datasets --stations [--years]`), station lists and station metadata → `store sync --datasets <key>` (ADR-015), catalogs → `store catalog --raw-root <raw> --provider`, series → `series build --raw-root <raw> --dataset`, analyses → `analyses build`, PMAXTP → `pmaxtp sync` of its point and cell; `<raw>` is `raw_root`, else the default raw root (ADR-017 D6). Refusals: `unsupported` with `details.reason="command_not_rebuildable"` (catalog built with `user_locations`, sidecar without a needed field, a file `store sync` does not select), `not_found`, `data_error`, `store_unavailable` (`wrong_root`), `validation_error` (a version in no root); ADR-008|
|`run_command(command, /, *, options)`|Run a command → `CommandResult` (list commands → `Page`)|
|`check_command(command, /, *, options)`|Plan of a command without side effects → `CommandResult`|
|`agent_guide(*, format="agents", lang="en", output=None, force=False)`|Agent guide `AGENTS.md`/`llms.txt`: line iterator, or with `output` one plain file and its `OutputReport`|

**Data Models:**
|Model|Description|
|---|---|
|`PMaXTPData`|Precipitation quantiles (ks, sg, rb) with `get_precipitation(duration_minutes, probability_percent)`, `get_confidence_bound` and `get_estimation_error`; the probability is a number, one of the 27 published percentages 0.01 to 99.9 (`50` and `50.0` are one key), any other number is `validation_error` with `details.allowed`|
|`PMaXTPResult`|Complete PMAXTP result with metadata|
|`HydroCurrentData`, `MeteoCurrentData`, `SynopData`|Current measurements (`station_code`)|
|`WarningData`|Weather/hydro warning (`kind`, `event`, `level`, ...)|
|`HydroState`|Station with coordinates and `water_state`|
|`StationListEntry`|Station list row (`kind`, `station_code`, `name`, `provider`, ...)|
|`NormalizedRecord`, `Measurement`|Normalized archive/series record with value flags (`Measurement.quality`, `source_flag` for ČHMÚ meteo)|
|`ProviderDescriptor`|Data provider: id, names, country, key prefix, base URL, license, station code pattern, datasets|
|`CommandResult`, `Page`|Result envelope (`obserwator-result/1`: `tool`, `version`, `result` a document or a list of them, `notices` `{level, code, message}`, `page`) and the paging of a list command (`total`, `next_cursor`, `truncated`)|
|`CommandCall`|A command line read by `parse_command` (or rebuilt by `command_for_version`): `command`, `options`, `run`|
|`FileResult`, `OutputReport`|One written file `{path, size_bytes, sha256, status}` and the result of an export `{output, files[]}`|

**Exceptions** (every `ObserwatorError` has `code` from `ERROR_CODES` and `details`):
|Exception|Default code|Description|
|---|---|---|
|`ObserwatorError`|`internal_error`|Base exception|
|`ObserwatorValidationError`|`validation_error`|Input validation errors (e.g. coords outside Poland)|
|`ObserwatorConnectionError`|`source_unavailable`|Connection/timeout/HTTP errors|
|`ObserwatorDataError`|`data_error`|Data parsing errors|
|`ObserwatorStoreError`|`store_unavailable`|Bad/unsupported root or a root of the other kind (`details.reason="wrong_root"`; `not_found` for missing versions)|
|`ObserwatorStoreConflictError`|`conflict`|Collisions, races, non-atomic filesystems|
|`ObserwatorStoreDependencyError`|`missing_dependency`|pyarrow missing|
|`ObserwatorCancelledError`|`cancelled`|Cancelled operation|

**Parsers:** `parse_zip_file(zip_data, interval)`, `parse_daily_csv`, `parse_monthly_csv`, `parse_semi_annual_csv`, `parse_stations_csv(content, /, *, kind)`, `parse_meteo_climate_daily`, `parse_meteo_precip_daily`, `parse_chmi_hydro_daily`, `parse_chmi_meteo_daily`, `parse_chmi_stations`, `normalize_archive`, `IMGW_ENCODING` (CP1250).

## Key Module: `commands.py`

The command catalog is the single source of options, validation, help texts and result types:
- `_CATALOG` — 35 `DataCommand` entries (spec §13.3 without the `project` group + `datasets providers` + `commands list` + `commands guide` + `stations export` of ADR-014 + the four `analyses` commands of ADR-016), each calling exactly one public function; every text (`description`, `help`, `rules`, group titles) is an English catalog message of `messages/commands.py` with its Polish variant (`localize(text, "pl")`); the first sentence of a description is the `summary` of `commands list` (at most 100 characters); each entry with a root names its kind (`root="raw"|"data"`, ADR-017)
- `command_schema(lang=)` — `obserwator-commands/1` (Nogat `commands-1`, validated against `schemas/nogat/commands-1.schema.json` by `tests/contract/test_commands_catalog.py`): an entry per command, plus `groups`, `errors`, `exit_codes`, `lang` for the whole catalog; `operation_id` is `obserwator_<group>_<verb>` (ECO-018): the MCP tool name and the REST `operationId`; the `errors` of an entry follow from its declared effects (`_errors`)
- `_input_schemas(lang)` — internal JSON Schema 2020-12 of the options per command with `x-obserwator` (`function`, `check`, `result_type`, `cli.flags`, `rest.method/path/server_options/local_options`, `rules`, `writes`, `network`, `idempotent`, `operation_id`): the source of the CLI, REST, MCP input schemas and the agent guide
- `run_command`/`check_command` — dispatch by `inspect.signature`, paging (`limit`/`cursor`, opaque URL-safe base64 of the next index) for the 13 list commands, notices deduplicated in the envelope; every result type names its document in `SCHEMA` (`obserwator-<kind>/1`), written first by `_jsonable`
- CLI (`cli/_dispatch.py`), REST (`api/routes/commands.py`) and MCP tools (`mcp/_tools.py`) are generated from the catalog (`_input_schemas`); never add hand-written commands there
- Changing catalog texts, the dataset/provider/error registries or the templates in `_data/agents/` requires regenerating `AGENTS.md` and `llms.txt` in the same change (`obserwator commands guide --format agents --output AGENTS.md --force`, `--format llms --output llms.txt --force`); `tests/unit/test_agent_guide.py` compares the bytes

## External Data Sources

### Station Lists (CSV)
- **Hydro stations**: `https://danepubliczne.imgw.pl/data/dane_pomiarowo_obserwacyjne/dane_hydrologiczne/lista_stacji_hydro.csv`
  - Format: `ID, nazwa, rzeka (id_cieku), kod`
  - Encoding: CP1250
- **Meteo stations**: `https://danepubliczne.imgw.pl/data/dane_pomiarowo_obserwacyjne/dane_meteorologiczne/wykaz_stacji.csv`
  - Format: `ID, nazwa, kod`
  - Encoding: CP1250

### Real-time API
- **Hydro data**: `https://danepubliczne.imgw.pl/api/data/hydro` (also `pl.imgw.hydro_now`: `store sync` keeps each station's code, name, river and coordinates for the catalog, never the measurements; ADR-015 D5)
- **Meteo data**: `https://danepubliczne.imgw.pl/api/data/meteo` (also `pl.imgw.meteo_now`, likewise)
- **Synop data**: `https://danepubliczne.imgw.pl/api/data/synop`
- **Warnings**: `https://danepubliczne.imgw.pl/api/data/warningshydro`, `.../warningsmeteo`

### Map Stations API
- **Hydro stations with coordinates**: `https://hydro-back.imgw.pl/map/stations/hydrologic?onlyMainStations=false`
  - Requires headers: `User-Agent`, `Referer: https://hydro.imgw.pl/`
  - Returns: 900+ stations with lat/lon and water state (alarm, warning, high, medium, low, etc.)
  - Public access: `fetch_hydro_states()`, `obserwator current hydro-states`, `GET /api/v1/current/hydro-states`
- **Hydro station details** (`pl.imgw.hydro_details`, ADR-021): `https://hydro-back.imgw.pl/station/hydro/status?id=<code>`, the data of a station page of hydro.imgw.pl
  - Same headers (`User-Agent: Obserwator/<version>`, `Referer: https://hydro.imgw.pl/`; without the Referer the backend answers 403); an unknown code answers `200` with `null`
  - `store sync` asks the map above for the codes, then each station once, in map order and one request at a time (about 910 requests, a few minutes); a `null` answer is skipped, any HTTP error fails the item (`source_unavailable`, nothing written, no retries); `cancel` is polled before each station
  - Kept (dotted `kept_fields`, a derived JSON list sorted by `id`): `id`, `properties.{maximumStateValue, maximumStateDate, minimumStateValue, minimumStateDate, district, waterGaugeZeroOrdinate, waterGaugeZeroOrdinateReferrenceSystem, yearOfEstablishment}`, `status.{riverCourseKm, catchmentArea, province, alarmValue, warningValue}`; never the water states and trends (operational, DEV-20.8), `status.notes`, `properties.dataClause`, the internal `status.id` or the coordinates
  - No freshness signal (`update_signal="none"`): `store check` → `unverifiable`, `store sync` always downloads; license = the hydro.imgw.pl terms (`https://hydro.imgw.pl/#/regulamin`), lines S, P, RH
  - Catalog properties of IMGW-PIB features (optional source of `store catalog`): `established_year`, `gauge_zero_m` (0 → null), `gauge_zero_datum` (only with a gauge zero), `river_km`, `catchment_area_km2` (0 → null), `province`, `district`, `warning_level_cm`, `alarm_level_cm`, `absolute_min_level_cm`, `absolute_min_level_dates`, `absolute_max_level_cm`, `absolute_max_level_dates`, `details_source` (`"hydro_details"` or null); all null without details (docs/USAGE.md, "Station data sources")

### Station Pages
- **Hydro**: `https://hydro.imgw.pl/#/station/hydro/{station_code}`
- **Meteo**: `https://hydro.imgw.pl/#/station/meteo/{station_code}`

### ČHMÚ (opendata.chmi.cz, ADR-003)
- **Hydro daily** (`cz.chmi.hydro_daily`): `https://opendata.chmi.cz/hydrology/historical/data/daily/H_<WIGOS>_DQ_<year>.json` — one JSON per station and calendar year (from 1887); `HD`/`QD`/`TD` → H [cm], Q [m3/s], T [°C]
- **Meteo daily** (`cz.chmi.meteo_daily`): `meteorology/climate/historical_csv/data/daily/{precipitation,temperature}/dly-<WIGOS>-{SRA,T,TMA,TMI}.csv` — four CSV files per station with the whole station history; `QUALITY` 0–5 and `FLAG` kept as `quality`/`source_flag`
- **Station lists** (`cz.chmi.hydro_stations`, `cz.chmi.meteo_stations`): `hydrology/historical/metadata/meta1.json`, `meteorology/climate/historical/metadata/meta1.json` (JSON envelope `zaznamID`/`datumVytvoreni` changes with every regeneration → canonical form `chmi-json/1`)
- **Catalog sources** (`cz.chmi.hydro_now`, `cz.chmi.meteo_now`, stored by `store sync --datasets`; ADR-015): `hydrology/now/metadata/meta1.json` (SPA thresholds), `meta3.json` (`HLGP4`), newest `meteorology/climate/now/metadata/meta1-<YYYYMMDD>.json` (directory listing); meteo `GEOGR1` = longitude, hydro `GEOGR1` = latitude
- **Inventory and freshness**: nginx directory listings (name, mtime to the minute, size): one GET instead of a HEAD per file; requests are sequential with `User-Agent: obserwator/<version>`; license CC BY 4.0 (attribution from the registry)
- Out of scope: `now`/`recent` measurements, hourly data, CAP warnings, PMAXTP

## Command Catalog (CLI, REST and MCP)

CLI command = `obserwator <group> <name>`; REST route = `/api/v1/<group>/<name>` (GET options in the query, POST options in a JSON body, `?check=true` on POST = plan without writing); MCP tool = the catalog `operation_id` (`obserwator_` + name with spaces and `-` → `_`, e.g. `obserwator_store_sync`; also the REST `operationId`). "Local" commands have no REST route. Check: twin function used by `--check`/`?check=true`/`check: true`; `—` = no `--check`; "self" = the command is a check.

|Command|Function|Check|REST|
|---|---|---|---|
|`datasets list`|`datasets`|—|`GET /api/v1/datasets/list`|
|`datasets files`|`archive_files`|—|`GET /api/v1/datasets/files`|
|`datasets download`|`download_archives`|`check_command`|local|
|`datasets providers`|`providers`|—|`GET /api/v1/datasets/providers`|
|`stations find`|`find_stations`|`check_command`|`GET /api/v1/stations/find`|
|`current hydro`|`fetch_hydro_current`|`check_command`|`GET /api/v1/current/hydro`|
|`current meteo`|`fetch_meteo_current`|`check_command`|`GET /api/v1/current/meteo`|
|`current synop`|`fetch_synop`|`check_command`|`GET /api/v1/current/synop`|
|`current warnings`|`fetch_warnings`|`check_command`|`GET /api/v1/current/warnings`|
|`current hydro-states`|`fetch_hydro_states`|`check_command`|`GET /api/v1/current/hydro-states`|
|`pmaxtp fetch`|`fetch_pmaxtp`|`check_command`|`GET /api/v1/pmaxtp/fetch`|
|`pmaxtp url`|`build_pmaxtp_url`|—|`GET /api/v1/pmaxtp/url`|
|`pmaxtp check`|`check_pmaxtp`|self|`GET /api/v1/pmaxtp/check`|
|`pmaxtp sync`|`sync_pmaxtp`|`check_pmaxtp`|`POST /api/v1/pmaxtp/sync`|
|`pmaxtp read`|`read_pmaxtp`|—|`GET /api/v1/pmaxtp/read`|
|`store init`|`init_store`|`check_command`|local|
|`store info`|`store_info`|—|`GET /api/v1/store/info`|
|`store scan`|`iter_store`|—|`GET /api/v1/store/scan`|
|`store check`|`check_store`|self|`GET /api/v1/store/check`|
|`store sync`|`sync_store`|`check_store`|`POST /api/v1/store/sync`|
|`store catalog`|`build_catalog`|`check_catalog`|`POST /api/v1/store/catalog`|
|`store export`|`export_archive`|`check_command`|`GET /api/v1/store/export`|
|`series build`|`build_series`|`check_series`|`POST /api/v1/series/build`|
|`series select`|`select_series`|—|`GET /api/v1/series/select`|
|`series read`|`read_series`|—|`GET /api/v1/series/read`|
|`series summary`|`summarize_series`|—|`GET /api/v1/series/summary`|
|`series export`|`export_series`|`check_command`|`GET /api/v1/series/export`|
|`stations export`|`export_stations`|`check_command`|`GET /api/v1/stations/export`|
|`analyses build`|`build_analyses`|`check_analyses`|`POST /api/v1/analyses/build`|
|`analyses list`|`list_analyses`|—|`GET /api/v1/analyses/list`|
|`analyses read`|`read_analysis`|—|`GET /api/v1/analyses/read`|
|`analyses export`|`export_analyses`|`check_command`|`GET /api/v1/analyses/export`|
|`commands list`|`list_commands`|—|`GET /api/v1/commands/list`|
|`commands schema`|`command_schema`|—|`GET /api/v1/commands/schema`|
|`commands guide`|`agent_guide`|`check_command`|`GET /api/v1/commands/guide`|

The `analyses` group (ADR-016): `analyses build` takes `root` (the data root), `stations` (`-s`, compute only these; the others are carried forward) and `workers` (Hydrolog processes at a time, ≥ 1, default 1) and is store only; `analyses list|read|export` take `version` (directory, `analyses.json` or sidecar; default the current version of the station's provider), `root` and the required `station` (`-s`; its code names the provider), `analyses read` the required `analysis` and `analyses export` the list `analyses` (both from the 87 registry ids, with their titles as `enum` meanings), `format` (`json`|`csv`), `output` and `force`. No option names Hydrolog's program. Errors (`errors` of `command_schema`): `analyses build` `validation_error`, `not_found`, `conflict`, `source_unavailable` (`hydrolog_failed`, `timeout`), `missing_dependency` (`hydrolog_missing`), `data_error`, `store_unavailable`, `io_error`, `cancelled`, `forbidden`, `internal_error`; `analyses list` and `analyses read` `validation_error`, `not_found`, `missing_dependency`, `data_error`, `store_unavailable`, `forbidden`, `internal_error`; `analyses export` the same plus `io_error` and `cancelled`.

Outside the catalog: `obserwator version`, `obserwator server` (`--host`, `--port`, `--reload`), `obserwator mcp` (`--allow-writes`, repeatable `--allow-dir`), `obserwator gui serve` (`--host`, `--port`, `--root`, `--no-browser`; the GUI and its private API, `docs/USAGE.md` „GUI”), `obserwator admin keys|create|revoke|delete|stats`, `obserwator config show`, `GET /health`, `GET /api/v1` (name, version, schema route, list of catalog routes), `GET /llms.txt` (agent guide, language from `Accept-Language`) and `/mcp` (MCP Streamable HTTP, English, only with `OBSERWATOR_MCP_ENABLED=true`).

Effects (`effects.writes`/`effects.network` of `command_schema`, ADR-004 D2): `none` = no file changes, `add` = only new files/versions, `replace` = may replace or remove user content (no command by its own run, only its writing options; a command's `effects.writes` is the strongest of its run and its options, and `destructive` when that is `replace`); writing options (`writes` of an option): `plan` of `store check` (`replace`), `output_dir` of `datasets download`/`store sync`/`pmaxtp sync` and `output` of `stations export`/`store export`/`series export`/`analyses export`/`commands guide` (`add`: new files), and `force` of the same commands (`replace`: an existing file). Every writing command has a check twin.

### Options

Option name = function parameter = JSON field; CLI flag = `--` + name with `_` → `-`. Short aliases: `-d` dataset(s), `-y` years, `-m` months, `-s` station(s), `-k` kind, `-q` query, `-o` output-dir, `-r` root, `-f` format; `--lat`/`--lon` alias `--latitude`/`--longitude`. Write targets: see "Data output" below. Lists: comma-separated or repeated flag/parameter. `--root` defaults to the root of the command's kind (ADR-017): `OBSERWATOR_RAW_ROOT` for `datasets download`, `store init|check|sync|export` and `pmaxtp check|sync|read`, `OBSERWATOR_ROOT` for the others and `store info|scan` (for `stations find` only with `--source store`; rule `DataCommand.env_root_when`, shared with MCP stdio); `store init --kind data` (`-k`) takes the data root; `--raw-root` of `series build` and `store catalog` defaults to `OBSERWATOR_RAW_ROOT`. List commands accept `--limit`/`--cursor` (`page.next_cursor`; a malformed cursor → `validation_error`, `details.option="cursor"`). `--check` exists only on commands with a check twin; `--schema` prints the command's schema without running it. `--provider` (`IMGW-PIB`|`CHMI`) in `datasets list`, `stations find`, `stations export`, `store scan` (absent = all) and `store catalog` (default `IMGW-PIB`); `--stations`/`-s` in `datasets files|download`, `store check|sync` (required for `cz.chmi.*`, forbidden for `pl.imgw.*`; `years` dataset-dependent — see `x-obserwator.rules`). `--lang pl|en` in `commands list`/`commands schema`/`commands guide` (default `en`); `OBSERWATOR_LANG=pl|en` sets only the CLI help language (incl. Typer/Click elements; invalid value → `validation_error`, exit 2).

### Data output

Python, CLI, REST and MCP share the names of the write targets (DEV-19.1, ADR-007); `obserwator/output.py` implements the plain way once.

|CLI|Python|Meaning|
|---|---|---|
|`-o`, `--output-dir`|`output_dir`|plain files in a directory: no metadata, named as in the store (`datasets download`: the provider's server path), `mkdir -p`|
|`-r`, `--root`|`root`|a root of the versioned store, of the command's kind; neither option given = the default root of that kind: the raw root of a download (`OBSERWATOR_RAW_ROOT`, `[obserwator] raw_root`, `<data_dir>/obserwator-raw`), the data root of a build (`OBSERWATOR_ROOT`, `[obserwator] root`, `<data_dir>/obserwator`)|
|`--output` (no short form)|`output`|exactly one file of an export (`stations export`, `store export`, `series export`, `analyses export`, `commands guide`)|
|`--force`|`force`|plain: replace existing targets (never deletes other files); store: fetch again, a new version or `unchanged`|

- `output_dir` and `root` exclude each other: `validation_error`, `details.reason="exclusive_options"`. Commands whose input or result is the store (`series build`, `store catalog`, `analyses build`) have no `output_dir` (rule "store only" in their description); `--plan` with `output_dir` is `validation_error` (`store_only_option`); a dataset without a store form given `root`: `not_in_store`.
- Preflight before the first byte: a directory that is or lies in a store of any tool → `conflict` (`output_in_store`, hint `--root`, `details.paths` the directory, before any request); then duplicate names → `conflict` (`duplicate_output_name`), a target that would enter a subdirectory with a store marker → `output_in_store` (its path), existing target without `--force` → `conflict` (`output_exists`); `details.paths` lists every offending path. `--check` plans `write`, `replace` or `conflict` per target; a plan with conflicts is `ok`. In store mode `--check` lists a root that is `nested_store` or `not_empty` as one `conflict` action of the root; `store_unavailable` (`no_marker`) and `data_error` (an unreadable marker) are raised.
- Writing: staging `<dir>/.obserwator-incoming/<host>_<pid>_<token>/`, sha256 computed while streaming, `os.replace` into place; staging removed on success, error, SIGINT and SIGTERM, leftovers older than 24 h by the next run. No sidecar, hard link or `versions/`. Result `files[]` = `{path, size_bytes, sha256, status}`, status `written`/`replaced` (store: `new`/`unchanged`/`relabeled`).
- Servers: REST writes only to its own `OBSERWATOR_RAW_ROOT` and `OBSERWATOR_ROOT` with writes enabled and takes none of these options in a request; MCP writes only inside `--allow-dir` with `--allow-writes`.

### Output, errors and exit codes

- CLI stdout with `--json`: compact one-line JSON envelope `obserwator-result/1` (`schema`, `tool`, `version`, `command`, `check`, `status` ok|partial|failed|cancelled, `result`, `notices`, `page` of a list command); `result` is a document with its own `schema` `obserwator-<kind>/1`, a list of them or null; store paths relative to the root. `stations export`/`store export`/`series export`/`analyses export`/`commands guide` without `--output` stream GeoJSON/CSV/JSONL/JSON/Markdown bytes; with it the `result` is `{schema, output, files[]}` (`OutputReport`, `obserwator-output/1`; `files[]` = `{path, size_bytes, sha256, status}`). Progress and notices (once per distinct notice) go to stderr.
- CLI stdout without `--json`: a short summary for a person in the language of `--lang` (`cli/_render.py`; status, the items of a list as a table of key fields and the page, the main fields of a document, the notices); not a contract.
- CLI error: stdout empty, last stderr line the `obserwator-error/1` document (`schema`, `code`, `title`, `message`, `hint`?, `details`, `exit_code`, `command`?; `error_report.py`); without `--json` one readable line in the language of `--lang` comes before it.
- REST: same envelope as the body; errors as `application/problem+json` (`type`, `title`, `status`, `detail`, `instance`, `code`, `hint`?, `details`); list `limit` default/maximum `OBSERWATOR_API_MAX_LIMIT` (1000). The texts of an answer (notices, item and plan texts, `title`, `detail` and `hint` of problem+json) are in the language of `?lang=` (commands with a `lang` option), else `Accept-Language`, else English; every command answer has `Content-Language`, and `Vary: Accept-Language` when the header decided. The OpenAPI document is English.
- MCP: `structuredContent` = envelope (`isError=false` also for `partial`/`failed`); errors `isError=true` with the CLI's `obserwator-error/1` document; lists default to 50 items; streams up to 256 KiB; without `--allow-writes` writing commands return the plan (`check` fixed `true`), refused writes → `forbidden` (`details.reason="writes_disabled"`); with it a write needs `--allow-dir` and a target inside it (`no_allowed_dir`, `outside_allowed_dirs`).

|Code|Title (`title` / `title.localized("pl")`)|CLI exit|HTTP|
|---|---|---|---|
|`validation_error`|Invalid input / Nieprawidłowe dane wejściowe|2|400|
|`not_found`|Not found / Nie znaleziono|3|404|
|`conflict`|State conflict / Konflikt stanu|4|409|
|`source_unavailable`|Data source unavailable / Źródło danych niedostępne|5|502|
|`missing_dependency`|Missing optional dependency / Brak opcjonalnej zależności|6|503|
|`data_error`|Invalid data / Niepoprawne dane|7|500|
|`store_unavailable`|Store unavailable / Magazyn niedostępny|8|503|
|`io_error`|File system error / Błąd systemu plików|9|500|
|`cancelled`|Cancelled / Anulowano|130|—|
|`forbidden`|Not allowed / Operacja niedozwolona|12|403|
|`unsupported`|Not supported / Nieobsługiwane|15|422|
|`method_not_allowed`|Method not allowed / Niedozwolona metoda|—|405|
|`internal_error`|Internal error / Błąd wewnętrzny|1|500|

Envelope status exit codes: `ok` 0, `partial` 10, `failed` 11, `cancelled` 130.

## Data Structure

### Dataset registry (22 descriptors, 2 providers)

|Key|Legacy alias|Store|
|---|---|---|
|`pl.imgw.hydro_daily`|`hydro/dobowe`|yes|
|`pl.imgw.hydro_monthly`|`hydro/miesieczne`|yes|
|`pl.imgw.hydro_semiannual`|`hydro/polroczne_i_roczne`|yes|
|`pl.imgw.meteo_climate_daily`|`meteo/dobowe/klimat`|yes|
|`pl.imgw.meteo_precip_daily`|`meteo/dobowe/opad`|yes|
|`pl.imgw.hydro_stations`, `pl.imgw.meteo_stations`|—|yes (station lists)|
|`pl.imgw.hydro_now`, `pl.imgw.meteo_now`|—|yes (station metadata of the current-data API, derived: code, name, river, coordinates; ADR-015 D5)|
|`pl.imgw.hydro_details`|—|yes (station details of hydro.imgw.pl, derived: gauge zero and datum, river km, catchment area, year, province, district, warning and alarm levels, absolute extremes; ADR-021)|
|`pl.imgw.pmaxtp`|—|yes (grid cells)|
|`pl.imgw.hydro_phenomena`|— (`hydro/dobowe` with month 13)|download only|
|`pl.imgw.meteo_climate_monthly`, `pl.imgw.meteo_precip_monthly`, `pl.imgw.meteo_synop_monthly`|`meteo/miesieczne/klimat\|opad\|synop`|download only|
|`pl.imgw.meteo_climate_terms`|`meteo/terminowe/klimat`|download only|
|`cz.chmi.hydro_daily`|—|yes (per station × calendar year, `stations` required)|
|`cz.chmi.meteo_daily`|—|yes (4 files per station: SRA, T, TMA, TMI; no `years`)|
|`cz.chmi.hydro_stations`, `cz.chmi.meteo_stations`|—|yes (station lists, canonical form `chmi-json/1`)|
|`cz.chmi.hydro_now`, `cz.chmi.meteo_now`|—|yes (`now` station metadata, canonical form `chmi-json/1`)|

`get_dataset`/`archive_files` accept the key, the slug (e.g. `hydro_daily`, `chmi_hydro_daily`) or the legacy alias; results and slots always use the full key. Archive commands (`datasets files|download`) accept 12 datasets, `store check|sync` the 7 measurement datasets and the 9 station sources (lists, metadata and the station details of hydro.imgw.pl, `time_unit="station_list"`, a call of their own; ADR-015, ADR-021), series commands 7. Descriptor fields added by ADR-003: `provider`, `archive_scope`, `variable_notes`, `measurement_fields`, `content_form`, `volatile_fields`, `update_signal="listing"`; by ADR-015: `base_url` (the current-data API lies below IMGW-PIB's site) and `kept_fields` (the station fields a derived file keeps; since ADR-021 a dotted name such as `status.alarmValue` reaches into a nested object and is kept nested). `title` and the values of `variable_notes` are English catalog messages (`messages/datasets.py`); `localize(title, "pl")` is the Polish title.

### IMGW-PIB hydrological data (1951-2024+)
- `dobowe` (daily):
  - Before 2023: `codz_{year}_{month:02d}.zip` (monthly files; month 13 = `zjaw_` phenomena)
  - From 2023: `codz_{year}.zip` (single yearly file)
- `miesieczne` (monthly): `mies_{year}.zip`
- `polroczne_i_roczne` (semi-annual): `polr_{param}_{year}.zip` (param: T, Q, H)

### IMGW-PIB meteorological data (1950-current)

Real IMGW layout, verified against live server listings (2026-07-05):

**Folders:** 5-year ranges until 2000 (e.g. `1996_2000`), yearly from 2001 (e.g. `2023`).
First folder differs per subtype: klimat `1951_1955`, opad `1950_1955`, synop `1960_1965` (six years); from `1966_1970` all subtypes share the same grid.

**Files per interval/subtype:**
- `miesieczne` (all subtypes): ONE file per folder — `{folder}_m_{k|o|s}.zip` (e.g. `1996_2000_m_s.zip`, `2023_m_s.zip`)
- `dobowe`/`terminowe` klimat & opad: yearly `{year}_{k|o}.zip` until 2000, monthly `{year}_{month:02d}_{k|o}.zip` from 2001
- `dobowe`/`terminowe` synop: PER-STATION files `{folder}_{station}_s.zip` — `get_dataset`/`archive_files` raise `ObserwatorValidationError` (`details.reason=per_station`)
- `terminowe` opad: dataset does not exist — `ObserwatorValidationError` (`details.reason=not_published`)

**Subtypes:** `k` (klimat), `o` (opad), `s` (synop)

## Docker Deployment

```bash
cd docker
docker compose up -d
OBSERWATOR_MCP_ENABLED=true OBSERWATOR_MCP_ALLOWED_HOSTS=dane.example.pl docker compose up -d  # with /mcp
```

Services: app (FastAPI, `python:3.12-slim`, `pip install ".[api,mcp]"`, one uvicorn process with `--no-access-log --log-level warning`, container `obserwator-api`), nginx (reverse proxy, container `obserwator-nginx`; `location /api/` and `location = /mcp` with the `api_limit` zone, burst 20, `/mcp` without buffering). Compose passes `OBSERWATOR_MCP_ENABLED` (default `false`) and `OBSERWATOR_MCP_ALLOWED_HOSTS` (default `127.0.0.1,localhost`), mounts `../data` read-only at `/app/data` and keeps the REST API keys in the volume `api_keys` (`OBSERWATOR_API_KEYS_FILE=/app/keys/api_keys.json`); it sets neither `OBSERWATOR_ROOT` nor `OBSERWATOR_RAW_ROOT`, so the routes of the commands that need a root answer 503 `not_configured` until they are added. No Redis needed. The GUI is not part of the image.

Logs (Nogat DEV-12.6 to DEV-12.8): the app writes its access, application and lifecycle records to `/state/obserwator/logs` (`NOGAT_STATE_DIR=/state`), the host's `${NOGAT_STATE_DIR:-../state}/obserwator` (relative to `docker/`; writable by the image's `appuser`, UID 1000), and deletes them after 14 days; both containers use the logging driver `local` (`max-size: "1m"`, `max-file: "3"`), which holds only the lifecycle records and errors reduced to their type. nginx keeps no log (`access_log off;`, `error_log /dev/null;`, so the rejections of `limit_req` are not logged either) and passes no `X-Request-ID`.

Operator note: a container created before this change keeps Docker's default `json-file` log, uncapped and with the client addresses of uvicorn's access lines (e.g. `imgwtools-api` on the VPS). Docker deletes that file with the container: rebuild it from this code (`docker compose up -d --build` in `docker/`) or remove it (`docker rm -f <name>`); both need the `docker` group. Create the host's state directory first (`mkdir -p <state_dir>/obserwator && chown 1000 <state_dir>/obserwator`).

## Cloud & Deployment Details

### Deployment Model
Application hosted on a private server. Components:
- **Nginx** — reverse proxy + HTTPS + rate limiting
- **FastAPI (Uvicorn)** — backend API
- **GUI (Uvicorn)** — `obserwator gui serve` as a service of its own (e.g. a systemd user unit) on 127.0.0.1 behind an authenticating proxy (e.g. Cloudflare Access through a tunnel); it writes `<data_dir>/obserwator/{stats.jsonl,feedback.jsonl,feedback.next_id}` (none when that directory and the data root are one or one holds the other) and its logs in `<state_dir>/obserwator/logs`; its admin panel (`/admin/`, `/api/admin/`, DEV-15.13) needs `OBSERWATOR_ADMIN_API_KEY_FILE` (a key file of mode 0600 named by the unit) or `OBSERWATOR_ADMIN_API_KEY`, and a public deployment protects `/admin`, `/admin/*` and `/api/admin/*`; unit, headers and public rules: `docs/USAGE.md` „GUI”

### Rate limiting
- Nginx: `limit_req_zone` `api_limit` (10 req/s per IP, burst 20) on `/api/` and `/mcp`; the zone `key_limit` (100 req/min per `X-API-Key`) is declared but used by no location
- API keys carry a rate limit (`obserwator admin create --limit`, default 100, stored in JSON), not enforced (see below)
- GUI: per client address in the app, 300 requests in 60 s by default (`OBSERWATOR_REQUEST_LIMIT`, `OBSERWATOR_REQUEST_WINDOW`; Nogat DEV-15.9), static files not counted; behind a proxy uvicorn's `FORWARDED_ALLOW_IPS` names the proxy

### Authorization (Planned)
API keys in a JSON file (`api_keys.json`). Header: `X-API-Key: <token>`

**Note:** API key validation middleware is not yet implemented. Keys are managed via CLI but not enforced in API requests. Store writes over REST use their own token (`OBSERWATOR_STORE_WRITE_TOKEN`, sent as `X-API-Key`).

### API versioning
All endpoints under `/api/v1/...`

## Versioned Store (Optional)

The store has two roots (ADR-017), each readable offline, also from network shares, and each holding both providers. The raw root (marker `obserwator-store.json`) keeps the downloads: archives, station sources and PMAXTP cells; it is `--root` of `datasets download`, `store init|check|sync|export` and `pmaxtp check|sync|read`, `OBSERWATOR_RAW_ROOT`, `raw_root` in `[obserwator]` of `nogat.toml` or `<data_dir>/obserwator-raw`. The data root (marker `obserwator-data.json`) keeps what is built from it: series, station catalogs and analyses; it is `--root` of the other store commands, `OBSERWATOR_ROOT`, `root` in `[obserwator]` or `<data_dir>/obserwator` (DEV-19.2, ADR-007; `init_store(root)` creates a raw root, `init_store(root, kind="data")` a data root). `series build` and `store catalog` read the raw root (`--raw-root`, `raw_root=`) read-only and write the data root; a root of the other kind than a command needs is `store_unavailable` with `details.reason="wrong_root"`, and a store written before ADR-017 is split once (`docs/USAGE.md`, "Splitting a store"). Writes need a file system with hard links, as Kartograf's store (its ADR-036): versions, observations and the markers are published by `os.link` from `.incoming/`, the main file's sidecar last (it commits the version); FAT/exFAT, some NAS/FUSE and the macOS SMB client → `conflict` with `details.reason="not_atomic"`. A version directory without its sidecar is an interrupted publication (`missing_sidecar`), completed by the next write of the same content under the same label, otherwise removed by hand while no write runs; a failed publication never removes linked data files. Decisions: `docs/DECISIONS.md` ADR-001, ADR-003, ADR-017; contracts: `docs/superpowers/specs/2026-10-17-versioned-store-design.md` (§13 = ADR-002 takes precedence) and `2026-10-18-chmi-provider-design.md` (ČHMÚ).

### Configuration

Resolution (DEV-18.1, `src/obserwator/_environment.py` and `config.py`): command-line option, `OBSERWATOR_<KEY>` variable, the same key in `.env`, `NOGAT_<KEY>` (shared keys `data_dir`, `cache_dir`, `state_dir`, `lang`), `[obserwator]` then `[nogat]` of `nogat.toml` (user config dir, or `NOGAT_CONFIG`; read with `tomllib`, absence is no error, an unusable file is `validation_error` for every `obserwator` call), default. `OBSERWATOR_STORE_WRITE_TOKEN` and the GUI's admin key (`OBSERWATOR_ADMIN_API_KEY`, `OBSERWATOR_ADMIN_API_KEY_FILE`) are credentials (`CREDENTIAL_KEYS`): environment or `.env` only, never from the file, never printed (`config show` says only `present` or `missing`). Nothing is written to the working directory. `obserwator config show [--json]` reports every key with its source (`obserwator-config/1`, DEV-18.6; outside the catalog, `config_cmd.py`).

The table `gui` of `[nogat]` (DEV-15.4, ADR-011) is no setting: only the file gives it, and no variable or default does. Its keys are registry names in lower case, its values GUI addresses (absolute or a path), e.g. `[nogat.gui]` with `hydrolog = "http://127.0.0.1:8070/"`. The GUI reads it when its app starts (`_environment.gui_addresses`) and gives it to the page in `api/session`, which hands it to Nogat's `<nogat-app-menu>` in the top bar; with no other GUI in it the menu is not drawn. Its `obserwator` entry is the GUI's own public address, named by the regulamin and by a hand-off.

The table `operator` of `[nogat]` (DEV-15.7, DEV-18.1; `_environment.operator`) names who runs a deployment open to others, from the file only: `name`, `email`, `terms_effective` (a TOML date or `YYYY-MM-DD`), `processor` and `mail_provider` must have a value; `processor_transfer`, `processor_cookie` and `mail_transfer` may be empty or left out (Nogat kit 0.4.0). A table with a required key missing or empty is not used. With a usable table and the `obserwator` address of `[nogat.gui]`, the GUI is public and serves `regulamin.html` (`docs/USAGE.md` „GUI”, „Public deployment”).

|Variable|Default|Description|
|---|---|---|
|`OBSERWATOR_ROOT`|`<data_dir>/obserwator`|The data root (series, station catalogs, analyses; ADR-017) of the CLI, the library and `obserwator mcp` when `--root` of a command of the data root is absent (also `root` in `[obserwator]` of `nogat.toml`); of the REST server its data root: unset → the routes of those commands 503 `not_configured`, never the default|
|`OBSERWATOR_RAW_ROOT`|`<data_dir>/obserwator-raw`|The raw root (archives, station sources, PMAXTP cells; ADR-017) of the CLI, the library and `obserwator mcp`: `--root` of `datasets download`, `store init\|check\|sync\|export` and `pmaxtp check\|sync\|read` and `--raw-root` of `series build` and `store catalog` when absent (also `raw_root` in `[obserwator]`); of the REST server its raw root: unset → the routes of those commands 503 `not_configured`, never the default|
|`OBSERWATOR_STORE_WRITES_ENABLED`|`false`|Allow REST writes (`POST` store/series/pmaxtp routes)|
|`OBSERWATOR_STORE_WRITE_TOKEN`|unset|Token required in `X-API-Key` for REST writes (else 403 `forbidden`)|
|`OBSERWATOR_USER_LOCATIONS_DIR`|unset|Directory of user location CSVs allowed in REST `user_locations`|
|`OBSERWATOR_API_MAX_LIMIT`|`1000`|Default and maximum `limit` of REST list commands|
|`OBSERWATOR_DATA_DIR`|user data dir of `nogat`|DEV-18.2 meaning since this change: parent of the roots (`<data_dir>/obserwator-raw`, `<data_dir>/obserwator`), of the API keys and of the GUI's `stats.jsonl` and `feedback.jsonl`; shared key (also `NOGAT_DATA_DIR`, `[nogat] data_dir`). Until 3.0.0 `IMGW_DATA_DIR` held the reference data: that is `OBSERWATOR_REFERENCE_DIR` now|
|`OBSERWATOR_REFERENCE_DIR`|`<cache_dir>/obserwator/reference`|IMGW-PIB reference data (`hydro_stations_locations.csv`, `desc/`; `python -m obserwator.reference_data`); `settings.reference_dir`|
|`OBSERWATOR_LANG`|`pl`|`pl`\|`en`: CLI help, progress and notice lines only (`--lang` of `commands list\|schema\|guide` defaults to English whatever it says; REST answers follow `Accept-Language`, English without it; MCP is always English; the CLI error line and the envelope are English)|
|`OBSERWATOR_MCP_ENABLED`|`false`|Serve MCP Streamable HTTP at `/mcp` in `obserwator server` (needs `obserwator[mcp]`; read and plan only)|
|`OBSERWATOR_MCP_ALLOWED_HOSTS`|`127.0.0.1,localhost`|Allowed `Host` values of `/mcp` (comma-separated; behind nginx add the public host name)|
|`OBSERWATOR_MCP_ALLOW_WRITES`|`false`|Envvar of `obserwator mcp --allow-writes`: writing tools still default to `check: true` (plan) and write only with `check: false`|
|`OBSERWATOR_CACHE_DIR`|user cache dir of `nogat`|Caches `<cache_dir>/obserwator`; shared key (also `NOGAT_CACHE_DIR`, `[nogat] cache_dir`)|
|`OBSERWATOR_STATE_DIR`|user state dir of `nogat` (`~/.local/state/nogat` on Linux)|State kept between runs (DEV-18.2): the logs of `obserwator server` and `obserwator gui serve` in `<state_dir>/obserwator/logs/<kind>-YYYY-MM-DD.jsonl` (`access`, `app`, `lifecycle`; Nogat DEV-12.6), deleted by the servers after 14 days; `Settings.log_dir`; shared key (also `NOGAT_STATE_DIR`, `[nogat] state_dir`). In a container `NOGAT_STATE_DIR` names the directory where the host's `<state_dir>/obserwator` is mounted|
|`OBSERWATOR_API_KEYS_FILE`|`<data_dir>/obserwator/api_keys.json`|File of the REST API keys of `obserwator admin`|
|`OBSERWATOR_ADMIN_API_KEY`, `OBSERWATOR_ADMIN_API_KEY_FILE`|unset|Credentials (environment or `.env` only): the key of the GUI's admin panel in `X-Admin-Key`, or a file holding it; read on every admin request; unset, every route of the admin API (`api/admin/…`) answers `401 admin_key_not_configured`|
|`OBSERWATOR_RATE_LIMIT`|`100`|Requests per hour (0 = unlimited); read by nothing: each REST API key has its own limit (`obserwator admin create --limit`), and the REST server checks no key of `api_keys.json`|
|`OBSERWATOR_ENV`, `OBSERWATOR_HOST`, `OBSERWATOR_PORT`|`development`, `0.0.0.0`, `8000`|REST server (`obserwator server`); `OBSERWATOR_ENV=production` turns off the default reload of `obserwator.api.main.run_server()` called without `reload` (`obserwator server` reloads only with `--reload`). No log-level setting: the servers log at the fixed levels of Nogat DEV-12.7 (`OBSERWATOR_LOG_LEVEL`, which configured nothing, is gone and ignored)|
|`OBSERWATOR_GUI_BASEMAP_URL`|`https://tiles.openfreemap.org/planet`|TileJSON of the GUI's basemap; `none`, `off` or the variable set and empty: no basemap, the packaged borders (offline)|
|`OBSERWATOR_GUI_BASEMAP_ATTRIBUTION`|`OpenFreeMap © OpenMapTiles Data from OpenStreetMap`|The basemap's credit line|
|`OBSERWATOR_HYDROLOG_COMMAND`|unset|`hydrolog_command` (also `[obserwator] hydrolog_command`): Hydrolog's program of `analyses build`, `compute_analysis` (ADR-016) and the GUI's choices computed on request (looked for once when it starts; without it the GUI shows only stored results), a command line split as a shell splits it; unset → `hydrolog` on `PATH`, none → `missing_dependency` (`details.reason="hydrolog_missing"`); no command option replaces it|
|`OBSERWATOR_REQUEST_LIMIT`, `OBSERWATOR_REQUEST_WINDOW`|`300`, `60`|The GUI's rate limit: counted requests of one client address in a window of seconds (DEV-15.9)|

`FORWARDED_ALLOW_IPS` is uvicorn's own variable (default `127.0.0.1,::1`): the addresses whose `X-Forwarded-For` the GUI's server trusts.

### Layout

```text
<raw root>/obserwator-store.json                        # obserwator-store/1 marker: schema, tool, created_at, producer_version (+ optional created_by)
  archives/versions/<server dir>/<stem>/<label>_<sha8>/<file> + <file>.meta.json
  archives/versions/<server dir>/<stem>/observations/   # obserwator-observation/1 signal register (ČHMÚ datasets with a content form)
  pmaxtp/versions/<POT|AMP>/<indX>_<indY>/<label>_<sha8>/cell.json + response.json + .meta.json
  .incoming/                                            # staging; never a version

<data root>/obserwator-data.json                        # obserwator-data/1 marker: the same fields (ADR-017)
  series/versions/<slug>/<label>_<sha8>/series.json + .meta.json + stations/<code>.parquet
  stations/versions/<label>_<sha8>/stations.geojson + .meta.json                # IMGW-PIB catalog
  stations/versions/chmi_stations/<label>_<sha8>/stations.geojson + .meta.json  # ČHMÚ catalog
  analyses/versions/<pl.imgw|cz.chmi>/<label>_<sha8>/analyses.json + .meta.json + stations/<code>.json + stations/<code>/<id>.json  # Hydrolog's answers (ADR-016)
  .incoming/                                            # staging; never a version
```

Slots (spec §13.7; the slot decides the kind of root `current_version` needs): of the raw root `archive:<key>:<file>` (e.g. `archive:pl.imgw.hydro_daily:2024/codz_2024.zip`, `archive:cz.chmi.hydro_daily:H_0-203-1-001000_DQ_2025.json`, `archive:cz.chmi.meteo_daily:precipitation/dly-0-203-0-11573-SRA.csv`) and `pmaxtp:pl.imgw.pmaxtp:<METHOD>/<indX>_<indY>`; of the data root `series:<key>`, `catalog:pl.imgw.stations`, `catalog:cz.chmi.stations`, `analyses:pl.imgw.analyses` and `analyses:cz.chmi.analyses`. A path in a sidecar is relative to its own root: the sources of a series or catalog under `archives/` of the raw root, the series a catalog read under `series/` of the data root.

Analyses versions (ADR-016): one slot per provider; `analyses.json` (`obserwator-analyses/1`) is the main file and its sidecar (`dataset` `pl.imgw.analyses`/`cz.chmi.analyses`, `extra.derived="analyses"`) is published last; `stations/<code>.json` (`obserwator-station-analyses/1`) records the inputs (series version, station Parquet and export SHA-256), options, Hydrolog version and registry digest of a station, and `stations/<code>/<id>.json` is Hydrolog's answer line byte for byte. They are entries of kind `analyses` of the data root (`store scan --kind analyses`, `iter_store`), and `current_version(root, slot="analyses:pl.imgw.analyses")` gives the newest by `downloaded_at`, then by path (ADR-017).

ČHMÚ specifics (ADR-003): freshness from one directory listing per dataset (plan fields `station_code`, `signal`, `remote_listed_at`, `local_observation`, `requests`); a station × year missing at the source is `unverifiable` with `error="not published"` (`download_archives`: `not_published`); datasets with the content form `chmi-json/1` store `content_sha256` — other bytes with the same canonical content give `unchanged` + notice `content_unchanged` + an observation, not a new version; series of per-station datasets carry `stations[<code>].periods` (unpublished years are unknown, not gaps); meteo series add `<V>_quality`/`<V>_source_flag`. Projects that pin store versions (by `sha256` and `content_sha256`) belong to Archiwista (`archiwista-project/1`, ADR-008).

### Contracts (IMGW-13)

`obserwator-store/1` (the marker of a raw root), `obserwator-data/1` (the marker of a data root, ADR-017), `obserwator-meta/1`, `obserwator-series/1`, `obserwator-plan/1`, `obserwator-pmaxtp/1`, `obserwator-observation/1`, envelope `obserwator-result/1`, `obserwator-commands/1` (command schema); the analyses (ADR-016): `obserwator-analyses/1`, `obserwator-station-analyses/1`, `obserwator-analysis-summary/1`, `obserwator-analysis/1`, `obserwator-analyses-report/1`, `obserwator-analyses-export/1`, `obserwator-analysis-definition/1`. Each has its own `/N` counter; within `/1` only optional fields are added. `/1` domains are open to further providers (ADR-003 C01): dataset key `^[a-z]{2}\.[a-z][a-z0-9]*\.[a-z][a-z0-9_]*$`, `country` `^[A-Z]{2}$`, station code `STATION_CODE_PATTERN` (9-digit IMGW or WIGOS), optional `content_sha256`/`content_form` in sidecars. Additive fields of 3.0.0 (ADR-003/004): sidecar `request.station_code`/`param`, `extra.period.station_code`, `license.terms_url`; series `stations[<code>].periods`; catalog `thresholds`; plan item `station_code`/`signal`/`remote_listed_at`/`local_observation` and plan `requests`; command schema `lang`, `x-obserwator.writes`/`network`/`operation_id`, `x-obserwator-writes`. IMGW-PIB files keep their bytes.

### IMGW CSV Format Notes

Archive files are inconsistent between years — parsers auto-detect the format per file:

- **Encoding**: CP1250 (Polish Windows encoding) for most archives; `codz_2023.zip` is UTF-8 with BOM (auto-detected)
- **Delimiter**: comma with quoted fields (e.g. 2019-2022, 2024) or semicolon (e.g. 2023) — auto-detected from the first line
- **Quoting**: daily/monthly 2024 files wrap whole lines in outer quotes with doubled inner quotes (auto-unwrapped); some files carry a header row of column codes (skipped)
- **Missing data codes**: `9999` (water level), `99999.999` (flow), `99.9` (temperature); meteo status 8 = `missing`, 9 = `no_phenomenon`
- **Hydrological year**: November 1 - October 31 (month 1 = November)

## Project structure (from README)

Directory tree from the README (moved unchanged); the detailed module tree: "Package Tree" above.

```
src/obserwator/
├── api/          # REST API (FastAPI): routes/commands.py (routes from the catalog), errors.py (problem+json), main.py (/health, /api/v1, /llms.txt, /mcp)
├── cli/          # CLI: _dispatch.py (commands from the catalog), admin.py, config_cmd.py (config show), gui_cmd.py (gui serve), main.py (version, server, mcp, admin, config, gui)
├── mcp/          # MCP server (extra obserwator[mcp]): tools from the catalog, stdio and /mcp
├── _parsing/     # Parsers of IMGW-PIB and ČHMÚ archives, listings and station lists (public: obserwator.parsers)
├── _data/        # Borders of Poland and Czechia (PRG, RÚIAN; ADR-018), guide templates agents/, test fixtures
├── store/        # Versioned store in a raw and a data root (ADR-017): writer, sync, series, catalog, pmaxtp, reader, export, content, plain, analyses, analysis_registry
├── output.py     # Writing plain files (--output-dir): resolve_target, plan_plain, Staging, OutputReport
├── datasets.py   # Registry of providers and 22 datasets (pl.imgw.*, cz.chmi.*), archive file generator
├── commands.py   # Catalog of 35 commands shared by Python, CLI, REST, MCP and integrations
├── agent_guide.py # Guide for agents (AGENTS.md, llms.txt): agent_guide, commands guide
├── fetch.py      # Current data, PMAXTP, archive downloads
├── stations.py   # find_stations (IMGW-PIB and ČHMÚ)
├── urls.py       # IMGW URL constants, build_pmaxtp_url, build_api_url
├── testing.py    # build_fixture_store — offline test roots, raw and data (also PL + CZ)
├── gui/          # Web GUI (obserwator gui serve): Starlette server, the page in web/, texts in messages/gui/
└── config.py     # Configuration (OBSERWATOR_*)

AGENTS.md, llms.txt  # Guide for AI agents — derived files (obserwator commands guide)

docker/           # Docker configuration
tests/            # Tests (offline; store fixtures in tests/fixtures/store; the GUI in Chromium in tests/e2e)
```
