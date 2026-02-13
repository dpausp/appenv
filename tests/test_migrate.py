"""Tests for migrate command."""

from pathlib import Path

import appenv


def get_test_settings(basedir=None):
    """Get settings for tests with optional explicit basedir."""
    base = basedir if basedir is not None else appenv.appenv_settings_from_env().basedir
    return appenv.AppEnvSettings(
        verbose=False,
        extras=[],
        profile=False,
        basedir=base,
    )


def test_migrate_uses_python_preference_from_requirements(
    tmp_path, monkeypatch, capsys
):
    """Migrate reads python preference from requirements.txt."""
    monkeypatch.chdir(tmp_path)
    base = tmp_path

    # Create requirements.txt with python preference (3.12 and 3.14, missing 3.13)
    (base / "requirements.txt").write_text(
        "# appenv-python-preference: 3.12,3.14\nrequests\n"
    )

    # Mock input to use defaults
    inputs = iter(["test-project"])  # project name
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    env = appenv.AppEnv(Path.cwd(), get_test_settings(Path.cwd()))
    env.migrate()

    # Classic assertions for pyproject.toml with python version range specifier
    pyproject = (base / "pyproject.toml").read_text()
    assert 'requires-python = ">=3.12,<3.15"' in pyproject
    assert '"requests"' in pyproject

    # Simple assertions for console output
    captured = capsys.readouterr()
    assert "Found python preference: 3.12, 3.14" in captured.out
    assert "Migration completed" in captured.out

    # Verify note is printed about missing version (3.13 not in list)
    assert "Note: Versions 3.13" in captured.out


def test_migrate_existing_symlinks(tmp_path, monkeypatch, capsys):
    """Migrate detects and preserves existing symlinks during migration."""
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

    env = appenv.AppEnv(Path.cwd(), get_test_settings(Path.cwd()))
    env.migrate()

    # Simple assertion for console output
    captured = capsys.readouterr()
    assert "Migration completed" in captured.out

    # Verify symlink still exists and points to appenv
    assert myapp_link.exists()
    assert myapp_link.is_symlink()
    assert myapp_link.resolve() == appenv_script.resolve()


def test_migrate_empty_dependencies(tmp_path, monkeypatch, capsys):
    """Migrate handles requirements.txt with only comments (no dependencies)."""
    monkeypatch.chdir(tmp_path)
    base = tmp_path

    # Create requirements.txt with only comments
    (base / "requirements.txt").write_text(
        "# This is a comment\n# Another comment\n# No actual dependencies\n"
    )

    # Mock input to use defaults
    inputs = iter(["empty-project"])  # project name
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    env = appenv.AppEnv(Path.cwd(), get_test_settings(Path.cwd()))
    env.migrate()

    # Check pyproject.toml was created with empty dependencies
    pyproject = (base / "pyproject.toml").read_text()
    assert "dependencies = []" in pyproject

    # Verify output mentions 0 dependencies found
    captured = capsys.readouterr()
    assert "0 dependency" in captured.out or "Found 0" in captured.out


def test_migrate_uses_directory_name(tmp_path, monkeypatch, capsys):
    """Migrate uses directory name as project name (non-interactive)."""
    monkeypatch.chdir(tmp_path)
    base = tmp_path

    # Create requirements.txt to trigger migration
    (base / "requirements.txt").write_text("requests>=2.0\n")

    env = appenv.AppEnv(Path.cwd(), get_test_settings(Path.cwd()))
    env.migrate()

    # Verify pyproject.toml uses directory name as project name
    pyproject = (base / "pyproject.toml").read_text()
    assert f'name = "{base.name}"' in pyproject
    assert '"requests>=2.0"' in pyproject

    captured = capsys.readouterr()
    assert "Migrating" in captured.out


