"""Coverage tests to improve from 98.61% to ~99.5%."""

import os
import shutil
from pathlib import Path

import pytest

import appenv
from appenv import UvVersion


def get_test_settings(basedir=None):
    """Get settings for tests with optional explicit basedir."""
    if basedir is None:
        basedir = appenv.appenv_settings_from_env().basedir
    return appenv.AppEnvSettings(
        verbose=os.environ.get("APPENV_VERBOSE") is not None,
        extras=[
            e.strip()
            for e in (os.environ.get("APPENV_EXTRAS") or "").split(",")
            if e.strip()
        ],
        profile=os.environ.get("APPENV_PROFILING") is not None,
        basedir=basedir,
    )


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
            return ""

    return MockUvBin()


def test_get_profiles_no_profiling_dir(tmp_path):
    """Line 1065: _get_profiles returns empty list if profiling_dir doesn't exist."""
    settings = get_test_settings(tmp_path)
    app = appenv.AppEnv(tmp_path, settings)
    # Don't create the profiling_dir - it should return []
    assert app._get_profiles() == []


def test_ensure_uv_invalid_version(tmp_path, monkeypatch, capsys):
    """Lines 1213-1215: ensure_uv exits with EXIT_CODE_UNAVAILABLE if invalid."""

    # Mock UvBin to return invalid version
    class MockUvBinInvalid:
        def __init__(self, appenv_dir):
            self.bin = Path("/usr/bin/uv")
            self.appenv_dir = appenv_dir

        @property
        def version(self):
            return UvVersion(0, 0, 0)  # Invalid - below minimum

    monkeypatch.setattr(appenv, "UvBin", MockUvBinInvalid)

    with pytest.raises(SystemExit) as exc:
        appenv.ensure_uv(tmp_path)

    assert exc.value.code == appenv.EXIT_CODE_UNAVAILABLE
    captured = capsys.readouterr()
    assert "cannot use uv binary" in captured.out


def test_remove_path_directory_with_files(tmp_path, caplog):
    """Line 144: remove_path removes directory with shutil.rmtree."""
    import logging

    caplog.set_level(logging.DEBUG)
    dir_path = tmp_path / "nested_dir"
    dir_path.mkdir()
    (dir_path / "subdir").mkdir()
    (dir_path / "subdir" / "deep_file.txt").write_text("deep content")
    (dir_path / "file.txt").write_text("content")

    assert dir_path.is_dir()
    assert (dir_path / "subdir" / "deep_file.txt").exists()

    appenv.remove_path(dir_path)

    assert not dir_path.exists()
    assert "Removing directory" in caplog.text


def test_remove_path_nonexistent(tmp_path):
    """Line 144->exit: remove_path with path that doesn't match any condition.

    This covers the implicit fallthrough when path is not a symlink, file, or dir.
    """
    nonexistent = tmp_path / "does_not_exist"

    # Path doesn't exist, so is_symlink, is_file, is_dir all return False
    # This should be a no-op (function exits without doing anything)
    appenv.remove_path(nonexistent)

    # No exception should be raised, path still doesn't exist
    assert not nonexistent.exists()


def test_prepare_venv_replaces_current_symlink(workdir, monkeypatch):
    """Line 1176: _prepare_venv replaces existing current symlink."""
    base = Path(workdir) / "myproject_venv_test"
    base.mkdir()
    os.chdir(base)

    (base / "pyproject.toml").write_text("[project]\nname='test'\nversion='1.0'\n")
    (base / "uv.lock").write_text("version = 1\n")

    settings = get_test_settings(Path.cwd())
    app = appenv.AppEnv(Path.cwd(), settings)

    # Create existing symlink pointing to wrong location
    app.appenv_dir.mkdir(parents=True, exist_ok=True)
    (app.appenv_dir / "current").symlink_to("/wrong/path", target_is_directory=True)

    # Create mock uv - follows the pattern from test_prepare.py
    class MockUvBin:
        def __init__(self):
            self.bin = Path("/usr/bin/uv")
            self._version = UvVersion(0, 7, 0)

        @property
        def version(self):
            return self._version

        def cmd(self, args, verbose=False, **kwargs):
            # Mock uv command - create venv structure
            if "venv" in args:
                venv = base / ".appenv" / "venv"
                venv.mkdir(parents=True, exist_ok=True)
                (venv / "bin").mkdir(exist_ok=True)
                python = venv / "bin" / "python"
                python.write_text("#!/bin/sh\necho Python 3.12.0\n")
                python.chmod(0o755)
            return ""

    mock_uv = MockUvBin()
    monkeypatch.setattr(appenv, "ensure_uv", lambda base: mock_uv)
    # Mock cmd to avoid executing the fake python
    monkeypatch.setattr(appenv, "cmd", lambda c, **kwargs: b"Python 3.12.0")

    app._prepare_venv(dev_mode=False)

    # Verify symlink was replaced
    assert (app.appenv_dir / "current").exists()
    assert (app.appenv_dir / "current").readlink() == Path("venv")

    # Cleanup: Remove the fake venv to prevent interference with other tests
    # Clear UV_PROJECT_ENVIRONMENT to prevent other tests from using this fake python
    os.environ.pop("UV_PROJECT_ENVIRONMENT", None)
    # Remove the fake venv directory
    fake_venv = base / ".appenv" / "venv"
    if fake_venv.exists():
        shutil.rmtree(fake_venv)


