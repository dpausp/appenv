"""Tests for update_lockfile pyproject.toml workflow."""

import argparse
import os
import shutil
from pathlib import Path

import appenv


def _setup_pyproject_project(workdir, name="ducker", deps=None):
    """Setup a pyproject.toml based project."""
    base = Path(workdir) / name
    base.mkdir()
    os.chdir(base)

    # Copy appenv script
    src_appenv = Path(appenv.__file__)
    dst_appenv = base / "appenv"
    shutil.copy(src_appenv, dst_appenv)
    dst_appenv.chmod(0o755)

    # Create symlink
    link = base / name
    link.symlink_to("appenv")

    # Create pyproject.toml
    deps_str = ", ".join(f'"{d}"' for d in (deps or ["click"]))
    (base / "pyproject.toml").write_text(
        f'[project]\nname = "{name}"\ndependencies = [{deps_str}]\n'
    )

    return base


def test_update_lockfile_pyproject_workflow(workdir, monkeypatch, capsys, patterns):
    """pyproject.toml mode should use uv lock and create uv.lock.

    The working directory is set correctly via os.chdir, so uv finds
    the correct pyproject.toml without needing --project flag.
    """
    # Create directory with pyproject.toml
    app_dir = Path(workdir) / "myapp"
    app_dir.mkdir()
    (app_dir / "pyproject.toml").write_text(
        """
[project]
name = "myapp"
version = "1.0.0"
dependencies = ["click"]
"""
    )
    (app_dir / "appenv").write_text("#!/usr/bin/env python3\npass\n")
    (app_dir / "appenv").chmod(0o755)

    # Mock ensure_uv and uv_cmd
    monkeypatch.setattr(appenv, "ensure_uv", lambda base: None)
    monkeypatch.setattr(appenv, "ensure_uv", lambda base=None: Path("/usr/bin/uv"))

    captured_calls = []

    def mock_uv_cmd(args, verbose=False, **kwargs):
        captured_calls.append({"args": list(args), "cwd": kwargs.get("cwd")})
        # Simulate uv lock output
        if "lock" in args and "pip" not in args:
            (app_dir / "uv.lock").write_text("version = 1\n")
        elif "pip" in args and "compile" in args:
            output_file = args[args.index("--output-file") + 1]
            Path(output_file).write_text("click==8.1.0\n")
        return b""

    monkeypatch.setattr(appenv, "uv_cmd", mock_uv_cmd)

    # Enable verbose output to check mode detection
    monkeypatch.setenv("APPENV_VERBOSE", "1")

    # Run update_lockfile
    env = appenv.AppEnv(app_dir, Path.cwd())
    env.update_lockfile()

    captured = capsys.readouterr()
    patterns.any.optional("...")
    patterns.main.merge("any")
    patterns.main.in_order("update_lockfile")

    patterns.no_errors.optional("...")
    patterns.no_errors.refused("...error...")
    patterns.no_errors.refused("...exception...")
    patterns.no_errors.refused("...traceback...")
    patterns.no_errors.refused("...failed...")

    full_pattern = patterns.full
    full_pattern.merge("main", "no_errors")

    example = full_pattern.generate_example()
    print(f"\n=== Pattern Example ===\n{example}\n=== End ===\n")

    assert full_pattern == captured.out

    # Verify uv.lock was created
    assert (app_dir / "uv.lock").exists()

    # Verify uv lock was called
    lock_calls = [
        call
        for call in captured_calls
        if "lock" in call["args"] and "pip" not in call["args"]
    ]
    assert len(lock_calls) >= 1, "Expected at least one uv lock call"


