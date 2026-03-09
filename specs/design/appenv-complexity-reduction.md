# appenv Complexity Reduction Refactoring

## Context

The appenv codebase has 3 functions exceeding cyclomatic complexity threshold of 15:
- `_prepare_venv` (25)
- `migrate` (25)
- `_init_project` (18)

These complexity levels make the code harder to understand, test, and maintain.
Standard refactoring patterns (extract method) will reduce complexity without
changing behavior.

Cynefin domain: Complicated - well-established refactoring patterns apply.

## Decisions

### extract-helper-methods

- Context: Three functions exceed cyclomatic complexity threshold
- Decision: Extract 6 helper methods following single responsibility principle
- Consequences: Each helper has one clear purpose, easier to test in isolation

### preserve-public-api

- Context: 45 existing tests validate current behavior
- Decision: All extractions are internal (private functions), no public API changes
- Consequences: Tests pass unchanged, no migration required for callers

### extraction-order-by-risk

- Context: Some extractions are simpler (pure functions), others have side effects
- Decision: Extract in order: pure functions first, then side-effect operations
- Consequences: Earlier extractions validate approach before tackling complex ones

## Extraction Specifications

### 1. `_parse_requirements_file`

**Source:** `migrate` lines 965-972

**Signature:**
```python
def _parse_requirements_file(content: str) -> tuple[list[str], list[str]]:
    """Parse requirements.txt content into dependencies and editable specs."""
```

**Logic:**
- Split content by lines
- Filter non-empty, non-comment lines
- Separate editable (`-e `) from regular dependencies
- Returns: `(dependencies, editable_specs)`

**Complexity reduction:** Removes list comprehension + filtering from `migrate`

---

### 2. `_process_editable_installs`

**Source:** `migrate` lines 974-1000

**Signature:**
```python
def _process_editable_installs(
    specs: list[str],
    base_dir: Path
) -> tuple[dict[str, dict], list[str]]:
    """Process editable install specs.

    Returns:
        tuple of (editable_sources, warnings)
        - editable_sources: {package_name: {path: str, editable: bool}}
        - warnings: list of warning messages for skipped specs
    """
```

**Logic:**
- Iterate over editable specs
- Call `parse_editable_spec` for each
- Call `extract_package_name_from_path` to get package name
- Build dependency string with extras
- Build source config with path normalization
- Collect warnings for unparseable specs

**Complexity reduction:** Most complex extraction - removes loop with conditionals

---

### 3. `_parse_python_preference`

**Source:** `migrate` lines 1016-1029

**Signature:**
```python
def _parse_python_preference(content: str) -> str:
    """Parse python preference from requirements.txt content.

    Returns minimum Python version from preference comment, or "3.10" default.
    """
```

**Logic:**
- Search for `# appenv-python-preference:` comment line
- Parse comma-separated versions from the comment
- Sort versions numerically (ascending)
- Return minimum version
- Return "3.10" if no preference found

**Complexity reduction:** Pure function, easy to test

---

### 4. `_cleanup_old_appenv_entries`

**Source:** `_prepare_venv` lines 866-882

**Signature:**
```python
def _cleanup_old_appenv_entries(appenv_dir: Path, log: logging.Logger) -> None:
    """Remove old hash-based venvs and files from .appenv directory.

    Keeps: venv, .uv, logs, profiling
    """
```

**Logic:**
- Define keep set: `{"venv", ".uv", "logs", "profiling"}`
- Iterate over `.appenv` contents
- Remove items not in keep set
- Handle both files and directories

**Complexity reduction:** Removes iteration + conditional from `_prepare_venv`

---

### 5. `_setup_command_symlink`

**Source:** `_init_project` lines 1118-1140

**Signature:**
```python
def _setup_command_symlink(
    target: Path,
    command_name: str | None,
    appenv_script: Path,
    project_name: str
) -> str:
    """Setup command symlink to appenv.

    Args:
        target: Project directory
        command_name: Explicit name, or None to detect existing symlinks
        appenv_script: Path to appenv script
        project_name: Fallback name for new symlink

    Returns:
        The command name (either provided or detected/created)
    """
```

**Logic:**
- If `command_name` provided: create/replace symlink
- If `command_name` is None: find existing symlinks or create with project name
- Handle broken symlinks (unlink before creating)
- Print appropriate messages

**Complexity reduction:** Removes symlink logic with two branches from `_init_project`

---

### 6. `_generate_pyproject_content`

**Source:** `_init_project` lines 1072-1107

**Signature:**
```python
def _generate_pyproject_content(
    project_name: str,
    description: str,
    dependencies: list[str],
    python_version: str,
    editable_sources: dict[str, dict],
    existing_content: str | None = None
) -> str:
    """Generate pyproject.toml content.

    Args:
        existing_content: If provided, merge [project] section into existing
    """
```

**Logic:**
- Generate `[project]` section with dependencies formatted as TOML array
- Generate `[tool.uv.sources]` section if editable sources exist
- Merge with existing content or return standalone
- Returns: complete pyproject.toml content string

**Complexity reduction:** Removes string building + conditional merge from `_init_project`

## Implementation Order

1. **Phase 1: Pure Functions** (lowest risk)
   - `_parse_requirements_file`
   - `_parse_python_preference`
   - `_generate_pyproject_content`

2. **Phase 2: Side Effects** (medium risk)
   - `_cleanup_old_appenv_entries`
   - `_setup_command_symlink`

3. **Phase 3: Complex Logic** (highest risk)
   - `_process_editable_installs`

## Constraints

- All 45 existing tests must pass unchanged
- Public API signatures remain compatible
- File outputs must be identical (pyproject.toml, symlinks)
- Exit codes (BSD sysexits) preserved: `EXIT_CODE_DATAERR`, `EXIT_CODE_NOINPUT`, `EXIT_CODE_UNAVAILABLE`
- Type annotations go in `.pyi` stub file, not source

## References

- AGENTS.md - Project coding conventions
- tests/test_migrate.py - Migration test coverage (18 tests)
- tests/test_prepare.py - Prepare/venv test coverage (18 tests)
- tests/test_init.py - Init command test coverage (7 tests)
