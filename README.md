# Obserwator: hydrological and meteorological data of Poland and Czechia for hydrology, GIS and AI agents

Obserwator downloads the public hydrological and meteorological data of IMGW-PIB (Poland) and ČHMÚ (Czechia) and the PMAXTP maximum precipitation of IMGW-PIB to plain files or a versioned store, and builds station series, station catalogs and Hydrolog's station analyses from them. Python library, CLI, REST API, MCP server and web GUI.

## When to use

- Download the archives of IMGW-PIB's public data service (daily, monthly and semi-annual hydrological data and the monthly hydrological telemetry; climate, precipitation and synoptic meteorological data) and ČHMÚ's daily and validated hourly station data and groundwater readings, as plain files or as immutable versions with SHA-256, HTTP headers and licence in a sidecar; the registry has 49 datasets, 33 of IMGW-PIB and 16 of ČHMÚ, captures of current data and hourly series among them.
- Read current water levels, meteorological and synoptic measurements and warnings of IMGW-PIB, every answer kept as it came and sealed into the raw root day by day (captures, `obserwator current poll` hourly), and find IMGW-PIB and ČHMÚ stations by name, river or code.
- Get the PMAXTP maximum precipitation (quantiles, confidence bounds, errors) of a point in Poland.
- Build daily, weekly and hourly station series (Parquet) and station catalogs (GeoJSON) offline from the downloaded archives and captures, and export them as CSV, JSON, JSONL or Parquet with the providers' attribution lines.
- Store the analyses Hydrolog computes for every station (87: characteristic levels and discharges, frequencies, regimes, trends, precipitation indices) next to the series, and browse stations, series, analyses and a station's hourly readings on a map in the web GUI.
- Let an AI agent call the same 36 commands through MCP, the CLI, REST or Python, with one result envelope and stable error codes.

## When not to use

