import logging
import os
import tempfile
from configparser import ConfigParser
from typing import TYPE_CHECKING
from urllib.parse import urlparse

import lxml.etree
from owslib.wps import WebProcessingService, WPSExecution
from pyramid.httpexceptions import HTTPNotFound
from pywps import configuration as pywps_config

from weaver.config import get_weaver_configuration
from weaver.utils import (
    get_cookie_headers,
    get_settings,
    get_ssl_verify_option,
    get_url_without_query,
    get_weaver_url,
    is_uuid,
    make_dirs,
    request_extra
)

LOGGER = logging.getLogger(__name__)
if TYPE_CHECKING:
    from typing import Dict, Union, Optional

    from weaver.typedefs import AnySettingsContainer, AnyRequestType, HeadersType, XML


def _get_settings_or_wps_config(container,                  # type: AnySettingsContainer
                                weaver_setting_name,        # type: str
                                config_setting_section,     # type: str
                                config_setting_name,        # type: str
                                default_not_found,          # type: str
                                message_not_found,          # type: str
                                ):                          # type: (...) -> str

    settings = get_settings(container)
    found = settings.get(weaver_setting_name)
    if not found:
        if not settings.get("weaver.wps_configured"):
            load_pywps_config(container)
        found = pywps_config.CONFIG.get(config_setting_section, config_setting_name)
    if not isinstance(found, str):
        LOGGER.warning("%s not set in settings or WPS configuration, using default value.", message_not_found)
        found = default_not_found
    return found.strip()


def get_wps_path(container):
    # type: (AnySettingsContainer) -> str
    """
    Retrieves the WPS path (without hostname).

    Searches directly in settings, then `weaver.wps_cfg` file, or finally, uses the default values if not found.
    """
    return _get_settings_or_wps_config(container, "weaver.wps_path", "server", "url", "/ows/wps", "WPS path")


def get_wps_url(container):
    # type: (AnySettingsContainer) -> str
    """
    Retrieves the full WPS URL (hostname + WPS path)

    Searches directly in settings, then `weaver.wps_cfg` file, or finally, uses the default values if not found.
    """
    return get_settings(container).get("weaver.wps_url") or get_weaver_url(container) + get_wps_path(container)


def get_wps_output_dir(container):
    # type: (AnySettingsContainer) -> str
    """
    Retrieves the WPS output directory path where to write XML and result files.
    Searches directly in settings, then `weaver.wps_cfg` file, or finally, uses the default values if not found.
    """
    tmp_dir = tempfile.gettempdir()
    return _get_settings_or_wps_config(container, "weaver.wps_output_dir",
                                       "server", "outputpath", tmp_dir, "WPS output directory")


def get_wps_output_path(container):
    # type: (AnySettingsContainer) -> str
    """
    Retrieves the WPS output path (without hostname) for staging XML status, logs and process outputs.
    Searches directly in settings, then `weaver.wps_cfg` file, or finally, uses the default values if not found.
    """
    return get_settings(container).get("weaver.wps_output_path") or urlparse(get_wps_output_url(container)).path


def get_wps_output_url(container):
    # type: (AnySettingsContainer) -> str
    """
    Retrieves the WPS output URL that maps to WPS output directory path.
    Searches directly in settings, then `weaver.wps_cfg` file, or finally, uses the default values if not found.
    """
    wps_output_default = get_weaver_url(container) + "/wpsoutputs"
    wps_output_config = _get_settings_or_wps_config(
        container, "weaver.wps_output_url", "server", "outputurl", wps_output_default, "WPS output url")
    return wps_output_config or wps_output_default


