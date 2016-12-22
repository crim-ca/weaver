import functools

from pyramid.view import view_defaults
from pyramid_rpc.xmlrpc import xmlrpc_method
from pyramid.settings import asbool

from twitcher.registry import service_registry_factory
from twitcher.tokens import tokengenerator_factory
from twitcher.tokens import tokenstore_factory

import logging
logger = logging.getLogger(__name__)


# shortcut for xmlrpc_method
# api_xmlrpc = functools.partial(xmlrpc_method, endpoint="api")


@view_defaults(permission='view')
class RPCInterface(object):
    def __init__(self, request):
        self.request = request
        registry = self.request.registry
        self.tokengenerator = tokengenerator_factory(registry)
        self.tokenstore = tokenstore_factory(registry)
        self.registry = service_registry_factory(registry)

    # token management
    # ----------------

    def gentoken(self, valid_in_hours=1, user_environ=None):
        """
        Generates an access token which is valid for ``valid_in_hours``.

        Arguments:

        * ``valid_in_hours``: number of hours the token is valid.
        * ``user_environ``: environment used with this token (dict object).
        Possible keys: ``esgf_access_token``, ``esgf_slcs_service_url``.
        """
        access_token = self.tokengenerator.create_access_token(
            valid_in_hours=valid_in_hours,
            user_environ=user_environ,
        )
        self.tokenstore.save_token(access_token)
        return {
            'access_token': access_token.token,
            'expires_at': access_token.expires_at}

    def revoke(self, token):
        """
        Remove token from tokenstore.
        """
        self.tokenstore.delete_token(token)

    def clean(self):
        """
        Removes all tokens.
        """
        try:
            self.tokenstore.clean_tokens()
        except:
            logger.exception('clean tokens failed')
            return False
        else:
            return True

    # service registry
    # ----------------

    def register(self, url, name, service_type, public, c4i, overwrite):
        """
        Adds an OWS service with the given ``url`` to the registry.
        """
        service = self.registry.register_service(
            url=url, name=name, service_type=service_type,
            public=public,
            c4i=c4i,
            overwrite=overwrite)
        return service['name']

    def unregister(self, name):
        """
        Removes OWS service with the given ``name`` from the registry.
        """
        try:
            self.registry.unregister_service(name=name)
        except:
            logger.exception('unregister failed')
            return False
        else:
            return True

    def get_service_name(self, url):
        """
        Get service name for given ``url``.
        """
        try:
            name = self.registry.get_service_name(url=url)
        except:
            logger.exception('could not get service with url %s', url)
            return ''
        else:
            return name

    def get_service_by_name(self, name):
        """
        Get service for given ``name`` from registry database.
        """
        try:
            service = self.registry.get_service_by_name(name=name)
        except:
            logger.exception('could not get service with name %s', name)
            return {}
        else:
            return service

    def get_service_by_url(self, url):
        """
        Get service for given ``url`` from registry database.
        """
        try:
            service = self.registry.get_service_by_url(url=url)
        except:
            logger.exception('could not get service with url %s', url)
            return {}
        else:
            return service

    def is_public(self, name):
        return self.registry.is_public(name=name)

    def status(self):
        """
        Lists all registred OWS services.
        """
        try:
            services = self.registry.list_services()
            for service in services:
                service['proxy_url'] = self.request.route_url('owsproxy', service_name=service['name'])
            return services
        except:
            logger.exception('register failed')
            return []

    def clear_services(self):
        """
        Removes all services from the registry.
        """
        try:
            self.registry.clear_services()
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
        logger.debug('Add twitcher rpcinterface')

        # using basic auth
        config.include('twitcher.basicauth')

        # pyramid xml-rpc
        # http://docs.pylonsproject.org/projects/pyramid-rpc/en/latest/xmlrpc.html
        config.include('pyramid_rpc.xmlrpc')
        config.include('twitcher.db')
        config.add_xmlrpc_endpoint('api', '/RPC2')

        # register xmlrpc methods
        config.add_xmlrpc_method(RPCInterface, attr='gentoken', endpoint='api', method='gentoken')
        config.add_xmlrpc_method(RPCInterface, attr='revoke', endpoint='api', method='revoke')
        config.add_xmlrpc_method(RPCInterface, attr='clean', endpoint='api', method='clean')
        config.add_xmlrpc_method(RPCInterface, attr='register', endpoint='api', method='register')
        config.add_xmlrpc_method(RPCInterface, attr='unregister', endpoint='api', method='unregister')
        config.add_xmlrpc_method(RPCInterface, attr='is_public', endpoint='api', method='is_public')
        config.add_xmlrpc_method(RPCInterface, attr='get_service_name', endpoint='api', method='get_service_name')
        config.add_xmlrpc_method(RPCInterface, attr='get_service_by_name', endpoint='api', method='get_service_by_name')
        config.add_xmlrpc_method(RPCInterface, attr='get_service_by_url', endpoint='api', method='get_service_by_url')
        config.add_xmlrpc_method(RPCInterface, attr='purge', endpoint='api', method='purge')
        config.add_xmlrpc_method(RPCInterface, attr='status', endpoint='api', method='status')
