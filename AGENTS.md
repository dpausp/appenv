# AGENTS.md - Coding Agent Guidelines for appenv

## Project Overview

appenv is a single-file Python application bootstrapping mechanism for CLI applications.
It manages virtual environments using uv and supports pyproject.toml-based workflows.

## Build/Lint/Test Commands

```bash
# Run all tests
uv run pytest

# Run single test file
uv run pytest tests/test_pyproject.py

# Run single test function
uv run pytest tests/test_pyproject.py::test_prepare_pyproject_creates_venv

# Run tests with coverage
uv run pytest --cov=appenv --cov-report=term-missing

# Run all CI checks (lint, format, type-check, test)
tox

# Run linting and formatting only
uv run ruff check --fix .
uv run ruff format .

# Type checking
uv run ty check .

# Fix trailing whitespace
uv run python scripts/fix_whitespace.py .
```

## Code Style

### Imports

```python
# Standard library first (alphabetical)
import argparse
import os
import subprocess
import sys
from pathlib import Path
from typing import cast

# Third-party (if any)
import pytest

# Local imports last
import appenv
```

### Formatting

- Target Python 3.9+ (see `requires-python` in pyproject.toml)
- Line length: default ruff (88 chars)
- Use double quotes for strings
- Trailing commas in multi-line structures

### Type Hints

- Minimal typing - use when it clarifies complex logic
- `from typing import cast` for type narrowing
- Return types optional for simple functions

```python
def find_files(root: Path) -> list[Path]:
    """Find text files to fix."""
    ...

def parse_requires_python(pyproject_path):  # No annotation needed
    """Parse requires-python from pyproject.toml."""
    ...
```

### Naming Conventions

- Functions: `snake_case`
- Constants: `UPPER_SNAKE_CASE` (module level)
- Private functions: `_leading_underscore`
- Exit codes: `EXIT_CODE_*` prefix

### Error Handling

Use BSD sysexits.h exit codes:

```python
EXIT_CODE_DATAERR = 65      # Input data issue
EXIT_CODE_NOINPUT = 67      # Missing input file
EXIT_CODE_UNAVAILABLE = 68  # Resource unavailable
```

For spec-first exception handling, use `# SPEC:` comments:

```python
# SPEC: SRS-F004-uv-version-check - Validate uv meets minimum requirements
# Action: Exit with actionable upgrade instructions if version too old
try:
    result = subprocess.run([uv_bin, "--version"], check=True)
except subprocess.CalledProcessError as e:
    print(f"Warning: Could not determine uv version: {e}")
    return (0, 0, 0)
```

### Docstrings

- Use triple-double-quotes
- First line: brief description
- Follow with blank line and details if needed

```python
def ensure_best_python(base):
    """Ensure best Python for pyproject.toml workflow.

    Reads requires-python from pyproject.toml and selects the newest
    available Python that satisfies the constraint.
    """
    ...
```

## Testing Conventions

### Test File Structure

```
tests/
├── conftest.py          # Shared fixtures
├── test_pyproject.py    # pyproject.toml workflow tests
├── test_prepare.py      # Environment preparation tests
├── test_coverage.py     # Coverage-targeted tests
└── integration/         # Integration tests (pexpect-based)
```

### Test Naming

```python
def test_<function>_<scenario>(tmpdir, monkeypatch):
    """Brief description of what is being tested."""
```

### Fixtures

- `tmpdir`: pytest built-in for temporary directories
- `monkeypatch`: pytest built-in for mocking
- `workdir`: project fixture (from conftest.py) - changes to tmpdir and back

### Mocking Pattern

```python
def test_something(tmpdir, monkeypatch):
    monkeypatch.chdir(tmpdir)
    base = Path(tmpdir)

    # Create test files
    (base / "pyproject.toml").write_text("[project]\nname = 'test'\n")

    # Mock external dependencies
    monkeypatch.setattr(appenv, "ensure_uv", lambda base: None)

    # Call and assert
    result = appenv.some_function(base)
    assert result == expected
```

## Architecture Notes

- Single-file design: `src/appenv.py` contains all logic
- No external runtime dependencies (only dev dependencies)
- Uses uv for venv management (bootstrapped automatically)
- Version defined in `__version__ = "YYYY.M.P"` format

## Version Management

- Calendar versioning: `YYYY.MINOR.PATCH`
- Update in `src/appenv.py`: `__version__ = "2026.2.0"`
