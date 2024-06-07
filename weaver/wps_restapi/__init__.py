import os.path

import logging
import uuid
from typing import TYPE_CHECKING

from pyramid.events import BeforeRender
from pyramid.response import Response
from pyramid.settings import asbool
from pyramid.static import QueryStringConstantCacheBuster

from weaver.formats import ContentType
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
            config.include("weaver.wps_restapi.providers")
            config.include("weaver.wps_restapi.processes")
            # Note:
            #   Important to add quotation and jobs last since providers/processes-prefixed
            #   routes for execution are defined in their respective modules.
            #   If not done this way, route/views get created before all cornice decorators could be found.
            config.include("weaver.wps_restapi.quotation")
            config.include("weaver.wps_restapi.jobs")

        # Note:
        #   Following definitions avoids WPS XML -> REST JSON redirects to default to the HTML renderer.
        #   By default, Pyramid prioritized HTML-based headers.
        #   (see https://docs.pylonsproject.org/projects/pyramid/en/latest/narr/viewconfig.html#default-accept-ordering)
        config.add_accept_view_order(
            ContentType.APP_JSON,
            weighs_more_than=ContentType.TEXT_HTML,
        )
        config.add_accept_view_order(
            ContentType.TEXT_HTML,
            weighs_more_than=ContentType.TEXT_XML,
        )
        config.add_accept_view_order(
            ContentType.TEXT_XML,
            weighs_more_than=ContentType.APP_XML,
        )

    if not asbool(settings.get("weaver.wps_restapi_html", True)):
        LOGGER.warning("Skipping WPS REST API HTML views [weaver.wps_restapi_html=false].")
    elif asbool(settings.get("weaver.wps_restapi", True)) is False:
        LOGGER.error("Cannot use HTML views without REST API view [weaver.wps_restapi=false].")
        raise RuntimeError("Cannot use HTML views without REST API views.")
    else:
        LOGGER.info("Adding API HTML views resources...")
        config.add_static_view("static", "weaver.wps_restapi:templates/static/", cache_max_age=3600)
        config.add_cache_buster(
            "weaver.wps_restapi:templates/static/",
            QueryStringConstantCacheBuster(str(uuid.uuid4()))
        )
        config.add_subscriber(add_renderer_context, BeforeRender)

        icon_path = os.path.join(os.path.dirname(__file__), "templates/static/favicon.ico")
        with open(icon_path, mode="rb") as ico_file:
            icon = ico_file.read()
        icon_response = Response(content_type="image/x-icon", body=icon)
        config.add_route(name="icon", pattern="favicon.ico")
        config.add_view(lambda *_, **__: icon_response, route_name="icon")

        logo_path = os.path.join(os.path.dirname(__file__), "templates/static/crim.png")
        with open(logo_path, mode="rb") as logo_file:
            logo = logo_file.read()
        logo_response = Response(content_type="image/png", body=logo)
        config.add_route(name="logo", pattern="crim.png")
        config.add_view(lambda *_, **__: logo_response, route_name="logo")
