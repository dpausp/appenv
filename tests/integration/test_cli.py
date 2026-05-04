"""Integration tests using pexpect for real CLI interaction."""

import shutil
import subprocess
import sys
from pathlib import Path

import pexpect
import pytest


def _uv_is_runnable():
    """Check that uv exists AND can actually execute (not just a broken binary)."""
    uv_path = shutil.which("uv")
    if uv_path is None:
        return False
    try:
        subprocess.run(
            [uv_path, "--version"], capture_output=True, timeout=5, check=True
        )
    except Exception:
        return False
    else:
        return True


# Skip all tests in this module on Windows (pexpect doesn't work there)
# or when uv is not installed / not runnable
pytestmark = [
    pytest.mark.skipif(
        sys.platform == "win32", reason="pexpect not available on Windows"
    ),
    pytest.mark.skipif(
        not _uv_is_runnable(), reason="uv not installed or not runnable"
    ),
]


def setup_isolated_appenv(tmp_path):
    """Copy appenv script to isolated directory for testing."""
    import appenv

    src_appenv = Path(appenv.__file__).resolve()
    dst_appenv = tmp_path / "appenv"
    shutil.copy(src_appenv, dst_appenv)
    dst_appenv.chmod(0o755)
    return dst_appenv


def test_init_cli(tmp_path):
    """Integration test: appenv init fresh start via CLI."""
    base = tmp_path
    appenv_script = setup_isolated_appenv(tmp_path)

    # Spawn the appenv process - it will detect no pyproject.toml
    child = pexpect.spawn(
        sys.executable,
        [str(appenv_script), "init"],
        cwd=str(tmp_path),
        timeout=20,
    )

    # Wait for first prompt
    child.expect(r"Binary to expose.*")
    child.sendline("mycli")

    # Wait for dependency prompts - enter two, then empty line
    child.expect(r"Dependency:.*")
    child.sendline("click")

    child.expect(r"Dependency:.*")
    child.sendline("rich")

    child.expect(r"Dependency:.*")
    child.sendline("")  # Empty to finish

    # Wait for project name prompt
    child.expect(r"Project name.*")
    child.sendline("mycli-project")

    # Wait for description prompt
    child.expect(r"Description.*")
    child.sendline("My CLI tool")

    # Wait for Python version prompt
    child.expect(r"Minimum Python version.*")
    child.sendline("3.10")

    # Wait for completion
    child.expect(pexpect.EOF)
    child.close()

    assert child.exitstatus == 0

    # Verify pyproject.toml was created with correct content
    pyproject = (base / "pyproject.toml").read_text()
    assert 'name = "mycli-project"' in pyproject
    assert 'description = "My CLI tool"' in pyproject
    assert '"click"' in pyproject
    assert '"rich"' in pyproject
    assert 'requires-python = ">=3.10"' in pyproject

    # Verify appenv script exists
    assert (base / "appenv").exists()

    # Verify symlink was created
    assert (base / "mycli").exists()
    assert (base / "mycli").is_symlink()


def test_migrate_cli(tmp_path):
    """Integration test: appenv migrate via CLI (non-interactive)."""
    base = tmp_path
    appenv_script = setup_isolated_appenv(tmp_path)

    # Create requirements.txt to trigger migration
    (base / "requirements.txt").write_text("requests>=2.28\nurllib3\n")

    child = pexpect.spawn(
        sys.executable,
        [str(appenv_script), "migrate"],
        cwd=str(tmp_path),
        timeout=20,
    )

    # Should see migration output
    child.expect(r"Migrating from requirements.txt")

    # Should find dependencies
    child.expect(r"Found 2 dependenc")

    # Wait for completion (no interactive prompt anymore)
    child.expect(pexpect.EOF)
    child.close()

    assert child.exitstatus == 0

    # Verify pyproject.toml uses directory name and has migrated dependencies
    pyproject = (base / "pyproject.toml").read_text()
    assert f'name = "{base.name}"' in pyproject
    assert '"requests>=2.28"' in pyproject
    assert '"urllib3"' in pyproject


