"""Sphinx configuration for appenv documentation."""

import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# Project information
project = "appenv"
copyright = "2026, Flying Circus"
author = "Christian Theune"

# Read version from source
version_path = Path(__file__).parent.parent / "src" / "appenv.py"
for line in version_path.read_text().splitlines():
    if line.startswith("__version__"):
        release = version = line.split('"')[1]
        break
else:
    release = version = "dev"

# Extensions
extensions = [
    # Markdown support
    "myst_parser",
    # Automatic API documentation
    "autoapi.extension",
    # Source code viewing
    "sphinx.ext.viewcode",
    # Type hints in documentation
    "sphinx_autodoc_typehints",
    # Copy-to-clipboard for code blocks
    "sphinx_copybutton",
]

# autoapi configuration
autoapi_type = "python"
autoapi_dirs = ["../src"]
autoapi_file_patterns = ["*.py"]
autoapi_generate_api_docs = True
autoapi_add_toctree_entry = False
autoapi_options = [
    "members",
    "undoc-members",
    "show-inheritance",
    "show-module-summary",
]
autoapi_keep_files = False
autoapi_python_use_implicit_namespaces = True


# Skip private members and test fixtures
def autoapi_skip_member(app, what, name, obj, skip, options):
    if name.startswith("_") and not name.startswith("__"):
        return True
    return skip


def setup(app):
    app.connect("autoapi-skip-member", autoapi_skip_member)


# MyST configuration
myst_enable_extensions = [
    "colon_fence",
    "deflist",
    "fieldlist",
]
myst_heading_anchors = 3
myst_all_links_external = False

# sphinx-copybutton configuration
copybutton_prompt_text = r">>> |\.\.\. |\$ |In \[\d*\]: | "
copybutton_prompt_is_regexp = True

# Type hints presentation
autodoc_typehints = "description"
autodoc_typehints_description_target = "documented"

# Theme configuration
html_theme = "furo"
html_title = "appenv Documentation"
html_theme_options = {
    "source_repository": "https://github.com/flyingcircusio/appenv/",
    "source_branch": "main",
    "source_directory": "docs/",
    "sidebar_hide_name": False,
    "navigation_with_keys": True,
    "light_css_variables": {
        "font-stack": "Inter, sans-serif",
    },
}

# Templates path
templates_path = ["_templates"]

# Exclude patterns
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

# Coverage-based documentation note
# This module has 87% test coverage - Tier 1 (full documentation priority)
