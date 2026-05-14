# Common Workflows

Practical workflows for using appenv. See {doc}`locking-behavior` for background on how appenv handles dependency locking.

## Migrate from requirements.txt

For existing appenv projects that still use `requirements.txt`:

```console
# Option A: If appenv is already in your project
./appenv migrate

# Option B: If not (e.g. running via uvx)
uvx appenv migrate

# After migration, verify and clean up
./http --help
rm requirements.txt
```

`migrate` reads `requirements.txt`, creates `pyproject.toml` with your
dependencies, generates `uv.lock`, and cleans up old `.appenv/` artifacts.
The `requirements.txt` file is kept so you can verify the migration worked
before removing it.

Version pins from `requirements.txt` are **not** preserved — `uv.lock`
resolves fresh to the latest compatible versions. Check `uv.lock` after
migration if exact versions matter.

## New Project from Scratch

```console
# 1. Create project directory
mkdir myproject && cd myproject

# 2. Initialize (answer prompts)
uvx appenv init

# 3. Add dependencies
./appenv uv add requests click

# 4. Run the exposed binary
./http --help
```

The symlink `http -> appenv` runs the `http` binary from your installed dependencies. See {doc}`commands` for details on symlink dispatch.

```console
ln -s appenv pytest
./pytest -xvs
```

## Development Workflow

```console
# Run the exposed binary (auto-prepares venv on first use)
./http

# Run dev tools — use uv run to include dev dependencies
uv run pytest -xvs
uv run ruff check .
uv run ruff format .

# Add dependencies
./appenv uv add --group dev pytest
./appenv update-lockfile
```

### Adding and Upgrading Dependencies

```console
# Add a production dependency (updates both pyproject.toml and uv.lock)
./appenv uv add requests

# Add a development dependency
./appenv uv add --group dev pytest

# Upgrade a specific package
./appenv uv lock --upgrade-package requests

# Upgrade all packages
./appenv uv lock --upgrade
```

## CI/CD Integration

### GitHub Actions

```yaml
name: Test
on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.13"

      - name: Install uv
        run: curl -LsSf https://astral.sh/uv/install.sh | sh

      - name: Run tests
        run: uv run pytest
```

`./http` auto-prepares the venv on first use — no explicit preparation step needed in CI.

### Container Environments

In containers or on CIFS mounts, uv may warn about failed hardlinks:

```console
warning: Failed to hardlink files; falling back to full copy.
```

This is harmless. To suppress it, set `UV_LINK_MODE=copy`:

```console
UV_LINK_MODE=copy ./http
```

See [astral-sh/uv#6101](https://github.com/astral-sh/uv/issues/6101) for details.

## Managing Multiple Python Versions

```toml
# pyproject.toml
[project]
requires-python = ">=3.11,<3.14"
```

appenv automatically selects the best available Python version. See {doc}`locking-behavior` for details on UV universal resolution across the `requires-python` range.

## Debugging Issues

### Verbose Mode

```console
APPENV_VERBOSE=1 ./http --version
```

Shows uv commands being executed, Python version selection, and venv creation steps.

### Reset and Rebuild

```console
./appenv reset
```

### Python Version Selection

If the wrong Python version is selected, check:

1. **`requires-python`** in `pyproject.toml` — this is the constraint
2. **PATH** — appenv scans `python3.X` binaries newest-first
3. **APPENV_BEST_PYTHON** — set by appenv after selection, check with verbose mode

Override selection:

```console
APPENV_BEST_PYTHON=/usr/bin/python3.12 ./mkdocs build
```

## Working with Extras

```toml
# pyproject.toml
[project.optional-dependencies]
dev = ["pytest", "ruff"]
```

```console
APPENV_EXTRAS=dev ./http
```

## Updating appenv Itself

```console
# If appenv is already in your project
./appenv self-update

# If running via uvx, specify the target directory
uvx appenv self-update .

# Check if update is needed (useful in CI)
./appenv self-update --check
```

`self-update` compares the `__version__` in the local script with the currently running version and replaces it if they differ.

When running via `uvx` (or `pip install`), appenv is externally managed and cannot update itself in place. Use `uvx appenv self-update .` to update the script in your current project directory.

### Manual Download

If uvx is not available, download appenv directly:

```console
curl -sL https://raw.githubusercontent.com/flyingcircusio/appenv/master/src/appenv.py -o appenv
chmod +x appenv
```
