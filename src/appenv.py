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
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import cached_property
from pathlib import Path
from typing import ClassVar, NamedTuple, TypeAlias, cast

# Global logger instance
log = logging.getLogger("appenv")

# Constants
PYPROJECT_TOML = "pyproject.toml"
REQUIREMENTS_TXT = "requirements.txt"
UV_LOCK = "uv.lock"
UV_MIN_VERSION = (0, 5, 0)

# Exit codes (BSD sysexits.h conventions)
EXIT_CODE_DATAERR = 65
EXIT_CODE_NOINPUT = 67
EXIT_CODE_UNAVAILABLE = 68


class GroupedHelpFormatter(argparse.HelpFormatter):
    """Group subcommands by category in help output."""

    GROUPS: ClassVar[list[tuple[str, list[str]]]] = [
        ("Project", ["init", "migrate", "update-lockfile"]),
        ("Venv", ["develop", "prepare", "reset"]),
        ("Tools", ["python", "run", "uv"]),
        ("Debug", ["version", "settings", "profiling"]),
    ]

    def _format_action(self, action):
        # Handle subparsers action with grouped display
        if isinstance(action, argparse._SubParsersAction):
            # Build command -> help mapping from _choices_actions
            cmd_help = {ca.metavar: ca.help or "" for ca in action._choices_actions}

            # Build grouped subcommand list
            lines = []
            for group_name, commands in self.GROUPS:
                lines.append(f"  {group_name}:")
                for cmd in commands:
                    if cmd in action.choices:
                        help_text = cmd_help.get(cmd, "")
                        # Truncate long help texts
                        if len(help_text) > 50:
                            help_text = help_text[:47] + "..."
                        lines.append(f"    {cmd:<16}  {help_text}")
                lines.append("")  # Empty line between groups

            # Remove trailing empty line and return
            return "\n".join(lines).rstrip() + "\n"

        return super()._format_action(action)


def cmd(c, merge_stderr=True, quiet=False, cwd=None):
    # SPEC: SRS-F001-cmd-wrapper - Enrich subprocess errors with command output context
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


def find_project_base(base, original_cwd):
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


def configure_logging(command_name, log_dir, verbose):
    """Setup command-specific logging to file and optional console."""
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

    if verbose:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.DEBUG)
        console_formatter = logging.Formatter("%(message)s")
        console_handler.setFormatter(console_formatter)
        log.addHandler(console_handler)


def cleanup_old_logs(log_dir, max_age_days=7):
    """Remove logs older than max_age_days."""
    cutoff = datetime.now() - timedelta(days=max_age_days)

    for log_file in log_dir.glob("*.log"):
        if datetime.fromtimestamp(log_file.stat().st_mtime) < cutoff:
            log_file.unlink()


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


class InvalidVersionError(ValueError):
    def __init__(self, version_str):
        self.version_str = version_str
        super().__init__(f"Invalid version string: {version_str}")

    def msg(self):
        pass


@dataclass(order=True, frozen=True)
class UvVersion:
    major: int
    minor: int
    patch: int

    def __str__(self):
        if self == (0, 0, 0):
            return "unknown"
        return f"{self.major}.{self.minor}.{self.patch}"

    @property
    def valid(self):
        return self >= UvVersion.minimum()

    @staticmethod
    def unknown():
        return UvVersion(0, 0, 0)

    @staticmethod
    def minimum():
        return UvVersion(*UV_MIN_VERSION)

    @staticmethod
    def from_string(version_str):
        parts = version_str.split(".")
        if len(parts) == 3:
            try:
                major, minor, patch = map(int, parts)
                return UvVersion(major, minor, patch)
            except ValueError:
                pass
        raise InvalidVersionError(version_str)


