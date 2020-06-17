"""
pywps 4.x wrapper
"""
import logging
import os
import tempfile
from typing import TYPE_CHECKING

import six
from lxml import etree
from owslib.wps import WPSExecution
from pyramid.httpexceptions import HTTPNotFound
from pyramid.settings import asbool
from pyramid.threadlocal import get_current_request
from pyramid.wsgi import wsgiapp2
from pyramid_celery import celery_app as app
from pywps import configuration as pywps_config
from pywps.app.Service import Service
from six.moves.configparser import ConfigParser
from six.moves.urllib.parse import urlparse

from weaver.config import get_weaver_configuration
from weaver.database import get_db
from weaver.owsexceptions import OWSNoApplicableCode
from weaver.store.base import StoreProcesses
from weaver.utils import get_settings, get_url_without_query, get_weaver_url, make_dirs, request_extra
from weaver.visibility import VISIBILITY_PUBLIC

LOGGER = logging.getLogger(__name__)
if TYPE_CHECKING:
    from weaver.typedefs import AnySettingsContainer        # noqa: F401
    from typing import AnyStr, Dict, Union, Optional        # noqa: F401


def _get_settings_or_wps_config(container,                  # type: AnySettingsContainer
                                weaver_setting_name,        # type: AnyStr
                                config_setting_section,     # type: AnyStr
                                config_setting_name,        # type: AnyStr
                                default_not_found,          # type: AnyStr
                                message_not_found,          # type: AnyStr
                                ):                          # type: (...) -> AnyStr

    settings = get_settings(container)
    found = settings.get(weaver_setting_name)
    if not found:
        if not settings.get("weaver.wps_configured"):
            load_pywps_cfg(container)
        found = pywps_config.CONFIG.get(config_setting_section, config_setting_name)
    if not isinstance(found, six.string_types):
        LOGGER.warning("%s not set in settings or WPS configuration, using default value.", message_not_found)
        found = default_not_found
    return found.strip()


def get_wps_path(container):
    # type: (AnySettingsContainer) -> AnyStr
    """
    Retrieves the WPS path (without hostname).
    Searches directly in settings, then `weaver.wps_cfg` file, or finally, uses the default values if not found.
    """
    return _get_settings_or_wps_config(container, "weaver.wps_path", "server", "url", "/ows/wps", "WPS path")


def get_wps_url(container):
    # type: (AnySettingsContainer) -> AnyStr
    """
    Retrieves the full WPS URL (hostname + WPS path).
    Searches directly in settings, then `weaver.wps_cfg` file, or finally, uses the default values if not found.
    """
    return get_settings(container).get("weaver.wps_url") or get_weaver_url(container) + get_wps_path(container)


def get_wps_output_dir(container):
    # type: (AnySettingsContainer) -> AnyStr
    """
    Retrieves the WPS output directory path where to write XML and result files.
    Searches directly in settings, then `weaver.wps_cfg` file, or finally, uses the default values if not found.
    """
    tmp_dir = tempfile.gettempdir()
    return _get_settings_or_wps_config(container, "weaver.wps_output_dir",
                                       "server", "outputpath", tmp_dir, "WPS output directory")


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
    wps_output_config = _get_settings_or_wps_config(
        container, "weaver.wps_output_url", "server", "outputurl", wps_output_default, "WPS output url")
    return wps_output_config or wps_output_default


def get_wps_local_status_location(url_status_location, container, must_exist=True):
    # type: (AnyStr, AnySettingsContainer, bool) -> Optional[AnyStr]
    """Attempts to retrieve the local file path corresponding to the WPS status location as URL.

    :param url_status_location: URL reference pointing to some WPS status location XML.
    :param container: any settings container to map configured local paths.
    :param must_exist: return only existing path if enabled, otherwise return the parsed value without validation.
    :returns: found local file path if it exists, ``None`` otherwise.
    """
    dir_path = get_wps_output_dir(container)
    if url_status_location and not urlparse(url_status_location).scheme in ["", "file"]:
        wps_out_url = get_wps_output_url(container)
        req_out_url = get_url_without_query(url_status_location)
        out_path = os.path.join(dir_path, req_out_url.replace(wps_out_url, "").lstrip("/"))
    else:
        out_path = url_status_location.replace("file://", "")
    if must_exist and not os.path.isfile(out_path):
        out_path_join = os.path.join(dir_path, out_path[1:] if out_path.startswith("/") else out_path)
        if not os.path.isfile(out_path_join):
            LOGGER.debug("Could not map WPS status reference [%s] to input local file path [%s].",
                         url_status_location, out_path)
            return None
        out_path = out_path_join
    LOGGER.debug("Resolved WPS status reference [%s] as local file path [%s].", url_status_location, out_path)
    return out_path


