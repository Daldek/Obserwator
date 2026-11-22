# Obserwator — PRD (Product Requirements Document)

## 1. Product Goal

Obserwator is a tool for downloading, exposing, versioning and basic visualization of hydrological and meteorological data published by IMGW-PIB and, since 3.0.0, by ČHMÚ (Czech Hydrometeorological Institute, opendata.chmi.cz). The product provides:
- Python library (public API)
- CLI application
- Web GUI (`obserwator gui serve`): the stations of both providers on a map, their series, Hydrolog's analyses and downloads, PMAXTP of a point
- Public REST API
- MCP server for AI agents (`obserwator mcp`, `/mcp`) and a generated agent guide (`AGENTS.md`, `llms.txt`)
- Optional versioned data store in a raw and a data root (ADR-001, ADR-017, `docs/DECISIONS.md`) for consumers such as Archiwista and Retman

Analytical and statistical parts (hydrological calculations, probabilistic models, statistical analyses) live in a separate repository (Hydrolog) and are out of scope for this PRD; the GUI shows Hydrolog's results and computes none itself.

---

## 2. Users

- Individual users interested in IMGW data
- GIS specialists
- Developers requiring API access to data
- Downstream projects: Hydrograf, Hydrolog, Archiwista (store reader, IMGW-PIB and ČHMÚ), Retman (command handler)
- AI agents and assistants using the tools through MCP, the CLI or REST
- Service administrator (owner)

### Scenarios

| ID | Scenario | Requirements |
|---|---|---|
| S1 | A hydrologist downloads the daily discharges of a river's gauges for 1951–2025 as plain files and opens them in a spreadsheet. | FR-1.2, FR-2.1, FR-4.3 |
| S2 | A consumer keeps a reproducible archive: `store check` plans, `store sync` downloads the new archives into the raw root, `series build` and `store catalog` build the data root, and Archiwista pins the versions. | FR-1.6, FR-2.1, FR-4.6 |
| S3 | An engineer takes the PMAXTP design precipitation of a point for a design storm (directly, or through Hydrograf or Hydrolog). | FR-1.4, FR-2.1 |
| S4 | A person browses the stations of Poland and Czechia on a map, reads a station's series and Hydrolog's stored analyses, and downloads them. | FR-2.2, FR-3.1, FR-3.3, FR-5.2 to FR-5.7 |
| S5 | An AI agent discovers the commands, plans a download with `check: true` and runs it through MCP, reading the same envelope and error codes as the CLI. | FR-2.4, FR-2.5, FR-4.1 |

---

## 3. Functional Scope

### 3.1. Data Access

