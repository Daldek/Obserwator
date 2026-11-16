# Plan: Operational hydro series: a nightly harvest, the monthly telemetry and a chart of the current readings

Approved: pending

Requirements: DEV-17.4 (no code before approval), DEV-20.1, DEV-20.5, DEV-20.8 (to be amended, step N0), DEV-13.2, ECO-059, ECO-060. Amends ADR-015 D5 and ADR-003 D4 of this repository (a new ADR-024). Inputs: the author's idea of 2026-11-16 (below); the probes of 2026-11-16 (report `obserwator-oper.md` of that session, files in `/data/nmt/e2e-2026-11-15/tmp/oper-check/`), including the comparison for Głogów 151160060 (`cmp_151160060_*.json`).

Status: draft of 2026-11-16, investigation only. No code begins until (1) Nogat amends DEV-20.8 (step N0) and (2) this plan's `Approved:` line is filled in. The blocking point is the rule „operational data are never stored” in Nogat DEV-20.8 and this repository's ADR-015 D5; the providers' terms do not forbid it (see „Terms of use”).

## The author's idea (2026-11-16)

- The current readings („Pomiary bieżące”) get a chart like the station page of hydro.imgw.pl.
- When a person opens a station, the missing data are fetched on demand: only the difference since the last stored timestamp.
- Every night the last day's data of every station are fetched through the API. The requests are spread over several night hours so that IMGW-PIB and the other providers are not loaded. This builds our own database of the current period: unverified, operational data.
- Once a month the telemetry package (`Hydro_YYYY-MM.zip`, 10-minute step) is added.
- Later, when IMGW-PIB publishes the verified set, the record is continuous.
- The same applies to ČHMÚ if it fits (`hydrology/recent|now` JSON).

## Facts (probed 2026-11-16)

| Source | What | Span and step | Stations | Lag |
|---|---|---|---|---|
| `hydro-back.imgw.pl/station/hydro/status/data?id=<code>&hoursInterval=<h>` (header `Referer: https://hydro.imgw.pl/`) | `operational` water level (H) | Hourly; only about the last 2 h at 10 min. Seen back to 2026-08-16 with `h=2200`; the terms promise „do 6 tygodni wstecz” | about 878 | live |
| `…/station/hydro/discharge?id=…&hoursInterval=…` | `operational` discharge (Q) | the same | about 659–682 | live |
| `…/station/hydro/water-temperature?id=…&hoursInterval=…` | `operational` water temperature (T, `B00100S`) | Hourly at automatic stations (149180080). One reading a day at 06:00 UTC at others (Głogów, 22/22) | about 81–83 | live |
| `danepubliczne.imgw.pl/datastore/getfiledown/Arch/Telemetria/Hydro/<YYYY>/Hydro_<YYYY-MM>.zip` | `B00020S`, `B00050S`, `B00100S` CSV `KodSH;Param;YYYY-MM-DD HH:MM;value` (`999` = missing) | 10 min, one zip per month for all stations (October: 17.6 MB, 3.75 M + 2.96 M + 0.18 M rows) | 878 / 682 / 83 | October built 2026-11-12, so about 12 days after the month ends |
| `danepubliczne.imgw.pl/data/dane_pomiarowo_obserwacyjne/dane_hydrologiczne/` | verified daily, monthly and semi-annual data (`pl.imgw.hydro_*`, already in the store) | daily | about 900 | hydrological year 2025 published 2026-08-31, about 10 months after it ended |
| `opendata.chmi.cz/hydrology/now/data/<WIGOS>.json` | H, Q, `TH` (plus forecasts `H_F`, `Q_F` at some stations) | the current UTC day, 10 min, rewritten every 20 min | 548 | live |
| `opendata.chmi.cz/hydrology/recent/data/<YYYYMMDD>_<WIGOS>.json` | the same, one file per station and day | from 1 January of the year, written at 00:40 the next day | 548 (Q about 500, TH about 250, estimated from file sizes) | 1 day; „následně kontrolují a validují” (they may change) |

Comparison for Głogów 151160060, October (made by Main): the full-hour values of hydro-back's `operational` equal the 10-min telemetry exactly, 744 of 744 for H and Q, with 0 differences. The temperature was 22 of 22 daily readings at 06:00 UTC. The telemetry lacked one 10-min record. So the hourly series is an exact subset of the telemetry, and the monthly zip replaces it without any change of values.

