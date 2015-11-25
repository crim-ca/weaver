from twitcher.owsexceptions import OWSException, OWSForbidden
from twitcher.owsrequest import OWSRequest
from twitcher.tokens import TokenStorage
from twitcher.db import mongodb

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
            if len(path_elements) > 1: # there is always /ows/
                token = path_elements[-1]   # last path element

        if token is None:
            raise OWSForbidden() # no access token provided
        return token
    
    def _validate_token(token):
        access_token = tokenstore.get_access_token(token)
        if access_token is None:
            raise OWSForbidden() # no access token in store
        if not access_token.is_valid():
            raise OWSForbidden() # access token not valid
        return access_token
    
    def ows_security_tween(request):
        try:
            ows_request = OWSRequest(request)
            if request.path.startswith(protected_path):
                if ows_request.service is None:
                    raise OWSForbidden() # service parameter is missing
                if not ows_request.service in allowed_service_types:
                    raise OWSForbidden() # service not supported
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
            return OWSForbidden()
        
    return ows_security_tween

OWS_SECURITY = 'twitcher.tweens.ows_security_tween_factory'
