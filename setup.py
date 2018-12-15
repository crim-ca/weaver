import os
import sys
from setuptools import setup, find_packages

# don't use 'from' to avoid import errors on not yet installed packages
import twitcher.__meta__ as meta

here = os.path.abspath(os.path.dirname(__file__))
README = open(os.path.join(here, 'README.rst')).read()
CHANGES = open(os.path.join(here, 'CHANGES.rst')).read()

PY2 = sys.version_info[0] == 2

reqs = [line.strip() for line in open('requirements.txt')]
if PY2:
    reqs += [line.strip() for line in open('requirements-py2.txt')]

setup(name='pyramid_twitcher',
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
      zip_safe=False,
      test_suite='twitcher',
      install_requires=reqs,
      entry_points="""\
      [paste.app_factory]
      main = twitcher:main
      [console_scripts]
      twitcherctl=twitcher.twitcherctl:main
      """,
      )
