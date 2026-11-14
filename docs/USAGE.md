# Obserwator — Usage Guide

A detailed guide to the Obserwator interfaces (Python library, CLI, REST, the GUI, MCP server), configuration, the versioned store and the 3.0.0 changes, moved without content changes from [README.md](../README.md) (Nogat standard 1.0, DOC-2.2). For developers: [CODEBASE.md](CODEBASE.md) (project structure) and [TESTING.md](TESTING.md) (tests).

## Contents

- [Using as a Python library](#using-as-a-python-library)
- [Quick start (CLI)](#quick-start-cli)
- [REST API](#rest-api)
- [GUI](#gui)
- [AI agents: language, command effects and the MCP server](#ai-agents-language-command-effects-and-the-mcp-server)
- [Source data structure](#source-data-structure)
- [Docker](#docker)
- [Configuration](#configuration)
- [Versioned store (optional)](#versioned-store-optional)
- [Changes in version 3.0.0](#changes-in-version-300)

## Using as a Python library

Obserwator can be used as a library in other Python projects (e.g. HydroLOG). Functions take the first object positionally and every further argument by name; a station code is always the string `station_code` (IMGW-PIB: 9 digits, ČHMÚ: a WIGOS identifier, e.g. `0-203-1-001000`).

### PMAXTP data (probable maximum precipitation)

```python
from obserwator import fetch_pmaxtp

# Fetch data for Warsaw (method: "POT" — the default — or "AMP")
result = fetch_pmaxtp(52.23, 21.01, method="POT")

# 15-minute precipitation with 50% probability
precip = result.data.get_precipitation(15, 50)
print(f"Precipitation 15 min, p=50%: {precip} mm")  # precipitation [mm] for t=15 min, p=50%
rare = result.data.get_precipitation(15, 0.01)  # fractional probability: a number, not a string

# Durations [min]: 5, 10, 15, 30, 45, 60, 90, 120, 180, 360, 720, 1080, 1440, 2160, 2880, 4320
# Probabilities [%]: 0.01, 0.02, 0.03, 0.05, 0.1, 0.2, 0.3, 0.5, 1, 2, 3, 5, 10, 20, 30, 40,
# 50, 60, 70, 80, 90, 95, 98, 98.5, 99, 99.5, 99.9 (50 and 50.0 are the same key). A number outside the list
# (e.g. 0.7) is an ObserwatorValidationError with the allowed values in details["allowed"]; the same applies
# to get_confidence_bound and get_estimation_error.
```

### Current data

```python
from obserwator import fetch_hydro_current, fetch_meteo_current, fetch_synop, fetch_warnings

# All hydrological stations or one station (station = 9-digit code)
stations = fetch_hydro_current()
print(f"Number of stations: {len(stations)}")
data = fetch_hydro_current(station="150160180")
print(f"{data[0].station_name}: {data[0].water_level_cm} cm")

# Meteorological and synoptic stations
meteo = fetch_meteo_current()
warszawa = fetch_synop(station_name="Warszawa")
print(f"Temperature: {warszawa[0].temperature_c}°C")

# Warnings: kind="hydro" | "meteo"; omitted = both families
for warning in fetch_warnings(kind="hydro"):
    print(warning.kind, warning.event, warning.level, warning.valid_to)
```

### Stations

```python
from obserwator import fetch_hydro_states, find_stations

# Search the station lists (case- and diacritics-insensitive);
# provider: "IMGW-PIB" | "CHMI", omitted = both providers
for station in find_stations(kind="hydro", query="wisla", provider="IMGW-PIB")[:5]:
    print(station.station_code, station.name, station.river)

# Offline, from the current station catalogs of a data root (built by store catalog; short_code is None)
stored = find_stations(kind="hydro", query="wisla", source="store", root="/dane/obserwator")

# Water states of hydro stations with coordinates (hydro-back.imgw.pl)
states = fetch_hydro_states()
alarmed = [s for s in states if s.water_state == "alarm"]
for s in alarmed:
    print(f"{s.name}: {s.latitude}, {s.longitude}")
```

### Downloading archival data

```python
from obserwator import archive_files, datasets, download_archives, download_hydro_data, parse_zip_file

# Dataset registry: key (pl.imgw.hydro_daily), slug (hydro_daily) or alias (hydro/dobowe)
for dataset in datasets(kind="hydro"):
    print(dataset.key, dataset.legacy_alias, dataset.first_year)

# File URLs without downloading; years: 2023 | "2020-2023" | "2020,2022" | [2020, "2022-2023"]
for file in archive_files("hydro/dobowe", years=2022, months=[1, 2]):
    print(file.server_path, file.url)

# Download plain files into a directory (output_dir) using the IMGW server path layout, without metadata;
# an existing file requires force=True, and root=... writes versions to the raw root instead of the directory
report = download_archives("hydro/miesieczne", years=2023, output_dir="dane")
for item in report.items:
    print(item.slot, item.status, item.path)

# One archive as bytes (DownloadResult) and the hydro parser
result = download_hydro_data("miesieczne", 2023)
print(result.url, result.etag, result.last_modified, result.content_length)
for station, record in parse_zip_file(result.data, "miesieczne"):
    print(station.station_code, record.hydro_year, record.hydro_month, record.flow_m3s)
    break
```

### Versioned store (requires `obserwator[store]` for Parquet)

```python
from obserwator import (
    build_catalog,
    build_series,
    check_store,
    current_version,
    export_archive,
    export_series,
    init_store,
    read_series,
    read_station_list,
    select_series,
    summarize_series,
    sync_store,
)

# The store has two roots (ADR-017): the raw root keeps the downloaded sources, the data root what is built from them
raw = init_store("/dane/obserwator-raw")            # obserwator-store.json; without a root: <data_dir>/obserwator-raw
data = init_store("/dane/obserwator", kind="data")  # obserwator-data.json; without a root: <data_dir>/obserwator

# 1. Check freshness without downloading archives (listing + HEAD); the plan is saved outside the roots
plan = check_store(raw, datasets=["pl.imgw.hydro_monthly"], years="2022-2023", plan="plan.json")

# 2. Download new/missing files into the raw root according to the plan (raw archives only, ADR-015), then
#    build the Parquet series of the dataset in the data root from the current archive versions of the raw root
report = sync_store(raw, plan="plan.json")
build_series(data, raw_root=raw, dataset="pl.imgw.hydro_monthly")  # raw_root is only read

# 3. Coverage and reading the current series version (offline; dataset = key, slug or alias)
for coverage in summarize_series(root=data, dataset="hydro/miesieczne", stations=["152210170"]):
    print(coverage.variable, coverage.first, coverage.last, coverage.gaps)
for record in read_series(root=data, dataset="hydro/miesieczne", station="152210170",
                          variables=["Q_mean"]):
    q = record.measurements["Q_mean"]
    print(record.date, q.value, q.flag)  # flag: value|missing|no_phenomenon|accumulated

# 4. Select a series version for a set of stations (read-only)
selection = select_series(data, dataset="pl.imgw.hydro_monthly", stations=["152210170"], years=2023)

# 5. CSV export with units and IMGW-PIB attribution (without output: a line iterator; with output: one file and an OutputReport, an existing file requires force=True)
export_series(root=data, dataset="pl.imgw.hydro_monthly", station="152210170",
              variables=["Q_mean"], output="q.csv")

# 6. Records of one archive version of the raw root (slot = archive:<key>:<file>, SHA-256 verified)
archive = current_version(raw, slot="archive:pl.imgw.hydro_monthly:2023/mies_2023.zip")
for line in export_archive(archive.version, format="jsonl"):
    print(line, end="")
    break

# 7. The stations.geojson catalog of the data root and the station lists of the raw root (a single
#    StationListEntry type): store sync downloads the station sources, the catalog is built offline from them
sync_store(raw, datasets=["pl.imgw.hydro_stations", "pl.imgw.meteo_stations",
                          "pl.imgw.hydro_now", "pl.imgw.meteo_now"])
sync_store(raw, datasets=["pl.imgw.hydro_details"])  # optional: hydro.imgw.pl's station details (~910 requests)
build_catalog(data, raw_root=raw)
for station in read_station_list(raw, kind="meteo")[:3]:
    print(station.station_code, station.name, station.short_code)
```

For offline tests use `obserwator.testing.build_fixture_store(raw_dir, data_root=data_dir)` — it builds a small raw root and the data root built from it from recorded responses, without internet access (fictitious stations, e.g. `149190310`), and returns `FixtureRoots(raw, data)`, the handles of both; the `variant="complete_pl_cz"` variant adds ČHMÚ data (stations `0-203-1-900001`, `0-203-1-900002`, `0-203-0-90001`, `0-203-0-90000000002`, series, catalog and an observation).

### ČHMÚ data (Czechia)

ČHMÚ datasets (`cz.chmi.*`) use the same registry, store, command catalog and contracts as IMGW-PIB. ČHMÚ archives are published per station, so every operation on them requires a list of stations (`stations`, WIGOS identifiers).

```python
from obserwator import archive_files, build_catalog, build_series, check_store, datasets, find_stations, providers, sync_store

# Providers: IMGW-PIB (pl.imgw.*, 9-digit codes) and CHMI ("ČHMÚ", cz.chmi.*, WIGOS identifiers)
for provider in providers():
    print(provider.id, provider.short_name, provider.country, provider.license.id)
print([d.key for d in datasets(provider="CHMI")])  # hydro_daily, meteo_daily, hydro_stations, meteo_stations, hydro_now, meteo_now

# A live ČHMÚ station ("now" metadata; query without Czech characters)
station = find_stations(kind="hydro", query="spindleruv", provider="CHMI")[0]
print(station.station_code, station.name, station.river)  # 0-203-1-001000 Špindlerův Mlýn Labe

# Station files offline: hydro — one JSON per station and year, meteo — 4 CSV files per station (no years)
for file in archive_files("cz.chmi.hydro_daily", stations=[station.station_code], years="2024-2025"):
    print(file.year, file.url)  # …/hydrology/historical/data/daily/H_0-203-1-001000_DQ_2024.json
for file in archive_files("cz.chmi.meteo_daily", stations=["0-203-0-11799"]):
    print(file.param, file.server_path)  # SRA, T, TMA, TMI

# Store (the roots raw and data of the example above): one GET of the server directory listing instead of a HEAD per file
plan = check_store(raw, datasets=["cz.chmi.hydro_daily"], stations=[station.station_code],
                   years="2024-2026")  # years optional for hydro: omitted = published years
for item in plan.items:
    print(item.archive.year, item.status, item.remote_listed_at, item.error)  # 2026 unverifiable … not published
print(plan.requests)  # {'made': 1, 'planned': 4}: HEAD+GET for the two missing files
report = sync_store(raw, plan=plan)  # HEAD before GET; change since the plan → stale_plan
build_series(data, raw_root=raw, dataset="cz.chmi.hydro_daily")  # series chmi_hydro_daily in the data root
sync_store(raw, datasets=["cz.chmi.hydro_stations", "cz.chmi.meteo_stations",
                          "cz.chmi.hydro_now", "cz.chmi.meteo_now"])  # station sources
build_catalog(data, raw_root=raw, provider="CHMI")  # offline; stations/versions/chmi_stations/…, catalog: catalog:cz.chmi.stations
```

Offline reading — here on the data root of the PL + CZ test roots:

```python
from obserwator import export_series, read_catalog, read_series, summarize_series
from obserwator.testing import build_fixture_store

roots = build_fixture_store("/tmp/obserwator-demo-raw", data_root="/tmp/obserwator-demo", variant="complete_pl_cz")
demo = roots.data  # the data root; fictitious stations, no internet

# ČHMÚ meteo: besides the value and flag, also ČHMÚ QUALITY (0–5) and FLAG verbatim
for record in read_series(root=demo, dataset="cz.chmi.meteo_daily", station="0-203-0-90001",
                          variables=["P"]):
    p = record.measurements["P"]
    print(record.date, p.value, p.flag, p.quality, p.source_flag)  # 2023-10-22 0.0 value 0 T (trace of precipitation)

# Coverage per station: a year without a published file (2005) is unknown, not a gap
for coverage in summarize_series(root=demo, dataset="cz.chmi.hydro_daily", stations=["0-203-1-900002"]):
    print(coverage.variable, coverage.first, coverage.last, coverage.gaps)  # Q 2004-01-01 2006-12-31 ()

# CSV: ČHMÚ quality and flag columns, ČHMÚ attribution (CC BY 4.0) in the first data row
lines = list(export_series(root=demo, dataset="cz.chmi.meteo_daily", station="0-203-0-90001",
                           variables=["P"]))
print(lines[0], end="")  # date,year,P [mm],P_flag,P_quality,P_source_flag,attribution_source,attribution_processed,attribution,terms_notice

# ČHMÚ station catalog: SPA thresholds (drought, spa1–spa3, q50) for water level and discharge
for feature in read_catalog(root=demo, provider="CHMI"):
    print(feature.properties["station_code"], feature.properties.get("thresholds"))
```

ČHMÚ rules and behavior:

- **Options:** `stations` is required for `cz.chmi.*` and not allowed for `pl.imgw.*`; `years` is required for `cz.chmi.hydro_daily` in `archive_files`/`datasets files|download`, optional in `check_store`/`sync_store` (omitted = years published in the station listing) and not allowed for `cz.chmi.meteo_daily` (the files cover the whole station history); `months` and `params` are for IMGW-PIB only. One `check_store`/`sync_store` call covers either IMGW-PIB national archives or ČHMÚ station files, not both at once.
- **Freshness:** `check_store` compares the time (to the minute) and size from the server listing with the version signal in the store (`current`, `newer`, `missing`); a year with no file at the source is `unverifiable` with `error="not published"` (not an error; the text is a catalog message, in Polish "nieopublikowany"), and `download_archives` gives it a `not_published` item. `now`/`recent` data, hourly data, ČHMÚ warnings and PMAXTP outside Poland are not supported; `current …` and `pmaxtp …` apply to IMGW-PIB only.
- **Versions:** ČHMÚ regenerates files in bulk. The same bytes under a new `Last-Modified` give `relabeled` (a copy, as for IMGW-PIB); different bytes with the same content (hydro JSON and station lists without the `zaznamID`/`datumVytvoreni` envelope, form `chmi-json/1`, sidecar field `content_sha256`) give `unchanged` without a new version, with the `content_unchanged` notice and an observation of the new signal in `observations/`, so the next check gives `current` without downloading.
- **Series:** `series.json` has the periods known per station (`stations[<code>].periods`); the meteo series has `<V>_quality` and `<V>_source_flag` columns, and values are not corrected based on quality. `series select` accepts only years within the series periods (a range across an unpublished year → `validation_error`).
- **Station catalog:** a separate version of the provider catalog in the data root (`build_catalog(data, raw_root=raw, provider="CHMI")`, `obserwator store catalog --provider CHMI`), built offline from the `now` and historical metadata stored in the raw root (`cz.chmi.hydro_now`, `cz.chmi.meteo_now`, `cz.chmi.hydro_stations`, `cz.chmi.meteo_stations`, downloaded by `store sync --datasets`) with a check against the Czech border outline; coordinates carry the published value (JSON does not keep trailing zeros, e.g. `50.6493690` → `50.649369`).
- **License:** CC BY 4.0; sidecars, series, the catalog and exports carry the ČHMÚ attribution (processed forms — marked as changed), and the `license_terms` notice states the license terms.

### Stored analyses (computed by Hydrolog)

Every number of an analysis is Hydrolog's (ADR-016, Nogat ECO-059): `build_analyses` exports the current series of every station of the data root, runs the calls of the registry through Hydrolog's program and stores each answer byte for byte as a version of the data root, one per provider (`analyses/versions/<pl.imgw|cz.chmi>/…`, slot `analyses:<pl.imgw|cz.chmi>.analyses`, see "Directory layout"); it reads no raw root. The readers return Hydrolog's answer with the series versions, options and Hydrolog version it came from. The program is the setting `hydrolog_command` (`OBSERWATOR_HYDROLOG_COMMAND`, `[obserwator] hydrolog_command`; a command line, e.g. `"/opt/hydrolog/.venv/bin/hydrolog"`); without it `hydrolog` on `PATH`; no command option chooses it. Without a program `build_analyses` and `compute_analysis` end with `missing_dependency` (`details.reason="hydrolog_missing"`); the readers need no Hydrolog.

```python
from obserwator import (
    analysis_definitions,
    build_analyses,
    compute_analysis,
    export_analyses,
    list_analyses,
    read_analysis,
)

# The registry: 87 analyses (59 hydro, 28 meteo), each one Hydrolog command over the whole record
for definition in analysis_definitions("meteo")[:2]:
    print(definition.id, definition.command, [option.name for option in definition.overridable])
# precipitation.sums meteo precipitation ['first_year', 'last_year', 'year_type', ...]

# 1. Compute and store every station in the data root (stations=[...] computes only these; workers = Hydrolog processes)
report = build_analyses(data, workers=2)
print(report.status, report.hydrolog_version, [(p.provider, p.status, p.computed, p.carried) for p in report.providers])

# 2. Read: the analyses of a station (the code names the provider) and one of them
for summary in list_analyses(root=data, station="149190310"):
    print(summary.analysis, summary.command, summary.status, summary.analyses_version)
result = read_analysis(root=data, station="149190310", analysis="characteristic.Q")
print(result.envelope["result"]["schema"], result.inputs[0].series_version)  # hydrolog-stats-characteristic/1
# a failed analysis: status "failed", error = Hydrolog's hydrolog-error/1 document, envelope None

# 3. Export: json (one obserwator-analyses-export/1 document) or csv (one row per value, with the attribution)
export_analyses(root=data, station="149190310", format="csv", output="raba-analyses.csv")

# 4. A subset on the fly: Hydrolog computes it now, nothing is stored (stored=False)
subset = compute_analysis(data, station="149190310", analysis="characteristic.Q", options={"first_year": 1990})
```

- **Carry-forward:** a station whose station Parquet files (SHA-256 per dataset), catalog thresholds, Hydrolog version and registry are unchanged is carried into the new version by hard links without a Hydrolog call; a provider with nothing to compute is `unchanged` and gets no new version. Hydrolog's development builds all report `1.0.0.dev0`, so a change of Hydrolog within one development version does not trigger a recomputation.
- **Failures:** an analysis Hydrolog answers with an error is stored with `status="failed"` and Hydrolog's `hydrolog-error/1` document; one whose input number (a pick from another analysis) is missing is not stored.
- **Options on the fly:** `compute_analysis` takes only the overridable options of the analysis or of an analysis it depends on (`analysis_definitions()` lists them with types and bounds), never a file or a column, minus `locked` (e.g. `durations_days` for `precipitation_quantiles.2d`, whose pick reads a position of that list); anything else is `validation_error`. `timeout` (30 s) bounds the whole computation (`source_unavailable`, `details.reason="timeout"`). It is a Python function only, not a catalog command, so REST and MCP never start Hydrolog on request.
- **Spells:** the stored `spells.dry`/`spells.wet` list only spells of 10 days or more; their summaries count every spell.

### Command catalog

Every CLI command and REST route can be called from Python with the same options; the result is a `CommandResult` (envelope `obserwator-result/1`), and list commands return the tuple of the page's items as `result` and a `Page` (`total`, `next_cursor`, `truncated`) as `page`; pass `next_cursor` as the `cursor` option for the next page.

```python
from obserwator import command_schema, run_command

result = run_command("stations find", options={"kind": "hydro", "query": "wisla", "limit": 5})
print(result.status, result.page.total, [s.name for s in result.result])
print(result.to_json())  # dict of the JSON envelope, the same as CLI stdout with --json and the REST body

(entry,) = command_schema("store sync")["commands"]  # obserwator-commands/1 (Nogat commands-1)
print(entry["rest"]["path"], entry["operation_id"])  # /api/v1/store/sync obserwator_store_sync
print(entry["effects"]["writes"], entry["effects"]["network"], entry["errors"])  # replace True [...]
print([option["name"] for option in entry["options"]], entry["i18n"]["pl"]["summary"])
```

The command that downloads or builds a stored version again is rebuilt from its sidecar by `command_for_version(version, *, root=None, raw_root=None)` (offline, no writes; ADR-008, ADR-017). The result has the shape of `parse_command`, so `format_command`, `check_command` and `run_command` accept it. The first directory of the version tells its root: `archives/` and `pmaxtp/` lie in a raw root, `series/`, `stations/` and `analyses/` in a data root. A relative version lies in `root`, else in the default root of its kind; an absolute one in `root` or, without it, in its nearest ancestor with a marker. The call names that root as `--root`, and the call of a series or catalog also the raw root it reads as `--raw-root` (`raw_root`, else the default raw root).

```python
from obserwator import check_command, command_for_version, format_command

call = command_for_version("archives/versions/dane_hydrologiczne/dobowe/2024/codz_2024/2026-10-19_b6a19f65/codz_2024.zip",
                           root="/dane/obserwator-raw")
print(format_command(call.command, options=call.options))
# obserwator store sync --root /dane/obserwator-raw --datasets pl.imgw.hydro_daily --years 2024
plan = check_command(call.command, options=call.options)  # plan for this file (listing + HEAD)
call = command_for_version("series/versions/hydro_daily/2026-10-19_b85f50c3/series.json",
                           root="/dane/obserwator", raw_root="/dane/obserwator-raw")
# obserwator series build --root /dane/obserwator --raw-root /dane/obserwator-raw --dataset pl.imgw.hydro_daily
```

| Version | Command |
|---|---|
| IMGW-PIB archive | `store sync --datasets <key> --years <year>` (`--months <month>` for a monthly file) |
| ČHMÚ hydro / meteo archive | `store sync --datasets <key> --stations <code>` (hydro also `--years <year>`) |
| station list or station metadata (`*_stations`, `*_now`, `pl.imgw.hydro_details`) | `store sync --datasets <key>` |
| station catalog | `store catalog --raw-root <raw> --provider <provider>` |
| series version (or its station file) | `series build --raw-root <raw> --dataset <key>` |
| PMAXTP cell | `pmaxtp sync --latitude --longitude --method --ind-x --ind-y` |
| analyses version (or one of its station files) | `analyses build` |

The command is the narrowest one that selects the version's file; it may cover neighboring files (half-year `H`, `Q` and `T`, all elements of a ČHMÚ meteo station, the analyses of every provider). A version whose metadata do not rebuild the call is an `unsupported` error with `details.reason="command_not_rebuildable"` (a catalog built from a user coordinates file, a sidecar without a required field, a file that `store sync` does not select); a missing version is `not_found`, a bad sidecar is `data_error`, a root of the other kind than the version's is `store_unavailable` (`details.reason="wrong_root"`) and a version in no root is `validation_error`.

### Async version

```python
import asyncio
from obserwator import fetch_pmaxtp_async, fetch_hydro_current_async

async def main():
    # Concurrent requests
    pmaxtp, hydro = await asyncio.gather(
        fetch_pmaxtp_async(52.23, 21.01),
        fetch_hydro_current_async()
    )
    print(f"PMAXTP: {pmaxtp.data.get_precipitation(15, 50)} mm")
    print(f"Hydro stations: {len(hydro)}")

asyncio.run(main())
```

### Error handling

Every `ObserwatorError` has a `code` from the closed `ERROR_CODES` registry, `details` (e.g. the name of the invalid option) and, when the raise site knows the fix, a `hint`; the same code determines the CLI exit code and the HTTP status. `obserwator.error_report.error_report(e).to_dict()` is the `obserwator-error/1` document the CLI and MCP print for it.

```python
from obserwator import ERROR_CODES, ObserwatorConnectionError, ObserwatorError, ObserwatorValidationError, fetch_pmaxtp

try:
    result = fetch_pmaxtp(40.0, 21.01)
except ObserwatorValidationError as e:
    print(f"Validation error: {e}", e.code, e.details)  # validation_error {'option': 'latitude', ...}
except ObserwatorConnectionError as e:
    print(f"Connection error: {e}")  # code source_unavailable: timeout, network error, HTTP outside 2xx
except ObserwatorError as e:
    spec = ERROR_CODES[e.code]
    print(spec.title, spec.exit_code, spec.http_status)
```

| Code | Meaning | CLI | HTTP |
|---|---|---|---|
| `validation_error` | Invalid input | 2 | 400 |
| `not_found` | Not found | 3 | 404 |
| `conflict` | State conflict | 4 | 409 |
| `source_unavailable` | Data source unavailable (`detail` names the provider and URL) | 5 | 502 |
| `missing_dependency` | Missing optional dependency | 6 | 503 |
| `data_error` | Invalid data | 7 | 500 |
| `store_unavailable` | Store unavailable | 8 | 503 |
| `io_error` | File system error | 9 | 500 |
| `cancelled` | Cancelled | 130 | — |
| `forbidden` | Not allowed | 12 | 403 |
| `unsupported` | Unsupported (e.g. `command_not_rebuildable` from `command_for_version`) | 15 | 422 |
| `method_not_allowed` | Method not allowed | — | 405 |
| `internal_error` | Internal error | 1 | 500 |

---

## Quick start (CLI)

```bash
# Start the API server
obserwator server --reload

# Dataset registry and file URLs (without downloading)
obserwator datasets list -k hydro
obserwator datasets files -d hydro/dobowe -y 2023 -m 1

# Download archives into a directory (IMGW server path layout)
obserwator datasets download -d hydro/miesieczne -y 2023 -o dane
obserwator datasets download -d meteo/miesieczne/synop -y 2020-2023 -o dane

# Stations, current data and PMAXTP
obserwator stations find -k hydro -q wisla --limit 5
obserwator current hydro -s 150160180
obserwator current hydro -s 150160180 --json     # the obserwator-result/1 envelope, one JSON line
obserwator current warnings -k meteo
obserwator pmaxtp fetch --lat 52.23 --lon 21.01 --method AMP

# Versioned store (ADR-017): the raw root of the downloads (--root of datasets download, store check|sync|export,
# pmaxtp check|sync|read; OBSERWATOR_RAW_ROOT, [obserwator] raw_root or <data_dir>/obserwator-raw) and the data root
# of what is built from them (--root of the other store commands; OBSERWATOR_ROOT, [obserwator] root or <data_dir>/obserwator)
export OBSERWATOR_RAW_ROOT=/dane/obserwator-raw OBSERWATOR_ROOT=/dane/obserwator
obserwator store init                                 # the raw root (obserwator-store.json)
obserwator store init --kind data                     # the data root (obserwator-data.json; the first build also creates it)
obserwator store check -d pl.imgw.hydro_monthly -y 2022-2023 --plan plan.json
obserwator store sync --plan plan.json               # raw archives only, into the raw root
obserwator series build -d pl.imgw.hydro_monthly      # reads the raw root (--raw-root), writes the data root
obserwator store sync -d pl.imgw.hydro_stations,pl.imgw.meteo_stations,pl.imgw.hydro_now,pl.imgw.meteo_now
obserwator store sync -d pl.imgw.hydro_details        # optional: hydro.imgw.pl's station details, one request per station (a few minutes)
obserwator store catalog                              # stations.geojson in the data root, offline
obserwator store scan -k series                       # store info|scan: the data root unless --root names another
obserwator store export --version archives/versions/<path>/<version> --format jsonl | head   # relative to the raw root
obserwator series summary -d hydro/miesieczne -s 152210170
obserwator series export -d hydro/miesieczne -s 152210170 --variables Q_mean --output q.csv
obserwator pmaxtp sync --lat 52.23 --lon 21.01        # PMAXTP cell in the raw root

# Stored analyses computed by Hydrolog (OBSERWATOR_HYDROLOG_COMMAND or hydrolog on PATH)
obserwator analyses build --check                     # stations to compute and to carry forward
obserwator analyses build --workers 2                 # analyses/versions/<pl.imgw|cz.chmi>/…
obserwator analyses list -s 149190310
obserwator analyses read -s 149190310 --analysis characteristic.Q --json
obserwator analyses export -s 149190310 --format csv --output raba-analyses.csv

# ČHMÚ data (WIGOS station codes; -s/--stations required for cz.chmi.*)
obserwator datasets providers
obserwator datasets list --provider CHMI
obserwator stations find -k hydro -q spindleruv --provider CHMI
obserwator datasets files -d cz.chmi.hydro_daily -s 0-203-1-001000 -y 2024-2025
obserwator datasets download -d cz.chmi.hydro_daily -s 0-203-1-001000 -y 2025-2026 -o dane  # 2026: not_published
obserwator store check -d cz.chmi.hydro_daily -s 0-203-1-001000 -y 2024-2026 --plan plan-cz.json
obserwator store sync --plan plan-cz.json
obserwator series build -d cz.chmi.hydro_daily
obserwator store sync -d cz.chmi.hydro_stations,cz.chmi.meteo_stations,cz.chmi.hydro_now,cz.chmi.meteo_now
obserwator store catalog --provider CHMI              # stations/versions/chmi_stations/…
obserwator series read -d cz.chmi.hydro_daily -s 0-203-1-001000 --variables Q --limit 5
obserwator store scan --root /dane/obserwator-raw --provider CHMI -k observation   # observations live in the raw root

# AI agents: guide and descriptions (English by default), MCP server (obserwator[mcp] extra)
obserwator commands guide --format llms
obserwator commands schema --command "store sync" --json          # obserwator-commands/1, English
obserwator commands schema --command "store sync" --lang pl  # readable description in Polish
OBSERWATOR_LANG=en obserwator store sync --help          # CLI help in English
obserwator mcp                                        # stdio — started by the MCP client

# Plan without writing or downloading; description of the command options
obserwator store sync -d pl.imgw.hydro_monthly -y 2024 --check
obserwator store sync --schema
```

Catalog commands (full list: `obserwator commands list`):

| Command | Python function | `--check` | REST |
|---|---|---|---|
| `obserwator datasets list` | `datasets` | — | `GET /api/v1/datasets/list` |
| `obserwator datasets files` | `archive_files` | — | `GET /api/v1/datasets/files` |
| `obserwator datasets download` | `download_archives` | `check_command` | — (local) |
| `obserwator datasets providers` | `providers` | — | `GET /api/v1/datasets/providers` |
| `obserwator stations find` | `find_stations` | `check_command` | `GET /api/v1/stations/find` |
| `obserwator current hydro` | `fetch_hydro_current` | `check_command` | `GET /api/v1/current/hydro` |
| `obserwator current meteo` | `fetch_meteo_current` | `check_command` | `GET /api/v1/current/meteo` |
| `obserwator current synop` | `fetch_synop` | `check_command` | `GET /api/v1/current/synop` |
| `obserwator current warnings` | `fetch_warnings` | `check_command` | `GET /api/v1/current/warnings` |
| `obserwator current hydro-states` | `fetch_hydro_states` | `check_command` | `GET /api/v1/current/hydro-states` |
| `obserwator pmaxtp fetch` | `fetch_pmaxtp` | `check_command` | `GET /api/v1/pmaxtp/fetch` |
| `obserwator pmaxtp url` | `build_pmaxtp_url` | — | `GET /api/v1/pmaxtp/url` |
| `obserwator pmaxtp check` | `check_pmaxtp` | self | `GET /api/v1/pmaxtp/check` |
| `obserwator pmaxtp sync` | `sync_pmaxtp` | `check_pmaxtp` | `POST /api/v1/pmaxtp/sync` |
| `obserwator pmaxtp read` | `read_pmaxtp` | — | `GET /api/v1/pmaxtp/read` |
| `obserwator store init` | `init_store` | `check_command` | — (local) |
| `obserwator store info` | `store_info` | — | `GET /api/v1/store/info` |
| `obserwator store scan` | `iter_store` | — | `GET /api/v1/store/scan` |
| `obserwator store check` | `check_store` | self | `GET /api/v1/store/check` |
| `obserwator store sync` | `sync_store` | `check_store` | `POST /api/v1/store/sync` |
| `obserwator store catalog` | `build_catalog` | `check_catalog` | `POST /api/v1/store/catalog` |
| `obserwator store export` | `export_archive` | `check_command` | `GET /api/v1/store/export` |
| `obserwator series build` | `build_series` | `check_series` | `POST /api/v1/series/build` |
| `obserwator series select` | `select_series` | — | `GET /api/v1/series/select` |
| `obserwator series read` | `read_series` | — | `GET /api/v1/series/read` |
| `obserwator series summary` | `summarize_series` | — | `GET /api/v1/series/summary` |
| `obserwator series export` | `export_series` | `check_command` | `GET /api/v1/series/export` |
| `obserwator stations export` | `export_stations` | `check_command` | `GET /api/v1/stations/export` |
| `obserwator analyses build` | `build_analyses` | `check_analyses` | `POST /api/v1/analyses/build` |
| `obserwator analyses list` | `list_analyses` | — | `GET /api/v1/analyses/list` |
| `obserwator analyses read` | `read_analysis` | — | `GET /api/v1/analyses/read` |
| `obserwator analyses export` | `export_analyses` | `check_command` | `GET /api/v1/analyses/export` |
| `obserwator commands list` | `list_commands` | — | `GET /api/v1/commands/list` |
| `obserwator commands schema` | `command_schema` | — | `GET /api/v1/commands/schema` |
| `obserwator commands guide` | `agent_guide` | `check_command` | `GET /api/v1/commands/guide` |

Outside the catalog: `obserwator version`, `obserwator server`, `obserwator mcp`, `obserwator gui serve` (section [GUI](#gui)) and `obserwator admin keys|create|revoke|delete|stats`, which manages the REST API keys of `api_keys.json` (`OBSERWATOR_API_KEYS_FILE`), not the GUI's admin key (section [Admin panel](#admin-panel)).

**Options.** Flag = `--` + option name with `-` instead of `_`; short forms: `-d` dataset(s), `-y` years, `-m` months, `-s` station(s), `-k` kind, `-q` query, `-o` plain-file directory (`--output-dir`), `-r` root, `-f` format; `--lat`/`--lon` are aliases of `--latitude`/`--longitude`. Write target (DEV-19.1): `--output-dir` (`-o`) writes plain files into a directory, `--root` (`-r`) writes to the versioned store, the raw root of a download or the data root of a build (the options are mutually exclusive; with neither of them, the default root of the command's kind: ADR-017), `--output` (no short form) writes one export file, and `--force` replaces existing plain files. `--raw-root` names the raw root that `series build` and `store catalog` read and never write (default: the raw root of `OBSERWATOR_RAW_ROOT`, `[obserwator] raw_root` or `<data_dir>/obserwator-raw`). Lists: comma-separated values or a repeated flag. List commands have `--limit` and `--cursor` (the opaque `page.next_cursor` of the previous page; any other text → `validation_error` with `details.option="cursor"`). `--provider` (`IMGW-PIB` or `CHMI`) narrows `datasets list`, `stations find` and `store scan` to one provider (omitted = both) and selects the catalog in `store catalog` (default `IMGW-PIB`). `--check` (only in commands with a `--check` column) prints the plan without writing and without downloading data, `--schema` — the description of the command options without running it, `--json` (every command) — the envelope instead of the summary for a person, `--lang pl|en` (every command) — the language of that summary and of the stderr lines. Dataset-dependent rules (e.g. `--stations` for `cz.chmi.*`) are in `x-obserwator.rules` of the schema. `OBSERWATOR_LANG=en` switches the CLI help and the default `--lang` of the summary to English (a value outside `pl|en` → `validation_error`, code 2).

**Output.** Without `--json` stdout carries a short summary for a person in the language of `--lang` (default `OBSERWATOR_LANG`): the status and the command, the items of a list as a table of their key fields with the page line (`Strona: 50 z 154, dalej: --cursor NTA`), the main fields of a document (work items with an error first), then the notices; its layout is not a contract. With `--json` stdout is one JSON line — the `obserwator-result/1` envelope (`schema`, `tool`, `version`, `command`, `check`, `status`, `result`, `notices` `{level, code, message}` and, for a list command, `page` `{total, next_cursor, truncated}`); `result` is a document with its own `schema` (`obserwator-<kind>/1`), the list of a page's items or null; store paths are relative to the root. `store export`, `series export` and `commands guide` without `--output` print a CSV/JSONL/Markdown stream (the same with and without `--json`); with `--output` they write one file (an existing one requires `--force`, a file in the store is a `conflict`), and the envelope `result` is `{schema, output, files[]}` (`obserwator-output/1`; `files[]` = `{path, size_bytes, sha256, status}`). Progress goes to stderr, as do the notices with `--json` (each distinct one once, e.g. `license_terms`; without `--json` they close the summary), and an error — as the JSON document `obserwator-error/1` (`schema`, `code`, `title`, `message`, `hint` when one fits — the option or command that fixes it, `details`, `exit_code`, `command` when known) on the last stderr line (stdout empty; without `--json` one readable line in the language of `--lang` comes before it). Exit codes:

| Code | Meaning |
|---|---|
| `0` | `status` `ok` |
| `10` / `11` | `status` `partial` / `failed` (e.g. a `failed` or `stale_plan` item in `store sync`) — the full envelope is printed |
| `2`–`9`, `1` | error according to the code table (`validation_error` 2 … `io_error` 9, `internal_error` 1) |
| `130` | cancelled with Ctrl+C |

A PMAXTP point inside the coordinate frame of Poland but outside the IMGW grid (e.g. Kaliningrad, Lviv, the Baltic Sea) gives `validation_error` (CLI 2, REST 400).

**Data output.** A writing command has two ways of writing (DEV-19). `-o`/`--output-dir` writes only the files, without metadata, under the names they have in the store (`datasets download`: the provider server path layout; `pmaxtp sync`: two files named after the cell indices); the directory is created if missing. A directory that is a store (of any Nogat tool) or lies inside a store is rejected before the first request with a `conflict` error (`details.reason` = `output_in_store`, `details.paths` is that directory). Then, before the first byte, the full list of targets is built: a duplicate name, an existing file without `--force` and a target that would enter a subdirectory containing a store end with a `conflict` error (`details.reason` = `duplicate_output_name`, `output_exists`, `output_in_store`; `details.paths` lists all paths). `--check` shows a plan with `write`, `replace` (with `--force`) and `conflict` actions; in store mode a root with foreign files (`not_empty`) or a nested store (`nested_store`) is a single `conflict` action of a plan that succeeds. Files first go to `<directory>/.obserwator-incoming/<host>_<pid>_<token>/` and only after checking are moved into place with `os.replace`; this directory is removed after success, an error, SIGINT and SIGTERM, and leftovers older than 24 h are removed by the next run. This works on FAT/exFAT and SMB because it does not use links. `--force` replaces only the given files and deletes nothing; in the store `--force` downloads again and gives a new version or `unchanged`. Commands whose input or output is the store (`store init`, `series build`, `store catalog`, `analyses build`) have no `--output-dir` (the "store only" rule in their description), and `--plan` with `--output-dir` ends with `validation_error` (`store_only_option`) with a `--root` hint. Example:

```bash
obserwator datasets download -d hydro/miesieczne -y 2023 -o dane --check  # plan: write/replace/conflict
obserwator datasets download -d hydro/miesieczne -y 2023 -o dane     # files in dane/…, files[] with sha256
obserwator datasets download -d hydro/miesieczne -y 2023 -o dane --force  # replaces existing files
obserwator datasets download -d hydro/miesieczne -y 2023             # no target: the raw root <data_dir>/obserwator-raw
```

### Exports (ADR-014)

The stations of the current catalogs as GeoJSON or CSV, and one station's series as CSV, JSON or
Parquet; every file carries the attribution lines of its providers (ADR-012). JSON Schemas:
`schemas/obserwator-stations-export-1.schema.json`, `schemas/obserwator-series-export-1.schema.json`.

```python
from obserwator import export_series, export_stations

geojson = "".join(export_stations("/data/obserwator"))            # both providers, with series
export_stations("/data/obserwator", provider="CHMI", kind="hydro", series=False,
                format="csv", output="chmi_hydro.csv")
document = "".join(export_series(root="/data/obserwator", dataset="pl.imgw.hydro_daily",
                                 station="150160180", format="json"))
export_series(root="/data/obserwator", dataset="pl.imgw.hydro_daily", station="150160180",
              format="parquet", output="klodzko.parquet")       # Parquet needs output
```

```bash
obserwator stations export --root /data/obserwator --output stations.geojson
obserwator series export --root /data/obserwator -d pl.imgw.hydro_daily -s 150160180 -f parquet --output k.parquet
curl -OJ 'http://127.0.0.1:8000/api/v1/series/export?dataset=pl.imgw.hydro_daily&station=150160180&format=parquet'
```

- **GeoJSON** (`obserwator-stations-export/1`): an RFC 7946 FeatureCollection; `catalogs` names
  each catalog read (`provider`, `dataset`, `version` relative to the root, `label`,
  `downloaded_at`, `stations`, `license` `{id, url, terms_url}`, its `attribution` and
  `terms_notice`), `series` the series read (`provider`, `dataset`, `version`), `attribution` and
  `terms_notice` all lines; a feature has the station code as `id`, a `Point` `[lon, lat]` or
  null, the catalog's properties, `provider` and `series`
  (`{"pl.imgw.hydro_daily": {"first": "1951-11-01", "last": "2025-10-31", "variables": ["H", "Q", "T"]}}`,
  read from `series.json`, no pyarrow).
- **Stations CSV:** `station_code,name,kind,provider`, the other properties sorted (ČHMÚ
  `thresholds` as JSON), `latitude,longitude` (empty without a location), `datasets` (`;`), then
  `attribution_source,attribution_processed,attribution,terms_notice`; each provider's rows start
  with its lines.
- **Series JSON** (`obserwator-series-export/1`): `dataset`, `provider`, `station`,
  `series_version` (`series/versions/<slug>/<label>_<sha8>`), `year_type`, `time_unit`,
  `variables` (`unit`, `note`), `license`, `attribution`, `terms_notice`, and `columns`: the CSV's
  data columns as arrays (a value column by its variable name, `null` without a value).
- **Series Parquet:** the CSV's data columns with their names, typed (`date32`, `int32`, `float64`,
  `string`, `int8` quality, `timestamp[us]` extremum times); the file metadata holds
  `obserwator_schema`, `dataset`, `provider`, `station`, `series_version`, `year_type`,
  `time_unit`, `units`, `variable_notes`, `license`, `attribution`, `terms_notice` (JSON text).
  Without `output` (Python, CLI, MCP) it is a `validation_error` (`details.reason="output_required"`).

## REST API

After starting the server (`obserwator server`):
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
- `GET /api/v1` — version and list of catalog routes, `GET /health` — server status, `GET /llms.txt` — guide for agents (llms.txt) in the language from `Accept-Language` (English by default)
- `/mcp` — MCP server (Streamable HTTP) when `OBSERWATOR_MCP_ENABLED=true` (section "AI agents")

Routes are generated from the catalog: `/api/v1/<group>/<command>` (table above; local commands — `datasets download`, `store init` — have no routes). GET takes options in the query (comma-separated lists or a repeated parameter), POST — in a JSON body; `?check=true` on POST returns the plan without writing. The response is the same `obserwator-result/1` envelope as in the CLI; list commands have `limit` (default and maximum `OBSERWATOR_API_MAX_LIMIT`, 1000) and `cursor` (`page.next_cursor` of the previous answer). Errors: `application/problem+json` (`type`, `title`, `status`, `detail`, `instance`, `code`, `hint` when one fits, `details`). Language: notices, item and plan texts and the problem+json `title`, `detail` and `hint` are in English, and in Polish with `Accept-Language: pl` (`q` weights per RFC 9110); commands with a `lang` option (`commands list`, `commands schema`, `commands guide`) take it from the query, and without it from the header. Every command response has `Content-Language`, and `Vary: Accept-Language` when the header decided. The OpenAPI document (`/openapi.json`) is in English.

```bash
# Current data and archive URLs
curl "http://localhost:8000/api/v1/current/hydro?station=150160180"
curl "http://localhost:8000/api/v1/datasets/files?dataset=hydro/dobowe&years=2023&months=1"
curl "http://localhost:8000/api/v1/datasets/files?dataset=cz.chmi.hydro_daily&stations=0-203-1-001000&years=2024"

# Command catalog and guide (in English; in Polish with Accept-Language: pl)
curl "http://localhost:8000/api/v1/commands/schema?command=store%20sync"
curl http://localhost:8000/llms.txt
curl -H "Accept-Language: pl" http://localhost:8000/llms.txt

# Store: the data root (OBSERWATOR_ROOT) and the raw root (OBSERWATOR_RAW_ROOT) set on the server; without the root
# of a command's kind: 503 store_unavailable, details.reason not_configured
curl http://localhost:8000/api/v1/store/info                     # the data root
curl "http://localhost:8000/api/v1/store/scan?kind=series"
curl "http://localhost:8000/api/v1/series/summary?dataset=pl.imgw.hydro_monthly&stations=152210170"
curl "http://localhost:8000/api/v1/analyses/read?station=149190310&analysis=characteristic.Q"
curl "http://localhost:8000/api/v1/analyses/export?station=149190310&format=csv"
curl "http://localhost:8000/api/v1/store/check?datasets=pl.imgw.hydro_monthly&years=2024"   # the raw root

# Writes (OBSERWATOR_STORE_WRITES_ENABLED=true, OBSERWATOR_STORE_WRITE_TOKEN and the X-API-Key header)
curl -X POST "http://localhost:8000/api/v1/store/sync?check=true" \
    -H "X-API-Key: $OBSERWATOR_STORE_WRITE_TOKEN" -H "Content-Type: application/json" \
    -d '{"datasets": ["pl.imgw.hydro_monthly"], "years": "2024"}'
```

Store routes work only on the server-side, absolute roots (ADR-017; the client passes neither): `OBSERWATOR_RAW_ROOT` is the root of `store check|sync|export` and `pmaxtp check|sync|read`, `OBSERWATOR_ROOT` the root of `store catalog`, `store info|scan`, `stations export`, `stations find?source=store`, `series *` and `analyses *`, and `series build` and `store catalog` also read `OBSERWATOR_RAW_ROOT` as their `raw_root`. A command whose root is not set answers 503 `store_unavailable` (`details.reason="not_configured"`, the message names the variable), a root of the other kind 503 with `details.reason="wrong_root"`; `version` is relative to the command's root. Writing operations additionally require `OBSERWATOR_STORE_WRITES_ENABLED=true`, `OBSERWATOR_STORE_WRITE_TOKEN` and an `X-API-Key` header with that token — they are disabled by default (403 `forbidden`). User coordinate CSV files (`user_locations`) only from the `OBSERWATOR_USER_LOCATIONS_DIR` directory.

The server prints nothing but its lifecycle records on stderr (the record `start` names `host` and `port`) and writes its access, application and lifecycle logs to `<state_dir>/obserwator/logs`: section [Server logs](#server-logs).

## GUI

`obserwator gui serve` serves a browser GUI of Obserwator's data root (ADR-013): every located station of IMGW-PIB and ČHMÚ on one map, a station's description, series and current IMGW-PIB measurements, the analyses Hydrolog computed, downloads, and PMAXTP of a point. It is a server of its own that reads Obserwator's data only through its public functions (and uses the internal helpers `_environment`, `_jsonable` and `_hydrolog` for the settings, JSON and Hydrolog's program); `obserwator server` serves the REST API, and its `GET /` redirects to `/docs`. The command needs `pip install "obserwator[cli,gui]"`; the Python API (`obserwator.gui.create_app`, `serve`) needs only the extra `gui` (pyarrow, Starlette, uvicorn). The page is Polish by default and English through „PL | EN”; its texts are the area `gui` of the message catalog. A guide in Polish is served at `instrukcja/` („Instrukcja” in the top bar).

```bash
obserwator gui serve [--host 127.0.0.1] [--port 8060] [--root PATH] [--no-browser]
```

- `--host` and `--port` give the address, `127.0.0.1:8060` by default (this computer only; port `0` takes a free one); `--root` the data root, else the CLI's root (`OBSERWATOR_ROOT`, `[obserwator] root`, `<data_dir>/obserwator`); `--no-browser` leaves the default browser closed.
- Once it listens, the command writes the lifecycle record `start` on stderr, one JSON line whose `settings.url` is the address (e.g. `http://127.0.0.1:8060/`), and blocks until Ctrl+C or `SIGTERM`; then it lets open requests end (at most 5 s), writes the record `stop` and exits with 0. Nothing else goes to stdout or stderr while it serves (section [Server logs](#server-logs)). A port in use is `conflict` (`details.reason="port_in_use"`), a host that does not resolve or a basemap address that is no `http`/`https` URL is `validation_error`, a missing package of the extra `missing_dependency`: the error line of every command, with its exit code.
- Python: `obserwator.gui.serve(host=, port=, root=, open_browser=)` blocks the same way and returns `url`, `started_at` and `stopped_at`; `obserwator.gui.create_app(root=)` returns the ASGI app. Importing `obserwator.gui` imports neither Starlette nor uvicorn.

**The page.** The top bar holds Obserwator's mark, the view with its station or point, „Zgłoś uwagę”, „Instrukcja”, Nogat's app menu „Aplikacje” (the GUIs of `[nogat.gui]`), „PL | EN” and the theme („Auto”, „Jasny”, „Ciemny”). The map's bar switches the views „Stacje | Pomiary bieżące | PMAXTP”:

- „Stacje” draws the stations of the current catalogs in hydro.imgw.pl's symbols: a triangle for a hydrological station, a circle for a meteorological one, a hollow centre when the root holds no series of the station, a dashed outline for ČHMÚ, inactive ones faded. The left panel searches by name, river or code ignoring case and diacritics, filters by provider, kind, dataset and „tylko czynne”, and lists the stations without coordinates too, marked and counted. With no station chosen, the right panel offers „Pobierz listę stacji” (GeoJSON or CSV of the list's provider and kind). A chosen station opens there with „Informacje o stacji” („Dane katalogowe”; for an IMGW-PIB hydrological station with hydro.imgw.pl's details also the gauge zero with its datum, e.g. „281,617 m n.p.m. (EVRF2007)”, the catchment area, „Województwo”, „Powiat” and the section „Progi i stany ekstremalne IMGW-PIB”: „Stan ostrzegawczy”, „Stan alarmowy”, „Absolutne minimum”, „Absolutne maksimum” with „H [cm]” and „Data”, the dates as published; its lines then add RH), „Pomiary bieżące” (IMGW-PIB's latest values with their times; for ČHMÚ „Dane bieżące ČHMÚ nie są udostępniane”), „Dane pomiarowo-obserwacyjne” (dataset, variables, hydrological or calendar year, chart and table, flags), the analyses that apply to it and „Pobierz”. Hydrological analyses: „Stany charakterystyczne”, „Krzywa natężenia przepływu”, „Przepływy maksymalne i minimalne”, „Niżówki”, „Czas trwania i strefy”, „Reżim i sezonowość”, „Temperatura wody”, „Trendy i bilans”; meteorological: „Opady”, „Susze i okresy bezopadowe”, „Temperatura”, „Śnieg”, „Trendy”.
- „Pomiary bieżące” hides the station layer and draws IMGW-PIB's current measurements: hydrological stations filled by their water state, meteorological ones by their latest 10-minute precipitation, each value with its time.
- „PMAXTP” takes a point clicked on the map or typed as coordinates, POT or AMP, and shows the quantiles (KS), the upper confidence bounds (SG) and the estimation errors (RB), their CSV and JSON and a link to IMGW-PIB's own answer for the point; the map draws no layer of the PMAXTP grid.

Every analysis shows Hydrolog's result with its source (stored, or computed on request), the series version and Hydrolog's version: a card opens with the stored results of the whole record, and a person's choice (another period, under „Zalecany minimalny okres: 30 lat”, a distribution, a threshold) is computed on request. „Pobierz” gives each series as CSV, JSON or Parquet with the `obserwator series export` line that writes the same file, the station's stored analyses as JSON or CSV with the `obserwator analyses export` line (each analysis also on its own) and, for a hydrological station, „Kopiuj do Hydrologa” and „Plik przekazania” (`nogat-handoff/1`); the hand-off also sits beside the characteristic values, the flood quantiles, the low-flow periods and the rating curve. Every view shows the attribution lines and terms of the data it shows (ADR-012). The address keeps the station, its open section, the view and the PMAXTP point (`?station=…&section=…&view=current|pmaxtp&lat=…&lon=…&method=AMP`), so a copied link opens the same view.

**What it reads and writes.**

- The data root, read-only, through Obserwator's public readers: the current catalog of each provider, the current series of each dataset and the current stored analyses of each provider (ADR-016). It asks again at most once a minute whether a current version changed, so a new `store catalog`, `series build` or `analyses build` shows without a restart. Answers from the root carry a strong `ETag` with `Cache-Control: no-cache`, so a browser asks again and gets `304` while nothing changed. It never writes under the root and never downloads archives.
- IMGW-PIB's current data (water states, hydrological, meteorological and synoptic records), each fetched by the server on demand at most once per 10 minutes, one request at a time (a failed fetch keeps the last snapshot with its time and is not repeated for a minute), and PMAXTP of a point (per method and point at four decimals) for 24 hours, at most 1,000 points: in memory only. The page connects only to its own origin and the basemap's; the link to IMGW-PIB's PMAXTP answer is a navigation the person starts.
- Analyses: every number is Hydrolog's. The results `obserwator analyses build` stored in the data root are shown as they are (`list_analyses`, `read_analysis`); a station whose provider has none stored shows no analysis. A person's choice (a period, a distribution, a threshold) and the normal of the climate stripes' reference period are computed on request by Hydrolog's program (`compute_analysis`): the program of `OBSERWATOR_HYDROLOG_COMMAND`, else `hydrolog` on `PATH`, looked for once when the server starts; at most two processes at a time, 30 s each, the result kept in memory (500 results) and never written. Without the program only stored results are shown, and a person's choice is refused (`missing_dependency`) until the server starts again with one.
- Temporary files in `TMPDIR`: the series files Hydrolog's program reads for a computation on request (a directory `obserwator-analyses-*` of each computation, removed when it ends) and a Parquet download (removed at once).
- Its own files, only in `<data_dir>/obserwator` (directories `0700`, files `0600`): `stats.jsonl` and `feedback.jsonl` (section [Public deployment](#public-deployment)), the latter rewritten by the admin panel when it marks or deletes a report (section [Admin panel](#admin-panel)). That directory is also the CLI's default root: when it and the data root are one, or one holds the other (also through symbolic links), the GUI writes neither (no statistics, „Zgłoś uwagę” answers `forbidden`, the admin panel sees no report) and logs one warning. Serve a root elsewhere, or set another `data_dir`, to keep them.
- Its logs, in `<state_dir>/obserwator/logs` (section [Server logs](#server-logs)), written by `obserwator gui serve` and `obserwator.gui.serve`; an app of `create_app` mounted by a host writes none, the host keeps its own.

**Settings** (also in the table of [Configuration](#configuration)):

| Variable (`nogat.toml` key) | Default | Meaning |
|---|---|---|
| `OBSERWATOR_GUI_BASEMAP_URL` (`gui_basemap_url`) | `https://tiles.openfreemap.org/planet` | TileJSON of the basemap, drawn in the GUI's own grey style with place names in the page's language where the tiles have them; the TileJSON and its tiles must share one origin, the only remote one the CSP allows. `none` or `off`, or the variable set and empty (`.env` ignores empty values): no basemap, the borders of Poland and Czechia packaged with Obserwator, offline |
| `OBSERWATOR_GUI_BASEMAP_ATTRIBUTION` (`gui_basemap_attribution`) | `OpenFreeMap © OpenMapTiles Data from OpenStreetMap` | the basemap's credit under the map |
| `OBSERWATOR_HYDROLOG_COMMAND` (`hydrolog_command`) | unset: `hydrolog` on `PATH` | Hydrolog's program for a person's choices computed on request: a command line, split as a shell splits it, looked for once when the server starts; without a program only stored results are shown |
| `OBSERWATOR_REQUEST_LIMIT`, `OBSERWATOR_REQUEST_WINDOW` (`request_limit`, `request_window`) | `300`, `60` | the rate limit: requests of one client address in a window of seconds (Nogat DEV-15.9) |
| `OBSERWATOR_ADMIN_API_KEY`, `OBSERWATOR_ADMIN_API_KEY_FILE` (environment only) | unset | the key of the admin panel, or a file holding it, read on every admin request (section [Admin panel](#admin-panel)); unset, every admin route answers `401` |

The tables `[nogat.gui]` and `[nogat.operator]` of `nogat.toml` are no settings (no variable, no default); the GUI reads them when it starts. `[nogat.gui]` lists the GUIs of the deployment for the app menu „Aplikacje” (a registry name in lower case → its address; Nogat DEV-15.4); its `obserwator` entry is this GUI's own public address, which the regulamin and a hand-off name. `[nogat.operator]` names who runs a deployment open to others (section [Public deployment](#public-deployment)).

**Private API.** The page talks to its server at addresses relative to the page (`api/…`), with GET and HEAD, and `POST api/feedback` (Nogat DEV-15.12); the admin panel adds `PATCH` and `DELETE` of `api/admin/feedback/{id}` (section [Admin panel](#admin-panel)); any other method is `405` with `Allow`. It serves this GUI only: no `/api/v1`, no OpenAPI, no stability promise (a deviation from Nogat AGI-6.1 recorded in `CLAUDE.md`); scripts and agents use the REST API, the CLI or MCP. Every parameter is checked before the root or Hydrolog is touched, and an unknown or repeated one is `validation_error`; an error is the document `obserwator-error/1` with the registry's HTTP status, in the language of `Accept-Language` (`pl` or `en`, Polish by default), without server paths.

| Route | Answer |
|---|---|
| `api/session` | `obserwator-gui-session/1`: Obserwator's and Hydrolog's versions; the catalogs and series in use (version, SHA-256, date) and the current stored analyses of each provider (`root.analyses`: version, SHA-256, date and Hydrolog's version, `null` without them), or the root's error; the providers and their attribution lines; the basemap; `[nogat.gui]`; in a public deployment `terms` and the operator's e-mail; whether a person's choices can be computed |
| `api/texts?lang=pl\|en` | the area `gui` of the message catalog in one language |
| `api/stations`, `api/stations/{code}` | the station layer of the current catalogs (code, name, river, provider, kind, active, location, datasets, first and last year); one station's catalog properties and the series holding it with each variable's coverage |
| `api/series/{dataset}/{code}?variables=&start=&end=` | a station's series: dates, values (`null` = none) and flags |
| `api/analyses/{code}`, `api/analysis/{code}/{id}?<options>` | the stored analyses of a station (`obserwator-analysis-summary/1`, each with the options a person may change) and whether a choice can be computed; one id's result (`obserwator-analysis/1`): without options the stored one (`source: stored`), with the person's options one computed on request (`source: computed`) |
| `api/current`, `api/current/{code}` | the points of „Pomiary bieżące”; one IMGW-PIB station's current values with their times (and its synoptic report where it pairs) |
| `api/pmaxtp?latitude=&longitude=&method=POT\|AMP` | PMAXTP of a point: the KS, SG and RB tables, IMGW-PIB's address of its answer and the equivalent `pmaxtp fetch` line |
| `api/downloads/{code}`, `api/downloads/stations?provider=&kind=` | the files offered: a station's series and its stored analyses, or the stations; each format with its file name, address, command line and licence |
| `api/files/series/{dataset}/{code}?format=csv\|json\|parquet` | `export_series`: the file `obserwator series export` writes |
| `api/files/stations?format=geojson\|csv&provider=&kind=` | `export_stations`: the file `obserwator stations export` writes |
| `api/files/analyses/{code}?format=json\|csv&analysis=` | `export_analyses`: the file `obserwator analyses export` writes, every stored analysis of the station or the one `analysis` |
| `api/files/analysis/{code}/{id}?<options>` | one analysis result as a JSON file (`obserwator-analysis/1`), stored or computed with the person's options |
| `api/files/pmaxtp?latitude=&longitude=&method=&format=csv\|json` | PMAXTP of a point packed by the server: CSV, or JSON `obserwator-pmaxtp-export/1`, with PMAXTP's lines |
| `api/handoff/{code}?variable=Q\|H&resolution=daily\|annual&…` | `nogat-handoff/1` around `hydrolog-series/1`: Q or H daily over the hydrological years chosen, or the annual maxima of a flood-frequency result with its command, options and numbers |
| `api/prototype/stripes/{code}` | the climate stripes (M15), a prototype of their colour scale: `obserwator-gui-stripes/1` |
| `POST api/feedback` | „Zgłoś uwagę” (section [Public deployment](#public-deployment)) |
| `admin` (`308` to `admin/`), `admin/`, `api/admin/…` | the admin panel and its API, behind the admin key (section [Admin panel](#admin-panel)) |
| `regulamin.html` | the terms of a public deployment |
| `data/poland_border_wgs84.geojson`, `data/czechia_border_wgs84.geojson` | the packaged borders of the offline map |

Every other address is a static file of `gui/web/` (`index.html` at `/`, `instrukcja/`, `admin/`); another address under `api/` is `404`.

**Under a prefix and as Nogat's module.** The page uses relative addresses only, so the app answers at `/` or mounted under any prefix of a host, e.g. `Starlette(routes=[Mount("/m/obserwator", app=create_app(root=root))])`. Nogat's GUI platform finds it through the entry point `nogat.gui` (`obserwator = "obserwator.gui:gui_module"`): `gui_module()` returns a `GuiModule` with `name="obserwator"`, `title="Obserwator"`, `web` (the page's directory), `index="index.html"`, `sections` (`stations` „Stacje”, `current` „Pomiary bieżące”, `pmaxtp` „PMAXTP”) and `app=create_app`. `?nogat=1` in the page's address hides Obserwator's own top bar before the first paint, inside a host's shell; the views stay in the map's bar.

### Behind an authenticating proxy

The GUI has no sign-in but its admin panel's key (section [Admin panel](#admin-panel)): whoever reaches its address uses it. Bind it to `127.0.0.1` (the default) and, when others need it, put an authenticating reverse proxy in front of it, e.g. Cloudflare Access through a Cloudflare Tunnel, or a proxy with a sign-in of its own; a public deployment leaves the GUI open and protects exactly `/admin`, `/admin/*` and `/api/admin/*` (Nogat DEV-15.13). uvicorn takes the client's address from the proxy's `X-Forwarded-For` only when the connection comes from an address of `FORWARDED_ALLOW_IPS` (uvicorn's variable, default `127.0.0.1,::1`): set it to the proxy's address, so the rate limit and the visitor count see clients, not the proxy; no log holds the address. uvicorn keeps no log of its own, and no `server` header is sent.

Every answer carries:

- `Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self'; worker-src 'self'; img-src 'self' data: blob: <basemap origin>; connect-src 'self' <basemap origin>; font-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'` (the basemap's origin only when a basemap is set); the admin panel's answers (`admin`, `admin/…`, `api/admin/…`) `default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; connect-src 'self'; font-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'`, without the basemap;
- `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer` (the tile server learns no page), `Cross-Origin-Opener-Policy: same-origin`, `Cross-Origin-Resource-Policy: same-origin`, `Permissions-Policy: camera=(), microphone=(), geolocation=()`;
- `Cache-Control: no-cache` unless the answer sets another; `no-store` on every answer of the admin panel and on a `429` of the rate limit. No answer names its request id: the id stays in the server's logs (Nogat DEV-12.4).

There are no cookies, sessions or CORS headers; answers of 1 KiB or more are compressed with gzip for a client that accepts it. `curl -sI http://127.0.0.1:8060/` shows the headers.

A systemd user unit, e.g. `~/.config/systemd/user/obserwator-gui.service`, where `<checkout>` holds a virtual environment with the extras (`uv sync --locked --extra cli --extra gui`):

```ini
[Unit]
Description=Obserwator GUI

[Service]
Environment=TMPDIR=/home/<user>/data/tmp
Environment=OBSERWATOR_HYDROLOG_COMMAND=/path/to/hydrolog
Environment=OBSERWATOR_ADMIN_API_KEY_FILE=/home/<user>/.config/obserwator/admin-key
Environment=FORWARDED_ALLOW_IPS=127.0.0.1
WorkingDirectory=<checkout>
ExecStart=<checkout>/.venv/bin/obserwator gui serve --no-browser --host 127.0.0.1 --port 8060 --root <data root>
Restart=on-failure
RestartSec=5
UMask=0077

[Install]
WantedBy=default.target
```

`systemctl --user enable --now obserwator-gui.service` starts it; `systemctl --user stop obserwator-gui.service` sends `SIGTERM`, after which the GUI writes the day's statistics and exits with 0. `TMPDIR` takes the temporary series and Parquet files. The admin key lives in a file of its own of mode `0600`, made once with `install -D -m 600 /dev/null ~/.config/obserwator/admin-key` and filled with a long random line (`python3 -c "import secrets; print(secrets.token_urlsafe(32))" > ~/.config/obserwator/admin-key`); the GUI reads it on every admin request, so a new key applies without a restart. The journal gets only the lifecycle records and the errors reduced to their type, which name no request (Nogat DEV-12.7), so it needs no retention of its own; the logs themselves are in `<state_dir>/obserwator/logs`, deleted by the GUI after 14 days (section [Server logs](#server-logs)). A user's services run while the user is logged in unless lingering is on (`loginctl enable-linger <user>`).

### Public deployment

A deployment open to others names its operator in `[nogat.operator]` of `nogat.toml` (Nogat DEV-18.1, DEV-15.7) and the GUI's own public address as `obserwator` in `[nogat.gui]`:

```toml
[nogat.gui]          # the GUIs of the deployment, listed in the app menu „Aplikacje”
obserwator = "https://obserwator.example.org/"
hydrolog = "https://hydrolog.example.org/"

[nogat.operator]     # who runs the deployment (Nogat kit 0.4.0)
name = "Jan Kowalski"
email = "obserwator@example.org"
terms_effective = 2026-11-13               # a date
processor = "Example Hosting sp. z o.o."   # carries the traffic and processes IP addresses
mail_provider = "iCloud Mail (Apple)"      # holds the operator's mailbox
processor_transfer = ""                    # the processor's transfers outside the EEA
processor_cookie = ""                      # the processor's cookie against bots
mail_transfer = "Mogą być przetwarzane poza Europejskim Obszarem Gospodarczym."
```

`name`, `email`, `terms_effective`, `processor` and `mail_provider` must have a value; `processor_transfer`, `processor_cookie` and `mail_transfer` are sentences of the terms, empty or left out when they do not apply. A table with a required key missing or empty is not used. With a usable `[nogat.operator]` and the `obserwator` address the GUI is public:

- **Terms (DEV-15.7).** `regulamin.html` beside the start page: the `nogat-terms.html` of Nogat's kit 0.6.0 (regulamin 1.0, copied into `gui/web/nogat/`), filled from `[nogat.operator]`, the `obserwator` address and Obserwator's own values (name, MIT licence, source address), with the blocks of its data sources kept (IMGW-PIB, hydro.imgw.pl, PMAXTP, ČHMÚ, and OpenStreetMap with a basemap). Every view links „Regulamin” beside the attribution lines, and the app menu passes it. Without the two tables there is neither page (`404`) nor link; a template that cannot be filled is logged and not served.
- **Statement (DEV-15.8).** Beside „Regulamin”, under the strip of provider lines across every view: „Serwis jest niekomercyjny i bezpłatny, nie zawiera reklam i nie służy działalności gospodarczej operatora. Służy celom badawczym i edukacyjnym. Dane IMGW-PIB są w nim wykorzystywane do celów niezarobkowych, zgodnie z regulaminami IMGW-PIB.” (in English with „EN”).

The other rules hold in every deployment whose own directory lies apart from the data root:

- **Rate limit (DEV-15.9).** API calls and HTML pages (`/`, `index.html`, `regulamin.html`, `instrukcja/`, the admin page `admin/`) of one client address are counted in a sliding window: 300 requests in 60 s by default (`OBSERWATOR_REQUEST_LIMIT`, `OBSERWATOR_REQUEST_WINDOW`); static files (scripts, styles, images, the borders) are not counted. Over the limit the answer is `429` with `Retry-After` in seconds and `Cache-Control: no-store`: the error document `rate_limited` for an API call, the page „Zbyt wiele żądań. Spróbuj ponownie za <n> s.” for a page. The address stays in memory for the window only. „Zgłoś uwagę” has a limit of its own: 5 reports of one address in 10 minutes.
- **Logs (DEV-15.10, DEV-12.4 to DEV-12.9).** No log holds the client's address, a header but the User-Agent's class, a cookie or a body; the access log is one record per answered request, the rate limit's `429` included, in `<state_dir>/obserwator/logs`, deleted after 14 days (section [Server logs](#server-logs)). A reverse proxy keeps no log (`access_log off;`, `error_log /dev/null;` for nginx; Cloudflare's own processing is the operator's processor, named in the regulamin).
- **Daily totals (DEV-15.11).** One JSON object per UTC day and line of `<data_dir>/obserwator/stats.jsonl`, in date order, rewritten atomically every 5 minutes, at the day's change and at shutdown; a restart adds to the day's line. The requests of the admin panel (`admin`, `admin/…`, `api/admin/…`) are never counted:

  | Key | What the GUI counts |
  |---|---|
  | `date` | the UTC day, `YYYY-MM-DD` |
  | `visitors` | distinct visitors: for each request the rate limit counts (but the admin panel's), the HMAC-SHA-256 of the client's address and User-Agent under a random 32-byte salt drawn at the start and at 00:00 UTC; salt and hashes stay in memory, and a restart counts anew |
  | `page_views` | HTML pages answered with `200`: `/`, `index.html`, `regulamin.html`, `instrukcja/` |
  | `stations_opened` | station descriptions served, `api/stations/{code}`: the page asks once for each station it opens |
  | `analyses_run` | answers with a result computed on request: `api/analysis/{code}/{id}` with a person's options (also when the result is repeated from the server's memory) and the climate stripes, `api/prototype/stripes/{code}`; a stored result is not counted |
  | `downloads` | files served by `api/files/…`: series, stations, stored analyses, analysis results, PMAXTP |

- **„Zgłoś uwagę” (DEV-15.12).** The top bar's button opens a dialog with one text field of 1 to 5,000 characters, „Nie wpisuj danych osobowych.” and, in a public deployment, „Jeśli chcesz odpowiedzi, napisz na <e-mail>” with `[nogat.operator] email`. `POST api/feedback` takes `{"message": text, "context": {"view", "station", "parameters"}}` as `application/json` of at most 112 KiB from the GUI's own page only (`Sec-Fetch-Site: same-origin`, else a matching `Origin`), checks it, appends one line to `<data_dir>/obserwator/feedback.jsonl` and answers `{"id": <id>, "status": "ok"}`. A report never holds an IP address or a User-Agent:

  | Field | Value |
  |---|---|
  | `id` | ascending and never reused: the next id is kept in `feedback.next_id` beside the file, under its lock (without that file, one more than the largest id in the file) |
  | `created_at` | the UTC time of receipt, ISO 8601 with offset |
  | `message` | the text, stripped |
  | `context` | `view` (`stations`, `current` or `pmaxtp`), `station` (a code of the catalog, or `null`), `parameters` (the address's parameters, at most 50), `app_version`; at most 100 KB |
  | `is_read` | `false` |

  The operator lists, marks and deletes the reports in the admin panel (section [Admin panel](#admin-panel)) and deletes each once handled.

### Admin panel

`admin/` is the operator's page (Nogat DEV-15.13, ECO-067, ADR-020): the shell `<nogat-admin>` of Nogat's kit 0.7.0 (`nogat-admin.js`, `nogat-admin.css` in `gui/web/nogat/`) with „Zgłoszenia”, „Statystyki” and „Stan”; `admin` answers `308` to it. It has no footer, regulamin link, app menu or statistics count, carries `<meta name="robots" content="noindex">`, and every answer of the panel is `Cache-Control: no-store` under the CSP `'self'` (section [Behind an authenticating proxy](#behind-an-authenticating-proxy)). „Wróć do aplikacji” leads to the map; „Wyloguj” forgets the key.

**The key.** The page asks for the admin key once per tab and keeps it in `sessionStorage` under `obserwator/admin-key/1`; each request of the panel sends it as `X-Admin-Key`. The server compares it in constant time with `OBSERWATOR_ADMIN_API_KEY` or, without that variable, the text of the file `OBSERWATOR_ADMIN_API_KEY_FILE` names (white space around it dropped), read on every request, so a new key or key file applies at once. Both come from the environment (or `.env`) only, never from `nogat.toml` (DEV-18.4), and `obserwator config show` reports each as `present` or `missing`; no key is generated and none is logged. A refusal is `401` with the error document `unauthorized` and `details.reason` `admin_key_not_configured` (neither variable gives a key), `admin_key_missing` (no header) or `admin_key_invalid`. The admin key is none of the REST API keys of `obserwator admin` (`api_keys.json`), which the GUI never reads, and not the store write token of `obserwator server`.

| Route | Answer |
|---|---|
| `GET api/admin/feedback?limit=&offset=` | `{items, total, unread_count}`: the reports of `feedback.jsonl`, newest first; `limit` 1 to 200 (default 50), `offset` from 0 |
| `PATCH api/admin/feedback/{id}` with `{"is_read": true\|false}` as `application/json` | the report as now stored |
| `DELETE api/admin/feedback/{id}` | `{"status": "deleted"}` |
| `GET api/admin/stats?from=&to=` | `{days, totals}`: the lines of `stats.jsonl` between two UTC days (`YYYY-MM-DD`, both included; by default the last 30 days up to today) in date order, today's as counted so far; `totals` sums every number but `visitors` |
| `GET api/admin/status` | `{app, version, started_at, uptime_s, data_dir, disk: {free_bytes, total_bytes}, checks: [{name, status, detail}]}`: `data_dir` is the GUI's own directory `<data_dir>/obserwator`, `disk` the space of its disk |

An id no report has is `404 not_found`; any other address under `api/admin/` is `404` once the key is checked. Marking or deleting rewrites `feedback.jsonl` atomically under the lock `POST api/feedback` takes (`flock`): the new text goes to a temporary file beside it, synced and renamed over it, so a report that waited for the lock is appended to the new file and none is lost; lines that hold no report stay as they are. Ids are never reused: `feedback.next_id` beside the file keeps the next one under the same lock, so deleting the newest report does not free its number. The panel's requests count against the rate limit, not in the daily totals.

The checks of „Stan”, each `ok`, `warning` or `failed` with a detail in the page's language:

| Check | `ok` | `warning` | `failed` |
|---|---|---|---|
| `data_root_marker` | the data root holds `obserwator-data.json`; the detail names the root and the stations of its current catalogs | — | no marker, or the root cannot be read: the map shows no station |
| `stored_analyses` | every provider with a current catalog has stored analyses (ADR-016); the detail names each version and its Hydrolog | none stored, or none of a provider with a catalog: its stations show no analysis | the root cannot be read |
| `hydrolog_command` | Hydrolog's program answers `config show` now; the detail names its version | the server started without the program (`OBSERWATOR_HYDROLOG_COMMAND`, else `hydrolog` on `PATH`): only stored results are shown | the program does not answer: computations on request fail |

## AI agents: language, command effects and the MCP server

**Language.** Machine output is in English (AGI-9.2): the envelope, the error `message` and `hint`, notices, plan lines, `commands list|schema|guide` descriptions (`command_schema()`, `list_commands()`, `agent_guide()`), `AGENTS.md`, `llms.txt`, the OpenAPI document, REST responses without an `Accept-Language` header and the MCP server. Polish catalog texts (command descriptions, option help, rules, groups, error and dataset titles) are available on explicit request: `lang="pl"`, `--lang pl`, `Accept-Language: pl`. `OBSERWATOR_LANG` (default `pl`) applies only to human-facing CLI text: help, progress lines, the summary printed without `--json` and the readable error line, all of which `--lang` overrides per call; the last error line and the envelope of `--json` are always in English, and with `--json` the `--lang` of `commands list|schema` defaults to English, not to `OBSERWATOR_LANG`. An agent decides by `code`, `status` and JSON fields; the language does not change the contract.

**Command effects.** `effects` of `command_schema` (`read_only`, `writes`: `none`, `add` — only new files and versions, `replace` — may replace a user file; `network`, `idempotent`, `destructive`) and the options' `writes` (e.g. `output`, `force`, `plan` in `store check`) tell what a command will do before it runs; every writing command has a plan (`--check`, `?check=true`, `check: true`), named by `check`.

### MCP server

`obserwator mcp` (the `obserwator[mcp]` extra: CLI + the official SDK `mcp>=2.3,<3`) is an MCP server on standard input and output. Every catalog command is a tool named by its catalog `operation_id` (`obserwator_` + command name: `obserwator_store_sync`, `obserwator_current_hydro_states`, …; also the REST `operationId`) with an input schema generated from the catalog options and the annotations `title`, `readOnlyHint`, `destructiveHint`, `idempotentHint`, `openWorldHint`; the arguments are the command options, and the only validator is `validate_command`. The `obserwator_commands_list` tool returns the list of commands, `obserwator_commands_schema` — the description of one command (`obserwator-commands/1`). Client configuration (e.g. `mcpServers` in the settings file):

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

- Without a system-wide installation: `"command": "uvx", "args": ["--from", "obserwator[mcp]", "obserwator", "mcp"]`.
- Writes: `"args": ["mcp", "--allow-writes", "--allow-dir", "/dane/obserwator", "--allow-dir", "/dane/obserwator-raw"]` (or `OBSERWATOR_MCP_ALLOW_WRITES=true`; `--allow-dir` can be repeated). Without `--allow-writes` the server does not write: writing commands have the `check` argument fixed to `true` and return an `obserwator-plan/1` plan, and writing options (`output_dir`, `output`, `force`, `plan`) are unavailable (an attempt → `forbidden`, `details.reason="writes_disabled"`). With the flag, `check` defaults to `true` and writing requires `check: false` — the user decides about writes in the configuration, not the model. Writing without `--allow-dir` is `forbidden` (`no_allowed_dir`), and a target (`root`, `raw_root`, `output_dir`, `output` or a default root) outside these directories is `forbidden` (`outside_allowed_dirs`).
- Language: the MCP server always speaks English (tool descriptions, instructions, error documents; AGI-9.2), regardless of `OBSERWATOR_LANG`. There is no `--lang` option; an agent gets Polish text only on explicit request (the `lang: "pl"` argument of the `obserwator_commands_list`, `obserwator_commands_schema`, `obserwator_commands_guide` tools).
- `root` as in the CLI: a tool argument, else the default root of the command's kind — the data root (`OBSERWATOR_ROOT`, `[obserwator] root` or `<data_dir>/obserwator`) or, for the commands of the raw root, the raw root (`OBSERWATOR_RAW_ROOT`, `[obserwator] raw_root` or `<data_dir>/obserwator-raw`); `raw_root` of `obserwator_series_build` and `obserwator_store_catalog` defaults to the raw root. With `--allow-dir` every root a call uses, a default root included, must lie within one of the directories; relative paths are resolved from the server's working directory, and the server instructions give the working directory and both default roots.

Tool result: `structuredContent` = the `obserwator-result/1` envelope (the same bytes as CLI stdout with `--json`, also as text), `isError=false` also for `partial` and `failed`. Error: `isError=true` and the `obserwator-error/1` document of the CLI error line (with the tool's `command`, in English) as `structuredContent` and as text. List commands without `limit` return a page of 50 items (at most `OBSERWATOR_API_MAX_LIMIT`; next pages with `cursor` = `page.next_cursor`); streams (`store export`, `series export`, `analyses export`, `commands guide` without `output`) — text up to 256 KiB with the envelope `result={schema: "obserwator-stream/1", format, bytes, lines}`, larger → `validation_error` (narrow the selection, read page by page with `series read` or write a file with the `output` option; writing requires `--allow-writes` and an `--allow-dir` directory). Progress is sent as `notifications/progress`; cancelling the request stops work between files. The list of 35 tools with descriptions is about 53 KB of schemas (read-only mode).

**MCP over HTTP.** `obserwator server` exposes `/mcp` (Streamable HTTP) with `OBSERWATOR_MCP_ENABLED=true`: the tools correspond to the 33 REST routes and are called as REST requests in the same process (with `Accept-Language: en`), so the server rules apply (the roots from `OBSERWATOR_ROOT` and `OBSERWATOR_RAW_ROOT`, `version` relative to the command's root, `OBSERWATOR_API_MAX_LIMIT`, hiding server directories); POST always with `?check=true` — over HTTP only reading and planning. The tools are in English, as in `obserwator mcp`; `OBSERWATOR_LANG` does not affect them. Allowed `Host` headers are listed in `OBSERWATOR_MCP_ALLOWED_HOSTS` (default `127.0.0.1,localhost`); behind `nginx` add the public host name.

```bash
OBSERWATOR_MCP_ENABLED=true OBSERWATOR_ROOT=/srv/obserwator OBSERWATOR_RAW_ROOT=/srv/obserwator-raw obserwator server  # → http://127.0.0.1:8000/mcp
```

## Source data structure

### IMGW-PIB hydrological data (1951-present)
- `dobowe`: monthly files (before 2023) or yearly files (from 2023)
- `miesieczne`: yearly files
- `polroczne_i_roczne`: yearly files with the T, Q, H parameters

> **CSV format:** IMGW archive files are inconsistent between years in three respects:
> - **separator** — most years use a comma with quotes, some (e.g. 2023) a semicolon, and some have an extra header row;
> - **encoding** — the standard is CP1250, but e.g. `codz_2023.zip` is UTF-8 with a BOM;
> - **quotes** — the 2024 daily and monthly files have whole rows wrapped in quotes (with doubled quotes inside).
>
> The parsers (`parse_zip_file`) **detect the separator, encoding and quoting variant automatically, per file**. Verified on real data for the years 2019-2024 (all intervals).

### IMGW-PIB meteorological data (1950-present)
- **up to 2000**: 5-year folders; **from 2001**: yearly folders
- **miesieczne**: one file per folder (`{folder}_m_{k|o|s}.zip`)
- **dobowe/terminowe klimat and opad**: yearly files (up to 2000) or monthly files (from 2001)
- **dobowe/terminowe synop**: per-station files (`{folder}_{code}_s.zip`) — the registry does not generate them (`validation_error`, `details.reason=per_station`; use `meteo/miesieczne/synop`)
- **terminowe opad**: the dataset does not exist on the IMGW server (`details.reason=not_published`)
- The folder grids start differently: klimat from `1951_1955`, opad from `1950_1955`, synop from `1960_1965` (structure verified on the IMGW servers, 2026-07-05)

### ČHMÚ data (opendata.chmi.cz)
- **daily hydro** (`cz.chmi.hydro_daily`): `hydrology/historical/data/daily/H_<WIGOS>_DQ_<year>.json` — one JSON file per station and calendar year (the oldest from 1887); series `HD`, `QD`, `TD` → H [cm], Q [m3/s], T [°C] (suspended sediment `PD` skipped); no measurement = no row
- **daily meteo** (`cz.chmi.meteo_daily`): `meteorology/climate/historical_csv/data/daily/precipitation/dly-<WIGOS>-SRA.csv` and `…/temperature/dly-<WIGOS>-{T,TMA,TMI}.csv` — the whole station history in the element file; P = total from the morning observation (06:00Z) of day D to the morning of D+1, Tmean = (T06 + T13 + 2·T20)/4, Tmax and Tmin — extremes of the period (D−1 20:00, D 20:00] UTC (descriptions in the dataset's `variable_notes`); `QUALITY` (0–5) and `FLAG` (e.g. `T` — trace of precipitation) kept
- **station lists**: `hydrology/historical/metadata/meta1.json` and `meteorology/climate/historical/metadata/meta1.json` (JSON with a `zaznamID`/`datumVytvoreni` envelope that changes with every generation)
- **station metadata** (`cz.chmi.hydro_now`, `cz.chmi.meteo_now`): `hydrology/now/metadata/meta1.json` and `meta3.json`, the newest `meteorology/climate/now/metadata/meta1-<YYYYMMDD>.json` — station metadata only (names, rivers, coordinates, SPA thresholds), stored verbatim for the catalog; the measurements of `now/data/` are never read
- **inventory**: server directory listings (name, time to the minute, size) — one GET of the hydro listing (about 5.3 MB) replaces a HEAD of each of about 39 thousand files; the server keeps only the latest version of a file, and a year enters `historical` only with the annual publication (hydro 2025: 2026-05-21)
- Out of scope: `now`/`recent` measurements, hourly and 10-minute data, CAP warnings; ČHMÚ does not publish a PMAXTP equivalent

### Station data sources

`store sync --datasets` downloads them into the raw root; `store catalog` builds the catalogs in the data root from the stored versions, offline (ADR-015, ADR-017).

- **IMGW-PIB hydro and meteo station lists** (`pl.imgw.hydro_stations`, `pl.imgw.meteo_stations`): CSV from `danepubliczne.imgw.pl` (CP1250 encoding)
- **IMGW-PIB station coordinates** (`pl.imgw.hydro_now`, `pl.imgw.meteo_now`): the current-data API `danepubliczne.imgw.pl/api/data/hydro` and `/meteo`; operational data are never archived, so the store keeps a derived file with each station's code, name, river and coordinates only (sidecar `extra.kept_fields`), never the measurements, their times or the warning and alarm levels (ADR-015 D5)
- **IMGW-PIB station details** (`pl.imgw.hydro_details`, optional, ADR-021): the station page of hydro.imgw.pl, `hydro-back.imgw.pl/station/hydro/status?id=<code>`, asked once per station of the map `hydro-back.imgw.pl/map/stations/hydrologic?onlyMainStations=false`, in map order and one request at a time, with the `User-Agent` `Obserwator/<version>` and the `Referer` `https://hydro.imgw.pl/` the backend requires; an unknown code (answer `null`) is skipped, any HTTP error fails the item and writes nothing (no retries). The store keeps one derived file, `archives/versions/station/hydro/status/<label>_<sha8>/status`: a JSON list of the stations sorted by `id` with only the dotted `kept_fields` (`id`, `properties.{maximumStateValue, maximumStateDate, minimumStateValue, minimumStateDate, district, waterGaugeZeroOrdinate, waterGaugeZeroOrdinateReferrenceSystem, yearOfEstablishment}`, `status.{riverCourseKm, catchmentArea, province, alarmValue, warningValue}`), never the water states, trends, notes or data clauses. There is no freshness signal: `store check` gives `unverifiable` and `store sync` always downloads (the same details give the same bytes, so `unchanged`). The sidecar's license and the products with the details carry the lines S, P and RH (the hydro.imgw.pl terms)
- **Coordinates for the map**: API `hydro-back.imgw.pl/map/stations/hydrologic` (900+ stations with water state), read live only
- **ČHMÚ stations** (`cz.chmi.*_stations`, `cz.chmi.*_now`): JSON metadata from `opendata.chmi.cz` — current (`hydrology/now/metadata/meta1.json`, `meta3.json`, the latest `meteorology/climate/now/metadata/meta1-<YYYYMMDD>.json`) and historical station lists; WGS84 coordinates, SPA thresholds of hydro stations

**Properties of an IMGW-PIB catalog feature from the station details** (`stations.geojson`, ADR-021; in this order after `active`, with `elevation_m`, which keeps its source, between `catchment_area_km2` and `province`): `established_year` (integer), `gauge_zero_m` (m in its datum; 0 → null), `gauge_zero_datum` (only with a gauge zero: `EVRF2007`, once `Kronsztad86`), `river_km`, `catchment_area_km2` (0 → null: gauges on the sea and its lagoons), `province`, `district`, `warning_level_cm`, `alarm_level_cm`, `absolute_min_level_cm`, `absolute_min_level_dates`, `absolute_max_level_cm`, `absolute_max_level_dates` and `details_source` (`"hydro_details"` or null). Levels are in cm above the gauge zero; the dates are free text as published (one or more days, ranges, months, sometimes a word), white space collapsed. Example, Kłodzko `150160180`: gauge zero 281.617 `EVRF2007`, river km 130.04, catchment 1082.27 km², established 1884, `dolnośląskie` / `kłodzki`, warning 160, alarm 240, absolute minimum 28 (`1950-08-31`), maximum 890 (`1997-07-08`). Meteorological stations and hydrological stations without details have every one of them null (`gauge_zero_m`, `river_km` and `established_year` too: the current-data API fields were never kept, ADR-015 D5); ČHMÚ features are unchanged and have none of the new keys. The details add no station and no location. They are optional: without them the catalog is built anyway, its sidecar lists `{"source": "hydro_details", "url": null, "file": null, "fetched_at": null, "count": 0, "sha256": null, "available": false}` among its `sources` and an `info` notice `source_missing` names the `store sync --datasets pl.imgw.hydro_details` that stores them; with them the entry is the stored version's record with `count` (stations with details) and `available: true`. The IMGW-PIB build reports 7 progress steps (step 5 the details, `done` or `missing`); `store catalog --check` has one more action for them: `current` (also when neither the raw root nor the catalog has them), `newer` (they appeared, changed or are gone) or `missing` (no catalog yet). The catalog, `stations export` and the envelope of `store catalog` add the line RH (the hydro.imgw.pl terms) only when a feature has details.

## Docker

```bash
cd docker
docker compose up -d

# With the MCP server at /mcp (read and plan only); behind nginx add the public host name
OBSERWATOR_MCP_ENABLED=true OBSERWATOR_MCP_ALLOWED_HOSTS=dane.example.pl docker compose up -d
```

The image (`python:3.12-slim`) installs `.[api,mcp]` and runs a single uvicorn process (MCP sessions live in the process) with `--no-access-log --log-level warning`. `docker-compose.yml` passes `OBSERWATOR_MCP_ENABLED` (default `false`) and `OBSERWATOR_MCP_ALLOWED_HOSTS` (default `127.0.0.1,localhost`) from the environment and `NOGAT_STATE_DIR=/state`, mounts the host's `${NOGAT_STATE_DIR:-../state}/obserwator` (relative to `docker/`) as `/state/obserwator`, where the server writes its logs (section [Server logs](#server-logs); the directory must be writable by the image's `appuser`, UID 1000: `mkdir -p <state_dir>/obserwator && chown 1000 <state_dir>/obserwator`), and gives both containers the logging driver `local` (`max-size: "1m"`, `max-file: "3"`). `nginx.conf` has `location = /mcp` with a request limit and no buffering, keeps no log (`access_log off;`, `error_log /dev/null;`, so a rejection of `limit_req` is not logged either) and passes no `X-Request-ID`.

**Migrating a container.** A container created before 3.0.0's logging change keeps Docker's default `json-file` log: uncapped, with uvicorn's access lines and the client addresses in them (on the VPS: `imgwtools-api`). Docker deletes that file with the container: rebuild it from this code (`docker compose up -d --build` in `docker/`) or remove it (`docker rm -f <name>`); both need the `docker` group.

## Server logs

`obserwator server` and `obserwator gui serve` keep the logs of Nogat DEV-12.4 to DEV-12.9 with Nogat's reference module, copied byte for byte as `obserwator.nogat_logging`. Every record is one JSON object per line, valid against `schemas/nogat/record-1.schema.json` (`nogat-log/1`): `time` (UTC), `level`, `app` (`obserwator`), `version`, `kind`, `request_id` (16 random hexadecimal digits, never sent to the client), and by kind:

| File | One record per | Keys |
|---|---|---|
| `access-YYYY-MM-DD.jsonl` | answered HTTP request | `method`, `path` (with the query; the values of free-text, personal and secret parameters such as `q`, `query`, `name`, `email`, `token`, `key` dropped, an IP address written `[ip]`), `status`, `bytes`, `duration_ms`, `agent` (`browser`, `bot`, `script` or `none`: the class of the User-Agent, never the header) |
| `app-YYYY-MM-DD.jsonl` | warning, error or exception of the server | `event` (a stable code or the logger's name), `message`, `error` (`type`, `message`, `stack`, or `null`) |
| `lifecycle-YYYY-MM-DD.jsonl` | start, stop, deletion of old files | `event` (`start`, `stop`, `prune`), `message`, and in `start` the `settings` (the GUI: `url`, `root`, `public`, `own_files`, `basemap`, `request_limit`, `request_window`; the REST server: `host`, `port`, `env`, `root`, `raw_root`, `store_writes_enabled`, `mcp`) |

- **Where.** `<state_dir>/obserwator/logs`, `state_dir` resolved as every setting (`OBSERWATOR_STATE_DIR`, `.env`, `NOGAT_STATE_DIR`, `[obserwator]`/`[nogat] state_dir`, default the user state directory of `nogat`, `~/.local/state/nogat` on Linux), by the UTC date of `time`. In a container `NOGAT_STATE_DIR` names the directory where the host's `<state_dir>/obserwator` is mounted ([Docker](#docker)).
- **What is not logged.** No client address, cookie, header, request body or uploaded file name; static content the same for every client answered below `400`: the GUI's page files (`css/`, `src/`, `vendor/`, `nogat/`, `theme-init.js`), its guide `instrukcja/`, the packaged borders `data/` and `regulamin.html`; the REST server's `/docs`, `/redoc`, `/openapi.json`, `/llms.txt`, `/health`, `/api/v1` and `/api/v1/commands/schema`.
- **Deletion.** The server deletes a file once its date is 14 days old, at start and at each 00:00 UTC; no cron, journald or Docker setting is needed.
- **Standard output and error** get only the lifecycle records and the `error` and `critical` app records reduced to their `event` and error `type` (no request id, no message), whatever else is configured: the journal or a container's log names no request. No setting changes a level: `OBSERWATOR_LOG_LEVEL` is gone (it configured nothing; a value left in the environment is ignored).
- **Use** is counted only by the GUI's daily totals in `<data_dir>/obserwator/stats.jsonl` (DEV-15.11), never from the logs.

The operator reads the logs with `jq` (not installed on every host: `apt install jq` as root once, or its static release binary in `~/.local/bin`): every record but the ordinary requests, in time order:

```bash
jq -cs 'sort_by(.time)[] | select(.kind != "access" or .status >= 500)' ~/.local/state/nogat/obserwator/logs/*.jsonl
```

**Migration from earlier 3.0.0 development builds.** The GUI's access log moves from `<data_dir>/obserwator/logs/access-YYYY-MM-DD.jsonl` to `<state_dir>/obserwator/logs/` in the format above: `size` is `bytes`, `user_agent` is `agent` (a class), and answers carry no `X-Request-Id`. The GUI deletes the old directory's files no more; remove `<data_dir>/obserwator/logs/` by hand. A unit that runs uvicorn directly (such as the mockup behind `obserwator-public.service` until the GUI replaces it) keeps `--no-access-log` and adds `--log-level warning`.

## Configuration

A setting comes from the first of: a command-line option, the `OBSERWATOR_<KEY>` variable, the same key in the `.env` file of the working directory, the `NOGAT_<KEY>` variable (only the shared keys `data_dir`, `cache_dir`, `state_dir`, `lang`), the `[obserwator]` and `[nogat]` sections of the `nogat.toml` file (in this order; `[nogat]` holds only shared keys), the default value. `nogat.toml` lies in the user configuration directory (`platformdirs.user_config_path("nogat")`, e.g. `~/.config/nogat/nogat.toml`) or at the path from `NOGAT_CONFIG`; a missing file is not an error, an unreadable or invalid file ends every `obserwator` call with a `validation_error`. Credentials (`OBSERWATOR_STORE_WRITE_TOKEN`) come only from the environment, never from the file. The tool writes nothing into the working directory: the roots of the store lie under `data_dir` (`<data_dir>/obserwator-raw` and `<data_dir>/obserwator`), the cache under `cache_dir` (`<cache_dir>/obserwator`) and the servers' logs under `state_dir` (`<state_dir>/obserwator/logs`).

```toml
[nogat]   # keys shared by all tools of the ecosystem
data_dir = "/srv/nogat/dane"
lang = "pl"

[obserwator]  # any setting from the table below: variable name without OBSERWATOR_, in lower case
root = "/srv/nogat/dane/obserwator"
raw_root = "/srv/nogat/dane/obserwator-raw"
api_max_limit = 500
```

| Variable | Key in `nogat.toml` | Default | Meaning |
|---|---|---|---|
| `OBSERWATOR_DATA_DIR` (also `NOGAT_DATA_DIR`) | `data_dir` | `nogat` user data directory (`~/.local/share/nogat`) | parent directory of the roots (`<data_dir>/obserwator-raw`, `<data_dir>/obserwator`), of the REST API keys and of the GUI's `stats.jsonl` and `feedback.jsonl`; **before 3.0.0 `IMGW_DATA_DIR` meant the reference data** (see `OBSERWATOR_REFERENCE_DIR`) |
| `OBSERWATOR_CACHE_DIR` (also `NOGAT_CACHE_DIR`) | `cache_dir` | `nogat` cache directory (`~/.cache/nogat`) | cache (`<cache_dir>/obserwator`) |
| `OBSERWATOR_STATE_DIR` (also `NOGAT_STATE_DIR`) | `state_dir` | `nogat` user state directory (`~/.local/state/nogat`) | state kept between runs: the servers' logs in `<state_dir>/obserwator/logs` (section [Server logs](#server-logs)) |
| `OBSERWATOR_REFERENCE_DIR` | `reference_dir` | `<cache_dir>/obserwator/reference` | IMGW-PIB reference data (`python -m obserwator.reference_data`) |
| `OBSERWATOR_LANG` (also `NOGAT_LANG`) | `lang` | `pl` | `pl` or `en`: CLI help, progress lines, the summary without `--json` and the default `--lang` (the last error line and the envelope of `--json` are always in English; Polish descriptions in it via `--lang pl`) |
| `OBSERWATOR_ROOT` | `root` | `<data_dir>/obserwator` | the data root (series, station catalogs, analyses; ADR-017): `--root` of its commands and of `store info\|scan` for the CLI, the library and `obserwator mcp`; the data root of the REST server (without it the routes of those commands answer 503, never the default directory) |
| `OBSERWATOR_RAW_ROOT` | `raw_root` | `<data_dir>/obserwator-raw` | the raw root (archives, station sources, PMAXTP cells; ADR-017): `--root` of `datasets download`, `store init\|check\|sync\|export` and `pmaxtp check\|sync\|read` and `--raw-root` of `series build` and `store catalog`, for the CLI, the library and `obserwator mcp`; the raw root of the REST server (without it the routes of those commands answer 503, never the default directory) |
| `OBSERWATOR_STORE_WRITES_ENABLED` | `store_writes_enabled` | `false` | writes over REST (POST without `?check=true`) |
| `OBSERWATOR_STORE_WRITE_TOKEN` | — (environment only) | none | write token in the `X-API-Key` header |
| `OBSERWATOR_USER_LOCATIONS_DIR` | `user_locations_dir` | none | directory of user location files for REST routes |
| `OBSERWATOR_API_MAX_LIMIT` | `api_max_limit` | `1000` | default and maximum `limit` of REST and MCP list commands |
| `OBSERWATOR_API_KEYS_FILE` | `api_keys_file` | `<data_dir>/obserwator/api_keys.json` | the file of the REST API keys of `obserwator admin` |
| `OBSERWATOR_RATE_LIMIT` | `rate_limit` | `100` | requests per hour (0 = no limit) |
| `OBSERWATOR_ENV` | `env` | `development` | `development` or `production` |
| `OBSERWATOR_HOST`, `OBSERWATOR_PORT` | `host`, `port` | `0.0.0.0`, `8000` | address and port of `obserwator server` |
| `OBSERWATOR_MCP_ENABLED` | `mcp_enabled` | `false` | `/mcp` in `obserwator server` (read and plan only) |
| `OBSERWATOR_MCP_ALLOWED_HOSTS` | `mcp_allowed_hosts` | `127.0.0.1,localhost` | `Host` names served by `/mcp` |
| `OBSERWATOR_MCP_ALLOW_WRITES` | `mcp_allow_writes` | `false` | `obserwator mcp` in write mode (`--allow-writes`, `--no-allow-writes`) |
| `OBSERWATOR_GUI_BASEMAP_URL` | `gui_basemap_url` | `https://tiles.openfreemap.org/planet` | TileJSON of the GUI's basemap; `none` or `off` (or the variable set and empty): the packaged borders, offline (section [GUI](#gui)) |
| `OBSERWATOR_GUI_BASEMAP_ATTRIBUTION` | `gui_basemap_attribution` | `OpenFreeMap © OpenMapTiles Data from OpenStreetMap` | the basemap's credit line |
| `OBSERWATOR_HYDROLOG_COMMAND` | `hydrolog_command` | none (`hydrolog` on `PATH`) | Hydrolog's program for `analyses build`, `compute_analysis` (ADR-016) and the GUI's choices computed on request (looked for once when it starts): a command line split as a shell splits it, e.g. `/opt/hydrolog/.venv/bin/hydrolog`; no command option replaces it |
| `OBSERWATOR_REQUEST_LIMIT`, `OBSERWATOR_REQUEST_WINDOW` | `request_limit`, `request_window` | `300`, `60` | the GUI's rate limit: requests of one client address in seconds |
| `OBSERWATOR_ADMIN_API_KEY` | — (environment only) | none | the key of the GUI's admin panel in the `X-Admin-Key` header (section [Admin panel](#admin-panel)) |
| `OBSERWATOR_ADMIN_API_KEY_FILE` | — (environment only) | none | a file holding that key, used without `OBSERWATOR_ADMIN_API_KEY`; both read on every admin request |

`[nogat.gui]` (GUI addresses, Nogat DEV-15.4) and `[nogat.operator]` (the operator of a public deployment, DEV-15.7) are tables of `[nogat]` in `nogat.toml` only, with no variable and no default; section [GUI](#gui).

`obserwator config show --json` prints one `obserwator-config/1` document: every key with its value and source (`default`, `env`, `dotenv`, `file` and the variable or table name), every credential variable as `present` or `missing` (without the value) and both roots, `store` the data root and `raw_store` the raw root, each with its source, whether it exists and its size (hard-linked files counted once); without `--json` the same description as text (the lines "Data root" and "Raw root").

**Store backup.** The raw root is the only place holding archive versions that IMGW-PIB or ČHMÚ have removed from their server, so they cannot be downloaded again. A backup of a root must preserve hard links (`rsync -aH`; on Windows a tool that preserves links, not Explorer or `robocopy`) or use an export (`obserwator store export`, `obserwator series export`); a copy without links multiplies the size of the root.

## Versioned store (optional)

The store is two plain directories, each with a marker of its own (ADR-017). The **raw root** keeps the downloaded sources: the archives with their sidecars, the station sources of the catalogs and the PMAXTP cells (marker `obserwator-store.json`). The **data root** keeps what Obserwator builds from them: the series, the station catalogs and the analyses (marker `obserwator-data.json`). Downloads (`datasets download`, `store sync`, `pmaxtp sync`) write only the raw root, and `store check|export` and `pmaxtp check|read` read it; `series build` and `store catalog` read the raw root given as `--raw-root` (`raw_root=`), never write it, and write the data root; `analyses build`, `stations export`, `stations find --source store` and the readers of series, catalogs and analyses use the data root; `store info` and `store scan` describe a root of either kind (by default the data root). Without an option the raw root lies in `<data_dir>/obserwator-raw` and the data root in `<data_dir>/obserwator` (DEV-19.2; `OBSERWATOR_RAW_ROOT` and `OBSERWATOR_ROOT`, section "Configuration"); `init_store(root)` creates a raw root and `init_store(root, kind="data")` a data root. There is no database; both roots can be read offline from a local disk or a network share, also when they are read-only, and each holds the data of both providers. One root never lies in the other, a directory with both markers is refused, and a function given a root of the other kind ends with `store_unavailable` (`details.reason="wrong_root"`, `details.kind` the kind it needs). In Nogat the raw root is Archiwista's and the data root is the one Obserwator serves (Nogat plan `2026-11-12-station-data-and-analyses.md`, D2). Details: `docs/DECISIONS.md` (ADR-001, ADR-003, ADR-017), `docs/superpowers/specs/2026-10-17-versioned-store-design.md` and `2026-10-18-chmi-provider-design.md`.

### Directory layout

```text
<raw root>/obserwator-store.json                        # obserwator-store/1 marker
  archives/versions/<server path>/<stem>/<label>_<sha8>/<file>[.meta.json]
  archives/versions/<server path>/<stem>/observations/<date>_<sha8>.json   # observation register (ČHMÚ)
  pmaxtp/versions/<POT|AMP>/<indX>_<indY>/<label>_<sha8>/cell.json[.meta.json]
  .incoming/                                            # staging; never a version

<data root>/obserwator-data.json                        # obserwator-data/1 marker
  series/versions/<slug>/<label>_<sha8>/series.json[.meta.json] + stations/<code>.parquet
  stations/versions/<label>_<sha8>/stations.geojson[.meta.json]                 # IMGW-PIB catalog
  stations/versions/chmi_stations/<label>_<sha8>/stations.geojson[.meta.json]   # ČHMÚ catalog
  analyses/versions/<pl.imgw|cz.chmi>/<label>_<sha8>/analyses.json[.meta.json] + stations/<code>.json + stations/<code>/<id>.json   # Hydrolog's analyses (ADR-016)
  .incoming/                                            # staging; never a version
```

Versions are immutable and append-only: no overwriting, no permanent links and no `latest` path. The current version is computed by `current_version(root, slot=...)`, and the slot decides the kind of root it needs; slots of the raw root: `archive:<key>:<file>` (e.g. `archive:pl.imgw.hydro_daily:2024/codz_2024.zip`, `archive:cz.chmi.hydro_daily:H_0-203-1-001000_DQ_2025.json`), `pmaxtp:pl.imgw.pmaxtp:<METHOD>/<indX>_<indY>`; slots of the data root: `series:<key>`, `catalog:pl.imgw.stations`, `catalog:cz.chmi.stations`, `analyses:pl.imgw.analyses`, `analyses:cz.chmi.analyses`. Every main file has a `*.meta.json` sidecar (`obserwator-meta/1`) with SHA-256, size, request, HTTP headers and the provider license; sidecars of ČHMÚ archives with a canonical form also have `content_sha256`. A path in a sidecar is relative to its own root, as its first directory tells: a series or catalog names its sources under `archives/` of the raw root and the series a catalog read under `series/` of the data root. The `observations/` directory (`obserwator-observation/1`) records a new source signal when the downloaded bytes have the same content as the current version — it is not a version; `store scan --root <raw root> --kind observation` shows it as publication history.

A write moves version files from the `.incoming/` staging area with hard links that never replace an existing file; the main file's sidecar is linked last and only it commits the version (Kartograf's model, hence the hard-link requirement — see "Installation"). A version directory without a sidecar is an interrupted publication (e.g. after a write error, Ctrl+C or a killed process): reads and writes skip it, `store scan` shows it as a `missing_sidecar` problem, and the next write of the same content under the same label completes it. The station catalog label is the build date, and for PMAXTP and an archive without `Last-Modified` — the download date (UTC): an interrupted publication that a retry with the same content and label will not complete (e.g. a catalog rebuilt the next day) must be removed manually — the whole `<label>_<sha8>/` directory without a sidecar — while no write to the root is in progress.

### Splitting a store

A store written before ADR-017 holds the trees of both kinds under the marker `obserwator-store.json`. Obserwator refuses it as a data root (`store_unavailable`, `details.reason="wrong_root"`) and scans it as a raw root whose `series/`, `stations/` and `analyses/` are `unknown_entry` problems. It is split once into a raw root and a data root by a copy with hard links; no command converts it and no alias reads it as both kinds. A store at the default `<data_dir>/obserwator` (e.g. `~/.local/share/nogat/obserwator`) is moved aside first, because that path is now the default data root (`mv ~/.local/share/nogat/obserwator ~/.local/share/nogat/obserwator-old`); with the defaults RAW is then `<data_dir>/obserwator-raw` and DATA `<data_dir>/obserwator`. With a `cp` that makes hard links (`cp -al`, GNU coreutils), for an old store `OLD`:

```bash
mkdir RAW DATA
cp -al OLD/archives OLD/pmaxtp RAW/                   # name only the trees OLD has
cp -al OLD/series OLD/stations OLD/analyses DATA/
obserwator store init --root RAW                      # verifies the layout, writes obserwator-store.json
obserwator store init --kind data --root DATA         # verifies the layout, writes obserwator-data.json
obserwator store scan --root RAW --kind problem       # lists nothing
obserwator store scan --root DATA --kind problem      # lists nothing
```

Without such a `cp` (on Windows, for example) Python makes the same links; the same `store init` and `store scan` calls follow (or `init_store("RAW")` and `init_store("DATA", kind="data")`):

```python
import os
import shutil
from pathlib import Path

old, raw, data = Path("OLD"), Path("RAW"), Path("DATA")
for target, trees in ((raw, ("archives", "pmaxtp")), (data, ("series", "stations", "analyses"))):
    target.mkdir()
    for tree in trees:
        if (old / tree).is_dir():
            shutil.copytree(old / tree, target / tree, copy_function=os.link)
```

- `store init` verifies a root before it writes its marker: every sidecar of its trees is `obserwator-meta/1` and nothing but those trees, `.incoming/` and `api_keys.json` lies in the root (a tree of the other kind counts as foreign: `data_error`, `details.reason="invalid_layout"`).
- Hard links are safe: a version never changes after its publication and nothing writes a file in place, so the old store and the new roots share their files without a write to one reaching another, and the copy takes almost no space. A hard link cannot cross file systems, so RAW and DATA lie on the file system of OLD; once both roots scan clean, OLD can be removed.
- The REST API keys of `obserwator admin` (`api_keys.json`, the default `OBSERWATOR_API_KEYS_FILE`) of a store moved aside go with it; copy the file into the new data root.
- Roots elsewhere are named by `OBSERWATOR_RAW_ROOT` and `OBSERWATOR_ROOT` (or `raw_root` and `root` in `[obserwator]` of `nogat.toml`); a REST server needs both.

### Datasets

| Key | Alias | Content |
|-------|-------|-----------|
| `pl.imgw.hydro_daily` | `hydro/dobowe` | Daily hydro: H [cm], Q [m3/s], T [°C] |
| `pl.imgw.hydro_monthly` | `hydro/miesieczne` | Monthly hydro: H/Q/T × min/mean/max |
| `pl.imgw.hydro_semiannual` | `hydro/polroczne_i_roczne` | Half-yearly and yearly hydro: H/Q/T × min/mean/max with dates of extremes |
| `pl.imgw.meteo_climate_daily` | `meteo/dobowe/klimat` | Daily climate meteo: Tmax, Tmin, Tmean, Tground, P, snow cover |
| `pl.imgw.meteo_precip_daily` | `meteo/dobowe/opad` | Daily precipitation meteo: P, snow cover and fresh snow |
| `pl.imgw.hydro_stations`, `pl.imgw.meteo_stations` | — | Station lists (CSV) — input of the `stations.geojson` catalog |
| `pl.imgw.hydro_now`, `pl.imgw.meteo_now` | — | Station code, name, river and coordinates kept of the current-data API (derived, no measurements) — input of the catalog |
| `pl.imgw.hydro_details` | — | Station details of hydro.imgw.pl kept of its station pages (gauge zero and datum, river km, catchment area, year of establishment, province, district, warning and alarm levels, absolute extremes; derived) — optional input of the IMGW-PIB catalog |
| `pl.imgw.pmaxtp` | — | PMAXTP per grid cell (`POT`, `AMP`) |
| `pl.imgw.hydro_phenomena` | — | Daily hydrological phenomena (download only) |
| `pl.imgw.meteo_climate_monthly`, `pl.imgw.meteo_precip_monthly`, `pl.imgw.meteo_synop_monthly` | `meteo/miesieczne/klimat\|opad\|synop` | Monthly meteo (download only) |
| `pl.imgw.meteo_climate_terms` | `meteo/terminowe/klimat` | Climate meteo at observation terms (download only) |
| `cz.chmi.hydro_daily` | — | ČHMÚ daily hydro: H [cm], Q [m3/s], T [°C]; one file per station and year |
| `cz.chmi.meteo_daily` | — | ČHMÚ daily meteo: P [mm], Tmean, Tmax, Tmin [°C] with quality (`QUALITY`) and the ČHMÚ flag; 4 files per station |
| `cz.chmi.hydro_stations`, `cz.chmi.meteo_stations` | — | ČHMÚ station lists (JSON) — input of the ČHMÚ catalog |
| `cz.chmi.hydro_now`, `cz.chmi.meteo_now` | — | ČHMÚ `now` station metadata (JSON) — input of the ČHMÚ catalog |

"Download only" datasets support `datasets files|download`, but not the store. Current data, warnings and `fetch_pmaxtp` remain live queries, without the store. `datasets(provider="CHMI")` or `obserwator datasets list --provider CHMI` lists the datasets of one provider, and `providers()` / `obserwator datasets providers` — the providers with licenses and station code patterns.

### Schemas

`obserwator-store/1` (the marker of a raw root), `obserwator-data/1` (the marker of a data root, ADR-017), `obserwator-meta/1`, `obserwator-series/1`, `obserwator-plan/1`, `obserwator-observation/1` (and the `obserwator-pmaxtp/1` extension) have their own version counters, independent of the package version; the command result envelope is `obserwator-result/1`. The analyses (ADR-016) add `obserwator-analyses/1` (main file of a version), `obserwator-station-analyses/1` (a station's record), `obserwator-analysis-summary/1`, `obserwator-analysis/1`, `obserwator-analyses-report/1`, `obserwator-analyses-export/1` and `obserwator-analysis-definition/1`; the stored answers keep Hydrolog's `hydrolog-result/1` and `hydrolog-error/1`. Within `/1` only optional fields are added; an incompatible change means `/2`. An unknown version is reported (`store_info(...).supported is False`), not guessed. The `/1` domains are open to further providers (key `<country>.<provider>.<slug>`, IMGW or WIGOS station code; ADR-003).

### Integrations

- **Archiwista** reads both roots only through the public read API (`store_info`, `iter_store`, `current_version`, `read_meta`, `read_catalog`, `read_station_list`, `read_archive`, `read_series_index`, `read_series`, `summarize_series`, `read_pmaxtp`, `command_for_version`), the data of both providers with the same adapter (`provider` in entries, catalogs and stations; `kind="observation"` entries read-only); Obserwator's library is the only writer, and neither root contains Archiwista files. In Nogat, Archiwista keeps the raw root and orders its downloads through Obserwator's library, and reads the series and catalogs from the data root (plan `2026-11-12-station-data-and-analyses.md` D2, D5; its step R2). `store_info(root).store_schema` tells the kind of a root (`obserwator-store/1` raw, `obserwator-data/1` data); from the marker the reader requires only `schema` (as `open_store` does); every problem in `StoreInfo.problems` has a code in `problem_codes`; `Meta.producer` and `Meta.producer_version` tell which release wrote the version; `iter_store(skip_versions=…)` returns versions already known to the consumer as `skipped` entries, without listing or reading them (incremental scan, a Python-library-only parameter). Projects pinning store versions (by `sha256` and `content_sha256` from the sidecar) are kept by Archiwista (`archiwista-project/1`, ADR-008); Obserwator has no projects of its own. Checking freshness and rebuilding a pinned version is provided by `command_for_version` (the version's command from its sidecar, `unsupported`/`command_not_rebuildable` when the metadata do not rebuild it; section "Command catalog").
- **Retman** runs actions as a handler through the public command catalog (`command_schema`, `data_commands`, `validate_command`, `format_command`, `check_command`, `run_command`) — the same options, validation, envelope and error codes as in the CLI and REST; English descriptions from `command_schema(lang="en")`, effects from `effects.writes` and `effects.network` of its `commands-1` entries. A command's `root` is the root of its kind, and `series build` and `store catalog` also take `raw_root`; both default to the configured roots.

The former optional SQLite cache was removed in 3.0.0 without migration — see `docs/CHANGELOG.md`.

## Changes in version 3.0.0

Full list with migration tables: [`docs/CHANGELOG.md`](CHANGELOG.md) (also earlier releases).

### Breaking changes

- The tool is called Obserwator (ADR-009): `pip install obserwator` and `import obserwator` instead of
  `imgwtools`, the command `obserwator` instead of `imgw`, the variables `OBSERWATOR_<KEY>` instead of
  `IMGW_<KEY>`, the section `[obserwator]` of `nogat.toml`, `ObserwatorError` and its subclasses instead of
  `IMGWError`; the dataset keys `pl.imgw.*` and the provider IMGW-PIB keep their names.
- CLI: the `datasets`, `stations`, `current` and `pmaxtp` groups replace `imgw fetch …` and `imgw list …`
  (e.g. `imgw fetch hydro -i dobowe -y 2023` → `obserwator datasets download -d hydro/dobowe -y 2023`);
  stdout is the `obserwator-result/1` envelope with `--json` (a summary for a person without it), an error is
  JSON on the last stderr line, exit codes follow the error registry.
- REST: catalog routes `/api/v1/<group>/<command>` replace `/api/v1/hydro|meteo|download|pmaxtp/*`
  and `/map/stations`; errors in `application/problem+json`.
- Python: `station_id` → `station` (argument) and `station_code` (field); `list_*_stations` →
  `find_stations`, `get_hydro_stations_with_coords` → `fetch_hydro_states`,
  `build_hydro_url`/`build_meteo_url` → `archive_files`; `download_hydro_data`,
  `download_meteo_data` return `DownloadResult` instead of `bytes`.
- Removed SQLite cache: the `imgwtools.db` package, the `imgw db` commands, the
  `GET /api/v1/hydro/data` endpoint, its settings and the installation extra. The replacement is
  the versioned store (`obserwator[store]`, `obserwator store …`); `.db` files are neither deleted nor migrated.
- `parse_zip_file` reports a corrupted ZIP as `ObserwatorDataError`; `parse_stations_csv` requires
  `kind="hydro"|"meteo"` and returns `StationListEntry`.

### New

- Versioned store in two roots, the raw root of the downloaded sources and the data root of what is
  built from them (ADR-017), with a freshness plan, Parquet series, a GeoJSON station catalog, PMAXTP
  per cell and CSV/JSONL export.
- A single catalog of 35 commands for Python, the CLI, REST and MCP (`command_schema`, `run_command`),
  the `obserwator-result/1` envelope with pagination, the `ERROR_CODES` error code registry.
- `find_stations`, `fetch_meteo_current`, `fetch_hydro_states`, `download_archives`,
  `select_series`, `summarize_series`, `export_archive`; a registry of 22 datasets from two providers.
- ČHMÚ provider (Czechia): per-station daily hydrological and meteorological data,
  freshness from the listing, canonical content and an observation register, a station catalog with SPA thresholds,
  ČHMÚ quality and flags in series.
- Stored analyses computed by Hydrolog (ADR-016): `analyses build|list|read|export`, `compute_analysis`
  for a subset on the fly, a registry of 87 analyses (`analysis_definitions`), the setting `hydrolog_command`.
- AI agents: `AGENTS.md`, `llms.txt`, `obserwator commands guide`, catalog descriptions in English
  (Polish on request: `--lang pl`, `Accept-Language`), command effect metadata, the `obserwator mcp` MCP server and `/mcp`.
- Public builder of test roots `obserwator.testing.build_fixture_store(root, *, data_root)`, returning
  `FixtureRoots(raw, data)` (also the PL + CZ variant).
