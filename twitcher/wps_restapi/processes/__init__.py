from twitcher.wps_restapi.processes import processes as p
from twitcher.wps_restapi import swagger_definitions as sd
import logging


logger = logging.getLogger(__name__)


def includeme(config):
    settings = config.registry.settings
    config.add_route(**sd.service_api_route_info(sd.provider_processes_service, settings))
    config.add_route(**sd.service_api_route_info(sd.provider_process_service, settings))
    config.add_route(**sd.service_api_route_info(sd.jobs_full_service, settings))
    config.add_view(p.get_provider_processes, route_name=sd.provider_processes_service.name,
                    request_method='GET', renderer='json')
    config.add_view(p.describe_provider_process, route_name=sd.provider_process_service.name,
                    request_method='GET', renderer='json')
    config.add_view(p.submit_provider_job, route_name=sd.jobs_full_service.name,
                    request_method='POST', renderer='json')
