"""Tests for appenv.ensure_best_python."""

import subprocess
from pathlib import Path

import pytest

import appenv

# Happy path


def test_ensure_best_python_skips_when_env_set(tmp_path, monkeypatch, make_pyproject):
    """Line 92: Returns early when APPENV_BEST_PYTHON is set."""
    base = tmp_path
    make_pyproject(base, '[project]\nname = "test"\n')

    monkeypatch.setenv("APPENV_BEST_PYTHON", "/usr/bin/python3")
    monkeypatch.setattr("os.chdir", lambda p: None)

    appenv.ensure_best_python(base)


def test_ensure_best_python_already_running_best(tmp_path, monkeypatch, make_pyproject):
    """Line 123: Returns early when already running the best Python."""
    base = tmp_path
    make_pyproject(base, '[project]\nname = "test"\n')

    monkeypatch.delenv("APPENV_BEST_PYTHON", raising=False)
    monkeypatch.setattr("os.chdir", lambda p: None)

    monkeypatch.setattr(
        appenv,
        "find_available_pythons",
        lambda: [("3.12", "/usr/bin/python3.12")],
    )

    def mock_resolve(self):
        return Path("/usr/bin/python3.12")

    monkeypatch.setattr("pathlib.Path.resolve", mock_resolve)
    monkeypatch.setattr("sys.executable", "/usr/bin/python3.12")

    appenv.ensure_best_python(base)


def test_ensure_best_python_execv_with_correct_args(
    monkeypatch, tmp_path, make_pyproject
):
    """ensure_best_python calls os.execv with correct args."""
    monkeypatch.delenv("APPENV_BEST_PYTHON", raising=False)
    monkeypatch.setattr("os.chdir", lambda p: None)

    base = tmp_path
    make_pyproject(base, '[project]\nrequires-python = ">=3.11"\n')

    # Mock available pythons
    monkeypatch.setattr(
        appenv,
        "find_available_pythons",
        lambda: [
            ("3.12", "/usr/bin/python3.12"),
            ("3.11", "/usr/bin/python3.11"),
        ],
    )
    monkeypatch.setattr("subprocess.check_call", lambda cmd, **kwargs: None)
    monkeypatch.setattr("sys.executable", "/old/python")

    execv_called = []

    def mock_execv(path, argv):
        execv_called.append((path, argv))
        raise SystemExit(0)

    monkeypatch.setattr("os.execv", mock_execv)

    with pytest.raises(SystemExit):
        appenv.ensure_best_python(base)

    assert len(execv_called) == 1
    # Should pick 3.12 (newest that satisfies >=3.11)
    assert "python3.12" in execv_called[0][0]


def test_ensure_best_python_respects_upper_bound(
    tmp_path, monkeypatch, capsys, make_pyproject
):
    """ensure_best_python respects upper bound in requires-python."""
    monkeypatch.chdir(tmp_path)
    base = tmp_path

    # Ensure APPENV_BEST_PYTHON is not set (causes early return if set)
    monkeypatch.delenv("APPENV_BEST_PYTHON", raising=False)

    # Create pyproject.toml with upper bound
    make_pyproject(
        base, '[project]\nname = "test"\nrequires-python = ">=3.11,<3.14"\n'
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


# Error cases


def test_ensure_best_python_exits_65_no_python_found(
    monkeypatch, tmp_path, capsys, make_pyproject
):
    """ensure_best_python exits with code 65 when no Python found."""
    monkeypatch.delenv("APPENV_BEST_PYTHON", raising=False)
    monkeypatch.setattr("os.chdir", lambda p: None)

    base = tmp_path
    make_pyproject(base, '[project]\nrequires-python = ">=3.99"\n')

    # No Python available
    monkeypatch.setattr(appenv, "find_available_pythons", list)

    with pytest.raises(SystemExit) as err:
        appenv.ensure_best_python(base)

    assert err.value.code == 65
    captured = capsys.readouterr()
    assert "requires-python:" in captured.out


def test_ensure_best_python_exits_65_with_upper_bound(
    monkeypatch, tmp_path, capsys, make_pyproject
):
    """ensure_best_python shows upper bound in error message."""
    monkeypatch.delenv("APPENV_BEST_PYTHON", raising=False)
    monkeypatch.setattr("os.chdir", lambda p: None)

    base = tmp_path
    make_pyproject(base, '[project]\nrequires-python = ">=3.99,<4.0"\n')

    # Only have old Python
    monkeypatch.setattr(
        appenv,
        "find_available_pythons",
        lambda: [("3.11", "/usr/bin/python3.11")],
    )

    with pytest.raises(SystemExit) as err:
        appenv.ensure_best_python(base)

    assert err.value.code == 65
    captured = capsys.readouterr()
    # Should show upper bound in error message
    assert "3.99" in captured.out
    assert "<4.0" in captured.out


# Edge cases


def test_ensure_best_python_default_min_version(tmp_path, monkeypatch, make_pyproject):
    """Line 99: Uses 3.10 as default when no requires-python specified."""
    base = tmp_path
    make_pyproject(base, '[project]\nname = "test"\n')

    monkeypatch.delenv("APPENV_BEST_PYTHON", raising=False)
    monkeypatch.setattr("os.chdir", lambda p: None)

    monkeypatch.setattr(
        appenv,
        "find_available_pythons",
        lambda: [
            ("3.14", "/usr/bin/python3.14"),
            ("3.10", "/usr/bin/python3.10"),
            ("3.9", "/usr/bin/python3.9"),
        ],
    )

    execv_called = []

    def mock_execv(path, argv):
        execv_called.append((path, argv))
        raise SystemExit(0)

    monkeypatch.setattr("os.execv", mock_execv)
    monkeypatch.setattr("subprocess.check_call", lambda cmd, **kwargs: None)
    monkeypatch.setattr("sys.executable", "/different/python")

    with pytest.raises(SystemExit):
        appenv.ensure_best_python(base)

    assert "python3.14" in execv_called[0][0]


def test_ensure_best_python_broken_python(tmp_path, monkeypatch, make_pyproject):
    """Lines 132-133: Continues to next Python when subprocess fails."""
    base = tmp_path
    make_pyproject(base, '[project]\nname = "test"\n')

    monkeypatch.delenv("APPENV_BEST_PYTHON", raising=False)
    monkeypatch.setattr("os.chdir", lambda p: None)

    monkeypatch.setattr(
        appenv,
        "find_available_pythons",
        lambda: [
            ("3.12", "/usr/bin/python3.12"),
            ("3.11", "/usr/bin/python3.11"),
        ],
    )

    check_call_count = []

    def mock_check_call(cmd, **kwargs):
        check_call_count.append(cmd)
        if "python3.12" in str(cmd):
            raise subprocess.CalledProcessError(1, cmd)

    execv_called = []

    def mock_execv(path, argv):
        execv_called.append((path, argv))
        raise SystemExit(0)

    monkeypatch.setattr("subprocess.check_call", mock_check_call)
    monkeypatch.setattr("os.execv", mock_execv)
    monkeypatch.setattr("sys.executable", "/different/python")

    with pytest.raises(SystemExit):
        appenv.ensure_best_python(base)

    assert len(check_call_count) == 2
    assert "python3.11" in execv_called[0][0]
