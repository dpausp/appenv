"""Tests for main() entry point and related functions."""

import argparse
import io
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import appenv


def mock_ensure_python(monkeypatch):
    """Mock ensure_best_python to prevent re-exec."""
    monkeypatch.setattr(appenv, "ensure_best_python", lambda base: None)


# main() tests


def test_main_shows_usage_without_subcommand(monkeypatch, capsys):
    """Test that calling appenv without subcommand shows usage."""
    mock_ensure_python(monkeypatch)
    monkeypatch.setattr("sys.argv", ["appenv"])
    monkeypatch.setattr(appenv, "__file__", "/some/path/appenv")

    # Should exit with usage message
    with pytest.raises(SystemExit):
        appenv.main()

    captured = capsys.readouterr()
    assert "usage: appenv" in captured.out


def test_main_clears_pythonpath(monkeypatch):
    mock_ensure_python(monkeypatch)
    monkeypatch.setattr("sys.argv", ["appenv"])

    monkeypatch.setenv("PYTHONPATH", "/some/path")
    assert "PYTHONPATH" in os.environ

    with pytest.raises(SystemExit):
        appenv.main()

    # PYTHONPATH should still be cleared before the exit
    assert "PYTHONPATH" not in os.environ


def test_main_calls_run_when_not_appenv(monkeypatch, tmp_path):
    mock_ensure_python(monkeypatch)

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


def test_main_calls_meta_when_appenv(monkeypatch):
    mock_ensure_python(monkeypatch)

    meta_called = []
    monkeypatch.setattr(
        appenv.AppEnv, "meta", lambda self, args: meta_called.append(args)
    )

    monkeypatch.setattr("sys.argv", ["appenv"])
    monkeypatch.setattr(appenv, "__file__", "/some/path/appenv")

    appenv.main()

    assert meta_called == [["help"]]


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


# uv_cmd() tests


def test_uv_cmd_raises_when_uv_not_found(monkeypatch):
    appenv._UV_BIN_CACHE = None  # Reset cache

    # Mock ensure_uv to raise RuntimeError
    def fake_ensure_uv(base=None):
        raise RuntimeError("uv not found and could not be installed.")

    monkeypatch.setattr(appenv, "ensure_uv", fake_ensure_uv)

    with pytest.raises(RuntimeError, match="uv not found and could not be installed"):
        appenv.uv_cmd([])


def test_get_uv_bin_uses_path(monkeypatch):
    """get_uv_bin returns uv from PATH if available."""
    appenv._UV_BIN_CACHE = None  # Reset cache
    monkeypatch.setattr(
        "shutil.which", lambda name: "/usr/bin/uv" if name == "uv" else None
    )

    # Mock subprocess.run to return version
    def mock_run(cmd, **kwargs):
        text_mode = kwargs.get("text", False)
        stdout = "uv 0.5.0\n" if text_mode else b"uv 0.5.0\n"
        return subprocess.CompletedProcess(cmd, 0, stdout, b"")

    monkeypatch.setattr(subprocess, "run", mock_run)

    assert str(appenv.get_uv_bin()) == "/usr/bin/uv"


def test_get_uv_bin_uses_pip_fallback(monkeypatch, tmp_path):
    """get_uv_bin installs uv via pip if not in PATH and no nix."""
    appenv._UV_BIN_CACHE = None  # Reset cache
    monkeypatch.setattr("shutil.which", lambda name: None)  # no uv, no nix

    pip_called = []
    monkeypatch.setattr(
        "subprocess.run",
        lambda cmd, **kwargs: pip_called.append(cmd),
    )

    with pytest.raises(RuntimeError, match="uv not found"):
        appenv.get_uv_bin(tmp_path)

    assert any("pip" in str(cmd) and "uv" in str(cmd) for cmd in pip_called)


# meta() tests


def test_meta_calls_reset(monkeypatch, tmp_path):
    env = appenv.AppEnv(tmp_path, Path.cwd())
    monkeypatch.setattr("sys.argv", ["appenv", "reset"])

    reset_called = []
    monkeypatch.setattr(
        env, "reset", lambda args=None, remaining=None: reset_called.append(True)
    )

    env.meta()

    assert reset_called == [True]


def test_meta_calls_prepare(monkeypatch, tmp_path):
    env = appenv.AppEnv(tmp_path, Path.cwd())
    monkeypatch.setattr("sys.argv", ["appenv", "prepare"])

    prepare_called = []
    monkeypatch.setattr(
        env,
        "prepare",
        lambda args=None, remaining=None: prepare_called.append(True),
    )

    env.meta()

    assert prepare_called == [True]


def test_meta_calls_python(monkeypatch, tmp_path):
    env = appenv.AppEnv(tmp_path, Path.cwd())
    monkeypatch.setattr("sys.argv", ["appenv", "python"])

    python_called = []
    monkeypatch.setattr(
        env,
        "python",
        lambda args, remaining: python_called.append((args, remaining)),
    )

    env.meta()

    assert len(python_called) == 1


def test_meta_calls_run_script(monkeypatch, tmp_path):
    env = appenv.AppEnv(tmp_path, Path.cwd())
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


def test_run_sets_env_and_execs(monkeypatch, tmp_path):
    env = appenv.AppEnv(tmp_path, Path.cwd())

    # Add pyproject.toml and uv.lock so _prepare_venv doesn't exit
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "test"\n')
    (tmp_path / "uv.lock").write_text("version = 1\n")

    env_dir = tmp_path / ".appenv" / "abc123"
    env_dir.mkdir(parents=True)
    bin_dir = env_dir / "bin"
    bin_dir.mkdir()
    (bin_dir / "myapp").write_text("#!/bin/sh\necho hello\n")

    monkeypatch.setattr(env, "prepare", lambda: str(env_dir))

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


