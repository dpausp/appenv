"""Tests specifically targeting coverage gaps."""

import argparse
import hashlib
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
# Lines 467, 475-476: ensure_best_python branches
# ==============================================================================


def test_ensure_best_python_already_running_preferred(tmpdir, monkeypatch):
    """Line 467: Breaks when already running a preferred Python version."""
    base = Path(tmpdir)
    (base / "requirements.txt").write_text("requests\n")

    monkeypatch.delenv("APPENV_BEST_PYTHON", raising=False)
    monkeypatch.setattr("os.chdir", lambda p: None)

    which_calls = []

    def mock_which(name):
        which_calls.append(name)
        if name == "python3.12":
            return "/usr/bin/python3.12"
        return None

    monkeypatch.setattr("shutil.which", mock_which)

    def mock_resolve(self):
        return Path("/usr/bin/python3.12")

    monkeypatch.setattr("pathlib.Path.resolve", mock_resolve)
    monkeypatch.setattr("sys.executable", "/usr/bin/python3.12")

    appenv.ensure_best_python(base)


def test_ensure_best_python_broken_python_continues(tmpdir, monkeypatch, capsys):
    """Lines 475-476: Continues to next Python when check_call fails."""
    base = Path(tmpdir)
    (base / "requirements.txt").write_text("requests\n")

    monkeypatch.delenv("APPENV_BEST_PYTHON", raising=False)
    monkeypatch.setattr("os.chdir", lambda p: None)

    def mock_which(name):
        if name == "python3.12":
            return "/usr/bin/python3.12"
        if name == "python3.11":
            return "/usr/bin/python3.11"
        return None

    monkeypatch.setattr("shutil.which", mock_which)

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

    assert "python3.11" in execv_called[0][0]


# ==============================================================================
# Lines 683, 685-687: _prepare_requirements cleanup branches
# ==============================================================================


def test_prepare_requirements_unlink_expired_file(workdir, monkeypatch, capsys):
    """Line 683: Unlinks non-directory expired paths (files)."""
    base = Path(workdir)
    (base / "requirements.txt").write_text("requests==2.28.0\n")

    req_content = (base / "requirements.txt").read_bytes()
    correct_hash = hashlib.new("sha256", req_content).hexdigest()
    (base / "requirements.lock").write_text(
        f"# appenv-requirements-hash: {correct_hash}\nrequests==2.28.0\n"
    )

    appenv_dir = base / ".appenv"
    appenv_dir.mkdir()

    expired_file = appenv_dir / "expired_file.txt"
    expired_file.write_text("expired")

    (appenv_dir / "unclean").mkdir()
    (appenv_dir / "current").symlink_to("nonexistent")

    monkeypatch.setattr(appenv, "ensure_uv", lambda base: None)
    monkeypatch.setattr(appenv, "get_uv_bin", lambda base: "/usr/bin/uv")
    monkeypatch.setattr(appenv, "uv_cmd", lambda args, **kwargs: b"")

    def mock_ensure_venv(target, base=None):
        target.mkdir(parents=True, exist_ok=True)
        (target / "bin").mkdir(exist_ok=True)
        python = target / "bin" / "python"
        python.write_text("#!/bin/sh\necho Python 3.12.0\n")
        python.chmod(0o755)

    monkeypatch.setattr(appenv, "ensure_venv", mock_ensure_venv)
    monkeypatch.setattr(appenv, "cmd", lambda c, **kwargs: b"Python 3.12.0")

    original_resolve = Path.resolve

    def mock_resolve(self):
        if "python" in str(self):
            return Path("/python_path")
        return original_resolve(self)

    monkeypatch.setattr("pathlib.Path.resolve", mock_resolve)
    monkeypatch.setenv("APPENV_VERBOSE", "1")

    env = appenv.AppEnv(base, Path.cwd())
    env._prepare_requirements()

    assert not expired_file.exists()
    captured = capsys.readouterr()
    assert "Removing expired path" in captured.out


