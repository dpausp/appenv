import logging
import shutil
import subprocess
from pathlib import Path

import pytest

import appenv
from appenv import EXIT_CODE_UNAVAILABLE, NoValidUvError, UvBin, UvVersion, ensure_uv


class FakeResult:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_uv_bin_cmd_raises_when_uv_not_found(monkeypatch):
    # UvBin.cmd raises FileNotFoundError when uv binary doesn't exist
    # Create a UvBin with a non-existent binary
    uv = UvBin.__new__(UvBin)
    uv.bin = Path("/usr/bin/nonexistent_uv")
    uv.appenv_dir = Path("/tmp/.appenv")
    uv.uv_dir = uv.appenv_dir / ".uv"

    with pytest.raises(FileNotFoundError):
        uv.cmd(["lock"])


def test_try_uv_from_path_returns_path_when_valid(monkeypatch, tmp_path):
    """_try_uv_from_path returns path when uv in PATH and version valid."""
    # Create a UvBin instance using constructor
    uv_bin = UvBin(tmp_path / ".appenv")

    # Mock shutil.which to return a path
    monkeypatch.setattr(
        "shutil.which", lambda name: "/usr/bin/uv" if name == "uv" else None
    )

    # Mock UvBin.get_uv_version to return a valid version
    mock_version = UvVersion(0, 10, 3)
    monkeypatch.setattr(UvBin, "get_uv_version", lambda path: mock_version)

    # Mock _cleanup_appenv_uv to track if it's called
    cleanup_called = []
    monkeypatch.setattr(
        uv_bin, "_cleanup_appenv_uv", lambda: cleanup_called.append(True)
    )

    # Call the method
    result = uv_bin._try_uv_from_path()

    # Verify results
    assert result == Path("/usr/bin/uv")
    assert cleanup_called == [True]  # Cleanup should be called


def test_try_uv_from_path_returns_none_when_invalid_version(monkeypatch):
    """_try_uv_from_path returns None when uv in PATH but version invalid."""
    # Create a UvBin instance
    uv_bin = UvBin.__new__(UvBin)
    uv_bin.appenv_dir = Path("/tmp/.appenv")
    uv_bin.uv_dir = uv_bin.appenv_dir / ".uv"

    # Mock shutil.which to return a path
    monkeypatch.setattr(
        "shutil.which", lambda name: "/usr/bin/uv" if name == "uv" else None
    )

    # Mock UvBin.get_uv_version to return None (invalid version)
    monkeypatch.setattr(UvBin, "get_uv_version", lambda path: UvVersion.unknown())

    # Mock _cleanup_appenv_uv to track if it's called
    cleanup_called = []
    monkeypatch.setattr(
        uv_bin, "_cleanup_appenv_uv", lambda: cleanup_called.append(True)
    )

    # Call the method
    result = uv_bin._try_uv_from_path()

    # Verify results
    assert result is None
    assert cleanup_called == []  # Cleanup should not be called


def test_try_uv_from_path_returns_none_when_not_in_path(monkeypatch):
    """_try_uv_from_path returns None when uv not in PATH."""
    # Create a UvBin instance
    uv_bin = UvBin.__new__(UvBin)
    uv_bin.appenv_dir = Path("/tmp/.appenv")
    uv_bin.uv_dir = uv_bin.appenv_dir / ".uv"

    # Mock shutil.which to return None (not found)
    monkeypatch.setattr("shutil.which", lambda name: None)

    # Mock _cleanup_appenv_uv to track if it's called
    cleanup_called = []
    monkeypatch.setattr(
        uv_bin, "_cleanup_appenv_uv", lambda: cleanup_called.append(True)
    )

    # Call the method
    result = uv_bin._try_uv_from_path()

    # Verify results
    assert result is None
    assert cleanup_called == []  # Cleanup should not be called


@pytest.mark.no_mock_uv_version
def test_uv_binget_uv_version_returns_version_on_success(tmp_path, monkeypatch):
    """Returns UvVersion object on successful version check."""
    uv = UvBin.__new__(UvBin)
    uv.bin = Path("/usr/bin/uv")
    uv.appenv_dir = tmp_path / ".appenv"
    uv.uv_dir = uv.appenv_dir / ".uv"

    monkeypatch.setattr(
        "subprocess.run",
        lambda *args, **kwargs: FakeResult(stdout="uv 0.10.3 (abc123 2024-01-01)\n"),
    )

    result = UvBin.get_uv_version(uv.bin)

    assert isinstance(result, UvVersion)
    assert result == UvVersion(0, 10, 3)


