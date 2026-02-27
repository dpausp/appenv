"""Type stubs for test fixtures."""

from collections.abc import Generator
from pathlib import Path

import pytest

@pytest.fixture
def workdir(tmp_path: Path) -> Generator[Path]: ...
