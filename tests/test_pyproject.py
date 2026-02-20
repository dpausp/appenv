"""Tests for pyproject.toml workflow."""

from pathlib import Path

import pytest

import appenv


def test_detect_project_type_pyproject(tmpdir, monkeypatch):
    """pyproject.toml is detected."""
    monkeypatch.chdir(tmpdir)
    (Path(tmpdir) / "pyproject.toml").write_text("[project]\nname = 'test'\n")

    result = appenv.detect_project_type(Path(tmpdir))
    assert result == "pyproject"


def test_detect_project_type_none(tmpdir, monkeypatch):
    """Returns None when no pyproject.toml exists."""
    monkeypatch.chdir(tmpdir)
    result = appenv.detect_project_type(Path(tmpdir))
    assert result is None


def test_prepare_pyproject_creates_venv(tmpdir, monkeypatch):
    """_prepare_pyproject creates .appenv/venv and runs uv sync."""
    monkeypatch.chdir(tmpdir)
    base = Path(tmpdir)

    # Create pyproject.toml and uv.lock
    (base / "pyproject.toml").write_text(
        "[project]\nname = 'test'\ndependencies = []\n"
    )
    (base / "uv.lock").write_text("version = 1\n")

    # Mock uv commands
    uv_calls = []
    monkeypatch.setattr(appenv, "ensure_uv", lambda base: None)
    monkeypatch.setattr(appenv, "ensure_uv_version", lambda: None)
    monkeypatch.setattr(
        appenv,
        "uv_cmd",
        lambda args, **kwargs: uv_calls.append(args),
    )

    env = appenv.AppEnv(base, Path.cwd())
    result = env._prepare_pyproject()

    # venv is now in .appenv/venv
    assert result == str(base / ".appenv" / "venv")
    # venv command should be called with path argument
    assert any("venv" in c for c in uv_calls), f"Expected venv call, got {uv_calls}"
    assert any("sync" in c for c in uv_calls), f"Expected sync call, got {uv_calls}"
    # Symlink should be created
    assert (base / ".venv").is_symlink()


def test_prepare_pyproject_cleanup_old_appenv(tmpdir, monkeypatch):
    """_prepare_pyproject removes old hash-based venvs but keeps .appenv."""
    monkeypatch.chdir(tmpdir)
    base = Path(tmpdir)

    # Create pyproject.toml and uv.lock (NO requirements.txt = migration)
    (base / "pyproject.toml").write_text(
        "[project]\nname = 'test'\ndependencies = []\n"
    )
    (base / "uv.lock").write_text("version = 1\n")

    # Create old .appenv directory with hash-based venv
    old_appenv = base / ".appenv" / "oldhash"
    old_appenv.mkdir(parents=True)
    (old_appenv / "marker.txt").write_text("old")

    # Mock uv commands
    monkeypatch.setattr(appenv, "ensure_uv", lambda base: None)
    monkeypatch.setattr(appenv, "ensure_uv_version", lambda: None)
    monkeypatch.setattr(appenv, "uv_cmd", lambda args, **kwargs: None)

    env = appenv.AppEnv(base, Path.cwd())
    env._prepare_pyproject()

    # Old hash-based venv should be gone
    assert not (base / ".appenv" / "oldhash").exists()
    # .appenv should still exist (even though mock didn't create venv)
    assert (base / ".appenv").exists()


def test_prepare_pyproject_keeps_appenv_if_requirements_exists(tmpdir, monkeypatch):
    """_prepare_pyproject keeps .appenv if requirements.txt still exists."""
    monkeypatch.chdir(tmpdir)
    base = Path(tmpdir)

    # Create BOTH pyproject.toml and requirements.txt
    (base / "pyproject.toml").write_text(
        "[project]\nname = 'test'\ndependencies = []\n"
    )
    (base / "uv.lock").write_text("version = 1\n")
    (base / "requirements.txt").write_text("requests\n")

    # Create old .appenv directory
    old_appenv = base / ".appenv" / "oldhash"
    old_appenv.mkdir(parents=True)
    (old_appenv / "marker.txt").write_text("old")

    # Mock uv commands
    monkeypatch.setattr(appenv, "ensure_uv", lambda base: None)
    monkeypatch.setattr(appenv, "ensure_uv_version", lambda: None)
    monkeypatch.setattr(appenv, "uv_cmd", lambda args, **kwargs: None)

    env = appenv.AppEnv(base, Path.cwd())
    env._prepare_pyproject()

    # Old .appenv should still exist (requirements.txt present)
    assert (base / ".appenv").exists()


