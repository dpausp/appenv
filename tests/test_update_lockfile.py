"""Tests for update_lockfile pyproject.toml workflow."""

import os
import shutil
from pathlib import Path

import appenv


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


def test_update_lockfile_pyproject_workflow(workdir, monkeypatch, capsys):
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
    monkeypatch.setattr(appenv, "ensure_uv", lambda base: None)
    monkeypatch.setattr(appenv, "ensure_uv_version", lambda: None)

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

    monkeypatch.setattr(appenv, "uv_cmd", mock_uv_cmd)

    # Enable verbose output to check mode detection
    monkeypatch.setenv("APPENV_VERBOSE", "1")

    # Run update_lockfile
    env = appenv.AppEnv(app_dir, Path.cwd())
    env.update_lockfile()

    # Verify it detected pyproject mode
    captured = capsys.readouterr()
    assert "Mode: pyproject.toml" in captured.out

    # Verify uv.lock was created
    assert (app_dir / "uv.lock").exists()

    # Verify uv lock was called
    lock_calls = [
        call
        for call in captured_calls
        if "lock" in call["args"] and "pip" not in call["args"]
    ]
    assert len(lock_calls) >= 1, "Expected at least one uv lock call"


# Tier 2 tests


def test_update_lockfile_pyproject_diff_mode(workdir, monkeypatch, capsys, tmp_path):
    """update_lockfile with --diff shows changes without modifying uv.lock."""
    import argparse

    # Create directory with pyproject.toml and uv.lock
    app_dir = Path(workdir) / "diffapp"
    app_dir.mkdir()

    (app_dir / "pyproject.toml").write_text(
        """[project]
name = "diffapp"
version = "1.0.0"
dependencies = ["click"]
"""
    )

    # Create existing uv.lock with old content
    old_lock_content = "version = 1\n[[package]]\nname = 'click'\nversion = '8.0.0'\n"
    (app_dir / "uv.lock").write_text(old_lock_content)

    # Mock ensure_uv and uv_cmd
    monkeypatch.setattr(appenv, "ensure_uv", lambda base: None)
    monkeypatch.setattr(appenv, "ensure_uv_version", lambda: None)

    def mock_uv_cmd(args, verbose=False, **kwargs):
        cwd = kwargs.get("cwd")
        if cwd and "lock" in args and "pip" not in args:
            # In diff mode, uv lock runs in temp dir
            # Create a "new" lock file with different content
            new_lock = Path(cwd) / "uv.lock"
            new_lock.write_text(
                "version = 1\n[[package]]\nname = 'click'\nversion = '8.1.0'\n"
            )
        return b""

    monkeypatch.setattr(appenv, "uv_cmd", mock_uv_cmd)

    env = appenv.AppEnv(app_dir, Path.cwd())
    args = argparse.Namespace(diff=True, verbose=False)

    env.update_lockfile(args=args, remaining=None)

    # Verify diff output was shown
    captured = capsys.readouterr()
    assert "Checking lockfile changes" in captured.out

    # Verify original uv.lock was NOT modified
    assert (app_dir / "uv.lock").read_text() == old_lock_content
