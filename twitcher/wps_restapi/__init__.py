from pyramid.settings import asbool
import logging
logger = logging.getLogger(__name__)


def includeme(config):
    settings = config.registry.settings

    if asbool(settings.get('twitcher.wps_restapi', True)):
        logger.info('Adding WPS REST API ...')
        config.include('wps_restapi.providers')
        config.include('wps_restapi.processes')
        config.include('wps_restapi.jobs')
