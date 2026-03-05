import os

import pytest


@pytest.fixture
def workdir(tmp_path):
    """Change to tmp_path for test duration, restore afterwards."""
    # Handle case where previous test removed current directory
    try:
        old = os.getcwd()
    except OSError:
        old = str(tmp_path)
    os.chdir(tmp_path)
    yield tmp_path
    try:
        os.chdir(old)
    except OSError:
        # If old directory no longer exists, use tmp_path
        os.chdir(tmp_path)


# Pattern example collection
_pattern_examples = {}


@pytest.fixture
def patterns(request):
    """Enhanced patterns fixture that collects examples."""
    from pytest_patterns.plugin import PatternsLib

    patterns_obj = PatternsLib()

    # Store reference to test name
    test_name = request.node.name
    test_file = request.node.fspath.basename

    # Wrap the full pattern to collect examples
    original_full = patterns_obj.full

    class PatternCollector:
        def __init__(self, original):
            self._original = original
            self._merged = False
            self._current_key = None

        def merge(self, *args, **kwargs):
            result = self._original.merge(*args, **kwargs)
            self._merged = True

            # Collect example after merge
            try:
                example = self._original.generate_example()

                # Store in global collection
                key = f"{test_file}::{test_name}"
                self._current_key = key
                if key not in _pattern_examples:
                    _pattern_examples[key] = {
                        "file": test_file,
                        "test": test_name,
                        "examples": [],
                    }
                # Store as dict with expected, actual will be filled in __eq__
                _pattern_examples[key]["examples"].append(
                    {"expected": example, "actual": None}
                )
            except Exception:
                pass  # Silently ignore if example generation fails

            return result

        def __eq__(self, actual):
            # Store actual output when comparison happens
            if self._current_key and self._current_key in _pattern_examples:
                examples = _pattern_examples[self._current_key]["examples"]
                if examples and examples[-1].get("actual") is None:
                    examples[-1]["actual"] = actual
            return self._original == actual

        def __getattr__(self, name):
            return getattr(self._original, name)

    patterns_obj.full = PatternCollector(original_full)  # type: ignore[attr-defined-but-dynamic]

    return patterns_obj


def pytest_sessionfinish(session, exitstatus):
    """Write collected pattern examples to Markdown file."""
    if not _pattern_examples:
        return

    from pathlib import Path

    output_file = Path(session.startpath) / ".pytest-patterns-examples.md"

    # Group by test file
    by_file = {}
    for _key, data in _pattern_examples.items():
        filename = data["file"]
        if filename not in by_file:
            by_file[filename] = []
        by_file[filename].append(data)

    # Write Markdown
    with output_file.open("w") as f:
        f.write("# pytest-patterns Examples\n\n")
        f.write("Auto-generated from test suite.\n\n")
        f.write(f"Generated: {session.startdir}\n\n")
        f.write("---\n\n")

        for filename in sorted(by_file.keys()):
            tests = by_file[filename]

            # Extract test file name without extension
            file_display = (
                filename.replace("test_", "")
                .replace(".py", "")
                .replace("_", " ")
                .title()
            )
            f.write(f"## {file_display}\n\n")

            for test_data in tests:
                test_name = test_data["test"]
                # Clean up test name
                test_display = test_name.replace("test_", "").replace("_", " ")

                f.write(f"### {test_display}\n\n")

                for example in test_data["examples"]:
                    # Handle both old format (string) and new format (dict)
                    if isinstance(example, dict):
                        f.write("**Expected:**\n\n")
                        f.write(f"```\n{example.get('expected', 'N/A')}\n```\n\n")
                        actual = example.get("actual")
                        if actual is not None:
                            f.write("**Actual:**\n\n")
                            f.write(f"```\n{actual}\n```\n\n")
                    else:
                        # Legacy format
                        f.write(f"```\n{example}\n```\n\n")

            f.write("---\n\n")

    print(f"\n✓ Pattern examples written to: {output_file.name}")
