"""Tests for pyproject.toml workflow core functionality."""

import os
from pathlib import Path

import pytest

import appenv


def test_detect_project_type_pyproject(tmpdir, monkeypatch):
    """pyproject.toml is detected."""
    monkeypatch.chdir(tmpdir)
    (Path(tmpdir) / "pyproject.toml").write_text("[project]\nname = 'test'\n")

    result = appenv.detect_project_type(Path(tmpdir))
    assert result == "pyproject"


def test_detect_project_type_none(tmpdir, monkeypatch):
    """Returns None when no pyproject.toml exists."""
    monkeypatch.chdir(tmpdir)
    result = appenv.detect_project_type(Path(tmpdir))
    assert result is None


def test_prepare_pyproject_creates_venv(tmpdir, monkeypatch):
    """_prepare_pyproject creates .appenv/venv and runs uv sync."""
    monkeypatch.chdir(tmpdir)
    base = Path(tmpdir)

    # Create pyproject.toml and uv.lock
    (base / "pyproject.toml").write_text(
        "[project]\nname = 'test'\ndependencies = []\n"
    )
    (base / "uv.lock").write_text("version = 1\n")

    # Mock uv commands
    uv_calls = []
    monkeypatch.setattr(appenv, "ensure_uv", lambda base: None)
    monkeypatch.setattr(appenv, "ensure_uv_version", lambda: None)
    monkeypatch.setattr(
        appenv,
        "uv_cmd",
        lambda args, **kwargs: uv_calls.append(args),
    )

    env = appenv.AppEnv(base, Path.cwd())
    result = env._prepare_pyproject()

    # venv is now in .appenv/venv
    assert result == str(base / ".appenv" / "venv")
    # venv command should be called with path argument
    assert any("venv" in c for c in uv_calls), f"Expected venv call, got {uv_calls}"
    assert any("sync" in c for c in uv_calls), f"Expected sync call, got {uv_calls}"
    # Symlink should be created
    assert (base / ".venv").is_symlink()


def test_prepare_pyproject_cleanup_old_appenv(tmpdir, monkeypatch):
    """_prepare_pyproject removes old hash-based venvs but keeps .appenv."""
    monkeypatch.chdir(tmpdir)
    base = Path(tmpdir)

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
    monkeypatch.setattr(appenv, "ensure_uv", lambda base: None)
    monkeypatch.setattr(appenv, "ensure_uv_version", lambda: None)
    monkeypatch.setattr(appenv, "uv_cmd", lambda args, **kwargs: None)

    env = appenv.AppEnv(base, Path.cwd())
    env._prepare_pyproject()

    # Old hash-based venv should be gone
    assert not (base / ".appenv" / "oldhash").exists()
    # .appenv should still exist (even though mock didn't create venv)
    assert (base / ".appenv").exists()


def test_prepare_pyproject_keeps_appenv_if_requirements_exists(tmpdir, monkeypatch):
    """_prepare_pyproject keeps .appenv if requirements.txt still exists."""
    monkeypatch.chdir(tmpdir)
    base = Path(tmpdir)

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
    monkeypatch.setattr(appenv, "ensure_uv", lambda base: None)
    monkeypatch.setattr(appenv, "ensure_uv_version", lambda: None)
    monkeypatch.setattr(appenv, "uv_cmd", lambda args, **kwargs: None)

    env = appenv.AppEnv(base, Path.cwd())
    env._prepare_pyproject()

    # Old .appenv should still exist (requirements.txt present)
    assert (base / ".appenv").exists()


def test_update_lockfile_pyproject_calls_uv_lock(tmpdir, monkeypatch):
    """_update_lockfile_pyproject calls uv lock."""
    monkeypatch.chdir(tmpdir)
    base = Path(tmpdir)

    (base / "pyproject.toml").write_text(
        "[project]\nname = 'test'\ndependencies = []\n"
    )

    uv_calls = []
    monkeypatch.setattr(appenv, "ensure_uv", lambda base: None)
    monkeypatch.setattr(appenv, "ensure_uv_version", lambda: None)
    monkeypatch.setattr(
        appenv,
        "uv_cmd",
        lambda args, **kwargs: uv_calls.append(args),
    )

    env = appenv.AppEnv(base, Path.cwd())
    env._update_lockfile_pyproject(None)

    # Should call uv lock
    assert any("lock" in str(c) for c in uv_calls)


