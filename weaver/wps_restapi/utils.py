import logging
from typing import TYPE_CHECKING

from weaver.formats import CONTENT_TYPE_APP_JSON, CONTENT_TYPE_APP_XML
from weaver.utils import get_settings, get_weaver_url

if TYPE_CHECKING:
    from weaver.typedefs import AnySettingsContainer

LOGGER = logging.getLogger(__name__)

WPS_VERSION_100 = "1.0.0"
WPS_VERSION_200 = "2.0.0"
OUTPUT_FORMAT_JSON = "json"
OUTPUT_FORMAT_XML = "xml"
OUTPUT_FORMATS = {
    WPS_VERSION_100: OUTPUT_FORMAT_XML,
    WPS_VERSION_200: OUTPUT_FORMAT_JSON,
    CONTENT_TYPE_APP_XML: OUTPUT_FORMAT_XML,
    CONTENT_TYPE_APP_JSON: OUTPUT_FORMAT_JSON,
}


def wps_restapi_base_path(container):
    # type: (AnySettingsContainer) -> str
    settings = get_settings(container)
    restapi_path = settings.get("weaver.wps_restapi_path", "").rstrip("/").strip()
    return restapi_path


def get_wps_restapi_base_url(container):
    # type: (AnySettingsContainer) -> str
    settings = get_settings(container)
    weaver_rest_url = settings.get("weaver.wps_restapi_url")
    if not weaver_rest_url:
        weaver_url = get_weaver_url(settings)
        restapi_path = wps_restapi_base_path(settings)
        weaver_rest_url = weaver_url + restapi_path
    return weaver_rest_url