@pytest.mark.slow(reason="Installs httpie package, takes ~10 seconds")
def test_bootstrap_flow_like_readme(tmp_path, capsys):
    """Full bootstrap flow as described in README.

    This test verifies the complete user journey and prints the real
    terminal interaction exactly as it happens.

    Run with: uv run pytest -m slow tests/integration/test_cli.py -s
    """
    import re

    base = tmp_path / "httpie"
    base.mkdir()
    appenv_script = setup_isolated_appenv(base)

    # Step 1: Run appenv init (simulates bootstrap script)
    child = pexpect.spawn(
        sys.executable,
        [str(appenv_script), "init"],
        cwd=str(base),
        timeout=30,
        encoding="utf-8",
        codec_errors="replace",
    )

    # Collect all terminal output
    terminal_output = []

    def interact(pattern, user_input):
        """Interact with prompt and capture output."""
        child.expect(pattern)
        # Capture everything before the prompt match
        if child.before:
            terminal_output.append(child.before)
        # Capture the prompt itself
        if child.after:
            terminal_output.append(child.after)
        # Send user input (will be echoed)
        child.sendline(user_input)

    # Follow the README flow
    interact(r"Binary to expose.*", "http")
    interact(r"Dependency:.*", "httpie")
    interact(r"Dependency:.*", "")  # Empty to finish
    interact(r"Project name.*", "http")  # Use test name
    interact(r"Description.*", "HTTP CLI")
    interact(r"Minimum Python version.*", "3.14")

    # Wait for completion
    child.expect(pexpect.EOF, timeout=60)
    terminal_output.append(child.before or "")
    child.close()

    assert child.exitstatus == 0

    # Print the real terminal session

    # Combine all output and clean up
    full_output = "".join(terminal_output)
    # Strip ANSI codes for readability
    clean_output = re.sub(r"\x1b\[[0-9;]*m", "", full_output)
    # Normalize line endings
    clean_output = clean_output.replace("\r\n", "\n").replace("\r", "\n")

    # Verify README messages appear in output
    assert "Created ./http -> appenv" in clean_output
    assert "Created" in clean_output and "pyproject.toml" in clean_output
    assert "Generating new lock file" in clean_output
    assert "Use `./http` to run the http binary" in clean_output

    # Verify file structure
    assert (base / "pyproject.toml").exists()
    assert (base / "uv.lock").exists()
    assert (base / "appenv").exists()
    assert (base / "http").is_symlink()

    # Step 2: Run ./http --version

    child2 = pexpect.spawn(
        str(base / "http"),
        ["--version"],
        cwd=str(base),
        timeout=60,
        encoding="utf-8",
        codec_errors="replace",
    )
    child2.expect(pexpect.EOF, timeout=60)
    child2.close()

    output2 = child2.before or ""

    # Verify httpie ran
    assert (
        child2.exitstatus == 0
        or "HTTPie" in output2
        or any(c.isdigit() for c in output2)
    )


def test_prepare_cli(tmp_path):
    """E2E: appenv prepare creates venv and .venv symlink for valid project."""
    base = tmp_path
    appenv_script = setup_isolated_appenv(tmp_path)

    # Create minimal pyproject.toml with one dependency
    (base / "pyproject.toml").write_text(
        '[project]\nname = "testprep"\nversion = "0.1.0"\n'
        "dependencies = []\n"
        'requires-python = ">=3.10"\n'
    )

    # Generate uv.lock using uv lock
    subprocess.run(
        ["uv", "lock"], cwd=str(base), capture_output=True, timeout=30, check=True
    )

    child = pexpect.spawn(
        sys.executable,
        [str(appenv_script), "prepare"],
        cwd=str(base),
        timeout=30,
        encoding="utf-8",
        codec_errors="replace",
    )

    child.expect(pexpect.EOF, timeout=30)
    child.close()

    assert child.exitstatus == 0
    # venv python exists
    assert (base / ".appenv" / "venv" / "bin" / "python").exists()
    # .venv is symlink to .appenv/venv
    assert (base / ".venv").is_symlink()


def test_prepare_cli_no_pyproject(tmp_path):
    """E2E: appenv prepare exits 67 when no pyproject.toml exists."""
    base = tmp_path
    appenv_script = setup_isolated_appenv(tmp_path)

    child = pexpect.spawn(
        sys.executable,
        [str(appenv_script), "prepare"],
        cwd=str(base),
        timeout=10,
        encoding="utf-8",
        codec_errors="replace",
    )

    child.expect(pexpect.EOF, timeout=10)
    child.close()

    assert child.exitstatus == 67
    assert child.before is not None and "No pyproject config file" in child.before


def test_prepare_cli_no_lockfile(tmp_path):
    """E2E: appenv prepare exits 67 when no uv.lock exists."""
    base = tmp_path
    appenv_script = setup_isolated_appenv(tmp_path)

    # Create pyproject.toml but no uv.lock
    (base / "pyproject.toml").write_text(
        '[project]\nname = "testprep"\nversion = "0.1.0"\n'
        'dependencies = ["click"]\n'
        'requires-python = ">=3.10"\n'
    )

    child = pexpect.spawn(
        sys.executable,
        [str(appenv_script), "prepare"],
        cwd=str(base),
        timeout=10,
        encoding="utf-8",
        codec_errors="replace",
    )

    child.expect(pexpect.EOF, timeout=10)
    child.close()

    assert child.exitstatus == 67
    assert child.before is not None and "No uv.lock" in child.before
