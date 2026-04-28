# Documentation Validation Report

## Summary

- **Factual issues**: 5
- **Structural violations**: 3 (SVR-03, SVR-06, SVR-08 failed)
- **Quality score**: 51/100 — Grade: F

---

## Track A: Factual Validation Results

### API Coverage Issues

1. **Phantom command in help: `develop`** - /srv/s-dev/git/appenv/src/appenv.py:51
   - GroupedHelpFormatter lists "develop" in the "Venv" group, but no corresponding add_parser("develop") exists

2. **Phantom command in help: `settings`** - /srv/s-dev/git/appenv/src/appenv.py:53
   - GroupedHelpFormatter lists "settings" in the "Debug" group, but no corresponding parser exists

3. **Phantom command in help: `profiling`** - /srv/s-dev/git/appenv/src/appenv.py:53
   - GroupedHelpFormatter lists "profiling" in the "Debug" group, but no corresponding parser exists

4. **Documentation states .pyi file exists** - /srv/s-dev/git/appenv/docs/dev-guide/architecture.md:12
   - Documentation claims src/appenv.pyi exists but only appenv.py is present

### Test Coverage Issues

NO ISSUES - Comprehensive test suite exists covering all major functionality

### Code Example Issues

NO ISSUES - Code blocks are appropriate CLI examples, not executable Python requiring imports

### Internal Consistency Issues

1. **Potentially broken cross-reference** - /srv/s-dev/git/appenv/docs/dev-guide/contributing.md:35
   - References {doc}`architecture` but may need {doc}`dev-guide/architecture`

---

## Track B: Structural Validation Results

| Rule | Status | Details |
|------|--------|---------|
| SVR-01 | PASS | All 8 files use kebab-case |
| SVR-02 | PASS | All directories use kebab-case (dev-guide/, user-guide/, _snippets/, autoapi/) |
| SVR-03 | FAIL | **Missing index.md with toctree**: dev-guide/ and user-guide/ directories have no index.md |
| SVR-04 | PASS | Max depth: 2 levels (e.g., docs/user-guide/installation.md) |
| SVR-05 | PASS | Top-level dirs organized by reader need: user-guide/, dev-guide/ |
| SVR-06 | FAIL | **Orphan file**: docs/_snippets/quickstart.md not referenced by any toctree |
| SVR-07 | PASS | Root clean: only index.md at docs root |
| SVR-08 | FAIL | No index.md in dev-guide/ or user-guide/ subdirectories |
| SVR-09 | PASS | autoapi_type="python", autoapi_dirs=["../src"], autoapi_file_patterns=["*.py"] |
| SVR-10 | PASS | All required extensions present |
| SVR-11 | N/A | Sphinx not available in environment |
| SVR-12 | PASS | autoapi/src/appenv/index.rst exists (9KB generated) |

---

## Phase 2: Qualitative Audit Results

**Score**: 51/100 — Grade: F

### Critical Findings

- [Art. 3] /srv/s-dev/git/appenv/docs/user-guide/installation.md:5 — False confidence: States "Python 3.10 or later" but pyproject.toml:12 specifies requires-python = ">=3.9". Documentation claims 3.10 minimum when code supports 3.9.

### Warnings

- [Art. 3] /srv/s-dev/git/appenv/docs/user-guide/installation.md:6 — No version anchor for uv minimum. States "0.5.0 or later" but doesn't say "as of current version".

- [Art. 5] /srv/s-dev/git/appenv/docs/user-guide/workflows.md:85 — Unverified claim: ./appenv uv lock --upgrade-package requests documented but no verification this produces expected behavior.

- [Art. 5] /srv/s-dev/git/appenv/docs/user-guide/commands.md:97-100 — Missing failure modes. Describes what migrate DOES but not what happens when requirements.txt has unparseable lines.

- [Art. 2] /srv/s-dev/git/appenv/docs/dev-guide/architecture.md — Structure mirrors source. Organized by components (Python Version Selection, uv Management, Venv Lifecycle) not by reader tasks.

- [Art. 3] /srv/s-dev/git/appenv/docs/user-guide/workflows.md — No audience decision. Mixes basic walkthrough with advanced technical details.

- [Art. 5] /srv/s-dev/git/appenv/docs/user-guide/workflows.md:25-47 — Missing edge cases. Migration doesn't document: version specifier conversion failures, conflicting extras.

### Suggestions

- [Art. 7] /srv/s-dev/git/appenv/docs/user-guide/commands.md — Discoverability: No command overview table at start.

- [Art. 1] /srv/s-dev/git/appenv/docs/user-guide/workflows.md:88 — Minor fluff: "within version constraints" is self-evident.

- [Art. 7] /srv/s-dev/git/appenv/docs/_snippets/quickstart.md:10 — Missing use-case context: Doesn't explain what happens if you ctrl+C or skip prompts.