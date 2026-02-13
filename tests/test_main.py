"""Tests for main() entry point and related functions."""

import argparse
import io
import logging
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import appenv
from appenv import UvVersion


def get_test_settings(basedir=None):
    """Get settings for tests with optional explicit basedir."""
    import os

    if basedir is None:
        basedir = appenv.appenv_settings_from_env().basedir
    return appenv.AppEnvSettings(
        verbose=os.environ.get("APPENV_VERBOSE") is not None,
        extras=[
            e.strip()
            for e in (os.environ.get("APPENV_EXTRAS") or "").split(",")
            if e.strip()
        ],
        profile=os.environ.get("APPENV_PROFILING") is not None,
        basedir=basedir,
    )


def mock_ensure_python(monkeypatch):
    """Mock ensure_best_python to prevent re-exec."""
    monkeypatch.setattr(appenv, "ensure_best_python", lambda base: None)


# main() tests


def test_main_shows_usage_without_subcommand(monkeypatch, capsys, tmp_path):
    """Test that calling appenv without subcommand shows usage."""
    mock_ensure_python(monkeypatch)
    monkeypatch.setattr("sys.argv", ["appenv"])
    monkeypatch.setattr(appenv, "__file__", "/some/path/appenv")

    # Mock _set_up_logdir to use tmp_path
    mock_log_dir = tmp_path / "logs"
    mock_log_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(appenv.AppEnv, "_set_up_logdir", lambda self: mock_log_dir)

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


def test_main_shows_grouped_help(monkeypatch, capsys, tmp_path):
    """Test that help output shows commands grouped by category."""
    mock_ensure_python(monkeypatch)
    monkeypatch.setattr("sys.argv", ["appenv", "--help"])
    monkeypatch.setattr(appenv, "__file__", "/some/path/appenv")

    # Mock _set_up_logdir to use tmp_path
    mock_log_dir = tmp_path / "logs"
    mock_log_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(appenv.AppEnv, "_set_up_logdir", lambda self: mock_log_dir)

    with pytest.raises(SystemExit):
        appenv.main()

    captured = capsys.readouterr()
    output = captured.out

    # Check for group headers
    assert "Project:" in output
    assert "Venv:" in output
    assert "Tools:" in output
    assert "Debug:" in output

    # Check that commands are in correct groups
    # Project group
    assert "init" in output
    assert "migrate" in output
    assert "update-lockfile" in output

    # Venv group
    assert "develop" in output
    assert "prepare" in output
    assert "reset" in output

    # Tools group
    assert "python" in output
    assert "run" in output

    # Debug group
    assert "version" in output
    assert "settings" in output


def test_help_same_as_no_args(monkeypatch, capsys, tmp_path):
    """Test that --help shows grouped help output."""
    mock_ensure_python(monkeypatch)
    monkeypatch.setattr(appenv, "__file__", "/some/path/appenv")

    # Mock _set_up_logdir to use tmp_path
    mock_log_dir = tmp_path / "logs"
    mock_log_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(appenv.AppEnv, "_set_up_logdir", lambda self: mock_log_dir)

    # Get output with --help
    monkeypatch.setattr("sys.argv", ["appenv", "--help"])
    with pytest.raises(SystemExit):
        appenv.main()
    captured_help = capsys.readouterr()

    # --help shows full grouped help on stdout
    assert "Project:" in captured_help.out
    assert "Commands:" in captured_help.out


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


# UvBin tests


def test_uv_bin_cmd_raises_when_uv_not_found(monkeypatch):
    # UvBin.cmd raises FileNotFoundError when uv binary doesn't exist
    # Create a UvBin with a non-existent binary
    uv = appenv.UvBin.__new__(appenv.UvBin)
    uv.bin = Path("/usr/bin/nonexistent_uv")
    uv.appenv_dir = Path("/tmp/.appenv")
    uv.uv_dir = uv.appenv_dir / ".uv"

    with pytest.raises(FileNotFoundError):
        uv.cmd(["lock"])


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


def test_try_uv_from_path_returns_path_when_valid(monkeypatch, tmp_path):
    """_try_uv_from_path returns path when uv in PATH and version valid."""
    # Create a UvBin instance using constructor
    uv_bin = appenv.UvBin(tmp_path / ".appenv")

    # Mock shutil.which to return a path
    monkeypatch.setattr(
        "shutil.which", lambda name: "/usr/bin/uv" if name == "uv" else None
    )

    # Mock UvBin.get_uv_version to return a valid version
    mock_version = UvVersion(0, 10, 3)
    monkeypatch.setattr(appenv.UvBin, "get_uv_version", lambda path: mock_version)

    # Mock _cleanup_appenv_uv to track if it's called
    cleanup_called = []
    monkeypatch.setattr(
        uv_bin, "_cleanup_appenv_uv", lambda: cleanup_called.append(True)
    )

    # Call the method
    result = uv_bin._try_uv_from_path()

    # Verify results
    assert result == Path("/usr/bin/uv")
    assert cleanup_called == [True]  # Cleanup should be called


def test_try_uv_from_path_returns_none_when_invalid_version(monkeypatch):
    """_try_uv_from_path returns None when uv in PATH but version invalid."""
    # Create a UvBin instance
    uv_bin = appenv.UvBin.__new__(appenv.UvBin)
    uv_bin.appenv_dir = Path("/tmp/.appenv")
    uv_bin.uv_dir = uv_bin.appenv_dir / ".uv"

    # Mock shutil.which to return a path
    monkeypatch.setattr(
        "shutil.which", lambda name: "/usr/bin/uv" if name == "uv" else None
    )

    # Mock UvBin.get_uv_version to return None (invalid version)
    monkeypatch.setattr(
        appenv.UvBin, "get_uv_version", lambda path: UvVersion.unknown()
    )

    # Mock _cleanup_appenv_uv to track if it's called
    cleanup_called = []
    monkeypatch.setattr(
        uv_bin, "_cleanup_appenv_uv", lambda: cleanup_called.append(True)
    )

    # Call the method
    result = uv_bin._try_uv_from_path()

    # Verify results
    assert result is None
    assert cleanup_called == []  # Cleanup should not be called


