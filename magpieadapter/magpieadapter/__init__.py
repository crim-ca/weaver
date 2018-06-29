import logging
import os
import sys

# TODO Is the following block really useful?
this_dir = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, this_dir)


from twitcher.adapter.base import AdapterInterface
from twitcher.owsproxy import owsproxy
from magpieadapter.magpieservice import MagpieServiceStore
from magpieadapter.magpieowssecurity import MagpieOWSSecurity


logger = logging.getLogger(__name__)


__version__ = '0.1.0'


class MagpieAdapter(AdapterInterface):

    def servicestore_factory(self, registry, database=None, headers=None):
        return MagpieServiceStore(registry=registry, headers=headers)

    def owssecurity_factory(self, registry):
        # TODO For magpie we cannot store the servicestore object since the constructor need a header with token
        # taken from the request... maybe we should check for that?!?
        #return MagpieOWSSecurity(tokenstore_factory(registry), servicestore_factory(registry))
        return MagpieOWSSecurity()

    def configurator_factory(self, settings):
        from pyramid.config import Configurator
        from pyramid.authentication import AuthTktAuthenticationPolicy
        from pyramid.authorization import ACLAuthorizationPolicy

        from magpie.models import group_finder

        magpie_secret = settings['magpie.secret']

        # Disable rpcinterface which is conflicting with postgres db
        settings['twitcher.rpcinterface'] = False

        authn_policy = AuthTktAuthenticationPolicy(
            magpie_secret,
            callback=group_finder,
        )
        authz_policy = ACLAuthorizationPolicy()

        config = Configurator(
            settings=settings,
            authentication_policy=authn_policy,
            authorization_policy=authz_policy
        )

        from magpie.models import get_user
        config.set_request_property(get_user, 'user', reify=True)
        return config

    def owsproxy_config(self, settings, config):
        protected_path = settings.get('twitcher.ows_proxy_protected_path', '/ows')

        config.add_route('owsproxy', protected_path + '/{service_name}')
        config.add_route('owsproxy_extra', protected_path + '/{service_name}/{extra_path:.*}')
        config.add_route('owsproxy_secured', protected_path + '/{service_name}/{access_token}')

        # include postgresdb
        config.include('magpieadapter.postgresdb')

        config.add_view(owsproxy, route_name='owsproxy')
        config.add_view(owsproxy, route_name='owsproxy_extra')
        config.add_view(owsproxy, route_name='owsproxy_secured')
