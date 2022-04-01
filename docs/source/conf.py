#
# weaver documentation build configuration file, created by
# sphinx-quickstart on Fri Oct 23 10:58:16 2015.
#
# This file is execfile()d with the current directory set to its
# containing dir.
#
# Note that not all possible configuration values are present in this
# autogenerated file.
#
# All configuration values have a default; values that are commented out
# serve to show the default.

# note:
#   ignore invalid-name convention flagged by codacy/pylint
#   as they refer to valid setting names defined by sphinx
# pylint: disable=C0103,invalid-name
# pylint: disable=C0209,consider-using-f-string

import json
import logging
import os
import re
import sys

# If extensions (or modules to document with autodoc) are in another directory,
# add these directories to sys.path here. If the directory is relative to the
# documentation root, use os.path.abspath to make it absolute, like shown here.
DOC_SRC_ROOT = os.path.abspath(os.path.dirname(__file__))
DOC_DIR_ROOT = os.path.dirname(DOC_SRC_ROOT)
DOC_PRJ_ROOT = os.path.dirname(DOC_DIR_ROOT)
DOC_BLD_ROOT = os.path.join(DOC_DIR_ROOT, "build")
sys.path.insert(0, os.path.abspath(DOC_SRC_ROOT))
sys.path.insert(0, os.path.abspath(DOC_DIR_ROOT))
sys.path.insert(0, os.path.abspath(DOC_PRJ_ROOT))

from weaver import __meta__  # isort:skip # noqa: E402 # pylint: disable=C0413

# for api generation
from weaver.wps_restapi.api import get_openapi_json  # isort:skip # noqa: E402
from pyramid.config import Configurator  # isort:skip # noqa: E402
from sphinx.domains.std import warn_missing_reference  # isort:skip # noqa: E402

DOC_PKG_ROOT = os.path.join(DOC_PRJ_ROOT, __meta__.__name__)

# -- General configuration ---------------------------------------------

# If your documentation needs a minimal Sphinx version, state it here.
needs_sphinx = "3.5"    # see requirements-doc.txt

# Add any Sphinx extension module names here, as strings. They can be
# extensions coming with Sphinx (named "sphinx.ext.*") or your custom ones.
sys.path.append(os.path.join(DOC_DIR_ROOT, "_extensions"))
extensions = [
    "doc_redirect",         # redirect literal RST references -> built HTML page
    "sphinxarg.ext",        # render argparse CLI definitions
    "sphinxcontrib.redoc",  # generate live OpenAPI with this doc
    "sphinx.ext.autodoc",   # document code docstrings
    "sphinx.ext.autosectionlabel",  # help make cross-references to title/sections
    "cloud_sptheme.ext.autodoc_sections",   # allow sections in docstrings code
    "sphinx.ext.githubpages",   # for publishing the doc to github pages
    "sphinx.ext.todo",          # support directives
    "sphinx.ext.viewcode",      # add links to highlighted source code
    "sphinx.ext.intersphinx",   # add links to other projects documentation
    "autoapi.extension",        # generate source code documentation
    "sphinx_autodoc_typehints",     # support '# type: (...) -> ...' typing
    "pywps.ext_autodoc",        # extra autodoc for PyWPS processes
    "sphinx_paramlinks",        # allow ':paramref:`<>`' references in docstrings
]

# note: see custom extension documentation
doc_redirect_ignores = [
    re.compile(r"weaver\..*"),  # autoapi generated files
    re.compile(r"index.*"),
]


def doc_redirect_include(file_path):
    return file_path.endswith(".rst") and not any(re.match(regex, file_path) for regex in doc_redirect_ignores)


doc_redirect_map = {}
for _dir in [DOC_SRC_ROOT, DOC_PRJ_ROOT]:
    doc_redirect_map.update({
        "docs/source/{}".format(file_name): file_name
        for file_name in os.listdir(_dir)
        if doc_redirect_include(file_name)
    })
    doc_redirect_map.update({
        file_name: file_name
        for file_name in os.listdir(_dir)
        if doc_redirect_include(file_name)
    })

# generate openapi
# note:
#   setting 'weaver.build_docs' allows to ignore part of code that cause problem or require unnecessary
#   configuration for the purpose of parsing the source to generate the OpenAPI
config = Configurator(settings={"weaver.wps": True, "weaver.wps_restapi": True, "weaver.build_docs": True})
config.include("weaver")  # need to include package to apply decorators and parse routes
api_spec_file = os.path.join(DOC_BLD_ROOT, "api.json")
# must disable references when using redoc (alpha version note rendering them correctly)
api_spec_json = get_openapi_json(http_host="example", http_scheme="https", use_docstring_summary=True, use_refs=False)
if not os.path.isdir(DOC_BLD_ROOT):
    os.makedirs(DOC_BLD_ROOT)
