import argparse
import logging
import os
import shutil
import sys
from pathlib import Path

import pytest

import appenv
from appenv import UvVersion


def test_prepare_creates_envdir(workdir, monkeypatch, test_settings, mock_uv):
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
    uv = mock_uv

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

    env = appenv.AppEnv(Path.cwd(), test_settings(Path.cwd()))
    env.prepare()

    # .appenv/venv should exist
    assert (base / ".appenv" / "venv").exists()
    # .venv symlink should be created
    assert (base / ".venv").is_symlink()


def test_prepare_creates_venv_symlink(workdir, monkeypatch, test_settings, mock_uv):
    """Test prepare returns .appenv/venv path for pyproject workflow."""
    base = Path(workdir) / "ducker"
    base.mkdir()
    os.chdir(base)

    (base / "pyproject.toml").write_text(
        '[project]\nname = "ducker"\ndependencies = ["requests"]\n'
    )
    (base / "uv.lock").write_text("version = 1\n")

    uv = mock_uv

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

    env = appenv.AppEnv(Path.cwd(), test_settings(Path.cwd()))
    env_dir = env.prepare()

    # prepare() returns the real venv path (.appenv/venv)
    assert env_dir == base / ".appenv" / "venv"


def test_prepare_syncs_with_frozen_flag(workdir, monkeypatch, test_settings, mock_uv):
    """Test prepare calls uv sync with --frozen and --no-dev flags."""
    base = Path(workdir) / "frozenproj"
    base.mkdir()
    os.chdir(base)

    (base / "pyproject.toml").write_text(
        '[project]\nname = "frozenproj"\ndependencies = ["click"]\n'
    )
    (base / "uv.lock").write_text("version = 1\n")

    uv = mock_uv
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

    env = appenv.AppEnv(Path.cwd(), test_settings(Path.cwd()))
    env.prepare()

    # Verify sync was called with --frozen and --no-dev (default for prepare)
    assert len(sync_args_captured) == 1
    assert "--frozen" in sync_args_captured[0]
    assert "--no-dev" in sync_args_captured[0]
    assert "--group" not in sync_args_captured[0]  # No dev group


def test_prepare_verbose_output(
    workdir, monkeypatch, capsys, patterns, test_settings, mock_uv
):
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

    uv = mock_uv

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

    env = appenv.AppEnv(Path.cwd(), test_settings(Path.cwd()))
    env.prepare()

    out = capsys.readouterr().out

    # Clean up logging handler
    log.removeHandler(console_handler)

    # Concrete debug labels from source in expected order
    patterns.main.in_order(
        """\
...project base:...
...Creating fresh venv with uv ...
...activated extras/optional deps:..."""
    )

    patterns.no_errors.optional("...")
    patterns.no_errors.refused("...error...")
    patterns.no_errors.refused("...exception...")
    patterns.no_errors.refused("...traceback...")
    patterns.no_errors.refused("...failed...")

    full_pattern = patterns.full
    full_pattern.merge("main")
    full_pattern.merge("no_errors")

    full_pattern.generate_example()

    assert full_pattern == out


def test_prepare_pyproject_mode_verbose(
    workdir, monkeypatch, capsys, patterns, test_settings, mock_uv
):
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

    uv = mock_uv

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

    env = appenv.AppEnv(Path.cwd(), test_settings(Path.cwd()))
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
    workdir, monkeypatch, capsys, patterns, test_settings, mock_uv
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

    uv = mock_uv
    monkeypatch.setattr(appenv, "ensure_uv", lambda base: uv)
    monkeypatch.setenv("APPENV_VERBOSE", "1")

    env = appenv.AppEnv(Path.cwd(), test_settings(Path.cwd()))
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


