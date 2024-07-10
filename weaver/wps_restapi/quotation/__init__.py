import logging
from typing import TYPE_CHECKING

from weaver.utils import get_settings
from weaver.wps_restapi.quotation.utils import check_quotation_supported

if TYPE_CHECKING:
    from pyramid.config import Configurator

LOGGER = logging.getLogger(__name__)


def includeme(config):
    # type: (Configurator) -> None

    settings = get_settings(config)
    if not check_quotation_supported(settings):
        LOGGER.warning("Skipping WPS REST API quotation.")
        return

    LOGGER.info("Adding WPS REST API quotation...")
    config.include("weaver.wps_restapi.quotation.bills")
    config.include("weaver.wps_restapi.quotation.quotes")
