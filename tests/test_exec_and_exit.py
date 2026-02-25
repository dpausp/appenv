"""Tests for os.execv() process replacement and sys.exit() error paths."""

import os
import shutil
from pathlib import Path

import pytest

import appenv

# ============================================================================
# 1. os.execv() - Process Replacement Tests
# ============================================================================


class TestExecvProcessReplacement:
    """Tests for os.execv() calls that replace the current process."""

    def test_ensure_best_python_execv_with_correct_args(self, monkeypatch, tmpdir):
        """ensure_best_python calls os.execv with correct args."""
        monkeypatch.delenv("APPENV_BEST_PYTHON", raising=False)
        monkeypatch.setattr("os.chdir", lambda p: None)

        base = Path(tmpdir)
        (base / "pyproject.toml").write_text('[project]\nrequires-python = ">=3.11"\n')

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
        monkeypatch.setattr("os.environ", {})

        with pytest.raises(SystemExit):
            appenv.ensure_best_python(base)

        assert len(execv_called) == 1
        # Should pick 3.12 (newest that satisfies >=3.11)
        assert "python3.12" in execv_called[0][0]

    def test_ensure_best_python_skips_too_new_python(self, monkeypatch, tmpdir):
        """ensure_best_python skips versions exceeding bound."""
        monkeypatch.delenv("APPENV_BEST_PYTHON", raising=False)
        monkeypatch.setattr("os.chdir", lambda p: None)

        base = Path(tmpdir)
        (base / "pyproject.toml").write_text(
            '[project]\nrequires-python = ">=3.11,<3.14"\n'
        )

        # Mock available pythons including one exceeding upper bound
        monkeypatch.setattr(
            appenv,
            "find_available_pythons",
            lambda: [
                ("3.15", "/usr/bin/python3.15"),  # Too new (>= 3.14)
                ("3.13", "/usr/bin/python3.13"),  # Good
                ("3.12", "/usr/bin/python3.12"),
            ],
        )
        monkeypatch.setattr("subprocess.check_call", lambda cmd, **kwargs: None)
        monkeypatch.setattr("sys.executable", "/old/python")

        execv_called = []

        def mock_execv(path, argv):
            execv_called.append((path, argv))
            raise SystemExit(0)

        monkeypatch.setattr("os.execv", mock_execv)
        monkeypatch.setattr("os.environ", {})

        with pytest.raises(SystemExit):
            appenv.ensure_best_python(base)

        # Should pick 3.13 (newest that satisfies >=3.11,<3.14)
        assert len(execv_called) == 1
        assert "python3.13" in execv_called[0][0]

    def test_appenv_run_execv_with_command_path(self, monkeypatch, tmpdir):
        """AppEnv.run calls os.execv with correct command path and argv."""
        env = appenv.AppEnv(Path(tmpdir), Path.cwd())

        # Create mock venv structure
        env_dir = Path(tmpdir) / ".appenv" / "abc123"
        bin_dir = env_dir / "bin"
        bin_dir.mkdir(parents=True)
        (bin_dir / "myapp").write_text("#!/bin/sh\necho hello\n")

        monkeypatch.setattr(env, "prepare", lambda: str(env_dir))

        execv_called = []
        monkeypatch.setattr(
            os,
            "execv",
            lambda path, argv: execv_called.append((path, argv)),
        )
        monkeypatch.setattr("os.chdir", lambda p: None)

        env.run("myapp", ["--help", "arg1"])

        assert len(execv_called) == 1
        assert "myapp" in execv_called[0][0]
        # argv should start with command path, then user args
        assert "--help" in execv_called[0][1]
        assert "arg1" in execv_called[0][1]

    def test_appenv_run_sets_appenv_basedir(self, monkeypatch, tmpdir):
        """AppEnv.run sets APPENV_BASEDIR environment variable."""
        env = appenv.AppEnv(Path(tmpdir), Path.cwd())

        env_dir = Path(tmpdir) / ".appenv" / "abc123"
        bin_dir = env_dir / "bin"
        bin_dir.mkdir(parents=True)
        (bin_dir / "myapp").write_text("#!/bin/sh\necho hello\n")

        monkeypatch.setattr(env, "prepare", lambda: str(env_dir))

        env_set = {}
        monkeypatch.setattr(
            os,
            "execv",
            lambda path, argv: env_set.update(os.environ),
        )
        monkeypatch.setattr("os.chdir", lambda p: None)

        env.run("myapp", [])

        assert env_set.get("APPENV_BASEDIR") == str(tmpdir)


