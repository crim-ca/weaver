import os
import sys

TWITCHER_MODULE_DIR = os.path.abspath(os.path.dirname(__file__))
TWITCHER_ROOT_DIR = os.path.abspath(os.path.dirname(TWITCHER_MODULE_DIR))
sys.path.insert(0, TWITCHER_ROOT_DIR)
sys.path.insert(0, TWITCHER_MODULE_DIR)

from twitcher.config import get_twitcher_configuration      # noqa E402
from pyramid.exceptions import ConfigurationError           # noqa E402
import logging                                              # noqa E402
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
    local_config = adapter_factory(settings).configurator_factory(settings)

    # celery
    if global_config.get('__file__') is not None:
        local_config.include('pyramid_celery')
        local_config.configure_celery(global_config['__file__'])

    # mako used by swagger-ui
    local_config.include('pyramid_mako')

    # include twitcher components
    local_config.include('twitcher.config')
    local_config.include('twitcher.database')
    local_config.include('twitcher.rpcinterface')
    local_config.include('twitcher.owsproxy')
    local_config.include('twitcher.wps')
    local_config.include('twitcher.wps_restapi')
    local_config.include('twitcher.processes')

    # tweens/middleware
    # TODO: maybe add tween for exception handling or use unknown_failure view
    local_config.include('twitcher.tweens')

    local_config.scan()

    return local_config.make_wsgi_app()
