import argparse
import logging
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple

__version__: str

log: logging.Logger

# Exit codes (BSD sysexits.h conventions)
EXIT_CODE_DATAERR: int
EXIT_CODE_NOINPUT: int
EXIT_CODE_UNAVAILABLE: int

COMMAND_GROUPS: OrderedDict[str, tuple[str]]

class GroupedHelpFormatter(argparse.HelpFormatter):
    def _format_action(self, action: argparse.Action) -> str: ...

class RequirementsTxtInfo(NamedTuple):
    dependencies: list[str]
    editable_dependencies: list[str]
    python_versions: list[str]

def version_satisfies_constraints(
    version: str, min_version: str, max_version: str | None = None
) -> bool: ...

class Pyproject:
    path: Path
    requirements_path: Path
    content: str
    exists: bool
    has_project_section: bool
    can_be_created_from_requirements_txt: bool
    requirements_txt_info: RequirementsTxtInfo | None

    def __init__(self, base: Path) -> None: ...
    def migrate_from_requirements_txt(self) -> Pyproject: ...
    @property
    def requires_python(self) -> tuple[str | None, str | None]: ...
    def print_migration_info(self) -> None: ...
    def _parse_requirements_file(self) -> RequirementsTxtInfo: ...
    def _parse_python_preference(self) -> list[str]: ...
    def _generate_updated_content(
        self,
        project_name: str,
        description: str,
        dependencies: list[str],
        python_version: str,
    ) -> str: ...

def create_pyproject(
    project_name: str,
    description: str,
    dependencies: list[str],
    python_versions: list[str],
) -> Pyproject: ...

class LockFile:
    path: Path
    exists: bool

    def __init__(self, base: Path) -> None: ...
    @property
    def content(self) -> str: ...
    def diff(self, uv_bin: UvBin, base: Path, verbose: bool) -> str: ...
    def diff_summary(self, old_lines: set[str]) -> str: ...
    def _read_lockfile_lines(self) -> set[str]: ...

@dataclass(order=True, frozen=True)
class UvVersion:
    major: int
    minor: int
    patch: int

    @property
    def valid(self) -> bool: ...
    @staticmethod
    def unknown() -> UvVersion: ...
    @staticmethod
    def minimum() -> UvVersion: ...
    @staticmethod
    def from_string(version_str: str) -> UvVersion: ...

class NoValidUvError(RuntimeError): ...

class UvBin:
    uv_bin: Path

    def __init__(self, base: Path) -> None: ...
    def cmd(
        self,
        args: list[str],
        verbose: bool = False,
        **kwargs: object,
    ) -> str: ...
    @property
    def uv_version(self) -> UvVersion: ...
    def _get_uv_bin(self) -> Path: ...
    def _try_uv_from_path(self) -> Path | None: ...
    def _try_uv_from_appenv_dir(self) -> Path | None: ...
    def _try_uv_from_nix(self) -> Path | None: ...
    def _try_uv_from_pip(self) -> Path | None: ...
    def _cleanup_appenv_uv(self) -> None: ...

def ensure_uv(base: Path) -> UvBin: ...
def ensure_pyproject(base: Path) -> Pyproject: ...
def ensure_lock_file(base: Path) -> LockFile: ...
def cmd(
    c: str | list[str],
    *,
    merge_stderr: bool = True,
    quiet: bool = False,
    cwd: str | None = None,
) -> bytes: ...
def ensure_best_python(base: Path) -> None: ...
def find_available_pythons() -> list[tuple[str, str]]: ...
def print_colored_diff(
    old_content: str, new_content: str, fromfile: str, tofile: str
) -> bool: ...

@dataclass(frozen=True)
class AppEnvSettings:
    verbose: bool
    extras: list[str]
    profile: bool
    profile_output: str | None
    basedir: Path | None

class AppEnv:
    base: Path
    appenv_dir: Path
    appenv_script: Path
    log_dir: Path
    original_cwd: Path
    settings: AppEnvSettings

    def __init__(
        self, base: Path, original_cwd: Path, settings: AppEnvSettings
    ) -> None: ...
    @property
    def project_base(self) -> Path: ...
    def meta(
        self, remaining_args: list[str] | None = None, prog: str = "appenv"
    ) -> None: ...
    def run(self, command: str, argv: list[str]) -> None: ...
    def prepare(
        self,
        args: argparse.Namespace | None = None,
        remaining: list[str] | None = None,
    ) -> str: ...
    def develop(
        self,
        args: argparse.Namespace | None = None,
        remaining: list[str] | None = None,
    ) -> str: ...
    def init(
        self,
        args: argparse.Namespace | None = None,
        remaining: list[str] | None = None,
    ) -> None: ...
    def migrate(
        self,
        args: argparse.Namespace | None = None,
        remaining: list[str] | None = None,
    ) -> None: ...
    def python(self, args: argparse.Namespace, remaining: list[str]) -> None: ...
    def run_script(self, args: argparse.Namespace, remaining: list[str]) -> None: ...
    def run_uv(self, args: argparse.Namespace, remaining: list[str]) -> None: ...
    def show_version(
        self,
        args: argparse.Namespace | None = None,
        remaining: list[str] | None = None,
    ) -> None: ...
    def show_settings(
        self,
        args: argparse.Namespace | None = None,
        remaining: list[str] | None = None,
    ) -> None: ...
    def _find_profile(self, args_file: str | None, message_prefix: str) -> Path: ...
    def profiling_list(
        self, args: argparse.Namespace, remaining: list[str] | None = None
    ) -> None: ...
    def profiling_show(
        self, args: argparse.Namespace, remaining: list[str] | None = None
    ) -> None: ...
    def profiling_snakeviz(
        self, args: argparse.Namespace, remaining: list[str] | None = None
    ) -> None: ...
    def reset(
        self,
        args: argparse.Namespace | None = None,
        remaining: list[str] | None = None,
    ) -> None: ...
    def update_lockfile(
        self,
        args: argparse.Namespace | None = None,
        remaining: list[str] | None = None,
    ) -> None: ...
    def _set_up_logdir(self) -> Path: ...
    def _init_project(
        self,
        pyproject: Pyproject,
        target: Path,
        project_name: str | None = None,
        description: str = "",
        dependencies: list[str] | None = None,
        python_version: str | None = None,
        command_name: str | None = None,
    ) -> None: ...
    def _prepare_venv(self, dev_mode: bool = False) -> str: ...
    def _cleanup_old_appenv_entries(self) -> None: ...
    def _set_up_command_symlink(
        self,
        command_name: str | None,
        project_name: str,
    ) -> str: ...

def appenv_settings_from_env() -> AppEnvSettings: ...
def setup_logging(command_name: str, log_dir: Path, verbose: bool) -> None: ...
def cleanup_old_logs(log_dir: Path, max_age_days: int = 7) -> None: ...
def detect_command_name() -> str: ...
def main() -> None: ...
