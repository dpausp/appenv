from collections.abc import Callable
from pathlib import Path

import pytest
from pytest import CaptureFixture, MonkeyPatch
from pytest_patterns.plugin import PatternsLib

from appenv import AppEnv

def test_migrate_uses_python_preference_from_requirements(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    capsys: CaptureFixture[str],
    app_env: Callable[..., AppEnv],
) -> None: ...
def test_migrate_existing_symlinks(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    capsys: CaptureFixture[str],
    app_env: Callable[..., AppEnv],
) -> None: ...
def test_migrate_empty_dependencies(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    capsys: CaptureFixture[str],
    app_env: Callable[..., AppEnv],
) -> None: ...
def test_migrate_uses_directory_name(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    capsys: CaptureFixture[str],
    app_env: Callable[..., AppEnv],
) -> None: ...
def test_migrate_already_exists(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    capsys: CaptureFixture[str],
    patterns: PatternsLib,
    app_env: Callable[..., AppEnv],
) -> None: ...
def test_migrate_no_requirements_txt(
    workdir: Path,
    monkeypatch: MonkeyPatch,
    capsys: CaptureFixture[str],
    patterns: PatternsLib,
    app_env: Callable[..., AppEnv],
) -> None: ...
def test_migrate_full_flow_pattern(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    capsys: CaptureFixture[str],
    patterns: PatternsLib,
    app_env: Callable[..., AppEnv],
    mock_uv_lock: None,
) -> None: ...
def test_migrate_editable_missing_package_warns(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    capsys: CaptureFixture[str],
    patterns: PatternsLib,
    app_env: Callable[..., AppEnv],
) -> None: ...
def test_migrate_editable_mixed_valid_and_invalid(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    capsys: CaptureFixture[str],
    patterns: PatternsLib,
    app_env: Callable[..., AppEnv],
) -> None: ...
@pytest.mark.parametrize("requirements,warning_pattern,regular_deps", ...)  # ty: ignore[invalid-argument-type]
def test_migrate_editable_unsupported_warns(
    requirements: str,
    warning_pattern: str,
    regular_deps: list[str],
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    capsys: CaptureFixture[str],
    patterns: PatternsLib,
    app_env: Callable[..., AppEnv],
) -> None: ...
def test_migrate_existing_pyproject_no_project_section(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    capsys: CaptureFixture[str],
    patterns: PatternsLib,
    app_env: Callable[..., AppEnv],
    mock_uv_lock: None,
) -> None: ...
def test_migrate_updates_appenv_script_on_version_mismatch(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    capsys: CaptureFixture[str],
    app_env: Callable[..., AppEnv],
    mock_uv_lock: None,
) -> None: ...
def test_migrate_skips_appenv_script_on_same_version(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    capsys: CaptureFixture[str],
    app_env: Callable[..., AppEnv],
    mock_uv_lock: None,
) -> None: ...
def test_migrate_updates_appenv_script_without_version(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    capsys: CaptureFixture[str],
    app_env: Callable[..., AppEnv],
    mock_uv_lock: None,
) -> None: ...
def test_migrate_with_path_argument(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    capsys: CaptureFixture[str],
    app_env: Callable[..., AppEnv],
    mock_uv_lock: None,
) -> None: ...
