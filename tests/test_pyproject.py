"""Tests for pyproject.toml workflow."""

from pathlib import Path

import pytest

import appenv


def test_detect_project_type_pyproject(tmpdir, monkeypatch):
    """pyproject.toml is detected and has priority over requirements.txt."""
    monkeypatch.chdir(tmpdir)
    (Path(tmpdir) / "pyproject.toml").write_text("[project]\nname = 'test'\n")
    (Path(tmpdir) / "requirements.txt").write_text("requests\n")

    result = appenv.detect_project_type(Path(tmpdir))
    assert result == "pyproject"


def test_detect_project_type_requirements(tmpdir, monkeypatch):
    """requirements.txt is detected when no pyproject.toml."""
    monkeypatch.chdir(tmpdir)
    (Path(tmpdir) / "requirements.txt").write_text("requests\n")

    result = appenv.detect_project_type(Path(tmpdir))
    assert result == "requirements"


def test_detect_project_type_none(tmpdir, monkeypatch):
    """Returns None when neither file exists."""
    monkeypatch.chdir(tmpdir)
    result = appenv.detect_project_type(Path(tmpdir))
    assert result is None


def test_prepare_pyproject_creates_venv(tmpdir, monkeypatch):
    """_prepare_pyproject creates .venv and runs uv sync."""
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
    monkeypatch.setattr(
        appenv,
        "uv_cmd",
        lambda args, **kwargs: uv_calls.append(args),
    )

    env = appenv.AppEnv(base, Path.cwd())
    result = env._prepare_pyproject()

    assert result == str(base / ".venv")
    assert ("venv",) in [tuple(c) for c in uv_calls]
    assert ("sync",) in [tuple(c) for c in uv_calls]


def test_prepare_pyproject_cleanup_old_appenv(tmpdir, monkeypatch):
    """_prepare_pyproject removes old .appenv after successful sync."""
    monkeypatch.chdir(tmpdir)
    base = Path(tmpdir)

    # Create pyproject.toml and uv.lock (NO requirements.txt = migration)
    (base / "pyproject.toml").write_text(
        "[project]\nname = 'test'\ndependencies = []\n"
    )
    (base / "uv.lock").write_text("version = 1\n")

    # Create old .appenv directory
    old_appenv = base / ".appenv" / "oldhash"
    old_appenv.mkdir(parents=True)
    (old_appenv / "marker.txt").write_text("old")

    # Mock uv commands
    monkeypatch.setattr(appenv, "ensure_uv", lambda base: None)
    monkeypatch.setattr(appenv, "uv_cmd", lambda args, **kwargs: None)

    env = appenv.AppEnv(base, Path.cwd())
    env._prepare_pyproject()

    # Old .appenv should be gone
    assert not (base / ".appenv").exists()


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
    monkeypatch.setattr(appenv, "uv_cmd", lambda args, **kwargs: None)

    env = appenv.AppEnv(base, Path.cwd())
    env._prepare_pyproject()

    # Old .appenv should still exist (requirements.txt present)
    assert (base / ".appenv").exists()


def test_update_lockfile_pyproject_calls_uv_lock(tmpdir, monkeypatch):
    """_update_lockfile_pyproject calls uv lock and pip compile for fallback."""
    monkeypatch.chdir(tmpdir)
    base = Path(tmpdir)

    (base / "pyproject.toml").write_text(
        "[project]\nname = 'test'\ndependencies = []\n"
    )

    uv_calls = []
    monkeypatch.setattr(appenv, "ensure_uv", lambda base: None)
    monkeypatch.setattr(appenv, "find_minimal_python", lambda: None)
    monkeypatch.setattr(
        appenv,
        "uv_cmd",
        lambda args, **kwargs: uv_calls.append(args),
    )

    env = appenv.AppEnv(base, Path.cwd())
    env._update_lockfile_pyproject(None)

    # Should call uv lock
    assert any("lock" in str(c) for c in uv_calls)
    # Should also call pip compile for fallback requirements.lock
    assert any("compile" in str(c) for c in uv_calls)


def test_prepare_exits_without_project_files(tmpdir, monkeypatch, capsys):
    """prepare() exits with error if no project files found."""
    monkeypatch.chdir(tmpdir)
    base = Path(tmpdir)

    env = appenv.AppEnv(base, Path.cwd())

    with pytest.raises(SystemExit) as err:
        env.prepare()

    assert err.value.code == 67
    captured = capsys.readouterr()
    assert "pyproject.toml" in captured.out or "requirements.txt" in captured.out
