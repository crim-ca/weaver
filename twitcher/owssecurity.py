from twitcher.tokens import validate_access_token
from twitcher.httpexceptions import OWSServiceNotAllowed

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
        raise OWSServiceNotAllowed()

    if ows_service.lower() in allowed_service_types:
        ows_service = ows_service.lower()
    else:
        raise OWSServiceNotAllowed()
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
        logger.debug('path %s', request.path)
        return 'owsproxy' in request.path or 'wps' in request.path
    except ValueError:
        logger.exception('route path check failed')
        return True

    
