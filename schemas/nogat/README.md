# Copies of the Nogat standard

Verbatim copies (ERR-3, AGI-4.1) of the files below, from the standard 1.1 (tag
`std-1.1`) of the [Nogat](https://github.com/Daldek/Nogat) repository, copied at the
commits named below:

- `error_registry.json` (Nogat `standards/error_registry.json`), copied again from
  Nogat commit `975136e` (standard 1.1, which changes only its `standard_version`):
  error codes, exit codes, HTTP statuses and titles.
  `tests/contract/test_nogat_registry.py` checks that `ERROR_CODES`
  (`src/obserwator/exceptions.py`) agrees with it.
- `result-1.schema.json`, `error-1.schema.json`, `commands-1.schema.json` (Nogat
  `schemas/agent/`, copied from Nogat commit `6d3bb4a` and unchanged in Nogat since):
  the schemas of the result envelope, the error document and the
  command catalog. `tests/contract/nogat.py` validates Obserwator's documents
  against them.
- `handoff-1.schema.json` (Nogat `schemas/exchange/`): the hand-off envelope
  `nogat-handoff/1` the GUI builds; copied again from Nogat commit `c47c42e`
  (ECO-065: its examples carry RK alone; the example's result is Hydrolog 0.9.0's).
- `record-1.schema.json` (Nogat `schemas/log/`): a record of the servers' logs,
  `nogat-log/1` (DEV-12.4), copied from Nogat commit `f370afe`. The module that
  writes the records, Nogat `standards/reference/nogat_logging.py`, is copied byte
  for byte from the same commit to `src/obserwator/nogat_logging.py`, shared by
  `obserwator server` and `obserwator gui serve`; `tests/unit/test_api_main.py`
  and `tests/unit/gui/` validate the records both servers write against the schema.

Do not edit these files; copy them again when the standard changes (DEV-15.6).
On 2026-11-22 all six, `src/obserwator/nogat_logging.py` and the GUI's copies below were byte
for byte equal to Nogat's `develop` at commit `f9a9677` (`tokens.css` apart from its DEV-15.3
header).

The GUI holds another copy of Nogat files, in `src/obserwator/gui/web/nogat/`: the files
of Nogat's `design/kit/` listed in its `nogat-kit.json` and `marks/` of `design/marks/`
(ADR-011, ADR-013). The kit's files are those of kit 1.3.0 at Nogat `ff18ee8`
(`nogat-sources.js` with PIG-PIB's W, WP and WK, and the terms with the block `pig`,
copied from there on 2026-11-25; the others unchanged since kit 1.1.0). Its
`nogat-kit.json` is Nogat's at `ff18ee8` with the files the GUI does not use left out
(the base maps, the charts and the command form of kit 1.3.0), so `drift` names it
modified until the GUI copies them too.
Nogat's `scripts/ecosystem.py drift` reports every copy as current, behind or modified.
