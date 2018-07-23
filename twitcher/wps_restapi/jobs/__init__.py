from twitcher.wps_restapi.swagger_definitions import (jobs_uri,
                                                      job_full_uri,
                                                      job_short_uri,
                                                      outputs_full_uri,
                                                      outputs_short_uri,
                                                      output_full_uri,
                                                      output_short_uri,
                                                      exceptions_full_uri,
                                                      exceptions_short_uri,
                                                      logs_full_uri,
                                                      logs_short_uri)
from twitcher.wps_restapi.jobs.jobs import (get_jobs,
                                            get_job_status,
                                            cancel_job,
                                            get_outputs,
                                            get_output,
                                            get_exceptions,
                                            get_log)
import logging
logger = logging.getLogger(__name__)


def includeme(config):
    config.add_route('jobs', jobs_uri)
    config.add_route('job_full', job_full_uri)
    config.add_route('job', job_short_uri)
    config.add_route('outputs_full', outputs_full_uri)
    config.add_route('outputs', outputs_short_uri)
    config.add_route('output_full', output_full_uri)
    config.add_route('output', output_short_uri)
    config.add_route('exceptions_full', exceptions_full_uri)
    config.add_route('exceptions', exceptions_short_uri)
    config.add_route('log_full', logs_full_uri)
    config.add_route('log', logs_short_uri)

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
