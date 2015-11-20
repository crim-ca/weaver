from twitcher.tokens import validate_access_token
from twitcher.owsexceptions import OWSServiceNotAllowed
from twitcher.owsrequest import OWSRequest

import logging
logger = logging.getLogger(__name__)


allowed_service_types = (
    'wps',
    )

    
allowed_requests = (
    'getcapabilities', 'describeprocess',
    )


def validate(request):
    validator = OWSSecurity(request)
    validator.validate()

        
class OWSSecurity(object):
    def __init__(self, request):
        self.request = OWSRequest(request)


    def validate(self):
        if self.is_route_path_protected():
            self.validate_ows_service()
            self.validate_ows_request()
        else:
            logger.warn('unprotected access')
                
    def validate_ows_service(self):
        if self.request.ows_service is None:
            raise OWSServiceNotAllowed()

        if not self.request.ows_service in allowed_service_types:
            raise OWSServiceNotAllowed()


    def validate_ows_request(self):
        if not self.request.ows_request in allowed_requests:
            validate_access_token(self.request.wrapped)


    def is_route_path_protected(self):
        try:
            # TODO: configure path which should be secured
            logger.debug('path %s', self.request.wrapped.path)
            return 'ows' in self.request.wrapped.path
        except ValueError:
            logger.exception('route path check failed')
            return True

    
