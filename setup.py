import os
import sys
from setuptools import setup, find_packages

CUR_DIR = os.path.abspath(os.path.dirname(__file__))
LONG_DESCRIPTION = None
if all(os.path.isfile(os.path.join(CUR_DIR, f)) for f in ['README.rst', 'CHANGES.rst']):
    README = open(os.path.join(CUR_DIR, 'README.rst')).read()
    CHANGES = open(os.path.join(CUR_DIR, 'CHANGES.rst')).read()
    LONG_DESCRIPTION = README + '\n\n' + CHANGES

# ensure that 'weaver' directory can be found for metadata import
sys.path.insert(0, CUR_DIR)
sys.path.insert(0, os.path.join(CUR_DIR, 'weaver'))
# don't use 'from' to avoid import errors on not yet installed packages
import __meta__  # noqa E402

PY2 = sys.version_info[0] == 2
requirements = [line.strip() for line in open('requirements.txt')]
if PY2:
    requirements += [line.strip() for line in open('requirements-py2.txt')]

setup(name=__meta__.__name__,
      version=__meta__.__version__,
      description=__meta__.__description__,
      long_description=LONG_DESCRIPTION,
      classifiers=[
          "Programming Language :: Python",
          "Framework :: Pyramid",
          "Topic :: Internet :: WWW/HTTP",
          "Topic :: Internet :: WWW/HTTP :: WSGI :: Application",
          "Development Status :: 4 - Beta",
      ],
      author=', '.join(__meta__.__authors__),
      author_email=', '.join(__meta__.__emails__),
      url=__meta__.__source_repository__,
      download_url=__meta__.__docker_repository__,
      license=__meta__.__license__,
      keywords=' '.join(__meta__.__keywords__),
      packages=find_packages(),
      include_package_data=True,
      package_data={"": "*.mako"},
      zip_safe=False,
      test_suite='weaver',
      install_requires=requirements,
      entry_points="""\
      [paste.app_factory]
      main = weaver:main
      """,
      )
