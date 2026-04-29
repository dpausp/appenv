"""Spec validation tests for output-patterns.

Phase 1: xfail contract tests that verify Phase 2 implementation
correctly adds/upgrades pytest-patterns tests in the target test files.

Each test reads the target test file source and verifies it contains
the expected pattern test structure as defined in the spec.

Spec: .agents/impl_specs/output-patterns.md
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

TESTS_DIR = Path(__file__).parent.parent
TEST_MAIN = TESTS_DIR / "test_main.py"
TEST_INIT = TESTS_DIR / "test_init.py"
TEST_MIGRATE = TESTS_DIR / "test_migrate.py"
TEST_PREPARE = TESTS_DIR / "test_prepare.py"


def _read(path: Path) -> str:
    return path.read_text()


# ============================================================================
# 1. --help pattern test in test_main.py
# ============================================================================


@pytest.mark.xfail(
    reason=(
        "Phase 2 contract: test_main_shows_grouped_help must use "
        "patterns.main.in_order with group headers"
    )
)
def test_help_pattern_uses_patterns_fixture():
    """test_main_shows_grouped_help must accept and use the patterns fixture.

    Phase 2 converts test_main_shows_grouped_help from simple string checks
    to patterns.main.in_order with group headers (Project:, Venv:, Tools:,
    Debug:) and their commands.
    """
    source = _read(TEST_MAIN)
    assert "def test_main_shows_grouped_help(" in source
    func_body = _extract_function(source, "test_main_shows_grouped_help")
    assert "patterns" in func_body


@pytest.mark.xfail(
    reason=(
        "Phase 2 contract: test_main_shows_grouped_help must use "
        "in_order with group headers"
    )
)
def test_help_pattern_has_group_headers_in_order():
    """The help pattern test must use in_order with the 4 group headers."""
    source = _read(TEST_MAIN)
    func_body = _extract_function(source, "test_main_shows_grouped_help")

    assert "patterns.main.in_order" in func_body

    # Must include the 4 group headers from GroupedHelpFormatter
    assert "Project:" in func_body
    assert "Venv:" in func_body
    assert "Tools:" in func_body
    assert "Debug:" in func_body

    # Must include command names in the pattern
    assert "init" in func_body
    assert "migrate" in func_body
    assert "prepare" in func_body
    assert "python" in func_body
    assert "version" in func_body


@pytest.mark.xfail(
    reason=(
        "Phase 2 contract: test_main_shows_grouped_help must assert "
        "full_pattern == captured.out"
    )
)
def test_help_pattern_has_full_assertion():
    """The help pattern test must have the standard full_pattern assertion."""
    source = _read(TEST_MAIN)
    func_body = _extract_function(source, "test_main_shows_grouped_help")

    assert "full_pattern = patterns.full" in func_body
    assert (
        'full_pattern.merge("main")' in func_body
        or "full_pattern.merge('main')" in func_body
    )
    assert "assert full_pattern ==" in func_body


# ============================================================================
# 2. init fresh start in test_init.py
# ============================================================================


@pytest.mark.xfail(
    reason=(
        "Phase 2 contract: test_init_fresh_start_interactive must "
        "assert full_pattern == captured.out"
    )
)
def test_init_fresh_start_has_full_pattern_assertion():
    """test_init_fresh_start_interactive must assert full_pattern == captured.out.

    The current code defines patterns via in_order but never asserts them
    against the output — the pattern check is a no-op. Phase 2 adds the
    missing assertion block.
    """
    source = _read(TEST_INIT)
    func_body = _extract_function(source, "test_init_fresh_start_interactive")

    assert "full_pattern = patterns.full" in func_body
    assert "full_pattern ==" in func_body
    # The assertion must compare against captured.out (not .lower())
    assert "assert full_pattern == captured.out" in func_body


@pytest.mark.xfail(
    reason=(
        "Phase 2 contract: test_init_fresh_start_interactive must "
        "use ... not escaped dots"
    )
)
def test_init_fresh_start_uses_wildcard_dots():
    """test_init_fresh_start_interactive must use ... (wildcard) not
    escaped dots.

    In pytest-patterns, ... is converted to .*? via re.escape +
    targeted replace. Using \\..... in a raw string creates literal
    backslash-dot which won't match source output containing literal
    dots. The pattern must use bare ... for wildcards.
    """
    source = _read(TEST_INIT)
    func_body = _extract_function(source, "test_init_fresh_start_interactive")

    assert r"\.\.\." not in func_body, (
        "Pattern must use ... (wildcard) not \\..... (escaped dots). "
        "pytest-patterns converts ... to .*? automatically."
    )


# ============================================================================
# 3. migrate full flow in test_migrate.py
# ============================================================================


@pytest.mark.xfail(
    reason=(
        "Phase 2 contract: test_migrate.py must have a new "
        "migrate full flow pattern test"
    )
)
def test_migrate_full_flow_pattern_test_exists():
    """A new test must exist in test_migrate.py that patterns the full
    migrate flow.

    The full migrate flow produces structured multi-line output:
    - 'Migrating from requirements.txt to pyproject.toml...'
    - 'Preparing/cleaning .appenv directory ...'
    - '=== Pyproject Migration completed ==='
    - 'requirements.{txt,lock} kept as legacy...'

    Phase 2 adds a new test that uses patterns to verify these strings.
    """
    source = _read(TEST_MIGRATE)

    has_migrate_flow_test = (
        "Migrating from requirements.txt" in source
        and "patterns" in source
        and "Migration completed" in source
    )
    assert has_migrate_flow_test, (
        "test_migrate.py must have a test that patterns the full migration "
        "flow including 'Migrating from requirements.txt' and "
        "'Migration completed'"
    )


@pytest.mark.xfail(
    reason=(
        "Phase 2 contract: migrate full flow test must use in_order "
        "with concrete strings"
    )
)
def test_migrate_full_flow_uses_concrete_patterns():
    """The migrate full flow test must use in_order with source-verified
    strings."""
    source = _read(TEST_MIGRATE)

    # Must include concrete strings from source (lines 893-924)
    assert (
        "Preparing/cleaning .appenv directory" in source
        or "Preparing/cleaning" in source
    )
    assert (
        "=== Pyproject Migration completed ===" in source
        or "Pyproject Migration completed" in source
    )


# ============================================================================
# 4. migrate editable warnings in test_migrate.py
# ============================================================================


@pytest.mark.xfail(
    reason=(
        "Phase 2 contract: editable tests must use concrete warning "
        "text, not loose keywords"
    )
)
def test_editable_tests_use_concrete_warning_text():
    """Editable tests must use concrete warning text from source.

    Source (line 233): 'Warning: {n} editable install(s) skipped:'
    Source (line 238): 'Add them manually to pyproject.toml if needed.'

    Current loose pattern: '...warning...skipped...'
    Required concrete pattern: must contain the actual warning text.
    """
    source = _read(TEST_MIGRATE)
    editable_tests = _extract_all_functions_with_name_containing(source, "editable")

    for func_name, func_body in editable_tests:
        has_concrete_warning = (
            "editable install" in func_body
            or "editable install(s) skipped" in func_body
        )
        assert has_concrete_warning, (
            f"Editable test '{func_name}' must use concrete warning text "
            f"from source (e.g., 'editable install(s) skipped'), "
            f"not loose keyword patterns"
        )


@pytest.mark.xfail(
    reason=(
        "Phase 2 contract: editable tests must not use loose "
        "...warning...skipped... patterns"
    )
)
def test_editable_tests_no_loose_keyword_patterns():
    """Editable tests must not use ultra-loose keyword patterns.

    The loose pattern '...warning...skipped...' matches any line
    containing both words anywhere. Phase 2 replaces with concrete
    strings from source.
    """
    source = _read(TEST_MIGRATE)

    assert "...warning...skipped..." not in source, (
        "Editable tests must not use loose '...warning...skipped...' "
        "pattern. Replace with concrete warning text from source."
    )


# ============================================================================
# 5. Binary not found in test_main.py
# ============================================================================


@pytest.mark.xfail(
    reason=("Phase 2 contract: binary-not-found test must use patterns fixture")
)
def test_binary_not_found_uses_patterns():
    """test_run_missing_binary_shows_helpful_error must use patterns fixture.

    Source (lines 681-695) produces structured multi-line output:
    - 'Error: Binary ... not found in .../bin/'
    - 'The symlink ... determines which binary gets executed.'
    - 'Available binaries:'
    - 'Either:'
    - '  - Install a package...'
    - '  - Add a [project.scripts] entry:'
    - '  - Or create a symlink...'

    Phase 2 upgrades the existing test to use patterns.
    """
    source = _read(TEST_MAIN)
    func_body = _extract_function(source, "test_run_missing_binary_shows_helpful_error")

    assert "patterns" in func_body, (
        "test_run_missing_binary_shows_helpful_error must accept patterns fixture"
    )


@pytest.mark.xfail(
    reason=(
        "Phase 2 contract: binary-not-found test must use in_order with full output"
    )
)
def test_binary_not_found_has_full_pattern():
    """Binary-not-found test must use patterns.main.in_order with all
    source strings."""
    source = _read(TEST_MAIN)
    func_body = _extract_function(source, "test_run_missing_binary_shows_helpful_error")

    assert "patterns.main.in_order" in func_body
    assert "not found in" in func_body
    assert "Available binaries" in func_body or "Available binaries:" in func_body
    assert "[project.scripts]" in func_body
    assert "full_pattern = patterns.full" in func_body
    assert "assert full_pattern ==" in func_body


# ============================================================================
# 6. Verbose prepare in test_prepare.py
# ============================================================================


@pytest.mark.xfail(
    reason=(
        "Phase 2 contract: test_prepare_verbose_output must use "
        "in_order with concrete strings"
    )
)
def test_prepare_verbose_uses_main_in_order():
    """test_prepare_verbose_output must use patterns.main.in_order with
    concrete debug labels.

    Source (lines 1086-1089, 1124) produces verbose debug output:
    - 'project base: ...' (line 1086)
    - 'Creating fresh venv with uv ...' (line 1124)
    - 'activated extras/optional deps: ...' (line 1069)

    Phase 2 upgrades from only no_errors checks to include these
    concrete strings via patterns.main.in_order.
    """
    source = _read(TEST_PREPARE)
    func_body = _extract_function(source, "test_prepare_verbose_output")

    assert "patterns.main.in_order" in func_body, (
        "test_prepare_verbose_output must use patterns.main.in_order "
        "with concrete debug output strings"
    )


@pytest.mark.xfail(
    reason=(
        "Phase 2 contract: test_prepare_verbose_output pattern must "
        "include concrete source strings in in_order"
    )
)
def test_prepare_verbose_has_concrete_source_strings():
    """Verbose prepare pattern must include actual debug labels in
    in_order call.

    The current code has these as simple 'assert "..." in out' checks.
    Phase 2 must move them into patterns.main.in_order as pattern strings.
    We verify by checking that an in_order call exists that contains
    these strings.
    """
    source = _read(TEST_PREPARE)
    func_body = _extract_function(source, "test_prepare_verbose_output")

    assert "patterns.main.in_order" in func_body

    # The in_order block must contain these concrete strings from source.
    in_order_block = _extract_in_order_block(func_body)
    assert in_order_block, "patterns.main.in_order must have a pattern argument"

    assert "project base:" in in_order_block
    assert "Creating fresh venv with uv ..." in in_order_block
    assert "activated extras/optional deps:" in in_order_block


@pytest.mark.xfail(
    reason=(
        "Phase 2 contract: test_prepare_verbose_output must not "
        "rely on only no_errors pattern"
    )
)
def test_prepare_verbose_not_only_no_errors():
    """test_prepare_verbose_output must have more than just no_errors.

    Currently the test only asserts simple string presence + no_errors
    refused checks. Phase 2 adds main.in_order with the concrete verbose
    output strings. The test should merge 'main' into full_pattern.
    """
    source = _read(TEST_PREPARE)
    func_body = _extract_function(source, "test_prepare_verbose_output")

    assert (
        'full_pattern.merge("main"' in func_body
        or "full_pattern.merge('main'" in func_body
    ), (
        "test_prepare_verbose_output must merge 'main' into full_pattern "
        "(the main section contains the concrete in_order patterns)"
    )


# ============================================================================
# Helpers
# ============================================================================


def _extract_function(source: str, func_name: str) -> str:
    """Extract the body of a top-level function from source code.

    Returns the text from the 'def' line to the next top-level def or EOF.
    """
    lines = source.splitlines()
    start = None
    end = len(lines)

    for i, line in enumerate(lines):
        if line.startswith(f"def {func_name}("):
            start = i
        elif start is not None and line.startswith("def ") and i > start:
            end = i
            break

    if start is None:
        return ""

    return "\n".join(lines[start:end])


def _extract_all_functions_with_name_containing(
    source: str, substring: str
) -> list[tuple[str, str]]:
    """Extract all top-level functions whose name contains the substring.

    Returns list of (func_name, func_body) tuples.
    """
    lines = source.splitlines()
    results: list[tuple[str, str]] = []
    func_starts: list[tuple[int, str]] = []

    for i, line in enumerate(lines):
        if line.startswith("def ") and substring in line:
            name = line.split("def ")[1].split("(")[0]
            func_starts.append((i, name))

    for idx, (start, name) in enumerate(func_starts):
        if idx + 1 < len(func_starts):
            end = func_starts[idx + 1][0]
        else:
            end = len(lines)
            for i in range(start + 1, len(lines)):
                if lines[i].startswith("def "):
                    end = i
                    break

        results.append((name, "\n".join(lines[start:end])))

    return results


def _extract_in_order_block(func_body: str) -> str:
    """Extract the string argument passed to patterns.main.in_order(...).

    Handles both inline string arguments and triple-quoted multi-line
    strings. Returns the argument text or empty string if not found.
    """
    match = re.search(r"patterns\.main\.in_order\(\s*", func_body)
    if not match:
        return ""

    remaining = func_body[match.end() :]

    if remaining.startswith('"""') or remaining.startswith("'''"):
        quote = remaining[:3]
        end_marker = remaining.index(quote, 3)
        return remaining[3:end_marker]

    if remaining.startswith('r"""') or remaining.startswith("r'''"):
        quote = remaining[1:4]
        end_marker = remaining.index(quote, 4)
        return remaining[4:end_marker]

    # Single-line string argument
    depth = 1
    result: list[str] = []
    for char in remaining:
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                break
        result.append(char)
    return "".join(result)
