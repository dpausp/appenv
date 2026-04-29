"""Spec validation tests for venv-lifecycle-fixes.

These tests reproduce the bugs described in the spec decisions.
They are marked xfail until Phase 2 implementation lands.

Spec: .agents/impl_specs/venv-lifecycle-fixes.md
"""

import logging
import os
from pathlib import Path

import pytest

import appenv
from appenv import UvVersion

# ============================================================================
# 1. logging-duplicate-handler-fix
# ============================================================================


def test_setup_logging_no_duplicate_handlers(tmp_path):
    """Calling setup_logging() twice results in exactly 2 handlers, not 4.

    The bug: setup_logging() appends handlers without clearing existing ones.
    When meta() calls setup_logging("appenv", ...) and then run() calls
    setup_logging("python", ...), the module-level logger gets 4 handlers
    (2 file + 2 console when verbose) instead of 2 (1 file + 1 console).
    """
    log = appenv.log
    # Clean slate
    for handler in log.handlers[:]:
        handler.close()
    log.handlers.clear()

    log_dir = tmp_path / "logs"
    log_dir.mkdir(parents=True)

    # First call (as meta() would do)
    appenv.setup_logging("appenv", log_dir, verbose=True)
    assert len(log.handlers) == 2  # 1 file + 1 console

    # Second call (as run() would do for python subcommand)
    appenv.setup_logging("python", log_dir, verbose=True)

    # After the fix, should still be 2 (cleared and re-added), not 4
    assert len(log.handlers) == 2

    handler_types = [type(h).__name__ for h in log.handlers]
    assert "TimedRotatingFileHandler" in handler_types
    assert "StreamHandler" in handler_types

    # Cleanup
    for handler in log.handlers[:]:
        handler.close()
    log.handlers.clear()


def test_setup_logging_non_verbose_no_duplicate(tmp_path):
    """Non-verbose double call results in exactly 1 handler, not 2."""
    log = appenv.log
    for handler in log.handlers[:]:
        handler.close()
    log.handlers.clear()

    log_dir = tmp_path / "logs"
    log_dir.mkdir(parents=True)

    appenv.setup_logging("cmd1", log_dir, verbose=False)
    assert len(log.handlers) == 1

    appenv.setup_logging("cmd2", log_dir, verbose=False)
    assert len(log.handlers) == 1

    for handler in log.handlers[:]:
        handler.close()
    log.handlers.clear()


# ============================================================================
# 2. stale-venv-recreate
# ============================================================================


def test_prepare_venv_recreates_on_version_mismatch(
    tmp_path, monkeypatch, test_settings
):
    """_prepare_venv recreates venv when Python version is
    outside constraints.


    The bug: _prepare_venv only checks venv directory existence and Nix GC,
    never validates the venv's Python version against requires-python.
    """
    monkeypatch.chdir(tmp_path)
    base = tmp_path

    # pyproject.toml requires Python >=3.13
    (base / "pyproject.toml").write_text(
        '[project]\nname = "test"\nrequires-python = ">=3.13"\n'
    )
    (base / "uv.lock").write_text("version = 1\n")

    settings = test_settings(Path.cwd())
    env = appenv.AppEnv(Path.cwd(), settings)

    # Create existing venv with Python 3.10 (too old for >=3.13)
    venv = env.appenv_dir / "venv"
    venv.mkdir(parents=True)
    (venv / "bin").mkdir()
    python_bin = venv / "bin" / "python"
    python_bin.write_text("#!/bin/sh\necho Python 3.10.0\n")
    python_bin.chmod(0o755)

    # Track whether venv was recreated
    venv_create_calls = []

    class MockUvBin:
        def __init__(self):
            self.bin = Path("/usr/bin/uv")
            self._version = UvVersion(0, 5, 0)

        @property
        def version(self):
            return self._version

        def cmd(self, args, verbose=False, **kwargs):
            if "venv" in args:
                venv_create_calls.append(list(args))
                # Recreate venv with valid Python
                if not venv.exists():
                    venv.mkdir(parents=True, exist_ok=True)
                    (venv / "bin").mkdir(exist_ok=True)
                    py = venv / "bin" / "python"
                    py.write_text("#!/bin/sh\necho Python 3.13.0\n")
                    py.chmod(0o755)
            return ""

    mock_uv = MockUvBin()
    monkeypatch.setattr(appenv, "ensure_uv", lambda base: mock_uv)
    # Mock cmd to return version strings for the venv Python
    monkeypatch.setattr(
        appenv,
        "cmd",
        lambda c, **kwargs: (
            b"Python 3.10.0" if str(python_bin) in str(c) else b"Python 3.13.0"
        ),
    )

    env._prepare_venv(dev_mode=False)

    # The fix should have detected version mismatch, removed old venv,
    # and triggered venv recreation
    assert len(venv_create_calls) >= 1, (
        "venv should be recreated when Python version is stale"
    )

    # Cleanup
    os.environ.pop("UV_PROJECT_ENVIRONMENT", None)


