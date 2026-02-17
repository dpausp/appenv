"""Tests for main() entry point and related functions."""

import argparse
import os
from pathlib import Path

import pytest

import appenv

# main() tests


def test_main_shows_usage_without_subcommand(monkeypatch, capsys):
    monkeypatch.setattr(appenv, "ensure_best_python", lambda base: None)
    monkeypatch.setattr("sys.argv", ["appenv"])

    appenv.main()

    captured = capsys.readouterr()
    assert "usage:" in captured.out.lower()


def test_main_clears_pythonpath(monkeypatch):
    monkeypatch.setattr(appenv, "ensure_best_python", lambda base: None)
    monkeypatch.setattr("sys.argv", ["appenv"])

    monkeypatch.setenv("PYTHONPATH", "/some/path")
    assert "PYTHONPATH" in os.environ

    appenv.main()

    assert "PYTHONPATH" not in os.environ


def test_main_calls_run_when_not_appenv(monkeypatch, tmpdir):
    monkeypatch.setattr(appenv, "ensure_best_python", lambda base: None)

    app_file = tmpdir / "myapp"
    app_file.write("#!/usr/bin/env python3\nprint('test')\n")

    run_called = []
    monkeypatch.setattr(
        appenv.AppEnv,
        "run",
        lambda self, cmd, argv: run_called.append((cmd, argv)),
    )

    monkeypatch.setattr("sys.argv", ["myapp", "--help"])
    monkeypatch.setattr(appenv, "__file__", str(app_file))

    appenv.main()

    assert run_called == [("myapp", ["--help"])]


def test_main_calls_meta_when_appenv(monkeypatch):
    monkeypatch.setattr(appenv, "ensure_best_python", lambda base: None)

    meta_called = []
    monkeypatch.setattr(appenv.AppEnv, "meta", lambda self: meta_called.append(True))

    monkeypatch.setattr("sys.argv", ["appenv"])
    monkeypatch.setattr(appenv, "__file__", "/some/path/appenv")

    appenv.main()

    assert meta_called == [True]


# cmd() tests


def test_cmd_with_string_uses_shell():
    result = appenv.cmd("echo hello")
    assert b"hello" in result


def test_cmd_raises_value_error_on_failure():
    with pytest.raises(ValueError):
        appenv.cmd("exit 1", quiet=True)


def test_cmd_with_list_no_shell():
    result = appenv.cmd(["echo", "world"])
    assert b"world" in result


# uv_cmd() tests


def test_uv_cmd_raises_when_uv_not_found(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: None)

    with pytest.raises(RuntimeError, match="uv not found"):
        appenv.uv_cmd(["--version"])


def test_get_uv_bin_uses_path(monkeypatch):
    """get_uv_bin returns uv from PATH if available."""
    appenv._uv_bin_cache = None  # Reset cache
    monkeypatch.setattr(
        "shutil.which", lambda name: "/usr/bin/uv" if name == "uv" else None
    )
    assert appenv.get_uv_bin() == "/usr/bin/uv"


def test_get_uv_bin_uses_pip_fallback(monkeypatch, tmpdir):
    """get_uv_bin installs uv via pip if not in PATH and no nix."""
    appenv._uv_bin_cache = None  # Reset cache
    monkeypatch.setattr("shutil.which", lambda name: None)  # no uv, no nix

    pip_called = []
    monkeypatch.setattr(
        "subprocess.run",
        lambda cmd, **kwargs: pip_called.append(cmd),
    )

    with pytest.raises(RuntimeError, match="uv not found"):
        appenv.get_uv_bin(Path(tmpdir))

    assert any("pip" in str(cmd) and "uv" in str(cmd) for cmd in pip_called)


# ensure_best_python() tests


def test_ensure_best_python_skips_when_env_set(monkeypatch, tmpdir):
    monkeypatch.setenv("APPENV_BEST_PYTHON", "/usr/bin/python3")
    monkeypatch.setattr("os.chdir", lambda p: None)

    appenv.ensure_best_python(Path(tmpdir))


def test_ensure_best_python_exits_when_no_python_found(monkeypatch, tmpdir, capsys):
    monkeypatch.delenv("APPENV_BEST_PYTHON", raising=False)
    monkeypatch.setattr("os.chdir", lambda p: None)
    monkeypatch.setattr("shutil.which", lambda name: None)

    with pytest.raises(SystemExit) as err:
        appenv.ensure_best_python(Path(tmpdir))

    assert err.value.code == 65
    captured = capsys.readouterr()
    assert "Could not find" in captured.out


# ensure_minimal_python() tests


def test_find_minimal_python_returns_none_when_no_preferences(monkeypatch, tmpdir):
    monkeypatch.chdir(tmpdir)
    (tmpdir / "requirements.txt").write("requests\n")

    result = appenv.find_minimal_python()

    assert result is None


def test_find_minimal_python_exits_when_not_found(monkeypatch, capsys, tmpdir):
    monkeypatch.chdir(tmpdir)
    (tmpdir / "requirements.txt").write("# appenv-python-preference: 3.99\nrequests\n")
    monkeypatch.setattr("shutil.which", lambda name: None)

    with pytest.raises(SystemExit) as err:
        appenv.find_minimal_python()

    assert err.value.code == 66


# meta() tests


