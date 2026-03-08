# Common Workflows

Practical workflows for using appenv.

## New Project from Scratch

```bash
# 1. Create project
mkdir myproject && cd myproject

# 2. Bootstrap
curl -sL https://github.com/flyingcircusio/appenv/raw/master/bootstrap | sh

# 3. Answer prompts
# Command: myapp
# Dependencies: requests, click
# Project name: myapp
# Description: My CLI app
# Python version: 3.11

# 4. Run
./myapp --help
```

## Migrate from requirements.txt

```bash
# 1. Ensure requirements.txt exists
cat requirements.txt
# requests>=2.28.0
# click>=8.0

# 2. Run migrate
./appenv migrate

# 3. Verify pyproject.toml
cat pyproject.toml

# 4. Update lockfile
./appenv update-lockfile

# 5. Test
./myapp --help

# 6. Remove old requirements.txt when done
rm requirements.txt
```

## Development Workflow

```bash
# 1. Setup dev environment
./appenv develop

# 2. Run tests
./appenv run pytest

# 3. Format code
./appenv run ruff format .

# 4. Type check
./appenv run ty check .

# 5. After adding dependencies
./appenv update-lockfile
./appenv develop  # Re-sync
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
        run: ./appenv run pytest
```

### Tox Integration

appenv works well with tox for multi-version testing:

```toml
# tox.toml
[tool.tox]
env_list = ["3.11", "3.12", "3.13"]

[tool.tox.env_run_base]
commands = [["pytest"]]
```

## Adding Dependencies

```bash
# Option 1: Edit pyproject.toml directly
vim pyproject.toml
./appenv update-lockfile

# Option 2: Use uv
./appenv uv add requests

# Option 3: Install temporarily
./appenv uv pip install requests
```

## Managing Multiple Python Versions

```bash
# Specify version constraint in pyproject.toml
[project]
requires-python = ">=3.11,<3.14"

# appenv will automatically select the best available version
./myapp --help

# Check which Python is being used
./appenv settings | grep BEST_PYTHON
```

## Debugging Issues

### Verbose Mode

```bash
APPENV_VERBOSE=1 ./mycommand args
```

Shows:
- uv commands being executed
- Python version selection
- venv creation steps

### Check Settings

```bash
./appenv settings
```

### Reset and Rebuild

```bash
./appenv reset
./appenv prepare
```

## Profiling Performance

```bash
# Enable profiling
APPENV_PROFILE=1 ./mycommand args

# View results
./appenv profiling list
./appenv profiling show

# Interactive visualization
./appenv profiling snakeviz
```

## Working with Extras

```bash
# Define extras in pyproject.toml
[project.optional-dependencies]
dev = ["pytest", "ruff"]

# Install with extras
APPENV_EXTRAS=dev ./appenv prepare
```

## Updating appenv Itself

```bash
# Download latest version
curl -sL https://github.com/flyingcircusio/appenv/raw/master/src/appenv.py -o appenv
chmod +x appenv
```