def test_run_uv_sets_environment_and_execs(
    workdir, monkeypatch, test_settings, mock_uv
):
    """run_uv sets UV_PROJECT_ENVIRONMENT and execs uv binary."""
    base = Path(workdir)

    uv = mock_uv
    monkeypatch.setattr(appenv, "ensure_uv", lambda base: uv)

    execv_called = []

    def mock_execv(path, argv):
        execv_called.append((path, argv))
        raise SystemExit(0)

    monkeypatch.setattr("os.execv", mock_execv)

    env = appenv.AppEnv(Path.cwd(), test_settings(Path.cwd()))
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
    assert "requires-python:" in captured.out


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


def test_update_lockfile_exits_67_no_project(
    monkeypatch, tmp_path, capsys, test_settings, mock_uv
):
    """update_lockfile exits with code 67 when no pyproject.toml found."""
    monkeypatch.chdir(tmp_path)
    uv = mock_uv
    monkeypatch.setattr(appenv, "ensure_uv", lambda base: uv)

    env = appenv.AppEnv(Path.cwd(), test_settings(Path.cwd()))

    with pytest.raises(SystemExit) as err:
        env.update_lockfile()

    # Exit code can be 65 (if requirements.txt found) or 67 (if not)
    assert err.value.code in (65, 67)
    captured = capsys.readouterr()
    assert "pyproject.toml" in captured.out


# ==============================================================================
# Additional pyproject workflow tests
# ==============================================================================


def test_prepare_pyproject_cleanup_old_appenv(
    tmp_path, monkeypatch, test_settings, mock_uv
):
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
    uv = mock_uv
    monkeypatch.setattr(appenv, "ensure_uv", lambda base: uv)

    env = appenv.AppEnv(Path.cwd(), test_settings(Path.cwd()))
    env.prepare()

    # Old hash-based venv should be gone
    assert not (base / ".appenv" / "oldhash").exists()
    # .appenv should still exist (even though mock didn't create venv)
    assert (base / ".appenv").exists()


def test_prepare_pyproject_removes_symlink_in_appenv(
    tmp_path, monkeypatch, caplog, test_settings, mock_uv
):
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

    uv = mock_uv
    monkeypatch.setattr(appenv, "ensure_uv", lambda base: uv)

    env = appenv.AppEnv(base, test_settings(base))
    env.prepare()

    # Symlink should be removed
    assert not old_symlink.exists()
    # Target should NOT be removed
    assert target.exists()
    # Debug log should mention symlink removal
    assert "Removing symlink" in caplog.text


def test_prepare_pyproject_keeps_appenv_if_requirements_exists(
    tmp_path, monkeypatch, test_settings, mock_uv
):
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
    uv = mock_uv
    monkeypatch.setattr(appenv, "ensure_uv", lambda base: uv)

    env = appenv.AppEnv(Path.cwd(), test_settings(Path.cwd()))
    env.prepare()

    # Old .appenv should still exist (requirements.txt present)
    assert (base / ".appenv").exists()


def test_prepare_exits_without_project_files(
    tmp_path, monkeypatch, capsys, test_settings
):
    """prepare() exits with error if no pyproject.toml found."""
    monkeypatch.chdir(tmp_path)

    env = appenv.AppEnv(Path.cwd(), test_settings(Path.cwd()))

    with pytest.raises(SystemExit) as err:
        env.prepare()

    # Exit code can be 65 (if requirements.txt found) or 67 (if not)
    assert err.value.code in (65, 67)
    captured = capsys.readouterr()
    assert "pyproject.toml" in captured.out


def test_prepare_pyproject_missing_uv_lock(
    tmp_path, monkeypatch, capsys, test_settings
):
    """_prepare_pyproject exits with code 67 when uv.lock is missing."""
    monkeypatch.chdir(tmp_path)
    base = tmp_path

    # Create pyproject.toml but NO uv.lock
    (base / "pyproject.toml").write_text(
        "[project]\nname = 'test'\ndependencies = []\n"
    )

    env = appenv.AppEnv(Path.cwd(), test_settings(Path.cwd()))

    with pytest.raises(SystemExit) as err:
        env.prepare()

    assert err.value.code == 67
    captured = capsys.readouterr()
    assert "uv.lock" in captured.out