def test_update_lockfile_pyproject_calls_uv_lock(tmpdir, monkeypatch):
    """_update_lockfile_pyproject calls uv lock and pip compile for fallback."""
    monkeypatch.chdir(tmpdir)
    base = Path(tmpdir)

    (base / "pyproject.toml").write_text(
        "[project]\nname = 'test'\ndependencies = []\n"
    )

    uv_calls = []
    monkeypatch.setattr(appenv, "ensure_uv", lambda base: None)
    monkeypatch.setattr(appenv, "ensure_uv_version", lambda: None)
    monkeypatch.setattr(
        appenv,
        "uv_cmd",
        lambda args, **kwargs: uv_calls.append(args),
    )

    env = appenv.AppEnv(base, Path.cwd())
    env._update_lockfile_pyproject(None)

    # Should call uv lock
    assert any("lock" in str(c) for c in uv_calls)
    # Should also call pip compile for fallback requirements.lock
    assert any("compile" in str(c) for c in uv_calls)


def test_prepare_exits_without_project_files(tmpdir, monkeypatch, capsys):
    """prepare() exits with error if no pyproject.toml found."""
    monkeypatch.chdir(tmpdir)
    base = Path(tmpdir)

    env = appenv.AppEnv(base, Path.cwd())

    with pytest.raises(SystemExit) as err:
        env.prepare()

    assert err.value.code == 67
    captured = capsys.readouterr()
    assert "pyproject.toml" in captured.out


def test_init_pyproject_uses_python_preference_from_requirements(
    tmpdir, monkeypatch, capsys
):
    """migrate reads python preference from requirements.txt."""
    monkeypatch.chdir(tmpdir)
    base = Path(tmpdir)

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


# Tier 2 tests


def test_prepare_pyproject_missing_uv_lock(tmpdir, monkeypatch, capsys):
    """_prepare_pyproject exits with code 67 when uv.lock is missing."""
    monkeypatch.chdir(tmpdir)
    base = Path(tmpdir)

    # Create pyproject.toml but NO uv.lock
    (base / "pyproject.toml").write_text(
        "[project]\nname = 'test'\ndependencies = []\n"
    )

    env = appenv.AppEnv(base, Path.cwd())

    with pytest.raises(SystemExit) as err:
        env._prepare_pyproject()

    assert err.value.code == 67
    captured = capsys.readouterr()
    assert "uv.lock" in captured.out


def test_prepare_pyproject_corrupted_venv(tmpdir, monkeypatch):
    """_prepare_pyproject removes corrupted venv and recreates it."""
    monkeypatch.chdir(tmpdir)
    base = Path(tmpdir)

    # Create pyproject.toml and uv.lock
    (base / "pyproject.toml").write_text(
        "[project]\nname = 'test'\ndependencies = []\n"
    )
    (base / "uv.lock").write_text("version = 1\n")

    # Create broken .appenv/venv (directory without bin/python)
    venv_real = base / ".appenv" / "venv"
    venv_real.mkdir(parents=True)
    (venv_real / "broken_marker.txt").write_text("broken")

    # Mock uv commands
    uv_calls = []
    monkeypatch.setattr(appenv, "ensure_uv", lambda base: None)
    monkeypatch.setattr(appenv, "ensure_uv_version", lambda: None)
    monkeypatch.setattr(
        appenv,
        "uv_cmd",
        lambda args, **kwargs: uv_calls.append(args),
    )

    env = appenv.AppEnv(base, Path.cwd())
    result = env._prepare_pyproject()

    # venv is now in .appenv/venv
    assert result == str(venv_real)
    # The broken marker should be gone (venv was recreated)
    assert not (venv_real / "broken_marker.txt").exists()
    # venv command should be called
    assert any("venv" in c for c in uv_calls), f"Expected venv call, got {uv_calls}"


def test_init_pyproject_editable_warnings(tmpdir, monkeypatch, capsys):
    """migrate warns about editable installs during migration."""
    monkeypatch.chdir(tmpdir)
    base = Path(tmpdir)

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


# Tier 3 tests


