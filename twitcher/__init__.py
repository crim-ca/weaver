import os
import sys
import logging
LOGGER = logging.getLogger('TWITCHER')

TWITCHER_MODULE_DIR = os.path.abspath(os.path.dirname(__file__))
TWITCHER_ROOT_DIR = os.path.abspath(os.path.dirname(TWITCHER_MODULE_DIR))
sys.path.insert(0, TWITCHER_ROOT_DIR)
sys.path.insert(0, TWITCHER_MODULE_DIR)

# ===============================================================================================
#   DO NOT IMPORT ANYTHING NOT PROVIDED BY BASE PYTHON HERE TO AVOID 'setup.py' INSTALL FAILURE
# ===============================================================================================


def main(global_config, **settings):
    """
    This function returns a Pyramid WSGI application.
    """
    from twitcher.adapter import adapter_factory
    from twitcher.config import get_twitcher_configuration
    from twitcher.utils import parse_extra_options

    # validate and fix configuration
    twitcher_config = get_twitcher_configuration(settings)
    settings.update({'twitcher.configuration': twitcher_config})

    # Parse extra_options and add each of them in the settings dict
    settings.update(parse_extra_options(settings.get('twitcher.extra_options', '')))

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
