# Obserwator — Architecture

## 1. Architecture Model

System consists of six main components:

1. **Python Library** (v3.0.0)
   - `pip install obserwator` for integration with external projects
   - Sync and async functions for live data and archive downloads (`DownloadResult`, `download_archives`)
   - Provider registry (`IMGW-PIB`, `CHMI` — ČHMÚ, ADR-003) and dataset registry (22 descriptors: 16 `pl.imgw.*`, 6 `cz.chmi.*`, with slugs and legacy aliases), IMGW-PIB and ČHMÚ parsers with value flags
   - Command catalog (`obserwator.commands`): 35 commands, one envelope `obserwator-result/1`, one error registry `ERROR_CODES` (ADR-002); Polish texts with an English variant, declared effects (`writes`, `network`, `idempotent`) and the agent guide `agent_guide` (ADR-004)
   - Minimal dependencies (httpx, platformdirs, pydantic, pydantic-settings)

2. **Versioned Store** [Parquet: `obserwator[store]`] in two roots (ADR-017)
   - Raw root (marker `obserwator-store.json`): append-only, immutable versions of IMGW-PIB and ČHMÚ archives with provenance sidecars, the station sources of the catalogs and the PMAXTP cells; the downloads write only here
   - Data root (marker `obserwator-data.json`): Parquet station series, `stations.geojson` per provider and the stations' analyses computed by Hydrolog's program and stored as its answers (ADR-016; Obserwator computes no number), built from the raw root, which the builders only read
   - Default roots in the user data directory (`<data_dir>/obserwator-raw` and `<data_dir>/obserwator`), or `--root`, `OBSERWATOR_RAW_ROOT` and `OBSERWATOR_ROOT`, `[obserwator] raw_root` and `root` (and `--raw-root` of a build); readable offline, also from network shares
   - Decision records: `docs/DECISIONS.md` (ADR-001 store, ADR-002 interfaces, ADR-003 ČHMÚ provider and open `/1` domains, ADR-004 agent support, ADR-015 raw data only in `store sync`, ADR-016 stored analyses computed by Hydrolog, ADR-017 the data root); contracts: `docs/superpowers/specs/2026-10-17-versioned-store-design.md`, `2026-10-18-chmi-provider-design.md`, `2026-10-19-agent-support-design.md`

3. **Backend (FastAPI)** [optional: `obserwator[api]`]
   - Routes `/api/v1/<group>/<command>` generated from the command catalog (33 commands; local-only commands have no route)
   - URL generation for IMGW-PIB and ČHMÚ downloads and live IMGW data
   - Store commands only with the explicit server-side root of their kind: `OBSERWATOR_RAW_ROOT` (raw root) or `OBSERWATOR_ROOT` (data root); `series build` and `store catalog` need both
   - Errors as `application/problem+json`; language negotiation (`Accept-Language`, English by default); `GET /llms.txt`; optional MCP endpoint `/mcp`; rate limiting via Nginx

4. **MCP Server** [optional: `obserwator[mcp]`]
   - `obserwator mcp` (stdio) and `/mcp` (Streamable HTTP inside the REST app); tools generated from the command catalog
   - Read and plan only by default; writes only with `--allow-writes` and `check: false` (stdio), and only inside the `--allow-dir` directories

