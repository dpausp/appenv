---
lifecycle:
  requirements:
    completed_at: "2026-04-29T12:00:00Z"
    git_rev: "cd905c9"
  design:
    completed_at: "2026-04-29T14:00:00Z"
    git_rev: "cd905c9"
  implement:
    completed_at: "2026-04-29T16:30:00Z"
    git_rev: "866f3e8"
---

# output-patterns

## Context

CLI output tests use pytest-patterns but only 1 of 10 pattern tests does real line-by-line matching. The other 9 use loose keyword patterns like `...warning...skipped...` or only check for absence of errors. Real command outputs (collected in `tmp/appenv/logs/appenv-outputs.txt`) show which static strings the source produces. These need systematic pattern coverage.

Critical discovery: the `...` token in pytest-patterns is always a wildcard (matches anything). There is no way to assert literal `...` in output. Source strings containing `...` like `"Creating fresh venv with uv ..."` can only have their static prefix verified.

Additionally, the existing `test_init_fresh_start_interactive` defines patterns via `in_order` but never asserts them against the output — the pattern check is a no-op.

## Constraint

No source code changes. Only test files are modified.

## Decisions

### pattern-threshold

#### Context

Not every CLI output justifies the pattern overhead.

#### Decision

Outputs with 3+ static lines get pytest-patterns tests. Outputs with fewer lines get simple string checks (`assert "..." in captured.out`). This yields 6 pattern test targets:

| Command | File | Action |
|---------|------|--------|
| `--help` | test_main.py | New: group headers + commands in_order |
| `init` fresh start | test_init.py | Fix: add missing assertion, fix escaping |
| `migrate` full flow | test_migrate.py | New: complete flow pattern |
| `migrate` editable warnings (5 tests) | test_migrate.py | Replace: concrete patterns for loose ones |
| Binary not found | test_main.py | New: full output with mock venv |
| Verbose prepare | test_prepare.py | Upgrade: concrete patterns instead of no_errors only |

All other outputs (version, init-exists, prepare-no-project, prepare-no-lock, reset, update-lockfile, etc.) stay as string checks.

#### Alternatives

a. All outputs get patterns — overhead not justified for 1-2 line outputs
b. No patterns, all string checks — loses diagnostic quality on multi-line outputs

#### Consequences

Clear split: patterns for structured multi-line output, strings for simple single-line checks.

### dot-wildcard-semantics

#### Context

The pytest-patterns plugin converts `...` to `.*?` (non-greedy wildcard) via `re.escape` + targeted replace. There is no escape mechanism for literal dots. 8 source strings contain literal `...` (e.g. `"Creating fresh venv with uv ..."`, `"Updating lock file ..."`).

#### Decision

Accept wildcard behavior. Use `...` in patterns where the source has literal `...`. The static prefix before `...` is verified. The trailing dots themselves are not. This is acceptable because the `...` are visual indicators, not functional content.

#### Alternatives

a. Dual-pattern approach (wildcard for prefix + refused for wrong suffix) — over-engineering
b. Patch pytest-patterns to support literal matching — maintenance burden for external plugin

#### Consequences

Pattern `"Creating fresh venv with uv ..."` matches both `"Creating fresh venv with uv ..."` and hypothetically `"Creating fresh venv with uv DONE"`. The risk is negligible — nobody changes trailing dots to text.

### test-structure

#### Context

New and modified tests need a home. Existing loose pattern tests need replacement.

#### Decision

All changes go into existing test files (test_main.py, test_init.py, test_migrate.py, test_prepare.py). Test lives next to the code it tests. Existing loose patterns in the 5 editable tests are replaced in-place with concrete patterns. The existing init test gets its missing assertion added and `\.\.\.` escaping fixed to `...`.

#### Alternatives

a. New file `tests/test_output_patterns.py` — clean separation but far from tested code
b. `tests/integration/test_cli.py` — those are pexpect integration tests, wrong layer

#### Consequences

Changes are localized to 4 test files. No new files created.

### mocking-strategy

#### Context

Pattern tests need deterministic output. Several commands call uv subprocesses that must be mocked.

#### Decision

**Binary not found**: Mock venv with exactly 2 binaries (python, ruff) as the existing `test_run_missing_binary_shows_helpful_error` already does. This makes the binary list deterministic and fully patternable.

**Migrate full flow**: Mock `ensure_uv` (returns MockUvBin) and `_uv_lock` (returns empty string or summary). Let `_ensure_appenv_script`, `ensure_gitignore`, and `_prepare_appenv_dir` run real. Mock `input()` for interactive prompts via `monkeypatch.setattr("builtins.input", ...)`.

**Verbose prepare**: Same mock approach as existing `test_prepare_verbose_output` — mock uv, set `APPENV_VERBOSE=1`.

#### Alternatives

a. Mock everything — over-isolated, doesn't test real flow
b. Mock nothing — fails without real uv installation

#### Consequences

Each pattern test has a clear mock boundary. Binary list is deterministic. Migrate flow is realistic enough to test output structure.

### existing-test-treatment

#### Context

5 editable tests in test_migrate.py use `captured.out.lower()` and ultra-loose patterns. The init fresh start test has no assertion on its patterns.

#### Decision