def test_migrate_already_exists(tmp_path, monkeypatch, capsys, patterns):
    """Migrate returns early when pyproject.toml already exists."""
    monkeypatch.chdir(tmp_path)
    base = tmp_path

    # Create existing pyproject.toml
    (base / "pyproject.toml").write_text(
        '[project]\nname = "existing"\ndependencies = []\n'
    )

    env = appenv.AppEnv(Path.cwd(), get_test_settings(Path.cwd()))
    env.migrate()

    # Pattern-test for console output
    captured = capsys.readouterr()
    patterns.main.in_order(
        """\
pyproject.toml already has [project] section in ...
Nothing to do."""
    )

    full_pattern = patterns.full
    full_pattern.merge("main")

    full_pattern.generate_example()

    assert full_pattern == captured.out


def test_migrate_no_requirements_txt(workdir, monkeypatch, capsys, patterns):
    """Lines 888-890: migrate() returns early when requirements.txt not found."""
    Path(workdir)

    env = appenv.AppEnv(Path.cwd(), get_test_settings(Path.cwd()))
    env.migrate()

    captured = capsys.readouterr()

    patterns.main.in_order(
        """\
No requirements.txt found in ...
Use 'init' to create a new project."""
    )

    full_pattern = patterns.full
    full_pattern.merge("main")

    full_pattern.generate_example()

    assert full_pattern == captured.out


def test_migrate_editable_missing_package_warns(
    tmp_path, monkeypatch, capsys, patterns
):
    """init_pyproject warns when editable path has no package metadata."""
    monkeypatch.chdir(tmp_path)
    base = tmp_path

    empty_dir = base / "empty-dir"
    empty_dir.mkdir()

    (base / "requirements.txt").write_text("-e ./empty-dir\nrequests\n")

    inputs = iter(["myproject"])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    env = appenv.AppEnv(Path.cwd(), get_test_settings(Path.cwd()))
    env.migrate()

    captured = capsys.readouterr()

    patterns.any.optional("...")
    patterns.main.merge("any")
    patterns.main.in_order(
        """\
...warning...skipped...
...-e ./empty-dir..."""
    )

    patterns.no_errors.optional("...")
    patterns.no_errors.refused("...error...")
    patterns.no_errors.refused("...exception...")
    patterns.no_errors.refused("...traceback...")
    patterns.no_errors.refused("...failed...")

    full_pattern = patterns.full
    full_pattern.merge("main", "no_errors")

    full_pattern.generate_example()

    assert full_pattern == captured.out.lower()

    pyproject = (base / "pyproject.toml").read_text()
    assert '"requests"' in pyproject
    assert "[tool.uv.sources]" not in pyproject


def test_migrate_editable_git_url_warns(tmp_path, monkeypatch, capsys, patterns):
    """init_pyproject warns for git URL editable (not supported)."""
    monkeypatch.chdir(tmp_path)
    base = tmp_path

    (base / "requirements.txt").write_text(
        "-e git+https://github.com/user/repo.git\nrequests\n"
    )

    inputs = iter(["myproject"])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    env = appenv.AppEnv(Path.cwd(), get_test_settings(Path.cwd()))
    env.migrate()

    captured = capsys.readouterr()

    patterns.any.optional("...")
    patterns.main.merge("any")
    patterns.main.in_order(
        """\
...warning...skipped...
...git+https://github.com/user/repo.git..."""
    )

    patterns.no_errors.optional("...")
    patterns.no_errors.refused("...error...")
    patterns.no_errors.refused("...exception...")
    patterns.no_errors.refused("...traceback...")
    patterns.no_errors.refused("...failed...")

    full_pattern = patterns.full
    full_pattern.merge("main", "no_errors")

    full_pattern.generate_example()

    assert full_pattern == captured.out.lower()

    pyproject = (base / "pyproject.toml").read_text()
    assert '"requests"' in pyproject
    assert "[tool.uv.sources]" not in pyproject