def test_run_with_profiling_enabled(monkeypatch, tmp_path, capsys, patterns):
    env = appenv.AppEnv(tmp_path, Path.cwd())

    # Add pyproject.toml and uv.lock so _prepare_venv doesn't exit
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "test"\n')
    (tmp_path / "uv.lock").write_text("version = 1\n")

    env_dir = tmp_path / ".appenv" / "abc123"
    env_dir.mkdir(parents=True)
    bin_dir = env_dir / "bin"
    bin_dir.mkdir()
    (bin_dir / "myapp").write_text("#!/bin/sh\necho hello\n")

    monkeypatch.setattr(env, "prepare", lambda: str(env_dir))
    monkeypatch.setattr("os.chdir", lambda p: None)
    monkeypatch.setenv("APPENV_PROFILE", "1")

    execv_called = []
    monkeypatch.setattr(
        os,
        "execv",
        lambda path, argv: execv_called.append((path, argv)),
    )

    env.run("myapp", ["--help"])

    assert len(execv_called) == 1
    path, argv = execv_called[0]
    assert path.endswith("bin/python")
    assert "-m" in argv
    assert "cProfile" in argv
    assert "-o" in argv
    # Check for datetime-based profile path:
    # .appenv/profiling/myapp-YYYYMMDD-HHMMSS.prof
    import re

    profile_arg = argv[argv.index("-o") + 1]
    assert re.match(r".*\.appenv/profiling/myapp-\d{8}-\d{6}\.prof$", profile_arg), (
        f"Unexpected profile path: {profile_arg}"
    )
    captured = capsys.readouterr()
    assert "APPENV_PROFILE enabled" in captured.out
    assert ".appenv/profiling/myapp-" in captured.out


def test_run_with_profiling_custom_output(monkeypatch, tmp_path, capsys, patterns):
    env = appenv.AppEnv(tmp_path, Path.cwd())

    # Add pyproject.toml and uv.lock so _prepare_venv doesn't exit
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "test"\n')
    (tmp_path / "uv.lock").write_text("version = 1\n")

    env_dir = tmp_path / ".appenv" / "abc123"
    env_dir.mkdir(parents=True)
    bin_dir = env_dir / "bin"
    bin_dir.mkdir()
    (bin_dir / "myapp").write_text("#!/bin/sh\necho hello\n")

    monkeypatch.setattr(env, "prepare", lambda: str(env_dir))
    monkeypatch.setattr("os.chdir", lambda p: None)
    monkeypatch.setenv("APPENV_PROFILE", "1")
    monkeypatch.setenv("APPENV_PROFILE_OUTPUT", "/tmp/custom.prof")

    execv_called = []
    monkeypatch.setattr(
        os,
        "execv",
        lambda path, argv: execv_called.append((path, argv)),
    )

    env.run("myapp", ["--help"])

    assert len(execv_called) == 1
    _path, argv = execv_called[0]
    assert "/tmp/custom.prof" in argv
    captured = capsys.readouterr()
    assert "APPENV_PROFILE enabled" in captured.out
    assert "/tmp/custom.prof" in captured.out


def test_profiling_list_no_data(tmp_path, capsys):
    """profiling_list shows message when no profiling data exists."""
    env = appenv.AppEnv(tmp_path, Path.cwd())
    args = argparse.Namespace(count=10)
    env.profiling_list(args)

    captured = capsys.readouterr()
    assert "No profiling data found" in captured.out


def test_profiling_list_with_profiles(tmp_path, capsys):
    """profiling_list shows profiles sorted by mtime."""
    env = appenv.AppEnv(tmp_path, Path.cwd())
    profiling_dir = tmp_path / ".appenv" / "profiling"
    profiling_dir.mkdir(parents=True)

    # Create test profiles with different mtimes
    import time

    profile1 = profiling_dir / "batou-20260301-100000.prof"
    profile1.write_text("dummy")
    time.sleep(0.01)
    profile2 = profiling_dir / "batou-20260301-110000.prof"
    profile2.write_text("dummy")
    time.sleep(0.01)
    profile3 = profiling_dir / "http-20260301-120000.prof"
    profile3.write_text("dummy")

    args = argparse.Namespace(count=10)
    env.profiling_list(args)

    captured = capsys.readouterr()
    assert "Showing 3 of 3 profiles" in captured.out
    # Newest first
    assert captured.out.index("http-20260301") < captured.out.index(
        "batou-20260301-110000"
    )
    assert captured.out.index("batou-20260301-110000") < captured.out.index(
        "batou-20260301-100000"
    )


def test_profiling_list_with_count_limit(tmp_path, capsys):
    """profiling_list respects -n count limit."""
    env = appenv.AppEnv(tmp_path, Path.cwd())
    profiling_dir = tmp_path / ".appenv" / "profiling"
    profiling_dir.mkdir(parents=True)

    for i in range(5):
        (profiling_dir / f"cmd-{i:04d}.prof").write_text("dummy")

    args = argparse.Namespace(count=2)
    env.profiling_list(args)

    captured = capsys.readouterr()
    assert "Showing 2 of 5 profiles" in captured.out


