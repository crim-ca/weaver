"""
pywps 4.x wrapper
"""
from weaver.config import get_weaver_configuration
from weaver.database import get_db
from weaver.store.base import StoreProcesses
from weaver.owsexceptions import OWSNoApplicableCode
from weaver.visibility import VISIBILITY_PUBLIC
from weaver.utils import get_weaver_url, get_settings
from pyramid.wsgi import wsgiapp2
from pyramid.settings import asbool
from pyramid_celery import celery_app as app
from pyramid.threadlocal import get_current_request
from pywps import configuration as pywps_config
from pywps.app.Service import Service
from six.moves.configparser import ConfigParser
from six.moves.urllib.parse import urlparse
from typing import TYPE_CHECKING
import os
import six
import logging
LOGGER = logging.getLogger(__name__)
if TYPE_CHECKING:
    from weaver.typedefs import AnySettingsContainer        # noqa: F401
    from typing import AnyStr, Dict, Union, Optional        # noqa: F401

# global config
WEAVER_PYWPS_CFG = None    # type: Optional[ConfigParser]


def _get_settings_or_wps_config(container,                  # type: AnySettingsContainer
                                weaver_setting_name,        # type: AnyStr
                                config_setting_section,     # type: AnyStr
                                config_setting_name,        # type: AnyStr
                                default_not_found,          # type: AnyStr
                                message_not_found,          # type: AnyStr
                                ):                          # type: (...) -> AnyStr
    global WEAVER_PYWPS_CFG

    settings = get_settings(container)
    found = settings.get(weaver_setting_name)
    if not found:
        if not WEAVER_PYWPS_CFG:
            load_pywps_cfg(container)
        found = WEAVER_PYWPS_CFG.get(config_setting_section, config_setting_name)
    if not isinstance(found, six.string_types):
        LOGGER.warn("{} not set in settings or WPS configuration, using default value.".format(message_not_found))
        found = default_not_found
    return found.strip()


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
    # type: (AnySettingsContainer, Optional[Union[AnyStr, Dict[AnyStr, AnyStr]]]) -> ConfigParser
    """Loads and updates the PyWPS configuration using Weaver settings."""
    global WEAVER_PYWPS_CFG

    settings = get_settings(container)
    if WEAVER_PYWPS_CFG is None:
        # initial setup of PyWPS config
        pywps_config.load_configuration([])  # load defaults
        WEAVER_PYWPS_CFG = pywps_config.CONFIG  # update reference
        # must be set to INFO to disable sqlalchemy trace.
        # see : https://github.com/geopython/pywps/blob/master/pywps/dblog.py#L169
        if logging.getLevelName(WEAVER_PYWPS_CFG.get("logging", "level")) <= logging.DEBUG:
            WEAVER_PYWPS_CFG.set("logging", "level", "INFO")
        # update metadata
        for setting_name, setting_value in settings.items():
            if setting_name.startswith("weaver.wps_metadata"):
                WEAVER_PYWPS_CFG.set("metadata:main", setting_name.replace("weaver.wps_metadata", ""), setting_value)
        # add weaver configuration keyword if not already provided
        wps_keywords = WEAVER_PYWPS_CFG.get("metadata:main", "identification_keywords")
        weaver_mode = get_weaver_configuration(settings)
        if weaver_mode not in wps_keywords:
            wps_keywords += ("," if wps_keywords else "") + weaver_mode
            WEAVER_PYWPS_CFG.set("metadata:main", "identification_keywords", wps_keywords)

    # add additional config passed as dictionary of {'section.key': 'value'}
    if isinstance(config, dict):
        for key, value in config.items():
            section, key = key.split('.')
            WEAVER_PYWPS_CFG.CONFIG.set(section, key, value)
        # cleanup alternative dict "PYWPS_CFG" which is not expected elsewhere
        if isinstance(settings.get("PYWPS_CFG"), dict):
            del settings["PYWPS_CFG"]

    # find output directory from app config or wps config
    if "weaver.wps_output_dir" not in settings:
        output_dir = pywps_config.get_config_value("server", "outputpath")
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
            output_url = WEAVER_PYWPS_CFG.get_config_value("server", "outputurl")
        settings["weaver.wps_output_url"] = output_url

    # enforce back resolved values onto PyWPS config
    WEAVER_PYWPS_CFG.set("server", "setworkdir", "true")
    WEAVER_PYWPS_CFG.set("server", "sethomedir", "true")
    WEAVER_PYWPS_CFG.set("server", "outputpath", settings["weaver.wps_output_dir"])
    WEAVER_PYWPS_CFG.set("server", "outputurl", settings["weaver.wps_output_url"])
    return WEAVER_PYWPS_CFG


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
        pywps_cfg = environ.get("PYWPS_CFG") or settings.get("PYWPS_CFG") or os.getenv("PYWPS_CFG")
        if not isinstance(pywps_cfg, ConfigParser):
            load_pywps_cfg(app, config=pywps_cfg)

        # call pywps application with processes filtered according to the adapter"s definition
        process_store = get_db(app).get_store(StoreProcesses)
        processes_wps = [process.wps() for process in
                         process_store.list_processes(visibility=VISIBILITY_PUBLIC, request=get_current_request())]
        service = Service(processes_wps)
    except Exception as ex:
        raise OWSNoApplicableCode("Failed setup of PyWPS Service and/or Processes. Error [{!r}]".format(ex))

    return service(environ, start_response)


def includeme(config):
    settings = get_settings(config)
    if asbool(settings.get("weaver.wps", True)):
        LOGGER.debug("Weaver WPS enabled.")
        config.include("weaver.config")
        wps_path = get_wps_path(settings)
        config.add_route("wps", wps_path)
        config.add_view(pywps_view, route_name="wps")
