from twitcher.wps_restapi import swagger_definitions as sd
from twitcher.wps_restapi.jobs import jobs as j
import logging
logger = logging.getLogger(__name__)


def includeme(config):
    settings = config.registry.settings
    config.add_route(**sd.service_api_route_info(sd.jobs_service, settings))
    config.add_route(**sd.service_api_route_info(sd.job_short_service, settings))
    config.add_route(**sd.service_api_route_info(sd.job_full_service, settings))
    config.add_route(**sd.service_api_route_info(sd.results_short_service, settings))
    config.add_route(**sd.service_api_route_info(sd.results_full_service, settings))
    config.add_route(**sd.service_api_route_info(sd.result_short_service, settings))
    config.add_route(**sd.service_api_route_info(sd.result_full_service, settings))
    config.add_route(**sd.service_api_route_info(sd.exceptions_short_service, settings))
    config.add_route(**sd.service_api_route_info(sd.exceptions_full_service, settings))
    config.add_route(**sd.service_api_route_info(sd.logs_short_service, settings))
    config.add_route(**sd.service_api_route_info(sd.logs_full_service, settings))
    config.add_route(**sd.service_api_route_info(sd.process_jobs_service, settings))
    config.add_route(**sd.service_api_route_info(sd.process_job_service, settings))

    config.add_view(j.get_jobs, route_name=sd.process_jobs_service.name,
                    request_method='GET', renderer='json')
    config.add_view(j.get_jobs, route_name=sd.jobs_service.name,
                    request_method='GET', renderer='json')
    config.add_view(j.get_job_status, route_name=sd.job_short_service.name,
                    request_method='GET', renderer='json')
    config.add_view(j.get_job_status, route_name=sd.job_full_service.name,
                    request_method='GET', renderer='json')
    config.add_view(j.get_job_status, route_name=sd.process_job_service.name,
                    request_method='GET', renderer='json')
    config.add_view(j.cancel_job, route_name=sd.job_short_service.name,
                    request_method='DELETE', renderer='json')
    config.add_view(j.cancel_job, route_name=sd.job_full_service.name,
                    request_method='DELETE', renderer='json')
    config.add_view(j.cancel_job, route_name=sd.process_job_service.name,
                    request_method='DELETE', renderer='json')
    config.add_view(j.get_job_results, route_name=sd.results_short_service.name,
                    request_method='GET', renderer='json')
    config.add_view(j.get_job_results, route_name=sd.results_full_service.name,
                    request_method='GET', renderer='json')
    config.add_view(j.get_job_result, route_name=sd.result_short_service.name,
                    request_method='GET', renderer='json')
    config.add_view(j.get_job_result, route_name=sd.result_full_service.name,
                    request_method='GET', renderer='json')
    config.add_view(j.get_job_exceptions, route_name=sd.exceptions_short_service.name,
                    request_method='GET', renderer='json')
    config.add_view(j.get_job_exceptions, route_name=sd.exceptions_full_service.name,
                    request_method='GET', renderer='json')
    config.add_view(j.get_job_log, route_name=sd.logs_short_service.name,
                    request_method='GET', renderer='json')
    config.add_view(j.get_job_log, route_name=sd.logs_full_service.name,
                    request_method='GET', renderer='json')
