import functools

from pyramid.view import view_defaults
from pyramid_rpc.xmlrpc import xmlrpc_method
from pyramid.settings import asbool

from twitcher.registry import registry_factory
from twitcher.tokens import TokenStorage

import logging
logger = logging.getLogger(__name__)


# shortcut for xmlrpc_method
api_xmlrpc = functools.partial(xmlrpc_method, endpoint="api")


@view_defaults(permission='admin')
class RPCInterface(object):
    def __init__(self, request):
        self.request = request
        self.tokenstore = TokenStorage(self.request.db)
        self.registry = registry_factory(self.request)

    # token management

    @api_xmlrpc()
    def generate_token(self, user_environ=None):
        """
        Generates an access token. Stores the optional ``user_environ`` dict with the token.
        """
        access_token = self.tokenstore.create_access_token(user_environ=user_environ)
        return access_token.access_token

    
    @api_xmlrpc()
    def clear_tokens(self):
        """
        Removes all tokens.
        """
        try:
            self.tokenstore.clear()
        except:
            logger.exception('clear tokens failed')
            return False
        else:
            return True
            

    # service registry

    @api_xmlrpc()
    def add_service(self, url, name=None):
        """
        Adds an OWS service with the given ``url`` to the registry.
        """
        service = self.registry.add_service(url=url, service_name=name)
        return service['name']


    @api_xmlrpc()
    def remove_service(self, name):
        """
        Removes OWS service with the given ``name`` from the registry.
        """
        try:
            self.registry.remove_service(service_name=name)
        except:
            logger.exception('unregister failed')
            return False
        else:
            return True



    @api_xmlrpc()
    def list_services(self):
        """
        Lists all registred OWS services.
        """
        try:
            services = self.registry.list_services()
            return services
        except:
            logger.exception('register failed')
            return []


    @api_xmlrpc()
    def clear_services(self):
        """
        Removes all services from the registry.
        """
        try:
            self.registry.clear_service()
        except:
            logger.exception('clear failed')
            return False
        else:
            return True

def includeme(config):
    """ The callable makes it possible to include rpcinterface
    in a Pyramid application.

    Calling ``config.include(twitcher.rpcinterface)`` will result in this
    callable being called.

    Arguments:

    * ``config``: the ``pyramid.config.Configurator`` object.
    """
    settings = config.registry.settings

    if asbool(settings.get('twitcher.rpcinferface', True)):
        logger.info('Add twitcher rpcinterface')

        # using basic auth
        config.include('twitcher.basicauth')
    
        # pyramid xml-rpc
        # http://docs.pylonsproject.org/projects/pyramid-rpc/en/latest/xmlrpc.html
        config.include('pyramid_rpc.xmlrpc')
        config.include('twitcher.db')
        config.add_xmlrpc_endpoint('api', '/RPC2')

