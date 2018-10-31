from pyramid.settings import asbool
from twitcher.wps_restapi import swagger_definitions as sd
from twitcher.wps_restapi.api import api_frontpage, api_swagger_json, api_swagger_ui, api_versions
from twitcher.adapter import jobstore_factory
import logging
logger = logging.getLogger(__name__)

"""
this script will include what's necessary for twitcher to act as a rest api over providers, processes and jobs
currently however, voluntarily or not,
it would be possible to include directly the providers, processes or jobs independently
we'll first try to keep that behaviour, but this is a nice to keep
"""
# create the store from either memory or mongodb
#   get twitcher store type from environment or configuration
#   ideally environment, as there should be no need to change configuration file to run tests
#   instantiate the store, inject it into test twitcher app (why does it need to be a "test" app?)
# inject it into job, processes and providers services
# register routes to views


def includeme(config):
    """
    called from twitcher config.include
    :param config:
    :return:
    """
    settings = config.registry.settings
    if asbool(settings.get('twitcher.wps_restapi', True)):
        logger.info('Adding WPS REST API ...')
        config.include('cornice')
        config.include('cornice_swagger')
        config.include('twitcher.wps_restapi.providers')
        config.include('twitcher.wps_restapi.processes')
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
        config.registry.celerydb = jobstore_factory(config.registry)


def instantiate_restapi(store):
    """
    for now, we must keep the handlers as functions and not instance methods
    as such, we will return a dict with the three services
    :param store:
    :return:
    """
    pass
