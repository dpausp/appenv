"""Tests for self-update command."""

import argparse
from pathlib import Path

import pytest

import appenv


def test_self_update_updates_on_version_mismatch(
    tmp_path, monkeypatch, capsys, test_settings
):
    """self-update replaces ./appenv when its version differs."""
    monkeypatch.chdir(tmp_path)
    base = tmp_path

    # Create an "old" appenv script with a different version
    old_script = base / "appenv"
    old_script.write_text(
        '#!/usr/bin/env python3\n__version__ = "0.0.1"\nprint("old")\n'
    )
    old_script.chmod(0o755)

    env = appenv.AppEnv(Path.cwd(), test_settings(Path.cwd()))
    env.self_update()

    captured = capsys.readouterr()
    assert "Updated" in captured.out
    assert "0.0.1" in captured.out
    assert appenv.__version__ in captured.out

    # The script should now contain the current version
    new_content = old_script.read_text()
    assert appenv.__version__ in new_content
    assert "0.0.1" not in new_content


def test_self_update_noop_on_same_version(tmp_path, monkeypatch, capsys, test_settings):
    """self-update does nothing when versions already match."""
    monkeypatch.chdir(tmp_path)
    base = tmp_path

    current_script = base / "appenv"
    current_script.write_text(
        f"#!/usr/bin/env python3\n"
        f'__version__ = "{appenv.__version__}"\n'
        f'print("current")\n'
    )
    current_script.chmod(0o755)
    original_mtime = current_script.stat().st_mtime

    env = appenv.AppEnv(Path.cwd(), test_settings(Path.cwd()))
    env.self_update()

    captured = capsys.readouterr()
    assert "already up-to-date" in captured.out

    # File should be untouched
    assert current_script.stat().st_mtime == original_mtime


def test_self_update_check_no_drift(tmp_path, monkeypatch, capsys, test_settings):
    """self-update --check exits 0 when versions match."""
    monkeypatch.chdir(tmp_path)
    base = tmp_path

    current_script = base / "appenv"
    current_script.write_text(
        f'#!/usr/bin/env python3\n__version__ = "{appenv.__version__}"\n'
    )
    current_script.chmod(0o755)

    env = appenv.AppEnv(Path.cwd(), test_settings(Path.cwd()))

    args = argparse.Namespace(check=True)
    with pytest.raises(SystemExit) as exc_info:
        env.self_update(args)

    assert exc_info.value.code == 0


def test_self_update_check_detects_drift(tmp_path, monkeypatch, capsys, test_settings):
    """self-update --check exits 1 when versions differ."""
    monkeypatch.chdir(tmp_path)
    base = tmp_path

    old_script = base / "appenv"
    old_script.write_text('#!/usr/bin/env python3\n__version__ = "0.0.1"\n')
    old_script.chmod(0o755)

    env = appenv.AppEnv(Path.cwd(), test_settings(Path.cwd()))

    args = argparse.Namespace(check=True)

    with pytest.raises(SystemExit) as exc_info:
        env.self_update(args)

    assert exc_info.value.code == 1

    captured = capsys.readouterr()
    assert "Version drift detected" in captured.out
    assert "0.0.1" in captured.out
    assert appenv.__version__ in captured.out

    # File should NOT be modified
    assert old_script.read_text().startswith("#!/usr/bin/env python3")
    assert '__version__ = "0.0.1"' in old_script.read_text()


def test_self_update_no_script(tmp_path, monkeypatch, test_settings):
    """self-update exits with NOINPUT when no appenv script exists."""
    monkeypatch.chdir(tmp_path)

    env = appenv.AppEnv(Path.cwd(), test_settings(Path.cwd()))

    with pytest.raises(SystemExit) as exc_info:
        env.self_update()

    assert exc_info.value.code == 67  # EXIT_CODE_NOINPUT


def test_self_update_unknown_version(tmp_path, monkeypatch, capsys, test_settings):
    """self-update handles scripts without __version__."""
    monkeypatch.chdir(tmp_path)
    base = tmp_path

    old_script = base / "appenv"
    old_script.write_text("#!/usr/bin/env python3\nprint('old')\n")
    old_script.chmod(0o755)

    env = appenv.AppEnv(Path.cwd(), test_settings(Path.cwd()))
    env.self_update()

    captured = capsys.readouterr()
    assert "Updated" in captured.out
    assert "unknown" in captured.out
    assert appenv.__version__ in captured.out

    # The script should now contain the current version
    new_content = old_script.read_text()
    assert appenv.__version__ in new_content


