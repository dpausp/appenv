"""Tests for migrate command and editable install parsing."""

from pathlib import Path

import pytest

import appenv


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

    env = appenv.AppEnv(base, Path.cwd())
    env.migrate()

    # Check that pyproject.toml has the correct python version
    pyproject = (base / "pyproject.toml").read_text()
    assert 'requires-python = ">=3.12"' in pyproject

    # Check output mentions the preference
    captured = capsys.readouterr()
    assert "python preference" in captured.out
    assert "3.12" in captured.out


def test_migrate_editable_warnings(tmp_path, monkeypatch, capsys):
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

    env = appenv.AppEnv(base, Path.cwd())
    env.migrate()

    # Check output mentions editable installs warning
    captured = capsys.readouterr()
    assert "editable" in captured.out.lower()
    assert "-e /path/to/local/pkg" in captured.out

    # Check pyproject.toml was created without editable installs
    pyproject = (base / "pyproject.toml").read_text()
    assert "-e" not in pyproject
    assert "requests" in pyproject
    assert "click" in pyproject


def test_migrate_already_exists(tmp_path, monkeypatch, capsys):
    """migrate returns early when pyproject.toml already exists."""
    monkeypatch.chdir(tmp_path)
    base = tmp_path

    # Create existing pyproject.toml
    (base / "pyproject.toml").write_text(
        '[project]\nname = "existing"\ndependencies = []\n'
    )

    env = appenv.AppEnv(base, Path.cwd())
    env.migrate()

    # Check output mentions "already has [project]" message
    captured = capsys.readouterr()
    assert "already has [project]" in captured.out
    assert "Nothing to do" in captured.out


def test_migrate_merges_with_tool_only_pyproject(tmp_path, monkeypatch, capsys):
    """migrate adds [project] section to pyproject.toml with only tool configs."""
    monkeypatch.chdir(tmp_path)
    base = tmp_path

    # Create pyproject.toml with only tool configs (no [project] section)
    (base / "pyproject.toml").write_text(
        '[tool.ruff]\nline-length = 88\n\n[tool.pytest]\naddopts = ["-v"]\n'
    )

    # Create requirements.txt to trigger migration
    (base / "requirements.txt").write_text("requests>=2.0\n")

    env = appenv.AppEnv(base, Path.cwd())
    env.migrate()

    # Verify pyproject.toml has both tool configs and [project] section
    pyproject = (base / "pyproject.toml").read_text()
    assert "[tool.ruff]" in pyproject
    assert "[tool.pytest]" in pyproject
    assert "[project]" in pyproject
    assert 'name = "' in pyproject
    assert '"requests>=2.0"' in pyproject

    captured = capsys.readouterr()
    assert "Adding [project] section" in captured.out
    assert "Updated pyproject.toml" in captured.out


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

    env = appenv.AppEnv(base, Path.cwd())
    env.migrate()

    # Check output mentions existing symlink
    captured = capsys.readouterr()
    assert "existing symlink" in captured.out.lower()
    assert "myapp" in captured.out

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

    env = appenv.AppEnv(base, Path.cwd())
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

    env = appenv.AppEnv(base, Path.cwd())
    env.migrate()

    # Verify pyproject.toml uses directory name as project name
    pyproject = (base / "pyproject.toml").read_text()
    assert f'name = "{base.name}"' in pyproject
    assert '"requests>=2.0"' in pyproject

    captured = capsys.readouterr()
    assert "Migrating" in captured.out


def test_migrate_no_requirements_txt(workdir, monkeypatch, capsys):
    """Lines 888-890: migrate() returns early when requirements.txt not found."""
    base = Path(workdir)

    # No requirements.txt, no pyproject.toml
    env = appenv.AppEnv(base, Path.cwd())
    env.migrate()

    captured = capsys.readouterr()
    assert "No requirements.txt found" in captured.out
    assert "Use 'init' to create" in captured.out


# Tests for parse_editable_spec


@pytest.mark.parametrize(
    "spec,expected",
    [
        ("-e ./local/pkg", {"path": "./local/pkg", "extras": []}),
        ("-e ../sibling/pkg", {"path": "../sibling/pkg", "extras": []}),
        ("-e /absolute/path/pkg", {"path": "/absolute/path/pkg", "extras": []}),
        ("-e plainpath", {"path": "plainpath", "extras": []}),
        ("-e ./pkg[extra1]", {"path": "./pkg", "extras": ["extra1"]}),
        ("-e ./pkg[extra1,extra2]", {"path": "./pkg", "extras": ["extra1", "extra2"]}),
        (
            "-e ./pkg[ extra1 , extra2 ]",
            {"path": "./pkg", "extras": ["extra1", "extra2"]},
        ),
        ("requests", None),  # not an editable spec
        ("-e git+https://github.com/user/repo", None),  # git URL not supported
        ("-e package @ ./path", None),  # PEP 508 direct ref not supported
    ],
)
def test_parse_editable_spec(spec, expected):
    """parse_editable_spec handles various editable spec formats."""
    # Use direct attribute access - ty can't resolve __all__ for single-file modules
    parse_editable_spec = appenv.parse_editable_spec
    result = parse_editable_spec(spec)
    assert result == expected


