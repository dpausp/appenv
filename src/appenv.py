#!/usr/bin/env python3
"""
appenv - a single-file tool that pins Python packages to exact versions and
         exposes their binaries via symlinks. Drop into a repository, commit,
         and every checkout gets the same tools at the same versions.

Assumptions:

  - the appenv file is placed in a repo with the name of the application
  - the name of the application/file becomes the CLI entrypoint via symlink
  - Python 3.10+
  - system has usable uv (see UV_MIN_VERSION) or has Nix to install uv on-demand
  - pyproject.toml next to the appenv file
"""

from __future__ import annotations

__version__ = "2026.5.13a1"

import argparse
import difflib
import io
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
from argparse import Namespace
from dataclasses import dataclass
from functools import cached_property
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import Any, NamedTuple, cast

# Global logger instance
log = logging.getLogger("appenv")

# Exit codes (BSD sysexits.h conventions)
EXIT_CODE_DATAERR = 65
EXIT_CODE_NOINPUT = 67
EXIT_CODE_UNAVAILABLE = 68
EXIT_CODE_USAGE = 64

# Format constants
MAX_HELP_TEXT_LENGTH = 50
VERSION_PARTS_COUNT = 3


class GroupedHelpFormatter(argparse.HelpFormatter):
    """Group subcommands by category in help output."""

    def _format_action(self, action: argparse.Action) -> str:
        groups = (
            ("Project", ["init", "migrate", "self-update", "update-lockfile"]),
            ("Venv", ["prepare", "reset"]),
            ("Tools", ["python", "uv"]),
            ("Debug", ["version"]),
        )

        if isinstance(action, argparse._SubParsersAction):  # noqa: SLF001
            # Build command -> help mapping from _choices_actions
            cmd_help = {ca.metavar: ca.help or "" for ca in action._choices_actions}  # noqa: SLF001

            # Build grouped subcommand list
            lines = []
            for group_name, commands in groups:
                lines.append(f"  {group_name}:")
                for cmd in commands:
                    if cmd in action.choices:
                        help_text = cmd_help.get(cmd, "")
                        # Truncate long help texts
                        if len(help_text) > MAX_HELP_TEXT_LENGTH:
                            help_text = help_text[:47] + "..."
                        lines.append(f"    {cmd:<16}  {help_text}")
                lines.append("")  # Empty line between groups

            # Remove trailing empty line and return
            return "\n".join(lines).rstrip() + "\n"

        return super()._format_action(action)


class RequirementsTxtInfo(NamedTuple):
    dependencies: list[str]
    editable_dependencies: list[str]
    python_versions: list[str]


def convert_version_preference(versions: list[str]) -> tuple[str, list[str]]:
    """Convert version list to requires-python specifier.

    Returns (specifier, missing_versions) where missing_versions
    are versions in the range that weren't explicitly listed.

    Example: ["3.11", "3.13", "3.10"] -> (">=3.10,<3.14", ["3.12"])
    """
    if not versions:
        return ">=3.10", []

    sorted_v = sorted(versions, key=lambda v: tuple(map(int, v.split("."))))
    min_v = sorted_v[0]
    max_v = sorted_v[-1]

    # Increment minor for exclusive upper bound
    parts = max_v.split(".")
    next_minor = f"{parts[0]}.{int(parts[1]) + 1}"

    # Find gaps in range
    min_parts = tuple(map(int, min_v.split(".")))
    max_parts = tuple(map(int, max_v.split(".")))
    all_in_range = [
        f"{min_parts[0]}.{i}" for i in range(min_parts[1], max_parts[1] + 1)
    ]
    missing = [v for v in all_in_range if v not in versions]

    return f">={min_v},<{next_minor}", missing


def version_satisfies_constraints(
    version: str, min_version: str, max_version: str | None = None
) -> bool:
    ver_parts = [int(p) for p in version.split(".")]
    min_parts = [int(p) for p in min_version.split(".")]

    if ver_parts < min_parts:
        return False

    if max_version is not None:
        max_parts = [int(p) for p in max_version.split(".")]
        if ver_parts >= max_parts:
            return False

    return True


def remove_path(path: Path) -> None:
    """Remove a path regardless of type (symlink, file, or directory).

    Logs the type before removal for debugging purposes.
    """
    if path.is_symlink():
        log.debug("Removing symlink: %s", path)
        path.unlink()
    elif path.is_file():
        log.debug("Removing file: %s", path)
        path.unlink()
    elif path.is_dir():
        log.debug("Removing directory: %s", path)
        shutil.rmtree(path)


