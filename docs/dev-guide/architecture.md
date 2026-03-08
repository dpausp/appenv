# Architecture

Understanding appenv's design and internals.

## Design Philosophy

appenv is designed around these principles:

1. **Single-file**: The entire application is one Python file (`appenv.py`)
2. **Self-bootstrapping**: No external dependencies required
3. **uv-based**: Uses uv for fast, reliable virtual environment management
4. **Convention over configuration**: Sensible defaults, minimal setup

## Core Components

### Main Entry Point

```python
def main():
    # 1. Ensure correct Python version
    ensure_best_python(base)
    
    # 2. Clear PYTHONPATH for isolation
    os.environ.pop("PYTHONPATH", None)
    
    # 3. Dispatch to run or meta commands
    appenv = AppEnv(base, original_cwd)
    if application_name == "appenv":
        appenv.meta(remaining)
    else:
        appenv.run(application_name, remaining)
```

### Python Version Selection

The `ensure_best_python()` function:

1. Reads `requires-python` from `pyproject.toml`
2. Finds all Python versions in PATH
3. Selects newest version satisfying constraints
4. Re-execs with selected Python if needed

### uv Management

The `get_uv_bin()` function implements fallback priority:

1. **PATH uv** (≥0.5.0) → use it
2. **Cached `.appenv/.uv`** → validate and use
3. **Nix build** → `nix build nixpkgs#uv`
4. **pip install** → `pip install uv`

### Virtual Environment

The `_prepare_venv()` method:

1. Creates `.appenv/venv` directory
2. Uses `uv venv` with explicit Python path
3. Syncs dependencies with `uv sync`
4. Creates `.venv` symlink for IDE compatibility

## Project Structure

```
project/
├── pyproject.toml     # Project configuration
├── uv.lock            # Dependency lockfile
├── appenv             # Bootstrap script (copy of appenv.py)
├── mycommand          # Symlink → appenv
├── .venv              # Symlink → .appenv/venv
└── .appenv/
    ├── venv/          # Virtual environment
    ├── .uv/           # uv binary (if built with nix)
    ├── logs/          # Command logs
    └── profiling/     # Profiling data
```

## Command Dispatch

### Run Mode (symlink name)

When called via symlink (e.g., `./mycommand`):

```python
appenv.run(application_name, remaining)
# → execv(.appenv/venv/bin/mycommand, argv)
```

### Meta Mode (appenv command)

When called as `./appenv <command>`:

```python
appenv.meta(remaining)
# → argparse dispatches to method
```

## Key Functions

| Function | Purpose |
|----------|---------|
| `ensure_best_python` | Select and re-exec with best Python |
| `get_uv_bin` | Find or install uv |
| `ensure_uv` | Get uv with version check |
| `uv_cmd` | Execute uv command |
| `parse_requires_python` | Parse version constraints |
| `find_available_pythons` | Find Pythons in PATH |

## AppEnv Class Methods

| Method | Purpose |
|--------|---------|
| `run` | Execute application command |
| `meta` | Handle appenv subcommands |
| `prepare` | Create production venv |
| `develop` | Create dev venv |
| `init` | Interactive project creation |
| `migrate` | Convert requirements.txt |
| `reset` | Remove venv |
| `update_lockfile` | Generate uv.lock |

## Error Handling

appenv uses BSD sysexits.h exit codes:

| Code | Constant | Meaning |
|------|----------|---------|
| 65 | `EXIT_CODE_DATAERR` | Input data issue |
| 67 | `EXIT_CODE_NOINPUT` | Missing input file |
| 68 | `EXIT_CODE_UNAVAILABLE` | Resource unavailable |

## Logging

- Logs stored in `.appenv/logs/<command>-<timestamp>.log`
- Console output enabled with `APPENV_VERBOSE=1`
- Old logs cleaned up after 7 days

## Extension Points

### Custom Commands

Add new subcommands by:

1. Adding parser in `meta()`
2. Creating handler method
3. Setting `func` default to method

### Environment Variables

| Variable | Usage |
|----------|-------|
| `APPENV_VERBOSE` | Enable verbose logging |
| `APPENV_EXTRAS` | Install optional dependencies |
| `APPENV_PROFILE` | Enable cProfile |
| `APPENV_BEST_PYTHON` | Selected Python path |
| `UV_PROJECT_ENVIRONMENT` | venv location |
