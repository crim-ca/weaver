from pyramid.httpexceptions import HTTPUnauthorized
from pyramid.security import forget
from pyramid.view import forbidden_view_config
from pyramid.view import view_config
from pyramid.response import Response

import logging
logger = logging.getLogger(__name__)

from registry import list_services


@view_config(route_name='frontpage', renderer='json', permission='view')
def frontpage(request):
    services = list_services(request)
    return {'services': services}


@forbidden_view_config()
def basic_challenge(request):
    response = HTTPUnauthorized()
    response.headers.update(forget(request))
    return response


@view_config(context=Exception)
def unknown_failure(request, exc):
    import traceback
    logger.exception('unknown failure')
    #msg = exc.args[0] if exc.args else ""
    response =  Response('Ooops, something went wrong: %s' % (traceback.format_exc()))
    #response =  Response('Ooops, something went wrong. Check the log files.')
    response.status_int = 500
    return response


def includeme(config):
    config.add_route('frontpage', '/')


    

   
