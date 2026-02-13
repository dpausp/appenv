import argparse
import logging
import os
import sys
from pathlib import Path

import pytest

import appenv
from appenv import UvVersion


def get_test_settings(basedir=None):
    """Get settings for tests.

    Uses basedir if provided. Falls basedir=None, determines it from the
    current working directory (for tests that chdir'd to their test dir).
    """
    if basedir is None:
        # Try to use tmp_path if it's in scope (for tests using tmp_path directly)
        try:
            import inspect

            frame = inspect.currentframe()
            while frame is not None:
                if "tmp_path" in frame.f_locals:
                    basedir = frame.f_locals["tmp_path"]
                    break
                frame = frame.f_back
        except Exception:
            pass
    if basedir is None:
        basedir = appenv.appenv_settings_from_env().basedir
    return appenv.AppEnvSettings(
        verbose=False,
        extras=[],
        profile=False,
        basedir=basedir,
    )


def make_mock_uv():
    """Create a mock UvBin instance for testing."""

    class MockUvBin:
        def __init__(self):
            self.base = Path("/tmp")
            self.bin = Path("/usr/bin/uv")
            self._version = UvVersion(0, 5, 0)

        @property
        def version(self):
            return self._version

        def cmd(self, args, verbose=False, **kwargs):
            # Mock uv command - do nothing, return empty string
            return ""

    return MockUvBin()


def test_prepare_creates_envdir(workdir, monkeypatch):
    """Test prepare creates venv for pyproject workflow."""
    base = Path(workdir) / "ducker"
    base.mkdir()
    os.chdir(base)

    # Create pyproject.toml and uv.lock
    (base / "pyproject.toml").write_text(
        '[project]\nname = "ducker"\ndependencies = ["requests"]\n'
    )
    (base / "uv.lock").write_text("version = 1\n")

    # Create a mock UvBin
    uv = make_mock_uv()

    def mock_cmd(args, verbose=False, **kwargs):
        if "venv" in args:
            # venv is now created in .appenv/venv
            venv = base / ".appenv" / "venv"
            venv.mkdir(parents=True, exist_ok=True)
            (venv / "bin").mkdir(exist_ok=True)
            (venv / "bin" / "python").write_text("#!/bin/sh\n")
        return ""

    uv.cmd = mock_cmd
    monkeypatch.setattr(appenv, "ensure_uv", lambda base: uv)

    # Mock cmd to avoid executing the fake python
    monkeypatch.setattr(appenv, "cmd", lambda c, **kwargs: b"Python 3.12.0")

    env = appenv.AppEnv(Path.cwd(), get_test_settings(Path.cwd()))
    env.prepare()

    # .appenv/venv should exist
    assert (base / ".appenv" / "venv").exists()
    # .venv symlink should be created
    assert (base / ".venv").is_symlink()


def test_prepare_creates_venv_symlink(workdir, monkeypatch):
    """Test prepare returns .appenv/venv path for pyproject workflow."""
    base = Path(workdir) / "ducker"
    base.mkdir()
    os.chdir(base)

    (base / "pyproject.toml").write_text(
        '[project]\nname = "ducker"\ndependencies = ["requests"]\n'
    )
    (base / "uv.lock").write_text("version = 1\n")

    uv = make_mock_uv()

    def mock_cmd(args, verbose=False, **kwargs):
        if "venv" in args:
            # venv is now created in .appenv/venv
            venv = base / ".appenv" / "venv"
            venv.mkdir(parents=True, exist_ok=True)
            (venv / "bin").mkdir(exist_ok=True)
            (venv / "bin" / "python").write_text("#!/bin/sh\n")
        return ""

    uv.cmd = mock_cmd
    monkeypatch.setattr(appenv, "ensure_uv", lambda base: uv)
    monkeypatch.setattr(appenv, "cmd", lambda c, **kwargs: b"Python 3.12.0")

    env = appenv.AppEnv(Path.cwd(), get_test_settings(Path.cwd()))
    env_dir = env.prepare()

    # prepare() returns the real venv path (.appenv/venv)
    assert env_dir == base / ".appenv" / "venv"


