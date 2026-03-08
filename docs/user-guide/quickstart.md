# Quick Start

Get started with appenv in minutes.

## Creating a New Project

### Interactive Setup

```bash
# Create and enter project directory
mkdir httpie && cd httpie

# Run bootstrap
curl -sL https://github.com/flyingcircusio/appenv/raw/master/bootstrap | sh
```

The bootstrap script will prompt for:

```
What should the command be named? [app] http
Enter dependencies (one per line, empty line to finish):
  Default: http
  Dependency: httpie
  Dependency: 
Project name [http-app]: http
Description []: HTTP CLI
Minimum Python version [3.10]: 3.13
```

### Generated Files

```
httpie/
├── pyproject.toml    # Project configuration
├── uv.lock           # Dependency lockfile
├── appenv            # Bootstrap script
└── http              # Entry point symlink
```

## Running Your Application

```bash
# First run - installs dependencies automatically
./http GET https://httpbin.org/get

# Subsequent runs are instant
./http GET https://httpbin.org/get
```

## Python Version Selection

appenv automatically selects the best Python version based on `requires-python` in `pyproject.toml`:

```toml
[project]
name = "myapp"
requires-python = ">=3.11,<3.14"
```

appenv will:
1. Find all Python versions in PATH
2. Select the newest one matching the constraint
3. Re-exec itself with that Python

## Updating Dependencies

```bash
# Update the lockfile
./appenv update-lockfile

# See changes before applying
./appenv update-lockfile --diff
```

## Development Mode

Install dev dependencies for development:

```bash
# Create venv with dev dependencies
./appenv develop

# Run tests
./appenv run pytest
```

## Common Commands

| Command | Description |
|---------|-------------|
| `./appenv prepare` | Create venv with production deps |
| `./appenv develop` | Create venv with dev deps |
| `./appenv update-lockfile` | Update uv.lock |
| `./appenv reset` | Remove virtual environment |
| `./appenv python` | Start Python REPL |
| `./appenv run <script>` | Run script from venv/bin |

## Environment Variables

| Variable | Description |
|----------|-------------|
| `APPENV_VERBOSE=1` | Show verbose output |
| `APPENV_EXTRAS` | Extras to install (comma-separated) |
| `APPENV_PROFILE=1` | Enable profiling |
| `APPENV_BASEDIR` | Project base directory |

## Next Steps

- {doc}`commands` - Full command reference
- {doc}`workflows` - Common workflow patterns
