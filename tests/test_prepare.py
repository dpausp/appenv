import argparse
import os
from pathlib import Path

import pytest

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


# ==============================================================================
# Verbose output tests for prepare (from test_coverage.py)
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
            # venv is now created in .appenv/venv
            venv = base / ".appenv" / "venv"
            venv.mkdir(parents=True, exist_ok=True)
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
            # venv is now created in .appenv/venv
            venv = base / ".appenv" / "venv"
            venv.mkdir(parents=True, exist_ok=True)
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


def test_prepare_pyproject_unlink_file_in_appenv(workdir, monkeypatch, capsys):
    """Line 758: _prepare_pyproject unlinks non-directory files in .appenv."""
    base = Path(workdir)

    # Create pyproject.toml and uv.lock
    (base / "pyproject.toml").write_text(
        '[project]\nname = "test"\ndependencies = []\n'
    )
    (base / "uv.lock").write_text("version = 1\n")

    # Create .appenv with a file (not directory)
    appenv_dir = base / ".appenv"
    appenv_dir.mkdir()
    old_file = appenv_dir / "old_file.txt"
    old_file.write_text("old content")

    monkeypatch.setattr(appenv, "ensure_uv", lambda base: None)
    monkeypatch.setattr(appenv, "ensure_uv_version", lambda: None)
    monkeypatch.setattr(appenv, "uv_cmd", lambda args, **kwargs: None)

    monkeypatch.setenv("APPENV_VERBOSE", "1")

    env = appenv.AppEnv(base, Path.cwd())
    env._prepare_pyproject()

    assert not old_file.exists()
    captured = capsys.readouterr()
    assert "Removing old .appenv entry" in captured.out


# ==============================================================================
# run_uv command tests (from test_coverage.py)
# ==============================================================================


def test_run_uv_sets_environment_and_execs(workdir, monkeypatch):
    """run_uv sets UV_PROJECT_ENVIRONMENT and execs uv binary."""
    base = Path(workdir)

    monkeypatch.setattr(appenv, "ensure_uv", lambda base: None)
    monkeypatch.setattr(appenv, "get_uv_bin", lambda base: "/usr/bin/uv")

    execv_called = []

    def mock_execv(path, argv):
        execv_called.append((path, argv))
        raise SystemExit(0)

    monkeypatch.setattr("os.execv", mock_execv)

    env = appenv.AppEnv(base, Path.cwd())
    args = argparse.Namespace()
    remaining = ["--version"]

    with pytest.raises(SystemExit):
        env.run_uv(args, remaining)  # type: ignore[attr-defined]

    assert len(execv_called) == 1
    assert execv_called[0][0] == "/usr/bin/uv"
    assert execv_called[0][1] == ["/usr/bin/uv", "--version"]
    assert os.environ.get("UV_PROJECT_ENVIRONMENT") == str(base / ".appenv" / "venv")