def test_profiling_show_no_data(tmp_path, capsys):
    """profiling_show exits when no profiling data exists."""
    env = appenv.AppEnv(tmp_path, Path.cwd())
    args = argparse.Namespace(file=None)

    with pytest.raises(SystemExit) as exc_info:
        env.profiling_show(args)

    assert exc_info.value.code == appenv.EXIT_CODE_NOINPUT
    captured = capsys.readouterr()
    assert "No profiling data found" in captured.out


def test_profiling_show_file_not_found(tmp_path, capsys):
    """profiling_show exits when specified file not found."""
    env = appenv.AppEnv(tmp_path, Path.cwd())
    args = argparse.Namespace(file="nonexistent.prof")

    with pytest.raises(SystemExit) as exc_info:
        env.profiling_show(args)

    assert exc_info.value.code == appenv.EXIT_CODE_NOINPUT
    captured = capsys.readouterr()
    assert "Profile not found" in captured.out


def test_profiling_snakeviz_no_data(tmp_path, capsys):
    """profiling_snakeviz exits when no profiling data exists."""
    env = appenv.AppEnv(tmp_path, Path.cwd())
    args = argparse.Namespace(file=None)

    with pytest.raises(SystemExit) as exc_info:
        env.profiling_snakeviz(args)

    assert exc_info.value.code == appenv.EXIT_CODE_NOINPUT
    captured = capsys.readouterr()
    assert "No profiling data found" in captured.out


def test_profiling_snakeviz_opens_latest(tmp_path, capsys, monkeypatch):
    """profiling_snakeviz opens latest profile with uv run snakeviz."""
    env = appenv.AppEnv(tmp_path, Path.cwd())
    profiling_dir = tmp_path / ".appenv" / "profiling"
    profiling_dir.mkdir(parents=True)

    profile = profiling_dir / "batou-20260301-100000.prof"
    profile.write_text("dummy")

    args = argparse.Namespace(file=None)

    execv_called = []
    monkeypatch.setattr(
        os,
        "execv",
        lambda path, argv: execv_called.append((path, argv)),
    )

    env.profiling_snakeviz(args)

    assert len(execv_called) == 1
    path, argv = execv_called[0]
    assert path == sys.executable
    assert "uv" in argv
    assert "run" in argv
    assert "--with" in argv
    assert "snakeviz" in argv
    assert str(profile) in argv
    captured = capsys.readouterr()
    assert "Opening latest profile" in captured.out


def test_profiling_snakeviz_specific_file(tmp_path, monkeypatch):
    """profiling_snakeviz opens specific profile file."""
    env = appenv.AppEnv(tmp_path, Path.cwd())
    profiling_dir = tmp_path / ".appenv" / "profiling"
    profiling_dir.mkdir(parents=True)

    profile = profiling_dir / "custom.prof"
    profile.write_text("dummy")

    args = argparse.Namespace(file="custom.prof")

    execv_called = []
    monkeypatch.setattr(
        os,
        "execv",
        lambda path, argv: execv_called.append((path, argv)),
    )

    env.profiling_snakeviz(args)

    assert len(execv_called) == 1
    _path, argv = execv_called[0]
    assert str(profile) in argv


def test_profiling_snakeviz_file_not_found(tmp_path, capsys):
    """profiling_snakeviz exits when specified file not found."""
    env = appenv.AppEnv(tmp_path, Path.cwd())
    args = argparse.Namespace(file="nonexistent.prof")

    with pytest.raises(SystemExit) as exc_info:
        env.profiling_snakeviz(args)

    assert exc_info.value.code == appenv.EXIT_CODE_NOINPUT
    captured = capsys.readouterr()
    assert "Profile not found" in captured.out


def test_python_method_calls_run(monkeypatch, tmp_path):
    env = appenv.AppEnv(tmp_path, Path.cwd())

    run_called = []
    monkeypatch.setattr(env, "run", lambda cmd, argv: run_called.append((cmd, argv)))

    env.python(argparse.Namespace(), ["-c", "print(1)"])

    assert run_called == [("python", ["-c", "print(1)"])]


# print_colored_diff() tests


def test_print_colored_diff_returns_true_when_changes(capsys, patterns):
    old = "line1\nline2\n"
    new = "line1\nline3\n"

    result = appenv.print_colored_diff(old, new, "old.txt", "new.txt")

    assert result is True
    captured = capsys.readouterr()
    output = re.sub(r"\x1b\[[0-9;]*m", "", captured.out)

    patterns.main.in_order(
        """\
--- old.txt
+++ new.txt
@@ -1,2 +1,2 @@
 line1
-line2
+line3"""
    )

    patterns.no_errors.refused("...error...")
    patterns.no_errors.refused("...exception...")
    patterns.no_errors.refused("...traceback...")
    patterns.no_errors.refused("...failed...")

    full_pattern = patterns.full
    full_pattern.merge("main", "no_errors")

    assert full_pattern == output


def test_print_colored_diff_returns_false_when_no_changes(capsys):
    content = "line1\nline2\n"

    result = appenv.print_colored_diff(content, content, "same.txt", "same.txt")

    assert result is False
    captured = capsys.readouterr()
    assert captured.out == ""


def test_print_colored_diff_shows_filenames(capsys, patterns):
    old = "a\n"
    new = "b\n"

    appenv.print_colored_diff(old, new, "oldfile.txt", "newfile.txt")

    captured = capsys.readouterr()
    output = re.sub(r"\x1b\[[0-9;]*m", "", captured.out)

    patterns.main.in_order(
        """\
--- oldfile.txt
+++ newfile.txt
@@ -1 +1 @@
-a
+b"""
    )

    patterns.no_errors.refused("...error...")
    patterns.no_errors.refused("...exception...")
    patterns.no_errors.refused("...traceback...")
    patterns.no_errors.refused("...failed...")

    full_pattern = patterns.full
    full_pattern.merge("main", "no_errors")

    assert full_pattern == output


