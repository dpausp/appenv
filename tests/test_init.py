"""Tests for init command."""

import argparse
from pathlib import Path

import pytest

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
            # Mock uv command - do nothing
            return ""

    return MockUvBin()


def test_init_fresh_start_interactive(tmp_path, monkeypatch, capsys):
    """Init fresh start flow with interactive inputs."""
    monkeypatch.chdir(tmp_path)
    base = tmp_path

    # Mock ensure_uv to return a mock UvBin with valid version
    monkeypatch.setattr(appenv, "ensure_uv", lambda base: make_mock_uv())

    # No requirements.txt - triggers fresh start flow
    # Inputs: command name, deps (2), empty, project name, desc, py version
    inputs = iter(
        [
            "myapp",  # command name
            "requests",  # dependency 1
            "click",  # dependency 2
            "",  # empty line to finish dependencies
            "myapp-project",  # project name
            "My test app",  # description
            "3.13",  # python version
        ]
    )
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    env = appenv.AppEnv(Path.cwd(), get_test_settings(Path.cwd()))
    env.init()

    # Verify pyproject.toml was created
    pyproject = (base / "pyproject.toml").read_text()
    assert 'name = "myapp-project"' in pyproject
    assert 'description = "My test app"' in pyproject
    assert '"requests"' in pyproject
    assert '"click"' in pyproject
    assert 'requires-python = ">=3.13"' in pyproject

    # Verify appenv script and symlink were created
    assert (base / "appenv").exists()
    assert (base / "myapp").exists()
    assert (base / "myapp").is_symlink()


def test_init_fresh_start_default_dependencies(tmp_path, monkeypatch, capsys):
    """Init fresh start uses command name as default dependency when empty."""
    monkeypatch.chdir(tmp_path)
    base = tmp_path

    # Mock ensure_uv to return a mock UvBin with valid version
    monkeypatch.setattr(appenv, "ensure_uv", lambda base: make_mock_uv())

    # No requirements.txt - triggers fresh start flow
    # Use a real package name that exists on PyPI
    inputs = iter(
        [
            "requests",  # command name (real package)
            # empty line immediately - deps default to "requests"
            "",
            "",  # project name (use default: requests-app)
            "",  # empty description
            "",  # python version (use default 3.13)
        ]
    )
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    env = appenv.AppEnv(Path.cwd(), get_test_settings(Path.cwd()))
    env.init()

    # Verify pyproject.toml was created with command name as dependency
    pyproject = (base / "pyproject.toml").read_text()
    assert 'name = "requests-app"' in pyproject
    assert '"requests"' in pyproject  # dependency defaults to command name
    assert 'requires-python = ">=3.13"' in pyproject  # default version


def test_init_empty_command_name_uses_app(workdir, monkeypatch, capsys):
    """Test fresh start with default command name and dependencies."""
    base = Path(workdir)

    # Mock ensure_uv to return a mock UvBin with valid version
    monkeypatch.setattr(appenv, "ensure_uv", lambda base: make_mock_uv())

    inputs = iter(
        [
            "app",  # command name (explicitly "app")
            "",  # empty dependencies -> defaults to "app"
            "",  # project name (default: app-app)
            "test description",
            "",  # python version (default)
        ]
    )
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    env = appenv.AppEnv(Path.cwd(), get_test_settings(Path.cwd()))
    env.init()

    pyproject = (base / "pyproject.toml").read_text()
    assert 'name = "app-app"' in pyproject
    assert '"app"' in pyproject  # dependency defaults to command name


def test_init_unlink_broken_symlink(workdir, monkeypatch, capsys):
    """Unlinks broken symlink before creating new one."""
    base = Path(workdir)

    # Mock ensure_uv to return a mock UvBin with valid version
    monkeypatch.setattr(appenv, "ensure_uv", lambda base: make_mock_uv())

    broken_link = base / "myapp"
    broken_link.symlink_to("nonexistent_target")
    assert broken_link.is_symlink()
    assert not broken_link.exists()

    inputs = iter(
        [
            "myapp",  # command name
            "",  # empty dependencies -> defaults to "myapp"
            "",  # project name (default: myapp-app)
            "",  # description
            "",  # python version
        ]
    )
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    env = appenv.AppEnv(Path.cwd(), get_test_settings(Path.cwd()))
    env.init()

    assert (base / "myapp").is_symlink()
    assert (base / "myapp").exists()
    assert (base / "myapp").resolve() == (base / "appenv").resolve()


def test_init_already_exists(workdir, monkeypatch, capsys):
    """Lines 838-841: init() returns early when pyproject.toml exists."""
    base = Path(workdir)

    (base / "pyproject.toml").write_text(
        '[project]\nname = "existing"\ndependencies = []\n'
    )

    env = appenv.AppEnv(Path.cwd(), get_test_settings(Path.cwd()))

    with pytest.raises(SystemExit) as exc_info:
        env.init()

    assert exc_info.value.code == 65  # EXIT_CODE_DATAERR

    captured = capsys.readouterr()
    assert "already exists" in captured.out
    assert "Nothing to do" in captured.out