# Tests for extract_package_name_from_path


def test_extract_package_name_from_pyproject(tmp_path):
    """extract_package_name_from_path reads name from pyproject.toml."""
    extract_package_name_from_path = appenv.extract_package_name_from_path
    base = tmp_path
    pkg_dir = base / "mypackage"
    pkg_dir.mkdir()

    (pkg_dir / "pyproject.toml").write_text(
        '[project]\nname = "my-cool-package"\nversion = "1.0.0"\n'
    )

    result = extract_package_name_from_path("mypackage", base)
    assert result == "my-cool-package"


def test_extract_package_name_from_setup_py(tmp_path):
    """extract_package_name_from_path reads name from setup.py."""
    extract_package_name_from_path = appenv.extract_package_name_from_path
    base = tmp_path
    pkg_dir = base / "legacy-pkg"
    pkg_dir.mkdir()

    (pkg_dir / "setup.py").write_text(
        'from setuptools import setup\nsetup(name="legacy-package", version="0.1.0")\n'
    )

    result = extract_package_name_from_path("legacy-pkg", base)
    assert result == "legacy-package"


def test_extract_package_name_from_path_relative(tmp_path):
    """extract_package_name_from_path handles relative paths."""
    extract_package_name_from_path = appenv.extract_package_name_from_path
    base = tmp_path
    pkg_dir = base / "packages" / "subpkg"
    pkg_dir.mkdir(parents=True)

    (pkg_dir / "pyproject.toml").write_text('[project]\nname = "sub-package"\n')

    result = extract_package_name_from_path("./packages/subpkg", base)
    assert result == "sub-package"


def test_extract_package_name_from_path_not_found(tmp_path):
    """extract_package_name_from_path returns None when no package metadata found."""
    extract_package_name_from_path = appenv.extract_package_name_from_path
    base = tmp_path
    empty_dir = base / "empty"
    empty_dir.mkdir()

    result = extract_package_name_from_path("empty", base)
    assert result is None


def test_extract_package_name_from_path_missing_dir(tmp_path):
    """extract_package_name_from_path returns None when directory doesn't exist."""
    extract_package_name_from_path = appenv.extract_package_name_from_path
    base = tmp_path

    result = extract_package_name_from_path("nonexistent", base)
    assert result is None


# Tests for init_pyproject with editable installs


def test_migrate_editable_with_valid_local_package(tmp_path, monkeypatch, capsys):
    """init_pyproject converts -e ./path to proper uv.sources entry."""
    monkeypatch.chdir(tmp_path)
    base = tmp_path

    # Create local package with pyproject.toml
    local_pkg = base / "local-lib"
    local_pkg.mkdir()
    (local_pkg / "pyproject.toml").write_text(
        '[project]\nname = "my-local-lib"\nversion = "0.1.0"\n'
    )

    # Create requirements.txt with editable install
    (base / "requirements.txt").write_text("-e ./local-lib\nrequests>=2.0\n")

    # Mock input to use defaults
    inputs = iter(["myproject"])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    env = appenv.AppEnv(base, Path.cwd())
    env.migrate()

    # Check pyproject.toml has both dependencies
    pyproject = (base / "pyproject.toml").read_text()
    assert '"my-local-lib"' in pyproject
    assert '"requests>=2.0"' in pyproject

    # Check [tool.uv.sources] was generated
    assert "[tool.uv.sources]" in pyproject
    assert 'my-local-lib = { path = "./local-lib", editable = true }' in pyproject

    # Check output mentions editable
    captured = capsys.readouterr()
    assert "editable" in captured.out.lower()
    assert "my-local-lib" in captured.out