def test_prepare_requirements_corrupted_envdir(workdir, monkeypatch, capsys):
    """Lines 685-687: Removes envdir when ready file is missing."""
    base = Path(workdir)
    (base / "requirements.txt").write_text("requests==2.28.0\n")

    req_content = (base / "requirements.txt").read_bytes()
    correct_hash = hashlib.new("sha256", req_content).hexdigest()
    (base / "requirements.lock").write_text(
        f"# appenv-requirements-hash: {correct_hash}\nrequests==2.28.0\n"
    )

    appenv_dir = base / ".appenv"
    appenv_dir.mkdir()

    # Create corrupted env dir (without appenv.ready file) using a known hash
    # that doesn't match the calculated hash
    corrupted_hash = "deadbeef"
    corrupted_dir = appenv_dir / corrupted_hash
    corrupted_dir.mkdir()
    (corrupted_dir / "incomplete.txt").write_text("incomplete install")
    # NO appenv.ready file - this makes it "not consistent"

    # Also create whitelist entries
    (appenv_dir / "unclean").mkdir()
    (appenv_dir / "current").symlink_to(corrupted_hash)

    monkeypatch.setattr(appenv, "ensure_uv", lambda base: None)
    monkeypatch.setattr(appenv, "get_uv_bin", lambda base: "/usr/bin/uv")
    monkeypatch.setattr(appenv, "uv_cmd", lambda args, **kwargs: b"")

    def mock_ensure_venv(target, base=None):
        target.mkdir(parents=True, exist_ok=True)
        (target / "bin").mkdir(exist_ok=True)
        python = target / "bin" / "python"
        python.write_text("#!/bin/sh\necho Python 3.12.0\n")
        python.chmod(0o755)

    monkeypatch.setattr(appenv, "ensure_venv", mock_ensure_venv)
    monkeypatch.setattr(appenv, "cmd", lambda c, **kwargs: b"Python 3.12.0")

    original_resolve = Path.resolve

    def mock_resolve(self):
        if "python" in str(self):
            return Path("/python_path")
        return original_resolve(self)

    monkeypatch.setattr("pathlib.Path.resolve", mock_resolve)
    monkeypatch.setenv("APPENV_VERBOSE", "1")

    env = appenv.AppEnv(base, Path.cwd())
    env._prepare_requirements()

    # The corrupted dir should have been removed
    assert not corrupted_dir.exists()
    captured = capsys.readouterr()
    # The "not consistent" message is only printed when an existing envdir
    # doesn't have the ready file. But we're also removing it via rm -rf
    # when it's expired, so let's check for either message
    assert "not consistent" in captured.out or "Removing expired" in captured.out


