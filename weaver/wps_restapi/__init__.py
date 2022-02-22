import logging
from typing import TYPE_CHECKING

from pyramid.settings import asbool

from weaver.formats import OutputFormat
from weaver.utils import get_settings

if TYPE_CHECKING:
    from pyramid.config import Configurator

LOGGER = logging.getLogger(__name__)


def includeme(config):
    # type: (Configurator) -> None

    from weaver.wps_restapi import api, swagger_definitions as sd
    settings = get_settings(config)

    config.add_route(**sd.service_api_route_info(sd.api_frontpage_service, settings))
    config.add_view(api.api_frontpage, route_name=sd.api_frontpage_service.name,
                    request_method="GET", renderer=OutputFormat.JSON)

    if asbool(settings.get("weaver.wps_restapi", True)):
        LOGGER.info("Adding WPS REST API...")
        config.registry.settings["handle_exceptions"] = False  # avoid cornice conflicting views
        config.include("weaver.wps_restapi.jobs")
        config.include("weaver.wps_restapi.providers")
        config.include("weaver.wps_restapi.processes")
        config.include("weaver.wps_restapi.quotation")
        config.add_forbidden_view(api.unauthorized_or_forbidden)
        config.add_notfound_view(api.not_found_or_method_not_allowed, append_slash=True)
        config.add_route(**sd.service_api_route_info(sd.openapi_json_service, settings))
        config.add_route(**sd.service_api_route_info(sd.api_openapi_ui_service, settings))
        config.add_route(**sd.service_api_route_info(sd.api_swagger_ui_service, settings))
        config.add_route(**sd.service_api_route_info(sd.api_redoc_ui_service, settings))
        config.add_route(**sd.service_api_route_info(sd.api_versions_service, settings))
        config.add_route(**sd.service_api_route_info(sd.api_conformance_service, settings))
        config.add_view(api.openapi_json, route_name=sd.openapi_json_service.name,
                        request_method="GET", renderer=OutputFormat.JSON)
        config.add_view(api.api_swagger_ui, route_name=sd.api_openapi_ui_service.name,
                        request_method="GET", renderer="templates/swagger_ui.mako")
        config.add_view(api.api_swagger_ui, route_name=sd.api_swagger_ui_service.name,
                        request_method="GET", renderer="templates/swagger_ui.mako")
        config.add_view(api.api_redoc_ui, route_name=sd.api_redoc_ui_service.name,
                        request_method="GET", renderer="templates/redoc_ui.mako")
        config.add_view(api.api_versions, route_name=sd.api_versions_service.name,
                        request_method="GET", renderer=OutputFormat.JSON)
        config.add_view(api.api_conformance, route_name=sd.api_conformance_service.name,
                        request_method="GET", renderer=OutputFormat.JSON)
