# Obserwator GUI mockup

A working mockup of Obserwator's web GUI, for the author's review before the plans are approved:

- Obserwator's GUI plan, `docs/plans/2026-11-12-obserwator-gui.md` on branch `plan/obserwator-gui` (pending);
- Nogat's cross-project plan, `docs/plans/2026-11-12-station-data-and-analyses.md` on branch `plan/station-data-and-analyses` (pending).

It shows every station of the catalogs on a map, with the selected station in the right panel. Hydrological and meteorological stations get different sections. The data are real, read from a demo store. Each number of an analysis comes from Hydrolog's own catalog command where Hydrolog has one. Otherwise a prototype computes it, and the page labels it „Prototyp obliczeń · docelowo Hydrolog (Hn/Mn)”.

The map's bar switches three views:

- „Stacje”: the stations of the catalogs;
- „Pomiary bieżące”: only IMGW-PIB's current measurements, hydrological and meteorological;
- „PMAXTP”: the point picked by a click or by coordinates, with its tables in the right panel; no layer of the PMAXTP grid.

The station points use hydro.imgw.pl's symbols, as recorded in `web/src/symbols.js` and `web/css/map.css`. The station panel opens with „Informacje o stacji” and „Pomiary bieżące”, then „Dane pomiarowo-obserwacyjne”, the analyses and „Pobierz”.

Nothing here is part of the package. The repository's ruff config excludes `mockup/`.

## What is real and what is mocked

| Area | In the mockup | In the plans |
|---|---|---|
| Data | A store filled by `obserwator store sync` and `store catalog` (below) | Archiwista's raw root and Obserwator's data root (Nogat plan D2, D3) |
| Hydrolog | Imported in-process; `run_command` is the function behind every `hydrolog` CLI call, so the numbers are the CLI's | Hydrolog started as a program, a batch for stored results (D6) |
| Results | Computed on request and cached in memory (500 entries) | Stored versions with provenance (`analyses build`, D7) |
| Analyses Hydrolog lacks | Prototypes in `server/analyses/_hydro_proto.py` and `_meteo_proto.py`; each docstring names its method and source | Hydrolog's steps H1 to H3 |
| Texts | Polish only, in the code | The message catalog, PL and EN (GUI plan D15) |
| Hand-off | `api/handoff`: `nogat-handoff/1` around `hydrolog-series/1`, opened by Hydrolog's GUI in „Statystyka przepływów” | the same (D13) |
| Current data | `api/current`: snapshots of `fetch_hydro_states`, `fetch_hydro_current`, `fetch_meteo_current` and `fetch_synop`, in memory only, at most one per source per 10 minutes, the last one kept on failure | the same (D8) |
| PMAXTP | `api/pmaxtp`: `fetch_pmaxtp`, 24 hours in memory per method and point, one live request at a time. `api/pmaxtp/file`: CSV and JSON packed by the server with PMAXTP's own terms. A link opens IMGW-PIB's own answer for the point. | the same (D8, D12) |
| Attribution | The lines of Nogat's DEV §20 (ECO-060), byte for byte, from `server/attribution.py` (below) | the same, from Obserwator's own catalog |
| Feedback | „Zgłoś uwagę”: `POST api/feedback`, the server's only write, one JSON line per report (below) | not yet planned; Hydrolog and Hydrograf keep reports in a database with an admin page |

## Provider attribution

The providers' terms require their lines with every product of their data. The mockup keeps the lines in `server/attribution.py`, the only place, quoted byte for byte from Nogat's `DEVELOPMENT_STANDARDS.md` §20:

- IMGW-PIB data: S and P;
- data of hydro.imgw.pl: also H;
- PMAXTP: PS, PP and the monograph M, in place of S and P;
- ČHMÚ: C and CP, where CP names what was done;
- with IMGW-PIB data: the notice N and the terms that apply, RD, RH and RK.

`api/meta` serves the texts to the page (`web/src/attribution.js`). Where each surface carries them:

| Surface | Lines |
|---|---|
| Every API response with data or results (`api/stations`, `api/station`, `api/series`, `api/analysis/*`, `api/current`, `api/export/info`, `api/pmaxtp`) | the fields `attribution` and `terms_notice`; `api/station` adds `attribution_parts` for the panel's catalog, series and results |
| `api/export` CSV | `export_series`'s file unchanged, plus the trailing columns `attribution` and `terms_notice`, one line per row from the first data row down |
| `api/export` JSON, `api/pmaxtp/file` JSON, `api/handoff` | the fields `attribution` and `terms_notice`; a hand-off validates against Nogat's `handoff-1` schema |
| `api/pmaxtp/file` CSV | the columns `attribution` and `terms_notice` |
| The map, views „Stacje” and „Pomiary bieżące” | a strip under the map with the lines of the data drawn. It never folds, unlike MapLibre's compact control, which keeps the basemap's credit only. |
| The station panel | a block under each open section with data: its catalog, current, series or results lines |
| „Opady” | an extra block beside the PMAXTP values |
| „Paski klimatyczne” in „Temperatura” | PNG and SVG: the lines and terms drawn under the stripes, after the station, the period and „Metoda: Ed Hawkins (University of Reading), #ShowYourStripes”; CSV, written in the browser: the columns `method`, `attribution` and `terms_notice` |
| The panel without a station, the station list on a phone | a block, or a sheet foot |
| PMAXTP | a block under the table |

The library's own lines differ in places: `export_series` writes S and P, but no `attribution` or `terms_notice` columns and no N. Its ČHMÚ source line lacks C's licence link. `provider_notice_imgw` says less than N.

## „Zgłoś uwagę”

The button „Zgłoś uwagę” of the top bar opens a dialog, after Hydrolog's GUI and Hydrograf. The author's decision of 2026-11-13 sets what a report holds: the text and the automatic context, no contact fields. Under the field the dialog says „Nie wpisuj danych osobowych. Jeśli chcesz odpowiedzi, napisz na kontakt@debever.pl”, and it shows the context it sends, read-only.

`POST api/feedback` takes `{"message", "context"}` as JSON, at most 8 KB, from the page's own origin only (`Sec-Fetch-Site: same-origin`, else a matching `Origin`). The text has 1 to 4000 characters. The context holds:

- `view`: `stations`, `current` or `pmaxtp`;
- `station`: a code of the catalog; the server adds its `station_name`;
- `section` and `section_title`: the open section of the station panel;
- `address`: the page's path and query.

An unknown field is refused. At most 5 reports per client address in 10 minutes, counted in memory, then `429` „Za dużo zgłoszeń z tego adresu…”.

Each report is one line of `${OBSERWATOR_MOCKUP_FEEDBACK:-<data_dir>/obserwator/feedback/reports.jsonl}`, where `data_dir` is Nogat's (DEV-18.2). On this host the path is `~/.local/share/nogat/obserwator/feedback/reports.jsonl`. The first report creates the file (directory 0700, file 0600). Each line is appended in one write under a lock. A line holds `schema`, `id`, `created_at` (UTC), `version` (Obserwator, Hydrolog, the mockup's commit), `context` and `message`. It never holds the IP address or the `User-Agent`:

```json
{"schema":"obserwator-mockup-feedback/1","id":"fbf467ec-973e-4708-80cc-e5e1f9e59292","created_at":"2026-11-13T12:23:18Z","version":{"obserwator":"3.0.0.dev0","hydrolog":"1.0.0.dev0","mockup":"667c886"},"context":{"view":"stations","station":"150160180","station_name":"KŁODZKO","section":"characteristic","section_title":"Stany charakterystyczne","address":"/?station=150160180&section=characteristic"},"message":"Test zgłoszenia: wykres stanów charakterystycznych nie mieści się w panelu."}
```

Reading the reports, without an admin page:

```bash
F=~/.local/share/nogat/obserwator/feedback/reports.jsonl
jq -r '[.created_at, .context.station // "-", .context.section // "-", .message] | @tsv' "$F"   # one line each
jq . "$F"                                                                                     # in full
```

Reports stay until handled. To set the handled ones aside, move the file, e.g. `mv "$F" "${F%.jsonl}-$(date +%F).jsonl"`. The next report starts a new file.

## Demo store

The store is `/home/claude-agent/data/obserwator-demo/store`, filled on 2026-11-12 by `scripts/sync.sh` and then `scripts/sync2.sh`.