def test_prepare_venv_checks_version_compatibility(
    tmp_path, monkeypatch, test_settings
):
    """_prepare_venv calls version_satisfies_constraints to validate venv Python.

    The fix adds a version compatibility check using the existing
    version_satisfies_constraints() function against pyproject.toml's
    requires-python. This test verifies the function is called during _prepare_venv.
    """
    monkeypatch.chdir(tmp_path)
    base = tmp_path

    (base / "pyproject.toml").write_text(
        '[project]\nname = "test"\nrequires-python = ">=3.12"\n'
    )
    (base / "uv.lock").write_text("version = 1\n")

    settings = test_settings(Path.cwd())
    env = appenv.AppEnv(Path.cwd(), settings)

    # Create existing venv with Python 3.12 (satisfies >=3.12)
    venv = env.appenv_dir / "venv"
    venv.mkdir(parents=True)
    (venv / "bin").mkdir()
    python_bin = venv / "bin" / "python"
    python_bin.write_text("#!/bin/sh\necho Python 3.12.0\n")
    python_bin.chmod(0o755)

    venv_create_calls = []

    class MockUvBin:
        def __init__(self):
            self.bin = Path("/usr/bin/uv")
            self._version = UvVersion(0, 5, 0)

        @property
        def version(self):
            return self._version

        def cmd(self, args, verbose=False, **kwargs):
            if "venv" in args:
                venv_create_calls.append(list(args))
            return ""

    mock_uv = MockUvBin()
    monkeypatch.setattr(appenv, "ensure_uv", lambda base: mock_uv)
    monkeypatch.setattr(appenv, "cmd", lambda c, **kwargs: b"Python 3.12.0")

    # Track calls to version_satisfies_constraints
    vsc_calls = []
    original_vsc = appenv.version_satisfies_constraints

    def tracking_vsc(version, min_version, max_version=None):
        vsc_calls.append((version, min_version, max_version))
        return original_vsc(version, min_version, max_version)

    monkeypatch.setattr(appenv, "version_satisfies_constraints", tracking_vsc)

    env._prepare_venv(dev_mode=False)

    # The fix should call version_satisfies_constraints during _prepare_venv
    # to check the venv's Python version against pyproject.toml constraints
    assert len(vsc_calls) >= 1, (
        "_prepare_venv should call version_satisfies_constraints to check "
        "venv Python version compatibility"
    )
    # venv should NOT be recreated — version is compatible
    assert len(venv_create_calls) == 0, (
        "venv should NOT be recreated when Python version is compatible"
    )

    os.environ.pop("UV_PROJECT_ENVIRONMENT", None)


# ============================================================================
# 3. ensure-best-python-logging
# ============================================================================


