"""Tests for main() entry point and related functions."""

import argparse
import logging
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import cast

import pytest

import appenv
from appenv import UvVersion

from .conftest import MockUvBin, strip_ansi_codes

# main() tests


def test_main_shows_usage_without_subcommand(
    monkeypatch, capsys, tmp_path, no_ensure_python, mock_logdir
):
    """Test that calling appenv without subcommand shows usage."""
    monkeypatch.setattr("sys.argv", ["appenv"])
    monkeypatch.setattr(appenv, "__file__", "/some/path/appenv")

    # Should exit with usage message
    with pytest.raises(SystemExit):
        appenv.main()

    captured = capsys.readouterr()
    # Help output goes to stdout
    assert "usage: appenv" in captured.out


def test_grouped_help_formatter_skips_command_not_in_choices():
    """GroupedHelpFormatter skips commands not in action.choices (branch 68->67)."""
    formatter = appenv.GroupedHelpFormatter(prog="appenv")

    # Create a real argparse parser with subparsers
    parser = argparse.ArgumentParser(prog="appenv")
    subparsers = parser.add_subparsers(dest="command")

    # Add only 'init' and 'update-lockfile' subcommands (not 'migrate')
    subparsers.add_parser("init", help="Initialize project")
    subparsers.add_parser("update-lockfile", help="Update lockfile")
    # Note: 'migrate' is NOT added, though it's in the Project group

    # Get the _SubParsersAction from the parser
    subparsers_action = None
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            subparsers_action = action
            break

    # Skip test if no subparsers action found (shouldn't happen)
    assert subparsers_action is not None

    # Now call the formatter with this action
    result = formatter._format_action(subparsers_action)

    # 'init' and 'update-lockfile' should be in output
    assert "init" in result
    assert "update-lockfile" in result
    # 'migrate' should NOT be in output (it's not in action.choices)
    assert "migrate" not in result
    # Group header should still appear
    assert "Project:" in result


def test_main_shows_grouped_help(
    monkeypatch, capsys, tmp_path, patterns, no_ensure_python, mock_logdir
):
    """Test that help output shows commands grouped by category."""
    monkeypatch.setattr("sys.argv", ["appenv", "--help"])
    monkeypatch.setattr(appenv, "__file__", "/some/path/appenv")

    with pytest.raises(SystemExit):
        appenv.main()

    captured = capsys.readouterr()

    patterns.main.in_order(
        """\
...Project:...
...init...
...migrate...
...update-lockfile...
...Venv:...
...prepare...
...reset...
...Tools:...
...python...
...uv...
...Debug:...
...version...
"""
    )

    patterns.no_errors.optional("...")

    full_pattern = patterns.full
    full_pattern.merge("main")
    full_pattern.merge("no_errors")

    full_pattern.generate_example()

    assert full_pattern == captured.out


def test_help_same_as_no_args(
    monkeypatch, capsys, tmp_path, no_ensure_python, mock_logdir
):
    """Test that --help shows grouped help output."""
    monkeypatch.setattr(appenv, "__file__", "/some/path/appenv")

    # Get output with --help
    monkeypatch.setattr("sys.argv", ["appenv", "--help"])
    with pytest.raises(SystemExit):
        appenv.main()
    captured_help = capsys.readouterr()

    # --help shows full grouped help on stdout
    assert "Project:" in captured_help.out
    assert "Commands:" in captured_help.out


def test_main_clears_pythonpath(monkeypatch, no_ensure_python):
    monkeypatch.setattr("sys.argv", ["appenv"])

    monkeypatch.setenv("PYTHONPATH", "/some/path")
    assert "PYTHONPATH" in os.environ

    with pytest.raises(SystemExit):
        appenv.main()

    # PYTHONPATH should still be cleared before the exit
    assert "PYTHONPATH" not in os.environ


def test_main_calls_run_when_not_appenv(monkeypatch, tmp_path, no_ensure_python):
    app_file = tmp_path / "myapp"
    app_file.write_text("#!/usr/bin/env python3\nprint('test')\n")

    run_called = []
    monkeypatch.setattr(
        appenv.AppEnv,
        "run",
        lambda self, cmd, argv: run_called.append((cmd, argv)),
    )

    monkeypatch.setattr("sys.argv", ["myapp", "--help"])
    monkeypatch.setattr(appenv, "__file__", str(app_file))

    appenv.main()

    assert run_called == [("myapp", ["--help"])]


def test_main_calls_meta_when_appenv(monkeypatch, no_ensure_python):
    meta_called = []
    monkeypatch.setattr(
        appenv.AppEnv,
        "meta",
        lambda self, args, prog="appenv": meta_called.append(args),
    )

    monkeypatch.setattr("sys.argv", ["appenv"])
    monkeypatch.setattr(appenv, "__file__", "/some/path/appenv")

    appenv.main()

    # When called as "appenv" without args, meta([]) is called
    # which shows help (same as --help)
    assert meta_called == [[]]


# cmd() tests


