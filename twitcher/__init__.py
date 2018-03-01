import logging
logger = logging.getLogger(__name__)

__version__ = '0.3.5'


def main(global_config, **settings):
    """
    This function returns a Pyramid WSGI application.
    """
    from pyramid.config import Configurator

    config = Configurator(settings=settings)

    # include twitcher components
    config.include('twitcher.config')
    config.include('twitcher.frontpage')
    config.include('twitcher.rpcinterface')
    config.include('twitcher.owsproxy')
    config.include('twitcher.wps')

    # tweens/middleware
    # TODO: maybe add tween for exception handling or use unknown_failure view
    config.include('twitcher.tweens')

    config.scan()

    return config.make_wsgi_app()
