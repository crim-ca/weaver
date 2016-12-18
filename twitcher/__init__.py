import tempfile

from pyramid.config import Configurator

import logging
logger = logging.getLogger(__name__)


def _workdir(request):
    settings = request.registry.settings
    workdir = settings.get('twitcher.temp_path')
    workdir = workdir or tempfile.gettempdir()
    logger.debug('using workdir %s', workdir)
    return workdir


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
    # TODO: maybe add tween for exception handling or use unknown_failure view
    config.include('twitcher.tweens')

    # configuraton
    config.add_request_method(_workdir, 'workdir', reify=True)

    config.scan()

    return config.make_wsgi_app()
