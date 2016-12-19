import os
from setuptools import setup, find_packages

version = __import__('twitcher').__version__

here = os.path.abspath(os.path.dirname(__file__))
README = open(os.path.join(here, 'README.rst')).read()
CHANGES = open(os.path.join(here, 'CHANGES.rst')).read()

reqs = [line.strip() for line in open('requirements/deploy.txt')]

setup(name='pyramid_twitcher',
      version=version,
      description='Security Proxy for OGC Services like WPS.',
      long_description=README + '\n\n' + CHANGES,
      classifiers=[
          "Programming Language :: Python",
          "Framework :: Pyramid",
          "Topic :: Internet :: WWW/HTTP",
          "Topic :: Internet :: WWW/HTTP :: WSGI :: Application",
          "Development Status :: 4 - Beta",
      ],
      author='Birdhouse Developers',
      author_email='wps-dev@lists.dkrz.de',
      url='https://github.com/bird-house/twitcher.git',
      license='Apache License 2.0',
      keywords='buildout pyramid twitcher birdhouse wps pywps security proxy ows ogc',
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
