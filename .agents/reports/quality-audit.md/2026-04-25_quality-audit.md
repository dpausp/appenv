# Quality Audit Report — 2026-04-25

## Human Summary

The quality meta-audit of appenv found a well-maintained project with trustworthy quality gates. The tool tolerance audit revealed no error-hiding — the ruff config is well-curated with only 1 cosmetic E501 violation, 0 type ignores, and 2 justified noqa comments. The test suite is exceptional: 0 mocks, 4.8:1 test-to-source ratio, and genuine integration tests using pexpect and subprocess. Two real bugs were found and fixed: an E501 line-length violation blocking tox CI, and unknown CLI arguments silently exiting 0 instead of non-zero. The project scores B+ (87/100), with the only notable gap being 4/9 subcommands with unit-only coverage (reset, python, run, uv).

## Completion Checklist
- [x] Entry point inventory completed (all subcommands, scripts, APIs catalogued)
- [x] E2E smoke test completed (basic invocation tested)
- [x] All raw data collected in `.agents/tmp/quality/` (baseline/, extreme/, analysis/, e2e/)
- [x] All 4 investigation streams completed with structured review results
- [x] Tool tolerance audit produced with per-tool signals (ruff/ty/noqa)
- [x] Test structure report with mock health metrics
- [x] E2E coverage assessed for every entry point (PROVEN/SUSPECTED/UNKNOWN/BROKEN)
- [ ] Full CLI test executed (not triggered — conditions not met)
- [x] Fixes applied for critical findings (E501 + exit code bug)
- [x] Baseline re-run confirms no regressions
- [ ] Git commit: pending

## Entry Point Inventory

| Entry Point | Type | Source | E2E Status | Evidence |
|-------------|------|--------|------------|----------|
| update-lockfile | cli-subcommand | src/appenv.py:723 | PROVEN | test_update_lockfile.py (8 tests) + test_subprocess indirect |
| init | cli-subcommand | src/appenv.py:737 | PROVEN | test_init.py (9 tests) + test_cli.py::test_init_cli (pexpect) |
| migrate | cli-subcommand | src/appenv.py:746 | PROVEN | test_migrate.py (9 tests) + test_cli.py::test_migrate_cli (pexpect) |
| reset | cli-subcommand | src/appenv.py:757 | SUSPECTED | test_reset.py (8 tests, unit-only) |
| version | cli-subcommand | src/appenv.py:760 | PROVEN | test_main.py::test_show_version + smoke test |
| prepare | cli-subcommand | src/appenv.py:763 | PROVEN | test_prepare.py (19 tests) + test_subprocess indirect |
| python | cli-subcommand | src/appenv.py:766 | SUSPECTED | test_main.py::test_python_method_calls_run (unit-only) |
| run | cli-subcommand | src/appenv.py:771 | SUSPECTED | test_main.py (2 tests, unit-only; deprecated command) |
| uv | cli-subcommand | src/appenv.py:778 | SUSPECTED | test_prepare.py::test_run_uv_sets_environment_and_execs (unit-only) |
| run mode (symlink) | dispatch | src/appenv.py:1353 | PROVEN | test_subprocess.py::test_subprocess_main_flow |

## Tool Tolerance Audit

| Tool | Baseline | Extreme | Delta | Signal |
|------|----------|---------|-------|--------|
| ruff (configured) | **0 issues** (was 1, fixed) | — | 1 fix applied | green |
| ruff (--select ALL) | — | ~200+ findings | All from excluded categories: ANN (in .pyi), T201 (CLI prints), D (docstrings), COM812, S (subprocess FPs) | green |
| ty | 0 errors | — | — | green |
| noqa | 2 (SLF001) | — | Both justified (argparse internals) | green |
| type:ignore | 0 | — | — | green |

## Test Structure

- Total tests: 175 active / 2 slow deselected
- Distribution: unit 171, integration 4, e2e 0 (test_subprocess serves this role)
- Mock health: 0 MagicMock, 0 with spec=, 0 with autospec= (hand-written MockUvBin fake instead)
- RED FLAGS: 0/10 — no mock-only concerns
- Test-to-source ratio: 4.8:1 (6512 test lines / 1358 source lines)
- Test suppressions: 2 skipif (justified — Windows, uv availability), 0 xfail
- Signal: green

## E2E Coverage Assessment

- PROVEN: 5/9 subcommands (update-lockfile, init, migrate, prepare, version) + run mode
- SUSPECTED: 4/9 subcommands (reset, python, run, uv) — unit-only, no integration test
- UNKNOWN: 0
- BROKEN: 0
- Full CLI test triggered: NO (conditions not met)
- Signal: orange

## Stream Signals

- Code Architecture: green — single-file monolith by design, clean class separation
- Code Quality: green — 0 ruff errors (post-fix), 0 ty errors, minimal noqa
- Test Structure: green — 0 mocks, 4.8:1 test ratio, real integration tests
- E2E Coverage + Production Reality: orange — 5/9 PROVEN, 4/9 SUSPECTED, 2 exit-code bugs found

## Critical Findings Fixed

1. **E501 line too long** (src/appenv.py:834) — input prompt string exceeded 88-char limit. Fixed by splitting the input() call across lines. This also fixes the tox `fix` environment which was failing CI.

2. **Unknown arguments exit code 0** (src/appenv.py:789-791) — `appenv --nonexistent` silently showed help and exited 0. Fixed to print "Error: unrecognized arguments: ..." and exit with EXIT_CODE_USAGE (64).

## Code Volume

| File | Change |
|------|--------|
| src/appenv.py | +5/-2 lines (E501 split + exit code logic) |

## Post-Fix Quality Gates

| Tool | Result |
|------|--------|
| ruff check | 0 issues |
| ty check | 0 errors, 0 warnings |
| pytest | 175 passed, 2 deselected |
| architecture tests | N/A (no test_architecture.py — appropriate for single-file project) |
| E2E smoke | PASS (all 10 help commands, --nonexistent exits 64) |

## Recommendations

1. **Medium**: Add integration tests for 4 SUSPECTED subcommands (reset, python, run, uv) — especially `reset` which performs filesystem operations
2. **Low**: Run slow tests in CI with a separate job to validate real venv creation
3. **Low**: Consider adding a `test_architecture.py` if the project grows beyond single-file scope

## Raw Data Location
`.agents/tmp/quality/` — baseline/, extreme/, analysis/, e2e/
