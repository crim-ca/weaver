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
    
    def ows_security_tween(request):
        try:
            ows_request = OWSRequest(request)
            if request.path.startswith(protected_path):
                if ows_request.service is None:
                    raise OWSForbidden() # service parameter is missing
                if not ows_request.service in allowed_service_types:
                    raise OWSForbidden() # service not supported
                if not ows_request.request in allowed_requests:
                    access_token = tokenstore.validate_access_token(request)
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
