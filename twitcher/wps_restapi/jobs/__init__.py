import logging
logger = logging.getLogger(__name__)

from twitcher.wps_restapi.jobs.jobs import *


def includeme(config):
    config.add_route('jobs', '/jobs')
    config.add_route('job_full', '/providers/{provider_id}/processes/{process_id}/jobs/{job_id}')
    config.add_route('job', '/jobs/{job_id}')
    config.add_route('outputs_full', '/providers/{provider_id}/processes/{process_id}/jobs/{job_id}/outputs')
    config.add_route('outputs', '/jobs/{job_id}/outputs')
    config.add_route('output_full', '/providers/{provider_id}/processes/{process_id}/jobs/{job_id}/outputs/{output_id}')
    config.add_route('output', '/jobs/{job_id}/outputs/{output_id}')
    config.add_route('exceptions_full', '/providers/{provider_id}/processes/{process_id}/jobs/{job_id}/exceptions')
    config.add_route('exceptions', '/jobs/{job_id}/exceptions')
    config.add_route('log_full', '/providers/{provider_id}/processes/{process_id}/jobs/{job_id}/log')
    config.add_route('log', '/jobs/{job_id}/log')

    config.add_view(get_jobs, route_name='jobs', request_method='GET', renderer='json')
    config.add_view(get_job_status, route_name='job', request_method='GET', renderer='json')
    config.add_view(get_job_status, route_name='job_full', request_method='GET', renderer='json')
    config.add_view(cancel_job, route_name='job', request_method='DELETE', renderer='json')
    config.add_view(cancel_job, route_name='job_full', request_method='DELETE', renderer='json')
    config.add_view(get_outputs, route_name='outputs', request_method='GET', renderer='json')
    config.add_view(get_outputs, route_name='outputs_full', request_method='GET', renderer='json')
    config.add_view(get_output, route_name='output', request_method='GET', renderer='json')
    config.add_view(get_output, route_name='output_full', request_method='GET', renderer='json')
    config.add_view(get_exceptions, route_name='exceptions', request_method='GET', renderer='json')
    config.add_view(get_exceptions, route_name='exceptions_full', request_method='GET', renderer='json')
    config.add_view(get_log, route_name='log', request_method='GET', renderer='json')
    config.add_view(get_log, route_name='log_full', request_method='GET', renderer='json')