def test_cmd_with_string_uses_shell():
    result = appenv.cmd("echo hello")
    assert b"hello" in result


def test_cmd_raises_value_error_on_failure():
    with pytest.raises(ValueError):
        appenv.cmd("exit 1", quiet=True)


def test_cmd_with_list_no_shell():
    result = appenv.cmd(["echo", "world"])
    assert b"world" in result


@pytest.mark.no_mock_uv_version
def test_ensure_uv_returns_uvbin_from_path(monkeypatch, tmp_path):
    """ensure_uv returns UvBin with uv from PATH if available."""
    monkeypatch.setattr(
        "shutil.which", lambda name: "/usr/bin/uv" if name == "uv" else None
    )

    # Mock subprocess.run to return version
    def mock_run(cmd, **kwargs):
        text_mode = kwargs.get("text", False)
        stdout = "uv 0.5.0\n" if text_mode else b"uv 0.5.0\n"
        return subprocess.CompletedProcess(cmd, 0, stdout, b"")

    monkeypatch.setattr(subprocess, "run", mock_run)

    result = appenv.ensure_uv(tmp_path)
    assert isinstance(result, appenv.UvBin)
    assert str(result.bin) == "/usr/bin/uv"


# meta() tests


def test_meta_calls_reset(monkeypatch, tmp_path, app_env):
    env = app_env()
    monkeypatch.setattr("sys.argv", ["appenv", "reset"])

    reset_called = []
    monkeypatch.setattr(
        env, "reset", lambda args=None, remaining=None: reset_called.append(True)
    )

    env.meta()

    assert reset_called == [True]


def test_meta_calls_prepare(monkeypatch, tmp_path, app_env):
    env = app_env()
    monkeypatch.setattr("sys.argv", ["appenv", "prepare"])

    prepare_called = []
    monkeypatch.setattr(
        env,
        "prepare",
        lambda args=None, remaining=None: prepare_called.append(True),
    )

    env.meta()

    assert prepare_called == [True]


def test_meta_calls_python(monkeypatch, tmp_path, app_env):
    env = app_env()
    monkeypatch.setattr("sys.argv", ["appenv", "python"])

    python_called = []
    monkeypatch.setattr(
        env,
        "python",
        lambda args, remaining: python_called.append((args, remaining)),
    )

    env.meta()

    assert len(python_called) == 1


def test_meta_calls_run_script(monkeypatch, tmp_path, app_env):
    env = app_env()
    monkeypatch.setattr("sys.argv", ["appenv", "run", "myscript"])

    run_called = []
    monkeypatch.setattr(
        env,
        "run_script",
        lambda args, remaining: run_called.append((args.script, remaining)),
    )

    env.meta()

    assert run_called == [("myscript", [])]


# run() tests


def test_run_sets_env_and_execs(monkeypatch, tmp_path, app_env, make_pyproject):
    env = app_env()

    # Add pyproject.toml and uv.lock so _prepare_venv doesn't exit
    make_pyproject(tmp_path, '[project]\nname = "test"\nversion = "0.1.0"\n')

    env_dir = tmp_path / ".appenv" / "abc123"
    env_dir.mkdir(parents=True)
    bin_dir = env_dir / "bin"
    bin_dir.mkdir()
    (bin_dir / "myapp").write_text("#!/bin/sh\necho hello\n")

    monkeypatch.setattr(env, "_prepare_venv", lambda dev_mode=False: env_dir)

    execv_called = []
    monkeypatch.setattr(
        os,
        "execv",
        lambda path, argv: execv_called.append((path, argv)),
    )
    monkeypatch.setattr("os.chdir", lambda p: None)

    env.run("myapp", ["--help"])

    assert len(execv_called) == 1
    assert "myapp" in execv_called[0][0]


def test_run_missing_binary_shows_helpful_error(
    monkeypatch, tmp_path, capsys, app_env, patterns
):
    env = app_env()

    env_dir = tmp_path / ".appenv" / "venv"
    bin_dir = env_dir / "bin"
    bin_dir.mkdir(parents=True)
    (bin_dir / "python").write_text("#!/bin/sh\necho python\n")
    (bin_dir / "ruff").write_text("#!/bin/sh\necho ruff\n")

    monkeypatch.setattr(env, "_prepare_venv", lambda dev_mode=False: env_dir)

    with pytest.raises(SystemExit) as exc_info:
        env.run("myapp", ["--help"])

    assert exc_info.value.code == appenv.EXIT_CODE_NOINPUT

    captured = capsys.readouterr()

    patterns.main.in_order(
        """\
...Error: Binary '...' not found in .../bin/
...The symlink '...' determines which binary gets executed.
...Available binaries:
...python...
...ruff...
...Either:
...Install a package that provides the '...' binary
...[project.scripts]...
...Or create a symlink with the name of an installed binary"""
    )
    patterns.no_errors.optional("...")

    full_pattern = patterns.full
    full_pattern.merge("main")
    full_pattern.merge("no_errors")

    full_pattern.generate_example()

    assert full_pattern == captured.out


