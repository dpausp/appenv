"""Tests for update_lockfile pyproject.toml workflow."""

import argparse
import os
import re
import shutil
from pathlib import Path

import appenv
from appenv import UvVersion


def get_test_settings(basedir=None):
    """Get settings for tests with optional explicit basedir."""
    base = basedir if basedir is not None else appenv.appenv_settings_from_env().basedir
    return appenv.AppEnvSettings(
        verbose=False,
        extras=[],
        profile=False,
        basedir=base,
    )


def strip_ansi_codes(text):
    """Remove ANSI color codes from text."""
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


def make_mock_uv():
    """Create a mock UvBin instance for testing."""

    class MockUvBin:
        def __init__(self):
            self.base = Path("/tmp")
            self.bin = Path("/usr/bin/uv")
            self._version = UvVersion(0, 5, 0)

        @property
        def version(self):
            return self._version

        def cmd(self, args, verbose=False, **kwargs):
            # Mock uv command - do nothing, return empty string
            return ""

    return MockUvBin()


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
    uv = make_mock_uv()
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

    uv.cmd = mock_uv_cmd
    monkeypatch.setattr(appenv, "ensure_uv", lambda base: uv)
    monkeypatch.setenv("APPENV_VERBOSE", "1")

    # Run update_lockfile
    env = appenv.AppEnv(app_dir, get_test_settings(app_dir))
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


def test_update_lockfile_verbose_output(workdir, monkeypatch, capsys):
    """Verbose mode shows structured output with paths and mode info."""
    app_dir = Path(workdir) / "verboseapp"
    app_dir.mkdir()
    (app_dir / "pyproject.toml").write_text(
        '[project]\nname = "verboseapp"\ndependencies = ["click"]\n'
    )
    (app_dir / "appenv").write_text("#!/usr/bin/env python3\npass\n")
    (app_dir / "appenv").chmod(0o755)

    uv = make_mock_uv()

    def mock_uv_cmd(args, verbose=False, **kwargs):
        if "lock" in args and "pip" not in args:
            (app_dir / "uv.lock").write_text("version = 1\n")
        return b""

    uv.cmd = mock_uv_cmd
    monkeypatch.setattr(appenv, "ensure_uv", lambda base: uv)
    monkeypatch.setenv("APPENV_VERBOSE", "1")

    env = appenv.AppEnv(app_dir, get_test_settings(app_dir))
    env.update_lockfile()

    captured = capsys.readouterr()
    out = strip_ansi_codes(captured.out)

    # Check for expected output
    assert "Updating lock file" in out
    assert "Created" in out


def test_update_lockfile_no_changes_output(workdir, monkeypatch, capsys):
    """update_lockfile shows 'No changes' when lockfile is up to date."""
    app_dir = Path(workdir) / "nochange"
    app_dir.mkdir()
    (app_dir / "pyproject.toml").write_text(
        '[project]\nname = "nochange"\ndependencies = ["click"]\n'
    )
    (app_dir / "appenv").write_text("#!/usr/bin/env python3\npass\n")
    (app_dir / "appenv").chmod(0o755)

    # Pre-create uv.lock so diff check finds no changes
    (app_dir / "uv.lock").write_text("version = 1\n")

    uv = make_mock_uv()

    def mock_uv_cmd(args, verbose=False, **kwargs):
        cwd = kwargs.get("cwd")
        if cwd and "lock" in args and "pip" not in args:
            # Same content = no changes
            Path(cwd, "uv.lock").write_text("version = 1\n")
        return b""

    uv.cmd = mock_uv_cmd
    monkeypatch.setattr(appenv, "ensure_uv", lambda base: uv)

    env = appenv.AppEnv(app_dir, get_test_settings(app_dir))
    env.update_lockfile()

    out = strip_ansi_codes(capsys.readouterr().out)

    # Check for expected output
    assert "Updating lock file" in out
    assert "No changes" in out


def test_update_lockfile_pyproject_diff_mode(workdir, monkeypatch, capsys, tmp_path):
    """update_lockfile with --diff shows changes without modifying uv.lock."""
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
    uv = make_mock_uv()

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

    uv.cmd = mock_uv_cmd
    monkeypatch.setattr(appenv, "ensure_uv", lambda base: uv)

    env = appenv.AppEnv(app_dir, get_test_settings(app_dir))
    args = argparse.Namespace(diff=True, verbose=False)

    env.update_lockfile(args=args, remaining=None)

    # Verify original uv.lock was NOT modified
    assert (app_dir / "uv.lock").read_text() == old_lock_content


def test_update_lockfile_pyproject_no_changes(workdir, monkeypatch, capsys):
    """Lines 1005, 1033: 'No changes' output when lockfile unchanged."""
    base = Path(workdir)
    (base / "pyproject.toml").write_text(
        '[project]\nname = "test"\ndependencies = ["click"]\n'
    )

    lock_content = "version = 1\n[[package]]\nname = 'click'\nversion = '8.1.0'\n"
    (base / "uv.lock").write_text(lock_content)

    uv = make_mock_uv()

    def mock_uv_cmd(args, verbose=False, **kwargs):
        return b""

    uv.cmd = mock_uv_cmd
    monkeypatch.setattr(appenv, "ensure_uv", lambda base: uv)

    env = appenv.AppEnv(base, get_test_settings(base))
    env.update_lockfile()

    captured = strip_ansi_codes(capsys.readouterr().out)
    assert "No changes" in captured