def test_prepare_venv_existing_venv(workdir, monkeypatch):
    """Branch 1148->1154: _prepare_venv skips uv venv when venv already exists."""
    base = Path(workdir) / "myproject_existing_venv"
    base.mkdir()
    os.chdir(base)

    (base / "pyproject.toml").write_text("[project]\nname='test'\nversion='1.0'\n")
    (base / "uv.lock").write_text("version = 1\n")

    settings = get_test_settings(Path.cwd())
    app = appenv.AppEnv(Path.cwd(), settings)

    # Create existing venv structure BEFORE calling _prepare_venv
    app.appenv_dir.mkdir(parents=True, exist_ok=True)
    venv = app.appenv_dir / "venv"
    venv.mkdir(parents=True, exist_ok=True)
    (venv / "bin").mkdir(exist_ok=True)
    python = venv / "bin" / "python"
    python.write_text("#!/bin/sh\necho Python 3.12.0\n")
    python.chmod(0o755)

    # Track if uv.cmd was called for venv creation
    venv_called = [False]

    class MockUvBin:
        def __init__(self):
            self.bin = Path("/usr/bin/uv")
            self._version = UvVersion(0, 7, 0)

        @property
        def version(self):
            return self._version

        def cmd(self, args, verbose=False, **kwargs):
            if "venv" in args:
                venv_called[0] = True
            return ""

    mock_uv = MockUvBin()
    monkeypatch.setattr(appenv, "ensure_uv", lambda base: mock_uv)
    monkeypatch.setattr(appenv, "cmd", lambda c, **kwargs: b"Python 3.12.0")

    app._prepare_venv(dev_mode=False)

    # uv venv should NOT have been called since venv already existed
    assert not venv_called[0], "uv venv should be skipped when venv exists"

    # Cleanup
    os.environ.pop("UV_PROJECT_ENVIRONMENT", None)
    if venv.exists():
        shutil.rmtree(venv)


def test_prepare_venv_current_is_directory(workdir, monkeypatch):
    """Branch 1177->1180: _prepare_venv skips symlink when current is a real dir."""
    base = Path(workdir) / "myproject_current_dir"
    base.mkdir()
    os.chdir(base)

    (base / "pyproject.toml").write_text("[project]\nname='test'\nversion='1.0'\n")
    (base / "uv.lock").write_text("version = 1\n")

    settings = get_test_settings(Path.cwd())
    app = appenv.AppEnv(Path.cwd(), settings)

    # Create existing venv
    app.appenv_dir.mkdir(parents=True, exist_ok=True)
    venv = app.appenv_dir / "venv"
    venv.mkdir(parents=True, exist_ok=True)
    (venv / "bin").mkdir(exist_ok=True)
    python = venv / "bin" / "python"
    python.write_text("#!/bin/sh\necho Python 3.12.0\n")
    python.chmod(0o755)

    # Create 'current' as a real directory (not a symlink)
    current_dir = app.appenv_dir / "current"
    current_dir.mkdir()
    (current_dir / "some_file.txt").write_text("test")

    assert current_dir.is_dir()
    assert not current_dir.is_symlink()

    class MockUvBin:
        def __init__(self):
            self.bin = Path("/usr/bin/uv")
            self._version = UvVersion(0, 7, 0)

        @property
        def version(self):
            return self._version

        def cmd(self, args, verbose=False, **kwargs):
            return ""

    mock_uv = MockUvBin()
    monkeypatch.setattr(appenv, "ensure_uv", lambda base: mock_uv)
    monkeypatch.setattr(appenv, "cmd", lambda c, **kwargs: b"Python 3.12.0")

    app._prepare_venv(dev_mode=False)

    # 'current' should still be a directory, not converted to symlink
    assert current_dir.is_dir()
    assert not current_dir.is_symlink()
    assert (current_dir / "some_file.txt").exists()

    # Cleanup
    os.environ.pop("UV_PROJECT_ENVIRONMENT", None)
    if venv.exists():
        shutil.rmtree(venv)


def test_init_appenv_script_already_exists(workdir, monkeypatch, capsys):
    """Branch 882->889: init() skips appenv script creation when it already exists."""
    base = Path(workdir) / "myproject_init_exists"
    base.mkdir()
    os.chdir(base)

    settings = get_test_settings(Path.cwd())
    app = appenv.AppEnv(Path.cwd(), settings)

    # Create appenv script BEFORE calling init
    app.appenv_script.write_text("#!/usr/bin/env python3\nprint('existing')\n")
    app.appenv_script.chmod(0o755)

    original_content = app.appenv_script.read_text()
    original_mtime = app.appenv_script.stat().st_mtime

    # Mock ensure_uv
    monkeypatch.setattr(appenv, "ensure_uv", lambda base: make_mock_uv())

    # Inputs for init
    inputs = iter(
        [
            "myapp",  # command name
            "",  # no dependencies
            "myapp-project",  # project name
            "test",  # description
            "3.13",  # python version
        ]
    )
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    app.init()

    # Verify appenv script was NOT overwritten
    assert app.appenv_script.read_text() == original_content
    assert app.appenv_script.stat().st_mtime == original_mtime

    # Verify pyproject.toml was still created
    assert (base / "pyproject.toml").exists()

    # Verify output does NOT say "Created appenv"
    captured = capsys.readouterr()
    assert "Created appenv" not in captured.out
