import os
import sys
from setuptools import setup, find_packages

CUR_DIR = os.path.abspath(os.path.dirname(__file__))
README = open(os.path.join(CUR_DIR, 'README.rst')).read()
CHANGES = open(os.path.join(CUR_DIR, 'CHANGES.rst')).read()

# ensure that 'twitcher' directory can be found for metadata import
sys.path.insert(0, CUR_DIR)
# don't use 'from' to avoid import errors on not yet installed packages
import twitcher.__meta__ as meta    # noqa E402

PY2 = sys.version_info[0] == 2
requirements = [line.strip() for line in open('requirements.txt')]
if PY2:
    requirements += [line.strip() for line in open('requirements-py2.txt')]

setup(name=meta.__name__,
      version=meta.__version__,
      description=meta.__description__,
      long_description=README + '\n\n' + CHANGES,
      classifiers=[
          "Programming Language :: Python",
          "Framework :: Pyramid",
          "Topic :: Internet :: WWW/HTTP",
          "Topic :: Internet :: WWW/HTTP :: WSGI :: Application",
          "Development Status :: 4 - Beta",
      ],
      author=', '.join(meta.__authors__),
      author_email=', '.join(meta.__emails__),
      url=meta.__source_repository__,
      download_url=meta.__docker_repository__,
      license=meta.__license__,
      keywords=' '.join(meta.__keywords__),
      packages=find_packages(),
      include_package_data=True,
      package_data={"": "*.mako"},
      zip_safe=False,
      test_suite='twitcher',
      install_requires=requirements,
      entry_points="""\
      [paste.app_factory]
      main = twitcher:main
      [console_scripts]
      twitcherctl=twitcher.twitcherctl:main
      """,
      )
