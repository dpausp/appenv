---
lifecycle:
  requirements:
    completed_at: "2026-05-09T12:00:00Z"
    git_rev: "HEAD"
  design:
    completed_at: "2026-05-09T12:30:00Z"
    git_rev: "1525042"
  plan:
    completed_at: "2026-05-09T12:30:00Z"
    git_rev: "1525042"
  workflow:
    completed_at: "2026-05-09T13:00:00Z"
    git_rev: "1525042"
  verify:
---

# test-type-annotations

## Context

Test files have near-zero type annotation coverage. 9 of ~14 test modules have .pyi stubs, but 4 are outdated (missing functions, stale fixture references) and 5 files have no stubs at all. The project uses .pyi stubs as its type documentation strategy (see decision `pyi-policy` in `quality-elevation`). Ty runs only on `src/` — tests are not type-checked.

## Decisions

### stub-only-policy

#### Context

The project decided to use .pyi stubs instead of inline annotations because ruff ANN ignores .pyi files (see `quality-elevation` spec decision `pyi-policy`).

#### Decision

Continue the .pyi-only approach for test files. No inline type annotations in .py test files. All type information lives in matching .pyi stubs.

#### Alternatives

a. Inline annotations in .py — contradicts project policy and would be ignored by ruff ANN
b. Mix of .pyi and inline — inconsistent, defeats the purpose

#### Consequences

Each test module must have a matching .pyi file. Any function signature change requires updating both files.

### full-fixture-typing

#### Context

Existing .pyi stubs leave fixture parameters as bare names. This provides no type information to type checkers and defeats the purpose of stubs.

#### Decision

All fixture parameters in .pyi test function stubs must have full type annotations. Builtin fixtures use their canonical types: `monkeypatch: MonkeyPatch`, `capsys: CaptureFixture[str]`, `tmp_path: Path`, `request: FixtureRequest`, `caplog: LogCaptureFixture`. Project-defined fixtures use their return types from conftest.pyi.

#### Alternatives

a. Bare fixture params — current state, provides no type information
b. Partial typing — inconsistent, confuses type checkers

#### Consequences

Stubs become useful for type checking. pytest fixture types are well-documented and stable.

### complete-stub-coverage

#### Context

5 test files have no .pyi stubs at all. 4 existing stubs are outdated with missing functions and wrong fixture references.

#### Decision

Every .py test file in tests/ must have a matching .pyi stub. Stubs must be in sync: every test function, helper function, and class in the .py file has a corresponding entry in the .pyi. Markers (@pytest.mark.*) are preserved in stubs.

#### Alternatives

a. Only fix existing stubs — leaves 5 files uncovered
b. Generate stubs automatically — loses the manual curation and type quality

#### Consequences

15 test modules → 15 .pyi files. Maintenance burden increases proportionally. Stubs follow the pattern established in src/appenv.pyi.

### ty-test-scope

#### Context

Pre-commit runs `ty check src/` only. pytest-ty is installed but dormant. Tests are not type-checked anywhere.

#### Decision

Do NOT change ty scope or activate pytest-ty in this spec. That is a separate decision requiring CI impact analysis. The stubs are the deliverable — enabling ty on tests is a follow-up.

#### Alternatives

a. Activate pytest-ty — CI impact unknown, scope creep
b. Add tests/ to pre-commit ty check — same concern

#### Consequences

Stubs are created but not yet enforced by CI. Enforcement is a follow-up task.

### test-strategy

#### Context

Work is updating/creating .pyi stub files only. No .py file changes except potentially removing stale .pyi-only content.

#### Decision

No new functional tests. Validation is: (1) stubs match .py counterparts (function count, parameter count, marker presence), (2) `ruff check --select PYI` passes on all .pyi files, (3) `ty check tests/` passes after stubs are correct.

#### Consequences

Quality gates are ruff PYI and ty check. No test execution needed for stub-only changes.

## Requirements

### Files needing NEW .pyi stubs