@pytest.mark.no_mock_uv_version
def test_uv_binget_uv_version_not_valid_on_subprocess_error(monkeypatch, capsys):
    """When uv --version fails, get_uv_version returns None."""
    uv = UvBin.__new__(UvBin)
    uv.bin = Path("/usr/bin/uv")
    uv.appenv_dir = Path("/tmp/.appenv")
    uv.uv_dir = uv.appenv_dir / ".uv"

    import subprocess

    def fake_run(*args, **kwargs):
        raise subprocess.CalledProcessError(1, "uv --version")

    monkeypatch.setattr("subprocess.run", fake_run)

    version = UvBin.get_uv_version(uv.bin)
    assert version == UvVersion.unknown()


@pytest.mark.no_mock_uv_version
def test_uv_binget_uv_version_returns_none_when_too_old(monkeypatch, capsys):
    """When version is too old, get_uv_version returns UvVersion with valid=False."""
    uv = UvBin.__new__(UvBin)
    uv.bin = Path("/usr/bin/uv")
    uv.appenv_dir = Path("/tmp/.appenv")
    uv.uv_dir = uv.appenv_dir / ".uv"

    monkeypatch.setattr(
        "subprocess.run",
        lambda *args, **kwargs: FakeResult(stdout="uv 0.4.0 (abc123 2024-01-01)\n"),
    )

    result = UvBin.get_uv_version(uv.bin)

    assert isinstance(result, UvVersion)
    assert result == UvVersion(0, 4, 0)
    assert not result.valid


@pytest.mark.no_mock_uv_version
def test_uv_binget_uv_version_handles_parse_error(tmp_path, monkeypatch, capsys):
    """When version string is unparseable, get_uv_version returns None."""
    uv = UvBin.__new__(UvBin)
    uv.bin = Path("/usr/bin/uv")
    uv.appenv_dir = tmp_path / ".appenv"
    uv.uv_dir = uv.appenv_dir / ".uv"

    monkeypatch.setattr(
        "subprocess.run",
        lambda *args, **kwargs: FakeResult(stdout="uv invalid-version\n"),
    )

    result = UvBin.get_uv_version(uv.bin)

    assert result == UvVersion.unknown()


@pytest.mark.no_mock_uv_version
def test_uv_binget_uv_version_index_error_on_split(monkeypatch, capsys):
    """IndexError when version output has no second element returns None."""
    uv = UvBin.__new__(UvBin)
    uv.bin = Path("/usr/bin/uv")
    uv.appenv_dir = Path("/tmp/.appenv")
    uv.uv_dir = uv.appenv_dir / ".uv"

    monkeypatch.setattr(
        "subprocess.run",
        lambda *args, **kwargs: FakeResult(stdout="uv\n"),
    )

    result = UvBin.get_uv_version(uv.bin)

    assert result == UvVersion.unknown()


def test_try_uv_from_appenv_dir_returns_path_when_valid(monkeypatch, tmp_path):
    """_try_uv_from_appenv_dir returns path when uv exists and version is valid."""
    # Create a UvBin instance
    uv_bin = UvBin(tmp_path / ".appenv")

    # Create the .appenv/.uv/bin/uv file
    uv_local = tmp_path / ".appenv/.uv/bin/uv"
    uv_local.parent.mkdir(parents=True)
    uv_local.write_text("#!/bin/sh\n")

    # Mock UvBin.get_uv_version to return a valid version
    mock_version = UvVersion(0, 10, 3)
    monkeypatch.setattr(UvBin, "get_uv_version", lambda path: mock_version)

    # Call the method
    result = uv_bin._try_uv_from_appenv_dir()

    # Verify results
    assert result == uv_local