5. **GUI** [optional: `obserwator[gui]`; the command also needs `obserwator[cli]`]
   - `obserwator gui serve` (ADR-013): a Starlette app of its own on 127.0.0.1:8060 with a private API relative to its page; Nogat's GUI platform finds it through the entry point `nogat.gui`
   - Every station of IMGW-PIB and ČHMÚ on a MapLibre map, the station panel (description, current IMGW-PIB values, series chart and table, Hydrolog's analyses, downloads), PMAXTP of a point; Preact + htm without a build step
   - Reads the data root read-only through public functions, Hydrolog's stored analyses (ADR-016) among it; IMGW-PIB's current data and PMAXTP pass through the server's memory; a person's choices are computed by Hydrolog's program on request

6. **CLI** [optional: `obserwator[cli]`]
   - Local client using the library directly (never through the REST API)
   - Groups `datasets`, `stations`, `current`, `pmaxtp`, `store`, `series`, `analyses`, `commands` generated from the command catalog; help in Polish or English (`OBSERWATOR_LANG`)
   - `obserwator mcp`, `obserwator server`, `obserwator gui serve`, REST API key management (`obserwator admin`; not the GUI's admin key)

---

## 2. Component Diagram

```
┌──────────────────────────────────────┐ ┌──────────────────────────────────┐
│            IMGW-PIB                  │ │              ČHMÚ                │
│ danepubliczne.imgw.pl, hydro.imgw.pl,│ │ opendata.chmi.cz (historical,    │
│ hydro-back.imgw.pl, klimat.imgw.pl   │ │ historical_csv, metadata, now)   │
└──────────────────────────────────────┘ └──────────────────────────────────┘
                              ▲            ▲
                              │ HTTP (URL generation, live proxy, listing/HEAD/GET
                              │ for the store; one request at a time)
┌─────────────────────────────────────────────────────────────────┐
│                       obserwator (library)                        │
│  ┌────────────┐ ┌────────────┐ ┌──────────────┐ ┌────────────┐  │
│  │ urls       │ │ fetch /    │ │ datasets     │ │ parsers    │  │
│  │            │ │ stations   │ │ (providers,  │ │ (_parsing) │  │
│  │            │ │            │ │  registry)   │ │            │  │
│  └────────────┘ └────────────┘ └──────────────┘ └────────────┘  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ store/: writer · content · sync · series · catalog ·      │   │
│  │         pmaxtp · reader · export                          │   │
│  └──────────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ commands.py: catalog · validate · run/check · schema      │   │
│  │ agent_guide.py: AGENTS.md / llms.txt                      │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
     ▲          ▲            ▲            ▲           ▲         ▲
     │          │            │            │           │         │
 ┌───────┐ ┌─────────┐ ┌───────────┐ ┌─────────┐ ┌──────────┐ ┌─────────────┐
 │  CLI  │ │ FastAPI │ │    GUI    │ │MCP stdio│ │Archiwista│ │   Retman    │
 │(local)│ │ + /mcp  │ │(gui serve)│ │  (mcp)  │ │(read API)│ │(run_command)│
 └───────┘ └─────────┘ └───────────┘ └─────────┘ └──────────┘ └─────────────┘
                ▲            ▲            ▲
                │            │            └── stdio: MCP clients (editor, chat app)
                │            └── HTTPS through an authenticating proxy: browsers
                └── HTTPS (Nginx: reverse proxy, rate limiting): API and MCP clients
```

The GUI also runs Hydrolog's program for the analyses it computes on request (section 5).

---

## 3. Backend Layer

### Technologies (Implemented)
- Python 3.12+
- FastAPI 0.100+
- HTTPX (async HTTP client)
- Pydantic v2 (validation)
- Uvicorn (ASGI server)
- Nginx (reverse proxy)

### Technologies (Not Used)
- ~~Redis (cache)~~ - not needed
- ~~SQLite / PostgreSQL~~ - the optional SQLite cache was removed in 3.0.0 (ADR-001 D5); the versioned store keeps files, not a database

### Key Design Principle
**No data storage on the server by default.** Without configuration the backend only:
1. Generates URLs pointing to IMGW-PIB and ČHMÚ servers
2. Proxies real-time API requests to IMGW-PIB
3. Returns results directly to the client

Data is written only after explicit configuration: an absolute `OBSERWATOR_RAW_ROOT` enables the commands of the raw root and an absolute `OBSERWATOR_ROOT` those of the data root, and `series build` and `store catalog` need both (ADR-017; otherwise 503 `store_unavailable` with `details.reason="not_configured"` naming the variable; a root that is relative or no supported root is 503 with `root_invalid` or `unsupported`, a root of the other kind 503 with `wrong_root`), and writes additionally need `OBSERWATOR_STORE_WRITES_ENABLED=true`, a non-empty `OBSERWATOR_STORE_WRITE_TOKEN` and a matching `X-API-Key` header (otherwise 403 `forbidden`). The server never writes to a default root and takes no `root`, `raw_root`, `output_dir`, `output` or `force` in a request (400 `validation_error`). Locally, the CLI and the library write to `--output-dir` (plain files), `--root` (a root of the store) or, with neither, to the default root of the command's kind, never to the working directory (section 8, "Data Output").

---

## 4. REST API

### Implemented Features
- Routes generated from the catalog (`x-obserwator.rest` of the internal input schemas) by `api/routes/commands.py`: `GET` for reads (options in the query; lists comma-separated or repeated), `POST` for `store sync`, `store catalog`, `series build`, `pmaxtp sync` (options in a JSON body; `?check=true` returns the plan without writing)
- Response body = `CommandResult.to_json(root, server=True, lang=)`, identical to the CLI envelope except hidden server paths and the language of the texts; list commands page with `limit` (default/maximum `OBSERWATOR_API_MAX_LIMIT`) and `cursor` (`page.next_cursor`); `store export`/`series export` stream CSV/JSONL with `X-Obserwator-Notices`/`X-Obserwator-Status` headers
- Errors: `api/errors.py` turns every `ObserwatorError`, request validation error, HTTP error, `OSError` and unexpected exception into `application/problem+json` with `code`, `details`, `hint` (when one fits) and the status of `ERROR_CODES` (validation always 400)
- `GET /api/v1` (name, version, schema route, catalog routes), `GET /health`, `GET /llms.txt` (agent guide in the language of `Accept-Language`, English by default), OpenAPI/Swagger documentation (`/docs`, English; `GET /` redirects to it)
- Language (AGI-6.4, AGI-9.2): the texts of an answer (notices, item and plan texts, the `title`, `detail` and `hint` of problem+json) follow `?lang=` of a command with the option `lang` (`commands list`, `commands schema`, `commands guide`), else `Accept-Language` (RFC 9110 weights, first subtag), else English; every command answer has `Content-Language`, and `Vary: Accept-Language` when the header decided
- Optional `/mcp` (MCP Streamable HTTP, `OBSERWATOR_MCP_ENABLED=true`): the SDK session manager runs in the app lifespan, tools call the REST routes in process (section 7)

### Security (Current State)
- Rate limiting via Nginx (`limit_req_zone`)
- CORS middleware configured
- GZip compression enabled
- Store routes: server-side roots only (clients never pass a root, a raw root or an absolute path; `version` is confined to `*/versions/` under the command's root, no `..`, symlinks rejected), write token compared in constant time, unknown/server-only/local options rejected (400 `validation_error`); answers hide server directories (both roots, `OBSERWATOR_USER_LOCATIONS_DIR`, `OBSERWATOR_DATA_DIR`, TMPDIR, CWD)
- `/mcp`: off by default (`OBSERWATOR_MCP_ENABLED`), read and plan only (POST routes always with `?check=true`, so the write token is never used), `Host` restricted to `OBSERWATOR_MCP_ALLOWED_HOSTS`, browser origins refused by the SDK (403); nginx `location = /mcp` shares the `api_limit` zone

### Security (Planned, Not Implemented)
- ~~API key validation middleware~~ - keys managed but not enforced (store writes use their own token)
- ~~Per-key rate limiting~~ - only nginx-level limiting
- ~~MCP writes over HTTP with authorization~~ - out of 3.0.0 (ADR-004 open question)

---

## 5. GUI Layer

`obserwator gui serve` (ADR-013; package `obserwator.gui`, outside `obserwator.__all__`; extra `obserwator[gui]` = `[store]` + Starlette + uvicorn, and `[cli]` for the command) is a server of its own, never mounted in the REST app, so only the GUI's routes reach its address. It reads Obserwator's data only through its public functions (it uses the internal helpers `_environment`, `_jsonable` and `_hydrolog` for settings, JSON and Hydrolog's program) and computes nothing itself: every number of an analysis is Hydrolog's. Running it, its settings and its public rules: `docs/USAGE.md`, section „GUI”.

### Technologies (Implemented)
- **Starlette** under **uvicorn**, one process (FastAPI was rejected: the private routes need neither OpenAPI nor pydantic); blocking reads and exports run in worker threads, at most four at a time
- **Preact 10.29.8 + htm 3.1.1** as ES modules without a build step, vendored byte for byte with their licences and SHA-256 (`gui/web/vendor/vendor.json`)
- **MapLibre GL JS 6.14.0**, vendored with its module worker (a same-origin file) and the Noto Sans glyphs; the basemap is a TileJSON from settings (OpenFreeMap's by default) drawn in the GUI's own grey style, or offline the packaged borders of Poland and Czechia
- **An own SVG chart module** (`gui/web/src/charts/`): linear, log, date, time and Gumbel-probability axes; lines, steps, areas, bands, bars, points and reference marks; long series decimated to the first, last, lowest and highest point per pixel column; zoom and a readout by pointer and keys
- **Nogat's identity**: copies of `tokens.css` (Nogat `55a2d4b`), the marks and kit 0.6.0 (`nogat-app-menu.*`, `nogat-sources.*`, `nogat-handoff.js`, `nogat-terms.*`), byte for byte with their manifests (DEV-15.3, DEV-15.6); light and dark theme; the top bar, side panels that resize, bottom sheets at 860 px and below
- **Provider lines on screen** (DEV-20.5, ECO-064): one compact `<nogat-sources>` of the kit per view, across the page under the map and both panels, fed the union of the lines of what the list and the map show and of what the right panel shows (the station's header, its open cards and their results, the stations files or PMAXTP's tables), the basemap's credit after it; never per panel or card; on a phone the sheets stop above it. S, P, PS, PP and the short ČHMÚ line on screen, every line and the terms behind „Źródła i warunki”; a welcome window on the first visit with the same full content (`fillSources`). Files, images, hand-offs and the API keep the full lines
- **Texts**: the area `gui` of the message catalog (`messages/gui/`, `Text(en, pl)`, ADR-006), served by `api/texts`; Polish by default, English through „PL | EN”

### Routes
Relative to the page, so the app works at `/` and under any prefix (Nogat's GUI platform mounts it through the entry point `nogat.gui`). GET includes HEAD; any other method is `405` with `Allow`; another `api/…` address is `404`.

| Route | Method | Answer |
|-------|--------|-------------|
| `/` and the other static files of `gui/web/` (`instrukcja/`: the guide in Polish) | GET | the page |
| `api/session`, `api/texts` | GET | versions, the data root in use (its catalogs, series and stored analyses), providers and their lines, basemap, `[nogat.gui]`, terms; the texts |
| `api/stations`, `api/stations/{code}` | GET | the station layer of the current catalogs; one station |
| `api/series/{dataset}/{code}` | GET | a station's series: dates, values, flags |
| `api/analyses/{code}`, `api/analysis/{code}/{id}` | GET | the stored analyses of a station; one result (`obserwator-analysis/1`), the stored one or one computed with the person's options |
| `api/current`, `api/current/{code}` | GET | IMGW-PIB's current measurements |
| `api/pmaxtp` | GET | PMAXTP of a point |
| `api/downloads/{code}`, `api/downloads/stations` | GET | the files offered (a station's series and stored analyses, the stations), each with its command line and licence |
| `api/files/series/{dataset}/{code}`, `api/files/stations`, `api/files/analyses/{code}`, `api/files/analysis/{code}/{id}`, `api/files/pmaxtp` | GET | the files |
| `api/handoff/{code}` | GET | `nogat-handoff/1` around `hydrolog-series/1` |
| `api/prototype/stripes/{code}` | GET | the climate stripes (M15), a prototype of their colour scale |
| `api/feedback` | POST | „Zgłoś uwagę” |
| `admin` (308), `admin/` | GET | the admin panel: the kit's `<nogat-admin>` (Nogat DEV-15.13, ADR-020) |
| `api/admin/feedback`, `api/admin/feedback/{id}` | GET; PATCH, DELETE | the reports, newest first; one marked read or unread, or deleted |
| `api/admin/stats`, `api/admin/status` | GET | the days of `stats.jsonl` with today; the app, its directory and disk, its checks |
| `regulamin.html` | GET | the terms of a public deployment |
| `data/{poland,czechia}_border_wgs84.geojson` | GET | the packaged borders |

### Data Flow
- **Data root**, read-only (`_root.py`): the current catalog of each provider, the current series of each dataset and the current stored analyses of each provider through `current_version`, `read_catalog`, `read_series_index`, `read_series` and `export_stations`; the current versions are asked again at most once a minute, so a new build shows without a restart (new stored analyses alone keep the station layer and its ETag); in memory the station layer, the 32 most recent series documents and 4 stations files; answers carry a strong ETag (the versions, the query and a token of the run) and `Cache-Control: no-cache`.
- **Live data** (`_live.py`), in memory only: snapshots of IMGW-PIB's current data (water states, hydro, meteo, synop), each fetched on demand at most once per 10 minutes, one request at a time, the last kept when a fetch fails; PMAXTP per method and point at four decimals for 24 hours, at most 1,000 points, one live request at a time.
- **Analyses** (`_analyses.py`): Hydrolog's results stored in the data root by `analyses build` (`list_analyses`, `read_analysis`), shown as they are; a person's choices (and the climate stripes' reference period) computed on request by `compute_analysis` through Hydrolog's program (`OBSERWATOR_HYDROLOG_COMMAND`, else `hydrolog` on `PATH`, looked for once when the app starts; without it only stored results): at most two processes of 30 s, 500 results in memory, never written.
- **Files**: `export_series`, `export_stations` and `export_analyses` write them byte for byte as the CLI does; PMAXTP of a point is packed by the server (CSV, JSON); a hand-off is built by the server from the data root or from Hydrolog's result.
- **Own files** in `<data_dir>/obserwator`: `stats.jsonl`, `feedback.jsonl` (rewritten atomically under its `flock` when the admin panel marks or deletes a report); neither when that directory and the data root are one or one holds the other.
- **Logs** in `<state_dir>/obserwator/logs` (Nogat DEV-12.4 to DEV-12.9): `obserwator gui serve` starts a `ServerLog` of `obserwator.nogat_logging` (Nogat's reference module, copied byte for byte and shared with `obserwator server`) and `build_app` adds its `AccessLog` as the outermost middleware, outside `Traffic`, so the rate limit's `429` is logged too; static content (`QUIET` of `_app.py`) only from status 400; stderr gets only the lifecycle records and reduced errors.
- The page connects only to its own origin and the basemap's.

### Security
- Every answer (`SecurityHeaders` of `_app.py`): `Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self'; worker-src 'self'; img-src 'self' data: blob: <basemap origin>; connect-src 'self' <basemap origin>; font-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'`, `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, `Cross-Origin-Opener-Policy: same-origin`, `Cross-Origin-Resource-Policy: same-origin`, `Permissions-Policy: camera=(), microphone=(), geolocation=()`, `Cache-Control: no-cache` unless the answer sets another
- No cookies, sessions or CORS headers; no inline script or style and no remote resource but the basemap
- Every parameter is checked against the registries before the data root or Hydrolog is touched (DEV-13.3); errors are `obserwator-error/1` in the page's language with the server's directories hidden (root, own directory, TMPDIR, CWD); Hydrolog gets only checked options and series files the server wrote
- No sign-in but the admin panel's: the GUI binds `127.0.0.1` by default and is reachable beyond it only behind an authenticating proxy (`FORWARDED_ALLOW_IPS` names the proxy to uvicorn); `admin/` and `api/admin/…` (`_admin.py`) check `X-Admin-Key` in constant time against `OBSERWATOR_ADMIN_API_KEY` or the file of `OBSERWATOR_ADMIN_API_KEY_FILE`, read on every request (`401 unauthorized` otherwise), and answer with `Cache-Control: no-store` under CSP `'self'`

### Public Rules (Nogat DEV-15.7 to DEV-15.12)
- `Traffic` (`_traffic.py`), an ASGI middleware: the rate limit per client address (300 requests in 60 s by default, static files not counted, `429` with `Retry-After`), the daily totals in `stats.jsonl` (visitors as keyed hashes kept in memory); the access log is `AccessLog`'s, outside it (Logs above); uvicorn keeps no log of its own
- `_feedback.py`: `POST api/feedback` appends a report of „Zgłoś uwagę” to `feedback.jsonl`; `_admin.py` (DEV-15.13) lists, marks and deletes reports, shows the daily totals and the status checks `data_root_marker`, `stored_analyses`, `hydrolog_command`; the panel's requests stay under the rate limit and out of the totals
- `_terms.py`: with `[nogat.operator]` and the `obserwator` address of `[nogat.gui]`, `regulamin.html` filled from kit 0.6.0 (its source blocks link each provider's terms, no summary of them); the page then shows „Regulamin” and the statement in every view

---

## 6. CLI Layer

### Technologies
- **Typer** (Click) - CLI framework; catalog groups via a custom Click group
- **Rich** - terminal formatting (`version`, `server`, `mcp`, `admin`)
- **HTTPX** - HTTP client

### Architecture
The CLI uses the library directly and downloads data straight from IMGW-PIB and ČHMÚ servers; it does NOT communicate through the REST API. All catalog groups (`datasets`, `stations`, `current`, `pmaxtp`, `store`, `series`, `commands`) are generated from `command_schema()` by `cli/_dispatch.py` (`ObserwatorGroup` + `register_catalog`): help texts and flags come from the catalog, raw option text goes to `run_command` (or `check_command` for `--check`), `--schema` prints the command schema. With `--json` stdout is the one-line JSON envelope `obserwator-result/1`, without it a short summary for a person in the language of `--lang` (`cli/_render.py`: status, the items of a list as a table of key fields and the page, the main fields of a document, the notices) (streams for `store export`/`series export`/`commands guide` without `--output`; with it the envelope result is `{output, files[]}`), with `--json` notices go to stderr once, errors are the `obserwator-error/1` document (`schema`, `code`, `title`, `message`, `hint`?, `details`, `exit_code`, `command`?; `error_report.py`) as the last stderr line with the exit code of `ERROR_CODES` (envelope status: `partial` 10, `failed` 11, `cancelled` 130). The CLI therefore has no validation or business rules of its own — CLI = Python API = REST = MCP (`tests/contract/test_interface_contract.py`, `test_mcp_contract.py`). `OBSERWATOR_LANG=pl|en` picks the help language once at import (catalog texts, group descriptions and the Typer/Click elements such as „Opcje”/„Options”, „Użycie:”/„Usage:”, `[OPCJE]`, „Przerwano.”); an invalid value ends every `obserwator` call with a `validation_error` line (exit 2). `obserwator version`, `obserwator server`, `obserwator mcp`, `obserwator gui serve` (section 5) and `obserwator admin` stay outside the catalog (Polish help).

---

## 7. MCP Server Layer

### Technologies
- Official MCP SDK `mcp>=2.3,<3` (low-level `Server`), extra `obserwator[mcp]` = `[cli]` + `mcp`; the core never imports it

### Architecture
`src/obserwator/mcp/` is the fourth adapter of the command catalog (ADR-004 D6–D9), outside `obserwator.__all__`:
- `_tools.py` — one tool per catalog command: name = the catalog `operation_id` (`obserwator_<group>_<verb>`, ECO-018), title `obserwator <command>`, description with rules, input schema = the internal JSON Schema of the options (`commands._input_schema`, without `$schema`, `title`, `x-obserwator`), annotations `title`, `readOnlyHint`, `destructiveHint` (`replace`; false when read-only), `idempotentHint` (`idempotent`), `openWorldHint` (`network`); list commands get `limit` default 50.
- `_calls.py` — stdio: `check_command`/`run_command` in a worker thread with `on_progress` → `notifications/progress`, `on_notice` → envelope and `cancel` ← request cancellation; http: the same request a REST client would send, dispatched in process to `obserwator.api.main:app` (POST always with `?check=true`, `Accept-Language` = server language).
- `server.py` — `create_server(*, mode, allow_dirs)`, `run_stdio(*, allow_writes, allow_dirs)` (used by `obserwator mcp`), `http_app()` (route `/mcp` added to the REST app when `OBSERWATOR_MCP_ENABLED=true`; hosts from `OBSERWATOR_MCP_ALLOWED_HOSTS`). `allow_dirs` = the repeatable `--allow-dir`: every path option, `root` and `raw_root` with their defaults included, must lie inside one, and a writing command without any gets only a plan; the instructions of a stdio server name the default data and raw roots.

| Mode | Start | Tools | Writes |
|---|---|---|---|
| `read` (default) | `obserwator mcp` | 35 | none: writing commands have `check` fixed `true` (plan `obserwator-plan/1`), writing options (`output_dir`, `output`, `force`, `plan`) removed |
| `write` | `obserwator mcp --allow-writes --allow-dir DIR` / `OBSERWATOR_MCP_ALLOW_WRITES=true` | 35 | `check` defaults to `true`; writes with `check: false`, only inside `--allow-dir` (an absent `root` is the default root of the command's kind and an absent `raw_root` the default raw root, which must lie inside too) |
| `http` | `obserwator server` + `OBSERWATOR_MCP_ENABLED=true` → `/mcp` | 33 (commands with a REST route) | none (REST rules: the server's roots, `version` under `*/versions/`, hidden server paths) |

Results: `structuredContent` = envelope `obserwator-result/1` (the CLI `--json` stdout bytes also as text), `isError=false` for every envelope; errors `isError=true` with the CLI's `obserwator-error/1` document (`OSError` → `io_error`, other exceptions → `internal_error`; refused write → `forbidden`, `details.reason="writes_disabled"`, `no_allowed_dir` or `outside_allowed_dirs`). Streams up to 256 KiB as text with `result={schema: "obserwator-stream/1", format, bytes, lines}`. The server speaks English only (AGI-9.2: tool descriptions, instructions, error documents; `OBSERWATOR_LANG` does not reach it), so the tool list does not depend on the connection or the user's setting; Polish text is only an explicit `lang: "pl"` argument of `obserwator_commands_list`, `obserwator_commands_schema` and `obserwator_commands_guide`.

---

## 8. Versioned Store Layer

### Layers (two roots, ADR-017)
1. **Raw root** (marker `obserwator-store.json`) — the source archives: IMGW-PIB ZIP/CSV and ČHMÚ JSON/CSV bytes 1:1 under their server path; the station sources of the catalogs are archives too (station lists, ČHMÚ `now` metadata). The one exception: of IMGW-PIB's current-data API answers (`pl.imgw.hydro_now`, `pl.imgw.meteo_now`) the store keeps a derived file with each station's code, name, river and coordinates, because operational data are never archived (ADR-015 D5), and of the station pages of hydro.imgw.pl (`pl.imgw.hydro_details`) one derived file with each station's reference data (gauge zero and datum, river km, catchment area, year of establishment, province, district, warning and alarm levels, absolute extremes; ADR-021). The PMAXTP cells (`cell.json`, `obserwator-pmaxtp/1`, beside the answer `response.json`) are downloads and live here too. Downloads write only this root.
2. **Data root** (marker `obserwator-data.json`) — what is built from the raw root, which the builders open read-only (no marker, staging or clean-up there): Parquet series per dataset/station (`obserwator-series/1`), `stations.geojson` catalog per provider, analyses per provider (`obserwator-analyses/1`: Hydrolog's answer lines byte for byte with the series versions, options and Hydrolog version they came from; ADR-016). In Nogat this is the root Obserwator's GUI, REST and MCP serve, and a public host gets the data root only (Nogat plan 2026-11-12 D2).
3. A rebuildable local index is out of scope; no `.db` file is ever part of either root.

### Layout
```text
<raw root>/obserwator-store.json                        # obserwator-store/1 marker: schema, tool, created_at, producer_version (+ optional created_by); written by the first write
  archives/versions/<server dir>/<stem>/<label>_<sha8>/<file> + <file>.meta.json
  archives/versions/<server dir>/<stem>/observations/  # obserwator-observation/1 signal register (read-only for consumers)
  pmaxtp/versions/<POT|AMP>/<indX>_<indY>/<label>_<sha8>/cell.json + response.json + .meta.json
  .incoming/<host>_<pid>_<token>/                       # staging; leftovers >24 h cleaned

<data root>/obserwator-data.json                        # obserwator-data/1 marker: the same fields; written by store init --kind data or the first build
  series/versions/<slug>/<label>_<sha8>/series.json + .meta.json + stations/<code>.parquet
  stations/versions/<label>_<sha8>/stations.geojson + .meta.json                 # IMGW-PIB catalog
  stations/versions/chmi_stations/<label>_<sha8>/stations.geojson + .meta.json   # ČHMÚ catalog
  analyses/versions/<pl.imgw|cz.chmi>/<label>_<sha8>/analyses.json + .meta.json + stations/<code>.json + stations/<code>/<id>.json  # Hydrolog's answers (ADR-016)
  .incoming/<host>_<pid>_<token>/                       # staging; leftovers >24 h cleaned
```

- `<sha8>` = first 8 hex digits of the full SHA-256 of the main file; labels come from `Last-Modified` (UTC) or download time.
- Every main file has an immutable `obserwator-meta/1` sidecar: producer/version, dataset, country and provider (from the registry), request, provider license and attribution, `downloaded_at`, `sha256`, `size_bytes`, HTTP signals; ČHMÚ datasets with a canonical content form add `content_sha256`/`content_form`. A path in a sidecar is relative to its own root, as its first directory tells: the sources of a series or catalog (`file`) under `archives/` of the raw root, the series a catalog read under `series/` of the data root.
- Append-only: no overwrite and no `latest` path; hard links only move staged files into a version (after publication each stored file has one name, a relabeled version is a copy). The current version is computed by `current_version(root, slot=...)` with slots `archive:<key>:<file>`, `pmaxtp:pl.imgw.pmaxtp:<METHOD>/<indX>_<indY>` of the raw root and `series:<key>`, `catalog:pl.imgw.stations`, `catalog:cz.chmi.stations`, `analyses:pl.imgw.analyses`, `analyses:cz.chmi.analyses` of the data root (spec §13.7, ADR-017 D2); the slot decides the kind of root, and a root of the other kind is `store_unavailable` (`details.reason="wrong_root"`); `observations/` is never a version candidate. A new HTTP signal with identical bytes is `relabeled` (a copy), identical signal and bytes are `unchanged`; for datasets with a content form (`chmi-json/1`: ČHMÚ hydro files and station lists, JSON without the regenerated envelope keys, RFC 8785) other bytes with the current version's `content_sha256` are `unchanged` (notice `content_unchanged`) and a new source signal is written once to `observations/` (ADR-003 D17, D18).
- Publication (the Kartograf model, ADR-001 erratum 2026-10-19): write into a unique `.incoming/` staging directory and `fsync`, then hard-link (`os.link`, never replaces a target) every file into `<label>_<sha8>/`, the main file's sidecar last — it commits the version. A version directory without that sidecar is an interrupted publication: skipped by `current_version` and writers, reported by `iter_store` as `missing_sidecar`, completed by the next write of the same content under the same label. A failure or Ctrl+C during publication never removes a linked data file (a concurrent writer of the same bytes may have kept it and committed its own sidecar), so it leaves an interrupted publication; only empty directories created by that write are removed, and a linked sidecar is never removed. Versions are never cleaned automatically: the catalog label is the build date, PMAXTP and archives without `Last-Modified` use the download date (UTC), so an interrupted publication that is not repeated with the same content under the same label (e.g. a catalog rebuilt the next day) stays and is removed by hand — the whole `<label>_<sha8>/` directory without the sidecar, while no write to the store runs.
- File system: the store needs hard links, the same requirement as Kartograf's store (its ADR-036 D18, D21, D22) — versions, observations and the markers `obserwator-store.json` and `obserwator-data.json` are all published by `os.link`. Works on Linux, macOS and Windows (ext4, APFS, NTFS, SMB shares with hard links); a file system without them (FAT, exFAT, some NAS/FUSE, the macOS SMB client) is refused by `init_store` and every write with `ObserwatorStoreConflictError` (`details.reason="not_atomic"`); reading needs no hard links. Directory `fsync` is skipped on Windows and where the file system does not support it.
- `stations.geojson` of IMGW-PIB: `meteo_kind` of a meteorological station is `climate` when the current `pl.imgw.meteo_climate_daily` series holds it, otherwise `precipitation` when the current `pl.imgw.meteo_precip_daily` series does, else `null` (always `null` for ČHMÚ); `check_catalog` reports the series action as `newer` when it differs from the catalog.
- A root never nests in another store of any Nogat tool, nor in the other Obserwator root: `init_store` and every write check the ancestors and the existing descendants by marker file name only (`output.STORE_MARKERS`: `kartograf-store.json`, `obserwator-store.json`, `obserwator-data.json`; nothing is imported from Kartograf) and refuse with `conflict` (`details.reason="nested_store"`), and so is a directory with both Obserwator markers (`store_info` and `iter_store` report it as `conflicting_markers`); a root that holds other files and is no store (or is a file) is `conflict` with `details.reason="not_empty"`. Every write refuses such a root before any request (`refuse_root`). A root of the other kind than a function needs is `store_unavailable` with `details.reason="wrong_root"` and `details.kind` (ADR-017 D3; a store not yet split is a raw root). A root with the layout of its kind but no marker is `store_unavailable` (`details.reason="no_marker"`, hint `obserwator store init --root`, with `--kind data` for a data root) and an unreadable marker is `data_error` (`details.reason="invalid_marker"`). The `--check` plan of every store write (`datasets download`, `store init`, `store sync`, `pmaxtp sync`, `series build`, `store catalog`) shows a refusal that is a `conflict` as its one action `conflict` with `reason="nested_store"` or `"not_empty"` and the root as `path`; the plan itself is `ok` and makes no request (`root_conflict_plan`); `store_unavailable` and `data_error` are raised by the check (DEV-19.10, ADR-007 erratum).

### Data Output (ADR-007, DEV §19)
Every writing command has one of two ways of writing, with the same names in Python, CLI, REST and MCP (`obserwator/output.py` is the one implementation of the plain way):

| Target | CLI / Python | Writes | `files[].status` |
|---|---|---|---|
| plain files | `-o`, `--output-dir` / `output_dir=` | the files only, named as in the store, no metadata | `written`, `replaced` |
| store | `-r`, `--root` / `root=` | versions with sidecars in the root of the command's kind (section 8) | `new`, `unchanged`, `relabeled` |
| none given | — | the default root of the command's kind: the raw root of a download (`OBSERWATOR_RAW_ROOT`, `[obserwator] raw_root`, `<data_dir>/obserwator-raw`), the data root of a build (`OBSERWATOR_ROOT`, `[obserwator] root`, `<data_dir>/obserwator`); `obserwator config show --json` names both and their sources | as store |
| one file | `--output` / `output=` | one export file (`store export`, `series export`, `commands guide`); result `OutputReport` | `written`, `replaced` |

- `output_dir` and `root` exclude each other (`validation_error`, `details.reason="exclusive_options"`). The commands whose input or result is the store (`series build`, `store catalog`, `analyses build`) are store-only: they have no `output_dir` (rule in their catalog entry); `--plan` with `output_dir` is refused (`store_only_option`); a dataset without a store form is refused with `not_in_store`; `store sync --output-dir` of a station-year dataset (ČHMÚ) needs `years` (`years_required_in_plain_mode`), because a plain write does not read the server listing.
- Plain names are the store names: for `datasets download` the provider's server path, kept as sub-directories because names collide across folders. `obserwator pmaxtp sync` names its two files by the cell indices of the answer (deviation DEV-19.5/19.6 in `CLAUDE.md`).
- Preflight before the first byte (`refuse_directory`, `plan_plain`, `refuse`): an output directory that is or lies in a store is `conflict` with `details.reason="output_in_store"` and `details.paths` the directory, before any request (it applies to every target); then the whole target list is built; duplicate names → `conflict` with `details.reason="duplicate_output_name"`, a target that would enter a subdirectory with a marker → `output_in_store` (its path), an existing target without `--force` → `output_exists`; `details.paths` lists every offending path. `--check` returns the plan with actions `write`, `replace` (with `--force`) or `conflict` per target; a plan with conflicts is still `ok`.
- Writing (`Staging`): files go to `<dir>/.obserwator-incoming/<host>_<pid>_<token>/` on the same file system, are hashed while written (`sha256` of `files[]`) and moved with `os.replace`; the staging directory is removed on success, error, SIGINT and SIGTERM (a first Ctrl+C lets the command finish its step; a second, or SIGTERM, ends it with exit 130 or 143), leftovers older than 24 h by the next run. No sidecar, hard link or `versions/`, so FAT, exFAT and SMB work. `--force` only replaces the named targets, never deletes other files; in the store `--force` fetches again and gives a new version or `unchanged`, never an overwrite.
- Surfaces: the REST server writes only to its own `OBSERWATOR_RAW_ROOT` and `OBSERWATOR_ROOT`; MCP writes only inside `--allow-dir` (section 7); a refused write is `forbidden`.

### Flow
```
check_store   ── raw root; IMGW-PIB: listing + HEAD; ČHMÚ: one directory listing (no HEAD/GET); station sources: lists by HEAD, `now` metadata and hydro.imgw.pl details unverifiable ──▶ StorePlan (obserwator-plan/1, saved outside the roots; series_state {})
sync_store    ── HEAD again; changed → stale_plan; GET only new/missing ──▶ archive versions only, in the raw root (ČHMÚ: content_unchanged + observation; ADR-015)
build_series  ── current archive versions of the raw root (read-only) → Parquet snapshot in the data root (`unchanged` if the current series version has the same inputs); ČHMÚ: per-station periods
build_catalog ── one provider, offline: the station sources stored in the raw root (lists and `now` metadata; missing → not_found; IMGW-PIB's hydro.imgw.pl details optional, ADR-021) + static/user locations + series indexes of the data root → stations.geojson in the data root
build_analyses ── current series and catalogs of the data root → Hydrolog's batch in a separate process → one analyses version per provider in the data root (ADR-016)
read_*        ── offline, read-only, each in the root of its kind; problems reported as StoreEntry(kind="problem"), observations as kind="observation"
```

Every write operation has a `check_*` twin that never writes or GETs data; long operations accept `on_progress`, `on_notice` (Polish messages) and `cancel` (between files; cancellation never publishes a partial version).

### Schema Versioning (IMGW-13)
Contracts with their own `/N` counters, independent of the package version:

| Contract | File / use |
|---|---|
| `obserwator-store/1` | `<raw root>/obserwator-store.json` marker of a raw root (`schema`, `tool`, `created_at`, `producer_version`, optional `created_by`; a reader needs only `schema`) |
| `obserwator-data/1` | `<data root>/obserwator-data.json` marker of a data root (the same fields; ADR-017) |
| `obserwator-meta/1` | `<file>.meta.json` sidecar of every version (optional `content_sha256` + `content_form`, always together) |
| `obserwator-series/1` | `series.json` index of a Parquet series (+ Parquet metadata) |
| `obserwator-plan/1` | `plan.json` freshness plan outside the store |
| `obserwator-pmaxtp/1` | `cell.json` PMAXTP cell (Obserwator extension) |
| `obserwator-observation/1` | `observations/<YYYY-MM-DD>_<sha8>.json` signal register in an archive slot (ADR-003 D18) |
| `obserwator-result/1` | result envelope of `run_command`/`check_command`, CLI stdout with `--json` and REST body |
| `obserwator-commands/1` | `command_schema()` document (Nogat `commands-1`) |
| `obserwator-command-list/1` | `list_commands()` summary |

Within `/1` only optional fields are added; readers tolerate extra fields in store files. A breaking change requires `/2` with a transition period reading both. Unknown versions are reported (`store_info(...).supported is False`, scan problems) and never parsed or written by old code. Before the 3.0.0 tag the `/1` value domains were opened for further providers (ADR-003 D2, task C01): dataset key `^[a-z]{2}\.[a-z][a-z0-9]*\.[a-z][a-z0-9_]*$`, `country` `^[A-Z]{2}$`, `provider`/`license.id` any non-empty text, station codes 9-digit IMGW or WIGOS (`STATION_CODE_PATTERN`), ČHMÚ `location_source` values; a sidecar of a known dataset must still match the registry's country and provider. The ČHMÚ provider (same release) only adds optional fields: sidecar `request.station_code`/`param`, `extra.period.station_code`, `license.terms_url`; series `stations[<code>].periods`, Parquet `<V>_quality`/`<V>_source_flag`; catalog `thresholds`; plan items `station_code`/`signal`/`remote_listed_at`/`local_observation` and plan `requests`. ADR-004 adds `lang`, `x-obserwator.writes`/`network`/`operation_id` and `x-obserwator-writes` to `obserwator-commands/1`. IMGW files keep identical bytes.

### Integrations
- **Archiwista** consumes both roots only through the public read API (`store_info`, `iter_store`, `current_version`, `read_meta`, `read_catalog`, `read_station_list`, `read_archive`, `read_series_index`, `read_series`, `summarize_series`, `read_pmaxtp`), for both providers (`provider` on entries, catalogs and stations; `read_catalog(root=, provider=)`). Obserwator's library is the only writer; no Archiwista files or indexes live in either root. In Nogat, Archiwista keeps the raw root, whose downloads it orders through Obserwator's library, and reads the series and catalogs from the data root (Nogat plan 2026-11-12 D2, D5, step R2). `iter_store` also returns read-only `kind="observation"` entries. Offline fixtures: `obserwator.testing.build_fixture_store(root, *, data_root, variant=…)` → `FixtureRoots(raw, data)` (`complete`, `complete_pl_cz`, …), `fixture_files()` (archives, listings, recordings, contract schemas). `store_info(root).store_schema` tells the kind of a root; what a reader needs of the marker is its `schema` (as `open_store`); each problem of `StoreInfo.problems` has a code in `problem_codes`; `Meta.producer` and `Meta.producer_version` say which release wrote a version; `iter_store(skip_versions=…)` returns the versions the consumer already knows as `skipped` entries, without listing or reading them (incremental scan; ADR-007 errata of 2026-10-25).
- **Retman** runs data actions as a handler via the public command catalog (`command_schema`, `data_commands`, `validate_command`, `format_command`, `check_command`, `run_command`), getting the same options, validation, envelope, error codes, progress and notices as the CLI and REST; English descriptions from `command_schema(lang="en")`, effects from `x-obserwator.writes`/`x-obserwator.network`. The `root` of a command is a root of its kind, and `series build` and `store catalog` take `raw_root` too (its command list follows in the Nogat plan's step R2).
- **AI agents** read `AGENTS.md`/`llms.txt` (derived from the catalog by `agent_guide`) and call the MCP tools or any other interface.
- **Projects** that pin store versions (by `sha256` and the sidecar's `content_sha256`) belong to Archiwista (`archiwista-project.json`, `archiwista-project/1`, ADR-008); Obserwator keeps no project files.

### CSV Parsing Notes
IMGW-PIB archives are inconsistent between years; parsers auto-detect the format per file:
- Encoding: CP1250 for most archives, UTF-8 with BOM for the 2023 daily archive (auto-detected)
- Delimiter: comma with quoted fields (e.g. 2019-2022, 2024) or semicolon (e.g. 2023), auto-detected
- Quoting: 2024 daily/monthly files wrap whole lines in outer quotes with doubled inner quotes (auto-unwrapped)
- Missing data codes: `9999` (H), `99999.999` (Q), `99.9` (T); meteo status 8 = `missing`, 9 = `no_phenomenon`; accumulated precipitation = `accumulated`
- Hydrological year: Nov 1 - Oct 31
- ZIP reading with member count/size limits and no path traversal; unreadable ZIP → `ObserwatorDataError`

ČHMÚ files (`_parsing/chmi.py`): hydro JSON `{"objID", "tsList"}` (`HD`/`QD`/`TD` → H/Q/T, `PD` skipped, `null` → `missing`, missing row = no record), meteo CSV `STATION,ELEMENT,TIMEFUNC,DT,VALUE,FLAG,QUALITY` (term rows of `T` skipped; `QUALITY` → `quality`, `FLAG` → `source_flag`; `0.0` without flag → `no_phenomenon`, trace `T` → `value`), metadata JSON located by column names (meteo `GEOGR1` = longitude, hydro `GEOGR1` = latitude; numbers read as `Decimal`), nginx listings (name from `href`, UTC minute, size). Errors → `ObserwatorDataError` with file name and place.

---

## 9. Data Formats

### Input (from the sources)
- IMGW-PIB: ZIP archives with CSV files; JSON from the real-time API and PMAXTP
- ČHMÚ: JSON per station and year (hydro), CSV per station and element (meteo), JSON metadata with an envelope, nginx directory listings (HTML)

### Output (to clients)
- JSON envelope `obserwator-result/1` (CLI stdout with `--json`, REST body, MCP `structuredContent`); without `--json` the CLI prints a short summary for a person; errors as CLI JSON line, `application/problem+json` or MCP tool error
- Generated URLs (for direct IMGW-PIB and ČHMÚ downloads)
- Store products: Parquet series, GeoJSON (RFC 7946) station catalogs, CSV export with units and the provider's attribution (IMGW-PIB terms or ČHMÚ CC BY 4.0), JSONL archive export
- Agent guide: `AGENTS.md` and `llms.txt` (markdown, `text/markdown` in REST)
- The GUI: its page and private JSON API (`obserwator-gui-session/1`, `obserwator-analysis/1`, `nogat-handoff/1`) and the files of the exports above (section 5)

### GIS Integration
- `stations.geojson` with WGS84 points per provider (stations without a valid location keep `geometry: null` and a reason; ČHMÚ hydro stations carry SPA `thresholds`)
- The GUI's map (MapLibre GL JS) draws the stations of both catalogs, IMGW-PIB's current measurements and the PMAXTP point (section 5)
- ~~WFS/WMS integration~~ - not implemented

---

## 10. Scaling Considerations

The service is stateless by default:
- No session state
- No database
- The optional store is two plain directories, the raw and the data root (local disk or network share), with append-only versions; concurrent writers are safe thanks to unique staging and no-replace publication
- MCP sessions over HTTP live in the uvicorn process, so `/mcp` needs one worker per instance (the Docker image runs one)
- The GUI is one uvicorn process: its caches, its rate limit and the day's totals live in that process's memory

Scaling options if needed:
- Horizontal scaling of FastAPI instances behind Nginx
- CDN for static files
- Shared read-only roots for several API instances (writes through one configured instance)

---

## 11. CI/CD

**Quality gate:** `scripts/gate.sh` (template `standards/ci/gate.sh` of the Nogat
standard, DEV-7.6) runs, in order and stopping at the first failure: `ruff format
--check`, `ruff check`, mypy (`strict`, over `src/` and `tests/`), one pytest call
over `tests/` with coverage (offline, `-m "not live"`, floor 80%) and the commit
step `scripts/check-commits.sh` (identity, Conventional Commits, no AI
attribution). The environment is `uv.lock` (`uv sync --locked`).

**CI:** GitHub Actions run the gate on Linux, macOS and Windows
(`.github/workflows/ci.yml`, DEV-7.7), the `live` tests weekly
(`.github/workflows/live.yml`), and Dependabot updates the Actions
(`.github/dependabot.yml`). Templates: `standards/ci/` of the Nogat standard. They
trigger on `main` and `develop`, so they start working once the branches are renamed.
The GUI's browser tests (`tests/e2e/`, Playwright) skip where Chromium is not
installed, as in CI.

**Deployment:** Docker (`docker/`) for the REST server; the GUI as a service of its
own on 127.0.0.1 behind an authenticating proxy (`docs/USAGE.md`, „GUI”).

---

## 12. File Structure

```
Obserwator/
├── src/obserwator/
│   ├── __init__.py       # PUBLIC API entry point (single __all__)
│   ├── output.py         # Plain output (ADR-007): resolve_target, refuse_directory, plan_plain, refuse, Staging, FileResult, OutputReport; markers STORE_MARKERS, DATA_MARKER
│   ├── _version.py       # Version, single source (pyproject reads it)
│   ├── fetch.py          # PUBLIC: fetch_* (live), download_archives, download_* -> DownloadResult
│   ├── models.py         # PUBLIC: Data models incl. NormalizedRecord, Measurement
│   ├── stations.py       # PUBLIC: find_stations (IMGW-PIB and ČHMÚ)
│   ├── exceptions.py     # PUBLIC: Custom exceptions + ERROR_CODES (title as a catalog message)
│   ├── error_report.py   # PUBLIC: obserwator-error/1 document (ErrorReport, error_report) and hints
│   ├── messages/         # Message catalog: message(), Message, localize(), Text(en, pl) per area (ADR-006); gui/: the GUI's texts
│   ├── urls.py           # PUBLIC: IMGW URL constants, build_pmaxtp_url, build_api_url
│   ├── parsers.py        # PUBLIC: Parser re-exports (IMGW-PIB hydro/meteo, ČHMÚ, station lists)
│   ├── datasets.py       # PUBLIC: Provider and dataset registry, archive_files, YearsArg/MonthsArg
│   ├── coverage.py       # PUBLIC: summarize_coverage
│   ├── commands.py       # PUBLIC: Command catalog, command_schema, run_command
│   ├── agent_guide.py    # PUBLIC: agent_guide (AGENTS.md, llms.txt), MCP instructions
│   ├── testing.py        # PUBLIC: build_fixture_store → FixtureRoots(raw, data), fixture_files
│   ├── _jsonable.py      # Single JSON converter (envelope, relative paths)
│   ├── _examples.py      # Example calls of the catalog (examples of command_schema)
│   ├── reference_data.py # Fetch IMGW-PIB reference data into reference_dir (OBSERWATOR_REFERENCE_DIR)
│   ├── config.py         # Settings (incl. hydrolog_command)
│   ├── _hydrolog.py      # Hydrolog's program: `commands batch` in a separate process (ADR-016)
│   ├── _data/            # Poland and Czechia borders (PRG of GUGiK, RÚIAN of ČÚZK; ADR-018), agents/ templates, packaged fixtures, recordings, contract schemas
│   ├── _parsing/         # common.py, hydro.py, meteo.py, stations.py, chmi.py
│   ├── store/            # types, writer, content, sync, series, catalog, pmaxtp, reader, export, plain (plan of a plain write), analyses and analysis_registry (ADR-016)
│   ├── api/              # REST API [optional]
│   │   ├── main.py       # FastAPI app (/health, /api/v1, /llms.txt, /docs, /mcp; GET / redirects to /docs)
│   │   ├── routes/commands.py  # Routes generated from the command catalog
│   │   ├── errors.py     # problem+json handlers, hide_server_paths, Accept-Language
│   │   └── schemas.py    # HealthCheck
│   ├── cli/              # CLI [optional]
│   │   ├── main.py       # Entry point (version, server, mcp, admin, config, catalog groups)
│   │   ├── gui_cmd.py    # obserwator gui serve
│   │   ├── _dispatch.py  # Catalog-driven command generation (only adapter), OBSERWATOR_LANG
│   │   ├── _render.py    # Summary for a person of the envelope (without --json)
│   │   └── admin.py      # REST API key management (api_keys.json)
│   ├── mcp/              # MCP server [optional: obserwator[mcp]]: _tools, _calls, server
│   └── gui/              # GUI [optional: obserwator[gui]]: obserwator gui serve, entry point nogat.gui (ADR-013)
│       ├── _app.py       # Starlette app: private API, headers; _root, _live, _analyses, _traffic, _feedback, _admin, _terms
│       └── web/          # the page: Preact + htm modules, charts, MapLibre, Nogat's kit and tokens, instrukcja/, admin/
├── AGENTS.md, llms.txt   # Agent guide — derived from the catalog (obserwator commands guide)
├── docker/               # Docker configuration (Python 3.12 image with .[api,mcp], compose, nginx with /mcp)
├── tests/                # Tests (unit, contract, e2e, live; fixtures/store with synthetic IMGW-PIB and ČHMÚ archives, recordings; fixtures/export_golden)
└── pyproject.toml        # Project configuration
```
