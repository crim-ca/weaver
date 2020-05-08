import logging
import os
import sys

from distutils.version import LooseVersion
from setuptools import find_packages, setup
from typing import Iterable, Set, Tuple, Union

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

LOGGER = logging.getLogger("weaver.setup")


def _split_requirement(requirement, version=False, python=False):
    # type: (str, bool, bool) -> Union[str, Tuple[str, str]]
    """
    Splits a requirement package definition into it's name and version specification.

    Returns the appropriate part(s) according to :paramref:`version`. If ``True``, returns the operator and version
    string. The returned version in this case would be either the package's or the environment python's version string
    according to the value of :paramref:`python`. Otherwise, only returns the 'other part' of the requirement, which
    will be the plain package name without version or the complete ``package+version`` without ``python_version`` part.

    Package requirement format::

        package [<|<=|==|>|>=|!= x.y.z][; python_version <|<=|==|>|>=|!= "x.y.z"]

    :param requirement: full package string requirement.
    :param version: retrieve version operator and version instead of package's name.
    :param python: retrieve python operator and version instead of the package's version.
    :return: extracted requirement part(s).
    """
    idx_pkg = -1 if version else 0
    idx_pyv = -1 if python else 0
    if python and "python_version" not in requirement:
        return ("", "") if version else ""
    requirement = requirement.split("python_version")[idx_pyv].replace(";", "").replace("\"", "")
    op_str = ""
    for operator in [">=", ">", "<=", "<", "!=", "==", "="]:
        if operator in requirement:
            op_str = operator
            requirement = requirement.split(operator)[idx_pkg]
            break
    return requirement.strip() if not version else (op_str.strip(), requirement.strip())


def _parse_requirements(file_path, requirements, links):
    # type: (str, Set[str], Set[str]) -> None
    """
    Parses a requirements file to extra packages and links.

    If a python version specific is present, requirements are added only if they match the current environment.

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
            if "python_version" in line:
                operator, py_ver = _split_requirement(line, version=True, python=True)
                op_map = {
                    "==": LooseVersion(sys.version) == LooseVersion(py_ver),
                    ">=": LooseVersion(sys.version) >= LooseVersion(py_ver),
                    "<=": LooseVersion(sys.version) <= LooseVersion(py_ver),
                    "!=": LooseVersion(sys.version) != LooseVersion(py_ver),
                    ">": LooseVersion(sys.version) > LooseVersion(py_ver),
                    "<": LooseVersion(sys.version) < LooseVersion(py_ver),
                }
                if not op_map[operator]:
                    continue
                line = _split_requirement(line)  # remove the python part
            if "git+https" in line:
                pkg = line.split("#")[-1]
                links.add(line.strip())
                requirements.add(pkg.replace("egg=", "").rstrip())
            elif line.startswith("http"):
                links.add(line.strip())
            else:
                requirements.add(line.strip())


def _extra_requirements(base_requirements, other_requirements):
    # type: (Iterable[str], Iterable[str]) -> Set[str]
    """
    Extracts only the extra requirements not already defined within the base requirements.

    :param base_requirements: base package requirements.
    :param other_requirements: other set of requirements referring to additional dependencies.
    """
    raw_requirements = set()
    for req in base_requirements:
        raw_req = _split_requirement(req)
        raw_requirements.add(raw_req)
    filtered_requirements = set()
    for req in other_requirements:
        raw_req = _split_requirement(req)
        if raw_req and raw_req not in raw_requirements:
            filtered_requirements.add(req)
    return filtered_requirements


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
DOCS_REQUIREMENTS = list(_extra_requirements(REQUIREMENTS, DOCS_REQUIREMENTS))
TEST_REQUIREMENTS = list(_extra_requirements(REQUIREMENTS, TEST_REQUIREMENTS))

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
      install_requires=requirements,
      dependency_links=[
          "git+https://github.com/ESGF/esgf-compute-api.git@v2.1.0#egg=esgf_compute_api"
      ],
      entry_points={
          "paste.app_factory": [
              "main = {}:main".format(__meta__.__name__)
          ]
      }
      )
