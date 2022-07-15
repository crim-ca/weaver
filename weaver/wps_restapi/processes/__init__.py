import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pyramid.config import Configurator

LOGGER = logging.getLogger(__name__)


def includeme(config):
    # type: (Configurator) -> None

    from weaver.formats import OutputFormat
    from weaver.wps_restapi import swagger_definitions as sd
    from weaver.wps_restapi.processes import processes as p

    LOGGER.info("Adding WPS REST API processes...")
    settings = config.registry.settings
    config.add_route(**sd.service_api_route_info(sd.processes_service, settings))
    config.add_route(**sd.service_api_route_info(sd.process_service, settings))
    config.add_route(**sd.service_api_route_info(sd.process_package_service, settings))
    config.add_route(**sd.service_api_route_info(sd.process_payload_service, settings))
    config.add_route(**sd.service_api_route_info(sd.process_visibility_service, settings))

    # added within jobs (conflict)
    # config.add_route(**sd.service_api_route_info(sd.process_jobs_service, settings))
    # config.add_route(**sd.service_api_route_info(sd.jobs_full_service, settings))
    config.add_route(**sd.service_api_route_info(sd.process_execution_service, settings))

    config.add_view(p.get_processes, route_name=sd.processes_service.name,
                    request_method="GET", renderer=OutputFormat.JSON)
    config.add_view(p.add_local_process, route_name=sd.processes_service.name,
                    request_method="POST", renderer=OutputFormat.JSON)
    config.add_view(p.get_local_process, route_name=sd.process_service.name,
                    request_method="GET", renderer=OutputFormat.JSON)
    config.add_view(p.patch_local_process, route_name=sd.process_service.name,
                    request_method="PATCH", renderer=OutputFormat.JSON)
    config.add_view(p.put_local_process, route_name=sd.process_service.name,
                    request_method="PUT", renderer=OutputFormat.JSON)
    config.add_view(p.delete_local_process, route_name=sd.process_service.name,
                    request_method="DELETE", renderer=OutputFormat.JSON)
    config.add_view(p.get_local_process_package, route_name=sd.process_package_service.name,
                    request_method="GET", renderer=OutputFormat.JSON)
    config.add_view(p.get_local_process_payload, route_name=sd.process_payload_service.name,
                    request_method="GET", renderer=OutputFormat.JSON)
    config.add_view(p.submit_local_job, route_name=sd.process_jobs_service.name,
                    request_method="POST", renderer=OutputFormat.JSON)
    config.add_view(p.submit_local_job, route_name=sd.process_execution_service.name,
                    request_method="POST", renderer=OutputFormat.JSON)
    config.add_view(p.get_process_visibility, route_name=sd.process_visibility_service.name,
                    request_method="GET", renderer=OutputFormat.JSON)
    config.add_view(p.set_process_visibility, route_name=sd.process_visibility_service.name,
                    request_method="PUT", renderer=OutputFormat.JSON)
