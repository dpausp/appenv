"""Type stubs for appenv."""

import argparse
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple, TypeAlias

__version__: str

log: logging.Logger

PYPROJECT_TOML: str
REQUIREMENTS_TXT: str
UV_LOCK: str
UV_MIN_VERSION: tuple[int, int, int]

# Exit codes (BSD sysexits.h conventions)
EXIT_CODE_DATAERR: int
EXIT_CODE_NOINPUT: int
EXIT_CODE_UNAVAILABLE: int

# Type aliases for editable source structures
EditableSpec: TypeAlias = dict[str, str | list[str]]
EditableSourceConfig: TypeAlias = dict[str, str | bool]
EditableSources: TypeAlias = dict[str, EditableSourceConfig]

class GroupedHelpFormatter(argparse.HelpFormatter):
    """Group subcommands by category in help output."""

    GROUPS: list[tuple[str, list[str]]]
    def _format_action(self, action: argparse.Action) -> str: ...

class RequirementsTxtInfo(NamedTuple):
    dependencies: list[str]
    editable_sources: EditableSourceConfig
    editable_dep_strings: list[str]
    editable_warnings: list[str]
    python_versions: list[str]

class Pyproject:
    def __init__(self, base: Path) -> None: ...
    def migrate_from_requirements_txt(self) -> Pyproject: ...
    @staticmethod
    def generate(
        project_name: str,
        description: str,
        dependencies: list[str],
        python_version: str,
        editable_sources: EditableSources,
        existing_pyproject: Pyproject | None,
    ) -> Pyproject: ...

    path: Path
    requirements_txt: Path
    content: str
    exists: bool
    has_project_section: bool
    can_be_created_from_requirements_txt: bool

class InvalidVersionError(ValueError):
    version_str: str
    def msg(self) -> None: ...

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

def cmd(
    c: str | list[str],
    *,
    merge_stderr: bool = True,
    quiet: bool = False,
    cwd: str | None = None,
) -> bytes: ...
def setup_logging(command_name: str, log_dir: Path, verbose: bool) -> None: ...
def cleanup_old_logs(log_dir: Path, max_age_days: int = 7) -> None: ...
def print_colored_diff(
    old_content: str, new_content: str, fromfile: str, tofile: str
) -> bool: ...
def _cleanup_appenv_uv(base: Path | None) -> None: ...
def _try_uv_from_path(base: Path | None) -> Path | None: ...
def _try_uv_from_appenv_dir(base: Path | None) -> Path | None: ...
def _try_uv_from_nix(base: Path | None) -> Path | None: ...
def _try_uv_from_pip() -> Path | None: ...
def get_uv_bin(base: Path | None = None) -> Path: ...
def ensure_uv(base: Path | None = None) -> Path: ...
def uv_cmd(
    uv_bin: Path,
    args: list[str],
    verbose: bool = False,
    **kwargs: object,
) -> str: ...
def ensure_best_python(base: Path) -> None: ...
def parse_requires_python(pyproject_path: Path) -> tuple[str | None, str | None]: ...
def find_available_pythons() -> list[tuple[str, str]]: ...
def find_project_base(base: Path, original_cwd: Path) -> Path: ...
def version_satisfies_constraints(
    version: str, min_version: str, max_version: str | None = None
) -> bool: ...
def get_uv_version(uv_bin: Path) -> UvVersion: ...
def parse_editable_spec(spec: str) -> EditableSpec | None: ...
def extract_package_name_from_path(path: str, base_dir: Path) -> str | None: ...
def _parse_requirements_file(
    requirements_path: Path,
) -> RequirementsTxtInfo: ...
def _parse_python_preference(content: str) -> list[str]: ...
def _generate_pyproject_content(
    project_name: str,
    description: str,
    dependencies: list[str],
    python_version: str,
    editable_sources: EditableSources,
    existing_content: str | None = None,
) -> str: ...
def _process_editable_installs(
    specs: list[str], base_dir: Path
) -> tuple[EditableSources, list[str], list[str]]: ...
def _print_migration_info(
    editable_warnings: list[str],
    editable_sources: EditableSources,
    dependencies: list[str],
    python_version: str,
) -> None: ...
def _cleanup_old_appenv_entries(appenv_dir: Path) -> None: ...
def _setup_command_symlink(
    target: Path,
    command_name: str | None,
    appenv_script: Path,
    project_name: str,
) -> str: ...
def ensure_pyproject(base: Path) -> Pyproject: ...
def ensure_lock_file(base: Path) -> Path: ...
def _detect_command_name() -> str: ...
def main() -> None: ...

@dataclass(frozen=True)
class AppEnvSettings:
    verbose: bool
    extras: str | None
    profile: bool
    profile_output: str | None
    basedir: Path | None

    @staticmethod
    def from_env() -> AppEnvSettings: ...

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
    def meta(
        self, remaining_args: list[str] | None = None, prog: str = "appenv"
    ) -> None: ...
    def run(self, command: str, argv: list[str]) -> None: ...
    def setup_logdir(self) -> Path: ...
    def _prepare_venv(self, dev_mode: bool = False) -> str: ...
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
    def _init_project(
        self,
        pyproject: Pyproject,
        target: Path,
        project_name: str | None = None,
        description: str = "",
        dependencies: list[str] | None = None,
        editable_sources: EditableSources | None = None,
        python_version: str | None = None,
        command_name: str | None = None,
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
    def _find_profile(
        self, args_file: str | None, message_prefix: str = "Showing"
    ) -> Path: ...
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

def _read_lockfile_lines(lock_file: Path) -> set[str]: ...
def _run_uv_lock_diff(uv_bin: Path, base: Path, verbose: bool) -> str: ...
def _create_lockfile_summary(old_lines: set[str], new_lines: set[str]) -> str: ...