def check_wps_status(url=None, response=None, sleep_secs=2, verify=True, settings=None):
    # type: (Optional[AnyStr], Optional[etree.ElementBase], int, bool, Optional[AnySettingsContainer]) -> WPSExecution
    """
    Run :func:`owslib.wps.WPSExecution.checkStatus` with additional exception handling.

    :param url: job URL where to look for job status.
    :param response: WPS response document of job status.
    :param sleep_secs: number of seconds to sleep before returning control to the caller.
    :param verify: Flag to enable SSL verification.
    :param settings: Application settings to retrieve any additional request parameters as applicable.
    :return: OWSLib.wps.WPSExecution object.
    """
    def _retry_file():
        LOGGER.warning("Failed retrieving WPS status-location, attempting with local file.")
        out_path = get_wps_local_status_location(url, settings)
        if not out_path:
            raise HTTPNotFound("Could not find file resource from [{}].".format(url))
        LOGGER.info("Resolved WPS status-location using local file reference.")
        return open(out_path, "r").read()

    execution = WPSExecution()
    if response:
        LOGGER.debug("Retrieving WPS status from XML response document...")
        xml = response
    elif url:
        xml_resp = HTTPNotFound()
        try:
            LOGGER.debug("Attempt to retrieve WPS status-location from URL...")
            xml_resp = request_extra("get", url, verify=verify, settings=settings)
            xml = xml_resp.content
        except Exception as ex:
            LOGGER.debug("Got exception during get status: [%r]", ex)
            xml = _retry_file()
        if xml_resp.status_code == HTTPNotFound.code:
            LOGGER.debug("Got not-found during get status: [%r]", xml)
            xml = _retry_file()
    else:
        raise Exception("Missing status-location URL/file reference or response with XML object.")
    if isinstance(xml, six.string_types):
        xml = xml.encode("utf8", errors="ignore")
    execution.checkStatus(response=xml, sleepSecs=sleep_secs)
    if execution.response is None:
        raise Exception("Missing response, cannot check status.")
    if not isinstance(execution.response, etree._Element):  # noqa: W0212
        execution.response = etree.fromstring(execution.response)
    return execution


def load_pywps_cfg(container, config=None):
    # type: (AnySettingsContainer, Optional[Union[AnyStr, Dict[AnyStr, AnyStr]]]) -> ConfigParser
    """
    Loads and updates the PyWPS configuration using Weaver settings.
    """
    settings = get_settings(container)
    if settings.get("weaver.wps_configured"):
        LOGGER.debug("Using preloaded internal Weaver WPS configuration.")
        return pywps_config.CONFIG

    LOGGER.info("Initial load of internal Weaver WPS configuration.")
    pywps_config.load_configuration([])  # load defaults
    # must be set to INFO to disable sqlalchemy trace.
    # see : https://github.com/geopython/pywps/blob/master/pywps/dblog.py#L169
    if logging.getLevelName(pywps_config.CONFIG.get("logging", "level")) <= logging.DEBUG:
        pywps_config.CONFIG.set("logging", "level", "INFO")
    # update metadata
    for setting_name, setting_value in settings.items():
        if setting_name.startswith("weaver.wps_metadata"):
            pywps_setting = setting_name.replace("weaver.wps_metadata_", "")
            pywps_config.CONFIG.set("metadata:main", pywps_setting, setting_value)
    # add weaver configuration keyword if not already provided
    wps_keywords = pywps_config.CONFIG.get("metadata:main", "identification_keywords")
    weaver_mode = get_weaver_configuration(settings)
    if weaver_mode not in wps_keywords:
        wps_keywords += ("," if wps_keywords else "") + weaver_mode
        pywps_config.CONFIG.set("metadata:main", "identification_keywords", wps_keywords)

    # add additional config passed as dictionary of {'section.key': 'value'}
    if isinstance(config, dict):
        for key, value in config.items():
            section, key = key.split(".")
            pywps_config.CONFIG.set(section, key, value)
        # cleanup alternative dict "PYWPS_CFG" which is not expected elsewhere
        if isinstance(settings.get("PYWPS_CFG"), dict):
            del settings["PYWPS_CFG"]

    # find output directory from app config or wps config
    if "weaver.wps_output_dir" not in settings:
        output_dir = pywps_config.get_config_value("server", "outputpath")
        settings["weaver.wps_output_dir"] = output_dir
    # ensure the output dir exists if specified
    output_dir = get_wps_output_dir(settings)
    make_dirs(output_dir, exist_ok=True)

    # find output url from app config (path/url) or wps config (url only)
    if "weaver.wps_output_url" not in settings:
        output_path = settings.get("weaver.wps_output_path", "")
        if isinstance(output_path, six.string_types):
            output_url = os.path.join(get_weaver_url(settings), output_path.strip("/"))
        else:
            output_url = pywps_config.get_config_value("server", "outputurl")
        settings["weaver.wps_output_url"] = output_url

    # apply workdir if provided, otherwise use default
    if "weaver.wps_workdir" in settings:
        make_dirs(settings["weaver.wps_workdir"], exist_ok=True)
        pywps_config.CONFIG.set("server", "workdir", settings["weaver.wps_workdir"])

    # enforce back resolved values onto PyWPS config
    pywps_config.CONFIG.set("server", "setworkdir", "true")
    pywps_config.CONFIG.set("server", "sethomedir", "true")
    pywps_config.CONFIG.set("server", "outputpath", settings["weaver.wps_output_dir"])
    pywps_config.CONFIG.set("server", "outputurl", settings["weaver.wps_output_url"])
    settings["weaver.wps_configured"] = True
    return pywps_config.CONFIG


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
        if not isinstance(pywps_cfg, ConfigParser) or not settings.get("weaver.wps_configured"):
            load_pywps_cfg(app, config=pywps_cfg)

        # call pywps application with processes filtered according to the adapter"s definition
        process_store = get_db(app).get_store(StoreProcesses)
        processes_wps = [process.wps() for process in
                         process_store.list_processes(visibility=VISIBILITY_PUBLIC, request=get_current_request())]
        service = Service(processes_wps)
    except Exception as ex:
        LOGGER.exception("Error occurred during PyWPS Service and/or Processes setup.")
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
        config.add_static_view(get_wps_output_path(config), get_wps_output_dir(config))