def test_develop_syncs_with_dev_group(workdir, monkeypatch):
    """Test develop calls uv sync with --group dev and NO --frozen flag."""
    base = Path(workdir) / "devproj"
    base.mkdir()
    os.chdir(base)

    (base / "pyproject.toml").write_text(
        '[project]\nname = "devproj"\ndependencies = ["click"]\n'
        '[dependency-groups]\ndev = ["pytest", "ruff"]\n'
    )
    (base / "uv.lock").write_text("version = 1\n")

    uv = make_mock_uv()
    sync_args_captured = []

    def mock_cmd(args, verbose=False, **kwargs):
        if "venv" in args:
            venv = base / ".appenv" / "venv"
            venv.mkdir(parents=True, exist_ok=True)
            (venv / "bin").mkdir(exist_ok=True)
            (venv / "bin" / "python").write_text("#!/bin/sh\n")
        elif "sync" in args:
            sync_args_captured.append(args)
        return ""

    uv.cmd = mock_cmd
    monkeypatch.setattr(appenv, "ensure_uv", lambda base: uv)
    monkeypatch.setattr(appenv, "cmd", lambda c, **kwargs: b"Python 3.12.0")

    env = appenv.AppEnv(Path.cwd(), get_test_settings(Path.cwd()))
    env.develop()

    # Verify sync called WITHOUT --frozen or --no-dev (dev included by default)
    assert len(sync_args_captured) == 1
    assert sync_args_captured[0] == ["sync"]
    assert "--no-dev" not in sync_args_captured[0]
    assert "--frozen" not in sync_args_captured[0]


def test_prepare_syncs_with_frozen_flag(workdir, monkeypatch):
    """Test prepare calls uv sync with --frozen and --no-dev flags."""
    base = Path(workdir) / "frozenproj"
    base.mkdir()
    os.chdir(base)

    (base / "pyproject.toml").write_text(
        '[project]\nname = "frozenproj"\ndependencies = ["click"]\n'
    )
    (base / "uv.lock").write_text("version = 1\n")

    uv = make_mock_uv()
    sync_args_captured = []

    def mock_cmd(args, verbose=False, **kwargs):
        if "venv" in args:
            venv = base / ".appenv" / "venv"
            venv.mkdir(parents=True, exist_ok=True)
            (venv / "bin").mkdir(exist_ok=True)
            (venv / "bin" / "python").write_text("#!/bin/sh\n")
        elif "sync" in args:
            sync_args_captured.append(args)
        return ""

    uv.cmd = mock_cmd
    monkeypatch.setattr(appenv, "ensure_uv", lambda base: uv)
    monkeypatch.setattr(appenv, "cmd", lambda c, **kwargs: b"Python 3.12.0")

    env = appenv.AppEnv(Path.cwd(), get_test_settings(Path.cwd()))
    env.prepare()

    # Verify sync was called with --frozen and --no-dev (default for prepare)
    assert len(sync_args_captured) == 1
    assert "--frozen" in sync_args_captured[0]
    assert "--no-dev" in sync_args_captured[0]
    assert "--group" not in sync_args_captured[0]  # No dev group


