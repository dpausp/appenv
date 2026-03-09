#!/usr/bin/env python3
# appenv - a single file 'application in venv bootstrapping and updating
#          mechanism for python-based (CLI) applications

# Assumptions:
#
#   - the appenv file is placed in a repo with the name of the application
#   - the name of the application/file becomes the CLI entrypoint via symlink
#   - Python 3.10+
#   - system has usable uv (see UV_MIN_VERSION) or has Nix to install uv on-demand
#   - pyproject.toml next to the appenv file

# TODO
#
# - provide a `clone` meta command to create a new project based on this one
#   maybe use an entry point to allow further initialisation of the clone.

__version__ = "2026.3.5"

import argparse
import difflib
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import cast

# Global logger instance
log = logging.getLogger("appenv")

# Constants
PYPROJECT_TOML = "pyproject.toml"
UV_LOCK = "uv.lock"
UV_MIN_VERSION = (0, 5, 0)

# Exit codes (BSD sysexits.h conventions)
EXIT_CODE_DATAERR = 65
EXIT_CODE_NOINPUT = 67
EXIT_CODE_UNAVAILABLE = 68


def cmd(c, merge_stderr=True, quiet=False, cwd=None):
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
        (f"3.{i}", path)
        for i in range(10, 25)
        if (path := shutil.which(f"python3.{i}"))
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
        try:
            subprocess.check_call(
                [path, "-c", "print(1)"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except subprocess.CalledProcessError:
            continue

        # Re-exec with this Python
        argv = [Path(path).name, *sys.argv]
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


def has_pyproject(base):
    return (base / PYPROJECT_TOML).exists()


def setup_logging(command_name: str, base: Path) -> None:
    """Setup command-specific logging to file and optional console."""
    # Only setup logging if base directory exists
    if not base.exists():
        return

    log_dir = base / ".appenv" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    cleanup_old_logs(log_dir)

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    log_file = log_dir / f"{command_name}-{timestamp}.log"

    log.setLevel(logging.DEBUG)

    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )
    file_handler.setFormatter(file_formatter)
    log.addHandler(file_handler)

    if os.environ.get("APPENV_VERBOSE"):
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.DEBUG)
        console_formatter = logging.Formatter("%(message)s")
        console_handler.setFormatter(console_formatter)
        log.addHandler(console_handler)


def cleanup_old_logs(log_dir: Path, max_age_days: int = 7) -> None:
    """Remove logs older than max_age_days."""
    cutoff = datetime.now() - timedelta(days=max_age_days)

    for log_file in log_dir.glob("*.log"):
        if datetime.fromtimestamp(log_file.stat().st_mtime) < cutoff:
            log_file.unlink()


def verbose_print(*args, **kwargs):
    """DEPRECATED: Use log.debug() instead."""
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


def parse_uv_version(version_str):
    """Parse uv version string like '0.5.11' to tuple."""
    # Remove leading 'v' if present
    version_str = version_str.lstrip("v")
    parts = version_str.split(".")
    try:
        return (int(parts[0]), int(parts[1]), int(parts[2]) if len(parts) > 2 else 0)
    except (ValueError, IndexError):
        return (0, 0, 0)


def get_uv_version(uv_bin):
    """Get uv version string if uv meets minimum version.

    Returns version string like '0.5.11' or None if invalid/too old.
    """
    try:
        version_str = _get_uv_version_raw(uv_bin)
        if version_str is None:
            return None

        version = parse_uv_version(version_str)

        if version >= UV_MIN_VERSION:
            return version_str

        return None
    except (subprocess.CalledProcessError, IndexError, ValueError):
        return None


