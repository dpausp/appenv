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

## New Classes and Data Structures

### UvVersion (dataclass)

**Location:** lines 322-351

```python
@dataclass(order=True, frozen=True)
class UvVersion:
    major: int
    minor: int
    patch: int

    def __str__(self) -> str:
        """Returns 'unknown' for (0,0,0), otherwise 'major.minor.patch'."""

    @property
    def valid(self) -> bool:
        """Returns True if version >= minimum required (UV_MIN_VERSION)."""

    @staticmethod
    def unknown() -> UvVersion:
        """Returns UvVersion(0, 0, 0) for unparseable versions."""

    @staticmethod
    def minimum() -> UvVersion:
        """Returns UvVersion(*UV_MIN_VERSION) - the minimum required version."""

    @staticmethod
    def from_string(version_str: str) -> UvVersion:
        """Parse 'major.minor.patch' string. Raises InvalidVersionError on failure."""
```

**Purpose:** Type-safe version comparison, replaces string-based version handling.

---

### Pyproject (class)

**Location:** lines 786-829

```python
class Pyproject:
    def __init__(self, base: Path) -> None:
        """Initialize with base directory. Sets path and requirements_txt attributes."""

    def migrate_from_requirements_txt(self) -> Self:
        """Create pyproject.toml from requirements.txt. Returns new Pyproject instance."""

    @cached_property
    def content(self) -> str:
        """Returns file content or empty string if not exists."""

    @cached_property
    def has_project_section(self) -> bool:
        """Check if [project] section exists in TOML."""

    def can_be_created_from_requirements_txt(self) -> bool:
        """Returns True if no [project] section and requirements.txt exists."""

    @property
    def exists(self) -> bool:
        """Returns True if pyproject.toml file exists."""
```

**Purpose:** Encapsulates pyproject.toml operations, provides cached access to content.

---

### AppEnvSettings (dataclass)

**Location:** lines 1004-1020

```python
@dataclass(frozen=True)
class AppEnvSettings:
    verbose: bool
    extras: str | None
    profile: bool
    profile_output: str | None
    basedir: Path | None

    @staticmethod
    def from_env() -> AppEnvSettings:
        """Read settings from environment variables (APPENV_*)."""
```

**Purpose:** Type-safe settings container, replaces loose environment variable access.

---

### RequirementsTxtInfo (NamedTuple)

**Location:** lines 673-676

```python
class RequirementsTxtInfo(NamedTuple):
    dependencies: list[str]
    editable_warnings: list[str]
    python_versions: list[str]
```

**Purpose:** Structured return type for requirements.txt parsing, replaces tuple unpacking.

---

### Helper Functions

**ensure_pyproject(base: Path) -> Pyproject**
- Location: line 832
- Validates pyproject.toml exists with [project] section
- Exits with EXIT_CODE_NOINPUT if missing or invalid

**ensure_lock_file(base: Path) -> Path**
- Location: line 855
- Validates uv.lock exists
- Exits with EXIT_CODE_NOINPUT if missing, returns lock file path otherwise

**_read_lockfile_lines(lock_file: Path) -> set[str]**
- Location: line 730
- Reads lockfile, returns set of non-empty, non-comment lines

**_run_uv_lock_diff(uv_bin: Path, base: Path, verbose: bool) -> str**
- Location: line 738
- Runs uv lock in temp directory, shows colored diff
- Returns "No changes" or diff output

**_create_lockfile_summary(old_lines: set[str], new_lines: set[str]) -> str**
- Location: line 762
- Compares old/new lockfile line sets
- Returns summary string like "✓ Created (+42 lines)"

**configure_logging(command_name: str, log_dir: Path, verbose: bool)**
- Location: line 251
- Sets up file logging (always) and console logging (if verbose)
- Creates log file: `{log_dir}/{command_name}-{timestamp}.log`

**find_project_base(base: Path) -> Path**
- Location: line 141
- Searches upward from base for pyproject.toml
- Returns base if no pyproject.toml found

