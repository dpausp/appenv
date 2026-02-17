import io
import os
import shutil
import sys
import unittest.mock
from pathlib import Path

import pytest

import appenv


def test_init_and_create_lockfile(workdir, monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO("ducker\nducker<2.0.2\n\n"))

    env = appenv.AppEnv(Path(workdir) / "ducker", Path.cwd())
    env.init()

    lockfile = os.path.join(workdir, "ducker", "requirements.lock")
    assert not os.path.exists(lockfile)

    env.update_lockfile()

    assert os.path.exists(lockfile)
    with open(lockfile) as f:
        lockfile_content = f.read()
    # UV generates lockfile with header and via-comments
    assert "ducker==2.0.1" in lockfile_content
    assert "# appenv-requirements-hash:" in lockfile_content


def test_update_lockfile_uses_minimal_python(workdir, monkeypatch):
    """It uses the minimal python version from preferences for lockfile."""
    monkeypatch.setattr("sys.stdin", io.StringIO("httpie\nhttpie\nmyapp\n"))
    monkeypatch.setattr(appenv, "ensure_uv", lambda base: None)

    env = appenv.AppEnv(Path(workdir) / "myapp", Path.cwd())
    env.init()

    requirements_file = Path(workdir) / "myapp" / "requirements.txt"
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

    env.update_lockfile()

    # Verify --python flag was passed with minimal version
    assert any("--python" in str(arg) for arg in captured_args)
    assert any("python3.9" in str(arg) for arg in captured_args)


@pytest.mark.skipif(sys.version_info[0:2] < (3, 8), reason="Isolated CI builds")
def test_update_lockfile_missing_minimal_python(workdir, monkeypatch):
    """It raises an error if the minimal python is not available."""
    monkeypatch.setattr("sys.stdin", io.StringIO("pytest\npytest==6.1.2\nppytest\n"))

    env = appenv.AppEnv(Path(workdir) / "ppytest", Path.cwd())
    env.init()

    requirements_file = os.path.join(workdir, "ppytest", "requirements.txt")

    with open(requirements_file, "r+") as f:
        lines = f.readlines()
        lines[0] = "# appenv-python-preference: 3.8,3.6,3.9\n"
        f.seek(0)
        f.writelines(lines)

    old_which = shutil.which

    def new_which(string):
        if string == "python3.6":
            return None
        else:
            return old_which(string)

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

    # Run update_lockfile from subdirectory
    env = appenv.AppEnv(subdir, Path.cwd())
    env.update_lockfile()

    # Verify it detected requirements.txt mode (not pyproject mode)
    captured = capsys.readouterr()
    assert "Mode: requirements.txt" in captured.out
    assert (
        "pyproject.toml" not in captured.out.lower()
        or "no pyproject" in captured.out.lower()
    )

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
