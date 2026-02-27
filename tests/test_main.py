"""Tests for main() entry point and related functions."""

import argparse
import os
import re
import subprocess
import sys
from importlib.metadata import version as get_metadata_version
from pathlib import Path

import pytest

import appenv


def mock_ensure_python(monkeypatch):
    """Mock ensure_best_python to prevent re-exec."""
    monkeypatch.setattr(appenv, "ensure_best_python", lambda base: None)


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
    appenv._uv_bin_cache = None  # Reset cache
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


def test_get_uv_bin_uses_pip_fallback(monkeypatch, tmp_path):
    """get_uv_bin installs uv via pip if not in PATH and no nix."""
    appenv._uv_bin_cache = None  # Reset cache
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


# python() method tests


def test_python_method_calls_run(monkeypatch, tmp_path):
    env = appenv.AppEnv(tmp_path, Path.cwd())

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
    assert versions == ["3.14", "3.13", "3.12", "3.11", "3.10", "3.9"]


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


def test_python_function_delegates(monkeypatch, tmp_path):
    """python() function delegates to cmd() with correct arguments."""
    cmd_called = []

    def mock_cmd(c, **kwargs):
        cmd_called.append((c, kwargs))
        return b"Python 3.12.0"

    monkeypatch.setattr(appenv, "cmd", mock_cmd)

    path = tmp_path
    result = appenv.python(path, ["--version"])

    assert cmd_called[0][0] == [str(path / "bin" / "python"), "--version"]
    assert result == b"Python 3.12.0"


def test_run_script_delegates(monkeypatch, tmp_path):
    """run_script() delegates to AppEnv.run() with script name."""
    env = appenv.AppEnv(tmp_path, Path.cwd())

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
# check_uv_version tests (from test_coverage.py)
# ==============================================================================


def test_check_uv_version_returns_version_on_success(tmp_path, monkeypatch):
    """Line 285: Returns version tuple on successful version check."""
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/uv")
    appenv._uv_bin_cache = "/usr/bin/uv"

    class FakeResult:
        stdout = "uv 0.10.3 (abc123 2024-01-01)\n"
        returncode = 0

    monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: FakeResult())

    result = appenv.check_uv_version()

    assert result == (0, 10, 3)
    appenv._uv_bin_cache = None


def test_check_uv_version_handles_parse_error(tmp_path, monkeypatch, capsys):
    """Lines 290-291: Handles IndexError/ValueError during version parse."""
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/uv")
    appenv._uv_bin_cache = "/usr/bin/uv"

    class FakeResult:
        stdout = "uv invalid-version\n"
        returncode = 0

    monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: FakeResult())

    with pytest.raises(SystemExit) as err:
        appenv.check_uv_version()

    assert err.value.code == 68
    captured = capsys.readouterr()
    assert "too old" in captured.out
    appenv._uv_bin_cache = None


def test_check_uv_version_index_error_on_split(monkeypatch, capsys):
    """Lines 290-291: IndexError when version output has no second element."""
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/uv")
    appenv._uv_bin_cache = "/usr/bin/uv"

    class FakeResult:
        # Single word output - split()[1] will raise IndexError
        stdout = "uv\n"
        returncode = 0

    monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: FakeResult())

    result = appenv.check_uv_version()

    # Returns (0, 0, 0) when parsing fails (caught at lines 289-291)
    assert result == (0, 0, 0)
    captured = capsys.readouterr()
    assert "Could not parse uv version" in captured.out
    appenv._uv_bin_cache = None


# ==============================================================================
# get_uv_bin tests (from test_coverage.py)
# ==============================================================================


def test_get_uv_bin_pip_fallback_success(tmp_path, monkeypatch):
    """Lines 333-334: pip install fallback returns uv path."""
    appenv._uv_bin_cache = None

    which_calls = []

    def mock_which(name):
        which_calls.append(name)
        if name == "uv":
            return "/usr/local/bin/uv" if len(which_calls) > 1 else None
        return None

    monkeypatch.setattr("shutil.which", mock_which)

    pip_called = []

    def mock_run(cmd, **kwargs):
        pip_called.append(cmd)

    monkeypatch.setattr("subprocess.run", mock_run)

    result = appenv.get_uv_bin(tmp_path)

    assert result == "/usr/local/bin/uv"
    assert any("pip" in str(cmd) and "uv" in str(cmd) for cmd in pip_called)
    appenv._uv_bin_cache = None


# ==============================================================================
# main entry point tests (from test_coverage.py)
# ==============================================================================


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
    monkeypatch.setattr(appenv.AppEnv, "meta", lambda self: None)
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
    """Ensure __version__, importlib.metadata and ./appenv version match."""
    source_version = get_source_version()
    metadata_version = get_metadata_version("appenv")
    appenv_version = get_appenv_version()

    assert source_version == metadata_version == appenv_version, (
        f"Version mismatch: __version__={source_version}, "
        f"metadata={metadata_version}, appenv={appenv_version}"
    )


# ==============================================================================
# reset tests (from test_reset.py)
# ==============================================================================


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
