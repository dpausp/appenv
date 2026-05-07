"""Integration tests for pip-based uv installation.

These tests exercise the real pip install flow end-to-end:
- ensurepip + pip install uv --target
- pip from PATH (which pip) + pip install uv --target

Run with: uv run pytest -m slow tests/integration/test_pip_install_uv.py -s
"""

import shutil
import subprocess
import sys

import pytest

import appenv
from appenv import UvBin


def _pip_is_available():
    """Check that pip is available (either as module or as command)."""
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "--version"],
            capture_output=True,
            timeout=10,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
    else:
        return True

    pip_path = shutil.which("pip")
    if pip_path:
        try:
            subprocess.run(
                [pip_path, "--version"],
                capture_output=True,
                timeout=10,
                check=True,
            )
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass
        else:
            return True

    return False


pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(
        not _pip_is_available(),
        reason="pip not available for integration test",
    ),
]


def _sys_python_has_pip():
    """Check if sys.executable has pip as a module."""
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "--version"],
            capture_output=True,
            timeout=10,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False
    else:
        return True


def test_pip_install_uv_creates_working_binary(tmp_path):
    """pip install uv -t <target> produces a working uv binary."""
    if not _sys_python_has_pip():
        pytest.skip("sys.executable has no pip module")

    target = tmp_path / ".uv"

    # This is exactly what _try_uv_from_pip does (minus the ensurepip step)
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "uv", "--upgrade", "-t", str(target)],
        capture_output=True,
        text=True,
        check=True,
        timeout=120,
    )

    # Verify binary exists where UvBin expects it
    uv_binary = target / "bin" / "uv"
    assert uv_binary.exists(), f"uv binary not found at {uv_binary}"

    # Verify binary is executable
    assert uv_binary.stat().st_mode & 0o111, "uv binary is not executable"

    # Verify binary runs and reports a valid version
    result = subprocess.run(
        [str(uv_binary), "--version"],
        capture_output=True,
        text=True,
        timeout=10,
        check=True,
    )
    assert "uv" in result.stdout.lower(), f"unexpected version output: {result.stdout}"

    # Verify UvBin.get_uv_version can parse it
    version = UvBin.get_uv_version(uv_binary)
    assert version.valid, f"version parsed as invalid: {version}"


def test_pip_install_uv_from_which_pip(tmp_path):
    """pip install uv -t works with pip found via shutil.which()."""
    pip_path = shutil.which("pip") or shutil.which("pip3")
    assert pip_path, "no pip/pip3 found in PATH"

    target = tmp_path / ".uv"

    subprocess.run(
        [pip_path, "install", "uv", "--upgrade", "-t", str(target)],
        capture_output=True,
        text=True,
        check=True,
        timeout=120,
    )

    uv_binary = target / "bin" / "uv"
    assert uv_binary.exists(), f"uv binary not found at {uv_binary}"

    version = UvBin.get_uv_version(uv_binary)
    assert version.valid, f"version parsed as invalid: {version}"


def test_try_uv_from_pip_integration(tmp_path, monkeypatch):
    """Full integration test of UvBin._try_uv_from_pip with real subprocess.

    Disables all earlier discovery methods so _try_uv_from_pip is reached.
    """
    appenv_dir = tmp_path / ".appenv"
    appenv_dir.mkdir()

    # Disable auto-mocking from conftest: we need real subprocess calls
    monkeypatch.undo()
    # Re-apply only ensure_uv mock to prevent UvBin.__init__ from running discovery
    monkeypatch.setattr(appenv, "ensure_uv", lambda base: None)

    # Build UvBin without triggering discovery
    uv_bin = UvBin.__new__(UvBin)
    uv_bin.appenv_dir = appenv_dir
    uv_bin.uv_dir = appenv_dir / ".uv"
    uv_bin.managed_uv = uv_bin.uv_dir / "bin" / "uv"

    result = uv_bin._try_uv_from_pip()

    assert result is not None, "_try_uv_from_pip returned None — pip install failed"
    assert result.exists(), f"returned path does not exist: {result}"

    version = UvBin.get_uv_version(result)
    assert version.valid, f"installed uv has invalid version: {version}"
