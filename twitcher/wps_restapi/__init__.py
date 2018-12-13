from pyramid.settings import asbool
from twitcher.wps_restapi.api import api_frontpage, api_swagger_json, api_swagger_ui, api_versions
from twitcher.database.base import get_database_factory
import logging
logger = logging.getLogger(__name__)


def includeme(config):
    from twitcher.wps_restapi import swagger_definitions as sd
    settings = config.registry.settings
    if asbool(settings.get('twitcher.wps_restapi', True)):
        logger.info('Adding WPS REST API ...')
        config.include('cornice')
        config.include('cornice_swagger')
        config.include('twitcher.wps_restapi.providers')
        config.include('twitcher.wps_restapi.processes')
        config.include('twitcher.wps_restapi.quotation')
        config.include('twitcher.wps_restapi.jobs')
        config.include('pyramid_mako')
        config.add_route(**sd.service_api_route_info(sd.api_frontpage_service, settings))
        config.add_route(**sd.service_api_route_info(sd.api_swagger_json_service, settings))
        config.add_route(**sd.service_api_route_info(sd.api_swagger_ui_service, settings))
        config.add_route(**sd.service_api_route_info(sd.api_versions_service, settings))
        config.add_view(api_frontpage, route_name=sd.api_frontpage_service.name,
                        request_method='GET', renderer='json')
        config.add_view(api_swagger_json, route_name=sd.api_swagger_json_service.name,
                        request_method='GET', renderer='json')
        config.add_view(api_swagger_ui, route_name=sd.api_swagger_ui_service.name,
                        request_method='GET', renderer='templates/swagger_ui.mako')
        config.add_view(api_versions, route_name=sd.api_versions_service.name,
                        request_method='GET', renderer='json')
        config.registry.celerydb = get_database_factory(config.registry)
