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


def test_prepare_verbose_output(workdir, monkeypatch, capsys, patterns):
    """Verbose mode shows structured output with paths, mode, and sync info."""
    base = Path(workdir) / "verboseprep"
    base.mkdir()
    os.chdir(base)

    (base / "pyproject.toml").write_text(
        '[project]\nname = "verboseprep"\ndependencies = ["click"]\n'
    )
    (base / "uv.lock").write_text("version = 1\n")

    monkeypatch.setattr(appenv, "ensure_uv", lambda base: None)
    monkeypatch.setattr(appenv, "ensure_uv_version", lambda: None)

    def mock_uv_cmd(args, **kwargs):
        if "venv" in args:
            venv = base / ".appenv" / "venv"
            venv.mkdir(parents=True, exist_ok=True)
            (venv / "bin").mkdir(exist_ok=True)
            (venv / "bin" / "python").write_text("#!/bin/sh\n")
        return b""

    monkeypatch.setattr(appenv, "uv_cmd", mock_uv_cmd)
    monkeypatch.setattr(appenv, "cmd", lambda c, **kwargs: b"Python 3.12.0")
    monkeypatch.setenv("APPENV_VERBOSE", "1")

    env = appenv.AppEnv(base, Path.cwd())
    env.prepare()

    out = capsys.readouterr().out

    # Use patterns for structured verbose output
    patterns.any.optional("...")
    patterns.main.merge("any")
    patterns.main.in_order(
        """\
Mode: pyproject
Workflow: pyproject.toml (uv native)
Project base: ...
pyproject.toml: .../pyproject.toml
uv.lock: .../uv.lock
venv: .../.appenv/venv
uv binary: ...
Python: ...
Creating venv with uv ...
Syncing dependencies (uv sync) ...
Venv Python: .../.appenv/venv/bin/python
Venv Python (realpath): ...
Venv Python version: Python 3.12.0"""
    )
    assert patterns.main == out


def test_prepare_verbose_with_venv_python_info(workdir, monkeypatch, capsys, patterns):
    """Verbose mode shows venv python path and version after sync."""
    base = Path(workdir) / "venvinfo"
    base.mkdir()
    os.chdir(base)

    (base / "pyproject.toml").write_text(
        '[project]\nname = "venvinfo"\ndependencies = ["click"]\n'
    )
    (base / "uv.lock").write_text("version = 1\n")

    monkeypatch.setattr(appenv, "ensure_uv", lambda base: None)
    monkeypatch.setattr(appenv, "ensure_uv_version", lambda: None)

    def mock_uv_cmd(args, **kwargs):
        if "venv" in args:
            venv = base / ".appenv" / "venv"
            venv.mkdir(parents=True, exist_ok=True)
            (venv / "bin").mkdir(exist_ok=True)
            (venv / "bin" / "python").write_text("#!/bin/sh\n")
        return b""

    monkeypatch.setattr(appenv, "uv_cmd", mock_uv_cmd)
    monkeypatch.setattr(appenv, "cmd", lambda c, **kwargs: b"Python 3.12.0")
    monkeypatch.setenv("APPENV_VERBOSE", "1")

    env = appenv.AppEnv(base, Path.cwd())
    env.prepare()

    out = capsys.readouterr().out

    # Check for venv python info in output
    patterns.any.optional("...")
    patterns.main.merge("any")
    patterns.main.in_order(
        """\
...
Venv Python: .../.appenv/venv/bin/python
Venv Python (realpath): ...
Venv Python version: Python 3.12.0"""
    )
    assert patterns.main == out
