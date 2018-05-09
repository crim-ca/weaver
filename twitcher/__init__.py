import logging
logger = logging.getLogger(__name__)

# -- Pyramid ----


# -- Ziggurat_foundation ----

#import sys
#sys.path.insert(0, '/home/deruefx/CrimProjects/PAVICS/Magpie')
import os

__version__ = '0.3.3'


def main(global_config, **settings):
    """
    This function returns a Pyramid WSGI application.
    """
    from pyramid.config import Configurator
    from pyramid.authentication import AuthTktAuthenticationPolicy
    from pyramid.authorization import ACLAuthorizationPolicy


    from magpie.models import group_finder

    magpie_secret = os.getenv('MAGPIE_SECRET')
    if magpie_secret is None:
        logger.debug('Use default secret from twitcher.ini')
        magpie_secret = settings['magpie.secret']

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

    # include twitcher components
    config.include('twitcher.config')
    config.include('twitcher.frontpage')
    #config.include('twitcher.rpcinterface')
    config.include('twitcher.owsproxy')
    config.include('twitcher.wps')

    # tweens/middleware
    # TODO: maybe add tween for exception handling or use unknown_failure view
    config.include('twitcher.tweens')

    config.scan()

    return config.make_wsgi_app()