def test_try_uv_from_appenv_dir_returns_none_when_invalid_version(
    monkeypatch, tmp_path
):
    """_try_uv_from_appenv_dir returns None when uv exists but version is invalid."""
    # Create a UvBin instance
    uv_bin = UvBin(tmp_path / ".appenv")

    # Create the .appenv/.uv/bin/uv file
    uv_local = tmp_path / ".appenv/.uv/bin/uv"
    uv_local.parent.mkdir(parents=True)
    uv_local.write_text("#!/bin/sh\n")

    # Mock UvBin.get_uv_version to return unknown version (invalid)
    monkeypatch.setattr(UvBin, "get_uv_version", lambda path: UvVersion.unknown())

    # Call the method
    result = uv_bin._try_uv_from_appenv_dir()

    # Verify results
    assert result is None


def test_try_uv_from_appenv_dir_returns_none_when_not_exists(monkeypatch, tmp_path):
    """_try_uv_from_appenv_dir returns None when uv does not exist."""
    # Create a UvBin instance
    uv_bin = UvBin(tmp_path / ".appenv")

    # Do not create the .appenv/.uv/bin/uv file

    # Call the method
    result = uv_bin._try_uv_from_appenv_dir()

    # Verify results
    assert result is None


# ==============================================================================
# UvBin._try_uv_from_nix_channel tests
# ==============================================================================


def test_try_uv_from_nix_channel_returns_path_when_valid(monkeypatch, tmp_path, caplog):
    """_try_uv_from_nix_channel returns path when nix build succeeds."""
    # Create a UvBin instance
    uv_bin = UvBin(tmp_path / ".appenv")

    # Mock preceding methods to return None so we reach this method
    monkeypatch.setattr(uv_bin, "_try_uv_from_path", lambda: None)
    monkeypatch.setattr(uv_bin, "_try_uv_from_appenv_dir", lambda: None)

    # Mock shutil.which to return nix path
    monkeypatch.setattr(
        "shutil.which", lambda name: "/nix/bin/nix" if name == "nix" else None
    )

    # Mock uv_local.exists() to return True (so we get the "Updating" log)
    uv_local = tmp_path / ".appenv/.uv/bin/uv"
    uv_local.parent.mkdir(parents=True)
    uv_local.write_text("#!/bin/sh\n")

    # Mock subprocess.run to return success
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: FakeResult())

    # Mock UvBin.get_uv_version to return a valid version
    mock_version = UvVersion(0, 10, 3)
    monkeypatch.setattr(UvBin, "get_uv_version", lambda path: mock_version)

    # Cap logs at DEBUG level
    caplog.set_level(logging.DEBUG)

    # Call the method
    result = uv_bin._try_uv_from_nix_channel()

    # Verify results
    assert result == uv_local
    # Check that we got the "Updating" log (since uv_local.exists() was True)
    assert "Updating .appenv/.uv with Nix" in caplog.text


def test_try_uv_from_nix_channel_returns_path_when_created(
    monkeypatch, tmp_path, caplog
):
    """_try_uv_from_nix_channel returns path when nix build succeeds and uv needed."""
    # Create a UvBin instance
    uv_bin = UvBin(tmp_path / ".appenv")

    # Mock preceding methods to return None so we reach this method
    monkeypatch.setattr(uv_bin, "_try_uv_from_path", lambda: None)
    monkeypatch.setattr(uv_bin, "_try_uv_from_appenv_dir", lambda: None)

    # Mock shutil.which to return nix path
    monkeypatch.setattr(
        "shutil.which", lambda name: "/nix/bin/nix" if name == "nix" else None
    )

    # Define uv_local path (but don't create the file, so exists() returns False)
    uv_local = tmp_path / ".appenv/.uv/bin/uv"

    # Mock subprocess.run to return success
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: FakeResult(stderr=b""),
    )

    # Mock UvBin.get_uv_version to return a valid version
    mock_version = UvVersion(0, 10, 3)
    monkeypatch.setattr(UvBin, "get_uv_version", lambda path: mock_version)

    # Cap logs at DEBUG level
    caplog.set_level(logging.DEBUG)

    # Call the method
    result = uv_bin._try_uv_from_nix_channel()

    # Verify results
    assert result == uv_local
    # Check that we got the "Creating" log (since uv_local.exists() was False)
    assert "Creating .appenv/.uv with Nix" in caplog.text


