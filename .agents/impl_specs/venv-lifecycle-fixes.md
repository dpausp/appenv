---
lifecycle:
  requirements:
    completed_at: "2026-04-28T12:00:00Z"
    git_rev: "f221160"
  design:
    completed_at: "2026-04-28T12:30:00Z"
    git_rev: "0327fbc"
  implement:
    completed_at: "2026-04-28T13:00:00Z"
    git_rev: "41455bd"
---

## Context

appenv has five related issues in its venv lifecycle and project initialization: duplicate logging output on the `python` subcommand, stale venvs when `requires-python` changes, no diagnostic logging in version selection, unclear error messages when no Python matches, and missing `.gitignore` setup during `init`/`migrate`.

## Decisions

### logging-duplicate-handler-fix

#### Context

The `python` subcommand routes through `meta()` then `run()`. Both call `setup_logging()` which adds handlers to the module-level singleton logger (`log = logging.getLogger("appenv")`) without clearing existing ones. Every log line dispatches to two file handlers and two console handlers.

#### Decision

Add `log.handlers.clear()` at the top of `setup_logging()` (L1359) before adding new handlers. The last call wins.

#### Alternatives

a. Skip second `setup_logging` in `python()` — fragile coupling between meta and run
b. Module-level `_logging_configured` flag — same effect, more indirection
c. Child loggers per command — over-engineering

#### Consequences

`python` subcommand logs to `python.log` only. All other paths unaffected.

### stale-venv-recreate

#### Context

`_prepare_venv` (L1085) only checks if the venv directory exists and if `bin/python` was garbage-collected on NixOS. It never validates the venv's Python version against `requires-python`. Changing constraints leaves the old venv in place.

#### Decision

Add a version compatibility check in `_prepare_venv` after the Nix-GC check (L1104) and before the venv-existence check (L1106). Detect the venv's Python version by running `<venv_python> --version` and parsing the output — this pattern already exists at L1118. Extract the version string to major.minor format, then call the existing `version_satisfies_constraints(version, min_version, max_version)` function (L117) against the parsed `requires-python` range from `Pyproject.requires_python` (L180).

If incompatible: print a one-line message to stdout, `shutil.rmtree()` the venv, let the existing creation path handle rebuild.

#### Alternatives

a. Read `pyvenv.cfg` — no subprocess needed but introduces a new parse pattern not used elsewhere
b. Compare `venv_python.resolve()` vs `sys.executable` — fragile on NixOS with symlink layers
c. Merge with Nix-GC check — conflates two different failure modes

#### Consequences

First run after a constraint change is slower (venv rebuild). User sees one informative line. Existing venv creation path reused unchanged.

### ensure-best-python-logging

#### Context

`ensure_best_python` (L1235) has zero `log.debug()` calls. Version selection issues are undebuggable.

#### Decision

Add `log.debug()` calls at: parsed requires-python constraints, available Python versions in range, per-candidate skip/selection reason, final decision (re-exec or already correct).

#### Alternatives

a. Key-decision-points only — too sparse for edge cases
b. Only final decision — insufficient for "why was X not found"
c. No additional logging — status quo

#### Consequences

`APPENV_VERBOSE=1` shows full version-selection reasoning. No non-verbose output change.

### error-message-improvement

#### Context

When no matching Python is found (L1278-1284), the error prints constraint and available versions but is bare.

#### Decision

Restructure the error output to clearly state the requires-python constraint and the available versions. No tips, no suggestions — just structured facts.

#### Alternatives

a. Add install suggestions — annoying, prescriptive
b. Keep current message — works but could be clearer

#### Consequences

Slightly clearer error output. No behavioral change.

### gitignore-setup

#### Context

`init` (L815) and `migrate` (L888) create files that should not be committed but never touch `.gitignore`.

#### Decision

Add a module-level function `ensure_gitignore(base, entries)` — consistent with the existing `ensure_pyproject`, `ensure_lock_file`, `ensure_uv` pattern. Called from `init()` with entries `[.venv, .appenv, .batou-lock]` and from `migrate()` with `[.venv]` only.

Idempotent: read existing `.gitignore`, normalize entries by stripping leading `/` and trailing `/`, check which entries are missing, append only those. Create file if it doesn't exist. Silent if all entries already present.

#### Alternatives

a. Method on `AppEnv` — inconsistent with module-level `ensure_*` functions
b. Inline in both methods — DRY violation

#### Consequences

New projects get sensible `.gitignore` automatically. Existing projects get `.venv` added safely. No duplicate entries.

### test-strategy

#### Context

Mature test infrastructure exists: pytest, 5300+ lines of tests, `MockUvBin` fixture, monkeypatching patterns, existing tests for `ensure_best_python`, `_prepare_venv`, `init`, `migrate`.

#### Decision

TDD — write failing tests first that reproduce each bug, then implement fixes. Extend existing test files: `test_main.py` (logging handlers, ensure_best_python logging, error message), `test_prepare.py` (stale-venv detection), `test_init.py` (gitignore), `test_migrate.py` (gitignore). Use existing mock infrastructure.

#### Alternatives

a. Tests-after — lower confidence that bugs are actually reproduced
b. No new tests — changes are too subtle to skip testing

#### Consequences

Each fix is verified by a test that first demonstrates the bug. Higher confidence, slightly more time.

## Appendix

**Scope**: ONLY the six decisions above. No new CLI flags, no `.python-version` support, no `appenv update` subcommand, no algorithm changes to `find_available_pythons` or `ensure_best_python`.

**Affected files**: `src/appenv.py` (all changes), `tests/test_main.py`, `tests/test_prepare.py`, `tests/test_init.py`, `tests/test_migrate.py`.

**Affected code paths**: `setup_logging` (L1359), `_prepare_venv` (L1085), `ensure_best_python` (L1235), error output (L1278-1284), `init` (L815), `migrate` (L888).

**Interface contracts**:
- CLI invocation: unchanged
- New stdout output: one line when venv is recreated due to Python version change
- Verbose output: `ensure_best_python` version-selection trace
- Error output: improved structure, no tips
- `.gitignore`: created or appended during `init` and `migrate`

```yaml
implementation_plan:
  id: venv-lifecycle-fixes
  description: "Fix five related issues in appenv's venv lifecycle: duplicate logging handlers, stale venv recreation, missing version-selection logging, unclear error messages, and missing .gitignore setup"
  created_at: "2026-04-28T13:00:00Z"
  git_rev: "41455bd"
  specs:
    - ".agents/impl_specs/venv-lifecycle-fixes.md"
  target_tests:
    - file: "tests/impl_spec/test_venv_lifecycle_fixes.py"
      tests:
        - test_setup_logging_no_duplicate_handlers
        - test_setup_logging_non_verbose_no_duplicate
        - test_prepare_venv_recreates_on_version_mismatch
        - test_prepare_venv_checks_version_compatibility
        - test_ensure_best_python_logs_constraints
        - test_ensure_best_python_logs_candidates
        - test_ensure_best_python_logs_final_decision
        - test_ensure_best_python_error_clear_constraint
        - test_ensure_best_python_error_restructured_format
        - test_init_creates_gitignore
        - test_init_appends_missing_gitignore_entries
        - test_init_gitignore_no_duplicates
        - test_migrate_creates_gitignore
        - test_migrate_appends_missing_gitignore_entries
        - test_migrate_gitignore_normalizes_entries
        - test_migrate_gitignore_normalizes_leading_slash
```
