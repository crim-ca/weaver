import os
import sys
import logging
LOGGER = logging.getLogger('weaver')

WEAVER_MODULE_DIR = os.path.abspath(os.path.dirname(__file__))
WEAVER_ROOT_DIR = os.path.abspath(os.path.dirname(WEAVER_MODULE_DIR))
sys.path.insert(0, WEAVER_ROOT_DIR)
sys.path.insert(0, WEAVER_MODULE_DIR)

# ===============================================================================================
#   DO NOT IMPORT ANYTHING NOT PROVIDED BY BASE PYTHON HERE TO AVOID 'setup.py' INSTALL FAILURE
# ===============================================================================================


def main(global_config, **settings):
    """
    This function returns a Pyramid WSGI application.
    """
    from weaver.adapter import adapter_factory
    from weaver.config import get_weaver_configuration
    from weaver.utils import parse_extra_options

    # validate and fix configuration
    weaver_config = get_weaver_configuration(settings)
    settings.update({'weaver.configuration': weaver_config})

    # Parse extra_options and add each of them in the settings dict
    settings.update(parse_extra_options(settings.get('weaver.extra_options', '')))

    local_config = adapter_factory(settings).configurator_factory(settings)

    # celery
    if global_config.get('__file__') is not None:
        local_config.include('pyramid_celery')
        local_config.configure_celery(global_config['__file__'])

    # mako used by swagger-ui
    local_config.include('pyramid_mako')
    # cornice used by swagger-ui, swagger json and route definitions
    local_config.include('cornice')
    local_config.include('cornice_swagger')

    # include weaver components
    local_config.include('weaver.config')
    local_config.include('weaver.database')
    local_config.include('weaver.rpcinterface')
    local_config.include('weaver.owsproxy')
    local_config.include('weaver.wps')
    local_config.include('weaver.wps_restapi')
    local_config.include('weaver.processes')

    # tweens/middleware
    # TODO: maybe add tween for exception handling or use unknown_failure view
    local_config.include('weaver.tweens')

    local_config.scan()

    return local_config.make_wsgi_app()