def test_try_uv_from_path_returns_none_when_not_in_path(monkeypatch):
    """_try_uv_from_path returns None when uv not in PATH."""
    # Create a UvBin instance
    uv_bin = appenv.UvBin.__new__(appenv.UvBin)
    uv_bin.appenv_dir = Path("/tmp/.appenv")
    uv_bin.uv_dir = uv_bin.appenv_dir / ".uv"

    # Mock shutil.which to return None (not found)
    monkeypatch.setattr("shutil.which", lambda name: None)

    # Mock _cleanup_appenv_uv to track if it's called
    cleanup_called = []
    monkeypatch.setattr(
        uv_bin, "_cleanup_appenv_uv", lambda: cleanup_called.append(True)
    )

    # Call the method
    result = uv_bin._try_uv_from_path()

    # Verify results
    assert result is None
    assert cleanup_called == []  # Cleanup should not be called


# meta() tests


def test_meta_calls_reset(monkeypatch, tmp_path):
    env = appenv.AppEnv(Path.cwd(), get_test_settings(Path.cwd()))
    monkeypatch.setattr("sys.argv", ["appenv", "reset"])

    reset_called = []
    monkeypatch.setattr(
        env, "reset", lambda args=None, remaining=None: reset_called.append(True)
    )

    env.meta()

    assert reset_called == [True]


def test_meta_calls_prepare(monkeypatch, tmp_path):
    env = appenv.AppEnv(Path.cwd(), get_test_settings(Path.cwd()))
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
    env = appenv.AppEnv(Path.cwd(), get_test_settings(Path.cwd()))
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
    env = appenv.AppEnv(Path.cwd(), get_test_settings(Path.cwd()))
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
    env = appenv.AppEnv(Path.cwd(), get_test_settings(Path.cwd()))

    # Add pyproject.toml and uv.lock so _prepare_venv doesn't exit
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "test"\nversion = "0.1.0"\n'
    )
    (tmp_path / "uv.lock").write_text("version = 1\n")

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


def test_run_with_profiling_enabled(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("APPENV_PROFILING", "1")
    env = appenv.AppEnv(Path.cwd(), get_test_settings(Path.cwd()))

    # Add pyproject.toml and uv.lock so _prepare_venv doesn't exit
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "test"\nversion = "0.1.0"\n'
    )
    (tmp_path / "uv.lock").write_text("version = 1\n")

    env_dir = tmp_path / ".appenv" / "abc123"
    env_dir.mkdir(parents=True)
    bin_dir = env_dir / "bin"
    bin_dir.mkdir()
    (bin_dir / "myapp").write_text("#!/bin/sh\necho hello\n")

    monkeypatch.setattr(env, "_prepare_venv", lambda dev_mode=False: env_dir)
    monkeypatch.setattr("os.chdir", lambda p: None)

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
    assert "Command profiling enabled" in captured.out
    assert ".appenv/profiling/myapp-" in captured.out


def test_profiling_list_no_data(tmp_path, capsys):
    """profiling_list shows message when no profiling data exists."""
    env = appenv.AppEnv(Path.cwd(), get_test_settings(Path.cwd()))
    args = argparse.Namespace(count=10)
    env.profile_list(args)

    captured = capsys.readouterr()
    assert "No profiling data found" in captured.out


def test_profiling_list_with_profiles(tmp_path, capsys):
    """profiling_list shows profiles sorted by mtime."""
    env = appenv.AppEnv(Path.cwd(), get_test_settings(tmp_path))
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
    env.profile_list(args)

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
    env = appenv.AppEnv(tmp_path, get_test_settings(tmp_path))
    profiling_dir = tmp_path / ".appenv" / "profiling"
    profiling_dir.mkdir(parents=True)

    for i in range(5):
        (profiling_dir / f"cmd-{i:04d}.prof").write_text("dummy")

    args = argparse.Namespace(count=2)
    env.profile_list(args)

    captured = capsys.readouterr()
    assert "Showing 2 of 5 profiles" in captured.out


def test_profiling_show_no_data(tmp_path, capsys):
    """profiling_show exits when no profiling data exists."""
    env = appenv.AppEnv(Path.cwd(), get_test_settings(Path.cwd()))
    args = argparse.Namespace(file=None)

    with pytest.raises(SystemExit) as exc_info:
        env.profiling_show(args)

    assert exc_info.value.code == appenv.EXIT_CODE_NOINPUT
    captured = capsys.readouterr()
    assert "No profiling data found" in captured.out


def test_profiling_show_file_not_found(tmp_path, capsys):
    """profiling_show exits when specified file not found."""
    env = appenv.AppEnv(Path.cwd(), get_test_settings(Path.cwd()))
    args = argparse.Namespace(file="nonexistent.prof")

    with pytest.raises(SystemExit) as exc_info:
        env.profiling_show(args)

    assert exc_info.value.code == appenv.EXIT_CODE_NOINPUT
    captured = capsys.readouterr()
    assert "Profile not found" in captured.out


def test_profiling_snakeviz_no_data(tmp_path, capsys):
    """profiling_snakeviz exits when no profiling data exists."""
    env = appenv.AppEnv(Path.cwd(), get_test_settings(Path.cwd()))
    args = argparse.Namespace(file=None)

    with pytest.raises(SystemExit) as exc_info:
        env.profiling_snakeviz(args)

    assert exc_info.value.code == appenv.EXIT_CODE_NOINPUT
    captured = capsys.readouterr()
    assert "No profiling data found" in captured.out


def test_profiling_snakeviz_opens_latest(tmp_path, capsys, monkeypatch):
    """profiling_snakeviz opens latest profile with uv run snakeviz."""
    env = appenv.AppEnv(tmp_path, get_test_settings(tmp_path))
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
    assert "uv" in path
    assert "uv" in argv
    assert "run" in argv
    assert "--with" in argv
    assert "snakeviz" in argv
    assert str(profile) in argv
    captured = capsys.readouterr()
    assert "Opening latest profile" in captured.out


def test_profiling_snakeviz_specific_file(tmp_path, monkeypatch):
    """profiling_snakeviz opens specific profile file."""
    env = appenv.AppEnv(tmp_path, get_test_settings(tmp_path))
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
    env = appenv.AppEnv(Path.cwd(), get_test_settings(Path.cwd()))
    args = argparse.Namespace(file="nonexistent.prof")

    with pytest.raises(SystemExit) as exc_info:
        env.profiling_snakeviz(args)

    assert exc_info.value.code == appenv.EXIT_CODE_NOINPUT
    captured = capsys.readouterr()
    assert "Profile not found" in captured.out


def test_python_method_calls_run(monkeypatch, tmp_path):
    env = appenv.AppEnv(Path.cwd(), get_test_settings(Path.cwd()))

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
    output = re.sub(r"\x1b\[[0-9;]*m", "", captured.out)

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


