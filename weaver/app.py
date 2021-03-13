#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Weaver Web Application (``weaver-manager``).
"""

import logging

import yaml
from pyramid.config import Configurator

from weaver.config import WEAVER_DEFAULT_REQUEST_OPTIONS_CONFIG, get_weaver_config_file, get_weaver_configuration
from weaver.processes.builtin import register_builtin_processes
from weaver.processes.utils import register_wps_processes_from_config
from weaver.utils import get_settings, parse_extra_options, setup_cache, setup_loggers

LOGGER = logging.getLogger(__name__)


def main(global_config, **settings):
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
        with open(req_file, "r") as f:
            settings.update({"weaver.request_options": yaml.safe_load(f)})
    else:
        LOGGER.warning("No request options found.")

    # add default caching regions if they were omitted in config file
    LOGGER.info("Adding default caching options...")
    setup_cache(settings)

    LOGGER.info("Setup celery configuration...")
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