def test_prepare_verbose_output(workdir, monkeypatch, capsys, patterns):
    """Verbose mode shows structured output with paths, mode, and sync info."""
    import logging

    # Setup logging to capture debug output
    log = logging.getLogger("appenv")
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG)
    console_formatter = logging.Formatter("%(message)s")
    console_handler.setFormatter(console_formatter)
    log.addHandler(console_handler)
    log.setLevel(logging.DEBUG)

    base = Path(workdir) / "verboseprep"
    base.mkdir()
    os.chdir(base)

    (base / "pyproject.toml").write_text(
        '[project]\nname = "verboseprep"\ndependencies = ["click"]\n'
    )
    (base / "uv.lock").write_text("version = 1\n")

    uv = make_mock_uv()

    def mock_cmd(args, verbose=False, **kwargs):
        if "venv" in args:
            venv = base / ".appenv" / "venv"
            venv.mkdir(parents=True, exist_ok=True)
            (venv / "bin").mkdir(exist_ok=True)
            (venv / "bin" / "python").write_text("#!/bin/sh\n")
        return ""

    uv.cmd = mock_cmd
    monkeypatch.setattr(appenv, "ensure_uv", lambda base: uv)
    monkeypatch.setattr(appenv, "cmd", lambda c, **kwargs: b"Python 3.12.0")
    monkeypatch.setenv("APPENV_VERBOSE", "1")

    env = appenv.AppEnv(Path.cwd(), get_test_settings(Path.cwd()))
    env.prepare()

    out = capsys.readouterr().out

    # Clean up logging handler
    log.removeHandler(console_handler)

    # Just verify verbose output contains key messages (any order, with extra logs OK)
    assert "project base:" in out
    assert "Creating fresh venv with uv ..." in out
    assert "activated extras/optional deps:" in out

    patterns.no_errors.optional("...")
    patterns.no_errors.refused("...error...")
    patterns.no_errors.refused("...exception...")
    patterns.no_errors.refused("...traceback...")
    patterns.no_errors.refused("...failed...")

    full_pattern = patterns.full
    full_pattern.merge("no_errors")

    full_pattern.generate_example()

    assert full_pattern == out


def test_prepare_pyproject_mode_verbose(workdir, monkeypatch, capsys, patterns):
    """Line 590: Verbose output shows mode."""
    # Setup logging to capture debug output
    log = logging.getLogger("appenv")
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG)
    console_formatter = logging.Formatter("%(message)s")
    console_handler.setFormatter(console_formatter)
    log.addHandler(console_handler)
    log.setLevel(logging.DEBUG)

    base = Path(workdir)
    (base / "pyproject.toml").write_text(
        '[project]\nname = "test"\ndependencies = []\n'
    )
    (base / "uv.lock").write_text("version = 1\n")

    uv = make_mock_uv()

    def mock_cmd(args, verbose=False, **kwargs):
        if "venv" in args:
            venv = base / ".appenv" / "venv"
            venv.mkdir(parents=True, exist_ok=True)
            (venv / "bin").mkdir(exist_ok=True)
            python = venv / "bin" / "python"
            python.write_text("#!/bin/sh\necho Python 3.12.0\n")
            python.chmod(0o755)
        return ""

    uv.cmd = mock_cmd
    monkeypatch.setattr(appenv, "ensure_uv", lambda base: uv)
    monkeypatch.setattr(appenv, "cmd", lambda c, **kwargs: b"Python 3.12.0")
    monkeypatch.setenv("APPENV_VERBOSE", "1")

    env = appenv.AppEnv(Path.cwd(), get_test_settings(Path.cwd()))
    env.prepare()

    captured = capsys.readouterr()

    # Clean up logging handler
    log.removeHandler(console_handler)

    # Just verify verbose output contains key messages (any order, with extra logs OK)
    assert "project base:" in captured.out
    assert "Creating fresh venv with uv ..." in captured.out
    assert "activated extras/optional deps:" in captured.out

    patterns.no_errors.optional("...")
    patterns.no_errors.refused("...error...")
    patterns.no_errors.refused("...exception...")
    patterns.no_errors.refused("...traceback...")
    patterns.no_errors.refused("...failed...")

    full_pattern = patterns.full
    full_pattern.merge("no_errors")

    full_pattern.generate_example()

    assert full_pattern == captured.out


