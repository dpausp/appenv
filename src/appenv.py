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
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# Constants
REQUIREMENTS_TXT = "requirements.txt"
REQUIREMENTS_LOCK = "requirements.lock"


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


def python(path: Path, c, **kwargs):
    return cmd([str(path / "bin" / "python")] + c, **kwargs)


def ensure_venv(target: Path):
    if (target / "bin" / "python").exists():
        return
    if target.exists():
        print("Deleting unclean target")
        cmd(["rm", "-rf", str(target)])
    print("Creating venv with uv ...")
    uv_cmd(["venv", "--python", sys.executable, str(target)])


def parse_preferences():
    preferences = None
    req_file = Path(REQUIREMENTS_TXT)
    if req_file.exists():
        for line in req_file.read_text().splitlines():
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
        print(f"To ensure a working {REQUIREMENTS_LOCK} on all Python versions")
        print(f"make Python {minimal_version} available on this system.")
        sys.exit(66)

    assert python_path is not None  # for type checker
    python_path = str(Path(python_path).resolve())

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


def ensure_best_python(base: Path):
    os.chdir(base)

    if "APPENV_BEST_PYTHON" in os.environ:
        # Don't do this twice to avoid being surprised with
        # accidental infinite loops.
        return

    preferences = parse_preferences()

    if preferences is None:
        # use newest Python available if nothing else is requested
        preferences = [f"3.{x}" for x in reversed(range(4, 20))]

    current_python = str(Path(sys.executable).resolve())
    for version in preferences:
        python = shutil.which(f"python{version}")
        if not python:
            # not a usable python
            continue
        python = str(Path(python).resolve())
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
        argv = [Path(python).name] + sys.argv
        os.environ["APPENV_BEST_PYTHON"] = python
        os.execv(python, argv)
    else:
        print("Could not find a preferred Python version.")
        print("Preferences: {}".format(", ".join(preferences)))
        sys.exit(65)