def test_prepare_exits_without_project_files(tmpdir, monkeypatch, capsys):
    """prepare() exits with error if no pyproject.toml found."""
    monkeypatch.chdir(tmpdir)
    base = Path(tmpdir)

    env = appenv.AppEnv(base, Path.cwd())

    with pytest.raises(SystemExit) as err:
        env.prepare()

    assert err.value.code == 67
    captured = capsys.readouterr()
    assert "pyproject.toml" in captured.out


def test_prepare_pyproject_missing_uv_lock(tmpdir, monkeypatch, capsys):
    """_prepare_pyproject exits with code 67 when uv.lock is missing."""
    monkeypatch.chdir(tmpdir)
    base = Path(tmpdir)

    # Create pyproject.toml but NO uv.lock
    (base / "pyproject.toml").write_text(
        "[project]\nname = 'test'\ndependencies = []\n"
    )

    env = appenv.AppEnv(base, Path.cwd())

    with pytest.raises(SystemExit) as err:
        env._prepare_pyproject()

    assert err.value.code == 67
    captured = capsys.readouterr()
    assert "uv.lock" in captured.out


def test_prepare_pyproject_corrupted_venv(tmpdir, monkeypatch):
    """_prepare_pyproject removes corrupted venv and recreates it."""
    monkeypatch.chdir(tmpdir)
    base = Path(tmpdir)

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
    monkeypatch.setattr(appenv, "ensure_uv", lambda base: None)
    monkeypatch.setattr(appenv, "ensure_uv_version", lambda: None)
    monkeypatch.setattr(
        appenv,
        "uv_cmd",
        lambda args, **kwargs: uv_calls.append(args),
    )

    env = appenv.AppEnv(base, Path.cwd())
    result = env._prepare_pyproject()

    # venv is now in .appenv/venv
    assert result == str(venv_real)
    # The broken marker should be gone (venv was recreated)
    assert not (venv_real / "broken_marker.txt").exists()
    # venv command should be called
    assert any("venv" in c for c in uv_calls), f"Expected venv call, got {uv_calls}"


def test_ensure_best_python_respects_upper_bound(tmpdir, monkeypatch, capsys):
    """ensure_best_python respects upper bound in requires-python."""
    monkeypatch.chdir(tmpdir)
    base = Path(tmpdir)

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


def test_prepare_pyproject_sets_uv_project_environment(tmpdir, monkeypatch):
    """_prepare_pyproject sets UV_PROJECT_ENVIRONMENT to .appenv/venv."""
    monkeypatch.chdir(tmpdir)
    base = Path(tmpdir)

    (base / "pyproject.toml").write_text(
        "[project]\nname = 'test'\ndependencies = []\n"
    )
    (base / "uv.lock").write_text("version = 1\n")

    monkeypatch.setattr(appenv, "ensure_uv", lambda base: None)
    monkeypatch.setattr(appenv, "ensure_uv_version", lambda: None)
    monkeypatch.setattr(appenv, "uv_cmd", lambda args, **kwargs: None)

    env = appenv.AppEnv(base, Path.cwd())
    env._prepare_pyproject()

    assert os.environ.get("UV_PROJECT_ENVIRONMENT") == str(base / ".appenv" / "venv")


def test_prepare_pyproject_creates_symlink(tmpdir, monkeypatch):
    """_prepare_pyproject creates .venv symlink to .appenv/venv."""
    monkeypatch.chdir(tmpdir)
    base = Path(tmpdir)

    (base / "pyproject.toml").write_text(
        "[project]\nname = 'test'\ndependencies = []\n"
    )
    (base / "uv.lock").write_text("version = 1\n")

    monkeypatch.setattr(appenv, "ensure_uv", lambda base: None)
    monkeypatch.setattr(appenv, "ensure_uv_version", lambda: None)
    monkeypatch.setattr(appenv, "uv_cmd", lambda args, **kwargs: None)

    env = appenv.AppEnv(base, Path.cwd())
    env._prepare_pyproject()

    venv_link = base / ".venv"
    assert venv_link.is_symlink()
    # Symlink should point to .appenv/venv (relative path)
    assert venv_link.resolve() == (base / ".appenv" / "venv").resolve()


