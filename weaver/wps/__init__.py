#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Views for WPS-XML endpoint implemented with :mod:`pywps`.
"""
import logging

from pyramid.settings import asbool

from weaver.utils import get_settings
from weaver.wps.utils import get_wps_path
from weaver.wps.views import pywps_view


def includeme(config):
    settings = get_settings(config)
    logger = logging.getLogger(__name__)
    if not asbool(settings.get("weaver.wps", True)):
        logger.debug("Weaver WPS disable. WPS-XML endpoint will not be available.")
    else:
        logger.debug("Weaver WPS enabled. Adding WPS-XML view.")
        wps_path = get_wps_path(settings)
        config.add_route("wps", wps_path)
        config.add_view(pywps_view, route_name="wps")
