import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pyramid.config import Configurator

LOGGER = logging.getLogger(__name__)


def includeme(config):
    # type: (Configurator) -> None
    LOGGER.info("Adding WPS REST API providers...")
    config.include("weaver.wps_restapi.providers.providers")
