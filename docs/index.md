# appenv

appenv is a single Python file that pins packages to exact versions and exposes
their binaries via symlinks. Drop it into a repository, commit it, and every
checkout gets the same tools at the same versions — locally and on remote machines.


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
│   ├── user/
│   └── dev/
├── src/                # Source code
│   └── appenv.py
└── tests/              # Test suite
```

## Conventions

- The appenv script requires Python 3.9+, managed environments require 3.10+.
- [uv](https://docs.astral.sh/uv/) 0.5.0+ is auto-installed if not found.
- The appenv filename becomes the CLI command via symlink dispatch — `./http` where `http → appenv`
- `pyproject.toml` must be present next to the appenv file
- Dependencies are resolved and locked by uv into `uv.lock`

## Getting Started

New to appenv? Start with the {doc}`user/workflows` — practical examples for setting up
a project, adding dependencies, and integrating with CI/CD.

For reference material, see {doc}`user/commands` and {doc}`user/locking-behavior`.

```{toctree}
:hidden:
user/index
dev/index
```