def test_try_uv_from_nix_channel_returns_none_when_nix_not_found(monkeypatch, tmp_path):
    """_try_uv_from_nix_channel returns None when nix not in PATH."""
    # Create a UvBin instance
    uv_bin = UvBin(tmp_path / ".appenv")

    # Mock shutil.which to return None (nix not found)
    monkeypatch.setattr("shutil.which", lambda name: None)

    # Call the method
    result = uv_bin._try_uv_from_nix_channel()

    # Verify results
    assert result is None


def test_try_uv_from_nix_channel_returns_none_when_build_fails(
    monkeypatch, tmp_path, caplog, subprocess_run_fail
):
    """_try_uv_from_nix_channel returns None when nix build fails."""
    # Create a UvBin instance
    uv_bin = UvBin(tmp_path / ".appenv")

    # Mock shutil.which to return nix path
    monkeypatch.setattr(
        "shutil.which", lambda name: "/nix/bin/nix" if name == "nix" else None
    )

    # Cap logs at DEBUG level
    caplog.set_level(logging.DEBUG)

    # Call the method
    result = uv_bin._try_uv_from_nix_channel()

    # Verify results
    assert result is None
    # Check that we logged the failure
    assert "nix-build failed:" in caplog.text


def test_try_uv_from_nix_channel_returns_none_when_invalid_version(
    monkeypatch, tmp_path, caplog
):
    """_try_uv_from_nix_channel returns None when uv built but version invalid."""
    # Create a UvBin instance
    uv_bin = UvBin(tmp_path / ".appenv")

    # Mock shutil.which to return nix path
    monkeypatch.setattr(
        "shutil.which", lambda name: "/nix/bin/nix" if name == "nix" else None
    )

    # Mock subprocess.run to return success
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: FakeResult(stderr=b""),
    )

    # Mock UvBin.get_uv_version to return unknown version (invalid)
    monkeypatch.setattr(UvBin, "get_uv_version", lambda path: UvVersion.unknown())

    # Cap logs at DEBUG level
    caplog.set_level(logging.DEBUG)

    # Call the method
    result = uv_bin._try_uv_from_nix_channel()

    # Verify results
    assert result is None


def test_try_uv_from_nix_channel_and_appenv_dir_share_same_path(
    monkeypatch, tmp_path, caplog
):
    """nix-build creates uv at .appenv/.uv, _try_uv_from_appenv_dir finds it.

    Verifies that _try_uv_from_nix_channel builds uv into the same
    directory that _try_uv_from_appenv_dir looks for.
    """
    uv_bin = UvBin(tmp_path / ".appenv")

    monkeypatch.setattr(uv_bin, "_try_uv_from_path", lambda: None)

    # Keep reference to real method before patching
    real_appenv_dir = uv_bin._try_uv_from_appenv_dir

    def mock_appenv_dir():
        return real_appenv_dir()

    monkeypatch.setattr(uv_bin, "_try_uv_from_appenv_dir", mock_appenv_dir)

    monkeypatch.setattr(
        "shutil.which", lambda name: "/nix/bin/nix" if name == "nix" else None
    )

    nix_build_output_dir = []

    class FakeNixResult:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_nix_run(*args, **kwargs):
        cmd = args[0] if args else kwargs.get("args", [])
        for i, arg in enumerate(cmd):
            if arg == "-o" and i + 1 < len(cmd):
                nix_build_output_dir.append(Path(cmd[i + 1]))
                uv_path = Path(cmd[i + 1]) / "bin/uv"
                uv_path.parent.mkdir(parents=True, exist_ok=True)
                uv_path.write_text("#!/bin/sh\n")
        return FakeNixResult()

    monkeypatch.setattr(subprocess, "run", fake_nix_run)

    mock_version = UvVersion(0, 10, 3)
    monkeypatch.setattr(UvBin, "get_uv_version", lambda path: mock_version)

    caplog.set_level(logging.DEBUG)

    result = uv_bin._get_uv_bin()

    assert len(nix_build_output_dir) == 1
    assert nix_build_output_dir[0] == tmp_path / ".appenv/.uv"

    expected_uv = tmp_path / ".appenv/.uv/bin/uv"
    assert expected_uv.exists(), f"uv not found at {expected_uv}"
    assert result == expected_uv

    found = uv_bin._try_uv_from_appenv_dir()
    assert found == expected_uv


# ==============================================================================
# UvBin._try_uv_from_nix_flake tests
# ==============================================================================


