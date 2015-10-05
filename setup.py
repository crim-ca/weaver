import os
from setuptools import setup, find_packages

here = os.path.abspath(os.path.dirname(__file__))
README = open(os.path.join(here, 'README.rst')).read()
CHANGES = open(os.path.join(here, 'CHANGES.rst')).read()

requires = [
    'pyramid>=1.5.7',
    'pyramid_beaker',
    'beaker_mongodb',
    'pymongo',
    'papyrus_ogcproxy'
    ]

setup(name='pywpsproxy',
      version='0.1.0',
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
      url='https://github.com/bird-house/pywps-proxy.git',
      license='Apache License 2.0',
      keywords='buildout pyramids birdhouse wps pywps esgf security proxy ows ogc',
      packages=find_packages(),
      include_package_data=True,
      zip_safe=False,
      test_suite='pywpsproxy',
      install_requires=requires,
      entry_points="""\
      [paste.app_factory]
      main = pywpsproxy:main
      """,
      )
