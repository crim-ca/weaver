from pyramid.view import view_config, view_defaults
from pyramid_rpc.xmlrpc import xmlrpc_method

from twitcher import registry

import logging
logger = logging.getLogger(__name__)

@view_defaults(permission='view')
class RpcInterface(object):
    def __init__(self, request):
        self.request = request
        self.session = self.request.session

        
    @xmlrpc_method(endpoint='api')
    def register(self, url, identifier):
        registry.register(self.request, url=url, identifier=identifier)
        return 'register %s done' % url
       

    @xmlrpc_method(endpoint='api')
    def unregister(self, identifier):
        registry.unregister(self.request, identifier=idenfitier)
        return 'remove service %s done' % identifier

    
    @xmlrpc_method(endpoint='api')
    def list(self):
        services = registry.list(self.request)
        return 'list services %s done' % services

    
    @xmlrpc_method(endpoint='api')
    def clear(self):
        registry.clear(self.request)
        return 'clear services done'
