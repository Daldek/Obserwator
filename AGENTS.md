# Obserwator — guide for agents (version 3.3.0.dev0)

> Generated from the command catalog: `obserwator commands guide --format agents`. Do not edit by hand.

## What Obserwator is

Obserwator is a Python library, the `obserwator` CLI, a REST API and an MCP server for public hydrological and meteorological data. Archives go into a versioned raw root (immutable versions identified by SHA-256) or plain files; series, station catalogs and analyses are built from it into a data root and read offline.

Use it for archive and current data of the providers' stations, reproducible local copies and PMAXTP maximum precipitation. Not supported: forecasts, ČHMÚ's climate `now` and `recent`, PMAXTP outside Poland. Install: `pip install obserwator[cli]` (`[mcp]` adds the MCP server, `[store]` the Parquet series).

- `IMGW` (IMGW-PIB) — Poland: keys `pl.imgw.*`, station code `^[0-9]{9}$`, license [IMGW-PIB](https://danepubliczne.imgw.pl/regulations)
- `CHMU` (ČHMÚ) — Czechia: keys `cz.chmu.*`, station code `^0-[0-9]{1,5}-[0-9]{1,5}-[0-9A-Z]{1,16}$`, license [CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
- `GDANSKIEWODY` (Gdańskie Wody) — Poland: keys `pl.gdanskiewody.*`, station code `^GDANSKIEWODY-[1-9][0-9]{0,2}$`, license [gdanskiewody-terms-unknown](https://pomiary.gdanskiewody.pl/account/signup), API key from `OBSERWATOR_GDANSKIE_WODY_API_KEY`, off by default (servers, `stations find`), draft attribution lines
- `PIG` (PIG-PIB) — Poland: keys `pl.pig.*`, station code `^[1-9][0-9]{0,5}$`, license [CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)

## Rules: check → run → read

1. **Learn the commands:** `obserwator commands list --json`, then `obserwator commands schema --command … --json` (REST `GET /api/v1/commands/list`, `/schema`; MCP `obserwator_commands_list`, `obserwator_commands_schema`): options in `options`, other rules in `rules`, effects in `effects` (`writes`, `network`, `idempotent`).
2. **Check without writing:** `--check` (CLI), `?check=true` (REST, POST), `check: true` (MCP; the default of writing commands), `check_command()` (Python) → an `obserwator-plan/1` plan, nothing written or downloaded. `store check` is a check itself. Ask the user about a large plan.
3. **Run:** without `check`; read the `status` of the envelope, not only the exit code.
4. **Read offline:** `store info`, `store scan`, `series summary`, `series read` (`limit`/`cursor`), `pmaxtp read`.
5. **Decide by codes:** `code`, `status`, `items[].status`, `error_code`; `message` is for humans, `hint` names the option or command that fixes the error.

## Interfaces

| Interface | Result | Error |
|---|---|---|
| Python | `CommandResult` (`to_json()`) | `ObserwatorError` (`code`, `detail`, `hint`, `details`); `obserwator.error_report.error_report(exc).to_dict()` = the error document |
| CLI `obserwator` | `--json`: one-line JSON envelope on stdout (without it a summary for a person) | last stderr line: error document `obserwator-error/1`; exit code |
| REST `/api/v1` | 200 + envelope, also for `partial` and `failed` | `application/problem+json` (with `hint`) |
| MCP | `structuredContent` = envelope | `isError: true` + error document `obserwator-error/1` |

One command in every interface: CLI `obserwator <group> <command> --option value --json` (flag: `--` + the option name, `-` for `_`); Python `run_command("<group> <command>", options={...})`; REST `/api/v1/<group>/<command>` (GET: query parameters, POST: JSON body); MCP tool `obserwator_<group>_<command>`.

- **REST:** the server sets the roots (`OBSERWATOR_ROOT`, `OBSERWATOR_RAW_ROOT`); no local options; writing (POST without `?check=true`) must be enabled on the server and needs `X-API-Key`.
- **MCP:** `obserwator mcp` (stdio): writing commands only plan (`check` fixed to `true`) until the user allows writes (`--allow-writes`). `/mcp` of the REST server (`OBSERWATOR_MCP_ENABLED=true`) only reads and plans.
- **Language:** machine output is English; Polish on request: `--lang pl` (`commands list|schema|guide`, else the CLI summary without `--json`), `lang: "pl"` (MCP), `Accept-Language: pl` (REST).

## Envelope, statuses and errors

A command returns the envelope `obserwator-result/1` `{schema, tool, version, command, check, status, result, attribution, terms_notice, notices}`: `result` is a document with its own `schema` (`obserwator-<kind>/1`), a list of them or null; `attribution` and `terms_notice` come with provider data; `notices` are `{level, code, message}`. A list command's `result` is the list, with the envelope's `page` `{total, next_cursor, truncated}`: while `truncated`, pass `next_cursor` as `cursor`. A stream without `output` gives only data lines: on the CLI's stdout, as a REST attachment (headers `X-Obserwator-Status`, `X-Obserwator-Notices`).

| Status | CLI exit code | Meaning |
|---|---|---|
| `ok` | 0 | no failures |
| `partial` | 10 | some items failed — read `items[].status`, `error_code`; the others are done |
| `failed` | 11 | no item succeeded (in a plan: `check_failed`); the envelope is complete |
| `cancelled` | 130 | cancelled (Ctrl+C, a cancelled request); a partial `result` or `null` |

An error has a code from a closed registry, the same in every interface; `details.option` names the wrong option. Codes (CLI exit code/HTTP status; `—`: never): `validation_error` (2/400), `not_found` (3/404), `conflict` (4/409), `source_unavailable` (5/502), `missing_dependency` (6/503), `data_error` (7/500), `store_unavailable` (8/503), `io_error` (9/500), `cancelled` (130/—), `forbidden` (12/403), `no_data` (14/404), `unsupported` (15/422), `method_not_allowed` (—/405), `internal_error` (1/500).

## Datasets

A dataset key reads `<country>.<provider>.<dataset>`; a slug (`imgw_hydro_daily`) and a legacy alias (`hydro/dobowe`) are accepted on input only. Datasets of the store:

| Key | Variables | First year |
|---|---|---|
| `pl.imgw.hydro_daily` | `H, Q, T` | 1951 |
| `pl.imgw.hydro_monthly` | `{H,Q,T}_{min,mean,max}` | 1951 |
| `pl.imgw.hydro_semiannual` | `{H,Q,T}_{min,mean,max}` | 1951 |
| `pl.imgw.meteo_climate_daily` | `Tmax, Tmin, Tmean, Tground, P, snow_cover` | 1951 |
| `pl.imgw.meteo_precip_daily` | `P, snow_cover, fresh_snow` | 1950 |
| `pl.imgw.meteo_synop_daily` | `Tmax, Tmin, Tmean`, … (37) | 1966 |
| `pl.imgw.pmaxtp` | `ks, sg, rb` | — |
| `pl.imgw.hydro_telemetry` | `H, Q, T` | 2008 |
| `pl.imgw.hydro_subdaily` | `H, Q, T` | 2008 |
| `cz.chmu.hydro_daily` | `H, Q, T` | 1887 |
| `cz.chmu.meteo_daily` | `P, Tmean, Tmax, Tmin, snow_cover, fresh_snow` | — |
| `cz.chmu.groundwater_daily` | `H_asl, spring_yield, T` | 1960 |
| `cz.chmu.groundwater_weekly` | `H_asl, spring_yield, T` | 1933 |
| `cz.chmu.groundwater_recent` | `H_asl, spring_yield` | 2025 |
| `cz.chmu.groundwater_characteristic` | — | — |
| `cz.chmu.hydro_hourly` | `H, Q` | 1905 |
| `cz.chmu.hydro_subdaily` | `H, Q, T` | 1905 |
| `pl.gdanskiewody.measurements` | `H_asl, Q, T`, … (10) | 2005 |
| `pl.gdanskiewody.hydro_hourly` | `H_asl, Q, T` | 2005 |
| `pl.gdanskiewody.meteo_hourly` | `P, Tair, wind_speed`, … (7) | 2005 |
| `pl.gdanskiewody.hydro_daily` | `H_asl, Q, T` | 2005 |
| `pl.gdanskiewody.meteo_daily` | `P, Tmean, wind_speed, pressure, humidity, irradiance` | 2005 |
| `pl.pig.groundwater_readings` | `depth_to_water, H_asl, spring_yield` | 1965 |
| `pl.pig.groundwater_chemistry` | — | — |
| `pl.pig.groundwater_watchlist` | — | — |
| `pl.pig.groundwater_subdaily` | `depth_to_water, H_asl` | 2015 |

Station sources (`*_stations`, `*_now`, `*.station_list`, `pl.imgw.*_details`): `store sync` alone.

Captures (`pl.*_{current,operational}`, `cz.chmu.hydro_{current,recent}`, unverified, one version a UTC day): `store sync` alone (`start`/`end`: closed UTC days); `pace_until` first harvests them (default yesterday) of `pl.imgw.hydro_operational` or `cz.chmu.hydro_recent`, of `pl.pig.groundwater_operational` from its watermark.

Download only (`datasets download`): `pl.imgw.{hydro_phenomena,meteo_climate_monthly,meteo_precip_monthly,meteo_synop_monthly,meteo_climate_terms,meteo_synop_terms,warnings_hydro_archive,warnings_meteo_archive,actinometric}`.

- `stations`: WIGOS (required for `cz.chmu.*`), 9 digits (`pl.imgw.meteo_synop_*`) or `GDANSKIEWODY-<no>` of the stored `pl.gdanskiewody.station_list`, the last two optional in `store check|sync`; one kind of files per call.
- `years`: required in `datasets files|download` and, for `pl.{imgw,gdanskiewody}.*`, in `store check|sync`; optional there for `cz.chmu.*` (none = the published years); never for `cz.chmu.{meteo_daily,groundwater_characteristic}`; not before "First year". `months` only for `pl.*`, `params` only for `pl.imgw.hydro_semiannual`.

## Commands

One line per command, by effect. Marks: `[output: …]` — the option writes a file when given; `[is a check]` — the command plans itself; `[local]` — no REST route.

**Read — no network, no writes**

- `datasets list` — List the datasets of the registry.
- `datasets files` — List the source files of a dataset for given years or stations.
- `datasets providers` — List the data providers.
- `stations export` — Export the stations of the current catalogs as GeoJSON or CSV. [output: write; force: overwrite]
- `pmaxtp url` — Build the PMAXTP API URL of a point.
- `pmaxtp check` — Check the PMAXTP cell in the raw root without downloading data. [is a check]
- `pmaxtp read` — Read a saved PMAXTP cell from the raw root.
- `store info` — Show the state of a raw or data root and the supported contracts.
- `store scan` — List the versions and problems of a raw or data root.
- `store export` — Export the records of one archive version as CSV or JSONL. [output: write; force: overwrite]
- `series select` — Select stations, variables and years of the current series.
- `series read` — Read the values and flags of one station's series from the data root.
- `series summary` — Show the coverage of stations and variables of a series.
- `series export` — Export one station's series as CSV, JSON or Parquet. [output: write; force: overwrite]
- `analyses list` — List the stored analyses of a station.
- `analyses read` — Read one stored analysis of a station.
- `analyses export` — Export the stored analyses of a station as JSON or CSV. [output: write; force: overwrite]
- `commands list` — List the catalog commands.
- `commands schema` — Describe a command or the whole catalog as obserwator-commands/1.
- `commands guide` — Generate AGENTS.md or llms.txt for AI agents. [output: write; force: overwrite]

**Network — connects to a source, writes nothing**

- `stations find` — Find stations by name, river, code prefix or area.
- `current hydro` — Fetch current hydrological data from the IMGW API.
- `current meteo` — Fetch current meteorological data from the IMGW API.
- `current synop` — Fetch current synoptic data from the IMGW API.
- `current warnings` — Fetch the current IMGW hydrological and meteorological warnings.
- `current hydro-states` — Fetch the water states of hydrological stations with coordinates (hydro.imgw.pl map).
- `pmaxtp fetch` — Fetch the PMAXTP maximum precipitation of a point.
- `store check` — Check the freshness of the dataset archives without downloading data. [plan: overwrite; is a check]

**Write — new files, versions or tasks; `--check` first**

- `datasets download` — Download the source files of a dataset as plain files or into the raw root. [output_dir: write; force: overwrite; local]
- `current poll` — Poll the sources of current data into the capture spool. [local]
- `pmaxtp sync` — Download the PMAXTP cell of a point into the raw root or as plain files. [output_dir: write; force: overwrite]
- `store init` — Create a raw root or, with --kind data, a data root. [local]
- `store sync` — Download new or missing archives into the raw root. [output_dir: write; force: overwrite]
- `store catalog` — Build the station catalog stations.geojson of one provider.
- `store import` — Import the files of a provider fed by files.
- `series build` — Build the Parquet series of a dataset from the raw root.
- `analyses build` — Compute and store the analyses of every station with Hydrolog.

## Flags and values

- Lists (`--analyses`, `--bbox`, `--datasets`, `--months`, `--params`, `--stations`, `--variables`, `--years`): comma-separated values (`--months 1,2`) or a repeated flag (`-s A -s B`). Years (`--years`): `2024`, `2020-2023` or `2018,2020-2023`. Dates (`--end`, `--start`): ISO `YYYY-MM-DD`.
- On by default: `--series/--no-series` (`--no-…` turns it off); the other boolean flags (`--force`, `--main-only`) take no value and turn their option on.
- Environment: `OBSERWATOR_ROOT` — the data root, the default `--root`, else `<data_dir>/obserwator`; `OBSERWATOR_RAW_ROOT` — the raw root, the default `--raw-root` and `--root` of `datasets download`, `pmaxtp check|sync|read`, `store init|check|sync|export`, else `<data_dir>/obserwator-raw` (CLI, MCP stdio; `stations find` — only with `source=store`); `OBSERWATOR_LANG` — the language of the CLI help and progress lines, the default `--lang` (`pl`, `en`).

## Typical flows

Replace `STATION_CODE` and `WIGOS_ID` with the values of earlier steps.

### 1. Daily precipitation at the Poznań station, 2010–2020

1. `obserwator stations find --kind meteo --query poznan --json` — several hits → ask the user; the code of the chosen station is `STATION_CODE`.
2. Start with `pl.imgw.meteo_precip_daily` (precipitation stations, `P`): the station list does not tell a station's network.
3. `obserwator store check --datasets pl.imgw.meteo_precip_daily --years 2010-2020 --json` — plan: files and bytes; the archives cover the whole country, so tell the user the size.
4. `obserwator store sync --datasets pl.imgw.meteo_precip_daily --years 2010-2020 --json` — after the user agrees.
5. `obserwator series build --dataset pl.imgw.meteo_precip_daily --json` — the station series in the data root.
6. `obserwator series summary --dataset pl.imgw.meteo_precip_daily --stations STATION_CODE --json` — the station is missing → repeat steps 3–6 with `pl.imgw.meteo_{climate,synop}_daily` in turn; missing from all → tell the user, do not substitute another station.
7. `obserwator series read --dataset pl.imgw.meteo_precip_daily --station STATION_CODE --variables P --start 2010-01-01 --end 2020-12-31 --limit 500 --json` — next pages: `--cursor` = `page.next_cursor`.

### 2. Daily discharge of a Czech station (ČHMÚ)

1. `obserwator stations find --kind hydro --query spindleruv --provider CHMU --json` — the WIGOS identifier of the chosen station is `WIGOS_ID`.
2. `obserwator store check --datasets cz.chmu.hydro_daily --years 2020-2025 --stations WIGOS_ID --json` — plan: the station files by year.
3. `obserwator store sync --datasets cz.chmu.hydro_daily --years 2020-2025 --stations WIGOS_ID --json` — after the user agrees.
4. `obserwator series build --dataset cz.chmu.hydro_daily --json` — the station series in the data root.
5. `obserwator series read --dataset cz.chmu.hydro_daily --station WIGOS_ID --variables Q --limit 500 --json` — next pages: `--cursor` = `page.next_cursor`.

## What not to do

1. Do not build or crawl the providers' server URLs by hand — use `datasets files|download`, `store sync`.
2. Do not run writes (`store sync`, `series build`, `datasets download`) without a plan and the user's consent.
3. Do not guess a station or a dataset: with several `stations find` hits, ask; check with `series summary` that a dataset has the station.
4. Do not edit, move or delete files of a store — it only grows.
5. Do not download "just in case": narrow `years`, `months` and `stations`.
6. Read long lists in pages (`limit`, `cursor`); use `series read` or `series export --output`, not CSV in the context.
7. Do not poll `current …` in a loop — it is a live API; keep the result.
8. Show the `attribution` and `terms_notice` lines verbatim with the data and in what you make of it (the `license_terms` notice too).
9. Point `version` only below `*/versions/` of a root, without `..`; over REST and MCP over HTTP relative to the command's root.

Developing this repository? Read CLAUDE.md.
