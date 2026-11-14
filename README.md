# Obserwator - A tool for downloading IMGW and ČHMÚ data

A Python library and tools for downloading public data from the Institute of Meteorology and Water Management (IMGW-PIB) and, since 3.0.0, also from the Czech Hydrometeorological Institute (Český hydrometeorologický ústav, ČHMÚ). The data come from the [IMGW Dane Publiczne](https://danepubliczne.imgw.pl/) (IMGW public data) and [ČHMÚ Open Data](https://opendata.chmi.cz/) services.

It also supports data from the probabilistic models of maximum precipitation (PMAXTP) from the [IMGW Klimat](https://klimat.imgw.pl/opady-maksymalne/) service.

Until release 2.1.1 the tool was called IMGWTools (`pip install imgwtools`, command `imgw`); since 3.0.0 it is Obserwator, because IMGW-PIB is the institute whose data it reads, not the tool ([ADR-009](https://github.com/Daldek/Obserwator/blob/main/docs/DECISIONS.md#adr-009-the-tool-is-called-obserwator)). The old and new names with the migration: [changelog](https://github.com/Daldek/Obserwator/blob/main/docs/CHANGELOG.md).

---

## Features

- **Python library** - `pip install obserwator` for integration with other projects
- **CLI** - `obserwator`, commands generated from the command catalog
- **REST API** - FastAPI with OpenAPI/Swagger documentation, routes generated from the same catalog
- **MCP server** - `obserwator mcp` (extra `obserwator[mcp]`) and the `/mcp` endpoint of the REST server: the catalog commands as tools for AI agents, read-only by default
- **GUI** - `obserwator gui serve` (extra `obserwator[gui]`): every station of IMGW-PIB and ČHMÚ on a map, the station panel with its series as a chart and a table, current IMGW-PIB measurements, analyses computed by Hydrolog and downloads (CSV, JSON, Parquet, GeoJSON), PMAXTP of a point

Since 3.0.0 all interfaces use one catalog of 35 commands (`obserwator commands list`, `obserwator commands schema`): the same option name in Python, CLI (`--option-name`), REST (parameter or JSON field) and MCP (tool argument), the same validation, one result envelope `obserwator-result/1` and one error code registry (`ERROR_CODES`). Machine output (envelope, errors, notices, catalog descriptions, the guide for AI agents, the MCP server) is in English; Polish texts are available on request (`--lang pl`, `Accept-Language: pl`), while CLI help and human-readable CLI lines are in Polish (`OBSERWATOR_LANG=en` switches them to English). Guide for AI agents: [`AGENTS.md`](https://github.com/Daldek/Obserwator/blob/main/AGENTS.md) and [`llms.txt`](https://github.com/Daldek/Obserwator/blob/main/llms.txt).

**Supported data:**
- Current hydrological, meteorological and synoptic data through the IMGW API
- Historical archive data of IMGW-PIB (ZIP/CSV) and ČHMÚ (JSON/CSV per station) — a registry of 22 datasets of two providers (`pl.imgw.*`, `cz.chmi.*`)
- Hydrological and meteorological warnings
- PMAXTP data (probable maximum precipitation)
- Station lists (IMGW-PIB and ČHMÚ search) and water levels of IMGW hydro stations with coordinates; the station details of hydro.imgw.pl (gauge zero, catchment area, warning and alarm levels, absolute extremes) in the IMGW-PIB catalog

**Key principle:** the HTTP server writes nothing until the administrator sets its roots (`OBSERWATOR_RAW_ROOT`, `OBSERWATOR_ROOT`) and enables writes; it generates direct links to the IMGW-PIB and ČHMÚ servers and passes current data through live. A writing command (CLI, Python) has two ways of writing and never writes to the working directory: `-o`/`--output-dir` writes plain files only, without metadata; `--root` writes to the versioned store, which has two roots (ADR-017): downloads go to the raw root (`OBSERWATOR_RAW_ROOT`), and the series, catalogs and analyses built from them to the data root (`OBSERWATOR_ROOT`). Without `--root` they go to the roots in the user data directory (`<data_dir>/obserwator-raw` and `<data_dir>/obserwator`; `obserwator config show --json` shows both roots and their sources). A single export file: `--output FILE`.

**Versioned data store** (optional, since 3.0.0):
- two roots, each with its own marker: the raw root keeps the downloaded sources, the data root what is built from them; `series build` and `store catalog` read the raw root and never write it (ADR-017),
- immutable 1:1 versions of IMGW-PIB and ČHMÚ archives with SHA-256 checksums, HTTP headers and the license in a `*.meta.json` sidecar,
- freshness checks without downloading (IMGW-PIB: listing + `HEAD`, ČHMÚ: one listing of the server directory) and an `obserwator-plan/1` plan,
- station series in Parquet, `stations.geojson` station catalogs of both providers, PMAXTP cells, CSV/JSONL export,
- the stations' analyses (characteristic levels and discharges, threshold events, flood and low-flow frequency, regimes, trends, precipitation indices, spells, SPI and more; 87 in all) computed by [Hydrolog](https://github.com/Daldek/Hydrolog) and stored as its answers with the series versions they came from (`obserwator analyses build|list|read|export`, ADR-016); Obserwator computes no number itself,
- the command that downloads a stored version again, reconstructed from its sidecar (`command_for_version`, for the pins of Archiwista projects),
- readable offline from a local disk or a network share, without a database.

---

## Installation

```bash
# Library only (minimal dependencies: httpx, pydantic, pydantic-settings, platformdirs)
pip install obserwator

# With CLI
pip install obserwator[cli]

# With REST API
pip install obserwator[api]

# With the versioned store and Parquet series (pyarrow)
pip install obserwator[store]

# With DataFrame export (PMaXTPData.to_dataframe)
pip install obserwator[pandas]

# With the MCP server for AI agents (obserwator mcp; includes the CLI)
pip install obserwator[mcp]

# With the web GUI (obserwator gui serve needs the CLI too; create_app and serve need only [gui])
pip install "obserwator[cli,gui]"

# Full installation (CLI + API + GUI + MCP + store + pandas)
pip install obserwator[full]

# For developers (from the repository; uv, environment from uv.lock)
git clone https://github.com/Daldek/Obserwator.git
cd Obserwator
uv sync --locked
```

Writing to the versioned store requires a file system with hard links — the same as Kartograf's store (its ADR-036). Linux, macOS and Windows (ext4, APFS, NTFS) and SMB shares that support hard links work; on FAT/exFAT, some NAS and FUSE file systems, and on an SMB share mounted on macOS, `store init` and every write end with the `conflict` error (`details.reason="not_atomic"`). Reading the store does not need hard links. Writing plain files (`--output-dir`, `--output`) does not use hard links and also works on FAT/exFAT and SMB.

---

## Quick start

Full guides to each interface: [docs/USAGE.md](https://github.com/Daldek/Obserwator/blob/main/docs/USAGE.md).

### Python

```python
from obserwator import fetch_pmaxtp

# Fetch data for Warsaw (method: "POT" — the default — or "AMP")
result = fetch_pmaxtp(52.23, 21.01, method="POT")
precip = result.data.get_precipitation(15, 50)
print(f"Precipitation 15 min, p=50%: {precip} mm")  # precipitation [mm] for t=15 min, p=50%
```

### CLI

```bash
obserwator datasets list -k hydro
obserwator datasets files -d hydro/dobowe -y 2023 -m 1
obserwator stations find -k hydro -q wisla --limit 5
obserwator current hydro -s 150160180
obserwator pmaxtp fetch --lat 52.23 --lon 21.01 --method AMP
obserwator datasets download -d hydro/miesieczne -y 2023 -o dane    # plain files in the dane/ directory
obserwator store sync -d pl.imgw.hydro_monthly -y 2023              # archives in the raw root <data_dir>/obserwator-raw
obserwator series build -d pl.imgw.hydro_monthly                    # series in the data root <data_dir>/obserwator
obserwator analyses read -s 149190310 --analysis characteristic.Q   # a stored analysis computed by Hydrolog
obserwator stations find -k hydro -q wisla --limit 5 --json        # one JSON line for scripts and agents
```

Without `--json` stdout is a short summary in the language of `--lang` (`OBSERWATOR_LANG`, `pl` by default); `--json` prints one JSON line — the `obserwator-result/1` envelope — and is what scripts and agents parse. `obserwator commands list` prints all commands of the catalog.

### REST API

```bash
obserwator server --reload  # Swagger UI: http://localhost:8000/docs
curl "http://localhost:8000/api/v1/current/hydro?station=150160180"
curl "http://localhost:8000/api/v1/datasets/files?dataset=hydro/dobowe&years=2023&months=1"
```

### MCP server

`obserwator mcp` (extra `obserwator[mcp]`) is an MCP server on stdio; client configuration (e.g. `mcpServers` in the settings file):

```json
{
  "mcpServers": {
    "obserwator": {
      "command": "obserwator",
      "args": ["mcp"],
      "env": {"OBSERWATOR_ROOT": "/dane/obserwator", "OBSERWATOR_RAW_ROOT": "/dane/obserwator-raw"}
    }
  }
}
```

Read-only by default (writing commands return a plan); `--allow-writes` enables writes, and only in directories given with `--allow-dir` (e.g. `"args": ["mcp", "--allow-writes", "--allow-dir", "/dane/obserwator", "--allow-dir", "/dane/obserwator-raw"]`); a root outside them ends with the `forbidden` error.

### GUI

```bash
pip install "obserwator[cli,gui]"
obserwator gui serve --root /dane/obserwator   # opens http://127.0.0.1:8060/; Ctrl+C stops it
```

The GUI reads the data root and never writes it: the analyses `obserwator analyses build` stored show as they are, and Hydrolog's program computes on request only a person's choices (another period, a distribution, a threshold) and the normal of the climate stripes' reference period. Its page has no sign-in: beyond this computer it runs behind an authenticating proxy, and open to others it follows Nogat's rules for a public GUI (terms, rate limit, logs without addresses, „Zgłoś uwagę”). It counts its use in daily totals only, one line per UTC day in `<data_dir>/obserwator/stats.jsonl` (Nogat DEV-15.11): `visitors` (distinct keyed hashes of address and User-Agent, kept in memory only), `page_views` (HTML pages served), `stations_opened` (station descriptions served, one per station the page opens), `analyses_run` (answers with a result computed on request: an analysis with a person's choices, also when repeated from the server's memory, and the climate stripes; stored results are not counted) and `downloads` (files served). The proxy, the settings, the private API and the public rules: [usage guide](https://github.com/Daldek/Obserwator/blob/main/docs/USAGE.md#gui).

Its admin panel at `admin/` (Nogat DEV-15.13, ADR-020) is Nogat's kit shell with „Zgłoszenia” (the reports of „Zgłoś uwagę”, read, marked and deleted in `<data_dir>/obserwator/feedback.jsonl`), „Statystyki” (the daily totals) and „Stan” (version, uptime, own directory, free disk and three checks: `data_root_marker`, the data root's `obserwator-data.json`; `stored_analyses`, Hydrolog's results stored for every provider with a catalog; `hydrolog_command`, Hydrolog's program for the computations on request). It asks for the key of `OBSERWATOR_ADMIN_API_KEY` or of the file named by `OBSERWATOR_ADMIN_API_KEY_FILE`, read on every request; that key is none of the REST API keys of `obserwator admin`. A deployment protects `/admin`, `/admin/*` and `/api/admin/*` and leaves the rest public.

### Server logs

`obserwator server` and `obserwator gui serve` keep Nogat's logs (DEV-12.4 to DEV-12.9): one JSON record per line (`nogat-log/1`) in `<state_dir>/obserwator/logs/<kind>-YYYY-MM-DD.jsonl` — `access` (one record per answered request: method, path with personal query values dropped, status, bytes, duration and the class of the User-Agent; never the client's address, a header or a body; the page's files, the guide, the regulamin, the borders, the API documentation, `/llms.txt` and `/health` only when answered with 400 or more), `app` (warnings, errors, exceptions) and `lifecycle` (start with the settings, stop, deletion). The servers delete the files after 14 days themselves; standard output and error get only the lifecycle records and errors reduced to their type. `state_dir` defaults to `~/.local/state/nogat` on Linux (`OBSERWATOR_STATE_DIR`, `NOGAT_STATE_DIR`, `state_dir` of `nogat.toml`). Read the logs, with the errors and without the ordinary requests:

```bash
jq -cs 'sort_by(.time)[] | select(.kind != "access" or .status >= 500)' ~/.local/state/nogat/obserwator/logs/*.jsonl
```

(`jq`: `apt install jq`, or its static release binary in `~/.local/bin`.) Use is counted only in the GUI's daily totals above, never from the logs.

---

## AI agents: AGENTS.md, llms.txt and the MCP server

An agent (an editor assistant, a chat application, a script with a language model) learns Obserwator from one source that matches the code:

- [`AGENTS.md`](https://github.com/Daldek/Obserwator/blob/main/AGENTS.md) — the guide: the "check → run → read" rule, the Python/CLI/REST/MCP mapping, the envelope and statuses, error codes, the datasets of both providers with option rules, command tables with effects, typical flows (e.g. "daily precipitation at the Poznań station", a ČHMÚ station) and a "what not to do" list;
- [`llms.txt`](https://github.com/Daldek/Obserwator/blob/main/llms.txt) — a summary following llms.txt v2 with links to the documentation; `GET /llms.txt` serves the same file;
- `obserwator commands guide [--format agents|llms] [--lang en|pl] [--output FILE] [--force]` or `agent_guide()` in Python — both files generated on the fly (English by default, `--lang pl` gives Polish); `GET /api/v1/commands/guide`.

`AGENTS.md` and `llms.txt` are derived from the command catalog, the registries and the templates in `src/obserwator/_data/agents/` — they are not edited by hand (rules for working on the code: `CLAUDE.md`).

Language, command effects and MCP server configuration (stdio and `/mcp`): [usage guide](https://github.com/Daldek/Obserwator/blob/main/docs/USAGE.md#ai-agents-language-command-effects-and-the-mcp-server).

---

## Configuration

A setting comes from the first of: the command-line option, the `OBSERWATOR_<KEY>` variable, the `.env` file, the `NOGAT_<KEY>` variable (shared keys `data_dir`, `cache_dir`, `state_dir`, `lang`), the `[obserwator]` and `[nogat]` sections of the `nogat.toml` file, the default value. The most important variables: `OBSERWATOR_ROOT` (the data root), `OBSERWATOR_RAW_ROOT` (the raw root), `OBSERWATOR_LANG` (`pl` or `en`), `OBSERWATOR_DATA_DIR`, `OBSERWATOR_CACHE_DIR`, `OBSERWATOR_STATE_DIR` (the servers' logs in `<state_dir>/obserwator/logs`), `OBSERWATOR_REFERENCE_DIR`, `OBSERWATOR_MCP_ENABLED`, `OBSERWATOR_HYDROLOG_COMMAND` (Hydrolog's program for the analyses; default `hydrolog` on `PATH`). `obserwator config show --json` prints every key with its value and source.

Full table of variables, a `nogat.toml` example and store backup: [Configuration](https://github.com/Daldek/Obserwator/blob/main/docs/USAGE.md#configuration).

---

## Data sources

Obserwator does not distribute IMGW-PIB or ČHMÚ data, and the server does not store them by default — every download and write is a deliberate decision of the user or administrator (`--output-dir`, `--output`, `--root`, `OBSERWATOR_RAW_ROOT`, `OBSERWATOR_ROOT`; without them the CLI and Python write to the roots in the user data directory). Below is a summary of the sources used.

| Source | Operator | Terms of use |
|--------|----------|---------------------|
| Measurement and observation archive — `danepubliczne.imgw.pl/data` (hydro/meteo, ZIP/CSV) | IMGW-PIB | Free of charge for private (non-profit) purposes; high-value data — for any purpose; business use, websites with advertising and the purposes the terms list (e.g. water management planning, art. 317 of the Water Law) need an agreement with IMGW-PIB; the source line, and for processed data the processed-data line, are mandatory. [Terms](https://danepubliczne.imgw.pl/regulations)
| Real-time API — `danepubliczne.imgw.pl/api/data` (hydro, synop, meteo, warnings) | IMGW-PIB | As above ([terms](https://danepubliczne.imgw.pl/regulations))
| PMAXTP — `klimat.imgw.pl/opady-maksymalne` | IMGW-PIB | Citing IMGW-PIB as the source (data from the `klimat.imgw.pl/opady-maksymalne` page) and citing the monograph of the PMAXTP Project (ed. B. Ozga-Zieliński, IMGW-PIB, Warsaw 2022; monograph: Open Access, CC-BY 4.0); for processed data — a note that the data were processed; use at your own risk. [Terms](https://klimat.imgw.pl/opady-maksymalne/) |
| Station map with coordinates — `hydro-back.imgw.pl/map/stations/hydrologic` (backend of the `hydro.imgw.pl` service) | IMGW-PIB | Terms of the hydro.imgw.pl service (accepted by starting to use it): private use only, the IMGW-PIB source and processed-data lines plus the line naming the service; the water states are operational data, shown as current and never stored. [Terms](https://hydro.imgw.pl/#/regulamin) |
| Station details — `hydro-back.imgw.pl/station/hydro/status` (the station page of `hydro.imgw.pl`; dataset `pl.imgw.hydro_details`) | IMGW-PIB | The same terms of the hydro.imgw.pl service: the IMGW-PIB source and processed-data lines plus the line naming the service on every product with the details (sidecar, catalog, export, GUI station panel). The store keeps only the station reference data (gauge zero and datum, river km, catchment area, year of establishment, province, district, warning and alarm levels, absolute extremes); water states, trends and notices are never stored (ADR-021). [Terms](https://hydro.imgw.pl/#/regulamin) |
| Archives and station metadata — `opendata.chmi.cz` (`hydrology/historical`, `hydrology/now/metadata`, `meteorology/climate/historical_csv`, `meteorology/climate/historical/metadata`, `meteorology/climate/now/metadata`) | ČHMÚ (Český hydrometeorologický ústav) | License [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/): copying, changes and commercial use provided that ČHMÚ is credited as the author, the license is given and changes are indicated ([ČHMÚ terms](https://www.chmi.cz/vylou%C4%8Den%C3%AD-odpov%C4%9Bdnosti)). ČHMÚ does not prescribe a wording; Obserwator writes "Źródło danych: Český hydrometeorologický ústav (ČHMÚ), https://opendata.chmi.cz, licencja CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/)" (data source: …, license CC BY 4.0), and for processed forms adds "Dane ČHMÚ zostały przetworzone" (ČHMÚ data have been processed), which never names the processing (Nogat ECO-071); an older line with the processing in parentheses is read as this one |

Every product of Obserwator with provider data carries the lines these terms require, byte for byte as the Nogat standard quotes them (DEV §20, ADR-012): the envelope of a command (`attribution` and `terms_notice`), the CLI summary, CSV, JSONL and Parquet exports and stored series, catalogs and PMAXTP cells, `ATTRIBUTION.txt` of a plain download and every view and file of the GUI; the texts live in `obserwator.messages.legal` and `obserwator.attribution` composes them. Whoever publishes results made with the data shows the lines with them.

### Reference data (station lists, coordinates, format descriptions)

The repository **does not contain** IMGW data. Download the reference files used by the tools (station lists, coordinates, format descriptions) once — after installing the package (`pip install -e .`), without any arguments:

```bash
python -m obserwator.reference_data
```

The downloaded files go to the reference data directory (`OBSERWATOR_REFERENCE_DIR`, by default `<cache_dir>/obserwator/reference`, e.g. `~/.cache/nogat/obserwator/reference`; see "Configuration") and come from IMGW-PIB — they are subject to the IMGW-PIB terms (not the project's MIT license).

The only geographic datasets bundled with the package are the border outlines of Poland `src/obserwator/_data/poland_border_wgs84.geojson` and Czechia `src/obserwator/_data/czechia_border_wgs84.geojson` (position checks in station catalogs) from the state border of PRG (GUGiK) and of RÚIAN (ČÚZK, CC BY 4.0), simplified to 50 m by `scripts/build_borders.py` (ADR-018); products checked against them carry the lines G and Z of Nogat DEV §20. They are not IMGW-PIB or ČHMÚ data.

---

## Documentation

Usage guide ([docs/USAGE.md](https://github.com/Daldek/Obserwator/blob/main/docs/USAGE.md)), sections:

- [Using as a Python library](https://github.com/Daldek/Obserwator/blob/main/docs/USAGE.md#using-as-a-python-library)
- [Quick start (CLI)](https://github.com/Daldek/Obserwator/blob/main/docs/USAGE.md#quick-start-cli)
- [REST API](https://github.com/Daldek/Obserwator/blob/main/docs/USAGE.md#rest-api)
- [GUI](https://github.com/Daldek/Obserwator/blob/main/docs/USAGE.md#gui)
- [AI agents: language, command effects and the MCP server](https://github.com/Daldek/Obserwator/blob/main/docs/USAGE.md#ai-agents-language-command-effects-and-the-mcp-server)
- [Source data structure](https://github.com/Daldek/Obserwator/blob/main/docs/USAGE.md#source-data-structure)
- [Docker](https://github.com/Daldek/Obserwator/blob/main/docs/USAGE.md#docker)
- [Server logs](https://github.com/Daldek/Obserwator/blob/main/docs/USAGE.md#server-logs)
- [Configuration](https://github.com/Daldek/Obserwator/blob/main/docs/USAGE.md#configuration)
- [Versioned store (optional)](https://github.com/Daldek/Obserwator/blob/main/docs/USAGE.md#versioned-store-optional)
- [Changes in version 3.0.0](https://github.com/Daldek/Obserwator/blob/main/docs/USAGE.md#changes-in-version-300)

Other documents:

- [`CLAUDE.md`](https://github.com/Daldek/Obserwator/blob/main/CLAUDE.md) - Instructions for Claude Code
- [`docs/CODEBASE.md`](https://github.com/Daldek/Obserwator/blob/main/docs/CODEBASE.md) - Code and module reference (public API, command catalog, data formats; [project structure](https://github.com/Daldek/Obserwator/blob/main/docs/CODEBASE.md#project-structure-from-readme))
- [`docs/TESTING.md`](https://github.com/Daldek/Obserwator/blob/main/docs/TESTING.md) - Tests: layout, markers, running ([test instructions from the README](https://github.com/Daldek/Obserwator/blob/main/docs/TESTING.md#tests-from-readme))
- [`docs/CHANGELOG.md`](https://github.com/Daldek/Obserwator/blob/main/docs/CHANGELOG.md) - Change history (including BREAKING 3.0.0)
- [`docs/DECISIONS.md`](https://github.com/Daldek/Obserwator/blob/main/docs/DECISIONS.md) - Decision log (ADR-001: versioned store, ADR-002: one command catalog, ADR-003: ČHMÚ provider, ADR-004: AI agent support, ADR-005: user environment, ADR-006: message catalog, ADR-007: writing data, ADR-008: projects moved to Archiwista, ADR-009: the tool is called Obserwator, ADR-013: web GUI, ADR-016: stored analyses computed by Hydrolog, ADR-017: the data root, ADR-018: state borders from PRG and RÚIAN, ADR-019: Nogat server logs, ADR-020: the GUI's admin panel, ADR-021: station details of hydro.imgw.pl)
- [`docs/ARCHITECTURE.md`](https://github.com/Daldek/Obserwator/blob/main/docs/ARCHITECTURE.md) - System architecture
- [`docs/PRD.md`](https://github.com/Daldek/Obserwator/blob/main/docs/PRD.md) - Product requirements
- [`docs/PROGRESS.md`](https://github.com/Daldek/Obserwator/blob/main/docs/PROGRESS.md) - Current status, next steps, open questions
- [`docs/HISTORY.md`](https://github.com/Daldek/Obserwator/blob/main/docs/HISTORY.md) - Release history and closed work
- [`AGENTS.md`](https://github.com/Daldek/Obserwator/blob/main/AGENTS.md), [`llms.txt`](https://github.com/Daldek/Obserwator/blob/main/llms.txt) - Guide for AI agents (generated: `obserwator commands guide`)

---

## Issues and support

Report issues in the [Issues](https://github.com/Daldek/Obserwator/issues) section.

---

## License

The project is released under the MIT license. Details in the [`LICENSE`](https://github.com/Daldek/Obserwator/blob/main/LICENSE) file.

---

## Author

- [Piotr de Bever](https://www.linkedin.com/in/piotr-de-bever/)