def test_prepare_pyproject_unlink_file_in_appenv(
    workdir, monkeypatch, capsys, patterns
):
    """Line 758: _prepare_pyproject unlinks non-directory files in .appenv."""
    # Setup logging to capture debug output
    log = logging.getLogger("appenv")
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG)
    console_formatter = logging.Formatter("%(message)s")
    console_handler.setFormatter(console_formatter)
    log.addHandler(console_handler)
    log.setLevel(logging.DEBUG)

    base = Path(workdir)

    (base / "pyproject.toml").write_text(
        '[project]\nname = "test"\ndependencies = []\n'
    )
    (base / "uv.lock").write_text("version = 1\n")

    appenv_dir = base / ".appenv"
    appenv_dir.mkdir()
    old_file = appenv_dir / "old_file.txt"
    old_file.write_text("old content")

    uv = make_mock_uv()
    monkeypatch.setattr(appenv, "ensure_uv", lambda base: uv)
    monkeypatch.setenv("APPENV_VERBOSE", "1")

    env = appenv.AppEnv(Path.cwd(), get_test_settings(Path.cwd()))
    env.prepare()

    assert not old_file.exists()
    captured = capsys.readouterr()

    # Clean up logging handler
    log.removeHandler(console_handler)

    # Just verify verbose output contains key messages (including the old file removal)
    assert "project base:" in captured.out
    assert "Creating fresh venv with uv ..." in captured.out
    assert "removing old .appenv entry: old_file.txt ..." in captured.out

    patterns.no_errors.optional("...")
    patterns.no_errors.refused("...error...")
    patterns.no_errors.refused("...exception...")
    patterns.no_errors.refused("...traceback...")
    patterns.no_errors.refused("...failed...")

    full_pattern = patterns.full
    full_pattern.merge("no_errors")

    full_pattern.generate_example()

    assert full_pattern == captured.out


# ==============================================================================
# run_uv command tests (from test_coverage.py)
# ==============================================================================


def test_run_uv_sets_environment_and_execs(workdir, monkeypatch):
    """run_uv sets UV_PROJECT_ENVIRONMENT and execs uv binary."""
    base = Path(workdir)

    uv = make_mock_uv()
    monkeypatch.setattr(appenv, "ensure_uv", lambda base: uv)

    execv_called = []

    def mock_execv(path, argv):
        execv_called.append((path, argv))
        raise SystemExit(0)

    monkeypatch.setattr("os.execv", mock_execv)

    env = appenv.AppEnv(Path.cwd(), get_test_settings(Path.cwd()))
    args = argparse.Namespace()
    remaining = ["--version"]

    with pytest.raises(SystemExit):
        env.run_uv(args, remaining)

    assert len(execv_called) == 1
    assert execv_called[0][0] == "/usr/bin/uv"
    assert execv_called[0][1] == ["/usr/bin/uv", "--version"]
    assert os.environ.get("UV_PROJECT_ENVIRONMENT") == str(base / ".appenv" / "venv")


# ==============================================================================
# os.execv() and sys.exit() tests (unique from test_exec_and_exit.py)
# ==============================================================================


def test_ensure_best_python_execv_with_correct_args(monkeypatch, tmp_path):
    """ensure_best_python calls os.execv with correct args."""
    monkeypatch.delenv("APPENV_BEST_PYTHON", raising=False)
    monkeypatch.setattr("os.chdir", lambda p: None)

    base = tmp_path
    (base / "pyproject.toml").write_text('[project]\nrequires-python = ">=3.11"\n')

    # Mock available pythons
    monkeypatch.setattr(
        appenv,
        "find_available_pythons",
        lambda: [
            ("3.12", "/usr/bin/python3.12"),
            ("3.11", "/usr/bin/python3.11"),
        ],
    )
    monkeypatch.setattr("subprocess.check_call", lambda cmd, **kwargs: None)
    monkeypatch.setattr("sys.executable", "/old/python")

    execv_called = []

    def mock_execv(path, argv):
        execv_called.append((path, argv))
        raise SystemExit(0)

    monkeypatch.setattr("os.execv", mock_execv)

    with pytest.raises(SystemExit):
        appenv.ensure_best_python(base)

    assert len(execv_called) == 1
    # Should pick 3.12 (newest that satisfies >=3.11)
    assert "python3.12" in execv_called[0][0]