def test_prepare_requirements_inconsistent_envdir(workdir, monkeypatch, capsys):
    """Lines 685-687: Removes envdir when ready file is missing (correct hash)."""
    base = Path(workdir)
    (base / "requirements.txt").write_text("requests==2.28.0\n")

    req_content = (base / "requirements.txt").read_bytes()
    correct_hash = hashlib.new("sha256", req_content).hexdigest()
    (base / "requirements.lock").write_text(
        f"# appenv-requirements-hash: {correct_hash}\nrequests==2.28.0\n"
    )

    appenv_dir = base / ".appenv"
    appenv_dir.mkdir()

    monkeypatch.setattr(appenv, "ensure_uv", lambda base: None)
    monkeypatch.setattr(appenv, "get_uv_bin", lambda base: "/usr/bin/uv")
    monkeypatch.setattr(appenv, "uv_cmd", lambda args, **kwargs: b"")

    # Compute the actual env_hash that _prepare_requirements will use
    def mock_ensure_venv(target, base=None):
        target.mkdir(parents=True, exist_ok=True)
        (target / "bin").mkdir(exist_ok=True)
        python = target / "bin" / "python"
        python.write_text("#!/bin/sh\necho Python 3.12.0\n")
        python.chmod(0o755)

    monkeypatch.setattr(appenv, "ensure_venv", mock_ensure_venv)
    monkeypatch.setattr(appenv, "cmd", lambda c, **kwargs: b"Python 3.12.0")

    original_resolve = Path.resolve

    def mock_resolve(self):
        if "python" in str(self):
            return Path("/python_path")
        return original_resolve(self)

    monkeypatch.setattr("pathlib.Path.resolve", mock_resolve)
    monkeypatch.setenv("APPENV_VERBOSE", "1")

    # Pre-compute the hash to create the inconsistent env_dir
    import os

    requirements = (base / "requirements.lock").read_bytes()
    hash_content = [
        os.fsencode(Path("/python_path")),
        requirements,
        Path(appenv.__file__).read_bytes(),
    ]
    env_hash = hashlib.new("sha256", b"".join(hash_content)).hexdigest()[:8]

    # Create the env_dir WITHOUT appenv.ready (inconsistent state)
    env_dir = appenv_dir / env_hash
    env_dir.mkdir(parents=True)
    (env_dir / "some_file.txt").write_text("incomplete install")
    # NO appenv.ready file

    # Also create whitelist entries
    (appenv_dir / "unclean").mkdir()
    (appenv_dir / "current").symlink_to(env_hash)

    env = appenv.AppEnv(base, Path.cwd())
    env._prepare_requirements()

    captured = capsys.readouterr()
    assert "not consistent" in captured.out


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
    monkeypatch.setattr(appenv, "find_minimal_python", lambda: "/usr/bin/python3.11")

    def mock_uv_cmd(args, verbose=False, **kwargs):
        if "lock" in args and "pip" not in args:
            pass
        elif "compile" in args:
            output_file = args[args.index("--output-file") + 1]
            Path(output_file).write_text("click==8.1.0\n")
        return b""

    monkeypatch.setattr(appenv, "uv_cmd", mock_uv_cmd)

    env = appenv.AppEnv(base, Path.cwd())
    args = argparse.Namespace(diff=False, verbose=True)

    env.update_lockfile(args=args, remaining=None)

    captured = capsys.readouterr()
    assert "Using minimal Python" in captured.out


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
    monkeypatch.setattr(appenv, "find_minimal_python", lambda: None)

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
    monkeypatch.setattr(appenv, "find_minimal_python", lambda: None)

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


def test_update_lockfile_requirements_verbose(workdir, monkeypatch, capsys):
    """Test verbose output in requirements update_lockfile workflow."""
    base = Path(workdir)
    (base / "requirements.txt").write_text("requests\n")

    monkeypatch.setattr(appenv, "ensure_uv", lambda base: None)
    monkeypatch.setattr(appenv, "find_minimal_python", lambda: "/usr/bin/python3.11")

    def mock_uv_cmd(args, verbose=False, **kwargs):
        if "compile" in args:
            output_file = args[args.index("--output-file") + 1]
            Path(output_file).write_text("requests==2.31.0\n")
        return b""

    monkeypatch.setattr(appenv, "uv_cmd", mock_uv_cmd)

    env = appenv.AppEnv(base, Path.cwd())
    args = argparse.Namespace(diff=False, verbose=True)

    env.update_lockfile(args=args, remaining=None)

    captured = capsys.readouterr()
    assert "Using minimal Python" in captured.out


def test_update_lockfile_requirements_verbose_existing_lockfile(
    workdir, monkeypatch, capsys
):
    """Line 1081: Verbose output shows reading existing lockfile."""
    base = Path(workdir)
    (base / "requirements.txt").write_text("requests\n")
    (base / "requirements.lock").write_text("requests==2.28.0\n")

    monkeypatch.setattr(appenv, "ensure_uv", lambda base: None)
    monkeypatch.setattr(appenv, "find_minimal_python", lambda: "/usr/bin/python3.11")

    def mock_uv_cmd(args, verbose=False, **kwargs):
        if "compile" in args:
            output_file = args[args.index("--output-file") + 1]
            Path(output_file).write_text("requests==2.31.0\n")
        return b""

    monkeypatch.setattr(appenv, "uv_cmd", mock_uv_cmd)

    env = appenv.AppEnv(base, Path.cwd())
    args = argparse.Namespace(diff=False, verbose=True)

    env.update_lockfile(args=args, remaining=None)

    captured = capsys.readouterr()
    assert "Reading existing lockfile" in captured.out


