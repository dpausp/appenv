# Commands Reference

Complete reference for all appenv commands.

## Global Options

```
./appenv --help
```

## update-lockfile

Update the dependency lockfile (`uv.lock`). See {doc}`locking-behavior` for details on UV's locking model.

```text
./appenv update-lockfile           # Update lockfile
./appenv update-lockfile --diff    # Show changes without writing
./appenv update-lockfile -v        # Verbose output
```

### Options

| Option | Description |
|--------|-------------|
| `--diff` | Show full diff without writing lockfile |
| `-v, --verbose` | Show detailed information |

See {doc}`workflows` for detailed examples.

## init

Create a new `pyproject.toml` project interactively.

```text
$ ./appenv init
Let's create a new pyproject.toml project.

What should the command be named? [app] http
Enter dependencies (one per line, empty line to finish):
  Default: http
  Dependency: httpie
  Dependency: 
Project name [http-app]: http
Description []: HTTP CLI
Minimum Python version [3.10]: 3.14

Created pyproject.toml
Created http symlink

Done. pyproject.toml created.

Generating lockfile ...
✓ Created (+273 lines)

Run `./http` to bootstrap and run

$ ./http
Installing httpie ...
http: warning: command-line flag syntax is deprecated
```

### Prompts

1. Command name (default: `app`)
2. Dependencies (one per line)
3. Project name (default: `<command>-app`)
4. Description
5. Minimum Python version (default: `3.10`)

See {doc}`workflows` for a detailed example.

### If pyproject.toml Already Exists

```text
$ ./appenv init
pyproject.toml already exists in /path/to/project.
Nothing to do.
Edit pyproject.toml manually to make changes.
```

## migrate

Migrate from `requirements.txt` to `pyproject.toml`. See {doc}`workflows` for detailed examples, features, and limitations.

```text
./appenv migrate
```

## reset

Remove the virtual environment and clean up legacy artifacts.

```text
./appenv reset
```

### What It Removes

- `.venv` symlink
- `.appenv/venv` directory
- Old hash-based venvs in `.appenv/`
- Old `.venv` directory (if not a symlink)

### What It Preserves

- Logs and profiling data in `.appenv/`
- `pyproject.toml` and `uv.lock`
- Source code and other project files

### Example Usage

```text
# After experiencing issues with the virtual environment
$ ./appenv reset
Removing .venv symlink ...
Removing .appenv/venv ...

# Then recreate it
$ ./appenv prepare
```

## version

Show appenv version.

```text
./appenv version
```

## prepare

Create the virtual environment with production dependencies only.

```text
./appenv prepare
```

### Details

- Uses `uv sync --no-dev --frozen` - requires an existing `uv.lock` and will not modify it
- Excludes dev dependencies (`[dependency-groups] dev`)
- Creates `.venv` symlink for IDE compatibility
- Called automatically when running the application via the symlink (e.g., `./mycommand`)

### Example Workflow

```text
# First time setup
$ ./appenv update-lockfile   # Create lockfile if needed
$ ./appenv prepare           # Create production venv

# Subsequent runs - prepares environment automatically when needed
$ ./mycommand --help

# Explicit preparation (e.g., after changing dependencies)
$ ./appenv prepare
```

## develop

Create the virtual environment with dev dependencies (from `[dependency-groups] dev`).

```text
./appenv develop
```

### Details

- Installs both production and dev dependencies
- Uses `uv sync` without `--frozen`, so the lockfile may be updated if `pyproject.toml` has changed
- Useful for development when you need tools like pytest, ruff, mypy, etc.
- Does not require an existing lockfile (will create one if missing)

### Example Usage

```text
# Set up development environment
$ ./appenv develop

# Run tests
$ ./appenv run pytest

# Code formatting
$ ./appenv run ruff format .

# Type checking
$ ./appenv run mypy src/

# After adding new dev dependencies
$ ./appenv uv add --group dev black
$ ./appenv develop  # Re-sync to include new package
```

## python

Start a Python REPL in the virtual environment.

