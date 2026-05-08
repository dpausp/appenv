from collections.abc import Callable
from pathlib import Path

from pytest import CaptureFixture, MonkeyPatch

from appenv import AppEnvSettings

def test_self_update_updates_on_version_mismatch(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    capsys: CaptureFixture[str],
    test_settings: Callable[..., AppEnvSettings],
) -> None: ...
def test_self_update_noop_on_same_version(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    capsys: CaptureFixture[str],
    test_settings: Callable[..., AppEnvSettings],
) -> None: ...
def test_self_update_check_no_drift(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    capsys: CaptureFixture[str],
    test_settings: Callable[..., AppEnvSettings],
) -> None: ...
def test_self_update_check_detects_drift(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    capsys: CaptureFixture[str],
    test_settings: Callable[..., AppEnvSettings],
) -> None: ...
def test_self_update_no_script(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    test_settings: Callable[..., AppEnvSettings],
) -> None: ...
def test_self_update_unknown_version(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    capsys: CaptureFixture[str],
    test_settings: Callable[..., AppEnvSettings],
) -> None: ...
