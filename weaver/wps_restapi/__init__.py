import logging
from typing import TYPE_CHECKING

from pyramid.settings import asbool

from weaver.utils import get_settings
from weaver.wps_restapi.utils import get_wps_restapi_base_path

if TYPE_CHECKING:
    from pyramid.config import Configurator

LOGGER = logging.getLogger(__name__)


def includeme(config):
    # type: (Configurator) -> None

    settings = get_settings(config)
    config.include("weaver.wps_restapi.api")  # only API informative endpoints
    if not asbool(settings.get("weaver.wps_restapi", True)):
        LOGGER.warning("Skipping WPS REST API views [weaver.wps_restapi=false].")
    else:
        LOGGER.info("Adding WPS REST API views...")
        api_base = get_wps_restapi_base_path(settings)
        with config.route_prefix_context(route_prefix=api_base):
            config.include("weaver.wps_restapi.jobs")
            config.include("weaver.wps_restapi.providers")
            config.include("weaver.wps_restapi.processes")
            config.include("weaver.wps_restapi.quotation")
