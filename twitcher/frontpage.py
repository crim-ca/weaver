from pyramid.view import view_config

import logging
logger = logging.getLogger(__name__)

from twitcher.registry import registry_factory


@view_config(route_name='frontpage', renderer='json')
def frontpage(request):
    registry = registry_factory(request)
    services = registry.list_services()
    return {'services': services}


def includeme(config):
    config.add_route('frontpage', '/')


    

   
