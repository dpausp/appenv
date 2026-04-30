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
```

### Options

| Option | Description |
|--------|-------------|
| `--diff` | Show full diff without writing lockfile |

Use `APPENV_VERBOSE=1` for verbose output.

See {doc}`workflows` for detailed examples.

## init

Create a new `pyproject.toml` project interactively.

### Prompts

1. Binary to expose — creates `./<name>` symlink that runs the installed `<name>` binary (default: `app`)
2. Dependencies (one per line, empty line to finish; default: `<command name>`)
3. Project name (default: `<directory name>`)
4. Description
5. Minimum Python version (default: `3.13`)

The symlink name must match a binary installed by your dependencies.
Create additional symlinks to expose more binaries:

```text
# After installing ruff and pytest as dependencies
ln -s appenv ruff
ln -s appenv pytest
./ruff check .
./pytest -xvs
```

### Options

- `path` — Create project in specified directory (default: current directory)

### Non-Interactive Usage

```{todo}
Add `--defaults` flag for non-interactive init. `init --defaults --dep batou` would set dependency, symlink, and description from the dependency name and skip all prompts. Requires at least one `--dep` argument to be useful.
```

### If pyproject.toml Already Exists

```text
$ ./appenv init
pyproject.toml already exists
Nothing to do - edit it manually to make changes
```

### If appenv Script Is Outdated

When the local `./appenv` script has a different version than the running appenv, `init` prints a warning:

```text
Warning: ./appenv is version 0.0.1, running appenv is 2026.3.19.
Run './appenv migrate' to update the script.
```

## migrate

Convert an existing `requirements.txt` into `pyproject.toml`. For appenv projects that still use `requirements.txt` instead of `pyproject.toml`.

```text
./appenv migrate
```

### Options

- `path` — Target directory (default: current directory)

### What It Does

- Reads `requirements.txt` from the current directory
- Creates or updates `pyproject.toml` with those dependencies
- Generates `uv.lock` automatically
- Skips editable installs (`-e`) with a warning
- Cleans up old `.appenv/` artifacts
- Updates the local `./appenv` script if the running version differs from the one on disk
- Creates or updates `.gitignore` with a `.venv` entry

### Running via uvx

If appenv is not yet in your project, you can run migrate directly:

```text
uvx appenv migrate
```

This downloads the latest appenv into your project and runs the migration.

### After Migrating

Test it (`./http --help`), then remove `requirements.txt`.

See {doc}`workflows` for a full migration walkthrough.

### Failure Cases

- No `requirements.txt` found — exits normally with a suggestion to use `init`
- `pyproject.toml` already has `[project]` section — exits normally without changes

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

- Logs in `.appenv/`
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
- Running `./http` (symlink) auto-prepares the venv on first use — same behavior as `prepare`, production deps only

### Example Workflow

```text
# First time setup
$ ./appenv update-lockfile   # Create lockfile if needed

# Just run — venv is prepared automatically
$ ./http --help

# Explicit preparation (e.g., CI or after dependency changes)
$ ./appenv prepare
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
- Production dependencies only — dev dependencies are excluded
- For `python -m pytest` or other dev tool usage, use `uv run` instead:
  `uv run python -m pytest`

### Example

```text
$ ./appenv python
Python 3.x.x ...
Type "help", "copyright", "credits" or "license" for more information.
>>>
```

## uv

Pass-through to the uv binary with appenv's configured environment (Python interpreter, venv paths). Use this when you need uv functionality not covered by dedicated appenv commands.

```text
./appenv uv add requests           # Add production dependency
./appenv uv add --group dev pytest  # Add dev dependency
./appenv uv sync                    # Re-sync dependencies
./appenv uv lock --upgrade          # Upgrade all packages
```

All arguments are passed through to uv unchanged. See {doc}`workflows` for dependency management examples.

## Environment Variables

| Variable | Description |
|----------|-------------|
| `APPENV_VERBOSE` | Show verbose output (uv commands, Python selection) |
| `APPENV_EXTRAS` | Extras to install (comma-separated) |
| `APPENV_BASEDIR` | Base directory of the project (auto-set) |
| `APPENV_BEST_PYTHON` | Selected Python interpreter (auto-set) |

See {doc}`workflows` for verbose mode example.

## Exit Codes

appenv uses BSD sysexits.h exit codes:

| Code | Name | Description |
|------|------|-------------|
| 64 | USAGE | Incorrect command usage (e.g., deprecated run subcommand) |
| 65 | DATAERR | Input data issue (e.g., invalid pyproject.toml) |
| 67 | NOINPUT | Missing input file (e.g., no pyproject.toml found) |
| 68 | UNAVAILABLE | Resource unavailable (e.g., required tool not found) |
