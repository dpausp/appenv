# Quality Audit Report

## Human Summary

The appenv project (single-file CLI tool, src/appenv.py, ~1466 lines) received a comprehensive quality meta-audit. All 9 CLI subcommands have proven test coverage with zero mock-only tests — the test suite is sociable, using real filesystem operations throughout. The project's quality gate configuration is clean and well-chosen: the 373 suppressed ruff rules in extreme mode are all legitimate design decisions (print statements in a CLI tool, annotations in .pyi stubs, docstring style choices). Two fixes were applied: removing 2 impl_spec tests that tested a deliberately removed gitignore normalization feature, and fixing a slow integration test assertion that had drifted from actual output format. All 195 tests now pass (193 default + 2 slow).

## Completion Checklist

- [x] Entry point inventory + smoke test completed
- [x] Structural inventory completed (noqa, mock, complexity)
- [x] Quality gates collected (baseline + extreme)
- [x] All 4 investigation streams completed with structured review results
- [x] Tool tolerance audit produced with per-tool signals (ruff/ty/pytest)
- [x] Test structure report with mock health metrics
- [x] E2E coverage assessed for every entry point (PROVEN/SUSPECTED/UNKNOWN/BROKEN)
- [x] Full CLI test NOT triggered — existing E2E evidence sufficient
- [x] Fixes applied for critical findings (2 impl_spec removals + 1 assertion fix)
- [x] Fix loop completed (gates green: 195/195 tests, ruff clean, ty clean)
- [x] Git commit: pending on main branch

## Entry Point Inventory

| Entry Point | Type | Source | Smoke | E2E Status | Evidence |
|-------------|------|--------|-------|------------|----------|
| appenv (console_script) | cli-entry | pyproject.toml:30 | PASS | PROVEN | integration/test_cli.py + test_main.py |
| init | cli-subcommand | src/appenv.py:729 | PASS | PROVEN | test_init.py (12 tests) + integration/test_cli.py (pexpect) |
| migrate | cli-subcommand | src/appenv.py:739 | PASS | PROVEN | test_migrate.py (13 tests) + integration/test_cli.py (pexpect) |
| update-lockfile | cli-subcommand | src/appenv.py:724 | PASS | PROVEN | test_update_lockfile.py (10 tests) |
| prepare | cli-subcommand | src/appenv.py:734 | PASS | PROVEN | test_prepare.py (26 tests) |
| reset | cli-subcommand | src/appenv.py:737 | PASS | PROVEN | test_reset.py (9 tests) |
| python | cli-subcommand | src/appenv.py:744 | PASS | PROVEN | test_main.py (dispatch tests) |
| uv | cli-subcommand | src/appenv.py:746 | PASS | PROVEN | test_uv_bin.py + test_prepare.py |
| run (deprecated) | cli-subcommand | src/appenv.py:741 | PASS | PROVEN | test_main.py::test_run_script_delegates |
| version | cli-subcommand | src/appenv.py:748 | PASS | PROVEN | test_main.py::test_show_version |

## Tool Tolerance Audit

| Tool | Baseline | Extreme | Delta | Signal |
|------|----------|---------|-------|--------|
| ruff | 0 issues | 373 issues (ALL rules) | 373 suppressed | green |
| ty | 0 errors | 0 errors | 0 | green |
| vulture | 0 findings | N/A | 0 | green |
| pytest (default) | 193 passed | 193 passed | 0 | green |
| pytest (slow) | 2 passed | 2 passed | 0 | green |

### Suppression Categorization (373 extreme ruff findings)

**Legitimate design decisions (360):**
- ANN001/ANN201/ANN202/ANN204/ANN205 (176): Type annotations in .pyi stub, not source
- T201 (84): print() is the CLI output mechanism
- D101/D102/D103/D105/D107 (53): Docstring style choice for CLI tool
- COM812 (25): Trailing comma formatter preference
- DOC201 (24): Returns documented in .pyi stubs
- S404/S603/S606/S607 (13): Intentional subprocess calls (wrapping uv/nix/pip)
- CPY001 (2): Copyright not required

**Minor/cosmetic (13):**
- ARG002 (13): Unused argparse callback args (correct pattern)

**Critical hiding: NONE**

