# Common Workflows

Practical workflows for using appenv.

## Understanding UV Locking and Command Behavior

Before diving into specific workflows, it's essential to understand how appenv interacts with UV's locking mechanism, as this affects which commands to use when.

See {doc}`locking-behavior` for detailed documentation on:
- How UV locking works (deterministic lockfiles)
- Three sync modes (none, --frozen, --locked)
- appenv command mapping
- Handling missing lockfiles

## New Project from Scratch

```text
# 1. Create project
mkdir myproject && cd myproject

# 2. Bootstrap
curl -sL https://github.com/flyingcircusio/appenv/raw/master/bootstrap | sh

# 3. Answer prompts
# Command: myapp
# Dependencies: requests, click
# Project name: myapp
# Description: My CLI app
# Python version: 3.14

# 4. Run
./myapp --help
```

### Detailed Bootstrap Example

For a more detailed view of what happens during bootstrapping:

```text
$ mkdir httpie && cd httpie
$ curl -sL https://github.com/flyingcircusio/appenv/raw/master/bootstrap | sh
Let's create a new pyproject.toml project.

What should the command be named? [app] http
Enter dependencies (one per line, empty line to finish):
  Default: http
  Dependency: httpie
  Dependency: 
Project name [http-app]: http
Description []: HTTP CLI
Minimum Python version [3.10]: 3.14

Created pyproject.toml
Created http symlink

Done. pyproject.toml created.

Generating lockfile ...
✓ Created (+273 lines)

Run `./http` to bootstrap and run

$ ./http
Installing httpie ...
http: warning: command-line flag syntax is deprecated
```

## Migrate from requirements.txt

```text
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

### Detailed Migration Example

```text
$ ./appenv migrate
Migrating from requirements.txt to pyproject.toml...

Found 3 dependency(ies): requests, click, rich
warning: 1 editable install(s) skipped:
  -e ./lib

Created pyproject.toml
```

### Post-Migration Steps

After running `migrate`, you should:
1. Review the generated `pyproject.toml`
2. Run `./appenv update-lockfile` to create the lockfile
3. Test your application
4. Remove the old `requirements.txt` when satisfied

## Development Workflow

```text
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

### Detailed Dependency Management

When working with dependencies, understanding the different workflows is crucial:

#### Adding Dependencies

```text
# Add a production dependency (updates both pyproject.toml and uv.lock)
$ ./appenv uv add requests
Resolved 5 packages in 12ms
Prepared 1 package in 45ms
Installed 1 package in 23ms
  + requests==2.32.3

# What changed in pyproject.toml:
# Before: dependencies = ["httpie>=3.0.0"]
# After:  dependencies = [
#           "httpie>=3.0.0",
#           "requests>=2.32.3",
#         ]

# Add a development dependency
$ ./appenv uv add --group dev pytest
Resolved 3 packages in 89ms
Prepared 2 packages in 141ms
Installed 2 packages in 72ms
  + pluggy==1.4.0
  + pytest==8.2.0
```

#### Upgrading Packages

```text
# Upgrade a specific package (within version constraints)
$ ./appenv uv lock --upgrade-package requests
Resolved 1 packages in 23ms
...
  + requests==2.32.3

# Upgrade all packages (within version constraints)
$ ./appenv uv lock --upgrade
Resolved 15 packages in 45ms
...
  + requests==2.32.3
  + click==8.1.7
  # ... etc
```

#### Freezing Dependencies for Repeatable Builds

```text
# Create/update lockfile for reproducible installs
$ ./appenv update-lockfile
✓ Created (+42 lines)

# First run after creating lockfile - installs dependencies
$ time ./http GET https://httpbin.org/get
Installing httpie ...
./http GET https://httpbin.org/get  2.91s user 0.99s system 88% cpu 4.407 total

# Subsequent runs - uses cached dependencies
$ time ./http GET https://httpbin.org/get
./http GET https://httpbin.org/get  0.22s user 0.11s system 90% cpu 0.371 total
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

```text
# Option 1: Edit pyproject.toml directly
vim pyproject.toml
./appenv update-lockfile

# Option 2: Use uv (recommended - updates both files)
./appenv uv add requests

# Option 3: Install temporarily (doesn't update pyproject.toml or uv.lock)
./appenv uv pip install requests
```

## Managing Multiple Python Versions

```text
# Specify version constraint in pyproject.toml
[project]
requires-python = ">=3.11,<3.14"

# appenv will automatically select the best available version
./myapp --help

# Check which Python is being used
./appenv settings | grep BEST_PYTHON
```

### UV Universal Resolution

See {doc}`locking-behavior` for details on how UV handles universal resolution across the entire `requires-python` range.

## Debugging Issues

### Verbose Mode

```text
APPENV_VERBOSE=1 ./mycommand args
```

Shows:
- uv commands being executed
- Python version selection
- venv creation steps

#### Verbose Mode Example

By default, appenv suppresses uv command output for a clean user experience.
With `APPENV_VERBOSE=1`, you can see exactly what uv commands are being executed:

```text
$ ./http GET https://example.org
# (silent - just the HTTP response)

$ APPENV_VERBOSE=1 ./http GET https://example.org
Running: /path/to/uv venv --python /usr/bin/python3.11 .appenv/venv
Running: /path/to/uv sync --no-dev --frozen
# ... HTTP response follows
```

### Check Settings

```text
./appenv settings
```

Shows environment variables, Python interpreter, and venv location.

### Reset and Rebuild

```text
./appenv reset
./appenv prepare
```

## Profiling Performance

```text
# Enable profiling
APPENV_PROFILE=1 ./mycommand args

# View results
./appenv profiling list
./appenv profiling show

# Interactive visualization
./appenv profiling snakeviz
```

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
curl -sL https://github.com/flyingcircusio/appenv/raw/master/src/appenv.py -o appenv
chmod +x appenv
```
