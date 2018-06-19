from pyramid.view import view_defaults
from pyramid_rpc.xmlrpc import xmlrpc_method
from pyramid.settings import asbool

from twitcher.api import ITokenManager, TokenManager
from twitcher.api import IRegistry, Registry
from twitcher.tokengenerator import tokengenerator_factory
from twitcher.store import tokenstore_factory
from twitcher.store import servicestore_factory

import logging
LOGGER = logging.getLogger("TWITCHER")


@view_defaults(permission='view', require_csrf=False)
class RPCInterface(ITokenManager, IRegistry):
    def __init__(self, request):
        self.request = request
        self.tokenmgr = TokenManager(
            tokengenerator_factory(request.registry),
            tokenstore_factory(request.registry))
        self.srvreg = Registry(servicestore_factory(request.registry))

    def generate_token(self, valid_in_hours=1, environ=None):
        """
        Implementation of :meth:`twitcher.api.ITokenManager.generate_token`.
        """
        return self.tokenmgr.generate_token(valid_in_hours, environ)

    def revoke_token(self, token):
        """
        Implementation of :meth:`twitcher.api.ITokenManager.revoke_token`.
        """
        return self.tokenmgr.revoke_token(token)

    def revoke_all_tokens(self):
        """
        Implementation of :meth:`twitcher.api.ITokenManager.revoke_all_tokens`.
        """
        return self.tokenmgr.revoke_all_tokens()

    def register_service(self, url, data=None, overwrite=True):
        """
        Implementation of :meth:`twitcher.api.IRegistry.register_service`.
        """
        return self.srvreg.register_service(url, data, overwrite)

    def unregister_service(self, name):
        """
        Implementation of :meth:`twitcher.api.IRegistry.unregister_service`.
        """
        return self.srvreg.unregister_service(name)

    def get_service_by_name(self, name):
        """
        Implementation of :meth:`twitcher.api.IRegistry.get_service_by_name`.
        """
        return self.srvreg.get_service_by_name(name)

    def get_service_by_url(self, url):
        """
        Implementation of :meth:`twitcher.api.IRegistry.get_service_by_url`.
        """
        return self.srvreg.get_service_by_url(url)

    def list_services(self):
        """
        Implementation of :meth:`twitcher.api.IRegistry.list_services`.
        """
        return self.srvreg.list_services()

    def clear_services(self):
        """
        Implementation of :meth:`twitcher.api.IRegistry.clear_services`.
        """
        return self.srvreg.clear_services()


def includeme(config):
    """ The callable makes it possible to include rpcinterface
    in a Pyramid application.

    Calling ``config.include(twitcher.rpcinterface)`` will result in this
    callable being called.

    Arguments:

    * ``config``: the ``pyramid.config.Configurator`` object.
    """
    settings = config.registry.settings

    if asbool(settings.get('twitcher.rpcinterface', True)):
        LOGGER.debug('Twitcher XML-RPC Interface enabled.')

        # include twitcher config
        config.include('twitcher.config')

        # using basic auth
        config.include('twitcher.basicauth')

        # pyramid xml-rpc
        # http://docs.pylonsproject.org/projects/pyramid-rpc/en/latest/xmlrpc.html
        config.include('pyramid_rpc.xmlrpc')
        config.include('twitcher.db')
        config.add_xmlrpc_endpoint('api', '/RPC2')

        # register xmlrpc methods
        config.add_xmlrpc_method(RPCInterface, attr='generate_token', endpoint='api', method='generate_token')
        config.add_xmlrpc_method(RPCInterface, attr='revoke_token', endpoint='api', method='revoke_token')
        config.add_xmlrpc_method(RPCInterface, attr='revoke_all_tokens', endpoint='api', method='revoke_all_tokens')
        config.add_xmlrpc_method(RPCInterface, attr='register_service', endpoint='api', method='register_service')
        config.add_xmlrpc_method(RPCInterface, attr='unregister_service', endpoint='api', method='unregister_service')
        config.add_xmlrpc_method(RPCInterface, attr='get_service_by_name', endpoint='api', method='get_service_by_name')
        config.add_xmlrpc_method(RPCInterface, attr='get_service_by_url', endpoint='api', method='get_service_by_url')
        config.add_xmlrpc_method(RPCInterface, attr='clear_services', endpoint='api', method='clear_services')
        config.add_xmlrpc_method(RPCInterface, attr='list_services', endpoint='api', method='list_services')