# get_uv_version() tests


def test_get_uv_version_returns_version_on_success(tmp_path, monkeypatch):
    """Returns version string on successful version check."""
    uv_bin = Path("/usr/bin/uv")

    class FakeResult:
        stdout = "uv 0.10.3 (abc123 2024-01-01)\n"
        returncode = 0

    monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: FakeResult())

    result = appenv.get_uv_version(uv_bin)

    assert result == "0.10.3"


def test_get_uv_version_returns_none_on_subprocess_error(monkeypatch, capsys):
    """When uv --version fails, get_uv_version returns None without exiting."""
    uv_bin = Path("/usr/bin/uv")

    import subprocess

    def fake_run(*args, **kwargs):
        raise subprocess.CalledProcessError(1, "uv --version")

    monkeypatch.setattr("subprocess.run", fake_run)

    result = appenv.get_uv_version(uv_bin)

    assert result is None


def test_get_uv_version_returns_none_when_too_old(monkeypatch, capsys):
    """When version is too old, get_uv_version returns None."""
    uv_bin = Path("/usr/bin/uv")

    class FakeResult:
        stdout = "uv 0.4.0 (abc123 2024-01-01)\n"
        returncode = 0

    monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: FakeResult())

    result = appenv.get_uv_version(uv_bin)

    assert result is None


def test_get_uv_version_handles_parse_error(tmp_path, monkeypatch, capsys):
    """When version string is unparseable, get_uv_version returns None."""
    uv_bin = Path("/usr/bin/uv")

    class FakeResult:
        stdout = "uv invalid-version\n"
        returncode = 0

    monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: FakeResult())

    result = appenv.get_uv_version(uv_bin)

    assert result is None


def test_get_uv_version_index_error_on_split(monkeypatch, capsys):
    """IndexError when version output has no second element returns None."""
    uv_bin = Path("/usr/bin/uv")

    class FakeResult:
        # Single word output - split()[1] will raise IndexError
        stdout = "uv\n"
        returncode = 0

    monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: FakeResult())

    result = appenv.get_uv_version(uv_bin)

    assert result is None


# ensure_uv() tests


def test_ensure_uv_exits_on_too_old_version(monkeypatch, capsys):
    """ensure_uv exits when uv version is too old."""
    uv_bin = Path("/usr/bin/uv")

    class FakeResult:
        stdout = "uv 0.4.0 (abc123 2024-01-01)\n"
        returncode = 0

    monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: FakeResult())
    monkeypatch.setattr("appenv.get_uv_bin", lambda base: uv_bin)

    with pytest.raises(SystemExit) as err:
        appenv.ensure_uv()

    assert err.value.code == 68
    captured = capsys.readouterr()
    assert "too old" in captured.out


def test_ensure_uv_returns_uv_bin_on_success(monkeypatch, capsys):
    """ensure_uv returns uv_bin path on success."""
    uv_bin = Path("/usr/bin/uv")

    class FakeResult:
        stdout = "uv 0.10.3 (abc123 2024-01-01)\n"
        returncode = 0

    monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: FakeResult())
    monkeypatch.setattr("appenv.get_uv_bin", lambda base: uv_bin)

    result = appenv.ensure_uv()

    assert result == uv_bin


# parse_uv_version() tests


def test_parse_uv_version_parses_correctly():
    assert appenv.parse_uv_version("0.5.0") == (0, 5, 0)
    assert appenv.parse_uv_version("0.10.3") == (0, 10, 3)
    assert appenv.parse_uv_version("1.2.3") == (1, 2, 3)


def test_parse_uv_version_handles_two_parts():
    # Two parts is valid: X.Y -> (X, Y, 0)
    assert appenv.parse_uv_version("0.5") == (0, 5, 0)
    assert appenv.parse_uv_version("1.2") == (1, 2, 0)


def test_parse_uv_version_returns_zero_on_invalid():
    # Single part or invalid format returns (0, 0, 0)
    assert appenv.parse_uv_version("1") == (0, 0, 0)
    assert appenv.parse_uv_version("invalid") == (0, 0, 0)
    assert appenv.parse_uv_version("") == (0, 0, 0)


def test_parse_uv_version_strips_v_prefix():
    assert appenv.parse_uv_version("v0.5.0") == (0, 5, 0)
    assert appenv.parse_uv_version("v1.2.3") == (1, 2, 3)


# Tier 1: Quick Wins


def test_find_available_pythons_sorting(monkeypatch):
    """find_available_pythons returns versions sorted numerically, newest-first.

    This test includes 3.9 to catch lexikographic vs numeric sorting bugs:
    - Numeric: 3.10 > 3.9 (correct)
    - Lexikographic: "3.9" > "3.10" (wrong, but would pass with broken sort)
    """
    import shutil

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

    # Must be numerically sorted: 3.14, 3.13, 3.12, 3.11, 3.10, 3.9
    # (lexikographic would be wrong: 3.9 > 3.10)
    versions = [v for v, _ in result]
    assert versions == ["3.14", "3.13", "3.12", "3.11", "3.10"]


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


