from pyramid.view import view_config, view_defaults
from pyramid_rpc.xmlrpc import xmlrpc_method

import logging
logger = logging.getLogger(__name__)

@view_defaults(permission='view')
class RpcInterface(object):
    def __init__(self, request):
        self.request = request
        self.session = self.request.session

        
    @xmlrpc_method(endpoint='api')
    def addService(self, url, identifier):
        return 'add service done'
       

    @xmlrpc_method(endpoint='api')
    def removeService(self, identifier):
        return 'remove service %s done' % identifier

    
    @xmlrpc_method(endpoint='api')
    def listServices(self):
        return 'list services done'

    
    @xmlrpc_method(endpoint='api')
    def clearServices(self):
        return 'clear services done'
