#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Weaver Web Application (``weaver-manager``).
"""

import logging

import yaml
from pyramid.config import Configurator
from pyramid_beaker import set_cache_regions_from_settings

from weaver.config import WEAVER_DEFAULT_REQUEST_OPTIONS_CONFIG, get_weaver_config_file, get_weaver_configuration
from weaver.processes.builtin import register_builtin_processes
from weaver.processes.utils import register_wps_processes_from_config
from weaver.utils import get_settings, parse_extra_options

LOGGER = logging.getLogger(__name__)


def includeme(config):
    LOGGER.info("Adding Web Application")
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

    # validate and fix configuration
    weaver_config = get_weaver_configuration(settings)
    settings.update({"weaver.configuration": weaver_config})

    # Parse extra_options and add each of them in the settings dict
    LOGGER.info("Parsing extra options...")
    settings.update(parse_extra_options(settings.get("weaver.extra_options", "")))

    # load requests options
    LOGGER.info("Loading request options...")
    req_file = get_weaver_config_file(settings.get("weaver.request_options", ""), WEAVER_DEFAULT_REQUEST_OPTIONS_CONFIG)
    with open(req_file, "r") as f:
        settings.update({"weaver.request_options": yaml.safe_load(f)})

    # add default caching regions if they were omitted in config file
    LOGGER.info("Adding default caching options...")
    settings.setdefault("cache.regions", "doc, result")
    settings.setdefault("cache.type", "memory")
    settings.setdefault("cache.doc.enable", "false")
    settings.setdefault("cache.result.enable", "false")
    set_cache_regions_from_settings(settings)

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