def test_ensure_best_python_respects_upper_bound(tmpdir, monkeypatch, capsys):
    """ensure_best_python respects upper bound in requires-python."""
    monkeypatch.chdir(tmpdir)
    base = Path(tmpdir)

    # Ensure APPENV_BEST_PYTHON is not set (causes early return if set)
    monkeypatch.delenv("APPENV_BEST_PYTHON", raising=False)

    # Create pyproject.toml with upper bound
    (base / "pyproject.toml").write_text(
        '[project]\nname = "test"\nrequires-python = ">=3.11,<3.14"\n'
    )

    # Mock find_available_pythons to return versions including ones exceeding bound
    monkeypatch.setattr(
        appenv,
        "find_available_pythons",
        lambda: [
            ("3.16", "/usr/bin/python3.16"),
            ("3.13", "/usr/bin/python3.13"),
            ("3.12", "/usr/bin/python3.12"),
            ("3.11", "/usr/bin/python3.11"),
        ],
    )

    # Mock os.execv and subprocess.check_call to prevent actual re-exec
    execv_called = []

    def mock_execv(path, argv):
        execv_called.append((path, argv))
        # In real code, execv never returns - simulate this by raising SystemExit
        raise SystemExit(0)

    monkeypatch.setattr("os.execv", mock_execv)
    monkeypatch.setattr(
        "subprocess.check_call", lambda cmd, **kwargs: None
    )  # Python works

    # Mock sys.executable to be different from available pythons
    monkeypatch.setattr("sys.executable", "/different/path/python")

    # Call the function - it should call execv and then SystemExit(0)
    with pytest.raises(SystemExit) as exc_info:
        appenv.ensure_best_python(base)

    # Should have exited via our mock (code 0), not the error path (code 65)
    assert exc_info.value.code == 0

    # Verify Python 3.13 was chosen (newest that satisfies >=3.11,<3.14)
    # 3.16 should be skipped (>= 3.14 upper bound)
    assert len(execv_called) == 1
    assert "python3.13" in execv_called[0][0]


def test_migrate_already_exists(tmpdir, monkeypatch, capsys):
    """migrate returns early when pyproject.toml already exists."""
    monkeypatch.chdir(tmpdir)
    base = Path(tmpdir)

    # Create existing pyproject.toml
    (base / "pyproject.toml").write_text(
        '[project]\nname = "existing"\ndependencies = []\n'
    )

    env = appenv.AppEnv(base, Path.cwd())
    env.migrate()

    # Check output mentions "already exists" message
    captured = capsys.readouterr()
    assert "already exists" in captured.out
    assert "Nothing to do" in captured.out


def test_migrate_existing_symlinks(tmpdir, monkeypatch, capsys):
    """migrate detects and preserves existing symlinks during migration."""
    monkeypatch.chdir(tmpdir)
    base = Path(tmpdir)

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


def test_migrate_empty_dependencies(tmpdir, monkeypatch, capsys):
    """migrate handles requirements.txt with only comments (no dependencies)."""
    monkeypatch.chdir(tmpdir)
    base = Path(tmpdir)

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


def test_init_fresh_start_interactive(tmpdir, monkeypatch, capsys):
    """init fresh start flow with interactive inputs."""
    monkeypatch.chdir(tmpdir)
    base = Path(tmpdir)

    # No requirements.txt - triggers fresh start flow
    # Inputs: command name, description, dependencies (2), empty, python version
    inputs = iter(
        [
            "myapp",  # command name
            "My test app",  # description
            "requests",  # dependency 1
            "click",  # dependency 2
            "",  # empty line to finish dependencies
            "3.10",  # python version
        ]
    )
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    env = appenv.AppEnv(base, Path.cwd())
    env.init()

    # Verify pyproject.toml was created
    pyproject = (base / "pyproject.toml").read_text()
    assert 'name = "myapp"' in pyproject
    assert 'description = "My test app"' in pyproject
    assert '"requests"' in pyproject
    assert '"click"' in pyproject
    assert 'requires-python = ">=3.10"' in pyproject

    # Verify appenv script and symlink were created
    assert (base / "appenv").exists()
    assert (base / "myapp").exists()
    assert (base / "myapp").is_symlink()