# ============================================================================
# 2. sys.exit() Error Paths Tests
# ============================================================================


class TestSysExitErrorPaths:
    """Tests for sys.exit() error handling paths."""

    # Code 65: Python not found errors

    def test_ensure_best_python_exits_65_no_python_found(
        self, monkeypatch, tmpdir, capsys
    ):
        """ensure_best_python exits with code 65 when no Python found."""
        monkeypatch.delenv("APPENV_BEST_PYTHON", raising=False)
        monkeypatch.setattr("os.chdir", lambda p: None)

        base = Path(tmpdir)
        (base / "pyproject.toml").write_text('[project]\nrequires-python = ">=3.99"\n')

        # No Python available
        monkeypatch.setattr(appenv, "find_available_pythons", lambda: [])

        with pytest.raises(SystemExit) as err:
            appenv.ensure_best_python(base)

        assert err.value.code == 65
        captured = capsys.readouterr()
        assert "Could not find Python" in captured.out

    def test_ensure_best_python_exits_65_with_upper_bound(
        self, monkeypatch, tmpdir, capsys
    ):
        """ensure_best_python shows upper bound in error message."""
        monkeypatch.delenv("APPENV_BEST_PYTHON", raising=False)
        monkeypatch.setattr("os.chdir", lambda p: None)

        base = Path(tmpdir)
        (base / "pyproject.toml").write_text(
            '[project]\nrequires-python = ">=3.99,<4.0"\n'
        )

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

    # Code 67: Missing lock files

    def test_prepare_exits_67_no_project_files(self, monkeypatch, tmpdir, capsys):
        """prepare exits with code 67 when no pyproject.toml found."""
        monkeypatch.chdir(tmpdir)

        env = appenv.AppEnv(Path(tmpdir), Path.cwd())

        with pytest.raises(SystemExit) as err:
            env.prepare()

        assert err.value.code == 67
        captured = capsys.readouterr()
        assert "pyproject.toml" in captured.out

    def test_prepare_pyproject_exits_67_missing_uv_lock(
        self, monkeypatch, tmpdir, capsys
    ):
        """_prepare_pyproject exits with code 67 when uv.lock is missing."""
        monkeypatch.chdir(tmpdir)
        base = Path(tmpdir)

        (base / "pyproject.toml").write_text(
            "[project]\nname = 'test'\ndependencies = []\n"
        )
        # No uv.lock created

        env = appenv.AppEnv(base, Path.cwd())

        with pytest.raises(SystemExit) as err:
            env._prepare_pyproject()

        assert err.value.code == 67
        captured = capsys.readouterr()
        assert "uv.lock" in captured.out

    # Code 68: uv version too old

    def test_ensure_uv_version_exits_68_too_old(self, monkeypatch, capsys):
        """ensure_uv_version exits with code 68 when uv is too old."""
        monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/uv")

        class FakeResult:
            stdout = "uv 0.4.0 (abc123 2024-01-01)\n"
            returncode = 0

        monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: FakeResult())

        with pytest.raises(SystemExit) as err:
            appenv.ensure_uv_version()

        assert err.value.code == 68
        captured = capsys.readouterr()
        assert "too old" in captured.out
        assert "0.5.0" in captured.out

    def test_check_uv_version_exits_68_parse_error(self, monkeypatch, capsys):
        """check_uv_version exits with code 68 when version is unparseable."""
        monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/uv")

        class FakeResult:
            stdout = "uv invalid-version\n"
            returncode = 0

        monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: FakeResult())

        with pytest.raises(SystemExit) as err:
            appenv.check_uv_version()

        assert err.value.code == 68
        captured = capsys.readouterr()
        assert "too old" in captured.out

    def test_update_lockfile_exits_67_no_project(self, monkeypatch, tmpdir, capsys):
        """update_lockfile exits with code 67 when no pyproject.toml found."""
        monkeypatch.chdir(tmpdir)
        monkeypatch.setattr(appenv, "ensure_uv", lambda base: None)

        env = appenv.AppEnv(Path(tmpdir), Path.cwd())

        with pytest.raises(SystemExit) as err:
            env.update_lockfile()

        assert err.value.code == 67
        captured = capsys.readouterr()
        assert "pyproject.toml" in captured.out


