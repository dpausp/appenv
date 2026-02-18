import os

import pytest


@pytest.fixture
def workdir(tmpdir):
    # Handle case where previous test removed current directory
    try:
        old = os.getcwd()
    except OSError:
        old = str(tmpdir)
    os.chdir(str(tmpdir))
    yield str(tmpdir)
    try:
        os.chdir(old)
    except OSError:
        # If old directory no longer exists, use tmpdir
        os.chdir(str(tmpdir))
