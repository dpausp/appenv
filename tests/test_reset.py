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


# ==============================================================================
# reset tests (from test_coverage.py)
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