def test_ensure_best_python_logs_constraints(tmp_path, monkeypatch, caplog):
    """ensure_best_python emits log.debug with parsed requires-python constraints."""
    monkeypatch.delenv("APPENV_BEST_PYTHON", raising=False)
    monkeypatch.setattr("os.chdir", lambda p: None)

    base = tmp_path
    (base / "pyproject.toml").write_text(
        '[project]\nname = "test"\nrequires-python = ">=3.11,<3.14"\n'
    )

    monkeypatch.setattr(
        appenv,
        "find_available_pythons",
        lambda: [
            ("3.13", "/usr/bin/python3.13"),
            ("3.12", "/usr/bin/python3.12"),
        ],
    )

    def mock_resolve(self):
        return Path("/usr/bin/python3.12")

    monkeypatch.setattr("pathlib.Path.resolve", mock_resolve)
    monkeypatch.setattr("sys.executable", "/usr/bin/python3.12")

    with caplog.at_level(logging.DEBUG, logger="appenv"):
        appenv.ensure_best_python(base)

    log_messages = caplog.text
    # Should log the parsed constraints
    assert "3.11" in log_messages or "constraint" in log_messages.lower(), (
        "ensure_best_python should log parsed requires-python constraints"
    )


def test_ensure_best_python_logs_candidates(tmp_path, monkeypatch, caplog):
    """ensure_best_python emits log.debug with candidate evaluation reasoning."""
    monkeypatch.delenv("APPENV_BEST_PYTHON", raising=False)
    monkeypatch.setattr("os.chdir", lambda p: None)

    base = tmp_path
    (base / "pyproject.toml").write_text(
        '[project]\nname = "test"\nrequires-python = ">=3.11,<3.14"\n'
    )

    monkeypatch.setattr(
        appenv,
        "find_available_pythons",
        lambda: [
            ("3.14", "/usr/bin/python3.14"),
            ("3.13", "/usr/bin/python3.13"),
        ],
    )

    execv_called = []

    def mock_execv(path, argv):
        execv_called.append((path, argv))
        raise SystemExit(0)

    monkeypatch.setattr("os.execv", mock_execv)
    monkeypatch.setattr("subprocess.check_call", lambda cmd, **kwargs: None)
    monkeypatch.setattr("sys.executable", "/different/python")

    with caplog.at_level(logging.DEBUG, logger="appenv"), pytest.raises(SystemExit):
        appenv.ensure_best_python(base)

    log_messages = caplog.text
    # Should log per-candidate reasoning (e.g., "3.14 skipped: exceeds max")
    assert "3.13" in log_messages, "ensure_best_python should log candidate evaluation"


def test_ensure_best_python_logs_final_decision(tmp_path, monkeypatch, caplog):
    """ensure_best_python emits log.debug with the final decision."""
    monkeypatch.delenv("APPENV_BEST_PYTHON", raising=False)
    monkeypatch.setattr("os.chdir", lambda p: None)

    base = tmp_path
    (base / "pyproject.toml").write_text(
        '[project]\nname = "test"\nrequires-python = ">=3.12"\n'
    )

    # Already running the best Python
    monkeypatch.setattr(
        appenv,
        "find_available_pythons",
        lambda: [("3.12", "/usr/bin/python3.12")],
    )

    def mock_resolve(self):
        return Path("/usr/bin/python3.12")

    monkeypatch.setattr("pathlib.Path.resolve", mock_resolve)
    monkeypatch.setattr("sys.executable", "/usr/bin/python3.12")

    with caplog.at_level(logging.DEBUG, logger="appenv"):
        appenv.ensure_best_python(base)

    log_messages = caplog.text
    # Should log final decision — either "already running" or "re-exec with ..."
    assert (
        "3.12" in log_messages
        or "already" in log_messages.lower()
        or "select" in log_messages.lower()
    ), "ensure_best_python should log the final decision"


# ============================================================================
# 4. error-message-improvement
# ============================================================================


