"""Tests for migrate command."""

from pathlib import Path

import appenv


def get_test_settings():
    """Get default settings for tests."""
    return appenv.AppEnvSettings.from_env()


def test_migrate_uses_python_preference_from_requirements(
    tmp_path, monkeypatch, capsys
):
    """migrate reads python preference from requirements.txt."""
    monkeypatch.chdir(tmp_path)
    base = tmp_path

    # Create requirements.txt with python preference
    (base / "requirements.txt").write_text(
        "# appenv-python-preference: 3.12,3.13,3.14\nrequests\n"
    )

    # Mock input to use defaults
    inputs = iter(["test-project"])  # project name
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    env = appenv.AppEnv(base, Path.cwd(), get_test_settings())
    env.migrate()

    # Classic assertions for pyproject.toml with python version
    pyproject = (base / "pyproject.toml").read_text()
    assert 'requires-python = ">=3.12"' in pyproject
    assert '"requests"' in pyproject

    # Simple assertions for console output
    captured = capsys.readouterr()
    assert "Found python preference: 3.12, 3.13, 3.14" in captured.out
    assert "Using minimum version: 3.12" in captured.out


def test_migrate_editable_warnings(tmp_path, monkeypatch, capsys, patterns):
    """migrate warns about editable installs during migration."""
    monkeypatch.chdir(tmp_path)
    base = tmp_path

    # Create requirements.txt with editable installs
    (base / "requirements.txt").write_text(
        "-e /path/to/local/pkg\n-e ../another-pkg\nrequests\nclick\n"
    )

    # Mock input to use defaults
    inputs = iter(["myproject"])  # project name
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    env = appenv.AppEnv(base, Path.cwd(), get_test_settings())
    env.migrate()

    # Pattern-test for console output
    captured = capsys.readouterr()
    patterns.editable_warnings.in_order(
        """\
...warning: 2 editable install(s) skipped:
...-e /path/to/local/pkg...
...-e ../another-pkg..."""
    )

    patterns.clean_output.optional("...")
    patterns.clean_output.refused("...error...")
    patterns.clean_output.refused("...exception...")
    patterns.clean_output.refused("...traceback...")
    patterns.clean_output.refused("...failed...")

    full_pattern = patterns.full
    full_pattern.merge("editable_warnings", "clean_output")

    example = full_pattern.generate_example()
    print(f"\n=== Pattern Example ===\n{example}\n=== End ===\n")

    assert full_pattern == captured.out.lower()

    # Classic assertions for pyproject.toml (NO editable, NO uv.sources)
    pyproject = (base / "pyproject.toml").read_text()
    assert "-e" not in pyproject
    assert '"requests"' in pyproject
    assert '"click"' in pyproject
    assert "[tool.uv.sources]" not in pyproject


def test_migrate_merges_with_tool_only_pyproject(tmp_path, monkeypatch, capsys):
    """migrate adds [project] section to pyproject.toml with only tool configs."""
    monkeypatch.chdir(tmp_path)
    base = tmp_path

    (base / "pyproject.toml").write_text(
        '[tool.ruff]\nline-length = 88\n\n[tool.pytest]\naddopts = ["-v"]\n'
    )

    (base / "requirements.txt").write_text("requests>=2.0\n")

    env = appenv.AppEnv(base, Path.cwd(), get_test_settings())
    env.migrate()

    pyproject = (base / "pyproject.toml").read_text()

    # Simple assertions for console output
    captured = capsys.readouterr()
    assert "Adding [project] section to existing pyproject.toml" in captured.out
    assert "Done. pyproject.toml created." in captured.out

    # Classic assertions for pyproject.toml structure
    assert "[tool.ruff]" in pyproject
    assert "[tool.pytest]" in pyproject
    assert "[project]" in pyproject
    assert 'name = "' in pyproject
    assert '"requests>=2.0"' in pyproject


def test_migrate_existing_symlinks(tmp_path, monkeypatch, capsys):
    """migrate detects and preserves existing symlinks during migration."""
    monkeypatch.chdir(tmp_path)
    base = tmp_path

    # Create requirements.txt and appenv script
    (base / "requirements.txt").write_text("requests\n")
    appenv_script = base / "appenv"
    appenv_script.write_text("#!/usr/bin/env python3\nprint('appenv')\n")
    appenv_script.chmod(0o755)

    # Create symlink pointing to appenv
    myapp_link = base / "myapp"
    myapp_link.symlink_to("appenv")

    # Mock input to use defaults
    inputs = iter(["myproject"])  # project name
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    env = appenv.AppEnv(base, Path.cwd(), get_test_settings())
    env.migrate()

    # Simple assertion for console output
    captured = capsys.readouterr()
    assert "found existing symlink(s): myapp" in captured.out.lower()

    # Verify symlink still exists and points to appenv
    assert myapp_link.exists()
    assert myapp_link.is_symlink()
    assert myapp_link.resolve() == appenv_script.resolve()


def test_migrate_empty_dependencies(tmp_path, monkeypatch, capsys):
    """migrate handles requirements.txt with only comments (no dependencies)."""
    monkeypatch.chdir(tmp_path)
    base = tmp_path

    # Create requirements.txt with only comments
    (base / "requirements.txt").write_text(
        "# This is a comment\n# Another comment\n# No actual dependencies\n"
    )

    # Mock input to use defaults
    inputs = iter(["empty-project"])  # project name
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    env = appenv.AppEnv(base, Path.cwd(), get_test_settings())
    env.migrate()

    # Check pyproject.toml was created with empty dependencies
    pyproject = (base / "pyproject.toml").read_text()
    assert "dependencies = []" in pyproject

    # Verify output mentions 0 dependencies found
    captured = capsys.readouterr()
    assert "0 dependency" in captured.out or "Found 0" in captured.out


def test_migrate_uses_directory_name(tmp_path, monkeypatch, capsys):
    """migrate uses directory name as project name (non-interactive)."""
    monkeypatch.chdir(tmp_path)
    base = tmp_path

    # Create requirements.txt to trigger migration
    (base / "requirements.txt").write_text("requests>=2.0\n")

    env = appenv.AppEnv(base, Path.cwd(), get_test_settings())
    env.migrate()

    # Verify pyproject.toml uses directory name as project name
    pyproject = (base / "pyproject.toml").read_text()
    assert f'name = "{base.name}"' in pyproject
    assert '"requests>=2.0"' in pyproject

    captured = capsys.readouterr()
    assert "Migrating" in captured.out