def _get_uv_version_raw(uv_bin):
    """Get raw uv version string without validation.

    Returns version string like '0.5.11' or None on error.
    """
    try:
        result = subprocess.run(
            [uv_bin, "--version"],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip().split()[1]
    except (subprocess.CalledProcessError, IndexError, AttributeError):
        return None


def ensure_uv(base=None):
    """Ensure uv is available and meets minimum version.

    Exits with error if uv is not available or too old.
    """
    uv_bin = get_uv_bin(base)
    version_str = _get_uv_version_raw(uv_bin)

    if version_str is None:
        print("Warning: Could not determine uv version")
        print(f"  uv binary: {uv_bin}")
        print("  Proceeding anyway - sync operations may fail if uv is too old")
        return uv_bin

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

    return uv_bin


def _cleanup_appenv_uv(base):
    """Remove leftover .appenv/.uv directory."""
    if base:
        appenv_uv = base / ".appenv" / ".uv"
        if appenv_uv.exists():
            shutil.rmtree(appenv_uv)


def _try_uv_from_path(base):
    """Try to find uv in PATH."""
    uv_in_path = shutil.which("uv")
    log.debug(f"_try_uv_from_path: uv in PATH = {uv_in_path}")
    if uv_in_path:
        uv_bin = Path(uv_in_path)
        version = get_uv_version(uv_bin)
        log.debug(
            f"_try_uv_from_path: version at {uv_bin} valid = {version is not None}"
        )
        if version:
            _cleanup_appenv_uv(base)
            return uv_bin
    return None


def _try_uv_from_appenv_dir(base):
    """Try to find uv in .appenv/.uv from previous run."""
    if not base:
        log.debug("_try_uv_from_appenv_dir: no base provided")
        return None
    uv_local = base / ".appenv" / ".uv" / "bin" / "uv"
    uv_local.exists()
    version = get_uv_version(uv_local)
    log.debug(
        f"_try_uv_from_appenv_dir: {uv_local} "
        f"exists={uv_local.exists()}, version valid={version is not None}"
    )
    if uv_local.exists() and version:
        return uv_local
    return None


def _try_uv_from_nix(base):
    """Try to build uv with nix."""
    nix_bin = shutil.which("nix")
    log.debug(f"_try_uv_from_nix: base={base}, nix_bin={nix_bin}")

    if not base or nix_bin is None:
        log.debug(
            f"_try_uv_from_nix: skipping "
            f"(base={base}, nix in PATH={nix_bin is not None})"
        )
        return None

    uv_local = base / ".appenv" / ".uv" / "bin" / "uv"
    uv_out = base / ".appenv" / ".uv"

    # Check if we already have a valid .appenv/.uv
    if uv_local.exists():
        version = get_uv_version(uv_local)
        log.debug(
            f"_try_uv_from_nix: local uv exists at {uv_local}, "
            f"version valid={version is not None}"
        )
        if version:
            return uv_local
        log.debug(".appenv/.uv version too old, updating ...")

    # Need to build/update uv with nix
    if nix_bin is None:
        log.debug("_try_uv_from_nix: nix not found in PATH, skipping nix build")
        return None
    log.debug(f"_try_uv_from_nix: nix found at {nix_bin}, attempting build ...")

    # Try cheap nix-build from local channel first
    result = subprocess.run(
        ["nix-build", "<nixpkgs>", "-A", "uv", "-o", str(uv_out)],
        capture_output=True,
    )

    # Check if version is recent enough (>= 0.5)
    if result.returncode == 0 and uv_local.exists():
        if get_uv_version(uv_local):
            return uv_local
        log.debug("nix-build uv version too old, trying nix build ...")

    # Fallback: expensive but fresh nix build from nixpkgs flake
    subprocess.run(
        ["nix", "build", "nixpkgs#uv", "--out-link", str(uv_out)],
        check=True,
    )
    return uv_local


def _try_uv_from_pip():
    """Try to install uv via pip.

    Returns None if pip is not available (e.g., on NixOS).
    """
    log.debug("_try_uv_from_pip: checking if pip is available ...")

    # Check if pip is available
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "--version"],
            check=True,
            capture_output=True,
        )
    except (subprocess.CalledProcessError, AttributeError):
        log.debug("_try_uv_from_pip: pip not available, skipping pip install")
        return None

    log.debug("_try_uv_from_pip: attempting to install uv via pip ...")
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "-q", "uv"],
            check=True,
        )
    except (subprocess.CalledProcessError, AttributeError):
        log.debug("_try_uv_from_pip: pip install failed, skipping pip install")
        return None

    # pip installs to user site or system - try to find it
    uv_in_path = shutil.which("uv")
    if uv_in_path:
        uv_bin = Path(uv_in_path)
        if get_uv_version(uv_bin):
            return uv_bin
    return None