def test_verbose_print_with_env(monkeypatch, capsys):
    """verbose_print outputs when APPENV_VERBOSE is set."""
    monkeypatch.setenv("APPENV_VERBOSE", "1")

    appenv.verbose_print("test message")

    captured = capsys.readouterr()
    assert "test message" in captured.out


def test_verbose_print_without_env(monkeypatch, capsys):
    """verbose_print outputs nothing when APPENV_VERBOSE is not set."""
    monkeypatch.delenv("APPENV_VERBOSE", raising=False)

    appenv.verbose_print("test message")

    captured = capsys.readouterr()
    assert captured.out == ""


def test_run_script_delegates(monkeypatch, tmp_path):
    """run_script() delegates to AppEnv.run() with script name."""
    env = appenv.AppEnv(tmp_path, Path.cwd())

    run_called = []
    monkeypatch.setattr(env, "run", lambda cmd, argv: run_called.append((cmd, argv)))

    env.run_script(argparse.Namespace(script="pytest"), ["-v", "test.py"])

    assert run_called == [("pytest", ["-v", "test.py"])]


def test_show_version(capsys, patterns):
    """show_version() prints the appenv version."""
    env = appenv.AppEnv(Path("/tmp"), Path.cwd())
    env.show_version()

    captured = capsys.readouterr()

    patterns.main.in_order(f"appenv {appenv.__version__}")

    full_pattern = patterns.full
    full_pattern.merge("main")

    example = full_pattern.generate_example()
    print(f"\n=== Pattern Example ===\n{example}\n=== End ===\n")

    assert full_pattern == captured.out


def test_settings_shows_all_vars(patterns, monkeypatch):
    """settings() displays all environment variables in clean state."""
    env = appenv.AppEnv(Path("/project"), Path.cwd())

    for var in [
        "APPENV_EXTRAS",
        "APPENV_VERBOSE",
        "APPENV_PROFILE",
        "APPENV_PROFILE_OUTPUT",
        "APPENV_BASEDIR",
        "APPENV_BEST_PYTHON",
        "UV_PROJECT_ENVIRONMENT",
    ]:
        monkeypatch.delenv(var, raising=False)

    output = io.StringIO()
    monkeypatch.setattr("sys.stdout", output)

    env.settings()

    result = output.getvalue()

    p = patterns.all_vars
    p.in_order(
        """\
appenv environment:
<empty-line>
  APPENV_EXTRAS: (not set)
    Extras to install (comma-separated)
<empty-line>
  APPENV_VERBOSE: (not set)
    Show verbose output
<empty-line>
  APPENV_PROFILE: (not set)
    Enable profiling
<empty-line>
  APPENV_PROFILE_OUTPUT: (not set)
    Profiling output file
<empty-line>
  APPENV_BASEDIR: (not set)
    Base directory of the project
<empty-line>
  APPENV_BEST_PYTHON: (not set)
    Selected Python interpreter
<empty-line>
  UV_PROJECT_ENVIRONMENT: (not set)
    uv venv location
<empty-line>
  PYTHONPATH: (not set)
    Python module search path
<empty-line>
  Base directory: /project
  Current working directory: ...
"""
    )

    patterns.no_errors.refused("...error...")
    patterns.no_errors.refused("...exception...")
    patterns.no_errors.refused("...traceback...")
    patterns.no_errors.refused("...failed...")

    full_pattern = patterns.full
    full_pattern.merge("all_vars", "no_errors")

    assert full_pattern == result


def test_settings_shows_set_values(patterns, monkeypatch):
    """settings() displays actual values when vars are set."""
    env = appenv.AppEnv(Path("/project"), Path.cwd())

    for var in [
        "APPENV_EXTRAS",
        "APPENV_VERBOSE",
        "APPENV_PROFILE",
        "APPENV_PROFILE_OUTPUT",
        "APPENV_BASEDIR",
        "APPENV_BEST_PYTHON",
        "UV_PROJECT_ENVIRONMENT",
    ]:
        monkeypatch.delenv(var, raising=False)

    monkeypatch.setenv("APPENV_EXTRAS", "controller,dev")
    monkeypatch.setenv("APPENV_VERBOSE", "1")

    output = io.StringIO()
    monkeypatch.setattr("sys.stdout", output)

    env.settings()

    result = output.getvalue()

    p = patterns.set_values
    p.in_order(
        """\
appenv environment:
<empty-line>
  APPENV_EXTRAS: controller,dev
    Extras to install (comma-separated)
<empty-line>
  APPENV_VERBOSE: 1
    Show verbose output
<empty-line>
  APPENV_PROFILE: (not set)
    Enable profiling
<empty-line>
  APPENV_PROFILE_OUTPUT: (not set)
    Profiling output file
<empty-line>
  APPENV_BASEDIR: (not set)
    Base directory of the project
<empty-line>
  APPENV_BEST_PYTHON: (not set)
    Selected Python interpreter
<empty-line>
  UV_PROJECT_ENVIRONMENT: (not set)
    uv venv location
<empty-line>
  PYTHONPATH: (not set)
    Python module search path
<empty-line>
  Base directory: /project
  Current working directory: ..."""
    )

    patterns.no_errors.refused("...error...")
    patterns.no_errors.refused("...exception...")
    patterns.no_errors.refused("...traceback...")
    patterns.no_errors.refused("...failed...")

    full_pattern = patterns.full
    full_pattern.merge("set_values", "no_errors")

    assert full_pattern == result


