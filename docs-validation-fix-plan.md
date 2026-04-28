# Documentation Validation Fix Plan

Prioritized fixes for all issues found in the documentation validation report.

---

## Executive Summary

| Priority | Count | Issues |
|----------|-------|--------|
| CRITICAL | 3 | Must fix immediately |
| STRUCTURAL | 3 | Fix before next release |
| MEDIUM | 3 | Address in next sprint |
| LOW | 3 | Backlog |
| **Total** | **12** | |

---

## Critical Fixes

Issues requiring immediate action.

### Issue #1: Python Version Mismatch

**File:** `docs/user-guide/installation.md`  
**Line:** 5

**Current:**
```markdown
- **Python**: 3.10 or later
```

**Fix:**
```markdown
- **Python**: 3.9 or later
```

**Rationale:** `pyproject.toml:12` specifies `requires-python = ">=3.9"`. Documentation must match implementation constraints.

---

### Issue #2: Phantom Commands in Help Formatter

**File:** `src/appenv.py`  
**Lines:** 51, 53

**Problem:** Help formatter references commands that don't exist.

**Current (lines 50-54):**
```python
groups = (
    ("Project", ["init", "migrate", "update-lockfile"]),
    ("Venv", ["develop", "prepare", "reset"]),
    ("Tools", ["python", "run", "uv"]),
    ("Debug", ["version", "settings", "profiling"]),
)
```

**Phantom commands:**
- Line 51: `develop` — doesn't exist
- Line 53: `settings`, `profiling` — don't exist

**Fix:** Remove non-existent commands from groups:

```python
groups = (
    ("Project", ["init", "migrate", "update-lockfile"]),
    ("Venv", ["prepare", "reset"]),
    ("Tools", ["python", "run", "uv"]),
    ("Debug", ["version"]),
)
```

**Rationale:** Commands showing in help but not executable confuse users. Either remove from help or implement the commands.

---

### Issue #3: Missing `.pyi` Reference Update

**File:** `docs/dev-guide/architecture.md`  
**Line:** 12

**Current:**
```markdown
- **Type stubs in `.pyi` files**: Implementation lives in `src/appenv.py` with minimal type hints. Full annotations go in `src/appenv.pyi`, following PEP 561.
```

**Fix:**
```markdown
- **Type stubs in `.pyi` files**: Implementation lives in `src/appenv.py` with minimal type hints. Full annotations go in `../../src/appenv.pyi`, following PEP 561.
```

**Rationale:** Path from `docs/dev-guide/architecture.md` to `src/` is `../../src/`, not `../src/`.

---

## Structural Fixes

Index files and navigation structure.

### Issue #4: Missing Dev Guide Index

**File:** `docs/dev-guide/index.md`  
**Status:** Does not exist

**Fix:** Create `docs/dev-guide/index.md`:

```markdown
# Developer Guide

```{toctree}
:maxdepth: 2
:caption: Developer Guide

architecture
contributing
```

**Note:** Architecture is at `architecture.md`, contributing at `contributing.md` (both in `dev-guide/`).

---

### Issue #5: Missing User Guide Index

**File:** `docs/user-guide/index.md`  
**Status:** Does not exist

**Fix:** Create `docs/user-guide/index.md`:

```markdown
# User Guide

```{toctree}
:maxdepth: 2
:caption: User Guide

installation
locking-behavior
commands
workflows
```

---

### Issue #6: Orphan Snippet

**File:** `docs/_snippets/quickstart.md`  
**Status:** Not in any toctree

**Current:** Included via `{include}` in `docs/index.md` (line 7)

**Fix:** Either:
- (A) Add to toctree in `index.md`:
  ```markdown
  ## Quickstart
  
  ```{include} _snippets/quickstart.md
  ```
  
  ```{toctree}
  :maxdepth: 1
  
  _snippets/quickstart
  ```
- (B) Document intentional exclusion in comment

**Recommendation:** Option A — add to toctree for full navigation.

---

## Medium Priority

Failure modes and edge cases.

### Issue #7: Cross-Reference Fix

**File:** `docs/dev-guide/contributing.md`  
**Line:** 35

**Current:**
```markdown
See {doc}`architecture` for the full error handling strategy.
```

**Fix:**
```markdown
See {doc}`dev-guide/architecture` for the full error handling strategy.
```

**Rationale:** `{doc}` requires full path when not in same directory.

---

### Issue #8: Missing Migrate Failure Modes

**File:** `docs/user-guide/commands.md`  
**Section:** `## migrate` (lines 77-101)