def get_wps_local_status_location(url_status_location, container, must_exist=True):
    # type: (str, AnySettingsContainer, bool) -> Optional[str]
    """Attempts to retrieve the local XML file path corresponding to the WPS status location as URL.

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
    found = os.path.isfile(out_path)
    if not found and "/jobs/" in url_status_location:
        job_uuid = url_status_location.rsplit("/jobs/", 1)[-1].split("/", 1)[0]
        if is_uuid(job_uuid):
            out_path_join = os.path.join(dir_path, "{}.xml".format(job_uuid))
            found = os.path.isfile(out_path_join)
            if found or not must_exist:
                out_path = out_path_join
    if not found and must_exist:
        out_path_join = os.path.join(dir_path, out_path[1:] if out_path.startswith("/") else out_path)
        if not os.path.isfile(out_path_join):
            LOGGER.debug("Could not map WPS status reference [%s] to input local file path [%s].",
                         url_status_location, out_path)
            return None
        out_path = out_path_join
    LOGGER.debug("Resolved WPS status reference [%s] as local file path [%s].", url_status_location, out_path)
    return out_path


def get_wps_client(url, container=None, verify=None, headers=None, language=None):
    # type: (str, Optional[AnySettingsContainer], bool, Optional[HeadersType], Optional[str]) -> WebProcessingService
    """
    Obtains a :class:`WebProcessingService` with pre-configured request options for the given URL.

    :param url: WPS URL location.
    :param container: request or settings container to retrieve headers and other request options.
    :param verify: flag to enable SSL verification (overrides request options from container).
    :param headers: specific headers to apply (overrides retrieved ones from container).
    :param language: preferred response language if supported by the service.
    :returns: created WPS client object with configured request options.
    """
    headers = headers or {}
    if headers is None and hasattr(container, "headers"):
        headers = get_cookie_headers(container.headers)
    # remove invalid values that should be recomputed by the client as needed
    for hdr in ["Accept", "Content-Length", "Content-Type", "Content-Transfer-Encoding"]:
        headers.pop(hdr, None)
    if verify is None:
        verify = get_ssl_verify_option("get", url, container)
    wps = WebProcessingService(url=url, headers=headers, verify=verify)
    set_wps_language(wps, request=container, accept_language=language)
    return wps


def check_wps_status(location=None,     # type: Optional[str]
                     response=None,     # type: Optional[XML]
                     sleep_secs=2,      # type: int
                     verify=True,       # type: bool
                     settings=None,     # type: Optional[AnySettingsContainer]
                     ):                 # type: (...) -> WPSExecution
    """
    Run :func:`owslib.wps.WPSExecution.checkStatus` with additional exception handling.

    :param location: job URL or file path where to look for job status.
    :param response: WPS response document of job status.
    :param sleep_secs: number of seconds to sleep before returning control to the caller.
    :param verify: flag to enable SSL verification.
    :param settings: application settings to retrieve any additional request parameters as applicable.
    :returns: OWSLib.wps.WPSExecution object.
    """
    def _retry_file():
        LOGGER.warning("Failed retrieving WPS status-location, attempting with local file.")
        out_path = get_wps_local_status_location(location, settings)
        if not out_path:
            raise HTTPNotFound("Could not find file resource from [{}].".format(location))
        LOGGER.info("Resolved WPS status-location using local file reference.")
        return open(out_path, "r").read()

    execution = WPSExecution()
    if response:
        LOGGER.debug("Retrieving WPS status from XML response document...")
        xml = response
    elif location:
        xml_resp = HTTPNotFound()
        try:
            LOGGER.debug("Attempt to retrieve WPS status-location from URL [%s]...", location)
            xml_resp = request_extra("get", location, verify=verify, settings=settings)
            xml = xml_resp.content
        except Exception as ex:
            LOGGER.debug("Got exception during get status: [%r]", ex)
            xml = _retry_file()
        if xml_resp.status_code == HTTPNotFound.code:
            LOGGER.debug("Got not-found during get status: [%r]", xml)
            xml = _retry_file()
    else:
        raise Exception("Missing status-location URL/file reference or response with XML object.")
    if isinstance(xml, str):
        xml = xml.encode("utf8", errors="ignore")
    execution.checkStatus(response=xml, sleepSecs=sleep_secs)
    if execution.response is None:
        raise Exception("Missing response, cannot check status.")
    if not isinstance(execution.response, lxml.etree._Element):  # noqa
        execution.response = lxml.etree.fromstring(execution.response)
    return execution


def load_pywps_config(container, config=None):
    # type: (AnySettingsContainer, Optional[Union[str, Dict[str, str]]]) -> ConfigParser
    """
    Loads and updates the PyWPS configuration using Weaver settings.
    """
    settings = get_settings(container)
    if settings.get("weaver.wps_configured"):
        LOGGER.debug("Using preloaded internal Weaver WPS configuration.")
        return pywps_config.CONFIG

    LOGGER.info("Initial load of internal Weaver WPS configuration.")
    pywps_config.load_configuration([])  # load defaults
    pywps_config.CONFIG.set("logging", "db_echo", "false")
    if logging.getLevelName(pywps_config.CONFIG.get("logging", "level")) <= logging.DEBUG:
        pywps_config.CONFIG.set("logging", "level", "INFO")

    # update metadata
    LOGGER.debug("Updating WPS metadata configuration.")
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

    LOGGER.debug("Updating WPS output configuration.")
    # find output directory from app config or wps config
    if "weaver.wps_output_dir" not in settings:
        output_dir = pywps_config.get_config_value("server", "outputpath")
        settings["weaver.wps_output_dir"] = output_dir
    # ensure the output dir exists if specified
    output_dir = get_wps_output_dir(settings)
    make_dirs(output_dir, exist_ok=True)
    # find output url from app config (path/url) or wps config (url only)
    # note: needs to be configured even when using S3 bucket since XML status is provided locally
    if "weaver.wps_output_url" not in settings:
        output_path = settings.get("weaver.wps_output_path", "")
        if isinstance(output_path, str):
            output_url = os.path.join(get_weaver_url(settings), output_path.strip("/"))
        else:
            output_url = pywps_config.get_config_value("server", "outputurl")
        settings["weaver.wps_output_url"] = output_url
    # apply workdir if provided, otherwise use default
    if "weaver.wps_workdir" in settings:
        make_dirs(settings["weaver.wps_workdir"], exist_ok=True)
        pywps_config.CONFIG.set("server", "workdir", settings["weaver.wps_workdir"])

    # configure S3 bucket if requested, storage of all process outputs
    # note:
    #   credentials and default profile are picked up automatically by 'boto3' from local AWS configs or env vars
    #   region can also be picked from there unless explicitly provided by weaver config
    # warning:
    #   if we set `(server, storagetype, s3)`, ALL status (including XML) are stored to S3
    #   to preserve status locally, we set 'file' and override the storage instance during output rewrite in WpsPackage
    #   we can still make use of the server configurations here to make this overridden storage auto-find its configs
    s3_bucket = settings.get("weaver.wps_output_s3_bucket")
    pywps_config.CONFIG.set("server", "storagetype", "file")
    # pywps_config.CONFIG.set("server", "storagetype", "s3")
    if s3_bucket:
        LOGGER.debug("Updating WPS S3 bucket configuration.")
        import boto3
        from botocore.exceptions import ClientError
        s3 = boto3.client("s3")
        s3_region = settings.get("weaver.wps_output_s3_region", s3.meta.region_name)
        LOGGER.info("Validating that S3 [Bucket=%s, Region=%s] exists or creating it.", s3_bucket, s3_region)
        try:
            s3.create_bucket(Bucket=s3_bucket, CreateBucketConfiguration={"LocationConstraint": s3_region})
            LOGGER.info("S3 bucket for WPS output created.")
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") != "BucketAlreadyExists":
                LOGGER.error("Failed setup of S3 bucket for WPS output: [%s]", exc)
                raise
            LOGGER.info("S3 bucket for WPS output already exists.")
        pywps_config.CONFIG.set("s3", "region", s3_region)
        pywps_config.CONFIG.set("s3", "bucket", s3_bucket)
        pywps_config.CONFIG.set("s3", "public", "false")  # don't automatically push results as publicly accessible
        pywps_config.CONFIG.set("s3", "encrypt", "true")  # encrypts data server-side, transparent from this side

    # enforce back resolved values onto PyWPS config
    pywps_config.CONFIG.set("server", "setworkdir", "true")
    pywps_config.CONFIG.set("server", "sethomedir", "true")
    pywps_config.CONFIG.set("server", "outputpath", settings["weaver.wps_output_dir"])
    pywps_config.CONFIG.set("server", "outputurl", settings["weaver.wps_output_url"])
    settings["weaver.wps_configured"] = True
    return pywps_config.CONFIG


def set_wps_language(wps, accept_language=None, request=None):
    # type: (WebProcessingService, Optional[str], Optional[AnyRequestType]) -> None
    """Set the :attr:`language` property on the :class:`WebProcessingService` object.

    Given the `Accept-Language` header value, match the best language
    to the supported languages.

    By default, and if no match is found, the :attr:`WebProcessingService.language`
    property is set to None.

    https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Accept-Language
    (q-factor weighting is ignored, only order is considered)

    :param wps: process for which to set the language header if it is accepted
    :param str accept_language: the value of the Accept-Language header
    :param request: request from which to extract Accept-Language header if not provided directly
    """
    if not accept_language and request and hasattr(request, "accept_language"):
        accept_language = request.accept_language.header_value

    if not accept_language:
        return

    if not hasattr(wps, "languages"):
        # owslib version doesn't support setting a language
        return

    accepted_languages = [lang.strip().split(";")[0] for lang in accept_language.lower().split(",")]

    for accept in accepted_languages:
        for language in wps.languages.supported:    # noqa
            # Accept-Language header could be only 'fr' instead of 'fr-CA'
            if language.lower().startswith(accept):
                wps.language = language
                return