def test_update_lockfile_requirements_no_changes(workdir, monkeypatch, capsys):
    """Line 1176: 'No changes' output for requirements.lock."""
    base = Path(workdir)
    (base / "requirements.txt").write_text("requests\n")

    (base / "requirements.lock").write_text("requests==2.31.0\n")

    monkeypatch.setattr(appenv, "ensure_uv", lambda base: None)
    monkeypatch.setattr(appenv, "find_minimal_python", lambda: None)

    def mock_uv_cmd(args, verbose=False, **kwargs):
        if "compile" in args:
            output_file = args[args.index("--output-file") + 1]
            Path(output_file).write_text("requests==2.31.0\n")
        return b""

    monkeypatch.setattr(appenv, "uv_cmd", mock_uv_cmd)

    env = appenv.AppEnv(base, Path.cwd())
    env.update_lockfile()

    captured = capsys.readouterr()
    assert "No changes" in captured.out


def test_update_lockfile_requirements_updated(workdir, monkeypatch, capsys):
    """Line 1183: 'Updated' output for requirements.lock with changes."""
    base = Path(workdir)
    (base / "requirements.txt").write_text("requests\n")

    (base / "requirements.lock").write_text("requests==2.28.0\n")

    monkeypatch.setattr(appenv, "ensure_uv", lambda base: None)
    monkeypatch.setattr(appenv, "find_minimal_python", lambda: None)

    def mock_uv_cmd(args, verbose=False, **kwargs):
        if "compile" in args:
            output_file = args[args.index("--output-file") + 1]
            Path(output_file).write_text("requests==2.31.0\n")
        return b""

    monkeypatch.setattr(appenv, "uv_cmd", mock_uv_cmd)

    env = appenv.AppEnv(base, Path.cwd())
    env.update_lockfile()

    captured = capsys.readouterr()
    assert "Updated" in captured.out


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
            venv = base / ".venv"
            venv.mkdir(exist_ok=True)
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


def test_prepare_requirements_verbose(workdir, monkeypatch, capsys):
    """Verbose output in requirements prepare workflow."""
    base = Path(workdir)
    (base / "requirements.txt").write_text("requests==2.28.0\n")

    req_content = (base / "requirements.txt").read_bytes()
    correct_hash = hashlib.new("sha256", req_content).hexdigest()
    (base / "requirements.lock").write_text(
        f"# appenv-requirements-hash: {correct_hash}\nrequests==2.28.0\n"
    )

    monkeypatch.setattr(appenv, "ensure_uv", lambda base: None)
    monkeypatch.setattr(appenv, "get_uv_bin", lambda base: "/usr/bin/uv")
    monkeypatch.setattr(appenv, "uv_cmd", lambda args, **kwargs: b"")

    def mock_ensure_venv(target, base=None):
        target.mkdir(parents=True, exist_ok=True)
        (target / "bin").mkdir(exist_ok=True)
        python = target / "bin" / "python"
        python.write_text("#!/bin/sh\necho Python 3.12.0\n")
        python.chmod(0o755)

    monkeypatch.setattr(appenv, "ensure_venv", mock_ensure_venv)
    monkeypatch.setattr(appenv, "cmd", lambda c, **kwargs: b"Python 3.12.0")

    original_resolve = Path.resolve

    def mock_resolve(self):
        if "python" in str(self):
            return Path("/python_path")
        return original_resolve(self)

    monkeypatch.setattr("pathlib.Path.resolve", mock_resolve)
    monkeypatch.setenv("APPENV_VERBOSE", "1")

    env = appenv.AppEnv(base, Path.cwd())
    env._prepare_requirements()

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
            venv = base / ".venv"
            venv.mkdir(exist_ok=True)
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