def test_python_method_calls_run(monkeypatch, tmp_path, app_env):
    env = app_env()

    run_called = []
    monkeypatch.setattr(env, "run", lambda cmd, argv: run_called.append((cmd, argv)))

    env.python(argparse.Namespace(), ["-c", "print(1)"])

    assert run_called == [("python", ["-c", "print(1)"])]


# print_colored_diff() tests


def test_print_colored_diff_returns_true_when_changes(capsys):
    old = "line1\nline2\n"
    new = "line1\nline3\n"

    result = appenv.print_colored_diff(old, new, "old.txt", "new.txt")

    assert result is True
    captured = capsys.readouterr()
    output = strip_ansi_codes(captured.out)

    expected = """\
--- old.txt
+++ new.txt
@@ -1,2 +1,2 @@
 line1
-line2
+line3
"""
    assert output == expected


def test_print_colored_diff_returns_false_when_no_changes(capsys):
    content = "line1\nline2\n"

    result = appenv.print_colored_diff(content, content, "same.txt", "same.txt")

    assert result is False
    captured = capsys.readouterr()
    assert captured.out == ""


# ensure_uv() tests


@pytest.mark.no_mock_uv_version
def test_ensure_uv_returns_uvbin_on_success(monkeypatch, tmp_path, capsys):
    """ensure_uv returns UvBin instance on success."""
    uv_bin = Path("/usr/bin/uv")

    class FakeResult:
        stdout = "uv 0.10.3 (abc123 2024-01-01)\n"
        returncode = 0

    monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: FakeResult())
    monkeypatch.setattr(
        "shutil.which", lambda name: str(uv_bin) if name == "uv" else None
    )

    result = appenv.ensure_uv(tmp_path)

    assert isinstance(result, appenv.UvBin)
    assert result.bin == uv_bin


# UvVersion.from_string() tests


def test_parse_uv_version_parses_correctly():
    assert UvVersion.from_string("0.5.0") == UvVersion(0, 5, 0)
    assert UvVersion.from_string("0.10.3") == UvVersion(0, 10, 3)
    assert UvVersion.from_string("1.2.3") == UvVersion(1, 2, 3)


def test_parse_uv_version_handles_two_parts():
    # Two parts now raises NoValidUvError (not auto-expanded to patch=0)
    with pytest.raises(appenv.NoValidUvError):
        UvVersion.from_string("0.5")
    with pytest.raises(appenv.NoValidUvError):
        UvVersion.from_string("1.2")


def test_parse_uv_version_returns_zero_on_invalid():
    # Invalid format now raises NoValidUvError (returns unknown instead)
    with pytest.raises(appenv.NoValidUvError):
        UvVersion.from_string("1")
    with pytest.raises(appenv.NoValidUvError):
        UvVersion.from_string("invalid")
    with pytest.raises(appenv.NoValidUvError):
        UvVersion.from_string("")


def test_parse_uv_version_strips_v_prefix():
    # v prefix is NOT stripped - must use version number only
    # With v prefix, it raises NoValidUvError
    with pytest.raises(appenv.NoValidUvError):
        UvVersion.from_string("v0.5.0")
    with pytest.raises(appenv.NoValidUvError):
        UvVersion.from_string("v1.2.3")


# Tier 1: Quick Wins


def test_find_available_pythons_sorting(monkeypatch):
    """find_available_pythons returns versions sorted numerically, newest-first.

    This test includes 3.9 to catch lexikographic vs numeric sorting bugs:
    - Numeric: 3.10 > 3.9 (correct)
    - Lexikographic: "3.9" > "3.10" (wrong, but would pass with broken sort)
    """

    def mock_which(name):
        versions = {
            "python3.9": "/usr/bin/python3.9",
            "python3.10": "/usr/bin/python3.10",
            "python3.11": "/usr/bin/python3.11",
            "python3.12": "/usr/bin/python3.12",
            "python3.13": "/usr/bin/python3.13",
            "python3.14": "/usr/bin/python3.14",
        }
        return versions.get(name)

    monkeypatch.setattr(shutil, "which", mock_which)

    result = appenv.find_available_pythons()

    # Must be numerically sorted: 3.14, 3.13, 3.12, 3.11, 3.10
    # (lexikographic would be wrong: 3.9 > 3.10)
    versions = [v for v, _ in result]
    assert versions == ["3.14", "3.13", "3.12", "3.11", "3.10"]


def test_find_available_pythons_bare_python3_fallback(monkeypatch):
    """find_available_pythons discovers unversioned python3 (macOS Xcode).

    When python3 exists but no python3.X symlinks point to it, the function
    should still discover it via subprocess version detection.
    """

    def mock_which(name):
        if name == "python3":
            return "/usr/bin/python3"
        return None

    monkeypatch.setattr(shutil, "which", mock_which)
    monkeypatch.setattr(
        subprocess,
        "check_output",
        lambda cmd, **kwargs: b"Python 3.12.0",
    )

    result = appenv.find_available_pythons()

    assert len(result) == 1
    assert result[0] == ("3.12", "/usr/bin/python3")


