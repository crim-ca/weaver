import logging

from weaver.formats import OUTPUT_FORMAT_JSON
from weaver.wps_restapi import swagger_definitions as sd
from weaver.wps_restapi.providers import providers as p

LOGGER = logging.getLogger(__name__)


def includeme(config):
    LOGGER.info("Adding WPS REST API providers...")
    settings = config.registry.settings
    config.add_route(**sd.service_api_route_info(sd.providers_service, settings))
    config.add_route(**sd.service_api_route_info(sd.provider_service, settings))
    config.add_route(**sd.service_api_route_info(sd.provider_processes_service, settings))
    config.add_route(**sd.service_api_route_info(sd.provider_process_service, settings))
    config.add_route(**sd.service_api_route_info(sd.provider_execution_service, settings))
    config.add_view(p.get_providers, route_name=sd.providers_service.name,
                    request_method="GET", renderer=OUTPUT_FORMAT_JSON)
    config.add_view(p.add_provider, route_name=sd.providers_service.name,
                    request_method="POST", renderer=OUTPUT_FORMAT_JSON)
    config.add_view(p.get_provider, route_name=sd.provider_service.name,
                    request_method="GET", renderer=OUTPUT_FORMAT_JSON)
    config.add_view(p.remove_provider, route_name=sd.provider_service.name,
                    request_method="DELETE", renderer=OUTPUT_FORMAT_JSON)
    config.add_view(p.get_provider_processes, route_name=sd.provider_processes_service.name,
                    request_method="GET", renderer=OUTPUT_FORMAT_JSON)
    config.add_view(p.get_provider_process, route_name=sd.provider_process_service.name,
                    request_method="GET", renderer=OUTPUT_FORMAT_JSON)
    config.add_view(p.submit_provider_job, route_name=sd.provider_jobs_service.name,
                    request_method="POST", renderer=OUTPUT_FORMAT_JSON)
    config.add_view(p.submit_provider_job, route_name=sd.provider_execution_service.name,
                    request_method="POST", renderer=OUTPUT_FORMAT_JSON)
