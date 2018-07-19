from pyramid.settings import asbool
from twitcher.wps_restapi.api import api_schema, api
from twitcher.wps_restapi.api import api
from twitcher.db import MongoDB
import logging
logger = logging.getLogger(__name__)


def includeme(config):
    settings = config.registry.settings

    if asbool(settings.get('twitcher.wps_restapi', True)):
        logger.info('Adding WPS REST API ...')
        config.include('cornice')
        config.include('cornice_swagger')
        config.include('twitcher.wps_restapi.providers')
        config.include('twitcher.wps_restapi.processes')
        config.include('twitcher.wps_restapi.jobs')
        config.add_route('wps_restapi_schema', '/__api__')
        config.add_route('wps_restapi', '/api')
        config.add_view(api_schema, route_name='wps_restapi_schema', request_method='GET', renderer='json')
        config.add_view(api, route_name='wps_restapi', request_method='GET')
        config.registry.celerydb = MongoDB.get(config.registry)
