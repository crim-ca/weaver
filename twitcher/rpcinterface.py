from pyramid.view import view_config, view_defaults
from pyramid_rpc.xmlrpc import xmlrpc_method

from twitcher import registry, tokenstore

import logging
logger = logging.getLogger(__name__)

# token management

@xmlrpc_method(endpoint='api')
def createToken(request):
    token = tokenstore.create_token(request)
    return token['identifier']

# service registry

@xmlrpc_method(endpoint='api')
def addService(request, url):
    service = registry.add_service(request, url=url)
    return service['name']

    
@xmlrpc_method(endpoint='api')
def removeService(request, name):
    try:
        registry.remove_service(request, name=name)
    except:
        logger.exception('unregister failed')
        return False
    else:
        return True

    
@xmlrpc_method(endpoint='api')
def listServices(request):
    try:
        services = registry.list_services(request)
        return services
    except:
        logger.exception('register failed')
        return []

    
@xmlrpc_method(endpoint='api')
def clearServices(request):
    try:
        registry.clear_service(request)
    except:
        logger.exception('clear failed')
        return False
    else:
        return True
    