def test_init_fresh_start_default_dependencies(tmpdir, monkeypatch, capsys):
    """init fresh start uses command name as default dependency when empty."""
    monkeypatch.chdir(tmpdir)
    base = Path(tmpdir)

    # No requirements.txt - triggers fresh start flow
    # Immediately empty line for dependencies - should default to command name
    inputs = iter(
        [
            "defaultapp",  # command name
            "",  # empty description
            "",  # empty line immediately - no dependencies entered
            "",  # python version (use default 3.8)
        ]
    )
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    env = appenv.AppEnv(base, Path.cwd())
    env.init()

    # Verify pyproject.toml was created with command name as dependency
    pyproject = (base / "pyproject.toml").read_text()
    assert 'name = "defaultapp"' in pyproject
    assert '"defaultapp"' in pyproject  # dependency defaults to command name
    assert 'requires-python = ">=3.8"' in pyproject  # default version


def test_migrate_interactive_project_name(tmpdir, monkeypatch, capsys):
    """migrate asks for project name interactively."""
    monkeypatch.chdir(tmpdir)
    base = Path(tmpdir)

    # Create requirements.txt to trigger migration
    (base / "requirements.txt").write_text("requests>=2.0\n")

    # Input: custom project name
    inputs = iter(["custom-project"])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    env = appenv.AppEnv(base, Path.cwd())
    env.migrate()

    # Verify pyproject.toml uses custom project name
    pyproject = (base / "pyproject.toml").read_text()
    assert 'name = "custom-project"' in pyproject
    assert '"requests>=2.0"' in pyproject

    captured = capsys.readouterr()
    assert "Migrating" in captured.out


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


def test_extract_package_name_from_pyproject(tmpdir):
    """extract_package_name_from_path reads name from pyproject.toml."""
    extract_package_name_from_path = appenv.extract_package_name_from_path
    base = Path(tmpdir)
    pkg_dir = base / "mypackage"
    pkg_dir.mkdir()

    (pkg_dir / "pyproject.toml").write_text(
        '[project]\nname = "my-cool-package"\nversion = "1.0.0"\n'
    )

    result = extract_package_name_from_path("mypackage", base)
    assert result == "my-cool-package"


def test_extract_package_name_from_setup_py(tmpdir):
    """extract_package_name_from_path reads name from setup.py."""
    extract_package_name_from_path = appenv.extract_package_name_from_path
    base = Path(tmpdir)
    pkg_dir = base / "legacy-pkg"
    pkg_dir.mkdir()

    (pkg_dir / "setup.py").write_text(
        'from setuptools import setup\nsetup(name="legacy-package", version="0.1.0")\n'
    )

    result = extract_package_name_from_path("legacy-pkg", base)
    assert result == "legacy-package"


def test_extract_package_name_from_path_relative(tmpdir):
    """extract_package_name_from_path handles relative paths."""
    extract_package_name_from_path = appenv.extract_package_name_from_path
    base = Path(tmpdir)
    pkg_dir = base / "packages" / "subpkg"
    pkg_dir.mkdir(parents=True)

    (pkg_dir / "pyproject.toml").write_text('[project]\nname = "sub-package"\n')

    result = extract_package_name_from_path("./packages/subpkg", base)
    assert result == "sub-package"


def test_extract_package_name_from_path_not_found(tmpdir):
    """extract_package_name_from_path returns None when no package metadata found."""
    extract_package_name_from_path = appenv.extract_package_name_from_path
    base = Path(tmpdir)
    empty_dir = base / "empty"
    empty_dir.mkdir()

    result = extract_package_name_from_path("empty", base)
    assert result is None


def test_extract_package_name_from_path_missing_dir(tmpdir):
    """extract_package_name_from_path returns None when directory doesn't exist."""
    extract_package_name_from_path = appenv.extract_package_name_from_path
    base = Path(tmpdir)

    result = extract_package_name_from_path("nonexistent", base)
    assert result is None


# Tests for init_pyproject with editable installs


def test_init_pyproject_editable_with_valid_local_package(tmpdir, monkeypatch, capsys):
    """init_pyproject converts -e ./path to proper uv.sources entry."""
    monkeypatch.chdir(tmpdir)
    base = Path(tmpdir)

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


def test_init_pyproject_editable_with_setup_py(tmpdir, monkeypatch, capsys):
    """init_pyproject handles editable with setup.py package."""
    monkeypatch.chdir(tmpdir)
    base = Path(tmpdir)

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


def test_init_pyproject_editable_only_dependencies(tmpdir, monkeypatch, capsys):
    """init_pyproject handles requirements.txt with ONLY editable installs."""
    monkeypatch.chdir(tmpdir)
    base = Path(tmpdir)

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


