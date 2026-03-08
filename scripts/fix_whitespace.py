#!/usr/bin/env python
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Fix trailing whitespace and ensure files end with newline."""

import sys
from pathlib import Path

EXTENSIONS = {".py", ".toml", ".md", ".yaml", ".yml", ".txt", ".cfg", ".ini"}
EXCLUDE_DIRS = {
    ".tox",
    ".git",
    "__pycache__",
    ".venv",
    "htmlcov",
    ".appenv",
    "*.egg-info",
    "example",
}


def find_files(root: Path) -> list[Path]:
    """Find text files to fix."""
    files = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        # Skip excluded dirs
        if any(
            part in EXCLUDE_DIRS or part.endswith(".egg-info") for part in path.parts
        ):
            continue
        # Check extension
        if path.suffix in EXTENSIONS:
            files.append(path)
    return files


def fix_file(path: Path) -> bool:
    """Fix a single file. Returns True if file was modified."""
    try:
        content = path.read_text()
    except (UnicodeDecodeError, OSError):
        return False

    lines = content.splitlines(keepends=True)
    if not lines:
        return False

    original = content
    fixed_lines = []

    for line in lines:
        # Remove trailing whitespace but keep the line ending
        stripped = line.rstrip()
        # Preserve the original line ending style
        ending = line[len(stripped) :]
        fixed_lines.append(stripped + ending)

    # Ensure file ends with newline
    if fixed_lines and not fixed_lines[-1].endswith("\n"):
        fixed_lines[-1] += "\n"

    fixed = "".join(fixed_lines)

    if fixed != original:
        path.write_text(fixed)
        print(f"Fixed: {path}")
        return True

    return False


def main():
    """Fix whitespace in files."""
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")

    files = [root] if root.is_file() else find_files(root)

    modified = 0
    for path in files:
        if fix_file(path):
            modified += 1

    if modified:
        print(f"Fixed {modified} file(s)")
        sys.exit(1)  # Signal that files were modified
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
