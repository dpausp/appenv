# Commands Reference

Complete reference for all appenv commands.

## Global Options

```
./appenv --help
```

## update-lockfile

Update the dependency lockfile (`uv.lock`).

```bash
./appenv update-lockfile           # Update lockfile
./appenv update-lockfile --diff    # Show changes without writing
./appenv update-lockfile -v        # Verbose output
```

### Options

| Option | Description |
|--------|-------------|
| `--diff` | Show full diff without writing lockfile |
| `-v, --verbose` | Show detailed information |

## init

Create a new `pyproject.toml` project interactively.

```bash
./appenv init
```

### Prompts

1. Command name (default: `app`)
2. Dependencies (one per line)
3. Project name (default: `<command>-app`)
4. Description
5. Minimum Python version (default: `3.10`)

## migrate

Migrate from `requirements.txt` to `pyproject.toml`.

```bash
./appenv migrate
```

### Features

- Parses regular dependencies
- Handles editable installs (`-e ./path`)
- Preserves existing `pyproject.toml` content
- Extracts package names from local paths

### Limitations

- Git URL editable installs are skipped with warning
- PEP 508 direct references are skipped

## reset

Remove the virtual environment.

```bash
./appenv reset
```

Removes:
- `.venv` symlink
- `.appenv/venv` directory
- Old hash-based venvs in `.appenv/`

## version

Show appenv version.

```bash
./appenv version
# Output: appenv 2026.3.5
```

## prepare

Create the virtual environment with production dependencies.

```bash
./appenv prepare
```

- Uses `--frozen` flag for strict lockfile adherence
- Excludes dev dependencies
- Creates `.venv` symlink for IDE compatibility

## develop

Create the virtual environment with dev dependencies.

```bash
./appenv develop
```

- Installs both production and dev dependencies
- Uses `[dependency-groups] dev` from `pyproject.toml`
- Useful for development (pytest, ruff, etc.)

## python

Start a Python REPL in the virtual environment.

```bash
./appenv python
```

## run

Run a script from the venv's bin directory.

```bash
./appenv run pytest
./appenv run ruff check .
```

## uv

Run uv with appenv-configured environment.

```bash
./appenv uv pip install requests    # Install additional package
./appenv uv add black               # Add to dependencies
./appenv uv sync                    # Re-sync dependencies
```

## settings

Show environment variables and settings.

```bash
./appenv settings
```

Output includes:
- `APPENV_EXTRAS` - Extras to install
- `APPENV_VERBOSE` - Verbose output
- `APPENV_PROFILE` - Profiling enabled
- `APPENV_BASEDIR` - Project base directory
- `APPENV_BEST_PYTHON` - Selected Python
- `UV_PROJECT_ENVIRONMENT` - venv location

## profiling

Manage profiling data.

```bash
./appenv profiling list              # List recent profiles
./appenv profiling show              # Show latest with pstats
./appenv profiling show file.prof    # Show specific profile
./appenv profiling snakeviz          # Open in snakeviz
```

### Enable Profiling

```bash
APPENV_PROFILE=1 ./mycommand args
# Output: APPENV_PROFILE enabled, profile output at .appenv/profiling/mycommand-20260303-143022.prof
```

### Options

| Subcommand | Description |
|------------|-------------|
| `list` | List recent profiles |
| `show [file]` | Show profile with pstats |
| `snakeviz [file]` | Open in snakeviz web UI |

## Environment Variables

| Variable | Description |
|----------|-------------|
| `APPENV_VERBOSE` | Show verbose output |
| `APPENV_EXTRAS` | Extras to install (comma-separated) |
| `APPENV_PROFILE` | Enable profiling (any value) |
| `APPENV_PROFILE_OUTPUT` | Custom profiling output file |
| `APPENV_BASEDIR` | Base directory (set by appenv) |
| `APPENV_BEST_PYTHON` | Selected Python interpreter |
