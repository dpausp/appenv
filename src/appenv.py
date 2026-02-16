#!/usr/bin/env python3
# appenv - a single file 'application in venv bootstrapping and updating
#          mechanism for python-based (CLI) applications

# Assumptions:
#
#   - the appenv file is placed in a repo with the name of the application
#   - the name of the application/file is an entrypoint XXX
#   - uv is available in PATH
#   - a requirements.txt file next to the appenv file

# TODO
#
# - provide a `clone` meta command to create a new project based on this one
#   maybe use an entry point to allow further initialisation of the clone.

import argparse
import glob
import hashlib
import os
import os.path
import shutil
import subprocess
import sys
import tempfile


class TColors:
    """Terminal colors for pretty output."""

    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RESET = "\033[0m"


def cmd(c, merge_stderr=True, quiet=False):
    try:
        kwargs = {}
        if isinstance(c, str):
            kwargs["shell"] = True
            c = [c]
        if merge_stderr:
            kwargs["stderr"] = subprocess.STDOUT
        return subprocess.check_output(c, **kwargs)
    except subprocess.CalledProcessError as e:
        print(f"{c} returned with exit code {e.returncode}")
        print(e.output.decode("utf-8", "replace"))
        raise ValueError(e.output.decode("utf-8", "replace")) from None


def has_uv():
    """Check if uv is available."""
    return shutil.which("uv") is not None


def uv_cmd(args, **kwargs):
    """Execute uv command."""
    uv_bin = shutil.which("uv")
    if not uv_bin:
        raise RuntimeError("uv not found.")
    return cmd([uv_bin] + [str(arg) for arg in args], **kwargs)


def python(path, c, **kwargs):
    return cmd([os.path.join(path, "bin/python")] + c, **kwargs)


def ensure_venv(target):
    if os.path.exists(os.path.join(target, "bin", "python")):
        return
    if os.path.exists(target):
        print("Deleting unclean target")
        cmd(["rm", "-rf", target])
    print("Creating venv with uv ...")
    uv_cmd(["venv", "--python", sys.executable, target])


def parse_preferences():
    preferences = None
    if os.path.exists("requirements.txt"):
        with open("requirements.txt") as f:
            for line in f:
                # Expected format:
                # # appenv-python-preference: 3.1,3.9,3.4
                if not line.startswith("# appenv-python-preference: "):
                    continue
                preferences = line.split(":")[1]
                preferences = [x.strip() for x in preferences.split(",")]
                preferences = list(filter(None, preferences))
                break
    return preferences


