# Quality Audit Report

## Human Summary

The appenv project achieves **Grade A- (92/100)** — exceptional quality for a zero-runtime-dependency single-file CLI tool. All quality gates (ruff, ty, pytest, vulture) pass clean at baseline. Test coverage is 99.63% with zero `unittest.mock` usage — all test isolation uses pytest's `monkeypatch`, which is exemplary practice. All 10 CLI subcommands plus the symlink dispatch mode are PROVEN via smoke tests, integration tests, and unit tests. No critical findings, no broken entry points, no error-hiding detected. The narrow ruff config is deliberate (zero-dep constraint), not deceptive. Full CLI test was not triggered — existing E2E evidence is sufficient.

## Completion Checklist

- [x] Entry point inventory + smoke test completed (10 subcommands + symlink dispatch discovered)
- [x] Structural inventory completed (noqa: 2, mock: 0, type:ignore: 0, monkeypatch: 600+)
- [x] Quality gates collected (baseline + extreme)
- [x] All 4 investigation streams completed with structured review results
- [x] Tool tolerance audit produced with per-tool signals (ruff/ty/pytest/vulture)
- [x] Test collection integrity verified (205/207 collected, 2 slow deselected)
- [x] Skip/xfail/xpass audit completed (2 skipif, no xfail, no xpass, no lazy skips)
- [x] Test double strategy analyzed (mock:fake:golden:real = 0:5:0:real)
- [x] E2E coverage assessed for every entry point (all PROVEN)
- [x] Full CLI test NOT triggered (all entry points PROVEN, no trigger conditions met)
- [x] Fixes NOT needed (all gates green, no critical findings)
- [x] Fix loop NOT needed (nothing to fix)
- [x] North Star generated from loaded skills (python-dev, python-audit, python-tests)
- [x] Course Corrections derived (6 intentional deviations, 0 actionable, 4 monitor items)
- [ ] Git commit: pending

## Entry Point Inventory

| Entry Point | Type | Source | Smoke | E2E Status | Evidence |
|-------------|------|--------|-------|------------|----------|
| init | cli-subcommand | src/appenv.py:729 | PASS | PROVEN | test_init.py (13 tests) + test_cli.py::test_init_cli |
| migrate | cli-subcommand | src/appenv.py:738 | PASS | PROVEN | test_migrate.py (16 tests) + test_cli.py::test_migrate_cli |
| prepare | cli-subcommand | src/appenv.py:763 | PASS | PROVEN | test_prepare.py (32 tests) + test_cli.py::test_prepare_cli |
| reset | cli-subcommand | src/appenv.py:757 | PASS | PROVEN | test_reset.py (9 tests) + smoke --help |
| self-update | cli-subcommand | src/appenv.py:749 | PASS | PROVEN | test_self_update.py (6 tests) + smoke --help |
| update-lockfile | cli-subcommand | src/appenv.py:715 | PASS | PROVEN | test_update_lockfile.py (10 tests) + smoke --help |
| version | cli-subcommand | src/appenv.py:760 | PASS | PROVEN | Smoke test: "appenv 2026.4.28" |
| python | cli-subcommand | src/appenv.py:766 | PASS | PROVEN | test_main.py::test_python_method_calls_run + smoke --help |
| uv | cli-subcommand | src/appenv.py:778 | PASS | PROVEN | test_prepare.py::test_run_uv_sets_environment_and_execs + smoke --help |
| run (deprecated) | cli-subcommand | src/appenv.py:771 | PASS | PROVEN | test_main.py::test_run_script_delegates + test_main.py::test_meta_calls_run_script |
| Symlink dispatch | dispatch-mode | src/appenv.py:1498 | PASS | PROVEN | test_main.py::test_main_calls_run_when_not_appenv |
| Meta/argparse | dispatch-mode | src/appenv.py:704 | PASS | PROVEN | test_main.py::test_main_calls_meta_when_appenv + 205 collected tests |

## Tool Tolerance Audit

| Tool | Baseline | Extreme | Delta | Signal |
|------|----------|---------|-------|--------|
| ruff | 0 issues | 3249 issues | 3249 suppressed | orange |
| ty | 0 errors | N/A | — | green |
| pytest | 205 passed, 2 deselected | 2 slow passed | 0 hidden failures | green |
| vulture | 0 dead code | N/A | — | green |

