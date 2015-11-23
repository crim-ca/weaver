from pyramid.authentication import BasicAuthAuthenticationPolicy
from pyramid.authorization import ACLAuthorizationPolicy

from twitcher.config import Configurator
from twitcher.security import groupfinder, root_factory
from twitcher.db import mongodb
from twitcher.tokens import TokenStorage
from twitcher.middleware import OWSSecurityMiddleware

import logging
logger = logging.getLogger(__name__)

def main(global_config, **settings):
    """
    This function returns a Pyramid WSGI application.
    """
    config = Configurator(settings=settings, root_factory=root_factory)

    # beaker session
    config.include('pyramid_beaker')

    # include twitcher components
    config.include('twitcher.rpcinterface')
    config.include('twitcher.owsproxy')
    config.include('twitcher.wps')
    
    # Security policies
    authn_policy = BasicAuthAuthenticationPolicy(check=groupfinder, realm="Birdhouse")
    authz_policy = ACLAuthorizationPolicy()
    config.set_authentication_policy(authn_policy)
    config.set_authorization_policy(authz_policy)

    # routes 
    config.add_route('home', '/')

    # middleware
    config.add_wsgi_middleware(
        OWSSecurityMiddleware,
        tokenstore=TokenStorage(mongodb(config.registry)))
    
    config.scan()

    return config.make_wsgi_app()