def get_uv_version(uv_bin):
    """Get uv version by calling uv --version.

    Returns UvVersion object on success, None on any error
    (subprocess failure, parse error, etc.).
    """
    try:
        result = subprocess.run(
            [uv_bin, "--version"],
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError:
        log.debug(
            "get_uv_version failed: %s",
        )
        return None

    version_cmd_output = result.stdout.strip()
    log.debug("uv --version: %s", version_cmd_output)

    try:
        uv_version_str = version_cmd_output.split()[1]
    except IndexError:
        return None

    log.debug("uv_version_str: %s", uv_version_str)

    try:
        return UvVersion.from_string(uv_version_str)
    except InvalidVersionError:
        return None


def ensure_uv(base=None):
    """Ensure uv is available and meets minimum version.

    Exits with error if uv is not available or too old.
    """
    uv_bin = get_uv_bin(base)
    log.debug(f"uv binary: {uv_bin}")

    uv_version = get_uv_version(uv_bin)
    log.debug(f"uv version: {uv_version}")

    if uv_version is None or not uv_version.valid:
        print(f"Error: cannot use uv binary: {uv_bin}. Version is: {uv_version}")
        print(f"Minimum required version: {UvVersion.minimum()}")
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
    log.debug(f"_uv_from_path: uv in PATH = {uv_in_path}")
    if uv_in_path:
        uv_bin = Path(uv_in_path)
        version = get_uv_version(uv_bin)
        log.debug(
            f"_try_uv_from_path: version at {uv_bin} valid = {version is not None}"
        )
        if version is not None and version.valid:
            _cleanup_appenv_uv(base)
            return uv_bin
    return None


def _try_uv_from_appenv_dir(base):
    """Try to find uv in .appenv/.uv from previous run."""
    if not base:
        log.debug("_try_uv_from_appenv_dir: no base provided")
        return None
    uv_local = base / ".appenv" / ".uv" / "bin" / "uv"
    version = get_uv_version(uv_local)
    log.debug(
        f"_try_uv_from_appenv_dir: {uv_local} "
        f"exists={uv_local.exists()}, version valid={version is not None}"
    )
    if uv_local.exists() and version is not None and version.valid:
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
        if version is not None and version.valid:
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
        version = get_uv_version(uv_local)
        if version is not None and version.valid:
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


def uv_cmd(uv_bin, args, verbose=False, **kwargs):
    cmd_args = [str(uv_bin)]
    if verbose:
        cmd_args.append("-v")
    cmd_args.extend(str(arg) for arg in args)

    log.debug("Running uv command: %s", " ".join(cmd_args))
    uv_output = cmd(cmd_args, **kwargs).decode("utf-8", "replace")
    log.debug("uv output: %s", uv_output)

    # Print output if APPENV_VERBOSE is set
    if os.environ.get("APPENV_VERBOSE"):
        print(uv_output)

    return uv_output


class RequirementsTxtInfo(NamedTuple):
    dependencies: list[str]
    editable_warnings: list[str]
    python_versions: list[str]


def _parse_requirements_file(requirements_path):
    """Parse requirements.txt content into dependencies and warnings.

    Editable installs (-e) are not supported and generate warnings.
    """
    content = requirements_path.read_text()
    all_deps = [
        line.strip()
        for line in content.splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]

    dependencies = [d for d in all_deps if not d.startswith("-e ")]
    editable_specs = [d for d in all_deps if d.startswith("-e ")]
    editable_warnings = [
        f"{spec} (editable installs not supported)" for spec in editable_specs
    ]

    python_versions = _parse_python_preference(content)
    return RequirementsTxtInfo(dependencies, editable_warnings, python_versions)


def _parse_python_preference(content):
    """Parse python preference from requirements.txt content."""
    for line in content.splitlines():
        if line.startswith("# appenv-python-preference: "):
            raw = line.split(":")[1]
            preferences = [x.strip() for x in raw.split(",") if x.strip()]
            if preferences:
                return preferences
    return ["3.10", "3.11", "3.12", "3.13", "3.14"]


def _print_migration_info(editable_warnings, dependencies, python_versions):
    """Print migration summary for editable installs and dependencies."""
    if editable_warnings:
        print(f"Warning: {len(editable_warnings)} editable install(s) skipped:")
        for warn in editable_warnings:
            print(f"  - {warn}")
        print("Add them manually to pyproject.toml if needed.\n")

    if python_versions and len(python_versions) > 1:
        print(f"Found python preference: {', '.join(python_versions)}")
        print(f"Using minimum version: {python_versions[0]}\n")

    print(f"Found {len(dependencies)} dependency(ies): {', '.join(dependencies)}")


def _read_lockfile_lines(lock_file):
    try:
        return {
            stripped
            for line in lock_file.read_text().splitlines()
            if (stripped := line.strip()) and not stripped.startswith("#")
        }
    except FileNotFoundError:
        return set()


def _run_uv_lock_diff(uv_bin, base, verbose):
    """Run uv lock in temp directory and show diff.

    Returns True if changes found.
    """
    log.debug("_ruf_uv_lock_diff")
    lock_file = base / UV_LOCK
    old_content = lock_file.read_text() if lock_file.exists() else ""

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_pyproject = Path(tmpdir) / PYPROJECT_TOML
        tmp_lock = Path(tmpdir) / UV_LOCK
        shutil.copy(base / PYPROJECT_TOML, tmp_pyproject)
        uv_cmd(uv_bin, ["lock"], verbose=verbose, cwd=tmpdir)
        new_content = tmp_lock.read_text() if tmp_lock.exists() else ""

    has_changes = print_colored_diff(
        old_content, new_content, UV_LOCK, f"{UV_LOCK} (new)"
    )
    if not has_changes:
        return "No changes"
    return has_changes


def _create_lockfile_summary(old_lines, new_lines):
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
        return "No changes"
    else:
        added_str = f"{green}+{n_added}{reset}"
        removed_str = f"{red}-{n_removed}{reset}"
        if is_new:
            return f"{check} Created ({added_str} lines)"
        else:
            return f"{check} Updated ({added_str} / {removed_str} lines)"


class Pyproject:
    def __init__(self, base):
        self.path = base / PYPROJECT_TOML
        self.requirements_txt = base / REQUIREMENTS_TXT

    @staticmethod
    def generate(
        project_name,
        description,
        dependencies,
        python_version,
        existing_pyproject=None,
    ):
        # SPEC: SRS-F003-project-generation - Generate pyproject.toml content
        # Action: Create new Pyproject instance with generated content
        existing_content = existing_pyproject.content if existing_pyproject else None
        content = _generate_pyproject_content(
            project_name=project_name,
            description=description,
            dependencies=dependencies,
            python_version=python_version,
            existing_content=existing_content,
        )
        pyproject = Pyproject(
            existing_pyproject.path.parent if existing_pyproject else Path.cwd()
        )
        pyproject.path.write_text(content)
        return pyproject

    def migrate_from_requirements_txt(self) -> "Pyproject":
        # Parse requirements.txt to get structured info
        req_info = _parse_requirements_file(self.requirements_txt)

        # Print migration summary
        _print_migration_info(
            req_info.editable_warnings,
            req_info.dependencies,
            req_info.python_versions,
        )

        # Use directory name as project name
        project_name = self.path.parent.name
        description = ""

        self.path.write_text(
            _generate_pyproject_content(
                project_name=project_name,
                description=description,
                dependencies=req_info.dependencies,
                python_version=req_info.python_versions[0],
                existing_content=self.content,
            )
        )
        return Pyproject(self.path.parent)

    @cached_property
    def content(self):
        if not self.exists:
            return ""
        return self.path.read_text()

    @cached_property
    def has_project_section(self):
        """Check if TOML content has a [project] section."""
        for line in self.content.splitlines():
            stripped = line.strip()
            if stripped == "[project]" or stripped.startswith("[project."):
                return True
        return False

    def can_be_created_from_requirements_txt(self):
        return not self.has_project_section and self.requirements_txt.exists()

    @property
    def exists(self):
        return self.path.exists()


def ensure_pyproject(base):
    pyproject = Pyproject(base)
    if pyproject.has_project_section:
        log.debug("pyproject %s has [project] section", pyproject.path)
        return pyproject

    if pyproject.exists:
        log.debug("pyproject found at %s", pyproject.path)

    if pyproject.exists:
        print(f"Error: {pyproject.path} has no [project] section.")
    else:
        print(f"Error: No pyproject config file at {pyproject.path} found.")

    if pyproject.can_be_created_from_requirements_txt:
        print("Legacy requirements.txt found.")
        print("Run: ./appenv migrate")
        sys.exit(EXIT_CODE_DATAERR)
    else:
        print("Run ./appenv init")
        sys.exit(EXIT_CODE_NOINPUT)


def ensure_lock_file(base):
    lock_file = base / UV_LOCK
    if not lock_file.exists():
        print(f"No {UV_LOCK} found. Run: ./appenv update-lockfile")
        sys.exit(EXIT_CODE_NOINPUT)

    log.debug(f"uv.lock: {lock_file}")
    return lock_file


def _generate_pyproject_content(
    project_name,
    description,
    dependencies,
    python_version,
    existing_content=None,
):
    """Generate pyproject.toml content string.

    Args:
        existing_content: If provided, merge [project] section into existing
    """
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

    # Merge with existing content or create new
    if existing_content:
        pyproject_content = existing_content.rstrip() + "\n\n" + project_section
    else:
        pyproject_content = project_section

    return pyproject_content


def _cleanup_old_appenv_entries(appenv_dir, verbose=False):
    """Remove old hash-based venvs and files from .appenv directory."""
    keep = {"venv", ".uv", "logs", "profiling", "current"}
    if appenv_dir.exists():
        for path in list(appenv_dir.iterdir()):
            if path.name not in keep:
                log.debug(f"Removing old .appenv entry: {path.name} ...")
                if verbose:
                    print(f"Removing old .appenv entry: {path.name}")
                if path.is_dir():
                    shutil.rmtree(path)
                else:
                    path.unlink()


def _setup_command_symlink(target, command_name, appenv_script, project_name):
    """Setup command symlink to appenv.

    Args:
        target: Project directory
        command_name: Explicit name, or None to detect existing symlinks
        appenv_script: Path to appenv script
        project_name: Fallback name for new symlink

    Returns:
        The command name (either provided or detected/created)
    """
    if command_name:
        # Fresh project: create new symlink
        command_link = target / command_name
        if command_link.is_symlink() or command_link.exists():
            command_link.unlink(missing_ok=True)
        command_link.symlink_to("appenv")
        print(f"Created {command_name} symlink")
        return command_name
    else:
        # Migration: find existing symlinks
        existing_symlinks = [
            path.name
            for path in target.iterdir()
            if path.is_symlink() and path.resolve() == appenv_script.resolve()
        ]
        if existing_symlinks:
            print(f"Found existing symlink(s): {', '.join(existing_symlinks)}")
            return existing_symlinks[0]
        else:
            command_link = target / project_name
            command_link.symlink_to("appenv")
            print(f"Created {project_name} symlink")
            return project_name


@dataclass(frozen=True)
class AppEnvSettings:
    verbose: bool
    extras: str | None
    profile: bool
    profile_output: str | None
    basedir: Path | None

    @staticmethod
    def from_env() -> "AppEnvSettings":
        # Read settings from environment variables
        verbose = os.environ.get("APPENV_VERBOSE") is not None
        extras = os.environ.get("APPENV_EXTRAS")
        profile = os.environ.get("APPENV_PROFILE") is not None
        profile_output = os.environ.get("APPENV_PROFILE_OUTPUT")
        basedir_str = os.environ.get("APPENV_BASEDIR")
        basedir = Path(basedir_str) if basedir_str else None

        return AppEnvSettings(
            verbose=verbose,
            extras=extras,
            profile=profile,
            profile_output=profile_output,
            basedir=basedir,
        )


class AppEnv:
    def __init__(self, base, original_cwd, settings):
        self.base = base.resolve()
        self.original_cwd = original_cwd
        self.settings = settings

        self.appenv_dir = self.base / ".appenv"
        self.appenv_script = base / "appenv"
        self.log_dir = self.appenv_dir / "logs"

    def setup_logdir(self):
        self.log_dir.mkdir(parents=True, exist_ok=True)
        cleanup_old_logs(self.log_dir)
        return self.log_dir

    def meta(self, remaining_args=None, prog="appenv"):
        log_dir = self.setup_logdir()
        configure_logging(prog, log_dir, self.settings.verbose)

        # Parse the appenv arguments
        parser = argparse.ArgumentParser(
            prog=prog,
            usage="%(prog)s <COMMAND>",
            formatter_class=GroupedHelpFormatter,
        )
        subparsers = parser.add_subparsers(title="Commands")
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
        p.set_defaults(func=self.show_settings)

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
            parser.print_help()
            sys.exit(0)

        args, remaining = parser.parse_known_args(remaining_args)

        if not hasattr(args, "func"):
            parser.print_help()
            sys.exit(0)
        else:
            args.func(args, remaining)

    def run(self, command, argv):
        log_dir = self.setup_logdir()
        configure_logging(command, log_dir, self.settings.verbose)

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

        venv_real = self.appenv_dir / "venv"
        venv_link = self.base / ".venv"

        ensure_pyproject(self.base)
        ensure_lock_file(self.base)
        uv_bin = ensure_uv(self.base)
        os.chdir(self.base)

        # Tell uv where to put/find venv
        os.environ["UV_PROJECT_ENVIRONMENT"] = str(venv_real)

        log.debug(f"Project base: {self.base}")
        log.debug(f"venv: {venv_real}")
        log.debug(f"Python: {Path(sys.executable).resolve()}")
        log.debug(f"Dev mode: {dev_mode}")

        # Ensure .appenv directory exists and cleanup old entries
        if not self.appenv_dir.exists():
            self.appenv_dir.mkdir()
        else:
            _cleanup_old_appenv_entries(self.appenv_dir, verbose=self.settings.verbose)

        # Print verbose project information if requested
        if self.settings.verbose:
            print(f"Project base: {self.base}")
            pyproject_path = self.base / PYPROJECT_TOML
            lock_path = self.base / UV_LOCK
            print(f"{PYPROJECT_TOML}: {pyproject_path}")
            print(f"{UV_LOCK}: {lock_path}")
            print(f"venv: {venv_real}")
            print(f"uv binary: {uv_bin}")
            try:
                uv_version = get_uv_version(uv_bin)
                print(f"uv version: {uv_version if uv_version else 'unknown'}")
            except (FileNotFoundError, subprocess.CalledProcessError):
                print("uv version: unknown")
            print(f"Python: {Path(sys.executable).resolve()}")
            print(f"Dev mode: {dev_mode}")

        # Create venv if needed or check integrity
        if not venv_real.exists() or not (venv_real / "bin" / "python").exists():
            if venv_real.exists():
                log.debug("Corrupted venv detected, removing ...")
                shutil.rmtree(venv_real)
            log.debug("Creating venv with uv ...")
            # Use current Python (already selected by ensure_best_python)
            # Explicit path avoids uv downloading its own (breaks on NixOS, for example)
            if self.settings.verbose:
                print("Creating venv with uv ...")
            uv_cmd(uv_bin, ["venv", "--python", sys.executable, str(venv_real)])

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
        if self.settings.verbose:
            print(f"prepare_venv activated extras/optional deps: {extras}")
            print(f"prepare_venv uv args: {sync_args}")
        uv_cmd(uv_bin, sync_args, cwd=self.base)

        # Show venv python info AFTER sync (version may have changed)
        venv_python = venv_real / "bin" / "python"
        if venv_python.exists():
            log.debug(f"Venv Python: {venv_python}")
            log.debug(f"Venv Python (realpath): {venv_python.resolve()}")
            if self.settings.verbose:
                print(f"Venv Python: {venv_python}")
                print(f"Venv Python (realpath): {venv_python.resolve()}")
            result = cmd([str(venv_python), "--version"], quiet=True)
            log.debug(f"Venv Python version: {result.decode().strip()}")
            if self.settings.verbose:
                print(f"Venv Python version: {result.decode().strip()}")

        # Create symlink for tool compatibility
        # (e.g., IDEs, formatters, linters that expect .venv)
        # Always update symlink unless .venv is a real directory
        # Use relative symlink for portability
        if venv_link.is_symlink():
            venv_link.unlink()
        if not venv_link.exists():
            venv_link.symlink_to(
                os.path.relpath(venv_real, self.base), target_is_directory=True
            )

        current_link = self.appenv_dir / "current"
        if current_link.is_symlink():
            current_link.unlink()
        if not current_link.exists():
            current_link.symlink_to(venv_real, target_is_directory=True)

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
        pyproject = Pyproject(target)
        if pyproject.exists:
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
            pyproject=pyproject,
            target=target,
            project_name=project_name,
            description=description,
            dependencies=dependencies,
            python_version=python_version,
            command_name=command_name,
        )

    def migrate(self, args=None, remaining=None):
        """Migrate from requirements.txt to pyproject.toml."""
        target = self.original_cwd.resolve()

        pyproject = Pyproject(target)
        if pyproject.has_project_section:
            print(f"pyproject.toml already has [project] section in {target}.")
            print("Nothing to do.")
            sys.exit(0)

        if pyproject.exists:
            print("Adding [project] section to existing pyproject.toml.\n")
        elif pyproject.can_be_created_from_requirements_txt:
            print("Migrating from requirements.txt to pyproject.toml...\n")
        else:
            print(f"No requirements.txt found in {target}.")
            print("Use 'init' to create a new project.")
            sys.exit(2)

        pyproject = pyproject.migrate_from_requirements_txt()

        self._init_project(
            pyproject=pyproject,
            target=target,
            project_name=target.name,  # Use directory name as fallback
            command_name=None,  # Find existing symlinks
        )

        # Cleanup old .appenv hash-based venvs
        _cleanup_old_appenv_entries(self.appenv_dir)

        print(
            "\nrequirements.txt kept as legacy. Delete it when migration is complete."
        )

    def _init_project(
        self,
        pyproject,
        target,
        project_name=None,
        description="",
        dependencies=None,
        python_version=None,
        command_name=None,
    ):
        """Create pyproject.toml, appenv bootstrap, symlink, and lockfile."""
        if pyproject.exists and pyproject.has_project_section:
            # Already have pyproject (e.g., from migration), skip generation
            print(f"\nUsing existing {pyproject.path}")
        else:
            if pyproject.exists:
                print(f"\nUpdating {pyproject.path}")
            else:
                print(f"\nCreating {pyproject.path}")

            pyproject = pyproject.generate(
                project_name=project_name or target.name,
                description=description,
                dependencies=dependencies or [],
                python_version=python_version or "3.10",
                existing_pyproject=pyproject if pyproject.exists else None,
            )

        # Create appenv bootstrap if needed
        if not self.appenv_script.exists():
            bootstrap_data = Path(__file__).read_bytes()
            self.appenv_script.write_bytes(bootstrap_data)
            self.appenv_script.chmod(0o755)
            print("Created appenv script")

        # Handle symlink
        command_name = _setup_command_symlink(
            target=target,
            command_name=command_name,
            appenv_script=self.appenv_script,
            project_name=project_name,
        )

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
        uv_bin = ensure_uv(self.base)

        # Tell uv where the venv lives (in .appenv/venv, not .venv)
        venv_real = self.appenv_dir / "venv"
        os.environ["UV_PROJECT_ENVIRONMENT"] = str(venv_real)

        uv_argv = [uv_bin, *remaining]
        os.chdir(self.base)
        os.execv(uv_bin, uv_argv)

    def show_version(self, args=None, remaining=None):
        """Show appenv version."""
        print(f"appenv {__version__}")

    def show_settings(self, args=None, remaining=None):
        """Show environment variables and settings."""
        print("appenv settings:\n")

        # show self.settings properly here

        # extra env vars which don't belong to appenv settings
        extra_env_vars = [
            ("APPENV_BEST_PYTHON", "Selected Python interpreter"),
            ("UV_PROJECT_ENVIRONMENT", "uv venv location"),
            ("PYTHONPATH", "Python module search path"),
        ]

        for var, description in extra_env_vars:
            value = os.environ.get(var, "(not set)")
            print(f"  {var}: {value}")
            print(f"    {description}\n")

        print(f"  Base directory: {self.base}")
        print(f"  Current working directory: {self.original_cwd}")
        print(f"  Log directory: {self.log_dir}")

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
                    print(f"Removing {path} ...")
                    if path.is_dir():
                        shutil.rmtree(path)
                    else:
                        path.unlink()

    def update_lockfile(self, args=None, remaining=None):
        verbose = bool(args and getattr(args, "verbose", False))
        pyproject = ensure_pyproject(self.base)
        lock_file = self.base / UV_LOCK
        uv_bin = ensure_uv(self.base)
        os.chdir(self.base)

        log.debug("update_lockfile: %s -> %s", pyproject.path, lock_file)

        if args and args.diff:
            print("Diff mode: only check lockfile changes ...")
            update_info = _run_uv_lock_diff(uv_bin, self.base, verbose)
        else:
            old_lines = _read_lockfile_lines(lock_file)
            print("Updating lock file ...")
            uv_cmd(uv_bin, ["lock"], verbose=verbose, cwd=self.base)

            new_lines = _read_lockfile_lines(lock_file)
            update_info = _create_lockfile_summary(old_lines, new_lines)

        print(update_info)


def _detect_command_name():
    """Detect command name from sys.argv."""
    # XXX: use this in main?
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

    settings = AppEnvSettings.from_env()
    appenv = AppEnv(base, original_cwd, settings)

    # Determine whether we're being called as appenv or as an application name
    application_name = Path(__file__).stem
    if application_name == "appenv":
        command_name = sys.argv[1] if len(sys.argv) > 1 else "help"
        remaining = sys.argv[1:] if len(sys.argv) > 1 else [command_name]
        appenv.meta(remaining)
    else:
        remaining = sys.argv[1:]
        appenv.run(application_name, remaining)


if __name__ == "__main__":
    main()