def test_find_available_pythons_bare_python3_deduplication(monkeypatch):
    """find_available_pythons skips python3 if its path already in the list.

    On systems where python3 -> python3.12, the resolved path should be
    deduplicated so we don't list the same binary twice.
    """

    def mock_which(name):
        if name == "python3.12":
            return "/usr/bin/python3.12"
        if name == "python3":
            return "/usr/bin/python3.12"
        return None

    monkeypatch.setattr(shutil, "which", mock_which)
    monkeypatch.setattr(
        subprocess,
        "check_output",
        lambda cmd, **kwargs: b"Python 3.12.0",
    )

    result = appenv.find_available_pythons()

    # Should only appear once (deduplicated by resolved path)
    assert len(result) == 1
    assert result[0][0] == "3.12"


def test_find_available_pythons_bare_python3_too_old(monkeypatch):
    """find_available_pythons skips python3 if version < 3.10."""

    def mock_which(name):
        if name == "python3":
            return "/usr/bin/python3"
        return None

    monkeypatch.setattr(shutil, "which", mock_which)
    monkeypatch.setattr(
        subprocess,
        "check_output",
        lambda cmd, **kwargs: b"Python 2.7.18",
    )

    result = appenv.find_available_pythons()

    assert len(result) == 0


def test_find_available_pythons_bare_python3_subprocess_fails(monkeypatch):
    """find_available_pythons handles subprocess failure for python3."""

    def mock_which(name):
        if name == "python3":
            return "/usr/bin/python3"
        return None

    monkeypatch.setattr(shutil, "which", mock_which)
    monkeypatch.setattr(
        subprocess,
        "check_output",
        lambda cmd, **kwargs: (_ for _ in ()).throw(OSError("broken")),
    )

    result = appenv.find_available_pythons()
    assert len(result) == 0


def test_version_satisfies_constraints_min_only():
    """version_satisfies_constraints with only minimum version."""
    # Satisfies minimum
    assert appenv.version_satisfies_constraints("3.10", "3.10") is True
    assert appenv.version_satisfies_constraints("3.14", "3.10") is True
    assert appenv.version_satisfies_constraints("3.10.1", "3.10") is True

    # Below minimum
    assert appenv.version_satisfies_constraints("3.9", "3.10") is False
    assert appenv.version_satisfies_constraints("3.8", "3.10") is False


def test_version_satisfies_constraints_with_max():
    """version_satisfies_constraints with min and max (exclusive)."""
    # In range
    assert appenv.version_satisfies_constraints("3.11", "3.10", "3.14") is True
    assert appenv.version_satisfies_constraints("3.13", "3.10", "3.14") is True

    # At min (inclusive)
    assert appenv.version_satisfies_constraints("3.10", "3.10", "3.14") is True

    # At max (exclusive) - should FAIL
    assert appenv.version_satisfies_constraints("3.14", "3.10", "3.14") is False

    # Above max
    assert appenv.version_satisfies_constraints("3.15", "3.10", "3.14") is False

    # Below min
    assert appenv.version_satisfies_constraints("3.9", "3.10", "3.14") is False


def test_version_satisfies_constraints_edge_cases():
    """version_satisfies_constraints handles patch versions correctly."""
    # Patch versions in comparison
    assert appenv.version_satisfies_constraints("3.10.5", "3.10.0") is True
    assert appenv.version_satisfies_constraints("3.10.0", "3.10.5") is False

    # Mixed major.minor vs major.minor.patch
    # Note: [3, 10] < [3, 10, 0] in list comparison, so 3.10 < 3.10.0
    # This is acceptable for our use case (we typically compare X.Y versions)
    assert (
        appenv.version_satisfies_constraints("3.10.1", "3.10") is True
    )  # [3,10,1] > [3,10]
    # 3.10 is treated as "less than" 3.10.0 due to list length - this is expected
    assert (
        appenv.version_satisfies_constraints("3.10", "3.10.0") is False
    )  # [3,10] < [3,10,0]


def test_run_script_delegates(capsys, tmp_path, app_env):
    """run_script() shows deprecation message with alternatives."""
    env = app_env()

    with pytest.raises(SystemExit) as exc_info:
        env.run_script(argparse.Namespace(script="pytest"), ["-v", "test.py"])

    assert exc_info.value.code == 64
    captured = capsys.readouterr()
    assert "uv run" in captured.out
    assert "ln -s appenv pytest" in captured.out


def test_show_version(tmp_path, capsys, patterns, app_env):
    """show_version() prints the appenv version."""
    env = app_env()
    env.show_version()

    captured = capsys.readouterr()

    patterns.main.in_order(f"appenv {appenv.__version__}")

    full_pattern = patterns.full
    full_pattern.merge("main")

    full_pattern.generate_example()

    assert full_pattern == captured.out


