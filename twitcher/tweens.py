from pyramid.settings import asbool

from twitcher.tokenstore import validate_token
from twitcher.exceptions import HTTPServiceNotAllowed

import logging
logger = logging.getLogger(__name__)


allowed_service_types = (
    'wps',
    )

    
allowed_requests = (
    'getcapabilities', 'describeprocess',
    )

    
def validate_ows_service(request):
    ows_service = None
    if 'service' in request.params:
        ows_service = request.params['service']
    elif 'SERVICE' in request.params:
        ows_service = request.params['SERVICE']

    if ows_service is None:
        raise HTTPServiceNotAllowed()

    if ows_service.lower() in allowed_service_types:
        ows_service = ows_service.lower()
    else:
        raise HTTPServiceNotAllowed()
    return ows_service


def validate_ows_request(request):
    ows_request = None
    if 'request' in request.params:
        ows_request = request.params['request']
    elif 'REQUEST' in request.params:
        ows_request = request.params['REQUEST']

    if not ows_request in allowed_requests:
        validate_token(request)
    return ows_request


def route_path_protected(request):
    try:
        route_path = request.current_route_path()
        # TODO: configure path which should be secured
        return 'owsproxy' in route_path
    except ValueError:
        return False

    
def ows_security_tween_factory(handler, registry):
    """ A :term:`tween` factory which produces a tween which raises an exception
    if access to OWS service is not allowed."""

    # check if tween is enabled
    #if asbool(registry.settings.get('do_ows_security')):
    if True:
        def ows_security_tween(request):
            if route_path_protected(request):
                validate_ows_service(request)
                validate_ows_request(request)
            response = handler(request)
            return response
        return ows_security_tween
        # if ows security tween is not enabled return original handler
    return handler

OWS_SECURITY = 'twitcher.tweens.ows_security_tween_factory'