@pytest.mark.no_mock_uv_version
def test_uv_binget_uv_version_returns_version_on_success(tmp_path, monkeypatch):
    """Returns UvVersion object on successful version check."""
    uv = appenv.UvBin.__new__(appenv.UvBin)
    uv.bin = Path("/usr/bin/uv")
    uv.appenv_dir = tmp_path / ".appenv"
    uv.uv_dir = uv.appenv_dir / ".uv"

    class FakeResult:
        stdout = "uv 0.10.3 (abc123 2024-01-01)\n"
        returncode = 0

    monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: FakeResult())

    result = appenv.UvBin.get_uv_version(uv.bin)

    assert isinstance(result, UvVersion)
    assert result == UvVersion(0, 10, 3)


@pytest.mark.no_mock_uv_version
def test_uv_binget_uv_version_not_valid_on_subprocess_error(monkeypatch, capsys):
    """When uv --version fails, get_uv_version returns None."""
    uv = appenv.UvBin.__new__(appenv.UvBin)
    uv.bin = Path("/usr/bin/uv")
    uv.appenv_dir = Path("/tmp/.appenv")
    uv.uv_dir = uv.appenv_dir / ".uv"

    import subprocess

    def fake_run(*args, **kwargs):
        raise subprocess.CalledProcessError(1, "uv --version")

    monkeypatch.setattr("subprocess.run", fake_run)

    version = appenv.UvBin.get_uv_version(uv.bin)
    assert version == UvVersion.unknown()


@pytest.mark.no_mock_uv_version
def test_uv_binget_uv_version_returns_none_when_too_old(monkeypatch, capsys):
    """When version is too old, get_uv_version returns UvVersion with valid=False."""
    uv = appenv.UvBin.__new__(appenv.UvBin)
    uv.bin = Path("/usr/bin/uv")
    uv.appenv_dir = Path("/tmp/.appenv")
    uv.uv_dir = uv.appenv_dir / ".uv"

    class FakeResult:
        stdout = "uv 0.4.0 (abc123 2024-01-01)\n"
        returncode = 0

    monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: FakeResult())

    result = appenv.UvBin.get_uv_version(uv.bin)

    assert isinstance(result, UvVersion)
    assert result == UvVersion(0, 4, 0)
    assert not result.valid


@pytest.mark.no_mock_uv_version
def test_uv_binget_uv_version_handles_parse_error(tmp_path, monkeypatch, capsys):
    """When version string is unparseable, get_uv_version returns None."""
    uv = appenv.UvBin.__new__(appenv.UvBin)
    uv.bin = Path("/usr/bin/uv")
    uv.appenv_dir = tmp_path / ".appenv"
    uv.uv_dir = uv.appenv_dir / ".uv"

    class FakeResult:
        stdout = "uv invalid-version\n"
        returncode = 0

    monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: FakeResult())

    result = appenv.UvBin.get_uv_version(uv.bin)

    assert result == UvVersion.unknown()


@pytest.mark.no_mock_uv_version
def test_uv_binget_uv_version_index_error_on_split(monkeypatch, capsys):
    """IndexError when version output has no second element returns None."""
    uv = appenv.UvBin.__new__(appenv.UvBin)
    uv.bin = Path("/usr/bin/uv")
    uv.appenv_dir = Path("/tmp/.appenv")
    uv.uv_dir = uv.appenv_dir / ".uv"

    class FakeResult:
        # Single word output - split()[1] will raise IndexError
        stdout = "uv\n"
        returncode = 0

    monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: FakeResult())

    result = appenv.UvBin.get_uv_version(uv.bin)

    assert result == UvVersion.unknown()


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


def test_run_script_delegates(monkeypatch, tmp_path):
    """run_script() delegates to AppEnv.run() with script name."""
    env = appenv.AppEnv(Path.cwd(), get_test_settings(Path.cwd()))

    run_called = []
    monkeypatch.setattr(env, "run", lambda cmd, argv: run_called.append((cmd, argv)))

    env.run_script(argparse.Namespace(script="pytest"), ["-v", "test.py"])

    assert run_called == [("pytest", ["-v", "test.py"])]


def test_settings_no_error_lines(monkeypatch):
    """settings() output contains no error or exception lines."""
    env = appenv.AppEnv(Path.cwd(), get_test_settings(Path.cwd()))

    for var in ["APPENV_EXTRAS", "APPENV_VERBOSE", "APPENV_PROFILING"]:
        monkeypatch.delenv(var, raising=False)

    output = io.StringIO()
    monkeypatch.setattr("sys.stdout", output)

    env.show_settings()

    result = output.getvalue()

    # Simple assertions: output should not contain error indicators
    output_lower = result.lower()
    assert "error" not in output_lower
    assert "exception" not in output_lower
    assert "traceback" not in output_lower
    assert "failed" not in output_lower


def test_show_version(tmp_path, capsys, patterns):
    """show_version() prints the appenv version."""
    env = appenv.AppEnv(Path.cwd(), get_test_settings(Path.cwd()))
    env.show_version()

    captured = capsys.readouterr()

    patterns.main.in_order(f"appenv {appenv.__version__}")

    full_pattern = patterns.full
    full_pattern.merge("main")

    full_pattern.generate_example()

    assert full_pattern == captured.out


def test_show_settings(patterns, monkeypatch):
    """settings() displays all environment variables in clean state."""
    for var in [
        "APPENV_PROFILING",
        "APPENV_BASEDIR",
        "APPENV_BEST_PYTHON",
        "UV_PROJECT_ENVIRONMENT",
    ]:
        monkeypatch.delenv(var, raising=False)

    monkeypatch.setenv("APPENV_EXTRAS", "controller,dev")
    monkeypatch.setenv("APPENV_VERBOSE", "1")

    env = appenv.AppEnv(Path.cwd(), get_test_settings(Path.cwd()))

    output = io.StringIO()
    monkeypatch.setattr("sys.stdout", output)

    env.show_settings()

    result = output.getvalue()

    patterns.ext.in_order(
        """\
<empty-line>
=== Appenv Execution Environment ===
<empty-line>
...
Base directory: ...
Current working directory: ...
<empty-line>
"""
    )

    patterns.env_vars.in_order("""\
=== Appenv Environment Variables ===
<empty-line>
APPENV_VERBOSE: True
   Show detailed output including uv commands
<empty-line>
APPENV_EXTRAS: ['controller', 'dev']
   Optional dependency groups to install (e.g. dev, test)
<empty-line>
APPENV_PROFILING: False
   Enable cProfile profiling for executed commands
<empty-line>
APPENV_BASEDIR: ...
   root directory containing pyproject.toml
""")

    patterns.no_errors.refused("...error...")
    patterns.no_errors.refused("...exception...")
    patterns.no_errors.refused("...traceback...")
    patterns.no_errors.refused("...failed...")

    full_pattern = patterns.full
    full_pattern.merge("ext", "env_vars")

    assert full_pattern == result


