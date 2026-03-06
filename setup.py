import logging
import os
import sys
from typing import Set

from setuptools import find_packages, setup

CUR_DIR = os.path.abspath(os.path.dirname(__file__))
LONG_DESCRIPTION = None
if all(os.path.isfile(os.path.join(CUR_DIR, f)) for f in ["README.rst", "CHANGES.rst"]):
    with open(os.path.join(CUR_DIR, "README.rst"), mode="r", encoding="utf-8") as readme_f:
        README = readme_f.read()
    with open(os.path.join(CUR_DIR, "CHANGES.rst"), mode="r", encoding="utf-8") as changes_f:
        CHANGES = changes_f.read()
    LONG_DESCRIPTION = f"{README}\n\n{CHANGES}"

    # remove RST contents that are not permitted within PyPI distributions
    # any contents between '.. remove-pypi-[start|end]' comments will be removed
    DOC_REMOVE_PYPI = str(os.getenv("DOC_REMOVE_PYPI", False)).lower() == "true"
    while DOC_REMOVE_PYPI:
        DOC_REMOVE_PYPI_START = LONG_DESCRIPTION.find(".. remove-pypi-start")
        DOC_REMOVE_PYPI_END = LONG_DESCRIPTION.find(".. remove-pypi-end")
        if (
            DOC_REMOVE_PYPI_START > 0 and  # noqa
            DOC_REMOVE_PYPI_END > 0 and
            DOC_REMOVE_PYPI_START < DOC_REMOVE_PYPI_END
        ):
            DOC_REMOVE_PYPI_END += len(".. remove-pypi-end")
            LONG_DESCRIPTION = LONG_DESCRIPTION[:DOC_REMOVE_PYPI_START] + LONG_DESCRIPTION[DOC_REMOVE_PYPI_END:]
        else:
            DOC_REMOVE_PYPI = False
            break

# ensure that 'weaver' directory can be found for metadata import
sys.path.insert(0, CUR_DIR)
sys.path.insert(0, os.path.join(CUR_DIR, os.path.split(CUR_DIR)[-1]))
# pylint: disable=C0413,wrong-import-order
from weaver import __meta__  # isort:skip # noqa: E402

# pylint: disable=C0209,consider-using-f-string

LOGGER = logging.getLogger(f"{__meta__.__name__}.setup")
if logging.StreamHandler not in LOGGER.handlers:
    LOGGER.addHandler(logging.StreamHandler(sys.stdout))  # type: ignore # noqa
LOGGER.setLevel(logging.INFO)
LOGGER.info("starting setup")


def _parse_requirements(file_path, requirements, links):
    # type: (str, Set[str], Set[str]) -> None
    """
    Parses a requirements file to extra packages and links.

    :param file_path: file path to the requirements file.
    :param requirements: pre-initialized set in which to store extracted package requirements.
    :param links: pre-initialized set in which to store extracted link reference requirements.
    """
    with open(file_path, "r") as requirements_file:
        for line in requirements_file:
            # ignore empty line, comment line or reference to other requirements file (-r flag)
            if not line or line.startswith("#") or line.startswith("-"):
                continue
            if "git+https" in line:
                pkg = line.split("#")[-1]
                links.add(line.strip())
                requirements.add(pkg.replace("egg=", "").rstrip())
            elif line.startswith("http"):
                links.add(line.strip())
            else:
                requirements.add(line.strip())


LOGGER.info("reading requirements")
# See https://github.com/pypa/pip/issues/3610
# use set to have unique packages by name
LINKS = set()
REQUIREMENTS = set()
DOCS_REQUIREMENTS = set()
TEST_REQUIREMENTS = set()
_parse_requirements("requirements.txt", REQUIREMENTS, LINKS)
_parse_requirements("requirements-doc.txt", DOCS_REQUIREMENTS, LINKS)
_parse_requirements("requirements-dev.txt", TEST_REQUIREMENTS, LINKS)
LINKS = list(LINKS)
REQUIREMENTS = list(REQUIREMENTS)

LOGGER.info("base requirements: %s", REQUIREMENTS)
LOGGER.info("docs requirements: %s", DOCS_REQUIREMENTS)
LOGGER.info("test requirements: %s", TEST_REQUIREMENTS)
LOGGER.info("link requirements: %s", LINKS)

setup(
    name=__meta__.__package__,
    version=__meta__.__version__,
    provides=[__meta__.__name__],  # ensure that the package distribution alias maps to the importable package name
    py_modules=[__meta__.__name__],
    description=__meta__.__description__,
    long_description=LONG_DESCRIPTION,
    long_description_content_type="text/x-rst",
    classifiers=[
        "Development Status :: 4 - Beta",
        "Environment :: Web Environment",
        "Framework :: Celery",
        "Framework :: Paste",
        "Framework :: Pyramid",
        "Intended Audience :: Developers",
        "Intended Audience :: Information Technology",
        "Intended Audience :: Science/Research",
        __meta__.__license_classifier__,
        "Natural Language :: English",
        "Operating System :: POSIX",
        "Programming Language :: Python",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
        "Programming Language :: Python :: 3 :: Only",
        "Topic :: Internet :: WWW/HTTP",
        "Topic :: Internet :: WWW/HTTP :: Dynamic Content",
        "Topic :: Internet :: WWW/HTTP :: WSGI :: Application",
        "Topic :: Scientific/Engineering :: Atmospheric Science",
        "Topic :: Scientific/Engineering :: GIS",
        "Topic :: Scientific/Engineering :: Interface Engine/Protocol Translator",
        "Topic :: System :: Distributed Computing",
    ],
    author=__meta__.__author__,
    author_email=", ".join(__meta__.__emails__),
    url=__meta__.__source_repository__,
    download_url=__meta__.__docker_repository__,
    license=__meta__.__license_type__,
    license_files=["LICENSE.txt"],
    keywords=" ".join(__meta__.__keywords__),
    packages=find_packages(exclude=["tests*"]),
    package_dir={
        __meta__.__name__: "weaver",
        __meta__.__package__: "weaver",
    },
    package_data={
        "": ["*.mako"],
        "weaver": ["*"],
    },
    include_package_data=True,
    zip_safe=False,
    python_requires=">=3.10, <4",
    install_requires=REQUIREMENTS,
    dependency_links=LINKS,
    extras_require={
        "docs": DOCS_REQUIREMENTS,
        "dev": TEST_REQUIREMENTS,
        "test": TEST_REQUIREMENTS,
    },
    entry_points={
        "paste.app_factory": [
            f"main = {__meta__.__name__}:main"
        ],
        "console_scripts": [
            "{0} = {0}.cli:main".format(__meta__.__name__)
        ]
    }
)
