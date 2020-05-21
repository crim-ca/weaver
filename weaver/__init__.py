import logging
import os
import sys
import yaml

logging.captureWarnings(True)
LOGGER = logging.getLogger("weaver")

WEAVER_MODULE_DIR = os.path.abspath(os.path.dirname(__file__))
WEAVER_ROOT_DIR = os.path.abspath(os.path.dirname(WEAVER_MODULE_DIR))
WEAVER_CONFIG_DIR = os.path.abspath(os.path.join(WEAVER_ROOT_DIR, "config"))
sys.path.insert(0, WEAVER_ROOT_DIR)
sys.path.insert(0, WEAVER_MODULE_DIR)

# provide standard package version location
from __meta__ import __version__  # isort:skip # noqa: E402 # pylint: disable=C0413

# ===============================================================================================
#   DO NOT IMPORT ANYTHING NOT PROVIDED BY BASE PYTHON HERE TO AVOID "setup.py" INSTALL FAILURE
# ===============================================================================================


def includeme(config):
    LOGGER.info("Adding weaver...")
    config.include("weaver.config")
    config.include("weaver.database")
    config.include("weaver.wps")
    config.include("weaver.wps_restapi")
    config.include("weaver.processes")
    config.include("weaver.tweens")


def main(global_config, **settings):
    """
    Creates a Pyramid WSGI application for Weaver.
    """
    LOGGER.info("Initiating weaver application")

    from weaver.config import WEAVER_DEFAULT_REQUEST_OPTIONS_CONFIG, get_weaver_configuration, get_weaver_config_file
    from weaver.processes.builtin import register_builtin_processes
    from weaver.processes.utils import register_wps_processes_from_config
    from weaver.utils import parse_extra_options, get_settings
    from pyramid.config import Configurator

    # validate and fix configuration
    weaver_config = get_weaver_configuration(settings)
    settings.update({"weaver.configuration": weaver_config})

    # Parse extra_options and add each of them in the settings dict
    settings.update(parse_extra_options(settings.get("weaver.extra_options", "")))

    # load requests options
    req_file = get_weaver_config_file(settings.get("weaver.request_options", ""), WEAVER_DEFAULT_REQUEST_OPTIONS_CONFIG)
    with open(req_file, "r") as f:
        settings.update({"weaver.request_options": yaml.safe_load(f)})

    local_config = Configurator(settings=settings)
    if global_config.get("__file__") is not None:
        local_config.include("pyramid_celery")
        local_config.configure_celery(global_config["__file__"])
    local_config.include("weaver")

    LOGGER.info("Registering builtin processes...")
    register_builtin_processes(local_config)

    LOGGER.info("Registering WPS-1 processes from configuration file...")
    wps_processes_file = get_settings(local_config).get("weaver.wps_processes_file")
    register_wps_processes_from_config(wps_processes_file, local_config)

    return local_config.make_wsgi_app()
