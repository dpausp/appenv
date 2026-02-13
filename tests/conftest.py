import os
import subprocess
from pathlib import Path

import pytest

import appenv
from appenv import UvVersion


@pytest.fixture(autouse=True)
def disable_argparse_colors(monkeypatch):
    """Disable argparse colors (Python 3.14+) for stable output assertions."""
    monkeypatch.setenv("NO_COLOR", "1")


@pytest.fixture
def workdir(tmp_path):
    """Change to tmp_path for test duration, restore afterwards."""
    # Handle case where previous test removed current directory
    try:
        old = os.getcwd()
    except OSError:
        old = str(tmp_path)
    os.chdir(tmp_path)
    yield tmp_path
    try:
        os.chdir(old)
    except OSError:
        # If old directory no longer exists, use tmp_path
        os.chdir(tmp_path)


def make_mock_uv():
    """Create a mock UvBin instance for testing.

    This helper creates a mock UvBin with stubbed methods that don't
    actually execute any subprocess commands.
    """

    class MockUvBin:
        def __init__(self):
            self.base = Path("/tmp")
            self.bin = Path("/usr/bin/uv")
            self._version = UvVersion(0, 5, 0)

        @property
        def version(self):
            return self._version

        def cmd(self, args, verbose=False, **kwargs):
            # Mock uv command - do nothing, return empty string
            return ""

    return MockUvBin()


@pytest.fixture(autouse=True)
def mock_uv_version(monkeypatch, request):
    """Auto-mock UvBin.get_uv_version to avoid subprocess calls in tests.

    Tests that mock ensure_uv to return a fake UvBin instance need get_uv_version
    to also be mocked, otherwise it tries to run the fake binary.

    Tests that directly test get_uv_version behavior can disable this
    by using the @pytest.mark.no_mock_uv_version decorator.
    """
    # Skip for tests that directly test get_uv_version
    if request.node.get_closest_marker("no_mock_uv_version"):
        return

    # Mock UvVersion to return a valid version
    mock_version = UvVersion(0, 5, 0)

    # Mock the get_uv_version method on UvBin class (static method)
    def mockget_uv_version(uv_path):
        return mock_version

    monkeypatch.setattr(appenv.UvBin, "get_uv_version", mockget_uv_version)


@pytest.fixture
def subprocess_run_fail(monkeypatch):
    def fail(*args, **kwargs):
        raise subprocess.CalledProcessError(
            returncode=1, cmd="test_cmd", stderr="test_stderr"
        )

    monkeypatch.setattr(subprocess, "run", fail)