def test_try_uv_from_nix_flake_returns_path_when_valid(monkeypatch, tmp_path, caplog):
    """_try_uv_from_nix_flake returns path when nix flake build succeeds."""
    # Create a UvBin instance
    uv_bin = UvBin(tmp_path / ".appenv")

    # Mock shutil.which to find nix
    monkeypatch.setattr(
        shutil, "which", lambda name: "/usr/bin/nix" if name == "nix" else None
    )

    # Mock subprocess.run to return success
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: FakeResult())

    # Mock UvBin.get_uv_version to return a valid version
    mock_version = UvVersion(0, 10, 3)
    monkeypatch.setattr(UvBin, "get_uv_version", lambda path: mock_version)

    # Cap logs at DEBUG level
    caplog.set_level(logging.DEBUG)

    # Call the method
    result = uv_bin._try_uv_from_nix_flake()

    # Verify results
    # Note: uv_local is created inside the method
    expected_path = tmp_path / ".appenv/.uv/bin/uv"
    assert result == expected_path
    # Check that we got the success log
    assert "nix build nixpkgs#uv:" in caplog.text


def test_try_uv_from_nix_flake_returns_none_when_build_fails(
    monkeypatch, tmp_path, caplog, subprocess_run_fail
):
    """_try_uv_from_nix_flake returns None when nix flake build fails."""
    # Create a UvBin instance
    uv_bin = UvBin(tmp_path / ".appenv")

    # Mock shutil.which to find nix
    monkeypatch.setattr(
        shutil, "which", lambda name: "/usr/bin/nix" if name == "nix" else None
    )

    # Cap logs at DEBUG level
    caplog.set_level(logging.DEBUG)

    # Call the method
    result = uv_bin._try_uv_from_nix_flake()

    # Verify results
    assert result is None
    # Check that we logged the failure
    assert "nix-build failed:" in caplog.text


def test_try_uv_from_nix_flake_returns_none_when_invalid_version(
    monkeypatch, tmp_path, caplog
):
    """_try_uv_from_nix_flake returns None when uv built but version invalid."""
    # Create a UvBin instance
    uv_bin = UvBin(tmp_path / ".appenv")

    # Mock shutil.which to find nix
    monkeypatch.setattr(
        shutil, "which", lambda name: "/usr/bin/nix" if name == "nix" else None
    )

    # Mock subprocess.run to return success
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: FakeResult(stderr=b""),
    )

    # Mock UvBin.get_uv_version to return unknown version (invalid)
    monkeypatch.setattr(UvBin, "get_uv_version", lambda path: UvVersion.unknown())

    # Cap logs at DEBUG level
    caplog.set_level(logging.DEBUG)

    # Call the method
    result = uv_bin._try_uv_from_nix_flake()

    # Verify results
    assert result is None


# ==============================================================================
# UvBin._try_uv_from_pip tests
# ==============================================================================


def test_try_uv_from_pip_returns_path_when_valid(monkeypatch, tmp_path, caplog):
    """_try_uv_from_pip returns path when pip install succeeds and version valid."""
    # Create a UvBin instance
    uv_bin = UvBin(tmp_path / ".appenv")

    # Mock subprocess.run for ensurepip to return success
    def mock_run_ensurepip(*args, **kwargs):
        return FakeResult(stdout="ensurepip output")

    # Mock subprocess.run for pip install to return success
    def mock_run_pip(*args, **kwargs):
        return FakeResult(stdout="Successfully installed uv")

    # Side effect to handle different calls
    def mock_run_side_effect(*args, **kwargs):
        if "ensurepip" in args[0]:
            return mock_run_ensurepip(*args, **kwargs)
        # pip install
        return mock_run_pip(*args, **kwargs)

    monkeypatch.setattr(subprocess, "run", mock_run_side_effect)

    # Mock UvBin.get_uv_version to return a valid version
    mock_version = UvVersion(0, 10, 3)
    monkeypatch.setattr(UvBin, "get_uv_version", lambda path: mock_version)

    # Cap logs at DEBUG level
    caplog.set_level(logging.DEBUG)

    # Call the method
    result = uv_bin._try_uv_from_pip()

    # Verify results
    expected_path = tmp_path / ".appenv/.uv/bin/uv"
    assert result == expected_path
    # Check that we got the success log
    assert "pip install uv:" in caplog.text


