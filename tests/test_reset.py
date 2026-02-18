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
    """reset() cleans up contents in .appenv."""
    env = appenv.AppEnv(Path(tmpdir) / "ducker", Path.cwd())
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
    """reset() removes .venv symlink and cleans .appenv contents."""
    base = Path(tmpdir) / "myproject"
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
