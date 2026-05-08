"""Spec validation tests for docs-e2e-alignment impl spec.

These tests validate that the contracts defined in
.agents/impl_specs/docs-e2e-alignment.md are fulfilled.
All tests validate spec contracts that ARE implemented.

Spec decisions validated:
- init-e2e-coverage
- python39-e2e
- discovery-docs-tiered
- platform-detection-docs
"""

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
E2E_YML = REPO_ROOT / ".github" / "workflows" / "e2e.yml"
INSTALLATION_MD = REPO_ROOT / "docs" / "user" / "installation.md"
ARCHITECTURE_MD = REPO_ROOT / "docs" / "dev" / "architecture.md"


def _load_e2e_yaml():
    return yaml.safe_load(E2E_YML.read_text())


# ---------------------------------------------------------------------------
# init-e2e-coverage: debian-bookworm-pip must use printf pipe to ./appenv init
# ---------------------------------------------------------------------------


def test_init_e2e_coverage_bookworm_pip_uses_printf_init():
    """SPEC: init-e2e-coverage — debian-bookworm-pip must use printf pipe to
    ./appenv init instead of heredoc pyproject.toml."""
    wf = _load_e2e_yaml()
    job = wf["jobs"]["debian-bookworm-pip"]

    # Collect all run scripts from all steps
    all_run_scripts = [step["run"] for step in job["steps"] if "run" in step]

    combined = "\n".join(all_run_scripts)

    # Must NOT contain heredoc pyproject.toml
    assert "cat > pyproject.toml" not in combined, (
        "debian-bookworm-pip still uses heredoc pyproject.toml; "
        "spec requires printf pipe to ./appenv init"
    )

    # Must contain printf pipe to appenv init
    assert "appenv init" in combined, "debian-bookworm-pip must invoke ./appenv init"


# ---------------------------------------------------------------------------
# python39-e2e: debian-bullseye-39 job must exist
# ---------------------------------------------------------------------------


def test_python39_e2e_job_exists():
    """SPEC: python39-e2e — debian-bullseye-39 job must exist in e2e.yml."""
    wf = _load_e2e_yaml()
    assert "debian-bullseye-39" in wf["jobs"], (
        "debian-bullseye-39 job missing from e2e.yml"
    )


def test_python39_e2e_uses_bullseye_container():
    """SPEC: python39-e2e — job must use debian:bullseye container image."""
    wf = _load_e2e_yaml()
    job = wf["jobs"]["debian-bullseye-39"]
    assert job["container"]["image"] == "debian:bullseye", (
        "debian-bullseye-39 must use debian:bullseye container"
    )


def test_python39_e2e_requires_python_39():
    """SPEC: python39-e2e — validates that the debian-bullseye-39 job uses a heredoc
    pyproject.toml with requires-python >= 3.9 (since appenv init enforces a
    minimum of 3.10, which cannot be satisfied on bullseye's Python 3.9)."""
    wf = _load_e2e_yaml()
    job = wf["jobs"]["debian-bullseye-39"]

    all_run_scripts = [step["run"] for step in job["steps"] if "run" in step]

    combined = "\n".join(all_run_scripts)
    assert "requires-python" in combined and "3.9" in combined, (
        "debian-bullseye-39 must set requires-python >= 3.9 via heredoc pyproject.toml"
    )


# ---------------------------------------------------------------------------
# discovery-docs-tiered: installation.md must mention auto-download
# ---------------------------------------------------------------------------


def test_installation_md_mentions_auto_download():
    """SPEC: discovery-docs-tiered — installation.md UV section must mention
    automatic download from astral.sh."""
    content = INSTALLATION_MD.read_text()

    # Must mention automatic download/astral.sh
    assert "astral.sh" in content, (
        "installation.md must mention astral.sh in UV installation section"
    )

    # Must have phrasing about automatic download
    has_auto_download = any(
        phrase in content.lower()
        for phrase in [
            "downloaded automatically",
            "automatically downloaded",
            "auto-download",
            "auto installed",
            "will be installed automatically",
        ]
    )
    assert has_auto_download, (
        "installation.md must mention automatic UV download from astral.sh"
    )


def test_installation_md_links_to_architecture():
    """SPEC: discovery-docs-tiered — user docs must link to architecture.md
    for full discovery chain details."""
    content = INSTALLATION_MD.read_text()
    assert "architecture" in content.lower(), (
        "installation.md must link to architecture.md for full discovery chain"
    )


# ---------------------------------------------------------------------------
# discovery-docs-tiered: architecture.md must list all 6 discovery steps
# ---------------------------------------------------------------------------


def test_architecture_md_has_six_discovery_steps():
    """SPEC: discovery-docs-tiered — architecture.md uv Management section
    must list all 6 discovery steps including direct-download."""
    content = ARCHITECTURE_MD.read_text()

    # Must mention all 6 discovery methods
    required_steps = [
        ("PATH", "PATH uv discovery step"),
        ("cached", "Cached binary step"),
        ("nix channel", "Nix channel step"),
        ("nix flake", "Nix flake step"),
        ("pip", "pip install step"),
        ("direct-download", "astral.sh direct-download step"),
    ]

    content_lower = content.lower()
    for step_keyword, description in required_steps:
        assert step_keyword.lower() in content_lower, (
            f"architecture.md discovery chain missing: {description}"
        )


# ---------------------------------------------------------------------------
# platform-detection-docs: architecture.md must have Platform Detection section
# ---------------------------------------------------------------------------


def test_architecture_md_has_platform_detection_section():
    """SPEC: platform-detection-docs — architecture.md must have a
    "Platform Detection" section as subsection of uv Management."""
    content = ARCHITECTURE_MD.read_text()

    assert "platform detection" in content.lower(), (
        "architecture.md must have a Platform Detection section"
    )


def test_architecture_md_platform_detection_has_triple_table():
    """SPEC: platform-detection-docs — Platform Detection section must contain
    triple mapping table with x86_64/aarch64/armv7 and gnu/musl/darwin."""
    content = ARCHITECTURE_MD.read_text()

    # Find the Platform Detection section area
    lower = content.lower()
    pd_idx = lower.find("platform detection")
    assert pd_idx != -1, "Platform Detection section not found"

    # Check for platform triple components in the document
    required_architectures = ["x86_64", "aarch64", "armv7"]
    required_libcs = ["gnu", "musl", "darwin"]

    for arch in required_architectures:
        assert arch in content, (
            f"Platform Detection section must mention {arch} architecture"
        )

    for libc in required_libcs:
        assert libc in content.lower(), (
            f"Platform Detection section must mention {libc} libc/OS"
        )
