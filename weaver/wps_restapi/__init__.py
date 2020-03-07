import logging

from pyramid.settings import asbool

from weaver.formats import OUTPUT_FORMAT_JSON

LOGGER = logging.getLogger(__name__)


def includeme(config):
    from weaver.wps_restapi import api, swagger_definitions as sd

    settings = config.registry.settings
    if asbool(settings.get("weaver.wps_restapi", True)):
        LOGGER.info("Adding WPS REST API...")
        config.registry.settings["handle_exceptions"] = False  # avoid cornice conflicting views
        config.include("weaver.wps_restapi.jobs")
        config.include("weaver.wps_restapi.providers")
        config.include("weaver.wps_restapi.processes")
        config.include("weaver.wps_restapi.quotation")
        config.add_route(**sd.service_api_route_info(sd.api_frontpage_service, settings))
        config.add_route(**sd.service_api_route_info(sd.api_swagger_json_service, settings))
        config.add_route(**sd.service_api_route_info(sd.api_swagger_ui_service, settings))
        config.add_route(**sd.service_api_route_info(sd.api_versions_service, settings))
        config.add_route(**sd.service_api_route_info(sd.api_conformance_service, settings))
        config.add_view(api.api_frontpage, route_name=sd.api_frontpage_service.name,
                        request_method="GET", renderer=OUTPUT_FORMAT_JSON)
        config.add_view(api.api_swagger_json, route_name=sd.api_swagger_json_service.name,
                        request_method="GET", renderer=OUTPUT_FORMAT_JSON)
        config.add_view(api.api_swagger_ui, route_name=sd.api_swagger_ui_service.name,
                        request_method="GET", renderer="templates/swagger_ui.mako")
        config.add_view(api.api_versions, route_name=sd.api_versions_service.name,
                        request_method="GET", renderer=OUTPUT_FORMAT_JSON)
        config.add_view(api.api_conformance, route_name=sd.api_conformance_service.name,
                        request_method="GET", renderer=OUTPUT_FORMAT_JSON)