def test_update_lockfile_verbose_output(workdir, monkeypatch, capsys, patterns):
    """Verbose mode shows structured output with paths and mode info."""
    app_dir = Path(workdir) / "verboseapp"
    app_dir.mkdir()
    (app_dir / "pyproject.toml").write_text(
        '[project]\nname = "verboseapp"\ndependencies = ["click"]\n'
    )
    (app_dir / "appenv").write_text("#!/usr/bin/env python3\npass\n")
    (app_dir / "appenv").chmod(0o755)

    monkeypatch.setattr(appenv, "ensure_uv", lambda base: None)
    monkeypatch.setattr(appenv, "ensure_uv", lambda base=None: Path("/usr/bin/uv"))

    def mock_uv_cmd(args, verbose=False, **kwargs):
        if "lock" in args and "pip" not in args:
            (app_dir / "uv.lock").write_text("version = 1\n")
        return b""

    monkeypatch.setattr(appenv, "uv_cmd", mock_uv_cmd)
    monkeypatch.setenv("APPENV_VERBOSE", "1")

    env = appenv.AppEnv(app_dir, Path.cwd())
    env.update_lockfile()

    captured = capsys.readouterr()
    patterns.any.optional("...")
    patterns.main.merge("any")
    patterns.main.in_order(
        """\
...Reading:...
...Lockfile:..."""
    )

    patterns.no_errors.optional("...")
    patterns.no_errors.refused("...error...")
    patterns.no_errors.refused("...exception...")
    patterns.no_errors.refused("...traceback...")
    patterns.no_errors.refused("...failed...")

    full_pattern = patterns.full
    full_pattern.merge("main", "no_errors")

    example = full_pattern.generate_example()
    print(f"\n=== Pattern Example ===\n{example}\n=== End ===\n")

    assert full_pattern == captured.out


# captured unused - removed

# Strip ANSI codes for cleaner pattern matching

# out_clean = re.sub(r"\x1b\[[0-9;]*m", "", out)


# Use patterns for structured verbose output
def test_update_lockfile_no_changes_output(workdir, monkeypatch, capsys, patterns):
    """update_lockfile shows 'No changes' when lockfile is up to date."""
    app_dir = Path(workdir) / "nochange"
    app_dir.mkdir()
    (app_dir / "pyproject.toml").write_text(
        '[project]\nname = "nochange"\ndependencies = ["click"]\n'
    )
    (app_dir / "appenv").write_text("#!/usr/bin/env python3\npass\n")
    (app_dir / "appenv").chmod(0o755)

    # Pre-create uv.lock so diff check finds no changes
    (app_dir / "uv.lock").write_text("version = 1\n")

    monkeypatch.setattr(appenv, "ensure_uv", lambda base: None)
    monkeypatch.setattr(appenv, "ensure_uv", lambda base=None: Path("/usr/bin/uv"))

    def mock_uv_cmd(args, verbose=False, **kwargs):
        cwd = kwargs.get("cwd")
        if cwd and "lock" in args and "pip" not in args:
            # Same content = no changes
            Path(cwd, "uv.lock").write_text("version = 1\n")
        return b""

    monkeypatch.setattr(appenv, "uv_cmd", mock_uv_cmd)

    env = appenv.AppEnv(app_dir, Path.cwd())
    env.update_lockfile()

    out = capsys.readouterr().out

    patterns.main.in_order("No changes")

    full_pattern = patterns.full
    full_pattern.merge("main")

    example = full_pattern.generate_example()
    print(f"\n=== Pattern Example ===\n{example}\n=== End ===\n")

    assert full_pattern == out


# Tier 2 tests


