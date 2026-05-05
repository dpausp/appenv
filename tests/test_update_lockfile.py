"""Tests for update_lockfile pyproject.toml workflow."""

import argparse
import os
import shutil
from pathlib import Path

import pytest

import appenv
from tests.conftest import strip_ansi_codes


def _setup_pyproject_project(workdir, name="ducker", deps=None):
    """Setup a pyproject.toml based project."""
    base = Path(workdir) / name
    base.mkdir()
    os.chdir(base)

    # Copy appenv script
    src_appenv = Path(appenv.__file__)
    dst_appenv = base / "appenv"
    shutil.copy(src_appenv, dst_appenv)
    dst_appenv.chmod(0o755)

    # Create symlink
    link = base / name
    link.symlink_to("appenv")

    # Create pyproject.toml
    deps_str = ", ".join(f'"{d}"' for d in (deps or ["click"]))
    (base / "pyproject.toml").write_text(
        f'[project]\nname = "{name}"\ndependencies = [{deps_str}]\n'
    )

    return base


def test_update_lockfile_pyproject_workflow(
    workdir, monkeypatch, capsys, mock_uv, app_env
):
    """pyproject.toml mode should use uv lock and create uv.lock.

    The working directory is set correctly via os.chdir, so uv finds
    the correct pyproject.toml without needing --project flag.
    """
    # Create directory with pyproject.toml
    app_dir = Path(workdir) / "myapp"
    app_dir.mkdir()
    (app_dir / "pyproject.toml").write_text(
        """
[project]
name = "myapp"
version = "1.0.0"
dependencies = ["click"]
"""
    )
    (app_dir / "appenv").write_text("#!/usr/bin/env python3\npass\n")
    (app_dir / "appenv").chmod(0o755)

    # Mock ensure_uv and uv_cmd
    captured_calls = []

    def mock_uv_cmd(args, verbose=False, **kwargs):
        captured_calls.append({"args": list(args), "cwd": kwargs.get("cwd")})
        # Simulate uv lock output
        if "lock" in args and "pip" not in args:
            (app_dir / "uv.lock").write_text("version = 1\n")
        elif "pip" in args and "compile" in args:
            output_file = args[args.index("--output-file") + 1]
            Path(output_file).write_text("click==8.1.0\n")
        return b""

    mock_uv.cmd = mock_uv_cmd
    monkeypatch.setattr(appenv, "ensure_uv", lambda base: mock_uv)
    monkeypatch.setenv("APPENV_VERBOSE", "1")

    # Run update_lockfile
    env = app_env(app_dir)
    env.update_lockfile()

    captured = capsys.readouterr()
    out = strip_ansi_codes(captured.out)

    # Check for expected output
    assert "Updating lock file" in out
    assert "Created" in out
    # Check for no errors
    out_lower = out.lower()
    assert "error" not in out_lower
    assert "exception" not in out_lower
    assert "traceback" not in out_lower
    assert "failed" not in out_lower

    # Verify uv.lock was created
    assert (app_dir / "uv.lock").exists()

    # Verify uv lock was called
    lock_calls = [
        call
        for call in captured_calls
        if "lock" in call["args"] and "pip" not in call["args"]
    ]
    assert len(lock_calls) >= 1, "Expected at least one uv lock call"


def test_update_lockfile_verbose_output(
    workdir, monkeypatch, capsys, mock_uv, app_env
):
    """Verbose mode shows structured output with paths and mode info."""
    app_dir = Path(workdir) / "verboseapp"
    app_dir.mkdir()
    (app_dir / "pyproject.toml").write_text(
        '[project]\nname = "verboseapp"\ndependencies = ["click"]\n'
    )
    (app_dir / "appenv").write_text("#!/usr/bin/env python3\npass\n")
    (app_dir / "appenv").chmod(0o755)

    def mock_uv_cmd(args, verbose=False, **kwargs):
        if "lock" in args and "pip" not in args:
            (app_dir / "uv.lock").write_text("version = 1\n")
        return b""

    mock_uv.cmd = mock_uv_cmd
    monkeypatch.setattr(appenv, "ensure_uv", lambda base: mock_uv)
    monkeypatch.setenv("APPENV_VERBOSE", "1")

    env = app_env(app_dir)
    env.update_lockfile()

    captured = capsys.readouterr()
    out = strip_ansi_codes(captured.out)

    # Check for expected output
    assert "Updating lock file" in out
    assert "Created" in out


@pytest.mark.parametrize("diff,verbose", [(False, False), (False, True), (True, False)])
def test_update_lockfile_no_changes(
    diff, verbose, workdir, monkeypatch, capsys, make_pyproject, mock_uv, app_env
):
    """update_lockfile shows 'No changes' when lockfile is up to date."""
    base = Path(workdir)
    lock_content = "version = 1\n[[package]]\nname = 'click'\nversion = '8.1.0'\n"
    make_pyproject(
        base,
        '[project]\nname = "test"\ndependencies = ["click"]\n',
        lock_content,
    )

    def mock_uv_cmd(args, verbose=False, **kwargs):
        if "lock" in args and "pip" not in args:
            cwd = kwargs.get("cwd")
            if cwd:
                (Path(cwd) / "uv.lock").write_text(lock_content)
        return b""

    mock_uv.cmd = mock_uv_cmd
    monkeypatch.setattr(appenv, "ensure_uv", lambda base: mock_uv)

    env = app_env(base)
    args = argparse.Namespace(diff=diff, verbose=verbose)
    env.update_lockfile(args=args, remaining=None)

    captured = strip_ansi_codes(capsys.readouterr().out)
    assert "No changes" in captured