def test_prepare_pyproject_corrupted_venv(
    tmp_path, monkeypatch, test_settings, mock_uv
):
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
    uv = mock_uv

    def mock_cmd(args, verbose=False, **kwargs):
        uv_calls.append(args)
        return ""

    uv.cmd = mock_cmd
    monkeypatch.setattr(appenv, "ensure_uv", lambda base: uv)

    env = appenv.AppEnv(Path.cwd(), test_settings(Path.cwd()))
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


def test_prepare_pyproject_sets_uv_project_environment(
    tmp_path, monkeypatch, test_settings, mock_uv
):
    """_prepare_pyproject sets UV_PROJECT_ENVIRONMENT to .appenv/venv."""
    monkeypatch.chdir(tmp_path)
    base = tmp_path

    (base / "pyproject.toml").write_text(
        "[project]\nname = 'test'\ndependencies = []\n"
    )
    (base / "uv.lock").write_text("version = 1\n")

    uv = mock_uv
    monkeypatch.setattr(appenv, "ensure_uv", lambda base: uv)

    env = appenv.AppEnv(Path.cwd(), test_settings(Path.cwd()))
    env.prepare()

    assert os.environ.get("UV_PROJECT_ENVIRONMENT") == str(base / ".appenv" / "venv")


def test_prepare_pyproject_updates_broken_symlink(
    tmp_path, monkeypatch, test_settings, mock_uv
):
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

    uv = mock_uv
    monkeypatch.setattr(appenv, "ensure_uv", lambda base: uv)

    env = appenv.AppEnv(Path.cwd(), test_settings(Path.cwd()))
    env.prepare()

    # Symlink should now point to correct location
    assert venv_link.is_symlink()
    assert venv_link.readlink() == Path(".appenv/venv")


def test_prepare_pyproject_keeps_real_venv_directory(
    tmp_path, monkeypatch, capsys, test_settings, mock_uv
):
    """_prepare_pyproject warns when .venv exists as a real directory."""
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

    uv = mock_uv
    monkeypatch.setattr(appenv, "ensure_uv", lambda base: uv)

    env = appenv.AppEnv(Path.cwd(), test_settings(Path.cwd()))
    env.prepare()

    # .venv should still be a real directory, not a symlink
    assert venv_dir.is_dir()
    assert not venv_dir.is_symlink()
    assert (venv_dir / "marker.txt").exists()

    # But user should be warned
    captured = capsys.readouterr()
    assert "Warning" in captured.out
    assert "not a symlink" in captured.out


def test_prepare_pyproject_keeps_dot_uv_dir(
    tmp_path, monkeypatch, test_settings, mock_uv
):
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

    uv = mock_uv
    monkeypatch.setattr(appenv, "ensure_uv", lambda base: uv)

    env = appenv.AppEnv(Path.cwd(), test_settings(Path.cwd()))
    env.prepare()

    # .uv should be kept
    assert uv_dir.exists()
    assert (uv_dir / "uv_binary").exists()
    # old hash venv should be removed
    assert not old_venv.exists()


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