with open(api_spec_file, "w") as f:
    json.dump(api_spec_json, f)

redoc = [{
    "name": __meta__.__title__,
    "page": "api",  # rendered under '{root}/api.html'
    "spec": api_spec_file,
    "embed": True,
    "opts": {
        "lazy-rendering": True,
        "hide-hostname": True
    }
}]
# must use next version (2.x-alpha) because default 1.x does not support OpenAPIv3
redoc_uri = "https://cdn.jsdelivr.net/npm/redoc@next/bundles/redoc.standalone.js"

autoapi_type = "python"
autoapi_dirs = [DOC_PKG_ROOT]
autoapi_file_pattern = "*.py"
autoapi_options = ["members", "undoc-members", "private-members"]
autoapi_python_class_content = "both"   # class|both|init
autoapi_template_dir = "../_templates/autoapi"

# sphinx_autodoc_typehints
set_type_checking_flag = False
typehints_fully_qualified = True
always_document_param_types = True

# Add any paths that contain templates here, relative to this directory.
templates_path = ["_templates"]

# The suffix(es) of source filenames.
# You can specify multiple suffix as a list of string:
# source_suffix = ['.rst', '.md']
source_suffix = ".rst"

# The encoding of source files.
# source_encoding = 'utf-8-sig'

# The master toctree document.
master_doc = "index"
master_title = "{} Documentation".format(__meta__.__title__)

# General information about the project.
project = __meta__.__title__
copyright = __meta__.__license_short__
author = __meta__.__author__

# The version info for the project you're documenting, acts as replacement for
# |version| and |release|, also used in various other places throughout the
# built documents.
#
# The short X.Y version.
version = __meta__.__version__
# The full version, including alpha/beta/rc tags.
release = __meta__.__version__

# The language for content autogenerated by Sphinx. Refer to documentation
# for a list of supported languages.
#
# This is also used if you do content translation via gettext catalogs.
# Usually you set "language" from the command line for these cases.
language = "en"

# allow conversion of quotes and repeated dashes to other representation characters
# https://www.sphinx-doc.org/en/master/usage/configuration.html#confval-smartquotes
# To avoid problems with '--param' employed in document of CLI, provide them as ``--param``.
smartquotes = True

# There are two options for replacing |today|: either, you set today to some
# non-false value, then it is used:
# today = ''
# Else, today_fmt is used as the format for a strftime call.
# today_fmt = '%B %d, %Y'

# List of patterns, relative to source directory, that match files and
# directories to ignore when looking for source files.
exclude_patterns = []

# The reST default role (used for this markup: `text`) to use for all
# documents.
# default_role = None

# If true, '()' will be appended to :func: etc. cross-reference text.
# add_function_parentheses = True

# If true, the current module name will be prepended to all description
# unit titles (such as .. function::).
# add_module_names = True

# If true, sectionauthor and moduleauthor directives will be shown in the
# output. They are ignored by default.
# show_authors = False

# The name of the Pygments (syntax highlighting) style to use.
pygments_style = "sphinx"

# A list of ignored prefixes for module index sorting.
# modindex_common_prefix = []

# If true, keep warnings as "system message" paragraphs in the built documents.
# keep_warnings = False

# If true, `todo` and `todoList` produce output, else they produce nothing.
todo_include_todos = True


# -- Options for HTML output ----------------------------------------------

# The theme to use for HTML and HTML Help pages.  See the documentation for
# a list of builtin themes.
# html_theme = "alabaster"
# html_theme = "nature"
html_theme = "sphinx_rtd_theme"

# otherwise, readthedocs.org uses their theme by default, so no need to specify it

# Theme options are theme-specific and customize the look and feel of a theme
# further.  For a list of options available for each theme, see the
# documentation.
html_theme_options = {
    "navigation_depth": 4,  # TOC, RTD theme
}

# Add any paths that contain custom themes here, relative to this directory.
# html_theme_path = []

# The name for this set of Sphinx documents.  If None, it defaults to
# "<project> v<release> documentation".
# html_title = None

# A shorter title for the navigation bar.  Default is the same as html_title.
# html_short_title = None

