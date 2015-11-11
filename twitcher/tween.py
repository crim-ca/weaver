from pyramid.settings import asbool
import logging

logger = logging.getLogger(__name__)


class TokenSecurityTween(object):
    def __init__(self, handler, registry):
        self.handler = handler
        self.registry = registry

    def __call__(self, request):
        try:
            response = self.handler(request)
        finally:
            logger.debug('handler = %s', self.handler)
        return response


