import os.path
from pathlib import Path

import appenv


def test_reset_nonexisting_envdir_silent(tmpdir):
    env = appenv.AppEnv(Path(tmpdir) / "ducker", Path.cwd())
    assert not os.path.exists(env.appenv_dir)
    env.reset()
    assert not os.path.exists(env.appenv_dir)
    assert os.path.exists(str(tmpdir))


def test_reset_removes_envdir_with_subdirs(tmpdir):
    env = appenv.AppEnv(Path(tmpdir) / "ducker", Path.cwd())
    os.makedirs(env.appenv_dir)
    assert os.path.exists(env.appenv_dir)
    env.reset()
    assert not os.path.exists(env.appenv_dir)
    assert os.path.exists(str(tmpdir))


def test_reset_removes_venv(tmpdir, capsys):
    """reset() also removes .venv for pyproject workflow."""
    base = Path(tmpdir) / "myproject"
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


def test_reset_removes_both_venv_and_appenv(tmpdir, capsys):
    """reset() removes both .venv and .appenv if both exist."""
    base = Path(tmpdir) / "myproject"
    base.mkdir()

    # Create .venv
    venv = base / ".venv"
    venv.mkdir()

    # Create .appenv
    appenv_dir = base / ".appenv"
    appenv_dir.mkdir()

    assert venv.exists()
    assert appenv_dir.exists()

    env = appenv.AppEnv(base, Path.cwd())
    env.reset()

    assert not venv.exists()
    assert not appenv_dir.exists()