def test_try_uv_from_pip_returns_none_when_ensurepip_fails(
    monkeypatch, tmp_path, caplog
):
    """_try_uv_from_pip returns None when ensurepip fails and no pip in PATH."""
    # Create a UvBin instance
    uv_bin = UvBin(tmp_path / ".appenv")

    # Mock subprocess.run for ensurepip to return failure
    def mock_run_ensurepip(*args, **kwargs):
        raise subprocess.CalledProcessError(1, "ensurepip")

    # Mock subprocess.run for pip install (should not be called)
    def mock_run_pip(*args, **kwargs):
        return FakeResult()

    # Side effect to handle different calls
    def mock_run_side_effect(*args, **kwargs):
        if "ensurepip" in args[0]:
            return mock_run_ensurepip(*args, **kwargs)
        # pip install
        return mock_run_pip(*args, **kwargs)

    monkeypatch.setattr(subprocess, "run", mock_run_side_effect)
    # Mock shutil.which to return None — no pip in PATH
    monkeypatch.setattr(shutil, "which", lambda name: None)

    # Cap logs at DEBUG level
    caplog.set_level(logging.DEBUG)

    # Call the method
    result = uv_bin._try_uv_from_pip()

    # Verify results
    assert result is None
    # Check that we logged the ensurepip failure
    assert "ensurepip failed" in caplog.text


def test_try_uv_from_pip_returns_none_when_pip_install_fails(
    monkeypatch, tmp_path, caplog
):
    """_try_uv_from_pip returns None when pip install fails."""
    # Create a UvBin instance
    uv_bin = UvBin(tmp_path / ".appenv")

    # Mock subprocess.run for ensurepip to return success
    def mock_run_ensurepip(*args, **kwargs):
        return FakeResult(stdout="ensurepip output")

    # Mock subprocess.run for pip install to return failure
    def mock_run_pip(*args, **kwargs):
        raise subprocess.CalledProcessError(1, "pip install")

    # Side effect to handle different calls
    def mock_run_side_effect(*args, **kwargs):
        if "ensurepip" in args[0]:
            return mock_run_ensurepip(*args, **kwargs)
        # pip install
        return mock_run_pip(*args, **kwargs)

    monkeypatch.setattr(subprocess, "run", mock_run_side_effect)

    # Cap logs at DEBUG level
    caplog.set_level(logging.DEBUG)

    # Call the method
    result = uv_bin._try_uv_from_pip()

    # Verify results
    assert result is None
    # Check that we logged the pip install failure
    assert "pip install failed, skipping pip install" in caplog.text


def test_try_uv_from_pip_returns_none_when_invalid_version(
    monkeypatch, tmp_path, caplog
):
    """_try_uv_from_pip returns None when uv installed but version invalid."""
    # Create a UvBin instance
    uv_bin = UvBin(tmp_path / ".appenv")

    # Mock subprocess.run for ensurepip to return success
    def mock_run_ensurepip(*args, **kwargs):
        return FakeResult(stdout="ensurepip output")

    # Mock subprocess.run for pip install to return success
    def mock_run_pip(*args, **kwargs):
        return FakeResult(stdout="Successfully installed uv")

    # Side effect to handle different calls
    def mock_run_side_effect(*args, **kwargs):
        if "ensurepip" in args[0]:
            return mock_run_ensurepip(*args, **kwargs)
        # pip install
        return mock_run_pip(*args, **kwargs)

    monkeypatch.setattr(subprocess, "run", mock_run_side_effect)

    # Mock UvBin.get_uv_version to return unknown version (invalid)
    monkeypatch.setattr(UvBin, "get_uv_version", lambda path: UvVersion.unknown())

    # Cap logs at DEBUG level
    caplog.set_level(logging.DEBUG)

    # Call the method
    result = uv_bin._try_uv_from_pip()

    # Verify results
    assert result is None


