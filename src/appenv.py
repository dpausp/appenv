#!/usr/bin/env python3
# appenv - a single file 'application in venv bootstrapping and updating
#          mechanism for python-based (CLI) applications

# Assumptions:
#
#   - the appenv file is placed in a repo with the name of the application
#   - the name of the application/file is an entrypoint XXX
#   - uv will be installed via pip or nix if not available
#   - pyproject.toml (preferred) or requirements.txt next to the appenv file

# TODO
#
#   - provide a `clone` meta command to create a new project based on this one
#     maybe use an entry point to allow further initialisation of the clone.

__version__ = "2026.2.0"

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
PYPROJECT_TOML = "pyproject.toml"
UV_LOCK = "uv.lock"


def detect_project_type(base: Path):
    """Detect project type based on present files.

    Priority: pyproject.toml > requirements.txt

    Returns: "pyproject", "requirements", or None
    """
    if (base / PYPROJECT_TOML).exists():
        return "pyproject"
    if (base / REQUIREMENTS_TXT).exists():
        return "requirements"
    return None


class TColors:
    """Terminal colors for pretty output."""

    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RESET = "\033[0m"


def cmd(c, merge_stderr=True, quiet=False, cwd=None):
    try:
        kwargs = {}
        if isinstance(c, str):
            kwargs["shell"] = True
            c = [c]
        if merge_stderr:
            kwargs["stderr"] = subprocess.STDOUT
        if cwd:
            kwargs["cwd"] = cwd
        return subprocess.check_output(c, **kwargs)
    except subprocess.CalledProcessError as e:
        print(f"{c} returned with exit code {e.returncode}")
        print(e.output.decode("utf-8", "replace"))
        raise ValueError(e.output.decode("utf-8", "replace")) from None


def has_nix():
    """Check if nix is available."""
    return shutil.which("nix") is not None


# Global cache for uv binary path
_uv_bin_cache = None


def get_uv_bin(base=None):
    """Get path to uv binary.

    Priority:
    1. uv in PATH → use it
    2. .appenv/.uv/bin/uv exists → use it
    3. nix build nixpkgs#uv --out-link .appenv/.uv → use it
    4. pip install uv → use it
    """
    global _uv_bin_cache

    if _uv_bin_cache:
        return _uv_bin_cache

    # 1. Check PATH
    uv_in_path = shutil.which("uv")
    if uv_in_path:
        _uv_bin_cache = uv_in_path
        return uv_in_path

    # 2-3. Check/use nix build in .appenv/.uv
    if base and has_nix():
        uv_local = base / ".appenv" / ".uv" / "bin" / "uv"
        if uv_local.exists():
            _uv_bin_cache = str(uv_local)
            return str(uv_local)

        # Build uv with nix
        print("Building uv with nix (one-time setup) ...")
        uv_out = base / ".appenv" / ".uv"
        subprocess.run(
            ["nix", "build", "nixpkgs#uv", "--out-link", str(uv_out)],
            check=True,
        )
        _uv_bin_cache = str(uv_local)
        return str(uv_local)

    # 4. pip install fallback
    print("Installing uv via pip ...")
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "-q", "uv"],
        check=True,
    )
    uv_in_path = shutil.which("uv")
    if uv_in_path:
        _uv_bin_cache = uv_in_path
        return uv_in_path

    raise RuntimeError("uv not found and could not be installed.")


def ensure_uv(base=None):
    """Ensure uv is available. Call get_uv_bin to get the path."""
    get_uv_bin(base)


def uv_cmd(args, **kwargs):
    """Execute uv command."""
    uv_bin = _uv_bin_cache or shutil.which("uv")
    if not uv_bin:
        raise RuntimeError("uv not found. Call ensure_uv() first.")
    return cmd([uv_bin] + [str(arg) for arg in args], **kwargs)


def python(path: Path, c, **kwargs):
    return cmd([str(path / "bin" / "python")] + c, **kwargs)


