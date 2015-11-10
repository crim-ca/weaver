import time
from pyramid.settings import asbool
import logging

logger = logging.getLogger(__name__)

def timing_tween_factory(handler, registry):
    #if asbool(registry.settings.get('do_timing')):
    if True:
        # if timing support is enabled, return a wrapper
        def timing_tween(request):
            start = time.time()
            try:
                response = handler(request)
            finally:
                end = time.time()
                logger.debug('handler = %s', handler)
                logger.debug('The request took %s seconds' %
                            (end - start))
            return response
        return timing_tween
    # if timing support is not enabled, return the original
    # handler
    return handler


def dummy_tween_factory(handler, registry):
    #if asbool(registry.settings.get('do_timing')):
    if True:
        def dummy_tween(request):
            try:
                response = handler(request)
            finally:
                logger.debug('handler = %s', handler)
            return response
        return dummy_tween
    # if timing support is not enabled, return the original
    # handler
    return handler
