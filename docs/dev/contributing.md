# Contributing

How to set up a development environment and submit changes.

## Development Setup

```bash
git clone https://github.com/flyingcircusio/appenv.git
cd appenv
```

Run tests:

```bash
uv run pytest
```

All CI checks (lint, format, type-check, test) run via:

```bash
tox
```

## Code Style

appenv follows the style defined in `pyproject.toml` under `[tool.ruff]`. Run `uv run ruff check --fix .` and `uv run ruff format .` to apply.

### Type Annotations

Type annotations live in `.pyi` stub files, not in `.py` source files. The `src/appenv.pyi` stub is the complete type surface — it must include all public *and* private methods. Ruff's `ANN` rules are dropped because they ignore `.pyi` files entirely.

Any method signature change requires updating both `src/appenv.py` and `src/appenv.pyi`. Validate with `uv run ruff check --select PYI src/appenv.pyi`.

The `src/py.typed` marker file signals PEP 561 compliance to type checkers.

Test files follow the same stub-only policy — every `.py` in `tests/` has a matching `.pyi`. See [](#test-type-stubs) for patterns and fixture types.

### Exit Codes

Use BSD sysexits.h constants (`EXIT_CODE_DATAERR`, `EXIT_CODE_NOINPUT`, `EXIT_CODE_UNAVAILABLE`) defined at module level. See {doc}`architecture` for the full error handling strategy.

### Spec Comments

Non-trivial error handling uses `# SPEC:` comments to trace requirements:

```python
# SPEC: SRS-F001-cmd-wrapper - Enrich subprocess errors with command output context
try:
    result = subprocess.check_output(cmd_list, stderr=subprocess.STDOUT)
except subprocess.CalledProcessError as e:
    raise ValueError(e.output.decode("utf-8", "replace")) from e
```

## Running Tests

```bash
# All tests (excludes slow by default)
uv run pytest

# Specific file
uv run pytest tests/test_prepare.py

# With coverage report
uv run pytest --cov=appenv --cov-report=term-missing

# Include slow tests
uv run pytest -m ''
```

### Two-Tier Model

appenv has no natural seam for an integration tier — `uv` is either mocked (unit) or real (E2E). Tests fall into exactly two tiers:

**Unit tests** (`tests/test_*.py`)
: Mock `uv` via `MockUvBin`. Fast, no external dependencies. Covers logic branches, error handling, and argument construction.

**E2E tests** (`tests/integration/`)
: Real `uv`, real subprocess via `pexpect`. Exercises the full bootstrap workflow end-to-end. Requires `uv` installed on the system.

The standard 70/20/10 pyramid model does not apply — test expansion beyond unit coverage is E2E-only.

### Slow Marker

Any test consistently exceeding 2 seconds gets `@pytest.mark.slow`. The threshold is objective: measure new tests and apply the marker if they cross it.

- Default `pytest` configuration excludes slow tests (`-m "not slow"`)
- `tox` cov environment runs all tests including slow
- E2E tests should target under 2s to avoid needing the marker

(test-type-stubs)=
### Test Type Stubs

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

```bash
uv run ruff check --select PYI tests/
uv run ty check tests/
```

Stubs must stay in sync with their `.py` counterparts — any signature change updates both files. Ty runs on `src/` only in CI; test stub validation is manual until a follow-up enables it.

### Test Strategy

- **Existing code with gaps**: write tests first (tests-after) to cover uncovered paths
- **New features with code changes**: write tests alongside or before implementation
- **Existing features with no code changes** (e.g., untested subcommands): write E2E tests first (E2E-first) since the feature already works

## Quality Gates

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

## Documentation

Docs are built with Sphinx using MyST markdown and autoapi:

```bash
tox -e docs
```

- **User docs**: `docs/user/` — usage and workflows
- **Dev docs**: `docs/dev/` — architecture and this guide
- **API reference**: auto-generated from source by autoapi — do not write API docs by hand

See {doc}`architecture` for how components interact.

## Pull Request Process

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