def test_ensure_best_python_exits_65_no_python_found(monkeypatch, tmp_path, capsys):
    """ensure_best_python exits with code 65 when no Python found."""
    monkeypatch.delenv("APPENV_BEST_PYTHON", raising=False)
    monkeypatch.setattr("os.chdir", lambda p: None)

    base = tmp_path
    (base / "pyproject.toml").write_text('[project]\nrequires-python = ">=3.99"\n')

    # No Python available
    monkeypatch.setattr(appenv, "find_available_pythons", list)

    with pytest.raises(SystemExit) as err:
        appenv.ensure_best_python(base)

    assert err.value.code == 65
    captured = capsys.readouterr()
    assert "Could not find Python" in captured.out


def test_ensure_best_python_exits_65_with_upper_bound(monkeypatch, tmp_path, capsys):
    """ensure_best_python shows upper bound in error message."""
    monkeypatch.delenv("APPENV_BEST_PYTHON", raising=False)
    monkeypatch.setattr("os.chdir", lambda p: None)

    base = tmp_path
    (base / "pyproject.toml").write_text('[project]\nrequires-python = ">=3.99,<4.0"\n')

    # Only have old Python
    monkeypatch.setattr(
        appenv,
        "find_available_pythons",
        lambda: [("3.11", "/usr/bin/python3.11")],
    )

    with pytest.raises(SystemExit) as err:
        appenv.ensure_best_python(base)

    assert err.value.code == 65
    captured = capsys.readouterr()
    # Should show upper bound in error message
    assert "3.99" in captured.out
    assert "<4.0" in captured.out


def test_update_lockfile_exits_67_no_project(monkeypatch, tmp_path, capsys):
    """update_lockfile exits with code 67 when no pyproject.toml found."""
    monkeypatch.chdir(tmp_path)
    uv = make_mock_uv()
    monkeypatch.setattr(appenv, "ensure_uv", lambda base: uv)

    env = appenv.AppEnv(Path.cwd(), get_test_settings(Path.cwd()))

    with pytest.raises(SystemExit) as err:
        env.update_lockfile()

    # Exit code can be 65 (if requirements.txt found) or 67 (if not)
    assert err.value.code in (65, 67)
    captured = capsys.readouterr()
    assert "pyproject.toml" in captured.out


# ==============================================================================
# Additional pyproject workflow tests
# ==============================================================================


def test_prepare_pyproject_cleanup_old_appenv(tmp_path, monkeypatch):
    """_prepare_pyproject removes old hash-based venvs but keeps .appenv."""
    monkeypatch.chdir(tmp_path)
    base = tmp_path

    # Create pyproject.toml and uv.lock (NO requirements.txt = migration)
    (base / "pyproject.toml").write_text(
        "[project]\nname = 'test'\ndependencies = []\n"
    )
    (base / "uv.lock").write_text("version = 1\n")

    # Create old .appenv directory with hash-based venv
    old_appenv = base / ".appenv" / "oldhash"
    old_appenv.mkdir(parents=True)
    (old_appenv / "marker.txt").write_text("old")

    # Mock uv commands
    uv = make_mock_uv()
    monkeypatch.setattr(appenv, "ensure_uv", lambda base: uv)

    env = appenv.AppEnv(Path.cwd(), get_test_settings(Path.cwd()))
    env.prepare()

    # Old hash-based venv should be gone
    assert not (base / ".appenv" / "oldhash").exists()
    # .appenv should still exist (even though mock didn't create venv)
    assert (base / ".appenv").exists()