## Signature Changes

### Function Signature Updates

| Function | Old Signature | New Signature |
|----------|---------------|---------------|
| `uv_cmd` | `(args, verbose=False, **kwargs)` | `(uv_bin: Path, args: list[str], verbose=False, **kwargs)` |
| `get_uv_version` | `() -> str` | `(uv_bin: Path) -> UvVersion` |
| `AppEnv.__init__` | `(base, original_cwd)` | `(base, original_cwd, settings: AppEnvSettings)` |
| `_parse_requirements_file` | `(content: str) -> tuple[list[str], list[str]]` | `(requirements_path: Path) -> RequirementsTxtInfo` |
| `_parse_python_preference` | `(content: str) -> str` | `(content: str) -> list[str]` |
| `find_project_base` | `(base: Path, original_cwd: Path)` | `(base: Path)` |

### Rationale

- **uv_cmd**: Explicit `uv_bin` required to avoid implicit uv resolution on every call
- **get_uv_version**: Returns `UvVersion` for type-safe comparison instead of string parsing
- **AppEnv.__init__**: `AppEnvSettings` groups environment configuration in one place
- **_parse_requirements_file**: Takes `Path` directly (no string conversion needed), returns `RequirementsTxtInfo` for named field access
- **_parse_python_preference**: Returns `list[str]` (all versions) instead of just minimum, caller decides which to use
- **find_project_base**: `original_cwd` was unused, removed for clarity

## Extraction Specifications

### 1. `_parse_requirements_file`

**Source:** `migrate` lines 965-972

**Signature:**
```python
def _parse_requirements_file(requirements_path: Path) -> RequirementsTxtInfo:
    """Parse requirements.txt content into structured data.

    Returns RequirementsTxtInfo with dependencies, warnings for editables, python versions.
    """
```

**Logic:**
- Read content from requirements_path
- Split content by lines
- Filter non-empty, non-comment lines
- Separate editable (`-e `) from regular dependencies
- Generate warnings for editable installs (not supported)
- Parse python preference comments
- Returns: `RequirementsTxtInfo` named tuple

**Complexity reduction:** Removes list comprehension + filtering from `migrate`

---

### 2. `_parse_python_preference`

**Source:** `migrate` lines 1016-1029

**Signature:**
```python
def _parse_python_preference(content: str) -> list[str]:
    """Parse python preference from requirements.txt content.

    Returns list of Python versions from preference comment, or ["3.10"] default.
    """
```

**Logic:**
- Search for `# appenv-python-preference:` comment line
- Parse comma-separated versions from the comment
- Return list of versions (caller decides which to use)
- Return `["3.10"]` if no preference found

**Complexity reduction:** Pure function, easy to test

---

### 3. `_cleanup_old_appenv_entries`

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

### 4. `_setup_command_symlink`

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

### 5. `_generate_pyproject_content`

**Source:** `_init_project` lines 1072-1107

**Signature:**
```python
def _generate_pyproject_content(
    project_name: str,
    description: str,
    dependencies: list[str],
    python_version: str,
    existing_content: str | None = None
) -> str:
    """Generate pyproject.toml content.

    Args:
        existing_content: If provided, merge [project] section into existing
    """
```

**Logic:**
- Generate `[project]` section with dependencies formatted as TOML array
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

## Constraints

- All 45 existing tests must pass unchanged
- Public API signatures remain compatible
- File outputs must be identical (pyproject.toml, symlinks)
- Exit codes (BSD sysexits) preserved: `EXIT_CODE_DATAERR`, `EXIT_CODE_NOINPUT`, `EXIT_CODE_UNAVAILABLE`
- Type annotations go in `.pyi` stub file, not source

## References

- AGENTS.md - Project coding conventions
- tests/test_migrate.py - Migration test coverage
- tests/test_prepare.py - Prepare/venv test coverage
- tests/test_init.py - Init command test coverage
