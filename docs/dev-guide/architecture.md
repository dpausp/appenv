# Architecture

How appenv's components fit together and why.

## Design Philosophy

appenv is a single-file Python CLI that pins packages to exact versions and exposes their binaries via symlinks, using [uv](https://docs.astral.sh/uv/) for environment management. The single-file constraint is deliberate: appenv gets copied into project repositories as a self-contained bootstrap script with zero runtime dependencies. Commit it alongside `pyproject.toml` and `uv.lock`, and every checkout — local or on a remote deployment target — gets the same tools at the same versions by running `./http` or `./batou`.

This shapes every architectural decision:

- **Symlink dispatch**: When invoked as `./http` (a symlink to `appenv`), it prepares the venv and runs `.appenv/venv/bin/http`. When invoked as `./appenv`, it parses subcommands via argparse. The script detects its own filename (`Path(__file__).stem`) to choose the mode. Multiple symlinks can coexist to expose different binaries from the same venv.
- **Type hints inline and stubs**: Implementation lives in `appenv.py` with type annotations. Type hints are provided both inline in appenv.py and as PEP 561 type stubs (appenv.pyi). The stubs enable type checking for downstream consumers without importing the module.
- **Guard-then-act pattern**: `ensure_*` functions validate preconditions and exit with specific error codes if unsatisfied. The main flow only proceeds after all guards pass.

## Command Dispatch

The entry point `main()` does three things:

1. **Clear PYTHONPATH** — prevents host environment contamination in the venv
2. **Select best Python** via `ensure_best_python()` (see [](#python-version-selection))
3. **Dispatch based on filename**:
   - Filename is `appenv` → `meta()` (argparse subcommand handling)
   - Filename is anything else → `run()` (exec the venv binary)

### Run Mode

`./http arg1 arg2` → appenv prepares the venv, then `os.execv()` replaces the current process with `.appenv/venv/bin/http arg1 arg2`. The original Python process is gone — no wrapper, no subprocess overhead.

### Meta Mode

`./appenv <subcommand>` → argparse dispatches to handler methods grouped by category (Project, Venv, Tools, Debug). Subcommands are defined in `AppEnv.meta()` with `func` defaults pointing to handler methods.

## Python Version Selection

(architecture-python-version-selection)=

`ensure_best_python()` runs before any other setup. It reads `requires-python` from `pyproject.toml`, scans PATH for `python3.X` binaries (newest first), and re-execs with the best match via `os.execv()`. A guard (`APPENV_BEST_PYTHON` env var) prevents infinite re-exec loops.

**Base directory**: `APPENV_BASEDIR` overrides the project location. By default, appenv uses `Path(__file__).parent` — meaning appenv must be located next to `pyproject.toml`. This is intentional: the bootstrap script lives beside the project it manages.

If no compatible Python is found, it lists available versions and exits with `EXIT_CODE_DATAERR` (65).

Each candidate is probed by running `python -c "print(1)"` to verify the binary actually works — important on systems like NixOS where symlink targets may have been garbage-collected.

## uv Management

### Discovery Chain

`UvBin` discovers the `uv` binary through a five-step cascade. Each step validates the version before accepting — see `UvVersion.minimum()` in the API reference for the current minimum:

1. **PATH** — `shutil.which("uv")`, validate version
2. **Cached binary** — `.appenv/.uv/bin/uv` from a previous nix/pip install
3. **Nix channel** — `nix-build <nixpkgs> -A uv` into `.appenv/.uv`
4. **Nix flake** — `nix build nixpkgs#uv` into `.appenv/.uv` (more expensive, fresher packages)
5. **pip install** — `pip install uv -t .appenv/.uv` as last resort

When a PATH uv is valid, any previously cached `.appenv/.uv` is cleaned up automatically. The cascade handles environments where uv may not be pre-installed (CI, NixOS, minimal containers).

### Version Enforcement

`ensure_uv()` wraps `UvBin` construction and exits with `EXIT_CODE_UNAVAILABLE` (68) if the discovered binary doesn't meet the minimum version. This guard runs before any venv operations.

## Venv Lifecycle

The venv lives at `.appenv/venv` — a real virtual environment managed by uv. `.venv` is a symlink to `.appenv/venv` for IDE and tool compatibility (editors, linters, debuggers that expect `.venv` by convention).

### Creation

`_prepare_venv()` handles the full lifecycle:

1. Run guards: `ensure_pyproject()`, `ensure_lock_file()`, `ensure_uv()`
2. Set `UV_PROJECT_ENVIRONMENT` to `.appenv/venv` so uv targets the right directory
3. **Corruption recovery**: if `.appenv/venv` exists but `bin/python` is missing (NixOS garbage collection), the venv is removed and recreated
4. Create venv with `uv venv --python <current_python>` — explicitly uses the current Python to prevent uv from downloading its own (which breaks on NixOS)
5. Sync dependencies via `uv sync`
6. Update `.venv` symlink (removed and recreated if stale)

### Sync Modes

- **Production** (`run`, `prepare`, symlink dispatch): `uv sync --no-dev --frozen` — only production dependencies, lockfile must exist and be unchanged. The symlink dispatch (`./http`) is equivalent to `prepare` followed by `os.execv`.

## Project Layout Conventions

appenv expects specific files relative to the project root. Paths are conventions, not configuration:

`pyproject.toml`
: Project definition with `[project]` section and `requires-python`. Required for all operations.

`uv.lock`
: Dependency lockfile created by `./appenv update-lockfile`. Required before `run` or `prepare`.

`appenv`
: The bootstrap script — a copy of `src/appenv.py`.

`<command>`
: Symlink to `appenv`. Running `./<command>` executes the `<command>` binary from the installed dependencies. Multiple symlinks can expose different binaries from the same venv.

`.appenv/`
: Internal state directory (venv, cached uv binary, logs). Managed entirely by appenv.

`.venv`
: Symlink to `.appenv/venv`. Created for tool compatibility — do not delete manually.

## Error Handling Strategy

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

## Logging Architecture

Each command gets its own log file at `.appenv/logs/<command>.log`. Logs use `TimedRotatingFileHandler` with daily rotation and 7-day retention.

Verbose mode (`APPENV_VERBOSE=1`) adds a console handler with dimmed caller info (`funcName:lineno`) prepended to each message. Useful during development without cluttering normal output.

The logger is a module-level `logging.getLogger("appenv")` singleton, configured per-command by `setup_logging()`. All components use it for structured debug output.