# The name of an image file (relative to this directory) to place at the top
# of the sidebar.
# html_logo = None

# The name of an image file (within the static path) to use as favicon of the
# docs.  This file should be a Windows icon file (.ico) being 16x16 or 32x32
# pixels large.
# html_favicon = None

# Add any paths that contain custom static files (such as style sheets) here,
# relative to this directory. They are copied after the builtin static files,
# so a file named "default.css" will overwrite the builtin "default.css".
html_static_path = ["../_static"]

# override some styles of the selected theme
html_css_files = ["custom.css"]

# Add any extra paths that contain custom files (such as robots.txt or
# .htaccess) here, relative to this directory. These files are copied
# directly to the root of the documentation.
# html_extra_path = []

# If not '', a 'Last updated on:' timestamp is inserted at every page bottom,
# using the given strftime format.
html_last_updated_fmt = "%Y-%m-%d"

# If true, SmartyPants will be used to convert quotes and dashes to
# typographically correct entities.
# html_use_smartypants = True

# Custom sidebar templates, maps document names to template names.
html_sidebars = {
    # add full TOC of the doc
    "**": ["globaltoc.html", "relations.html", "sourcelink.html", "searchbox.html"]
}

# Additional templates that should be rendered to pages, maps page names to
# template names.
# html_additional_pages = {}

# If false, no module index is generated.
# html_domain_indices = True

# If false, no index is generated.
# html_use_index = True

# If true, the index is split into individual pages for each letter.
# html_split_index = False

# If true, links to the reST sources are added to the pages.
# html_show_sourcelink = True

# If true, "Created using Sphinx" is shown in the HTML footer. Default is True.
# html_show_sphinx = True

# If true, "(C) Copyright ..." is shown in the HTML footer. Default is True.
# html_show_copyright = True

# If true, an OpenSearch description file will be output, and all pages will
# contain a <link> tag referring to it.  The value of this option must be the
# base URL from which the finished HTML is served.
# html_use_opensearch = ''

# This is the file name suffix for HTML files (e.g. ".xhtml").
# html_file_suffix = None

# Language to be used for generating the HTML full-text search index.
# Sphinx supports the following languages:
#   'da', 'de', 'en', 'es', 'fi', 'fr', 'hu', 'it', 'ja'
#   'nl', 'no', 'pt', 'ro', 'ru', 'sv', 'tr'
# html_search_language = 'en'

# A dictionary with options for the search language support, empty by default.
# Now only 'ja' uses this config value
# html_search_options = {'type': 'default'}

# The name of a javascript file (relative to the configuration directory) that
# implements a search results scorer. If empty, the default will be used.
# html_search_scorer = 'scorer.js'

# Output file base name for HTML help builder.
htmlhelp_basename = __meta__.__name__

# -- Options for LaTeX output ---------------------------------------------

latex_elements = {
    # The paper size ('letterpaper' or 'a4paper').
    #'papersize': 'letterpaper',
    # The font size ('10pt', '11pt' or '12pt').
    #'pointsize': '10pt',
    # Additional stuff for the LaTeX preamble.
    #'preamble': '',
    # Latex figure (float) alignment
    #'figure_align': 'htbp',
}

# Grouping the document tree into LaTeX files. List of tuples
# (source start file, target name, title,
#  author, document class [howto, manual, or own class]).
latex_file = "{}.tex".format(__meta__.__name__)
latex_documents = [
    (master_doc, latex_file, master_title, __meta__.__author__, "manual"),
]

# The name of an image file (relative to this directory) to place at the top of
# the title page.
# latex_logo = None

# For "manual" documents, if this is true, then toplevel headings are parts,
# not chapters.
# latex_use_parts = False

# If true, show page references after internal links.
# latex_show_pagerefs = False

# If true, show URL addresses after external links.
# latex_show_urls = False

# Documents to append as an appendix to all manuals.
# latex_appendices = []

# If false, no module index is generated.
# latex_domain_indices = True


# -- Options for manual page output ---------------------------------------

# One entry per manual page. List of tuples
# (source start file, name, description, authors, manual section).
man_pages = [(master_doc, __meta__.__name__, master_title, [author], 1)]

# If true, show URL addresses after external links.
# man_show_urls = False


# -- Options for Texinfo output -------------------------------------------