def find_minimal_python():
    """Find the minimal preferred Python version for lockfile generation.

    Returns the path to the minimal Python, or None if no preference is set.
    Exits with code 66 if a preference is set but the minimal version is not found.
    """
    preferences = parse_preferences()
    if not preferences:
        return None

    # Sort to get minimal version first
    preferences.sort(key=lambda s: [int(u) for u in s.split(".")])
    minimal_version = preferences[0]

    python_path = shutil.which(f"python{minimal_version}")
    if not python_path:
        print("Could not find the minimal preferred Python version.")
        print("To ensure a working requirements.lock on all Python versions")
        print(f"make Python {minimal_version} available on this system.")
        sys.exit(66)

    assert python_path is not None  # for type checker
    python_path = os.path.realpath(python_path)

    # Verify it works
    try:
        subprocess.check_call(
            [python_path, "-c", "print(1)"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except subprocess.CalledProcessError:
        print(f"Python {minimal_version} found but not functional.")
        sys.exit(66)

    return python_path


def ensure_best_python(base):
    os.chdir(base)

    if "APPENV_BEST_PYTHON" in os.environ:
        # Don't do this twice to avoid being surprised with
        # accidental infinite loops.
        return
    import shutil

    preferences = parse_preferences()

    if preferences is None:
        # use newest Python available if nothing else is requested
        preferences = [f"3.{x}" for x in reversed(range(4, 20))]

    current_python = os.path.realpath(sys.executable)
    for version in preferences:
        python = shutil.which(f"python{version}")
        if not python:
            # not a usable python
            continue
        python = os.path.realpath(python)
        if python == current_python:
            # found a preferred python and we're already running as it
            break
        # Try whether this Python works
        try:
            subprocess.check_call(
                [python, "-c", "print(1)"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except subprocess.CalledProcessError:
            continue
        argv = [os.path.basename(python)] + sys.argv
        os.environ["APPENV_BEST_PYTHON"] = python
        os.execv(python, argv)
    else:
        print("Could not find a preferred Python version.")
        print("Preferences: {}".format(", ".join(preferences)))
        sys.exit(65)


class AppEnv:
    def __init__(self, base, original_cwd):
        self.base = base

        # This used to be computed based on the application name but
        # as we can have multiple application names now, we always put the
        # environments into '.appenv'. They're hashed anyway.
        self.appenv_dir = os.path.join(self.base, ".appenv")

        # Allow simplifying a lot of code by assuming that all the
        # meta-operations happen in the base directory. Store the original
        # working directory here so we switch back at the appropriate time.
        self.original_cwd = original_cwd

    def meta(self):
        # Parse the appenv arguments
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers()
        p = subparsers.add_parser("update-lockfile", help="Update the lock file.")
        p.add_argument(
            "--diff",
            action="store_true",
            help="Show full diff without writing lockfile.",
        )
        p.set_defaults(func=self.update_lockfile)

        p = subparsers.add_parser("init", help="Create a new appenv project.")
        p.set_defaults(func=self.init)

        p = subparsers.add_parser("reset", help="Reset the environment.")
        p.set_defaults(func=self.reset)

        p = subparsers.add_parser("prepare", help="Prepare the venv.")
        p.set_defaults(func=self.prepare)

        p = subparsers.add_parser(
            "python", help="Spawn the embedded Python interpreter REPL"
        )
        p.set_defaults(func=self.python)

        p = subparsers.add_parser(
            "run",
            help="Run a script from the bin/ directory of the virtual env.",
        )
        p.add_argument("script", help="Name of the script to run.")
        p.set_defaults(func=self.run_script)

        args, remaining = parser.parse_known_args()

        if not hasattr(args, "func"):
            parser.print_usage()
        else:
            args.func(args, remaining)

    def run(self, command, argv):
        env_dir = self.prepare()
        cmd = os.path.join(env_dir, "bin", command)
        argv = [cmd] + argv
        os.environ["APPENV_BASEDIR"] = self.base
        os.chdir(self.original_cwd)
        os.execv(cmd, argv)

    def _assert_requirements_lock(self):
        if not os.path.exists("requirements.lock"):
            print(
                "No requirements.lock found. Generate it using ./appenv update-lockfile"
            )
            sys.exit(67)

        with open("requirements.lock") as f:
            locked_hash = None
            for line in f:
                if line.startswith("# appenv-requirements-hash: "):
                    locked_hash = line.split(":")[1].strip()
                    break
            if locked_hash != self._hash_requirements():
                print(
                    "requirements.txt seems out of date (hash mismatch). "
                    "Regenerate using ./appenv update-lockfile"
                )
                sys.exit(67)

    def _hash_requirements(self):
        with open("requirements.txt", "rb") as f:
            hash_content = f.read()
        return hashlib.new("sha256", hash_content).hexdigest()

    def prepare(self, args=None, remaining=None):
        # copy used requirements.txt into the target directory so we can use
        # that to check later
        # - when to clean up old versions? keep like one or two old revisions?
        # - enumerate the revisions and just copy the requirements.txt, check
        #   for ones that are clean or rebuild if necessary
        os.chdir(self.base)

        self._assert_requirements_lock()

        hash_content = []
        with open("requirements.lock", "rb") as f:
            requirements = f.read()
        hash_content.append(os.fsencode(os.path.realpath(sys.executable)))
        hash_content.append(requirements)
        with open(__file__, "rb") as f:
            hash_content.append(f.read())
        env_hash = hashlib.new("sha256", b"".join(hash_content)).hexdigest()[:8]
        env_dir = os.path.join(self.appenv_dir, env_hash)

        whitelist = set(
            [
                env_dir,
                os.path.join(self.appenv_dir, "unclean"),
                os.path.join(self.appenv_dir, "current"),
            ]
        )
        for path in glob.glob(f"{self.appenv_dir}/*"):
            if path not in whitelist:
                print(f"Removing expired path: {path} ...")
                if not os.path.isdir(path):
                    os.unlink(path)
                else:
                    shutil.rmtree(path)
        if os.path.exists(env_dir):
            # check whether the existing environment is OK, it might be
            # nice to rebuild in a separate place if necessary to avoid
            # interruptions to running services, but that isn't what we're
            # using it for at the  moment
            try:
                if not os.path.exists(f"{env_dir}/appenv.ready"):
                    raise Exception()
            except Exception:
                print("Existing envdir not consistent, deleting")
                cmd(["rm", "-rf", env_dir])

        if not os.path.exists(env_dir):
            ensure_venv(env_dir)

            with open(os.path.join(env_dir, "requirements.lock"), "wb") as f:
                f.write(requirements)

            print("Installing ...")
            uv_cmd(
                [
                    "pip",
                    "sync",
                    "--python",
                    f"{env_dir}/bin/python",
                    f"{env_dir}/requirements.lock",
                ]
            )

            with open(os.path.join(env_dir, "appenv.ready"), "w") as f:
                f.write("Ready or not, here I come, you can't hide\n")
            current_path = os.path.join(self.appenv_dir, "current")
            try:
                os.unlink(current_path)
            except FileNotFoundError:
                pass
            os.symlink(env_hash, current_path)

        return env_dir

    def init(self, args=None, remaining=None):
        print("Let's create a new appenv project.\n")
        command = None
        while not command:
            command = input("What should the command be named? ").strip()
        dependency = input(
            f"What is the main dependency as found on PyPI? [{command}] "
        ).strip()
        if not dependency:
            dependency = command
        default_target = os.path.abspath(os.path.join(self.original_cwd, command))
        target = input(f"Where should we create this? [{default_target}] ").strip()
        if target:
            target = os.path.join(self.original_cwd, target)
        else:
            target = default_target
        target = os.path.abspath(target)
        if not os.path.exists(target):
            os.makedirs(target)
        print()
        print(f"Creating appenv setup in {target} ...")
        with open(__file__, "rb") as bootstrap_file:
            bootstrap_data = bootstrap_file.read()
        os.chdir(target)
        with open("appenv", "wb") as new_appenv:
            new_appenv.write(bootstrap_data)
        os.chmod("appenv", 0o755)
        if os.path.exists(command):
            os.unlink(command)
        os.symlink("appenv", command)
        with open("requirements.txt", "w") as requirements_txt:
            requirements_txt.write(dependency + "\n")
        print()
        rel_path = os.path.relpath(target, self.original_cwd)
        print(f"Done. You can now `cd {rel_path}` and call `./{command}`")
        print("to bootstrap and run it.")

    def python(self, args, remaining):
        self.run("python", remaining)

    def run_script(self, args, remaining):
        self.run(args.script, remaining)

    def reset(self, args=None, remaining=None):
        print(f"Resetting ALL application environments in {self.appenv_dir} ...")
        cmd(["rm", "-rf", self.appenv_dir])

    def update_lockfile(self, args=None, remaining=None):
        """Update requirements.lock using uv pip compile.

        Editable installs (-e) are preserved exactly as written in
        requirements.txt to maintain portability across machines.
        """
        if not has_uv():
            print("ERROR: uv is required for update-lockfile.")
            print("Install uv: curl -LsSf https://astral.sh/uv/install.sh | sh")
            sys.exit(1)

        minimal_python = find_minimal_python()
        os.chdir(self.base)

        # Read existing lockfile for comparison
        old_lines: set[str] = set()
        if os.path.exists("requirements.lock"):
            with open("requirements.lock") as f:
                old_lines = set(
                    line.strip()
                    for line in f
                    if line.strip() and not line.startswith("#")
                )

        print("Updating lockfile with uv ...")

        # Separate editable installs from regular requirements
        editable_specs = []
        regular_lines = []
        with open("requirements.txt") as f:
            for line in f:
                stripped = line.strip()
                if stripped.startswith("-e "):
                    editable_specs.append(stripped)
                elif stripped and not stripped.startswith("#"):
                    regular_lines.append(stripped)

        # Create temp requirements without editables for uv
        tmp_fd, tmp_requirements = tempfile.mkstemp(suffix=".txt", text=True)
        try:
            with os.fdopen(tmp_fd, "w") as tmp:
                tmp.write("\n".join(regular_lines) + "\n")

            # Compile with uv to temp file
            tmp_lock_fd, tmp_lock = tempfile.mkstemp(suffix=".lock", text=True)
            os.close(tmp_lock_fd)

            compile_args = [
                "pip",
                "compile",
                tmp_requirements,
                "--output-file",
                tmp_lock,
            ]
            if minimal_python:
                compile_args.extend(["--python", minimal_python])
            uv_cmd(compile_args)

            # Read compiled content
            with open(tmp_lock) as f:
                compiled = f.read()

            # Build new lockfile content
            new_content = f"# appenv-requirements-hash: {self._hash_requirements()}\n"
            if editable_specs:
                new_content += "\n# Editable installs\n"
                for spec in editable_specs:
                    new_content += spec + "\n"
            new_content += compiled

            # Extract new lines for comparison
            new_lines = set(
                line.strip()
                for line in new_content.splitlines()
                if line.strip() and not line.startswith("#")
            )

            if args and args.diff:
                # Show full diff
                import difflib

                old_content = ""
                if os.path.exists("requirements.lock"):
                    with open("requirements.lock") as f:
                        old_content = f.read()

                diff = difflib.unified_diff(
                    old_content.splitlines(keepends=True),
                    new_content.splitlines(keepends=True),
                    fromfile="requirements.lock",
                    tofile="requirements.lock (new)",
                )
                print("".join(diff), end="")
            else:
                # Write lockfile
                with open("requirements.lock", "w") as f:
                    f.write(new_content)

                # Show summary
                added = new_lines - old_lines
                removed = old_lines - new_lines
                print(f"Done. +{len(added)} -{len(removed)}")
        finally:
            if os.path.exists(tmp_requirements):
                os.unlink(tmp_requirements)
            if os.path.exists(tmp_lock):
                os.unlink(tmp_lock)


def main():
    base = os.path.dirname(__file__)
    original_cwd = os.getcwd()

    ensure_best_python(base)
    # clear PYTHONPATH variable to get a defined environment
    # XXX this is a bit of history. not sure whether its still needed. keeping
    # it for good measure
    if "PYTHONPATH" in os.environ:
        del os.environ["PYTHONPATH"]

    # Determine whether we're being called as appenv or as an application name
    application_name = os.path.splitext(os.path.basename(__file__))[0]

    appenv = AppEnv(base, original_cwd)
    if application_name == "appenv":
        appenv.meta()
    else:
        appenv.run(application_name, sys.argv[1:])


if __name__ == "__main__":
    main()