| ID | Feature | Status | Description |
|---|---------|--------|-------------|
| FR-1.1 | Real-time data (IMGW API) | Implemented | Current hydro/meteo/synop data |
| FR-1.2 | Archive data (ZIP/CSV) | Implemented | Dataset registry (21 `pl.imgw.*` descriptors, 9 of them download-only, `in_store` false: ADR-001 D6, ADR-023): URL generation and downloads into an IMGW server-path tree |
| FR-1.3 | ČHMÚ data (JSON/CSV per station) | Implemented (3.0.0) | 6 `cz.chmu.*` descriptors (daily hydro H/Q/T, daily meteo P/Tmean/Tmax/Tmin with quality and flags, since 3.1.0 also the snow depth and new snow; station lists, current station metadata); freshness from directory listings; station catalog with SPA thresholds |
| FR-1.4 | PMAXTP data | Implemented | Maximum precipitation of a given duration and probability of exceedance (IMGW-PIB grid only) |
| FR-1.5 | Warnings | Implemented | Hydro/meteo warnings from API |
| FR-1.6 | Versioned store | Implemented (3.0.0) | Immutable versions with provenance (both providers) in a raw root (archives, station sources, PMAXTP cells) and a data root (Parquet series, `stations.geojson` per provider, Hydrolog's stored analyses; ADR-016, ADR-017), freshness plan, canonical content (`content_sha256`) and the observation register for ČHMÚ |
| FR-1.7 | Projects (pins of store versions) | Moved to Archiwista (ADR-008, 2026-10-31) | Obserwator's project manifest and the `imgw project` command group are removed; Archiwista keeps projects in `archiwista-project/1` and pins versions by the store's `sha256` and `content_sha256` |

### 3.2. Interfaces

| ID | Interface | Status | Description |
|---|-----------|--------|-------------|
| FR-2.1 | CLI | Implemented | `obserwator` command: catalog groups `datasets`, `stations`, `current`, `pmaxtp`, `store`, `series`, `analyses`, `commands` plus `version`, `server`, `mcp`, `gui serve`, `admin`, `config show`; help in Polish or English (`OBSERWATOR_LANG`) |
| FR-2.2 | GUI | Implemented (ADR-013) | `obserwator gui serve` (extra `gui`, with `cli` for the command): a Starlette app of its own on the data root, reading data only through public functions; every station of both providers on a map, the station panel with series, Hydrolog's stored analyses and downloads, PMAXTP of a point |
| FR-2.3 | REST API | Implemented | FastAPI with OpenAPI documentation; routes generated from the same command catalog; `Accept-Language`; `GET /llms.txt` |
| FR-2.4 | Python command catalog | Implemented (3.0.0) | 35 commands, `command_schema` and `list_commands` (Polish or English texts, declared effects), `run_command`/`check_command`, envelope `obserwator-result/1`, error registry `ERROR_CODES` |
| FR-2.5 | MCP server | Implemented (3.0.0) | `obserwator[mcp]`: `obserwator mcp` (stdio, read and plan by default, writes with `--allow-writes`) and `/mcp` in the REST server (read and plan only); tools = catalog commands |

### 3.3. Visualization

| ID | Feature | Status | Description |
|---|---------|--------|-------------|
| FR-3.1 | Interactive map | Implemented (GUI) | MapLibre GL JS map of every located station of both catalogs, IMGW-PIB's current measurements and a PMAXTP point |
| FR-3.2 | Station listings | Implemented (GUI) | The GUI's station list: search by name, river or code ignoring case and diacritics, filters, stations without coordinates included |
| FR-3.3 | Data charts | Implemented (GUI) | Series and analysis charts in the GUI's own SVG module (zoom, readout by pointer and keys) |

### 3.4. Data Export

| ID | Format | Status | Description |
|---|--------|--------|-------------|
| FR-4.1 | JSON | Implemented | Envelope `obserwator-result/1` (CLI stdout, REST body, MCP `structuredContent`); errors as `application/problem+json` |
| FR-4.2 | URLs | Implemented | Direct links to IMGW-PIB and ČHMÚ servers |
| FR-4.3 | CSV | Implemented | Station series export (`export_series`, `obserwator series export`) with units and the provider's attribution (IMGW-PIB or ČHMÚ CC BY 4.0); the stations (`export_stations`, `obserwator stations export`); archive export (`export_archive`, CSV or JSONL); PMAXTP of a point in the GUI, packed by the server |
| FR-4.4 | GeoJSON | Implemented | Versioned `stations.geojson` station catalogs per provider (RFC 7946) in the store; exposed by `export_stations` / `obserwator stations export` / `GET /api/v1/stations/export` (`obserwator-stations-export/1`) and the GUI („Pobierz listę stacji”) |
| FR-4.5 | Markdown | Implemented | Agent guide `AGENTS.md`/`llms.txt` (`obserwator commands guide`, `GET /api/v1/commands/guide`, `GET /llms.txt`) |
| FR-4.6 | Parquet | Implemented (store) | Station series per dataset (`obserwator-series/1`, `obserwator[store]`) |

---

## 4. REST API — Requirements

### Implemented

| ID | Requirement | Status |
|---|-------------|--------|
| FR-6.1 | OpenAPI/Swagger documentation | Implemented |
| FR-6.2 | API versioning (`/api/v1/`) | Implemented |
| FR-6.3 | Catalog routes `/api/v1/<group>/<command>` (datasets, stations, current, pmaxtp, store, series, analyses, commands) | Implemented — 33 routes generated from `command_schema()` (every catalog command but `datasets download` and `store init`) |
| FR-6.4 | Paging of list commands (`limit`/`cursor`, maximum `OBSERWATOR_API_MAX_LIMIT`) | Implemented |
| FR-6.5 | Errors as `application/problem+json` with registry codes | Implemented |
| FR-6.6 | Health check | Implemented |
| FR-6.7 | Language negotiation (`Accept-Language`, `Content-Language`) | Implemented |
| FR-6.8 | Agent guide `GET /llms.txt` | Implemented |
| FR-6.9 | MCP Streamable HTTP `/mcp` (`OBSERWATOR_MCP_ENABLED`) | Implemented — read and plan only |
| FR-6.10 | Store commands | Implemented — only with the server's `OBSERWATOR_RAW_ROOT` (raw root) and `OBSERWATOR_ROOT` (data root); writes need `OBSERWATOR_STORE_WRITES_ENABLED` + write token (`OBSERWATOR_STORE_WRITE_TOKEN` or `…_FILE`) |
| FR-6.11 | Request logging (Nogat's `nogat_logging`: `<state_dir>/obserwator/logs/<kind>-YYYY-MM-DD.jsonl`, kept 14 days, no client addresses) | Implemented (ADR-019) |
| FR-6.14 | Cross-origin access only from the configured origins (`OBSERWATOR_CORS_ORIGINS`, none by default), never with credentials; the security headers the GUI sends (`nosniff`, `Referrer-Policy`, `Permissions-Policy`) | Implemented (3.1.0) |
| FR-6.15 | An operator's instance (`[obserwator.instance]` of `nogat.toml`): the providers and the area served, filtered on the server for every route | Implemented (3.1.0, ADR-025) |

### Not Implemented

| ID | Requirement | Status | Notes |
|---|-------------|--------|-------|
| FR-6.12 | API key validation | Not planned | The REST API keys of `obserwator admin` are checked by nothing, deprecated and removed in v4.0.0 (ADR-025 D10); store writes use the one write token |
| FR-6.13 | Per-key rate limiting | Not Implemented | Only Nginx-level limiting |

---

## 5. GUI — Requirements

`obserwator gui serve` (ADR-013; usage: `docs/USAGE.md`, „GUI”).

### Implemented

| ID | Requirement | Status |
|---|-------------|--------|
| FR-5.1 | A server of its own with a private API relative to its page (not the REST API), on 127.0.0.1:8060 by default; hosted by Nogat's GUI platform through the entry point `nogat.gui`, also under a prefix | Implemented (extra `gui`) |
| FR-5.2 | Every located station of IMGW-PIB and ČHMÚ on one map (MapLibre GL JS) in hydro.imgw.pl's symbols; search ignoring case and diacritics; filters by provider, kind, dataset and activity; stations without coordinates listed | Implemented |
| FR-5.3 | A station's panel by kind: description, current IMGW-PIB measurements, IMGW-PIB's levels and extremes of a hydrological station (ADR-021), series as a chart and a table (flags, hydrological or calendar year), analyses, downloads | Implemented |
| FR-5.4 | „Pomiary bieżące”: IMGW-PIB's current hydrological and meteorological measurements on the map | Implemented |
| FR-5.5 | Data charts: an own SVG module with zoom and a readout by pointer and keys | Implemented |
| FR-5.6 | The analyses of the Nogat plan, hydrological and meteorological, every number Hydrolog's: the results stored in the data root (ADR-016) shown as they are; a period, distribution or threshold chosen by the person computed on request | Implemented |
| FR-5.7 | Downloads: series as CSV, JSON or Parquet, the stations as GeoJSON or CSV, the stored analyses as JSON or CSV, an analysis result as JSON, PMAXTP of a point as CSV or JSON; each with its provider's lines, series, stations and stored analyses with the command line that writes the same file | Implemented |
| FR-5.8 | Hand-off to Hydrolog (`nogat-handoff/1`) | Implemented |
| FR-5.9 | PMAXTP of a point picked on the map or by coordinates, without a layer of the grid | Implemented |
| FR-5.10 | Polish and English, light and dark theme, a phone layout; Nogat's identity and app menu | Implemented |
| FR-5.11 | Offline map without a basemap (the packaged borders) | Implemented |
| FR-5.12 | Nogat's rules for a public GUI (DEV-15.7 to DEV-15.12): terms (linked from the left panel, the app menu and the welcome window; the statement of DEV-15.8 in § 3 of the terms), rate limit, logs without addresses, daily totals, „Zgłoś uwagę” | Implemented |
| FR-5.13 | Admin panel of the GUI (DEV-15.13): `admin/` with „Zgłoszenia”, „Statystyki”, „Stan” behind `OBSERWATOR_ADMIN_API_KEY` (or the file of `OBSERWATOR_ADMIN_API_KEY_FILE`), not a REST API key | Implemented (ADR-020) |
| FR-5.20 | An operator's instance (ADR-025): providers `visible`, `hidden` or `off`, a featured provider with the others faded (`others_opacity`) until „Pokaż inne źródła”, an area (`focus` or `clip`), the start view, PMAXTP on or off, the operator's title, logo and regulamin | Implemented (3.1.0) |
| FR-5.14 | HTTPS | Through the deployment's authenticating proxy |

### Not Implemented

| ID | Requirement | Status |
|---|-------------|--------|
| FR-5.15 | User accounts, sign-in | Not in scope: an authenticating proxy in front of the GUI |
| FR-5.16 | Climate stripes (M15) | A prototype of the colour scale only (Hydrolog has no stripes yet) |
| FR-5.17 | IMGW-PIB warnings | Not implemented (warnings name areas, not stations) |
| FR-5.18 | ČHMÚ current data | Not supported (Obserwator reads no ČHMÚ current data) |
| FR-5.19 | Other open gaps | `docs/PROGRESS.md`, „GUI: open gaps” |

---

## 6. CLI — Requirements

### Implemented

| ID | Requirement | Status |
|---|-------------|--------|
| FR-7.1 | Installation from Git by tag (not on PyPI; README "Install") | Implemented |
| FR-7.2 | `obserwator datasets`, `obserwator stations`, `obserwator current` (replace `imgw fetch`/`imgw list` of 2.x) | Implemented (3.0.0, generated from the command catalog; `--provider`, `--stations` for ČHMÚ) |
| FR-7.3 | `obserwator admin` command (REST API keys) | Implemented; deprecated, removed in v4.0.0 (ADR-025 D10) |
| FR-7.4 | `obserwator server` command | Implemented |
| FR-7.5 | `obserwator mcp` command (MCP server on stdio) | Implemented (3.0.0, `obserwator[mcp]`) |
| FR-7.6 | `obserwator gui serve` command (the GUI) | Implemented (extra `gui` with `cli`, ADR-013) |
| FR-7.7 | `obserwator store`, `obserwator series`, `obserwator pmaxtp`, `obserwator commands` | Implemented (3.0.0, generated from the command catalog) |
| FR-7.8 | `imgw project` | Moved to Archiwista (ADR-008, 2026-10-31) |
| FR-7.9 | `--check` (plan only, no writes), `--schema` (command schema) | Implemented |
| FR-7.10 | JSON envelope on stdout, JSON error on stderr, exit codes from the error registry | Implemented |
| FR-7.11 | `--output` flag | Implemented |
| FR-7.12 | `--station` filtering | Implemented |
| FR-7.13 | Progress bars | Implemented |

The commands and their options are listed by `obserwator commands list` and `obserwator <group> <command> --help` (generated from the catalog); the task-oriented guide is `docs/USAGE.md`.

---

## 7. Non-Functional Requirements

| ID | Requirement | Status | Notes |
|---|-------------|--------|-------|
| NFR-1 | No server-side data storage by default | Implemented | Core design principle: URL generation and live proxy; the servers store data only in their configured roots (`OBSERWATOR_RAW_ROOT`, `OBSERWATOR_ROOT`); the CLI and the library write where the person says (`--root`, `--output-dir`, `--output`) or, without it, to the default raw and data roots (ADR-017) |
| NFR-2 | PEP8 compliance | Implemented | Using ruff |
| NFR-3 | NumPy-style docstrings | Implemented | Enforced by ruff `D` rules, numpy convention |
| NFR-4 | Unit and contract tests | Implemented | 3325 tests in `/tests/unit` and `/tests/contract`, all offline (2026-11-15); Python = CLI = REST = MCP contract |
| NFR-5 | GUI browser tests | Implemented | 152 tests in `/tests/e2e` (Playwright, Chromium; marker `e2e`, 44 of them also `hydrolog`), skipped without Chromium (2026-11-15) |
| NFR-6 | Live integration tests | Implemented | 72 tests marked `live` (outside the gate, run with `-m live`): `tests/live/test_interfaces_live.py` (50: 35 commands × Python/`obserwator`/REST on real IMGW-PIB servers, live errors, MCP leg) and `tests/live/test_chmu_live.py` (22: ČHMÚ on opendata.chmi.cz) (2026-11-15) |
| NFR-7 | API response time < 2s | Implemented | For proxied requests |
| NFR-8 | Online documentation | Implemented | Swagger at `/docs` |

---

## 8. Out of Scope

| Out of scope | Reason | Covered by |
|---|---|---|
| Hydrological and statistical analyses | Obserwator downloads and serves data; computation belongs to one tool | Hydrolog (Obserwator stores its answers, ADR-016) |
| Forecasts and predictive models | Obserwator reads published observations only | the forecasts of IMGW-PIB (meteo.imgw.pl) and ČHMÚ (chmi.cz) |
| Machine learning | not a data-access task | none in the ecosystem |
| Raster and other spatial data (elevation, land cover, soils) | another domain and other providers | Kartograf |
| Stream data processing | the sources publish files and snapshots, not streams | none |
| Projects that pin store versions | one owner of projects in the ecosystem (ADR-008) | Archiwista |
| User authentication and accounts | the servers stay read-only or behind a proxy; MCP over HTTP is read-only, writes need a local `obserwator mcp --allow-writes` | an authenticating proxy (the GUI, REST) |

**Note:** The optional SQLite cache of 2.x was removed in 3.0.0 and replaced by the file-based versioned store (ADR-001); no database is part of the product.

---

## 9. Success Criteria (KPIs)

| KPI | Target | Current Status |
|-----|--------|----------------|
| API response time (proxied) | < 2s | Met |
| API documentation completeness | 100% | Met (Swagger) |
| Test coverage | 80% | 94.54% (last measured 2026-11-15) |
| Stability (no critical bugs) | 30 days | In progress |

---

## 10. Versioning

- SemVer for API and CLI/GUI package
- Current version: 3.1.0 (release notes: `docs/CHANGELOG.md`)
- Contracts (`obserwator-store/1`, `obserwator-data/1`, `obserwator-meta/1`, `obserwator-series/1`, `obserwator-plan/1`, `obserwator-pmaxtp/1`, `obserwator-observation/1`, `obserwator-result/1`, `obserwator-commands/1`, the stored analyses' `obserwator-analyses/1` and its family) carry their own `/N` versions, independent of the package version (IMGW-13); ČHMÚ and agent support add only optional fields within `/1`; the project manifest contract left with the projects (ADR-008)

---

## 11. Future Enhancements (Backlog)

The backlog is maintained exclusively in `docs/PROGRESS.md` (section "Next") — the single source of truth for pending work.
