import logging
from typing import TYPE_CHECKING

from weaver.formats import OutputFormat
from weaver.wps_restapi import swagger_definitions as sd
from weaver.wps_restapi.providers import providers as p

if TYPE_CHECKING:
    from pyramid.config import Configurator

LOGGER = logging.getLogger(__name__)


def includeme(config):
    # type: (Configurator) -> None
    LOGGER.info("Adding WPS REST API providers...")
    settings = config.registry.settings
    config.add_route(**sd.service_api_route_info(sd.providers_service, settings))
    config.add_route(**sd.service_api_route_info(sd.provider_service, settings))
    config.add_route(**sd.service_api_route_info(sd.provider_processes_service, settings))
    config.add_route(**sd.service_api_route_info(sd.provider_process_service, settings))
    config.add_route(**sd.service_api_route_info(sd.provider_process_package_service, settings))
    config.add_route(**sd.service_api_route_info(sd.provider_execution_service, settings))
    config.add_view(p.get_providers, route_name=sd.providers_service.name,
                    request_method="GET", renderer=OutputFormat.JSON)
    config.add_view(p.add_provider, route_name=sd.providers_service.name,
                    request_method="POST", renderer=OutputFormat.JSON)
    config.add_view(p.get_provider, route_name=sd.provider_service.name,
                    request_method="GET", renderer=OutputFormat.JSON)
    config.add_view(p.remove_provider, route_name=sd.provider_service.name,
                    request_method="DELETE", renderer=OutputFormat.JSON)
    config.add_view(p.get_provider_processes, route_name=sd.provider_processes_service.name,
                    request_method="GET", renderer=OutputFormat.JSON)
    config.add_view(p.get_provider_process, route_name=sd.provider_process_service.name,
                    request_method="GET", renderer=OutputFormat.JSON)
    config.add_view(p.get_provider_process_package, route_name=sd.provider_process_package_service.name,
                    request_method="GET", renderer=OutputFormat.JSON)
    config.add_view(p.submit_provider_job, route_name=sd.provider_jobs_service.name,
                    request_method="POST", renderer=OutputFormat.JSON)
    config.add_view(p.submit_provider_job, route_name=sd.provider_execution_service.name,
                    request_method="POST", renderer=OutputFormat.JSON)
