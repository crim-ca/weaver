import functools

from pyramid.view import view_config, view_defaults
from pyramid_rpc.xmlrpc import xmlrpc_method

from twitcher import registry, tokens

import logging
logger = logging.getLogger(__name__)


# shortcut for xmlrpc_method
api_xmlrpc = functools.partial(xmlrpc_method, endpoint="api")


# token management

@api_xmlrpc
def generateToken(request):
    access_token = tokens.generate_access_token(request)
    return access_token.access_token


# service registry

@api_xmlrpc()
def addService(request, url):
    service = registry.add_service(request, url=url)
    return service['name']

    
@api_xmlrpc()
def removeService(request, name):
    try:
        registry.remove_service(request, service_name=name)
    except:
        logger.exception('unregister failed')
        return False
    else:
        return True

    
@api_xmlrpc()
def listServices(request):
    try:
        services = registry.list_services(request)
        return services
    except:
        logger.exception('register failed')
        return []

    
@api_xmlrpc()
def clearServices(request):
    try:
        registry.clear_service(request)
    except:
        logger.exception('clear failed')
        return False
    else:
        return True
    
