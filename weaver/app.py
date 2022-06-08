#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Weaver Web Application (``weaver-manager``).
"""

import logging
from typing import TYPE_CHECKING

import yaml
from pyramid.config import Configurator

from weaver.config import WEAVER_DEFAULT_REQUEST_OPTIONS_CONFIG, get_weaver_config_file, get_weaver_configuration
from weaver.database import get_db
from weaver.processes.builtin import register_builtin_processes
from weaver.processes.utils import register_cwl_processes_from_config, register_wps_processes_from_config
from weaver.utils import parse_extra_options, setup_cache, setup_loggers
from weaver.wps_restapi.patches import patch_pyramid_view_no_auto_head_get_method

if TYPE_CHECKING:
    from typing import Any

    from pyramid.router import Router

    from weaver.typedefs import SettingsType

LOGGER = logging.getLogger(__name__)


def main(global_config, **settings):
    # type: (SettingsType, **Any) -> Router
    """
    Creates a Pyramid WSGI application for Weaver.
    """
    setup_loggers(settings)
    LOGGER.info("Initiating weaver application")

    # validate and fix configuration
    weaver_config = get_weaver_configuration(settings)
    settings.update({"weaver.configuration": weaver_config})

    # Parse extra_options and add each of them in the settings dict
    LOGGER.info("Parsing extra options...")
    settings.update(parse_extra_options(settings.get("weaver.extra_options", "")))

    # load requests options if found, otherwise skip
    LOGGER.info("Checking for request options file...")
    req_file = get_weaver_config_file(settings.get("weaver.request_options", ""),
                                      WEAVER_DEFAULT_REQUEST_OPTIONS_CONFIG,
                                      generate_default_from_example=False)
    if req_file:
        LOGGER.info("Loading request options...")
        with open(req_file, mode="r", encoding="utf-8") as f:
            settings.update({"weaver.request_options": yaml.safe_load(f)})
    else:
        LOGGER.warning("No request options found.")

    # add default caching regions if they were omitted in config file
    if settings.get("weaver.celery", False):
        LOGGER.info("Celery runner detected. Skipping cache options setup.")
    else:
        LOGGER.info("Adding default caching options...")
        setup_cache(settings)

    LOGGER.info("Setup pyramid view configuration...")
    local_config = Configurator(settings=settings)
    patch_pyramid_view_no_auto_head_get_method(local_config)

    LOGGER.info("Setup celery configuration...")
    if global_config.get("__file__") is not None:
        local_config.include("pyramid_celery")
        local_config.configure_celery(global_config["__file__"])

    LOGGER.info("Setup Weaver...")
    local_config.include("weaver")

    LOGGER.info("Running database migration...")
    db = get_db(local_config)
    db.run_migration()

    if settings.get("weaver.celery", False):
        LOGGER.info("Celery runner detected. Skipping process registration.")
    else:
        LOGGER.info("Registering builtin processes...")
        register_builtin_processes(local_config)

        LOGGER.info("Registering WPS-1 processes from configuration file...")
        register_wps_processes_from_config(local_config)

        LOGGER.info("Registering CWL processes from configuration directory...")
        register_cwl_processes_from_config(local_config)

    return local_config.make_wsgi_app()
