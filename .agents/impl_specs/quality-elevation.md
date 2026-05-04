---
lifecycle:
  requirements:
    completed_at: "2026-05-03T19:00:00Z"
    git_rev: "8358798"
  design:
    completed_at: "2026-05-04T12:00:00Z"
    git_rev: "8358798"
  implement:
    completed_at: "2026-05-04T12:30:00Z"
    git_rev: "6ee0089"
---

# quality-elevation

## Context

Quality audit (Grade A, 95/100) identified improvement opportunities. Investigation revealed: .pyi stub has minor gaps (2 signature mismatches + 2 missing private methods), 15 uncovered lines (4 artefacts, 7 testable), only 2 of 9 subcommands have E2E tests, and the slow test marker lacks a defined threshold.

## Decisions

### pyi-policy

#### Context

The .pyi stub covers all public API but diverges from the implementation in two places and is missing two private methods. The project uses .pyi stubs as its type documentation strategy — ruff ANN is dropped because it ignores .pyi files entirely.

#### Decision

Maintain .pyi as the complete type surface including private methods. Fix all divergences.

#### Alternatives

a. Public-only .pyi — rejected: stub and implementation must not diverge
b. Drop .pyi, use inline annotations — rejected: project policy is .pyi-based

#### Consequences

.pyi maintenance burden increases slightly. Any method signature change must update both .py and .pyi.

### test-tier-model

#### Context

Single-file project with one external dependency (uv). Either uv is mocked (unit) or real (e2e). No natural seam for an integration tier.

#### Decision

Two-tier test model: Unit (mocked uv via MockUvBin) and E2E (real uv, real subprocess). The 70/20/10 pyramid model does not apply.

#### Alternatives

a. Force integration tier with partial mocking — no natural seam exists
b. Rename tests/integration/ to tests/e2e/ — cosmetic, out of scope

#### Consequences

Test expansion is E2E-only. No integration tests will be added.

### slow-marker-policy

#### Context

Slow marker was applied ad-hoc to two tests that install real packages. No defined threshold for "slow".

#### Decision

2-second threshold: any test consistently exceeding 2s gets `@pytest.mark.slow`. Enforcement is manual — measure new tests, apply marker if needed. Default pytest keeps `-m "not slow"`. Tox cov env runs everything.

#### Alternatives

a. CI duration check script — infra overhead for minimal gain
b. pytest-timeout per test — kills tests instead of marking them

#### Consequences

Slow marker is objective and measurable. New E2E tests are measured against this threshold.

### coverage-scope

#### Context

7 testable paths identified in 15 uncovered lines. 4 are coverage artefacts (accept). The stale-venv block (lines 1146-1161) has 3 untested behaviors. Extras sync (lines 1105-1108) is a real feature path.

#### Decision

Address 4 paths: stale-venv broken python (except branch), stale-venv version mismatch, stale-venv max version constraint, and extras sync args. Accept the remaining 3 (help text truncation, empty venv binaries, no-pyproject message) as marginal.

#### Alternatives

a. All 7 paths — marginal tests add noise
b. Stale-venv only — extras is a real feature worth testing

#### Consequences

4 new unit tests in existing test files. Potential 97.70% → ~99% coverage (exact impact depends on branch coverage).

### prepare-e2e-design

#### Context

Only init and migrate have E2E tests. Prepare is the most complex subcommand (venv creation, uv sync, symlink management) and has no E2E coverage.

#### Decision

Add 3 E2E tests for prepare: (1) happy path with minimal dependency, (2) no pyproject.toml → exit code 67, (3) no uv.lock → exit code 67. Follow existing pexpect pattern from tests/integration/test_cli.py. Target < 2s per test to avoid slow marker.

#### Alternatives

a. Happy path only — misses error regression detection
b. Full matrix (happy + stale venv + corrupted venv) — too much for PoC

#### Consequences

3 new test functions in tests/integration/test_cli.py (or new test_prepare_cli.py). Tests require uv installed. If happy path exceeds 2s, apply slow marker.

### test-strategy

#### Context

Work spans .pyi fixes (trivial, no tests), coverage gaps (tests for existing code), and E2E (new tests).

#### Decision

Tests-after for coverage gaps (code exists, write tests). E2E-first for prepare (test first, no code change needed — the feature exists). No tests for .pyi fixes (syntax-only).

#### Consequences

Implementation order: .pyi fixes first (trivial), then coverage gap tests, then E2E tests.

## Requirements

### .pyi Fixes (src/appenv.pyi)

1. Line 179: `_ensure_appenv_script` — add `*, update: bool = False` keyword-only parameter
2. Line 186: `_set_up_command_symlink` — change `command_name: str | None` to `command_name: str`
3. Add `_chdir_to_project(self, target: Path) -> None` after `_ensure_appenv_script`
4. Add `@staticmethod` + `_extract_version(script: Path) -> str | None` after `_chdir_to_project`

### Coverage Gap Tests (tests/test_prepare.py)

5. Test: stale-venv broken python — mock `cmd()` to raise `ValueError` when checking venv python version. Assert venv is removed and recreated.
6. Test: stale-venv version mismatch — mock `cmd()` to return "Python 3.8.0", set `requires-python = ">=3.12"`. Assert venv is removed and recreated.
7. Test: stale-venv max version constraint — mock `cmd()` to return "Python 3.15.0", set `requires-python = ">=3.12,<3.14"`. Assert venv is removed and recreated with correct constraint message.
8. Test: extras sync args — configure `AppEnvSettings(extras=["dev-tools"])`, call `_uv_sync`. Assert sync args include `--extra dev-tools`.

### E2E Tests (tests/integration/)

9. Test `test_prepare_cli` — setup: minimal pyproject.toml with one dependency + uv.lock. Run `./appenv prepare`. Assert: exit code 0, `.appenv/venv/bin/python` exists, `.venv` is symlink to `.appenv/venv`.
10. Test `test_prepare_cli_no_pyproject` — setup: empty directory. Run `./appenv prepare`. Assert: exit code 67, stderr contains "No pyproject config file".
11. Test `test_prepare_cli_no_lockfile` — setup: pyproject.toml but no uv.lock. Run `./appenv prepare`. Assert: exit code 67, stderr contains "No uv.lock file".

### Acceptance Criteria

- All quality gates green: ruff 0, ty 0, pytest all passed
- Coverage ≥ 99% (up from 97.70%)
- .pyi passes `ruff check --select PYI` with no new violations
- New E2E tests follow existing pexpect patterns
- Tests measured against 2s slow threshold

## Appendix

```yaml
implementation_plan:
  id: quality-elevation
  description: "Fix .pyi stub completeness, add coverage gap tests for stale-venv block and extras sync, add 3 E2E tests for prepare subcommand"
  specs:
    - .agents/impl_specs/quality-elevation.md
  target_tests:
    - file: tests/test_prepare.py
      tests:
        - test_stale_venv_broken_python
        - test_stale_venv_version_mismatch
        - test_stale_venv_max_version_constraint
        - test_extras_sync_args
    - file: tests/integration/test_cli.py
      tests:
        - test_prepare_cli
        - test_prepare_cli_no_pyproject
        - test_prepare_cli_no_lockfile
  git_rev: "6ee0089"
  created_at: "2026-05-04T12:30:00Z"
```