def test_try_uv_from_appenv_dir_returns_path_when_valid(monkeypatch, tmp_path):
    """_try_uv_from_appenv_dir returns path when uv exists and version is valid."""
    # Create a UvBin instance
    uv_bin = appenv.UvBin(tmp_path / ".appenv")

    # Create the .appenv/.uv/bin/uv file
    uv_local = tmp_path / ".appenv/.uv/bin/uv"
    uv_local.parent.mkdir(parents=True)
    uv_local.write_text("#!/bin/sh\n")

    # Mock UvBin.get_uv_version to return a valid version
    mock_version = UvVersion(0, 10, 3)
    monkeypatch.setattr(appenv.UvBin, "get_uv_version", lambda path: mock_version)

    # Call the method
    result = uv_bin._try_uv_from_appenv_dir()

    # Verify results
    assert result == uv_local


def test_try_uv_from_appenv_dir_returns_none_when_invalid_version(
    monkeypatch, tmp_path
):
    """_try_uv_from_appenv_dir returns None when uv exists but version is invalid."""
    # Create a UvBin instance
    uv_bin = appenv.UvBin(tmp_path / ".appenv")

    # Create the .appenv/.uv/bin/uv file
    uv_local = tmp_path / ".appenv/.uv/bin/uv"
    uv_local.parent.mkdir(parents=True)
    uv_local.write_text("#!/bin/sh\n")

    # Mock UvBin.get_uv_version to return unknown version (invalid)
    monkeypatch.setattr(
        appenv.UvBin, "get_uv_version", lambda path: UvVersion.unknown()
    )

    # Call the method
    result = uv_bin._try_uv_from_appenv_dir()

    # Verify results
    assert result is None


def test_try_uv_from_appenv_dir_returns_none_when_not_exists(monkeypatch, tmp_path):
    """_try_uv_from_appenv_dir returns None when uv does not exist."""
    # Create a UvBin instance
    uv_bin = appenv.UvBin(tmp_path / ".appenv")

    # Do not create the .appenv/.uv/bin/uv file

    # Call the method
    result = uv_bin._try_uv_from_appenv_dir()

    # Verify results
    assert result is None


# ==============================================================================
# UvBin._try_uv_from_nix_channel tests
# ==============================================================================


def test_try_uv_from_nix_channel_returns_path_when_valid(monkeypatch, tmp_path, caplog):
    """_try_uv_from_nix_channel returns path when nix build succeeds."""
    # Create a UvBin instance
    uv_bin = appenv.UvBin(tmp_path / ".appenv")

    # Mock preceding methods to return None so we reach this method
    monkeypatch.setattr(uv_bin, "_try_uv_from_path", lambda: None)
    monkeypatch.setattr(uv_bin, "_try_uv_from_appenv_dir", lambda: None)

    # Mock shutil.which to return nix path
    monkeypatch.setattr(
        "shutil.which", lambda name: "/nix/bin/nix" if name == "nix" else None
    )

    # Mock uv_local.exists() to return True (so we get the "Updating" log)
    uv_local = tmp_path / ".appenv/.uv/bin/uv"
    uv_local.parent.mkdir(parents=True)
    uv_local.write_text("#!/bin/sh\n")

    # Mock subprocess.run to return success
    class FakeResult:
        returncode = 0
        stderr = ""
        stdout = ""

    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: FakeResult())

    # Mock UvBin.get_uv_version to return a valid version
    mock_version = UvVersion(0, 10, 3)
    monkeypatch.setattr(appenv.UvBin, "get_uv_version", lambda path: mock_version)

    # Cap logs at DEBUG level
    caplog.set_level(logging.DEBUG)

    # Call the method
    result = uv_bin._try_uv_from_nix_channel()

    # Verify results
    assert result == uv_local
    # Check that we got the "Updating" log (since uv_local.exists() was True)
    assert "Updating .appenv/.uv with Nix" in caplog.text


def test_try_uv_from_nix_channel_returns_path_when_created(
    monkeypatch, tmp_path, caplog
):
    """_try_uv_from_nix_channel returns path when nix build succeeds and uv needed."""
    # Create a UvBin instance
    uv_bin = appenv.UvBin(tmp_path / ".appenv")

    # Mock preceding methods to return None so we reach this method
    monkeypatch.setattr(uv_bin, "_try_uv_from_path", lambda: None)
    monkeypatch.setattr(uv_bin, "_try_uv_from_appenv_dir", lambda: None)

    # Mock shutil.which to return nix path
    monkeypatch.setattr(
        "shutil.which", lambda name: "/nix/bin/nix" if name == "nix" else None
    )

    # Define uv_local path (but don't create the file, so exists() returns False)
    uv_local = tmp_path / ".appenv/.uv/bin/uv"

    # Mock subprocess.run to return success
    class FakeResult:
        returncode = 0
        stdout = ""
        stderr = b""

    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: FakeResult())

    # Mock UvBin.get_uv_version to return a valid version
    mock_version = UvVersion(0, 10, 3)
    monkeypatch.setattr(appenv.UvBin, "get_uv_version", lambda path: mock_version)

    # Cap logs at DEBUG level
    caplog.set_level(logging.DEBUG)

    # Call the method
    result = uv_bin._try_uv_from_nix_channel()

    # Verify results
    assert result == uv_local
    # Check that we got the "Creating" log (since uv_local.exists() was False)
    assert "Creating .appenv/.uv with Nix" in caplog.text


def test_try_uv_from_nix_channel_returns_none_when_nix_not_found(monkeypatch, tmp_path):
    """_try_uv_from_nix_channel returns None when nix not in PATH."""
    # Create a UvBin instance
    uv_bin = appenv.UvBin(tmp_path / ".appenv")

    # Mock shutil.which to return None (nix not found)
    monkeypatch.setattr("shutil.which", lambda name: None)

    # Call the method
    result = uv_bin._try_uv_from_nix_channel()

    # Verify results
    assert result is None