def test_prepare_pyproject_removes_symlink_in_appenv(tmp_path, monkeypatch, caplog):
    """_prepare_appenv_dir removes symlinks in .appenv (e.g., nix-build out-links)."""
    caplog.set_level("DEBUG")

    base = tmp_path
    (base / "pyproject.toml").write_text(
        '[project]\nname = "test"\ndependencies = []\n'
    )
    (base / "uv.lock").write_text("version = 1\n")

    # Create target directory and symlink in .appenv (simulates nix-build -o)
    target = base / "nix-store-uv"
    target.mkdir()
    (target / "bin").mkdir()

    appenv_dir = base / ".appenv"
    appenv_dir.mkdir()
    old_symlink = appenv_dir / "uv"
    old_symlink.symlink_to(target)

    assert old_symlink.is_symlink()
    assert old_symlink.exists()

    uv = make_mock_uv()
    monkeypatch.setattr(appenv, "ensure_uv", lambda base: uv)

    env = appenv.AppEnv(base, get_test_settings(base))
    env.prepare()

    # Symlink should be removed
    assert not old_symlink.exists()
    # Target should NOT be removed
    assert target.exists()
    # Debug log should mention symlink removal
    assert "Removing symlink" in caplog.text


def test_prepare_pyproject_keeps_appenv_if_requirements_exists(tmp_path, monkeypatch):
    """_prepare_pyproject keeps .appenv if requirements.txt still exists."""
    monkeypatch.chdir(tmp_path)
    base = tmp_path

    # Create BOTH pyproject.toml and requirements.txt
    (base / "pyproject.toml").write_text(
        "[project]\nname = 'test'\ndependencies = []\n"
    )
    (base / "uv.lock").write_text("version = 1\n")
    (base / "requirements.txt").write_text("requests\n")

    # Create old .appenv directory
    old_appenv = base / ".appenv" / "oldhash"
    old_appenv.mkdir(parents=True)
    (old_appenv / "marker.txt").write_text("old")

    # Mock uv commands
    uv = make_mock_uv()
    monkeypatch.setattr(appenv, "ensure_uv", lambda base: uv)

    env = appenv.AppEnv(Path.cwd(), get_test_settings(Path.cwd()))
    env.prepare()

    # Old .appenv should still exist (requirements.txt present)
    assert (base / ".appenv").exists()


def test_prepare_exits_without_project_files(tmp_path, monkeypatch, capsys):
    """prepare() exits with error if no pyproject.toml found."""
    monkeypatch.chdir(tmp_path)

    env = appenv.AppEnv(Path.cwd(), get_test_settings(Path.cwd()))

    with pytest.raises(SystemExit) as err:
        env.prepare()

    # Exit code can be 65 (if requirements.txt found) or 67 (if not)
    assert err.value.code in (65, 67)
    captured = capsys.readouterr()
    assert "pyproject.toml" in captured.out


def test_prepare_pyproject_missing_uv_lock(tmp_path, monkeypatch, capsys):
    """_prepare_pyproject exits with code 67 when uv.lock is missing."""
    monkeypatch.chdir(tmp_path)
    base = tmp_path

    # Create pyproject.toml but NO uv.lock
    (base / "pyproject.toml").write_text(
        "[project]\nname = 'test'\ndependencies = []\n"
    )

    env = appenv.AppEnv(Path.cwd(), get_test_settings(Path.cwd()))

    with pytest.raises(SystemExit) as err:
        env.prepare()

    assert err.value.code == 67
    captured = capsys.readouterr()
    assert "uv.lock" in captured.out


def test_prepare_pyproject_corrupted_venv(tmp_path, monkeypatch):
    """_prepare_pyproject removes corrupted venv and recreates it."""
    monkeypatch.chdir(tmp_path)
    base = tmp_path

    # Create pyproject.toml and uv.lock
    (base / "pyproject.toml").write_text(
        "[project]\nname = 'test'\ndependencies = []\n"
    )
    (base / "uv.lock").write_text("version = 1\n")

    # Create broken .appenv/venv (directory without bin/python)
    venv_real = base / ".appenv" / "venv"
    venv_real.mkdir(parents=True)
    (venv_real / "broken_marker.txt").write_text("broken")

    # Mock uv commands
    uv_calls = []
    uv = make_mock_uv()

    def mock_cmd(args, verbose=False, **kwargs):
        uv_calls.append(args)
        return ""

    uv.cmd = mock_cmd
    monkeypatch.setattr(appenv, "ensure_uv", lambda base: uv)

    env = appenv.AppEnv(Path.cwd(), get_test_settings(Path.cwd()))
    result = env.prepare()

    # venv is now in .appenv/venv
    assert result == venv_real
    # The broken marker should be gone (venv was recreated)
    assert not (venv_real / "broken_marker.txt").exists()
    # venv command should be called
    assert any("venv" in c for c in uv_calls), f"Expected venv call, got {uv_calls}"


