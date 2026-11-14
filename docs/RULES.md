# Obserwator — Working rules and standards

## 1. Code style and quality
- style: **PEP8**
- docstrings: **NumPy Style** (enforced by the `D` rules in ruff, `convention = "numpy"`)
- linting/formatting: **ruff** (`ruff check`, `ruff format` — the whole repository)
- typing: **typing** (mandatory)

---

## 2. Tests
- **unit and contract tests** — required, status: 3280 tests in `tests/unit` and `tests/contract` (2026-11-14), all offline
- **browser tests of the GUI** — 148 tests in `tests/e2e` (Playwright, Chromium; marker `e2e`, skipped without Chromium; 44 also marked `hydrolog`, skipped without Hydrolog's program)
- **live tests** — 72 tests in `tests/live` (marker `live`, outside the gate: `pytest -m live`): 50 against IMGW-PIB servers (35 commands × Python/CLI/REST, live errors, MCP leg `-k obserwator_mcp`) and 22 against opendata.chmi.cz (ČHMÚ provider)
- coverage: last measurement **94.37%** (2026-10-25), gate threshold **80%**
- a change of the command catalog, CLI, REST or MCP must keep the Python = CLI = REST = MCP contract (`tests/contract/test_interface_contract.py`, `test_mcp_contract.py`, `test_mcp_http_contract.py`)
- a change of catalog texts, registries (datasets, providers, error codes) or guide templates regenerates `AGENTS.md` and `llms.txt` in the same change (drift test in `tests/unit/test_agent_guide.py`)
- we do not merge a PR without tests

---

## 3. Git workflow
Branches:
- `main` — stable releases
- `develop` — main development branch
- `feature/*` — new features
- `hotfix/*` — critical fixes

Commit (`scripts/check-commits.sh`, in the gate):
- an English Conventional Commits subject (`feat`, `fix`, `docs`, `test`, `refactor`, `perf`, `style`, `build`, `ci`, `chore`; DEV-4.1) with a meaningful description
- no AI attribution lines (DEV-4.3)

---

## 4. Documentation
Every functional change must:
- update the Markdown documentation,
- update comments and docstrings,
- update OpenAPI (if applicable).

---

## 5. Claude Code integration
The project uses **Claude Code** (claude.ai/code) to support development.

Configuration:
- `CLAUDE.md` in the root directory — loaded automatically by Claude Code
- Contains instructions, commands, project structure

Claude Code helps with:
- generating and modifying code,
- updating documentation,
- keeping the project consistent.

---

## 6. Code Review
- at least 1 reviewer (if the team > 1)
- checking the tests
- checking the documentation

---

## 7. License
**Open Source** project, MIT license.
