import logging
import os
import sys
from typing import TYPE_CHECKING

# NOTE:
#   DO NOT IMPORT ANYTHING NOT PROVIDED BY PYTHON STANDARD LIBRARY HERE TO AVOID "setup.py" INSTALL FAILURE

logging.captureWarnings(True)
LOGGER = logging.getLogger(__name__)

WEAVER_MODULE_DIR = os.path.abspath(os.path.dirname(__file__))
WEAVER_ROOT_DIR = os.path.abspath(os.path.dirname(WEAVER_MODULE_DIR))
WEAVER_CONFIG_DIR = os.path.abspath(os.path.join(WEAVER_ROOT_DIR, "config"))
sys.path.insert(0, WEAVER_ROOT_DIR)
sys.path.insert(0, WEAVER_MODULE_DIR)

if TYPE_CHECKING:
    from typing import Any

    from pyramid.config import Configurator

    from weaver.typedefs import SettingsType


def main(global_config, **settings):
    # type: (SettingsType, Any) -> None
    import weaver.app
    # add flag to disable some unnecessary operations when runner is celery (worker)
    settings["weaver.celery"] = sys.argv[0].rsplit("/", 1)[-1] == "celery"
    return weaver.app.main(global_config, **settings)


def includeme(config):
    # type: (Configurator) -> None
    LOGGER.info("Adding Weaver")
    config.include("weaver.config")
    config.include("weaver.database")
    config.include("weaver.processes")
    config.include("weaver.vault")
    config.include("weaver.wps")
    config.include("weaver.wps_restapi")
    config.include("weaver.tweens")
    # must be after views includes,
    # otherwise can cause sporadic conflicts
    config.include("cornice")
    config.include("cornice_swagger")
    config.include("pyramid_beaker")
    config.include("pyramid_mako")
    config.include("pyramid_rewrite")
    # attempt finding a not found route using either an added or removed trailing slash according to situation
    config.add_rewrite_rule(r"/(?P<path>.*)/", r"/%(path)s")