**Editable tests (5x)**: Keep same structure (`main.in_order` + `no_errors.refused` + `full_pattern == captured.out.lower()`) but replace loose keyword patterns with concrete strings that include the actual warning text and paths. Example: `...warning...skipped...` becomes `...Warning: the following editable installs were skipped...` followed by the actual editable path.

**Init fresh start**: Add the missing `assert full_pattern == captured.out` block. Replace `r"\.\.\."` with `...` (correct wildcard usage).

#### Alternatives

a. Rewrite editable tests from scratch without `.lower()` — stricter but fragile
b. Merge 5 editable tests into 1 parametrized test — DRY but less readable on failure

#### Consequences

Editable tests keep their provenance. Init test becomes a real pattern assertion.

### help-pattern-approach

#### Context

The `--help` output has group headers, command names, blank lines, and indentation controlled by argparse.

#### Decision

Use `in_order` for group headers (`Project:`, `Venv:`, `Tools:`, `Debug:`) and command names within each group. Ignore blank lines and exact indentation — they're argparse implementation details that change across Python versions.

#### Alternatives

a. Full line-by-line pattern including blank lines — fragile against argparse changes
b. Don't pattern test --help at all — existing string checks are sufficient

#### Consequences

Pattern is robust against formatting changes but still verifies structure and command presence.

## Requirements

### Expected Static Strings (from source)

These strings appear in `src/appenv.py` at the listed lines. Pattern tests MUST verify their presence in the correct order.

**init() output** (lines 820-879):
- `already has a [project] section` (line 820)
- `Nothing to do - edit it manually to make changes` (line 821)
- `Adding [project] section to existing` (line 825)
- `Let's create a new appenv project in` (line 827)
- `I'll ask a few questions, then create pyproject.toml here` (line 828)
- `Binary to expose (creates ./<name> symlink) [app]` (line 831, input prompt)
- `Enter dependencies (one per line, empty line to finish):` (line 836)
- `Default:` (line 837)
- `Created` (line 866, prefix for pyproject path)
- `Generating new lock file ...` (line 873)
- `=== Appenv project initialized ===` (line 878)
- `Use \`./...\` to run the` (line 879)

**migrate() output** (lines 893-924):
- `pyproject.toml already has [project] section in` (line 893-894)
- `Nothing to do.` (line 896, note: with period, differs from init)
- `Migrating from requirements.txt to pyproject.toml...` (line 902)
- `No requirements.txt found in` (line 904)
- `Use 'init' to create a new project.` (line 905)
- `Preparing/cleaning .appenv directory ...` (line 919)
- `=== Pyproject Migration completed ===` (line 923)
- `requirements.{txt,lock} kept as legacy. You can delete these files now.` (line 924)

**_prepare_venv() output** (lines 1076-1160):
- `Creating fresh venv with uv ...` (line 1124)
- `Warning:` + `exists but is not a symlink.` + `Expected .venv ->` + `Remove` + `manually if you want appenv to manage it.` (lines 1147-1151)

**run() binary-not-found output** (lines 681-695):
- `Error: Binary '` + `' not found in` + `/bin/`
- `The symlink '` + `' determines which binary gets executed.`
- `Available binaries:`
- `Either:`
- `  - Install a package that provides the '` + `' binary`
- `  - Add a [project.scripts] entry:`
- `  - Or create a symlink with the name of an installed binary`

**ensure_pyproject() output** (lines 1205-1224):
- `Error:` + `has no [project] section.` (line 1213)
- `Error: No pyproject config file at` (line 1215)
- `appenv must be located next to pyproject.toml (not in a subdirectory)` (line 1216)
- `Run ./appenv init` (line 1223)

**ensure_lock_file() output** (lines 1227-1232):
- `No uv.lock found. Run: ./appenv update-lockfile` (line 1231)

**Verbose debug labels** (lines 1086-1069):
- `project base:` (line 1086)
- `activated extras/optional deps:` (line 1069)

### Test Strategy

The pattern tests ARE the deliverable. TDD approach: define pattern strings from source first, write tests, run against real output. No separate test infrastructure needed — pytest-patterns is already installed and configured.

## Appendix

```yaml
description: "Upgrade CLI output tests from loose keyword assertions to concrete pytest-patterns coverage for 6 multi-line output scenarios across 4 test files"
id: output-patterns
created_at: "2026-04-29T16:30:00Z"
git_rev: "866f3e8"
specs:
  - ".agents/impl_specs/output-patterns.md"
target_tests:
  - file: "tests/impl_spec/test_output_patterns.py"
    tests:
      - test_help_pattern_uses_patterns_fixture
      - test_help_pattern_has_group_headers_in_order
      - test_help_pattern_has_full_assertion
      - test_init_fresh_start_has_full_pattern_assertion
      - test_init_fresh_start_uses_wildcard_dots
      - test_migrate_full_flow_pattern_test_exists
      - test_migrate_full_flow_uses_concrete_patterns
      - test_editable_tests_use_concrete_warning_text
      - test_editable_tests_no_loose_keyword_patterns
      - test_binary_not_found_uses_patterns
      - test_binary_not_found_has_full_pattern
      - test_prepare_verbose_uses_main_in_order
      - test_prepare_verbose_has_concrete_source_strings
      - test_prepare_verbose_not_only_no_errors
```