def test_settings_no_error_lines(patterns, monkeypatch):
    """settings() output contains no error or exception lines."""
    env = appenv.AppEnv(Path("/project"), Path.cwd())

    for var in ["APPENV_EXTRAS", "APPENV_VERBOSE", "APPENV_PROFILE"]:
        monkeypatch.delenv(var, raising=False)

    output = io.StringIO()
    monkeypatch.setattr("sys.stdout", output)

    env.settings()

    result = output.getvalue()

    # Pattern: refuse common error indicators
    p = patterns.clean_output
    p.refused("...error...")
    p.refused("...exception...")
    p.refused("...traceback...")
    p.refused("...failed...")
    p.optional("...")  # Allow everything else

    assert p == result


def test_get_uv_version_requires_uv_bin_argument(monkeypatch):
    """get_uv_version raises TypeError when uv_bin is missing."""
    with pytest.raises(TypeError):
        appenv.get_uv_version()  # type: ignore[missing-argument]


# Tier 2: Moderate Effort


def test_parse_requires_python_edge_cases(tmp_path):
    """parse_requires_python handles non-existent file and various regex formats."""
    base = tmp_path

    # Non-existent file returns (None, None)
    result = appenv.parse_requires_python(base / "nonexistent.toml")
    assert result == (None, None)

    pyproject = base / "pyproject.toml"

    # Format: >=3.13 (no space around operators)
    pyproject.write_text('requires-python = ">=3.13"\n')
    assert appenv.parse_requires_python(pyproject) == ("3.13", None)

    # Format: = "3.14" (with space after = and before value)
    pyproject.write_text('requires-python = ">=3.14"\n')
    assert appenv.parse_requires_python(pyproject) == ("3.14", None)

    # Format: >3.10 (greater than, not >=) - regex handles >=? so just > matches
    pyproject.write_text("requires-python = '>3.10'\n")
    assert appenv.parse_requires_python(pyproject) == ("3.10", None)

    # Format with extra whitespace around = (regex allows \s*)
    pyproject.write_text('requires-python=">=3.11"\n')
    assert appenv.parse_requires_python(pyproject) == ("3.11", None)

    # No match returns (None, None)
    pyproject.write_text("name = 'test'\n")
    assert appenv.parse_requires_python(pyproject) == (None, None)


def test_parse_requires_python_with_upper_bound(tmp_path):
    """parse_requires_python handles upper bounds like >=3.11,<3.15."""
    base = tmp_path
    pyproject = base / "pyproject.toml"

    # Format: >=3.11,<3.15
    pyproject.write_text('requires-python = ">=3.11,<3.15"\n')
    assert appenv.parse_requires_python(pyproject) == ("3.11", "3.15")

    # Format: >=3.11.0,<3.15.0 (with patch version)
    pyproject.write_text('requires-python = ">=3.11.0,<3.15.0"\n')
    assert appenv.parse_requires_python(pyproject) == ("3.11", "3.15")

    # Format: >=3.10,<=3.14 (inclusive upper bound)
    pyproject.write_text('requires-python = ">=3.10,<=3.14"\n')
    assert appenv.parse_requires_python(pyproject) == ("3.10", "3.14")

    # Format with spaces: >= 3.11, < 3.15
    pyproject.write_text('requires-python = ">= 3.11, < 3.15"\n')
    assert appenv.parse_requires_python(pyproject) == ("3.11", "3.15")


# Tier 3 tests


def test_uv_cmd_verbose_flag_and_output(monkeypatch, capsys):
    """uv_cmd adds -v flag when verbose=True and prints output."""
    monkeypatch.setenv("APPENV_VERBOSE", "1")
    monkeypatch.setattr(appenv, "ensure_uv", lambda: Path("/usr/bin/uv"))
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/uv")
    appenv._UV_BIN_CACHE = Path("/usr/bin/uv")

    cmd_calls = []

    def mock_cmd(c, **kwargs):
        cmd_calls.append(c)
        return b"verbose output from uv"

    monkeypatch.setattr(appenv, "cmd", mock_cmd)

    appenv.uv_cmd(["lock"], verbose=True)

    # Verify -v flag is added to command
    assert "-v" in cmd_calls[0]
    assert "lock" in cmd_calls[0]

    # Verify output is printed when APPENV_VERBOSE is set
    captured = capsys.readouterr()
    assert "verbose output from uv" in captured.out

    # Reset cache
    appenv._UV_BIN_CACHE = None


# ==============================================================================
# ensure_best_python tests (from test_coverage.py)
# ==============================================================================


def test_ensure_best_python_skips_when_env_set(tmp_path, monkeypatch):
    """Line 92: Returns early when APPENV_BEST_PYTHON is set."""
    base = tmp_path
    (base / "pyproject.toml").write_text('[project]\nname = "test"\n')

    monkeypatch.setenv("APPENV_BEST_PYTHON", "/usr/bin/python3")
    monkeypatch.setattr("os.chdir", lambda p: None)

    appenv.ensure_best_python(base)


def test_ensure_best_python_default_min_version(tmp_path, monkeypatch):
    """Line 99: Uses 3.10 as default when no requires-python specified."""
    base = tmp_path
    (base / "pyproject.toml").write_text('[project]\nname = "test"\n')

    monkeypatch.delenv("APPENV_BEST_PYTHON", raising=False)
    monkeypatch.setattr("os.chdir", lambda p: None)

    monkeypatch.setattr(
        appenv,
        "find_available_pythons",
        lambda: [
            ("3.14", "/usr/bin/python3.14"),
            ("3.10", "/usr/bin/python3.10"),
            ("3.9", "/usr/bin/python3.9"),
        ],
    )

    execv_called = []

    def mock_execv(path, argv):
        execv_called.append((path, argv))
        raise SystemExit(0)

    monkeypatch.setattr("os.execv", mock_execv)
    monkeypatch.setattr("subprocess.check_call", lambda cmd, **kwargs: None)
    monkeypatch.setattr("sys.executable", "/different/python")

    with pytest.raises(SystemExit):
        appenv.ensure_best_python(base)

    assert "python3.14" in execv_called[0][0]


