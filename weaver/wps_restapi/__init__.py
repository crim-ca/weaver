import os.path

import logging
import uuid
from typing import TYPE_CHECKING

from pyramid.events import BeforeRender
from pyramid.response import Response
from pyramid.settings import asbool
from pyramid.static import QueryStringConstantCacheBuster

from weaver.utils import get_settings
from weaver.wps_restapi.utils import add_renderer_context, get_wps_restapi_base_path

if TYPE_CHECKING:
    from pyramid.config import Configurator

LOGGER = logging.getLogger(__name__)


def includeme(config):
    # type: (Configurator) -> None

    settings = get_settings(config)
    config.include("weaver.wps_restapi.api")  # only API informative endpoints
    if not asbool(settings.get("weaver.wps_restapi", True)):
        LOGGER.warning("Skipping WPS REST API views [weaver.wps_restapi=false].")
    else:
        LOGGER.info("Adding WPS REST API views...")
        api_base = get_wps_restapi_base_path(settings)
        with config.route_prefix_context(route_prefix=api_base):
            config.include("weaver.wps_restapi.jobs")
            config.include("weaver.wps_restapi.providers")
            config.include("weaver.wps_restapi.processes")
            config.include("weaver.wps_restapi.quotation")

    if not asbool(settings.get("weaver.wps_restapi_html", True)):
        LOGGER.warning("Skipping WPS REST API HTML views [weaver.wps_restapi_html=false].")
    else:
        LOGGER.info("Adding API HTML views resources...")
        config.add_static_view("static", "weaver.wps_restapi:templates/static/", cache_max_age=3600)
        config.add_cache_buster(
            "weaver.wps_restapi:templates/static/",
            QueryStringConstantCacheBuster(str(uuid.uuid4()))
        )
        config.add_subscriber(add_renderer_context, BeforeRender)

        ico_path = os.path.join(os.path.dirname(__file__), "templates/static/favicon.ico")
        with open(ico_path, mode="rb") as ico_file:
            icon = ico_file.read()
        icon_response = Response(content_type='image/x-icon', body=icon)
        config.add_route(name="favicon.ico", pattern="favicon.ico")
        config.add_view(lambda *_, **__: icon_response, route_name="favicon.ico")