def test_migrate_editable_with_setup_py(tmp_path, monkeypatch, capsys):
    """init_pyproject handles editable with setup.py package."""
    monkeypatch.chdir(tmp_path)
    base = tmp_path

    # Create local package with setup.py
    local_pkg = base / "legacy-lib"
    local_pkg.mkdir()
    (local_pkg / "setup.py").write_text(
        'from setuptools import setup\nsetup(name="legacy-lib")\n'
    )

    # Create requirements.txt with editable install
    (base / "requirements.txt").write_text("-e ./legacy-lib\n")

    inputs = iter(["myproject"])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    env = appenv.AppEnv(base, Path.cwd())
    env.migrate()

    pyproject = (base / "pyproject.toml").read_text()
    assert '"legacy-lib"' in pyproject
    assert "[tool.uv.sources]" in pyproject
    assert 'legacy-lib = { path = "./legacy-lib", editable = true }' in pyproject


def test_migrate_editable_only_dependencies(tmp_path, monkeypatch, capsys):
    """init_pyproject handles requirements.txt with ONLY editable installs."""
    monkeypatch.chdir(tmp_path)
    base = tmp_path

    # Create local package
    local_pkg = base / "only-pkg"
    local_pkg.mkdir()
    (local_pkg / "pyproject.toml").write_text(
        '[project]\nname = "only-pkg"\nversion = "1.0.0"\n'
    )

    # Create requirements.txt with ONLY editable (the bug case!)
    (base / "requirements.txt").write_text("-e ./only-pkg\n")

    inputs = iter(["myproject"])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    env = appenv.AppEnv(base, Path.cwd())
    env.migrate()

    pyproject = (base / "pyproject.toml").read_text()

    # Should have the editable as dependency
    assert '"only-pkg"' in pyproject
    assert "[tool.uv.sources]" in pyproject
    assert 'only-pkg = { path = "./only-pkg", editable = true }' in pyproject

    # Should NOT have empty dependencies
    assert "dependencies = []" not in pyproject


def test_migrate_multiple_editables(tmp_path, monkeypatch, capsys):
    """init_pyproject handles multiple editable installs."""
    monkeypatch.chdir(tmp_path)
    base = tmp_path

    # Create multiple local packages
    for name in ["pkg-a", "pkg-b", "pkg-c"]:
        pkg_dir = base / name
        pkg_dir.mkdir()
        (pkg_dir / "pyproject.toml").write_text(
            f'[project]\nname = "{name}"\nversion = "0.1.0"\n'
        )

    # Create requirements.txt with multiple editables
    (base / "requirements.txt").write_text(
        "-e ./pkg-a\n-e ./pkg-b\n-e ./pkg-c\nrequests\n"
    )

    inputs = iter(["myproject"])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    env = appenv.AppEnv(base, Path.cwd())
    env.migrate()

    pyproject = (base / "pyproject.toml").read_text()

    # All packages should be in dependencies
    assert '"pkg-a"' in pyproject
    assert '"pkg-b"' in pyproject
    assert '"pkg-c"' in pyproject
    assert '"requests"' in pyproject

    # All should have sources
    assert "[tool.uv.sources]" in pyproject
    assert "pkg-a" in pyproject
    assert "pkg-b" in pyproject
    assert "pkg-c" in pyproject


def test_migrate_editable_with_extras(tmp_path, monkeypatch, capsys):
    """init_pyproject handles editable with extras like -e ./pkg[extra]."""
    monkeypatch.chdir(tmp_path)
    base = tmp_path

    # Create local package
    local_pkg = base / "lib-with-extras"
    local_pkg.mkdir()
    (local_pkg / "pyproject.toml").write_text(
        '[project]\nname = "lib-with-extras"\nversion = "0.1.0"\n'
    )

    # Create requirements.txt with extras
    (base / "requirements.txt").write_text("-e ./lib-with-extras[dev,test]\n")

    inputs = iter(["myproject"])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    env = appenv.AppEnv(base, Path.cwd())
    env.migrate()

    pyproject = (base / "pyproject.toml").read_text()

    # Should have dependency with extras
    assert '"lib-with-extras[dev,test]"' in pyproject
    assert "[tool.uv.sources]" in pyproject


def test_migrate_editable_missing_package_warns(tmp_path, monkeypatch, capsys):
    """init_pyproject warns when editable path has no package metadata."""
    monkeypatch.chdir(tmp_path)
    base = tmp_path

    # Create directory without pyproject.toml or setup.py
    empty_dir = base / "empty-dir"
    empty_dir.mkdir()

    # Create requirements.txt with invalid editable
    (base / "requirements.txt").write_text("-e ./empty-dir\nrequests\n")

    inputs = iter(["myproject"])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    env = appenv.AppEnv(base, Path.cwd())
    env.migrate()

    # Check warning in output
    captured = capsys.readouterr()
    assert "skipped" in captured.out.lower()
    assert "empty-dir" in captured.out

    # pyproject.toml should still have requests
    pyproject = (base / "pyproject.toml").read_text()
    assert '"requests"' in pyproject
    assert "[tool.uv.sources]" not in pyproject


