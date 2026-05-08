from pathlib import Path

import pytest

def setup_test_project(tmp_path: Path, app_name: str = ...) -> Path: ...
@pytest.mark.slow(reason="Creates real venv with uv, takes ~10 seconds")
def test_subprocess_main_flow(tmp_path: Path) -> None: ...
