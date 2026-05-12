"""Spec validation tests for docs-fix implementation plan.

Each test references a decision slug from .agents/impl_specs/docs-fix.md.
These tests define the contract that Phase 2 implementation must fulfill.
"""

from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent


def test_file_cleanup_deleted_files_not_present():
    """file-cleanup: docs/appenv.md, docs/README.md,
    docs/_snippets/quickstart.md must not exist."""
    assert not (ROOT / "docs" / "appenv.md").exists(), (
        "docs/appenv.md should be deleted"
    )
    assert not (ROOT / "docs" / "README.md").exists(), (
        "docs/README.md should be deleted"
    )
    assert not (ROOT / "docs" / "_snippets" / "quickstart.md").exists(), (
        "docs/_snippets/quickstart.md should be deleted"
    )


def test_flat_toctree_index_has_toctree():
    """flat-toctree: docs/index.md must contain a {toctree} directive."""
    content = (ROOT / "docs" / "index.md").read_text()
    assert "{toctree}" in content


def test_flat_toctree_lists_all_content_files():
    """flat-toctree: toctree must reference section indexes."""
    content = (ROOT / "docs" / "index.md").read_text()
    expected_refs = [
        "user/index",
        "dev/index",
    ]
    for ref in expected_refs:
        assert ref in content, f"toctree must reference {ref}"


def test_flat_toctree_conf_suppress_warnings_only_myst():
    """flat-toctree (D12): conf.py suppress_warnings
    must contain only myst.header."""
    content = (ROOT / "docs" / "conf.py").read_text()
    # Extract the suppress_warnings list
    in_list = False
    entries: list[str] = []
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("suppress_warnings"):
            in_list = True
            continue
        if in_list:
            if stripped == "]":
                break
            entry = stripped.strip('",').strip()
            if entry:
                entries.append(entry)
    assert entries == ["myst.header"], (
        f"suppress_warnings should be only ['myst.header'], got {entries}"
    )


def test_factual_corrections_pyi_has_exit_code_usage():
    """factual-corrections: src/appenv.pyi must declare EXIT_CODE_USAGE."""
    content = (ROOT / "src" / "appenv.pyi").read_text()
    assert "EXIT_CODE_USAGE" in content


def test_factual_corrections_no_appenv_profiling_in_readme():
    """factual-corrections: README.md must not reference
    phantom APPENV_PROFILING."""
    content = (ROOT / "README.md").read_text()
    assert "APPENV_PROFILING" not in content


def test_factual_corrections_no_specs_dir_in_index():
    """factual-corrections: docs/index.md must not list
    non-existent specs/ directory."""
    content = (ROOT / "docs" / "index.md").read_text()
    assert "specs/" not in content


def test_factual_corrections_correct_uv_commands_in_index():
    """factual-corrections: docs/index.md must use
    'uv run pytest' and 'uv run ruff check'."""
    content = (ROOT / "docs" / "index.md").read_text()
    # Bare 'uv pytest' without 'run' before it is wrong
    assert "uv pytest" not in content, (
        "Found bare 'uv pytest' — should be 'uv run pytest'"
    )
    # Bare 'uv ruff check' without 'run' before it is wrong
    assert "uv ruff check" not in content, (
        "Found bare 'uv ruff check' — should be 'uv run ruff check'"
    )


def test_factual_corrections_exit_code_usage_in_commands():
    """factual-corrections: commands.md exit codes table
    must include code 64 (USAGE)."""
    content = (ROOT / "docs" / "user" / "commands.md").read_text()
    # Find exit codes section and verify 64/USAGE
    assert "64" in content, "Exit code 64 must appear in commands.md"
    assert "USAGE" in content, "Exit code name USAGE must appear in commands.md"


def test_factual_corrections_exit_code_usage_in_architecture():
    """factual-corrections: dev docs must mention exit code 64 (USAGE)."""
    content = (ROOT / "docs" / "dev" / "index.md").read_text()
    assert "64" in content, "Exit code 64 must appear in dev docs"
    assert "USAGE" in content, "Exit code name USAGE must appear in dev docs"


def test_factual_corrections_pyi_stub_claim_corrected():
    """factual-corrections: dev docs must not claim
    .pyi files are 'not currently used'."""
    content = (ROOT / "docs" / "dev" / "index.md").read_text()
    assert "not currently used" not in content


def test_run_command_removal_no_run_command_in_commands_doc():
    """run-command-removal: commands.md must not have a ## run section heading."""
    content = (ROOT / "docs" / "user" / "commands.md").read_text()
    # Check for run as a command section header (## run or ## `run`)
    lines = content.splitlines()
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("## run") or stripped.startswith("## `run`"):
            pytest.fail(f"Found run command section header: {stripped}")


def test_python_version_statement_nuance_in_index():
    """python-version-statement: docs/index.md must mention both 3.9 and 3.10."""
    content = (ROOT / "docs" / "index.md").read_text()
    assert "3.9" in content, "docs/index.md must mention Python 3.9 (bootstrap compat)"
    assert "3.10" in content, "docs/index.md must mention Python 3.10 (managed envs)"


def test_quick_start_rewrite_prompt_text_matches_source():
    """quick-start-rewrite / factual-corrections:
    init prompt must match source at appenv.py:834."""
    content = (ROOT / "docs" / "user" / "commands.md").read_text()
    assert "Binary to expose" in content, (
        "commands.md must contain correct prompt text 'Binary to expose'"
    )
    assert "What should the command be named" not in content, (
        "commands.md must not contain stale prompt 'What should the command be named'"
    )


def test_quick_start_rewrite_dependency_is_httpie():
    """quick-start-rewrite: Quick Start dependency example
    must use httpie, not requests."""
    content = (ROOT / "docs" / "index.md").read_text()
    if "Quick Start" in content:
        # Find the Quick Start section
        sections = content.split("## ")
        for section in sections:
            if section.startswith("Quick Start"):
                assert "httpie" in section.lower(), (
                    "Quick Start must reference httpie (not requests) as the dependency"
                )
                assert "requests" not in section or "httpie" in section.lower(), (
                    "Quick Start should not use requests as the example dependency"
                )
                break