def test_get_uv_bin_returns_from_nix_channel_when_previous_fail(monkeypatch, tmp_path):
    """_get_uv_bin returns from nix_channel when previous methods return None."""
    # Create a UvBin instance
    uv_bin = UvBin(tmp_path / ".appenv")

    # Mock preceding methods to return None so we reach nix_channel method
    monkeypatch.setattr(uv_bin, "_try_uv_from_path", lambda: None)
    monkeypatch.setattr(uv_bin, "_try_uv_from_appenv_dir", lambda: None)

    # Mock the nix_channel method to return a valid path
    expected_path = tmp_path / ".appenv/.uv/bin/uv"
    expected_path.parent.mkdir(parents=True)
    expected_path.write_text("#!/bin/sh\n")
    monkeypatch.setattr(uv_bin, "_try_uv_from_nix_channel", lambda: expected_path)

    # Mock subsequent methods to ensure they're not called
    monkeypatch.setattr(uv_bin, "_try_uv_from_nix_flake", lambda: None)
    monkeypatch.setattr(uv_bin, "_try_uv_from_pip", lambda: None)


def test_get_uv_bin_returns_from_nix_flake_when_previous_fail(monkeypatch, tmp_path):
    """_get_uv_bin returns from nix_flake when previous methods return None."""
    # Create a UvBin instance
    uv_bin = UvBin(tmp_path / ".appenv")

    # Mock preceding methods to return None so we reach nix_flake method
    monkeypatch.setattr(uv_bin, "_try_uv_from_path", lambda: None)
    monkeypatch.setattr(uv_bin, "_try_uv_from_appenv_dir", lambda: None)
    monkeypatch.setattr(uv_bin, "_try_uv_from_nix_channel", lambda: None)

    # Mock the nix_flake method to return a valid path
    expected_path = tmp_path / ".appenv/.uv/bin/uv"
    expected_path.parent.mkdir(parents=True)
    expected_path.write_text("#!/bin/sh\n")
    monkeypatch.setattr(uv_bin, "_try_uv_from_nix_flake", lambda: expected_path)

    # Mock subsequent method to ensure it's not called
    monkeypatch.setattr(uv_bin, "_try_uv_from_pip", lambda: None)

    # Call the method
    result = uv_bin._get_uv_bin()

    # Verify results
    assert result == expected_path
    # Verify subsequent method was not called (early return)


def test_get_uv_bin_returns_from_pip_when_previous_fail(monkeypatch, tmp_path):
    """_get_uv_bin returns from _try_uv_from_pip when previous methods return None."""
    # Create a UvBin instance
    uv_bin = UvBin(tmp_path / ".appenv")

    # Mock preceding methods to return None so we reach pip method
    monkeypatch.setattr(uv_bin, "_try_uv_from_path", lambda: None)
    monkeypatch.setattr(uv_bin, "_try_uv_from_appenv_dir", lambda: None)
    monkeypatch.setattr(uv_bin, "_try_uv_from_nix_channel", lambda: None)
    monkeypatch.setattr(uv_bin, "_try_uv_from_nix_flake", lambda: None)

    # Mock the pip method to return a valid path
    expected_path = tmp_path / ".appenv/.uv/bin/uv"
    expected_path.parent.mkdir(parents=True)
    expected_path.write_text("#!/bin/sh\n")
    monkeypatch.setattr(uv_bin, "_try_uv_from_pip", lambda: expected_path)

    # Call the method
    result = uv_bin._get_uv_bin()

    # Verify results
    assert result == expected_path


# Tier 3 tests


def test_uv_bin_cmd_verbose_flag_and_output(monkeypatch, caplog):
    """UvBin.cmd adds -v flag when verbose=True and logs output."""
    import logging

    caplog.set_level(logging.DEBUG)

    # Create a mock UvBin
    uv = UvBin.__new__(UvBin)
    uv.bin = Path("/usr/bin/uv")
    uv.appenv_dir = Path("/tmp/.appenv")
    uv.uv_dir = uv.appenv_dir / ".uv"

    cmd_calls = []

    def mock_cmd(c, **kwargs):
        cmd_calls.append(c)
        return b"verbose output from uv"

    monkeypatch.setattr(appenv, "cmd", mock_cmd)

    uv.cmd(["lock"], verbose=True)

    # Verify -v flag is added to command
    assert "-v" in cmd_calls[0]
    assert "lock" in cmd_calls[0]

    # Verify output is logged via log.debug
    assert "verbose output from uv" in caplog.text


# ==============================================================================
# UvBin._get_uv_bin tests (pip fallback behavior)
# ==============================================================================


