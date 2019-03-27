"""
pywps 4.x wrapper
"""
from weaver.database import get_db
from weaver.store.base import StoreProcesses
from weaver.owsexceptions import OWSNoApplicableCode
from weaver.visibility import VISIBILITY_PUBLIC
from weaver.utils import get_weaver_url, get_settings
from pyramid.wsgi import wsgiapp2
from pyramid.settings import asbool
from pyramid_celery import celery_app as app
from pyramid.threadlocal import get_current_request
# noinspection PyPackageRequirements
from pywps import configuration as pywps_config
# noinspection PyPackageRequirements
from pywps.app.Service import Service
from six.moves.configparser import SafeConfigParser
from six.moves.urllib.parse import urlparse
from typing import TYPE_CHECKING
import os
import six
import logging
LOGGER = logging.getLogger(__name__)
if TYPE_CHECKING:
    from weaver.typedefs import AnySettingsContainer
    from typing import AnyStr, Dict, Union, Optional

# can be overridden with 'settings.wps-cfg'
DEFAULT_PYWPS_CFG = os.path.join(os.path.abspath(os.path.dirname(__file__)), "wps.cfg")
PYWPS_CFG = None


def _get_settings_or_wps_config(container,                  # type: AnySettingsContainer
                                weaver_setting_name,        # type: AnyStr
                                config_setting_section,     # type: AnyStr
                                config_setting_name,        # type: AnyStr
                                default_not_found,          # type: AnyStr
                                message_not_found,          # type: AnyStr
                                ):                          # type: (...) -> AnyStr
    settings = get_settings(container)
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


def get_wps_cfg_path(container):
    # type: (AnySettingsContainer) -> AnyStr
    """
    Retrieves the WPS configuration file (`wps.cfg` by default or `weaver.wps_cfg` if specified).
    """
    return get_settings(container).get("weaver.wps_cfg", DEFAULT_PYWPS_CFG)


def get_wps_path(container):
    # type: (AnySettingsContainer) -> AnyStr
    """
    Retrieves the WPS path (without hostname).
    Searches directly in settings, then `weaver.wps_cfg` file, or finally, uses the default values if not found.
    """
    return _get_settings_or_wps_config(
        container, "weaver.wps_path", "server", "url", "/ows/wps", "WPS path")


def get_wps_url(container):
    # type: (AnySettingsContainer) -> AnyStr
    """
    Retrieves the full WPS URL (hostname + WPS path).
    Searches directly in settings, then `weaver.wps_cfg` file, or finally, uses the default values if not found.
    """
    return get_weaver_url(container) + get_wps_path(container)


def get_wps_output_dir(container):
    # type: (AnySettingsContainer) -> AnyStr
    """
    Retrieves the WPS output directory path where to write XML and result files.
    Searches directly in settings, then `weaver.wps_cfg` file, or finally, uses the default values if not found.
    """
    return _get_settings_or_wps_config(
        container, "weaver.wps_output_dir", "server", "outputpath", "/tmp", "WPS output directory")


def get_wps_output_path(container):
    # type: (AnySettingsContainer) -> AnyStr
    """
    Retrieves the WPS output path (without hostname) for staging XML status, logs and process outputs.
    Searches directly in settings, then `weaver.wps_cfg` file, or finally, uses the default values if not found.
    """
    return get_settings(container).get("weaver.wps_output_path") or urlparse(get_wps_output_url(container)).path


def get_wps_output_url(container):
    # type: (AnySettingsContainer) -> AnyStr
    """
    Retrieves the WPS output URL that maps to WPS output directory path.
    Searches directly in settings, then `weaver.wps_cfg` file, or finally, uses the default values if not found.
    """
    wps_output_default = get_weaver_url(container) + "/wpsoutputs"
    return _get_settings_or_wps_config(
        container, "weaver.wps_output_url", "server", "outputurl", wps_output_default, "WPS output url")


def load_pywps_cfg(container, config=None):
    # type: (AnySettingsContainer, Optional[Union[AnyStr, Dict[AnyStr, AnyStr]]]) -> None
    global PYWPS_CFG

    settings = get_settings(container)
    if PYWPS_CFG is None:
        # get PyWPS config
        file_config = config if isinstance(config, six.string_types) or isinstance(config, list) else None
        pywps_config.load_configuration(file_config or get_wps_cfg_path(settings))
        PYWPS_CFG = pywps_config

    # add additional config passed as dictionary of {'section.key': 'value'}
    if isinstance(config, dict):
        for key, value in config.items():
            section, key = key.split('.')
            PYWPS_CFG.CONFIG.set(section, key, value)
        # cleanup alternative dict "PYWPS_CFG" which is not expected elsewhere
        if isinstance(settings.get("PYWPS_CFG"), dict):
            del settings["PYWPS_CFG"]

    # find output directory from app config or wps config
    if "weaver.wps_output_dir" not in settings:
        output_dir = PYWPS_CFG.get_config_value("server", "outputpath")
        settings["weaver.wps_output_dir"] = output_dir
    # ensure the output dir exists if specified
    output_dir = get_wps_output_dir(settings)
    if not os.path.isdir(output_dir):
        os.makedirs(output_dir)

    # find output url from app config (path/url) or wps config (url only)
    if "weaver.wps_output_url" not in settings:
        output_path = settings.get("weaver.wps_output_path", "")
        if output_path:
            output_url = os.path.join(get_weaver_url(settings), output_path.strip('/'))
        else:
            output_url = PYWPS_CFG.get_config_value("server", "outputurl")
        settings["weaver.wps_output_url"] = output_url

    # enforce back resolved values onto PyWPS config
    PYWPS_CFG.CONFIG.set("server", "outputpath", settings["weaver.wps_output_dir"])
    PYWPS_CFG.CONFIG.set("server", "outputurl", settings["weaver.wps_output_url"])


# @app.task(bind=True)
@wsgiapp2
def pywps_view(environ, start_response):
    """
    * TODO: add xml response renderer
    """
    LOGGER.debug("pywps env: %s", environ.keys())

    try:
        # get config file
        settings = get_settings(app)
        pywps_cfg = environ.get("PYWPS_CFG") or settings.get("PYWPS_CFG")
        if not pywps_cfg:
            environ["PYWPS_CFG"] = os.getenv("PYWPS_CFG") or get_wps_cfg_path(settings)
        load_pywps_cfg(app, config=pywps_cfg)

        # call pywps application with processes filtered according to the adapter"s definition
        process_store = get_db(app).get_store(StoreProcesses)
        processes_wps = [process.wps() for process in
                         process_store.list_processes(visibility=VISIBILITY_PUBLIC, request=get_current_request())]
        service = Service(processes_wps)
    except Exception as ex:
        raise OWSNoApplicableCode("Failed setup of PyWPS Service and/or Processes. Error [{}]".format(ex))

    return service(environ, start_response)


def includeme(config):
    settings = get_settings(config)
    if asbool(settings.get("weaver.wps", True)):
        LOGGER.debug("Weaver WPS enabled.")
        config.include("weaver.config")
        wps_path = get_wps_path(settings)
        config.add_route("wps", wps_path)
        config.add_view(pywps_view, route_name="wps")

        config.add_static_view(get_wps_output_path(config), get_wps_output_dir(config))

        config.add_request_method(lambda req: get_wps_cfg_path(req.registry.settings), "wps_cfg", reify=True)
