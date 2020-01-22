import os
import sys
from setuptools import setup, find_packages

CUR_DIR = os.path.abspath(os.path.dirname(__file__))
LONG_DESCRIPTION = None
if all(os.path.isfile(os.path.join(CUR_DIR, f)) for f in ["README.rst", "CHANGES.rst"]):
    README = open(os.path.join(CUR_DIR, "README.rst")).read()
    CHANGES = open(os.path.join(CUR_DIR, "CHANGES.rst")).read()
    LONG_DESCRIPTION = README + "\n\n" + CHANGES

# ensure that 'weaver' directory can be found for metadata import
sys.path.insert(0, CUR_DIR)
sys.path.insert(0, os.path.join(CUR_DIR, os.path.split(CUR_DIR)[-1]))
from weaver import __meta__  # noqa: E402

requirements = [line.strip() for line in open("requirements.txt")]

setup(name=__meta__.__name__,
      version=__meta__.__version__,
      description=__meta__.__description__,
      long_description=LONG_DESCRIPTION,
      classifiers=[
          "Natural Language :: English",
          "Programming Language :: Python :: 2.7",
          "Programming Language :: Python :: 3.5",
          "Programming Language :: Python :: 3.6",
          "Programming Language :: Python :: 3.7",
          "Programming Language :: Python :: 3.8",
          "Framework :: Pyramid",
          "Topic :: Internet :: WWW/HTTP",
          "Topic :: Internet :: WWW/HTTP :: WSGI :: Application",
          "Development Status :: 4 - Beta",
      ],
      author=", ".join(__meta__.__authors__),
      author_email=", ".join(__meta__.__emails__),
      url=__meta__.__source_repository__,
      download_url=__meta__.__docker_repository__,
      license=__meta__.__license__,
      keywords=" ".join(__meta__.__keywords__),
      packages=find_packages(),
      include_package_data=True,
      package_data={"": ["*.mako"]},
      zip_safe=False,
      test_suite="tests",
      python_requires=">=2.7, !=3.0.*, !=3.1.*, !=3.2.*, !=3.3.*, !=3.4.*, <4",
      install_requires=requirements,
      entry_points={
          "paste.app_factory": [
              "main = {}:main".format(__meta__.__name__)
          ]
      }
      )
