"""Integration tests using subprocess for real appenv execution.

These tests exercise the full __main__ flow and venv creation.
"""

import shutil
import subprocess
import sys
from pathlib import Path

import pytest


def setup_test_project(tmp_path: Path, app_name: str = "mycmd") -> Path:
    """Create a test project with pyproject.toml and appenv script as app_name."""
    import appenv

    base = tmp_path / "project"
    base.mkdir()

    # Copy appenv as the application name (e.g., "mycmd")
    src_appenv = Path(appenv.__file__).resolve()
    dst_appenv = base / app_name
    shutil.copy(src_appenv, dst_appenv)
    dst_appenv.chmod(0o755)

    # Create a minimal package with a simple CLI
    pkg_dir = base / "mypkg"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text("")
    (pkg_dir / "cli.py").write_text("""
import sys
def main():
    if "--help" in sys.argv:
        print("My CLI - help")
        return 0
    if "--version" in sys.argv:
        print("1.0.0")
        return 0
    print("Hello from my CLI")
    return 0

if __name__ == "__main__":
    sys.exit(main())
""")

    # Create pyproject.toml with the package and console script
    pyproject_content = f"""
[build-system]
requires = ["setuptools>=61.0"]
build-backend = "setuptools.build_meta"

[project]
name = "test-app"
version = "0.1.0"
description = "Test application"
dependencies = []
requires-python = ">=3.10"

[project.scripts]
{app_name} = "mypkg.cli:main"

[tool.setuptools.packages.find]
where = ["."]
"""
    (base / "pyproject.toml").write_text(pyproject_content)

    return base


@pytest.mark.slow(reason="Creates real venv with uv, takes ~10 seconds")
def test_subprocess_main_flow(tmp_path):
    """Integration test: Run appenv via subprocess to cover __main__ and venv creation.

    This exercises:
    - Line 1444: if __name__ == "__main__": main()
    - Branch 1148->1154: _prepare_venv when venv doesn't exist
    - Branch 1177->1180: _prepare_venv when 'current' already exists
    """
    base = setup_test_project(tmp_path, "mycmd")

    # Also copy appenv as "appenv" for lockfile generation
    import appenv

    src_appenv = Path(appenv.__file__).resolve()
    appenv_script = base / "appenv"
    shutil.copy(src_appenv, appenv_script)
    appenv_script.chmod(0o755)

    # First: generate lockfile via appenv update-lockfile
    result_lock = subprocess.run(
        [sys.executable, str(appenv_script), "update-lockfile"],
        capture_output=True,
        text=True,
        cwd=str(base),
        timeout=60,
    )
    assert result_lock.returncode == 0, f"Lockfile failed: {result_lock.stderr}"
    assert (base / "uv.lock").exists()

    # First call: creates venv from scratch
    result1 = subprocess.run(
        [sys.executable, str(base / "mycmd"), "--help"],
        capture_output=True,
        text=True,
        cwd=str(base),
        timeout=60,
    )

    # mycmd --help should succeed
    assert result1.returncode == 0
    assert "My CLI" in result1.stdout

    # Verify venv was created
    venv_dir = base / ".appenv" / "venv"
    assert venv_dir.exists()
    current_link = base / ".appenv" / "current"
    assert current_link.exists()
    assert current_link.is_symlink()

    # Second call: reuses existing venv (covers branch when current exists)
    result2 = subprocess.run(
        [sys.executable, str(base / "mycmd"), "--version"],
        capture_output=True,
        text=True,
        cwd=str(base),
        timeout=30,
    )

    # Should still work
    assert result2.returncode == 0
