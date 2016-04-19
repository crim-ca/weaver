import os
from setuptools import setup, find_packages

here = os.path.abspath(os.path.dirname(__file__))
README = open(os.path.join(here, 'README.rst')).read()
CHANGES = open(os.path.join(here, 'CHANGES.rst')).read()

reqs = [line.strip() for line in open('requirements/deploy.txt')]
test_reqs = [line.strip() for line in open('requirements/tests.txt')]

setup(name='birdhouse-twitcher',
      version='0.1.1',
      description='Security Proxy for Web Processing Services (WPS)',
      long_description=README + '\n\n' + CHANGES,
      classifiers=[
        "Programming Language :: Python",
        "Framework :: Pyramid",
        "Topic :: Internet :: WWW/HTTP",
        "Topic :: Internet :: WWW/HTTP :: WSGI :: Application",
        "Development Status :: 4 - Beta",
        ],
      author='Birdhouse Developers',
      author_email='',
      url='https://github.com/bird-house/twitcher.git',
      license='Apache License 2.0',
      keywords='buildout pyramid birdhouse wps pywps esgf security proxy ows ogc',
      packages=find_packages(),
      include_package_data=True,
      zip_safe=False,
      test_suite='twitcher',
      install_requires=reqs,
      test_require=test_reqs,
      entry_points="""\
      [paste.app_factory]
      main = twitcher:main
      [console_scripts]
      twitcherctl=twitcher.twitcherctl:main
      """,
      )
