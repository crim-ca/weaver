from pyramid.settings import asbool
import logging
logger = logging.getLogger(__name__)



def includeme(config):
    settings = config.registry.settings

    if asbool(settings.get('twitcher.wps_restapi', True)):
        logger.info('Adding WPS REST API ...')
        config.include('twitcher.wps_restapi.providers')
        config.include('twitcher.wps_restapi.processes')
        config.include('twitcher.wps_restapi.jobs')
        config.add_route('wps_restapi', '/api')
