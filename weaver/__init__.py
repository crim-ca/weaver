import logging
import os
import sys

# NOTE:
#   DO NOT IMPORT ANYTHING NOT PROVIDED BY PYTHON STANDARD LIBRARY HERE TO AVOID "setup.py" INSTALL FAILURE

logging.captureWarnings(True)
LOGGER = logging.getLogger(__name__)

WEAVER_MODULE_DIR = os.path.abspath(os.path.dirname(__file__))
WEAVER_ROOT_DIR = os.path.abspath(os.path.dirname(WEAVER_MODULE_DIR))
WEAVER_CONFIG_DIR = os.path.abspath(os.path.join(WEAVER_ROOT_DIR, "config"))
sys.path.insert(0, WEAVER_ROOT_DIR)
sys.path.insert(0, WEAVER_MODULE_DIR)

# provide standard package version location
from __meta__ import __version__  # noqa: E402 # isort:skip # pylint: disable=C0413


def main(global_config, **settings):
    import weaver.app
    return weaver.app.main(global_config, **settings)


def includeme(config):
    LOGGER.info("Adding Weaver Package")
    config.include("weaver.app")
