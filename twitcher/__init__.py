from pyramid.config import Configurator
from pyramid.authentication import BasicAuthAuthenticationPolicy
from pyramid.authorization import ACLAuthorizationPolicy
from pyramid.tweens import EXCVIEW

from twitcher.security import groupfinder, root_factory
from twitcher.tweens import OWS_SECURITY

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
    config.include('twitcher.frontpage')
    config.include('twitcher.rpcinterface')
    config.include('twitcher.owsproxy')
    config.include('twitcher.wps')
    
    # Security policies
    authn_policy = BasicAuthAuthenticationPolicy(check=groupfinder, realm="Birdhouse")
    authz_policy = ACLAuthorizationPolicy()
    config.set_authentication_policy(authn_policy)
    config.set_authorization_policy(authz_policy)

    # tweens/middleware
    config.add_tween(OWS_SECURITY, under=EXCVIEW)
   
    config.scan()

    return config.make_wsgi_app()

