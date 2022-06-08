import logging
from typing import TYPE_CHECKING

from pyramid.settings import asbool

from weaver.utils import get_settings
from weaver.vault import views as v
from weaver.wps_restapi import swagger_definitions as sd

if TYPE_CHECKING:
    from pyramid.config import Configurator

LOGGER = logging.getLogger(__name__)


def includeme(config):
    # type: (Configurator) -> None
    settings = get_settings(config)
    if asbool(settings.get("weaver.vault", True)):
        LOGGER.info("Adding file vault...")
        config.add_route(**sd.service_api_route_info(sd.vault_service, settings))
        config.add_route(**sd.service_api_route_info(sd.vault_file_service, settings))
        config.add_view(v.upload_file, route_name=sd.vault_service.name, request_method="POST")
        config.add_view(v.describe_file, route_name=sd.vault_file_service.name, request_method="HEAD")
        config.add_view(v.download_file, route_name=sd.vault_file_service.name, request_method="GET")
