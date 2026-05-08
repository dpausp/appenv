from collections.abc import Callable
from pathlib import Path

from pytest import CaptureFixture, MonkeyPatch

def test_ensure_best_python_skips_when_env_set(
    tmp_path: Path, monkeypatch: MonkeyPatch, make_pyproject: Callable[..., None]
) -> None: ...
def test_ensure_best_python_already_running_best(
    tmp_path: Path, monkeypatch: MonkeyPatch, make_pyproject: Callable[..., None]
) -> None: ...
def test_ensure_best_python_execv_with_correct_args(
    monkeypatch: MonkeyPatch, tmp_path: Path, make_pyproject: Callable[..., None]
) -> None: ...
def test_ensure_best_python_respects_upper_bound(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    capsys: CaptureFixture[str],
    make_pyproject: Callable[..., None],
) -> None: ...
def test_ensure_best_python_exits_65_no_python_found(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
    capsys: CaptureFixture[str],
    make_pyproject: Callable[..., None],
) -> None: ...
def test_ensure_best_python_exits_65_with_upper_bound(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
    capsys: CaptureFixture[str],
    make_pyproject: Callable[..., None],
) -> None: ...
def test_ensure_best_python_default_min_version(
    tmp_path: Path, monkeypatch: MonkeyPatch, make_pyproject: Callable[..., None]
) -> None: ...
def test_ensure_best_python_broken_python(
    tmp_path: Path, monkeypatch: MonkeyPatch, make_pyproject: Callable[..., None]
) -> None: ...
