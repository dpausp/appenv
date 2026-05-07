# appenv

appenv pins Python packages to exact versions and exposes their binaries
via symlinks — one file, no installation step. Drop it into a repository,
commit it, and every checkout (local or remote) gets the same tools at the
same versions by running `./http`, `./mkdocs`, `./batou`, or whatever you need.

**appenv never modifies your system** — all state lives in `.appenv/` inside
the project directory. Remove that folder and nothing is left behind.

## Using an existing appenv project

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

## New Project

appenv is distributed as a standalone script. Just use uvx or download it yourself.
`appenv init` will ask you some questions and set up the project. The example
assumes that you want to run a binary called `http` from the `httpie` package.

### uvx (uv)

`uvx` is part of [uv](https://docs.astral.sh/uv/) — the easiest way to start:

```bash
uvx appenv init
```

### Manual Download

No uv installed? Download appenv directly:

```bash
curl -sL https://raw.githubusercontent.com/flyingcircusio/appenv/master/src/appenv.py -o appenv
chmod +x appenv
./appenv init
```

**What just happened?**

- appenv installed itself inplace by adding the `./appenv` script.
- `init` created `pyproject.toml` and a symlink `http → appenv`.
- `./http` set up the venv with pinned versions from `uv.lock`, then ran the `http` binary (from the httpie package)


The repository now contains:

```
myproject/
├── appenv          # The appenv script (single file, committed to git)
├── http -> appenv  # Runs the `http` binary from installed deps
├── pyproject.toml  # Project config and dependency list
└── uv.lock         # Exact versions of all dependencies (committed to git)
```

### Development

For dev tooling, `uv run` works transparently (uses the `.venv` symlink):

```bash
uv run pytest -xvs
```

## Documentation

Full documentation at [Readthedocs](https://appenv.readthedocs.io):

- [Installation](docs/user/installation.md) -- how to get appenv
- [Commands Reference](docs/user/commands.md) -- all commands with options
- [Workflows](docs/user/workflows.md) -- common usage patterns
- [Locking Behavior](docs/user/locking-behavior.md) -- how uv.lock works
- [Architecture](docs/dev/architecture.md) -- internals and design
- [Contributing](docs/dev/contributing.md) -- development setup

## Environment Variables

| Variable | Description |
|----------|-------------|
| `APPENV_VERBOSE` | Show uv commands being executed |
| `APPENV_EXTRAS` | Comma-separated dependency groups to install |
| `APPENV_BASEDIR` | Auto-set to project root |
| `APPENV_BEST_PYTHON` | Selected Python interpreter |

## Requirements

- Python 3.9+ for the appenv script (environments managed by appenv require 3.10+)
- uv 0.5.0+ (auto-installed if not found)


## Appenv Development

XXX note: applies to development of appenv itself, not projects managed by appenv!

Sync dev dependencies:

```commandline
uv sync
```

Run tests and linter:

```bash
uv run tox
```
