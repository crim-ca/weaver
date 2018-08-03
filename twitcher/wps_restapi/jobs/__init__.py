from twitcher.wps_restapi import swagger_definitions as sd
from twitcher.wps_restapi.jobs import jobs as j
import logging
logger = logging.getLogger(__name__)


def includeme(config):
    settings = config.registry.settings
    config.add_route(**sd.service_api_route_info(sd.jobs_service, settings))
    config.add_route(**sd.service_api_route_info(sd.job_short_service, settings))
    config.add_route(**sd.service_api_route_info(sd.job_full_service, settings))
    config.add_route(**sd.service_api_route_info(sd.outputs_short_service, settings))
    config.add_route(**sd.service_api_route_info(sd.outputs_full_service, settings))
    config.add_route(**sd.service_api_route_info(sd.output_short_service, settings))
    config.add_route(**sd.service_api_route_info(sd.output_full_service, settings))
    config.add_route(**sd.service_api_route_info(sd.exceptions_short_service, settings))
    config.add_route(**sd.service_api_route_info(sd.exceptions_full_service, settings))
    config.add_route(**sd.service_api_route_info(sd.logs_short_service, settings))
    config.add_route(**sd.service_api_route_info(sd.logs_full_service, settings))

    config.add_view(j.get_jobs, route_name=sd.jobs_service.name, request_method='GET', renderer='json')
    config.add_view(j.get_job_status, route_name=sd.job_short_service.name, request_method='GET', renderer='json')
    config.add_view(j.get_job_status, route_name=sd.job_full_service.name, request_method='GET', renderer='json')
    config.add_view(j.cancel_job, route_name=sd.job_short_service.name, request_method='DELETE', renderer='json')
    config.add_view(j.cancel_job, route_name=sd.job_full_service.name, request_method='DELETE', renderer='json')
    config.add_view(j.get_outputs, route_name=sd.outputs_short_service.name, request_method='GET', renderer='json')
    config.add_view(j.get_outputs, route_name=sd.outputs_full_service.name, request_method='GET', renderer='json')
    config.add_view(j.get_output, route_name=sd.output_short_service.name, request_method='GET', renderer='json')
    config.add_view(j.get_output, route_name=sd.output_full_service.name, request_method='GET', renderer='json')
    config.add_view(j.get_exceptions, route_name=sd.exceptions_short_service.name, request_method='GET', renderer='json')
    config.add_view(j.get_exceptions, route_name=sd.exceptions_full_service.name, request_method='GET', renderer='json')
    config.add_view(j.get_log, route_name=sd.logs_short_service.name, request_method='GET', renderer='json')
    config.add_view(j.get_log, route_name=sd.logs_full_service.name, request_method='GET', renderer='json')