def ensure_venv(target, base=None):
    if (target / "bin" / "python").exists():
        return
    # Derive base from target if not provided: .appenv/hash -> base
    if not base:
        base = (
            target.parent.parent if target.parent.name == ".appenv" else target.parent
        )
    ensure_uv(base)
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

        p = subparsers.add_parser(
            "init-pyproject",
            help="Create or migrate to pyproject.toml project.",
        )
        p.set_defaults(func=self.init_pyproject)

        p = subparsers.add_parser("reset", help="Reset the environment.")
        p.set_defaults(func=self.reset)

        p = subparsers.add_parser("version", help="Show appenv version.")
        p.set_defaults(func=self.show_version)

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
        os.chdir(self.base)

        project_type = detect_project_type(self.base)

        if project_type == "pyproject":
            return self._prepare_pyproject()
        elif project_type == "requirements":
            return self._prepare_requirements()
        else:
            print(f"No {PYPROJECT_TOML} or {REQUIREMENTS_TXT} found.")
            sys.exit(67)

    def _prepare_pyproject(self):
        """Prepare environment for pyproject.toml using uv native workflow."""
        venv = self.base / ".venv"
        lock_file = self.base / UV_LOCK
        old_appenv = self.appenv_dir

        # Ensure uv.lock exists
        if not lock_file.exists():
            print(f"No {UV_LOCK} found. Run: ./appenv update-lockfile")
            sys.exit(67)

        ensure_uv(self.base)

        # Create venv if needed or check integrity
        if not venv.exists() or not (venv / "bin" / "python").exists():
            if venv.exists():
                print("Corrupted venv detected, removing ...")
                shutil.rmtree(venv)
            print("Creating venv with uv ...")
            uv_cmd(["venv"])

        # Sync dependencies (idempotent)
        print("Syncing dependencies ...")
        uv_cmd(["sync"])

        # Cleanup old .appenv if migration is complete
        # (requirements.txt removed = user migrated intentionally)
        if old_appenv.exists() and not (self.base / REQUIREMENTS_TXT).exists():
            print("Removing old .appenv ...")
            shutil.rmtree(old_appenv)

        return str(venv)

    def _prepare_requirements(self):
        """Prepare environment for requirements.txt using legacy workflow."""
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

    def init_pyproject(self, args=None, remaining=None):
        """Create or migrate to pyproject.toml project."""
        target = self.original_cwd.resolve()

        # Check for migration
        requirements_file = target / REQUIREMENTS_TXT
        pyproject_file = target / PYPROJECT_TOML

        if pyproject_file.exists():
            print(f"pyproject.toml already exists in {target}.")
            print("Nothing to do.")
            print("Edit pyproject.toml manually to make changes.")
            return

        initial_command = target.name
        dependencies: list[str] = []
        description = ""
        python_version = "3.8"
        migrated = requirements_file.exists()

        if migrated:
            # Migration mode
            print("Migrating from requirements.txt to pyproject.toml...\n")
            deps_content = requirements_file.read_text().strip()
            editable_warnings = []
            if deps_content:
                for line in deps_content.splitlines():
                    stripped = line.strip()
                    if stripped and not stripped.startswith("#"):
                        if stripped.startswith("-e "):
                            # Handle editable installs - warn and skip
                            editable_warnings.append(stripped)
                        else:
                            dependencies.append(stripped)
            if editable_warnings:
                print(f"Warning: {len(editable_warnings)} editable install(s) skipped:")
                for warn in editable_warnings:
                    print(f"  - {warn}")
                print("Edit pyproject.toml manually to add them if needed.\n")
            print(
                f"Found {len(dependencies)} dependency(ies): {', '.join(dependencies)}"
            )
        else:
            # Fresh start
            print("Let's create a new pyproject.toml project.\n")
            initial_command = None
            while not initial_command:
                initial_command = input(
                    "What should the command be named? [app] "
                ).strip()
            if not initial_command:
                initial_command = "app"

            description = input("Description []: ").strip()

            print("\nEnter dependencies (one per line, empty line to finish):")
            print(f"  Default: {initial_command}")
            deps: list[str] = []
            while True:
                dep = input("  Dependency: ").strip()
                if not dep:
                    break
                deps.append(dep)
            if not deps:
                deps = [initial_command]

            python_version = input("\nMinimum Python version [3.8]: ").strip()
            if not python_version:
                python_version = "3.8"

            dependencies = deps

        # Generate pyproject.toml
        deps_toml = ", ".join(f'"{dep}"' for dep in dependencies)

        pyproject_content = f"""[project]
name = "{initial_command}"
version = "0.1.0"
description = "{description}"
dependencies = [
    {deps_toml},
]
requires-python = ">={python_version}"
"""

        pyproject_file.write_text(pyproject_content)
        print(f"Created {PYPROJECT_TOML}")

        # Create appenv bootstrap if needed
        appenv_script = target / "appenv"
        if not appenv_script.exists():
            bootstrap_data = Path(__file__).read_bytes()
            appenv_script.write_bytes(bootstrap_data)
            appenv_script.chmod(0o755)
            print("Created appenv bootstrap script")

        # Create symlink if needed (handle broken symlinks)
        command_link = target / initial_command
        if command_link.is_symlink() or command_link.exists():
            command_link.unlink(missing_ok=True)
        command_link.symlink_to("appenv")
        print(f"Created {initial_command} symlink")

        print()
        if migrated:
            print("Done. pyproject.toml created, requirements.txt kept as legacy.")
        else:
            print("Done. pyproject.toml created.")
        print(f"Run `./{initial_command}` to bootstrap and run.")

    def python(self, args, remaining):
        self.run("python", remaining)

    def run_script(self, args, remaining):
        self.run(args.script, remaining)

    def show_version(self, args=None, remaining=None):
        """Show appenv version."""
        print(f"appenv {__version__}")

    def reset(self, args=None, remaining=None):
        """Reset all virtual environments."""
        venv = self.base / ".venv"
        if venv.exists():
            print(f"Removing {venv} ...")
            shutil.rmtree(venv)
        if self.appenv_dir.exists():
            print(f"Resetting ALL application environments in {self.appenv_dir} ...")
            cmd(["rm", "-rf", str(self.appenv_dir)])

    def update_lockfile(self, args=None, remaining=None):
        """Update lockfile.

        For pyproject.toml: uses uv lock (native)
        For requirements.txt: uses uv pip compile (legacy)
        """
        ensure_uv(self.base)
        os.chdir(self.base)

        project_type = detect_project_type(self.base)

        if project_type == "pyproject":
            self._update_lockfile_pyproject(args)
        elif project_type == "requirements":
            self._update_lockfile_requirements(args)
        else:
            print(f"No {PYPROJECT_TOML} or {REQUIREMENTS_TXT} found.")
            sys.exit(67)

    def _update_lockfile_pyproject(self, args):
        """Update uv.lock using uv lock (native workflow)."""
        lock_file = self.base / UV_LOCK

        # Read existing lockfile for comparison
        old_lines: set[str] = set()
        if lock_file.exists():
            old_lines = set(
                stripped
                for line in lock_file.read_text().splitlines()
                if (stripped := line.strip()) and not stripped.startswith("#")
            )

        if args and args.diff:
            print("Checking lockfile changes ...")
            old_content = lock_file.read_text() if lock_file.exists() else ""

            # Run uv lock in temp directory to avoid modifying real lockfile
            with tempfile.TemporaryDirectory() as tmpdir:
                tmp_pyproject = Path(tmpdir) / PYPROJECT_TOML
                tmp_lock = Path(tmpdir) / UV_LOCK
                shutil.copy(self.base / PYPROJECT_TOML, tmp_pyproject)
                uv_cmd(["lock"], cwd=tmpdir)
                new_content = tmp_lock.read_text() if tmp_lock.exists() else ""

            import difflib

            # ANSI colors for diff
            red = "\033[31m"
            green = "\033[32m"
            cyan = "\033[36m"
            reset = "\033[0m"

            diff = difflib.unified_diff(
                old_content.splitlines(keepends=True),
                new_content.splitlines(keepends=True),
                fromfile=UV_LOCK,
                tofile=f"{UV_LOCK} (new)",
            )
            has_changes = False
            for line in diff:
                has_changes = True
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
            if not has_changes:
                print("No changes")
        else:
            # Run uv lock to update
            uv_cmd(["lock"])

            # Read new content
            new_content = lock_file.read_text() if lock_file.exists() else ""
            new_lines = set(
                stripped
                for line in new_content.splitlines()
                if (stripped := line.strip()) and not stripped.startswith("#")
            )

            # Show summary
            added = new_lines - old_lines
            removed = old_lines - new_lines
            n_added = len(added)
            n_removed = len(removed)

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

        # Also generate requirements.lock for non-uv fallback (but not in diff mode)
        if not (args and args.diff):
            print("Also generating requirements.lock for non-uv fallback ...")
            compile_args = [
                "pip",
                "compile",
                str(self.base / PYPROJECT_TOML),
                "--output-file",
                REQUIREMENTS_LOCK,
            ]
            minimal_python = find_minimal_python()
            if minimal_python:
                compile_args.extend(["--python", minimal_python])
            uv_cmd(compile_args)

    def _update_lockfile_requirements(self, args):
        """Update requirements.lock using uv pip compile (legacy workflow)."""
        minimal_python = find_minimal_python()

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