- IMGW-PIB:
  - `hydro_daily` and `hydro_semiannual`, hydrological years 1951–2025 (1,372 stations);
  - `meteo_climate_daily` (339 stations) and `meteo_precip_daily` (1,653 stations), 1961–2025;
  - catalogs with the static locations of `python -m obserwator.reference_data`.
- ČHMÚ:
  - `hydro_daily` for 13 stations (Labe, Odra, Opava, Lužická Nisa, Vltava and others);
  - `meteo_daily` for 10 stations, with Praha-Klementinum from 1775;
  - catalogs.

Found while filling it:

- Obserwator's ČHMÚ meteo parser rejects some 19th-century rows: `TIMEFUNC` `05:00`, `12:00` or `19:00` „not allowed for the element”. One such row fails the whole `series build`. The rejected files were moved out of the store to `/home/claude-agent/data/obserwator-demo/quarantine/`: Opava `SRA`, `T`, `TMA`, `TMI` and Liberec `T`.
- IMGW-PIB's current files have no rows for Kłodzko (150160180) in hydrological year 1997, neither in `codz` nor in `polr`, so the July 1997 flood is missing.

Found while building the views (2026-11-13):

- IMGW-PIB has no PMAXTP file for a point. Its page klimat.imgw.pl/opady-maksymalne reads `https://powietrze.imgw.pl/tpmax-api/point/{P|A}/KS/{lat}/{lon}`, the URL that `build_pmaxtp_url` builds. It writes its downloads in the browser (SheetJS, XLSX). The page's „Regulamin udostępniania danych projektu PMAXTP” asks for its own source line, which names the page, for the monograph and for its own mark of processed data. Obserwator's registry gives `pl.imgw.pmaxtp` IMGW-PIB's general formula.
- hydro.imgw.pl classes a meteorological station by the precipitation of the last 6 hours (`hydro-back.imgw.pl/map/stations/meteorologic`). Obserwator has no function for that endpoint, so the mockup classes by the 10-minute total of `fetch_meteo_current` and its legend says so.
- `MeteoCurrentData` keeps 4 of the meteo API's values: air temperature, mean wind, humidity and the 10-minute precipitation. It drops ground temperature, wind direction, maximum wind speed and the 10-minute gust. Of the times, it keeps only the air temperature's.
- The times of IMGW-PIB's current-data API are UTC; hydro.imgw.pl labels the same measurements „UTC”.
- `fetch_synop` names stations by WMO index (`12566`). The mockup pairs it with the catalog's code `3PPLL0NNN` (`350190566`); this matches 61 of the 62 synoptic stations by name.
- showyourstripes.info's FAQ („How have these graphics been made?”) changed the stripes' scale. In June 2019 the centre was the mean of 1971–2000 and the colours spanned ±2.6 standard deviations of the annual means of 1901–2000; the current page (data to 2025) says 1961–2010 and ±3.0. „Paski klimatyczne” offers both, the current one first. IMGW-PIB's records start in 1951 or later, so their spread falls back to the whole record.

## Run

```bash
uv sync
OBSERWATOR_MOCKUP_ROOT=/home/claude-agent/data/obserwator-demo/store \
  .venv/bin/uvicorn server.app:app --host 127.0.0.1 --port 8060
```

The app menu „Aplikacje” reads `[nogat] gui` from `nogat.toml`, as Obserwator's other pages do.

## Layout

- `server/`:
  - `app.py`: routes, headers, cache; `attribution.py`: the providers' lines; `feedback.py`: „Zgłoś uwagę”'s checks, rate limit and file;
  - `store.py`: catalogs, series indexes, station Parquet files;
  - `hydrolog_bridge.py`;
  - `analyses/`: `hydro.py`, `meteo.py` and their prototypes.
- `web/`:
  - `index.html` and `src/`: Preact with htm, the panel and the map; `src/symbols.js`: hydro.imgw.pl's station symbols; `src/current.js`: the current measurements; `src/pmaxtp/`: the PMAXTP view; `src/attribution.js`: the lines drawn; `src/ui/feedback.js` and `src/ui/toast.js`: „Zgłoś uwagę” and the toasts;
  - `src/charts/`: Hydrolog's chart module, copied, with a `date` axis and a `band` series added;
  - `vendor/`: Preact, htm, MapLibre and Archiwista's glyphs;
  - `nogat/`: the kit and tokens, byte for byte.
