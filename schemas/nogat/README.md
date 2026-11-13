# Copies of the Nogat standard

Verbatim copies (ERR-3, AGI-4.1) of the files below, from the standard 1.0 of the
[Nogat](https://github.com/Daldek/Nogat) repository, branch `develop` at commit
`6d3bb4af445ee475daff33062b8c0fe6d2d7a8c7` (the tag `std-1.0` does not exist yet;
refresh the copies from `std-1.0` at the tag when it does):

- `error_registry.json` (Nogat `standards/error_registry.json`): error codes, exit
  codes, HTTP statuses and titles. `tests/contract/test_nogat_registry.py` checks
  that `ERROR_CODES` (`src/obserwator/exceptions.py`) agrees with it.
- `result-1.schema.json`, `error-1.schema.json`, `commands-1.schema.json` (Nogat
  `schemas/agent/`): the schemas of the result envelope, the error document and the
  command catalog. `tests/contract/nogat.py` validates Obserwator's documents
  against them.
- `handoff-1.schema.json` (Nogat `schemas/exchange/`): the hand-off envelope
  `nogat-handoff/1` the GUI builds; copied again from Nogat commit `b29eada`
  (ECO-065: its examples carry RK alone).

Do not edit these files; copy them again when the standard changes (DEV-15.6).
On 2026-11-12 all four were byte for byte equal to Nogat commit `7786271`.

The web pages hold another copy of Nogat files, in `src/obserwator/web/static/nogat/`:
`nogat-app-menu.js`, `nogat-app-menu.css` and `nogat-kit.json` of Nogat `design/kit/`
(kit 0.1.0) and `marks/` of `design/marks/`, from commit `7786271` (ADR-011).
Nogat's `scripts/ecosystem.py drift` reports every copy as current, behind or modified.
