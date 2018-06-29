import os
from setuptools import setup, find_packages

version = __import__('magpieadapter').__version__

here = os.path.abspath(os.path.dirname(__file__))
README = open(os.path.join(here, 'README.rst')).read()
CHANGES = open(os.path.join(here, 'CHANGES.rst')).read()

reqs = [line.strip() for line in open('requirements.txt')]

setup(name='magpieadapter',
      version=version,
      description='Twitcher adapter using Magpie as services providers and for AuthN/AuthZ.',
      long_description=README + '\n\n' + CHANGES,
      classifiers=[
          "Programming Language :: Python",
          "Topic :: Internet :: WWW/HTTP",
          "Topic :: Internet :: WWW/HTTP :: WSGI :: Application",
          "Development Status :: 4 - Beta",
      ],
      author='David Byrns (CRIM)',
      author_email='david.byrns@crim.ca',
      url='https://ouranosinc.github.io/pavics-sdi/index.html',
      license='Apache License 2.0',
      keywords='buildout pyramid twitcher magpie birdhouse wps pywps security proxy ows ogc',
      packages=find_packages(),
      include_package_data=True,
      zip_safe=False,
      test_suite='magpieadapter',
      install_requires=reqs,
      )
