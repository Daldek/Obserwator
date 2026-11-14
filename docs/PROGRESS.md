# Obserwator - Progress Tracker

Current state of the project (Nogat standard 1.0, DOC-6.1). Release history, cross-project analysis, closed backlog items and working notes: [docs/HISTORY.md](HISTORY.md). Full list of changes: [CHANGELOG.md](CHANGELOG.md).

## Status

| Field | Value |
|------|---------|
| **Version** | 3.0.0 |
| **Date** | 2026-11-13 |
| **Working branch** | `develop` (formerly `slave`, ECO-008). On 2026-11-03 the finished `feature/archiwista-projects` stack `0e0bc3a` (tree as after the green gate `8cd6844c`) was merged into it (`--no-ff`, the author's decision, without a pull request): projects moved to Archiwista and `command_for_version` (ADR-008), data output (`feature/data-output`, ADR-007), Nogat standard 1.0 (`chore/nogat-2.1`), Archiwista compatibility fixes (`fix/archiwista-compat-2`), and earlier `feature/chmi-agents` (ADR-003, ADR-004) and `feature/versioned-store` (ADR-001, ADR-002); these branches were deleted locally and on GitHub. Remaining: `main` (releases, v2.1.1); `fix/archiwista-compat` — superseded by `fix/archiwista-compat-2` (`e77a6f9` and `c280088` cherry-picked over), but `e9d8886` (publication without hard links, rejected in favour of `cb6af4f`) and `2e78eb6` are not in any other branch, so its deletion awaits the author's decision; the local `backup/versioned-store-master-base` `7263212` (a copy of `feature/versioned-store` from before the rework, 8 commits not present elsewhere, not on GitHub) — also the author's decision. Next: merge `develop` → `main` and tag 3.0.0 with the author's approval |
| **Python** | >=3.12 |

| Component | State | Notes |
|-----------|------|-------|
| Versioned data store (ADR-001) | done (3.0.0) | local, rebuildable store index: planned (ADR-001 D2) |
| Single command catalog, CLI and REST (ADR-002) | done (3.0.0) | CLI and REST generated from the catalog |
| ČHMÚ provider (ADR-003) | done (3.0.0) | questions to ČHMÚ and Archiwista confirmations: open (below) |
| AI agent support, MCP server (ADR-004) | done (3.0.0) | agent surfaces in English (ADR-006): done, entry in [HISTORY.md](HISTORY.md) |
| Web GUI: `obserwator gui serve` (ADR-013; plan [`docs/plans/2026-11-12-obserwator-gui.md`](plans/2026-11-12-obserwator-gui.md), the GUI part of Nogat's plan `2026-11-12-station-data-and-analyses.md`, ECO-059) | implemented on `feature/gui`, not merged into `develop` | GUI plan S0–S9 implemented: every station of both providers on a map, the station panel with series, Hydrolog's stored analyses of the data root (a person's choices computed on request) and downloads (series, stored analyses as JSON and CSV), „Pomiary bieżące”, PMAXTP of a point, the hand-off to Hydrolog, Nogat's public-GUI rules (DEV-15.7 to DEV-15.12, kit 0.4.0), the Jinja pages removed, the documentation and the Polish guide `instrukcja/`; open gaps below („GUI: open gaps”). The deployment (`obserwator-public.service` on 127.0.0.1:8060 behind Cloudflare Access) waits for the author's merge; it serves the target data root once that root's `analyses build` publishes its analyses versions |
| State borders from PRG and RÚIAN, lines G and Z (ADR-018; Nogat plan `2026-11-13-terms-fix.md`) | done (`fix/terms-1.0`) | `scripts/build_borders.py`, `obserwator._borders`, catalog tolerance 50 m + location uncertainty; GK/ZK in the GUI strip |
| Nogat server logs (ADR-019, ECO-066) and kit 0.6.2 (ECO-068) | done (`fix/terms-1.0`) | `nogat_logging.py` in both servers, `<state_dir>/obserwator/logs`; regulamin 1.0 corrected |
| API key enforcement, per-key limits | planned | backlog in "Next" |
| Compliance with Nogat standard 1.0 (`chore/nogat-2.1`, merged into `develop`) | in progress | done and to do: below and in "Next" |
| Data output: plain mode, store, default root (ADR-007, DEV §19) | done (`develop`) | code, tests and documents finished; for consumers: [CHANGELOG "Migration guide: data output"](CHANGELOG.md) |
| Store reading: Archiwista's requests of 2026-10-25 (ADR-007 erratum) | done (`develop`) | `StoreInfo.problem_codes`, `Meta.producer` and `Meta.producer_version`, `iter_store(skip_versions=)` with `StoreEntry.skipped` (incremental scan, Python only) and a marker without `created_by` readable by the reader; all optional in `/1`, details in [CHANGELOG "Unreleased"](CHANGELOG.md). Archiwista after the pin change: codes instead of text matching, `producer*` from `Meta` instead of the `PACKAGE` constant, `known_versions` as `skip_versions`; requests to Nogat remain (registry edge) |
| Write refusals: directory inside the store and a root with foreign files (ADR-007 erratum, Nogat decisions R1 and R2) | done (`develop`) | `output_dir` inside the store rejected before the first request with `details.paths` = the directory (store only below it: the target path); `--check` lists `not_empty` like `nested_store` as a single root `conflict` action, and reports `store_unavailable` and an unreadable marker (`data_error`) as an error; details in [CHANGELOG "Unreleased"](CHANGELOG.md) |
| MCP server: buffered `print` on stdout after the client disconnects (final integration run 2026-10-25, F1) | done (`develop`) | `run_stdio` flushes the stdout buffer before the SDK restores descriptor 1, so the text goes to stderr and not to the client (as in Hydrolog and Kartograf); a test in `tests/unit/test_mcp_stdio.py` runs `obserwator mcp` without `PYTHONUNBUFFERED`; details in [CHANGELOG "Unreleased"](CHANGELOG.md) |
| Command line as a call: `parse_command` and `format_command(..., run=)` (Archiwista's request, AGI-2.1, ADR-002 erratum) | done (`develop`) | `parse_command(line)` reads an `obserwator` line with CLI flags into `CommandCall(command, options, run)` (options are the strings the CLI passes to `run_command`; `run` = `{"check": True}` for `--check`); `format_command` writes `--check` via `run`; names, shapes and errors as in Kartograf; the contract test `tests/contract/test_command_lines.py` reads back the line of every example; details in [CHANGELOG "Unreleased"](CHANGELOG.md) |
| Example calls in the catalog (AGI-2.2, ADR-002 erratum) | done (`develop`) | every command has `x-obserwator.examples` (`{call, result}`): a canonical `obserwator` line and an excerpt of the result; the contract test `tests/contract/test_command_lines.py` checks that `format_command(*parse_command(call)) == call` and that `validate_command` accepts the options; details in [CHANGELOG "Unreleased"](CHANGELOG.md) |
| Projects moved to Archiwista (ADR-008; Nogat plan [`2026-10-31-archiwista-projects.md`](https://github.com/Daldek/Nogat/blob/main/docs/plans/2026-10-31-archiwista-projects.md), step 3, items 1–2) | done (`develop`) | removed without aliases: the `project` group (8 commands; the catalog had 30 then), the project functions, types and exception, the manifest contract, `OperationResult.task` and the `restored_by_content` status; the store, the read API, `content_sha256`/`content_form` in sidecars and the observation registry remain; details in [CHANGELOG "Unreleased"](CHANGELOG.md) |
| Command of a saved version `command_for_version` (ADR-008 D5; Nogat plan 2026-10-31, step 3, item 3) | done (`develop`) | from the sidecar and the store layout, offline: IMGW-PIB and ČHMÚ archives → `store sync`, station lists and catalogs → `store catalog`, series → `series build`, PMAXTP → `pmaxtp sync`; refusal `unsupported`/`command_not_rebuildable` (new Nogat registry code, exit 15, HTTP 422), `not_found`, `data_error`; test `tests/unit/test_command_for_version.py`; Archiwista (pin `8cd6844c`) uses it to check and restore the IMGW pins; Retman also pins `8cd6844c` (both pins are in `develop`) |
| The tool is called Obserwator (ADR-009, Nogat ECO-057; Nogat plan [`2026-11-03-imgwtools-to-obserwator.md`](https://github.com/Daldek/Nogat/blob/main/docs/plans/2026-11-03-imgwtools-to-obserwator.md), step 2) | done (`feature/obserwator`) | distribution, import package and command `obserwator`, `OBSERWATOR_<KEY>`, `[obserwator]`, `<data_dir>/obserwator`, `obserwator-<kind>/1`, `obserwator-store.json`, MCP tools `obserwator_*`, `x-obserwator*`, `ObserwatorError`; no alias (ECO-056); the name map and migration lines: [CHANGELOG "The tool is called Obserwator"](CHANGELOG.md); the GitHub repository keeps its name until the author renames it (plan step 5) |
| CI with an ubuntu/macos/windows matrix | done (`develop`) | `ci.yml` from the Nogat template: the gate on ubuntu, macOS and Windows with Python 3.12 (required) and 3.15 (reported), and `pip-audit`; first green run 2026-11-03 (`feature/ci`, run 41714582095) after Windows fixes (UTF-8 and LF output, a pipe closed by its reader, the agent guide, hard links, the reference CSV) and test fixes for CI terminals and paths |
| Provider attribution in every product (ADR-012, Nogat DEV §20, ECO-060; the author's order of 2026-11-13) | done, merged into `develop` 2026-11-13 | `obserwator.attribution` composes the lines of `messages/legal.py` (IMGW-PIB S, P, H; PMAXTP PS, PP, M; ČHMÚ C with the licence link, CP; the terms notice N with RD, RH, RK); the envelope fields `attribution`/`terms_notice` and REST stream headers, the CLI summary, CSV/JSONL/Parquet exports, `series.json`, `stations.geojson`, PMAXTP `cell.json`, sidecar texts, `ATTRIBUTION.txt` of plain writes and of the reference data, the web pages of the time (now the GUI's views and files, ADR-013); a series version without the lines is rebuilt; details in [CHANGELOG "Unreleased"](CHANGELOG.md). Outside this repository: consumers carry the envelope lines on (Hydrolog, Archiwista, Retman, Hydrograf/Hydraulik for PMAXTP through `fetch_pmaxtp`, which as a Python function returns no lines — they take them from `obserwator.attribution`) |
| Raw data only in `store sync`, station sources archived, catalogs offline (ADR-015; Nogat plan 2026-11-12 step R1, ECO-059) | done (`feature/data-root`) | `store sync` writes archive versions only (`obserwator-sync-report/2`, no `series`); the station sources `pl.imgw.{hydro,meteo}_{stations,now}` and `cz.chmi.{hydro,meteo}_{stations,now}` are datasets that `store sync --datasets` stores; IMGW-PIB current-data answers are kept as station metadata only (code, name, river, coordinates; no operational data, the author's decision of 2026-11-13); `store catalog` builds and checks offline (`missing_source` when a source is absent); details in [CHANGELOG "Unreleased"](CHANGELOG.md). Open: Archiwista's actions and Retman follow (plan step R2); ČHMÚ rating curves and long-term characteristics (plan D10) are not yet datasets |
| Stored analyses computed by Hydrolog (ADR-016, Nogat ECO-059; Nogat plan `2026-11-12-station-data-and-analyses.md`, step O2) | done (`feature/data-root`, on S0 and R1) | registry of 87 analyses (59 hydro, 28 meteo; since O1 also `low_flow_sequences.H`, `seasonality.H.max`, `seasonality.H.min`), `analyses build\|list\|read\|export` (the catalog has 35 commands, REST 33 routes), `compute_analysis` for subsets on the fly (never stored), setting `hydrolog_command`; versions `analyses/versions/<pl.imgw\|cz.chmi>/` with Hydrolog's lines byte for byte and carry-forward by hard links; tests against a fake Hydrolog recorded from Hydrolog develop `14e8f06`. The gap until O1 is closed: the analyses live in the data root, and `store scan --kind analyses`, `iter_store`, `current_version` (`analyses:<pl.imgw\|cz.chmi>.analyses`) and `command_for_version` (`analyses build`) know them |
| The data root (ADR-017, Nogat ECO-059; Nogat plan `2026-11-12-station-data-and-analyses.md` D2, D3, step O1) | done (`feature/data-root`, on R1 and O2) | two roots: the raw root (`obserwator-store.json`: archives, station sources, PMAXTP cells) and the data root (new marker `obserwator-data.json`, `obserwator-data/1`: series, catalogs, analyses); `OBSERWATOR_ROOT` is the data root and `OBSERWATOR_RAW_ROOT` the raw root (defaults `<data_dir>/obserwator` and `<data_dir>/obserwator-raw`, REST needs both); `build_series`, `check_series`, `build_catalog`, `check_catalog` take `raw_root` (`--raw-root`) and only read it; a root of the other kind is `store_unavailable` (`wrong_root`); `store init --kind raw\|data`; `stations find --source store` reads the catalogs; `command_for_version(..., raw_root=)` of every kind; `build_fixture_store(root, *, data_root)` → `FixtureRoots`; an existing store is split once by a documented hard-link copy (USAGE "Splitting a store", `tests/unit/test_store_split.py`); details in [CHANGELOG "Unreleased"](CHANGELOG.md). Open: Archiwista configures both roots, downloads into the raw root and reads the data root, and Retman's command list follows (plan step R2); ČHMÚ rating curves and long-term characteristics (plan D10) are not yet datasets |

### Compliance with Nogat standard 1.0 (`chore/nogat-2.1`)

**Done:** pyright → mypy `strict` (ECO-010; tests without annotations are a DEV-7.3 deviation in `CLAUDE.md`), `scripts/gate.sh` + `check-commits.sh`, `uv.lock`, the `live` marker instead of `IMGW_LIVE=1`, coverage ≥ 80% (DEV-7.5), CI/Dependabot from the Nogat templates (they work after the branch rename), `forbidden` with exit code 12 (ERR §4), erratum to ADR-001 D1 (hard links), MCP prefix `obserwator_` = the catalog `operation_id` = the OpenAPI `operationId`, the full set of MCP annotations with `idempotentHint`, the `commands list` command (ECO-018, AGI-5.2, AGI-5.4, AGI-5.9, AGI-6.2; ADR-004 erratum of 2026-10-24); user environment DEV-18: `nogat.toml` via `tomllib`, `NOGAT_*`, `cache_dir`, `IMGW_DATA_DIR` → `OBSERWATOR_REFERENCE_DIR` (breaking change), `obserwator config show --json`, 18 variables in README and `.env.example` (ADR-005).

**Done (document budgets, DOC-1.7):** `CLAUDE.md` 96 lines (budget 200), `README.md` 221 (400), `docs/PROGRESS.md` 191 (300; history in [HISTORY.md](HISTORY.md)) — as of 2026-10-31, `AGENTS.md` 174 lines and 16.0 KiB in both languages (200 lines and 16 KiB), `llms.txt` 2,810 characters before the first list of links (8,000); the `AGENTS.md` and `llms.txt` budgets are guarded by `tests/unit/test_agent_guide.py`, the rest are limits for review. Content moved out of `CLAUDE.md` and `README.md` lives in `docs/CODEBASE.md`, `docs/TESTING.md` and `docs/USAGE.md`. The "unusable `nogat.toml`" error has `details.reason = "invalid_config"` (the cause text in the message), and a file not in UTF-8 ends with `validation_error` (test `test_environment.py`).

## Next

Dependency order; unfinished work first. The backlog is the single source of truth for things to do — add new tasks only here (consolidation 2026-08-02: the former "Planned"/"Implemented" sections and section 11 of `PRD.md`).

1. **Documentation in English (ECO-005, phase 3) — translated 2026-11-03;** `docs/DEVELOPMENT_STANDARDS.md` removed in favour of the Nogat standard (DEV-1.3), the CHANGELOG folded into one `[Unreleased]` against v2.1.1. Open: facts that the budget moves left in two places — the project tree (README ↔ `CODEBASE.md` "Package Tree"), test instructions (README ↔ `TESTING.md`), "Source data structure" (`USAGE.md`) ↔ "Data Structure" (`CODEBASE.md`), the store layout (`CODEBASE.md` ↔ `ARCHITECTURE.md` §8) — still to be merged; the README summary (400 characters, DOC-1.7) and the DOC-2.1 section order have not been checked. `docs/superpowers/` (specs and plans of 3.0.0) stays Polish.
2. **Consumers after the pin changes (ADR-005 D2, ADR-006, ADR-007, ADR-008):** Retman switched to `IMGW_REFERENCE_DIR` and the data output mode names and pins `8cd6844c` with a green gate; Archiwista has an IMGW adapter and pins `8cd6844c`. List of changes for further consumers: [CHANGELOG "Migration guide: data output"](CHANGELOG.md).
3. **Consumers after the rename (ADR-009; Nogat plan 2026-11-03, steps 3–4):** Archiwista, Retman, Hydraulik and Hydrolog pin the rename commit and rename imports, commands, variables, ids and identifiers; Kartograf (frozen) names `obserwator-store.json` in `STORE_MARKERS`; Hydrograf keeps its pin and imports of `imgwtools` until after its v0.5.0. Then the author renames the GitHub repository (step 5) and the URLs follow.
4. **Data output — open:** review by the author. The smoke test with the real network passed on 2026-11-03 (release audit, code of `0045bac`): IMGW-PIB and ČHMÚ `datasets download` with `output_dir` through Python, CLI, REST and MCP; `obserwator store sync … -o` and `obserwator pmaxtp sync … -o`; an existing file refused with `conflict` (exit 4, `output_exists`) and replaced with `--force`. No live test covers plain mode yet.
5. **Consumers of the two roots (ADR-017; Nogat plan 2026-11-12 step R2):** Archiwista configures its stores with both roots, orders downloads into the raw root and reads series and catalogs from the data root; Retman's command list gives each command the root of its kind and `series build`/`store catalog` their `--raw-root`; a store written before ADR-017 is split once ([USAGE "Splitting a store"](USAGE.md#splitting-a-store)), and the deployment's roots start afresh with one full download (plan answer 2). List of changes: [CHANGELOG "Unreleased"](CHANGELOG.md), the entry "the data root".

Further open backlog items (priority in the text):

### Features

- [ ] API key enforcement — middleware validating the `X-API-Key` header. `docs/CODEBASE.md` (section "Cloud & Deployment Details") notes that keys are managed by the CLI (`obserwator admin`) but not enforced on API requests — this is a missing security layer, not a new feature. Priority: high.
- [ ] Per-key rate limiting — tracking and limiting requests per API key. Depends on API key enforcement. Priority: medium.
- [x] GeoJSON in REST/GUI — done 2026-11-13 (ADR-014, GUI plan S0): `export_stations` / `obserwator stations export` / `GET /api/v1/stations/export` export the current catalogs as GeoJSON (`obserwator-stations-export/1`) or CSV with the series of each station, and `series export` gained JSON and Parquet; the GUI draws the same catalogs on its map and offers the stations as GeoJSON and CSV („Pobierz listę stacji”, ADR-013).
- [x] Data charts — done by the GUI (ADR-013): series and analysis charts in its own SVG module (`gui/web/src/charts/`).
- [ ] CSV export in REST/GUI for data without a store — since 3.0.0 `export_series`/`obserwator series export`/`GET /api/v1/series/export` export series from the store; there is no on-demand export without a store. Priority: low.
- [ ] Request logging — tracking API usage for analytics. Priority: low.
- [ ] Redis caching layer — cache for frequently fetched data. Priority: low.

- [ ] Better KS/SG/RB naming in `PMaXTPData` — property aliases and a `get_design_precipitation()` method; details in the section "TODO: Improve PMaXTPData readability" below. Priority: medium.
- [ ] Native PMAXTP grid in `fetch_pmaxtp` — since 3.0.0 the PMAXTP store (`sync_pmaxtp`/`read_pmaxtp`) keys cells by the `indX/indY` indices from the response and stores the cell centre in `cell.json`, but the `PMaXTPResult` from `fetch_pmaxtp` still has no `point` fields, and there are no cell conversion/iteration functions either; details in the section "TODO: Native PMAXTP grid" below. Reported from Hydrograf (2026-09-28). Priority: high.
- [x] ČHMÚ data in the GUI — done by the GUI (ADR-013): ČHMÚ stations on its map with their series, analyses and files beside IMGW-PIB's.

### GUI: open gaps

- M15 climate stripes: only the colour scale is a prototype (Hydrolog has no stripes yet); their centre, Hydrolog's normal of the scale's reference period, is computed on request (no stored analysis holds it), so a server without Hydrolog's program shows no stripes.
- IMGW-PIB's 6-hour precipitation class is unavailable: the meteorological points of „Pomiary bieżące” are classed by the 10-minute sum.
- ČHMÚ's published rating curve is not in the store.
- The source of the annual maxima (half-years or daily) cannot be chosen.
- H–Q pairs cannot be handed off (`hydrolog-series/1` holds one variable).
- Regime curves and Rybczyński's zones over a chosen period are not offered (Hydrolog's ids take no period).
- No circular chart in the shared chart module (`regime.js` draws its own).
- No XLSX and no „Kopiuj JSON” for PMAXTP (XLSX rejected, plan G6).
- A result computed on request cannot be downloaded from its section: plan D14 offers it as its JSON, and `api/files/analysis/{code}/{id}` takes the options, but only „Pobierz” links the stored results.
- On-request computations of the longest records come close to the 30 s limit (plan D8) on a busy server: at the acceptance of 2026-11-13 (4 CPUs, load about 12) a chain for Praha-Klementinum (1775–2025, `mann_kendall.temperature.summer_days`) took 28 s alone and passed 30 s beside other computations; the part then names Hydrolog's limit.

### AI agent support (after 3.0.0, ADR-004)

- [ ] Filter MCP tools by group or provider (`--groups`, `--provider`, `data_commands(provider=…)`), if the context cost of the tool list (about 53 KB for 35 tools since ADR-016) turns out to be a problem (ADR-004, question 4). Priority: low.
- [ ] A limit on network calls of the MCP server on stdio (today only the library's sequential requests) and writing through MCP over HTTP with authorisation (ADR-004, questions 5–6). Priority: low.

### Versioned store (after 3.0.0)

- [ ] Local, rebuildable store index (ADR-001 D2: outside the 3.0.0 release; never as the source of truth). Priority: low.
- [ ] A request to IMGW-PIB for an official list of station coordinates (ADR-001 Q6) and confirmation of the meaning of the hydrographic code and the `river_order` ordering (Q4, Q5) — until then no interpretation. Priority: medium.
- [ ] Extending the store with further datasets (monthly/hourly meteo, synop) — D6 limits 3.0.0 to Archiwista's five datasets and PMAXTP. Priority: low.
- [ ] Questions to ČHMÚ (chmi@chmi.cz; ADR-003, questions 5–10): the time zone of `historical` timestamps and the definition of the HD/QD day, the official hydrological year, whether regenerations preserve bytes and whether a corrections register exists, continuity of `historical_csv`, the meaning of `WGS_ELE`, `RICKM`, `HA`, `QA`, `CEVT`, `PRF_ID`, the full `FLAG` dictionary. Priority: medium.
- [ ] Archiwista confirmations (ADR-003, questions 11–15): `stations[<code>].periods` in coverage labels, distinguishing `relabeled`/`unchanged` by content in IMGW-16, missing content fields as `null`, `kind="observation"` entries read-only (`restored_by_content`/`content_match` from IMGW-19 were dropped together with projects, ADR-008). Priority: medium.
- [ ] The rest of `docs/OBSERWATOR_SPEC.md` (the rename itself is done in 3.0.0, ADR-009): the provider layer and the English API, now without the SQLite cache (replaced by the store); the ČHMÚ provider is described by ADR-003 (item above). Priority: low.

### TODO: Improve PMaXTPData readability (KS/SG/RB)

**Context:** The abbreviations KS, SG, RB in the PMAXTP API response can be confusing. It is easy to mistake the upper confidence bound (SG) for the actual quantile value (KS), which leads to wrong hydrological calculations.

| Symbol | Meaning | Use |
|--------|-----------|--------------|
| **KS** | Quantiles (point estimate) | Design value (default) |
| **SG** | Upper confidence bound | Conservative calculations |
| **RB** | Estimation errors | Uncertainty analysis |

#### Proposed changes

**1. Aliases for better readability:**
```python
@property
def quantiles(self) -> dict:
    """Alias for ks (precipitation quantiles)."""
    return self.ks

@property
def upper_bounds(self) -> dict:
    """Alias for sg (upper confidence bounds)."""
    return self.sg

@property
def errors(self) -> dict:
    """Alias for rb (estimation errors)."""
    return self.rb
```

**2. A method for the design value with a conservative option:**
```python
def get_design_precipitation(
    self,
    duration_minutes: int,
    probability_percent: int,
    conservative: bool = False
) -> float | None:
    """Get design precipitation value for engineering design.

    Args:
        duration_minutes: Duration in minutes
        probability_percent: Probability in percent
        conservative: If True, return upper confidence bound (SG)
                     If False, return quantile estimate (KS) - default

    Returns:
        Precipitation [mm] for engineering design
    """
    if conservative:
        return self.get_confidence_bound(duration_minutes, probability_percent)
    return self.get_precipitation(duration_minutes, probability_percent)
```

**3. Extend the README** with a table of the KS/SG/RB meanings.

**Note:** The existing `get_precipitation()` method already returns the correct value (KS), but direct access to the attributes `data.ks`, `data.sg`, `data.rb` can lead to mistakes.

---

### TODO: Native PMAXTP grid

**Context:** investigation from Hydrograf (2026-09-28, ~60 requests to `https://powietrze.imgw.pl/tpmax-api/point/P/KS/{lat}/{lon}`). The point endpoint assigns the request to the nearest cell centre of a regular grid and returns that cell's parameters, which Obserwator does not expose today. Without them the client does not know which cell it fetched — dense sampling queries the same cell many times, sparse sampling skips cells (Hydrograf's 2 km grid skipped ~80% of the cells).

#### Raw response

```json
{
  "point": {"lon": "21.0100", "lat": "52.2300", "name": "", "method": "POT",
            "dataLon": 21.007098333333, "dataLat": 52.234416666667,
            "indX": 751, "indY": 317, "recalcualted": true},
  "data": {"ks": {...}, "rb": {...}, "sg": {...}}
}
```

- `dataLon`/`dataLat` — cell centre (WGS84), `indX`/`indY` — cell indices.
- `recalcualted` (a typo on the IMGW side) — meaning unknown; the field is absent from responses outside the data coverage.
- Outside Poland: the indices and the centre are returned, but with `data: {}` and an additional `error` key.

#### Grid parameters (measured)

| Parameter | Value |
|---|---|
| System | regular grid in WGS84 degrees (EPSG:4326) |
| Step | Δlon = 0.01001°, Δlat = 0.01° (~680 m × 1110 m at 52°N, ~0.75 km²) |
| Cell centre | `lon = 13.489588333 + 0.01001 · indX`, `lat = 55.404416667 − 0.01 · indY` (indY grows southwards) |
| Point assignment | to the nearest cell centre (checked at cell boundaries) |

Verified on the points (52.23, 21.01) → (751, 317), (50.0, 19.0) → (550, 540), (54.0, 15.0) → (151, 140), (49.3, 14.2) → (71, 610, outside the data coverage). Steps and origin agree in all four.

#### Data range

The response contains **16 durations × 27 probabilities** for each of the `ks`/`sg`/`rb` arrays:
- durations [min]: 5, 10, 15, 30, 45, 60, 90, 120, 180, 360, 720, 1080, 1440, 2160, 2880, 4320,
- probabilities [%]: 0.01, 0.02, 0.03, 0.05, 0.1, 0.2, 0.3, 0.5, 1, 2, 3, 5, 10, 20, 30, 40, 50, 60, 70, 80, 90, 95, 98, 98.5, 99, 99.5, 99.9.

#### Proposed changes

1. `PMaXTPResult` — add the fields from the `point` block: `cell_lat`, `cell_lon`, `ind_x`, `ind_y` (and `has_data: bool` based on `error`/empty `data`); keep the raw response (e.g. `raw: dict`) for archiving on the client side.
2. Grid constants and conversion functions: `pmaxtp_cell_for(lat, lon) -> (ind_x, ind_y)`, `pmaxtp_cell_center(ind_x, ind_y) -> (lat, lon)`, `pmaxtp_cells_in_bbox(bbox) -> Iterator[(ind_x, ind_y)]` — fetching "one cell = one request for its centre".
3. A contract test on a saved response (fixture) — verifying the grid steps and origin and the 16 × 27 keys (today `PMaXTPData` knows the 27 probabilities from the 2026-09-28 measurement, without a response saved in a fixture).

## Open questions

Decisions waiting for the author (remove once resolved):

- IMGW-PIB's terms for serving its series and analysis results on the public instance (Nogat plan `2026-11-12-station-data-and-analyses.md`, question 4, „do sprawdzenia”); until answered the public GUI stays behind Cloudflare Access.
- Hydrolog's version for production builds of the analyses (ADR-016): Hydrolog's development builds all report `1.0.0.dev0`, so the carry-forward does not see a Hydrolog change within one development version; should a deployment build only with a released Hydrolog version (or recompute into a data root without analyses versions after each Hydrolog update)?

**For the author (outside the agent's reach):** branch/tag rulesets, Dependabot security updates, `SECURITY.md` and private vulnerability reporting (DEV-3.6, DEV-13.7); the CLA text. Done on 2026-11-03: the branches renamed `master`/`slave` → `main`/`develop` on GitHub (rename API; `main` is the default branch) and locally, with the links in the docs and `llms.*` (ECO-008); the history and author identities rewritten (phase 1).

### Decided

Author's decisions of 2026-11-09.

- **`/mcp` on the public server.** Off by default: `OBSERWATOR_MCP_ENABLED=false` stays in `Settings`, `.env.example` and `docker/docker-compose.yml`, and an operator enables `/mcp` explicitly (ADR-004, open question 2).

---

**Last updated:** 2026-11-13
