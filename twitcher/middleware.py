from webob import Request

from twitcher.owsexceptions import OWSException, OWSServiceNotAllowed
from twitcher.owsrequest import OWSRequest

import logging
logger = logging.getLogger(__name__)


allowed_service_types = (
    'wps',
    )

    
allowed_requests = (
    'getcapabilities', 'describeprocess',
    )


class OWSSecurityMiddleware(object):
    def __init__(self, app, tokenstore, **kwargs):
        self.app = app
        self.tokenstore = tokenstore


    def __call__(self, environ, start_response):
        self.request = Request(environ)
        self.ows_request = OWSRequest(self.request)
        if self.is_route_path_protected():
            try:
                self.validate_ows_service()
                self.validate_ows_request()
            except OWSException as e:
                return e(environ, start_response)
            except Exception,e:
                return [e]
        else:
            logger.warn('unprotected access')

        return self.app(environ, start_response)

    
    def is_route_path_protected(self):
        try:
            # TODO: configure path which should be secured
            logger.debug('path %s', self.request.path)
            return 'ows' in self.request.path
        except ValueError:
            logger.exception('route path check failed')
            return True

        
    def validate_ows_service(self):
        if self.ows_request.service is None:
            raise OWSServiceNotAllowed()

        if not self.ows_request.service in allowed_service_types:
            raise OWSServiceNotAllowed()


    def validate_ows_request(self):
        if not self.ows_request.request in allowed_requests:
           self.tokenstore.validate_access_token(self.request)


    