def test_ensure_best_python_respects_upper_bound(tmp_path, monkeypatch, capsys):
    """ensure_best_python respects upper bound in requires-python."""
    monkeypatch.chdir(tmp_path)
    base = tmp_path

    # Ensure APPENV_BEST_PYTHON is not set (causes early return if set)
    monkeypatch.delenv("APPENV_BEST_PYTHON", raising=False)

    # Create pyproject.toml with upper bound
    (base / "pyproject.toml").write_text(
        '[project]\nname = "test"\nrequires-python = ">=3.11,<3.14"\n'
    )

    # Mock find_available_pythons to return versions including ones exceeding bound
    monkeypatch.setattr(
        appenv,
        "find_available_pythons",
        lambda: [
            ("3.16", "/usr/bin/python3.16"),
            ("3.13", "/usr/bin/python3.13"),
            ("3.12", "/usr/bin/python3.12"),
            ("3.11", "/usr/bin/python3.11"),
        ],
    )

    # Mock os.execv and subprocess.check_call to prevent actual re-exec
    execv_called = []

    def mock_execv(path, argv):
        execv_called.append((path, argv))
        # In real code, execv never returns - simulate this by raising SystemExit
        raise SystemExit(0)

    monkeypatch.setattr("os.execv", mock_execv)
    monkeypatch.setattr(
        "subprocess.check_call", lambda cmd, **kwargs: None
    )  # Python works

    # Mock sys.executable to be different from available pythons
    monkeypatch.setattr("sys.executable", "/different/path/python")

    # Call the function - it should call execv and then SystemExit(0)
    with pytest.raises(SystemExit) as exc_info:
        appenv.ensure_best_python(base)

    # Should have exited via our mock (code 0), not the error path (code 65)
    assert exc_info.value.code == 0

    # Verify Python 3.13 was chosen (newest that satisfies >=3.11,<3.14)
    # 3.16 should be skipped (>= 3.14 upper bound)
    assert len(execv_called) == 1
    assert "python3.13" in execv_called[0][0]


def test_prepare_pyproject_sets_uv_project_environment(tmp_path, monkeypatch):
    """_prepare_pyproject sets UV_PROJECT_ENVIRONMENT to .appenv/venv."""
    monkeypatch.chdir(tmp_path)
    base = tmp_path

    (base / "pyproject.toml").write_text(
        "[project]\nname = 'test'\ndependencies = []\n"
    )
    (base / "uv.lock").write_text("version = 1\n")

    uv = make_mock_uv()
    monkeypatch.setattr(appenv, "ensure_uv", lambda base: uv)

    env = appenv.AppEnv(Path.cwd(), get_test_settings(Path.cwd()))
    env.prepare()

    assert os.environ.get("UV_PROJECT_ENVIRONMENT") == str(base / ".appenv" / "venv")


