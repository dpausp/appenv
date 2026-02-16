import io
import os
import shutil
import sys
import unittest.mock
from pathlib import Path

import pytest

import appenv


def test_init_and_create_lockfile(workdir, monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO("ducker\nducker<2.0.2\n\n"))

    env = appenv.AppEnv(Path(workdir) / "ducker", Path.cwd())
    env.init()

    lockfile = os.path.join(workdir, "ducker", "requirements.lock")
    assert not os.path.exists(lockfile)

    env.update_lockfile()

    assert os.path.exists(lockfile)
    with open(lockfile) as f:
        lockfile_content = f.read()
    # UV generates lockfile with header and via-comments
    assert "ducker==2.0.1" in lockfile_content
    assert "# appenv-requirements-hash:" in lockfile_content


def test_update_lockfile_uses_minimal_python(workdir, monkeypatch):
    """It uses the minimal python version from preferences for lockfile."""
    monkeypatch.setattr("sys.stdin", io.StringIO("httpie\nhttpie\nmyapp\n"))
    monkeypatch.setattr(appenv, "has_uv", lambda: True)

    env = appenv.AppEnv(Path(workdir) / "myapp", Path.cwd())
    env.init()

    requirements_file = Path(workdir) / "myapp" / "requirements.txt"
    content = requirements_file.read_text()
    requirements_file.write_text(
        "# appenv-python-preference: 3.11,3.9,3.10\n" + content
    )

    # Mock uv_cmd to capture --python argument
    captured_args = []
    monkeypatch.setattr(
        appenv, "uv_cmd", lambda args, **kwargs: captured_args.append(args)
    )
    monkeypatch.setattr(appenv, "find_minimal_python", lambda: "/usr/bin/python3.9")

    env.update_lockfile()

    # Verify --python flag was passed with minimal version
    assert any("--python" in str(arg) for arg in captured_args)
    assert any("python3.9" in str(arg) for arg in captured_args)


@pytest.mark.skipif(sys.version_info[0:2] < (3, 8), reason="Isolated CI builds")
def test_update_lockfile_missing_minimal_python(workdir, monkeypatch):
    """It raises an error if the minimal python is not available."""
    monkeypatch.setattr("sys.stdin", io.StringIO("pytest\npytest==6.1.2\nppytest\n"))

    env = appenv.AppEnv(Path(workdir) / "ppytest", Path.cwd())
    env.init()

    requirements_file = os.path.join(workdir, "ppytest", "requirements.txt")

    with open(requirements_file, "r+") as f:
        lines = f.readlines()
        lines[0] = "# appenv-python-preference: 3.8,3.6,3.9\n"
        f.seek(0)
        f.writelines(lines)

    old_which = shutil.which

    def new_which(string):
        if string == "python3.6":
            return None
        else:
            return old_which(string)

    with unittest.mock.patch("shutil.which") as which:
        which.side_effect = new_which
        with pytest.raises(SystemExit) as e:
            env.update_lockfile()
    assert e.value.code == 66