# ============================================================================
# 3. Nix Build Paths Tests
# ============================================================================


class TestNixBuildPaths:
    """Tests for nix-related functionality."""

    def test_has_nix_returns_true_when_available(self, monkeypatch):
        """has_nix returns True when nix is in PATH."""
        monkeypatch.setattr(
            "shutil.which", lambda name: "/usr/bin/nix" if name == "nix" else None
        )
        assert appenv.has_nix() is True

    def test_has_nix_returns_false_when_not_available(self, monkeypatch):
        """has_nix returns False when nix is not in PATH."""
        monkeypatch.setattr("shutil.which", lambda name: None)
        assert appenv.has_nix() is False

    def test_get_uv_bin_uses_nix_fallback(self, monkeypatch, tmpdir):
        """get_uv_bin uses nix build when uv not in PATH and nix available."""
        appenv._uv_bin_cache = None  # Reset cache
        base = Path(tmpdir)

        # No uv in PATH, but nix available
        def mock_which(name):
            if name == "uv":
                return None
            if name == "nix":
                return "/usr/bin/nix"
            return None

        monkeypatch.setattr("shutil.which", mock_which)

        # Create the expected uv binary path (directory structure only)
        uv_out = base / ".appenv" / ".uv"
        uv_bin_dir = uv_out / "bin"
        uv_bin_dir.mkdir(parents=True)
        uv_bin = uv_bin_dir / "uv"
        uv_bin.write_text("#!/bin/sh\necho 'uv 0.6.0'\n")

        class MockResult:
            def __init__(self, returncode=0, stdout=""):
                self.returncode = returncode
                self.stdout = stdout

        nix_calls = []

        def mock_run(cmd, **kwargs):
            nix_calls.append(cmd)
            # Return version output for uv --version calls
            if "--version" in cmd:
                return MockResult(stdout="uv 0.6.0\n")
            return MockResult()

        monkeypatch.setattr("subprocess.run", mock_run)

        result = appenv.get_uv_bin(base)

        assert ".appenv/.uv/bin/uv" in result
        assert any("nix" in str(cmd) and "build" in str(cmd) for cmd in nix_calls)

    def test_get_uv_bin_prioritizes_path_over_nix(self, monkeypatch, tmpdir):
        """get_uv_bin uses uv from PATH even when nix is available."""
        appenv._uv_bin_cache = None  # Reset cache
        base = Path(tmpdir)

        # Both uv and nix available
        def mock_which(name):
            if name == "uv":
                return "/usr/bin/uv"
            if name == "nix":
                return "/usr/bin/nix"
            return None

        monkeypatch.setattr("shutil.which", mock_which)

        result = appenv.get_uv_bin(base)

        assert result == "/usr/bin/uv"

    def test_get_uv_bin_uses_pip_when_no_nix(self, monkeypatch, tmpdir):
        """get_uv_bin uses pip install fallback when no nix available."""
        appenv._uv_bin_cache = None  # Reset cache
        base = Path(tmpdir)

        # No uv, no nix
        monkeypatch.setattr("shutil.which", lambda name: None)

        pip_calls = []
        monkeypatch.setattr(
            "subprocess.run",
            lambda cmd, **kwargs: pip_calls.append(cmd),
        )

        with pytest.raises(RuntimeError, match="uv not found"):
            appenv.get_uv_bin(base)

        # Should have tried pip install
        assert any("pip" in str(cmd) and "uv" in str(cmd) for cmd in pip_calls)

    @pytest.mark.skipif(shutil.which("nix") is None, reason="nix not installed")
    def test_get_uv_bin_nix_integration(self, monkeypatch, tmpdir):
        """Integration test: get_uv_bin works with real nix when available."""
        appenv._uv_bin_cache = None  # Reset cache
        base = Path(tmpdir)

        # Remove uv from consideration to force nix fallback
        original_which = shutil.which

        def mock_which(name):
            if name == "uv":
                return None
            return original_which(name)

        # Use monkeypatch instead of direct assignment
        monkeypatch.setattr("shutil.which", mock_which)

        result = appenv.get_uv_bin(base)

        assert ".appenv/.uv/bin/uv" in result
        assert (base / ".appenv" / ".uv" / "bin" / "uv").exists()

        # Cleanup
        appenv._uv_bin_cache = None