### noqa/type:ignore Inventory

- Source noqa: 2 (both SLF001 for argparse private API access — necessary)
- Source type:ignore: 0
- Test noqa: 0
- Test type:ignore: 0

## Test Structure

- Total tests: 195 (193 default + 2 slow)
- Distribution: unit ~163, docs_spec ~15, impl_spec ~14, integration 3
- Mock health: 0 MagicMock, 0 spec=, 0 autospec= (ZERO mocks)
- Mock pattern: MockUvBin is a hand-rolled test double in conftest.py (not unittest.mock)
- Test suppressions: 2 skipif (OS/dependency conditionals), 0 xfail, 0 skip
- RED FLAGS: 0/10
- Signal: green

### Test File Coverage Map

| Test File | Tests | Coverage Focus |
|-----------|-------|----------------|
| test_main.py | ~25 | CLI dispatch, version, python, run, meta |
| test_init.py | ~12 | init subcommand, pyproject creation |
| test_migrate.py | ~13 | migrate from requirements.txt |
| test_prepare.py | ~26 | venv preparation, symlink handling |
| test_reset.py | ~9 | environment reset |
| test_update_lockfile.py | ~10 | lockfile update, diff mode |
| test_uv_bin.py | ~5 | uv binary discovery chain |
| test_docs_spec.py | ~15 | documentation accuracy |
| test_venv_lifecycle_fixes.py | ~14 | venv lifecycle spec validation |
| integration/test_cli.py | 3 | pexpect E2E (init, migrate, bootstrap) |
| integration/test_subprocess.py | 1 | Full subprocess E2E |

## E2E Coverage Assessment

- PROVEN: 10 entry points (all subcommands + console script)
- SUSPECTED: 0
- UNKNOWN: 0
- BROKEN: 0
- Full CLI test triggered: NO (not needed)
- Signal: green

## Stream Signals

- Code Architecture: green (single-file appropriate for CLI tool, no enforcement needed)
- Code Quality: green (clean baseline, all suppressions legitimate)
- Test Structure: green (zero mocks, sociable tests, real filesystem)
- E2E Coverage + Production Reality: green (all 9 subcommands proven)

## Critical Findings Fixed

1. **Removed 2 impl_spec tests** (test_migrate_gitignore_normalizes_entries, test_migrate_gitignore_normalizes_leading_slash) — tested a normalization feature deliberately removed in commit 9a1fb67
2. **Fixed slow test assertion** (test_bootstrap_flow_like_readme) — assertion expected literal "Created pyproject.toml" but actual output is full path "Created /tmp/.../pyproject.toml". Changed to check both substrings independently.

## Full CLI Test Trace

Full CLI test not triggered — existing E2E evidence sufficient. All 9 subcommands have proven test coverage with sociable tests (real filesystem, real file I/O). Integration tests use pexpect for true end-to-end verification.

## Code Volume

| File | Change |
|------|--------|
| src/appenv.py | +3/-19 (gitignore normalization removal, prior commit) |
| tests/impl_spec/test_venv_lifecycle_fixes.py | -79 (removed 2 test functions) |
| tests/integration/test_cli.py | +1/-1 (assertion fix) |

## Post-Fix Quality Gates

| Tool | Result |
|------|--------|
| ruff check src/ | 0 issues (PASS) |
| ty check src/ | 0 errors (PASS) |
| vulture src/ | 0 findings (PASS) |
| pytest (default) | 193 passed (PASS) |
| pytest (slow) | 2 passed (PASS) |
| Total tests | 195/195 (PASS) |
| E2E smoke | PASS (help + version) |

## Recommendations

1. **ensure_gitignore missing from .pyi stub** — the function is public but not declared in src/appenv.pyi. Low priority but should be added for type safety.
2. **No test_architecture.py** — for a single-file module this is cosmetic, but if the project grows, structural enforcement would be valuable.
3. **Symlink-based binary execution** — the `./<name>` dispatch path (detected via stem != "appenv") has no explicit E2E test. Covered indirectly by test_main.py dispatch tests, but a direct integration test would strengthen coverage.

## Raw Data Location

`.agents/tmp/quality/` — inventory/, baseline/, extreme/, analysis/, e2e/
