from pyramid.config import Configurator
from pyramid.tweens import EXCVIEW

from twitcher.tweens import OWS_SECURITY

import logging
logger = logging.getLogger(__name__)

def main(global_config, **settings):
    """
    This function returns a Pyramid WSGI application.
    """
    config = Configurator(settings=settings)

    # beaker session
    config.include('pyramid_beaker')

    # include twitcher components
    config.include('twitcher.frontpage')
    config.include('twitcher.rpcinterface')
    config.include('twitcher.owsproxy')
    config.include('twitcher.wps')
    
    # tweens/middleware
    config.add_tween(OWS_SECURITY, under=EXCVIEW)
   
    config.scan()

    return config.make_wsgi_app()