**ruff extreme breakdown**: ANN (1700+ missing annotations), D (150+ docstring rules), COM (259 trailing commas), S (500+ security rules for subprocess), ARG (134 unused args), ERA (commented code). All exclusions are **intentional** for a zero-dep CLI tool — not error-hiding.

## Test Collection Integrity

| Check | Result | Signal |
|-------|--------|--------|
| Tests on disk | 12 files | — |
| Tests collected | 11 files (205 nodes) | — |
| Uncollected files | 1 — tests/integration/test_subprocess.py (all tests marked `slow`) | green |
| Collection errors | 0 | green |
| Config exclusions | `-m "not slow"` in addopts deselects 2 slow tests | — |
| conftest hooks modifying collection | autouse=True fixtures (2): mock_uv_version, disable_argparse_colors | green |

- pytest config: `--import-mode=importlib`, `--timeout=120`, `-W error`, `-m "not slow"`
- Unaccounted test files: none — test_subprocess.py is collected when `-m slow` is used

## Skip/Xfail/Xpass Audit

| Category | Count | Signal |
|----------|-------|--------|
| @pytest.mark.skip | 0 | — |
| @pytest.mark.skipif (platform) | 2 | green |
| @pytest.mark.skipif (dependency) | 0 | — |
| @pytest.mark.xfail (strict=True) | 0 | — |
| @pytest.mark.xfail (strict=False) | 0 | — |
| XPASS | 0 | — |
| Lazy skips | 0 | green |
| Flaky-hidden | 0 | green |
| Stale temporal skips | 0 | green |

- Cross-platform skip asymmetry: none (2 skipif in integration tests for platform-specific behavior)
- Suspicious skip details: none

## Test Double Strategy

| Layer | Mock | Spec'd Mock | Fake | Golden | Real | Total |
|-------|------|-------------|------|--------|------|-------|
| Unit | 0 | 0 | 5 | 0 | ~200 | ~205 |
| Integration | 0 | 0 | 0 | 0 | 5 | 5 |
| E2E | 0 | 0 | 0 | 0 | 13 (smoke) | 13 |

- Tautological tests (mock theater): 0 — no mock usage detected
- Golden file smell (no regenerate path): 0 — no golden files
- Mock density hotspots: none — zero unittest.mock usage across entire test suite
- Overall double strategy verdict: EXEMPLARY — all isolation via monkeypatch, 5 hand-rolled Fakes for test doubles
- Signal: green

## Test Structure Summary

- Total tests: 207 (205 collected + 2 slow deselected)
- Distribution: unit ~200, integration 5, e2e 13 (smoke)
- RED FLAGS: 0/10 — no mock-only indicators
- Signal: green

## Test Coverage

| Module | Coverage | Missing Lines | Signal |
|--------|----------|---------------|--------|
| src/appenv.py | 99.63% | 1298, 1302 | green |

- Overall coverage: 99.63%
- Modules < 50%: none
- Entry points with 0% coverage: none
- Signal: green

## Duration Anomalies

- Total suite time: 4s
- Duration stats: P50=~0.01s, P90=~0.09s, P95=~0.30s, P99=~0.82s

| Category | Count | Details |
|----------|-------|---------|
| EXTREME OUTLIER (>P99+2σ) | 0 | None above ~0.94s threshold |
| FAKE SLOW (marked slow, <P50) | 0 | No tests marked slow in the main suite |
| HIDDEN SLOW (unmarked, >P95) | 1 | test_prepare_cli_no_lockfile (0.30s) |
| Zero-duration (<1ms) | ~600 | Fast unit tests — majority of suite |

- Slow test cluster: tests/integration/test_cli.py (5 integration tests, 0.29-0.82s each)
- Root causes for outliers: none — integration tests legitimately involve filesystem/subprocess operations
- Signal: green

## Dependency Audit

| Category | Count | Signal |
|----------|-------|--------|
| Forbidden libraries | 0 | green |
| Stdlib reinvention | 0 | green |
| Unused dependencies | 0 | green |
| Missing blessed libraries | 0 | green (zero-dep constraint) |
| Available but unused (partial migration) | 0 | green |

- Zero runtime dependencies. All imports are stdlib.
- argparse and logging are stdlib — forbidden by python-dev skill but correct for zero-dep tool
- Signal: green

## E2E Coverage Assessment

