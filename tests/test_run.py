import os.path
import subprocess
import sys
from pathlib import Path

import pytest

import appenv


def test_bootstrap_lockfile_existing_venv_broken_python():
    pass


def test_bootstrap_lockfile_missing_dependency():
    pass


def _setup_requirements_project(workdir):
    """Setup a requirements.txt based project without calling init()."""
    base = Path(workdir) / "ducker"
    base.mkdir()
    os.chdir(base)

    # Copy appenv script
    import shutil

    src_appenv = Path(appenv.__file__)
    dst_appenv = base / "appenv"
    shutil.copy(src_appenv, dst_appenv)
    dst_appenv.chmod(0o755)

    # Create symlink
    link = base / "ducker"
    link.symlink_to("appenv")

    # Create requirements.txt
    (base / "requirements.txt").write_text("ducker==2.0.1\n")

    return base


def test_bootstrap_and_run_with_lockfile(workdir, monkeypatch):
    base = _setup_requirements_project(workdir)

    env = appenv.AppEnv(base, Path.cwd())
    env.update_lockfile()

    with open(base / "ducker") as f:
        script = f"#!{sys.executable}\n{f.read()}"
    with open(base / "ducker", "w") as f:
        f.write(script)

    output = subprocess.check_output("./ducker --help", shell=True, cwd=base)
    assert output.startswith(b"usage: Ducker")


def test_bootstrap_and_run_python_with_lockfile(workdir, monkeypatch):
    base = _setup_requirements_project(workdir)

    env = appenv.AppEnv(base, Path.cwd())
    env.update_lockfile()

    output = subprocess.check_output(
        './appenv python -c "print(1)"', shell=True, cwd=base
    )
    assert output == b"1\n"


def test_bootstrap_and_run_without_lockfile(workdir, monkeypatch):
    """It raises an error if no requirements.lock is present."""
    base = _setup_requirements_project(workdir)

    with open(base / "ducker") as f:
        script = f"#!{sys.executable}\n{f.read()}"
    with open(base / "ducker", "w") as f:
        f.write(script)

    with pytest.raises(subprocess.CalledProcessError) as err:
        subprocess.check_output(["./ducker", "--help"], cwd=base)
    assert b"No requirements.lock found" in err.value.output
    assert b"update-lockfile" in err.value.output


def test_bootstrap_and_run_with_outdated_lockfile(workdir, monkeypatch):
    base = _setup_requirements_project(workdir)

    env = appenv.AppEnv(base, Path.cwd())
    env.update_lockfile()

    output = subprocess.check_output(
        './appenv python -c "print(1)"', shell=True, cwd=base
    )
    assert output == b"1\n"

    # Modify requirements.txt to make lockfile outdated (add a new dependency)
    with open(base / "requirements.txt", "a") as f:
        f.write("\nclick\n")

    s = subprocess.Popen(
        './appenv python -c "print(1)"',
        shell=True,
        stdout=subprocess.PIPE,
        cwd=base,
    )
    stdout, stderr = s.communicate()
    assert b"requirements.txt seems out of date" in stdout
    assert b"update-lockfile" in stdout

    subprocess.check_call("./appenv update-lockfile", shell=True, cwd=base)

    output = subprocess.check_output(
        './appenv python -c "print(1)"', shell=True, cwd=base
    )
    assert output == b"1\n"
