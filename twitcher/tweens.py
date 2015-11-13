from pyramid.settings import asbool

from twitcher.tokens import validate_access_token
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
        validate_access_token(request)
    return ows_request


def is_route_path_protected(request):
    try:
        # TODO: configure path which should be secured
        logger.debug('route path %s', request.path_info)
        return 'owsproxy' in request.path_info
    except ValueError:
        logger.exception('route path check failed')
        return True

    
def ows_security_tween_factory(handler, registry):
    """ A :term:`tween` factory which produces a tween which raises an exception
    if access to OWS service is not allowed."""

    def ows_security_tween(request):
        if is_route_path_protected(request):
            validate_ows_service(request)
            validate_ows_request(request)
        else:
            logger.warn('unprotected access')
        return handler(request)
    return ows_security_tween

OWS_SECURITY = 'twitcher.tweens.ows_security_tween_factory'

