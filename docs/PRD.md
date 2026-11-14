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

## 2. Stakeholders

- Individual users interested in IMGW data
- GIS specialists
- Developers requiring API access to data
- Downstream projects: Hydrograf, Hydrolog, Archiwista (store reader, IMGW-PIB and ČHMÚ), Retman (command handler)
- AI agents and assistants using the tools through MCP, the CLI or REST
- Service administrator (owner)

---

## 3. Functional Scope

### 3.1. Data Access

| Feature | Status | Description |
|---------|--------|-------------|
| Real-time data (IMGW API) | Implemented | Current hydro/meteo/synop data |
| Archive data (ZIP/CSV) | Implemented | Dataset registry (16 `pl.imgw.*` descriptors): URL generation and downloads into an IMGW server-path tree |
| ČHMÚ data (JSON/CSV per station) | Implemented (3.0.0) | 6 `cz.chmi.*` descriptors (daily hydro H/Q/T, daily meteo P/Tmean/Tmax/Tmin with quality and flags, station lists, current station metadata); freshness from directory listings; station catalog with SPA thresholds |
| PMAXTP data | Implemented | Probabilistic max precipitation (IMGW-PIB grid only) |
| Warnings | Implemented | Hydro/meteo warnings from API |
| Versioned store | Implemented (3.0.0) | Immutable versions with provenance (both providers) in a raw root (archives, station sources, PMAXTP cells) and a data root (Parquet series, `stations.geojson` per provider, Hydrolog's stored analyses; ADR-016, ADR-017), freshness plan, canonical content (`content_sha256`) and the observation register for ČHMÚ |
| Projects (pins of store versions) | Moved to Archiwista (ADR-008, 2026-10-31) | Obserwator's project manifest and the `imgw project` command group are removed; Archiwista keeps projects in `archiwista-project/1` and pins versions by the store's `sha256` and `content_sha256` |

### 3.2. Interfaces

| Interface | Status | Description |
|-----------|--------|-------------|
| CLI | Implemented | `obserwator` command: catalog groups `datasets`, `stations`, `current`, `pmaxtp`, `store`, `series`, `analyses`, `commands` plus `version`, `server`, `mcp`, `gui serve`, `admin`, `config show`; help in Polish or English (`OBSERWATOR_LANG`) |
| GUI | Implemented (ADR-013) | `obserwator gui serve` (extra `gui`, with `cli` for the command): a Starlette app of its own on the data root, reading data only through public functions; every station of both providers on a map, the station panel with series, Hydrolog's stored analyses and downloads, PMAXTP of a point |
| REST API | Implemented | FastAPI with OpenAPI documentation; routes generated from the same command catalog; `Accept-Language`; `GET /llms.txt` |
| Python command catalog | Implemented (3.0.0) | 35 commands, `command_schema` and `list_commands` (Polish or English texts, declared effects), `run_command`/`check_command`, envelope `obserwator-result/1`, error registry `ERROR_CODES` |
| MCP server | Implemented (3.0.0) | `obserwator[mcp]`: `obserwator mcp` (stdio, read and plan by default, writes with `--allow-writes`) and `/mcp` in the REST server (read and plan only); tools = catalog commands |

### 3.3. Visualization

| Feature | Status | Description |
|---------|--------|-------------|
| Interactive map | Implemented (GUI) | MapLibre GL JS map of every located station of both catalogs, IMGW-PIB's current measurements and a PMAXTP point |
| Station listings | Implemented (GUI) | The GUI's station list: search by name, river or code ignoring case and diacritics, filters, stations without coordinates included |
| Data charts | Implemented (GUI) | Series and analysis charts in the GUI's own SVG module (zoom, readout by pointer and keys) |

### 3.4. Data Export

| Format | Status | Description |
|--------|--------|-------------|
| JSON | Implemented | Envelope `obserwator-result/1` (CLI stdout, REST body, MCP `structuredContent`); errors as `application/problem+json` |
| URLs | Implemented | Direct links to IMGW-PIB and ČHMÚ servers |
| CSV | Implemented | Station series export (`export_series`, `obserwator series export`) with units and the provider's attribution (IMGW-PIB or ČHMÚ CC BY 4.0); the stations (`export_stations`, `obserwator stations export`); archive export (`export_archive`, CSV or JSONL); PMAXTP of a point in the GUI, packed by the server |
| GeoJSON | Implemented | Versioned `stations.geojson` station catalogs per provider (RFC 7946) in the store; exposed by `export_stations` / `obserwator stations export` / `GET /api/v1/stations/export` (`obserwator-stations-export/1`) and the GUI („Pobierz listę stacji”) |
| Markdown | Implemented | Agent guide `AGENTS.md`/`llms.txt` (`obserwator commands guide`, `GET /api/v1/commands/guide`, `GET /llms.txt`) |
| Parquet | Implemented (store) | Station series per dataset (`obserwator-series/1`, `obserwator[store]`) |

---

## 4. REST API — Requirements

### Implemented

| Requirement | Status |
|-------------|--------|
| OpenAPI/Swagger documentation | Implemented |
| API versioning (`/api/v1/`) | Implemented |
| Catalog routes `/api/v1/<group>/<command>` (datasets, stations, current, pmaxtp, store, series, analyses, commands) | Implemented — 33 routes generated from `command_schema()` (every catalog command but `datasets download` and `store init`) |
| Paging of list commands (`limit`/`cursor`, maximum `OBSERWATOR_API_MAX_LIMIT`) | Implemented |
| Errors as `application/problem+json` with registry codes | Implemented |
| Health check | Implemented |
| Language negotiation (`Accept-Language`, `Content-Language`) | Implemented |
| Agent guide `GET /llms.txt` | Implemented |
| MCP Streamable HTTP `/mcp` (`OBSERWATOR_MCP_ENABLED`) | Implemented — read and plan only |
| Store commands | Implemented — only with the server's `OBSERWATOR_RAW_ROOT` (raw root) and `OBSERWATOR_ROOT` (data root); writes need `OBSERWATOR_STORE_WRITES_ENABLED` + write token |
| Request logging (Nogat's `nogat_logging`: `<state_dir>/obserwator/logs/<kind>-YYYY-MM-DD.jsonl`, kept 14 days, no client addresses) | Implemented (ADR-019) |

### Not Implemented

| Requirement | Status | Notes |
|-------------|--------|-------|
| API key validation | Not Implemented | Keys managed via CLI but not enforced |
| Per-key rate limiting | Not Implemented | Only Nginx-level limiting |

---

## 5. GUI — Requirements

`obserwator gui serve` (ADR-013; usage: `docs/USAGE.md`, „GUI”).

### Implemented

| Requirement | Status |
|-------------|--------|
| A server of its own with a private API relative to its page (not the REST API), on 127.0.0.1:8060 by default; hosted by Nogat's GUI platform through the entry point `nogat.gui`, also under a prefix | Implemented (extra `gui`) |
| Every located station of IMGW-PIB and ČHMÚ on one map (MapLibre GL JS) in hydro.imgw.pl's symbols; search ignoring case and diacritics; filters by provider, kind, dataset and activity; stations without coordinates listed | Implemented |
| A station's panel by kind: description, current IMGW-PIB measurements, IMGW-PIB's levels and extremes of a hydrological station (ADR-021), series as a chart and a table (flags, hydrological or calendar year), analyses, downloads | Implemented |
| „Pomiary bieżące”: IMGW-PIB's current hydrological and meteorological measurements on the map | Implemented |
| Data charts: an own SVG module with zoom and a readout by pointer and keys | Implemented |
| The analyses of the Nogat plan, hydrological and meteorological, every number Hydrolog's: the results stored in the data root (ADR-016) shown as they are; a period, distribution or threshold chosen by the person computed on request | Implemented |
| Downloads: series as CSV, JSON or Parquet, the stations as GeoJSON or CSV, the stored analyses as JSON or CSV, an analysis result as JSON, PMAXTP of a point as CSV or JSON; each with its provider's lines, series, stations and stored analyses with the command line that writes the same file | Implemented |
| Hand-off to Hydrolog (`nogat-handoff/1`) | Implemented |
| PMAXTP of a point picked on the map or by coordinates, without a layer of the grid | Implemented |
| Polish and English, light and dark theme, a phone layout; Nogat's identity and app menu | Implemented |
| Offline map without a basemap (the packaged borders) | Implemented |
| Nogat's rules for a public GUI (DEV-15.7 to DEV-15.12): terms (linked from the left panel, the app menu and the welcome window; the statement of DEV-15.8 in § 3 of the terms), rate limit, logs without addresses, daily totals, „Zgłoś uwagę” | Implemented |
| Admin panel of the GUI (DEV-15.13): `admin/` with „Zgłoszenia”, „Statystyki”, „Stan” behind `OBSERWATOR_ADMIN_API_KEY` (or the file of `OBSERWATOR_ADMIN_API_KEY_FILE`), not a REST API key | Implemented (ADR-020) |
| HTTPS | Through the deployment's authenticating proxy |

### Not Implemented

| Requirement | Status |
|-------------|--------|
| User accounts, sign-in | Not in scope: an authenticating proxy in front of the GUI |
| Climate stripes (M15) | A prototype of the colour scale only (Hydrolog has no stripes yet) |
| IMGW-PIB warnings | Not implemented (warnings name areas, not stations) |
| ČHMÚ current data | Not supported (Obserwator reads no ČHMÚ current data) |
| Other open gaps | `docs/PROGRESS.md`, „GUI: open gaps” |

---

## 6. CLI — Requirements

### Implemented

| Requirement | Status |
|-------------|--------|
| pip installation | Implemented |
| `obserwator datasets`, `obserwator stations`, `obserwator current` (replace `imgw fetch`/`imgw list` of 2.x) | Implemented (3.0.0, generated from the command catalog; `--provider`, `--stations` for ČHMÚ) |
| `obserwator admin` command (REST API keys) | Implemented |
| `obserwator server` command | Implemented |
| `obserwator mcp` command (MCP server on stdio) | Implemented (3.0.0, `obserwator[mcp]`) |
| `obserwator gui serve` command (the GUI) | Implemented (extra `gui` with `cli`, ADR-013) |
| `obserwator store`, `obserwator series`, `obserwator pmaxtp`, `obserwator commands` | Implemented (3.0.0, generated from the command catalog) |
| `imgw project` | Moved to Archiwista (ADR-008, 2026-10-31) |
| `--check` (plan only, no writes), `--schema` (command schema) | Implemented |
| JSON envelope on stdout, JSON error on stderr, exit codes from the error registry | Implemented |
| `--output` flag | Implemented |
| `--station` filtering | Implemented |
| Progress bars | Implemented |

### Commands Available

```bash
# Main commands
obserwator version
obserwator server [--host] [--port] [--reload]
obserwator mcp [--allow-writes] [--allow-dir <dir>]
obserwator gui serve [--host] [--port] [--root] [--no-browser]
obserwator config show [--json]

# Datasets, stations, live data (lists accept --limit/--cursor)
obserwator datasets list [-k hydro|meteo] [--provider IMGW-PIB|CHMI]
obserwator datasets providers
obserwator datasets files -d <dataset> [-y <years>] [-m <months>] [--params H,Q,T] [-s <stations>]
obserwator datasets download -d <dataset> [-y <years>] [-m <months>] [--params] [-s <stations>] [-o <dir> | --root <dir>] [--check]
obserwator stations find [-k hydro|meteo] [-q <query>] [--source live|store] [--root <dir>] [--provider IMGW-PIB|CHMI]
obserwator stations export [--root <dir>] [--provider IMGW-PIB|CHMI] [-k hydro|meteo] [-f geojson|csv] [--output <file> [--force]]
obserwator current hydro|meteo [-s <code>]
obserwator current synop [-s <code>] [--station-name <name>]
obserwator current warnings [-k hydro|meteo]
obserwator current hydro-states [--main-only]
obserwator pmaxtp fetch|url --lat <lat> --lon <lon> [--method POT|AMP]

# REST API keys (not the GUI's admin key)
obserwator admin keys
obserwator admin create --name <name> [--limit]
obserwator admin revoke <key_id>
obserwator admin delete <key_id> [--force]
obserwator admin stats [key_id]

# Versioned store: raw root (archives, station sources, PMAXTP; OBSERWATOR_RAW_ROOT) and data root (series, catalogs, analyses; OBSERWATOR_ROOT)
obserwator store init [--root <dir>] [-k raw|data]
obserwator store info [--root <dir>]
obserwator store scan --root <dir> [-k archive|series|catalog|pmaxtp|analyses|observation|problem] [--provider IMGW-PIB|CHMI]
obserwator store check --root <dir> -d <keys> [-y <years>] [-m <months>] [-s <stations>] [--plan plan.json]
obserwator store sync --root <dir> (--plan plan.json | -d <keys> [-y <years>] [-s <stations>]) [-o <dir>] [--check]
obserwator store catalog --root <dir> [--raw-root <dir>] [--provider IMGW-PIB|CHMI] [--user-locations <csv>] [--check]
obserwator store export --version <archive version> [--format csv|jsonl] [--output <file> [--force]]
obserwator series build --root <dir> [--raw-root <dir>] -d <key> [--check]
obserwator series select --root <dir> -d <key> -s <codes> [--variables] [-y <years>] [--year-type]
obserwator series read|summary [--version <v> | --root <dir> -d <key>] -s <code(s)> [--variables]
obserwator series export [--version <v> | --root <dir> -d <key>] -s <code> [--variables] [-f csv|json|parquet] [--output <file> [--force]]
obserwator pmaxtp check|sync --root <dir> --lat <lat> --lon <lon> [--method POT|AMP]
obserwator pmaxtp read --root <dir> --ind-x <x> --ind-y <y> [--method POT|AMP]

# Hydrolog's stored analyses (data root)
obserwator analyses build --root <dir> [-s <stations>] [--workers <n>] [--check]
obserwator analyses list|read [--version <v> | --root <dir>] -s <code> [--analysis <id>]
obserwator analyses export [--version <v> | --root <dir>] -s <code> [--analyses <ids>] [-f json|csv] [--output <file> [--force]]

# Command catalog
obserwator commands list [--lang pl|en]
obserwator commands schema [--command "<group> <name>"] [--lang pl|en]
obserwator commands guide [-f agents|llms] [--lang pl|en] [--output <file> [--force]]
```

---

## 7. Non-Functional Requirements

| Requirement | Status | Notes |
|-------------|--------|-------|
| No server-side data storage by default | Implemented | Core design principle: URL generation and live proxy; the servers store data only in their configured roots (`OBSERWATOR_RAW_ROOT`, `OBSERWATOR_ROOT`); the CLI and the library write where the person says (`--root`, `--output-dir`, `--output`) or, without it, to the default raw and data roots (ADR-017) |
| PEP8 compliance | Implemented | Using ruff |
| NumPy-style docstrings | Implemented | Enforced by ruff `D` rules, numpy convention |
| Unit and contract tests | Implemented | 3280 tests in `/tests/unit` and `/tests/contract`, all offline (2026-11-14); Python = CLI = REST = MCP contract |
| GUI browser tests | Implemented | 149 tests in `/tests/e2e` (Playwright, Chromium; marker `e2e`, 44 of them also `hydrolog`), skipped without Chromium (2026-11-14) |
| Live integration tests | Implemented | 72 tests marked `live` (outside the gate, run with `-m live`): `tests/live/test_interfaces_live.py` (50: 35 commands × Python/`obserwator`/REST on real IMGW-PIB servers, live errors, MCP leg) and `tests/live/test_chmi_live.py` (22: ČHMÚ on opendata.chmi.cz) (2026-11-14) |
| API response time < 2s | Implemented | For proxied requests |
| Online documentation | Implemented | Swagger at `/docs` |

---

## 8. Out of Scope

The following are explicitly out of scope for this project:
- Advanced hydrological and statistical analyses
- Predictive models
- Machine learning
- Raster processing
- Stream data processing
- User authentication/accounts (MCP over HTTP is read-only; writes need a local `obserwator mcp --allow-writes`)

**Note:** The optional SQLite cache of 2.x was removed in 3.0.0 and replaced by the file-based versioned store (ADR-001); no database is part of the product.

---

## 9. KPIs

| KPI | Target | Current Status |
|-----|--------|----------------|
| API response time (proxied) | < 2s | Met |
| API documentation completeness | 100% | Met (Swagger) |
| Test coverage | 80% | 94.37% (last measured 2026-10-25) |
| Stability (no critical bugs) | 30 days | In progress |

---

## 10. Versioning

- SemVer for API and CLI/GUI package
- Current version: 3.0.0 (release notes: `docs/CHANGELOG.md`)
- Contracts (`obserwator-store/1`, `obserwator-data/1`, `obserwator-meta/1`, `obserwator-series/1`, `obserwator-plan/1`, `obserwator-pmaxtp/1`, `obserwator-observation/1`, `obserwator-result/1`, `obserwator-commands/1`, the stored analyses' `obserwator-analyses/1` and its family) carry their own `/N` versions, independent of the package version (IMGW-13); ČHMÚ and agent support add only optional fields within `/1`; the project manifest contract left with the projects (ADR-008)

---

## 11. Future Enhancements (Backlog)

The backlog is maintained exclusively in `docs/PROGRESS.md` (section "Next") — the single source of truth for pending work.