1. `tests/test_self_update.py` → `tests/test_self_update.pyi`
2. `tests/test_docs_spec.py` → `tests/test_docs_spec.pyi`
3. `tests/impl_spec/test_docs_e2e_alignment.py` → `tests/impl_spec/test_docs_e2e_alignment.pyi`
4. `tests/integration/test_pip_install_uv.py` → `tests/integration/test_pip_install_uv.pyi`
5. `tests/integration/test_cli.py` → `tests/integration/test_cli.pyi`
6. `tests/integration/test_subprocess.py` → `tests/integration/test_subprocess.pyi`

### Files needing .pyi stub UPDATES

7. `tests/test_prepare.pyi` — sync with test_prepare.py (6 missing tests, wrong fixture names)
8. `tests/test_update_lockfile.pyi` — sync with test_update_lockfile.py (missing parametrized test, 3 phantom tests, wrong fixtures)
9. `tests/test_migrate.pyi` — sync with test_migrate.py (7 missing tests, 2 phantom tests)
10. `tests/test_init.pyi` — sync with test_init.py (2 missing tests)

### Files that are CURRENT (no changes needed)

11. `tests/conftest.pyi`
12. `tests/test_main.pyi`
13. `tests/test_ensure_best_python.pyi`
14. `tests/test_reset.pyi`
15. `tests/test_uv_bin.pyi`

### Annotation patterns

- Test functions: `def test_xxx(fixture1: Type1, fixture2: Type2, ...) -> None: ...`
- Helper functions: full parameter and return types
- Helper classes: attribute types, `__init__ -> None`, method signatures
- Markers preserved: `@pytest.mark.slow`, `@pytest.mark.no_mock_uv_version`, `@pytest.mark.parametrize(...)`
- Default values: use `...` (Ellipsis) — e.g., `verbose: bool = ...`
- Imports needed: `from pathlib import Path`, `from pytest import MonkeyPatch, CaptureFixture, FixtureRequest, LogCaptureFixture`, `import pytest`, `import logging`, plus project types from conftest.pyi (MockUvBin, AppEnvSettings, AppEnv, UvVersion)

### Builtin fixture types

- `monkeypatch` → `MonkeyPatch`
- `capsys` → `CaptureFixture[str]`
- `tmp_path` → `Path`
- `request` → `FixtureRequest`
- `caplog` → `LogCaptureFixture`

### Project fixture types (from conftest.pyi)

- `workdir` → `Path`
- `test_settings` → `Callable[..., AppEnvSettings]` (returns inner function)
- `mock_uv` → `MockUvBin`
- `mock_uv_version` → `None`
- `subprocess_run_fail` → `None`
- `app_env` → `Callable[..., AppEnv]` (returns inner function)
- `make_mock_uv` → `Callable[..., MockUvBin]` (returns inner function)
- `no_ensure_python` → `None`
- `mock_cmd_python` → `None`
- `create_venv` → `Callable[..., Path]` (returns inner function)
- `mock_uv_lock` → `None`
- `mock_logdir` → `Path`
- `clean_uv_project_env` → `None`
- `make_pyproject` → `Callable[..., None]` (returns inner function)
- `capture_appenv_logs` → `logging.Logger`
- `patterns` → type from pytest-patterns plugin

### Acceptance Criteria

- Every .py file in tests/ has a matching .pyi stub
- Stub function count matches .py function count (no missing, no phantom)
- All fixture parameters are typed in stubs
- `ruff check --select PYI tests/` passes with 0 issues
- `ty check tests/` passes with 0 errors

## Appendix

```yaml
implementation_plan:
  id: test-type-annotations
  description: "Create missing .pyi stubs for 6 test modules and update 4 outdated stubs with full fixture typing"
  specs:
    - .agents/impl_specs/test-type-annotations.md
  target_tests:
    - file: tests/impl_spec/test_test_type_annotations.py
      tests:
        - test_complete_stub_coverage
        - test_stub_sync_function_count
        - test_no_phantom_functions
        - test_fixture_parameter_typing
        - test_specific_new_stubs_exist
        - test_specific_updated_stubs_sync
  created_at: "2026-05-09T12:30:00Z"
```