def test_meta_calls_reset(monkeypatch, tmpdir):
    env = appenv.AppEnv(Path(tmpdir), Path.cwd())
    monkeypatch.setattr("sys.argv", ["appenv", "reset"])

    reset_called = []
    monkeypatch.setattr(
        env, "reset", lambda args=None, remaining=None: reset_called.append(True)
    )

    env.meta()

    assert reset_called == [True]


def test_meta_calls_prepare(monkeypatch, tmpdir):
    env = appenv.AppEnv(Path(tmpdir), Path.cwd())
    monkeypatch.setattr("sys.argv", ["appenv", "prepare"])

    prepare_called = []
    monkeypatch.setattr(
        env,
        "prepare",
        lambda args=None, remaining=None: prepare_called.append(True),
    )

    env.meta()

    assert prepare_called == [True]


def test_meta_calls_python(monkeypatch, tmpdir):
    env = appenv.AppEnv(Path(tmpdir), Path.cwd())
    monkeypatch.setattr("sys.argv", ["appenv", "python"])

    python_called = []
    monkeypatch.setattr(
        env,
        "python",
        lambda args, remaining: python_called.append((args, remaining)),
    )

    env.meta()

    assert len(python_called) == 1


def test_meta_calls_run_script(monkeypatch, tmpdir):
    env = appenv.AppEnv(Path(tmpdir), Path.cwd())
    monkeypatch.setattr("sys.argv", ["appenv", "run", "myscript"])

    run_called = []
    monkeypatch.setattr(
        env,
        "run_script",
        lambda args, remaining: run_called.append((args.script, remaining)),
    )

    env.meta()

    assert run_called == [("myscript", [])]


# run() tests


def test_run_sets_env_and_execs(monkeypatch, tmpdir):
    env = appenv.AppEnv(Path(tmpdir), Path.cwd())

    env_dir = tmpdir.mkdir(".appenv").mkdir("abc123")
    bin_dir = env_dir.mkdir("bin")
    bin_dir.join("myapp").write("#!/bin/sh\necho hello\n")

    monkeypatch.setattr(env, "prepare", lambda: str(env_dir))

    execv_called = []
    monkeypatch.setattr(
        os,
        "execv",
        lambda path, argv: execv_called.append((path, argv)),
    )
    monkeypatch.setattr("os.chdir", lambda p: None)

    env.run("myapp", ["--help"])

    assert len(execv_called) == 1
    assert "myapp" in execv_called[0][0]


# _assert_requirements_lock() tests


def test_assert_requirements_lock_hash_mismatch_exits(monkeypatch, tmpdir, capsys):
    monkeypatch.chdir(tmpdir)

    (tmpdir / "requirements.txt").write("requests==2.0.0\n")
    (tmpdir / "requirements.lock").write(
        "# appenv-requirements-hash: wronghash123\nrequests==1.0.0\n"
    )

    env = appenv.AppEnv(Path(tmpdir), Path.cwd())

    with pytest.raises(SystemExit) as err:
        env._assert_requirements_lock()

    assert err.value.code == 67
    captured = capsys.readouterr()
    assert "out of date" in captured.out or "hash mismatch" in captured.out


# update_lockfile() tests


def test_update_lockfile_without_uv_installs_it(monkeypatch, tmpdir, capsys):
    """When uv is not available, ensure_uv installs it via pip."""
    monkeypatch.chdir(tmpdir)
    monkeypatch.setattr("shutil.which", lambda name: None)  # no uv, no nix

    pip_install_called = []
    monkeypatch.setattr(
        "subprocess.run",
        lambda cmd, **kwargs: pip_install_called.append(cmd),
    )

    env = appenv.AppEnv(Path(tmpdir), Path.cwd())

    # Reset uv cache
    appenv._uv_bin_cache = None

    # Mock uv_cmd to avoid actual execution
    monkeypatch.setattr(appenv, "uv_cmd", lambda args, **kwargs: None)
    monkeypatch.setattr(appenv, "find_minimal_python", lambda: None)

    (tmpdir / "requirements.txt").write("requests\n")

    # This should try to install uv via pip
    try:
        env.update_lockfile()
    except RuntimeError:
        # Expected: uv not found (mocked)
        pass

    assert any("pip" in str(cmd) and "uv" in str(cmd) for cmd in pip_install_called)


def test_update_lockfile_preserves_editable_installs(monkeypatch, tmpdir):
    monkeypatch.chdir(tmpdir)
    monkeypatch.setattr(appenv, "ensure_uv", lambda base: None)
    monkeypatch.setattr(appenv, "find_minimal_python", lambda: None)

    (tmpdir / "requirements.txt").write("-e /path/to/local/pkg\nrequests\n")

    def mock_uv_cmd(args, **kwargs):
        with open("requirements.lock", "w") as f:
            f.write("requests==2.28.0\n")

    monkeypatch.setattr(appenv, "uv_cmd", mock_uv_cmd)

    env = appenv.AppEnv(Path(tmpdir), Path.cwd())
    env.update_lockfile()

    with open("requirements.lock") as f:
        content = f.read()
    assert "-e /path/to/local/pkg" in content


# python() method tests


def test_python_method_calls_run(monkeypatch, tmpdir):
    env = appenv.AppEnv(Path(tmpdir), Path.cwd())

    run_called = []
    monkeypatch.setattr(env, "run", lambda cmd, argv: run_called.append((cmd, argv)))

    env.python(argparse.Namespace(), ["-c", "print(1)"])

    assert run_called == [("python", ["-c", "print(1)"])]
