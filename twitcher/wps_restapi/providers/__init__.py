import logging
logger = logging.getLogger(__name__)

from twitcher.wps_restapi.providers.providers import get_providers, add_provider, get_capabilities, remove_provider


def includeme(config):
    config.add_route('providers', '/providers')
    config.add_route('provider', '/providers/{provider_id}')
    config.add_view(get_providers, route_name='providers', request_method='GET', renderer='json')
    config.add_view(add_provider, route_name='providers', request_method='POST', renderer='json')
    config.add_view(get_capabilities, route_name='provider', request_method='GET', renderer='json')
    config.add_view(remove_provider, route_name='provider', request_method='DELETE', renderer='json')