def test_migrate_editable_mixed_valid_and_invalid(
    tmp_path, monkeypatch, capsys, patterns
):
    """init_pyproject handles mix of valid and invalid editables."""
    monkeypatch.chdir(tmp_path)
    base = tmp_path

    # Create valid package
    valid_pkg = base / "valid-pkg"
    valid_pkg.mkdir()
    (valid_pkg / "pyproject.toml").write_text(
        '[project]\nname = "valid-pkg"\nversion = "1.0.0"\n'
    )

    # Create empty invalid package
    empty_dir = base / "empty-dir"
    empty_dir.mkdir()

    (base / "requirements.txt").write_text("-e ./valid-pkg\n-e ./empty-dir\nrequests\n")

    inputs = iter(["myproject"])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    env = appenv.AppEnv(Path.cwd(), get_test_settings(Path.cwd()))
    env.migrate()

    captured = capsys.readouterr()

    patterns.any.optional("...")
    patterns.main.merge("any")
    patterns.main.in_order("...warning...skipped...")

    patterns.no_errors.optional("...")
    patterns.no_errors.refused("...error...")
    patterns.no_errors.refused("...exception...")
    patterns.no_errors.refused("...traceback...")
    patterns.no_errors.refused("...failed...")

    full_pattern = patterns.full
    full_pattern.merge("main", "no_errors")

    full_pattern.generate_example()

    assert full_pattern == captured.out.lower()

    # Check pyproject.toml
    pyproject = (base / "pyproject.toml").read_text()
    assert "requests" in pyproject


def test_migrate_editable_warnings_updated(tmp_path, monkeypatch, capsys, patterns):
    """init_pyproject warns about unsupported editable formats (git URLs, etc)."""
    monkeypatch.chdir(tmp_path)
    base = tmp_path

    # Create requirements.txt with git URLs (not supported)
    (base / "requirements.txt").write_text(
        "-e git+https://github.com/user/pkg.git\n"
        "-e package @ ./path\n"  # PEP 508 format
        "requests\nclick\n"
    )

    # Mock input to use defaults
    inputs = iter(["myproject"])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    env = appenv.AppEnv(Path.cwd(), get_test_settings(Path.cwd()))
    env.migrate()

    # Check output mentions editable installs warning
    captured = capsys.readouterr()
    patterns.any.optional("...")
    patterns.main.merge("any")
    patterns.main.in_order(
        """\
...warning...skipped...
...-e git+https://github.com/user/pkg.git...
...add them manually..."""
    )

    patterns.no_errors.optional("...")
    patterns.no_errors.refused("...error...")
    patterns.no_errors.refused("...exception...")
    patterns.no_errors.refused("...traceback...")
    patterns.no_errors.refused("...failed...")

    full_pattern = patterns.full
    full_pattern.merge("main", "no_errors")

    full_pattern.generate_example()

    assert full_pattern == captured.out.lower()

    # Check pyproject.toml was created with only regular deps
    pyproject = (base / "pyproject.toml").read_text()
    assert "-e" not in pyproject
    assert "requests" in pyproject
    assert "click" in pyproject
    assert "[tool.uv.sources]" not in pyproject
    assert "[tool.uv.sources]" not in pyproject


def test_migrate_existing_pyproject_no_project_section(
    tmp_path, monkeypatch, capsys, patterns
):
    """Line 884: migrate() when pyproject.toml exists but has no [project] section."""
    monkeypatch.chdir(tmp_path)
    base = tmp_path

    # Create pyproject.toml without [project] section (e.g., only tool config)
    (base / "pyproject.toml").write_text("[tool.ruff]\nline-length = 100\n")

    # Create requirements.txt to allow migration
    (base / "requirements.txt").write_text("requests\n")

    # Mock ensure_uv to prevent actual uv execution
    monkeypatch.setattr(appenv, "ensure_uv", lambda base: None)

    # Mock migrate_from_requirements_txt to return a pyproject
    def mock_migrate(self):
        (base / "pyproject.toml").write_text(
            '[project]\nname = "test"\n[tool.ruff]\nline-length = 100\n'
        )
        return self

    monkeypatch.setattr(appenv.Pyproject, "migrate_from_requirements_txt", mock_migrate)

    # Mock print_migration_info
    monkeypatch.setattr(appenv.Pyproject, "print_migration_info", lambda self: None)

    # Mock _uv_lock to prevent actual uv execution
    monkeypatch.setattr(appenv.AppEnv, "_uv_lock", lambda self, uv, diff=False: None)

    env = appenv.AppEnv(Path.cwd(), get_test_settings(Path.cwd()))
    env.migrate()

    captured = capsys.readouterr()
    assert "Adding [project] section to existing pyproject.toml" in captured.out