def test_prepare_pyproject_updates_broken_symlink(tmp_path, monkeypatch):
    """_prepare_pyproject updates broken .venv symlink to point to .appenv/venv."""
    monkeypatch.chdir(tmp_path)
    base = tmp_path

    (base / "pyproject.toml").write_text(
        "[project]\nname = 'test'\ndependencies = []\n"
    )
    (base / "uv.lock").write_text("version = 1\n")

    # Create broken symlink (pointing to non-existent path)
    venv_link = base / ".venv"
    venv_link.symlink_to("/nonexistent/path")

    uv = make_mock_uv()
    monkeypatch.setattr(appenv, "ensure_uv", lambda base: uv)

    env = appenv.AppEnv(Path.cwd(), get_test_settings(Path.cwd()))
    env.prepare()

    # Symlink should now point to correct location
    assert venv_link.is_symlink()
    assert os.readlink(venv_link) == ".appenv/venv"


def test_prepare_pyproject_keeps_real_venv_directory(tmp_path, monkeypatch):
    """_prepare_pyproject does not touch .venv if it's a real directory."""
    monkeypatch.chdir(tmp_path)
    base = tmp_path

    (base / "pyproject.toml").write_text(
        "[project]\nname = 'test'\ndependencies = []\n"
    )
    (base / "uv.lock").write_text("version = 1\n")

    # Create real .venv directory (not a symlink)
    venv_dir = base / ".venv"
    venv_dir.mkdir()
    (venv_dir / "marker.txt").write_text("real directory")

    uv = make_mock_uv()
    monkeypatch.setattr(appenv, "ensure_uv", lambda base: uv)

    env = appenv.AppEnv(Path.cwd(), get_test_settings(Path.cwd()))
    env.prepare()

    # .venv should still be a real directory, not a symlink
    assert venv_dir.is_dir()
    assert not venv_dir.is_symlink()
    assert (venv_dir / "marker.txt").exists()


def test_prepare_pyproject_keeps_dot_uv_dir(tmp_path, monkeypatch):
    """_prepare_pyproject does not delete .appenv/.uv during cleanup."""
    monkeypatch.chdir(tmp_path)
    base = tmp_path

    (base / "pyproject.toml").write_text(
        "[project]\nname = 'test'\ndependencies = []\n"
    )
    (base / "uv.lock").write_text("version = 1\n")

    # Create old hash-based venv AND .uv
    old_venv = base / ".appenv" / "oldhash"
    old_venv.mkdir(parents=True)
    (old_venv / "marker.txt").write_text("old")

    uv_dir = base / ".appenv" / ".uv"
    uv_dir.mkdir(parents=True)
    (uv_dir / "uv_binary").write_text("uv")

    uv = make_mock_uv()
    monkeypatch.setattr(appenv, "ensure_uv", lambda base: uv)

    env = appenv.AppEnv(Path.cwd(), get_test_settings(Path.cwd()))
    env.prepare()

    # .uv should be kept
    assert uv_dir.exists()
    assert (uv_dir / "uv_binary").exists()
    # old hash venv should be removed
    assert not old_venv.exists()


# ==============================================================================
# Reset and project detection tests
# ==============================================================================


def test_reset_keeps_uv_binary(tmp_path, monkeypatch, capsys):
    """Reset keeps .appenv/.uv directory (uv binary cache)."""
    monkeypatch.chdir(tmp_path)
    base = tmp_path

    # Create .appenv/.uv
    uv_dir = base / ".appenv" / ".uv"
    uv_dir.mkdir(parents=True)
    (uv_dir / "bin").mkdir()
    (uv_dir / "bin" / "uv").write_text("#!/bin/bash")

    env = appenv.AppEnv(Path.cwd(), get_test_settings(Path.cwd()))
    env.reset()

    # .appenv/.uv should still exist
    assert uv_dir.exists()
    assert (uv_dir / "bin" / "uv").exists()


def test_detect_project_type_pyproject(tmp_path, monkeypatch):
    """pyproject.toml is detected."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'test'\n")

    pyproject = appenv.Pyproject(tmp_path)
    result = pyproject.exists
    assert result is True


def test_detect_project_type_none(tmp_path, monkeypatch):
    """Returns None when no pyproject.toml exists."""
    monkeypatch.chdir(tmp_path)
    pyproject = appenv.Pyproject(tmp_path)
    result = pyproject.exists
    assert result is False