def test_init_pyproject_multiple_editables(tmpdir, monkeypatch, capsys):
    """init_pyproject handles multiple editable installs."""
    monkeypatch.chdir(tmpdir)
    base = Path(tmpdir)

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


def test_init_pyproject_editable_with_extras(tmpdir, monkeypatch, capsys):
    """init_pyproject handles editable with extras like -e ./pkg[extra]."""
    monkeypatch.chdir(tmpdir)
    base = Path(tmpdir)

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


def test_init_pyproject_editable_missing_package_warns(tmpdir, monkeypatch, capsys):
    """init_pyproject warns when editable path has no package metadata."""
    monkeypatch.chdir(tmpdir)
    base = Path(tmpdir)

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


def test_init_pyproject_editable_git_url_warns(tmpdir, monkeypatch, capsys):
    """init_pyproject warns for git URL editable (not supported)."""
    monkeypatch.chdir(tmpdir)
    base = Path(tmpdir)

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


def test_init_pyproject_editable_relative_parent_path(tmpdir, monkeypatch, capsys):
    """init_pyproject handles -e ../sibling style paths."""
    base = Path(tmpdir)

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


def test_init_pyproject_editable_bare_path_gets_prefix(tmpdir, monkeypatch, capsys):
    """init_pyproject adds ./ prefix to bare path editables."""
    monkeypatch.chdir(tmpdir)
    base = Path(tmpdir)

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


def test_init_pyproject_editable_mixed_valid_and_invalid(tmpdir, monkeypatch, capsys):
    """init_pyproject handles mix of valid and invalid editables."""
    monkeypatch.chdir(tmpdir)
    base = Path(tmpdir)

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


# Update the old test to match new behavior


def test_init_pyproject_editable_warnings_updated(tmpdir, monkeypatch, capsys):
    """init_pyproject warns about unsupported editable formats (git URLs, etc)."""
    monkeypatch.chdir(tmpdir)
    base = Path(tmpdir)

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


# Tests for .appenv/venv location and symlink behavior


def test_prepare_pyproject_sets_uv_project_environment(tmpdir, monkeypatch):
    """_prepare_pyproject sets UV_PROJECT_ENVIRONMENT to .appenv/venv."""
    monkeypatch.chdir(tmpdir)
    base = Path(tmpdir)

    (base / "pyproject.toml").write_text(
        "[project]\nname = 'test'\ndependencies = []\n"
    )
    (base / "uv.lock").write_text("version = 1\n")

    monkeypatch.setattr(appenv, "ensure_uv", lambda base: None)
    monkeypatch.setattr(appenv, "ensure_uv_version", lambda: None)
    monkeypatch.setattr(appenv, "uv_cmd", lambda args, **kwargs: None)

    env = appenv.AppEnv(base, Path.cwd())
    env._prepare_pyproject()

    import os

    assert os.environ.get("UV_PROJECT_ENVIRONMENT") == str(base / ".appenv" / "venv")


def test_prepare_pyproject_creates_symlink(tmpdir, monkeypatch):
    """_prepare_pyproject creates .venv symlink to .appenv/venv."""
    monkeypatch.chdir(tmpdir)
    base = Path(tmpdir)

    (base / "pyproject.toml").write_text(
        "[project]\nname = 'test'\ndependencies = []\n"
    )
    (base / "uv.lock").write_text("version = 1\n")

    monkeypatch.setattr(appenv, "ensure_uv", lambda base: None)
    monkeypatch.setattr(appenv, "ensure_uv_version", lambda: None)
    monkeypatch.setattr(appenv, "uv_cmd", lambda args, **kwargs: None)

    env = appenv.AppEnv(base, Path.cwd())
    env._prepare_pyproject()

    venv_link = base / ".venv"
    assert venv_link.is_symlink()
    # Symlink should point to .appenv/venv (relative path)
    assert venv_link.resolve() == (base / ".appenv" / "venv").resolve()


def test_prepare_pyproject_updates_broken_symlink(tmpdir, monkeypatch):
    """_prepare_pyproject updates broken .venv symlink to point to .appenv/venv."""
    monkeypatch.chdir(tmpdir)
    base = Path(tmpdir)

    (base / "pyproject.toml").write_text(
        "[project]\nname = 'test'\ndependencies = []\n"
    )
    (base / "uv.lock").write_text("version = 1\n")

    # Create broken symlink (pointing to non-existent path)
    venv_link = base / ".venv"
    venv_link.symlink_to("/nonexistent/path")

    monkeypatch.setattr(appenv, "ensure_uv", lambda base: None)
    monkeypatch.setattr(appenv, "ensure_uv_version", lambda: None)
    monkeypatch.setattr(appenv, "uv_cmd", lambda args, **kwargs: None)

    env = appenv.AppEnv(base, Path.cwd())
    env._prepare_pyproject()

    # Symlink should now point to correct location
    assert venv_link.is_symlink()
    import os

    assert os.readlink(venv_link) == ".appenv/venv"


