from twitcher.owsexceptions import OWSServiceNotAllowed
from twitcher.owsrequest import OWSRequest
from twitcher.tokens import TokenStorage
from twitcher.db import mongodb

import logging
logger = logging.getLogger(__name__)


def ows_security_tween_factory(handler, registry):
    """A :term:`tween` factory which produces a tween which raises an exception
    if access to OWS service is not allowed."""

    allowed_service_types = ('wps',)
    allowed_requests = ('getcapabilities', 'describeprocess',)
    
    tokenstore = TokenStorage( mongodb(registry) )
    
    def ows_security_tween(request):
        ows_request = OWSRequest(request)
        if 'ows' in request.path:
            if ows_request.service is None:
                raise OWSServiceNotAllowed()
            if not ows_request.service in allowed_service_types:
                raise OWSServiceNotAllowed()
            if not ows_request.request in allowed_requests:
                tokenstore.validate_access_token(request)
        return handler(request)
    return ows_security_tween

OWS_SECURITY = 'twitcher.tweens.ows_security_tween_factory'