def test_ensure_best_python_error_clear_constraint(tmp_path, monkeypatch, capsys):
    """Error output has a dedicated structured line for constraint.

    The current code prints constraint and versions but on raw lines
    like:

    The current code prints constraint and versions but on raw lines like:
      'Could not find Python >=3.13,<3.15'
    The fix should restructure to clearly separate constraint from version list.
    """
    monkeypatch.delenv("APPENV_BEST_PYTHON", raising=False)
    monkeypatch.setattr("os.chdir", lambda p: None)

    base = tmp_path
    (base / "pyproject.toml").write_text(
        '[project]\nname = "test"\nrequires-python = ">=3.13,<3.15"\n'
    )

    # Only old Python available
    monkeypatch.setattr(
        appenv,
        "find_available_pythons",
        lambda: [
            ("3.10", "/usr/bin/python3.10"),
            ("3.11", "/usr/bin/python3.11"),
        ],
    )

    with pytest.raises(SystemExit) as exc_info:
        appenv.ensure_best_python(base)

    assert exc_info.value.code == 65
    captured = capsys.readouterr()
    output = captured.out
    lines = output.strip().splitlines()

    # The restructured error should have a clearly labeled constraint line
    # (not just embedded in 'Could not find Python ...')
    has_constraint_line = any(
        ">=3.13" in line and "<3.15" in line and "requires" in line.lower()
        for line in lines
    )
    assert has_constraint_line, (
        "Error should have a clearly labeled constraint line with 'requires' label, "
        f"got:\n{output}"
    )


def test_ensure_best_python_error_restructured_format(tmp_path, monkeypatch, capsys):
    """When no matching Python found, error has restructured output.

    Current format: 'Could not find Python >=3.13,<3.15' on one line.
    The fix should separate the constraint into a clearly labeled line
    and keep the available versions in a well-structured list.
    """
    monkeypatch.delenv("APPENV_BEST_PYTHON", raising=False)
    monkeypatch.setattr("os.chdir", lambda p: None)

    base = tmp_path
    (base / "pyproject.toml").write_text(
        '[project]\nname = "test"\nrequires-python = ">=3.13,<3.15"\n'
    )

    # Only old Python available
    monkeypatch.setattr(
        appenv,
        "find_available_pythons",
        lambda: [
            ("3.10", "/usr/bin/python3.10"),
            ("3.11", "/usr/bin/python3.11"),
        ],
    )

    with pytest.raises(SystemExit) as exc_info:
        appenv.ensure_best_python(base)

    assert exc_info.value.code == 65
    captured = capsys.readouterr()
    output = captured.out
    lines = [ln for ln in output.strip().splitlines() if ln.strip()]

    # The restructured output should NOT have the old raw format:
    # 'Could not find Python >=3.13,<3.15'
    # Instead, constraint should be on a dedicated labeled line.
    has_labeled_constraint = any(
        ">=3.13" in line and "<3.15" in line and "require" in line.lower()
        for line in lines
    )
    assert has_labeled_constraint, (
        "Error should have a dedicated labeled constraint line (with 'require'), "
        f"got:\\n{output}"
    )

    # Should list all available versions with paths
    assert "/usr/bin/python3.10" in output
    assert "/usr/bin/python3.11" in output


# ============================================================================
# 5. gitignore-setup — init
# ============================================================================


def test_init_creates_gitignore(tmp_path, monkeypatch, test_settings, mock_uv):
    """init() creates .gitignore with [.venv, .appenv, .batou-lock] entries."""
    monkeypatch.chdir(tmp_path)
    base = tmp_path

    monkeypatch.setattr(appenv, "ensure_uv", lambda base: mock_uv)

    inputs = iter(
        [
            "myapp",  # command name
            "",  # no dependencies
            "myproject",  # project name
            "test",  # description
            "3.13",  # python version
        ]
    )
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    env = appenv.AppEnv(Path.cwd(), test_settings(Path.cwd()))
    env.init()

    gitignore_path = base / ".gitignore"
    assert gitignore_path.exists(), ".gitignore should be created by init()"

    content = gitignore_path.read_text()
    assert ".venv" in content
    assert ".appenv" in content
    assert ".batou-lock" in content


