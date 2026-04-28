# appenv

appenv is a single Python file that pins packages to exact versions and exposes
their binaries via symlinks. Drop it into a repository, commit it, and every
checkout gets the same tools at the same versions — locally and on remote machines.

No venv activation, no pip, no Python packaging knowledge required.

## Quick Start

```bash
mkdir myproject && cd myproject
curl -sL https://raw.githubusercontent.com/flyingcircusio/appenv/master/src/appenv.py -o appenv
chmod +x appenv
./appenv init
```

The init command walks you through project setup:

```
Let's create a new appenv project in /home/user/myproject
I'll ask a few questions, then create pyproject.toml here

Binary to expose (creates ./<name> symlink) [app] http

Enter dependencies (one per line, empty line to finish):
  Default: http
  Dependency: httpie
  Dependency:

Project name [myproject]:
Description []: My HTTP client
Minimum Python version [3.13]:
Created pyproject.toml
Generating new lock file ...

=== Appenv project initialized ===

Use `./http` to run the http binary
```

Run the exposed binary:

```bash
./http GET https://httpbin.org/get
```

## Core Concepts

- **Single-file deployment**: `appenv.py` is the entire tool — drop it into any repository
- **Symlink dispatch**: `./http` (where `http → appenv`) runs the `http` binary from the pinned venv
- **Reproducible everywhere**: commit `appenv`, `pyproject.toml`, and `uv.lock` — every checkout gets identical versions
- **Multiple binaries**: create additional symlinks to expose more tools from the same venv

## Project Structure

```
.
├── appenv              # Main application entrypoint
├── pyproject.toml      # Project configuration and dependencies
├── docs/               # Documentation
│   ├── index.md
│   ├── user-guide/
│   └── dev-guide/
├── src/                # Source code
│   └── appenv.py
└── tests/              # Test suite
```

## Conventions

- appenv runs on Python 3.9+. Managed environments require Python 3.10+.
- [uv](https://docs.astral.sh/uv/) must be available on the system (see {doc}`user-guide/installation`)
- The appenv filename becomes the CLI command via symlink dispatch — `./http` where `http → appenv`
- `pyproject.toml` must be present next to the appenv file
- Dependencies are resolved and locked by uv into `uv.lock`

```{toctree}
:hidden:
user-guide/installation
user-guide/commands
user-guide/workflows
user-guide/locking-behavior
dev-guide/architecture
dev-guide/contributing
```