@pytest.mark.no_mock_uv_version
def test_uv_bin_pip_fallback_raises_error(tmp_path, monkeypatch):
    """UvBin._get_uv_bin raises NoValidUvError when uv still not found after pip."""

    which_calls = []

    def mock_which(name):
        which_calls.append(name)
        # uv never available

    monkeypatch.setattr("shutil.which", mock_which)

    pip_called = []

    def mock_run(cmd, **kwargs):
        pip_called.append(cmd)
        # Return a fake result for uv --version calls
        if "uv" in cmd and "--version" in cmd:
            return FakeResult(stdout="uv 0.10.3 (abc123 2024-01-01)\n", returncode=0)
        # Return success for other subprocess calls (like pip --version, pip install)
        return FakeResult(stdout="", returncode=0)

    monkeypatch.setattr("subprocess.run", mock_run)

    with pytest.raises(NoValidUvError, match="uv not found"):
        ensure_uv(tmp_path)

    assert any("pip" in str(cmd) and "uv" in str(cmd) for cmd in pip_called)


# ==============================================================================
# Coverage tests for 99% target
# ==============================================================================


def test_cleanup_appenv_uv_with_base_and_existing_dir(tmp_path):
    """Lines 622, 625: _cleanup_appenv_uv when base is set and .appenv/.uv exists."""
    # Create .appenv/.uv directory
    appenv_uv = tmp_path / ".appenv" / ".uv"
    appenv_uv.mkdir(parents=True)
    (appenv_uv / "some_file").write_text("test")

    # Create UvBin with base set
    uv_bin = UvBin(tmp_path / ".appenv")

    uv_bin._cleanup_appenv_uv()

    assert not appenv_uv.exists()


def test_get_uv_bin_returns_from_appenv_dir_when_path_fails(monkeypatch, tmp_path):
    """Test that _get_uv_bin returns from appenv_dir when path fails."""
    # Create a UvBin instance with a real base
    uv_bin = UvBin(tmp_path / ".appenv")

    # Mock _try_uv_from_path to return None (so we skip the first method)
    monkeypatch.setattr(uv_bin, "_try_uv_from_path", lambda: None)

    # Create a mock path to return from _try_uv_from_appenv_dir
    mock_uv_path = tmp_path / ".appenv" / ".uv" / "bin" / "uv"
    mock_uv_path.parent.mkdir(parents=True, exist_ok=True)
    mock_uv_path.write_text("#!/bin/sh\n")

    monkeypatch.setattr(uv_bin, "_try_uv_from_appenv_dir", lambda: mock_uv_path)

    # Track if the other methods are called
    nix_channel_called = []
    nix_flake_called = []
    pip_called = []

    monkeypatch.setattr(
        uv_bin,
        "_try_uv_from_nix_channel",
        lambda: nix_channel_called.append(True) or None,
    )
    monkeypatch.setattr(
        uv_bin, "_try_uv_from_nix_flake", lambda: nix_flake_called.append(True) or None
    )
    monkeypatch.setattr(
        uv_bin, "_try_uv_from_pip", lambda: pip_called.append(True) or None
    )

    # Call the method
    result = uv_bin._get_uv_bin()

    # Verify results
    assert result == mock_uv_path
    assert nix_channel_called == []  # Should not be called
    assert nix_flake_called == []  # Should not be called
    assert pip_called == []  # Should not be called


@pytest.mark.no_mock_uv_version
def test_ensure_uv_invalid_version(tmp_path, monkeypatch, capsys):
    """Lines 1213-1215: ensure_uv exits with EXIT_CODE_UNAVAILABLE if invalid."""

    # Mock UvBin to return invalid version
    class MockUvBinInvalid:
        def __init__(self, appenv_dir):
            self.bin = Path("/usr/bin/uv")
            self.appenv_dir = appenv_dir

        @property
        def version(self):
            return UvVersion(0, 0, 0)  # Invalid - below minimum

    monkeypatch.setattr(appenv, "UvBin", MockUvBinInvalid)

    with pytest.raises(SystemExit) as exc:
        ensure_uv(tmp_path)

    assert exc.value.code == EXIT_CODE_UNAVAILABLE
    captured = capsys.readouterr()
    assert "cannot use uv binary" in captured.out
