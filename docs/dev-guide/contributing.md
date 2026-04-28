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

Type annotations go in `.pyi` stub files, not in `.py` source files. This is the PEP 561 pattern: `src/appenv.py` has the implementation with minimal typing, `src/appenv.pyi` has full type annotations. The `src/py.typed` marker file signals PEP 561 compliance to type checkers.

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
# All tests
uv run pytest

# Specific file
uv run pytest tests/test_pyproject.py

# With coverage report
uv run pytest --cov=appenv --cov-report=term-missing
```

Integration tests in `tests/integration/` exercise the full bootstrap workflow end-to-end.

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

- **User docs**: `docs/user-guide/` — usage and workflows
- **Dev docs**: `docs/dev-guide/` — architecture and this guide
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