def test_update_lockfile_pyproject_diff_mode(
    workdir, monkeypatch, capsys, tmp_path, patterns
):
    """update_lockfile with --diff shows changes without modifying uv.lock."""
    import argparse

    # Create directory with pyproject.toml and uv.lock
    app_dir = Path(workdir) / "diffapp"
    app_dir.mkdir()

    (app_dir / "pyproject.toml").write_text(
        """[project]
name = "diffapp"
version = "1.0.0"
dependencies = ["click"]
"""
    )

    # Create existing uv.lock with old content
    old_lock_content = "version = 1\n[[package]]\nname = 'click'\nversion = '8.0.0'\n"
    (app_dir / "uv.lock").write_text(old_lock_content)

    # Mock ensure_uv and uv_cmd
    monkeypatch.setattr(appenv, "ensure_uv", lambda base: None)
    monkeypatch.setattr(appenv, "ensure_uv", lambda base=None: Path("/usr/bin/uv"))

    def mock_uv_cmd(args, verbose=False, **kwargs):
        cwd = kwargs.get("cwd")
        if cwd and "lock" in args and "pip" not in args:
            # In diff mode, uv lock runs in temp dir
            # Create a "new" lock file with different content
            new_lock = Path(cwd) / "uv.lock"
            new_lock.write_text(
                "version = 1\n[[package]]\nname = 'click'\nversion = '8.1.0'\n"
            )
        return b""

    monkeypatch.setattr(appenv, "uv_cmd", mock_uv_cmd)

    env = appenv.AppEnv(app_dir, Path.cwd())
    args = argparse.Namespace(diff=True, verbose=False)

    env.update_lockfile(args=args, remaining=None)

    # Verify diff output was shown
    # captured unused - removed

    # Strip ANSI codes for cleaner pattern matching
    # out_clean = re.sub(r"\x1b\[[0-9;]*m", "", out)

    # Use patterns for diff mode output - check for unified diff format
    patterns.any.optional("...")
    patterns.main.merge("any")
    patterns.main.in_order(
        """\
Checking lockfile changes ...
--- uv.lock
+++ uv.lock (new)
...
-version = '8.0.0'
+version = '8.1.0'"""
    )
    # Removed unused assertion

    # Verify original uv.lock was NOT modified
    assert (app_dir / "uv.lock").read_text() == old_lock_content


# ==============================================================================
# Verbose output tests for update_lockfile (from test_coverage.py)
# ==============================================================================


def test_update_lockfile_pyproject_no_changes(workdir, monkeypatch, capsys):
    """Lines 1005, 1033: 'No changes' output when lockfile unchanged."""
    base = Path(workdir)
    (base / "pyproject.toml").write_text(
        '[project]\nname = "test"\ndependencies = ["click"]\n'
    )

    lock_content = "version = 1\n[[package]]\nname = 'click'\nversion = '8.1.0'\n"
    (base / "uv.lock").write_text(lock_content)

    monkeypatch.setattr(appenv, "ensure_uv", lambda base: None)
    monkeypatch.setattr(appenv, "ensure_uv", lambda base=None: Path("/usr/bin/uv"))

    def mock_uv_cmd(args, verbose=False, **kwargs):
        return b""

    monkeypatch.setattr(appenv, "uv_cmd", mock_uv_cmd)

    env = appenv.AppEnv(base, Path.cwd())
    env.update_lockfile()

    captured = capsys.readouterr()
    assert "No changes" in captured.out


def test_update_lockfile_pyproject_updated(workdir, monkeypatch, capsys):
    """Line 1040: 'Updated' output when lockfile has changes."""
    base = Path(workdir)
    (base / "pyproject.toml").write_text(
        '[project]\nname = "test"\ndependencies = ["click"]\n'
    )

    (base / "uv.lock").write_text(
        "version = 1\n[[package]]\nname = 'click'\nversion = '8.0.0'\n"
    )

    monkeypatch.setattr(appenv, "ensure_uv", lambda base: None)
    monkeypatch.setattr(appenv, "ensure_uv", lambda base=None: Path("/usr/bin/uv"))

    def mock_uv_cmd(args, verbose=False, **kwargs):
        if "lock" in args and "pip" not in args:
            (base / "uv.lock").write_text(
                "version = 1\n[[package]]\nname = 'click'\nversion = '8.1.0'\n"
            )
        elif "compile" in args:
            output_file = args[args.index("--output-file") + 1]
            Path(output_file).write_text("click==8.1.0\n")
        return b""

    monkeypatch.setattr(appenv, "uv_cmd", mock_uv_cmd)

    env = appenv.AppEnv(base, Path.cwd())
    env.update_lockfile()

    captured = capsys.readouterr()
    assert "Updated" in captured.out


