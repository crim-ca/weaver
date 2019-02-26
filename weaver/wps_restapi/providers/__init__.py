from weaver.wps_restapi import swagger_definitions as sd
from weaver.wps_restapi.providers import providers as p
import logging
logger = logging.getLogger('weaver')


def includeme(config):
    logger.info('Adding WPS REST API providers ...')
    settings = config.registry.settings
    config.add_route(**sd.service_api_route_info(sd.providers_service, settings))
    config.add_route(**sd.service_api_route_info(sd.provider_service, settings))
    config.add_view(p.get_providers, route_name=sd.providers_service.name, request_method='GET', renderer='json')
    config.add_view(p.add_provider, route_name=sd.providers_service.name, request_method='POST', renderer='json')
    config.add_view(p.get_provider, route_name=sd.provider_service.name, request_method='GET', renderer='json')
    config.add_view(p.remove_provider, route_name=sd.provider_service.name, request_method='DELETE', renderer='json')
