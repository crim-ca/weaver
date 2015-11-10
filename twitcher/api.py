from pyramid.view import view_config, view_defaults
from pyramid_rpc.xmlrpc import xmlrpc_method

from twitcher import registry

import logging
logger = logging.getLogger(__name__)

@xmlrpc_method(endpoint='api')
def register(request, url):
    service = registry.register(request, url=url)
    return service['name']

    
@xmlrpc_method(endpoint='api')
def unregister(request, name):
    try:
        registry.unregister(request, name=name)
    except:
        logger.exception('unregister failed')
        return False
    else:
        return True

    
@xmlrpc_method(endpoint='api')
def list(request):
    try:
        services = registry.list(request)
        return services
    except:
        logger.exception('register failed')
        return []

    
@xmlrpc_method(endpoint='api')
def clear(request):
    try:
        registry.clear(request)
    except:
        logger.exception('clear failed')
        return False
    else:
        return True
    
