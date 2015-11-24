from pyramid.view import view_config

import logging
logger = logging.getLogger(__name__)

from registry import list_services


@view_config(route_name='frontpage', renderer='json')
def frontpage(request):
    services = list_services(request)
    return {'services': services}


def includeme(config):
    config.add_route('frontpage', '/')


    

   
