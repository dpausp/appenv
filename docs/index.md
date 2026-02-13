# appenv

Self-contained bootstrapping and updating of Python CLI applications using
[pyproject.toml](https://packaging.python.org/en/latest/specifications/pyproject-toml/)
and [uv](https://docs.astral.sh/uv/).

```{note}
This documentation is auto-generated with test-coverage-driven priority.
**Test coverage: 91%** - Full documentation tier.
```

## Quick Start

### Bootstrapping a New Project

```bash
# Create a new project directory
mkdir myproject && cd myproject

# Download and run the bootstrap script
curl -sL https://github.com/flyingcircusio/appenv/raw/master/bootstrap | sh
```

The bootstrap script will guide you through:

1. Choosing a command name
2. Adding dependencies
3. Setting Python version requirements

### Project Structure

```
myproject/
├── pyproject.toml    # Dependencies and metadata
├── uv.lock           # Lockfile (generated)
├── appenv            # Bootstrap script
├── mycommand         # Symlink to appenv (entry point)
└── .appenv/
    └── venv/         # Virtual environment
```

## User Guide

```{toctree}
:maxdepth: 2
:caption: User Guide

user-guide/installation
user-guide/quickstart
user-guide/locking-behavior
user-guide/commands
user-guide/workflows
```

## API Reference

```{toctree}
:maxdepth: 2
:caption: API Reference

autoapi/src/appenv/index
```

## Developer Guide

```{toctree}
:maxdepth: 2
:caption: Developer Guide

dev-guide/architecture
dev-guide/contributing
```

## Indices

- {ref}`genindex`
- {ref}`modindex`
- {ref}`search`