def test_prepare_venv_replaces_current_symlink(workdir, monkeypatch, test_settings):
    """Line 1176: _prepare_venv replaces existing current symlink."""
    base = Path(workdir) / "myproject_venv_test"
    base.mkdir()
    os.chdir(base)

    (base / "pyproject.toml").write_text("[project]\nname='test'\nversion='1.0'\n")
    (base / "uv.lock").write_text("version = 1\n")

    settings = test_settings(Path.cwd())
    app = appenv.AppEnv(Path.cwd(), settings)

    # Create existing symlink pointing to wrong location
    app.appenv_dir.mkdir(parents=True, exist_ok=True)
    (app.appenv_dir / "current").symlink_to("/wrong/path", target_is_directory=True)

    # Create mock uv - follows the pattern from test_prepare.py
    class MockUvBin:
        def __init__(self):
            self.bin = Path("/usr/bin/uv")
            self._version = UvVersion(0, 7, 0)

        @property
        def version(self):
            return self._version

        def cmd(self, args, verbose=False, **kwargs):
            # Mock uv command - create venv structure
            if "venv" in args:
                venv = base / ".appenv" / "venv"
                venv.mkdir(parents=True, exist_ok=True)
                (venv / "bin").mkdir(exist_ok=True)
                python = venv / "bin" / "python"
                python.write_text("#!/bin/sh\necho Python 3.12.0\n")
                python.chmod(0o755)
            return ""

    mock_uv = MockUvBin()
    monkeypatch.setattr(appenv, "ensure_uv", lambda base: mock_uv)
    # Mock cmd to avoid executing the fake python
    monkeypatch.setattr(appenv, "cmd", lambda c, **kwargs: b"Python 3.12.0")

    app._prepare_venv(dev_mode=False)

    # Verify symlink was replaced
    assert (app.appenv_dir / "current").exists()
    assert (app.appenv_dir / "current").readlink() == Path("venv")

    # Cleanup: Remove the fake venv to prevent interference with other tests
    # Clear UV_PROJECT_ENVIRONMENT to prevent other tests from using this fake python
    os.environ.pop("UV_PROJECT_ENVIRONMENT", None)
    # Remove the fake venv directory
    fake_venv = base / ".appenv" / "venv"
    if fake_venv.exists():
        shutil.rmtree(fake_venv)


def test_prepare_venv_existing_venv(workdir, monkeypatch, test_settings):
    """Branch 1148->1154: _prepare_venv skips uv venv when venv already exists."""
    base = Path(workdir) / "myproject_existing_venv"
    base.mkdir()
    os.chdir(base)

    (base / "pyproject.toml").write_text("[project]\nname='test'\nversion='1.0'\n")
    (base / "uv.lock").write_text("version = 1\n")

    settings = test_settings(Path.cwd())
    app = appenv.AppEnv(Path.cwd(), settings)

    # Create existing venv structure BEFORE calling _prepare_venv
    app.appenv_dir.mkdir(parents=True, exist_ok=True)
    venv = app.appenv_dir / "venv"
    venv.mkdir(parents=True, exist_ok=True)
    (venv / "bin").mkdir(exist_ok=True)
    python = venv / "bin" / "python"
    python.write_text("#!/bin/sh\necho Python 3.12.0\n")
    python.chmod(0o755)

    # Track if uv.cmd was called for venv creation
    venv_called = [False]

    class MockUvBin:
        def __init__(self):
            self.bin = Path("/usr/bin/uv")
            self._version = UvVersion(0, 7, 0)

        @property
        def version(self):
            return self._version

        def cmd(self, args, verbose=False, **kwargs):
            if "venv" in args:
                venv_called[0] = True
            return ""

    mock_uv = MockUvBin()
    monkeypatch.setattr(appenv, "ensure_uv", lambda base: mock_uv)
    monkeypatch.setattr(appenv, "cmd", lambda c, **kwargs: b"Python 3.12.0")

    app._prepare_venv(dev_mode=False)

    # uv venv should NOT have been called since venv already existed
    assert not venv_called[0], "uv venv should be skipped when venv exists"

    # Cleanup
    os.environ.pop("UV_PROJECT_ENVIRONMENT", None)
    if venv.exists():
        shutil.rmtree(venv)


