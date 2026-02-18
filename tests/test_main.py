"""Tests for main() entry point and related functions."""

import argparse
import os
from pathlib import Path

import pytest

import appenv


def mock_ensure_python(monkeypatch):
    """Mock ensure_best_python_for_pyproject to prevent re-exec."""
    monkeypatch.setattr(appenv, "ensure_best_python_for_pyproject", lambda base: None)


# main() tests


def test_main_shows_usage_without_subcommand(monkeypatch, capsys):
    mock_ensure_python(monkeypatch)
    monkeypatch.setattr("sys.argv", ["appenv"])

    appenv.main()

    captured = capsys.readouterr()
    assert "usage:" in captured.out.lower()


def test_main_clears_pythonpath(monkeypatch):
    mock_ensure_python(monkeypatch)
    monkeypatch.setattr("sys.argv", ["appenv"])

    monkeypatch.setenv("PYTHONPATH", "/some/path")
    assert "PYTHONPATH" in os.environ

    appenv.main()

    assert "PYTHONPATH" not in os.environ


def test_main_calls_run_when_not_appenv(monkeypatch, tmpdir):
    mock_ensure_python(monkeypatch)

    app_file = tmpdir / "myapp"
    app_file.write("#!/usr/bin/env python3\nprint('test')\n")

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
    monkeypatch.setattr(appenv.AppEnv, "meta", lambda self: meta_called.append(True))

    monkeypatch.setattr("sys.argv", ["appenv"])
    monkeypatch.setattr(appenv, "__file__", "/some/path/appenv")

    appenv.main()

    assert meta_called == [True]


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
    monkeypatch.setattr("shutil.which", lambda name: None)

    with pytest.raises(RuntimeError, match="uv not found"):
        appenv.uv_cmd(["--version"])


def test_get_uv_bin_uses_path(monkeypatch):
    """get_uv_bin returns uv from PATH if available."""
    appenv._uv_bin_cache = None  # Reset cache
    monkeypatch.setattr(
        "shutil.which", lambda name: "/usr/bin/uv" if name == "uv" else None
    )
    assert appenv.get_uv_bin() == "/usr/bin/uv"


def test_get_uv_bin_uses_pip_fallback(monkeypatch, tmpdir):
    """get_uv_bin installs uv via pip if not in PATH and no nix."""
    appenv._uv_bin_cache = None  # Reset cache
    monkeypatch.setattr("shutil.which", lambda name: None)  # no uv, no nix

    pip_called = []
    monkeypatch.setattr(
        "subprocess.run",
        lambda cmd, **kwargs: pip_called.append(cmd),
    )

    with pytest.raises(RuntimeError, match="uv not found"):
        appenv.get_uv_bin(Path(tmpdir))

    assert any("pip" in str(cmd) and "uv" in str(cmd) for cmd in pip_called)


# meta() tests


def test_meta_calls_reset(monkeypatch, tmpdir):
    env = appenv.AppEnv(Path(tmpdir), Path.cwd())
    monkeypatch.setattr("sys.argv", ["appenv", "reset"])

    reset_called = []
    monkeypatch.setattr(
        env, "reset", lambda args=None, remaining=None: reset_called.append(True)
    )

    env.meta()

    assert reset_called == [True]


def test_meta_calls_prepare(monkeypatch, tmpdir):
    env = appenv.AppEnv(Path(tmpdir), Path.cwd())
    monkeypatch.setattr("sys.argv", ["appenv", "prepare"])

    prepare_called = []
    monkeypatch.setattr(
        env,
        "prepare",
        lambda args=None, remaining=None: prepare_called.append(True),
    )

    env.meta()

    assert prepare_called == [True]


def test_meta_calls_python(monkeypatch, tmpdir):
    env = appenv.AppEnv(Path(tmpdir), Path.cwd())
    monkeypatch.setattr("sys.argv", ["appenv", "python"])

    python_called = []
    monkeypatch.setattr(
        env,
        "python",
        lambda args, remaining: python_called.append((args, remaining)),
    )

    env.meta()

    assert len(python_called) == 1