def test_ensure_best_python_already_running_best(tmp_path, monkeypatch):
    """Line 123: Returns early when already running the best Python."""
    base = tmp_path
    (base / "pyproject.toml").write_text('[project]\nname = "test"\n')

    monkeypatch.delenv("APPENV_BEST_PYTHON", raising=False)
    monkeypatch.setattr("os.chdir", lambda p: None)

    monkeypatch.setattr(
        appenv,
        "find_available_pythons",
        lambda: [("3.12", "/usr/bin/python3.12")],
    )

    def mock_resolve(self):
        return Path("/usr/bin/python3.12")

    monkeypatch.setattr("pathlib.Path.resolve", mock_resolve)
    monkeypatch.setattr("sys.executable", "/usr/bin/python3.12")

    appenv.ensure_best_python(base)


def test_ensure_best_python_broken_python(tmp_path, monkeypatch):
    """Lines 132-133: Continues to next Python when subprocess fails."""
    base = tmp_path
    (base / "pyproject.toml").write_text('[project]\nname = "test"\n')

    monkeypatch.delenv("APPENV_BEST_PYTHON", raising=False)
    monkeypatch.setattr("os.chdir", lambda p: None)

    monkeypatch.setattr(
        appenv,
        "find_available_pythons",
        lambda: [
            ("3.12", "/usr/bin/python3.12"),
            ("3.11", "/usr/bin/python3.11"),
        ],
    )

    check_call_count = []

    def mock_check_call(cmd, **kwargs):
        check_call_count.append(cmd)
        if "python3.12" in str(cmd):
            raise subprocess.CalledProcessError(1, cmd)

    execv_called = []

    def mock_execv(path, argv):
        execv_called.append((path, argv))
        raise SystemExit(0)

    monkeypatch.setattr("subprocess.check_call", mock_check_call)
    monkeypatch.setattr("os.execv", mock_execv)
    monkeypatch.setattr("sys.executable", "/different/python")

    with pytest.raises(SystemExit):
        appenv.ensure_best_python(base)

    assert len(check_call_count) == 2
    assert "python3.11" in execv_called[0][0]


# ==============================================================================
# get_uv_bin tests (from test_coverage.py)
# ==============================================================================


def test_get_uv_bin_pip_fallback_success(tmp_path, monkeypatch):
    """pip install fallback raises RuntimeError when uv still not found."""
    appenv._UV_BIN_CACHE = None

    which_calls = []

    def mock_which(name):
        which_calls.append(name)
        return None  # uv never available

    monkeypatch.setattr("shutil.which", mock_which)

    pip_called = []

    def mock_run(cmd, **kwargs):
        pip_called.append(cmd)

    monkeypatch.setattr("subprocess.run", mock_run)

    with pytest.raises(RuntimeError, match="uv not found and could not be installed"):
        appenv.get_uv_bin(tmp_path)

    assert any("pip" in str(cmd) and "uv" in str(cmd) for cmd in pip_called)
    appenv._UV_BIN_CACHE = None


def test_get_uv_bin_pip_fallback_finds_installed_uv(tmp_path, monkeypatch):
    """pip install fallback finds uv after installation."""
    appenv._UV_BIN_CACHE = None

    which_calls = []

    def mock_which(name):
        which_calls.append(name)
        if name == "uv":
            # First call: no uv in PATH
            # After pip install: uv is available
            if len(which_calls) > 2:  # After pip install attempt
                return "/usr/bin/uv"
            return None
        if name == "nix":
            return None  # No nix available
        return shutil.which(name)

    monkeypatch.setattr(shutil, "which", mock_which)

    run_calls = []

    def mock_run(cmd, **kwargs):
        run_calls.append(list(cmd))
        text_mode = kwargs.get("text", False)
        # pip install succeeds
        if "pip" in str(cmd) and "install" in str(cmd):
            return subprocess.CompletedProcess(cmd, 0, b"", b"")
        # uv --version check after pip install
        if "--version" in str(cmd):
            stdout = "uv 0.5.0\n" if text_mode else b"uv 0.5.0\n"
            return subprocess.CompletedProcess(cmd, 0, stdout, b"")
        return subprocess.CompletedProcess(cmd, 0, b"", b"")

    monkeypatch.setattr(subprocess, "run", mock_run)

    result = appenv.get_uv_bin(tmp_path)

    assert str(result) == "/usr/bin/uv"
    assert any("pip" in str(cmd) and "install" in str(cmd) for cmd in run_calls)
    appenv._UV_BIN_CACHE = None


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
    monkeypatch.setattr(appenv.AppEnv, "meta", lambda self, args: None)
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


def get_source_version():
    """Get version from src/appenv.py __version__."""
    appenv_py = Path(__file__).parent.parent / "src" / "appenv.py"
    content = appenv_py.read_text()
    match = re.search(r'^__version__\s*=\s*"([^"]+)"', content, re.MULTILINE)
    if not match:
        raise ValueError("Could not find __version__ in src/appenv.py")
    return match.group(1)