def test_self_update_with_explicit_dot_path(
    tmp_path, monkeypatch, capsys, test_settings
):
    """self-update . updates the appenv script in the specified directory."""
    monkeypatch.chdir(tmp_path)
    base = tmp_path

    # Create an old appenv script
    old_script = base / "appenv"
    old_script.write_text(
        '#!/usr/bin/env python3\n__version__ = "0.0.1"\nprint("old")\n'
    )
    old_script.chmod(0o755)

    env = appenv.AppEnv(Path.cwd(), test_settings(Path.cwd()))

    # Explicitly pass path as "."
    args = argparse.Namespace(check=False, path=".")
    env.self_update(args)

    captured = capsys.readouterr()
    assert "Updated" in captured.out
    assert "0.0.1" in captured.out
    assert appenv.__version__ in captured.out

    new_content = old_script.read_text()
    assert appenv.__version__ in new_content
    assert "0.0.1" not in new_content


def test_self_update_with_explicit_abs_path(
    tmp_path, monkeypatch, capsys, test_settings
):
    """self-update /some/path updates the appenv script in /some/path."""
    target_dir = tmp_path / "target"
    target_dir.mkdir()

    old_script = target_dir / "appenv"
    old_script.write_text(
        '#!/usr/bin/env python3\n__version__ = "0.0.1"\nprint("old")\n'
    )
    old_script.chmod(0o755)

    # Use a different basedir so it's not the same as target_dir
    monkeypatch.chdir(tmp_path)
    env = appenv.AppEnv(Path.cwd(), test_settings(Path.cwd()))

    args = argparse.Namespace(check=False, path=str(target_dir))
    env.self_update(args)

    captured = capsys.readouterr()
    assert "Updated" in captured.out

    new_content = old_script.read_text()
    assert appenv.__version__ in new_content
    assert "0.0.1" not in new_content


def test_self_update_externally_managed_no_path_no_basedir(
    tmp_path, monkeypatch, capsys
):
    """self-update without path and without APPENV_BASEDIR exits with USAGE."""
    monkeypatch.chdir(tmp_path)
    # Ensure APPENV_BASEDIR is not set
    monkeypatch.delenv("APPENV_BASEDIR", raising=False)

    # Create settings with basedir pointing to the package dir (simulating uvx)
    package_dir = Path(appenv.__file__).parent
    settings = appenv.AppEnvSettings(verbose=False, extras=[], basedir=package_dir)
    env = appenv.AppEnv(Path.cwd(), settings)

    with pytest.raises(SystemExit) as exc_info:
        env.self_update()

    assert exc_info.value.code == 64  # EXIT_CODE_USAGE
    captured = capsys.readouterr()
    assert "externally managed" in captured.out
    assert "HINT" in captured.out
    assert "appenv self-update ." in captured.out


def test_self_update_with_basedir_set(tmp_path, monkeypatch, capsys, test_settings):
    """self-update without path but WITH APPENV_BASEDIR uses existing behavior."""
    monkeypatch.chdir(tmp_path)
    base = tmp_path

    # Set APPENV_BASEDIR
    monkeypatch.setenv("APPENV_BASEDIR", str(base))

    old_script = base / "appenv"
    old_script.write_text(
        '#!/usr/bin/env python3\n__version__ = "0.0.1"\nprint("old")\n'
    )
    old_script.chmod(0o755)

    env = appenv.AppEnv(Path.cwd(), test_settings(Path.cwd()))
    env.self_update()

    captured = capsys.readouterr()
    assert "Updated" in captured.out
    assert "0.0.1" in captured.out
    assert appenv.__version__ in captured.out

    new_content = old_script.read_text()
    assert appenv.__version__ in new_content
    assert "0.0.1" not in new_content


def test_self_update_path_overrides_externally_managed(tmp_path, monkeypatch, capsys):
    """self-update . works even when running from externally managed env."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("APPENV_BASEDIR", raising=False)

    # Simulate externally managed (basedir = package dir)
    package_dir = Path(appenv.__file__).parent
    settings = appenv.AppEnvSettings(verbose=False, extras=[], basedir=package_dir)
    env = appenv.AppEnv(Path.cwd(), settings)

    # Create appenv script in cwd
    old_script = tmp_path / "appenv"
    old_script.write_text(
        '#!/usr/bin/env python3\n__version__ = "0.0.1"\nprint("old")\n'
    )
    old_script.chmod(0o755)

    # Explicit path overrides the externally-managed detection
    args = argparse.Namespace(check=False, path=".")
    env.self_update(args)

    captured = capsys.readouterr()
    assert "Updated" in captured.out

    new_content = old_script.read_text()
    assert appenv.__version__ in new_content
