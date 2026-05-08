from pathlib import Path

import pytest
from pytest import CaptureFixture, LogCaptureFixture, MonkeyPatch

class FakeResult:
    returncode: int
    stdout: str
    stderr: str
    def __init__(
        self, returncode: int = ..., stdout: str = ..., stderr: str = ...
    ) -> None: ...

def test_uv_bin_cmd_raises_when_uv_not_found(monkeypatch: MonkeyPatch) -> None: ...
def test_try_uv_from_path_returns_path_when_valid(
    monkeypatch: MonkeyPatch, tmp_path: Path
) -> None: ...
def test_try_uv_from_path_returns_none_when_invalid_version(
    monkeypatch: MonkeyPatch,
) -> None: ...
def test_try_uv_from_path_returns_none_when_not_in_path(
    monkeypatch: MonkeyPatch,
) -> None: ...
@pytest.mark.no_mock_uv_version
def test_uv_binget_uv_version_returns_version_on_success(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None: ...
@pytest.mark.no_mock_uv_version
def test_uv_binget_uv_version_not_valid_on_subprocess_error(
    monkeypatch: MonkeyPatch, capsys: CaptureFixture[str]
) -> None: ...
@pytest.mark.no_mock_uv_version
def test_uv_binget_uv_version_returns_none_when_too_old(
    monkeypatch: MonkeyPatch, capsys: CaptureFixture[str]
) -> None: ...
@pytest.mark.no_mock_uv_version
def test_uv_binget_uv_version_handles_parse_error(
    tmp_path: Path, monkeypatch: MonkeyPatch, capsys: CaptureFixture[str]
) -> None: ...
@pytest.mark.no_mock_uv_version
def test_uv_binget_uv_version_index_error_on_split(
    monkeypatch: MonkeyPatch, capsys: CaptureFixture[str]
) -> None: ...
def test_try_uv_from_appenv_dir_returns_path_when_valid(
    monkeypatch: MonkeyPatch, tmp_path: Path
) -> None: ...
def test_try_uv_from_appenv_dir_returns_none_when_invalid_version(
    monkeypatch: MonkeyPatch, tmp_path: Path
) -> None: ...
def test_try_uv_from_appenv_dir_returns_none_when_not_exists(
    monkeypatch: MonkeyPatch, tmp_path: Path
) -> None: ...
def test_try_uv_from_nix_channel_returns_path_when_valid(
    monkeypatch: MonkeyPatch, tmp_path: Path, caplog: LogCaptureFixture
) -> None: ...
def test_try_uv_from_nix_channel_returns_path_when_created(
    monkeypatch: MonkeyPatch, tmp_path: Path, caplog: LogCaptureFixture
) -> None: ...
def test_try_uv_from_nix_channel_returns_none_when_nix_not_found(
    monkeypatch: MonkeyPatch, tmp_path: Path
) -> None: ...
def test_try_uv_from_nix_channel_returns_none_when_build_fails(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
    caplog: LogCaptureFixture,
    subprocess_run_fail: None,
) -> None: ...
def test_try_uv_from_nix_channel_returns_none_when_invalid_version(
    monkeypatch: MonkeyPatch, tmp_path: Path, caplog: LogCaptureFixture
) -> None: ...
def test_try_uv_from_nix_channel_and_appenv_dir_share_same_path(
    monkeypatch: MonkeyPatch, tmp_path: Path, caplog: LogCaptureFixture
) -> None: ...
def test_try_uv_from_nix_flake_returns_path_when_valid(
    monkeypatch: MonkeyPatch, tmp_path: Path, caplog: LogCaptureFixture
) -> None: ...
def test_try_uv_from_nix_flake_returns_none_when_build_fails(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
    caplog: LogCaptureFixture,
    subprocess_run_fail: None,
) -> None: ...
def test_try_uv_from_nix_flake_returns_none_when_invalid_version(
    monkeypatch: MonkeyPatch, tmp_path: Path, caplog: LogCaptureFixture
) -> None: ...
def test_try_uv_from_pip_returns_path_when_valid(
    monkeypatch: MonkeyPatch, tmp_path: Path, caplog: LogCaptureFixture
) -> None: ...
def test_try_uv_from_pip_returns_none_when_ensurepip_fails(
    monkeypatch: MonkeyPatch, tmp_path: Path, caplog: LogCaptureFixture
) -> None: ...
def test_try_uv_from_pip_returns_none_when_pip_install_fails(
    monkeypatch: MonkeyPatch, tmp_path: Path, caplog: LogCaptureFixture
) -> None: ...
def test_try_uv_from_pip_returns_none_when_invalid_version(
    monkeypatch: MonkeyPatch, tmp_path: Path, caplog: LogCaptureFixture
) -> None: ...
def test_get_uv_bin_returns_from_nix_channel_when_previous_fail(
    monkeypatch: MonkeyPatch, tmp_path: Path
) -> None: ...
def test_get_uv_bin_returns_from_nix_flake_when_previous_fail(
    monkeypatch: MonkeyPatch, tmp_path: Path
) -> None: ...
def test_get_uv_bin_returns_from_pip_when_previous_fail(
    monkeypatch: MonkeyPatch, tmp_path: Path
) -> None: ...
def test_uv_bin_cmd_verbose_flag_and_output(
    monkeypatch: MonkeyPatch, caplog: LogCaptureFixture
) -> None: ...
@pytest.mark.no_mock_uv_version
def test_uv_bin_pip_fallback_raises_error(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None: ...
def test_cleanup_appenv_uv_with_base_and_existing_dir(tmp_path: Path) -> None: ...
def test_get_uv_bin_returns_from_appenv_dir_when_path_fails(
    monkeypatch: MonkeyPatch, tmp_path: Path
) -> None: ...
@pytest.mark.no_mock_uv_version
def test_ensure_uv_invalid_version(
    tmp_path: Path, monkeypatch: MonkeyPatch, capsys: CaptureFixture[str]
) -> None: ...
