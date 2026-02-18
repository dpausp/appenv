"""Integration tests using pexpect for real CLI interaction."""

import shutil
import sys
from pathlib import Path

import pexpect
import pytest

# Skip all tests in this module on Windows (pexpect doesn't work there)
pytestmark = pytest.mark.skipif(
    sys.platform == "win32", reason="pexpect not available on Windows"
)


def setup_isolated_appenv(tmpdir):
    """Copy appenv script to isolated directory for testing."""
    import appenv

    src_appenv = Path(appenv.__file__).resolve()
    dst_appenv = Path(tmpdir) / "appenv"
    shutil.copy(src_appenv, dst_appenv)
    dst_appenv.chmod(0o755)
    return dst_appenv


def test_init_pyproject_fresh_start_cli(tmpdir):
    """Integration test: appenv init-pyproject fresh start via CLI."""
    base = Path(tmpdir)
    appenv_script = setup_isolated_appenv(tmpdir)

    # Spawn the appenv process - it will detect no pyproject.toml
    child = pexpect.spawn(
        sys.executable,
        [str(appenv_script), "init-pyproject"],
        cwd=str(tmpdir),
        timeout=10,
    )

    # Wait for first prompt
    child.expect(r"What should the command be named\?.*")
    child.sendline("mycli")

    # Wait for description prompt
    child.expect(r"Description.*")
    child.sendline("My CLI tool")

    # Wait for dependency prompts - enter two, then empty line
    child.expect(r"Dependency:.*")
    child.sendline("click")

    child.expect(r"Dependency:.*")
    child.sendline("rich")

    child.expect(r"Dependency:.*")
    child.sendline("")  # Empty to finish

    # Wait for Python version prompt
    child.expect(r"Minimum Python version.*")
    child.sendline("3.10")

    # Wait for completion
    child.expect(pexpect.EOF)
    child.close()

    assert child.exitstatus == 0

    # Verify pyproject.toml was created with correct content
    pyproject = (base / "pyproject.toml").read_text()
    assert 'name = "mycli"' in pyproject
    assert 'description = "My CLI tool"' in pyproject
    assert '"click"' in pyproject
    assert '"rich"' in pyproject
    assert 'requires-python = ">=3.10"' in pyproject

    # Verify appenv script exists
    assert (base / "appenv").exists()

    # Verify symlink was created
    assert (base / "mycli").exists()
    assert (base / "mycli").is_symlink()


def test_init_pyproject_migration_cli(tmpdir):
    """Integration test: appenv init-pyproject migration via CLI."""
    base = Path(tmpdir)
    appenv_script = setup_isolated_appenv(tmpdir)

    # Create requirements.txt to trigger migration
    (base / "requirements.txt").write_text("requests>=2.28\nurllib3\n")

    child = pexpect.spawn(
        sys.executable,
        [str(appenv_script), "init-pyproject"],
        cwd=str(tmpdir),
        timeout=10,
    )

    # Should see migration output
    child.expect(r"Migrating from requirements.txt")

    # Should find dependencies
    child.expect(r"Found 2 dependenc")

    # Wait for project name prompt
    child.expect(r"Project name.*")
    child.sendline("migrated-app")

    # Wait for completion
    child.expect(pexpect.EOF)
    child.close()

    assert child.exitstatus == 0

    # Verify pyproject.toml has migrated dependencies
    pyproject = (base / "pyproject.toml").read_text()
    assert 'name = "migrated-app"' in pyproject
    assert '"requests>=2.28"' in pyproject
    assert '"urllib3"' in pyproject
