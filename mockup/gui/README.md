# Obserwator GUI mockup

A working mockup of Obserwator's web GUI, for the author's review before the plans are approved:

- Obserwator's GUI plan, `docs/plans/2026-11-12-obserwator-gui.md` on branch `plan/obserwator-gui` (pending);
- Nogat's cross-project plan, `docs/plans/2026-11-12-station-data-and-analyses.md` on branch `plan/station-data-and-analyses` (pending).

It shows every station of the catalogs on a map, with the selected station in the right panel. Hydrological and meteorological stations get different sections. The data are real, read from a demo store. Each number of an analysis comes from Hydrolog's own catalog command where Hydrolog has one. Otherwise a prototype computes it, and the page labels it „Prototyp obliczeń · docelowo Hydrolog (Hn/Mn)”.

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
  - `index.html` and `src/`: Preact with htm, the panel and the map;
  - `src/charts/`: Hydrolog's chart module, copied, with a `date` axis and a `band` series added;
  - `vendor/`: Preact, htm, MapLibre and Archiwista's glyphs;
  - `nogat/`: the kit and tokens, byte for byte.
