from twitcher.wps_restapi.processes.processes import (
    get_processes,
    add_process,
    get_process,
    delete_process,
    get_provider_processes,
    describe_provider_process,
    submit_provider_job,
)
from twitcher.wps_restapi import swagger_definitions as sd
import logging


logger = logging.getLogger(__name__)


def includeme(config):
    config.add_route(**sd.service_api_route_info(sd.processes_service))
    config.add_route(**sd.service_api_route_info(sd.process_service))
    config.add_route(**sd.service_api_route_info(sd.provider_processes_service))
    config.add_route(**sd.service_api_route_info(sd.provider_process_service))
    config.add_route(**sd.service_api_route_info(sd.provider_process_jobs_service))
    config.add_view(get_processes, route_name=sd.processes_service.name,
                    request_method='GET', renderer='json')
    config.add_view(add_process, route_name=sd.processes_service.name,
                    request_method='POST', renderer='json')
    config.add_view(get_process, route_name=sd.process_service.name,
                    request_method='GET', renderer='json')
    config.add_view(delete_process, route_name=sd.process_service.name,
                    request_method='DELETE', renderer='json')
    config.add_view(get_provider_processes, route_name=sd.provider_processes_service.name,
                    request_method='GET', renderer='json')
    config.add_view(describe_provider_process, route_name=sd.provider_process_service.name,
                    request_method='GET', renderer='json')
    config.add_view(submit_provider_job, route_name=sd.provider_process_jobs_service.name,
                    request_method='POST', renderer='json')
