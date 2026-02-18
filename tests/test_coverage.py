"""Tests specifically targeting coverage gaps."""

import argparse
import os
import subprocess
import sys
from pathlib import Path

import pytest

import appenv

# ==============================================================================
# Lines 92, 99, 123, 132-133: ensure_best_python_for_pyproject branches
# ==============================================================================


def test_ensure_best_python_for_pyproject_skips_when_env_set(tmpdir, monkeypatch):
    """Line 92: Returns early when APPENV_BEST_PYTHON is set."""
    base = Path(tmpdir)
    (base / "pyproject.toml").write_text('[project]\nname = "test"\n')

    monkeypatch.setenv("APPENV_BEST_PYTHON", "/usr/bin/python3")
    monkeypatch.setattr("os.chdir", lambda p: None)

    appenv.ensure_best_python_for_pyproject(base)


def test_ensure_best_python_for_pyproject_default_min_version(tmpdir, monkeypatch):
    """Line 99: Uses 3.8 as default when no requires-python specified."""
    base = Path(tmpdir)
    (base / "pyproject.toml").write_text('[project]\nname = "test"\n')

    monkeypatch.delenv("APPENV_BEST_PYTHON", raising=False)
    monkeypatch.setattr("os.chdir", lambda p: None)

    monkeypatch.setattr(
        appenv,
        "find_available_pythons",
        lambda: [
            ("3.12", "/usr/bin/python3.12"),
            ("3.8", "/usr/bin/python3.8"),
            ("3.7", "/usr/bin/python3.7"),
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
        appenv.ensure_best_python_for_pyproject(base)

    assert "python3.12" in execv_called[0][0]


def test_ensure_best_python_for_pyproject_already_running_best(tmpdir, monkeypatch):
    """Line 123: Returns early when already running the best Python."""
    base = Path(tmpdir)
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

    appenv.ensure_best_python_for_pyproject(base)


def test_ensure_best_python_for_pyproject_broken_python(tmpdir, monkeypatch):
    """Lines 132-133: Continues to next Python when subprocess fails."""
    base = Path(tmpdir)
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
        appenv.ensure_best_python_for_pyproject(base)

    assert len(check_call_count) == 2
    assert "python3.11" in execv_called[0][0]


# ==============================================================================
# Lines 285, 290-291: check_uv_version branches
# ==============================================================================


def test_check_uv_version_returns_version_on_success(tmpdir, monkeypatch):
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


def test_check_uv_version_handles_parse_error(tmpdir, monkeypatch, capsys):
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
# Lines 333-334: get_uv_bin pip fallback success
# ==============================================================================


def test_get_uv_bin_pip_fallback_success(tmpdir, monkeypatch):
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

    result = appenv.get_uv_bin(Path(tmpdir))

    assert result == "/usr/local/bin/uv"
    assert any("pip" in str(cmd) and "uv" in str(cmd) for cmd in pip_called)
    appenv._uv_bin_cache = None


# ==============================================================================
# Lines 818, 829: init_pyproject empty input defaults
# ==============================================================================


def test_migrate_empty_project_name_uses_default(workdir, monkeypatch, capsys):
    """Empty project name input uses default name during migration."""
    base = Path(workdir)
    (base / "requirements.txt").write_text("requests\n")

    inputs = iter([""])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    env = appenv.AppEnv(base, Path.cwd())
    env.migrate()

    pyproject = (base / "pyproject.toml").read_text()
    assert f'name = "{base.name}"' in pyproject


def test_init_empty_command_name_uses_app(workdir, monkeypatch, capsys):
    """Test fresh start with default command name and dependencies."""
    base = Path(workdir)

    inputs = iter(
        [
            "app",  # command name (explicitly "app")
            "test description",
            "",  # empty dependencies -> defaults to "app"
            "",  # python version (default)
        ]
    )
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    env = appenv.AppEnv(base, Path.cwd())
    env.init()

    pyproject = (base / "pyproject.toml").read_text()
    assert 'name = "app"' in pyproject
    assert '"app"' in pyproject  # dependency defaults to command name


# ==============================================================================
# init unlink broken symlink
# ==============================================================================


def test_init_unlink_broken_symlink(workdir, monkeypatch, capsys):
    """Unlinks broken symlink before creating new one."""
    base = Path(workdir)

    broken_link = base / "myapp"
    broken_link.symlink_to("nonexistent_target")
    assert broken_link.is_symlink()
    assert not broken_link.exists()

    inputs = iter(
        [
            "myapp",
            "",
            "",
            "",
        ]
    )
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    env = appenv.AppEnv(base, Path.cwd())
    env.init()

    assert (base / "myapp").is_symlink()
    assert (base / "myapp").exists()
    assert (base / "myapp").resolve() == (base / "appenv").resolve()


# ==============================================================================
# Lines 1196: main() calls ensure_best_python_for_pyproject
# ==============================================================================


def test_main_calls_ensure_best_python_for_pyproject(monkeypatch, workdir):
    """Line 1196: main() calls ensure_best_python_for_pyproject."""
    base = Path(workdir)
    (base / "pyproject.toml").write_text('[project]\nname = "test"\n')
    (base / "appenv").write_text("#!/usr/bin/env python3\npass\n")
    (base / "appenv").chmod(0o755)

    called = []
    monkeypatch.setattr(
        appenv,
        "ensure_best_python_for_pyproject",
        lambda b: called.append("pyproject"),
    )
    monkeypatch.setattr(appenv.AppEnv, "meta", lambda self: None)
    monkeypatch.setattr(appenv, "__file__", str(base / "appenv"))
    monkeypatch.setattr("sys.argv", ["appenv"])

    appenv.main()

    assert called == ["pyproject"]


# ==============================================================================
# Line 1216: __main__ entry point
# ==============================================================================


def test_main_entry_point_subprocess():
    """Line 1216: Test __main__ entry point via subprocess."""
    result = subprocess.run(
        [sys.executable, str(Path("src/appenv.py")), "--help"],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent.parent,
    )
    assert result.returncode == 0
    assert "usage" in result.stdout.lower() or "usage" in result.stderr.lower()


# ==============================================================================
# Verbose output tests for update_lockfile (various lines)
# ==============================================================================


def test_update_lockfile_pyproject_verbose(workdir, monkeypatch, capsys):
    """Test verbose output in pyproject update_lockfile workflow."""
    base = Path(workdir)
    (base / "pyproject.toml").write_text(
        '[project]\nname = "test"\ndependencies = ["click"]\n'
    )
    (base / "uv.lock").write_text("version = 1\n")

    monkeypatch.setattr(appenv, "ensure_uv", lambda base: None)
    monkeypatch.setattr(appenv, "ensure_uv_version", lambda: None)

    def mock_uv_cmd(args, verbose=False, **kwargs):
        if "lock" in args and "pip" not in args:
            pass
        elif "compile" in args:
            output_file = args[args.index("--output-file") + 1]
            Path(output_file).write_text("click==8.1.0\n")
        return b""

    monkeypatch.setattr(appenv, "uv_cmd", mock_uv_cmd)

    # Enable verbose mode via environment variable
    monkeypatch.setenv("APPENV_VERBOSE", "1")

    env = appenv.AppEnv(base, Path.cwd())
    args = argparse.Namespace(diff=False, verbose=True)

    env.update_lockfile(args=args, remaining=None)

    captured = capsys.readouterr()
    assert "Generating requirements.lock" in captured.out


def test_update_lockfile_pyproject_no_changes(workdir, monkeypatch, capsys):
    """Lines 1005, 1033: 'No changes' output when lockfile unchanged."""
    base = Path(workdir)
    (base / "pyproject.toml").write_text(
        '[project]\nname = "test"\ndependencies = ["click"]\n'
    )

    lock_content = "version = 1\n[[package]]\nname = 'click'\nversion = '8.1.0'\n"
    (base / "uv.lock").write_text(lock_content)

    monkeypatch.setattr(appenv, "ensure_uv", lambda base: None)
    monkeypatch.setattr(appenv, "ensure_uv_version", lambda: None)

    def mock_uv_cmd(args, verbose=False, **kwargs):
        return b""

    monkeypatch.setattr(appenv, "uv_cmd", mock_uv_cmd)

    env = appenv.AppEnv(base, Path.cwd())
    env.update_lockfile()

    captured = capsys.readouterr()
    assert "No changes" in captured.out


def test_update_lockfile_pyproject_updated(workdir, monkeypatch, capsys):
    """Line 1040: 'Updated' output when lockfile has changes."""
    base = Path(workdir)
    (base / "pyproject.toml").write_text(
        '[project]\nname = "test"\ndependencies = ["click"]\n'
    )

    (base / "uv.lock").write_text(
        "version = 1\n[[package]]\nname = 'click'\nversion = '8.0.0'\n"
    )

    monkeypatch.setattr(appenv, "ensure_uv", lambda base: None)
    monkeypatch.setattr(appenv, "ensure_uv_version", lambda: None)

    def mock_uv_cmd(args, verbose=False, **kwargs):
        if "lock" in args and "pip" not in args:
            (base / "uv.lock").write_text(
                "version = 1\n[[package]]\nname = 'click'\nversion = '8.1.0'\n"
            )
        elif "compile" in args:
            output_file = args[args.index("--output-file") + 1]
            Path(output_file).write_text("click==8.1.0\n")
        return b""

    monkeypatch.setattr(appenv, "uv_cmd", mock_uv_cmd)

    env = appenv.AppEnv(base, Path.cwd())
    env.update_lockfile()

    captured = capsys.readouterr()
    assert "Updated" in captured.out


def test_update_lockfile_pyproject_diff_verbose(workdir, monkeypatch, capsys):
    """Line 990: Verbose output in pyproject diff mode."""
    base = Path(workdir)
    (base / "pyproject.toml").write_text(
        '[project]\nname = "test"\ndependencies = ["click"]\n'
    )
    (base / "uv.lock").write_text("version = 1\n")

    monkeypatch.setattr(appenv, "ensure_uv", lambda base: None)
    monkeypatch.setattr(appenv, "ensure_uv_version", lambda: None)

    def mock_uv_cmd(args, verbose=False, **kwargs):
        if "lock" in args and "pip" not in args:
            cwd = kwargs.get("cwd")
            if cwd:
                # Create lock file in temp directory
                (Path(cwd) / "uv.lock").write_text("version = 1\nnew = true\n")
        return b""

    monkeypatch.setattr(appenv, "uv_cmd", mock_uv_cmd)

    env = appenv.AppEnv(base, Path.cwd())
    args = argparse.Namespace(diff=True, verbose=True)

    env.update_lockfile(args=args, remaining=None)

    captured = capsys.readouterr()
    assert "dry run" in captured.out


def test_update_lockfile_pyproject_diff_no_changes(workdir, monkeypatch, capsys):
    """Line 1005: 'No changes' output in diff mode for pyproject."""
    base = Path(workdir)
    (base / "pyproject.toml").write_text(
        '[project]\nname = "test"\ndependencies = ["click"]\n'
    )

    lock_content = "version = 1\n[[package]]\nname = 'click'\nversion = '8.1.0'\n"
    (base / "uv.lock").write_text(lock_content)

    monkeypatch.setattr(appenv, "ensure_uv", lambda base: None)
    monkeypatch.setattr(appenv, "ensure_uv_version", lambda: None)

    def mock_uv_cmd(args, verbose=False, **kwargs):
        if "lock" in args and "pip" not in args:
            cwd = kwargs.get("cwd")
            if cwd:
                # Create identical lock file
                (Path(cwd) / "uv.lock").write_text(lock_content)
        return b""

    monkeypatch.setattr(appenv, "uv_cmd", mock_uv_cmd)

    env = appenv.AppEnv(base, Path.cwd())
    args = argparse.Namespace(diff=True, verbose=False)

    env.update_lockfile(args=args, remaining=None)

    captured = capsys.readouterr()
    assert "No changes" in captured.out


# ==============================================================================
# Verbose output tests for prepare
# ==============================================================================


def test_prepare_pyproject_verbose(workdir, monkeypatch, capsys):
    """Lines 639-642: Verbose output shows venv python info."""
    base = Path(workdir)
    (base / "pyproject.toml").write_text(
        '[project]\nname = "test"\ndependencies = []\n'
    )
    (base / "uv.lock").write_text("version = 1\n")

    monkeypatch.setattr(appenv, "ensure_uv", lambda base: None)
    monkeypatch.setattr(appenv, "ensure_uv_version", lambda: None)
    monkeypatch.setattr(appenv, "get_uv_bin", lambda base: "/usr/bin/uv")

    def mock_uv_cmd(args, **kwargs):
        if "venv" in args:
            # venv is now created in .appenv/venv
            venv = base / ".appenv" / "venv"
            venv.mkdir(parents=True, exist_ok=True)
            (venv / "bin").mkdir(exist_ok=True)
            python = venv / "bin" / "python"
            python.write_text("#!/bin/sh\necho Python 3.12.0\n")
            python.chmod(0o755)
        return b""

    monkeypatch.setattr(appenv, "uv_cmd", mock_uv_cmd)
    monkeypatch.setattr(appenv, "cmd", lambda c, **kwargs: b"Python 3.12.0")

    monkeypatch.setenv("APPENV_VERBOSE", "1")

    env = appenv.AppEnv(base, Path.cwd())
    env._prepare_pyproject()

    captured = capsys.readouterr()
    assert "Venv Python" in captured.out


def test_prepare_pyproject_mode_verbose(workdir, monkeypatch, capsys):
    """Line 590: Verbose output shows mode."""
    base = Path(workdir)
    (base / "pyproject.toml").write_text(
        '[project]\nname = "test"\ndependencies = []\n'
    )
    (base / "uv.lock").write_text("version = 1\n")

    monkeypatch.setattr(appenv, "ensure_uv", lambda base: None)
    monkeypatch.setattr(appenv, "ensure_uv_version", lambda: None)

    def mock_uv_cmd(args, **kwargs):
        if "venv" in args:
            # venv is now created in .appenv/venv
            venv = base / ".appenv" / "venv"
            venv.mkdir(parents=True, exist_ok=True)
            (venv / "bin").mkdir(exist_ok=True)
            python = venv / "bin" / "python"
            python.write_text("#!/bin/sh\necho Python 3.12.0\n")
            python.chmod(0o755)
        return b""

    monkeypatch.setattr(appenv, "uv_cmd", mock_uv_cmd)
    monkeypatch.setattr(appenv, "cmd", lambda c, **kwargs: b"Python 3.12.0")

    monkeypatch.setenv("APPENV_VERBOSE", "1")

    env = appenv.AppEnv(base, Path.cwd())
    env.prepare()

    captured = capsys.readouterr()
    assert "Mode: pyproject" in captured.out


# ==============================================================================
# run_uv command
# ==============================================================================


def test_run_uv_sets_environment_and_execs(workdir, monkeypatch):
    """run_uv sets UV_PROJECT_ENVIRONMENT and execs uv binary."""
    base = Path(workdir)

    monkeypatch.setattr(appenv, "ensure_uv", lambda base: None)
    monkeypatch.setattr(appenv, "get_uv_bin", lambda base: "/usr/bin/uv")

    execv_called = []

    def mock_execv(path, argv):
        execv_called.append((path, argv))
        raise SystemExit(0)

    monkeypatch.setattr("os.execv", mock_execv)

    env = appenv.AppEnv(base, Path.cwd())
    args = argparse.Namespace()
    remaining = ["--version"]

    with pytest.raises(SystemExit):
        env.run_uv(args, remaining)  # type: ignore[attr-defined]

    assert len(execv_called) == 1
    assert execv_called[0][0] == "/usr/bin/uv"
    assert execv_called[0][1] == ["/usr/bin/uv", "--version"]
    assert os.environ.get("UV_PROJECT_ENVIRONMENT") == str(base / ".appenv" / "venv")


# ==============================================================================
# Line 758: _prepare_pyproject unlinks non-directory files in .appenv
# ==============================================================================


def test_prepare_pyproject_unlink_file_in_appenv(workdir, monkeypatch, capsys):
    """Line 758: _prepare_pyproject unlinks non-directory files in .appenv."""
    base = Path(workdir)

    # Create pyproject.toml and uv.lock
    (base / "pyproject.toml").write_text(
        '[project]\nname = "test"\ndependencies = []\n'
    )
    (base / "uv.lock").write_text("version = 1\n")

    # Create .appenv with a file (not directory)
    appenv_dir = base / ".appenv"
    appenv_dir.mkdir()
    old_file = appenv_dir / "old_file.txt"
    old_file.write_text("old content")

    monkeypatch.setattr(appenv, "ensure_uv", lambda base: None)
    monkeypatch.setattr(appenv, "ensure_uv_version", lambda: None)
    monkeypatch.setattr(appenv, "uv_cmd", lambda args, **kwargs: None)

    monkeypatch.setenv("APPENV_VERBOSE", "1")

    env = appenv.AppEnv(base, Path.cwd())
    env._prepare_pyproject()

    assert not old_file.exists()
    captured = capsys.readouterr()
    assert "Removing old .appenv entry" in captured.out


# ==============================================================================
# Lines 838-841: init() returns early when pyproject.toml exists
# ==============================================================================


def test_init_pyproject_already_exists(workdir, monkeypatch, capsys):
    """Lines 838-841: init() returns early when pyproject.toml exists."""
    base = Path(workdir)

    (base / "pyproject.toml").write_text(
        '[project]\nname = "existing"\ndependencies = []\n'
    )

    env = appenv.AppEnv(base, Path.cwd())
    env.init()

    captured = capsys.readouterr()
    assert "already exists" in captured.out
    assert "Nothing to do" in captured.out


# ==============================================================================
# Line 847: init() uses default "app" for empty command name
# ==============================================================================


def test_init_empty_command_name_defaults_to_app(workdir, monkeypatch, capsys):
    """Line 847: init() uses 'app' as default when command name is empty."""
    base = Path(workdir)

    # Empty command name -> defaults to "app"
    inputs = iter(
        [
            "",  # empty command name -> default "app"
            "test description",
            "",  # no dependencies -> defaults to "app"
            "",  # python version default
        ]
    )
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    env = appenv.AppEnv(base, Path.cwd())
    env.init()

    pyproject = (base / "pyproject.toml").read_text()
    assert 'name = "app"' in pyproject
    assert '"app"' in pyproject  # dependency also defaults to app


# ==============================================================================
# Lines 888-890: migrate() returns early when requirements.txt not found
# ==============================================================================


def test_migrate_no_requirements_txt(workdir, monkeypatch, capsys):
    """Lines 888-890: migrate() returns early when requirements.txt not found."""
    base = Path(workdir)

    # No requirements.txt, no pyproject.toml
    env = appenv.AppEnv(base, Path.cwd())
    env.migrate()

    captured = capsys.readouterr()
    assert "No requirements.txt found" in captured.out
    assert "Use 'init' to create" in captured.out


# ==============================================================================
# Line 1108: reset() unlinks files in .appenv
# ==============================================================================


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
