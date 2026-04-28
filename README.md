# appenv

appenv pins Python packages to exact versions and exposes their binaries
via symlinks — one file, no installation step. Drop it into a repository,
commit it, and every checkout (local or remote) gets the same tools at the
same versions by running `./http`, `./mkdocs`, `./batou`, or whatever you need.

## Quick Start

Drop appenv into a repository:

```bash
cd myproject
curl -sL https://raw.githubusercontent.com/flyingcircusio/appenv/master/src/appenv.py -o appenv
chmod +x appenv
```

Declare which tools you need:

```bash
$ ./appenv init
Let's create a new appenv project in /tmp/myproject
I'll ask a few questions, then create pyproject.toml here

Binary to expose (creates ./<name> symlink) [app] http
Enter dependencies (one per line, empty line to finish):
  Default: http
  Dependency: httpie
  Dependency:
Project name [myproject]:
Description []:
Minimum Python version [3.13]:
Created pyproject.toml
Generating new lock file ...
✓ Created (+42 lines)

=== Appenv project initialized ===

Use `./http` to set up environment and run

$ ./http GET https://httpbin.org/get
200
```

If appenv is published on PyPI, you can skip the download:

```bash
mkdir myproject && cd myproject
uvx appenv init
```

**What just happened?**

- `curl` downloaded a single file: `appenv`
- `init` created `pyproject.toml` and a symlink `http → appenv`
- `./http` set up the venv with pinned versions from `uv.lock`, then ran the `http` binary (from the httpie package)

The symlink name determines which installed binary gets executed.
Create additional symlinks to expose more binaries from your dependencies:

```bash
ln -s appenv ruff
./ruff check .
```

Plugin-based tools work the same way — just add plugins as dependencies:

```bash
./appenv uv add mkdocs-material
./mkdocs build   # theme is available immediately
```

For dev tools, `uv run` works transparently (uses the `.venv` symlink):

```bash
uv run pytest -xvs
```

The repository now contains:

```
myproject/
├── appenv          # The appenv script (single file, committed to git)
├── http -> appenv  # Runs the `http` binary from installed deps
├── pyproject.toml  # Project config and dependency list
└── uv.lock         # Exact versions of all dependencies (committed to git)
```

### Using an existing appenv project

Someone gave you a project that already uses appenv? Just run the command:

```bash
git clone <project> && cd <project>
./http    # First run sets up everything automatically
```

No `uv.lock` yet? Generate it:

```bash
./appenv update-lockfile
```

Only needed again after manually editing `pyproject.toml` — `uv add`/`uv remove`
update the lockfile automatically.

### Upgrading from requirements.txt

Still using `requirements.txt` instead of `pyproject.toml`?

```bash
uvx appenv migrate
```

## Documentation

Full documentation at [flyingcircusio.github.io/appenv](https://flyingcircusio.github.io/appenv/):

- [Installation](docs/user-guide/installation.md) -- how to get appenv
- [Commands Reference](docs/user-guide/commands.md) -- all commands with options
- [Workflows](docs/user-guide/workflows.md) -- common usage patterns
- [Locking Behavior](docs/user-guide/locking-behavior.md) -- how uv.lock works
- [Architecture](docs/dev-guide/architecture.md) -- internals and design
- [Contributing](docs/dev-guide/contributing.md) -- development setup

## Environment Variables

| Variable | Description |
|----------|-------------|
| `APPENV_VERBOSE` | Show uv commands being executed |
| `APPENV_EXTRAS` | Comma-separated dependency groups to install |
| `APPENV_BASEDIR` | Auto-set to project root |
| `APPENV_BEST_PYTHON` | Selected Python interpreter |

## Requirements

- Python 3.9+ (managed environments require 3.10+)
- uv 0.5.0+ (auto-installed if not found)

## Testing

```bash
tox
```
