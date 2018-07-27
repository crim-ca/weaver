from twitcher.wps_restapi.swagger_definitions import (provider_processes_uri,
                                                      provider_process_uri)
from twitcher.wps_restapi.processes.processes import (get_processes,
                                                      describe_process,
                                                      submit_job)
import logging


logger = logging.getLogger(__name__)


def includeme(config):
    config.add_route('processes', provider_processes_uri)
    config.add_route('process', provider_process_uri)
    config.add_view(get_processes, route_name='processes', request_method='GET', renderer='json')
    config.add_view(describe_process, route_name='process', request_method='GET', renderer='json')
    config.add_view(submit_job, route_name='process', request_method='POST', renderer='json')
