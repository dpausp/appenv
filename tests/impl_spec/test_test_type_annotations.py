"""Spec validation tests for test-type-annotations impl spec.

Validates the contract defined in .agents/impl_specs/test-type-annotations.md.
These tests are expected to fail until Phase 2 implementation creates/updates
the .pyi stub files for the tests/ directory.
"""

import ast
from pathlib import Path

import pytest

# Resolve tests/ directory relative to this file
TESTS_DIR = Path(__file__).resolve().parent.parent


def _collect_py_modules(root):
    """Collect .py files excluding __pycache__, __init__.py, conftest."""
    modules = []
    for py_file in sorted(root.rglob("*.py")):
        if "__pycache__" in py_file.parts:
            continue
        if py_file.name == "__init__.py":
            continue
        if py_file.name == "conftest.py":
            continue
        modules.append(py_file)
    return modules


def _get_function_defs(source):
    """Parse source and return all top-level and class method defs."""
    tree = ast.parse(source)
    functions = [
        node for node in ast.iter_child_nodes(tree) if isinstance(node, ast.FunctionDef)
    ]
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.ClassDef):
            functions.extend(
                child
                for child in ast.iter_child_nodes(node)
                if isinstance(child, ast.FunctionDef)
            )
    return functions


def _get_function_names(source):
    """Parse source and return set of all function/method names."""
    return {f.name for f in _get_function_defs(source)}


# --- Test 1: Complete stub coverage ---


@pytest.mark.xfail(reason="Spec validation — will pass after Phase 2 implementation")
def test_complete_stub_coverage():
    """COMPLETE STUB COVERAGE: Every .py test module has a matching .pyi stub.

    Validates spec decision 'complete-stub-coverage': every .py file in
    tests/ must have a matching .pyi stub file.
    """
    py_modules = _collect_py_modules(TESTS_DIR)
    missing = []

    for py_file in py_modules:
        pyi_file = py_file.with_suffix(".pyi")
        if not pyi_file.exists():
            rel = py_file.relative_to(TESTS_DIR)
            missing.append(str(rel))

    assert missing == [], f"Missing .pyi stubs for: {missing}"


# --- Test 2: Stub sync - function count ---


@pytest.mark.xfail(reason="Spec validation — will pass after Phase 2 implementation")
def test_stub_sync_function_count():
    """STUB SYNC: .pyi stub has same function/method count as .py.

    Validates spec decision 'complete-stub-coverage': stubs must be in
    sync with every test function, helper function, and class in the .py.
    """
    py_modules = _collect_py_modules(TESTS_DIR)
    mismatches = []

    for py_file in py_modules:
        pyi_file = py_file.with_suffix(".pyi")
        if not pyi_file.exists():
            continue  # covered by test_complete_stub_coverage

        py_source = py_file.read_text(encoding="utf-8")
        pyi_source = pyi_file.read_text(encoding="utf-8")

        py_funcs = _get_function_defs(py_source)
        pyi_funcs = _get_function_defs(pyi_source)

        if len(py_funcs) != len(pyi_funcs):
            rel = py_file.relative_to(TESTS_DIR)
            mismatches.append(
                f"{rel}: .py has {len(py_funcs)} functions, "
                f".pyi has {len(pyi_funcs)} functions"
            )

    assert mismatches == [], "Function count mismatches:\n" + "\n".join(mismatches)


# --- Test 3: No phantom functions ---


@pytest.mark.xfail(reason="Spec validation — will pass after Phase 2 implementation")
def test_no_phantom_functions():
    """NO PHANTOM FUNCTIONS: No functions in .pyi that don't exist in .py.

    Validates spec requirement: stub function count matches .py function
    count with no phantom tests (functions in .pyi but not in .py).
    """
    py_modules = _collect_py_modules(TESTS_DIR)
    phantoms = []

    for py_file in py_modules:
        pyi_file = py_file.with_suffix(".pyi")
        if not pyi_file.exists():
            continue

        py_source = py_file.read_text(encoding="utf-8")
        pyi_source = pyi_file.read_text(encoding="utf-8")

        py_names = _get_function_names(py_source)
        pyi_names = _get_function_names(pyi_source)

        extra = pyi_names - py_names
        if extra:
            rel = py_file.relative_to(TESTS_DIR)
            phantoms.append(f"{rel}: phantom functions in .pyi: {sorted(extra)}")

    assert phantoms == [], "Phantom functions found:\n" + "\n".join(phantoms)