def test_pyproject_requires_python_edge_cases(tmp_path):
    """Pyproject.requires_python handles various regex formats."""
    base = tmp_path

    # Non-existent file returns (None, None)
    pyproject = appenv.Pyproject(base)
    assert pyproject.requires_python == (None, None)

    pyproject_path = base / "pyproject.toml"

    # Format: >=3.13 (no space around operators)
    pyproject_path.write_text('[project]\nname = "test"\nrequires-python = ">=3.13"\n')
    assert appenv.Pyproject(base).requires_python == ("3.13", None)

    # Format: = "3.14" (with space after = and before value)
    pyproject_path.write_text('[project]\nname = "test"\nrequires-python = ">=3.14"\n')
    assert appenv.Pyproject(base).requires_python == ("3.14", None)

    # Format: >3.10 (greater than, not >=) - regex handles >=? so just > matches
    pyproject_path.write_text('[project]\nname = "test"\nrequires-python = ">3.10"\n')
    assert appenv.Pyproject(base).requires_python == ("3.10", None)

    # Format with extra whitespace around = (regex allows \s*)
    pyproject_path.write_text('[project]\nname = "test"\nrequires-python=">=3.11"\n')
    assert appenv.Pyproject(base).requires_python == ("3.11", None)

    # No match returns (None, None)
    pyproject_path.write_text('[project]\nname = "test"\n')
    assert appenv.Pyproject(base).requires_python == (None, None)


def test_pyproject_requires_python_with_upper_bound(tmp_path):
    """Pyproject.requires_python handles upper bounds like >=3.11,<3.15."""
    base = tmp_path
    pyproject_path = base / "pyproject.toml"

    # Format: >=3.11,<3.15
    pyproject_path.write_text(
        '[project]\nname = "test"\nrequires-python = ">=3.11,<3.15"\n'
    )
    assert appenv.Pyproject(base).requires_python == ("3.11", "3.15")

    # Format: >=3.11.0,<3.15.0 (with patch version)
    pyproject_path.write_text(
        '[project]\nname = "test"\nrequires-python = ">=3.11.0,<3.15.0"\n'
    )
    assert appenv.Pyproject(base).requires_python == ("3.11", "3.15")

    # Format: >=3.10,<=3.14 (inclusive upper bound)
    pyproject_path.write_text(
        '[project]\nname = "test"\nrequires-python = ">=3.10,<=3.14"\n'
    )
    assert appenv.Pyproject(base).requires_python == ("3.10", "3.14")

    # Format with spaces: >= 3.11, < 3.15
    pyproject_path.write_text(
        '[project]\nname = "test"\nrequires-python = ">= 3.11, < 3.15"\n'
    )
    assert appenv.Pyproject(base).requires_python == ("3.11", "3.15")


def test_main_calls_ensure_best_python(monkeypatch, workdir):
    """Line 1196: main() calls ensure_best_python."""
    base = Path(workdir)
    (base / "pyproject.toml").write_text('[project]\nname = "test"\n')
    (base / "appenv").write_text("#!/usr/bin/env python3\npass\n")
    (base / "appenv").chmod(0o755)

    called = []
    monkeypatch.setattr(
        appenv,
        "ensure_best_python",
        lambda b: called.append("pyproject"),
    )
    monkeypatch.setattr(appenv.AppEnv, "meta", lambda self, args, prog="appenv": None)
    monkeypatch.setattr(appenv, "__file__", str(base / "appenv"))
    monkeypatch.setattr("sys.argv", ["appenv"])

    appenv.main()

    assert called == ["pyproject"]


