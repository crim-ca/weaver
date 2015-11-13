from webob import Request

import logging
logger = logging.getLogger(__name__)

class OWSSecurityMiddleware(object):
    def __init__(self, app, **kwargs):
        """Initialize the Dummy Middleware"""
        self.app = app
        #config = config or {}

    def __call__(self, environ, start_response):
        request = Request(environ)
        logger.debug("request = %s", request)
        return self.app(environ, start_response)