def test_meta_calls_run_script(monkeypatch, tmpdir):
    env = appenv.AppEnv(Path(tmpdir), Path.cwd())
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


def test_run_sets_env_and_execs(monkeypatch, tmpdir):
    env = appenv.AppEnv(Path(tmpdir), Path.cwd())

    env_dir = tmpdir.mkdir(".appenv").mkdir("abc123")
    bin_dir = env_dir.mkdir("bin")
    bin_dir.join("myapp").write("#!/bin/sh\necho hello\n")

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


# python() method tests


def test_python_method_calls_run(monkeypatch, tmpdir):
    env = appenv.AppEnv(Path(tmpdir), Path.cwd())

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
    assert "-line2" in captured.out
    assert "+line3" in captured.out


def test_print_colored_diff_returns_false_when_no_changes(capsys):
    content = "line1\nline2\n"

    result = appenv.print_colored_diff(content, content, "same.txt", "same.txt")

    assert result is False
    captured = capsys.readouterr()
    assert captured.out == ""


def test_print_colored_diff_shows_filenames(capsys):
    old = "a\n"
    new = "b\n"

    appenv.print_colored_diff(old, new, "oldfile.txt", "newfile.txt")

    captured = capsys.readouterr()
    assert "oldfile.txt" in captured.out
    assert "newfile.txt" in captured.out


# ensure_uv_version() tests


def test_ensure_uv_version_exits_when_too_old(monkeypatch, capsys):
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/uv")

    # Mock subprocess.run to return old version
    class FakeResult:
        stdout = "uv 0.4.0 (abc123 2024-01-01)\n"
        returncode = 0

    monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: FakeResult())

    with pytest.raises(SystemExit) as err:
        appenv.ensure_uv_version()

    assert err.value.code == 68
    captured = capsys.readouterr()
    assert "too old" in captured.out
    assert "0.5.0" in captured.out


def test_check_uv_version_returns_zero_on_subprocess_error(monkeypatch, capsys):
    """When uv --version fails, check_uv_version returns (0,0,0) without exiting."""
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/uv")

    import subprocess

    def fake_run(*args, **kwargs):
        raise subprocess.CalledProcessError(1, "uv --version")

    monkeypatch.setattr("subprocess.run", fake_run)

    result = appenv.check_uv_version()

    assert result == (0, 0, 0)
    captured = capsys.readouterr()
    assert "Warning" in captured.out


def test_check_uv_version_exits_on_parse_error(monkeypatch, capsys):
    """When version string is unparseable, parse_uv_version returns (0,0,0)
    which is < UV_MIN_VERSION, so check_uv_version exits."""
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/uv")

    class FakeResult:
        stdout = "uv invalid-version\n"
        returncode = 0

    monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: FakeResult())

    with pytest.raises(SystemExit) as err:
        appenv.check_uv_version()

    assert err.value.code == 68
    captured = capsys.readouterr()
    assert "too old" in captured.out


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
    """find_available_pythons returns versions sorted newest-first."""

    # Mock shutil.which to return paths for specific versions
    def mock_which(name):
        versions = {
            "python3.8": "/usr/bin/python3.8",
            "python3.10": "/usr/bin/python3.10",
            "python3.12": "/usr/bin/python3.12",
            "python3.9": "/usr/bin/python3.9",
        }
        return versions.get(name)

    monkeypatch.setattr("shutil.which", mock_which)

    result = appenv.find_available_pythons()

    # Should be sorted newest first
    versions = [v for v, _ in result]
    assert versions == ["3.12", "3.10", "3.9", "3.8"]


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


def test_python_function_delegates(monkeypatch, tmpdir):
    """python() function delegates to cmd() with correct arguments."""
    cmd_called = []

    def mock_cmd(c, **kwargs):
        cmd_called.append((c, kwargs))
        return b"Python 3.12.0"

    monkeypatch.setattr(appenv, "cmd", mock_cmd)

    path = Path(tmpdir)
    result = appenv.python(path, ["--version"])

    assert cmd_called[0][0] == [str(path / "bin" / "python"), "--version"]
    assert result == b"Python 3.12.0"


