import hashlib
import os
from pathlib import Path

import appenv


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

    # Mock uv commands - uv_cmd should create venv structure
    monkeypatch.setattr(appenv, "ensure_uv", lambda base: None)
    monkeypatch.setattr(appenv, "ensure_uv_version", lambda: None)

    def mock_uv_cmd(args, **kwargs):
        if "venv" in args:
            # venv is now created in .appenv/venv
            venv = base / ".appenv" / "venv"
            venv.mkdir(parents=True, exist_ok=True)
            (venv / "bin").mkdir(exist_ok=True)
            (venv / "bin" / "python").write_text("#!/bin/sh\n")
        return b""

    monkeypatch.setattr(appenv, "uv_cmd", mock_uv_cmd)

    # Mock cmd to avoid executing the fake python
    monkeypatch.setattr(appenv, "cmd", lambda c, **kwargs: b"Python 3.12.0")

    env = appenv.AppEnv(base, Path.cwd())
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

    monkeypatch.setattr(appenv, "ensure_uv", lambda base: None)
    monkeypatch.setattr(appenv, "ensure_uv_version", lambda: None)

    def mock_uv_cmd(args, **kwargs):
        if "venv" in args:
            # venv is now created in .appenv/venv
            venv = base / ".appenv" / "venv"
            venv.mkdir(parents=True, exist_ok=True)
            (venv / "bin").mkdir(exist_ok=True)
            (venv / "bin" / "python").write_text("#!/bin/sh\n")
        return b""

    monkeypatch.setattr(appenv, "uv_cmd", mock_uv_cmd)
    monkeypatch.setattr(appenv, "cmd", lambda c, **kwargs: b"Python 3.12.0")

    env = appenv.AppEnv(base, Path.cwd())
    env_dir = env.prepare()

    # prepare() returns the real venv path (.appenv/venv)
    assert env_dir == str(base / ".appenv" / "venv")


# Tier 2 tests


def test_prepare_requirements_cleanup_expired(workdir, monkeypatch, tmpdir):
    """_prepare_requirements removes expired env dirs with different hashes."""
    base = Path(workdir) / "myapp"
    base.mkdir()
    os.chdir(base)

    # Create requirements.txt and requirements.lock
    (base / "requirements.txt").write_text("requests==2.28.0\n")

    # Calculate the hash that will be used
    req_content = (base / "requirements.txt").read_bytes()
    correct_hash = hashlib.new("sha256", req_content).hexdigest()

    (base / "requirements.lock").write_text(
        f"# appenv-requirements-hash: {correct_hash}\nrequests==2.28.0\n"
    )

    # Create old env dirs in .appenv with different hashes
    appenv_dir = base / ".appenv"
    appenv_dir.mkdir()

    old_env1 = appenv_dir / "oldhash1"
    old_env1.mkdir()
    (old_env1 / "marker.txt").write_text("old env 1")

    old_env2 = appenv_dir / "oldhash2"
    old_env2.mkdir()
    (old_env2 / "marker.txt").write_text("old env 2")

    # Create 'unclean' and 'current' which should be whitelisted
    (appenv_dir / "unclean").mkdir()
    (appenv_dir / "current").symlink_to("oldhash1")

    # Mock ensure_uv and uv_cmd
    monkeypatch.setattr(appenv, "ensure_uv", lambda base: None)

    def mock_uv_cmd(args, **kwargs):
        return b""

    monkeypatch.setattr(appenv, "uv_cmd", mock_uv_cmd)

    # Mock ensure_venv to create the expected structure
    def mock_ensure_venv(target, base=None):
        if not target.exists():
            target.mkdir(parents=True)
            (target / "bin").mkdir()
            (target / "bin" / "python").write_text("#!/bin/sh\n")

    monkeypatch.setattr(appenv, "ensure_venv", mock_ensure_venv)

    # Mock cmd to avoid permission errors when running the fake python
    def mock_cmd(c, **kwargs):
        if isinstance(c, list) and "python" in c[-1] if len(c) > 0 else False:
            return b"Python 3.12.0"
        return b""

    monkeypatch.setattr(appenv, "cmd", mock_cmd)

    # Monkeypatch Path.resolve for consistent python path
    original_resolve = Path.resolve

    def mock_resolve(self):
        if "python" in str(self):
            return Path("/python_path")
        return original_resolve(self)

    monkeypatch.setattr("pathlib.Path.resolve", mock_resolve)

    env = appenv.AppEnv(base, Path.cwd())

    # The prepare will create a new env dir based on the hash
    # and should clean up old directories
    env._prepare_requirements()

    # Old env dirs should be removed (except current symlink target and unclean)
    # Note: current still points to oldhash1, so oldhash1 is in whitelist
    assert not old_env2.exists()
    assert (appenv_dir / "unclean").exists()
