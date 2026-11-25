# Obserwator — guide for agents (version <!-- obserwator:version -->)

> Generated from the command catalog: `obserwator commands guide --format agents`. Do not edit by hand.

## What Obserwator is

Obserwator is a Python library, the `obserwator` CLI, a REST API and an MCP server for public hydrological and meteorological data. Archives go into a versioned raw root (immutable versions identified by SHA-256) or plain files; series, station catalogs and analyses are built from it into a data root and read offline.

Use it for archive and current data of the providers' stations, reproducible local copies and PMAXTP maximum precipitation. Not supported: forecasts, ČHMÚ's climate `now` and `recent`, PMAXTP outside Poland. Install: `pip install obserwator[cli]` (`[mcp]` adds the MCP server, `[store]` the Parquet series).

<!-- obserwator:providers -->

## Rules: check → run → read

<!-- obserwator:rules -->

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

<!-- obserwator:statuses -->

An error has a code from a closed registry, the same in every interface; `details.option` names the wrong option. Codes (CLI exit code/HTTP status; `—`: never): <!-- obserwator:errors -->.

## Datasets

A dataset key reads `<country>.<provider>.<dataset>`; a slug (`imgw_hydro_daily`) and a legacy alias (`hydro/dobowe`) are accepted on input only. Datasets of the store:

<!-- obserwator:datasets -->

- `stations`: WIGOS (required for `cz.chmu.*`), 9 digits (`pl.imgw.meteo_synop_*`) or `GDANSKIEWODY-<no>` of the stored `pl.gdanskiewody.station_list`, the last two optional in `store check|sync`; one kind of files per call.
- `years`: required in `datasets files|download` and, for `pl.{imgw,gdanskiewody}.*`, in `store check|sync`; optional there for `cz.chmu.*` (none = the published years); never for `cz.chmu.{meteo_daily,groundwater_characteristic}`; not before "First year". `months` only for `pl.*`, `params` only for `pl.imgw.hydro_semiannual`.

## Commands

One line per command, by effect. Marks: `[output: …]` — the option writes a file when given; `[is a check]` — the command plans itself; `[local]` — no REST route.

<!-- obserwator:commands -->

## Flags and values

<!-- obserwator:flags -->

## Typical flows

Replace `STATION_CODE` and `WIGOS_ID` with the values of earlier steps.

<!-- obserwator:flows -->

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
