"""
pywps 4.x wrapper
"""

from pyramid.wsgi import wsgiapp2
from pyramid.settings import asbool
from pyramid.registry import Registry
from pyramid_celery import celery_app as app
from pyramid.threadlocal import get_current_request
# noinspection PyPackageRequirements
from pywps import configuration as pywps_config
# noinspection PyPackageRequirements
from pywps.app.Service import Service
from six.moves.configparser import SafeConfigParser
from typing import AnyStr, Dict, Union, Optional
from weaver.database import get_db
from weaver.store.base import StoreProcesses
from weaver.owsexceptions import OWSNoApplicableCode
from weaver.visibility import VISIBILITY_PUBLIC
from weaver.utils import get_weaver_url
import os
import six
import logging
LOGGER = logging.getLogger(__name__)

# can be overridden with 'settings.wps-cfg'
DEFAULT_PYWPS_CFG = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'wps.cfg')
PYWPS_CFG = None


def _get_settings_or_wps_config(
        settings,                   # type: Dict[AnyStr, AnyStr]
        weaver_setting_name,        # type: AnyStr
        config_setting_section,     # type: AnyStr
        config_setting_name,        # type: AnyStr
        default_not_found,          # type: AnyStr
        message_not_found,          # type: AnyStr
        ):                          # type: (...) -> AnyStr
    wps_path = settings.get(weaver_setting_name)
    if not wps_path:
        wps_cfg = get_wps_cfg_path(settings)
        config = SafeConfigParser()
        config.read(wps_cfg)
        wps_path = config.get(config_setting_section, config_setting_name)
    if not isinstance(wps_path, six.string_types):
        LOGGER.warn("{} not set in settings or WPS configuration, using default value.".format(message_not_found))
        wps_path = default_not_found
    return wps_path.rstrip('/').strip()


def get_wps_cfg_path(settings):
    # type: (Dict[AnyStr, AnyStr]) -> AnyStr
    """
    Retrieves the WPS configuration file (`wps.cfg` by default or `weaver.wps_cfg` if specified).
    """
    return settings.get('weaver.wps_cfg', DEFAULT_PYWPS_CFG)


def get_wps_path(settings):
    # type: (Dict[AnyStr, AnyStr]) -> AnyStr
    """
    Retrieves the WPS path (without hostname).
    Searches directly in settings, then `weaver.wps_cfg` file, or finally, uses the default values if not found.
    """
    return _get_settings_or_wps_config(
        settings, 'weaver.wps_path', 'server', 'url', '/ows/wps', 'WPS path')


def get_wps_url(settings):
    # type: (Dict[AnyStr, AnyStr]) -> AnyStr
    """
    Retrieves the full WPS URL (hostname + WPS path).
    Searches directly in settings, then `weaver.wps_cfg` file, or finally, uses the default values if not found.
    """
    return get_weaver_url(settings) + get_wps_path(settings)


def get_wps_output_path(settings):
    # type: (Dict[AnyStr, AnyStr]) -> AnyStr
    """
    Retrieves the WPS output path directory where to write XML and result files.
    Searches directly in settings, then `weaver.wps_cfg` file, or finally, uses the default values if not found.
    """
    return _get_settings_or_wps_config(
        settings, 'weaver.wps_output_path', 'server', 'outputpath', '/tmp', 'WPS output path')


def get_wps_output_url(settings):
    # type: (Dict[AnyStr, AnyStr]) -> AnyStr
    """
    Retrieves the WPS output URL that maps to WPS output path directory.
    Searches directly in settings, then `weaver.wps_cfg` file, or finally, uses the default values if not found.
    """
    wps_output_default = get_weaver_url(settings) + '/wpsoutputs'
    return _get_settings_or_wps_config(
        settings, 'weaver.wps_output_url', 'server', 'outputurl', wps_output_default, 'WPS output url')


def load_pywps_cfg(registry, config=None):
    # type: (Registry, Optional[Union[AnyStr, Dict[AnyStr, AnyStr]]]) -> None
    global PYWPS_CFG

    if PYWPS_CFG is None:
        # get PyWPS config
        file_config = config if isinstance(config, six.string_types) or isinstance(config, list) else None
        pywps_config.load_configuration(file_config or get_wps_cfg_path(registry.settings))
        PYWPS_CFG = pywps_config

    # add additional config passed as dictionary of {'section.key': 'value'}
    if isinstance(config, dict):
        for key, value in config.items():
            section, key = key.split('.')
            PYWPS_CFG.CONFIG.set(section, key, value)
        # cleanup alternative dict 'PYWPS_CFG' which is not expected elsewhere
        if isinstance(registry.settings.get('PYWPS_CFG'), dict):
            del registry.settings['PYWPS_CFG']

    if 'weaver.wps_output_path' not in registry.settings:
        # ensure the output dir exists if specified
        out_dir_path = PYWPS_CFG.get_config_value('server', 'outputpath')
        if not os.path.isdir(out_dir_path):
            os.makedirs(out_dir_path)
        registry.settings['weaver.wps_output_path'] = out_dir_path

    if 'weaver.wps_output_url' not in registry.settings:
        output_url = PYWPS_CFG.get_config_value('server', 'outputurl')
        registry.settings['weaver.wps_output_url'] = output_url


# @app.task(bind=True)
@wsgiapp2
def pywps_view(environ, start_response):
    """
    * TODO: add xml response renderer
    * TODO: fix exceptions ... use OWSException (raise ...)
    """
    LOGGER.debug('pywps env: %s', environ.keys())

    try:
        registry = app.conf['PYRAMID_REGISTRY']

        # get config file
        pywps_cfg = environ.get('PYWPS_CFG') or registry.settings.get('PYWPS_CFG')
        if not pywps_cfg:
            environ['PYWPS_CFG'] = os.getenv('PYWPS_CFG') or get_wps_cfg_path(registry.settings)
        load_pywps_cfg(registry, config=pywps_cfg)

        # call pywps application with processes filtered according to the adapter's definition
        process_store = get_db(registry).get_store(StoreProcesses)
        processes_wps = [process.wps() for process in
                         process_store.list_processes(visibility=VISIBILITY_PUBLIC, request=get_current_request())]
        service = Service(processes_wps)
    except Exception as ex:
        raise OWSNoApplicableCode("Failed setup of PyWPS Service and/or Processes. Error [{}]".format(ex))

    return service(environ, start_response)


def includeme(config):
    settings = config.registry.settings

    if asbool(settings.get('weaver.wps', True)):
        LOGGER.debug("weaver WPS enabled.")

        # include weaver config
        config.include('weaver.config')

        wps_path = get_wps_path(settings)
        config.add_route('wps', wps_path)
        config.add_route('wps_secured', wps_path + '/{access_token}')
        config.add_view(pywps_view, route_name='wps')
        config.add_view(pywps_view, route_name='wps_secured')
        config.add_request_method(lambda req: get_wps_cfg_path(req.registry.settings), 'wps_cfg', reify=True)
