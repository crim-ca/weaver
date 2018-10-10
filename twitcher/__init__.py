__version__ = 'ogc-0.3.15-dev'

import os
import sys
TWITCHER_MODULE_DIR = os.path.abspath(os.path.dirname(__file__))
TWITCHER_ROOT_DIR = os.path.abspath(os.path.dirname(TWITCHER_MODULE_DIR))
sys.path.insert(0, TWITCHER_ROOT_DIR)
sys.path.insert(0, TWITCHER_MODULE_DIR)

from twitcher import adapter
from twitcher.config import get_twitcher_configuration
from pyramid.exceptions import ConfigurationError
from pyramid.httpexceptions import HTTPServerError
from pyramid.view import exception_view_config, notfound_view_config, forbidden_view_config
import logging
logger = logging.getLogger('TWITCHER')


def parse_extra_options(option_str):
    """
    Parses the extra options parameter.

    The option_str is a string with coma separated ``opt=value`` pairs.
    Example::

        tempdir=/path/to/tempdir,archive_root=/path/to/archive

    :param option_str: A string parameter with the extra options.
    :return: A dict with the parsed extra options.
    """
    if option_str:
        try:
            extra_options = option_str.split(',')
            extra_options = dict([('=' in opt) and opt.split('=', 1) for opt in extra_options])
        except Exception:
            msg = "Can not parse extra-options: {}".format(option_str)
            raise ConfigurationError(msg)
    else:
        extra_options = {}
    return extra_options


def main(global_config, **settings):
    """
    This function returns a Pyramid WSGI application.
    """

    # validate and fix configuration
    twitcher_config = get_twitcher_configuration(settings)
    settings.update({'twitcher.configuration': twitcher_config})

    # Parse extra_options and add each of them in the settings dict
    settings.update(parse_extra_options(settings.get('twitcher.extra_options', '')))

    from twitcher.adapter import adapter_factory

    config = adapter_factory(settings).configurator_factory(settings)

    # celery
    config.include('pyramid_celery')
    config.configure_celery(global_config['__file__'])

    # mako used by swagger-ui
    config.include('pyramid_mako')

    # include twitcher components
    config.include('twitcher.config')
    config.include('twitcher.rpcinterface')
    config.include('twitcher.owsproxy')
    config.include('twitcher.wps')
    config.include('twitcher.wps_restapi')
    config.include('twitcher.processes')

    # tweens/middleware
    # TODO: maybe add tween for exception handling or use unknown_failure view
    config.include('twitcher.tweens')

    ##config.add_exception_view(exception_view)

    config.scan()

    return config.make_wsgi_app()