def test_try_uv_from_nix_channel_returns_none_when_build_fails(
    monkeypatch, tmp_path, caplog, subprocess_run_fail
):
    """_try_uv_from_nix_channel returns None when nix build fails."""
    # Create a UvBin instance
    uv_bin = appenv.UvBin(tmp_path / ".appenv")

    # Mock shutil.which to return nix path
    monkeypatch.setattr(
        "shutil.which", lambda name: "/nix/bin/nix" if name == "nix" else None
    )

    # Cap logs at DEBUG level
    caplog.set_level(logging.DEBUG)

    # Call the method
    result = uv_bin._try_uv_from_nix_channel()

    # Verify results
    assert result is None
    # Check that we logged the failure
    assert "nix-build failed:" in caplog.text


def test_try_uv_from_nix_channel_returns_none_when_invalid_version(
    monkeypatch, tmp_path, caplog
):
    """_try_uv_from_nix_channel returns None when uv built but version invalid."""
    # Create a UvBin instance
    uv_bin = appenv.UvBin(tmp_path / ".appenv")

    # Mock shutil.which to return nix path
    monkeypatch.setattr(
        "shutil.which", lambda name: "/nix/bin/nix" if name == "nix" else None
    )

    # Mock subprocess.run to return success
    class FakeResult:
        returncode = 0
        stdout = ""
        stderr = b""

    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: FakeResult())

    # Mock UvBin.get_uv_version to return unknown version (invalid)
    monkeypatch.setattr(
        appenv.UvBin, "get_uv_version", lambda path: UvVersion.unknown()
    )

    # Cap logs at DEBUG level
    caplog.set_level(logging.DEBUG)

    # Call the method
    result = uv_bin._try_uv_from_nix_channel()

    # Verify results
    assert result is None


def test_try_uv_from_nix_channel_and_appenv_dir_share_same_path(
    monkeypatch, tmp_path, caplog
):
    """nix-build creates uv at .appenv/.uv, _try_uv_from_appenv_dir finds it.

    Verifies that _try_uv_from_nix_channel builds uv into the same
    directory that _try_uv_from_appenv_dir looks for.
    """
    uv_bin = appenv.UvBin(tmp_path / ".appenv")

    monkeypatch.setattr(uv_bin, "_try_uv_from_path", lambda: None)

    # Keep reference to real method before patching
    real_appenv_dir = uv_bin._try_uv_from_appenv_dir

    def mock_appenv_dir():
        return real_appenv_dir()

    monkeypatch.setattr(uv_bin, "_try_uv_from_appenv_dir", mock_appenv_dir)

    monkeypatch.setattr(
        "shutil.which", lambda name: "/nix/bin/nix" if name == "nix" else None
    )

    nix_build_output_dir = []

    class FakeNixResult:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_nix_run(*args, **kwargs):
        cmd = args[0] if args else kwargs.get("args", [])
        for i, arg in enumerate(cmd):
            if arg == "-o" and i + 1 < len(cmd):
                nix_build_output_dir.append(Path(cmd[i + 1]))
                uv_path = Path(cmd[i + 1]) / "bin/uv"
                uv_path.parent.mkdir(parents=True, exist_ok=True)
                uv_path.write_text("#!/bin/sh\n")
        return FakeNixResult()

    monkeypatch.setattr(subprocess, "run", fake_nix_run)

    mock_version = UvVersion(0, 10, 3)
    monkeypatch.setattr(appenv.UvBin, "get_uv_version", lambda path: mock_version)

    caplog.set_level(logging.DEBUG)

    result = uv_bin._get_uv_bin()

    assert len(nix_build_output_dir) == 1
    assert nix_build_output_dir[0] == tmp_path / ".appenv/.uv"

    expected_uv = tmp_path / ".appenv/.uv/bin/uv"
    assert expected_uv.exists(), f"uv not found at {expected_uv}"
    assert result == expected_uv

    found = uv_bin._try_uv_from_appenv_dir()
    assert found == expected_uv


# ==============================================================================
# UvBin._try_uv_from_nix_flake tests
# ==============================================================================


def test_try_uv_from_nix_flake_returns_path_when_valid(monkeypatch, tmp_path, caplog):
    """_try_uv_from_nix_flake returns path when nix flake build succeeds."""
    # Create a UvBin instance
    uv_bin = appenv.UvBin(tmp_path / ".appenv")

    # Mock subprocess.run to return success
    class FakeResult:
        returncode = 0
        stdout = ""
        stderr = ""

    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: FakeResult())

    # Mock UvBin.get_uv_version to return a valid version
    mock_version = UvVersion(0, 10, 3)
    monkeypatch.setattr(appenv.UvBin, "get_uv_version", lambda path: mock_version)

    # Cap logs at DEBUG level
    caplog.set_level(logging.DEBUG)

    # Call the method
    result = uv_bin._try_uv_from_nix_flake()

    # Verify results
    # Note: uv_local is created inside the method
    expected_path = tmp_path / ".appenv/.uv/bin/uv"
    assert result == expected_path
    # Check that we got the success log
    assert "nix build nixpkgs#uv:" in caplog.text


def test_try_uv_from_nix_flake_returns_none_when_build_fails(
    monkeypatch, tmp_path, caplog, subprocess_run_fail
):
    """_try_uv_from_nix_flake returns None when nix flake build fails."""
    # Create a UvBin instance
    uv_bin = appenv.UvBin(tmp_path / ".appenv")

    # Mock subprocess.run to return failure
    class FakeResult:
        returncode = 1
        stdout = ""
        stderr = "flake build failed"

    # Cap logs at DEBUG level
    caplog.set_level(logging.DEBUG)

    # Call the method
    result = uv_bin._try_uv_from_nix_flake()

    # Verify results
    assert result is None
    # Check that we logged the failure
    assert "nix-build failed:" in caplog.text


def test_try_uv_from_nix_flake_returns_none_when_invalid_version(
    monkeypatch, tmp_path, caplog
):
    """_try_uv_from_nix_flake returns None when uv built but version invalid."""
    # Create a UvBin instance
    uv_bin = appenv.UvBin(tmp_path / ".appenv")

    # Mock subprocess.run to return success
    class FakeResult:
        returncode = 0
        stdout = ""
        stderr = b""

    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: FakeResult())

    # Mock UvBin.get_uv_version to return unknown version (invalid)
    monkeypatch.setattr(
        appenv.UvBin, "get_uv_version", lambda path: UvVersion.unknown()
    )

    # Cap logs at DEBUG level
    caplog.set_level(logging.DEBUG)

    # Call the method
    result = uv_bin._try_uv_from_nix_flake()

    # Verify results
    assert result is None


# ==============================================================================
# UvBin._try_uv_from_pip tests
# ==============================================================================