def test_migrate_editable_git_url_warns(tmp_path, monkeypatch, capsys):
    """init_pyproject warns for git URL editable (not supported)."""
    monkeypatch.chdir(tmp_path)
    base = tmp_path

    # Create requirements.txt with git URL
    (base / "requirements.txt").write_text(
        "-e git+https://github.com/user/repo.git\nrequests\n"
    )

    inputs = iter(["myproject"])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    env = appenv.AppEnv(base, Path.cwd())
    env.migrate()

    # Check warning
    captured = capsys.readouterr()
    assert "skipped" in captured.out.lower()
    assert "unsupported format" in captured.out.lower()

    # pyproject.toml should only have requests
    pyproject = (base / "pyproject.toml").read_text()
    assert '"requests"' in pyproject
    assert "[tool.uv.sources]" not in pyproject


def test_migrate_editable_relative_parent_path(tmp_path, monkeypatch, capsys):
    """init_pyproject handles -e ../sibling style paths."""
    base = tmp_path

    # Create sibling package
    sibling = base / "sibling-pkg"
    sibling.mkdir()
    (sibling / "pyproject.toml").write_text(
        '[project]\nname = "sibling-lib"\nversion = "1.0.0"\n'
    )

    # Create project subdirectory (where we run init)
    project_dir = base / "myproject"
    project_dir.mkdir()

    # Create requirements.txt INSIDE project_dir (not base)
    (project_dir / "requirements.txt").write_text("-e ../sibling-pkg\n")

    inputs = iter(["myproject"])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    # AppEnv uses original_cwd as target, so pass project_dir as original_cwd
    env = appenv.AppEnv(project_dir, project_dir)
    env.migrate()

    pyproject = (project_dir / "pyproject.toml").read_text()
    assert '"sibling-lib"' in pyproject
    assert "[tool.uv.sources]" in pyproject
    assert "../sibling-pkg" in pyproject


def test_migrate_editable_bare_path_gets_prefix(tmp_path, monkeypatch, capsys):
    """init_pyproject adds ./ prefix to bare path editables."""
    monkeypatch.chdir(tmp_path)
    base = tmp_path

    # Create local package
    local_pkg = base / "bare-pkg"
    local_pkg.mkdir()
    (local_pkg / "pyproject.toml").write_text(
        '[project]\nname = "bare-pkg"\nversion = "1.0.0"\n'
    )

    # Create requirements.txt with bare path (no ./)
    (base / "requirements.txt").write_text("-e bare-pkg\n")

    inputs = iter(["myproject"])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    env = appenv.AppEnv(base, Path.cwd())
    env.migrate()

    pyproject = (base / "pyproject.toml").read_text()
    assert '"bare-pkg"' in pyproject
    # Should have ./ prefix in source path
    assert 'path = "./bare-pkg"' in pyproject


def test_migrate_editable_mixed_valid_and_invalid(tmp_path, monkeypatch, capsys):
    """init_pyproject handles mix of valid and invalid editables."""
    monkeypatch.chdir(tmp_path)
    base = tmp_path

    # Create one valid package
    valid_pkg = base / "valid-pkg"
    valid_pkg.mkdir()
    (valid_pkg / "pyproject.toml").write_text(
        '[project]\nname = "valid-pkg"\nversion = "1.0.0"\n'
    )

    # Create one empty directory (invalid)
    empty_dir = base / "empty-dir"
    empty_dir.mkdir()

    # Create requirements.txt with mix
    (base / "requirements.txt").write_text("-e ./valid-pkg\n-e ./empty-dir\nrequests\n")

    inputs = iter(["myproject"])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    env = appenv.AppEnv(base, Path.cwd())
    env.migrate()

    pyproject = (base / "pyproject.toml").read_text()

    # Valid should be in pyproject
    assert '"valid-pkg"' in pyproject
    assert "[tool.uv.sources]" in pyproject

    # Check warning for invalid
    captured = capsys.readouterr()
    assert "skipped" in captured.out.lower()
    assert "empty-dir" in captured.out


def test_migrate_editable_warnings_updated(tmp_path, monkeypatch, capsys):
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

    env = appenv.AppEnv(base, Path.cwd())
    env.migrate()

    # Check output mentions editable installs warning
    captured = capsys.readouterr()
    assert "editable" in captured.out.lower()
    assert "skipped" in captured.out.lower()

    # Check pyproject.toml was created with only regular deps
    pyproject = (base / "pyproject.toml").read_text()
    assert "-e" not in pyproject
    assert "requests" in pyproject
    assert "click" in pyproject
    assert "[tool.uv.sources]" not in pyproject