## Terms of use

### hydro.imgw.pl

Source: the regulamin (`https://hydro.imgw.pl/#/regulamin`). The SPA loads its text from `https://hydro.imgw.pl/assets/i18n/pl.json`, key `REGULATIONS`.

- p2: „Udostępnia dane operacyjne do 6 tygodni wstecz.”
- p3: „Serwis posiada otwarty dostęp dla wszystkich użytkowników, jednakże korzystanie z Serwisu wymaga akceptacji poniższych … warunków”.
- p4: „Użytkownik może używać nieodpłatnie udostępnionych informacji jedynie do celów prywatnych. Wykorzystywanie informacji pochodzących z IMGW-PIB dla potrzeb działalności gospodarczej, na stronach internetowych zawierających reklamy lub do celów: … badania elementów hydrologicznych i morfologicznych wód powierzchniowych na potrzeby planowania w gospodarowaniu wodami … bez zawarcia umowy i ponoszenia określonych w niej kosztów utrzymania sieci pomiarowej stanowi wprost naruszenie art. 385 ust. 5 Ustawy … Prawo wodne”.
- p4: „Brak wskazania źródła danych, brak zamieszczenia informacji o przetworzeniu danych … może skutkować odpowiedzialnością”.
- **Nothing** is said about automated or bulk retrieval, request rates, storage or keeping copies. `hydro-back.imgw.pl` is the site's own backend, not a published API.

### danepubliczne.imgw.pl

Source: `https://danepubliczne.imgw.pl/pl/regulations`, also published as PDF. These terms cover `api/data/hydro` and the datastore `Arch/Telemetria`.

- § 1: „Niniejszy regulamin stanowi ofertę. Przyjęcie oferty następuje poprzez przystąpienie do korzystania z udostępnionych danych.”
- § 2 pkt 2: „cel prywatny – użycie danych do celów prywatnych, niezarobkowych, w tym do celów prac magisterskich lub doktorskich”.
- § 2 pkt 3: „cel działalności gospodarczej – … w tym publikacja danych … na stronach internetowych, zawierających reklamy”.
- § 5 ust. 1: „Korzystający może używać nieodpłatnie udostępnionych danych do celów prywatnych, a w przypadku danych o wysokiej wartości w każdym celu.”
- § 5 ust. 3 and 4: the lines „Źródłem pochodzenia danych jest …” and „… zostały przetworzone”.
- § 6 ust. 3: „Część udostępnianych danych może stanowić dane niezweryfikowane”.
- § 8 ust. 2: „Wniosek może dotyczyć umożliwienia korzystania w sposób stały i bezpośredni w czasie rzeczywistym z danych gromadzonych i przechowywanych w systemie teleinformatycznym IMGW-PIB.”
- The telemetry folder's own `opis_1.1.txt` says: „Dane pomiarowe prezentowane w poniższych katalogach, należy traktować jako dane operacyjne”. It also points to hydro.imgw.pl's terms („posiada własny regulamin udostępniania danych”). The file `kody_parametr_hydro_1.1.csv` description adds: „nie może być wykorzystywany w sprawach sądowych”.
- **Nothing** is said about automated download, rate or storage. The datastore files are offered for download.

### ČHMÚ

Source: `https://www.chmi.cz/o-chmu/produkty-a-sluzby/data-a-vyhodnoceni`.

- „Otevřená data ČHMÚ můžete využívat bezplatně při respektování licence Creative Commons BY 4.0”.
- The same page announces „API rozhraním pro automatické stahování publikovaných dat”, so automated download is intended.
- `hydrology/hydrologicka_data_now_a_recent_popis.pdf`: now and recent data are „operativní nevalidované”. Recent data „se následně kontrolují a validují. Po uplynutí jednoho kalendářního roku jsou postupně nahrazena daty historickými.”

### Verdict