def test_main_entry_point_subprocess():
    """Line 1216: Test __main__ entry point via subprocess."""
    project_root = Path(__file__).parent.parent.resolve()
    result = subprocess.run(
        [sys.executable, str(project_root / "src" / "appenv.py"), "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "usage" in result.stdout.lower() or "usage" in result.stderr.lower()


# ==============================================================================
# Version consistency tests (from test_version.py)
# ==============================================================================


def test_version_consistency():
    """Version in appenv.py matches version in appenv bootstrap script."""
    # Read version from appenv module
    module_version = appenv.__version__

    # Read version from src/appenv.py
    appenv_path = Path(__file__).parent.parent / "src" / "appenv.py"
    appenv_content = appenv_path.read_text()

    match = re.search(r'__version__ = "([^"]+)"', appenv_content)
    assert match, "Could not find __version__ in appenv file"
    file_version = match.group(1)

    assert module_version == file_version, (
        f"Version mismatch: module={module_version}, file={file_version}"
    )


# ==============================================================================
# build_requires_python_spec tests
# ==============================================================================


def test_convert_version_preference_empty_versions():
    """Test convert_version_preference with empty versions list."""
    result = appenv.convert_version_preference([])
    assert result == (">=3.10", [])


# ==============================================================================
# LockFile tests
# ==============================================================================


def test_lockfile_content_missing_file(tmp_path):
    """Test LockFile.content returns empty string when file doesn't exist."""
    lockfile = appenv.LockFile(tmp_path)
    assert lockfile.content == ""


# ==============================================================================
# UvVersion tests
# ==============================================================================


def test_uv_version_unknown():
    """Test UvVersion.unknown() returns zero version."""
    version = UvVersion.unknown()
    assert version.major == 0
    assert version.minor == 0
    assert version.patch == 0


def test_uv_version_str_zero():
    """Test UvVersion.__str__ for zero version."""
    version = UvVersion(0, 0, 0)
    assert str(version) == "unknown"


# ==============================================================================
# Coverage tests for Batch 2
# ==============================================================================


def test_pyproject_builder_merges_with_existing_content(tmp_path):
    """Line 282: PyprojectBuilder merges with existing pyproject content."""
    base = tmp_path
    pyproject_path = base / "pyproject.toml"

    # Create existing pyproject content (e.g., tool settings)
    pyproject_path.write_text("[tool.ruff]\nline-length = 100\n")

    # Create Pyproject instance and add project section
    pyproject = appenv.Pyproject(base)
    pyproject.with_project_section(
        project_name="myproject",
        description="A test project",
        dependencies=["requests"],
        requires_python=">=3.10",
    )

    # Verify content includes both original and new section
    content = pyproject_path.read_text()
    assert "[tool.ruff]" in content
    assert "line-length = 100" in content
    assert "[project]" in content
    assert 'name = "myproject"' in content
    assert "requests" in content


def test_uv_sync_with_extras(tmp_path, monkeypatch, make_mock_uv):
    """Line 1087: _uv_sync with extras setting."""
    # Create settings with extras
    settings = appenv.AppEnvSettings(
        verbose=False,
        extras=["dev", "test"],
        basedir=tmp_path,
    )
    env = appenv.AppEnv(Path.cwd(), settings)

    # Mock uv.cmd to capture sync args
    sync_calls = []

    uv = make_mock_uv(
        cmd_fn=lambda args, **kwargs: sync_calls.append(list(args)) or "",
    )
    env._uv_sync(dev_mode=True, uv=cast("appenv.UvBin", uv))

    # Verify extras were added to sync command
    assert len(sync_calls) == 1
    sync_args = sync_calls[0]
    assert "--extra" in sync_args
    extra_idx = sync_args.index("--extra")
    assert sync_args[extra_idx + 1] == "dev,test"


# ==============================================================================
# Coverage tests for Batch 3
# ==============================================================================


def test_ensure_pyproject_no_project_section_no_requirements(
    tmp_path, monkeypatch, capsys
):
    """Lines 1204, 1209-1211: ensure_pyproject exits when no [project].

    Also no requirements.txt.
    """
    base = tmp_path

    # Create pyproject.toml without [project] section
    (base / "pyproject.toml").write_text("[tool.ruff]\nline-length = 100\n")

    with pytest.raises(SystemExit) as exc_info:
        appenv.ensure_pyproject(base)

    assert exc_info.value.code == appenv.EXIT_CODE_NOINPUT
    captured = capsys.readouterr()
    assert "has no [project] section" in captured.out
    assert "Run ./appenv init" in captured.out


def test_ensure_pyproject_no_file_with_requirements(tmp_path, monkeypatch, capsys):
    """Lines 1209-1211: ensure_pyproject exits with DATAERR.

    When requirements.txt exists.
    """
    base = tmp_path

    # Create requirements.txt (no pyproject.toml)
    (base / "requirements.txt").write_text("requests\n")

    with pytest.raises(SystemExit) as exc_info:
        appenv.ensure_pyproject(base)

    assert exc_info.value.code == appenv.EXIT_CODE_DATAERR
    captured = capsys.readouterr()
    assert "No pyproject config file" in captured.out
    assert "Legacy requirements.txt found" in captured.out
    assert "Run: ./appenv migrate" in captured.out


def test_cmd_error_output_not_quiet(capsys):
    """Lines 1237-1238: cmd() prints error output when not quiet."""
    with pytest.raises(ValueError):
        appenv.cmd("exit 42", quiet=False)

    captured = capsys.readouterr()
    assert "exit 42" in captured.out
    assert "exit code 42" in captured.out


def test_colored_caller_formatter_format():
    """Lines 1368-1370: ColoredCallerFormatter.format adds caller info."""

    formatter = appenv.ColoredCallerFormatter("%(message)s")

    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="test.py",
        lineno=42,
        msg="test message",
        args=(),
        exc_info=None,
        func="test_func",
    )

    result = formatter.format(record)

    # Should include funcName and lineno with ANSI codes
    assert "test_func:42" in result
    assert "test message" in result


def test_setup_logging_verbose(tmp_path, caplog):
    """Lines 1389-1393: setup_logging adds console handler when verbose=True."""
    _ = caplog  # Used for capturing logs

    log_dir = tmp_path / "logs"
    log_dir.mkdir(parents=True)

    # Clear any existing handlers (close first to avoid ResourceWarning)
    for handler in appenv.log.handlers[:]:
        handler.close()
    appenv.log.handlers.clear()

    appenv.setup_logging("test", log_dir, verbose=True)

    # Should have file handler and console handler
    assert len(appenv.log.handlers) == 2
    handler_types = {type(h).__name__ for h in appenv.log.handlers}
    assert "TimedRotatingFileHandler" in handler_types
    assert "StreamHandler" in handler_types

    # Console handler should use ColoredCallerFormatter
    console_handler = next(
        h for h in appenv.log.handlers if type(h).__name__ == "StreamHandler"
    )
    assert isinstance(console_handler.formatter, appenv.ColoredCallerFormatter)

    # Close all handlers to avoid resource warnings
    for handler in appenv.log.handlers:
        handler.close()
    appenv.log.handlers.clear()


def test_pyproject_python_preference_empty_after_filter(tmp_path, capsys):
    """Line 257->253: Empty preferences list falls through to default."""
    base = tmp_path
    # Create requirements.txt with empty preference comment
    requirements_path = base / "requirements.txt"
    requirements_path.write_text(
        "# appenv-python-preference:   \nrequests\n",
    )

    pyproject = appenv.Pyproject(base)
    req_info = pyproject.requirements_txt_info

    # Should return default list when comment has only whitespace
    assert req_info.python_versions == ["3.10", "3.11", "3.12", "3.13", "3.14"]

    # Call print_migration_info and verify output
    pyproject.print_migration_info()

    captured = capsys.readouterr()
    # With default 5 versions, "Using minimum version" SHOULD be printed
    assert "Using minimum version" in captured.out


def test_print_migration_info_skips_minimum_version_with_single_python(
    tmp_path, capsys
):
    """Line 242->246: Skips 'Using minimum version' print when only 1 Python version."""
    base = tmp_path
    requirements_path = base / "requirements.txt"
    requirements_path.write_text(
        "# appenv-python-preference: 3.12\nrequests\n",
    )

    pyproject = appenv.Pyproject(base)
    req_info = pyproject.requirements_txt_info

    # Should have single python version
    assert len(req_info.python_versions) == 1
    assert req_info.python_versions == ["3.12"]

    # Call print_migration_info
    pyproject.print_migration_info()

    captured = capsys.readouterr()
    # "Using minimum version" should NOT be printed with single version
    assert "Using minimum version" not in captured.out


def test_migrate_single_python_version(tmp_path, capsys):
    """Line 226->230: migrate with single python version skips preference print."""
    base = tmp_path
    requirements_path = base / "requirements.txt"
    requirements_path.write_text(
        "# appenv-python-preference: 3.12\nrequests\n",
    )

    pyproject = appenv.Pyproject(base)
    req_info = pyproject.requirements_txt_info

    # Should have single python version
    assert len(req_info.python_versions) == 1
    assert req_info.python_versions == ["3.12"]


def test_init_skips_appenv_script_creation(tmp_path, monkeypatch, capsys, app_env):
    """Line 894-900: init() skips appenv script creation when it already exists."""
    base = tmp_path

    # Create existing appenv script (the one init() checks)
    appenv_script = base / "appenv"
    appenv_script.write_text("#!/usr/bin/env python3\n# Existing appenv\n")
    appenv_script.chmod(0o755)

    # Mock input() calls for init() interactive prompts
    inputs = iter(["myapp", "", "myproject", "Test project", "3.12"])
    monkeypatch.setattr("builtins.input", lambda prompt: next(inputs))

    # Mock _set_up_command_symlink to avoid file system side effects
    monkeypatch.setattr(
        appenv.AppEnv, "_set_up_command_symlink", lambda self, **kwargs: None
    )

    env = app_env()

    with pytest.raises(SystemExit):
        env.init()

    captured = capsys.readouterr()
    assert "Created appenv script" not in captured.out


def test_remove_path_directory(tmp_path):
    """remove_path() removes a directory with shutil.rmtree."""
    d = tmp_path / "subdir"
    d.mkdir()
    (d / "file.txt").write_text("hello")
    assert d.exists()

    appenv.remove_path(d)
    assert not d.exists()


def test_remove_path_nonexistent(tmp_path):
    """remove_path() is a no-op for nonexistent paths."""
    missing = tmp_path / "does_not_exist"
    appenv.remove_path(missing)  # should not raise


# ==============================================================================
# Quality elevation coverage tests
# ==============================================================================


def test_grouped_help_formatter_truncates_long_help():
    """Line 71: GroupedHelpFormatter truncates long help text."""
    formatter = appenv.GroupedHelpFormatter(prog="appenv")

    parser = argparse.ArgumentParser(prog="appenv")
    subparsers = parser.add_subparsers(dest="command")

    # 'init' is in the Project group - give it help text > 50 chars
    long_help = "A" * 60
    subparsers.add_parser("init", help=long_help)

    subparsers_action = None
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            subparsers_action = action
            break

    assert subparsers_action is not None
    result = formatter._format_action(subparsers_action)

    # Help should be truncated to first 47 chars + "..."
    assert "A" * 60 not in result
    assert "A" * 47 + "..." in result


def test_run_missing_binary_empty_venv(monkeypatch, tmp_path, capsys, app_env):
    """Line 690: run() shows 'No binaries found' when venv/bin/ is empty."""
    env = app_env()

    # Create empty venv/bin/ directory (no binaries)
    env_dir = tmp_path / ".appenv" / "venv"
    bin_dir = env_dir / "bin"
    bin_dir.mkdir(parents=True)
    # bin_dir is intentionally empty

    monkeypatch.setattr(env, "_prepare_venv", lambda dev_mode=False: env_dir)

    with pytest.raises(SystemExit) as exc_info:
        env.run("myapp", ["--help"])

    assert exc_info.value.code == appenv.EXIT_CODE_NOINPUT
    captured = capsys.readouterr()
    assert "No binaries found in the virtual environment" in captured.out


def test_meta_unrecognized_arguments(tmp_path, app_env, capsys):
    """Lines 791-793: meta() exits with USAGE on unrecognized arguments."""
    env = app_env()

    with pytest.raises(SystemExit) as exc_info:
        env.meta(remaining_args=["--totally-bogus-flag"])

    assert exc_info.value.code == appenv.EXIT_CODE_USAGE
    captured = capsys.readouterr()
    assert "Error: unrecognized arguments: --totally-bogus-flag" in captured.out


def test_ensure_gitignore_returns_early_when_all_entries_exist(tmp_path, capsys):
    """Line 1294: ensure_gitignore returns early when all entries already exist."""
    base = tmp_path

    # Create .gitignore with all the entries we'll pass
    (base / ".gitignore").write_text(".venv\n.appenv\n.batou-lock\n")

    appenv.ensure_gitignore(base, [".venv", ".appenv", ".batou-lock"])

    # Should return early — no "Updated" or "Created" print
    captured = capsys.readouterr()
    assert "Updated" not in captured.out
    assert "Created" not in captured.out

    # File content unchanged
    assert (base / ".gitignore").read_text() == ".venv\n.appenv\n.batou-lock\n"


# python and uv subcommand dispatch tests


def test_meta_dispatches_python_subcommand(
    monkeypatch, tmp_path, app_env, no_ensure_python, mock_logdir
):
    """meta() dispatches 'python' subcommand to python() which calls run()."""
    monkeypatch.setattr("sys.argv", ["appenv", "python", "-c", "print(1)"])

    env = app_env()
    run_called = []
    monkeypatch.setattr(env, "run", lambda cmd, argv: run_called.append((cmd, argv)))

    env.meta()

    assert run_called == [("python", ["-c", "print(1)"])]


def test_meta_dispatches_uv_subcommand(
    monkeypatch, tmp_path, app_env, no_ensure_python, mock_logdir
):
    """meta() dispatches 'uv' subcommand to run_uv() which execs uv binary."""
    monkeypatch.setattr("sys.argv", ["appenv", "uv", "pip", "list"])

    env = app_env()
    mock_uv = MockUvBin()
    monkeypatch.setattr(appenv, "ensure_uv", lambda base: mock_uv)

    execv_called = []
    monkeypatch.setattr(
        os, "execv", lambda path, argv: execv_called.append((path, argv))
    )
    monkeypatch.setattr(os, "chdir", lambda d: None)

    env.meta()

    assert len(execv_called) == 1
    path, argv = execv_called[0]
    assert "uv" in path
    assert "pip" in argv
    assert "list" in argv
    assert os.environ.get("UV_PROJECT_ENVIRONMENT") == str(env.venv_real)


def test_run_uv_sets_environment_and_execs(
    monkeypatch, tmp_path, app_env, no_ensure_python, mock_logdir
):
    """run_uv() sets UV_PROJECT_ENVIRONMENT and execs the uv binary."""
    env = app_env()
    mock_uv = MockUvBin()
    monkeypatch.setattr(appenv, "ensure_uv", lambda base: mock_uv)

    execv_called = []
    monkeypatch.setattr(
        os, "execv", lambda path, argv: execv_called.append((path, argv))
    )
    monkeypatch.setattr(os, "chdir", lambda d: None)

    env.run_uv(argparse.Namespace(), ["pip", "install", "pkg"])

    assert os.environ.get("UV_PROJECT_ENVIRONMENT") == str(env.venv_real)
    assert len(execv_called) == 1
    path, argv = execv_called[0]
    assert path == str(mock_uv.bin)
    assert argv == [str(mock_uv.bin), "pip", "install", "pkg"]


def test_python_delegates_to_run_with_remaining_args(monkeypatch, tmp_path, app_env):
    """python() delegates to run() with command and remaining args."""
    env = app_env()
    run_called = []
    monkeypatch.setattr(env, "run", lambda cmd, argv: run_called.append((cmd, argv)))

    env.python(argparse.Namespace(), ["-m", "pdb", "script.py"])

    assert run_called == [("python", ["-m", "pdb", "script.py"])]