def test_prepare_pyproject_keeps_real_venv_directory(tmpdir, monkeypatch):
    """_prepare_pyproject does not touch .venv if it's a real directory."""
    monkeypatch.chdir(tmpdir)
    base = Path(tmpdir)

    (base / "pyproject.toml").write_text(
        "[project]\nname = 'test'\ndependencies = []\n"
    )
    (base / "uv.lock").write_text("version = 1\n")

    # Create real .venv directory (not a symlink)
    venv_dir = base / ".venv"
    venv_dir.mkdir()
    (venv_dir / "marker.txt").write_text("real directory")

    monkeypatch.setattr(appenv, "ensure_uv", lambda base: None)
    monkeypatch.setattr(appenv, "ensure_uv_version", lambda: None)
    monkeypatch.setattr(appenv, "uv_cmd", lambda args, **kwargs: None)

    env = appenv.AppEnv(base, Path.cwd())
    env._prepare_pyproject()

    # .venv should still be a real directory, not a symlink
    assert venv_dir.is_dir()
    assert not venv_dir.is_symlink()
    assert (venv_dir / "marker.txt").exists()


def test_reset_removes_symlink_and_venv(tmpdir, monkeypatch, capsys):
    """reset removes .venv symlink and .appenv/venv."""
    monkeypatch.chdir(tmpdir)
    base = Path(tmpdir)

    # Create .appenv/venv
    venv_real = base / ".appenv" / "venv"
    venv_real.mkdir(parents=True)
    (venv_real / "bin").mkdir()
    (venv_real / "bin" / "python").write_text("#!/bin/bash")

    # Create symlink
    venv_link = base / ".venv"
    venv_link.symlink_to(".appenv/venv")

    env = appenv.AppEnv(base, Path.cwd())
    env.reset()

    # Symlink should be removed
    assert not venv_link.exists()
    # venv should be removed
    assert not venv_real.exists()


def test_reset_keeps_uv_binary(tmpdir, monkeypatch, capsys):
    """reset keeps .appenv/.uv directory (uv binary cache)."""
    monkeypatch.chdir(tmpdir)
    base = Path(tmpdir)

    # Create .appenv/.uv
    uv_dir = base / ".appenv" / ".uv"
    uv_dir.mkdir(parents=True)
    (uv_dir / "bin").mkdir()
    (uv_dir / "bin" / "uv").write_text("#!/bin/bash")

    env = appenv.AppEnv(base, Path.cwd())
    env.reset()

    # .appenv/.uv should still exist
    assert uv_dir.exists()
    assert (uv_dir / "bin" / "uv").exists()


def test_prepare_pyproject_keeps_dot_uv_dir(tmpdir, monkeypatch):
    """_prepare_pyproject does not delete .appenv/.uv during cleanup."""
    monkeypatch.chdir(tmpdir)
    base = Path(tmpdir)

    (base / "pyproject.toml").write_text(
        "[project]\nname = 'test'\ndependencies = []\n"
    )
    (base / "uv.lock").write_text("version = 1\n")

    # Create old hash-based venv AND .uv
    old_venv = base / ".appenv" / "oldhash"
    old_venv.mkdir(parents=True)
    (old_venv / "marker.txt").write_text("old")

    uv_dir = base / ".appenv" / ".uv"
    uv_dir.mkdir(parents=True)
    (uv_dir / "uv_binary").write_text("uv")

    monkeypatch.setattr(appenv, "ensure_uv", lambda base: None)
    monkeypatch.setattr(appenv, "ensure_uv_version", lambda: None)
    monkeypatch.setattr(appenv, "uv_cmd", lambda args, **kwargs: None)

    env = appenv.AppEnv(base, Path.cwd())
    env._prepare_pyproject()

    # .uv should be kept
    assert uv_dir.exists()
    assert (uv_dir / "uv_binary").exists()
    # old hash venv should be removed
    assert not old_venv.exists()