def test_init_empty_command_name_defaults_to_app(workdir, monkeypatch, capsys):
    """Line 847: init() uses 'app' as default when command name is empty."""
    base = Path(workdir)

    # Mock ensure_uv to return a mock UvBin with valid version
    monkeypatch.setattr(appenv, "ensure_uv", lambda base: make_mock_uv())

    # Empty command name -> defaults to "app"
    inputs = iter(
        [
            "",  # empty command name -> default "app"
            "",  # no dependencies -> defaults to "app"
            "",  # project name (default: app-app)
            "test description",
            "",  # python version default
        ]
    )
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    env = appenv.AppEnv(Path.cwd(), get_test_settings(Path.cwd()))
    env.init()

    pyproject = (base / "pyproject.toml").read_text()
    assert 'name = "app-app"' in pyproject
    assert '"app"' in pyproject  # dependency also defaults to app


def test_init_with_path_creates_directory(tmp_path, monkeypatch, capsys):
    """init with path argument creates directory and initializes there."""
    base = tmp_path
    target_dir = base / "myproject"

    # Mock ensure_uv to return a mock UvBin with valid version
    monkeypatch.setattr(appenv, "ensure_uv", lambda base: make_mock_uv())

    inputs = iter(
        [
            "myapp",  # command name
            "",  # empty dependencies -> defaults to "myapp"
            "",  # project name (default: myapp-app)
            "Test project",
            "",  # python version
        ]
    )
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    env = appenv.AppEnv(base, get_test_settings(base))
    args = argparse.Namespace(path="myproject")
    env.init(args)

    # Verify directory was created
    assert target_dir.exists()
    assert target_dir.is_dir()

    # Verify pyproject.toml was created in target directory
    pyproject = (target_dir / "pyproject.toml").read_text()
    assert 'name = "myapp-app"' in pyproject
    assert '"myapp"' in pyproject

    # Verify appenv script and symlink are created in base directory
    # (self.base is the original basedir, not the target)
    assert (base / "appenv").exists()
    assert (base / "myapp").exists()
    assert (base / "myapp").is_symlink()


def test_init_with_nested_path_creates_directories(tmp_path, monkeypatch, capsys):
    """init with nested path creates all parent directories."""
    base = tmp_path
    target_dir = base / "some" / "nested" / "path"

    # Mock ensure_uv to return a mock UvBin with valid version
    monkeypatch.setattr(appenv, "ensure_uv", lambda base: make_mock_uv())

    inputs = iter(
        [
            "nestedapp",  # command name
            "",  # empty dependencies
            "",  # project name
            "Nested project",
            "",  # python version
        ]
    )
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    env = appenv.AppEnv(base, get_test_settings(base))
    args = argparse.Namespace(path="some/nested/path")
    env.init(args)

    # Verify all directories were created
    assert target_dir.exists()
    assert target_dir.is_dir()

    # Verify pyproject.toml was created in target directory
    assert (target_dir / "pyproject.toml").exists()
    pyproject = (target_dir / "pyproject.toml").read_text()
    assert 'name = "nestedapp-app"' in pyproject


def test_init_with_existing_directory(tmp_path, monkeypatch, capsys):
    """init with path to existing directory initializes inside it."""
    base = tmp_path
    target_dir = base / "existing"
    target_dir.mkdir()

    # Mock ensure_uv to return a mock UvBin with valid version
    monkeypatch.setattr(appenv, "ensure_uv", lambda base: make_mock_uv())

    inputs = iter(
        [
            "existingapp",  # command name
            "",  # empty dependencies
            "",  # project name
            "Existing dir project",
            "",  # python version
        ]
    )
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    env = appenv.AppEnv(base, get_test_settings(base))
    args = argparse.Namespace(path="existing")
    env.init(args)

    # Verify pyproject.toml was created in existing directory
    assert (target_dir / "pyproject.toml").exists()
    pyproject = (target_dir / "pyproject.toml").read_text()
    assert 'name = "existingapp-app"' in pyproject


def test_init_without_path_uses_current_directory(tmp_path, monkeypatch, capsys):
    """init without path argument uses current directory (original_cwd)."""
    base = tmp_path
    monkeypatch.chdir(base)

    # Mock ensure_uv to return a mock UvBin with valid version
    monkeypatch.setattr(appenv, "ensure_uv", lambda base: make_mock_uv())

    inputs = iter(
        [
            "cwdapp",  # command name
            "",  # empty dependencies
            "",  # project name
            "Current dir project",
            "",  # python version
        ]
    )
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    env = appenv.AppEnv(Path.cwd(), get_test_settings(Path.cwd()))
    # Call init without args (path=None is default)
    env.init()

    # Verify pyproject.toml was created in current directory (base)
    assert (base / "pyproject.toml").exists()
    pyproject = (base / "pyproject.toml").read_text()
    assert 'name = "cwdapp-app"' in pyproject
