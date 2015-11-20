from webob import Request

from twitcher.owssecurity import validate

import logging
logger = logging.getLogger(__name__)

class OWSSecurityMiddleware(object):
    def __init__(self, app, **kwargs):
        self.app = app
        #config = config or {}

    def __call__(self, environ, start_response):
        request = Request(environ)
        logger.debug("request = %s", request)
        logger.debug('path_info=%s, path=%s, query=%s', request.path_info, request.path, request.query_string)
        logger.debug("request params = %s", request.params)
        validate(request)
        return self.app(environ, start_response)
