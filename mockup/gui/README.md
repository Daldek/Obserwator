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

## Run

```bash
uv sync
OBSERWATOR_MOCKUP_ROOT=/home/claude-agent/data/obserwator-demo/store \
  .venv/bin/uvicorn server.app:app --host 127.0.0.1 --port 8060
```

The app menu „Aplikacje” reads `[nogat] gui` from `nogat.toml`, as Obserwator's other pages do.

## Layout

- `server/`:
  - `app.py`: routes, headers, cache;
  - `store.py`: catalogs, series indexes, station Parquet files;
  - `hydrolog_bridge.py`;
  - `analyses/`: `hydro.py`, `meteo.py` and their prototypes.
- `web/`:
  - `index.html` and `src/`: Preact with htm, the panel and the map; `src/symbols.js`: hydro.imgw.pl's station symbols; `src/current.js`: the current measurements; `src/pmaxtp/`: the PMAXTP view;
  - `src/charts/`: Hydrolog's chart module, copied, with a `date` axis and a `band` series added;
  - `vendor/`: Preact, htm, MapLibre and Archiwista's glyphs;
  - `nogat/`: the kit and tokens, byte for byte.
