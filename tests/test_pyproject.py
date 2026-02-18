"""Tests for pyproject.toml workflow."""

from pathlib import Path

import pytest

import appenv


def test_detect_project_type_pyproject(tmpdir, monkeypatch):
    """pyproject.toml is detected and has priority over requirements.txt."""
    monkeypatch.chdir(tmpdir)
    (Path(tmpdir) / "pyproject.toml").write_text("[project]\nname = 'test'\n")
    (Path(tmpdir) / "requirements.txt").write_text("requests\n")

    result = appenv.detect_project_type(Path(tmpdir))
    assert result == "pyproject"


def test_detect_project_type_requirements(tmpdir, monkeypatch):
    """requirements.txt is detected when no pyproject.toml."""
    monkeypatch.chdir(tmpdir)
    (Path(tmpdir) / "requirements.txt").write_text("requests\n")

    result = appenv.detect_project_type(Path(tmpdir))
    assert result == "requirements"


def test_detect_project_type_none(tmpdir, monkeypatch):
    """Returns None when neither file exists."""
    monkeypatch.chdir(tmpdir)
    result = appenv.detect_project_type(Path(tmpdir))
    assert result is None


def test_prepare_pyproject_creates_venv(tmpdir, monkeypatch):
    """_prepare_pyproject creates .venv and runs uv sync."""
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

    assert result == str(base / ".venv")
    # venv command should be called with path argument
    assert any("venv" in c for c in uv_calls), f"Expected venv call, got {uv_calls}"
    assert any("sync" in c for c in uv_calls), f"Expected sync call, got {uv_calls}"


def test_prepare_pyproject_cleanup_old_appenv(tmpdir, monkeypatch):
    """_prepare_pyproject removes old .appenv after successful sync."""
    monkeypatch.chdir(tmpdir)
    base = Path(tmpdir)

    # Create pyproject.toml and uv.lock (NO requirements.txt = migration)
    (base / "pyproject.toml").write_text(
        "[project]\nname = 'test'\ndependencies = []\n"
    )
    (base / "uv.lock").write_text("version = 1\n")

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

    # Old .appenv should be gone
    assert not (base / ".appenv").exists()


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
    monkeypatch.setattr(appenv, "find_minimal_python", lambda: None)
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
    """prepare() exits with error if no project files found."""
    monkeypatch.chdir(tmpdir)
    base = Path(tmpdir)

    env = appenv.AppEnv(base, Path.cwd())

    with pytest.raises(SystemExit) as err:
        env.prepare()

    assert err.value.code == 67
    captured = capsys.readouterr()
    assert "pyproject.toml" in captured.out or "requirements.txt" in captured.out


def test_init_pyproject_uses_python_preference_from_requirements(
    tmpdir, monkeypatch, capsys
):
    """init-pyproject migration reads python preference from requirements.txt."""
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
    env.init_pyproject()

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

    # Create broken .venv (directory without bin/python)
    venv = base / ".venv"
    venv.mkdir()
    (venv / "broken_marker.txt").write_text("broken")

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

    assert result == str(venv)
    # The broken marker should be gone (venv was recreated)
    assert not (venv / "broken_marker.txt").exists()
    # venv command should be called
    assert any("venv" in c for c in uv_calls), f"Expected venv call, got {uv_calls}"


def test_init_pyproject_editable_warnings(tmpdir, monkeypatch, capsys):
    """init_pyproject warns about editable installs during migration."""
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
    env.init_pyproject()

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


def test_ensure_best_python_for_pyproject_respects_upper_bound(
    tmpdir, monkeypatch, capsys
):
    """ensure_best_python_for_pyproject respects upper bound in requires-python."""
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
        appenv.ensure_best_python_for_pyproject(base)

    # Should have exited via our mock (code 0), not the error path (code 65)
    assert exc_info.value.code == 0

    # Verify Python 3.13 was chosen (newest that satisfies >=3.11,<3.14)
    # 3.16 should be skipped (>= 3.14 upper bound)
    assert len(execv_called) == 1
    assert "python3.13" in execv_called[0][0]


def test_init_pyproject_already_exists(tmpdir, monkeypatch, capsys):
    """init_pyproject returns early when pyproject.toml already exists."""
    monkeypatch.chdir(tmpdir)
    base = Path(tmpdir)

    # Create existing pyproject.toml
    (base / "pyproject.toml").write_text(
        '[project]\nname = "existing"\ndependencies = []\n'
    )

    env = appenv.AppEnv(base, Path.cwd())
    env.init_pyproject()

    # Check output mentions "already exists" message
    captured = capsys.readouterr()
    assert "already exists" in captured.out
    assert "Nothing to do" in captured.out


def test_init_pyproject_existing_symlinks(tmpdir, monkeypatch, capsys):
    """init_pyproject detects and preserves existing symlinks during migration."""
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
    env.init_pyproject()

    # Check output mentions existing symlink
    captured = capsys.readouterr()
    assert "existing symlink" in captured.out.lower()
    assert "myapp" in captured.out

    # Verify symlink still exists and points to appenv
    assert myapp_link.exists()
    assert myapp_link.is_symlink()
    assert myapp_link.resolve() == appenv_script.resolve()


def test_init_pyproject_empty_dependencies(tmpdir, monkeypatch, capsys):
    """init_pyproject handles requirements.txt with only comments (no dependencies)."""
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
    env.init_pyproject()

    # Check pyproject.toml was created with empty dependencies
    pyproject = (base / "pyproject.toml").read_text()
    assert "dependencies = []" in pyproject

    # Verify output mentions 0 dependencies found
    captured = capsys.readouterr()
    assert "0 dependency" in captured.out or "Found 0" in captured.out


def test_init_pyproject_fresh_start_interactive(tmpdir, monkeypatch, capsys):
    """init_pyproject fresh start flow with interactive inputs."""
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
    env.init_pyproject()

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


def test_init_pyproject_fresh_start_default_dependencies(tmpdir, monkeypatch, capsys):
    """init_pyproject fresh start uses command name as default dependency when empty."""
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
    env.init_pyproject()

    # Verify pyproject.toml was created with command name as dependency
    pyproject = (base / "pyproject.toml").read_text()
    assert 'name = "defaultapp"' in pyproject
    assert '"defaultapp"' in pyproject  # dependency defaults to command name
    assert 'requires-python = ">=3.8"' in pyproject  # default version


def test_init_pyproject_migration_interactive_project_name(tmpdir, monkeypatch, capsys):
    """init_pyproject migration asks for project name interactively."""
    monkeypatch.chdir(tmpdir)
    base = Path(tmpdir)

    # Create requirements.txt to trigger migration
    (base / "requirements.txt").write_text("requests>=2.0\n")

    # Input: custom project name
    inputs = iter(["custom-project"])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    env = appenv.AppEnv(base, Path.cwd())
    env.init_pyproject()

    # Verify pyproject.toml uses custom project name
    pyproject = (base / "pyproject.toml").read_text()
    assert 'name = "custom-project"' in pyproject
    assert '"requests>=2.0"' in pyproject

    captured = capsys.readouterr()
    assert "Migrating" in captured.out