def get_uv_bin(base=None):
    """Get path to uv binary.

    Priority:
    1. uv in PATH (>= 0.5.0) → use it (and cleanup .appenv/.uv if present)
    2. .appenv/.uv from previous run (if still valid)
    3. nix-build/nix build → build uv with nix
    4. pip install uv → install via pip
    """
    log.debug(f"get_uv_bin: searching for uv, base={base}")

    # 1. Check PATH first
    uv_bin = _try_uv_from_path(base)
    if uv_bin:
        log.debug(f"get_uv_bin: found uv in PATH at {uv_bin}")
        return uv_bin

    # 2. Check .appenv/.uv from previous run
    uv_bin = _try_uv_from_appenv_dir(base)
    if uv_bin:
        log.debug(f"get_uv_bin: found uv in .appenv/.uv at {uv_bin}")
        return uv_bin

    # 3. Build with nix
    uv_bin = _try_uv_from_nix(base)
    if uv_bin:
        log.debug(f"get_uv_bin: built uv with nix at {uv_bin}")
        return uv_bin

    # 4. pip install fallback
    log.debug("get_uv_bin: falling back to pip install")
    uv_bin = _try_uv_from_pip()
    if uv_bin:
        _cleanup_appenv_uv(base)
        return uv_bin

    raise RuntimeError("uv not found and could not be installed")


