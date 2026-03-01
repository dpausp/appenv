#!/usr/bin/env python3
# appenv - a single file 'application in venv bootstrapping and updating
#          mechanism for python-based (CLI) applications

# Assumptions:
#
#   - the appenv file is placed in a repo with the name of the application
#   - the name of the application/file becomes the CLI entrypoint via symlink
#   - pyproject.toml next to the appenv file

__version__ = "2026.2.0"

import argparse
import difflib
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import cast

# Constants
PYPROJECT_TOML = "pyproject.toml"
UV_LOCK = "uv.lock"

# Exit codes (BSD sysexits.h conventions)
EXIT_CODE_DATAERR = 65  # Input data issue (Python version not found)
EXIT_CODE_NOINPUT = 67  # Missing input file (pyproject.toml/uv.lock not found)
EXIT_CODE_UNAVAILABLE = 68  # Resource unavailable (uv too old)


def parse_requires_python(pyproject_path):
    """Parse requires-python from pyproject.toml.

    Returns tuple of (min_version, max_version) where max may be None.
    Handles patterns like:
        ">=3.13" → ("3.13", None)
        ">=3.11,<3.15" → ("3.11", "3.15")
        ">=3.11.0,<3.15.0" → ("3.11", "3.15")
    """
    if not pyproject_path.exists():
        return (None, None)

    content = pyproject_path.read_text()

    # Extract the requires-python value
    value_match = re.search(r'requires-python\s*=\s*["\']([^"\']+)["\']', content)
    if not value_match:
        return (None, None)

    spec = value_match.group(1)

    # Parse minimum version (>=X.Y or >X.Y)
    min_match = re.search(r">=?\s*(\d+\.\d+)", spec)
    min_version = min_match.group(1) if min_match else None

    # Parse maximum version (<X.Y or <=X.Y)
    # For < we exclude that version, for <= we include it
    max_match = re.search(r"<=?\s*(\d+\.\d+)", spec)
    max_version = max_match.group(1) if max_match else None

    return (min_version, max_version)


def find_available_pythons():
    """Find all available Python versions in PATH.

    Returns list of (version_str, path) tuples, sorted by version (newest first).
    """
    pythons = [
        (f"3.{i}", path) for i in range(4, 20) if (path := shutil.which(f"python3.{i}"))
    ]
    pythons.sort(key=lambda x: [int(p) for p in x[0].split(".")], reverse=True)
    return pythons


def version_satisfies_constraints(version, min_version, max_version=None):
    """Check if a version satisfies min/max constraints.

    Args:
        version: Version string like "3.10" or "3.10.1"
        min_version: Minimum version string (inclusive)
        max_version: Maximum version string (exclusive), optional

    Returns:
        True if version >= min_version and (version < max_version if max set)

    Examples:
        >>> version_satisfies_constraints("3.12", "3.10")
        True
        >>> version_satisfies_constraints("3.9", "3.10")
        False
        >>> version_satisfies_constraints("3.14", "3.10", "3.14")
        False
        >>> version_satisfies_constraints("3.13", "3.10", "3.14")
        True
    """
    ver_parts = [int(p) for p in version.split(".")]
    min_parts = [int(p) for p in min_version.split(".")]

    if ver_parts < min_parts:
        return False

    if max_version is not None:
        max_parts = [int(p) for p in max_version.split(".")]
        if ver_parts >= max_parts:
            return False

    return True