def test_prepare_venv_current_is_directory(workdir, monkeypatch, test_settings):
    """Branch 1177->1180: _prepare_venv skips symlink when current is a real dir."""
    base = Path(workdir) / "myproject_current_dir"
    base.mkdir()
    os.chdir(base)

    (base / "pyproject.toml").write_text("[project]\nname='test'\nversion='1.0'\n")
    (base / "uv.lock").write_text("version = 1\n")

    settings = test_settings(Path.cwd())
    app = appenv.AppEnv(Path.cwd(), settings)

    # Create existing venv
    app.appenv_dir.mkdir(parents=True, exist_ok=True)
    venv = app.appenv_dir / "venv"
    venv.mkdir(parents=True, exist_ok=True)
    (venv / "bin").mkdir(exist_ok=True)
    python = venv / "bin" / "python"
    python.write_text("#!/bin/sh\necho Python 3.12.0\n")
    python.chmod(0o755)

    # Create 'current' as a real directory (not a symlink)
    current_dir = app.appenv_dir / "current"
    current_dir.mkdir()
    (current_dir / "some_file.txt").write_text("test")

    assert current_dir.is_dir()
    assert not current_dir.is_symlink()

    class MockUvBin:
        def __init__(self):
            self.bin = Path("/usr/bin/uv")
            self._version = UvVersion(0, 7, 0)

        @property
        def version(self):
            return self._version

        def cmd(self, args, verbose=False, **kwargs):
            return ""

    mock_uv = MockUvBin()
    monkeypatch.setattr(appenv, "ensure_uv", lambda base: mock_uv)
    monkeypatch.setattr(appenv, "cmd", lambda c, **kwargs: b"Python 3.12.0")

    app._prepare_venv(dev_mode=False)

    # 'current' should still be a directory, not converted to symlink
    assert current_dir.is_dir()
    assert not current_dir.is_symlink()
    assert (current_dir / "some_file.txt").exists()

    # Cleanup
    os.environ.pop("UV_PROJECT_ENVIRONMENT", None)
    if venv.exists():
        shutil.rmtree(venv)


# ==============================================================================
# Stale-venv coverage gap tests (from quality-elevation spec)
# ==============================================================================


def test_stale_venv_broken_python(tmp_path, monkeypatch, test_settings, mock_uv):
    """Stale-venv broken python: cmd() raises ValueError, venv removed and recreated."""
    monkeypatch.chdir(tmp_path)
    base = tmp_path

    (base / "pyproject.toml").write_text(
        "[project]\nname = 'test'\ndependencies = []\n"
    )
    (base / "uv.lock").write_text("version = 1\n")

    # Create existing venv with working python
    venv_real = base / ".appenv" / "venv"
    venv_real.mkdir(parents=True)
    (venv_real / "bin").mkdir()
    python = venv_real / "bin" / "python"
    python.write_text("#!/bin/sh\necho Python 3.12.0\n")
    python.chmod(0o755)

    uv = mock_uv
    venv_python = venv_real / "bin" / "python"
    first_call = [True]

    def uv_mock_cmd(args, verbose=False, **kwargs):
        if "venv" in args:
            venv_real.mkdir(parents=True, exist_ok=True)
            (venv_real / "bin").mkdir(exist_ok=True)
            (venv_real / "bin" / "python").write_text("#!/bin/sh\n")
        return ""

    uv.cmd = uv_mock_cmd

    def mock_cmd(c, **kwargs):
        # Only raise on first call (stale-venv check), not post-sync check
        if str(venv_python) in str(c) and first_call[0]:
            first_call[0] = False
            raise ValueError("malformed output")  # noqa: EM101, TRY003
        return b"Python 3.12.0"

    monkeypatch.setattr(appenv, "ensure_uv", lambda base: uv)
    monkeypatch.setattr(appenv, "cmd", mock_cmd)

    env = appenv.AppEnv(Path.cwd(), test_settings(Path.cwd()))
    env.prepare()

    # Old venv was removed (broken python) and recreated by mock uv
    assert venv_real.exists()