- Hydrological computation (frequency analysis, hydrographs, statistics): [Hydrolog](https://github.com/Daldek/Hydrolog). Obserwator stores Hydrolog's answers and computes no number itself.
- Elevation models (DEM, Polish NMT), land cover, soils and other spatial data: [Kartograf](https://github.com/Daldek/Kartograf).
- Projects that pin store versions, browsing a store in a browser: [Archiwista](https://github.com/Daldek/Archiwista) (ADR-008).
- Watershed delineation and design hydrographs in a web application: [Hydrograf](https://github.com/Daldek/Hydrograf).
- Forecasts: Obserwator reads published observations only; use the forecasts of IMGW-PIB (https://meteo.imgw.pl) and ČHMÚ (https://www.chmi.cz).
- ČHMÚ's current meteorological measurements and the current readings of its groundwater objects: Obserwator reads ČHMÚ's current hydrological files and only the station metadata of the rest; read https://opendata.chmi.cz directly.
- Data of other countries: use the provider of that country.

## Install

Obserwator is not on PyPI yet (the name `imgwtools` there holds the releases up to 2.1.1); install it from Git (Python 3.12 or newer):

```bash
uv tool install "obserwator[cli] @ git+https://github.com/Daldek/Obserwator.git@v3.2.0"
uv add "obserwator @ git+https://github.com/Daldek/Obserwator.git@v3.2.0"
uvx --from "obserwator[mcp] @ git+https://github.com/Daldek/Obserwator.git@v3.2.0" obserwator mcp
```

The lines install the CLI of the release 3.2.0, add the library to a project pinned to its tag (Nogat REL-5.1) and start the MCP server once. `pip install "<requirement>"` takes the same requirement strings. The library alone needs `httpx`, `pydantic`, `pydantic-settings` and `platformdirs`; the extras add the rest:

| Extra | Adds |
|---|---|
| `cli` | the command `obserwator` (Typer, Rich) |
| `api` | the REST server `obserwator server` (FastAPI, uvicorn) |
| `store` | Parquet series of the versioned store (pyarrow) |
| `mcp` | the MCP server `obserwator mcp` (includes `cli`; SDK `mcp>=2.3,<3`) |
| `gui` | the web GUI (`obserwator gui serve` with `cli`; includes `store`) |
| `pandas` | `PMaXTPData.to_dataframe` |
| `full` | all of the above |

Writing to the versioned store needs a file system with hard links, as Kartograf's store (its ADR-036): ext4, APFS, NTFS and SMB shares that support them work; on FAT/exFAT, some NAS and FUSE file systems, and on an SMB share mounted on macOS, `store init` and every write end with `conflict` (`details.reason="not_atomic"`). Reading the store and writing plain files (`--output-dir`, `--output`) need no hard links.

Development setup: `git clone https://github.com/Daldek/Obserwator.git && cd Obserwator && uv sync --locked`.

## Quick start

Every command takes `--json`: stdout is then one line, the `obserwator-result/1` envelope, and an error is an `obserwator-error/1` document on the last line of stderr. Without it the output is a short summary in the language of `--lang` (`OBSERWATOR_LANG`, `pl` by default). Guides to every interface: [USAGE.md](https://github.com/Daldek/Obserwator/blob/main/docs/USAGE.md).

### CLI

```bash
obserwator datasets files -d hydro/dobowe -y 2023 -m 1 --json
```

Offline: the URLs of a dataset's files, nothing downloaded. The envelope names the command and holds its result:

```json
{
  "schema": "obserwator-result/1",
  "tool": "obserwator",
  "version": "3.2.0",
  "command": "datasets files",
  "check": false,
  "status": "ok",
  "result": [
    {
      "schema": "obserwator-archive-file/1",
      "dataset": "pl.imgw.hydro_daily",
      "server_path": "dane_hydrologiczne/dobowe/2023/codz_2023.zip",
      "url": "https://danepubliczne.imgw.pl/data/dane_pomiarowo_obserwacyjne/dane_hydrologiczne/dobowe/2023/codz_2023.zip",
      "year": 2023,
      "month": null,
      "param": null,
      "year_type": "hydrological",
      "period_start": "2022-11-01",
      "period_end": "2023-10-31",
      "station_code": null
    }
  ],
  "notices": [],
  "page": {"total": 1, "next_cursor": null, "truncated": false}
}
```

Network commands; a result with provider data also has `attribution` and `terms_notice`:

```bash
obserwator stations find -k hydro -q wisla --limit 5 --json        # obserwator-station/1 entries
obserwator pmaxtp fetch --lat 52.23 --lon 21.01 --method POT --json # obserwator-pmaxtp-result/1
obserwator datasets download -d hydro/miesieczne -y 2023 -o dane    # plain files in dane/ with ATTRIBUTION.txt
obserwator store sync -d pl.imgw.hydro_monthly -y 2023 --check      # plan only: what the raw root lacks
obserwator store sync -d pl.imgw.hydro_monthly -y 2023              # archives into the raw root
obserwator series build -d pl.imgw.hydro_monthly                    # Parquet series into the data root
obserwator analyses read -s 149190310 --analysis characteristic.Q   # a stored analysis computed by Hydrolog
```

Where data goes: `-o`/`--output-dir` writes plain files only; `--root` writes the versioned store, which has two roots (ADR-017): downloads go to the raw root (`OBSERWATOR_RAW_ROOT`, default `<data_dir>/obserwator-raw`), the series, catalogs and analyses built from them to the data root (`OBSERWATOR_ROOT`, default `<data_dir>/obserwator`). Nothing is written to the working directory, and `--check` plans without writing.

### Python

```python
from obserwator import fetch_pmaxtp

result = fetch_pmaxtp(52.23, 21.01, method="POT")  # method "POT" (default) or "AMP"
print(result.data.get_precipitation(15, 50))  # precipitation [mm] for t = 15 min, p = 50 %
```

`fetch_pmaxtp` returns a `PMaXTPResult`; the CLI envelope's `result` is the same document. Every catalog command is a public function with the same options as keyword arguments (`run_command`, `check_command` and `command_schema` take a command by name); failures raise `ObserwatorError` subclasses with `code`, `detail`, `hint` and `details`.

### REST API

```bash
obserwator server   # extra api; Swagger UI at http://localhost:8000/docs
curl "http://localhost:8000/api/v1/datasets/files?dataset=hydro/dobowe&years=2023&months=1"
```

The body is the same `obserwator-result/1` envelope; an error is `application/problem+json` with the registry code.

### MCP

The server lists the catalog commands as tools. A tool is called with the options as arguments and answers with the envelope as `structuredContent`:

```json
{"name": "obserwator_datasets_files", "arguments": {"dataset": "pl.imgw.hydro_daily", "years": [2023], "months": [1]}}
```

### Web GUI

```bash
obserwator gui serve --root /dane/obserwator   # extras cli and gui; opens http://127.0.0.1:8060/
```

The GUI reads the data root and never writes it. Running it behind an authenticating proxy, a public deployment and its admin panel: [USAGE.md "GUI"](https://github.com/Daldek/Obserwator/blob/main/docs/USAGE.md#gui).

## Capabilities

The CLI command is `obserwator <group> <name>`, the MCP tool `obserwator_<group>_<name>` and the REST route `/api/v1/<group>/<name>` (every command but `datasets download` and `store init`).

| Task | CLI command | Python function | Data source and licence |
|---|---|---|---|
| Datasets and providers of the registry (offline) | `datasets list`, `datasets providers` | `datasets`, `providers` | none |
| URLs of a dataset's files (offline) | `datasets files` | `archive_files` | IMGW-PIB, ČHMÚ |
| Plain download of a dataset | `datasets download` | `download_archives` | IMGW-PIB public data terms; ČHMÚ CC BY 4.0 |
| Find stations; export the catalogs | `stations find`, `stations export` | `find_stations`, `export_stations` | IMGW-PIB, ČHMÚ |
| Current measurements and warnings of IMGW-PIB | `current hydro`, `current meteo`, `current synop`, `current warnings`, `current hydro-states` | `fetch_hydro_current`, `fetch_meteo_current`, `fetch_synop`, `fetch_warnings`, `fetch_hydro_states` | IMGW-PIB public data terms; hydro.imgw.pl terms for `hydro-states` |
| PMAXTP of a point; its cell in the raw root | `pmaxtp fetch`, `pmaxtp url`, `pmaxtp check`, `pmaxtp sync`, `pmaxtp read` | `fetch_pmaxtp`, `build_pmaxtp_url`, `check_pmaxtp`, `sync_pmaxtp`, `read_pmaxtp` | IMGW-PIB klimat.imgw.pl terms |
| Versioned archives in the raw root | `store init`, `store info`, `store scan`, `store check`, `store sync`, `store export` | `init_store`, `store_info`, `iter_store`, `check_store`, `sync_store`, `export_archive` | IMGW-PIB, ČHMÚ |
| Station catalog of a provider (offline) | `store catalog` | `build_catalog` | IMGW-PIB, ČHMÚ, hydro.imgw.pl; borders PRG (GUGiK) and RÚIAN (ČÚZK) |
| Station series (offline) | `series build`, `series select`, `series read`, `series summary`, `series export` | `build_series`, `select_series`, `read_series`, `summarize_series`, `export_series` | the archives of the raw root |
| Stations' analyses computed by Hydrolog | `analyses build`, `analyses list`, `analyses read`, `analyses export` | `build_analyses`, `list_analyses`, `read_analysis`, `export_analyses` | the series of the data root |
| The catalog itself | `commands list`, `commands schema`, `commands guide` | `list_commands`, `command_schema`, `agent_guide` | none |

The full list with effects is `obserwator commands list --json`; Python names are in `obserwator.__all__`.

## For AI agents

- [llms.txt](https://raw.githubusercontent.com/Daldek/Obserwator/main/llms.txt) and [AGENTS.md](https://raw.githubusercontent.com/Daldek/Obserwator/main/AGENTS.md) are generated from the command catalog; `obserwator commands guide --format agents|llms` prints them (`GET /llms.txt` on the REST server).
- Discover the commands with `obserwator commands list --json` and one command with `obserwator commands schema --command "store sync" --json` (options, allowed values, rules, examples, errors); in MCP `obserwator_commands_list` and `obserwator_commands_schema`.
- Every command answers with `obserwator-result/1` (`status` `ok`, `partial` or `failed`, `result`, `items`, `notices`); an error is `obserwator-error/1`. Machine output is English; `--lang pl` or `Accept-Language: pl` gives Polish texts.
- Writing commands take `--check` (`check: true` in MCP), which returns an `obserwator-plan/1` plan and writes nothing; the MCP server only plans until it is started with `--allow-writes`.

## MCP server

`obserwator mcp` serves the 36 catalog commands as tools named `obserwator_<group>_<name>` over stdio. Each client below starts it as in the Install section:

```bash
claude mcp add obserwator -- uvx --from "obserwator[mcp] @ git+https://github.com/Daldek/Obserwator.git@v3.2.0" obserwator mcp
codex mcp add obserwator -- uvx --from "obserwator[mcp] @ git+https://github.com/Daldek/Obserwator.git@v3.2.0" obserwator mcp
```

Cursor reads `.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "obserwator": {
      "command": "uvx",
      "args": ["--from", "obserwator[mcp] @ git+https://github.com/Daldek/Obserwator.git@v3.2.0", "obserwator", "mcp"]
    }
  }
}
```

VS Code reads `.vscode/mcp.json`, whose key is `servers`:

```json
{
  "servers": {
    "obserwator": {
      "command": "uvx",
      "args": ["--from", "obserwator[mcp] @ git+https://github.com/Daldek/Obserwator.git@v3.2.0", "obserwator", "mcp"]
    }
  }
}
```

| Option | Meaning |
|---|---|
| `--allow-writes` | writing tools write (`check: false`); without it they return a plan |
| `--allow-dir DIR` | directory the server may read and write (repeatable); a root outside them is `forbidden`, and without one a writing tool only plans |

The roots come from `OBSERWATOR_RAW_ROOT` and `OBSERWATOR_ROOT` in the server's environment. The REST server also serves `/mcp` (Streamable HTTP) with `OBSERWATOR_MCP_ENABLED=true`, read and plan only. Details: [USAGE.md "MCP server"](https://github.com/Daldek/Obserwator/blob/main/docs/USAGE.md#mcp-server).

## Related tools

- [Hydrolog](https://github.com/Daldek/Hydrolog) computes the stations' analyses that `analyses build` stores, reads the CSV of `series export` and calls `fetch_pmaxtp`.
- [Hydrograf](https://github.com/Daldek/Hydrograf) calls `fetch_pmaxtp` for the design precipitation of its watersheds.
- [Archiwista](https://github.com/Daldek/Archiwista) reads Obserwator's stores through the public read API and keeps the projects that pin store versions (`command_for_version`).
- [Retman](https://github.com/Daldek/Retman) is a Polish natural-language layer over the command catalogs of the tools.
- [Kartograf](https://github.com/Daldek/Kartograf) downloads the spatial data that Obserwator does not; its store follows the same design.
- External: the web pages of IMGW-PIB (https://danepubliczne.imgw.pl, https://hydro.imgw.pl) and ČHMÚ (https://opendata.chmi.cz) for one-off manual downloads; the R package [`climate`](https://cran.r-project.org/package=climate) downloads IMGW-PIB data in R.

## Errors and exit codes

An error is an `obserwator-error/1` document with `code`, `title`, `message`, `hint`, `details` and `exit_code`; the codes come from the [shared registry](https://github.com/Daldek/Nogat/blob/main/standards/ERROR_REGISTRY.md) (`ERROR_CODES` in Python). The outcomes `partial` (10) and `failed` (11) are results, not errors: read `items[].status` and `error_code`. The most common errors:

| Code | Exit | What to do |
|---|---|---|
| `validation_error` | 2 | an option is wrong or missing: fix `details.option` as `hint` says |
| `conflict` | 4 | the target is taken (`details.reason`, for example `output_exists`): `--force` replaces plain files |
| `source_unavailable` | 5 | network, HTTP or timeout at IMGW-PIB or ČHMÚ: retry the same call later |
| `store_unavailable` | 8 | no root, no marker or a root of the other kind (`details.reason`: `not_configured`, `no_marker`, `wrong_root`): run `store init` or pass the right `--root` |
| `missing_dependency` | 6 | an extra is not installed: install the extra the hint names |
| `forbidden` | 12 | MCP only: a root outside `--allow-dir` |

## Data and licensing

Obserwator does not distribute IMGW-PIB or ČHMÚ data; every download and write is a decision of the user or the administrator.

| Source | Data | Terms |
|---|---|---|
| IMGW-PIB, `danepubliczne.imgw.pl` | archives of measurements and observations (ZIP/CSV), current data API | free for private (non-profit) purposes, high-value data for any purpose; business use, websites with advertising and the purposes the terms list need an agreement with IMGW-PIB; the source line and, for processed data, the processed-data line are mandatory ([terms](https://danepubliczne.imgw.pl/regulations)) |
| IMGW-PIB, `klimat.imgw.pl/opady-maksymalne` | PMAXTP | cite IMGW-PIB and the monograph of the PMAXTP project (ed. B. Ozga-Zieliński, IMGW-PIB, Warsaw 2022, CC BY 4.0); mark processed data ([terms](https://klimat.imgw.pl/opady-maksymalne/)) |
| IMGW-PIB, `hydro-back.imgw.pl` (backend of `hydro.imgw.pl`) | station map with coordinates, water states, station details (`pl.imgw.hydro_details`), meteorological stations' coordinates and elevation (`pl.imgw.meteo_details`) | private use only; the source and processed-data lines plus the line naming the service; water states are shown as current, and every answer is also kept as a capture, which a server serves only when its operator sets it `public` in `[obserwator.capture]` (ADR-030; `private` by default) ([terms](https://hydro.imgw.pl/#/regulamin)) |
| ČHMÚ, `opendata.chmi.cz` | daily hydrological and meteorological archives, station metadata | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/): credit ČHMÚ, give the licence, mark changes ([terms](https://www.chmi.cz/vylou%C4%8Den%C3%AD-odpov%C4%9Bdnosti)) |
| GUGiK (PRG), ČÚZK (RÚIAN, CC BY 4.0) | the state borders bundled in `src/obserwator/_data/` for position checks (ADR-018) | the lines G and Z of Nogat DEV §20 |

Every product with provider data carries the lines these terms require, as the Nogat standard quotes them (DEV §20, ADR-012): the envelope (`attribution`, `terms_notice`), the CLI summary, CSV, JSONL and Parquet exports, stored series, catalogs and PMAXTP cells, `ATTRIBUTION.txt` of a plain download and every view and file of the GUI. Whoever publishes results made with the data shows the lines with them.

Data is written only where the user says: `--output-dir` (plain files), `--root`, or the default raw and data roots under `<data_dir>` (`~/.local/share/nogat` on Linux); a server writes only to its configured `OBSERWATOR_RAW_ROOT` and `OBSERWATOR_ROOT`. The IMGW-PIB reference files (station lists, coordinates, format descriptions) are downloaded once with `python -m obserwator.reference_data` into `OBSERWATOR_REFERENCE_DIR` (default `<cache_dir>/obserwator/reference`); they are IMGW-PIB data under its terms, not under the project's MIT licence. Settings, their precedence (`OBSERWATOR_<KEY>`, `.env`, `NOGAT_<KEY>`, `nogat.toml`) and store backup: [USAGE.md "Configuration"](https://github.com/Daldek/Obserwator/blob/main/docs/USAGE.md#configuration); `obserwator config show --json` lists every setting with its source.

**What cannot be downloaded again, and backups (DEV-18.5).** The raw root holds archive versions that IMGW-PIB or ČHMÚ have since removed and the captures of operational data, which hydro.imgw.pl keeps for about six weeks only (ADR-030); losing it loses them. Copy a root only with hard links kept (`rsync -aH`; on Windows a tool that keeps hard links, not Explorer or `robocopy`) or through `store export`/`series export`. A deployment runs `deploy/obserwator-backup.sh` with its timer: weekly snapshots of both roots linked to the one before, a monthly full copy with a restore test, 8 and 6 kept, a free-space guard ([USAGE.md "Backups"](https://github.com/Daldek/Obserwator/blob/main/docs/USAGE.md#backups)); the night, telemetry and hourly timers are in [USAGE.md "Timers"](https://github.com/Daldek/Obserwator/blob/main/docs/USAGE.md#timers).

## Documentation

| File | Content |
|---|---|
| [USAGE.md](https://github.com/Daldek/Obserwator/blob/main/docs/USAGE.md) | task-oriented guide to the library, the CLI, REST, the GUI and the MCP server; configuration, the versioned store, Docker, server logs |
| [ARCHITECTURE.md](https://github.com/Daldek/Obserwator/blob/main/docs/ARCHITECTURE.md) | layers, store layout, data flow, CI/CD |
| [CODEBASE.md](https://github.com/Daldek/Obserwator/blob/main/docs/CODEBASE.md) | public API, command catalog, option and error tables, data formats |
| [DECISIONS.md](https://github.com/Daldek/Obserwator/blob/main/docs/DECISIONS.md) | architecture decision records ADR-001 to ADR-032 |
| [PRD.md](https://github.com/Daldek/Obserwator/blob/main/docs/PRD.md) | product requirements and scope |
| [CHANGELOG.md](https://github.com/Daldek/Obserwator/blob/main/docs/CHANGELOG.md) | changes per release, including the breaking changes and the migration from IMGWTools 2.1.1 |

## Development

Read [CLAUDE.md](https://github.com/Daldek/Obserwator/blob/main/CLAUDE.md) first: rules, code map and documentation map. `scripts/gate.sh` runs the whole gate (ruff, mypy, offline tests with coverage, commit checks); it must pass before a commit. Tests: [TESTING.md](https://github.com/Daldek/Obserwator/blob/main/docs/TESTING.md).

## Status, licence, author

Beta (`Development Status :: 4 - Beta`); the version is `obserwator version`, and the changes that are not released yet are in the CHANGELOG under `[Unreleased]`. Until release 2.1.1 the tool was called IMGWTools (`pip install imgwtools`, command `imgw`); since 3.0.0 it is Obserwator ([ADR-009](https://github.com/Daldek/Obserwator/blob/main/docs/DECISIONS.md#adr-009-the-tool-is-called-obserwator)). Issues: [GitHub](https://github.com/Daldek/Obserwator/issues). Licence: MIT ([LICENSE](https://github.com/Daldek/Obserwator/blob/main/LICENSE)). Author: [Piotr de Bever](https://www.linkedin.com/in/piotr-de-bever/).