def ensure_best_python(base):
    """Ensure best Python for pyproject.toml workflow.

    Reads requires-python from pyproject.toml and selects the newest
    available Python that satisfies the constraint.
    """
    os.chdir(base)

    if "APPENV_BEST_PYTHON" in os.environ:
        return

    pyproject_path = base / PYPROJECT_TOML
    min_version, max_version = parse_requires_python(pyproject_path)

    if min_version is None:
        # No constraint, use default (newest available)
        min_version = "3.10"

    available = find_available_pythons()
    current_python = str(Path(sys.executable).resolve())

    for version, path in available:
        if not version_satisfies_constraints(version, min_version, max_version):
            continue

        path = str(Path(path).resolve())
        if path == current_python:
            # Already running this version
            return

        # Try whether this Python works
        # SPEC: SRS-F001-python-detection - Skip non-functional Python binaries
        # Action: Continue to next candidate if this Python fails basic execution
        try:
            subprocess.check_call(
                [path, "-c", "print(1)"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except subprocess.CalledProcessError:
            continue

        # Re-exec with this Python
        argv = [Path(path).name] + sys.argv
        os.environ["APPENV_BEST_PYTHON"] = path
        os.execv(path, argv)

    # No suitable Python found
    if max_version:
        print(f"Could not find Python >={min_version}, <{max_version}")
    else:
        print(f"Could not find Python >= {min_version}")
    print("Available versions:")
    for version, path in available:
        print(f"  python{version}: {path}")
    sys.exit(EXIT_CODE_DATAERR)


def detect_project_type(base):
    """Detect project type based on present files.

    Returns: "pyproject" or None
    """
    if (base / PYPROJECT_TOML).exists():
        return "pyproject"
    return None


def cmd(c, merge_stderr=True, quiet=False, cwd=None):
    # SPEC: SRS-F002-command-execution - Provide actionable error context for failures
    # Action: Print command output then raise ValueError with full context
    try:
        is_shell = isinstance(c, str)
        cmd_list = cast("list[str]", [c] if is_shell else c)
        stderr = subprocess.STDOUT if merge_stderr else None
        return subprocess.check_output(cmd_list, shell=is_shell, stderr=stderr, cwd=cwd)
    except subprocess.CalledProcessError as e:
        if not quiet:
            print(f"{c} returned with exit code {e.returncode}")
            print(e.output.decode("utf-8", "replace"))
        raise ValueError(e.output.decode("utf-8", "replace")) from e


def has_nix():
    """Check if nix is available."""
    return shutil.which("nix") is not None


def verbose_print(*args, **kwargs):
    """Print only if APPENV_VERBOSE is set.

    Used for output during symlink calls (app bootstrap).
    Meta commands (init, update-lockfile, etc.) always print.
    """
    if os.environ.get("APPENV_VERBOSE"):
        print(*args, **kwargs, flush=True)


def print_colored_diff(old_content, new_content, fromfile, tofile):
    """Print a unified diff with ANSI colors.

    Returns True if there were changes, False otherwise.
    """
    red = "\033[31m"
    green = "\033[32m"
    cyan = "\033[36m"
    reset = "\033[0m"

    diff = difflib.unified_diff(
        old_content.splitlines(keepends=True),
        new_content.splitlines(keepends=True),
        fromfile=fromfile,
        tofile=tofile,
    )
    has_changes = False
    for line in diff:
        has_changes = True
        if line.startswith(("---", "+++", "@@")):
            print(cyan + line + reset, end="")
        elif line.startswith("-"):
            print(red + line + reset, end="")
        elif line.startswith("+"):
            print(green + line + reset, end="")
        else:
            print(line, end="")
    return has_changes


# Global cache for uv binary path
_uv_bin_cache = None

# Minimum uv version required for pyproject workflow
UV_MIN_VERSION = (0, 5, 0)


def parse_uv_version(version_str):
    """Parse uv version string like '0.5.11' to tuple."""
    # Remove leading 'v' if present
    version_str = version_str.lstrip("v")
    parts = version_str.split(".")
    # SPEC: SRS-F003-uv-version-parsing - Graceful fallback for malformed versions
    # Action: Return (0, 0, 0) sentinel that fails comparison, triggering warning
    try:
        return (int(parts[0]), int(parts[1]), int(parts[2]) if len(parts) > 2 else 0)
    except (ValueError, IndexError):
        return (0, 0, 0)


def check_uv_version():
    """Check uv version and return version tuple.

    Exits with error if version is too old.
    """
    uv_bin = _uv_bin_cache or shutil.which("uv")
    if not uv_bin:
        raise RuntimeError("uv not found")

    # SPEC: SRS-F004-uv-version-check - Validate uv meets minimum requirements
    # Action: Exit with actionable upgrade instructions if version too old;
    # warn but proceed with degraded functionality if version cannot be determined.
    try:
        result = subprocess.run(
            [uv_bin, "--version"],
            capture_output=True,
            text=True,
            check=True,
        )
        # Output format: "uv 0.10.3 (c75a0c625 2026-02-16)"
        version_str = result.stdout.strip().split()[1]
        version = parse_uv_version(version_str)

        if version < UV_MIN_VERSION:
            min_str = ".".join(str(v) for v in UV_MIN_VERSION)
            print(f"Error: uv version {version_str} is too old.")
            print(f"Minimum required version: {min_str}")
            print(f"uv binary: {uv_bin}")
            print()
            print("To upgrade uv:")
            print("  curl -LsSf https://astral.sh/uv/install.sh | sh")
            print()
            print("Or with nix:")
            print("  nix profile install nixpkgs#uv")
            print()
            print("Or remove outdated local uv:")
            print("  rm -rf .appenv/.uv")
            sys.exit(EXIT_CODE_UNAVAILABLE)

        return version
    # SPEC: SRS-F004-uv-version-check - Handle uv executable failures
    # Action: Warn and return sentinel (0,0,0) which fails comparison, allowing
    # operation to proceed with potential version issues visible to user
    except subprocess.CalledProcessError as e:
        print(f"Warning: Could not determine uv version: {e}")
        print(f"  uv binary: {uv_bin}")
        print("  Proceeding anyway - sync operations may fail if uv is too old")
        return (0, 0, 0)
    # SPEC: SRS-F004-uv-version-check - Handle unexpected uv --version output format
    # Action: Warn and return sentinel (0,0,0) allowing degraded operation
    except (IndexError, ValueError) as e:
        print(f"Warning: Could not parse uv version: {e}")
        print(f"  uv binary: {uv_bin}")
        print("  Proceeding anyway - sync operations may fail if uv is too old")
        return (0, 0, 0)


def get_uv_bin(base=None):
    """Get path to uv binary.

    Priority:
    1. uv in PATH → use it
    2. nix-build '<nixpkgs>' -A uv → cheap, from local channel
       (fallback to nix build nixpkgs#uv if version < 0.5)
    3. pip install uv → use it
    """
    global _uv_bin_cache

    if _uv_bin_cache:
        return _uv_bin_cache

    # 1. Check PATH
    uv_in_path = shutil.which("uv")
    if uv_in_path:
        _uv_bin_cache = uv_in_path
        return uv_in_path

    # 2. Build with nix (try cheap channel first, fallback to fresh nixpkgs)
    if base and has_nix():
        uv_local = base / ".appenv" / ".uv" / "bin" / "uv"
        uv_out = base / ".appenv" / ".uv"
        verbose_print("Building uv with nix ...")

        # Try cheap nix-build from local channel first
        result = subprocess.run(
            ["nix-build", "<nixpkgs>", "-A", "uv", "-o", str(uv_out)],
            capture_output=True,
        )

        # Check if version is recent enough (>= 0.5)
        if result.returncode == 0 and uv_local.exists():
            # SPEC: SRS-F004-uv-version-check - Handle nix-built uv check failures
            try:
                version_result = subprocess.run(
                    [str(uv_local), "--version"],
                    capture_output=True,
                    text=True,
                    check=True,
                )
                version_str = version_result.stdout.strip().split()[1]
                version = parse_uv_version(version_str)

                if version >= (0, 5, 0):
                    _uv_bin_cache = str(uv_local)
                    return str(uv_local)

                verbose_print(
                    f"nix-build uv version {version_str} too old, trying nix build ..."
                )
            except (subprocess.CalledProcessError, IndexError, ValueError):
                verbose_print(
                    "Could not determine nix-build uv version, trying nix build ..."
                )

        # Fallback: expensive but fresh nix build from nixpkgs flake
        subprocess.run(
            ["nix", "build", "nixpkgs#uv", "--out-link", str(uv_out)],
            check=True,
        )
        _uv_bin_cache = str(uv_local)
        return str(uv_local)

    # 3. pip install fallback
    verbose_print("Installing uv via pip ...")
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


def ensure_uv_version():
    """Ensure uv version is new enough for pyproject workflow."""
    check_uv_version()


def uv_cmd(args, verbose=False, **kwargs):
    """Execute uv command.

    Args:
        args: Command arguments for uv
        verbose: If True, pass -v flag to uv for verbose output and print it
        **kwargs: Additional arguments passed to cmd()
    """
    uv_bin = _uv_bin_cache or shutil.which("uv")
    if not uv_bin:
        raise RuntimeError("uv not found. Call ensure_uv() first.")
    cmd_args = [uv_bin]
    if verbose:
        cmd_args.append("-v")
    cmd_args.extend(str(arg) for arg in args)

    # Show command if APPENV_VERBOSE is set
    verbose_print(f"Running: {' '.join(cmd_args)}")

    output = cmd(cmd_args, **kwargs)
    if verbose and output:
        print(output.decode("utf-8", "replace"), end="")
    return output


def python(path, c, **kwargs):
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
        verbose_print("Deleting unclean target")
        cmd(["rm", "-rf", str(target)])
    verbose_print("Creating venv with uv ...")
    # Note: venv doesn't need --project, explicit python path is given
    uv_cmd(["venv", "--python", sys.executable, str(target)])


def parse_editable_spec(spec):
    """Parse an editable install spec like '-e ./path' or '-e /absolute/path'.

    Returns dict with 'path' and 'package_name', or None if parsing fails.

    Supports:
        -e ./relative/path
        -e ../relative/path
        -e /absolute/path
        -e path  (no leading ./ or /)

    Does NOT support:
        -e git+... (git URLs)
        -e package @ path (PEP 508 direct references)
    """
    if not spec.startswith("-e "):
        return None

    path_part = spec[3:].strip()

    # Skip git URLs and PEP 508 direct references
    if path_part.startswith(("git+", "git://", "hg+", "svn+")):
        return None
    if " @ " in path_part:
        return None

    # Handle extras like `-e ./path[extra]`
    extras = []
    if "[" in path_part and "]" in path_part:
        start = path_part.index("[")
        end = path_part.index("]")
        extras_str = path_part[start + 1 : end]
        extras = [e.strip() for e in extras_str.split(",") if e.strip()]
        path_part = path_part[:start] + path_part[end + 1 :]

    return {"path": path_part, "extras": extras}


def extract_package_name_from_path(path, base_dir):
    """Extract package name from a local path.

    Checks for:
    1. pyproject.toml with [project] name
    2. setup.py with name= or name =

    Returns package name or None if not found.
    """
    full_path = (base_dir / path).resolve()

    # Try pyproject.toml first
    pyproject_path = full_path / PYPROJECT_TOML
    if pyproject_path.exists():
        content = pyproject_path.read_text()
        # Match name = "..." or name='...'
        match = re.search(r'^name\s*=\s*["\']([^"\']+)["\']', content, re.MULTILINE)
        if match:
            return match.group(1)

    # Try setup.py
    setup_path = full_path / "setup.py"
    if setup_path.exists():
        content = setup_path.read_text()
        # Match name="..." or name='...' or name = "..."
        match = re.search(r'name\s*=\s*["\']([^"\']+)["\']', content)
        if match:
            return match.group(1)

    return None


class AppEnv:
    def __init__(self, base, original_cwd):
        self.base = Path(base).resolve()
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
        p.add_argument(
            "-v",
            "--verbose",
            action="store_true",
            help="Show detailed information about what is being done.",
        )
        p.set_defaults(func=self.update_lockfile)

        p = subparsers.add_parser("init", help="Create a new pyproject.toml project.")
        p.set_defaults(func=self.init)

        p = subparsers.add_parser(
            "migrate", help="Migrate from requirements.txt to pyproject.toml."
        )
        p.set_defaults(func=self.migrate)

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

        p = subparsers.add_parser(
            "uv",
            help="Run uv with the appenv-configured uv binary.",
        )
        p.set_defaults(func=self.run_uv)

        # profiling subcommand with list/show
        p = subparsers.add_parser("profiling", help="Manage profiling data.")
        profiling_subparsers = p.add_subparsers(dest="profiling_command")

        p_list = profiling_subparsers.add_parser("list", help="List recent profiles.")
        p_list.add_argument(
            "-n", "--count", type=int, default=10, help="Number of profiles to show."
        )
        p_list.set_defaults(func=self.profiling_list)

        p_show = profiling_subparsers.add_parser(
            "show", help="Show latest profile with pstats."
        )
        p_show.add_argument("file", nargs="?", help="Specific profile file to show.")
        p_show.set_defaults(func=self.profiling_show)

        p_snakeviz = profiling_subparsers.add_parser(
            "snakeviz", help="Show latest profile with snakeviz (interactive web UI)."
        )
        p_snakeviz.add_argument(
            "file", nargs="?", help="Specific profile file to show."
        )
        p_snakeviz.set_defaults(func=self.profiling_snakeviz)

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

        # Profiling support via APPENV_PROFILE=1
        if os.environ.get("APPENV_PROFILE"):
            if os.environ.get("APPENV_PROFILE_OUTPUT"):
                profile_output = os.environ["APPENV_PROFILE_OUTPUT"]
            else:
                profiling_dir = self.appenv_dir / "profiling"
                profiling_dir.mkdir(parents=True, exist_ok=True)
                timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
                profile_output = str(profiling_dir / f"{command}-{timestamp}.prof")
            print(f"Profile written to: {profile_output}")
            venv_python = env_dir / "bin" / "python"
            os.execv(
                str(venv_python),
                [
                    str(venv_python),
                    "-m",
                    "cProfile",
                    "-o",
                    profile_output,
                    str(cmd_path),
                ]
                + argv[1:],
            )
        else:
            os.execv(str(cmd_path), argv)

    def prepare(self, args=None, remaining=None):
        os.chdir(self.base)

        project_type = detect_project_type(self.base)

        verbose_print(f"Mode: {project_type}")

        if project_type == "pyproject":
            return self._prepare_pyproject()
        else:
            print(f"No {PYPROJECT_TOML} found.")
            sys.exit(EXIT_CODE_NOINPUT)

    def _prepare_pyproject(self):
        """Prepare environment for pyproject.toml using uv native workflow."""
        # Store venv in .appenv/venv to avoid deployment issues
        # (batou and similar tools can ignore .appenv)
        venv_real = self.appenv_dir / "venv"
        venv_link = self.base / ".venv"
        lock_file = self.base / UV_LOCK
        old_appenv = self.appenv_dir
        pyproject_file = self.base / PYPROJECT_TOML

        verbose_print("Workflow: pyproject.toml (uv native)")

        # Ensure uv.lock exists
        if not lock_file.exists():
            print(f"No {UV_LOCK} found. Run: ./appenv update-lockfile")
            sys.exit(EXIT_CODE_NOINPUT)

        ensure_uv(self.base)
        ensure_uv_version()

        # Tell uv where to put/find the venv
        os.environ["UV_PROJECT_ENVIRONMENT"] = str(venv_real)

        # Show verbose info
        verbose_print(f"Project base: {self.base}")
        verbose_print(f"pyproject.toml: {pyproject_file}")
        verbose_print(f"uv.lock: {lock_file}")
        verbose_print(f"venv: {venv_real}")
        verbose_print(f"uv binary: {get_uv_bin(self.base)}")
        verbose_print(f"Python: {Path(sys.executable).resolve()}")

        # Ensure .appenv directory exists
        if not self.appenv_dir.exists():
            self.appenv_dir.mkdir()

        # Create venv if needed or check integrity
        if not venv_real.exists() or not (venv_real / "bin" / "python").exists():
            if venv_real.exists():
                verbose_print("Corrupted venv detected, removing ...")
                shutil.rmtree(venv_real)
            verbose_print("Creating venv with uv ...")
            # Use current Python (already selected by ensure_best_python)
            # Explicit path avoids uv downloading its own (breaks on NixOS)
            uv_cmd(["venv", "--python", sys.executable, str(venv_real)])

        # Sync dependencies (idempotent)
        verbose_print("Syncing dependencies (uv sync) ...")
        uv_cmd(["sync"])

        # Show venv python info AFTER sync (version may have changed)
        venv_python = venv_real / "bin" / "python"
        if venv_python.exists():
            verbose_print(f"Venv Python: {venv_python}")
            verbose_print(f"Venv Python (realpath): {venv_python.resolve()}")
            result = cmd([str(venv_python), "--version"], quiet=True)
            verbose_print(f"Venv Python version: {result.decode().strip()}")

        # Create symlink for tool compatibility
        # (e.g., IDEs, formatters, linters that expect .venv)
        # Always update symlink unless .venv is a real directory
        if venv_link.is_symlink():
            venv_link.unlink()
        if not venv_link.exists():
            venv_link.symlink_to(".appenv/venv")

        # Cleanup old .appenv/current symlink first
        # (Python 3.14 rmtree doesn't like symlinks)
        current_link = old_appenv / "current"
        if current_link.is_symlink():
            current_link.unlink()

        # Cleanup old .appenv hash-based venvs
        # But keep .appenv/venv (the current venv location) and .uv
        if old_appenv.exists():
            for path in list(old_appenv.iterdir()):
                if path.name != "venv" and path.name != ".uv":
                    verbose_print(f"Removing old .appenv entry: {path.name} ...")
                    if path.is_dir():
                        shutil.rmtree(path)
                    else:
                        path.unlink()

        return str(venv_real)

    def init(self, args=None, remaining=None):
        """Create a new pyproject.toml project."""
        target = self.original_cwd.resolve()
        pyproject_file = target / PYPROJECT_TOML

        if pyproject_file.exists():
            print(f"pyproject.toml already exists in {target}.")
            print("Nothing to do.")
            print("Edit pyproject.toml manually to make changes.")
            return

        print("Let's create a new pyproject.toml project.\n")

        command_name = input("What should the command be named? [app] ").strip()
        if not command_name:
            command_name = "app"

        print("\nEnter dependencies (one per line, empty line to finish):")
        print(f"  Default: {command_name}")
        dependencies = []
        while True:
            dep = input("  Dependency: ").strip()
            if not dep:
                break
            dependencies.append(dep)
        if not dependencies:
            dependencies = [command_name]

        project_name = input(f"\nProject name [{command_name}-app]: ").strip()
        if not project_name:
            project_name = f"{command_name}-app"

        description = input("Description []: ").strip()

        python_version = input("Minimum Python version [3.10]: ").strip()
        if not python_version:
            python_version = "3.10"

        self._create_pyproject(
            target=target,
            project_name=project_name,
            description=description,
            dependencies=dependencies,
            editable_sources={},
            python_version=python_version,
            command_name=command_name,
        )

    def migrate(self, args=None, remaining=None):
        """Migrate from requirements.txt to pyproject.toml."""
        target = self.original_cwd.resolve()
        requirements_file = target / "requirements.txt"
        pyproject_file = target / PYPROJECT_TOML

        existing_pyproject = None
        if pyproject_file.exists():
            existing_pyproject = pyproject_file.read_text()
            if self._has_project_section(existing_pyproject):
                print(f"pyproject.toml already has [project] section in {target}.")
                print("Nothing to do.")
                return
            print(f"Adding [project] section to existing pyproject.toml.\n")

        if not requirements_file.exists():
            print(f"No requirements.txt found in {target}.")
            print("Use 'init' to create a new project.")
            return

        print("Migrating from requirements.txt to pyproject.toml...\n")
        deps_content = requirements_file.read_text().strip()

        # Parse dependencies - separate editable from regular
        all_deps = [
            line.strip()
            for line in deps_content.splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
        editable_specs = [d for d in all_deps if d.startswith("-e ")]
        dependencies = [d for d in all_deps if not d.startswith("-e ")]

        # Process editable installs
        editable_sources = {}
        editable_warnings = []
        for spec in editable_specs:
            parsed = parse_editable_spec(spec)
            if not parsed:
                editable_warnings.append(f"{spec} (unsupported format)")
                continue

            package_name = extract_package_name_from_path(parsed["path"], target)
            if not package_name:
                editable_warnings.append(
                    f"{spec} (no pyproject.toml or setup.py found)"
                )
                continue

            # Build dependency string with extras if present
            dep_str = package_name
            if parsed["extras"]:
                dep_str = f"{package_name}[{','.join(parsed['extras'])}]"
            dependencies.append(dep_str)

            # Build source config
            path = parsed["path"]
            if not path.startswith(("./", "../", "/")):
                path = "./" + path
            editable_sources[package_name] = {"path": path, "editable": True}

        if editable_warnings:
            print(f"Warning: {len(editable_warnings)} editable install(s) skipped:")
            for warn in editable_warnings:
                print(f"  - {warn}")
            print("Add them manually to pyproject.toml if needed.\n")

        if editable_sources:
            print(f"Found {len(editable_sources)} editable install(s):")
            for name, src in editable_sources.items():
                print(f"  - {name} ({src['path']})")
            print()

        print(f"Found {len(dependencies)} dependency(ies): {', '.join(dependencies)}")

        # Parse python preference from requirements.txt
        python_version = "3.10"
        for line in deps_content.splitlines():
            if line.startswith("# appenv-python-preference: "):
                raw = line.split(":")[1]
                preferences = [x.strip() for x in raw.split(",") if x.strip()]
                if preferences:
                    preferences_sorted = sorted(
                        preferences, key=lambda s: [int(u) for u in s.split(".")]
                    )
                    python_version = preferences_sorted[0]
                    print(f"Found python preference: {', '.join(preferences)}")
                    print(f"Using minimum version: {python_version}")
                break

        # Use directory name as project name
        project_name = target.name

        self._create_pyproject(
            target=target,
            project_name=project_name,
            description="",
            dependencies=dependencies,
            editable_sources=editable_sources,
            python_version=python_version,
            command_name=None,  # Find existing symlinks
            existing_content=existing_pyproject,
        )
        print(
            "\nrequirements.txt kept as legacy. Delete it when migration is complete."
        )

    @staticmethod
    def _has_project_section(content):
        """Check if TOML content has a [project] section."""
        for line in content.splitlines():
            stripped = line.strip()
            if stripped == "[project]" or stripped.startswith("[project."):
                return True
        return False

    def _create_pyproject(
        self,
        target,
        project_name,
        description,
        dependencies,
        editable_sources,
        python_version,
        command_name,
        existing_content=None,
    ):
        """Create pyproject.toml, appenv bootstrap, symlink, and lockfile."""
        pyproject_file = target / PYPROJECT_TOML
        appenv_script = target / "appenv"

        # Generate [project] section
        if dependencies:
            deps_toml = ",\n    ".join(f'"{dep}"' for dep in dependencies)
            deps_block = f"[\n    {deps_toml},\n]"
        else:
            deps_block = "[]"

        project_section = f"""[project]
name = "{project_name}"
version = "0.1.0"
description = "{description}"
dependencies = {deps_block}
requires-python = ">={python_version}"
"""

        # Generate [tool.uv.sources] section if needed
        sources_section = ""
        if editable_sources:
            sources_lines = ["[tool.uv.sources]"]
            for pkg_name, src_config in sorted(editable_sources.items()):
                path = src_config["path"]
                sources_lines.append(
                    f'{pkg_name} = {{ path = "{path}", editable = true }}'
                )
            sources_section = "\n" + "\n".join(sources_lines) + "\n"

        # Merge with existing content or create new
        if existing_content:
            # Ensure existing content ends with newline for clean merge
            pyproject_content = existing_content.rstrip() + "\n\n" + project_section
            if sources_section:
                pyproject_content += sources_section
            print(f"\nUpdated {PYPROJECT_TOML}")
        else:
            pyproject_content = project_section + sources_section
            print(f"\nCreated {PYPROJECT_TOML}")

        pyproject_file.write_text(pyproject_content)

        # Create appenv bootstrap if needed
        if not appenv_script.exists():
            bootstrap_data = Path(__file__).read_bytes()
            appenv_script.write_bytes(bootstrap_data)
            appenv_script.chmod(0o755)
            print("Created appenv bootstrap script")

        # Handle symlink
        if command_name:
            # Fresh project: create new symlink
            command_link = target / command_name
            if command_link.is_symlink() or command_link.exists():
                command_link.unlink(missing_ok=True)
            command_link.symlink_to("appenv")
            print(f"Created {command_name} symlink")
        else:
            # Migration: find existing symlinks
            existing_symlinks = [
                path.name
                for path in target.iterdir()
                if path.is_symlink() and path.resolve() == appenv_script.resolve()
            ]
            if existing_symlinks:
                print(f"Found existing symlink(s): {', '.join(existing_symlinks)}")
                command_name = existing_symlinks[0]
            else:
                command_link = target / project_name
                command_link.symlink_to("appenv")
                print(f"Created {project_name} symlink")
                command_name = project_name

        print("\nDone. pyproject.toml created.")

        # Auto-generate lockfile
        print("\nGenerating lockfile ...")
        self.update_lockfile(
            argparse.Namespace(diff=False, verbose=False), remaining=None
        )
        print(f"\nRun `./{command_name}` to bootstrap and run")

    def python(self, args, remaining):
        self.run("python", remaining)

    def run_script(self, args, remaining):
        self.run(args.script, remaining)

    def run_uv(self, args, remaining):
        """Run uv with the appenv-configured uv binary."""
        ensure_uv(self.base)
        uv_bin = get_uv_bin(self.base)

        # Tell uv where the venv lives (in .appenv/venv, not .venv)
        venv_real = self.appenv_dir / "venv"
        os.environ["UV_PROJECT_ENVIRONMENT"] = str(venv_real)

        uv_argv = [uv_bin] + remaining
        os.chdir(self.base)
        os.execv(uv_bin, uv_argv)

    def show_version(self, args=None, remaining=None):
        """Show appenv version."""
        print(f"appenv {__version__}")

    def profiling_list(self, args, remaining=None):
        """List recent profiling files."""
        profiling_dir = self.appenv_dir / "profiling"
        if not profiling_dir.exists():
            print("No profiling data found.")
            return

        profiles = sorted(
            profiling_dir.glob("*.prof"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )

        if not profiles:
            print("No profiling data found.")
            return

        count = min(args.count, len(profiles))
        print(f"Showing {count} of {len(profiles)} profiles:\n")
        for i, profile in enumerate(profiles[:count], 1):
            mtime = datetime.fromtimestamp(profile.stat().st_mtime)
            size = profile.stat().st_size
            print(
                f"  {i:3}. {profile.name}  ({size:,} bytes, {mtime:%Y-%m-%d %H:%M:%S})"
            )

    def profiling_show(self, args, remaining=None):
        """Show profile with pstats."""
        profiling_dir = self.appenv_dir / "profiling"

        if args.file:
            profile_path = profiling_dir / args.file
            if not profile_path.exists():
                print(f"Profile not found: {args.file}")
                sys.exit(EXIT_CODE_NOINPUT)
        else:
            if not profiling_dir.exists():
                print("No profiling data found.")
                sys.exit(EXIT_CODE_NOINPUT)

            profiles = sorted(
                profiling_dir.glob("*.prof"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )

            if not profiles:
                print("No profiling data found.")
                sys.exit(EXIT_CODE_NOINPUT)

            profile_path = profiles[0]
            print(f"Showing latest profile: {profile_path.name}\n")

        import pstats

        stats = pstats.Stats(str(profile_path))
        stats.sort_stats("cumulative")
        stats.print_stats(20)

    def profiling_snakeviz(self, args, remaining=None):
        """Show profile with snakeviz (interactive web UI)."""
        profiling_dir = self.appenv_dir / "profiling"

        if args.file:
            profile_path = profiling_dir / args.file
            if not profile_path.exists():
                print(f"Profile not found: {args.file}")
                sys.exit(EXIT_CODE_NOINPUT)
        else:
            if not profiling_dir.exists():
                print("No profiling data found.")
                sys.exit(EXIT_CODE_NOINPUT)

            profiles = sorted(
                profiling_dir.glob("*.prof"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )

            if not profiles:
                print("No profiling data found.")
                sys.exit(EXIT_CODE_NOINPUT)

            profile_path = profiles[0]
            print(f"Opening latest profile: {profile_path.name}")

        os.execv(
            sys.executable,
            [
                sys.executable,
                "-m",
                "uv",
                "run",
                "--with",
                "snakeviz",
                "snakeviz",
                str(profile_path),
            ],
        )

    def reset(self, args=None, remaining=None):
        """Reset all virtual environments."""
        venv_link = self.base / ".venv"
        venv_real = self.appenv_dir / "venv"

        # Remove symlink if it exists
        if venv_link.is_symlink():
            print(f"Removing {venv_link} symlink ...")
            venv_link.unlink()

        # Remove real venv in .appenv
        if venv_real.exists():
            print(f"Removing {venv_real} ...")
            shutil.rmtree(venv_real)

        # Legacy: also handle old .venv directory (pre-migration)
        if venv_link.exists() and not venv_link.is_symlink():
            print(f"Removing old {venv_link} ...")
            shutil.rmtree(venv_link)

        # Clean up old hash-based venvs in .appenv (keep .uv)
        if self.appenv_dir.exists():
            for path in list(self.appenv_dir.iterdir()):
                if path.name not in (".uv", "venv"):
                    verbose_print(f"Removing {path} ...")
                    if path.is_dir():
                        shutil.rmtree(path)
                    else:
                        path.unlink()

    def update_lockfile(self, args=None, remaining=None):
        """Update lockfile.

        For pyproject.toml: uses uv lock (native)
        For requirements.txt: uses uv pip compile (legacy)
        """
        ensure_uv(self.base)
        os.chdir(self.base)

        project_type = detect_project_type(self.base)
        verbose: bool = bool(args and getattr(args, "verbose", False))

        # Show what we're doing (only in verbose mode)
        verbose_print(f"Base directory: {self.base}")
        if project_type == "pyproject":
            source_file = self.base / PYPROJECT_TOML
            lock_file = self.base / UV_LOCK
            verbose_print("Mode: pyproject.toml (native uv workflow)")
            verbose_print(f"Reading: {source_file}")
            verbose_print(f"Lockfile: {lock_file}")
        else:
            print(f"No {PYPROJECT_TOML} found.")
            sys.exit(EXIT_CODE_NOINPUT)

        self._update_lockfile_pyproject(args, verbose)

    def _update_lockfile_pyproject(self, args, verbose=False):
        """Update uv.lock using uv lock (native workflow)."""
        ensure_uv_version()

        lock_file = self.base / UV_LOCK

        # Read existing lockfile for comparison
        old_lines: set[str] = set()
        if lock_file.exists():
            if verbose:
                print(f"Reading existing lockfile: {lock_file}")
            old_lines = set(
                stripped
                for line in lock_file.read_text().splitlines()
                if (stripped := line.strip()) and not stripped.startswith("#")
            )

        if args and args.diff:
            print("Checking lockfile changes ...")
            if verbose:
                print("Running uv lock in temp directory (dry run)")
            old_content = lock_file.read_text() if lock_file.exists() else ""

            # Run uv lock in temp directory to avoid modifying real lockfile
            with tempfile.TemporaryDirectory() as tmpdir:
                tmp_pyproject = Path(tmpdir) / PYPROJECT_TOML
                tmp_lock = Path(tmpdir) / UV_LOCK
                shutil.copy(self.base / PYPROJECT_TOML, tmp_pyproject)
                uv_cmd(["lock"], verbose=verbose, cwd=tmpdir)
                new_content = tmp_lock.read_text() if tmp_lock.exists() else ""

            has_changes = print_colored_diff(
                old_content, new_content, UV_LOCK, f"{UV_LOCK} (new)"
            )
            if not has_changes:
                print("No changes")
        else:
            # Run uv lock to update
            if verbose:
                print("Running: uv lock")
            uv_cmd(["lock"], verbose=verbose)

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

            is_new = len(old_lines) == 0
            if n_added == 0 and n_removed == 0 and not is_new:
                print("No changes")
            else:
                added_str = f"{green}+{n_added}{reset}"
                removed_str = f"{red}-{n_removed}{reset}"
                if is_new:
                    print(f"{check} Created ({added_str} lines)")
                else:
                    print(f"{check} Updated ({added_str} / {removed_str} lines)")


def main():
    base = Path(__file__).parent
    original_cwd = Path.cwd()

    # Select best Python for pyproject.toml workflow
    ensure_best_python(base)

    # Clear PYTHONPATH to ensure clean isolated environment.
    # Historical note: Some systems set PYTHONPATH globally which can interfere
    # with venv isolation. Clearing it ensures the venv's site-packages take precedence.
    os.environ.pop("PYTHONPATH", None)

    # Determine whether we're being called as appenv or as an application name
    application_name = Path(__file__).stem

    appenv = AppEnv(base, original_cwd)
    if application_name == "appenv":
        appenv.meta()
    else:
        appenv.run(application_name, sys.argv[1:])


if __name__ == "__main__":  # pragma: no cover
    main()