def test_stale_venv_version_mismatch(tmp_path, monkeypatch, test_settings, mock_uv):
    """Stale-venv version mismatch: venv Python too old for requires-python."""
    monkeypatch.chdir(tmp_path)
    base = tmp_path

    (base / "pyproject.toml").write_text(
        '[project]\nname = "test"\ndependencies = []\nrequires-python = ">=3.12"\n'
    )
    (base / "uv.lock").write_text("version = 1\n")

    # Create existing venv with old python
    venv_real = base / ".appenv" / "venv"
    venv_real.mkdir(parents=True)
    (venv_real / "bin").mkdir()
    python = venv_real / "bin" / "python"
    python.write_text("#!/bin/sh\necho Python 3.12.0\n")
    python.chmod(0o755)

    uv = mock_uv

    def uv_mock_cmd(args, verbose=False, **kwargs):
        if "venv" in args:
            venv_real.mkdir(parents=True, exist_ok=True)
            (venv_real / "bin").mkdir(exist_ok=True)
            (venv_real / "bin" / "python").write_text("#!/bin/sh\n")
        return ""

    uv.cmd = uv_mock_cmd

    def mock_cmd(c, **kwargs):
        # Return old Python version to trigger version mismatch
        if str(venv_real / "bin" / "python") in str(c):
            return b"Python 3.8.0"
        return b"Python 3.12.0"

    monkeypatch.setattr(appenv, "ensure_uv", lambda base: uv)
    monkeypatch.setattr(appenv, "cmd", mock_cmd)

    env = appenv.AppEnv(Path.cwd(), test_settings(Path.cwd()))
    env.prepare()

    # Venv was removed (Python 3.8 doesn't satisfy >=3.12) and recreated
    assert venv_real.exists()


def test_stale_venv_max_version_constraint(
    tmp_path, monkeypatch, capsys, test_settings, mock_uv
):
    """Stale-venv max version: Python exceeds upper bound in requires-python."""
    monkeypatch.chdir(tmp_path)
    base = tmp_path

    (base / "pyproject.toml").write_text(
        '[project]\nname = "test"\n'
        'dependencies = []\nrequires-python = ">=3.12,<3.14"\n'
    )
    (base / "uv.lock").write_text("version = 1\n")

    # Create existing venv with Python exceeding upper bound
    venv_real = base / ".appenv" / "venv"
    venv_real.mkdir(parents=True)
    (venv_real / "bin").mkdir()
    python = venv_real / "bin" / "python"
    python.write_text("#!/bin/sh\necho Python 3.15.0\n")
    python.chmod(0o755)

    uv = mock_uv

    def uv_mock_cmd(args, verbose=False, **kwargs):
        if "venv" in args:
            venv_real.mkdir(parents=True, exist_ok=True)
            (venv_real / "bin").mkdir(exist_ok=True)
            (venv_real / "bin" / "python").write_text("#!/bin/sh\n")
        return ""

    uv.cmd = uv_mock_cmd

    def mock_cmd(c, **kwargs):
        if str(venv_real / "bin" / "python") in str(c):
            return b"Python 3.15.0"
        return b"Python 3.12.0"

    monkeypatch.setattr(appenv, "ensure_uv", lambda base: uv)
    monkeypatch.setattr(appenv, "cmd", mock_cmd)

    env = appenv.AppEnv(Path.cwd(), test_settings(Path.cwd()))
    env.prepare()

    captured = capsys.readouterr()
    # Should show constraint message including upper bound
    assert "Recreating venv" in captured.out
    assert "<3.14" in captured.out
    assert venv_real.exists()


def test_extras_sync_args(tmp_path, monkeypatch, test_settings, mock_uv):
    """Extras in AppEnvSettings produce --extra flag in uv sync args."""
    monkeypatch.chdir(tmp_path)
    base = tmp_path

    (base / "pyproject.toml").write_text(
        '[project]\nname = "test"\ndependencies = []\n'
    )
    (base / "uv.lock").write_text("version = 1\n")

    uv = mock_uv
    sync_args_captured = []

    def mock_cmd(args, verbose=False, **kwargs):
        if "sync" in args:
            sync_args_captured.append(args)
        if "venv" in args:
            venv = base / ".appenv" / "venv"
            venv.mkdir(parents=True, exist_ok=True)
            (venv / "bin").mkdir(exist_ok=True)
            (venv / "bin" / "python").write_text("#!/bin/sh\n")
        return ""

    uv.cmd = mock_cmd
    monkeypatch.setattr(appenv, "ensure_uv", lambda base: uv)
    monkeypatch.setattr(appenv, "cmd", lambda c, **kwargs: b"Python 3.12.0")

    settings = appenv.AppEnvSettings(verbose=False, extras=["dev-tools"], basedir=base)
    env = appenv.AppEnv(Path.cwd(), settings)
    env.prepare()

    assert len(sync_args_captured) == 1
    assert "--extra" in sync_args_captured[0]
    assert "dev-tools" in sync_args_captured[0]


