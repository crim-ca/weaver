import logging
logger = logging.getLogger(__name__)

from twitcher.wps_restapi.processes.processes import get_processes, describe_process, submit_job

def includeme(config):
    config.add_route('processes', '/providers/{provider_id}/processes')
    config.add_route('process', '/providers/{provider_id}/processes/{process_id}')
    config.add_view(get_processes, route_name='processes', request_method='GET', renderer='json')
    config.add_view(describe_process, route_name='process', request_method='GET', renderer='json')
    config.add_view(submit_job, route_name='process', request_method='POST', renderer='json')