import logging
from typing import TYPE_CHECKING

from weaver.utils import get_settings, get_weaver_url

if TYPE_CHECKING:
    from weaver.typedefs import AnySettingsContainer

LOGGER = logging.getLogger(__name__)


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