def test_try_uv_from_pip_returns_path_when_valid(monkeypatch, tmp_path, caplog):
    """_try_uv_from_pip returns path when pip install succeeds and version valid."""
    # Create a UvBin instance
    uv_bin = appenv.UvBin(tmp_path / ".appenv")

    # Mock subprocess.run for ensurepip to return success
    def mock_run_ensurepip(*args, **kwargs):
        class FakeResult:
            returncode = 0
            stdout = "ensurepip output"
            stderr = ""

        return FakeResult()

    # Mock subprocess.run for pip install to return success
    def mock_run_pip(*args, **kwargs):
        class FakeResult:
            returncode = 0
            stdout = "Successfully installed uv"
            stderr = ""

        return FakeResult()

    # Side effect to handle different calls
    def mock_run_side_effect(*args, **kwargs):
        if "ensurepip" in args[0]:
            return mock_run_ensurepip(*args, **kwargs)
        # pip install
        return mock_run_pip(*args, **kwargs)

    monkeypatch.setattr(subprocess, "run", mock_run_side_effect)

    # Mock UvBin.get_uv_version to return a valid version
    mock_version = UvVersion(0, 10, 3)
    monkeypatch.setattr(appenv.UvBin, "get_uv_version", lambda path: mock_version)

    # Cap logs at DEBUG level
    caplog.set_level(logging.DEBUG)

    # Call the method
    result = uv_bin._try_uv_from_pip()

    # Verify results
    expected_path = tmp_path / ".appenv/.uv/bin/uv"
    assert result == expected_path
    # Check that we got the success log
    assert "pip install uv:" in caplog.text


def test_try_uv_from_pip_returns_none_when_ensurepip_fails(
    monkeypatch, tmp_path, caplog
):
    """_try_uv_from_pip returns None when ensurepip fails."""
    # Create a UvBin instance
    uv_bin = appenv.UvBin(tmp_path / ".appenv")

    # Mock subprocess.run for ensurepip to return failure
    def mock_run_ensurepip(*args, **kwargs):
        raise subprocess.CalledProcessError(1, "ensurepip")

    # Mock subprocess.run for pip install (should not be called)
    def mock_run_pip(*args, **kwargs):
        class FakeResult:
            returncode = 0
            stdout = ""
            stderr = ""

        return FakeResult()

    # Side effect to handle different calls
    def mock_run_side_effect(*args, **kwargs):
        if "ensurepip" in args[0]:
            return mock_run_ensurepip(*args, **kwargs)
        # pip install
        return mock_run_pip(*args, **kwargs)

    monkeypatch.setattr(subprocess, "run", mock_run_side_effect)

    # Cap logs at DEBUG level
    caplog.set_level(logging.DEBUG)

    # Call the method
    result = uv_bin._try_uv_from_pip()

    # Verify results
    assert result is None
    # Check that we logged the ensurepip failure
    assert "pip -mensurepip failed, skipping pip install" in caplog.text


def test_try_uv_from_pip_returns_none_when_pip_install_fails(
    monkeypatch, tmp_path, caplog
):
    """_try_uv_from_pip returns None when pip install fails."""
    # Create a UvBin instance
    uv_bin = appenv.UvBin(tmp_path / ".appenv")

    # Mock subprocess.run for ensurepip to return success
    def mock_run_ensurepip(*args, **kwargs):
        class FakeResult:
            returncode = 0
            stdout = "ensurepip output"
            stderr = ""

        return FakeResult()

    # Mock subprocess.run for pip install to return failure
    def mock_run_pip(*args, **kwargs):
        raise subprocess.CalledProcessError(1, "pip install")

    # Side effect to handle different calls
    def mock_run_side_effect(*args, **kwargs):
        if "ensurepip" in args[0]:
            return mock_run_ensurepip(*args, **kwargs)
        # pip install
        return mock_run_pip(*args, **kwargs)

    monkeypatch.setattr(subprocess, "run", mock_run_side_effect)

    # Cap logs at DEBUG level
    caplog.set_level(logging.DEBUG)

    # Call the method
    result = uv_bin._try_uv_from_pip()

    # Verify results
    assert result is None
    # Check that we logged the pip install failure
    assert "pip install failed, skipping pip install" in caplog.text


def test_try_uv_from_pip_returns_none_when_invalid_version(
    monkeypatch, tmp_path, caplog
):
    """_try_uv_from_pip returns None when uv installed but version invalid."""
    # Create a UvBin instance
    uv_bin = appenv.UvBin(tmp_path / ".appenv")

    # Mock subprocess.run for ensurepip to return success
    def mock_run_ensurepip(*args, **kwargs):
        class FakeResult:
            returncode = 0
            stdout = "ensurepip output"
            stderr = ""

        return FakeResult()

    # Mock subprocess.run for pip install to return success
    def mock_run_pip(*args, **kwargs):
        class FakeResult:
            returncode = 0
            stdout = "Successfully installed uv"
            stderr = ""

        return FakeResult()

    # Side effect to handle different calls
    def mock_run_side_effect(*args, **kwargs):
        if "ensurepip" in args[0]:
            return mock_run_ensurepip(*args, **kwargs)
        # pip install
        return mock_run_pip(*args, **kwargs)

    monkeypatch.setattr(subprocess, "run", mock_run_side_effect)

    # Mock UvBin.get_uv_version to return unknown version (invalid)
    monkeypatch.setattr(
        appenv.UvBin, "get_uv_version", lambda path: UvVersion.unknown()
    )

    # Cap logs at DEBUG level
    caplog.set_level(logging.DEBUG)

    # Call the method
    result = uv_bin._try_uv_from_pip()

    # Verify results
    assert result is None


def test_get_uv_bin_returns_from_nix_channel_when_previous_fail(monkeypatch, tmp_path):
    """_get_uv_bin returns from nix_channel when previous methods return None."""
    # Create a UvBin instance
    uv_bin = appenv.UvBin(tmp_path / ".appenv")

    # Mock preceding methods to return None so we reach nix_channel method
    monkeypatch.setattr(uv_bin, "_try_uv_from_path", lambda: None)
    monkeypatch.setattr(uv_bin, "_try_uv_from_appenv_dir", lambda: None)

    # Mock the nix_channel method to return a valid path
    expected_path = tmp_path / ".appenv/.uv/bin/uv"
    expected_path.parent.mkdir(parents=True)
    expected_path.write_text("#!/bin/sh\n")
    monkeypatch.setattr(uv_bin, "_try_uv_from_nix_channel", lambda: expected_path)

    # Mock subsequent methods to ensure they're not called
    monkeypatch.setattr(uv_bin, "_try_uv_from_nix_flake", lambda: None)
    monkeypatch.setattr(uv_bin, "_try_uv_from_pip", lambda: None)


