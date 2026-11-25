# Obserwator — Architecture

## 1. Architecture Model

System consists of six main components:

1. **Python Library** (v3.2.0)
   - the package `obserwator` (installed from Git by its tag, README "Install") for integration with external projects
   - Sync and async functions for live data and archive downloads (`DownloadResult`, `download_archives`)
   - Provider registry (`IMGW` — IMGW-PIB, `CHMU` — ČHMÚ, ADR-003, ADR-028; `GDANSKIEWODY` — Gdańskie Wody, the registry's first provider of the source class `other`, off by default, ADR-034; `PIG` — PIG-PIB, groundwater monitoring of the state geological service, class `other`, served by default, ADR-035) and dataset registry (61 descriptors: 33 `pl.imgw.*`, nine of them captures, one the monthly telemetry and one an hourly series, 16 `cz.chmu.*`, two of them captures and one an hourly series, 6 `pl.gdanskiewody.*`, its station list, month files and four series built from them, and 6 `pl.pig.*`, its points, the month files of its readings, its chemistry and watch list as published, one capture and one hourly series, with slugs and legacy aliases, each with its tier; one more declared ahead of the step that serves it, offered by no surface, ADR-030), IMGW-PIB, ČHMÚ, Gdańskie Wody and PIG-PIB parsers with value flags
   - Command catalog (`obserwator.commands`): 37 commands, one envelope `obserwator-result/1`, one error registry `ERROR_CODES` (ADR-002); English texts with a Polish variant (ADR-006), declared effects (`writes`, `network`, `idempotent`) and the agent guide `agent_guide` (ADR-004)
   - Providers fed by files (ADR-033): an operator's own network declared in a provider file listed by `[obserwator] provider_files` of `nogat.toml`, served by one adapter (`providers/files.py`) and imported by `store import --provider-file`
   - Captures (ADR-030): every answer of a source of current data, whichever interface asked, is kept as it came in the capture spool `<state_dir>/obserwator/captures` (one file per answer, never in a root); `current poll` asks each polled source at most once per its declared interval; `store sync --pace-until` harvests hydro-back's hourly series or ČHMÚ's `recent` day files of the last closed UTC day, or PIG-PIB's automatic measurements appended after the watermark of its newest capture (ADR-035), through `fetch.PacedSession` (spread to a deadline, at least 5 s apart, backoff, gzip), then seals
   - Minimal dependencies (httpx, platformdirs, pydantic, pydantic-settings)

2. **Versioned Store** [Parquet: `obserwator[store]`] in two roots (ADR-017)
   - Raw root (marker `obserwator-store.json`): append-only, immutable versions of IMGW-PIB, ČHMÚ, Gdańskie Wody and PIG-PIB archives with provenance sidecars, the station sources of the catalogs, the captures of current data sealed from the spool (one version per dataset and UTC day) and the PMAXTP cells; the downloads and the sealing write only here
   - Data root (marker `obserwator-data.json`): Parquet station series, `stations.geojson` per provider and the stations' analyses computed by Hydrolog's program and stored as its answers (ADR-016; Obserwator computes no number), built from the raw root, which the builders only read
   - Default roots in the user data directory (`<data_dir>/obserwator-raw` and `<data_dir>/obserwator`), or `--root`, `OBSERWATOR_RAW_ROOT` and `OBSERWATOR_ROOT`, `[obserwator] raw_root` and `root` (and `--raw-root` of a build); readable offline, also from network shares
   - Decision records: `docs/DECISIONS.md` (ADR-001 store, ADR-002 interfaces, ADR-003 ČHMÚ provider and open `/1` domains, ADR-004 agent support, ADR-015 raw data only in `store sync`, ADR-016 stored analyses computed by Hydrolog, ADR-017 the data root, ADR-021 station details of hydro.imgw.pl, ADR-029 provider adapters, ADR-030 captures and the operational tier, ADR-033 providers fed by files, ADR-034 Gdańskie Wody and the source classes, ADR-035 PIG-PIB groundwater); contracts: `docs/superpowers/specs/2026-10-17-versioned-store-design.md`, `2026-10-18-chmi-provider-design.md`, `2026-10-19-agent-support-design.md`

3. **Backend (FastAPI)** [optional: `obserwator[api]`]
   - Routes `/api/v1/<group>/<command>` generated from the command catalog (33 commands; the local-only commands `datasets download`, `store init` and `current poll` have no route)
   - URL generation for IMGW-PIB, ČHMÚ and PIG-PIB downloads and live IMGW data
   - Store commands only with the explicit server-side root of their kind: `OBSERWATOR_RAW_ROOT` (raw root) or `OBSERWATOR_ROOT` (data root); `series build` and `store catalog` need both
   - Errors as `application/problem+json`; language negotiation (`Accept-Language`, English by default); `GET /llms.txt`; optional MCP endpoint `/mcp`; rate limiting via Nginx; Nogat's logs in `<state_dir>/obserwator/logs` (ADR-019)
   - An operator's instance (`[obserwator.instance]` of `nogat.toml`, ADR-025; `api/instance.py`): read once at start, the routes serve only its providers, its area and PMAXTP when it says so; a wrong section, a root of a layout this version does not read (`store_unavailable`, `details.reason="unsupported_layout"`) and, with the section, a weak write token stop the start
   - The sources' publication state (`[obserwator.capture]`, ADR-030 D5; `api/publication.py`): a request naming a source of a tier other than `verified` set `private` (an option `dataset` or `datasets`, a `store sync` plan item, a `version` under its slots) answers `not_found` (`details.reason="private"`) before any request; a fetch of current data the server makes is kept in the capture spool beside its logs; `store sync`'s `pace_until` has no REST parameter

4. **MCP Server** [optional: `obserwator[mcp]`]
   - `obserwator mcp` (stdio) and `/mcp` (Streamable HTTP inside the REST app); tools generated from the command catalog
   - Read and plan only by default; writes only with `--allow-writes` and `check: false` (stdio), and only inside the `--allow-dir` directories

5. **GUI** [optional: `obserwator[gui]`; the command also needs `obserwator[cli]`]
   - `obserwator gui serve` (ADR-013): a Starlette app of its own on 127.0.0.1:8060 with a private API relative to its page; Nogat's GUI platform finds it through the entry point `nogat.gui`
   - Every station of the providers served on a MapLibre map (IMGW-PIB, ČHMÚ, PIG-PIB, providers fed by files; Gdańskie Wody is off by default), the outline telling the source class (solid grey for a national service, dashed for another source) and the list filtered by class (ADR-034 D12), the station panel (description, IMGW-PIB's levels and extremes of a hydrological station (ADR-021), a PIG-PIB point's hydrogeology (ADR-035), current IMGW-PIB values, the hourly chart of a hydrological station's stored hours and live tail (O6), series chart and table, Hydrolog's analyses, downloads), PMAXTP of a point; Preact + htm without a build step
   - Reads the data root read-only through public functions, Hydrolog's stored analyses (ADR-016) among it; IMGW-PIB's current data, the live tails of the hourly chart in „teraz” (either provider) and PMAXTP pass through the server's memory, and every answer of the current data and of the live tails also goes to the capture spool (ADR-030 D7); a person's choices are computed by Hydrolog's program on request
   - A public deployment adds a rate limit, daily statistics, „Zgłoś uwagę”, the regulamin and the admin panel `admin/` with a key of its own (ADR-020); the logs are Nogat's, as the REST server's (ADR-019); an operator's instance (ADR-025) filters every route with the REST server's predicate and adds its title, logo, area and regulamin

6. **CLI** [optional: `obserwator[cli]`]
   - Local client using the library directly (never through the REST API)
   - Groups `datasets`, `stations`, `current`, `pmaxtp`, `store`, `series`, `analyses`, `commands` generated from the command catalog; help in Polish or English (`OBSERWATOR_LANG`)
   - `obserwator mcp`, `obserwator server`, `obserwator gui serve`, `obserwator config show`, REST API key management (`obserwator admin`, deprecated in 3.1.0 and removed in v4.0.0; not the GUI's admin key)

---

## 2. Component Diagram

```
┌──────────────────────────────────────┐ ┌──────────────────────────────────┐
│            IMGW-PIB                  │ │              ČHMÚ                │
│ danepubliczne.imgw.pl, hydro.imgw.pl,│ │ opendata.chmi.cz (historical,    │
│ hydro-back.imgw.pl, klimat.imgw.pl   │ │ historical_csv, metadata, now)   │
└──────────────────────────────────────┘ └──────────────────────────────────┘
┌──────────────────────────────────────┐ ┌──────────────────────────────────┐
│ Gdańskie Wody (class other, off by   │ │ PIG-PIB (class other; ADR-035):  │
│ default; ADR-034): an API with a key,│ │ open ArcGIS REST, no key,        │
│ pomiary.gdanskiewody.pl/rest         │ │ cbdgmapa.pgi.gov.pl/arcgis       │
└──────────────────────────────────────┘ └──────────────────────────────────┘
                              ▲            ▲
                              │ HTTP (URL generation, live proxy, listing/HEAD/GET
                              │ for the store; one request at a time)
┌─────────────────────────────────────────────────────────────────┐
│                       obserwator (library)                        │
│  ┌────────────┐ ┌────────────┐ ┌──────────────┐ ┌────────────┐  │
│  │ urls       │ │ fetch /    │ │ datasets     │ │ parsers    │  │
│  │            │ │ stations / │ │ (providers,  │ │ (_parsing) │  │
│  │            │ │ captures   │ │  registry)   │ │            │  │
│  └────────────┘ └────────────┘ └──────────────┘ └────────────┘  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ store/: writer · content · sync · captures · series ·     │   │
│  │         catalog · pmaxtp · reader · export · plain ·      │   │
│  │         analyses · files · staging                        │   │
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

The GUI also runs Hydrolog's program for the analyses it computes on request (section 5). Every answer of a source of current data the library receives, whichever component asked, is also written to the capture spool in `state_dir`, which `store sync` seals into the raw root (section 8, „Captures”).

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
1. Generates URLs pointing to IMGW-PIB, ČHMÚ and PIG-PIB servers
2. Proxies real-time API requests to IMGW-PIB
3. Returns results directly to the client

Data is written only after explicit configuration: an absolute `OBSERWATOR_RAW_ROOT` enables the commands of the raw root and an absolute `OBSERWATOR_ROOT` those of the data root, and `series build` and `store catalog` need both (ADR-017; otherwise 503 `store_unavailable` with `details.reason="not_configured"` naming the variable; a root that is relative or no supported root is 503 with `root_invalid` or `unsupported`, a root of the other kind 503 with `wrong_root`), and writes additionally need `OBSERWATOR_STORE_WRITES_ENABLED=true`, a non-empty write token (`OBSERWATOR_STORE_WRITE_TOKEN`, or the file of `OBSERWATOR_STORE_WRITE_TOKEN_FILE`) and a matching `X-API-Key` header (otherwise 403 `forbidden`). The server never writes to a default root and takes no `root`, `raw_root`, `output_dir`, `output` or `force` in a request (400 `validation_error`). Locally, the CLI and the library write to `--output-dir` (plain files), `--root` (a root of the store) or, with neither, to the default root of the command's kind, never to the working directory (section 8, "Data Output").

The data the server keeps without that configuration are its captures (ADR-030 D7): every answer of a source of current data it fetches is kept in the capture spool `<state_dir>/obserwator/captures`, beside its logs, never in a root; `store sync` of the capture datasets seals the spool into the raw root.

---

## 4. REST API

### Implemented Features
- Routes generated from the catalog (`x-obserwator.rest` of the internal input schemas) by `api/routes/commands.py`: `GET` for reads (options in the query; lists comma-separated or repeated), `POST` for `store sync`, `store catalog`, `store import`, `series build`, `analyses build`, `pmaxtp sync` (options in a JSON body; `?check=true` returns the plan without writing)
- Response body = `CommandResult.to_json(root, server=True, lang=)`, identical to the CLI envelope except hidden server paths and the language of the texts; list commands page with `limit` (default/maximum `OBSERWATOR_API_MAX_LIMIT`) and `cursor` (`page.next_cursor`); `stations export`, `store export`, `series export`, `analyses export` and `commands guide` stream their file (a Parquet export is written by the server, then sent) as an attachment named `obserwator_<content>_<qualifiers>.<extension>` (`_file_names.py`, Nogat DEV-19.21) with `X-Obserwator-Notices`/`X-Obserwator-Status` headers and, for a provider's data, `X-Obserwator-Attribution`/`X-Obserwator-Terms-Notice`
- Errors: `api/errors.py` turns every `ObserwatorError`, request validation error, HTTP error, `OSError` and unexpected exception into `application/problem+json` with `code`, `details`, `hint` (when one fits) and the status of `ERROR_CODES` (validation always 400)
- Captures and the telemetry (ADR-030 D5): `api/publication.py` reads `[obserwator.capture]` on every request, `?check=true` included, and answers `not_found` (`details.reason="private"`) before any request when an option `dataset` or `datasets` or an item of a `store sync` plan names a source of a tier other than `verified` set `private`, and for a `version` under its slots (by the path alone: a capture's day by the day grammar, another source by the longest server directory it lies below, so an existing version answers like a missing one); MCP over HTTP goes through the same routes
- `GET /api/v1` (name, version, schema route, catalog routes), `GET /health`, `GET /llms.txt` (agent guide in the language of `Accept-Language`, English by default), OpenAPI/Swagger documentation (`/docs`, English; `GET /` redirects to it)
- Language (AGI-6.4, AGI-9.2): the texts of an answer (notices, item and plan texts, the `title`, `detail` and `hint` of problem+json) follow `?lang=` of a command with the option `lang` (`commands list`, `commands schema`, `commands guide`), else `Accept-Language` (RFC 9110 weights, first subtag), else English; every command answer has `Content-Language`, and `Vary: Accept-Language` when the header decided
- Optional `/mcp` (MCP Streamable HTTP, `OBSERWATOR_MCP_ENABLED=true`): the SDK session manager runs in the app lifespan, tools call the REST routes in process (section 7)
- Logs (Nogat DEV-12.4 to DEV-12.9, ADR-019): `api/main.py` starts a `ServerLog` of `obserwator.nogat_logging` (Nogat's reference module, copied byte for byte and shared with `obserwator gui serve`) and adds its `AccessLog` as the outermost middleware (no client address; `/docs`, `/redoc`, `/openapi.json`, `/llms.txt`, `/health` logged only from status 400): access, application and lifecycle records in `<state_dir>/obserwator/logs/<kind>-YYYY-MM-DD.jsonl`, deleted after 14 days; stderr gets only the lifecycle records and the errors reduced to their type; uvicorn runs with `--no-access-log --log-level warning` and there is no log level setting

### Security (Current State)
- Rate limiting via Nginx (`limit_req_zone`)
- CORS: only the origins of `OBSERWATOR_CORS_ORIGINS` (none by default; `*` for every origin), never with credentials
- Security headers on every answer (`SecurityHeaders` of `api/main.py`, from `_http_headers.py` as the GUI's): `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, a `Permissions-Policy` denying unused browser features; no Content-Security-Policy, since `/docs` and `/redoc` load Swagger UI and ReDoc from their CDN
- GZip compression enabled
- Store routes: server-side roots only (clients never pass a root, a raw root or an absolute path; `version` is confined to `*/versions/` under the command's root, no `..`, symlinks rejected), write token compared in constant time, unknown/server-only/local options rejected (400 `validation_error`); answers hide server directories (both roots, `OBSERWATOR_USER_LOCATIONS_DIR`, `OBSERWATOR_REFERENCE_DIR`, `OBSERWATOR_DATA_DIR`, `OBSERWATOR_CACHE_DIR`, TMPDIR, the directory of `nogat.toml` with the provider files of `store import`, CWD)
- `/mcp`: off by default (`OBSERWATOR_MCP_ENABLED`), read and plan only (POST routes always with `?check=true`, so the write token is never used), `Host` restricted to `OBSERWATOR_MCP_ALLOWED_HOSTS`, browser origins refused by the SDK (403); nginx `location = /mcp` shares the `api_limit` zone

### Security (Planned, Not Implemented)
- ~~API key validation middleware~~ - keys managed but not enforced (store writes use their own token); `obserwator admin` and `api_keys.json` are deprecated and go in v4.0.0
- ~~Per-key rate limiting~~ - only nginx-level limiting
- ~~MCP writes over HTTP with authorization~~ - out of 3.2.0 (ADR-004 open question)

---

## 5. GUI Layer

`obserwator gui serve` (ADR-013; package `obserwator.gui`, outside `obserwator.__all__`; extra `obserwator[gui]` = `[store]` + Starlette + uvicorn, and `[cli]` for the command) is a server of its own, never mounted in the REST app, so only the GUI's routes reach its address. It reads Obserwator's data only through its public functions (it uses the internal helpers `_environment`, `_jsonable`, `_hydrolog`, `_borders` and `_http_headers` for settings, JSON, Hydrolog's program, the packaged borders and the security headers shared with the REST server) and computes no statistic itself: every number of an analysis is Hydrolog's; the one exception is the colour scale of the climate stripes (`_stripes.py`, route `api/prototype/stripes/{code}`). Running it, its settings and its public rules: `docs/USAGE.md`, section „GUI”.

### Technologies (Implemented)
- **Starlette** under **uvicorn**, one process (FastAPI was rejected: the private routes need neither OpenAPI nor pydantic); blocking reads and exports run in worker threads, at most four at a time
- **Preact 10.29.8 + htm 3.1.1** as ES modules without a build step, vendored byte for byte with their licences and SHA-256 (`gui/web/vendor/vendor.json`)
- **MapLibre GL JS 6.14.0**, vendored with its module worker (a same-origin file) and the Noto Sans glyphs; the basemap is a TileJSON from settings (OpenFreeMap's by default) drawn in the GUI's own grey style, or offline the packaged borders of Poland and Czechia
- **An own SVG chart module** (`gui/web/src/charts/`): linear, log, date, time and Gumbel-probability axes; lines, steps, areas, bands, bars, points and reference marks; long series decimated to the first, last, lowest and highest point per pixel column; zoom and a readout by pointer and keys
- **Nogat's identity**: copies of `tokens.css` (Nogat `55a2d4b`), the marks and kit 1.3.0 (Nogat `ff18ee8`; `nogat-app-menu.*`, `nogat-sources.*` with `screen-lines` and PIG-PIB's W, WP and WK, `nogat-handoff.js`, `nogat-terms*`, `nogat-admin.*`), byte for byte with their manifests (DEV-15.3, DEV-15.6); light and dark theme; the top bar, side panels that resize, bottom sheets at 860 px and below
- **Provider lines on screen** (DEV-20.5, ECO-064): one compact `<nogat-sources>` of the kit per view, across the page under the map and both panels, fed the union of the lines of what the list and the map show and of what the right panel shows (the station's header, its open cards and their results, the stations files or PMAXTP's tables), the basemap's credit after it; never per panel or card; on a phone the sheets stop above it. A set of catalog stations brings the line of the state border its locations were checked against (G or Z, ADR-018). S, P, PS, PP and the short forms of ČHMÚ's, GUGiK's and ČÚZK's lines (CK, GK, ZK) on screen, every line and the terms behind „Źródła i warunki”; a welcome window on the first visit with the same full content (`fillSources`). Files, images, hand-offs and the API keep the full lines
- **Texts**: the area `gui` of the message catalog (`messages/gui/`, `Text(en, pl)`, ADR-006), served by `api/texts`; Polish by default, English through „PL | EN”

### Routes
Relative to the page, so the app works at `/` and under any prefix (Nogat's GUI platform mounts it through the entry point `nogat.gui`). GET includes HEAD; any other method is `405` with `Allow`; another `api/…` address is `404`.

| Route | Method | Answer |
|-------|--------|-------------|
| `/` and `index.html` | GET | the page, rendered with the versioned addresses of its files (`_page.py`) |
| `v/<build>/…` (`theme-init.js`, `src/`, `css/`, `nogat/`, `vendor/`) and the other static files of `gui/web/` (`instrukcja/`: the guide in Polish; `favicon.ico`, `apple-touch-icon.png`) | GET | the page's files |
| `robots.txt`, `apple-touch-icon-precomposed.png` | GET | the crawlers' rules (not `api/`); the touch icon again |
| `api/session`, `api/texts` | GET | versions, the data root in use (its catalogs, series and stored analyses), providers and their lines, basemap, `[nogat.gui]`, terms, the instance (null without one); the texts |
| `api/stations`, `api/stations/{code}` | GET | the station layer of the current catalogs; one station |
| `api/series/{dataset}/{code}` | GET | a station's series: dates, values, flags |
| `api/analyses/{code}`, `api/analysis/{code}/{id}` | GET | the stored analyses of a station; one result (`obserwator-analysis/1`), the stored one or one computed with the person's options |
| `api/current`, `api/current/{code}` | GET | IMGW-PIB's current measurements |
| `api/station/{code}/subdaily?from=` | GET | the hourly chart of „teraz” (O6): a hydrological station's stored hours of its provider's hourly series from `from` on, with their tiers, and the live tail after them; `404` (`kind`, `provider`, `private`) before any request |
| `api/pmaxtp` | GET | PMAXTP of a point |
| `api/downloads/{code}`, `api/downloads/stations` | GET | the files offered (a station's series and stored analyses, the stations), each with its command line and licence |
| `api/files/series/{dataset}/{code}`, `api/files/stations`, `api/files/analyses/{code}`, `api/files/analysis/{code}/{id}`, `api/files/pmaxtp` | GET | the files |
| `api/handoff/{code}` | GET | `nogat-handoff/1` around `hydrolog-series/1` |
| `api/prototype/stripes/{code}` | GET | the climate stripes (M15), a prototype of their colour scale |
| `api/feedback` | POST | „Zgłoś uwagę” |
| `admin` (308), `admin/` | GET | the admin panel: the kit's `<nogat-admin>` (Nogat DEV-15.13, ADR-020) |
| `api/admin/feedback`, `api/admin/feedback/{id}` | GET; PATCH, DELETE | the reports, newest first; one marked read or unread, or deleted |
| `api/admin/stats`, `api/admin/status` | GET | the days of `stats.jsonl` with today; the app, its directory and disk, its checks |
| `api/logo`, `api/area` | GET | the operator's logo and the instance's area as a GeoJSON Feature (ADR-025; `404` without them) |
| `regulamin.html` | GET | the terms of a public deployment, or the operator's |
| `data/{poland,czechia}_border_wgs84.geojson` | GET | the packaged borders |

### Data Flow
- **Data root**, read-only (`_root.py`): the current catalog of each provider, the current series of each dataset and the current stored analyses of each provider through `current_version`, `read_catalog`, `read_series_index`, `read_series` and `export_stations`; the current versions are asked again at most once a minute, in the background (the first read alone is a request's own; the requests take the last snapshot while one re-read runs), so a new build shows without a restart (new stored analyses alone keep the station layer and its ETag); in memory the station layer, a summary of each series index (its ranges without a value counted, not kept), the most recent series documents (at most 32 and 2 million cells) and 4 stations files; what a large read keeps is copied once the read is over, and pyarrow's Parquet modules are imported when the root is made, so that no read leaves memory behind (ADR-027); answers carry a strong ETag (the versions, the query and a token of the run) and `Cache-Control: no-cache`.
- **Instance** (`obserwator.instance`, ADR-025): with `[obserwator.instance]`, `Instance.reduce` reduces each read of the data root, so the station layer, its ETag and every station route agree; a provider `off`, a station outside a clipped area and PMAXTP `off` are not served, IMGW-PIB's current data only while IMGW-PIB is; `api/session` gives the page the title, logo, featured provider, `others_opacity`, start view and area. Without the section both servers apply `default_instance()`, which leaves out only the providers off by default (Gdańskie Wody, ADR-034 D11) and keeps the session's `instance` null.
- **The page** (`_page.py`): `index.html` is served rendered, its own files at `v/<build>/` (a digest of `theme-init.js`, `src/`, `css/`, `nogat/` and `vendor/`, so a release has new addresses and the browser keeps each file for a year), MapLibre's module, worker, stylesheet and glyphs at `vendor/…?v=<version>` of `vendor/vendor.json`, and a `modulepreload` of every module `src/main.js` imports statically, so the start asks for all of them at once; `theme-init.js` asks for `api/texts`, `api/session` and `api/stations` before the modules load (`src/start.js`).
- **Live data** (`_live.py`), in memory only: snapshots of IMGW-PIB's current data (water states, hydro, meteo, synop), each fetched on demand at most once per 10 minutes, one request per source at a time and the sources of one answer at the same time, an expired one served while its refresh runs in a background thread, the last kept when a fetch fails; `api/current` and `api/current/{code}` answer `304` to the ETag of their snapshots; PMAXTP per method and point at four decimals for 24 hours, at most 1,000 points, one live request at a time; every request to IMGW-PIB is an app record `upstream_fetch`. Every answer of the current data the snapshots fetch also goes, as it came, to the capture spool `<state_dir>/obserwator/captures` (the library's fetchers hand it to the provider's adapter, ADR-030 D7); a spool that cannot be written is one warning record and the snapshot is served all the same. The GUI writes no root.
- **Live tails** (`LiveTail` of `_live.py`, O6; ADR-013 and ADR-030 errata of 2026-11-23): `api/station/{code}/subdaily` reads a station's months of the hourly series from the first of its range on (`DataRoot.series_document(since=…)`, in the bounded cache of the series documents) and, while the newest stored hour is older than the current one, asks the provider for the hours after it through its adapter (`ProviderAdapter.live_tail`: hydro-back's hourly series with `hoursInterval` up to 1,000, or ČHMÚ's `now` file), whose answers go to the spool of `ProviderAdapter.live_source`; `store.subdaily.tail_hours` reads their full hours. One tail per station, kept 10 minutes while it reaches the newest stored hour (a failure 60 s), at most 500 stations, one request per station at a time and one live request of the server behind its own limiter; each request is an app record `upstream_fetch`. A station whose hourly series or live source is `private` (`[obserwator.capture]`, read on every request) is `not_found` before any request, and its station document says `subdaily: false`.
- **Analyses** (`_analyses.py`): Hydrolog's results stored in the data root by `analyses build` (`list_analyses`, `read_analysis`), shown as they are; a person's choices (and the climate stripes' reference period) computed on request by `compute_analysis` through Hydrolog's program (`OBSERWATOR_HYDROLOG_COMMAND`, else `hydrolog` on `PATH`, looked for once when the app starts; without it only stored results): at most two processes of 30 s, 500 results in memory, never written.
- **Files**: `export_series`, `export_stations` and `export_analyses` write them byte for byte as the CLI does; PMAXTP of a point is packed by the server (CSV, JSON); a hand-off is built by the server from the data root or from Hydrolog's result.
- **Own files** in `<data_dir>/obserwator`: `stats.jsonl`, `feedback.jsonl` (rewritten atomically under its `flock` when the admin panel marks or deletes a report) and `feedback.next_id` beside it (ids are never reused); none when that directory and the data root are one or one holds the other.
- **Logs** in `<state_dir>/obserwator/logs` (Nogat DEV-12.4 to DEV-12.9, ADR-019): `obserwator gui serve` starts a `ServerLog` of `obserwator.nogat_logging` (Nogat's reference module, copied byte for byte and shared with `obserwator server`) and `build_app` adds its `AccessLog` as the outermost middleware, outside `Traffic`, so the rate limit's `429` is logged too; one file per kind and UTC day (`<kind>-YYYY-MM-DD.jsonl`), deleted after 14 days, no client address; static content (`QUIET` of `_app.py`) only from status 400; stderr gets only the lifecycle records and reduced errors.
- The page connects only to its own origin and the basemap's.

### Security
- Every answer (`SecurityHeaders` of `_app.py`): `Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self'; worker-src 'self'; img-src 'self' data: blob: <basemap origin>; connect-src 'self' <basemap origin>; font-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'`, `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, `Cross-Origin-Opener-Policy: same-origin`, `Cross-Origin-Resource-Policy: same-origin`, `Permissions-Policy` denying every browser feature the page does not use (`accelerometer`, `autoplay`, `browsing-topics`, `camera`, `display-capture`, `encrypted-media`, `fullscreen`, `geolocation`, `gyroscope`, `hid`, `idle-detection`, `local-fonts`, `magnetometer`, `microphone`, `midi`, `payment`, `picture-in-picture`, `publickey-credentials-get`, `screen-wake-lock`, `serial`, `usb`, `xr-spatial-tracking`; the clipboard stays allowed for the hand-off; `_http_headers.py`, shared with `obserwator server`), `Cache-Control: no-cache` unless the answer sets another (`max-age=31536000, immutable` on the page's files at a versioned address, `_page.py`)
- No cookies, sessions or CORS headers; no inline script or style and no remote resource but the basemap
- Every parameter is checked against the registries before the data root or Hydrolog is touched (DEV-13.3); errors are `obserwator-error/1` in the page's language with the server's directories hidden (root, own directory, TMPDIR, CWD); Hydrolog gets only checked options and series files the server wrote
- No sign-in but the admin panel's: the GUI binds `127.0.0.1` by default and is reachable beyond it only behind an authenticating proxy (`FORWARDED_ALLOW_IPS` names the proxy to uvicorn); every route of `api/admin/…` (`_admin.py`) checks `X-Admin-Key` in constant time against `OBSERWATOR_ADMIN_API_KEY` or the file of `OBSERWATOR_ADMIN_API_KEY_FILE`, read on every request (`401 unauthorized` otherwise; never generated or logged, and not one of the REST API keys of `obserwator admin`); the panel's answers (`admin/` and `api/admin/…`) carry `Cache-Control: no-store` under CSP `'self'`

### Public Rules (Nogat DEV-15.7 to DEV-15.12)
- `Traffic` (`_traffic.py`), an ASGI middleware: the rate limit per client address (300 requests in 60 s by default, static files not counted, `429` with `Retry-After`), the daily totals in `stats.jsonl` (visitors as keyed hashes kept in memory); the access log is `AccessLog`'s, outside it (Logs above); uvicorn keeps no log of its own
- `_feedback.py`: `POST api/feedback` appends a report of „Zgłoś uwagę” to `feedback.jsonl` (never an IP address or a User-Agent); `_admin.py` (DEV-15.13) lists, marks and deletes reports, shows the daily totals and the status checks `data_root_marker`, `stored_analyses`, `hydrolog_command`; the panel's requests stay under the rate limit and out of the totals
- `_terms.py`: with `[nogat.operator]` and the `obserwator` address of `[nogat.gui]`, `regulamin.html` filled from the kit's `nogat-terms.html` (its source blocks of Obserwator's data sources, the borders' GUGiK and ČÚZK among them, link each provider's terms, no summary of them), or on an operator's instance its own regulamin (`terms` of `[obserwator.instance]`, Markdown written from the kit's `nogat-terms-operator.md`) filled the same way; the page then links „Regulamin” at the bottom of the left panel, in the app menu and in the welcome window, with no footer statement

---

## 6. CLI Layer

### Technologies
- **Typer** (Click) - CLI framework; catalog groups via a custom Click group
- **Rich** - terminal formatting (`version`, `server`, `mcp`, `admin`)
- **HTTPX** - HTTP client

### Architecture
The CLI uses the library directly and downloads data straight from IMGW-PIB, ČHMÚ and PIG-PIB servers; it does NOT communicate through the REST API. All catalog groups (`datasets`, `stations`, `current`, `pmaxtp`, `store`, `series`, `analyses`, `commands`) are generated from `command_schema()` by `cli/_dispatch.py` (`ObserwatorGroup` + `register_catalog`): help texts and flags come from the catalog, raw option text goes to `run_command` (or `check_command` for `--check`), `--schema` prints the command schema. With `--json` stdout is the one-line JSON envelope `obserwator-result/1`, without it a short summary for a person in the language of `--lang` (`cli/_render.py`: status, the items of a list as a table of key fields and the page, the main fields of a document, the notices) (streams for `stations export`/`store export`/`series export`/`analyses export`/`commands guide` without `--output`; with it the envelope result is `{output, files[]}`), with `--json` notices go to stderr once, errors are the `obserwator-error/1` document (`schema`, `code`, `title`, `message`, `hint`?, `details`, `exit_code`, `command`?; `error_report.py`) as the last stderr line with the exit code of `ERROR_CODES` (envelope status: `partial` 10, `failed` 11, `cancelled` 130). The CLI therefore has no validation or business rules of its own — CLI = Python API = REST = MCP (`tests/contract/test_interface_contract.py`, `test_mcp_contract.py`). `OBSERWATOR_LANG=pl|en` picks the help language once at import (catalog texts, group descriptions and the Typer/Click elements such as „Opcje”/„Options”, „Użycie:”/„Usage:”, `[OPCJE]`, „Przerwano.”); an invalid value ends every `obserwator` call with a `validation_error` line (exit 2). `obserwator version`, `obserwator server`, `obserwator mcp`, `obserwator gui serve` (section 5), `obserwator config show` and `obserwator admin` stay outside the catalog (their help also in the language of `OBSERWATOR_LANG`).

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
| `read` (default) | `obserwator mcp` | 37 | none: writing commands have `check` fixed `true` (plan `obserwator-plan/1`), writing options (`output_dir`, `output`, `force`, `plan`) removed |
| `write` | `obserwator mcp --allow-writes --allow-dir DIR` / `OBSERWATOR_MCP_ALLOW_WRITES=true` | 37 | `check` defaults to `true`; writes with `check: false`, only inside `--allow-dir` (an absent `root` is the default root of the command's kind and an absent `raw_root` the default raw root, which must lie inside too) |
| `http` | `obserwator server` + `OBSERWATOR_MCP_ENABLED=true` → `/mcp` | 34 (commands with a REST route) | none (REST rules: the server's roots, `version` under `*/versions/`, hidden server paths) |

Results: `structuredContent` = envelope `obserwator-result/1` (the CLI `--json` stdout bytes also as text), `isError=false` for every envelope; errors `isError=true` with the CLI's `obserwator-error/1` document (`OSError` → `io_error`, other exceptions → `internal_error`; refused write → `forbidden`, `details.reason="writes_disabled"`, `no_allowed_dir` or `outside_allowed_dirs`). Streams up to 256 KiB as text with `result={schema: "obserwator-stream/1", format, bytes, lines}`. The server speaks English only (AGI-9.2: tool descriptions, instructions, error documents; `OBSERWATOR_LANG` does not reach it), so the tool list does not depend on the connection or the user's setting; Polish text is only an explicit `lang: "pl"` argument of `obserwator_commands_list`, `obserwator_commands_schema` and `obserwator_commands_guide`.

---

## 8. Versioned Store Layer

### Layers (two roots, ADR-017)
1. **Raw root** (marker `obserwator-store.json`) — the source archives: IMGW-PIB ZIP/CSV and ČHMÚ JSON/CSV bytes 1:1 under their server path; the station sources of the catalogs are archives too (station lists, ČHMÚ `now` metadata). The one exception: of IMGW-PIB's current-data API answers (`pl.imgw.hydro_now`, `pl.imgw.meteo_now`) the station sources keep a derived file with each station's code, name, river and coordinates (ADR-015 D5), and of the station pages of hydro.imgw.pl (`pl.imgw.hydro_details`) one derived file with each station's reference data (gauge zero and datum, river km, catchment area, year of establishment, province, district, warning and alarm levels, absolute extremes; ADR-021), and of the meteorological station pages (`pl.imgw.meteo_details`) one with each station's coordinates and elevation (ADR-021 erratum of 2026-11-23); the answers themselves, as they came, are captures (below). The PMAXTP cells (`cell.json`, `obserwator-pmaxtp/1`, beside the answer `response.json`) are downloads and live here too. Downloads and the sealing of captures write only this root.
   PIG-PIB's tables (ADR-035) are kept as Obserwator's capture container of a run's answers (gzip-compressed JSON Lines; a POST's address is the URL with its form as the query string), a new version only when the run's content in `pig-json/1` differs: the points `mwp/MapServer/0/MWP_points.jsonl.gz`, the readings one file per calendar month of their rows `mwp/MapServer/1/MWP_<YYYY-MM>.jsonl.gz` (the service holds one month, so a month not captured before it is replaced is lost; `store check` reports it `not_captured`), the chemistry and the watch list one file each; the night's answers of `mwp_auto` are captures (below). `store import --staging` (`store/staging.py`) writes PIG-PIB's interim capture here too, each version dated by its run.
2. **Data root** (marker `obserwator-data.json`) — what is built from the raw root, which the builders open read-only (no marker, staging or clean-up there): Parquet series per dataset/station (`obserwator-series/1`), `stations.geojson` catalog per provider, analyses per provider (`obserwator-analyses/1`: Hydrolog's answer lines byte for byte with the series versions, options and Hydrolog version they came from; ADR-016). In Nogat this is the root Obserwator's GUI, REST and MCP serve, and a public host gets the data root only (Nogat plan 2026-11-12 D2).
3. **Captures** (ADR-030 D3, D7) — every answer of a source of current data (IMGW-PIB's current-data API, hydro-back's maps, station pages and hourly series, ČHMÚ's `recent` and `now` files; one capture dataset each, tier `operational`) is written as it came, by any interface (the `current` commands, the GUI's snapshots, the live station search, `store sync` of the station sources, the hourly `current poll`, the night's harvest), to the capture spool `<state_dir>/obserwator/captures/<dataset>/<YYYY-MM-DD>/<YYYYMMDDTHHMMSS.ffffffZ>_<sha256>.json`, outside both roots: one file per answer, created with `O_EXCL`, so several processes write it without a lock. `store sync` of the capture datasets seals each closed UTC day of the spool into one archive version of the raw root and then removes the sealed spool files; the version lies in the day's slot directory below the source's server path (`api/data/hydro/<YYYY-MM-DD>/` inside the slot directory of the station source `pl.imgw.hydro_now`, which the readers tell apart by their file names).
   The night's harvest (ADR-030 D9): `store sync --pace-until HH:MM` of `pl.imgw.hydro_operational` or `cz.chmu.hydro_recent` first asks the source for the last closed UTC day (or the days of `--start`/`--end`, at most 40 back), one request per station and series, spread evenly to that local time and never closer than 5 s (`fetch.PacedSession`: backoff 60, 120, 240 s after 429 and 5xx, three connection failures end the run, gzip); its answers land in today's spool day, which that run seals too. A `store sync` that seals captures holds `flock` on `<state_dir>/obserwator/store-sync.lock` for its whole run (a second one waits 600 s, then `conflict`, `sync_locked`; ADR-030 D10); archive syncs and checks take no lock, so Archiwista's downloads never wait on the timers.
   PIG-PIB's harvest (ADR-035 W9): `store sync --pace-until` of `pl.pig.groundwater_operational` takes no days and no stations: it asks `mwp_auto`'s automatic points, the table's count and every row appended after the last `OBJECTID` of the newest capture (`extra.capture.watermark` of its sidecar; 0 in an empty root), page by page until a short one, then the stored hour 02 of each summer-time start day among them, and seals today's capture with `extra.capture` (`watermark`, `count`, `period`), so it keeps no state outside the raw root.
4. A rebuildable local index is out of scope; no `.db` file is ever part of either root.

### Layout
```text
<raw root>/obserwator-store.json                        # obserwator-store/1 marker: schema, tool, created_at, producer_version (+ optional created_by); written by the first write
  archives/versions/<server dir>/<stem>/<label>_<sha8>/<file> + <file>.meta.json
  archives/versions/<server dir>/<YYYY-MM-DD>/<YYYY-MM-DD>_<sha8>/<YYYY-MM-DD>.jsonl.gz + .meta.json   # a capture of one UTC day (ADR-030 D3)
  archives/versions/mwp/MapServer/<n>/<stem>/<label>_<sha8>/<stem>.jsonl.gz + .meta.json   # PIG-PIB: the answers of a run, the points (0, MWP_points), the readings (1, MWP_<YYYY-MM>), chemistry and watch list (2, 3; ADR-035)
  archives/versions/mwp_auto/MapServer/<YYYY-MM-DD>/<YYYY-MM-DD>_<sha8>/<YYYY-MM-DD>.jsonl.gz + .meta.json   # PIG-PIB's night's capture of mwp_auto, its watermark in extra.capture (ADR-035)
  archives/versions/<server dir>/<stem>/observations/  # obserwator-observation/1 signal register (read-only for consumers)
  pmaxtp/versions/<POT|AMP>/<indX>_<indY>/<label>_<sha8>/cell.json + response.json + .meta.json
  .incoming/<host>_<pid>_<token>/                       # staging; leftovers >24 h cleaned

<data root>/obserwator-data.json                        # obserwator-data/1 marker: the same fields; written by store init --kind data or the first build
  series/versions/<slug>/<label>_<sha8>/series.json + .meta.json + stations/<code>.parquet   # <slug> imgw_*, chmu_*, gdanskiewody_* or pig_* (ADR-028)
  series/versions/<slug>/<YYYY-MM>/<label>_<sha8>/series.json + .meta.json + stations/<code>.parquet   # a month of a sub-daily series: slot series:<key>:<YYYY-MM> (ADR-031)
  stations/versions/imgw_stations/<label>_<sha8>/stations.geojson + .meta.json   # IMGW-PIB catalog
  stations/versions/chmu_stations/<label>_<sha8>/stations.geojson + .meta.json   # ČHMÚ catalog
  stations/versions/<acronym>_stations/<label>_<sha8>/stations.geojson + .meta.json   # another provider's catalog (gdanskiewody, ADR-034; pig, ADR-035; a provider file's acronym, ADR-033)
  analyses/versions/<pl.imgw|cz.chmu>/<label>_<sha8>/analyses.json + .meta.json + stations/<code>.json + stations/<code>/<id>.json  # Hydrolog's answers (ADR-016)
  .incoming/<host>_<pid>_<token>/                       # staging; leftovers >24 h cleaned (an interrupted analyses build's stations resumed first)
```

- `<sha8>` = first 8 hex digits of the full SHA-256 of the main file; labels come from `Last-Modified` (UTC) or download time.
- Every main file has an immutable `obserwator-meta/1` sidecar: producer/version, dataset, country and provider (from the registry), request, provider license and attribution, `downloaded_at`, `sha256`, `size_bytes`, HTTP signals; ČHMÚ and PIG-PIB datasets with a canonical content form add `content_sha256`/`content_form`, and a dataset whose tier is not `verified` (the captures) `tier` and `publication` (ADR-030 D6). A path in a sidecar is relative to its own root, as its first directory tells: the sources of a series or catalog (`file`) under `archives/` of the raw root, the series a catalog read under `series/` of the data root.
- Append-only: no overwrite and no `latest` path; hard links only move staged files into a version (after publication each stored file has one name, a relabeled version is a copy). The current version is computed by `current_version(root, slot=...)` with slots `archive:<key>:<file>` (a capture `archive:<key>:<YYYY-MM-DD>.jsonl.gz`), `pmaxtp:pl.imgw.pmaxtp:<METHOD>/<indX>_<indY>` of the raw root and `series:<key>`, `catalog:pl.imgw.stations`, `catalog:cz.chmu.stations`, `catalog:pl.pig.stations`, `analyses:pl.imgw.analyses`, `analyses:cz.chmu.analyses` of the data root (spec §13.7, ADR-017 D2); the slot decides the kind of root, and a root of the other kind is `store_unavailable` (`details.reason="wrong_root"`); `observations/` is never a version candidate. A new HTTP signal with identical bytes is `relabeled` (a copy), identical signal and bytes are `unchanged`; for datasets with a content form (`chmu-json/1`: ČHMÚ hydro files and station lists, JSON without the regenerated envelope keys, RFC 8785; `pig-json/1`: PIG-PIB's runs, the rows sorted by their key without `OBJECTID` and paging, ADR-035) other bytes with the current version's `content_sha256` are `unchanged` (notice `content_unchanged`) and a new source signal is written once to `observations/` (ADR-003 D17, D18).
- A capture version (ADR-030 D3 and its errata): `<YYYY-MM-DD>.jsonl.gz`, gzip of level 9 with the time 0 and no file name around canonical JSON Lines sorted by time, address, SHA-256 and status, each line an answer (`time`, `address` without any credential, `status`, `sha256`, `body` or `body_base64`), an answer equal to the one before it from its address `seen: true` without its body, so the same answers give the same bytes; the label is the day (`label_source` `downloaded`), the sidecar adds `extra.capture.answers` and the source's address as `extra.http.url`. Sealing a day again joins the answers of its current version with the spool's: late answers give a new version holding every answer, nothing new is `unchanged`; today (UTC) is never sealed, and a spool file that cannot be read stays (`capture_unreadable`).
- Publication (the Kartograf model, ADR-001 erratum 2026-10-19): write into a unique `.incoming/` staging directory and `fsync`, then hard-link (`os.link`, never replaces a target) every file into `<label>_<sha8>/`, the main file's sidecar last — it commits the version. A version directory without that sidecar is an interrupted publication: skipped by `current_version` and writers, reported by `iter_store` as `missing_sidecar`, completed by the next write of the same content under the same label. A failure or Ctrl+C during publication never removes a linked data file (a concurrent writer of the same bytes may have kept it and committed its own sidecar), so it leaves an interrupted publication; only empty directories created by that write are removed, and a linked sidecar is never removed. Versions are never cleaned automatically: the catalog label is the build date, PMAXTP and archives without `Last-Modified` use the download date (UTC), so an interrupted publication that is not repeated with the same content under the same label (e.g. a catalog rebuilt the next day) stays and is removed by hand — the whole `<label>_<sha8>/` directory without the sidecar, while no write to the store runs.
- Resume of `analyses build` (ADR-016 erratum 2026-11-21, Nogat ECO-073): a build that ends before it publishes keeps its staging directory when it holds stations it computed, and the next build, before the 24 h cleanup, hard-links from every other staging directory each station to compute whose record there is whole, holds the inputs of now (series versions, station Parquet SHA-256s, thresholds, Hydrolog version, registry digest) and whose result files match their SHA-256. Without locks this is safe by the rules every writer keeps — unique staging, files written once and fsynced, a station's record after its results, no-replace links, removal of whole directories only — and it never changes another staging directory, which may belong to a build still running.
- File system: the store needs hard links, the same requirement as Kartograf's store (its ADR-036 D18, D21, D22) — versions, observations and the markers `obserwator-store.json` and `obserwator-data.json` are all published by `os.link`. Works on Linux, macOS and Windows (ext4, APFS, NTFS, SMB shares with hard links); a file system without them (FAT, exFAT, some NAS/FUSE, the macOS SMB client) is refused by `init_store` and every write with `ObserwatorStoreConflictError` (`details.reason="not_atomic"`); reading needs no hard links. Directory `fsync` is skipped on Windows and where the file system does not support it.
- `stations.geojson` of IMGW-PIB: `meteo_kind` of a meteorological station is `synop` when the current `pl.imgw.meteo_synop_daily` series holds it, otherwise `climate` when the current `pl.imgw.meteo_climate_daily` series does, otherwise `precipitation` when the current `pl.imgw.meteo_precip_daily` series does, else `null` (always `null` for ČHMÚ; ADR-022 D5); `check_catalog` reports the series action as `newer` when it differs from the catalog, and `build_catalog` gives a `series_missing` notice naming the ones the data root lacks (a warning when it holds none of them).
- A root never nests in another store of any Nogat tool, nor in the other Obserwator root: `init_store` and every write check the ancestors and the existing descendants by marker file name only (`output.STORE_MARKERS`: `kartograf-store.json`, `obserwator-store.json`, `obserwator-data.json`; nothing is imported from Kartograf) and refuse with `conflict` (`details.reason="nested_store"`), and so is a directory with both Obserwator markers (`store_info` and `iter_store` report it as `conflicting_markers`); a root that holds other files and is no store (or is a file) is `conflict` with `details.reason="not_empty"`. Every write refuses such a root before any request (`refuse_root`). A root of the other kind than a function needs is `store_unavailable` with `details.reason="wrong_root"` and `details.kind` (ADR-017 D3; a store not yet split is a raw root). A root with the layout of its kind but no marker is `store_unavailable` (`details.reason="no_marker"`, hint `obserwator store init --root`, with `--kind data` for a data root) and an unreadable marker is `data_error` (`details.reason="invalid_marker"`). The `--check` plan of every store write (`datasets download`, `store init`, `store sync`, `pmaxtp sync`, `series build`, `store catalog`) shows a refusal that is a `conflict` as its one action `conflict` with `reason="nested_store"` or `"not_empty"` and the root as `path`; the plan itself is `ok` and makes no request (`root_conflict_plan`); `store_unavailable` and `data_error` are raised by the check (DEV-19.10, ADR-007 erratum).

### Data Output (ADR-007, DEV §19)
Every writing command has one of two ways of writing, with the same names in Python, CLI, REST and MCP (`obserwator/output.py` is the one implementation of the plain way):

| Target | CLI / Python | Writes | `files[].status` |
|---|---|---|---|
| plain files | `-o`, `--output-dir` / `output_dir=` | the files only, named as in the store, no metadata | `written`, `replaced` |
| store | `-r`, `--root` / `root=` | versions with sidecars in the root of the command's kind (section 8) | `new`, `unchanged`, `relabeled` |
| none given | — | the default root of the command's kind: the raw root of a download (`OBSERWATOR_RAW_ROOT`, `[obserwator] raw_root`, `<data_dir>/obserwator-raw`), the data root of a build (`OBSERWATOR_ROOT`, `[obserwator] root`, `<data_dir>/obserwator`); `obserwator config show --json` names both and their sources | as store |
| one file | `--output` / `output=` | one export file (`stations export`, `store export`, `series export`, `analyses export`, `commands guide`); result `OutputReport` | `written`, `replaced` |

- `output_dir` and `root` exclude each other (`validation_error`, `details.reason="exclusive_options"`). The commands whose input or result is the store (`series build`, `store catalog`, `analyses build`) are store-only: they have no `output_dir` (rule in their catalog entry); `--plan` with `output_dir` is refused (`store_only_option`); a dataset without a store form is refused with `not_in_store`; `store sync --output-dir` of a station-year dataset (ČHMÚ) needs `years` (`years_required_in_plain_mode`), because a plain write does not read the server listing.
- Plain names are the store names: for `datasets download` the provider's server path, kept as sub-directories because names collide across folders. `obserwator pmaxtp sync` names its two files by the cell indices of the answer (deviation DEV-19.5/19.6 in `CLAUDE.md`).
- Preflight before the first byte (`refuse_directory`, `plan_plain`, `refuse`): an output directory that is or lies in a store is `conflict` with `details.reason="output_in_store"` and `details.paths` the directory, before any request (it applies to every target); then the whole target list is built; duplicate names → `conflict` with `details.reason="duplicate_output_name"`, a target that would enter a subdirectory with a marker → `output_in_store` (its path), an existing target without `--force` → `output_exists`; `details.paths` lists every offending path. `--check` returns the plan with actions `write`, `replace` (with `--force`) or `conflict` per target; a plan with conflicts is still `ok`.
- Writing (`Staging`): files go to `<dir>/.obserwator-incoming/<host>_<pid>_<token>/` on the same file system, are hashed while written (`sha256` of `files[]`) and moved with `os.replace`; the staging directory is removed on success, error, SIGINT and SIGTERM (a first Ctrl+C lets the command finish its step; a second, or SIGTERM, ends it with exit 130 or 143), leftovers older than 24 h by the next run. No sidecar, hard link or `versions/`, so FAT, exFAT and SMB work. `--force` only replaces the named targets, never deletes other files; in the store `--force` fetches again and gives a new version or `unchanged`, never an overwrite.
- Surfaces: the REST server writes only to its own `OBSERWATOR_RAW_ROOT` and `OBSERWATOR_ROOT`; MCP writes only inside `--allow-dir` (section 7); a refused write is `forbidden`.

### Flow
```
keep          ── every answer of a capture source on any request path (fetch._get, _archive_response, stations._station_details) ──▶ ProviderAdapter.capture → the spool in state_dir (never a root; a failure is one warning record)
poll_current  ── one GET per polled source, skipped while its declared interval has not passed ──▶ the spool only (current poll, the hourly timer)
harvest       ── store sync --pace-until: the adapter's harvest_requests (station list through the session) ──▶ PacedSession.run, one GET at a time to the deadline ──▶ the spool (HarvestReport)
check_store   ── raw root; IMGW-PIB: listing + HEAD (synop archives: the folder index names the files, ADR-022; the telemetry: the datastore's listing `POST getFilesList` alone); ČHMÚ: one directory listing (no HEAD/GET); Gdańskie Wody: the month files the stored station list names, against the clock (`ProviderAdapter.settled`), no request (ADR-034 D6); PIG-PIB: the one file each table publishes now (`ProviderAdapter.published`: one statistics POST for the readings' month), a stored one unverifiable, the months no capture can fill `not_captured` (ADR-035); station sources: lists by HEAD, `now` metadata and hydro.imgw.pl details unverifiable; captures: the closed UTC days of the spool against the raw root (with pace_until today's too), no request ──▶ StorePlan (obserwator-plan/1, saved outside the roots; series_state {})
sync_store    ── HEAD again (none for the telemetry); changed → stale_plan; GET only new/missing ──▶ archive versions only, in the raw root (ČHMÚ: content_unchanged + observation; ADR-015; PIG-PIB: the table paged by POST in one run, another month than planned → stale_plan, a changed month → month_republished, ADR-035); captures: each closed day (and today after a harvest) sealed into one version, then its spool files removed (ADR-030)
build_series  ── current archive versions of the raw root (read-only) → Parquet snapshot in the data root (`unchanged` if the current series version has the same inputs); ČHMÚ and IMGW-PIB synop: per-station periods (a synop station's yearly archive supersedes its records in the monthly files of that year); a sub-daily series (store/subdaily.py, ADR-031): one version per month from the full hours of the closed UTC days of the captures, the telemetry and ČHMÚ's validated hours, the highest tier of each station, variable and hour; Gdańskie Wody's series from its month files (ADR-034 D8): the daily ones by the provider's day through its parser, the hourly ones one version per month through `ProviderAdapter.hourly_points`; PIG-PIB's readings from its month files, newest version first per point and date, and its hourly series from the captures of mwp_auto, `H_asl` from the points version (`ProviderAdapter.series_sources`, ADR-035)
build_catalog ── one provider, offline: the station sources stored in the raw root (lists and `now` metadata; missing → not_found; IMGW-PIB's hydro.imgw.pl details optional, ADR-021) + static/user locations + series indexes of the data root → stations.geojson in the data root
build_analyses ── current series and catalogs of the data root → Hydrolog's batch in a separate process → one analyses version per provider in the data root (ADR-016); a meteo station's daily record joins its synop, climate and precipitation series by day and variable (ADR-022)
read_*        ── offline, read-only, each in the root of its kind; problems reported as StoreEntry(kind="problem"), observations as kind="observation"
```

Every write operation has a `check_*` twin that never writes or GETs data; long operations accept `on_progress`, `on_notice` (Polish messages) and `cancel` (between files; cancellation never publishes a partial version).

### Schema Versioning (IMGW-13)
Contracts with their own `/N` counters, independent of the package version:

| Contract | File / use |
|---|---|
| `obserwator-store/1` | `<raw root>/obserwator-store.json` marker of a raw root (`schema`, `tool`, `created_at`, `producer_version`, optional `created_by`; a reader needs only `schema`) |
| `obserwator-data/1` | `<data root>/obserwator-data.json` marker of a data root (the same fields; ADR-017) |
| `obserwator-meta/1` | `<file>.meta.json` sidecar of every version (optional `content_sha256` + `content_form`, always together; optional `tier` + `publication`, always together, ADR-030 D6) |
| `obserwator-series/1` | `series.json` index of a Parquet series (+ Parquet metadata) |
| `obserwator-plan/1` | `plan.json` freshness plan outside the store |
| `obserwator-pmaxtp/1` | `cell.json` PMAXTP cell (Obserwator extension) |
| `obserwator-observation/1` | `observations/<YYYY-MM-DD>_<sha8>.json` signal register in an archive slot (ADR-003 D18) |
| `obserwator-result/1` | result envelope of `run_command`/`check_command`, CLI stdout with `--json` and REST body |
| `obserwator-commands/1` | `command_schema()` document (Nogat `commands-1`) |
| `obserwator-command-list/1` | `list_commands()` summary |

Within `/1` only optional fields are added; readers tolerate extra fields in store files. A breaking change requires `/2` with a transition period reading both. Unknown versions are reported (`store_info(...).supported is False`, scan problems) and never parsed or written by old code. Before the 3.0.0 tag the `/1` value domains were opened for further providers (ADR-003 D2, task C01): dataset key `^[a-z]{2}\.[a-z][a-z0-9]*\.[a-z][a-z0-9_]*$`, `country` `^[A-Z]{2}$`, `provider`/`license.id` any non-empty text, station codes 9-digit IMGW or WIGOS (`STATION_CODE_PATTERN`), ČHMÚ `location_source` values; a sidecar of a known dataset must still match the registry's country and provider. The ČHMÚ provider (same release) only adds optional fields: sidecar `request.station_code`/`param`, `extra.period.station_code`, `license.terms_url`; series `stations[<code>].periods`, Parquet `<V>_quality`/`<V>_source_flag`; catalog `thresholds`; plan items `station_code`/`signal`/`remote_listed_at`/`local_observation` and plan `requests`. ADR-004 adds `lang`, `x-obserwator.writes`/`network`/`operation_id` and `x-obserwator-writes` to `obserwator-commands/1`. IMGW files keep identical bytes.

### Integrations
- **Archiwista** consumes both roots only through the public read API (`store_info`, `iter_store`, `current_version`, `read_meta`, `read_catalog`, `read_station_list`, `read_archive`, `read_series_index`, `read_series`, `summarize_series`, `read_pmaxtp`), for both providers (`provider` on entries, catalogs and stations; `read_catalog(root=, provider=)`). Obserwator's library is the only writer; no Archiwista files or indexes live in either root. In Nogat, Archiwista keeps the raw root, whose downloads it orders through Obserwator's library, and reads the series and catalogs from the data root (Nogat plan 2026-11-12 D2, D5, step R2). `iter_store` also returns read-only `kind="observation"` entries. A capture is an archive version of its dataset (slot `archive:<key>:<YYYY-MM-DD>.jsonl.gz`), indexed as any archive; its sidecar's `tier` and `publication` are `Meta.tier` and `Meta.publication` (ADR-030 D6). Offline fixtures: `obserwator.testing.build_fixture_store(root, *, data_root, variant=…)` → `FixtureRoots(raw, data)` (`complete`, `complete_pl_cz`, …), `fixture_files()` (archives, listings, recordings, contract schemas). `store_info(root).store_schema` tells the kind of a root; what a reader needs of the marker is its `schema` (as `open_store`); each problem of `StoreInfo.problems` has a code in `problem_codes`; `Meta.producer` and `Meta.producer_version` say which release wrote a version; `iter_store(skip_versions=…)` returns the versions the consumer already knows as `skipped` entries, without listing or reading them (incremental scan; ADR-007 errata of 2026-10-25).
- **Retman** runs data actions as a handler via the public command catalog (`command_schema`, `data_commands`, `validate_command`, `format_command`, `check_command`, `run_command`), getting the same options, validation, envelope, error codes, progress and notices as the CLI and REST; English descriptions from `command_schema(lang="en")`, effects from `x-obserwator.writes`/`x-obserwator.network`. The `root` of a command is a root of its kind, and `series build` and `store catalog` take `raw_root` too (its command list follows in the Nogat plan's step R2).
- **AI agents** read `AGENTS.md`/`llms.txt` (derived from the catalog by `agent_guide`) and call the MCP tools or any other interface.
- **Projects** that pin store versions (by `sha256` and the sidecar's `content_sha256`) belong to Archiwista (`archiwista-project.json`, `archiwista-project/1`, ADR-008); Obserwator keeps no project files.

### CSV Parsing Notes
IMGW-PIB archives are inconsistent between years; parsers auto-detect the format per file:
- Encoding: CP1250 for most archives, UTF-8 with BOM for the 2023 daily archive (auto-detected)
- Delimiter: comma with quoted fields (e.g. 2019-2022, 2024) or semicolon (e.g. 2023), auto-detected
- Quoting: 2024 daily/monthly files wrap whole lines in outer quotes with doubled inner quotes (auto-unwrapped)
- Missing data codes: `9999` (H), `99999.999` (Q), `99.9` (T); meteo status 8 = `missing`, 9 = `no_phenomenon`; an `o_d` precipitation total with status `Z` or directly after a listed day without a measurement (status 8) = `accumulated`, the series build carrying such days from one monthly archive to the next
- Synop archives (`s_d`, 65 columns, and `s_d_t`, 23 columns, per station and folder or per month of the whole country): the first 18 columns of `s_d` are those of `k_d`; a station file holds only codes ending with its number; every day of the archive's period is a record of each station (ADR-022)
- Hydrological year: Nov 1 - Oct 31
- ZIP reading with member count/size limits and no path traversal; unreadable ZIP → `ObserwatorDataError`

ČHMÚ files (`_parsing/chmu.py`): hydro JSON `{"objID", "tsList"}` (`HD`/`QD`/`TD` → H/Q/T, `PD` skipped, `null` → `missing`, missing row = no record), meteo CSV `STATION,ELEMENT,TIMEFUNC,DT,VALUE,FLAG,QUALITY` (`SRA`, `TMA`, `TMI`, `SCE`, `SNO`: a row at the term of its observation, `TIMEFUNC` = the time of `DT`, today's or an older one, is the value of the date of `DT`; `T`: `AVG` is the daily mean and its term rows are skipped; `QUALITY` → `quality`, `FLAG` → `source_flag`; `0.0` of `SRA`, `SCE` or `SNO` without flag → `no_phenomenon`, with a flag (trace `T`, dusting `P`, discontinuous cover `N`, melted `R`) → `value`), metadata JSON located by column names (meteo `GEOGR1` = longitude, hydro `GEOGR1` = latitude; numbers read as `Decimal`), nginx listings (name from `href`, UTC minute, size). Errors → `ObserwatorDataError` with file name and place.

---

## 9. Data Formats

### Input (from the sources)
- IMGW-PIB: ZIP archives with CSV files; JSON from the real-time API and PMAXTP
- ČHMÚ: JSON per station and year (hydro), CSV per station and element (meteo), JSON metadata with an envelope, nginx directory listings (HTML)
- Gdańskie Wody: JSON of an API with a key (`Authorization: Bearer`): the station list and one station's quantity over one provider's day; every error an HTTP 200 answer that says so in its body (ADR-034)
- PIG-PIB: JSON answers of ArcGIS REST queries (POST, paged by `resultOffset`, `returnCountOnly`, `outStatistics`), kept in Obserwator's capture container of a run's answers; an error is an HTTP 200 `{"error"}` answer (ADR-035)

### Output (to clients)
- JSON envelope `obserwator-result/1` (CLI stdout with `--json`, REST body, MCP `structuredContent`); without `--json` the CLI prints a short summary for a person; errors as CLI JSON line, `application/problem+json` or MCP tool error
- Generated URLs (for direct IMGW-PIB, ČHMÚ and PIG-PIB downloads)
- Store products: Parquet series, GeoJSON (RFC 7946) station catalogs, CSV export with units and the provider's attribution (IMGW-PIB terms, ČHMÚ CC BY 4.0, Gdańskie Wody's draft lines with the notice of a source of the class `other`, PIG-PIB's CC BY 4.0 lines W with its period and date filled, WP and RW, with the same notice), JSONL archive export; in the raw root the captures of current data (gzip-compressed JSON Lines of the answers as they came)
- Agent guide: `AGENTS.md` and `llms.txt` (markdown, `text/markdown` in REST)
- The GUI: its page and private JSON API (`obserwator-gui-session/1`, `obserwator-analysis/1`, `nogat-handoff/1`) and the files of the exports above (section 5)

### GIS Integration
- `stations.geojson` with WGS84 points per provider (stations without a valid location keep `geometry: null` and a reason; ČHMÚ hydro stations carry SPA `thresholds`, IMGW-PIB hydro stations the details of hydro.imgw.pl: gauge zero, river km, catchment area, warning and alarm levels, absolute extremes; ADR-021; PIG-PIB's points their `hydrogeology`, ADR-035)
- A location counts only in its provider's country (ADR-018): inside the packaged state border of Poland (PRG of GUGiK) or Czechia (RÚIAN of ČÚZK), built by `scripts/build_borders.py` and read by `obserwator._borders`, or nearer to it than its 50 m simplification tolerance plus the location's uncertainty (at least 150 m); else `location_missing_reason="outside_country"`. The border's line (G of GUGiK, Z of ČÚZK) joins the attribution of the catalog and of every product of it
- The GUI's map (MapLibre GL JS) draws the stations of every served catalog (the outline by source class), IMGW-PIB's current measurements and the PMAXTP point (section 5)
- ~~WFS/WMS integration~~ - not implemented

---

## 10. Scaling Considerations

The service is stateless by default:
- No session state
- No database
- The optional store is two plain directories, the raw and the data root (local disk or network share), with append-only versions; concurrent writers are safe thanks to unique staging and no-replace publication
- The capture spool in `state_dir` takes one new file per answer, created with `O_EXCL`, so the GUI, the REST server, the hourly poll and a CLI run share it without a lock
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
attribution). The environment is `uv.lock` (`uv sync --locked --all-extras`, the
gate's first step).

**CI:** GitHub Actions run the gate on Linux, macOS and Windows with Python 3.12
(required) and 3.15 (reported, not blocking) on pushes and pull requests to `main`
and `develop` (`.github/workflows/ci.yml`, DEV-7.7); its commit step checks commits
only of pull requests into `develop` and of `hotfix/*` into `main` (DEV-4.5). The
same workflow audits the locked PyPI dependencies with `pip-audit`, also weekly
(informative, DEV-13.6). The `live` tests run weekly and on demand
(`.github/workflows/live.yml`), and Dependabot updates the Actions weekly into
`develop` (`.github/dependabot.yml`). Templates: `standards/ci/` of the Nogat
standard. The GUI's browser tests (`tests/e2e/`, Playwright) skip where Chromium
is not installed, as in CI.

**Deployment:** Docker (`docker/`) for the REST server, its logs and the capture spool on a volume of
`<state_dir>/obserwator` and nginx keeping no log; the GUI as a service of its
own on 127.0.0.1 behind an authenticating proxy (`docs/USAGE.md`, „GUI”).

---

## 12. File Structure

```
Obserwator/
├── src/obserwator/
│   ├── __init__.py       # PUBLIC API entry point (single __all__)
│   ├── output.py         # Plain output (ADR-007): resolve_target, refuse_directory, plan_plain, refuse, Staging, FileResult, OutputReport; markers STORE_MARKERS, DATA_MARKER
│   ├── _environment.py   # nogat.toml, NOGAT_* variables, user directories, [nogat.gui] and [nogat.operator]
│   ├── attribution.py    # Provider attribution and terms lines of every product (ADR-012)
│   ├── _borders.py       # Packaged state borders of Poland and Czechia (ADR-018), read by the catalog, the GUI and attribution
│   ├── _http_headers.py  # Security headers of both servers (nosniff, Referrer-Policy, Permissions-Policy)
│   ├── _file_names.py    # The names of the files both servers send (Nogat DEV-19.21): obserwator_<content>_<qualifiers>.<extension>
│   ├── nogat_logging.py  # Nogat's reference logging module, copied byte for byte: logs of both servers (ADR-019)
│   ├── _version.py       # Version, single source (pyproject reads it)
│   ├── fetch.py          # PUBLIC: fetch_* (live), download_archives, download_* -> DownloadResult; PacedSession (the harvests' pacing, backoff and gzip)
│   ├── captures.py       # PUBLIC: poll_current; the capture spool, [obserwator.capture], the hourly poll, the night's harvest (ADR-030)
│   ├── models.py         # PUBLIC: Data models incl. NormalizedRecord, Measurement
│   ├── stations.py       # PUBLIC: find_stations (IMGW-PIB, ČHMÚ and PIG-PIB; Gdańskie Wody where named)
│   ├── exceptions.py     # PUBLIC: Custom exceptions + ERROR_CODES (title as a catalog message)
│   ├── error_report.py   # PUBLIC: obserwator-error/1 document (ErrorReport, error_report) and hints
│   ├── messages/         # Message catalog: message(), Message, localize(), Text(en, pl) per area (ADR-006); gui/: the GUI's texts
│   ├── urls.py           # PUBLIC: IMGW URL constants, build_pmaxtp_url, build_api_url
│   ├── parsers.py        # PUBLIC: Parser re-exports (IMGW-PIB hydro/meteo, ČHMÚ, Gdańskie Wody, station lists)
│   ├── datasets.py       # PUBLIC: Provider and dataset registry, archive_files, YearsArg/MonthsArg
│   ├── coverage.py       # PUBLIC: summarize_coverage
│   ├── commands.py       # PUBLIC: Command catalog, command_schema, run_command
│   ├── agent_guide.py    # PUBLIC: agent_guide (AGENTS.md, llms.txt), MCP instructions
│   ├── testing.py        # PUBLIC: build_fixture_store → FixtureRoots(raw, data), fixture_files
│   ├── _jsonable.py      # Single JSON converter (envelope, relative paths)
│   ├── _examples.py      # Example calls of the catalog (examples of command_schema)
│   ├── reference_data.py # Fetch IMGW-PIB reference data into reference_dir (OBSERWATOR_REFERENCE_DIR)
│   ├── instance.py       # [obserwator.instance] of nogat.toml (ADR-025): load_instance, Instance, the one filter of both servers
│   ├── config.py         # Settings (incl. hydrolog_command)
│   ├── _hydrolog.py      # Hydrolog's program: `commands batch` in a separate process (ADR-016)
│   ├── _data/            # Poland and Czechia borders (PRG of GUGiK, RÚIAN of ČÚZK; ADR-018), agents/ templates, packaged fixtures, recordings, contract schemas
│   ├── _parsing/         # common.py, hydro.py, meteo.py, stations.py, chmu.py, files.py, gdanskiewody.py, pig.py (ADR-035)
│   ├── providers/        # One adapter per provider behind ProviderAdapter (ADR-029): base.py, pl/imgw.py, cz/chmu.py, pl/gdanskiewody.py (ADR-034), pl/pig.py (ADR-035), files.py (ADR-033)
│   ├── store/            # types, writer (the store's one canonical JSON, new-file write, file checksum and archive slot directory), content, sync, captures (the sealing of the capture spool, ADR-030), series, catalog, files (store import, ADR-033), staging (store import --staging, ADR-035), pmaxtp, reader, export, plain (plan of a plain write), analyses and analysis_registry (ADR-016)
│   ├── api/              # REST API [optional]
│   │   ├── main.py       # FastAPI app (/health, /api/v1, /llms.txt, /docs, /mcp; GET / redirects to /docs)
│   │   ├── routes/commands.py  # Routes generated from the command catalog
│   │   ├── instance.py   # The instance on the REST routes (ADR-025): check_start, Scope of each request
│   │   ├── publication.py  # [obserwator.capture] on the REST routes (ADR-030 D5): a private capture → not_found
│   │   ├── errors.py     # problem+json handlers, hide_server_paths, Accept-Language
│   │   └── schemas.py    # HealthCheck
│   ├── cli/              # CLI [optional]
│   │   ├── main.py       # Entry point (version, server, mcp, admin, config, gui, catalog groups)
│   │   ├── config_cmd.py # obserwator config show
│   │   ├── gui_cmd.py    # obserwator gui serve
│   │   ├── _dispatch.py  # Catalog-driven command generation (only adapter), OBSERWATOR_LANG
│   │   ├── _render.py    # Summary for a person of the envelope (without --json)
│   │   └── admin.py      # REST API key management (api_keys.json)
│   ├── mcp/              # MCP server [optional: obserwator[mcp]]: _tools, _calls, server
│   └── gui/              # GUI [optional: obserwator[gui]]: obserwator gui serve, entry point nogat.gui (ADR-013)
│       ├── _app.py       # Starlette app: private API, headers; _page, _root, _live, _analyses, _stripes, _traffic, _feedback, _admin, _terms, _http, _params, _config, _state, _serving, _extra
│       └── web/          # the page: Preact + htm modules, charts, MapLibre, Nogat's kit and tokens, instrukcja/, admin/
├── AGENTS.md, llms.txt   # Agent guide — derived from the catalog (obserwator commands guide)
├── deploy/               # user systemd timers (night, telemetry, current poll) and the backup script with its timer (USAGE.md "Timers", "Backups")
├── docker/               # Docker configuration (Python 3.12 image with .[api,mcp,store], compose with the logs volume, nginx with /mcp, the jobs service of the timers)
├── tests/                # Tests (unit, contract, e2e, live; fixtures/store with synthetic IMGW-PIB and ČHMÚ archives, recordings, PIG-PIB's pig_recordings.json; fixtures/pig_staging; fixtures/export_golden)
└── pyproject.toml        # Project configuration
```