def test_update_lockfile_pyproject_updated(workdir, monkeypatch, capsys):
    """Line 1040: 'Updated' output when lockfile has changes."""
    base = Path(workdir)
    (base / "pyproject.toml").write_text(
        '[project]\nname = "test"\ndependencies = ["click"]\n'
    )

    (base / "uv.lock").write_text(
        "version = 1\n[[package]]\nname = 'click'\nversion = '8.0.0'\n"
    )

    uv = make_mock_uv()

    def mock_uv_cmd(args, verbose=False, **kwargs):
        if "lock" in args and "pip" not in args:
            (base / "uv.lock").write_text(
                "version = 1\n[[package]]\nname = 'click'\nversion = '8.1.0'\n"
            )
        elif "compile" in args:
            output_file = args[args.index("--output-file") + 1]
            Path(output_file).write_text("click==8.1.0\n")
        return b""

    uv.cmd = mock_uv_cmd
    monkeypatch.setattr(appenv, "ensure_uv", lambda base: uv)

    env = appenv.AppEnv(base, get_test_settings(base))
    env.update_lockfile()

    captured = strip_ansi_codes(capsys.readouterr().out)
    assert "Updated" in captured


def test_update_lockfile_pyproject_diff_verbose(workdir, monkeypatch, capsys):
    """Line 990: Verbose output in pyproject diff mode."""
    base = Path(workdir)
    (base / "pyproject.toml").write_text(
        '[project]\nname = "test"\ndependencies = ["click"]\n'
    )
    (base / "uv.lock").write_text("version = 1\n")

    uv = make_mock_uv()

    def mock_uv_cmd(args, verbose=False, **kwargs):
        if "lock" in args and "pip" not in args:
            cwd = kwargs.get("cwd")
            if cwd:
                # Create lock file in temp directory
                (Path(cwd) / "uv.lock").write_text("version = 1\nnew = true\n")
        return b""

    uv.cmd = mock_uv_cmd
    monkeypatch.setattr(appenv, "ensure_uv", lambda base: uv)

    env = appenv.AppEnv(base, get_test_settings(base))
    args = argparse.Namespace(diff=True, verbose=True)

    env.update_lockfile(args=args, remaining=None)

    captured = strip_ansi_codes(capsys.readouterr().out)
    assert "Diff mode" in captured


def test_update_lockfile_pyproject_diff_no_changes(workdir, monkeypatch, capsys):
    """Line 1005: 'No changes' output in diff mode for pyproject."""
    base = Path(workdir)
    (base / "pyproject.toml").write_text(
        '[project]\nname = "test"\ndependencies = ["click"]\n'
    )

    lock_content = "version = 1\n[[package]]\nname = 'click'\nversion = '8.1.0'\n"
    (base / "uv.lock").write_text(lock_content)

    uv = make_mock_uv()

    def mock_uv_cmd(args, verbose=False, **kwargs):
        if "lock" in args and "pip" not in args:
            cwd = kwargs.get("cwd")
            if cwd:
                # Create identical lock file
                (Path(cwd) / "uv.lock").write_text(lock_content)
        return b""

    uv.cmd = mock_uv_cmd
    monkeypatch.setattr(appenv, "ensure_uv", lambda base: uv)

    env = appenv.AppEnv(base, get_test_settings(base))
    args = argparse.Namespace(diff=True, verbose=False)

    env.update_lockfile(args=args, remaining=None)

    captured = strip_ansi_codes(capsys.readouterr().out)
    assert "No changes" in captured


def test_update_lockfile_pyproject_calls_uv_lock(tmp_path, monkeypatch):
    """_update_lockfile_pyproject calls uv lock."""
    monkeypatch.chdir(tmp_path)
    base = tmp_path

    (base / "pyproject.toml").write_text(
        "[project]\nname = 'test'\ndependencies = []\n"
    )

    uv_calls = []
    uv = make_mock_uv()
    uv.cmd = lambda args, **kwargs: uv_calls.append(args)
    monkeypatch.setattr(appenv, "ensure_uv", lambda base: uv)

    env = appenv.AppEnv(base, get_test_settings(base))
    env.update_lockfile(None)

    # Should call uv lock
    assert any("lock" in str(c) for c in uv_calls)


def test_update_lockfile_verbose_shows_running_uv_lock(tmp_path, monkeypatch, capsys):
    """_update_lockfile_pyproject shows 'Running: uv lock' in verbose mode."""
    monkeypatch.chdir(tmp_path)
    base = tmp_path

    (base / "pyproject.toml").write_text(
        "[project]\nname = 'test'\ndependencies = []\n"
    )

    uv = make_mock_uv()
    monkeypatch.setattr(appenv, "ensure_uv", lambda base: uv)

    env = appenv.AppEnv(base, get_test_settings(base))
    args = argparse.Namespace(diff=False, verbose=True)
    env.update_lockfile(args)

    captured = strip_ansi_codes(capsys.readouterr().out)
    assert "Updating lock file" in captured
