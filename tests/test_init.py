"""Tests for init command."""

from pathlib import Path

import appenv


def test_init_fresh_start_interactive(tmp_path, monkeypatch, capsys):
    """init fresh start flow with interactive inputs."""
    monkeypatch.chdir(tmp_path)
    base = tmp_path

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
            "3.10",  # python version
        ]
    )
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    env = appenv.AppEnv(base, Path.cwd())
    env.init()

    # Verify pyproject.toml was created
    pyproject = (base / "pyproject.toml").read_text()
    assert 'name = "myapp-project"' in pyproject
    assert 'description = "My test app"' in pyproject
    assert '"requests"' in pyproject
    assert '"click"' in pyproject
    assert 'requires-python = ">=3.10"' in pyproject

    # Verify appenv script and symlink were created
    assert (base / "appenv").exists()
    assert (base / "myapp").exists()
    assert (base / "myapp").is_symlink()


def test_init_fresh_start_default_dependencies(tmp_path, monkeypatch, capsys):
    """init fresh start uses command name as default dependency when empty."""
    monkeypatch.chdir(tmp_path)
    base = tmp_path

    # No requirements.txt - triggers fresh start flow
    # Use a real package name that exists on PyPI
    inputs = iter(
        [
            "requests",  # command name (real package)
            # empty line immediately - deps default to "requests"
            "",
            "",  # project name (use default: requests-app)
            "",  # empty description
            "",  # python version (use default 3.8)
        ]
    )
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    env = appenv.AppEnv(base, Path.cwd())
    env.init()

    # Verify pyproject.toml was created with command name as dependency
    pyproject = (base / "pyproject.toml").read_text()
    assert 'name = "requests-app"' in pyproject
    assert '"requests"' in pyproject  # dependency defaults to command name
    assert 'requires-python = ">=3.8"' in pyproject  # default version


def test_init_empty_command_name_uses_app(workdir, monkeypatch, capsys):
    """Test fresh start with default command name and dependencies."""
    base = Path(workdir)

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

    env = appenv.AppEnv(base, Path.cwd())
    env.init()

    pyproject = (base / "pyproject.toml").read_text()
    assert 'name = "app-app"' in pyproject
    assert '"app"' in pyproject  # dependency defaults to command name


def test_init_unlink_broken_symlink(workdir, monkeypatch, capsys):
    """Unlinks broken symlink before creating new one."""
    base = Path(workdir)

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

    env = appenv.AppEnv(base, Path.cwd())
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

    env = appenv.AppEnv(base, Path.cwd())
    env.init()

    captured = capsys.readouterr()
    assert "already exists" in captured.out
    assert "Nothing to do" in captured.out


def test_init_empty_command_name_defaults_to_app(workdir, monkeypatch, capsys):
    """Line 847: init() uses 'app' as default when command name is empty."""
    base = Path(workdir)

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

    env = appenv.AppEnv(base, Path.cwd())
    env.init()

    pyproject = (base / "pyproject.toml").read_text()
    assert 'name = "app-app"' in pyproject
    assert '"app"' in pyproject  # dependency also defaults to app
