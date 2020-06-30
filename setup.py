import logging
import os
import sys
from typing import Set

from setuptools import find_packages, setup

CUR_DIR = os.path.abspath(os.path.dirname(__file__))
LONG_DESCRIPTION = None
if all(os.path.isfile(os.path.join(CUR_DIR, f)) for f in ["README.rst", "CHANGES.rst"]):
    README = open(os.path.join(CUR_DIR, "README.rst")).read()
    CHANGES = open(os.path.join(CUR_DIR, "CHANGES.rst")).read()
    LONG_DESCRIPTION = README + "\n\n" + CHANGES

# ensure that 'weaver' directory can be found for metadata import
sys.path.insert(0, CUR_DIR)
sys.path.insert(0, os.path.join(CUR_DIR, os.path.split(CUR_DIR)[-1]))
# pylint: disable=C0413,wrong-import-order
from weaver import __meta__  # isort:skip # noqa: E402

LOGGER = logging.getLogger("{}.setup".format(__meta__.__name__))
if logging.StreamHandler not in LOGGER.handlers:
    LOGGER.addHandler(logging.StreamHandler(sys.stdout))  # type: ignore # noqa
LOGGER.setLevel(logging.INFO)
LOGGER.info("starting setup")

with open("README.rst") as readme_file:
    README = readme_file.read()

with open("CHANGES.rst") as changes_file:
    CHANGES = changes_file.read().replace(".. :changelog:", "")


def _parse_requirements(file_path, requirements, links):
    # type: (str, Set[str], Set[str]) -> None
    """
    Parses a requirements file to extra packages and links.

    :param file_path: file path to the requirements file.
    :param requirements: pre-initialized set in which to store extracted package requirements.
    :param links: pre-initialized set in which to store extracted link reference requirements.
    :returns: None
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
_parse_requirements("requirements-docs.txt", DOCS_REQUIREMENTS, LINKS)
_parse_requirements("requirements-dev.txt", TEST_REQUIREMENTS, LINKS)
LINKS = list(LINKS)
REQUIREMENTS = list(REQUIREMENTS)

LOGGER.info("base requirements: %s", REQUIREMENTS)
LOGGER.info("docs requirements: %s", DOCS_REQUIREMENTS)
LOGGER.info("test requirements: %s", TEST_REQUIREMENTS)
LOGGER.info("link requirements: %s", LINKS)

setup(name=__meta__.__name__,
      version=__meta__.__version__,
      description=__meta__.__description__,
      long_description=LONG_DESCRIPTION,
      long_description_content_type="text/x-rst",
      classifiers=[
          "Natural Language :: English",
          "Programming Language :: Python",
          "Programming Language :: Python :: 3",
          "Programming Language :: Python :: 3.6",
          "Programming Language :: Python :: 3.7",
          "Programming Language :: Python :: 3.8",
          "Framework :: Pyramid",
          "Topic :: Internet :: WWW/HTTP",
          "Topic :: Internet :: WWW/HTTP :: WSGI :: Application",
          "Topic :: Scientific/Engineering :: GIS",
          "Development Status :: 4 - Beta",
      ],
      author=__meta__.__author__,
      author_email=", ".join(__meta__.__emails__),
      url=__meta__.__source_repository__,
      download_url=__meta__.__docker_repository__,
      license=__meta__.__license_type__,
      keywords=" ".join(__meta__.__keywords__),
      packages=find_packages(),
      include_package_data=True,
      package_data={"": ["*.mako"]},
      zip_safe=False,
      test_suite="tests",
      python_requires=">=3.0.*, !=3.1.*, !=3.2.*, !=3.3.*, !=3.4.*, !=3.5.*, <4",
      install_requires=REQUIREMENTS,
      dependency_links=LINKS,
      extras_require={
          "docs": DOCS_REQUIREMENTS,
          "dev": TEST_REQUIREMENTS,
          "test": TEST_REQUIREMENTS,
      },
      entry_points={
          "paste.app_factory": [
              "main = {}:main".format(__meta__.__name__)
          ]
      }
      )