**Current failure cases (lines 99-101):**
- No `requirements.txt` found
- `pyproject.toml` already has `[project]` section

**Missing failure modes:**
- Unparseable lines in requirements.txt
- Conflicting extras (e.g., multiple `extra` sections)
- Invalid version specifiers

**Fix:** Add to failure cases section:

```markdown
### Failure Cases

- No `requirements.txt` found — exits normally with suggestion to use `init`
- `pyproject.toml` already has `[project]` section — exits normally without changes
- Unparseable lines in requirements.txt — reports line number and parse error
- Conflicting extras — warns and skips, keeps first definition
- Invalid version specifiers — reports specific specifier and error
```

---

### Issue #9: Missing Migration Edge Cases

**File:** `docs/user-guide/workflows.md`  
**Section:** `## Migrate from requirements.txt` (lines 25-47)

**Current content:** Basic workflow without edge cases.

**Missing edge cases:**
- Version specifier conversion failures (e.g., unsupported operators)
- Conflicting extras between requirements.txt and generated pyproject.toml

**Fix:** Add note after step 3:

```markdown
### Edge Cases

- **Version specifier conversion**: Some pip specifiers (e.g., `~=`) don't map directly to PEP 440. The tool attempts closest equivalent but review generated `pyproject.toml`.
- **Conflicting extras**: If requirements.txt specifies extras that conflict with generated `[project.optional-dependencies]`, review and merge manually.
```

---

## Low Priority

Quality improvements.

### Issue #10: Architecture Structure

**File:** `docs/dev-guide/architecture.md`  
**Status:** Feedback

**Observation:** Structure mirrors source code organization.

**Suggestion:** Consider reorganizing by reader task:
- "Reading appenv code" (entry points, flow)
- "Adding a new command" (dispatch, subparsers)
- "Debugging issues" (error codes, logging)

**Priority:** Backlog — improves clarity but not broken.

---

### Issue #11: Command Overview Table

**File:** `docs/user-guide/commands.md`  
**Status:** Enhancement

**Suggestion:** Add discoverability table at start:

```markdown
## Command Overview

| Command | Purpose |
|---------|---------|
| `init` | Create new project |
| `migrate` | Convert requirements.txt |
| `prepare` | Create venv |
| `reset` | Clean venv |
| `update-lockfile` | Generate lockfile |
| `python` | REPL in venv |
| `run` | Execute venv binary |
| `uv` | Pass-through to uv |
| `version` | Show version |
```

**Priority:** Backlog — improves discoverability.

---

### Issue #12: Quickstart Use-Case Context

**File:** `docs/_snippets/quickstart.md`  
**Status:** Enhancement

**Missing context:**
- `Ctrl+C` handling (SIGINT exits cleanly)
- Prompt skipping (all options can be passed as arguments)

**Suggestion:** Add note after first code block:

```markdown
> **Tip:** Press `Ctrl+C` to exit prompts early. Pass `--help` to see all options for non-interactive use.
```

**Priority:** Backlog — UX improvement.

---

## Files to Change

| Priority | File | Change Type |
|----------|------|-------------|
| CRITICAL | `docs/user-guide/installation.md` | Edit line 5 |
| CRITICAL | `src/appenv.py` | Edit lines 50-54 |
| CRITICAL | `docs/dev-guide/architecture.md` | Edit line 12 |
| STRUCTURAL | `docs/dev-guide/index.md` | Create new file |
| STRUCTURAL | `docs/user-guide/index.md` | Create new file |
| STRUCTURAL | `docs/index.md` | Add toctree entry |
| MEDIUM | `docs/dev-guide/contributing.md` | Edit line 35 |
| MEDIUM | `docs/user-guide/commands.md` | Add failure modes |
| MEDIUM | `docs/user-guide/workflows.md` | Add edge cases note |
| LOW | `docs/user-guide/commands.md` | Add overview table |
| LOW | `docs/_snippets/quickstart.md` | Add tip |
| LOW | `docs/dev-guide/architecture.md` | Consider restructure |

---

## Summary

- **3 Critical fixes** must be applied before next release
- **3 Structural fixes** required for proper navigation
- **3 Medium priority** address documentation gaps
- **3 Low priority** are enhancements for backlog