```text
./appenv python                           # Start REPL
./appenv python -c "print('hello')"       # Execute code
./appenv python script.py --verbose       # Run script with args
```

### Details

- Automatically ensures the virtual environment is prepared (equivalent to running `prepare` first)
- Uses the Python interpreter selected by appenv based on `requires-python` in `pyproject.toml`
- Exits the REPL with `Ctrl+D` or `exit()`

### Example

```text
$ ./appenv python
Python 3.11.0 (main, Sep  1 2023, 00:00:00) [GCC 11.2.0]
Type "help", "copyright", "credits" or "license" for more information.
>>>
```

## run

Run a script from the venv's bin directory. Additional arguments are passed through to the target script.

```text
./appenv run pytest
./appenv run ruff check .
./appenv run script.py --verbose --flag
```

### Details

- Automatically prepares the virtual environment if needed (equivalent to running `prepare` first)
- Finds executables in the virtual environment's `bin/` directory
- Passes all arguments directly to the target script

### Common Examples

```text
# Run tests
$ ./appenv run pytest -xvs

# Lint code
$ ./appenv run ruff check .

# Format code
$ ./appenv run ruff format .

# Run custom scripts
$ ./appenv run ./scripts/deploy.py --env=staging

# Run a one-off Python script
$ ./appenv run python -c "import sys; print(sys.version)"
```

## uv

Run uv with appenv-configured environment.

```text
./appenv uv pip install requests    # Install additional package
./appenv uv add black               # Add to dependencies
./appenv uv sync                    # Re-sync dependencies
```

See {doc}`workflows` for detailed dependency management examples.

## settings

Show environment variables and settings.

```text
./appenv settings
```

### Example Output

```text
$ ./appenv settings
appenv environment:

  APPENV_EXTRAS: (not set)
    Extras to install (comma-separated)

  APPENV_VERBOSE: (not set)
    Show verbose output

  APPENV_PROFILE: (not set)
    Enable profiling

  APPENV_BASEDIR: /path/to/project
    Base directory of the project

  APPENV_BEST_PYTHON: /usr/bin/python3.11
    Selected Python interpreter

  UV_PROJECT_ENVIRONMENT: /path/to/project/.appenv/venv
    Virtual environment location
```

### Details

- Displays all environment variables that influence appenv's behavior
- Shows computed values like the selected Python interpreter and venv location
- Helpful for debugging configuration issues

## profiling

Manage profiling data. Enable with `APPENV_PROFILE=1`.

```text
./appenv profiling list              # List recent profiles
./appenv profiling show              # Show latest profile with pstats
./appenv profiling show file.prof    # Show specific profile
./appenv profiling snakeviz          # Open latest profile in snakeviz
```

### Options

| Subcommand | Description |
|------------|-------------|
| `list` | List recent profiles |
| `show [file]` | Show profile with pstats |
| `snakeviz [file]` | Open in snakeviz web UI |

See {doc}`workflows` for detailed examples.

## Environment Variables

| Variable | Description |
|----------|-------------|
| `APPENV_VERBOSE` | Show verbose output during bootstrap |
| `APPENV_EXTRAS` | Extras to install (comma-separated) |
| `APPENV_PROFILE` | Enable profiling (any non-empty value) |
| `APPENV_BASEDIR` | Base directory of the project (auto-set) |
| `APPENV_BEST_PYTHON` | Selected Python interpreter (auto-set) |

See {doc}`workflows` for verbose mode example.

## Requirements

- Python 3.10+
- uv 0.5.0+ (auto-installed if not found)

## Testing

If you want to contribute, please install `tox` and run it.

```text
$ tox
```

## Exit Codes

appenv uses BSD sysexits.h exit codes:

| Code | Name | Description |
|------|------|-------------|
| 65 | DATAERR | Input data issue (e.g., invalid pyproject.toml) |
| 67 | NOINPUT | Missing input file (e.g., no pyproject.toml found) |
| 68 | UNAVAILABLE | Resource unavailable (e.g., required tool not found) |