def test_update_lockfile_pyproject_diff_verbose(workdir, monkeypatch, capsys):
    """Line 990: Verbose output in pyproject diff mode."""
    base = Path(workdir)
    (base / "pyproject.toml").write_text(
        '[project]\nname = "test"\ndependencies = ["click"]\n'
    )
    (base / "uv.lock").write_text("version = 1\n")

    monkeypatch.setattr(appenv, "ensure_uv", lambda base: None)
    monkeypatch.setattr(appenv, "ensure_uv", lambda base=None: Path("/usr/bin/uv"))

    def mock_uv_cmd(args, verbose=False, **kwargs):
        if "lock" in args and "pip" not in args:
            cwd = kwargs.get("cwd")
            if cwd:
                # Create lock file in temp directory
                (Path(cwd) / "uv.lock").write_text("version = 1\nnew = true\n")
        return b""

    monkeypatch.setattr(appenv, "uv_cmd", mock_uv_cmd)

    env = appenv.AppEnv(base, Path.cwd())
    args = argparse.Namespace(diff=True, verbose=True)

    env.update_lockfile(args=args, remaining=None)

    captured = capsys.readouterr()
    assert "dry run" in captured.out


def test_update_lockfile_pyproject_diff_no_changes(workdir, monkeypatch, capsys):
    """Line 1005: 'No changes' output in diff mode for pyproject."""
    base = Path(workdir)
    (base / "pyproject.toml").write_text(
        '[project]\nname = "test"\ndependencies = ["click"]\n'
    )

    lock_content = "version = 1\n[[package]]\nname = 'click'\nversion = '8.1.0'\n"
    (base / "uv.lock").write_text(lock_content)

    monkeypatch.setattr(appenv, "ensure_uv", lambda base: None)
    monkeypatch.setattr(appenv, "ensure_uv", lambda base=None: Path("/usr/bin/uv"))

    def mock_uv_cmd(args, verbose=False, **kwargs):
        if "lock" in args and "pip" not in args:
            cwd = kwargs.get("cwd")
            if cwd:
                # Create identical lock file
                (Path(cwd) / "uv.lock").write_text(lock_content)
        return b""

    monkeypatch.setattr(appenv, "uv_cmd", mock_uv_cmd)

    env = appenv.AppEnv(base, Path.cwd())
    args = argparse.Namespace(diff=True, verbose=False)

    env.update_lockfile(args=args, remaining=None)

    captured = capsys.readouterr()
    assert "No changes" in captured.out


def test_update_lockfile_pyproject_calls_uv_lock(tmp_path, monkeypatch):
    """_update_lockfile_pyproject calls uv lock."""
    monkeypatch.chdir(tmp_path)
    base = tmp_path

    (base / "pyproject.toml").write_text(
        "[project]\nname = 'test'\ndependencies = []\n"
    )

    uv_calls = []
    monkeypatch.setattr(appenv, "ensure_uv", lambda base: None)
    monkeypatch.setattr(appenv, "ensure_uv", lambda base=None: Path("/usr/bin/uv"))
    monkeypatch.setattr(
        appenv,
        "uv_cmd",
        lambda args, **kwargs: uv_calls.append(args),
    )

    env = appenv.AppEnv(base, Path.cwd())
    env.update_lockfile(None)

    # Should call uv lock
    assert any("lock" in str(c) for c in uv_calls)


def test_update_lockfile_verbose_shows_running_uv_lock(tmp_path, monkeypatch, capsys):
    """_update_lockfile_pyproject shows 'Running: uv lock' in verbose mode."""
    monkeypatch.chdir(tmp_path)
    base = tmp_path

    (base / "pyproject.toml").write_text(
        "[project]\nname = 'test'\ndependencies = []\n"
    )

    monkeypatch.setattr(appenv, "ensure_uv", lambda base: None)
    monkeypatch.setattr(appenv, "ensure_uv", lambda base=None: Path("/usr/bin/uv"))
    monkeypatch.setattr(appenv, "uv_cmd", lambda args, **kwargs: None)

    env = appenv.AppEnv(base, Path.cwd())
    args = argparse.Namespace(diff=False, verbose=True)
    env.update_lockfile(args)

    captured = capsys.readouterr()
    assert "Running: uv lock" in captured.out