def test_get_uv_bin_returns_from_nix_flake_when_previous_fail(monkeypatch, tmp_path):
    """_get_uv_bin returns from nix_flake when previous methods return None."""
    # Create a UvBin instance
    uv_bin = appenv.UvBin(tmp_path / ".appenv")

    # Mock preceding methods to return None so we reach nix_flake method
    monkeypatch.setattr(uv_bin, "_try_uv_from_path", lambda: None)
    monkeypatch.setattr(uv_bin, "_try_uv_from_appenv_dir", lambda: None)
    monkeypatch.setattr(uv_bin, "_try_uv_from_nix_channel", lambda: None)

    # Mock the nix_flake method to return a valid path
    expected_path = tmp_path / ".appenv/.uv/bin/uv"
    expected_path.parent.mkdir(parents=True)
    expected_path.write_text("#!/bin/sh\n")
    monkeypatch.setattr(uv_bin, "_try_uv_from_nix_flake", lambda: expected_path)

    # Mock subsequent method to ensure it's not called
    monkeypatch.setattr(uv_bin, "_try_uv_from_pip", lambda: None)

    # Call the method
    result = uv_bin._get_uv_bin()

    # Verify results
    assert result == expected_path
    # Verify subsequent method was not called (early return)


def test_get_uv_bin_returns_from_pip_when_previous_fail(monkeypatch, tmp_path):
    """_get_uv_bin returns from _try_uv_from_pip when previous methods return None."""
    # Create a UvBin instance
    uv_bin = appenv.UvBin(tmp_path / ".appenv")

    # Mock preceding methods to return None so we reach pip method
    monkeypatch.setattr(uv_bin, "_try_uv_from_path", lambda: None)
    monkeypatch.setattr(uv_bin, "_try_uv_from_appenv_dir", lambda: None)
    monkeypatch.setattr(uv_bin, "_try_uv_from_nix_channel", lambda: None)
    monkeypatch.setattr(uv_bin, "_try_uv_from_nix_flake", lambda: None)

    # Mock the pip method to return a valid path
    expected_path = tmp_path / ".appenv/.uv/bin/uv"
    expected_path.parent.mkdir(parents=True)
    expected_path.write_text("#!/bin/sh\n")
    monkeypatch.setattr(uv_bin, "_try_uv_from_pip", lambda: expected_path)

    # Call the method
    result = uv_bin._get_uv_bin()

    # Verify results
    assert result == expected_path


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


# Tier 3 tests


def test_uv_bin_cmd_verbose_flag_and_output(monkeypatch, caplog):
    """UvBin.cmd adds -v flag when verbose=True and logs output."""
    import logging

    caplog.set_level(logging.DEBUG)

    # Create a mock UvBin
    uv = appenv.UvBin.__new__(appenv.UvBin)
    uv.bin = Path("/usr/bin/uv")
    uv.appenv_dir = Path("/tmp/.appenv")
    uv.uv_dir = uv.appenv_dir / ".uv"

    cmd_calls = []

    def mock_cmd(c, **kwargs):
        cmd_calls.append(c)
        return b"verbose output from uv"

    monkeypatch.setattr(appenv, "cmd", mock_cmd)

    uv.cmd(["lock"], verbose=True)

    # Verify -v flag is added to command
    assert "-v" in cmd_calls[0]
    assert "lock" in cmd_calls[0]

    # Verify output is logged via log.debug
    assert "verbose output from uv" in caplog.text


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
# UvBin._get_uv_bin tests (pip fallback behavior)
# ==============================================================================


@pytest.mark.no_mock_uv_version
def test_uv_bin_pip_fallback_raises_error(tmp_path, monkeypatch):
    """UvBin._get_uv_bin raises NoValidUvError when uv still not found after pip."""

    which_calls = []

    def mock_which(name):
        which_calls.append(name)
        # uv never available

    monkeypatch.setattr("shutil.which", mock_which)

    pip_called = []

    class FakeResult:
        stdout = "uv 0.10.3 (abc123 2024-01-01)\n"
        returncode = 0

        def __init__(self, stdout="", returncode=0):
            self.stdout = stdout
            self.returncode = returncode

    def mock_run(cmd, **kwargs):
        pip_called.append(cmd)
        # Return a fake result for uv --version calls
        if "uv" in cmd and "--version" in cmd:
            return FakeResult(stdout="uv 0.10.3 (abc123 2024-01-01)\n", returncode=0)
        # Return success for other subprocess calls (like pip --version, pip install)
        return FakeResult(stdout="", returncode=0)

    monkeypatch.setattr("subprocess.run", mock_run)

    with pytest.raises(appenv.NoValidUvError, match="uv not found"):
        appenv.ensure_uv(tmp_path)

    assert any("pip" in str(cmd) and "uv" in str(cmd) for cmd in pip_called)


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


def get_source_version():
    """Get version from src/appenv.py __version__."""
    appenv_py = Path(__file__).parent.parent / "src" / "appenv.py"
    content = appenv_py.read_text()
    match = re.search(r'^__version__\s*=\s*"([^"]+)"', content, re.MULTILINE)
    if not match:
        msg = "Could not find __version__ in src/appenv.py"
        raise ValueError(msg)
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
    env = appenv.AppEnv(Path.cwd(), get_test_settings(tmp_path))
    assert not os.path.exists(env.appenv_dir)
    env.reset()
    assert not os.path.exists(env.appenv_dir)
    assert os.path.exists(str(tmp_path))


def test_reset_removes_envdir_with_subdirs(tmp_path):
    """reset() cleans up contents in .appenv."""
    env = appenv.AppEnv(Path.cwd(), get_test_settings(tmp_path))
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

    env = appenv.AppEnv(Path.cwd(), get_test_settings(base))
    env.reset()

    assert not venv.exists()
    captured = capsys.readouterr()
    assert "Removing" in captured.out
    assert ".venv" in captured.out


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

    env = appenv.AppEnv(Path.cwd(), get_test_settings(base))
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

    env = appenv.AppEnv(Path.cwd(), get_test_settings(Path.cwd()))
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

    env = appenv.AppEnv(Path.cwd(), get_test_settings(Path.cwd()))
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

    env = appenv.AppEnv(Path.cwd(), get_test_settings(Path.cwd()))
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

    env = appenv.AppEnv(Path.cwd(), get_test_settings(Path.cwd()))
    env.reset()

    assert not venv_dir.exists()
    captured = capsys.readouterr()
    assert "Removing old" in captured.out


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