def test_init_appends_missing_gitignore_entries(
    tmp_path, monkeypatch, test_settings, mock_uv
):
    """init() appends missing entries to existing .gitignore."""
    monkeypatch.chdir(tmp_path)
    base = tmp_path

    # Pre-create .gitignore with some entries
    (base / ".gitignore").write_text("__pycache__/\n*.pyc\n")

    monkeypatch.setattr(appenv, "ensure_uv", lambda base: mock_uv)

    inputs = iter(
        [
            "myapp",
            "",
            "myproject",
            "test",
            "3.13",
        ]
    )
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    env = appenv.AppEnv(Path.cwd(), test_settings(Path.cwd()))
    env.init()

    content = (base / ".gitignore").read_text()
    # Original content preserved
    assert "__pycache__/" in content
    assert "*.pyc" in content
    # New entries added
    assert ".venv" in content
    assert ".appenv" in content
    assert ".batou-lock" in content


def test_init_gitignore_no_duplicates(tmp_path, monkeypatch, test_settings, mock_uv):
    """init() appends missing entries without duplicating existing ones.

    The .gitignore has .venv but not .appenv or .batou-lock.
    After init(), .appenv and .batou-lock should be added but .venv not duplicated.
    Currently XPASS: init() never touches .gitignore, so the file stays as-is.
    """
    monkeypatch.chdir(tmp_path)
    base = tmp_path

    # Pre-create .gitignore with .venv already present
    original = ".venv\n__pycache__/\n"
    (base / ".gitignore").write_text(original)

    monkeypatch.setattr(appenv, "ensure_uv", lambda base: mock_uv)

    inputs = iter(
        [
            "myapp",
            "",
            "myproject",
            "test",
            "3.13",
        ]
    )
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    env = appenv.AppEnv(Path.cwd(), test_settings(Path.cwd()))
    env.init()

    content = (base / ".gitignore").read_text()
    # .venv should appear exactly once (was already there, should not be re-added)
    assert content.count(".venv") == 1, ".venv should not be duplicated"
    # But the other entries should be added
    assert ".appenv" in content, ".appenv should be appended"
    assert ".batou-lock" in content, ".batou-lock should be appended"


# ============================================================================
# 6. gitignore-setup — migrate
# ============================================================================


def test_migrate_creates_gitignore(tmp_path, monkeypatch, test_settings):
    """migrate() creates .gitignore with [.venv] entry only."""
    monkeypatch.chdir(tmp_path)
    base = tmp_path

    (base / "requirements.txt").write_text("requests\n")

    # Mock ensure_uv and _uv_lock
    monkeypatch.setattr(appenv, "ensure_uv", lambda base_dir: None)
    monkeypatch.setattr(appenv.AppEnv, "_uv_lock", lambda self, uv, diff=False: None)

    inputs = iter(["myproject"])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    env = appenv.AppEnv(Path.cwd(), test_settings(Path.cwd()))
    env.migrate()

    gitignore_path = base / ".gitignore"
    assert gitignore_path.exists(), ".gitignore should be created by migrate()"

    content = gitignore_path.read_text()
    assert ".venv" in content
    # migrate() should NOT add .appenv or .batou-lock
    assert ".appenv" not in content
    assert ".batou-lock" not in content


def test_migrate_appends_missing_gitignore_entries(
    tmp_path, monkeypatch, test_settings
):
    """migrate() appends .venv to existing .gitignore without duplicating."""
    monkeypatch.chdir(tmp_path)
    base = tmp_path

    # Pre-create .gitignore
    (base / ".gitignore").write_text("__pycache__/\n*.pyc\n")
    (base / "requirements.txt").write_text("requests\n")

    monkeypatch.setattr(appenv, "ensure_uv", lambda base_dir: None)
    monkeypatch.setattr(appenv.AppEnv, "_uv_lock", lambda self, uv, diff=False: None)

    inputs = iter(["myproject"])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    env = appenv.AppEnv(Path.cwd(), test_settings(Path.cwd()))
    env.migrate()

    content = (base / ".gitignore").read_text()
    assert "__pycache__/" in content
    assert "*.pyc" in content
    assert ".venv" in content