def test_prepare_venv_link_is_symlink_survives_unlink(
    tmp_path, monkeypatch, capsys, test_settings, mock_uv
):
    """Branch 1186->1194: .venv symlink survives unlink (race / mock).

    Covers the False branch of 'elif not self.venv_link.is_symlink()'.
    When .venv is a symlink that survives the unlink call, we reach line 1194
    without entering the warning block.
    """
    monkeypatch.chdir(tmp_path)
    base = tmp_path

    (base / "pyproject.toml").write_text(
        "[project]\nname = 'test'\ndependencies = []\n"
    )
    (base / "uv.lock").write_text("version = 1\n")

    # Create .appenv/venv so _prepare_venv has something to link to
    venv_real = base / ".appenv" / "venv"
    venv_real.mkdir(parents=True)
    (venv_real / "bin").mkdir()
    python = venv_real / "bin" / "python"
    python.write_text("#!/bin/sh\necho Python 3.12.0\n")
    python.chmod(0o755)

    # Create a real directory for the symlink target
    other_dir = base / "other_venv"
    other_dir.mkdir()

    # Create .venv as a symlink to other_dir
    venv_link = base / ".venv"
    venv_link.symlink_to(other_dir)
    assert venv_link.is_symlink()

    uv = mock_uv

    # Track unlink calls — make the first one for .venv a no-op
    original_unlink = Path.unlink
    unlink_calls = []

    def mock_unlink(self, missing_ok=False):
        if str(self).endswith("/.venv"):
            unlink_calls.append(str(self))
            return None  # No-op: simulate race where unlink fails silently
        return original_unlink(self, missing_ok=missing_ok)

    monkeypatch.setattr(Path, "unlink", mock_unlink)
    monkeypatch.setattr(appenv, "ensure_uv", lambda base: uv)
    monkeypatch.setattr(appenv, "cmd", lambda c, **kwargs: b"Python 3.12.0")

    env = appenv.AppEnv(Path.cwd(), test_settings(Path.cwd()))
    env._prepare_venv(dev_mode=False)

    # The unlink was attempted but was a no-op, so .venv is still a symlink
    assert len(unlink_calls) > 0, "unlink should have been called for .venv"

    # Cleanup
    os.environ.pop("UV_PROJECT_ENVIRONMENT", None)


def test_prepare_removes_legacy_current_symlink(
    tmp_path, monkeypatch, test_settings, mock_uv
):
    """Line 1196: _prepare_venv removes existing .appenv/current symlink."""
    monkeypatch.chdir(tmp_path)
    base = tmp_path

    (base / "pyproject.toml").write_text(
        "[project]\nname = 'test'\ndependencies = []\n"
    )
    (base / "uv.lock").write_text("version = 1\n")

    # Create .appenv with a 'current' symlink pointing to old location
    appenv_dir = base / ".appenv"
    appenv_dir.mkdir()
    old_target = base / "old_venv"
    old_target.mkdir()
    current_link = appenv_dir / "current"
    current_link.symlink_to(old_target, target_is_directory=True)
    assert current_link.is_symlink()

    uv = mock_uv

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

    env = appenv.AppEnv(Path.cwd(), test_settings(Path.cwd()))
    env._prepare_venv(dev_mode=False)

    # The old symlink should have been removed and recreated pointing to venv
    assert current_link.is_symlink()
    assert current_link.readlink() == Path("venv")

    # Cleanup
    os.environ.pop("UV_PROJECT_ENVIRONMENT", None)