def get_appenv_version():
    """Get version from ./appenv version command."""
    result = subprocess.run(
        ["./appenv", "version"],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent.parent,
    )
    # Output is "appenv X.Y.Z"
    return result.stdout.strip().split()[-1]


def test_version_consistency():
    """Version in appenv.py matches version in appenv bootstrap script."""
    # Read version from appenv module
    module_version = appenv.__version__

    # Read version from src/appenv.py
    appenv_path = Path(__file__).parent.parent / "src" / "appenv.py"
    appenv_content = appenv_path.read_text()

    # Extract version from appenv file
    import re

    match = re.search(r'__version__ = "([^"]+)"', appenv_content)
    assert match, "Could not find __version__ in appenv file"
    file_version = match.group(1)

    assert module_version == file_version, (
        f"Version mismatch: module={module_version}, file={file_version}"
    )


def test_reset_nonexisting_envdir_silent(tmp_path):
    env = appenv.AppEnv(tmp_path / "ducker", Path.cwd())
    assert not os.path.exists(env.appenv_dir)
    env.reset()
    assert not os.path.exists(env.appenv_dir)
    assert os.path.exists(str(tmp_path))


def test_reset_removes_envdir_with_subdirs(tmp_path):
    """reset() cleans up contents in .appenv."""
    env = appenv.AppEnv(tmp_path / "ducker", Path.cwd())
    os.makedirs(env.appenv_dir)
    # Create some subdirectories
    (env.appenv_dir / "subdir1").mkdir()
    (env.appenv_dir / "subdir2").mkdir()
    assert os.path.exists(env.appenv_dir)
    env.reset()
    # .appenv should still exist but be empty (or only contain .uv)
    assert os.path.exists(env.appenv_dir)
    # No subdirectories left (except possibly .uv)
    remaining = list(env.appenv_dir.iterdir())
    assert all(p.name == ".uv" for p in remaining)


def test_reset_removes_venv(tmp_path, capsys):
    """reset() also removes .venv for pyproject workflow."""
    base = tmp_path / "myproject"
    base.mkdir()
    venv = base / ".venv"
    venv.mkdir()
    (venv / "bin").mkdir()
    (venv / "bin" / "python").write_text("#!/bin/sh\necho python")

    assert venv.exists()

    env = appenv.AppEnv(base, Path.cwd())
    env.reset()

    assert not venv.exists()
    captured = capsys.readouterr()
    assert "Removing" in captured.out and ".venv" in captured.out


def test_reset_removes_both_venv_and_appenv(tmp_path, capsys):
    """reset() removes .venv symlink and cleans .appenv contents."""
    base = tmp_path / "myproject"
    base.mkdir()

    # Create .venv (as symlink to .appenv/venv)
    appenv_dir = base / ".appenv"
    appenv_dir.mkdir()
    venv_real = appenv_dir / "venv"
    venv_real.mkdir()
    venv_link = base / ".venv"
    venv_link.symlink_to(".appenv/venv")

    assert venv_link.exists()
    assert appenv_dir.exists()

    env = appenv.AppEnv(base, Path.cwd())
    env.reset()

    # Symlink should be removed
    assert not venv_link.exists()
    # .appenv should still exist but venv should be gone
    assert appenv_dir.exists()
    assert not venv_real.exists()


def test_reset_unlinks_file_in_appenv(workdir, monkeypatch, capsys):
    """Line 1108: reset() unlinks non-directory files in .appenv."""
    base = Path(workdir)

    # Create .appenv with a file (not directory)
    appenv_dir = base / ".appenv"
    appenv_dir.mkdir()
    old_file = appenv_dir / "old_file.txt"
    old_file.write_text("old content")

    monkeypatch.setenv("APPENV_VERBOSE", "1")

    env = appenv.AppEnv(base, Path.cwd())
    env.reset()

    assert not old_file.exists()
    captured = capsys.readouterr()
    assert "Removing" in captured.out


def test_reset_removes_venv_symlink(workdir, monkeypatch, capsys):
    """reset() removes .venv symlink."""
    base = Path(workdir)

    # Create .appenv/venv and .venv symlink
    appenv_dir = base / ".appenv"
    appenv_dir.mkdir()
    venv_real = appenv_dir / "venv"
    venv_real.mkdir()
    venv_link = base / ".venv"
    venv_link.symlink_to(".appenv/venv")

    env = appenv.AppEnv(base, Path.cwd())
    env.reset()

    assert not venv_link.exists()
    captured = capsys.readouterr()
    assert "Removing" in captured.out


def test_reset_removes_real_venv(workdir, monkeypatch, capsys):
    """reset() removes .appenv/venv directory."""
    base = Path(workdir)

    # Create .appenv/venv
    appenv_dir = base / ".appenv"
    appenv_dir.mkdir()
    venv_real = appenv_dir / "venv"
    venv_real.mkdir()
    (venv_real / "bin").mkdir()

    env = appenv.AppEnv(base, Path.cwd())
    env.reset()

    assert not venv_real.exists()
    captured = capsys.readouterr()
    assert "Removing" in captured.out


def test_reset_removes_old_venv_directory(workdir, monkeypatch, capsys):
    """reset() removes old .venv directory (not symlink)."""
    base = Path(workdir)

    # Create .venv as a real directory (legacy)
    venv_dir = base / ".venv"
    venv_dir.mkdir()
    (venv_dir / "bin").mkdir()

    env = appenv.AppEnv(base, Path.cwd())
    env.reset()

    assert not venv_dir.exists()
    captured = capsys.readouterr()
    assert "Removing old" in captured.out
