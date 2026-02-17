"""Test version consistency across sources."""

import re
import subprocess
from importlib.metadata import version as get_metadata_version
from pathlib import Path


def get_source_version():
    """Get version from src/appenv.py __version__."""
    appenv_py = Path(__file__).parent.parent / "src" / "appenv.py"
    content = appenv_py.read_text()
    match = re.search(r'^__version__\s*=\s*"([^"]+)"', content, re.MULTILINE)
    if not match:
        raise ValueError("Could not find __version__ in src/appenv.py")
    return match.group(1)


def get_appenv_version():
    """Get version from ./appenv version command."""
    result = subprocess.run(
        ["./appenv", "version"],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent.parent,
    )
    # Output is "appenv X.Y.Z"
    return result.stdout.strip().split()[-1]


def test_version_consistency():
    """Ensure __version__, importlib.metadata and ./appenv version match."""
    source_version = get_source_version()
    metadata_version = get_metadata_version("appenv")
    appenv_version = get_appenv_version()

    assert source_version == metadata_version == appenv_version, (
        f"Version mismatch: __version__={source_version}, "
        f"metadata={metadata_version}, appenv={appenv_version}"
    )