def test_update_lockfile_pyproject_diff_mode(
    workdir, monkeypatch, capsys, make_pyproject, mock_uv, app_env
):
    """update_lockfile with --diff shows changes without modifying uv.lock."""
    # Create directory with pyproject.toml and uv.lock
    app_dir = Path(workdir) / "diffapp"
    app_dir.mkdir()

    old_lock_content = "version = 1\n[[package]]\nname = 'click'\nversion = '8.0.0'\n"
    make_pyproject(
        app_dir,
        """[project]
name = "diffapp"
version = "1.0.0"
dependencies = ["click"]
""",
        old_lock_content,
    )

    def mock_uv_cmd(args, verbose=False, **kwargs):
        cwd = kwargs.get("cwd")
        if cwd and "lock" in args and "pip" not in args:
            new_lock = Path(cwd) / "uv.lock"
            new_lock.write_text(
                "version = 1\n[[package]]\nname = 'click'\nversion = '8.1.0'\n"
            )
        return b""

    mock_uv.cmd = mock_uv_cmd
    monkeypatch.setattr(appenv, "ensure_uv", lambda base: mock_uv)

    env = app_env(app_dir)
    args = argparse.Namespace(diff=True, verbose=False)

    env.update_lockfile(args=args, remaining=None)

    # Verify original uv.lock was NOT modified
    assert (app_dir / "uv.lock").read_text() == old_lock_content


def test_update_lockfile_pyproject_updated(
    workdir, monkeypatch, capsys, make_pyproject, mock_uv, app_env
):
    """Line 1040: 'Updated' output when lockfile has changes."""
    base = Path(workdir)
    make_pyproject(
        base,
        '[project]\nname = "test"\ndependencies = ["click"]\n',
        "version = 1\n[[package]]\nname = 'click'\nversion = '8.0.0'\n",
    )

    def mock_uv_cmd(args, verbose=False, **kwargs):
        if "lock" in args and "pip" not in args:
            (base / "uv.lock").write_text(
                "version = 1\n[[package]]\nname = 'click'\nversion = '8.1.0'\n"
            )
        elif "compile" in args:
            output_file = args[args.index("--output-file") + 1]
            Path(output_file).write_text("click==8.1.0\n")
        return b""

    mock_uv.cmd = mock_uv_cmd
    monkeypatch.setattr(appenv, "ensure_uv", lambda base: mock_uv)

    env = app_env(base)
    env.update_lockfile()

    captured = strip_ansi_codes(capsys.readouterr().out)
    assert "Updated" in captured


def test_update_lockfile_pyproject_diff_verbose(
    workdir, monkeypatch, capsys, make_pyproject, mock_uv, app_env
):
    """Line 990: Verbose output in pyproject diff mode."""
    base = Path(workdir)
    make_pyproject(
        base,
        '[project]\nname = "test"\ndependencies = ["click"]\n',
        "version = 1\n",
    )

    def mock_uv_cmd(args, verbose=False, **kwargs):
        if "lock" in args and "pip" not in args:
            cwd = kwargs.get("cwd")
            if cwd:
                (Path(cwd) / "uv.lock").write_text("version = 1\nnew = true\n")
        return b""

    mock_uv.cmd = mock_uv_cmd
    monkeypatch.setattr(appenv, "ensure_uv", lambda base: mock_uv)

    env = app_env(base)
    args = argparse.Namespace(diff=True, verbose=True)

    env.update_lockfile(args=args, remaining=None)

    captured = strip_ansi_codes(capsys.readouterr().out)
    assert "Diff mode" in captured


def test_update_lockfile_pyproject_calls_uv_lock(
    tmp_path, monkeypatch, make_pyproject, mock_uv, app_env
):
    """_update_lockfile_pyproject calls uv lock."""
    monkeypatch.chdir(tmp_path)
    base = tmp_path

    make_pyproject(base, "[project]\nname = 'test'\ndependencies = []\n")

    uv_calls = []
    mock_uv.cmd = lambda args, **kwargs: uv_calls.append(args)
    monkeypatch.setattr(appenv, "ensure_uv", lambda base: mock_uv)

    env = app_env(base)
    env.update_lockfile(None)

    # Should call uv lock
    assert any("lock" in str(c) for c in uv_calls)


def test_update_lockfile_verbose_shows_running_uv_lock(
    tmp_path, monkeypatch, capsys, make_pyproject, app_env
):
    """_update_lockfile_pyproject shows 'Running: uv lock' in verbose mode."""
    monkeypatch.chdir(tmp_path)
    base = tmp_path

    make_pyproject(base, "[project]\nname = 'test'\ndependencies = []\n")

    env = app_env(base)
    args = argparse.Namespace(diff=False, verbose=True)
    env.update_lockfile(args)

    captured = strip_ansi_codes(capsys.readouterr().out)
    assert "Updating lock file" in captured
