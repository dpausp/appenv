# Developer Guide

How appenv works internally and how to contribute.

## Architecture

How appenv's components fit together and why.

### Design Philosophy

appenv is a single-file Python CLI that pins packages to exact versions and exposes their binaries via symlinks, using [uv](https://docs.astral.sh/uv/) for environment management. The single-file constraint is deliberate: appenv gets copied into project repositories as a self-contained bootstrap script with zero runtime dependencies. Commit it alongside `pyproject.toml` and `uv.lock`, and every checkout — local or on a remote deployment target — gets the same tools at the same versions by running `./http` or `./batou`.

This shapes every architectural decision:

- **Zero system modification**: appenv never installs anything outside the project directory. All state lives in `.appenv/` — venv, cached uv binary, logs. No system packages, no global bin directories, no PATH modifications. Drop the script, remove `.appenv/`, and the system is unchanged.
- **Symlink dispatch**: When invoked as `./http` (a symlink to `appenv`), it prepares the venv and runs `.appenv/venv/bin/http`. When invoked as `./appenv`, it parses subcommands via argparse. The script detects its own filename (`Path(__file__).stem`) to choose the mode. Multiple symlinks can coexist to expose different binaries from the same venv.
- **Type hints in stubs only**: Implementation lives in `appenv.py` with minimal typing. Complete type annotations (public and private methods) live in `appenv.pyi`. Any signature change must update both files. See [](#type-annotations) for the full policy.
- **Guard-then-act pattern**: `ensure_*` functions validate preconditions and exit with specific error codes if unsatisfied. The main flow only proceeds after all guards pass.

### Command Dispatch

The entry point `main()` does three things:

1. **Clear PYTHONPATH** — prevents host environment contamination in the venv
2. **Select best Python** via `ensure_best_python()` (see [](#python-version-selection))
3. **Dispatch based on filename**:
   - Filename is `appenv` → `meta()` (argparse subcommand handling)
   - Filename is anything else → `run()` (exec the venv binary)

#### Run Mode

`./http arg1 arg2` → appenv prepares the venv, then `os.execv()` replaces the current process with `.appenv/venv/bin/http arg1 arg2`. The original Python process is gone — no wrapper, no subprocess overhead.

#### Meta Mode

`./appenv <subcommand>` → argparse dispatches to handler methods grouped by category (Project, Venv, Tools, Debug). Subcommands are defined in `AppEnv.meta()` with `func` defaults pointing to handler methods.

### Python Version Selection

(python-version-selection)=

`ensure_best_python()` runs before any other setup. It reads `requires-python` from `pyproject.toml`, scans PATH for `python3.X` binaries (newest first), and re-execs with the best match via `os.execv()`. A guard (`APPENV_BEST_PYTHON` env var) prevents infinite re-exec loops.

**Base directory**: `APPENV_BASEDIR` overrides the project location. By default, appenv uses `Path(__file__).parent` — meaning appenv must be located next to `pyproject.toml`. This is intentional: the bootstrap script lives beside the project it manages.

If no compatible Python is found, it lists available versions and exits with `EXIT_CODE_DATAERR` (65).

Each candidate is probed by running `python -c "print(1)"` to verify the binary actually works — important on systems like NixOS where symlink targets may have been garbage-collected.

### uv Management

#### Discovery Chain

`UvBin` discovers the `uv` binary through a six-step cascade. Each step validates the version before accepting — see `UvVersion.minimum()` in the API reference for the current minimum:

1. **PATH** — `shutil.which("uv")`, validate version
2. **Cached binary** — `.appenv/.uv/bin/uv` from a previous nix/pip install
3. **Nix channel** — `nix-build <nixpkgs> -A uv` into `.appenv/.uv`
4. **Nix flake** — `nix build nixpkgs#uv` into `.appenv/.uv` (more expensive, fresher packages)
5. **pip install** — `pip install uv -t .appenv/.uv` as last resort
6. **Direct download** — download the uv binary tarball from [astral-sh/uv GitHub releases](https://github.com/astral-sh/uv/releases) via `urllib` + `tarfile` (stdlib only), extract to `.appenv/.uv/bin/uv`. See [](#platform-detection) for supported platforms.

When a PATH uv is valid, any previously cached `.appenv/.uv` is cleaned up automatically. The cascade handles environments where uv may not be pre-installed (CI, NixOS, minimal containers).

#### Platform Detection

(platform-detection)=

The direct-download step (6) needs to know the correct release archive for the current platform. `_uv_platform_triple()` in `src/appenv.py` maps `platform.machine()` and `sys.platform` to the archive naming convention used by astral-sh/uv:

| Architecture | Linux (glibc) | Linux (musl/Alpine) | macOS |
| ------------ | -------------------------- | -------------------------- | --------------------- |
| x86_64 | `x86_64-unknown-linux-gnu` | `x86_64-unknown-linux-musl` | `x86_64-apple-darwin` |
| aarch64 | `aarch64-unknown-linux-gnu` | `aarch64-unknown-linux-musl` | `aarch64-apple-darwin` |
| armv7 | `armv7-unknown-linux-gnu` | `armv7-unknown-linux-musl` | — |

Linux glibc vs. musl is detected by checking for `/etc/alpine-release` (Alpine uses musl). Unsupported platforms (unrecognized architecture or OS) cause the direct-download step to be skipped silently.

#### Version Enforcement

`ensure_uv()` wraps `UvBin` construction and exits with `EXIT_CODE_UNAVAILABLE` (68) if the discovered binary doesn't meet the minimum version. This guard runs before any venv operations.

### Venv Lifecycle

The venv lives at `.appenv/venv` — a real virtual environment managed by uv. `.venv` is a symlink to `.appenv/venv` for IDE and tool compatibility (editors, linters, debuggers that expect `.venv` by convention).

#### Creation

`_prepare_venv()` handles the full lifecycle:

1. Run guards: `ensure_pyproject()`, `ensure_lock_file()`, `ensure_uv()`
2. Set `UV_PROJECT_ENVIRONMENT` to `.appenv/venv` so uv targets the right directory
3. **Corruption recovery**: if `.appenv/venv` exists but `bin/python` is missing (NixOS garbage collection), the venv is removed and recreated
4. **Stale version recovery**: if the venv's Python version doesn't satisfy `requires-python` (e.g., after a constraint change), the venv is removed and recreated with a one-line message to stdout
5. Create venv with `uv venv --python <current_python>` — explicitly uses the current Python to prevent uv from downloading its own (which breaks on NixOS)
6. Sync dependencies via `uv sync`
7. Update `.venv` symlink (removed and recreated if stale)

#### Sync Modes

- **Production** (`prepare`, symlink dispatch): `uv sync --no-dev --frozen` — only production dependencies, lockfile must exist and be unchanged. The symlink dispatch (`./http`) is equivalent to `prepare` followed by `os.execv`.
- **Run** (`run`): Delegates directly to `uv run` with appenv's configured environment. Does not enforce frozen — uv run handles its own sync.

### Project Layout Conventions

appenv expects specific files relative to the project root. Paths are conventions, not configuration:

`pyproject.toml`
: Project definition with `[project]` section and `requires-python`. Required for all operations.

`uv.lock`
: Dependency lockfile created by `./appenv update-lockfile`. Required before `prepare`.

`appenv`
: The bootstrap script — a copy of `src/appenv.py`. `migrate` updates this file when the running appenv version differs from the one on disk. `init` warns when a version mismatch is detected.

`<command>`
: Symlink to `appenv`. Running `./<command>` executes the `<command>` binary from the installed dependencies. Multiple symlinks can expose different binaries from the same venv.

`.appenv/`
: Internal state directory (venv, cached uv binary, logs). Managed entirely by appenv.

`.venv`
: Symlink to `.appenv/venv`. Created for tool compatibility — do not delete manually.

### Error Handling Strategy

appenv uses BSD sysexits.h exit codes to communicate specific failure modes:

**64 (USAGE)**
: Incorrect command usage — deprecated subcommand invoked or invalid arguments.

**65 (DATAERR)**
: Input data is malformed — missing `[project]` section in `pyproject.toml`, no compatible Python found.

**67 (NOINPUT)**
: Required file missing — no `pyproject.toml`, no `uv.lock`.

**68 (UNAVAILABLE)**
: Required tool unavailable — uv not found or too old.

The `cmd()` subprocess wrapper converts `CalledProcessError` to `ValueError` with captured output, giving calling code both the exit code and full stderr/stdout for error reporting.

### Logging Architecture

Each command gets its own log file at `.appenv/logs/<command>.log`. Logs use `TimedRotatingFileHandler` with daily rotation and 7-day retention.

Verbose mode (`APPENV_VERBOSE=1`) adds a console handler with dimmed caller info (`funcName:lineno`) prepended to each message. Useful during development without cluttering normal output.

The logger is a module-level `logging.getLogger("appenv")` singleton, configured per-command by `setup_logging()`. All components use it for structured debug output.

## Contributing

How to set up a development environment and submit changes.

### Development Setup

```console
git clone https://github.com/flyingcircusio/appenv.git
cd appenv
```

Run tests:

```console
uv run pytest
```

All CI checks (lint, format, type-check, test) run via:

```console
tox
```

### Code Style

appenv follows the style defined in `pyproject.toml` under `[tool.ruff]`. Run `uv run ruff check --fix .` and `uv run ruff format .` to apply.

#### Type Annotations

(type-annotations)=

Type annotations live in `.pyi` stub files, not in `.py` source files. The `src/appenv.pyi` stub is the complete type surface — it must include all public *and* private methods. Ruff's `ANN` rules are dropped because they ignore `.pyi` files entirely.

Any method signature change requires updating both `src/appenv.py` and `src/appenv.pyi`. Validate with `uv run ruff check --select PYI src/appenv.pyi`.

The `src/py.typed` marker file signals PEP 561 compliance to type checkers.

Test files follow the same stub-only policy — every `.py` in `tests/` has a matching `.pyi`. See [](#test-type-stubs) for patterns and fixture types.

#### Exit Codes

Use BSD sysexits.h constants (`EXIT_CODE_DATAERR`, `EXIT_CODE_NOINPUT`, `EXIT_CODE_UNAVAILABLE`) defined at module level. See [](#error-handling-strategy) for the full error handling strategy.

#### Spec Comments

Non-trivial error handling uses `# SPEC:` comments to trace requirements:

```python
# SPEC: SRS-F001-cmd-wrapper - Enrich subprocess errors with command output context
try:
    result = subprocess.check_output(cmd_list, stderr=subprocess.STDOUT)
except subprocess.CalledProcessError as e:
    raise ValueError(e.output.decode("utf-8", "replace")) from e
```

### Running Tests

```console
# All tests (excludes slow by default)
uv run pytest

# Specific file
uv run pytest tests/test_prepare.py

# With coverage report
uv run pytest --cov=appenv --cov-report=term-missing

# Include slow tests
uv run pytest -m ''
```

#### Two-Tier Model

appenv has no natural seam for an integration tier — `uv` is either mocked (unit) or real (E2E). Tests fall into exactly two tiers:

**Unit tests** (`tests/test_*.py`)
: Mock `uv` via `MockUvBin`. Fast, no external dependencies. Covers logic branches, error handling, and argument construction.

**E2E tests** (`tests/integration/`)
: Real `uv`, real subprocess via `pexpect`. Exercises the full bootstrap workflow end-to-end. Requires `uv` installed on the system.

The standard 70/20/10 pyramid model does not apply — test expansion beyond unit coverage is E2E-only.

#### Slow Marker

Any test consistently exceeding 2 seconds gets `@pytest.mark.slow`. The threshold is objective: measure new tests and apply the marker if they cross it.

- Default `pytest` configuration excludes slow tests (`-m "not slow"`)
- `tox` cov environment runs all tests including slow
- E2E tests should target under 2s to avoid needing the marker

(test-type-stubs)=
#### Test Type Stubs

Test stubs live alongside their `.py` files in `tests/`. Every test function, helper, and class has a corresponding stub entry. Markers (`@pytest.mark.slow`, `@pytest.mark.parametrize(...)`) are preserved in stubs.

**Signature patterns:**

```python
def test_example(monkeypatch: MonkeyPatch, tmp_path: Path) -> None: ...
def helper(verbose: bool = ...) -> None: ...
```

**Builtin pytest fixture types:**

| Fixture | Type |
|---------|------|
| `monkeypatch` | `MonkeyPatch` |
| `capsys` | `CaptureFixture[str]` |
| `tmp_path` | `Path` |
| `request` | `FixtureRequest` |
| `caplog` | `LogCaptureFixture` |

**Project fixture types** (from `tests/conftest.pyi`):

| Fixture | Return type |
|---------|-------------|
| `workdir` | `Path` |
| `mock_uv` | `MockUvBin` |
| `mock_uv_version` | `None` |
| `subprocess_run_fail` | `None` |
| `app_env` | `Callable[..., AppEnv]` |
| `make_mock_uv` | `Callable[..., MockUvBin]` |
| `no_ensure_python` | `None` |
| `mock_cmd_python` | `None` |
| `create_venv` | `Callable[..., Path]` |
| `mock_uv_lock` | `None` |
| `mock_logdir` | `Path` |
| `clean_uv_project_env` | `None` |
| `make_pyproject` | `Callable[..., None]` |
| `capture_appenv_logs` | `logging.Logger` |
| `test_settings` | `Callable[..., AppEnvSettings]` |
| `patterns` | pytest-patterns plugin type |

**Validation:**

```console
uv run ruff check --select PYI tests/
uv run ty check tests/
```

Stubs must stay in sync with their `.py` counterparts — any signature change updates both files. Ty runs on `src/` only in CI; test stub validation is manual until a follow-up enables it.

#### Test Strategy

- **Existing code with gaps**: write tests first (tests-after) to cover uncovered paths
- **New features with code changes**: write tests alongside or before implementation
- **Existing features with no code changes** (e.g., untested subcommands): write E2E tests first (E2E-first) since the feature already works

### Quality Gates

All of these must pass before submitting a PR:

| Gate | Command | What it checks |
|------|---------|----------------|
| Lint | `uv run ruff check .` | Code quality rules |
| Format | `uv run ruff format --check .` | Formatting consistency |
| Types | `uv run ty check .` | Type correctness via `.pyi` stubs |
| Dead code | `uv run vulture .` | Unused code detection |
| Tests | `uv run pytest` | All tests pass |
| Full CI | `tox` | All environments (fix, cov, multiple Python versions) |

Pre-commit hooks run these automatically.

### Documentation

Docs are built with Sphinx using MyST markdown and autoapi:

```console
tox -e docs
```

- **User docs**: `docs/user/` — usage and workflows
- **Dev docs**: `docs/dev/` — this guide
- **API reference**: auto-generated from source by autoapi — do not write API docs by hand

### Pull Request Process

1. Fork and create a feature branch
2. Make changes with accompanying tests
3. Run `tox` — all environments must pass
4. Update documentation if behavior changed
5. Submit pull request

**PR checklist:**

- [ ] `tox` passes cleanly
- [ ] New behavior has tests
- [ ] Documentation updated if applicable
- [ ] No `# noqa` without justification
