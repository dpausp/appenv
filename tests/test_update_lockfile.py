import os
import shutil
import sys
import unittest.mock
from pathlib import Path

import pytest

import appenv


def _setup_requirements_project(workdir, name="ducker", dep="ducker<2.0.2"):
    """Setup a requirements.txt based project without calling init()."""
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

    # Create requirements.txt
    (base / "requirements.txt").write_text(f"{dep}\n")

    return base


def test_init_and_create_lockfile(workdir, monkeypatch):
    base = _setup_requirements_project(workdir)

    lockfile = base / "requirements.lock"
    assert not lockfile.exists()

    env = appenv.AppEnv(base, Path.cwd())
    env.update_lockfile()

    assert lockfile.exists()
    lockfile_content = lockfile.read_text()
    assert "ducker" in lockfile_content
    assert "# appenv-requirements-hash:" in lockfile_content


def test_update_lockfile_uses_minimal_python(workdir, monkeypatch):
    """It uses the minimal python version from preferences for lockfile."""
    base = _setup_requirements_project(workdir, name="myapp", dep="httpie")

    monkeypatch.setattr(appenv, "ensure_uv", lambda base: None)

    # Add python preference to requirements.txt
    requirements_file = base / "requirements.txt"
    content = requirements_file.read_text()
    requirements_file.write_text(
        "# appenv-python-preference: 3.11,3.9,3.10\n" + content
    )

    # Mock uv_cmd to capture --python argument
    captured_args = []
    monkeypatch.setattr(
        appenv, "uv_cmd", lambda args, **kwargs: captured_args.append(args)
    )
    monkeypatch.setattr(appenv, "find_minimal_python", lambda: "/usr/bin/python3.9")

    env = appenv.AppEnv(base, Path.cwd())
    env.update_lockfile()

    # Verify --python flag was passed with minimal version
    assert any("--python" in str(arg) for arg in captured_args)
    assert any("python3.9" in str(arg) for arg in captured_args)


@pytest.mark.skipif(sys.version_info[0:2] < (3, 8), reason="Isolated CI builds")
def test_update_lockfile_missing_minimal_python(workdir, monkeypatch):
    """It raises an error if the minimal python is not available."""
    base = _setup_requirements_project(workdir, name="ppytest", dep="pytest==6.1.2")

    requirements_file = base / "requirements.txt"
    content = requirements_file.read_text()
    requirements_file.write_text("# appenv-python-preference: 3.8,3.6,3.9\n" + content)

    old_which = shutil.which

    def new_which(string):
        if string == "python3.6":
            return None
        else:
            return old_which(string)

    env = appenv.AppEnv(base, Path.cwd())

    with unittest.mock.patch("shutil.which") as which:
        which.side_effect = new_which
        with pytest.raises(SystemExit) as e:
            env.update_lockfile()
    assert e.value.code == 66


def test_update_lockfile_ignores_parent_pyproject(workdir, monkeypatch, capsys):
    """Legacy requirements.txt in subdirectory ignores parent pyproject.toml.

    This tests the bug case where uv might walk up the directory tree and find
    a pyproject.toml in a parent directory instead of using the requirements.txt
    in the appenv's own directory.
    """
    # Create parent directory with pyproject.toml
    parent_dir = Path(workdir) / "parent"
    parent_dir.mkdir()
    (parent_dir / "pyproject.toml").write_text(
        """
[project]
name = "parent-project"
version = "1.0.0"
dependencies = ["requests"]
"""
    )

    # Create subdirectory with requirements.txt (no pyproject.toml)
    subdir = parent_dir / "subapp"
    subdir.mkdir()
    (subdir / "requirements.txt").write_text("click\n")
    (subdir / "appenv").write_text("#!/usr/bin/env python3\npass\n")
    (subdir / "appenv").chmod(0o755)

    # Mock ensure_uv and uv_cmd to capture behavior
    monkeypatch.setattr(appenv, "ensure_uv", lambda base: None)

    captured_calls = []

    def mock_uv_cmd(args, verbose=False, **kwargs):
        captured_calls.append({"args": list(args), "cwd": kwargs.get("cwd")})
        # Simulate successful pip compile output
        if "compile" in args:
            output_file = args[args.index("--output-file") + 1]
            Path(output_file).write_text("click==8.1.0\n")
        return b""

    monkeypatch.setattr(appenv, "uv_cmd", mock_uv_cmd)

    # Enable verbose output to check mode detection
    monkeypatch.setenv("APPENV_VERBOSE", "1")

    # Run update_lockfile from subdirectory
    env = appenv.AppEnv(subdir, Path.cwd())
    env.update_lockfile()

    # Verify it detected requirements.txt mode (not pyproject mode)
    captured = capsys.readouterr()
    assert "Mode: requirements.txt" in captured.out

    # Verify pip compile was called (legacy workflow)
    assert any(
        "pip" in call["args"] and "compile" in call["args"] for call in captured_calls
    )

    # Verify it did NOT create uv.lock (would be pyproject workflow)
    assert not (subdir / "uv.lock").exists()

    # Verify requirements.lock was created
    assert (subdir / "requirements.lock").exists()


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
    monkeypatch.setattr(appenv, "find_minimal_python", lambda: None)

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


def test_update_lockfile_requirements_diff_mode(workdir, monkeypatch, capsys):
    """update_lockfile with --diff for requirements.txt shows changes.

    Does not modify the lockfile.
    """
    import argparse

    # Create directory with requirements.txt
    app_dir = Path(workdir) / "reqdiff"
    app_dir.mkdir()

    (app_dir / "requirements.txt").write_text("requests\n")

    # Create existing requirements.lock with old content
    old_lock_content = "# appenv-requirements-hash: oldhash\nrequests==2.28.0\n"
    (app_dir / "requirements.lock").write_text(old_lock_content)

    # Mock ensure_uv and uv_cmd
    monkeypatch.setattr(appenv, "ensure_uv", lambda base: None)
    monkeypatch.setattr(appenv, "find_minimal_python", lambda: None)

    def mock_uv_cmd(args, verbose=False, **kwargs):
        # Simulate pip compile creating new content
        if "compile" in args:
            output_file = args[args.index("--output-file") + 1]
            Path(output_file).write_text("requests==2.31.0\n")
        return b""

    monkeypatch.setattr(appenv, "uv_cmd", mock_uv_cmd)

    env = appenv.AppEnv(app_dir, Path.cwd())
    args = argparse.Namespace(diff=True, verbose=False)

    env.update_lockfile(args=args, remaining=None)

    # Verify diff output was shown
    captured = capsys.readouterr()
    assert "Checking lockfile changes" in captured.out

    # Verify original requirements.lock was NOT modified
    current_content = (app_dir / "requirements.lock").read_text()
    assert current_content == old_lock_content