# Grouping the document tree into Texinfo files. List of tuples
# (source start file, target name, title, author,
#  dir menu entry, description, category)
texinfo_documents = [
    (
        master_doc,
        __meta__.__name__,
        master_title,
        author,
        __meta__.__name__,
        __meta__.__description__,
        "Miscellaneous",
    )
]

# Documents to append as an appendix to all manuals.
# texinfo_appendices = []

# If false, no module index is generated.
# texinfo_domain_indices = True

# How to display URL addresses: 'footnote', 'no', or 'inline'.
# texinfo_show_urls = 'footnote'

# If true, do not generate a @detailmenu in the "Top" node's menu.
# texinfo_no_detailmenu = False


# Example configuration for intersphinx: refer to the Python standard library.
# intersphinx_mapping = {'https://docs.python.org/': None}
intersphinx_mapping = {
    "python": ("http://docs.python.org/", None),
    __meta__.__name__: ("{}/en/latest".format(__meta__.__documentation_url__), None),
}

# linkcheck options
# http://www.sphinx-doc.org/en/stable/config.html?highlight=linkchecker#options-for-the-linkcheck-builder
linkcheck_ignore = [
    # paths to local repository files directly referenced in doc (different root dir when built)
    # path links are handled by 'doc_redirect' extension
    r"../../../.*",
    r"./config.*",
    r"./docs.*",
    r"docs/source/.*",
    # inter-reference between document page and section headers
    # when link is itself a documentation reference, they are not resolved correctly, but this works with text replaces
    r":ref:`.*`",
    # dummy values
    r"http[s]*://localhost.*/",
    r"http[s]*://example.com.*",
    # ignore celery docs having problem (https://github.com/celery/celery/issues/7351), use 'docs.celeryq.dev' instead
    "https://docs.celeryproject.org/",
    "https://mouflon.dkrz.de/",
    # following have sporadic downtimes
    "https://esgf-data.dkrz.de/",
    "https://indico.egi.eu/",
    ".*docker-registry.crim.ca.*",  # protected
    # might not exist yet (we are generating it!)
    "https://pavics-weaver.readthedocs.io/en/latest/api.html",
    # ignore requires.io which just fails periodically - not critical link
    "https://requires.io/github/crim-ca/weaver/.*",
    "https://github.com/crim-ca/weaver/*",  # limit only our repo so others are still checked
    "https://service.crim.ca/.*",
    "https://ogc-ems.crim.ca/.*",
    "https://ogc-ades.crim.ca/.*",
    "https://ogc.crim.ca/.*",
]

linkcheck_timeout = 30
linkcheck_retries = 5

# known warning issues to be ignored
# https://www.sphinx-doc.org/en/master/usage/configuration.html#confval-nitpick_ignore
nitpicky = False
nitpick_ignore = [
    ("ref.term", "appstruct"),
    ("ref.term", "cstruct"),
]
nitpick_ignore_regex = [
    ("paramref", ".*")
]

# https://www.sphinx-doc.org/en/master/usage/configuration.html#confval-suppress_warnings
suppress_warnings = [
    "autosectionlabel.changes",
    "autosectionlabel.fixes",
    "autosectionlabel.module contents",
    "autosectionlabel.submodules",
    "autosectionlabel.response_subclassing_notes",
]

# ignore multiple known false-positives caused by autoapi generation
filter_warning_labels = [
    ("term", "appstruct"),
    ("term", "cstruct"),
    # for "undefined label: x"
    ("ref", "response_subclassing_notes"),
    ("ref", "package contents"),
    ("ref", "module contents"),
    ("ref", "submodules"),
]


# mute loggers that are not using any connector to allow evaluation before warning
# avoid getting flooded by false positive autosectionlabel warnings (which we can't fix anyway) to focus on real ones
troublesome_loggers = [
    "sphinx.domains.math",
    "sphinx.domains.std",
    "sphinx.ext.autosectionlabel",
    "sphinx.sphinx.ext.autosectionlabel"
]
for logger_name in troublesome_loggers:
    logger = logging.getLogger(logger_name)
    logger.setLevel(logging.ERROR)


def should_filter_warning(app, domain, node) -> bool:
    typ = node["reftype"]
    target = node["reftarget"]
    if (typ, target) in filter_warning_labels:
        return True  # skip
    return False


def filter_warnings_missing_reference(app, domain, node) -> bool:
    if should_filter_warning(app, domain, node):
        return True  # skip
    return warn_missing_reference(app, domain, node)


def setup(app):
    app.connect("warn-missing-reference", filter_warnings_missing_reference)