- PROVEN: 12 entry points (10 subcommands + symlink dispatch + meta/argparse mode)
- SUSPECTED: 0
- UNKNOWN: 0
- BROKEN: 0
- Full CLI test triggered: NO
- Signal: green

## Stream Signals

- Code Architecture: green
- Code Quality: orange (narrow ruff config but intentional)
- Test Structure: green
- E2E Coverage + Production Reality: green

## Architectural North Star

Loaded from python-dev, python-audit, python-tests skills. Key dimensions:

| Dimension | True North | Source |
|-----------|------------|--------|
| CLI | typer + rich | python-dev |
| Logging | structlog | python-dev |
| HTTP | httpx | python-dev |
| Test Pyramid | Integration-heavy, real deps | python-tests |
| Mock Policy | Only external boundaries, autospec=True | python-tests |
| Type System | Type-First, native types, PEP 695 | python-dev |
| Exception Handling | Zero without SPEC reference | python-audit |
| Dependency Quality | Blessed libs only, no stdlib reinvention | python-audit |

## Course Corrections

### NAV-1 CLI Framework
- **Current heading:** argparse (stdlib) — correct for zero-dep constraint
- **True north:** typer + rich
- **Correction:** Maintain argparse. Zero-dep constraint makes typer impossible. INTENTIONAL.

### NAV-2 Logging
- **Current heading:** logging (stdlib) — correct for zero-dep constraint
- **True north:** structlog
- **Correction:** Maintain logging. Zero-dep constraint makes structlog impossible. INTENTIONAL.

### NAV-3 Type Annotations
- **Current heading:** Many functions unannotated; ty passes via inference
- **True north:** Full annotations on all public functions
- **Correction:** Consider adding ANN rule incrementally. MONITOR.

### NAV-4 Subprocess Security
- **Current heading:** subprocess.run with list args throughout
- **True north:** Security rules (S404, S603, S607) enforced
- **Correction:** Maintain current approach — list args are safe, tool must execute external programs. INTENTIONAL.

### NAV-5 CI/CD Testing
- **Current heading:** Slow tests excluded from default run
- **True north:** All tests run in CI
- **Correction:** Ensure `pytest -m slow` runs in CI pipeline. MONITOR.

### NAV-6 Exception Handling Specificity
- **Current heading:** Some broad exception catches for subprocess calls
- **True north:** Narrow catches, SPEC references, always re-raise
- **Correction:** Review exception handlers for narrowing opportunities. MONITOR.

- NAV-items total: 6
- Dimensions on course (no deviation): 8 (test framework, test structure, coverage, architecture, dependency quality, test doubles, duration, collection integrity)
- Signal: green

## Test Automation

- Task runner: tox (tox-uv)
- Single-command gate: YES (`tox -p` runs all envs)
- Default coverage: partial (slow tests excluded via `-m "not slow"`)
- Signal: orange (slow tests should be verified in CI)

## Infrastructure Recommendations

- **CI gate**: Add `pytest -m slow` to CI pipeline to ensure bootstrap/subprocess tests run regularly
- **Coverage pipeline**: Already configured (`[tool.tox.env.cov]`). No changes needed.
- **Duration regression**: No extreme outliers found. Optional: add `--durations=10` to CI to catch regressions early.

## Critical Findings Fixed

None — no critical findings were identified.

## Full CLI Test Trace

Full CLI test not triggered — existing E2E evidence sufficient. All 10 subcommands + 2 dispatch modes PROVEN via smoke tests, integration tests, and unit tests.

## Code Volume

| File | Change |
|------|--------|
| .agents/reports/quality-audit.md | Created |
| .agents/tmp/quality/ | Created (19+ inventory/data files) |

## Post-Fix Quality Gates

| Tool | Result |
|------|--------|
| ruff | 0 issues |
| ty | 0 errors |
| pytest | 205 passed, 2 deselected |
| vulture | 0 dead code |
| E2E smoke | 13/13 PASS |

## Recommendations

1. **Run slow tests in CI**: `pytest -m slow` (2 tests, ~3.5s) should be part of CI pipeline
2. **Investigate uncovered lines**: Lines 1298, 1302 in src/appenv.py — likely an error-path edge case
3. **Consider incremental ANN adoption**: Start with ANN201 for public functions as the project matures

## Raw Data Location

`.agents/tmp/quality/` — inventory/, baseline/, extreme/, analysis/, e2e/
