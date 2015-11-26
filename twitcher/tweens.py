from twitcher.owsexceptions import (OWSException,
                                    OWSAccessForbidden,
                                    OWSMissingParameterValue,
                                    OWSInvalidParameterValue)
from twitcher.owsrequest import OWSRequest
from twitcher.tokens import TokenStorage
from twitcher.db import mongodb
from twitcher.utils import path_elements

import logging
logger = logging.getLogger(__name__)


def ows_security_tween_factory(handler, registry):
    """A :term:`tween` factory which produces a tween which raises an exception
    if access to OWS service is not allowed."""

    allowed_service_types = ('wps',)
    allowed_requests = ('getcapabilities', 'describeprocess')
    protected_path = '/ows/'
    
    tokenstore = TokenStorage( mongodb(registry) )

    def _get_token(request):
        token = None
        if 'access_token' in request.params:
            token = request.params['access_token']   # in params
        elif 'Access-Token' in request.headers:
            token = request.headers['Access-Token']  # in header
        else:  # in path
            elements = path_elements(request.path)
            if len(elements) > 1: # there is always /ows/
                token = elements[-1]   # last path element

        if token is None:
            raise OWSAccessForbidden("no access token provided")
        return token
    
    def _validate_token(token):
        access_token = tokenstore.get_access_token(token)
        if access_token is None:
            raise OWSAccessForbidden("You need to provide an access token to use this service")
        if not access_token.is_valid():
            raise OWSAccessForbidden("The access token is invalid")
        return access_token
    
    def ows_security_tween(request):
        try:
            ows_request = OWSRequest(request)
            if request.path.startswith(protected_path):
                if not ows_request.service in allowed_service_types:
                    raise OWSInvalidParameterValue(
                        "service %s not supported" % ows_request.service, value="service")
                if not ows_request.request in allowed_requests:
                    token = _get_token(request)
                    access_token = _validate_token(token)
                    # update request with user environ from access token
                    request.environ.update( access_token.user_environ )
            return handler(request)
        except OWSException as err:
            logger.exception("security check failed.")
            return err
        except Exception as err:
            logger.exception("unknown error")
            return OWSAccessForbidden(err.message)
        
    return ows_security_tween

OWS_SECURITY = 'twitcher.tweens.ows_security_tween_factory'
