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
    # AI-friendly output (llms.txt)
    "sphinx_llm.txt",
    # UX enhancements
    "sphinx_copybutton",
    "sphinx_design",
    "sphinx_togglebutton",
    # Diagrams
    "sphinx.ext.graphviz",
    # Planned features / TODOs
    "sphinx.ext.todo",
    # Social sharing metadata
    "sphinxext.opengraph",
]

# source_suffix: autoapi generates .rst internally, so register both
source_suffix = {".md": "markdown", ".rst": "restructuredtext"}

# autoapi configuration
autoapi_type = "python"
autoapi_dirs = ["../src"]
autoapi_file_patterns = ["*.py"]
autoapi_generate_api_docs = True
autoapi_add_toctree_entry = True
autoapi_options = [
    "members",
    "undoc-members",
    "show-inheritance",
    "show-module-summary",
]
autoapi_keep_files = True
autoapi_python_use_implicit_namespaces = True


# Skip private members (underscore prefix except dunder)
def autoapi_skip_member(
    _app, _what: str, name: str, _obj, skip: bool, _options
) -> bool:
    if name.startswith("_") and not name.startswith("__"):
        return True
    return skip


def _suppress_autoapi_orphan_warnings(app, env, docnames):
    """Post-build hook: fix autoapi toctree for single-file modules.

    autoapi generates an empty toctree in autoapi/index.rst when the source
    is a single .py file (not a package). Add the generated module page so
    it is not reported as orphan.
    """
    autoapi_index = Path(app.srcdir) / "autoapi" / "index.rst"
    if not autoapi_index.exists():
        return
    content = autoapi_index.read_text()
    if "src/appenv/index" in content:
        return
    content = content.replace(
        ".. toctree::\n   :titlesonly:\n\n\n",
        ".. toctree::\n   :titlesonly:\n\n   src/appenv/index\n\n",
    )
    autoapi_index.write_text(content)


def setup(app):
    app.connect("autoapi-skip-member", autoapi_skip_member)
    app.connect("env-before-read-docs", _suppress_autoapi_orphan_warnings)


# MyST configuration
myst_enable_extensions = [
    "colon_fence",
    "deflist",
    "fieldlist",
    "tasklist",
    "dollarmath",
]
myst_heading_anchors = 3
myst_all_links_external = False

# sphinx-copybutton configuration
copybutton_prompt_text = r">>> |\.\.\. |\$ |In \[\d*\]: | "
copybutton_prompt_is_regexp = True

# Type hints presentation
autodoc_typehints = "description"
autodoc_typehints_description_target = "documented"

# sphinx-llm configuration
llms_txt_build_parallel = True
llms_txt_full_build = True
llms_txt_suffix_mode = "auto"
llms_txt_description = (
    "appenv - Self-contained bootstrapping and updating of Python CLI applications"
)

# sphinx.ext.todo configuration
todo_include_todos = True

# sphinx.ext.graphviz configuration
graphviz_output_format = "svg"

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

# Suppress specific warnings that are known and harmless
suppress_warnings = [
    "myst.header",
]
