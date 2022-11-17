# pylint: disable=unused-import
try:
    from packaging.version import Version as LooseVersion  # noqa
except ImportError:
    from distutils.version import LooseVersion  # pylint: disable=deprecated-module
