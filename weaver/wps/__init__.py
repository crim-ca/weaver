#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Views for WPS-XML endpoint implemented with :mod:`pywps`.
"""
import logging
from typing import TYPE_CHECKING

from pyramid.settings import asbool

from weaver.utils import get_settings

if TYPE_CHECKING:
    from pyramid.config import Configurator

LOGGER = logging.getLogger(__name__)


def includeme(config):
    # type: (Configurator) -> None
    settings = get_settings(config)
    if not asbool(settings.get("weaver.wps", True)):
        LOGGER.warning("Skipping Weaver WPS views [weaver.wps=false]. WPS KVP/XML endpoint will not be available.")
    else:
        LOGGER.info("Adding Weaver WPS application.")
        config.include("weaver.wps.app")
