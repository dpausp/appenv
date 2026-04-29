# Common Workflows

Practical workflows for using appenv. See {doc}`locking-behavior` for background on how appenv handles dependency locking.

## New Project from Scratch

```text
# 1. Create project directory
mkdir myproject && cd myproject

# 2. Download appenv
curl -sL https://raw.githubusercontent.com/flyingcircusio/appenv/master/src/appenv.py -o appenv
chmod +x appenv

# 3. Initialize (answer prompts)
# Binary to expose: http
# Dependencies: (press Enter for default, we'll add them next)
# Project name: (press Enter for directory name)
# Description: (press Enter to skip)
# Python version: (press Enter for 3.13)
./appenv init

# 4. Add dependencies
./appenv uv add requests click

# 5. Run the exposed binary
./http --help
```

The symlink `http -> appenv` runs the `http` binary from your
installed dependencies. Expose more binaries by adding symlinks:

```text
ln -s appenv pytest
./pytest -xvs
```

### Extending with Plugins

Many CLI tools support plugins — just add them as dependencies and they
work automatically when you run the symlink:

```text
# Set up mkdocs with the material theme
./appenv init
#   Binary to expose: mkdocs
#   Dependencies: mkdocs, mkdocs-material

./mkdocs serve
# Theme is available immediately — mkdocs-material is in the same venv

# Add more plugins later
./appenv uv add mkdocs-mermaid2-plugin
./mkdocs build   # plugin just works
```

This works for any plugin-based tool: `pytest` with `pytest-cov`,
`pytest-xdist`, `ruff` with config extensions, `ansible` with collections,
etc.

Or with uvx (if appenv is on PyPI):

```text
mkdir myproject && cd myproject
uvx appenv init
```

## Migrate from requirements.txt

For existing appenv projects that still use `requirements.txt`:

```text
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

## Development Workflow

```text
# 1. Run the exposed binary (auto-prepares venv on first use)
./http

# 2. Run dev tools — use uv run to include dev dependencies
uv run pytest -xvs
uv run ruff check .
uv run ruff format .

# 3. After adding dependencies
./appenv uv add --group dev pytest
./appenv update-lockfile
```

### Detailed Dependency Management

#### Adding Dependencies

```text
# Add a production dependency (updates both pyproject.toml and uv.lock)
$ ./appenv uv add requests

# Add a development dependency
$ ./appenv uv add --group dev pytest
```

#### Upgrading Packages

```text
# Upgrade a specific package (within version constraints)
$ ./appenv uv lock --upgrade-package requests

# Upgrade all packages (within version constraints)
$ ./appenv uv lock --upgrade
```

#### Freezing Dependencies for Repeatable Builds

```text
# Create/update lockfile for reproducible installs
$ ./appenv update-lockfile

# First run installs dependencies, subsequent runs use cache
$ ./http GET https://httpbin.org/get
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

      - name: Prepare environment
        run: ./appenv prepare

      - name: Run tests
        run: uv run pytest
```

### Container Environments

In containers or on CIFS mounts, uv may warn about failed hardlinks:

```text
warning: Failed to hardlink files; falling back to full copy.
```

This is harmless. To suppress it, set `UV_LINK_MODE=copy` before running `prepare`:

```text
UV_LINK_MODE=copy ./appenv prepare
```

See [astral-sh/uv#6101](https://github.com/astral-sh/uv/issues/6101) for details.

### Tox Integration

appenv works well with tox for multi-version testing:

```toml
# tox.toml
[tool.tox]
env_list = ["3.11", "3.12", "3.13"]

[tool.tox.env_run_base]
commands = [["pytest"]]
```

## Managing Multiple Python Versions

```text
# Specify version constraint in pyproject.toml
[project]
requires-python = ">=3.11,<3.14"

# appenv will automatically select the best available version
./http --help
```

### UV Universal Resolution

See {doc}`locking-behavior` for details on how UV handles universal resolution across the entire `requires-python` range.

## Debugging Issues

### Verbose Mode

```text
APPENV_VERBOSE=1 ./http --version
```

Shows uv commands being executed, Python version selection, and venv creation steps. Without verbose mode, appenv suppresses uv output for a clean experience.

### Reset and Rebuild

```text
./appenv reset
./appenv prepare
```

### Python Version Selection

If the wrong Python version is selected, check:

1. **`requires-python`** in `pyproject.toml` — this is the constraint
2. **PATH** — appenv scans `python3.X` binaries newest-first
3. **APPENV_BEST_PYTHON** — set by appenv after selection, check with `verbose` mode

Override selection:

```text
# Force a specific Python (set before running)
APPENV_BEST_PYTHON=/usr/bin/python3.12 ./mkdocs build

# Or use the full path in your shell
/path/to/python3.12 -m venv .venv
```

Run with `APPENV_VERBOSE=1` to see which Python is selected and why.

## Working with Extras

```text
# Define extras in pyproject.toml
[project.optional-dependencies]
dev = ["pytest", "ruff"]

# Install with extras
APPENV_EXTRAS=dev ./appenv prepare
```

## Updating appenv Itself

```text
# Download latest version
curl -sL https://raw.githubusercontent.com/flyingcircusio/appenv/master/src/appenv.py -o appenv
chmod +x appenv
```