def uv_cmd(args, verbose=False, base=None, **kwargs):
    """Execute uv command.

    Args:
        args: Command arguments for uv
        verbose: If True, pass -v flag to uv for verbose output and print it
        base: Base directory for uv discovery (passed to ensure_uv)
        **kwargs: Additional arguments passed to cmd()
    """
    uv_bin = ensure_uv(base)
    cmd_args = [str(uv_bin)]
    if verbose:
        cmd_args.append("-v")
    cmd_args.extend(str(arg) for arg in args)

    # Show command if APPENV_VERBOSE is set
    log.debug(f"Running: {' '.join(cmd_args)}")

    output = cmd(cmd_args, **kwargs)
    if verbose and output:
        print(output.decode("utf-8", "replace"), end="")
    return output


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
        self._uv_bin_cache = None  # Instance-level cache for uv binary

        # Determine command name for logging
        if Path(sys.argv[0]).stem == "appenv":
            command_name = sys.argv[1] if len(sys.argv) > 1 else "help"
        else:
            command_name = Path(sys.argv[0]).stem

        # Setup logging in project base directory
        project_base = find_project_base(self.base, self.original_cwd)
        setup_logging(command_name, project_base)

    def meta(self, remaining_args: list[str] | None = None, prog: str = "appenv"):
        # Parse the appenv arguments
        parser = argparse.ArgumentParser(prog=prog)
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

        p = subparsers.add_parser(
            "settings", help="Show environment variables and settings."
        )
        p.set_defaults(func=self.settings)

        p = subparsers.add_parser("prepare", help="Prepare the venv.")
        p.set_defaults(func=self.prepare)

        p = subparsers.add_parser(
            "develop", help="Prepare the venv with dev dependencies."
        )
        p.set_defaults(func=self.develop)

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

        # Handle 'help' subcommand specially
        if remaining_args and remaining_args[0] == "help":
            parser.print_usage()
            sys.exit(0)

        args, remaining = parser.parse_known_args(remaining_args)

        if not hasattr(args, "func"):
            parser.print_usage()
            sys.exit(0)
        else:
            args.func(args, remaining)

    def run(self, command, argv):
        env_dir = Path(self._prepare_venv())
        cmd_path = env_dir / "bin" / command
        argv = [str(cmd_path), *argv]
        os.environ["APPENV_BASEDIR"] = str(self.base)
        os.chdir(self.original_cwd)

        if os.environ.get("APPENV_PROFILE"):
            if os.environ.get("APPENV_PROFILE_OUTPUT"):
                profile_output = os.environ["APPENV_PROFILE_OUTPUT"]
            else:
                profiling_dir = self.appenv_dir / "profiling"
                profiling_dir.mkdir(parents=True, exist_ok=True)
                timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
                profile_output = str(profiling_dir / f"{command}-{timestamp}.prof")
            print(f"APPENV_PROFILE enabled, profile output at {profile_output}")
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
                    *argv[1:],
                ],
            )
        else:
            os.execv(str(cmd_path), argv)

    def _prepare_venv(self, dev_mode=False):
        """Shared venv preparation logic.

        Args:
            dev_mode:
              - If True, include dev dependency group
              - If False, use --frozen flag for strict lockfile adherence.
        """
        if not has_pyproject(self.base):
            print(f"No {PYPROJECT_TOML} found.")
            sys.exit(EXIT_CODE_NOINPUT)

        os.chdir(self.base)

        venv_real = self.appenv_dir / "venv"
        venv_link = self.base / ".venv"
        lock_file = self.base / UV_LOCK
        old_appenv = self.appenv_dir
        pyproject_file = self.base / PYPROJECT_TOML

        # Ensure uv.lock exists
        if not lock_file.exists():
            print(f"No {UV_LOCK} found. Run: ./appenv update-lockfile")
            sys.exit(EXIT_CODE_NOINPUT)

        uv_bin = ensure_uv(self.base)

        # Tell uv where to put/find the venv
        os.environ["UV_PROJECT_ENVIRONMENT"] = str(venv_real)

        # Show verbose info
        log.debug(f"Project base: {self.base}")
        log.debug(f"pyproject.toml: {pyproject_file}")
        log.debug(f"uv.lock: {lock_file}")
        log.debug(f"venv: {venv_real}")
        log.debug(f"uv binary: {uv_bin}")
        try:
            uv_version = get_uv_version(uv_bin)
            log.debug(f"uv version: {uv_version or 'unknown'}")
        except (OSError, subprocess.CalledProcessError):
            log.debug("uv version: unknown")
        log.debug(f"Python: {Path(sys.executable).resolve()}")
        log.debug(f"Dev mode: {dev_mode}")

        # Ensure .appenv directory exists
        if not self.appenv_dir.exists():
            self.appenv_dir.mkdir()

        # Create venv if needed or check integrity
        if not venv_real.exists() or not (venv_real / "bin" / "python").exists():
            if venv_real.exists():
                log.debug("Corrupted venv detected, removing ...")
                shutil.rmtree(venv_real)
            log.debug("Creating venv with uv ...")
            # Use current Python (already selected by ensure_best_python)
            # Explicit path avoids uv downloading its own (breaks on NixOS, for example)
            uv_cmd(["venv", "--python", sys.executable, str(venv_real)], base=self.base)

        # Sync dependencies (idempotent)
        sync_args = ["sync"]

        if not dev_mode:
            sync_args.extend(["--no-dev", "--frozen"])

        extras = [
            e.strip()
            for e in os.environ.get("APPENV_EXTRAS", "").split(",")
            if e.strip()
        ]
        if extras:
            sync_args.extend(["--extra", ",".join(extras)])

        log.debug(f"prepare_venv activated extras/optional deps: {extras}")
        log.debug(f"prepare_venv uv args: {sync_args}")
        uv_cmd(sync_args, base=self.base)

        # Show venv python info AFTER sync (version may have changed)
        venv_python = venv_real / "bin" / "python"
        if venv_python.exists():
            log.debug(f"Venv Python: {venv_python}")
            log.debug(f"Venv Python (realpath): {venv_python.resolve()}")
            result = cmd([str(venv_python), "--version"], quiet=True)
            log.debug(f"Venv Python version: {result.decode().strip()}")

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
        # But keep .appenv/venv (current venv), .uv (local uv), logs, and profiling
        keep = {"venv", ".uv", "logs", "profiling"}
        if old_appenv.exists():
            for path in list(old_appenv.iterdir()):
                if path.name not in keep:
                    log.debug(f"Removing old .appenv entry: {path.name} ...")
                    if path.is_dir():
                        shutil.rmtree(path)
                    else:
                        path.unlink()

        return str(venv_real)

    def prepare(self, args=None, remaining=None):
        """Prepare venv with production dependencies only."""
        return self._prepare_venv()

    def develop(self, args=None, remaining=None):
        """Prepare the venv with dev dependencies."""
        return self._prepare_venv(dev_mode=True)

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

        self._init_project(
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
        if has_pyproject(target):
            existing_pyproject = pyproject_file.read_text()
            if self._has_project_section(existing_pyproject):
                print(f"pyproject.toml already has [project] section in {target}.")
                print("Nothing to do.")
                return
            print("Adding [project] section to existing pyproject.toml.\n")

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

        self._init_project(
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

    def _init_project(
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

        uv_argv = [uv_bin, *remaining]
        os.chdir(self.base)
        os.execv(uv_bin, uv_argv)

    def show_version(self, args=None, remaining=None):
        """Show appenv version."""
        print(f"appenv {__version__}")

    def settings(self, args=None, remaining=None):
        """Show environment variables and settings."""
        print("appenv environment:\n")

        env_vars = [
            ("APPENV_EXTRAS", "Extras to install (comma-separated)"),
            ("APPENV_VERBOSE", "Show verbose output"),
            ("APPENV_PROFILE", "Enable profiling"),
            ("APPENV_PROFILE_OUTPUT", "Profiling output file"),
            ("APPENV_BASEDIR", "Base directory of the project"),
            ("APPENV_BEST_PYTHON", "Selected Python interpreter"),
            ("UV_PROJECT_ENVIRONMENT", "uv venv location"),
            ("PYTHONPATH", "Python module search path"),
        ]

        for var, description in env_vars:
            value = os.environ.get(var, "(not set)")
            print(f"  {var}: {value}")
            print(f"    {description}\n")

        print(f"  Base directory: {self.base}")
        print(f"  Current working directory: {Path.cwd()}")

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

    def _find_profile(
        self, args_file: str | None, message_prefix: str = "Showing"
    ) -> Path:
        """Find profile file from args or latest.

        Returns Path to profile. Exits on error if not found.
        """
        profiling_dir = self.appenv_dir / "profiling"

        if args_file:
            profile_path = profiling_dir / args_file
            if not profile_path.exists():
                print(f"Profile not found: {args_file}")
                sys.exit(EXIT_CODE_NOINPUT)
            return profile_path

        # Find latest profile
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
        print(f"{message_prefix} latest profile: {profile_path.name}\n")
        return profile_path

    def profiling_show(self, args, remaining=None):
        """Show profile with pstats."""
        profile_path = self._find_profile(args.file, "Showing")

        import pstats

        stats = pstats.Stats(str(profile_path))
        stats.sort_stats("cumulative")
        stats.print_stats(20)

    def profiling_snakeviz(self, args, remaining=None):
        """Show profile with snakeviz (interactive web UI)."""
        profile_path = self._find_profile(args.file, "Opening")

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
                    log.debug(f"Removing {path} ...")
                    if path.is_dir():
                        shutil.rmtree(path)
                    else:
                        path.unlink()

    def _read_lockfile_lines(self, lock_file: Path) -> set[str]:
        """Read lockfile and return non-comment lines as a set."""
        if not lock_file.exists():
            return set()
        return {
            stripped
            for line in lock_file.read_text().splitlines()
            if (stripped := line.strip()) and not stripped.startswith("#")
        }

    def _run_uv_lock_diff(self, base: Path, verbose: bool) -> bool:
        """Run uv lock in temp directory and show diff.

        Returns True if changes found.
        """
        lock_file = base / UV_LOCK
        old_content = lock_file.read_text() if lock_file.exists() else ""

        print("Checking lockfile changes ...")
        if verbose:
            print("Running uv lock in temp directory (dry run)")

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_pyproject = Path(tmpdir) / PYPROJECT_TOML
            tmp_lock = Path(tmpdir) / UV_LOCK
            shutil.copy(base / PYPROJECT_TOML, tmp_pyproject)
            uv_cmd(["lock"], verbose=verbose, cwd=tmpdir)
            new_content = tmp_lock.read_text() if tmp_lock.exists() else ""

        has_changes = print_colored_diff(
            old_content, new_content, UV_LOCK, f"{UV_LOCK} (new)"
        )
        if not has_changes:
            print("No changes")
        return has_changes

    def _print_lockfile_summary(self, old_lines: set[str], new_lines: set[str]) -> None:
        """Print summary of lockfile changes."""
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

    def update_lockfile(self, args=None, remaining=None):
        verbose: bool = bool(args and getattr(args, "verbose", False))

        ensure_uv(self.base)
        os.chdir(self.base)

        if not has_pyproject(self.base):
            print(f"No {PYPROJECT_TOML} found.")
            sys.exit(EXIT_CODE_NOINPUT)

        source_file = self.base / PYPROJECT_TOML
        lock_file = self.base / UV_LOCK
        log.debug("update_lockfile")
        log.debug(f"Reading: {source_file}")
        log.debug(f"Lockfile: {lock_file}")

        # Read existing lockfile for comparison
        old_lines = self._read_lockfile_lines(lock_file)

        if args and args.diff:
            self._run_uv_lock_diff(self.base, verbose)
        else:
            # Run uv lock to update
            if verbose:
                print("Running: uv lock")
            uv_cmd(["lock"], verbose=verbose, base=self.base)

            # Read new content and show summary
            new_lines = self._read_lockfile_lines(lock_file)
            self._print_lockfile_summary(old_lines, new_lines)


def _detect_command_name() -> str:
    """Detect command name from sys.argv."""
    if len(sys.argv) > 1 and not sys.argv[1].startswith("-"):
        return sys.argv[1]
    return Path(sys.argv[0]).stem


def main():
    base = Path(__file__).parent
    original_cwd = Path.cwd()

    ensure_best_python(base)

    # Clear PYTHONPATH to ensure clean isolated environment.
    # Historical note: Some systems set PYTHONPATH globally which can interfere
    # with venv isolation. Clearing it ensures the venv's site-packages take precedence.
    os.environ.pop("PYTHONPATH", None)

    # Determine whether we're being called as appenv or as an application name
    application_name = Path(__file__).stem

    if application_name == "appenv":
        command_name = sys.argv[1] if len(sys.argv) > 1 else "help"
        remaining = sys.argv[1:] if len(sys.argv) > 1 else [command_name]
    else:
        command_name = "run"
        remaining = sys.argv[1:]

    appenv = AppEnv(base, original_cwd)
    if application_name == "appenv":
        appenv.meta(remaining, application_name)
    else:
        appenv.run(application_name, remaining)


def find_project_base(base: Path, original_cwd: Path) -> Path:
    """Find the project base directory by looking for pyproject.toml.

    Start from the directory where appenv.py is located and
    search upward in the filesystem tree for pyproject.toml.
    """
    # Check current directory
    if (base / PYPROJECT_TOML).exists():
        return base

    # Check parent directories
    for parent in base.parents:
        if (parent / PYPROJECT_TOML).exists():
            return parent

    # Fallback to appenv.py directory if no pyproject.toml found
    return base


if __name__ == "__main__":  # pragma: no cover
    main()