# --- Test 4: Fixture parameter typing ---


@pytest.mark.xfail(reason="Spec validation — will pass after Phase 2 implementation")
def test_fixture_parameter_typing():
    """FIXTURE PARAMETER TYPING: All params in .pyi stubs are typed.

    Validates spec decision 'full-fixture-typing': all fixture parameters
    in .pyi test function stubs must have full type annotations.
    """
    py_modules = _collect_py_modules(TESTS_DIR)
    untyped = []

    for py_file in py_modules:
        pyi_file = py_file.with_suffix(".pyi")
        if not pyi_file.exists():
            continue

        pyi_source = pyi_file.read_text(encoding="utf-8")
        funcs = _get_function_defs(pyi_source)

        for func in funcs:
            for arg in func.args.args:
                if arg.arg == "self":
                    continue
                if arg.annotation is None:
                    rel = pyi_file.relative_to(TESTS_DIR)
                    untyped.append(
                        f"{rel}::{func.name}: "
                        f"parameter '{arg.arg}' has no type annotation"
                    )

    assert untyped == [], "Untyped parameters found:\n" + "\n".join(untyped)


# --- Test 5: Specific new .pyi files exist ---


@pytest.mark.xfail(reason="Spec validation — will pass after Phase 2 implementation")
def test_specific_new_stubs_exist():
    """SPECIFIC FILES: New .pyi stubs from spec Requirements exist.

    Validates spec requirements: 6 specific .pyi files to be created.
    """
    expected_stubs = [
        TESTS_DIR / "test_self_update.pyi",
        TESTS_DIR / "test_docs_spec.pyi",
        TESTS_DIR / "impl_spec" / "test_docs_e2e_alignment.pyi",
        TESTS_DIR / "integration" / "test_pip_install_uv.pyi",
        TESTS_DIR / "integration" / "test_cli.pyi",
        TESTS_DIR / "integration" / "test_subprocess.pyi",
    ]

    missing = [
        str(stub.relative_to(TESTS_DIR)) for stub in expected_stubs if not stub.exists()
    ]

    assert missing == [], f"Missing new .pyi stubs: {missing}"


# --- Test 6: Specific updated stubs have correct function counts ---


@pytest.mark.xfail(reason="Spec validation — will pass after Phase 2 implementation")
def test_specific_updated_stubs_sync():
    """SPECIFIC FIXES: Outdated stubs now have correct function counts.

    Validates spec requirements: 4 specific .pyi files that need updating
    to match their corresponding .py files.
    """
    files_to_check = [
        TESTS_DIR / "test_prepare.pyi",
        TESTS_DIR / "test_update_lockfile.pyi",
        TESTS_DIR / "test_migrate.pyi",
        TESTS_DIR / "test_init.pyi",
    ]

    mismatches = []

    for pyi_path in files_to_check:
        py_path = pyi_path.with_suffix(".py")

        py_source = py_path.read_text(encoding="utf-8")
        pyi_source = pyi_path.read_text(encoding="utf-8")

        py_count = len(_get_function_defs(py_source))
        pyi_count = len(_get_function_defs(pyi_source))

        if py_count != pyi_count:
            rel = pyi_path.relative_to(TESTS_DIR)
            mismatches.append(
                f"{rel}: .py has {py_count} functions, .pyi has {pyi_count}"
            )

    assert mismatches == [], "Sync issues in updated stubs:\n" + "\n".join(mismatches)