class AppEnv:
    def __init__(self, base: Path, original_cwd: Path):
        self.base = Path(base)
        self.appenv_dir = self.base / ".appenv"
        self.original_cwd = Path(original_cwd)

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
        env_dir = Path(self.prepare())
        cmd_path = env_dir / "bin" / command
        argv = [str(cmd_path)] + argv
        os.environ["APPENV_BASEDIR"] = str(self.base)
        os.chdir(self.original_cwd)
        os.execv(str(cmd_path), argv)

    def _assert_requirements_lock(self):
        lock_file = Path(REQUIREMENTS_LOCK)
        if not lock_file.exists():
            print(
                f"No {REQUIREMENTS_LOCK} found. "
                "Generate it using ./appenv update-lockfile"
            )
            sys.exit(67)

        locked_hash = None
        for line in lock_file.read_text().splitlines():
            if line.startswith("# appenv-requirements-hash: "):
                locked_hash = line.split(":")[1].strip()
                break
        if locked_hash != self._hash_requirements():
            print(
                f"{REQUIREMENTS_TXT} seems out of date (hash mismatch). "
                "Regenerate using ./appenv update-lockfile"
            )
            sys.exit(67)

    def _hash_requirements(self):
        return hashlib.new("sha256", Path(REQUIREMENTS_TXT).read_bytes()).hexdigest()

    def prepare(self, args=None, remaining=None):
        # copy used requirements.txt into the target directory so we can use
        # that to check later
        # - when to clean up old versions? keep like one or two old revisions?
        # - enumerate the revisions and just copy the requirements.txt, check
        #   for ones that are clean or rebuild if necessary
        os.chdir(self.base)

        self._assert_requirements_lock()

        requirements = Path(REQUIREMENTS_LOCK).read_bytes()
        hash_content = [
            os.fsencode(Path(sys.executable).resolve()),
            requirements,
            Path(__file__).read_bytes(),
        ]
        env_hash = hashlib.new("sha256", b"".join(hash_content)).hexdigest()[:8]
        env_dir = self.appenv_dir / env_hash

        whitelist = {
            str(env_dir),
            str(self.appenv_dir / "unclean"),
            str(self.appenv_dir / "current"),
        }
        if self.appenv_dir.exists():
            for path in self.appenv_dir.iterdir():
                if str(path) not in whitelist:
                    print(f"Removing expired path: {path} ...")
                    if path.is_dir():
                        shutil.rmtree(path)
                    else:
                        path.unlink()
        if env_dir.exists():
            # check whether the existing environment is OK, it might be
            # nice to rebuild in a separate place if necessary to avoid
            # interruptions to running services, but that isn't what we're
            # using it for at the  moment
            if not (env_dir / "appenv.ready").exists():
                print("Existing envdir not consistent, deleting")
                cmd(["rm", "-rf", str(env_dir)])

        if not env_dir.exists():
            ensure_venv(env_dir)

            (env_dir / REQUIREMENTS_LOCK).write_bytes(requirements)

            print("Installing ...")
            uv_cmd(
                [
                    "pip",
                    "sync",
                    "--python",
                    str(env_dir / "bin" / "python"),
                    str(env_dir / REQUIREMENTS_LOCK),
                ]
            )

            (env_dir / "appenv.ready").write_text(
                "Ready or not, here I come, you can't hide\n"
            )
            current_path = self.appenv_dir / "current"
            current_path.unlink(missing_ok=True)
            current_path.symlink_to(env_hash)

        return str(env_dir)

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
        default_target = (self.original_cwd / command).resolve()
        target_input = input(
            f"Where should we create this? [{default_target}] "
        ).strip()
        if target_input:
            target = (self.original_cwd / target_input).resolve()
        else:
            target = default_target
        if not target.exists():
            target.mkdir(parents=True)
        print()
        print(f"Creating appenv setup in {target} ...")
        bootstrap_data = Path(__file__).read_bytes()
        os.chdir(target)
        (target / "appenv").write_bytes(bootstrap_data)
        (target / "appenv").chmod(0o755)
        link = target / command
        link.unlink(missing_ok=True)
        link.symlink_to("appenv")
        (target / REQUIREMENTS_TXT).write_text(dependency + "\n")
        print()
        try:
            rel_path = target.relative_to(self.original_cwd)
        except ValueError:
            rel_path = target
        print(f"Done. You can now `cd {rel_path}` and call `./{command}`")
        print("to bootstrap and run it.")

    def python(self, args, remaining):
        self.run("python", remaining)

    def run_script(self, args, remaining):
        self.run(args.script, remaining)

    def reset(self, args=None, remaining=None):
        print(f"Resetting ALL application environments in {self.appenv_dir} ...")
        cmd(["rm", "-rf", str(self.appenv_dir)])

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
        lock_file = Path(REQUIREMENTS_LOCK)
        old_lines: set[str] = set()
        if lock_file.exists():
            old_lines = set(
                stripped
                for line in lock_file.read_text().splitlines()
                if (stripped := line.strip()) and not stripped.startswith("#")
            )

        if args and args.diff:
            print("Checking lockfile changes ...")
        else:
            print("Updating lockfile with uv ...")

        # Separate editable installs from regular requirements
        editable_specs = []
        regular_lines = []
        for line in Path(REQUIREMENTS_TXT).read_text().splitlines():
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
            compiled = Path(tmp_lock).read_text()

            # Build new lockfile content
            new_content = f"# appenv-requirements-hash: {self._hash_requirements()}\n"
            if editable_specs:
                new_content += "\n# Editable installs\n"
                for spec in editable_specs:
                    new_content += spec + "\n"
            new_content += compiled

            # Extract new lines for comparison
            new_lines = set(
                stripped
                for line in new_content.splitlines()
                if (stripped := line.strip()) and not stripped.startswith("#")
            )

            if args and args.diff:
                # Show full diff with colors
                import difflib

                old_content = lock_file.read_text() if lock_file.exists() else ""

                # ANSI colors for diff
                red = "\033[31m"
                green = "\033[32m"
                cyan = "\033[36m"
                reset = "\033[0m"

                diff = difflib.unified_diff(
                    old_content.splitlines(keepends=True),
                    new_content.splitlines(keepends=True),
                    fromfile=REQUIREMENTS_LOCK,
                    tofile=f"{REQUIREMENTS_LOCK} (new)",
                )
                for line in diff:
                    if line.startswith("---") or line.startswith("+++"):
                        print(cyan + line + reset, end="")
                    elif line.startswith("@@"):
                        print(cyan + line + reset, end="")
                    elif line.startswith("-"):
                        print(red + line + reset, end="")
                    elif line.startswith("+"):
                        print(green + line + reset, end="")
                    else:
                        print(line, end="")
            else:
                # Write lockfile
                lock_file.write_text(new_content)

                # Show summary with colors
                added = new_lines - old_lines
                removed = old_lines - new_lines
                n_added = len(added)
                n_removed = len(removed)

                # ANSI colors
                green = "\033[32m"
                red = "\033[31m"
                reset = "\033[0m"
                check = green + "✓" + reset

                if n_added == 0 and n_removed == 0:
                    print("No changes")
                else:
                    added_str = f"{green}+{n_added}{reset}"
                    removed_str = f"{red}-{n_removed}{reset}"
                    print(f"{check} Updated ({added_str} / {removed_str} lines)")
        finally:
            Path(tmp_requirements).unlink(missing_ok=True)
            Path(tmp_lock).unlink(missing_ok=True)


def main():
    base = Path(__file__).parent
    original_cwd = Path.cwd()

    ensure_best_python(base)
    # clear PYTHONPATH variable to get a defined environment
    # XXX this is a bit of history. not sure whether its still needed. keeping
    # it for good measure
    os.environ.pop("PYTHONPATH", None)

    # Determine whether we're being called as appenv or as an application name
    application_name = Path(__file__).stem

    appenv = AppEnv(base, original_cwd)
    if application_name == "appenv":
        appenv.meta()
    else:
        appenv.run(application_name, sys.argv[1:])


if __name__ == "__main__":
    main()