- **No provider clause blocks a polite nightly harvest or keeping the data.** ČHMÚ is CC BY 4.0, with the lines C/CP already carried. For IMGW-PIB both regulamins allow free use only „do celów prywatnych” (private, non-profit), with attribution and a processing note; use for business, on sites with ads, or for water-management planning needs a contract.
- **What blocks is internal:** Nogat DEV-20.8 („never stored or presented as archive … no project keeps them”) and ADR-015 D5. These need the author's amendment (step N0).
- **Flags for the author:**
  - (a) Serving the stored operational series on the public instance falls under the open question already in PROGRESS („IMGW-PIB's terms for serving its series … on the public instance”). The public GUI stays behind Cloudflare Access until it is answered.
  - (b) Use by Nogat tools for water-management planning (Hydrograf, Hydraulik) could fall under the purpose that needs a contract.
  - (c) hydro-back is an undocumented backend. The formal path to continuous access is a request under § 8 ust. 2 (biznes@imgw.pl), or cash@imgw.pl for hydro.imgw.pl.

## Where it starts (`develop` `f4f6a8d`)

- **Rule:**
  - ADR-015 D5 (`docs/DECISIONS.md:749`): „No operational data … «danych operacyjnych nie archiwizujemy»”. `pl.imgw.hydro_now` keeps only `kept_fields` (`src/obserwator/datasets.py:657-677`, applied in `store/writer.py:1664-1670`).
  - ADR-003 D4 (`docs/DECISIONS.md:227`): ČHMÚ `now`/`recent` are out of scope.
  - Nogat `standards/DEVELOPMENT_STANDARDS.md:1131` (DEV-20.8) and `standards/DECISIONS.md:1191-1215` (ECO-060).
- **Live data:**
  - `current hydro` (`src/obserwator/commands.py:748-764`, `fetch.py:469-509`) gives one snapshot of `api/data/hydro`. `current hydro-states` (`commands.py:820-837`, `stations.py:490-528`) gives the hydro-back map.
  - `_hydro_details` (`stations.py:546-604`) already walks hydro-back one station at a time with the required headers.
  - The `current` group is IMGW-PIB only (`commands.py:175`).
- **Store (ADR-017, `docs/ARCHITECTURE.md:226-252`):**
  - Append-only versions under `archives/versions/…` (raw root) and `series/versions/<slug>/<label>_<sha8>/` (data root). Publication is by unique staging and no-replace hard links (`store/writer.py:187-403`). There is no pruning.
  - Concurrent writers are safe (`ARCHITECTURE.md:349`). The slot `series:<key>` is one version for the whole dataset.
- **Series:**
  - `_station_table` (`store/series.py:819-879`): columns `date` (date32), `hydro_year`, `<var>_value`, `<var>_flag`, optional `_quality`/`_source_flag`. There is no time of day and no provenance column.
  - `series build` accepts `time_unit` `day|month|half_year` only (`commands.py:163-167`).
- **GUI:**
  - It reads the data root read-only (ADR-013 D5, `docs/DECISIONS.md:674`).
  - Live snapshots are in memory, at most once per 10 min, single-flight (`gui/_live.py:79-110`, `ARCHITECTURE.md:173`).
  - The „Pomiary bieżące” API is `gui/_app.py:618` (routes `:1467-1468`). The station card „teraz” is `gui/web/src/sections/teraz.js:34` (`HydroNow`). The SVG charts are in `gui/web/src/charts/` (`chart.js`, `draw.js`).
- **Scheduling:** none. `gui serve` runs no background job (`gui/_serving.py:116-118` only opens a browser), and docker has a health check only (`docker/Dockerfile:36-37`).
- **Politeness:** `fetch.py:77-90` sets timeouts and `User-Agent: obserwator/<version>`. There are no delays and no rate limiter.
- **Consumers (Nogat `ecosystem.yaml`):**
  - Archiwista (`:489`) reads `obserwator-store/1`, `obserwator-series/1` and `obserwator-data/1`, and indexes the series by `time_unit` (Archiwista `index/writer.py:1300`, `index/queries.py:1533`).
  - Hydrolog (`:295`) reads `obserwator-series-csv` (column `date`).
  - Retman (`:434`) reads the command catalog.

## Obserwator only, or a Nogat plan?

**Cross-project, with this plan as Obserwator's part:**

- DEV-20.8 is a Nogat standard („no project keeps them”), so only Nogat can amend it (N0).
- The new sub-daily series and their `time_unit` change what Archiwista indexes and shows (A1).
- In Nogat, Archiwista keeps the raw root and orders downloads through Obserwator's library (Nogat plan 2026-11-12 D2, D5; `ARCHITECTURE.md:304`), so who runs the nightly job is a role question (Q3).
- Hydrolog is untouched: analyses keep reading verified daily series (D6).

Nogat's step N0 is small: an amended DEV-20.8 plus an ECO decision. Archiwista's step A1 follows this plan's interfaces.

## Decisions proposed

### D1. Three tiers, separate datasets

| Tier | Dataset (raw root) | Source | Step |
|---|---|---|---|
| verified | `pl.imgw.hydro_daily` (exists), `cz.chmi.hydro_daily` (exists) | danepubliczne, ČHMÚ historical | day |
| telemetry | `pl.imgw.hydro_telemetry` (new) | `Arch/Telemetria/Hydro/<YYYY>/Hydro_<YYYY-MM>.zip`, verbatim | 10 min |
| operational | `pl.imgw.hydro_operational` (new) | hydro-back `status/data`, `discharge`, `water-temperature` | hour (10 min for the last 2 h, dropped) |
| operational | `cz.chmi.hydro_recent` (new) | `hydrology/recent/data/<YYYYMMDD>_<WIGOS>.json` | 10 min |

A tier is a property of the dataset (`DatasetDescriptor.tier`), never inferred from values.

### D2. Amendments

- **N0 (Nogat).** DEV-20.8 becomes: operational data MAY be stored as a labelled, unverified tier, always presented with their tier and never as the verified archive. Live-only rules stay for warnings and water-state classes.
- **ADR-024 (here).** It amends ADR-015 D5 (operational measurements of `pl.imgw.hydro_operational` and `cz.chmi.hydro_recent` are kept, as derived files of measurements only; forecasts, states, notes and thresholds are still never kept) and ADR-003 D4 (`recent` comes into scope; `now` stays live only). It adds errata in both.

### D3. Raw root: what is kept

- **`pl.imgw.hydro_operational`:** one derived file per UTC day, `operational/<YYYY-MM-DD>.json`. It is a JSON list of `{id, parameter (B00020S|B00050S|B00100S), points: [{date, value}]}` for the full hours of that day, with only the `operational` arrays (dotted `kept_fields` as in ADR-021). The derived form follows ADR-015 D5's exception. A day re-harvested (on-demand or a backfill night) with other bytes becomes a new version of that day.
- **`pl.imgw.hydro_telemetry`:** the monthly zip verbatim (ADR-001), `update_signal` `listing` (POST `datastore/getFilesList`, `productType=arch`, `path=/Arch/Telemetria/Hydro/<YYYY>`).
- **`cz.chmi.hydro_recent`:** per day, one file gathering the 548 station answers without `H_F`/`Q_F` (the forecasts are not measurements). The canonical form is `chmi-json/1` with `_CHMI_VOLATILE`. A re-fetch with other content (ČHMÚ validates `recent`) becomes a new version.

### D4. Data root: sub-daily series

- **New series slugs:** `pl.imgw.hydro_subdaily` and `cz.chmi.hydro_subdaily`. Each joins its provider's telemetry and operational datasets.
- **Columns:** `time` (timestamp[us, UTC]), `<var>_value`, `<var>_flag`, and **`<var>_tier`** (dictionary `telemetry|operational`) for each of `H`, `Q`, `T`.
- **Schema:** a new contract `obserwator-subdaily/1`. `obserwator-series/1` and the daily series stay unchanged, so Hydrolog and today's readers are unaffected.
- **Slots per month:** `series:pl.imgw.hydro_subdaily:<YYYY-MM>`. A night rebuilds only the current month (about 900 small Parquet files) rather than the whole history, which keeps append-only growth bounded (see D11).
- The new `time_unit` values are `hour` and `10min`. `commands.py:163-167` widens to accept them for these slugs.

### D5. Precedence and replacement

- **Within the sub-daily series:**
  - telemetry > operational, per station, variable and month. When `Hydro_<YYYY-MM>.zip` is published, that month's series version is rebuilt from telemetry alone. Operational points remain only where the telemetry has no record (`999` or missing; the one missing 10-min record of Głogów stays an hourly operational point with tier `operational`).
  - ČHMÚ has no telemetry tier. A newer version of a `recent` day replaces the older one.
- **Across resolutions:** verified daily > a daily mean of sub-daily data. The verified daily series stays the archive. The sub-daily series is never aggregated into it and never edits it.
- **For a day that has a verified value:**
  - The GUI shows the verified value as the record.
  - The sub-daily line is still drawn with its tier label, because it is the only intra-day record.
- **„Continuous measurements”:** verified daily up to the last published hydrological year, then telemetry months, then operational days up to yesterday, then the live tail.

### D6. Resolutions

- The data keep their native steps: verified daily, telemetry 10 min, operational hourly. Nothing is resampled in the store.
- The chart draws each tier at its own step.
- The analyses (Hydrolog) read only the verified daily series. Operational data never enter an analysis.

### D7. Nightly job

- **The command:** `obserwator store sync --dataset pl.imgw.hydro_operational --dataset cz.chmi.hydro_recent --days 1 --pace auto`, then `obserwator series build --dataset pl.imgw.hydro_subdaily --dataset cz.chmi.hydro_subdaily --months current`.
- **The schedule:** run by a **systemd timer** (`obserwator-operational.timer`, `OnCalendar=*-*-* 00:30 UTC`, `RandomizedDelaySec=20min`, `Persistent=true`), oneshot service, as the store's owner.
- **Why a systemd timer:**
  - `gui serve` is a read-only reader of the data root (ADR-013 D5). Writing from a public process widens its rights.
  - A restart or a second worker would duplicate or lose a run.
  - systemd never starts a second instance of an active oneshot unit, so it serialises the runs itself.
- **Missed nights:** `--days N` (N ≤ 40, inside the „6 tygodni” of the terms) backfills from the last stored day. hydro-back answers `hoursInterval=24·N+1` with one request per station and parameter.
- **Who runs it in Nogat:** Obserwator's CLI or Archiwista's job runner (Q3).

### D8. Monthly telemetry job

- **Daily check:** the same timer checks the listing of `Arch/Telemetria/Hydro/<YYYY>` (one POST). When a new month appears, it downloads the zip (one request, about 18 MB) and rebuilds that month's sub-daily slot.
- **The month after:** expected around the 12th. Until then the operational days fill it.

### D9. On-demand delta in the GUI

- **When a station's card opens:** the GUI server reads the last `time` of the station in the current sub-daily series. If it is older than the current hour, the server fetches hydro-back for that station only. The request is `hoursInterval = ceil((now − last)/1 h) + 1`, capped at 1 000 h. ČHMÚ's delta is `now/data/<WIGOS>.json`, plus `recent` days if more than one is missing.
- **Kept in memory only, never written:**
  - Per station, with a TTL of 10 min (as `_live.py`), at most 500 stations.
  - Single-flight per station, at most one live request at a time for the whole server.
  - So the GUI stays read-only, and the nightly job remains the only writer.
- **Persisting on-demand data:** the author's „only the difference since the last stored timestamp” is satisfied for the request. Persisting the on-demand delta is Q2.

### D10. Locking

- **One writer:** the timer's oneshot unit. Store publication is already safe for concurrent writers (unique staging, no-replace links).
- **A manual run during the night run:** a manual `store sync` of the same datasets takes `flock` on `<state_dir>/obserwator/operational.lock`. The second process fails with the existing `ObserwatorStoreConflictError` (code `conflict`, exit 4, HTTP 409; `exceptions.py:76`, „busy lock” in its docstring at `:232-239`) instead of interleaving the night's pacing.
- **The GUI** never writes (D9), so it never takes the lock.

### D11. Rate limiting and load budget

- **Pacing in the library:** `--pace auto` spreads the night's requests evenly over a window (default 01:00–05:00 local, 4 h). There is one request at a time, `Accept-Encoding: gzip`, and the existing timeouts.
- **Backoff:** on a 429 or 5xx it backs off exponentially (60 s, 120 s, 240 s, then the station is skipped and retried the next night). Three consecutive connection errors stop the night with `partial`.
- **User-Agent:** `obserwator/<version> (+contact URL)`.

| Item | Requests | Wire (gzip) | Kept (derived) |
|---|---|---|---|
| IMGW-PIB `status/data` (H), about 880 stations, `hoursInterval=25` | about 880 | about 5 KB each (32 KB plain, mostly forecasts), so about 4.4 MB | about 1.5 KB per station-day |
| IMGW-PIB `discharge` (Q), about 680 stations | about 680 | about 0.5 KB each, so about 0.35 MB | about 1 KB |
| IMGW-PIB `water-temperature` (T), about 85 stations | about 85 | about 0.6 KB each, so 0.05 MB | under 1 KB |
| **IMGW-PIB per night** | **about 1 650 (at most 2 700 if every station is asked for all three)**; one every **5–9 s** over 4 h | **about 5 MB** | about 2–3 MB per day, so about 1 GB a year |
| ČHMÚ `recent` day, 548 files | 548, one every 6.5 s over 1 h (02:00–03:00) | about 9 MB (15 Nov: 9.04 MB) | about 6 MB without forecasts, so about 2.2 GB a year |
| IMGW-PIB telemetry, monthly | 1 listing POST a day + 1 zip a month | 17.6 MB a month | 17.6 MB a month (verbatim) |
| Sub-daily series (data root), nightly version of the current month | — | — | about 25 MB per night version. With no pruning that is about 0.75 GB a month of superseded versions (R3) |

Which stations have Q and T comes from the previous night's answers and `api/data/hydro` (fields present), so most of the 2 700 possible requests are never made.

### D12. GUI chart

- **Where:** the station card „teraz” (`gui/web/src/sections/teraz.js`, `HydroNow`) gets a chart under the current values, built with the existing SVG module (`gui/web/src/charts/chart.js`, date axis, lines, steps, reference marks).
- **What it shows:**
  - H, with the warning and alarm levels from `pl.imgw.hydro_details` (ADR-021) as reference lines. Q and T are switchable.
  - Range buttons 3 d, 7 d, 30 d (the site's own `hoursInterval` 73 and 169, plus 30 d).
  - Each tier in its own style and legend: verified solid, telemetry thin, operational dashed, the live tail dotted. The caption reads „dane operacyjne, niezweryfikowane” as § 6 ust. 3 and the site do.
- **Data:** a new private route `GET /api/station/{code}/subdaily?from=…` that joins the stored sub-daily series with the D9 delta. Its ETag is the series version plus the delta time. The „Pomiary bieżące” map is unchanged.
- **Lines:** the provider's lines (RH/RD for IMGW-PIB, C/CP for ČHMÚ) in the card's strip (DEV-20.5), with the processing note.

### D13. Catalog: commands, REST, MCP

- **`series read|export`:** accept the sub-daily slugs. The CSV export has columns `time`, `H [cm]`, `H_flag`, `H_tier`, … and the export schema `obserwator-subdaily-export/1`.
- **`store sync`:** gains `--days` (operational) and `--pace`. Both come from the catalog, so the CLI, REST and MCP change together (ADR-002).
- **Unchanged:** `current hydro` stays the live snapshot.

### D14. Attribution

- Every product with sub-daily data carries the lines of its tiers: RH for hydro-back (`_HYDRO_LICENSE`), RD for the telemetry (`_LICENSE`), C/CP for ČHMÚ.
- It also carries a fixed tier notice in the result envelope's `notices`.
- Nothing presents operational or telemetry data as the verified archive (the amended DEV-20.8).

## Steps

| Step | Project | What | Depends on |
|---|---|---|---|
| N0 | Nogat | Amend DEV-20.8 and record an ECO decision: operational data may be stored as a labelled tier. List the consumers (Archiwista A1) | the author |
| O1 | Obserwator | ADR-024 (amends ADR-015 D5, ADR-003 D4, errata in both). Descriptors `pl.imgw.hydro_telemetry`, `pl.imgw.hydro_operational`, `cz.chmi.hydro_recent`, with `tier`, `time_unit` `10min`/`hour`/`day` | N0, approval |
| O2 | Obserwator | Fetchers: hydro-back series (`stations.py`, beside `_hydro_details`), the telemetry listing and zip (`fetch.py`), ČHMÚ `recent`/`now` (`fetch.py`, parser `_parsing/chmi.py`). Pacing and backoff in one place (`fetch.py`) | O1 |
| O3 | Obserwator | `store sync --days --pace`, derived files (D3), `flock` (D10) | O2 |
| O4 | Obserwator | Sub-daily series: builder, schema `obserwator-subdaily/1`, monthly slots, precedence (D4, D5), readers and exports (D13) | O3 |
| O5 | Obserwator | GUI: delta in memory (D9), route `/api/station/{code}/subdaily`, chart in „teraz” (D12) | O4 |
| O6 | Obserwator | `docs/USAGE.md` (the timer unit, pacing), `ARCHITECTURE.md`, CHANGELOG, `llms.txt`, `AGENTS.md` | O5 |
| A1 | Archiwista | Index and show `time_unit` `hour`/`10min` and the contract `obserwator-subdaily/1` (or skip them explicitly); probe with `obserwator.testing` | O4 |
| D1 | Operator | Install the timer on the host of the raw root (Q3). First run with `--days 40` to fill the six weeks | O3 |

## Acceptance

- After one night, the raw root holds `operational/<yesterday>.json` for IMGW-PIB and the ČHMÚ day file. The sub-daily slot of the current month is a new version, and the run's envelope reports the requests, failures and wall time inside the window.
- `series read --dataset pl.imgw.hydro_subdaily --station 151160060` returns the hours of October from operational data. After `Hydro_2026-10.zip` is synced, the same read returns 10-min rows with tier `telemetry`, and the full-hour values are equal (the Głogów check: 744 of 744). The one missing 10-min record stays an operational hourly point.
- A station opened in the GUI at 14:30 shows the stored series up to yesterday plus today's hours from the delta, each tier labelled. Opening it again within 10 min makes no request.
- A second `store sync` started during the night run fails with `conflict` (exit 4) without writing.
- No request rate above one per 5 s to hydro-back in the night window. Proof: the run log.
- `obserwator-series/1` readers (Hydrolog's tests, the Archiwista adapter's contract tests) pass unchanged.
- The lines of D14 appear in the GUI strip, the exports and the envelopes.

## Risks

- **R1. Undocumented backend.** hydro-back may change paths or fields (it is the SPA's backend), or start refusing scripted clients. Mitigations: one module, a contract test against a recorded answer, the telemetry month as the fallback source.
- **R2. Terms.** Public serving and planning use need IMGW-PIB's view („Terms of use”, flags a–c). Until then the public GUI stays behind Cloudflare Access (PROGRESS).
- **R3. Store growth.** It is append-only with no pruning. Nightly versions of the current month's sub-daily slot add about 0.75 GB a month of superseded versions. Option: a pruning command for superseded sub-daily versions (a new ADR), or keep nightly versions out of the slot until the month closes (Q4).
- **R4. Operational corrections.** IMGW-PIB corrects operational values after the night, and ČHMÚ validates `recent`. A night reads a day once, so late corrections arrive only with the telemetry month (IMGW-PIB) or a re-fetch (ČHMÚ; Q5).
- **R5. Time.**
  - hydro-back and ČHMÚ `now`/`recent` are in UTC, which was checked. ČHMÚ's PDF says „SEČ a SELČ”; the files carry `Z`.
  - Telemetry times are local or UTC (unverified; the Głogów comparison matched hydro-back's `Z` hours exactly, so treat them as UTC).
- **R6. Temperature mix.** Some stations are hourly and others give one reading at 06:00 UTC, so the chart must not join daily points into a curve.

## Open questions

- **Q1.** Amend DEV-20.8 (N0) as in D2: are operational measurements kept as a labelled unverified tier, while warnings and water-state classes stay live only?
- **Q2.** On-demand data: memory only (D9, proposed), or also written to the store? Writing makes the GUI a writer, which needs the lock and widens its rights.
- **Q3.** Who runs the nightly job in Nogat: Obserwator's timer on the raw root's host (proposed), or Archiwista's job runner? The Nogat plan of 2026-11-12 gives downloads to Archiwista.
- **Q4.** Store growth: allow pruning of superseded sub-daily versions (new ADR), or accept the growth (R3)?
- **Q5.** ČHMÚ `recent`: fetch once (D+1), or fetch again at the month's end to pick up ČHMÚ's validation?
- **Q6.** Ask IMGW-PIB (cash@imgw.pl, biznes@imgw.pl) about the nightly harvest and public serving before the first run (flag c)?
- **Q7.** The meteo side (`Arch/Telemetria/Meteo`, ČHMÚ climate `now`/`recent`): in a later plan, or now?

## Not in this plan

- Meteorological telemetry (Q7), forecasts (`hdModelStateForecast`, `H_F`/`Q_F`), warnings and water-state classes (still live only).
- Analyses on sub-daily data.
- The Slovak and German providers.
