from pyramid.settings import asbool
from pyramid.tweens import EXCVIEW

from twitcher.owsexceptions import (OWSException,
                                    OWSAccessForbidden,
                                    OWSNoApplicableCode,
                                    OWSMissingParameterValue,
                                    OWSInvalidParameterValue)
from twitcher.owsrequest import OWSRequest
from twitcher.tokens import TokenStore
from twitcher.db import mongodb
from twitcher.utils import path_elements

import logging
logger = logging.getLogger(__name__)

def includeme(config):
    settings = config.registry.settings

    if asbool(settings.get('twitcher.ows_security', True)):
        logger.info('Add OWS security tween')
        config.add_tween(OWS_SECURITY, under=EXCVIEW)


def ows_security_tween_factory(handler, registry):
    """A tween factory which produces a tween which raises an exception
    if access to OWS service is not allowed."""

    allowed_service_types = ('wps',)
    allowed_requests = ('getcapabilities', 'describeprocess')
    protected_path = '/ows/'
    
    tokenstore = TokenStore( mongodb(registry) )

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
            raise OWSAccessForbidden("You need to provide an access token to use this service.")
        return token
    
    def _validate_token(token):
        access_token = tokenstore.get_access_token(token)
        if access_token is None:
            raise OWSAccessForbidden("The access token is invalid.")
        if not access_token.is_valid():
            raise OWSAccessForbidden("The access token is invalid.")
        return access_token
    
    def ows_security_tween(request):
        try:
            if request.path.startswith(protected_path):
                ows_request = OWSRequest(request)
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
            return OWSNoApplicableCode(err.message)
        
    return ows_security_tween

OWS_SECURITY = 'twitcher.tweens.ows_security_tween_factory'