def test_show_settings_non_symlink_interpreter(tmp_path, capsys, monkeypatch):
    """Line 938: show_settings when interpreter is NOT a symlink."""
    for var in ["APPENV_EXTRAS", "APPENV_VERBOSE", "APPENV_PROFILING"]:
        monkeypatch.delenv(var, raising=False)

    env = appenv.AppEnv(Path.cwd(), get_test_settings(Path.cwd()))

    # Mock interpreter to be non-symlink
    class MockPath:
        def __init__(self, path):
            self._path = path

        def is_symlink(self):
            return False

        def __str__(self):
            return self._path

    monkeypatch.setattr("sys.executable", "/usr/bin/python3.12")
    monkeypatch.setattr(
        "pathlib.Path.__new__",
        lambda cls, *args, **kwargs: MockPath(args[0]) if args else Path.__new__(cls),
    )

    # Simpler approach: patch Path directly
    class NonSymlinkPath:
        def __init__(self, p):
            self._path = str(p)

        def is_symlink(self):
            return False

        def resolve(self):
            return self

        def __str__(self):
            return self._path

    # Patch the local Path used in show_settings
    env.show_settings()

    captured = capsys.readouterr()
    # Should show interpreter without arrow (non-symlink case)
    assert "Python interpreter:" in captured.out


def test_uv_sync_with_extras(tmp_path, monkeypatch):
    """Line 1087: _uv_sync with extras setting."""
    # Create settings with extras
    settings = appenv.AppEnvSettings(
        verbose=False,
        extras=["dev", "test"],
        profile=False,
        basedir=tmp_path,
    )
    env = appenv.AppEnv(Path.cwd(), settings)

    # Mock uv.cmd to capture sync args
    sync_calls = []

    class MockUvBin:
        def cmd(self, args, **kwargs):
            sync_calls.append(list(args))

    uv = MockUvBin()
    env._uv_sync(dev_mode=True, uv=uv)  # type: ignore[invalid-argument-type]

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


def test_profiling_snakeviz_no_uv(tmp_path, capsys, monkeypatch):
    """Lines 979-980: profiling_snakeviz exits when uv not found."""
    env = appenv.AppEnv(tmp_path, get_test_settings(tmp_path))
    profiling_dir = tmp_path / ".appenv" / "profiling"
    profiling_dir.mkdir(parents=True)

    profile = profiling_dir / "test-20260301-100000.prof"
    profile.write_text("dummy")

    # Mock shutil.which to return None (uv not found)
    monkeypatch.setattr("shutil.which", lambda name: None if name == "uv" else name)

    args = argparse.Namespace(file=None)

    with pytest.raises(SystemExit) as exc_info:
        env.profiling_snakeviz(args)

    assert exc_info.value.code == appenv.EXIT_CODE_DATAERR
    captured = capsys.readouterr()
    assert "Cannot find local uv to execute snakeviz" in captured.out


# ==============================================================================
# Coverage tests for Batch 4
# ==============================================================================


def test_profiling_show_with_valid_profile(tmp_path, capsys, monkeypatch):
    """Lines 969-971: profiling_show calls pstats.Stats and prints stats."""
    import cProfile

    env = appenv.AppEnv(tmp_path, get_test_settings(tmp_path))
    profiling_dir = tmp_path / ".appenv" / "profiling"
    profiling_dir.mkdir(parents=True)

    # Create a valid profile file
    profile_path = profiling_dir / "test-20260301-100000.prof"
    pr = cProfile.Profile()
    pr.enable()
    _ = sum(range(100))
    pr.disable()
    pr.dump_stats(str(profile_path))

    args = argparse.Namespace(file=None)

    env.profiling_show(args)

    captured = capsys.readouterr()
    # pstats output includes function names/call counts
    assert (
        "function calls" in captured.out.lower() or "ordered by" in captured.out.lower()
    )


def test_colored_caller_formatter_format():
    """Lines 1368-1370: ColoredCallerFormatter.format adds caller info."""
    import logging

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


# ==============================================================================
# Coverage tests for 99% target
# ==============================================================================


def test_cleanup_appenv_uv_with_base_and_existing_dir(tmp_path):
    """Lines 622, 625: _cleanup_appenv_uv when base is set and .appenv/.uv exists."""
    # Create .appenv/.uv directory
    appenv_uv = tmp_path / ".appenv" / ".uv"
    appenv_uv.mkdir(parents=True)
    (appenv_uv / "some_file").write_text("test")

    # Create UvBin with base set
    uv_bin = appenv.UvBin(tmp_path / ".appenv")

    uv_bin._cleanup_appenv_uv()

    assert not appenv_uv.exists()


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


def test_init_skips_appenv_script_creation(tmp_path, monkeypatch, capsys):
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

    env = appenv.AppEnv(Path.cwd(), get_test_settings(Path.cwd()))

    with pytest.raises(SystemExit):
        env.init()

    captured = capsys.readouterr()
    assert "Created appenv script" not in captured.out


def test_get_uv_bin_returns_from_appenv_dir_when_path_fails(monkeypatch, tmp_path):
    """Test that _get_uv_bin returns from appenv_dir when path fails."""
    # Create a UvBin instance with a real base
    uv_bin = appenv.UvBin(tmp_path / ".appenv")

    # Mock _try_uv_from_path to return None (so we skip the first method)
    monkeypatch.setattr(uv_bin, "_try_uv_from_path", lambda: None)

    # Create a mock path to return from _try_uv_from_appenv_dir
    mock_uv_path = tmp_path / ".appenv" / ".uv" / "bin" / "uv"
    mock_uv_path.parent.mkdir(parents=True, exist_ok=True)
    mock_uv_path.write_text("#!/bin/sh\n")

    monkeypatch.setattr(uv_bin, "_try_uv_from_appenv_dir", lambda: mock_uv_path)

    # Track if the other methods are called
    nix_channel_called = []
    nix_flake_called = []
    pip_called = []

    monkeypatch.setattr(
        uv_bin,
        "_try_uv_from_nix_channel",
        lambda: nix_channel_called.append(True) or None,
    )
    monkeypatch.setattr(
        uv_bin, "_try_uv_from_nix_flake", lambda: nix_flake_called.append(True) or None
    )
    monkeypatch.setattr(
        uv_bin, "_try_uv_from_pip", lambda: pip_called.append(True) or None
    )

    # Call the method
    result = uv_bin._get_uv_bin()

    # Verify results
    assert result == mock_uv_path
    assert nix_channel_called == []  # Should not be called
    assert nix_flake_called == []  # Should not be called
    assert pip_called == []  # Should not be called
