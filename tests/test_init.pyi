from collections.abc import Callable
from pathlib import Path

from pytest import CaptureFixture, MonkeyPatch
from pytest_patterns.plugin import PatternsLib

from appenv import AppEnv

def test_init_fresh_start_interactive(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    capsys: CaptureFixture[str],
    app_env: Callable[..., AppEnv],
    patterns: PatternsLib,
) -> None: ...
def test_init_fresh_start_default_dependencies(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    capsys: CaptureFixture[str],
    app_env: Callable[..., AppEnv],
) -> None: ...
def test_init_empty_command_name_uses_app(
    workdir: Path,
    monkeypatch: MonkeyPatch,
    capsys: CaptureFixture[str],
    app_env: Callable[..., AppEnv],
) -> None: ...
def test_init_unlink_broken_symlink(
    workdir: Path,
    monkeypatch: MonkeyPatch,
    capsys: CaptureFixture[str],
    app_env: Callable[..., AppEnv],
) -> None: ...
def test_init_already_exists(
    workdir: Path,
    monkeypatch: MonkeyPatch,
    capsys: CaptureFixture[str],
    app_env: Callable[..., AppEnv],
) -> None: ...
def test_init_empty_command_name_defaults_to_app(
    workdir: Path,
    monkeypatch: MonkeyPatch,
    capsys: CaptureFixture[str],
    app_env: Callable[..., AppEnv],
) -> None: ...
def test_init_with_path_creates_directory(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    capsys: CaptureFixture[str],
    app_env: Callable[..., AppEnv],
) -> None: ...
def test_init_with_nested_path_creates_directories(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    capsys: CaptureFixture[str],
    app_env: Callable[..., AppEnv],
) -> None: ...
def test_init_with_existing_directory(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    capsys: CaptureFixture[str],
    app_env: Callable[..., AppEnv],
) -> None: ...
def test_init_without_path_uses_current_directory(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    capsys: CaptureFixture[str],
    app_env: Callable[..., AppEnv],
) -> None: ...
def test_init_appenv_script_already_exists(
    workdir: Path,
    monkeypatch: MonkeyPatch,
    capsys: CaptureFixture[str],
    app_env: Callable[..., AppEnv],
) -> None: ...
def test_init_warns_on_version_mismatch(
    workdir: Path,
    monkeypatch: MonkeyPatch,
    capsys: CaptureFixture[str],
    app_env: Callable[..., AppEnv],
) -> None: ...
def test_init_existing_pyproject_no_project_section(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    capsys: CaptureFixture[str],
    app_env: Callable[..., AppEnv],
) -> None: ...