def test_prepare_pyproject_updates_broken_symlink(tmpdir, monkeypatch):
    """_prepare_pyproject updates broken .venv symlink to point to .appenv/venv."""
    monkeypatch.chdir(tmpdir)
    base = Path(tmpdir)

    (base / "pyproject.toml").write_text(
        "[project]\nname = 'test'\ndependencies = []\n"
    )
    (base / "uv.lock").write_text("version = 1\n")

    # Create broken symlink (pointing to non-existent path)
    venv_link = base / ".venv"
    venv_link.symlink_to("/nonexistent/path")

    monkeypatch.setattr(appenv, "ensure_uv", lambda base: None)
    monkeypatch.setattr(appenv, "ensure_uv_version", lambda: None)
    monkeypatch.setattr(appenv, "uv_cmd", lambda args, **kwargs: None)

    env = appenv.AppEnv(base, Path.cwd())
    env._prepare_pyproject()

    # Symlink should now point to correct location
    assert venv_link.is_symlink()
    assert os.readlink(venv_link) == ".appenv/venv"


def test_prepare_pyproject_keeps_real_venv_directory(tmpdir, monkeypatch):
    """_prepare_pyproject does not touch .venv if it's a real directory."""
    monkeypatch.chdir(tmpdir)
    base = Path(tmpdir)

    (base / "pyproject.toml").write_text(
        "[project]\nname = 'test'\ndependencies = []\n"
    )
    (base / "uv.lock").write_text("version = 1\n")

    # Create real .venv directory (not a symlink)
    venv_dir = base / ".venv"
    venv_dir.mkdir()
    (venv_dir / "marker.txt").write_text("real directory")

    monkeypatch.setattr(appenv, "ensure_uv", lambda base: None)
    monkeypatch.setattr(appenv, "ensure_uv_version", lambda: None)
    monkeypatch.setattr(appenv, "uv_cmd", lambda args, **kwargs: None)

    env = appenv.AppEnv(base, Path.cwd())
    env._prepare_pyproject()

    # .venv should still be a real directory, not a symlink
    assert venv_dir.is_dir()
    assert not venv_dir.is_symlink()
    assert (venv_dir / "marker.txt").exists()


def test_reset_removes_symlink_and_venv(tmpdir, monkeypatch, capsys):
    """reset removes .venv symlink and .appenv/venv."""
    monkeypatch.chdir(tmpdir)
    base = Path(tmpdir)

    # Create .appenv/venv
    venv_real = base / ".appenv" / "venv"
    venv_real.mkdir(parents=True)
    (venv_real / "bin").mkdir()
    (venv_real / "bin" / "python").write_text("#!/bin/bash")

    # Create symlink
    venv_link = base / ".venv"
    venv_link.symlink_to(".appenv/venv")

    env = appenv.AppEnv(base, Path.cwd())
    env.reset()

    # Symlink should be removed
    assert not venv_link.exists()
    # venv should be removed
    assert not venv_real.exists()


def test_reset_keeps_uv_binary(tmpdir, monkeypatch, capsys):
    """reset keeps .appenv/.uv directory (uv binary cache)."""
    monkeypatch.chdir(tmpdir)
    base = Path(tmpdir)

    # Create .appenv/.uv
    uv_dir = base / ".appenv" / ".uv"
    uv_dir.mkdir(parents=True)
    (uv_dir / "bin").mkdir()
    (uv_dir / "bin" / "uv").write_text("#!/bin/bash")

    env = appenv.AppEnv(base, Path.cwd())
    env.reset()

    # .appenv/.uv should still exist
    assert uv_dir.exists()
    assert (uv_dir / "bin" / "uv").exists()


def test_prepare_pyproject_keeps_dot_uv_dir(tmpdir, monkeypatch):
    """_prepare_pyproject does not delete .appenv/.uv during cleanup."""
    monkeypatch.chdir(tmpdir)
    base = Path(tmpdir)

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

    monkeypatch.setattr(appenv, "ensure_uv", lambda base: None)
    monkeypatch.setattr(appenv, "ensure_uv_version", lambda: None)
    monkeypatch.setattr(appenv, "uv_cmd", lambda args, **kwargs: None)

    env = appenv.AppEnv(base, Path.cwd())
    env._prepare_pyproject()

    # .uv should be kept
    assert uv_dir.exists()
    assert (uv_dir / "uv_binary").exists()
    # old hash venv should be removed
    assert not old_venv.exists()