class Pyproject:
    """Encapsulates pyproject.toml parsing, migration, and generation."""

    def __init__(self, base: Path) -> None:
        self.path = base / "pyproject.toml"
        self.requirements_path = base / "requirements.txt"

    @cached_property
    def content(self) -> str:
        if not self.exists:
            return ""
        return self.path.read_text()

    def migrate_from_requirements_txt(self) -> Pyproject:
        req_info = self.requirements_txt_info

        requires_python, missing = convert_version_preference(req_info.python_versions)
        content = self._generate_content_with_project(
            project_name=self.path.parent.name,
            description="Migrated Appenv project",
            dependencies=req_info.dependencies,
            requires_python=requires_python,
        )
        self.path.write_text(content)

        # Print info about missing versions
        if missing:
            print(f"Note: Versions {', '.join(missing)} were not in preference list")

        return Pyproject(self.path.parent)

    @property
    def requires_python(self) -> tuple[str | None, str | None]:
        """Parse requires-python from pyproject.toml.

        Returns tuple of (min_version, max_version) where max may be None.
        """
        if not self.exists:
            return (None, None)

        # Extract the requires-python value
        value_match = re.search(
            r'requires-python\s*=\s*["\']([^"\']+)["\']', self.content
        )
        if not value_match:
            return (None, None)

        spec = value_match.group(1)

        # Parse minimum version (>=X.Y or >X.Y)
        min_match = re.search(r">=?\s*(\d+\.\d+)", spec)
        min_version = min_match.group(1) if min_match else None

        # Parse maximum version (<X.Y or <=X.Y)
        max_match = re.search(r"<=?\s*(\d+\.\d+)", spec)
        max_version = max_match.group(1) if max_match else None

        return (min_version, max_version)

    @property
    def exists(self) -> bool:
        return self.path.exists()

    @cached_property
    def has_project_section(self) -> bool:
        """Check if TOML content has a [project] section."""
        for line in self.content.splitlines():
            stripped = line.strip()
            if stripped == "[project]" or stripped.startswith("[project."):
                return True
        return False

    @property
    def can_be_created_from_requirements_txt(self) -> bool:
        return not self.has_project_section and self.requirements_path.exists()

    @cached_property
    def requirements_txt_info(self) -> RequirementsTxtInfo:
        return self._parse_requirements_file()

    def print_migration_info(self) -> None:
        req_info = self.requirements_txt_info

        if req_info.editable_dependencies:
            print(
                f"Warning: {len(req_info.editable_dependencies)} "
                f"editable install(s) skipped:"
            )
            for spec in req_info.editable_dependencies:
                print(f"  - {spec}")
            print("Add them manually to pyproject.toml if needed.\n")

        if req_info.python_versions and len(req_info.python_versions) > 1:
            print(f"Found python preference: {', '.join(req_info.python_versions)}")
            print(f"Using minimum version: {req_info.python_versions[0]}\n")

        print(
            f"Found {len(req_info.dependencies)} dependency(ies): "
            f"{', '.join(req_info.dependencies)}"
        )

    def _parse_requirements_file(self) -> RequirementsTxtInfo:
        """Parse requirements.txt content into dependencies and info."""
        content = self.requirements_path.read_text()
        all_deps = [
            line.strip()
            for line in content.splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]

        dependencies = [d for d in all_deps if not d.startswith("-e ")]
        editable_specs = [d for d in all_deps if d.startswith("-e ")]

        python_versions = self._parse_python_preference()
        return RequirementsTxtInfo(dependencies, editable_specs, python_versions)

    def _parse_python_preference(self) -> list[str]:
        """Parse python preference from requirements.txt content."""
        content = self.requirements_path.read_text()
        for line in content.splitlines():
            if line.startswith("# appenv-python-preference: "):
                raw = line.split(":")[1]
                preferences = [x.strip() for x in raw.split(",") if x.strip()]
                if preferences:
                    return preferences
        return ["3.10", "3.11", "3.12", "3.13", "3.14"]

    def _generate_content_with_project(
        self,
        project_name: str,
        description: str,
        dependencies: list[str],
        requires_python: str,
    ) -> str:
        """Generate pyproject.toml content string with [project] section."""
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
requires-python = "{requires_python}"
"""

        # Merge with existing content or create new
        if self.content:
            pyproject_content = self.content.rstrip() + "\n\n" + project_section
        else:
            pyproject_content = project_section

        return pyproject_content

    def with_project_section(
        self,
        project_name: str,
        description: str,
        dependencies: list[str],
        requires_python: str = ">=3.10",
    ) -> Pyproject:
        """Add [project] section, write file, return fresh instance.

        This method writes the updated content to disk and returns a new
        Pyproject instance (immutable pattern - cached content stays valid).
        """
        content = self._generate_content_with_project(
            project_name=project_name,
            description=description,
            dependencies=dependencies,
            requires_python=requires_python,
        )
        self.path.write_text(content)
        return Pyproject(self.path.parent)


def create_pyproject(
    target: Path,
    project_name: str,
    description: str,
    dependencies: list[str],
    python_version: str,
) -> Pyproject:
    """Factory function to create a new pyproject.toml file."""
    pyproject = Pyproject(target)
    return pyproject.with_project_section(
        project_name=project_name,
        description=description,
        dependencies=dependencies,
        requires_python=f">={python_version}",
    )


class LockFile:
    """Encapsulates lockfile operations and diff logic."""

    def __init__(self, base: Path) -> None:
        self.path = base / "uv.lock"

    @property
    def exists(self) -> bool:
        return self.path.exists()

    @cached_property
    def content(self) -> str:
        return self.path.read_text() if self.path.exists() else ""

    def diff(self, uv_bin: UvBin, base: Path, verbose: bool) -> str:
        """Run uv lock in temp dir, return diff string."""
        log.debug("starting")
        old_content = self.content

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_pyproject = Path(tmpdir) / "pyproject.toml"
            tmp_lock = Path(tmpdir) / "uv.lock"
            shutil.copy(base / "pyproject.toml", tmp_pyproject)
            uv_bin.cmd(["lock"], verbose=verbose, cwd=tmpdir)
            new_content = tmp_lock.read_text() if tmp_lock.exists() else ""

        has_changes = print_colored_diff(
            old_content, new_content, "uv.lock", "uv.lock (new)"
        )
        if not has_changes:
            return "No changes"
        return "Changed"

    def diff_summary(self, old_lines: set[str]) -> str:
        """Create summary like '✓ Created (+42 lines)'."""
        new_lines = self.read_lockfile_lines()
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
        added_str = f"{green}+{n_added}{reset}"
        removed_str = f"{red}-{n_removed}{reset}"
        if is_new:
            return f"{check} Created ({added_str} lines)"
        return f"{check} Updated ({added_str} / {removed_str} lines)"

    def read_lockfile_lines(self) -> set[str]:
        """Read lockfile lines as a set of non-comment lines."""
        try:
            return {
                stripped
                for line in self.path.read_text().splitlines()
                if (stripped := line.strip()) and not stripped.startswith("#")
            }
        except FileNotFoundError:
            return set()


@dataclass(order=True, frozen=True)
class UvVersion:
    major: int
    minor: int
    patch: int

    def __str__(self) -> str:
        if self.major == 0 and self.minor == 0 and self.patch == 0:
            return "unknown"
        return f"{self.major}.{self.minor}.{self.patch}"

    @property
    def valid(self) -> bool:
        return self >= UvVersion.minimum()

    @staticmethod
    def unknown() -> UvVersion:
        return UvVersion(0, 0, 0)

    @staticmethod
    def minimum() -> UvVersion:
        return UvVersion(0, 5, 0)

    @staticmethod
    def from_string(version_str: str) -> UvVersion:
        parts = version_str.split(".")
        if len(parts) == VERSION_PARTS_COUNT:
            try:
                major, minor, patch = map(int, parts)
                return UvVersion(major, minor, patch)
            except ValueError:
                pass

        msg = f"Invalid version string: {version_str}"
        raise NoValidUvError(msg)


class UvBin:
    """Encapsulates UV binary discovery, version check, and command execution."""

    def __init__(self, appenv_dir: Path) -> None:
        self.appenv_dir = appenv_dir
        self.uv_dir = appenv_dir / ".uv"
        self.managed_uv = self.uv_dir / "bin/uv"
        self.bin = self._get_uv_bin()

    def cmd(self, args: list[str], *, verbose: bool = False, **kwargs: Any) -> str:
        """Execute uv command and return stdout."""
        cmd_args = [str(self.bin)]
        if verbose:
            cmd_args.append("-v")
        cmd_args.extend(str(arg) for arg in args)

        log.debug("running %s", " ".join(cmd_args))
        uv_output = cmd(cmd_args, **kwargs).decode("utf-8", "replace")
        log.debug("uv output: %s", uv_output)

        return uv_output

    @cached_property
    def version(self) -> UvVersion:
        return UvBin.get_uv_version(self.bin)

    @staticmethod
    def get_uv_version(uv_path: Path) -> UvVersion:
        """Get uv version by calling uv --version."""
        try:
            result = subprocess.run(
                [uv_path, "--version"],
                capture_output=True,
                text=True,
                check=True,
            )
        except subprocess.CalledProcessError as e:
            log.debug("uv --version failed with error: %s", e.stderr)
            return UvVersion.unknown()

        version_cmd_output = result.stdout.strip()
        log.debug("uv --version: %s", version_cmd_output)

        try:
            uv_version_str = version_cmd_output.split()[1]
        except IndexError:
            log.exception("Cannot parse uv --version output, version unknown")
            return UvVersion.unknown()

        try:
            return UvVersion.from_string(uv_version_str)
        except NoValidUvError:
            log.exception("Cannot parse version string, version unknown")
            return UvVersion.unknown()

    def _get_uv_bin(self) -> Path:
        """Get path to valid uv binary via discovery chain:
        1. uv from PATH
        2. Check .appenv/.uv from previous run
        3. Build with nix-build from nixpkgs channel
        4. Build with nix build from nixpkgs flake
        5. pip install
        6. astral.sh installer (curl)
        """
        log.debug("searching for uv, appenv_dir=%s", self.appenv_dir)

        uv_bin = (
            self._try_uv_from_path()
            or self._try_uv_from_appenv_dir()
            or self._try_uv_from_nix_channel()
            or self._try_uv_from_nix_flake()
            or self._try_uv_from_pip()
            or self._try_uv_from_installer()
        )
        if not uv_bin:
            msg = "uv not found and could not be installed"
            raise NoValidUvError(msg)

        return uv_bin

    def _try_uv_from_path(self) -> Path | None:
        """Try to find uv in PATH."""
        uv_in_path = shutil.which("uv")
        log.debug("uv in PATH = %s", uv_in_path)
        if uv_in_path:
            uv_bin = Path(uv_in_path)
            version = UvBin.get_uv_version(uv_bin)
            log.debug("uv version is %s, valid: %s", version, version.valid)

            if version.valid:
                self._cleanup_appenv_uv()
                return uv_bin

        return None

    def _try_uv_from_appenv_dir(self) -> Path | None:
        log.debug("Trying appenv-managed uv at %s", self.managed_uv)
        if not self.managed_uv.exists():
            log.debug("no appenv-managed uv found at %s", self.managed_uv)
            return None

        version = UvBin.get_uv_version(self.managed_uv)
        log.debug("uv version is %s, valid: %s", version, version.valid)

        return self.managed_uv if version.valid else None

    def _try_uv_from_nix_channel(self) -> Path | None:
        """Try nix-build with nixpkgs channel"""
        nix_bin = shutil.which("nix")
        log.debug("appenv_dir=%s, nix_bin=%s", self.appenv_dir, nix_bin)

        if nix_bin is None:
            log.debug(
                "skipping (appenv_dir=%s, nix in PATH=%s)",
                self.appenv_dir,
                nix_bin is not None,
            )
            return None

        action = "Updating" if self.managed_uv.exists() else "Creating"
        log.debug("%s .appenv/.uv with Nix at %s ...", action, nix_bin)

        try:
            result = subprocess.run(
                ["nix-build", "<nixpkgs>", "-A", "uv", "-o", str(self.uv_dir)],
                capture_output=True,
                text=True,
                check=True,
            )
        except subprocess.CalledProcessError as e:
            log.debug("nix-build failed: %s", e.stderr)
            return None

        log.debug("nix-build succeeded: %s", result.stdout)

        version = UvBin.get_uv_version(self.managed_uv)
        log.debug("uv version is %s, valid: %s", version, version.valid)

        return self.managed_uv if version.valid else None

    def _try_uv_from_nix_flake(self) -> Path | None:
        """Tries more expensive but fresh nix build from nixpkgs flake"""

        if shutil.which("nix") is None:
            log.debug("skipping (nix not in PATH)")
            return None

        try:
            result = subprocess.run(
                ["nix", "build", "nixpkgs#uv", "--out-link", str(self.uv_dir)],
                capture_output=True,
                check=True,
                text=True,
            )
        except subprocess.CalledProcessError as e:
            log.debug("nix-build failed: %s", e.stderr)
            return None

        log.debug("nix build nixpkgs#uv: %s", result.stdout)

        version = UvBin.get_uv_version(self.managed_uv)
        log.debug("uv version is %s, valid: %s", version, version.valid)

        return self.managed_uv if version.valid else None

    def _try_uv_from_pip(self) -> Path | None:
        """Try to install uv via pip."""
        log.debug("attempting to install uv via pip ...")

        pip_cmd = self._resolve_pip_command()
        if not pip_cmd:
            log.debug("no pip found, skipping pip install")
            return None

        try:
            result = subprocess.run(
                [*pip_cmd, "install", "uv", "--upgrade", "-t", self.uv_dir],
                capture_output=True,
                text=True,
                check=True,
            )
        except subprocess.CalledProcessError as e:
            log.debug("pip install failed, skipping pip install: %s", e.stderr)
            return None

        log.debug("pip install uv: %s", result.stdout)

        version = UvBin.get_uv_version(self.managed_uv)
        log.debug("uv version is %s, valid: %s", version, version.valid)

        return self.managed_uv if version.valid else None

    def _try_uv_from_installer(self) -> Path | None:
        """Download uv binary directly from GitHub releases.

        Detects platform, downloads the appropriate tarball via urllib
        (stdlib), extracts and places the binary in .appenv/.uv/bin/uv.
        No curl, no wget, no shell script needed.
        """
        log.debug("attempting to download uv binary from GitHub releases ...")

        triple = self._uv_platform_triple()
        if not triple:
            log.debug("unsupported platform, skipping direct download")
            return None

        url = f"https://github.com/astral-sh/uv/releases/latest/download/uv-{triple}.tar.gz"

        try:
            import tarfile
            import urllib.error
            import urllib.request

            log.debug("downloading %s", url)
            resp = urllib.request.urlopen(url, timeout=60)
            data = resp.read()

            with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
                # tar contains uv-<triple>/uv — extract the binary
                for member in tar:
                    if member.name.endswith("/uv") and not member.isdir():
                        member.name = "bin/uv"
                        self.uv_dir.mkdir(parents=True, exist_ok=True)
                        tar.extract(member, self.uv_dir, filter="data")
                        break
        except (urllib.error.URLError, OSError, tarfile.TarError) as e:
            log.debug("failed to download/extract uv: %s", e)
            return None

        if not self.managed_uv.exists():
            log.debug("uv binary not found after extraction")
            return None

        version = UvBin.get_uv_version(self.managed_uv)
        log.debug("uv version is %s, valid: %s", version, version.valid)

        return self.managed_uv if version.valid else None

    @staticmethod
    def _uv_platform_triple() -> str | None:
        """Return the UV release triple for the current platform.

        Maps Python's platform.machine() and sys.platform to the
        archive naming used by astral-sh/uv GitHub releases.
        Returns None for unsupported platforms.
        """
        import platform

        machine = platform.machine().lower()
        system = sys.platform

        # Map architecture names to UV triples
        if machine in ("x86_64", "amd64"):
            arch = "x86_64"
        elif machine in ("aarch64", "arm64"):
            arch = "aarch64"
        elif machine == "armv7l":
            arch = "armv7"
        else:
            return None

        if system == "linux":
            libc = "musl" if Path("/etc/alpine-release").exists() else "gnu"
            return f"{arch}-unknown-linux-{libc}"
        if system == "darwin":
            return f"{arch}-apple-darwin"
        return None

    def _resolve_pip_command(self) -> list[str] | None:
        """Find a working pip command.

        Tries ensurepip first (blessed way), then falls back to
        shutil.which("pip"/"pip3") for systems where ensurepip is
        disabled (e.g. Debian Bookworm).
        """
        try:
            subprocess.run(
                [sys.executable, "-m", "ensurepip"],
                check=True,
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError as e:
            log.debug("ensurepip failed: %s", e.stderr)
        else:
            log.debug("ensurepip succeeded, using python -m pip")
            return [sys.executable, "-m", "pip"]

        # ensurepip failed — try finding pip in PATH
        for candidate in ("pip", "pip3"):
            pip_path = shutil.which(candidate)
            if pip_path:
                log.debug("found pip via which(%s): %s", candidate, pip_path)
                return [pip_path]

        return None

    def _cleanup_appenv_uv(self) -> None:
        """Remove leftover .appenv/.uv directory."""
        if self.uv_dir.exists():
            remove_path(self.uv_dir)


class NoValidUvError(RuntimeError):
    """Raised when no valid uv binary can be found or installed."""


@dataclass(frozen=True)
class AppEnvSettings:
    verbose: bool
    extras: list[str]
    basedir: Path


class AppEnv:
    def __init__(self, original_cwd: Path, settings: AppEnvSettings) -> None:
        self.base = settings.basedir.resolve()
        self.original_cwd = original_cwd
        self.settings = settings

        self.appenv_dir = self.base / ".appenv"
        self.appenv_script = self.base / "appenv"
        self.log_dir = self.appenv_dir / "logs"
        self.venv_real = self.appenv_dir / "venv"
        self.venv_link = self.base / ".venv"
        self.venv_python = self.venv_real / "bin" / "python"

    def run(self, command: str, argv: list[str]) -> None:
        log_dir = self._set_up_logdir()
        setup_logging(command, log_dir, self.settings.verbose)

        venv_path = self._prepare_venv(dev_mode=False)
        cmd_path = venv_path / "bin" / command

        if not cmd_path.exists():
            available = sorted(
                p.name
                for p in (venv_path / "bin").iterdir()
                if p.is_file() and not p.name.startswith("_")
            )
            print(f"Error: Binary '{command}' not found in {venv_path}/bin/")
            print()
            print(f"The symlink '{command}' determines which binary gets executed.")
            print()
            if available:
                print("Available binaries:")
                for name in available:
                    print(f"  {name}")
            else:
                print("No binaries found in the virtual environment.")
            print()
            print("Either:")
            print(f"  - Install a package that provides the '{command}' binary")
            print(f'  - Add a [project.scripts] entry: {command} = "pkg.module:main"')
            print("  - Or create a symlink with the name of an installed binary")
            sys.exit(EXIT_CODE_NOINPUT)

        argv = [str(cmd_path), *argv]
        os.environ["APPENV_BASEDIR"] = str(self.base)
        os.chdir(self.original_cwd)

        os.execv(str(cmd_path), argv)

    def meta(
        self, remaining_args: list[str] | None = None, prog: str = "appenv"
    ) -> None:
        log_dir = self._set_up_logdir()
        setup_logging(prog, log_dir, self.settings.verbose)

        # Parse the appenv arguments
        parser = argparse.ArgumentParser(
            prog=prog,
            usage="%(prog)s <COMMAND>",
            description=f"appenv {__version__}",
            formatter_class=GroupedHelpFormatter,
        )
        subparsers = parser.add_subparsers(title="Commands")
        p = subparsers.add_parser(
            "update-lockfile", help="Re-resolve dependencies and write uv.lock."
        )
        p.add_argument(
            "--diff",
            action="store_true",
            help="Show what would change without writing the lockfile.",
        )
        p.add_argument(
            "-v",
            "--verbose",
            action="store_true",
            help="Show what's happening under the hood.",
        )
        p.set_defaults(func=self.update_lockfile)

        p = subparsers.add_parser(
            "init",
            help="Set up a new project with pyproject.toml, symlink, and lockfile.",
        )
        p.add_argument(
            "path",
            nargs="?",
            default=None,
            help="Target directory for the new project (default: current directory).",
        )
        p.set_defaults(func=self.init)

        p = subparsers.add_parser(
            "migrate", help="Convert requirements.txt to pyproject.toml."
        )
        p.add_argument(
            "path",
            nargs="?",
            default=None,
            help="Target directory (default: current directory).",
        )
        p.set_defaults(func=self.migrate)

        p = subparsers.add_parser(
            "self-update", help="Replace the local script with the latest version."
        )
        p.add_argument(
            "--check",
            action="store_true",
            help="Exit 1 if the script is outdated, 0 if current.",
        )
        p.add_argument(
            "path",
            nargs="?",
            default=None,
            help=(
                "Target directory containing the appenv script"
                " (default: project directory)."
            ),
        )
        p.set_defaults(func=self.self_update)

        p = subparsers.add_parser(
            "reset", help="Delete the venv — next run rebuilds from scratch."
        )
        p.set_defaults(func=self.reset)

        p = subparsers.add_parser("version", help="Show appenv version.")
        p.set_defaults(func=self.show_version)

        p = subparsers.add_parser(
            "prepare", help="Create the virtual environment with pinned versions."
        )
        p.set_defaults(func=self.prepare)

        p = subparsers.add_parser("python", help="Run Python in the project venv.")
        p.set_defaults(func=self.python)

        p = subparsers.add_parser(
            "run",
            help="Run a script from the bin/ directory of the virtual env.",
        )
        p.add_argument("script", help="Name of the script to run.")
        p.set_defaults(func=self.run_script)

        p = subparsers.add_parser(
            "uv",
            help="Run any uv command with project paths set.",
        )
        p.set_defaults(func=self.run_uv)

        args, remaining = parser.parse_known_args(remaining_args)

        log.debug("args: %s", args)
        log.debug("remaining: %s", remaining)

        if not hasattr(args, "func"):
            if remaining:
                print(f"Error: unrecognized arguments: {' '.join(remaining)}")
                parser.print_help()
                sys.exit(EXIT_CODE_USAGE)
            parser.print_help()
            sys.exit(0)
        else:
            args.func(args, remaining)

    def prepare(
        self, args: Namespace | None = None, remaining: list[str] | None = None
    ) -> Path:
        """Prepare venv with production dependencies only."""
        return self._prepare_venv(dev_mode=False)

    def _chdir_to_project(self, target: Path) -> None:
        """Change to target directory and update all derived paths."""
        log.debug("chdir to %s", target)
        os.chdir(target)
        self.base = target.resolve()
        self.appenv_dir = self.base / ".appenv"
        self.appenv_script = self.base / "appenv"
        self.log_dir = self.appenv_dir / "logs"
        self.venv_real = self.appenv_dir / "venv"
        self.venv_link = self.base / ".venv"
        self.venv_python = self.venv_real / "bin" / "python"

    def init(
        self, args: Namespace | None = None, remaining: list[str] | None = None
    ) -> None:
        """Create a new pyproject.toml project."""
        if args and args.path:
            target = (self.original_cwd / args.path).resolve()
            target.mkdir(parents=True, exist_ok=True)
        else:
            target = self.original_cwd.resolve()

        self._chdir_to_project(target)

        # Check after chdir - now we check ./pyproject.toml
        pyproject = Pyproject(self.base)
        if pyproject.exists and pyproject.has_project_section:
            print(f"{pyproject.path} already has a [project] section")
            print("Nothing to do - edit it manually to make changes")
            sys.exit(EXIT_CODE_DATAERR)

        if pyproject.exists:
            print(f"Adding [project] section to existing {pyproject.path}\n")
        else:
            print(f"Let's create a new appenv project in {self.base}")
            print("I'll ask a few questions, then create pyproject.toml here\n")

        command_name = input(
            "Binary to expose (creates ./<name> symlink) [app] "
        ).strip()
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

        project_name = input(f"\nProject name [{target.name}]: ").strip()
        if not project_name:
            project_name = target.name

        description = input("Description []: ").strip()

        python_version = input("Minimum Python version [3.13]: ").strip()
        if not python_version:
            python_version = "3.13"

        self._ensure_appenv_script()

        pyproject = create_pyproject(
            target=target,
            project_name=project_name,
            description=description,
            dependencies=dependencies,
            python_version=python_version,
        )
        print(f"Created {pyproject.path}")

        self._set_up_command_symlink(
            command_name=command_name,
            project_name=project_name or target.name,
        )

        print("Generating new lock file ...")
        uv = ensure_uv(self.appenv_dir)
        self._uv_lock(uv, diff=False)

        ensure_gitignore(self.base, [".venv", ".appenv", ".batou-lock"])
        print("\n=== Appenv project initialized ===")
        print(f"\nUse `./{command_name}` to run the {command_name} binary")

    def migrate(
        self, args: Namespace | None = None, remaining: list[str] | None = None
    ) -> None:
        """Migrate from requirements.txt to pyproject.toml."""
        if args and args.path:
            target = (self.original_cwd / args.path).resolve()
            target.mkdir(parents=True, exist_ok=True)
        else:
            target = self.original_cwd.resolve()

        self._chdir_to_project(target)

        pyproject = Pyproject(self.base)
        if pyproject.has_project_section:
            print(
                "pyproject.toml already has [project] section in", str(self.base) + "."
            )
            print("Nothing to do.")
            return

        if pyproject.exists:
            print("Adding [project] section to existing pyproject.toml.\n")
        elif pyproject.can_be_created_from_requirements_txt:
            print("Migrating from requirements.txt to pyproject.toml...\n")
        else:
            print(f"No requirements.txt found in {self.base}.")
            print("Use 'init' to create a new project.")
            return

        self._ensure_appenv_script(update=True)

        uv = ensure_uv(self.appenv_dir)

        pyproject = pyproject.migrate_from_requirements_txt()
        pyproject.print_migration_info()

        uv_lock_out = self._uv_lock(uv, diff=False)
        print(uv_lock_out)

        # Also cleans up old .appenv hash-based venvs
        print("Preparing/cleaning .appenv directory ...")
        self._prepare_appenv_dir()

        ensure_gitignore(self.base, [".venv"])
        print("\n=== Pyproject Migration completed ===")
        print("requirements.{txt,lock} kept as legacy. You can delete these files now.")

    def self_update(
        self, args: Namespace | None = None, remaining: list[str] | None = None
    ) -> None:
        """Update the local ./appenv script to match the running version."""

        # Determine target script path
        if args and getattr(args, "path", None) is not None:
            target_script = Path(args.path).resolve() / "appenv"
        elif (
            os.environ.get("APPENV_BASEDIR")
            or self.base != Path(__file__).parent.resolve()
        ):
            target_script = self.appenv_script
        else:
            # Externally managed (uvx, pip install, etc.)
            print(
                "Error: appenv is running from an externally managed"
                " environment and cannot update itself in place."
            )
            print(
                "HINT: To update the appenv script in your current directory,"
                " use: appenv self-update ."
            )
            sys.exit(EXIT_CODE_USAGE)

        if not target_script.exists():
            print(f"Error: No appenv script found at {target_script}")
            sys.exit(EXIT_CODE_NOINPUT)

        local_version = self._extract_version(target_script)
        running_version = __version__
        local_label = local_version if local_version else "unknown"

        if local_version == running_version:
            print(f"{target_script} is already up-to-date (version {running_version}).")
            if args and args.check:
                sys.exit(0)
            return

        if args and args.check:
            print(
                f"Version drift detected: {target_script} is {local_label}, "
                f"running appenv is {running_version}."
            )
            sys.exit(1)

        # Perform the update
        bootstrap_data = Path(__file__).read_bytes()
        target_script.write_bytes(bootstrap_data)
        target_script.chmod(0o755)
        print(f"Updated {target_script} ({local_label} -> {running_version})")

    def python(self, args: Namespace, remaining: list[str]) -> None:
        self.run("python", remaining)

    def run_script(self, args: Namespace, remaining: list[str]) -> None:
        print("'run' has been removed. Use one of these instead:\n")
        print("  uv run <command>        — run any binary (includes dev dependencies)")
        print("  ./appenv python         — start Python REPL in the venv")
        print(f"  ln -s appenv {args.script}    — create a symlink for regular use")
        print(f"  ./{args.script}              — then run the {args.script} binary")
        sys.exit(EXIT_CODE_USAGE)

    def run_uv(self, args: Namespace, remaining: list[str]) -> None:
        """Run uv with the appenv-configured uv binary."""
        uv = ensure_uv(self.appenv_dir)

        # Tell uv where the venv lives (in .appenv/venv, not .venv)
        os.environ["UV_PROJECT_ENVIRONMENT"] = str(self.venv_real)

        uv_argv = [str(uv.bin), *remaining]
        os.chdir(self.base)
        os.execv(str(uv.bin), uv_argv)

    def show_version(
        self, args: Namespace | None = None, remaining: list[str] | None = None
    ) -> None:
        """Show appenv version."""
        print(f"appenv {__version__}")

    def reset(
        self, args: Namespace | None = None, remaining: list[str] | None = None
    ) -> None:
        """Remove appenv-managed files/directories"""
        log.debug("Resetting %s", self.settings.basedir)
        # Remove symlink if it exists
        log.debug("venv link %s", self.venv_link)
        if self.venv_link.is_symlink():
            print(f"Removing {self.venv_link} symlink ...")
            self.venv_link.unlink()

        # Remove real venv in .appenv
        log.debug("venv real %s", self.venv_real)
        if self.venv_real.exists():
            print(f"Removing {self.venv_real} ...")
            shutil.rmtree(self.venv_real)

        # Note: .venv may exist as a real directory (not managed by appenv)
        if self.venv_link.exists() and not self.venv_link.is_symlink():
            print(
                f"Note: {self.venv_link} exists but is not a symlink. "
                f"Not removing it automatically."
            )

        # Clean up old hash-based venvs in .appenv (keep logs, profiling)
        if self.appenv_dir.exists():
            for path in list(self.appenv_dir.iterdir()):
                if path.name not in {"venv", ".uv", "logs", "profiling", "current"}:
                    print(f"Removing {path} ...")
                    remove_path(path)

    def update_lockfile(
        self, args: Namespace | None = None, remaining: list[str] | None = None
    ) -> None:
        ensure_pyproject(self.base)
        uv = ensure_uv(self.appenv_dir)
        os.chdir(self.base)
        uv_lock_out = self._uv_lock(uv, diff=args.diff if args else False)
        print(uv_lock_out)

    def _ensure_appenv_script(self, *, update: bool = False) -> None:
        """
        Creates local ./appenv script if needed.

        When the script already exists and versions differ:
        - update=True: replaces it (used by migrate)
        - update=False: warns only (used by init)
        """
        log.debug("Looking for %s", self.appenv_script)
        if not self.appenv_script.exists():
            log.debug("Creating %s", self.appenv_script)
            bootstrap_data = Path(__file__).read_bytes()
            self.appenv_script.write_bytes(bootstrap_data)
            self.appenv_script.chmod(0o755)
            print(f"Created {self.appenv_script}")
            return

        local_version = self._extract_version(self.appenv_script)
        running_version = __version__
        log.debug(
            "Version check: local=%s, running=%s",
            local_version,
            running_version,
        )
        if local_version == running_version:
            log.debug("Versions match, skipping")
            return

        if update:
            local_label = local_version if local_version else "unknown"
            log.debug(
                "Updating %s: %s -> %s",
                self.appenv_script,
                local_label,
                running_version,
            )
            bootstrap_data = Path(__file__).read_bytes()
            self.appenv_script.write_bytes(bootstrap_data)
            self.appenv_script.chmod(0o755)
            print(f"Updated {self.appenv_script} ({local_label} -> {running_version})")
        else:
            local_label = local_version if local_version else "unknown"
            log.debug("Version mismatch, warning user")
            print(
                f"Warning: {self.appenv_script} is version {local_label}, "
                f"running appenv is {running_version}."
            )
            print("Run './appenv self-update' to update the script.")

    @staticmethod
    def _extract_version(script: Path) -> str | None:
        """Extract __version__ from an appenv script file."""
        content = script.read_text(errors="replace")
        match = re.search(r'__version__ = "([^"]+)"', content)
        return match.group(1) if match else None

    def _uv_lock(self, uv: UvBin, diff: bool) -> str:
        lock = LockFile(self.base)

        if diff:
            print("Diff mode: only check lockfile changes ...")
            update_info = lock.diff(uv, self.base, self.settings.verbose)
        else:
            old_lines = lock.read_lockfile_lines()
            print("Updating lock file ...")
            uv.cmd(["lock"], verbose=self.settings.verbose, cwd=self.base)

            update_info = lock.diff_summary(old_lines)

        return update_info

    def _uv_sync(self, *, dev_mode: bool, uv: UvBin) -> None:
        # Sync dependencies (idempotent)
        sync_args = ["sync"]

        if not dev_mode:
            sync_args.extend(["--no-dev", "--frozen"])

        if self.settings.extras:
            sync_args.extend(["--extra", ",".join(self.settings.extras)])

        log.debug("activated extras/optional deps: %s", self.settings.extras)
        uv.cmd(sync_args)

    def _set_up_logdir(self) -> Path:
        self.log_dir.mkdir(parents=True, exist_ok=True)
        return self.log_dir

    def _prepare_venv(self, dev_mode: bool) -> Path:
        ensure_pyproject(self.base)
        ensure_lock_file(self.base)
        uv = ensure_uv(self.appenv_dir)
        os.chdir(self.base)

        self._prepare_appenv_dir()
        # Tell uv where to put/find venv
        os.environ["UV_PROJECT_ENVIRONMENT"] = str(self.venv_real)

        log.debug("project base: %s", self.base)
        log.debug("venv: %s", self.venv_real)
        log.debug("Python: %s", Path(sys.executable).resolve())
        log.debug("dev mode: %s", dev_mode)

        # Check for the typical case that a Nix Python was garbage-collected so
        # the linked python won't be valid anymore.
        if self.venv_real.exists() and not self.venv_python.exists():
            log.debug("corrupted venv with missing bin/python, removing ...")
            shutil.rmtree(self.venv_real)

        # SPEC: stale-venv-recreate — check venv Python version against requires-python
        if self.venv_real.exists() and self.venv_python.exists():
            # SPEC: stale-venv-recreate — handle broken binary or malformed output
            try:
                result = cmd([str(self.venv_python), "--version"], quiet=True)
                venv_version_str = result.decode().strip()
                # Extract major.minor from e.g. "Python 3.10.0"
                venv_version = ".".join(venv_version_str.split()[1].split(".")[:2])
            except (ValueError, IndexError, OSError) as e:
                log.debug("stale-venv check failed: %s", e)
                print("Recreating venv: Python version could not be determined")
                shutil.rmtree(self.venv_real)
            else:
                min_version, max_version = Pyproject(self.base).requires_python
                if min_version and not version_satisfies_constraints(
                    venv_version, min_version, max_version
                ):
                    constraint = ">=" + min_version
                    if max_version:
                        constraint += ",<" + max_version
                    print(
                        f"Recreating venv: Python {venv_version} does not satisfy"
                        f" requires-python {constraint}"
                    )
                    shutil.rmtree(self.venv_real)

        if not self.venv_real.exists():
            print("Creating fresh venv with uv ...")
            # Use current Python (already selected by ensure_best_python)
            # Explicit path avoids uv downloading its own (breaks on NixOS, for example)
            uv.cmd(["venv", "--python", sys.executable, str(self.venv_real)])

        self._uv_sync(dev_mode=dev_mode, uv=uv)

        # Show venv python info AFTER sync (version may have changed)
        if self.venv_python.exists():
            log.debug("venv Python: %s", self.venv_python)
            log.debug("venv Python (realpath): %s", self.venv_python.resolve())
            result = cmd([str(self.venv_python), "--version"], quiet=True)
            log.debug("venv Python version: %s", result.decode().strip())

        # Create symlink for tool compatibility
        # (e.g., IDEs, formatters, linters that expect .venv)
        if self.venv_link.is_symlink():
            self.venv_link.unlink()
        if not self.venv_link.exists():
            self.venv_link.symlink_to(
                os.path.relpath(self.venv_real, self.base), target_is_directory=True
            )
        elif not self.venv_link.is_symlink():
            print(
                f"Warning: {self.venv_link} exists but is not a symlink. "
                f"Expected .venv -> {self.venv_real}. "
                f"Remove {self.venv_link} manually if you want appenv to manage it."
            )

        # Legacy link to current venv, doesn't change anymore with this implementation.
        current_link = self.appenv_dir / "current"
        if current_link.is_symlink():
            current_link.unlink()
        if not current_link.exists():
            current_link.symlink_to("venv", target_is_directory=True)

        return self.venv_real

    def _set_up_command_symlink(self, command_name: str, project_name: str) -> None:
        command_link = self.base / command_name
        if command_link.is_symlink() or command_link.exists():
            command_link.unlink(missing_ok=True)
        command_link.symlink_to("appenv")
        print(f"Created ./{command_name} -> appenv (runs the {command_name} binary)")

    def _prepare_appenv_dir(self) -> None:
        """Remove old hash-based venvs and files from .appenv directory."""
        self.appenv_dir.mkdir(exist_ok=True)
        keep = {"venv", ".uv", "logs", "profiling", "current"}
        for path in list(self.appenv_dir.iterdir()):
            if path.name not in keep:
                log.debug("removing old .appenv entry: %s ...", path.name)
                remove_path(path)

        # Remove dangling current symlink (left over from hash-based venvs)
        current = self.appenv_dir / "current"
        if current.is_symlink() and not current.exists():
            log.debug("removing dangling current symlink ...")
            current.unlink()


def ensure_uv(appenv_dir: Path) -> UvBin:
    """Ensure uv is available and meets minimum version.

    Exits with error if uv is not available or too old.
    Returns UvBin instance.
    """
    uv = UvBin(appenv_dir)
    log.debug("uv binary: %s", uv.bin)

    version = uv.version
    log.debug("uv version: %s", version)

    if version is None or not version.valid:
        print(f"Error: cannot use uv binary: {uv.bin}. Version is: {version}")
        print(f"Minimum required version: {UvVersion.minimum()}")
        sys.exit(EXIT_CODE_UNAVAILABLE)

    return uv


def ensure_pyproject(base: Path) -> Pyproject:
    """Ensure pyproject.toml exists with [project] section, return Pyproject."""
    pyproject = Pyproject(base)
    if pyproject.has_project_section:
        log.debug("pyproject %s has [project] section", pyproject.path)
        return pyproject

    if pyproject.exists:
        print(f"Error: {pyproject.path} has no [project] section.")
    else:
        print(f"Error: No pyproject config file at {pyproject.path} found.")
        print("appenv must be located next to pyproject.toml (not in a subdirectory)")

    if pyproject.can_be_created_from_requirements_txt:
        print("Legacy requirements.txt found.")
        print("Run: ./appenv migrate")
        sys.exit(EXIT_CODE_DATAERR)
    else:
        print("Run ./appenv init")
        sys.exit(EXIT_CODE_NOINPUT)


def ensure_lock_file(base: Path) -> LockFile:
    """Ensure lockfile exists, return LockFile instance."""
    lock = LockFile(base)
    if not lock.exists:
        print("No uv.lock found. Run: ./appenv update-lockfile")
        sys.exit(EXIT_CODE_NOINPUT)

    log.debug("uv.lock: %s", lock.path)
    return lock


def ensure_gitignore(base: Path, entries: list[str]) -> None:
    """Ensure .gitignore contains the given entries.

    Idempotent: appends only missing entries, never modifies existing content.
    """
    gitignore_path = base / ".gitignore"

    if gitignore_path.exists():
        existing_lines = gitignore_path.read_text().splitlines()
    else:
        existing_lines = []

    existing_set = {line for line in existing_lines if line.strip()}
    missing = [e for e in entries if e not in existing_set]

    if not missing:
        return

    new_content = "\n".join(existing_lines)
    if new_content and not new_content.endswith("\n"):
        new_content += "\n"
    new_content += "\n".join(missing) + "\n"
    gitignore_path.write_text(new_content)
    if existing_lines:
        print(f"Updated {gitignore_path}")
    else:
        print(f"Created {gitignore_path}")


def cmd(
    c: str | list[str],
    *,
    merge_stderr: bool = True,
    quiet: bool = False,
    cwd: str | None = None,
) -> bytes:
    # SPEC: SRS-F001-cmd-wrapper - Enrich subprocess errors with command output context
    try:
        if isinstance(c, str):
            cmd_list = [c]
            is_shell = True
        else:
            cmd_list = c
            is_shell = False
        stderr = subprocess.STDOUT if merge_stderr else None
        return subprocess.check_output(cmd_list, shell=is_shell, stderr=stderr, cwd=cwd)
    except subprocess.CalledProcessError as e:
        if not quiet:
            print(f"{c} returned with exit code {e.returncode}")
            print(e.output.decode("utf-8", "replace"))
        raise ValueError(e.output.decode("utf-8", "replace")) from e


def ensure_best_python(base: Path) -> None:
    """Ensure best Python for pyproject.toml workflow.

    Reads requires-python from pyproject.toml and selects the newest
    available Python that satisfies the constraint.
    """
    if "APPENV_BEST_PYTHON" in os.environ:
        return

    pyproject = Pyproject(base)
    min_version, max_version = pyproject.requires_python

    log.debug("requires-python constraints: min=%s, max=%s", min_version, max_version)
    if min_version is None:
        min_version = "3.10"

    available = find_available_pythons()
    log.debug("available Python candidates: %s", available)
    current_python = str(Path(sys.executable).resolve())

    for version, path in available:
        if not version_satisfies_constraints(version, min_version, max_version):
            log.debug("skipping python%s: does not satisfy constraints", version)
            continue

        resolved_path = str(Path(path).resolve())
        if resolved_path == current_python:
            # Already running this version
            log.debug("already running best Python: %s", resolved_path)
            return

        # Try whether this Python works
        try:
            subprocess.check_call(
                [resolved_path, "-c", "print(1)"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except subprocess.CalledProcessError:
            log.debug("skipping python%s: subprocess check failed", version)
            continue

        # Re-exec with this Python
        argv = [Path(path).name, *sys.argv]
        os.environ["APPENV_BEST_PYTHON"] = path
        log.debug("re-executing with Python: %s", path)
        os.execv(path, argv)

    # No suitable Python found
    if max_version:
        print(f"requires-python: >={min_version},<{max_version}")
    else:
        print(f"requires-python: >={min_version}")
    print("Available versions:")
    for version, path in available:
        print(f"  python{version}: {path}")
    sys.exit(EXIT_CODE_DATAERR)


def find_available_pythons() -> list[tuple[str, str]]:
    """Find all available Python versions in PATH.

    Returns list of (version_str, path) tuples, sorted by version (newest first).
    """
    pythons = [
        (f"3.{i}", path)
        for i in range(10, 25)
        if (path := shutil.which(f"python3.{i}"))
    ]

    # SPEC: macos-python-fallback — check unversioned python3 (Xcode on macOS)
    bare_python = shutil.which("python3")
    if bare_python:
        resolved_existing = {Path(p).resolve() for _, p in pythons}
        if Path(bare_python).resolve() not in resolved_existing:
            try:
                raw = subprocess.check_output(
                    [bare_python, "--version"], stderr=subprocess.STDOUT
                )
                parts = raw.decode().strip().split()
                # "Python 3.12.0" -> "3.12"
                version_str = ".".join(parts[1].split(".")[:2])
                major, minor = (int(x) for x in version_str.split("."))
                if major >= 3 and minor >= 10:
                    pythons.append((version_str, bare_python))
            except (OSError, subprocess.CalledProcessError):
                pass

    pythons.sort(key=lambda x: [int(p) for p in x[0].split(".")], reverse=True)
    return pythons


def print_colored_diff(
    old_content: str, new_content: str, fromfile: str, tofile: str
) -> bool:
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


def appenv_settings_from_env() -> AppEnvSettings:
    """Read settings from environment variables."""
    verbose = os.environ.get("APPENV_VERBOSE") is not None
    extras_raw = os.environ.get("APPENV_EXTRAS") or ""
    extras = cast(list[str], [e.strip() for e in extras_raw.split(",") if e.strip()])
    basedir_str = os.environ.get("APPENV_BASEDIR")
    basedir = Path(basedir_str) if basedir_str else Path(__file__).parent

    return AppEnvSettings(
        verbose=verbose,
        extras=extras,
        basedir=basedir,
    )


class ColoredCallerFormatter(logging.Formatter):
    """Formatter with dimmed caller info (funcName:lineno) and message."""

    dim = "\033[2m"
    reset = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        caller = f"{record.funcName}:{record.lineno}"
        message = super().format(record)
        return f"{self.dim}{caller}{self.reset} {message}"


def setup_logging(command_name: str, log_dir: Path, verbose: bool) -> None:
    """Setup command-specific logging with daily rotation."""
    log_file = log_dir / f"{command_name}.log"

    for handler in log.handlers[:]:
        handler.close()
    log.handlers.clear()
    log.setLevel(logging.DEBUG)

    file_handler = TimedRotatingFileHandler(log_file, when="midnight", backupCount=7)
    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(funcName)s:%(lineno)d %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler.setFormatter(file_formatter)
    log.addHandler(file_handler)

    if verbose:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.DEBUG)
        console_formatter = ColoredCallerFormatter("%(message)s")
        console_handler.setFormatter(console_formatter)
        log.addHandler(console_handler)

    log.debug("Logging configured log_file=%s verbose=%s", log_file, verbose)


def main() -> None:
    # Clear PYTHONPATH to ensure clean isolated environment.
    # Historical note: Some systems set PYTHONPATH globally which can interfere
    # with venv isolation. Clearing it ensures the venv's site-packages take precedence.
    os.environ.pop("PYTHONPATH", None)
    settings = appenv_settings_from_env()

    ensure_best_python(settings.basedir)

    original_cwd = Path.cwd()
    appenv = AppEnv(original_cwd, settings)

    # Determine whether we're being called as appenv or as an application name
    application_name = Path(__file__).stem
    if application_name == "appenv":
        if len(sys.argv) > 1:
            remaining = sys.argv[1:]
            appenv.meta(remaining)
        else:
            # No arguments: show help directly instead of passing "help" as command
            appenv.meta([])
    else:
        remaining = sys.argv[1:]
        appenv.run(application_name, remaining)


if __name__ == "__main__":  # pragma: no cover
    main()
