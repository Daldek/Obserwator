# Plan: Obserwator's web GUI: stations on a map, harmonized data and analyses, standalone and as a Nogat module

Approved: 2026-11-13, the author (answers to questions 1–6 and the go-ahead to implement, in session)

Requirements: DEV-17.4, DEV-15.1 to DEV-15.6, DEV-2.2, DEV-2.3, DEV-13.2, DEV-13.3, DEV-18.1, AGI-6.1, ECO-054, ECO-055, ECO-058, ECO-059, HUB-2.9, HUB-5.2. Inputs: the author's answers and requirements of 2026-11-12 and 2026-11-13 (below); the cross-project plan, Nogat `docs/plans/2026-11-12-station-data-and-analyses.md` (branch `plan/station-data-and-analyses`, approved 2026-11-13, its step N1 at `70ba25a`), which fixes the roles of Archiwista, Obserwator and Hydrolog (ECO-059), the split of the store, the analyses and the steps of every project; Nogat's stage 1 plan `docs/plans/2026-11-12-gui-links-and-handoff.md` (approved 2026-11-12) and stage 2 plan `docs/plans/2026-11-01-nogat-gui-platform.md` (pending; decision B6, item 9, step 14); step 7 of Nogat's visual identity plan; Hydrolog's GUI plan `docs/plans/2026-11-02-hydrolog-gui.md` and its ADR-0014 as the model. This plan is the GUI part of the Nogat plan (its steps O3 and O4). The reviewed prototype is the mockup on branch `feat/gui-mockup` (below). No code before `Approved:`.

## The author's answers (2026-11-12)