def test_run_script_delegates(monkeypatch, tmpdir):
    """run_script() delegates to AppEnv.run() with script name."""
    env = appenv.AppEnv(Path(tmpdir), Path.cwd())

    run_called = []
    monkeypatch.setattr(env, "run", lambda cmd, argv: run_called.append((cmd, argv)))

    env.run_script(argparse.Namespace(script="pytest"), ["-v", "test.py"])

    assert run_called == [("pytest", ["-v", "test.py"])]


def test_show_version(capsys):
    """show_version() prints the appenv version."""
    env = appenv.AppEnv(Path("/tmp"), Path.cwd())
    env.show_version()

    captured = capsys.readouterr()
    assert "appenv" in captured.out
    assert appenv.__version__ in captured.out


def test_check_uv_version_not_found(monkeypatch):
    """check_uv_version raises RuntimeError when uv not in PATH."""
    monkeypatch.setattr("shutil.which", lambda name: None)
    # Reset cache
    appenv._uv_bin_cache = None

    with pytest.raises(RuntimeError, match="uv not found"):
        appenv.check_uv_version()


# Tier 2: Moderate Effort


def test_parse_requires_python_edge_cases(tmpdir):
    """parse_requires_python handles non-existent file and various regex formats."""
    base = Path(tmpdir)

    # Non-existent file returns (None, None)
    result = appenv.parse_requires_python(base / "nonexistent.toml")
    assert result == (None, None)

    pyproject = base / "pyproject.toml"

    # Format: >=3.8 (no space around operators)
    pyproject.write_text('requires-python = ">=3.8"\n')
    assert appenv.parse_requires_python(pyproject) == ("3.8", None)

    # Format: = "3.9" (with space after = and before value)
    pyproject.write_text('requires-python = ">=3.9"\n')
    assert appenv.parse_requires_python(pyproject) == ("3.9", None)

    # Format: >3.10 (greater than, not >=) - regex handles >=? so just > matches
    pyproject.write_text("requires-python = '>3.10'\n")
    assert appenv.parse_requires_python(pyproject) == ("3.10", None)

    # Format with extra whitespace around = (regex allows \s*)
    pyproject.write_text('requires-python=">=3.11"\n')
    assert appenv.parse_requires_python(pyproject) == ("3.11", None)

    # No match returns (None, None)
    pyproject.write_text("name = 'test'\n")
    assert appenv.parse_requires_python(pyproject) == (None, None)


def test_parse_requires_python_with_upper_bound(tmpdir):
    """parse_requires_python handles upper bounds like >=3.11,<3.15."""
    base = Path(tmpdir)
    pyproject = base / "pyproject.toml"

    # Format: >=3.11,<3.15
    pyproject.write_text('requires-python = ">=3.11,<3.15"\n')
    assert appenv.parse_requires_python(pyproject) == ("3.11", "3.15")

    # Format: >=3.11.0,<3.15.0 (with patch version)
    pyproject.write_text('requires-python = ">=3.11.0,<3.15.0"\n')
    assert appenv.parse_requires_python(pyproject) == ("3.11", "3.15")

    # Format: >=3.8,<=3.12 (inclusive upper bound)
    pyproject.write_text('requires-python = ">=3.8,<=3.12"\n')
    assert appenv.parse_requires_python(pyproject) == ("3.8", "3.12")

    # Format with spaces: >= 3.11, < 3.15
    pyproject.write_text('requires-python = ">= 3.11, < 3.15"\n')
    assert appenv.parse_requires_python(pyproject) == ("3.11", "3.15")


# Tier 3 tests


def test_uv_cmd_verbose_flag_and_output(monkeypatch, capsys):
    """uv_cmd adds -v flag when verbose=True and prints output."""
    monkeypatch.setenv("APPENV_VERBOSE", "1")
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/uv")
    appenv._uv_bin_cache = "/usr/bin/uv"

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
    appenv._uv_bin_cache = None