- Scope: „Podgląd stacji, udostępnianie zharmonizowanych danych w innym formacie niż to co dane IMGW i Czesi. Archiwista pokazuje to co teraz i odpowiada za trzymanie surowych danych, pobieranie ich, itp., a Obserwator docelowo ma też udostępniać statystyki i inne dane po ich analizie.” Station browsing; serving the data of IMGW-PIB and ČHMÚ harmonized, in formats other than the providers' own; Archiwista keeps showing what it shows and owns the raw data and their download; Obserwator also serves statistics and other derived data.
- Form: „Podobnie do GUI Hydrografa, bo wszystkie stacje będą na mapie, a ich dane w panelu po prawej stronie.” Every station on a map, the chosen station's data in the right panel.
- Public: yes, in the public test deployment beside Hydrograf (hydrograf-test.debever.pl), Hydrolog (hydrolog-test.debever.pl) and Archiwista (archiwista-test.debever.pl), the last two behind Cloudflare Access.
- Requirements of the same day (Nogat plan, „The author's requests”): raw data and downloads are Archiwista's; Obserwator keeps only harmonized data and analysis results and serves them; Hydrolog does every computation; a station's view differs by kind; the hydrological and meteorological analyses listed there.

## The author's answers (2026-11-13)

Verbatim where the author wrote in Polish; the full record is in the Nogat plan's „The author's answers (2026-11-13)”.

- Download code: „Kod pobierania zostaje biblioteką Obserwatora, którą Archiwista wywołuje” (the Nogat plan's B1).
- Roots and refresh: „Surowy leży u Archiwisty, zharmonizowany też, ale tylko jako backup całego zakresu. Wersja produkcyjna leży u Obserwatora. Co do odświeżania — dane powinny być przeliczone raz, na początku i tyle, a pobieranie nowych będzie realizowane 1 raz w roku, gdy pojawią się nowe paczki danych publicznych. Jeżeli user liczy jakieś rzeczy dla wybranego wycinka danych, to robimy to w locie i nie jest to w żaden sposób zapisywane na stałe.” The GUI reads Obserwator's production data root; the stored results are computed once and refreshed yearly; a subset the person chooses is computed on the fly and never stored.
- IMGW-PIB's warning and alarm levels: „Nie, danych operacyjnych nie archiwizujemy”; the station view shows ČHMÚ's thresholds and the characteristic levels only.
- IMGW-PIB's terms for the public instance: „do sprawdzenia”; a research note follows.
- Reference periods (relayed in English): the whole record by default, adjustable by the person, with a note that the recommended minimum period is 30 years.
- XLSX (this plan's question): not needed; exports are CSV, JSON and Parquet.
- PMAXTP in the GUI, relayed in English: no graphic layer of the PMAXTP grid; the person picks a point and gets the results; downloads come straight from IMGW-PIB's service if correct file addresses can be generated, otherwise through the API queried by coordinates and packed into a file, as Obserwator's old PMAXTP page did.
- The map, relayed in English: switching from „Stacje” to „Stan wody (IMGW-PIB)” did not hide the stations (a bug of the mockup); the view is renamed „Pomiary bieżące” and shows the current measurements of IMGW-PIB's hydrological and meteorological stations (meteo was missing); station points are styled as on hydro.imgw.pl, so people orient themselves easily.

## Prototype

The working mockup on Obserwator's branch `feat/gui-mockup`, `mockup/gui/` (`27cfb4e` and the changes of 2026-11-13 for the answers above), is the prototype the author reviewed: the map with every station of the demo store, the panel by station kind, Hydrolog's numbers where Hydrolog has a command and labelled prototypes elsewhere. Its `README.md` lists what is real and what is mocked. The slices take its layout, sections and texts as the reference and rebuild the code by this plan (the mockup imports Hydrolog in-process, keeps its texts in the code and is not part of the package).

## Goal

A browser GUI of Obserwator, in Nogat's identity, that the public test deployment serves read-only:

- every station of IMGW-PIB and ČHMÚ that Obserwator's catalogs locate is a point on one map; a click opens the station in the right panel (Hydrograf's form), with a view for a hydrological and another for a meteorological station: the station's description, its series as a chart and a table, current IMGW-PIB values, the analyses of the Nogat plan (H1 to H18, M1 to M14) and downloads;
- harmonized data out: a station's series as CSV (exists), JSON or Parquet, the stations of both providers as GeoJSON or CSV, analysis results as CSV and JSON, each file with its provider's licence and attribution, made by catalog commands so that the CLI, REST and MCP give the same files;
- PMAXTP of a point in Poland, which the Jinja pages offer today: a point picked on the map or by coordinates, the results tables and the downloads, without a layer of the PMAXTP grid;
- it runs alone (`obserwator gui serve`, 127.0.0.1:8060 by default) and is the hosted module of Nogat's stage 2 (B6) through the entry point group `nogat.gui`; the Jinja, HTMX and Pico pages are removed at the end;
- it reads Obserwator's production data root (series, catalogs, stored analysis results) and never writes it; it never downloads (raw data are Archiwista's); every number of an analysis is Hydrolog's, read from the stored results or, for a subset the person chooses, computed by Hydrolog's program on the server's request and never stored; the browser formats, decimates for drawing and draws.

## Where it starts

Read on 2026-11-12: Obserwator `origin/develop` `b853637` (the base of this branch; paths below are Obserwator's unless a project is named), Nogat `origin/develop` `99de00a`, Hydrolog `origin/develop` `912dbf2`, Archiwista `origin/develop` `a656ee1`, Hydrograf `develop` `7d2535e`, and the deployment host.

| Fact | Consequence |
|---|---|
| The web GUI is FastAPI + Jinja2 + HTMX with nine routes: dashboard, archive download links, the PMAXTP form, station search and the map (`src/obserwator/web/app.py:143-377`, `docs/ARCHITECTURE.md:140-153`), IMGW-PIB only (`web/app.py:8-9,85-86`); PROGRESS: „the pages give way to the GUI hub of Nogat's stage 2” (`docs/PROGRESS.md:20`); Nogat's stage 2: „B6. Obserwator gets a new hosted module; its Jinja pages are removed.” (Nogat `docs/plans/2026-11-01-nogat-gui-platform.md:78`, step 14 at `:439`) | a new GUI; the pages go once it covers search, the map and PMAXTP |
| The pages load HTMX 1.9.10 and Pico 2 from unpkg and jsDelivr (`templates/base.html:9,12`), Leaflet 1.9.4 from unpkg with OpenStreetMap's own tiles (`templates/map.html:5,151,160`) and SheetJS 0.20.1 from its CDN (`templates/partials/pmaxtp_result.html:71`); no tokens and no dark theme. Nogat: „No remote resources: apps run offline under CSP `'self'`.” (Nogat `design/README.md:26`), DEV-15.1 to DEV-15.3 (Nogat `standards/DEVELOPMENT_STANDARDS.md:423-435`) | restyling the pages (visual identity step 7, Nogat `docs/plans/2026-11-01-visual-identity.md:85`) is not worth it; the new GUI follows the standard from its first commit |
| Today's map draws the markers of `GET /api/v1/current/hydro-states`, fetched by the browser (`map.html:209-234`): IMGW-PIB hydro stations with a live water state, no ČHMÚ, no store, no series. „Data charts” are „Not Implemented” (`docs/PRD.md:113-117`); backlog: „GeoJSON in REST/GUI” and „Data charts” (`docs/PROGRESS.md:55-56`) | the station layer comes from the catalogs; charts are new |
| `obserwator server` is one FastAPI app: the catalog routes, the pages, `/static` and, when enabled, `/mcp` (`src/obserwator/api/main.py:157-169`); CORS allows every origin with credentials (`:149-155`); defaults 0.0.0.0:8000 (`src/obserwator/config.py:117-118`) and reload unless `production` (`api/main.py:221-226`); writes need `OBSERWATOR_STORE_WRITES_ENABLED` and `X-API-Key` (`config.py:141-150`) | a public page must not be served by that app: the GUI gets its own app with only its own routes |
| Commands outside the catalog: `version`, `server`, `mcp`, `admin` (`src/obserwator/cli/main.py:6-7`); everything else is generated from the catalog (`CLAUDE.md:12`). `AGENTS.md` has 16,094 of its 16,384 bytes (`tests/unit/test_agent_guide.py:162`) | `gui serve` joins `server` and `mcp`; the catalog commands of the Nogat plan's O2 and O3 must fit the budget |
| One store holds archives, series, catalogs and PMAXTP cells (`docs/ARCHITECTURE.md:199-211`); the Nogat plan splits it into Archiwista's raw root and Obserwator's data root (its D2, D3; step O1) and stores Hydrolog's results in the data root (its D7; step O2). Reading needs neither writes nor hard links (`docs/ARCHITECTURE.md:213`); readers `read_catalog`, `read_series`, `summarize_series` (`src/obserwator/store/reader.py:1758,2322,2552`); `build_fixture_store(variant="complete_pl_cz")` builds an offline store of both providers (`src/obserwator/testing.py:300-336`) | the GUI reads the data root only, never writes; its tests run on the fixture store (split by O1), also on a read-only copy |
| `series.json` holds each station's file, rows, SHA-256 and the coverage of each variable: first, last, gaps (`src/obserwator/store/series.py:1145-1179`). A station's Parquet has `date`, `hydro_year`, `{V}_value`, `{V}_flag`, and for ČHMÚ meteo `{V}_quality` and `{V}_source_flag`; its metadata are `obserwator_schema`, `dataset`, `units` and `variable_notes`, no licence (`series.py:770-827`) | coverage for the map without pyarrow; a Parquet download must add the licence |
| Catalog properties are one set for both providers (`src/obserwator/store/catalog.py:125-141`), ČHMÚ hydro stations add SPA `thresholds` (`reader.py:1770-1771`); the stored GeoJSON carries no attribution, only its sidecar does. In the store `/mnt/magazyn/agent-tmp/archiwista-zespol/obserwator` (481 MB, catalogs of 2026-11-05 and 2026-11-06): IMGW-PIB 3,810 stations, 2,142 of them without coordinates (1,614 meteo, 528 hydro; the located ones come from the current IMGW-PIB API, `location_source` `api_hydro` and `api_meteo`); ČHMÚ 2,486, 14 without (outside the country); the two files 1.56 MB and 1.29 MB | „wszystkie stacje na mapie” holds for ČHMÚ and the current IMGW-PIB stations; the others are found by search and listed, and open without a marker; an official list is asked of IMGW-PIB (`docs/PROGRESS.md:73`) |
| Harmonized today: one record and flag model, `value`, `missing`, `no_phenomenon`, `accumulated` (`src/obserwator/models.py:20`); the same variables and units, e.g. `{"H": "cm", "Q": "m3/s", "T": "degC"}` for the daily hydro data of IMGW-PIB and ČHMÚ (`src/obserwator/datasets.py:335,550`); a calendar `date` and a `hydro_year` XI–X for both (`docs/DECISIONS.md:212,233`); one CSV layout for both with the provider's attribution in the first row (`src/obserwator/store/export.py:558-565`) | the GUI shows and exports this model and converts nothing itself |
| Not harmonized or missing: `series export` writes CSV only (`src/obserwator/commands.py:1068-1075`); no export of the stations (`docs/PROGRESS.md:55`); variable definitions exist only for ČHMÚ (`datasets.py:560,585`, `src/obserwator/messages/datasets.py:195-238`), and ČHMÚ's day and hydrological year are unconfirmed (`docs/DECISIONS.md:212,233`; `docs/PROGRESS.md:75`); ČHMÚ meteo adds `_quality` and `_source_flag` columns (`export.py:560-561`); monthly and half-year series exist for IMGW-PIB only (`AGENTS.md:54-67`) | new formats: a series as JSON and Parquet, the stations as GeoJSON and CSV; definitions next to each variable and in each file |
| Licences: IMGW-PIB with the formula „Źródłem pochodzenia danych jest Instytut Meteorologii i Gospodarki Wodnej – Państwowy Instytut Badawczy”, its processed mark and the terms `https://danepubliczne.imgw.pl/regulations` (`datasets.py:305-309`, `src/obserwator/messages/legal.py:13-30`), and the notice „Do użytku prywatnego i badawczego; inne zastosowania wymagają sprawdzenia warunków IMGW-PIB, także wyjątków dla danych o wysokiej wartości.” (`messages/datasets.py:122-127`; ADR-001 Q15, `docs/DECISIONS.md:69`); ČHMÚ under CC BY 4.0 with its formula, processed mark and disclaimer page (`datasets.py:310-315`, `messages/legal.py:18-22,31-32`); the pages' footer names IMGW-PIB only (`templates/base.html:49`) | every view and every file names the provider, its licence and that the data were processed; the Nogat plan's question 4 |
| Current data: `current hydro`, `meteo`, `synop`, `warnings` and `hydro-states` ask IMGW-PIB on every call (`AGENTS.md:99-104`, `src/obserwator/urls.py:20`; no cache in `src/obserwator/fetch.py`): water level, discharge and water temperature with their times (`models.py:349-380`), water states with coordinates (`models.py:600-620`); ČHMÚ `now` and `recent` are not supported (`AGENTS.md:9`) | the server keeps snapshots that it does not store (the Nogat plan's D3); ČHMÚ stations have no current values |
| PMAXTP: `fetch_pmaxtp` is live and for Poland only (`src/obserwator/fetch.py:67-70,363`); a stored cell is read by its grid indices only (`src/obserwator/store/pmaxtp.py:736-744`), and no function maps a point to a cell (`docs/PROGRESS.md:62`) | the server fetches PMAXTP of a point and caches it, without storing it |
| Archiwista already shows Obserwator's catalogs and series: a station card with daily, monthly and annual charts (A-ADR-051), coverage, a map with MapLibre GL JS 6.14.0 (Archiwista `src/archiwista/web/vendor/vendor.json:47-49`) and the hand-off of a series to Hydrolog (A-ADR-052), deployed on archiwista-test (Nogat `docs/PROGRESS.md:103`); it „never writes to a store” and a download „goes through the producer's API” (Archiwista `README.md:3,43`); out of its scope: „Hydrological calculations and statistics of series” and „Current IMGW and ČHMÚ data” (Archiwista `docs/SCOPE.md:108-109`); its v1.1 exports series through Obserwator's `export_series` (Archiwista `docs/SCOPE.md:226`) | both draw a station's series: D3 makes the boundary explicit; the new export formats serve Archiwista too |
| Archiwista's map takes its basemaps from settings, by default OpenFreeMap's grey vector tiles (Polish names, no key) and GUGiK's OSM raster for Poland (Archiwista `src/archiwista/config.py:465-483`), and builds its CSP from their origins with `worker-src 'self'` for MapLibre's worker (Archiwista `src/archiwista/security.py:1484-1519`); Preact 10.29.8 and htm 3.1.1 vendored with SHA-256 per file (`vendor.json:5-7,29-31`) | the model of the map, the CSP and the vendoring |
| Hydrograf: the map in the centre, the results in the right panel (Hydrograf `frontend/index.html:86,175`); IIFE scripts (`:636-660`) with Leaflet 1.9.4, MapLibre GL 4.7.1, Chart.js 4.4.7 and VectorGrid from unpkg and jsDelivr (`:613-631`) | the model of the form, not of the code |
| Hydrolog's GUI: `hydrolog gui serve` on 127.0.0.1:8070, Starlette, a private API relative to the page, the entry point `nogat.gui` with a `GuiModule` (Hydrolog `src/hydrolog/gui/__init__.py:48,151`, `pyproject.toml:94-95`), the headers of its D8 (`src/hydrolog/gui/_app.py:114`), Preact and htm without a build, Playwright tests (its plan D2 to D9, D17); ADR-0014 rejected FastAPI, a public REST API and Chart.js (Hydrolog `docs/decisions/0014-web-gui-enters-the-scope.md:115-123`); a CLI call costs about 1.4 s (its plan, „Where it starts”) | the model of serving, hosting, headers and tests; on-demand computations are few and cached |
| Registry: Obserwator has no `gui` interface (Nogat `ecosystem.yaml:132-136`); `validate` only checks that a route starts with the project's CLI (Nogat `scripts/guide.py:78-91`) | Nogat adds the interface and a route (Nogat plan, N2) |
| Host: `obserwator-test.debever.pl` already serves a placeholder from 127.0.0.1:8060 behind Cloudflare Access, through the user unit `obserwator-public.service` (Nogat `docs/PROGRESS.md:94`, `docs/plans/2026-11-12-gui-links-and-handoff.md:184-189`); `~/.config/nogat/nogat.toml` lists `obserwator = "https://obserwator-test.debever.pl/"`; Hydrolog's GUI runs from `~/workspace/Hydrolog-gui` under `hydrolog-gui.service` | the GUI takes over 127.0.0.1:8060; on-demand computations can use the same Hydrolog program as hydrolog-test |
| Dependencies: Starlette 1.9.0 and uvicorn 0.54.0 are in `uv.lock` through `fastapi` and `mcp` (`uv.lock:1831-1832,1898-1899`); httpx is a base dependency (`pyproject.toml:35`); Jinja2 and python-multipart serve only `web/app.py` (`pyproject.toml:46-47`); Playwright is not in the lock | the `gui` extra adds no package to the lock but Playwright in the dev group; the pages' removal drops two |

## Options

**A. Frontend stack**

| Option | Verdict |
|---|---|
| A1. Preact 10.29.8 and htm 3.1.1 as ES modules without a build, vendored byte for byte as in Archiwista and Hydrolog | Recommended: DEV-15.1 and CSP `'self'`; components and state for a map, a list, a panel and charts; the same files, `vendor.json` and Playwright model as two GUIs of the ecosystem |
| A2. Classic IIFE scripts on a global, as Hydrograf | Rejected: DEV-15.1 asks for ES modules; Hydrograf's form is the model, not its code |
| A3. Jinja and HTMX kept, vendored and restyled | Rejected: B6 removes the pages; a map and a panel that follow a selection are client state, which server-rendered partials model badly |

**B. Map library**

| Option | Verdict |
|---|---|
| B1. MapLibre GL JS 6.14.0, vendored byte for byte as Archiwista's | Recommended: vector basemaps with Polish names, WebGL circles for over 4,000 points with data-driven style and selection, and the ecosystem's direction (platform plan `:453` „Hydrograf on MapLibre to share a map shell”, the kit's `basemaps.json` at `:308`) |
| B2. Leaflet 1.9.4 (Hydrograf, today's `/map`) | Rejected: raster tiles only, unless a second library and a bridge are added as Hydrograf does (`frontend/index.html:613-621`); a map unlike Archiwista's |

**C. Serving**

| Option | Verdict |
|---|---|
| C1. `obserwator gui serve`: its own Starlette app with a private API relative to the page, found by a host through `nogat.gui` | Recommended: Hydrolog's model; only the GUI's routes reach the public address; it mounts under any prefix |
| C2. Routes in `obserwator server` | Rejected: the public address would also expose the catalog routes (live calls to IMGW-PIB and ČHMÚ), `/docs`, `/mcp` and CORS `*` (`api/main.py:149-155`) |
| C3. Both: the GUI app also mounted in `obserwator server` | Rejected: two ways to serve one page, twice the tests, and the server's CORS would wrap the GUI's routes |

**D. Data source**

| Option | Verdict |
|---|---|
| D1. Obserwator's data root, read-only: series, catalogs and stored analysis results; the provider only for current data and PMAXTP, through the server's caches, nothing stored | Recommended: the Nogat plan's D3; reproducible (the panel names the versions), works offline, bounded load on IMGW-PIB |
| D2. The raw root or live calls for series | Rejected: raw data are Archiwista's, parsed once by Obserwator into the data root |
| D3. A database or precomputed files of the GUI | Rejected: a second copy of the data root; Obserwator keeps no database (`CLAUDE.md:11`) |

**E. Boundary with Archiwista**

| Option | Verdict |
|---|---|
| E1. Obserwator is the window on the harmonized data and the analyses (what the stations measured and measure, in one format, and what follows from it); Archiwista the archive of raw data, their download, versions and projects, keeping what it shows now | Recommended: the author's answers and the Nogat plan's D1; the overlap, a station's series chart, is accepted and bounded by D3 |
| E2. Obserwator shows only what Archiwista does not (current data, PMAXTP, files, analyses) and links to Archiwista for series | Rejected: „ich dane w panelu po prawej stronie” asks for the series in Obserwator, and Archiwista is not in every deployment |
| E3. Archiwista's station views move to Obserwator | Rejected: „Archiwista pokazuje to co teraz” |

**F. Analyses in the GUI**

| Option | Verdict |
|---|---|
| F1. The stored results of the Nogat plan's O2, computed once over the whole record and refreshed yearly, and for a subset the person chooses (a range of years, a distribution, a threshold, a period) one call of Hydrolog's program made by the server, computed on the fly and never stored | Chosen: the Nogat plan's C1, D7 and D12; every number is Hydrolog's |
| F2. Every analysis computed on request | Rejected: dozens of Hydrolog calls per station view on a small server |
| F3. The browser or the server computes | Rejected: „Hydrolog does every computation” |

**G. Export formats**

| Option | Verdict |
|---|---|
| G1. A series as CSV (exists) | Kept byte for byte: Hydrolog's statistics read it (Nogat `ecosystem.yaml:279`) |
| G2. A series as JSON: one columnar document with units, definitions, the series version and the attribution | Recommended: the panel's chart reads the same document the person downloads |
| G3. A series as Parquet, typed, with the licence and attribution in its metadata | Recommended: for pandas, R and DuckDB; cheap with pyarrow, which the series need anyway |
| G4. The stations of both providers as GeoJSON and CSV, one schema, each provider's attribution | Recommended: closes the backlog item (`docs/PROGRESS.md:55`); the harmonized station list neither provider publishes |
| G5. Analysis results as CSV and JSON (`analyses export`, Nogat plan O2), with the series version and Hydrolog's version | Recommended: requirement 1, „udostępniać statystyki” |
| G6. XLSX | Rejected (answer of 2026-11-13): not needed; CSV, JSON and Parquet cover the files |
| G7. NetCDF, WaterML 2.0 | Rejected for now: no consumer in the ecosystem, heavier dependencies |
| G8. The providers' raw files and the wget script of today's page | Rejected: raw data are Archiwista's; `obserwator datasets files` and `datasets download` stay |

**H. UI texts**

| Option | Verdict |
|---|---|
| H1. Entries of Obserwator's message catalog, a new area `gui` (`Text(en, pl)`, ADR-006), served to the page | Recommended: the repository's one convention for texts (`CLAUDE.md:17`); both languages by construction, so Polish by default and English on request (DEV-2.2) without a deviation |
| H2. JavaScript label modules (Archiwista, Hydrolog) | Rejected here: a second place for texts in this repository, and a second set for English |

## Decisions proposed

### D1. Branch and slices

After approval `feature/gui` starts from this plan's commit on `plan/obserwator-gui` (based on `develop` `b853637`). Each slice is one agent on `feature/gui-<slice>` in its own worktree, with the gate green before every commit and its own `docs/CHANGELOG.md` entry; the coordinating session lands the slices by rebasing and fast-forwarding `feature/gui` (no merge commits, nothing pushed), runs the gate and updates `docs/PROGRESS.md`, as Hydrolog's GUI did (its plan, Steps). The author merges `feature/gui` into `develop` (DEV-3.3). The Nogat plan's O1 and O2 run on branches of their own, before the slices that read them.

### D2. Package and extra

`src/obserwator/gui/` holds the server, `src/obserwator/gui/web/` the page (package data `gui/web/**`). Extra `gui = ["obserwator[store]", "starlette>=1.9,<2", "uvicorn[standard]>=0.24"]` (a self-reference as the `mcp` extra's, `pyproject.toml:67-69`), repeated in `full`; the dev group gains `playwright>=1.64,<2`. Starlette rather than FastAPI: the private routes need neither OpenAPI nor pydantic (Hydrolog ADR-0014). Importing `obserwator.gui` imports neither Starlette nor uvicorn; `create_app` and `serve` raise `missing_dependency` without the extra.

### D3. Boundary with Archiwista

| | Obserwator's GUI | Archiwista |
|---|---|---|
| For whom | anyone the deployment admits, read-only; the public test instance | a person working with stores and projects, alone or in a team with roles |
| Stations | every station of Obserwator's current catalogs, on the map or in the list | the stations of its configured stores, in its catalog and map views |
| Series | the current version only: values and flags in Obserwator's format, chart, table, the definition of each variable | every stored version; coverage, origin, technical details; monthly bands and annual extremes (A-ADR-051) |
| Analyses | Hydrolog's results, stored by Obserwator or computed on request (the Nogat plan's H1 to H18, M1 to M14) | none beyond its display-only annual extremes (A-ADR-051 D8) |
| Current data | IMGW-PIB current measurements of hydrological and meteorological stations and the water states, from a server snapshot | none (Archiwista `docs/SCOPE.md:109`) |
| PMAXTP | the results tables of a point and their files (D12) | none |
| Files | series as CSV, JSON, Parquet; stations as GeoJSON, CSV; analysis results as CSV, JSON; PMAXTP as CSV and JSON packed from the API's answer, with a link to that answer (D12); each with its attribution | copies of pinned files in a project's export; series CSV through `export_series` from its v1.1 (`docs/SCOPE.md:226`) |
| Hand-off to Hydrolog | a series or annual maxima with the options of an analysis, for the same numbers in Hydrolog (D13) | a station's series (A-ADR-052) |
| Raw data, versions, provenance | never read; the panel names the series version, the analysis's Hydrolog version and their dates | yes: the raw root and its downloads (the Nogat plan's D5) |
| Downloading, store management | never; the GUI writes nothing | through its jobs and the `store.write` permission (Archiwista `README.md:43`) |
| Projects, accounts | none (ECO-054) | yes |

Both read Obserwator's data root through Obserwator's public functions; neither imports the other. Archiwista's changes are the Nogat plan's R2.

### D4. `obserwator gui serve`

A command outside the catalog, beside `obserwator server` and `obserwator mcp` (`cli/main.py:6-7`): options `--host` (default `127.0.0.1`), `--port` (default `8060`), `--root` (the data root; else the CLI's root: `OBSERWATOR_ROOT`, `[obserwator] root`, `<data_dir>/obserwator`) and `--no-browser`; it prints the address from the message catalog and blocks until Ctrl+C or `SIGTERM`. It is no MCP tool (a server inside a tool), has no REST route and adds no line to `AGENTS.md`; `CLAUDE.md:12` names it among the exceptions. Nogat's registry gets `interfaces.gui: obserwator gui serve` and a route (Nogat plan, N2), which `validate` accepts as it starts with the CLI's name.

### D5. Hosting: the entry point `nogat.gui` (B6)

```toml
[project.entry-points."nogat.gui"]
obserwator = "obserwator.gui:gui_module"
```

`gui_module()` returns a frozen `GuiModule(name="obserwator", title="Obserwator", web=<gui/web>, index="index.html", sections=(("stacje", "Stacje"), ("pmaxtp", "PMAXTP")), app=create_app)`, the fields of Hydrolog's `GuiModule` (Hydrolog `src/hydrolog/gui/__init__.py:48`) until Nogat publishes the contract (platform plan, item 3). The page uses relative URLs only, so it works at `/` and under any prefix; `?nogat=1` hides the top bar and the rail before the first paint.

### D6. Private API

GET and HEAD only, relative to the page (routes under Interfaces). They serve this GUI and are no REST interface: no `/api/v1`, no OpenAPI, no stability promise; a deviation from AGI-6.1 (Nogat `standards/AGENT_INTERFACE.md:320`) recorded in `CLAUDE.md`, as Hydrolog's. Every parameter is checked against the registry (dataset keys, variables, station code patterns, ISO dates, the analyses and their options) before the data root or Hydrolog is touched (DEV-13.3). An error is `obserwator-error/1` with the registry's HTTP status, the title in the page's language and server paths hidden (`hide_server_paths`, as `web/app.py:39` uses it).

### D7. Reading the data root

- Read-only: the server never writes under `--root`; a test serves a read-only copy of the fixture data root.
- The current versions of catalogs, series and analysis results are read again at most once a minute, so a new `series build` or `analyses build` (once at the start, then at the yearly refresh, the Nogat plan's D7) shows without a restart; the panel names the series version, the Hydrolog version of a result and their dates.
- Answers from the data root carry a strong ETag made of the versions' SHA-256 and the query, with `Cache-Control: no-cache`.
- One uvicorn process; blocking reads (pyarrow) run in threads, at most four at a time (the VPS's 4 vCPU). In memory: the station layer per set of catalog and series versions, and the 32 most recent series documents.

### D8. Live data and on-demand computations, through the server only

- Snapshots of `current hydro`, `current meteo` and `current hydro-states` (IMGW-PIB), each fetched on demand at most once per 10 minutes, one request at a time (single-flight), with the library's timeout (DEV-13.2). A failed refresh keeps the last snapshot, shown with its time („Dane z 14:20”). Nothing is stored.
- PMAXTP: cached in memory per method and point at the four decimals of IMGW-PIB's URL (`urls.py:59`) for 24 hours, at most 1,000 entries; one live request at a time; nothing stored.
- A subset the person chooses (the Nogat plan's D7 and D12): the public function of the Nogat plan's O2 that computes one analysis through Hydrolog's program without storing it; at most two Hydrolog processes at a time, 30 s each. The result is held in the server's memory only, per series version, analysis, options and Hydrolog version (at most 500 entries), and is never written to the data root or to disk. The configured program (`OBSERWATOR_HYDROLOG_COMMAND`) is the same as the one `analyses build` uses.
- The browser connects only to its own origin and the basemap's (D16); the link to IMGW-PIB's PMAXTP answer (D12) is a navigation the person starts, not a request of the page.

### D9. The map

- MapLibre GL JS 6.14.0. The basemap comes from settings, `OBSERWATOR_GUI_BASEMAP_URL` (a TileJSON; default `https://tiles.openfreemap.org/planet`, Archiwista's default) and `OBSERWATOR_GUI_BASEMAP_ATTRIBUTION` (default „OpenFreeMap © OpenMapTiles Data from OpenStreetMap”), drawn by the GUI's own grey style in the tokens for both themes, place names from `name:pl` where present. An empty URL is the offline mode: the borders of Poland and Czechia from the package (`src/obserwator/_data/poland_border_wgs84.geojson`, `czechia_border_wgs84.geojson`) are the background.
- Stations as hydro.imgw.pl draws them (its icon service and CSS variables `--<state>-status-color`, read on 2026-11-13 for the mockup), so a person who knows IMGW-PIB's map reads this one at once: a hydrological station is a rounded downward triangle ▼, a meteorological one a circle, both 16 px with a `#777` outline, and the selected station the same icon at 32 px. In „Stacje” hydrological stations are filled `#0A65C0` and meteorological ones `#289613`, the generic icons of hydro.imgw.pl's legend; a hollow centre marks a station known only from the catalog, a dashed outline marks ČHMÚ, inactive ones are faded. No text labels on the map; a tooltip names the station.
- The `.map-bar`: „Stacje” | „Pomiary bieżące”. „Stacje” shows the station layer of the catalogs. „Pomiary bieżące” shows only the layer of IMGW-PIB's current measurements and hides the station layer. Hydrological stations carry their water level, discharge and temperature and are filled by the snapshot's water state with hydro.imgw.pl's colours: alarm `#f00`, warning `#FFA500`, high `#FFEB09`, medium `#0A65C0`, low `#000`, below `#791919`, no water-state data `#CECEFF`, unknown `#fff`; a state older than 2 hours (up to 26) shows a hollow inner triangle, as there (today's `/map` function, `map.html:164-207`, gives the states). Meteorological stations carry their latest measurements (`current meteo`, located by the snapshot's coordinates) and are filled by precipitation: heavy `#f00`, precipitation `#2B60BD`, none `#289613`, no data `#CECEFF`. hydro.imgw.pl classes the last 6 hours, which no Obserwator function reads; until one does, the class comes from the latest sum of `current meteo` and the legend says so. Each point names its measurement time, and the bar names the snapshot's time. The water state is a live class of IMGW-PIB's current data, not an archived level (answer 3). Legend bottom-left, in the same symbols; zoom bottom-right (Nogat `design/README.md:187`). Without WebGL the map says so and the list and panel still work.

### D10. Left panel: search and filters

- Search by name, river or code, ignoring case and diacritics as `stations find` does (`src/obserwator/stations.py:340-343`), over the station layer in the browser.
- Filters: provider, kind, the datasets that hold the station (chips), active only.
- The list of matches includes stations without coordinates, marked „bez współrzędnych”, under counts („na mapie 4 140 · bez współrzędnych 2 156”); a click selects the station and the map flies to it when it has a location.
- The address keeps the state, as Archiwista's router does (Archiwista `src/archiwista/web/src/router.js:1-12`): `?station=<code>&section=<id>&dataset=<key>&variables=Q,H&from=…&to=…&year_type=…` and the options of an analysis, so a link opens the same view. Station codes are unique across providers (disjoint patterns, `AGENTS.md:11-12`).

### D11. Right panel: the station, by kind

Every view has the header (name, river, code, provider, kind, active or not), „Dane” and „Pobierz”; the other sections depend on the kind and show only what the station's data allow. Every analysis section shows Hydrolog's result with its method, source, series version and Hydrolog version, its (i) explanation, and „Otwórz w Hydrologu” where D13 applies. An analysis over a period runs over the whole record by default; the person may choose another period, computed on the fly (D8), and the choice shows „Zalecany minimalny okres: 30 lat”, marking a shorter period (the Nogat plan's D12).

Hydrological station:

| Section | Content | Nogat plan |
|---|---|---|
| „Dane” | H, Q, T daily, monthly and half-year: dataset, variables, range, „rok hydrologiczny \| kalendarzowy”, the chart and „Tabela”, units and definitions, flags (`missing` as gaps, `accumulated` and `no_phenomenon` marked), the attribution | — |
| „Teraz” | IMGW-PIB: the snapshot's values with their times and the water state; ČHMÚ: „Dane bieżące ČHMÚ nie są udostępniane” | — |
| „Stany charakterystyczne” | first degree per year and half-year; second degree over the whole record or the period the person chooses (on the fly); ČHMÚ's SPA, drought level and Q50 (IMGW-PIB's warning and alarm levels are not archived); the levels drawn on the H chart; days and events above each level | H1, H2, H3 |
| „Krzywa natężenia przepływu” | the fitted curve over the years the person chooses (on request), the curves of successive periods, ČHMÚ's published curve; the H–Q points coloured by year | H4 |
| „Przepływy maksymalne i minimalne” | quantiles of annual maxima and minima with the probability plot; the distribution and method the person chooses (on request); the source of the maxima | H5, H6, H16 (homogeneity) |
| „Niżówki” | low-flow periods per year with the threshold the person chooses (on request), the deficit, the longest period | H7 |
| „Czas trwania i strefy” | duration curves of H and Q, class frequencies with the modal class, Rybczyński's zones | H8, H9 |
| „Reżim i sezonowość” | daily regime curves, monthly statistics, Pardé coefficients and the regime type, the dates of annual extremes on a circular chart | H10 to H13 |
| „Temperatura wody” | the annual cycle and its harmonics, days above and below thresholds | H14, H15 |
| „Trendy i bilans” | trends with Sen's slope, runoff volumes, baseflow and its index | H16 to H18 |
| „Stacja” | the catalog's properties (location source and uncertainty, elevation, gauge zero, river km, hydrographic code, year established) and the coverage per dataset and variable | — |

Meteorological station:

| Section | Content | Nogat plan |
|---|---|---|
| „Dane” | P, Tmax, Tmin, Tmean, snow: as for hydrological stations, ČHMÚ's quality marks shown | — |
| „Teraz” | IMGW-PIB automatic stations from the snapshot | — |
| „Opady” | sums, normals and anomalies; maxima of 1 to 10 days and their quantiles beside PMAXTP of the point; means and the wet-day intensity; days at least 0.1, 1, 10 and 20 mm; the share of heavy precipitation; seasonality | M1 to M5, M7, M9 |
| „Susze i okresy bezopadowe” | dry and wet spells with the threshold the person chooses (on request); SPI and the relative precipitation classes | M6, M8 |
| „Temperatura” | means, extremes, normals and anomalies, characteristic days, degree days, the annual cycle and its harmonics, the hydrothermal coefficient | M11, M12, M14 |
| „Śnieg” | days with snow cover, maximum depth per winter, first and last day, fresh snow | M10 |
| „Trendy” | trends with Sen's slope of the annual series | M13 |
| „Stacja” | as for hydrological stations | — |

Charts are an own SVG module with Hydrolog's `charts/` as the model (its D12; Chart.js rejected there): pure functions for scales, ticks, the time axis, log and probability axes and decimation to the minimum and maximum per pixel column (a ČHMÚ daily series since 1887 has about 50,000 values); lines, steps, bars, a band for `{V}_min`/`_mean`/`_max`, reference lines, points, a circular (calendar) chart; zoom by a range and by keys, a readout by pointer and keys.

### D12. PMAXTP

The rail item „PMAXTP”: a point picked by a click on the map or by coordinates (the bounds of `fetch_pmaxtp`), POT or AMP. The map draws no layer of the PMAXTP grid, only the chosen point. The panel shows the results tables of today's page (`templates/partials/pmaxtp_result.html`). IMGW-PIB publishes no PMAXTP file for a point: klimat.imgw.pl/opady-maksymalne reads the JSON answer of `https://powietrze.imgw.pl/tpmax-api/point/{P|A}/KS/{lat}/{lon}` (the address `build_pmaxtp_url` builds) and writes its files in the browser; its other resources are PNG rasters (checked for the mockup on 2026-11-13). So the downloads go through the API by coordinates: the server fetches the point (`fetch_pmaxtp`, D8) and the browser packs the result into CSV and JSON, as today's page does; beside them, a link „Odpowiedź API IMGW-PIB (JSON)” opens the API's own answer for the point. Every table and file carries PMAXTP's formula „Źródłem pochodzenia danych jest Instytut Meteorologii i Gospodarki Wodnej – Państwowy Instytut Badawczy, dane pochodzą ze strony https://klimat.imgw.pl/opady-maksymalne”, for packed files its processed form („… pochodzące ze strony https://klimat.imgw.pl/opady-maksymalne zostały przetworzone”), and the citation of the monograph „Modele probabilistyczne opadów maksymalnych o określonym czasie trwania i prawdopodobieństwie przewyższenia – Projekt PMAXTP” (ed. B. Ozga-Zieliński, IMGW-PIB, Warszawa 2022, CC BY 4.0). It replaces `/download/pmaxtp`.

### D13. Hand-off to Hydrolog

„Kopiuj do Hydrologa” and „Plik przekazania” (DEV-15.5, the kit's `nogat-handoff.js`) beside the flood and low-flow quantiles, the characteristic values, the low-flow periods and the rating curve: `nogat-handoff/1` around `hydrolog-series/1` (the daily series or the annual maxima used), with the analysis's command and options in `provenance` and Obserwator's result (Hydrolog's numbers and version) in `result`, built by the server from the data root (as Archiwista builds its own, A-ADR-052). Hydrolog reads it through „Wczytaj z Obserwatora”, the Nogat plan's H5, and shows the producer's numbers beside its own.

### D14. Exports

| Export | How |
|---|---|
| Series, CSV | `export_series(format="csv")`, unchanged (UTF-8, comma, decimal dot, the attribution in the first data row) |
| Series, JSON | `export_series(format="json")`, new: `obserwator-series-export/1`, columnar, with units, definitions, the series version and the attribution; the chart reads the same document |
| Series, Parquet | `export_series(format="parquet")`, new: the CSV's columns typed, the licence, attribution, units and definitions in the file's metadata |
| Stations, GeoJSON | `export_stations(format="geojson")`, new: the current catalogs of the chosen providers, each feature with `provider` and the series that hold it, each provider's attribution as a member of the collection |
| Stations, CSV | `export_stations(format="csv")`, new: one row per station, the attribution columns of `series export` |
| Analysis results, CSV and JSON | `analyses export` (Nogat plan O2), with the station, series version, method, options and Hydrolog's version; a result computed on request downloads as its JSON with the same fields |
| PMAXTP | CSV and JSON written in the browser from the result the server fetched by coordinates, with PMAXTP's formula and citation, as today's page does; a link to the API's own JSON answer for the point (D12) |

Each series, stations and analysis download shows the equivalent command line (`format_command`, public, `docs/PROGRESS.md:27`), so the same file comes from the CLI, REST or MCP.

### D15. Identity, shell and texts

- `tokens.css` copied from Nogat with its commit in the leading comment (DEV-15.3), the marks (`obserwator.svg` as favicon and in the top bar, the others for the app menu), kit 0.1.0 (`nogat-app-menu.*`, `nogat-handoff.js`, `nogat-kit.json`) and `schemas/nogat/handoff-1.schema.json`, all byte for byte (DEV-15.6).
- The shell of Nogat `design/README.md:179-195`: the top bar (mark, „Obserwator”, the selected station, „PL | EN”, the app menu with the deployment's `[nogat.gui]`, the theme switch „Auto”, „Jasny”, „Ciemny” under the key `nogat-theme`), the rail („Stacje”, „PMAXTP”), `.view-layout` with resizable left (260 to 560 px, 300) and right (340 to 720 px, 400) panels that keys also resize, and bottom sheets at 860 px and below. This GUI does visual identity step 7.
- Texts (H1): the area `gui` of `obserwator.messages`, served by `GET api/texts?lang=`; Polish by default, English from the switch, remembered in `localStorage`; the (i) explanations of the analyses as entries of the same area, with their sources. Numbers and dates through `Intl` in the page's language; station names and rivers as published. A contract test: every `gui` key has both languages and no Polish literal is left in `gui/web/src/`. The kit's app menu stays Polish (kit 0.1.0).

### D16. Security

- Headers of every response: `Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self'; worker-src 'self'; img-src 'self' data: blob: <basemap origin>; connect-src 'self' <basemap origin>; font-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'` (Archiwista's builder, Hydrolog's list; the origin only when a basemap is set), `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer` (the tile server learns no page), `Cross-Origin-Opener-Policy: same-origin`, `Cross-Origin-Resource-Policy: same-origin`, `Permissions-Policy: camera=(), microphone=(), geolocation=()`; `Cache-Control: no-cache` on static files.
- GET and HEAD only (`405` otherwise); no cookies, no sessions, no CORS headers; Hydrolog's program gets only validated options and a series file the server wrote, never a path from the request.
- It binds 127.0.0.1 by default and has no sign-in: reachable beyond loopback only behind an authenticating proxy (Cloudflare Access), as `docs/USAGE.md` will say. Framing by a hub's origin comes with stage 2 (platform plan A1).

### D17. Tests

- Python, in the gate, offline: Starlette `TestClient` tests of every route, header, error status and cache rule on the fixture data root and on its read-only copy; snapshots and PMAXTP from recorded IMGW-PIB answers (the recorded-HTTP helpers of `obserwator.testing`); on-demand analyses against a recorded Hydrolog program (a test executable answering recorded envelopes), with its timeout and failure; the app mounted under a prefix; contract tests of the copied and vendored files' hashes, of no remote URL and no inline script or style in `gui/web/`, of both languages of the `gui` texts, of the new documents against their schemas in `schemas/`.
- With Hydrolog installed (a marker the gate runs where Hydrolog is present): a stored result and an on-demand one equal Hydrolog's own single call.
- Browser: Playwright for Python with Chromium in `tests/e2e/` (Hydrolog's and Archiwista's model): a live server on a free port, a test fails on any console error or `securitypolicyviolation`, widths 1440 and 390, both themes; pure modules through `page.evaluate(import(…))`, without Node. CI installs Chromium (`playwright install --with-deps chromium`).
- A `live` test asks IMGW-PIB (outside the gate). Coverage stays at 80 % or more (DEV-7.5).

### D18. Removal of the pages (B6)

After S7: `src/obserwator/web/` and `tests/unit/test_web_app.py` go; `obserwator server` keeps `/api/v1`, `/health`, `/llms.txt`, `/docs` and `/mcp`, and `GET /` redirects to `/docs`; the `api` extra drops Jinja2 and python-multipart; README, USAGE, ARCHITECTURE (section 5), CODEBASE, PRD (section 5 and the scope statement of `docs/PRD.md:13`), `CLAUDE.md` and `docker/Dockerfile:1` follow. `_environment.gui_addresses()` stays: the GUI gives its table to the page (DEV-15.4).

## Interfaces fixed by this plan

Python (S0, S1; the analyses' functions are the Nogat plan's O2):

```python
# obserwator, public (__all__), S0
def export_stations(root: RootArg | None = None, /, *, provider: str | None = None,
                    kind: Literal["hydro", "meteo"] | None = None, series: bool = True,
                    format: Literal["geojson", "csv"] = "geojson", output: PathArg | None = None,
                    force: bool = False, on_progress=None, on_notice=None,
                    cancel=None) -> OutputReport | Iterator[str]: ...
def export_series(..., format: Literal["csv", "json", "parquet"] = "csv", ...) -> OutputReport | Iterator[str]: ...
# obserwator.gui, extra gui, S1
def gui_module() -> GuiModule: ...    # name, title, web, index, sections, app
def create_app(*, root: Path | None = None) -> Starlette: ...
def serve(*, host: str = "127.0.0.1", port: int = 8060, root: Path | None = None,
          open_browser: bool = True) -> None: ...    # blocks until Ctrl+C or SIGTERM
```

- `export_stations(format="geojson")` gives `obserwator-stations-export/1`: an RFC 7946 FeatureCollection with the members `schema`, `catalogs` (provider, version label, `downloaded_at`) and `attribution` (per provider: the formula, the processed mark, the licence's id and URL, the terms' URL); each feature carries the catalog's properties, `provider` and, with `series`, the current series that hold the station, e.g. `{"pl.imgw.hydro_daily": {"first": "1951-11-01", "last": "2025-10-31", "variables": ["H", "Q", "T"]}}`. `format="csv"`: one row per station with the same properties, `latitude`, `longitude` and `datasets` (keys joined by `;`), and the attribution columns of `series export`, filled in the first row of each provider.
- `export_series(format="json")` gives `obserwator-series-export/1`: `dataset`, `provider`, `station`, `series_version`, `year_type`, `time_unit`, `variables` (`unit`, `note`), `attribution` and `columns` (`date`, `year` and, per variable, the value and flag arrays and the extra columns the CSV has). `format="parquet"`: the CSV's columns typed, with the metadata `obserwator_schema` (`obserwator-series-export/1`), `dataset`, `station`, `series_version`, `units`, `variable_notes`, `attribution` and `license`; it needs `output` in Python, the CLI and MCP; REST answers every format as an attachment. The CSV stays byte for byte.

Catalog (S0): `stations export`, new in the group `stations` (marks `[output: write; force: overwrite]`, REST `GET /api/v1/stations/export`, MCP `obserwator_stations_export`); `series export` gains the `format` values `json` and `parquet` (`commands.py:1068-1075`). Settings (S1): `OBSERWATOR_GUI_BASEMAP_URL`, `OBSERWATOR_GUI_BASEMAP_ATTRIBUTION` (`[obserwator] gui_basemap_url`, `gui_basemap_attribution`); `OBSERWATOR_HYDROLOG_COMMAND` is the Nogat plan's O2. CLI (S1): `obserwator gui serve [--host 127.0.0.1] [--port 8060] [--root PATH] [--no-browser]`, outside the catalog.

Private API of the GUI (S1, S6):

| Route | Answer |
|---|---|
| `GET api/session` | `obserwator-gui-session/1`: version; the data root (catalogs, series and analysis results in use with their version labels and dates, or the error); providers with their licence, formula, processed mark and notice; the basemap (URL, attribution) or none; the table `[nogat.gui]` (DEV-15.4); whether on-demand analyses are available (a configured Hydrolog program) and its version |
| `GET api/texts?lang=pl\|en` | the area `gui` of the message catalog |
| `GET api/stations` | `export_stations(format="geojson", series=True)` |
| `GET api/series/{dataset}/{station}?variables=…&start=…&end=…&year_type=…` | `export_series(format="json")` |
| `GET api/analyses/{station}` | the stored results of the station (the Nogat plan's O2 `analyses read`): analysis, dataset, series version, Hydrolog version, date |
| `GET api/analyses/{station}/{analysis}` | one stored result: Hydrolog's envelope with Obserwator's provenance |
| `GET api/compute/{analysis}/{station}?dataset=…&<options>` | one analysis with the person's options, computed by Hydrolog on request (D8), the same document as a stored result, marked „na żądanie” |
| `GET api/handoff/{analysis}/{station}?dataset=…&<options>` | the `nogat-handoff/1` document of D13 |
| `GET api/files/series/{dataset}/{station}?format=csv\|json\|parquet&…` | the file as an attachment, `<station>_<dataset slug>.<ext>` |
| `GET api/files/stations?format=geojson\|csv&provider=…&kind=…` | the file as an attachment |
| `GET api/files/analyses/{station}?format=csv\|json&analysis=…` | `analyses export` as an attachment |
| `GET api/line/{group}/{verb}?…` | `{"line": …}` from `format_command`, for `series export`, `stations export`, `analyses export` and `pmaxtp fetch` only |
| `GET api/current/{hydro\|meteo\|states}` | the snapshot with `fetched_at` and `stale` |
| `GET api/pmaxtp?latitude=…&longitude=…&method=POT\|AMP` | the result of `fetch_pmaxtp` with IMGW-PIB's attribution |

JavaScript (S2 to S7), every exported function with JSDoc:

```js
// src/api.js
api.session(); api.texts(lang); api.stations();
api.series(dataset, station, {variables, start, end, yearType, signal}); // obserwator-series-export/1
api.analyses(station); api.analysis(station, analysis); api.compute(analysis, station, options, {signal});
api.handoffUrl(analysis, station, options); api.fileUrl("series" | "stations" | "analyses", options);
api.line(command, options); api.current("hydro" | "meteo" | "states");
api.pmaxtp({latitude, longitude, method});
// src/ui/view-layout.js
html`<${ViewLayout} left=${{title, body}} center=${{bar, body}} right=${{title, body}} />`
// src/map/stations.js
stationLayer(map, collection, {filters, selected, mode: "stations" | "current", onSelect});
// src/charts/chart.js
html`<${Chart} spec=${{x: {kind: "time" | "linear" | "log" | "probability" | "calendar"}, y: {label, unit},
                       series: [{id, kind, data, cls, label}], marks, readout}} />`
// src/sections/<kind>/<section>.js, registered by one line in src/sections/index.js
export default function Section({station, results, compute}) {}
```

## Steps

Producers before consumers (HUB-5.2): the Nogat plan's O1 (the data root), O2 (the stored results, after Hydrolog's computations) and this plan's S0 (its O3) come before the slices that read them. Sizes are in sessions; S1 to S9 are the Nogat plan's O4.

| # | Owns | Provides and acceptance | Size | After |
|---|---|---|---|---|
| S0 | `store/export.py`, `commands.py`, `__init__.py`, `messages/{commands,export,datasets}.py`, `api/routes/commands.py` (a binary attachment), `schemas/` (two documents), `AGENTS.md`, `llms.txt`, ADR-012 (the GUI: D2 to D18) and ADR-013 (the exports) in `docs/DECISIONS.md`, `docs/USAGE.md`, `docs/CODEBASE.md`, their tests | `export_stations` and `stations export`; `series export` as JSON and Parquet; IMGW-PIB variable definitions where IMGW-PIB's format descriptions give them (none invented). Acceptance: the fixture's IMGW-PIB and ČHMÚ stations in one GeoJSON valid against RFC 7946 and its schema, and in the CSV; a series' JSON and Parquet hold the values and flags of its CSV; the CSV unchanged byte for byte; the Python = CLI = REST = MCP contract tests; `AGENTS.md` within its budget in both languages | 2-2.5 | the Nogat plan's N1 |
| S1 | `src/obserwator/gui/*.py`, `cli/main.py` (`gui serve`), `config.py`, `messages/gui.py`, `pyproject.toml`, `uv.lock`, `.github/workflows/ci.yml` (Chromium), `CLAUDE.md` (the exception, the AGI-6.1 deviation), `tests/unit/gui/`, `tests/integration/gui/`, `tests/e2e/conftest.py` | D4 to D8 and D16 without the analyses' routes, `gui_module`, `serve`. Acceptance: `TestClient` tests of every route, header, refused method and parameter, error status and cache rule on the fixture data root and its read-only copy; the app mounted at `/m/obserwator/` serves the page and the API; `obserwator gui serve --no-browser` answers on 8060 and stops with exit 0; the `nogat.gui` entry point loads; RSS after warm-up and the p95 of `api/stations` and `api/series` recorded in PROGRESS | 2-2.5 | O1, S0 |
| S2 | `gui/web/{index.html,theme-init.js}`, `gui/web/nogat/`, `gui/web/vendor/`, `gui/web/css/app.css`, `gui/web/src/*.js`, `gui/web/src/ui/`, `tests/e2e/test_shell.py`, `tests/contract/test_gui_web.py` | the shell, theme, language switch, router with the address state, API client, texts, layout with resizers and sheets, status and errors. Acceptance: the page loads in both themes and at 390 px without a console error or CSP violation; the hashes of every copied and vendored file are checked; `?nogat=1` hides the top bar and the rail before the first paint | 2-2.5 | A1 of the Nogat plan |
| S2b | `gui/web/src/charts/`, `gui/web/css/charts.css`, `tests/e2e/test_charts.py` | `Chart`: time, log, probability and calendar axes, lines, steps, bars, band, reference lines, decimation, zoom, readout. Acceptance: scales, ticks and decimation tested as pure functions; 50,000 daily values drawn in under 200 ms in Chromium at 1440 px; the readout works by keys | 1.5-2 | A1 of the Nogat plan |
| S3 | `gui/web/src/map/`, `gui/web/src/sections/stacje/{map,list,filters}.js`, `gui/web/css/map.css`, `tests/e2e/test_map.py` | D9, D10. Acceptance: the fixture's stations of both providers on the map and those without coordinates in the list with their count; search ignores case and diacritics; the filters; „Pomiary bieżące” from recorded hydro and meteo snapshots shows both kinds and hides the station layer, and „Stacje” brings it back; the symbols and legend of D9; the borders without a basemap; a copied address opens the same selection | 2-2.5 | S1, S2 |
| S4 | `gui/web/src/sections/{panel,dane,teraz,stacja}.js`, `tests/e2e/test_station.py` | D11's „Dane”, „Teraz” and „Stacja” for both kinds. Acceptance: the fixture's IMGW-PIB daily series shows H, Q and T with flags and the year switch, and its table equals the CSV; a meteorological station shows P and temperatures; a ČHMÚ station shows its thresholds and „Dane bieżące ČHMÚ nie są udostępniane”; current values from a recorded snapshot with their time | 2-2.5 | S1, S2, S2b; lands after S3 |
| S5 | the analyses' routes of the API, `gui/web/src/sections/hydro/`, `tests/e2e/test_hydro_analyses.py` | D11's hydrological sections, on-demand computations (D8), the hand-off (D13). Acceptance: every section of the fixture's IMGW-PIB and ČHMÚ station shows the stored result of O2 with its provenance; a chosen range of years refits the rating curve through the recorded Hydrolog program; a flood quantile equals Hydrolog's single call; the hand-off validates against `handoff-1` and `hydrolog-series/1` | 2.5-3.5 | S4, O2 |
| S6 | `gui/web/src/sections/meteo/`, `tests/e2e/test_meteo_analyses.py` | D11's meteorological sections. Acceptance: every section of the fixture's IMGW-PIB climate station and ČHMÚ station shows the stored result; a dry-spell threshold chosen by the person recomputes through the recorded Hydrolog program | 1.5-2 | S5 |
| S7 | `gui/web/src/sections/{pobierz,pmaxtp}/`, `tests/e2e/test_files.py`, `tests/e2e/test_pmaxtp.py` | D12, D14. Acceptance: every download equals, byte for byte, the catalog command's output for the same options, and the shown command line gives the same file; PMAXTP of a recorded point, picked on the map and by coordinates, shows the tables of today's page with no grid layer, downloads CSV and JSON with the formula and citation, and links the API's answer for the point (D12) | 1.5-2 | S0, S3, S4, O2 |
| S8 | `src/obserwator/web/` (removed), `api/main.py`, `pyproject.toml`, `uv.lock`, `tests/unit/test_web_app.py` (removed), `docker/Dockerfile`, `README.md`, `docs/{USAGE,ARCHITECTURE,CODEBASE,PRD}.md`, `CLAUDE.md` | D18. Acceptance: the REST and MCP tests green; `GET /` redirects to `/docs`; Jinja2 and python-multipart leave the lock unless another package needs them | 1 | S7 |
| S9 | `gui/web/instrukcja/`, the top bar's „Instrukcja”, `docs/USAGE.md` (a „GUI” section), `README.md`, `docs/PROGRESS.md`, `tests/e2e/test_smoke.py` | the guide in Polish (what the GUI shows, the analyses and their sources, the licences and how to cite them, the formats); USAGE in English, with running the GUI behind an authenticating proxy. Acceptance: every view opens without a console error in both themes and on a phone; the guide's examples work on the fixture data root | 1-1.5 | S8 |

Waves: **A** = S0, S2, S2b in parallel, then S1 when O1 lands; **B** = S3, S4 (landing order S3, S4); **C** = S5, S6 when O2 lands; **D** = S7, S8, S9. S1 to S9 take about 17 to 22 sessions (the Nogat plan's O4) and S0 2 to 2.5 (its O3).

Outside Obserwator, by the Nogat plan: N2 gives the registry `interfaces.gui: obserwator gui serve`, the route „Open Obserwator's GUI in the browser” and the routes of the new commands; the tunnel host `obserwator-test.debever.pl` and its Access exist already (the author's); the author places the roots (the Nogat plan's A2), answers IMGW-PIB's terms (its question 4) and merges `feature/gui` into `develop` (DEV-3.3).

## Deployment

1. After wave B, the user unit `obserwator-public.service` changes from the placeholder (`python3 -m http.server 8060 … placeholder`) to `<integration worktree>/.venv/bin/obserwator gui serve --no-browser --host 127.0.0.1 --port 8060 --root <Obserwator's production data root, the Nogat plan's D2>` with `TMPDIR=/home/claude-agent/data/tmp` and `OBSERWATOR_HYDROLOG_COMMAND=/home/claude-agent/workspace/Hydrolog-gui/.venv/bin/hydrolog` (the Hydrolog of hydrolog-test, so both give the same numbers), after `uv sync --locked --all-extras` in that worktree, as `hydrolog-gui.service` runs Hydrolog's; it is restarted after each landing. The host's `nogat.toml` already gives the other GUIs' menus the address, and the tunnel host and Access exist.
2. Smoke through the public address after each wave: the Access sign-in; the map with both providers; a station's chart and table of each kind; „Pomiary bieżące” with hydrological and meteorological stations and the station layer hidden; an analysis of each section; a rating curve over a chosen range of years; a flood quantile equal in Obserwator and in Hydrolog after the hand-off; a CSV, JSON and Parquet download read back with pandas; PMAXTP of a point; `curl -sI` shows the headers of D16; a phone at 390 px; no console errors.
3. On the VPS later: the same unit, the data root copied there, Hydrolog installed beside; the RSS and p95 recorded in S1 show whether anything needs tuning.

## Risks

| Risk | Effect | Mitigation |
|---|---|---|
| 2,142 of the 3,810 IMGW-PIB stations of the test store have no coordinates | „wszystkie stacje na mapie” holds for ČHMÚ and the current IMGW-PIB stations only | the list and search reach every station, with the count; IMGW-PIB's official list (`docs/PROGRESS.md:73`) |
| IMGW-PIB's terms on a public instance | data and results published beyond the terms | an Access-limited audience until the Nogat plan's open question (its question 4, „do sprawdzenia”) is answered; the formula, processed mark and notice beside every series, result and file |
| Load on IMGW-PIB from a public page | the source slows or blocks the host | snapshots at most every 10 minutes, single-flight, the PMAXTP cache and one request at a time; the page itself never calls a provider (the link to the PMAXTP answer is the person's own request) |
| On-demand computations on a 4 vCPU, 8 GB VPS shared by four apps | slow answers, memory | at most two Hydrolog processes, 30 s each, a result cache in memory only; stored defaults over the whole record cover the first view of every section |
| The slices wait for the Nogat plan's O1 and O2 | a late GUI | S0, S2 and S2b start at once; the analysis sections come last (wave C) |
| Two GUIs draw a station's series | people ask which to use; the two drift apart | D3; the guide says what each app is for |
| A third chart module and basemap style in the ecosystem | duplicated work, a diverging look | pure modules, ready for the kit's `chart-theme.js` and `basemaps.json` (platform plan, step 3) |
| `AGENTS.md` at 16,094 of 16,384 bytes | the new commands' lines do not fit, in English or in Polish | S0 and O2 shorten other lines; the budget test fails early |
| OpenFreeMap unavailable or limited | no basemap | the packaged borders as the offline background; the basemap is a setting |
| Playwright on three CI systems | slow or flaky CI | Chromium only, Hydrolog's and Archiwista's fixtures as the model |
| Copies of the kit and the tokens drift | the look, the menu and the hand-off split again | the hashes and Nogat's `drift` (DEV-15.6) |
| Parallel slices of one branch | conflicts | owned files, one integration owner, a rebase and the gate per landing |

## Decided (2026-11-13)

The cross-project questions are the Nogat plan's; its „Decided (2026-11-13)” records the answers (B1; the raw root and the data root's backup in Archiwista, the production data root in Obserwator; computed once, refreshed yearly, subsets on the fly and never stored; no IMGW-PIB warning and alarm levels; the whole record by default with the 30-year note). IMGW-PIB's terms on the public instance stay open there (its question 4). This plan's question:

1. **Spreadsheets.** No XLSX: CSV (comma, decimal dot), JSON and Parquet (G6, D14). The PMAXTP page's SheetJS goes with the pages (D18).

Decided here, open to the author's veto: port 8060 (the placeholder's); Polish by default and English through the switch (no deviation from DEV-2.2); IMGW-PIB's synop data and warnings left out (warnings name areas, not stations); the page of archive links and its wget script dropped; `GET /` of `obserwator server` redirecting to `/docs`; the app menu's line for Obserwator, „Dane IMGW-PIB i ČHMÚ, PMAXTP” (Nogat `design/kit/nogat-app-menu.js:15`), unchanged.

## Not in this plan

The roles, the data root, the stored analyses and Hydrolog's computations (the Nogat plan's steps N1, H1 to H5, R1, R2, O1, O2); „Zgłoś uwagę” (Nogat plan `2026-11-03-feedback-in-archiwista-and-hydrolog.md`; reports need a store, and Obserwator keeps no database, `CLAUDE.md:11`); a link into Archiwista's station card (`/?view=catalog&station=<store>/<provider>/<code>`, Archiwista `src/archiwista/web/src/views/catalog-stations.js:250-251`), which needs Archiwista's store id and a published address; exports of several stations in one file; IMGW-PIB synop and warnings; IMGW-PIB's warning and alarm levels (operational data, not archived); ČHMÚ current data (`AGENTS.md:9`); the native PMAXTP grid (`docs/PROGRESS.md:62`) and any layer of it on the map; coordinates of closed IMGW-PIB stations (`docs/PROGRESS.md:73`); an English guide; the hub itself (platform plan, steps 8 to 10).
